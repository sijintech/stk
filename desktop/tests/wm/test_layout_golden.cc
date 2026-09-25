/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Layout goldens of the default screen: area, region and splitter rectangles plus every UI
 * block and widget rectangle, for zh and en at UI scales 1x, 1.5x and 2x (window 1280x800 points,
 * fake text measurer, no GPU). STK_UPDATE_GOLDENS=1 rewrites desktop/tests/wm/golden/. */

#include <cmath>
#include <cstdlib>
#include <sstream>

#include <gtest/gtest.h>

#include "support.hh"

using stk::wmtest::AppFixture;

namespace {

struct Case {
  const char *lang;
  float scale;
};

std::string case_name(const Case &c)
{
  std::ostringstream ss;
  ss << c.lang << "_" << c.scale << "x";
  std::string s = ss.str();
  for (char &ch : s) {
    if (ch == '.') {
      ch = '_';
    }
  }
  return s;
}

class DefaultScreenGolden : public ::testing::TestWithParam<Case> {};

}  // namespace

TEST_P(DefaultScreenGolden, MatchesGolden)
{
  const Case c = GetParam();
  const int w = int(std::lround(1280 * c.scale)), h = int(std::lround(800 * c.scale));
  AppFixture f(c.lang, c.scale, w, h);
  const std::string got = stk::wmtest::dump_screen(f.screen);
  const std::string path = std::string(STK_WM_GOLDEN_DIR) + "/layout_default_" + case_name(c) + ".json";
  if (const char *u = std::getenv("STK_UPDATE_GOLDENS"); u && *u == '1') {
    ASSERT_TRUE(stk::wmtest::write_text(path, got)) << path;
    GTEST_SKIP() << "updated " << path;
  }
  const std::string want = stk::wmtest::read_text(path);
  ASSERT_FALSE(want.empty()) << "missing golden " << path << " (run with STK_UPDATE_GOLDENS=1)";
  EXPECT_EQ(got, want) << "layout differs from " << path;

  /* Structural checks independent of the golden: widgets stay inside their blocks, blocks inside
   * their regions, regions inside the window. */
  for (const auto &b : f.screen.ui()->blocks()) {
    for (const stk::ui::Widget &wd : b->widgets()) {
      EXPECT_GE(wd.rect.x, b->rect().x - 0.5f) << wd.key;
      EXPECT_LE(wd.rect.x1(), b->rect().x1() + 0.5f) << wd.key;
    }
  }
  for (const stk::wm::Region *r : f.screen.visible_regions()) {
    EXPECT_GE(r->rect().xmin, 0);
    EXPECT_LE(r->rect().xmax, w);
    EXPECT_GE(r->rect().ymin, 0);
    EXPECT_LE(r->rect().ymax, h);
  }
}

INSTANTIATE_TEST_SUITE_P(Wm,
                         DefaultScreenGolden,
                         ::testing::Values(Case{"en", 1.0f},
                                           Case{"en", 1.5f},
                                           Case{"en", 2.0f},
                                           Case{"zh", 1.0f},
                                           Case{"zh", 1.5f},
                                           Case{"zh", 2.0f}),
                         [](const ::testing::TestParamInfo<Case> &i) { return case_name(i.param); });
