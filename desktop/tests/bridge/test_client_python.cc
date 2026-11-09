/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk::bridge::Client against the real Python bridge (python -m suan.desktop_bridge --stdio
 * --strict, every message also validated by the client against the schema).
 *
 * The interpreter: $STK_BRIDGE_TEST_PYTHON, else the CMake setting STK_BRIDGE_TEST_PYTHON, else
 * python3 on PATH; the tests skip (with the reason) when it cannot import suan.desktop_bridge.
 * Runtime tests start a loopback Runtime (127.0.0.1, ephemeral port) in a helper process
 * (bridge_fixture.py runtime) and stop it afterwards; the Hub test likewise starts a loopback Hub,
 * node agent and Runtime (bridge_fixture.py hub) that it drives over the helper's stdin.
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

#if defined(__linux__)
#  include <arpa/inet.h>
#  include <fcntl.h>
#  include <netinet/in.h>
#  include <sys/socket.h>
#  include <unistd.h>
#endif

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

  /** A loopback Runtime with a slowly logging task (bridge_fixture.py runtime), or the loopback
   * Hub chain (bridge_fixture.py hub). */
  struct RuntimeFixture {
    std::unique_ptr<ChildProcess> process;
    std::thread drain;
    Json info;
    std::shared_ptr<std::string> stderr_text = std::make_shared<std::string>();
    std::shared_ptr<std::mutex> stderr_mutex = std::make_shared<std::mutex>();
    ~RuntimeFixture()
    {
      stop();
    }
    void open_gate() const
    {
      std::ofstream(info["gate"].get<std::string>()) << "go\n";
    }
    /** The hub fixture: one stdin command, its one-line JSON reply (null when the helper ended). */
    Json command(const std::string &name) const
    {
      if (!process->write_stdin(name + "\n")) {
        return nullptr;
      }
      std::string line;
      char c;
      while (process->read(ChildProcess::Stream::Stdout, &c, 1) == 1 && c != '\n') {
        line += c;
      }
      return line.empty() ? Json(nullptr) : io::parse_json(line);
    }
    std::string stderr_tail(size_t keep = 1500) const
    {
      std::lock_guard lock(*stderr_mutex);
      return stderr_text->substr(stderr_text->size() - std::min(keep, stderr_text->size()));
    }
    /** The hub fixture's checked close (EOF on stdin): "" when it printed {"closed": true} with
     * every part stopped and exited 0 within 60 s, else why. #stop stays the unchecked teardown. */
    std::string close_checked()
    {
      if (!process) {
        return "the helper was not running";
      }
      process->close_stdin();
      std::optional<ExitStatus> status = process->wait(60);
      std::string why;
      if (!status) {
        process->kill();
        process->wait(-1);
        why = "did not exit within 60 s (killed)";
      }
      else if (!status->success()) {
        why = "exited " + status->describe();
      }
      std::string rest;
      char buffer[4096];
      std::ptrdiff_t n;
      while ((n = process->read(ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
        rest.append(buffer, size_t(n));
      }
      process->abort_reads();
      if (drain.joinable()) {
        drain.join();
      }
      process.reset();
      Json closed;
      if (const size_t at = rest.rfind("{\"closed\""); at != std::string::npos) {
        closed = io::parse_json(rest.substr(at, rest.find('\n', at) - at));
      }
      bool all_stopped = closed.is_object() && closed.value("closed", false) && closed["stopped"].is_object() &&
                         !closed["stopped"].empty();
      if (all_stopped) {
        for (const auto &[part, stopped] : closed["stopped"].items()) {
          all_stopped &= stopped.is_boolean() && stopped.get<bool>();
        }
      }
      if (why.empty() && !all_stopped) {
        why = "no complete {\"closed\": true} report";
      }
      return why.empty() ? why : why + "; stdout tail: " + rest.substr(rest.size() - std::min<size_t>(rest.size(), 500)) +
                                     "; stderr tail: " + stderr_tail();
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

  /** Starts the `mode` (runtime | hub) fixture; "" or why it could not start (the test then skips). */
  std::string start_runtime(RuntimeFixture &fixture, const std::string &mode = "runtime",
                            const std::map<std::string, std::optional<std::string>> &extra_env = {})
  {
    SpawnOptions spawn;
    spawn.argv = {python_, fixture_script(), mode, dir_.str() + "/" + mode};
    spawn.env["PYTHONPATH"] = repo_root();
    if (mode == "hub") { /* as tests/test_runtime_hub_cli.py: no shared profile or local Runtime */
      spawn.env["STK_PROFILES_FILE"] = dir_.str() + "/hub-profiles.json";
      spawn.env["STK_STATE_DIR"] = dir_.str() + "/hub-no-local-runtime";
      spawn.env["MPLCONFIGDIR"] = dir_.str() + "/mpl";
    }
    for (const auto &[name, value] : extra_env) {
      spawn.env[name] = value;
    }
    std::string error;
    fixture.process = ChildProcess::spawn(spawn, error);
    if (!fixture.process) {
      return error;
    }
    ChildProcess *process = fixture.process.get();
    auto stderr_text = fixture.stderr_text;
    auto stderr_mutex = fixture.stderr_mutex;
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
      return "the " + mode + " fixture did not start: " + stderr_text->substr(stderr_text->size() - keep);
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
  for (const char *method : {"hello", "graph.evaluate", "logs.subscribe", "hub.policy", "colormaps.list", "connections.ssh"}) {
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
  /* require_live passes the local schema and the strict bridge; the direct read maps the same way. */
  const Result<Json> live_not_found = client->task_get({"runtime:nope", ""}, "a", true).get();
  ASSERT_FALSE(live_not_found.ok());
  EXPECT_EQ(live_not_found.error().code, ErrorCode::NotFound) << live_not_found.error().describe();
  EXPECT_FALSE(live_not_found.error().local);
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

TEST_F(PythonBridge, ManagedSSHProfileRoundTripDoesNotConnectImplicitly)
{
  auto client = started(options());
  AddRuntimeParams params;
  params.name = "ssh-cluster";
  params.url = "http://127.0.0.1:8765";
  params.token = "private-ssh-profile-test";
  params.ssh_host = "test-cluster";
  params.check = false;
  const auto added = client->connections_add_runtime(params).get();
  ASSERT_TRUE(added.ok()) << added.error().describe();
  EXPECT_EQ(added.value().id, "runtime:ssh-cluster");
  EXPECT_EQ(added.value().raw["ssh"]["state"], "stopped");
  EXPECT_EQ(added.value().raw["ssh"]["host"], "test-cluster");
  EXPECT_FALSE(added.value().raw.contains("token"));
  const auto status = client->connections_ssh(added.value().id, "status").get();
  ASSERT_TRUE(status.ok()) << status.error().describe();
  EXPECT_EQ(status.value()["ssh"]["state"], "stopped");
  const auto stopped = client->connections_ssh(added.value().id, "disconnect").get();
  ASSERT_TRUE(stopped.ok()) << stopped.error().describe();
  EXPECT_EQ(stopped.value()["ssh"]["state"], "stopped");
  EXPECT_TRUE(client->connections_remove(added.value().id).get().ok());
  const auto missing = client->connections_ssh(added.value().id, "status").get();
  ASSERT_FALSE(missing.ok());
  EXPECT_EQ(missing.error().code, ErrorCode::NotFound);
}

TEST_F(PythonBridge, ProjectLifecycleAndRevisionedEdits)
{
  auto client = started(options());
  ASSERT_TRUE(client->hello_info()->has_method("project.create"));
  const auto created = client->project_create(dir_.str() + "/project", "Parameter scan").get();
  ASSERT_TRUE(created.ok()) << created.error().describe();
  const ProjectInfo project = created.value();
  EXPECT_EQ(project.revision, 0);
  EXPECT_EQ(project.format_version, 15);
  EXPECT_EQ(project.name, "Parameter scan");
  const auto opened = client->project_open(project.directory).get();
  ASSERT_TRUE(opened.ok());
  EXPECT_EQ(opened.value().handle, project.handle);
  ASSERT_TRUE(client->hello_info()->has_method("project.preview"));
  const auto proposal = client->project_preview(
      project.handle, 0, Json::array({{{"op", "create_table"}, {"name", "Cases"}}})).get();
  ASSERT_TRUE(proposal.ok()) << proposal.error().describe();
  EXPECT_EQ(proposal.value()["persisted"], false);
  EXPECT_EQ(proposal.value()["base_revision"], 0);
  const auto unchanged = client->project_snapshot(project.handle).get();
  ASSERT_TRUE(unchanged.ok());
  EXPECT_TRUE(unchanged.value()["tables"].empty());
  EXPECT_EQ(unchanged.value()["project"]["revision"], 0);
  const auto edited = client->project_apply(project.handle, 0, proposal.value()["commands"]).get();
  ASSERT_TRUE(edited.ok()) << edited.error().describe();
  EXPECT_EQ(edited.value()["revision"], 1);
  const auto conflict = client->project_apply(
      project.handle, 0, Json::array({{{"op", "create_table"}, {"name", "Stale"}}})).get();
  ASSERT_FALSE(conflict.ok());
  EXPECT_EQ(conflict.error().code, ErrorCode::Conflict);
  const auto snapshot = client->project_snapshot(project.handle).get();
  ASSERT_TRUE(snapshot.ok()) << snapshot.error().describe();
  EXPECT_EQ(snapshot.value()["project"]["revision"], 1);
  ASSERT_EQ(snapshot.value()["tables"].size(), 1u);
  EXPECT_EQ(snapshot.value()["tables"][0]["id"], edited.value()["commands"][0]["id"]);
  EXPECT_EQ(snapshot.value(), proposal.value()["snapshot"]);
  const auto history = client->project_history(project.handle).get();
  ASSERT_TRUE(history.ok());
  ASSERT_EQ(history.value().size(), 1u);
  /* History JSON is canonicalized by SQLite storage; object member order is immaterial. */
  EXPECT_EQ(nlohmann::json(history.value()[0]["commands"]), nlohmann::json(edited.value()["commands"]));
  const auto listed = client->project_list().get();
  ASSERT_TRUE(listed.ok());
  ASSERT_EQ(listed.value().size(), 1u);
  EXPECT_EQ(listed.value()[0].revision, 1);
  const auto closed = client->project_close(project.handle).get();
  ASSERT_TRUE(closed.ok());
  EXPECT_TRUE(closed.value());
  const auto expired = client->project_snapshot(project.handle).get();
  ASSERT_FALSE(expired.ok());
  EXPECT_EQ(expired.error().code, ErrorCode::NotFound);
  const auto reopened = client->project_open(project.directory).get();
  ASSERT_TRUE(reopened.ok());
  EXPECT_NE(reopened.value().handle, project.handle);
  EXPECT_EQ(reopened.value().id, project.id);
  EXPECT_EQ(reopened.value().revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
  EXPECT_EQ(client->stats().protocol_errors, 0u);
}

TEST_F(PythonBridge, ProjectEditOperationReceiptSurvivesRetryAndBridgeRestart)
{
  auto client = started(options());
  ASSERT_TRUE(client->hello_info()->has_method("project.edit_operations.apply_once"));
  ASSERT_TRUE(client->hello_info()->has_method("project.edit_operations.get"));
  const auto created = client->project_create(dir_.str() + "/receipt-project", "Durable edit").get();
  ASSERT_TRUE(created.ok()) << created.error().describe();
  const ProjectInfo project = created.value();
  ASSERT_EQ(project.format_version, 15);
  const std::string operation_id = "10000000-0000-4000-8000-000000000001";
  Json request = {{"handle", project.handle},
                  {"operation_id", operation_id},
                  {"expected_revision", 0},
                  {"commands", Json::array({{{"op", "create_table"}, {"name", "Created once"}}})}};
  CallOptions once;
  once.retry = CallOptions::Retry::Never;
  const auto first = client->call("project.edit_operations.apply_once", request, once).get();
  ASSERT_TRUE(first.ok()) << first.error().describe();
  EXPECT_EQ(first.value()["replayed"], false);

  /* The caller retries as though the first reply was lost: same unexpanded commands and old base,
   * without adopting the generated table UUID or changing the expected revision. */
  const auto replay = client->call("project.edit_operations.apply_once", request, once).get();
  ASSERT_TRUE(replay.ok()) << replay.error().describe();
  EXPECT_EQ(replay.value()["replayed"], true);
  const Json receipt = replay.value()["receipt"];
  EXPECT_EQ(nlohmann::json(receipt), nlohmann::json(first.value()["receipt"]));
  EXPECT_EQ(receipt["format"], "stk.project-edit-receipt/1");
  EXPECT_EQ(receipt["project_id"], project.id);
  EXPECT_EQ(receipt["operation_id"], operation_id);
  EXPECT_EQ(receipt["scope"], "local");
  EXPECT_EQ(receipt["base_revision"], 0);
  EXPECT_EQ(receipt["applied_revision"], 1);
  ASSERT_EQ(receipt["commands"].size(), 1u);
  ASSERT_TRUE(receipt["commands"][0]["id"].is_string());
  const std::string table_id = receipt["commands"][0]["id"].get<std::string>();
  EXPECT_EQ(table_id.size(), 36u);
  EXPECT_EQ(client->stats().schema_violations, 0u);
  EXPECT_EQ(client->stats().protocol_errors, 0u);
  client->close();
  client.reset();

  client = started(options());
  const auto reopened = client->project_open(project.directory).get();
  ASSERT_TRUE(reopened.ok()) << reopened.error().describe();
  EXPECT_EQ(reopened.value().id, project.id);
  EXPECT_EQ(reopened.value().revision, 1);
  const auto persisted = client->call("project.edit_operations.get",
                                      {{"handle", reopened.value().handle}, {"operation_id", operation_id}},
                                      once).get();
  ASSERT_TRUE(persisted.ok()) << persisted.error().describe();
  EXPECT_EQ(nlohmann::json(persisted.value()["receipt"]), nlohmann::json(receipt));
  request["handle"] = reopened.value().handle;
  const auto replay_after_restart = client->call("project.edit_operations.apply_once", request, once).get();
  ASSERT_TRUE(replay_after_restart.ok()) << replay_after_restart.error().describe();
  EXPECT_EQ(replay_after_restart.value()["replayed"], true);
  EXPECT_EQ(nlohmann::json(replay_after_restart.value()["receipt"]), nlohmann::json(receipt));
  const auto snapshot = client->project_snapshot(reopened.value().handle).get();
  ASSERT_TRUE(snapshot.ok()) << snapshot.error().describe();
  EXPECT_EQ(snapshot.value()["project"]["revision"], 1);
  ASSERT_EQ(snapshot.value()["tables"].size(), 1u);
  EXPECT_EQ(snapshot.value()["tables"][0]["id"], table_id);
  const auto history = client->project_history(reopened.value().handle).get();
  ASSERT_TRUE(history.ok()) << history.error().describe();
  EXPECT_EQ(history.value().size(), 1u);
  EXPECT_EQ(client->stats().schema_violations, 0u);
  EXPECT_EQ(client->stats().protocol_errors, 0u);
  client->close();
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
  EXPECT_TRUE(ids.count("scalar-volume"));
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

/** A listening 127.0.0.1 socket (ephemeral port) that only counts connections: the hostile proxy
 * of the hub tests. It never answers, so nothing reaches any other host through it. */
class ProxySink {
 public:
  ProxySink()
  {
    fd_ = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    socklen_t size = sizeof(address);
    if (fd_ < 0 || bind(fd_, reinterpret_cast<sockaddr *>(&address), size) != 0 || listen(fd_, 64) != 0 ||
        getsockname(fd_, reinterpret_cast<sockaddr *>(&address), &size) != 0)
    {
      return;
    }
    port_ = ntohs(address.sin_port);
  }
  ~ProxySink()
  {
    if (fd_ >= 0) {
      close(fd_);
    }
  }
  int port() const
  {
    return port_;
  }
  /** Connections made so far (accepted and closed here). */
  int connections()
  {
    while (fd_ >= 0) {
      const int client = accept4(fd_, nullptr, nullptr, SOCK_CLOEXEC);
      if (client < 0) {
        break;
      }
      close(client);
      connections_++;
    }
    return connections_;
  }

 private:
  int fd_ = -1;
  int port_ = 0;
  int connections_ = 0;
};

/* Synthetic, low-entropy proxy credentials: they must never appear in any output. */
constexpr const char *kProxyUserinfo = "stk-proxy:abcdefghijklmnopqrstu";

/** Every proxy variable pointed at `sink`, with no bypass list. */
std::map<std::string, std::optional<std::string>> hostile_proxy_env(const ProxySink &sink)
{
  const std::string url = std::string("http://") + kProxyUserinfo + "@127.0.0.1:" + std::to_string(sink.port());
  std::map<std::string, std::optional<std::string>> env;
  for (const char *name : {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}) {
    env[name] = url;
  }
  env["NO_PROXY"] = env["no_proxy"] = std::string();
  return env;
}

/* Client::task_get(target, id, require_live=true) through the strict Python bridge, a loopback Hub
 * (uvicorn), a real NodeAgent.run (outbound WebSocket) and the loopback Runtime: the exact lookup
 * finds a finished task after it left the node's bounded 200-task heartbeat snapshot, answers
 * `unavailable` (from the bridge, retryable) while the node is offline, and after the reconnect finds
 * the same task again, with no task or Hub action created on the way. The helper runs under hostile
 * proxy variables (a counting loopback sink) and must keep its own traffic off them, then close in order. */
TEST_F(PythonBridge, ExactLiveTaskGetThroughALoopbackHubAcrossTheWindowAndAnOutage)
{
  if (const std::string why = unavailable("hub"); !why.empty()) {
    GTEST_SKIP() << why;
  }
  ProxySink sink;
  ASSERT_NE(sink.port(), 0);
  RuntimeFixture hub;
  /* Its dependencies import (checked above): a helper that does not come up is a chain failure. */
  if (const std::string why = start_runtime(hub, "hub", hostile_proxy_env(sink)); !why.empty()) {
    FAIL() << why;
  }
  for (const auto &[name, value] : hostile_proxy_env(sink)) { /* names only, never values */
    if (value && !value->empty()) {
      EXPECT_NE(std::find(hub.info["proxy_env_cleared"].begin(), hub.info["proxy_env_cleared"].end(), name),
                hub.info["proxy_env_cleared"].end())
          << name;
    }
  }
  const std::string task_id = hub.info["task_id"].get<std::string>();
  const std::string node_id = hub.info["node_id"].get<std::string>();
  const std::string missing = hub.info["missing_id"].get<std::string>();
  auto client = started(options());
  PairHubParams pairing;
  pairing.name = "lab";
  pairing.url = hub.info["url"].get<std::string>();
  {
    std::ifstream code_file(hub.info["code_file"].get<std::string>());
    std::getline(code_file, pairing.code);
  }
  ASSERT_FALSE(pairing.code.empty());
  pairing.device_name = "桌面";
  const Result<ConnectionInfo> paired = client->connections_pair_hub(pairing).get();
  ASSERT_TRUE(paired.ok()) << paired.error().describe();
  ASSERT_EQ(paired.value().id, "hub:lab");
  const Target target{paired.value().id, node_id};
  auto listed = [&] {
    std::set<std::string> ids;
    const Result<Json> tasks = client->task_list(target).get();
    EXPECT_TRUE(tasks.ok()) << tasks.error().describe();
    if (tasks.ok()) {
      for (const Json &task : tasks.value()["tasks"]) {
        ids.insert(task["id"].get<std::string>());
      }
    }
    return ids;
  };
  /* One observation of the Hub's device record, for this node. */
  auto replied = [&](const Json &reply) {
    return reply.is_object() && reply.value("ok", false) && reply.value("node_id", "") == node_id;
  };
  auto expect_found = [&](const char *phase) {
    const Result<Json> found = client->task_get(target, task_id, true).get();
    EXPECT_TRUE(found.ok()) << phase << ": " << found.error().describe();
    return found.ok() ? found.value()["task"] : Json(nullptr);
  };

  const Json before = hub.command("state");
  ASSERT_TRUE(replied(before)) << before.dump();
  ASSERT_TRUE(before["task_in_snapshot"].get<bool>());
  EXPECT_EQ(before["synthetic_rows"], 0);
  EXPECT_EQ(before["runtime_tasks"], Json::array({task_id}));
  EXPECT_EQ(before["task_state"], "succeeded");
  EXPECT_TRUE(listed().count(task_id)) << "the finished task starts inside the heartbeat snapshot";

  /* 1. The next real heartbeat lists only synthetic rows; the exact entry still finds the task. */
  const Json windowed = hub.command("window");
  ASSERT_TRUE(replied(windowed)) << windowed.dump();
  ASSERT_GT(windowed["last_seen"].get<double>(), before["last_seen"].get<double>());
  ASSERT_EQ(windowed["snapshot_tasks"], 200);
  ASSERT_EQ(windowed["synthetic_rows"], 200);
  ASSERT_EQ(windowed["other_rows"], Json::array());
  ASSERT_FALSE(windowed["task_in_snapshot"].get<bool>());
  ASSERT_TRUE(windowed["missing_in_snapshot"].get<bool>());
  const std::set<std::string> window_ids = listed();
  EXPECT_EQ(window_ids.size(), 200u);
  EXPECT_FALSE(window_ids.count(task_id));
  EXPECT_TRUE(window_ids.count(missing));
  const Json original = expect_found("outside the window");
  ASSERT_TRUE(original.is_object());
  EXPECT_EQ(original["id"], task_id);
  EXPECT_EQ(original["state"], "succeeded");
  /* Control: listed in the snapshot but absent from the Runtime, so the live answer is the node's. */
  const Result<Json> absent = client->task_get(target, missing, true).get();
  ASSERT_FALSE(absent.ok());
  EXPECT_EQ(absent.error().code, ErrorCode::RemoteError) << absent.error().describe();
  EXPECT_NE(absent.error().message.find("Task not found"), std::string::npos) << absent.error().describe();
  EXPECT_FALSE(absent.error().local);

  /* 2. Offline: `unavailable` from the bridge, never a task result; the Runtime still says succeeded. */
  const Json down = hub.command("offline");
  ASSERT_TRUE(replied(down)) << down.dump();
  ASSERT_FALSE(down["online"].get<bool>());
  const Result<Json> offline = client->task_get(target, task_id, true).get();
  ASSERT_FALSE(offline.ok()) << offline.value().dump();
  EXPECT_EQ(offline.error().code, ErrorCode::Unavailable) << offline.error().describe();
  EXPECT_TRUE(offline.error().retryable);
  EXPECT_FALSE(offline.error().local) << "the bridge answered, not the client";
  const Json during = hub.command("state");
  ASSERT_TRUE(replied(during)) << during.dump();
  EXPECT_EQ(during["task_state"], "succeeded");
  EXPECT_EQ(during["runtime_tasks"], Json::array({task_id}));

  /* 3. Reconnected: its first heartbeat (still the window) and the same identity, nothing new created. */
  const Json up = hub.command("online");
  ASSERT_TRUE(replied(up)) << up.dump();
  ASSERT_TRUE(up["online"].get<bool>());
  ASSERT_GT(up["last_seen"].get<double>(), windowed["last_seen"].get<double>());
  ASSERT_EQ(up["synthetic_rows"], 200);
  ASSERT_FALSE(up["task_in_snapshot"].get<bool>());
  const Json recovered = expect_found("after the reconnect");
  EXPECT_EQ(recovered, original);
  const Json after = hub.command("state");
  ASSERT_TRUE(replied(after)) << after.dump();
  EXPECT_EQ(after["runtime_tasks"], Json::array({task_id}));
  EXPECT_EQ(after["actions"], before["actions"]);
  EXPECT_EQ(after["action_events"], before["action_events"]);
  EXPECT_EQ(after["task_state"], "succeeded");
  EXPECT_EQ(client->bridge_log().text().find(pairing.code), std::string::npos);
  EXPECT_EQ(client->stats().schema_violations, 0u);
  EXPECT_EQ(client->stats().restarts, 0u);
  client->close();
  EXPECT_EQ(hub.close_checked(), "");
  EXPECT_EQ(sink.connections(), 0) << "the helper sent traffic to the proxy variables";
  EXPECT_EQ(hub.stderr_tail(1 << 20).find(kProxyUserinfo), std::string::npos);
}

/* The helper stops while its node is offline (as when a check fails between `offline` and
 * `online`): the stopped agent, the Hub and the Runtime still close in order, exit 0. */
TEST_F(PythonBridge, LoopbackHubFixtureClosesInOrderWhileItsNodeIsOffline)
{
  if (const std::string why = unavailable("hub"); !why.empty()) {
    GTEST_SKIP() << why;
  }
  ProxySink sink;
  ASSERT_NE(sink.port(), 0);
  RuntimeFixture hub;
  if (const std::string why = start_runtime(hub, "hub", hostile_proxy_env(sink)); !why.empty()) {
    FAIL() << why;
  }
  const Json down = hub.command("offline");
  ASSERT_TRUE(down.is_object() && down.value("ok", false)) << down.dump();
  ASSERT_FALSE(down["online"].get<bool>());
  EXPECT_EQ(hub.close_checked(), "");
  EXPECT_EQ(sink.connections(), 0);
}

#endif

}  // namespace
}  // namespace stk::bridge
