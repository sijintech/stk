/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Screen tree: split / join / resize with minimum sizes, hit testing, event routing,
 * pointer capture, maximize, drops and deferred changes, on plain areas (no GPU, no UI). */

#include <gtest/gtest.h>

#include "stk/wm/screen.hh"

#include "support.hh"

using namespace stk;
using namespace stk::wm;
using stk::wmtest::ScreenDriver;

namespace {

class RecRegion : public Region {
 public:
  explicit RecRegion(std::string name = "main", RegionAlign align = RegionAlign::Fill, float size = 0.0f)
      : Region(std::move(name), align, size)
  {
  }
  bool handle_event(const Event &e, const DrawContext &) override
  {
    events.push_back(e.type);
    if (on_event) {
      on_event(e);
    }
    return true;
  }
  std::vector<EventType> events;
  std::function<void(const Event &)> on_event;
};

class RecArea : public Area {
 public:
  explicit RecArea(const std::string &type) : Area(type)
  {
    main = &emplace_region<RecRegion>();
  }
  bool on_drop(const Event &e) override
  {
    dropped = e.paths;
    return true;
  }
  RecRegion *main;
  std::vector<std::string> dropped;
};

std::unique_ptr<Area> rec(const std::string &type = "rec")
{
  return std::make_unique<RecArea>(type);
}

RecArea &as_rec(Area *a)
{
  return *static_cast<RecArea *>(a);
}

std::pair<int, int> center(const Rect &r)
{
  return {(r.xmin + r.xmax) / 2, (r.ymin + r.ymax) / 2};
}

struct TreeFixture : ::testing::Test {
  Screen screen;
  ScreenDriver drv{screen, 1000, 500, 1.0f};
  void SetUp() override
  {
    screen.set_area_factory([](const std::string &t) { return rec(t); });
  }
};

}  // namespace

TEST_F(TreeFixture, AddAreaIsAHorizontalRow)
{
  screen.add_area(rec("a"));
  screen.add_area(rec("b")).set_weight(2.0f);
  screen.add_area(rec("c"));
  drv.frame();
  const auto areas = screen.areas();
  ASSERT_EQ(areas.size(), 3u);
  /* 1000 - 2 gaps of 2 px = 996 = 249 + 498 + 249. */
  EXPECT_EQ(areas[0]->rect(), (Rect{0, 0, 249, 500}));
  EXPECT_EQ(areas[1]->rect(), (Rect{251, 0, 749, 500}));
  EXPECT_EQ(areas[2]->rect(), (Rect{751, 0, 1000, 500}));
  ASSERT_EQ(screen.splitters().size(), 2u);
  EXPECT_EQ(screen.splitters()[0].rect, (Rect{249, 0, 251, 500}));
  EXPECT_EQ(areas[0]->id(), "a1");
  EXPECT_EQ(areas[2]->id(), "a3");
}

TEST_F(TreeFixture, SplitJoinAndCollapse)
{
  Area &a = screen.set_root(rec("a"));
  drv.frame();
  Area *b = screen.split(a, SplitDir::Horizontal, 0.5f);
  ASSERT_NE(b, nullptr);
  EXPECT_EQ(b->type(), "a"); /* Same type as the source. */
  drv.frame();
  Area *c = screen.split(*b, SplitDir::Vertical, 0.25f);
  ASSERT_NE(c, nullptr);
  drv.frame();
  /* H[a, V[b, c]]: c is the bottom quarter of the right half. */
  EXPECT_EQ(screen.root()->dir, SplitDir::Horizontal);
  EXPECT_EQ(b->rect().xmin, c->rect().xmin);
  EXPECT_GT(b->rect().ymin, c->rect().ymax - 1);
  EXPECT_NEAR(double(c->rect().height()) / 498.0, 0.25, 0.01);
  EXPECT_FALSE(screen.can_join(a, *b)); /* Different parents: no shared full edge. */
  EXPECT_TRUE(screen.can_join(*b, *c));
  EXPECT_EQ(screen.sibling(*b, true), c);
  EXPECT_EQ(screen.sibling(a, true), nullptr); /* Its next sibling is a split, not an area. */

  ASSERT_TRUE(screen.join(*b, *c));
  drv.frame();
  ASSERT_EQ(screen.areas().size(), 2u);
  EXPECT_EQ(b->rect().height(), 500); /* The vertical split collapsed. */
  EXPECT_TRUE(screen.root()->children[1]->leaf());
  ASSERT_TRUE(screen.join(a, *b));
  drv.frame();
  ASSERT_EQ(screen.areas().size(), 1u);
  EXPECT_TRUE(screen.root()->leaf());
  EXPECT_EQ(a.rect(), (Rect{0, 0, 1000, 500}));
}

TEST_F(TreeFixture, SplitAlongParentDirectionInserts)
{
  Area &a = screen.set_root(rec());
  Area *b = screen.split(a, SplitDir::Horizontal, 0.5f);
  Area *c = screen.split(a, SplitDir::Horizontal, 0.5f); /* Between a and b. */
  drv.frame();
  ASSERT_EQ(screen.root()->children.size(), 3u);
  EXPECT_EQ(screen.root()->children[1]->area.get(), c);
  EXPECT_LT(a.rect().xmax, c->rect().xmin);
  EXPECT_LT(c->rect().xmax, b->rect().xmin);
  Area *d = screen.split(a, SplitDir::Horizontal, 0.5f, true); /* Before a. */
  drv.frame();
  EXPECT_EQ(screen.root()->children[0]->area.get(), d);
}

TEST_F(TreeFixture, SplitRefusedBelowMinimumSize)
{
  drv.ctx.rect = {0, 0, 300, 200};
  Area &a = screen.set_root(rec());
  drv.frame();
  Area *b = screen.split(a, SplitDir::Horizontal, 0.5f);
  ASSERT_NE(b, nullptr); /* 149 px each >= 100. */
  drv.frame();
  EXPECT_EQ(screen.split(*b, SplitDir::Horizontal, 0.5f), nullptr); /* 73 px < 100. */
  EXPECT_EQ(screen.areas().size(), 2u);
}

TEST_F(TreeFixture, ResizeKeepsMinimumsAndOtherChildren)
{
  screen.add_area(rec());
  screen.add_area(rec());
  screen.add_area(rec());
  drv.frame();
  ScreenNode &root = const_cast<ScreenNode &>(*screen.root());
  const auto areas = screen.areas();
  const Rect c_before = areas[2]->rect();
  const int total = areas[0]->rect().width() + areas[1]->rect().width();
  EXPECT_EQ(screen.resize_split(root, 0, 400), 400);
  drv.frame();
  EXPECT_EQ(areas[0]->rect().width(), 400);
  EXPECT_EQ(areas[1]->rect().width(), total - 400);
  EXPECT_EQ(areas[2]->rect(), c_before);
  /* Past the neighbour's minimum. */
  EXPECT_EQ(screen.resize_split(root, 0, 5000), total - areas[1]->min_width(1.0f));
  drv.frame();
  EXPECT_EQ(areas[1]->rect().width(), areas[1]->min_width(1.0f));
  EXPECT_EQ(areas[2]->rect(), c_before);
  /* Below its own minimum. */
  EXPECT_EQ(screen.resize_split(root, 0, 1), areas[0]->min_width(1.0f));
}

TEST_F(TreeFixture, WindowShrinkKeepsMinimums)
{
  screen.add_area(rec());
  screen.add_area(rec()).set_weight(8.0f);
  screen.add_area(rec());
  drv.frame();
  drv.ctx.rect = {0, 0, 330, 200};
  drv.frame();
  for (Area *a : screen.areas()) {
    EXPECT_GE(a->rect().width(), a->min_width(1.0f));
  }
  /* Far too small: nothing overlaps, everything stays inside the window. */
  drv.ctx.rect = {0, 0, 90, 40};
  drv.frame();
  int x = 0;
  for (Area *a : screen.areas()) {
    EXPECT_GE(a->rect().xmin, x);
    EXPECT_LE(a->rect().xmax, 90);
    x = a->rect().xmax;
  }
}

TEST_F(TreeFixture, SplitterDragViaEvents)
{
  screen.add_area(rec());
  screen.add_area(rec());
  drv.frame();
  auto areas = screen.areas();
  const Splitter s = screen.splitters().at(0);
  const auto [bx, by] = center(s.rect);
  EXPECT_EQ(screen.splitter_at(bx, by)->index, 0);
  EXPECT_NE(screen.splitter_at(s.rect.xmin - 2, by), nullptr); /* Hit zone is widened. */
  EXPECT_EQ(screen.splitter_at(s.rect.xmin - 10, by), nullptr);
  const int w0 = areas[0]->rect().width();
  drv.move(bx, by);
  drv.down(bx, by);
  EXPECT_EQ(screen.capture(), Screen::Capture::Splitter);
  drv.move(bx + 60, by + 30);
  drv.move(bx + 100, by - 200); /* Across the other area: still the splitter. */
  drv.up(bx + 100, by);
  drv.frame();
  EXPECT_EQ(areas[0]->rect().width(), w0 + 100);
  EXPECT_EQ(screen.capture(), Screen::Capture::None);
  EXPECT_TRUE(as_rec(areas[0]).main->events.empty());
  EXPECT_TRUE(as_rec(areas[1]).main->events.empty());
}

TEST_F(TreeFixture, VerticalSplitterDrag)
{
  Area &top = screen.set_root(rec());
  Area *bottom = screen.split(top, SplitDir::Vertical, 0.3f);
  drv.frame();
  const Splitter s = screen.splitters().at(0);
  EXPECT_EQ(s.dir, SplitDir::Vertical);
  const auto [bx, by] = center(s.rect);
  const int h0 = bottom->rect().height();
  drv.drag(bx, by, bx, by - 40); /* Down (y grows upwards): the top area grows. */
  EXPECT_EQ(bottom->rect().height(), h0 - 40);
}

TEST_F(TreeFixture, DoubleClickOnSplitterJoinsKeepingTheLarger)
{
  Area &a = screen.set_root(rec("a"));
  Area *b = screen.split(a, SplitDir::Horizontal, 0.7f);
  drv.frame();
  const auto [bx, by] = center(screen.splitters().at(0).rect);
  drv.move(bx, by);
  drv.down(bx, by);
  drv.up(bx, by);
  drv.wait_ms(120);
  drv.down(bx, by);
  drv.up(bx, by);
  drv.frame();
  ASSERT_EQ(screen.areas().size(), 1u);
  EXPECT_EQ(screen.areas()[0], b);
}

TEST_F(TreeFixture, PointerCaptureAcrossAreas)
{
  screen.add_area(rec());
  screen.add_area(rec());
  drv.frame();
  auto areas = screen.areas();
  RecRegion &ra = *as_rec(areas[0]).main, &rb = *as_rec(areas[1]).main;
  const auto [ax, ay] = center(areas[0]->rect());
  const auto [bx, by] = center(areas[1]->rect());
  drv.move(ax, ay);
  drv.down(ax, ay);
  EXPECT_EQ(screen.capture(), Screen::Capture::Region);
  EXPECT_EQ(screen.focused_region(), &ra);
  drv.move(bx, by);
  drv.up(bx, by);
  EXPECT_EQ(ra.events, (std::vector<EventType>{EventType::MouseMove, EventType::MouseDown, EventType::MouseMove,
                                                EventType::MouseUp}));
  EXPECT_TRUE(rb.events.empty());
  drv.move(bx + 1, by);
  EXPECT_EQ(rb.events, (std::vector<EventType>{EventType::MouseMove}));
  /* Keys go to the region under the pointer. */
  drv.key(Key::A);
  EXPECT_EQ(rb.events.back(), EventType::KeyUp);
}

TEST_F(TreeFixture, MaximizeAndRestore)
{
  Area &a = screen.set_root(rec());
  Area *b = screen.split(a, SplitDir::Horizontal, 0.5f);
  Area *c = screen.split(*b, SplitDir::Vertical, 0.5f);
  drv.frame();
  const Rect ra = a.rect(), rb = b->rect(), rc = c->rect();
  const auto [cx, cy] = center(rc);
  drv.move(cx, cy);
  EXPECT_TRUE(drv.key(Key::Space, ModCtrl));
  EXPECT_EQ(screen.maximized(), c);
  EXPECT_EQ(c->rect(), screen.tree_rect());
  EXPECT_TRUE(a.rect().empty());
  EXPECT_TRUE(b->rect().empty());
  EXPECT_TRUE(screen.splitters().empty());
  EXPECT_EQ(screen.area_at(10, 10), c);
  EXPECT_TRUE(drv.key(Key::Space, ModCtrl));
  EXPECT_EQ(screen.maximized(), nullptr);
  EXPECT_EQ(a.rect(), ra);
  EXPECT_EQ(b->rect(), rb);
  EXPECT_EQ(c->rect(), rc);
  /* Joining away a maximized area restores. */
  screen.set_maximized(c);
  ASSERT_TRUE(screen.join(*b, *c));
  EXPECT_EQ(screen.maximized(), nullptr);
}

TEST_F(TreeFixture, RegionEdgeResize)
{
  Area &a = screen.set_root(rec());
  Region &side = a.emplace_region<RecRegion>("sidebar", RegionAlign::Right, 200.0f);
  side.resizable = true;
  side.min_size_1x = 120.0f;
  side.max_size_1x = 300.0f;
  drv.frame();
  /* The Fill region was added first but still takes what the sidebar leaves. */
  EXPECT_EQ(as_rec(&a).main->rect().xmax, side.rect().xmin);
  EXPECT_EQ(side.rect().width(), 200);
  const int ex = side.rect().xmin, ey = (side.rect().ymin + side.rect().ymax) / 2;
  drv.drag(ex, ey, ex - 50, ey);
  EXPECT_EQ(side.size_1x(), 250.0f);
  drv.drag(side.rect().xmin, ey, side.rect().xmin - 400, ey);
  EXPECT_EQ(side.size_1x(), 300.0f);
  drv.drag(side.rect().xmin, ey, side.rect().xmin + 400, ey);
  EXPECT_EQ(side.size_1x(), 120.0f);
}

TEST_F(TreeFixture, DropsGoToTheAreaUnderThePointer)
{
  screen.add_area(rec());
  screen.add_area(rec());
  drv.frame();
  auto areas = screen.areas();
  const auto [bx, by] = center(areas[1]->rect());
  Event e;
  e.type = EventType::DragEnter;
  e.x = bx;
  e.y = by;
  EXPECT_TRUE(drv.send(e));
  e.type = EventType::Drop;
  e.paths = {"/tmp/a.stkp", "/tmp/b.txt"};
  EXPECT_TRUE(drv.send(e));
  EXPECT_EQ(as_rec(areas[1]).dropped, e.paths);
  EXPECT_TRUE(as_rec(areas[0]).dropped.empty());
}

TEST_F(TreeFixture, DeferredChangesRunAfterDispatch)
{
  Area &a = screen.set_root(rec());
  drv.frame();
  RecRegion &r = *as_rec(&a).main;
  bool ran_inside = false;
  r.on_event = [&](const Event &e) {
    if (e.type == EventType::MouseDown) {
      screen.defer([&]() { screen.split(a, SplitDir::Vertical, 0.5f); });
      ran_inside = screen.areas().size() > 1;
    }
  };
  const auto [x, y] = center(a.rect());
  drv.click(x, y);
  EXPECT_FALSE(ran_inside);
  EXPECT_EQ(screen.areas().size(), 2u);
}

TEST_F(TreeFixture, RedrawTags)
{
  Area &a = screen.set_root(rec());
  drv.frame();
  int requests = 0;
  screen.on_redraw_request = [&]() { requests++; };
  screen.clear_redraw();
  as_rec(&a).main->tag_redraw();
  EXPECT_TRUE(screen.needs_redraw());
  EXPECT_TRUE(as_rec(&a).main->redraw_tagged());
  EXPECT_EQ(requests, 1);
}
