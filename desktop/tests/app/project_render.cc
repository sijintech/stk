/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real local project bridge -> shared model -> native editor -> offscreen PNG. */
#include "stk/app/project_state.hh"
#include "stk/app/bridge_status.hh"
#include "stk/app/shell.hh"
#include "stk/app/editor_area.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "../bridge/support.hh"

#include <cstdio>

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
    io::Json commands = io::Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Cases / 参数表"}},
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"id", label}, {"table_id", table}, {"name", "Notes / 记录"}, {"type", "text"}}
    });
    for (int i = 0; i < 5; ++i) {
      const std::string id = std::to_string(40000000 + i) + "-4444-4444-8444-444444444444";
      commands.push_back({{"op", "add_record"}, {"id", id}, {"table_id", table}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", temperature}, {"value", 300 + i * 25}});
      commands.push_back({{"op", "set_cell"}, {"table_id", table}, {"record_id", id}, {"field_id", label}, {"value", "Prepared / 待运行"}});
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
      screen.set_maximized(area);
      wm::DrawContext ctx;
      ctx.ui_scale = 1;
      ctx.fonts = &gpu->fonts();
      ctx.rect = {0, 0, 1280, 900};
      ctx.now = 100;
      gfx::Image image;
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
