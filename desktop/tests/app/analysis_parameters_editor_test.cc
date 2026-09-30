/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_analyses.hh"
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
constexpr const char *analysis_id = "48603d22-b2c8-4870-84e6-11b95b529fed";
std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }
constexpr const char *kAnalysisBridge = R"PY(
import copy
import json
from pathlib import Path
import sys
import threading
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main

control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run, original_send = Bridge._run, Bridge.send

def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}, ensure_ascii=True) + '\n')
    return original_run(self, identity, method, params)

def send(self, message, method=None):
    path = control / 'mode'
    mode = path.read_text(encoding='utf-8') if path.exists() else ''
    if method in ('project.analyses.create', 'project.analyses.update') and 'result' in message:
        if mode == 'lost':
            return
        if mode == 'malformed':
            message = copy.deepcopy(message)
            message['result']['record_id'] = '00000000-0000-4000-8000-000000000000'
    if method == 'project.analyses.get' and 'result' in message and mode == 'hold':
        (control / 'held').write_text('ready', encoding='utf-8')
        while not (control / 'release').exists():
            if self.closing.wait(0.01):
                return
    return original_send(self, message, method)

Bridge._run, Bridge.send = run, send
main()
)PY";

class AnalysisParametersEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-parameters-ui"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1700};
  std::unique_ptr<bridge::Client> client;
  Json document, snapshot;
  std::string file_id;
  int64_t revision = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  ViewerState &viewer() { return store().viewer(); }
  EditorArea &area() { return f.area("a2"); }
  std::string handle() { return project().project()->handle; }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  const ui::Widget *name_widget() {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.key.find("/analysis_name/") != std::string::npos) { return &item; } }
    }
    return nullptr;
  }
  void mode(const std::string &value) {
    std::ofstream file(directory.path() / "mode", std::ios::binary); file << value; ASSERT_TRUE(file.good());
  }
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
  void type(const std::string &text, const bool finish = true) {
    const auto *input = widget("analysis_parameter_value"); ASSERT_NE(input, nullptr); ASSERT_TRUE(input->enabled);
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
  void edit(const std::string &name, const std::string &value) {
    ASSERT_NO_FATAL_FAILURE(row(name));
    ASSERT_NO_FATAL_FAILURE(type(value));
    ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  }
  void save() {
    ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision > revision &&
        widget("analysis_parameters_save") && !widget("analysis_parameters_save")->enabled &&
        widget("analysis_parameter_value") && widget("analysis_parameter_value")->enabled; }));
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
    options.executor = loop.executor(); options.strict = options.validate = true; options.call_timeout_s = 5;
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
    revision = saved.at("revision").get<int64_t>(); project().refresh();
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
  void TearDown() override {
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating()); EXPECT_FALSE(viewer().payload());
    EXPECT_TRUE(calls("graph.evaluate").empty()); EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
    EXPECT_TRUE(calls("project.analysis_runs.start").empty());
    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisParametersEditorPython, KeyboardEditSavesOneCasUpdateAndUndoRestoresExactDocument)
{
  ASSERT_NO_FATAL_FAILURE(row("component"));
  const auto reload = widget("analysis_reload")->on_click;
  const auto copy = widget("analysis_save")->on_click;
  const auto rename = widget("analysis_rename")->on_click;
  const auto selected = widget("analysis_documents")->table->selected;
  ASSERT_NO_FATAL_FAILURE(type("2", false));
  reload(); copy(); rename(); selected.assign(0); loop.run_ready();
  EXPECT_TRUE(calls("project.analyses.update").empty()); EXPECT_EQ(calls("project.analyses.create").size(), 1u);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "2");
  f.drv->key(wm::Key::Enter); f.drv->frame();
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); EXPECT_FALSE(widget("analysis_reload")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(save());
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["parameters"]["component"] = 2;
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_EQ(current.at("analysis").at("name"), "Original analysis");
  ASSERT_EQ(calls("project.analyses.update").size(), 1u);
  EXPECT_EQ(calls("project.analyses.update")[0].at("expected_revision"), revision);
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
}

TEST_F(AnalysisParametersEditorPython, InvalidTextAndLastKeypressFenceRetainedSaveAndSelection)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  const auto save_old = widget("analysis_parameters_save")->on_click;
  ASSERT_NO_FATAL_FAILURE(type("1e", false)); save_old(); loop.run_ready();
  EXPECT_TRUE(calls("project.analyses.update").empty());
  f.drv->key(wm::Key::Enter); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); save_old();
  const auto before = widget("analysis_parameters")->table->selected.value();
  widget("analysis_parameters")->table->selected.assign(0); f.drv->frame();
  EXPECT_EQ(widget("analysis_parameters")->table->selected.value(), before);
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(row("component"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1");
}

TEST_F(AnalysisParametersEditorPython, NullAbsentEmptyStringAndEmptyUnknownKeyStayDistinct)
{
  ASSERT_NO_FATAL_FAILURE(row("unit"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_remove"));
  ASSERT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_null")); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(edit("field", ""));
  ASSERT_NO_FATAL_FAILURE(edit("", "false"));
  ASSERT_NO_FATAL_FAILURE(save()); Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["parameters"]["field"] = ""; expected["parameters"][""] = false;
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_TRUE(current.at("analysis").at("document").at("parameters").at("unit").is_null());
  EXPECT_FALSE(current.at("analysis").at("document").at("parameters").contains("colormap"));
}

TEST_F(AnalysisParametersEditorPython, ExternalRevisionAndSessionSwitchPreserveDetachedInputWithoutRetargeting)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); const auto save_old = widget("analysis_parameters_save")->on_click;
  Json response; const Json commands = Json::array({{{"op", "create_table"}, {"name", "Other work"}}});
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", commands}}, response));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); EXPECT_FALSE(widget("analysis_parameter_value")->enabled);
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2"); save_old();
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  ASSERT_TRUE(project().create(directory.str() + "/other-project", "Different project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); })); save_old();
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2"); EXPECT_FALSE(widget("analysis_parameter_value")->enabled);
  EXPECT_EQ(project().project()->revision, 0); EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard")); EXPECT_EQ(widget("analysis_parameter_value"), nullptr);
}

TEST_F(AnalysisParametersEditorPython, LostSaveReplyReadsMatchingIdentityWithoutResubmitting)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); mode("lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; }));
  EXPECT_FALSE(widget("analysis_parameter_value")->enabled); EXPECT_FALSE(widget("analysis_parameters_discard")->enabled);
  mode("");
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameter_value") && widget("analysis_parameter_value")->enabled; }));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2");
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}

TEST_F(AnalysisParametersEditorPython, DifferingLostReplyReadbackKeepsDraftUntilExplicitDiscard)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); mode("lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; })); mode("");
  Json current, changed;
  ASSERT_NO_FATAL_FAILURE(read(current)); auto external = current.at("analysis").at("document");
  external["parameters"]["component"] = 3;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id}, {"name", "Other author"},
      {"document", external}, {"expected_revision", current.at("revision")}}, changed));
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters_discard") && widget("analysis_parameters_discard")->enabled; }));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2"); EXPECT_FALSE(widget("analysis_parameter_value")->enabled);
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); EXPECT_EQ(calls("project.analyses.update").size(), 2u);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NO_FATAL_FAILURE(row("component"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "3");
}

TEST_F(AnalysisParametersEditorPython, DirtyDraftFencesAlreadyCapturedRunPrepare)
{
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_snapshots"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_snapshot") && widget("analysis_run_snapshot")->items.size() == 2; }));
  widget("analysis_run_snapshot")->index.assign(1); f.drv->frame(); widget("analysis_run_file")->index.assign(1); f.drv->frame();
  widget("analysis_run_path")->string.assign("input.dat");
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_add_file"));
  ASSERT_TRUE(widget("analysis_run_prepare")->enabled); const auto prepare = widget("analysis_run_prepare")->on_click;
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); prepare();
  widget("analysis_saved_section")->index.assign(1); f.drv->frame(); EXPECT_FALSE(widget("analysis_run_prepare")->enabled); prepare();
  EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
}

TEST_F(AnalysisParametersEditorPython, DestroyedEditorRejectsRetainedBindingsAndSave)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); const auto save_old = widget("analysis_parameters_save")->on_click;
  const auto input = widget("analysis_parameter_value")->string;
  ASSERT_TRUE(area().set_tab_type(0, kEditorProject)); input.assign("3"); save_old(); loop.run_ready();
  EXPECT_TRUE(calls("project.analyses.update").empty()); EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(AnalysisParametersEditorPython, ControllerWrapperRequiresCapturedSelectionAndPreservesUntouchedFields)
{
  ProjectAnalyses analyses(store()); ASSERT_TRUE(analyses.load(analysis_id));
  ASSERT_TRUE(loop.pump_until([&] { return !analyses.busy(); }, 30));
  const auto selection = analyses.selected_version(); auto parameters = document.at("parameters"); parameters["component"] = 4;
  ASSERT_TRUE(analyses.load(analysis_id)); ASSERT_TRUE(loop.pump_until([&] { return !analyses.busy(); }, 30));
  EXPECT_FALSE(analyses.replace_parameters(parameters, selection));
  ASSERT_TRUE(analyses.replace_parameters(parameters, analyses.selected_version()));
  ASSERT_TRUE(loop.pump_until([&] { return !analyses.busy() && !project().busy(); }, 30));
  EXPECT_TRUE(analyses.error().empty()) << analyses.error(); auto expected = document; expected["parameters"] = parameters;
  EXPECT_EQ(exact(analyses.selected().at("document")), exact(expected));
  EXPECT_EQ(analyses.selected().at("name"), "Original analysis");
  EXPECT_EQ(analyses.selected_revision(), revision + 1);
}

TEST_F(AnalysisParametersEditorPython, TableShowsTypedNullStringAndFloatWithoutInventingDefaults)
{
  const auto &spec = *widget("analysis_parameters")->table;
  auto cell = [&](const std::string &name, const int column) {
    for (int row = 0; row < spec.rows; ++row) { if (spec.cell(row, 0) == name) { return spec.cell(row, column); } }
    ADD_FAILURE() << name; return std::string();
  };
  EXPECT_EQ(cell("unit", 1), "null"); EXPECT_EQ(cell("null_text", 1), "\"null\"");
  EXPECT_EQ(cell("field", 1), "\"input\"");
  EXPECT_NE(cell("precision_record", 1).find("1.0"), std::string::npos);
  EXPECT_NE(cell("precision_record", 1).find("18446744073709551615"), std::string::npos);
  EXPECT_EQ(cell("colormap", 3), store().tr("analysis_parameters.default"));
  EXPECT_EQ(cell("colormap", 1), "\"viridis\"");
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisParametersEditorPython, SavingRemovedUnknownKeyRemovesItsRowAndSelectedEditor)
{
  ASSERT_NO_FATAL_FAILURE(row("null_text"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_remove"));
  ASSERT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision == revision + 1 &&
      !widget("analysis_parameters_save")->enabled; }));
  EXPECT_EQ(widget("analysis_parameter_value"), nullptr);
  const auto &spec = *widget("analysis_parameters")->table;
  EXPECT_EQ(spec.selected.value(), -1);
  for (int row = 0; row < spec.rows; ++row) { EXPECT_NE(spec.cell(row, 0), "null_text"); }
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  EXPECT_FALSE(current.at("analysis").at("document").at("parameters").contains("null_text"));
}

TEST_F(AnalysisParametersEditorPython, ParameterSavePreservesSeparatePendingNameAndActiveNameTextBlocksRetainedSave)
{
  ASSERT_NE(name_widget(), nullptr); name_widget()->string.assign("Pending rename"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(save()); ASSERT_NE(name_widget(), nullptr);
  EXPECT_EQ(name_widget()->string.value(), "Pending rename");
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(current.at("analysis").at("name"), "Original analysis");
  ASSERT_NO_FATAL_FAILURE(edit("component", "3"));
  const auto save_old = widget("analysis_parameters_save")->on_click;
  // A retained callback cannot race an active text edit in this window, including another field.
  // The name field is intentionally disabled while parameter edits are dirty, so begin while clean.
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NE(name_widget(), nullptr); ASSERT_TRUE(name_widget()->enabled);
  const auto [x, y] = f.widget_center(name_widget()->key); f.drv->click(x, y);
  f.drv->key(wm::Key::Unknown, wm::ModNone, " unfinished"); ASSERT_TRUE(f.screen.ui()->text_input_active());
  save_old(); loop.run_ready(); EXPECT_EQ(calls("project.analyses.update").size(), 1u);
  EXPECT_NE(f.screen.ui()->edit_state()->text().find("unfinished"), std::string::npos);
  f.drv->key(wm::Key::Enter); f.drv->frame();
}

TEST_F(AnalysisParametersEditorPython, AcceptedTypedTextAbove64KiBIsNotTruncatedByFocusing)
{
  auto expanded = document;
  expanded["parameters"]["precision_record"] = Json::array();
  for (int i = 0; i < 15000; ++i) { expanded["parameters"]["precision_record"].push_back(-0.0); }
  const auto text = io::python_json_dumps(expanded.at("parameters").at("precision_record"), false, true);
  ASSERT_GT(text.size(), 64u * 1024u);
  Json changed;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Original analysis"}, {"document", expanded}, {"expected_revision", revision}}, changed));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters") && widget("analysis_parameters")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(row("precision_record"));
  const auto *input = widget("analysis_parameter_value"); ASSERT_EQ(input->string.value(), text);
  const auto [x, y] = f.widget_center(input->key); f.drv->click(x, y); f.drv->frame();
  ASSERT_TRUE(f.screen.ui()->text_input_active()); EXPECT_EQ(f.screen.ui()->edit_state()->text(), text);
  f.drv->key(wm::Key::Enter); f.drv->frame(); EXPECT_EQ(widget("analysis_parameter_value")->string.value(), text);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply")); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expanded));
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}

TEST_F(AnalysisParametersEditorPython, MissingLostReplyReadbackKeepsLocalCandidateAndNeverReplays)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2")); mode("lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; })); mode("");
  Json current, removed;
  ASSERT_NO_FATAL_FAILURE(read(current));
  const Json commands = Json::array({{{"op", "delete_record"}, {"id", analysis_id}}});
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", current.at("revision")},
      {"commands", commands}}, removed));
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters_discard") && widget("analysis_parameters_discard")->enabled; }));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2"); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  const auto reads_before = calls("project.analyses.get").size();
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return calls("project.analyses.get").size() > reads_before &&
      widget("analysis_reload") && widget("analysis_reload")->enabled; }));
  EXPECT_EQ(calls("project.analyses.create").size(), 1u);
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}


TEST_F(AnalysisParametersEditorPython, ActiveInvalidTextSurvivesProjectCloseAndReopenWithoutRetargeting)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  const auto old_save = widget("analysis_parameters_save")->on_click;
  ASSERT_NO_FATAL_FAILURE(type("1e", false));
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  ASSERT_NE(widget("analysis_parameter_value"), nullptr);
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameter_value")->enabled);
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled); old_save();
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  ASSERT_NE(widget("analysis_parameter_value"), nullptr);
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameter_value")->enabled); old_save();
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
  EXPECT_TRUE(calls("project.analyses.update").empty());
  if (f.screen.ui()->text_input_active()) { f.drv->key(wm::Key::Enter); f.drv->frame(); }
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  EXPECT_EQ(widget("analysis_parameter_value"), nullptr);
}


TEST_F(AnalysisParametersEditorPython, StringDeclarationsUseExactJsonForNullDefaultsAndNonstringOverrides)
{
  auto mixed = document;
  mixed["parameters"]["field"] = nullptr;
  mixed["parameters"]["path"] = Json::array({1, 1.0});
  mixed["graph"]["parameters"].push_back({{"name", "caption"}, {"type", "string"}, {"default", nullptr}});
  Json changed;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Original analysis"}, {"document", mixed}, {"expected_revision", revision}}, changed));
  revision = changed.at("revision").get<int64_t>(); project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters") && widget("analysis_parameters")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(row("field"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "null");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply")); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(type("\"null\""));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "null");
  ASSERT_NO_FATAL_FAILURE(row("path"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "[1,1.0]");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(row("caption"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "null");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  ASSERT_NO_FATAL_FAILURE(save());
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = mixed; expected["parameters"]["field"] = "null"; expected["parameters"]["caption"] = nullptr;
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_TRUE(current.at("analysis").at("document").at("parameters").at("field").is_string());
  EXPECT_TRUE(current.at("analysis").at("document").at("parameters").at("caption").is_null());
}


} // namespace
} // namespace stk::app
