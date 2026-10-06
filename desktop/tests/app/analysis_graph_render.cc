/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real local graph evaluation -> verified Viewer receipt -> read-only native graph -> PNG. */
#include "stk/app/editor_area.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/project_state.hh"
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
  if (output.empty() || (mode != "wide" && mode != "narrow" && mode != "saved_wide" && mode != "saved_narrow")) { return 2; }
  const bool saved = mode == "saved_wide" || mode == "saved_narrow";
  const bool narrow = mode == "narrow" || mode == "saved_narrow";
  const int width = narrow ? 760 : 1440, height = saved ? 1200 : 1000;
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
    const auto original_viewer = viewer.graph_inspection();
    auto &project = shell.store().project();
    if (saved) {
      project.sync();
      ok = ok && project.create(directory.str() + "/project", "Saved analyses") &&
          loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30);
      ok = ok && project.project() && project.project()->revision == 0;
    }
    auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
    ok = ok && area && area->set_tab_type(0, app::kEditorAnalysisGraph);
    if (ok) {
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(saved ? (narrow ? 340 : 430) : (narrow ? 260 : 350));
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { return gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error); };
      auto has_text = [&](const std::string &text) {
        for (const auto &block : screen.ui()->blocks()) {
          for (const auto &widget : block->widgets()) {
            if (widget.text.find(text) != std::string::npos) { return true; }
          }
        }
        return false;
      };
      auto toggle_panel = [&](const char *key) {
        // Panels above may grow as the editor gains sections: scroll the header into the
        // sidebar through the real wheel path before clicking it, never click off-screen.
        const auto sidebar = area->find_region(app::EditorArea::kSidebar)->ui_rect();
        const auto *panel = screen.ui()->find(key);
        for (int step = 0; panel && step < 60 && panel->rect.intersect(sidebar) != panel->rect; ++step) {
          screen.ui()->handle_event(ui::Event::wheel({sidebar.x1() - 2, sidebar.cy()}, panel->rect.cy() > sidebar.cy() ? -1.0f : 1.0f));
          if (!frame()) { return false; }
          panel = screen.ui()->find(key);
        }
        if (!panel || panel->rect.intersect(sidebar) != panel->rect) { return false; }
        const ui::Vec2 center{panel->rect.x + panel->rect.w / 2, panel->rect.y + panel->rect.h / 2};
        screen.ui()->handle_event(ui::Event::mouse_down(center));
        screen.ui()->handle_event(ui::Event::mouse_up(center));
        return frame();
      };
      ok = ok && frame();
      if (saved) {
        ok = ok && toggle_panel("graph_documents");
        const ui::Widget *name = nullptr;
        for (const auto &block : screen.ui()->blocks()) {
          for (const auto &widget : block->widgets()) {
            if (widget.key.find("/analysis_name/") != std::string::npos) { name = &widget; }
          }
        }
        if (name && name->enabled) { name->string.assign("analysis"); } else { ok = false; }
        ok = ok && frame();
        const auto *save = screen.ui()->find("analysis_save");
        if (save && save->enabled) { save->on_click(); } else { ok = false; }
        ok = ok && loop.pump_until([&] {
          if (!frame()) { ok = false; return true; }
          const auto *tabs = screen.ui()->find("graph_mode");
          return !project.busy() && project.project()->revision == 1 && tabs && tabs->index.value() == 2;
        }, 30);
        ok = ok && project.tables().size() == 1 && project.tables().front().records.size() == 1;
        const auto *refresh = screen.ui()->find("analysis_list");
        if (refresh && refresh->enabled) { refresh->on_click(); } else { ok = false; }
        ok = ok && loop.pump_until([&] {
          if (!frame()) { ok = false; return true; }
          return screen.ui()->find("analysis_documents") != nullptr;
        }, 30);
        // Load the persisted record through the normal list after returning to the live view.
        // This proves the saved canvas comes from a project read, not the initial save copy.
        const auto *tabs = screen.ui()->find("graph_mode");
        if (tabs) { tabs->index.assign(0); } else { ok = false; }
        ok = ok && frame();
        const auto *list = screen.ui()->find("analysis_documents");
        if (list && list->enabled && list->table && list->table->rows == 1 &&
            project.tables().size() == 1 && project.tables().front().records.size() == 1) {
          ok = ok && list->table->cell(0, 0) == "analysis" &&
              list->table->cell(0, 1) == shell.store().tr("analysis_documents.state.readable") &&
              list->table->cell(0, 2) == project.tables().front().records.front().id;
          list->table->selected.assign(0);
        }
        else { ok = false; }
        ok = ok && loop.pump_until([&] {
          if (!frame()) { ok = false; return true; }
          const auto *current = screen.ui()->find("graph_mode");
          return current && current->index.value() == 2 && screen.ui()->find("analysis_rename") &&
              screen.ui()->find("analysis_rename")->enabled;
        }, 30);
        ok = ok && has_text(std::string(shell.store().tr("analysis_documents.definition_only"))) &&
            !has_text(std::string(shell.store().tr("analysis_graph.executed_receipt"))) &&
            !has_text(std::string(shell.store().tr("analysis_graph.same_configuration"))) &&
            !has_text(std::string(shell.store().tr("analysis_graph.different_configuration")));
        if (original_viewer->shown_evaluation) { ok = ok && !has_text(original_viewer->shown_evaluation->eval_id); }
      }
      else if (narrow) {
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
      if (saved) {
        ok = ok && has_text(std::string(shell.store().tr("analysis_graph.submitted")) + ": turbo") &&
            !has_text(std::string(shell.store().tr("analysis_graph.executed_receipt")));
        // Keep the document list and source disclaimer visible alongside typed submitted values.
        ok = ok && toggle_panel("graph_node") && toggle_panel("graph_parameters");
        const auto *values = screen.ui()->find("graph_parameter_values");
        bool colormap = false;
        if (values && values->table) {
          for (int row = 0; row < values->table->rows; ++row) {
            ok = ok && values->table->cell(row, 2).empty();
            colormap |= values->table->cell(row, 0) == "colormap" && values->table->cell(row, 1) == "turbo";
          }
        }
        ok = ok && colormap;
      }
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
      if (saved) {
        ok = ok && viewer.graph_inspection() == original_viewer && viewer.payload() &&
            project.project()->revision == 1 && has_text(std::string(shell.store().tr("analysis_documents.definition_only")));
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
