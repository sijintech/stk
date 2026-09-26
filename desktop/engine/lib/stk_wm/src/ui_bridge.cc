/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/ui_bridge.hh"

#include "stk/wm/window.hh"

namespace stk::wm {

ui::Key to_ui_key(const Key k)
{
  const int32_t v = int32_t(k);
  if ((v >= 'A' && v <= 'Z') || (v >= '0' && v <= '9')) {
    return ui::Key(v);
  }
  switch (k) {
    case Key::BackSpace: return ui::Key::Backspace;
    case Key::Tab: return ui::Key::Tab;
    case Key::Enter:
    case Key::NumpadEnter: return ui::Key::Enter;
    case Key::Esc: return ui::Key::Escape;
    case Key::Space: return ui::Key::Space;
    case Key::LeftArrow: return ui::Key::Left;
    case Key::RightArrow: return ui::Key::Right;
    case Key::UpArrow: return ui::Key::Up;
    case Key::DownArrow: return ui::Key::Down;
    case Key::Insert: return ui::Key::Insert;
    case Key::Delete: return ui::Key::Delete;
    case Key::Home: return ui::Key::Home;
    case Key::End: return ui::Key::End;
    case Key::PageUp: return ui::Key::PageUp;
    case Key::PageDown: return ui::Key::PageDown;
    default:
      if (v >= int32_t(Key::F1) && v <= int32_t(Key::F12)) {
        return ui::Key(uint16_t(ui::Key::F1) + (v - int32_t(Key::F1)));
      }
      return ui::Key::None;
  }
}

uint8_t to_ui_modifiers(const uint32_t m)
{
  uint8_t out = ui::MOD_NONE;
  if (m & ModShift) {
    out |= ui::MOD_SHIFT;
  }
  if (m & ModCtrl) {
    out |= ui::MOD_CTRL;
  }
  if (m & ModAlt) {
    out |= ui::MOD_ALT;
  }
  if (m & ModOS) {
    out |= ui::MOD_SUPER;
  }
  return out;
}

std::vector<ui::Event> translate_event(const Event &e, const Rect &r)
{
  using ui::EventType;
  std::vector<ui::Event> out;
  const double t = double(e.time_ms) / 1000.0;
  const ui::Vec2 p{float(e.x - r.xmin), float(r.ymax - 1 - e.y)};
  const uint8_t mods = to_ui_modifiers(e.modifiers);
  auto push = [&](ui::Event ev) {
    ev.time = t;
    ev.mods = mods;
    if (ev.type != EventType::TextInput && ev.type != EventType::ImePreedit && ev.type != EventType::ImeCommit) {
      ev.pos = p;
    }
    out.push_back(std::move(ev));
  };
  auto button = [](MouseButton b) {
    return b == MouseButton::Left   ? ui::MouseButton::Left :
           b == MouseButton::Middle ? ui::MouseButton::Middle :
           b == MouseButton::Right  ? ui::MouseButton::Right :
                                      ui::MouseButton::None;
  };
  switch (e.type) {
    case wm::EventType::MouseMove:
      push(ui::Event::mouse_move(p));
      break;
    case wm::EventType::MouseDown:
      push(ui::Event::mouse_down(p, button(e.button)));
      break;
    case wm::EventType::MouseUp:
      push(ui::Event::mouse_up(p, button(e.button)));
      break;
    case wm::EventType::Wheel: {
      /* Trackpads report pixels; the toolkit scrolls by notches (3 rows each). */
      const float dy = e.precise ? e.wheel_y / 40.0f : e.wheel_y;
      if (dy != 0.0f) {
        push(ui::Event::wheel(p, dy));
      }
      break;
    }
    case wm::EventType::KeyDown: {
      const ui::Key k = to_ui_key(e.key);
      if (k != ui::Key::None) {
        ui::Event ev = ui::Event::key_down(k);
        ev.repeat = e.is_repeat;
        push(ev);
      }
      const bool shortcut = (mods & (ui::MOD_CTRL | ui::MOD_ALT | ui::MOD_SUPER)) != 0;
      if (!e.text.empty() && !shortcut && (unsigned char)e.text[0] >= 0x20 && e.text[0] != 0x7f) {
        push(ui::Event::text_input(e.text));
      }
      break;
    }
    case wm::EventType::KeyUp: {
      const ui::Key k = to_ui_key(e.key);
      if (k != ui::Key::None) {
        push(ui::Event::key_up(k));
      }
      break;
    }
    case wm::EventType::ImeUpdate:
      if (!e.ime.result.empty()) {
        push(ui::Event::ime_commit(e.ime.result));
      }
      push(ui::Event::ime_preedit(e.ime.composite, e.ime.cursor));
      break;
    case wm::EventType::ImeEnd:
      if (!e.ime.result.empty()) {
        push(ui::Event::ime_commit(e.ime.result));
      }
      else {
        push(ui::Event::ime_preedit(std::string(), 0));
      }
      break;
    case wm::EventType::FocusOut: {
      ui::Event ev;
      ev.type = EventType::FocusLost;
      push(ev);
      break;
    }
    default:
      break;
  }
  return out;
}

std::string WmClipboard::get()
{
  return wm_.clipboard_text();
}

void WmClipboard::set(std::string_view text)
{
  wm_.set_clipboard_text(text);
}

UiRegion::UiRegion(std::string name, const RegionAlign align, const float size_1x, BuildFn build)
    : Region(std::move(name), align, size_1x), build_(std::move(build))
{
}

std::unique_ptr<UiRegion> UiRegion::with_layout(std::string name,
                                                const RegionAlign align,
                                                const float size_1x,
                                                LayoutFn fn)
{
  auto region = std::make_unique<UiRegion>(std::move(name), align, size_1x, nullptr);
  UiRegion *self = region.get();
  region->build_ = [self, fn = std::move(fn)](ui::Context &ui, const ui::Rect &rect, const DrawContext &ctx) {
    ui::Layout &l = ui.block(self->block_name(), rect).layout();
    if (fn) {
      fn(l, ctx);
    }
  };
  return region;
}

void UiRegion::build_ui(ui::Context &ui, const DrawContext &ctx)
{
  if (build_) {
    build_(ui, ui_rect(), ctx);
  }
  if (after_build) {
    after_build();
  }
}

}  // namespace stk::wm
