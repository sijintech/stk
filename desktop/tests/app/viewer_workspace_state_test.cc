/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Inert portable Viewer restore and independent per-window cameras, with the fake bridge. */
#include <cmath>
#include <limits>

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
