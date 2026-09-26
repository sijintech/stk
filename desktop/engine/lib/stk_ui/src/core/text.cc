/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/text.hh"

#include <algorithm>
#include <cmath>

#include "stk/core/utf8.hh"
#include "stk/ui/utf8.hh"

namespace stk::ui {

/* -------------------------------------------------------------------- */
/* Measurement */

float TextMeasurer::caret_x(std::string_view text, size_t index, const FontStyle &style) const
{
  index = std::min(index, text.size());
  return index == 0 ? 0.0f : width(text.substr(0, index), style);
}

size_t TextMeasurer::index_at_x(std::string_view text, float x, const FontStyle &style) const
{
  if (x <= 0.0f || text.empty()) {
    return 0;
  }
  float prev_w = 0.0f;
  for (size_t p = 0; p < text.size();) {
    const size_t n = utf8::next(text, p);
    const float w = width(text.substr(0, n), style);
    if (w >= x) {
      return (x - prev_w < w - x) ? p : n;
    }
    prev_w = w;
    p = n;
  }
  return text.size();
}

float FakeTextMeasurer::advance(uint32_t cp, const FontStyle &style)
{
  const float em = style.size_px;
  if (cp == '\n' || cp == '\r') {
    return 0.0f;
  }
  if (cp < 0x80) {
    return (style.kind == FontKind::Mono ? 0.6f : 0.5f) * em;
  }
  if (utf8::is_wide(cp)) {
    return em;
  }
  return 0.6f * em;
}

float FakeTextMeasurer::width(std::string_view text, const FontStyle &style) const
{
  float w = 0.0f;
  for (size_t p = 0; p < text.size();) {
    size_t len = 1;
    const uint32_t cp = utf8::decode(text, p, &len);
    w += advance(cp, style);
    p += std::max<size_t>(len, 1);
  }
  return w;
}

FontMetrics FakeTextMeasurer::metrics(const FontStyle &style) const
{
  return {0.8f * style.size_px, 0.2f * style.size_px};
}

/* -------------------------------------------------------------------- */
/* Line breaking */

namespace {

struct Glyph {
  size_t offset;
  uint32_t cp;
  float advance;
};

bool break_allowed(uint32_t prev2, uint32_t prev, uint32_t cur)
{
  if (cur == '\n' || prev == '\n') {
    return false; /* Mandatory breaks are handled separately. */
  }
  if (utf8::is_space(cur)) {
    return false;
  }
  if (utf8::is_space(prev)) {
    return !utf8::no_break_before(cur);
  }
  if (utf8::no_break_before(cur) || utf8::no_break_after(prev)) {
    return false;
  }
  if (utf8::is_cjk(prev) || utf8::is_cjk(cur)) {
    return true;
  }
  /* "well-known": break after a hyphen between word characters. */
  if (prev == '-' && utf8::is_word_char(prev2) && utf8::is_word_char(cur)) {
    return true;
  }
  return false;
}

}  // namespace

std::vector<size_t> break_opportunities(std::string_view text)
{
  std::vector<size_t> out;
  uint32_t prev2 = 0, prev = 0;
  for (size_t p = 0; p < text.size();) {
    size_t len = 1;
    const uint32_t cp = utf8::decode(text, p, &len);
    if (p > 0 && break_allowed(prev2, prev, cp)) {
      out.push_back(p);
    }
    prev2 = prev;
    prev = cp;
    p += std::max<size_t>(len, 1);
  }
  return out;
}

std::vector<TextLine> break_lines(std::string_view text,
                                  float max_width,
                                  const TextMeasurer &measurer,
                                  const FontStyle &style)
{
  std::vector<Glyph> glyphs;
  glyphs.reserve(text.size());
  for (size_t p = 0; p < text.size();) {
    size_t len = 1;
    const uint32_t cp = utf8::decode(text, p, &len);
    len = std::max<size_t>(len, 1);
    glyphs.push_back({p, cp, cp == '\n' ? 0.0f : measurer.width(text.substr(p, len), style)});
    p += len;
  }
  const size_t n = glyphs.size();
  std::vector<float> prefix(n + 1, 0.0f);
  for (size_t i = 0; i < n; i++) {
    prefix[i + 1] = prefix[i] + glyphs[i].advance;
  }
  auto offset = [&](size_t gi) { return gi < n ? glyphs[gi].offset : text.size(); };

  std::vector<TextLine> lines;
  auto emit = [&](size_t g0, size_t g1) {
    size_t e = g1;
    while (e > g0 && utf8::is_space(glyphs[e - 1].cp)) {
      e--;
    }
    lines.push_back({offset(g0), offset(e), prefix[e] - prefix[g0]});
  };

  size_t start = 0;
  size_t last_break = 0; /* 0 = none (a break at the line start is useless). */
  uint32_t prev2 = 0, prev = 0;
  for (size_t k = 0; k < n; k++) {
    const uint32_t cp = glyphs[k].cp;
    if (cp == '\n') {
      emit(start, k);
      start = k + 1;
      last_break = 0;
      prev2 = prev = 0;
      continue;
    }
    if (k > start && break_allowed(prev2, prev, cp)) {
      last_break = k;
    }
    prev2 = prev;
    prev = cp;
    if (max_width <= 0.0f || utf8::is_space(cp)) {
      continue;
    }
    while (k >= start && prefix[k + 1] - prefix[start] > max_width && k > start) {
      if (last_break > start) {
        emit(start, last_break);
        start = last_break;
        last_break = 0;
        /* Re-scan break opportunities inside the carried-over segment. */
        for (size_t j = start + 1; j <= k; j++) {
          if (break_allowed(j >= 2 ? glyphs[j - 2].cp : 0, glyphs[j - 1].cp, glyphs[j].cp)) {
            last_break = j;
          }
        }
        if (last_break == k + 1) {
          last_break = 0;
        }
      }
      else {
        /* Emergency break inside an over-long word; keep closing punctuation attached. */
        size_t cut = k;
        if (utf8::no_break_before(cp) && cut > start + 1) {
          cut--;
        }
        emit(start, cut);
        start = cut;
        last_break = 0;
      }
    }
  }
  if (start < n || lines.empty() || (n > 0 && glyphs[n - 1].cp == '\n')) {
    emit(start, n);
  }
  return lines;
}

/* -------------------------------------------------------------------- */
/* Word navigation */

namespace {

enum class CharClass : uint8_t { Space, Word, Han, Kana, Hangul, Punct, Other };

CharClass char_class(uint32_t cp)
{
  if (utf8::is_space(cp)) {
    return CharClass::Space;
  }
  if (utf8::is_han(cp)) {
    return CharClass::Han;
  }
  if (utf8::is_kana(cp) || cp == 0x30FC) {
    return CharClass::Kana;
  }
  if (utf8::is_hangul(cp)) {
    return CharClass::Hangul;
  }
  if (utf8::is_punct(cp)) {
    return CharClass::Punct;
  }
  if (utf8::is_word_char(cp)) {
    return CharClass::Word;
  }
  return CharClass::Other;
}

CharClass class_at(std::string_view s, size_t pos)
{
  return char_class(utf8::decode(s, pos));
}

}  // namespace

size_t next_word_boundary(std::string_view text, size_t pos)
{
  pos = utf8::floor_boundary(text, pos);
  if (pos >= text.size()) {
    return text.size();
  }
  const CharClass c = class_at(text, pos);
  if (c != CharClass::Space) {
    while (pos < text.size() && class_at(text, pos) == c) {
      pos = utf8::next(text, pos);
    }
  }
  while (pos < text.size() && class_at(text, pos) == CharClass::Space) {
    pos = utf8::next(text, pos);
  }
  return pos;
}

size_t prev_word_boundary(std::string_view text, size_t pos)
{
  pos = utf8::floor_boundary(text, pos);
  while (pos > 0 && class_at(text, utf8::prev(text, pos)) == CharClass::Space) {
    pos = utf8::prev(text, pos);
  }
  if (pos == 0) {
    return 0;
  }
  const CharClass c = class_at(text, utf8::prev(text, pos));
  while (pos > 0 && class_at(text, utf8::prev(text, pos)) == c) {
    pos = utf8::prev(text, pos);
  }
  return pos;
}

void word_at(std::string_view text, size_t pos, size_t *r_begin, size_t *r_end)
{
  pos = utf8::floor_boundary(text, pos);
  if (text.empty()) {
    *r_begin = *r_end = 0;
    return;
  }
  if (pos >= text.size()) {
    pos = utf8::prev(text, text.size());
  }
  const CharClass c = class_at(text, pos);
  size_t b = pos, e = pos;
  while (b > 0 && class_at(text, utf8::prev(text, b)) == c) {
    b = utf8::prev(text, b);
  }
  while (e < text.size() && class_at(text, e) == c) {
    e = utf8::next(text, e);
  }
  *r_begin = b;
  *r_end = e;
}

/* -------------------------------------------------------------------- */
/* Clipping */

std::string clip_text(std::string_view text,
                      float max_width,
                      const TextMeasurer &measurer,
                      const FontStyle &style)
{
  if (measurer.width(text, style) <= max_width) {
    return std::string(text);
  }
  static constexpr std::string_view ELLIPSIS = "\xe2\x80\xa6";
  const float avail = max_width - measurer.width(ELLIPSIS, style);
  if (avail <= 0.0f) {
    return std::string();
  }
  /* Binary search over codepoint boundaries. */
  std::vector<size_t> bounds;
  for (size_t p = 0; p < text.size(); p = utf8::next(text, p)) {
    bounds.push_back(p);
  }
  size_t lo = 0, hi = bounds.size(); /* bounds[lo] fits. */
  while (hi - lo > 1) {
    const size_t mid = (lo + hi) / 2;
    if (measurer.width(text.substr(0, bounds[mid]), style) <= avail) {
      lo = mid;
    }
    else {
      hi = mid;
    }
  }
  size_t cut = bounds[lo];
  while (cut > 0 && utf8::is_space(utf8::decode(text, utf8::prev(text, cut)))) {
    cut = utf8::prev(text, cut);
  }
  std::string out(text.substr(0, cut));
  out += ELLIPSIS;
  return out;
}

/* -------------------------------------------------------------------- */
/* ANSI stripping */

std::string AnsiStripper::feed(std::string_view chunk)
{
  std::string out;
  out.reserve(chunk.size());
  for (const char ch : chunk) {
    const unsigned char c = (unsigned char)ch;
    switch (state_) {
      case State::Text:
        if (c == 0x1B) {
          state_ = State::Esc;
        }
        else if (c < 0x20 && c != '\n' && c != '\r' && c != '\t') {
          /* Drop other C0 controls (BEL, BS, ...). */
        }
        else if (c == 0x7F) {
        }
        else {
          out += ch;
        }
        break;
      case State::Esc:
        if (c == '[') {
          state_ = State::Csi;
        }
        else if (c == ']' || c == 'P' || c == '_' || c == '^' || c == 'X') {
          state_ = State::Osc; /* OSC, DCS, APC, PM, SOS: string terminated by BEL or ST. */
        }
        else if (c == '(' || c == ')' || c == '*' || c == '+' || c == '#' || c == '%') {
          state_ = State::Charset;
        }
        else {
          state_ = State::Text;
        }
        break;
      case State::Csi:
        if (c >= 0x40 && c <= 0x7E) {
          state_ = State::Text;
        }
        else if (c == 0x1B) {
          state_ = State::Esc;
        }
        break;
      case State::Osc:
        if (c == 0x07) {
          state_ = State::Text;
        }
        else if (c == 0x1B) {
          state_ = State::OscEsc;
        }
        break;
      case State::OscEsc:
        state_ = (c == '\\') ? State::Text : State::Osc;
        break;
      case State::Charset:
        state_ = State::Text;
        break;
    }
  }
  return out;
}

std::string strip_ansi(std::string_view s)
{
  AnsiStripper st;
  return st.feed(s);
}

std::string mask_text(const std::string_view text)
{
  std::string out;
  const size_t n = core::utf8::count_code_points(text);
  out.reserve(n * 3);
  for (size_t i = 0; i < n; i++) {
    out += "\xe2\x80\xa2";
  }
  return out;
}

size_t mask_offset(const std::string_view text, const size_t byte)
{
  return core::utf8::count_code_points(text.substr(0, std::min(byte, text.size()))) * 3;
}

size_t unmask_offset(const std::string_view text, const size_t masked)
{
  const size_t chars = masked / 3;
  size_t pos = 0;
  for (size_t c = 0; c < chars && pos < text.size(); c++) {
    pos += std::max<size_t>(1, core::utf8::decode(text, pos).length);
  }
  return std::min(pos, text.size());
}

}  // namespace stk::ui
