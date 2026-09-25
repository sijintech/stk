/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Shared helpers of the stk_bridge tests. */
#pragma once

#include <chrono>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "stk/bridge/client.hh"

namespace stk::bridge::test {

/** A main-loop stand-in: the executor queues tasks, the test thread runs them with pump(). */
class ManualLoop {
 public:
  Executor executor()
  {
    return [this](std::function<void()> fn) {
      {
        std::lock_guard lock(mutex_);
        tasks_.push_back(std::move(fn));
      }
      cv_.notify_all();
    };
  }
  /** Runs queued tasks (and those they queue) until `until()` holds or the timeout passes. */
  bool pump_until(const std::function<bool()> &until, double timeout_s = 30.0)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::microseconds(int64_t(timeout_s * 1e6));
    while (true) {
      run_ready();
      if (until()) {
        return true;
      }
      std::unique_lock lock(mutex_);
      if (std::chrono::steady_clock::now() >= deadline) {
        return false;
      }
      cv_.wait_for(lock, std::chrono::milliseconds(10), [&] { return !tasks_.empty(); });
    }
  }
  void run_ready()
  {
    while (true) {
      std::function<void()> fn;
      {
        std::lock_guard lock(mutex_);
        if (tasks_.empty()) {
          return;
        }
        fn = std::move(tasks_.front());
        tasks_.pop_front();
      }
      fn();
      ran_++;
    }
  }
  size_t ran() const
  {
    return ran_;
  }
  size_t queued()
  {
    std::lock_guard lock(mutex_);
    return tasks_.size();
  }

 private:
  std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> tasks_;
  size_t ran_ = 0;
};

bool wait_until(const std::function<bool()> &predicate, double timeout_s = 30.0);

/** A fresh directory under the build tree's test scratch area, removed on destruction. */
class TempDir {
 public:
  explicit TempDir(const std::string &tag);
  ~TempDir();
  const std::filesystem::path &path() const
  {
    return path_;
  }
  std::string str() const
  {
    return path_.string();
  }

 private:
  std::filesystem::path path_;
};

/** Linux: pids whose command line contains `needle` (strays check); empty elsewhere. */
std::vector<long> processes_matching(const std::string &needle);
/** POSIX: whether any process of group `pgid` is alive. */
bool process_group_alive(long pgid);
bool process_alive(long pid);
void kill_hard(long pid);

/**
 * Bounded polls for state that other threads produce (the bridge log, counters): tests never
 * assume those are complete the moment a call returns.
 */
bool log_eventually_contains(Client &client, const std::string &text, double timeout_s = 30.0);
bool protocol_errors_reach(Client &client, uint64_t count, double timeout_s = 30.0);

/** Path of the stk-bridge-fake executable (next to the test binary). */
std::string fake_bridge_path();

/** ClientOptions running the fake bridge with `args`. */
ClientOptions fake_options(const std::vector<std::string> &args, Executor executor = {});

}  // namespace stk::bridge::test
