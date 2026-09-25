/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Layout goldens: resolved widget rects and draw lists of the gallery screens, serialized to
 * JSON, for en and zh at UI scales 1x, 1.5x and 2x (fake text measurer, no GPU).
 * STK_UPDATE_GOLDENS=1 rewrites desktop/tests/ui/golden/. */
#include <cstdlib>
#include <sstream>

#include <gtest/gtest.h>

#include "screens.hh"
#include "stk/ui/golden.hh"
#include "support.hh"

using namespace stk::ui;
namespace g = stk::ui::gallery;

namespace {

struct Case {
  g::Screen screen;
  const char *lang;
  float scale;
};

std::string scale_name(float s)
{
  std::ostringstream ss;
  ss << s << "x";
  return ss.str();
}

std::string case_name(const Case &c)
{
  std::string s = std::string(g::screen_name(c.screen)) + "_" + (std::string(c.lang) == "en" ? "en" : "zh") + "_" +
                  scale_name(c.scale);
  for (char &ch : s) {
    if (ch == '.') {
      ch = '_';
    }
  }
  return s;
}

class LayoutGolden : public ::testing::TestWithParam<Case> {};

}  // namespace

TEST_P(LayoutGolden, MatchesGolden)
{
  const Case c = GetParam();
  FakeTextMeasurer m;
  MemoryClipboard cb;
  g::State s;
  ASSERT_TRUE(g::init_state(s, STK_DESKTOP_DIR, c.lang));
  if (c.screen == g::Screen::Form) {
    std::string err;
    ASSERT_TRUE(g::load_form(s, STK_REPO_ROOT, &err)) << err;
  }
  ContextConfig cfg;
  cfg.measurer = &m;
  cfg.clipboard = &cb;
  cfg.catalog = &s.catalog;
  Context ctx(cfg);
  ctx.set_scale(1.0f, c.scale);
  const Vec2 base = g::screen_size(c.screen);
  const Vec2 win{std::round(base.x * c.scale), std::round(base.y * c.scale)};
  if (c.screen == g::Screen::Overlays) {
    g::build_staged(ctx, s, c.screen, win, 100.0);
  }
  else {
    g::build(ctx, s, c.screen, win, 100.0);
  }

  /* Structural sanity independent of the golden. */
  for (const auto &b : ctx.blocks()) {
    for (const Widget &w : b->widgets()) {
      EXPECT_GE(w.rect.w, 0.0f) << w.key;
      EXPECT_GT(w.rect.h, 0.0f) << w.key;
      EXPECT_GE(w.rect.x, b->frame().x - 0.5f) << w.key;
      EXPECT_LE(w.rect.x1(), b->frame().x1() + 0.5f) << w.key;
      EXPECT_EQ(w.rect.x, std::round(w.rect.x)) << w.key << ": pixel aligned";
    }
  }
  const std::string got = dump_frame(ctx);
  const std::string path = std::string(STK_UI_GOLDEN_DIR) + "/" + case_name(c) + ".json";
  if (std::getenv("STK_UPDATE_GOLDENS")) {
    ASSERT_TRUE(test::write_text(path, got)) << path;
    return;
  }
  const std::string want = test::read_text(path);
  if (got != want) {
    const std::string actual = case_name(c) + ".actual.json";
    test::write_text(actual, got);
    std::istringstream a(got), b(want);
    std::string la, lb;
    int line = 0;
    while (true) {
      line++;
      const bool ea = !std::getline(a, la), eb = !std::getline(b, lb);
      if (ea || eb || la != lb) {
        ADD_FAILURE() << path << " differs at line " << line << "\n  golden: " << (eb ? "<eof>" : lb)
                      << "\n  actual: " << (ea ? "<eof>" : la) << "\n(actual written to " << actual
                      << "; STK_UPDATE_GOLDENS=1 to accept)";
        break;
      }
    }
  }
}

static std::vector<Case> all_cases()
{
  std::vector<Case> out;
  for (const g::Screen s : {g::Screen::Widgets, g::Screen::Lists, g::Screen::Form, g::Screen::Overlays}) {
    for (const char *lang : {"zh_CN", "en"}) {
      for (const float scale : {1.0f, 1.5f, 2.0f}) {
        out.push_back({s, lang, scale});
      }
    }
  }
  return out;
}

INSTANTIATE_TEST_SUITE_P(Screens, LayoutGolden, ::testing::ValuesIn(all_cases()),
                         [](const ::testing::TestParamInfo<Case> &info) { return case_name(info.param); });

TEST(LayoutGolden, StagedOverlaysArePresent)
{
  FakeTextMeasurer m;
  g::State s;
  ASSERT_TRUE(g::init_state(s, STK_DESKTOP_DIR, "zh_CN"));
  ContextConfig cfg;
  cfg.measurer = &m;
  cfg.catalog = &s.catalog;
  Context ctx(cfg);
  g::build_staged(ctx, s, g::Screen::Overlays, g::screen_size(g::Screen::Overlays), 100.0);
  int kinds[5] = {0, 0, 0, 0, 0};
  for (const auto &b : ctx.blocks()) {
    kinds[int(b->kind())]++;
  }
  EXPECT_EQ(kinds[int(Block::Kind::Modal)], 1);
  EXPECT_EQ(kinds[int(Block::Kind::Popup)], 1);
  EXPECT_EQ(kinds[int(Block::Kind::Tooltip)], 1);
  EXPECT_EQ(kinds[int(Block::Kind::Toast)], 1);
  ASSERT_NE(ctx.edit_state(), nullptr);
  EXPECT_TRUE(ctx.edit_state()->composing());
}
