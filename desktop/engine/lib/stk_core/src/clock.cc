/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/clock.hh"

#include <cmath>
#include <cstdio>

namespace stk::core {

double monotonic_seconds()
{
  static const auto epoch = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(std::chrono::steady_clock::now() - epoch).count();
}

double wall_clock_seconds()
{
  return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}

namespace {

/* Howard Hinnant's civil_from_days (public domain): proleptic Gregorian date of a day count. */
void civil_from_days(int64_t z, int64_t &y, unsigned &m, unsigned &d)
{
  z += 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = unsigned(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  y = int64_t(yoe) + era * 400;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  d = doy - (153 * mp + 2) / 5 + 1;
  m = mp < 10 ? mp + 3 : mp - 9;
  y += (m <= 2);
}

}  // namespace

std::string format_utc_iso8601(double unix_seconds)
{
  if (!std::isfinite(unix_seconds)) {
    return {};
  }
  const int64_t total_ms = int64_t(std::floor(unix_seconds * 1000.0 + 0.5));
  int64_t days = total_ms / 86400000;
  int64_t ms_of_day = total_ms % 86400000;
  if (ms_of_day < 0) {
    ms_of_day += 86400000;
    days -= 1;
  }
  int64_t y;
  unsigned m, d;
  civil_from_days(days, y, m, d);
  const int hh = int(ms_of_day / 3600000), mm = int(ms_of_day / 60000 % 60), ss = int(ms_of_day / 1000 % 60),
            ms = int(ms_of_day % 1000);
  char buffer[48];
  std::snprintf(buffer, sizeof(buffer), "%04lld-%02u-%02uT%02d:%02d:%02d.%03dZ", (long long)y, m, d, hh, mm, ss, ms);
  return buffer;
}

}  // namespace stk::core
