/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <chrono>
#include <cstdint>
#include <string>

namespace stk::core {

/** Monotonic seconds since an arbitrary process-wide epoch (steady_clock). */
double monotonic_seconds();

/** Wall-clock seconds since the Unix epoch (system_clock). */
double wall_clock_seconds();

/** "2026-09-25T12:34:56.789Z" (UTC, millisecond precision) for a Unix time in seconds. */
std::string format_utc_iso8601(double unix_seconds);

/** Elapsed monotonic time since construction or the last restart(). */
class Stopwatch {
 public:
  Stopwatch() : start_(std::chrono::steady_clock::now()) {}
  void restart()
  {
    start_ = std::chrono::steady_clock::now();
  }
  double seconds() const
  {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
  }
  double milliseconds() const
  {
    return seconds() * 1e3;
  }

 private:
  std::chrono::steady_clock::time_point start_;
};

/** Clock interface so time-dependent logic (prefetch, playback, LOD) can be tested with a fake clock. */
class Clock {
 public:
  virtual ~Clock() = default;
  virtual double now() const = 0;
};

class SteadyClock final : public Clock {
 public:
  double now() const override
  {
    return monotonic_seconds();
  }
};

class ManualClock final : public Clock {
 public:
  explicit ManualClock(double start = 0.0) : now_(start) {}
  double now() const override
  {
    return now_;
  }
  void advance(double seconds)
  {
    now_ += seconds;
  }
  void set(double seconds)
  {
    now_ = seconds;
  }

 private:
  double now_;
};

}  // namespace stk::core
