/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_analysis_runs.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include "scalar_volume_support.hh"

#include <algorithm>
#include <cmath>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
using Reply = bridge::Result<Json>;
namespace fs = std::filesystem;
constexpr const char *kAnalysisId = "28cb6aa8-55fa-4e48-9a1e-33e6bac14001";

// Real bridge/storage/worker, with portable fault injection only around response delivery.
// The orphan mode represents a process that claimed work and disappeared before completion.
constexpr const char *kRunBridge = R"PY(
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

def mode():
    path = control / 'mode'
    return path.read_text(encoding='utf-8') if path.exists() else ''

def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}, ensure_ascii=True) + '\n')
    if method == 'project.analysis_runs.get' and mode() == 'orphan':
        self.projects._get(params['handle']).analysis_runs._claim(
            params['run_id'], executor_id='6a731019-49cd-48ef-a508-8ee3fc2cda3e')
    if method == 'project.snapshot' and mode() == 'legacy':
        store = self.projects._get(params['handle'])
        with store._connect(write=True) as database:
            database.execute('DROP TABLE analysis_run_events')
            database.execute('DROP TABLE analysis_run_plans')
            database.execute('PRAGMA user_version=8')
        (control / 'mode').write_text('', encoding='utf-8')
    return original_run(self, identity, method, params)

def send(self, message, method=None):
    setting = mode()
    if method == 'project.analysis_runs.prepare' and 'result' in message:
        if setting == 'lost':
            return
        if setting == 'malformed':
            message = copy.deepcopy(message)
            message['result']['run']['id'] = '00000000-0000-4000-8000-000000000000'
    if method == 'project.analysis_runs.get' and 'result' in message and setting == 'hold':
        (control / 'held').write_text('ready', encoding='utf-8')
        while not (control / 'release').exists():
            if self.closing.wait(0.01):
                return
    return original_send(self, message, method)

Bridge._run, Bridge.send = run, send
main()
)PY";

class ProjectAnalysisRunsPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"analysis-runs-native"};
  wmtest::AppFixture f{"en", 1, 1440, 1200};
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectAnalysisRuns> runs;
  Json document, bindings, snapshot;
  std::string record_id, snapshot_id;
  int64_t revision = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  ViewerState &viewer() { return store().viewer(); }
  std::string handle() { return project().project()->handle; }

  void write(const fs::path &path, const std::string &value)
  {
    std::ofstream stream(path, std::ios::binary); stream << value; ASSERT_TRUE(stream.good());
  }
  void mode(const std::string &value) { write(directory.path() / "mode", value); }
  void call(const std::string &method, Json params, Json &out)
  {
    auto result = std::make_shared<std::optional<Reply>>();
    auto future = client->call(method, std::move(params));
    future.then([result](auto value) { *result = std::move(value); });
    const bool finished = loop.pump_until([&] { return result->has_value(); }, 30);
    if (!finished) { future.cancel(); }
    ASSERT_TRUE(finished) << client->bridge_log().text();
    ASSERT_TRUE(result->value().ok()) << result->value().error().describe();
    out = result->value().value();
  }
  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] {
      return (!runs || !runs->busy()) && !project().busy() && !project().recent_loading();
    }, 30)) << (runs ? runs->error() : "") << project().error() << client->bridge_log().text();
  }
  Json calls(const std::string &method)
  {
    Json matches = Json::array(); std::ifstream stream(directory.path() / "calls.jsonl"); std::string line;
    while (std::getline(stream, line)) {
      const auto entry = io::parse_json(line);
      if (entry.at("method") == method) { matches.push_back(entry.at("params")); }
    }
    return matches;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const auto *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for durable analysis runs"; }
    ASSERT_NO_FATAL_FAILURE(write(directory.path() / "bridge.py", kRunBridge));
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), directory.str(),
        "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    options.executor = loop.executor(); options.strict = options.validate = true; options.call_timeout_s = 5;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)) << client->bridge_log().text();
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "Analysis runs"));
    ASSERT_NO_FATAL_FAILURE(settled()); ASSERT_TRUE(project().loaded());
    ASSERT_EQ(project().project()->format_version, 9);
    ASSERT_TRUE(apptest::write_signed_field(directory.path() / "signed.dat"));
    Json indexed, captured, saved;
    ASSERT_NO_FATAL_FAILURE(call("project.files.index", {{"handle", handle()}, {"expected_revision", 0},
        {"paths", Json::array({core::path_to_utf8(directory.path() / "signed.dat")})}}, indexed));
    record_id = indexed.at("record_ids")[0].get<std::string>();
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()}, {"expected_revision", indexed.at("revision")},
        {"record_ids", Json::array({record_id})}}, captured));
    snapshot = captured.at("snapshot"); snapshot_id = snapshot.at("id").get<std::string>();
    document = {{"format", "stk.analysis-document/1"},
        {"graph", io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
        {"parameters", {{"path", "input.dat"}, {"field", "input"}, {"component", 1}, {"unit", nullptr}}},
        {"outputs", Json::array({"view"})}};
    bindings = {{"data", {{"input.dat", record_id}}}};
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", kAnalysisId},
        {"name", "Frozen scalar"}, {"document", document}, {"expected_revision", captured.at("revision")}}, saved));
    revision = saved.at("revision").get<int64_t>();
    project().refresh();
  ASSERT_NO_FATAL_FAILURE(settled());
    runs = std::make_unique<ProjectAnalysisRuns>(store()); ASSERT_TRUE(runs->supported());
    viewer().set_auto_evaluate(false); viewer().prefetch_neighbours = false;
  }
  void TearDown() override
  {
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating());
    runs.reset(); viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  void prepare()
  {
    ASSERT_TRUE(runs->prepare(kAnalysisId, revision, snapshot_id, bindings));
    ASSERT_NO_FATAL_FAILURE(settled()); ASSERT_TRUE(runs->error().empty()) << runs->error();
    ASSERT_FALSE(runs->run().is_null()); ASSERT_EQ(runs->run().at("status"), "prepared");
  }
  void execute()
  {
    ASSERT_TRUE(runs->start());
  ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_TRUE(runs->error().empty()) << runs->error();
    ASSERT_TRUE(loop.pump_until([&] {
      const auto time = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
      runs->pump(time);
      const auto status = io::get_string(runs->run(), "status");
      return status != "prepared" && status != "running" && status != "cancel_requested";
    }, 60)) << runs->error() << client->bridge_log().text();
  }
  void update_document()
  {
    Json result;
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", kAnalysisId},
        {"name", "Frozen scalar"}, {"document", document}, {"expected_revision", revision}}, result));
    revision = result.at("revision").get<int64_t>();
    project().refresh();
  ASSERT_NO_FATAL_FAILURE(settled());
  }
  std::shared_ptr<const io::Payload> result_payload()
  {
    if (!runs->read_result()) { ADD_FAILURE() << "Result read not accepted"; return nullptr; }
    if (!loop.pump_until([&] { return !runs->busy(); }, 30)) { ADD_FAILURE() << "Result read timed out"; return nullptr; }
    EXPECT_TRUE(runs->error().empty()) << runs->error();
    return runs->decode_payload("view");
  }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }
  void toggle(const char *key)
  {
    const auto *value = widget(key); ASSERT_NE(value, nullptr);
    const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
    f.screen.ui()->handle_event(ui::Event::mouse_down(center));
    f.screen.ui()->handle_event(ui::Event::mouse_up(center)); f.drv->frame();
  }
  void open_runs_ui()
  {
    auto &area = f.area("a2");
    ASSERT_TRUE(area.set_tab_type(0, kEditorAnalysisGraph));
    ASSERT_TRUE(area.editor().load_state({{"saved", true}}));
    f.screen.set_maximized(&area); area.find_region(EditorArea::kSidebar)->set_size_1x(440); f.drv->frame();
    ASSERT_NE(widget("analysis_list"), nullptr); widget("analysis_list")->on_click();
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("analysis_documents") != nullptr; }, 30));
    widget("analysis_documents")->table->selected.assign(0);
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); return widget("analysis_rename") && widget("analysis_rename")->enabled;
    }, 30));
    ASSERT_NE(widget("analysis_saved_section"), nullptr);
    widget("analysis_saved_section")->index.assign(1); f.drv->frame();
    ASSERT_NE(widget("analysis_run_snapshots"), nullptr);
  }
  void map_file_ui()
  {
    widget("analysis_run_snapshots")->on_click();
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); return widget("analysis_run_snapshot") && widget("analysis_run_snapshot")->items.size() == 2;
    }, 30));
    widget("analysis_run_snapshot")->index.assign(1); f.drv->frame();
    ASSERT_NE(widget("analysis_run_file"), nullptr); widget("analysis_run_file")->index.assign(1); f.drv->frame();
    ASSERT_NE(widget("analysis_run_path"), nullptr); widget("analysis_run_path")->string.assign("input.dat"); f.drv->frame();
    widget("analysis_run_add_file")->on_click(); f.drv->frame();
    ASSERT_NE(widget("analysis_run_bindings"), nullptr); ASSERT_EQ(widget("analysis_run_bindings")->table->rows, 1);
    ASSERT_NE(widget("analysis_run_prepare"), nullptr); ASSERT_TRUE(widget("analysis_run_prepare")->enabled);
  }
};

TEST_F(ProjectAnalysisRunsPython, PrepareFreezesExactParametersWithoutRevisionHistoryOrViewerChanges)
{
  const auto viewer_before = viewer().graph_inspection();
  Json before, after;
  ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", handle()}}, before));
  const auto calls_before = client->stats().calls_sent;
  runs->sync(); EXPECT_TRUE(std::isinf(runs->pump(10)));
  EXPECT_EQ(client->stats().calls_sent, calls_before);
  ASSERT_NO_FATAL_FAILURE(prepare());
  EXPECT_EQ(io::python_json_dumps(runs->run().at("document"), true, true), io::python_json_dumps(document, true, true));
  EXPECT_TRUE(runs->run().at("document").at("parameters").at("unit").is_null());
  EXPECT_EQ(runs->run().at("bindings").at("data").at("input.dat").at("record_id"), record_id);
  EXPECT_EQ(runs->run().at("source_revision"), revision);
  ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", handle()}}, after));
  EXPECT_EQ(after, before); EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(viewer().graph_inspection(), viewer_before);
  EXPECT_TRUE(calls("project.analysis_runs.start").empty()); EXPECT_TRUE(calls("graph.evaluate").empty());
}

TEST_F(ProjectAnalysisRunsPython, CancelPreparedAndReopenReadsTheSameDurableRunWithoutStarting)
{
  ASSERT_NO_FATAL_FAILURE(prepare()); const auto id = runs->run().at("id").get<std::string>();
  ASSERT_TRUE(runs->cancel());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(runs->run().at("status"), "cancelled"); EXPECT_FALSE(runs->start());
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(settled()); runs->sync();
  EXPECT_TRUE(runs->run().is_null());
  ASSERT_TRUE(project().open(directory.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settled()); runs->sync();
  EXPECT_TRUE(runs->run().is_null());
  ASSERT_TRUE(runs->load_page());
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_EQ(runs->page().at("runs").size(), 1u); EXPECT_EQ(runs->page().at("runs")[0].at("id"), id);
  ASSERT_TRUE(runs->load(id));
  ASSERT_NO_FATAL_FAILURE(settled()); EXPECT_EQ(runs->run().at("status"), "cancelled");
  EXPECT_TRUE(calls("project.analysis_runs.start").empty()); EXPECT_TRUE(calls("project.analysis_runs.recover").empty());
}

TEST_F(ProjectAnalysisRunsPython, ExplicitExecutionUsesSnapshotAfterOriginalChangesAndDecodesOnlySelectedOutput)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(write(directory.path() / "signed.dat", "original has changed"));
  ASSERT_NO_FATAL_FAILURE(execute());
  ASSERT_EQ(runs->run().at("status"), "succeeded") << runs->run().dump();
  ASSERT_TRUE(runs->run().at("result").at("has_payload").get<bool>());
  EXPECT_FALSE(runs->start()); EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u);
  auto payload = result_payload(); ASSERT_NE(payload, nullptr);
  ASSERT_NE(payload->layer("volume"), nullptr);
  EXPECT_EQ(payload->layer("volume")->at("value_range"), Json::array({-9.0, 14.0}));
  EXPECT_EQ(runs->payload_outputs(), std::vector<std::string>{"view"});
  EXPECT_EQ(viewer().source().kind, SourceKind::None); EXPECT_FALSE(viewer().payload());
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(ProjectAnalysisRunsPython, EmptyOutputSelectionDoesNotExpandToAllGraphOutputs)
{
  document["outputs"] = Json::array();
  ASSERT_NO_FATAL_FAILURE(update_document());
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  ASSERT_EQ(runs->run().at("status"), "succeeded") << runs->run().dump();
  EXPECT_FALSE(runs->run().at("result").at("has_payload").get<bool>());
  ASSERT_TRUE(runs->read_result());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(runs->result().at("outputs").empty()); EXPECT_TRUE(runs->payload_outputs().empty());
  EXPECT_EQ(runs->result().at("evaluated"), Json::array());
}

TEST_F(ProjectAnalysisRunsPython, PartialOutputFailureRemainsFailedWhileVerifiedPayloadCanBeRead)
{
  document["graph"]["nodes"].push_back({{"id", "bad_component"}, {"type", "stk.filter.calculator@1"},
      {"inputs", {{"in", {{"from", "src.out"}}}}},
      {"params", {{"operation", "component"}, {"field", "input"}, {"component", 4095}}}});
  document["graph"]["outputs"]["bad"] = "bad_component.out";
  document["outputs"].push_back("bad");
  ASSERT_NO_FATAL_FAILURE(update_document());
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  ASSERT_EQ(runs->run().at("status"), "failed") << runs->run().dump();
  ASSERT_TRUE(runs->run().at("result").is_object()); EXPECT_TRUE(runs->run().at("result").at("has_errors").get<bool>());
  ASSERT_NE(result_payload(), nullptr);
  EXPECT_FALSE(runs->result().at("errors").empty()); EXPECT_FALSE(runs->start());
}

TEST_F(ProjectAnalysisRunsPython, LostPrepareReplyKeepsIdentityForReadBackWithoutResubmission)
{
  ASSERT_NO_FATAL_FAILURE(mode("lost"));
  ASSERT_TRUE(runs->prepare(kAnalysisId, revision, snapshot_id, bindings));
  const auto id = runs->pending_id(); ASSERT_FALSE(id.empty());
  ASSERT_NO_FATAL_FAILURE(settled()); EXPECT_TRUE(runs->uncertain());
  EXPECT_FALSE(runs->prepare(kAnalysisId, revision, snapshot_id, bindings));
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(runs->check_pending());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_FALSE(runs->uncertain()); EXPECT_EQ(runs->run().at("id"), id);
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u); EXPECT_TRUE(calls("project.analysis_runs.start").empty());
}

TEST_F(ProjectAnalysisRunsPython, MalformedPrepareReplyIsNotAcceptedAsAnotherRun)
{
  ASSERT_NO_FATAL_FAILURE(mode("malformed"));
  ASSERT_TRUE(runs->prepare(kAnalysisId, revision, snapshot_id, bindings));
  const auto id = runs->pending_id();
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(runs->uncertain()); EXPECT_TRUE(runs->run().is_null());
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(runs->check_pending());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(runs->run().at("id"), id); EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
}

TEST_F(ProjectAnalysisRunsPython, ReadPollingIsBoundedAndOrphanRecoveryNeverReplays)
{
  ASSERT_NO_FATAL_FAILURE(prepare()); const auto id = runs->run().at("id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(mode("orphan")); ASSERT_TRUE(runs->load(id));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_EQ(runs->run().at("status"), "running");
  ASSERT_NO_FATAL_FAILURE(mode(""));
  EXPECT_TRUE(std::isfinite(runs->pump(100)));
  runs->pump(101.1);
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(std::isinf(runs->pump(191))); EXPECT_FALSE(runs->following());
  const auto reads = calls("project.analysis_runs.get").size();
  runs->pump(300); EXPECT_EQ(calls("project.analysis_runs.get").size(), reads);
  EXPECT_TRUE(calls("project.analysis_runs.start").empty()); EXPECT_TRUE(calls("project.analysis_runs.recover").empty());
  ASSERT_TRUE(runs->recover());
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(runs->run().at("status"), "unknown"); EXPECT_FALSE(runs->start());
  EXPECT_EQ(calls("project.analysis_runs.recover").size(), 1u);
}

TEST_F(ProjectAnalysisRunsPython, LateReadAfterProjectCloseCannotAdoptState)
{
  ASSERT_NO_FATAL_FAILURE(prepare()); const auto id = runs->run().at("id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(mode("hold")); ASSERT_TRUE(runs->load(id));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
  runs->sync(); EXPECT_TRUE(runs->run().is_null()); const auto epoch = runs->epoch();
  ASSERT_NO_FATAL_FAILURE(write(directory.path() / "release", "go"));
  Json barrier;
  ASSERT_NO_FATAL_FAILURE(call("graph.catalog", Json::object(), barrier));
  loop.run_ready();
  EXPECT_EQ(runs->epoch(), epoch); EXPECT_TRUE(runs->run().is_null());
  runs.reset(); loop.run_ready(); EXPECT_TRUE(calls("project.analysis_runs.start").empty());
}

TEST_F(ProjectAnalysisRunsPython, FormatEightRequiresAnExplicitVerifiedBackupUpgrade)
{
  ASSERT_NO_FATAL_FAILURE(mode("legacy")); project().refresh();
  ASSERT_NO_FATAL_FAILURE(settled());
  runs->sync(); ASSERT_EQ(project().project()->format_version, 8); EXPECT_FALSE(runs->supported());
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject)); f.screen.set_maximized(&area);
  f.drv->frame(); const auto *upgrade = f.screen.ui()->find("a2/main/upgrade_project"); ASSERT_NE(upgrade, nullptr);
  EXPECT_EQ(project().project()->format_version, 8); EXPECT_TRUE(calls("project.upgrade").empty());
  upgrade->on_click();
  ASSERT_NO_FATAL_FAILURE(settled()); runs->sync();
  EXPECT_EQ(project().project()->format_version, 9); EXPECT_TRUE(runs->supported());
  size_t backups = 0;
  for (const auto &entry : fs::directory_iterator(directory.path() / "project/backups")) {
    if (entry.path().extension() == ".sqlite3") { ++backups; }
  }
  EXPECT_EQ(backups, 1u); EXPECT_EQ(project().project()->revision, revision + 1);
}

TEST_F(ProjectAnalysisRunsPython, DestroyedControllerRejectsAReadReleasedAfterItsLifetime)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  const auto id = runs->run().at("id").get<std::string>();
  const auto before = viewer().graph_inspection();
  ASSERT_NO_FATAL_FAILURE(mode("hold"));
  ASSERT_TRUE(runs->load(id));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  runs.reset();
  ASSERT_NO_FATAL_FAILURE(write(directory.path() / "release", "go"));
  Json barrier;
  ASSERT_NO_FATAL_FAILURE(call("graph.catalog", Json::object(), barrier));
  loop.run_ready();
  EXPECT_EQ(viewer().graph_inspection(), before);
  EXPECT_TRUE(calls("project.analysis_runs.start").empty());
}

TEST_F(ProjectAnalysisRunsPython, DetachedBridgeEpochRejectsAnOldReadEvenIfTheSameClientReturns)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  const auto id = runs->run().at("id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(mode("hold"));
  ASSERT_TRUE(runs->load(id));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  const auto old_epoch = runs->epoch();
  store().set_bridge(nullptr); runs->sync();
  EXPECT_GT(runs->epoch(), old_epoch); EXPECT_TRUE(runs->run().is_null());
  store().set_bridge(client.get()); project().sync(); runs->sync();
  ASSERT_NO_FATAL_FAILURE(write(directory.path() / "release", "go"));
  Json barrier;
  ASSERT_NO_FATAL_FAILURE(call("graph.catalog", Json::object(), barrier));
  loop.run_ready();
  EXPECT_TRUE(runs->run().is_null()); EXPECT_FALSE(runs->following());
  EXPECT_TRUE(calls("project.analysis_runs.start").empty());
}

TEST_F(ProjectAnalysisRunsPython, ResultImportIsDeferredAndOccupiedViewerPreservesSourceAndLayout)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  const auto payload = result_payload(); ASSERT_NE(payload, nullptr);
  const auto target = f.shell->analysis_payload_target(&f.screen); ASSERT_TRUE(target.ok());
  auto reply = std::make_shared<std::optional<Reply>>();
  f.shell->open_analysis_payload(&f.screen, handle(), target.value(), payload, "Frozen scalar / view",
      [] { return true; }, [reply](auto result) { *reply = std::move(result); });
  EXPECT_FALSE(viewer().payload()); EXPECT_FALSE(reply->has_value());
  f.screen.run_deferred(); ASSERT_TRUE(reply->has_value()); ASSERT_TRUE(reply->value().ok());
  EXPECT_EQ(viewer().base_payload(), payload); EXPECT_EQ(viewer().source().kind, SourceKind::Payload);
  EXPECT_FALSE(viewer().graph_inspection()->shown_configuration); EXPECT_FALSE(viewer().graph_inspection()->desired);
  const auto layout = f.screen.to_json();
  const auto source = viewer().source().key();
  const auto version = viewer().version();
  EXPECT_FALSE(f.shell->analysis_payload_target(&f.screen).ok());
  auto denied = std::make_shared<std::optional<Reply>>();
  f.shell->open_analysis_payload(&f.screen, handle(), version, payload, "Another result", [] { return true; },
      [denied](auto result) { *denied = std::move(result); });
  ASSERT_TRUE(denied->has_value()); EXPECT_FALSE(denied->value().ok());
  EXPECT_EQ(viewer().source().key(), source); EXPECT_EQ(viewer().version(), version); EXPECT_EQ(f.screen.to_json(), layout);
}

TEST_F(ProjectAnalysisRunsPython, ResultImportRefusesChangedThenClearedViewerAndExpiredCaller)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  const auto payload = result_payload(); ASSERT_NE(payload, nullptr);
  const auto target = f.shell->analysis_payload_target(&f.screen); ASSERT_TRUE(target.ok());
  const auto layout = f.screen.to_json();
  auto reply = std::make_shared<std::optional<Reply>>();
  f.shell->open_analysis_payload(&f.screen, handle(), target.value(), payload, "Saved result", [] { return true; },
      [reply](auto result) { *reply = std::move(result); });
  viewer().open_payload(payload, "Intervening result"); viewer().close(); f.screen.run_deferred();
  ASSERT_TRUE(reply->has_value()); EXPECT_FALSE(reply->value().ok());
  EXPECT_EQ(reply->value().error().code, bridge::ErrorCode::Conflict);
  EXPECT_FALSE(viewer().payload()); EXPECT_EQ(f.screen.to_json(), layout);
  bool live = true; reply->reset();
  f.shell->open_analysis_payload(&f.screen, handle(), viewer().version(), payload, "Saved result", [&live] { return live; },
      [reply](auto result) { *reply = std::move(result); });
  live = false; f.screen.run_deferred(); EXPECT_FALSE(reply->has_value()); EXPECT_FALSE(viewer().payload());
}

TEST_F(ProjectAnalysisRunsPython, ResultImportPreflightsCapacityAndAllInstalledWindowText)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  const auto payload = result_payload(); ASSERT_NE(payload, nullptr);
  for (auto *base : f.screen.areas()) {
    auto *area = dynamic_cast<EditorArea *>(base); ASSERT_NE(area, nullptr);
    for (int index = 0; index < area->tab_count(); ++index) { ASSERT_TRUE(area->set_tab_type(index, kEditorLogs)); }
    while (area->tab_count() < 16) { ASSERT_TRUE(area->add_tab(kEditorLogs, false)); }
  }
  const auto layout = f.screen.to_json();
  EXPECT_FALSE(f.shell->analysis_payload_target(&f.screen).ok());
  auto reply = std::make_shared<std::optional<Reply>>();
  f.shell->open_analysis_payload(&f.screen, handle(), viewer().version(), payload, "Saved result", [] { return true; },
      [reply](auto result) { *reply = std::move(result); });
  ASSERT_TRUE(reply->has_value()); EXPECT_FALSE(reply->value().ok()); EXPECT_EQ(f.screen.to_json(), layout);
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorViewer));
  EXPECT_TRUE(f.shell->analysis_payload_target(&f.screen).ok());
  struct Extra {
    AppShell &shell; wm::Screen screen; wmtest::ScreenDriver driver;
    explicit Extra(AppShell &owner) : shell(owner), driver(screen, 1000, 900, 1) {
      shell.install(screen, nullptr); shell.build_default_layout(screen);
    }
    ~Extra() { shell.forget(screen); }
  } extra(*f.shell);
  auto *area = dynamic_cast<EditorArea *>(extra.screen.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorPython)); extra.screen.set_maximized(area); extra.driver.frame();
  const auto *input = extra.screen.ui()->find("python_source"); ASSERT_NE(input, nullptr);
  const auto rect = input->rect;
  const auto target = f.shell->analysis_payload_target(&f.screen); ASSERT_TRUE(target.ok()); reply->reset();
  f.shell->open_analysis_payload(&f.screen, handle(), target.value(), payload, "Saved result", [] { return true; },
      [reply](auto result) { *reply = std::move(result); });
  extra.driver.click(int(rect.cx()), extra.screen.rect().ymax - 1 - int(rect.cy()));
  extra.driver.key(wm::Key::Unknown, wm::ModNone, "unfinished"); ASSERT_TRUE(extra.screen.ui()->text_input_active());
  f.screen.run_deferred(); ASSERT_TRUE(reply->has_value()); EXPECT_FALSE(reply->value().ok());
  EXPECT_EQ(reply->value().error().code, bridge::ErrorCode::Busy); EXPECT_FALSE(viewer().payload());
  ASSERT_NE(extra.screen.ui()->edit_state(), nullptr); EXPECT_NE(extra.screen.ui()->edit_state()->text().find("unfinished"), std::string::npos);
  EXPECT_FALSE(f.shell->analysis_payload_target(nullptr).ok());
}

TEST_F(ProjectAnalysisRunsPython, SavedRunsUiPreparesInspectableMappingsAndCancellationDoesNotExecute)
{
  document["parameters"]["future_note"] = "null";
  ASSERT_NO_FATAL_FAILURE(update_document());
  ASSERT_NO_FATAL_FAILURE(open_runs_ui());
  EXPECT_TRUE(calls("project.snapshots.list").empty()); EXPECT_TRUE(calls("project.analysis_runs.list").empty());
  EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
  ASSERT_NO_FATAL_FAILURE(map_file_ui());
  const auto *mapping = widget("analysis_run_bindings");
  EXPECT_EQ(mapping->table->cell(0, 0), "data"); EXPECT_EQ(mapping->table->cell(0, 1), "input.dat");
  EXPECT_FALSE(widget("analysis_run_snapshot")->enabled);
  widget("analysis_run_prepare")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return widget("analysis_run_start") && widget("analysis_run_start")->enabled;
  }, 30)) << client->bridge_log().text();
  EXPECT_EQ(calls("project.analysis_runs.prepare").size(), 1u);
  EXPECT_EQ(calls("project.analysis_runs.prepare")[0].at("bindings"), bindings);
  EXPECT_TRUE(calls("project.analysis_runs.start").empty()); EXPECT_EQ(project().project()->revision, revision);
  widget("analysis_run_cancel")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return widget("analysis_run_start") && !widget("analysis_run_start")->enabled &&
        widget("analysis_run_refresh") && widget("analysis_run_refresh")->enabled;
  }, 30));
  EXPECT_TRUE(calls("project.analysis_runs.start").empty()); EXPECT_TRUE(calls("graph.evaluate").empty());
  EXPECT_FALSE(viewer().payload());
  ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_prepare_panel"));
  ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_history"));
  ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_frozen"));
  ASSERT_NE(widget("analysis_run_frozen_parameters"), nullptr);
  const auto &parameters = *widget("analysis_run_frozen_parameters")->table;
  ASSERT_EQ(parameters.rows, 5);
  int null_row = -1, string_row = -1;
  for (int row = 0; row < parameters.rows; ++row) {
    if (parameters.cell(row, 0) == "unit") { null_row = row; }
    if (parameters.cell(row, 0) == "future_note") { string_row = row; }
  }
  ASSERT_GE(null_row, 0); ASSERT_GE(string_row, 0);
  EXPECT_EQ(parameters.cell(null_row, 1), store().tr("discussion.cells.null"));
  EXPECT_EQ(parameters.cell(null_row, 2), "null");
  EXPECT_EQ(parameters.cell(string_row, 1), store().tr("project.type.text"));
  EXPECT_EQ(parameters.cell(string_row, 2), "null");
  ASSERT_NE(widget("analysis_run_frozen_outputs"), nullptr);
  EXPECT_EQ(widget("analysis_run_frozen_outputs")->table->cell(0, 0), "view");
}

TEST_F(ProjectAnalysisRunsPython, RetainedPrepareButtonRejectsChangedMappingsAndProjectRevision)
{
  ASSERT_NO_FATAL_FAILURE(open_runs_ui());
  ASSERT_NO_FATAL_FAILURE(map_file_ui());
  const auto prepare_old = widget("analysis_run_prepare")->on_click;
  widget("analysis_run_clear_files")->on_click(); prepare_old();
  EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
  f.drv->frame(); widget("analysis_run_add_file")->on_click(); f.drv->frame();
  ASSERT_TRUE(widget("analysis_run_prepare")->enabled);
  const auto stale = widget("analysis_run_prepare")->on_click;
  Json changed;
  const Json commands = Json::array({{{"op", "create_table"}, {"name", "Unrelated edit"}}});
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", commands}}, changed));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(settled()); stale(); f.drv->frame();
  EXPECT_TRUE(calls("project.analysis_runs.prepare").empty()); EXPECT_FALSE(widget("analysis_run_prepare")->enabled);
}

TEST_F(ProjectAnalysisRunsPython, ExplicitPayloadSelectionAndShowAreRequiredAfterUiResultRead)
{
  ASSERT_NO_FATAL_FAILURE(prepare());
  ASSERT_NO_FATAL_FAILURE(execute());
  ASSERT_EQ(runs->run().at("status"), "succeeded");
  ASSERT_NO_FATAL_FAILURE(open_runs_ui());
  ASSERT_NE(widget("analysis_run_list"), nullptr); widget("analysis_run_list")->on_click();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("analysis_run_rows") != nullptr; }, 30));
  widget("analysis_run_rows")->table->selected.assign(0);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return widget("analysis_run_read_result") && widget("analysis_run_read_result")->enabled;
  }, 30));
  EXPECT_FALSE(viewer().payload()); EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u);
  widget("analysis_run_read_result")->on_click();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("analysis_run_output") != nullptr; }, 30));
  EXPECT_EQ(widget("analysis_run_output")->index.value(), 0); EXPECT_FALSE(widget("analysis_run_show")->enabled);
  EXPECT_FALSE(viewer().payload());
  widget("analysis_run_output")->index.assign(1); f.drv->frame();
  ASSERT_TRUE(widget("analysis_run_show")->enabled); widget("analysis_run_show")->on_click();
  EXPECT_FALSE(viewer().payload()); f.screen.run_deferred();
  ASSERT_TRUE(viewer().payload()); EXPECT_EQ(viewer().source().kind, SourceKind::Payload);
  EXPECT_FALSE(viewer().graph_inspection()->shown_configuration);
  EXPECT_EQ(calls("project.analysis_runs.start").size(), 1u); EXPECT_TRUE(calls("graph.evaluate").empty());
}

TEST_F(ProjectAnalysisRunsPython, OccupiedUnrenderedViewerIntentAndClosedTargetNeverGetReplaced)
{
  const auto metadata = io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json");
  viewer().set_metadata({{"presets", Json::array({metadata})}},
      io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json"));
  store().set_bridge(nullptr);
  ASSERT_TRUE(viewer().open_path(core::path_to_utf8(directory.path() / "signed.dat"), "scalar-volume"));
  viewer().set_parameter("component", ui::FormValue::number(2));
  store().set_bridge(client.get());
  const auto intent = viewer().graph_inspection(); ASSERT_TRUE(intent->desired); ASSERT_FALSE(viewer().payload());
  EXPECT_FALSE(f.shell->analysis_payload_target(&f.screen).ok()); EXPECT_EQ(viewer().graph_inspection(), intent);
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorViewer));
  EditorContext context{store(), area}; std::vector<ui::MenuEntry> entries;
  area.editor().menu_entries(entries, context);
  auto close = std::find_if(entries.begin(), entries.end(), [&](const auto &entry) {
    return entry.text == store().tr("viewer.action.close");
  });
  ASSERT_NE(close, entries.end()); ASSERT_TRUE(close->enabled); ASSERT_TRUE(close->action);
  close->action(); EXPECT_EQ(viewer().source().kind, SourceKind::None); EXPECT_FALSE(viewer().payload());
  EXPECT_TRUE(f.shell->analysis_payload_target(&f.screen).ok());
  entries.clear(); area.editor().menu_entries(entries, context);
  close = std::find_if(entries.begin(), entries.end(), [&](const auto &entry) {
    return entry.text == store().tr("viewer.action.close");
  });
  ASSERT_NE(close, entries.end()); EXPECT_FALSE(close->enabled);
  wm::Screen other; f.shell->install(other, nullptr); f.shell->build_default_layout(other); f.shell->forget(other);
  EXPECT_FALSE(f.shell->analysis_payload_target(&other).ok()); EXPECT_FALSE(viewer().payload());
}

}  // namespace
}  // namespace stk::app
