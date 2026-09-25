/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Helpers of the WP10 viewer tests: a manual main loop for bridge callbacks, temporary
 * directories, repository paths, the fake bridge, and fixture writers (result / series folders). */
#pragma once

#include <chrono>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

#include "stk/app/app_store.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/client.hh"
#include "stk/io/json.hh"

namespace stk::apptest {

std::string repo_root();
std::filesystem::path fixture_payload_dir();  /**< desktop/tests/viewer/fixtures/muferro_domains */
std::filesystem::path fixture_stkp();         /**< .../muferro_domains.stkp */
std::string fake_bridge_path();

/** A main-loop stand-in: the executor queues, the test thread runs the tasks. */
class ManualLoop {
 public:
  bridge::Executor executor();
  /** Runs queued tasks (and `each` after every round) until `until()` or the timeout. */
  bool pump_until(const std::function<bool()> &until, double timeout_s = 30.0, const std::function<void()> &each = {});
  void run_ready();

 private:
  std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> tasks_;
};

class TempDir {
 public:
  explicit TempDir(const std::string &tag);
  ~TempDir();
  const std::filesystem::path &path() const
  {
    return path_;
  }
  std::string str() const
  {
    return path_.string();
  }

 private:
  std::filesystem::path path_;
};

/** graph.presets-shaped {presets: [...]} from suan/graph/presets and the M1 catalog document. */
io::Json repo_presets();
io::Json repo_catalog();

/** A CLI result folder (result.json + view/manifest.json + buffers) of the fixture payload. */
void write_result_dir(const std::filesystem::path &dir, const io::Json &step = io::Json());
/** A CLI series folder: series.json over `steps`, one result.<step>.json + payload folder each. */
void write_series_dir(const std::filesystem::path &dir, const std::vector<int> &steps);

bool write_text(const std::string &path, const std::string &text);
std::string read_text(const std::string &path);

/** Runs a command to completion (stdout into `out`); its exit code, -1 when it cannot start. */
int run_command(const std::vector<std::string> &argv, std::string *out = nullptr, double timeout_s = 300.0);
/** The interpreter of the Python-bridge tests ($STK_BRIDGE_TEST_PYTHON, else the CMake setting,
 * else python3); "" with `reason` when it cannot evaluate graphs locally (numpy / VTK missing). */
std::string graph_python(std::string &reason);
/** Writes a fake muFerro run (tests/mupro_fake.write_domain_run, 16 x 12 x 10, 2 steps). */
bool write_fake_run(const std::string &python, const std::string &dir);
/** Options of the real bridge, isolated under `dir` (state, cache, profiles, graph cache). */
bridge::ClientOptions python_bridge_options(const std::string &python, const std::string &dir, bridge::Executor executor);

/**
 * A ViewerState on an AppStore whose bridge is the scripted fake (graph methods on, the fixture
 * payload for every step), with a controllable clock.
 */
struct FakeViewer {
  explicit FakeViewer(const std::vector<std::string> &extra_args = {});
  ~FakeViewer();

  ManualLoop loop;
  TempDir dir{"viewer-fake"};
  app::AppStore store;
  std::unique_ptr<bridge::Client> client;
  app::ViewerState *vs = nullptr;
  double t = 1000.0;

  /** Pumps bridge callbacks and ViewerState::pump until `until()`. */
  bool pump_until(const std::function<bool()> &until, double timeout_s = 30.0);
  /** Advances the fake clock and pumps once (debounce, playback). */
  void advance(double seconds);
  /** The fake bridge's counters (stats). */
  io::Json stats();
  /** An empty run folder that guess_preset() takes for muFerro. */
  std::string run_dir();
};

}  // namespace stk::apptest
