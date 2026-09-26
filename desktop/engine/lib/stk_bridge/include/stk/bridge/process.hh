/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * A child process with piped stdin / stdout / stderr, in its own process group (POSIX) or job
 * object (Windows), so the bridge and anything it started in that group can be terminated
 * together without touching the app.
 *
 * - Linux / macOS: posix_spawn (POSIX_SPAWN_SETPGROUP, default signal dispositions, empty signal
 *   mask); every pipe end is close-on-exec in the parent, the child gets exactly fds 0-2.
 *   Writes never raise SIGPIPE in the app (the writing thread blocks it; macOS: F_SETNOSIGPIPE).
 * - Windows: CreateProcessW with an explicit inheritable-handle list (the three pipe ends),
 *   CREATE_NO_WINDOW, a Unicode environment block, started suspended and assigned to a job object
 *   (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, BREAKAWAY_OK for detached helpers) before it runs.
 *
 * Detached services the child starts in a new session (the local Runtime) are not in the group and
 * keep running, as jobs must when the app closes.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::bridge {

struct SpawnOptions {
  /** argv[0] is the executable: an absolute path or a name looked up on PATH. UTF-8. */
  std::vector<std::string> argv;
  /** Environment changes on top of the app's environment: a value sets, nullopt removes. */
  std::map<std::string, std::optional<std::string>> env;
  /** Working directory (empty: the app's). */
  std::string cwd;
};

struct ExitStatus {
  /** Exit code when the process exited normally, else -1. */
  int code = -1;
  /** POSIX signal that ended the process (0 when it exited). */
  int signal = 0;
  bool success() const
  {
    return code == 0 && signal == 0;
  }
  std::string describe() const;
};

class ChildProcess {
 public:
  enum class Stream { Stdout, Stderr };

  /** Starts the process; nullptr with `r_error` on failure (executable missing, ...). */
  static std::unique_ptr<ChildProcess> spawn(const SpawnOptions &options, std::string &r_error);
  /** Kills the whole group if it still runs, reaps it and closes every handle. */
  ~ChildProcess();
  ChildProcess(const ChildProcess &) = delete;
  ChildProcess &operator=(const ChildProcess &) = delete;

  int64_t pid() const;

  /** Writes all bytes to the child's stdin (blocking). False once the pipe is broken or closed. */
  bool write_stdin(std::string_view data);
  /** EOF for the child (idempotent). */
  void close_stdin();
  /**
   * Blocking read of up to `size` bytes: > 0 bytes read, 0 at EOF or after #abort_reads, < 0 on
   * an error. One reader per stream.
   */
  std::ptrdiff_t read(Stream stream, char *buffer, size_t size);
  /** Makes pending and future #read calls return 0 (thread-safe). */
  void abort_reads();

  /**
   * Waits up to `timeout_s` (< 0: forever) for the process to exit; the exit status once it did.
   * When it exited, the rest of its process group / job is killed and the process is reaped.
   */
  std::optional<ExitStatus> wait(double timeout_s);
  /** The exit status if the process has exited (non-blocking #wait). */
  std::optional<ExitStatus> poll()
  {
    return wait(0.0);
  }
  /** Asks the process group to stop (SIGTERM; Windows: terminates the job). */
  void terminate();
  /** Kills the process group (SIGKILL; Windows: terminates the job). */
  void kill();
  /** Whether any process of the group / job is still alive (tests: no strays). */
  bool group_alive() const;

  struct Impl;

 private:
  explicit ChildProcess(std::unique_ptr<Impl> impl);
  std::unique_ptr<Impl> impl_;
};

/** An executable on PATH (Windows: also with PATHEXT extensions); nullopt when not found. */
std::optional<std::string> find_executable(std::string_view name);

}  // namespace stk::bridge
