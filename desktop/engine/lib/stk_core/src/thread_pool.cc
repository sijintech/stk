/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/core/thread_pool.hh"

#include <algorithm>
#include <atomic>
#include <exception>

namespace stk::core {

ThreadPool::ThreadPool(size_t threads)
{
  if (threads == 0) {
    const unsigned hw = std::thread::hardware_concurrency();
    threads = hw > 1 ? hw - 1 : 1;
  }
  workers_.reserve(threads);
  for (size_t i = 0; i < threads; i++) {
    workers_.emplace_back([this] { run(); });
  }
}

ThreadPool::~ThreadPool()
{
  {
    std::lock_guard lock(mutex_);
    stopping_ = true;
  }
  wake_.notify_all();
  for (std::thread &worker : workers_) {
    worker.join();
  }
}

void ThreadPool::enqueue(std::function<void()> job)
{
  {
    std::lock_guard lock(mutex_);
    queue_.push_back(std::move(job));
  }
  wake_.notify_one();
}

void ThreadPool::run()
{
  for (;;) {
    std::function<void()> job;
    {
      std::unique_lock lock(mutex_);
      wake_.wait(lock, [this] { return stopping_ || !queue_.empty(); });
      if (queue_.empty()) {
        return; /* stopping and drained */
      }
      job = std::move(queue_.front());
      queue_.pop_front();
      active_++;
    }
    job();
    {
      std::lock_guard lock(mutex_);
      active_--;
      if (queue_.empty() && active_ == 0) {
        idle_.notify_all();
      }
    }
  }
}

void ThreadPool::wait_idle()
{
  std::unique_lock lock(mutex_);
  idle_.wait(lock, [this] { return queue_.empty() && active_ == 0; });
}

void ThreadPool::parallel_for(size_t count, size_t grain, const std::function<void(size_t, size_t)> &body)
{
  if (count == 0) {
    return;
  }
  grain = std::max<size_t>(grain, 1);
  const size_t max_chunks = (workers_.size() + 1) * 4;
  const size_t chunk = std::max(grain, (count + max_chunks - 1) / max_chunks);
  const size_t chunks = (count + chunk - 1) / chunk;
  if (chunks == 1) {
    body(0, count);
    return;
  }
  std::atomic<size_t> next{0};
  std::exception_ptr error;
  std::mutex error_mutex;
  auto worker = [&] {
    for (;;) {
      const size_t index = next.fetch_add(1);
      if (index >= chunks) {
        return;
      }
      const size_t begin = index * chunk;
      try {
        body(begin, std::min(count, begin + chunk));
      }
      catch (...) {
        std::lock_guard lock(error_mutex);
        if (!error) {
          error = std::current_exception();
        }
      }
    }
  };
  std::vector<std::future<void>> helpers;
  const size_t helper_count = std::min(workers_.size(), chunks - 1);
  helpers.reserve(helper_count);
  for (size_t i = 0; i < helper_count; i++) {
    helpers.push_back(submit(worker));
  }
  worker();
  for (auto &helper : helpers) {
    helper.get();
  }
  if (error) {
    std::rethrow_exception(error);
  }
}

}  // namespace stk::core
