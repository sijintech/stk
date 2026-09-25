/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "post_queue.hh"

#include <chrono>
#include <utility>

#if defined(_WIN32)
#  ifndef WIN32_LEAN_AND_MEAN
#    define WIN32_LEAN_AND_MEAN
#  endif
#  include <windows.h>
#else
#  include <cerrno>
#  include <fcntl.h>
#  include <unistd.h>
#  if defined(__linux__)
#    include <sys/eventfd.h>
#  endif
#endif

namespace stk::wm::detail {

PostQueue::PostQueue()
{
#if defined(__linux__)
  const int fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
  if (fd >= 0) {
    read_fd_ = write_fd_ = fd;
  }
#elif !defined(_WIN32)
  int fds[2];
  if (pipe(fds) == 0) {
    for (const int fd : fds) {
      fcntl(fd, F_SETFD, FD_CLOEXEC);
      fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
    }
    read_fd_ = fds[0];
    write_fd_ = fds[1];
  }
#endif
}

PostQueue::~PostQueue()
{
#if !defined(_WIN32)
  if (read_fd_ >= 0) {
    ::close(read_fd_);
  }
  if (write_fd_ >= 0 && write_fd_ != read_fd_) {
    ::close(write_fd_);
  }
#endif
}

void PostQueue::set_wake(const Wake wake)
{
  std::lock_guard lock(mutex_);
  wake_ = (wake == Wake::Fd && read_fd_ < 0) ? Wake::Condition : wake;
#if defined(_WIN32)
  win32_thread_ = uint64_t(GetCurrentThreadId());
#else
  if (wake_ == Wake::Win32Message) {
    wake_ = Wake::Condition;
  }
#endif
  if (!queue_.empty()) {
    signalled_ = false;
    signal_locked();
  }
}

void PostQueue::signal_locked()
{
  cv_.notify_all();
  if (signalled_) {
    return; /* The primitive is already set; take() resets it. */
  }
  signalled_ = true;
  switch (wake_) {
    case Wake::Condition:
      break;
    case Wake::Fd: {
#if !defined(_WIN32)
#  if defined(__linux__)
      const uint64_t one = 1;
      const void *data = &one;
      const size_t size = sizeof(one);
#  else
      const char byte = 1;
      const void *data = &byte;
      const size_t size = 1;
#  endif
      /* EAGAIN means it is already readable, which is all a wake needs. */
      while (::write(write_fd_, data, size) < 0 && errno == EINTR) {
      }
#endif
      break;
    }
    case Wake::Win32Message:
#if defined(_WIN32)
      PostThreadMessageW(DWORD(win32_thread_), WM_NULL, 0, 0);
#endif
      break;
  }
}

void PostQueue::drain_locked()
{
  signalled_ = false;
#if !defined(_WIN32)
  if (wake_ == Wake::Fd && read_fd_ >= 0) {
    char buffer[64];
    while (true) {
      const ssize_t n = ::read(read_fd_, buffer, sizeof(buffer));
      if (n > 0) {
        continue;
      }
      if (n < 0 && errno == EINTR) {
        continue;
      }
      break;
    }
  }
#endif
}

bool PostQueue::post(std::function<void()> fn)
{
  if (!fn) {
    return false;
  }
  std::lock_guard lock(mutex_);
  if (closed_) {
    return false;
  }
  queue_.push_back(std::move(fn));
  signal_locked();
  return true;
}

std::deque<std::function<void()>> PostQueue::take()
{
  std::lock_guard lock(mutex_);
  std::deque<std::function<void()>> tasks;
  tasks.swap(queue_);
  drain_locked();
  return tasks;
}

void PostQueue::requeue_front(std::deque<std::function<void()>> tasks)
{
  std::lock_guard lock(mutex_);
  if (closed_ || tasks.empty()) {
    return;
  }
  while (!queue_.empty()) {
    tasks.push_back(std::move(queue_.front()));
    queue_.pop_front();
  }
  queue_.swap(tasks);
  signal_locked();
}

bool PostQueue::has_pending()
{
  std::lock_guard lock(mutex_);
  return !queue_.empty();
}

void PostQueue::close()
{
  std::deque<std::function<void()>> dropped;
  {
    std::lock_guard lock(mutex_);
    closed_ = true;
    dropped.swap(queue_);
    drain_locked();
  }
  /* Destroyed outside the lock: a task's captures may post (and would be refused). */
  dropped.clear();
}

void PostQueue::wait(const int timeout_ms)
{
  std::unique_lock lock(mutex_);
  cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms), [this] { return !queue_.empty() || closed_; });
}

}  // namespace stk::wm::detail
