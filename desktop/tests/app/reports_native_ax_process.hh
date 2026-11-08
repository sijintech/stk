/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "reports_native_ax_protocol.hh"

#include <memory>
#include <optional>
#include <string>
#include <utility>

namespace stk::reports_native_test::ax {
enum class ProcessStatus { Response, Cancelled, Deadline, SpawnError, IoError, OutputLimit, ExitError, ProtocolError, Unsupported };
struct ProcessResult {
  ProcessStatus status = ProcessStatus::SpawnError;
  Response response;
  int64_t child_pid = 0;
  int exit_code = -1, signal = 0, system_error = 0;
  bool killed = false, reaped = false, ownership_lost = false;
  size_t stderr_bytes = 0;
  double elapsed_ms = 0;
};
// This class never joins or waits on its caller. The bounded worker owns every FD/PID until kill+reap.
// Cancellation drops only the caller's interest; the worker still performs owned-child cleanup.
class ProbeProcess {
  struct State;
 public:
  class Completion {
   public:
    std::optional<ProcessResult> poll() const;
    void cancel() const;
   private:
    friend class ProbeProcess;
    explicit Completion(std::shared_ptr<State> state) : state_(std::move(state)) {}
    std::shared_ptr<State> state_;
  };
  ProbeProcess(const std::string &absolute_helper, const Request &request);
  ~ProbeProcess();
  ProbeProcess(const ProbeProcess &) = delete;
  ProbeProcess &operator=(const ProbeProcess &) = delete;
  void cancel();
  std::optional<ProcessResult> poll() const;
  Completion completion() const { return Completion(state_); } // Plain CPU cleanup handle may outlive the UI owner.
 private:
  std::shared_ptr<State> state_;
};
std::string_view name(ProcessStatus status);
} // namespace stk::reports_native_test::ax
