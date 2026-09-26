/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * ui_gpu: paints ui::DrawList with Blender's GPU module (immediate mode + the widget-base SDF
 * shader, so rounded boxes, outlines, emboss and check/arrow/chevron decorations match Blender)
 * and measures/draws text with BLF through WP1's font stack (Inter with the Noto Sans CJK
 * fallback, DejaVu Sans Mono for logs).
 *
 * Requirements: an active GPU context and loaded fonts (stk::gfx::Gpu). Texture handles in
 * DrawCmd::texture are `blender::gpu::Texture *` cast to uint64_t.
 */
#pragma once

#include "stk/gfx/fonts.hh"
#include "stk/ui/draw_list.hh"
#include "stk/ui/text.hh"

namespace blender::gpu {
class Batch;
}

namespace stk::ui::gpu {

class BlfTextMeasurer final : public TextMeasurer {
 public:
  explicit BlfTextMeasurer(const gfx::FontStack &fonts) : ui_(fonts.ui), mono_(fonts.mono) {}
  float width(std::string_view text, const FontStyle &style) const override;
  FontMetrics metrics(const FontStyle &style) const override;

 private:
  int font(const FontStyle &style) const { return style.kind == FontKind::Mono ? mono_ : ui_; }
  int ui_, mono_;
};

class GpuPainter final : public Painter {
 public:
  explicit GpuPainter(const gfx::FontStack &fonts) : ui_(fonts.ui), mono_(fonts.mono) {}
  ~GpuPainter() override;
  GpuPainter(const GpuPainter &) = delete;
  GpuPainter &operator=(const GpuPainter &) = delete;

  /**
   * Paints into the bound framebuffer. `viewport` is the size of the current GPU viewport (a WP1
   * region's rectangle, or the whole offscreen target); draw-list coordinates are relative to its
   * top-left corner. Sets its own pixel projection; leaves the scissor at the viewport.
   */
  void paint(const DrawList &list, Vec2 viewport) override;
  /** Pixel size used for widget outlines (U.pixelsize); set from ui::Style::pixel. */
  void set_pixel_size(float px) { pixel_ = px; }

 private:
  int ui_, mono_;
  blender::gpu::Batch *widget_batch_ = nullptr;
  float pixel_ = 1.0f;
};

}  // namespace stk::ui::gpu
