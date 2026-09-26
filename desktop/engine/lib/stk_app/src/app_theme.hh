/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Region colours of the application frame (Blender 5.2 default dark theme). */
#pragma once

#include "stk/ui/geom.hh"

namespace stk::app::theme {

/** Top bar and status bar (Blender: topbar / statusbar header). */
inline constexpr ui::Color kBarBack = ui::Color::rgb(0x181818);
/** Area headers. */
inline constexpr ui::Color kHeaderBack = ui::Color::rgb(0x303030);
/** List-like editors (Blender: outliner back). */
inline constexpr ui::Color kListBack = ui::Color::rgb(0x282828);
/** Property editors. */
inline constexpr ui::Color kPropertiesBack = ui::Color::rgb(0x2b2b2b);
/** 3D viewer background (Blender: view_3d gradient, flat). */
inline constexpr ui::Color kViewerBack = ui::Color::rgb(0x3d3d3d);
/** Toolbar and sidebar regions. */
inline constexpr ui::Color kToolBack = ui::Color::rgb(0x2e2e2e);

}  // namespace stk::app::theme
