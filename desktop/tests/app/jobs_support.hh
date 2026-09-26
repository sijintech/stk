/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Helpers of the Jobs editor tests: catalogs, a JobsState on the fake bridge, demo content. */
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "stk/app/app_store.hh"
#include "stk/app/jobs_state.hh"
#include "stk/bridge/client.hh"
#include "../bridge/support.hh" /* ManualLoop, TempDir, fake_options */

namespace stk::jobstest {

std::string desktop_dir();
/** Loads desktop/app/i18n into the store's catalog and picks `lang` ("en" / "zh_CN"). */
void load_catalogs(app::AppStore &store, const std::string &lang = "en");

/** An AppStore whose JobsState runs against `stk-bridge-fake --jobs DIR` on a manual loop. */
struct FakeJobs {
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"jobs"};
  app::AppStore store;
  std::unique_ptr<bridge::Client> client;
  /** Files the state asked the system to open (open_external is stubbed: no xdg-open in tests). */
  std::vector<std::string> opened;

  /** `extra`: more fake options (--submit-fail 1, --review-refuse, ...). */
  explicit FakeJobs(const std::vector<std::string> &extra = {}, const std::string &lang = "en");
  ~FakeJobs();
  app::JobsState &jobs()
  {
    return store.jobs();
  }
  std::string jobs_dir() const
  {
    return dir.str() + "/model";
  }
  /** Runs posted callbacks until `until` holds (false on timeout). */
  bool pump(const std::function<bool()> &until, double timeout_s = 20.0)
  {
    return loop.pump_until(until, timeout_s);
  }
  /** Pumps for `seconds` (lets the fake's ticker advance). */
  void settle(double seconds);
  /** The methods the fake received (DIR/model/methods.log). */
  std::vector<std::string> methods() const;
  /** Connects to `connection` and waits for its first workspace and watch snapshot. */
  bool connect(const std::string &connection);
  /** Shuts the client down (EOF to the fake), as closing the app does. */
  void close();
};

/**
 * Deterministic content for layout and render goldens, without a bridge: two connections (the
 * Runtime "lab" active and online), a workspace with input files, five tasks in every state,
 * the selected task's logs, two artifacts (result.png verified) and a transfer. `png`: a PNG shown
 * as the preview (empty: none).
 */
void populate_demo(app::JobsState &jobs, const std::string &png = {});

/** Writes a small RGBA gradient PNG (64x48) to `path`. */
void write_demo_png(const std::string &path);

}  // namespace stk::jobstest
