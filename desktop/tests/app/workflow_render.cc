/* SPDX-License-Identifier: GPL-2.0-or-later */
/** A project workflow (cases -> field files -> saved analysis) on the canvas with a step selected,
 * (--scenario enter) its analysis opened in the same area with the breadcrumb back, or
 * (--scenario workflow_edit) an unsaved candidate with an added, linked and field-bound step, or
 * (--scenario workflow_run) a finished per-row run of cases -> synthetic solver -> analysis with its task grid, or
 * (--scenario home_attention) Home's "needs attention" box after a run with a failed row and a finished run. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <stdexcept>

using namespace stk;
using io::Json;

int main(int argc, char **argv)
{
  std::string backend_name, language = "en", output, mode = "wide", scenario = "workflow";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { language = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--mode") { mode = argv[i + 1]; }
    else if (arg == "--scenario") { scenario = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty() || (mode != "wide" && mode != "narrow") ||
      (scenario != "workflow" && scenario != "enter" && scenario != "workflow_edit" && scenario != "workflow_run" &&
       scenario != "home_attention")) { return 2; }
  const bool narrow = mode == "narrow", zh = language == "zh";
  const int width = narrow ? 760 : 1440, height = 900;
  bridge::test::TempDir directory{"workflow-render"};
  bridge::test::ManualLoop loop;
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
    shell_options.language = zh ? "zh_CN" : "en"; shell_options.interactive = false;
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
      int64_t revision = 0;
      auto call = [&](const std::string &method, Json params) {
        auto reply = std::make_shared<std::optional<bridge::Result<Json>>>();
        auto future = client->call(method, params);
        future.then([reply](auto value) { *reply = std::move(value); });
        const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
        if (!done) { future.cancel(); }
        require(done, method + " timeout");
        require(reply->value().ok(), method + ": " + (reply->value() ? "" : reply->value().error().describe()));
        const auto value = reply->value().value();
        if (value.contains("revision") && value.at("revision").is_number_integer()) { revision = value.at("revision").get<int64_t>(); }
        return value;
      };
      const auto root = directory.str() + "/project";
      project.sync(); require(project.create(root, zh ? "温度扫描示例" : "Temperature scan example"), "create");
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "load project");
      const auto handle = project.project()->handle;
      const std::string table = "11111111-1111-4111-8111-111111111111", analysis = "2f4c8a1e-5b3d-4e6f-8a9b-0c1d2e3f4a5b";
      const std::string workflow = "3a5d9b2f-6c4e-4f70-9bac-1d2e3f4a5b6c";
      call("project.apply", {{"handle", handle}, {"expected_revision", 0}, {"commands", {
          {{"op", "create_table"}, {"id", table}, {"name", zh ? "算例" : "Cases"}},
          {{"op", "add_field"}, {"id", "12121212-1212-4121-8121-121212121212"}, {"table_id", table},
           {"name", zh ? "色图" : "Colormap"}, {"type", "text"}}}}});
      for (const auto *name : {"case-1", "case-2", "case-3"}) {
        std::filesystem::create_directories(std::filesystem::path(root) / name);
        std::ofstream(std::filesystem::path(root) / name / "field.vtk") << "not read\n";
      }
      const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", revision},
          {"paths", {root + "/case-1/field.vtk", root + "/case-2/field.vtk", root + "/case-3/field.vtk"}}});
      const auto snapshot = call("project.snapshots.capture", {{"handle", handle}, {"expected_revision", revision},
          {"record_ids", indexed.at("record_ids")}}).at("snapshot").at("id").get<std::string>();
      call("project.analyses.create", {{"handle", handle}, {"analysis_id", analysis}, {"name", zh ? "温度场" : "Temperature field"},
          {"document", {{"format", "stk.analysis-document/1"},
              {"graph", io::read_json_file(std::filesystem::path(STK_REPO_ROOT) / "suan/graph/presets/volume.json").at("graph")},
              {"parameters", {{"path", "field.vtk"}}}, {"outputs", Json::array({"view"})}}},
          {"expected_revision", revision}});
      call("project.workflows.create", {{"handle", handle}, {"workflow_id", workflow}, {"name", zh ? "温度扫描" : "Temperature scan"},
          {"document", {{"format", "stk.workflow/1"}, {"steps", {
              {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table}}}},
              {{"id", "fields"}, {"kind", "files"}, {"ref", {{"snapshot", snapshot}}}, {"after", {"cases"}}},
              {{"id", "temperature"}, {"kind", "analysis"}, {"ref", {{"analysis", analysis}}},
               {"inputs", {{"data", {{"from", "fields.files"}}}}}}}},
              {"ui", {{"positions", {{"cases", {0, 0}}, {"fields", {260, 0}}, {"temperature", {520, 0}}}}}}}},
          {"expected_revision", revision}});
      const bool runs = scenario == "workflow_run" || scenario == "home_attention";
      if (runs) {
        // Three temperatures and the runnable form of the workflow: the synthetic solver per row, then the analysis.
        const std::string temperature = "17171717-1717-4171-8171-171717171717";
        Json commands = Json::array({{{"op", "add_field"}, {"id", temperature}, {"table_id", table},
                                      {"name", zh ? "温度" : "Temperature"}, {"type", "number"}, {"unit", "K"}}});
        const char *rows[] = {"18181818-1818-4181-8181-181818181801", "18181818-1818-4181-8181-181818181802",
                              "18181818-1818-4181-8181-181818181803"};
        for (int i = 0; i < 3; ++i) {
          commands.push_back({{"op", "add_record"}, {"id", rows[i]}, {"table_id", table}});
          commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", rows[i]}, {"field_id", temperature},
                              {"value", scenario == "home_attention" && i == 2 ? -5 : 300 + 25 * i}});  // -5 K fails
        }
        call("project.apply", {{"handle", handle}, {"expected_revision", revision}, {"commands", commands}});
        call("project.workflows.update", {{"handle", handle}, {"workflow_id", workflow}, {"name", zh ? "温度扫描" : "Temperature scan"},
            {"document", {{"format", "stk.workflow/1"}, {"steps", {
                {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table}}}},
                {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
                 {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", temperature}}}}}},
                {{"id", "temperature"}, {"kind", "analysis"}, {"ref", {{"analysis", analysis}}},
                 {"inputs", {{"data", {{"from", "simulate.files"}}}}}}}},
                {"ui", {{"positions", {{"cases", {0, 0}}, {"simulate", {260, 0}}, {"temperature", {520, 0}}}}}}}},
            {"expected_revision", revision}});
      }
      project.refresh(); require(loop.pump_until([&] { return !project.busy() && project.project()->revision == revision; }, 30),
                                 "refresh project");
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      require(area && area->set_tab_type(0, app::kEditorWorkflow), "workflow editor");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 385 : 520);
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error); };
      auto widget = [&](const std::string &key) { return screen.ui()->find(key); };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { screen.run_deferred(); frame(); return predicate(); }, 45), description);
      };
      auto shows = [&](const std::string &text) {
        for (const auto &block : screen.ui()->blocks()) {
          for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
        }
        return false;
      };
      wait([&] { return shows(zh ? "所有引用与连线都有效。" : "All references and links are valid."); }, "workflow checked");
      std::string reason;
      require(area->editor().navigate({{"workflow_id", workflow}, {"step", "temperature"}}, {}, reason), "select step");
      frame();
      require(widget("workflow_enter_analysis") && widget("workflow_enter_analysis")->enabled, "enter button");
      auto choose = [&](const std::string &key, const std::string &label) {
        const auto *dropdown = widget(key);
        require(dropdown && dropdown->enabled, "dropdown unavailable: " + key);
        const auto found = std::find_if(dropdown->items.begin(), dropdown->items.end(),
            [&](const std::string &item) { return item.find(label) != std::string::npos; });
        require(found != dropdown->items.end(), "no entry " + label + " in " + key);
        dropdown->index.assign(int(found - dropdown->items.begin())); frame();
      };
      if (scenario == "workflow_edit") {
        // A second analysis step: added, linked to the field files, its colormap taken per row; not saved.
        wait([&] { return widget("workflow_add_object") && widget("workflow_add_object")->enabled; }, "choices");
        choose("workflow_add_kind", zh ? "分析" : "Analysis");
        choose("workflow_add_object", zh ? "温度场" : "Temperature field");
        widget("workflow_add_step")->on_click(); frame();
        wait([&] { return widget("workflow_input/data/source") != nullptr; }, "added step selected");
        choose("workflow_input/data/source", "fields.files");
        wait([&] { return widget("workflow_param/colormap/mode") != nullptr; }, "parameters");
        choose("workflow_param/colormap/mode", zh ? "参数表字段" : "Parameter table field");
        wait([&] { return shows(zh ? "修改后所有引用与连线都有效。" : "After the changes all references and links are valid."); }, "candidate check");
        const auto unchanged = call("project.workflows.get", {{"handle", handle}, {"workflow_id", workflow}});
        require(unchanged.at("workflow").at("document").at("steps").size() == 3, "editing must not save");
      }
      if (scenario == "workflow_run") {
        wait([&] { return widget("workflow_run_start") && widget("workflow_run_start")->enabled; }, "run panel");
        widget("workflow_run_start")->on_click();
        wait([&] { return shows(zh ? "全部完成 · 完成 6/6" : "All done · 6/6 done"); }, "run finished");
        // The run list is read again once the run stops.
        wait([&] { const auto *runs = widget("workflow_runs");
                   return runs && runs->table && runs->table->rows == 1 && runs->table->cell(0, 3) == "6/6"; }, "run list updated");
        // Row 2's temperature changes afterwards: it is marked stale with the reason (W4c); its old result stays.
        call("project.apply", {{"handle", handle}, {"expected_revision", project.project()->revision}, {"commands", {
            {{"op", "set_cell"}, {"table_id", table}, {"record_id", "18181818-1818-4181-8181-181818181802"},
             {"field_id", "17171717-1717-4171-8171-171717171717"}, {"value", 330}}}}});
        project.refresh();
        wait([&] { return shows(zh ? "1 行的结果已过期" : "1 rows have stale results"); }, "stale rows");
        widget("workflow_run_tasks")->table->selected.assign(1); frame();
        // Bring the run panel into view (the sidebar is long); the canvas keeps the selected step.
        const auto *header = widget("workflow_edit_panel");
        if (header) {
          const ui::Vec2 center{header->rect.x + 8, header->rect.cy()};
          screen.ui()->handle_event(ui::Event::mouse_down(center)); screen.ui()->handle_event(ui::Event::mouse_up(center)); frame();
        }
      }
      if (scenario == "home_attention") {
        // All three rows (the third fails in the synthetic solver), then row 1 alone (finishes); Home lists both.
        const auto run = [&](const std::string &id, const Json &rows) {
          const auto saved = call("project.workflows.get", {{"handle", handle}, {"workflow_id", workflow}});
          call("project.workflow_runs.prepare", {{"handle", handle}, {"workflow_id", workflow}, {"rows", rows}, {"run_id", id},
              {"expected_revision", saved.at("revision")}});
          call("project.workflow_runs.start", {{"handle", handle}, {"run_id", id}});
          wait([&] { return call("project.workflow_runs.get", {{"handle", handle}, {"run_id", id}}).at("run").at("status") == "stopped"; },
               "run stopped");
        };
        run("19191919-1919-4191-8191-191919191901", Json::array({"18181818-1818-4181-8181-181818181801",
            "18181818-1818-4181-8181-181818181802", "18181818-1818-4181-8181-181818181803"}));
        run("19191919-1919-4191-8191-191919191902", Json::array({"18181818-1818-4181-8181-181818181801"}));
        project.refresh();
        require(area->set_tab_type(0, app::kEditorWorkspace), "home");
        wait([&] { return shows(zh ? "失败 · 工作流运行 · 温度扫描 · 完成 4/6" : "Failed · Workflow run · Temperature scan · 4/6 done") &&
                          shows(zh ? "已完成未查看（1）" : "Finished, not viewed (1)"); }, "attention listed");
      }
      if (scenario == "enter") {
        widget("workflow_enter_analysis")->on_click();
        // Wait for the node catalog too, so nodes are drawn with their types rather than as unknown.
        wait([&] { return widget("analysis_breadcrumb_workflow") != nullptr && widget("graph_mode") &&
            widget("graph_mode")->index.value() == 2 && widget("analysis_parameters") != nullptr &&
            !shows(zh ? "正在读取节点说明" : "Reading node descriptions"); }, "analysis with breadcrumb");
      }
      frame(); require(gfx::png_write(output, image), "write screenshot");
      // Only the run scenarios prepare analysis runs, through an explicit start.
      require(runs || call("project.analysis_runs.list", {{"handle", handle}}).at("runs").empty(),
              "browsing must not prepare a run");
      require(!viewer.payload() && viewer.evaluations_started() == 0, "browsing must not configure or evaluate the Viewer");
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
