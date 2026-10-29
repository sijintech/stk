/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_input.hh"

namespace stk::reports_native_test {
bool NativeInput::click_document(wm::NativeWindowHandle, document_preview::ViewBounds,
                                int, int, double, double,
                                std::string &delivery, std::string &error)
{
  delivery.clear();
  error = "Native report click delivery is unsupported on this platform";
  return false;
}

bool NativeInput::key_document(wm::NativeWindowHandle, document_preview::ViewBounds,
                              int, int, wm::Key, std::string &delivery, std::string &error)
{
  delivery.clear();
  error = "Native report key delivery is unsupported on this platform";
  return false;
}
}  // namespace stk::reports_native_test
