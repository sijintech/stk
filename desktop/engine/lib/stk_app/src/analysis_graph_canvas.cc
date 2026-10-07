/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_canvas.hh"

#include <algorithm>
#include <cmath>

namespace stk::app {
namespace {
using Point = AnalysisGraphPoint;
using Rect = AnalysisGraphRect;
constexpr double max_pan = 1e9, max_viewport = 1e6;

bool viewport(double width, double height, double scale)
{
  return std::isfinite(width) && std::isfinite(height) && width > 0 && height > 0 &&
         width <= max_viewport && height <= max_viewport && std::isfinite(scale) && scale >= .25 && scale <= 8;
}
bool geometry(const Rect &rect)
{
  return std::isfinite(rect.x) && std::isfinite(rect.y) && std::isfinite(rect.width) && std::isfinite(rect.height) &&
         rect.width > 0 && rect.height > 0 && std::abs(rect.x) <= 1e8 && std::abs(rect.y) <= 1e8 &&
         rect.width <= 1e7 && rect.height <= 1e7;
}
bool finite(Point point) { return std::isfinite(point.x) && std::isfinite(point.y); }
bool visible(const Rect &rect, double width, double height, double margin = 0)
{
  return geometry(rect) && rect.x < width + margin && rect.y < height + margin &&
         rect.x + rect.width > -margin && rect.y + rect.height > -margin;
}
ui::Rect pixels(const Rect &rect)
{
  return {float(rect.x), float(rect.y), float(rect.width), float(rect.height)};
}
bool safe_pan(double x, double y)
{
  return std::isfinite(x) && std::isfinite(y) && std::abs(x) <= max_pan && std::abs(y) <= max_pan;
}

ui::Color stage_color(std::string_view stage)
{
  if (stage == "source") { return ui::Color::rgb(0x609AC9); }
  if (stage == "data") { return ui::Color::rgb(0x73AD91); }
  if (stage == "analysis") { return ui::Color::rgb(0xCEA265); }
  if (stage == "representation") { return ui::Color::rgb(0xA189CA); }
  if (stage == "view") { return ui::Color::rgb(0x6FB8BC); }
  return ui::Color::rgb(0xA1A9B4);
}
ui::Color port_color(const AnalysisGraphPort &port)
{
  if (!port.declared) { return ui::Color::rgb(0xDCA765); }
  uint32_t hash = 2166136261u;
  for (const unsigned char c : port.type_text) { hash = (hash ^ c) * 16777619u; }
  constexpr uint32_t colors[] = {0x80B5D8, 0x87C5A1, 0xC6A0DB, 0xD5BC80, 0xD69894, 0x85C3C8};
  return ui::Color::rgb(colors[hash % 6]);
}

/** Clip in double precision before generating triangles or converting coordinates to float. */
void segment(ui::DrawList &draw, Point a, Point b, double width, double height, double thickness, ui::Color color)
{
  if (!finite(a) || !finite(b)) { return; }
  const double dx = b.x - a.x, dy = b.y - a.y;
  double start = 0, end = 1;
  auto boundary = [&](double p, double q) {
    if (p == 0) { return q >= 0; }
    const double ratio = q / p;
    if (p < 0) { if (ratio > end) { return false; } start = std::max(start, ratio); }
    else { if (ratio < start) { return false; } end = std::min(end, ratio); }
    return true;
  };
  if (!boundary(-dx, a.x + thickness) || !boundary(dx, width + thickness - a.x) ||
      !boundary(-dy, a.y + thickness) || !boundary(dy, height + thickness - a.y)) { return; }
  b = {a.x + end * dx, a.y + end * dy};
  a = {a.x + start * dx, a.y + start * dy};
  // Floating-point cancellation at a distant endpoint must not bypass the clip after rounding.
  a.x = std::clamp(a.x, -thickness, width + thickness);
  a.y = std::clamp(a.y, -thickness, height + thickness);
  b.x = std::clamp(b.x, -thickness, width + thickness);
  b.y = std::clamp(b.y, -thickness, height + thickness);
  const double length = std::hypot(b.x - a.x, b.y - a.y);
  if (!std::isfinite(length) || length < .01) { return; }
  const double nx = -(b.y - a.y) * thickness / (2 * length), ny = (b.x - a.x) * thickness / (2 * length);
  const ui::Vec2 p0{float(a.x + nx), float(a.y + ny)}, p1{float(a.x - nx), float(a.y - ny)};
  const ui::Vec2 p2{float(b.x - nx), float(b.y - ny)}, p3{float(b.x + nx), float(b.y + ny)};
  draw.triangle(p0, p1, p2, color);
  draw.triangle(p0, p2, p3, color);
}

void curve(ui::DrawList &draw, Point from, Point to, double width, double height,
           double scale, double thickness, ui::Color color)
{
  if (!finite(from) || !finite(to) || std::abs(from.x) > 1e10 || std::abs(from.y) > 1e10 ||
      std::abs(to.x) > 1e10 || std::abs(to.y) > 1e10) { return; }
  const double reach = std::max(40 * scale, std::abs(to.x - from.x) * .5);
  const Point a{from.x + reach, from.y}, b{to.x - reach, to.y};
  const double left = std::min({from.x, to.x, a.x, b.x}), right = std::max({from.x, to.x, a.x, b.x});
  const double top = std::min(from.y, to.y), bottom = std::max(from.y, to.y);
  if (right < -thickness || left > width + thickness || bottom < -thickness || top > height + thickness) { return; }
  Point previous = from;
  for (int i = 1; i <= 20; ++i) {
    const double t = double(i) / 20, u = 1 - t;
    const Point next{u*u*u*from.x + 3*u*u*t*a.x + 3*u*t*t*b.x + t*t*t*to.x,
                     u*u*u*from.y + 3*u*u*t*a.y + 3*u*t*t*b.y + t*t*t*to.y};
    segment(draw, previous, next, width, height, thickness, color);
    previous = next;
  }
}
}  // namespace

void AnalysisGraphCanvas::set_view(std::shared_ptr<const AnalysisGraphView> view, const bool keep_transform)
{
  if (view_ == view) { return; }
  view_ = std::move(view);
  if (keep_transform) { return; }
  zoom_ = 1;
  pan_x_ = pan_y_ = 0;
  width_ = height_ = 0;
}

bool AnalysisGraphCanvas::fit(double width, double height, double ui_scale)
{
  if (!view_ || view_->nodes.empty() || !viewport(width, height, ui_scale) || !geometry(view_->bounds)) { return false; }
  const double padding = std::min({32 * ui_scale, width / 4, height / 4});
  const double zoom = std::clamp(std::min((width - 2 * padding) / view_->bounds.width,
                                        (height - 2 * padding) / view_->bounds.height) / ui_scale, min_zoom, max_zoom);
  const double scale = zoom * ui_scale;
  const double x = width / 2 - (view_->bounds.x + view_->bounds.width / 2) * scale;
  const double y = height / 2 - (view_->bounds.y + view_->bounds.height / 2) * scale;
  if (!safe_pan(x, y)) { return false; }
  zoom_ = zoom; pan_x_ = x; pan_y_ = y; ui_scale_ = ui_scale;
  width_ = width; height_ = height;
  return true;
}

bool AnalysisGraphCanvas::pan(double dx, double dy)
{
  if (!std::isfinite(dx) || !std::isfinite(dy) || !safe_pan(pan_x_ + dx, pan_y_ + dy)) { return false; }
  pan_x_ += dx; pan_y_ += dy;
  return true;
}

bool AnalysisGraphCanvas::zoom_at(double factor, double x, double y)
{
  if (!std::isfinite(factor) || factor <= 0 || !safe_pan(x, y)) { return false; }
  const auto anchor = to_graph({x, y});
  const double zoom = std::clamp(zoom_ * factor, min_zoom, max_zoom);
  const double next_x = x - anchor.x * zoom * ui_scale_, next_y = y - anchor.y * zoom * ui_scale_;
  if (!safe_pan(next_x, next_y)) { return false; }
  zoom_ = zoom; pan_x_ = next_x; pan_y_ = next_y;
  return true;
}

AnalysisGraphPoint AnalysisGraphCanvas::to_screen(AnalysisGraphPoint point) const
{
  const double scale = zoom_ * ui_scale_;
  return {pan_x_ + point.x * scale, pan_y_ + point.y * scale};
}

AnalysisGraphPoint AnalysisGraphCanvas::to_graph(AnalysisGraphPoint point) const
{
  const double scale = zoom_ * ui_scale_;
  return {(point.x - pan_x_) / scale, (point.y - pan_y_) / scale};
}

std::optional<size_t> AnalysisGraphCanvas::hit(double x, double y) const
{
  if (!view_ || !std::isfinite(x) || !std::isfinite(y) || x < 0 || y < 0 || x >= width_ || y >= height_) { return {}; }
  const auto point = to_graph({x, y});
  const size_t count = std::min(view_->nodes.size(), AnalysisGraphView::max_nodes);
  for (size_t i = count; i > 0; --i) {
    const auto &rect = view_->nodes[i - 1].rect;
    if (geometry(rect) && point.x >= rect.x && point.x < rect.x + rect.width &&
        point.y >= rect.y && point.y < rect.y + rect.height) { return i - 1; }
  }
  return {};
}

std::optional<AnalysisGraphCanvas::PortHit> AnalysisGraphCanvas::hit_port(double x, double y) const
{
  if (!view_ || !std::isfinite(x) || !std::isfinite(y) || x < 0 || y < 0 || x >= width_ || y >= height_ || zoom_ < .5) { return {}; }
  std::optional<PortHit> best;
  double nearest = 8 * ui_scale_;
  const size_t count = std::min(view_->nodes.size(), AnalysisGraphView::max_nodes);
  for (size_t i = 0; i < count; ++i) {
    const auto &node = view_->nodes[i];
    for (const bool output : {false, true}) {
      const auto &ports = output ? node.outputs : node.inputs;
      for (size_t p = 0; p < std::min(ports.size(), AnalysisGraphView::max_ports); ++p) {
        const auto point = to_screen(ports[p].point);
        const double distance = std::hypot(point.x - x, point.y - y);
        if (finite(point) && distance <= nearest) { nearest = distance; best = PortHit{i, p, output}; }
      }
    }
  }
  return best;
}

ui::DrawList AnalysisGraphCanvas::draw_list(double width, double height, double ui_scale,
                                           const ui::TextMeasurer &measurer, std::string_view language,
                                           std::optional<size_t> selected)
{
  ui::DrawList draw;
  if (!viewport(width, height, ui_scale)) { return draw; }
  if (ui_scale != ui_scale_) {
    const auto center = to_graph({width / 2, height / 2});
    const double x = width / 2 - center.x * zoom_ * ui_scale, y = height / 2 - center.y * zoom_ * ui_scale;
    if (!safe_pan(x, y)) { return draw; }
    pan_x_ = x; pan_y_ = y; ui_scale_ = ui_scale;
  }
  width_ = width; height_ = height;
  const ui::Rect clip{0, 0, float(width), float(height)};
  draw.clip_push(clip);
  draw.rect(clip, ui::Color::rgb(0x20252C));
  const double scale = zoom_ * ui_scale_;
  double grid = 40 * scale;
  const double minimum_grid = std::max({16 * ui_scale_, width / 128, height / 128});
  while (grid < minimum_grid) { grid *= 2; }
  const double gx = std::fmod(std::fmod(pan_x_, grid) + grid, grid);
  const double gy = std::fmod(std::fmod(pan_y_, grid) + grid, grid);
  for (double x = gx; x < width; x += grid) { draw.rect({float(x), 0, 1, float(height)}, ui::Color::rgb(0x2A3038)); }
  for (double y = gy; y < height; y += grid) { draw.rect({0, float(y), float(width), 1}, ui::Color::rgb(0x2A3038)); }
  if (!view_) { draw.clip_pop(); return draw; }

  for (size_t i = 0; i < std::min(view_->edges.size(), AnalysisGraphView::max_edges); ++i) {
    const auto &edge = view_->edges[i];
    if (edge.source < 0 && edge.target < 0) { continue; }
    ui::Color color = edge.diagnostic.empty() ? ui::Color::rgb(0x788C9F) :
        edge.diagnostic == "unknown_type" ? ui::Color::rgb(0xBE975F) : ui::Color::rgb(0xCD7979);
    const bool chosen = selected && ((edge.source >= 0 && size_t(edge.source) == *selected) ||
                                     (edge.target >= 0 && size_t(edge.target) == *selected));
    if (chosen && edge.diagnostic.empty()) { color = ui::Color::rgb(0x9ECDEA); }
    curve(draw, to_screen(edge.from), to_screen(edge.to), width, height, scale,
          (chosen ? 1.8 : 1.2) * ui_scale_, color);
  }

  const bool labels = zoom_ >= .5, fine_labels = zoom_ >= .7;
  const ui::FontStyle title_font{ui::FontKind::Regular, float(13 * scale)};
  const ui::FontStyle small_font{ui::FontKind::Regular, float(11 * scale)};
  const bool chinese = language.starts_with("zh");
  for (size_t i = 0; i < std::min(view_->nodes.size(), AnalysisGraphView::max_nodes); ++i) {
    const auto &node = view_->nodes[i];
    if (!geometry(node.rect)) { continue; }
    const auto origin = to_screen({node.rect.x, node.rect.y});
    const Rect box{origin.x, origin.y, node.rect.width * scale, node.rect.height * scale};
    if (!visible(box, width, height, 8 * ui_scale_)) { continue; }
    const bool chosen = selected && *selected == i;
    const bool problem = node.cyclic || node.ambiguous_id || !node.known_type || node.flagged;
    const auto accent = node.cyclic || node.ambiguous_id || node.flagged ? ui::Color::rgb(0xCC7C7C) :
        !node.known_type ? ui::Color::rgb(0xD3AB70) : stage_color(node.stage);
    // Unsaved candidate changes are outlined in amber until saved or discarded.
    const auto outline = chosen ? ui::Color::rgb(0xBBDCF2) : node.edited ? ui::Color::rgb(0xE8C46A) : accent;
    auto &body = draw.round_box(pixels(box), float(5 * scale), ui::CORNER_ALL, ui::Color::rgb(0x343C47), outline);
    body.line_width = float((chosen || node.edited ? 2 : 1) * ui_scale_);
    draw.round_box({float(box.x + scale), float(box.y + scale), float(std::max(0.0, box.width - 2 * scale)), float(34 * scale)},
                   float(4 * scale), ui::CORNER_TOP, ui::Color::rgb(0x424D5A), {0, 0, 0, 0});
    draw.clip_push(pixels({box.x - 4 * scale, box.y, box.width + 8 * scale, box.height}).intersect(clip));
    if (labels) {
      const auto &localized = chinese && !node.title_zh.empty() ? node.title_zh : node.title_en;
      const auto &title = node.label != node.id || localized.empty() ? node.label : localized;
      const float room = float(std::max(0.0, box.width - (problem ? 28 : 16) * scale));
      draw.text(ui::clip_text(title, room, measurer, title_font), {float(box.x + 8 * scale), float(box.y + 16 * scale)},
                title_font, ui::Color::rgb(0xF0F2F5));
      draw.text(ui::clip_text(node.id, room, measurer, small_font), {float(box.x + 8 * scale), float(box.y + 30 * scale)},
                small_font, ui::Color::rgb(0xC3CEDB));
      if (problem) { draw.text("!", {float(box.x + box.width - 15 * scale), float(box.y + 17 * scale)}, title_font, accent); }
    }
    auto sockets = [&](const std::vector<AnalysisGraphPort> &ports, bool input) {
      const bool shared_row = !node.inputs.empty() && !node.outputs.empty();
      const double available = (shared_row ? box.width / 2 : box.width) - 14 * scale;
      const double radius = 3 * scale;
      for (size_t p = 0; p < std::min(ports.size(), AnalysisGraphView::max_ports); ++p) {
        const auto &port = ports[p];
        const auto point = to_screen(port.point);
        if (!finite(point) || point.x < -radius || point.x > width + radius || point.y < -radius || point.y > height + radius) { continue; }
        if (labels) {
          draw.round_box({float(point.x - radius), float(point.y - radius), float(2 * radius), float(2 * radius)},
                         float(radius), ui::CORNER_ALL, port_color(port), {0, 0, 0, 0});
        }
        if (fine_labels && available > 0) {
          const auto label = ui::clip_text(port.name, float(available), measurer, small_font);
          const double x = input ? point.x + 8 * scale : point.x - 8 * scale - measurer.width(label, small_font);
          const auto metrics = measurer.metrics(small_font);
          draw.text(label, {float(x), float(point.y + (metrics.ascent - metrics.descent) / 2)},
                    small_font, ui::Color::rgb(0xD8DFE7));
        }
      }
    };
    sockets(node.inputs, true);
    sockets(node.outputs, false);
    draw.clip_pop();
  }
  if (pending_link_) {
    curve(draw, pending_link_->first, pending_link_->second, width, height, scale, 2 * ui_scale_, ui::Color::rgb(0xE8C46A));
  }
  draw.clip_pop();
  return draw;
}

}  // namespace stk::app
