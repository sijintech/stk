/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/viewer/picking.hh"

#include <vector>

namespace stk::viewer {

/** Area-weighted unit normals, as web smoothNormals (not VTK's equal-face weighting). Float64
 * accumulation keeps finite float32 geometry stable at large/small scales. Empty indices mean
 * consecutive triangles; incomplete, out-of-range or non-finite faces are ignored. Isolated,
 * degenerate and exactly cancelling vertices have zero normals. Output matches positions.size(). */
std::vector<float> smooth_normals(std::span<const float> positions,
                                  const IndexSpan &indices = std::span<const uint32_t>{});

}  // namespace stk::viewer
