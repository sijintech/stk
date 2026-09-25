/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/text_edit.hh"

#include <algorithm>

#include "stk/ui/text.hh"
#include "stk/ui/utf8.hh"

namespace stk::ui {

static constexpr size_t MAX_UNDO = 200;

void TextEdit::set_text(std::string text, bool select_all)
{
  text_ = utf8::sanitize(text);
  cursor_ = text_.size();
  anchor_ = select_all ? 0 : cursor_;
  preedit_.clear();
  preedit_caret_ = 0;
  undo_.clear();
  redo_.clear();
  last_op_ = Op::None;
}

std::pair<size_t, size_t> TextEdit::selection() const
{
  return {std::min(cursor_, anchor_), std::max(cursor_, anchor_)};
}

std::string TextEdit::selected_text() const
{
  const auto [b, e] = selection();
  return text_.substr(b, e - b);
}

void TextEdit::set_cursor(size_t pos, bool select)
{
  cursor_ = utf8::floor_boundary(text_, std::min(pos, text_.size()));
  if (!select) {
    anchor_ = cursor_;
  }
  last_op_ = Op::None;
}

void TextEdit::move_left(bool word, bool select)
{
  if (has_selection() && !select) {
    set_cursor(selection().first, false);
    return;
  }
  set_cursor(word ? prev_word_boundary(text_, cursor_) : utf8::prev(text_, cursor_), select);
}

void TextEdit::move_right(bool word, bool select)
{
  if (has_selection() && !select) {
    set_cursor(selection().second, false);
    return;
  }
  set_cursor(word ? next_word_boundary(text_, cursor_) : utf8::next(text_, cursor_), select);
}

void TextEdit::home(bool select)
{
  set_cursor(0, select);
}

void TextEdit::end(bool select)
{
  set_cursor(text_.size(), select);
}

void TextEdit::select_all()
{
  anchor_ = 0;
  cursor_ = text_.size();
  last_op_ = Op::None;
}

void TextEdit::select_word_at(size_t pos)
{
  size_t b, e;
  word_at(text_, pos, &b, &e);
  anchor_ = b;
  cursor_ = e;
  last_op_ = Op::None;
}

void TextEdit::push_undo(Op op)
{
  /* Coalesce consecutive typing into one step per word; a space after a word starts a new one. */
  if (op == Op::Type && last_op_ == Op::Type && !last_was_space_) {
    return;
  }
  if (op == Op::Delete && last_op_ == Op::Delete) {
    return;
  }
  undo_.push_back({text_, cursor_, anchor_});
  if (undo_.size() > MAX_UNDO) {
    undo_.erase(undo_.begin());
  }
  redo_.clear();
}

void TextEdit::replace_selection(std::string_view s)
{
  const auto [b, e] = selection();
  std::string ins = utf8::sanitize(s);
  if (max_len_ > 0) {
    const size_t keep = utf8::count(text_) - utf8::count(std::string_view(text_).substr(b, e - b));
    size_t room = max_len_ > keep ? max_len_ - keep : 0;
    size_t p = 0;
    while (p < ins.size() && room > 0) {
      p = utf8::next(ins, p);
      room--;
    }
    ins.resize(p);
  }
  text_.replace(b, e - b, ins);
  cursor_ = anchor_ = b + ins.size();
}

void TextEdit::insert(std::string_view s)
{
  if (s.empty() && !has_selection()) {
    return;
  }
  push_undo(has_selection() ? Op::Other : Op::Type);
  replace_selection(s);
  last_was_space_ = !s.empty() && utf8::is_space(utf8::decode(s, utf8::prev(s, s.size())));
  last_op_ = Op::Type;
}

void TextEdit::backspace(bool word)
{
  if (!has_selection()) {
    if (cursor_ == 0) {
      return;
    }
    anchor_ = cursor_;
    cursor_ = word ? prev_word_boundary(text_, cursor_) : utf8::prev(text_, cursor_);
  }
  push_undo(Op::Delete);
  replace_selection("");
  last_op_ = Op::Delete;
}

void TextEdit::delete_forward(bool word)
{
  if (!has_selection()) {
    if (cursor_ >= text_.size()) {
      return;
    }
    anchor_ = cursor_;
    cursor_ = word ? next_word_boundary(text_, cursor_) : utf8::next(text_, cursor_);
  }
  push_undo(Op::Delete);
  replace_selection("");
  last_op_ = Op::Delete;
}

std::string TextEdit::cut()
{
  if (!has_selection()) {
    return {};
  }
  std::string s = selected_text();
  push_undo(Op::Other);
  replace_selection("");
  last_op_ = Op::Other;
  return s;
}

void TextEdit::paste(std::string_view s)
{
  std::string clean;
  clean.reserve(s.size());
  for (const char c : s) {
    if (c == '\r') {
      continue;
    }
    clean += (c == '\n' || c == '\t') ? ' ' : c;
  }
  push_undo(Op::Other);
  replace_selection(clean);
  last_op_ = Op::Other;
}

bool TextEdit::undo()
{
  if (undo_.empty()) {
    return false;
  }
  redo_.push_back({text_, cursor_, anchor_});
  const Snapshot s = undo_.back();
  undo_.pop_back();
  text_ = s.text;
  cursor_ = s.cursor;
  anchor_ = s.anchor;
  preedit_.clear();
  last_op_ = Op::None;
  return true;
}

bool TextEdit::redo()
{
  if (redo_.empty()) {
    return false;
  }
  undo_.push_back({text_, cursor_, anchor_});
  const Snapshot s = redo_.back();
  redo_.pop_back();
  text_ = s.text;
  cursor_ = s.cursor;
  anchor_ = s.anchor;
  preedit_.clear();
  last_op_ = Op::None;
  return true;
}

void TextEdit::set_preedit(std::string preedit, size_t caret)
{
  if (!preedit.empty() && preedit_.empty() && has_selection()) {
    /* Starting a composition replaces the selection, as native text fields do. */
    push_undo(Op::Other);
    replace_selection("");
    last_op_ = Op::Other;
  }
  preedit_ = utf8::sanitize(preedit);
  preedit_caret_ = utf8::floor_boundary(preedit_, std::min(caret, preedit_.size()));
}

void TextEdit::commit(std::string_view s)
{
  preedit_.clear();
  preedit_caret_ = 0;
  if (!s.empty()) {
    /* A committed composition is its own undo step. */
    last_op_ = Op::None;
    insert(s);
    last_op_ = Op::Other;
  }
}

std::string TextEdit::display_text() const
{
  if (preedit_.empty()) {
    return text_;
  }
  std::string s = text_;
  s.insert(cursor_, preedit_);
  return s;
}

size_t TextEdit::display_caret() const
{
  return cursor_ + (preedit_.empty() ? 0 : preedit_caret_);
}

std::pair<size_t, size_t> TextEdit::display_preedit() const
{
  return {cursor_, cursor_ + preedit_.size()};
}

}  // namespace stk::ui
