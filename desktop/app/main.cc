/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-desktop: the STK desktop application (WP1: engine bootstrap).
 *
 * GUI mode opens a window titled "STK" showing the sample frame; `--headless` renders the same
 * frame offscreen and exports it as PNG. See `stk-desktop --help`.
 */

#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/wm/window.hh"

#include "sample_screen.hh"

#ifndef STK_DESKTOP_VERSION
#  define STK_DESKTOP_VERSION "0.0.0"
#endif
#ifndef STK_BLENDER_VERSION
#  define STK_BLENDER_VERSION "?"
#endif
#ifndef STK_DESKTOP_GIT
#  define STK_DESKTOP_GIT ""
#endif

namespace {

/** Exit codes (documented in --help). */
enum ExitCode { kOk = 0, kFailure = 1, kUsage = 2, kNoDisplay = 3 };

struct Args {
  bool headless = false;
  bool help = false;
  bool version = false;
  bool size_given = false;
  int width = 0, height = 0;
  float scale = 1.0f;
  std::string export_path;
  std::string gpu_backend;
  std::string datafiles;
  bool gpu_debug = false;
  bool verbose = false;
  long exit_after_frames = 0;
};

void print_help(FILE *f)
{
  fprintf(f,
          "Usage: stk-desktop [options]\n"
          "\n"
          "STK desktop application (GPL-2.0-or-later). Opens the main window, or renders\n"
          "offscreen with --headless.\n"
          "\n"
          "Options:\n"
          "  --headless               Render one frame offscreen (no display needed), then exit.\n"
          "  --export FILE.png        Headless: write the rendered frame to FILE.png.\n"
          "  --size WxH               Headless: frame size in pixels (default 960x600).\n"
          "                           GUI: initial window size in points (default 1280x800).\n"
          "  --scale S                Headless: UI scale of the frame (default 1).\n"
          "                           GUI: user scale, multiplied with the display DPI factor.\n"
          "  --gpu-backend B          auto, opengl, vulkan or metal (default: $STK_GPU_BACKEND,\n"
          "                           else OpenGL on Linux/Windows and Metal on macOS).\n"
          "  --datafiles DIR          Directory containing fonts/ (default: next to the program,\n"
          "                           $STK_BLENDER_DATAFILES, or the source tree in dev builds).\n"
          "  --gpu-debug              Create debug GPU contexts.\n"
          "  --exit-after-frames N    GUI: quit after N frames were presented (smoke tests).\n"
          "  --verbose                Print backend and device details.\n"
          "  --version                Print the version and exit.\n"
          "  --help                   Print this help and exit.\n"
          "\n"
          "GUI keys: type to echo text (IME supported), Ctrl+V / Ctrl+C clipboard,\n"
          "Ctrl + / - / 0 change the UI scale, drop files onto the window.\n"
          "\n"
          "Exit codes: 0 success, 1 failure, 2 usage error, 3 no display available.\n");
}

bool parse_size(std::string_view s, int &w, int &h)
{
  const size_t x = s.find_first_of("xX");
  if (x == std::string_view::npos) {
    return false;
  }
  const auto a = std::from_chars(s.data(), s.data() + x, w);
  const auto b = std::from_chars(s.data() + x + 1, s.data() + s.size(), h);
  return a.ec == std::errc() && a.ptr == s.data() + x && b.ec == std::errc() &&
         b.ptr == s.data() + s.size() && w > 0 && h > 0 && w <= 16384 && h <= 16384;
}

bool parse_args(int argc, char **argv, Args &a, std::string &err)
{
  for (int i = 1; i < argc; i++) {
    const std::string_view arg = argv[i];
    auto value = [&](std::string_view &r) {
      if (i + 1 >= argc) {
        err = std::string(arg) + " needs a value";
        return false;
      }
      r = argv[++i];
      return true;
    };
    std::string_view v;
    if (arg == "--help" || arg == "-h") {
      a.help = true;
    }
    else if (arg == "--version") {
      a.version = true;
    }
    else if (arg == "--headless") {
      a.headless = true;
    }
    else if (arg == "--gpu-debug") {
      a.gpu_debug = true;
    }
    else if (arg == "--verbose") {
      a.verbose = true;
    }
    else if (arg == "--size") {
      if (!value(v)) {
        return false;
      }
      if (!parse_size(v, a.width, a.height)) {
        err = "--size: expected WxH, e.g. 960x600";
        return false;
      }
      a.size_given = true;
    }
    else if (arg == "--scale") {
      if (!value(v)) {
        return false;
      }
      char *end = nullptr;
      const std::string s(v);
      a.scale = strtof(s.c_str(), &end);
      if (!end || *end || !(a.scale >= 0.25f && a.scale <= 8.0f)) {
        err = "--scale: expected a number between 0.25 and 8";
        return false;
      }
    }
    else if (arg == "--export") {
      if (!value(v)) {
        return false;
      }
      a.export_path = v;
    }
    else if (arg == "--gpu-backend") {
      if (!value(v)) {
        return false;
      }
      a.gpu_backend = v;
    }
    else if (arg == "--datafiles") {
      if (!value(v)) {
        return false;
      }
      a.datafiles = v;
    }
    else if (arg == "--exit-after-frames") {
      if (!value(v)) {
        return false;
      }
      a.exit_after_frames = strtol(std::string(v).c_str(), nullptr, 10);
      if (a.exit_after_frames <= 0) {
        err = "--exit-after-frames: expected a positive number";
        return false;
      }
    }
    else {
      err = "unknown option '" + std::string(arg) + "'";
      return false;
    }
  }
  if (!a.export_path.empty() && !a.headless) {
    err = "--export requires --headless";
    return false;
  }
  return true;
}

int run_headless(const Args &a, const stk::gfx::Backend backend)
{
  using namespace stk;
  const int w = a.size_given ? a.width : 960;
  const int h = a.size_given ? a.height : 600;

  std::string err;
  GHOST_ISystem *system = gfx::create_background_system(err);
  if (!system) {
    fprintf(stderr, "stk-desktop: %s\n", err.c_str());
    return kFailure;
  }
  int rc = kOk;
  {
    gfx::GpuOptions opts;
    opts.backend = backend;
    opts.datafiles = a.datafiles;
    opts.debug = a.gpu_debug;
    std::unique_ptr<gfx::Gpu> gpu = gfx::Gpu::create(*system, opts, err);
    if (!gpu) {
      fprintf(stderr, "stk-desktop: %s\n", err.c_str());
      gfx::dispose_system();
      return kFailure;
    }
    if (a.verbose) {
      printf("backend: %s | %s\nfonts: %s\n", gpu->backend_name(), gpu->device_info().c_str(),
             gpu->fonts().fonts_dir.c_str());
    }

    gfx::set_ui_scale(a.scale);
    wm::Screen screen;
    app::build_sample_screen(screen, nullptr);
    wm::DrawContext ctx;
    ctx.ui_scale = a.scale;
    ctx.fonts = &gpu->fonts();
    ctx.rect = {0, 0, w, h};
    screen.layout(ctx.rect, ctx);

    gfx::Image img;
    if (!gfx::render_offscreen(w, h, [&] { screen.draw(ctx); }, img, err)) {
      fprintf(stderr, "stk-desktop: render failed: %s\n", err.c_str());
      rc = kFailure;
    }
    else if (!a.export_path.empty()) {
      if (!gfx::png_write(a.export_path, img)) {
        fprintf(stderr, "stk-desktop: cannot write %s\n", a.export_path.c_str());
        rc = kFailure;
      }
      else {
        printf("wrote %s (%dx%d, scale %g, %s)\n", a.export_path.c_str(), w, h, a.scale,
               gpu->backend_name());
      }
    }
    else {
      printf("rendered %dx%d at scale %g with %s (no --export given)\n", w, h, a.scale,
             gpu->backend_name());
    }
  }
  gfx::dispose_system();
  return rc;
}

int run_gui(const Args &a, const stk::gfx::Backend backend)
{
  using namespace stk;
  wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.gpu.datafiles = a.datafiles;
  opts.gpu.debug = a.gpu_debug;
  opts.user_scale = a.scale;
  opts.window.title = "STK";
  if (a.size_given) {
    opts.window.width = a.width;
    opts.window.height = a.height;
  }

  std::string err;
  std::unique_ptr<wm::WindowManager> wm = wm::WindowManager::create(opts, err);
  if (!wm) {
    fprintf(stderr, "stk-desktop: %s\n", err.c_str());
    const bool no_display = err.find("no display") != std::string::npos;
    if (no_display) {
      fprintf(stderr, "stk-desktop: use --headless to render without a display\n");
    }
    return no_display ? kNoDisplay : kFailure;
  }

  wm::Window *win = wm->main_window();
  app::build_sample_screen(win->screen(), wm.get());
  printf("stk-desktop: %s, %s, window %dx%d px, UI scale %.3g\n", wm->system_backend(),
         wm->gpu().backend_name(), win->width(), win->height(), win->ui_scale());
  if (a.verbose) {
    printf("device: %s\nfonts: %s\n", wm->gpu().device_info().c_str(),
           wm->gpu().fonts().fonts_dir.c_str());
  }
  fflush(stdout);

  win->on_event = [win](const wm::Event &e) {
    /* The whole window is one text field in the sample: enable IME while focused. */
    if (e.type == wm::EventType::FocusIn) {
      win->ime_begin({0, 0, 1, 1}, true);
      win->request_redraw();
    }
    else if (e.type == wm::EventType::FocusOut) {
      win->ime_end();
    }
    return false;
  };

  if (a.exit_after_frames > 0) {
    const long target = a.exit_after_frames;
    wm->add_timer(20, 20, [&wm, target] {
      const auto &wins = wm->windows();
      if (wins.empty() || long(wins.front()->frames_drawn()) >= target) {
        printf("stk-desktop: %ld frame(s) presented, exiting\n",
               wins.empty() ? 0L : long(wins.front()->frames_drawn()));
        wm->quit(kOk);
      }
      else {
        /* Keep presenting frames until the target is reached. */
        wins.front()->request_redraw();
      }
    });
    wm->add_timer(30000, 0, [&wm] {
      fprintf(stderr, "stk-desktop: timed out waiting for frames\n");
      wm->quit(kFailure);
    });
  }
  const int rc = wm->run();
  wm.reset();
  return rc;
}

}  // namespace

int main(int argc, char **argv)
{
  Args args;
  std::string err;
  if (!parse_args(argc, argv, args, err)) {
    fprintf(stderr, "stk-desktop: %s\n\n", err.c_str());
    print_help(stderr);
    return kUsage;
  }
  if (args.help) {
    print_help(stdout);
    return kOk;
  }
  if (args.version) {
    printf("stk-desktop %s%s%s\n", STK_DESKTOP_VERSION, STK_DESKTOP_GIT[0] ? "+" : "", STK_DESKTOP_GIT);
    printf("engine: Blender %s GHOST + GPU + BLF (GPL-2.0-or-later)\n", STK_BLENDER_VERSION);
    printf("GPU backends:");
    for (const auto b : {stk::gfx::Backend::OpenGL, stk::gfx::Backend::Vulkan, stk::gfx::Backend::Metal}) {
      if (stk::gfx::backend_compiled(b)) {
        printf(" %s", stk::gfx::backend_id(b));
      }
    }
    printf(" (default %s)\n", stk::gfx::backend_id(stk::gfx::platform_default_backend()));
    return kOk;
  }

  stk::gfx::Backend backend;
  if (!stk::gfx::resolve_backend(args.gpu_backend, backend, err)) {
    fprintf(stderr, "stk-desktop: %s\n", err.c_str());
    return kUsage;
  }

  int rc;
  {
    stk::gfx::Runtime runtime;
    rc = args.headless ? run_headless(args, backend) : run_gui(args, backend);
  }
  /* Everything engine-side is shut down now; guardedalloc also aborts at exit on leaks. */
  const unsigned int blocks = stk::gfx::Runtime::memory_blocks_in_use();
  if (blocks != 0) {
    fprintf(stderr, "stk-desktop: %u guardedalloc block(s) leaked (report follows at exit)\n", blocks);
    if (rc == kOk) {
      rc = kFailure;
    }
  }
  else if (args.verbose) {
    printf("guardedalloc: 0 blocks in use at exit\n");
  }
  return rc;
}
