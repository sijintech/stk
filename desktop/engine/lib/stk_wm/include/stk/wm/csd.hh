/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Client-side window decorations (CSD).
 *
 * GNOME's Wayland compositor does not draw title bars. Blender 5.2's GHOST no longer uses
 * libdecor for this: it has its own CSD (WITH_GHOST_CSD, built in our vendored GHOST), enabled on
 * GNOME (XDG_CURRENT_DESKTOP). GHOST performs the window actions itself (move by dragging the
 * title bar, resize at the borders, minimize / maximize / close buttons, double-click maximize,
 * right-click window menu) on the elements the application reports through a layout callback;
 * the application draws the title bar. stk_wm installs that callback (WindowManager::create) with
 * the geometry below, and the application's top bar doubles as the title bar: it draws the
 * buttons at #CsdLayout::buttons when #csd_active is true.
 */
#pragma once

#include <cstdint>
#include <vector>

#include "stk/wm/screen.hh"

namespace stk::wm {

class Window;
class WindowManager;

enum class CsdButtonKind : uint8_t { Close, Maximize, Minimize, Menu };

struct CsdButton {
  CsdButtonKind kind = CsdButtonKind::Close;
  /** Window pixels, origin bottom-left. */
  Rect rect;
};

struct CsdLayout {
  /** Title bar strip at the top of the window (the application's top bar). */
  Rect titlebar;
  /** Drag zone of the title bar: #titlebar minus the menus and the buttons. */
  Rect drag;
  std::vector<CsdButton> buttons;
  /** Resize border thickness (0 when maximized). */
  int border = 0;
  /** Widths taken by buttons at the left / right end of the title bar. */
  int left_reserve = 0;
  int right_reserve = 0;
};

struct CsdConfig {
  /** Button width at scale 1 (height = the top bar height). */
  float button_width_1x = 34.0f;
  /** Resize border inside the window edge at scale 1. */
  float border_1x = 5.0f;
  /** Width kept for the application menus at the left of the title bar (not a drag zone). */
  float menu_width_1x = 330.0f;
};

void csd_configure(const CsdConfig &config);
const CsdConfig &csd_config();

/**
 * Title-bar geometry for a `width` x `height` pixel window at `ui_scale`, with GHOST's button
 * order (`left` of the title, then `right` of it). Pure arithmetic (unit tested).
 */
CsdLayout csd_compute_layout(int width,
                             int height,
                             float ui_scale,
                             const std::vector<CsdButtonKind> &left,
                             const std::vector<CsdButtonKind> &right,
                             bool maximized);

/** The window system needs client-side decorations (GNOME on Wayland). */
bool csd_active(const WindowManager &wm);
/** Current layout of a window's decorations (empty when #csd_active is false). */
CsdLayout csd_layout(const Window &window);
/** Times GHOST asked for the layout (diagnostics and tests). */
uint64_t csd_layout_calls();

/** Installs the GHOST layout callback; called by WindowManager::create before any window. */
void csd_install(WindowManager &wm);

}  // namespace stk::wm
