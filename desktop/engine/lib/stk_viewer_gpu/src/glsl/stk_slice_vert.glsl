/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Slice image (spec §6.2): one quad over origin .. origin + u + v (relative to the layer origin)
 * with texel centres on the samples: the texture coordinate of sample i is (i + 0.5) / w. */

void main()
{
  uint k = uint(gl_VertexID) % 6u;
  vec2 st = vec2((k == 1u || k == 2u || k == 4u) ? 1.0 : 0.0, (k == 2u || k == 4u || k == 5u) ? 1.0 : 0.0);
  vec3 p = u_plane_origin.xyz + st.x * u_plane_u.xyz + st.y * u_plane_v.xyz;
  gl_Position = u_mvp * vec4(p, 1.0);
  v_eye = (u_mv * vec4(p, 1.0)).xyz;
  vec2 size = u_misc.xy;
  /* Sample (0,0) at st = 0 and (w-1, h-1) at st = 1. */
  v_uv = (st * (size - 1.0) + 0.5) / size;
}
