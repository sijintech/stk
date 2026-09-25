/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "gallery_wm.hh"

#include <cmath>
#include <limits>

#include "GPU_texture.hh"

#include "stk/gfx/gpu.hh"
#include "stk/wm/window.hh"

namespace stk::ui::gallery {

namespace bgpu = blender::gpu;
using namespace blender;

/* -------------------------------------------------------------------- */
/* Demo texture */

uint64_t create_demo_texture(int w, int h)
{
  std::vector<uint8_t> px(size_t(w) * h * 4);
  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      /* Two domain families separated by wavy walls, shaded like a polarization map. */
      const float fx = float(x) / w, fy = float(y) / h;
      const float wall = std::sin(fx * 9.0f + 1.5f * std::sin(fy * 6.0f));
      const float v = 0.5f + 0.5f * std::tanh(wall * 4.0f);
      uint8_t *p = &px[(size_t(y) * w + x) * 4];
      p[0] = uint8_t(40 + 200 * v);
      p[1] = uint8_t(70 + 90 * (1.0f - std::fabs(wall)));
      p[2] = uint8_t(220 - 170 * v);
      p[3] = 255;
    }
  }
  bgpu::Texture *tex = GPU_texture_create_2d("stk-gallery-demo", w, h, 1, bgpu::TextureFormat::UNORM_8_8_8_8,
                                             GPU_TEXTURE_USAGE_SHADER_READ, nullptr);
  GPU_texture_update(tex, GPU_DATA_UBYTE, px.data());
  GPU_texture_filter_mode(tex, false);
  return uint64_t(uintptr_t(tex));
}

void free_texture(uint64_t handle)
{
  if (handle) {
    GPU_texture_free(reinterpret_cast<bgpu::Texture *>(uintptr_t(handle)));
  }
}

/* -------------------------------------------------------------------- */
/* Event adapter */

static Key map_key(wm::Key k)
{
  const int32_t v = int32_t(k);
  if ((v >= 'A' && v <= 'Z') || (v >= '0' && v <= '9')) {
    return Key(v);
  }
  switch (k) {
    case wm::Key::BackSpace: return Key::Backspace;
    case wm::Key::Tab: return Key::Tab;
    case wm::Key::Enter:
    case wm::Key::NumpadEnter: return Key::Enter;
    case wm::Key::Esc: return Key::Escape;
    case wm::Key::Space: return Key::Space;
    case wm::Key::LeftArrow: return Key::Left;
    case wm::Key::RightArrow: return Key::Right;
    case wm::Key::UpArrow: return Key::Up;
    case wm::Key::DownArrow: return Key::Down;
    case wm::Key::Insert: return Key::Insert;
    case wm::Key::Delete: return Key::Delete;
    case wm::Key::Home: return Key::Home;
    case wm::Key::End: return Key::End;
    case wm::Key::PageUp: return Key::PageUp;
    case wm::Key::PageDown: return Key::PageDown;
    default:
      if (v >= int32_t(wm::Key::F1) && v <= int32_t(wm::Key::F12)) {
        return Key(uint16_t(Key::F1) + (v - int32_t(wm::Key::F1)));
      }
      return Key::None;
  }
}

static uint8_t map_mods(uint32_t m)
{
  uint8_t out = MOD_NONE;
  if (m & wm::ModShift) {
    out |= MOD_SHIFT;
  }
  if (m & wm::ModCtrl) {
    out |= MOD_CTRL;
  }
  if (m & wm::ModAlt) {
    out |= MOD_ALT;
  }
  if (m & wm::ModOS) {
    out |= MOD_SUPER;
  }
  return out;
}

std::vector<Event> translate_event(const wm::Event &e, const wm::Rect &r)
{
  std::vector<Event> out;
  const double t = double(e.time_ms) / 1000.0;
  const Vec2 p{float(e.x - r.xmin), float(r.ymax - 1 - e.y)};
  const uint8_t mods = map_mods(e.modifiers);
  auto push = [&](Event ev) {
    ev.time = t;
    ev.mods = mods;
    if (ev.type != EventType::TextInput && ev.type != EventType::ImePreedit && ev.type != EventType::ImeCommit) {
      ev.pos = p;
    }
    out.push_back(std::move(ev));
  };
  switch (e.type) {
    case wm::EventType::MouseMove:
      push(Event::mouse_move(p));
      break;
    case wm::EventType::MouseDown:
    case wm::EventType::MouseUp: {
      const MouseButton b = e.button == wm::MouseButton::Left   ? MouseButton::Left :
                            e.button == wm::MouseButton::Middle ? MouseButton::Middle :
                            e.button == wm::MouseButton::Right  ? MouseButton::Right :
                                                                  MouseButton::None;
      push(e.type == wm::EventType::MouseDown ? Event::mouse_down(p, b) : Event::mouse_up(p, b));
      break;
    }
    case wm::EventType::Wheel: {
      /* Trackpads report pixels; the toolkit scrolls by notches (3 rows each). */
      const float dy = e.precise ? e.wheel_y / 40.0f : e.wheel_y;
      if (dy != 0.0f) {
        push(Event::wheel(p, dy));
      }
      break;
    }
    case wm::EventType::KeyDown: {
      const Key k = map_key(e.key);
      if (k != Key::None) {
        Event ev = Event::key_down(k);
        ev.repeat = e.is_repeat;
        push(ev);
      }
      const bool shortcut = (mods & (MOD_CTRL | MOD_ALT | MOD_SUPER)) != 0;
      if (!e.text.empty() && !shortcut && (unsigned char)e.text[0] >= 0x20 && e.text[0] != 0x7f) {
        push(Event::text_input(e.text));
      }
      break;
    }
    case wm::EventType::KeyUp: {
      const Key k = map_key(e.key);
      if (k != Key::None) {
        push(Event::key_up(k));
      }
      break;
    }
    case wm::EventType::ImeUpdate:
      if (!e.ime.result.empty()) {
        push(Event::ime_commit(e.ime.result));
      }
      push(Event::ime_preedit(e.ime.composite, e.ime.cursor));
      break;
    case wm::EventType::ImeEnd:
      if (!e.ime.result.empty()) {
        push(Event::ime_commit(e.ime.result));
      }
      else {
        push(Event::ime_preedit(std::string(), 0));
      }
      break;
    case wm::EventType::FocusOut: {
      Event ev;
      ev.type = EventType::FocusLost;
      push(ev);
      break;
    }
    default:
      break;
  }
  return out;
}

/* -------------------------------------------------------------------- */
/* Clipboard */

std::string WmClipboard::get()
{
  return wm_.clipboard_text();
}

void WmClipboard::set(std::string_view text)
{
  wm_.set_clipboard_text(text);
}

/* -------------------------------------------------------------------- */
/* Region */

UiRegion::UiRegion(std::string name, wm::WindowManager &wm, ContextConfig config, BuildFn build)
    : wm::Region(std::move(name)), wm_(wm), config_(std::move(config)), build_(std::move(build))
{
  measurer_ = std::make_unique<gpu::BlfTextMeasurer>(wm.gpu().fonts());
  painter_ = std::make_unique<gpu::GpuPainter>(wm.gpu().fonts());
  config_.measurer = measurer_.get();
  ctx_ = std::make_unique<Context>(config_);
}

UiRegion::~UiRegion()
{
  if (timer_) {
    wm_.remove_timer(timer_);
  }
}

void UiRegion::draw(const wm::DrawContext &dc)
{
  const wm::Rect &r = dc.rect;
  const Vec2 size{float(r.width()), float(r.height())};
  ctx_->set_scale(dc.ui_scale, 1.0f);
  build_(*ctx_, size, double(wm_.time_ms()) / 1000.0);
  painter_->set_pixel_size(ctx_->style().pixel);
  painter_->paint(ctx_->draw_list(), size);
  ctx_->clear_redraw();
  /* Input method: enabled while a field is edited, candidate window at the caret. */
  if (dc.window) {
    if (ctx_->text_input_active()) {
      const Rect c = ctx_->text_input_rect();
      const wm::Rect caret{r.xmin + int(c.x), r.ymax - int(c.y1()), r.xmin + int(c.x1()) + 1, r.ymax - int(c.y)};
      if (!dc.window->ime_active() || !(caret == ime_caret_)) {
        const TextEdit *ed = ctx_->edit_state();
        dc.window->ime_begin(caret, !(ed && ed->composing()));
        ime_caret_ = caret;
      }
    }
    else if (dc.window->ime_active()) {
      dc.window->ime_end();
      ime_caret_ = {};
    }
  }
  schedule_wakeup();
  if (after_draw) {
    after_draw();
  }
}

bool UiRegion::handle_event(const wm::Event &event, const wm::DrawContext &dc)
{
  bool consumed = false;
  for (const Event &e : translate_event(event, rect())) {
    const EventResult res = ctx_->handle_event(e);
    consumed |= res.consumed;
    if (res.redraw || ctx_->redraw_requested()) {
      tag_redraw();
    }
  }
  return consumed;
}

void UiRegion::schedule_wakeup()
{
  const double wake = ctx_->next_wakeup();
  if (!std::isfinite(wake) || (timer_ && wake == timer_at_)) {
    return;
  }
  if (timer_) {
    wm_.remove_timer(timer_);
  }
  const double now = double(wm_.time_ms()) / 1000.0;
  const uint64_t delay = uint64_t(std::max(0.0, wake - now) * 1000.0) + 5;
  timer_at_ = wake;
  timer_ = wm_.add_timer(delay, 0, [this]() {
    timer_ = 0;
    ctx_->handle_event(Event::tick(double(wm_.time_ms()) / 1000.0));
    tag_redraw();
  });
}

}  // namespace stk::ui::gallery
