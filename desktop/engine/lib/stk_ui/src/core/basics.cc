/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Event constructors, draw list builders, log buffer. */
#include "stk/ui/draw_list.hh"
#include "stk/ui/event.hh"
#include "stk/ui/log_buffer.hh"

namespace stk::ui {

/* -------------------------------------------------------------------- */
/* Events */

Event Event::mouse_move(Vec2 p, double t)
{
  Event e;
  e.type = EventType::MouseMove;
  e.pos = p;
  e.time = t;
  return e;
}

Event Event::mouse_down(Vec2 p, MouseButton b, double t, uint8_t mods)
{
  Event e;
  e.type = EventType::MouseDown;
  e.pos = p;
  e.button = b;
  e.time = t;
  e.mods = mods;
  return e;
}

Event Event::mouse_up(Vec2 p, MouseButton b, double t, uint8_t mods)
{
  Event e = mouse_down(p, b, t, mods);
  e.type = EventType::MouseUp;
  return e;
}

Event Event::wheel(Vec2 p, float dy, double t, uint8_t mods)
{
  Event e;
  e.type = EventType::Wheel;
  e.pos = p;
  e.wheel_y = dy;
  e.time = t;
  e.mods = mods;
  return e;
}

Event Event::key_down(Key k, uint8_t mods, double t)
{
  Event e;
  e.type = EventType::KeyDown;
  e.key = k;
  e.mods = mods;
  e.time = t;
  return e;
}

Event Event::key_up(Key k, uint8_t mods, double t)
{
  Event e = key_down(k, mods, t);
  e.type = EventType::KeyUp;
  return e;
}

Event Event::text_input(std::string s, double t)
{
  Event e;
  e.type = EventType::TextInput;
  e.text = std::move(s);
  e.time = t;
  return e;
}

Event Event::ime_preedit(std::string s, int cursor, double t)
{
  Event e;
  e.type = EventType::ImePreedit;
  e.text = std::move(s);
  e.ime_cursor = cursor;
  e.time = t;
  return e;
}

Event Event::ime_commit(std::string s, double t)
{
  Event e;
  e.type = EventType::ImeCommit;
  e.text = std::move(s);
  e.time = t;
  return e;
}

Event Event::tick(double t)
{
  Event e;
  e.type = EventType::Tick;
  e.time = t;
  return e;
}

/* -------------------------------------------------------------------- */
/* Draw list */

void DrawList::rect(const Rect &r, Color c)
{
  if (c.a == 0 || r.empty()) {
    return;
  }
  DrawCmd cmd;
  cmd.type = CmdType::Rect;
  cmd.rect = r;
  cmd.color = c;
  cmds.push_back(std::move(cmd));
}

DrawCmd &DrawList::round_box(const Rect &r, float radius, uint8_t corners, Color inner, Color outline, Color emboss)
{
  DrawCmd cmd;
  cmd.type = CmdType::RoundBox;
  cmd.rect = r;
  cmd.radius = radius;
  cmd.corners = corners;
  cmd.color = inner;
  cmd.color2 = inner;
  cmd.outline = outline;
  cmd.emboss = emboss;
  cmds.push_back(std::move(cmd));
  return cmds.back();
}

void DrawList::triangle(Vec2 a, Vec2 b, Vec2 c, Color col)
{
  DrawCmd cmd;
  cmd.type = CmdType::Triangle;
  cmd.p[0] = a;
  cmd.p[1] = b;
  cmd.p[2] = c;
  cmd.color = col;
  cmds.push_back(std::move(cmd));
}

void DrawList::text(std::string s, Vec2 baseline_left, const FontStyle &font, Color c)
{
  if (s.empty() || c.a == 0) {
    return;
  }
  DrawCmd cmd;
  cmd.type = CmdType::Text;
  cmd.text = std::move(s);
  cmd.pos = baseline_left;
  cmd.font = font;
  cmd.color = c;
  cmds.push_back(std::move(cmd));
}

void DrawList::color_strip(const Rect &r, std::vector<Color> colors)
{
  DrawCmd cmd;
  cmd.type = CmdType::ColorStrip;
  cmd.rect = r;
  cmd.colors = std::move(colors);
  cmds.push_back(std::move(cmd));
}

void DrawList::image(const Rect &r, uint64_t texture, const Rect &uv, Color tint)
{
  DrawCmd cmd;
  cmd.type = CmdType::Image;
  cmd.rect = r;
  cmd.texture = texture;
  cmd.uv = uv;
  cmd.color = tint;
  cmds.push_back(std::move(cmd));
}

void DrawList::clip_push(const Rect &r)
{
  DrawCmd cmd;
  cmd.type = CmdType::ClipPush;
  cmd.rect = r;
  cmds.push_back(std::move(cmd));
}

void DrawList::clip_pop()
{
  DrawCmd cmd;
  cmd.type = CmdType::ClipPop;
  cmds.push_back(std::move(cmd));
}

/* -------------------------------------------------------------------- */
/* Log buffer */

void LogBuffer::push_line(std::string s)
{
  lines_.push_back(std::move(s));
  while (lines_.size() > max_lines_) {
    lines_.pop_front();
    dropped_++;
  }
}

void LogBuffer::append(std::string_view chunk)
{
  if (chunk.empty()) {
    return;
  }
  const std::string clean = ansi_.feed(utf8_.feed(chunk));
  for (const char c : clean) {
    if (pending_cr_) {
      pending_cr_ = false;
      if (c == '\n') {
        push_line(std::move(partial_));
        partial_.clear();
        rewind_ = false;
        continue;
      }
      /* Lone \r: the next text overwrites the current line. */
      rewind_ = true;
    }
    if (c == '\r') {
      pending_cr_ = true;
      continue;
    }
    if (c == '\n') {
      push_line(std::move(partial_));
      partial_.clear();
      rewind_ = false;
      continue;
    }
    if (rewind_) {
      partial_.clear();
      rewind_ = false;
    }
    if (c == '\t') {
      partial_.append(4 - (partial_.size() % 4), ' ');
    }
    else {
      partial_ += c;
    }
  }
  version_++;
}

void LogBuffer::clear()
{
  lines_.clear();
  partial_.clear();
  rewind_ = pending_cr_ = false;
  ansi_.reset();
  utf8_ = {};
  version_++;
}

size_t LogBuffer::line_count() const
{
  return lines_.size() + (partial_.empty() ? 0 : 1);
}

std::string_view LogBuffer::line(size_t i) const
{
  if (i < lines_.size()) {
    return lines_[i];
  }
  if (i == lines_.size()) {
    return partial_;
  }
  return {};
}

}  // namespace stk::ui
