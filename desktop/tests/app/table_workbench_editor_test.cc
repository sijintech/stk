/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/table_workbench.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
const std::string samples = "c1111111-1111-4111-8111-111111111111";
const std::string temperature = "c2222222-2222-4222-8222-222222222222";
const std::string counter = "c3333333-3333-4333-8333-333333333333";
const std::string accepted = "c4444444-4444-4444-8444-444444444444";
const std::string phase = "c5555555-5555-4555-8555-555555555555";
const std::string evidence = "c6666666-6666-4666-8666-666666666666";
const std::string row_a = "c7777777-7777-4777-8777-777777777777";
const std::string row_b = "c8888888-8888-4888-8888-888888888888";
const std::string row_c = "c9999999-9999-4999-8999-999999999999";
const std::string dry = "caaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const std::string batches = "cbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const std::string batch_label = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const std::string batch_row = "cddddddd-dddd-4ddd-8ddd-dddddddddddd";

class TableWorkbenchEditorPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"table-workbench-editor"};
  wmtest::AppFixture f{"en", 1, 1440, 1200};
  ui::MemoryClipboard clipboard;
  std::unique_ptr<bridge::Client> client;
  std::shared_ptr<const io::Payload> existing_payload;
  uint64_t payload_serial = 0, camera_serial = 0;
  double event_time = 500;
  ProjectState &project() { return f.shell->store().project(); }
  ViewerState &viewer() { return f.shell->store().viewer(); }
  EditorArea &area() { return f.area("a4"); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  bool pump(const std::function<bool()> &predicate)
  {
    return loop.pump_until([&] { frame(); return predicate(); }, 30);
  }
  void settled(int expected_rows = 3)
  {
    ASSERT_TRUE(pump([&] {
      const auto *grid = widget("records");
      return !project().busy() && grid && grid->table && grid->table->rows == expected_rows;
    }));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  void send(ui::Event event)
  {
    event.time = event_time += 1;
    f.screen.ui()->handle_event(event);
    frame();
  }
  void point(ui::Vec2 point)
  {
    send(ui::Event::mouse_down(point));
    send(ui::Event::mouse_up(point));
  }
  void click(const char *key)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    point({w->rect.cx(), w->rect.cy()});
  }
  void action(const char *key)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_TRUE(w->on_click) << key;
    w->on_click(); frame();
  }
  void cell(int row, int column)
  {
    const auto *w = widget("records");
    ASSERT_NE(w, nullptr);
    ASSERT_TRUE(w->table && w->table->grid);
    const auto &style = f.screen.ui()->style();
    const auto width = [&](int c) {
      const auto &field = w->table->columns[size_t(c)];
      float value = field.width;
      if (w->table->column_width) {
        const auto configured = w->table->column_width(field.key);
        if (configured && std::isfinite(*configured) && *configured >= 1.5f && *configured <= 10000) {
          value = *configured;
        }
      }
      return std::round(value * style.unit);
    };
    float x = w->rect.x + style.pixel;
    for (int c = 0; c < column; ++c) { x += width(c); }
    x += .5f * width(column);
    point({x, w->rect.y + style.pixel + (row + 1.5f) * style.unit * w->table->row_height});
  }
  void select(int row, int column)
  {
    const auto *w = widget("records");
    ASSERT_NE(w, nullptr);
    ASSERT_TRUE(w->table && w->table->grid);
    w->table->grid->selection.assign({{row, column}, {row, column}});
    frame();
  }
  void assign(const char *key, const std::string &value)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    w->string.assign(value); frame();
  }
  void index(const char *key, int value)
  {
    const auto *w = widget(key);
    ASSERT_NE(w, nullptr) << key;
    w->index.assign(value); frame();
  }
  void edit_field(int column)
  {
    const auto *grid = widget("records");
    ASSERT_NE(grid, nullptr);
    ASSERT_TRUE(grid->table && grid->table->column_menu);
    const auto menu = grid->table->column_menu(column);
    const auto label = std::string(f.shell->store().tr("table.edit_field"));
    const auto edit = std::find_if(menu.begin(), menu.end(), [&](const auto &entry) { return entry.text == label; });
    ASSERT_NE(edit, menu.end());
    ASSERT_TRUE(edit->enabled && edit->action);
    edit->action(); frame();
    ASSERT_NE(widget("field_name"), nullptr);
  }
  void expect_viewer()
  {
    EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
    EXPECT_EQ(f.screen.maximized(), nullptr);
    EXPECT_EQ(viewer().base_payload(), existing_payload);
    EXPECT_EQ(viewer().payload_serial(), payload_serial);
    EXPECT_EQ(viewer().camera_serial(), camera_serial);
    EXPECT_EQ(viewer().evaluations_started(), 0);
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    ui::ContextConfig ui_config;
    ui_config.measurer = &f.measurer;
    ui_config.catalog = &f.shell->store().catalog();
    ui_config.clipboard = &clipboard;
    f.screen.set_ui_config(ui_config);
    frame();
    bridge::ClientOptions options;
    options.python.configured = python;
    options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready();
    f.shell->store().set_bridge(client.get());
    project().sync();
    ASSERT_TRUE(project().create(dir.str() + "/project", "Synthetic research table"));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", samples}, {"name", "Synthetic PET samples"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", temperature}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", counter}, {"name", "Counter"}, {"type", "integer"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", accepted}, {"name", "Accepted"}, {"type", "boolean"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", phase}, {"name", "State"}, {"type", "single_select"},
       {"options", {{"version", 1}, {"choices", Json::array({{{"id", dry}, {"label", "Dry"}, {"color", "#123456"}}})}}}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", evidence}, {"name", "Evidence"}, {"type", "object"},
       {"options", {{"version", 1}, {"kinds", Json::array({"record", "file"})}}}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_a}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_b}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_c}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", temperature}, {"value", 300}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", temperature}, {"value", nullptr}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_c}, {"field_id", temperature}, {"value", 350}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", counter}, {"value", INT64_MAX}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", accepted}, {"value", false}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", phase}, {"value", dry}},
      {{"op", "create_table"}, {"id", batches}, {"name", "Synthetic batches"}},
      {{"op", "add_field"}, {"table_id", batches}, {"id", batch_label}, {"name", "Label"}, {"type", "text"}},
      {{"op", "add_record"}, {"table_id", batches}, {"id", batch_row}},
      {{"op", "set_cell"}, {"table_id", batches}, {"record_id", batch_row}, {"field_id", batch_label}, {"value", "Synthetic B"}},
    })));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    project().select_table(samples);
    project().select_record(row_a);
    ASSERT_NO_FATAL_FAILURE(settled());
    existing_payload = std::make_shared<io::Payload>(io::read_stkp(
        std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    viewer().open_payload(existing_payload, "Existing public synthetic result");
    frame();
    payload_serial = viewer().payload_serial();
    camera_serial = viewer().camera_serial();
  }
  void TearDown() override
  {
    if (existing_payload) { expect_viewer(); }
    project().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(TableWorkbenchEditorPython, DefaultGridUsesMostOfTheTablePaneAndBooleanChangesInOnePointerClick)
{
  ASSERT_EQ(area().editor().type().id, kEditorTable);
  const auto *grid = widget("records");
  ASSERT_NE(grid, nullptr);
  ASSERT_NE(area().find_region("main"), nullptr);
  EXPECT_GE(grid->rect.h, .55f * area().find_region("main")->rect().height());
  EXPECT_EQ(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("manage_objects"), nullptr);
  EXPECT_EQ(grid->table->grid->cell_style(0, 3), ui::TableCellStyle::Checkbox);
  EXPECT_EQ(grid->table->grid->cell_style(1, 3), ui::TableCellStyle::Text);
  EXPECT_TRUE(grid->table->cell(1, 3).empty()) << "an unset scientific observation is not displayed as false";
  const auto revision = project().project()->revision;
  cell(0, 3);  // The actual checkbox body receives one pointer down/up, with no form or Save.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_TRUE(project().table()->cell(0, 2)->get<bool>());
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, InlineTypingSuspendsOnBlurAndOnlyEnterWritesTheRetainedDraft)
{
  const auto revision = project().project()->revision;
  cell(0, 1);
  send(ui::Event::text_input("315"));
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  click("table_search");
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  cell(0, 1);
  send(ui::Event::key_down(ui::Key::F2));
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "315");
  send(ui::Event::key_down(ui::Key::Enter));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 315);
  EXPECT_FALSE(area().editor().has_unsaved_changes());
  EXPECT_EQ(project().record_id(), row_b);
  EXPECT_EQ(widget("records")->table->grid->selection.value().active, (ui::TableCell{1, 1}));
}

TEST_F(TableWorkbenchEditorPython, PasteFitsTheActualRectanglePreviewsAndUndoesAsOneEdit)
{
  const auto initial = project().project()->revision;
  cell(0, 1);
  clipboard.text = "310";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { const auto *apply = widget("table_paste_apply"); return apply && apply->enabled; }));
  EXPECT_EQ(project().project()->revision, initial);
  ASSERT_NE(widget("table_paste_cells"), nullptr);
  EXPECT_EQ(widget("table_paste_cells")->table->rows, 1);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, initial + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 310);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);

  cell(0, 1);
  clipboard.text = "320\t9223372036854775806\n330\t-9223372036854775807";
  const auto before = project().project()->revision;
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { const auto *apply = widget("table_paste_apply"); return apply && apply->enabled; }));
  EXPECT_EQ(widget("table_paste_cells")->table->rows, 4);
  EXPECT_EQ(project().project()->revision, before);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, before + 1);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_C(9223372036854775806));
  EXPECT_EQ(*project().table()->cell(1, 0), 330);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(project().table()->cell(1, 1), nullptr);
}

TEST_F(TableWorkbenchEditorPython, CsvPreviewMappingRejectsChangedBytesThenImportsUndoablyAndExportsTheFilteredView)
{
  const auto source = dir.path() / "synthetic-input.csv";
  const auto output = dir.path() / "synthetic-filtered.csv";
  const auto write_source = [&](const char *hot_temperature) {
    std::ofstream file(source, std::ios::binary | std::ios::trunc);
    ASSERT_TRUE(file.is_open());
    file << "Temperature,Count,Note\n300,9223372036854775807,\"synthetic, cold\"\n"
         << hot_temperature << ",2,\"synthetic, hot\"\n";
    file.close();
    ASSERT_TRUE(file.good());
  };
  const auto open_csv = [&] {
    const auto *more = widget("table_more"); ASSERT_NE(more, nullptr);
    const auto label = std::string(f.shell->store().tr("project.csv.title"));
    const auto found = std::find_if(more->menu.begin(), more->menu.end(),
        [&](const auto &entry) { return entry.text == label; });
    ASSERT_NE(found, more->menu.end()); ASSERT_TRUE(found->enabled && found->action);
    const auto open = found->action;
    open(); frame();
    ASSERT_NE(widget("table_csv_source"), nullptr);
  };
  const auto preview_and_map = [&](const std::string &expected_hot) {
    assign("table_csv_source", core::path_to_utf8(source));
    action("table_csv_preview");
    ASSERT_TRUE(pump([&] {
      const auto *grid = widget("table_csv_preview_grid");
      return grid && grid->table && grid->table->rows == 2 && grid->table->columns.size() == 3 &&
             grid->table->cell(1, 0) == expected_hot;
    }));
    EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 1), "9223372036854775807");
    EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 2), "synthetic, cold");
    // Explicit per-column GUI declarations: previewing does not infer numeric types or units.
    ASSERT_NE(widget("csv_column0/type"), nullptr);
    EXPECT_EQ(widget("csv_column0/type")->index.value(), 0);
    index("csv_column0/type", 2);  // number
    ASSERT_NE(widget("csv_column0/unit"), nullptr); ASSERT_TRUE(widget("csv_column0/unit")->enabled);
    assign("csv_column0/unit", "K");
    index("csv_column1/type", 1);  // integer, retained exactly beyond double precision
    EXPECT_EQ(widget("csv_column2/type")->index.value(), 0);  // text remains text
    assign("table_csv_name", "Synthetic imported measurements");
    ASSERT_NE(widget("table_csv_import"), nullptr); ASSERT_TRUE(widget("table_csv_import")->enabled);
  };

  const auto initial = project().project()->revision;
  const auto initial_tables = project().tables().size();
  ASSERT_NO_FATAL_FAILURE(write_source("350"));
  ASSERT_NO_FATAL_FAILURE(open_csv());
  ASSERT_NO_FATAL_FAILURE(preview_and_map("350"));
  EXPECT_EQ(project().project()->revision, initial);
  EXPECT_EQ(project().tables().size(), initial_tables);
  ASSERT_NO_FATAL_FAILURE(write_source("360.5"));  // A real byte change after the displayed preview.
  action("table_csv_import");
  ASSERT_TRUE(pump([&] { return !project().busy() && !project().error().empty(); }));
  EXPECT_NE(project().error().find("changed since its preview"), std::string::npos);
  EXPECT_EQ(project().project()->revision, initial);
  EXPECT_EQ(project().tables().size(), initial_tables);
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  expect_viewer();

  ASSERT_NO_FATAL_FAILURE(open_csv());
  ASSERT_NO_FATAL_FAILURE(preview_and_map("360.5"));
  action("table_csv_import");
  ASSERT_NO_FATAL_FAILURE(settled(2));
  ASSERT_EQ(project().tables().size(), initial_tables + 1);
  EXPECT_EQ(project().project()->revision, initial + 1);
  ASSERT_NE(project().table_id(), samples);
  const auto imported = project().table_id();
  const auto first_record = project().table()->records[0].id, second_record = project().table()->records[1].id;
  ASSERT_EQ(project().table()->fields.size(), 3u);
  EXPECT_EQ(project().table()->fields[0].type, "number");
  EXPECT_EQ(project().table()->fields[0].unit, "K");
  EXPECT_EQ(project().table()->fields[1].type, "integer");
  EXPECT_EQ(project().table()->fields[2].type, "text");
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(*project().table()->cell(1, 0), 360.5);
  EXPECT_EQ(*project().table()->cell(1, 2), "synthetic, hot");

  // One Undo removes the entire table/field/record/cell batch; one Redo restores its identities.
  action("project_undo");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, initial + 2);
  EXPECT_EQ(project().tables().size(), initial_tables);
  EXPECT_TRUE(std::none_of(project().tables().begin(), project().tables().end(),
      [&](const auto &table) { return table.id == imported; }));
  action("project_redo");
  ASSERT_TRUE(pump([&] { return !project().busy() && project().tables().size() == initial_tables + 1; }));
  const auto restored = std::find_if(project().tables().begin(), project().tables().end(),
      [&](const auto &table) { return table.id == imported; });
  ASSERT_NE(restored, project().tables().end());
  index("table", int(restored - project().tables().begin()));
  ASSERT_NO_FATAL_FAILURE(settled(2));
  EXPECT_EQ(project().project()->revision, initial + 3);
  ASSERT_EQ(project().table()->records.size(), 2u);
  EXPECT_EQ(project().table()->records[0].id, first_record);
  EXPECT_EQ(project().table()->records[1].id, second_record);
  EXPECT_EQ(project().table()->fields[0].unit, "K");
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);

  action("table_settings");
  index("table_filter_field", 0);
  index("table_filter_op", 3);  // Numeric gt.
  assign("table_filter_value", "300");
  action("table_filter_add");
  action("table_view_done");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "360.5");
  ASSERT_EQ(project().table()->records.size(), 2u) << "filtering changes the view, not stored rows";
  ASSERT_NO_FATAL_FAILURE(open_csv());
  assign("table_csv_destination", core::path_to_utf8(output));
  action("table_csv_export");
  ASSERT_TRUE(pump([&] { return !project().busy() && std::filesystem::is_regular_file(output); }));
  EXPECT_TRUE(project().error().empty()) << project().error();
  EXPECT_EQ(project().project()->revision, initial + 3);
  std::ifstream file(output, std::ios::binary); ASSERT_TRUE(file.is_open());
  const std::string actual((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
  EXPECT_EQ(actual, std::string("\xEF\xBB\xBF") +
      "Temperature,Count,Note\r\n360.5,2,\"synthetic, hot\"\r\n");
  const auto &scripts = f.shell->store().scripts();
  EXPECT_TRUE(scripts.history().empty());
  EXPECT_TRUE(!scripts.status().contains("run") || scripts.status().at("run").is_null());
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, SavedLeafFilterSurvivesAddingAnotherConditionAndResavingTheView)
{
  const std::string saved_view = "e1111111-1111-4111-8111-111111111111";
  const Json positive = {{"field_id", temperature}, {"op", "gt"}, {"value", 0}};
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_b}, {"field_id", temperature}, {"value", -10}},
    {{"op", "put_table_view"}, {"id", saved_view}, {"table_id", samples}, {"name", "Positive synthetic samples"},
     {"definition", {{"version", 1}, {"kind", "grid"}, {"filters", positive}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  index("table_views", 1);
  ASSERT_NO_FATAL_FAILURE(settled(2));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300");
  EXPECT_EQ(widget("records")->table->cell(1, 1), "350");

  action("table_settings");
  ASSERT_NE(widget("filter0/remove"), nullptr) << "the root leaf is visible in the builder";
  index("table_filter_field", 0);
  index("table_filter_op", 5); // lt
  assign("table_filter_value", "325");
  action("table_filter_add");
  const auto before_save = project().project()->revision;
  action("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(project().project()->revision, before_save + 1);
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300")
      << "the negative record must not reappear when the upper bound is added";
  ASSERT_EQ(project().table()->records.size(), 3u);
  EXPECT_EQ(*project().table()->cell(1, 0), -10);

  Json stored;
  bool done = false;
  bridge::CallOptions never;
  never.retry = bridge::CallOptions::Retry::Never;
  client->call("project.table.views.get", {{"handle", project().project()->handle},
      {"expected_revision", project().project()->revision}, {"id", saved_view}}, never).then([&](auto response) {
    EXPECT_TRUE(response);
    if (response) { stored = response.value().at("view").at("definition").at("filters"); }
    done = true;
  });
  ASSERT_TRUE(pump([&] { return done; }));
  ASSERT_TRUE(stored.is_object());
  EXPECT_EQ(stored.at("op"), "and");
  ASSERT_EQ(stored.at("conditions").size(), 2u);
  EXPECT_EQ(nlohmann::json(stored.at("conditions")[0]), nlohmann::json(positive));
  EXPECT_EQ(nlohmann::json(stored.at("conditions")[1]),
      nlohmann::json({{"field_id", temperature}, {"op", "lt"}, {"value", 325}}));
  expect_viewer();
}

TEST_F(TableWorkbenchEditorPython, NullDateAndAmbiguousChoiceLabelsNeverTurnIntoAnotherValue)
{
  const std::string date = "d6666666-6666-4666-8666-666666666666";
  const std::string other = "d7777777-7777-4777-8777-777777777777";
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "add_field"}, {"table_id", samples}, {"id", date}, {"name", "Observed"}, {"type", "date"}},
    {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", date}, {"value", nullptr}},
    {{"op", "set_field_schema"}, {"id", phase}, {"type", "single_select"}, {"unit", nullptr},
      {"options", {{"version", 1}, {"choices", Json::array({
        {{"id", dry}, {"label", "Repeated"}, {"color", "#123456"}},
        {{"id", other}, {"label", "Repeated"}, {"color", "#234567"}}
      })}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  cell(0, 6);
  send(ui::Event::key_down(ui::Key::F2));
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_TRUE(f.screen.ui()->edit_state()->text().empty());
  send(ui::Event::key_down(ui::Key::Enter));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(project().table()->cell(0, 5));
  EXPECT_TRUE(project().table()->cell(0, 5)->is_null());
  cell(0, 4);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::text_input("Repeated"));
  const auto revision = project().project()->revision;
  send(ui::Event::key_down(ui::Key::Enter));
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "Repeated");
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, NamedTypedFilterAndSortSurviveProjectCloseAndReopen)
{
  click("table_settings");
  assign("table_view_name", "Hot synthetic samples");
  index("table_filter_field", 0);
  index("table_filter_op", 3);  // Numeric gt, not lexicographic text matching.
  assign("table_filter_value", "300");
  click("table_filter_add");
  index("table_sort_field", 1);
  index("table_sort_direction", 1);
  click("table_sort_add");
  click("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "350");
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(pump([&] { return !project().project() && !project().busy(); }));
  ASSERT_TRUE(area().add_tab(kEditorTable));  // A fresh instance proves the view came from the project DB.
  frame();
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(pump([&] { const auto *tabs = widget("table_views"); return tabs && tabs->items.size() == 2; }));
  // Fixed starting point: freshly reopened project, all-records view visible. One pointer
  // click switches to the saved view; asynchronous reads and typing are not counted as clicks.
  const auto *tabs = widget("table_views"); ASSERT_NE(tabs, nullptr);
  point({tabs->rect.x + tabs->rect.w * .75f, tabs->rect.cy()});
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "350");
  EXPECT_EQ(project().table()->records.size(), 3u);
}

TEST_F(TableWorkbenchEditorPython, ChoiceAndBooleanFiltersUseTypedPickersWithoutEnteringIdentities)
{
  click("table_settings");
  index("table_filter_field", 3);  // State: stored UUID, human option label in the UI.
  index("table_filter_op", 0);
  ASSERT_NE(widget("table_filter_choice"), nullptr);
  EXPECT_EQ(widget("table_filter_choice")->items, (std::vector<std::string>{"Dry"}));
  EXPECT_EQ(widget("table_filter_value"), nullptr);
  index("table_filter_choice", 0);
  click("table_filter_add");
  index("table_filter_field", 2);  // Accepted: a boolean picker, not JSON entry.
  ASSERT_NE(widget("table_filter_boolean"), nullptr);
  index("table_filter_boolean", 1);
  click("table_filter_add");
  assign("table_view_name", "Dry pending samples");
  click("table_view_save");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(widget("records")->table->cell(0, 1), "300");
  EXPECT_EQ(project().table()->records.size(), 3u);
}

TEST_F(TableWorkbenchEditorPython, SameTableExternalSelectionKeepsGridDetailAndSaveOnTheSameRecord)
{
  select(0, 1);
  action("table_details");
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "300");
  const auto selected = project().request_select(project().project()->handle, project().project()->revision, samples, row_c);
  ASSERT_TRUE(selected);
  frame();
  ASSERT_NE(widget("records"), nullptr);
  EXPECT_EQ(widget("records")->table->grid->selection.value().active, (ui::TableCell{2, 1}));
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "350");
  assign("cell_value", "360");
  action("save_cell");  // Exercise the retained advanced editor's stable-ID command, not a mouse KPI.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  EXPECT_EQ(*project().table()->cell(2, 0), 360);
  EXPECT_EQ(project().record_id(), row_c);
}

TEST_F(TableWorkbenchEditorPython, RecordObjectPickerLinksAnotherTableAndLocatesItsStableRecord)
{
  select(0, 5);
  click("table_details");
  click("table_pick_object");
  ASSERT_NE(widget("table_object_table"), nullptr);
  index("table_object_table", 1);
  ASSERT_TRUE(pump([&] {
    const auto *list = widget("table_object_candidates");
    return list && list->list && list->list->count == 1 &&
        list->list->text(0).find("Synthetic batches") != std::string::npos;
  }));
  widget("table_object_candidates")->list->selected.assign(0);
  frame();
  click("table_object_set");
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto *reference = project().table()->cell(0, 4);
  ASSERT_NE(reference, nullptr);
  ASSERT_TRUE(reference->is_object());
  EXPECT_EQ(reference->at("kind"), "record");
  EXPECT_EQ(reference->at("table_id"), batches);
  EXPECT_EQ(reference->at("id"), batch_row);
  EXPECT_EQ(reference->at("project_id"), project().project()->id);
  EXPECT_EQ(project().table_id(), samples);
  click("table_resolve_object");
  ASSERT_TRUE(pump([&] { return widget("table_object_locate") != nullptr; }));
  action("table_object_locate");
  ASSERT_NO_FATAL_FAILURE(settled(1));
  EXPECT_EQ(project().table_id(), batches);
  EXPECT_EQ(project().record_id(), batch_row);
  EXPECT_EQ(*project().table()->cell(0, 0), "Synthetic B");
}

TEST_F(TableWorkbenchEditorPython, CancelledAndSupersededPasteApplyCallbacksCannotWrite)
{
  cell(0, 1);
  clipboard.text = "310";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { return widget("table_paste_apply") != nullptr; }));
  const auto abandoned = widget("table_paste_apply")->on_click;
  ASSERT_TRUE(abandoned);
  click("table_paste_cancel");
  const auto revision = project().project()->revision;
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);

  cell(0, 1);
  clipboard.text = "320";
  send(ui::Event::key_down(ui::Key::V, ui::MOD_CTRL));
  ASSERT_TRUE(pump([&] { return widget("table_paste_apply") != nullptr; }));
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(*project().table()->cell(0, 0), 300);
  click("table_paste_apply");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(*project().table()->cell(0, 0), 320);
}

TEST_F(TableWorkbenchEditorPython, CancelledObjectPickerCannotApplyItsRetainedUseCallback)
{
  select(0, 5);
  click("table_details");
  click("table_pick_object");
  index("table_object_table", 1);
  ASSERT_TRUE(pump([&] {
    const auto *list = widget("table_object_candidates");
    return list && list->list && list->list->count == 1 &&
        list->list->text(0).find("Synthetic batches") != std::string::npos;
  }));
  widget("table_object_candidates")->list->selected.assign(0);
  frame();
  const auto *use = widget("table_object_set");
  ASSERT_NE(use, nullptr);
  ASSERT_TRUE(use->enabled);
  const auto abandoned = use->on_click;
  ASSERT_TRUE(abandoned);
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_EQ(widget("table_object_set"), nullptr);
  const auto revision = project().project()->revision;
  abandoned(); frame(); loop.run_ready(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 4), nullptr);
}

TEST_F(TableWorkbenchEditorPython, FormulaCellsOpenTheirDefinitionAndRecomputeWithoutBecomingLiterals)
{
  const std::string derived = "ceeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
  ASSERT_TRUE(project().apply(Json::array({
    {{"op", "add_field"}, {"table_id", samples}, {"id", derived}, {"name", "Derived temperature"}, {"type", "number"}, {"unit", "K"}},
    {{"op", "set_expression"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", derived},
     {"expression", "base + quantity(10, \"K\")"},
     {"bindings", {{"base", {{"record_id", row_a}, {"field_id", temperature}}}}}}
  })));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  cell(0, 6);
  send(ui::Event::key_down(ui::Key::F2));
  send(ui::Event::text_input("999"));
  EXPECT_EQ(f.screen.ui()->editing(), 0);
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("cell_mode"), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 2);
  EXPECT_NE(widget("expression")->string.value().find("quantity"), std::string::npos);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(*project().table()->cell(0, 5), 310);
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", samples},
      {"record_id", row_a}, {"field_id", temperature}, {"value", 305}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 5), 315);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(project().table()->definition(0, 5)->at("kind"), "expression");
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(pump([&] { return !project().project() && !project().busy(); }));
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(*project().table()->cell(0, 5), 315);
  ASSERT_TRUE(project().table()->definition(0, 5));
  EXPECT_EQ(project().table()->definition(0, 5)->at("kind"), "expression");
}

TEST_F(TableWorkbenchEditorPython, FieldChoiceRenameAndRepeatedReorderPreserveIdsAndStoredSelection)
{
  const std::string wet = "cfffffff-ffff-4fff-8fff-ffffffffffff";
  const std::string desorbed = "d1111111-1111-4111-8111-111111111111";
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_field_schema"}, {"id", phase},
      {"type", "single_select"}, {"unit", nullptr}, {"options", {{"version", 1},
        {"choices", Json::array({
          {{"id", dry}, {"label", "Dry"}, {"color", "#123456"}},
          {{"id", wet}, {"label", "Wet"}, {"color", "#234567"}},
          {{"id", desorbed}, {"label", "Desorbed"}, {"color", "#345678"}}
        })}}}}})));
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto revision = project().project()->revision;
  edit_field(4);
  const auto dry_label = "option" + dry + "/label";
  assign(dry_label.c_str(), "Dried");
  assign("field_name", "Sample state");
  const auto up_key = "option" + desorbed + "/up";
  const auto *up = widget(up_key.c_str());
  ASSERT_NE(up, nullptr);
  ASSERT_TRUE(up->enabled && up->on_click);
  const auto same_choice_up = up->on_click;
  same_choice_up(); frame();
  same_choice_up(); frame();  // The retained event must still mean the same choice UUID.
  action("add_field");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, revision + 1);
  const auto &field = project().table()->fields[3];
  EXPECT_EQ(field.id, phase);
  EXPECT_EQ(field.name, "Sample state");
  const auto &choices = field.options.at("choices");
  ASSERT_EQ(choices.size(), 3u);
  EXPECT_EQ(choices[0].at("id"), desorbed);
  EXPECT_EQ(choices[1].at("id"), dry);
  EXPECT_EQ(choices[1].at("label"), "Dried");
  EXPECT_EQ(choices[1].at("color"), "#123456");
  EXPECT_EQ(choices[2].at("id"), wet);
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
  EXPECT_EQ(widget("records")->table->cell(0, 4), "Dried");
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().table()->fields[3].name, "State");
  EXPECT_EQ(project().table()->fields[3].options.at("choices").at(0).at("id"), dry);
  EXPECT_EQ(project().table()->fields[3].options.at("choices").at(0).at("label"), "Dry");
  EXPECT_EQ(*project().table()->cell(0, 3), dry);
}

TEST_F(TableWorkbenchEditorPython, SchemaDraftBlocksEditorCloseAndOldBindingsCannotChangeANewFieldForm)
{
  edit_field(4);
  assign("field_name", "Abandoned state name");
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  const auto old_name = widget("field_name")->string;
  const auto old_type = widget("field_type")->index;
  const auto old_save = widget("add_field")->on_click;
  const auto old_tabs = area().tab_count();
  const auto *editor = &area().editor();
  area().close_tab(area().active_tab());
  frame();
  EXPECT_EQ(area().tab_count(), old_tabs);
  EXPECT_EQ(&area().editor(), editor);
  index("table", 1);
  EXPECT_EQ(project().table_id(), samples);
  send(ui::Event::key_down(ui::Key::Escape));  // Explicitly cancel the field form and its draft.
  ASSERT_FALSE(area().editor().has_unsaved_changes());

  edit_field(1);
  assign("field_name", "Current temperature name");
  const auto revision = project().project()->revision;
  old_name.assign("Stale field name");
  old_type.assign(7);
  old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("field_name"), nullptr);
  EXPECT_EQ(widget("field_name")->string.value(), "Current temperature name");
  EXPECT_EQ(widget("field_type")->index.value(), 2);
  EXPECT_EQ(project().table()->fields[0].name, "Temperature");
  EXPECT_EQ(project().table()->fields[3].name, "State");
  send(ui::Event::key_down(ui::Key::Escape));
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST_F(TableWorkbenchEditorPython, RenamingAnObjectFieldPreservesItsAllowedReferenceKinds)
{
  edit_field(5);
  assign("field_name", "Renamed evidence");
  action("add_field");
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().table()->fields[4].id, evidence);
  EXPECT_EQ(project().table()->fields[4].name, "Renamed evidence");
  EXPECT_EQ(project().table()->fields[4].options.at("kinds"), Json::array({"record", "file"}));
}

TEST_F(TableWorkbenchEditorPython, ClosedViewBuilderCannotSaveOrChangeTheNewBuildersName)
{
  click("table_settings");
  assign("table_view_name", "Abandoned view");
  const auto old_name = widget("table_view_name")->string;
  const auto old_save = widget("table_view_save")->on_click;
  action("table_view_done");
  click("table_settings");
  assign("table_view_name", "Current view");
  const auto revision = project().project()->revision;
  old_name.assign("Stale view name");
  old_save(); frame();
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NE(widget("table_view_name"), nullptr);
  EXPECT_EQ(widget("table_view_name")->string.value(), "Current view");
  action("table_view_discard");
  EXPECT_FALSE(area().editor().has_unsaved_changes());
}

TEST(TableWorkbenchLayout, MalformedSavedViewStateIsRejectedWithoutChangingTheCurrentState)
{
  TableWorkbench workbench;
  const auto initial = workbench.save_state();
  EXPECT_TRUE(workbench.load_state(Json::object()));
  EXPECT_EQ(workbench.save_state(), initial);
  for (const auto &bad_columns : {Json::array({3}), Json::array({{{"field_id", temperature}, {"width", "wide"}, {"hidden", false}}})}) {
    auto invalid = initial;
    invalid["view"]["columns"] = bad_columns;
    EXPECT_FALSE(workbench.load_state(invalid));
    EXPECT_EQ(workbench.save_state(), initial);
  }
  auto invalid = initial;
  invalid["view"]["filters"] = {{"op", "and"}, {"conditions", 3}};
  EXPECT_FALSE(workbench.load_state(invalid));
  EXPECT_EQ(workbench.save_state(), initial);
  EXPECT_TRUE(workbench.load_state(initial));
}
}  // namespace
}  // namespace stk::app
