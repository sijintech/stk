/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/glyph.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>

namespace stk::viewer {

namespace {

constexpr double kPi = std::numbers::pi;

using P3 = std::array<double, 3>;

std::array<float, 3> f3(const P3 &p)
{
  return {float(p[0]), float(p[1]), float(p[2])};
}

/* vtkCylinderSource (capping on) around +y: 2n side points (bottom y = +h/2 then top y = -h/2 per
 * angle), 2n cap points (bottom ring in order, top ring reversed); n quads then the two caps. */
void cylinder(int n, double radius, double height, const P3 &c, std::vector<P3> &points,
              std::vector<std::vector<uint32_t>> &polygons)
{
  const uint32_t base = uint32_t(points.size());
  const double angle = 2.0 * kPi / n;
  for (int i = 0; i < n; i++) {
    const double x = radius * std::cos(i * angle), z = -radius * std::sin(i * angle);
    points.push_back({x + c[0], 0.5 * height + c[1], z + c[2]});
    points.push_back({x + c[0], -0.5 * height + c[1], z + c[2]});
  }
  for (int i = 0; i < n; i++) {
    const uint32_t p0 = 2 * i, p1 = p0 + 1, p2 = (p1 + 2) % (2 * n), p3 = p2 - 1;
    polygons.push_back({base + p0, base + p1, base + p2, base + p3});
  }
  std::vector<P3> top(static_cast<size_t>(n));
  for (int i = 0; i < n; i++) {
    const double x = radius * std::cos(i * angle), z = -radius * std::sin(i * angle);
    points.push_back({x + c[0], 0.5 * height + c[1], z + c[2]});
    top[size_t(n - 1 - i)] = {x + c[0], -0.5 * height + c[1], z + c[2]};
  }
  for (const P3 &p : top) {
    points.push_back(p);
  }
  std::vector<uint32_t> cap0, cap1;
  for (int i = 0; i < n; i++) {
    cap0.push_back(base + uint32_t(2 * n + i));
    cap1.push_back(base + uint32_t(3 * n + i));
  }
  polygons.push_back(cap0);
  polygons.push_back(cap1);
}

/* vtkConeSource along +x centred on the origin (apex at +h/2), capping on. */
void cone(int n, double radius, double height, std::vector<P3> &points, std::vector<std::vector<uint32_t>> &polygons)
{
  const uint32_t base = uint32_t(points.size());
  const double angle = 2.0 * kPi / n;
  points.push_back({height / 2.0, 0.0, 0.0});
  for (int i = 0; i < n; i++) {
    points.push_back({-height / 2.0, radius * std::cos(i * angle), radius * std::sin(i * angle)});
  }
  std::vector<uint32_t> bottom(static_cast<size_t>(n));
  for (int i = 0; i < n; i++) {
    bottom[size_t(n - i - 1)] = base + uint32_t(i + 1);
  }
  polygons.push_back(bottom);
  for (int i = 0; i < n; i++) {
    uint32_t p2 = uint32_t(i + 2);
    if (p2 > uint32_t(n)) {
      p2 = 1;
    }
    polygons.push_back({base, base + uint32_t(i + 1), base + p2});
  }
}

}  // namespace

std::optional<GlyphShape> parse_glyph_shape(std::string_view name)
{
  for (GlyphShape shape : {GlyphShape::Arrow, GlyphShape::Cone, GlyphShape::Sphere, GlyphShape::Line, GlyphShape::Cube}) {
    if (glyph_shape_name(shape) == name) {
      return shape;
    }
  }
  return std::nullopt;
}

std::string_view glyph_shape_name(GlyphShape shape)
{
  switch (shape) {
    case GlyphShape::Arrow:
      return "arrow";
    case GlyphShape::Cone:
      return "cone";
    case GlyphShape::Sphere:
      return "sphere";
    case GlyphShape::Line:
      return "line";
    case GlyphShape::Cube:
      return "cube";
  }
  return "arrow";
}

std::vector<uint32_t> GlyphMesh::triangles() const
{
  std::vector<uint32_t> out;
  for (const auto &polygon : polygons) {
    for (size_t k = 1; k + 1 < polygon.size(); k++) {
      out.insert(out.end(), {polygon[0], polygon[k], polygon[k + 1]});
    }
  }
  return out;
}

void GlyphMesh::flat(std::vector<std::array<float, 3>> &positions, std::vector<std::array<float, 3>> &face_normals) const
{
  positions.clear();
  face_normals.clear();
  const std::vector<uint32_t> tris = triangles();
  for (size_t t = 0; t + 2 < tris.size(); t += 3) {
    const dvec3 a = dvec3::from(points[tris[t]]), b = dvec3::from(points[tris[t + 1]]), c = dvec3::from(points[tris[t + 2]]);
    const std::array<float, 3> n = normalize(cross(b - a, c - a)).to_float();
    for (int k = 0; k < 3; k++) {
      positions.push_back(points[tris[t + size_t(k)]]);
      face_normals.push_back(n);
    }
  }
}

GlyphMesh glyph_mesh(GlyphShape shape, int resolution, bool center)
{
  resolution = std::max(3, resolution);
  GlyphMesh mesh;
  std::vector<P3> points;
  switch (shape) {
    case GlyphShape::Arrow: {
      /* vtkArrowSource: tip length 0.35, tip radius 0.1, shaft radius 0.03. The shaft cylinder
       * (height 0.65, centre y = 0.325) is rotated by -90 degrees about z: (x, y, z) -> (y, -x, z);
       * the cone (height 0.35) is translated by 0.825 along x. */
      const double tip_length = 0.35;
      cylinder(resolution, 0.03, 1.0 - tip_length, {0.0, (1.0 - tip_length) * 0.5, 0.0}, points, mesh.polygons);
      for (P3 &p : points) {
        p = {p[1], -p[0], p[2]};
      }
      const size_t cone_start = points.size();
      cone(resolution, 0.1, tip_length, points, mesh.polygons);
      for (size_t i = cone_start; i < points.size(); i++) {
        points[i][0] += 1.0 - tip_length * 0.5;
      }
      break;
    }
    case GlyphShape::Cone: {
      /* Height 1, radius 0.25, centre (0.5, 0, 0), direction +x: vtkConeSource rotates by 180 degrees
       * about x ((x, y, z) -> (x, -y, -z)) and translates by the centre. */
      cone(resolution, 0.25, 1.0, points, mesh.polygons);
      for (P3 &p : points) {
        p = {p[0] + 0.5, -p[1], -p[2]};
      }
      break;
    }
    case GlyphShape::Sphere: {
      const int theta = resolution;
      const int phi = std::max(3, resolution / 2 + 1);
      const double r = 0.5;
      points.push_back({0.0, 0.0, r});
      points.push_back({0.0, 0.0, -r});
      mesh.normals.push_back({0.0f, 0.0f, 1.0f});
      mesh.normals.push_back({0.0f, 0.0f, -1.0f});
      const double delta_phi = kPi / (phi - 1);
      const double delta_theta = (360.0 / theta) * kPi / 180.0;
      for (int i = 0; i < theta; i++) {
        const double t = i * delta_theta;
        for (int j = 1; j < phi - 1; j++) {
          const double p = j * delta_phi;
          const double ring = r * std::sin(p);
          const P3 n{ring * std::cos(t), ring * std::sin(t), r * std::cos(p)};
          points.push_back(n);
          double norm = std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
          if (norm == 0.0) {
            norm = 1.0;
          }
          mesh.normals.push_back({float(n[0] / norm), float(n[1] / norm), float(n[2] / norm)});
        }
      }
      const uint32_t rows = uint32_t(phi - 2), poles = 2, base = rows * uint32_t(theta);
      for (uint32_t i = 0; i < uint32_t(theta); i++) {
        mesh.polygons.push_back({rows * i + poles, (rows * (i + 1) % base) + poles, 0});
      }
      const uint32_t offset = rows - 1 + poles;
      for (uint32_t i = 0; i < uint32_t(theta); i++) {
        mesh.polygons.push_back({rows * i + offset, poles - 1, ((rows * (i + 1)) % base) + offset});
      }
      for (uint32_t i = 0; i < uint32_t(theta); i++) {
        for (uint32_t j = 0; j + 1 < rows; j++) {
          const uint32_t p0 = rows * i + j + poles;
          const uint32_t p2 = ((rows * (i + 1) + j) % base) + poles + 1;
          mesh.polygons.push_back({p0, p0 + 1, p2});
          mesh.polygons.push_back({p0, p2, p2 - 1});
        }
      }
      break;
    }
    case GlyphShape::Line:
      points = {{0.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
      mesh.lines.push_back({0, 1});
      break;
    case GlyphShape::Cube: {
      /* vtkCubeSource: 4 points per face (normals per face), faces -x +x -y +y -z +z. */
      const auto face = [&](int axis, double sign, std::array<uint32_t, 4> order) {
        const uint32_t base = uint32_t(points.size());
        /* outer loop / inner loop axes of vtkCubeSource: -x/+x (y, z), -y/+y (x, z), -z/+z (y, x) */
        const int u = axis == 1 ? 0 : 1;
        const int v = axis == 2 ? 0 : 2;
        for (int i = 0; i < 2; i++) {
          for (int j = 0; j < 2; j++) {
            P3 p{};
            p[size_t(axis)] = 0.5 * sign;
            p[size_t(u)] = -0.5 + i;
            p[size_t(v)] = -0.5 + j;
            points.push_back(p);
            std::array<float, 3> n{0, 0, 0};
            n[size_t(axis)] = float(sign);
            mesh.normals.push_back(n);
          }
        }
        mesh.polygons.push_back({base + order[0], base + order[1], base + order[2], base + order[3]});
      };
      face(0, -1, {0, 1, 3, 2});
      face(0, 1, {0, 2, 3, 1});
      face(1, -1, {0, 2, 3, 1});
      face(1, 1, {0, 1, 3, 2});
      face(2, -1, {0, 2, 3, 1});
      face(2, 1, {0, 1, 3, 2});
      break;
    }
  }
  if (center && (shape == GlyphShape::Arrow || shape == GlyphShape::Cone || shape == GlyphShape::Line)) {
    for (P3 &p : points) {
      p[0] = double(float(p[0])) - 0.5;
    }
  }
  mesh.points.reserve(points.size());
  for (const P3 &p : points) {
    mesh.points.push_back(f3(p));
  }
  return mesh;
}

GlyphScale GlyphScale::from_json(const io::Json &value)
{
  GlyphScale scale;
  if (!value.is_object()) {
    return scale;
  }
  const std::string by = io::get_string(value, "by", "uniform");
  scale.by = by == "magnitude" ? ScaleMode::Magnitude : by == "attribute" ? ScaleMode::Attribute : ScaleMode::Uniform;
  const auto factor = value.find("factor");
  if (factor != value.end() && io::is_finite_number(*factor)) {
    scale.factor = factor->get<double>();
  }
  scale.attribute = io::get_string(value, "attribute");
  return scale;
}

std::vector<double> instance_scales(std::span<const float> directions,
                                    std::span<const float> scales,
                                    const GlyphScale &scale,
                                    std::span<const double> attribute,
                                    int attribute_components)
{
  const size_t n = directions.size() / 3;
  const double nan = std::numeric_limits<double>::quiet_NaN();
  std::vector<double> out(n, nan);
  for (size_t i = 0; i < n; i++) {
    const double magnitude = std::sqrt(double(directions[3 * i]) * directions[3 * i] +
                                       double(directions[3 * i + 1]) * directions[3 * i + 1] +
                                       double(directions[3 * i + 2]) * directions[3 * i + 2]);
    double s;
    if (!scales.empty()) {
      s = i < scales.size() ? scales[i] : nan;
    }
    else if (scale.by == ScaleMode::Magnitude) {
      s = scale.factor * magnitude;
    }
    else if (scale.by == ScaleMode::Attribute) {
      const size_t c = size_t(std::max(1, attribute_components));
      if ((i + 1) * c > attribute.size()) {
        s = nan;
      }
      else if (c == 1) {
        s = scale.factor * attribute[i];
      }
      else {
        double sum = 0;
        for (size_t k = 0; k < c; k++) {
          sum += attribute[i * c + k] * attribute[i * c + k];
        }
        s = scale.factor * std::sqrt(sum);
      }
    }
    else {
      s = scale.factor;
    }
    if (magnitude > 0 && std::isfinite(s)) {
      out[i] = std::abs(s);
    }
  }
  return out;
}

dmat4 instance_matrix(const dvec3 &position, const dvec3 &direction, double scale)
{
  return dmat4::translation(position) * rotate_x_to(direction) * dmat4::scale({scale, scale, scale});
}

}  // namespace stk::viewer
