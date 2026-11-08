/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

namespace stk::reports_native_test {
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
