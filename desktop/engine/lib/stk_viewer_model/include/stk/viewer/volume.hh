/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Volume layers (spec §6.6; web/src/volume.ts; suan/render/colormaps.py): transfer functions in
 * physical values mapped onto the stored texture values, a sampled RGBA transfer-function LUT for
 * the ray marcher, the grid transform, and opacity per unit distance min(spacing). */

#include "stk/io/payload.hh"
#include "stk/viewer/colormap.hh"
#include "stk/viewer/math.hh"

#include <array>
#include <vector>

namespace stk::viewer {

struct VolumeGrid {
  std::array<int64_t, 3> dimensions{1, 1, 1};
  dvec3 origin;                              /* relative to the layer origin */
  dvec3 spacing{1, 1, 1};
  std::array<double, 9> direction{1, 0, 0, 0, 1, 0, 0, 0, 1}; /* row-major; columns are the axes */

  /** index (i, j, k) -> layer-local position: origin + direction * (spacing * ijk). */
  dmat4 index_to_local() const;
  /** Opacity unit distance: the smallest spacing (VTK SetScalarOpacityUnitDistance(min(spacing))). */
  double unit_distance() const;
};

struct VolumeTransfer {
  VolumeGrid grid;
  std::vector<std::array<double, 4>> color_points;   /* [physical value, r, g, b] */
  std::vector<std::array<double, 2>> opacity_points; /* [physical value, alpha], sorted */
  double value_scale = 1.0, value_offset = 0.0;       /* physical = stored * scale + offset */
  std::array<double, 2> value_range{0, 1};            /* physical */
  bool nearest = false;                               /* sampling: "nearest" (labels) */
  bool shade = false;
  bool categorical = false;
  std::vector<std::string> warnings;

  double stored_to_physical(double stored) const
  {
    return stored * value_scale + value_offset;
  }
  double physical_to_stored(double physical) const
  {
    return value_scale != 0 ? (physical - value_offset) / value_scale : 0.0;
  }
};

/** The transfer function of a validated volume layer. */
VolumeTransfer volume_transfer(const io::Payload &payload, const io::Json &layer);

/** Finite stored-value domain for a volume texture's transfer LUT, before value_scale/offset.
 * Normalized u8/u16 values divide by 255/65535. Empty/all-nonfinite input gives [0,1]; a constant
 * range expands by 0.5 (or the adjacent doubles when 0.5 cannot change a large value). */
std::array<double, 2> stored_range(std::span<const float> values);
std::array<double, 2> stored_range(std::span<const uint8_t> values, bool normalized = false);
std::array<double, 2> stored_range(std::span<const uint16_t> values, bool normalized = false);

/** vtkColorTransferFunction evaluation: piecewise linear in RGB between sorted points, clamped at the ends. */
RGB evaluate_color(const std::vector<std::array<double, 4>> &points, double value);
/** Piecewise-linear opacity, constant beyond the end points (colormaps.py opacity_at). */
double evaluate_opacity(const std::vector<std::array<double, 2>> &points, double value);

/**
 * RGBA float LUT of `size` texels over the STORED value domain [stored_lo, stored_hi] (texel i at
 * stored_lo + (i + 0.5) / size * (hi - lo)), for a 1D texture indexed by the raw texture value.
 * Alpha is the opacity per unit distance (apply opacity_correction() per sample step).
 */
std::vector<std::array<float, 4>> transfer_lut(const VolumeTransfer &tf, double stored_lo, double stored_hi,
                                               int size = 1024);

/** Opacity of a ray-march step of length `step` for a per-unit-distance alpha:
 * 1 - (1 - alpha)^(step / unit_distance). */
double opacity_correction(double alpha, double step, double unit_distance);

/** colormaps.py categorical_opacity: labels >= 0 get `alpha`, negative labels 0 (step at -0.5). */
std::vector<std::array<double, 2>> categorical_opacity(double lo, double hi, double alpha = 0.8);

}  // namespace stk::viewer
