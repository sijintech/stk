/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <chrono>
#include <cstdint>

namespace stk::document_preview::detail {

// One accepted pause, including its acknowledgement and state queries, has one
// absolute deadline. A missing callback must not leave playback unverified.
class MediaPauseVerification {
 public:
  using Clock = std::chrono::steady_clock;
  enum class Result { Ignored, Waiting, Paused, Failed };
  static constexpr auto timeout = std::chrono::seconds(1);

  MediaPauseVerification(uint64_t generation, uint64_t navigation, Clock::time_point now)
      : generation_(generation), navigation_(navigation), deadline_(now + timeout)
  {
  }

  Result expire(uint64_t generation, uint64_t navigation, Clock::time_point now)
  {
    if (finished_ || generation != generation_ || navigation != navigation_) {
      return Result::Ignored;
    }
    if (now >= deadline_) {
      finished_ = true;
      return Result::Failed;
    }
    return Result::Waiting;
  }

  Result observe(bool playing, uint64_t generation, uint64_t navigation, Clock::time_point now)
  {
    const auto pending = expire(generation, navigation, now);
    if (pending != Result::Waiting || playing) {
      return pending;
    }
    finished_ = true;
    return Result::Paused;
  }

 private:
  uint64_t generation_, navigation_;
  Clock::time_point deadline_;
  bool finished_ = false;
};

}  // namespace stk::document_preview::detail
