/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Inert Viewer restore and independent per-window cameras, with the portable payload bridge. */
#include <cmath>
#include <limits>
#include <mutex>

#include <gtest/gtest.h>

#include "stk/app/editor.hh"
#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include "viewer_support.hh"
#include "../wm/support.hh"

namespace stk::app {
namespace {
using io::Json;
using namespace apptest;

void open_workspace_run(FakeViewer &f)
{
  f.vs->prefetch_neighbours = false;
  f.vs->set_metadata(repo_presets(), repo_catalog());
  ASSERT_TRUE(f.vs->open_path(f.run_dir()));
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() && !f.vs->evaluating(); })) << f.vs->eval_error();
}

/** Hold only main-loop continuations; the client still receives and fulfills bridge replies. */
class ProbeCallbackGate {
 public:
  explicit ProbeCallbackGate(bridge::Executor next) : next_(std::move(next)) {}

  bridge::Executor executor()
  {
    return [this](std::function<void()> task) {
      {
        std::lock_guard lock(mutex_);
        if (holding_) {
          held_.push_back(std::move(task));
          return;
        }
      }
      next_(std::move(task));
    };
  }

  void hold()
  {
    std::lock_guard lock(mutex_);
    holding_ = true;
  }

  std::vector<std::function<void()>> take()
  {
    std::lock_guard lock(mutex_);
    holding_ = false;
    std::vector<std::function<void()>> tasks;
    tasks.swap(held_);
    return tasks;
  }

 private:
  bridge::Executor next_;
  std::mutex mutex_;
  bool holding_ = false;
  std::vector<std::function<void()>> held_;
};

void completed_probe_cannot_overwrite_repick(const bool reopen)
{
  TempDir dir("probe-callback-race");
  ManualLoop loop;
  ProbeCallbackGate gate(loop.executor());
  bridge::ClientOptions options;
  options.command = {fake_bridge_path(), "--payload-dir", fixture_payload_dir().string(),
                     "--blob-dir", (dir.path() / "blobs").string()};
  options.executor = gate.executor();
  auto client = bridge::Client::create(std::move(options));
  std::string error;
  ASSERT_TRUE(client->start(&error)) << error;
  ASSERT_TRUE(client->wait_ready(30)) << client->bridge_log().text();
  {
    AppStore store;
    store.set_bridge(client.get());
    auto &viewer = store.viewer();
    viewer.prefetch_neighbours = false;
    viewer.set_metadata(repo_presets(), repo_catalog());
    const auto open = [&](const char *name) {
      const auto path = dir.path() / name;
      std::filesystem::create_directories(path);
      if (!write_text((path / "Polar.00000000.dat").string(), "1 1 1\n") ||
          !viewer.open_path(path.string(), "muferro-domains")) {
        return false;
      }
      if (!loop.pump_until([&] { return viewer.payload() && !viewer.evaluating(); },
                           30, [&] { viewer.pump(); })) {
        return false;
      }
      // Drain opening metadata continuations before isolating the probe callback.
      const auto settled = client->call("stats").wait_for(std::chrono::seconds(30));
      if (!settled || !settled->ok()) { return false; }
      loop.run_ready();
      return true;
    };
    ASSERT_TRUE(open("first")) << viewer.eval_error();
    const auto first_source = viewer.source().key();
    PickInfo a;
    a.probe_node = "frame";
    a.physical = {1.0, 2.0, 3.0};
    gate.hold();
    viewer.set_pick(a);
    // This bridge handles stdin synchronously. Receiving stats proves the preceding probe
    // response has fulfilled A's Future; cancel() can no longer replace that success.
    const auto first_barrier = client->call("stats").wait_for(std::chrono::seconds(30));
    ASSERT_TRUE(first_barrier.has_value());
    ASSERT_TRUE(first_barrier->ok()) << first_barrier->error().describe();
    ASSERT_EQ(first_barrier->value()["probe_requests"].size(), 1u);
    auto a_callbacks = gate.take();
    ASSERT_EQ(a_callbacks.size(), 1u);
    ASSERT_EQ(viewer.probe().status, ProbeState::Status::Pending);

    if (reopen) {
      viewer.close();
      ASSERT_TRUE(open("second")) << viewer.eval_error();
      EXPECT_NE(viewer.source().key(), first_source);
    }
    else {
      viewer.clear_pick();
      EXPECT_EQ(viewer.source().key(), first_source);
    }
    PickInfo b = a;
    b.physical = {4.0, 5.0, 6.0};
    gate.hold();
    viewer.set_pick(b);
    const auto second_barrier = client->call("stats").wait_for(std::chrono::seconds(30));
    ASSERT_TRUE(second_barrier.has_value());
    ASSERT_TRUE(second_barrier->ok()) << second_barrier->error().describe();
    ASSERT_EQ(second_barrier->value()["probe_requests"].size(), 2u);
    auto b_callbacks = gate.take();
    ASSERT_EQ(b_callbacks.size(), 1u);
    const auto source = viewer.source().key();
    const auto payload = viewer.base_payload();
    const auto pending = viewer.save_workspace_state()["probe"];
    ASSERT_EQ(viewer.probe().status, ProbeState::Status::Pending);
    ASSERT_TRUE(viewer.probe().target.is_null());
    ASSERT_TRUE(viewer.probe().sample.is_null());

    // Deliver only completed A. B's own successful reply remains deliberately withheld.
    a_callbacks.front()();
    EXPECT_EQ(viewer.save_workspace_state()["probe"], pending);
    EXPECT_EQ(viewer.source().key(), source);
    EXPECT_EQ(viewer.base_payload(), payload);
    EXPECT_EQ(viewer.probe().pick.physical, b.physical);

    // The active B continuation still completes normally once released.
    b_callbacks.front()();
    EXPECT_EQ(viewer.probe().status, ProbeState::Status::Done);
    EXPECT_FALSE(viewer.probe().target.is_null());
    EXPECT_EQ(viewer.probe().sample["values"], Json::array({0.25, -0.5, 0.75}));
    viewer.close();
    store.set_bridge(nullptr);
  }
  client->close();
  loop.run_ready();
}

TEST(ViewerWorkspace, CompletedProbeCannotOverwriteRepickAfterClear)
{
  ASSERT_NO_FATAL_FAILURE(completed_probe_cannot_overwrite_repick(false));
}

TEST(ViewerWorkspace, CompletedProbeCannotOverwriteRepickAfterReopen)
{
  ASSERT_NO_FATAL_FAILURE(completed_probe_cannot_overwrite_repick(true));
}

/** The portable bridge proves Viewer state transitions; real graph byte checks live in Python tests. */
struct GuardedOpenViewer {
  TempDir dir{"guarded-open"};
  ManualLoop loop;
  ProbeCallbackGate gate{loop.executor()};
  std::unique_ptr<bridge::Client> client;
  AppStore store;

  ~GuardedOpenViewer()
  {
    gate.take();
    store.viewer().close();
    store.set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
  }

  ViewerState &viewer() { return store.viewer(); }

  bool start(const bool metadata = true)
  {
    bridge::ClientOptions options;
    options.command = {fake_bridge_path(), "--payload-dir", fixture_payload_dir().string(),
                       "--blob-dir", (dir.path() / "blobs").string()};
    options.executor = gate.executor();
    client = bridge::Client::create(std::move(options));
    std::string error;
    if (!client->start(&error) || !client->wait_ready(30)) { return false; }
    store.set_bridge(client.get());
    viewer().prefetch_neighbours = false;
    viewer().set_colormaps(std::make_shared<const std::vector<ui::ColormapItem>>());
    if (metadata) { viewer().set_metadata(repo_presets(), repo_catalog()); }
    return true;
  }

  bool open(const std::string &name)
  {
    const auto path = dir.path() / name;
    std::filesystem::create_directories(path);
    if (!write_text((path / "Polar.00000000.dat").string(), "1 1 1\n")) { return false; }
    const Json proof = {{"project_root", dir.str()}, {"case_path", name},
                        {"files", {{{"path", name + "/Polar.00000000.dat"}, {"sha256", std::string(64, 'a')}}}}};
    return viewer().open_path(path.string(), "muferro-domains", Json(), proof);
  }

  bool wait(const std::function<bool()> &condition)
  {
    return loop.pump_until(condition, 30, [&] { viewer().pump(); });
  }

  Json barrier()
  {
    const auto reply = client->call("stats").wait_for(std::chrono::seconds(30));
    if (!reply || !reply->ok()) { return Json(); }
    return reply->value();
  }

  bool open_first()
  {
    if (!open("first") || !wait([&] { return viewer().payload() && !viewer().evaluating(); })) { return false; }
    if (!barrier().is_object()) { return false; }
    loop.run_ready();
    viewer().set_auto_evaluate(false);
    viewer().set_parameter("min_magnitude", ui::FormValue::number(0.3));
    return viewer().pending_edit() == "data";
  }
};

Json visible_viewer_state(const ViewerState &viewer)
{
  auto state = viewer.save_workspace_state();
  state.erase("open_error");
  state.erase("eval_error");
  return state;
}

TEST(ViewerWorkspace, GuardedOpenCommitsOneCompletedCandidateWithoutClearingTheOldDraft)
{
  GuardedOpenViewer f;
  ASSERT_TRUE(f.start());
  ASSERT_TRUE(f.open_first());
  auto &viewer = f.viewer();
  const auto previous = visible_viewer_state(viewer);
  const auto payload = viewer.base_payload(), display = viewer.payload();
  const auto camera = viewer.camera_serial(), serial = viewer.payload_serial();
  f.gate.hold();
  ASSERT_TRUE(f.open("second"));
  viewer.pump();
  const auto completed = f.barrier();
  ASSERT_TRUE(completed.is_object());
  ASSERT_EQ(completed["evaluate_requests"].size(), 2u);
  EXPECT_NE(completed["evaluate_requests"][0]["eval_id"], completed["evaluate_requests"][1]["eval_id"]);
  auto callbacks = f.gate.take();
  ASSERT_EQ(callbacks.size(), 1u);
  EXPECT_TRUE(viewer.evaluating());
  EXPECT_TRUE(visible_viewer_state(viewer) == previous);
  EXPECT_EQ(viewer.base_payload(), payload);
  EXPECT_EQ(viewer.payload(), display);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(viewer.payload_serial(), serial);

  callbacks.front()();
  viewer.pump();
  EXPECT_FALSE(viewer.evaluating());
  EXPECT_EQ(viewer.source().path, (f.dir.path() / "second").string());
  EXPECT_TRUE(viewer.payload());
  EXPECT_GT(viewer.camera_serial(), camera);
  EXPECT_GT(viewer.payload_serial(), serial);
  EXPECT_FALSE(viewer.auto_evaluate);
  EXPECT_TRUE(viewer.pending_edit().empty());
  ASSERT_EQ(f.barrier()["evaluate_requests"].size(), 2u) << "Commit must adopt the decoded frame without evaluating again";
}

enum class OpenInterruption { Cancel, Edit, Close, NewerOpen };

TEST(ViewerWorkspace, RejectedOpenCannotCancelAnAcceptedCandidate)
{
  GuardedOpenViewer f;
  ASSERT_TRUE(f.start());
  ASSERT_TRUE(f.open_first());
  auto &viewer = f.viewer();
  const auto payload = viewer.payload();
  f.gate.hold();
  ASSERT_TRUE(f.open("second"));
  const auto request = viewer.opening_status();
  const auto completed = f.barrier();
  ASSERT_EQ(completed["evaluate_requests"].size(), 2u);
  auto callbacks = f.gate.take();
  ASSERT_EQ(callbacks.size(), 1u);

  // Validation rejects this request before superseding the already accepted open.
  EXPECT_FALSE(viewer.open_path((f.dir.path() / "second").string(), "muferro-domains", Json(), Json::object()));
  EXPECT_EQ(viewer.opening_status(), request);
  EXPECT_TRUE(viewer.evaluating());
  EXPECT_EQ(viewer.payload(), payload);
  EXPECT_EQ(viewer.pending_edit(), "data");
  callbacks.front()();
  viewer.pump();
  EXPECT_FALSE(viewer.evaluating());
  EXPECT_EQ(viewer.source().path, (f.dir.path() / "second").string());
  EXPECT_EQ(viewer.opening_status()["state"], "succeeded");
  EXPECT_EQ(f.barrier()["evaluate_requests"].size(), 2u);
}

void completed_guarded_open_cannot_overwrite_a_newer_action(const OpenInterruption action)
{
  GuardedOpenViewer f;
  ASSERT_TRUE(f.start());
  ASSERT_TRUE(f.open_first());
  auto &viewer = f.viewer();
  const auto first = visible_viewer_state(viewer);
  f.gate.hold();
  ASSERT_TRUE(f.open("second"));
  viewer.pump();
  ASSERT_EQ(f.barrier()["evaluate_requests"].size(), 2u);
  auto callbacks = f.gate.take();
  ASSERT_EQ(callbacks.size(), 1u) << "The candidate Future is fulfilled, and cancel cannot revoke its held success";
  switch (action) {
    case OpenInterruption::Cancel:
      viewer.cancel_evaluation();
      EXPECT_TRUE(visible_viewer_state(viewer) == first);
      break;
    case OpenInterruption::Edit:
      viewer.set_parameter("min_magnitude", ui::FormValue::number(0.7));
      EXPECT_EQ(viewer.source().path, (f.dir.path() / "first").string());
      EXPECT_EQ(viewer.parameters()["min_magnitude"], Json(0.7));
      break;
    case OpenInterruption::Close:
      viewer.close();
      EXPECT_EQ(viewer.source().kind, SourceKind::None);
      EXPECT_FALSE(viewer.payload());
      break;
    case OpenInterruption::NewerOpen:
      ASSERT_TRUE(f.open("third"));
      ASSERT_TRUE(f.wait([&] { return viewer.source().path == (f.dir.path() / "third").string() && !viewer.evaluating(); }));
      ASSERT_EQ(f.barrier()["evaluate_requests"].size(), 3u);
      break;
  }
  const auto newer = visible_viewer_state(viewer);
  const auto payload = viewer.base_payload(), display = viewer.payload();
  const auto camera = viewer.camera_serial(), serial = viewer.payload_serial();
  callbacks.front()();
  viewer.pump();
  EXPECT_FALSE(viewer.evaluating());
  EXPECT_TRUE(visible_viewer_state(viewer) == newer);
  EXPECT_EQ(viewer.base_payload(), payload);
  EXPECT_EQ(viewer.payload(), display);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(viewer.payload_serial(), serial);
}

TEST(ViewerWorkspace, CompletedGuardedOpenCannotReplaceTheOldViewerAfterCancellation)
{
  ASSERT_NO_FATAL_FAILURE(completed_guarded_open_cannot_overwrite_a_newer_action(OpenInterruption::Cancel));
}

TEST(ViewerWorkspace, CompletedGuardedOpenCannotReplaceANewerParameterDraft)
{
  ASSERT_NO_FATAL_FAILURE(completed_guarded_open_cannot_overwrite_a_newer_action(OpenInterruption::Edit));
}

TEST(ViewerWorkspace, CompletedGuardedOpenCannotReopenAClosedViewer)
{
  ASSERT_NO_FATAL_FAILURE(completed_guarded_open_cannot_overwrite_a_newer_action(OpenInterruption::Close));
}

TEST(ViewerWorkspace, CompletedGuardedOpenCannotReplaceANewerSource)
{
  ASSERT_NO_FATAL_FAILURE(completed_guarded_open_cannot_overwrite_a_newer_action(OpenInterruption::NewerOpen));
}

TEST(ViewerWorkspace, GuardedOpenMetadataFailureKeepsThePreviousPayload)
{
  GuardedOpenViewer f;
  ASSERT_TRUE(f.start(false));
  auto &viewer = f.viewer();
  ASSERT_TRUE(viewer.open_path(fixture_stkp().string()));
  const auto previous = visible_viewer_state(viewer);
  const auto payload = viewer.base_payload(), display = viewer.payload();
  const auto camera = viewer.camera_serial(), serial = viewer.payload_serial();
  ASSERT_TRUE(f.open("second"));
  ASSERT_TRUE(f.wait([&] {
    return !viewer.evaluating() && (!viewer.open_error().empty() || !viewer.eval_error().empty() ||
                                    !viewer.metadata_error().empty());
  }));
  EXPECT_TRUE(visible_viewer_state(viewer) == previous);
  EXPECT_EQ(viewer.base_payload(), payload);
  EXPECT_EQ(viewer.payload(), display);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(viewer.payload_serial(), serial);
  EXPECT_EQ(f.barrier()["evaluate_requests"].size(), 0u);
  // The error is terminal: another completed main-loop turn must not queue a retry.
  f.loop.run_ready();
  viewer.pump();
  EXPECT_FALSE(viewer.evaluating());
  EXPECT_EQ(f.barrier()["evaluate_requests"].size(), 0u);
}

TEST(ViewerWorkspace, RestoresFrozenPayloadParametersLayersAndSettingsWithoutAnyReplay)
{
  FakeViewer f;
  ASSERT_NO_FATAL_FAILURE(open_workspace_run(f));
  f.vs->set_auto_evaluate(false);
  f.vs->set_parameter("view", ui::FormValue::string("+x"));
  f.vs->set_layer_opacity("surface_layer", 0.375);
  f.vs->set_layer_visible("box", false);
  f.vs->set_overlays(false);
  f.vs->fps = 9.5; f.vs->loop = false; f.vs->prefetch_neighbours = true;
  f.vs->data_debounce_s = 0.7; f.vs->client_debounce_s = 0.2;
  f.vs->export_settings.width = 2048; f.vs->export_settings.height = 1152;
  f.vs->export_settings.magnification = 3; f.vs->export_settings.transparent = true;
  f.vs->export_settings.path = "research-view.png"; f.vs->export_settings.sequence = true;
  const auto state = f.vs->save_workspace_state();
  const auto payload = f.vs->base_payload();
  const auto count = f.stats()["evaluate_requests"].size();
  ASSERT_TRUE(f.vs->load_workspace_state(state, payload));
  EXPECT_TRUE(f.vs->workspace_suspended()); EXPECT_FALSE(f.vs->playing());
  EXPECT_FALSE(f.vs->auto_evaluate); EXPECT_FALSE(f.vs->overlays());
  EXPECT_EQ(f.vs->parameters()["view"], "+x");
  EXPECT_EQ(f.vs->source().path, state["source"]["path"].get<std::string>());
  EXPECT_EQ(f.vs->shown_step(), state["shown_step"]);
  EXPECT_EQ(f.vs->payload()->layer("surface_layer")->at("appearance")["opacity"], 0.375);
  EXPECT_FALSE(f.vs->visibility().at("box"));
  EXPECT_EQ(f.vs->fps, 9.5); EXPECT_FALSE(f.vs->loop);
  EXPECT_EQ(f.vs->export_settings.path, "research-view.png");
  EXPECT_EQ(f.vs->save_workspace_state(), state);
  f.advance(100.0); f.loop.run_ready();
  EXPECT_EQ(f.stats()["evaluate_requests"].size(), count);
  EXPECT_FALSE(f.vs->graph_inspection()->shown_graph_verified.has_value());
  EXPECT_FALSE(f.vs->graph_inspection()->shown_matches_desired.has_value());
}

TEST(ViewerWorkspace, CollectedSourceProofSurvivesRestoreAndReachesEveryExplicitRead)
{
  FakeViewer f;
  f.vs->prefetch_neighbours = false;
  f.vs->set_metadata(repo_presets(), repo_catalog());
  const auto path = f.run_dir();
  const Json proof = {{"project_root", f.dir.str()}, {"case_path", "run"},
                      {"files", {{{"path", "run/Polar.00000000.dat"}, {"sha256", std::string(64, 'a')}}}}};
  ASSERT_TRUE(f.vs->open_path(path, "muferro-domains", Json(), proof));
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() && !f.vs->evaluating(); }));
  const auto key = f.vs->source().key();
  EXPECT_NE(key, classify_path(path).key());
  EXPECT_EQ(f.stats()["evaluate_requests"].back()["local_proofs"], Json({{"run", proof}}));

  const auto count = f.stats()["evaluate_requests"].size();
  f.vs->evaluate_now();
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating(); }));
  EXPECT_EQ(f.stats()["evaluate_requests"].size(), count + 1);  // The native cache cannot bypass a new proof check.
  EXPECT_EQ(f.stats()["evaluate_requests"].back()["local_proofs"], Json({{"run", proof}}));

  PickInfo pick;
  pick.probe_node = "frame";
  pick.physical = {0.0, 0.0, 0.0};
  f.vs->set_pick(pick);
  ASSERT_TRUE(f.pump_until([&] { return f.vs->probe().status == ProbeState::Status::Done; }));
  EXPECT_EQ(f.stats()["probe_requests"].back()["local_proofs"], Json({{"run", proof}}));

  const auto state = f.vs->save_workspace_state();
  const auto payload = f.vs->base_payload();
  const auto before = f.stats();
  ASSERT_TRUE(f.vs->load_workspace_state(state, payload));
  EXPECT_EQ(f.vs->source().source_proof, proof);
  EXPECT_EQ(f.vs->source().key(), key);
  EXPECT_EQ(f.stats(), before);
  f.vs->evaluate_now();
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating(); }));
  EXPECT_EQ(f.stats()["evaluate_requests"].back()["local_proofs"], Json({{"run", proof}}));

  auto invalid = proof;
  invalid["files"][0]["path"] = "run/../foreign.dat";
  EXPECT_FALSE(f.vs->open_path(path, "muferro-domains", Json(), invalid));
  EXPECT_EQ(f.vs->source().key(), key);
  auto invalid_state = state;
  invalid_state["source"]["source_proof"] = invalid;
  EXPECT_FALSE(f.vs->load_workspace_state(invalid_state, payload));
  EXPECT_EQ(f.vs->source().key(), key);
}

TEST(ViewerWorkspace, PreservesAutomaticPreferenceAndRawDraftButRequiresExplicitRun)
{
  FakeViewer f;
  ASSERT_NO_FATAL_FAILURE(open_workspace_run(f));
  auto state = f.vs->save_workspace_state();
  state["playing"] = true; state["auto_evaluate"] = true; state["prefetch_neighbours"] = true;
  state["form_values"]["unsaved_json_draft"] = {{"kind", 3}, {"boolean", false}, {"number", 0.0},
      {"text", "{ invalid JSON draft"}, {"array", Json::array()}, {"null_mask", Json::array()}};
  const auto payload = f.vs->base_payload();
  const auto count = f.stats()["evaluate_requests"].size();
  ASSERT_TRUE(f.vs->load_workspace_state(state, payload));
  EXPECT_TRUE(f.vs->auto_evaluate); EXPECT_TRUE(f.vs->prefetch_neighbours); EXPECT_FALSE(f.vs->playing());
  EXPECT_EQ(f.vs->form().get("unsaved_json_draft").str, "{ invalid JSON draft");
  EXPECT_EQ(f.vs->save_workspace_state()["playing"], true);
  f.vs->set_parameter("view", ui::FormValue::string("-x"));
  f.vs->set_auto_evaluate(false); f.vs->set_auto_evaluate(true);
  f.advance(100.0);
  EXPECT_TRUE(f.vs->workspace_suspended()); EXPECT_FALSE(f.vs->evaluating());
  EXPECT_EQ(f.stats()["evaluate_requests"].size(), count);
  f.vs->prefetch_neighbours = false;
  f.vs->evaluate_now();
  EXPECT_FALSE(f.vs->workspace_suspended());
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating(); }));
  EXPECT_EQ(f.stats()["evaluate_requests"].size(), count + 1);
}

TEST(ViewerWorkspace, SavingTheFrozenSingleFrameDoesNotResumeEvaluationOrPrefetch)
{
  FakeViewer f;
  ASSERT_NO_FATAL_FAILURE(open_workspace_run(f));
  auto state = f.vs->save_workspace_state();
  state["playing"] = true; state["auto_evaluate"] = true; state["prefetch_neighbours"] = true;
  const auto count = f.stats()["evaluate_requests"].size();
  ASSERT_TRUE(f.vs->load_workspace_state(state, f.vs->base_payload()));
  f.vs->export_settings.path = "explicit-frame.png";
  f.vs->export_settings.sequence = false;
  f.vs->request_export();
  ASSERT_TRUE(f.vs->export_job()); EXPECT_TRUE(f.vs->export_job()->ready);
  EXPECT_TRUE(f.vs->workspace_suspended());
  f.advance(100.0);
  EXPECT_EQ(f.stats()["evaluate_requests"].size(), count);
  EXPECT_FALSE(f.vs->playing());
}

TEST(ViewerWorkspace, InvalidSettingsRejectBeforeReplacingAnyCurrentState)
{
  FakeViewer f;
  ASSERT_NO_FATAL_FAILURE(open_workspace_run(f));
  const auto original = f.vs->save_workspace_state();
  const auto payload = f.vs->base_payload();
  for (int fault = 0; fault < 7; fault++) {
    auto bad = original;
    if (fault == 0) { bad["version"] = true; }
    if (fault == 1) { bad["export_settings"]["width"] = 0; }
    if (fault == 2) { bad["opacity"]["surface_layer"] = 1.5; }
    if (fault == 3) { bad["source"]["kind"] = "unsupported"; }
    if (fault == 4) { bad["form_values"]["bad"] = {{"kind", 2}, {"number", "not numeric"}}; }
    if (fault == 5) { bad["auto_evaluate"] = 1; }
    if (fault == 6) { bad["fps"] = std::numeric_limits<double>::quiet_NaN(); }
    std::string error;
    EXPECT_FALSE(f.vs->load_workspace_state(bad, {}, &error)) << fault;
    EXPECT_FALSE(error.empty()); EXPECT_EQ(f.vs->base_payload(), payload);
    EXPECT_EQ(f.vs->save_workspace_state(), original) << fault;
  }
}

TEST(ViewerWorkspace, PendingProbeBecomesUnavailableAndNeverRequeries)
{
  FakeViewer f;
  ASSERT_NO_FATAL_FAILURE(open_workspace_run(f));
  auto state = f.vs->save_workspace_state();
  state["probe"]["status"] = int(ProbeState::Status::Pending);
  state["probe"]["pick"]["physical"] = {1.25, 2.5, 3.75};
  state["probe"]["pick"]["layer_id"] = "surface_layer";
  const auto before = f.stats();
  ASSERT_TRUE(f.vs->load_workspace_state(state, f.vs->base_payload()));
  EXPECT_EQ(f.vs->probe().status, ProbeState::Status::Unavailable);
  EXPECT_EQ(f.vs->probe().pick.physical, (std::array<double, 3>{1.25, 2.5, 3.75}));
  f.advance(100.0);
  const auto after = f.stats();
  EXPECT_EQ(after.value("probe_requests", Json()), before.value("probe_requests", Json()));
  EXPECT_EQ(after["evaluate_requests"].size(), before["evaluate_requests"].size());
}

TEST(ViewerWorkspace, FinishedProbeSampleAndPickRemainOfflineInspectible)
{
  AppStore source;
  auto &viewer = source.viewer();
  auto state = viewer.save_workspace_state();
  state["probe"]["status"] = int(ProbeState::Status::Done);
  state["probe"]["pick"]["layer_name"] = "Polarization";
  state["probe"]["target"] = {{"path", "Polar.00000002.dat"}, {"binding", "run"}};
  state["probe"]["sample"] = {{"values", {1.0, 2.0, 3.0}}, {"units", "C/m^2"}};
  AppStore target;
  ASSERT_TRUE(target.viewer().load_workspace_state(state, {}));
  EXPECT_EQ(target.viewer().probe().status, ProbeState::Status::Done);
  EXPECT_EQ(target.viewer().probe().sample, state["probe"]["sample"]);
  EXPECT_EQ(target.viewer().probe().pick.layer_name, "Polarization");
  EXPECT_TRUE(target.viewer().workspace_suspended());
}

TEST(ViewerWorkspace, EachEditorKeepsIndependentCameraAndLegacyLayoutState)
{
  wmtest::AppFixture fixture;
  auto first = fixture.shell->registry().create(kEditorViewer);
  auto second = fixture.shell->registry().create(kEditorViewer);
  ASSERT_TRUE(first && second);
  const auto old_layout = first->save_state();
  const auto second_original = second->save_workspace_state();
  auto state = first->save_workspace_state();
  state["camera"]["position"] = {12.0, 9.0, 5.0};
  state["camera"]["parallel"] = true;
  state["camera"]["parallel_scale"] = 7.25;
  state["camera"]["view_angle_deg"] = 45.0;
  state["saved_camera"] = state["camera"];
  state["navigation"] = "paraview"; state["lighting"] = "headlight"; state["tool"] = "pick";
  ASSERT_TRUE(first->load_workspace_state(state));
  EXPECT_EQ(first->save_workspace_state(), state);
  EXPECT_EQ(second->save_workspace_state(), second_original);
  EXPECT_EQ(old_layout, (nlohmann::json{{"tool", "orbit"}, {"navigation", "blender"}}));
  EXPECT_FALSE(first->save_state().contains("camera"));
  auto bad = state; bad["camera"]["focal_point"] = state["camera"]["position"];
  EXPECT_FALSE(first->load_workspace_state(bad)); EXPECT_EQ(first->save_workspace_state(), state);
  bad = state; bad["navigation"] = "unknown";
  EXPECT_FALSE(first->load_workspace_state(bad)); EXPECT_EQ(first->save_workspace_state(), state);
}

TEST(ViewerWorkspace, ProbeEditorRestoresTypedCoordinateDraftWithoutSubmitting)
{
  wmtest::AppFixture fixture;
  auto editor = fixture.shell->registry().create(kEditorProbe);
  ASSERT_TRUE(editor);
  nlohmann::json state = {{"version", 1}, {"typed", true}, {"position", {1.0, -2.5, 900719925.25}}};
  ASSERT_TRUE(editor->load_workspace_state(state));
  EXPECT_EQ(editor->save_workspace_state(), state);
  EXPECT_TRUE(editor->save_state().empty());
  auto bad = state; bad["position"][2] = "invalid";
  EXPECT_FALSE(editor->load_workspace_state(bad)); EXPECT_EQ(editor->save_workspace_state(), state);
  EXPECT_EQ(fixture.shell->store().viewer().probe().status, ProbeState::Status::Empty);
}

}  // namespace
}  // namespace stk::app
