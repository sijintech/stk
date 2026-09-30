/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real archived inline table -> explicit paged scientific grid, no Viewer import. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <cstdio>
#include <fstream>
#include <stdexcept>

using namespace stk;
using io::Json;

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
  const bool narrow = mode.find("narrow") != std::string::npos;
  const int width = narrow ? 760 : 1440, height = 1200;
  bridge::test::TempDir directory{"analysis-table-grid-render"};
  bridge::test::ManualLoop loop;
  {
    std::ofstream csv(directory.path() / "stats.csv");
    csv << "step,temperature_difference,pressure,energy,density,velocity,field_x,field_y,phase,stress\n";
    for (int row = 0; row < 70; ++row) {
      csv << row << ',' << row - 9.5 << ",1,2,3,4,5,6," << (row % 2 ? "beta" : "alpha") << ',' << row - 35.5 << '\n';
    }
    if (!csv) { return 1; }
  }
  bridge::ClientOptions options;
  options.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
  options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = "";
  options.executor = loop.executor(); options.strict = options.validate = true;
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
    shell_options.language = language == "zh" ? "zh_CN" : "en"; shell_options.interactive = false;
    app::AppShell shell(shell_options);
    wm::Screen screen; shell.install(screen, nullptr); shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &viewer = shell.store().viewer();
    viewer.prefetch_neighbours = false; viewer.set_auto_evaluate(false);
    auto &project = shell.store().project();
    try {
      const auto require = [](const bool condition, const std::string &message) {
        if (!condition) { throw std::runtime_error(message); }
      };
      auto call = [&](const std::string &method, Json params) {
        auto reply = std::make_shared<std::optional<bridge::Result<Json>>>();
        auto future = client->call(method, params);
        future.then([reply](auto value) { *reply = std::move(value); });
        const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
        if (!done) { future.cancel(); }
        require(done, method + " timeout");
        require(reply->value().ok(), method + ": " + (reply->value() ? "" : reply->value().error().describe()));
        return reply->value().value();
      };
      project.sync(); require(project.create(directory.str() + "/project", "Frozen scalar analysis"), "create");
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "load project");
      const auto handle = project.project()->handle;
      const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
          {"paths", Json::array({core::path_to_utf8(directory.path() / "stats.csv")})}});
      const auto file_id = indexed.at("record_ids")[0];
      const auto captured = call("project.snapshots.capture", {{"handle", handle}, {"expected_revision", indexed.at("revision")},
          {"record_ids", Json::array({file_id})}});
      const Json graph = io::parse_json(R"JSON({
  "schema": "stk.graph/1",
  "id": "result-inspection",
  "nodes": [
    {
      "id": "table",
      "type": "stk.source.table@1",
      "params": {
        "binding": "data",
        "path": "stats.csv",
        "format": "csv",
        "units": {
          "temperature_difference": "K", "stress": "Pa"
        }
      }
    },
    {
      "id": "missing",
      "type": "stk.source.table@1",
      "params": {
        "binding": "data",
        "path": "absent.csv",
        "format": "csv"
      }
    }
  ],
  "outputs": {
    "table": "table.out",
    "missing": "missing.out"
  }
})JSON");
      const Json document = {{"format", "stk.analysis-document/1"}, {"graph", graph},
          {"parameters", Json::object()}, {"outputs", Json::array({"table", "missing"})}};
      const auto saved = call("project.analyses.create", {{"handle", handle}, {"analysis_id", "2dd622ed-3dd2-46b6-9567-4d0b4873916e"},
          {"name", language == "zh" ? "合成表格 · 部分结果" : "Synthetic table · partial result"},
          {"document", document}, {"expected_revision", captured.at("revision")}});
      const auto revision = saved.at("revision");
      project.refresh(); require(loop.pump_until([&] { return !project.busy(); }, 30), "refresh project");
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      require(area && area->set_tab_type(0, app::kEditorAnalysisGraph), "analysis editor");
      require(area->editor().load_state({{"saved", true}}), "saved mode");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 385 : 560);
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] {
        require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error);
      };
      auto widget = [&](const char *key) { return screen.ui()->find(key); };
      auto click = [&](const char *key) {
        const auto *value = widget(key);
        require(value && value->enabled && bool(value->on_click), std::string("button unavailable: ") + key);
        value->on_click(); frame();
      };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { frame(); return predicate(); }, 45), description);
      };
      auto toggle = [&](const char *key) {
        const auto *value = widget(key); require(value != nullptr, key);
        const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
        screen.ui()->handle_event(ui::Event::mouse_down(center));
        screen.ui()->handle_event(ui::Event::mouse_up(center)); frame();
      };
      frame(); click("analysis_list");
      wait([&] { return widget("analysis_documents") != nullptr; }, "analysis list");
      widget("analysis_documents")->table->selected.assign(0);
      wait([&] {
        const auto *ports = widget("graph_ports");
        return widget("analysis_rename") && widget("analysis_rename")->enabled &&
            ports && ports->table && ports->table->rows > 0;
      }, "saved definition and independently loaded node descriptions");
      widget("analysis_saved_section")->index.assign(1); frame();
      click("analysis_run_snapshots");
      wait([&] { return widget("analysis_run_snapshot") && widget("analysis_run_snapshot")->items.size() == 2; }, "snapshot list");
      widget("analysis_run_snapshot")->index.assign(1); frame();
      widget("analysis_run_file")->index.assign(1); frame();
      widget("analysis_run_path")->string.assign("stats.csv"); frame(); click("analysis_run_add_file");
      require(widget("analysis_run_bindings") && widget("analysis_run_bindings")->table->rows == 1, "mapped input");
      require(widget("analysis_run_bindings")->table->cell(0, 1) == "stats.csv", "relative mapped name");
      const auto no_runs = call("project.analysis_runs.list", {{"handle", handle}});
      require(no_runs.at("runs").empty(), "mapping must not prepare or execute");
      click("analysis_run_prepare");
      wait([&] { return widget("analysis_run_start") && widget("analysis_run_start")->enabled; }, "prepare run");
      const auto page = call("project.analysis_runs.list", {{"handle", handle}});
      require(page.at("runs").size() == 1 && page.at("runs")[0].at("status") == "prepared", "only one prepared run");
      toggle("analysis_run_prepare_panel"); toggle("analysis_run_history");
      click("analysis_run_start");
      wait([&] { return widget("analysis_run_read_result") && widget("analysis_run_read_result")->enabled; }, "execute partial run");
      const auto run_id = page.at("runs")[0].at("id");
      const auto finished = call("project.analysis_runs.get", {{"handle", handle}, {"run_id", run_id}}).at("run");
      require(finished.at("status") == "failed" && finished.at("result").at("has_errors") == true,
          "partial delivery must retain failed status");
      require(!widget("analysis_result_outputs"), "no automatic archive read");
      click("analysis_run_read_result");
      wait([&] { return widget("analysis_result_outputs") && widget("analysis_result_outputs")->table->rows == 2; }, "explicit archived outputs");
      if (widget("analysis_run_frozen_parameters")) { toggle("analysis_run_frozen"); }
      auto select = [&](const char *key, const std::string &name) {
        const auto *table = widget(key); require(table && table->table && table->enabled, key);
        int found = -1;
        for (int row = 0; row < table->table->rows; ++row) { if (table->table->cell(row, 0) == name || table->table->cell(row, 0) == io::python_json_dumps(Json(name), true, true)) { found = row; } }
        require(found >= 0, "missing property: " + name); table->table->selected.assign(found); frame();
      };
      select("analysis_result_outputs", "table");
      click("analysis_result_table_grid");
      require(widget("analysis_table_grid") != nullptr, "explicit inline table grid");
      require(widget("analysis_table_grid_jump_row") && widget("analysis_table_grid_jump_column"),
          "explicit source coordinate inputs");
      widget("analysis_table_grid_jump_row")->string.assign("64"); frame();
      widget("analysis_table_grid_jump_column")->string.assign("8"); frame();
      click("analysis_table_grid_jump");
      const auto *table = widget("analysis_table_grid");
      require(table && table->table && table->table->rows == 6, "all remaining rows after page64");
      require(table->table->cell(0, 1) == "\"alpha\"" && table->table->cell(1, 2) == "29.5",
          "source row and column identities survive independent paging");
      table->table->selected.assign(1); frame();
      require(widget("analysis_table_grid_column") != nullptr, "explicit selected-cell column");
      widget("analysis_table_grid_column")->index.assign(1); frame();
      // A widget may exist outside a scrolled region. Exercise the real sidebar
      // wheel path and require complete on-screen detail before exporting evidence.
      const auto sidebar = area->find_region(app::EditorArea::kSidebar)->ui_rect();
      screen.ui()->handle_event(ui::Event::wheel({sidebar.x1() - 2, sidebar.cy()}, -1000));
      frame();
      const auto visible = [&](const ui::Rect &rect) {
        return !rect.empty() && rect.intersect(sidebar) == rect;
      };
      bool exact_visible = false;
      for (const auto &block : screen.ui()->blocks()) {
        for (const auto &value : block->widgets()) {
          if (value.key.find("/analysis_table_grid_value/") != std::string::npos && value.text == "29.5") {
            exact_visible = visible(value.rect);
          }
        }
      }
      require(exact_visible, "selected exact scalar must be fully visible before screenshot");
      const auto *open_cell = widget("analysis_table_grid_open_cell");
      require(open_cell && open_cell->enabled && visible(open_cell->rect), "open cell action must be fully visible");
      require(!viewer.payload() && viewer.evaluations_started() == 0 && project.project()->revision == revision,
          "result inspection must not change editable revision or Viewer");
      require(viewer.catalog().is_null() && !viewer.presets_loaded(), "result inspection must not mutate Viewer metadata");
      frame(); require(gfx::png_write(output, image), "write screenshot");
      require(call("project.analysis_runs.list", {{"handle", handle}}).at("runs").size() == 1, "inspection must not create runs");
      require(client->stats().schema_violations == 0, "bridge schema violations");
      printf("wrote %s\n", output.c_str());
    }
    catch (const std::exception &exception) {
      fprintf(stderr, "FAIL: %s\n%s", exception.what(), client->bridge_log().text().c_str()); rc = 1;
    }
    viewer.close(); shell.store().set_bridge(nullptr); client->close(); loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
