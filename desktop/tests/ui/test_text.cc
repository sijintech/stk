/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file UTF-8 helpers, CJK line breaking, word navigation, clipping, ANSI stripping, LogBuffer. */
#include <gtest/gtest.h>

#include "stk/ui/log_buffer.hh"
#include "stk/ui/text.hh"
#include "stk/ui/utf8.hh"

using namespace stk::ui;

namespace {

std::vector<std::string> wrap(std::string_view text, float max_w, float size = 10.0f)
{
  FakeTextMeasurer m;
  std::vector<std::string> out;
  for (const TextLine &l : break_lines(text, max_w, m, {FontKind::Regular, size})) {
    out.emplace_back(text.substr(l.begin, l.end - l.begin));
  }
  return out;
}

using V = std::vector<std::string>;

}  // namespace

TEST(Utf8, DecodeStepAndSanitize)
{
  const std::string s = "a\xe4\xb8\xad\xf0\x9f\x98\x80z"; /* a 中 😀 z */
  size_t len = 0;
  EXPECT_EQ(utf8::decode(s, 1, &len), 0x4E2Du);
  EXPECT_EQ(len, 3u);
  EXPECT_EQ(utf8::decode(s, 4, &len), 0x1F600u);
  EXPECT_EQ(utf8::next(s, 1), 4u);
  EXPECT_EQ(utf8::prev(s, 8), 4u);
  EXPECT_EQ(utf8::prev(s, 4), 1u);
  EXPECT_EQ(utf8::count(s), 4u);
  EXPECT_EQ(utf8::floor_boundary(s, 2), 1u);
  EXPECT_EQ(utf8::sanitize("a\xff" "b"), "a\xef\xbf\xbd" "b");
  EXPECT_EQ(utf8::fold_fullwidth("\xef\xbc\x91\xef\xbc\x8e\xef\xbc\x95"), "1.5"); /* １．５ */
}

TEST(LineBreak, BreaksBetweenIdeographsWithKinsoku)
{
  /* "中文段落。下一句": 。 may not start a line, so 落 moves down with it. */
  EXPECT_EQ(wrap("\xe4\xb8\xad\xe6\x96\x87\xe6\xae\xb5\xe8\x90\xbd\xe3\x80\x82\xe4\xb8\x8b\xe4\xb8\x80\xe5\x8f\xa5", 40),
            (V{"\xe4\xb8\xad\xe6\x96\x87\xe6\xae\xb5", "\xe8\x90\xbd\xe3\x80\x82\xe4\xb8\x8b\xe4\xb8\x80",
               "\xe5\x8f\xa5"}));
  /* Full-width comma and closing bracket stay on the previous line: "甲乙，丙）丁". */
  const V lines = wrap("\xe7\x94\xb2\xe4\xb9\x99\xef\xbc\x8c\xe4\xb8\x99\xef\xbc\x89\xe4\xb8\x81", 20);
  for (const std::string &l : lines) {
    EXPECT_NE(l.substr(0, 3), "\xef\xbc\x8c") << l;
    EXPECT_NE(l.substr(0, 3), "\xef\xbc\x89") << l;
  }
  /* Opening bracket 「 never ends a line: "文文「引用」". */
  for (const std::string &l : wrap("\xe6\x96\x87\xe6\x96\x87\xe3\x80\x8c\xe5\xbc\x95\xe7\x94\xa8\xe3\x80\x8d", 30)) {
    EXPECT_FALSE(l.size() >= 3 && l.substr(l.size() - 3) == "\xe3\x80\x8c") << l;
  }
}

TEST(LineBreak, KeepsLatinWordsTogether)
{
  EXPECT_EQ(wrap("hello world foo", 60), (V{"hello world", "foo"}));
  EXPECT_EQ(wrap("hello world foo", 1000), (V{"hello world foo"}));
  /* CJK / Latin boundaries are break opportunities: "STK你好world". */
  EXPECT_EQ(wrap("STK\xe4\xbd\xa0\xe5\xa5\xbdworld", 30), (V{"STK\xe4\xbd\xa0", "\xe5\xa5\xbd", "world"}));
  /* An over-long word is split by character. */
  EXPECT_EQ(wrap("abcdefghij", 20), (V{"abcd", "efgh", "ij"}));
  /* Hyphenated words may break after the hyphen. */
  EXPECT_EQ(wrap("well-known", 30), (V{"well-", "known"}));
  /* Latin punctuation stays with its word. */
  EXPECT_EQ(wrap("one, two.", 25), (V{"one,", "two."}));
}

TEST(LineBreak, NewlinesAndEmpty)
{
  EXPECT_EQ(wrap("a\nb", 100), (V{"a", "b"}));
  EXPECT_EQ(wrap("a\n", 100), (V{"a", ""}));
  EXPECT_EQ(wrap("", 100), (V{""}));
  FakeTextMeasurer m;
  const auto lines = break_lines("ab cd", 0, m, {FontKind::Regular, 10});
  ASSERT_EQ(lines.size(), 1u);
  EXPECT_FLOAT_EQ(lines[0].width, 25.0f);
}

TEST(WordNav, MixedScripts)
{
  const std::string s = "hello \xe4\xb8\x96\xe7\x95\x8c" "abc,def"; /* hello 世界abc,def */
  EXPECT_EQ(next_word_boundary(s, 0), 6u);
  EXPECT_EQ(next_word_boundary(s, 6), 12u);
  EXPECT_EQ(next_word_boundary(s, 12), 15u);
  EXPECT_EQ(next_word_boundary(s, 15), 16u);
  EXPECT_EQ(next_word_boundary(s, 16), 19u);
  EXPECT_EQ(prev_word_boundary(s, 19), 16u);
  EXPECT_EQ(prev_word_boundary(s, 16), 15u);
  EXPECT_EQ(prev_word_boundary(s, 15), 12u);
  EXPECT_EQ(prev_word_boundary(s, 12), 6u);
  EXPECT_EQ(prev_word_boundary(s, 6), 0u);
  size_t b, e;
  word_at(s, 7, &b, &e); /* inside 世界 (offset rounded down to the codepoint) */
  EXPECT_EQ(b, 6u);
  EXPECT_EQ(e, 12u);
  /* Kana and ideographs are different words: 日本語のテキスト */
  const std::string j = "\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe3\x81\xae\xe3\x83\x86\xe3\x82\xad\xe3\x82\xb9\xe3\x83\x88";
  EXPECT_EQ(next_word_boundary(j, 0), 9u);
}

TEST(Clip, Ellipsis)
{
  FakeTextMeasurer m;
  const FontStyle f{FontKind::Regular, 10};
  EXPECT_EQ(clip_text("abcdef", 100, m, f), "abcdef");
  const std::string c = clip_text("abcdefghij", 30, m, f);
  EXPECT_EQ(c, "abcd\xe2\x80\xa6");
  EXPECT_LE(m.width(c, f), 30.0f);
  EXPECT_EQ(clip_text("\xe4\xb8\xad\xe6\x96\x87\xe5\xad\x97", 25, m, f), "\xe4\xb8\xad\xe2\x80\xa6");
}

TEST(Ansi, StripsSequencesAcrossChunks)
{
  EXPECT_EQ(strip_ansi("\x1b[1;31mred\x1b[0m plain"), "red plain");
  EXPECT_EQ(strip_ansi("\x1b]0;title\x07ok"), "ok");
  EXPECT_EQ(strip_ansi("\x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\"), "link");
  EXPECT_EQ(strip_ansi("a\x07" "b\x1b(Bc"), "abc");
  AnsiStripper st;
  EXPECT_EQ(st.feed("x\x1b[3"), "x");
  EXPECT_EQ(st.feed("2;1my"), "y");
}

TEST(Log, LinesCarriageReturnAndCap)
{
  LogBuffer log(3);
  log.append("a\r\nb\rc\n");
  ASSERT_EQ(log.line_count(), 2u);
  EXPECT_EQ(log.line(0), "a");
  EXPECT_EQ(log.line(1), "c");
  log.append("\x1b[32mpart");
  EXPECT_EQ(log.line_count(), 3u);
  EXPECT_EQ(log.line(2), "part");
  log.append("ial\tx\n");
  EXPECT_EQ(log.line(2), "partial x");
  log.append("d\n");
  EXPECT_EQ(log.line_count(), 3u);
  EXPECT_EQ(log.dropped(), 1u);
  EXPECT_EQ(log.line(0), "c");
  const uint64_t v = log.version();
  log.append("e");
  EXPECT_GT(log.version(), v);
}

TEST(Log, Utf8SplitAcrossChunks)
{
  LogBuffer log;
  log.append("\xe4\xb8"); /* first two bytes of 中 */
  EXPECT_EQ(log.line_count(), 0u);
  log.append("\xad\xe6\x96\x87\n\xff!\n");
  ASSERT_EQ(log.line_count(), 2u);
  EXPECT_EQ(log.line(0), "\xe4\xb8\xad\xe6\x96\x87");
  EXPECT_EQ(log.line(1), "\xef\xbf\xbd!") << "invalid bytes become U+FFFD";
}
