/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/math.hh"

#include <numbers>

namespace stk::viewer {

dmat4 dmat4::identity()
{
  dmat4 r;
  for (int i = 0; i < 4; i++) {
    r.m[i][i] = 1.0;
  }
  return r;
}

dmat4 dmat4::translation(const dvec3 &t)
{
  dmat4 r = identity();
  r.m[3][0] = t.x;
  r.m[3][1] = t.y;
  r.m[3][2] = t.z;
  return r;
}

dmat4 dmat4::scale(const dvec3 &s)
{
  dmat4 r = identity();
  r.m[0][0] = s.x;
  r.m[1][1] = s.y;
  r.m[2][2] = s.z;
  return r;
}

dmat4 dmat4::rotation(const dvec3 &axis, double radians)
{
  const dvec3 a = normalize(axis);
  const double c = std::cos(radians), s = std::sin(radians), t = 1.0 - c;
  dmat4 r = identity();
  r.m[0][0] = t * a.x * a.x + c;
  r.m[0][1] = t * a.x * a.y + s * a.z;
  r.m[0][2] = t * a.x * a.z - s * a.y;
  r.m[1][0] = t * a.x * a.y - s * a.z;
  r.m[1][1] = t * a.y * a.y + c;
  r.m[1][2] = t * a.y * a.z + s * a.x;
  r.m[2][0] = t * a.x * a.z + s * a.y;
  r.m[2][1] = t * a.y * a.z - s * a.x;
  r.m[2][2] = t * a.z * a.z + c;
  return r;
}

dmat4 dmat4::from_rows(const std::array<std::array<double, 4>, 4> &rows)
{
  dmat4 r;
  for (int row = 0; row < 4; row++) {
    for (int col = 0; col < 4; col++) {
      r.m[col][row] = rows[row][col];
    }
  }
  return r;
}

dmat4 dmat4::operator*(const dmat4 &o) const
{
  dmat4 r;
  for (int c = 0; c < 4; c++) {
    for (int row = 0; row < 4; row++) {
      double s = 0;
      for (int k = 0; k < 4; k++) {
        s += m[k][row] * o.m[c][k];
      }
      r.m[c][row] = s;
    }
  }
  return r;
}

dvec4 dmat4::operator*(const dvec4 &v) const
{
  const double in[4] = {v.x, v.y, v.z, v.w};
  double out[4];
  for (int row = 0; row < 4; row++) {
    out[row] = m[0][row] * in[0] + m[1][row] * in[1] + m[2][row] * in[2] + m[3][row] * in[3];
  }
  return {out[0], out[1], out[2], out[3]};
}

dvec3 dmat4::transform_point(const dvec3 &p) const
{
  const dvec4 r = (*this) * dvec4{p.x, p.y, p.z, 1.0};
  if (r.w != 1.0 && r.w != 0.0) {
    return {r.x / r.w, r.y / r.w, r.z / r.w};
  }
  return {r.x, r.y, r.z};
}

dvec3 dmat4::transform_direction(const dvec3 &d) const
{
  const dvec4 r = (*this) * dvec4{d.x, d.y, d.z, 0.0};
  return {r.x, r.y, r.z};
}

dmat4 dmat4::transposed() const
{
  dmat4 r;
  for (int c = 0; c < 4; c++) {
    for (int row = 0; row < 4; row++) {
      r.m[c][row] = m[row][c];
    }
  }
  return r;
}

double dmat4::determinant() const
{
  const auto &a = m;
  const double s0 = a[0][0] * a[1][1] - a[1][0] * a[0][1];
  const double s1 = a[0][0] * a[1][2] - a[1][0] * a[0][2];
  const double s2 = a[0][0] * a[1][3] - a[1][0] * a[0][3];
  const double s3 = a[0][1] * a[1][2] - a[1][1] * a[0][2];
  const double s4 = a[0][1] * a[1][3] - a[1][1] * a[0][3];
  const double s5 = a[0][2] * a[1][3] - a[1][2] * a[0][3];
  const double c5 = a[2][2] * a[3][3] - a[3][2] * a[2][3];
  const double c4 = a[2][1] * a[3][3] - a[3][1] * a[2][3];
  const double c3 = a[2][1] * a[3][2] - a[3][1] * a[2][2];
  const double c2 = a[2][0] * a[3][3] - a[3][0] * a[2][3];
  const double c1 = a[2][0] * a[3][2] - a[3][0] * a[2][2];
  const double c0 = a[2][0] * a[3][1] - a[3][0] * a[2][1];
  return s0 * c5 - s1 * c4 + s2 * c3 + s3 * c2 - s4 * c1 + s5 * c0;
}

dmat4 dmat4::inverted() const
{
  const auto &a = m;
  const double s0 = a[0][0] * a[1][1] - a[1][0] * a[0][1];
  const double s1 = a[0][0] * a[1][2] - a[1][0] * a[0][2];
  const double s2 = a[0][0] * a[1][3] - a[1][0] * a[0][3];
  const double s3 = a[0][1] * a[1][2] - a[1][1] * a[0][2];
  const double s4 = a[0][1] * a[1][3] - a[1][1] * a[0][3];
  const double s5 = a[0][2] * a[1][3] - a[1][2] * a[0][3];
  const double c5 = a[2][2] * a[3][3] - a[3][2] * a[2][3];
  const double c4 = a[2][1] * a[3][3] - a[3][1] * a[2][3];
  const double c3 = a[2][1] * a[3][2] - a[3][1] * a[2][2];
  const double c2 = a[2][0] * a[3][3] - a[3][0] * a[2][3];
  const double c1 = a[2][0] * a[3][2] - a[3][0] * a[2][2];
  const double c0 = a[2][0] * a[3][1] - a[3][0] * a[2][1];
  const double det = s0 * c5 - s1 * c4 + s2 * c3 + s3 * c2 - s4 * c1 + s5 * c0;
  const double inv = det != 0.0 ? 1.0 / det : 0.0;
  dmat4 r;
  auto &b = r.m;
  b[0][0] = (a[1][1] * c5 - a[1][2] * c4 + a[1][3] * c3) * inv;
  b[0][1] = (-a[0][1] * c5 + a[0][2] * c4 - a[0][3] * c3) * inv;
  b[0][2] = (a[3][1] * s5 - a[3][2] * s4 + a[3][3] * s3) * inv;
  b[0][3] = (-a[2][1] * s5 + a[2][2] * s4 - a[2][3] * s3) * inv;
  b[1][0] = (-a[1][0] * c5 + a[1][2] * c2 - a[1][3] * c1) * inv;
  b[1][1] = (a[0][0] * c5 - a[0][2] * c2 + a[0][3] * c1) * inv;
  b[1][2] = (-a[3][0] * s5 + a[3][2] * s2 - a[3][3] * s1) * inv;
  b[1][3] = (a[2][0] * s5 - a[2][2] * s2 + a[2][3] * s1) * inv;
  b[2][0] = (a[1][0] * c4 - a[1][1] * c2 + a[1][3] * c0) * inv;
  b[2][1] = (-a[0][0] * c4 + a[0][1] * c2 - a[0][3] * c0) * inv;
  b[2][2] = (a[3][0] * s4 - a[3][1] * s2 + a[3][3] * s0) * inv;
  b[2][3] = (-a[2][0] * s4 + a[2][1] * s2 - a[2][3] * s0) * inv;
  b[3][0] = (-a[1][0] * c3 + a[1][1] * c1 - a[1][2] * c0) * inv;
  b[3][1] = (a[0][0] * c3 - a[0][1] * c1 + a[0][2] * c0) * inv;
  b[3][2] = (-a[3][0] * s3 + a[3][1] * s1 - a[3][2] * s0) * inv;
  b[3][3] = (a[2][0] * s3 - a[2][1] * s1 + a[2][2] * s0) * inv;
  return r;
}

std::array<float, 16> dmat4::to_float() const
{
  std::array<float, 16> out;
  for (int c = 0; c < 4; c++) {
    for (int row = 0; row < 4; row++) {
      out[size_t(c * 4 + row)] = float(m[c][row]);
    }
  }
  return out;
}

dmat4 look_at(const dvec3 &eye, const dvec3 &target, const dvec3 &up)
{
  const dvec3 f = normalize(target - eye);
  const dvec3 s = normalize(cross(f, up));
  const dvec3 u = cross(s, f);
  dmat4 r = dmat4::identity();
  r.m[0][0] = s.x;
  r.m[1][0] = s.y;
  r.m[2][0] = s.z;
  r.m[0][1] = u.x;
  r.m[1][1] = u.y;
  r.m[2][1] = u.z;
  r.m[0][2] = -f.x;
  r.m[1][2] = -f.y;
  r.m[2][2] = -f.z;
  r.m[3][0] = -dot(s, eye);
  r.m[3][1] = -dot(u, eye);
  r.m[3][2] = dot(f, eye);
  return r;
}

dmat4 perspective(double fovy_deg, double aspect, double near_z, double far_z)
{
  const double f = 1.0 / std::tan(fovy_deg * std::numbers::pi / 360.0);
  dmat4 r;
  r.m[0][0] = f / aspect;
  r.m[1][1] = f;
  r.m[2][2] = (far_z + near_z) / (near_z - far_z);
  r.m[2][3] = -1.0;
  r.m[3][2] = 2.0 * far_z * near_z / (near_z - far_z);
  return r;
}

dmat4 orthographic(double left, double right, double bottom, double top, double near_z, double far_z)
{
  dmat4 r = dmat4::identity();
  r.m[0][0] = 2.0 / (right - left);
  r.m[1][1] = 2.0 / (top - bottom);
  r.m[2][2] = -2.0 / (far_z - near_z);
  r.m[3][0] = -(right + left) / (right - left);
  r.m[3][1] = -(top + bottom) / (top - bottom);
  r.m[3][2] = -(far_z + near_z) / (far_z - near_z);
  return r;
}

dmat4 rotate_x_to(const dvec3 &d)
{
  if (d.y == 0.0 && d.z == 0.0) {
    if (d.x < 0) {
      return dmat4::rotation({0, 1, 0}, std::numbers::pi);
    }
    return dmat4::identity();
  }
  /* 180 degrees about n = (x + d)/|x + d| (vtkGlyph3D): R = 2 n n^T - I, no trigonometry. For d near -x,
   * 1 + d_x cancels; (d_y^2 + d_z^2) / (1 - d_x) is the same value without the cancellation. */
  const dvec3 u = normalize(d);
  const double a = u.x >= 0 ? 1.0 + u.x : (u.y * u.y + u.z * u.z) / (1.0 - u.x);
  const dvec3 n = normalize(dvec3{a, u.y, u.z});
  dmat4 r = dmat4::identity();
  const double v[3] = {n.x, n.y, n.z};
  for (int c = 0; c < 3; c++) {
    for (int row = 0; row < 3; row++) {
      r.m[c][row] = 2.0 * v[c] * v[row] - (c == row ? 1.0 : 0.0);
    }
  }
  return r;
}

}  // namespace stk::viewer
