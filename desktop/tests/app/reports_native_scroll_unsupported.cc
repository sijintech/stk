/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_scroll.hh"
namespace stk::reports_native_test {
struct ScrollGuard::Impl {};
ScrollGuard::ScrollGuard() = default;
ScrollGuard::~ScrollGuard() = default;
bool ScrollGuard::check(std::string &error) const { error.clear(); return true; }
bool ScrollGuard::scroll_document(wm::NativeWindowHandle, document_preview::ViewBounds, int, int, int,
                     std::string &delivery, std::string &error)
{
  delivery.clear(); error = "Native report wheel delivery is unsupported on this platform";
  return false;
}
}  // namespace stk::reports_native_test
