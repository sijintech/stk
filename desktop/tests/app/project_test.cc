/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>

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

}  // namespace
}  // namespace stk::app
