/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_scroll.hh"
#ifndef NOMINMAX
#  define NOMINMAX
#endif
#include <windows.h>
#include <commctrl.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace stk::reports_native_test {
struct ScrollGuard::Impl {
  HWND container = nullptr, parent = nullptr;
  DWORD thread = GetCurrentThreadId();
  uint64_t escaped = 0;
  bool detach_failed = false;

  UINT_PTR id() const { return reinterpret_cast<UINT_PTR>(this); }
  bool bound() const
  {
    DWORD_PTR reference = 0;
    return container && GetWindowSubclass(container, intercept, id(), &reference) &&
           reference == reinterpret_cast<DWORD_PTR>(this);
  }
  static LRESULT CALLBACK intercept(HWND window, UINT message, WPARAM wparam, LPARAM lparam,
                                    UINT_PTR subclass, DWORD_PTR reference)
  {
    auto *self = reinterpret_cast<Impl *>(reference);
    if (message == WM_MOUSEWHEEL || message == WM_MOUSEHWHEEL) {
      ++self->escaped;
      // Never forward an unconsumed browser wheel to the GHOST parent. check() makes
      // this observable failure persistent across posted messages and later captures.
      return 0;
    }
    if (message == WM_NCDESTROY) {
      if (!RemoveWindowSubclass(window, intercept, subclass)) { self->detach_failed = true; }
      self->container = nullptr;
      self->parent = nullptr;
      // The owner outlives this callback; destruction of the native window does not
      // destroy refdata. A new preparation may bind a different container afterward.
    }
    return DefSubclassProc(window, message, wparam, lparam);
  }
};

ScrollGuard::ScrollGuard() : impl_(std::make_unique<Impl>()) {}
ScrollGuard::~ScrollGuard()
{
  if (impl_->escaped || impl_->detach_failed) {
    std::fputs("FAIL: Native scroll guard retained a propagation or removal failure\n", stderr);
    std::abort();
  }
  if (!impl_->container) { return; }
  // Exercise outlives normal window cleanup. On an earlier exception, explicitly
  // detach only our exact registration, not a reused HWND or somebody else's state.
  if (GetCurrentThreadId() != impl_->thread || !impl_->bound() ||
      !RemoveWindowSubclass(impl_->container, Impl::intercept, impl_->id())) {
    // Continuing would free refdata that an existing HWND might still call. A hard
    // test failure also prevents a capture_complete result becoming a false PASS.
    std::fputs("FAIL: Native scroll guard could not safely detach\n", stderr);
    std::abort();
  }
}
bool ScrollGuard::check(std::string &error) const
{
  error.clear();
  if (GetCurrentThreadId() != impl_->thread) { error = "Native scroll guard used from another thread"; }
  else if (impl_->escaped) {
    error = "Native wheel escaped browser content and was blocked at its container (count=" +
            std::to_string(impl_->escaped) + ")";
  }
  else if (impl_->detach_failed) { error = "Native scroll guard removal failed during window destruction"; }
  else if (impl_->container &&
           (!IsWindow(impl_->container) || GetParent(impl_->container) != impl_->parent ||
            GetAncestor(impl_->container, GA_ROOT) != impl_->parent || !impl_->bound())) {
    error = "Native scroll guard lost its exact container registration";
  }
  return error.empty();
}

bool ScrollGuard::scroll_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                     int framebuffer_width, int framebuffer_height, int direction,
                     std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  auto fail = [&](const char *text) { error = text; return false; };
  if (!check(error)) { return false; }
  if (handle.kind != wm::NativeWindowKind::Win32 || !handle.value ||
      (direction != -1 && direction != 1)) { return fail("Invalid Win32 wheel target"); }
  const HWND parent = static_cast<HWND>(handle.value);
  DWORD pid = 0;
  const DWORD thread = GetWindowThreadProcessId(parent, &pid);
  if (!IsWindow(parent) || pid != GetCurrentProcessId() || thread != GetCurrentThreadId() ||
      !IsWindowVisible(parent) || IsIconic(parent) || GetAncestor(parent, GA_ROOT) != parent) {
    return fail("Wheel delivery requires this process's visible top-level UI window");
  }
  RECT client{};
  // The evidence preflight establishes per-monitor DPI awareness. Reject any mismatch rather
  // than guessing a DPI multiplier or delivering an event to a different logical position.
  if (!GetClientRect(parent, &client) || client.right != framebuffer_width ||
      client.bottom != framebuffer_height || client.left != 0 || client.top != 0 ||
      bounds.x < 0 || bounds.y < 0 || bounds.width <= 0 || bounds.height <= 0 ||
      bounds.width > framebuffer_width - bounds.x || bounds.height > framebuffer_height - bounds.y) {
    return fail("Win32 wheel framebuffer/client geometry differs");
  }
  POINT screen_point{bounds.x + bounds.width / 2,
                     framebuffer_height - bounds.y - bounds.height / 2};
  if (!ClientToScreen(parent, &screen_point)) { return fail("Cannot convert wheel client coordinates"); }
  if (screen_point.x < std::numeric_limits<short>::min() || screen_point.x > std::numeric_limits<short>::max() ||
      screen_point.y < std::numeric_limits<short>::min() || screen_point.y > std::numeric_limits<short>::max()) {
    return fail("Wheel message coordinates exceed the signed 16-bit Windows contract");
  }
  const POINT client_point{bounds.x + bounds.width / 2,
                           framebuffer_height - bounds.y - bounds.height / 2};
  const HWND container = ChildWindowFromPointEx(parent, client_point,
      CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT);
  if (!container || container == parent) { return fail("No native document container at the viewport center"); }
  wchar_t class_name[256]{};
  DWORD container_pid = 0;
  const DWORD container_thread = GetWindowThreadProcessId(container, &container_pid);
  RECT rectangle{};
  POINT origin{};
  const auto style = GetWindowLongPtrW(container, GWL_STYLE);
  constexpr LONG_PTR required_style = WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS;
  // This is the production adapter's public STATIC host, not a guessed WebView2
  // private class. Require its complete own-window identity and exact viewport.
  if (container_pid != GetCurrentProcessId() || container_thread != thread ||
      GetParent(container) != parent || GetAncestor(container, GA_ROOT) != parent ||
      !IsWindowVisible(container) || !IsWindowEnabled(container) ||
      !GetClassNameW(container, class_name, 256) || lstrcmpiW(class_name, L"STATIC") != 0 ||
      (style & required_style) != required_style || !GetClientRect(container, &rectangle) ||
      !ClientToScreen(container, &origin) || !ScreenToClient(parent, &origin) ||
      origin.x != bounds.x || origin.y != framebuffer_height - bounds.y - bounds.height ||
      rectangle.left != 0 || rectangle.top != 0 || rectangle.right != bounds.width ||
      rectangle.bottom != bounds.height) {
    return fail("Native wheel container does not match this process's exact document viewport");
  }
  if (impl_->container && impl_->container != container) {
    return fail("Previous native scroll container is still alive; refusing to rebind");
  }
  if (!impl_->container) {
    if (!SetWindowSubclass(container, Impl::intercept, impl_->id(), reinterpret_cast<DWORD_PTR>(impl_.get()))) {
      return fail("Cannot install native wheel propagation guard");
    }
    impl_->container = container;
    impl_->parent = parent;
  }
  HWND target = container;
  for (int depth = 0; depth < 32; ++depth) {
    POINT local = screen_point;
    if (!ScreenToClient(target, &local)) { return fail("Cannot convert descendant wheel coordinates"); }
    const HWND child = ChildWindowFromPointEx(target, local,
        CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT);
    if (!child) { return fail("Native wheel descendant lookup failed"); }
    if (child == target) { break; }
    if (GetParent(child) != target || !IsChild(container, child) || GetAncestor(child, GA_ROOT) != parent ||
        !IsWindowVisible(child) || !IsWindowEnabled(child)) {
      return fail("Wheel target escaped the original STK child hierarchy");
    }
    target = child;
    if (depth == 31) { return fail("Native child hierarchy exceeds the bounded lookup"); }
  }
  if (target == container || !IsChild(container, target) ||
      !GetClassNameW(target, class_name, 256) || lstrcmpiW(class_name, L"STATIC") == 0) {
    return fail("No native document content descendant; refusing GHOST and STATIC containers");
  }
  // WebView2 can own descendants in its renderer process. Exact ancestry, not a global
  // WindowFromPoint search or a guessed class name, constrains this message's recipient.
  // A non-STATIC class does not prove consumption: the persistent container guard
  // intercepts default parent-chain forwarding, and OS pixels must prove page change.
  if (!check(error)) { return false; }
  if (!PostMessageW(target, WM_MOUSEWHEEL, MAKEWPARAM(0, short(direction * WHEEL_DELTA)),
                    MAKELPARAM(short(screen_point.x), short(screen_point.y)))) {
    return fail("PostMessage WM_MOUSEWHEEL failed");
  }
  DWORD target_pid = 0;
  const DWORD target_thread = GetWindowThreadProcessId(target, &target_pid);
  delivery = "Win32 PostMessage WM_MOUSEWHEEL; parent=" + std::to_string(reinterpret_cast<uintptr_t>(parent)) +
      "; guarded_container=" + std::to_string(reinterpret_cast<uintptr_t>(container)) +
      "; descendant=" + std::to_string(reinterpret_cast<uintptr_t>(target)) + "; pid=" + std::to_string(target_pid) +
      "; thread=" + std::to_string(target_thread) + "; screen_point=" + std::to_string(screen_point.x) + "," +
      std::to_string(screen_point.y) + "; delta=" + std::to_string(direction * WHEEL_DELTA);
  return true;
}
}  // namespace stk::reports_native_test
