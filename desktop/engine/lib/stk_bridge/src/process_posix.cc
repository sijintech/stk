/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file ChildProcess on Linux and macOS: posix_spawn, pipes, a process group (see process.hh). */

#include "stk/bridge/process.hh"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <mutex>
#include <thread>

#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

namespace stk::bridge {

namespace {

std::string errno_text(const int error)
{
  return std::strerror(error);
}

/** A pipe whose ends are close-on-exec and above the standard descriptors. */
bool make_pipe(int fds[2])
{
#if defined(__linux__)
  if (pipe2(fds, O_CLOEXEC) != 0) {
    return false;
  }
#else
  /* macOS spawns with POSIX_SPAWN_CLOEXEC_DEFAULT, so a concurrent spawn cannot leak these. */
  if (pipe(fds) != 0) {
    return false;
  }
  fcntl(fds[0], F_SETFD, FD_CLOEXEC);
  fcntl(fds[1], F_SETFD, FD_CLOEXEC);
#endif
  for (int i = 0; i < 2; i++) {
    if (fds[i] <= 2) {
      /* A descriptor the child's dup2 targets could alias (the app closed its stdio). */
      const int moved = fcntl(fds[i], F_DUPFD_CLOEXEC, 3);
      close(fds[i]);
      fds[i] = moved;
    }
  }
  return fds[0] >= 0 && fds[1] >= 0;
}

void close_fd(int &fd)
{
  if (fd >= 0) {
    close(fd);
    fd = -1;
  }
}

ExitStatus decode_status(const int status)
{
  ExitStatus exit;
  if (WIFEXITED(status)) {
    exit.code = WEXITSTATUS(status);
  }
  else if (WIFSIGNALED(status)) {
    exit.signal = WTERMSIG(status);
  }
  return exit;
}

}  // namespace

std::string ExitStatus::describe() const
{
  if (signal != 0) {
    return "killed by signal " + std::to_string(signal);
  }
  return "exit code " + std::to_string(code);
}

struct ChildProcess::Impl {
  pid_t pid = -1;
  int in_w = -1, out_r = -1, err_r = -1;
  int abort_r = -1, abort_w = -1;
  std::atomic<bool> aborted{false};
  std::mutex stdin_mutex;
  std::mutex wait_mutex;
  std::optional<ExitStatus> status;
  bool reaped = false;

  ~Impl()
  {
    close_fd(in_w);
    close_fd(out_r);
    close_fd(err_r);
    close_fd(abort_r);
    close_fd(abort_w);
  }
};

ChildProcess::ChildProcess(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}

ChildProcess::~ChildProcess()
{
  if (!impl_) {
    return;
  }
  if (!wait(0.0)) {
    kill();
    wait(-1.0);
  }
  else {
    /* Strays of an exited child were killed by wait(); nothing else to do. */
  }
}

std::optional<std::string> find_executable(const std::string_view name)
{
  if (name.empty()) {
    return std::nullopt;
  }
  const auto usable = [](const std::string &path) {
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode) && access(path.c_str(), X_OK) == 0;
  };
  if (name.find('/') != std::string_view::npos) {
    const std::string path(name);
    return usable(path) ? std::optional(path) : std::nullopt;
  }
  const char *env = getenv("PATH");
  const std::string path_list = env ? env : "/usr/local/bin:/usr/bin:/bin";
  size_t start = 0;
  while (start <= path_list.size()) {
    size_t end = path_list.find(':', start);
    if (end == std::string::npos) {
      end = path_list.size();
    }
    std::string dir = path_list.substr(start, end - start);
    if (dir.empty()) {
      dir = ".";
    }
    const std::string candidate = dir + "/" + std::string(name);
    if (usable(candidate)) {
      return candidate;
    }
    start = end + 1;
  }
  return std::nullopt;
}

std::unique_ptr<ChildProcess> ChildProcess::spawn(const SpawnOptions &options, std::string &r_error)
{
  if (options.argv.empty()) {
    r_error = "no command";
    return nullptr;
  }
  const std::optional<std::string> exe = find_executable(options.argv[0]);
  if (!exe) {
    r_error = "executable not found: " + options.argv[0];
    return nullptr;
  }

  /* Environment: the app's, then the overrides. */
  std::map<std::string, std::string> env;
  for (char **e = environ; e && *e; e++) {
    const char *eq = strchr(*e, '=');
    if (eq) {
      env[std::string(*e, size_t(eq - *e))] = eq + 1;
    }
  }
  for (const auto &[key, value] : options.env) {
    if (value) {
      env[key] = *value;
    }
    else {
      env.erase(key);
    }
  }
  std::vector<std::string> env_strings;
  env_strings.reserve(env.size());
  for (const auto &[key, value] : env) {
    env_strings.push_back(key + "=" + value);
  }
  std::vector<char *> envp;
  for (std::string &s : env_strings) {
    envp.push_back(s.data());
  }
  envp.push_back(nullptr);
  std::vector<std::string> args = options.argv;
  args[0] = *exe;
  std::vector<char *> argv;
  for (std::string &s : args) {
    argv.push_back(s.data());
  }
  argv.push_back(nullptr);

  auto impl = std::make_unique<Impl>();
  int in[2] = {-1, -1}, out[2] = {-1, -1}, err[2] = {-1, -1}, abort_pipe[2] = {-1, -1};
  const auto cleanup = [&] {
    for (int *p : {in, out, err, abort_pipe}) {
      close_fd(p[0]);
      close_fd(p[1]);
    }
  };
  if (!make_pipe(in) || !make_pipe(out) || !make_pipe(err) || !make_pipe(abort_pipe)) {
    r_error = "pipe: " + errno_text(errno);
    cleanup();
    return nullptr;
  }
#if defined(__APPLE__) && defined(F_SETNOSIGPIPE)
  fcntl(in[1], F_SETNOSIGPIPE, 1);
#endif

  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, in[0], 0);
  posix_spawn_file_actions_adddup2(&actions, out[1], 1);
  posix_spawn_file_actions_adddup2(&actions, err[1], 2);
  if (!options.cwd.empty()) {
#if (defined(__GLIBC__) && (__GLIBC__ > 2 || (__GLIBC__ == 2 && __GLIBC_MINOR__ >= 29))) || defined(__APPLE__)
    posix_spawn_file_actions_addchdir_np(&actions, options.cwd.c_str());
#else
    posix_spawn_file_actions_destroy(&actions);
    r_error = "a working directory is not supported by this C library's posix_spawn";
    cleanup();
    return nullptr;
#endif
  }

  posix_spawnattr_t attr;
  posix_spawnattr_init(&attr);
  short flags = POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF;
#if defined(__APPLE__) && defined(POSIX_SPAWN_CLOEXEC_DEFAULT)
  flags |= POSIX_SPAWN_CLOEXEC_DEFAULT;
#endif
  posix_spawnattr_setflags(&attr, flags);
  posix_spawnattr_setpgroup(&attr, 0); /* a new group led by the child */
  sigset_t mask;
  sigemptyset(&mask);
  posix_spawnattr_setsigmask(&attr, &mask);
  sigset_t defaults;
  sigemptyset(&defaults);
  for (const int sig : {SIGPIPE, SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGCHLD, SIGUSR1, SIGUSR2, SIGALRM}) {
    sigaddset(&defaults, sig);
  }
  posix_spawnattr_setsigdefault(&attr, &defaults);

  pid_t pid = -1;
  const int rc = posix_spawn(&pid, exe->c_str(), &actions, &attr, argv.data(), envp.data());
  posix_spawn_file_actions_destroy(&actions);
  posix_spawnattr_destroy(&attr);
  close_fd(in[0]);
  close_fd(out[1]);
  close_fd(err[1]);
  if (rc != 0) {
    r_error = "posix_spawn " + *exe + ": " + errno_text(rc);
    cleanup();
    return nullptr;
  }
  impl->pid = pid;
  impl->in_w = in[1];
  impl->out_r = out[0];
  impl->err_r = err[0];
  impl->abort_r = abort_pipe[0];
  impl->abort_w = abort_pipe[1];
  in[1] = out[0] = err[0] = abort_pipe[0] = abort_pipe[1] = -1;
  return std::unique_ptr<ChildProcess>(new ChildProcess(std::move(impl)));
}

int64_t ChildProcess::pid() const
{
  return impl_->pid;
}

bool ChildProcess::write_stdin(std::string_view data)
{
  std::lock_guard lock(impl_->stdin_mutex);
  if (impl_->in_w < 0) {
    return false;
  }
#if defined(__linux__)
  /* A write to a closed pipe raises SIGPIPE in the writing thread: block it here and consume a
   * signal this write generated, so the app's own SIGPIPE disposition never matters. */
  sigset_t pipe_set, old_set, pending;
  sigemptyset(&pipe_set);
  sigaddset(&pipe_set, SIGPIPE);
  pthread_sigmask(SIG_BLOCK, &pipe_set, &old_set);
  sigpending(&pending);
  const bool was_pending = sigismember(&pending, SIGPIPE) == 1;
#endif
  bool ok = true;
  while (!data.empty()) {
    const ssize_t n = ::write(impl_->in_w, data.data(), data.size());
    if (n < 0) {
      if (errno == EINTR) {
        continue;
      }
      ok = false;
      break;
    }
    data.remove_prefix(size_t(n));
  }
#if defined(__linux__)
  if (!ok && !was_pending) {
    const timespec zero = {0, 0};
    while (sigtimedwait(&pipe_set, nullptr, &zero) < 0 && errno == EINTR) {
    }
  }
  pthread_sigmask(SIG_SETMASK, &old_set, nullptr);
#endif
  return ok;
}

void ChildProcess::close_stdin()
{
  std::lock_guard lock(impl_->stdin_mutex);
  close_fd(impl_->in_w);
}

std::ptrdiff_t ChildProcess::read(const Stream stream, char *buffer, const size_t size)
{
  const int fd = stream == Stream::Stdout ? impl_->out_r : impl_->err_r;
  while (true) {
    if (impl_->aborted.load()) {
      return 0;
    }
    pollfd fds[2] = {{fd, POLLIN, 0}, {impl_->abort_r, POLLIN, 0}};
    const int rc = ::poll(fds, 2, -1);
    if (rc < 0) {
      if (errno == EINTR) {
        continue;
      }
      return -1;
    }
    if (fds[1].revents != 0 || impl_->aborted.load()) {
      return 0;
    }
    if (fds[0].revents & (POLLIN | POLLHUP | POLLERR)) {
      const ssize_t n = ::read(fd, buffer, size);
      if (n < 0 && (errno == EINTR || errno == EAGAIN)) {
        continue;
      }
      return n;
    }
  }
}

void ChildProcess::abort_reads()
{
  if (!impl_->aborted.exchange(true)) {
    const char byte = 1;
    while (::write(impl_->abort_w, &byte, 1) < 0 && errno == EINTR) {
    }
  }
}

std::optional<ExitStatus> ChildProcess::wait(const double timeout_s)
{
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::microseconds(int64_t((timeout_s < 0 ? 0 : timeout_s) * 1e6));
  while (true) {
    /* The lock is held per check, not while sleeping: other threads may poll meanwhile. */
    std::unique_lock lock(impl_->wait_mutex);
    if (impl_->status) {
      return impl_->status;
    }
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    const int rc = waitid(P_PID, id_t(impl_->pid), &info, WEXITED | WNOHANG | WNOWAIT);
    if (rc == 0 && info.si_pid == impl_->pid) {
      /* It exited: kill whatever it left in its group (the group id stays valid until the leader is
       * reaped), then reap it. */
      ::kill(-impl_->pid, SIGKILL);
      int status = 0;
      while (waitpid(impl_->pid, &status, 0) < 0 && errno == EINTR) {
      }
      impl_->status = decode_status(status);
      impl_->reaped = true;
      return impl_->status;
    }
    if (rc < 0 && errno == ECHILD) {
      /* Reaped elsewhere (SIGCHLD ignored by the app): the status is unknown. */
      impl_->status = ExitStatus{};
      impl_->reaped = true;
      return impl_->status;
    }
    lock.unlock();
    if (timeout_s >= 0 && std::chrono::steady_clock::now() >= deadline) {
      return std::nullopt;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
}

void ChildProcess::terminate()
{
  ::kill(-impl_->pid, SIGTERM);
}

void ChildProcess::kill()
{
  ::kill(-impl_->pid, SIGKILL);
}

bool ChildProcess::group_alive() const
{
  if (::kill(-impl_->pid, 0) == 0) {
    return true;
  }
  return errno == EPERM;
}

}  // namespace stk::bridge
