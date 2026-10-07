/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <chrono>
#include <optional>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;
class ProjectState;

/** The open project's "needs attention" summary (project.attention.list, UX package U1), shared by
 * Home and the status bar: failures and reviews first, then running and finished work, with this
 * person's viewed marks. Read again after a project change, every few seconds while something runs,
 * or when asked. Marking viewed never changes the project. Replies of a closed or replaced project
 * opening or bridge are ignored. */
class ProjectAttention {
 public:
  explicit ProjectAttention(AppStore &store);
  ~ProjectAttention();
  ProjectAttention(const ProjectAttention &) = delete;
  ProjectAttention &operator=(const ProjectAttention &) = delete;

  /** Follow the project opening and, when due, read the summary again (cheap to call every frame). */
  void sync();
  bool supported() const;
  bool busy() const { return future_.has_value(); }
  /** {revision, items, counts} or null until read. */
  const io::Json &result() const { return result_; }
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }
  /** Unviewed items that need a person (the status bar count). */
  int64_t needs_you() const;
  /** Something runs, so the summary is read again every few seconds; the caller wakes the frame loop. */
  bool polling() const;
  static constexpr int kPollMs = 3000;
  /** Set while a wake-up timer for the next poll is pending (owned by the status bar). */
  bool wake_scheduled = false;
  bool refresh();
  /** Mark these item keys viewed (an explicit "seen", or opening an item). */
  bool mark_viewed(std::vector<std::string> keys);

 private:
  void reset();
  void changed();

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_;
  int64_t read_revision_ = -1;
  bool stale_ = false;  // a simulation run changed, or viewed marks were stored after the last read
  bridge::ListenerHandle runs_listener_;
  uint64_t epoch_ = 0, version_ = 0;
  io::Json result_;
  std::chrono::steady_clock::time_point read_at_{};
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
