/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* A joinable POSIX event worker with an independent stop descriptor. No Wayland/GPU dependency. */
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>

#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <unistd.h>

namespace stk::ghost {

class PosixEventThread {
 private:
  static int system_fcntl(const int fd, const int command, const int value)
  {
    return ::fcntl(fd, command, value);
  }

 public:
  using Entry = void (*)(void *, PosixEventThread &);

  /** Narrow syscall seam for initialization-failure tests. Calls follow the POSIX contracts. */
  struct Operations {
    int (*make_pipe)(int *) = ::pipe;
    int (*fcntl)(int, int, int) = system_fcntl;
    int (*create_thread)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *) =
        ::pthread_create;
  };

  PosixEventThread() = default;
  explicit PosixEventThread(const Operations &operations) : operations_(operations) {}
  ~PosixEventThread()
  {
    stop_and_join();
    close_pipe();
  }
  PosixEventThread(const PosixEventThread &) = delete;
  PosixEventThread &operator=(const PosixEventThread &) = delete;

  /** Single owner starts/joins this one-shot worker. Initialization failure permits a retry.
   * Start/destruction require external exclusion from other calls. Once start succeeds,
   * request_stop may run concurrently with the worker and stop_and_join. The entry and its
   * data remain alive until join completes; callers must not join while holding a worker lock. */
  int start(Entry entry, void *data)
  {
    if (started_ || used_) {
      return EALREADY;
    }
    if (!entry || !operations_.make_pipe || !operations_.fcntl || !operations_.create_thread) {
      return EINVAL;
    }
    if (operations_.make_pipe(pipe_) != 0) {
      const int error = errno ? errno : EIO;
      close_pipe();
      return error;
    }
    for (const int fd : pipe_) {
      const int descriptor_flags = operations_.fcntl(fd, F_GETFD, 0);
      if (descriptor_flags < 0 ||
          operations_.fcntl(fd, F_SETFD, descriptor_flags | FD_CLOEXEC) < 0) {
        const int error = errno ? errno : EIO;
        close_pipe();
        return error;
      }
      const int status_flags = operations_.fcntl(fd, F_GETFL, 0);
      if (status_flags < 0 || operations_.fcntl(fd, F_SETFL, status_flags | O_NONBLOCK) < 0) {
        const int error = errno ? errno : EIO;
        close_pipe();
        return error;
      }
    }
    entry_ = entry;
    data_ = data;
    stop_.store(false, std::memory_order_release);
    const int error = operations_.create_thread(&thread_, nullptr, trampoline, this);
    if (error != 0) {
      close_pipe();
      entry_ = nullptr;
      data_ = nullptr;
      thread_ = {};
      return error;
    }
    started_ = used_ = true;
    return 0;
  }

  void request_stop()
  {
    if (stop_.exchange(true, std::memory_order_acq_rel) || pipe_[1] < 0) {
      return;
    }
    const char wake = 1;
    while (true) {
      const ssize_t written = ::write(pipe_[1], &wake, sizeof(wake));
      if (written == 1 ||
          (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))) {
        return;
      }
      if (written < 0 && errno == EINTR) {
        continue;
      }
      fail("stop write", written < 0 ? errno : EIO);
    }
  }

  void stop_and_join()
  {
    request_stop();
    if (!started_) {
      return;
    }
    if (pthread_equal(pthread_self(), thread_)) {
      fail("pthread_join", EDEADLK);
    }
    const int error = pthread_join(thread_, nullptr);
    if (error != 0) {
      fail("pthread_join", error);
    }
    started_ = false;
    thread_ = {};
    entry_ = nullptr;
    data_ = nullptr;
    // Keep descriptors until destruction: another request_stop may still be finishing its write.
  }

  bool stop_requested() const { return stop_.load(std::memory_order_acquire); }
  pthread_t native_handle() const { return thread_; }
  bool joinable() const { return started_; }

  /** 1: display readable, 0: stop, -1: error (errno). Stop takes precedence over display events.
   * The entry may call this repeatedly; a terminal display error must end its own loop. */
  int wait_readable(const int fd) const
  {
    if (stop_requested()) {
      return 0;
    }
    if (fd < 0 || pipe_[0] < 0) {
      errno = EBADF;
      return -1;
    }
    pollfd descriptors[2] = {{pipe_[0], POLLIN, 0}, {fd, POLLIN | POLLPRI, 0}};
    while (true) {
      if (stop_requested()) {
        return 0;
      }
      const int ready = ::poll(descriptors, 2, -1);
      if (stop_requested()) {
        return 0;
      }
      if (ready < 0) {
        if (errno == EINTR) {
          continue;
        }
        return -1;
      }
      if (descriptors[0].revents & POLLIN) {
        return 0;
      }
      if (descriptors[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
        errno = (descriptors[0].revents & POLLNVAL) ? EBADF : EIO;
        return -1;
      }
      if (descriptors[1].revents & (POLLERR | POLLHUP | POLLNVAL)) {
        errno = (descriptors[1].revents & POLLNVAL) ? EBADF : EIO;
        return -1;
      }
      if (descriptors[1].revents & (POLLIN | POLLPRI)) {
        return 1;
      }
    }
  }

 private:
  [[noreturn]] static void fail(const char *operation, const int error)
  {
    std::fprintf(stderr, "STK POSIX event thread: %s failed (%d)\n", operation, error);
    std::abort();  // Continuing teardown without a joined worker could free live state.
  }

  static void *trampoline(void *data)
  {
    auto &self = *static_cast<PosixEventThread *>(data);
    self.entry_(self.data_, self);
    return nullptr;
  }

  void close_pipe()
  {
    if (pipe_[0] >= 0) {
      ::close(pipe_[0]);
    }
    if (pipe_[1] >= 0 && pipe_[1] != pipe_[0]) {
      ::close(pipe_[1]);
    }
    pipe_[0] = pipe_[1] = -1;
  }

  Operations operations_;
  int pipe_[2] = {-1, -1};
  pthread_t thread_ = {};
  Entry entry_ = nullptr;
  void *data_ = nullptr;
  std::atomic<bool> stop_ = false;
  bool started_ = false, used_ = false;
};

}  // namespace stk::ghost
