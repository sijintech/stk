/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Internal: layout resolution passes (friend of Layout/Block/Context). */
#pragma once

#include <string_view>

#include "stk/ui/ui.hh"

namespace stk::ui {

struct LayoutEngine {
  static float text_w(const Context &ctx, std::string_view s, bool mono = false);
  static float pref_width(const Context &ctx, const Widget &w);
  static float space(const Layout &l, const Style &st);
  static float measure(Context &ctx, Layout &l);
  static void set_x(Layout::Item &it, float x, float w);
  static void place_x(Context &ctx, Layout &l, float x, float w);
  static float widget_height(Context &ctx, Widget &w);
  static float height(Context &ctx, Layout &l);
  static void place_y(Context &ctx, Layout &l, float y);
  static void apply_align(Layout &l);
  /** Resolves `root` at (x, y) with width w; returns the content height. */
  static float resolve(Context &ctx, Layout &root, float x, float y, float w);

  /* Block internals for context.cc/draw.cc. */
  static Layout &init_block(Context &ctx, Block &b);
  static const std::deque<Layout> &layouts(const Block &b) { return b.layouts_; }
  static const std::vector<Layout::Item> &items(const Layout &l) { return l.items_; }
  static const Widget *header(const Layout &l) { return l.header_; }
  static bool open(const Layout &l) { return l.open_; }
};

}  // namespace stk::ui
