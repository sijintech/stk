/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/picking.hh"

#include <cmath>
#include <algorithm>
#include <limits>
#include <numbers>

namespace stk::viewer {

namespace {

constexpr double kEdge = 1e-12; /* barycentric tolerance: rays through shared edges hit one of the triangles */

uint32_t index_at(const IndexSpan &indices, size_t k)
{
  return std::visit(
      [k](const auto &span) -> uint32_t { return span.empty() ? uint32_t(k) : uint32_t(span[k]); }, indices);
}

size_t index_count(const IndexSpan &indices, size_t points)
{
  return std::visit([points](const auto &span) { return span.empty() ? points : span.size(); }, indices);
}

dvec3 point_at(std::span<const float> positions, uint32_t i)
{
  return {double(positions[3 * size_t(i)]), double(positions[3 * size_t(i) + 1]), double(positions[3 * size_t(i) + 2])};
}

/* Offset from render_origin to the layer origin, and the ray in layer-local coordinates. */
struct LocalRay {
  dvec3 offset;
  Ray ray;
};

LocalRay to_layer(const Ray &ray, const LayerGeometry &g)
{
  const dvec3 offset = g.layer_origin - g.render_origin;
  return {offset, {ray.origin - offset, ray.direction}};
}

PickHit make_hit(uint32_t element, double t, const dvec3 &layer_local, const LayerGeometry &g)
{
  PickHit hit;
  hit.element = element;
  hit.t = t;
  hit.local = (g.layer_origin - g.render_origin) + layer_local;
  hit.physical = {g.layer_origin.x + layer_local.x, g.layer_origin.y + layer_local.y, g.layer_origin.z + layer_local.z};
  return hit;
}

template<typename Test>
std::optional<PickHit> pick_elements(size_t count, std::optional<uint32_t> candidate, PickMode mode, const Test &test)
{
  if (candidate && *candidate < count) {
    if (auto hit = test(*candidate)) {
      return hit;
    }
  }
  if (mode == PickMode::CandidateOnly) {
    return std::nullopt;
  }
  std::optional<PickHit> best;
  for (size_t i = 0; i < count; i++) {
    if (auto hit = test(i); hit && (!best || hit->t < best->t)) {
      best = hit;
    }
  }
  return best;
}

dvec3 interpolate(const dvec3 &a, const dvec3 &b, double u)
{
  return {std::lerp(a.x, b.x, u), std::lerp(a.y, b.y, u), std::lerp(a.z, b.z, u)};
}

}  // namespace

std::optional<TriangleHit> intersect_triangle(const Ray &ray, const dvec3 &a, const dvec3 &b, const dvec3 &c, bool cull)
{
  const dvec3 e1 = b - a, e2 = c - a;
  const dvec3 p = cross(ray.direction, e2);
  const double det = dot(e1, p);
  const double scale = length(e1) * length(e2) * length(ray.direction);
  if (!(std::abs(det) > scale * 1e-15) || (cull && det < 0)) {
    return std::nullopt;
  }
  const double inv = 1.0 / det;
  const dvec3 s = ray.origin - a;
  const double u = dot(s, p) * inv;
  if (u < -kEdge || u > 1.0 + kEdge) {
    return std::nullopt;
  }
  const dvec3 q = cross(s, e1);
  const double v = dot(ray.direction, q) * inv;
  if (v < -kEdge || u + v > 1.0 + kEdge) {
    return std::nullopt;
  }
  const double t = dot(e2, q) * inv;
  if (!(t >= 0)) {
    return std::nullopt;
  }
  return TriangleHit{t, u, v};
}

std::optional<double> intersect_sphere(const Ray &ray, const dvec3 &center, double radius)
{
  const dvec3 oc = ray.origin - center;
  const double b = dot(oc, ray.direction);
  const double dd = dot(ray.direction, ray.direction);
  /* Distance of the centre from the ray line, computed without cancellation. */
  const dvec3 closest = oc - ray.direction * (b / dd);
  const double h = radius * radius - dot(closest, closest);
  if (h < 0) {
    return std::nullopt;
  }
  const double sq = std::sqrt(h * dd);
  double t = (-b - sq) / dd;
  if (t < 0) {
    t = (-b + sq) / dd;
  }
  if (t < 0) {
    return std::nullopt;
  }
  return t;
}

std::optional<PickHit> pick_triangles(const Ray &ray, const LayerGeometry &g, std::optional<uint32_t> candidate,
                                      PickMode mode)
{
  const LocalRay local = to_layer(ray, g);
  const size_t points = g.positions.size() / 3;
  const size_t triangles = index_count(g.indices, points) / 3;
  const auto test = [&](size_t tri) -> std::optional<PickHit> {
    const uint32_t ia = index_at(g.indices, 3 * tri), ib = index_at(g.indices, 3 * tri + 1),
                   ic = index_at(g.indices, 3 * tri + 2);
    if (ia >= points || ib >= points || ic >= points) {
      return std::nullopt;
    }
    const dvec3 a = point_at(g.positions, ia), b = point_at(g.positions, ib), c = point_at(g.positions, ic);
    const auto h = intersect_triangle(local.ray, a, b, c);
    if (!h) {
      return std::nullopt;
    }
    /* The hit from the barycentric weights (exact on the triangle) rather than origin + t * dir. */
    const dvec3 p = a + (b - a) * h->u + (c - a) * h->v;
    PickHit hit = make_hit(uint32_t(tri), h->t, p, g);
    hit.barycentric = {1.0 - h->u - h->v, h->u, h->v};
    return hit;
  };
  return pick_elements(triangles, candidate, mode, test);
}

std::optional<PickHit> pick_points(const CameraPose &pose, const Viewport &viewport, double x, double y,
                                   const LayerGeometry &g, double size_px, std::optional<uint32_t> candidate,
                                   PickMode mode)
{
  const dvec3 offset = g.layer_origin - g.render_origin;
  const size_t points = g.positions.size() / 3;
  const double radius = std::max(0.5, size_px / 2.0);
  const Ray ray = pixel_ray(pose, viewport, x, y);
  const auto test = [&](size_t i) -> std::optional<PickHit> {
    const dvec3 p = point_at(g.positions, uint32_t(i));
    const auto s = project(pose, viewport, offset + p);
    if (!s || std::hypot(s->x - x, s->y - y) > radius) {
      return std::nullopt;
    }
    return make_hit(uint32_t(i), dot(offset + p - ray.origin, ray.direction), p, g);
  };
  return pick_elements(points, candidate, mode, test);
}

std::optional<PickHit> pick_spheres(const Ray &ray, const LayerGeometry &g, double radius, std::span<const float> radii,
                                    std::optional<uint32_t> candidate, PickMode mode)
{
  const LocalRay local = to_layer(ray, g);
  const size_t points = g.positions.size() / 3;
  const auto test = [&](size_t i) -> std::optional<PickHit> {
    const double r = i < radii.size() ? double(radii[i]) : radius;
    if (!(r > 0)) {
      return std::nullopt;
    }
    const dvec3 c = point_at(g.positions, uint32_t(i));
    const auto t = intersect_sphere(local.ray, c, r);
    if (!t) {
      return std::nullopt;
    }
    return make_hit(uint32_t(i), *t, local.ray.at(*t), g);
  };
  return pick_elements(points, candidate, mode, test);
}

std::optional<PickHit> pick_segments(const CameraPose &pose, const Viewport &viewport, double x, double y,
                                     const LayerGeometry &g, double width_px, std::optional<uint32_t> candidate,
                                     PickMode mode, std::optional<ClipRange> clip)
{
  if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(width_px) ||
      !std::isfinite(viewport.width) || !std::isfinite(viewport.height) ||
      !(viewport.width > 0) || !(viewport.height > 0) ||
      (clip && (!std::isfinite(clip->near_z) || !std::isfinite(clip->far_z) ||
                (!pose.parallel && clip->near_z < 0) || !(clip->far_z > clip->near_z))))
  {
    return std::nullopt;
  }
  /* Form camera-relative differences in double, without adding small vertices to a large origin. */
  const dvec3 offset = g.layer_origin - g.render_origin;
  CameraPose local_pose = pose;
  local_pose.position = pose.position - offset;
  local_pose.focal_point = pose.focal_point - offset;
  const dvec3 forward = local_pose.direction();
  if (!is_finite(local_pose.position) || !is_finite(forward) || !(length(forward) > 0) ||
      !is_finite(local_pose.view_up) || !(length(cross(forward, local_pose.view_up)) > 0) ||
      (pose.parallel && (!std::isfinite(pose.parallel_scale) || !(pose.parallel_scale > 0))) ||
      (!pose.parallel && !(pose.view_angle_deg > 0 && pose.view_angle_deg < 180)))
  {
    return std::nullopt;
  }
  const Ray ray = pixel_ray(local_pose, viewport, x, y);
  const double radius = std::max(0.5, width_px / 2.0);
  dvec3 right, up, back;
  local_pose.frame(right, up, back);
  const double half_height = pose.parallel ? pose.parallel_scale :
                                            std::tan(pose.view_angle_deg * std::numbers::pi / 360.0);
  const double left = (2.0 * (x - radius) / viewport.width - 1.0) * half_height * viewport.aspect();
  const double right_edge = (2.0 * (x + radius) / viewport.width - 1.0) * half_height * viewport.aspect();
  const double bottom = (1.0 - 2.0 * (y + radius) / viewport.height) * half_height;
  const double top = (1.0 - 2.0 * (y - radius) / viewport.height) * half_height;
  const size_t points = g.positions.size() / 3;
  const size_t segments = index_count(g.indices, points) / 2;
  const auto test = [&](size_t segment) -> std::optional<PickHit> {
    const uint32_t ia = index_at(g.indices, segment * 2), ib = index_at(g.indices, segment * 2 + 1);
    if (ia >= points || ib >= points) {
      return std::nullopt;
    }
    const dvec3 a = point_at(g.positions, ia), b = point_at(g.positions, ib);
    if (!is_finite(a) || !is_finite(b)) {
      return std::nullopt;
    }
    const double da = dot(a - local_pose.position, forward), db = dot(b - local_pose.position, forward);
    /* The tiny positive guard avoids perspective division at the eye plane when a segment crosses
     * it. Scale to the segment's depths so tiny scenes keep the same relative precision. */
    double near_z = clip ? std::max(0.0, clip->near_z) : 0.0;
    if (!pose.parallel) {
      near_z = std::max(near_z, std::max(std::abs(da), std::abs(db)) *
                                      (64.0 * std::numeric_limits<double>::epsilon()));
    }
    const double far_z = clip ? clip->far_z : std::numeric_limits<double>::infinity();
    if (!std::isfinite(da) || !std::isfinite(db)) {
      return std::nullopt;
    }
    double first = 0.0, last = 1.0;
    const auto clip_plane = [&](double fa, double fb) {
      if (fa < 0 && fb < 0) {
        return false;
      }
      if (fa < 0) {
        first = std::max(first, fa / (fa - fb));
      }
      if (fb < 0) {
        last = std::min(last, fa / (fa - fb));
      }
      return first <= last;
    };
    /* Clip to the cursor's tolerance square before projecting. This bounds screen coordinates
     * even for segments crossing the eye plane; subtracting enormous projected endpoints would
     * otherwise lose precision. The final circular tolerance is checked below. */
    const dvec3 ea = a - local_pose.position, eb = b - local_pose.position;
    const double ax = dot(ea, right), bx = dot(eb, right), ay = dot(ea, up), by = dot(eb, up);
    const double wa = pose.parallel ? 1.0 : da, wb = pose.parallel ? 1.0 : db;
    if (!clip_plane(da - near_z, db - near_z) ||
        (std::isfinite(far_z) && !clip_plane(far_z - da, far_z - db)) ||
        !clip_plane(ax - left * wa, bx - left * wb) ||
        !clip_plane(right_edge * wa - ax, right_edge * wb - bx) ||
        !clip_plane(ay - bottom * wa, by - bottom * wb) ||
        !clip_plane(top * wa - ay, top * wb - by))
    {
      return std::nullopt;
    }
    const auto sa = project(local_pose, viewport, interpolate(a, b, first));
    const auto sb = project(local_pose, viewport, interpolate(a, b, last));
    if (!sa || !sb || !is_finite(*sa) || !is_finite(*sb)) {
      return std::nullopt;
    }
    const double dx = sb->x - sa->x, dy = sb->y - sa->y;
    const double length_squared = dx * dx + dy * dy;
    /* For a segment along the view ray all projected positions coincide: use the nearer end. */
    double u = length_squared > 0 ? std::clamp(((x - sa->x) * dx + (y - sa->y) * dy) / length_squared, 0.0, 1.0) :
                                   (sa->z <= sb->z ? 0.0 : 1.0);
    const double sx = std::lerp(sa->x, sb->x, u), sy = std::lerp(sa->y, sb->y, u);
    if (std::hypot(sx - x, sy - y) > radius) {
      return std::nullopt;
    }
    if (!pose.parallel) {
      /* Screen interpolation is linear in reciprocal depth. Normalize to avoid depth overflow. */
      const double depth_scale = std::max(sa->z, sb->z);
      const double az = sa->z / depth_scale, bz = sb->z / depth_scale;
      u = u * az / ((1.0 - u) * bz + u * az);
    }
    u = std::lerp(first, last, u);
    const dvec3 p = interpolate(a, b, u);
    const double t = dot(p - ray.origin, ray.direction);
    if (!std::isfinite(t) || t < 0) {
      return std::nullopt;
    }
    PickHit hit = make_hit(uint32_t(segment), t, p, g);
    hit.barycentric = {1.0 - u, u, 0.0};
    return hit;
  };
  return pick_elements(segments, candidate, mode, test);
}

std::optional<PickHit> pick_glyphs(const Ray &ray, const LayerGeometry &g, std::span<const float> directions,
                                   std::span<const double> scales, const GlyphMesh &mesh,
                                   std::optional<uint32_t> candidate, PickMode mode)
{
  const LocalRay local = to_layer(ray, g);
  const size_t instances = std::min(g.positions.size() / 3, directions.size() / 3);
  const std::vector<uint32_t> tris = mesh.triangles();
  const auto test = [&](size_t i) -> std::optional<PickHit> {
    if (i >= scales.size() || !std::isfinite(scales[i]) || !(scales[i] > 0)) {
      return std::nullopt;
    }
    const dvec3 d{directions[3 * i], directions[3 * i + 1], directions[3 * i + 2]};
    const dmat4 m = instance_matrix(point_at(g.positions, uint32_t(i)), d, scales[i]);
    const dmat4 inv = m.inverted();
    const Ray glyph_ray{inv.transform_point(local.ray.origin), inv.transform_direction(local.ray.direction)};
    std::optional<TriangleHit> best;
    for (size_t k = 0; k + 2 < tris.size(); k += 3) {
      const auto h = intersect_triangle(glyph_ray, dvec3::from(mesh.points[tris[k]]), dvec3::from(mesh.points[tris[k + 1]]),
                                        dvec3::from(mesh.points[tris[k + 2]]));
      if (h && (!best || h->t < best->t)) {
        best = h;
      }
    }
    if (!best) {
      return std::nullopt;
    }
    /* An affine map keeps the ray parameter: t is also the world distance for a unit direction. */
    return make_hit(uint32_t(i), best->t, local.ray.at(best->t), g);
  };
  return pick_elements(instances, candidate, mode, test);
}

std::optional<PickHit> pick_slice_image(const Ray &ray, const dvec3 &origin, const dvec3 &u, const dvec3 &v,
                                        uint32_t width, uint32_t height, const dvec3 &render_origin,
                                        const dvec3 &layer_origin)
{
  const dvec3 offset = layer_origin - render_origin;
  const Ray r{ray.origin - offset, ray.direction};
  const dvec3 n = cross(u, v);
  const double denom = dot(r.direction, n);
  if (!(std::abs(denom) > 0) || !(length(n) > 0)) {
    return std::nullopt;
  }
  const double t = dot(origin - r.origin, n) / denom;
  if (!(t >= 0)) {
    return std::nullopt;
  }
  const dvec3 h = r.at(t) - origin;
  const double uu = dot(u, u), uv = dot(u, v), vv = dot(v, v);
  const double hu = dot(h, u), hv = dot(h, v);
  const double det = uu * vv - uv * uv;
  const double a = (hu * vv - hv * uv) / det, b = (hv * uu - hu * uv) / det;
  if (a < -kEdge || a > 1 + kEdge || b < -kEdge || b > 1 + kEdge) {
    return std::nullopt;
  }
  const uint32_t i = width > 1 ? uint32_t(std::lround(std::clamp(a, 0.0, 1.0) * (width - 1))) : 0;
  const uint32_t j = height > 1 ? uint32_t(std::lround(std::clamp(b, 0.0, 1.0) * (height - 1))) : 0;
  PickHit hit;
  hit.element = i + j * width;
  hit.t = t;
  const dvec3 p = origin + u * a + v * b;
  hit.local = offset + p;
  hit.physical = {layer_origin.x + p.x, layer_origin.y + p.y, layer_origin.z + p.z};
  hit.barycentric = {a, b, 0.0};
  return hit;
}

}  // namespace stk::viewer
