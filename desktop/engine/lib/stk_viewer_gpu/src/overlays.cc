/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Screen-space overlays (spec §6.7) in pixel space with BLF text (CJK through the font stack's
 * fallback). Placement and sizes follow the offscreen reference (suan/render/offscreen.py:
 * _place, overlay_scalar_bar, overlay_legend, overlay_text, the corner renderers), with text widths
 * measured by BLF instead of estimated; the orientation sphere and the axes triad follow
 * web/src/Legend.tsx. Every size is in logical pixels times FrameParams::pixel_scale. */

#include "render.hh"

#include <algorithm>
#include <cmath>
#include <vector>

#include "BLF_api.hh"
#include "GPU_immediate.hh"
#include "GPU_matrix.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"

#include "stk/gfx/fonts.hh"
#include "stk/viewer/colormap.hh"
#include "stk/viewer/format.hh"

namespace stk::viewer_gpu {

using namespace blender;
using viewer::dvec3;

namespace {

struct Anchor {
  double fx, fy;
};

Anchor anchor_fractions(const std::string &anchor)
{
  if (anchor == "top_left") {
    return {0, 1};
  }
  if (anchor == "top") {
    return {0.5, 1};
  }
  if (anchor == "top_right") {
    return {1, 1};
  }
  if (anchor == "left") {
    return {0, 0.5};
  }
  if (anchor == "center") {
    return {0.5, 0.5};
  }
  if (anchor == "right") {
    return {1, 0.5};
  }
  if (anchor == "bottom_left") {
    return {0, 0};
  }
  if (anchor == "bottom") {
    return {0.5, 0};
  }
  if (anchor == "bottom_right") {
    return {1, 0};
  }
  return {0, 1};
}

/** offscreen.py _place: bottom-left position of a `size` box at `anchor` with `offset` inward. */
std::array<double, 2> place(const std::string &anchor, std::array<double, 2> offset, std::array<double, 2> size,
                            std::array<double, 2> window)
{
  const Anchor a = anchor_fractions(anchor);
  const double x = a.fx == 0 ? offset[0] : (a.fx == 1 ? window[0] - size[0] - offset[0] : (window[0] - size[0]) / 2 + offset[0]);
  const double y = a.fy == 0 ? offset[1] : (a.fy == 1 ? window[1] - size[1] - offset[1] : (window[1] - size[1]) / 2 - offset[1]);
  return {x, y};
}

struct Painter {
  const gfx::FontStack &fonts;
  float s; /* pixel scale */
  std::array<float, 4> ink;

  void rect(double x0, double y0, double x1, double y1, const float c[4]) const
  {
    GPUVertFormat *format = immVertexFormat();
    const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
    immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
    immUniformColor4fv(c);
    immRectf(pos, float(x0), float(y0), float(x1), float(y1));
    immUnbindProgram();
  }

  /** A line as a quad `width` pixels across (flat caps). */
  void line(double x0, double y0, double x1, double y1, double width, const float c[4]) const
  {
    double dx = x1 - x0, dy = y1 - y0;
    const double len = std::hypot(dx, dy);
    if (len <= 0) {
      return;
    }
    dx /= len;
    dy /= len;
    const double nx = -dy * width / 2, ny = dx * width / 2;
    GPUVertFormat *format = immVertexFormat();
    const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
    immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
    immUniformColor4fv(c);
    immBegin(GPU_PRIM_TRIS, 6);
    immVertex2f(pos, float(x0 - nx), float(y0 - ny));
    immVertex2f(pos, float(x1 - nx), float(y1 - ny));
    immVertex2f(pos, float(x1 + nx), float(y1 + ny));
    immVertex2f(pos, float(x0 - nx), float(y0 - ny));
    immVertex2f(pos, float(x1 + nx), float(y1 + ny));
    immVertex2f(pos, float(x0 + nx), float(y0 + ny));
    immEnd();
    immUnbindProgram();
  }

  void frame(double x0, double y0, double x1, double y1, double width, const float c[4]) const
  {
    line(x0, y0 + width / 2, x1, y0 + width / 2, width, c);
    line(x0, y1 - width / 2, x1, y1 - width / 2, width, c);
    line(x0 + width / 2, y0, x0 + width / 2, y1, width, c);
    line(x1 - width / 2, y0, x1 - width / 2, y1, width, c);
  }

  int font() const
  {
    return fonts.ui;
  }

  double text_width(const std::string &text, double size_px, bool bold = false) const
  {
    const int f = font();
    if (f < 0 || text.empty()) {
      return 0;
    }
    BLF_size(f, float(size_px * s));
    BLF_character_weight(f, bold ? 700 : 400);
    const double w = BLF_width(f, text.data(), text.size());
    BLF_character_weight(f, 400);
    return w / s;
  }

  /** Text at pixel (x, y) (already scaled) with VTK-style justification. */
  void text(const std::string &str, double x, double y, double size_px, const float c[4],
            const char *halign = "left", const char *valign = "bottom", bool bold = false) const
  {
    const int f = font();
    if (f < 0 || str.empty()) {
      return;
    }
    BLF_size(f, float(size_px * s));
    BLF_character_weight(f, bold ? 700 : 400);
    const double w = BLF_width(f, str.data(), str.size());
    const double asc = BLF_ascender(f), desc = BLF_descender(f); /* desc <= 0 */
    double bx = x;
    if (std::string_view(halign) == "center") {
      bx = x - w / 2;
    }
    else if (std::string_view(halign) == "right") {
      bx = x - w;
    }
    double by = y - desc; /* bottom */
    if (std::string_view(valign) == "center") {
      by = y - (asc + desc) / 2;
    }
    else if (std::string_view(valign) == "top") {
      by = y - asc;
    }
    BLF_color4f(f, c[0], c[1], c[2], c[3]);
    BLF_position(f, float(std::round(bx)), float(std::round(by)), 0.0f);
    BLF_draw(f, str.data(), str.size());
    BLF_character_weight(f, 400);
  }

  void image(gpu::Texture *tex, double x0, double y0, double x1, double y1) const
  {
    GPUVertFormat *format = immVertexFormat();
    const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
    const uint uv = GPU_vertformat_attr_add(format, "texCoord", gpu::VertAttrType::SFLOAT_32_32);
    immBindBuiltinProgram(GPU_SHADER_3D_IMAGE_COLOR);
    immUniformColor4f(1, 1, 1, 1);
    immBindTexture("image", tex);
    immBegin(GPU_PRIM_TRI_FAN, 4);
    immAttr2f(uv, 0, 0);
    immVertex2f(pos, float(x0), float(y0));
    immAttr2f(uv, 1, 0);
    immVertex2f(pos, float(x1), float(y0));
    immAttr2f(uv, 1, 1);
    immVertex2f(pos, float(x1), float(y1));
    immAttr2f(uv, 0, 1);
    immVertex2f(pos, float(x0), float(y1));
    immEnd();
    immUnbindProgram();
  }
};

void rgba_f(const viewer::RGBA8 &c, float out[4])
{
  for (int k = 0; k < 4; k++) {
    out[k] = c[size_t(k)] / 255.0f;
  }
}

/* -------------------------------------------------------------------- */

void scalar_bar(const Painter &P, const OverlayItem &o, std::array<double, 2> window)
{
  if (!o.lut) {
    return;
  }
  const double font = 12.0;
  const double lo = o.range[0], hi = o.range[1];
  const std::vector<viewer::ScalarBarTick> ticks = viewer::scalar_bar_ticks(lo, hi, o.label_count, o.format);
  double thick = 28, length = 320;
  if (o.has_size) {
    thick = std::min(o.size[0], o.size[1]);
    length = std::max(o.size[0], o.size[1]);
  }
  length = std::min(length, 0.7 * (o.vertical ? window[1] : window[0]));
  const double bar_w = o.vertical ? thick : length, bar_h = o.vertical ? length : thick;
  std::string title = o.title;
  if (!o.unit.empty() && o.unit != "1" && !title.empty() && title.find("[" + o.unit + "]") == std::string::npos) {
    title += " [" + o.unit + "]";
  }
  double label_w = 0;
  for (const auto &t : ticks) {
    label_w = std::max(label_w, P.text_width(t.label, font));
  }
  label_w += 6;
  const double title_w = title.empty() ? 0 : P.text_width(title, font, true);
  const double title_h = title.empty() ? 0 : font * 1.7;
  std::array<double, 2> box;
  if (o.vertical) {
    box = {std::max(bar_w + label_w, title_w), bar_h + title_h + font / 2};
  }
  else {
    box = {std::max(bar_w + label_w, title_w), bar_h + font * 1.6 + title_h};
  }
  const std::array<double, 2> offset = o.has_offset ? o.offset : std::array<double, 2>{24, 24};
  const auto [x, y] = place(o.anchor, offset, box, window);
  const double fx = anchor_fractions(o.anchor).fx;
  const double bar_x = fx == 1 ? x + box[0] - bar_w - (o.vertical ? label_w : 0) : x;
  const double bar_y = o.vertical ? y + font / 2 : y + font * 1.6;
  const double s = P.s;
  const double X = bar_x * s, Y = bar_y * s, bw = bar_w * s, bh = bar_h * s;
  /* One quad per LUT entry, so each bin is drawn exactly. */
  for (int i = 0; i < 256; i++) {
    float c[4];
    rgba_f(o.lut->lut[size_t(i)], c);
    if (o.vertical) {
      P.rect(X, Y + i / 256.0 * bh, X + bw, Y + (i + 1) / 256.0 * bh, c);
    }
    else {
      P.rect(X + i / 256.0 * bw, Y, X + (i + 1) / 256.0 * bw, Y + bh, c);
    }
  }
  P.frame(X, Y, X + bw, Y + bh, std::max(1.0, 1.0 * s), P.ink.data());
  for (const auto &t : ticks) {
    if (o.vertical) {
      P.text(t.label, X + bw + 4 * s, Y + t.fraction * bh, font, P.ink.data(), "left", "center");
    }
    else {
      P.text(t.label, X + t.fraction * bw, Y - 2 * s, font, P.ink.data(), "center", "top");
    }
  }
  if (!title.empty()) {
    const char *halign = fx == 0 ? "left" : (fx == 1 ? "right" : "center");
    const double tx = fx == 0 ? x * s : (fx == 1 ? (x + box[0]) * s : (x + box[0] / 2) * s);
    P.text(title, tx, Y + bh + 6 * s, font, P.ink.data(), halign, "bottom", true);
  }
}

void legend(const Painter &P, const OverlayItem &o, std::array<double, 2> window)
{
  const double font = 12.0;
  const int columns = std::max(1, o.columns);
  const size_t rows = o.legend.size();
  const size_t per_column = rows ? (rows + size_t(columns) - 1) / size_t(columns) : 0;
  const double row_h = font * 1.5;
  double name_w = 0;
  for (const auto &item : o.legend) {
    name_w = std::max(name_w, P.text_width(item.name, font));
  }
  if (rows == 0) {
    name_w = 4 * font * 0.62;
  }
  const double col_w = font * 1.4 + name_w + font;
  const double title_h = o.title.empty() ? 0 : font * 1.7;
  const double title_w = o.title.empty() ? 0 : P.text_width(o.title, font, true);
  const std::array<double, 2> box = {std::max(columns * col_w, title_w), double(per_column) * row_h + title_h};
  const std::array<double, 2> offset = o.has_offset ? o.offset : std::array<double, 2>{16, 16};
  auto [x, y] = place(o.anchor, offset, box, window);
  const double fx = anchor_fractions(o.anchor).fx;
  const double title_x = fx == 1 ? x + box[0] : x;
  if (fx == 1) {
    x += box[0] - columns * col_w;
  }
  const double s = P.s;
  const double top = y + double(per_column) * row_h;
  for (size_t index = 0; index < rows; index++) {
    const size_t column = index / per_column, line = index % per_column;
    const double cx = x + double(column) * col_w;
    const double cy = top - double(line + 1) * row_h;
    const double swatch = cy + 0.15 * row_h;
    float c[4];
    rgba_f(o.legend[index].color, c);
    P.rect(cx * s, swatch * s, (cx + font) * s, (swatch + font) * s, c);
    P.text(o.legend[index].name, (cx + font * 1.4) * s, (swatch + font / 2) * s, font, P.ink.data(), "left", "center");
  }
  if (!o.title.empty()) {
    P.text(o.title, title_x * s, (top + font * 0.4) * s, font, P.ink.data(), fx == 1 ? "right" : "left", "bottom",
           true);
  }
}

void text_overlay(const Painter &P, const OverlayItem &o, std::array<double, 2> window)
{
  const Anchor a = anchor_fractions(o.anchor);
  const std::array<double, 2> off = o.has_offset ? o.offset : std::array<double, 2>{12, 12};
  const double x = a.fx == 0 ? off[0] : (a.fx == 1 ? window[0] - off[0] : window[0] / 2 + off[0]);
  const double y = a.fy == 0 ? off[1] : (a.fy == 1 ? window[1] - off[1] : window[1] / 2 - off[1]);
  const char *halign = a.fx == 0 ? "left" : (a.fx == 1 ? "right" : "center");
  const char *valign = a.fy == 0 ? "bottom" : (a.fy == 1 ? "top" : "center");
  float c[4] = {P.ink[0], P.ink[1], P.ink[2], 1.0f};
  if (o.color) {
    c[0] = (*o.color)[0];
    c[1] = (*o.color)[1];
    c[2] = (*o.color)[2];
  }
  P.text(o.text, x * P.s, y * P.s, o.font_size, c, halign, valign);
}

/** offscreen.py corner_renderer: a square corner box of size_px (limited to 35% of the window). */
std::array<double, 4> corner_box(const OverlayItem &o, double default_size, std::array<double, 2> window)
{
  const double limit = 0.35 * std::min(window[0], window[1]);
  const double w = std::min(o.has_size ? o.size[0] : default_size, limit);
  const double h = std::min(o.has_size ? o.size[1] : default_size, limit);
  const std::array<double, 2> offset = o.has_offset ? o.offset : std::array<double, 2>{12, 12};
  const auto [x, y] = place(o.anchor, offset, {w, h}, window);
  return {x, y, w, h};
}

void orientation_legend(const Painter &P, const OverlayItem &o, std::array<double, 2> window,
                        const viewer::CameraPose &camera)
{
  const auto [x, y, w, h] = corner_box(o, 120, window);
  const double side = std::min(w, h);
  const int px = std::max(8, int(std::lround(side * P.s)));
  dvec3 right, up, back;
  camera.frame(right, up, back);
  /* web/src/Legend.tsx OrientationLegend: the unit sphere seen by the camera, surface point n
   * coloured orientation-hsl(n, M = 1), shaded 0.8 + 0.2 z. */
  std::vector<uint8_t> rgba(size_t(px) * px * 4, 0);
  const double c = px / 2.0, R = px * 0.4;
  for (int yy = 0; yy < px; yy++) {
    for (int xx = 0; xx < px; xx++) {
      const double sx = (xx + 0.5 - c) / R, sy = (yy + 0.5 - c) / R; /* texture row 0 = bottom */
      const double d2 = sx * sx + sy * sy;
      const double coverage = std::clamp((1 - std::sqrt(d2)) * R + 0.5, 0.0, 1.0);
      if (coverage <= 0) {
        continue;
      }
      const double sz = std::sqrt(std::max(0.0, 1 - d2));
      const dvec3 n = right * sx + up * sy + back * sz;
      const viewer::RGB col = viewer::orientation_hsl(n.x, n.y, n.z, 1.0, o.lightness[0], o.lightness[1]);
      const double shade = 0.8 + 0.2 * sz;
      uint8_t *p = &rgba[(size_t(yy) * px + xx) * 4];
      p[0] = viewer::to_byte(col[0] * shade);
      p[1] = viewer::to_byte(col[1] * shade);
      p[2] = viewer::to_byte(col[2] * shade);
      p[3] = viewer::to_byte(coverage);
    }
  }
  gpu::Texture *tex = GPU_texture_create_2d("stk_viewer_orientation", px, px, 1, gpu::TextureFormat::UNORM_8_8_8_8,
                                            GPU_TEXTURE_USAGE_SHADER_READ, nullptr);
  GPU_texture_update(tex, GPU_DATA_UBYTE, rgba.data());
  const double X = (x + (w - side) / 2) * P.s, Y = (y + (h - side) / 2) * P.s;
  GPU_blend(GPU_BLEND_ALPHA);
  P.image(tex, X, Y, X + px, Y + px);
  GPU_texture_free(tex);
  const double cx = X + px / 2.0, cy = Y + px / 2.0;
  const float grey[4] = {0.5f, 0.5f, 0.5f, 0.95f};
  const char *names[3] = {"x", "y", "z"};
  const dvec3 axes[3] = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
  for (int k = 0; k < 3; k++) {
    if (viewer::dot(axes[k], back) < -0.3) {
      continue;
    }
    P.text(names[k], cx + viewer::dot(axes[k], right) * R * 1.17, cy + viewer::dot(axes[k], up) * R * 1.17, 10,
           grey, "center", "center");
  }
  if (!o.title.empty()) {
    P.text(o.title, (x + w / 2) * P.s, (y + h + 2) * P.s, 12, P.ink.data(), "center", "bottom");
  }
}

void axes_triad(const Painter &P, const OverlayItem &o, std::array<double, 2> window, const viewer::CameraPose &camera)
{
  const auto [x, y, w, h] = corner_box(o, 80, window);
  const double side = std::min(w, h) * P.s;
  const double cx = (x + w / 2) * P.s, cy = (y + h / 2) * P.s;
  const double L = side * 0.32;
  dvec3 right, up, back;
  camera.frame(right, up, back);
  /* offscreen.py overlay_axes_triad colours; far axes first (web AxesTriad). */
  const float colors[3][4] = {{0.85f, 0.1f, 0.1f, 1}, {0.1f, 0.65f, 0.1f, 1}, {0.1f, 0.25f, 0.9f, 1}};
  const dvec3 axes[3] = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
  int order[3] = {0, 1, 2};
  std::sort(order, order + 3, [&](int a, int b) { return viewer::dot(axes[a], back) < viewer::dot(axes[b], back); });
  for (const int i : order) {
    const double ax = viewer::dot(axes[i], right), ay = viewer::dot(axes[i], up);
    P.line(cx, cy, cx + ax * L, cy + ay * L, 2.2 * P.s, colors[i]);
    P.text(o.labels[size_t(i)], cx + ax * L * 1.3, cy + ay * L * 1.3, 12, P.ink.data(), "center", "center", true);
  }
}

}  // namespace

void Renderer::draw_overlays(const GpuScene &scene, const FrameParams &params)
{
  const bool light_background = (scene.background[0] + scene.background[1] + scene.background[2]) / 3 > 0.5f;
  Painter P{fonts_, params.pixel_scale,
            light_background ? std::array<float, 4>{0, 0, 0, 1} : std::array<float, 4>{1, 1, 1, 1}};
  const std::array<double, 2> window = {params.full_width / double(params.pixel_scale),
                                        params.full_height / double(params.pixel_scale)};
  /* Pixel space of the whole image, restricted to the current tile. */
  GPU_matrix_push_projection();
  GPU_matrix_push();
  GPU_matrix_identity_set();
  GPU_matrix_ortho_set(float(params.tile.x), float(params.tile.x + params.tile.width), float(params.tile.y),
                       float(params.tile.y + params.tile.height), -100.0f, 100.0f);
  GPU_blend(GPU_BLEND_ALPHA);
  for (const DrawLayer &layer : scene.layers) {
    if (layer.kind != LayerKind::Overlay || !layer_shown(layer, params)) {
      continue;
    }
    const OverlayItem &o = layer.overlay;
    if (o.kind == "scalar_bar") {
      scalar_bar(P, o, window);
    }
    else if (o.kind == "legend") {
      legend(P, o, window);
    }
    else if (o.kind == "text") {
      text_overlay(P, o, window);
    }
    else if (o.kind == "orientation_legend") {
      orientation_legend(P, o, window, params.camera);
    }
    else if (o.kind == "axes_triad") {
      axes_triad(P, o, window, params.camera);
    }
    GPU_blend(GPU_BLEND_ALPHA);
  }
  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

}  // namespace stk::viewer_gpu
