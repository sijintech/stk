/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Multiline input uses the existing TextEdit/IME model, with unwrapped physical lines. */
#include "stk/ui/ui.hh"

#include <algorithm>
#include <cmath>

namespace stk::ui {

void Context::draw_text_area(const Widget &w, const WidgetColors &colors)
{
  const bool editing = edit_.id == w.id;
  const auto &st = style_;
  const auto &tm = measurer();
  const auto &font = w.mono ? st.mono : st.font;
  const auto fm = tm.metrics(font);
  const Rect area = w.rect.inset(st.text_margin, st.text_margin);
  if (area.w <= 0 || area.h <= 0) { return; }
  const std::string text = editing ? edit_.edit.display_text() : w.string.value();
  const auto lines = hard_lines(text);
  const float height = st.line_height;
  const float max_scroll = std::max(0.0f, float(lines.size()) * height - area.h);
  float scroll = std::clamp(scroll_of(w.id), 0.0f, max_scroll);
  const size_t caret = editing ? edit_.edit.display_caret() : 0;
  size_t caret_row = 0;
  if (editing) {
    while (caret_row + 1 < lines.size() && lines[caret_row + 1].begin <= caret) { ++caret_row; }
  }
  const auto line_text = [&](size_t row) {
    const auto &line = lines[row];
    return std::string_view(text).substr(line.begin, line.end - line.begin);
  };
  const float caret_x = editing ? tm.caret_x(line_text(caret_row), caret - lines[caret_row].begin, font) : 0;
  if (editing && edit_.follow_caret) {
    const float top = float(caret_row) * height;
    if (top < scroll) { scroll = top; }
    if (top + height > scroll + area.h) { scroll = top + height - area.h; }
    if (caret_x - edit_.scroll_x > area.w - st.pixel) { edit_.scroll_x = caret_x - area.w + st.pixel; }
    if (caret_x - edit_.scroll_x < 0) { edit_.scroll_x = caret_x; }
    edit_.scroll_x = std::max(0.0f, edit_.scroll_x);
    edit_.follow_caret = false;
  }
  set_scroll(w.id, scroll, max_scroll);
  const float x = std::round(area.x - (editing ? edit_.scroll_x : 0));
  const float lead = std::round((height - fm.ascent - fm.descent) * 0.5f + fm.ascent);
  const auto selection = editing ? edit_.edit.selection() : std::pair<size_t, size_t>{0, 0};
  const auto preedit = editing ? edit_.edit.display_preedit() : std::pair<size_t, size_t>{0, 0};
  draw_.clip_push(area);
  const size_t first = size_t(std::max(0.0f, std::floor(scroll / height)));
  for (size_t row = first; row < lines.size(); ++row) {
    const float y = area.y + float(row) * height - scroll;
    if (y >= area.y1()) { break; }
    const auto &line = lines[row];
    const auto value = line_text(row);
    if (editing && edit_.edit.has_selection() && !edit_.edit.composing() &&
        selection.first <= line.end && selection.second > line.begin) {
      const size_t start = std::max(line.begin, selection.first) - line.begin;
      const size_t end = std::min(line.end, selection.second) - line.begin;
      const float left = tm.caret_x(value, start, font), right = tm.caret_x(value, end, font);
      const float newline = selection.second > line.end && row + 1 < lines.size() ? st.text_margin : 0;
      draw_.rect({x + left, y, std::max(0.0f, right - left) + newline, height}, config_.theme.text.item);
    }
    draw_.text(std::string(value), {x, y + lead}, font, editing ? config_.theme.text.text_sel : colors.text);
    if (editing && edit_.edit.composing() && preedit.first <= line.end && preedit.second > line.begin) {
      const size_t start = std::max(line.begin, preedit.first) - line.begin;
      const size_t end = std::min(line.end, preedit.second) - line.begin;
      const float left = tm.caret_x(value, start, font), right = tm.caret_x(value, end, font);
      draw_.rect({x + left, y + lead + st.pixel, right - left, st.pixel}, config_.theme.text.text_sel);
    }
  }
  if (text.empty() && !editing && !w.text_opts.placeholder.empty()) {
    draw_.text(w.text_opts.placeholder, {area.x, area.y + lead}, font, colors.text.scaled_alpha(0.45f));
  }
  if (editing) {
    const float width = std::max(1.0f, std::round(1.5f * st.scale));
    const Rect caret_rect = {x + caret_x, area.y + float(caret_row) * height - scroll, width, height};
    draw_.rect(caret_rect, config_.theme.text_cursor);
    edit_caret_ = {std::clamp(caret_rect.x, area.x, area.x1()),
                   std::clamp(caret_rect.y, area.y, std::max(area.y, area.y1() - height)), width, height};
  }
  draw_.clip_pop();
}

}  // namespace stk::ui
