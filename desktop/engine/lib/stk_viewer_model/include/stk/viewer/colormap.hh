/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Colour mapping of stk.payload/2 (spec §5; web/src/colormaps.ts; suan/render/colormaps.py):
 * 256-entry RGBA8 LUTs with exact VTK binning, categorical palettes with exact integer matching and
 * nearest sampling, stk:orientation-hsl, stk:categorical and the volume colour transfer points. */

#include "stk/io/payload.hh"

#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace stk::viewer {

using RGBA8 = std::array<uint8_t, 4>;
using RGB = std::array<double, 3>;

inline constexpr std::string_view kOrientationHsl = "stk:orientation-hsl";

/** 8-bit value of a colour component in [0, 1]: floor(255 c + 0.5), clamped. */
uint8_t to_byte(double c);
/** RGBA8 of float RGB(A) (alpha 1 when absent); `fallback` when `c` has fewer than 3 values. */
RGBA8 rgba8(std::span<const double> c, RGBA8 fallback = {128, 128, 128, 255});
RGBA8 rgba8_json(const io::Json *color, RGBA8 fallback = {128, 128, 128, 255});

/** CSS Color 4 HSL -> RGB (h in degrees, s and l in [0, 1]). */
RGB hsl_to_rgb(double h, double s, double l);
/** stk:orientation-hsl of vector p for maximum magnitude M (domain-classifiers.md §6.2). */
RGB orientation_hsl(double px, double py, double pz, double max_magnitude, double l0 = 0.0, double l1 = 1.0);
/** stk:categorical colour of a label value (domain-classifiers.md §6.5); non-integers are grey. */
RGB categorical_color(double value);

/** LUT entry of value v over [lo, hi] (spec §5): 0..255, -1 below, 256 above, -2 for NaN. */
int lut_index(double v, double lo, double hi);

struct ContinuousColormap {
  std::string id, name;
  std::array<RGBA8, 256> lut{};
  RGBA8 nan{128, 128, 128, 255}, below{}, above{};

  RGBA8 map(double v, double lo, double hi) const;
  /** 259 texels [below, lut 0..255, above, nan] for a GPU texture sampled with texelFetch at
   * lut_texel(v): exact binning on the GPU (spec §5, Blender "Closest" sampling). */
  std::array<RGBA8, 259> texture() const;
  static int texel(double v, double lo, double hi);
};

struct CategoryEntry {
  int64_t value;
  std::string name;
  RGBA8 color;
};

struct CategoricalColormap {
  std::string id, name;
  std::vector<CategoryEntry> entries;
  std::map<int64_t, RGBA8> lookup;
  RGBA8 unknown{128, 128, 128, 255};

  /** Exact integer match (non-integers and misses give `unknown`). */
  RGBA8 map(double v) const;
};

/** The grey ramp used when a payload names no continuous colormap. */
ContinuousColormap grey_colormap();

/** Colormap `id` of a payload (continuous LUT or categorical palette); nullopt when absent. */
struct Colormap {
  std::optional<ContinuousColormap> continuous;
  std::optional<CategoricalColormap> categorical;
};
std::optional<Colormap> resolve_colormap(const io::Payload &payload, std::string_view id);

/** Scalar per tuple: the component, or the magnitude ("magnitude", or null/absent on vectors). */
std::vector<double> scalar_values(std::span<const double> values, int components, const io::Json &component);
/** [min, max] of the finite values ([0, 1] when there is none). */
std::array<double, 2> finite_range(std::span<const double> values);

/**
 * Colour transfer points [physical value, r, g, b] of a volume (spec §6.6): a continuous LUT spread
 * over `range` at bin centres ((i + 0.5) / 256) (one point, LUT entry 128, when hi <= lo), or each
 * categorical entry (its RGBA8 colour) held over value +- 0.499.
 */
std::vector<std::array<double, 4>> volume_color_points(const Colormap *colormap, std::array<double, 2> range,
                                                       std::vector<std::string> *warnings = nullptr);

/** Result of colouring the tuples of a layer (web colormaps.ts layerColors). */
struct ColorResult {
  std::vector<RGBA8> colors; /* one per tuple; empty for a solid colour */
  std::array<double, 4> solid{0.8, 0.8, 0.8, 1.0};
  bool categorical = false;
  bool nearest = false; /* nearest sampling (labels, interpolate: "nearest") */
  std::optional<std::array<double, 2>> range;
  std::optional<std::string> colormap; /* id of the colormap used */
  std::vector<std::string> warnings;
};

/**
 * Colours of `count` tuples of a layer per its colour spec (spec §5): solid, attribute (continuous
 * LUT over spec range / attribute range / accessor min-max hint / finite data range, or categorical
 * palette), or direction (stk:orientation-hsl of `vectors` or the named attribute).
 */
ColorResult layer_colors(const io::Payload &payload,
                         const io::Json &layer,
                         const io::Json &color_spec,
                         size_t count,
                         std::string_view association,
                         std::span<const float> vectors = {},
                         int vector_components = 3);

}  // namespace stk::viewer
