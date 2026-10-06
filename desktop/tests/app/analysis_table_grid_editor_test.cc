/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_analyses.hh"
#include "stk/app/project_analysis_runs.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include "scalar_volume_support.hh"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <thread>
#include <chrono>

namespace stk::app {
namespace {
using io::Json;
using Reply = bridge::Result<Json>;
namespace fs = std::filesystem;
constexpr const char *run_id = "34603d22-b2c8-4870-84e6-11b95b529fed";
constexpr const char *second_run_id = "55603d22-b2c8-4870-84e6-11b95b529fed";
constexpr const char *analysis_id = "48603d22-b2c8-4870-84e6-11b95b529fed";
std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }
constexpr const char *kAnalysisBridge = R"PY(
import hashlib
import json
from pathlib import Path
import sys
import threading
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
from suan.desktop_bridge.protocol import encode_message
control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run = Bridge._run
def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}) + '\n')
    return original_run(self, identity, method, params)
Bridge._run = run
original_send = Bridge.send
def send(self, message, method=None):
    if method == 'project.analysis_runs.result' and 'result' in message:
        mode = (control / 'mode').read_text() if (control / 'mode').exists() else ''
        envelope = message['result']
        record, result = envelope['run'], envelope['result']
        table = None
        if mode == 'paged':
            names = ['9', '0', '科学', 'a/b~c'] + [f'col{i}' for i in range(4, 16)]
            table = {'type': 'table', 'column_names': names,
                     'columns': {name: [row * 100 + col for row in range(128)] for col, name in enumerate(names)},
                     'units': {names[9]: 'Pa'}}
        elif mode == 'types':
            values = [18446744073709551615, -9223372036854775808, 1.0, -0.0, None, 'null', '',
                      'NaN', 'Inf', '-Inf', [1, 1.0], {'a/b~c': None}]
            table = {'type': 'table', 'column_names': ['exact', 'unitless'],
                     'columns': {'exact': values, 'unitless': values}, 'units': {'unitless': 'unspecified'}}
        elif mode == 'long':
            name, unit, value = '科学' * 1500, '单位' * 1500, '科学\n' * 2500
            table = {'type': 'table', 'column_names': [name], 'columns': {name: [value]}, 'units': {name: unit}}
        elif mode == 'malformed':
            table = {'type': 'table', 'column_names': ['a', 'b'], 'columns': {'a': [1], 'b': [2, 3]}, 'units': {}}
        elif mode == 'blob':
            table = {'type': 'table', 'blob': 'a' * 64, 'media_type': 'application/json',
                     'size': 1024, 'rows': 12, 'column_names': ['blob-only']}
        elif mode == 'empty':
            table = {'type': 'table', 'column_names': [], 'columns': {}, 'units': {}}
        if table is not None:
            result['outputs']['table'] = table
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            record['result']['manifest_sha256'] = hashlib.sha256(raw).hexdigest()
            record['result']['size_bytes'] = len(raw) + 1024
    return original_send(self, message, method)
Bridge.send = send
main()
)PY";

class AnalysisTableGridEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-table-grid-ui"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1700};
  std::unique_ptr<bridge::Client> client;
  Json document, snapshot, frozen;
  std::string file_id;
  int64_t revision = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  ViewerState &viewer() { return store().viewer(); }
  EditorArea &area() { return f.area("a2"); }
  std::string handle() { return project().project()->handle; }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  Json calls(const std::string &method) {
    Json result = Json::array(); std::ifstream file(directory.path() / "calls.jsonl"); std::string line;
    while (std::getline(file, line)) { auto item = io::parse_json(line); if (item.at("method") == method) { result.push_back(item.at("params")); } }
    return result;
  }
  void call(const std::string &method, Json params, Json &out) {
    auto reply = std::make_shared<std::optional<Reply>>(); auto future = client->call(method, std::move(params));
    future.then([reply](auto value) { *reply = std::move(value); });
    const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
    if (!done) { future.cancel(); }
    ASSERT_TRUE(done) << client->bridge_log().text();
    ASSERT_TRUE(reply->value().ok()) << reply->value().error().describe(); out = reply->value().value();
  }
  void read(Json &out) { ASSERT_NO_FATAL_FAILURE(call("project.analyses.get", {{"handle", handle()}, {"analysis_id", analysis_id}}, out)); }
  void frames_until(const std::function<bool()> &condition) {
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return condition(); }, 30)) << client->bridge_log().text();
  }
  void click(const char *key) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled); ASSERT_TRUE(value->on_click);
    value->on_click(); f.drv->frame();
  }
  void row(const std::string &key) {
    const auto *value = widget("analysis_parameters"); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled);
    const auto spec = *value->table; int selected = -1;
    for (int index = 0; index < spec.rows; ++index) { if (spec.cell(index, 0) == (key.empty() ? "\"\"" : key)) { selected = index; } }
    ASSERT_GE(selected, 0); spec.selected.assign(selected); f.drv->frame();
    ASSERT_NE(widget("analysis_parameter_value"), nullptr);
  }
  void type_field(const char *key, const std::string &text, const bool finish = true) {
    const auto *input = widget(key); ASSERT_NE(input, nullptr); ASSERT_TRUE(input->enabled);
    const auto [x, y] = f.widget_center(input->key); f.drv->click(x, y);
#ifdef __APPLE__
    constexpr auto primary = wm::ModOS;
#else
    constexpr auto primary = wm::ModCtrl;
#endif
    f.drv->key(wm::Key::A, primary);
    f.drv->key(wm::Key::BackSpace);
    if (!text.empty()) { f.drv->key(wm::Key::Unknown, wm::ModNone, text); }
    f.drv->frame(); ASSERT_TRUE(f.screen.ui()->text_input_active());
    ASSERT_EQ(f.screen.ui()->edit_state()->text(), text);
    if (finish) { f.drv->key(wm::Key::Enter); f.drv->frame(); ASSERT_FALSE(f.screen.ui()->text_input_active()); }
  }
  void type(const std::string &text, const bool finish = true) { type_field("analysis_parameter_value", text, finish); }
  void edit(const std::string &name, const std::string &value) {
    ASSERT_NO_FATAL_FAILURE(row(name));
    ASSERT_NO_FATAL_FAILURE(type(value));
    ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  }
  void toggle(const char *key) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr);
    const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
    f.screen.ui()->handle_event(ui::Event::mouse_down(center));
    f.screen.ui()->handle_event(ui::Event::mouse_up(center)); f.drv->frame();
  }
  void prepare(const std::string &id, Json &out) {
    Json response;
    ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.prepare", {{"handle", handle()}, {"run_id", id},
        {"analysis_id", analysis_id}, {"snapshot_id", snapshot.at("id")},
        {"bindings", {{"data", {{"stats.csv", file_id}}}}}, {"expected_revision", revision}}, response));
    out = response.at("run");
  }
  void choose_mode(const int mode) {
    ASSERT_NE(widget("graph_mode"), nullptr); widget("graph_mode")->index.assign(mode); f.drv->frame();
    ASSERT_EQ(widget("graph_mode")->index.value(), mode);
  }
  void run_list() {
    ASSERT_NO_FATAL_FAILURE(choose_mode(2));
    ASSERT_NE(widget("analysis_saved_section"), nullptr);
    widget("analysis_saved_section")->index.assign(1); f.drv->frame();
    if (!widget("analysis_run_list")) { ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_history")); }
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_list"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_rows") && widget("analysis_run_rows")->enabled; }));
  }
  void select_run(const std::string &id) {
    ASSERT_NE(widget("analysis_run_rows"), nullptr); const auto table = *widget("analysis_run_rows")->table;
    int row = -1;
    for (int i = 0; i < table.rows; ++i) { if (table.cell(i, 2) == id.substr(0, 8)) { row = i; } }
    ASSERT_GE(row, 0); table.selected.assign(row);
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_inspect") && widget("analysis_run_inspect")->enabled; }));
  }
  void inspect() {
    ASSERT_NO_FATAL_FAILURE(run_list());
    ASSERT_NO_FATAL_FAILURE(select_run(run_id));
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
    ASSERT_EQ(widget("graph_mode")->index.value(), 3);
  }
  void frozen_parameters() {
    if (!widget("graph_parameter_values")) { ASSERT_NO_FATAL_FAILURE(toggle("graph_parameters")); }
    ASSERT_NE(widget("graph_parameter_values"), nullptr);
  }
  std::string cell(const char *table_key, const std::string &name, const int col = 1) {
    const auto *value = widget(table_key);
    if (!value || !value->table) { ADD_FAILURE() << "Missing table " << table_key; return {}; }
    for (int i = 0; i < value->table->rows; ++i) { if (value->table->cell(i, 0) == name) { return value->table->cell(i, col); } }
    ADD_FAILURE() << "Missing row " << name; return {};
  }
  void SetUp() override {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const auto *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for parameter editing"; }
    { std::ofstream file(directory.path() / "bridge.py"); file << kAnalysisBridge; ASSERT_TRUE(file.good()); }
    bridge::ClientOptions options;
    options.python.configured = python; options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime"; options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), directory.str(), "--stdio",
        "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    options.executor = loop.executor(); options.strict = options.validate = true; options.call_timeout_s = 30;
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    viewer().set_auto_evaluate(false); viewer().prefetch_neighbours = false;
    ASSERT_TRUE(project().create(directory.str() + "/project", "Parameter edits"));
    ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
    { std::ofstream file(directory.path() / "stats.csv"); file << "step,temperature\n0,-9.5\n1,0.0\n2,14.5\n"; ASSERT_TRUE(file.good()); }
    Json indexed, captured, saved;
    ASSERT_NO_FATAL_FAILURE(call("project.files.index", {{"handle", handle()}, {"expected_revision", 0},
        {"paths", Json::array({core::path_to_utf8(directory.path() / "stats.csv")})}}, indexed));
    file_id = indexed.at("record_ids")[0].get<std::string>();
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()}, {"expected_revision", indexed.at("revision")},
        {"record_ids", Json::array({file_id})}}, captured)); snapshot = captured.at("snapshot");
    auto graph = io::parse_json(R"JSON({
  "schema": "stk.graph/1",
  "id": "result-inspection",
  "nodes": [
    {
      "id": "table",
      "type": "stk.source.table@1",
      "params": {
        "binding": "data",
        "path": "stats.csv",
        "format": "csv",
        "units": {
          "temperature": "K"
        }
      }
    },
    {
      "id": "missing",
      "type": "stk.source.table@1",
      "params": {
        "binding": "data",
        "path": "absent.csv",
        "format": "csv"
      }
    }
  ],
  "outputs": {
    "table": "table.out",
    "missing": "missing.out"
  }
})JSON");
    graph["parameters"] = Json::array({{{"name", "probe"}, {"type", "number"}, {"default", 1.0}}});
    document = {{"format", "stk.analysis-document/1"}, {"graph", graph},
        {"parameters", {{"probe", 1.0}}}, {"outputs", Json::array({"table", "missing"})}};
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", analysis_id},
        {"name", "Original analysis"}, {"document", document}, {"expected_revision", captured.at("revision")}}, saved));
    revision = saved.at("revision").get<int64_t>();
    ASSERT_NO_FATAL_FAILURE(prepare(run_id, frozen));
    ASSERT_NO_FATAL_FAILURE(execute(run_id, frozen));
    ASSERT_EQ(frozen.at("status"), "failed") << frozen.dump(2);
    ASSERT_TRUE(frozen.at("result").is_object()) << frozen.dump(2);
    ASSERT_TRUE(frozen.at("result").at("has_errors").get<bool>());
    project().refresh();
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(area().set_tab_type(0, kEditorAnalysisGraph)); ASSERT_TRUE(area().editor().load_state({{"saved", true}}));
    f.screen.set_maximized(&area()); area().find_region(EditorArea::kSidebar)->set_size_1x(510); f.drv->frame();
    ASSERT_NO_FATAL_FAILURE(click("analysis_list"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_documents") != nullptr; }));
    widget("analysis_documents")->table->selected.assign(0);
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters") != nullptr; }));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return store().scripts().ready() && store().scripts().desktop_ready() &&
        io::get_int(store().scripts().status(), "cursor", -1) >= 0; }));
  }
  void mode(const std::string &value) { std::ofstream stream(directory.path() / "mode"); stream << value; ASSERT_TRUE(stream.good()); }
  void release() {
    { std::ofstream stream(directory.path() / "release"); stream << "ready"; }
    ASSERT_NO_FATAL_FAILURE(mode(""));
  }
  void execute(const std::string &id, Json &out) {
    ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.start", {{"handle", handle()}, {"run_id", id}}, out));
    for (int attempt = 0; attempt < 300; ++attempt) {
      Json value;
      ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", id}}, value));
      const auto status = io::get_string(value.at("run"), "status");
      if (status == "succeeded" || status == "failed") { out = value.at("run"); return; }
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    FAIL() << "Analysis did not settle";
  }
  void select_original() {
    ASSERT_NO_FATAL_FAILURE(run_list());
    ASSERT_NO_FATAL_FAILURE(select_run(run_id));
  }
  void read_result() {
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_result_outputs") != nullptr; }));
  }
  void select(const char *key, const std::string &label) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled); ASSERT_TRUE(value->table);
    const auto table = *value->table; int row = -1;
    for (int index = 0; index < table.rows; ++index) { if (table.cell(index, 0) == label) { row = index; } }
    ASSERT_GE(row, 0) << label; table.selected.assign(row); f.drv->frame();
  }
  void property(const std::string &key, const bool open = false) {
    ASSERT_NO_FATAL_FAILURE(select("analysis_result_properties", io::python_json_dumps(Json(key), false, true)));
    if (open) { ASSERT_NO_FATAL_FAILURE(click("analysis_result_open")); }
  }
  std::string paragraph(const std::string &scope) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.key.find("/" + scope + "/") != std::string::npos && item.type == ui::WidgetType::Paragraph) { return item.text; }
      }
    }
    return {};
  }
  void grid(const std::string &fixture = "") {
    ASSERT_NO_FATAL_FAILURE(mode(fixture));
    ASSERT_NO_FATAL_FAILURE(select_original());
    ASSERT_NO_FATAL_FAILURE(read_result());
    ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
    ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
    ASSERT_NE(widget("analysis_table_grid"), nullptr);
  }
  void grid_row(int row) {
    ASSERT_NE(widget("analysis_table_grid"), nullptr);
    widget("analysis_table_grid")->table->selected.assign(row); f.drv->frame();
    ASSERT_EQ(widget("analysis_table_grid")->table->selected.value(), row);
  }
  void grid_column(int column) {
    ASSERT_NE(widget("analysis_table_grid_column"), nullptr);
    widget("analysis_table_grid_column")->index.assign(column); f.drv->frame();
    ASSERT_EQ(widget("analysis_table_grid_column")->index.value(), column);
  }
  void jump(const std::string &row, const std::string &column) {
    ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_row", row));
    ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_column", column));
    ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_jump"));
  }
  bool has_text(const std::string_view text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text == text) { return true; } }
    }
    return false;
  }
  std::string all_pages(const std::string &scope) {
    std::string combined = paragraph(scope), next = scope == "analysis_result_path_text" ? "analysis_result_path_next" : scope + "_next";
    for (int page = 0; widget(next.c_str()) && widget(next.c_str())->enabled && page < 1000; ++page) {
      const auto callback = widget(next.c_str())->on_click; callback(); f.drv->frame(); combined += paragraph(scope);
    }
    return combined;
  }
  void TearDown() override {
    { std::ofstream stream(directory.path() / "release"); stream << "ready"; }
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating()); EXPECT_FALSE(viewer().payload());
    EXPECT_TRUE(calls("graph.evaluate").empty());

    EXPECT_TRUE(calls("project.snapshots.resolve").empty());

    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisTableGridEditorPython, RealPartialCsvRequiresExplicitGridAndExposesExactCellWithoutFurtherCalls)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  EXPECT_EQ(widget("analysis_result_table_grid"), nullptr);
  ASSERT_NO_FATAL_FAILURE(read_result());
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  ASSERT_NE(widget("analysis_table_grid"), nullptr);
  const auto table = *widget("analysis_table_grid")->table;
  EXPECT_EQ(table.rows, 3); ASSERT_EQ(table.columns.size(), 3u);
  EXPECT_EQ(table.cell(0, 0), "0"); EXPECT_EQ(table.cell(0, 2), "-9.5");
  EXPECT_EQ(table.cell(1, 2), "0.0"); EXPECT_EQ(table.cell(2, 2), "14.5");
  EXPECT_FALSE(widget("analysis_table_grid_rows_next")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_columns_next")->enabled);
  ASSERT_NO_FATAL_FAILURE(grid_column(1));
  ASSERT_NO_FATAL_FAILURE(grid_row(1));
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"temperature\"");
  EXPECT_EQ(paragraph("analysis_table_grid_unit"), "\"K\"");
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "0.0");
  EXPECT_TRUE(has_text("Source row 1 · column 1"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_open_cell"));
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table/columns/temperature/1");
  EXPECT_EQ(paragraph("analysis_result_scalar_text"), "0.0");
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_properties_view"));
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table");
  EXPECT_EQ(client->stats().calls_sent, sent); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisTableGridEditorPython, IndependentPagesKeepAbsoluteIdentityAndRejectRetainedRoundTripCallbacks)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto old_rows = widget("analysis_table_grid")->table->selected;
  const auto old_column = widget("analysis_table_grid_column")->index;
  const auto old_next = widget("analysis_table_grid_rows_next")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_columns_next"));
  ASSERT_NO_FATAL_FAILURE(grid_column(1));
  ASSERT_NO_FATAL_FAILURE(grid_row(1));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "109");
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"col9\"");
  EXPECT_EQ(paragraph("analysis_table_grid_unit"), "\"Pa\"");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_next"));
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), -1);
  EXPECT_EQ(widget("analysis_table_grid_column")->index.value(), 0);
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "");
  ASSERT_NO_FATAL_FAILURE(grid_column(1));
  ASSERT_NO_FATAL_FAILURE(grid_row(1));
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(1, 0), "65");
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "6509");
  EXPECT_TRUE(has_text("Source row 65 · column 9"));
  old_rows.assign(2); old_column.assign(3); old_next(); f.drv->frame();
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "6509");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_previous"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_columns_previous"));
  old_rows.assign(2); old_column.assign(3); old_next(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), -1);
  EXPECT_EQ(widget("analysis_table_grid_column")->index.value(), 0);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisTableGridEditorPython, HeaderClicksCannotSortSourceRowsOrChangeAuthoritativeColumnOrder)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto table = *widget("analysis_table_grid")->table;
  for (const auto &column : table.columns) { EXPECT_FALSE(column.sortable); }
  EXPECT_NE(table.columns.at(1).title.find("\"9\""), std::string::npos);
  EXPECT_NE(table.columns.at(2).title.find("\"0\""), std::string::npos);
  const auto unit = f.screen.ui()->style().unit;
  for (const float x_offset : {2.0f, 7.0f}) {
    const auto rect = widget("analysis_table_grid")->rect;
    const ui::Vec2 header{rect.x + 1 + x_offset * unit, rect.y + 1 + 0.5f * unit};
    f.screen.ui()->handle_event(ui::Event::mouse_down(header));
    f.screen.ui()->handle_event(ui::Event::mouse_up(header)); f.drv->frame();
  }
  const auto bounds = widget("analysis_table_grid")->rect;
  const ui::Vec2 first{bounds.x + 10, bounds.y + 1 + 1.5f * unit};
  f.screen.ui()->handle_event(ui::Event::mouse_down(first));
  f.screen.ui()->handle_event(ui::Event::mouse_up(first)); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), 0);
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "0");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_next"));
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "64");
  ASSERT_NO_FATAL_FAILURE(grid_row(0));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "6400");
}

TEST_F(AnalysisTableGridEditorPython, ExactTypedCellsAndCompoundPathsNeverNormalizeScientificValues)
{
  ASSERT_NO_FATAL_FAILURE(grid("types"));
  const std::vector<std::string> expected{"18446744073709551615", "-9223372036854775808", "1.0", "-0.0",
      "null", "\"null\"", "\"\"", "\"NaN\"", "\"Inf\"", "\"-Inf\""};
  for (size_t index = 0; index < expected.size(); ++index) {
    ASSERT_NO_FATAL_FAILURE(grid_row(int(index)));
    EXPECT_EQ(paragraph("analysis_table_grid_value"), expected[index]);
  }
  EXPECT_TRUE(has_text(store().tr("analysis_table_grid.unit_missing")));
  ASSERT_NO_FATAL_FAILURE(grid_column(1));
  EXPECT_EQ(paragraph("analysis_table_grid_unit"), "\"unspecified\"");
  ASSERT_NO_FATAL_FAILURE(grid_row(10));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_open_cell"));
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table/columns/unitless/10");
  EXPECT_EQ(cell("analysis_result_properties", "0"), "1");
  EXPECT_EQ(cell("analysis_result_properties", "1"), "1.0");
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  ASSERT_NO_FATAL_FAILURE(grid_row(11));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_open_cell"));
  ASSERT_NO_FATAL_FAILURE(property("a/b~c", true));
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table/columns/exact/11/a~1b~0c");
  EXPECT_EQ(paragraph("analysis_result_scalar_text"), "null");
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisTableGridEditorPython, FullColumnNameUnitAndScalarRemainReachableBeyondPreviewAndTextPages)
{
  ASSERT_NO_FATAL_FAILURE(grid("long"));
  ASSERT_NO_FATAL_FAILURE(grid_row(0));
  std::string name, unit, value;
  for (int index = 0; index < 1500; ++index) { name += "科学"; unit += "单位"; }
  for (int index = 0; index < 2500; ++index) { value += "科学\n"; }
  EXPECT_EQ(all_pages("analysis_table_grid_name"), io::python_json_dumps(Json(name), false, true));
  EXPECT_EQ(all_pages("analysis_table_grid_unit"), io::python_json_dumps(Json(unit), false, true));
  EXPECT_EQ(all_pages("analysis_table_grid_value"), io::python_json_dumps(Json(value), false, true));
  EXPECT_LT(widget("analysis_table_grid")->table->columns.at(1).title.size(), 600u);
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_open_cell"));
  EXPECT_EQ(all_pages("analysis_result_path_text"), "/outputs/table/columns/" + name + "/0");
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisTableGridEditorPython, MalformedInlineTableRetainsHonestPropertiesFallback)
{
  ASSERT_NO_FATAL_FAILURE(mode("malformed"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table");
  ASSERT_NE(widget("analysis_result_properties"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_properties_view"));
  ASSERT_NO_FATAL_FAILURE(property("columns", true));
  ASSERT_NO_FATAL_FAILURE(property("b", true));
  EXPECT_EQ(widget("analysis_result_properties")->table->rows, 2);
  EXPECT_EQ(cell("analysis_result_properties", "1"), "3");
  EXPECT_EQ(client->stats().calls_sent, sent);
}

TEST_F(AnalysisTableGridEditorPython, BlobTableIsMetadataOnlyAndMissingOutputCannotReusePriorGrid)
{
  ASSERT_NO_FATAL_FAILURE(mode("blob"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  EXPECT_TRUE(has_text(store().tr("analysis_results.not_loaded")));
  ASSERT_NE(widget("analysis_result_table_grid"), nullptr);
  EXPECT_FALSE(widget("analysis_result_table_grid")->enabled);
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(property("blob"));
  EXPECT_EQ(paragraph("analysis_result_scalar_text"), "\"" + std::string(64, 'a') + "\"");
  const auto old_open = widget("analysis_result_table_grid")->on_click;
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "missing"));
  old_open(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  EXPECT_EQ(widget("analysis_result_properties"), nullptr);
  EXPECT_EQ(client->stats().calls_sent, sent);
}

TEST_F(AnalysisTableGridEditorPython, EmptyInlineTableShowsNoRowsWithoutInventingCellsOrUnits)
{
  ASSERT_NO_FATAL_FAILURE(grid("empty"));
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 0);
  EXPECT_EQ(widget("analysis_table_grid")->table->columns.size(), 1u);
  EXPECT_TRUE(has_text(store().tr("analysis_table_grid.empty")));
  EXPECT_FALSE(widget("analysis_table_grid_column")->enabled);
  ASSERT_NE(widget("analysis_table_grid_jump_row"), nullptr);
  ASSERT_NE(widget("analysis_table_grid_jump_column"), nullptr);
  ASSERT_NE(widget("analysis_table_grid_jump"), nullptr);
  EXPECT_FALSE(widget("analysis_table_grid_jump_row")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_jump_column")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_jump")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_rows_next")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_columns_next")->enabled);
  EXPECT_EQ(widget("analysis_table_grid_open_cell"), nullptr);
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "");
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_properties_view"));
  ASSERT_NO_FATAL_FAILURE(property("columns", true));
  EXPECT_EQ(widget("analysis_result_properties")->table->rows, 0);
}

TEST_F(AnalysisTableGridEditorPython, RetainedGridCallbacksCannotOverrideNewSourceSectionOutputOrArchive)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto old_row = widget("analysis_table_grid")->table->selected;
  const auto old_page = widget("analysis_table_grid_rows_next")->on_click;
  const auto old_column = widget("analysis_table_grid_column")->index;
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  old_row.assign(1); old_column.assign(1); old_page(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), -1);
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  const auto old_activate = widget("analysis_result_table_grid")->on_click;
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "missing"));
  old_activate(); f.drv->frame(); EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  const auto old_again = widget("analysis_table_grid_rows_next")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_read_result")->enabled; }));
  old_again(); f.drv->frame(); EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 2u);
}

TEST_F(AnalysisTableGridEditorPython, SavedDirtyParametersAndInvalidTextSurviveIndependentGridBrowsing)
{
  ASSERT_NO_FATAL_FAILURE(edit("probe", "2.0"));
  ASSERT_NO_FATAL_FAILURE(type("1e"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(grid());
  ASSERT_NO_FATAL_FAILURE(grid_column(1));
  ASSERT_NO_FATAL_FAILURE(grid_row(2));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "14.5");
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  EXPECT_EQ(cell("analysis_parameters", "probe"), "2.0");
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisTableGridEditorPython, ActiveTextInAnotherInstalledWindowFencesRowColumnAndPageActions)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto old_row = widget("analysis_table_grid")->table->selected;
  const auto old_column = widget("analysis_table_grid_column")->index;
  const auto old_next = widget("analysis_table_grid_rows_next")->on_click;
  struct ExtraScreen {
    AppShell &shell; wm::Screen screen; wmtest::ScreenDriver driver;
    explicit ExtraScreen(AppShell &owner) : shell(owner), driver(screen, 1280, 1000, 1) {
      shell.install(screen, nullptr); shell.build_default_layout(screen);
    }
    ~ExtraScreen() { shell.forget(screen); }
  } extra(*f.shell);
  auto *target = dynamic_cast<EditorArea *>(extra.screen.find_area("a2")); ASSERT_NE(target, nullptr);
  ASSERT_TRUE(target->set_tab_type(0, kEditorProject)); ASSERT_TRUE(target->editor().show_view("review"));
  extra.screen.set_maximized(target); extra.driver.frame(); loop.run_ready(); extra.driver.frame();
  if (const auto *json = extra.screen.ui()->find("a2/main/review_json")) {  // The JSON editor is folded away.
    const auto header = json->rect;
    extra.driver.click(int(header.cx()), extra.screen.rect().ymax - 1 - int(header.cy())); extra.driver.frame();
  }
  const auto *input = extra.screen.ui()->find("a2/main/review_json/review_source"); ASSERT_NE(input, nullptr);
  const auto rect = input->rect;
  extra.driver.click(int(rect.cx()), extra.screen.rect().ymax - 1 - int(rect.cy()));
  extra.driver.key(wm::Key::Unknown, wm::ModNone, " pending text");
  ASSERT_TRUE(extra.screen.ui()->text_input_active()); const auto typed = extra.screen.ui()->edit_state()->text();
  old_row.assign(1); old_column.assign(1); old_next(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), -1);
  EXPECT_EQ(widget("analysis_table_grid_column")->index.value(), 0);
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), typed);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  extra.driver.key(wm::Key::Enter, primary); extra.driver.frame();
  ASSERT_FALSE(f.shell->text_input_active());
  old_next(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "64");
}

TEST_F(AnalysisTableGridEditorPython, DestroyedEditorAndReopenedProjectCannotReuseRetainedGridCallbacks)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto old_row = widget("analysis_table_grid")->table->selected;
  const auto old_next = widget("analysis_table_grid_rows_next")->on_click;
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().loaded() && !project().busy(); }));
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  old_row.assign(1); old_next(); f.drv->frame(); EXPECT_EQ(widget("analysis_table_grid"), nullptr);
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs)); f.drv->frame();
  const auto sent = client->stats().calls_sent;
  old_row.assign(1); old_next(); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorLogs); EXPECT_EQ(client->stats().calls_sent, sent);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}
TEST_F(AnalysisTableGridEditorPython, JumpCommitsBothKeyboardFieldsWithTabAndFirstGoSelectsOriginalCoordinates)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto sent = client->stats().calls_sent;
  const auto retained_go = widget("analysis_table_grid_jump")->on_click;
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_row", "72", false));
  EXPECT_FALSE(widget("analysis_table_grid_jump")->enabled);
  retained_go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  // Tab commits row and focuses column before another frame can rebuild its setter.
  f.drv->key(wm::Key::Tab); f.drv->frame();
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  ASSERT_EQ(f.screen.ui()->editing(), widget("analysis_table_grid_jump_column")->id);
  f.drv->key(wm::Key::Unknown, wm::ModNone, "9");
  f.drv->key(wm::Key::Enter); f.drv->frame();
  ASSERT_FALSE(f.screen.ui()->text_input_active());
  EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), "72");
  EXPECT_EQ(widget("analysis_table_grid_jump_column")->string.value(), "9");
  retained_go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_jump"));
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 56);
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "72");
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), 0);
  EXPECT_EQ(widget("analysis_table_grid_column")->index.value(), 0);
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "7209");
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"col9\"");
  EXPECT_TRUE(has_text("Source row 72 · column 9"));
  EXPECT_EQ(client->stats().calls_sent, sent); EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(AnalysisTableGridEditorPython, JumpUsesExactWindowStartIncludingEndZeroAndRelativePreviousPages)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  ASSERT_NO_FATAL_FAILURE(jump("127", "15"));
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 1);
  EXPECT_EQ(widget("analysis_table_grid")->table->columns.size(), 2u);
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "12715");
  EXPECT_FALSE(widget("analysis_table_grid_rows_next")->enabled);
  EXPECT_FALSE(widget("analysis_table_grid_columns_next")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_previous"));
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "63");
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), -1);
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_columns_previous"));
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"col7\"");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_next"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_columns_next"));
  ASSERT_NO_FATAL_FAILURE(grid_row(0));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "12715");
  ASSERT_NO_FATAL_FAILURE(jump("3", "2"));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "302");
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_previous"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_columns_previous"));
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"9\"");
  ASSERT_NO_FATAL_FAILURE(jump("0", "0"));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "0");
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 64);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisTableGridEditorPython, InvalidJumpTextAndBoundsKeepTheExactPageAndSelectionForCorrection)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  ASSERT_NO_FATAL_FAILURE(jump("72", "9"));
  const auto sent = client->stats().calls_sent;
  const std::vector<std::pair<std::string, std::string>> invalid{
      {"", "9"}, {"-1", "9"}, {"+1", "9"}, {"1.5", "9"}, {"1e2", "9"},
      {" 1", "9"}, {"１", "9"}, {"18446744073709551616", "9"},
      {std::string(21, '0'), "9"}, {"128", "9"}, {"72", "16"}, {"72", "-1"}};
  for (const auto &[row, column] : invalid) {
    SCOPED_TRACE(row + "/" + column);
    ASSERT_NO_FATAL_FAILURE(jump(row, column));
    EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), row);
    EXPECT_EQ(widget("analysis_table_grid_jump_column")->string.value(), column);
    EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "72");
    EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), 0);
    EXPECT_EQ(paragraph("analysis_table_grid_value"), "7209");
    EXPECT_TRUE(has_text(store().tr("analysis_table_grid.jump_invalid")));
  }
  ASSERT_NO_FATAL_FAILURE(jump("73", "10"));
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "7310");
  EXPECT_FALSE(has_text(store().tr("analysis_table_grid.jump_invalid")));
  EXPECT_EQ(client->stats().calls_sent, sent);
}

TEST_F(AnalysisTableGridEditorPython, RetainedJumpActionsAndSettersCannotOverrideNewTextPageNavigationOrArchive)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  const auto old_row = widget("analysis_table_grid_jump_row")->string;
  const auto old_go = widget("analysis_table_grid_jump")->on_click;
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_row", "72"));
  old_row.assign("127"); old_go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), "72");
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_column", "9"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_jump"));
  const auto before_page_row = widget("analysis_table_grid_jump_row")->string;
  const auto before_page_go = widget("analysis_table_grid_jump")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_rows_previous"));
  before_page_row.assign("127"); before_page_go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), "72");
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "8");
  const auto before_navigation = widget("analysis_table_grid_jump_column")->string;
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  before_navigation.assign("15"); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid_jump_column")->string.value(), "9");
  const auto before_archive = widget("analysis_table_grid_jump_row")->string;
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_read_result")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  before_archive.assign("127"); old_go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), "0");
  EXPECT_EQ(widget("analysis_table_grid_jump_column")->string.value(), "0");
  const auto destroyed_go = widget("analysis_table_grid_jump")->on_click;
  const auto destroyed_row = widget("analysis_table_grid_jump_row")->string;
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs)); f.drv->frame();
  const auto sent = client->stats().calls_sent;
  destroyed_row.assign("12"); destroyed_go(); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorLogs); EXPECT_EQ(client->stats().calls_sent, sent);
}

TEST_F(AnalysisTableGridEditorPython, CommittedJumpTextSurvivesAnotherWindowInputButGoWaitsUntilItFinishes)
{
  ASSERT_NO_FATAL_FAILURE(grid("paged"));
  struct ExtraScreen {
    AppShell &shell; wm::Screen screen; wmtest::ScreenDriver driver;
    explicit ExtraScreen(AppShell &owner) : shell(owner), driver(screen, 1280, 1000, 1) {
      shell.install(screen, nullptr); shell.build_default_layout(screen);
    }
    ~ExtraScreen() { shell.forget(screen); }
  } extra(*f.shell);
  auto *target = dynamic_cast<EditorArea *>(extra.screen.find_area("a2")); ASSERT_NE(target, nullptr);
  ASSERT_TRUE(target->set_tab_type(0, kEditorProject)); ASSERT_TRUE(target->editor().show_view("review"));
  extra.screen.set_maximized(target); extra.driver.frame(); loop.run_ready(); extra.driver.frame();
  if (const auto *json = extra.screen.ui()->find("a2/main/review_json")) {  // The JSON editor is folded away.
    const auto header = json->rect;
    extra.driver.click(int(header.cx()), extra.screen.rect().ymax - 1 - int(header.cy())); extra.driver.frame();
  }
  const auto *input = extra.screen.ui()->find("a2/main/review_json/review_source"); ASSERT_NE(input, nullptr);
  const auto rect = input->rect;
  extra.driver.click(int(rect.cx()), extra.screen.rect().ymax - 1 - int(rect.cy()));
  extra.driver.key(wm::Key::Unknown, wm::ModNone, " pending text");
  ASSERT_TRUE(extra.screen.ui()->text_input_active()); const auto typed = extra.screen.ui()->edit_state()->text();
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_row", "72"));
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_table_grid_jump_column", "9"));
  EXPECT_EQ(widget("analysis_table_grid_jump_row")->string.value(), "72");
  EXPECT_EQ(widget("analysis_table_grid_jump_column")->string.value(), "9");
  EXPECT_FALSE(widget("analysis_table_grid_jump")->enabled);
  const auto go = widget("analysis_table_grid_jump")->on_click;
  go(); f.drv->frame();
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "0");
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), typed);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  extra.driver.key(wm::Key::Enter, primary); extra.driver.frame();
  ASSERT_FALSE(f.shell->text_input_active());
  go(); f.drv->frame();
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "7209");
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisTableGridEditorPython, ExplicitJumpPreservesSavedDraftInvalidParameterTextAndProjectHistory)
{
  ASSERT_NO_FATAL_FAILURE(edit("probe", "2.0"));
  ASSERT_NO_FATAL_FAILURE(type("1e"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(grid());
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(jump("2", "1"));
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "2");
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "14.5");
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  EXPECT_EQ(cell("analysis_parameters", "probe"), "2.0");
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_EQ(project().project()->revision, revision); EXPECT_EQ(client->stats().calls_sent, sent);
  EXPECT_TRUE(calls("project.analyses.update").empty());
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u);
}
}  // namespace
}  // namespace stk::app
