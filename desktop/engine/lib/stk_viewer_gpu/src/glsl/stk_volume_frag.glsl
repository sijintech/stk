/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Ray-marched volume (spec §6.6; web/src/volume.ts, vtkVolumeMapper):
 *  - the ray of this pixel in eye space (u_inv_proj), clipped by the grid box in continuous voxel
 *    index space (u_eye_to_index; samples at integer indices, box [0, n-1]) and by the opaque scene
 *    depth (s_depth);
 *  - samples every u_vol.w eye units; the stored value (texture value * u_vol2.w) indexes the
 *    transfer-function LUT over the stored domain [u_vol2.y, u_vol2.z] (colour, and opacity per unit
 *    distance u_vol2.x = min(spacing), corrected per step: 1 - (1 - a)^(step / unit));
 *  - front-to-back compositing into premultiplied colour.
 * No IEEE infinities or NaN (Metal fast math): ray directions parallel to a box face use a large
 * finite reciprocal, and non-finite voxels arrive as a finite sentinel far below the stored domain
 * (scene.cc) and are skipped (transparent). */

void main()
{
  vec4 near_h = u_inv_proj * vec4(v_ndc, -1.0, 1.0);
  vec4 far_h = u_inv_proj * vec4(v_ndc, 1.0, 1.0);
  vec3 ro = near_h.xyz / near_h.w;
  vec3 rf = far_h.xyz / far_h.w;
  vec3 rd = rf - ro;
  float t_scene = length(rd);
  rd /= max(t_scene, 1e-30);
  float depth = texelFetch(s_depth, ivec2(gl_FragCoord.xy), 0).r;
  if (depth < 1.0) {
    vec4 hit_h = u_inv_proj * vec4(v_ndc, depth * 2.0 - 1.0, 1.0);
    t_scene = dot(hit_h.xyz / hit_h.w - ro, rd);
  }
  vec3 dims = u_vol.xyz;
  vec3 io = (u_eye_to_index * vec4(ro, 1.0)).xyz;
  vec3 id = (u_eye_to_index * vec4(rd, 0.0)).xyz;
  vec3 box_lo = mix(vec3(0.0), vec3(-0.5), vec3(lessThan(dims, vec3(1.5))));
  vec3 box_hi = max(dims - 1.0, vec3(0.5) * vec3(lessThan(dims, vec3(1.5))));
  /* Components near zero get a tiny signed finite value, so the slab test never divides by zero. */
  vec3 id_safe = mix(id, mix(vec3(1e-20), vec3(-1e-20), lessThan(id, vec3(0.0))), lessThan(abs(id), vec3(1e-20)));
  vec3 inv = 1.0 / id_safe;
  vec3 ta = (box_lo - io) * inv;
  vec3 tb = (box_hi - io) * inv;
  vec3 tmin3 = min(ta, tb);
  vec3 tmax3 = max(ta, tb);
  float t0 = max(max(tmin3.x, tmin3.y), max(tmin3.z, 0.0));
  float t1 = min(min(tmax3.x, tmax3.y), min(tmax3.z, t_scene));
  if (!(t1 > t0)) {
    discard;
  }
  float step_len = u_vol.w;
  float unit = u_vol2.x;
  float lo = u_vol2.y, hi = u_vol2.z;
  float inv_range = hi > lo ? 1.0 / (hi - lo) : 0.0;
  /* Below this stored value (u_light.w) a sample is a non-finite voxel (a hole); data values are
   * >= lo, holes are stored far below it. */
  float hole = u_light.w;
  vec4 acc = vec4(0.0);
  float t = t0 + 0.5 * step_len;
  for (int i = 0; i < 16384 && t < t1; i++, t += step_len) {
    vec3 p = io + id * t;
    float stored = texture(s_vol, (p + 0.5) / dims).r * u_vol2.w;
    if (stored < hole) {
      continue;
    }
    float u = (stored - lo) * inv_range;
    vec4 tf = texture(s_tf, vec2(u, 0.5));
    float a = clamp(tf.a, 0.0, 1.0);
    if (a > 0.0) {
      float a_step = 1.0 - pow(1.0 - min(a, 0.999999), step_len / unit);
      acc.rgb += (1.0 - acc.a) * a_step * tf.rgb;
      acc.a += (1.0 - acc.a) * a_step;
      if (acc.a > 0.995) {
        break;
      }
    }
  }
  out_color = acc * u_light.z;
}
