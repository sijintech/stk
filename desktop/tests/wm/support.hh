/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Helpers for the screen / app tests (no GPU): a screen on ui::FakeTextMeasurer with synthesized
 * window events, and the application shell's default screen.
 */
#pragma once

#include <memory>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/ui/text.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/screen.hh"

namespace stk::wmtest {

std::string desktop_dir();
std::string read_text(const std::string &path);
bool write_text(const std::string &path, const std::string &text);
/** A fresh directory under the system temp dir (removed by the caller). */
std::string temp_dir(const std::string &tag);

/** A screen with a clock, window rectangle and event helpers. */
struct ScreenDriver {
  wm::Screen &screen;
  wm::DrawContext ctx;
  uint64_t time_ms = 100000;

  ScreenDriver(wm::Screen &s, int width, int height, float scale);
  /** Layout + one UI frame. */
  void frame();
  bool send(wm::Event e);
  bool move(int x, int y);
  bool down(int x, int y, wm::MouseButton b = wm::MouseButton::Left);
  bool up(int x, int y, wm::MouseButton b = wm::MouseButton::Left);
  /** Press, move in steps, release (frames in between, like a real window). */
  void drag(int x0, int y0, int x1, int y1, int steps = 4);
  bool click(int x, int y, wm::MouseButton b = wm::MouseButton::Left);
  bool key(wm::Key k, uint32_t mods = wm::ModNone, const std::string &text = {});
  void wait_ms(uint64_t ms)
  {
    time_ms += ms;
  }
};

/** The application shell with its default screen (fake measurer, catalogs from the source). */
struct AppFixture {
  ui::FakeTextMeasurer measurer;
  std::unique_ptr<app::AppShell> shell;
  wm::Screen screen;
  std::unique_ptr<ScreenDriver> drv;

  AppFixture(const std::string &lang = "en", float scale = 1.0f, int width = 1280, int height = 800);
  app::EditorArea &area(const std::string &id);
  /** Center of a rectangle (window pixels). */
  static std::pair<int, int> center(const wm::Rect &r)
  {
    return {(r.xmin + r.xmax) / 2, (r.ymin + r.ymax) / 2};
  }
  /** Window-pixel center of a widget of the last frame (by key or key suffix). */
  std::pair<int, int> widget_center(const std::string &key) const;
};

/** Serializes areas, regions, splitters and UI blocks / widgets of the last frame (goldens). */
std::string dump_screen(const wm::Screen &screen);

}  // namespace stk::wmtest
