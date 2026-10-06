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
        if mode == 'hold':
            (control / 'held').write_text('ready')
            while not (control / 'release').exists() and not self.closing.wait(0.01):
                pass
        elif mode in ('overflow', 'complex'):
            if mode == 'overflow':
                result['outputs']['table']['columns']['temperature'][0] = 18446744073709551617
            else:
                result['outputs']['table'] = {'type': 'value', 'value': {
                    '0': [18446744073709551615, -9223372036854775808, 1.0, -0.0, None, 'null', '', 'NaN'],
                    'a/b~c': {'': True},
                    'pages': {f'key{i:03}': i if i < 64 else 191 - i for i in range(128)},
                    'long': '科学\n' * 2500, 'identity': {'x' * 5000 + 'A': 1, 'x' * 5000 + 'B': 2}}}
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            record['result']['manifest_sha256'] = hashlib.sha256(raw).hexdigest()
            record['result']['size_bytes'] = len(raw) + 1024
        elif mode == 'hash':
            record['result']['manifest_sha256'] = '0' * 64
            record['error']['message'] = 'untrusted replacement'
        elif mode == 'graph':
            result['graph_hash'] = 'sha256:' + '0' * 64
        elif mode == 'plan':
            record['document']['parameters']['probe'] = 2.0
        elif mode == 'summary':
            record['result']['output_count'] += 1
        elif mode == 'receipt_extra':
            extra = True
            for _ in range(128):
                extra = {'nested': extra}
            record['result']['extra'] = extra
            # Exercise the controller boundary without either wire-schema validator.
            with self.write_lock:
                self.writer.write(encode_message(message))
                self.writer.flush()
            return
    return original_send(self, message, method)
Bridge.send = send
main()
)PY";

class AnalysisResultInspectionEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-result-inspection-ui"};
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
    if (std::string(::testing::UnitTest::GetInstance()->current_test_info()->name()) ==
        "RejectedRefreshKeepsTheEntireVerifiedBundleAndGeneration") { options.validate = false; }
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
  void select_original() { ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(run_id)); }
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
  void controller_read(ProjectAnalysisRuns &runs) {
    ASSERT_TRUE(runs.read_result()); ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
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

TEST_F(AnalysisResultInspectionEditorPython, ExplicitReadExposesPartialTableAndRawIssuesWithoutFurtherCalls)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  EXPECT_EQ(widget("analysis_result_outputs"), nullptr); EXPECT_TRUE(calls("project.analysis_runs.result").empty());
  ASSERT_NO_FATAL_FAILURE(read_result());
  EXPECT_EQ(widget("analysis_result_outputs")->table->rows, 2);
  EXPECT_EQ(cell("analysis_result_outputs", "table"), store().tr("analysis_results.delivered"));
  EXPECT_EQ(cell("analysis_result_outputs", "missing"), store().tr("analysis_results.missing"));
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(property("columns", true));
  ASSERT_NO_FATAL_FAILURE(property("temperature", true));
  EXPECT_EQ(cell("analysis_result_properties", "0"), "-9.5");
  EXPECT_EQ(cell("analysis_result_properties", "1"), "0.0");
  EXPECT_EQ(cell("analysis_result_properties", "2"), "14.5");
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_properties", "0"));
  EXPECT_EQ(paragraph("analysis_result_scalar_text"), "-9.5");
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_errors"));
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_properties", "0"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_open"));
  ASSERT_NO_FATAL_FAILURE(property("message"));
  EXPECT_NE(paragraph("analysis_result_scalar_text").find("absent.csv"), std::string::npos);
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "missing"));
  EXPECT_EQ(widget("analysis_result_properties"), nullptr); EXPECT_EQ(widget("analysis_run_output"), nullptr);
  EXPECT_EQ(client->stats().calls_sent, sent); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u); EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, RejectedRefreshKeepsTheEntireVerifiedBundleAndGeneration)
{
  ProjectAnalysisRuns runs(store()); ASSERT_TRUE(runs.load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  ASSERT_NO_FATAL_FAILURE(controller_read(runs)); ASSERT_TRUE(runs.error().empty());
  ASSERT_TRUE(runs.result_inspection()); const auto model = runs.result_inspection();
  ASSERT_TRUE(runs.load_page()); ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  const auto generation = runs.result_generation(); const auto original = exact(runs.run()), page = exact(runs.page());
  for (const auto *failure : {"hash", "graph", "plan", "summary", "overflow", "receipt_extra"}) {
    SCOPED_TRACE(failure);
  ASSERT_NO_FATAL_FAILURE(mode(failure));
    ASSERT_NO_FATAL_FAILURE(controller_read(runs)); EXPECT_FALSE(runs.error().empty());
    EXPECT_EQ(runs.result_inspection(), model); EXPECT_EQ(runs.result_generation(), generation);
    EXPECT_EQ(exact(runs.run()), original); EXPECT_EQ(exact(runs.page()), page);
    EXPECT_EQ(exact(runs.result()), exact(model->result()));
  }
  // The overflow fixture writes the actual JSON integer token 18446744073709551617 and
  // its Python-computed receipt. Native double promotion cannot pass the exact SHA check.
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(runs.load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  EXPECT_EQ(runs.result_inspection(), model); EXPECT_EQ(runs.result_generation(), generation);
  ASSERT_NO_FATAL_FAILURE(controller_read(runs)); EXPECT_TRUE(runs.error().empty());
  EXPECT_NE(runs.result_inspection(), model); EXPECT_GT(runs.result_generation(), generation);
}

TEST_F(AnalysisResultInspectionEditorPython, ExactTypedScalarSelectionPreservesNullStringsNumbersAndJsonPaths)
{
  ASSERT_NO_FATAL_FAILURE(mode("complex"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(property("value", true));
  ASSERT_NO_FATAL_FAILURE(property("0", true));
  const std::vector<std::string> expected{"18446744073709551615", "-9223372036854775808", "1.0", "-0.0", "null", "\"null\"", "\"\"", "\"NaN\""};
  const auto before = client->stats().calls_sent;
  for (size_t index = 0; index < expected.size(); ++index) {
    ASSERT_NO_FATAL_FAILURE(select("analysis_result_properties", std::to_string(index)));
    EXPECT_EQ(paragraph("analysis_result_scalar_text"), expected[index]);
  }
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table/value/0");
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_up"));
  ASSERT_NO_FATAL_FAILURE(property("a/b~c", true));
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table/value/a~1b~0c");
  ASSERT_NO_FATAL_FAILURE(property("")); EXPECT_EQ(paragraph("analysis_result_scalar_text"), "true");
  EXPECT_EQ(client->stats().calls_sent, before);
}

TEST_F(AnalysisResultInspectionEditorPython, LongScalarAndLongKeyIdentityAreFullyReachableByExplicitPages)
{
  ASSERT_NO_FATAL_FAILURE(mode("complex"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(property("value", true));
  ASSERT_NO_FATAL_FAILURE(property("long"));
  const auto sent = client->stats().calls_sent;
  std::string combined = paragraph("analysis_result_scalar_text");
  while (widget("analysis_result_scalar_next") && widget("analysis_result_scalar_next")->enabled) {
    ASSERT_NO_FATAL_FAILURE(click("analysis_result_scalar_next")); combined += paragraph("analysis_result_scalar_text");
  }
  std::string original; for (int index = 0; index < 2500; ++index) { original += "科学\n"; }
  EXPECT_EQ(combined, io::python_json_dumps(Json(original), false, true));
  ASSERT_NO_FATAL_FAILURE(property("identity", true));
  const auto table = *widget("analysis_result_properties")->table;
  ASSERT_EQ(table.rows, 2); EXPECT_EQ(table.cell(0, 0), table.cell(1, 0));
  for (int index = 0; index < 2; ++index) {
    widget("analysis_result_properties")->table->selected.assign(index); f.drv->frame();
    ASSERT_NO_FATAL_FAILURE(click("analysis_result_open"));
    std::string path = paragraph("analysis_result_path_text");
    while (widget("analysis_result_path_next") && widget("analysis_result_path_next")->enabled) {
      ASSERT_NO_FATAL_FAILURE(click("analysis_result_path_next")); path += paragraph("analysis_result_path_text");
    }
    EXPECT_EQ(path, "/outputs/table/value/identity/" + std::string(5000, 'x') + char('A' + index));
    EXPECT_EQ(paragraph("analysis_result_scalar_text"), std::to_string(index + 1));
    ASSERT_NO_FATAL_FAILURE(click("analysis_result_up"));
  }
  EXPECT_EQ(client->stats().calls_sent, sent);
}

TEST_F(AnalysisResultInspectionEditorPython, SortedEqualSizedPagesInvalidatePermutationAndRetainedNavigation)
{
  ASSERT_NO_FATAL_FAILURE(mode("complex"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(property("value", true));
  ASSERT_NO_FATAL_FAILURE(property("pages", true));
  ASSERT_EQ(widget("analysis_result_properties")->table->rows, 64);
  const auto retained_next = widget("analysis_result_next")->on_click;
  const auto retained_select = widget("analysis_result_properties")->table->selected;
  const auto rect = widget("analysis_result_properties")->rect;
  const auto unit = f.screen.ui()->style().unit;
  // Sort by the Value column, then select its first visible row with real pointer events.
  const ui::Vec2 header{rect.x + 1 + 8 * unit, rect.y + 1 + 0.5f * unit};
  f.screen.ui()->handle_event(ui::Event::mouse_down(header)); f.screen.ui()->handle_event(ui::Event::mouse_up(header)); f.drv->frame();
  auto select_first = [&] {
    const auto bounds = widget("analysis_result_properties")->rect;
    const ui::Vec2 pos{bounds.x + 10, bounds.y + 1 + 1.5f * unit};
    f.screen.ui()->handle_event(ui::Event::mouse_down(pos)); f.screen.ui()->handle_event(ui::Event::mouse_up(pos)); f.drv->frame();
  };
  select_first(); ASSERT_EQ(widget("analysis_result_properties")->table->selected.value(), 0);
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_next"));
  ASSERT_EQ(widget("analysis_result_properties")->table->rows, 64);
  select_first(); EXPECT_EQ(widget("analysis_result_properties")->table->selected.value(), 27); // lexical "100" is first
  const auto chosen = widget("analysis_result_properties")->table->selected.value();
  retained_select.assign(2); retained_next(); f.drv->frame();
  EXPECT_EQ(widget("analysis_result_properties")->table->selected.value(), chosen);
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_previous")); retained_next(); f.drv->frame();
  EXPECT_EQ(widget("analysis_result_properties")->table->cell(0, 0), "\"key000\"");
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, RetainedCallbacksCannotOverrideSourceSectionOrNewResultIntent)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  const auto old_rows = widget("analysis_result_properties")->table->selected;
  const auto old_issues = widget("analysis_result_errors")->on_click;
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  old_rows.assign(0); old_issues(); f.drv->frame();
  EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table");
  EXPECT_EQ(widget("analysis_result_properties")->table->selected.value(), -1);
  const auto read_before = calls("project.analysis_runs.result").size();
  const auto old_again = widget("analysis_result_errors")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_read_result")->enabled; }));
  old_again(); f.drv->frame(); EXPECT_EQ(widget("analysis_result_properties"), nullptr);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), read_before + 1);
}

TEST_F(AnalysisResultInspectionEditorPython, DirtySavedDraftAndInvalidRawTextRemainIndependentOfResultInspection)
{
  ASSERT_NO_FATAL_FAILURE(edit("probe", "2.0"));
  ASSERT_NO_FATAL_FAILURE(type("1e"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  ASSERT_NO_FATAL_FAILURE(property("columns", true));
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_errors"));
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  EXPECT_EQ(cell("analysis_parameters", "probe"), "2.0"); EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisResultInspectionEditorPython, NewRunSelectionAndProjectReopenClearBrowserWithoutAutomaticRead)
{
  Json second;
  ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, second));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  const auto retained = widget("analysis_result_outputs")->table->selected;
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id)); retained.assign(0); f.drv->frame();
  EXPECT_EQ(widget("analysis_result_outputs"), nullptr);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().loaded() && !project().busy(); }));
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  retained.assign(0); f.drv->frame(); EXPECT_EQ(widget("analysis_result_outputs"), nullptr);
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, LateResultAfterBridgeReplacementOrControllerDestructionCannotPublish)
{
  auto runs = std::make_unique<ProjectAnalysisRuns>(store()); ASSERT_TRUE(runs->load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs->busy(); }, 30));
  ASSERT_NO_FATAL_FAILURE(mode("hold")); ASSERT_TRUE(runs->read_result());
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  store().set_bridge(nullptr); runs->sync(); EXPECT_FALSE(runs->result_inspection());
  const auto generation = runs->result_generation();
  ASSERT_NO_FATAL_FAILURE(release()); store().set_bridge(client.get()); runs->sync(); loop.run_ready();
  EXPECT_FALSE(runs->result_inspection()); EXPECT_GE(runs->result_generation(), generation);
  runs.reset(); f.drv->frame(); EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, ExplicitEmptySelectionShowsEmptyStateWithoutInventingOutputs)
{
  auto empty = document; empty["outputs"] = Json::array(); Json saved, prepared;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "No requested outputs"}, {"document", empty}, {"expected_revision", revision}}, saved));
  revision = saved.at("revision").get<int64_t>();
  ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, prepared));
  ASSERT_NO_FATAL_FAILURE(execute(second_run_id, prepared)); EXPECT_EQ(prepared.at("status"), "succeeded");
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision == revision; }));
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_result_warnings") != nullptr; }));
  EXPECT_EQ(widget("analysis_result_outputs"), nullptr); EXPECT_EQ(widget("analysis_run_output"), nullptr);
  bool found = false;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) { found |= item.text == store().tr("analysis_results.empty"); }
  }
  EXPECT_TRUE(found); EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, ActiveRawInputInAnotherWindowFencesRetainedBrowserActions)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  const auto errors = widget("analysis_result_errors")->on_click;
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
  errors(); f.drv->frame(); EXPECT_EQ(paragraph("analysis_result_path_text"), "/outputs/table");
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), typed);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  extra.driver.key(wm::Key::Enter, primary); extra.driver.frame(); ASSERT_FALSE(f.shell->text_input_active());
  errors(); f.drv->frame(); EXPECT_EQ(paragraph("analysis_result_path_text"), "/errors");
  EXPECT_EQ(calls("project.analysis_runs.result").size(), 1u);
}

TEST_F(AnalysisResultInspectionEditorPython, DestroyedEditorRetainedPropertyCallbacksDoNothing)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(read_result());
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", "table"));
  const auto row = widget("analysis_result_properties")->table->selected;
  const auto errors = widget("analysis_result_errors")->on_click;
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs)); f.drv->frame();
  const auto sent = client->stats().calls_sent; row.assign(0); errors(); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorLogs); EXPECT_EQ(client->stats().calls_sent, sent);
}
}  // namespace
}  // namespace stk::app
