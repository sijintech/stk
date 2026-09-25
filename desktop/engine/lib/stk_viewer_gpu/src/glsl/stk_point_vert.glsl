/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Points (spec §6.4) as quads, 6 vertices per point:
 *  - sprites: u_misc.x pixels square (render_as "points") or a shaded disc (render_as "spheres"
 *    without a world radius; VTK RenderPointsAsSpheres);
 *  - sphere impostors: world radius u_misc.y or s_rad[i] (STK_F_RADII); the fragment stage
 *    intersects the exact sphere and writes its depth.
 * u_misc.zw = target size in pixels. */

vec3 stk_vec3(uint i)
{
  return vec3(s_pos[3u * i], s_pos[3u * i + 1u], s_pos[3u * i + 2u]);
}

void main()
{
  uint pt = uint(gl_VertexID) / 6u + uint(u_params.z);
  uint k = uint(gl_VertexID) % 6u;
  vec2 corner = vec2((k == 1u || k == 2u || k == 4u) ? 1.0 : -1.0, (k == 2u || k == 4u || k == 5u) ? 1.0 : -1.0);
  vec3 p = stk_vec3(pt);
  vec3 center_eye = (u_mv * vec4(p, 1.0)).xyz;
  v_center = center_eye;
  v_corner = corner;
  if (stk_flag(STK_F_WORLD_SPHERES)) {
    float r = stk_flag(STK_F_RADII) ? abs(s_rad[pt]) : u_misc.y;
    v_radius = r;
    /* The silhouette of a sphere under perspective extends past r in the view plane: enlarge the
     * quad by the distance ratio (the fragment stage discards what misses). */
    float grow = 1.0;
    if (!stk_flag(STK_F_PARALLEL)) {
      float d = length(center_eye);
      grow = d > r * 1.0001 ? d / sqrt(d * d - r * r) : 4.0;
    }
    vec3 q = center_eye + vec3(corner * r * grow * 1.05, 0.0);
    v_eye = q;
    gl_Position = u_proj * vec4(q, 1.0);
  }
  else {
    v_radius = 0.0;
    vec4 c = u_mvp * vec4(p, 1.0);
    vec2 half_size = 0.5 * u_misc.zw;
    gl_Position = vec4(c.xy + corner * (0.5 * u_misc.x) / half_size * c.w, c.z, c.w);
    v_eye = center_eye;
  }
  v_t = 0.0;
  v_rgba = vec4(1.0);
  int mode = stk_color_mode();
  if (mode == STK_COLOR_LUT) {
    v_t = stk_cval_float(pt);
  }
  else if (mode == STK_COLOR_RGBA) {
    v_rgba = stk_cval_rgba(pt);
  }
  v_id = pt;
}
