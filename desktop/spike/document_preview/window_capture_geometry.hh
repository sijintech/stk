/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <cstdint>
#include <optional>

namespace stk::document_preview::capture_geometry {
struct Rect {
  int32_t left = 0, top = 0, right = 0, bottom = 0;
};
enum class Origin { DwmVisibleBounds, FullWindowRect };
struct Geometry {
  Origin origin = Origin::DwmVisibleBounds;
  Rect frame{};
  uint32_t left = 0, top = 0, right = 0, bottom = 0;
};
constexpr int64_t width(Rect rect) { return int64_t(rect.right) - rect.left; }
constexpr int64_t height(Rect rect) { return int64_t(rect.bottom) - rect.top; }
constexpr bool contains(Rect outer, Rect inner)
{
  return width(outer) > 0 && height(outer) > 0 && width(inner) > 0 && height(inner) > 0 &&
         inner.left >= outer.left && inner.top >= outer.top &&
         inner.right <= outer.right && inner.bottom <= outer.bottom;
}
// WGC surfaces have physical pixel extents. Only a matching, documented rectangle
// may supply their origin: no guessed border width, scaling or pixel tolerance.
constexpr std::optional<Geometry> select(int item_width, int item_height, Rect window,
                                         Rect dwm, Rect client, bool physical_coordinates)
{
  if (!physical_coordinates || item_width <= 0 || item_height <= 0 ||
      item_width > 8192 || item_height > 8192 ||
      int64_t(item_width) * item_height > 16 * 1024 * 1024 ||
      !contains(dwm, client)) return std::nullopt;
  Origin origin;
  Rect frame;
  if (item_width == width(dwm) && item_height == height(dwm)) {
    origin = Origin::DwmVisibleBounds; frame = dwm;
  }
  else if (item_width == width(window) && item_height == height(window) && contains(window, dwm)) {
    origin = Origin::FullWindowRect; frame = window;
  }
  else return std::nullopt;
  // Containment and the <=8192 item bounds prove all crop offsets fit uint32_t.
  return Geometry{origin, frame, uint32_t(int64_t(client.left) - frame.left),
      uint32_t(int64_t(client.top) - frame.top), uint32_t(int64_t(client.right) - frame.left),
      uint32_t(int64_t(client.bottom) - frame.top)};
}

struct FrameGeometry {
  Geometry pool{};
  Geometry content{};
};
// WGC ContentSize describes valid pixels inside the fixed-size pool surface.
// Select its origin independently from the allocation's origin; no pixel outside
// ContentSize may be copied, even when the surface's allocation is larger.
// Extent matching is still only a geometry candidate: OS pixel/cycle acceptance
// must verify the selected content origin on the target Windows environment.
constexpr std::optional<FrameGeometry> select_frame(
    int content_width, int content_height, int item_width, int item_height,
    int pool_width, int pool_height, uint32_t texture_width, uint32_t texture_height,
    Rect window, Rect dwm, Rect client, bool physical_coordinates)
{
  if (item_width != pool_width || item_height != pool_height ||
      !contains(window, dwm) || texture_width == 0 || texture_height == 0 ||
      texture_width > 8192 || texture_height > 8192 ||
      uint64_t(texture_width) * texture_height > 16 * 1024 * 1024 ||
      content_width <= 0 || content_height <= 0 ||
      content_width > pool_width || content_height > pool_height ||
      uint64_t(content_width) > texture_width || uint64_t(content_height) > texture_height) {
    return std::nullopt;
  }
  const auto pool = select(item_width, item_height, window, dwm, client, physical_coordinates);
  const auto content = select(content_width, content_height, window, dwm, client, physical_coordinates);
  if (!pool || !content || content->right > uint32_t(content_width) ||
      content->bottom > uint32_t(content_height)) return std::nullopt;
  return FrameGeometry{*pool, *content};
}
} // namespace stk::document_preview::capture_geometry
