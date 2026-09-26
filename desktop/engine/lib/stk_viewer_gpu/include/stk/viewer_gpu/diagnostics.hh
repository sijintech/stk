/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Self-checks of stk_viewer_gpu (for tests and debugging).
 *
 * The shaders rely on no NaN or Inf semantics (Metal compiles them with fast math): every float
 * buffer and float texture the shaders read passes an upload gate that checks all values are
 * finite. NaN colour values are encoded as a finite sentinel, non-finite normals and radii become
 * 0, non-finite voxels become a finite "hole" value and glyphs with non-finite transforms are
 * dropped before upload, so the gate never fires in a correct build; when it does, the values are
 * replaced by 0, counted here and reported on stderr ("stk_viewer_gpu: non-finite ..."). */

#include <cstdint>

namespace stk::viewer_gpu {

/** Non-finite float values seen by the upload gate since the process started (0 when correct). */
uint64_t nonfinite_float_uploads();

}  // namespace stk::viewer_gpu
