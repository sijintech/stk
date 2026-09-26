/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file stk::bridge::Client against the scripted fake bridge (stk-bridge-fake). */

#include <gtest/gtest.h>

#include <atomic>
#include <cmath>
#include <set>

#include "stk/bridge/client.hh"
#include "support.hh"

namespace stk::bridge {
namespace {

using test::fake_options;
using test::ManualLoop;
using test::TempDir;
using test::wait_until;

class FakeBridge : public ::testing::Test {
 protected:
  void TearDown() override
  {
    /* Every test leaves no fake bridge (or its helpers) behind. */
    for (long pgid : groups_) {
      EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10.0))
          << "process group " << pgid << " still alive";
    }
    EXPECT_TRUE(wait_until([&] { return test::processes_matching(marker_).empty(); }, 10.0))
        << "stray fake bridges: " << test::processes_matching(marker_).size();
  }

  /** Options whose command line carries a marker unique to this test (strays check). */
  ClientOptions options(std::vector<std::string> args, Executor executor = {})
  {
    args.push_back("--state");
    args.push_back(dir_.str() + "/" + marker_);
    return fake_options(args, std::move(executor));
  }

  std::unique_ptr<Client> started(ClientOptions opts)
  {
    auto client = Client::create(std::move(opts));
    std::string error;
    EXPECT_TRUE(client->start(&error)) << error;
    EXPECT_TRUE(client->wait_ready(20.0));
    track(*client);
    return client;
  }

  void track(Client &client)
  {
    if (const int64_t pid = client.bridge_pid()) {
      groups_.insert(long(pid));
    }
  }

  TempDir dir_{"fake"};
  std::string marker_ = "fake-marker-" + std::to_string(::testing::UnitTest::GetInstance()->random_seed()) + "-" +
                        ::testing::UnitTest::GetInstance()->current_test_info()->name();
  std::set<long> groups_;
};

TEST_F(FakeBridge, HelloAndEchoWithCjk)
{
  auto client = started(options({}));
  const auto hello = client->hello_info();
  ASSERT_TRUE(hello);
  EXPECT_EQ(hello->server.name, "stk-bridge-fake");
  EXPECT_EQ(hello->server.pid, client->bridge_pid());
  EXPECT_EQ(hello->limits.max_line_bytes, 4096);
  const Result<Json> r = client->call("echo", {{"text", "计算完成 🧲"}, {"n", 3}}).get();
  ASSERT_TRUE(r.ok()) << r.error().describe();
  EXPECT_EQ(r.value()["params"]["text"], "计算完成 🧲");
  EXPECT_EQ(client->state(), BridgeState::Ready);
  client->close();
  EXPECT_EQ(client->state(), BridgeState::Stopped);
}

TEST_F(FakeBridge, ResponseSplitAcrossManyReads)
{
  auto client = started(options({}));
  const std::string text = "多字节字符被切开 🧲🧲🧲 end";
  const Result<Json> r = client->call("split", {{"text", text}}).get();
  ASSERT_TRUE(r.ok()) << r.error().describe();
  EXPECT_EQ(r.value()["text"], text);
  EXPECT_EQ(client->stats().protocol_errors, 0u);
}

TEST_F(FakeBridge, OversizedInvalidUtf8AndBadJsonLinesAreDropped)
{
  auto client = started(options({}));
  /* The junk lines precede each response on the pipe, so they are counted before the call
   * completes; the checks still poll (bounded) rather than rely on that ordering. */
  const auto answer = [&](const char *method) {
    const Result<Json> r = client->call(method).get();
    EXPECT_TRUE(r.ok()) << method << ": " << (r.ok() ? "" : r.error().describe());
    return r.ok() ? io::get_string(r.value(), "after") : std::string();
  };
  EXPECT_EQ(answer("oversize"), "oversize");
  EXPECT_TRUE(test::protocol_errors_reach(*client, 1));
  EXPECT_EQ(answer("badutf8"), "badutf8");
  EXPECT_TRUE(test::protocol_errors_reach(*client, 2));
  /* garbage, a duplicate key (its id must not complete the call), NaN, a non-object, result+error */
  EXPECT_EQ(answer("badjson"), "badjson");
  EXPECT_TRUE(test::protocol_errors_reach(*client, 7));
  EXPECT_TRUE(test::log_eventually_contains(*client, "over the line limit"));
  EXPECT_TRUE(test::log_eventually_contains(*client, "not valid UTF-8"));
  EXPECT_TRUE(test::log_eventually_contains(*client, "duplicate key"));
  EXPECT_EQ(client->stats().protocol_errors, 7u); /* and not more */
  EXPECT_EQ(client->state(), BridgeState::Ready); /* junk never kills the session */
}

TEST_F(FakeBridge, OutOfOrderResponsesMatchById)
{
  auto client = started(options({}));
  std::vector<Future<Json>> held;
  for (int i = 0; i < 5; i++) {
    held.push_back(client->call("hold", {{"tag", i}}));
  }
  Future<Json> slow = client->call("slow", {{"ms", 200}});
  EXPECT_TRUE(client->call("release").get().ok()); /* answered after the held ones, in reverse */
  for (int i = 0; i < 5; i++) {
    EXPECT_EQ(held[size_t(i)].get().value()["tag"], i);
  }
  EXPECT_EQ(slow.get().value()["slept"], 200);
}

TEST_F(FakeBridge, EventsInterleavedWithResponsesKeepTheirOrderOnTheLoop)
{
  ManualLoop loop;
  auto client = started(options({}, loop.executor()));
  std::vector<std::string> seen;
  ListenerHandle ticks = client->on_event("test.tick", [&](const std::string &, const Json &data) {
    seen.push_back("tick" + std::to_string(data["i"].get<int>()));
  });
  bool done = false;
  client->call("interleave", {{"n", 3}}).then([&](Result<Json> r) {
    ASSERT_TRUE(r.ok());
    seen.push_back("response");
    done = true;
  });
  ASSERT_TRUE(loop.pump_until([&] { return done && seen.size() == 7; }));
  const std::vector<std::string> expected = {"tick0", "tick1", "tick2", "response", "tick3", "tick4", "tick5"};
  EXPECT_EQ(seen, expected);
  ticks.reset();
  client->call("interleave", {{"n", 2}}).get();
  loop.run_ready();
  EXPECT_EQ(seen.size(), 7u); /* the listener is gone */
}

TEST_F(FakeBridge, TimeoutAndCancelAreLocal)
{
  auto client = started(options({}));
  CallOptions quick;
  quick.timeout_s = 0.2;
  const Result<Json> timed_out = client->call("slow", {{"ms", 1500}}, quick).get();
  ASSERT_FALSE(timed_out.ok());
  EXPECT_EQ(timed_out.error().code, ErrorCode::Timeout);
  EXPECT_TRUE(timed_out.error().local);
  Future<Json> cancelled = client->call("slow", {{"ms", 1500}});
  cancelled.cancel();
  EXPECT_EQ(cancelled.get().error().code, ErrorCode::Cancelled);
  /* The late answers are dropped; the session goes on. */
  EXPECT_TRUE(client->call("echo").get().ok());
  std::this_thread::sleep_for(std::chrono::milliseconds(1600));
  EXPECT_TRUE(client->call("echo").get().ok());
  EXPECT_EQ(client->stats().protocol_errors, 0u);
}

TEST_F(FakeBridge, CallsMadeBeforeReadyWaitForHello)
{
  auto client = Client::create(options({"--hello-delay-once", "300"}));
  ASSERT_TRUE(client->start());
  Future<Json> early = client->call("echo", {{"early", true}});
  EXPECT_NE(client->state(), BridgeState::Ready);
  const Result<Json> r = early.get();
  ASSERT_TRUE(r.ok()) << r.error().describe();
  EXPECT_EQ(r.value()["params"]["early"], true);
  track(*client);
}

TEST_F(FakeBridge, LocalValidationAndLineLimit)
{
  ClientOptions opts = options({});
  opts.validate = true;
  auto client = started(std::move(opts));
  const Result<Json> invalid = client->call("task.get", {{"connection", "local"}}).get();
  ASSERT_FALSE(invalid.ok());
  EXPECT_EQ(invalid.error().code, ErrorCode::InvalidParams);
  EXPECT_TRUE(invalid.error().local);
  EXPECT_TRUE(invalid.error().data.contains("errors"));
  ClientOptions plain = options({});
  auto second = Client::create(std::move(plain));
  ASSERT_TRUE(second->start());
  ASSERT_TRUE(second->wait_ready(20));
  track(*second);
  const Result<Json> long_line = second->call("echo", {{"pad", std::string(5000, 'x')}}).get();
  ASSERT_FALSE(long_line.ok());
  EXPECT_EQ(long_line.error().code, ErrorCode::LineTooLong); /* the fake's hello said 4096 */
  const Result<Json> nan = second->call("echo", {{"v", std::nan("")}}).get();
  EXPECT_EQ(nan.error().code, ErrorCode::InvalidParams);
}

TEST_F(FakeBridge, ReadsAreRetriedAfterTheBridgeDies)
{
  auto client = started(options({"--die-once-on", "task.get"}));
  const int64_t first = client->bridge_pid();
  const Result<Json> r = client->call("task.get", {{"connection", "local"}, {"task_id", "t"}}).get();
  ASSERT_TRUE(r.ok()) << r.error().describe();
  EXPECT_EQ(r.value()["method"], "task.get");
  EXPECT_NE(client->bridge_pid(), first);
  track(*client);
  const ClientStats stats = client->stats();
  EXPECT_EQ(stats.spawned, 2u);
  EXPECT_EQ(stats.restarts, 1u);
  EXPECT_EQ(stats.calls_retried, 1u);
  EXPECT_EQ(client->state(), BridgeState::Ready);
}

TEST_F(FakeBridge, NonIdempotentCallsFailUnavailableAfterADeath)
{
  auto client = started(options({"--die-once-on", "upload.start"}));
  const Result<Json> r = client->call("upload.start", {{"connection", "local"}}).get();
  ASSERT_FALSE(r.ok());
  EXPECT_EQ(r.error().code, ErrorCode::Unavailable);
  EXPECT_TRUE(r.error().retryable);
  EXPECT_TRUE(r.error().local);
  EXPECT_TRUE(client->wait_ready(20));
  track(*client);
  EXPECT_TRUE(client->call("echo").get().ok()); /* the restarted bridge serves new calls */
  /* Retry::Always overrides the method table (the caller knows it is safe). */
  CallOptions always;
  always.retry = CallOptions::Retry::Always;
  const Result<Json> retried = client->call("partial_crash", Json::object(), always).get();
  EXPECT_FALSE(retried.ok()); /* it crashes every time: bounded by max_retries */
  EXPECT_EQ(retried.error().code, ErrorCode::Unavailable);
}

TEST_F(FakeBridge, APartialLineAtDeathIsNeverDelivered)
{
  auto client = started(options({}));
  const Result<Json> r = client->call("partial_crash").get();
  ASSERT_FALSE(r.ok());
  EXPECT_EQ(r.error().code, ErrorCode::Unavailable);
  EXPECT_TRUE(test::log_eventually_contains(*client, "unterminated final line"));
  EXPECT_TRUE(client->wait_ready(20));
  track(*client);
}

TEST_F(FakeBridge, LogSubscriptionResumesExactlyAfterKill9)
{
  ManualLoop loop;
  ClientOptions opts = options({"--log-interval", "10"}, loop.executor());
  auto client = started(std::move(opts));
  std::string text;
  std::vector<LogChunk> chunks;
  bool ended = false;
  LogsParams params;
  params.target = {"local", ""};
  params.task_id = "t";
  LogsHandlers handlers;
  handlers.on_chunk = [&](const LogChunk &c) {
    chunks.push_back(c);
    text += c.text;
  };
  handlers.on_end = [&](const LogsEnd &) { ended = true; };
  Subscription sub = client->subscribe_logs(params, handlers);
  ASSERT_TRUE(loop.pump_until([&] { return chunks.size() >= 5; }));
  const int64_t first = client->bridge_pid();
  test::kill_hard(first);
  ASSERT_TRUE(loop.pump_until([&] { return ended; }, 60));
  track(*client);
  std::string expected;
  for (int i = 0; i < 40; i++) {
    expected += "第" + std::to_string(i) + "步 能量 −1.5e-3 🧲\n";
  }
  expected += "结束";
  EXPECT_EQ(text, expected);
  int64_t position = 0;
  for (const LogChunk &c : chunks) {
    EXPECT_EQ(c.offset, position);
    EXPECT_EQ(c.bytes, c.next_offset - c.offset); /* the fake sends no `bytes`: derived from the offsets */
    EXPECT_TRUE(c.exact());
    position = c.next_offset;
  }
  EXPECT_EQ(position, int64_t(expected.size()));
  EXPECT_EQ(sub.subscribe_count(), 2);
  EXPECT_EQ(client->stats().restarts, 1u);
  EXPECT_FALSE(sub.active());
  EXPECT_NE(client->bridge_pid(), first);
}

TEST_F(FakeBridge, EventsSubscriptionResumesFromItsOffsetAfterKill9)
{
  ManualLoop loop;
  auto client = started(options({"--log-interval", "10"}, loop.executor()));
  std::vector<EventsBatch> batches;
  std::optional<EventsEnd> end;
  EventsParams params;
  params.target = {"local", ""};
  params.task_id = "t";
  params.offset = 20; /* a view restored at event 2 */
  EventsHandlers handlers;
  handlers.on_batch = [&](const EventsBatch &b) { batches.push_back(b); };
  handlers.on_end = [&](const EventsEnd &e) { end = e; };
  Subscription sub = client->subscribe_events(params, handlers);
  ASSERT_TRUE(loop.pump_until([&] { return batches.size() >= 5; }));
  test::kill_hard(client->bridge_pid());
  ASSERT_TRUE(loop.pump_until([&] { return end.has_value(); }, 60));
  track(*client);
  int64_t position = 20;
  for (const EventsBatch &b : batches) {
    EXPECT_EQ(b.offset, position);
    EXPECT_EQ(b.events[0]["i"], position / 10);
    position = b.next_offset;
  }
  EXPECT_EQ(position, 300);
  EXPECT_EQ(end->next_offset, 300);
  EXPECT_EQ(sub.subscribe_count(), 2);
  EXPECT_EQ(sub.events_offset(), 300);
}

TEST_F(FakeBridge, UnsubscribeStopsCallbacksAndTellsTheBridge)
{
  ManualLoop loop;
  auto client = started(options({"--log-interval", "20"}, loop.executor()));
  int chunks = 0;
  LogsParams params;
  params.target = {"local", ""};
  params.task_id = "t";
  LogsHandlers handlers;
  handlers.on_chunk = [&](const LogChunk &) { chunks++; };
  {
    Subscription sub = client->subscribe_logs(params, handlers);
    ASSERT_TRUE(loop.pump_until([&] { return chunks >= 2; }));
    EXPECT_FALSE(sub.server_id().empty());
  } /* RAII: unsubscribed here */
  const int at_unsubscribe = chunks;
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  loop.run_ready();
  EXPECT_EQ(chunks, at_unsubscribe); /* already-posted callbacks are skipped too */
  EXPECT_TRUE(wait_until([&] { return client->call("stats").get().value()["unsubscribes"] == 1; }, 10));
}

TEST_F(FakeBridge, CrashLoopEndsInFailed)
{
  ClientOptions opts = options({"--exit-at-start", "1"});
  opts.restart.max_failures = 3;
  auto client = Client::create(std::move(opts));
  ASSERT_TRUE(client->start());
  EXPECT_FALSE(client->wait_ready(20));
  EXPECT_EQ(client->state(), BridgeState::Failed);
  EXPECT_EQ(client->stats().spawned, 4u);
  ASSERT_TRUE(client->last_error());
  EXPECT_NE(client->last_error()->message.find("keeps exiting"), std::string::npos);
  const Result<Json> r = client->call("echo").get();
  EXPECT_EQ(r.error().code, ErrorCode::Unavailable);
  Subscription sub = client->watch({{"local", ""}}, {});
  EXPECT_FALSE(sub.active());
}

TEST_F(FakeBridge, ABusyStateDirectoryIsNotRetried)
{
  auto client = Client::create(options({"--busy"}));
  std::vector<BridgeState> states;
  std::mutex m;
  ListenerHandle listener = client->on_state([&](BridgeState s, const std::optional<Error> &) {
    std::lock_guard lock(m);
    states.push_back(s);
  });
  ASSERT_TRUE(client->start());
  EXPECT_FALSE(client->wait_ready(20));
  EXPECT_EQ(client->state(), BridgeState::Failed);
  ASSERT_TRUE(client->last_error());
  EXPECT_EQ(client->last_error()->code, ErrorCode::Busy);
  EXPECT_FALSE(client->last_error()->retryable);
  EXPECT_NE(client->last_error()->message.find("state directory"), std::string::npos);
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  EXPECT_EQ(client->stats().spawned, 1u); /* no restart loop */
  std::lock_guard lock(m);
  EXPECT_EQ(states.back(), BridgeState::Failed);
}

TEST_F(FakeBridge, HelloTimeoutRestartsTheBridge)
{
  /* The first bridge sleeps far past the hello timeout; the second answers at once (a loaded
   * machine may still need more than one retry, hence >= 2). */
  ClientOptions opts = options({"--hello-delay-once", "20000"});
  opts.hello_timeout_s = 1.5;
  auto client = Client::create(std::move(opts));
  ASSERT_TRUE(client->start());
  ASSERT_TRUE(client->wait_ready(60));
  track(*client);
  EXPECT_GE(client->stats().spawned, 2u);
  EXPECT_TRUE(test::log_eventually_contains(*client, "no hello answer"));
}

TEST_F(FakeBridge, CloseTerminatesABridgeThatIgnoresEofAndItsHelpers)
{
  ClientOptions opts = options({"--ignore-eof", "--grandchild"});
  opts.shutdown_grace_s = 0.3;
  auto client = started(std::move(opts));
  const long pgid = long(client->bridge_pid());
  EXPECT_TRUE(test::process_group_alive(pgid));
  const auto started_at = std::chrono::steady_clock::now();
  client->close();
  EXPECT_LT(std::chrono::steady_clock::now() - started_at, std::chrono::seconds(5));
  EXPECT_TRUE(test::log_eventually_contains(*client, "did not exit"));
  EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10));
  const Result<Json> r = client->call("echo").get();
  EXPECT_EQ(r.error().code, ErrorCode::ShuttingDown);
}

TEST_F(FakeBridge, CloseFailsPendingCallsWithShuttingDown)
{
  auto client = started(options({}));
  Future<Json> held = client->call("hold", {{"tag", 1}});
  client->close();
  const Result<Json> r = held.get();
  ASSERT_FALSE(r.ok());
  EXPECT_EQ(r.error().code, ErrorCode::ShuttingDown);
}

TEST_F(FakeBridge, StderrGoesToTheBridgeLog)
{
  auto client = started(options({"--stderr-noise"}));
  EXPECT_TRUE(test::log_eventually_contains(*client, "启动 ok"));
  /* close() drains stderr to EOF before it returns: nothing written before the exit is lost. */
  client->close();
  const std::string log = client->bridge_log().text();
  EXPECT_NE(log.find("bad bytes: \xef\xbf\xbd\xef\xbf\xbd end"), std::string::npos);
  EXPECT_NE(log.find("no newline at the end"), std::string::npos); /* flushed at exit */
  EXPECT_NE(log.find("state ready"), std::string::npos);
}

TEST_F(FakeBridge, CallbacksRunOnlyOnTheExecutorThread)
{
  ManualLoop loop;
  auto client = started(options({}, loop.executor()));
  const std::thread::id test_thread = std::this_thread::get_id();
  std::atomic<int> done{0};
  std::atomic<bool> wrong_thread{false};
  for (int i = 0; i < 20; i++) {
    client->call("echo", {{"i", i}}).then([&](Result<Json>) {
      if (std::this_thread::get_id() != test_thread) {
        wrong_thread = true;
      }
      done++;
    });
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  EXPECT_EQ(done.load(), 0); /* nothing runs until the loop pumps */
  ASSERT_TRUE(loop.pump_until([&] { return done.load() == 20; }));
  EXPECT_FALSE(wrong_thread.load());
}

TEST_F(FakeBridge, RestartAfterFailedStartsAgain)
{
  ClientOptions opts = options({"--die-once-on", "hello"});
  opts.restart.max_failures = 0;
  auto client = Client::create(std::move(opts));
  ASSERT_TRUE(client->start());
  EXPECT_FALSE(client->wait_ready(20));
  EXPECT_EQ(client->state(), BridgeState::Failed);
  client->restart();
  ASSERT_TRUE(client->wait_ready(20));
  track(*client);
  EXPECT_TRUE(client->call("echo").get().ok());
}

}  // namespace
}  // namespace stk::bridge
