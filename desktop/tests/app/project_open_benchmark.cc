/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Optional CPU desktop/real-bridge benchmark. The Python driver owns synthetic inputs and RSS sampling. */
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <algorithm>
#include <chrono>
#include <iostream>

using namespace stk;
int main(int argc, char **argv)
{
  if (argc != 5) { return 2; }
  const std::string python = argv[1], wrapper = argv[2], control = argv[3], directory = argv[4];
  bridge::test::ManualLoop loop;
  wmtest::AppFixture app{"en", 1, 1440, 1200};
  bridge::ClientOptions options;
  options.python.configured = python; options.executor = loop.executor();
  options.state_dir = control + "/state"; options.cache_dir = control + "/cache";
  options.command = {python, "-u", wrapper, control, "--stdio", "--strict", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir};
  options.env["PYTHONPATH"] = STK_REPO_ROOT;
  options.env["STK_STATE_DIR"] = control + "/runtime";
  options.env["STK_PROFILES_FILE"] = control + "/profiles.json";
  options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
  options.strict = options.validate = true;
  auto client = bridge::Client::create(options);
  struct Detach {
    stk::app::AppStore &store;
    ~Detach() { store.project().attach(nullptr); store.set_bridge(nullptr); }
  } detach{app.shell->store()};
  auto &project = app.shell->store().project();
  auto frame = [&] { app.screen.run_deferred(); app.drv->frame(); };
  if (!client->start()) { return 2; }
  app.shell->store().set_bridge(client.get());
  if (!loop.pump_until([&] { frame(); return project.ready(); }, 60)) { return 2; }
  // The driver starts sampling only after the empty desktop and bridge have initialized.
  std::cout << io::Json({{"event", "ready"}, {"bridge_pid", client->bridge_pid()}}).dump() << std::endl;
  std::string go; std::getline(std::cin, go);
  if (go != "open") { return 2; }
  const auto started = std::chrono::steady_clock::now();
  const auto calls_before = client->stats().calls_sent;
  double first_visible = -1;
  bool ok = project.open(directory);
  ok = ok && loop.pump_until([&] {
    frame();
    if (!project.error().empty() || client->state() != bridge::BridgeState::Ready) { return true; }
    const auto *grid = app.screen.ui()->find("a4/main/records");
    if (!project.loaded() || project.busy() || !grid || !grid->table || grid->table->rows == 0) { return false; }
    first_visible = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    return true;
  }, 120);
  const auto *grid = app.screen.ui()->find("a4/main/records");
  ok = ok && first_visible >= 0 && project.loaded() && project.table() && grid && grid->table && project.error().empty();
  io::Json report = {{"event", "result"}, {"ok", ok}, {"first_visible_seconds", first_visible},
      {"calls_sent", client->stats().calls_sent - calls_before}, {"schema_violations", client->stats().schema_violations},
      {"protocol_errors", client->stats().protocol_errors}, {"restarts", client->stats().restarts}};
  if (!ok) { report["error"] = project.error(); }
  if (ok) {
    size_t loaded = 0; int64_t total = 0;
    for (const auto &table : project.tables()) { loaded += table.records.size(); total += table.total_records(); }
    report["tables"] = project.tables().size(); report["total_records"] = total;
    report["shared_loaded_records"] = loaded; report["visible_rows"] = grid->table->rows;
    report["first_value"] = *project.table()->cell(0, 0);
    report["viewer_evaluations"] = app.shell->store().viewer().evaluations_started();
    report["script_runs"] = app.shell->store().scripts().history().size();
    report["project_revision"] = project.project()->revision;
  }
  std::cout << report.dump() << std::endl;
  project.attach(nullptr); app.shell->store().set_bridge(nullptr); client->close(); loop.run_ready();
  return ok ? 0 : 1;
}
