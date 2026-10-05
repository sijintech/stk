/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;

TEST(WorkspaceNavigation, EmptyWorkspaceHasOnlyProjectManagementAndSurvivesShellClosure)
{
  wmtest::AppFixture f;
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorWorkspace));
  f.screen.set_maximized(&area); f.drv->frame();
  for (const auto *page : {"conversation", "files", "workflows", "analysis_runs", "simulation_runs", "data"}) {
    const auto *w = f.screen.ui()->find(std::string("workspace_") + page);
    ASSERT_NE(w, nullptr); EXPECT_FALSE(w->enabled);
  }
  auto action = f.screen.ui()->find("workspace_project")->on_click;
  action(); f.screen.run_deferred(); f.drv->frame();
  auto *target = dynamic_cast<EditorArea *>(f.screen.maximized()); ASSERT_NE(target, nullptr);
  EXPECT_EQ(target->editor().type().id, kEditorProject);
  EXPECT_NE(f.screen.ui()->find("project_location/directory"), nullptr);
  auto back = f.screen.ui()->find("project_workspace")->on_click;
  back(); f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), &area);
  action = f.screen.ui()->find("workspace_project")->on_click;
  f.shell.reset();
  action(); back(); // Screens may outlive the shell in headless integrations.
}

class WorkspaceNavigationPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"workspace-navigation"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;
  ProjectState &project() { return f.shell->store().project(); }
  EditorArea &home() { return f.area("a1"); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  std::string handle() { return project().project()->handle; }
  void idle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(project().error().empty()) << project().error();
    f.drv->frame();
  }
  void go(const char *page)
  {
    f.shell->open_project_page_later(&f.screen, page, handle());
    f.screen.run_deferred(); f.drv->frame();
  }
  EditorArea &destination() { return *dynamic_cast<EditorArea *>(f.screen.maximized()); }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    f.shell->store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(dir.str() + "/project", "Workspace navigation"));
    ASSERT_NO_FATAL_FAILURE(idle()); ASSERT_TRUE(project().loaded());
    ASSERT_TRUE(home().set_tab_type(0, kEditorWorkspace));
    ASSERT_TRUE(f.area("a2").add_tab(kEditorProject));
    ASSERT_TRUE(f.area("a3").add_tab(kEditorAI));
    ASSERT_TRUE(f.area("a4").add_tab(kEditorAnalysisGraph));
    f.screen.set_maximized(&home()); f.drv->frame();
  }
  void TearDown() override
  {
    EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
    EXPECT_FALSE(f.shell->store().viewer().payload());
    project().attach(nullptr); f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(WorkspaceNavigationPython, VisibleButtonsReuseEditorsAndRevealFilesAndBothRunHistories)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(viewer.open_path(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  const auto payload = viewer.payload(); ASSERT_TRUE(payload);
  const auto source = viewer.source().key();
  const auto camera = viewer.camera_serial();
  const auto revision = project().project()->revision;
  auto *tables = &f.area("a2").editor(), *ai = &f.area("a3").editor(), *graph = &f.area("a4").editor();
  const int n2 = f.area("a2").tab_count(), n3 = f.area("a3").tab_count(), n4 = f.area("a4").tab_count();
  const auto click = [&](const char *page) {
    const auto key = std::string("workspace_") + page;
    ASSERT_NE(widget(key), nullptr); ASSERT_TRUE(widget(key)->enabled);
    const auto [x, y] = f.widget_center(key); f.drv->click(x, y); f.screen.run_deferred(); f.drv->frame();
  };
  ASSERT_NO_FATAL_FAILURE(click("files"));
  EXPECT_EQ(&destination().editor(), tables); EXPECT_NE(widget("project_files/paths"), nullptr);
  EXPECT_EQ(widget("project_view"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("simulation_runs"));
  EXPECT_EQ(&destination().editor(), tables); EXPECT_NE(widget("project_runs/list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("analysis_runs"));
  EXPECT_EQ(&destination().editor(), graph); ASSERT_NE(widget("analysis_saved_section"), nullptr);
  EXPECT_EQ(widget("analysis_saved_section")->index.value(), 1); EXPECT_NE(widget("analysis_run_list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("workflows"));
  EXPECT_EQ(&destination().editor(), graph); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  EXPECT_EQ(widget("analysis_saved_section")->index.value(), 0); EXPECT_NE(widget("analysis_list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("conversation"));
  EXPECT_EQ(&destination().editor(), ai);
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(f.area("a2").tab_count(), n2); EXPECT_EQ(f.area("a3").tab_count(), n3); EXPECT_EQ(f.area("a4").tab_count(), n4);
  EXPECT_EQ(viewer.payload(), payload); EXPECT_EQ(viewer.source().key(), source);
  EXPECT_EQ(viewer.camera_serial(), camera); EXPECT_EQ(viewer.evaluations_started(), 0);
  viewer.close();
}

TEST_F(WorkspaceNavigationPython, FilesSelectsExistingIndexWithoutEditingIt)
{
  { std::ofstream file(dir.path() / "input.txt"); file << "input fixture"; }
  ASSERT_TRUE(project().index_files({core::path_to_utf8(dir.path() / "input.txt")}));
  ASSERT_NO_FATAL_FAILURE(idle());
  const auto revision = project().project()->revision;
  const auto table = io::get_string(project().file_index(), "table_id"); ASSERT_FALSE(table.empty());
  const auto snapshot = project().tables();
  go("files");
  EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget(table + "/records"), nullptr); EXPECT_EQ(widget(table + "/records")->table->rows, 1);
  EXPECT_EQ(project().tables().size(), snapshot.size());
}

TEST_F(WorkspaceNavigationPython, OldActionsRefuseProjectSwitchCloseReopenAndDestroyedSource)
{
  auto old = widget("workspace_files")->on_click;
  const auto original = handle();
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().open(dir.str() + "/project")); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_NE(handle(), original);
  const auto layout = f.screen.to_json(); old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), layout);
  old = widget("workspace_files")->on_click;
  ASSERT_TRUE(project().create(dir.str() + "/other", "Other project")); ASSERT_NO_FATAL_FAILURE(idle());
  old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), layout);
  old = widget("workspace_files")->on_click;
  ASSERT_TRUE(home().set_tab_type(0, kEditorLogs)); const auto destroyed = f.screen.to_json();
  old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), destroyed);
}

TEST_F(WorkspaceNavigationPython, FilesProtectCellDraftsInHiddenTabsAndOtherWindows)
{
  const std::string table = "aabbccdd-1111-4111-8111-111111111111";
  const std::string field = "aabbccdd-2222-4222-8222-222222222222";
  const std::string record = "aabbccdd-3333-4333-8333-333333333333";
  ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Parameters"}},
      {{"op", "add_field"}, {"id", field}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}},
      {{"op", "add_record"}, {"id", record}, {"table_id", table}},
      {{"op", "set_cell"}, {"table_id", table}, {"record_id", record}, {"field_id", field}, {"value", 300}}
  })));
  ASSERT_NO_FATAL_FAILURE(idle());
  { std::ofstream file(dir.path() / "input.txt"); file << "input fixture"; }
  ASSERT_TRUE(project().index_files({core::path_to_utf8(dir.path() / "input.txt")}));
  ASSERT_NO_FATAL_FAILURE(idle());
  project().select_table(table); project().select_record(record); go("data");
  ASSERT_EQ(project().table_id(), table);
  const auto revision = project().project()->revision;
  ASSERT_NE(widget("cell_value"), nullptr); widget("cell_value")->string.assign("1e"); f.drv->frame();
  ASSERT_FALSE(f.area("a2").editor().can_change_project_selection(project().project()->id));
  go("workspace"); f.area("a2").set_active_tab(0); // Keep the dirty Project editor hidden behind Viewer.

  wm::Screen other; f.shell->install(other, nullptr); f.shell->build_default_layout(other);
  struct ForgetScreen {
    AppShell *shell; wm::Screen *screen;
    ~ForgetScreen() { shell->forget(*screen); }
  } cleanup{f.shell.get(), &other};
  wmtest::ScreenDriver driver(other, 1000, 1000, 1);
  auto *area = dynamic_cast<EditorArea *>(other.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorProject)); other.set_maximized(area); driver.frame();
  const auto *cell = other.ui()->find("cell_value"); ASSERT_NE(cell, nullptr);
  const auto layout = f.screen.to_json(), other_layout = other.to_json();
  ASSERT_EQ(project().table_id(), table);
  ASSERT_FALSE(f.area("a2").tab(1).can_change_project_selection(project().project()->id));
  go("files"); EXPECT_EQ(f.screen.to_json(), layout); EXPECT_EQ(other.to_json(), other_layout);
  EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().record_id(), record);
  cell->string.assign("2e"); driver.frame();
  ASSERT_FALSE(area->editor().can_change_project_selection(project().project()->id));

  go("data"); ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "1e");
  ASSERT_NE(widget("reload_cell"), nullptr); widget("reload_cell")->on_click(); f.drv->frame();
  go("workspace"); const auto first_clean = f.screen.to_json();
  go("files"); EXPECT_EQ(f.screen.to_json(), first_clean); EXPECT_EQ(project().table_id(), table);
  ASSERT_NE(other.ui()->find("cell_value"), nullptr);
  EXPECT_EQ(other.ui()->find("cell_value")->string.value(), "2e");
  ASSERT_NE(other.ui()->find("reload_cell"), nullptr); other.ui()->find("reload_cell")->on_click(); driver.frame();
  go("data");
  ASSERT_NE(widget("manage_objects"), nullptr);
  const auto [x, y] = f.widget_center("manage_objects"); f.drv->click(x, y); f.drv->frame();
  ASSERT_NE(widget("manage_objects/rename_table"), nullptr);
  widget("manage_objects/rename_table")->string.assign("Unsaved table name"); f.drv->frame();
  go("workspace"); const auto names_dirty = f.screen.to_json();
  go("files"); EXPECT_EQ(f.screen.to_json(), names_dirty); EXPECT_EQ(project().table_id(), table);
  go("data"); ASSERT_NE(widget("manage_objects/rename_table"), nullptr);
  EXPECT_EQ(widget("manage_objects/rename_table")->string.value(), "Unsaved table name");
  ASSERT_NE(widget("manage_objects/reload_names"), nullptr); widget("manage_objects/reload_names")->on_click(); f.drv->frame();
  go("files"); EXPECT_EQ(project().table_id(), io::get_string(project().file_index(), "table_id"));
  EXPECT_NE(widget("project_files/paths"), nullptr); EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(WorkspaceNavigationPython, DeferredNavigationRefusesChangedSourceAndClosedScreen)
{
  auto action = widget("workspace_files")->on_click;
  action(); ASSERT_TRUE(home().add_tab(kEditorLogs)); const auto changed = f.screen.to_json();
  f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), changed);
  home().set_active_tab(0); f.drv->frame();
  action = widget("workspace_files")->on_click; action();
  f.shell->forget(f.screen); const auto closed = f.screen.to_json();
  f.screen.run_deferred(); action(); EXPECT_EQ(f.screen.to_json(), closed);
}

TEST_F(WorkspaceNavigationPython, FullTabsDoNotReplaceAnEditorOrChangeSelection)
{
  for (auto *base : f.screen.areas()) {
    auto *area = dynamic_cast<EditorArea *>(base); ASSERT_NE(area, nullptr);
    for (int i = 0; i < area->tab_count(); ++i) {
      if (area->tab(i).type().id == kEditorProject) { ASSERT_TRUE(area->set_tab_type(i, kEditorLogs)); }
    }
    while (area->tab_count() < 16) { ASSERT_TRUE(area->add_tab(kEditorLogs, false)); }
  }
  f.drv->frame(); const auto layout = f.screen.to_json(); const auto selected = project().table_id();
  go("files"); EXPECT_EQ(f.screen.to_json(), layout); EXPECT_EQ(project().table_id(), selected);
}

TEST_F(WorkspaceNavigationPython, AnotherWindowActiveInputPreventsProjectNavigation)
{
  wm::Screen other; f.shell->install(other, nullptr); f.shell->build_default_layout(other);
  struct ForgetScreen {
    AppShell *shell; wm::Screen *screen;
    ~ForgetScreen() { shell->forget(*screen); }
  } cleanup{f.shell.get(), &other};
  wmtest::ScreenDriver driver(other, 1000, 800, 1);
  auto *area = dynamic_cast<EditorArea *>(other.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorPython)); other.set_maximized(area); driver.frame();
  const auto *source = other.ui()->find("python_source"); ASSERT_NE(source, nullptr);
  driver.click(int(source->rect.cx()), other.rect().ymax - 1 - int(source->rect.cy()));
  ASSERT_TRUE(other.ui()->text_input_active());
  const auto text = other.ui()->edit_state()->text(); const auto layout = f.screen.to_json();
  go("files"); EXPECT_EQ(f.screen.to_json(), layout); EXPECT_EQ(other.ui()->edit_state()->text(), text);
  driver.key(wm::Key::Esc); go("files"); EXPECT_EQ(destination().editor().type().id, kEditorProject);
}

TEST_F(WorkspaceNavigationPython, ReturningToConversationKeepsItsUnsentQuestion)
{
  go("conversation");
  const auto key = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(key) != nullptr; }, 30));
  widget(key)->string.assign("Compare these cases without starting a simulation.");
  f.drv->frame(); ASSERT_NE(widget("project_workspace"), nullptr);
  widget("project_workspace")->on_click(); f.screen.run_deferred(); f.drv->frame();
  ASSERT_EQ(destination().editor().type().id, kEditorWorkspace);
  go("conversation");
  ASSERT_NE(widget(key), nullptr);
  EXPECT_EQ(widget(key)->string.value(), "Compare these cases without starting a simulation.");
  EXPECT_EQ(project().project()->revision, 0);
}

}  // namespace
}  // namespace stk::app
