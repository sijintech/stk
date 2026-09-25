/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file ViewerState against the scripted fake bridge (no GPU): metadata, opening sources,
 * client- vs data-stage re-evaluation (result.evaluated), debounce and cancellation of superseded
 * evaluations, graph.progress, timestep prefetch with cached switches and camera preservation,
 * playback, probing, layer display overrides and sequence export planning. */

#include <algorithm>
#include <filesystem>

#include <gtest/gtest.h>

#include "stk/io/payload.hh"
#include "stk/viewer/camera.hh"
#include "viewer_support.hh"

namespace fs = std::filesystem;
using stk::io::Json;
using namespace stk;
using namespace stk::apptest;
using app::SourceKind;
using app::ViewerState;

namespace {

bool contains(const std::vector<std::string> &v, const std::string &s)
{
  return std::find(v.begin(), v.end(), s) != v.end();
}

/** Opens the fake run and waits for the first payload. */
void open_run(FakeViewer &f)
{
  f.vs->refresh_metadata();
  ASSERT_TRUE(f.pump_until([&] { return f.vs->presets_loaded() && !f.vs->catalog().is_null(); }));
  ASSERT_TRUE(f.vs->open_path(f.run_dir()));
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() != nullptr && !f.vs->evaluating(); }))
      << f.vs->eval_error();
}

}  // namespace

TEST(ViewerFake, MetadataAndOpeningARunFolderEvaluates)
{
  FakeViewer f;
  f.vs->refresh_metadata();
  ASSERT_TRUE(f.pump_until([&] { return f.vs->presets_loaded() && f.vs->colormaps() && !f.vs->catalog().is_null(); }));
  EXPECT_EQ(f.vs->presets().size(), 7u);
  EXPECT_NE(f.vs->preset("muferro-domains"), nullptr);
  ASSERT_EQ(f.vs->colormaps()->size(), 2u);
  EXPECT_EQ(f.vs->colormaps()->front().lut.size(), 256u);

  ASSERT_TRUE(f.vs->open_path(f.run_dir()));
  EXPECT_EQ(f.vs->source().kind, SourceKind::RunDir);
  EXPECT_EQ(f.vs->preset_id(), "muferro-domains") << "guessed from the Polar.* frames";
  EXPECT_EQ(f.vs->step_param(), "step");
  EXPECT_EQ(f.vs->payload_outputs(), std::vector<std::string>{"view"});
  EXPECT_TRUE(f.vs->evaluating());
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() != nullptr; })) << f.vs->eval_error();
  EXPECT_FALSE(f.vs->evaluating());
  ASSERT_TRUE(f.vs->last_eval().has_value());
  const app::EvalRecord &rec = *f.vs->last_eval();
  EXPECT_EQ(rec.reason, "open");
  EXPECT_EQ(rec.evaluated.size(), 10u);
  /* Data nodes come from the catalog stages (source / data / analysis). */
  const std::vector<std::string> data = f.vs->data_nodes();
  for (const char *n : {"run", "polar", "domains", "surfaces", "fractions"}) {
    EXPECT_TRUE(contains(data, n)) << n;
  }
  for (const char *n : {"surface_layer", "camera", "scene", "png"}) {
    EXPECT_FALSE(contains(data, n)) << n;
  }
  EXPECT_EQ(rec.data_nodes, (std::vector<std::string>{"run", "polar", "domains", "surfaces"}));
  /* graph.progress arrived for every evaluated node. */
  EXPECT_EQ(f.vs->progress().started, 10);
  EXPECT_EQ(f.vs->progress().finished, 10);
  EXPECT_EQ(f.vs->progress().expected, 10) << "ancestors of the payload output";
  /* Steps from result.parameters. */
  ASSERT_EQ(f.vs->step_choices().size(), 3u);
  EXPECT_EQ(f.vs->shown_step(), Json(2));
  EXPECT_EQ(f.vs->step_index(), 2);
  EXPECT_EQ(f.vs->parameters()["step"], "latest");
  EXPECT_EQ(f.vs->parameters()["view"], "iso");
  /* The payload decoded from the bridge's blob cache. */
  const auto p = f.vs->payload();
  EXPECT_EQ(p->manifest["schema"], "stk.payload/2");
  EXPECT_EQ(p->manifest["view"]["time"]["step"], 2);
}

TEST(ViewerFake, ClientStageChangeRunsNoDataNode)
{
  FakeViewer f;
  open_run(f);
  const uint64_t serial = f.vs->payload_serial();
  const uint64_t camera = f.vs->camera_serial();
  EXPECT_EQ(f.vs->param_stage("view"), "client");
  f.vs->set_parameter("view", ui::FormValue::string("+x"));
  EXPECT_EQ(f.vs->pending_edit(), "client");
  f.advance(f.vs->client_debounce_s + 0.01);
  ASSERT_TRUE(f.vs->evaluating());
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating() && f.vs->payload_serial() != serial; }));
  const app::EvalRecord &rec = *f.vs->last_eval();
  EXPECT_EQ(rec.reason, "client");
  EXPECT_FALSE(rec.from_cache);
  EXPECT_EQ(rec.evaluated, (std::vector<std::string>{"camera", "scene"}));
  EXPECT_TRUE(rec.data_nodes.empty()) << "a client-stage change re-runs no data node";
  EXPECT_EQ(f.vs->camera_serial(), camera) << "the views follow the payload's camera signature";
}

TEST(ViewerFake, DataStageChangeRerunsDataNodesAfterTheDebounce)
{
  FakeViewer f;
  open_run(f);
  const int started = f.vs->evaluations_started();
  EXPECT_EQ(f.vs->param_stage("min_magnitude"), "data");
  f.vs->set_parameter("min_magnitude", ui::FormValue::number(0.2));
  f.advance(0.1);
  f.vs->set_parameter("min_magnitude", ui::FormValue::number(0.25));
  f.advance(0.1);
  f.vs->set_parameter("min_magnitude", ui::FormValue::number(0.3));
  f.advance(f.vs->data_debounce_s - 0.05);
  EXPECT_EQ(f.vs->evaluations_started(), started) << "still inside the debounce window";
  f.advance(0.1);
  EXPECT_EQ(f.vs->evaluations_started(), started + 1) << "three edits, one evaluation";
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating(); }));
  const app::EvalRecord &rec = *f.vs->last_eval();
  EXPECT_EQ(rec.reason, "data");
  EXPECT_TRUE(contains(rec.evaluated, "domains"));
  EXPECT_FALSE(rec.data_nodes.empty());
  EXPECT_EQ(f.vs->result()->evaluated.size(), 10u);
}

TEST(ViewerFake, SupersededEvaluationIsCancelled)
{
  FakeViewer f({"--eval-delay-ms", "600"});
  f.vs->prefetch_neighbours = false;
  f.vs->refresh_metadata();
  ASSERT_TRUE(f.pump_until([&] { return f.vs->presets_loaded() && !f.vs->catalog().is_null(); }));
  ASSERT_TRUE(f.vs->open_path(f.run_dir()));
  ASSERT_TRUE(f.vs->evaluating());
  const std::string first = f.vs->progress().eval_id;
  /* A data edit while the first evaluation runs supersedes it. */
  f.vs->set_parameter("min_magnitude", ui::FormValue::number(0.3));
  f.advance(f.vs->data_debounce_s + 0.01);
  ASSERT_TRUE(f.vs->evaluating());
  EXPECT_NE(f.vs->progress().eval_id, first);
  EXPECT_EQ(f.vs->evaluations_cancelled(), 1);
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() != nullptr && !f.vs->evaluating(); }, 30));
  EXPECT_NE(f.vs->last_eval()->eval_id, first) << "only the newest result is shown";
  EXPECT_EQ(f.vs->result()->raw["parameters"]["step"]["value"], 2);
  const Json stats = f.stats();
  EXPECT_EQ(stats.value("cancels", -1), 1) << "graph.cancel reached the bridge: " << stats.dump();
  EXPECT_EQ(stats.value("evaluations", -1), 2);
}

TEST(ViewerFake, TimestepPrefetchCachedSwitchAndCameraPreservation)
{
  FakeViewer f;
  open_run(f);
  const uint64_t camera = f.vs->camera_serial();
  const std::string signature = viewer::camera_signature(f.vs->payload()->manifest["view"]);
  /* Showing step 2 prefetches its neighbour (step 1) in the background. */
  ASSERT_TRUE(f.pump_until([&] { return f.vs->prefetched_count() >= 1 && !f.vs->evaluating(); }));
  EXPECT_EQ(f.vs->take_prefetched().size(), 1u) << "handed to the GPU viewer for upload";
  EXPECT_EQ(f.vs->cached_results(), 2u);
  const int started = f.vs->evaluations_started();
  /* Switching to the prefetched step: no bridge call, the payload is current at once (the next
   * neighbour, step 0, starts prefetching in the background). */
  f.vs->set_step_index(1);
  EXPECT_FALSE(f.vs->evaluating()) << "served from the viewer cache";
  EXPECT_LE(f.vs->evaluations_started(), started + 1);
  EXPECT_EQ(f.vs->shown_step(), Json(1));
  EXPECT_TRUE(f.vs->last_eval()->from_cache);
  EXPECT_EQ(f.vs->last_eval()->reason, "step");
  EXPECT_GE(f.vs->last_step_switch_ms(), 0.0);
  EXPECT_LT(f.vs->last_step_switch_ms(), 1.0) << "fake clock: the switch happens within the call";
  EXPECT_EQ(f.vs->payload()->manifest["view"]["time"]["step"], 1);
  EXPECT_EQ(f.vs->parameters()["step"], 1);
  /* Camera: the view's signature is unchanged across steps and no reset is requested. */
  EXPECT_EQ(viewer::camera_signature(f.vs->payload()->manifest["view"]), signature);
  EXPECT_EQ(f.vs->camera_serial(), camera);
  /* Now step 0 is prefetched; stepping back is cached too. */
  ASSERT_TRUE(f.pump_until([&] { return f.vs->prefetched_count() >= 2 && !f.vs->evaluating(); }));
  f.vs->step_by(-1);
  EXPECT_EQ(f.vs->shown_step(), Json(0));
  EXPECT_TRUE(f.vs->last_eval()->from_cache);
  EXPECT_EQ(f.vs->evaluations_started(), started + 1) << "only the one prefetch";
  /* A data edit invalidates: the next step switch evaluates again. */
  f.vs->set_parameter("min_magnitude", ui::FormValue::number(0.4));
  f.advance(f.vs->data_debounce_s + 0.01);
  ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating() && f.vs->last_eval()->reason == "data"; }));
  EXPECT_EQ(f.vs->camera_serial(), camera);
}

TEST(ViewerFake, CameraResetsForANewSourceOrPreset)
{
  FakeViewer f;
  open_run(f);
  uint64_t camera = f.vs->camera_serial();
  f.vs->select_preset("muferro-polarization-glyphs");
  EXPECT_GT(f.vs->camera_serial(), camera);
  EXPECT_EQ(f.vs->parameters().value("max_points", Json()), 20000) << "the new preset's defaults";
  camera = f.vs->camera_serial();
  ASSERT_TRUE(f.vs->open_path(fixture_stkp().string()));
  EXPECT_GT(f.vs->camera_serial(), camera);
  EXPECT_EQ(f.vs->source().kind, SourceKind::Payload);
}

TEST(ViewerFake, PlaybackAdvancesAndLoops)
{
  FakeViewer f;
  open_run(f);
  ASSERT_TRUE(f.pump_until([&] { return f.vs->prefetched_count() >= 1 && !f.vs->evaluating(); }));
  f.vs->fps = 10.0;
  f.vs->loop = true;
  f.vs->set_playing(true);
  ASSERT_TRUE(f.vs->playing());
  std::vector<int> seen;
  for (int i = 0; i < 12 && seen.size() < 4; i++) {
    const int before = f.vs->step_index();
    f.advance(0.11);
    ASSERT_TRUE(f.pump_until([&] { return !f.vs->evaluating(); }));
    if (f.vs->step_index() != before) {
      seen.push_back(f.vs->step_index());
    }
  }
  ASSERT_GE(seen.size(), 3u);
  EXPECT_EQ(seen[0], 0) << "from the last step, looping to the first";
  EXPECT_EQ(seen[1], 1);
  EXPECT_EQ(seen[2], 2);
  f.vs->set_playing(false);
  EXPECT_FALSE(f.vs->playing());
}

TEST(ViewerFake, ProbeReadsTheOriginalValueThroughTheBridge)
{
  FakeViewer f;
  open_run(f);
  app::PickInfo pick;
  pick.layer_id = "surface_layer";
  pick.layer_type = "triangles";
  pick.element = 42;
  pick.physical = {3.5, 2.25, 4.0};
  pick.probe_node = "polar";
  pick.probe_dataset = "Polar";
  f.vs->set_pick(pick);
  EXPECT_EQ(f.vs->probe().status, app::ProbeState::Status::Pending);
  ASSERT_TRUE(f.pump_until([&] { return f.vs->probe().status != app::ProbeState::Status::Pending; }));
  ASSERT_EQ(f.vs->probe().status, app::ProbeState::Status::Done) << f.vs->probe().error;
  EXPECT_EQ(f.vs->probe().sample["values"], Json::array({0.25, -0.5, 0.75}));
  EXPECT_EQ(f.vs->probe().sample["position"], Json::array({3.5, 2.25, 4.0}));
  EXPECT_EQ(f.vs->probe().target["node"], "polar");
  f.vs->probe_position({1.0, 1.0, 1.0});
  ASSERT_TRUE(f.pump_until([&] { return f.vs->probe().status == app::ProbeState::Status::Done; }));
  EXPECT_EQ(f.vs->probe().sample["position"], Json::array({1.0, 1.0, 1.0}));
  EXPECT_EQ(f.stats().value("probes", -1), 2);
  /* A payload opened from a file has no data source. */
  ASSERT_TRUE(f.vs->open_path(fixture_stkp().string()));
  f.vs->set_pick(pick);
  EXPECT_EQ(f.vs->probe().status, app::ProbeState::Status::Unavailable);
}

TEST(ViewerFake, LayerVisibilityAndOpacityOverrides)
{
  FakeViewer f;
  open_run(f);
  std::vector<std::string> ids;
  for (const auto &r : f.vs->layers()) {
    ids.push_back(r.id);
  }
  EXPECT_EQ(ids, (std::vector<std::string>{"surface_layer", "box", "legend", "axes"}));
  const auto base = f.vs->base_payload();
  const uint64_t serial = f.vs->payload_serial();
  f.vs->set_layer_opacity("surface_layer", 0.5);
  EXPECT_GT(f.vs->payload_serial(), serial);
  EXPECT_EQ(f.vs->base_payload(), base) << "the delivered payload is untouched";
  EXPECT_EQ(f.vs->payload()->layer("surface_layer")->at("appearance")["opacity"], 0.5);
  f.vs->set_layer_visible("box", false);
  EXPECT_FALSE(f.vs->layers()[1].visible);
  /* Overrides stay across steps (kept by layer id). */
  ASSERT_TRUE(f.pump_until([&] { return f.vs->prefetched_count() >= 1 && !f.vs->evaluating(); }));
  f.vs->set_step_index(1);
  EXPECT_EQ(f.vs->payload()->layer("surface_layer")->at("appearance")["opacity"], 0.5);
  EXPECT_FALSE(f.vs->layers()[1].visible);
}

TEST(ViewerFake, SequenceExportCollectsEveryStep)
{
  FakeViewer f;
  open_run(f);
  f.vs->export_settings.path = (f.dir.path() / "out" / "domains.png").string();
  f.vs->export_settings.sequence = true;
  f.vs->request_export();
  app::ExportJob *job = f.vs->export_job();
  ASSERT_NE(job, nullptr);
  EXPECT_EQ(job->frames.size(), 3u);
  EXPECT_EQ(job->parameter, "step");
  ASSERT_TRUE(f.pump_until([&] { return f.vs->export_job() && f.vs->export_job()->ready; }));
  for (const auto &[step, payload] : f.vs->export_job()->frames) {
    ASSERT_NE(payload, nullptr) << step.dump();
    EXPECT_EQ(payload->manifest["view"]["time"]["step"], step);
  }
  fs::create_directories(f.dir.path() / "out");
  std::string err;
  ASSERT_TRUE(ViewerState::write_series(*f.vs->export_job(), &err)) << err;
  const Json series = io::read_json_file(f.dir.path() / "out" / "domains.series.json");
  EXPECT_EQ(series["schema"], "stk.series/1");
  EXPECT_EQ(series["parameter"], "step");
  ASSERT_EQ(series["frames"].size(), 3u);
  EXPECT_EQ(series["frames"][0]["step"], 0);
  EXPECT_EQ(series["frames"][2]["outputs"]["image"], "domains.00000002.png");
  EXPECT_NO_THROW(io::Series::from_json(series));
  f.vs->finish_export(true, "done");
  EXPECT_EQ(f.vs->export_job(), nullptr);
}

TEST(ViewerFake, TaskSourceEvaluatesThroughTheBridge)
{
  FakeViewer f;
  f.vs->refresh_metadata();
  ASSERT_TRUE(f.pump_until([&] { return f.vs->presets_loaded() && !f.vs->catalog().is_null(); }));
  app::OpenResultRequest req;
  req.connection = "runtime:lab";
  req.task_id = "task-123";
  req.preset = "muferro-domains";
  ASSERT_TRUE(f.vs->open(req));
  EXPECT_EQ(f.vs->source().kind, SourceKind::Task);
  EXPECT_EQ(f.vs->source_label(), "task-123 @ runtime:lab");
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() != nullptr; })) << f.vs->eval_error();
}

TEST(ViewerFake, OpenBeforeMetadataWaitsForIt)
{
  FakeViewer f;
  ASSERT_TRUE(f.vs->open_path(f.run_dir(), "muferro-domains"));
  EXPECT_EQ(f.vs->payload(), nullptr);
  ASSERT_TRUE(f.pump_until([&] { return f.vs->payload() != nullptr; })) << f.vs->eval_error();
  EXPECT_EQ(f.vs->last_eval()->reason, "open");
}

/* -------------------------------------------------------------------- */
/* Paths, result and series folders (no bridge). */

TEST(ViewerPaths, ClassifiesPayloadsResultsAndRunFolders)
{
  TempDir d("viewer-paths");
  std::string err;
  EXPECT_EQ(app::classify_path(fixture_stkp().string()).kind, SourceKind::Payload);
  EXPECT_EQ(app::classify_path(fixture_payload_dir().string()).kind, SourceKind::Payload);
  const app::ViewerSource m = app::classify_path((fixture_payload_dir() / "manifest.json").string());
  EXPECT_EQ(m.kind, SourceKind::Payload);
  EXPECT_EQ(m.path, fixture_payload_dir().string());
  write_result_dir(d.path() / "result");
  EXPECT_EQ(app::classify_path((d.path() / "result").string()).kind, SourceKind::ResultDir);
  EXPECT_EQ(app::classify_path((d.path() / "result" / "result.json").string()).kind, SourceKind::ResultDir);
  write_series_dir(d.path() / "series", {1, 2});
  const app::ViewerSource s = app::classify_path((d.path() / "series").string());
  EXPECT_EQ(s.kind, SourceKind::ResultDir);
  EXPECT_TRUE(s.series);
  fs::create_directories(d.path() / "run" / "out");
  write_text((d.path() / "run" / "out" / "Polar.00000003.dat").string(), "x");
  const app::ViewerSource r = app::classify_path((d.path() / "run").string());
  EXPECT_EQ(r.kind, SourceKind::RunDir);
  EXPECT_EQ(app::guess_preset(r.path), "muferro-domains");
  fs::create_directories(d.path() / "other");
  EXPECT_EQ(app::guess_preset((d.path() / "other").string()), "");
  EXPECT_EQ(app::classify_path((d.path() / "missing").string(), &err).kind, SourceKind::None);
  EXPECT_NE(err.find("not found"), std::string::npos);
  write_text((d.path() / "notes.txt").string(), "x");
  EXPECT_EQ(app::classify_path((d.path() / "notes.txt").string(), &err).kind, SourceKind::None);
}

TEST(ViewerPaths, OpensResultAndSeriesFolders)
{
  TempDir d("viewer-results");
  app::AppStore store;
  ViewerState &vs = store.viewer();
  write_result_dir(d.path() / "result");
  ASSERT_TRUE(vs.open_path((d.path() / "result").string())) << vs.open_error();
  EXPECT_EQ(vs.source().kind, SourceKind::ResultDir);
  ASSERT_NE(vs.payload(), nullptr);
  EXPECT_TRUE(vs.result().has_value());
  EXPECT_EQ(vs.layers().size(), 4u);

  write_series_dir(d.path() / "series", {10, 20, 30});
  ASSERT_TRUE(vs.open_path((d.path() / "series").string())) << vs.open_error();
  ASSERT_EQ(vs.step_choices().size(), 3u);
  EXPECT_EQ(vs.shown_step(), Json(30)) << "the last frame first";
  const uint64_t serial = vs.payload_serial();
  vs.set_step_index(0);
  EXPECT_EQ(vs.shown_step(), Json(10));
  EXPECT_GT(vs.payload_serial(), serial);
  vs.step_by(1);
  EXPECT_EQ(vs.shown_step(), Json(20));
  vs.step_latest();
  EXPECT_EQ(vs.shown_step(), Json(30));
  /* Plain payloads: no steps, no evaluation, no probe source. */
  ASSERT_TRUE(vs.open_path(fixture_stkp().string()));
  EXPECT_TRUE(vs.step_choices().empty());
  EXPECT_FALSE(vs.source().evaluates());
}

TEST(ViewerPaths, SequenceFileNames)
{
  EXPECT_EQ(app::sequence_frame_path("/tmp/out/view.png", Json(12)), "/tmp/out/view.00000012.png");
  EXPECT_EQ(app::sequence_frame_path("/tmp/out/view.png", Json("latest")), "/tmp/out/view.latest.png");
  EXPECT_EQ(app::sequence_manifest_path("/tmp/out/view.png"), "/tmp/out/view.series.json");
}
