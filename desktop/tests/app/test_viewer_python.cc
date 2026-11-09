/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The Viewer's state and GPU viewer against the real Python bridge (local graph.evaluate
 * of muferro-domains on a fake muFerro run): a client-stage change re-runs no data node and the
 * view re-renders; a data-stage change re-runs the data nodes; a cached step switch completes in
 * under 300 ms with the camera kept; a GPU pick is probed for its original value; a collected
 * open whose registered bytes changed must keep the previous Viewer and its unsaved draft. */

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>

#include <gtest/gtest.h>

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "stk/viewer_gpu/viewer.hh"
#include "viewer_support.hh"

namespace stk::apptest {
extern gfx::Gpu *g_gpu;
extern bool g_skipped_all;
}  // namespace stk::apptest

using namespace stk;
using namespace stk::apptest;
using stk::io::Json;

namespace {

double now_ms()
{
  return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

gfx::Image render(viewer_gpu::Viewer &v, int w, int h)
{
  viewer_gpu::ExportOptions eo;
  eo.width = w;
  eo.height = h;
  gfx::Image img;
  std::string err;
  EXPECT_TRUE(v.render_image(eo, img, err)) << err;
  return img;
}

double differing_fraction(const gfx::Image &a, const gfx::Image &b)
{
  if (a.width != b.width || a.height != b.height || a.rgba.empty()) {
    return 1.0;
  }
  size_t n = 0;
  for (size_t i = 0; i < a.rgba.size(); i += 4) {
    int d = 0;
    for (int k = 0; k < 3; k++) {
      d = std::max(d, std::abs(int(a.rgba[i + k]) - int(b.rgba[i + k])));
    }
    n += d > 24 ? 1 : 0;
  }
  return double(n) / double(a.rgba.size() / 4);
}

bool contains(const std::vector<std::string> &v, const std::string &s)
{
  return std::find(v.begin(), v.end(), s) != v.end();
}

}  // namespace

TEST(PythonViewer, MolecularTopologyAndRealTimestepsRenderWithoutChangingTheCamera)
{
  std::string reason;
  const std::string python = graph_python(reason);
  if (python.empty()) { g_skipped_all = true; GTEST_SKIP() << reason; }
  ASSERT_NE(g_gpu, nullptr);
  TempDir dir("molecule-python");
  const auto run = dir.str() + "/molecule";
  std::filesystem::create_directories(run);
  ASSERT_TRUE(write_text(run + "/state.data", R"(Full real molecular display fixture

2 atoms
1 bonds
0 angles
0 dihedrals
0 impropers

2 atom types
1 bond types

0 8 xlo xhi
0 8 ylo yhi
0 8 zlo zhi

Masses

1 12.011
2 15.9994

Atoms # full

27 7 2 -0.2 3.2074 4 4
9 7 1 0.2 2 4 4

Bonds

8 1 9 27
)"));
  ASSERT_TRUE(write_text(run + "/trajectory.dump", R"(ITEM: TIMESTEP
0
ITEM: NUMBER OF ATOMS
2
ITEM: BOX BOUNDS pp pp pp
0 8
0 8
0 8
ITEM: ATOMS id mol type q xu yu zu
27 7 2 -0.2 3.2074 4 4
9 7 1 0.2 2 4 4
ITEM: TIMESTEP
100
ITEM: NUMBER OF ATOMS
2
ITEM: BOX BOUNDS pp pp pp
0 8
0 8
0 8
ITEM: ATOMS id mol type q xu yu zu
9 7 1 0.2 4 4 4
27 7 2 -0.2 5.2074 4 4
)"));
  ManualLoop loop;
  auto client = bridge::Client::create(python_bridge_options(python, dir.str(), loop.executor()));
  std::string error;
  ASSERT_TRUE(client->start(&error)) << error;
  ASSERT_TRUE(client->wait_ready(120)) << client->bridge_log().text();
  {
    app::AppStore store;
    store.set_bridge(client.get());
    auto &vs = store.viewer();
    vs.prefetch_neighbours = false;
    auto ready = [&] {
      return loop.pump_until([&] { return !vs.evaluating() && (vs.payload() || !vs.eval_error().empty()); },
                             120, [&] { vs.pump(); });
    };
    ASSERT_TRUE(vs.open_path(run, "lammps-molecule", {{"topology", "state.data"}, {"trajectory", "trajectory.dump"}}));
    ASSERT_TRUE(ready()) << vs.eval_error() << client->bridge_log().text();
    ASSERT_NE(vs.payload(), nullptr) << vs.eval_error();
    ASSERT_EQ(vs.step_choices().size(), 2u);
    const auto *atoms = vs.payload()->layer("atoms");
    ASSERT_NE(atoms, nullptr);
    EXPECT_EQ((*atoms)["type"], "points");
    EXPECT_EQ((*atoms)["appearance"]["render_as"], "spheres");
    EXPECT_FALSE(atoms->contains("pick"));
    EXPECT_EQ((*atoms)["appearance"]["radius"], 0.3);
    EXPECT_EQ(vs.payload()->doubles((*atoms)["attributes"]["atom_id"]["accessor"].get<std::string>()),
              (std::vector<double>{9, 27}));
    EXPECT_EQ(vs.payload()->doubles((*atoms)["attributes"]["atom_type"]["accessor"].get<std::string>()),
              (std::vector<double>{1, 2}));
    const auto charges = vs.payload()->doubles((*atoms)["attributes"]["charge"]["accessor"].get<std::string>());
    ASSERT_EQ(charges.size(), 2u);
    EXPECT_NEAR(charges[0], 0.2, 1e-7);  // GPU delivery uses float32; reader values remain float64.
    EXPECT_NEAR(charges[1], -0.2, 1e-7);
    ASSERT_NE(vs.payload()->layer("bonds"), nullptr);
    ASSERT_NE(vs.payload()->layer("box"), nullptr);
    viewer_gpu::Viewer viewer(g_gpu->fonts());
    viewer.set_payload(vs.payload());
    auto changed_camera = viewer.camera();
    changed_camera.position += viewer::dvec3{1.0, 0.5, 0.25};
    viewer.set_camera(changed_camera);
    const auto latest = render(viewer, 400, 300);
    const auto layer_infos = viewer.layers();
    for (const auto &[id, count] : {std::pair{"atoms", 2u}, {"bonds", 1u}, {"box", 12u}}) {
      const auto layer = std::find_if(layer_infos.begin(), layer_infos.end(),
                                     [&](const auto &item) { return item.id == id; });
      ASSERT_NE(layer, layer_infos.end()) << id;
      EXPECT_EQ(layer->elements, count) << id;
    }
    const auto camera = viewer.camera();
    const auto serial = vs.payload_serial();
    vs.set_parameter("step", ui::FormValue::number(0));
    ASSERT_TRUE(loop.pump_until([&] { return vs.payload_serial() != serial && !vs.evaluating(); },
                               120, [&] { vs.pump(); })) << vs.eval_error();
    viewer.set_payload(vs.payload());
    const auto first = render(viewer, 400, 300);
    EXPECT_GT(differing_fraction(latest, first), 0.001);
    EXPECT_EQ(viewer.camera().position, camera.position);
    EXPECT_EQ(viewer.camera().focal_point, camera.focal_point);
    const auto image_path = std::filesystem::path(STK_APP_TEST_SCRATCH) /
        (std::string("molecule-") + g_gpu->backend_name() + ".png");
    std::filesystem::create_directories(image_path.parent_path());
    ASSERT_TRUE(gfx::png_write(image_path.string(), first));
  }
  client->close();
}

TEST(PythonViewer, OpacityFormUpdatesVolumeWithoutRerunningData)
{
  std::string reason;
  const std::string python = graph_python(reason);
  if (python.empty()) {
    g_skipped_all = true;
    GTEST_SKIP() << reason;
  }
  ASSERT_NE(g_gpu, nullptr);
  TempDir dir("volume-opacity");
  const std::string run = dir.str() + "/run";
  ASSERT_TRUE(write_fake_run(python, run));
  ManualLoop loop;
  auto client = bridge::Client::create(python_bridge_options(python, dir.str(), loop.executor()));
  std::string err;
  ASSERT_TRUE(client->start(&err)) << err;
  ASSERT_TRUE(client->wait_ready(120)) << client->bridge_log().text();
  {
    app::AppStore store;
    store.set_bridge(client.get());
    auto &vs = store.viewer();
    auto ready = [&]() {
      return loop.pump_until([&]() { return (vs.payload() || !vs.eval_error().empty()) && !vs.evaluating(); },
                             120, [&]() { vs.pump(); });
    };
    ASSERT_TRUE(vs.open_path(run, "volume"));
    ASSERT_TRUE(ready()) << vs.eval_error() << client->bridge_log().text();
    const auto before = vs.payload();
    ASSERT_NE(before, nullptr) << vs.eval_error() << client->bridge_log().text();
    const Json *volume = before->layer("volume");
    ASSERT_NE(volume, nullptr);
    viewer_gpu::Viewer viewer(g_gpu->fonts());
    viewer.set_payload(before);
    const auto opaque = render(viewer, 400, 300);

    ui::FakeTextMeasurer measurer;
    ui::ContextConfig cfg;
    cfg.measurer = &measurer;
    ui::Context ui(cfg);
    ui::SchemaNode schema;
    schema.type = ui::SchemaType::Object;
    schema.properties = {*vs.schema().property("opacity")};
    ASSERT_EQ(schema.properties[0].stage, "client");
    ui.begin_frame({320, 700}, 100);
    ui::build_form(ui.block("opacity_form", {0, 0, 320, 700}).layout(), schema, vs.form());
    ui.end_frame();
    const auto *alpha = ui.find("opacity/1/alpha");
    ASSERT_NE(alpha, nullptr);
    const uint64_t serial = vs.payload_serial();
    alpha->number.assign(0.0);
    ASSERT_TRUE(loop.pump_until([&]() { return vs.payload_serial() != serial && !vs.evaluating(); },
                                120, [&]() { vs.pump(); })) << vs.eval_error();
    ASSERT_TRUE(vs.last_eval());
    EXPECT_EQ(vs.last_eval()->reason, "client");
    EXPECT_TRUE(vs.last_eval()->data_nodes.empty());
    for (const auto &node : vs.last_eval()->evaluated) {
      EXPECT_FALSE(contains(vs.data_nodes(), node)) << node;
    }
    const Json *updated = vs.payload()->layer("volume");
    ASSERT_NE(updated, nullptr);
    EXPECT_EQ((*updated)["data"], (*volume)["data"]);
    for (const auto &point : (*updated)["transfer_function"]["opacity"]) {
      EXPECT_EQ(point[1], 0);
    }
    viewer.set_payload(vs.payload());
    const auto transparent = render(viewer, 400, 300);
    EXPECT_GT(differing_fraction(opaque, transparent), 0.005);
  }
  client->close();
}

TEST(ViewerFormsGpu, VolumePropertiesAtNarrowWidth)
{
  ASSERT_NE(g_gpu, nullptr);
  for (const char *lang : {"en", "zh_CN"}) {
    app::ShellOptions opts;
    opts.language = lang;
    opts.interactive = false;
    app::AppShell shell(opts);
    shell.layout_path.clear();
    wm::Screen screen;
    shell.install(screen, nullptr);
    shell.build_default_layout(screen);
    ASSERT_TRUE(shell.activate_editor(&screen, app::kEditorProperties, true).ok());
    auto &vs = shell.store().viewer();
    vs.set_metadata(repo_presets(), repo_catalog());
    vs.select_preset("volume");
    wm::DrawContext dc;
    dc.ui_scale = 1;
    dc.fonts = &g_gpu->fonts();
    dc.rect = {0, 0, 320, 900};
    dc.now = 100;
    gfx::Image img;
    std::string err;
    ASSERT_TRUE(gfx::render_offscreen(320, 900, [&]() { screen.draw(dc); }, img, err)) << err;
    const auto *preview = screen.ui()->find("opacity/preview");
    ASSERT_NE(preview, nullptr);
    EXPECT_GE(preview->rect.w, 180);
    EXPECT_FALSE(preview->rect.intersect(preview->clip).empty());
    const auto *add = screen.ui()->find("opacity/add");
    ASSERT_NE(add, nullptr);
    EXPECT_FALSE(add->rect.intersect(add->clip).empty());
    for (size_t i = 3; i < img.rgba.size(); i += 4) {
      img.rgba[i] = 255;
    }
    const auto path = std::filesystem::path(STK_APP_TEST_SCRATCH) /
                      (std::string("volume-properties-") + lang + "-" + g_gpu->backend_name() + ".png");
    std::filesystem::create_directories(path.parent_path());
    ASSERT_TRUE(gfx::png_write(path.string(), img));
  }
}

TEST(PythonViewer, ClientAndDataStagesStepSwitchAndProbe)
{
  std::string reason;
  const std::string python = graph_python(reason);
  if (python.empty()) {
    g_skipped_all = true;
    GTEST_SKIP() << reason;
  }
  ASSERT_NE(g_gpu, nullptr);
  TempDir dir("viewer-python");
  const std::string run = dir.str() + "/run";
  ASSERT_TRUE(write_fake_run(python, run));

  ManualLoop loop;
  auto client = bridge::Client::create(python_bridge_options(python, dir.str(), loop.executor()));
  std::string err;
  ASSERT_TRUE(client->start(&err)) << err;
  ASSERT_TRUE(client->wait_ready(120)) << client->bridge_log().text();
  {
    app::AppStore store;
    store.set_bridge(client.get());
    app::ViewerState &vs = store.viewer();
    /* Isolate stage-cache assertions from neighbour work: cancelling a prefetch stuck in native
     * code can restart the worker and legitimately drop memory-only entries (e.g. the run index).
     * Enable prefetch below for the separate cached-step assertions. */
    vs.prefetch_neighbours = false;
    auto pump_until = [&](const std::function<bool()> &until, double timeout = 300.0) {
      return loop.pump_until(until, timeout, [&]() { vs.pump(); });
    };

    /* 1. Open the run folder: muferro-domains evaluates in the bridge. */
    ASSERT_TRUE(vs.open_path(run, "muferro-domains"));
    ASSERT_TRUE(pump_until([&] { return vs.payload() != nullptr && !vs.evaluating(); }))
        << vs.eval_error() << "\n" << client->bridge_log().text();
    ASSERT_TRUE(vs.last_eval().has_value());
    const std::vector<std::string> data_nodes = vs.data_nodes();
    std::printf("METRIC open: evaluated %zu nodes (%zu data) in %.3f s; data nodes of the graph: %zu\n",
                vs.last_eval()->evaluated.size(), vs.last_eval()->data_nodes.size(), vs.last_eval()->seconds,
                data_nodes.size());
    EXPECT_TRUE(contains(vs.last_eval()->evaluated, "domains"));
    EXPECT_GT(vs.progress().finished + vs.progress().cached, 0) << "graph.progress events arrived";
    ASSERT_EQ(vs.step_choices().size(), 3u) << "fake run: steps 0, 1, 2";

    viewer_gpu::Viewer v(g_gpu->fonts());
    v.set_payload(vs.payload());
    const gfx::Image iso = render(v, 400, 300);
    const viewer::CameraPose iso_camera = v.camera();

    /* 2. Client stage (view: iso -> +x): no data node re-runs, and the view re-renders. */
    const uint64_t serial = vs.payload_serial();
    ASSERT_EQ(vs.param_stage("view"), "client");
    vs.set_parameter("view", ui::FormValue::string("+x"));
    ASSERT_TRUE(pump_until([&] { return vs.payload_serial() != serial && !vs.evaluating(); }));
    const app::EvalRecord client_rec = *vs.last_eval();
    std::string ev;
    for (const std::string &n : client_rec.evaluated) {
      ev += n + " ";
    }
    std::printf("METRIC client-stage change: evaluated [%s] data nodes %zu, %.3f s, cache hits %lld\n", ev.c_str(),
                client_rec.data_nodes.size(), client_rec.seconds, (long long)client_rec.cache_hits);
    EXPECT_EQ(client_rec.reason, "client");
    EXPECT_FALSE(client_rec.from_cache);
    EXPECT_TRUE(client_rec.data_nodes.empty()) << "a client-stage change re-runs no data node: " << ev;
    for (const std::string &n : client_rec.evaluated) {
      EXPECT_FALSE(contains(data_nodes, n)) << n;
    }
    EXPECT_TRUE(contains(client_rec.evaluated, "scene"));
    v.set_payload(vs.payload());
    const gfx::Image side = render(v, 400, 300);
    const double changed = differing_fraction(iso, side);
    std::printf("METRIC re-render after the client change: %.1f %% of the pixels changed\n", changed * 100.0);
    EXPECT_GT(changed, 0.05) << "the +x view differs from the iso view";
    EXPECT_GT(viewer::length(v.camera().position - iso_camera.position), 1e-6) << "the camera follows the new view";

    /* 3. Data stage (|P| threshold): the data nodes re-run. */
    vs.set_parameter("min_magnitude", ui::FormValue::number(0.3));
    ASSERT_TRUE(pump_until([&] { return vs.last_eval()->reason == "data" && !vs.evaluating(); }));
    const app::EvalRecord data_rec = *vs.last_eval();
    std::printf("METRIC data-stage change: evaluated %zu nodes, data nodes %zu (", data_rec.evaluated.size(),
                data_rec.data_nodes.size());
    for (const std::string &n : data_rec.data_nodes) {
      std::printf("%s ", n.c_str());
    }
    std::printf(") %.3f s\n", data_rec.seconds);
    EXPECT_TRUE(contains(data_rec.data_nodes, "domains"));
    EXPECT_TRUE(contains(data_rec.evaluated, "surfaces"));

    /* 4. Cached step switch: the neighbour (step 1) is prefetched in the background, the switch
     *    is served by the viewer cache and uploaded ahead; the camera is kept. */
    vs.prefetch_neighbours = true;
    v.set_payload(vs.payload());
    render(v, 400, 300);
    viewer::CameraPose orbited = v.camera();
    viewer::orbit(orbited, viewer::NavigationStyle::Blender, 40, -25, {400, 300});
    v.set_camera(orbited);
    ASSERT_TRUE(pump_until([&] { return vs.prefetched_count() >= 1 && !vs.evaluating(); }));
    for (const auto &p : vs.take_prefetched()) {
      v.prefetch(p);
    }
    const int started = vs.evaluations_started();
    const double t0 = now_ms();
    vs.set_step_index(1);
    v.set_payload(vs.payload());
    const gfx::Image step1 = render(v, 400, 300);
    const double switch_ms = now_ms() - t0;
    std::printf("METRIC cached step switch (2 -> 1): state %.2f ms, state + GPU set_payload + 400x300 render %.2f ms\n",
                vs.last_step_switch_ms(), switch_ms);
    EXPECT_FALSE(vs.evaluating()) << "no bridge evaluation for the switch";
    EXPECT_LE(vs.evaluations_started(), started + 1) << "at most the next neighbour's prefetch";
    EXPECT_TRUE(vs.last_eval()->from_cache);
    EXPECT_EQ(vs.shown_step(), Json(1));
    EXPECT_LT(switch_ms, 300.0);
    EXPECT_LT(viewer::length(v.camera().position - orbited.position), 1e-9) << "camera kept across steps";
    /* Also through the bridge (its node cache): revisit step 2 with the viewer cache bypassed. */
    vs.set_step_index(2);
    const double t1 = now_ms();
    vs.evaluate_now("manual");
    ASSERT_TRUE(pump_until([&] { return !vs.evaluating() && vs.last_eval()->reason == "manual"; }));
    const double bridge_ms = now_ms() - t1;
    std::printf("METRIC step revisit through the bridge (node cache): %.1f ms, evaluated %zu nodes\n", bridge_ms,
                vs.last_eval()->evaluated.size());
    EXPECT_TRUE(vs.last_eval()->data_nodes.empty());
    EXPECT_LT(bridge_ms, 3000.0);

    /* 5. Pick on the GPU and probe the original value. */
    v.set_payload(vs.payload());
    v.reset_camera();
    render(v, 400, 300);
    viewer_gpu::PickResult hit;
    for (int dy = 0; dy <= 60 && !hit.hit; dy += 10) {
      hit = v.pick(200.5, 150.5 + dy, 400, 300);
    }
    ASSERT_TRUE(hit.hit) << "the domain surfaces cover the centre";
    app::PickInfo pick;
    pick.layer_id = hit.layer_id;
    pick.layer_type = hit.layer_type;
    pick.element = hit.element;
    pick.physical = hit.physical;
    if (hit.probe) {
      pick.probe_node = hit.probe->node;
      pick.probe_dataset = hit.probe->dataset;
    }
    vs.set_pick(pick);
    ASSERT_TRUE(pump_until([&] { return vs.probe().status != app::ProbeState::Status::Pending; }, 120));
    ASSERT_EQ(vs.probe().status, app::ProbeState::Status::Done) << vs.probe().error;
    std::printf("METRIC probe at %.4f %.4f %.4f (%s #%u): %s\n", hit.physical[0], hit.physical[1], hit.physical[2],
                hit.layer_id.c_str(), hit.element, vs.probe().sample.dump().c_str());
    EXPECT_EQ(vs.probe().sample["values"].size(), 3u) << "Polar has three components";
    EXPECT_EQ(vs.probe().sample.value("source", ""), "original_point_data");
    vs.close();
    store.set_bridge(nullptr);
  }
  client->close();
  loop.run_ready();
}

TEST(PythonViewer, CollectedFramesKeepTheirProofAcrossCachedStepsAndWorkspaceRestore)
{
  std::string reason;
  const auto python = graph_python(reason);
  if (python.empty()) { g_skipped_all = true; GTEST_SKIP() << reason; }
  ASSERT_NE(g_gpu, nullptr);
  TempDir dir("viewer-collected-python");
  const auto run = dir.str() + "/run";
  ASSERT_TRUE(write_fake_run(python, run));
  Json files = Json::array();
  for (const auto &entry : std::filesystem::recursive_directory_iterator(run)) {
    if (entry.is_regular_file()) {
      files.push_back({{"path", entry.path().lexically_relative(dir.path()).generic_string()},
                       {"sha256", core::Sha256::hex(read_text(entry.path().string()))}});
    }
  }
  const Json proof = {{"project_root", dir.str()}, {"case_path", "run"}, {"files", files}};
  ManualLoop loop;
  auto options = python_bridge_options(python, dir.str(), loop.executor());
  options.strict = options.validate = true;
  auto client = bridge::Client::create(std::move(options));
  std::string error;
  ASSERT_TRUE(client->start(&error)) << error;
  ASSERT_TRUE(client->wait_ready(120)) << client->bridge_log().text();
  {
    app::AppStore store;
    store.set_bridge(client.get());
    auto &vs = store.viewer();
    vs.prefetch_neighbours = false;
    const auto wait = [&](const std::function<bool()> &condition) {
      return loop.pump_until(condition, 120, [&] { vs.pump(); });
    };
    ASSERT_TRUE(vs.open_path(run, "muferro-collected-domains", Json(), proof));
    ASSERT_TRUE(wait([&] { return vs.payload() && !vs.evaluating(); }))
        << vs.eval_error() << client->bridge_log().text();
    ASSERT_EQ(vs.shown_step(), Json(2));
    ASSERT_EQ(vs.step_choices().size(), 3u);
    const auto initial_payload = vs.base_payload();
    const auto state = vs.save_workspace_state();
    viewer_gpu::Viewer viewer(g_gpu->fonts());
    viewer.set_payload(vs.payload());
    const auto initial_image = render(viewer, 400, 300);
    ASSERT_EQ(initial_image.rgba.size(), 400u * 300u * 4u);
    app::PickInfo pick;
    pick.probe_node = "polar";
    pick.probe_dataset = "Polar";
    pick.physical = {1.0, 1.0, 1.0};
    vs.set_pick(pick);
    ASSERT_TRUE(wait([&] { return vs.probe().status != app::ProbeState::Status::Pending; }));
    ASSERT_EQ(vs.probe().status, app::ProbeState::Status::Done) << vs.probe().error;
    const auto original_sample = vs.probe().sample;

    // The latest frame is already in the native frame cache when this earlier frame is selected.
    vs.set_step_index(0);
    ASSERT_TRUE(wait([&] { return vs.shown_step() == Json(0) && !vs.evaluating(); })) << vs.eval_error();
    const auto previous_payload = vs.base_payload();
    const auto previous_serial = vs.payload_serial();
    const auto frame = std::filesystem::path(run) / "Polar.00000002.dat";
    const auto original = read_text(frame.string());
    const auto modified = std::filesystem::last_write_time(frame);
    auto replacement = original;
    const auto digit = replacement.find_last_of("0123456789");
    ASSERT_NE(digit, std::string::npos);
    replacement[digit] = replacement[digit] == '0' ? '1' : '0';
    const auto rewrite = [&](const std::string &bytes) {
      std::fstream stream(frame, std::ios::in | std::ios::out | std::ios::binary);
      stream.write(bytes.data(), std::streamsize(bytes.size()));
      stream.close();
      EXPECT_TRUE(stream.good());
      std::filesystem::last_write_time(frame, modified);
      EXPECT_EQ(std::filesystem::file_size(frame), original.size());
      EXPECT_EQ(std::filesystem::last_write_time(frame), modified);
    };
    rewrite(replacement);
    vs.set_step_index(2);
    ASSERT_TRUE(wait([&] { return !vs.eval_error().empty() && !vs.evaluating(); }));
    EXPECT_EQ(vs.base_payload(), previous_payload);
    EXPECT_EQ(vs.payload_serial(), previous_serial);
    EXPECT_EQ(vs.shown_step(), Json(0));
    EXPECT_EQ(vs.source().source_proof, proof);

    // Restore is inert, and its next explicit evaluation and probe still check the recorded bytes.
    ASSERT_TRUE(vs.load_workspace_state(state, initial_payload));
    EXPECT_TRUE(vs.workspace_suspended());
    EXPECT_EQ(vs.source().source_proof, proof);
    vs.evaluate_now();
    ASSERT_TRUE(wait([&] { return !vs.eval_error().empty() && !vs.evaluating(); }));
    EXPECT_EQ(vs.base_payload(), initial_payload);
    vs.set_pick(pick);
    ASSERT_TRUE(wait([&] { return vs.probe().status != app::ProbeState::Status::Pending; }));
    EXPECT_EQ(vs.probe().status, app::ProbeState::Status::Failed);
    EXPECT_TRUE(vs.probe().sample.is_null());

    rewrite(original);
    const auto restored_serial = vs.payload_serial();
    vs.evaluate_now();
    ASSERT_TRUE(wait([&] { return vs.payload_serial() != restored_serial && !vs.evaluating(); }))
        << vs.eval_error() << client->bridge_log().text();
    EXPECT_TRUE(vs.eval_error().empty());
    EXPECT_EQ(vs.shown_step(), Json(2));
    viewer.set_payload(vs.payload());
    EXPECT_LT(differing_fraction(initial_image, render(viewer, 400, 300)), 0.001);
    vs.set_pick(pick);
    ASSERT_TRUE(wait([&] { return vs.probe().status != app::ProbeState::Status::Pending; }));
    ASSERT_EQ(vs.probe().status, app::ProbeState::Status::Done) << vs.probe().error;
    EXPECT_EQ(vs.probe().sample, original_sample);
    vs.close();
    store.set_bridge(nullptr);
  }
  client->close();
  loop.run_ready();
}

TEST(PythonViewer, FailedCollectedOpenKeepsThePreviousViewerAndItsDraft)
{
  std::string reason;
  const auto python = graph_python(reason);
  if (python.empty()) { g_skipped_all = true; GTEST_SKIP() << reason; }
  ASSERT_NE(g_gpu, nullptr);
  TempDir dir("viewer-guarded-open-python");
  const auto proof_of = [&](const std::string &case_path) {
    Json files = Json::array();
    for (const auto &entry : std::filesystem::recursive_directory_iterator(dir.path() / case_path)) {
      if (entry.is_regular_file()) {
        files.push_back({{"path", entry.path().lexically_relative(dir.path()).generic_string()},
                         {"sha256", core::Sha256::hex(read_text(entry.path().string()))}});
      }
    }
    return Json{{"project_root", dir.str()}, {"case_path", case_path}, {"files", files}};
  };
  const auto run_a = dir.str() + "/run-a", run_b = dir.str() + "/run-b";
  ASSERT_TRUE(write_fake_run(python, run_a));
  ASSERT_TRUE(write_fake_run(python, run_b));
  const Json proof_a = proof_of("run-a"), proof_b = proof_of("run-b");
  const std::string preset = "muferro-collected-domains";
  ManualLoop loop;
  auto options = python_bridge_options(python, dir.str(), loop.executor());
  options.strict = options.validate = true;
  auto client = bridge::Client::create(std::move(options));
  std::string error;
  ASSERT_TRUE(client->start(&error)) << error;
  ASSERT_TRUE(client->wait_ready(120)) << client->bridge_log().text();
  {
    app::AppStore store;
    store.set_bridge(client.get());
    auto &vs = store.viewer();
    vs.prefetch_neighbours = false;
    const auto wait = [&](const std::function<bool()> &condition, double timeout = 120) {
      return loop.pump_until(condition, timeout, [&] { vs.pump(); });
    };
    const auto failure = [&] { return vs.open_error() + "|" + vs.eval_error(); };

    // A good collected Viewer A with an unsaved data-stage draft (automatic evaluation off).
    ASSERT_TRUE(vs.open_path(run_a, preset, Json(), proof_a));
    ASSERT_TRUE(wait([&] { return vs.payload() && !vs.evaluating(); })) << failure() << client->bridge_log().text();
    ASSERT_EQ(vs.shown_step(), Json(2));
    vs.set_auto_evaluate(false);
    vs.set_parameter("min_magnitude", ui::FormValue::number(0.3));
    ASSERT_EQ(vs.pending_edit(), "data");
    ASSERT_EQ(vs.parameters().value("min_magnitude", Json()), Json(0.3));
    const auto a_base = vs.base_payload(), a_payload = vs.payload();
    const auto a_serial = vs.payload_serial(), a_camera = vs.camera_serial();
    const auto a_step = vs.shown_step();
    const auto a_parameters = vs.parameters();
    viewer_gpu::Viewer viewer(g_gpu->fonts());
    viewer.set_payload(a_payload);
    const auto a_image = render(viewer, 400, 300);
    const auto a_intact = [&] {
      EXPECT_EQ(vs.source().path, run_a) << "the previous Viewer source was dropped";
      EXPECT_TRUE(vs.source().source_proof == proof_a) << vs.source().source_proof.value("case_path", "");
      EXPECT_EQ(vs.preset_id(), preset);
      EXPECT_TRUE(vs.base_payload() == a_base) << "base payload replaced";
      EXPECT_TRUE(vs.payload() == a_payload) << "rendered payload replaced";
      EXPECT_EQ(vs.payload_serial(), a_serial);
      EXPECT_EQ(vs.camera_serial(), a_camera);
      EXPECT_EQ(vs.shown_step(), a_step);
      EXPECT_EQ(vs.parameters(), a_parameters) << "the unsaved draft of the previous Viewer was dropped";
      EXPECT_EQ(vs.pending_edit(), "data");
      EXPECT_FALSE(vs.auto_evaluate);
      if (vs.payload()) {
        viewer.set_payload(vs.payload());
        EXPECT_LT(differing_fraction(a_image, render(viewer, 400, 300)), 0.001);
      }
    };
    a_intact();
    ASSERT_FALSE(::testing::Test::HasFailure()) << "Viewer A precondition";

    // B keeps its original exact proof, but a registered frame changes locally before the open.
    const auto frame = std::filesystem::path(run_b) / "Polar.00000002.dat";
    const auto original = read_text(frame.string());
    const auto modified = std::filesystem::last_write_time(frame);
    auto replacement = original;
    const auto digit = replacement.find_last_of("0123456789");
    ASSERT_NE(digit, std::string::npos);
    replacement[digit] = replacement[digit] == '0' ? '1' : '0';
    const auto rewrite = [&](const std::string &bytes) {
      std::fstream stream(frame, std::ios::in | std::ios::out | std::ios::binary);
      stream.write(bytes.data(), std::streamsize(bytes.size()));
      stream.close();
      ASSERT_TRUE(stream.good());
      std::filesystem::last_write_time(frame, modified);
      ASSERT_EQ(std::filesystem::file_size(frame), original.size());
      ASSERT_EQ(std::filesystem::last_write_time(frame), modified);
    };
    ASSERT_NO_FATAL_FAILURE(rewrite(replacement));
    const auto before = client->stats();
    const int started = vs.evaluations_started();
    ASSERT_TRUE(vs.open_path(run_b, preset, Json(), proof_b)) << failure();
    // The graph worker's byte check completes; A's still-present payload is not a completion signal.
    ASSERT_TRUE(wait([&] {
      return !vs.evaluating() && failure().find("Polar.00000002.dat") != std::string::npos;
    })) << failure() << client->bridge_log().text();
    std::printf("METRIC guarded collected open failure: %s\n", failure().c_str());
    EXPECT_NE(failure().find("changed"), std::string::npos) << failure();
    ASSERT_TRUE(vs.graph_inspection());
    EXPECT_NE(vs.graph_inspection()->error.find("Polar.00000002.dat"), std::string::npos);
    a_intact();

    // The failure replays nothing: no further evaluation, retry or bridge restart while idle.
    const int after_failure = vs.evaluations_started();
    const auto calls = client->stats().calls_sent;
    EXPECT_LE(after_failure, started + 1);
    EXPECT_FALSE(wait([&] { return vs.evaluating() || vs.evaluations_started() != after_failure; }, 1.5));
    EXPECT_EQ(vs.evaluations_started(), after_failure);
    EXPECT_EQ(client->stats().calls_sent, calls);
    EXPECT_EQ(client->stats().calls_retried, before.calls_retried);
    EXPECT_EQ(client->stats().restarts, before.restarts);
    EXPECT_EQ(vs.prefetched_count(), 0);

    // Positive control: explicitly restoring the registered bytes lets the user reopen B.
    ASSERT_NO_FATAL_FAILURE(rewrite(original));
    ASSERT_TRUE(vs.open_path(run_b, preset, Json(), proof_b)) << failure();
    ASSERT_TRUE(wait([&] { return vs.source().path == run_b && vs.payload() && !vs.evaluating(); }))
        << failure() << client->bridge_log().text();
    EXPECT_EQ(failure(), "|");
    EXPECT_EQ(vs.source().source_proof, proof_b);
    EXPECT_EQ(vs.shown_step(), Json(2));
    EXPECT_NE(vs.base_payload(), a_base);
    EXPECT_GT(vs.camera_serial(), a_camera);
    viewer.set_payload(vs.payload());
    EXPECT_LT(differing_fraction(a_image, render(viewer, 400, 300)), 0.001) << "B's frame is A's synthetic frame";
    vs.close();
    store.set_bridge(nullptr);
  }
  client->close();
  loop.run_ready();
}
