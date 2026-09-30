/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Frozen run graph inspection stays independent of later saved-analysis edits. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "scalar_volume_support.hh"

#include <cstdio>
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
  const bool narrow = mode == "narrow";
  const int width = narrow ? 760 : 1440, height = 1200;
  bridge::test::TempDir directory{"analysis-graph-run-render"};
  bridge::test::ManualLoop loop;
  if (!apptest::write_signed_field(directory.path() / "signed.dat")) { return 1; }
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
          {"paths", Json::array({core::path_to_utf8(directory.path() / "signed.dat")})}});
      const auto file_id = indexed.at("record_ids")[0];
      const auto captured = call("project.snapshots.capture", {{"handle", handle}, {"expected_revision", indexed.at("revision")},
          {"record_ids", Json::array({file_id})}});
      const Json document = {{"format", "stk.analysis-document/1"},
          {"graph", io::read_json_file(std::filesystem::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
          {"parameters", {{"path", "fields/signed.dat"}, {"field", "signed"}, {"component", 1}, {"unit", "K"}}},
          {"outputs", Json::array({"view"})}};
      const auto saved = call("project.analyses.create", {{"handle", handle}, {"analysis_id", "2dd622ed-3dd2-46b6-9567-4d0b4873916e"},
          {"name", language == "zh" ? "温差分析 · 冻结输入" : "Temperature difference · frozen input"},
          {"document", document}, {"expected_revision", captured.at("revision")}});
      const auto revision = saved.at("revision");
      project.refresh(); require(loop.pump_until([&] { return !project.busy(); }, 30), "refresh project");
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      require(area && area->set_tab_type(0, app::kEditorAnalysisGraph), "analysis editor");
      require(area->editor().load_state({{"saved", true}}), "saved mode");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 385 : 510);
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
      widget("analysis_run_path")->string.assign("fields/signed.dat"); frame(); click("analysis_run_add_file");
      require(widget("analysis_run_bindings") && widget("analysis_run_bindings")->table->rows == 1, "mapped input");
      require(widget("analysis_run_bindings")->table->cell(0, 1) == "fields/signed.dat", "relative mapped name");
      const auto no_runs = call("project.analysis_runs.list", {{"handle", handle}});
      require(no_runs.at("runs").empty(), "mapping must not prepare or execute");
      click("analysis_run_prepare");
      wait([&] { return widget("analysis_run_inspect") && widget("analysis_run_inspect")->enabled; }, "prepare run");
      const auto page = call("project.analysis_runs.list", {{"handle", handle}});
      require(page.at("runs").size() == 1 && page.at("runs")[0].at("status") == "prepared", "one prepared run");
      const auto run_id = page.at("runs")[0].at("id");
      const auto frozen = call("project.analysis_runs.get", {{"handle", handle}, {"run_id", run_id}}).at("run");
      require(frozen.at("document").at("parameters").at("component") == 1, "frozen original component");
      // A later editable definition is deliberately different. The explicit historical view must
      // keep the original parameters without replacing the separate saved-document inspection.
      auto newer = document; newer["parameters"]["component"] = 2;
      const auto changed = call("project.analyses.update", {{"handle", handle},
          {"analysis_id", frozen.at("analysis_id")}, {"name", "Current definition"},
          {"document", newer}, {"expected_revision", revision}});
      project.refresh(); wait([&] { return !project.busy(); }, "later project revision");
      widget("analysis_saved_section")->index.assign(0); frame(); click("analysis_reload");
      wait([&] { return widget("analysis_parameters") && widget("analysis_parameters")->enabled; }, "reload current definition");
      auto parameter = [&](const char *key, const char *name) {
        const auto *value = widget(key); require(value && value->table, key);
        for (int row = 0; row < value->table->rows; ++row) {
          if (value->table->cell(row, 0) == name) { return value->table->cell(row, 1); }
        }
        throw std::runtime_error(std::string("missing parameter: ") + name);
      };
      require(parameter("analysis_parameters", "component") == "2", "current saved component");
      widget("analysis_saved_section")->index.assign(1); frame();
      std::error_code ec;
      require(std::filesystem::remove(directory.path() / "signed.dat", ec) && !ec, "remove live source");
      auto &scripts = shell.store().scripts();
      wait([&] { return scripts.ready() && scripts.desktop_ready() && io::get_int(scripts.status(), "cursor", -1) >= 0; }, "settle script session");
      const auto sent = client->stats().calls_sent;
      click("analysis_run_inspect");
      require(widget("graph_mode") && widget("graph_mode")->index.value() == 3, "explicit frozen mode");
      require(widget("graph_run_source") && widget("graph_run_files"), "pinned provenance and file mapping");
      require(!widget("analysis_parameters_save") && !widget("analysis_save") && !widget("analysis_run_prepare"), "read-only source");
      if (!widget("graph_parameter_values")) { toggle("graph_parameters"); }
      require(parameter("graph_parameter_values", "component") == "1", "inspect original frozen component");
      if (!widget("graph_output_rows")) { toggle("graph_outputs"); }
      const auto *outputs = widget("graph_output_rows");
      require(outputs && outputs->table && outputs->table->rows == 2 && outputs->table->columns.size() == 3,
          "frozen output requests have no result column");
      for (int row = 0; row < outputs->table->rows; ++row) {
        const bool selected = outputs->table->cell(row, 0) == "view";
        require(outputs->table->cell(row, 1) == shell.store().tr(selected ?
            "analysis_graph.requested" : "analysis_graph.not_requested"), "frozen output selection");
      }
      require(client->stats().calls_sent == sent, "inspect must not send requests or read files");
      require(widget("graph_run_files")->table->rows == 1 &&
          widget("graph_run_files")->table->cell(0, 1) == "fields/signed.dat", "frozen relative mapping");
      // The selected node may be collapsed to give the provenance and exact parameters room in
      // the narrow image; this is ordinary sidebar interaction, not a special rendering layout.
      if (widget("graph_ports")) { toggle("graph_node"); }
      frame(); require(gfx::png_write(output, image), "write screenshot");
      click("analysis_run_return_saved");
      require(widget("graph_mode")->index.value() == 2, "return to saved source");
      if (widget("analysis_saved_section")->index.value() != 0) {
        widget("analysis_saved_section")->index.assign(0); frame();
      }
      require(parameter("analysis_parameters", "component") == "2", "saved definition was never replaced");
      const auto observed = call("project.analysis_runs.get", {{"handle", handle}, {"run_id", run_id}}).at("run");
      require(observed.at("status") == "prepared" && observed.at("plan_sha256") == frozen.at("plan_sha256"), "inspection never starts or rewrites run");
      require(!viewer.payload() && viewer.evaluations_started() == 0 && project.project()->revision == changed.at("revision"),
          "inspection must not change editable revision or Viewer");
      require(viewer.catalog().is_null() && !viewer.presets_loaded(), "independent node descriptions");
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
