/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Size distribution with minimum sizes and splitter pair clamping (no GPU). */

#include <cmath>
#include <numeric>
#include <random>

#include <gtest/gtest.h>

#include "stk/wm/csd.hh"
#include "stk/wm/layout_math.hh"

using namespace stk::wm;

static int sum(const std::vector<int> &v)
{
  return std::accumulate(v.begin(), v.end(), 0);
}

TEST(LayoutMath, ProportionalShares)
{
  EXPECT_EQ(distribute_sizes(300, {1, 1, 1}, {0, 0, 0}), (std::vector<int>{100, 100, 100}));
  EXPECT_EQ(distribute_sizes(100, {1, 1, 1}, {0, 0, 0}), (std::vector<int>{34, 33, 33}));
  EXPECT_EQ(distribute_sizes(1000, {0.22f, 0.53f, 0.25f}, {0, 0, 0}), (std::vector<int>{220, 530, 250}));
  /* 7.5 / 2.5: the leftover pixel goes to the earlier child on equal remainders. */
  EXPECT_EQ(distribute_sizes(10, {3, 1}, {}), (std::vector<int>{8, 2}));
}

TEST(LayoutMath, MinimumsArePinned)
{
  /* The small child would get 50 but needs 120: it is pinned, the others share the rest. */
  const std::vector<int> s = distribute_sizes(1000, {0.05f, 0.5f, 0.45f}, {120, 100, 100});
  EXPECT_EQ(s[0], 120);
  EXPECT_EQ(sum(s), 1000);
  EXPECT_NEAR(double(s[1]) / s[2], 0.5 / 0.45, 0.02);
  /* Cascading pins: pinning one child pushes another below its minimum. */
  const std::vector<int> c = distribute_sizes(400, {0.1f, 0.2f, 0.7f}, {100, 100, 50});
  EXPECT_EQ(c[0], 100);
  EXPECT_EQ(c[1], 100);
  EXPECT_EQ(c[2], 200);
}

TEST(LayoutMath, NotEnoughRoomSharesByMinimum)
{
  const std::vector<int> s = distribute_sizes(100, {1, 1}, {150, 50});
  EXPECT_EQ(s, (std::vector<int>{75, 25}));
  EXPECT_EQ(distribute_sizes(0, {1, 1}, {10, 10}), (std::vector<int>{0, 0}));
  EXPECT_EQ(distribute_sizes(-5, {1}, {0}), (std::vector<int>{0}));
}

TEST(LayoutMath, DegenerateFactors)
{
  EXPECT_EQ(distribute_sizes(90, {0, 0, 0}, {}), (std::vector<int>{30, 30, 30}));
  EXPECT_EQ(sum(distribute_sizes(90, {NAN, INFINITY, -1.0f}, {})), 90);
  EXPECT_TRUE(distribute_sizes(10, {}, {}).empty());
}

TEST(LayoutMath, RandomizedInvariants)
{
  std::mt19937 rng(42);
  for (int iter = 0; iter < 5000; iter++) {
    const int n = 1 + int(rng() % 6);
    std::vector<float> f(n);
    std::vector<int> m(n);
    for (int i = 0; i < n; i++) {
      f[i] = float(rng() % 1000) / 100.0f;
      m[i] = int(rng() % 200);
    }
    const int avail = int(rng() % 2000);
    const std::vector<int> s = distribute_sizes(avail, f, m);
    ASSERT_EQ(int(s.size()), n);
    ASSERT_EQ(sum(s), avail);
    const bool room = std::accumulate(m.begin(), m.end(), 0) <= avail;
    for (int i = 0; i < n; i++) {
      ASSERT_GE(s[i], 0);
      if (room) {
        ASSERT_GE(s[i], m[i]) << "iter " << iter << " child " << i;
      }
    }
  }
}

TEST(LayoutMath, ClampPair)
{
  EXPECT_EQ(clamp_pair(500, 200, 100, 100), 200);
  EXPECT_EQ(clamp_pair(500, 20, 100, 100), 100);
  EXPECT_EQ(clamp_pair(500, 480, 100, 100), 400);
  EXPECT_EQ(clamp_pair(150, 75, 100, 100), 75); /* Cannot satisfy both: by minimum ratio. */
  EXPECT_EQ(clamp_pair(0, 10, 1, 1), 0);
}

TEST(Csd, LayoutGeometry)
{
  const int w = 1280, h = 800;
  const int bar = ui_bar_height_px(1.0f);
  CsdLayout l = csd_compute_layout(w, h, 1.0f, {CsdButtonKind::Menu},
                                   {CsdButtonKind::Minimize, CsdButtonKind::Maximize, CsdButtonKind::Close}, false);
  EXPECT_EQ(l.titlebar, (Rect{0, h - bar, w, h}));
  ASSERT_EQ(l.buttons.size(), 4u);
  const int bw = int(std::lround(csd_config().button_width_1x));
  EXPECT_EQ(l.left_reserve, bw);
  EXPECT_EQ(l.right_reserve, 3 * bw);
  /* The close button sits at the right edge, the menu button at the left edge. */
  for (const CsdButton &b : l.buttons) {
    EXPECT_EQ(b.rect.ymin, h - bar);
    EXPECT_EQ(b.rect.ymax, h);
    if (b.kind == CsdButtonKind::Close) {
      EXPECT_EQ(b.rect.xmax, w);
    }
    if (b.kind == CsdButtonKind::Menu) {
      EXPECT_EQ(b.rect.xmin, 0);
    }
  }
  /* The drag zone excludes the menus and the buttons. */
  EXPECT_EQ(l.drag.xmin, bw + int(std::lround(csd_config().menu_width_1x)));
  EXPECT_EQ(l.drag.xmax, w - 3 * bw);
  EXPECT_GT(l.border, 0);
  /* Maximized: no resize border; 2x doubles everything. */
  EXPECT_EQ(csd_compute_layout(w, h, 1.0f, {}, {CsdButtonKind::Close}, true).border, 0);
  const CsdLayout l2 = csd_compute_layout(2 * w, 2 * h, 2.0f, {}, {CsdButtonKind::Close}, false);
  EXPECT_EQ(l2.titlebar.height(), ui_bar_height_px(2.0f));
  EXPECT_EQ(l2.right_reserve, 2 * bw);
  /* A window narrower than the menus has no drag zone rather than a negative one. */
  const CsdLayout tiny = csd_compute_layout(200, 100, 1.0f, {}, {CsdButtonKind::Close}, false);
  EXPECT_LE(tiny.drag.xmin, tiny.drag.xmax);
}
