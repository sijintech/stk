/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Window state and geometry queries (layout persistence) and the CSD capability. */

#include "stk/wm/window.hh"

#include "GHOST_IWindow.hh"
#include "GHOST_Rect.hh"

#include "stk/wm/csd.hh"

namespace stk::wm {

bool Window::maximized() const
{
  return ghost_ && ghost_->getState() == GHOST_kWindowStateMaximized;
}

void Window::set_maximized(const bool maximized)
{
  if (ghost_ && maximized != this->maximized()) {
    ghost_->setState(maximized ? GHOST_kWindowStateMaximized : GHOST_kWindowStateNormal);
  }
}

void Window::client_geometry(int &r_x, int &r_y, int &r_width, int &r_height) const
{
  GHOST_Rect r;
  ghost_->getClientBounds(r);
  r_x = r.l_;
  r_y = r.t_;
  r_width = client_w_;
  r_height = client_h_;
}

bool WindowManager::csd_active() const
{
  return wm::csd_active(*this);
}

}  // namespace stk::wm
