/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Window events, independent of GHOST headers.
 *
 * Coordinates are framebuffer pixels with the origin at the bottom-left of the window (the GPU
 * and Blender convention), so `x`/`y` can be compared directly with region rectangles and the
 * pixel-space projection of stk_gfx. On HiDPI outputs one logical point is `native_pixel_size`
 * pixels; the UI scale (see Window::ui_scale) already includes that factor.
 */
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace stk::wm {

class Window;

/** Key codes. Values mirror GHOST_TKey (checked with static_asserts in the implementation). */
enum class Key : int32_t {
  Unknown = -1,
  BackSpace = 0,
  Tab,
  Linefeed,
  Clear,
  Enter = 0x0D,
  Esc = 0x1B,
  Space = ' ',
  Quote = 0x27,
  Comma = ',',
  Minus = '-',
  Plus = '+',
  Period = '.',
  Slash = '/',
  Num0 = '0', Num1, Num2, Num3, Num4, Num5, Num6, Num7, Num8, Num9,
  Semicolon = ';',
  Equal = '=',
  A = 'A', B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z,
  LeftBracket = '[',
  RightBracket = ']',
  Backslash = 0x5C,
  AccentGrave = '`',
  LeftShift = 0x100,
  RightShift,
  LeftControl,
  RightControl,
  LeftAlt,
  RightAlt,
  /** Command on macOS, Windows key elsewhere. */
  LeftOS,
  RightOS,
  LeftHyper,
  RightHyper,
  GrLess,
  App,
  CapsLock,
  NumLock,
  ScrollLock,
  LeftArrow,
  RightArrow,
  UpArrow,
  DownArrow,
  PrintScreen,
  Pause,
  Insert,
  Delete,
  Home,
  End,
  PageUp,
  PageDown,
  Numpad0, Numpad1, Numpad2, Numpad3, Numpad4, Numpad5, Numpad6, Numpad7, Numpad8, Numpad9,
  NumpadPeriod,
  NumpadEnter,
  NumpadPlus,
  NumpadMinus,
  NumpadAsterisk,
  NumpadSlash,
  F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
  F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24,
  MediaPlay,
  MediaStop,
  MediaFirst,
  MediaLast,
};

/** Modifier bit mask (left and right keys are merged). */
enum Modifier : uint32_t {
  ModNone = 0,
  ModShift = 1 << 0,
  ModCtrl = 1 << 1,
  ModAlt = 1 << 2,
  /** Command on macOS, Windows key elsewhere. */
  ModOS = 1 << 3,
  ModHyper = 1 << 4,
};

enum class MouseButton : int8_t { None = -1, Left, Middle, Right, Button4, Button5, Button6, Button7 };

/** Standard cursor shapes (subset of GHOST's). */
enum class Cursor : uint8_t {
  Default,
  Text,
  Wait,
  Help,
  Crosshair,
  Move,
  HandPoint,
  HandOpen,
  HandClosed,
  /** Horizontal resize (splitter between side-by-side areas). */
  ResizeLeftRight,
  /** Vertical resize (splitter between stacked areas). */
  ResizeUpDown,
  Stop,
  Copy,
  ZoomIn,
  ZoomOut,
  Eyedropper,
};

enum class EventType : uint8_t {
  None,
  /** The window was resized; `width`/`height` are the new framebuffer size in pixels. */
  Resize,
  /** Content must be redrawn (exposed, restored, compositor request). */
  Expose,
  /** The UI scale changed (monitor DPI, native pixel size or user scale); `ui_scale` is new. */
  DpiChange,
  /** The user asked to close the window (title bar button, Alt+F4, ...). */
  Close,
  FocusIn,
  FocusOut,
  KeyDown,
  KeyUp,
  MouseMove,
  MouseDown,
  MouseUp,
  /** Mouse wheel (`wheel_x`/`wheel_y` in notches) or trackpad scroll (`precise`, in pixels). */
  Wheel,
  /** Trackpad pinch (`magnify`, relative change) on macOS / Wayland. */
  Magnify,
  /** IME composition started / updated / ended (see #ImeData). */
  ImeStart,
  ImeUpdate,
  ImeEnd,
  DragEnter,
  DragOver,
  DragLeave,
  /** Files or text dropped: `paths` (absolute file paths) or `text`. */
  Drop,
};

/**
 * IME state for ImeStart / ImeUpdate / ImeEnd (inline preedit on Wayland text-input-v3, macOS
 * and Windows; X11/XIM delivers committed text as KeyDown `text` only).
 */
struct ImeData {
  /** Committed text to insert (may be set on ImeUpdate). */
  std::string result;
  /** Current preedit (composition) string, displayed inline and not yet part of the text. */
  std::string composite;
  /** Caret position in `composite`, in bytes; -1 when unknown. */
  int cursor = -1;
  /** Highlighted (target) range in `composite`, in bytes; -1 when none. */
  int target_start = -1;
  int target_end = -1;
};

struct Event {
  EventType type = EventType::None;
  Window *window = nullptr;
  /** Milliseconds (GHOST clock). */
  uint64_t time_ms = 0;

  /** Cursor position in framebuffer pixels, origin bottom-left. */
  int x = 0;
  int y = 0;
  /** #Modifier bits held when the event happened. */
  uint32_t modifiers = ModNone;

  /* KeyDown / KeyUp. */
  Key key = Key::Unknown;
  /** Auto-repeat (KeyDown without a matching KeyUp). */
  bool is_repeat = false;
  /** UTF-8 text produced by the key press (empty for non-text keys). */
  std::string text;

  /* MouseDown / MouseUp. */
  MouseButton button = MouseButton::None;

  /* Wheel. */
  float wheel_x = 0.0f;
  float wheel_y = 0.0f;
  /** Trackpad (pixel deltas) rather than a notched wheel. */
  bool precise = false;
  /* Magnify. */
  float magnify = 0.0f;

  /* Resize / DpiChange: framebuffer size and UI scale after the change. */
  int width = 0;
  int height = 0;
  float ui_scale = 1.0f;

  /* ImeStart / ImeUpdate / ImeEnd. */
  ImeData ime;

  /* Drop (DragEnter/Over carry the position only). */
  std::vector<std::string> paths;

  bool is_pointer() const
  {
    return type == EventType::MouseMove || type == EventType::MouseDown ||
           type == EventType::MouseUp || type == EventType::Wheel ||
           type == EventType::Magnify || type == EventType::DragEnter ||
           type == EventType::DragOver || type == EventType::Drop;
  }
  bool is_keyboard() const
  {
    return type == EventType::KeyDown || type == EventType::KeyUp ||
           type == EventType::ImeStart || type == EventType::ImeUpdate ||
           type == EventType::ImeEnd;
  }
};

const char *event_type_name(EventType type);

}  // namespace stk::wm
