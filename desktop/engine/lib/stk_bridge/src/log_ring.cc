/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/bridge/log_ring.hh"

#include "stk/core/clock.hh"

namespace stk::bridge {

LogRing::LogRing(const size_t capacity_lines, const size_t max_line_bytes)
    : capacity_(capacity_lines ? capacity_lines : 1), max_line_bytes_(max_line_bytes ? max_line_bytes : 1)
{
}

void LogRing::push_locked(std::string text, const Source source)
{
  if (!text.empty() && text.back() == '\r') {
    text.pop_back();
  }
  if (text.size() > max_line_bytes_) {
    text = std::string(core::utf8::truncate_bytes(text, max_line_bytes_)) + "…";
  }
  Line line;
  line.seq = ++seq_;
  line.wall_time = core::wall_clock_seconds();
  line.source = source;
  line.text = std::move(text);
  lines_.push_back(std::move(line));
  while (lines_.size() > capacity_) {
    lines_.pop_front();
    dropped_++;
  }
}

void LogRing::append_bytes(const std::string_view bytes)
{
  std::lock_guard lock(mutex_);
  partial_ += decoder_.feed(bytes);
  size_t start = 0;
  while (true) {
    const size_t newline = partial_.find('\n', start);
    if (newline == std::string::npos) {
      break;
    }
    push_locked(partial_.substr(start, newline - start), Source::Stderr);
    start = newline + 1;
  }
  partial_.erase(0, start);
  if (partial_.size() > max_line_bytes_ * 4) {
    /* A runaway line without newlines: cut it into pieces rather than growing without bound. */
    push_locked(std::move(partial_), Source::Stderr);
    partial_.clear();
  }
}

void LogRing::flush()
{
  std::lock_guard lock(mutex_);
  partial_ += decoder_.finish();
  if (!partial_.empty()) {
    push_locked(std::move(partial_), Source::Stderr);
    partial_.clear();
  }
}

void LogRing::append_line(const std::string_view text, const Source source)
{
  std::lock_guard lock(mutex_);
  push_locked(core::utf8::sanitize(text), source);
}

std::vector<LogRing::Line> LogRing::lines_after(const uint64_t after) const
{
  std::lock_guard lock(mutex_);
  std::vector<Line> out;
  for (const Line &line : lines_) {
    if (line.seq > after) {
      out.push_back(line);
    }
  }
  return out;
}

uint64_t LogRing::last_seq() const
{
  std::lock_guard lock(mutex_);
  return seq_;
}

std::string LogRing::text() const
{
  std::lock_guard lock(mutex_);
  std::string out;
  for (const Line &line : lines_) {
    out += line.text;
    out += '\n';
  }
  return out;
}

size_t LogRing::dropped() const
{
  std::lock_guard lock(mutex_);
  return dropped_;
}

}  // namespace stk::bridge
