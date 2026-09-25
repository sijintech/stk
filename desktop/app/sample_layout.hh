/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Layout of the WP1 sample frame ("中文 English" at several sizes on Blender's dark theme).
 *
 * Pure arithmetic, no GPU: the application draws with it and the golden / crispness checker
 * (desktop/tests/wm) uses it to find the text rows in exported PNGs. Coordinates are framebuffer
 * pixels with a bottom-left origin.
 */
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace stk::app {

/** Blender default dark theme (release/datafiles/userdef/userdef_default_theme.c). */
namespace theme {
inline constexpr float kWindowBack[4] = {0x18 / 255.0f, 0x18 / 255.0f, 0x18 / 255.0f, 1.0f};
inline constexpr float kHeaderBack[4] = {0x18 / 255.0f, 0x18 / 255.0f, 0x18 / 255.0f, 1.0f};
inline constexpr float kRegionBack[4] = {0x30 / 255.0f, 0x30 / 255.0f, 0x30 / 255.0f, 1.0f};
inline constexpr float kText[4] = {0xe6 / 255.0f, 0xe6 / 255.0f, 0xe6 / 255.0f, 1.0f};
inline constexpr float kTextHi[4] = {1.0f, 1.0f, 1.0f, 1.0f};
inline constexpr float kAccent[4] = {0x47 / 255.0f, 0x72 / 255.0f, 0xb3 / 255.0f, 1.0f};
}  // namespace theme

inline constexpr const char *kSampleCjk = "\xe4\xb8\xad\xe6\x96\x87"; /* 中文 */
inline constexpr const char *kSampleLatin = "English";
inline constexpr std::array<float, 5> kSamplePoints = {9.0f, 11.0f, 14.0f, 20.0f, 28.0f};

/** Header height at 1x (Blender's HEADERY). */
inline constexpr float kHeader1x = 26.0f;
inline constexpr float kMargin1x = 16.0f;

struct SampleRow {
  float points = 0.0f;
  /** BLF pixel size (points x scale). */
  float px = 0.0f;
  int baseline = 0;
  /** "中文" starts here and spans two em (full-width glyphs). */
  int cjk_x = 0;
  /** "English" starts here, half an em after the CJK text. */
  int latin_x = 0;
};

struct SampleLayout {
  int width = 0, height = 0;
  float scale = 1.0f;
  int header_h = 0;
  int margin = 0;
  /** Accent line under the header: [accent_y0, accent_y1). */
  int accent_y0 = 0, accent_y1 = 0;
  std::vector<SampleRow> rows;
};

inline int round_px(const float v)
{
  return int(std::lround(v));
}

inline SampleLayout sample_layout(const int width, const int height, const float scale)
{
  SampleLayout l;
  l.width = width;
  l.height = height;
  l.scale = scale;
  l.header_h = round_px(kHeader1x * scale);
  l.margin = round_px(kMargin1x * scale);
  const int main_top = height - l.header_h;
  l.accent_y1 = main_top;
  l.accent_y0 = main_top - std::max(1, round_px(2.0f * scale));
  int cursor = l.accent_y0 - l.margin;
  for (const float pt : kSamplePoints) {
    SampleRow row;
    row.points = pt;
    row.px = pt * scale;
    row.baseline = cursor - round_px(row.px * 1.2f);
    row.cjk_x = l.margin;
    row.latin_x = l.margin + round_px(row.px * 2.5f);
    l.rows.push_back(row);
    cursor -= round_px(row.px * 1.6f);
  }
  return l;
}

}  // namespace stk::app
