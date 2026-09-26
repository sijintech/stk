/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Cross-thread queue of main-loop tasks (WindowManager::post) and the OS primitive that wakes the
 * loop's wait when a task arrives. Internal to stk_wm.
 *
 * Wake primitives (chosen by WindowManager::create per GHOST backend):
 * - Fd: an eventfd (Linux) or a CLOEXEC non-blocking self-pipe (other POSIX). The X11 wait polls
 *   it next to the X connection (see ghost_native.cc).
 * - Win32Message: PostThreadMessageW(main thread, WM_NULL); GHOST's Win32 wait loop
 *   (PeekMessage / Sleep(1)) then dispatches it and returns.
 * - Condition: a condition variable; the polling backends (Wayland, Cocoa) wait on it for at most
 *   5 ms instead of sleeping, so a post ends the wait at once.
 * The condition variable is always notified, whatever the primary primitive.
 */
#pragma once

#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>

namespace stk::wm::detail {

class PostQueue {
 public:
  enum class Wake { Condition, Fd, Win32Message };

  PostQueue();
  ~PostQueue();
  PostQueue(const PostQueue &) = delete;
  PostQueue &operator=(const PostQueue &) = delete;

  /** Thread-safe. False (and `fn` dropped) once #close was called. */
  bool post(std::function<void()> fn);
  /** Main thread: takes every queued task and resets the wake primitive. */
  std::deque<std::function<void()>> take();
  /** Main thread: puts tasks back at the front (a task threw; the rest run next time). */
  void requeue_front(std::deque<std::function<void()>> tasks);
  bool has_pending();
  /** Drops queued tasks; later posts are refused. */
  void close();

  /** Blocks for at most `timeout_ms` or until a task is queued. */
  void wait(int timeout_ms);

  /** Win32Message targets the calling thread (the main thread). */
  void set_wake(Wake wake);
  Wake wake() const
  {
    return wake_;
  }
  /** Readable while tasks are queued (POSIX; -1 when unavailable). */
  int fd() const
  {
    return read_fd_;
  }

 private:
  void signal_locked();
  void drain_locked();

  std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> queue_;
  bool closed_ = false;
  bool signalled_ = false;
  Wake wake_ = Wake::Condition;
  [[maybe_unused]] uint64_t win32_thread_ = 0; /* Windows only */
  int read_fd_ = -1;
  [[maybe_unused]] int write_fd_ = -1; /* POSIX only */
};

}  // namespace stk::wm::detail
