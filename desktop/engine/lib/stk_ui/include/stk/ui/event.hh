/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Toolkit input events: a plain struct the window manager fills from GHOST (or tests fill by
 * hand). Coordinates are window pixels, origin top-left. Time is seconds on any monotonic clock.
 *
 * Adapter point (WP1/WP3, stk_wm): one ui::Event per GHOST event —
 *   GHOST_kEventCursorMove           -> MouseMove   (screenToClient, flip y if needed)
 *   GHOST_kEventButtonDown/Up        -> MouseDown/MouseUp (button: Left/Middle/Right)
 *   GHOST_kEventWheel / Trackpad     -> Wheel (wheel_y > 0 scrolls up / away from the user)
 *   GHOST_kEventKeyDown/Up           -> KeyDown/KeyUp (Key values equal GHOST_kKeyA.. for letters and
 *                                       digits); plus TextInput with utf8_buf when it is printable
 *                                       and no Ctrl/Alt/Super is held
 *   GHOST_kEventImeComposition       -> ImePreedit (composite text, cursor_position in bytes)
 *   GHOST_kEventImeCompositionEnd    -> ImeCommit (result text; may be empty = cancelled)
 *   GHOST_kEventWindowDeactivate     -> FocusLost
 *   timers / redraw                  -> Tick (lets tooltips and toasts advance)
 */
#pragma once

#include <cstdint>
#include <string>

#include "stk/ui/geom.hh"

namespace stk::ui {

enum class EventType : uint8_t {
  MouseMove,
  MouseDown,
  MouseUp,
  Wheel,
  KeyDown,
  KeyUp,
  TextInput,
  ImePreedit,
  ImeCommit,
  FocusLost,
  Tick,
};

enum class MouseButton : uint8_t { None, Left, Middle, Right };

/** Letters and digits use their ASCII upper-case code (as GHOST_TKey does). */
enum class Key : uint16_t {
  None = 0,
  Space = ' ',
  Num0 = '0', Num1, Num2, Num3, Num4, Num5, Num6, Num7, Num8, Num9,
  A = 'A', B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z,
  Tab = 256,
  Enter,
  Escape,
  Backspace,
  Delete,
  Insert,
  Left,
  Right,
  Up,
  Down,
  Home,
  End,
  PageUp,
  PageDown,
  F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
};

enum Modifier : uint8_t {
  MOD_NONE = 0,
  MOD_SHIFT = 1 << 0,
  MOD_CTRL = 1 << 1,
  MOD_ALT = 1 << 2,
  MOD_SUPER = 1 << 3, /**< Cmd on macOS, Windows/"OS" key elsewhere. */
};

struct Event {
  EventType type = EventType::Tick;
  double time = 0.0;
  Vec2 pos;          /**< Pointer position (all pointer events; also kept for keys). */
  MouseButton button = MouseButton::None;
  float wheel_x = 0.0f;
  float wheel_y = 0.0f; /**< Positive = scroll up (content moves down). */
  Key key = Key::None;
  uint8_t mods = MOD_NONE;
  bool repeat = false;
  /** TextInput / ImeCommit: UTF-8 text. ImePreedit: the composition string. */
  std::string text;
  /** ImePreedit: caret byte offset inside `text`. */
  int ime_cursor = -1;

  static Event mouse_move(Vec2 p, double t = 0.0);
  static Event mouse_down(Vec2 p, MouseButton b = MouseButton::Left, double t = 0.0, uint8_t mods = 0);
  static Event mouse_up(Vec2 p, MouseButton b = MouseButton::Left, double t = 0.0, uint8_t mods = 0);
  static Event wheel(Vec2 p, float dy, double t = 0.0, uint8_t mods = 0);
  static Event key_down(Key k, uint8_t mods = 0, double t = 0.0);
  static Event key_up(Key k, uint8_t mods = 0, double t = 0.0);
  static Event text_input(std::string s, double t = 0.0);
  static Event ime_preedit(std::string s, int cursor, double t = 0.0);
  static Event ime_commit(std::string s, double t = 0.0);
  static Event tick(double t);
};

/** What handling an event did. `redraw` asks the host to rebuild and repaint (on demand). */
struct EventResult {
  bool consumed = false;
  bool redraw = false;
};

}  // namespace stk::ui
