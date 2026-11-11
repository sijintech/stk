/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file JobsState against the scripted fake bridge (stk-bridge-fake --jobs): the Jobs editor's
 * state machines through the real stk_bridge client, without a GPU. */

#include <algorithm>
#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "stk/io/json.hh"
#include "stk/io/png.hh"

#include "jobs_support.hh"
#include "../bridge/fake_jobs.hh"

namespace stk::jobstest {
namespace {

using app::JobsState;
using app::SubmitState;
using io::Json;

bool has(const std::vector<std::string> &v, const std::string &s)
{
  return std::find(v.begin(), v.end(), s) != v.end();
}

void set_f03_phase(const FakeJobs &fixture, const char *value)
{
  std::ofstream(fixture.jobs_dir() + "/f03-phase.next") << value;
  std::filesystem::rename(fixture.jobs_dir() + "/f03-phase.next", fixture.jobs_dir() + "/f03-phase");
}

void release_artifact_start(FakeJobs &fixture, const std::string &completed_id)
{
  bool received = false;
  /* The fake sends the held start response before replying to this read. */
  fixture.client->transfer_get(completed_id).then([&](const auto &reply) {
    EXPECT_TRUE(reply && reply.value().state == "completed");
    received = true;
  });
  ASSERT_TRUE(fixture.pump([&] { return received; }));
}

const app::TaskRow *task_named(JobsState &j, const std::string &name)
{
  for (const app::TaskRow &t : j.tasks()) {
    if (t.name == name) {
      return &t;
    }
  }
  return nullptr;
}

std::string log_text(ui::LogBuffer &log)
{
  std::string s;
  for (size_t i = 0; i < log.line_count(); i++) {
    s += std::string(log.line(i)) + "\n";
  }
  return s;
}

class JobsFake : public ::testing::Test {
 protected:
  void SetUp() override
  {
    if (std::string(STK_BRIDGE_FAKE).empty()) {
      GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
    }
  }
};

/* ---- Scripted log subscriptions (DIR/logs-plan.json of the fake) ---- */

const std::string kLogTask = "33333333333333333333333333333333";
const std::string kOtherLogTask = "44444444444444444444444444444444";
#define STK_FFFD "\xEF\xBF\xBD" /* U+FFFD: what one invalid source byte decodes to */

void write_logs_plan(const FakeJobs &f, const Json &plan)
{
  const std::string path = f.jobs_dir() + "/logs-plan.json";
  std::ofstream(path + ".tmp") << plan.dump();
  std::filesystem::rename(path + ".tmp", path);
}

void touch(const FakeJobs &f, const std::string &name)
{
  std::ofstream(f.jobs_dir() + "/" + name) << "go\n";
}

/** The params of every logs.subscribe the fake received, in order. */
std::vector<Json> logs_subscribes(const FakeJobs &f)
{
  std::vector<Json> out;
  std::ifstream in(f.jobs_dir() + "/logs-subscribes.jsonl");
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty()) {
      out.push_back(io::parse_json(line));
    }
  }
  return out;
}

size_t method_count(const FakeJobs &f, const std::string &method)
{
  const std::vector<std::string> m = f.methods();
  return size_t(std::count(m.begin(), m.end(), method));
}

/** Requests that a log retry must never send (anything but logs.subscribe). */
std::map<std::string, size_t> non_log_requests(const FakeJobs &f)
{
  std::map<std::string, size_t> out;
  for (const char *m : {"events.subscribe", "watch", "task.get", "task.list", "task.submit", "task.cancel",
                        "task.artifacts", "workspace.list", "workspace.files", "download.start", "upload.start"}) {
    out[m] = method_count(f, m);
  }
  return out;
}

/** Waits until the client has handled everything the fake sent before this round trip. */
void drain(FakeJobs &f)
{
  bool drained = false;
  f.client->call("connections.list").then([&](const bridge::Result<Json> &) { drained = true; });
  ASSERT_TRUE(f.pump([&] { return drained; }));
}

Json log_chunk(const std::string &stream, const std::string &text, int64_t offset, int64_t next_offset)
{
  return {{"stream", stream}, {"text", text}, {"offset", offset}, {"next_offset", next_offset}};
}

/* Source bytes: stdout "开始 α\n第1步 能" (21 bytes) + "量" and one invalid byte (4 bytes, decoded as
 * 量 U+FFFD: 6 bytes of text); stderr "警告：网" (12 bytes). Both streams stop mid-line. */
Json partial_then_final(const std::string &code = "unavailable", bool retryable = true)
{
  return {{"chunks", Json::array({log_chunk("stdout", "开始 α\n第1步 能", 0, 21),
                                  log_chunk("stdout", "量" STK_FFFD, 21, 25),
                                  log_chunk("stderr", "警告：网", 0, 12)})},
          {"error", {{"code", code}, {"message", "The local Runtime API is not running"},
                     {"retryable", retryable}, {"final", true}}}};
}

/** The rest of both streams; stderr overlaps 3 already accepted bytes (the client trims them). */
Json continuation()
{
  return {{"chunks", Json::array({log_chunk("stdout", " −1.5e-3\n完成\n", 25, 43),
                                  log_chunk("stderr", "网格较粗\n", 9, 22)})},
          {"end", true}};
}

const char *const kPartialAll = "开始 α\n";
const char *const kPartialOut = "开始 α\n第1步 能量" STK_FFFD "\n";
const char *const kPartialErr = "警告：网\n";
const char *const kWholeAll = "开始 α\n第1步 能量" STK_FFFD " −1.5e-3\n完成\n[stderr] 警告：网格较粗\n";
const char *const kWholeOut = "开始 α\n第1步 能量" STK_FFFD " −1.5e-3\n完成\n";
const char *const kWholeErr = "警告：网格较粗\n";

using Offsets = std::map<std::string, int64_t>;

/** Lists synthetic failed tasks (no artifact read: nothing is selected yet) and selects the first. */
void select_failed_task(FakeJobs &f, const Json &plan, const std::vector<std::string> &tasks = {kLogTask})
{
  JobsState &j = f.jobs();
  write_logs_plan(f, plan);
  Json rows = Json::array();
  for (const std::string &id : tasks) {
    rows.push_back({{"id", id}, {"name", "合成失败任务 " + id.substr(0, 4)}, {"state", "failed"},
                    {"workspace_id", j.workspace()}});
  }
  ASSERT_TRUE(j.selected().empty());
  j.apply_snapshot(rows, 100.0);
  j.select_task(tasks.front());
}

TEST_F(JobsFake, FinalLogErrorKeepsPartialLinesAndRetriesOnceFromSourceOffsets)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  select_failed_task(f, Json::array({partial_then_final(), continuation()}));
  ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));

  /* Stopped truthfully: accepted text kept, both half lines held out of the combined view. */
  EXPECT_EQ(j.logs_failure()->code, bridge::ErrorCode::Unavailable);
  EXPECT_TRUE(j.logs_failure()->retryable);
  EXPECT_FALSE(j.logs_ended());
  EXPECT_EQ(log_text(j.log_all()), kPartialAll);
  EXPECT_EQ(log_text(j.log_stdout()), kPartialOut);
  EXPECT_EQ(log_text(j.log_stderr()), kPartialErr);
  /* Source bytes, not text length (stdout's text is 27 bytes long). */
  EXPECT_EQ(j.log_offsets(), (Offsets{{"stdout", 25}, {"stderr", 12}}));
  ASSERT_TRUE(j.can_retry_logs());

  const auto others = non_log_requests(f);
  j.retry_logs(j.log_retry_generation());
  j.retry_logs(j.log_retry_generation()); /* a second click before any answer sends nothing */
  EXPECT_FALSE(j.logs_failure().has_value());
  EXPECT_FALSE(j.can_retry_logs());
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));

  const std::vector<Json> subs = logs_subscribes(f);
  ASSERT_EQ(subs.size(), 2u);
  EXPECT_FALSE(subs[0].contains("offsets")) << subs[0].dump();
  EXPECT_EQ(subs[1].value("task_id", std::string()), kLogTask);
  EXPECT_EQ(subs[1].value("streams", Json()), Json::array({"stdout", "stderr"}));
  EXPECT_EQ(subs[1].at("offsets").get<Offsets>(), (Offsets{{"stdout", 25}, {"stderr", 12}})) << subs[1].dump();
  /* Continued exactly: no repeated or spliced line in any view. */
  EXPECT_EQ(log_text(j.log_all()), kWholeAll);
  EXPECT_EQ(log_text(j.log_stdout()), kWholeOut);
  EXPECT_EQ(log_text(j.log_stderr()), kWholeErr);
  EXPECT_EQ(j.log_offsets(), (Offsets{{"stdout", 43}, {"stderr", 22}}));
  EXPECT_FALSE(j.logs_failure().has_value());
  EXPECT_FALSE(j.can_retry_logs());
  EXPECT_EQ(non_log_requests(f), others);
  EXPECT_EQ(j.selected(), kLogTask);
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "failed");

  j.retry_logs(j.log_retry_generation()); /* complete: nothing to retry */
  drain(f);
  EXPECT_EQ(logs_subscribes(f).size(), 2u);
}

TEST_F(JobsFake, RefusedLogRetryKeepsTheTextAndOffersTheRetryAgain)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const Json refuse = {{"refuse", {{"code", "unavailable"}, {"message", "The Runtime cannot be reached"},
                                   {"retryable", true}}}};
  select_failed_task(f, Json::array({partial_then_final(), refuse, continuation()}));
  ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));
  const auto others = non_log_requests(f);
  const auto first_failure = j.log_retry_generation();

  j.retry_logs(first_failure);
  ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));
  EXPECT_EQ(logs_subscribes(f).size(), 2u);
  EXPECT_EQ(j.logs_failure()->message, "The Runtime cannot be reached");
  EXPECT_EQ(log_text(j.log_all()), kPartialAll);
  EXPECT_EQ(log_text(j.log_stdout()), kPartialOut);
  EXPECT_EQ(log_text(j.log_stderr()), kPartialErr);
  EXPECT_EQ(j.log_offsets(), (Offsets{{"stdout", 25}, {"stderr", 12}}));
  ASSERT_TRUE(j.can_retry_logs());
  ASSERT_NE(j.log_retry_generation(), first_failure);
  j.retry_logs(first_failure); // A cached action cannot retry a newer failure.
  drain(f);
  ASSERT_EQ(logs_subscribes(f).size(), 2u);

  j.retry_logs(j.log_retry_generation());
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));
  const std::vector<Json> subs = logs_subscribes(f);
  ASSERT_EQ(subs.size(), 3u);
  EXPECT_EQ(subs[1].at("offsets").get<Offsets>(), (Offsets{{"stdout", 25}, {"stderr", 12}}));
  EXPECT_EQ(subs[2].at("offsets").get<Offsets>(), (Offsets{{"stdout", 25}, {"stderr", 12}}));
  EXPECT_EQ(log_text(j.log_all()), kWholeAll);
  EXPECT_EQ(log_text(j.log_stdout()), kWholeOut);
  EXPECT_EQ(log_text(j.log_stderr()), kWholeErr);
  EXPECT_EQ(non_log_requests(f), others);
}

TEST_F(JobsFake, NonFinalAndUnretryableLogErrorsOfferNoRetry)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  /* Non-final: the bridge keeps polling the same subscription; nothing is shown as stopped. */
  const Json non_final = {
      {"id", "nf"},
      {"chunks", Json::array({log_chunk("stdout", "开始 α\n第1步 能", 0, 21)})},
      {"error", {{"code", "unavailable"}, {"message", "The Runtime cannot be reached"}, {"retryable", true},
                 {"final", false}}},
      {"resume", "nf-resume"},
      {"after", Json::array({log_chunk("stdout", "量\n", 21, 25)})},
      {"end", true}};
  select_failed_task(f, Json::array({non_final, partial_then_final("unauthorized", false)}),
                     {kLogTask, kOtherLogTask});
  ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/logs-nf-error"); }));
  drain(f);
  EXPECT_FALSE(j.logs_failure().has_value());
  EXPECT_FALSE(j.can_retry_logs());
  EXPECT_FALSE(j.logs_ended());
  touch(f, "nf-resume");
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));
  EXPECT_EQ(log_text(j.log_all()), "开始 α\n第1步 能量\n");
  EXPECT_FALSE(j.logs_failure().has_value());
  EXPECT_FALSE(j.can_retry_logs());
  EXPECT_EQ(logs_subscribes(f).size(), 1u);

  /* A final, non-retryable refusal (the credential): stopped, but no retry is offered or sent. */
  j.select_task(kOtherLogTask);
  ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));
  EXPECT_EQ(j.logs_failure()->code, bridge::ErrorCode::Unauthorized);
  EXPECT_FALSE(j.logs_failure()->retryable);
  EXPECT_FALSE(j.can_retry_logs());
  EXPECT_EQ(log_text(j.log_all()), kPartialAll);
  j.retry_logs(j.log_retry_generation());
  drain(f);
  EXPECT_EQ(logs_subscribes(f).size(), 2u);
  EXPECT_TRUE(j.logs_failure().has_value());
}

TEST_F(JobsFake, LateLogRetryOfAnOldTaskChangesNothing)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  Json late = continuation();
  late["id"] = "late";
  late["hold"] = "release-late";
  const Json other = {{"chunks", Json::array({log_chunk("stdout", "任务二\n", 0, 10)})}, {"end", true}};
  select_failed_task(f, Json::array({partial_then_final(), late, other}), {kLogTask, kOtherLogTask});
  ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));
  j.retry_logs(j.log_retry_generation());
  ASSERT_TRUE(f.pump([&] { return logs_subscribes(f).size() == 2u; }));

  /* Another task while the retry is unanswered: its receipt must not reach the new task. */
  j.select_task(kOtherLogTask);
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));
  touch(f, "release-late");
  ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/logs-late-done"); }));
  drain(f);
  EXPECT_EQ(j.selected(), kOtherLogTask);
  EXPECT_EQ(log_text(j.log_all()), "任务二\n");
  EXPECT_EQ(log_text(j.log_stdout()), "任务二\n");
  EXPECT_EQ(j.log_stderr().line_count(), 0u);
  EXPECT_EQ(j.log_offsets(), (Offsets{{"stdout", 10}}));
  EXPECT_FALSE(j.logs_failure().has_value());
  EXPECT_FALSE(j.can_retry_logs());

  /* Back to the first task: a fresh read from the start, without its old offsets or half lines. */
  j.select_task(kLogTask);
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));
  const std::vector<Json> subs = logs_subscribes(f);
  ASSERT_EQ(subs.size(), 4u);
  EXPECT_FALSE(subs[3].contains("offsets")) << subs[3].dump();
  const std::string all = log_text(j.log_all());
  EXPECT_NE(all.find("开始计算 333333"), std::string::npos) << all;
  EXPECT_EQ(all.find("第1步 能量" STK_FFFD), std::string::npos) << all;
  EXPECT_EQ(all.find("任务二"), std::string::npos) << all;
}

TEST_F(JobsFake, ScopeRevocationAndBridgeChangesDropTheLogRetry)
{
  {
    SCOPED_TRACE("revoked node");
    FakeJobs f;
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("hub:mesh"));
    const std::string node = j.node();
    select_failed_task(f, Json::array({partial_then_final(), continuation()}));
    ASSERT_TRUE(f.pump([&] {
      const auto requests = non_log_requests(f);
      return j.logs_failure().has_value() && requests.at("task.get") == 1 && requests.at("task.artifacts") == 1;
    }));
    ASSERT_TRUE(j.can_retry_logs());
    const auto others = non_log_requests(f);
    j.apply_nodes(Json::array({{{"id", node}, {"role", "node"}, {"revoked", 1}}}));
    EXPECT_EQ(j.selected_task_observation(), app::TaskObservation::Denied);
    EXPECT_FALSE(j.logs_failure().has_value());
    EXPECT_FALSE(j.can_retry_logs());
    EXPECT_EQ(j.log_all().line_count(), 0u);
    j.retry_logs(j.log_retry_generation());
    drain(f);
    EXPECT_EQ(logs_subscribes(f).size(), 1u);
    EXPECT_EQ(non_log_requests(f), others);
  }
  for (const std::string_view change : {"workspace", "connection", "bridge"}) {
    SCOPED_TRACE(change);
    FakeJobs f;
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("runtime:lab"));
    select_failed_task(f, Json::array({partial_then_final(), continuation()}));
    ASSERT_TRUE(f.pump([&] { return j.logs_failure().has_value(); }));
    if (change == "workspace") {
      j.select_workspace("");
    }
    else if (change == "connection") {
      j.select_connection("runtime:lab");
    }
    else {
      j.attach(nullptr);
    }
    EXPECT_FALSE(j.logs_failure().has_value());
    EXPECT_FALSE(j.can_retry_logs());
    j.retry_logs(j.log_retry_generation());
    drain(f);
    EXPECT_EQ(logs_subscribes(f).size(), 1u);
  }
}

TEST_F(JobsFake, ConnectsChecksHealthAndWatchesTheWorkspace)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.pump([&] { return j.ready() && j.connections().size() == 3; }));
  EXPECT_TRUE(f.store.connection().empty());
  ASSERT_TRUE(f.connect("runtime:lab"));
  ASSERT_TRUE(f.pump([&] { return j.active() && j.active()->health == app::Health::Online; }));
  EXPECT_EQ(j.workspace(), "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0");
  EXPECT_NE(f.store.connection().find("lab"), std::string::npos) << f.store.connection();
  EXPECT_NE(f.store.connection().find("connected"), std::string::npos) << f.store.connection();
  /* An unreachable connection is shown offline with the bridge's reason. */
  j.check_connection("runtime:lab");
  j.apply_connections({bridge::ConnectionInfo::from_json(Json{{"id", "runtime:lab"}, {"kind", "runtime"}, {"name", "lab"}}),
                       bridge::ConnectionInfo::from_json(Json{{"id", "runtime:down"}, {"kind", "runtime"}, {"name", "down"}})});
  j.check_connection("runtime:down");
  ASSERT_TRUE(f.pump([&] {
    for (const app::ConnectionRow &c : j.connections()) {
      if (c.info.id == "runtime:down") {
        return c.health == app::Health::Offline && !c.detail.empty();
      }
    }
    return false;
  }));
  EXPECT_TRUE(has(f.methods(), "watch"));
}

TEST_F(JobsFake, SelectedHubTaskKeepsLastKnownFactOutsideHeartbeatWindow)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string task = "22222222222222222222222222222222";
  j.apply_snapshot(Json::array({{{"id", task}, {"name", "original task"}, {"state", "running"},
                                 {"workspace_id", j.workspace()}}}), 100.0);
  j.select_task(task);
  j.apply_snapshot(Json::array(), 101.0);

  EXPECT_TRUE(j.tasks().empty());
  EXPECT_EQ(j.selected(), task);
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "running");
  EXPECT_EQ(j.selected_task()->name, "original task");
}

TEST_F(JobsFake, TaskResultRequestExpiresDuringWorkspaceCreation)
{
  FakeJobs f;
  auto &jobs = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const std::string task(32, 'c');
  jobs.select_task(task);
  const auto request = jobs.selected_result_request();
  ASSERT_TRUE(request);
  ASSERT_TRUE(request->still_current());

  bool checked = false;
  jobs.create_workspace("Next workspace", [&](const auto &error) {
    EXPECT_FALSE(error);
    // Observe the creation callback after it clears the old scope, before its list reply.
    f.loop.executor()([&] {
      EXPECT_TRUE(jobs.workspace().empty());
      EXPECT_EQ(jobs.selected(), task);
      EXPECT_FALSE(request->still_current());
      EXPECT_FALSE(jobs.can_open_selected_result());
      checked = true;
    });
  });
  ASSERT_TRUE(f.pump([&] { return checked; }));
}

TEST_F(JobsFake, ExactHubObservationRecoversOriginalTaskAndClearsDeniedFacts)
{
  using app::TaskObservation;
  FakeJobs f({"--f03"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  ASSERT_EQ(j.tasks().size(), 1u);
  const std::string original = fake_jobs::kF03Task;
  const auto phase = [&](const char *value) {
    set_f03_phase(f, value);
  };
  const auto wait_for = [&](TaskObservation wanted) {
    return f.pump([&] { return j.selected_task_observation() == wanted; });
  };
  j.select_task(original);
  ASSERT_TRUE(wait_for(TaskObservation::Verified));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "running");

  phase("offline");
  ASSERT_TRUE(f.pump([&] { return j.tasks().empty(); }));
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Unavailable));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "running");
  const std::string workspace = j.workspace();
  j.apply_workspaces(Json::array({{{"id", "different workspace"}, {"name", "another workspace"}}}));
  EXPECT_EQ(j.workspace(), workspace);
  EXPECT_EQ(j.selected(), original);

  phase("unsupported");
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Unsupported));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "running");

  phase("wrong-workspace");
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Unconfirmed));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->workspace_id, j.workspace());

  phase("recovered");
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Verified));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected(), original);
  EXPECT_EQ(j.selected_task()->id, original);
  EXPECT_EQ(j.selected_task()->state, "succeeded");
  EXPECT_TRUE(j.tasks().empty());
  j.apply_snapshot(Json::array({{{"id", original}, {"state", "running"}, {"workspace_id", j.workspace()}}}), 123.0);
  EXPECT_EQ(j.selected_task()->state, "succeeded");

  phase("denied");
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Denied));
  EXPECT_EQ(j.selected_task(), nullptr);
  j.open_in_viewer();
  EXPECT_FALSE(f.store.has_open_result());
  j.apply_snapshot(Json::array({{{"id", original}, {"state", "running"}, {"workspace_id", j.workspace()}}}), 124.0);
  EXPECT_EQ(j.selected_task(), nullptr);
  EXPECT_TRUE(j.tasks().empty());

  phase("recovered");
  j.refresh_tasks();
  ASSERT_TRUE(wait_for(TaskObservation::Verified));
  j.apply_nodes(Json::array({{{"id", j.node()}, {"name", "original node"}, {"role", "node"}, {"revoked", 1}}}));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Denied);
  EXPECT_EQ(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected(), original);
  j.apply_nodes(Json::array({{{"id", j.node()}, {"name", "original node"}, {"role", "node"}, {"online", true}}}));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Denied);
  j.apply_snapshot(Json::array({{{"id", original}, {"state", "running"}, {"workspace_id", j.workspace()}}}), 125.0);
  EXPECT_EQ(j.selected_task(), nullptr);
  EXPECT_TRUE(j.tasks().empty());

  j.refresh_tasks();
  j.select_connection("runtime:lab");
  f.settle(0.25);
  EXPECT_TRUE(j.selected().empty());
  EXPECT_EQ(j.selected_task(), nullptr);
  const auto methods = f.methods();
  EXPECT_FALSE(has(methods, "task.submit"));
  EXPECT_FALSE(has(methods, "task.cancel"));
}

TEST_F(JobsFake, NewerTerminalHeartbeatOutranksAnExactReplyAlreadyInFlight)
{
  using app::TaskObservation;
  for (const char *late : {"hold-running", "hold-unavailable"}) {
    SCOPED_TRACE(late);
    FakeJobs f({"--f03"});
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("hub:mesh"));
    j.select_task(fake_jobs::kF03Task);
    ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified; }));
    ASSERT_EQ(j.selected_task()->state, "running");
    set_f03_phase(f, late);
    j.refresh_tasks();
    ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/f03-held"); }, 3));
    set_f03_phase(f, "terminal");
    ASSERT_TRUE(f.pump([&] { return !j.tasks().empty() && j.tasks().front().terminal(); }, 3));
    EXPECT_TRUE(f.pump([&] {
      return j.selected_task() && j.selected_task()->terminal() &&
             j.selected_task_observation() == TaskObservation::Verified;
    }, 3));
    std::ofstream(f.jobs_dir() + "/f03-release") << "release\n";
    ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/f03-replied"); }, 3));
    f.settle(0.15);
    ASSERT_NE(j.selected_task(), nullptr);
    EXPECT_EQ(j.selected_task()->state, "succeeded");
    EXPECT_EQ(j.selected_task_observation(), TaskObservation::Verified);
  }
}

TEST_F(JobsFake, CancelConfirmationCannotDispatchForChangedScopeOrIneligibleTask)
{
  for (const char *change : {"terminal", "denied", "scope", "selection"}) {
    SCOPED_TRACE(change);
    FakeJobs f({"--f03"});
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("hub:mesh"));
    j.select_task(fake_jobs::kF03Task);
    ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == app::TaskObservation::Verified; }));
    const auto confirmation = j.confirm_selected_task_cancel();
    ASSERT_TRUE(confirmation);
    if (std::string_view(change) == "terminal") {
      set_f03_phase(f, "terminal");
      ASSERT_TRUE(f.pump([&] { return !j.tasks().empty() && j.tasks().front().terminal(); }, 3));
    }
    else if (std::string_view(change) == "denied") {
      j.apply_nodes(Json::array({{{"id", j.node()}, {"role", "node"}, {"revoked", 1}}}));
      ASSERT_EQ(j.selected_task_observation(), app::TaskObservation::Denied);
    }
    else if (std::string_view(change) == "scope") {
      ASSERT_TRUE(f.connect("runtime:lab"));
    }
    else {
      j.select_task("");
      j.select_task(fake_jobs::kF03Task);
      ASSERT_TRUE(f.pump([&] { return j.can_cancel_selected_task(); }));
    }
    EXPECT_FALSE(j.can_cancel_task(*confirmation));
    j.cancel_task(*confirmation);
    f.settle(0.15);
    EXPECT_FALSE(has(f.methods(), "task.cancel"));
  }
}

TEST_F(JobsFake, ReattachingBridgeDiscardsOldTaskListCallback)
{
  FakeJobs replacement({"--f03"});
  ASSERT_TRUE(replacement.pump([&] { return replacement.jobs().ready(); }));
  set_f03_phase(replacement, "terminal");
  FakeJobs old({"--f03"});
  JobsState &j = old.jobs();
  ASSERT_TRUE(old.connect("hub:mesh"));
  ASSERT_EQ(j.tasks().size(), 1u);
  const auto before = old.methods();
  j.refresh_tasks();
  old.store.set_bridge(replacement.client.get());
  j.attach(replacement.client.get());
  ASSERT_TRUE(j.tasks().empty());
  ASSERT_TRUE(old.pump([&] {
    const auto methods = old.methods();
    return std::count(methods.begin(), methods.end(), "task.list") >
           std::count(before.begin(), before.end(), "task.list");
  }, 3));
  old.settle(0.15);
  EXPECT_TRUE(j.tasks().empty());

  j.refresh_tasks();
  ASSERT_TRUE(replacement.pump([&] { return j.tasks().size() == 1u && j.tasks().front().terminal(); }, 3));
  j.select_task(fake_jobs::kF03Task);
  ASSERT_TRUE(replacement.pump([&] {
    return j.selected_task_observation() == app::TaskObservation::Verified;
  }, 3));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "succeeded");
  EXPECT_EQ(j.active_id(), "hub:mesh");
  ASSERT_EQ(j.nodes().size(), 1u);
  EXPECT_EQ(j.nodes().front().id, j.node());
  set_f03_phase(replacement, "listed");
  ASSERT_TRUE(replacement.pump([&] { return j.tasks().size() == 1u && j.tasks().front().state == "running"; }, 3));
  EXPECT_EQ(j.selected_task()->state, "succeeded");
}

TEST_F(JobsFake, CancelConfirmationExpiresAcrossBridgeProcessRestart)
{
  using app::TaskObservation;
  FakeJobs f({"--f03"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  j.select_task(fake_jobs::kF03Task);
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified; }));
  const auto confirmation = j.confirm_selected_task_cancel();
  ASSERT_TRUE(confirmation);

  set_f03_phase(f, "hold-running");
  const int64_t pid = f.client->bridge_pid();
  bridge::test::kill_hard(pid);
  ASSERT_TRUE(f.pump([&] {
    return j.ready() && f.client->bridge_pid() != pid && j.selected_task_observation() == TaskObservation::Checking &&
           std::filesystem::exists(f.jobs_dir() + "/f03-held");
  }, 4));
  ASSERT_FALSE(j.tasks().empty()); // Replay returns the same cached running row while exact verification waits.
  EXPECT_FALSE(j.can_cancel_selected_task());
  EXPECT_FALSE(j.can_cancel_task(*confirmation));
  j.cancel_task(*confirmation);

  std::ofstream(f.jobs_dir() + "/f03-release") << "release\n";
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified; }, 3));
  EXPECT_TRUE(j.can_cancel_selected_task());
  EXPECT_FALSE(j.can_cancel_task(*confirmation));
  EXPECT_FALSE(has(f.methods(), "task.cancel"));
}

TEST_F(JobsFake, UnrevokedNodeWithoutSelectionGetsFreshTaskList)
{
  using app::TaskObservation;
  FakeJobs f({"--f03"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string node = j.node(), workspace = j.workspace();
  ASSERT_TRUE(j.selected().empty());
  ASSERT_EQ(j.tasks().size(), 1u);
  j.apply_nodes(Json::array({{{"id", node}, {"role", "node"}, {"revoked", true}}}));
  ASSERT_EQ(j.selected_task_observation(), TaskObservation::Denied);
  EXPECT_TRUE(j.tasks().empty());
  j.apply_nodes(Json::array({{{"id", node}, {"role", "node"}, {"online", true}, {"revoked", false}}}));
  ASSERT_TRUE(f.pump([&] { return j.tasks().size() == 1u; }, 3));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Snapshot);
  EXPECT_EQ(j.node(), node);
  EXPECT_EQ(j.workspace(), workspace);
  EXPECT_TRUE(j.selected().empty());
  EXPECT_EQ(j.tasks().front().id, fake_jobs::kF03Task);

  set_f03_phase(f, "deny-list");
  j.refresh_tasks();
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Denied; }, 3));
  EXPECT_TRUE(j.tasks().empty());
  const auto before_refresh = f.methods();
  set_f03_phase(f, "listed");
  j.refresh_tasks(); // Both fixture phases leave the device list unchanged and emit no devices.changed.
  ASSERT_TRUE(f.pump([&] { return j.tasks().size() == 1u; }, 3));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Snapshot);
  EXPECT_EQ(j.node(), node);
  EXPECT_EQ(j.workspace(), workspace);
  EXPECT_TRUE(j.selected().empty());

  set_f03_phase(f, "terminal");
  ASSERT_TRUE(f.pump([&] { return j.tasks().size() == 1u && j.tasks().front().terminal(); }, 3));
  EXPECT_TRUE(j.selected().empty()); // The restored subscription delivered the later change.
  const auto after_watch = f.methods();
  for (const std::string method : {"hub.devices", "task.list", "watch"}) {
    EXPECT_EQ(std::count(after_watch.begin(), after_watch.end(), method),
              std::count(before_refresh.begin(), before_refresh.end(), method) + 1) << method;
  }
}

TEST_F(JobsFake, LegacyHubCanCancelOnlyWithAnEligibleHeartbeatRow)
{
  FakeJobs f({"--f03"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  set_f03_phase(f, "unsupported-listed");
  j.select_task(fake_jobs::kF03Task);
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == app::TaskObservation::Unsupported; }));
  const auto confirmation = j.confirm_selected_task_cancel();
  ASSERT_TRUE(confirmation);

  set_f03_phase(f, "unsupported");
  ASSERT_TRUE(f.pump([&] { return j.tasks().empty(); }));
  EXPECT_FALSE(j.can_cancel_task(*confirmation));
  j.cancel_task(*confirmation);
  EXPECT_FALSE(has(f.methods(), "task.cancel"));

  set_f03_phase(f, "node-offline");
  ASSERT_TRUE(f.pump([&] { return !j.tasks().empty() && !j.nodes().empty() && !j.nodes().front().online; }));
  EXPECT_FALSE(j.can_cancel_task(*confirmation));
  j.cancel_task(*confirmation);
  EXPECT_FALSE(has(f.methods(), "task.cancel"));

  set_f03_phase(f, "unsupported-listed");
  ASSERT_TRUE(f.pump([&] { return !j.nodes().empty() && j.nodes().front().online; }));
  j.refresh_tasks();
  ASSERT_TRUE(f.pump([&] { return j.can_cancel_selected_task(); }));
  const auto eligible = j.confirm_selected_task_cancel();
  ASSERT_TRUE(eligible);
  j.cancel_task(*eligible);
  ASSERT_TRUE(f.pump([&] { return has(f.methods(), "task.cancel"); }));
  const auto methods = f.methods();
  EXPECT_EQ(std::count(methods.begin(), methods.end(), "task.cancel"), 1);
}

TEST_F(JobsFake, FilteredRevocationClearsTheOriginalNodeFactAndDetails)
{
  using app::TaskObservation;
  FakeJobs f({"--f03"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string node = j.node(), workspace = j.workspace();
  j.select_task(fake_jobs::kF03Task);
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified && j.logs_ended(); }));
  const auto confirmation = j.confirm_selected_task_cancel();
  ASSERT_TRUE(confirmation);
  ASSERT_GT(j.log_all().line_count(), 0u);
  j.apply_artifacts({bridge::FileEntry{"out.txt", std::string(64, 'a'), "text/plain", 1}});
  ASSERT_FALSE(j.artifacts().empty());

  set_f03_phase(f, "hold-running");
  j.refresh_tasks();
  ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/f03-held"); }, 3));
  set_f03_phase(f, "node-offline");
  ASSERT_TRUE(f.pump([&] { return j.nodes().size() == 1u && j.nodes().front().id == node && !j.nodes().front().online; }));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Unavailable);
  std::ofstream(f.jobs_dir() + "/f03-release") << "release\n";
  ASSERT_TRUE(f.pump([&] { return std::filesystem::exists(f.jobs_dir() + "/f03-replied"); }, 3));
  f.settle(0.1);
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Unavailable);
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "running");
  EXPECT_GT(j.log_all().line_count(), 0u);
  EXPECT_FALSE(j.artifacts().empty());
  EXPECT_FALSE(j.can_cancel_task(*confirmation));
  j.cancel_task(*confirmation);
  EXPECT_FALSE(has(f.methods(), "task.cancel"));

  set_f03_phase(f, "listed");
  ASSERT_TRUE(f.pump([&] { return j.nodes().size() == 1u && j.nodes().front().id == node && j.nodes().front().online; }));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Unavailable);
  j.refresh_tasks();
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified; }));

  set_f03_phase(f, "filtered");
  ASSERT_TRUE(f.pump([&] { return j.nodes().size() == 1u && j.nodes().front().id == "node2"; }));
  EXPECT_EQ(j.node(), node);
  EXPECT_EQ(j.workspace(), workspace);
  EXPECT_EQ(j.selected(), fake_jobs::kF03Task);
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Denied);
  EXPECT_EQ(j.selected_task(), nullptr);
  EXPECT_TRUE(j.tasks().empty());
  EXPECT_EQ(j.log_all().line_count(), 0u);
  EXPECT_TRUE(j.artifacts().empty());
  const auto before = f.methods();
  j.refresh_artifacts();
  j.download_artifact("out.txt");
  f.settle(0.1);
  const auto after = f.methods();
  EXPECT_EQ(std::count(before.begin(), before.end(), "task.artifacts"),
            std::count(after.begin(), after.end(), "task.artifacts"));
  EXPECT_FALSE(has(after, "download.start"));

  set_f03_phase(f, "listed");
  ASSERT_TRUE(f.pump([&] { return j.nodes().size() == 1u && j.nodes().front().id == node; }));
  EXPECT_EQ(j.selected_task_observation(), TaskObservation::Denied);
  EXPECT_EQ(j.selected_task(), nullptr);
  j.refresh_tasks();
  ASSERT_TRUE(f.pump([&] { return j.selected_task_observation() == TaskObservation::Verified; }));
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->id, fake_jobs::kF03Task);
}

TEST_F(JobsFake, SubmitRunsStreamsLogsEventsAndListsArtifacts)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  /* Validation first: nothing is sent. */
  j.form().program = "";
  EXPECT_FALSE(j.submit());
  EXPECT_EQ(j.status().kind, ui::ToastKind::Error);
  EXPECT_FALSE(has(f.methods(), "task.submit"));
  j.form().program = "{python}";
  j.form().name = "铁电畴 300K";
  j.form().arguments = "-c 'print(1)'";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.submission() && j.submission()->state == SubmitState::Done; }));
  const std::string id = j.submission()->task_id;
  EXPECT_EQ(j.submission()->key.size(), 32u);
  EXPECT_EQ(j.selected(), id); /* the new task is selected */
  /* The watch shows it and its state progresses (snapshots replace the list). */
  ASSERT_TRUE(f.pump([&] { return task_named(j, "铁电畴 300K") != nullptr; }));
  ASSERT_TRUE(f.pump([&] {
    const app::TaskRow *t = task_named(j, "铁电畴 300K");
    return t && t->state == "succeeded";
  }));
  /* Logs: both streams, stderr lines marked in the combined view; complete at the end. */
  ASSERT_TRUE(f.pump([&] { return j.logs_ended(); }));
  const std::string all = log_text(j.log_all());
  EXPECT_NE(all.find("第1步 能量 −1.5e-3"), std::string::npos) << all;
  EXPECT_NE(all.find("[stderr] 警告：网格较粗"), std::string::npos) << all;
  EXPECT_EQ(log_text(j.log_stderr()).find("[stderr]"), std::string::npos);
  EXPECT_NE(log_text(j.log_stdout()).find("完成"), std::string::npos);
  /* Monitoring summary. */
  ASSERT_TRUE(f.pump([&] { return j.events().ended; }));
  EXPECT_EQ(j.events().app, "muFerro");
  ASSERT_TRUE(j.events().fraction.has_value());
  EXPECT_DOUBLE_EQ(*j.events().fraction, 1.0);
  EXPECT_EQ(j.events().frames, 1);
  EXPECT_EQ(j.events().warnings, 1);
  EXPECT_EQ(j.events().completed, "succeeded");
  EXPECT_EQ(j.events().metrics.at("total_energy"), "-0.0015");
  /* Artifacts are listed once the task finished. */
  ASSERT_TRUE(f.pump([&] { return j.artifacts().size() == 2; }));
  EXPECT_EQ(j.artifacts()[0].file.path, "result.png");
}

TEST_F(JobsFake, AutomaticRetryReusesTheIdempotencyKey)
{
  FakeJobs f({"--submit-fail", "2"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().retry.auto_retries = 2;
  j.form().retry.backoff_s = 0.0;
  j.form().name = "retry";
  ASSERT_TRUE(j.submit());
  const std::string key = j.submission()->key;
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
  EXPECT_EQ(j.submission()->attempts, 3);
  EXPECT_EQ(j.submission()->key, key);
  const std::vector<std::string> m = f.methods();
  EXPECT_EQ(std::count(m.begin(), m.end(), "task.submit"), 3);
  f.settle(0.3);
  int named = 0;
  for (const app::TaskRow &t : j.tasks()) {
    named += t.name == "retry";
  }
  EXPECT_EQ(named, 1);
}

TEST_F(JobsFake, ManualRetryAfterAFailedSubmission)
{
  FakeJobs f({"--submit-fail", "1"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().retry.auto_retries = 0;
  j.form().name = "manual";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Failed; }));
  EXPECT_EQ(j.submission()->error->code, bridge::ErrorCode::Unavailable);
  EXPECT_NE(j.status().text.find("retry"), std::string::npos) << j.status().text;
  const std::string key = j.submission()->key;
  j.retry_submission();
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
  EXPECT_EQ(j.submission()->key, key);
  /* A new submit gets a new key. */
  j.form().name = "second";
  ASSERT_TRUE(j.submit());
  EXPECT_NE(j.submission()->key, key);
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
}

TEST_F(JobsFake, UploadsWaitForAWorkspaceThenCompleteAndBlockSubmitting)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  const std::filesystem::path folder = f.dir.path() / "case";
  std::filesystem::create_directories(folder / "sub");
  std::ofstream(folder / "input.toml") << "x = 1\n";
  std::ofstream(folder / "sub" / "b.txt") << "乙\n";
  const std::string file = (f.dir.path() / "单个.dat").string();
  std::ofstream(file) << "0123456789";
  ASSERT_TRUE(f.pump([&] { return j.ready(); }));
  j.upload({folder.string(), file});
  EXPECT_EQ(j.pending_uploads().size(), 2u); /* no workspace yet */
  ASSERT_TRUE(f.connect("runtime:lab"));
  /* Choosing the workspace started them. */
  ASSERT_TRUE(f.pump([&] { return j.pending_uploads().empty() && j.transfers().size() == 2; }));
  /* While they move, submitting waits. */
  if (j.uploads_in_flight() > 0) {
    EXPECT_FALSE(j.submit());
    EXPECT_EQ(j.status().kind, ui::ToastKind::Warning);
  }
  ASSERT_TRUE(f.pump([&] {
    return j.uploads_in_flight() == 0 && std::all_of(j.transfers().begin(), j.transfers().end(),
                                                     [](const bridge::Transfer &t) { return t.state == "completed"; });
  }));
  ASSERT_TRUE(f.pump([&] { return j.workspace_files().size() == 3; }));
  std::vector<std::string> paths;
  for (const bridge::FileEntry &e : j.workspace_files()) {
    paths.push_back(e.path);
  }
  /* A folder's contents land at the workspace root by default (the legacy tab's layout). */
  EXPECT_TRUE(has(paths, "input.toml"));
  EXPECT_TRUE(has(paths, "sub/b.txt"));
  EXPECT_TRUE(has(paths, "单个.dat"));
  /* Off: under the folder's name. */
  j.folder_into_root = false;
  j.upload({folder.string()});
  ASSERT_TRUE(f.pump([&] { return j.workspace_files().size() == 5; }));
  paths.clear();
  for (const bridge::FileEntry &e : j.workspace_files()) {
    paths.push_back(e.path);
  }
  EXPECT_TRUE(has(paths, "case/input.toml"));
  EXPECT_TRUE(has(paths, "case/sub/b.txt"));
  EXPECT_NE(j.status().text.find("Uploaded"), std::string::npos) << j.status().text;
}

TEST_F(JobsFake, DownloadIsVerifiedAndPngIsPreviewedAsATexture)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  int textures = 0, freed = 0;
  j.create_texture = [&](const io::Image &img) -> uint64_t {
    EXPECT_EQ(img.channels, 4u);
    return ++textures + 100;
  };
  j.free_texture = [&](uint64_t) { freed++; };
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().name = "png";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.artifacts().size() == 2; }));
  j.download_artifact("result.png");
  ASSERT_TRUE(f.pump([&] { return j.artifacts()[0].verify == app::ArtifactRow::Verify::Ok; }));
  const app::ArtifactRow &a = j.artifacts()[0];
  EXPECT_TRUE(std::filesystem::exists(a.local)) << a.local;
  EXPECT_EQ(j.preview().width, 64);
  EXPECT_EQ(j.preview().height, 48);
  EXPECT_EQ(j.preview().texture, 101u);
  EXPECT_TRUE(j.preview().error.empty());
  /* Save as: an explicit destination. */
  const std::string dest = (f.dir.path() / "保存" / "summary.txt").string();
  j.download_artifact("out/summary.txt", dest);
  ASSERT_TRUE(f.pump([&] { return j.artifacts()[1].verify == app::ArtifactRow::Verify::Ok; }));
  EXPECT_EQ(j.artifacts()[1].local, dest);
  EXPECT_TRUE(std::filesystem::exists(dest));
  EXPECT_TRUE(f.opened.empty()); /* "Save as" does not open; a PNG is previewed instead */
  /* Open in viewer raises the request for the Viewer editor. */
  j.open_in_viewer();
  ASSERT_TRUE(f.store.has_open_result());
  const auto req = f.store.take_open_result();
  EXPECT_EQ(req->connection, "runtime:lab");
  EXPECT_EQ(req->task_id, j.selected());
  EXPECT_EQ(req->workspace_id, j.workspace());
  /* Previews are released with the selection. */
  j.select_task("");
  EXPECT_EQ(freed, textures);
}

TEST_F(JobsFake, CompletedTransfersKeepTheirStateAndOwnershipWhenStartRepliesArriveLate)
{
  FakeJobs f({"--late-transfer-start"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const auto drain = [&] {
    bool received = false;
    /* This read uses the same executor without adopting its snapshot in JobsState. */
    f.client->transfer_list().then([&](const auto &reply) {
      EXPECT_TRUE(reply);
      received = true;
    });
    ASSERT_TRUE(f.pump([&] { return received; }));
  };
  const auto workspace_reads = [&] {
    const auto methods = f.methods();
    return std::count(methods.begin(), methods.end(), "workspace.files");
  };
  ASSERT_NO_FATAL_FAILURE(drain());
  const auto before_upload = workspace_reads();
  const std::string source = (f.dir.path() / "input.txt").string();
  std::ofstream(source) << "synthetic input";
  j.upload({source});
  ASSERT_NO_FATAL_FAILURE(drain());
  ASSERT_TRUE(f.pump([&] { return j.workspace_files().size() == 1; }));
  ASSERT_EQ(j.transfers().size(), 1u);
  EXPECT_EQ(j.transfers()[0].state, "completed");
  EXPECT_EQ(j.uploads_in_flight(), 0);
  EXPECT_EQ(workspace_reads(), before_upload + 1);
  EXPECT_NE(j.status().text.find("Uploaded"), std::string::npos);

  const std::string dest = (f.dir.path() / "downloaded.txt").string();
  j.download_input("input.txt", dest);
  ASSERT_NO_FATAL_FAILURE(drain());
  EXPECT_EQ(f.opened, (std::vector<std::string>{dest}));

  int previews = 0;
  j.create_texture = [&](const io::Image &) -> uint64_t { return ++previews; };
  j.free_texture = [](uint64_t) {};
  j.form().name = "completed upload no longer blocks submission";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.artifacts().size() == 2; }));
  j.download_artifact("result.png");
  ASSERT_NO_FATAL_FAILURE(drain());
  ASSERT_EQ(j.transfers().size(), 3u);
  EXPECT_TRUE(std::all_of(j.transfers().begin(), j.transfers().end(),
                          [](const bridge::Transfer &t) { return t.state == "completed"; }));
  EXPECT_EQ(j.artifacts()[0].verify, app::ArtifactRow::Verify::Ok);
  EXPECT_EQ(j.preview().texture, 1u);
  EXPECT_EQ(previews, 1);
  EXPECT_EQ(f.opened, (std::vector<std::string>{dest}));
}

TEST_F(JobsFake, NewerArtifactSaveKeepsItsRowAndPreviewAfterAnOlderStartReply)
{
  for (const bool first_fails : {false, true}) {
    SCOPED_TRACE(first_fails);
    FakeJobs f({"--late-transfer-start", first_fails ? "--hold-artifact-start-error" : "--hold-artifact-start"});
    JobsState &j = f.jobs();
    int previews = 0;
    j.create_texture = [&](const io::Image &) -> uint64_t { return ++previews; };
    j.free_texture = [](uint64_t) {};
    ASSERT_TRUE(f.connect("runtime:lab"));
    const auto submit = [&](const std::string &name) {
      j.form().name = name;
      ASSERT_TRUE(j.submit());
      ASSERT_TRUE(f.pump([&] {
        const auto *task = task_named(j, name);
        return task && j.selected() == task->id && j.artifacts().size() == 2;
      }));
    };
    ASSERT_NO_FATAL_FAILURE(submit("first artifact task"));
    const std::string first = (f.dir.path() / "first.png").string();
    const std::string second = (f.dir.path() / "second.png").string();
    j.download_artifact("result.png", first);
    if (first_fails) {
      ASSERT_TRUE(f.pump([&] { return has(f.methods(), "download.start"); }));
      ASSERT_NO_FATAL_FAILURE(submit("second artifact task"));
    }
    else {
      ASSERT_TRUE(f.pump([&] { return j.transfers().size() == 1 && j.transfers()[0].state == "completed"; }));
    }
    EXPECT_EQ(previews, 0);
    j.download_artifact("result.png", second);
    ASSERT_TRUE(f.pump([&] {
      return j.artifacts()[0].local == second && j.artifacts()[0].verify == app::ArtifactRow::Verify::Ok;
    }));
    const auto second_id = j.artifacts()[0].transfer_id;
    ASSERT_NO_FATAL_FAILURE(release_artifact_start(f, second_id));
    EXPECT_EQ(j.artifacts()[0].transfer_id, second_id);
    EXPECT_EQ(j.artifacts()[0].local, second);
    EXPECT_EQ(j.artifacts()[0].verify, app::ArtifactRow::Verify::Ok);
    EXPECT_EQ(j.preview().path, second);
    EXPECT_EQ(previews, 1);
    EXPECT_TRUE(f.opened.empty());
    EXPECT_EQ(std::filesystem::exists(first), !first_fails);
    EXPECT_TRUE(std::filesystem::exists(second));
    EXPECT_EQ(j.transfers().size(), first_fails ? 1u : 2u);
    EXPECT_TRUE(std::all_of(j.transfers().begin(), j.transfers().end(),
                            [](const auto &t) { return t.state == "completed"; }));
  }
}

TEST_F(JobsFake, OpeningADetachedArtifactRechecksItsDownloadedBytes)
{
  for (const bool tamper : {false, true}) {
    SCOPED_TRACE(tamper);
    FakeJobs f({"--late-transfer-start", "--hold-artifact-start"});
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("runtime:lab"));
    j.form().name = "detached artifact";
    ASSERT_TRUE(j.submit());
    ASSERT_TRUE(f.pump([&] { return j.artifacts().size() == 2; }));
    j.download_artifact("out/summary.txt");
    ASSERT_TRUE(f.pump([&] { return j.transfers().size() == 1 && j.transfers()[0].state == "completed"; }));
    const auto id = j.transfers()[0].id;
    const auto local = j.transfers()[0].local;
    ASSERT_TRUE(std::filesystem::exists(local));
    ASSERT_TRUE(f.opened.empty());
    j.select_task("");
    ASSERT_TRUE(j.artifacts().empty());
    if (tamper) {
      std::fstream file(local, std::ios::binary | std::ios::in | std::ios::out);
      const int first = file.get();
      ASSERT_NE(first, std::char_traits<char>::eof());
      file.seekp(0);
      file.put(char(first ^ 1));
      ASSERT_TRUE(file.good());
    }
    ASSERT_NO_FATAL_FAILURE(release_artifact_start(f, id));
    ASSERT_NE(j.transfer(id), nullptr);
    EXPECT_EQ(j.transfer(id)->state, "completed");
    if (tamper) {
      EXPECT_TRUE(f.opened.empty());
      EXPECT_EQ(j.status().kind, ui::ToastKind::Error);
    }
    else {
      EXPECT_EQ(f.opened, (std::vector<std::string>{local}));
    }
  }
}

TEST_F(JobsFake, CancelShowsCancellingThenCancelled)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().name = "slow job";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] {
    const app::TaskRow *t = task_named(j, "slow job");
    return t && t->state == "running" && j.selected() == t->id;
  }));
  const auto confirmation = j.confirm_selected_task_cancel();
  ASSERT_TRUE(confirmation);
  j.cancel_task(*confirmation);
  ASSERT_TRUE(f.pump([&] {
    const app::TaskRow *t = task_named(j, "slow job");
    return t && t->state == "cancelled";
  }));
  EXPECT_TRUE(has(f.methods(), "task.cancel"));
}

TEST_F(JobsFake, ClosingTheAppNeverCancelsTasks)
{
  std::string model;
  std::string task_id;
  {
    FakeJobs f;
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("runtime:lab"));
    j.form().name = "slow overnight";
    ASSERT_TRUE(j.submit());
    ASSERT_TRUE(f.pump([&] {
      const app::TaskRow *t = task_named(j, "slow overnight");
      return t && t->state == "running";
    }));
    task_id = task_named(j, "slow overnight")->id;
    model = f.jobs_dir();
    /* Keep the directory: the fixture's TempDir goes with f, so copy what we need. */
    f.close(); /* EOF to the bridge, as when the window closes */
    const std::vector<std::string> m = f.methods();
    EXPECT_FALSE(has(m, "task.cancel"));
    EXPECT_FALSE(has(m, "transfer.cancel"));
    EXPECT_EQ(m.back(), "EOF"); /* a clean EOF, not a kill */
    std::ifstream in(model + "/model.json");
    const Json saved = io::parse_json(std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>()));
    bool found = false;
    for (const Json &t : saved["tasks"]) {
      if (t["id"] == task_id) {
        found = true;
        EXPECT_FALSE(t["cancel_requested"].get<bool>());
        EXPECT_NE(t["state"], "cancelled");
      }
    }
    EXPECT_TRUE(found);
  }
}

TEST_F(JobsFake, AddPairRemoveConnectionsAndTheLocalRuntime)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.pump([&] { return j.ready() && !j.connections().empty(); }));
  std::optional<bridge::Error> err;
  bool done = false;
  bridge::AddRuntimeParams p;
  p.name = "cluster";
  p.url = "http://127.0.0.1:19876";
  p.token = "secret-token";
  j.add_runtime(p, [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(f.pump([&] { return done; }));
  EXPECT_FALSE(err.has_value());
  ASSERT_TRUE(f.pump([&] { return j.active_id() == "runtime:cluster" && j.active() != nullptr; }));
  /* A refused token: the dialog gets the error. */
  done = false;
  p.name = "bad";
  j.add_runtime(p, [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(f.pump([&] { return done; }));
  ASSERT_TRUE(err.has_value());
  EXPECT_EQ(err->code, bridge::ErrorCode::Unauthorized);
  /* Remove the active one. */
  done = false;
  j.remove_connection("runtime:cluster", [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(f.pump([&] { return done; }));
  EXPECT_FALSE(err.has_value());
  EXPECT_TRUE(j.active_id().empty());
  EXPECT_TRUE(f.store.connection().empty());
  ASSERT_TRUE(f.pump([&] {
    return std::none_of(j.connections().begin(), j.connections().end(),
                        [](const app::ConnectionRow &c) { return c.info.id == "runtime:cluster"; });
  }));
  /* Pair a hub. */
  done = false;
  j.pair_hub({"lab2", "https://hub2.example", "code-123", "STK Desktop"}, [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(f.pump([&] { return done && j.active_id() == "hub:lab2"; }));
  /* The local Runtime: stopped, then started from the editor. */
  ASSERT_TRUE(j.local_status().has_value());
  EXPECT_FALSE(j.local_status()->api_running);
  j.start_local();
  EXPECT_TRUE(j.local_busy());
  ASSERT_TRUE(f.pump([&] { return !j.local_busy() && j.local_status()->api_running; }));
  j.select_connection("local");
  ASSERT_TRUE(f.pump([&] { return j.active() && j.active()->health == app::Health::Online; }));
  EXPECT_TRUE(j.workspaces().empty()); /* a fresh local Runtime */
}

TEST_F(JobsFake, AnUninitializedLocalRuntimeIsListedAndSetUpOnStart)
{
  FakeJobs f({"--local-uninitialized"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.pump([&] { return j.ready() && !j.connections().empty() && j.local_status().has_value(); }));
  ASSERT_EQ(j.connections()[0].info.id, "local");
  EXPECT_EQ(j.connections()[0].info.state, "not_initialized");
  EXPECT_FALSE(j.local_status()->initialized);
  j.start_local(); /* sends initialize: true, as the legacy tab set the Runtime up on Connect */
  ASSERT_TRUE(f.pump([&] { return !j.local_busy(); }));
  EXPECT_TRUE(j.local_status()->initialized);
  EXPECT_TRUE(j.local_status()->api_running);
  ASSERT_TRUE(f.pump([&] { return j.connections()[0].info.state == "initialized"; }));
}

TEST_F(JobsFake, HubCustomSubmitGoesToReviewThenRunsAfterApproval)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  EXPECT_TRUE(j.hub());
  EXPECT_EQ(j.node(), "node1");
  ASSERT_TRUE(f.pump([&] { return !j.templates().empty() && j.policy().has_value(); }));
  EXPECT_EQ(j.templates().front(), "muferro-small");
  EXPECT_EQ(j.policy()->review_policy, "any");
  j.form().use_template = false;
  j.form().name = "custom";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Review; }));
  const std::string action = j.submission()->action->id;
  ASSERT_TRUE(f.pump([&] { return j.reviews().size() == 1; }));
  EXPECT_EQ(j.reviews()[0].kind, "task.submit"); /* from request.kind in the hub listing */
  EXPECT_FALSE(j.reviews()[0].inspected);
  /* Approving needs an inspection first. */
  j.review(action, true);
  EXPECT_NE(j.reviews()[0].message.find("Inspect"), std::string::npos) << j.reviews()[0].message;
  EXPECT_FALSE(has(f.methods(), "hub.review"));
  j.inspect(action);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  EXPECT_EQ(j.reviews()[0].request["kind"], "task.submit");
  j.review(action, true);
  /* The action leaves review, the same key is sent again and returns the task. */
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
  ASSERT_TRUE(f.pump([&] { return j.reviews().empty(); }));
  ASSERT_TRUE(f.pump([&] { return task_named(j, "custom") != nullptr; }));
  /* A template runs at once. */
  j.form().use_template = true;
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
}

TEST_F(JobsFake, ReviewPolicyRefusalIsExplained)
{
  FakeJobs f({"--review-refuse", "--review-policy", "not-self"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  ASSERT_TRUE(f.pump([&] { return j.policy().has_value(); }));
  j.form().name = "custom";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.reviews().size() == 1; }));
  const std::string action = j.reviews()[0].action.id;
  j.inspect(action);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  j.review(action, true);
  ASSERT_TRUE(f.pump([&] { return !j.reviews()[0].message.empty() && !j.reviews()[0].busy; }));
  const std::string msg = j.reviews()[0].message;
  EXPECT_NE(msg.find("review policy (not-self)"), std::string::npos) << msg;
  EXPECT_NE(msg.find("hub owner"), std::string::npos) << msg;
  EXPECT_EQ(j.status().kind, ui::ToastKind::Error);
  /* Still in review; rejecting is always allowed. */
  j.review(action, false);
  ASSERT_TRUE(f.pump([&] { return j.reviews().empty(); }));
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Failed; }));
}

TEST_F(JobsFake, AWorkspaceCreatedThroughAHubStaysSelectedWhileTheListingIsStale)
{
  /* Found by the D1 acceptance: a hub lists workspaces from the node's heartbeat snapshot, so the
   * new workspace was missing from the refresh after creating it and another one got selected. */
  FakeJobs f({"--stale-workspace-lists", "3"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string before = j.workspace();
  bool done = false;
  std::string adopted;
  int adoptions = 0;
  j.create_workspace("d1-accept", [&](const std::optional<bridge::Error> &e) {
    EXPECT_FALSE(e.has_value());
    done = true;
  }, [&] {
    adopted = j.workspace();
    ++adoptions;
  });
  ASSERT_TRUE(f.pump([&] { return done; }));
  std::string created;
  ASSERT_TRUE(f.pump([&] {
    for (const app::WorkspaceRow &w : j.workspaces()) {
      if (w.name == "d1-accept") {
        created = w.id;
      }
    }
    return !created.empty() && j.workspace() == created;
  }));
  EXPECT_NE(created, before);
  /* Once the snapshot lists it, it stays selected and appears exactly once. */
  ASSERT_TRUE(f.pump([&] {
    const auto log = f.methods();
    return std::count(log.begin(), log.end(), std::string("workspace.list")) >= 5;
  }));
  f.settle(0.2);
  EXPECT_EQ(j.workspace(), created);
  int seen = 0;
  for (const app::WorkspaceRow &w : j.workspaces()) {
    seen += w.id == created;
  }
  EXPECT_EQ(seen, 1);
  EXPECT_EQ(adopted, created);
  EXPECT_EQ(adoptions, 1);
}

TEST_F(JobsFake, WorkspaceCreationDoesNotAdoptAfterASelectionChange)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const std::string workspace = j.workspace();
  ASSERT_FALSE(workspace.empty());
  bool done = false;
  j.create_workspace("Late synthetic workspace", [&](const std::optional<bridge::Error> &e) {
    EXPECT_FALSE(e);
    done = true;
  }, [&] { ADD_FAILURE() << "A stale workspace creation must not be adopted"; });
  // The bridge reply is delivered by the manual loop. Restore the same ID before it is processed.
  j.select_workspace("");
  j.select_workspace(workspace);
  ASSERT_TRUE(f.pump([&] { return done; }));
  EXPECT_EQ(j.workspace(), workspace);
}

TEST_F(JobsFake, AProvisionalWorkspaceCannotFollowAnotherSelection)
{
  FakeJobs f({"--stale-workspace-lists", "10"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string workspace = j.workspace();
  const std::string created_name = "Hidden synthetic workspace";
  bool checked = false;
  j.create_workspace(created_name, [&](const std::optional<bridge::Error> &e) {
    EXPECT_FALSE(e);
    f.loop.executor()([&] {
      // The creation object arrived, but the workspace listing has not selected it yet.
      EXPECT_TRUE(j.workspace().empty());
      j.select_workspace(workspace);
      j.refresh_workspaces();
      f.client->call("connections.list").then([&](const auto &result) {
        EXPECT_TRUE(result);
        checked = true;
      });
    });
  }, [&] { ADD_FAILURE() << "The new selection must not adopt the previous creation"; });
  ASSERT_TRUE(f.pump([&] { return checked; }));
  EXPECT_EQ(j.workspace(), workspace);
  EXPECT_TRUE(std::none_of(j.workspaces().begin(), j.workspaces().end(),
                           [&](const auto &row) { return row.name == created_name; }));
}

TEST_F(JobsFake, ApprovalAfterABridgeRestartReadsTheActionAgain)
{
  FakeJobs f({"--forget-inspected-once"});
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  j.form().name = "custom";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.reviews().size() == 1; }));
  const std::string action = j.reviews()[0].action.id;
  j.inspect(action);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  /* The bridge answers review_not_inspected: the editor reads the action again and asks again. */
  j.review(action, true);
  ASSERT_TRUE(f.pump([&] {
    return !j.reviews().empty() && j.reviews()[0].inspected && !j.reviews()[0].busy &&
           j.reviews()[0].message.find("restarted") != std::string::npos;
  }));
  const std::vector<std::string> m = f.methods();
  EXPECT_EQ(std::count(m.begin(), m.end(), "hub.action"), 2);
  j.review(action, true);
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
}

TEST_F(JobsFake, BridgeRestartClearsInspectionsAndKeepsWatching)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  j.form().name = "custom";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return j.reviews().size() == 1; }));
  const std::string action = j.reviews()[0].action.id;
  j.inspect(action);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  const int64_t pid = f.client->bridge_pid();
  bridge::test::kill_hard(pid);
  ASSERT_TRUE(f.pump([&] { return j.ready() && f.client->bridge_pid() != pid; }));
  /* The new bridge process has read nothing: approving needs a new inspection. */
  ASSERT_TRUE(f.pump([&] { return !j.reviews().empty() && !j.reviews()[0].inspected; }));
  j.review(action, true);
  EXPECT_NE(j.reviews()[0].message.find("Inspect"), std::string::npos);
  j.inspect(action);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  j.review(action, true);
  ASSERT_TRUE(f.pump([&] { return j.submission()->state == SubmitState::Done; }));
  /* The watch was replayed: the approved task shows up. */
  ASSERT_TRUE(f.pump([&] { return task_named(j, "custom") != nullptr; }));
}

TEST_F(JobsFake, HubUploadWaitsForTheImportReview)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("hub:mesh"));
  const std::string file = (f.dir.path() / "输入.toml").string();
  std::ofstream(file) << "x = 1\n";
  j.upload({file});
  ASSERT_TRUE(f.pump([&] {
    return !j.transfers().empty() && j.transfers()[0].action && j.transfers()[0].action->in_review();
  }));
  const bridge::Transfer t = j.transfers()[0];
  EXPECT_EQ(t.state, "running");
  EXPECT_EQ(t.bytes_done, t.bytes_total);
  EXPECT_NE(j.status().text.find("review"), std::string::npos) << j.status().text;
  ASSERT_TRUE(f.pump([&] { return j.reviews().size() == 1; }));
  EXPECT_EQ(j.reviews()[0].kind, "workspace.import");
  j.inspect(t.action->id);
  ASSERT_TRUE(f.pump([&] { return j.reviews()[0].inspected; }));
  j.review(t.action->id, true);
  ASSERT_TRUE(f.pump([&] { return j.transfer(t.id) && j.transfer(t.id)->state == "completed"; }));
  ASSERT_TRUE(f.pump([&] { return j.workspace_files().size() == 1; }));
  /* A second upload is withdrawn with transfer.cancel (its import rejected). */
  j.upload({file});
  ASSERT_TRUE(f.pump([&] {
    return j.transfers().size() == 2 && j.transfers()[0].action && j.transfers()[0].action->in_review();
  }));
  j.cancel_transfer(j.transfers()[0].id);
  ASSERT_TRUE(f.pump([&] { return j.transfers()[0].state == "cancelled"; }));
}

TEST_F(JobsFake, InputFilesDownloadToAChosenDestination)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const std::string file = (f.dir.path() / "in.txt").string();
  std::ofstream(file) << "abc";
  j.upload({file});
  ASSERT_TRUE(f.pump([&] { return j.workspace_files().size() == 1; }));
  const std::string dest = (f.dir.path() / "back" / "in.txt").string();
  j.download_input("in.txt", dest);
  ASSERT_TRUE(f.pump([&] {
    return std::any_of(j.transfers().begin(), j.transfers().end(), [](const bridge::Transfer &t) {
      return t.kind == "download" && t.state == "completed";
    });
  }));
  EXPECT_TRUE(std::filesystem::exists(dest));
  EXPECT_NE(j.status().text.find(dest), std::string::npos);
  /* Opened once verified, as the legacy tab did. */
  ASSERT_EQ(f.opened.size(), 1u);
  EXPECT_EQ(f.opened[0], dest);
}

TEST_F(JobsFake, CompletedResumeOutranksLateResumeAndListSnapshots)
{
  for (const bool list_first : {false, true}) {
    SCOPED_TRACE(list_first);
    FakeJobs f({list_first ? "--completed-transfer-list-first" : "--late-transfer-snapshots"});
    JobsState &j = f.jobs();
    ASSERT_TRUE(f.connect("runtime:lab"));
    const std::string file = (f.dir.path() / "interrupted-upload.bin").string();
    std::ofstream(file) << "resume";
    j.upload({file});
    ASSERT_TRUE(f.pump([&] { return j.transfers().size() == 1 && j.transfers()[0].state == "interrupted"; }));
    const std::string id = j.transfers()[0].id;
    j.cancel_transfer(id);
    ASSERT_TRUE(f.pump([&] { return j.transfer(id) && j.transfer(id)->state == "cancelled"; }));

    const auto before = f.methods();
    const auto lists = std::count(before.begin(), before.end(), "transfer.list");
    const auto files = std::count(before.begin(), before.end(), "workspace.files");
    if (list_first) {
      j.resume_transfer(id);
      ASSERT_TRUE(f.pump([&] { return j.transfer(id) && j.transfer(id)->state == "running"; }));
      j.refresh_transfers();
      ASSERT_TRUE(f.pump([&] {
        return j.transfer(id) && j.transfer(id)->state == "completed" && j.workspace_files().size() == 1;
      }));
    }
    else {
      j.refresh_transfers();
      ASSERT_TRUE(f.pump([&] {
        const auto methods = f.methods();
        return std::count(methods.begin(), methods.end(), "transfer.list") == lists + 1;
      }));
      j.resume_transfer(id);
    }

    /* This reply follows the completed event and both snapshots on the same client. */
    bool received = false;
    f.client->transfer_get(id).then([&](const bridge::Result<bridge::Transfer> &reply) {
      EXPECT_TRUE(reply && reply.value().state == "completed");
      received = true;
    });
    ASSERT_TRUE(f.pump([&] { return received && j.workspace_files().size() == 1; }));
    ASSERT_EQ(j.transfers().size(), 1u);
    ASSERT_NE(j.transfer(id), nullptr);
    EXPECT_EQ(j.transfer(id)->state, "completed");
    EXPECT_EQ(j.transfer(id)->bytes_done, j.transfer(id)->bytes_total);
    const auto after = f.methods();
    EXPECT_EQ(std::count(after.begin(), after.end(), "workspace.files"), files + 1);
  }
}

TEST_F(JobsFake, SwitchingConnectionDropsStaleResults)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().name = "x";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] { return !j.tasks().empty(); }));
  /* Switch before anything else arrives: the lab's snapshots must not show up under the hub. */
  j.select_connection("hub:mesh");
  EXPECT_TRUE(j.tasks().empty());
  ASSERT_TRUE(f.pump([&] { return j.workspace() == "b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1"; }));
  f.settle(0.4);
  EXPECT_EQ(task_named(j, "x"), nullptr);
}

/* ---- Opening a task's sole published VTI (DIR/artifacts-plan.json of the fake) ---- */

const std::string kVtiTask = "55555555555555555555555555555555";
const std::string kOtherVtiTask = "66666666666666666666666666666666";
const std::string kDigestA(64, 'a');

Json artifact(const std::string &path, const std::string &sha256 = kDigestA, int64_t size = 4096)
{
  Json a = Json::object();
  a["path"] = path;
  a["size"] = size;
  a["sha256"] = sha256;
  a["media_type"] = "application/octet-stream";
  return a;
}

/** One scripted task.artifacts reply: `files`, after DIR/<hold> when set; `id` marks its stages. */
Json listing(const std::vector<Json> &files, const std::string &hold = {}, const std::string &id = {})
{
  Json list = Json::array();
  for (const Json &file : files) {
    list.push_back(file);
  }
  Json entry = Json::object();
  entry["artifacts"] = std::move(list);
  if (!hold.empty()) {
    entry["hold"] = hold;
  }
  if (!id.empty()) {
    entry["id"] = id;
  }
  return entry;
}

Json refusal(const std::string &code, bool retryable)
{
  Json error = Json::object();
  error["code"] = code;
  error["message"] = "Synthetic listing refusal";
  error["retryable"] = retryable;
  Json entry = Json::object();
  entry["error"] = std::move(error);
  return entry;
}

void write_artifacts_plan(const FakeJobs &f, const std::map<std::string, std::vector<Json>> &plan)
{
  Json out = Json::object();
  for (const auto &[task, entries] : plan) {
    Json list = Json::array();
    for (const Json &entry : entries) {
      list.push_back(entry);
    }
    out[task] = std::move(list);
  }
  const std::string path = f.jobs_dir() + "/artifacts-plan.json";
  std::ofstream(path + ".tmp") << out.dump();
  std::filesystem::rename(path + ".tmp", path);
}

bool marked(const FakeJobs &f, const std::string &name)
{
  return std::filesystem::exists(f.jobs_dir() + "/artifacts-" + name);
}

/** Lists synthetic tasks in `state` and selects the first (its own task.artifacts read follows,
 * or none when it is already selected and not newly terminal). */
void select_listed_task(FakeJobs &f, const std::vector<std::string> &tasks, const std::string &state = "succeeded")
{
  JobsState &j = f.jobs();
  Json rows = Json::array();
  for (const std::string &id : tasks) {
    Json row = Json::object();
    row["id"] = id;
    row["name"] = "合成场 " + id.substr(0, 4);
    row["state"] = state;
    row["workspace_id"] = j.workspace();
    row["updated_at"] = "2026-11-11T08:00:00+00:00";
    rows.push_back(std::move(row));
  }
  j.apply_snapshot(rows, 100.0);
  j.select_task(tasks.front());
}

/** Waits until the fake has received `count` task.artifacts reads and their replies were handled. */
void await_artifact_reads(FakeJobs &f, size_t count)
{
  ASSERT_TRUE(f.pump([&] { return method_count(f, "task.artifacts") >= count; }));
  drain(f);
  EXPECT_EQ(method_count(f, "task.artifacts"), count);
}

/** Requests an explicit open must never send (it reads only the task's artifact list). */
std::map<std::string, size_t> open_side_effects(const FakeJobs &f)
{
  std::map<std::string, size_t> out;
  for (const char *m : {"task.get", "task.submit", "task.cancel", "download.start", "upload.start", "workspace.create"}) {
    out[m] = method_count(f, m);
  }
  return out;
}

struct Resolved {
  int calls = 0;
  std::optional<app::OpenResultRequest> request;
};

void resolve_request(JobsState &j, app::OpenResultRequest request, Resolved &out)
{
  j.resolve_selected_result(std::move(request), [&out](app::OpenResultRequest r) {
    out.calls++;
    out.request = std::move(r);
  });
}

void resolve(JobsState &j, Resolved &out)
{
  auto request = j.selected_result_request();
  ASSERT_TRUE(request);
  resolve_request(j, std::move(*request), out);
}

void expect_original(const Resolved &r, const std::string &task, const std::string &why)
{
  ASSERT_EQ(r.calls, 1) << why;
  ASSERT_TRUE(r.request) << why;
  EXPECT_EQ(r.request->task_id, task) << why;
  EXPECT_TRUE(r.request->preset.empty()) << why;
  EXPECT_TRUE(r.request->task_artifact_path.empty()) << why;
  EXPECT_TRUE(r.request->task_artifact_sha256.empty()) << why;
  EXPECT_TRUE(r.request->local_paths.empty()) << why;
}

void expect_sole_vti(const Resolved &r, const std::string &task, const std::string &path, const std::string &sha)
{
  ASSERT_EQ(r.calls, 1);
  ASSERT_TRUE(r.request);
  EXPECT_EQ(r.request->task_id, task);
  EXPECT_EQ(r.request->connection, "runtime:lab");
  EXPECT_EQ(r.request->workspace_id, "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0");
  EXPECT_EQ(r.request->preset, "slice");
  EXPECT_EQ(r.request->task_artifact_path, path);
  EXPECT_EQ(r.request->task_artifact_sha256, sha);
  EXPECT_TRUE(r.request->local_paths.empty());
  ASSERT_TRUE(r.request->still_current);
  EXPECT_TRUE(r.request->still_current());
  ASSERT_TRUE(r.request->still_same_scope);
  EXPECT_TRUE(r.request->still_same_scope());
}

TEST_F(JobsFake, SoleVtiOfTheAcceptedListOpensThatExactFileWithTheSlicePreset)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  /* One published VTI beside a log and notes. */
  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("out/field-0.vti"), artifact("run.log"),
                                                artifact("README.md"), artifact("out/notes.txt")})}}});
  select_listed_task(f, {kVtiTask});
  await_artifact_reads(f, 1);
  ASSERT_EQ(j.artifacts().size(), 4u);
  const auto before = open_side_effects(f);

  Resolved r;
  resolve(j, r); /* The accepted list answers at once: no second read. */
  expect_sole_vti(r, kVtiTask, "out/field-0.vti", kDigestA);
  f.settle(0.2);
  EXPECT_EQ(method_count(f, "task.artifacts"), 1u);
  EXPECT_EQ(open_side_effects(f), before);
  ASSERT_NE(j.selected_task(), nullptr);
  EXPECT_EQ(j.selected_task()->state, "succeeded");
}

TEST_F(JobsFake, MixedRefusedAndUnsucceededListsKeepTheOriginalRequest)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const std::string vti = "field.vti";
  const std::vector<std::pair<std::string, std::vector<Json>>> cases = {
      {"vti+dat", {artifact(vti), artifact("Polar.00000100.dat")}},
      {"vti+vtk", {artifact(vti), artifact("field.vtk")}},
      {"vti+npy", {artifact(vti), artifact("field.npy")}},
      {"vti+vtkhdf", {artifact(vti), artifact("field.vtkhdf")}},
      {"vti+stkp", {artifact(vti), artifact("view.stkp")}},
      {"vti+result json", {artifact(vti), artifact("result.json")}},
      {"vti+mupro h5", {artifact(vti), artifact("case/run.h5")}},
      {"vti+png", {artifact(vti), artifact("result.png")}},
      {"vti+unknown plugin file", {artifact(vti), artifact("case/output.xyz")}},
      {"two vti", {artifact("a.vti"), artifact("b.vti")}},
      {"muferro dat", {artifact("Polar.00000000.dat"), artifact("Polar.00000100.dat"), artifact("run.log")}},
      {"single vtk", {artifact("field.vtk")}},
      {"notes only", {artifact("run.log")}},
      {"empty", {}},
      {"duplicate", {artifact(vti), artifact(vti)}},
      {"case duplicate", {artifact(vti), artifact("Field.VTI")}},
      {"missing digest", {artifact(vti, "")}},
      {"short digest", {artifact(vti, std::string(63, 'a'))}},
      {"uppercase digest", {artifact(vti, std::string(64, 'A'))}},
      {"graph path too long", {artifact(std::string(1021, 'x') + ".vti")}},
      {"non-hex digest", {artifact(vti, std::string(63, 'a') + "g")}},
      {"note without digest", {artifact(vti), artifact("run.log", "")}},
      {"negative size", {artifact(vti), artifact("run.log", kDigestA, -1)}},
      {"empty file", {artifact(vti, kDigestA, 0)}},
      {"parent segment", {artifact("../field.vti")}},
      {"absolute", {artifact("/tmp/field.vti")}},
      {"drive", {artifact("C:field.vti")}},
      {"backslash", {artifact("out\\field.vti")}},
      {"dot segment", {artifact("./field.vti")}},
      {"double slash", {artifact("out//field.vti")}},
      {"trailing slash", {artifact("out/field.vti/")}},
      {"control character", {artifact("out/\nfield.vti")}},
      {"file and directory", {artifact(vti), artifact(vti + "/notes.txt")}},
  };
  std::map<std::string, std::vector<Json>> plan;
  std::vector<std::string> ids;
  for (size_t i = 0; i < cases.size(); i++) {
    char id[33];
    snprintf(id, sizeof(id), "7%031zx", i);
    ids.push_back(id);
    plan[id] = {listing(cases[i].second)};
  }
  plan[kVtiTask] = {listing({artifact(vti)})};
  write_artifacts_plan(f, plan);
  std::vector<std::string> listed = ids;
  listed.push_back(kVtiTask);
  select_listed_task(f, listed);
  size_t reads = 0;
  await_artifact_reads(f, ++reads);
  for (size_t i = 0; i < cases.size(); i++) {
    if (i > 0) {
      j.select_task(ids[i]);
      await_artifact_reads(f, ++reads);
    }
    Resolved r;
    resolve(j, r);
    expect_original(r, ids[i], cases[i].first);
    EXPECT_EQ(method_count(f, "task.artifacts"), reads) << cases[i].first;
  }

  /* The same sole VTI of a task that did not succeed: the click reads nothing, original route. */
  for (const char *state : {"failed", "cancelled", "running", "unknown"}) {
    j.select_task("");
    select_listed_task(f, {kVtiTask}, state);
    await_artifact_reads(f, ++reads);
    Resolved r;
    resolve(j, r);
    expect_original(r, kVtiTask, state);
    f.settle(0.1);
    EXPECT_EQ(method_count(f, "task.artifacts"), reads) << state;
  }

  /* Once it succeeded, its finished list is read again and the sole VTI opens. */
  select_listed_task(f, {kVtiTask});
  await_artifact_reads(f, ++reads);
  Resolved sole;
  resolve(j, sole);
  expect_sole_vti(sole, kVtiTask, vti, kDigestA);

  /* Requests that are not a plain task open of the current selection pass through unchanged. */
  auto preset = j.selected_result_request();
  ASSERT_TRUE(preset);
  preset->preset = "muferro-domains";
  Resolved chosen;
  resolve_request(j, std::move(*preset), chosen);
  ASSERT_EQ(chosen.calls, 1);
  EXPECT_EQ(chosen.request->preset, "muferro-domains");
  EXPECT_TRUE(chosen.request->task_artifact_path.empty());
  auto other = j.selected_result_request();
  ASSERT_TRUE(other);
  other->task_id = kOtherVtiTask;
  Resolved another;
  resolve_request(j, std::move(*other), another);
  expect_original(another, kOtherVtiTask, "another task");
  auto local = j.selected_result_request();
  ASSERT_TRUE(local);
  local->task_id.clear();
  local->local_paths = {"/tmp/field.vti"};
  Resolved opened;
  resolve_request(j, std::move(*local), opened);
  ASSERT_EQ(opened.calls, 1);
  EXPECT_EQ(opened.request->local_paths, std::vector<std::string>{"/tmp/field.vti"});
  EXPECT_TRUE(opened.request->preset.empty());
  EXPECT_EQ(method_count(f, "task.artifacts"), reads);
}

TEST_F(JobsFake, ClickBeforeTheListArrivesWaitsForThatReadOnce)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("out/field.vti"), artifact("run.log")}, "vti-release", "vti")}}});
  select_listed_task(f, {kVtiTask, kOtherVtiTask});
  ASSERT_TRUE(f.pump([&] { return marked(f, "vti-held"); }));
  const auto before = open_side_effects(f);

  Resolved first, second;
  resolve(j, first);
  resolve(j, second); /* A second click replaces the first and sends nothing either. */
  f.settle(0.2);
  EXPECT_EQ(first.calls, 0);
  EXPECT_EQ(second.calls, 0);
  EXPECT_EQ(method_count(f, "task.artifacts"), 1u);

  touch(f, "vti-release");
  ASSERT_TRUE(f.pump([&] { return second.calls > 0; }));
  expect_sole_vti(second, kVtiTask, "out/field.vti", kDigestA);
  f.settle(0.2);
  EXPECT_EQ(first.calls, 0);
  EXPECT_EQ(second.calls, 1);
  EXPECT_EQ(method_count(f, "task.artifacts"), 1u);
  EXPECT_EQ(open_side_effects(f), before);

  /* A failed read leaves no accepted list: one explicit click lists once more, then opens the VTI. */
  const std::string digest_b(64, 'b');
  write_artifacts_plan(f, {{kOtherVtiTask, {refusal("unavailable", true), listing({artifact("field.vti", digest_b)})}}});
  j.select_task(kOtherVtiTask);
  await_artifact_reads(f, 2);
  EXPECT_TRUE(j.artifacts().empty());
  Resolved retried;
  resolve(j, retried);
  EXPECT_EQ(retried.calls, 0);
  ASSERT_TRUE(f.pump([&] { return retried.calls > 0; }));
  expect_sole_vti(retried, kOtherVtiTask, "field.vti", digest_b);
  EXPECT_EQ(method_count(f, "task.artifacts"), 3u);

  /* A read that keeps failing returns the original request after its single reply. */
  write_artifacts_plan(f, {{kVtiTask, {refusal("remote_error", false)}}});
  j.select_task(kVtiTask);
  await_artifact_reads(f, 4);
  Resolved failed;
  resolve(j, failed);
  EXPECT_EQ(failed.calls, 0);
  ASSERT_TRUE(f.pump([&] { return failed.calls > 0; }));
  expect_original(failed, kVtiTask, "failed read");
  f.settle(0.2);
  EXPECT_EQ(failed.calls, 1);
  EXPECT_EQ(method_count(f, "task.artifacts"), 5u);
  EXPECT_EQ(open_side_effects(f), before);
}

TEST_F(JobsFake, StaleEmptyListOfTheRunningTaskCannotAnswerTheFinishedTasksOpen)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  write_artifacts_plan(f, {{kVtiTask, {listing({}, "old-release", "old"),
                                       listing({artifact("field.vti")}, "new-release", "new")}}});
  select_listed_task(f, {kVtiTask}, "running");
  ASSERT_TRUE(f.pump([&] { return marked(f, "old-held"); }));
  /* The task finished: its list is read again while the running state's read is still out. */
  select_listed_task(f, {kVtiTask}, "succeeded");
  ASSERT_TRUE(f.pump([&] { return marked(f, "new-held"); }));
  Resolved r;
  resolve(j, r);
  EXPECT_EQ(method_count(f, "task.artifacts"), 2u);

  touch(f, "old-release");
  ASSERT_TRUE(f.pump([&] { return marked(f, "old-replied"); }));
  drain(f);
  EXPECT_EQ(r.calls, 0);
  EXPECT_TRUE(j.artifacts().empty());

  touch(f, "new-release");
  ASSERT_TRUE(f.pump([&] { return r.calls > 0; }));
  expect_sole_vti(r, kVtiTask, "field.vti", kDigestA);
  ASSERT_EQ(j.artifacts().size(), 1u);
  EXPECT_EQ(method_count(f, "task.artifacts"), 2u);
}

TEST_F(JobsFake, HeldListIsNotAdoptedAfterTheSelectionOrScopeChanged)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  const std::string digest_c(64, 'c');
  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("old.vti")}, "a-release", "a"),
                                       listing({artifact("new.vti", digest_c)})}}});
  select_listed_task(f, {kVtiTask, kOtherVtiTask});
  ASSERT_TRUE(f.pump([&] { return marked(f, "a-held"); }));
  /* Without the request's own source fence: JobsState alone must drop the late reply. */
  auto request = j.selected_result_request();
  ASSERT_TRUE(request);
  request->still_current = nullptr;
  Resolved r;
  resolve_request(j, std::move(*request), r);
  /* A -> B -> A while the first list is held: the click belonged to the first selection. */
  j.select_task(kOtherVtiTask);
  j.select_task(kVtiTask);
  await_artifact_reads(f, 3);
  ASSERT_EQ(j.artifacts().size(), 1u);
  EXPECT_EQ(j.artifacts()[0].file.path, "new.vti");
  touch(f, "a-release");
  ASSERT_TRUE(f.pump([&] { return marked(f, "a-replied"); }));
  drain(f);
  f.settle(0.2);
  EXPECT_EQ(r.calls, 0);
  ASSERT_EQ(j.artifacts().size(), 1u);
  EXPECT_EQ(j.artifacts()[0].file.path, "new.vti");

  /* A new click on the reselected task uses its own accepted list. */
  Resolved again;
  resolve(j, again);
  expect_sole_vti(again, kVtiTask, "new.vti", digest_c);

  /* A workspace round trip while a click waits: the late list is dropped as well. */
  write_artifacts_plan(f, {{kOtherVtiTask, {listing({artifact("b.vti")}, "b-release", "b")}}});
  j.select_task(kOtherVtiTask);
  ASSERT_TRUE(f.pump([&] { return marked(f, "b-held"); }));
  auto scoped_request = j.selected_result_request();
  ASSERT_TRUE(scoped_request);
  scoped_request->still_current = nullptr;
  Resolved scoped;
  resolve_request(j, std::move(*scoped_request), scoped);
  const std::string workspace = j.workspace();
  j.select_workspace("");
  j.select_workspace(workspace);
  select_listed_task(f, {kOtherVtiTask});
  touch(f, "b-release");
  ASSERT_TRUE(f.pump([&] { return marked(f, "b-replied"); }));
  drain(f);
  f.settle(0.2);
  EXPECT_EQ(scoped.calls, 0);
}

TEST_F(JobsFake, ClickWaitingAcrossABridgeRestartIsDropped)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("field.vti")}, "r-release", "r")}}});
  select_listed_task(f, {kVtiTask});
  ASSERT_TRUE(f.pump([&] { return marked(f, "r-held"); }));
  auto request = j.selected_result_request();
  ASSERT_TRUE(request);
  request->still_current = nullptr;
  Resolved r;
  resolve_request(j, std::move(*request), r);

  std::filesystem::remove(f.jobs_dir() + "/artifacts-r-held");
  const int64_t pid = f.client->bridge_pid();
  bridge::test::kill_hard(pid);
  /* The client re-sends the idempotent read to the new bridge process, which holds it again. */
  ASSERT_TRUE(f.pump([&] { return j.ready() && f.client->bridge_pid() != pid && marked(f, "r-held"); }, 6));
  /* The replayed watch lists the fake's own (empty) model; list the same finished task again so
   * only the bridge generation separates the waiting click from the reply. */
  ASSERT_TRUE(f.pump([&] { return j.tasks().empty(); }, 6));
  select_listed_task(f, {kVtiTask});
  ASSERT_EQ(j.selected(), kVtiTask);
  ASSERT_NE(j.selected_task(), nullptr);
  touch(f, "r-release");
  ASSERT_TRUE(f.pump([&] { return j.artifacts().size() == 1; }));
  drain(f);
  f.settle(0.2);
  EXPECT_EQ(r.calls, 0);

  /* The same task's list, accepted from the new process, answers a new click at once. */
  const size_t reads = method_count(f, "task.artifacts");
  Resolved again;
  resolve(j, again);
  expect_sole_vti(again, kVtiTask, "field.vti", kDigestA);
  EXPECT_EQ(method_count(f, "task.artifacts"), reads);
}


TEST_F(JobsFake, TaskResultRequiresCurrentBridgeArtifactListAfterRestart)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("before.vti")})}}});
  select_listed_task(f, {kVtiTask});
  await_artifact_reads(f, 1);
  Resolved first;
  resolve(j, first);
  expect_sole_vti(first, kVtiTask, "before.vti", kDigestA);

  write_artifacts_plan(f, {{kVtiTask, {listing({artifact("after.vti")}, "release-restart-result", "restart-result")}}});
  const auto pid = f.client->bridge_pid();
  bridge::test::kill_hard(pid);
  ASSERT_TRUE(f.pump([&] { return j.ready() && f.client->bridge_pid() != pid; }));
  select_listed_task(f, {kVtiTask});
  ASSERT_EQ(j.selected(), kVtiTask);
  ASSERT_EQ(j.artifacts().size(), 1u);
  EXPECT_EQ(j.artifacts().front().file.path, "before.vti");
  Resolved next;
  resolve(j, next);
  EXPECT_EQ(next.calls, 0);
  EXPECT_TRUE(j.resolving_task_result());
  ASSERT_TRUE(f.pump([&] { return marked(f, "restart-result-held"); }));
  EXPECT_EQ(next.calls, 0);
  touch(f, "release-restart-result");
  ASSERT_TRUE(f.pump([&] { return next.calls == 1; }));
  expect_sole_vti(next, kVtiTask, "after.vti", kDigestA);
  EXPECT_FALSE(j.resolving_task_result());
}

TEST_F(JobsFake, TaskResultDoesNotOpenAfterArtifactAuthorizationFailure)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  write_artifacts_plan(f, {{kVtiTask, {refusal("unauthorized", false)}}});
  select_listed_task(f, {kVtiTask});
  Resolved result;
  resolve(j, result);
  ASSERT_TRUE(j.resolving_task_result());
  await_artifact_reads(f, 1);
  EXPECT_FALSE(j.resolving_task_result());
  EXPECT_EQ(result.calls, 0);
  EXPECT_NE(j.status().text.find("Synthetic listing refusal"), std::string::npos);
}

}  // namespace
}  // namespace stk::jobstest
