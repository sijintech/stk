/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Saved analysis -> exact local parameter edit -> explicit CAS save, without evaluation. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <cstdio>
#include <limits>
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
  bridge::test::TempDir directory{"analysis-parameter-render"};
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
      project.sync(); require(project.create(directory.str() + "/project", "Exact analysis parameters"), "create");
      require(loop.pump_until([&] { return project.loaded() && !project.busy(); }, 30), "load project");
      const auto handle = project.project()->handle;
      const std::string analysis_id = "d9c908d5-a99b-44ed-a21f-a088ed1e2227";
      const std::string name = language == "zh" ? "温差分析 · 参数草稿" : "Temperature difference · parameter draft";
      const Json document = {{"format", "stk.analysis-document/1"},
          {"graph", io::read_json_file(std::filesystem::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
          {"parameters", {{"path", "fields/signed.dat"}, {"field", "signed"}, {"component", 0}, {"unit", nullptr},
              {"precision_record", {{"integer", std::numeric_limits<uint64_t>::max()}, {"float", 1.0},
                  {"negative_zero", -0.0}, {"empty", ""}, {"text", "null"}}}}},
          {"outputs", Json::array()}};
      const auto saved = call("project.analyses.create", {{"handle", handle}, {"analysis_id", analysis_id},
          {"name", name}, {"document", document}, {"expected_revision", 0}});
      const int64_t revision = saved.at("revision").get<int64_t>();
      project.refresh(); require(loop.pump_until([&] { return !project.busy(); }, 30), "refresh project");
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      require(area && area->set_tab_type(0, app::kEditorAnalysisGraph), "analysis editor");
      require(area->editor().load_state({{"saved", true}}), "saved mode");
      area->find_region(app::EditorArea::kSidebar)->set_size_1x(narrow ? 385 : 510);
      screen.set_maximized(area);
      wm::DrawContext context;
      context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
      gfx::Image image;
      auto frame = [&] { require(gfx::render_offscreen(width, height, [&] { screen.draw(context); }, image, error), error); };
      auto widget = [&](const char *key) { return screen.ui()->find(key); };
      auto click = [&](const char *key) {
        const auto *value = widget(key);
        require(value && value->enabled && bool(value->on_click), std::string("button unavailable: ") + key);
        value->on_click(); frame();
      };
      auto wait = [&](const std::function<bool()> &predicate, const char *description) {
        require(loop.pump_until([&] { frame(); return predicate(); }, 45), description);
      };
      frame(); click("analysis_list");
      wait([&] { return widget("analysis_documents") != nullptr; }, "analysis list");
      widget("analysis_documents")->table->selected.assign(0);
      wait([&] {
        const auto *ports = widget("graph_ports");
        return widget("analysis_parameters") && ports && ports->table && ports->table->rows > 0;
      }, "saved definition, draft and node descriptions");
      const auto *table = widget("analysis_parameters");
      require(table && table->table, "parameter table");
      int component_row = -1;
      for (int i = 0; i < table->table->rows; ++i) {
        if (table->table->cell(i, 0) == "component") { component_row = i; }
      }
      require(component_row >= 0, "component row");
      table->table->selected.assign(component_row); frame();
      const auto *value = widget("analysis_parameter_value");
      require(value && value->enabled, "exact value input");
      const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
      screen.ui()->handle_event(ui::Event::mouse_down(center));
      screen.ui()->handle_event(ui::Event::mouse_up(center));
#ifdef __APPLE__
      constexpr auto primary = ui::MOD_SUPER;
#else
      constexpr auto primary = ui::MOD_CTRL;
#endif
      screen.ui()->handle_event(ui::Event::key_down(ui::Key::A, primary));
      screen.ui()->handle_event(ui::Event::text_input("2")); frame();
      require(screen.ui()->text_input_active(), "real keyboard input");
      screen.ui()->handle_event(ui::Event::key_down(ui::Key::Enter)); frame();
      click("analysis_parameter_apply");
      require(widget("analysis_parameters_save") && widget("analysis_parameters_save")->enabled, "explicit save available");
      const auto before = call("project.analyses.get", {{"handle", handle}, {"analysis_id", analysis_id}});
      require(before.at("revision") == revision && before.at("analysis").at("document").at("parameters").at("component") == 0,
          "local edit must not persist");
      frame(); require(gfx::png_write(output, image), "write screenshot");
      click("analysis_parameters_save");
      wait([&] { return project.project()->revision == revision + 1 && !project.busy() &&
          widget("analysis_parameters_save") && !widget("analysis_parameters_save")->enabled; }, "save receipt");
      auto expected = document; expected["parameters"]["component"] = 2;
      const auto after = call("project.analyses.get", {{"handle", handle}, {"analysis_id", analysis_id}});
      require(after.at("analysis").at("name") == name &&
          io::python_json_dumps(after.at("analysis").at("document"), true, true) == io::python_json_dumps(expected, true, true),
          "only selected exact override may change; preserve uint64, float, negative zero, null, empty string and outputs");
      require(call("project.analysis_runs.list", {{"handle", handle}}).at("runs").empty(), "editing must not prepare a run");
      require(!viewer.payload() && viewer.evaluations_started() == 0 && viewer.catalog().is_null() && !viewer.presets_loaded(),
          "editing must not configure or evaluate Viewer");
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
