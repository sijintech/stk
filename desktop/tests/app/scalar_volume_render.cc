/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Real signed field -> Python graph -> native decoded payload -> Viewer + parameter form. */
#include "stk/app/bridge_status.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "scalar_volume_support.hh"

#include <algorithm>
#include <cstdio>

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
  const int width = narrow ? 760 : 1440, height = 1100;
  bridge::test::TempDir directory{"scalar-render"};
  bridge::test::ManualLoop loop;
  if (!apptest::write_signed_field(directory.path() / "signed.dat", 12, 12, 12)) { return 1; }
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
    fprintf(stderr, "FAIL: %s\n%s", error.c_str(), client->bridge_log().text().c_str()); return 1;
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
    wm::Screen screen; shell.install(screen, nullptr);
    wm::LayoutFile layout;
    layout.language = shell_options.language;
    layout.screen = nlohmann::json::parse(R"JSON({"maximized":null,"root":{"factor":1,"split":"horizontal","children":[
      {"factor":0.67,"area":{"id":"scalar-view","type":"viewer"}},
      {"factor":0.33,"area":{"id":"scalar-properties","type":"properties"}}
    ]}})JSON");
    if (narrow) {
      layout.screen["root"]["children"][0]["factor"] = 0.52;
      layout.screen["root"]["children"][1]["factor"] = 0.48;
    }
    bool ok = shell.apply_layout(screen, layout, &error);
    auto *view_area = dynamic_cast<app::EditorArea *>(screen.find_area("scalar-view"));
    if (view_area) { view_area->set_sidebar_open(false); view_area->set_toolbar_open(false); }
    else { ok = false; }
    shell.store().set_bridge(client.get());
    app::BridgeStatus bridge_status(shell.store(), *client, nullptr);
    auto &viewer = shell.store().viewer();
    viewer.prefetch_neighbours = false; viewer.set_auto_evaluate(false);
    ok = ok && loop.pump_until([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60);
    ok = ok && viewer.open_path(core::path_to_utf8(directory.path() / "signed.dat"), "scalar-volume",
        {{"field", "signed"}, {"component", 1}, {"unit", "K"}, {"colormap", "coolwarm"},
         {"opacity", io::Json::array({io::Json::array({0.0, 0.12}), io::Json::array({1.0, 0.45})})}}) &&
        loop.pump_until([&] { viewer.pump(); return !viewer.evaluating() && (viewer.payload() || !viewer.eval_error().empty()); }, 60);
    ok = ok && viewer.payload() && viewer.eval_error().empty() &&
        viewer.graph_inspection()->shown_graph_verified.value_or(false);
    const int evaluations = viewer.evaluations_started();
    if (ok) {
      const auto *volume = viewer.payload()->layer("volume"), *bar = viewer.payload()->layer("bar");
      ok = volume && bar && volume->at("value_range") == io::Json::array({-66.0, 22.0}) &&
          volume->at("transfer_function").at("range") == io::Json::array({-66.0, 22.0}) &&
          bar->at("range") == io::Json::array({-66.0, 22.0}) && bar->at("unit") == "K";
      if (volume) {
        const auto values = viewer.payload()->view<float>(volume->at("data").get<std::string>());
        ok = ok && values.size() == 1728 && values.front() == 11.0f && values.back() == -55.0f;
      }
    }
    wm::DrawContext context;
    context.ui_scale = 1; context.fonts = &gpu->fonts(); context.rect = {0, 0, width, height}; context.now = 100;
    gfx::Image image, hidden;
    auto frame = [&](gfx::Image &target) { return gfx::render_offscreen(width, height, [&] { screen.draw(context); }, target, error); };
    // Viewer GPU attachment occurs on the first draw; the next frame has the actual volume.
    ok = ok && frame(image) && frame(image);
    if (ok) {
      for (const char *key : {"field", "component", "unit", "colormap", "evaluate"}) {
        const auto *widget = screen.ui()->find(key);
        ok = ok && widget && !widget->rect.intersect(widget->clip).empty();
      }
      const auto *field = screen.ui()->find("field"), *component = screen.ui()->find("component"), *unit = screen.ui()->find("unit");
      ok = ok && field && field->string.value() == "signed" && component && component->number.value() == 1 &&
          unit && unit->string.value() == "K";
      // Require the volume itself to affect pixels; an outline and labels alone are insufficient.
      viewer.set_layer_visible("volume", false);
      ok = ok && frame(hidden) && frame(hidden);
      size_t changed = 0;
      const int view_width = view_area->rect().width();
      for (int y = 60; y < height - 60; ++y) {
        for (int x = 0; x < view_width; ++x) {
          const size_t index = size_t(y * width + x) * 4;
          int delta = 0;
          for (int channel = 0; channel < 3; ++channel) {
            delta = std::max(delta, std::abs(int(image.rgba[index + channel]) - int(hidden.rgba[index + channel])));
          }
          changed += delta > 12;
        }
      }
      ok = ok && changed > size_t(view_width * (height - 120) / 100);
      viewer.set_layer_visible("volume", true);
      ok = ok && frame(image) && frame(image) && viewer.evaluations_started() == evaluations &&
          client->stats().schema_violations == 0 && gfx::png_write(output, image);
    }
    if (!ok) { fprintf(stderr, "FAIL: %s\n%s\n%s", error.c_str(), viewer.eval_error().c_str(), client->bridge_log().text().c_str()); rc = 1; }
    else { printf("wrote %s\n", output.c_str()); }
    viewer.close(); shell.store().set_bridge(nullptr); client->close(); loop.run_ready();
  }
  gfx::dispose_system();
  return rc;
}
