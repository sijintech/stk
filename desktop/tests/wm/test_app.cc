/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The application shell on its default screen (fake text measurer, no GPU): layout,
 * splitter / edge drags through events, UI routing and capture, maximize, side regions, tabs,
 * editor switching, area menu, drops, IME placement, wake-ups and the i18n keys of the editors. */

#include <chrono>
#include <cmath>
#include <functional>
#include <mutex>
#include <thread>

#include <gtest/gtest.h>

#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/bridge/client.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/ui_bridge.hh"

#include "support.hh"

using namespace stk;
using stk::wmtest::AppFixture;
using stk::wmtest::ScreenDriver;

namespace {

const wm::Splitter *splitter_between(const wm::Screen &s, const wm::Area &a, const wm::Area &b)
{
  for (const wm::Splitter &sp : s.splitters()) {
    const wm::ScreenNode &n = *sp.node;
    auto contains = [](const wm::ScreenNode &node, const wm::Area &area) {
      std::vector<const wm::ScreenNode *> stack{&node};
      while (!stack.empty()) {
        const wm::ScreenNode *c = stack.back();
        stack.pop_back();
        if (c->area.get() == &area) {
          return true;
        }
        for (const auto &ch : c->children) {
          stack.push_back(ch.get());
        }
      }
      return false;
    };
    if (contains(*n.children[size_t(sp.index)], a) && contains(*n.children[size_t(sp.index) + 1], b)) {
      return &sp;
    }
  }
  return nullptr;
}

/** Clicks the popup item whose text contains `needle` (the popup must be open). */
bool click_popup_item(AppFixture &f, const std::string &needle)
{
  const ui::Context &ui = *f.screen.ui();
  for (const auto &b : ui.blocks()) {
    if (b->kind() != ui::Block::Kind::Popup) {
      continue;
    }
    for (const ui::Widget &w : b->widgets()) {
      if (w.text.find(needle) != std::string::npos) {
        const int top = f.screen.rect().ymax;
        f.drv->click(int(w.rect.cx()), top - 1 - int(w.rect.cy()));
        return true;
      }
    }
  }
  return false;
}

}  // namespace

TEST(App, DefaultLayout)
{
  AppFixture f("en");
  const auto areas = f.screen.areas();
  ASSERT_EQ(areas.size(), 4u);
  EXPECT_EQ(areas[0]->type(), app::kEditorJobs);
  EXPECT_EQ(areas[1]->type(), app::kEditorViewer);
  EXPECT_EQ(areas[2]->type(), app::kEditorProperties);
  EXPECT_EQ(areas[3]->type(), app::kEditorLogs);
  app::EditorArea &bottom = f.area("a4");
  ASSERT_EQ(bottom.tab_count(), 4);
  EXPECT_EQ(bottom.tab(1).type().id, app::kEditorProbe);
  EXPECT_EQ(bottom.tab(2).type().id, app::kEditorTransfers);
  EXPECT_EQ(bottom.tab(3).type().id, app::kEditorBridgeLog);
  /* Jobs | Viewer | Properties side by side over the full-width bottom strip. */
  const wm::Rect jobs = areas[0]->rect(), viewer = areas[1]->rect(), props = areas[2]->rect(),
                 strip = areas[3]->rect();
  EXPECT_EQ(jobs.xmin, 0);
  EXPECT_EQ(props.xmax, 1280);
  EXPECT_LT(jobs.xmax, viewer.xmin);
  EXPECT_LT(viewer.xmax, props.xmin);
  EXPECT_EQ(strip.xmin, 0);
  EXPECT_EQ(strip.xmax, 1280);
  EXPECT_LT(strip.ymax, jobs.ymin);
  EXPECT_NEAR(double(jobs.width()) / 1276.0, 0.22, 0.01);
  EXPECT_NEAR(double(viewer.width()) / 1276.0, 0.53, 0.01);
  /* Top bar and status bar are global areas of one bar height each. */
  const int bar = wm::ui_bar_height_px(1.0f);
  ASSERT_NE(f.screen.global_area(wm::RegionAlign::Top), nullptr);
  EXPECT_EQ(f.screen.global_area(wm::RegionAlign::Top)->rect(), (wm::Rect{0, 800 - bar, 1280, 800}));
  EXPECT_EQ(f.screen.global_area(wm::RegionAlign::Bottom)->rect(), (wm::Rect{0, 0, 1280, bar}));
  /* Regions: header on top of every area; the viewer has a toolbar and a sidebar. */
  app::EditorArea &v = f.area("a2");
  EXPECT_EQ(v.find_region("header")->rect().height(), bar);
  EXPECT_TRUE(v.find_region("toolbar")->visible());
  EXPECT_TRUE(v.find_region("sidebar")->visible());
  EXPECT_FALSE(f.area("a1").find_region("toolbar")->visible());
  /* The UI built one block per visible region plus the bars. */
  EXPECT_NE(f.screen.ui()->find("a2/header/editor_type"), nullptr);
  EXPECT_NE(f.screen.ui()->find("a4/header/tabs"), nullptr);
  EXPECT_NE(f.screen.ui()->find("file"), nullptr);
}

TEST(App, SplitterDragMovesOnlyItsNeighbours)
{
  AppFixture f("en");
  wm::Area &a1 = f.area("a1"), &a2 = f.area("a2"), &a3 = f.area("a3"), &a4 = f.area("a4");
  const wm::Splitter *s = splitter_between(f.screen, a1, a2);
  ASSERT_NE(s, nullptr);
  const auto [bx, by] = AppFixture::center(s->rect);
  const wm::Rect r1 = a1.rect(), r2 = a2.rect(), r3 = a3.rect();
  f.drv->drag(bx, by, bx + 60, by + 5);
  EXPECT_EQ(a1.rect().width(), r1.width() + 60);
  EXPECT_EQ(a2.rect().width(), r2.width() - 60);
  EXPECT_EQ(a3.rect(), r3);
  /* The horizontal bar above the bottom strip: dragging up grows the strip. */
  const wm::Splitter *sv = splitter_between(f.screen, a1, a4);
  ASSERT_NE(sv, nullptr);
  EXPECT_EQ(sv->dir, wm::SplitDir::Vertical);
  const int h4 = a4.rect().height();
  const auto [vx, vy] = AppFixture::center(sv->rect);
  f.drv->drag(vx, vy, vx, vy + 50);
  EXPECT_EQ(a4.rect().height(), h4 + 50);
  /* Far past the minimum: clamped. */
  const wm::Splitter *s2 = splitter_between(f.screen, a1, a2);
  const auto [cx, cy] = AppFixture::center(s2->rect);
  f.drv->drag(cx, cy, 5, cy);
  EXPECT_EQ(a1.rect().width(), a1.min_width(1.0f));
}

TEST(App, DoubleClickSplitterJoins)
{
  AppFixture f("en");
  const wm::Splitter *s = splitter_between(f.screen, f.area("a2"), f.area("a3"));
  ASSERT_NE(s, nullptr);
  const auto [bx, by] = AppFixture::center(s->rect);
  f.drv->move(bx, by);
  f.drv->down(bx, by);
  f.drv->up(bx, by);
  f.drv->wait_ms(100);
  f.drv->down(bx, by);
  f.drv->up(bx, by);
  f.drv->frame();
  ASSERT_EQ(f.screen.areas().size(), 3u);
  EXPECT_EQ(f.screen.find_area("a3"), nullptr); /* The larger viewer stays. */
  EXPECT_EQ(f.area("a2").rect().xmax, 1280);
}

TEST(App, MaximizeWithCtrlSpace)
{
  AppFixture f("en");
  app::EditorArea &v = f.area("a2");
  const auto [x, y] = AppFixture::center(v.find_region("main")->rect());
  f.drv->move(x, y);
  EXPECT_TRUE(f.drv->key(wm::Key::Space, wm::ModCtrl));
  EXPECT_EQ(f.screen.maximized(), &v);
  EXPECT_EQ(v.rect(), f.screen.tree_rect());
  EXPECT_TRUE(f.area("a1").rect().empty());
  /* The status bar tells how to restore. */
  bool hint = false;
  for (const auto &b : f.screen.ui()->blocks()) {
    for (const ui::Widget &w : b->widgets()) {
      hint |= w.text == f.shell->store().tr("app.status.maximized");
    }
  }
  EXPECT_TRUE(hint);
  f.drv->key(wm::Key::Space, wm::ModCtrl);
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_FALSE(f.area("a1").rect().empty());
}

TEST(App, ToolbarAndSidebarToggle)
{
  AppFixture f("en");
  app::EditorArea &v = f.area("a2");
  const auto [x, y] = AppFixture::center(v.find_region("main")->rect());
  f.drv->move(x, y);
  const int main_w = v.find_region("main")->rect().width();
  f.drv->key(wm::Key::T);
  EXPECT_FALSE(v.find_region("toolbar")->visible());
  f.drv->key(wm::Key::N);
  EXPECT_FALSE(v.find_region("sidebar")->visible());
  EXPECT_EQ(v.find_region("main")->rect().width(), v.rect().width());
  EXPECT_GT(v.find_region("main")->rect().width(), main_w);
  f.drv->key(wm::Key::T);
  f.drv->key(wm::Key::N);
  EXPECT_TRUE(v.find_region("toolbar")->visible());
  EXPECT_TRUE(v.find_region("sidebar")->visible());
  /* The jobs editor has neither: T is not consumed there. */
  const auto [jx, jy] = AppFixture::center(f.area("a1").find_region("main")->rect());
  f.drv->move(jx, jy);
  EXPECT_FALSE(f.drv->key(wm::Key::T));
}

TEST(App, SidebarEdgeDragIsClamped)
{
  AppFixture f("en");
  wm::Region &side = *f.area("a2").find_region("sidebar");
  const int y = (side.rect().ymin + side.rect().ymax) / 2;
  const float s0 = side.size_1x();
  f.drv->drag(side.rect().xmin, y, side.rect().xmin - 40, y);
  EXPECT_EQ(side.size_1x(), s0 + 40.0f);
  f.drv->drag(side.rect().xmin, y, side.rect().xmin + 500, y);
  EXPECT_EQ(side.size_1x(), side.min_size_1x);
}

TEST(App, TabsAndEditorSwitching)
{
  AppFixture f("en");
  app::EditorArea &bottom = f.area("a4");
  const auto [x, y] = AppFixture::center(bottom.find_region("main")->rect());
  f.drv->move(x, y);
  f.drv->key(wm::Key::PageDown, wm::ModCtrl);
  EXPECT_EQ(bottom.active_tab(), 1);
  EXPECT_EQ(bottom.type(), app::kEditorProbe);
  f.drv->key(wm::Key::PageUp, wm::ModCtrl);
  f.drv->key(wm::Key::PageUp, wm::ModCtrl);
  EXPECT_EQ(bottom.active_tab(), 3);
  /* Clicking the third tab. */
  const ui::Widget *tabs = f.screen.ui()->find("a4/header/tabs");
  ASSERT_NE(tabs, nullptr);
  const int top = f.screen.rect().ymax;
  f.drv->click(int(tabs->rect.x + tabs->rect.w * 2.5f / 4.0f), top - 1 - int(tabs->rect.cy()));
  EXPECT_EQ(bottom.active_tab(), 2);
  EXPECT_EQ(bottom.type(), app::kEditorTransfers);

  /* The editor-type dropdown replaces the jobs editor (deferred until after the event). */
  app::EditorArea &jobs = f.area("a1");
  const auto [dx, dy] = f.widget_center("a1/header/editor_type");
  f.drv->click(dx, dy);
  ASSERT_TRUE(f.screen.ui()->popup_open());
  ASSERT_TRUE(click_popup_item(f, f.shell->store().tr("editor.properties.title").data()));
  EXPECT_EQ(jobs.type(), app::kEditorProperties);
  EXPECT_EQ(jobs.tab_count(), 1);
}

TEST(App, AreaMenuFromHeaderRightClick)
{
  AppFixture f("en");
  app::EditorArea &props = f.area("a3");
  const wm::Rect h = props.find_region("header")->rect();
  /* Empty header space between the dropdown and the menu button. */
  const ui::Widget *dd = f.screen.ui()->find("a3/header/editor_type");
  ASSERT_NE(dd, nullptr);
  const int x = int(dd->rect.x1()) + 20, y = (h.ymin + h.ymax) / 2;
  f.drv->click(x, y, wm::MouseButton::Right);
  ASSERT_TRUE(f.screen.ui()->popup_open());
  ASSERT_TRUE(click_popup_item(f, f.shell->store().tr("area.menu.split_v").data()));
  ASSERT_EQ(f.screen.areas().size(), 5u);
  wm::Area *created = f.screen.sibling(props, true);
  ASSERT_NE(created, nullptr);
  EXPECT_EQ(created->type(), app::kEditorProperties);
  EXPECT_LT(created->rect().ymax, props.rect().ymin + 1);
  /* Close it again through its own area menu. */
  const auto [mx, my] = f.widget_center(created->id() + "/header/area_menu");
  f.drv->click(mx, my);
  ASSERT_TRUE(click_popup_item(f, f.shell->store().tr("area.menu.close_area").data()));
  EXPECT_EQ(f.screen.areas().size(), 4u);
}

TEST(App, UiCaptureAcrossAreas)
{
  AppFixture f("en");
  /* Press on the viewer sidebar's "Layers" panel header, drag into Properties, release there:
   * the UI keeps the pointer (no toggle outside the header, nothing reaches Properties). */
  const auto [px, py] = f.widget_center("a2/sidebar/layers");
  f.drv->move(px, py);
  f.drv->down(px, py);
  EXPECT_EQ(f.screen.capture(), wm::Screen::Capture::Ui);
  const auto [qx, qy] = AppFixture::center(f.area("a3").find_region("main")->rect());
  f.drv->move(qx, qy);
  EXPECT_EQ(f.screen.capture(), wm::Screen::Capture::Ui);
  f.drv->up(qx, qy);
  f.drv->frame();
  EXPECT_EQ(f.screen.capture(), wm::Screen::Capture::None);
  EXPECT_NE(f.screen.ui()->find("a2/sidebar/layers"), nullptr);
  EXPECT_TRUE(f.screen.ui()->panel_open(f.screen.ui()->find("a2/sidebar/layers")->id, true));
  /* A plain click toggles it. */
  f.drv->click(px, py);
  EXPECT_FALSE(f.screen.ui()->panel_open(f.screen.ui()->find("a2/sidebar/layers")->id, true));
}

TEST(App, DropsRouteToTheAreaUnderThePointer)
{
  AppFixture f("en");
  app::EditorArea &bottom = f.area("a4");
  bottom.set_active_tab(2); /* Transfers. */
  f.drv->frame();
  auto drop = [&](wm::Area &a, std::vector<std::string> paths) {
    const auto [x, y] = AppFixture::center(a.find_region("main")->rect());
    wm::Event e;
    e.type = wm::EventType::Drop;
    e.x = x;
    e.y = y;
    e.paths = std::move(paths);
    const bool r = f.drv->send(e);
    f.drv->frame();
    return r;
  };
  EXPECT_TRUE(drop(bottom, {"/data/run1/phi.bin", "/data/run1/input.toml"}));
  const ui::Widget *t = f.screen.ui()->find("a4/main/transfers");
  ASSERT_NE(t, nullptr);
  EXPECT_EQ(t->table->rows, 2);
  EXPECT_EQ(t->table->cell(0, 0), "phi.bin");
  /* Jobs lists pending uploads; Properties does not take files (logged). */
  EXPECT_TRUE(drop(f.area("a1"), {"/x/a.dat"}));
  EXPECT_NE(f.screen.ui()->find("a1/main/workspace/pending"), nullptr);
  const size_t lines = f.shell->store().app_log().line_count();
  EXPECT_TRUE(drop(f.area("a3"), {"/x/b.dat"}));
  EXPECT_EQ(f.shell->store().app_log().line_count(), lines + 1);
  EXPECT_NE(std::string(f.shell->store().app_log().line(lines)).find("Properties"), std::string::npos);
}

TEST(App, LanguageAndScaleThroughTheTopBar)
{
  AppFixture f("en");
  const auto [lx, ly] = f.widget_center("language");
  f.drv->click(lx, ly);
  ASSERT_TRUE(click_popup_item(f, "\xe4\xb8\xad\xe6\x96\x87"));
  EXPECT_EQ(f.shell->store().language(), "zh_CN");
  EXPECT_EQ(f.screen.ui()->find("file")->text, "\xe6\x96\x87\xe4\xbb\xb6"); /* 文件 */
  /* Without a window manager the scale entries are disabled. */
  const auto [sx, sy] = f.widget_center("scale");
  f.drv->click(sx, sy);
  ASSERT_TRUE(click_popup_item(f, "150%"));
  EXPECT_EQ(f.shell->store().ui_scale(), 1.0f);
}

TEST(App, ScalesKeepEverythingInside)
{
  for (const float s : {1.0f, 1.25f, 1.5f, 2.0f}) {
    AppFixture f("zh", s, int(std::lround(1280 * s)), int(std::lround(800 * s)));
    for (const wm::Area *a : f.screen.areas()) {
      EXPECT_GE(a->rect().width(), a->min_width(s)) << s;
      EXPECT_GE(a->rect().height(), a->min_height(s)) << s;
      for (const auto &r : a->regions()) {
        if (r->visible()) {
          EXPECT_GE(r->rect().xmin, a->rect().xmin);
          EXPECT_LE(r->rect().xmax, a->rect().xmax);
        }
      }
    }
    EXPECT_EQ(f.area("a1").find_region("header")->rect().height(), wm::ui_bar_height_px(s));
  }
}

TEST(App, TooltipWakeupAndRedraw)
{
  AppFixture f("en");
  EXPECT_FALSE(std::isfinite(f.screen.next_wakeup()));
  const auto [x, y] = f.widget_center("a1/header/area_menu");
  f.drv->move(x, y);
  f.drv->frame();
  const double now = double(f.drv->time_ms) / 1000.0;
  EXPECT_NEAR(f.screen.next_wakeup(), now + 0.5, 1e-6);
  f.drv->wait_ms(600);
  f.drv->frame();
  bool tooltip = false;
  for (const auto &b : f.screen.ui()->blocks()) {
    tooltip |= b->kind() == ui::Block::Kind::Tooltip;
  }
  EXPECT_TRUE(tooltip);
}

TEST(App, EditorKeysExistInEveryCatalog)
{
  AppFixture f("en");
  const ui::Catalog &cat = f.shell->store().catalog();
  std::vector<std::string> keys;
  for (const auto &t : f.shell->registry().types()) {
    keys.push_back(t->title_key);
  }
  for (const char *k : {"editor.viewer.tool.orbit", "editor.viewer.tool.pan", "editor.viewer.tool.zoom",
                        "editor.viewer.tool.pick"})
  {
    keys.emplace_back(k);
  }
  for (const auto st : {app::BridgeState::NotStarted, app::BridgeState::Starting, app::BridgeState::Ready,
                        app::BridgeState::Restarting, app::BridgeState::Failed})
  {
    keys.emplace_back(app::bridge_state_key(st));
  }
  EXPECT_EQ(f.shell->registry().types().size(), 7u);
  for (const std::string &k : keys) {
    EXPECT_TRUE(cat.has("zh_CN", k)) << k;
    EXPECT_TRUE(cat.has("en", k)) << k;
  }
}

/* -------------------------------------------------------------------- */
/* IME placement follows the focused text field (a UiRegion in a screen of its own). */

TEST(App, ImeCaretFollowsTheEditedField)
{
  ui::FakeTextMeasurer m;
  ui::MemoryClipboard cb;
  wm::Screen screen;
  ui::ContextConfig cfg;
  cfg.measurer = &m;
  cfg.clipboard = &cb;
  screen.set_ui_config(cfg);
  std::string name = "run";
  std::string other = "x";
  wm::Area &left = screen.add_area("form");
  left.add_region(wm::UiRegion::with_layout("main", wm::RegionAlign::Fill, 0.0f,
                                            [&](ui::Layout &l, const wm::DrawContext &) {
                                              l.text_field("name", ui::bind(name));
                                            }));
  wm::Area &right = screen.add_area("form2");
  right.add_region(wm::UiRegion::with_layout("main", wm::RegionAlign::Fill, 0.0f,
                                             [&](ui::Layout &l, const wm::DrawContext &) {
                                               l.separator(3.0f);
                                               l.text_field("other", ui::bind(other));
                                             }));
  ScreenDriver d(screen, 800, 400, 1.0f);
  d.frame();
  EXPECT_FALSE(screen.ime_caret().has_value());
  const ui::Widget *w = screen.ui()->find("a2/main/other");
  ASSERT_NE(w, nullptr);
  d.click(int(w->rect.cx()), 399 - int(w->rect.cy()));
  const auto caret = screen.ime_caret();
  ASSERT_TRUE(caret.has_value());
  /* Bottom-left window pixels inside the field of the right area. */
  EXPECT_GE(caret->xmin, int(w->rect.x));
  EXPECT_LE(caret->xmax, int(w->rect.x1()) + 1);
  EXPECT_GE(caret->ymin, 400 - int(w->rect.y1()));
  EXPECT_LE(caret->ymax, 400 - int(w->rect.y));
  EXPECT_GE(caret->xmin, right.rect().xmin);
  d.key(wm::Key::End);
  wm::Event ime;
  ime.type = wm::EventType::ImeUpdate;
  ime.ime.composite = "\xe4\xb8\xad";
  ime.ime.cursor = 3;
  d.send(ime);
  d.frame();
  EXPECT_TRUE(screen.ime_composing());
  ime.type = wm::EventType::ImeEnd;
  ime.ime.result = "\xe4\xb8\xad";
  ime.ime.composite.clear();
  d.send(ime);
  d.key(wm::Key::Enter);
  EXPECT_EQ(other, "x\xe4\xb8\xad");
  EXPECT_FALSE(screen.ime_caret().has_value());
  EXPECT_EQ(name, "run");
}

TEST(App, BridgeStatusFollowsTheClientThroughTheExecutor)
{
  /* The executor stands in for WindowManager::executor(): callbacks wait in a queue until the
   * "main loop" runs them. */
  std::vector<std::function<void()>> queue;
  std::mutex mutex;
  bridge::ClientOptions o;
  o.command = {"/nonexistent/stk-no-such-bridge"};
  o.executor = [&](std::function<void()> fn) {
    std::lock_guard lock(mutex);
    queue.push_back(std::move(fn));
  };
  o.restart.max_failures = 1;
  o.restart.initial_backoff_s = 0.01;
  std::unique_ptr<bridge::Client> client = bridge::Client::create(o);
  AppFixture f("en");
  app::AppStore &store = f.shell->store();
  auto run_queue = [&]() {
    std::vector<std::function<void()>> q;
    {
      std::lock_guard lock(mutex);
      q.swap(queue);
    }
    for (auto &fn : q) {
      fn();
    }
  };
  {
    app::BridgeStatus status(store, *client, nullptr);
    EXPECT_EQ(store.bridge_state(), app::BridgeState::NotStarted);
    client->start();
    for (int i = 0; i < 500 && client->state() != bridge::BridgeState::Failed; i++) {
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    ASSERT_EQ(client->state(), bridge::BridgeState::Failed);
    /* Nothing reaches the store before the main loop runs the posted callbacks. */
    EXPECT_EQ(store.bridge_state(), app::BridgeState::NotStarted);
    run_queue();
    EXPECT_EQ(store.bridge_state(), app::BridgeState::Failed);
    EXPECT_FALSE(store.bridge_error().empty());
    f.drv->frame();
    bool shown = false;
    const std::string want =
        store.catalog().format("app.status.bridge", {{"state", std::string(store.tr("app.status.bridge.failed"))}});
    for (const auto &b : f.screen.ui()->blocks()) {
      for (const ui::Widget &w : b->widgets()) {
        shown |= w.text == want;
      }
    }
    EXPECT_TRUE(shown) << want;
    /* A state change posted now but run after BridgeStatus is gone is ignored. */
    client->restart();
  }
  store.set_bridge_state(app::BridgeState::NotStarted);
  for (int i = 0; i < 100; i++) {
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  run_queue();
  EXPECT_EQ(store.bridge_state(), app::BridgeState::NotStarted);
  client.reset();
  run_queue();
}

TEST(App, SplitterDragWithoutFramesInBetween)
{
  AppFixture f("en", 1.0f, 1100, 700);
  wm::Area &a1 = f.area("a1");
  const wm::Splitter *s = splitter_between(f.screen, a1, f.area("a2"));
  ASSERT_NE(s, nullptr);
  const int x = (s->rect.xmin + s->rect.xmax) / 2, y = (s->rect.ymin + s->rect.ymax) / 2;
  const int w0 = a1.rect().width();
  f.drv->move(x, y);
  f.drv->down(x, y);
  for (int i = 1; i <= 4; i++) {
    f.drv->move(x + 20 * i, y);
  }
  f.drv->up(x + 80, y);
  f.drv->frame();
  EXPECT_EQ(a1.rect().width(), w0 + 80);
}
