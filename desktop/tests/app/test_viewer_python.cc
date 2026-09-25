/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The Viewer's state and GPU viewer against the real Python bridge (local graph.evaluate
 * of muferro-domains on a fake muFerro run): a client-stage change re-runs no data node and the
 * view re-renders; a data-stage change re-runs the data nodes; a cached step switch completes in
 * under 300 ms with the camera kept; a GPU pick is probed for its original value. */

#include <algorithm>
#include <chrono>
#include <cstdio>

#include <gtest/gtest.h>

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
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
