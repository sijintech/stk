/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/app_store.hh"
#include "stk/app/project_file_tree.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
namespace fs = std::filesystem;
using io::Json;
class ProjectFileTreePython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"project-file-tree"};
  bridge::test::ManualLoop loop;
  AppStore store;
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectFileTree> tree;
  ProjectState &project() { return store.project(); }
  void idle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  void loaded(ProjectFileTree &view)
  {
    ASSERT_TRUE(loop.pump_until([&] { return !view.busy(); }, 30));
    ASSERT_TRUE(view.error().empty()) << view.error();
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    bridge::ClientOptions options; options.python.configured = python; options.executor = loop.executor();
    options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json"; options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    store.set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "File tree"));
    ASSERT_NO_FATAL_FAILURE(idle()); ASSERT_TRUE(project().loaded());
    fs::create_directories(directory.path() / "project" / "inputs");
    std::ofstream(directory.path() / "project" / "inputs" / "case.py") << "raise AssertionError('must not run')\n";
    std::ofstream(directory.path() / "project" / "field.npy") << "synthetic metadata-only fixture\n";
    tree = std::make_unique<ProjectFileTree>(store); tree->sync(); ASSERT_TRUE(tree->supported());
  }
  void TearDown() override
  {
    tree.reset();
    EXPECT_EQ(store.viewer().evaluations_started(), 0);
    project().attach(nullptr); store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(ProjectFileTreePython, ListsActualChildrenLazilyWithoutRegisteringOrChangingSelection)
{
  const auto table = project().table_id(), record = project().record_id();
  ASSERT_TRUE(tree->refresh()); ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  ASSERT_EQ(tree->pages().size(), 1u);
  const auto &entries = tree->pages().at("").at("entries");
  ASSERT_EQ(entries.size(), 2u); EXPECT_EQ(entries.at(0).at("path"), "inputs");
  EXPECT_FALSE(entries.at(1).at("registered").get<bool>());
  ASSERT_TRUE(tree->toggle("inputs")); ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  ASSERT_EQ(tree->pages().size(), 2u);
  EXPECT_EQ(tree->pages().at("inputs").at("entries").at(0).at("path"), "inputs/case.py");
  EXPECT_EQ(project().project()->revision, 0); EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().record_id(), record);
}

TEST_F(ProjectFileTreePython, RegisteredSearchTargetsAndExplicitResolutionKeepSharedSelection)
{
  ASSERT_TRUE(project().index_files({core::path_to_utf8(directory.path() / "project" / "inputs" / "case.py")}));
  ASSERT_NO_FATAL_FAILURE(idle());
  const auto table = project().table_id(), record = project().record_id();
  tree->sync(); ASSERT_TRUE(tree->refresh()); ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  ASSERT_TRUE(tree->select_record(record));
  EXPECT_EQ(tree->selected().at("path"), "inputs/case.py");
  EXPECT_EQ(tree->selected().at("location"), "project");
  std::string resolved;
  ASSERT_TRUE(tree->resolve([&](const std::string &path) { resolved = path; }));
  ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  EXPECT_EQ(resolved, core::path_to_utf8(directory.path() / "project" / "inputs" / "case.py"));
  EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().record_id(), record);
}

TEST_F(ProjectFileTreePython, InstancesAreIndependentAndClosingOrDestroyingDropsPendingReplies)
{
  ProjectFileTree other(store); other.sync();
  ASSERT_TRUE(tree->refresh()); ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  ASSERT_TRUE(other.refresh()); ASSERT_NO_FATAL_FAILURE(loaded(other));
  ASSERT_TRUE(tree->toggle("inputs")); ASSERT_NO_FATAL_FAILURE(loaded(*tree));
  EXPECT_TRUE(tree->expanded("inputs")); EXPECT_FALSE(other.expanded("inputs"));
  ASSERT_TRUE(other.refresh());
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(idle());
  other.sync(); EXPECT_FALSE(other.loaded()); EXPECT_FALSE(other.supported());
  tree.reset(); loop.run_ready();  // A retained completion cannot access a destroyed controller.
}

TEST_F(ProjectFileTreePython, CodeActionReusesRightEditorAndRejectsHiddenOriginWithoutRunning)
{
  wmtest::AppFixture f{"en", 1, 1440, 1000};
  auto &app = f.shell->store();
  app.set_bridge(client.get());
  auto &visible = app.project();
  visible.sync();
  ASSERT_TRUE(visible.open(directory.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return !visible.busy() && visible.loaded(); }, 30));
  const auto table = visible.table_id(), record = visible.record_id();
  auto frame = [&] { f.screen.run_deferred(); f.drv->frame(); };
  auto row_named = [&](const std::string &name) {
    const auto *widget = f.screen.ui()->find("files_tree");
    if (widget && widget->table) {
      for (int row = 0; row < widget->table->rows; ++row) {
        if (widget->table->cell(row, 0).find(name) != std::string::npos) { return row; }
      }
    }
    return -1;
  };
  ASSERT_TRUE(loop.pump_until([&] { frame(); return row_named("inputs") >= 0; }, 30));
  f.screen.ui()->find("files_tree")->table->selected.assign(row_named("inputs"));
  frame();
  const auto *expand = f.screen.ui()->find("files_toggle");
  ASSERT_NE(expand, nullptr); ASSERT_TRUE(expand->enabled); expand->on_click();
  ASSERT_TRUE(loop.pump_until([&] { frame(); return row_named("case.py") >= 0; }, 30));
  f.screen.ui()->find("files_tree")->table->selected.assign(row_named("case.py"));
  frame();
  const auto *open = f.screen.ui()->find("files_open_code");
  ASSERT_NE(open, nullptr); ASSERT_TRUE(open->enabled);
  const auto old_action = open->on_click;
  auto &right = f.area("a3");
  const int right_tabs = right.tab_count();
  const auto viewer_payload = app.viewer().payload();

  f.tab("a1", kEditorWorkspace);
  old_action(); f.screen.run_deferred(); loop.run_ready(); frame();
  EXPECT_EQ(right.editor().type().id, kEditorAnalysisGraph);
  f.tab("a1", kEditorFiles); frame();
  open = f.screen.ui()->find("files_open_code");
  ASSERT_NE(open, nullptr); ASSERT_TRUE(open->enabled); open->on_click();
  const auto path = core::path_to_utf8(directory.path() / "project" / "inputs" / "case.py");
  ASSERT_TRUE(loop.pump_until([&] {
    frame();
    return right.editor().type().id == kEditorPython && right.editor().save_state().value("source_path", "") == path;
  }, 30));
  EXPECT_EQ(right.tab_count(), right_tabs);
  EXPECT_EQ(right.editor().save_state().at("source"), "raise AssertionError('must not run')\n");
  EXPECT_EQ(f.area("a1").editor().type().id, kEditorFiles);
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
  EXPECT_EQ(app.viewer().payload(), viewer_payload);
  EXPECT_EQ(app.viewer().evaluations_started(), 0);
  EXPECT_EQ(visible.project()->revision, 0);
  EXPECT_EQ(visible.table_id(), table); EXPECT_EQ(visible.record_id(), record);
  EXPECT_TRUE(app.scripts().status().at("run").is_null());
  EXPECT_TRUE(app.scripts().history().empty());
  EXPECT_EQ(f.screen.maximized(), nullptr);
  app.set_bridge(nullptr); loop.run_ready();
}
}  // namespace
}  // namespace stk::app
