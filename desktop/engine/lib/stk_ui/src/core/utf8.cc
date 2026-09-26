/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/utf8.hh"

#include "stk/core/utf8.hh"

#include <algorithm>

namespace stk::ui::utf8 {

static bool is_cont(unsigned char c)
{
  return (c & 0xC0) == 0x80;
}

uint32_t decode(std::string_view s, size_t pos, size_t *len)
{
  if (pos >= s.size()) {
    if (len) {
      *len = 0;
    }
    return 0;
  }
  const core::utf8::Decoded d = core::utf8::decode(s, pos);
  if (len) {
    *len = std::max<size_t>(1, d.length);
  }
  return uint32_t(d.code_point);
}

size_t next(std::string_view s, size_t pos)
{
  if (pos >= s.size()) {
    return s.size();
  }
  size_t len = 1;
  decode(s, pos, &len);
  return pos + (len ? len : 1);
}

size_t prev(std::string_view s, size_t pos)
{
  if (pos == 0) {
    return 0;
  }
  pos = std::min(pos, s.size());
  size_t p = pos - 1;
  /* Step back over continuation bytes (at most 3), then verify the sequence decodes to pos. */
  size_t k = 0;
  while (p > 0 && k < 3 && is_cont((unsigned char)s[p])) {
    p--;
    k++;
  }
  size_t len = 1;
  decode(s, p, &len);
  if (p + len == pos) {
    return p;
  }
  return pos - 1;
}

size_t floor_boundary(std::string_view s, size_t pos)
{
  if (pos >= s.size()) {
    return s.size();
  }
  size_t p = 0;
  while (true) {
    const size_t n = next(s, p);
    if (n > pos) {
      return p;
    }
    if (n == pos) {
      return n;
    }
    p = n;
  }
}

size_t count(std::string_view s)
{
  return core::utf8::count_code_points(s);
}

void append(std::string &out, uint32_t cp)
{
  core::utf8::append(out, char32_t(cp));
}

std::string sanitize(std::string_view s)
{
  return core::utf8::sanitize(s);
}

static bool in(uint32_t cp, uint32_t a, uint32_t b)
{
  return cp >= a && cp <= b;
}

bool is_space(uint32_t cp)
{
  return cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r' || cp == 0x3000 || cp == 0xA0 ||
         in(cp, 0x2000, 0x200A) || cp == 0x202F || cp == 0x205F;
}

bool is_han(uint32_t cp)
{
  return in(cp, 0x4E00, 0x9FFF) || in(cp, 0x3400, 0x4DBF) || in(cp, 0x20000, 0x3134F) ||
         in(cp, 0xF900, 0xFAFF) || in(cp, 0x2E80, 0x2FDF) || cp == 0x3005 || cp == 0x3007;
}

bool is_kana(uint32_t cp)
{
  return in(cp, 0x3040, 0x309F) || in(cp, 0x30A0, 0x30FF) || in(cp, 0x31F0, 0x31FF) ||
         in(cp, 0xFF66, 0xFF9F);
}

bool is_hangul(uint32_t cp)
{
  return in(cp, 0xAC00, 0xD7AF) || in(cp, 0x1100, 0x11FF) || in(cp, 0x3130, 0x318F);
}

bool is_cjk(uint32_t cp)
{
  return is_han(cp) || is_kana(cp) || is_hangul(cp) || in(cp, 0x3000, 0x303F) ||
         in(cp, 0xFF00, 0xFFEF) || in(cp, 0x3100, 0x312F) || in(cp, 0x3200, 0x33FF) ||
         in(cp, 0xFE30, 0xFE4F);
}

bool is_wide(uint32_t cp)
{
  return core::utf8::display_width(char32_t(cp)) == 2;
}

bool no_break_before(uint32_t cp)
{
  switch (cp) {
    /* ASCII closing punctuation. */
    case '!': case ')': case ',': case '.': case ':': case ';': case '?': case ']': case '}':
    case '%':
    /* General punctuation. */
    case 0x2019: case 0x201D: case 0x2025: case 0x2026: case 0x2030: case 0x2032: case 0x2033:
    case 0x2103: case 0x00B0:
    /* CJK symbols and punctuation. */
    case 0x3001: case 0x3002: case 0x3003: case 0x3005: case 0x3006: case 0x3009: case 0x300B:
    case 0x300D: case 0x300F: case 0x3011: case 0x3015: case 0x3017: case 0x3019: case 0x301B:
    case 0x301C: case 0x301E: case 0x301F: case 0x303B:
    /* Small kana, prolonged sound mark, iteration marks, middle dot. */
    case 0x3041: case 0x3043: case 0x3045: case 0x3047: case 0x3049: case 0x3063: case 0x3083:
    case 0x3085: case 0x3087: case 0x308E: case 0x3095: case 0x3096: case 0x309D: case 0x309E:
    case 0x30A1: case 0x30A3: case 0x30A5: case 0x30A7: case 0x30A9: case 0x30C3: case 0x30E3:
    case 0x30E5: case 0x30E7: case 0x30EE: case 0x30F5: case 0x30F6: case 0x30FB: case 0x30FC:
    case 0x30FD: case 0x30FE:
    /* Full-width / half-width forms. */
    case 0xFF01: case 0xFF05: case 0xFF09: case 0xFF0C: case 0xFF0E: case 0xFF1A: case 0xFF1B:
    case 0xFF1F: case 0xFF3D: case 0xFF5D: case 0xFF5E: case 0xFF61: case 0xFF63: case 0xFF64:
    case 0xFF65: case 0xFF9E: case 0xFF9F:
      return true;
    default:
      return in(cp, 0x31F0, 0x31FF) || in(cp, 0xFE50, 0xFE57);
  }
}

bool no_break_after(uint32_t cp)
{
  switch (cp) {
    case '(': case '[': case '{':
    case 0x2018: case 0x201C:
    case 0x3008: case 0x300A: case 0x300C: case 0x300E: case 0x3010: case 0x3014: case 0x3016:
    case 0x3018: case 0x301A: case 0x301D:
    case 0xFF08: case 0xFF3B: case 0xFF5B: case 0xFF62: case 0xFF04: case 0xFFE1: case 0xFFE5:
      return true;
    default:
      return false;
  }
}

bool is_punct(uint32_t cp)
{
  if (cp < 0x80) {
    return (cp >= 0x21 && cp <= 0x2F) || (cp >= 0x3A && cp <= 0x40) || (cp >= 0x5B && cp <= 0x60 && cp != '_') ||
           (cp >= 0x7B && cp <= 0x7E);
  }
  return (in(cp, 0x3000, 0x303F) && cp != 0x3005 && cp != 0x3007 && cp != 0x3000) ||
         in(cp, 0xFF01, 0xFF0F) || in(cp, 0xFF1A, 0xFF20) || in(cp, 0xFF3B, 0xFF40) ||
         in(cp, 0xFF5B, 0xFF65) || in(cp, 0x2010, 0x2027) || in(cp, 0x2030, 0x205E) ||
         in(cp, 0x00A1, 0x00BF) || cp == 0x30FB;
}

bool is_word_char(uint32_t cp)
{
  if (cp < 0x80) {
    return (cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z') || cp == '_';
  }
  return !is_space(cp) && !is_punct(cp) && !is_cjk(cp);
}

std::string fold_fullwidth(std::string_view s)
{
  std::string out;
  out.reserve(s.size());
  for (size_t p = 0; p < s.size();) {
    size_t len = 1;
    const uint32_t cp = decode(s, p, &len);
    if (in(cp, 0xFF01, 0xFF5E)) {
      out += char(cp - 0xFEE0);
    }
    else if (cp == 0x3000) {
      out += ' ';
    }
    else {
      out.append(s.substr(p, len));
    }
    p += len;
  }
  return out;
}

}  // namespace stk::ui::utf8
