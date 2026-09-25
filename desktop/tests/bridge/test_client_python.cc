/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk::bridge::Client against the real Python bridge (python -m suan.desktop_bridge --stdio
 * --strict, every message also validated by the client against the schema).
 *
 * The interpreter: $STK_BRIDGE_TEST_PYTHON, else the CMake setting STK_BRIDGE_TEST_PYTHON, else
 * python3 on PATH; the tests skip (with the reason) when it cannot import suan.desktop_bridge.
 * Runtime tests start a loopback Runtime (127.0.0.1, ephemeral port) in a helper process
 * (bridge_fixture.py runtime) and stop it afterwards.
 */

#include <gtest/gtest.h>

#include <atomic>
#include <fstream>
#include <mutex>
#include <set>

#include "stk/bridge/client.hh"
#include "stk/bridge/process.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/payload.hh"
#include "support.hh"

namespace stk::bridge {
namespace {

using test::ManualLoop;
using test::TempDir;
using test::wait_until;

std::string repo_root()
{
  return STK_REPO_ROOT;
}

std::string fixture_script()
{
  return repo_root() + "/desktop/tests/bridge/bridge_fixture.py";
}

/** The interpreter, or "" with `reason` when the Python bridge cannot run here. */
std::string test_python(std::string &reason)
{
  static std::string cached, cached_reason;
  static bool probed = false;
  if (probed) {
    reason = cached_reason;
    return cached;
  }
  probed = true;
  std::string python;
  if (const char *env = getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) {
    python = env;
  }
  else if (std::string(STK_BRIDGE_TEST_PYTHON_DEFAULT).size() > 0) {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  }
  else if (auto found = find_executable("python3")) {
    python = *found;
  }
  if (python.empty() || !find_executable(python)) {
    cached_reason = "no Python interpreter (set STK_BRIDGE_TEST_PYTHON)";
    reason = cached_reason;
    return "";
  }
  SpawnOptions options;
  options.argv = {python, fixture_script(), "check"};
  options.env["PYTHONPATH"] = repo_root();
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  if (!child) {
    cached_reason = "cannot run " + python + ": " + error;
    reason = cached_reason;
    return "";
  }
  child->close_stdin();
  std::string out;
  char buffer[1024];
  std::ptrdiff_t n;
  while ((n = child->read(ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
    out.append(buffer, size_t(n));
  }
  const auto status = child->wait(60);
  if (!status || !status->success()) {
    cached_reason = python + " cannot run the bridge: " + out;
    reason = cached_reason;
    return "";
  }
  cached = python;
  return cached;
}

class PythonBridge : public ::testing::Test {
 protected:
  void SetUp() override
  {
    std::string reason;
    python_ = test_python(reason);
    if (python_.empty()) {
      GTEST_SKIP() << reason;
    }
  }

  void TearDown() override
  {
    if (python_.empty()) {
      return;
    }
    for (long pgid : groups_) {
      EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 15))
          << "bridge process group " << pgid << " still alive";
    }
    /* No bridge (or helper) of this test is left: their command lines name its directory. */
    EXPECT_TRUE(wait_until([&] { return test::processes_matching(dir_.str()).empty(); }, 15))
        << test::processes_matching(dir_.str()).size() << " stray process(es) under " << dir_.str();
  }

  ClientOptions options(Executor executor = {})
  {
    ClientOptions o;
    o.python.configured = python_;
    o.state_dir = dir_.str() + "/state";
    o.cache_dir = dir_.str() + "/cache";
    o.strict = true;
    o.validate = true;
    o.executor = std::move(executor);
    o.env["PYTHONPATH"] = repo_root();
    o.env["STK_PROFILES_FILE"] = dir_.str() + "/profiles/connections.json";
    o.env["STK_STATE_DIR"] = dir_.str() + "/no-local-runtime";
    o.env["STK_DESKTOP_BRIDGE_DIR"] = std::nullopt;
    o.env["STK_RUNTIME_URL"] = std::nullopt;
    o.env["STK_RUNTIME_TOKEN"] = std::nullopt;
    o.env["MPLCONFIGDIR"] = dir_.str() + "/mpl";
    o.env["STK_GRAPH_CACHE"] = dir_.str() + "/graph-cache";
    o.restart.initial_backoff_s = 0.1;
    o.call_timeout_s = 240;
    o.hello_timeout_s = 120;
    return o;
  }

  std::unique_ptr<Client> started(ClientOptions opts)
  {
    auto client = Client::create(std::move(opts));
    std::string error;
    EXPECT_TRUE(client->start(&error)) << error;
    EXPECT_TRUE(client->wait_ready(120)) << (client->last_error() ? client->last_error()->describe() : "")
                                         << "\n" << client->bridge_log().text();
    track(*client);
    return client;
  }

  void track(Client &client)
  {
    if (const int64_t pid = client.bridge_pid()) {
      groups_.insert(long(pid));
    }
  }

  /** Why `bridge_fixture.py check <what>` fails here ("" when that part can run). */
  std::string unavailable(const std::string &what)
  {
    SpawnOptions spawn;
    spawn.argv = {python_, fixture_script(), "check", what};
    spawn.env["PYTHONPATH"] = repo_root();
    spawn.env["MPLCONFIGDIR"] = dir_.str() + "/mpl";
    std::string error;
    auto child = ChildProcess::spawn(spawn, error);
    if (!child) {
      return error;
    }
    child->close_stdin();
    std::string out;
    char buffer[1024];
    std::ptrdiff_t n;
    while ((n = child->read(ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
      out.append(buffer, size_t(n));
    }
    const auto status = child->wait(120);
    return status && status->success() ? std::string() : "needs " + what + ": " + out;
  }

  /** Runs bridge_fixture.py with `args` to completion; its stdout. */
  std::string run_fixture(const std::vector<std::string> &args)
  {
    SpawnOptions spawn;
    spawn.argv = {python_, fixture_script()};
    spawn.argv.insert(spawn.argv.end(), args.begin(), args.end());
    spawn.env["PYTHONPATH"] = repo_root();
    spawn.env["MPLCONFIGDIR"] = dir_.str() + "/mpl";
    std::string error;
    auto child = ChildProcess::spawn(spawn, error);
    EXPECT_TRUE(child) << error;
    if (!child) {
      return {};
    }
    child->close_stdin();
    std::string out;
    char buffer[4096];
    std::ptrdiff_t n;
    while ((n = child->read(ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
      out.append(buffer, size_t(n));
    }
    const auto status = child->wait(120);
    EXPECT_TRUE(status && status->success()) << "bridge_fixture.py failed";
    return out;
  }

  /** A loopback Runtime with a slowly logging task (bridge_fixture.py runtime). */
  struct RuntimeFixture {
    std::unique_ptr<ChildProcess> process;
    std::thread drain;
    Json info;
    ~RuntimeFixture()
    {
      stop();
    }
    void open_gate() const
    {
      std::ofstream(info["gate"].get<std::string>()) << "go\n";
    }
    void stop()
    {
      if (!process) {
        return;
      }
      process->close_stdin(); /* EOF: cancel tasks, stop the server */
      if (!process->wait(30)) {
        process->kill();
        process->wait(-1);
      }
      process->abort_reads();
      if (drain.joinable()) {
        drain.join();
      }
      process.reset();
    }
  };

  /** Starts the Runtime fixture; "" or why it could not start (the test then skips). */
  std::string start_runtime(RuntimeFixture &fixture)
  {
    SpawnOptions spawn;
    spawn.argv = {python_, fixture_script(), "runtime", dir_.str() + "/runtime"};
    spawn.env["PYTHONPATH"] = repo_root();
    std::string error;
    fixture.process = ChildProcess::spawn(spawn, error);
    if (!fixture.process) {
      return error;
    }
    ChildProcess *process = fixture.process.get();
    auto stderr_text = std::make_shared<std::string>();
    auto stderr_mutex = std::make_shared<std::mutex>();
    fixture.drain = std::thread([process, stderr_text, stderr_mutex] {
      char buffer[4096];
      std::ptrdiff_t n;
      while ((n = process->read(ChildProcess::Stream::Stderr, buffer, sizeof(buffer))) > 0) {
        std::lock_guard lock(*stderr_mutex);
        stderr_text->append(buffer, size_t(n));
      }
    });
    std::string line;
    char c;
    while (process->read(ChildProcess::Stream::Stdout, &c, 1) == 1 && c != '\n') {
      line += c;
    }
    if (line.empty()) {
      process->wait(30);
      fixture.stop();
      std::lock_guard lock(*stderr_mutex);
      const size_t keep = std::min<size_t>(stderr_text->size(), 1500);
      return "the Runtime fixture did not start: " + stderr_text->substr(stderr_text->size() - keep);
    }
    fixture.info = io::parse_json(line);
    return {};
  }

  std::string add_runtime(Client &client, const RuntimeFixture &fixture)
  {
    AddRuntimeParams params;
    params.name = "rt";
    params.url = fixture.info["url"].get<std::string>();
    params.token_file = fixture.info["token_file"].get<std::string>();
    const Result<ConnectionInfo> added = client.connections_add_runtime(params).get();
    EXPECT_TRUE(added.ok()) << (added.ok() ? "" : added.error().describe());
    return added.ok() ? added.value().id : std::string();
  }

  std::string python_;
  TempDir dir_{"py"};
  std::set<long> groups_;
};

TEST_F(PythonBridge, HelloListsTheProtocol)
{
  auto client = started(options());
  const auto hello = client->hello_info();
  ASSERT_TRUE(hello);
  EXPECT_EQ(hello->protocol, 1);
  EXPECT_EQ(hello->server.name, "stk-desktop-bridge");
  EXPECT_EQ(hello->server.pid, client->bridge_pid());
  for (const char *method : {"hello", "graph.evaluate", "logs.subscribe", "hub.policy", "colormaps.list"}) {
    EXPECT_TRUE(hello->has_method(method)) << method;
  }
  EXPECT_EQ(hello->limits.max_line_bytes, 16 * 1024 * 1024);
  EXPECT_EQ(hello->paths.state_dir, dir_.str() + "/state");
  const Result<std::vector<ConnectionInfo>> connections = client->connections_list().get();
  ASSERT_TRUE(connections.ok()) << connections.error().describe();
  /* Only the local Runtime, always listed; here not initialized. */
  ASSERT_EQ(connections.value().size(), 1u);
  EXPECT_EQ(connections.value()[0].id, "local");
  EXPECT_EQ(connections.value()[0].state, "not_initialized");
  EXPECT_TRUE(connections.value()[0].url.empty());
  const Result<Json> unknown = client->call("no.such.method").get();
  ASSERT_FALSE(unknown.ok());
  EXPECT_EQ(unknown.error().code, ErrorCode::UnknownMethod);
  EXPECT_FALSE(unknown.error().local);
  const Result<Json> invalid = client->call("task.get", {{"connection", "local"}}, {}).get();
  EXPECT_EQ(invalid.error().code, ErrorCode::InvalidParams); /* caught locally by the schema */
  const Result<Json> not_found = client->task_get({"runtime:nope", ""}, "a").get();
  ASSERT_FALSE(not_found.ok());
  EXPECT_EQ(not_found.error().code, ErrorCode::NotFound);
  const Result<HubPolicy> policy = client->hub_policy("hub:nope").get(); /* WP11 method, typed */
  ASSERT_FALSE(policy.ok());
  EXPECT_EQ(policy.error().code, ErrorCode::NotFound) << policy.error().describe();
  const Result<CancelResult> cancel = client->graph_cancel("never-started").get();
  ASSERT_TRUE(cancel.ok()) << cancel.error().describe();
  EXPECT_EQ(client->stats().schema_violations, 0u);
  EXPECT_EQ(client->stats().protocol_errors, 0u);
  client->close();
  EXPECT_NE(client->bridge_log().text().find("exit code 0"), std::string::npos);
}

TEST_F(PythonBridge, ASecondBridgeOnTheSameStateDirFailsWithoutRestarting)
{
  auto first = started(options());
  auto second = Client::create(options());
  ASSERT_TRUE(second->start());
  EXPECT_FALSE(second->wait_ready(120));
  EXPECT_EQ(second->state(), BridgeState::Failed);
  ASSERT_TRUE(second->last_error());
  EXPECT_EQ(second->last_error()->code, ErrorCode::Busy);
  EXPECT_FALSE(second->last_error()->retryable);
  EXPECT_EQ(second->last_error()->data["state_dir"], dir_.str() + "/state");
  std::this_thread::sleep_for(std::chrono::milliseconds(500));
  EXPECT_EQ(second->stats().spawned, 1u); /* no restart loop */
  EXPECT_NE(second->bridge_log().text().find("exit code 3"), std::string::npos);
  EXPECT_EQ(first->state(), BridgeState::Ready);
  EXPECT_TRUE(first->connections_list().get().ok());
  second->close();
  first->close();
}

TEST_F(PythonBridge, ColormapsList)
{
  auto client = started(options());
  const Result<ColormapList> maps = client->colormaps_list().get();
  ASSERT_TRUE(maps.ok()) << maps.error().describe();
  ASSERT_FALSE(maps.value().colormaps.empty());
  bool viridis = false;
  for (const Colormap &map : maps.value().colormaps) {
    viridis |= map.name == "viridis";
    EXPECT_EQ(map.lut_rgba8[3], 255) << map.name; /* opaque first entry */
  }
  EXPECT_TRUE(viridis);
  EXPECT_TRUE(maps.value().aliases.is_object());
}

TEST_F(PythonBridge, GraphPresets)
{
  auto client = started(options());
  const Result<Json> presets = client->graph_presets().get();
  ASSERT_TRUE(presets.ok()) << presets.error().describe();
  std::set<std::string> ids;
  for (const Json &preset : presets.value()["presets"]) {
    ids.insert(preset["id"].get<std::string>());
  }
  EXPECT_TRUE(ids.count("muferro-domains"));
  const Result<Json> catalog = client->graph_catalog().get();
  ASSERT_TRUE(catalog.ok());
  EXPECT_EQ(catalog.value()["catalog"]["schema"], "stk.catalog/1");
}

TEST_F(PythonBridge, LocalGraphEvaluateOnAFakeMuferroRun)
{
  if (const std::string why = unavailable("graph"); !why.empty()) {
    GTEST_SKIP() << why;
  }
  const std::string run = dir_.str() + "/run";
  run_fixture({"write-run", run});
  ManualLoop loop;
  auto client = started(options(loop.executor()));
  EvaluateParams params;
  params.eval_id = "eval-1";
  params.request = {{"preset", "muferro-domains"},
                    {"outputs", {"view", "fractions"}},
                    {"parameters", {{"step", "latest"}}}};
  params.local_bindings = {{"run", run}};
  std::vector<std::string> progress;
  std::optional<Result<EvaluateResult>> done;
  client->graph_evaluate(params, [&](const GraphProgress &p) {
    EXPECT_EQ(p.eval_id, "eval-1");
    progress.push_back(io::get_string(p.event, "type"));
  }).then([&](Result<EvaluateResult> r) { done = std::move(r); });
  ASSERT_TRUE(loop.pump_until([&] { return done.has_value(); }, 300));
  ASSERT_TRUE(done->ok()) << done->error().describe() << "\n" << client->bridge_log().text();
  const EvaluateResult &evaluated = done->value();
  EXPECT_FALSE(progress.empty());
  EXPECT_NE(std::find(progress.begin(), progress.end(), "node.finished"), progress.end());
  const io::GraphResult result = evaluated.graph_result();
  EXPECT_EQ(result.schema, "stk.graph-result/1");
  const io::ResultOutput *view = result.output("view");
  ASSERT_NE(view, nullptr);
  ASSERT_NE(view->manifest(), nullptr);
  /* The payload's buffers are in the content-addressed cache and decode with stk::io. */
  const io::BlobCache cache(evaluated.blob_dir);
  const io::Payload payload = io::decode_manifest(*view->manifest(), cache.provider(true));
  EXPECT_EQ(payload.manifest["schema"], "stk.payload/2");
  std::vector<std::string> blobs = view->blobs();
  ASSERT_FALSE(blobs.empty());
  const Result<BlobEnsureResult> ensured = client->blob_ensure(blobs).get();
  ASSERT_TRUE(ensured.ok()) << ensured.error().describe();
  EXPECT_TRUE(ensured.value().missing.empty());
  EXPECT_EQ(ensured.value().blobs.size(), std::set<std::string>(blobs.begin(), blobs.end()).size());
  /* A bad preset is a graph_error with the stk-graph code. */
  EvaluateParams bad = params;
  bad.eval_id = "eval-2";
  bad.request = {{"preset", "no-such"}};
  const Result<EvaluateResult> error = client->graph_evaluate(bad).get();
  ASSERT_FALSE(error.ok());
  EXPECT_EQ(error.error().code, ErrorCode::GraphError);
  EXPECT_EQ(error.error().data["graph_code"], "unknown_preset");
}

#if defined(__linux__)

TEST_F(PythonBridge, LogsSubscribeAgainstALoopbackRuntime)
{
  if (const std::string why = unavailable("runtime"); !why.empty()) {
    GTEST_SKIP() << why;
  }
  RuntimeFixture runtime;
  if (const std::string why = start_runtime(runtime); !why.empty()) {
    GTEST_SKIP() << why;
  }
  ManualLoop loop;
  auto client = started(options(loop.executor()));
  const std::string connection = add_runtime(*client, runtime);
  ASSERT_EQ(connection, "runtime:rt");
  const Result<ConnectionCheck> check = client->connections_check(connection).get();
  ASSERT_TRUE(check.ok());
  EXPECT_TRUE(check.value().ok);
  std::string text;
  bool ended = false;
  LogsParams params;
  params.target = {connection, ""};
  params.task_id = runtime.info["task_id"].get<std::string>();
  params.streams = {"stdout"};
  params.chunk_bytes = 64;
  LogsHandlers handlers;
  bool bytes_ok = true;
  handlers.on_chunk = [&](const LogChunk &c) {
    text += c.text;
    bytes_ok &= c.bytes == c.next_offset - c.offset && c.exact();
  };
  handlers.on_end = [&](const LogsEnd &) { ended = true; };
  Subscription sub = client->subscribe_logs(params, handlers);
  runtime.open_gate(); /* the task starts writing only now: the stream is live, never replayed whole */
  ASSERT_TRUE(loop.pump_until([&] { return ended; }, 120)) << client->bridge_log().text();
  EXPECT_EQ(text, runtime.info["expected_stdout"].get<std::string>());
  EXPECT_TRUE(bytes_ok);
  /* A keyed upload is started once: the repeat (as after a bridge restart) names the same transfer. */
  const std::string upload_source = dir_.str() + "/上传.txt";
  std::ofstream(upload_source) << "数据\n";
  UploadParams upload;
  upload.target = {connection, ""};
  upload.workspace_id = runtime.info["workspace_id"].get<std::string>();
  upload.source = upload_source;
  upload.idempotency_key = "stk-bridge-upload-1";
  const Result<Transfer> first_upload = client->upload_start(upload).get();
  ASSERT_TRUE(first_upload.ok()) << first_upload.error().describe();
  const Result<Transfer> second_upload = client->upload_start(upload).get();
  ASSERT_TRUE(second_upload.ok()) << second_upload.error().describe();
  EXPECT_EQ(second_upload.value().id, first_upload.value().id);
  upload.remote = "elsewhere.txt";
  const Result<Transfer> conflicting = client->upload_start(upload).get();
  ASSERT_FALSE(conflicting.ok());
  EXPECT_EQ(conflicting.error().code, ErrorCode::Conflict);
  /* The token went into the bridge only. */
  std::ifstream token_file(runtime.info["token_file"].get<std::string>());
  std::string token;
  std::getline(token_file, token);
  ASSERT_FALSE(token.empty());
  EXPECT_EQ(client->bridge_log().text().find(token), std::string::npos);
  client->close();
  runtime.stop();
}

/* The WP8 acceptance: kill -9 the bridge in the middle of a log subscription; the client restarts
 * it and the subscription continues from its last offset with no duplicate or missing byte. */
TEST_F(PythonBridge, Kill9MidSubscriptionResumesWithoutGapsOrDuplicates)
{
  if (const std::string why = unavailable("runtime"); !why.empty()) {
    GTEST_SKIP() << why;
  }
  RuntimeFixture runtime;
  if (const std::string why = start_runtime(runtime); !why.empty()) {
    GTEST_SKIP() << why;
  }
  ManualLoop loop;
  auto client = started(options(loop.executor()));
  const std::string connection = add_runtime(*client, runtime);
  ASSERT_FALSE(connection.empty());
  std::vector<LogChunk> chunks;
  std::string text;
  bool ended = false;
  std::vector<BridgeState> states;
  ListenerHandle state_listener = client->on_state([&](BridgeState s, const std::optional<Error> &) {
    states.push_back(s);
  });
  LogsParams params;
  params.target = {connection, ""};
  params.task_id = runtime.info["task_id"].get<std::string>();
  params.streams = {"stdout"};
  params.chunk_bytes = 16; /* small reads: characters are split across them */
  LogsHandlers handlers;
  handlers.on_chunk = [&](const LogChunk &c) {
    chunks.push_back(c);
    text += c.text;
  };
  handlers.on_end = [&](const LogsEnd &) { ended = true; };
  Subscription sub = client->subscribe_logs(params, handlers);
  runtime.open_gate(); /* the task starts writing only now: the stream is live, never replayed whole */
  /* Also a watch: it is re-subscribed and snapshots continue after the restart. */
  int snapshots = 0;
  WatchParams watch_params;
  watch_params.target = {connection, ""};
  watch_params.interval = 0.5;
  Subscription watch = client->watch(watch_params, {[&](const WatchSnapshot &) { snapshots++; }, nullptr});

  const std::string expected = runtime.info["expected_stdout"].get<std::string>();
  /* Kill as soon as the first chunk arrived: the task keeps writing for seconds after that. */
  ASSERT_TRUE(loop.pump_until([&] { return !chunks.empty(); }, 120)) << client->bridge_log().text();
  ASSERT_LT(text.size(), expected.size()) << "the log stream finished before the kill";
  const int64_t first_pid = client->bridge_pid();
  const size_t before_kill = chunks.size();
  test::kill_hard(first_pid);
  ASSERT_TRUE(loop.pump_until([&] { return ended; }, 180)) << client->bridge_log().text();
  track(*client);

  EXPECT_EQ(text, expected);
  int64_t position = 0;
  for (const LogChunk &c : chunks) {
    EXPECT_EQ(c.offset, position) << "gap or overlap in the replayed stream";
    position = c.next_offset;
  }
  EXPECT_GT(chunks.size(), before_kill);
  EXPECT_EQ(sub.subscribe_count(), 2);
  EXPECT_EQ(watch.subscribe_count(), 2);
  EXPECT_TRUE(watch.active());
  EXPECT_GE(snapshots, 2);
  EXPECT_EQ(client->stats().restarts, 1u);
  EXPECT_NE(client->bridge_pid(), first_pid);
  EXPECT_FALSE(test::process_alive(first_pid));
  EXPECT_NE(std::find(states.begin(), states.end(), BridgeState::Restarting), states.end());
  EXPECT_EQ(states.back(), BridgeState::Ready);
  EXPECT_EQ(client->stats().schema_violations, 0u);
  watch.unsubscribe();
  client->close();
  runtime.stop();
}

#endif

}  // namespace
}  // namespace stk::bridge
