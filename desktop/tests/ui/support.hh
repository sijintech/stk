/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Test helpers: a Context on the fake measurer with a rebuild callback. */
#pragma once

#include <functional>
#include <string>

#include <gtest/gtest.h>

#include "stk/ui/ui.hh"

namespace stk::ui::test {

std::string read_text(const std::string &path);
bool write_text(const std::string &path, const std::string &text);

/** Owns a Context; `ui` rebuilds the frame from test state (called by frame()). */
struct Harness {
  FakeTextMeasurer measurer;
  MemoryClipboard clipboard;
  Catalog catalog;
  std::unique_ptr<Context> ctx;
  std::function<void(Context &)> ui;
  Vec2 window{400, 600};
  double t = 10.0;

  explicit Harness(float scale = 1.0f, bool load_catalog = true);
  /** begin_frame, ui(ctx), end_frame. */
  void frame();
  const Widget &w(std::string_view key);
  Vec2 center(std::string_view key);

  EventResult send(const Event &e);
  void move(Vec2 p);
  void click(Vec2 p, uint8_t mods = 0);
  void click(std::string_view key) { click(center(key)); }
  void drag(Vec2 from, Vec2 to, uint8_t mods = 0, int steps = 4);
  void key(Key k, uint8_t mods = 0);
  void type(const std::string &s);
  /** Advances the clock (no event). */
  void wait(double seconds) { t += seconds; }
};

}  // namespace stk::ui::test
