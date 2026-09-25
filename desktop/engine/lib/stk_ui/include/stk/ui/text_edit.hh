/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Single-line text editing model: UTF-8 buffer, caret and selection (byte offsets on codepoint
 * boundaries), IME preedit (composition) display, word navigation that handles CJK, and
 * undo/redo with typing coalescing. Pure data; the text field widget drives it from events.
 */
#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace stk::ui {

class TextEdit {
 public:
  TextEdit() = default;
  explicit TextEdit(std::string text) { set_text(std::move(text)); }

  /** Replaces the content, clears undo history and preedit; caret at the end. */
  void set_text(std::string text, bool select_all = false);
  const std::string &text() const { return text_; }

  size_t cursor() const { return cursor_; }
  size_t anchor() const { return anchor_; }
  bool has_selection() const { return cursor_ != anchor_; }
  /** [begin, end) of the selection. */
  std::pair<size_t, size_t> selection() const;
  std::string selected_text() const;

  /* Caret movement; `select` extends the selection from the anchor. */
  void set_cursor(size_t pos, bool select = false);
  void move_left(bool word, bool select);
  void move_right(bool word, bool select);
  void home(bool select = false);
  void end(bool select = false);
  void select_all();
  void select_word_at(size_t pos);

  /* Editing (each is one undo step, typing is coalesced per word). */
  void insert(std::string_view s);
  void backspace(bool word);
  void delete_forward(bool word);
  /** Removes the selection and returns it (cut). */
  std::string cut();
  /** Inserts clipboard text: newlines and tabs become spaces. */
  void paste(std::string_view s);

  bool can_undo() const { return !undo_.empty(); }
  bool can_redo() const { return !redo_.empty(); }
  bool undo();
  bool redo();

  /* IME composition. The preedit is shown at the caret and not part of text() until committed. */
  /** Updates the composition; an empty string ends it. `caret` is a byte offset in `preedit`. */
  void set_preedit(std::string preedit, size_t caret);
  /** Inserts committed IME text (replaces the selection) and clears the preedit. */
  void commit(std::string_view s);
  const std::string &preedit() const { return preedit_; }
  size_t preedit_caret() const { return preedit_caret_; }
  bool composing() const { return !preedit_.empty(); }

  /** text() with the preedit inserted at the caret. */
  std::string display_text() const;
  /** Caret byte offset in display_text() (inside the preedit while composing). */
  size_t display_caret() const;
  /** [begin, end) of the preedit in display_text() (empty when not composing). */
  std::pair<size_t, size_t> display_preedit() const;

  /** Optional maximum length in codepoints (0 = unlimited). */
  void set_max_length(size_t n) { max_len_ = n; }

 private:
  struct Snapshot {
    std::string text;
    size_t cursor, anchor;
  };
  enum class Op { None, Type, Delete, Other };

  void push_undo(Op op);
  void replace_selection(std::string_view s);

  std::string text_;
  size_t cursor_ = 0;
  size_t anchor_ = 0;
  std::string preedit_;
  size_t preedit_caret_ = 0;
  std::vector<Snapshot> undo_;
  std::vector<Snapshot> redo_;
  Op last_op_ = Op::None;
  bool last_was_space_ = false;
  size_t max_len_ = 0;
};

}  // namespace stk::ui
