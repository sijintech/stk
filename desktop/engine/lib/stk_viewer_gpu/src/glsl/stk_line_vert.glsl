/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Wide lines (spec §6.3): each segment (a pair in s_idx) is expanded procedurally into a quad of
 * u_misc.x pixels across, perpendicular to the segment in screen space (u_misc.zw = target size in
 * pixels). Endpoints behind the near plane are moved onto it before the screen-space expansion. */

uint stk_index(uint i)
{
  if (!stk_flag(STK_F_HAS_INDEX)) {
    return i;
  }
  if (stk_flag(STK_F_INDEX_U16)) {
    uint word = s_idx[i >> 1u];
    return ((i & 1u) == 0u) ? (word & 0xFFFFu) : (word >> 16u);
  }
  return s_idx[i];
}

vec3 stk_vec3(uint i)
{
  return vec3(s_pos[3u * i], s_pos[3u * i + 1u], s_pos[3u * i + 2u]);
}

void main()
{
  uint seg = uint(gl_VertexID) / 6u + uint(u_params.z);
  uint k = uint(gl_VertexID) % 6u;
  /* Two triangles: (a-, b-, b+), (a-, b+, a+). */
  bool at_b = (k == 1u || k == 2u || k == 4u);
  float side = (k == 2u || k == 4u || k == 5u) ? 1.0 : -1.0;
  uint ia = stk_index(2u * seg), ib = stk_index(2u * seg + 1u);
  vec3 pa = stk_vec3(ia), pb = stk_vec3(ib);
  vec4 ca = u_mvp * vec4(pa, 1.0);
  vec4 cb = u_mvp * vec4(pb, 1.0);
  /* Clip against w = epsilon so the perspective divide stays valid. */
  const float eps = 1e-6;
  if (ca.w < eps && cb.w >= eps) {
    ca = mix(ca, cb, (eps - ca.w) / (cb.w - ca.w));
  }
  else if (cb.w < eps && ca.w >= eps) {
    cb = mix(cb, ca, (eps - cb.w) / (ca.w - cb.w));
  }
  vec2 half_size = 0.5 * u_misc.zw;
  vec2 sa = ca.xy / max(ca.w, eps) * half_size;
  vec2 sb = cb.xy / max(cb.w, eps) * half_size;
  vec2 dir = sb - sa;
  float len = length(dir);
  dir = len > 1e-12 ? dir / len : vec2(1.0, 0.0);
  vec2 normal = vec2(-dir.y, dir.x);
  vec4 c = at_b ? cb : ca;
  vec2 offset = normal * (side * 0.5 * u_misc.x) / half_size;
  gl_Position = vec4(c.xy + offset * c.w, c.z, c.w);
  vec3 p = at_b ? pb : pa;
  v_eye = (u_mv * vec4(p, 1.0)).xyz;
  v_nrm = vec3(0.0, 0.0, 1.0);
  uint ci = stk_flag(STK_F_CELL) ? seg : (at_b ? ib : ia);
  uint cflat = stk_flag(STK_F_CELL) ? seg : ia;
  v_t = 0.0;
  v_tf = 0.0;
  v_rgba = vec4(1.0);
  v_rgbaf = vec4(1.0);
  v_nan = 0;
  int mode = stk_color_mode();
  if (mode == STK_COLOR_LUT) {
    v_t = stk_cval_float(ci);
    v_tf = stk_cval_float(cflat);
    bool any_nan = stk_flag(STK_F_CELL) ? stk_cval_nan(seg) : (stk_cval_nan(ia) || stk_cval_nan(ib));
    v_nan = (any_nan ? STK_NAN_SMOOTH : 0) | (stk_cval_nan(cflat) ? STK_NAN_FLAT : 0);
  }
  else if (mode == STK_COLOR_RGBA) {
    v_rgba = stk_cval_rgba(ci);
    v_rgbaf = stk_cval_rgba(cflat);
  }
  v_id = seg;
}
