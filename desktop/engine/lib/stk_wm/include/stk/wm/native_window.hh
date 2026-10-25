/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

namespace stk::wm {

enum class NativeWindowKind { Unsupported, Cocoa, Win32 };

/** Borrowed platform window, valid only while its owning wm::Window is alive.
 * Cocoa: NSWindow*. Win32: HWND. Callers must stay on the window's UI thread.
 * This is not a GHOST_IWindow pointer and confers no ownership.
 */
struct NativeWindowHandle {
  NativeWindowKind kind = NativeWindowKind::Unsupported;
  void *value = nullptr;
};

}  // namespace stk::wm
