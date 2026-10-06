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
control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run = Bridge._run
def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}, ensure_ascii=True) + '\n')
    return original_run(self, identity, method, params)
Bridge._run = run
main()
)PY";

class AnalysisGraphRunEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-frozen-run-ui"};
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
  void TearDown() override {
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating()); EXPECT_FALSE(viewer().payload());
    EXPECT_TRUE(calls("graph.evaluate").empty());
    EXPECT_TRUE(calls("project.analysis_runs.result").empty());
    EXPECT_TRUE(calls("project.snapshots.resolve").empty());
    EXPECT_TRUE(calls("project.analysis_runs.start").empty());
    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisGraphRunEditorPython, ExplicitInspectionCopiesTypedDefinitionWithoutReadingFilesOrSendingRequests)
{
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(run_id));
  ASSERT_TRUE(fs::remove(directory.path() / "input.dat"));
  const auto sent = client->stats().calls_sent;
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
  ASSERT_EQ(widget("graph_mode")->index.value(), 3);
  ASSERT_NO_FATAL_FAILURE(frozen_parameters());
  EXPECT_EQ(client->stats().calls_sent, sent);
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.run_id"))), run_id);
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.plan_hash"))), frozen.at("plan_sha256").get<std::string>());
  ASSERT_NE(widget("graph_run_files"), nullptr);
  EXPECT_EQ(widget("graph_run_files")->table->cell(0, 1), "input.dat");
  EXPECT_EQ(cell("graph_parameter_values", "component"), "1");
  EXPECT_EQ(cell("graph_parameter_values", "unit"), "null");
  EXPECT_EQ(cell("graph_parameter_values", "null_text"), "\"null\"");
  EXPECT_EQ(cell("graph_parameter_values", "\"\""), "true");
  EXPECT_NE(cell("graph_parameter_values", "precision_record").find("18446744073709551615"), std::string::npos);
  if (!widget("graph_output_rows")) { ASSERT_NO_FATAL_FAILURE(toggle("graph_outputs")); }
  ASSERT_NE(widget("graph_output_rows"), nullptr); EXPECT_EQ(widget("graph_output_rows")->table->columns.size(), 3u);
  EXPECT_EQ(cell("graph_output_rows", "view", 1), store().tr("analysis_graph.requested"));
  EXPECT_EQ(widget("analysis_parameters"), nullptr); EXPECT_EQ(widget("analysis_save"), nullptr);
  EXPECT_EQ(widget("analysis_rename"), nullptr); EXPECT_EQ(widget("analysis_run_prepare"), nullptr);
  EXPECT_EQ(widget("analysis_run_read_result"), nullptr);
}

TEST_F(AnalysisGraphRunEditorPython, DirtyDraftAndInvalidRawBufferSurviveFrozenInspectionAndReturn)
{
  ASSERT_NO_FATAL_FAILURE(edit("component", "2"));
  ASSERT_NO_FATAL_FAILURE(type("1e"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  ASSERT_NO_FATAL_FAILURE(inspect());
  ASSERT_NO_FATAL_FAILURE(frozen_parameters());
  EXPECT_EQ(cell("graph_parameter_values", "component"), "1");
  EXPECT_EQ(widget("analysis_parameter_value"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_return_saved"));
  ASSERT_NE(widget("analysis_parameter_value"), nullptr);
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_EQ(cell("analysis_parameters", "component"), "2");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
  EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_discard"));
  ASSERT_NO_FATAL_FAILURE(row("component"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1");
}

TEST_F(AnalysisGraphRunEditorPython, RetainedModeAndInspectCallbacksPreserveActiveInputAcrossInstalledWindows)
{
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(run_id));
  const auto inspect_old = widget("analysis_run_inspect")->on_click;
  const auto mode_old = widget("graph_mode")->index;
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
  extra.driver.key(wm::Key::Unknown, wm::ModNone, " active input");
  ASSERT_TRUE(extra.screen.ui()->text_input_active());
  const auto typed = extra.screen.ui()->edit_state()->text();
  EXPECT_TRUE(f.shell->text_input_active()); inspect_old(); mode_old.assign(3); f.drv->frame();
  EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  EXPECT_FALSE(widget("analysis_run_inspect")->enabled);
  EXPECT_EQ(extra.screen.ui()->edit_state()->text(), typed);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  // Review source is multiline: plain Enter inserts a newline; primary+Enter commits it.
  extra.driver.key(wm::Key::Enter, primary); extra.driver.frame();
  EXPECT_EQ(project().review_source(), typed);
  EXPECT_FALSE(f.shell->text_input_active()); inspect_old(); f.drv->frame();
  EXPECT_EQ(widget("graph_mode")->index.value(), 3);
}

TEST_F(AnalysisGraphRunEditorPython, RetainedInspectRejectsNewSelectionAndDestroyedEditor)
{
  Json second; ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, second));
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(run_id));
  const auto old = widget("analysis_run_inspect")->on_click;
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id)); old(); f.drv->frame();
  EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.run_id"))), second_run_id);
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  const auto destroyed = widget("analysis_run_inspect")->on_click;
  const auto before = client->stats().calls_sent;
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs)); f.drv->frame(); destroyed(); f.drv->frame();
  EXPECT_EQ(area().editor().type().id, kEditorLogs); EXPECT_EQ(client->stats().calls_sent, before);
}

TEST_F(AnalysisGraphRunEditorPython, FrozenCopyIgnoresSavedRevisionDeletionAndSelectedRunStatus)
{
  ASSERT_NO_FATAL_FAILURE(inspect());
  const auto plan = frozen.at("plan_sha256").get<std::string>();
  auto changed = document; changed["parameters"]["component"] = 2;
  Json updated;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Changed analysis"}, {"document", changed}, {"expected_revision", revision}}, updated));
  revision = updated.at("revision").get<int64_t>(); project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(frozen_parameters());
  EXPECT_EQ(cell("graph_parameter_values", "component"), "1");
  const Json commands = Json::array({{{"op", "delete_record"}, {"id", analysis_id}}}); Json removed, cancelled;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", commands}}, removed));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  EXPECT_EQ(cell("graph_parameter_values", "component"), "1");
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.plan_hash"))), plan);
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.cancel", {{"handle", handle()}, {"run_id", run_id}}, cancelled));
  ASSERT_EQ(cancelled.at("run").at("status"), "cancelled");
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_refresh"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_run_inspect") && widget("analysis_run_inspect")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(choose_mode(3));
  EXPECT_EQ(cell("graph_parameter_values", "component"), "1");
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.plan_hash"))), plan);
}

TEST_F(AnalysisGraphRunEditorPython, SelectingAnotherRunDoesNotAutomaticallyReplacePreviouslyInspectedCopy)
{
  Json second; ASSERT_NO_FATAL_FAILURE(prepare(second_run_id, second));
  ASSERT_NO_FATAL_FAILURE(inspect());
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  ASSERT_NO_FATAL_FAILURE(select_run(second_run_id));
  ASSERT_NO_FATAL_FAILURE(choose_mode(3));
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.run_id"))), run_id);
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
  EXPECT_EQ(cell("graph_run_provenance", std::string(store().tr("analysis_runs.run_id"))), second_run_id);
}

TEST_F(AnalysisGraphRunEditorPython, ProjectReopenClearsInactiveFrozenCopyAndRejectsRetainedInspect)
{
  ASSERT_NO_FATAL_FAILURE(inspect());
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  const auto old = widget("analysis_run_inspect")->on_click;
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  old(); f.drv->frame();
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  old(); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(choose_mode(3));
  EXPECT_EQ(widget("graph_run_provenance"), nullptr); EXPECT_FALSE(widget("graph_fit")->enabled);
  EXPECT_EQ(widget("graph_validate"), nullptr);
}

TEST_F(AnalysisGraphRunEditorPython, NarrowDropdownAndLayoutRestorePersistOnlyModeWithoutLoadingIdentity)
{
  ASSERT_NO_FATAL_FAILURE(inspect());
  const auto persisted = area().editor().save_state();
  EXPECT_EQ(persisted, nlohmann::json({{"displayed", false}, {"run", true}}));
  EXPECT_EQ(widget("graph_mode")->type, ui::WidgetType::Tabs);
  f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, 760, 1200, 1);
  area().find_region(EditorArea::kSidebar)->set_size_1x(385); f.drv->frame();
  ASSERT_NE(widget("graph_mode"), nullptr); EXPECT_EQ(widget("graph_mode")->type, ui::WidgetType::Dropdown);
  EXPECT_EQ(widget("graph_mode")->index.value(), 3);
  const auto sent = client->stats().calls_sent;
  ASSERT_TRUE(area().editor().load_state(persisted)); f.drv->frame();
  EXPECT_EQ(widget("graph_mode")->index.value(), 3); EXPECT_EQ(widget("graph_run_provenance"), nullptr);
  EXPECT_FALSE(widget("graph_fit")->enabled); EXPECT_EQ(client->stats().calls_sent, sent);
  ASSERT_FALSE(area().editor().load_state({{"run", 1}}));
}

TEST_F(AnalysisGraphRunEditorPython, ActiveLocalRawInputBlocksRetainedModeSwitchWithoutCommitting)
{
  const auto mode_old = widget("graph_mode")->index;
  ASSERT_NO_FATAL_FAILURE(row("component"));
  ASSERT_NO_FATAL_FAILURE(type("1e", false));
  mode_old.assign(3); f.drv->frame();
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "1e");
  EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  f.drv->key(wm::Key::Enter); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(choose_mode(3));
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_return_saved"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_FALSE(widget("analysis_parameters_save")->enabled);
}

TEST_F(AnalysisGraphRunEditorPython, RetainedInspectionAndReturnButtonsCannotOverrideNewerSourceNavigation)
{
  ASSERT_NO_FATAL_FAILURE(run_list());
  ASSERT_NO_FATAL_FAILURE(select_run(run_id));
  const auto inspect_old = widget("analysis_run_inspect")->on_click;
  widget("analysis_saved_section")->index.assign(0); f.drv->frame();
  inspect_old(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  inspect_old(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  const auto inspect_before_restore = widget("analysis_run_inspect")->on_click;
  ASSERT_TRUE(area().editor().load_state({{"saved", true}})); f.drv->frame();
  inspect_before_restore(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  const auto inspect_before_mode = widget("analysis_run_inspect")->on_click;
  ASSERT_NO_FATAL_FAILURE(choose_mode(0));
  inspect_before_mode(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 0);
  ASSERT_NO_FATAL_FAILURE(choose_mode(2));
  inspect_before_mode(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_inspect"));
  const auto return_old = widget("analysis_run_return_saved")->on_click;
  ASSERT_NO_FATAL_FAILURE(choose_mode(0));
  return_old(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 0);
  ASSERT_NO_FATAL_FAILURE(choose_mode(3));
  return_old(); f.drv->frame(); EXPECT_EQ(widget("graph_mode")->index.value(), 3);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_return_saved"));
  EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  EXPECT_EQ(widget("analysis_saved_section")->index.value(), 0);
}

} // namespace
} // namespace stk::app
