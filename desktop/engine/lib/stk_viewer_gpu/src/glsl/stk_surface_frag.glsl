/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Fragment stage shared by triangles, glyphs and lines: base colour (LUT bin, exact RGBA or solid),
 * headlight shading, or the (layer, element) id in the id pass. */

void main()
{
#ifdef STK_ID_PASS
  out_id = uvec2(uint(u_params.y), v_id);
#else
  vec4 base = stk_base_color(v_t, v_tf, v_rgba, v_rgbaf);
  vec3 color = base.rgb;
  if (stk_flag(STK_F_LIGHTING)) {
    vec3 n = v_nrm;
    if (stk_flag(STK_F_FLAT_SHADING) || !stk_flag(STK_F_HAS_NORMALS)) {
      n = cross(dFdx(v_eye), dFdy(v_eye));
    }
    color = stk_shade(color, n, v_eye);
  }
  float alpha = base.a * u_light.z;
  /* Premultiplied output (blended with GPU_BLEND_ALPHA_PREMULT). */
  out_color = vec4(color * alpha, alpha);
#endif
}
