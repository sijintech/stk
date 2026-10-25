/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Opt-in live-window / real-bridge opening benchmark. Not installed or run by CTest.
 * Protocol: ready -> stdin open -> measurement_complete -> stdin capture -> result.
 * The second handshake keeps screenshot allocations outside the driver's opening RSS samples.
 * Timing ends when an additional draw and swap-release call return after data becomes ready.
 * Window::frames_drawn counts those calls without checking presentation success or scan-out.
 */
#include "stk/app/project_state.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/script_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/client.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/window.hh"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>

using namespace stk;
namespace {
constexpr int kWidth = 1440, kHeight = 1200;
constexpr const char *kPrefix = "STK_BENCHMARK ";
using Clock = std::chrono::steady_clock;

void emit(const io::Json &value)
{
  std::cout << kPrefix << value.dump() << std::endl;
}

double elapsed(const Clock::time_point started)
{
  return std::chrono::duration<double>(Clock::now() - started).count();
}

std::string rendering_class(std::string device)
{
  std::transform(device.begin(), device.end(), device.begin(),
                 [](unsigned char c) { return char(std::tolower(c)); });
  for (const auto *software : {"llvmpipe", "lavapipe", "softpipe", "swiftshader"}) {
    if (device.find(software) != std::string::npos) { return "software"; }
  }
  // A backend name or an unrecognized device string is not hardware-acceleration evidence.
  return "unverified";
}

struct DetachBridge {
  app::AppStore &store;
  bridge::Client &client;
  ~DetachBridge()
  {
    store.project().attach(nullptr);
    store.set_bridge(nullptr);
    client.close();
  }
};

int run(const std::string &python, const std::string &wrapper, const std::string &control,
        const std::string &directory, const gfx::Backend backend)
{
  app::AppShell shell({.language = "en", .interactive = false});
  wm::WmOptions window_options;
  window_options.gpu.backend = backend;
  window_options.window = {"STK synthetic project opening benchmark", kWidth, kHeight, false};
  window_options.user_scale = 1.0f;
  std::string error;
  auto manager = wm::WindowManager::create(window_options, error);
  if (!manager) { throw std::runtime_error("Cannot create benchmark window: " + error); }
  auto *window = manager->main_window();
  auto &screen = window->screen();
  shell.install(screen, window);
  shell.build_default_layout(screen);
  if (!shell.catalogs_loaded()) { throw std::runtime_error("Benchmark catalogs are unavailable"); }

  bridge::ClientOptions options;
  options.python.configured = python;
  options.executor = manager->executor();
  options.state_dir = control + "/state";
  options.cache_dir = control + "/cache";
  options.command = {python, "-u", wrapper, control, "--stdio", "--strict", "--state-dir",
                     options.state_dir, "--cache-dir", options.cache_dir};
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = control + "/runtime";
  options.env["STK_PROFILES_FILE"] = control + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = "";
  options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  options.strict = options.validate = true;
  auto client = bridge::Client::create(options);
  DetachBridge detach{shell.store(), *client};
  app::BridgeStatus bridge_status(shell.store(), *client, manager.get());
  auto &project = shell.store().project();
  shell.store().set_bridge(client.get());
  if (!client->start()) { throw std::runtime_error("Benchmark bridge could not start"); }

  // Keep process(true) bounded even if a failed bridge stops generating events.
  manager->add_timer(5, 5, [] {});
  auto process = [&] {
    return manager->process(true) && manager->main_window() == window;
  };
  const auto startup = Clock::now();
  while ((!project.ready() || window->frames_drawn() == 0) && elapsed(startup) < 60) {
    if (!process()) { throw std::runtime_error("Benchmark window closed during startup"); }
  }
  if (!project.ready() || window->frames_drawn() == 0) {
    throw std::runtime_error("Benchmark desktop or bridge startup timed out");
  }
  if (window->width() != kWidth || window->height() != kHeight ||
      std::fabs(window->ui_scale() - 1.0f) > 1e-4f) {
    throw std::runtime_error("Display did not provide the fixed 1440x1200, 1x benchmark layout");
  }
  const std::string device = manager->gpu().device_info();
  emit({{"event", "ready"}, {"measurement_kind", "native_window"}, {"bridge_pid", client->bridge_pid()},
        {"system_backend", manager->system_backend()}, {"gpu_backend", manager->gpu().backend_name()},
        {"gpu_device", device}, {"rendering_class", rendering_class(device)}});
  std::string command;
  if (!std::getline(std::cin, command) || command != "open") {
    throw std::runtime_error("Expected the explicit open measurement command");
  }

  const auto calls_before = client->stats().calls_sent;
  const auto frames_before = window->frames_drawn();
  const auto started = Clock::now();
  double data_ready_seconds = -1, first_visible_seconds = -1;
  uint64_t frames_at_data = 0;
  bool ok = project.open(directory);
  while (ok && elapsed(started) < 120) {
    if (!process()) { throw std::runtime_error("Benchmark window closed during opening"); }
    if (!project.error().empty() || client->state() != bridge::BridgeState::Ready) { ok = false; break; }
    const auto *grid = screen.ui() ? screen.ui()->find("a4/main/records") : nullptr;
    const bool data_ready = project.loaded() && !project.busy() && project.table() &&
                            grid && grid->table && grid->table->rows > 0;
    if (!data_ready) { continue; }
    if (data_ready_seconds < 0) {
      data_ready_seconds = elapsed(started);
      frames_at_data = window->frames_drawn();
      // Require a draw and swap-release call to return after the data-ready observation.
      // frames_drawn increments unconditionally, so this does not verify presentation success.
      window->request_redraw();
    }
    else if (window->frames_drawn() > frames_at_data) {
      first_visible_seconds = elapsed(started);
      break;
    }
  }
  const auto *grid = screen.ui() ? screen.ui()->find("a4/main/records") : nullptr;
  ok = ok && first_visible_seconds >= 0 && project.loaded() && project.table() &&
       grid && grid->table && project.error().empty();
  io::Json report = {{"event", "measurement_complete"}, {"ok", ok}, {"measurement_kind", "native_window"},
      {"first_visible_seconds", first_visible_seconds}, {"data_ready_seconds", data_ready_seconds},
      {"timing_boundary", "post_data_ready_draw_and_swap_release_return"},
      {"first_visible_definition", "draw and swap-release calls returned after observing a data-ready grid; includes one explicit redraw; presentation success and scan-out are not verified"},
      {"frames_before_open", frames_before}, {"frames_at_data_ready", frames_at_data},
      {"frames_at_first_visible", window->frames_drawn()}, {"system_backend", manager->system_backend()},
      {"gpu_backend", manager->gpu().backend_name()}, {"gpu_device", device},
      {"rendering_class", rendering_class(device)}, {"window_width", window->width()},
      {"window_height", window->height()}, {"ui_scale", window->ui_scale()},
      {"dpi_factor", window->dpi_factor()}, {"native_pixel_size", window->native_pixel_size()},
      {"calls_sent", client->stats().calls_sent - calls_before},
      {"schema_violations", client->stats().schema_violations}, {"protocol_errors", client->stats().protocol_errors},
      {"restarts", client->stats().restarts}};
  if (!ok) {
    report["event"] = "result";
    report["error"] = project.error().empty() ? "Window opening timed out or lost its bridge/window" : project.error();
    emit(report);
    return 1;
  }
  size_t loaded = 0;
  int64_t total = 0;
  for (const auto &table : project.tables()) { loaded += table.records.size(); total += table.total_records(); }
  report["tables"] = project.tables().size();
  report["total_records"] = total;
  report["shared_loaded_records"] = loaded;
  report["visible_rows"] = grid->table->rows;
  const auto first_value = project.table()->cell(0, 0);
  if (!first_value) { throw std::runtime_error("Synthetic table has no first cell"); }
  report["first_value"] = *first_value;
  report["viewer_evaluations"] = shell.store().viewer().evaluations_started();
  report["script_runs"] = shell.store().scripts().history().size();
  report["project_revision"] = project.project()->revision;
  emit(report);

  // The driver stops RSS sampling before acknowledging this phase. GPU readback and PNG
  // encoding are evidence collection, outside the measured draw/swap-return timing and opening memory.
  if (!std::getline(std::cin, command) || command != "capture") {
    throw std::runtime_error("Expected the explicit post-measurement capture command");
  }
  const auto captured = Clock::now();
  gfx::Image pixels;
  const std::string screenshot = control + "/window.png";
  ok = window->read_pixels(pixels, error) && pixels.width == kWidth && pixels.height == kHeight &&
       gfx::png_write(screenshot, pixels);
  report["event"] = "result";
  report["ok"] = ok;
  report["screenshot"] = screenshot;
  report["screenshot_ok"] = ok;
  report["screenshot_seconds"] = elapsed(captured);
  report["screenshot_kind"] = "post-measurement offscreen rendering of the live window state";
  if (!ok) { report["error"] = error.empty() ? "Could not save the window evidence image" : error; }
  emit(report);
  return ok ? 0 : 1;
}
}  // namespace

int main(int argc, char **argv)
{
  if (argc != 7 || std::string(argv[5]) != "--gpu-backend") {
    std::cerr << "usage: stk-project-open-window-benchmark PYTHON WRAPPER CONTROL PROJECT --gpu-backend opengl|vulkan\n";
    return 2;
  }
  gfx::Backend backend;
  if ((std::string(argv[6]) != "opengl" && std::string(argv[6]) != "vulkan") ||
      !gfx::parse_backend(argv[6], backend)) { return 2; }
  try {
    int result;
    { gfx::Runtime runtime; result = run(argv[1], argv[2], argv[3], argv[4], backend); }
    return result;
  }
  catch (const std::exception &error) {
    emit({{"event", "result"}, {"ok", false}, {"error", error.what()}});
    return 1;
  }
}
