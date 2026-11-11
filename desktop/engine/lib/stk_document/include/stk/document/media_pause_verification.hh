/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <chrono>
#include <cstdint>
#include <optional>

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

/** One view-owned suspension pair, with at most one native command awaiting its ACK.
 * Desired state may change while a command is in flight. Its effect must settle before
 * the opposite command is submitted, even when its original navigation has changed. */
class MediaPlaybackSuspension {
 public:
  using Clock = MediaPauseVerification::Clock;
  enum class Reply { Ignored, Accepted, Failed };
  struct Command {
    uint64_t serial;
    bool suspend;
  };

  void require(bool suspended) { desired_ = suspended; }
  bool ready(bool suspended) const { return !pending_ && desired_ == suspended && owned_ == suspended; }
  std::optional<Command> next(Clock::time_point now)
  {
    if (pending_ || desired_ == owned_) { return {}; }
    owned_ = desired_;
    pending_ = Command{++serial_, owned_};
    deadline_ = now + MediaPauseVerification::timeout;
    return pending_;
  }
  Reply acknowledge(Command command, Clock::time_point now)
  {
    if (!pending_ || pending_->serial != command.serial || pending_->suspend != command.suspend) {
      return Reply::Ignored;
    }
    if (now >= deadline_) { return Reply::Failed; }
    pending_.reset();
    return Reply::Accepted;
  }
  bool expired(Command command, Clock::time_point now) const
  {
    return pending_ && pending_->serial == command.serial && now >= deadline_;
  }

 private:
  bool desired_ = false, owned_ = false;
  uint64_t serial_ = 0;
  std::optional<Command> pending_;
  Clock::time_point deadline_{};
};

}  // namespace stk::document_preview::detail
