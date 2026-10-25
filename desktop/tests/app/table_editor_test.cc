/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <cstdlib>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
const std::string table_id = "31212121-1111-4111-8111-111111111111";
const std::string value_id = "32222222-2222-4222-8222-222222222222";
const std::string object_id = "32222222-2222-4222-8222-333333333333";
const std::string reference_id = "32222222-2222-4222-8222-444444444444";
const std::string record_id = "33333333-3333-4333-8333-333333333333";
const std::string second_id = "33333333-3333-4333-8333-444444444444";
const std::string other_table_id = "31212121-1111-4111-8111-222222222222";

class TableEditorPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"table-editor"};
  wmtest::AppFixture f{"en", 1, 1440, 1500};
  std::unique_ptr<bridge::Client> client;
  ProjectState &state() { return f.shell->store().project(); }
  EditorArea &area() { return f.area("a2"); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run table bridge integration"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.env["STK_PROJECTS_DIR"] = dir.str() + "/projects";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    state().sync();
    ASSERT_TRUE(loop.pump_until([&] { return state().ready(); }, 30)) << client->bridge_log().text();
    ASSERT_TRUE(area().set_tab_type(0, kEditorTable));
    f.screen.set_maximized(&area());
    f.drv->frame();
  }
  void TearDown() override
  {
    state().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
  }
  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }, 30)) << client->bridge_log().text();
    f.drv->frame();
    if (state().table()) {
      ASSERT_TRUE(loop.pump_until([&] {
        f.drv->frame();
        const auto *grid = widget("records");
        return grid && grid->table && size_t(grid->table->rows) == state().table()->records.size();
      }, 30));
    }
  }
  void populated()
  {
    ASSERT_TRUE(state().create(dir.str() + "/project", "Typed cells"));
    settled();
    ASSERT_TRUE(state().apply(Json::array({
      {{"op", "create_table"}, {"id", table_id}, {"name", "Cases"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", value_id}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", object_id}, {"name", "Metadata"}, {"type", "json"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", reference_id}, {"name", "Linked"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"table_id", table_id}, {"id", record_id}},
      {{"op", "add_record"}, {"table_id", table_id}, {"id", second_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", value_id}, {"value", 300}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second_id}, {"field_id", value_id}, {"value", 200}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", object_id}, {"value", {{"source_kind", "synthetic"}, {"array", {1, 2}}}}},
      {{"op", "set_reference"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", reference_id},
       {"source", {{"record_id", record_id}, {"field_id", value_id}}}},
      {{"op", "create_table"}, {"id", other_table_id}, {"name", "Other"}}
    })));
    settled();
    state().select_table(table_id);
    state().select_record(record_id);
    settled();
    ASSERT_NE(widget("records"), nullptr);
    ASSERT_EQ(widget("cell_value"), nullptr) << "the default workspace keeps the grid unobstructed";
    click("table_details");
    ASSERT_NE(widget("cell_value"), nullptr);
  }
  void click(const char *key)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_TRUE(w->on_click) << key;
    w->on_click();
    f.drv->frame();
  }
  void panel(const char *key)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    const ui::Vec2 center{w->rect.cx(), w->rect.cy()};
    f.screen.ui()->handle_event(ui::Event::mouse_down(center));
    f.screen.ui()->handle_event(ui::Event::mouse_up(center));
    f.drv->frame();
  }
  void assign_value(const std::string &value)
  {
    const auto *w = widget("cell_value"); ASSERT_NE(w, nullptr);
    w->string.assign(value);
    f.drv->frame();
  }
  void cell(int row, int column)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      const auto *grid = widget("records");
      return grid && grid->table && row < grid->table->rows;
    }, 30));
    const auto *w = widget("records"); ASSERT_NE(w, nullptr); ASSERT_TRUE(w->table->on_cell_select);
    const auto spec = *w->table;
    spec.selected.assign(row);
    spec.on_cell_select(row, column);
    f.drv->frame();
    if (!widget("table_detail_field")) { click("table_details"); }
  }
};

TEST_F(TableEditorPython, OpensAsIndependentTableOnlyPageWithoutCreatingProject)
{
  EXPECT_EQ(area().editor().type().id, kEditorTable);
  EXPECT_TRUE(area().editor().show_view("data"));
  EXPECT_FALSE(area().editor().show_view("runs"));
  EXPECT_FALSE(state().project());
  EXPECT_NE(widget("table_open_project"), nullptr);
  EXPECT_EQ(widget("create"), nullptr);
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  populated();
  EXPECT_NE(widget("table"), nullptr);
  EXPECT_NE(widget("records"), nullptr);
  EXPECT_NE(widget("table_detail_field"), nullptr);
  EXPECT_EQ(widget("project_simulation"), nullptr);
  EXPECT_EQ(widget("project_files"), nullptr);
  EXPECT_EQ(widget("project_snapshots"), nullptr);
  EXPECT_EQ(widget("project_location"), nullptr);
  EXPECT_EQ(widget("project_view"), nullptr);
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableEditorPython, ClickedCellSelectsStableFieldAndUsesExistingReferenceAndUndo)
{
  populated();
  // Real table pointer events: sorting changes view rows but editing still uses row/field UUIDs.
  const auto *w = widget("records"); ASSERT_NE(w, nullptr);
  const ui::Rect rect = w->rect;
  const auto &style = f.screen.ui()->style();
  auto pointer = [&](float x, float y) {
    const ui::Vec2 p{x, y};
    f.screen.ui()->handle_event(ui::Event::mouse_down(p));
    f.screen.ui()->handle_event(ui::Event::mouse_up(p));
    f.drv->frame();
  };
  pointer(rect.x + style.pixel + 6 * style.unit, rect.y + style.pixel + 0.5f * style.unit);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *grid = widget("records");
    return grid && grid->table && grid->table->rows == 2 && grid->table->cell(0, 1) == "200";
  }, 30));
  pointer(rect.x + style.pixel + 6 * style.unit, rect.y + style.pixel + 1.5f * style.unit);
  EXPECT_EQ(state().record_id(), second_id);
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "200");
  assign_value("210");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  click("save_cell"); settled();
  EXPECT_EQ(state().table()->cell(1, 0), &state().table()->records[1].values.at(value_id));
  EXPECT_EQ(*state().table()->cell(1, 0), 210);
  click("project_undo"); settled();
  EXPECT_EQ(*state().table()->cell(1, 0), 200);
  cell(1, 3);  // The saved/query sort puts the original first record second in the view.
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(*state().table()->cell(0, 2), 300);
  cell(1, 2);
  EXPECT_EQ(widget("cell_mode")->index.value(), 0);
  EXPECT_NE(widget("cell_value")->string.value().find("synthetic"), std::string::npos);
  panel("cell_details");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableEditorPython, DirtyDraftBlocksOtherRowFieldTableAndHiddenTabNavigation)
{
  populated();
  assign_value("345");
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  cell(1, 2);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 0);
  EXPECT_EQ(widget("cell_value")->string.value(), "345");
  widget("table_detail_field")->index.assign(1);
  f.drv->frame();
  EXPECT_EQ(widget("table_detail_field")->index.value(), 0);
  const auto table_dropdown = widget("table")->index;
  table_dropdown.assign(1);
  f.drv->frame();
  EXPECT_EQ(state().table_id(), table_id);
  ASSERT_TRUE(area().add_tab(kEditorTable));
  settled();
  ASSERT_EQ(area().tab_count(), 2);
  ASSERT_NE(widget("records"), nullptr);
  cell(1, 1);
  EXPECT_EQ(state().record_id(), record_id) << "hidden first tab still owns its unsaved draft";
  area().set_active_tab(0); f.drv->frame();
  EXPECT_EQ(widget("cell_value")->string.value(), "345");
  click("reload_cell");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  cell(1, 2);
  EXPECT_EQ(state().record_id(), second_id);
  EXPECT_EQ(widget("table_detail_field")->index.value(), 1);
}

TEST_F(TableEditorPython, RetainedGridCallbacksRefuseChangedFilterRevisionAndDestroyedEditor)
{
  populated();
  const auto stale = *widget("records")->table;
  widget("table_search")->string.assign(record_id);
  f.drv->frame();
  stale.selected.assign(1);
  stale.on_cell_select(1, 2);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_TRUE(stale.cell(0, 1).empty());
  widget("table_search")->string.assign(""); f.drv->frame();
  const auto before_revision = *widget("records")->table;
  ASSERT_TRUE(state().apply(Json::array({{{"op", "rename_table"}, {"id", table_id}, {"name", "Renamed"}}})));
  settled();
  before_revision.selected.assign(1);
  EXPECT_EQ(state().record_id(), record_id);
  const auto before_destroy = *widget("records")->table;
  ASSERT_TRUE(area().set_tab_type(0, kEditorProject)); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorProject);
  before_destroy.selected.assign(1);
  before_destroy.on_cell_select(1, 2);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_TRUE(before_destroy.cell(0, 1).empty());
}

TEST_F(TableEditorPython, RetainedManagementCallbacksCannotModifyAnotherProjectOrOutliveEditor)
{
  populated();
  panel("manage_objects");
  ASSERT_NE(widget("save_table_name"), nullptr);
  const auto old_rename = widget("save_table_name")->on_click;
  const auto old_delete = widget("delete_table")->on_click;
  ASSERT_NE(widget("table_detail_field"), nullptr);
  const auto old_field = widget("table_detail_field")->index;
  ASSERT_TRUE(state().create(dir.str() + "/project-b", "Other project"));
  settled();
  ASSERT_TRUE(state().apply(Json::array({
    {{"op", "create_table"}, {"id", table_id}, {"name", "Other cases"}},
    {{"op", "add_field"}, {"table_id", table_id}, {"id", value_id}, {"name", "Temperature"}, {"type", "number"}},
    {{"op", "add_record"}, {"table_id", table_id}, {"id", record_id}}
  })));
  settled();
  state().select_table(table_id); state().select_record(record_id); f.drv->frame();
  settled();
  if (!widget("table_detail_field")) { click("table_details"); }
  if (!widget("rename_table")) { panel("manage_objects"); }
  ASSERT_NE(widget("rename_table"), nullptr);
  widget("rename_table")->string.assign("Unsaved name");
  f.drv->frame();
  const auto revision = state().project()->revision;
  old_rename(); old_delete(); old_field.assign(1);
  settled();
  ASSERT_NE(state().table(), nullptr);
  EXPECT_EQ(state().table()->name, "Other cases");
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(widget("rename_table")->string.value(), "Unsaved name");
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  click("reload_names");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  const auto destroyed_rename = widget("save_table_name")->on_click;
  const auto destroyed_delete = widget("delete_table")->on_click;
  ASSERT_TRUE(area().set_tab_type(0, kEditorProject)); f.drv->frame();
  destroyed_rename(); destroyed_delete();
  old_rename(); old_delete();
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(state().table()->name, "Other cases");
}

TEST_F(TableEditorPython, DestructiveActionsCannotDiscardAnotherHiddenTablesDirtyCell)
{
  populated();
  assign_value("345");
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  ASSERT_TRUE(area().add_tab(kEditorTable)); settled();
  ASSERT_FALSE(area().editor().has_unsaved_changes());
  click("table_details");
  panel("manage_objects");
  const auto revision = state().project()->revision;
  for (const auto *key : {"delete_record", "delete_field", "delete_table"}) {
    const auto *action = widget(key); ASSERT_NE(action, nullptr); ASSERT_TRUE(action->enabled);
    action->on_click(); f.drv->frame();
    EXPECT_FALSE(state().busy()) << key;
    EXPECT_EQ(state().project()->revision, revision) << key;
    ASSERT_NE(state().table(), nullptr);
    EXPECT_EQ(state().table()->records.size(), 2u) << key;
    EXPECT_EQ(state().table()->fields.size(), 3u) << key;
    EXPECT_EQ(state().record_id(), record_id) << key;
  }
  area().set_active_tab(0); f.drv->frame();
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(widget("cell_value")->string.value(), "345");
  click("reload_cell");
  ASSERT_FALSE(area().editor().has_unsaved_changes());
  area().set_active_tab(1); f.drv->frame();
  click("delete_record"); settled();
  EXPECT_EQ(state().project()->revision, revision + 1);
  ASSERT_NE(state().table(), nullptr);
  EXPECT_EQ(state().table()->records.size(), 1u);
  EXPECT_EQ(state().table()->records.front().id, second_id);
}
}  // namespace
}  // namespace stk::app
