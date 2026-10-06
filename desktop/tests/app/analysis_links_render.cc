/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Saved analysis -> one single-input link replaced -> explicit validation -> CAS save, without evaluation. */
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
  bridge::test::TempDir directory{"analysis-links-render"};
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
      project.sync(); require(project.create(directory.str() + "/project", "Analysis links"), "create");
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "load project");
      const auto handle = project.project()->handle;
      const std::string analysis_id = "2f4c8a1e-5b3d-4e6f-8a9b-0c1d2e3f4a5b";
      const std::string name = language == "zh" ? "带符号标量 · 连线草稿" : "Signed scalar · link draft";
      const Json document = {{"format", "stk.analysis-document/1"},
          {"graph", io::read_json_file(std::filesystem::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
          {"parameters", {{"path", "fields/signed.dat"}, {"field", "signed"}, {"component", 0}, {"unit", nullptr}}},
          {"outputs", Json::array({"view"})}};
      const auto saved = call("project.analyses.create", {{"handle", handle}, {"analysis_id", analysis_id},
          {"name", name}, {"document", document}, {"expected_revision", 0}});
      const int64_t revision = saved.at("revision").get<int64_t>();
      project.refresh(); require(loop.pump_until([&] { return !project.busy(); }, 30), "refresh project");
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      require(area && area->set_tab_type(0, app::kEditorAnalysisGraph), "analysis editor");
      require(area->editor().load_state({{"saved", true}}), "saved mode");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 385 : 560);
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error); };
      auto widget = [&](const std::string &key) { return screen.ui()->find(key); };
      auto click = [&](const std::string &key) {
        const auto *value = widget(key);
        require(value && value->enabled && bool(value->on_click), "button unavailable: " + key);
        value->on_click(); frame();
      };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { frame(); return predicate(); }, 45), description);
      };
      auto choose = [&](const std::string &key, const std::string &prefix) {
        const auto *dropdown = widget(key);
        require(dropdown && dropdown->enabled, "dropdown unavailable: " + key);
        const auto found = std::find_if(dropdown->items.begin(), dropdown->items.end(),
            [&](const std::string &item) { return item.rfind(prefix, 0) == 0; });
        require(found != dropdown->items.end(), "no entry " + prefix + " in " + key);
        dropdown->index.assign(int(found - dropdown->items.begin())); frame();
      };
      auto collapse = [&](const std::string &key) {
        const auto *panel = widget(key);
        require(panel != nullptr, "panel " + key);
        const ui::Vec2 center{panel->rect.x + 8, panel->rect.cy()};
        screen.ui()->handle_event(ui::Event::mouse_down(center));
        screen.ui()->handle_event(ui::Event::mouse_up(center)); frame();
      };
      frame(); click("analysis_list");
      wait([&] { return widget("analysis_documents") != nullptr; }, "analysis list");
      widget("analysis_documents")->table->selected.assign(0);
      wait([&] {
        const auto *ports = widget("graph_ports");
        return widget("analysis_parameters") && widget("graph_node_select") && ports && ports->table &&
            ports->table->rows > 0 && ports->table->cell(0, 2) != "?";
      }, "saved definition, draft and node catalog");
      // Bring the links panel into view; the parameter and output editors stay intact.
      collapse("analysis_parameter_values_panel");
      collapse("analysis_output_panel");
      collapse("analysis_links_panel");  // starts collapsed: this opens it
      require(widget("analysis_links_validate") != nullptr, "links panel open");
      choose("graph_node_select", "box / ");
      choose("analysis_link/box/in/analysis_link_source", "component.out");
      require(!widget("analysis_parameters_save")->enabled, "a link change needs validation before saving");
      click("analysis_links_validate");
      wait([&] { return widget("analysis_links_validate") && widget("analysis_links_validate")->enabled &&
          widget("analysis_parameters_save") && widget("analysis_parameters_save")->enabled; }, "candidate validation");
      const auto before = call("project.analyses.get", {{"handle", handle}, {"analysis_id", analysis_id}});
      require(before.at("revision") == revision, "local link edit must not persist");
      frame(); require(gfx::png_write(output, image), "write screenshot");
      click("analysis_parameters_save");
      wait([&] { return project.project()->revision == revision + 1 && !project.busy() &&
          widget("analysis_parameters_save") && !widget("analysis_parameters_save")->enabled; }, "save receipt");
      auto expected = document;
      for (auto &node : expected["graph"]["nodes"]) { if (node.at("id") == "box") { node["inputs"]["in"] = {{"from", "component.out"}}; } }
      const auto after = call("project.analyses.get", {{"handle", handle}, {"analysis_id", analysis_id}});
      require(after.at("analysis").at("name") == name &&
          io::python_json_dumps(after.at("analysis").at("document"), true, true) == io::python_json_dumps(expected, true, true),
          "only the replaced link may change");
      require(call("project.analysis_runs.list", {{"handle", handle}}).at("runs").empty(), "editing must not prepare a run");
      require(!viewer.payload() && viewer.evaluations_started() == 0, "editing must not configure or evaluate the Viewer");
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
