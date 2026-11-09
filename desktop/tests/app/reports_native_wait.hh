/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <chrono>

namespace stk::reports_native_test {
// A capture phase may replace an empty WGC session twice. Every replacement
// stays within the caller's deadline and must deliver its own capture frame.
class StalledCaptureRestart {
 public:
  using Clock = std::chrono::steady_clock;

  void started(Clock::time_point now) { next_ = now + std::chrono::seconds(2); }

  bool due(Clock::time_point now)
  {
    if (remaining_ == 0 || now < next_) { return false; }
    --remaining_;
    next_ = Clock::time_point::max();
    return true;
  }

 private:
  Clock::time_point next_ = Clock::time_point::max();
  unsigned remaining_ = 2;
};

// Poll external completion while the caller pumps the real UI without waiting for an OS event.
// No phase renews the absolute deadline. Synchronous callbacks cannot be preempted, but their
// late results are rejected. Yielding is supplied by the host (or a deterministic test clock).
template<class Clock, class Predicate, class Pump, class Yield>
bool poll_before(typename Clock::time_point deadline, Predicate predicate, Pump pump, Yield yield)
{
  while (Clock::now() < deadline) {
    const bool ready = predicate();
    if (Clock::now() >= deadline) { return false; }
    if (ready) { return true; }
    pump(false);
    if (Clock::now() >= deadline) { return false; }
    yield();
  }
  return false;
}
} // namespace stk::reports_native_test
