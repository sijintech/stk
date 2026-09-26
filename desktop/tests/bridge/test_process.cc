/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file ChildProcess: pipes, environment, process group, SIGPIPE safety, aborting reads (POSIX). */

#include <gtest/gtest.h>

#include <csignal>
#include <string>

#include "stk/bridge/process.hh"
#include "support.hh"

namespace stk::bridge {
namespace {

using test::wait_until;

#if !defined(_WIN32)
std::string read_all(ChildProcess &child, ChildProcess::Stream stream)
{
  std::string out;
  char buffer[4096];
  while (true) {
    const std::ptrdiff_t n = child.read(stream, buffer, sizeof(buffer));
    if (n <= 0) {
      break;
    }
    out.append(buffer, size_t(n));
  }
  return out;
}

TEST(Process, PipesEnvironmentAndExitStatus)
{
  SpawnOptions options;
  options.argv = {"sh", "-c", "read line; echo \"got:$line:$STK_T1:${STK_T2-unset}\"; echo err >&2; exit 7"};
  options.env["STK_T1"] = "中文";
  options.env["STK_T2"] = std::nullopt;
  setenv("STK_T2", "present", 1);
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  unsetenv("STK_T2");
  ASSERT_TRUE(child) << error;
  EXPECT_GT(child->pid(), 0);
  ASSERT_TRUE(child->write_stdin("hello\n"));
  child->close_stdin();
  EXPECT_EQ(read_all(*child, ChildProcess::Stream::Stdout), "got:hello:中文:unset\n");
  EXPECT_EQ(read_all(*child, ChildProcess::Stream::Stderr), "err\n");
  const auto status = child->wait(10.0);
  ASSERT_TRUE(status);
  EXPECT_EQ(status->code, 7);
  EXPECT_FALSE(status->success());
}

TEST(Process, MissingExecutableIsAnError)
{
  SpawnOptions options;
  options.argv = {"stk-no-such-program-xyz"};
  std::string error;
  EXPECT_FALSE(ChildProcess::spawn(options, error));
  EXPECT_NE(error.find("not found"), std::string::npos);
  options.argv = {};
  EXPECT_FALSE(ChildProcess::spawn(options, error));
}

TEST(Process, OwnProcessGroupIsKilledWithStrays)
{
  SpawnOptions options;
  options.argv = {"sh", "-c", "sleep 300 & echo started; wait"};
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  ASSERT_TRUE(child) << error;
  char buffer[64];
  ASSERT_GT(child->read(ChildProcess::Stream::Stdout, buffer, sizeof(buffer)), 0);
  const long pgid = long(child->pid());
  EXPECT_TRUE(test::process_group_alive(pgid));
  EXPECT_TRUE(child->group_alive());
  child->kill();
  const auto status = child->wait(10.0);
  ASSERT_TRUE(status);
  EXPECT_EQ(status->signal, SIGKILL);
  EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10.0));
}

TEST(Process, ExitedChildLeavesNoStraysInItsGroup)
{
  /* The shell exits at once; its background sleep would linger without the group kill in wait(). */
  SpawnOptions options;
  options.argv = {"sh", "-c", "sleep 300 >/dev/null 2>&1 & exit 0"};
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  ASSERT_TRUE(child) << error;
  const long pgid = long(child->pid());
  const auto status = child->wait(10.0);
  ASSERT_TRUE(status);
  EXPECT_EQ(status->code, 0);
  EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10.0));
}

TEST(Process, WritingToADeadChildDoesNotRaiseSigpipe)
{
  /* The default SIGPIPE disposition would kill this test process. */
  struct sigaction previous;
  struct sigaction dfl = {};
  dfl.sa_handler = SIG_DFL;
  sigaction(SIGPIPE, &dfl, &previous);
  SpawnOptions options;
  options.argv = {"sh", "-c", "exit 0"};
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  ASSERT_TRUE(child) << error;
  ASSERT_TRUE(child->wait(10.0));
  const std::string big(1 << 20, 'x');
  EXPECT_FALSE(child->write_stdin(big));
  EXPECT_FALSE(child->write_stdin("again\n"));
  sigaction(SIGPIPE, &previous, nullptr);
}

TEST(Process, AbortReadsEndsAReadThatNoDataWillComplete)
{
  /* A helper keeps stderr open after the child exits: the read would block forever. */
  SpawnOptions options;
  options.argv = {"sh", "-c", "sleep 300 & exit 0"};
  std::string error;
  auto child = ChildProcess::spawn(options, error);
  ASSERT_TRUE(child) << error;
  std::atomic<bool> returned{false};
  std::thread reader([&] {
    char buffer[16];
    while (child->read(ChildProcess::Stream::Stderr, buffer, sizeof(buffer)) > 0) {
    }
    returned = true;
  });
  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  EXPECT_FALSE(returned.load());
  child->abort_reads();
  reader.join();
  EXPECT_TRUE(returned.load());
  child->kill();
  child->wait(10.0);
  const long pgid = long(child->pid());
  EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10.0));
}

TEST(Process, DestructorKillsARunningChild)
{
  long pgid = 0;
  {
    SpawnOptions options;
    options.argv = {"sh", "-c", "sleep 300"};
    std::string error;
    auto child = ChildProcess::spawn(options, error);
    ASSERT_TRUE(child) << error;
    pgid = long(child->pid());
  }
  EXPECT_TRUE(wait_until([&] { return !test::process_group_alive(pgid); }, 10.0));
}

TEST(Process, FindExecutable)
{
  EXPECT_TRUE(find_executable("sh").has_value());
  EXPECT_EQ(find_executable("/bin/sh").value_or(""), "/bin/sh");
  EXPECT_FALSE(find_executable("/no/such").has_value());
  EXPECT_FALSE(find_executable("").has_value());
}

#endif

}  // namespace
}  // namespace stk::bridge
