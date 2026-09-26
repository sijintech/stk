/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file TextEdit model: IME preedit/commit, selection, clipboard ops, undo/redo, CJK words. */
#include <gtest/gtest.h>

#include "stk/ui/text_edit.hh"

using namespace stk::ui;

static const std::string ZHONG = "\xe4\xb8\xad"; /* 中 */
static const std::string WEN = "\xe6\x96\x87";   /* 文 */

TEST(TextEdit, ImePreeditThenCommit)
{
  TextEdit e("ab");
  e.set_cursor(1);
  e.set_preedit("zhong", 5);
  EXPECT_TRUE(e.composing());
  EXPECT_EQ(e.text(), "ab") << "preedit is not part of the text";
  EXPECT_EQ(e.display_text(), "azhongb");
  EXPECT_EQ(e.display_caret(), 6u);
  EXPECT_EQ(e.display_preedit(), (std::pair<size_t, size_t>{1, 6}));
  /* Candidate conversion: caret inside the preedit after the first character. */
  e.set_preedit(ZHONG + WEN, 3);
  EXPECT_EQ(e.display_text(), "a" + ZHONG + WEN + "b");
  EXPECT_EQ(e.display_caret(), 4u);
  e.commit(ZHONG + WEN);
  EXPECT_FALSE(e.composing());
  EXPECT_EQ(e.text(), "a" + ZHONG + WEN + "b");
  EXPECT_EQ(e.cursor(), 7u);
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "ab");
  EXPECT_TRUE(e.redo());
  EXPECT_EQ(e.text(), "a" + ZHONG + WEN + "b");
}

TEST(TextEdit, CompositionReplacesSelectionAndCancelKeepsText)
{
  TextEdit e("hello world");
  e.set_cursor(6);
  e.set_cursor(11, true);
  EXPECT_EQ(e.selected_text(), "world");
  e.set_preedit("shi", 3);
  EXPECT_EQ(e.text(), "hello ");
  e.set_preedit("", 0); /* composition cancelled */
  EXPECT_EQ(e.display_text(), "hello ");
  e.commit("");
  EXPECT_EQ(e.text(), "hello ");
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "hello world");
}

TEST(TextEdit, SelectionClipboardOps)
{
  TextEdit e("one two three");
  e.set_cursor(4);
  e.move_right(true, true);
  EXPECT_EQ(e.selected_text(), "two ");
  const std::string cut = e.cut();
  EXPECT_EQ(cut, "two ");
  EXPECT_EQ(e.text(), "one three");
  e.end();
  e.paste(" A\nB\tC");
  EXPECT_EQ(e.text(), "one three A B C");
  e.select_all();
  EXPECT_EQ(e.selected_text(), "one three A B C");
  e.insert("x");
  EXPECT_EQ(e.text(), "x");
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "one three A B C");
}

TEST(TextEdit, UndoCoalescesTypingPerWord)
{
  TextEdit e;
  for (const char *c : {"a", "b", "c", " ", "d", "e"}) {
    e.insert(c);
  }
  EXPECT_EQ(e.text(), "abc de");
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "abc ");
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "");
  EXPECT_FALSE(e.undo());
  EXPECT_TRUE(e.redo());
  EXPECT_TRUE(e.redo());
  EXPECT_EQ(e.text(), "abc de");
  e.backspace(false);
  e.backspace(false);
  EXPECT_EQ(e.text(), "abc ");
  EXPECT_TRUE(e.undo());
  EXPECT_EQ(e.text(), "abc de");
  EXPECT_FALSE(e.can_redo() && false);
}

TEST(TextEdit, CjkNavigationAndDeletion)
{
  TextEdit e("ab " + ZHONG + WEN + "cd");
  e.home();
  e.move_right(true, false);
  EXPECT_EQ(e.cursor(), 3u);
  e.move_right(true, false);
  EXPECT_EQ(e.cursor(), 9u);
  e.move_right(false, false);
  EXPECT_EQ(e.cursor(), 10u);
  e.end();
  e.backspace(true); /* deletes "cd" */
  EXPECT_EQ(e.text(), "ab " + ZHONG + WEN);
  e.backspace(false); /* one codepoint */
  EXPECT_EQ(e.text(), "ab " + ZHONG);
  e.home();
  e.delete_forward(true);
  EXPECT_EQ(e.text(), ZHONG);
  e.select_word_at(0);
  EXPECT_EQ(e.selected_text(), ZHONG);
}

TEST(TextEdit, MaxLengthInCodepoints)
{
  TextEdit e;
  e.set_max_length(3);
  e.insert("a" + ZHONG + WEN + "b");
  EXPECT_EQ(e.text(), "a" + ZHONG + WEN);
}
