/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk_posix_event_thread.hh"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <future>
#include <mutex>
#include <system_error>

namespace stk::ghost {
namespace {
using namespace std::chrono_literals;

struct Pipe {
  int fds[2] = {-1, -1};
  Pipe()
  {
    if (::pipe(fds) != 0) { throw std::system_error(errno, std::generic_category(), "test display pipe"); }
  }
  ~Pipe()
  {
    for (const int fd : fds) {
      if (fd >= 0) { ::close(fd); }
    }
  }
};

struct Signal {
  std::mutex mutex;
  std::condition_variable condition;
  bool set = false;
  void notify()
  {
    std::lock_guard lock(mutex);
    set = true;
    condition.notify_all();
  }
  bool wait()
  {
    std::unique_lock lock(mutex);
    return condition.wait_for(lock, 5s, [&] { return set; });
  }
};

struct Gate {
  Signal entered;
  std::mutex mutex;
  std::condition_variable condition;
  bool open = false;
  void wait()
  {
    std::unique_lock lock(mutex);
    entered.notify();
    condition.wait(lock, [&] { return open; });
  }
  void release()
  {
    std::lock_guard lock(mutex);
    open = true;
    condition.notify_all();
  }
};

struct ReleaseGate {
  Gate &gate;
  ~ReleaseGate() { gate.release(); }
};

void no_work(void *, PosixEventThread &) {}

/* Syscalls are real unless one selected initialization step deliberately fails. Only the
 * owner calls these wrappers; the worker never reads the thread-local injection state. */
struct StartupFault {
  enum Kind { None, PipeFailure, FcntlFailure, ThreadFailure } kind = None;
  int fds[2] = {-1, -1};
  int fcntl_calls = 0, fail_fcntl_at = 1, thread_calls = 0;
  bool configured_at_thread_start = false;
  static thread_local StartupFault *active;
  StartupFault() { active = this; }
  ~StartupFault() { active = nullptr; }
  PosixEventThread::Operations operations()
  {
    return {make_pipe, fcntl_call, create_thread};
  }
  static int make_pipe(int *fds)
  {
    if (active->kind == PipeFailure) { errno = EMFILE; return -1; }
    const int result = ::pipe(fds);
    if (result == 0) {
      active->fds[0] = fds[0]; active->fds[1] = fds[1];
    }
    return result;
  }
  static int fcntl_call(const int fd, const int command, const int value)
  {
    if (++active->fcntl_calls == active->fail_fcntl_at && active->kind == FcntlFailure) {
      errno = EIO; return -1;
    }
    return ::fcntl(fd, command, value);
  }
  static int create_thread(pthread_t *thread, const pthread_attr_t *attributes,
                           void *(*entry)(void *), void *data)
  {
    ++active->thread_calls;
    active->configured_at_thread_start = true;
    for (const int fd : active->fds) {
      const int descriptor_flags = ::fcntl(fd, F_GETFD), status_flags = ::fcntl(fd, F_GETFL);
      active->configured_at_thread_start &= descriptor_flags >= 0 && status_flags >= 0 &&
                                           (descriptor_flags & FD_CLOEXEC) != 0 &&
                                           (status_flags & O_NONBLOCK) != 0;
    }
    if (active->kind == ThreadFailure) { return EAGAIN; }
    return ::pthread_create(thread, attributes, entry, data);
  }
};
thread_local StartupFault *StartupFault::active = nullptr;

void expect_closed(const StartupFault &fault)
{
  for (const int fd : fault.fds) {
    ASSERT_GE(fd, 0);
    errno = 0;
    EXPECT_EQ(::fcntl(fd, F_GETFD), -1);
    EXPECT_EQ(errno, EBADF);
  }
}

TEST(PosixEventThread, DefaultAndRepeatedStopAreSafe)
{
  PosixEventThread thread;
  EXPECT_FALSE(thread.joinable());
  EXPECT_FALSE(thread.stop_requested());
  EXPECT_EQ(thread.start(nullptr, nullptr), EINVAL);
  thread.request_stop(); thread.request_stop();
  EXPECT_TRUE(thread.stop_requested());
  EXPECT_EQ(thread.wait_readable(-1), 0) << "stop takes precedence even over an invalid display";
  thread.stop_and_join(); thread.stop_and_join();
  EXPECT_FALSE(thread.joinable());
}

TEST(PosixEventThread, RealDisplayReadThenStopWakesTheNextPollWithoutDisplayTraffic)
{
  Pipe display;
  ASSERT_GE(display.fds[0], 0);
  struct Probe {
    int fd;
    Signal next_poll;
    int first = -2, second = -2;
    ssize_t drained = -1;
    bool exited = false;
  } probe{display.fds[0]};
  PosixEventThread thread;
  ASSERT_EQ(thread.start([](void *data, PosixEventThread &worker) {
    auto &p = *static_cast<Probe *>(data);
    p.first = worker.wait_readable(p.fd);
    if (p.first == 1) {
      char byte;
      p.drained = ::read(p.fd, &byte, 1);
      p.next_poll.notify();
      p.second = worker.wait_readable(p.fd);
    }
    p.exited = true;
  }, &probe), 0);
  ASSERT_EQ(::write(display.fds[1], "x", 1), 1);
  ASSERT_TRUE(probe.next_poll.wait());
  thread.request_stop();
  thread.stop_and_join();
  EXPECT_EQ(probe.first, 1);
  EXPECT_EQ(probe.drained, 1);
  EXPECT_EQ(probe.second, 0);
  EXPECT_TRUE(probe.exited);
  EXPECT_FALSE(thread.joinable());
}

TEST(PosixEventThread, StopWinsWhenTheDisplayAndWakeDescriptorsAreBothReady)
{
  Pipe display;
  ASSERT_GE(display.fds[0], 0);
  struct Probe { int fd; Gate gate; int result = -2; } probe{display.fds[0]};
  PosixEventThread thread;
  ReleaseGate release{probe.gate};
  ASSERT_EQ(thread.start([](void *data, PosixEventThread &worker) {
    auto &p = *static_cast<Probe *>(data);
    p.gate.wait();
    p.result = worker.wait_readable(p.fd);
  }, &probe), 0);
  ASSERT_TRUE(probe.gate.entered.wait());
  ASSERT_EQ(::write(display.fds[1], "x", 1), 1);
  thread.request_stop();
  probe.gate.release();
  thread.stop_and_join();
  EXPECT_EQ(probe.result, 0);
}

TEST(PosixEventThread, DisplayHangupReturnsAnErrorInsteadOfSpinning)
{
  Pipe display;
  ASSERT_GE(display.fds[0], 0);
  ::close(display.fds[1]); display.fds[1] = -1;
  PosixEventThread thread;
  ASSERT_EQ(thread.start(no_work, nullptr), 0);
  errno = 0;
  EXPECT_EQ(thread.wait_readable(display.fds[0]), -1);
  EXPECT_EQ(errno, EIO);
}

TEST(PosixEventThread, InvalidAndClosedDescriptorsReturnBadFileDescriptor)
{
  Pipe display;
  ASSERT_GE(display.fds[0], 0);
  PosixEventThread thread;
  ASSERT_EQ(thread.start(no_work, nullptr), 0);
  errno = 0;
  EXPECT_EQ(thread.wait_readable(-1), -1);
  EXPECT_EQ(errno, EBADF);
  const int closed = ::dup(display.fds[0]);
  ASSERT_GE(closed, 0);
  ::close(closed);
  errno = 0;
  EXPECT_EQ(thread.wait_readable(closed), -1);
  EXPECT_EQ(errno, EBADF);
}

TEST(PosixEventThread, JoinWaitsForAWorkerBlockedOnTheCallbackMutexAndPreventsLateAccess)
{
  std::mutex server;
  std::unique_lock held(server);
  struct Probe {
    std::mutex &server;
    Signal attempted;
    std::atomic<int> callbacks = 0;
    std::atomic<bool> exited = false;
  } probe{server};
  PosixEventThread thread;
  ASSERT_EQ(thread.start([](void *data, PosixEventThread &worker) {
    auto &p = *static_cast<Probe *>(data);
    p.attempted.notify();
    std::lock_guard lock(p.server);
    if (!worker.stop_requested()) { ++p.callbacks; }
    p.exited = true;
  }, &probe), 0);
  EXPECT_TRUE(probe.attempted.wait());
  // Stop is visible before the owner releases the mutex, even if the joining
  // thread is descheduled after announcing its entry.
  thread.request_stop();
  Signal joining;
  auto result = std::async(std::launch::async, [&] {
    joining.notify();
    thread.stop_and_join();
    return probe.exited.load();
  });
  EXPECT_TRUE(joining.wait());
  EXPECT_EQ(result.wait_for(25ms), std::future_status::timeout);
  held.unlock();
  ASSERT_EQ(result.wait_for(5s), std::future_status::ready);
  EXPECT_TRUE(result.get()) << "join must return only after the worker's exit sentinel";
  EXPECT_EQ(probe.callbacks, 0) << "a worker acquiring the mutex after stop cannot touch its owner";
}

TEST(PosixEventThread, JoinLetsAnInFlightCallbackFinishAndReleaseItsMutex)
{
  struct Probe {
    std::mutex server;
    Gate callback;
    std::atomic<bool> completed = false;
  } probe;
  PosixEventThread thread;
  ReleaseGate release{probe.callback};
  ASSERT_EQ(thread.start([](void *data, PosixEventThread &) {
    auto &p = *static_cast<Probe *>(data);
    std::lock_guard lock(p.server);
    p.callback.wait();
    p.completed = true;
  }, &probe), 0);
  ASSERT_TRUE(probe.callback.entered.wait());
  Signal joining;
  auto result = std::async(std::launch::async, [&] {
    joining.notify();
    thread.stop_and_join();
    return probe.completed.load();
  });
  EXPECT_TRUE(joining.wait());
  EXPECT_EQ(result.wait_for(25ms), std::future_status::timeout);
  probe.callback.release();
  ASSERT_EQ(result.wait_for(5s), std::future_status::ready);
  EXPECT_TRUE(result.get());
  ASSERT_TRUE(probe.server.try_lock());
  probe.server.unlock();
}

TEST(PosixEventThread, AnEntryCanReturnNormallyBeforeItsOwnerJoins)
{
  Signal done;
  PosixEventThread thread;
  ASSERT_EQ(thread.start([](void *data, PosixEventThread &) {
    static_cast<Signal *>(data)->notify();
  }, &done), 0);
  ASSERT_TRUE(done.wait());
  EXPECT_TRUE(thread.joinable());
  thread.stop_and_join(); thread.stop_and_join();
  EXPECT_FALSE(thread.joinable());
}

TEST(PosixEventThread, WakeDescriptorsAreNonblockingCloseOnExecAndLiveUntilDestruction)
{
  StartupFault fault;
  {
    PosixEventThread thread(fault.operations());
    ASSERT_EQ(thread.start(no_work, nullptr), 0);
    EXPECT_TRUE(fault.configured_at_thread_start);
    for (const int fd : fault.fds) {
      EXPECT_NE(::fcntl(fd, F_GETFD) & FD_CLOEXEC, 0);
      EXPECT_NE(::fcntl(fd, F_GETFL) & O_NONBLOCK, 0);
    }
    EXPECT_EQ(thread.start(no_work, nullptr), EALREADY);
    thread.stop_and_join();
    EXPECT_EQ(thread.start(no_work, nullptr), EALREADY);
    for (const int fd : fault.fds) { EXPECT_GE(::fcntl(fd, F_GETFD), 0); }
  }
  expect_closed(fault);
}

TEST(PosixEventThread, PipeFailureDoesNotStartAWorker)
{
  StartupFault fault; fault.kind = StartupFault::PipeFailure;
  PosixEventThread thread(fault.operations());
  EXPECT_EQ(thread.start(no_work, nullptr), EMFILE);
  EXPECT_FALSE(thread.joinable());
  EXPECT_EQ(fault.fcntl_calls, 0);
  EXPECT_EQ(fault.thread_calls, 0);
  thread.stop_and_join();
}

TEST(PosixEventThread, PartialDescriptorConfigurationFailureClosesBothDescriptors)
{
  for (const int failure : {1, 3, 5, 8}) {
    SCOPED_TRACE(failure);
    StartupFault fault; fault.kind = StartupFault::FcntlFailure; fault.fail_fcntl_at = failure;
    PosixEventThread thread(fault.operations());
    EXPECT_EQ(thread.start(no_work, nullptr), EIO);
    EXPECT_FALSE(thread.joinable());
    EXPECT_EQ(fault.thread_calls, 0);
    expect_closed(fault);
    thread.stop_and_join();
  }
}

TEST(PosixEventThread, ThreadCreationFailureRollsBackAndAllowsARealRetry)
{
  StartupFault fault; fault.kind = StartupFault::ThreadFailure;
  {
    PosixEventThread thread(fault.operations());
    EXPECT_EQ(thread.start(no_work, nullptr), EAGAIN);
    EXPECT_TRUE(fault.configured_at_thread_start);
    EXPECT_FALSE(thread.joinable());
    expect_closed(fault);
    thread.stop_and_join();
    fault.kind = StartupFault::None;
    ASSERT_EQ(thread.start(no_work, nullptr), 0);
    thread.stop_and_join();
    EXPECT_EQ(fault.thread_calls, 2);
  }
  expect_closed(fault);
}

}  // namespace
}  // namespace stk::ghost
