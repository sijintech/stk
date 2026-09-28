/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/core/paths.hh"
#include "stk/app/script_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include "stk/platform/file_dialog.hh"

namespace stk::app {
namespace {

using io::Json;

const std::string table_id = "11111111-1111-4111-8111-111111111111";
const std::string field_id = "22222222-2222-4222-8222-222222222222";
const std::string record_id = "33333333-3333-4333-8333-333333333333";

Json sample_commands()
{
  return Json::array({
      {{"op", "create_table"}, {"id", table_id}, {"name", "Cases"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", field_id},
       {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"table_id", table_id}, {"id", record_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", field_id}, {"value", 300}},
  });
}

Json set_cell(const int value)
{
  return Json::array({{{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id},
                       {"field_id", field_id}, {"value", value}}});
}

TEST(ProjectTable, LiteralTypesPreservePrecisionAndRejectInvalidInput)
{
  std::string error;
  EXPECT_EQ(project_literal("text", "  中文\n", error)->get<std::string>(), "  中文\n");
  EXPECT_EQ(project_literal("text", "", error)->get<std::string>(), "");
  EXPECT_EQ(project_literal("integer", "9223372036854775807", error)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(project_literal("integer", "-9223372036854775808", error)->get<int64_t>(), INT64_MIN);
  EXPECT_FALSE(project_literal("integer", "9223372036854775808", error));
  EXPECT_FALSE(project_literal("integer", "-9223372036854775809", error));
  EXPECT_FALSE(project_literal("integer", "3.0", error));
  EXPECT_FALSE(project_literal("integer", "true", error));
  EXPECT_FALSE(project_literal("number", "true", error));
  EXPECT_FALSE(project_literal("number", "NaN", error));
  EXPECT_FALSE(project_literal("number", "1e999", error));
  EXPECT_FALSE(project_literal("boolean", "1", error));
  EXPECT_FALSE(project_literal("json", "[broken", error));
  EXPECT_FALSE(project_literal("unknown", "null", error));
  ASSERT_TRUE(project_literal("number", "1e-12", error));
  EXPECT_EQ(project_literal("number", "1e-12", error)->get<double>(), 1e-12);
  EXPECT_TRUE(project_literal("boolean", "false", error)->is_boolean());
  EXPECT_TRUE(project_literal("number", "null", error)->is_null());
  EXPECT_EQ(project_literal("json", "{\"a\":[1,true,null]}", error)->at("a").size(), 3u);
  EXPECT_TRUE(error.empty());
}

TEST(ProjectFiles, VscodeUrlsEncodePathDataAndRejectAmbiguousLocations)
{
  EXPECT_EQ(platform::vscode_file_url("/tmp/hello world#?.md"), "vscode://file/tmp/hello%20world%23%3F.md");
  EXPECT_EQ(platform::vscode_file_url("C:\\Research\\温度.py"), "vscode://file/C:/Research/%E6%B8%A9%E5%BA%A6.py");
  EXPECT_EQ(platform::vscode_file_url("/tmp/%file"), "vscode://file/tmp/%25file");
  EXPECT_TRUE(platform::vscode_file_url("relative/file.py").empty());
  EXPECT_TRUE(platform::vscode_file_url("/tmp/ambiguous:12").empty());
  EXPECT_TRUE(platform::vscode_file_url("\\\\server\\share\\file.py").empty());
  EXPECT_TRUE(platform::vscode_file_url(std::string("/tmp/a\0b", 8)).empty());
  std::string error;
  EXPECT_FALSE(platform::open_with_system("", &error));
  EXPECT_FALSE(error.empty());
}

TEST(ProjectTable, ValuesFollowFieldIdsAndDistinguishUnsetFromNull)
{
  ProjectTable table = ProjectTable::from_json({
      {"id", table_id}, {"name", "Cases"},
      {"fields", Json::array({{{"id", "a"}, {"name", "Renamed"}, {"type", "integer"}, {"unit", nullptr}},
                              {{"id", "b"}, {"name", "Optional"}, {"type", "json"}, {"unit", nullptr}}})},
      {"records", Json::array({{{"id", record_id}, {"values", {{"a", INT64_MAX}, {"b", nullptr}}}},
                               {{"id", "empty"}, {"values", Json::object()}}})}});
  EXPECT_EQ(table.text(0, 0), "9223372036854775807");
  EXPECT_EQ(table.text(0, 1), "null");
  EXPECT_EQ(table.cell(1, 1), nullptr);
  EXPECT_EQ(table.cell(-1, 0), nullptr);
  EXPECT_EQ(table.cell(0, 2), nullptr);
  std::swap(table.fields[0], table.fields[1]);
  EXPECT_EQ(table.text(0, 1), "9223372036854775807");
}

TEST(ProjectLayout, EditorAvailableWithoutBridgeAndPersistsLocation)
{
  wmtest::AppFixture f("zh_CN");
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().load_state({{"directory", "/tmp/项目"}, {"name", "扫描"}}));
  f.screen.set_maximized(&area);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/project_location/directory"), nullptr);
  EXPECT_EQ(area.editor().save_state()["directory"], "/tmp/项目");
  EXPECT_FALSE(f.shell->store().project().ready());
  EXPECT_FALSE(f.shell->store().project().create("/tmp/must-not-create", "No bridge"));
}

TEST(ProjectLayout, FileMenuOpensOneProjectTabAndKeepsViewer)
{
  wmtest::AppFixture f;
  f.drv->frame();
  const auto menu = f.screen.ui()->find("file")->menu;
  const auto it = std::find_if(menu.begin(), menu.end(), [&](const auto &entry) {
    return entry.text == f.shell->store().tr("editor.project.title");
  });
  ASSERT_NE(it, menu.end());
  it->action();
  f.drv->frame();
  auto &area = f.area("a2");
  ASSERT_EQ(area.tab_count(), 2);
  EXPECT_EQ(area.editor().type().id, kEditorProject);
  EXPECT_EQ(area.tab(0).type().id, kEditorViewer);
  it->action();
  f.drv->frame();
  EXPECT_EQ(area.tab_count(), 2);
}

class ProjectPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"project-app"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;

  ProjectState &state() { return f.shell->store().project(); }

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) {
      python = env;
    }
    if (python.empty()) {
      python = bridge::find_executable("python3").value_or("");
    }
    if (python.empty()) {
      GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run the project bridge integration";
    }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    state().sync();
    ASSERT_TRUE(loop.pump_until([&] { return state().ready(); }, 60)) << client->bridge_log().text();
  }

  void TearDown() override
  {
    state().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) {
      client->close();
    }
    loop.run_ready();
  }

  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }, 30)) << client->bridge_log().text();
  }

  void populated()
  {
    ASSERT_TRUE(state().create(dir.str() + "/project", "扫描"));
    settled();
    ASSERT_TRUE(state().loaded()) << state().error();
    ASSERT_TRUE(state().apply(sample_commands()));
    settled();
    ASSERT_EQ(state().tables().size(), 1u);
    ASSERT_EQ(state().project()->revision, 1);
  }
};

TEST_F(ProjectPython, SharedSelectionPersistsAcrossRefreshConflictCloseAndReopen)
{
  populated();
  ASSERT_TRUE(state().table());
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().record_id(), record_id);
  ASSERT_TRUE(state().apply(set_cell(350)));
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().record_id(), record_id);
  ASSERT_TRUE(state().apply(set_cell(400), 1));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().table()->text(0, 0), "350");
  const std::string identity = state().project()->id;
  const std::string handle = state().project()->handle;
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_FALSE(state().project());
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  EXPECT_EQ(state().project()->id, identity);
  EXPECT_NE(state().project()->handle, handle);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, BridgeRestartReopensWithoutReplayingEdits)
{
  populated();
  const auto before = *state().project();
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] {
    return state().loaded() && !state().busy() && state().project()->handle != before.handle;
  }, 60));
  EXPECT_EQ(state().project()->id, before.id);
  EXPECT_NE(state().project()->handle, before.handle);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, TableEditorSavesTypedValuesThroughSharedModel)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto *value = f.screen.ui()->find("a2/main/cell_value");
  ASSERT_NE(value, nullptr);
  auto *save = f.screen.ui()->find("a2/main/save_cell");
  ASSERT_NE(save, nullptr);
  // Drive the real bindings/callbacks rather than a second mutation implementation.
  value->string.assign("420.5");
  save->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 0), "420.5");
  value = f.screen.ui()->find("a2/main/cell_value");
  ASSERT_NE(value, nullptr);
  value->string.assign("true");
  f.screen.ui()->find("a2/main/save_cell")->on_click();
  EXPECT_FALSE(state().busy());
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "420.5");
}

TEST_F(ProjectPython, ExternalEditPreservesDraftAndRequiresReload)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/cell_value")->string.assign("450");
  std::optional<bridge::Result<Json>> edited;
  client->project_apply(state().project()->handle, 1, set_cell(500)).then([&](auto result) { edited = result; });
  ASSERT_TRUE(loop.pump_until([&] {
    return edited.has_value() && !state().busy() && state().project()->revision == 2;
  }));
  ASSERT_TRUE(edited->ok());
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "450");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  EXPECT_EQ(state().table()->text(0, 0), "500");
  f.screen.ui()->find("a2/main/reload_cell")->on_click();
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "500");
  EXPECT_TRUE(f.screen.ui()->find("a2/main/save_cell")->enabled);
}

TEST_F(ProjectPython, ReferenceAndExpressionEditorsPreserveDefinitionsAndShowErrors)
{
  populated();
  const std::string derived = "55555555-5555-4555-8555-555555555555";
  ASSERT_TRUE(state().apply(Json::array({{{"op", "add_field"}, {"id", derived}, {"table_id", table_id},
                                        {"name", "Derived"}, {"type", "number"}, {"unit", "K"}}})));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  widget("cell_field")->index.assign(1);
  f.drv->frame();
  widget("cell_mode")->index.assign(1);
  f.drv->frame();
  widget("source_table")->index.assign(1);
  f.drv->frame();
  widget("source_record")->index.assign(1);
  widget("source_field")->index.assign(1);
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 300");
  ASSERT_NE(state().table()->definition(0, 1), nullptr);
  EXPECT_EQ(state().table()->definition(0, 1)->at("source").at("field_id"), field_id);
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  widget("cell_mode")->index.assign(2);
  f.drv->frame();
  widget("expression")->string.assign("base + quantity(10, \"K\")");
  const auto [x, y] = f.widget_center("a2/main/bindings_raw");
  f.drv->click(x, y);
  f.drv->frame();
  ASSERT_NE(widget("bindings_raw/bindings"), nullptr);
  widget("bindings_raw/bindings")->string.assign(Json{{"base", {{"record_id", record_id}, {"field_id", field_id}}}}.dump());
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 310");
  EXPECT_EQ(widget("cell_mode")->index.value(), 2);
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 510");
  widget("expression")->string.assign("base / 0");
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "#division_by_zero");
  EXPECT_EQ(widget("expression")->string.value(), "base / 0");
  widget("unset_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->definition(0, 1), nullptr);
  EXPECT_EQ(state().table()->cell(0, 1), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 0);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExpressionDraftSurvivesExternalDependencyChanges)
{
  populated();
  const std::string derived = "55555555-5555-4555-8555-555555555555";
  ASSERT_TRUE(state().apply(Json::array({
    {{"op", "add_field"}, {"id", derived}, {"table_id", table_id}, {"name", "Derived"}, {"type", "number"}, {"unit", "K"}},
    {{"op", "set_expression"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", derived},
     {"expression", "base * 2"}, {"bindings", {{"base", {{"record_id", record_id}, {"field_id", field_id}}}}}}
  })));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/cell_field")->index.assign(1);
  f.drv->frame();
  f.screen.ui()->find("a2/main/expression")->string.assign("base * 3");
  std::optional<bridge::Result<Json>> edited;
  client->project_apply(state().project()->handle, 2, set_cell(500)).then([&](auto result) { edited = result; });
  ASSERT_TRUE(loop.pump_until([&] { return edited.has_value() && !state().busy() && state().project()->revision == 3; }));
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/expression")->string.value(), "base * 3");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  EXPECT_EQ(state().table()->text(0, 1), "= 1000");
  f.screen.ui()->find("a2/main/reload_cell")->on_click();
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/expression")->string.value(), "base * 2");
}

TEST_F(ProjectPython, ExplicitUpgradeCreatesBackupAndRefreshesFormat)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  const std::string source = "import sqlite3\nwith sqlite3.connect(" + Json(dir.str() + "/project/project.sqlite3").dump() +
      ") as db:\n    db.execute('DROP TABLE project_snapshots')\n    db.execute('DROP TABLE edit_journal')\n    db.execute('DROP TABLE evaluations')\n    db.execute('DROP TABLE definitions')\n    db.execute('PRAGMA user_version=1')";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  state().refresh();
  settled();
  ASSERT_EQ(state().project()->format_version, 1);
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/upgrade_project"), nullptr);
  f.screen.ui()->find("a2/main/upgrade_project")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().project()->format_version, 4);
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(f.screen.ui()->find("a2/main/upgrade_project"), nullptr);
  EXPECT_FALSE(state().notice().empty());
  size_t backups = 0;
  for (const auto &entry : std::filesystem::directory_iterator(dir.str() + "/project/backups")) {
    if (entry.path().extension() == ".sqlite3") { ++backups; }
  }
  EXPECT_EQ(backups, 1u);
  ASSERT_TRUE(state().backup());
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DestroyingStateDropsQueuedCallbacks)
{
  auto temporary = std::make_unique<ProjectState>(f.shell->store());
  temporary->attach(client.get());
  ASSERT_TRUE(temporary->create(dir.str() + "/temporary", "Temporary"));
  temporary.reset();
  std::optional<bridge::Result<std::vector<bridge::ProjectInfo>>> listed;
  client->project_list().then([&](auto result) { listed = result; });
  ASSERT_TRUE(loop.pump_until([&] { return listed.has_value(); }));
  EXPECT_TRUE(listed->ok());
  EXPECT_FALSE(state().project());
}

TEST_F(ProjectPython, PersistentUndoRedoButtonsAndNewEditsShareTheProjectHistory)
{
  populated();
  ASSERT_TRUE(state().apply(set_cell(450)));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto undo = [&] { return f.screen.ui()->find("a2/header/project_undo"); };
  auto redo = [&] { return f.screen.ui()->find("a2/header/project_redo"); };
  ASSERT_NE(undo(), nullptr);
  ASSERT_TRUE(undo()->enabled);
  EXPECT_FALSE(redo()->enabled);
  f.screen.ui()->find("a2/main/cell_value")->string.assign("Unsaved draft");
  undo()->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "Unsaved draft");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  ASSERT_TRUE(redo()->enabled);
  ASSERT_TRUE(state().close());
  settled();
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  f.drv->frame();
  ASSERT_TRUE(redo()->enabled);
  redo()->on_click();
  settled();
  EXPECT_EQ(state().table()->text(0, 0), "450");
  EXPECT_EQ(state().project()->revision, 4);
  ASSERT_TRUE(state().undo());
  settled();
  ASSERT_TRUE(state().apply(set_cell(600)));
  settled();
  EXPECT_FALSE(state().can_redo());
  EXPECT_EQ(state().table()->text(0, 0), "600");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ObjectManagementRenamesDeletesAndUndoRestoresStableSelection)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/manage_objects");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/manage_objects/" + key); };
  ASSERT_NE(widget("rename_table"), nullptr);
  widget("rename_table")->string.assign("Renamed cases");
  widget("save_table_name")->on_click();
  settled();
  f.drv->frame();
  f.drv->frame();
  EXPECT_EQ(state().table()->name, "Renamed cases");
  EXPECT_EQ(state().table_id(), table_id);
  widget("rename_field")->string.assign("");
  f.drv->frame();
  ASSERT_NE(widget("rename_field"), nullptr);  // Empty text must not hide its own input.
  widget("rename_field")->string.assign("Temperature renamed");
  widget("save_field_name")->on_click();
  settled();
  f.drv->frame();
  f.drv->frame();
  EXPECT_EQ(state().table()->fields[0].name, "Temperature renamed");
  EXPECT_EQ(state().table()->fields[0].id, field_id);
  ASSERT_TRUE(widget("delete_record")->enabled);
  widget("delete_record")->on_click();
  settled();
  f.drv->frame();
  EXPECT_TRUE(state().table()->records.empty());
  ASSERT_TRUE(state().undo());
  settled();
  f.drv->frame();
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(widget("delete_table")->enabled);
  widget("delete_table")->on_click();
  settled();
  EXPECT_TRUE(state().tables().empty());
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().table_id(), table_id);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RenameDraftRejectsExternalRevisionUntilExplicitReload)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/manage_objects");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/manage_objects/" + key); };
  widget("rename_table")->string.assign("Draft name");
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  f.drv->frame();
  EXPECT_EQ(widget("rename_table")->string.value(), "Draft name");
  EXPECT_FALSE(widget("save_table_name")->enabled);
  EXPECT_FALSE(widget("delete_table")->enabled);
  widget("reload_names")->on_click();
  f.drv->frame();
  EXPECT_EQ(widget("rename_table")->string.value(), "Cases");
  EXPECT_TRUE(widget("save_table_name")->enabled);
}

TEST_F(ProjectPython, FileIndexButtonsResolveBeforeLaunchingAndRefreshWithoutChangingFiles)
{
  populated();
  const std::string path = dir.str() + "/project/笔记 #1.md";
  { std::ofstream file(core::path_from_utf8(path)); file << "# Notes\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_files");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_files/" + key); };
  ASSERT_NE(widget("paths"), nullptr);
  widget("paths")->string.assign("笔记 #1.md");
  f.drv->frame();
  widget("index")->on_click();
  settled();
  f.drv->frame();
  ASSERT_TRUE(state().selected_file()) << state().error();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 1), "笔记 #1.md");
  int system_calls = 0, code_calls = 0;
  state().open_external = [&](const std::string &opened, std::string *) {
    EXPECT_TRUE(std::filesystem::equivalent(core::path_from_utf8(opened), core::path_from_utf8(path)));
    ++system_calls; return true;
  };
  state().open_vscode = [&](const std::string &opened, std::string *) {
    EXPECT_TRUE(std::filesystem::equivalent(core::path_from_utf8(opened), core::path_from_utf8(path)));
    ++code_calls; return true;
  };
  widget("open")->on_click();
  settled();
  f.drv->frame();
  widget("code")->on_click();
  settled();
  EXPECT_EQ(system_calls, 1);
  EXPECT_EQ(code_calls, 1);
  EXPECT_EQ(state().project()->revision, 2);  // Resolving/opening is not an edit.
  std::filesystem::remove(core::path_from_utf8(path));
  ASSERT_TRUE(state().open_file(false));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(system_calls, 1);  // A stale 'present' observation cannot launch a missing path.
  f.drv->frame();
  widget("refresh")->on_click();
  settled();
  EXPECT_EQ(state().table()->text(0, 6), "missing");
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().table()->text(0, 6), "present");
  EXPECT_FALSE(std::filesystem::exists(core::path_from_utf8(path)));
  state().open_external = platform::open_with_system;
  state().open_vscode = platform::open_with_vscode;
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, InputSnapshotsPersistBeyondSourceRemovalAndTableUndo)
{
  populated();
  const std::string path = dir.str() + "/project/input.dat";
  { std::ofstream file(core::path_from_utf8(path)); file << "frozen inputs"; }
  ASSERT_TRUE(state().index_files({path}));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/input_snapshots");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/input_snapshots/" + key); };
  ASSERT_NE(widget("capture"), nullptr);
  ASSERT_TRUE(widget("capture")->enabled);
  widget("capture")->on_click();
  settled();
  f.drv->frame();
  ASSERT_EQ(state().input_snapshots().size(), 1u) << state().error();
  const Json snapshot = state().input_snapshots().front();
  const std::string id = io::get_string(snapshot, "id");
  EXPECT_EQ(state().project()->revision, 3);
  std::filesystem::remove(core::path_from_utf8(path));
  widget("verify")->on_click();
  settled();
  EXPECT_TRUE(state().input_verification().value("ok", false)) << state().error();
  ASSERT_TRUE(state().undo());  // Undo the index edit, never the historical input copy.
  settled();
  EXPECT_EQ(state().project()->revision, 4);
  EXPECT_TRUE(state().file_index().empty());
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_TRUE(state().input_snapshots().empty());
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  ASSERT_TRUE(state().load_input_snapshots());
  settled();
  ASSERT_EQ(state().input_snapshots().size(), 1u);
  EXPECT_EQ(state().input_snapshots().front(), snapshot);
  ASSERT_TRUE(state().verify_input_snapshot(id));
  settled();
  EXPECT_TRUE(state().input_verification().value("ok", false));
  const std::string hash = io::get_string(snapshot.at("manifest").at("files").front(), "sha256");
  std::filesystem::remove(core::path_from_utf8(dir.str() + "/project/.stk/objects/sha256/" + hash.substr(0, 2) + "/" + hash.substr(2)));
  ASSERT_TRUE(state().verify_input_snapshot(id));
  settled();
  EXPECT_FALSE(state().input_verification().value("ok", true));
  EXPECT_EQ(state().input_verification().at("files").front().at("state"), "missing");
  EXPECT_EQ(state().project()->revision, 4);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DroppedFilesRegisterInCurrentProjectAndUndoRemovesOnlyTheIndex)
{
  populated();
  const std::string path = dir.str() + "/project/input.dat";
  { std::ofstream file(path); file << "1 2 3\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  auto context = area.context(nullptr, nullptr);
  ASSERT_TRUE(area.editor().on_drop({path}, context));
  settled();
  EXPECT_TRUE(state().selected_file());
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_TRUE(std::filesystem::exists(path));
  EXPECT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(state().table_id(), table_id);
  EXPECT_TRUE(state().file_index().empty());
}

}  // namespace
}  // namespace stk::app
