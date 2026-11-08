/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_native_ax_process.hh"

#include <atomic>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <mutex>
#include <thread>
#ifndef _WIN32
#  include <fcntl.h>
#  include <poll.h>
#  include <pthread.h>
#  include <signal.h>
#  include <spawn.h>
#  include <sys/wait.h>
#  include <unistd.h>
#endif

namespace stk::reports_native_test::ax {
struct ProbeProcess::State {
  std::atomic<bool> cancelled = false;
  mutable std::mutex mutex;
  std::optional<ProcessResult> result;
};
namespace {
using Clock = std::chrono::steady_clock;
#ifndef _WIN32
struct Fd {
  int value = -1;
  Fd() = default;
  explicit Fd(int fd) : value(fd) {}
  ~Fd() { close(); }
  Fd(const Fd &) = delete;
  Fd &operator=(const Fd &) = delete;
  void close() { if (value >= 0) { ::close(value); value = -1; } }
};
bool pipe_pair(Fd &read, Fd &write) {
  int pair[2];
  if (::pipe(pair)) return false;
  read.value = pair[0]; write.value = pair[1];
  for (int fd : pair) {
    if (fd <= STDERR_FILENO || fcntl(fd, F_SETFD, FD_CLOEXEC) < 0) return false;
  }
  return true;
}
bool nonblocking(int fd) {
  const int old = fcntl(fd, F_GETFL); return old >= 0 && fcntl(fd, F_SETFL, old | O_NONBLOCK) == 0;
}
template<class Cancelled> ProcessResult execute(const std::string &path, const Request &request,
                                               Clock::time_point began, Cancelled cancelled) {
  ProcessResult out;
  const Deadline deadline(began + std::chrono::seconds(2));
  auto elapsed = [&] { out.elapsed_ms = std::chrono::duration<double, std::milli>(Clock::now() - began).count(); };
  if (path.empty() || path[0] != '/' || !valid_request(request) || request.parent_pid != uint64_t(getpid())) {
    out.status = ProcessStatus::ProtocolError; elapsed(); return out;
  }
  if (cancelled()) { out.status = ProcessStatus::Cancelled; elapsed(); return out; }
  if (!deadline.permits(Clock::now())) { out.status = ProcessStatus::Deadline; elapsed(); return out; }
  struct sigaction child_policy{};
  if (sigaction(SIGCHLD, nullptr, &child_policy) < 0) { out.system_error = errno; elapsed(); return out; }
  if (child_policy.sa_handler != SIG_DFL || (child_policy.sa_flags & SA_NOCLDWAIT)) {
    out.status = ProcessStatus::Unsupported; elapsed(); return out;
  }
  Fd input_read, input_write, output_read, output_write, error_read, error_write, progress_read, progress_write;
  if (!pipe_pair(input_read, input_write) || !pipe_pair(output_read, output_write) || !pipe_pair(error_read, error_write) || !pipe_pair(progress_read, progress_write)) {
    out.system_error = errno; elapsed(); return out;
  }
  posix_spawn_file_actions_t actions;
  int code = posix_spawn_file_actions_init(&actions);
  if (code) { out.system_error = code; elapsed(); return out; }
  auto action = [&](int result) { if (!code && result) code = result; };
  action(posix_spawn_file_actions_adddup2(&actions, input_read.value, STDIN_FILENO));
  action(posix_spawn_file_actions_adddup2(&actions, output_write.value, STDOUT_FILENO));
  action(posix_spawn_file_actions_adddup2(&actions, error_write.value, STDERR_FILENO));
  // Close the original input FD (which can be 3) before installing the dedicated progress FD.
  for (int fd : {input_read.value,input_write.value,output_read.value,output_write.value,error_read.value,error_write.value,
                 progress_read.value})
    action(posix_spawn_file_actions_addclose(&actions, fd));
  action(posix_spawn_file_actions_adddup2(&actions, progress_write.value, kProgressFd));
  if (progress_write.value != kProgressFd) action(posix_spawn_file_actions_addclose(&actions, progress_write.value));
#if defined(__linux__) && defined(__GLIBC__)
#  if __GLIBC_PREREQ(2, 34)
  action(posix_spawn_file_actions_addclosefrom_np(&actions, kProgressFd + 1));
#  endif
#endif
  posix_spawnattr_t attributes;
  int attr_code = posix_spawnattr_init(&attributes);
  if (!attr_code) {
    sigset_t mask, defaults; sigemptyset(&mask); sigemptyset(&defaults);
    sigaddset(&defaults, SIGPIPE); sigaddset(&defaults, SIGTERM); sigaddset(&defaults, SIGINT); sigaddset(&defaults, SIGALRM);
    action(posix_spawnattr_setsigmask(&attributes, &mask));
    action(posix_spawnattr_setsigdefault(&attributes, &defaults));
    short flags = POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF;
#ifdef __APPLE__
    flags |= POSIX_SPAWN_CLOEXEC_DEFAULT;
#endif
    action(posix_spawnattr_setflags(&attributes, flags));
  }
  else code = attr_code;
  pid_t pid = -1;
  char locale[] = "LC_ALL=C", language[] = "LANG=C";
  char *env[] = {locale, language, nullptr}; // No inherited product keys, model settings or loader overrides.
  char *argv[] = {const_cast<char *>(path.c_str()), nullptr};
  const bool expired = !deadline.permits(Clock::now());
  const bool stopped = cancelled();
  if (!code && !expired && !stopped) code = posix_spawn(&pid, path.c_str(), &actions, &attributes, argv, env);
  posix_spawn_file_actions_destroy(&actions);
  if (!attr_code) posix_spawnattr_destroy(&attributes);
  if (code) { out.system_error = code; elapsed(); return out; }
  if (expired || stopped) {
    out.status = stopped ? ProcessStatus::Cancelled : ProcessStatus::Deadline; elapsed(); return out;
  }
  out.child_pid = pid;
  input_read.close(); output_write.close(); error_write.close(); progress_write.close();
  out.status = ProcessStatus::IoError;
  bool io_ok = nonblocking(input_write.value) && nonblocking(output_read.value) && nonblocking(error_read.value) && nonblocking(progress_read.value);
  const auto wire = encode(request);
  size_t sent = 0;
  ResponseWire bytes{};
  size_t received = 0;
  ProgressWire progress_wire{};
  size_t progress_received = 0;
  uint64_t last_sequence = 0, dropped = 0;
  int wait_status = 0;
  bool exited = false, failed = !io_ok;
  // Suppress SIGPIPE only for this worker/pipe. Never change a process-wide disposition.
#ifdef __APPLE__
  const int mask_error = fcntl(input_write.value, F_SETNOSIGPIPE, 1) < 0 ? errno : 0;
#else
  sigset_t block, previous; sigemptyset(&block); sigaddset(&block, SIGPIPE);
  const int mask_error = pthread_sigmask(SIG_BLOCK, &block, &previous);
#endif
  if (mask_error) { out.system_error = mask_error; failed = true; }
  bool pipe_signal = false;
  auto progress_error = [&] {
    out.progress_invalid = true; out.progress_incomplete = true;
    if (!failed) { out.status = ProcessStatus::ProtocolError; failed = true; }
  };
  auto progress_frame = [&] {
    Progress value;
    if (!decode(progress_wire, value) || !correlated(request, value) || value.sequence <= last_sequence ||
        value.dropped < dropped || value.sequence - last_sequence - 1 != value.dropped - dropped ||
        (out.last_progress && value.elapsed_ms < out.last_progress->elapsed_ms)) {
      progress_error(); return;
    }
    const bool lossy = value.dropped != 0;
    if (!last_sequence && !lossy &&
        (value.stage != ProgressStage::Request || value.edge != ProgressEdge::Returned)) {
      progress_error(); return;
    }
    if (!lossy && value.stage == ProgressStage::Response && value.edge == ProgressEdge::Returned &&
        (!out.last_progress || out.last_progress->stage != ProgressStage::Response ||
         out.last_progress->edge != ProgressEdge::Enter)) {
      progress_error(); return;
    }
    if (value.stage == ProgressStage::Api) {
      const uint64_t latest = std::max(out.last_api_enter ? out.last_api_enter->call_sequence : 0,
                                      out.last_api_return ? out.last_api_return->call_sequence : 0);
      if (value.call_sequence < latest || (value.edge == ProgressEdge::Enter && value.call_sequence == latest) ||
          (value.edge == ProgressEdge::Returned && out.last_api_return &&
           value.call_sequence == out.last_api_return->call_sequence)) {
        progress_error(); return;
      }
    }
    if (value.stage == ProgressStage::Api && !lossy) {
      if (value.edge == ProgressEdge::Enter) {
        const uint64_t previous = out.last_api_enter ? out.last_api_enter->call_sequence : 0;
        if (value.call_sequence != previous + 1 || (previous &&
            (!out.last_api_return || out.last_api_return->call_sequence != previous))) {
          progress_error(); return;
        }
      }
      else {
        if (!out.last_api_enter || value.call_sequence != out.last_api_enter->call_sequence ||
            (out.last_api_return && out.last_api_return->call_sequence == value.call_sequence) ||
            value.phase != out.last_api_enter->phase || value.operation != out.last_api_enter->operation ||
            value.attribute != out.last_api_enter->attribute || value.node_index != out.last_api_enter->node_index ||
            value.node_depth != out.last_api_enter->node_depth || value.role != out.last_api_enter->role) {
          progress_error(); return;
        }
      }
    }
    out.progress_dropped |= value.dropped != 0;
    out.progress_incomplete |= out.progress_dropped;
    last_sequence = value.sequence; dropped = value.dropped;
    ++out.progress_records; out.progress_available = true; out.last_progress = value;
    if (value.stage == ProgressStage::Api) {
      if (value.edge == ProgressEdge::Enter) out.last_api_enter = value;
      else out.last_api_return = value;
    }
  };
  // A hostile continuously-writing child cannot keep us in drain until the watchdog expires.
  auto drain_progress = [&] {
    if (progress_read.value < 0) return;
    size_t turn = 0;
    while (turn < 4096) {
      uint8_t buffer[512];
      const ssize_t count = read(progress_read.value, buffer, sizeof(buffer));
      if (count == 0) {
        progress_read.close(); if (progress_received) progress_error(); return;
      }
      if (count < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) progress_error();
        return;
      }
      turn += size_t(count); out.progress_bytes += size_t(count);
      if (out.progress_bytes > kProgressRecordLimit * kProgressBytes) {
        out.progress_incomplete = true;
        if (!failed) { out.status = ProcessStatus::OutputLimit; failed = true; }
        return;
      }
      for (ssize_t i = 0; i < count; ++i) {
        progress_wire[progress_received++] = buffer[i];
        if (progress_received == progress_wire.size()) {
          progress_frame(); progress_received = 0;
          if (out.progress_invalid) return;
        }
      }
      if (!deadline.permits(Clock::now()) || cancelled()) return;
    }
  };
  while (!failed) {
    // Observe without consuming the child. The controlled host must not run a competing waitpid(-1) reaper.
    siginfo_t information{};
    const int observed = waitid(P_PID, id_t(pid), &information, WEXITED | WNOHANG | WNOWAIT);
    if (observed == 0 && information.si_pid == pid) exited = true;
    else if (observed < 0 && errno != EINTR) {
      out.system_error = errno; out.ownership_lost = true; failed = true; break;
    }
    if (cancelled()) { out.status = ProcessStatus::Cancelled; failed = true; break; }
    if (!deadline.permits(Clock::now())) { out.status = ProcessStatus::Deadline; failed = true; break; }
    if (input_write.value >= 0) {
      const ssize_t count = write(input_write.value, wire.data() + sent, wire.size() - sent);
      if (count > 0) { sent += size_t(count); out.request_bytes_sent = sent; }
      else if (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
        out.system_error = errno; pipe_signal = errno == EPIPE; failed = true; break;
      }
      if (sent == wire.size()) input_write.close();
    }
    auto drain = [&](Fd &fd, bool diagnostic) {
      if (fd.value < 0) return;
      uint8_t buffer[512];
      for (;;) {
        const ssize_t count = read(fd.value, buffer, sizeof(buffer));
        if (count == 0) { fd.close(); break; }
        if (count < 0) {
          if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) { out.system_error = errno; failed = true; }
          break;
        }
        if (diagnostic) {
          out.stderr_bytes += size_t(count); // Contents are discarded, never logged.
          if (out.stderr_bytes > 4096) { out.status = ProcessStatus::OutputLimit; failed = true; break; }
        }
        else {
          if (received + size_t(count) > bytes.size()) { out.status = ProcessStatus::OutputLimit; failed = true; break; }
          std::copy_n(buffer, size_t(count), bytes.data() + received); received += size_t(count);
          out.response_bytes_received = received;
        }
      }
    };
    drain(output_read, false); drain(error_read, true); drain_progress();
    if (failed || (exited && output_read.value < 0 && error_read.value < 0 && progress_read.value < 0)) break;
    pollfd fds[] = {{output_read.value, POLLIN, 0}, {error_read.value, POLLIN, 0}, {input_write.value, POLLOUT, 0},
                    {progress_read.value, POLLIN, 0}};
    if (::poll(fds, 4, 5) < 0 && errno != EINTR) { out.system_error = errno; failed = true; }
  }
  if (!out.ownership_lost) {
    // Check ownership again immediately before any signal. ECHILD means no signal and no PID-reuse assumption.
    siginfo_t information{};
    int observed;
    do { observed = waitid(P_PID, id_t(pid), &information, WEXITED | WNOHANG | WNOWAIT); } while (observed < 0 && errno == EINTR);
    if (observed < 0) { out.system_error = errno; out.ownership_lost = true; failed = true; }
    else if (!information.si_pid) {
      if (kill(pid, SIGKILL) == 0) out.killed = true;
      else if (errno != ESRCH) { out.system_error = errno; failed = true; }
    }
  }
  if (!out.ownership_lost) {
    pid_t reaped;
    do { reaped = waitpid(pid, &wait_status, 0); } while (reaped < 0 && errno == EINTR);
    out.reaped = reaped == pid;
    if (!out.reaped) { out.system_error = errno; out.ownership_lost = true; failed = true; }
  }
  if (!mask_error) {
#ifndef __APPLE__
    if (pipe_signal) { timespec zero{}; sigtimedwait(&block, nullptr, &zero); }
    pthread_sigmask(SIG_SETMASK, &previous, nullptr);
#else
    (void)pipe_signal;
#endif
  }
  // Keep the last already-buffered numeric evidence after deadline/cancellation, never wait for more.
  if (out.reaped) drain_progress();
  if (progress_received) out.progress_incomplete = true;
  if (out.reaped) {
    if (WIFEXITED(wait_status)) out.exit_code = WEXITSTATUS(wait_status);
    if (WIFSIGNALED(wait_status)) out.signal = WTERMSIG(wait_status);
  }
  if (!failed && !deadline.permits(Clock::now())) { out.status = ProcessStatus::Deadline; failed = true; }
  if (!failed) {
    if (out.signal || out.stderr_bytes || (out.exit_code != 0 && out.exit_code != 1)) out.status = ProcessStatus::ExitError;
    else if (!decode(std::span(bytes.data(), received), out.response) ||
        (out.exit_code == 0) != (out.response.status == Status::Success)) out.status = ProcessStatus::ProtocolError;
    else {
      out.response_available = true;
      // Nonblocking diagnostics may lose their final frame without a later drop report.
      // Only the independently decoded current response supplies the numerical proof.
      if (!out.last_progress || out.last_progress->stage != ProgressStage::Response ||
          out.last_progress->edge != ProgressEdge::Returned || (!out.progress_dropped &&
          (out.response.calls ? !out.last_api_return || out.last_api_return->call_sequence != out.response.calls :
                                out.last_api_return.has_value()))) {
        out.progress_incomplete = true;
      }
      out.status = ProcessStatus::Response;
    }
  }
  if (!out.response_available) out.progress_incomplete = true;
  elapsed(); return out;
}
#endif
}
ProbeProcess::ProbeProcess(const std::string &path, const Request &request) : state_(std::make_shared<State>()) {
  auto state = state_;
  const auto began = Clock::now();
  std::thread([state, path, request, began] {
    ProcessResult result;
#ifndef _WIN32
    result = execute(path, request, began, [&] { return state->cancelled.load(); });
#else
    (void)path; (void)request; (void)began;
    result.status = ProcessStatus::Unsupported;
#endif
    std::lock_guard lock(state->mutex); state->result = result;
  }).detach();
}
ProbeProcess::~ProbeProcess() { cancel(); }
void ProbeProcess::cancel() { state_->cancelled = true; }
std::optional<ProcessResult> ProbeProcess::poll() const { std::lock_guard lock(state_->mutex); return state_->result; }
std::optional<ProcessResult> ProbeProcess::Completion::poll() const { std::lock_guard lock(state_->mutex); return state_->result; }
void ProbeProcess::Completion::cancel() const { state_->cancelled = true; }
std::string_view name(ProcessStatus status) {
  switch (status) {
    case ProcessStatus::Response: return "response"; case ProcessStatus::Cancelled: return "cancelled";
    case ProcessStatus::Deadline: return "deadline"; case ProcessStatus::SpawnError: return "spawn_error";
    case ProcessStatus::IoError: return "io_error"; case ProcessStatus::OutputLimit: return "output_limit";
    case ProcessStatus::ExitError: return "exit_error"; case ProcessStatus::ProtocolError: return "protocol_error";
    case ProcessStatus::Unsupported: return "unsupported";
  }
  return "invalid";
}
} // namespace stk::reports_native_test::ax
