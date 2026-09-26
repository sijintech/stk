/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/geometry.hh"

#include <cmath>

namespace stk::viewer {

std::vector<float> smooth_normals(std::span<const float> positions, const IndexSpan &indices)
{
  const size_t points = positions.size() / 3;
  const size_t index_count = std::visit([](auto span) { return span.size(); }, indices);
  const size_t count = index_count ? index_count : points;
  const auto index_at = [&](size_t i) -> size_t {
    return index_count ? std::visit([i](auto span) -> size_t { return span[i]; }, indices) : i;
  };
  const auto point = [&](size_t i) -> dvec3 {
    return {positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]};
  };
  std::vector<dvec3> sums(points);
  for (size_t i = 0; i + 2 < count; i += 3) {
    const size_t a = index_at(i), b = index_at(i + 1), c = index_at(i + 2);
    if (a >= points || b >= points || c >= points) {
      continue;
    }
    const dvec3 normal = cross(point(b) - point(a), point(c) - point(a));
    if (!std::isfinite(normal.x) || !std::isfinite(normal.y) || !std::isfinite(normal.z)) {
      continue;
    }
    sums[a] = sums[a] + normal;
    sums[b] = sums[b] + normal;
    sums[c] = sums[c] + normal;
  }
  std::vector<float> normals(positions.size(), 0.0f);
  for (size_t i = 0; i < points; i++) {
    const double length = std::hypot(sums[i].x, sums[i].y, sums[i].z);
    if (length > 0) {
      normals[i * 3] = float(sums[i].x / length);
      normals[i * 3 + 1] = float(sums[i].y / length);
      normals[i * 3 + 2] = float(sums[i].z / length);
    }
  }
  return normals;
}

}  // namespace stk::viewer
