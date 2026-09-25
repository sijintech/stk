/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Glue between stk_ui and WP1's stk_gfx / stk_wm used by the widget gallery: a demo texture, the
 * stk::wm::Event -> ui::Event adapter, a clipboard on the window manager, and a wm::Region that
 * hosts a ui::Context (rebuild on demand, IME caret placement, tooltip/toast timers).
 * WP3 can lift the adapter and the region into stk_wm/stk_app.
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

#include "stk/ui/gpu_painter.hh"
#include "stk/ui/ui.hh"
#include "stk/wm/screen.hh"

namespace stk::wm {
class WindowManager;
}

namespace stk::ui::gallery {

/** RGBA8 demo texture (ferroelectric-domain-like stripes); returns the handle for ImageSpec. */
uint64_t create_demo_texture(int w, int h);
void free_texture(uint64_t handle);

/**
 * Translates one window event into toolkit events for a region: window pixels with a bottom-left
 * origin become region-local pixels with a top-left origin; a key press with printable text also
 * yields TextInput; an IME update yields ImeCommit (result) and/or ImePreedit (composition).
 */
std::vector<Event> translate_event(const wm::Event &e, const wm::Rect &region);

class WmClipboard final : public Clipboard {
 public:
  explicit WmClipboard(wm::WindowManager &wm) : wm_(wm) {}
  std::string get() override;
  void set(std::string_view text) override;

 private:
  wm::WindowManager &wm_;
};

/** A wm::Region rebuilding a ui::Context each (on-demand) frame via `build`. */
class UiRegion : public wm::Region {
 public:
  using BuildFn = std::function<void(Context &ctx, Vec2 size, double now)>;
  UiRegion(std::string name, wm::WindowManager &wm, ContextConfig config, BuildFn build);
  ~UiRegion() override;

  void draw(const wm::DrawContext &ctx) override;
  bool handle_event(const wm::Event &event, const wm::DrawContext &ctx) override;
  Context &context() { return *ctx_; }
  /** Called after every painted frame (smoke tests count frames). */
  std::function<void()> after_draw;

 private:
  void schedule_wakeup();

  wm::WindowManager &wm_;
  std::unique_ptr<gpu::BlfTextMeasurer> measurer_;
  std::unique_ptr<gpu::GpuPainter> painter_;
  std::unique_ptr<Context> ctx_;
  ContextConfig config_;
  BuildFn build_;
  uint64_t timer_ = 0;
  double timer_at_ = 0.0;
  wm::Rect ime_caret_;
};

}  // namespace stk::ui::gallery
