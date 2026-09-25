/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "support.hh"

#include <atomic>
#include <cerrno>
#include <csignal>
#include <fstream>
#include <random>
#include <sstream>

#if !defined(_WIN32)
#  include <sys/types.h>
#  include <unistd.h>
#endif

namespace stk::bridge::test {

bool wait_until(const std::function<bool()> &predicate, const double timeout_s)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::microseconds(int64_t(timeout_s * 1e6));
  while (!predicate()) {
    if (std::chrono::steady_clock::now() >= deadline) {
      return false;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  return true;
}

TempDir::TempDir(const std::string &tag)
{
  static std::atomic<int> counter{0};
  std::random_device random;
  const std::filesystem::path root = std::filesystem::path(STK_BRIDGE_TEST_SCRATCH);
  std::filesystem::create_directories(root);
  std::ostringstream name;
  name << tag << "-" << counter.fetch_add(1) << "-" << std::hex << random();
  path_ = root / name.str();
  std::filesystem::remove_all(path_);
  std::filesystem::create_directories(path_);
}

TempDir::~TempDir()
{
  std::error_code ignored;
  std::filesystem::remove_all(path_, ignored);
}

std::vector<long> processes_matching(const std::string &needle)
{
  std::vector<long> out;
#if defined(__linux__)
  for (const auto &entry : std::filesystem::directory_iterator("/proc")) {
    const std::string name = entry.path().filename().string();
    if (name.empty() || name.find_first_not_of("0123456789") != std::string::npos) {
      continue;
    }
    std::ifstream in(entry.path() / "cmdline", std::ios::binary);
    std::string cmdline((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (cmdline.find(needle) == std::string::npos) {
      continue;
    }
    /* Zombies waiting for their reaper are gone for our purposes. */
    std::ifstream stat(entry.path() / "stat");
    std::string line;
    std::getline(stat, line);
    const size_t paren = line.rfind(')');
    if (paren != std::string::npos && paren + 2 < line.size() && line[paren + 2] == 'Z') {
      continue;
    }
    const long pid = std::stol(name);
    if (pid != long(getpid())) {
      out.push_back(pid);
    }
  }
#else
  (void)needle;
#endif
  return out;
}

bool process_group_alive(const long pgid)
{
#if defined(_WIN32)
  (void)pgid;
  return false;
#else
  return ::kill(-pid_t(pgid), 0) == 0 || errno == EPERM;
#endif
}

bool process_alive(const long pid)
{
#if defined(_WIN32)
  (void)pid;
  return false;
#else
  if (::kill(pid_t(pid), 0) != 0 && errno != EPERM) {
    return false;
  }
#  if defined(__linux__)
  std::ifstream stat("/proc/" + std::to_string(pid) + "/stat");
  std::string line;
  std::getline(stat, line);
  const size_t paren = line.rfind(')');
  if (paren != std::string::npos && paren + 2 < line.size() && line[paren + 2] == 'Z') {
    return false;
  }
#  endif
  return true;
#endif
}

void kill_hard(const long pid)
{
#if !defined(_WIN32)
  ::kill(pid_t(pid), SIGKILL);
#else
  (void)pid;
#endif
}

std::string fake_bridge_path()
{
  return STK_BRIDGE_FAKE;
}

ClientOptions fake_options(const std::vector<std::string> &args, Executor executor)
{
  ClientOptions options;
  options.command = {fake_bridge_path()};
  options.command.insert(options.command.end(), args.begin(), args.end());
  options.executor = std::move(executor);
  options.restart.initial_backoff_s = 0.02;
  options.restart.max_backoff_s = 0.2;
  options.call_timeout_s = 20.0;
  options.hello_timeout_s = 10.0;
  options.shutdown_grace_s = 5.0;
  return options;
}

}  // namespace stk::bridge::test
