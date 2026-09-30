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

class AnalysisOutputsEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-outputs-ui"};
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
        widget("analysis_output_choices") && widget("analysis_output_choices")->enabled; }));
  }
  void toggle(const char *key) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr);
    const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
    f.screen.ui()->handle_event(ui::Event::mouse_down(center));
    f.screen.ui()->handle_event(ui::Event::mouse_up(center)); f.drv->frame();
  }
  void output(const std::string &name, const bool selected) {
    const auto *value = widget("analysis_output_choices"); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled);
    const auto spec = *value->table; int row = -1;
    for (int i = 0; i < spec.rows; ++i) { if (spec.cell(i, 0) == name) { row = i; } }
    ASSERT_GE(row, 0); spec.selected.assign(row); f.drv->frame();
    const auto *checkbox = widget("analysis_output_requested"); ASSERT_NE(checkbox, nullptr); ASSERT_TRUE(checkbox->enabled);
    checkbox->boolean.assign(selected); f.drv->frame();
  }
  void ordered_outputs() {
    ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
    ASSERT_NO_FATAL_FAILURE(output("view", true));
    ASSERT_NO_FATAL_FAILURE(output("image", true));
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
    document["graph"]["outputs"]["image"] = document.at("graph").at("outputs").at("view");
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
    EXPECT_TRUE(calls("graph.evaluate").empty());
    EXPECT_TRUE(calls("project.analysis_runs.start").empty());
    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisOutputsEditorPython, CombinedSaveKeepsOutputOrderExactParametersAndOneUndoStepAcrossReopen)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(ordered_outputs());
  const auto *choices = widget("analysis_output_choices"); ASSERT_NE(choices, nullptr);
  for (int i = 0; i < choices->table->rows; ++i) {
    EXPECT_EQ(choices->table->cell(i, 2), document.at("graph").at("outputs").at(choices->table->cell(i, 0)).get<std::string>());
  }
  ASSERT_NO_FATAL_FAILURE(save());
  Json current; ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["parameters"]["component"] = 2; expected["outputs"] = Json::array({"view", "image"});
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_EQ(current.at("revision").get<int64_t>(), revision + 1);
  EXPECT_EQ(current.at("analysis").at("name"), "Original analysis");
  ASSERT_EQ(calls("project.analyses.update").size(), 1u);
  EXPECT_EQ(calls("project.analyses.update")[0].at("expected_revision"), revision);
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
}

TEST_F(AnalysisOutputsEditorPython, OutputOnlyClearPersistsAnExplicitEmptyArrayAndKeepsAllParameterTypes)
{
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
  ASSERT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(toggle("analysis_parameter_values_panel"));
  EXPECT_EQ(widget("analysis_parameters"), nullptr);
  EXPECT_NE(widget("analysis_output_choices"), nullptr); EXPECT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(save());
  Json current; ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["outputs"] = Json::array();
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_TRUE(current.at("analysis").at("document").at("outputs").empty());
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}

TEST_F(AnalysisOutputsEditorPython, SelectAllAndClearPreserveAcceptedParametersWhileWholeDiscardResetsBoth)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_all"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NO_FATAL_FAILURE(row("component"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1");
  ASSERT_NO_FATAL_FAILURE(output("image", false));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(output("view", true));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisOutputsEditorPython, RawInvalidAndActiveTextFenceOutputCallbacksWithoutDroppingEitherDraft)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(output("image", true));
  const auto old_clear = widget("analysis_outputs_clear")->on_click;
  const auto old_all = widget("analysis_outputs_all")->on_click;
  const auto old_checkbox = widget("analysis_output_requested")->boolean;
  const auto old_rows = widget("analysis_output_choices")->table->selected;
  ASSERT_NO_FATAL_FAILURE(type("1e", false));
  old_clear(); old_all(); old_checkbox.assign(false); old_rows.assign(1); f.drv->frame();
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "1e");
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_output_choices")->enabled);
  f.drv->key(wm::Key::Enter); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  old_clear(); old_all(); old_checkbox.assign(false); f.drv->frame();
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NO_FATAL_FAILURE(output("image", false));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisOutputsEditorPython, MatchingLostReplyAdoptsBothChangesWithoutReplayingTheWrite)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(ordered_outputs());
  mode("lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; }));
  mode("");
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_output_choices") && widget("analysis_output_choices")->enabled &&
      widget("analysis_parameters_save") && !widget("analysis_parameters_save")->enabled; }));
  Json current; ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["parameters"]["component"] = 2; expected["outputs"] = Json::array({"view", "image"});
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2");
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}

TEST_F(AnalysisOutputsEditorPython, DifferingLostReplyKeepsBothLocalChangesUntilExplicitDiscard)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(ordered_outputs());
  mode("lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; }));
  mode(""); Json current, changed;
  ASSERT_NO_FATAL_FAILURE(read(current));
  auto external = current.at("analysis").at("document"); external["outputs"] = Json::array();
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Original analysis"}, {"document", external}, {"expected_revision", current.at("revision")}}, changed));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().project()->revision == changed.at("revision").get<int64_t>() &&
      !project().busy() && widget("analysis_check_save") && widget("analysis_check_save")->enabled; }));
  const auto reads_before = calls("project.analyses.get").size();
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_parameters_discard") && widget("analysis_parameters_discard")->enabled; }));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2");
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_output_choices")->enabled); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_EQ(calls("project.analyses.update").size(), 2u);
  EXPECT_EQ(calls("project.analyses.get").size(), reads_before + 1);
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  EXPECT_FALSE(widget("analysis_outputs_clear")->enabled);
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_TRUE(current.at("analysis").at("document").at("outputs").empty());
}

TEST_F(AnalysisOutputsEditorPython, OutputOnlyDraftFencesRenameReloadNewSaveAndPrepareCallbacks)
{
  const auto reload = widget("analysis_reload")->on_click;
  const auto create = widget("analysis_save")->on_click;
  const auto rename = widget("analysis_rename")->on_click;
  const auto selection = widget("analysis_documents")->table->selected;
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
  const auto old_all = widget("analysis_outputs_all")->on_click;
  reload(); create(); rename(); selection.assign(0); f.drv->frame(); loop.run_ready();
  EXPECT_FALSE(widget("analysis_reload")->enabled); EXPECT_FALSE(widget("analysis_save")->enabled);
  EXPECT_FALSE(widget("analysis_rename")->enabled);
  EXPECT_EQ(calls("project.analyses.create").size(), 1u); EXPECT_TRUE(calls("project.analyses.update").empty());
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  ASSERT_NE(widget("analysis_run_prepare"), nullptr); EXPECT_FALSE(widget("analysis_run_prepare")->enabled);
  widget("analysis_run_prepare")->on_click(); loop.run_ready();
  EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
  old_all(); f.drv->frame();
  widget("analysis_saved_section")->index.assign(0); f.drv->frame(); old_all(); f.drv->frame();
  EXPECT_FALSE(widget("analysis_outputs_clear")->enabled);
}

TEST_F(AnalysisOutputsEditorPython, ProjectCloseAndReopenPreserveDetachedOutputDraftAndRejectRetainedSave)
{
  ASSERT_NO_FATAL_FAILURE(output("image", true));
  const auto old_save = widget("analysis_parameters_save")->on_click;
  const auto old_clear = widget("analysis_outputs_clear")->on_click;
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  old_save(); old_clear(); f.drv->frame();
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_output_choices")->enabled);
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  old_save(); old_clear(); f.drv->frame();
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  Json current; ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
  EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
}

TEST_F(AnalysisOutputsEditorPython, WrapperChecksBoundsAndSelectionWhileLegacyParameterUpdatePreservesOutputs)
{
  ProjectAnalyses controller(store()); ASSERT_TRUE(controller.load(analysis_id));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !controller.busy(); }));
  const auto selection = controller.selected_version();
  EXPECT_FALSE(controller.replace_submission(document.at("parameters"), Json::object(), selection));
  EXPECT_FALSE(controller.replace_submission(document.at("parameters"), Json::array({"missing"}), selection));
  EXPECT_FALSE(controller.replace_submission(document.at("parameters"), Json::array({"view", "view"}), selection));
  EXPECT_FALSE(controller.replace_submission(document.at("parameters"), Json::array(), selection + 1));
  auto oversized = document.at("parameters"); oversized["oversized"] = std::string(384 * 1024 + 1, 'x');
  EXPECT_FALSE(controller.replace_submission(oversized, Json::array(), selection));
  EXPECT_TRUE(calls("project.analyses.update").empty());
  auto parameters = document.at("parameters"); parameters["component"] = 2;
  ASSERT_TRUE(controller.replace_parameters(parameters, selection));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !controller.busy() && !project().busy(); }));
  Json current; ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document; expected["parameters"] = parameters;
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_FALSE(controller.replace_submission(parameters, Json::array(), selection));
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);
}

TEST_F(AnalysisOutputsEditorPython, PaginationSelectAllUsesEveryPageAndStalePageCallbacksCannotRetarget)
{
  auto expanded = document; expanded["graph"]["outputs"] = Json::object();
  Json all = Json::array();
  for (int i = 0; i < 128; ++i) {
    const auto name = "out_" + std::to_string(1000 + i);
    expanded["graph"]["outputs"][name] = i == 0 || i == 127 ? "a.out" : i == 64 ? "z.out" : "b.out";
    all.push_back(name);
  }
  expanded["outputs"] = Json::array(); Json changed;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Original analysis"}, {"document", expanded}, {"expected_revision", revision}}, changed));
  revision = changed.at("revision").get<int64_t>(); project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_output_choices") && widget("analysis_output_choices")->enabled; }));
  const auto old_all = widget("analysis_outputs_all")->on_click;
  const auto old_rows = widget("analysis_output_choices")->table->selected;
  const auto mouse = [&](const ui::Vec2 point) {
    f.screen.ui()->handle_event(ui::Event::mouse_down(point));
    f.screen.ui()->handle_event(ui::Event::mouse_up(point)); f.drv->frame();
  };
  auto table_rect = widget("analysis_output_choices")->rect;
  const auto unit = f.screen.ui()->style().unit;
  mouse({table_rect.x + 1 + 17 * unit, table_rect.y + 1 + unit * 0.5f}); // Sort by endpoint.
  mouse({table_rect.x + 10, table_rect.y + 1 + unit * 1.5f});
  EXPECT_EQ(widget("analysis_output_choices")->table->selected.value(), 0);
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_next")); old_all(); old_rows.assign(0); f.drv->frame();
  EXPECT_EQ(widget("analysis_output_requested"), nullptr); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  table_rect = widget("analysis_output_choices")->rect;
  mouse({table_rect.x + 10, table_rect.y + 1 + unit * 1.5f});
  EXPECT_EQ(widget("analysis_output_choices")->table->selected.value(), 63) << "Second page has a different ascending endpoint order";
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_previous")); old_all(); old_rows.assign(0); f.drv->frame();
  EXPECT_EQ(widget("analysis_output_requested"), nullptr); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_next"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_all"));
  ASSERT_NO_FATAL_FAILURE(save());
  Json current; ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(current.at("analysis").at("document").at("outputs"), all);
}

TEST_F(AnalysisOutputsEditorPython, MoreThan256DeclarationsKeepLaterSelectionsEditableAndAllCannotSubmitAPrefix)
{
  auto expanded = document; expanded["graph"]["outputs"] = Json::object();
  for (int i = 0; i < 300; ++i) { expanded["graph"]["outputs"]["out_" + std::to_string(1000 + i)] = "scene.scene"; }
  expanded["outputs"] = Json::array({"out_1299"}); Json changed;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Original analysis"}, {"document", expanded}, {"expected_revision", revision}}, changed));
  revision = changed.at("revision").get<int64_t>(); project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_output_choices") && widget("analysis_output_choices")->enabled; }));
  EXPECT_FALSE(widget("analysis_outputs_all")->enabled);
  widget("analysis_outputs_all")->on_click(); f.drv->frame(); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  for (int i = 0; i < 4; ++i) { ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_next")); }
  ASSERT_EQ(widget("analysis_output_choices")->table->rows, 44);
  ASSERT_NO_FATAL_FAILURE(output("out_1299", false));
  ASSERT_NO_FATAL_FAILURE(save());
  Json current; ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_TRUE(current.at("analysis").at("document").at("outputs").empty());
  EXPECT_EQ(exact(current.at("analysis").at("document").at("parameters")), exact(document.at("parameters")));
}

TEST_F(AnalysisOutputsEditorPython, FrozenAndPreparedRunsKeepOldOutputsUntilAnExplicitCombinedSave)
{
  const char *old_id = "ce603d22-b2c8-4870-84e6-11b95b529fed";
  const char *new_id = "fe603d22-b2c8-4870-84e6-11b95b529fed";
  auto prepare = [&](const char *id, const int64_t source_revision, Json &result) {
    call("project.analysis_runs.prepare", {{"handle", handle()}, {"run_id", id}, {"analysis_id", analysis_id},
        {"snapshot_id", snapshot.at("id")}, {"bindings", {{"data", {{"input.dat", file_id}}}}},
        {"expected_revision", source_revision}}, result);
  };
  Json old_run, new_run;
  ASSERT_NO_FATAL_FAILURE(prepare(old_id, revision, old_run));
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_list"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_rows") && widget("analysis_run_rows")->enabled; }));
  widget("analysis_run_rows")->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_inspect") && widget("analysis_run_inspect")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_return_saved"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
  const auto old_save = widget("analysis_parameters_save")->on_click;
  const auto old_all = widget("analysis_outputs_all")->on_click;
  widget("graph_mode")->index.assign(3); f.drv->frame(); old_save(); old_all(); f.drv->frame();
  EXPECT_TRUE(calls("project.analyses.update").empty());
  if (!widget("graph_output_rows")) { ASSERT_NO_FATAL_FAILURE(toggle("graph_outputs")); }
  const auto table = *widget("graph_output_rows")->table;
  for (int i = 0; i < table.rows; ++i) {
    if (table.cell(i, 0) == "view") { EXPECT_EQ(table.cell(i, 1), store().tr("analysis_graph.requested")); }
  }
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_return_saved"));
  EXPECT_FALSE(widget("analysis_outputs_clear")->enabled); ASSERT_TRUE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(save());
  ASSERT_NO_FATAL_FAILURE(prepare(new_id, revision + 1, new_run));
  EXPECT_EQ(old_run.at("run").at("document").at("outputs"), Json::array({"view"}));
  EXPECT_TRUE(new_run.at("run").at("document").at("outputs").empty());
  widget("graph_mode")->index.assign(3); f.drv->frame();
  const auto frozen_outputs = *widget("graph_output_rows")->table;
  for (int i = 0; i < frozen_outputs.rows; ++i) {
    if (frozen_outputs.cell(i, 0) == "view") { EXPECT_EQ(frozen_outputs.cell(i, 1), store().tr("analysis_graph.requested")); }
  }
}

TEST_F(AnalysisOutputsEditorPython, ExternalRevisionPreservesCombinedDraftWithoutRebasingOrSendingAStaleSave)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(output("image", true));
  const auto save_old = widget("analysis_parameters_save")->on_click;
  const auto clear_old = widget("analysis_outputs_clear")->on_click;
  const Json commands = Json::array({{{"op", "create_table"}, {"name", "Other work"}}}); Json changed;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", commands}}, changed));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  save_old(); clear_old(); f.drv->frame();
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "2");
  EXPECT_TRUE(widget("analysis_output_requested")->boolean.value());
  EXPECT_FALSE(widget("analysis_output_choices")->enabled); EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_output_choices") && widget("analysis_output_choices")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(row("component"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1");
  ASSERT_NO_FATAL_FAILURE(output("image", false));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
}

} // namespace
} // namespace stk::app
