/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/log.hh"

#include "stk/core/clock.hh"

#include <atomic>
#include <cstdio>
#include <mutex>

namespace stk::core {

namespace {

std::mutex &sink_mutex()
{
  static std::mutex mutex;
  return mutex;
}

LogSink &sink_slot()
{
  static LogSink sink;
  return sink;
}

std::atomic<LogLevel> &level_slot()
{
  static std::atomic<LogLevel> level{LogLevel::Info};
  return level;
}

void stderr_sink(const LogRecord &record)
{
  const std::string_view level = log_level_name(record.level);
  std::fprintf(stderr,
               "[%.*s] %.*s: %.*s\n",
               int(level.size()),
               level.data(),
               int(record.channel.size()),
               record.channel.data(),
               int(record.message.size()),
               record.message.data());
}

}  // namespace

std::string_view log_level_name(LogLevel level)
{
  switch (level) {
    case LogLevel::Debug:
      return "debug";
    case LogLevel::Info:
      return "info";
    case LogLevel::Warning:
      return "warning";
    case LogLevel::Error:
      return "error";
    case LogLevel::Off:
      return "off";
  }
  return "?";
}

LogSink set_log_sink(LogSink sink)
{
  std::lock_guard lock(sink_mutex());
  LogSink previous = std::move(sink_slot());
  sink_slot() = std::move(sink);
  return previous;
}

void set_log_level(LogLevel level)
{
  level_slot().store(level);
}

LogLevel log_level()
{
  return level_slot().load(std::memory_order_relaxed);
}

void log_message(LogLevel level, std::string_view channel, std::string_view message)
{
  if (level < log_level() || level == LogLevel::Off) {
    return;
  }
  const LogRecord record{level, channel, message, wall_clock_seconds()};
  std::lock_guard lock(sink_mutex());
  if (sink_slot()) {
    sink_slot()(record);
  }
  else {
    stderr_sink(record);
  }
}

}  // namespace stk::core
