/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/graph.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;

fs::path payload_fixture()
{
  return fs::path(STK_REPO_ROOT) / "desktop/tests/viewer/fixtures/muferro_domains";
}

Json inspection_presets()
{
  Json list = Json::array();
  for (const auto *name : {"muferro-domains", "muferro-polarization-glyphs"}) {
    list.push_back(io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets" / (std::string(name) + ".json")));
  }
  return Json{{"presets", std::move(list)}};
}

Json inspection_catalog()
{
  return io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json");
}

// Portable NDJSON fixture. It returns a static payload, but hashes the backend's independent
// preset document with the real Python hash contract. Explicit release keeps pending/cancel
// tests deterministic without wall-clock delays, native-only fake processes, or evaluations.
constexpr const char *kInspectionBridge = R"PY(
import copy
import json
import os
import shutil
import sys
from pathlib import Path
from suan.graph.schema import graph_hash

root, temporary = map(Path, sys.argv[1:3])
fixture = root / 'desktop/tests/viewer/fixtures/muferro_domains'
blob_dir = temporary / 'blobs'
requests = []
pending = {}
cancels = 0

def respond(identity, result):
    print(json.dumps({'id': identity, 'result': result}, ensure_ascii=True), flush=True)

def cancelled(identity):
    print(json.dumps({'id': identity, 'error': {'code': 'cancelled',
          'message': 'Fixture evaluation cancelled', 'retryable': False}}), flush=True)

def presets():
    return json.loads((temporary / 'presets.json').read_text(encoding='utf-8'))

def result_for(params):
    request = params['request']
    graph = next(p['graph'] for p in presets()['presets'] if p['id'] == request['preset'])
    step_value = request.get('parameters', {}).get('step', 'latest')
    step = max(0, min(2, int(step_value))) if isinstance(step_value, (int, float)) else (0 if step_value == 'first' else 2)
    manifest = json.loads((fixture / 'manifest.json').read_text(encoding='utf-8'))
    for buffer in manifest['buffers']:
        digest = buffer['sha256']
        target = blob_dir / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(fixture / (digest + '.bin'), target)
        buffer['uri'] = 'sha256:' + digest
    manifest['view']['time'] = {'step': step}
    hashed = graph_hash(graph)
    result = {'schema': 'stk.graph-result/1', 'graph_hash': hashed,
              'graph_sha256': hashed.split(':', 1)[1], 'profile': 'desktop',
              'parameters': {'step': {'value': step, 'choices': [0, 1, 2]}},
              'outputs': {request.get('outputs', ['view'])[0]: {'type': 'payload', 'manifest': manifest}},
              'keys': {}, 'evaluated': [node['id'] for node in graph['nodes']],
              'timings': {}, 'cache': {'hits': 0, 'misses': len(graph['nodes'])}, 'warnings': []}
    mode_file = temporary / 'receipt-mode'
    mode = mode_file.read_text(encoding='utf-8') if mode_file.exists() else ''
    if mode == 'missing':
        del result['graph_hash']
    elif mode == 'invalid':
        result['graph_sha256'] = 'not-a-sha256'
    elif mode == 'conflicting':
        result['graph_sha256'] = '0' * 64
    return {'result': result, 'blob_dir': str(blob_dir)}

for line in sys.stdin:
    message = json.loads(line)
    identity, method, params = message['id'], message['method'], message.get('params', {})
    if method == 'hello':
        respond(identity, {'protocol': 1,
            'server': {'name': 'inspection-fixture', 'version': '1', 'python': sys.version,
                       'platform': sys.platform, 'pid': os.getpid()},
            'methods': ['hello', 'graph.presets', 'graph.catalog', 'graph.evaluate', 'graph.cancel'],
            'events': [], 'limits': {'max_line_bytes': 16777216, 'max_inflight': 64},
            'paths': {'state_dir': str(temporary), 'cache_dir': str(temporary),
                      'blob_dir': str(blob_dir), 'download_dir': str(temporary)}, 'resumed_transfers': []})
    elif method == 'graph.presets':
        respond(identity, presets())
    elif method == 'graph.catalog':
        respond(identity, {'catalog': json.loads((root / 'docs/specs/catalog/stk-catalog-m1.json').read_text(encoding='utf-8'))})
    elif method == 'graph.evaluate':
        requests.append(copy.deepcopy(params))
        pending[params['eval_id']] = (identity, result_for(params))
    elif method == 'graph.cancel':
        entry = pending.pop(params['eval_id'], None)
        if entry:
            cancels += 1
            cancelled(entry[0])
        respond(identity, {'cancelled': entry is not None})
    elif method == 'inspection.release':
        ready, pending = pending, {}
        for request_id, result in ready.values():
            respond(request_id, result)
        respond(identity, {})
    elif method == 'stats':
        respond(identity, {'evaluations': len(requests), 'cancels': cancels, 'evaluate_requests': requests})
    elif method == 'colormaps.list':
        respond(identity, {'colormaps': []})
    else:
        respond(identity, {})
)PY";

class ViewerGraphInspectionTest : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"viewer-inspection"};
  AppStore store;
  std::unique_ptr<bridge::Client> client;
  ViewerState &viewer = store.viewer();
  double now = 1000;

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run inspection bridge tests"; }
    { std::ofstream out(directory.path() / "bridge.py", std::ios::binary); out << kInspectionBridge; ASSERT_TRUE(out.good()); }
    write_backend_presets(inspection_presets());
    bridge::ClientOptions options;
    options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), STK_REPO_ROOT, directory.str()};
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_BRIDGE_VALIDATE"] = "0";
    options.executor = loop.executor();
    client = bridge::Client::create(std::move(options));
    ASSERT_TRUE(client->start());
    ASSERT_TRUE(client->wait_ready(30)) << client->bridge_log().text();
    loop.run_ready();
    store.set_bridge(client.get());
    viewer.clock = [this] { return now; };
    viewer.prefetch_neighbours = false;
    viewer.set_metadata(inspection_presets(), inspection_catalog());
  }

  void TearDown() override
  {
    viewer.close(); store.set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
  }

  void open_run(const Json &parameters = Json::object())
  {
    const auto run = directory.path() / "run";
    fs::create_directories(run);
    ASSERT_TRUE(viewer.open_path(core::path_to_utf8(run), "muferro-domains", parameters));
  }

  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] {
      viewer.pump();
      if (viewer.evaluating()) { release(); }
      return !viewer.evaluating() && bool(viewer.payload());
    }, 30)) << viewer.eval_error() << client->bridge_log().text();
  }

  void release() { client->call("inspection.release"); }

  void write_backend_presets(const Json &presets)
  {
    std::ofstream out(directory.path() / "presets.json", std::ios::binary);
    out << presets.dump(); ASSERT_TRUE(out.good());
  }

  void receipt_mode(const char *mode)
  {
    std::ofstream out(directory.path() / "receipt-mode", std::ios::binary);
    out << mode; ASSERT_TRUE(out.good());
  }

  Json stats()
  {
    std::optional<bridge::Result<Json>> response;
    client->call("stats").then([&](auto result) { response = std::move(result); });
    EXPECT_TRUE(loop.pump_until([&] { return response.has_value(); }, 30));
    EXPECT_TRUE(response && response->ok());
    return response && response->ok() ? response->value() : Json();
  }
};

TEST_F(ViewerGraphInspectionTest, PureReadsReuseAnImmutableSnapshotWithoutStartingWork)
{
  const auto before = viewer.graph_inspection();
  EXPECT_EQ(before, viewer.graph_inspection());
  EXPECT_FALSE(before->desired); EXPECT_FALSE(before->shown_configuration);
  EXPECT_FALSE(before->shown_result); EXPECT_FALSE(before->has_payload);
  EXPECT_FALSE(before->shown_matches_desired); EXPECT_FALSE(before->shown_graph_verified);
  ASSERT_NO_FATAL_FAILURE(open_run());
  const auto running = viewer.graph_inspection();
  ASSERT_TRUE(running->desired); EXPECT_TRUE(running->evaluating);
  EXPECT_EQ(running->desired->preset_id, "muferro-domains");
  EXPECT_EQ(running->desired->parameters.at("step"), "latest");
  EXPECT_FALSE(running->desired->requested_outputs.empty());
  const int started = viewer.evaluations_started();
  const auto version = viewer.version();
  for (int i = 0; i < 100; ++i) { EXPECT_EQ(viewer.graph_inspection(), running); }
  EXPECT_EQ(viewer.version(), version); EXPECT_EQ(viewer.evaluations_started(), started);
  EXPECT_FALSE(before->desired); EXPECT_FALSE(before->evaluating);
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  ASSERT_TRUE(shown->shown_configuration); ASSERT_TRUE(shown->shown_result);
  ASSERT_TRUE(shown->shown_evaluation); ASSERT_TRUE(shown->shown_matches_desired);
  ASSERT_TRUE(shown->shown_graph_verified); EXPECT_TRUE(*shown->shown_graph_verified);
  EXPECT_EQ(shown->shown_result->graph_hash, io::graph_hash(shown->shown_configuration->graph));
  EXPECT_TRUE(*shown->shown_matches_desired); EXPECT_TRUE(shown->has_payload); EXPECT_FALSE(shown->evaluating);
  EXPECT_EQ(shown->shown_configuration->parameters.at("step"), "latest");
  EXPECT_EQ(shown->shown_resolved_parameters.at("step"), 2);
  EXPECT_EQ(shown->shown_result->raw, viewer.result()->raw);
  EXPECT_EQ(shown->shown_evaluation->eval_id, viewer.last_eval()->eval_id);
  EXPECT_EQ(stats().at("evaluations"), 1);
  EXPECT_TRUE(running->evaluating); EXPECT_FALSE(running->shown_result);
}

TEST_F(ViewerGraphInspectionTest, PendingEditsDoNotRelabelTheDisplayedResult)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  viewer.set_auto_evaluate(false);
  const auto original = viewer.graph_inspection();
  const auto payload = viewer.base_payload();
  const auto receipt = original->shown_evaluation->eval_id;
  viewer.set_parameter("min_magnitude", ui::FormValue::number(0.75));
  const auto changed = viewer.graph_inspection();
  ASSERT_TRUE(changed->desired); ASSERT_TRUE(changed->shown_configuration);
  ASSERT_TRUE(changed->shown_matches_desired); EXPECT_FALSE(*changed->shown_matches_desired);
  EXPECT_EQ(changed->desired->parameters.at("min_magnitude"), 0.75);
  EXPECT_EQ(changed->shown_configuration->parameters.at("min_magnitude"), 0.1);
  EXPECT_EQ(changed->shown_resolved_parameters.at("min_magnitude"), 0.1);
  EXPECT_EQ(changed->pending_edit, "data"); EXPECT_FALSE(changed->evaluating);
  EXPECT_EQ(changed->shown_evaluation->eval_id, receipt); EXPECT_EQ(viewer.base_payload(), payload);
  EXPECT_TRUE(*original->shown_matches_desired);
  EXPECT_EQ(viewer.evaluations_started(), 1);
}

TEST_F(ViewerGraphInspectionTest, DispatchFreezesGraphParametersAndRequestedOutputs)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  const auto dispatched = viewer.graph_inspection();
  ASSERT_TRUE(dispatched->desired);
  viewer.set_auto_evaluate(false);
  viewer.set_parameter("min_magnitude", ui::FormValue::number(0.85));
  auto presets = inspection_presets();
  presets["presets"][0]["graph"]["name"] = "Later local metadata";
  const auto output = presets["presets"][0]["graph"]["outputs"]["view"];
  presets["presets"][0]["graph"]["outputs"] = Json{{"other-view", output}};
  viewer.set_metadata(presets, inspection_catalog());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  ASSERT_TRUE(shown->shown_configuration); ASSERT_TRUE(shown->desired);
  ASSERT_TRUE(shown->shown_graph_verified); EXPECT_TRUE(*shown->shown_graph_verified);
  EXPECT_EQ(shown->shown_configuration->graph, dispatched->desired->graph);
  EXPECT_EQ(shown->shown_configuration->parameters, dispatched->desired->parameters);
  EXPECT_EQ(shown->shown_configuration->requested_outputs, dispatched->desired->requested_outputs);
  EXPECT_NE(shown->desired->requested_outputs, shown->shown_configuration->requested_outputs);
  EXPECT_NE(shown->desired->graph, shown->shown_configuration->graph);
  EXPECT_EQ(shown->desired->parameters.at("min_magnitude"), 0.85);
  ASSERT_TRUE(shown->shown_matches_desired); EXPECT_FALSE(*shown->shown_matches_desired);
  const auto requested = stats().at("evaluate_requests"); ASSERT_EQ(requested.size(), 1u);
  EXPECT_EQ(requested[0].at("request").at("parameters"), shown->shown_configuration->parameters);
}

TEST_F(ViewerGraphInspectionTest, GraphMetadataChangesInvalidateInspectionWithoutEvaluation)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto original = viewer.graph_inspection();
  auto presets = inspection_presets();
  presets["presets"][0]["graph"]["nodes"][0]["params"]["new_setting"] = 7;
  viewer.set_metadata(presets, inspection_catalog());
  const auto changed = viewer.graph_inspection();
  EXPECT_NE(changed, original); EXPECT_GT(changed->version, original->version);
  ASSERT_TRUE(changed->shown_matches_desired); EXPECT_FALSE(*changed->shown_matches_desired);
  EXPECT_EQ(changed->shown_configuration->graph, original->shown_configuration->graph);
  EXPECT_EQ(viewer.evaluations_started(), 1); EXPECT_EQ(viewer.evaluations_cancelled(), 0);
}

TEST_F(ViewerGraphInspectionTest, CachedStepsKeepTheirOriginalReceiptAndExactRequestedConfiguration)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto latest = viewer.graph_inspection();
  viewer.set_step_index(0);
  now += 0.11; // Uncached scrubber steps use the Viewer's 100 ms debounce.
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto first = viewer.graph_inspection();
  ASSERT_TRUE(first->shown_configuration); EXPECT_EQ(first->shown_configuration->parameters.at("step"), 0);
  const auto calls = viewer.evaluations_started();
  viewer.set_step_index(2);
  const auto cached = viewer.graph_inspection();
  EXPECT_EQ(viewer.evaluations_started(), calls); EXPECT_FALSE(cached->evaluating);
  ASSERT_TRUE(cached->shown_evaluation); EXPECT_TRUE(cached->shown_evaluation->from_cache);
  ASSERT_TRUE(cached->shown_graph_verified); EXPECT_TRUE(*cached->shown_graph_verified);
  EXPECT_TRUE(cached->shown_evaluation->evaluated.empty());
  EXPECT_FALSE(cached->shown_result->evaluated.empty()); // Historical bridge result, not a new evaluation.
  EXPECT_EQ(cached->shown_evaluation->eval_id, latest->shown_evaluation->eval_id);
  EXPECT_EQ(cached->shown_configuration->parameters.at("step"), "latest");
  EXPECT_EQ(cached->shown_resolved_parameters.at("step"), 2);
  ASSERT_TRUE(cached->shown_matches_desired); EXPECT_FALSE(*cached->shown_matches_desired);
  viewer.set_step_index(0);
  const auto reused = viewer.graph_inspection();
  EXPECT_EQ(reused->shown_evaluation->eval_id, first->shown_evaluation->eval_id);
  ASSERT_TRUE(reused->shown_matches_desired); EXPECT_TRUE(*reused->shown_matches_desired);
  EXPECT_EQ(viewer.evaluations_started(), calls);
}

TEST_F(ViewerGraphInspectionTest, PresetAndSourceSwitchesCannotReuseAnotherRequestsProvenance)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto original = viewer.graph_inspection();
  viewer.select_preset("muferro-polarization-glyphs");
  const auto pending = viewer.graph_inspection();
  EXPECT_EQ(pending->desired->preset_id, "muferro-polarization-glyphs");
  EXPECT_EQ(pending->shown_configuration->preset_id, "muferro-domains");
  ASSERT_TRUE(pending->shown_matches_desired); EXPECT_FALSE(*pending->shown_matches_desired);
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(viewer.graph_inspection()->shown_configuration->preset_id, "muferro-polarization-glyphs");
  OpenResultRequest task;
  task.connection = "runtime:inspection"; task.task_id = "task-A"; task.workspace_id = "workspace-A";
  task.preset = "muferro-domains";
  ASSERT_TRUE(viewer.open(task));
  const auto opening = viewer.graph_inspection();
  EXPECT_FALSE(opening->shown_configuration); EXPECT_FALSE(opening->has_payload);
  EXPECT_EQ(opening->desired->source.workspace_id, "workspace-A");
  task.task_id = "task-B"; task.workspace_id = "workspace-B";
  ASSERT_TRUE(viewer.open(task)); ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  EXPECT_EQ(shown->shown_configuration->source.task_id, "task-B");
  EXPECT_EQ(shown->shown_configuration->source.workspace_id, "workspace-B");
  EXPECT_EQ(original->shown_configuration->source.kind, SourceKind::RunDir);
  EXPECT_EQ(viewer.evaluations_cancelled(), 1);
}

TEST_F(ViewerGraphInspectionTest, PrefetchedConfigurationIsPublishedOnlyWhenItsFrameIsShown)
{
  viewer.prefetch_neighbours = true;
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto original = viewer.graph_inspection();
  ASSERT_TRUE(loop.pump_until([&] { viewer.pump(); release(); return viewer.prefetched_count() >= 1; }, 30));
  const auto prefetched = viewer.graph_inspection();
  EXPECT_EQ(prefetched->shown_evaluation->eval_id, original->shown_evaluation->eval_id);
  EXPECT_EQ(prefetched->shown_configuration->parameters.at("step"), "latest");
  viewer.prefetch_neighbours = false;
  const auto started = viewer.evaluations_started();
  viewer.set_step_index(1);
  const auto shown = viewer.graph_inspection();
  EXPECT_EQ(shown->shown_configuration->parameters.at("step"), 1);
  EXPECT_EQ(shown->shown_resolved_parameters.at("step"), 1);
  EXPECT_TRUE(shown->shown_evaluation->from_cache);
  EXPECT_NE(shown->shown_evaluation->eval_id, original->shown_evaluation->eval_id);
  EXPECT_EQ(viewer.evaluations_started(), started);
  ASSERT_TRUE(shown->shown_matches_desired); EXPECT_TRUE(*shown->shown_matches_desired);
}

TEST_F(ViewerGraphInspectionTest, RemoteCancellationInvalidatesCachedRunningStatus)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  const auto running = viewer.graph_inspection(); ASSERT_TRUE(running->evaluating);
  client->graph_cancel(viewer.progress().eval_id);
  ASSERT_TRUE(loop.pump_until([&] { return !viewer.evaluating(); }, 30));
  const auto cancelled = viewer.graph_inspection();
  EXPECT_NE(cancelled, running); EXPECT_GT(cancelled->version, running->version);
  EXPECT_FALSE(cancelled->evaluating); EXPECT_FALSE(cancelled->shown_configuration);
  EXPECT_FALSE(cancelled->shown_matches_desired); EXPECT_EQ(viewer.evaluations_started(), 1);
}

TEST_F(ViewerGraphInspectionTest, BackendPresetMismatchRetainsLocalIntentButDoesNotVerifyTheShownGraph)
{
  auto backend = inspection_presets();
  backend["presets"][0]["graph"]["nodes"][0]["params"]["binding"] = "different-runtime-binding";
  write_backend_presets(backend);
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  ASSERT_TRUE(shown->shown_configuration); ASSERT_TRUE(shown->shown_result);
  ASSERT_TRUE(shown->shown_graph_verified); EXPECT_FALSE(*shown->shown_graph_verified);
  EXPECT_FALSE(shown->shown_matches_desired); EXPECT_TRUE(shown->has_payload);
  EXPECT_EQ(shown->shown_result->graph_hash, io::graph_hash(backend["presets"][0]["graph"]));
  EXPECT_NE(shown->shown_result->graph_hash, io::graph_hash(shown->shown_configuration->graph));
  EXPECT_EQ(shown->shown_configuration->graph, shown->desired->graph);
  EXPECT_EQ(viewer.evaluations_started(), 1); EXPECT_EQ(stats().at("evaluations"), 1);
}

TEST_F(ViewerGraphInspectionTest, SemanticVerificationIgnoresBackendLabelsAndNodeOrder)
{
  auto backend = inspection_presets();
  auto &graph = backend["presets"][0]["graph"];
  graph["name"] = "Runtime display label";
  graph["nodes"][0]["label"] = "Runtime node label";
  graph["ui"] = Json{{"pan", Json::array({1, 2})}};
  std::reverse(graph["nodes"].begin(), graph["nodes"].end());
  write_backend_presets(backend);
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  ASSERT_TRUE(shown->shown_configuration); EXPECT_NE(shown->shown_configuration->graph, graph);
  ASSERT_TRUE(shown->shown_graph_verified); EXPECT_TRUE(*shown->shown_graph_verified);
  ASSERT_TRUE(shown->shown_matches_desired); EXPECT_TRUE(*shown->shown_matches_desired);
}

TEST_F(ViewerGraphInspectionTest, MissingOrMalformedReceiptHashesLeaveVerificationUnavailable)
{
  for (const char *mode : {"missing", "invalid"}) {
    SCOPED_TRACE(mode);
    receipt_mode(mode);
    ASSERT_NO_FATAL_FAILURE(open_run());
    ASSERT_NO_FATAL_FAILURE(settled());
    const auto shown = viewer.graph_inspection();
    ASSERT_TRUE(shown->shown_configuration); ASSERT_TRUE(shown->shown_result);
    EXPECT_FALSE(shown->shown_graph_verified); EXPECT_FALSE(shown->shown_matches_desired);
    EXPECT_TRUE(shown->has_payload); EXPECT_EQ(shown->shown_configuration->graph, shown->desired->graph);
    viewer.close();
  }
}

TEST_F(ViewerGraphInspectionTest, ContradictoryReceiptHashesDoNotVerifyEvenWhenTheGraphHashMatches)
{
  receipt_mode("conflicting");
  ASSERT_NO_FATAL_FAILURE(open_run());
  ASSERT_NO_FATAL_FAILURE(settled());
  const auto shown = viewer.graph_inspection();
  ASSERT_TRUE(shown->shown_configuration); ASSERT_TRUE(shown->shown_result);
  EXPECT_EQ(shown->shown_result->graph_hash, io::graph_hash(shown->shown_configuration->graph));
  ASSERT_TRUE(shown->shown_graph_verified); EXPECT_FALSE(*shown->shown_graph_verified);
  EXPECT_FALSE(shown->shown_matches_desired); EXPECT_TRUE(shown->has_payload);
}

TEST(ViewerGraphInspection, ImportedPayloadsAndResultsNeverInventTheOriginalGraph)
{
  bridge::test::TempDir directory{"inspection-import"};
  AppStore store;
  auto &viewer = store.viewer();
  viewer.set_metadata(inspection_presets(), inspection_catalog());
  viewer.select_preset("muferro-domains");
  ASSERT_TRUE(viewer.open_path(core::path_to_utf8(payload_fixture())));
  const auto payload = viewer.graph_inspection();
  EXPECT_TRUE(payload->has_payload); EXPECT_FALSE(payload->desired); EXPECT_FALSE(payload->shown_configuration);
  EXPECT_FALSE(payload->shown_result); EXPECT_FALSE(payload->shown_evaluation); EXPECT_FALSE(payload->shown_matches_desired);
  EXPECT_FALSE(payload->shown_graph_verified);
  fs::copy(payload_fixture(), directory.path() / "view", fs::copy_options::recursive);
  const auto manifest = io::read_json_file(payload_fixture() / "manifest.json");
  const Json receipt = {{"schema", "stk.graph-result/1"}, {"graph_sha256", std::string(64, '1')},
      {"graph_hash", "sha256:" + std::string(64, '1')}, {"profile", "desktop"},
      {"outputs", {{"view", {{"type", "payload"}, {"manifest", manifest}}}}},
      {"parameters", {{"step", {{"value", 13}, {"choices", Json::array()}}}}},
      {"keys", Json::object()}, {"evaluated", Json::array({"historical-node"})},
      {"timings", Json::object()}, {"cache", {{"hits", 2}, {"misses", 1}}},
      {"warnings", Json::array()}, {"files", {{"view", "view/manifest.json"}}}};
  { std::ofstream out(directory.path() / "result.json", std::ios::binary); out << receipt.dump(); ASSERT_TRUE(out.good()); }
  ASSERT_TRUE(viewer.open_path(directory.str())) << viewer.open_error();
  const auto imported = viewer.graph_inspection();
  EXPECT_TRUE(imported->has_payload); EXPECT_FALSE(imported->desired); EXPECT_FALSE(imported->shown_configuration);
  ASSERT_TRUE(imported->shown_result); EXPECT_EQ(imported->shown_result->raw, receipt);
  EXPECT_EQ(imported->shown_resolved_parameters, (Json{{"step", 13}}));
  EXPECT_FALSE(imported->shown_matches_desired); EXPECT_EQ(viewer.evaluations_started(), 0);
  EXPECT_FALSE(imported->shown_graph_verified);
  viewer.close();
  const auto closed = viewer.graph_inspection();
  EXPECT_EQ(closed->source.kind, SourceKind::None); EXPECT_FALSE(closed->has_payload);
  EXPECT_FALSE(closed->desired); EXPECT_FALSE(closed->shown_configuration); EXPECT_FALSE(closed->shown_result);
  EXPECT_TRUE(closed->shown_resolved_parameters.is_null());
  EXPECT_TRUE(imported->has_payload); EXPECT_EQ(imported->shown_result->raw, receipt);
}
}  // namespace
}  // namespace stk::app
