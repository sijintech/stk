/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Small float64 vector/matrix types for the viewer model. Matrices are column-major (OpenGL/Blender
 * GPU convention): m[c][r], and transform column vectors (p' = M p). */

#include <array>
#include <cmath>
#include <cstddef>

namespace stk::viewer {

struct dvec3 {
  double x = 0, y = 0, z = 0;

  constexpr dvec3() = default;
  constexpr dvec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
  template<typename T> static constexpr dvec3 from(const T &a)
  {
    return {double(a[0]), double(a[1]), double(a[2])};
  }
  constexpr double operator[](size_t i) const
  {
    return i == 0 ? x : i == 1 ? y : z;
  }
  constexpr double &operator[](size_t i)
  {
    return i == 0 ? x : i == 1 ? y : z;
  }
  constexpr dvec3 operator+(const dvec3 &o) const
  {
    return {x + o.x, y + o.y, z + o.z};
  }
  constexpr dvec3 operator-(const dvec3 &o) const
  {
    return {x - o.x, y - o.y, z - o.z};
  }
  constexpr dvec3 operator-() const
  {
    return {-x, -y, -z};
  }
  constexpr dvec3 operator*(double s) const
  {
    return {x * s, y * s, z * s};
  }
  constexpr dvec3 operator/(double s) const
  {
    return {x / s, y / s, z / s};
  }
  constexpr dvec3 &operator+=(const dvec3 &o)
  {
    x += o.x;
    y += o.y;
    z += o.z;
    return *this;
  }
  constexpr dvec3 &operator-=(const dvec3 &o)
  {
    x -= o.x;
    y -= o.y;
    z -= o.z;
    return *this;
  }
  constexpr bool operator==(const dvec3 &) const = default;
  std::array<float, 3> to_float() const
  {
    return {float(x), float(y), float(z)};
  }
  std::array<double, 3> to_array() const
  {
    return {x, y, z};
  }
};

inline constexpr dvec3 operator*(double s, const dvec3 &v)
{
  return v * s;
}
inline constexpr double dot(const dvec3 &a, const dvec3 &b)
{
  return a.x * b.x + a.y * b.y + a.z * b.z;
}
inline constexpr dvec3 cross(const dvec3 &a, const dvec3 &b)
{
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline double length(const dvec3 &a)
{
  return std::hypot(a.x, a.y, a.z);
}
/** Unit vector (a zero vector stays zero, as web camera.ts `unit`). */
inline dvec3 normalize(const dvec3 &a)
{
  const double l = length(a);
  return l > 0 ? a / l : a;
}
inline bool is_finite(const dvec3 &a)
{
  return std::isfinite(a.x) && std::isfinite(a.y) && std::isfinite(a.z);
}

struct dvec4 {
  double x = 0, y = 0, z = 0, w = 0;
};

struct dmat4 {
  /* m[column][row] */
  std::array<std::array<double, 4>, 4> m{};

  static dmat4 identity();
  static dmat4 translation(const dvec3 &t);
  static dmat4 scale(const dvec3 &s);
  /** Rotation by `radians` about a unit axis (right-handed). */
  static dmat4 rotation(const dvec3 &axis, double radians);
  static dmat4 from_rows(const std::array<std::array<double, 4>, 4> &rows);

  dmat4 operator*(const dmat4 &o) const;
  dvec4 operator*(const dvec4 &v) const;
  dvec3 transform_point(const dvec3 &p) const; /* w = 1, with perspective divide */
  dvec3 transform_direction(const dvec3 &d) const;
  dmat4 inverted() const; /* identity-scaled garbage when singular: check determinant() first */
  dmat4 transposed() const;
  double determinant() const;
  /** Column-major float copy for GPU uniforms. */
  std::array<float, 16> to_float() const;
};

/** Right-handed view matrix (world -> eye, looking down -z). */
dmat4 look_at(const dvec3 &eye, const dvec3 &target, const dvec3 &up);
/** OpenGL clip space (z in [-1, 1]); fovy in degrees. */
dmat4 perspective(double fovy_deg, double aspect, double near_z, double far_z);
dmat4 orthographic(double left, double right, double bottom, double top, double near_z, double far_z);

/** Rotation that maps +x onto the unit direction d exactly as vtkGlyph3D: 180 degrees about (x + d)/2,
 * or about y when d is -x. */
dmat4 rotate_x_to(const dvec3 &unit_direction);

}  // namespace stk::viewer
