/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Triangles (spec §6.1), drawn procedurally: 3 vertices per triangle read from storage buffers
 * (positions f32x3 relative to the layer origin, u32 or packed u16 indices, optional normals). */

uint stk_index(uint corner)
{
  if (!stk_flag(STK_F_HAS_INDEX)) {
    return corner;
  }
  if (stk_flag(STK_F_INDEX_U16)) {
    uint word = s_idx[corner >> 1u];
    return ((corner & 1u) == 0u) ? (word & 0xFFFFu) : (word >> 16u);
  }
  return s_idx[corner];
}

vec3 stk_vec3(uint i)
{
  return vec3(s_pos[3u * i], s_pos[3u * i + 1u], s_pos[3u * i + 2u]);
}

void main()
{
  uint corner = uint(gl_VertexID) + uint(u_params.z) * 3u;
  uint tri = corner / 3u;
  uint vi = stk_index(corner);
  vec3 p = stk_vec3(vi);
  gl_Position = u_mvp * vec4(p, 1.0);
  v_eye = (u_mv * vec4(p, 1.0)).xyz;
  v_nrm = vec3(0.0, 0.0, 1.0);
  if (stk_flag(STK_F_HAS_NORMALS)) {
    v_nrm = mat3(u_mv) * vec3(s_nrm[3u * vi], s_nrm[3u * vi + 1u], s_nrm[3u * vi + 2u]);
  }
  uint ci = stk_flag(STK_F_CELL) ? tri : vi;
  v_t = 0.0;
  v_tf = 0.0;
  v_rgba = vec4(1.0);
  v_rgbaf = vec4(1.0);
  int mode = stk_color_mode();
  if (mode == STK_COLOR_LUT) {
    v_t = stk_cval_float(ci);
    v_tf = v_t;
  }
  else if (mode == STK_COLOR_RGBA) {
    v_rgba = stk_cval_rgba(ci);
    v_rgbaf = v_rgba;
  }
  v_id = tri;
}
