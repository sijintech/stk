/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real local graph evaluation -> verified Viewer receipt -> read-only native graph -> PNG. */
#include "stk/app/editor_area.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <cstdio>
#include <filesystem>
#include <fstream>

using namespace stk;

int main(int argc, char **argv)
{
  std::string backend_name, language = "en", output, mode = "wide";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { language = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--mode") { mode = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty() || (mode != "wide" && mode != "narrow")) { return 2; }
  const bool narrow = mode == "narrow";
  const int width = narrow ? 760 : 1440, height = 1000;
  bridge::test::TempDir directory{"graph-render"};
  bridge::test::ManualLoop loop;
  bridge::ClientOptions options;
  options.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  options.state_dir = directory.str() + "/bridge";
  options.cache_dir = directory.str() + "/cache";
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
  options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = "";
  options.env["STK_TOKEN_PLAN_MODEL"] = "fixture-model";
  options.executor = loop.executor();
  options.strict = options.validate = true;
  auto client = bridge::Client::create(options);
  std::string error;
  if (!client->start(&error) || !client->wait_ready(60)) {
    fprintf(stderr, "FAIL: bridge: %s\n%s", error.c_str(), client->bridge_log().text().c_str()); return 1;
  }
  loop.run_ready();
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { return 1; }
  int rc = 0;
  {
    gfx::GpuOptions gpu_options; gpu_options.backend = backend;
    auto gpu = gfx::Gpu::create(*system, gpu_options, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(1);
    app::ShellOptions shell_options;
    shell_options.language = language == "zh" ? "zh_CN" : "en";
    shell_options.interactive = false;
    app::AppShell shell(shell_options);
    wm::Screen screen;
    shell.install(screen, nullptr); shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &viewer = shell.store().viewer();
    viewer.prefetch_neighbours = false;
    bool ok = loop.pump_until([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60);
    const auto source = directory.path() / "field.dat";
    {
      std::ofstream file(source);
      file << "8 8 8 3\n";
      for (int x = 1; x <= 8; ++x) {
        for (int y = 1; y <= 8; ++y) {
          for (int z = 1; z <= 8; ++z) {
            for (int component = 1; component <= 3; ++component) {
              file << x << ' ' << y << ' ' << z << ' ' << component << ' ' << x + 2 * y + 3 * z + component << '\n';
            }
          }
        }
      }
      ok = ok && bool(file);
    }
    ok = ok && viewer.open_path(core::path_to_utf8(source), "volume") &&
        loop.pump_until([&] { viewer.pump(); return !viewer.evaluating() && bool(viewer.payload()); }, 60);
    const auto result = viewer.graph_inspection();
    ok = ok && result->shown_graph_verified.value_or(false) && result->shown_matches_desired.value_or(false);
    const int evaluations = viewer.evaluations_started();
    viewer.set_auto_evaluate(false);
    viewer.set_parameter("colormap", ui::FormValue::string("turbo"));
    ok = ok && viewer.graph_inspection()->shown_matches_desired == false;
    auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
    ok = ok && area && area->set_tab_type(0, app::kEditorAnalysisGraph);
    if (ok) {
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 260 : 350);
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { return gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error); };
      ok = ok && frame();
      if (narrow) {
        const auto *mode_widget = screen.ui()->find("graph_mode");
        if (mode_widget) { mode_widget->index.assign(1); } else { ok = false; }
        ok = ok && frame();
      }
      const auto *node = screen.ui()->find("graph_node_select");
      if (node) { node->index.assign(2); } else { ok = false; }
      ok = ok && frame();
      const auto *parameters = screen.ui()->find("graph_node_parameters");
      ok = ok && parameters && parameters->table && parameters->table->rows > 1;
      // The colormap row exposes an actual graph-parameter reference in the common table.
      if (parameters && parameters->table) {
        bool found = false;
        for (int row = 0; row < parameters->table->rows; ++row) {
          if (parameters->table->cell(row, 0) == "colormap") { parameters->table->selected.assign(row); found = true; break; }
        }
        ok = ok && found;
      }
      ok = ok && frame();
      const auto *validate = screen.ui()->find("graph_validate");
      if (validate && validate->enabled) { validate->on_click(); } else { ok = false; }
      ok = ok && loop.pump_until([&] {
        if (!frame()) { return true; }
        const auto *button = screen.ui()->find("graph_validate");
        return button && button->enabled;
      }, 30);
      bool valid = false;
      for (const auto &block : screen.ui()->blocks()) {
        for (const auto &widget : block->widgets()) {
          valid |= widget.text == shell.store().tr("analysis_graph.valid");
        }
      }
      ok = ok && valid && viewer.evaluations_started() == evaluations && client->stats().schema_violations == 0;
      if (!narrow) {
        const auto *fit = screen.ui()->find("graph_fit");
        if (fit && fit->enabled) { fit->on_click(); } else { ok = false; }
      }
      ok = ok && frame() && gfx::png_write(output, image);
    }
    if (!ok) { fprintf(stderr, "FAIL: %s\n%s\n%s", error.c_str(), viewer.eval_error().c_str(), client->bridge_log().text().c_str()); rc = 1; }
    else { printf("wrote %s\n", output.c_str()); }
    viewer.close(); shell.store().set_bridge(nullptr); client->close(); loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
