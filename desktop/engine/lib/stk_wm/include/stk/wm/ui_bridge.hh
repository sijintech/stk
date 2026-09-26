/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Glue between the window manager and the UI toolkit (stk_ui): the stk::wm::Event ->
 * ui::Event adapter, the window manager's clipboard as a ui::Clipboard, and #UiRegion, a region
 * whose UI is built by a callback. (Lifted from the WP2 widget gallery.)
 */
#pragma once

#include <functional>
#include <string>
#include <string_view>
#include <vector>

#include "stk/ui/event.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/event.hh"
#include "stk/wm/screen.hh"

namespace stk::wm {

class WindowManager;

/**
 * Translates one window event into toolkit events relative to `frame` (normally the whole
 * window): window pixels with a bottom-left origin become frame pixels with a top-left origin; a
 * key press with printable text (and no Ctrl/Alt/Super) also yields TextInput; an IME update
 * yields ImeCommit (result) and/or ImePreedit (composition); focus loss yields FocusLost.
 */
std::vector<ui::Event> translate_event(const Event &e, const Rect &frame);
ui::Key to_ui_key(Key key);
uint8_t to_ui_modifiers(uint32_t modifiers);

/** The window manager's text clipboard. */
class WmClipboard final : public ui::Clipboard {
 public:
  explicit WmClipboard(WindowManager &wm) : wm_(wm) {}
  std::string get() override;
  void set(std::string_view text) override;

 private:
  WindowManager &wm_;
};

/**
 * A region whose UI is built by a callback in the screen's shared ui::Context. The callback
 * receives the region rectangle in UI coordinates and creates its blocks, e.g.
 *   [](ui::Context &ui, const ui::Rect &r, const DrawContext &) {
 *     ui::Layout &l = ui.block("my/main", r).layout(); ...
 *   }
 * With `block_name` set, the region creates one block itself and the callback fills its layout
 * (use #build_layout).
 */
class UiRegion : public Region {
 public:
  using BuildFn = std::function<void(ui::Context &ui, const ui::Rect &rect, const DrawContext &ctx)>;
  using LayoutFn = std::function<void(ui::Layout &layout, const DrawContext &ctx)>;

  UiRegion(std::string name, RegionAlign align, float size_1x, BuildFn build);
  /** One block named #block_name, laid out by `fn`. */
  static std::unique_ptr<UiRegion> with_layout(std::string name, RegionAlign align, float size_1x, LayoutFn fn);

  void build_ui(ui::Context &ui, const DrawContext &ctx) override;
  /** Called after every UI frame this region took part in (smoke tests count frames). */
  std::function<void()> after_build;

 private:
  BuildFn build_;
};

}  // namespace stk::wm
