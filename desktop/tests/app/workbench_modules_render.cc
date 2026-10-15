/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real project, lazy directory tree, typed table and Viewer in the default split workspace.
 * All files and values are synthetic. No Runtime, model or solver is contacted. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
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

namespace {
bool write_text(const std::filesystem::path &path, const std::string &text)
{
  std::ofstream file(path, std::ios::binary);
  file << text;
  file.close();
  return bool(file);
}

int table_row(const wm::Screen &screen, const std::string &name)
{
  const auto *tree = screen.ui()->find("files_tree");
  if (!tree || !tree->table) { return -1; }
  for (int row = 0; row < tree->table->rows; ++row) {
    if (tree->table->cell(row, 0).find(name) != std::string::npos) { return row; }
  }
  return -1;
}

const ui::Widget *records_widget(const wm::Screen &screen)
{
  return screen.ui()->find("records");
}
}  // namespace

int main(int argc, char **argv)
{
  std::string backend_name, language = "en", output, mode = "nodes_wide";
  if ((argc - 1) % 2 != 0) { return 2; }
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { language = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--mode") { mode = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty() || (language != "en" && language != "zh") ||
      (mode != "nodes_wide" && mode != "nodes_narrow" && mode != "python_wide" && mode != "python_narrow" &&
       mode != "table_wide" && mode != "table_narrow" && mode != "table_focus" && mode != "table_board" && mode != "table_gallery")) {
    return 2;
  }
  const bool python = mode == "python_wide" || mode == "python_narrow";
  const bool tables = mode.starts_with("table_");
  const bool focused = mode == "table_focus" || mode == "table_board" || mode == "table_gallery";
  const bool narrow = mode == "nodes_narrow" || mode == "python_narrow" || mode == "table_narrow";
  const int width = narrow ? 900 : 1440, height = 1000;
  bridge::test::TempDir directory{"workbench-modules-render"};
  bridge::test::ManualLoop loop;
  bridge::ClientOptions options;
  options.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  options.state_dir = directory.str() + "/bridge";
  options.cache_dir = directory.str() + "/cache";
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
  options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = "";
  options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  options.executor = loop.executor();
  options.strict = options.validate = true;
  auto client = bridge::Client::create(options);
  std::string error;
  if (!client->start(&error) || !client->wait_ready(60)) {
    fprintf(stderr, "FAIL: bridge startup: %s\n", error.c_str());
    return 1;
  }
  loop.run_ready();
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  int rc = 0;
  {
    gfx::GpuOptions gpu_options;
    gpu_options.backend = backend;
    auto gpu = gfx::Gpu::create(*system, gpu_options, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(1);
    app::ShellOptions shell_options;
    shell_options.language = language == "zh" ? "zh_CN" : "en";
    shell_options.interactive = false;
    app::AppShell shell(shell_options);
    wm::Screen screen;
    shell.install(screen, nullptr);
    shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &project = shell.store().project();
    auto &viewer = shell.store().viewer();
    viewer.prefetch_neighbours = false;
    project.sync();
    std::string stage = "create synthetic project";
    bool ok = loop.pump_until([&] { return project.ready(); }, 60) &&
        project.create(directory.str() + "/project", language == "zh" ? "合成材料演练" : "Synthetic material study") &&
        loop.pump_until([&] { return !project.busy() && project.loaded(); }, 30);
    const std::string table = "11111111-1111-4111-8111-111111111111";
    const std::string temperature = "22222222-2222-4222-8222-222222222222";
    const std::string label = "33333333-3333-4333-8333-333333333333";
    const std::string reviewed = "55555555-5555-4555-8555-555555555555";
    io::Json commands = io::Json::array({
        {{"op", "create_table"}, {"id", table}, {"name", language == "zh" ? "合成观测" : "Synthetic observations"}},
        {{"op", "add_field"}, {"id", temperature}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
        {{"op", "add_field"}, {"id", label}, {"table_id", table}, {"name", "Source"}, {"type", "text"}},
        {{"op", "add_field"}, {"id", reviewed}, {"table_id", table}, {"name", "Reviewed"}, {"type", "boolean"}}
    });
    const std::string phase = "66666666-6666-4666-8666-666666666666";
    const std::string date = "77777777-7777-4777-8777-777777777777";
    const std::string evidence = "88888888-8888-4888-8888-888888888888";
    const std::string dry = "99999999-9999-4999-8999-999999999999";
    const std::string wet = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    if (tables) {
      commands.push_back({{"op", "add_field"}, {"id", phase}, {"table_id", table}, {"name", language == "zh" ? "状态" : "State"}, {"type", "single_select"},
        {"options", {{"version", 1}, {"choices", io::Json::array({{{"id", dry}, {"label", language == "zh" ? "待复核" : "To review"}, {"color", "#5B8FF9"}},
          {{"id", wet}, {"label", language == "zh" ? "已复核" : "Reviewed"}, {"color", "#61DDAA"}}})}}}});
      commands.push_back({{"op", "add_field"}, {"id", date}, {"table_id", table}, {"name", language == "zh" ? "日期" : "Date"}, {"type", "date"}});
      commands.push_back({{"op", "add_field"}, {"id", evidence}, {"table_id", table}, {"name", language == "zh" ? "证据对象" : "Evidence"}, {"type", "object"},
        {"options", {{"version", 1}, {"kinds", {"record", "file", "snapshot_file", "analysis", "simulation", "workflow"}}}}});
    }
    for (int i = 0; i < (tables ? 24 : 3); ++i) {
      const std::string id = std::to_string(40000000 + i) + "-4444-4444-8444-444444444444";
      commands.push_back({{"op", "add_record"}, {"id", id}, {"table_id", table}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", temperature}, {"value", 300 + i * 25}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", label}, {"value", "synthetic"}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", reviewed}, {"value", i == 0}});
      if (tables) {
        commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", phase}, {"value", i % 3 == 0 ? dry : wet}});
        commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", date}, {"value", "2026-10-15"}});
        commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", evidence},
          {"value", {{"version", 1}, {"project_id", project.project()->id}, {"kind", "record"}, {"id", "40000000-4444-4444-8444-444444444444"}, {"table_id", table}}}});
      }
    }
    if (tables) {
      const auto kind = mode == "table_board" ? "board" : mode == "table_gallery" ? "gallery" : "grid";
      commands.push_back({{"op", "put_table_view"}, {"id", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}, {"table_id", table},
        {"name", language == "zh" ? "复核工作视图" : "Review workspace"}, {"definition", {{"version", 1}, {"kind", kind}, {"group_field_id", phase}}}});
    }
    ok = ok && project.apply(commands) && loop.pump_until([&] { return !project.busy(); }, 30);
    const auto inputs = directory.path() / "project" / "inputs";
    const auto results = directory.path() / "project" / "results";
    const auto source = results / "field.dat";
    const auto program = inputs / "inspect.py";
    const std::string code =
        "# Synthetic example; reads the open project only.\n"
        "snapshot = stk.project.snapshot()\n"
        "print('Project:', snapshot['project']['name'])\n"
        "for temperature in [300, 325, 350]:\n"
        "    print(f'{temperature} K = {temperature - 273.15:.2f} C')\n";
    if (ok) {
      stage = "write public synthetic files";
      std::error_code ec;
      std::filesystem::create_directories(inputs, ec);
      ok = !ec;
      std::filesystem::create_directories(results, ec);
      ok = ok && !ec && write_text(program, code) &&
          write_text(inputs / "material.json", "{\"source_kind\":\"synthetic\",\"name\":\"Example\"}\n");
      std::ofstream file(source, std::ios::binary);
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
      file.close();
      ok = ok && bool(file) && project.index_files({core::path_to_utf8(source), core::path_to_utf8(inputs / "material.json"),
                                                  core::path_to_utf8(inputs / "missing.dat")}) &&
          loop.pump_until([&] { return !project.busy(); }, 30);
      project.select_table(table);
      ok = ok && project.table_id() == table;
    }
    if (ok) {
      stage = "evaluate synthetic field once";
      ok = loop.pump_until([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60) &&
          viewer.open_path(core::path_to_utf8(source), "volume") &&
          loop.pump_until([&] { viewer.pump(); return !viewer.evaluating() && bool(viewer.payload()); }, 60);
    }
    const auto payload = viewer.payload();
    const int evaluations = viewer.evaluations_started();
    const int64_t revision = project.project() ? project.project()->revision : -1;
    viewer.set_auto_evaluate(false);
    auto *files_area = dynamic_cast<app::EditorArea *>(screen.find_area("a1"));
    auto *viewer_area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
    auto *tools_area = dynamic_cast<app::EditorArea *>(screen.find_area("a3"));
    auto *table_area = dynamic_cast<app::EditorArea *>(screen.find_area("a4"));
    ok = ok && files_area && viewer_area && tools_area && table_area && screen.areas().size() == 4 &&
        !screen.maximized() && files_area->editor().type().id == app::kEditorFiles &&
        viewer_area->editor().type().id == app::kEditorViewer && tools_area->editor().type().id == app::kEditorAnalysisGraph &&
        table_area->editor().type().id == app::kEditorTable;
    if (ok) {
      stage = "expand actual input directory";
      wm::DrawContext context;
      context.ui_scale = 1;
      context.fonts = &gpu->fonts();
      context.rect = {0, 0, width, height};
      context.now = 100;
      gfx::Image image;
      auto frame = [&] {
        screen.run_deferred();
        viewer.pump();
        return gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error);
      };
      bool drawing = true;
      ok = loop.pump_until([&] {
        drawing = frame();
        return !drawing || table_row(screen, "inputs") >= 0;
      }, 30) && drawing;
      if (ok) {
        screen.ui()->find("files_tree")->table->selected.assign(table_row(screen, "inputs"));
        ok = frame();
        const auto *expand = screen.ui()->find("files_toggle");
        if (expand && expand->enabled) { expand->on_click(); } else { ok = false; }
        ok = ok && loop.pump_until([&] {
          drawing = frame();
          return !drawing || table_row(screen, "inspect.py") >= 0;
        }, 30) && drawing;
      }
      if (ok) {
        const auto *tree = screen.ui()->find("files_tree");
        tree->table->selected.assign(table_row(screen, "inspect.py"));
        ok = frame();
        const auto *code_open = screen.ui()->find("files_open_code");
        const auto *records = records_widget(screen);
        ok = ok && code_open && code_open->enabled && records && records->table->rows == (tables ? 24 : 3) &&
            records->table->cell(0, 1) == "300" && records->table->cell(0, 2) == "synthetic";
      }
      if (ok && python) {
        stage = "load and explicitly run public example program";
        // Use the actual tree action: navigation must reuse the right Python tab and
        // leave both the directory tree and Viewer visible.
        const auto *open = screen.ui()->find("files_open_code");
        if (open && open->enabled) { open->on_click(); } else { ok = false; }
        ok = ok && loop.pump_until([&] {
          drawing = frame();
          if (!drawing) { return true; }
          const auto state = tools_area->editor().save_state();
          return tools_area->editor().type().id == app::kEditorPython &&
              io::get_string(state, "source") == code && !io::get_string(state, "version").empty();
        }, 30) && drawing;
        auto &scripts = shell.store().scripts();
        ok = ok && loop.pump_until([&] {
          drawing = frame();
          return !drawing || (scripts.ready() && scripts.desktop_ready() && !scripts.busy());
        }, 30) && drawing;
        if (ok) {
          const auto *run = screen.ui()->find("python_run");
          if (run && run->enabled) { run->on_click(); } else { ok = false; }
          ok = ok && loop.pump_until([&] {
            drawing = frame();
            return !drawing || (!scripts.busy() && scripts.status().contains("run") &&
                                io::get_string(scripts.status().at("run"), "state") == "succeeded");
          }, 30) && drawing && screen.ui()->find("python_source") && screen.ui()->find("python_output") &&
              scripts.output().line_count() >= 4;
        }
      }
      else if (ok && !tables) {
        stage = "fit verified source pipeline beside Viewer";
        const auto inspection = viewer.graph_inspection();
        ok = inspection && inspection->shown_graph_verified.value_or(false) && inspection->shown_matches_desired.value_or(false);
        const auto *mode_widget = screen.ui()->find("graph_mode");
        if (mode_widget) { mode_widget->index.assign(1); } else { ok = false; }
        ok = ok && frame();
        const auto *fit = screen.ui()->find("graph_fit");
        if (fit && fit->enabled) { fit->on_click(); } else { ok = false; }
      }
      if (ok && tables) {
        stage = "show typed table workspace";
        ok = loop.pump_until([&] { drawing = frame(); const auto *v = screen.ui()->find("table_views"); return !drawing || (v && v->items.size() >= 2); }, 30) && drawing;
        if (ok && (mode == "table_board" || mode == "table_gallery")) { screen.ui()->find("table_views")->index.assign(1); }
        if (focused) { screen.set_maximized(table_area); }
        ok = ok && loop.pump_until([&] {
          drawing = frame();
          const auto *records = screen.ui()->find("records");
          return !drawing || (mode == "table_board" || mode == "table_gallery" ? screen.ui()->find("open") != nullptr : records && records->table->rows == 24);
        }, 30) && drawing;
      }
      stage = ok ? "export combined workspace" : stage;
      ok = ok && frame() && (focused ? screen.maximized() == table_area : !screen.maximized()) && files_area->editor().type().id == app::kEditorFiles &&
          viewer_area->editor().type().id == app::kEditorViewer && table_area->editor().type().id == app::kEditorTable &&
          viewer.payload() == payload && viewer.evaluations_started() == evaluations &&
          project.project()->revision == revision && project.table_id() == table && client->stats().schema_violations == 0 &&
          gfx::png_write(output, image);
    }
    if (ok) { printf("wrote %s\n", output.c_str()); }
    else {
      fprintf(stderr, "FAIL: %s: %s\nViewer: %s\nProject: %s\n", stage.c_str(), error.c_str(),
              viewer.eval_error().c_str(), project.error().c_str());
      rc = 1;
    }
    viewer.close();
    shell.store().set_bridge(nullptr);
    client->close();
    loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
