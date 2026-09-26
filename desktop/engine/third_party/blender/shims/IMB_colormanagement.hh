/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file STK shim: the two color-management helpers BLF uses when drawing into buffers.
 * STK buffers are sRGB (byte) or linear Rec.709 (float); there is no OCIO. */
#pragma once

#include <cmath>

/* Upstream pulls these in via colormanagement_inline.h; BLF relies on it. */
#include "BLI_math_color.h"
#include "BLI_math_vector.h"

namespace blender {
namespace ocio {
class ColorSpace;
}
using ColorSpace = ocio::ColorSpace;

inline void IMB_colormanagement_srgb_to_scene_linear_v3(float scene_linear[3], const float srgb[3])
{
  for (int i = 0; i < 3; i++) {
    const float c = srgb[i];
    scene_linear[i] = c <= 0.04045f ? c / 12.92f : std::pow((c + 0.055f) / 1.055f, 2.4f);
  }
}

/** Any non-null colorspace is treated as sRGB. */
inline void IMB_colormanagement_scene_linear_to_colorspace_v3(float pixel[3],
                                                              const ColorSpace * /*colorspace*/)
{
  for (int i = 0; i < 3; i++) {
    const float c = pixel[i];
    pixel[i] = c <= 0.0031308f ? c * 12.92f : 1.055f * std::pow(c, 1.0f / 2.4f) - 0.055f;
  }
}

}  // namespace blender
