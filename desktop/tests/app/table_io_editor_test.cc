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

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
const std::string source_table = "e1111111-1111-4111-8111-111111111111";
const std::string count_field = "e2222222-2222-4222-8222-222222222222";
const std::string note_field = "e3333333-3333-4333-8333-333333333333";
const std::string bool_field = "e4444444-4444-4444-8444-444444444444";
const std::string first_row = "e5555555-5555-4555-8555-555555555555";
const std::string null_row = "e6666666-6666-4666-8666-666666666666";
const std::string unset_row = "e7777777-7777-4777-8777-777777777777";

std::string bytes(const std::filesystem::path &path)
{
  std::ifstream stream(path, std::ios::binary);
  return std::string(std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>());
}

class TableIOEditorPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"table-io-editor"};
  wmtest::AppFixture f{"en", 1, 1440, 1200};
  std::unique_ptr<bridge::Client> client;
  std::shared_ptr<const io::Payload> shown;
  uint64_t camera = 0, payload = 0;
  int clicks = 0;
  double clock = 1000;
  ProjectState &project() { return f.shell->store().project(); }
  Editor &editor() { return f.area("a4").editor(); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  bool pump(const std::function<bool()> &predicate)
  {
    return loop.pump_until([&] { frame(); return predicate(); }, 30);
  }
  void click(const char *key)
  {
    const auto *w = widget(key); ASSERT_NE(w, nullptr) << key;
    ASSERT_TRUE(w->enabled) << key;
    ASSERT_FALSE(w->rect.intersect(w->clip).empty()) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    ++clicks; frame();
  }
  void text(const char *key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    f.drv->key(wm::Key::A, wm::ModCtrl | wm::ModOS);
    auto event = ui::Event::text_input(value); event.time = ++clock;
    f.screen.ui()->handle_event(event); frame();
    f.drv->key(wm::Key::Enter); frame();  // Commit the parameter binding, without applying project data.
  }
  void choose(const char *key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    const auto option = "popup/" + std::to_string(index);
    ASSERT_NO_FATAL_FAILURE(click(option.c_str()));
  }
  void close_io()
  {
    f.drv->key(wm::Key::Esc); frame();
    ASSERT_EQ(widget("table_io_format"), nullptr);
  }
  void export_file(int format, const std::filesystem::path &destination)
  {
    ASSERT_NO_FATAL_FAILURE(click("table_export"));
    if (widget("table_io_format")->index.value() != format) { ASSERT_NO_FATAL_FAILURE(choose("table_io_format", format)); }
    ASSERT_NO_FATAL_FAILURE(text("table_csv_destination", core::path_to_utf8(destination)));
    ASSERT_NO_FATAL_FAILURE(click("table_csv_export"));
    ASSERT_TRUE(pump([&] { return !project().busy() && std::filesystem::is_regular_file(destination); }));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  void preview_file(const std::filesystem::path &source)
  {
    ASSERT_NO_FATAL_FAILURE(text("table_csv_source", core::path_to_utf8(source)));
    ASSERT_NO_FATAL_FAILURE(click("table_csv_preview"));
    ASSERT_TRUE(pump([&] { const auto *grid = widget("table_csv_preview_grid"); return grid && grid->table && grid->table->rows == 3; }));
  }
  void expect_viewer()
  {
    auto &viewer = f.shell->store().viewer();
    EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
    EXPECT_EQ(f.screen.maximized(), nullptr);
    EXPECT_EQ(viewer.base_payload(), shown);
    EXPECT_EQ(viewer.payload_serial(), payload);
    EXPECT_EQ(viewer.camera_serial(), camera);
    EXPECT_EQ(viewer.evaluations_started(), 0u);
    EXPECT_TRUE(f.shell->store().scripts().history().empty());
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    f.shell->store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "Synthetic table exchange"));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", source_table}, {"name", "Synthetic measurements"}},
      {{"op", "add_field"}, {"id", count_field}, {"table_id", source_table}, {"name", "Count"}, {"type", "integer"}},
      {{"op", "add_field"}, {"id", note_field}, {"table_id", source_table}, {"name", "Note"}, {"type", "text"}},
      {{"op", "add_field"}, {"id", bool_field}, {"table_id", source_table}, {"name", "Accepted"}, {"type", "boolean"}},
      {{"op", "add_record"}, {"id", first_row}, {"table_id", source_table}},
      {{"op", "add_record"}, {"id", null_row}, {"table_id", source_table}},
      {{"op", "add_record"}, {"id", unset_row}, {"table_id", source_table}},
      {{"op", "set_cell"}, {"table_id", source_table}, {"record_id", first_row}, {"field_id", count_field}, {"value", INT64_MAX}},
      {{"op", "set_cell"}, {"table_id", source_table}, {"record_id", first_row}, {"field_id", note_field}, {"value", "=SUM(A1:A2)"}},
      {{"op", "set_cell"}, {"table_id", source_table}, {"record_id", first_row}, {"field_id", bool_field}, {"value", false}},
      {{"op", "set_cell"}, {"table_id", source_table}, {"record_id", null_row}, {"field_id", count_field}, {"value", nullptr}},
      {{"op", "set_cell"}, {"table_id", source_table}, {"record_id", null_row}, {"field_id", note_field}, {"value", ""}},
    })));
    ASSERT_TRUE(pump([&] { return !project().busy(); }));
    project().select_table(source_table); project().select_record(first_row);
    ASSERT_TRUE(pump([&] { const auto *grid = widget("records"); return grid && grid->table && grid->table->rows == 3; }));
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    auto &viewer = f.shell->store().viewer(); viewer.open_payload(shown, "Existing public synthetic result"); frame();
    camera = viewer.camera_serial(); payload = viewer.payload_serial();
  }
  void TearDown() override
  {
    if (shown) { expect_viewer(); }
    project().attach(nullptr); f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(TableIOEditorPython, DirectEntryExportsThreeFormatsWithRealPointerCountsAndProtectsExistingFiles)
{
  const auto revision = project().project()->revision;
  const std::vector<std::string> extensions = {"csv", "xlsx", "json"};
  for (int format = 0; format < 3; ++format) {
    const auto destination = directory.path() / ("synthetic." + extensions[size_t(format)]);
    clicks = 0;
    ASSERT_NO_FATAL_FAILURE(export_file(format, destination));
    EXPECT_EQ(clicks, format == 0 ? 3 : 5);  // Entry, path focus, Export; format menu adds two clicks.
    const auto contents = bytes(destination); ASSERT_FALSE(contents.empty());
    if (format == 1) { EXPECT_EQ(contents.substr(0, 2), "PK"); }
    if (format == 2) {
      const auto document = Json::parse(contents);
      EXPECT_EQ(document.at("format"), "stk.table");
      EXPECT_EQ(document.at("fields").at(0).at("type"), "integer");
      EXPECT_EQ(document.at("records").at(0).at("values").at(count_field).get<int64_t>(), INT64_MAX);
      ASSERT_NO_FATAL_FAILURE(click("table_csv_export"));
      ASSERT_TRUE(pump([&] { return !project().busy() && !project().error().empty(); }));
      EXPECT_EQ(bytes(destination), contents) << "Export never replaces an existing file";
    }
    EXPECT_EQ(project().project()->revision, revision);
    ASSERT_NO_FATAL_FAILURE(close_io());
  }
}

TEST_F(TableIOEditorPython, CachedExportAndDirectCallsCannotUseADetachedBridgeWithoutAnotherFrame)
{
  const auto destination = directory.path() / "must-not-export.json";
  ASSERT_NO_FATAL_FAILURE(click("table_export"));
  ASSERT_NO_FATAL_FAILURE(choose("table_io_format", 2));
  ASSERT_NO_FATAL_FAILURE(text("table_csv_destination", core::path_to_utf8(destination)));
  ASSERT_NE(widget("table_csv_export"), nullptr);
  const auto stale = widget("table_csv_export")->on_click;
  const auto handle = project().project()->handle;
  const auto revision = project().project()->revision;
  f.shell->store().set_bridge(nullptr);
  // No frame/project.sync runs between detachment and the cached UI callback.
  stale();
  EXPECT_FALSE(project().busy());
  EXPECT_FALSE(std::filesystem::exists(destination));
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_FALSE(project().export_table_file({{"format", "json"}, {"destination", core::path_to_utf8(destination)}}));
  EXPECT_FALSE(project().import_table_file({{"format", "json"}, {"source", core::path_to_utf8(destination)}, {"table_name", "Detached import"}}));
  bool observed = false;
  client->project_snapshot(handle).then([&](bridge::Result<Json> result) {
    ASSERT_TRUE(result) << result.error().describe();
    EXPECT_EQ(io::get_int(result.value().at("project"), "revision", -1), revision);
    observed = true;
  });
  ASSERT_TRUE(loop.pump_until([&] { return observed; }, 30));
  EXPECT_FALSE(std::filesystem::exists(destination));
}

TEST_F(TableIOEditorPython, CachedImportCannotMutateTheDetachedProjectWithoutAnotherFrame)
{
  const auto source = directory.path() / "detached-source.json";
  ASSERT_NO_FATAL_FAILURE(export_file(2, source));
  ASSERT_NO_FATAL_FAILURE(close_io());
  ASSERT_NO_FATAL_FAILURE(click("table_io"));
  ASSERT_NO_FATAL_FAILURE(preview_file(source));
  ASSERT_NO_FATAL_FAILURE(text("table_csv_name", "Must not import"));
  ASSERT_NE(widget("table_csv_import"), nullptr);
  const auto stale = widget("table_csv_import")->on_click;
  const auto handle = project().project()->handle;
  const auto revision = project().project()->revision;
  const auto tables = project().tables().size();
  f.shell->store().set_bridge(nullptr);
  stale();  // Keep the old bridge alive: even a valid old handle must receive no mutation.
  EXPECT_FALSE(project().busy());
  EXPECT_EQ(project().project()->revision, revision);
  bool observed = false;
  client->project_snapshot(handle).then([&](bridge::Result<Json> result) {
    ASSERT_TRUE(result) << result.error().describe();
    const auto &snapshot = result.value();
    EXPECT_EQ(io::get_int(snapshot.at("project"), "revision", -1), revision);
    EXPECT_EQ(snapshot.at("tables").size(), tables);
    observed = true;
  });
  ASSERT_TRUE(loop.pump_until([&] { return observed; }, 30));
}

TEST_F(TableIOEditorPython, JsonPreviewImportPreservesInt64NullUnsetAndBooleanAsOneUndoableEdit)
{
  const auto source = directory.path() / "synthetic.json";
  ASSERT_NO_FATAL_FAILURE(export_file(2, source));
  ASSERT_NO_FATAL_FAILURE(close_io());
  const auto revision = project().project()->revision;
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(click("table_io"));
  ASSERT_NO_FATAL_FAILURE(preview_file(source));
  EXPECT_EQ(clicks, 3);  // Entry, source focus and Preview; JSON is retained from Export.
  EXPECT_EQ(widget("csv_column0/type"), nullptr) << "JSON schema is retained, rather than remapped to text";
  EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 0), "9223372036854775807");
  EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 2), "false");
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_NO_FATAL_FAILURE(click("table_csv_import"));
  EXPECT_EQ(clicks, 4);
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table_id() != source_table; }));
  ASSERT_TRUE(project().error().empty()) << project().error();
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_NE(project().table(), nullptr); ASSERT_EQ(project().table()->records.size(), 3u);
  EXPECT_EQ(project().table()->fields[0].type, "integer");
  EXPECT_EQ(project().table()->cell(0, 0)->get<int64_t>(), INT64_MAX);
  ASSERT_NE(project().table()->cell(1, 0), nullptr); EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
  EXPECT_EQ(project().table()->cell(2, 0), nullptr);
  EXPECT_EQ(*project().table()->cell(0, 1), "=SUM(A1:A2)");
  EXPECT_EQ(*project().table()->cell(1, 1), "");
  EXPECT_EQ(*project().table()->cell(0, 2), false);
  ASSERT_NO_FATAL_FAILURE(click("project_undo"));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().tables().size() == 1; }));
  EXPECT_EQ(project().tables().front().id, source_table);
}

TEST_F(TableIOEditorPython, ExcelPreviewProvidesARealSheetAndExplicitIntegerMappingPreservesPrecision)
{
  const auto source = directory.path() / "synthetic.xlsx";
  ASSERT_NO_FATAL_FAILURE(export_file(1, source));
  ASSERT_NO_FATAL_FAILURE(close_io());
  ASSERT_NO_FATAL_FAILURE(click("table_io"));
  ASSERT_NO_FATAL_FAILURE(preview_file(source));
  ASSERT_NE(widget("table_io_sheet"), nullptr);
  EXPECT_EQ(widget("table_io_sheet")->items.size(), 1u);
  EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 0), "9223372036854775807");
  EXPECT_EQ(widget("table_csv_preview_grid")->table->cell(0, 1), "=SUM(A1:A2)");
  ASSERT_NO_FATAL_FAILURE(choose("csv_column0/type", 1));
  ASSERT_NO_FATAL_FAILURE(text("table_csv_name", "Synthetic Excel import"));
  const auto revision = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(click("table_csv_import"));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().table_id() != source_table; }));
  ASSERT_TRUE(project().error().empty()) << project().error();
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(project().table()->fields[0].type, "integer");
  EXPECT_EQ(project().table()->cell(0, 0)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(*project().table()->cell(0, 1), "=SUM(A1:A2)") << "Formula-looking text remains literal";
}

TEST_F(TableIOEditorPython, ChangedSourceAndFormatMakeAnOldImportActionInert)
{
  const auto source = directory.path() / "synthetic.json";
  ASSERT_NO_FATAL_FAILURE(export_file(2, source));
  ASSERT_NO_FATAL_FAILURE(close_io());
  ASSERT_NO_FATAL_FAILURE(click("table_io"));
  ASSERT_NO_FATAL_FAILURE(preview_file(source));
  ASSERT_NE(widget("table_csv_import"), nullptr);
  auto stale_import = widget("table_csv_import")->on_click;
  const auto revision = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(text("table_csv_source", directory.str() + "/another.json"));
  stale_import(); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().tables().size(), 1u);
  ASSERT_NO_FATAL_FAILURE(text("table_csv_source", core::path_to_utf8(source)));
  ASSERT_NO_FATAL_FAILURE(choose("table_io_format", 1));
  stale_import(); frame();
  EXPECT_FALSE(project().busy()); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().tables().size(), 1u);
}

TEST_F(TableIOEditorPython, WorkspaceRestoreKeepsAnInlineDraftWithoutWritingUntilExplicitSave)
{
  const auto *grid = widget("records"); ASSERT_NE(grid, nullptr); ASSERT_TRUE(grid->table);
  const auto &style = f.screen.ui()->style();
  const float x = grid->rect.x + 2.5f * style.unit + 80.0f;
  const float y = grid->rect.y + style.pixel + 1.5f * style.unit * grid->table->row_height;
  ASSERT_TRUE(f.drv->click(int(x), f.screen.rect().ymax - 1 - int(y))); frame();
  auto event = ui::Event::text_input("301"); event.time = ++clock; f.screen.ui()->handle_event(event); frame();
  const auto revision = project().project()->revision;
  ASSERT_TRUE(editor().has_unsaved_changes());
  const auto saved = editor().save_workspace_state();
  EXPECT_EQ(saved.at("draft").at("text"), "301");
  ASSERT_TRUE(editor().load_workspace_state(saved));
  ASSERT_TRUE(pump([&] { const auto *grid = widget("records"); return grid && grid->table && grid->table->rows == 3; }));
  ASSERT_TRUE(editor().has_unsaved_changes());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 0)->get<int64_t>(), INT64_MAX);
  ASSERT_NO_FATAL_FAILURE(click("table_draft_resume"));
  ASSERT_NE(widget("table_draft_text"), nullptr);
  EXPECT_EQ(widget("table_draft_text")->string.value(), "301");
  ASSERT_TRUE(widget("table_draft_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("table_draft_save"));
  ASSERT_TRUE(pump([&] { return !project().busy() && project().project()->revision == revision + 1; }));
  EXPECT_EQ(*project().table()->cell(0, 0), 301);
  EXPECT_FALSE(editor().has_unsaved_changes());
}

TEST_F(TableIOEditorPython, WorkspaceRestoreKeepsAdvancedFormulaDraftAndCannotExecuteIt)
{
  ASSERT_NO_FATAL_FAILURE(click("table_details"));
  ASSERT_NE(widget("cell_mode"), nullptr);
  ASSERT_NO_FATAL_FAILURE(choose("cell_mode", 2));
  ASSERT_NO_FATAL_FAILURE(text("expression", "base * 2"));
  ASSERT_TRUE(editor().has_unsaved_changes());
  const auto revision = project().project()->revision;
  const auto saved = editor().save_workspace_state();
  EXPECT_EQ(saved.at("advanced").at("expression"), "base * 2");
  ASSERT_TRUE(editor().load_workspace_state(saved));
  ASSERT_TRUE(pump([&] { return widget("expression") != nullptr; }));
  EXPECT_TRUE(editor().has_unsaved_changes());
  ASSERT_NE(widget("expression"), nullptr);
  EXPECT_EQ(widget("expression")->string.value(), "base * 2");
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 0)->get<int64_t>(), INT64_MAX);
}

TEST(TableIOWorkspaceState, ParametersAndAllDraftKindsRoundTripWithoutTransientHandles)
{
  TableWorkbench original;
  auto saved = original.save_workspace_state();
  saved["layout"]["io"]["format"] = "xlsx";
  saved["layout"]["io"]["source"] = "/synthetic/input.xlsx";
  saved["layout"]["io"]["destination"] = "/synthetic/output.xlsx";
  saved["layout"]["io"]["sheet"] = "Thermal history";
  saved["layout"]["io"]["column_types"] = Json::array({2});
  saved["layout"]["io"]["column_units"] = Json::array({"K"});
  saved["parameters"]["filter_value"] = "300";
  saved["parameters"]["view_name_dirty"] = true;
  saved["draft"] = {{"dirty", true}, {"project_id", source_table}, {"record_id", first_row}, {"field_id", count_field}, {"revision", 17}, {"text", "301"}};
  saved["schema"]["dirty"] = true;
  saved["schema"]["field_name"] = "Synthetic modulus";
  saved["schema"]["field_unit"] = "GPa";
  saved["advanced"]["draft_dirty"] = true;
  saved["advanced"]["cell_mode"] = 2;
  saved["advanced"]["expression"] = "base * 2";
  saved["advanced"]["bindings"] = "{\"base\":{\"record_id\":\"synthetic\"}}";
  saved["advanced"]["manage_dirty"] = true;
  saved["advanced"]["rename_table"] = "Synthetic renamed table";
  TableWorkbench restored;
  ASSERT_TRUE(restored.load_workspace_state(saved));
  EXPECT_TRUE(restored.has_unsaved_changes());
  EXPECT_EQ(restored.save_workspace_state(), saved);
  EXPECT_EQ(saved.dump().find("draft_handle"), std::string::npos);
  const auto before = restored.save_workspace_state();
  saved["layout"]["io"]["column_types"][0] = 999;
  EXPECT_FALSE(restored.load_workspace_state(saved));
  EXPECT_EQ(restored.save_workspace_state(), before) << "Invalid imported state cannot partially replace a draft";
  saved = before; saved["advanced"]["sweep"][0]["kind"] = -1;
  EXPECT_FALSE(restored.load_workspace_state(saved));
  EXPECT_EQ(restored.save_workspace_state(), before);
}

}  // namespace
}  // namespace stk::app
