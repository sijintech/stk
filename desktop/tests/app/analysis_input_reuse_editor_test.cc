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
import json
from pathlib import Path
import sys
import threading
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
from suan.desktop_bridge.protocol import error_object
control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run = Bridge._run
def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}, ensure_ascii=True) + '\n')
    return original_run(self, identity, method, params)
Bridge._run = run
original_send = Bridge.send
def send(self, message, method=None):
    if method == 'project.snapshots.get' and 'result' in message:
        mode = (control / 'mode').read_text() if (control / 'mode').exists() else ''
        if mode == 'hold':
            (control / 'held').write_text('ready')
            while not (control / 'release').exists() and not self.closing.wait(0.01):
                pass
        elif mode == 'foreign':
            message['result']['snapshot']['manifest']['project_id'] = '78603d22-b2c8-4870-84e6-11b95b529fed'
        elif mode == 'hash':
            message['result']['snapshot']['sha256'] = '0' * 64
        elif mode == 'size':
            message['result']['snapshot']['manifest']['files'][0]['size'] += 1
        elif mode == 'missing':
            message = {'id': message['id'], 'error': error_object('not_found', 'Snapshot unavailable in controlled test')}
    return original_send(self, message, method)
Bridge.send = send
main()
)PY";

class AnalysisInputReuseEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-input-reuse-ui"};
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
        {"bindings", {{"data", {{"input.dat", file_id}}}}}, {"expected_revision", revision}}, response));
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
    ASSERT_TRUE(apptest::write_signed_field(directory.path() / "input.dat"));
    Json indexed, captured, saved;
    ASSERT_NO_FATAL_FAILURE(call("project.files.index", {{"handle", handle()}, {"expected_revision", 0},
        {"paths", Json::array({core::path_to_utf8(directory.path() / "input.dat")})}}, indexed));
    file_id = indexed.at("record_ids")[0].get<std::string>();
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()}, {"expected_revision", indexed.at("revision")},
        {"record_ids", Json::array({file_id})}}, captured)); snapshot = captured.at("snapshot");
    document = {{"format", "stk.analysis-document/1"},
        {"graph", io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
        {"parameters", {{"path", "input.dat"}, {"field", "input"}, {"component", 1}, {"unit", nullptr},
          {"precision_record", {{"large", std::numeric_limits<uint64_t>::max()}, {"float", 1.0}, {"empty", ""}}}, {"", true}, {"null_text", "null"}}},
        {"outputs", Json::array({"view"})}};
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", analysis_id},
        {"name", "Original analysis"}, {"document", document}, {"expected_revision", captured.at("revision")}}, saved));
    revision = saved.at("revision").get<int64_t>();
    ASSERT_NO_FATAL_FAILURE(prepare(run_id, frozen));
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
  void show_preparation() {
    if (!widget("analysis_input_preparation_clear")) { ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_prepare_panel")); }
    ASSERT_NE(widget("analysis_input_preparation_clear"), nullptr);
  }
  void select_original() {
    ASSERT_NO_FATAL_FAILURE(run_list());
    ASSERT_NO_FATAL_FAILURE(select_run(run_id));
    ASSERT_NO_FATAL_FAILURE(show_preparation());
  }
  void reuse() {
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_reuse_inputs"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_reused_inputs") != nullptr; }));
  }
  void mode(const std::string &value) {
    std::ofstream stream(directory.path() / "mode"); stream << value; ASSERT_TRUE(stream.good());
  }
  void hold() {
    fs::remove(directory.path() / "held"); fs::remove(directory.path() / "release");
    ASSERT_NO_FATAL_FAILURE(mode("hold"));
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_reuse_inputs"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return fs::exists(directory.path() / "held"); }));
  }
  void release() {
    { std::ofstream stream(directory.path() / "release"); stream << "ready"; }
    ASSERT_NO_FATAL_FAILURE(mode(""));
  }
  void refresh_revision(const int64_t expected) {
    project().refresh();
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision == expected; }));
  }
  void load_original_snapshots() {
    ASSERT_NO_FATAL_FAILURE(click("analysis_run_snapshots"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_snapshot") && widget("analysis_run_snapshot")->enabled; }));
    widget("analysis_run_snapshot")->index.assign(1); f.drv->frame();
    ASSERT_NE(widget("analysis_run_file"), nullptr);
  }
  void completion_without_adoption() {
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_inspect") && widget("analysis_run_inspect")->enabled; }));
    for (int i = 0; i < 4; ++i) { loop.run_ready(); f.drv->frame(); EXPECT_EQ(widget("analysis_reused_inputs"), nullptr); }
  }
  void TearDown() override {
    { std::ofstream stream(directory.path() / "release"); stream << "ready"; }
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating()); EXPECT_FALSE(viewer().payload());
    EXPECT_TRUE(calls("graph.evaluate").empty());
    EXPECT_TRUE(calls("project.analysis_runs.result").empty());
    EXPECT_TRUE(calls("project.snapshots.resolve").empty());
    EXPECT_TRUE(calls("project.analysis_runs.start").empty());
    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisInputReuseEditorPython, ReuseAndPrepareReadMetadataEvenWhenSnapshotBytesAreMissing)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  const auto digest = snapshot.at("manifest").at("files")[0].at("sha256").get<std::string>();
  ASSERT_TRUE(fs::remove(directory.path() / "input.dat"));
  ASSERT_TRUE(fs::remove(directory.path() / "project/.stk/objects/sha256" / digest.substr(0, 2) / digest.substr(2)));
  const auto before = calls("project.analysis_runs.prepare").size();
  ASSERT_NO_FATAL_FAILURE(reuse());
  ASSERT_EQ(calls("project.snapshots.get").size(), 1u);
  EXPECT_EQ(calls("project.snapshots.get")[0].at("snapshot_id"), snapshot.at("id"));
  EXPECT_EQ(calls("project.snapshots.get")[0].at("handle"), handle());
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), before);
  EXPECT_EQ(cell("analysis_reused_inputs", std::string(store().tr("analysis_runs.run_id"))), run_id);
  EXPECT_EQ(cell("analysis_reused_inputs", std::string(store().tr("analysis_runs.snapshot_id"))), snapshot.at("id").get<std::string>());
  ASSERT_NE(widget("analysis_run_bindings"), nullptr);
  EXPECT_EQ(widget("analysis_run_bindings")->table->cell(0, 0), "data");
  EXPECT_EQ(widget("analysis_run_bindings")->table->cell(0, 1), "input.dat");
  EXPECT_EQ(widget("analysis_run_bindings")->table->cell(0, 2), file_id.substr(0, 8));
  EXPECT_EQ(widget("analysis_run_snapshot"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_prepare"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_start") && widget("analysis_run_start")->enabled; }));
  ASSERT_EQ(calls("project.analysis_runs.prepare").size(), before + 1);
  const auto new_id = calls("project.analysis_runs.prepare").back().at("run_id");
  EXPECT_NE(new_id, run_id);
  Json current, original;
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", new_id}}, current));
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", run_id}}, original));
  EXPECT_EQ(exact(current.at("run").at("document")), exact(document));
  EXPECT_EQ(exact(current.at("run").at("bindings")), exact(frozen.at("bindings")));
  EXPECT_EQ(exact(original.at("run")), exact(frozen));
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_TRUE(calls("project.snapshots.verify").empty());
}

TEST_F(AnalysisInputReuseEditorPython, ExplicitPrepareUsesCurrentSavedDefinitionAndPreservesHistoricalRun)
{
  auto changed = document; changed["parameters"]["component"] = 2; changed["outputs"] = Json::array();
  Json response;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Current saved definition"}, {"document", changed}, {"expected_revision", revision}}, response));
  revision = response.at("revision").get<int64_t>();
  ASSERT_NO_FATAL_FAILURE(refresh_revision(revision));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters") && cell("analysis_parameters", "component") == "2"; }));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(reuse());
  const auto before = calls("project.analysis_runs.prepare").size();
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_prepare"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_start") && widget("analysis_run_start")->enabled; }));
  ASSERT_EQ(calls("project.analysis_runs.prepare").size(), before + 1);
  Json prepared, old;
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", calls("project.analysis_runs.prepare").back().at("run_id")}}, prepared));
  EXPECT_EQ(exact(prepared.at("run").at("document")), exact(changed));
  EXPECT_EQ(prepared.at("run").at("analysis_name"), "Current saved definition");
  EXPECT_EQ(exact(prepared.at("run").at("bindings")), exact(frozen.at("bindings")));
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", run_id}}, old));
  EXPECT_EQ(exact(old.at("run")), exact(frozen));
}

TEST_F(AnalysisInputReuseEditorPython, ExactSnapshotOutsideFirstHundredIsPinnedWithoutChangingTheList)
{
  for (int index = 0; index < 100; ++index) {
    Json response;
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()}, {"expected_revision", revision},
        {"record_ids", Json::array({file_id})}}, response));
    snapshot = response.at("snapshot"); revision = response.at("revision").get<int64_t>();
  }
  Json second; ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, second));
  ASSERT_NO_FATAL_FAILURE(refresh_revision(revision));
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id));
  ASSERT_NO_FATAL_FAILURE(show_preparation());
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_snapshots"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_snapshot") && widget("analysis_run_snapshot")->enabled; }));
  ProjectAnalysisRuns separate(store());
  ASSERT_TRUE(separate.load_snapshots());
  ASSERT_TRUE(loop.pump_until([&] { return !separate.busy(); }, 30));
  ASSERT_EQ(separate.snapshots().size(), 100u); EXPECT_EQ(separate.omitted_snapshots(), 1u);
  for (const auto &item : separate.snapshots()) { EXPECT_NE(item.at("id"), snapshot.at("id")); }
  ASSERT_NO_FATAL_FAILURE(reuse());
  EXPECT_EQ(calls("project.snapshots.get").back().at("snapshot_id"), snapshot.at("id"));
  EXPECT_EQ(cell("analysis_reused_inputs", std::string(store().tr("analysis_runs.snapshot_id"))), snapshot.at("id").get<std::string>());
  EXPECT_EQ(widget("analysis_run_snapshot"), nullptr);
  ASSERT_NE(widget("analysis_run_file"), nullptr); EXPECT_TRUE(widget("analysis_run_file")->enabled);
  EXPECT_EQ(separate.snapshots().size(), 100u);
}

TEST_F(AnalysisInputReuseEditorPython, UnaddedFormTextRequiresExplicitClearAndLastKeypressIsPreserved)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  const auto retained_reuse = widget("analysis_run_reuse_inputs")->on_click;
  ASSERT_NO_FATAL_FAILURE(load_original_snapshots());
  widget("analysis_run_file")->index.assign(1); f.drv->frame();
  const auto retained_clear = widget("analysis_input_preparation_clear")->on_click;
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_run_path", "unadded/input.dat", false));
  retained_clear(); retained_reuse(); f.drv->frame();
  EXPECT_TRUE(f.screen.ui()->text_input_active());
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "unadded/input.dat");
  EXPECT_TRUE(calls("project.snapshots.get").empty());
  EXPECT_EQ(widget("analysis_run_bindings"), nullptr);
  f.drv->key(wm::Key::Enter); f.drv->frame();
  EXPECT_EQ(widget("analysis_run_path")->string.value(), "unadded/input.dat");
  EXPECT_FALSE(widget("analysis_run_reuse_inputs")->enabled);
  retained_clear(); f.drv->frame();
  EXPECT_EQ(widget("analysis_run_path")->string.value(), "unadded/input.dat");
  ASSERT_NO_FATAL_FAILURE(click("analysis_input_preparation_clear"));
  EXPECT_EQ(widget("analysis_run_snapshot")->index.value(), 0);
  EXPECT_EQ(widget("analysis_run_file"), nullptr);
  ASSERT_NO_FATAL_FAILURE(reuse());
}

TEST_F(AnalysisInputReuseEditorPython, ClearDuringPendingReadConsumesTheCompletionWithoutLaterAdoption)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(hold());
  ASSERT_NO_FATAL_FAILURE(click("analysis_input_preparation_clear"));
  ASSERT_NO_FATAL_FAILURE(release());
  ASSERT_NO_FATAL_FAILURE(completion_without_adoption());
  EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  ASSERT_NO_FATAL_FAILURE(reuse());
  EXPECT_EQ(calls("project.snapshots.get").size(), 2u);
}

TEST_F(AnalysisInputReuseEditorPython, AnyInstalledWindowRawInputRejectsCompletionExactlyOnce)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(hold());
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
  const auto *input = extra.screen.ui()->find("a2/main/review_source"); ASSERT_NE(input, nullptr);
  const auto rect = input->rect;
  extra.driver.click(int(rect.cx()), extra.screen.rect().ymax - 1 - int(rect.cy()));
  extra.driver.key(wm::Key::Unknown, wm::ModNone, " unfinished input");
  ASSERT_TRUE(extra.screen.ui()->text_input_active()); const auto typed = extra.screen.ui()->edit_state()->text();
  ASSERT_NO_FATAL_FAILURE(release());
  // The read completes while input remains active, so the local stage must stay empty.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_refresh") && widget("analysis_run_refresh")->enabled; }));
  EXPECT_EQ(widget("analysis_reused_inputs"), nullptr);
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), typed);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  extra.driver.key(wm::Key::Enter, primary); extra.driver.frame();
  ASSERT_FALSE(f.shell->text_input_active()); EXPECT_EQ(project().review_source(), typed);
  ASSERT_NO_FATAL_FAILURE(completion_without_adoption());
  ASSERT_NO_FATAL_FAILURE(reuse());
}

TEST_F(AnalysisInputReuseEditorPython, NavigationRoundTripRejectsPendingAndRetainedReuse)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  const auto retained = widget("analysis_run_reuse_inputs")->on_click;
  ASSERT_NO_FATAL_FAILURE(hold());
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(release());
  ASSERT_NO_FATAL_FAILURE(completion_without_adoption());
  retained(); f.drv->frame(); EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  ASSERT_NO_FATAL_FAILURE(reuse());
}

TEST_F(AnalysisInputReuseEditorPython, CopiedInputsStayIndependentOfRunSelectionAndRetainedOldFormCallbacks)
{
  Json second; ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, second));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(reuse());
  const auto old_clear = widget("analysis_input_preparation_clear")->on_click;
  widget("analysis_run_file")->index.assign(1); f.drv->frame();
  const auto old_path = widget("analysis_run_path")->string;
  ASSERT_NO_FATAL_FAILURE(click("analysis_input_preparation_clear"));
  ASSERT_NO_FATAL_FAILURE(reuse());
  old_clear(); old_path.assign("stale.dat"); f.drv->frame();
  ASSERT_NE(widget("analysis_reused_inputs"), nullptr);
  EXPECT_EQ(widget("analysis_run_path")->string.value(), "");
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id));
  EXPECT_EQ(cell("analysis_reused_inputs", std::string(store().tr("analysis_runs.run_id"))), run_id);
  EXPECT_EQ(calls("project.snapshots.get").size(), 2u);
  widget("analysis_run_file")->index.assign(1); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(type_field("analysis_run_path", "alternative.dat"));
  // Exercise the real post-Enter mouse action, not a programmatic retained callback.
  ASSERT_TRUE(widget("analysis_run_add_file")->enabled);
  const auto [add_x, add_y] = f.widget_center(widget("analysis_run_add_file")->key);
  f.drv->click(add_x, add_y); f.drv->frame();
  ASSERT_NE(widget("analysis_run_bindings"), nullptr); EXPECT_EQ(widget("analysis_run_bindings")->table->rows, 2);
  widget("analysis_run_bindings")->table->selected.assign(0); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_remove_file"));
  EXPECT_EQ(widget("analysis_run_bindings")->table->rows, 1);
  EXPECT_EQ(widget("analysis_run_bindings")->table->cell(0, 1), "alternative.dat");
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 2u);
}

TEST_F(AnalysisInputReuseEditorPython, DirtyParametersAndInvalidTextSurviveReuseAndKeepPrepareBlocked)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(type("1e"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(reuse());
  ASSERT_NE(widget("analysis_run_prepare"), nullptr); EXPECT_FALSE(widget("analysis_run_prepare")->enabled);
  const auto prepare_old = widget("analysis_run_prepare")->on_click; prepare_old();
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  EXPECT_EQ(cell("analysis_parameters", "component"), "2");
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisInputReuseEditorPython, ControllerFailurePreservesLastValidatedStagingWithoutImplicitRetry)
{
  ProjectAnalysisRuns runs(store()); ASSERT_TRUE(runs.load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  ASSERT_TRUE(runs.read_reusable_inputs());
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  ASSERT_TRUE(runs.reusable_inputs()); const auto generation = runs.reusable_inputs_generation();
  const auto original = *runs.reusable_inputs();
  for (const auto *failure : {"foreign", "hash", "size", "missing"}) {
    SCOPED_TRACE(failure); ASSERT_NO_FATAL_FAILURE(mode(failure));
    ASSERT_TRUE(runs.read_reusable_inputs());
    ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
    EXPECT_FALSE(runs.error().empty()); EXPECT_EQ(runs.reusable_inputs_generation(), generation);
    ASSERT_TRUE(runs.reusable_inputs()); EXPECT_EQ(runs.reusable_inputs()->run_id, run_id);
    EXPECT_EQ(exact(runs.reusable_inputs()->bindings), exact(original.bindings));
  }
  EXPECT_EQ(calls("project.snapshots.get").size(), 5u);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
  ASSERT_NO_FATAL_FAILURE(mode(""));
}

TEST_F(AnalysisInputReuseEditorPython, LateReadAfterBridgeReplacementIsIgnoredAndNeverWrites)
{
  ProjectAnalysisRuns runs(store()); ASSERT_TRUE(runs.load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  ASSERT_NO_FATAL_FAILURE(mode("hold")); ASSERT_TRUE(runs.read_reusable_inputs());
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  const auto epoch = runs.epoch();
  store().set_bridge(nullptr); runs.sync();
  EXPECT_GT(runs.epoch(), epoch); EXPECT_FALSE(runs.reusable_inputs()); EXPECT_FALSE(runs.busy());
  ASSERT_NO_FATAL_FAILURE(release()); loop.run_ready();
  store().set_bridge(client.get()); runs.sync(); f.drv->frame();
  EXPECT_FALSE(runs.reusable_inputs()); EXPECT_TRUE(runs.run().is_null());
  EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
}

TEST_F(AnalysisInputReuseEditorPython, RejectedMetadataDoesNotPopulateTheFormAfterClearOrLaterFrames)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  ASSERT_NO_FATAL_FAILURE(mode("hash"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_reuse_inputs"));
  ASSERT_NO_FATAL_FAILURE(completion_without_adoption());
  ASSERT_NO_FATAL_FAILURE(click("analysis_input_preparation_clear"));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(completion_without_adoption());
  EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  EXPECT_EQ(widget("analysis_run_bindings"), nullptr);
  ASSERT_NO_FATAL_FAILURE(reuse());
}

TEST_F(AnalysisInputReuseEditorPython, LateReadFromClosedOpeningCannotAttachToReopenedProject)
{
  ProjectAnalysisRuns runs(store()); ASSERT_TRUE(runs.load(run_id));
  ASSERT_TRUE(loop.pump_until([&] { return !runs.busy(); }, 30));
  const auto old_handle = handle();
  ASSERT_NO_FATAL_FAILURE(mode("hold")); ASSERT_TRUE(runs.read_reusable_inputs());
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(loop.pump_until([&] { return !project().loaded() && !project().busy(); }, 30));
  runs.sync(); EXPECT_FALSE(runs.reusable_inputs());
  ASSERT_NO_FATAL_FAILURE(release());
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  EXPECT_NE(handle(), old_handle); runs.sync();
  EXPECT_FALSE(runs.reusable_inputs()); EXPECT_TRUE(runs.run().is_null());
  EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
}

TEST_F(AnalysisInputReuseEditorPython, DestroyedEditorRejectsLateCompletionAndRetainedActions)
{
  ASSERT_NO_FATAL_FAILURE(select_original());
  const auto retained = widget("analysis_run_reuse_inputs")->on_click;
  ASSERT_NO_FATAL_FAILURE(hold());
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs)); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(release()); retained();
  loop.run_ready(); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorLogs);
  EXPECT_EQ(calls("project.snapshots.get").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
}
}  // namespace
}  // namespace stk::app
