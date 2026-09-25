/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include <fstream>
#include <sstream>

namespace stk::ui::test {

std::string read_text(const std::string &path)
{
  std::ifstream f(path, std::ios::binary);
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
}

bool write_text(const std::string &path, const std::string &text)
{
  std::ofstream f(path, std::ios::binary);
  f << text;
  return bool(f);
}

Harness::Harness(float scale, bool load_catalog)
{
  if (load_catalog) {
    catalog.load_dir(std::string(STK_DESKTOP_DIR) + "/app/i18n");
  }
  ContextConfig cfg;
  cfg.measurer = &measurer;
  cfg.clipboard = &clipboard;
  cfg.catalog = &catalog;
  ctx = std::make_unique<Context>(cfg);
  ctx->set_scale(scale);
}

void Harness::frame()
{
  ctx->begin_frame(window, t);
  if (ui) {
    ui(*ctx);
  }
  ctx->end_frame();
}

const Widget &Harness::w(std::string_view key)
{
  const Widget *wp = ctx->find(key);
  if (!wp) {
    ADD_FAILURE() << "no widget '" << key << "'";
    static Widget dummy;
    return dummy;
  }
  return *wp;
}

Vec2 Harness::center(std::string_view key)
{
  const Widget &x = w(key);
  return {x.rect.cx(), x.rect.cy()};
}

EventResult Harness::send(const Event &e)
{
  Event ev = e;
  ev.time = t;
  const EventResult r = ctx->handle_event(ev);
  frame();
  return r;
}

void Harness::move(Vec2 p)
{
  send(Event::mouse_move(p));
}

void Harness::click(Vec2 p, uint8_t mods)
{
  send(Event::mouse_move(p));
  send(Event::mouse_down(p, MouseButton::Left, 0, mods));
  send(Event::mouse_up(p, MouseButton::Left, 0, mods));
  t += 1.0; /* Never a double click unless a test wants one. */
}

void Harness::drag(Vec2 from, Vec2 to, uint8_t mods, int steps)
{
  send(Event::mouse_move(from));
  send(Event::mouse_down(from, MouseButton::Left, 0, mods));
  for (int i = 1; i <= steps; i++) {
    const float f = float(i) / float(steps);
    Event e = Event::mouse_move({from.x + (to.x - from.x) * f, from.y + (to.y - from.y) * f});
    e.mods = mods;
    send(e);
  }
  send(Event::mouse_up(to, MouseButton::Left, 0, mods));
  t += 1.0;
}

void Harness::key(Key k, uint8_t mods)
{
  send(Event::key_down(k, mods));
  send(Event::key_up(k, mods));
}

void Harness::type(const std::string &s)
{
  send(Event::text_input(s));
}

}  // namespace stk::ui::test
