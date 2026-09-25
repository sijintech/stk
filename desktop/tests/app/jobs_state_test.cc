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

namespace stk::jobstest {
namespace {

using app::JobsState;
using app::SubmitState;
using io::Json;

bool has(const std::vector<std::string> &v, const std::string &s)
{
  return std::find(v.begin(), v.end(), s) != v.end();
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
  EXPECT_TRUE(has(paths, "case/input.toml"));
  EXPECT_TRUE(has(paths, "case/sub/b.txt"));
  EXPECT_TRUE(has(paths, "单个.dat"));
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

TEST_F(JobsFake, CancelShowsCancellingThenCancelled)
{
  FakeJobs f;
  JobsState &j = f.jobs();
  ASSERT_TRUE(f.connect("runtime:lab"));
  j.form().name = "slow job";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(f.pump([&] {
    const app::TaskRow *t = task_named(j, "slow job");
    return t && t->state == "running";
  }));
  j.cancel_task(task_named(j, "slow job")->id);
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
