/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The WP1 sample screen: a header region and a content region showing "中文 English" at several
 * sizes (see sample_layout.hh), plus, in the GUI, a status line that echoes typed text, IME
 * preedit, clipboard pastes and dropped files (a manual IME / clipboard / DnD test bed).
 * The same screen is drawn by the window and by `--headless` exports.
 */
#pragma once

#include "stk/wm/screen.hh"

namespace stk::wm {
class WindowManager;
}

namespace stk::app {

/**
 * Adds the sample area to `screen`. `wm` enables the interactive parts (status line, keyboard,
 * IME, clipboard, drop and Ctrl +/-/0 UI scale); pass nullptr for headless rendering.
 */
void build_sample_screen(wm::Screen &screen, wm::WindowManager *wm);

}  // namespace stk::app
