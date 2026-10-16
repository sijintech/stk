/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real native-window adoption, separate from headless workspace tree tests. */
#include <cstdio>
#include <cstring>
#include <exception>
#include <string>

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/gfx/gpu.hh"
#include "stk/wm/window.hh"

using namespace stk;

namespace {
constexpr const char *draft = "# synthetic portable draft\nprint('explicit Run required')\n";
int failures = 0;
void check(bool ok, const char *what, const std::string &detail = {})
{
  std::printf("%s %s%s%s\n", ok ? "ok" : "FAIL", what, detail.empty() ? "" : ": ", detail.c_str());
  std::fflush(stdout);
  if (!ok) { failures++; }
}
bool set_hidden_draft(io::Json &node)
{
  if (node.contains("area")) {
    auto &state = node.at("area").at("state");
    auto &tabs = state.at("tabs");
    for (size_t i = 0; i < tabs.size(); i++) {
      if (io::get_string(tabs[i], "type") == app::kEditorPython) {
        tabs[i]["state"]["source"] = draft;
        tabs[i]["state"]["baseline"] = "";
        return state.at("active") != int(i);
      }
    }
    return false;
  }
  for (auto &child : node.at("children")) { if (set_hidden_draft(child)) { return true; } }
  return false;
}
bool has_hidden_draft(const wm::Screen &screen)
{
  for (auto *base : screen.areas()) {
    const auto *area = dynamic_cast<const app::EditorArea *>(base);
    if (!area) { continue; }
    for (int i = 0; i < area->tab_count(); i++) {
      if (area->tab(i).type().id == app::kEditorPython && &area->editor() != &area->tab(i)) {
        const auto state = area->tab(i).save_workspace_state();
        if (state.value("source", "") == draft && area->tab(i).has_unsaved_changes()) { return true; }
      }
    }
  }
  return false;
}
int run(gfx::Backend backend)
{
  app::AppShell shell({.language = "en", .interactive = false});
  wm::WmOptions options;
  options.gpu.backend = backend;
  options.window = {"STK workspace window test", 1100, 700, false};
  std::string error;
  auto manager = wm::WindowManager::create(options, error);
  if (!manager) {
    std::printf("%s: %s\n", error.find("no display") != std::string::npos ? "SKIP" : "FAIL", error.c_str());
    return error.find("no display") != std::string::npos ? 77 : 1;
  }
  auto *original = manager->main_window();
  shell.install(original->screen(), original);
  shell.build_default_layout(original->screen());
  int phase = 0;
  manager->add_timer(25, 25, [&] {
    if (phase == 0 && original->frames_drawn() > 0) {
      auto state = shell.capture_workspace();
      check(set_hidden_draft(state["windows"][0]["screen"]["root"]), "candidate contains a hidden Python draft");
      state["windows"].push_back(state["windows"][0]);
      state["windows"].push_back(state["windows"][0]);
      state["app"]["viewer"]["overlays"] = false;
      state["app"]["viewer"]["export_settings"]["width"] = 2048;
      check(shell.apply_workspace(state, &error), "adopt three real native windows", error);
      phase = 1;
      if (failures) { manager->quit(1); }
      return;
    }
    if (phase != 1 || manager->windows().size() != 3) { return; }
    for (const auto &window : manager->windows()) { if (window->frames_drawn() == 0) { return; } }
    check(shell.screen_count() == 3, "three screens remain installed after old-window close");
    for (const auto &window : manager->windows()) {
      check(window.get() != original, "original native window was replaced");
      check(has_hidden_draft(window->screen()), "hidden draft restored in every native window");
      check(!shell.can_close_screen(&window->screen()), "restored draft protects native close");
      gfx::Image pixels;
      check(window->read_pixels(pixels, error) && pixels.width > 0 && pixels.height > 0,
            "restored window draws and supports GPU readback", error);
    }
    check(!shell.store().viewer().overlays() && shell.store().viewer().export_settings.width == 2048,
          "shared Viewer parameters restored");
    check(shell.store().viewer().workspace_suspended() && shell.store().viewer().evaluations_started() == 0 &&
              shell.store().scripts().history().empty(), "restore leaves Viewer and Python unexecuted");
    phase = 2;
    // Deliberate fixture teardown bypasses user-close veto; no draft is written or run.
    while (!manager->windows().empty()) { manager->close_window(manager->main_window()); }
    check(shell.screen_count() == 0, "closing native windows forgets every screen");
    manager->quit(failures ? 1 : 0);
  });
  manager->add_timer(30000, 0, [&] { check(false, "workspace native-window timeout"); manager->quit(1); });
  const int result = manager->run();
  check(phase == 2, "workspace native-window sequence finished");
  return failures ? 1 : result;
}
}  // namespace

int main(int argc, char **argv)
{
  gfx::Backend backend = gfx::Backend::Vulkan;
  for (int i = 1; i < argc; i++) {
    if (!std::strcmp(argv[i], "--gpu-backend") && i + 1 < argc) {
      if (!gfx::parse_backend(argv[++i], backend)) { std::fprintf(stderr, "unknown GPU backend\n"); return 2; }
    }
    else { std::fprintf(stderr, "usage: stk-workspace-window-smoke [--gpu-backend BACKEND]\n"); return 2; }
  }
  try {
    int result;
    { gfx::Runtime runtime; result = run(backend); }
    if (result == 77) { return result; }
    check(gfx::Runtime::memory_blocks_in_use() == 0, "no guarded allocation leaks");
    if (!result && !failures) { std::puts("PASS workspace native windows"); }
    return result || failures ? 1 : 0;
  }
  catch (const std::exception &e) { std::fprintf(stderr, "FAIL %s\n", e.what()); return 1; }
}
