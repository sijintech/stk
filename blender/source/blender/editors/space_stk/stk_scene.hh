/* SPDX-FileCopyrightText: 2026 STK Authors
 * SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* No Blender/GPU dependency: scientific coordinates and picking are testable
 * independently of the window system. All world-coordinate math uses doubles. */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>

namespace blender::ed::stk {
using Point = std::array<double, 3>;

struct Camera {
  double yaw = 30, pitch = 55, zoom = 0.85;
  double pan_x = 0, pan_y = 0;

  Point project(const Point &p, const Point &center, double extent, double aspect) const
  {
    const double a = yaw * 0.017453292519943295, b = pitch * 0.017453292519943295;
    const double x = (p[0] - center[0]) * 2 / extent;
    const double y = (p[1] - center[1]) * 2 / extent;
    const double z = (p[2] - center[2]) * 2 / extent;
    const double u = std::cos(a) * x - std::sin(a) * y;
    const double v = std::sin(a) * x + std::cos(a) * y;
    return {(u * zoom + pan_x) / aspect,
            (std::cos(b) * v - std::sin(b) * z) * zoom + pan_y,
            (std::sin(b) * v + std::cos(b) * z) * zoom};
  }
};

inline std::array<float, 4> color(double value, double lower, double upper)
{
  const double t = upper > lower ? std::clamp((value - lower) / (upper - lower), 0.0, 1.0) : .5;
  /* Fixed sequential blue / cyan / yellow scale, also used by the legend. */
  constexpr float stops[3][3] = {{.10f, .18f, .46f}, {.07f, .67f, .70f}, {.98f, .88f, .26f}};
  const int i = t < .5 ? 0 : 1;
  const float f = float(t * 2 - i);
  return {stops[i][0] * (1 - f) + stops[i + 1][0] * f,
          stops[i][1] * (1 - f) + stops[i + 1][1] * f,
          stops[i][2] * (1 - f) + stops[i + 1][2] * f,
          1.f};
}

struct Scene {
  std::vector<Point> positions;
  std::vector<double> values;
  std::vector<uint32_t> indices;
  Point render_origin{}, center{};
  double extent = 1, lower = 0, upper = 1;

  bool validate()
  {
    if (positions.size() > 80000 || values.size() != positions.size() || indices.size() > 480000 ||
        indices.size() % 3 || !std::isfinite(lower) || !std::isfinite(upper) || lower > upper)
    {
      return false;
    }
    for (double n : render_origin) {
      if (!std::isfinite(n))
        return false;
    }
    Point lo{1e30, 1e30, 1e30}, hi{-1e30, -1e30, -1e30};
    for (const Point &p : positions) {
      for (int d = 0; d < 3; d++) {
        if (!std::isfinite(p[d]) || std::abs(p[d]) >= 1e30)
          return false;
        lo[d] = std::min(lo[d], p[d]);
        hi[d] = std::max(hi[d], p[d]);
      }
    }
    for (double v : values)
      if (!std::isfinite(v))
        return false;
    for (uint32_t i : indices)
      if (i >= positions.size())
        return false;
    if (!positions.empty()) {
      extent = std::max({hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], 1e-30});
      for (int d = 0; d < 3; d++)
        center[d] = (hi[d] + lo[d]) * .5;
    }
    return true;
  }

  /* Fit a rotated scientific model with a margin inside the current viewport. */
  double fit_zoom(Camera camera, double aspect) const
  {
    camera.zoom = 1;
    camera.pan_x = camera.pan_y = 0;
    double radius = 1e-6;
    for (const Point &p : positions) {
      const Point projected = camera.project(p, center, extent, aspect);
      radius = std::max({radius, std::abs(projected[0]), std::abs(projected[1])});
    }
    return std::clamp(.8 / radius, .02, 100.0);
  }

  /* Exact triangle intersection in orthographic screen coordinates. The
   * returned physical location is sent to the node for an original-data probe;
   * interpolated display colors are never reported as scientific measurements. */
  std::optional<Point> pick(const Camera &camera, double x, double y, double aspect) const
  {
    if (!(aspect > 0))
      return std::nullopt;
    std::optional<Point> hit;
    double front = -std::numeric_limits<double>::infinity();
    for (size_t i = 0; i < indices.size(); i += 3) {
      const Point &a = positions[indices[i]], &b = positions[indices[i + 1]],
                  &c = positions[indices[i + 2]];
      const Point pa = camera.project(a, center, extent, aspect);
      const Point pb = camera.project(b, center, extent, aspect);
      const Point pc = camera.project(c, center, extent, aspect);
      const double det = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1]);
      if (std::abs(det) < 1e-18)
        continue;
      const double u = ((pb[1] - pc[1]) * (x - pc[0]) + (pc[0] - pb[0]) * (y - pc[1])) / det;
      const double v = ((pc[1] - pa[1]) * (x - pc[0]) + (pa[0] - pc[0]) * (y - pc[1])) / det;
      const double w = 1 - u - v;
      if (std::min({u, v, w}) < -1e-9)
        continue;
      const double depth = u * pa[2] + v * pb[2] + w * pc[2];
      if (depth > front) {
        front = depth;
        hit = Point{render_origin[0] + u * a[0] + v * b[0] + w * c[0],
                    render_origin[1] + u * a[1] + v * b[1] + w * c[1],
                    render_origin[2] + u * a[2] + v * b[2] + w * c[2]};
      }
    }
    return hit;
  }
};
}  // namespace blender::ed::stk
