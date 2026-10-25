/* SPDX-License-Identifier: GPL-2.0-or-later */
/** CPU-only layout subscriptions. No native view, window or GPU context is created. */
#include <gtest/gtest.h>

#include <type_traits>
#include <utility>

#include "stk/app/editor.hh"
#include "stk/wm/screen.hh"
#include "support.hh"

using namespace stk;
using namespace stk::wm;

namespace {
static_assert(!std::is_copy_constructible_v<Screen::LayoutObserver>);
static_assert(!std::is_copy_assignable_v<Screen::LayoutObserver>);
static_assert(std::is_nothrow_move_constructible_v<Screen::LayoutObserver>);
static_assert(std::is_nothrow_move_assignable_v<Screen::LayoutObserver>);

class ObserverRegion : public Region {
 public:
  ObserverRegion() : Region("main") {}
  void build_ui(ui::Context &ui, const DrawContext &) override
  {
    auto &layout = ui.block(block_name(), ui_rect()).layout();
    layout.button("content", "Resolved content", [] {});
    if (modal) { ui.modal("observer_modal", "Modal", [] {}).label("Resolved overlay"); }
  }
  bool modal = false;
};

std::unique_ptr<Area> make_area()
{
  auto area = std::make_unique<Area>("observer");
  area->emplace_region<ObserverRegion>();
  return area;
}

struct LayoutObserverTest : ::testing::Test {
  ui::FakeTextMeasurer measurer;
  Screen screen;
  wmtest::ScreenDriver driver{screen, 800, 600, 1.0f};

  void SetUp() override
  {
    ui::ContextConfig config;
    config.measurer = &measurer;
    screen.set_ui_config(config);
    screen.set_area_factory([](const std::string &) { return make_area(); });
    screen.set_root(make_area());
    driver.frame();
  }
};

struct OwnerProbe {
  int ready = 0, invalidated = 0, destroyed = 0;
  bool visible = false;
  std::vector<std::string> events;
};

class ObserverEditor final : public app::Editor {
 public:
  ObserverEditor(const app::EditorType &type, OwnerProbe &probe) : Editor(type), probe_(probe) {}
  ~ObserverEditor() override
  {
    probe_.visible = false;
    ++probe_.destroyed;
    probe_.events.push_back("destroyed");
    // observer_ is cancelled by its member destructor, while Screen::clear is destroying tabs.
  }
  void draw_main(ui::Layout &layout, app::EditorContext &ctx) override
  {
    if (!observer_) {
      owner_ = &ctx.area;
      observer_ = ctx.area.screen()->observe_layout([this](const DrawContext &draw) {
        EXPECT_EQ(probe_.destroyed, 0);
        ++probe_.ready;
        probe_.visible = draw.ui && &owner_->editor() == this && !owner_->rect().empty();
      }, [this] {
        EXPECT_EQ(probe_.destroyed, 0);
        ++probe_.invalidated;
        probe_.visible = false;
        probe_.events.push_back("invalidated");
      });
    }
    layout.label("Observer owner");
  }
 private:
  OwnerProbe &probe_;
  app::EditorArea *owner_ = nullptr;
  Screen::LayoutObserver observer_;
};

void register_owner(wmtest::AppFixture &fixture, OwnerProbe &probe)
{
  fixture.shell->registry().add({"observer_owner", "Observer owner", [&probe](const app::EditorType &type) {
    return std::make_unique<ObserverEditor>(type, probe);
  }});
}
}  // namespace

TEST_F(LayoutObserverTest, ReadySeesFinalWidgetsOverlaysAndFrameNumber)
{
  const auto previous = screen.frames_built();
  auto *region = static_cast<ObserverRegion *>(screen.find_region("main"));
  ASSERT_NE(region, nullptr);
  region->modal = true;
  int calls = 0;
  auto subscription = screen.observe_layout([&](const DrawContext &ctx) {
    ++calls;
    EXPECT_EQ(screen.frames_built(), previous + 1);
    EXPECT_EQ(ctx.rect, driver.ctx.rect);
    EXPECT_EQ(ctx.ui, screen.ui());
    ASSERT_NE(ctx.ui, nullptr);
    const auto *widget = ctx.ui->find(region->block_name() + "/content");
    ASSERT_NE(widget, nullptr);
    EXPECT_GT(widget->rect.w, 0);
    EXPECT_GT(widget->rect.h, 0);
    bool overlay = false;
    for (const auto &block : ctx.ui->blocks()) {
      if (block->kind() == ui::Block::Kind::Modal) {
        overlay = true;
        EXPECT_GT(block->frame().w, 0);
        EXPECT_GT(block->frame().h, 0);
      }
    }
    EXPECT_TRUE(overlay);
  });
  driver.frame();
  EXPECT_EQ(calls, 1);
}

TEST_F(LayoutObserverTest, RedrawDoesNotInvalidateButActualRectangleAndScaleDo)
{
  int invalid = 0, ready = 0;
  auto subscription = screen.observe_layout([&](const DrawContext &) { ++ready; }, [&] {
    ++invalid;
  });
  driver.frame();
  screen.tag_redraw();
  driver.frame();
  screen.layout(driver.ctx.rect, driver.ctx);
  EXPECT_EQ(invalid, 0);
  driver.ctx.rect.xmax += 120;
  screen.layout(driver.ctx.rect, driver.ctx);
  EXPECT_EQ(invalid, 1);
  screen.layout(driver.ctx.rect, driver.ctx);
  screen.invalidate_layout();
  EXPECT_EQ(invalid, 1);  // Multiple causes coalesce until another completed frame.
  driver.frame();
  driver.ctx.ui_scale = 1.5f;
  screen.layout(driver.ctx.rect, driver.ctx);
  EXPECT_EQ(invalid, 2);
  driver.frame();
  EXPECT_EQ(ready, 4);
}

TEST_F(LayoutObserverTest, RegionVisibilityAndSizeInvalidateBeforeMutation)
{
  auto &area = *screen.areas().front();
  auto &side = area.emplace_region<Region>("side", RegionAlign::Left, 80.0f);
  driver.frame();
  int invalid = 0;
  bool expected_visible = true;
  float expected_size = 80;
  auto subscription = screen.observe_layout([](const DrawContext &) {}, [&] {
    ++invalid;
    EXPECT_EQ(side.visible(), expected_visible);
    EXPECT_FLOAT_EQ(side.size_1x(), expected_size);
  });
  side.set_visible(false);
  EXPECT_EQ(invalid, 1);
  side.set_visible(false);
  driver.frame();
  expected_visible = false;
  side.set_size_1x(100);
  EXPECT_EQ(invalid, 2);
  expected_size = 100;
  side.set_size_1x(100);
  driver.frame();
  EXPECT_EQ(invalid, 2);
  subscription.reset();
}

TEST_F(LayoutObserverTest, AHiddenAreaStillReceivesReadyAndCanWithdrawItsView)
{
  Area *owner = screen.areas().front();
  Area &other = screen.add_area(make_area());
  driver.frame();
  int ready = 0, invalid = 0;
  bool visible = true;
  auto subscription = screen.observe_layout([&](const DrawContext &) {
    ++ready;
    visible = !owner->rect().empty();
  }, [&] { ++invalid; visible = false; });
  screen.set_maximized(&other);
  EXPECT_FALSE(visible);  // Synchronous, before any paint.
  EXPECT_EQ(invalid, 1);
  driver.frame();
  EXPECT_EQ(ready, 1);
  EXPECT_FALSE(visible);
  screen.set_maximized(nullptr);
  driver.frame();
  EXPECT_EQ(ready, 2);
  EXPECT_TRUE(visible);
}

TEST_F(LayoutObserverTest, NoUiStillNotifiesAndDoesNotLeakTheCallersUiPointer)
{
  Screen plain;
  plain.set_root(make_area());
  DrawContext ctx = driver.ctx;
  ctx.ui = screen.ui();
  ASSERT_NE(ctx.ui, nullptr);
  int ready = 0;
  auto subscription = plain.observe_layout([&](const DrawContext &resolved) {
    ++ready;
    EXPECT_EQ(resolved.ui, nullptr);
    EXPECT_EQ(resolved.rect, ctx.rect);
    EXPECT_EQ(resolved.window, nullptr);
  });
  plain.update(ctx);  // No fonts/config: ensure_ui cannot create a context.
  EXPECT_EQ(ready, 1);
  EXPECT_EQ(plain.ui(), nullptr);
}

TEST_F(LayoutObserverTest, ReadyCanCancelItselfAndALaterObserver)
{
  Screen::LayoutObserver first, later;
  int first_calls = 0, later_calls = 0;
  first = screen.observe_layout([&](const DrawContext &) {
    ++first_calls;
    first.reset();
    later.reset();
  });
  later = screen.observe_layout([&](const DrawContext &) { ++later_calls; });
  driver.frame();
  driver.frame();
  EXPECT_EQ(first_calls, 1);
  EXPECT_EQ(later_calls, 0);
  EXPECT_FALSE(first);
  EXPECT_FALSE(later);
}

TEST_F(LayoutObserverTest, InvalidatedCanCancelAndReenterWithoutRepeatingOrCallingCancelledOwners)
{
  Screen::LayoutObserver first, later;
  int first_calls = 0, later_calls = 0;
  first = screen.observe_layout({}, [&] {
    ++first_calls;
    first.reset();
    later.reset();
    screen.invalidate_layout();
  });
  later = screen.observe_layout({}, [&] { ++later_calls; });
  screen.invalidate_layout();
  EXPECT_EQ(first_calls, 1);
  EXPECT_EQ(later_calls, 0);
  EXPECT_FALSE(first);
  EXPECT_FALSE(later);
}

TEST_F(LayoutObserverTest, ObserverRegisteredInNotificationStartsOnNextUpdate)
{
  Screen::LayoutObserver added;
  int added_ready = 0, added_invalid = 0;
  auto first = screen.observe_layout([&](const DrawContext &) {
    if (added) { return; }
    added = screen.observe_layout([&](const DrawContext &) { ++added_ready; }, [&] { ++added_invalid; });
    screen.invalidate_layout();
  });
  driver.frame();
  EXPECT_EQ(added_ready, 0);
  EXPECT_EQ(added_invalid, 0);
  driver.frame();
  EXPECT_EQ(added_ready, 1);
  screen.invalidate_layout();
  EXPECT_EQ(added_invalid, 1);
}

TEST_F(LayoutObserverTest, InvalidationDuringReadyStopsLaterGeometryDeliveryAndRecursiveUpdate)
{
  bool withdraw = true;
  int later = 0, invalid = 0;
  auto first = screen.observe_layout([&](const DrawContext &) {
    if (withdraw) {
      withdraw = false;
      screen.invalidate_layout();
      driver.frame();  // Defensive guard: borrowed frame cannot be rebuilt recursively.
    }
  });
  auto second = screen.observe_layout([&](const DrawContext &) { ++later; }, [&] { ++invalid; });
  const auto before = screen.frames_built();
  driver.frame();
  EXPECT_EQ(screen.frames_built(), before + 1);
  EXPECT_EQ(later, 0);
  EXPECT_EQ(invalid, 1);
  driver.frame();
  EXPECT_EQ(later, 1);
}

TEST_F(LayoutObserverTest, MoveAssignmentCancelsPreviousSubscription)
{
  int former = 0, kept = 0;
  auto destination = screen.observe_layout([&](const DrawContext &) { ++former; });
  auto source = screen.observe_layout([&](const DrawContext &) { ++kept; });
  destination = std::move(source);
  EXPECT_FALSE(source);
  EXPECT_TRUE(destination);
  driver.frame();
  EXPECT_EQ(former, 0);
  EXPECT_EQ(kept, 1);
  auto moved = std::move(destination);
  EXPECT_FALSE(destination);
  EXPECT_TRUE(moved);
  moved.reset();
  driver.frame();
  EXPECT_EQ(kept, 1);
}

TEST(LayoutObserverLifetime, ScreenCanDieBeforeItsSubscription)
{
  int ready = 0, invalid = 0;
  Screen::LayoutObserver retained;
  {
    Screen screen;
    retained = screen.observe_layout([&](const DrawContext &) { ++ready; }, [&] { ++invalid; });
    DrawContext ctx;
    screen.update(ctx);
    EXPECT_EQ(ready, 1);
    EXPECT_TRUE(retained);
  }
  EXPECT_EQ(invalid, 1);
  EXPECT_FALSE(retained);
  retained.reset();
  EXPECT_EQ(invalid, 1);
}

TEST(LayoutObserverLifetime, DestructionInvalidatesASubscriptionQueuedByTheLastReadyCallback)
{
  int ready = 0, invalid = 0;
  Screen::LayoutObserver retained;
  {
    Screen screen;
    auto first = screen.observe_layout([&](const DrawContext &) {
      retained = screen.observe_layout([&](const DrawContext &) { ++ready; }, [&] { ++invalid; });
    });
    screen.update({});
    EXPECT_EQ(ready, 0);
    EXPECT_EQ(invalid, 0);
  }
  EXPECT_EQ(invalid, 1);
  EXPECT_FALSE(retained);
}

TEST_F(LayoutObserverTest, ReadyCanDeferATreeMutationWithoutChangingItsBorrowedFrame)
{
  bool queued = false;
  const auto *original = screen.areas().front();
  int invalid = 0;
  auto subscription = screen.observe_layout([&](const DrawContext &) {
    if (!queued) {
      queued = true;
      screen.defer([&] { screen.clear(); });
      EXPECT_EQ(screen.areas().front(), original);
    }
  }, [&] { ++invalid; });
  screen.clear_redraw();
  driver.frame();
  EXPECT_TRUE(screen.needs_redraw());
  EXPECT_EQ(screen.areas().size(), 1u);
  EXPECT_EQ(invalid, 0);
  driver.frame();
  EXPECT_TRUE(screen.areas().empty());
  EXPECT_EQ(invalid, 1);
}

TEST_F(LayoutObserverTest, AdoptInvalidatesBothScreensButDoesNotTransferSubscriptions)
{
  Screen prepared;
  prepared.set_root(make_area());
  wmtest::ScreenDriver other{prepared, 400, 300, 1.0f};
  other.frame();
  int destination_ready = 0, source_ready = 0, destination_invalid = 0, source_invalid = 0;
  auto destination = screen.observe_layout([&](const DrawContext &ctx) {
    ++destination_ready;
    EXPECT_EQ(ctx.rect, driver.ctx.rect);
  }, [&] { ++destination_invalid; });
  auto source = prepared.observe_layout([&](const DrawContext &ctx) {
    ++source_ready;
    EXPECT_EQ(ctx.rect, other.ctx.rect);
  }, [&] { ++source_invalid; });
  screen.adopt_tree_from(prepared);
  EXPECT_EQ(destination_invalid, 1);
  EXPECT_EQ(source_invalid, 1);
  EXPECT_TRUE(prepared.areas().empty());
  driver.frame();
  EXPECT_EQ(destination_ready, 1);
  EXPECT_EQ(source_ready, 0);
  other.frame();
  EXPECT_EQ(source_ready, 1);
  EXPECT_EQ(destination_ready, 1);
  EXPECT_TRUE(source);
  EXPECT_TRUE(destination);
}

TEST(LayoutObserverLifetime, ClearInvalidatesBeforeDestroyingAnEditorThatOwnsItsSubscription)
{
  OwnerProbe probe;  // Must outlive the fixture's editors.
  wmtest::AppFixture fixture;
  register_owner(fixture, probe);
  ASSERT_TRUE(fixture.area("a1").set_tabs({"observer_owner"}, 0));
  fixture.drv->frame();
  ASSERT_EQ(probe.ready, 1);
  ASSERT_TRUE(probe.visible);
  fixture.screen.clear();
  EXPECT_FALSE(probe.visible);
  EXPECT_EQ(probe.invalidated, 1);
  EXPECT_EQ(probe.destroyed, 1);
  EXPECT_EQ(probe.events, (std::vector<std::string>{"invalidated", "destroyed"}));
  fixture.drv->frame();
  fixture.screen.invalidate_layout();
  EXPECT_EQ(probe.ready, 1);
  EXPECT_EQ(probe.invalidated, 1);
}

TEST(LayoutObserverLifetime, TabSwitchImmediatelyInvalidatesAndHiddenEditorStillReceivesLayout)
{
  OwnerProbe probe;
  wmtest::AppFixture fixture;
  register_owner(fixture, probe);
  auto &area = fixture.area("a1");
  ASSERT_TRUE(area.set_tabs({"observer_owner", app::kEditorLogs}, 0));
  fixture.drv->frame();
  ASSERT_TRUE(probe.visible);
  area.set_active_tab(0);
  EXPECT_EQ(probe.invalidated, 0);
  area.set_active_tab(1);
  EXPECT_EQ(probe.invalidated, 1);
  EXPECT_FALSE(probe.visible);
  fixture.drv->frame();
  EXPECT_EQ(probe.ready, 2);
  EXPECT_FALSE(probe.visible);
  area.set_active_tab(0);
  EXPECT_FALSE(probe.visible);
  fixture.drv->frame();
  EXPECT_EQ(probe.ready, 3);
  EXPECT_TRUE(probe.visible);
  EXPECT_EQ(probe.destroyed, 0);
}
