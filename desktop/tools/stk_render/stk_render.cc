/* SPDX-License-Identifier: GPL-2.0-or-later */
/**
 * stk-render: headless stk.payload/2 renderer on the stk_viewer_gpu viewer (no window, no network).
 *
 *   stk-render --payload <dir|manifest.json|.stkp> --export out.png
 *              [--size WxH] [--scale N] [--camera iso|+x|-x|+y|-y|+z|-z] [--tile PX]
 *              [--gpu-backend auto|opengl|vulkan] [--lighting three_point|headlight|none]
 *              [--hide LAYER]... [--no-overlays] [--transparent]
 *              [--pick X,Y]... [--bench FRAMES] [--datafiles DIR]
 *
 * --scale N is the export magnification (1..8): the image is (W x N) by (H x N) pixels with every
 * pixel size scaled (fonts, line widths, overlays), rendered in tiles of at most --tile pixels.
 * --pick prints one JSON line per pick (pixel coordinates of the WxH view, y down).
 * --bench renders FRAMES frames of WxH and prints the timing as JSON.
 */

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "GPU_capabilities.hh"
#include "GPU_context.hh"
#include "GPU_state.hh"

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/io/json.hh"
#include "stk/viewer_gpu/viewer.hh"

namespace {

struct Args {
  std::string payload, out, camera, backend, lighting, datafiles;
  int width = 0, height = 0, scale = 1, tile = 0, bench = 0;
  std::vector<std::string> hide;
  std::vector<std::pair<double, double>> picks;
  bool overlays = true, transparent = false;
};

int usage(const char *argv0)
{
  std::fprintf(stderr,
               "usage: %s --payload PATH [--export OUT.png] [--size WxH] [--scale N] [--camera PRESET]\n"
               "          [--tile PX] [--gpu-backend B] [--lighting P] [--hide LAYER]... [--no-overlays]\n"
               "          [--transparent] [--pick X,Y]... [--bench FRAMES] [--datafiles DIR]\n",
               argv0);
  return 2;
}

bool parse(int argc, char **argv, Args &a)
{
  for (int i = 1; i < argc; i++) {
    const std::string s = argv[i];
    auto next = [&]() -> const char * { return i + 1 < argc ? argv[++i] : nullptr; };
    if (s == "--headless") {
      continue;
    }
    if (s == "--no-overlays") {
      a.overlays = false;
      continue;
    }
    if (s == "--transparent") {
      a.transparent = true;
      continue;
    }
    const char *v = next();
    if (!v) {
      return false;
    }
    if (s == "--payload") {
      a.payload = v;
    }
    else if (s == "--export") {
      a.out = v;
    }
    else if (s == "--size") {
      if (std::sscanf(v, "%dx%d", &a.width, &a.height) != 2 || a.width <= 0 || a.height <= 0) {
        return false;
      }
    }
    else if (s == "--scale") {
      a.scale = std::atoi(v);
    }
    else if (s == "--camera") {
      a.camera = v;
    }
    else if (s == "--tile") {
      a.tile = std::atoi(v);
    }
    else if (s == "--gpu-backend") {
      a.backend = v;
    }
    else if (s == "--lighting") {
      a.lighting = v;
    }
    else if (s == "--hide") {
      a.hide.push_back(v);
    }
    else if (s == "--pick") {
      double x, y;
      if (std::sscanf(v, "%lf,%lf", &x, &y) != 2) {
        return false;
      }
      a.picks.emplace_back(x, y);
    }
    else if (s == "--bench") {
      a.bench = std::atoi(v);
    }
    else if (s == "--datafiles") {
      a.datafiles = v;
    }
    else {
      return false;
    }
  }
  return !a.payload.empty() && a.scale >= 1 && a.scale <= 8;
}

int run(const Args &a)
{
  using namespace stk;
  std::string err;
  gfx::Backend backend;
  if (!gfx::resolve_backend(a.backend, backend, err)) {
    std::fprintf(stderr, "stk-render: %s\n", err.c_str());
    return 2;
  }
  std::shared_ptr<const io::Payload> payload;
  try {
    payload = viewer_gpu::load_payload(a.payload);
  }
  catch (const std::exception &e) {
    std::fprintf(stderr, "stk-render: %s\n", e.what());
    return 1;
  }
  GHOST_ISystem *system = gfx::create_background_system(err);
  if (!system) {
    std::fprintf(stderr, "stk-render: %s\n", err.c_str());
    return 1;
  }
  int rc = 0;
  {
    gfx::GpuOptions opts;
    opts.backend = backend;
    opts.datafiles = a.datafiles;
    std::unique_ptr<gfx::Gpu> gpu = gfx::Gpu::create(*system, opts, err);
    if (!gpu) {
      std::fprintf(stderr, "stk-render: %s\n", err.c_str());
      gfx::dispose_system();
      return 1;
    }
    {
      viewer_gpu::Viewer viewer(gpu->fonts());
      viewer.set_payload(payload);
      for (const std::string &w : viewer.warnings()) {
        std::fprintf(stderr, "stk-render: warning: %s\n", w.c_str());
      }
      if (!a.camera.empty()) {
        const auto preset = viewer::parse_camera_preset(a.camera);
        if (!preset) {
          std::fprintf(stderr, "stk-render: unknown camera preset %s\n", a.camera.c_str());
          rc = 2;
        }
        else {
          viewer.set_camera_preset(*preset);
        }
      }
      for (const std::string &id : a.hide) {
        viewer.set_layer_visible(id, false);
      }
      viewer.set_overlays_visible(a.overlays);
      viewer.set_lighting(a.lighting);
      viewer_gpu::ExportOptions eo;
      eo.width = a.width;
      eo.height = a.height;
      eo.magnification = a.scale;
      eo.tile_size = a.tile;
      eo.transparent = a.transparent;
      if (rc == 0 && !a.out.empty()) {
        const auto t0 = std::chrono::steady_clock::now();
        if (!viewer.export_png(a.out, eo, err)) {
          std::fprintf(stderr, "stk-render: %s\n", err.c_str());
          rc = 1;
        }
        else {
          const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
          io::Json j = {{"ok", true}, {"out", a.out}, {"backend", gpu->backend_name()}, {"ms", ms}};
          std::printf("%s\n", j.dump().c_str());
        }
      }
      const int vw = a.width > 0 ? a.width : 800, vh = a.height > 0 ? a.height : 600;
      for (const auto &[x, y] : a.picks) {
        const viewer_gpu::PickResult r = viewer.pick(x, y, vw, vh);
        io::Json j = {{"pick", {x, y}}, {"hit", r.hit}};
        if (r.hit) {
          j["layer"] = r.layer_id;
          j["type"] = r.layer_type;
          j["element"] = r.element;
          j["physical"] = {r.physical[0], r.physical[1], r.physical[2]};
          j["distance"] = r.distance;
          if (r.probe) {
            j["probe"] = {{"node", r.probe->node}, {"dataset", r.probe->dataset}};
          }
        }
        std::printf("%s\n", j.dump(-1, ' ', false, io::Json::error_handler_t::replace).c_str());
      }
      if (a.bench > 0) {
        std::vector<double> times;
        blender::GPUContext *ctx = blender::GPU_context_active_get();
        for (int f = 0; f < a.bench + 1; f++) {
          const auto t0 = std::chrono::steady_clock::now();
          blender::GPU_render_begin();
          blender::GPU_context_begin_frame(ctx);
          viewer.render(vw, vh, 1.0f);
          blender::GPU_finish();
          blender::GPU_context_end_frame(ctx);
          blender::GPU_render_end();
          times.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
        }
        const double first = times.front();
        double sum = 0, best = 1e300;
        for (size_t i = 1; i < times.size(); i++) {
          sum += times[i];
          best = std::min(best, times[i]);
        }
        const viewer_gpu::GpuStats st = viewer.stats();
        io::Json j = {{"bench", a.bench},
                      {"backend", gpu->backend_name()},
                      {"size", {vw, vh}},
                      {"first_ms", first},
                      {"mean_ms", sum / a.bench},
                      {"best_ms", best},
                      {"triangles", st.drawn_triangles},
                      {"resident_bytes", st.resident_bytes},
                      {"max_storage_buffer_bytes", uint64_t(blender::GPU_max_storage_buffer_size())}};
        std::printf("%s\n", j.dump().c_str());
      }
    }
    gpu.reset();
  }
  gfx::dispose_system();
  return rc;
}

}  // namespace

int main(int argc, char **argv)
{
  Args a;
  if (!parse(argc, argv, a)) {
    return usage(argv[0]);
  }
  stk::gfx::Runtime runtime;
  return run(a);
}
