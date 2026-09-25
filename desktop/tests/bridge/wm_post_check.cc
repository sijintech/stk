/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-wm-post-check: WindowManager::post / executor under a live display (run through
 * tests/wm/run_with_display.py: private Xvfb or headless weston).
 *
 *   - a post from another thread wakes an idle blocking process(true) at once (X11: without
 *     spinning; Wayland: within the 5 ms poll);
 *   - posts from several threads run on the main thread, each thread's in posting order;
 *   - a task posted by a task runs in a later iteration;
 *   - an executor that outlives the manager drops its calls;
 *   - the stk_bridge client delivers its callbacks through the executor.
 *
 * Exit codes: 0 pass, 1 failure, 77 skipped (no display).
 *   stk-wm-post-check [--gpu-backend B] [--fake-bridge PATH]
 */

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <thread>
#include <vector>

#include "stk/bridge/client.hh"
#include "stk/gfx/gpu.hh"
#include "stk/wm/window.hh"

using namespace stk;
using Clock = std::chrono::steady_clock;

namespace {

int g_failures = 0;

void check(const bool ok, const char *what, const std::string &detail = {})
{
  printf("%s %s%s%s\n", ok ? "ok  " : "FAIL", what, detail.empty() ? "" : ": ", detail.c_str());
  fflush(stdout);
  if (!ok) {
    g_failures++;
  }
}

double ms_since(const Clock::time_point t)
{
  return std::chrono::duration<double, std::milli>(Clock::now() - t).count();
}

int run(const gfx::Backend backend, const std::string &fake_bridge)
{
  wm::WmOptions opts;
  opts.gpu.backend = backend;
  opts.window = {"STK post check", 320, 200, false};
  std::string err;
  std::function<void(std::function<void()>)> executor;
  {
    std::unique_ptr<wm::WindowManager> manager = wm::WindowManager::create(opts, err);
    if (!manager) {
      printf("SKIP: %s\n", err.c_str());
      return err.find("no display") != std::string::npos ? 77 : 1;
    }
    wm::WindowManager &wm = *manager;
    const std::string mechanism = wm.wake_mechanism();
    printf("system %s, wake %s\n", wm.system_backend(), mechanism.c_str());
    if (strcmp(wm.system_backend(), "X11") == 0 && !getenv("STK_WM_WAIT")) {
      check(mechanism == "x11-poll-fd", "X11 waits on the X connection and the wake fd", mechanism);
    }
    /* Settle: first frames, expose, focus. */
    const auto settle = Clock::now();
    while (ms_since(settle) < 300) {
      wm.process(false);
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }

    /* 1. Wake-up latency of an idle blocking loop. */
    const std::thread::id main_thread = std::this_thread::get_id();
    for (int round = 0; round < 3; round++) {
      std::atomic<bool> ran{false};
      std::atomic<bool> on_main{false};
      Clock::time_point posted_at;
      std::thread poster([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
        posted_at = Clock::now();
        wm.post([&] {
          on_main = std::this_thread::get_id() == main_thread;
          ran = true;
        });
      });
      int iterations = 0;
      const auto start = Clock::now();
      while (!ran.load() && ms_since(start) < 5000) {
        wm.process(true);
        iterations++;
      }
      poster.join();
      const double latency = ms_since(posted_at);
      check(ran.load() && on_main.load(), "a post from another thread runs on the main thread");
      check(latency < 100.0, "the post woke the blocking wait", std::to_string(latency) + " ms");
      if (mechanism == "x11-poll-fd") {
        /* Blocking for real: a handful of iterations in 250 ms, not a 5 ms poll (~50). */
        check(iterations < 20, "the X11 wait blocks while idle", std::to_string(iterations) + " iterations");
      }
    }

    /* 2. Order and thread of many posts from several threads. */
    constexpr int kThreads = 4, kPosts = 500;
    std::map<int, std::vector<int>> seen;
    std::atomic<int> count{0};
    std::atomic<bool> wrong_thread{false};
    std::vector<std::thread> posters;
    for (int t = 0; t < kThreads; t++) {
      posters.emplace_back([&, t] {
        for (int i = 0; i < kPosts; i++) {
          wm.post([&, t, i] {
            if (std::this_thread::get_id() != main_thread) {
              wrong_thread = true;
            }
            seen[t].push_back(i);
            count++;
          });
        }
      });
    }
    const auto start = Clock::now();
    while (count.load() < kThreads * kPosts && ms_since(start) < 10000) {
      wm.process(true);
    }
    for (std::thread &t : posters) {
      t.join();
    }
    bool ordered = !wrong_thread.load();
    for (int t = 0; t < kThreads; t++) {
      for (int i = 0; i < int(seen[t].size()); i++) {
        ordered &= seen[t][size_t(i)] == i;
      }
    }
    check(count.load() == kThreads * kPosts, "every post ran", std::to_string(count.load()));
    check(ordered, "posts ran on the main thread in each thread's order");

    /* 3. A task posting a task: the second runs in a later iteration. */
    int step = 0;
    wm.post([&] {
      step = 1;
      wm.post([&] { step = 2; });
    });
    wm.process(false);
    check(step == 1, "a task posted by a task waits for the next iteration", std::to_string(step));
    wm.process(false);
    check(step == 2, "... and runs then", std::to_string(step));

    /* 4. The bridge client delivers on the loop. */
    if (!fake_bridge.empty()) {
      bridge::ClientOptions options;
      options.command = {fake_bridge};
      options.executor = wm.executor();
      auto client = bridge::Client::create(options);
      client->start();
      bool answered = false, on_loop = false;
      client->call("echo", {{"from", "wm"}}).then([&](bridge::Result<bridge::Json> r) {
        answered = r.ok() && r.value()["params"]["from"] == "wm";
        on_loop = std::this_thread::get_id() == main_thread;
      });
      const auto t0 = Clock::now();
      while (!answered && ms_since(t0) < 20000) {
        wm.process(true);
      }
      check(answered && on_loop, "stk_bridge callbacks arrive on the main loop");
      client->close();
    }
    executor = wm.executor();
  }
  /* 5. The manager is gone: its executor drops calls instead of crashing. */
  bool ran_late = false;
  executor([&] { ran_late = true; });
  check(!ran_late, "an executor that outlived the manager drops its calls");
  return 0;
}

}  // namespace

int main(int argc, char **argv)
{
  std::string backend_arg, fake_bridge;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--gpu-backend") && i + 1 < argc) {
      backend_arg = argv[++i];
    }
    else if (!strcmp(argv[i], "--fake-bridge") && i + 1 < argc) {
      fake_bridge = argv[++i];
    }
    else {
      fprintf(stderr, "usage: %s [--gpu-backend B] [--fake-bridge PATH]\n", argv[0]);
      return 2;
    }
  }
  gfx::Backend backend;
  std::string err;
  if (!gfx::resolve_backend(backend_arg, backend, err)) {
    fprintf(stderr, "%s\n", err.c_str());
    return 2;
  }
  int rc;
  {
    gfx::Runtime runtime;
    rc = run(backend, fake_bridge);
  }
  if (rc == 77) {
    return rc;
  }
  printf("%s\n", (rc == 0 && g_failures == 0) ? "PASS" : "FAIL");
  return (rc == 0 && g_failures == 0) ? 0 : 1;
}
