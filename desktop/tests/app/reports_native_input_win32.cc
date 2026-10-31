/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_input.hh"
#ifndef NOMINMAX
#  define NOMINMAX
#endif
#include <windows.h>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>

namespace stk::reports_native_test {
namespace {
struct Target {
  HWND parent = nullptr, container = nullptr, child = nullptr;
  DWORD parent_thread = 0, child_thread = 0, child_pid = 0;
  POINT child_point{};
  document_preview::ViewBounds bounds{};
  int width = 0, height = 0;
  UINT dpi = 0;
};

UINT physical_dpi(HWND window)
{
  using ThreadContext = HANDLE (WINAPI *)();
  using WindowContext = HANDLE (WINAPI *)(HWND);
  using Awareness = int (WINAPI *)(HANDLE);
  using WindowDpi = UINT (WINAPI *)(HWND);
  const auto user32 = GetModuleHandleW(L"user32.dll");
  if (!user32) return 0;
  const auto thread_context = reinterpret_cast<ThreadContext>(GetProcAddress(user32, "GetThreadDpiAwarenessContext"));
  const auto window_context = reinterpret_cast<WindowContext>(GetProcAddress(user32, "GetWindowDpiAwarenessContext"));
  const auto awareness = reinterpret_cast<Awareness>(GetProcAddress(user32, "GetAwarenessFromDpiAwarenessContext"));
  const auto window_dpi = reinterpret_cast<WindowDpi>(GetProcAddress(user32, "GetDpiForWindow"));
  // 2 is the documented DPI_AWARENESS_PER_MONITOR_AWARE value: client/screen
  // coordinates must stay in physical pixels, including the browser descendant.
  if (!thread_context || !window_context || !awareness || !window_dpi ||
      awareness(thread_context()) != 2 || awareness(window_context(window)) != 2) return 0;
  return window_dpi(window);
}

bool exact_container(const Target &target)
{
  DWORD parent_pid = 0, container_pid = 0;
  const DWORD parent_thread = GetWindowThreadProcessId(target.parent, &parent_pid);
  const DWORD container_thread = GetWindowThreadProcessId(target.container, &container_pid);
  RECT client{}, rectangle{};
  POINT origin{};
  wchar_t class_name[256]{};
  constexpr LONG_PTR required_style = WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS;
  return IsWindow(target.parent) && parent_pid == GetCurrentProcessId() &&
         parent_thread == GetCurrentThreadId() && parent_thread == target.parent_thread &&
         IsWindowVisible(target.parent) && !IsIconic(target.parent) &&
         target.dpi != 0 && physical_dpi(target.parent) == target.dpi &&
         GetAncestor(target.parent, GA_ROOT) == target.parent &&
         GetClientRect(target.parent, &client) && client.left == 0 && client.top == 0 &&
         client.right == target.width && client.bottom == target.height &&
         IsWindow(target.container) && container_pid == GetCurrentProcessId() &&
         container_thread == parent_thread && GetParent(target.container) == target.parent &&
         GetAncestor(target.container, GA_ROOT) == target.parent &&
         IsWindowVisible(target.container) && IsWindowEnabled(target.container) &&
         GetClassNameW(target.container, class_name, 256) && lstrcmpiW(class_name, L"STATIC") == 0 &&
         (GetWindowLongPtrW(target.container, GWL_STYLE) & required_style) == required_style &&
         GetClientRect(target.container, &rectangle) && ClientToScreen(target.container, &origin) &&
         ScreenToClient(target.parent, &origin) && origin.x == target.bounds.x &&
         origin.y == target.height - target.bounds.y - target.bounds.height &&
         rectangle.left == 0 && rectangle.top == 0 && rectangle.right == target.bounds.width &&
         rectangle.bottom == target.bounds.height;
}

bool attached(const Target &target)
{
  DWORD pid = 0;
  const DWORD thread = GetWindowThreadProcessId(target.child, &pid);
  RECT rectangle{};
  return exact_container(target) && target.child != target.container && IsWindow(target.child) &&
         IsChild(target.container, target.child) && GetAncestor(target.child, GA_ROOT) == target.parent &&
         IsWindowVisible(target.child) && IsWindowEnabled(target.child) &&
         pid == target.child_pid && thread == target.child_thread &&
         physical_dpi(target.child) == target.dpi &&
         GetClientRect(target.child, &rectangle) && PtInRect(&rectangle, target.child_point);
}

bool resolve(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
             int width, int height, double nx, double ny, Target &target, std::string &error)
{
  auto fail = [&](const char *text) { error = text; return false; };
  if (handle.kind != wm::NativeWindowKind::Win32 || !handle.value || width <= 0 || height <= 0 ||
      !std::isfinite(nx) || !std::isfinite(ny) || nx < 0 || nx > 1 || ny < 0 || ny > 1 ||
      bounds.x < 0 || bounds.y < 0 || bounds.width <= 0 || bounds.height <= 0 ||
      bounds.width > width - bounds.x || bounds.height > height - bounds.y) {
    return fail("Invalid Win32 native input target/geometry/coordinates");
  }
  target.parent = static_cast<HWND>(handle.value);
  target.bounds = bounds; target.width = width; target.height = height;
  DWORD parent_pid = 0;
  target.parent_thread = GetWindowThreadProcessId(target.parent, &parent_pid);
  RECT client{};
  if (!IsWindow(target.parent) || parent_pid != GetCurrentProcessId() ||
      target.parent_thread != GetCurrentThreadId() || !IsWindowVisible(target.parent) ||
      IsIconic(target.parent) || GetAncestor(target.parent, GA_ROOT) != target.parent ||
      !GetClientRect(target.parent, &client) || client.left != 0 || client.top != 0 ||
      client.right != width || client.bottom != height) {
    return fail("Native input requires this process's exact visible top-level UI window");
  }
  target.dpi = physical_dpi(target.parent);
  if (!target.dpi) { return fail("Native input requires physical per-monitor DPI coordinates"); }
  const POINT parent_point{bounds.x + static_cast<LONG>(std::floor(nx * (bounds.width - 1))),
      height - bounds.y - bounds.height + static_cast<LONG>(std::floor(ny * (bounds.height - 1)))};
  target.container = ChildWindowFromPointEx(target.parent, parent_point,
      CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT);
  if (!target.container || target.container == target.parent || !exact_container(target)) {
    return fail("Native input container does not match this process's exact STATIC document viewport");
  }
  POINT screen_point = parent_point;
  if (!ClientToScreen(target.parent, &screen_point)) {
    return fail("Cannot convert native input client coordinates");
  }
  target.child = target.container;
  for (int depth = 0; depth < 32; ++depth) {
    POINT point = screen_point;
    if (!ScreenToClient(target.child, &point)) { return fail("Cannot convert native child coordinates"); }
    const HWND child = ChildWindowFromPointEx(target.child, point,
        CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT);
    if (!child) { return fail("Native input child lookup failed"); }
    if (child == target.child) { break; }
    if (GetParent(child) != target.child || !IsChild(target.container, child) ||
        GetAncestor(child, GA_ROOT) != target.parent || !IsWindowVisible(child) || !IsWindowEnabled(child)) {
      return fail("Native input target escaped the original STK child hierarchy");
    }
    target.child = child;
    if (depth == 31) { return fail("Native input child hierarchy exceeds the bounded lookup"); }
  }
  wchar_t class_name[256]{};
  if (target.child == target.container || !GetClassNameW(target.child, class_name, 256) ||
      lstrcmpiW(class_name, L"STATIC") == 0) {
    return fail("No native browser child HWND; refusing GHOST and STATIC input targets");
  }
  target.child_thread = GetWindowThreadProcessId(target.child, &target.child_pid);
  target.child_point = screen_point;
  if (!target.child_thread || !target.child_pid || !ScreenToClient(target.child, &target.child_point) ||
      target.child_point.x < std::numeric_limits<short>::min() ||
      target.child_point.x > std::numeric_limits<short>::max() ||
      target.child_point.y < std::numeric_limits<short>::min() ||
      target.child_point.y > std::numeric_limits<short>::max() || !attached(target)) {
    return fail("Native input child identity or signed 16-bit client point differs");
  }
  // WebView2 descendants may belong to another renderer process. Only the exact
  // child hierarchy of our verified own-process STATIC container is accepted.
  return true;
}

bool send(const Target &target, UINT message, WPARAM wparam, LPARAM lparam, std::string &error)
{
  if (!attached(target)) { error = "Native input child changed before message delivery"; return false; }
  DWORD_PTR ignored = 0;
  const auto began = std::chrono::steady_clock::now();
  // This API may return zero without setting LastError. Reset it immediately before the
  // unchanged bounded send, then capture it before any identity/geometry diagnostic API.
  SetLastError(ERROR_SUCCESS);
  // WebView2's cross-process key handler may synchronously ask its owning STA
  // to process a message. SMTO_BLOCK prevents that host-side dispatch; this is
  // a possible cause of the observed timeout with the exact child still attached.
  // Keep the same 2s deadline and synchronous result, but permit those sent
  // requests to run (SMTO_NORMAL). This does not post global keyboard input.
  const auto sent = SendMessageTimeoutW(target.child, message, wparam, lparam,
                                       SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT, 2000, &ignored);
  const DWORD send_error = GetLastError();
  if (!sent) {
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - began).count();
    DWORD observed_pid = 0;
    const DWORD observed_thread = GetWindowThreadProcessId(target.child, &observed_pid);
    const bool still_attached = attached(target);
    error = "SendMessageTimeout native input failed or timed out (message=" + std::to_string(message) +
        "); win32_error=" + std::to_string(send_error) + "; elapsed_ms=" + std::to_string(elapsed) +
        "; sender_pid=" + std::to_string(GetCurrentProcessId()) +
        "; sender_thread=" + std::to_string(GetCurrentThreadId()) +
        "; expected_parent_thread=" + std::to_string(target.parent_thread) +
        "; expected_child_pid=" + std::to_string(target.child_pid) +
        "; expected_child_thread=" + std::to_string(target.child_thread) +
        "; observed_child_pid=" + std::to_string(observed_pid) +
        "; observed_child_thread=" + std::to_string(observed_thread) +
        "; parent_hwnd=" + std::to_string(reinterpret_cast<uintptr_t>(target.parent)) +
        "; container_hwnd=" + std::to_string(reinterpret_cast<uintptr_t>(target.container)) +
        "; child_hwnd=" + std::to_string(reinterpret_cast<uintptr_t>(target.child)) +
        "; attached_after=" + (still_attached ? "true" : "false");
    return false;
  }
  if (!attached(target)) { error = "Native input child changed during message delivery"; return false; }
  return true;
}

bool post_mouse(const Target &target, UINT message, WPARAM wparam, LPARAM lparam,
                std::string &error)
{
  if (message != WM_MOUSEMOVE && message != WM_LBUTTONDOWN && message != WM_LBUTTONUP) {
    error = "Native mouse queue refuses an unsupported message"; return false;
  }
  if (!attached(target)) { error = "Native mouse child/DPI changed before enqueue"; return false; }
  // Mouse input is queued by Windows. A synchronous DOWN can wait inside a
  // control's modal/capture dispatch before the caller can send its matching UP.
  // Queue this fixed three-message sequence locally instead of blocking the host
  // STA message pump. Success here proves enqueue only; the caller's subsequent
  // observed media transition and OS pixels must still prove actual processing.
  SetLastError(ERROR_SUCCESS);
  const bool queued = PostMessageW(target.child, message, wparam, lparam) != FALSE;
  const DWORD queue_error = queued ? ERROR_SUCCESS : GetLastError();
  if (!queued) {
    error = "PostMessage native mouse enqueue failed (message=" + std::to_string(message) +
        "); win32_error=" + std::to_string(queue_error) +
        "; expected_child_pid=" + std::to_string(target.child_pid) +
        "; expected_child_thread=" + std::to_string(target.child_thread);
    return false;
  }
  if (!attached(target)) { error = "Native mouse child/DPI changed during enqueue"; return false; }
  return true;
}

std::string identity(const Target &target)
{
  return "; parent=" + std::to_string(reinterpret_cast<uintptr_t>(target.parent)) +
      "; exact_STATIC_container=" + std::to_string(reinterpret_cast<uintptr_t>(target.container)) +
      "; browser_descendant=" + std::to_string(reinterpret_cast<uintptr_t>(target.child)) +
      "; descendant_pid=" + std::to_string(target.child_pid) +
      "; descendant_thread=" + std::to_string(target.child_thread) +
      "; physical_dpi=" + std::to_string(target.dpi);
}

bool key_spec(wm::Key key, UINT &native_key, bool &extended)
{
  extended = false;
  switch (key) {
    case wm::Key::Space: native_key = VK_SPACE; return true;
    case wm::Key::Esc: native_key = VK_ESCAPE; return true;
    case wm::Key::LeftArrow: native_key = VK_LEFT; break;
    case wm::Key::RightArrow: native_key = VK_RIGHT; break;
    case wm::Key::Home: native_key = VK_HOME; break;
    case wm::Key::End: native_key = VK_END; break;
    default: return false;
  }
  extended = true;
  return true;
}
}  // namespace

bool NativeInput::click_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                                int width, int height, double nx, double ny,
                                std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  Target target;
  if (!resolve(handle, bounds, width, height, nx, ny, target, error)) { return false; }
  const LPARAM position = MAKELPARAM(static_cast<short>(target.child_point.x),
                                    static_cast<short>(target.child_point.y));
  if (!post_mouse(target, WM_MOUSEMOVE, 0, position, error) ||
      !post_mouse(target, WM_LBUTTONDOWN, MK_LBUTTON, position, error) ||
      !post_mouse(target, WM_LBUTTONUP, 0, position, error)) { return false; }
  delivery = "Win32 local PostMessage queued WM_MOUSEMOVE/WM_LBUTTONDOWN/WM_LBUTTONUP" + identity(target) +
      "; child_point=" + std::to_string(target.child_point.x) + "," + std::to_string(target.child_point.y) +
      "; normalized=" + std::to_string(nx) + "," + std::to_string(ny) +
      "; enqueue_only=true; consumption_requires_media_observation_and_OS_pixels; no global input injection";
  return true;
}

bool NativeInput::key_document(wm::NativeWindowHandle handle, document_preview::ViewBounds bounds,
                              int width, int height, wm::Key key,
                              std::string &delivery, std::string &error)
{
  delivery.clear(); error.clear();
  UINT native_key = 0;
  bool extended = false;
  if (!key_spec(key, native_key, extended)) { error = "Unsupported native report test key"; return false; }
  Target target;
  if (!resolve(handle, bounds, width, height, 0.5, 0.5, target, error)) { return false; }
  if (GetForegroundWindow() != target.parent) {
    error = "Native key delivery requires the exact foreground STK window";
    return false;
  }
  const bool different_thread = target.child_thread != GetCurrentThreadId();
  if (different_thread && !AttachThreadInput(GetCurrentThreadId(), target.child_thread, TRUE)) {
    error = "Cannot attach input queues for focus on the exact native browser child";
    return false;
  }
  // Attach only the verified target's thread, only while focusing and delivering
  // this pair. No global activation, posted keyboard input or SendInput is used.
  SetFocus(target.child);
  const bool focused = GetFocus() == target.child && attached(target);
  const UINT scan = MapVirtualKeyW(native_key, MAPVK_VK_TO_VSC);
  const LPARAM down = static_cast<LPARAM>(1u | ((scan & 0xffu) << 16) | (extended ? (1u << 24) : 0u));
  bool delivered = false;
  if (!focused) { error = "Native key focus did not remain on the exact browser child"; }
  else if (!scan) { error = "Native report key has no Windows scan code"; }
  else {
    delivered = send(target, WM_KEYDOWN, native_key, down, error) && GetFocus() == target.child &&
                send(target, WM_KEYUP, native_key, down | static_cast<LPARAM>(0xc0000000u), error);
    if (!delivered && error.empty()) { error = "Native key focus changed before keyUp"; }
  }
  if (different_thread && !AttachThreadInput(GetCurrentThreadId(), target.child_thread, FALSE)) {
    error = "Cannot detach native browser input queues after local key delivery";
    return false;
  }
  if (!delivered) { return false; }
  delivery = "Win32 local SendMessageTimeout WM_KEYDOWN/WM_KEYUP; sent host requests permitted" + identity(target) +
      "; native_key=" + std::to_string(native_key) + "; key=" + std::to_string(static_cast<int>(key)) +
      "; no global input injection";
  return true;
}
}  // namespace stk::reports_native_test
