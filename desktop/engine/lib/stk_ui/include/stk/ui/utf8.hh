/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * UTF-8 helpers of stk_ui: thin wrappers over stk_core's decoder (RFC 3629, maximal-subpart
 * replacement) plus what stk_core does not have — codepoint stepping, the character classes used
 * by CJK line breaking and word navigation, and FNV-1a hashing for widget ids.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace stk::ui::utf8 {

/** Decodes the codepoint at `pos`; invalid bytes decode as U+FFFD with length 1. */
uint32_t decode(std::string_view s, size_t pos, size_t *len = nullptr);
/** Byte index of the next codepoint start after `pos` (clamped to size). */
size_t next(std::string_view s, size_t pos);
/** Byte index of the codepoint start before `pos` (0 at the start). */
size_t prev(std::string_view s, size_t pos);
/** Rounds `pos` down to a codepoint boundary. */
size_t floor_boundary(std::string_view s, size_t pos);
size_t count(std::string_view s);
void append(std::string &out, uint32_t cp);
/** Replaces invalid sequences with U+FFFD. */
std::string sanitize(std::string_view s);

/* Character classes (Unicode subsets relevant to zh/ja/ko/en UI text). */
bool is_space(uint32_t cp);
/** Han ideographs, CJK symbols, kana, hangul, full-width forms: breakable on both sides. */
bool is_cjk(uint32_t cp);
bool is_han(uint32_t cp);
bool is_kana(uint32_t cp);
bool is_hangul(uint32_t cp);
/** East Asian wide / full-width (two columns). */
bool is_wide(uint32_t cp);
/** Kinsoku: must not start a line (closing punctuation, 。，、！？）」 etc.). */
bool no_break_before(uint32_t cp);
/** Kinsoku: must not end a line (opening brackets （「『【 etc.). */
bool no_break_after(uint32_t cp);
/** Letters and digits of alphabetic scripts (word characters for navigation). */
bool is_word_char(uint32_t cp);
bool is_punct(uint32_t cp);

/** Maps full-width ASCII variants (U+FF01..U+FF5E) and the ideographic space to ASCII. */
std::string fold_fullwidth(std::string_view s);

/** 64-bit FNV-1a. */
constexpr uint64_t FNV_OFFSET = 1469598103934665603ull;
inline uint64_t fnv1a(std::string_view s, uint64_t h = FNV_OFFSET)
{
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ull;
  }
  return h;
}
inline uint64_t hash_combine(uint64_t seed, uint64_t v)
{
  for (int i = 0; i < 8; i++) {
    seed ^= (v >> (i * 8)) & 0xff;
    seed *= 1099511628211ull;
  }
  return seed;
}

}  // namespace stk::ui::utf8
