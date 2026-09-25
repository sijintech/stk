/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-desktop: the STK desktop application.
 *
 * GUI mode opens the main window with the application shell (top bar, areas, status bar) and
 * restores the saved layout (`<user config>/desktop/layout.json`, or `--layout FILE`), falling
 * back to the default layout; the layout is saved again when the window closes. `--headless`
 * renders the default (or `--layout`) screen offscreen and exports it as PNG; `--sample` renders
 * the WP1 engine sample frame instead. See `stk-desktop --help`.
 */

#include <charconv>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <filesystem>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>

#include "stk/app/bridge_status.hh"
#include "stk/app/viewer_export.hh"
#include "stk/app/viewer_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/wm/csd.hh"
#include "stk/wm/layout_store.hh"
#include "stk/wm/window.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer_gpu/viewer.hh"

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
  bool scale_given = false;
  bool sample = false;
  bool no_save_layout = false;
  bool no_bridge = false;
  int width = 0, height = 0;
  float scale = 1.0f;
  std::string export_path;
  std::string gpu_backend;
  std::string datafiles;
  std::string i18n_dir;
  std::string lang;
  std::string layout;
  std::string save_layout;
  std::string python;
  bool gpu_debug = false;
  bool verbose = false;
  long exit_after_frames = 0;
  /* WP10 headless viewer export (--preset / --run / --open). */
  std::string preset;
  std::string run;
  std::string open;
  std::string camera;
  std::string state_dir;
  std::vector<std::pair<std::string, std::string>> params;
  int magnification = 1;
  bool transparent = false;
  bool no_overlays = false;
  bool sequence = false;
  bool viewer() const
  {
    return !preset.empty() || !run.empty() || !open.empty();
  }
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
          "  --sample                 Headless: render the engine sample frame instead of the\n"
          "                           application screen.\n"
          "  --size WxH               Headless: frame size in pixels (default 960x600).\n"
          "                           GUI: initial window size in points (default: saved, else\n"
          "                           1280x800).\n"
          "  --scale S                Headless: UI scale of the frame (default 1).\n"
          "                           GUI: user scale, multiplied with the display DPI factor.\n"
          "  --lang zh|en             UI language (default: saved, else zh).\n"
          "  --layout FILE            Load this layout instead of the saved one (not written back).\n"
          "  --save-layout FILE       Write the layout of the screen to FILE (headless: the\n"
          "                           rendered screen; GUI: on exit).\n"
          "  --no-save-layout         GUI: do not save the layout on exit.\n"
          "  --no-bridge              GUI: do not start the Python bridge (status bar shows it).\n"
          "  --python PATH            GUI: interpreter for the bridge (default: $STK_PYTHON, else\n"
          "                           python3 / python on PATH).\n"
          "  --gpu-backend B          auto, opengl, vulkan or metal (default: $STK_GPU_BACKEND,\n"
          "                           else OpenGL on Linux/Windows and Metal on macOS).\n"
          "  --datafiles DIR          Directory containing fonts/ (default: next to the program,\n"
          "                           $STK_BLENDER_DATAFILES, or the source tree in dev builds).\n"
          "  --i18n DIR               Directory of the message catalogs (default: next to the\n"
          "                           program, $STK_I18N_DIR, or the source tree in dev builds).\n"
          "\n"
          "Headless viewer export (WP10; renders the Viewer's image, not the screen):\n"
          "  --run DIR                Evaluate a run folder locally through the Python bridge.\n"
          "  --open PATH              Show a payload (.stkp / folder), result folder or run folder\n"
          "                           (also in the GUI: opened in the Viewer at start).\n"
          "  --preset ID              Graph preset for --run (default: guessed, muferro-domains).\n"
          "  --param NAME=JSON        Preset parameter (repeatable), e.g. --param step=1.\n"
          "  --camera PRESET          iso, +x, -x, +y, -y, +z or -z (default: the result's view).\n"
          "  --magnification N        1..8, tiled (default 1). --size is the logical image size\n"
          "                           (default: the result's viewport).\n"
          "  --transparent            Keep a transparent background.\n"
          "  --no-overlays            Hide scalar bars, legends, axes and text.\n"
          "  --sequence               Export every time step: <stem>.%%08d.png and an stk.series/1\n"
          "                           manifest <stem>.series.json next to --export.\n"
          "  --state-dir DIR          Bridge state and cache under DIR (default: the user's).\n"
          "  --python PATH            Interpreter of the bridge (default: $STK_PYTHON, python3).\n"
          "\n"
          "  --gpu-debug              Create debug GPU contexts.\n"
          "  --exit-after-frames N    GUI: quit after N frames were presented (smoke tests).\n"
          "  --verbose                Print backend and device details.\n"
          "  --version                Print the version and exit.\n"
          "  --help                   Print this help and exit.\n"
          "\n"
          "Layout: saved to $XDG_CONFIG_HOME/stk/desktop/layout.json (~/.config/stk/...) when the\n"
          "window closes; a corrupt file is moved to layout.json.corrupt and the default layout\n"
          "is used.\n"
          "\n"
          "GUI keys: Ctrl+Space maximize / restore the area under the pointer, T / N toggle the\n"
          "toolbar / sidebar, Ctrl+PageUp / PageDown switch tabs, Ctrl+S save the layout,\n"
          "Ctrl + / - / 0 UI scale, Ctrl+Q quit. Drag splitters to resize areas, double-click\n"
          "one to join the areas beside it; right-click an area header for the area menu.\n"
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
    else if (arg == "--sample") {
      a.sample = true;
    }
    else if (arg == "--gpu-debug") {
      a.gpu_debug = true;
    }
    else if (arg == "--verbose") {
      a.verbose = true;
    }
    else if (arg == "--no-save-layout") {
      a.no_save_layout = true;
    }
    else if (arg == "--no-bridge") {
      a.no_bridge = true;
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
      a.scale_given = true;
    }
    else if (arg == "--lang") {
      if (!value(v)) {
        return false;
      }
      if (v == "zh" || v == "zh_CN") {
        a.lang = "zh_CN";
      }
      else if (v == "en") {
        a.lang = "en";
      }
      else {
        err = "--lang: expected zh or en";
        return false;
      }
    }
    else if (arg == "--transparent") {
      a.transparent = true;
    }
    else if (arg == "--no-overlays") {
      a.no_overlays = true;
    }
    else if (arg == "--sequence") {
      a.sequence = true;
    }
    else if (arg == "--preset" || arg == "--run" || arg == "--open" || arg == "--camera" || arg == "--state-dir") {
      if (!value(v)) {
        return false;
      }
      std::string &dst = arg == "--preset" ? a.preset :
                         arg == "--run"    ? a.run :
                         arg == "--open"   ? a.open :
                         arg == "--camera" ? a.camera :
                                             a.state_dir;
      dst = v;
    }
    else if (arg == "--param") {
      if (!value(v)) {
        return false;
      }
      const size_t eq = v.find('=');
      if (eq == std::string_view::npos || eq == 0) {
        err = "--param: expected NAME=VALUE";
        return false;
      }
      a.params.emplace_back(std::string(v.substr(0, eq)), std::string(v.substr(eq + 1)));
    }
    else if (arg == "--magnification") {
      if (!value(v)) {
        return false;
      }
      a.magnification = int(strtol(std::string(v).c_str(), nullptr, 10));
      if (a.magnification < 1 || a.magnification > 8) {
        err = "--magnification: expected 1..8";
        return false;
      }
    }
    else if (arg == "--export" || arg == "--gpu-backend" || arg == "--datafiles" || arg == "--i18n" ||
             arg == "--layout" || arg == "--save-layout" || arg == "--python")
    {
      if (!value(v)) {
        return false;
      }
      std::string &dst = arg == "--export"      ? a.export_path :
                         arg == "--gpu-backend" ? a.gpu_backend :
                         arg == "--datafiles"   ? a.datafiles :
                         arg == "--i18n"        ? a.i18n_dir :
                         arg == "--layout"      ? a.layout :
                         arg == "--python"      ? a.python :
                                                  a.save_layout;
      dst = v;
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
  if (a.sample && !a.headless) {
    err = "--sample requires --headless";
    return false;
  }
  if ((!a.run.empty() || !a.params.empty() || !a.camera.empty()) && !a.headless) {
    err = "--run / --param / --camera require --headless (the GUI takes --open PATH [--preset ID])";
    return false;
  }
  if (!a.camera.empty() && !stk::viewer::parse_camera_preset(a.camera)) {
    err = "--camera: expected iso, +x, -x, +y, -y, +z or -z";
    return false;
  }
  return true;
}

stk::app::ShellOptions shell_options(const Args &a, const bool interactive)
{
  stk::app::ShellOptions so;
  so.i18n_dir = stk::app::locate_i18n_dir(a.i18n_dir);
  if (!a.lang.empty()) {
    so.language = a.lang;
  }
  so.interactive = interactive;
  return so;
}

/** Loads `--layout` (or the saved layout) into the screen, else the default layout. */
void restore_or_default(stk::app::AppShell &shell, stk::wm::Screen &screen, const Args &a, const std::string &path)
{
  const bool explicit_file = !a.layout.empty();
  if (!shell.restore(screen, stk::core::path_from_utf8(path), !explicit_file)) {
    if (explicit_file) {
      fprintf(stderr, "stk-desktop: cannot use layout %s, using the default layout\n", path.c_str());
    }
    shell.build_default_layout(screen);
  }
  if (!a.lang.empty()) {
    /* An explicit --lang wins over the saved language. */
    shell.set_language(a.lang);
  }
}

int run_sample_headless(const Args &a, stk::gfx::Gpu &gpu, const int w, const int h)
{
  using namespace stk;
  std::string err;
  wm::Screen screen;
  app::build_sample_screen(screen, nullptr);
  wm::DrawContext ctx;
  ctx.ui_scale = a.scale;
  ctx.fonts = &gpu.fonts();
  ctx.rect = {0, 0, w, h};
  gfx::Image img;
  if (!gfx::render_offscreen(w, h, [&] { screen.draw(ctx); }, img, err)) {
    fprintf(stderr, "stk-desktop: render failed: %s\n", err.c_str());
    return kFailure;
  }
  if (!a.export_path.empty()) {
    if (!gfx::png_write(a.export_path, img)) {
      fprintf(stderr, "stk-desktop: cannot write %s\n", a.export_path.c_str());
      return kFailure;
    }
    printf("wrote %s (%dx%d, scale %g, %s)\n", a.export_path.c_str(), w, h, a.scale, gpu.backend_name());
  }
  else {
    printf("rendered %dx%d at scale %g with %s (no --export given)\n", w, h, a.scale, gpu.backend_name());
  }
  return kOk;
}

int run_app_headless(const Args &a, stk::gfx::Gpu &gpu, const int w, const int h)
{
  using namespace stk;
  std::string err;
  app::AppShell shell(shell_options(a, false));
  if (!shell.catalogs_loaded()) {
    fprintf(stderr, "stk-desktop: %s\n", shell.catalog_error().c_str());
  }
  shell.layout_path.clear();
  wm::Screen screen;
  shell.install(screen, nullptr);
  if (!a.layout.empty()) {
    restore_or_default(shell, screen, a, a.layout);
  }
  else {
    shell.build_default_layout(screen);
  }
  wm::DrawContext ctx;
  ctx.ui_scale = a.scale;
  ctx.fonts = &gpu.fonts();
  ctx.rect = {0, 0, w, h};
  /* A fixed clock keeps exports deterministic (no tooltips, toasts or animations). */
  ctx.now = 100.0;
  gfx::Image img;
  if (!gfx::render_offscreen(w, h, [&] { screen.draw(ctx); }, img, err)) {
    fprintf(stderr, "stk-desktop: render failed: %s\n", err.c_str());
    return kFailure;
  }
  /* A window ignores the framebuffer alpha; keep exported PNGs opaque the same way. */
  for (size_t i = 3; i < img.rgba.size(); i += 4) {
    img.rgba[i] = 255;
  }
  int rc = kOk;
  if (!a.save_layout.empty() && !shell.save(screen, nullptr, core::path_from_utf8(a.save_layout))) {
    fprintf(stderr, "stk-desktop: cannot write layout %s\n", a.save_layout.c_str());
    rc = kFailure;
  }
  const size_t areas = screen.areas().size();
  if (!a.export_path.empty()) {
    if (!gfx::png_write(a.export_path, img)) {
      fprintf(stderr, "stk-desktop: cannot write %s\n", a.export_path.c_str());
      return kFailure;
    }
    printf("wrote %s (%dx%d, scale %g, %s, %s, %zu areas)\n", a.export_path.c_str(), w, h, a.scale,
           shell.store().language().c_str(), gpu.backend_name(), areas);
  }
  else {
    printf("rendered %dx%d (scale %g, %s, %s, %zu areas, no --export given)\n", w, h, a.scale,
           shell.store().language().c_str(), gpu.backend_name(), areas);
  }
  return rc;
}

/** A main loop for the bridge's callbacks in headless runs: the executor queues, pump() runs. */
class HeadlessLoop {
 public:
  stk::bridge::Executor executor()
  {
    return [this](std::function<void()> fn) {
      {
        std::lock_guard lock(mutex_);
        tasks_.push_back(std::move(fn));
      }
      cv_.notify_all();
    };
  }
  /** Runs tasks (and `each`) until `until()` or the timeout; false on timeout. */
  bool pump_until(const std::function<bool()> &until, const std::function<void()> &each, const double timeout_s)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(int64_t(timeout_s * 1000));
    while (true) {
      while (true) {
        std::function<void()> fn;
        {
          std::lock_guard lock(mutex_);
          if (tasks_.empty()) {
            break;
          }
          fn = std::move(tasks_.front());
          tasks_.pop_front();
        }
        fn();
      }
      each();
      if (until()) {
        return true;
      }
      std::unique_lock lock(mutex_);
      if (std::chrono::steady_clock::now() >= deadline) {
        return false;
      }
      cv_.wait_for(lock, std::chrono::milliseconds(10), [&] { return !tasks_.empty(); });
    }
  }

 private:
  std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> tasks_;
};

/**
 * WP10 headless viewer export: opens --open / --run (evaluated through the Python bridge with
 * --preset and --param), renders the Viewer's image with stk_viewer_gpu and writes --export.
 * This is the end-to-end path of the WP12 golden:
 *   stk-desktop --headless --preset muferro-domains --run DIR --export out.png --size 800x600
 */
int run_viewer_headless(const Args &a, stk::gfx::Gpu &gpu)
{
  using namespace stk;
  app::ShellOptions so = shell_options(a, false);
  app::AppStore store;
  std::string err;
  if (!so.i18n_dir.empty()) {
    store.catalog().load_dir(so.i18n_dir, &err);
    store.catalog().set_language(so.language);
  }
  app::ViewerState &vs = store.viewer();
  const std::string path = a.open.empty() ? a.run : a.open;
  if (path.empty()) {
    fprintf(stderr, "stk-desktop: --preset needs --run DIR (or --open PATH)\n");
    return kUsage;
  }
  const app::ViewerSource kind = app::classify_path(path, &err);
  if (kind.kind == app::SourceKind::None) {
    fprintf(stderr, "stk-desktop: %s\n", err.c_str());
    return kFailure;
  }
  io::Json params = io::Json::object();
  for (const auto &[name, text] : a.params) {
    try {
      params[name] = io::parse_json(text);
    }
    catch (const std::exception &) {
      params[name] = text; /* a bare string such as --param view=+x */
    }
  }
  HeadlessLoop loop;
  std::unique_ptr<bridge::Client> client;
  if (kind.evaluates()) {
    bridge::ClientOptions bo;
    bo.executor = loop.executor();
    bo.python.configured = a.python;
    bo.client_version = STK_DESKTOP_VERSION;
    bo.call_timeout_s = 1800.0;
    if (!a.state_dir.empty()) {
      bo.state_dir = a.state_dir + "/state";
      bo.cache_dir = a.state_dir + "/cache";
    }
#ifdef STK_DESKTOP_SOURCE_REPO
    {
      const std::string repo = STK_DESKTOP_SOURCE_REPO;
      std::error_code ec;
      if (std::filesystem::exists(core::path_from_utf8(repo + "/suan/desktop_bridge/__main__.py"), ec)) {
        const auto old = core::getenv_utf8("PYTHONPATH");
#  ifdef _WIN32
        const char sep = ';';
#  else
        const char sep = ':';
#  endif
        bo.env["PYTHONPATH"] = old && !old->empty() ? repo + sep + *old : repo;
      }
    }
#endif
    client = bridge::Client::create(std::move(bo));
    if (!client->start(&err) || !client->wait_ready(180.0)) {
      fprintf(stderr, "stk-desktop: bridge: %s\n%s\n", err.empty() ? "did not start" : err.c_str(),
              client->bridge_log().text().c_str());
      return kFailure;
    }
    store.set_bridge(client.get());
    /* The parameters apply to the preset's form, which needs the presets and the catalog. */
    vs.refresh_metadata();
  }
  int rc = kOk;
  auto each = [&vs]() { vs.pump(); };
  if (!vs.open_path(path, a.preset, params)) {
    fprintf(stderr, "stk-desktop: cannot open %s: %s\n", path.c_str(), vs.open_error().c_str());
    rc = kFailure;
  }
  else if (!loop.pump_until(
               [&vs]() {
                 return (vs.payload() != nullptr && !vs.evaluating()) || !vs.eval_error().empty() ||
                        !vs.metadata_error().empty();
               },
               each,
               1800.0))
  {
    fprintf(stderr, "stk-desktop: timed out waiting for the evaluation\n");
    rc = kFailure;
  }
  else if (!vs.payload()) {
    fprintf(stderr, "stk-desktop: evaluation failed: %s%s\n", vs.eval_error().c_str(), vs.metadata_error().c_str());
    rc = kFailure;
  }
  if (rc == kOk) {
    viewer_gpu::Viewer v(gpu.fonts());
    v.set_payload(vs.payload());
    if (!a.camera.empty()) {
      v.set_camera_preset(*viewer::parse_camera_preset(a.camera));
    }
    viewer_gpu::ExportOptions eo;
    if (a.size_given) {
      eo.width = a.width;
      eo.height = a.height;
    }
    eo.magnification = a.magnification;
    eo.transparent = a.transparent;
    eo.overlays = !a.no_overlays;
    if (!a.export_path.empty() && a.sequence) {
      /* Every step: evaluated (or read from the series) first, then rendered in order. */
      vs.export_settings.path = a.export_path;
      vs.export_settings.sequence = true;
      vs.export_settings.width = eo.width;
      vs.export_settings.height = eo.height;
      vs.export_settings.magnification = eo.magnification;
      vs.export_settings.transparent = eo.transparent;
      vs.export_settings.overlays = eo.overlays;
      vs.request_export();
      if (!vs.export_job() || !loop.pump_until([&vs]() { return vs.export_job() && vs.export_job()->ready; }, each, 1800.0))
      {
        fprintf(stderr, "stk-desktop: sequence export: %s\n", vs.export_status().c_str());
        rc = kFailure;
      }
      else {
        std::string message;
        if (!app::render_export_job(v, *vs.export_job(), store, vs.payload(), message)) {
          rc = kFailure;
        }
        printf("%s\n", message.c_str());
        vs.finish_export(rc == kOk, message);
      }
    }
    else if (!a.export_path.empty()) {
      if (!v.export_png(core::path_from_utf8(a.export_path), eo, err)) {
        fprintf(stderr, "stk-desktop: export failed: %s\n", err.c_str());
        rc = kFailure;
      }
    }
    if (rc == kOk) {
      std::string evaluated;
      if (vs.last_eval()) {
        for (const std::string &n : vs.last_eval()->evaluated) {
          evaluated += (evaluated.empty() ? "" : ",") + n;
        }
      }
      printf("%s %s (%s, preset %s, step %s, %zu layers, %s, evaluated [%s])\n",
             a.export_path.empty() ? "rendered" : "wrote",
             a.export_path.empty() ? path.c_str() :
             a.sequence            ? app::sequence_manifest_path(a.export_path).c_str() :
                                     a.export_path.c_str(),
             app::source_kind_name(vs.source().kind), vs.preset_id().empty() ? "-" : vs.preset_id().c_str(),
             vs.shown_step().is_null() ? "-" : vs.shown_step().dump().c_str(), vs.layers().size(), gpu.backend_name(),
             evaluated.c_str());
      for (const std::string &w : vs.warnings()) {
        printf("warning: %s\n", w.c_str());
      }
    }
  }
  vs.close();
  store.set_bridge(nullptr);
  if (client) {
    client->close();
    loop.pump_until([]() { return true; }, []() {}, 1.0);
    client.reset();
  }
  return rc;
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
    rc = a.sample     ? run_sample_headless(a, *gpu, w, h) :
         a.viewer()   ? run_viewer_headless(a, *gpu) :
                        run_app_headless(a, *gpu, w, h);
  }
  gfx::dispose_system();
  return rc;
}

int run_gui(const Args &a, const stk::gfx::Backend backend)
{
  using namespace stk;
  app::AppShell shell(shell_options(a, true));
  if (!shell.catalogs_loaded()) {
    fprintf(stderr, "stk-desktop: %s\n", shell.catalog_error().c_str());
  }
  const std::string layout_path = a.layout.empty() ? core::path_to_utf8(wm::default_layout_path()) : a.layout;
  /* The saved window geometry and UI scale are needed before the window exists. */
  wm::LayoutFile saved;
  const bool have_saved = wm::load_layout_file(core::path_from_utf8(layout_path), saved) == wm::LayoutLoad::Ok;

  wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.gpu.datafiles = a.datafiles;
  opts.gpu.debug = a.gpu_debug;
  opts.user_scale = a.scale_given ? a.scale : (have_saved ? saved.ui_scale : 1.0f);
  opts.window.title = "STK";
  opts.window.width = app::kDefaultWindowWidth;
  opts.window.height = app::kDefaultWindowHeight;
  if (have_saved && saved.window.width > 0 && saved.window.height > 0) {
    opts.window.width = saved.window.width;
    opts.window.height = saved.window.height;
    if (saved.window.has_position) {
      opts.window.x = saved.window.x;
      opts.window.y = saved.window.y;
    }
    opts.window.maximized = saved.window.maximized;
  }
  if (a.size_given) {
    opts.window.width = a.width;
    opts.window.height = a.height;
    opts.window.maximized = false;
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
  wm::Screen &screen = win->screen();
  shell.install(screen, win);
  shell.set_ui_scale(opts.user_scale);
  restore_or_default(shell, screen, a, layout_path);
  if (a.scale_given) {
    shell.set_ui_scale(a.scale);
  }
  /* Saving: the per-user layout unless --layout (read-only) or --no-save-layout; --save-layout
   * adds an explicit target. */
  std::string save_path;
  if (!a.save_layout.empty()) {
    save_path = a.save_layout;
  }
  else if (a.layout.empty() && !a.no_save_layout) {
    save_path = layout_path;
  }
  shell.layout_path = core::path_from_utf8(save_path);
  bool saved_once = false;
  auto save_layout = [&]() {
    if (!saved_once && !save_path.empty() && wm->main_window()) {
      saved_once = shell.save(wm->main_window()->screen(), wm->main_window(), shell.layout_path);
    }
  };
  shell.on_quit = [&]() {
    save_layout();
    wm->quit(kOk);
  };
  win->on_event = [&](const wm::Event &e) {
    if (e.type == wm::EventType::Close) {
      save_layout();
      /* The window (and its screen) goes away now: later store changes (bridge callbacks, the
       * viewer state) must not tag its screen for redraw. */
      shell.store().on_change = nullptr;
      shell.store().toast = nullptr;
    }
    return false;
  };

  printf("stk-desktop: %s, %s, window %dx%d px, UI scale %.3g, CSD %s\n", wm->system_backend(),
         wm->gpu().backend_name(), win->width(), win->height(), win->ui_scale(), wm->csd_active() ? "on" : "off");
  if (a.verbose) {
    printf("device: %s\nfonts: %s\ni18n: %s\nlayout: %s\n", wm->gpu().device_info().c_str(),
           wm->gpu().fonts().fonts_dir.c_str(), shell.options().i18n_dir.c_str(), layout_path.c_str());
  }
  fflush(stdout);
  shell.store().log(shell.store().catalog().format(
      "app.log.started", {{"backend", wm->system_backend()}, {"gpu", wm->gpu().backend_name()}}));

  /* The Python bridge: its callbacks run on the main loop (the window manager's executor); the
   * status bar and the Bridge log editor follow it through BridgeStatus. */
  std::unique_ptr<bridge::Client> bridge_client;
  std::unique_ptr<app::BridgeStatus> bridge_status;
  if (!a.no_bridge) {
    bridge::ClientOptions bo;
    bo.executor = wm->executor();
    bo.python.configured = a.python;
    bo.client_version = STK_DESKTOP_VERSION;
#ifdef STK_DESKTOP_SOURCE_REPO
    /* Development builds: make the repository's suan package importable. */
    {
      const std::string repo = STK_DESKTOP_SOURCE_REPO;
      std::error_code ec;
      if (std::filesystem::exists(core::path_from_utf8(repo + "/suan/desktop_bridge/__main__.py"), ec)) {
        const auto old = core::getenv_utf8("PYTHONPATH");
#  ifdef _WIN32
        const char sep = ';';
#  else
        const char sep = ':';
#  endif
        bo.env["PYTHONPATH"] = old && !old->empty() ? repo + sep + *old : repo;
      }
    }
#endif
    bridge_client = bridge::Client::create(std::move(bo));
    shell.store().set_bridge(bridge_client.get());
    bridge_status = std::make_unique<app::BridgeStatus>(shell.store(), *bridge_client, wm.get());
    std::string berr;
    if (!bridge_client->start(&berr)) {
      shell.store().set_bridge_error(berr);
      fprintf(stderr, "stk-desktop: bridge: %s\n", berr.c_str());
    }
  }

  if (!a.open.empty()) {
    /* WP10: open a payload / result / run folder in the Viewer at start. */
    if (!shell.store().viewer().open_path(a.open, a.preset)) {
      fprintf(stderr, "stk-desktop: cannot open %s: %s\n", a.open.c_str(), shell.store().viewer().open_error().c_str());
    }
  }

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
  save_layout();
  if (a.verbose) {
    printf("bridge: %s%s%s\n",
           bridge_client ? std::string(bridge::bridge_state_name(bridge_client->state())).c_str() : "off",
           shell.store().bridge_error().empty() ? "" : ", ", shell.store().bridge_error().c_str());
  }
  /* Reverse order: status mirror, bridge (EOF, grace period, terminate), then the windows. */
  bridge_status.reset();
  shell.store().set_bridge(nullptr);
  bridge_client.reset();
  if (a.verbose) {
    printf("csd: %s, %llu layout callback(s)\n", wm->csd_active() ? "on" : "off",
           (unsigned long long)wm::csd_layout_calls());
  }
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
  /* Everything engine-side is shut down now. Function-local statics of the engine may still hold
   * blocks until static destruction (e.g. the Metal shader generator's `glsl_builtin_types` set),
   * so the leak check itself is guardedalloc's at-exit one, which aborts when a block remains. */
  if (args.verbose) {
    printf("guardedalloc: %u block(s) in use after shutdown (leaks are checked at exit)\n",
           stk::gfx::Runtime::memory_blocks_in_use());
  }
  return rc;
}
