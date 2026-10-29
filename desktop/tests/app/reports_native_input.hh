/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/document/native_view.hh"
#include "stk/wm/event.hh"
#include <string>

namespace stk::reports_native_test {
/** Test-only delivery to this application's exact native document child.
 * The viewport is in parent framebuffer pixels with a bottom-left origin;
 * normalized click coordinates are top-left and inclusive in [0, 1].
 * Keys are limited to Space, LeftArrow, RightArrow, Home, End and Esc.
 * No global input queue is used. Success proves local event delivery only;
 * callers must independently prove playback/seek/pause with DOM and OS pixels.
 */
class NativeInput {
 public:
  bool click_document(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                      int framebuffer_width, int framebuffer_height,
                      double normalized_x, double normalized_y,
                      std::string &delivery, std::string &error);
  bool key_document(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                    int framebuffer_width, int framebuffer_height, wm::Key key,
                    std::string &delivery, std::string &error);
};
}  // namespace stk::reports_native_test
