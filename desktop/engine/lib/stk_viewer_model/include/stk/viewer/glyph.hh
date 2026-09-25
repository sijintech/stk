/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Canonical glyph geometry (docs/specs/stk-render-payload-v2.md §6.5): unit length along +x, built
 * point for point like the VTK sources the offscreen renderer uses (vtkArrowSource,
 * vtkConeSource, vtkSphereSource, vtkCubeSource, vtkLineSource with the parameters of
 * suan/render/offscreen.py glyph_source), so the GPU glyphs, the offscreen PNGs and picking agree. */

#include "stk/io/json.hh"
#include "stk/viewer/math.hh"

#include <array>
#include <cstdint>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

namespace stk::viewer {

enum class GlyphShape { Arrow, Cone, Sphere, Line, Cube };

std::optional<GlyphShape> parse_glyph_shape(std::string_view name);
std::string_view glyph_shape_name(GlyphShape shape);

struct GlyphMesh {
  std::vector<std::array<float, 3>> points;
  /** Per-point normals where VTK provides them (sphere, cube); empty = flat shading. */
  std::vector<std::array<float, 3>> normals;
  /** VTK polygons (triangles, quads, cap n-gons) in VTK's order. */
  std::vector<std::vector<uint32_t>> polygons;
  /** Line cells (the "line" shape). */
  std::vector<std::array<uint32_t, 2>> lines;

  /** Fan triangulation of the polygons (vtkTriangleFilter order), 3 indices per triangle. */
  std::vector<uint32_t> triangles() const;
  /** Flat-shaded triangle soup (positions and face normals, 3 vertices per triangle) for GPUs that
   * need explicit normals. */
  void flat(std::vector<std::array<float, 3>> &positions, std::vector<std::array<float, 3>> &normals) const;
};

/**
 * Glyph geometry: `resolution` sides of cylinders/cones and the sphere's longitude count; the sphere
 * uses max(3, resolution / 2 + 1) latitude rows (offscreen.py). `center` shifts arrows, cones and
 * lines by -0.5 along x.
 */
GlyphMesh glyph_mesh(GlyphShape shape, int resolution = 8, bool center = false);

enum class ScaleMode { Uniform, Magnitude, Attribute };

/** appearance.scale of an instances layer. */
struct GlyphScale {
  ScaleMode by = ScaleMode::Uniform;
  double factor = 1.0;
  std::string attribute;
  static GlyphScale from_json(const io::Json &appearance_scale);
};

/**
 * Per-instance scale s_i (spec §6.5): scales[i] when given, else factor (uniform), factor * |d_i|
 * (magnitude) or factor * attribute_i (attribute; the magnitude of vector attributes). Instances
 * with |d_i| = 0, a non-finite direction or a non-finite scale get NaN (not drawn). Returns |s_i|
 * as the offscreen renderer draws it.
 */
std::vector<double> instance_scales(std::span<const float> directions,
                                    std::span<const float> scales,
                                    const GlyphScale &scale,
                                    std::span<const double> attribute = {},
                                    int attribute_components = 1);

/** translate(position) * rotate(+x -> d/|d|) * scale(s) (the centre shift is in the mesh). */
dmat4 instance_matrix(const dvec3 &position, const dvec3 &direction, double scale);

}  // namespace stk::viewer
