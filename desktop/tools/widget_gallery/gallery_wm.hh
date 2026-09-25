/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * GPU helpers of the widget gallery: the demo texture for the image widget. (The event adapter,
 * clipboard and UI region moved to stk_wm: stk/wm/ui_bridge.hh.)
 */
#pragma once

#include <cstdint>

namespace stk::ui::gallery {

/** RGBA8 demo texture (ferroelectric-domain-like stripes); returns the handle for ImageSpec. */
uint64_t create_demo_texture(int w, int h);
void free_texture(uint64_t handle);

}  // namespace stk::ui::gallery
