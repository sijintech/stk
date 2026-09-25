/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* CPU pick refinement in float64. The GPU id buffer names (layer, element); these functions
 * intersect the exact element (or all elements) with the pixel ray in double precision and return
 * the physical position: layer origin + hit point, where the payload stores float32 coordinates
 * relative to that origin. Colours are never reported as data: the client probes the original data
 * at the returned position (view.probe). */

#include "stk/viewer/camera.hh"
#include "stk/viewer/glyph.hh"

#include <cstdint>
#include <optional>
#include <span>
#include <variant>

namespace stk::viewer {

struct TriangleHit {
  double t;    /* ray parameter */
  double u, v; /* barycentric weights of vertices b and c (a: 1 - u - v) */
};

/** Moller-Trumbore in double relative to vertex a; nullopt when the ray misses or is parallel. */
std::optional<TriangleHit> intersect_triangle(const Ray &ray, const dvec3 &a, const dvec3 &b, const dvec3 &c,
                                              bool cull_back_faces = false);
/** Ray/sphere: the nearest t >= 0. */
std::optional<double> intersect_sphere(const Ray &ray, const dvec3 &center, double radius);

struct PickHit {
  uint32_t element = 0;         /* triangle, point, instance, segment or sample index */
  double t = 0;                 /* distance along the (unit) ray */
  dvec3 local;                  /* hit relative to render_origin */
  std::array<double, 3> physical{}; /* render_origin + local, in physical coordinates */
  std::array<double, 3> barycentric{}; /* triangles: weights of the three vertices */
};

/** Indices of a triangles/lines layer: u32 or u16 (payload accessor types); empty = 0,1,2,... */
using IndexSpan = std::variant<std::span<const uint32_t>, std::span<const uint16_t>>;

/** Positions of a layer: float32 xyz relative to the layer origin. */
struct LayerGeometry {
  std::span<const float> positions; /* 3 per point */
  IndexSpan indices;
  dvec3 render_origin;              /* payload render_origin */
  dvec3 layer_origin;               /* layer origin (== render_origin when the layer has none) */
};

/**
 * Nearest triangle hit along the ray. `candidate` (from the GPU id buffer) is tested first and, if
 * it is hit, returned without scanning (exact refinement); otherwise every triangle is tested.
 */
std::optional<PickHit> pick_triangles(const Ray &ray, const LayerGeometry &geometry,
                                      std::optional<uint32_t> candidate = std::nullopt);

/**
 * Point sprites of `size_px` pixels (screen space): the nearest point whose projection lies within
 * size_px / 2 of the pixel (x, y); its exact position is returned. Spheres (`radius_world` > 0 or
 * per-point radii) are intersected in world space instead.
 */
std::optional<PickHit> pick_points(const CameraPose &pose, const Viewport &viewport, double x, double y,
                                   const LayerGeometry &geometry, double size_px,
                                   std::optional<uint32_t> candidate = std::nullopt);
std::optional<PickHit> pick_spheres(const Ray &ray, const LayerGeometry &geometry, double radius,
                                    std::span<const float> radii = {});

/** Glyph instances (spec §6.5): each instance transform is inverted and the ray intersected with
 * the glyph mesh in the glyph's frame. `scales` are the per-instance scales (instance_scales()). */
std::optional<PickHit> pick_glyphs(const Ray &ray, const LayerGeometry &geometry, std::span<const float> directions,
                                   std::span<const double> scales, const GlyphMesh &mesh,
                                   std::optional<uint32_t> candidate = std::nullopt);

/** A slice image quad (spec §6.2): hit position and the nearest sample index (i + j * w). */
std::optional<PickHit> pick_slice_image(const Ray &ray, const dvec3 &plane_origin, const dvec3 &u, const dvec3 &v,
                                        uint32_t width, uint32_t height, const dvec3 &render_origin,
                                        const dvec3 &layer_origin);

}  // namespace stk::viewer
