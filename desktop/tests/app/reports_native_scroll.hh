/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/document/native_view.hh"
#include <memory>
#include <string>

namespace stk::reports_native_test {
/** Test-only local delivery of native wheel events, never global input injection.
 * The viewport uses ViewBounds: parent framebuffer pixels, bottom-left origin.
 * direction is -1 (down) or +1 (up). Success means delivery, not scrolling/painting;
 * the caller must prove the resulting page using independent OS pixels.
 * Keep this owner alive across event pumps and captures. On Windows it intercepts
 * unconsumed wheel messages at the exact document container before they reach GHOST.
 * check() must succeed after each pump and before accepting an OS image. The Cocoa
 * implementation has no Win32 parent-chain interception and check() is a no-op.
 */
class ScrollGuard {
 public:
  ScrollGuard();
  ~ScrollGuard();
  ScrollGuard(const ScrollGuard &) = delete;
  ScrollGuard &operator=(const ScrollGuard &) = delete;
  bool check(std::string &error) const;
  bool scroll_document(wm::NativeWindowHandle parent, document_preview::ViewBounds viewport,
                       int framebuffer_width, int framebuffer_height, int direction,
                       std::string &delivery, std::string &error);
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace stk::reports_native_test
