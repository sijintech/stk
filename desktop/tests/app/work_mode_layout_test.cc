/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "../wm/support.hh"
#include "stk/app/viewer_state.hh"
#include <algorithm>

namespace stk::app {
namespace {
using Mode = AppShell::WorkMode;
using Json = nlohmann::json;

class WorkModeLayouts : public ::testing::Test {
 protected:
  wmtest::AppFixture f{"en", 1, 1280, 900};
  void switch_to(Mode mode) {
    const auto result = f.shell->switch_work_mode(&f.screen, mode);
    ASSERT_TRUE(result.ok()) << result.error().message;
    f.drv->frame();
  }
};

TEST_F(WorkModeLayouts, KeepsViewerAndHiddenDraftInstancesAndRestoresIndependentPreferences)
{
  auto &viewer = f.area("a2"), &editing = f.area("a3");
  auto *viewer_editor = &viewer.editor();
  ASSERT_TRUE(editing.add_tab(kEditorPython));
  auto *python = &editing.editor();
  ASSERT_TRUE(python->load_state({{"source", "print('draft 保留')"}}));
  editing.set_active_tab(0);
  const auto python_state = python->save_workspace_state();
  const auto viewer_state = f.shell->store().viewer().save_workspace_state();
  const auto analysis = f.screen.arrangement();
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  auto *ai = &editing.editor(); ASSERT_EQ(ai->type().id, kEditorAI);
  editing.set_sidebar_open(true); editing.set_toolbar_open(false);
  ASSERT_TRUE(f.screen.swap_areas(viewer, f.area("a4")));
  f.screen.set_maximized(&editing);
  const auto preparation = f.screen.arrangement();
  for (int i = 0; i < 3; ++i) {
    ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Analysis));
    EXPECT_EQ(f.screen.arrangement(), analysis); EXPECT_EQ(editing.active_tab(), 0);
    EXPECT_EQ(&viewer.editor(), viewer_editor); EXPECT_EQ(python->save_workspace_state(), python_state);
    EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer_state);
    ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
    EXPECT_EQ(f.screen.arrangement(), preparation); EXPECT_EQ(&editing.editor(), ai);
    EXPECT_TRUE(editing.sidebar_open()); EXPECT_FALSE(editing.toolbar_open());
  }
}

TEST_F(WorkModeLayouts, TracksMovedAndDuplicateTabsByInstanceAndRetainsNewAreas)
{
  auto &editing = f.area("a3");
  ASSERT_TRUE(editing.add_tab(kEditorPython)); auto *selected = &editing.editor();
  ASSERT_TRUE(editing.add_tab(kEditorPython, false));
  const auto selected_index = editing.active_tab();
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  auto *extra = dynamic_cast<EditorArea *>(f.screen.split(f.area("a4"), wm::SplitDir::Horizontal, 0.4f, false, kEditorLogs));
  ASSERT_NE(extra, nullptr);
  ASSERT_TRUE(editing.move_tab_to(selected_index, *extra, false));
  const auto geometry = f.screen.arrangement();
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Analysis));
  EXPECT_EQ(f.screen.areas().size(), 5u); EXPECT_EQ(&extra->editor(), selected);
  // Added areas stay present in every mode; no hidden old tree owns discarded editors.
  EXPECT_EQ(f.screen.root()->children.size(), geometry.at("root").at("children").size());
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  EXPECT_EQ(f.screen.find_area(extra->id()), extra);
}

TEST_F(WorkModeLayouts, LayoutAndPortableWorkspaceRoundTripAndLegacyDefaults)
{
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  f.area("a3").set_weight(0.71f);
  f.area("a3").set_sidebar_open(true);
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Analysis));
  const auto layout = f.shell->capture_layout(f.screen, nullptr);
  const auto workspace = f.shell->capture_workspace();
  wmtest::AppFixture restored;
  std::string error;
  ASSERT_TRUE(restored.shell->apply_layout(restored.screen, layout, &error)) << error;
  auto result = restored.shell->switch_work_mode(&restored.screen, Mode::Preparation);
  ASSERT_TRUE(result.ok()); EXPECT_NEAR(restored.area("a3").weight(), 0.71f, 1e-6);
  EXPECT_TRUE(restored.area("a3").sidebar_open());
  wmtest::AppFixture imported;
  ASSERT_TRUE(imported.shell->apply_workspace(workspace, &error)) << error;
  result = imported.shell->switch_work_mode(&imported.screen, Mode::Preparation);
  ASSERT_TRUE(result.ok()); EXPECT_EQ(imported.area("a3").editor().type().id, kEditorAI);
  EXPECT_NEAR(imported.area("a3").weight(), 0.71f, 1e-6);
  auto legacy = layout; legacy.screen.erase("work_modes");
  ASSERT_TRUE(restored.shell->apply_layout(restored.screen, legacy, &error)) << error;
  EXPECT_EQ(restored.shell->work_mode(restored.screen), Mode::Analysis);
}

TEST_F(WorkModeLayouts, BadSavedModeDoesNotReplaceEditorsLanguageOrWorkspace)
{
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Analysis));
  const auto before = f.shell->capture_workspace();
  auto *editor = &f.area("a2").editor();
  for (int problem = 0; problem < 5; ++problem) {
    auto invalid = f.shell->capture_layout(f.screen, nullptr);
    auto &modes = invalid.screen["work_modes"];
    if (problem == 0) { modes["version"] = 2; }
    if (problem == 1) { modes["active"] = "report"; }
    if (problem == 2) { modes["layouts"]["preparation"]["panes"][0]["tab"] = 16; }
    if (problem == 3) { modes["layouts"]["analysis"]["geometry"]["maximized"] = "gone"; }
    if (problem == 4) { modes["layouts"]["analysis"]["panes"][0]["type"] = "absent"; }
    invalid.language = "zh_CN";
    std::string error;
    EXPECT_FALSE(f.shell->apply_layout(f.screen, invalid, &error)); EXPECT_FALSE(error.empty());
    EXPECT_EQ(&f.area("a2").editor(), editor); EXPECT_EQ(f.shell->capture_workspace(), before);
    auto workspace = before;
    workspace["windows"][0]["screen"] = io::Json(invalid.screen);
    EXPECT_FALSE(f.shell->apply_workspace(workspace, &error));
    EXPECT_EQ(f.shell->capture_workspace(), before);
  }
}

TEST_F(WorkModeLayouts, AnotherWindowKeepsIndependentModeAndClosingForgetsPreferences)
{
  wm::Screen other;
  f.shell->install(other, nullptr); f.shell->build_default_layout(other);
  const auto original = other.to_json();
  ASSERT_NO_FATAL_FAILURE(switch_to(Mode::Preparation));
  EXPECT_EQ(f.shell->work_mode(other), Mode::Analysis); EXPECT_EQ(other.to_json(), original);
  EXPECT_FALSE(f.shell->switch_work_mode(nullptr, Mode::Preparation).ok());
  f.shell->forget(f.screen);
  EXPECT_FALSE(f.shell->switch_work_mode(&f.screen, Mode::Analysis).ok());
  f.shell->install(f.screen, nullptr); EXPECT_EQ(f.shell->work_mode(f.screen), Mode::Analysis);
  f.shell->forget(other);
}

TEST_F(WorkModeLayouts, ActiveTextAndDeferredOldMenusCannotHideOrCommitInput)
{
  const auto *view = f.screen.ui()->find("view"); ASSERT_NE(view, nullptr);
  const auto label = f.shell->store().tr("app.menu.view.mode_preparation");
  const auto found = std::find_if(view->menu.begin(), view->menu.end(),
      [&](const auto &entry) { return entry.text.find(label) != std::string::npos; });
  ASSERT_NE(found, view->menu.end());
  const auto action = found->action;
  ASSERT_TRUE(action);
  f.tab("a3", kEditorPython); f.screen.set_maximized(&f.area("a3")); f.drv->frame();
  const auto [x, y] = f.widget_center("a3/main/python_source");
  f.drv->click(x, y);
  f.drv->key(wm::Key::Unknown, wm::ModNone, "uncommitted input");
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  const auto typed = f.screen.ui()->edit_state()->text();
  const auto before = f.screen.to_json();
  EXPECT_FALSE(f.shell->switch_work_mode(&f.screen, Mode::Preparation).ok());
  action(); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before); EXPECT_EQ(f.screen.ui()->edit_state()->text(), typed);
  f.drv->key(wm::Key::Esc);
  action(); f.shell->forget(f.screen); f.screen.run_deferred();
  EXPECT_EQ(f.shell->work_mode(f.screen), Mode::Analysis);
  // Live editors borrow AppStore state; destroy them before the shell, keeping the copied action.
  f.screen.clear();
  f.shell.reset(); action();
}

class WorkModeLayoutClicks : public ::testing::TestWithParam<std::tuple<const char *, int>> {};

TEST_P(WorkModeLayoutClicks, TwoClicksSwitchEachModeWithoutRunningOrSending)
{
  const auto [language, scale] = GetParam();
  wmtest::AppFixture fixture{language, float(scale), 1000 * scale, 900 * scale};
  auto *viewer = &fixture.area("a2").editor();
  const auto original = fixture.screen.arrangement();
  const auto click = [&](const std::string &key, int &count) {
    const auto *widget = fixture.screen.ui()->find(key); ASSERT_NE(widget, nullptr);
    ASSERT_TRUE(widget->enabled);
    EXPECT_GE(widget->rect.x, 0); EXPECT_LE(widget->rect.x1(), 1000 * scale);
    const auto [x, y] = fixture.widget_center(key);
    ++count; ASSERT_TRUE(fixture.drv->click(x, y));
    fixture.screen.run_deferred(); fixture.drv->frame();
  };
  int clicks = 0;
  for (const auto mode : {Mode::Preparation, Mode::Analysis}) {
    ASSERT_NO_FATAL_FAILURE(click("view", clicks));
    const auto label = fixture.shell->store().tr(mode == Mode::Preparation ?
        "app.menu.view.mode_preparation" : "app.menu.view.mode_analysis");
    std::string target;
    for (const auto &block : fixture.screen.ui()->blocks()) {
      for (const auto &widget : block->widgets()) {
        if (widget.type == ui::WidgetType::MenuItem && widget.text.find(label) != std::string::npos) { target = widget.key; }
      }
    }
    ASSERT_FALSE(target.empty()); ASSERT_NO_FATAL_FAILURE(click(target, clicks));
    EXPECT_EQ(fixture.shell->work_mode(fixture.screen), mode);
    EXPECT_EQ(&fixture.area("a2").editor(), viewer);
    EXPECT_EQ(fixture.screen.maximized(), nullptr);
    EXPECT_EQ(fixture.shell->store().viewer().evaluations_started(), 0);
    EXPECT_TRUE(fixture.shell->store().scripts().session().empty());
  }
  EXPECT_EQ(clicks, 4); RecordProperty("clicks_per_mode", 2);
  EXPECT_EQ(fixture.screen.arrangement(), original);
}

INSTANTIATE_TEST_SUITE_P(LanguagesAndScale, WorkModeLayoutClicks,
    ::testing::Combine(::testing::Values("en", "zh_CN"), ::testing::Values(1, 2)));
}  // namespace
}  // namespace stk::app
