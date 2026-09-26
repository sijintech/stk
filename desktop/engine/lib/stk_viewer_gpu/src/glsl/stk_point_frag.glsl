/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Point sprites and sphere impostors (see stk_point_vert.glsl). */

void main()
{
  vec3 normal = vec3(0.0, 0.0, 1.0);
  vec3 surface = v_eye;
  if (stk_flag(STK_F_WORLD_SPHERES)) {
    /* Ray from the eye (perspective) or along -z (parallel) through this fragment's quad point. */
    vec3 ro = stk_flag(STK_F_PARALLEL) ? vec3(v_eye.xy, 0.0) : vec3(0.0);
    vec3 rd = stk_flag(STK_F_PARALLEL) ? vec3(0.0, 0.0, -1.0) : normalize(v_eye);
    vec3 oc = ro - v_center;
    float b = dot(oc, rd);
    float c = dot(oc, oc) - v_radius * v_radius;
    float disc = b * b - c;
    if (disc < 0.0) {
      discard;
    }
    float t = -b - sqrt(disc);
    vec3 hit = ro + rd * t;
    normal = (hit - v_center) / max(v_radius, 1e-30); /* radius > 0: zero radii give empty quads */
    surface = hit;
    vec4 clip = u_proj * vec4(hit, 1.0);
    gl_FragDepth = clamp(clip.z / clip.w * 0.5 + 0.5, 0.0, 1.0);
  }
  else {
    if (stk_flag(STK_F_ROUND_SPRITES)) {
      float d2 = dot(v_corner, v_corner);
      if (d2 > 1.0) {
        discard;
      }
      normal = vec3(v_corner, sqrt(1.0 - d2));
    }
    gl_FragDepth = gl_FragCoord.z;
  }
#ifdef STK_ID_PASS
  out_id = uvec2(uint(u_params.y), v_id);
#else
  vec4 base = stk_base_color(v_t, v_t, v_rgba, v_rgba, v_nan);
  vec3 color = base.rgb;
  bool shaded = stk_flag(STK_F_WORLD_SPHERES) || stk_flag(STK_F_ROUND_SPRITES);
  if (shaded) {
    color = stk_shade(color, normal, surface);
  }
  float alpha = base.a * u_light.z;
  out_color = vec4(color * alpha, alpha);
#endif
}
