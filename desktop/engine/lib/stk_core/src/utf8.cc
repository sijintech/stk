/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/utf8.hh"

#include <algorithm>
#include <array>

namespace stk::core::utf8 {

Decoded decode(std::string_view text, size_t pos)
{
  const auto byte = [&](size_t i) { return uint8_t(text[i]); };
  const size_t n = text.size();
  const uint8_t b0 = byte(pos);
  if (b0 < 0x80) {
    return {b0, 1, true, false};
  }
  int need;
  uint8_t lo = 0x80, hi = 0xBF;
  char32_t cp;
  if (b0 >= 0xC2 && b0 <= 0xDF) {
    need = 1;
    cp = b0 & 0x1F;
  }
  else if (b0 >= 0xE0 && b0 <= 0xEF) {
    need = 2;
    cp = b0 & 0x0F;
    if (b0 == 0xE0) {
      lo = 0xA0;
    }
    else if (b0 == 0xED) {
      hi = 0x9F;
    }
  }
  else if (b0 >= 0xF0 && b0 <= 0xF4) {
    need = 3;
    cp = b0 & 0x07;
    if (b0 == 0xF0) {
      lo = 0x90;
    }
    else if (b0 == 0xF4) {
      hi = 0x8F;
    }
  }
  else {
    return {kReplacement, 1, false, false};
  }
  size_t i = pos + 1;
  for (int k = 0; k < need; k++, i++) {
    if (i >= n) {
      return {kReplacement, uint8_t(i - pos), false, true};
    }
    const uint8_t b = byte(i);
    if (b < lo || b > hi) {
      return {kReplacement, uint8_t(i - pos), false, false};
    }
    lo = 0x80;
    hi = 0xBF;
    cp = (cp << 6) | (b & 0x3F);
  }
  return {cp, uint8_t(need + 1), true, false};
}

size_t first_invalid(std::string_view text)
{
  size_t pos = 0;
  while (pos < text.size()) {
    if (uint8_t(text[pos]) < 0x80) {
      pos++;
      continue;
    }
    const Decoded d = decode(text, pos);
    if (!d.valid) {
      return pos;
    }
    pos += d.length;
  }
  return text.size();
}

bool is_valid(std::string_view text)
{
  return first_invalid(text) == text.size();
}

void append(std::string &out, char32_t cp)
{
  if (cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) {
    cp = kReplacement;
  }
  if (cp < 0x80) {
    out.push_back(char(cp));
  }
  else if (cp < 0x800) {
    out.push_back(char(0xC0 | (cp >> 6)));
    out.push_back(char(0x80 | (cp & 0x3F)));
  }
  else if (cp < 0x10000) {
    out.push_back(char(0xE0 | (cp >> 12)));
    out.push_back(char(0x80 | ((cp >> 6) & 0x3F)));
    out.push_back(char(0x80 | (cp & 0x3F)));
  }
  else {
    out.push_back(char(0xF0 | (cp >> 18)));
    out.push_back(char(0x80 | ((cp >> 12) & 0x3F)));
    out.push_back(char(0x80 | ((cp >> 6) & 0x3F)));
    out.push_back(char(0x80 | (cp & 0x3F)));
  }
}

std::string encode(char32_t cp)
{
  std::string out;
  append(out, cp);
  return out;
}

std::string sanitize(std::string_view text)
{
  std::string out;
  out.reserve(text.size());
  size_t pos = 0;
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    if (d.valid) {
      out.append(text.substr(pos, d.length));
    }
    else {
      append(out, kReplacement);
    }
    pos += d.length;
  }
  return out;
}

size_t count_code_points(std::string_view text)
{
  size_t count = 0, pos = 0;
  while (pos < text.size()) {
    pos += decode(text, pos).length;
    count++;
  }
  return count;
}

std::u32string to_utf32(std::string_view text)
{
  std::u32string out;
  out.reserve(text.size());
  size_t pos = 0;
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    out.push_back(d.code_point);
    pos += d.length;
  }
  return out;
}

std::string from_utf32(std::u32string_view text)
{
  std::string out;
  out.reserve(text.size());
  for (char32_t cp : text) {
    append(out, cp);
  }
  return out;
}

std::u16string to_utf16(std::string_view text)
{
  std::u16string out;
  out.reserve(text.size());
  size_t pos = 0;
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    pos += d.length;
    char32_t cp = d.code_point;
    if (cp >= 0x10000) {
      cp -= 0x10000;
      out.push_back(char16_t(0xD800 + (cp >> 10)));
      out.push_back(char16_t(0xDC00 + (cp & 0x3FF)));
    }
    else {
      out.push_back(char16_t(cp));
    }
  }
  return out;
}

std::string from_utf16(std::u16string_view text)
{
  std::string out;
  out.reserve(text.size());
  for (size_t i = 0; i < text.size(); i++) {
    const char32_t u = static_cast<uint16_t>(text[i]);
    if (u >= 0xD800 && u <= 0xDBFF && i + 1 < text.size() && text[i + 1] >= 0xDC00 && text[i + 1] <= 0xDFFF) {
      append(out, 0x10000 + ((u - 0xD800) << 10) + (static_cast<uint16_t>(text[i + 1]) - 0xDC00u));
      i++;
    }
    else {
      append(out, (u >= 0xD800 && u <= 0xDFFF) ? kReplacement : u);
    }
  }
  return out;
}

std::string_view truncate_bytes(std::string_view text, size_t max_bytes)
{
  if (text.size() <= max_bytes) {
    return text;
  }
  size_t pos = 0;
  while (pos < text.size()) {
    const size_t next = pos + decode(text, pos).length;
    if (next > max_bytes) {
      break;
    }
    pos = next;
  }
  return text.substr(0, pos);
}

namespace {

struct Range {
  char32_t lo, hi;
};

/* Zero-width: combining marks (the common blocks), zero-width format characters, variation selectors. */
constexpr std::array<Range, 18> kZeroWidth{{
    {0x0300, 0x036F}, {0x0483, 0x0489}, {0x0591, 0x05BD}, {0x0610, 0x061A}, {0x064B, 0x065F},
    {0x0E31, 0x0E31}, {0x0E34, 0x0E3A}, {0x0E47, 0x0E4E}, {0x1AB0, 0x1AFF}, {0x1DC0, 0x1DFF},
    {0x200B, 0x200F}, {0x202A, 0x202E}, {0x2060, 0x2064}, {0x20D0, 0x20FF}, {0x302A, 0x302D},
    {0x3099, 0x309A}, {0xFE00, 0xFE0F}, {0xFE20, 0xFE2F},
}};

/* East Asian Wide (W) and Fullwidth (F) ranges (Unicode 15 EastAsianWidth.txt, merged). */
constexpr std::array<Range, 36> kWide{{
    {0x1100, 0x115F},   {0x231A, 0x231B},   {0x2329, 0x232A},   {0x23E9, 0x23EC},   {0x23F0, 0x23F0},
    {0x23F3, 0x23F3},   {0x25FD, 0x25FE},   {0x2614, 0x2615},   {0x2648, 0x2653},   {0x267F, 0x267F},
    {0x2693, 0x2693},   {0x26A1, 0x26A1},   {0x26AA, 0x26AB},   {0x26BD, 0x26BE},   {0x26C4, 0x26C5},
    {0x26CE, 0x26CE},   {0x26D4, 0x26D4},   {0x26EA, 0x26EA},   {0x26F2, 0x26F5},   {0x26FA, 0x26FD},
    {0x2705, 0x2705},   {0x2E80, 0x303E},   {0x3041, 0x33FF},   {0x3400, 0x4DBF},   {0x4E00, 0x9FFF},
    {0xA000, 0xA4CF},   {0xA960, 0xA97F},   {0xAC00, 0xD7A3},   {0xF900, 0xFAFF},   {0xFE10, 0xFE19},
    {0xFE30, 0xFE6F},   {0xFF00, 0xFF60},   {0xFFE0, 0xFFE6},   {0x1F300, 0x1F64F}, {0x1F900, 0x1F9FF},
    {0x20000, 0x3FFFD},
}};

bool in(const auto &ranges, char32_t cp)
{
  for (const Range &r : ranges) {
    if (cp >= r.lo && cp <= r.hi) {
      return true;
    }
  }
  return false;
}

}  // namespace

int display_width(char32_t cp)
{
  if (cp == 0 || cp < 0x20 || (cp >= 0x7F && cp < 0xA0)) {
    return 0;
  }
  if (cp < 0x300) {
    return 1;
  }
  if (in(kZeroWidth, cp)) {
    return 0;
  }
  return in(kWide, cp) ? 2 : 1;
}

int display_width(std::string_view text)
{
  int width = 0;
  size_t pos = 0;
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    width += display_width(d.code_point);
    pos += d.length;
  }
  return width;
}

std::string truncate_display(std::string_view text, int max_columns, std::string_view ellipsis)
{
  if (display_width(text) <= max_columns) {
    return std::string(text);
  }
  const int budget = max_columns - display_width(ellipsis);
  if (budget < 0) {
    return std::string(truncate_display(ellipsis, max_columns, ""));
  }
  int width = 0;
  size_t pos = 0;
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    const int w = display_width(d.code_point);
    if (width + w > budget) {
      break;
    }
    width += w;
    pos += d.length;
  }
  /* Keep combining marks attached to the last kept base character. */
  while (pos < text.size()) {
    const Decoded d = decode(text, pos);
    if (display_width(d.code_point) != 0 || !d.valid) {
      break;
    }
    pos += d.length;
  }
  std::string out = sanitize(text.substr(0, pos));
  out.append(ellipsis);
  return out;
}

std::string StreamDecoder::feed(std::string_view bytes)
{
  std::string buffer;
  std::string_view input = bytes;
  if (!pending_.empty()) {
    buffer = pending_;
    buffer.append(bytes);
    pending_.clear();
    input = buffer;
  }
  std::string out;
  out.reserve(input.size());
  size_t pos = 0;
  while (pos < input.size()) {
    const Decoded d = decode(input, pos);
    if (d.incomplete) {
      pending_.assign(input.substr(pos));
      break;
    }
    if (d.valid) {
      out.append(input.substr(pos, d.length));
    }
    else {
      append(out, kReplacement);
    }
    pos += d.length;
  }
  return out;
}

std::string StreamDecoder::finish()
{
  if (pending_.empty()) {
    return {};
  }
  pending_.clear();
  return encode(kReplacement);
}

}  // namespace stk::core::utf8
