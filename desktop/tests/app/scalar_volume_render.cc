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
#include "stk/viewer/camera.hh"
#include "../bridge/support.hh"
#include "scalar_volume_support.hh"

#include <algorithm>
#include <cstdio>

using namespace stk;

namespace {

// Copy the actual numeric sidebar bindings before collapsing it. They continue to read the
// same editor, allowing the test to inspect its camera without changing the viewport later.
struct CameraControls {
  std::array<ui::Binding<double>, 3> position, focal, up;
  ui::Binding<double> angle, scale;
  ui::Binding<bool> parallel;

  viewer::CameraPose pose() const
  {
    viewer::CameraPose camera;
    for (size_t i = 0; i < 3; ++i) {
      camera.position[i] = position[i].value();
      camera.focal_point[i] = focal[i].value();
      camera.view_up[i] = up[i].value();
    }
    camera.view_angle_deg = angle.value();
    camera.parallel = parallel.value();
    camera.parallel_scale = scale.value();
    return camera;
  }
};

bool encloses_grid(const viewer::CameraPose &camera, const viewer::Viewport &viewport)
{
  for (const double x : {0.0, 11.0}) {
    for (const double y : {0.0, 11.0}) {
      for (const double z : {0.0, 11.0}) {
        const auto projected = viewer::project(camera, viewport, {x, y, z});
        if (!projected || !viewer::is_finite(*projected) || !(projected->z > 0) ||
            projected->x < 0 || projected->x > viewport.width ||
            projected->y < 0 || projected->y > viewport.height) {
          return false;
        }
      }
    }
  }
  return true;
}

bool same_camera(const viewer::CameraPose &a, const viewer::CameraPose &b)
{
  return viewer::numeric_camera_json(a, {}) == viewer::numeric_camera_json(b, {});
}

}  // namespace

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
    int frame_width = width;
    auto frame = [&](gfx::Image &target) {
      context.rect = {0, 0, frame_width, height};
      return gfx::render_offscreen(frame_width, height, [&] { screen.draw(context); }, target, error);
    };
    // Viewer GPU attachment occurs on the first draw; the next frame has the actual volume.
    ok = ok && frame(image) && frame(image);
    CameraControls camera;
    if (ok) {
      view_area->set_sidebar_open(true);
      ok = frame(image);
      const auto *panel = screen.ui()->find("scalar-view/sidebar/camera/numeric");
      if (!panel) { ok = false; }
      else {
        const ui::Vec2 center{panel->rect.x + panel->rect.w / 2, panel->rect.y + panel->rect.h / 2};
        screen.ui()->handle_event(ui::Event::mouse_down(center));
        screen.ui()->handle_event(ui::Event::mouse_up(center));
        ok = ok && frame(image);
      }
      auto number = [&](const std::string &key, ui::Binding<double> &binding) {
        const auto *widget = screen.ui()->find("scalar-view/sidebar/camera/numeric/" + key);
        if (!widget || !widget->number) { ok = false; }
        else { binding = widget->number; }
      };
      for (size_t i = 0; i < 3; ++i) {
        number("position/" + std::to_string(i), camera.position[i]);
        number("focal/" + std::to_string(i), camera.focal[i]);
        number("up/" + std::to_string(i), camera.up[i]);
      }
      number("angle", camera.angle);
      const auto *parallel = screen.ui()->find("scalar-view/sidebar/camera/numeric/parallel");
      if (!parallel || !parallel->boolean || parallel->boolean.value()) { ok = false; }
      else { camera.parallel = parallel->boolean; }
      if (ok) {
        camera.parallel.assign(true);
        ok = frame(image);
        number("parallel_scale", camera.scale);
        camera.parallel.assign(false);
        view_area->set_sidebar_open(false);
        ok = ok && frame(image);
      }
    }
    if (ok) {
      const viewer::CameraPose imported = camera.pose();
      // Ordinary drawing and layout changes retain the imported numeric camera.
      frame_width = width + 600;
      ok = frame(image) && same_camera(imported, camera.pose());
      const auto *fit = screen.ui()->find("view_all");
      if (!fit || !fit->on_click) { ok = false; }
      else {
        const auto action = fit->on_click;
        frame_width = width;
        context.rect = {0, 0, frame_width, height};
        screen.layout(context.rect, context);
        const auto *main = view_area->find_region(app::EditorArea::kMain);
        const viewer::Viewport viewport{double(main->rect().width()), double(main->rect().height())};
        // Fit after layout but before a GPU draw: using the previous drawn width is incorrect.
        action();
        ok = ok && encloses_grid(camera.pose(), viewport) && frame(image);
        const viewer::CameraPose fitted = camera.pose();
        frame_width = width + 200;
        ok = ok && frame(image) && same_camera(fitted, camera.pose());
        frame_width = width;
        ok = ok && frame(image) && same_camera(fitted, camera.pose());
        // A native direction shortcut and Home must also fit the current main region.
        wm::Event key;
        key.type = wm::EventType::KeyDown; key.key = wm::Key::Numpad3;
        auto editor_context = view_area->context(screen.ui(), &context);
        ok = ok && view_area->editor().on_key(key, editor_context) && encloses_grid(camera.pose(), viewport);
        camera.parallel.assign(true);
        key.key = wm::Key::Home;
        ok = ok && view_area->editor().on_key(key, editor_context) && encloses_grid(camera.pose(), viewport);
        camera.parallel.assign(false);
        key.key = wm::Key::Numpad0;
        ok = ok && view_area->editor().on_key(key, editor_context) && encloses_grid(camera.pose(), viewport) && frame(image);
      }
    }
    if (ok) {
      size_t backed_captions = 0;
      for (const auto &block : screen.ui()->blocks()) {
        if (block->name() != "scalar-view/main") { continue; }
        for (const auto &widget : block->widgets()) {
          if (widget.type == ui::WidgetType::Label && !widget.text.empty()) {
            ok = ok && widget.label_backdrop;
            ++backed_captions;
          }
        }
      }
      ok = ok && backed_captions >= 2;
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
