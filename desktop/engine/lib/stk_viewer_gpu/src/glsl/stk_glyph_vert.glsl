/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Instanced glyphs (spec §6.5): the canonical glyph mesh (flat triangle soup: position, normal) is
 * drawn once per instance. s_inst holds 12 floats per instance: the position (relative to the layer
 * origin) and the rows of rotate(+x -> d/|d|) * scale(s) computed in float64 on the CPU
 * (stk::viewer::instance_matrix). */

void main()
{
  uint vi = uint(gl_VertexID);
  uint inst = uint(gl_InstanceID) + uint(u_params.z);
  vec3 gp = vec3(s_pos[6u * vi], s_pos[6u * vi + 1u], s_pos[6u * vi + 2u]);
  vec3 gn = vec3(s_pos[6u * vi + 3u], s_pos[6u * vi + 4u], s_pos[6u * vi + 5u]);
  uint b = 12u * inst;
  vec3 origin = vec3(s_inst[b], s_inst[b + 1u], s_inst[b + 2u]);
  vec3 r0 = vec3(s_inst[b + 3u], s_inst[b + 4u], s_inst[b + 5u]);
  vec3 r1 = vec3(s_inst[b + 6u], s_inst[b + 7u], s_inst[b + 8u]);
  vec3 r2 = vec3(s_inst[b + 9u], s_inst[b + 10u], s_inst[b + 11u]);
  vec3 p = origin + vec3(dot(r0, gp), dot(r1, gp), dot(r2, gp));
  /* Rotation times a uniform scale: the normal transforms like a direction. */
  vec3 n = vec3(dot(r0, gn), dot(r1, gn), dot(r2, gn));
  gl_Position = u_mvp * vec4(p, 1.0);
  v_eye = (u_mv * vec4(p, 1.0)).xyz;
  v_nrm = mat3(u_mv) * n;
  v_t = 0.0;
  v_tf = 0.0;
  v_rgba = vec4(1.0);
  v_rgbaf = vec4(1.0);
  v_nan = 0;
  int mode = stk_color_mode();
  if (mode == STK_COLOR_LUT) {
    v_t = stk_cval_float(inst);
    v_tf = v_t;
    v_nan = stk_cval_nan(inst) ? (STK_NAN_SMOOTH | STK_NAN_FLAT) : 0;
  }
  else if (mode == STK_COLOR_RGBA) {
    v_rgba = stk_cval_rgba(inst);
    v_rgbaf = v_rgba;
  }
  v_id = inst;
}
