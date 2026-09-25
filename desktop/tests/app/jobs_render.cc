/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-jobs-render: the application screen with the Jobs area maximized and a populated fake task
 * list (tests/app/jobs_support.cc: populate_demo), the Results tab open with a PNG preview uploaded
 * as a GPU texture, rendered headless to PNG (compared with golden/jobs_editor_<lang>.png by
 * stk-png-diff; label `gpu`).
 *
 *   stk-jobs-render [--gpu-backend B] [--lang en|zh] [--size WxH] --export out.png --work DIR
 */

#include <cstdio>
#include <filesystem>
#include <string>

#include "stk/app/editor_area.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/shell.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/wm/screen.hh"

#include "jobs_support.hh"

using namespace stk;

int main(int argc, char **argv)
{
  std::string backend_name, lang = "en", out, work;
  int w = 1280, h = 1500;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    auto next = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
    if (a == "--gpu-backend") {
      backend_name = next();
    }
    else if (a == "--lang") {
      lang = next();
    }
    else if (a == "--export") {
      out = next();
    }
    else if (a == "--work") {
      work = next();
    }
    else if (a == "--size") {
      const std::string s = next();
      if (sscanf(s.c_str(), "%dx%d", &w, &h) != 2) {
        fprintf(stderr, "FAIL: bad --size\n");
        return 2;
      }
    }
  }
  if (out.empty() || work.empty()) {
    fprintf(stderr, "usage: stk-jobs-render [--gpu-backend B] [--lang en|zh] --export out.png --work DIR\n");
    return 2;
  }
  std::filesystem::create_directories(work);
  const std::string png = work + "/result.png";
  jobstest::write_demo_png(png);

  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(backend_name, backend, err)) {
    fprintf(stderr, "FAIL: %s\n", err.c_str());
    return 2;
  }
  int rc = 0;
  {
    gfx::Runtime runtime;
    GHOST_ISystem *system = gfx::create_background_system(err);
    if (!system) {
      fprintf(stderr, "FAIL: %s\n", err.c_str());
      return 1;
    }
    {
      gfx::GpuOptions opts;
      opts.backend = backend;
      std::unique_ptr<gfx::Gpu> gpu = gfx::Gpu::create(*system, opts, err);
      if (!gpu) {
        fprintf(stderr, "FAIL: %s\n", err.c_str());
        gfx::dispose_system();
        return 1;
      }
      gfx::set_ui_scale(1.0f);
      app::ShellOptions so;
      so.language = lang == "zh" ? "zh_CN" : "en";
      so.interactive = false;
      app::AppShell shell(so);
      shell.layout_path.clear();
      wm::Screen screen;
      shell.install(screen, nullptr);
      shell.build_default_layout(screen);
      app::JobsState &jobs = shell.store().jobs();
      app::use_gpu_textures(jobs);
      auto *jobs_area = dynamic_cast<app::EditorArea *>(screen.find_area("a1"));
      screen.set_maximized(jobs_area);
      jobs_area->editor().load_state(nlohmann::json{{"detail_tab", 2}});
      wm::DrawContext ctx;
      ctx.ui_scale = 1.0f;
      ctx.fonts = &gpu->fonts();
      ctx.rect = {0, 0, w, h};
      ctx.now = 100.0;
      gfx::Image img;
      bool populated = false;
      const bool ok = gfx::render_offscreen(w, h, [&] {
        if (!populated) {
          jobstest::populate_demo(jobs, png);
          populated = true;
        }
        screen.draw(ctx);
      }, img, err);
      const bool textured = jobs.preview().texture != 0;
      gfx::Image dummy;
      /* Free the preview texture with a context current, before the GPU goes away. */
      gfx::render_offscreen(8, 8, [&] { jobs.clear_preview(); }, dummy, err);
      jobs.create_texture = nullptr;
      jobs.free_texture = nullptr;
      if (!ok) {
        fprintf(stderr, "FAIL: render: %s\n", err.c_str());
        rc = 1;
      }
      else {
        for (size_t i = 3; i < img.rgba.size(); i += 4) {
          img.rgba[i] = 255;
        }
        if (!textured) {
          fprintf(stderr, "FAIL: the preview has no texture\n");
          rc = 1;
        }
        if (!gfx::png_write(out, img)) {
          fprintf(stderr, "FAIL: cannot write %s\n", out.c_str());
          rc = 1;
        }
        else {
          printf("wrote %s (%dx%d, %s, %s)\n", out.c_str(), w, h, lang.c_str(), gpu->backend_name());
        }
      }
    }
    gfx::dispose_system();
  }
  /* Engine statics may hold blocks until static destruction (Metal): the leak verdict is
   * guardedalloc's at-exit check (it aborts, and ctest matches its report). */
  printf("guardedalloc: %u block(s) in use after shutdown\n", gfx::Runtime::memory_blocks_in_use());
  return rc;
}
