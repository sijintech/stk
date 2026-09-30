/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
using Result = bridge::Result<Json>;
using bridge::ErrorCode;
namespace fs = std::filesystem;

Json capture_presets()
{
  return {{"presets", Json::array({io::read_json_file(fs::path(STK_REPO_ROOT) /
      "suan/graph/presets/muferro-domains.json")})}};
}
Json capture_catalog()
{
  return io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json");
}
std::string test_python()
{
  std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  if (const auto *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
  if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
  return python;
}
const char *capture_bridge();

class ViewerGraphConfigurationTest : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"viewer-configuration"};
  wmtest::AppFixture f{"en"};
  bridge::test::ManualLoop ui_loop;
  std::unique_ptr<bridge::Client> ui_client;
  ViewerState &viewer() { return f.shell->store().viewer(); }

  void settle_ui()
  {
    ASSERT_TRUE(ui_loop.pump_until([&] {
      const auto &scripts = f.shell->store().scripts();
      return scripts.ready() && scripts.desktop_ready() && scripts.status().contains("cursor");
    }, 30)) << ui_client->bridge_log().text();
    ui_loop.run_ready();
  }

  void SetUp() override
  {
    const auto python = test_python();
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for portable desktop requests"; }
    const auto script = dir.path() / "capture.py";
    { std::ofstream file(script, std::ios::binary); file << capture_bridge(); ASSERT_TRUE(file.good()); }
    bridge::ClientOptions options;
    options.command = {python, "-u", core::path_to_utf8(script), STK_REPO_ROOT, dir.str()};
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_BRIDGE_VALIDATE"] = "0";
    options.executor = ui_loop.executor();
    ui_client = bridge::Client::create(options);
    ASSERT_TRUE(ui_client->start());
    ASSERT_TRUE(ui_client->wait_ready(30)) << ui_client->bridge_log().text();
    ui_loop.run_ready();
    f.shell->store().set_bridge(ui_client.get());
    ASSERT_NO_FATAL_FAILURE(settle_ui());
  }

  void TearDown() override
  {
    viewer().clock = {};
    viewer().close(); f.shell->store().set_bridge(nullptr);
    if (ui_client) { ui_client->close(); }
    ui_loop.run_ready();
  }

  Result request(const Json &params, const int64_t deadline = std::numeric_limits<int64_t>::max())
  {
    std::optional<Result> result;
    ui_client->call("fixture.capture", {{"params", params}, {"expires_at_ms", deadline}}).then(
        [&](Result value) { result = std::move(value); });
    EXPECT_TRUE(ui_loop.pump_until([&] { f.screen.run_deferred(); return bool(result); }, 30));
    EXPECT_TRUE(result);
    return result ? std::move(*result) : Result(bridge::Error::make(ErrorCode::Unavailable, "Missing response"));
  }

  void open_run()
  {
    // Prepare the source offline. Opening a run is otherwise an explicit evaluation action.
    f.shell->store().set_bridge(nullptr);
    viewer().prefetch_neighbours = false;
    viewer().set_metadata(capture_presets(), capture_catalog());
    fs::create_directories(dir.path() / "run");
    ASSERT_TRUE(viewer().open_path(core::path_to_utf8(dir.path() / "run"), "muferro-domains"));
    EXPECT_EQ(viewer().evaluations_started(), 0);
    if (ui_client) {
      f.shell->store().set_bridge(ui_client.get());
      ASSERT_NO_FATAL_FAILURE(settle_ui());
    }
  }
};

TEST_F(ViewerGraphConfigurationTest, EmptyAndImportedSourcesReturnNullWithoutInventingDefinitions)
{
  const auto version = f.shell->store().version();
  const auto snapshot = viewer().graph_inspection();
  for (const bool displayed : {false, true}) {
    const auto result = request({{"displayed", displayed}});
    ASSERT_TRUE(result.ok());
    EXPECT_EQ(result.value(), (Json{{"viewer_version", snapshot->version}, {"displayed", displayed},
        {"displayed_graph_verified", nullptr}, {"configuration", nullptr}}));
  }
  EXPECT_EQ(f.shell->store().version(), version);
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  ASSERT_TRUE(viewer().open_path(core::path_to_utf8(fs::path(STK_REPO_ROOT) /
      "desktop/tests/viewer/fixtures/muferro_domains")));
  ASSERT_TRUE(viewer().payload());
  const auto imported = viewer().graph_inspection();
  const auto imported_version = f.shell->store().version();
  for (const bool displayed : {false, true}) {
    const auto result = request({{"displayed", displayed}});
    ASSERT_TRUE(result.ok());
    EXPECT_TRUE(result.value().at("configuration").is_null());
    EXPECT_TRUE(result.value().at("displayed_graph_verified").is_null());
    EXPECT_EQ(result.value().at("viewer_version"), imported->version);
  }
  EXPECT_EQ(viewer().graph_inspection(), imported);
  EXPECT_EQ(f.shell->store().version(), imported_version);
}

TEST_F(ViewerGraphConfigurationTest, ExportsCopiedConfigurationWithoutLayoutOrViewerChanges)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  const auto snapshot = viewer().graph_inspection();
  ASSERT_TRUE(snapshot->desired);
  const auto layout = f.screen.to_json();
  const auto version = f.shell->store().version();
  auto result = request({{"displayed", false}});
  ASSERT_TRUE(result.ok());
  EXPECT_EQ(result.value().size(), 4u);
  const auto &configuration = result.value().at("configuration");
  EXPECT_EQ(configuration.size(), 5u);
  EXPECT_EQ(configuration.at("graph"), snapshot->desired->graph);
  EXPECT_EQ(configuration.at("parameters"), snapshot->desired->parameters);
  EXPECT_EQ(configuration.at("requested_outputs"), snapshot->desired->requested_outputs);
  EXPECT_EQ(configuration.at("preset_id"), "muferro-domains");
  EXPECT_EQ(configuration.at("source"), (Json{{"key", viewer().source().key()}, {"kind", "run"},
      {"path", core::path_to_utf8(dir.path() / "run")}, {"field_file", ""}, {"connection", ""},
      {"node", ""}, {"workspace_id", ""}, {"task_id", ""}, {"series", false}}));
  EXPECT_EQ(result.value().at("viewer_version"), snapshot->version);
  result.value()["configuration"]["graph"]["nodes"][0]["id"] = "changed_copy";
  result.value()["configuration"]["parameters"]["step"] = 17;
  const auto next = request({{"displayed", false}});
  ASSERT_TRUE(next.ok());
  EXPECT_EQ(next.value().at("configuration").at("graph"), snapshot->desired->graph);
  EXPECT_EQ(next.value().at("configuration").at("parameters"), snapshot->desired->parameters);
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  EXPECT_EQ(f.shell->store().version(), version);
  EXPECT_EQ(f.screen.to_json(), layout);
  EXPECT_EQ(viewer().evaluations_started(), 0);
}

TEST_F(ViewerGraphConfigurationTest, ReadDoesNotServiceAnExpiredDebounceOrRefreshMetadata)
{
  double now = 1000;
  viewer().clock = [&] { return now; };
  ASSERT_NO_FATAL_FAILURE(open_run());
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  ASSERT_FALSE(viewer().pending_edit().empty());
  now += 100;
  const auto snapshot = viewer().graph_inspection();
  const auto version = f.shell->store().version();
  const auto error = viewer().eval_error();
  for (int i = 0; i < 3; ++i) {
    const auto result = request({{"displayed", false}});
    ASSERT_TRUE(result.ok());
    EXPECT_EQ(result.value().at("configuration").at("parameters").at("min_magnitude"), 0.75);
  }
  EXPECT_EQ(viewer().pending_edit(), snapshot->pending_edit);
  EXPECT_EQ(viewer().eval_error(), error);
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  EXPECT_EQ(f.shell->store().version(), version);
  EXPECT_EQ(viewer().evaluations_started(), 0);
  viewer().clock = {};
}

TEST_F(ViewerGraphConfigurationTest, TaskSourceExportsItsFullIdentityWithoutConnecting)
{
  f.shell->store().set_bridge(nullptr);
  viewer().set_metadata(capture_presets(), capture_catalog());
  OpenResultRequest source;
  source.connection = "hub:test"; source.node = "node-7";
  source.workspace_id = "workspace-9"; source.task_id = "task-12"; source.preset = "muferro-domains";
  ASSERT_TRUE(viewer().open(source));
  f.shell->store().set_bridge(ui_client.get());
  ASSERT_NO_FATAL_FAILURE(settle_ui());
  const auto snapshot = viewer().graph_inspection();
  const auto version = f.shell->store().version();
  const auto result = request({{"displayed", false}});
  ASSERT_TRUE(result.ok());
  EXPECT_EQ(result.value().at("configuration").at("source"), (Json{{"key", viewer().source().key()},
      {"kind", "task"}, {"path", ""}, {"field_file", ""}, {"connection", "hub:test"},
      {"node", "node-7"}, {"workspace_id", "workspace-9"}, {"task_id", "task-12"}, {"series", false}}));
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  EXPECT_EQ(f.shell->store().version(), version);
  EXPECT_EQ(viewer().evaluations_started(), 0);
  EXPECT_EQ(f.shell->store().bridge(), ui_client.get());
}

TEST_F(ViewerGraphConfigurationTest, StrictBooleanAndExactParameterNamesAreRequired)
{
  const auto snapshot = viewer().graph_inspection();
  const auto version = f.shell->store().version();
  for (const auto &params : {Json(), Json::array(), Json::object(), Json{{"displayed", 0}},
      Json{{"displayed", "false"}}, Json{{"displayed", nullptr}}, Json{{"displayed", false}, {"expected_source", "x"}}}) {
    const auto result = request(params);
    ASSERT_FALSE(result.ok()) << params;
    EXPECT_EQ(result.error().code, ErrorCode::InvalidParams);
  }
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  EXPECT_EQ(f.shell->store().version(), version);
}

TEST_F(ViewerGraphConfigurationTest, ExpiredCancelledAndClosedScreenRequestsCannotExportLaterState)
{
  const auto expired = request({{"displayed", false}}, 0);
  ASSERT_FALSE(expired.ok()); EXPECT_EQ(expired.error().code, ErrorCode::Timeout);
  bool queued = false;
  auto listener = ui_client->on_event("ui.request", [&](const auto &, const auto &) { queued = true; });
  std::optional<Result> closed;
  ui_client->call("fixture.capture", {{"params", {{"displayed", false}}},
      {"expires_at_ms", std::numeric_limits<int64_t>::max()}}).then([&](Result value) { closed = std::move(value); });
  ASSERT_TRUE(ui_loop.pump_until([&] { return queued; }, 30));
  f.shell->forget(f.screen);
  ASSERT_TRUE(ui_loop.pump_until([&] { f.screen.run_deferred(); return bool(closed); }, 30));
  ASSERT_TRUE(closed); ASSERT_FALSE(closed->ok());
  EXPECT_EQ(closed->error().code, ErrorCode::Unavailable);
  const auto absent = request({{"displayed", false}});
  ASSERT_FALSE(absent.ok()); EXPECT_EQ(absent.error().code, ErrorCode::Unavailable);

  f.shell->install(f.screen, nullptr);
  queued = false;
  std::optional<Result> cancelled;
  auto pending = ui_client->call("fixture.capture", {{"params", {{"displayed", false}}},
      {"expires_at_ms", std::numeric_limits<int64_t>::max()}});
  pending.then([&](Result value) { cancelled = std::move(value); });
  ASSERT_TRUE(ui_loop.pump_until([&] { return queued; }, 30));
  const auto snapshot = viewer().graph_inspection();
  f.shell->store().set_bridge(nullptr);
  f.screen.run_deferred(); ui_loop.run_ready();
  EXPECT_FALSE(cancelled); EXPECT_EQ(viewer().graph_inspection(), snapshot);
  pending.cancel(); ui_loop.run_ready();
}

// Synthetic graph receipt and static payload only: this portable fixture uses no NumPy, VTK,
// network or native fake process. The real Python graph hash remains authoritative.
constexpr const char *kCaptureBridge = R"PY(
import json, os, shutil, sys
from pathlib import Path
from suan.graph.schema import graph_hash
root, temporary = map(Path, sys.argv[1:3])
preset = json.loads((root/'suan/graph/presets/muferro-domains.json').read_text(encoding='utf-8'))
fixture = root/'desktop/tests/viewer/fixtures/muferro_domains'
blob_dir = temporary/'blobs'
pending = {}
for line in sys.stdin:
    message = json.loads(line)
    method, params = message['method'], message.get('params', {})
    result = {}
    if method == 'hello':
        result = {'protocol': 1, 'server': {'name': 'capture-fixture', 'version': '1', 'python': sys.version,
            'platform': sys.platform, 'pid': os.getpid()},
            'methods': ['hello', 'graph.evaluate', 'graph.cancel', 'script.open', 'script.read',
                'script.catalog', 'ui.attach', 'ui.reply', 'fixture.capture'], 'events': ['ui.request'],
            'limits': {'max_line_bytes': 16777216, 'max_inflight': 64},
            'paths': {key: str(temporary) for key in ('state_dir','cache_dir','download_dir')}, 'resumed_transfers': []}
        result['paths']['blob_dir'] = str(blob_dir)
    elif method == 'script.open': result = {'session':'script-fixture','state':'ready','output_end':0}
    elif method == 'script.read': result = {'session':'script-fixture','state':'ready','text':'','cursor':0,'output_end':0}
    elif method == 'script.catalog': result = {'ui_operations':['viewer.graph_configuration']}
    elif method == 'ui.attach': result = {'session':'ui-fixture'}
    elif method == 'fixture.capture':
        request = str(message['id'])
        pending[request] = message['id']
        print(json.dumps({'event':'ui.request','data':{'session':'ui-fixture','request':request,
            'operation':'viewer.graph_configuration','params':params['params'],
            'expires_at_ms':params['expires_at_ms']}}), flush=True)
        continue
    elif method == 'ui.reply':
        original = pending.pop(params['request'])
        key = 'result' if 'result' in params else 'error'
        print(json.dumps({'id':original,key:params[key]}), flush=True)
        result = {'accepted':True}
    elif method == 'graph.evaluate':
        manifest = json.loads((fixture/'manifest.json').read_text(encoding='utf-8'))
        for buffer in manifest['buffers']:
            digest = buffer['sha256']; target = blob_dir/digest[:2]/digest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fixture/(digest+'.bin'), target)
            buffer['uri'] = 'sha256:'+digest
        hashed = graph_hash(preset['graph'])
        receipt = {'schema':'stk.graph-result/1','graph_hash':hashed,'graph_sha256':hashed[7:],
            'profile':'desktop','parameters':{'step':{'value':2,'choices':[0,1,2]}},
            'outputs':{params['request']['outputs'][0]:{'type':'payload','manifest':manifest}},
            'keys':{},'evaluated':[node['id'] for node in preset['graph']['nodes']],
            'timings':{},'cache':{'hits':0,'misses':1},'warnings':[]}
        mode = temporary/'receipt-mode'
        if mode.exists() and mode.read_text() == 'mismatch': receipt['graph_sha256'] = '0'*64
        if mode.exists() and mode.read_text() == 'missing': del receipt['graph_hash']
        result = {'result':receipt,'blob_dir':str(blob_dir)}
    elif method == 'graph.cancel': result = {'cancelled': False}
    print(json.dumps({'id':message['id'],'result':result}, ensure_ascii=True), flush=True)
)PY";

const char *capture_bridge() { return kCaptureBridge; }

TEST_F(ViewerGraphConfigurationTest, DisplayedExportRetainsSubmittedIntentAndAllThreeVerificationStates)
{
  ASSERT_NO_FATAL_FAILURE(open_run());
  for (const char *mode : {"matching", "mismatch", "missing"}) {
    SCOPED_TRACE(mode);
    { std::ofstream file(dir.path() / "receipt-mode"); file << mode; }
    viewer().set_parameter("min_magnitude", ui::FormValue::number(0.1));
    viewer().evaluate_now();
    ASSERT_TRUE(ui_loop.pump_until([&] { return !viewer().evaluating() && bool(viewer().payload()); }, 30))
        << viewer().eval_error() << ui_client->bridge_log().text();
    viewer().set_auto_evaluate(false);
    viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
    const auto snapshot = viewer().graph_inspection();
    const auto version = f.shell->store().version();
    const auto evaluations = viewer().evaluations_started();
    const auto sent = ui_client->stats().calls_sent;
    const auto current = request({{"displayed", false}}), displayed = request({{"displayed", true}});
    ASSERT_TRUE(current.ok()); ASSERT_TRUE(displayed.ok());
    EXPECT_EQ(current.value().at("configuration").at("parameters").at("min_magnitude"), 0.75);
    EXPECT_EQ(displayed.value().at("configuration").at("parameters").at("min_magnitude"), 0.1);
    EXPECT_EQ(displayed.value().at("configuration").at("parameters").at("step"), "latest");
    const Json verified = std::string(mode) == "missing" ? Json() : Json(std::string(mode) == "matching");
    EXPECT_EQ(current.value().at("displayed_graph_verified"), verified);
    EXPECT_EQ(displayed.value().at("displayed_graph_verified"), verified);
    EXPECT_EQ(current.value().at("viewer_version"), displayed.value().at("viewer_version"));
    EXPECT_EQ(displayed.value().size(), 4u); EXPECT_EQ(displayed.value().at("configuration").size(), 5u);
    EXPECT_EQ(viewer().graph_inspection(), snapshot); EXPECT_EQ(f.shell->store().version(), version);
    EXPECT_EQ(viewer().evaluations_started(), evaluations);
    EXPECT_EQ(ui_client->stats().calls_sent, sent + 4); // Two fixture requests and their UI replies.
  }
}

class ViewerGraphConfigurationPython : public ViewerGraphConfigurationTest {
 protected:
  bridge::test::ManualLoop loop;
  std::unique_ptr<bridge::Client> client;
  ScriptState &scripts() { return f.shell->store().scripts(); }
  bool pump(const std::function<bool()> &until)
  {
    return loop.pump_until([&] { f.screen.run_deferred(); return until(); }, 30);
  }
  void SetUp() override
  {
    const auto python = test_python();
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for desktop graph export"; }
    ASSERT_NO_FATAL_FAILURE(open_run());
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)) << client->bridge_log().text();
    loop.run_ready(); f.shell->store().set_bridge(client.get());
    ASSERT_TRUE(pump([&] { return scripts().ready() && scripts().desktop_ready() && scripts().status().contains("cursor"); }))
        << scripts().error() << client->bridge_log().text();
  }
  void TearDown() override
  {
    viewer().clock = {};
    viewer().close(); f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(ViewerGraphConfigurationPython, NegotiatedFacadeExportsWithoutPumpingOrExecutingGraphWork)
{
  double now = 1000;
  viewer().clock = [&] { return now; };
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  now += 100;
  const auto snapshot = viewer().graph_inspection();
  const auto layout = f.screen.to_json();
  ASSERT_TRUE(snapshot->desired);
  const auto &config = *snapshot->desired;
  const auto &source = config.source;
  const Json expected = {{"viewer_version", snapshot->version}, {"displayed", false},
      {"displayed_graph_verified", nullptr}, {"configuration", {
        {"source", {{"key", source.key()}, {"kind", source_kind_name(source.kind)}, {"path", source.path},
          {"field_file", source.field_file}, {"connection", source.connection}, {"node", source.node},
          {"workspace_id", source.workspace_id}, {"task_id", source.task_id}, {"series", source.series}}},
        {"preset_id", config.preset_id}, {"graph", config.graph}, {"parameters", config.parameters},
        {"requested_outputs", config.requested_outputs}}}};
  const auto code = "import json\n"
      "expected = json.loads(" + Json(expected.dump()).dump() + ")\n"
      "captured = stk.viewer.graph_configuration()\n"
      "assert captured == expected, captured\n"
      "assert stk.viewer.graph_configuration(displayed=True)['configuration'] is None\n"
      "assert 'evaluation' not in captured and 'result' not in captured\n"
      "captured['configuration']['graph']['nodes'][0]['id'] = 'local_copy'\n"
      "assert stk.viewer.graph_configuration() == expected\n"
      "try:\n"
      "    stk.viewer.graph_configuration(displayed=1)\n"
      "except (TypeError, ValueError):\n"
      "    pass\n"
      "else:\n"
      "    raise AssertionError('displayed must be boolean')\n";
  ASSERT_TRUE(scripts().execute(code));
  ASSERT_TRUE(pump([&] { return !scripts().busy(); })) << client->bridge_log().text();
  ASSERT_TRUE(scripts().error().empty()) << scripts().error();
  EXPECT_EQ(scripts().status().at("run").at("state"), "succeeded");
  EXPECT_EQ(viewer().graph_inspection(), snapshot);
  EXPECT_EQ(viewer().evaluations_started(), 0);
  EXPECT_EQ(viewer().pending_edit(), snapshot->pending_edit);
  EXPECT_EQ(f.screen.to_json(), layout);
  viewer().clock = {};
}

}  // namespace
}  // namespace stk::app
