/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* A small fixed-size thread pool (payload decode, hashing, colour mapping, prefetch). */

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <functional>
#include <future>
#include <mutex>
#include <thread>
#include <type_traits>
#include <vector>

namespace stk::core {

class ThreadPool {
 public:
  /** `threads` = 0 uses hardware_concurrency() - 1 (at least 1). */
  explicit ThreadPool(size_t threads = 0);
  ~ThreadPool();
  ThreadPool(const ThreadPool &) = delete;
  ThreadPool &operator=(const ThreadPool &) = delete;

  size_t size() const
  {
    return workers_.size();
  }

  /** Queue a task; the future carries its result or exception. */
  template<typename F>
  auto submit(F &&task) -> std::future<std::invoke_result_t<std::decay_t<F>>>
  {
    using R = std::invoke_result_t<std::decay_t<F>>;
    auto packaged = std::make_shared<std::packaged_task<R()>>(std::forward<F>(task));
    std::future<R> future = packaged->get_future();
    enqueue([packaged] { (*packaged)(); });
    return future;
  }

  /** Run body(begin, end) over [0, count) in chunks of at least `grain`, on the pool and the calling
   * thread; rethrows the first exception after all chunks finished. */
  void parallel_for(size_t count, size_t grain, const std::function<void(size_t, size_t)> &body);

  /** Block until the queue is empty and no task is running. */
  void wait_idle();

 private:
  void enqueue(std::function<void()> job);
  void run();

  std::vector<std::thread> workers_;
  std::deque<std::function<void()>> queue_;
  std::mutex mutex_;
  std::condition_variable wake_;
  std::condition_variable idle_;
  size_t active_ = 0;
  bool stopping_ = false;
};

}  // namespace stk::core
