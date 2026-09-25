/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The "Bridge log" panel's backing store: the bridge's stderr (free-form diagnostics, §1) plus the
 * client's own lifecycle notes, as a bounded ring of UTF-8 lines. Thread-safe.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include "stk/core/utf8.hh"

namespace stk::bridge {

class LogRing {
 public:
  enum class Source : uint8_t { Stderr, Client };
  struct Line {
    uint64_t seq = 0; /* 1, 2, ... (never reused, also across clear()) */
    double wall_time = 0.0;
    Source source = Source::Stderr;
    std::string text; /* valid UTF-8, no newline */
  };

  explicit LogRing(size_t capacity_lines = 4000, size_t max_line_bytes = 16 * 1024);

  /** Raw stderr bytes, split into lines (a partial line waits for its end; invalid UTF-8 -> U+FFFD). */
  void append_bytes(std::string_view bytes);
  /** Flushes a pending partial stderr line (the child exited). */
  void flush();
  void append_line(std::string_view text, Source source = Source::Client);

  /** Lines with seq > `after` still in the ring (the UI polls with the last seq it showed). */
  std::vector<Line> lines_after(uint64_t after = 0) const;
  uint64_t last_seq() const;
  /** Every line in the ring joined with '\n'. */
  std::string text() const;
  size_t dropped() const;

 private:
  void push_locked(std::string text, Source source);

  mutable std::mutex mutex_;
  std::deque<Line> lines_;
  size_t capacity_;
  size_t max_line_bytes_;
  uint64_t seq_ = 0;
  size_t dropped_ = 0;
  std::string partial_;
  core::utf8::StreamDecoder decoder_;
};

}  // namespace stk::bridge
