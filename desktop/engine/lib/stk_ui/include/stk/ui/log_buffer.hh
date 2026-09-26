/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Append-only log model for the log view: decodes UTF-8 incrementally (a character split across
 * chunks is kept until complete, invalid bytes become U+FFFD), strips ANSI escapes (also when split
 * across chunks),
 * splits lines on \n (\r\n counts once, a lone \r rewinds the current line like a terminal
 * progress bar), expands tabs and keeps at most `max_lines` lines.
 */
#pragma once

#include <cstdint>
#include <deque>
#include <string>
#include <string_view>

#include "stk/core/utf8.hh"
#include "stk/ui/text.hh"

namespace stk::ui {

class LogBuffer {
 public:
  explicit LogBuffer(size_t max_lines = 200000) : max_lines_(max_lines) {}

  /** Appends raw bytes (e.g. a child process pipe). */
  void append(std::string_view chunk);
  void clear();

  /** Lines including the unterminated last one (when non-empty). */
  size_t line_count() const;
  std::string_view line(size_t i) const;
  /** Lines dropped from the front because of max_lines. */
  uint64_t dropped() const { return dropped_; }
  /** Incremented on every change (views use it to follow the tail). */
  uint64_t version() const { return version_; }

 private:
  void push_line(std::string s);

  std::deque<std::string> lines_;
  std::string partial_;
  bool rewind_ = false;
  bool pending_cr_ = false;
  core::utf8::StreamDecoder utf8_;
  AnsiStripper ansi_;
  size_t max_lines_;
  uint64_t dropped_ = 0;
  uint64_t version_ = 0;
};

}  // namespace stk::ui
