/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Minimal thread-safe logging. Messages are UTF-8. The default sink writes
 * "[level] channel: message" lines to stderr; the app installs its own sink
 * (log view, bridge log) with set_sink(). */

#include <cstdint>
#include <format>
#include <functional>
#include <string>
#include <string_view>

namespace stk::core {

enum class LogLevel : uint8_t { Debug = 0, Info = 1, Warning = 2, Error = 3, Off = 4 };

struct LogRecord {
  LogLevel level;
  std::string_view channel;
  std::string_view message;
  double wall_time;   /* seconds since the Unix epoch */
};

using LogSink = std::function<void(const LogRecord &)>;

std::string_view log_level_name(LogLevel level);

/** Replace the process-wide sink (nullptr restores the stderr sink). Returns the previous sink. */
LogSink set_log_sink(LogSink sink);
void set_log_level(LogLevel level);
LogLevel log_level();

void log_message(LogLevel level, std::string_view channel, std::string_view message);

template<typename... Args>
void log(LogLevel level, std::string_view channel, std::format_string<Args...> fmt, Args &&...args)
{
  if (level < log_level()) {
    return;
  }
  log_message(level, channel, std::format(fmt, std::forward<Args>(args)...));
}

template<typename... Args>
void log_debug(std::string_view channel, std::format_string<Args...> fmt, Args &&...args)
{
  log(LogLevel::Debug, channel, fmt, std::forward<Args>(args)...);
}
template<typename... Args>
void log_info(std::string_view channel, std::format_string<Args...> fmt, Args &&...args)
{
  log(LogLevel::Info, channel, fmt, std::forward<Args>(args)...);
}
template<typename... Args>
void log_warning(std::string_view channel, std::format_string<Args...> fmt, Args &&...args)
{
  log(LogLevel::Warning, channel, fmt, std::forward<Args>(args)...);
}
template<typename... Args>
void log_error(std::string_view channel, std::format_string<Args...> fmt, Args &&...args)
{
  log(LogLevel::Error, channel, fmt, std::forward<Args>(args)...);
}

}  // namespace stk::core
