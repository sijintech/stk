/* SPDX-License-Identifier: GPL-2.0-or-later */
/* UI-only pixel oracle: caption interiors must be independent of the scene background. */
#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/ui/gpu_painter.hh"
#include "stk/ui/ui.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>

namespace {
using namespace stk;

int delta(const uint8_t *a, const uint8_t *b)
{
  return std::max({std::abs(int(a[0]) - b[0]), std::abs(int(a[1]) - b[1]), std::abs(int(a[2]) - b[2])});
}

int delta(const uint8_t *a, const ui::Color b)
{
  const uint8_t rgb[]{b.r, b.g, b.b};
  return delta(a, rgb);
}

bool check(gfx::Gpu &device, bool light, float scale, std::string &error)
{
  const int width = int(320 * scale), height = int(150 * scale);
  gfx::set_ui_scale(scale);
  ui::gpu::BlfTextMeasurer measurer(device.fonts());
  ui::ContextConfig config;
  config.measurer = &measurer;
  if (light) {
    config.theme.tooltip.inner = {235, 239, 245, 24};
    config.theme.tooltip.text = {21, 29, 36, 33};
    config.theme.space_text = {255, 0, 0, 255};
  }
  ui::Context context(config);
  context.set_scale(scale);
  context.begin_frame({float(width), float(height)}, 1);
  auto &block = context.block("captions", {16 * scale, 16 * scale, 288 * scale, 110 * scale});
  block.set_background({0, 0, 0, 0});
  auto &layout = block.layout();
  const auto &source = layout.label("Source: signed.dat").backdrop();
  const auto &disabled = layout.label("范围 −66 至 22 K").backdrop().disable();
  const auto &plain = layout.label("Ordinary label stays transparent");
  context.end_frame();
  ui::gpu::GpuPainter painter(device.fonts());
  painter.set_pixel_size(context.style().pixel);
  const std::array<ui::Color, 3> backgrounds{{{255, 255, 255, 255}, {0, 0, 0, 255}, {250, 0, 180, 255}}};
  std::array<gfx::Image, 3> images;
  for (size_t i = 0; i < backgrounds.size(); i++) {
    ui::DrawList draw;
    draw.rect({0, 0, float(width), float(height)}, backgrounds[i]);
    draw.cmds.insert(draw.cmds.end(), context.draw_list().cmds.begin(), context.draw_list().cmds.end());
    if (!gfx::render_offscreen(width, height, [&] { painter.paint(draw, {float(width), float(height)}); },
                               images[i], error)) { return false; }
    /* Untouched margins of ordinary labels still expose the original scene. */
    if (delta(images[i].px(int(plain.rect.x + 2 * scale), int(plain.rect.cy())), backgrounds[i]) > 2) {
      error = "ordinary labels acquired a background"; return false;
    }
    for (const auto *caption : {&source, &disabled}) {
      if (delta(images[i].px(int(caption->rect.x + 2 * scale), int(caption->rect.cy())),
                config.theme.tooltip.inner) > 2) {
        error = "caption background is not the opaque theme fill"; return false;
      }
    }
  }
  for (const auto *caption : {&source, &disabled}) {
    /* Exclude antialiased rounded edges; include glyphs, spaces and the disabled text. */
    const ui::Rect interior = caption->rect.inset(6 * scale, 2 * scale);
    size_t ink = 0;
    int maximum_ink_delta = 0;
    for (int y = int(std::ceil(interior.y)); y < int(std::floor(interior.y1())); y++) {
      for (int x = int(std::ceil(interior.x)); x < int(std::floor(interior.x1())); x++) {
        const auto *pixel = images[0].px(x, y);
        for (size_t i = 1; i < images.size(); i++) {
          if (delta(pixel, images[i].px(x, y)) > 2) {
            error = "caption interior depends on the underlying scene"; return false;
          }
        }
        const int difference = delta(pixel, config.theme.tooltip.inner);
        maximum_ink_delta = std::max(maximum_ink_delta, difference);
        ink += difference > 20;
      }
    }
    if (ink < size_t(35 * scale * scale) || maximum_ink_delta < (caption->enabled ? 120 : 60)) {
      error = "caption glyphs are absent or do not contrast with the theme fill"; return false;
    }
  }
  return true;
}

}  // namespace

int main(int argc, char **argv)
{
  using namespace stk;
  std::string backend_name, error;
  if (argc == 3 && std::string(argv[1]) == "--gpu-backend") { backend_name = argv[2]; }
  else { return 2; }
  gfx::Runtime runtime;
  gfx::Backend backend;
  if (!gfx::resolve_backend(backend_name, backend, error)) {
    std::fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1;
  }
  auto *system = gfx::create_background_system(error);
  if (!system) { std::fprintf(stderr, "FAIL: %s\n", error.c_str()); return 1; }
  int result = 0;
  {
    gfx::GpuOptions options; options.backend = backend;
    auto device = gfx::Gpu::create(*system, options, error);
    if (!device) { std::fprintf(stderr, "FAIL: %s\n", error.c_str()); result = 1; }
    else {
      for (const bool light : {false, true}) {
        for (const float scale : {1.0f, 2.0f}) {
          if (!check(*device, light, scale, error)) {
            std::fprintf(stderr, "FAIL: theme=%s scale=%.1f: %s\n", light ? "light" : "dark", scale, error.c_str());
            result = 1;
          }
        }
      }
    }
  }
  gfx::dispose_system();
  if (result == 0) { std::puts("Label backdrops passed over white, black and saturated scenes"); }
  return result;
}
