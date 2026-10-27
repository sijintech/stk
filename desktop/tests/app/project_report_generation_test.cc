/* SPDX-License-Identifier: GPL-2.0-or-later */
// Real stdio bridge, ProjectStore and RequestExecutor; the sole model adapter is
// local, deterministic and cannot make a network connection. No automatic completion
// in Requests.create: only an actual project.requests.start may enter Adapter.send.
#include <gtest/gtest.h>
#include "stk/app/model_settings.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_report_generation.hh"
#include "stk/app/project_reports.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/sha256.hh"
#include "stk/io/graph.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <optional>
#include <tuple>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
const std::string reply_text = "# Original draft\n\nThe frozen observation is 300 K; run status is not a result.\n";
const std::string edited_text = "# Reviewed report\n\nExplicit edit: frozen temperature 300 K.\n\n![Plot](images/plot.png)\n";
constexpr const char *kBridge = R"PY(
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
from uuid import uuid4
import zipfile
import zlib
from suan.project import ProjectStore
from suan.project.contexts import _encode
from suan.project.request_executor import ConfirmedCancellation, RequestExecutor, TextResponse
from suan.desktop_bridge.projects import ProjectSessions
from suan.desktop_bridge.protocol import error_object
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main

control = Path(sys.argv.pop(1))
root = control.parent
trace_lock = threading.Lock()
def trace(method, **fields):
    with trace_lock, control.with_suffix('.calls').open('a', encoding='utf-8') as output:
        output.write(json.dumps(dict(method=method, **fields)) + '\n')
def mode():
    return control.read_text(encoding='utf-8') if control.exists() else ''
def no_network(*args, **kwargs):
    trace('forbidden_network')
    raise AssertionError('This fixture never permits network I/O')
socket.create_connection = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network

def chunk(kind, value):
    return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff)
if not (root / 'seed.json').exists():
    store = ProjectStore.create(root / 'project', 'Report generation fixture')
    table, field, row, context_id = [str(uuid4()) for _ in range(4)]
    store.apply([{'op': 'create_table', 'id': table, 'name': 'Cases'},
        {'op': 'add_field', 'id': field, 'table_id': table, 'name': 'temperature', 'type': 'number', 'unit': 'K'},
        {'op': 'add_record', 'id': row, 'table_id': table},
        {'op': 'set_cell', 'table_id': table, 'record_id': row, 'field_id': field, 'value': 300}], expected_revision=0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff\x00\xff\x00\xff')) + chunk(b'IEND', b'')
    live = store.directory / 'plot.png'
    live.write_bytes(png)
    indexed = store.files.index([str(live)], expected_revision=1)
    record = indexed['record_ids'][0]
    snapshot = store.snapshots.capture([record], expected_revision=indexed['revision'])['snapshot']
    simulation = store.runs.prepare([{'table_id': table, 'record_id': row,
        'spec': {'workspace_id': 'a' * 32, 'argv': ['{python}', '-c', 'pass']}}],
        connection='runtime:Fixture', connection_identity='a' * 16,
        expected_revision=store.info()['revision'])['run_ids'][0]
    analysis, analysis_run, workflow, workflow_run = [str(uuid4()) for _ in range(4)]
    store.analyses.create('Unexecuted analysis', {'format': 'stk.analysis-document/1',
        'graph': {'schema': 'stk.graph/1', 'nodes': [{'id': 'source', 'type': 'missing.source.node@1',
                  'params': {'binding': 'data'}}], 'outputs': {'view': 'source.payload'}},
        'parameters': {}, 'outputs': ['view']}, analysis_id=analysis, expected_revision=store.info()['revision'])
    store.analysis_runs.prepare(analysis, snapshot['id'], {'data': {'plot.png': record}},
        run_id=analysis_run, expected_revision=store.info()['revision'])
    store.workflows.create('Unexecuted workflow', {'format': 'stk.workflow/1', 'steps': [
        {'id': 'cases', 'kind': 'table', 'ref': {'table': table}},
        {'id': 'simulate', 'kind': 'simulation', 'ref': {'template': 'demo-synthetic/1'},
         'inputs': {'rows': {'from': 'cases.rows'}}, 'parameters': {'temperature': {'$field': field}}}],
        'ui': {}}, workflow_id=workflow, expected_revision=store.info()['revision'])
    store.workflow_runs.prepare(workflow, [row], run_id=workflow_run, expected_revision=store.info()['revision'])
    store.contexts.capture(table, [row], [field], expected_revision=store.info()['revision'],
        title='Frozen 300 K', context_id=context_id)
    seed = {'table': table, 'field': field, 'row': row, 'context': context_id,
        'snapshot': snapshot['id'], 'asset': record, 'png_sha256': hashlib.sha256(png).hexdigest(),
        'runs': [{'kind': kind, 'id': identity} for kind, identity in
                 [('simulation_run', simulation), ('analysis_run', analysis_run), ('workflow_run', workflow_run)]]}
    (root / 'seed.json').write_text(json.dumps(seed), encoding='utf-8')

class Adapter:
    def send(self, frozen, cancel):
        trace('adapter_send', message_id=frozen['message']['id'], input_sha256=hashlib.sha256(_encode(frozen)).hexdigest())
        if mode() in ('hold_model', 'uncertain_model'):
            control.with_suffix('.model_started').write_text('ready', encoding='ascii')
            deadline = time.monotonic() + 45
            while not control.with_suffix('.model_release').exists():
                if cancel.wait(.01):
                    raise ConfirmedCancellation()
                if time.monotonic() >= deadline:
                    raise RuntimeError('Controlled model was not released')
            if mode() == 'uncertain_model':
                raise OSError('Controlled response lost after send')
        if cancel.is_set():
            raise ConfirmedCancellation()
        return TextResponse('# Original draft\n\nThe frozen observation is 300 K; run status is not a result.\n',
                            {'model': 'fixture/report', 'remote_request_id': 'fixture-reply', 'output_tokens': 22})

init = ProjectSessions.__init__
def session_init(self, *args, **kwargs):
    init(self, *args, **kwargs)
    # Isolated test state only. No settings RPC, key, downloaded model, or real server.
    endpoint = self.models.endpoints.add('fixture-report-generation', 'Controlled local fixture',
        'http://127.0.0.1:9/v1', ['fixture/report'], location='local')
    self.models[endpoint['adapter']] = Adapter()
ProjectSessions.__init__ = session_init

start_request = RequestExecutor.start
def delayed_start(self, store, request_id):
    if mode() != 'lost_start_pending':
        return start_request(self, store, request_id)
    trace('deferred_start', request_id=request_id)
    # Stop before the real durable claim, then let cancellation race the same start.
    def claim_later():
        deadline = time.monotonic() + 45
        while not control.with_suffix('.start_release').exists():
            if time.monotonic() >= deadline:
                trace('late_start_timeout')
                return
            time.sleep(.01)
        result = start_request(self, store, request_id)
        trace('late_start_observed', status=result['status'], request_id=request_id)
    threading.Thread(target=claim_later, daemon=True).start()
    return store.requests.get(request_id)
RequestExecutor.start = delayed_start

run = Bridge._run
def observed_run(self, identity, method, params):
    trace(method, request_id=params.get('request_id'), report_id=params.get('report_id'), message_id=params.get('message_id'))
    return run(self, identity, method, params)
Bridge._run = observed_run
send = Bridge.send
def observed_send(self, message, method=None):
    current = mode()
    if 'result' in message:
        result = message['result']
        if method == 'project.reports.generation_request':
            if current == 'wrong_response_text' and result['response']:
                result['response']['text'] += 'Wire-valid wrong text'
            if current == 'wrong_input_question':
                result['input']['message']['text'] += 'Wire-valid wrong question'
        if method == 'project.reports.get' and current == 'wrong_saved_body':
            item = result['report']; manifest = item['manifest']
            body = manifest['generation']['body'] + '\nReplaced body'
            manifest['generation']['body'] = body
            manifest['generation']['edited'] = True
            manifest['assets'][0].update(sha256=hashlib.sha256(body.encode()).hexdigest(), size=len(body.encode()))
            item['source_sha256'] = hashlib.sha256(_encode(manifest)).hexdigest()
        if method == 'project.reports.export_file':
            # Independently inspect the bytes actually written by the real exporter.
            with zipfile.ZipFile(result['path']) as package:
                manifest = json.loads(package.read('stk-report.json'))
                report_manifest = manifest['manifest']
                entry = report_manifest['entry_path']
                evidence = {'body': package.read(entry).decode('utf-8'),
                    'input_sha256': hashlib.sha256(package.read('stk-generation-input.json')).hexdigest(),
                    'response': package.read('stk-generation-response.txt').decode('utf-8'),
                    'png_sha256': hashlib.sha256(package.read('images/plot.png')).hexdigest(),
                    'names': sorted(package.namelist())}
            control.with_suffix('.zip').write_text(json.dumps(evidence), encoding='utf-8')
        if ((current in ('lost_start', 'lost_start_pending') and method == 'project.requests.start') or
            (current == 'lost_save' and method == 'project.reports.create_generated') or
            (current == 'lost_prepare' and method == 'project.requests.create')):
            return send(self, {'id': message['id'], 'error': error_object('unavailable',
                'Controlled transport uncertainty after the real operation committed', retryable=False)}, method)
        if ((current == 'hold_bundle' and method == 'project.reports.generation_request') or
            (current == 'hold_catalog' and method == 'project.catalog')):
            control.with_suffix('.held').write_text('ready', encoding='ascii')
            def deliver():
                deadline = time.monotonic() + 45
                while not control.with_suffix('.release').exists() and time.monotonic() < deadline:
                    if control.with_suffix('.crash').exists():
                        os._exit(73)
                    time.sleep(.01)
                send(self, message, method)
                control.with_suffix('.sent').write_text('sent', encoding='ascii')
            threading.Thread(target=deliver, daemon=True).start()
            return
    return send(self, message, method)
Bridge.send = observed_send
main()
)PY";

Json read_json(const fs::path &path)
{
  std::ifstream input(path, std::ios::binary);
  return Json::parse(input);
}
std::string digest(const Json &value) { return core::Sha256::hex(io::python_json_dumps(value, true, true)); }

class ReportGenerationPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"report-generation"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1000};
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectReportGeneration> composer;
  std::string python;
  Json seed, primary, viewer_baseline;
  std::shared_ptr<const io::Payload> shown;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  std::string handle() { return project().project()->handle; }
  int64_t revision() { return project().project()->revision; }
  double now() const
  {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
  }
  void write(const std::string &name, const std::string &value)
  {
    std::ofstream output(dir.path() / name, std::ios::binary); output << value;
    ASSERT_TRUE(output.good());
  }
  void mode(const std::string &value) { write("mode", value); }
  std::vector<Json> calls(const std::string &method = {})
  {
    std::ifstream input(dir.path() / "mode.calls"); std::string line; std::vector<Json> result;
    while (std::getline(input, line)) {
      if (line.empty()) { continue; }
      const auto item = Json::parse(line);
      if (method.empty() || io::get_string(item, "method") == method) { result.push_back(item); }
    }
    return result;
  }
  size_t count(const std::string &method) { return calls(method).size(); }
  Json call_on(bridge::Client &sender, const std::string &method, Json params)
  {
    auto result = std::make_shared<std::optional<bridge::Result<Json>>>();
    auto future = sender.call(method, std::move(params));
    future.then([result](auto value) { *result = std::move(value); });
    if (!loop.pump_until([&] { return result->has_value(); }, 30)) {
      future.cancel(); ADD_FAILURE() << method << " timed out"; return nullptr;
    }
    if (!result->value()) { ADD_FAILURE() << result->value().error().describe(); return nullptr; }
    return result->value().value();
  }
  Json call(const std::string &method, Json params) { return call_on(*client, method, std::move(params)); }
  bool start_client(const std::string &suffix)
  {
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge-" + suffix; options.cache_dir = dir.str() + "/cache-" + suffix;
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime-" + suffix;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/mode", "--stdio",
        "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options);
    if (!client->start() || !client->wait_ready(60)) { return false; }
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    return loop.pump_until([&] { return project().ready(); }, 30);
  }
  void settle_project()
  {
    ASSERT_TRUE(loop.pump_until([&] { project().sync(); return project().loaded() && !project().busy() && !project().recent_loading(); }, 30))
        << project().error();
  }
  void idle(ProjectReportGeneration &c)
  {
    ASSERT_TRUE(loop.pump_until([&] { c.sync(); return !c.busy(); }, 30)) << c.error();
  }
  void phase(ProjectReportGeneration &c, const std::string &expected)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      c.pump(now()); return !c.busy() && io::get_string(c.draft(), "phase") == expected;
    }, 30)) << c.error() << " phase=" << c.draft().at("phase");
  }
  void input(ProjectReportGeneration &c, bool all_sources = false)
  {
    const auto context = call("project.contexts.get", {{"handle", handle()}, {"context_id", seed.at("context")}});
    ASSERT_TRUE(context.is_object()); primary = context.at("context");
    Json sources = Json::array();
    if (all_sources) {
      sources.push_back({{"kind", "context"}, {"id", seed.at("context")}});
      for (const auto &item : seed.at("runs")) { sources.push_back(item); }
    }
    const auto review = call("project.reports.review_sources", {{"handle", handle()}, {"expected_revision", revision()}, {"sources", sources}});
    ASSERT_TRUE(review.is_object());
    Json assets = Json::array(), descriptors = Json::array(), snapshot_id = nullptr, snapshot_sha = nullptr;
    if (all_sources) {
      const auto snapshot = call("project.snapshots.get", {{"handle", handle()}, {"snapshot_id", seed.at("snapshot")}});
      ASSERT_TRUE(snapshot.is_object()); const auto &s = snapshot.at("snapshot");
      snapshot_id = s.at("id"); snapshot_sha = s.at("sha256");
      const auto &file = s.at("manifest").at("files").front();
      assets.push_back({{"record_id", seed.at("asset")}, {"path", "images/plot.png"}});
      descriptors.push_back({{"record_id", seed.at("asset")}, {"path", "images/plot.png"}, {"mime", "image/png"},
          {"sha256", file.at("sha256")}, {"size", file.at("size")}});
    }
    const Json selection = {{"expected_revision", revision()}, {"sources", sources}, {"expected_sources_sha256", review.at("sources_sha256")},
        {"snapshot_id", snapshot_id}, {"assets", assets}};
    ASSERT_TRUE(c.set_input(c.token(), primary, "Report only the explicitly selected frozen evidence.",
        {{"adapter", "openai-compatible/1:fixture-report-generation"}, {"model", "fixture/report"}},
        selection, review.at("sources"), descriptors, snapshot_sha)) << c.error();
    ASSERT_TRUE(c.edit(c.token(), "name", "Reviewed report"));
  }
  void prepare(ProjectReportGeneration &c, bool all_sources = false)
  {
    ASSERT_NO_FATAL_FAILURE(input(c, all_sources));
    ASSERT_TRUE(c.prepare(c.token())) << c.error();
    ASSERT_NO_FATAL_FAILURE(phase(c, "prepared"));
    ASSERT_TRUE(c.request().is_object()); ASSERT_EQ(c.request().at("status"), "pending");
  }
  void complete(ProjectReportGeneration &c)
  {
    ASSERT_TRUE(loop.pump_until([&] { store().models().sync(); return store().models().loaded() && !store().models().busy(); }, 30));
    ASSERT_TRUE(c.send_blocked().empty()) << c.send_blocked();
    ASSERT_TRUE(c.start(c.token())) << c.error();
    ASSERT_NO_FATAL_FAILURE(phase(c, "completed"));
    ASSERT_EQ(c.response().at("text"), reply_text);
  }
  void hold_bundle()
  {
    for (const auto *suffix : {".held", ".release", ".sent", ".crash"}) { fs::remove(dir.path() / ("mode" + std::string(suffix))); }
    ASSERT_NO_FATAL_FAILURE(mode("hold_bundle"));
    ASSERT_TRUE(composer->refresh(composer->token()));
    ASSERT_TRUE(loop.pump_until([&] { composer->sync(); return fs::exists(dir.path() / "mode.held"); }, 30));
    ASSERT_TRUE(composer->busy());
  }
  void drain(bridge::Client &sender)
  {
    ASSERT_NO_FATAL_FAILURE(write("mode.release", "release"));
    ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.sent"); }, 15));
    ASSERT_TRUE(call_on(sender, "project.list", Json::object()).is_object());
    loop.run_ready(); composer->sync();
  }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    ASSERT_NO_FATAL_FAILURE(write("bridge.py", kBridge));
    ASSERT_TRUE(start_client("first")); seed = read_json(dir.path() / "seed.json");
    ASSERT_TRUE(project().open(dir.str() + "/project"));
    ASSERT_NO_FATAL_FAILURE(settle_project());
    composer = std::make_unique<ProjectReportGeneration>(store()); ASSERT_TRUE(composer->supported());
    store().models().sync();
    ASSERT_TRUE(loop.pump_until([&] { store().models().sync(); return store().models().loaded() && !store().models().busy(); }, 30));
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store().viewer().open_payload(shown, "Keep existing result"); store().viewer().refresh_metadata();
    ASSERT_TRUE(loop.pump_until([&] { return store().viewer().presets_loaded() && !store().viewer().catalog().is_null() && store().viewer().colormaps(); }, 30));
    viewer_baseline = store().viewer().save_workspace_state();
  }
  void TearDown() override
  {
    write("mode.release", "release"); write("mode.model_release", "release");
    write("mode.start_release", "release");
    if (count("deferred_start")) {
      EXPECT_TRUE(bridge::test::wait_until([&] { return count("late_start_observed") == count("deferred_start"); }, 10));
      EXPECT_EQ(count("late_start_timeout"), 0u);
    }
    if (shown) {
      EXPECT_EQ(store().viewer().base_payload(), shown);
      EXPECT_TRUE(store().viewer().save_workspace_state() == viewer_baseline);
      EXPECT_EQ(store().viewer().evaluations_started(), 0u);
      EXPECT_TRUE(store().scripts().history().empty());
    }
    EXPECT_EQ(count("forbidden_network"), 0u);
    composer.reset(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(ReportGenerationPython, ExplicitSendEditedReportFrozenSourcesPreviewZipAndReopen)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer, true));
  EXPECT_EQ(count("adapter_send"), 0u); EXPECT_EQ(count("project.requests.start"), 0u);
  EXPECT_EQ(count("project.requests.create"), 1u);
  const auto input_sha = composer->request().at("input_sha256");
  const auto selected_sources = composer->frozen_input().at("report_input").at("sources");
  ASSERT_EQ(selected_sources.size(), 4u);
  ASSERT_TRUE(fs::remove(dir.path() / "project/plot.png"));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  EXPECT_FALSE(composer->start(composer->token()));
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("adapter_send"), 1u);
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  ASSERT_TRUE(composer->refresh(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  EXPECT_EQ(composer->draft().at("body"), edited_text); EXPECT_EQ(composer->response().at("text"), reply_text);
  const auto before = revision();
  ASSERT_TRUE(composer->create_report(composer->token())) << composer->error();
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "saved"));
  const auto created = composer->take_created(); ASSERT_TRUE(created);
  EXPECT_EQ(revision(), before + 1); EXPECT_EQ(count("project.reports.create_generated"), 1u);
  const auto result = call("project.reports.get", {{"handle", handle()}, {"report_id", created->report_id}});
  ASSERT_TRUE(result.is_object()); const auto &report = result.at("report"); const auto &manifest = report.at("manifest");
  EXPECT_EQ(report.at("format"), "stk.report/2"); EXPECT_EQ(manifest.at("generation").at("body"), edited_text);
  EXPECT_EQ(manifest.at("generation").at("edited"), true);
  EXPECT_EQ(digest(manifest.at("sources")), digest(selected_sources));
  ProjectReports reader(store()); ASSERT_TRUE(reader.load(created->report_id, created->source_sha256));
  ASSERT_TRUE(loop.pump_until([&] { reader.sync(); return !reader.busy(); }, 30));
  ASSERT_TRUE(reader.prepare_preview());
  ASSERT_TRUE(loop.pump_until([&] { reader.sync(); return !reader.preview_busy(); }, 30));
  ASSERT_TRUE(reader.prepared_preview()) << reader.preview_error();
  const auto &prepared = *reader.prepared_preview(); ASSERT_EQ(prepared.assets.size(), 2u);
  EXPECT_EQ(prepared.assets[1].path, "images/plot.png");
  EXPECT_EQ(core::Sha256::hex(prepared.assets[1].bytes), seed.at("png_sha256").get<std::string>());
  const auto exported = call("project.reports.export_file", {{"handle", handle()}, {"report_id", created->report_id},
      {"expected_revision", revision()}, {"expected_source_sha256", created->source_sha256}, {"destination", dir.str() + "/report.zip"}});
  ASSERT_TRUE(exported.is_object()); ASSERT_TRUE(fs::exists(dir.path() / "report.zip"));
  const auto zip = read_json(dir.path() / "mode.zip");
  EXPECT_EQ(zip.at("body"), edited_text); EXPECT_EQ(zip.at("response"), reply_text);
  EXPECT_EQ(zip.at("input_sha256"), input_sha); EXPECT_EQ(zip.at("png_sha256"), seed.at("png_sha256"));
  reader.clear(); ASSERT_TRUE(project().close());
  ASSERT_TRUE(loop.pump_until([&] { project().sync(); return !project().project() && !project().busy(); }, 30));
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(settle_project());
  const auto reopened = call("project.reports.get", {{"handle", handle()}, {"report_id", created->report_id}});
  EXPECT_EQ(digest(reopened.at("report")), digest(report));
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, WorkspaceRestorationDoesNotReadPrepareSendOrReplaceEditedBody)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto workspace = composer->save_workspace_state();
  ASSERT_TRUE(ProjectReportGeneration::valid_workspace_state(workspace));
  EXPECT_FALSE(workspace.contains("handle")); EXPECT_FALSE(workspace.contains("response")); EXPECT_FALSE(workspace.contains("input"));
  const auto before = calls().size();
  ProjectReportGeneration restored(store()); ASSERT_TRUE(restored.load_workspace_state(workspace));
  restored.sync(); restored.pump(now()); restored.pump(now() + 120);
  EXPECT_TRUE(restored.request().is_null()); EXPECT_TRUE(restored.frozen_input().is_null());
  EXPECT_EQ(restored.draft().at("body"), edited_text);
  EXPECT_FALSE(restored.start(restored.token()));
  ASSERT_TRUE(call("project.list", Json::object()).is_object());
  const auto observed = calls();
  for (size_t i = before; i < observed.size(); ++i) { EXPECT_EQ(observed[i].at("method"), "project.list"); }
  ASSERT_TRUE(restored.refresh(restored.token()));
  ASSERT_NO_FATAL_FAILURE(idle(restored));
  EXPECT_EQ(restored.draft().at("body"), edited_text); EXPECT_EQ(restored.response().at("text"), reply_text);
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, LostPreparationReplyOnlyQueriesOriginalRequestThenRequiresExplicitStart)
{
  ASSERT_NO_FATAL_FAILURE(input(*composer));
  ASSERT_NO_FATAL_FAILURE(mode("lost_prepare"));
  ASSERT_TRUE(composer->prepare(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  ASSERT_TRUE(composer->pending()); const auto id = composer->draft().at("request_id");
  EXPECT_EQ(count("project.requests.create"), 1u); EXPECT_EQ(count("adapter_send"), 0u);
  EXPECT_FALSE(composer->prepare(composer->token()));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(composer->check_pending(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "prepared"));
  EXPECT_EQ(composer->request().at("id"), id);
  EXPECT_EQ(count("project.requests.create"), 1u); EXPECT_EQ(count("project.requests.start"), 0u);
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, LostStartReplyNeverResendsAndRestoredPendingOnlyQueriesOriginalIdentity)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(mode("lost_start"));
  ASSERT_TRUE(composer->start(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  ASSERT_TRUE(composer->pending()); const auto id = composer->draft().at("request_id");
  const auto workspace = composer->save_workspace_state();
  ProjectReportGeneration restored(store()); ASSERT_TRUE(restored.load_workspace_state(workspace));
  EXPECT_FALSE(restored.start(restored.token()));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(restored.check_pending(restored.token()));
  ASSERT_NO_FATAL_FAILURE(idle(restored));
  // A query may first observe running; following is deliberately explicit here.
  ASSERT_TRUE(loop.pump_until([&] {
    if (!restored.busy() && io::get_string(restored.request(), "status") != "completed") { restored.refresh(restored.token()); }
    return !restored.busy() && io::get_string(restored.request(), "status") == "completed";
  }, 30)) << restored.error();
  EXPECT_EQ(restored.request().at("id"), id); EXPECT_FALSE(restored.start(restored.token()));
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("adapter_send"), 1u);
  for (const auto &query : calls("project.reports.generation_request")) { EXPECT_EQ(query.at("request_id"), id); }
}

TEST_F(ReportGenerationPython, LostSaveReplyKeepsOriginalUuidAndRejectsSelfConsistentWrongBody)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  ASSERT_NO_FATAL_FAILURE(mode("lost_save"));
  ASSERT_TRUE(composer->create_report(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(settle_project());
  ASSERT_TRUE(composer->pending()); const auto saved = composer->draft().at("pending_save");
  const auto id = saved.at("report_id"); EXPECT_FALSE(composer->create_report(composer->token()));
  ASSERT_NO_FATAL_FAILURE(mode("wrong_saved_body"));
  ASSERT_TRUE(composer->check_pending(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  EXPECT_TRUE(composer->pending()); EXPECT_FALSE(composer->take_created()); EXPECT_FALSE(composer->error().empty());
  EXPECT_EQ(composer->draft().at("pending_save"), saved); EXPECT_EQ(composer->draft().at("body"), edited_text);
  EXPECT_EQ(client->stats().schema_violations, 0u); // Fault is a valid, independently rehashed wire result.
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(composer->check_pending(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "saved"));
  const auto created = composer->take_created(); ASSERT_TRUE(created); EXPECT_EQ(created->report_id, id.get<std::string>());
  EXPECT_EQ(count("project.reports.create_generated"), 1u);
  for (const auto &query : calls("project.reports.get")) { EXPECT_EQ(query.at("report_id"), id); }
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, SaveRefreshWaitStopsAfterNinetySecondsAndKeepsOriginalIdentityForExplicitCheck)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  ASSERT_NO_FATAL_FAILURE(mode("hold_catalog"));
  const auto expected = revision();
  const auto reads = count("project.reports.generation_request");
  ASSERT_TRUE(composer->create_report(composer->token()));
  ASSERT_TRUE(loop.pump_until([&] {
    composer->sync();
    return !composer->busy() && composer->pending() && fs::exists(dir.path() / "mode.held");
  }, 30));
  const auto pending = composer->draft().at("pending_save");
  ASSERT_TRUE(pending.is_object());
  const auto started = now();
  EXPECT_GT(composer->pump(started), started);
  EXPECT_LT(composer->pump(started + 91), 0);
  EXPECT_LT(composer->pump(started + 92), 0);
  EXPECT_EQ(composer->draft().at("pending_save"), pending);
  EXPECT_EQ(composer->draft().at("body"), edited_text);
  EXPECT_FALSE(composer->take_created());
  EXPECT_FALSE(composer->create_report(composer->token()));
  EXPECT_EQ(count("project.reports.generation_request"), reads);
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  ASSERT_TRUE(loop.pump_until([&] {
    project().sync();
    return project().loaded() && !project().refreshing() && revision() > expected;
  }, 30));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  EXPECT_LT(composer->pump(started + 93), 0);
  EXPECT_EQ(count("project.reports.generation_request"), reads);
  ASSERT_TRUE(composer->check_pending(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "saved"));
  const auto created = composer->take_created(); ASSERT_TRUE(created);
  EXPECT_EQ(created->report_id, pending.at("report_id").get<std::string>());
  EXPECT_EQ(count("project.reports.create_generated"), 1u);
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, ValidWireWrongResponseAndInputCannotReplaceVerifiedBundle)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto input_before = digest(composer->frozen_input()), reply_before = digest(composer->response());
  for (const auto *fault : {"wrong_response_text", "wrong_input_question"}) {
    SCOPED_TRACE(fault);
    ASSERT_NO_FATAL_FAILURE(mode(fault));
    ASSERT_TRUE(composer->refresh(composer->token()));
    ASSERT_NO_FATAL_FAILURE(idle(*composer));
    EXPECT_FALSE(composer->error().empty()); EXPECT_EQ(digest(composer->frozen_input()), input_before);
    EXPECT_EQ(digest(composer->response()), reply_before); EXPECT_EQ(composer->draft().at("body"), edited_text);
    EXPECT_EQ(client->stats().schema_violations, 0u);
  }
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, CancelledAndUncertainRepliesCannotBeSavedOrAutomaticallySentAgain)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(mode("hold_model"));
  ASSERT_TRUE(composer->start(composer->token()));
  ASSERT_TRUE(loop.pump_until([&] { composer->pump(now()); return !composer->busy() && io::get_string(composer->request(), "status") == "running" && fs::exists(dir.path() / "mode.model_started"); }, 30));
  ASSERT_TRUE(composer->cancel(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "terminal"));
  EXPECT_EQ(composer->request().at("status"), "cancelled"); EXPECT_FALSE(composer->create_report(composer->token()));
  EXPECT_FALSE(composer->start(composer->token()));
  ASSERT_TRUE(composer->discard(composer->token(), true));
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(mode("uncertain_model"));
  ASSERT_TRUE(composer->start(composer->token()));
  ASSERT_TRUE(loop.pump_until([&] { composer->pump(now()); return !composer->busy() && io::get_string(composer->request(), "status") == "running"; }, 30));
  ASSERT_NO_FATAL_FAILURE(write("mode.model_release", "release"));
  ASSERT_TRUE(loop.pump_until([&] { composer->pump(now()); return !composer->busy() && io::get_string(composer->request(), "status") == "uncertain"; }, 30)) << composer->error();
  EXPECT_FALSE(composer->create_report(composer->token())); EXPECT_FALSE(composer->start(composer->token()));
  EXPECT_EQ(count("project.requests.start"), 2u); EXPECT_EQ(count("adapter_send"), 2u);
  EXPECT_EQ(count("project.reports.create_generated"), 0u);
}

TEST_F(ReportGenerationPython, RevisionChangeRejectsLateReadAndRetainedControlToken)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto stale = composer->token(); const auto frozen = digest(composer->frozen_input());
  ASSERT_NO_FATAL_FAILURE(hold_bundle());
  ASSERT_TRUE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision()},
      {"commands", Json::array({{{"op", "rename_table"}, {"id", seed.at("table")}, {"name", "Changed after read"}}})}}).is_object());
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(settle_project()); composer->sync();
  EXPECT_FALSE(composer->edit(stale, "body", "Late control must not overwrite"));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_FALSE(composer->error().empty()); EXPECT_EQ(digest(composer->frozen_input()), frozen);
  EXPECT_EQ(composer->draft().at("body"), edited_text); EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, ProjectSwitchRejectsLateReadWithoutMigratingRequestOrBody)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto original = composer->draft().at("project_id"); const auto stale = composer->token();
  ASSERT_NO_FATAL_FAILURE(hold_bundle());
  ASSERT_TRUE(project().create(dir.str() + "/other", "Other project"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); composer->sync();
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_TRUE(composer->request().is_null()); EXPECT_TRUE(composer->frozen_input().is_null());
  EXPECT_EQ(composer->draft().at("project_id"), original); EXPECT_EQ(composer->draft().at("body"), edited_text);
  EXPECT_FALSE(composer->edit(stale, "body", "Wrong project")); EXPECT_FALSE(composer->refresh(composer->token()));
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, ReplacementBridgeRejectsOldCompletionUntilExplicitReadOnNewHandle)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto id = composer->draft().at("request_id"); const auto stale = composer->token();
  ASSERT_NO_FATAL_FAILURE(hold_bundle());
  const auto old_handle = handle();
  auto old = std::move(client); ASSERT_TRUE(start_client("replacement"));
  // Attaching the replacement Ready client already reopens the saved project.
  // Wait for that metadata read rather than attempting a second open while busy.
  ASSERT_NO_FATAL_FAILURE(settle_project()); composer->sync();
  EXPECT_NE(handle(), old_handle);
  ASSERT_NO_FATAL_FAILURE(drain(*old));
  EXPECT_TRUE(composer->request().is_null()); EXPECT_FALSE(composer->edit(stale, "body", "Old bridge control"));
  EXPECT_EQ(composer->draft().at("body"), edited_text);
  old->close(); EXPECT_EQ(old->stats().schema_violations, 0u);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_TRUE(composer->refresh(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  EXPECT_EQ(composer->request().at("id"), id); EXPECT_EQ(composer->draft().at("body"), edited_text);
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, SavedAImportsCompletedBReadOnlyAndTwoComposersLeaveDiscussionSelectionAlone)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  auto &discussion = project().discussion();
  ASSERT_TRUE(discussion.load_context(seed.at("context").get<std::string>()));
  ASSERT_TRUE(loop.pump_until([&] { return !discussion.busy(); }, 30));
  const auto discussion_context = digest(discussion.context()), discussion_message = digest(discussion.message());
  const auto exchange_id = discussion.exchange_id();
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->create_report(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "saved")); ASSERT_TRUE(composer->take_created());
  const auto saved_a = composer->draft().at("request_id");
  ProjectReportGeneration second(store());
  ASSERT_NO_FATAL_FAILURE(prepare(second));
  ASSERT_NO_FATAL_FAILURE(complete(second));
  ASSERT_TRUE(second.edit(second.token(), "body", "# Independent B edit\n"));
  const auto id_b = second.draft().at("request_id").get<std::string>();
  EXPECT_NE(saved_a.get<std::string>(), id_b);
  const auto sends = count("project.requests.start"), creates = count("project.requests.create");
  ASSERT_TRUE(composer->open_saved_request(composer->token(), id_b)) << composer->error();
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  ASSERT_TRUE(composer->request().is_object()) << composer->error();
  EXPECT_EQ(composer->request().at("id"), id_b); EXPECT_EQ(composer->response().at("text"), reply_text);
  EXPECT_EQ(composer->draft().at("body"), reply_text); EXPECT_EQ(second.draft().at("body"), "# Independent B edit\n");
  EXPECT_FALSE(composer->start(composer->token())); EXPECT_EQ(count("project.requests.start"), sends);
  EXPECT_EQ(count("project.requests.create"), creates); EXPECT_EQ(count("adapter_send"), 2u);
  EXPECT_EQ(digest(discussion.context()), discussion_context); EXPECT_EQ(digest(discussion.message()), discussion_message);
  EXPECT_EQ(discussion.exchange_id(), exchange_id);
}

TEST_F(ReportGenerationPython, LostStartStillPendingCanBeExplicitlyCancelledBeforeItsLateClaim)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(mode("lost_start_pending"));
  const auto request_id = composer->draft().at("request_id");
  ASSERT_TRUE(composer->start(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  ASSERT_TRUE(composer->pending());
  EXPECT_EQ(composer->draft().at("phase"), "start_pending");
  EXPECT_EQ(composer->draft().at("send_attempted"), true);
  EXPECT_EQ(count("adapter_send"), 0u);
  ASSERT_TRUE(composer->check_pending(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  EXPECT_EQ(composer->request().at("status"), "pending");
  EXPECT_EQ(composer->draft().at("phase"), "start_pending");
  EXPECT_FALSE(composer->start(composer->token()));
  ASSERT_TRUE(composer->cancel(composer->token())) << composer->error();
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "terminal"));
  EXPECT_EQ(composer->request().at("status"), "cancelled");
  EXPECT_EQ(composer->request().at("error_code"), "cancelled_before_start");
  ASSERT_NO_FATAL_FAILURE(write("mode.start_release", "release"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return count("late_start_observed") == 1; }, 10));
  const auto late = calls("late_start_observed"); ASSERT_EQ(late.size(), 1u);
  EXPECT_EQ(late.front().at("status"), "cancelled"); EXPECT_EQ(late.front().at("request_id"), request_id);
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("project.requests.cancel"), 1u);
  EXPECT_EQ(count("adapter_send"), 0u); EXPECT_FALSE(composer->create_report(composer->token()));
  for (const auto &item : calls("project.requests.cancel")) { EXPECT_EQ(item.at("request_id"), request_id); }
}

TEST_F(ReportGenerationPython, SavedDraftFromPreviousProjectNeedsCurrentExplicitDiscardBeforeNewInputs)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  ASSERT_TRUE(composer->create_report(composer->token()));
  ASSERT_NO_FATAL_FAILURE(phase(*composer, "saved"));
  ASSERT_TRUE(composer->take_created()); EXPECT_FALSE(composer->dirty());
  const auto stale = composer->token(); const auto original_project = composer->draft().at("project_id");
  ASSERT_TRUE(project().create(dir.str() + "/other", "Other project"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); composer->sync();
  EXPECT_EQ(composer->draft().at("body"), edited_text); EXPECT_EQ(composer->draft().at("project_id"), original_project);
  EXPECT_FALSE(composer->discard(stale, true));
  EXPECT_FALSE(composer->refresh(composer->token()));
  EXPECT_FALSE(composer->create_report(composer->token()));
  ASSERT_TRUE(composer->discard(composer->token(), true));
  EXPECT_FALSE(composer->dirty()); EXPECT_TRUE(composer->request().is_null());
  ASSERT_TRUE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision()},
      {"commands", Json::array({
          {{"op", "create_table"}, {"id", seed.at("table")}, {"name", "Project B cases"}},
          {{"op", "add_field"}, {"id", seed.at("field")}, {"table_id", seed.at("table")},
              {"name", "temperature"}, {"type", "number"}, {"unit", "K"}},
          {{"op", "add_record"}, {"id", seed.at("row")}, {"table_id", seed.at("table")}},
          {{"op", "set_cell"}, {"table_id", seed.at("table")}, {"record_id", seed.at("row")},
              {"field_id", seed.at("field")}, {"value", 301}}})}}).is_object());
  project().refresh(); ASSERT_NO_FATAL_FAILURE(settle_project());
  const auto context = call("project.contexts.capture", {{"handle", handle()},
      {"context_id", "a1111111-1111-4111-8111-111111111111"}, {"table_id", seed.at("table")},
      {"record_ids", Json::array({seed.at("row")})}, {"field_ids", Json::array({seed.at("field")})},
      {"expected_revision", revision()}, {"title", "Frozen project B context"}});
  ASSERT_TRUE(context.is_object());
  const auto review = call("project.reports.review_sources", {{"handle", handle()}, {"expected_revision", revision()}, {"sources", Json::array()}});
  ASSERT_TRUE(review.is_object());
  const Json selection = {{"expected_revision", revision()}, {"sources", Json::array()},
      {"expected_sources_sha256", review.at("sources_sha256")}, {"snapshot_id", nullptr}, {"assets", Json::array()}};
  ASSERT_TRUE(composer->set_input(composer->token(), context.at("context"), "New unsent draft for B.",
      {{"adapter", "openai-compatible/1:fixture-report-generation"}, {"model", "fixture/report"}},
      selection, review.at("sources"), Json::array(), nullptr)) << composer->error();
  EXPECT_EQ(io::get_string(composer->draft(), "project_id"), project().project()->id);
  EXPECT_EQ(composer->draft().at("request_id"), ""); EXPECT_EQ(count("project.requests.start"), 1u);
  EXPECT_EQ(count("adapter_send"), 1u);
}

TEST_F(ReportGenerationPython, SameClientRealRestartChangesScopeAndDoesNotReplayReadOrSend)
{
  ASSERT_NO_FATAL_FAILURE(prepare(*composer));
  ASSERT_NO_FATAL_FAILURE(complete(*composer));
  ASSERT_TRUE(composer->edit(composer->token(), "body", edited_text));
  const auto stale = composer->token(); const auto id = composer->draft().at("request_id");
  ASSERT_NO_FATAL_FAILURE(hold_bundle());
  const auto spawned = client->stats().spawned;
  const auto reads = count("project.reports.generation_request");
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(write("mode.crash", "Crash only the fixture holding the completed read"));
  ASSERT_TRUE(loop.pump_until([&] {
    composer->sync(); return client->stats().spawned > spawned && client->state() == bridge::BridgeState::Ready;
  }, 60));
  ASSERT_NO_FATAL_FAILURE(settle_project()); composer->sync();
  EXPECT_TRUE(composer->request().is_null()); EXPECT_TRUE(composer->frozen_input().is_null());
  EXPECT_EQ(composer->draft().at("body"), edited_text);
  EXPECT_FALSE(composer->edit(stale, "body", "Old process callback"));
  EXPECT_EQ(count("project.reports.generation_request"), reads);
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("adapter_send"), 1u);
  ASSERT_TRUE(composer->refresh(composer->token()));
  ASSERT_NO_FATAL_FAILURE(idle(*composer));
  ASSERT_TRUE(composer->request().is_object()) << composer->error();
  EXPECT_EQ(composer->request().at("id"), id); EXPECT_EQ(composer->draft().at("body"), edited_text);
}
// The concrete form controls are exercised below after the production view lands.
// Fixture preparation is outside the recorded flow. Generation actions themselves
// may only enter through mouse/keyboard events, never this fixture's composer.
class ReportGenerationMouse : public ReportGenerationPython,
                              public ::testing::WithParamInterface<std::tuple<const char *, int>> {
 protected:
  int width = 1440, clicks = 0, wheels = 0, keys = 0, text_events = 0, moves = 0;
  std::vector<std::string> action_log;
  Editor *python_draft = nullptr, *ai_draft = nullptr, *viewer_editor = nullptr;
  nlohmann::json python_state, ai_state, camera_state;
  EditorArea &area() { return f.area("a3"); }
  void frame() { f.screen.run_deferred(); f.drv->wait_ms(16); f.drv->frame(); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *item = widget(key); return item && item->enabled; }, 30)) << key;
  }
  bool visible(const ui::Widget *item)
  {
    if (!item) { return false; }
    const auto rect = item->rect.intersect(item->clip).intersect(ui::Rect{0, 0, float(width), 1000});
    return !rect.empty() && rect.w >= item->rect.w - 1 && rect.h >= item->rect.h - 1;
  }
  void scroll_to(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget(key));
    const auto main = area().find_region(EditorArea::kMain)->ui_rect();
    for (int i = 0; i < 100 && !visible(widget(key)); ++i) {
      const auto *item = widget(key); ASSERT_NE(item, nullptr) << key;
      const float delta = item->rect.cy() > main.cy() ? -1.0f : 1.0f;
      const auto event = ui::Event::wheel({main.x1() - 2, main.cy()}, delta, double(f.drv->time_ms) / 1000.0);
      f.screen.ui()->handle_event(event); ++wheels;
      action_log.push_back(std::string("wheel:") + (delta < 0 ? "down:" : "up:") + key);
      frame();
    }
    ASSERT_TRUE(visible(widget(key))) << key << " is not wholly inside its clip and the viewport";
  }
  void click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(scroll_to(key));
    const auto [x, y] = f.widget_center(key);
    ASSERT_GE(x, 0); ASSERT_LT(x, width); ASSERT_GE(y, 0); ASSERT_LT(y, 1000);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    ++clicks; action_log.push_back("click:" + key); frame();
  }
  void row(const std::string &key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(scroll_to(key));
    const auto *item = widget(key); ASSERT_NE(item, nullptr); ASSERT_NE(item->list, nullptr);
    const auto &style = f.screen.ui()->style();
    const int x = int(item->rect.cx());
    const int y = f.screen.rect().ymax - 1 - int(item->rect.y + style.pixel + style.unit * (float(index) + .5f));
    ASSERT_GE(x, 0); ASSERT_LT(x, width); ASSERT_GE(y, 0); ASSERT_LT(y, 1000);
    ASSERT_TRUE(f.drv->click(x, y)); ++clicks;
    action_log.push_back("row:" + key + ":" + std::to_string(index)); frame();
  }
  void keyboard(wm::Key key, uint32_t modifiers, const std::string &description)
  {
    ASSERT_TRUE(f.drv->key(key, modifiers)); ++keys; action_log.push_back("key:" + description); frame();
  }
  void insert_text(const std::string &value)
  {
    // TextInput contains printable committed characters. Newlines are separate
    // Enter key events, as in the real window route, not control bytes in text.
    size_t start = 0;
    while (start < value.size()) {
      const auto end = value.find('\n', start);
      const auto line = value.substr(start, end == std::string::npos ? end : end - start);
      if (!line.empty()) {
        auto event = ui::Event::text_input(line); event.time = double(f.drv->time_ms) / 1000.0;
        ASSERT_TRUE(f.screen.ui()->handle_event(event).consumed); ++text_events;
        action_log.push_back("text:printable-characters");
      }
      if (end == std::string::npos) { break; }
      wm::Event event; event.type = wm::EventType::KeyDown; event.key = wm::Key::Enter;
      ASSERT_TRUE(f.drv->send(event)); event.type = wm::EventType::KeyUp; f.drv->send(event);
      ++keys; action_log.push_back("key:insert-newline"); start = end + 1;
    }
  }
  void replace_text(const std::string &key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
#ifdef __APPLE__
    ASSERT_NO_FATAL_FAILURE(keyboard(wm::Key::A, wm::ModOS, "select-all"));
#else
    ASSERT_NO_FATAL_FAILURE(keyboard(wm::Key::A, wm::ModCtrl, "select-all"));
#endif
    ASSERT_NO_FATAL_FAILURE(insert_text(value));
    action_log.push_back("text:" + key); frame();
  }
  void commit_text(const std::string &key, const std::string &value, bool multiline)
  {
    ASSERT_NO_FATAL_FAILURE(replace_text(key, value));
#ifdef __APPLE__
    constexpr uint32_t commit_modifier = wm::ModOS;
#else
    constexpr uint32_t commit_modifier = wm::ModCtrl;
#endif
    ASSERT_NO_FATAL_FAILURE(keyboard(wm::Key::Enter, multiline ? commit_modifier : wm::ModNone,
                                    multiline ? "commit-text-primary-Enter" : "commit-text-Enter"));
    ASSERT_FALSE(f.shell->text_input_active()) << key;
  }
  void dropdown_index(const std::string &key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    ASSERT_TRUE(f.screen.ui()->popup_open());
    ASSERT_NO_FATAL_FAILURE(click("popup/" + std::to_string(index)));
    ASSERT_FALSE(f.screen.ui()->popup_open());
  }
  void dropdown_label(const std::string &key, const std::string &label)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
    ASSERT_TRUE(f.screen.ui()->popup_open());
    std::string target;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.type == ui::WidgetType::MenuItem && item.text.find(label) != std::string::npos) {
          ASSERT_TRUE(target.empty()) << "Ambiguous popup choice " << label;
          target = item.key;
        }
      }
    }
    ASSERT_FALSE(target.empty()) << label;
    ASSERT_NO_FATAL_FAILURE(click(target));
    ASSERT_FALSE(f.screen.ui()->popup_open());
  }
  void choose_reviewed_inputs()
  {
    ASSERT_NO_FATAL_FAILURE(click("reports_generation_panel"));
    // Input and source panels are open by default only in generation mode.
    ASSERT_NO_FATAL_FAILURE(click("reports_create_sources_load"));
    ASSERT_NO_FATAL_FAILURE(row("reports_create_source_candidates", 0));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_source_add"));
    for (int kind = 1; kind <= 3; ++kind) {
      ASSERT_NO_FATAL_FAILURE(dropdown_index("reports_create_source_kind", kind));
      ASSERT_NO_FATAL_FAILURE(click("reports_create_sources_load"));
      ASSERT_NO_FATAL_FAILURE(row("reports_create_source_candidates", 0));
      ASSERT_NO_FATAL_FAILURE(click("reports_create_source_add"));
    }
    ASSERT_NO_FATAL_FAILURE(click("reports_generation_attachments_panel"));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_snapshots"));
    ASSERT_NO_FATAL_FAILURE(row("reports_create_snapshot_list", 0));
    ASSERT_NO_FATAL_FAILURE(row("reports_create_files", 0));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_include"));
    ASSERT_NO_FATAL_FAILURE(commit_text("reports_create_path", "images/plot.png", false));
    ASSERT_NO_FATAL_FAILURE(click("reports_create_sources_review"));
    ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_context"));
    ASSERT_NO_FATAL_FAILURE(click("reports_generation_input_panel"));
    ASSERT_NO_FATAL_FAILURE(dropdown_index("reports_generation_context", 0));
    ASSERT_NO_FATAL_FAILURE(dropdown_label("reports_generation_endpoint", "Controlled local fixture"));
    ASSERT_NO_FATAL_FAILURE(dropdown_label("reports_generation_model", "fixture/report"));
    EXPECT_EQ(count("project.requests.create"), 0u); EXPECT_EQ(count("project.requests.start"), 0u);
    EXPECT_EQ(count("adapter_send"), 0u); EXPECT_EQ(count("project.reports.asset"), 0u);
  }
  void maximize_by_keyboard()
  {
    ASSERT_EQ(f.screen.maximized(), nullptr);
    const auto [x, y] = wmtest::AppFixture::center(area().rect());
    f.drv->move(x, y); ++moves; action_log.push_back("move:a3");
    ASSERT_NO_FATAL_FAILURE(keyboard(wm::Key::Space, wm::ModCtrl, "maximize-a3"));
    ASSERT_EQ(f.screen.maximized(), &area());
  }
  void protected_state()
  {
    ASSERT_NE(python_draft, nullptr); ASSERT_NE(ai_draft, nullptr); ASSERT_NE(viewer_editor, nullptr);
    EXPECT_EQ(python_draft->save_workspace_state(), python_state);
    EXPECT_TRUE(python_draft->has_unsaved_changes());
    // The existing AI editor does not advertise has_unsaved_changes. Assert preserved
    // draft content, without claiming that its independent dirty-fence gap is fixed.
    EXPECT_EQ(ai_draft->save_workspace_state(), ai_state);
    EXPECT_EQ(viewer_editor->save_workspace_state(), camera_state);
    EXPECT_TRUE(store().viewer().save_workspace_state() == viewer_baseline);
    EXPECT_EQ(store().viewer().base_payload(), shown);
    EXPECT_EQ(store().viewer().evaluations_started(), 0u);
    EXPECT_TRUE(store().scripts().history().empty());
  }
  void record_actions()
  {
    const auto [language, selected_width] = GetParam();
    RecordProperty("starting_layout", "default Report work mode, not maximized, a3 report active; hidden Python and AI drafts; existing Viewer payload/camera");
    RecordProperty("language", language); RecordProperty("viewport_width", selected_width); RecordProperty("viewport_height", 1000);
    RecordProperty("mouse_clicks_from_default_report", clicks);
    RecordProperty("mouse_clicks_after_maximize", clicks);
    RecordProperty("keyboard_actions_from_default_report", keys);
    RecordProperty("keyboard_actions_after_maximize", keys - 1);
    RecordProperty("text_input_events", text_events); RecordProperty("wheel_events", wheels); RecordProperty("pointer_moves", moves);
    RecordProperty("actual_action_sequence", Json(action_log).dump());
  }
  void SetUp() override
  {
    ReportGenerationPython::SetUp();
    if (HasFatalFailure() || IsSkipped()) { return; }
    const auto [language, selected_width] = GetParam(); width = selected_width;
    store().set_language(language); f.drv->ctx.rect = {0, 0, width, 1000}; frame();
    ASSERT_TRUE(f.shell->switch_work_mode(&f.screen, AppShell::WorkMode::Report).ok()); frame();
    ASSERT_EQ(f.screen.maximized(), nullptr); ASSERT_EQ(area().editor().type().id, kEditorReports);
    ASSERT_TRUE(area().add_tab(kEditorPython, false)); python_draft = &area().tab(area().tab_count() - 1);
    ASSERT_TRUE(python_draft->load_state({{"source", "print('hidden Python draft must survive')"}}));
    ASSERT_TRUE(python_draft->has_unsaved_changes()); python_state = python_draft->save_workspace_state();
    ASSERT_TRUE(area().add_tab(kEditorAI, false)); ai_draft = &area().tab(area().tab_count() - 1);
    ASSERT_TRUE(ai_draft->load_workspace_state({{"version", 1}, {"drafts", nlohmann::json::array({
        {{"project", project().project()->id}, {"text", "Unsent hidden AI question"}, {"agent_text", "Unsent hidden agent draft"}, {"intent", 0}}})}}));
    ai_state = ai_draft->save_workspace_state();
    viewer_editor = &f.area("a2").editor(); camera_state = viewer_editor->save_workspace_state();
    camera_state["camera"]["position"] = {6.0, 4.0, 9.0};
    ASSERT_TRUE(viewer_editor->load_workspace_state(camera_state)); frame();
    camera_state = viewer_editor->save_workspace_state();
    ASSERT_EQ(area().editor().type().id, kEditorReports);
    clicks = wheels = keys = text_events = moves = 0; action_log.clear();
  }
};

TEST_P(ReportGenerationMouse, ExplicitSourceReviewSendEditAndSaveByVisibleControls)
{
  ASSERT_NO_FATAL_FAILURE(maximize_by_keyboard());
  ASSERT_NO_FATAL_FAILURE(choose_reviewed_inputs());
  ASSERT_NO_FATAL_FAILURE(commit_text("reports_generation_question", "Write only the selected frozen observations; distinguish run state from results.", true));
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  ASSERT_NO_FATAL_FAILURE(protected_state());
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_prepare"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_start"));
  ASSERT_EQ(count("project.requests.create"), 1u);
  EXPECT_EQ(count("project.requests.start"), 0u); EXPECT_EQ(count("adapter_send"), 0u);
  const auto request_id = calls("project.requests.create").front().at("request_id");
  const auto prepared = call("project.reports.generation_request", {{"handle", handle()}, {"request_id", request_id}});
  ASSERT_TRUE(prepared.is_object()); EXPECT_EQ(prepared.at("request").at("status"), "pending");
  ASSERT_EQ(prepared.at("input").at("report_input").at("sources").size(), 4u);
  ASSERT_EQ(prepared.at("input").at("report_input").at("assets").size(), 1u);
  EXPECT_TRUE(prepared.at("response").is_null());
  // The source file is gone before the explicit send/save. Only the verified snapshot remains.
  ASSERT_TRUE(fs::remove(dir.path() / "project/plot.png"));
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_start"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_body"));
  ASSERT_NO_FATAL_FAILURE(commit_text("reports_generation_name", "Reviewed UI report / 已复核报告", false));
  ASSERT_NO_FATAL_FAILURE(commit_text("reports_generation_body", edited_text, true));
  ASSERT_TRUE(area().editor().has_unsaved_changes());
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("adapter_send"), 1u);
  EXPECT_EQ(count("project.reports.create_generated"), 0u);
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_save"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame(); const auto state = area().editor().save_workspace_state();
    return state.contains("report_id") && state.at("report_id").is_string() && !state.at("report_id").get<std::string>().empty();
  }, 30));
  const auto reading = area().editor().save_workspace_state();
  const auto saved = call("project.reports.get", {{"handle", handle()}, {"report_id", reading.at("report_id")}});
  ASSERT_TRUE(saved.is_object()); const auto &manifest = saved.at("report").at("manifest");
  EXPECT_EQ(saved.at("report").at("format"), "stk.report/2");
  EXPECT_EQ(manifest.at("generation").at("request_id"), request_id);
  EXPECT_EQ(manifest.at("generation").at("body"), edited_text); EXPECT_EQ(manifest.at("generation").at("edited"), true);
  EXPECT_EQ(manifest.at("sources").size(), 4u); EXPECT_EQ(manifest.at("assets").size(), 2u);
  EXPECT_EQ(manifest.at("assets")[1].at("path"), "images/plot.png");
  EXPECT_EQ(count("project.requests.start"), 1u); EXPECT_EQ(count("project.reports.create_generated"), 1u);
  EXPECT_EQ(count("project.reports.asset"), 0u); EXPECT_EQ(count("project.reports.preview"), 0u);
  EXPECT_EQ(count("project.reports.preview_resources"), 0u);
  ASSERT_NO_FATAL_FAILURE(protected_state());
  RecordProperty("result", "saved readable report/2, four frozen source kinds, frozen PNG, edited body, one explicit model send; no asset/preview reads");
  record_actions();
}


// This is a state-import regression, not an additional mouse-click acceptance claim.
// Its draft is nevertheless produced through the same visible controls as the flow above.
TEST_P(ReportGenerationMouse, WorkspaceV3RejectsAtomicallyAndRestoresWithoutReadingOrSending)
{
  ASSERT_NO_FATAL_FAILURE(maximize_by_keyboard());
  ASSERT_NO_FATAL_FAILURE(choose_reviewed_inputs());
  ASSERT_NO_FATAL_FAILURE(commit_text("reports_generation_question", "Preserve this unsent report request across workspace restore.", true));
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_prepare"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_start"));
  const auto before = area().editor().save_workspace_state();
  ASSERT_EQ(before.at("version"), 3);
  ASSERT_EQ(before.size(), 8u);
  const auto &draft = before.at("generation_draft");
  ASSERT_EQ(draft.size(), 8u);
  ASSERT_EQ(draft.at("generation").at("phase"), "prepared");
  ASSERT_EQ(draft.at("generation").at("send_attempted"), false);
  ASSERT_EQ(draft.at("inputs").at("sources").size(), 4u);
  ASSERT_EQ(draft.at("inputs").at("assets").size(), 1u);
  const auto request_id = draft.at("generation").at("request_id").get<std::string>();
  auto stale_start = widget("reports_generation_start")->on_click;
  ASSERT_TRUE(bool(stale_start));
  const auto edits_before = project().project()->revision;
  const auto creates_before = count("project.requests.create");
  const auto messages_before = count("project.discussion.add");
  std::vector<std::pair<std::string, nlohmann::json>> bad;
  auto candidate = before;
  candidate["handle"] = handle();
  bad.emplace_back("untrusted live handle in outer envelope", candidate);
  candidate = before;
  candidate["generation_draft"]["question"] = std::string(65537, 'x');
  bad.emplace_back("oversized UTF-8 input before copying", candidate);
  candidate = before;
  candidate["generation_draft"]["generation"]["project_id"] = "11111111-1111-4111-8111-111111111111";
  bad.emplace_back("valid UUID bound to a different project", candidate);
  candidate = before;
  candidate["generation_draft"]["inputs"]["pending"] = {{"report_id", "11111111-1111-4111-8111-111111111111"}};
  bad.emplace_back("write receipt injected into read-only input selector", candidate);
  candidate = before;
  candidate["generation_draft"]["generation"]["phase"] = "start_pending";
  bad.emplace_back("pending send without immutable send-attempt marker", candidate);
  candidate = before;
  candidate["generation_draft"]["generation"]["body"] = "forged body before initialization";
  bad.emplace_back("body contradicts uninitialized flag", candidate);
  candidate = before;
  candidate["generation_draft"]["question"] = std::string("valid\0hidden", 12);
  bad.emplace_back("embedded NUL in draft text", candidate);
  candidate = before;
  candidate["create_draft"] = {{"version", 2}};
  bad.emplace_back("invalid sibling creation draft", candidate);
  for (auto &[reason, payload] : bad) {
    SCOPED_TRACE(reason);
    // This legal reader change must not be partially applied before a nested rejection.
    payload["text_page"] = before.at("text_page").get<int>() + 1;
    EXPECT_FALSE(area().editor().load_workspace_state(payload));
    EXPECT_EQ(area().editor().save_workspace_state(), before);
    EXPECT_TRUE(area().editor().has_unsaved_changes());
    ASSERT_NO_FATAL_FAILURE(protected_state());
  }
  const std::vector<std::string> no_implicit_calls{
      "project.contexts.get", "project.reports.review_sources", "project.snapshots.get",
      "project.snapshots.list_summaries", "project.reports.generation_request", "project.requests.get",
      "project.requests.progress", "project.requests.start", "project.requests.cancel", "project.requests.recover",
      "project.discussion.add", "project.requests.create", "project.reports.create_generated",
      "project.reports.asset", "project.reports.preview", "project.reports.preview_resources",
      "script.execute", "graph.evaluate", "adapter_send"};
  std::vector<size_t> counts_before;
  for (const auto &method : no_implicit_calls) { counts_before.push_back(count(method)); }
  ASSERT_TRUE(area().editor().load_workspace_state(before));
  for (int i = 0; i < 12; ++i) { loop.run_ready(); frame(); }
  ASSERT_TRUE(call("project.list", Json::object()).is_object()); // Drain earlier real bridge work.
  frame();
  EXPECT_EQ(area().editor().save_workspace_state().at("generation_draft"), draft);
  EXPECT_TRUE(area().editor().has_unsaved_changes());
  const auto *start = widget("reports_generation_start");
  ASSERT_NE(start, nullptr);
  EXPECT_FALSE(start->enabled); // Cached request was deliberately not restored or fetched.
  stale_start(); // Retained pre-restore callback is a negative lifetime test, not a UI action.
  frame();
  ASSERT_TRUE(call("project.list", Json::object()).is_object());
  for (size_t i = 0; i < no_implicit_calls.size(); ++i) {
    EXPECT_EQ(count(no_implicit_calls[i]), counts_before[i]) << no_implicit_calls[i];
  }
  EXPECT_EQ(project().project()->revision, edits_before);
  EXPECT_EQ(count("project.requests.create"), creates_before);
  EXPECT_EQ(count("project.discussion.add"), messages_before);
  ASSERT_NO_FATAL_FAILURE(protected_state());
  // A fresh explicit read may revalidate the same original request. It still does not send.
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_check"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_start"));
  ASSERT_EQ(calls("project.reports.generation_request").back().at("request_id").get<std::string>(), request_id);
  EXPECT_EQ(count("project.requests.start"), 0u);
  EXPECT_EQ(count("adapter_send"), 0u);
  EXPECT_EQ(count("project.requests.create"), creates_before);
  EXPECT_EQ(area().editor().save_workspace_state().at("generation_draft").at("generation").at("request_id"), request_id);
  ASSERT_NO_FATAL_FAILURE(protected_state());
  RecordProperty("workspace_result", "v3 rejects eight malformed payloads atomically; restore and stale callback do not read, send or execute; fresh explicit check queries only the original UUID");
}


// ScreenDriver::key/click intentionally build a frame. Use send/down/up here so
// this regression really dispatches consecutive events against one set of bindings.
TEST_P(ReportGenerationMouse, ConsecutiveTextCommitsAndTabsPreserveSiblingValuesWithoutAFrame)
{
  ASSERT_NO_FATAL_FAILURE(maximize_by_keyboard());
  ASSERT_NO_FATAL_FAILURE(choose_reviewed_inputs());
  const auto raw_key = [&](wm::Key value, uint32_t modifiers) {
    wm::Event event;
    event.type = wm::EventType::KeyDown;
    event.key = value;
    event.modifiers = modifiers;
    ASSERT_TRUE(f.drv->send(event));
    event.type = wm::EventType::KeyUp;
    f.drv->send(event);
    ++keys;
  };
  const auto raw_text = [&](const std::string &value) {
    ASSERT_NO_FATAL_FAILURE(insert_text(value));
  };
  const auto raw_click = [&](const std::string &key) {
    const auto [x, y] = f.widget_center(key);
    f.drv->move(x, y);
    ASSERT_TRUE(f.drv->down(x, y));
    f.drv->up(x, y);
    f.drv->time_ms += 500;
    ++clicks;
  };
#ifdef __APPLE__
  constexpr uint32_t select_modifier = wm::ModOS;
#else
  constexpr uint32_t select_modifier = wm::ModCtrl;
#endif
  const std::string initial_question = "Preserve the selected evidence";
  const std::string final_question = initial_question + " and its frozen provenance.";
  ASSERT_NO_FATAL_FAILURE(replace_text("reports_generation_question", initial_question));
  const auto *question = widget("reports_generation_question");
  ASSERT_NE(question, nullptr);
  ASSERT_TRUE(bool(question->string.get));
  // No frame from the first commit through the second commit. Re-entering must
  // initialize TextEdit from the just-committed value, not an invalidated empty getter.
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::Enter, select_modifier));
  EXPECT_EQ(question->string.get(), initial_question);
  ASSERT_NO_FATAL_FAILURE(raw_click("reports_generation_question"));
  ASSERT_EQ(f.screen.ui()->editing(), question->id);
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::End, wm::ModNone));
  ASSERT_NO_FATAL_FAILURE(raw_text(" and its frozen provenance."));
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::Enter, select_modifier));
  EXPECT_EQ(question->string.get(), final_question);
  frame();
  EXPECT_EQ(area().editor().save_workspace_state().at("generation_draft").at("question"), final_question);
  EXPECT_EQ(count("project.requests.create"), 0u);
  EXPECT_EQ(count("project.requests.start"), 0u);
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_prepare"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_start"));
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_start"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("reports_generation_body"));
  ASSERT_NO_FATAL_FAILURE(scroll_to("reports_generation_body"));
  ASSERT_TRUE(visible(widget("reports_generation_name")));
  ASSERT_TRUE(visible(widget("reports_generation_path")));
  ASSERT_TRUE(visible(widget("reports_generation_body")));
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_name"));
  const auto *name = widget("reports_generation_name");
  const auto *path = widget("reports_generation_path");
  const auto *body = widget("reports_generation_body");
  ASSERT_NE(name, nullptr);
  ASSERT_NE(path, nullptr);
  ASSERT_NE(body, nullptr);
  ASSERT_TRUE(bool(body->string.get));
  const auto original_body = body->string.get();
  ASSERT_EQ(original_body, reply_text);
  const std::string final_name = "Tabbed report / 连续输入";
  const std::string final_path = "reviewed/report.md";
  const std::string final_body = "# Tabbed report\n\nExact edited text / 精确编辑正文。\n";
  // No helper which renders, pumps the bridge, or rebuilds widgets is allowed
  // between this name edit and the body commit.
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::A, select_modifier));
  ASSERT_NO_FATAL_FAILURE(raw_text(final_name));
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::Tab, wm::ModNone));
  ASSERT_EQ(f.screen.ui()->editing(), path->id);
  EXPECT_EQ(name->string.get(), final_name);
  EXPECT_EQ(path->string.get(), "report.md");
  EXPECT_EQ(body->string.get(), original_body);
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::A, select_modifier));
  ASSERT_NO_FATAL_FAILURE(raw_text(final_path));
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::Tab, wm::ModNone));
  ASSERT_EQ(f.screen.ui()->editing(), body->id);
  EXPECT_EQ(path->string.get(), final_path);
  EXPECT_EQ(body->string.get(), original_body);
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::A, select_modifier));
  ASSERT_NO_FATAL_FAILURE(raw_text(final_body));
  ASSERT_NO_FATAL_FAILURE(raw_key(wm::Key::Enter, select_modifier));
  EXPECT_EQ(body->string.get(), final_body);
  frame();
  const auto generated = area().editor().save_workspace_state().at("generation_draft").at("generation");
  EXPECT_EQ(generated.at("name"), final_name);
  EXPECT_EQ(generated.at("entry_path"), final_path);
  EXPECT_EQ(generated.at("body"), final_body);
  EXPECT_EQ(count("project.requests.start"), 1u);
  EXPECT_EQ(count("adapter_send"), 1u);
  ASSERT_NO_FATAL_FAILURE(protected_state());
  ASSERT_NO_FATAL_FAILURE(click("reports_generation_save"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame();
    const auto state = area().editor().save_workspace_state();
    return state.contains("report_id") && !state.at("report_id").get<std::string>().empty();
  }, 30));
  const auto reading = area().editor().save_workspace_state();
  const auto saved = call("project.reports.get", {{"handle", handle()}, {"report_id", reading.at("report_id")}});
  ASSERT_TRUE(saved.is_object());
  EXPECT_EQ(saved.at("report").at("name"), final_name);
  EXPECT_EQ(saved.at("report").at("manifest").at("entry_path"), final_path);
  EXPECT_EQ(saved.at("report").at("manifest").at("generation").at("body"), final_body);
  EXPECT_EQ(count("project.reports.create_generated"), 1u);
  ASSERT_NO_FATAL_FAILURE(protected_state());
  RecordProperty("input_regression", "question commit/re-entry and name-Tab-path-Tab-body commit dispatch without intervening frames; exact saved values verified through the real bridge");
}

INSTANTIATE_TEST_SUITE_P(LanguagesAndWidths, ReportGenerationMouse,
    ::testing::Combine(::testing::Values("en", "zh_CN"), ::testing::Values(1440, 560)),
    [](const ::testing::TestParamInfo<ReportGenerationMouse::ParamType> &info) {
      return std::string(std::get<0>(info.param)) + "_" + std::to_string(std::get<1>(info.param));
    });
} // namespace
} // namespace stk::app
