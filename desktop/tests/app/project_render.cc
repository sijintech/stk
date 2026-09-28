/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real local project bridge -> shared model -> native editor -> offscreen PNG. */
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/shell.hh"
#include "stk/app/editor_area.hh"
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
  std::string backend_name, lang = "en", output, editor = "project";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string arg = argv[i];
    if (arg == "--gpu-backend") { backend_name = argv[i + 1]; }
    else if (arg == "--lang") { lang = argv[i + 1]; }
    else if (arg == "--export") { output = argv[i + 1]; }
    else if (arg == "--editor") { editor = argv[i + 1]; }
    else { return 2; }
  }
  if (output.empty()) { return 2; }
  bridge::test::TempDir dir{"project-render"};
  bridge::test::ManualLoop loop;
  bridge::ClientOptions bo;
  bo.python.configured = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  bo.state_dir = dir.str() + "/bridge";
  bo.cache_dir = dir.str() + "/cache";
  bo.env["PYTHONPATH"] = STK_REPO_ROOT;
  bo.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
  bo.env["STK_STATE_DIR"] = dir.str() + "/runtime";
  bo.executor = loop.executor();
  bo.strict = bo.validate = true;
  auto client = bridge::Client::create(bo);
  std::string error;
  if (!client->start(&error)) { fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) { return 2; }
  gfx::Runtime runtime;
  auto *system = gfx::create_background_system(error);
  if (!system) { return 1; }
  int rc = 0;
  {
    gfx::GpuOptions go;
    go.backend = backend;
    auto gpu = gfx::Gpu::create(*system, go, error);
    if (!gpu) { fprintf(stderr, "FAIL: %s\n", error.c_str()); gfx::dispose_system(); return 1; }
    gfx::set_ui_scale(1);
    app::ShellOptions so;
    so.language = lang == "zh" ? "zh_CN" : "en";
    so.interactive = false;
    app::AppShell shell(so);
    wm::Screen screen;
    shell.install(screen, nullptr);
    shell.build_default_layout(screen);
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &state = shell.store().project();
    state.sync();
    bool ok = loop.pump_until([&] { return state.ready(); }, 60);
    ok = ok && state.create(dir.str() + "/project", "Temperature scan / 温度扫描");
    ok = ok && loop.pump_until([&] { return !state.busy(); }, 30) && state.loaded();
    const std::string table = "11111111-1111-4111-8111-111111111111";
    const std::string temperature = "22222222-2222-4222-8222-222222222222";
    const std::string label = "33333333-3333-4333-8333-333333333333";
    const std::string derived = "55555555-5555-4555-8555-555555555555";
    io::Json commands = io::Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Cases / 参数表"}},
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"id", label}, {"table_id", table}, {"name", "Notes / 记录"}, {"type", "text"}},
      {{"op", "add_field"}, {"id", derived}, {"table_id", table}, {"name", "Derived / 派生值"}, {"type", "number"}, {"unit", "K"}}
    });
    for (int i = 0; i < 5; ++i) {
      const std::string id = std::to_string(40000000 + i) + "-4444-4444-8444-444444444444";
      commands.push_back({{"op", "add_record"}, {"id", id}, {"table_id", table}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", temperature}, {"value", 300 + i * 25}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", label}, {"value", "Prepared / 待运行"}});
      commands.push_back({{"op", "set_expression"}, {"table_id", table}, {"record_id", id}, {"field_id", derived},
                          {"expression", i == 4 ? "base / 0" : "base + quantity(10, \"K\")"},
                          {"bindings", {{"base", {{"record_id", id}, {"field_id", temperature}}}}}});
    }
    ok = ok && state.apply(commands) && loop.pump_until([&] { return !state.busy(); }, 30);
    ok = ok && state.loaded() && state.project()->revision == 1;
    if (ok) {
      auto *area = dynamic_cast<app::EditorArea *>(screen.find_area("a2"));
      area->set_tab_type(0, editor == "python" ? app::kEditorPython : app::kEditorProject);
      if (editor == "python") {
        auto &scripts = shell.store().scripts();
        const std::string source =
            "project = stk.project.snapshot()\n"
            "temperatures = [300, 325, 350, 375, 400]\n"
            "for value in temperatures:\n"
            "    print(f'{value} K -> {value - 273.15:.2f} C')\n"
            "print('Project / 项目:', project['project']['name'])\n"
            "print('Editors:', len(stk.ui.editors()))";
        area->editor().load_state({{"source", source}});
        ok = loop.pump_until([&] { return scripts.ready() && scripts.desktop_ready() && !scripts.busy(); }, 30);
        ok = ok && scripts.execute(source) && loop.pump_until([&] {
          screen.run_deferred();
          return !scripts.busy();
        }, 30);
        ok = ok && scripts.status().at("run").at("state") == "succeeded";
      }
      if (editor == "offline") {
        auto &scripts = shell.store().scripts();
        ok = loop.pump_until([&] { return scripts.ready() && scripts.desktop_ready() && !scripts.busy(); }, 30);
        const std::string source = "from examples.project_scan.offline import create_demo\n"
            "offline_demo = create_demo(stk, " + io::Json(dir.str() + "/offline").dump() + ")";
        ok = ok && scripts.execute(source) && loop.pump_until([&] {
          screen.run_deferred();
          return !scripts.busy();
        }, 60);
        ok = ok && scripts.status().at("run").at("state") == "succeeded" && bool(shell.store().viewer().payload());
        if (!ok) {
          for (size_t line = 0; line < scripts.output().line_count(); ++line) {
            fprintf(stderr, "%s\n", std::string(scripts.output().line(line)).c_str());
          }
        }
      }
      if (editor == "files" || editor == "snapshots") {
        const std::string path = dir.str() + "/project/Notes 中文.md";
        { std::ofstream file(core::path_from_utf8(path)); file << "# Simulation notes\n"; }
        ok = ok && state.index_files({path, dir.str() + "/project/results/temperature.vti"}) &&
             loop.pump_until([&] { return !state.busy(); }, 30) && state.selected_file();
        if (editor == "snapshots") {
          state.select_record(state.table()->records.front().id);
          ok = ok && state.capture_file() && loop.pump_until([&] { return !state.busy(); }, 30);
          if (!state.input_snapshots().empty()) {
            ok = ok && state.verify_input_snapshot(io::get_string(state.input_snapshots().front(), "id")) &&
                 loop.pump_until([&] { return !state.busy(); }, 30);
          }
          else { ok = false; }
        }
      }
      if (editor == "runs") {
        std::optional<bridge::Result<io::Json>> result;
        client->call("connections.add_runtime", {{"name", "demo"}, {"url", "http://127.0.0.1:1"},
          {"token", "render-test-only"}, {"check", false}}).then([&](auto r) { result = r; });
        ok = ok && loop.pump_until([&] { return result.has_value(); }, 30) && result->ok();
        io::Json entries = io::Json::array();
        for (int i = 0; i < 4; ++i) {
          entries.push_back({{"table_id", table}, {"record_id", std::to_string(40000000 + i) + "-4444-4444-8444-444444444444"},
            {"label", std::to_string(300 + i * 25) + " K"}, {"spec", {{"workspace_id", std::string(32, 'a')},
              {"argv", io::Json::array({"solver", "--temperature", std::to_string(300 + i * 25)})}}}});
        }
        result.reset();
        client->call("project.runs.prepare", {{"handle", state.project()->handle}, {"connection", "runtime:demo"},
          {"expected_revision", state.project()->revision}, {"entries", entries}}).then([&](auto r) { result = r; });
        ok = ok && loop.pump_until([&] { return result.has_value() && !state.busy(); }, 30) && result->ok();
        ok = ok && state.load_runs() && loop.pump_until([&] { return !state.busy(); }, 30);
        ok = ok && state.runs().size() == 4 && !state.run().empty();
      }
      if (editor == "csv") {
        const auto source = dir.str() + "/project/parameters.csv";
        { std::ofstream file(core::path_from_utf8(source)); file << "Temperature,Note\n300,Prepared / 待运行\n350,Comparison / 对比\n"; }
        ok = ok && state.import_csv(source, "Imported parameters / 导入参数", {{"Temperature", "number"}},
                                   {{"Temperature", "K"}}, ",") && loop.pump_until([&] { return !state.busy(); }, 30);
      }
      if (editor == "recent") {
        ok = ok && state.close() && loop.pump_until([&] { return !state.busy() && !state.recent_loading(); }, 30);
        ok = ok && state.create(dir.str() + "/comparison", "Comparison / 对比分析") &&
             loop.pump_until([&] { return !state.busy() && !state.recent_loading(); }, 30);
        ok = ok && state.close() && loop.pump_until([&] { return !state.busy(); }, 30);
      }
      if (editor != "offline") { screen.set_maximized(area); }
      wm::DrawContext ctx;
      ctx.ui_scale = 1;
      ctx.fonts = &gpu->fonts();
      ctx.rect = {0, 0, 1280, 900};
      ctx.now = 100;
      gfx::Image image;
      if (editor == "recent") {
        ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
        ok = ok && loop.pump_until([&] { return !state.recent_loading(); }, 30);
        if (const auto *widget = screen.ui()->find("a2/main/project_recent/projects"); widget && widget->table) {
          widget->table->selected.assign(0);
        }
        else { ok = false; }
      }
      if (editor == "expression") {
        ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/cell_field")) {
          widget->index.assign(2);
        }
        else { ok = false; }
      }
      if (editor == "manage" || editor == "files" || editor == "snapshots" || editor == "runs" || editor == "csv") {
        ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find(editor == "manage" ? "a2/main/manage_objects" :
                                                  editor == "files" ? "a2/main/project_files" : editor == "csv" ? "a2/main/project_csv" : editor == "runs" ? "a2/main/project_runs" : "a2/main/input_snapshots")) {
          const ui::Vec2 center{widget->rect.x + widget->rect.w / 2, widget->rect.y + widget->rect.h / 2};
          screen.ui()->handle_event(ui::Event::mouse_down(center));
          screen.ui()->handle_event(ui::Event::mouse_up(center));
        }
        else { ok = false; }
      }
      if (editor == "csv") {
        ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
        if (const auto *widget = screen.ui()->find("a2/main/project_csv/source")) {
          widget->string.assign(dir.str() + "/project/parameters.csv");
          screen.ui()->find("a2/main/project_csv/name")->string.assign("Imported parameters / 导入参数");
          screen.ui()->find("a2/main/project_csv/destination")->string.assign(dir.str() + "/project/results.csv");
        }
        else { ok = false; }
      }
      if (editor == "runs") {
        // Drawing services queued model notifications; wait for resulting list/detail reads
        // before capturing enabled controls rather than the transient loading frame.
        for (int i = 0; i < 3; ++i) {
          ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
          ok = ok && loop.pump_until([&] { return !state.busy(); }, 30);
        }
      }
      if (editor == "offline") {
        // A new editor attaches during its first UI draw; subsequent frames draw its GPU region.
        for (int frame = 0; frame < 2; ++frame) {
          ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
        }
      }
      ok = ok && gfx::render_offscreen(1280, 900, [&] { screen.draw(ctx); }, image, error);
      ok = ok && gfx::png_write(output, image);
    }
    if (!ok) { fprintf(stderr, "FAIL: %s %s\n%s", state.error().c_str(), error.c_str(), client->bridge_log().text().c_str()); rc = 1; }
    else { printf("wrote %s\n", output.c_str()); }
    state.attach(nullptr);
    shell.store().set_bridge(nullptr);
    client->close();
    loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
