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

}  // namespace
}  // namespace stk::jobstest
