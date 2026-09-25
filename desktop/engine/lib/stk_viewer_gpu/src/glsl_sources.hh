/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* GLSL sources of src/glsl/, embedded at build time (cmake/embed_glsl.cmake). */

namespace stk::viewer_gpu::glsl {

extern const char *const stk_common_lib;
extern const char *const stk_mesh_vert;
extern const char *const stk_glyph_vert;
extern const char *const stk_line_vert;
extern const char *const stk_surface_frag;
extern const char *const stk_point_vert;
extern const char *const stk_point_frag;
extern const char *const stk_slice_vert;
extern const char *const stk_slice_frag;
extern const char *const stk_volume_vert;
extern const char *const stk_volume_frag;

}  // namespace stk::viewer_gpu::glsl
