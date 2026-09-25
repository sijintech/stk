/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Layout persistence: JSON / file round trips and the fallback on corrupt files. */

#include <filesystem>

#include <gtest/gtest.h>

#include "stk/wm/layout_store.hh"

#include "support.hh"

using namespace stk;
using stk::wmtest::AppFixture;
namespace fs = std::filesystem;

namespace {

/** Changes everything the layout file stores. */
void customize(AppFixture &f)
{
  wm::Screen &s = f.screen;
  /* A split, a resized splitter, a resized and a hidden side region, another tab, a maximized
   * area, English and a 1.5x UI scale. */
  ASSERT_NE(s.split(f.area("a3"), wm::SplitDir::Vertical, 0.4f), nullptr);
  f.drv->frame();
  s.resize_split(const_cast<wm::ScreenNode &>(*f.area("a1").node()->parent), 0, 300);
  f.area("a2").find_region("sidebar")->set_size_1x(260.0f);
  f.area("a2").set_toolbar_open(false);
  f.area("a4").set_active_tab(3);
  f.area("a4").add_tab(app::kEditorViewer, false);
  s.set_maximized(&f.area("a2"));
  f.shell->set_language("en");
  f.shell->set_ui_scale(1.5f);
  f.drv->frame();
}

}  // namespace

TEST(Persistence, JsonRoundTrip)
{
  AppFixture f("zh");
  customize(f);
  const wm::LayoutFile saved = f.shell->capture_layout(f.screen, nullptr);
  const std::string text = wm::layout_to_json(saved).dump(2);

  wm::LayoutFile parsed;
  std::string err;
  ASSERT_TRUE(wm::layout_from_json(nlohmann::json::parse(text), parsed, &err)) << err;
  EXPECT_EQ(parsed.language, "en");
  EXPECT_FLOAT_EQ(parsed.ui_scale, 1.5f);
  EXPECT_EQ(parsed.window.width, app::kDefaultWindowWidth);

  AppFixture g("zh");
  ASSERT_TRUE(g.shell->apply_layout(g.screen, parsed, &err)) << err;
  g.drv->frame();
  EXPECT_EQ(g.shell->store().language(), "en");
  EXPECT_FLOAT_EQ(g.shell->store().ui_scale(), 1.5f);
  EXPECT_EQ(g.screen.to_json(), f.screen.to_json());
  ASSERT_EQ(g.screen.areas().size(), 5u);
  EXPECT_EQ(g.screen.maximized(), g.screen.find_area("a2"));
  EXPECT_EQ(g.area("a4").tab_count(), 5);
  EXPECT_EQ(g.area("a4").active_tab(), 3);
  EXPECT_FALSE(g.area("a2").find_region("toolbar")->visible());
  EXPECT_FLOAT_EQ(g.area("a2").find_region("sidebar")->size_1x(), 260.0f);
  /* Same rectangles once restored (after un-maximizing both). */
  f.screen.set_maximized(nullptr);
  g.screen.set_maximized(nullptr);
  f.drv->frame();
  g.drv->frame();
  const auto fa = f.screen.areas(), ga = g.screen.areas();
  for (size_t i = 0; i < fa.size(); i++) {
    EXPECT_EQ(fa[i]->id(), ga[i]->id());
    EXPECT_EQ(fa[i]->rect(), ga[i]->rect()) << fa[i]->id();
  }
  /* New areas continue the id sequence. */
  wm::Area *n = g.screen.split(g.area("a1"), wm::SplitDir::Vertical);
  ASSERT_NE(n, nullptr);
  EXPECT_EQ(n->id(), "a6");
}

TEST(Persistence, FileRoundTripAndMissingFile)
{
  const std::string dir = wmtest::temp_dir("layout");
  const fs::path path = fs::path(dir) / "sub" / "layout.json";
  AppFixture f("zh");
  customize(f);
  ASSERT_TRUE(f.shell->save(f.screen, nullptr, path));
  EXPECT_TRUE(fs::exists(path));
  EXPECT_FALSE(fs::exists(fs::path(path) += ".tmp"));

  AppFixture g("zh");
  ASSERT_TRUE(g.shell->restore(g.screen, path));
  EXPECT_EQ(g.screen.to_json(), f.screen.to_json());

  AppFixture h("zh");
  const nlohmann::json before = h.screen.to_json();
  EXPECT_FALSE(h.shell->restore(h.screen, fs::path(dir) / "missing.json"));
  EXPECT_EQ(h.screen.to_json(), before);
  EXPECT_FALSE(fs::exists(fs::path(dir) / "missing.json.corrupt"));
  wm::LayoutFile lf;
  EXPECT_EQ(wm::load_layout_file(fs::path(dir) / "missing.json", lf), wm::LayoutLoad::Missing);
  fs::remove_all(dir);
}

TEST(Persistence, CorruptFilesFallBackToTheDefault)
{
  const std::string dir = wmtest::temp_dir("corrupt");
  AppFixture ref("zh");
  const std::string good = wm::layout_to_json(ref.shell->capture_layout(ref.screen, nullptr)).dump();
  auto replace = [&](const std::string &from, const std::string &to) {
    std::string s = good;
    const size_t p = s.find(from);
    EXPECT_NE(p, std::string::npos) << from;
    if (p != std::string::npos) {
      s.replace(p, from.size(), to);
    }
    return s;
  };
  const std::vector<std::pair<std::string, std::string>> cases = {
      {"garbage", "\x01\x02 not json at all"},
      {"truncated", good.substr(0, good.size() / 2)},
      {"empty", ""},
      {"array", "[1, 2, 3]"},
      {"wrong_format", replace("stk.desktop.layout", "something.else")},
      {"newer_version", replace("\"version\":1", "\"version\":99")},
      {"bad_scale", replace("\"ui_scale\":1.0", "\"ui_scale\":50")},
      {"negative_factor", replace("\"factor\":0.22", "\"factor\":-1")},
      {"duplicate_id", replace("\"id\":\"a2\"", "\"id\":\"a1\"")},
      {"unknown_editor", replace("\"type\":\"probe\"", "\"type\":\"nonsense\"")},
      {"bad_split", replace("\"split\":\"vertical\"", "\"split\":\"diagonal\"")},
      {"bad_state", replace("\"active\":0", "\"active\":17")},
      {"no_screen", replace("\"screen\":", "\"scree\":")},
  };
  for (const auto &[name, text] : cases) {
    const fs::path path = fs::path(dir) / (name + ".json");
    ASSERT_TRUE(wmtest::write_text(path.string(), text));
    AppFixture f("zh");
    const nlohmann::json before = f.screen.to_json();
    EXPECT_FALSE(f.shell->restore(f.screen, path)) << name;
    EXPECT_EQ(f.screen.to_json(), before) << name; /* Unchanged: still the default layout. */
    EXPECT_EQ(f.shell->store().language(), "zh_CN") << name;
    EXPECT_TRUE(fs::exists(fs::path(path) += ".corrupt")) << name;
    EXPECT_FALSE(fs::exists(path)) << name;
    EXPECT_GE(f.shell->store().app_log().line_count(), 1u) << name;
  }
  /* The unmodified text restores fine (the replacements above really hit the file). */
  const fs::path ok = fs::path(dir) / "good.json";
  ASSERT_TRUE(wmtest::write_text(ok.string(), good));
  AppFixture f("en");
  EXPECT_TRUE(f.shell->restore(f.screen, ok));
  EXPECT_EQ(f.shell->store().language(), "zh_CN");
  /* Oversized files are rejected before parsing. */
  const fs::path big = fs::path(dir) / "big.json";
  ASSERT_TRUE(wmtest::write_text(big.string(), std::string(wm::kLayoutMaxBytes + 10, ' ')));
  wm::LayoutFile lf;
  EXPECT_EQ(wm::load_layout_file(big, lf), wm::LayoutLoad::Corrupt);
  fs::remove_all(dir);
}

TEST(Persistence, ScreenFromJsonIsAtomic)
{
  AppFixture f("en");
  const nlohmann::json before = f.screen.to_json();
  nlohmann::json bad = before;
  bad["root"]["children"][1]["area"]["state"]["tabs"][2]["type"] = "missing";
  std::string err;
  EXPECT_FALSE(f.screen.from_json(bad, &err));
  EXPECT_NE(err.find("state"), std::string::npos) << err;
  EXPECT_EQ(f.screen.to_json(), before);
  bad = before;
  bad["root"]["children"] = nlohmann::json::array({before["root"]["children"][0]});
  EXPECT_FALSE(f.screen.from_json(bad, &err));
  EXPECT_EQ(f.screen.to_json(), before);
  /* Too deep. */
  nlohmann::json deep = before["root"]["children"][1];
  for (int i = 0; i < 20; i++) {
    nlohmann::json leaf = before["root"]["children"][1];
    leaf["area"]["id"] = "d" + std::to_string(i);
    deep = {{"factor", 1}, {"split", "horizontal"}, {"children", {deep, leaf}}};
  }
  EXPECT_FALSE(f.screen.from_json({{"root", deep}}, &err));
  EXPECT_EQ(f.screen.to_json(), before);
}

TEST(Persistence, SplitCopiesAreaState)
{
  AppFixture f("en");
  app::EditorArea &bottom = f.area("a4");
  bottom.set_active_tab(2);
  bottom.set_sidebar_open(false);
  auto *copy = dynamic_cast<app::EditorArea *>(f.screen.split(bottom, wm::SplitDir::Horizontal, 0.5f));
  ASSERT_NE(copy, nullptr);
  EXPECT_EQ(copy->tab_count(), 4);
  EXPECT_EQ(copy->active_tab(), 2);
  EXPECT_EQ(copy->type(), app::kEditorTransfers);
  EXPECT_FALSE(copy->sidebar_open());
}
