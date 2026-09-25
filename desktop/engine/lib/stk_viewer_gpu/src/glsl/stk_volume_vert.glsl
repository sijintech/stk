/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Volume ray marching: one full-screen triangle; rays are rebuilt from the interpolated NDC. */

void main()
{
  uint k = uint(gl_VertexID) % 3u;
  vec2 p = vec2(k == 1u ? 3.0 : -1.0, k == 2u ? 3.0 : -1.0);
  v_ndc = p;
  gl_Position = vec4(p, 0.0, 1.0);
}
