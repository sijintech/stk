/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/viewer_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/io/payload.hh"
#include "../wm/support.hh"
#include <algorithm>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;

class WorkbenchModules : public ::testing::Test {
 protected:
  wmtest::AppFixture f{"en", 1, 1600, 1100};
  EditorArea *active(const char *id)
  {
    for (auto *base : f.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base);
      if (area && area->editor().type().id == id) { return area; }
    }
    return nullptr;
  }
  void click(const char *key)
  {
    const auto *w = f.screen.ui()->find(key); ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_FALSE(w->clip.intersect(w->rect).empty()) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y));
    f.screen.run_deferred(); f.drv->frame();
  }
  std::vector<Editor *> instances()
  {
    std::vector<Editor *> result;
    // Area IDs stay with the live objects when their screen positions are swapped.
    for (const auto *id : {"a1", "a2", "a3", "a4"}) {
      auto &area = f.area(id);
      for (int i = 0; i < area.tab_count(); ++i) { result.push_back(&area.tab(i)); }
    }
    return result;
  }
};

TEST_F(WorkbenchModules, DefaultFourModulesAreVisibleWithoutNavigation)
{
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.areas().size(), 4u);
  std::vector<wm::Rect> rectangles;
  for (const auto *id : {kEditorViewer, kEditorFiles, kEditorAnalysisGraph, kEditorTable}) {
    auto *area = active(id); ASSERT_NE(area, nullptr) << id;
    EXPECT_GT(area->rect().width(), 0) << id;
    EXPECT_GT(area->rect().height(), 0) << id;
    rectangles.push_back(area->rect());
    const auto *main = area->find_region("main"); ASSERT_NE(main, nullptr);
    EXPECT_TRUE(main->visible()) << id;
    EXPECT_GT(main->rect().width(), 0) << id;
    EXPECT_GT(main->rect().height(), 0) << id;
    const auto [x, y] = wmtest::AppFixture::center(main->rect());
    f.drv->click(x, y);
    EXPECT_EQ(area->editor().type().id, id) << "clicking a visible pane does not navigate or replace it";
  }
  for (size_t i = 0; i < rectangles.size(); ++i) {
    for (size_t j = 0; j < i; ++j) {
      const auto &a = rectangles[i], &b = rectangles[j];
      EXPECT_TRUE(a.xmax <= b.xmin || b.xmax <= a.xmin || a.ymax <= b.ymin || b.ymax <= a.ymin);
    }
  }
  for (const auto *key : {"tool_files", "tool_analysis_graph", "tool_table", "tool_python", "tool_swap"}) {
    const auto *w = f.screen.ui()->find(key); ASSERT_NE(w, nullptr);
    EXPECT_TRUE(w->enabled) << key;
    EXPECT_GE(w->rect.x, 0) << key;
    EXPECT_LE(w->rect.x1(), 1600) << key;
  }
  EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
}

TEST_F(WorkbenchModules, OneClickToolsKeepTheViewerAndDoubleSwapRestoresTheLiveTree)
{
  auto *viewer_area = active(kEditorViewer); ASSERT_NE(viewer_area, nullptr);
  Editor *viewer_editor = &viewer_area->editor();
  auto &viewer = f.shell->store().viewer();
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  viewer.open_payload(payload, "Existing synthetic test payload");
  viewer.set_overlays(false);
  f.drv->frame();
  const auto base = viewer.base_payload(), shown = viewer.payload();
  const auto payload_serial = viewer.payload_serial(), camera_serial = viewer.camera_serial();
  const auto label = viewer.source_label();
  const auto original = f.screen.to_json();
  const auto editors = instances();
  auto *nodes = active(kEditorAnalysisGraph); ASSERT_NE(nodes, nullptr);
  Editor *nodes_editor = &nodes->editor();
  click("tool_python");
  EXPECT_EQ(f.screen.maximized(), nullptr);
  ASSERT_NE(active(kEditorPython), nullptr);
  EXPECT_EQ(&viewer_area->editor(), viewer_editor);
  EXPECT_EQ(active(kEditorViewer), viewer_area);
  EXPECT_EQ(viewer.base_payload(), base);
  EXPECT_EQ(viewer.payload(), shown);
  EXPECT_EQ(viewer.payload_serial(), payload_serial);
  EXPECT_EQ(viewer.camera_serial(), camera_serial);
  EXPECT_EQ(viewer.source_label(), label);
  EXPECT_FALSE(viewer.overlays());
  click("tool_analysis_graph");
  EXPECT_EQ(active(kEditorAnalysisGraph), nodes);
  EXPECT_EQ(&nodes->editor(), nodes_editor);
  EXPECT_EQ(f.screen.to_json(), original);
  const auto viewer_rect = viewer_area->rect(), nodes_rect = nodes->rect();
  click("tool_swap");
  EXPECT_EQ(viewer_area->rect(), nodes_rect);
  EXPECT_EQ(nodes->rect(), viewer_rect);
  EXPECT_EQ(&viewer_area->editor(), viewer_editor);
  EXPECT_EQ(&nodes->editor(), nodes_editor);
  EXPECT_EQ(instances(), editors);
  click("tool_swap");
  EXPECT_EQ(f.screen.to_json(), original);
  EXPECT_EQ(instances(), editors);
  EXPECT_EQ(viewer.base_payload(), base);
  EXPECT_EQ(viewer.payload(), shown);
  EXPECT_EQ(viewer.payload_serial(), payload_serial);
  EXPECT_EQ(viewer.camera_serial(), camera_serial);
  EXPECT_FALSE(viewer.overlays());
  EXPECT_EQ(viewer.evaluations_started(), 0);
}

TEST_F(WorkbenchModules, OldSingleViewerLayoutRollsBackFailedFactoriesWithoutReplacingViewer)
{
  auto &only = f.screen.set_root(std::make_unique<EditorArea>(*f.shell, kEditorViewer));
  f.drv->frame();
  auto *area = dynamic_cast<EditorArea *>(&only); ASSERT_NE(area, nullptr);
  Editor *viewer = &area->editor();
  const auto before = f.screen.to_json();
  const auto region = area->find_region("main");
  f.screen.set_focus(region);
  f.shell->registry().add({"workbench-null", "editor.python.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { return nullptr; }});
  f.shell->registry().add({"workbench-throw", "editor.python.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { throw std::runtime_error("synthetic factory failure"); }});
  for (const auto *id : {"workbench-null", "workbench-throw"}) {
    const auto result = f.shell->activate_editor(&f.screen, id, false);
    ASSERT_FALSE(result.ok());
    EXPECT_EQ(result.error().code, bridge::ErrorCode::Unavailable);
    f.drv->frame();
    EXPECT_EQ(f.screen.to_json(), before);
    ASSERT_EQ(f.screen.areas().size(), 1u);
    EXPECT_EQ(f.screen.areas().front(), area);
    EXPECT_EQ(&area->editor(), viewer);
    EXPECT_EQ(f.screen.focused_region(), region);
  }
  const auto success = f.shell->activate_editor(&f.screen, kEditorPython, false);
  ASSERT_TRUE(success.ok()); f.drv->frame();
  EXPECT_EQ(f.screen.areas().size(), 2u);
  EXPECT_EQ(&area->editor(), viewer);
  EXPECT_NE(active(kEditorPython), nullptr);
  EXPECT_NE(active(kEditorViewer), nullptr);
  EXPECT_EQ(f.screen.maximized(), nullptr);
}

TEST_F(WorkbenchModules, HiddenLegacyDraftMovesToExistingEditingAreaWithoutReplacingViewer)
{
  auto &viewer_area = f.area("a2");
  Editor *viewer_editor = &viewer_area.editor();
  ASSERT_TRUE(viewer_area.add_tab(kEditorPython, false));
  Editor *draft = &viewer_area.tab(viewer_area.tab_count() - 1);
  ASSERT_TRUE(draft->load_state({{"source", "print('unsaved legacy draft')\n"}, {"baseline", ""}}));
  ASSERT_TRUE(draft->has_unsaved_changes());
  auto &right = f.area("a3");
  const int right_tabs = right.tab_count();
  f.drv->frame();
  click("tool_python");
  EXPECT_EQ(&viewer_area.editor(), viewer_editor);
  EXPECT_EQ(viewer_area.tab_count(), 1);
  EXPECT_EQ(&right.editor(), draft);
  EXPECT_EQ(right.tab_count(), right_tabs + 1);
  EXPECT_EQ(draft->save_state().at("source"), "print('unsaved legacy draft')\n");
  EXPECT_TRUE(draft->has_unsaved_changes());
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
  EXPECT_TRUE(f.shell->store().scripts().history().empty());
}

TEST_F(WorkbenchModules, MaximizedLegacyViewerRevealsItsExistingDraftWithoutCloningIt)
{
  auto *viewer_area = dynamic_cast<EditorArea *>(&f.screen.set_root(std::make_unique<EditorArea>(*f.shell, kEditorViewer)));
  ASSERT_NE(viewer_area, nullptr);
  Editor *viewer_editor = &viewer_area->editor();
  ASSERT_TRUE(viewer_area->add_tab(kEditorPython, false));
  Editor *draft = &viewer_area->tab(1);
  ASSERT_TRUE(draft->load_state({{"source", "print('keep this exact instance')\n"}, {"baseline", ""}}));
  auto &viewer = f.shell->store().viewer();
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  viewer.open_payload(payload, "Existing synthetic legacy result");
  viewer.set_overlays(false);
  f.screen.set_maximized(viewer_area);
  f.drv->frame();
  const auto shown = viewer.payload();
  const auto camera = viewer.camera_serial(), serial = viewer.payload_serial();
  click("tool_python");
  ASSERT_EQ(f.screen.areas().size(), 2u);
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(&viewer_area->editor(), viewer_editor);
  EXPECT_EQ(viewer_area->tab_count(), 1);
  auto *editing = active(kEditorPython); ASSERT_NE(editing, nullptr);
  EXPECT_EQ(&editing->editor(), draft);
  EXPECT_EQ(editing->tab_count(), 1) << "the temporary split must not clone or retain another draft";
  EXPECT_EQ(draft->save_state().at("source"), "print('keep this exact instance')\n");
  EXPECT_TRUE(draft->has_unsaved_changes());
  EXPECT_EQ(viewer.payload(), shown);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(viewer.payload_serial(), serial);
  EXPECT_FALSE(viewer.overlays());
  EXPECT_EQ(viewer.evaluations_started(), 0);
}

TEST_F(WorkbenchModules, FailedOrdinaryNavigationRestoresTheMaximizedLegacyViewer)
{
  auto *viewer_area = dynamic_cast<EditorArea *>(&f.screen.set_root(std::make_unique<EditorArea>(*f.shell, kEditorViewer)));
  ASSERT_NE(viewer_area, nullptr);
  Editor *viewer_editor = &viewer_area->editor();
  f.screen.set_maximized(viewer_area);
  f.drv->frame();
  const auto before = f.screen.to_json();
  f.shell->registry().add({"workbench-null-max", "editor.python.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { return nullptr; }});
  f.shell->registry().add({"workbench-throw-max", "editor.python.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { throw std::runtime_error("synthetic factory failure"); }});
  for (const auto *id : {"workbench-null-max", "workbench-throw-max"}) {
    const auto result = f.shell->activate_editor(&f.screen, id, false);
    ASSERT_FALSE(result.ok());
    EXPECT_EQ(result.error().code, bridge::ErrorCode::Unavailable);
    f.drv->frame();
    EXPECT_EQ(f.screen.to_json(), before);
    EXPECT_EQ(f.screen.maximized(), viewer_area);
    EXPECT_EQ(&viewer_area->editor(), viewer_editor);
  }
  click("tool_python");
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.areas().size(), 2u);
  EXPECT_EQ(&viewer_area->editor(), viewer_editor);
  EXPECT_NE(active(kEditorPython), nullptr);
}

TEST_F(WorkbenchModules, RetainedToolbarCallbacksAreInertAfterScreenForgetAndShellDestruction)
{
  std::vector<std::function<void()>> callbacks;
  for (const auto *key : {"tool_files", "tool_analysis_graph", "tool_table", "tool_python", "tool_swap"}) {
    const auto *w = f.screen.ui()->find(key); ASSERT_NE(w, nullptr); ASSERT_TRUE(w->on_click);
    callbacks.push_back(w->on_click);
  }
  const auto before = f.screen.to_json();
  callbacks.back()();  // Forget also invalidates an action already queued on this screen.
  f.shell->forget(f.screen);
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
  for (const auto &callback : callbacks) { callback(); }
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
  // Destroy live editors while their shared AppStore still exists. Copied callbacks outlive both.
  f.screen.clear();
  f.shell.reset();
  for (const auto &callback : callbacks) { callback(); }
  f.screen.run_deferred();
}

TEST(WorkbenchModulesClicks, OldSingleViewerMenuNeedsTwoClicksAndToolbarOneForTheSameResult)
{
  wmtest::AppFixture menu{"en", 1, 1600, 1100}, toolbar{"en", 1, 1600, 1100};
  for (auto *fixture : {&menu, &toolbar}) {
    fixture->screen.set_root(std::make_unique<EditorArea>(*fixture->shell, kEditorViewer));
    fixture->drv->frame();
  }
  ASSERT_EQ(menu.screen.to_json(), toolbar.screen.to_json()) << "fixed legacy one-Viewer starting layout";
  const auto menu_history = menu.shell->store().scripts().history();
  const auto toolbar_history = toolbar.shell->store().scripts().history();
  int menu_clicks = 0, toolbar_clicks = 0;
  const auto click = [](wmtest::AppFixture &fixture, const std::string &key, int &count) {
    const auto *w = fixture.screen.ui()->find(key); ASSERT_NE(w, nullptr); ASSERT_TRUE(w->enabled);
    const auto [x, y] = fixture.widget_center(key);
    ++count;
    ASSERT_TRUE(fixture.drv->click(x, y));
    fixture.screen.run_deferred(); fixture.drv->frame();
  };
  ASSERT_NO_FATAL_FAILURE(click(menu, "file", menu_clicks));
  std::string python_item;
  for (const auto &block : menu.screen.ui()->blocks()) {
    for (const auto &w : block->widgets()) {
      if (w.type == ui::WidgetType::MenuItem && w.text == menu.shell->store().tr("editor.python.title")) { python_item = w.key; }
    }
  }
  ASSERT_FALSE(python_item.empty());
  ASSERT_NO_FATAL_FAILURE(click(menu, python_item, menu_clicks));
  ASSERT_NO_FATAL_FAILURE(click(toolbar, "tool_python", toolbar_clicks));
  EXPECT_EQ(menu_clicks, 2);
  EXPECT_EQ(toolbar_clicks, 1);
  RecordProperty("legacy_file_menu_clicks", menu_clicks);
  RecordProperty("direct_toolbar_clicks", toolbar_clicks);
  EXPECT_EQ(menu.screen.to_json(), toolbar.screen.to_json());
  for (auto *fixture : {&menu, &toolbar}) {
    int viewers = 0, programs = 0;
    for (auto *base : fixture->screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base); ASSERT_NE(area, nullptr);
      viewers += area->editor().type().id == kEditorViewer;
      programs += area->editor().type().id == kEditorPython;
    }
    EXPECT_EQ(viewers, 1); EXPECT_EQ(programs, 1);
    EXPECT_EQ(fixture->screen.maximized(), nullptr);
    EXPECT_EQ(fixture->shell->store().viewer().evaluations_started(), 0);
    EXPECT_TRUE(fixture->shell->store().scripts().session().empty());
  }
  EXPECT_EQ(menu.shell->store().scripts().history(), menu_history);
  EXPECT_EQ(toolbar.shell->store().scripts().history(), toolbar_history);
}

TEST_F(WorkbenchModules, RetainedAreaMenusRefuseRebuiltOwnersAndQueuedLayoutReplacement)
{
  const auto actions = [&] {
    const auto menu = f.area("a3").area_menu(&f.drv->ctx);
    std::vector<std::function<void()>> callbacks;
    for (const auto *key : {"area.menu.close_tab", "area.menu.join_prev", "area.menu.new_tab"}) {
      const auto label = f.shell->store().tr(key);
      const auto item = std::find_if(menu.begin(), menu.end(), [&](const auto &entry) { return entry.text == label; });
      EXPECT_NE(item, menu.end()) << key;
      if (item != menu.end()) { EXPECT_TRUE(item->enabled) << key; callbacks.push_back(item->action); }
    }
    return callbacks;
  };
  const auto destroyed_owner = actions(); ASSERT_EQ(destroyed_owner.size(), 3u);
  f.shell->build_default_layout(f.screen); f.drv->frame();
  const auto expected = f.screen.to_json();
  for (const auto &action : destroyed_owner) { action(); }
  f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.to_json(), expected);
  const auto queued_owner = actions(); ASSERT_EQ(queued_owner.size(), 3u);
  f.screen.defer([&] { f.shell->build_default_layout(f.screen); });
  for (const auto &action : queued_owner) { action(); }
  f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.to_json(), expected);
}

class CloseGuardEditor final : public Editor {
 public:
  CloseGuardEditor(const EditorType &type, std::shared_ptr<bool> dirty) : Editor(type), dirty_(std::move(dirty)) {}
  void draw_main(ui::Layout &, EditorContext &) override {}
  bool has_unsaved_changes() const override { return *dirty_; }
 private:
  std::shared_ptr<bool> dirty_;
};

TEST_F(WorkbenchModules, SecondaryScreenCloseChecksItsHiddenDirtyTabs)
{
  const auto dirty = std::make_shared<bool>(true);
  f.shell->registry().add({"workbench-dirty", "editor.table.title", [dirty](const EditorType &type) {
    return std::make_unique<CloseGuardEditor>(type, dirty);
  }});
  wm::Screen secondary;
  f.shell->install(secondary, nullptr); f.shell->build_default_layout(secondary);
  struct Forget { AppShell &shell; wm::Screen &screen; ~Forget() { shell.forget(screen); } } forget{*f.shell, secondary};
  wmtest::ScreenDriver driver(secondary, 1280, 900, 1);
  driver.frame();
  auto *area = dynamic_cast<EditorArea *>(secondary.find_area("a3")); ASSERT_NE(area, nullptr);
  const int active_tab = area->active_tab();
  ASSERT_TRUE(area->add_tab("workbench-dirty", false));
  EXPECT_EQ(area->active_tab(), active_tab);
  EXPECT_FALSE(area->editor().has_unsaved_changes());
  EXPECT_TRUE(area->tab(area->tab_count() - 1).has_unsaved_changes());
  EXPECT_TRUE(f.shell->has_unsaved_changes());
  EXPECT_FALSE(f.shell->can_close_screen(&secondary));
  EXPECT_TRUE(f.shell->can_close_screen(&f.screen));
  *dirty = false;
  EXPECT_TRUE(f.shell->can_close_screen(&secondary));
  f.shell->forget(secondary);
  EXPECT_TRUE(f.shell->can_close_screen(&secondary));
}
TEST(WorkbenchModulesClicks, NarrowAndScaledToolButtonsRemainOneClick)
{
  for (const auto *language : {"en", "zh"}) {
    for (const float scale : {1.0f, 1.5f, 2.0f}) {
      SCOPED_TRACE(std::string(language) + " scale=" + std::to_string(scale));
      wmtest::AppFixture f{language, scale, int(900 * scale), int(1000 * scale)};
      auto &viewer = f.area("a2");
      auto *instance = &viewer.editor();
      for (const auto *key : {"tool_python", "tool_analysis_graph", "tool_files", "tool_table", "tool_swap"}) {
        const auto *button = f.screen.ui()->find(key); ASSERT_NE(button, nullptr);
        ASSERT_TRUE(button->enabled);
        EXPECT_GE(button->rect.x, button->clip.x);
        EXPECT_LE(button->rect.x1(), button->clip.x1());
      }
      const auto [x, y] = f.widget_center("tool_python");
      ASSERT_TRUE(f.drv->click(x, y)); f.screen.run_deferred(); f.drv->frame();
      EXPECT_EQ(f.area("a3").editor().type().id, kEditorPython);
      EXPECT_EQ(&viewer.editor(), instance); EXPECT_EQ(f.screen.maximized(), nullptr);
      EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
      EXPECT_TRUE(f.shell->store().scripts().history().empty());
    }
  }
}

TEST_F(WorkbenchModules, WorkspaceAreaAndTabEnvelopesRejectMissingAndUnknownSettingsAtomically)
{
  auto &area = f.area("a3");
  const auto original = area.save_workspace_state();
  ASSERT_FALSE(area.has_unsaved_changes());
  const auto before = instances();
  auto extra_area = original; extra_area["unknown_setting"] = true;
  auto missing_area = original; missing_area.erase("active");
  auto extra_tab = original; extra_tab["tabs"][0]["unknown_setting"] = true;
  auto missing_tab = original; missing_tab["tabs"][0].erase("state");
  for (const auto &invalid : {extra_area, missing_area, extra_tab, missing_tab}) {
    EXPECT_FALSE(area.load_state(invalid));
    EXPECT_EQ(area.save_workspace_state(), original);
    EXPECT_EQ(instances(), before);
  }
  EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0u);
}

TEST_F(WorkbenchModules, ExplicitWorkspaceHooksRoundTripAllLocalEditorsWithoutViewerEvaluation)
{
  auto &area = f.area("a4");
  for (const auto *type : {kEditorSkills, kEditorWorkspace, kEditorAI, kEditorJobs, kEditorProject,
                          kEditorFiles, kEditorWorkflow, kEditorAnalysisGraph}) {
    ASSERT_TRUE(area.set_tab_type(area.active_tab(), type)) << type;
    const auto captured = area.editor().save_workspace_state();
    EXPECT_TRUE(captured.is_object()) << type;
    EXPECT_TRUE(area.editor().load_workspace_state(captured)) << type << " " << captured.dump();
    EXPECT_EQ(area.editor().save_workspace_state(), captured) << type;
    EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0) << type;
  }
}

TEST_F(WorkbenchModules, WorkspaceKeepsLocalSearchAndUnsentAITextButRefusesHostConfiguration)
{
  auto &area = f.area("a4");
  ASSERT_TRUE(area.set_tab_type(area.active_tab(), kEditorSkills));
  ASSERT_TRUE(area.editor().load_workspace_state({{"version", 1}, {"query", "LAMMPS"}}));
  EXPECT_EQ(area.editor().save_workspace_state().at("query"), "LAMMPS");
  EXPECT_FALSE(area.editor().load_workspace_state({{"version", 1}, {"query", 12}}));
  ASSERT_TRUE(area.set_tab_type(area.active_tab(), kEditorAI));
  const Json saved = {{"version", 1}, {"drafts", Json::array({{{"project", "11111111-1111-4111-8111-111111111111"},
    {"text", "Unsent scientific question"}, {"agent_text", "Unsent local task"}, {"intent", 0}}})}};
  ASSERT_TRUE(area.editor().load_workspace_state(saved)); EXPECT_EQ(area.editor().save_workspace_state(), saved);
  auto invalid = saved; invalid["endpoint"] = "must-not-restore";
  EXPECT_FALSE(area.editor().load_workspace_state(invalid)); EXPECT_EQ(area.editor().save_workspace_state(), saved);
  EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
}

TEST_F(WorkbenchModules, WorkspaceRetainsDiscussionDraftAndReviewParametersWithoutSendingOrApplying)
{
  auto &area = f.area("a4"); ASSERT_TRUE(area.set_tab_type(area.active_tab(), kEditorProject));
  auto saved = area.editor().save_workspace_state();
  saved["project_id"] = "11111111-1111-4111-8111-111111111111";
  saved["review_source"] = "[{\"op\":\"create_table\",\"name\":\"Explicit apply only\"}]";
  saved["discussion"]["project"] = saved["project_id"];
  saved["discussion"]["title"] = "Unsent selection"; saved["discussion"]["text"] = "Unsent scientific note";
  saved["discussion"]["category"] = 2; saved["discussion"]["rows"] = {"22222222-2222-4222-8222-222222222222"};
  saved["review"]["project"] = saved["project_id"]; saved["review"]["draft_title"] = "Unsaved review title";
  saved["review"]["selected"] = 3; saved["review"]["category"] = 1;
  ASSERT_TRUE(area.editor().load_workspace_state(saved)); EXPECT_EQ(area.editor().save_workspace_state(), saved);
  auto invalid = saved; invalid["discussion"]["rows"] = {123};
  EXPECT_FALSE(area.editor().load_workspace_state(invalid)); EXPECT_EQ(area.editor().save_workspace_state(), saved);
  EXPECT_FALSE(f.shell->store().project().project()); EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
}

}  // namespace
}  // namespace stk::app
