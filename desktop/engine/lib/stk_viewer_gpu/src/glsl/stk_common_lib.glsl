/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Shared by every stk_viewer_gpu 3D program (prepended to each stage's source).
 *
 * Push constants declared by the create infos (see shaders.cc):
 *   u_mvp, u_mv    : float32 casts of the camera-relative float64 matrices (stk_viewer_model)
 *   u_solid        : solid colour (rgba)
 *   u_light        : ambient, diffuse, opacity, unused
 *   u_params       : flags, layer tag (id pass), element base (id pass), program-specific
 * Storage buffer s_cval holds one value per point or element: the float bits of the normalized LUT
 * coordinate t (colour mode LUT) or packed RGBA8 (colour mode RGBA). */

#define STK_COLOR_MODE_MASK 3
#define STK_COLOR_SOLID 0
#define STK_COLOR_LUT 1
#define STK_COLOR_RGBA 2
#define STK_F_CELL 4
#define STK_F_FLAT_VALUE 8
#define STK_F_LIGHTING 16
#define STK_F_INDEX_U16 32
#define STK_F_HAS_INDEX 64
#define STK_F_HAS_NORMALS 128
#define STK_F_FLAT_SHADING 256
#define STK_F_PARALLEL 512
#define STK_F_RADII 1024
#define STK_F_WORLD_SPHERES 2048
#define STK_F_ROUND_SPRITES 4096

bool stk_flag(int bit)
{
  return (u_params.x & bit) != 0;
}

int stk_color_mode()
{
  return u_params.x & STK_COLOR_MODE_MASK;
}

#ifndef STK_NO_COLOR_LIB
/* Exact spec §5 binning of a normalized coordinate t = (v - lo) / (hi - lo) into the model's
 * 259-texel texture [below, lut 0..255, above, nan] (ContinuousColormap::texture / texel). */
int stk_lut_texel(float t)
{
  if (isnan(t)) {
    return 258;
  }
  if (t < 0.0) {
    return 0;
  }
  if (t > 1.0) {
    return 257;
  }
  return 1 + min(255, int(floor(t * 256.0)));
}

/* Base colour of a fragment from the interpolated (smooth) and per-element (flat) values. */
vec4 stk_base_color(float t_smooth, float t_flat, vec4 rgba_smooth, vec4 rgba_flat)
{
  int mode = stk_color_mode();
  bool use_flat = stk_flag(STK_F_CELL) || stk_flag(STK_F_FLAT_VALUE);
  if (mode == STK_COLOR_LUT) {
    return texelFetch(s_lut, ivec2(stk_lut_texel(use_flat ? t_flat : t_smooth), 0), 0);
  }
  if (mode == STK_COLOR_RGBA) {
    return use_flat ? rgba_flat : rgba_smooth;
  }
  return u_solid;
}

#endif

/* Lighting in eye space, as the offscreen reference (suan/render/offscreen.py):
 *  - "three_point": vtkLightKit defaults (camera lights; key 0.75 at elevation 50, azimuth 10, warm;
 *    fill key/3 at -75, -10, cool; two back lights key/3.5 at 0, +-110; headlight key/3), scaled by
 *    u_light.y (view.lighting.intensity);
 *  - "headlight": VTK's automatic headlight (intensity u_light.y);
 * diffuse only (vtkProperty defaults: ambient u_light.x = 0, diffuse 1, specular 0), two-sided (the
 * normal is turned towards the viewer). */
vec3 stk_shade(vec3 color, vec3 normal_eye, vec3 eye_pos)
{
  if (!stk_flag(STK_F_LIGHTING)) {
    return color;
  }
  vec3 n = normalize(normal_eye);
  vec3 to_eye = stk_flag(STK_F_PARALLEL) ? vec3(0.0, 0.0, 1.0) : normalize(-eye_pos);
  if (dot(n, to_eye) < 0.0) {
    n = -n;
  }
  vec3 light = vec3(0.0);
  if (u_light.w > 0.5) {
    const vec3 key_dir = vec3(0.11161889704894966, 0.766044443118978, 0.6330222215594891);
    const vec3 fill_dir = vec3(-0.044943455527547777, -0.9659258262890683, 0.25488700224417876);
    const vec3 back1_dir = vec3(0.9396926207859084, 0.0, -0.3420201433256687);
    const vec3 back2_dir = vec3(-0.9396926207859084, 0.0, -0.3420201433256687);
    const vec3 key_color = vec3(1.0, 0.97232, 0.90222);
    const vec3 fill_color = vec3(0.90824, 0.93314, 1.0);
    const vec3 neutral = vec3(0.9998);
    light += 0.75 * key_color * max(dot(n, key_dir), 0.0);
    light += 0.25 * fill_color * max(dot(n, fill_dir), 0.0);
    light += (0.75 / 3.5) * neutral * (max(dot(n, back1_dir), 0.0) + max(dot(n, back2_dir), 0.0));
    light += 0.25 * neutral * max(n.z, 0.0);
    light *= u_light.y;
  }
  else {
    light = vec3(u_light.y * max(n.z, 0.0));
  }
  return color * (vec3(u_light.x) + light);
}

#ifndef STK_NO_COLOR_LIB
/* The value of point/element i in s_cval. */
float stk_cval_float(uint i)
{
  return uintBitsToFloat(s_cval[i]);
}

vec4 stk_cval_rgba(uint i)
{
  return unpackUnorm4x8(s_cval[i]);
}
#endif
