/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Basic value types of the UI toolkit: points, rectangles (window pixels, origin top-left, y down)
 * and 8-bit RGBA colours.
 */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

namespace stk::ui {

struct Vec2 {
  float x = 0.0f;
  float y = 0.0f;
};

/** Axis-aligned rectangle in window pixels (origin top-left, y grows downwards). */
struct Rect {
  float x = 0.0f;
  float y = 0.0f;
  float w = 0.0f;
  float h = 0.0f;

  float x1() const { return x + w; }
  float y1() const { return y + h; }
  float cx() const { return x + 0.5f * w; }
  float cy() const { return y + 0.5f * h; }
  bool empty() const { return w <= 0.0f || h <= 0.0f; }
  bool contains(Vec2 p) const { return p.x >= x && p.x < x + w && p.y >= y && p.y < y + h; }
  Rect inset(float dx, float dy) const { return {x + dx, y + dy, std::max(0.0f, w - 2 * dx), std::max(0.0f, h - 2 * dy)}; }
  Rect translated(float dx, float dy) const { return {x + dx, y + dy, w, h}; }
  Rect intersect(const Rect &o) const
  {
    const float ax = std::max(x, o.x), ay = std::max(y, o.y);
    const float bx = std::min(x1(), o.x1()), by = std::min(y1(), o.y1());
    return {ax, ay, std::max(0.0f, bx - ax), std::max(0.0f, by - ay)};
  }
  bool operator==(const Rect &o) const = default;
};

/** Rounds a rectangle's edges to whole pixels (layout output is pixel aligned). */
inline Rect snap(const Rect &r)
{
  const float x0 = std::round(r.x), y0 = std::round(r.y);
  return {x0, y0, std::round(r.x + r.w) - x0, std::round(r.y + r.h) - y0};
}

/** Straight (non-premultiplied) sRGB colour, 8 bits per channel. */
struct Color {
  uint8_t r = 0, g = 0, b = 0, a = 255;

  /** From 0xRRGGBBAA, the notation used by Blender's userdef_default_theme.c. */
  static constexpr Color hex(uint32_t rgba)
  {
    return {uint8_t(rgba >> 24), uint8_t(rgba >> 16), uint8_t(rgba >> 8), uint8_t(rgba)};
  }
  static constexpr Color rgb(uint32_t rgb_hex) { return hex((rgb_hex << 8) | 0xffu); }
  static Color from_float(float r, float g, float b, float a = 1.0f);

  Color with_alpha(uint8_t alpha) const { return {r, g, b, alpha}; }
  Color scaled_alpha(float f) const { return {r, g, b, uint8_t(std::clamp(a * f, 0.0f, 255.0f) + 0.5f)}; }
  /** Blender's color_mul_hsl_v3(): scales hue, saturation and lightness. */
  Color mul_hsl(float h, float s, float l) const;
  /** Linear blend towards `o` (fac 0 = this, 1 = o), alpha included. */
  Color blend(const Color &o, float fac) const;
  /** "#rrggbbaa". */
  std::string to_hex() const;
  bool operator==(const Color &o) const = default;
};

}  // namespace stk::ui
