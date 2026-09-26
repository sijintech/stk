/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Slice image texture (RGBA8 colours of the samples; nearest for labels, else linear). */

void main()
{
#ifdef STK_ID_PASS
  vec2 size = u_misc.xy;
  ivec2 ij = clamp(ivec2(floor(v_uv * size)), ivec2(0), ivec2(size) - 1);
  out_id = uvec2(uint(u_params.y), uint(ij.x) + uint(ij.y) * uint(size.x));
#else
  vec4 base = texture(s_img, v_uv);
  vec3 color = base.rgb;
  if (stk_flag(STK_F_LIGHTING)) {
    color = stk_shade(color, cross(dFdx(v_eye), dFdy(v_eye)), v_eye);
  }
  float alpha = base.a * u_light.z;
  out_color = vec4(color * alpha, alpha);
#endif
}
