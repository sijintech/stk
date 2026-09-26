/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* UTF-8 helpers (RFC 3629: no overlong forms, no surrogates, at most U+10FFFF).
 * Invalid input is replaced by U+FFFD per "maximal subpart" (the rule of Python's
 * errors="replace", WHATWG and ICU), so a stream decoded in chunks gives exactly the
 * same text as the whole buffer decoded at once. */

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace stk::core::utf8 {

inline constexpr char32_t kReplacement = 0xFFFD;

/** Result of decoding one code point at a position. */
struct Decoded {
  char32_t code_point;  /* kReplacement when invalid */
  uint8_t length;       /* bytes consumed (>= 1 unless at the end) */
  bool valid;
  /** The bytes are a valid but incomplete prefix of a sequence that ends the input. */
  bool incomplete;
};

/** Decode the code point starting at `text[pos]` (pos < text.size()). */
Decoded decode(std::string_view text, size_t pos);

bool is_valid(std::string_view text);
/** Byte offset of the first invalid (or truncated) sequence, or text.size() when valid. */
size_t first_invalid(std::string_view text);

/** Replace invalid sequences with U+FFFD (maximal subpart). */
std::string sanitize(std::string_view text);

void append(std::string &out, char32_t code_point);
std::string encode(char32_t code_point);

size_t count_code_points(std::string_view text);
std::u32string to_utf32(std::string_view text);
std::string from_utf32(std::u32string_view text);
/** UTF-16 (Windows APIs); unpaired surrogates become U+FFFD. */
std::u16string to_utf16(std::string_view text);
std::string from_utf16(std::u16string_view text);

/** Longest prefix of at most `max_bytes` bytes that does not split a code point. */
std::string_view truncate_bytes(std::string_view text, size_t max_bytes);

/** Terminal/monospace columns of a code point: 0 for combining marks and controls, 2 for East Asian
 * wide/fullwidth (CJK, Hangul, kana, fullwidth forms, most emoji), else 1. */
int display_width(char32_t code_point);
int display_width(std::string_view text);

/** Truncate to at most `max_columns` display columns without splitting a code point or a wide
 * character; appends `ellipsis` (counted in the budget) when shortened. */
std::string truncate_display(std::string_view text, int max_columns, std::string_view ellipsis = "…");

/**
 * Incremental decoder for byte streams split at arbitrary positions (child-process logs,
 * NDJSON frames): feed() returns the valid UTF-8 text of all complete sequences, keeping a
 * trailing incomplete sequence (at most 3 bytes) for the next call; finish() flushes it as
 * U+FFFD. Invalid bytes are replaced as by sanitize() on the concatenated input.
 */
class StreamDecoder {
 public:
  std::string feed(std::string_view bytes);
  std::string finish();
  size_t pending() const
  {
    return pending_.size();
  }

 private:
  std::string pending_;
};

}  // namespace stk::core::utf8
