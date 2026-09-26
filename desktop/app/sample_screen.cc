/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "sample_screen.hh"

#include <cmath>
#include <cstring>
#include <string>

#include "GPU_immediate.hh"
#include "GPU_immediate_util.hh"
#include "GPU_state.hh"
#include "GPU_vertex_format.hh"

#include "BLF_api.hh"

#include "stk/gfx/fonts.hh"
#include "stk/wm/window.hh"

#include "sample_layout.hh"

namespace stk::app {

using namespace blender;

static void fill_rect(const float x0, const float y0, const float x1, const float y1, const float color[4])
{
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
  immUniformColor4fv(color);
  immRectf(pos, x0, y0, x1, y1);
  immUnbindProgram();
}

static void text(const int font, const float px, const float x, const float y, const char *str, const float color[4])
{
  GPU_blend(GPU_BLEND_ALPHA);
  BLF_size(font, px);
  BLF_color4fv(font, color);
  BLF_position(font, std::round(x), std::round(y), 0.0f);
  BLF_draw(font, str, strlen(str));
  GPU_blend(GPU_BLEND_NONE);
}

/* -------------------------------------------------------------------- */

class HeaderRegion : public wm::Region {
 public:
  HeaderRegion() : Region("header", wm::RegionAlign::Top, kHeader1x) {}

  void draw(const wm::DrawContext &ctx) override
  {
    fill_rect(0, 0, ctx.rect.width(), ctx.rect.height(), theme::kHeaderBack);
    const float px = gfx::font_px(gfx::kUiTextPoints, ctx.ui_scale);
    const float y = std::round((ctx.rect.height() - px * 0.7f) * 0.5f);
    text(ctx.fonts->ui, px, kMargin1x * ctx.ui_scale, y, "STK", theme::kTextHi);
  }
};

class StatusRegion : public wm::Region {
 public:
  explicit StatusRegion(wm::WindowManager *wm) : Region("status", wm::RegionAlign::Bottom, 22.0f), wm_(wm) {}

  void draw(const wm::DrawContext &ctx) override
  {
    fill_rect(0, 0, ctx.rect.width(), ctx.rect.height(), theme::kHeaderBack);
    const float px = gfx::font_px(gfx::kUiTextPoints, ctx.ui_scale);
    const float x = kMargin1x * ctx.ui_scale;
    const float y = std::round((ctx.rect.height() - px * 0.7f) * 0.5f);
    const std::string shown = typed_.empty() && preedit_.empty() ? message_ : "> " + typed_;
    text(ctx.fonts->ui, px, x, y, shown.c_str(), theme::kText);
    float caret_x = x;
    if (!(typed_.empty() && preedit_.empty())) {
      BLF_size(ctx.fonts->ui, px);
      caret_x += BLF_width(ctx.fonts->ui, shown.c_str(), shown.size());
    }
    if (!preedit_.empty()) {
      /* Inline IME preedit: accent colored and underlined. */
      text(ctx.fonts->ui, px, caret_x, y, preedit_.c_str(), theme::kAccent);
      BLF_size(ctx.fonts->ui, px);
      const float w = BLF_width(ctx.fonts->ui, preedit_.c_str(), preedit_.size());
      const float t = std::max(1.0f, std::round(ctx.ui_scale));
      fill_rect(caret_x, y - 2 * t, caret_x + w, y - t, theme::kAccent);
    }
    caret_ = {int(ctx.rect.xmin + caret_x),
              int(ctx.rect.ymin + y - px * 0.25f),
              int(ctx.rect.xmin + caret_x + 1),
              int(ctx.rect.ymin + y + px)};
    if (wm_ && ctx.window && ctx.window->ime_active() && !(caret_ == ime_caret_)) {
      /* Keep the IME candidate window next to the caret (only when it moved). */
      ime_caret_ = caret_;
      ctx.window->ime_begin(caret_, preedit_.empty());
    }
  }

  bool handle_event(const wm::Event &e, const wm::DrawContext &ctx) override
  {
    if (!wm_) {
      return false;
    }
    using wm::EventType;
    using wm::Key;
    switch (e.type) {
      case EventType::MouseMove:
        ctx.window->set_cursor(wm::Cursor::Text);
        return false;
      case EventType::KeyDown:
        if (e.modifiers & wm::ModCtrl) {
          if (e.key == Key::V) {
            typed_ += first_line(wm_->clipboard_text());
          }
          else if (e.key == Key::C) {
            wm_->set_clipboard_text(typed_);
            message_ = "Copied";
          }
          else {
            return false;
          }
        }
        else if (e.key == Key::BackSpace) {
          pop_utf8(typed_);
        }
        else if (e.key == Key::Esc) {
          typed_.clear();
          preedit_.clear();
        }
        else if (!e.text.empty()) {
          typed_ += e.text;
        }
        else {
          return false;
        }
        tag_redraw();
        return true;
      case EventType::ImeStart:
      case EventType::ImeUpdate:
        typed_ += e.ime.result;
        preedit_ = e.ime.composite;
        tag_redraw();
        return true;
      case EventType::ImeEnd:
        typed_ += e.ime.result;
        preedit_.clear();
        tag_redraw();
        return true;
      default:
        return false;
    }
  }

  void set_message(std::string m)
  {
    message_ = std::move(m);
    tag_redraw();
  }

 private:
  static std::string first_line(const std::string &s)
  {
    return s.substr(0, s.find_first_of("\r\n"));
  }
  static void pop_utf8(std::string &s)
  {
    while (!s.empty() && (uint8_t(s.back()) & 0xC0) == 0x80) {
      s.pop_back();
    }
    if (!s.empty()) {
      s.pop_back();
    }
  }

  wm::WindowManager *wm_;
  std::string typed_, preedit_;
  std::string message_ = "\xe5\xb0\xb1\xe7\xbb\xaa Ready"; /* 就绪 Ready */
  wm::Rect caret_, ime_caret_;
};

class ContentRegion : public wm::Region {
 public:
  ContentRegion(wm::WindowManager *wm, StatusRegion *status)
      : Region("content", wm::RegionAlign::Fill), wm_(wm), status_(status)
  {
  }

  void draw(const wm::DrawContext &ctx) override
  {
    fill_rect(0, 0, ctx.rect.width(), ctx.rect.height(), theme::kRegionBack);
    /* The layout is defined in window pixels; this region starts at the window's left edge. */
    const wm::Rect &screen_rect = screen()->rect();
    const SampleLayout l = sample_layout(screen_rect.width(), screen_rect.height(), ctx.ui_scale);
    const float ox = float(-ctx.rect.xmin), oy = float(-ctx.rect.ymin);
    fill_rect(0, l.accent_y0 + oy, ctx.rect.width(), l.accent_y1 + oy, theme::kAccent);
    for (const SampleRow &row : l.rows) {
      text(ctx.fonts->ui, row.px, row.cjk_x + ox, row.baseline + oy, kSampleCjk, theme::kText);
      text(ctx.fonts->ui, row.px, row.latin_x + ox, row.baseline + oy, kSampleLatin, theme::kText);
    }
  }

  bool handle_event(const wm::Event &e, const wm::DrawContext &ctx) override
  {
    if (!wm_) {
      return false;
    }
    using wm::EventType;
    switch (e.type) {
      case EventType::MouseMove:
        ctx.window->set_cursor(wm::Cursor::Default);
        return false;
      case EventType::KeyDown:
        if (e.modifiers & wm::ModCtrl) {
          if (e.key == wm::Key::Equal || e.key == wm::Key::Plus || e.key == wm::Key::NumpadPlus) {
            wm_->set_user_scale(wm_->user_scale() * 1.25f);
            return true;
          }
          if (e.key == wm::Key::Minus || e.key == wm::Key::NumpadMinus) {
            wm_->set_user_scale(wm_->user_scale() / 1.25f);
            return true;
          }
          if (e.key == wm::Key::Num0 || e.key == wm::Key::Numpad0) {
            wm_->set_user_scale(1.0f);
            return true;
          }
        }
        /* Everything else types into the status line. */
        return status_->handle_event(e, ctx);
      case EventType::ImeStart:
      case EventType::ImeUpdate:
      case EventType::ImeEnd:
        return status_->handle_event(e, ctx);
      case EventType::Drop: {
        std::string m = e.paths.empty() ? "Dropped text: " + e.text :
                                          "Dropped " + std::to_string(e.paths.size()) + " file(s): " +
                                              e.paths.front();
        status_->set_message(m);
        return true;
      }
      default:
        return false;
    }
  }

 private:
  wm::WindowManager *wm_;
  StatusRegion *status_;
};

void build_sample_screen(wm::Screen &screen, wm::WindowManager *wm)
{
  std::copy(theme::kWindowBack, theme::kWindowBack + 4, screen.background);
  wm::Area &area = screen.add_area("sample");
  area.emplace_region<HeaderRegion>();
  auto &status = area.emplace_region<StatusRegion>(wm);
  auto &content = area.emplace_region<ContentRegion>(wm, &status);
  /* Keyboard and IME go to the content region, which forwards text to the status line. */
  screen.set_focus(&content);
}

}  // namespace stk::app
