/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Logs editor (the application log: operations, their outcomes and errors, with timestamps)
 * and the Bridge-log editor (the Python bridge's stderr ring and the client's lifecycle notes,
 * mirrored by BridgeStatus, plus the bridge's state and a restart after it failed).
 */

#include "stk/bridge/client.hh"

#include "../app_theme.hh"
#include "jobs_common.hh"

namespace stk::app {

namespace {

using namespace jobs_ui;

class LogsEditor final : public Editor {
 public:
  explicit LogsEditor(const EditorType &type) : Editor(type) {}

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kListBack;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    const std::string_view clear = ctx.tr("logs.clear");
    ui::LogBuffer &log = ctx.store.app_log();
    AppStore &store = ctx.store;
    row.button("clear", clear, [&log, &store]() {
         log.clear();
         store.changed();
       })
        .width(fit_units(ctx, clear))
        .tip(ctx.tr("logs.clear.tip"));
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    ui::LogBuffer &log = ctx.store.app_log();
    l.label(ctx.store.catalog().format("logs.app.summary", {{"lines", std::to_string(log.line_count())}}))
        .tip(ctx.tr("logs.app.tip"));
    l.log_view("log", log, fill_units(ctx, 2.0f));
  }
};

class BridgeLogEditor final : public Editor {
 public:
  explicit BridgeLogEditor(const EditorType &type) : Editor(type) {}

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kListBack;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    bridge::Client *client = ctx.store.bridge();
    const std::string_view restart = ctx.tr("logs.bridge.restart");
    row.button("restart", restart, [client]() {
         if (client) {
           client->restart();
         }
       })
        .width(fit_units(ctx, restart))
        .disable(!client || ctx.store.bridge_state() != BridgeState::Failed)
        .tip(ctx.tr("logs.bridge.restart.tip"));
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    AppStore &store = ctx.store;
    std::string line = store.catalog().format(
        "app.status.bridge", {{"state", std::string(store.tr(bridge_state_key(store.bridge_state())))}});
    std::string tip;
    if (bridge::Client *c = store.bridge()) {
      const bridge::ClientStats s = c->stats();
      line += "  ·  " + store.catalog().format("logs.bridge.stats", {{"pid", std::to_string(c->bridge_pid())},
                                                                      {"restarts", std::to_string(s.restarts)},
                                                                      {"calls", std::to_string(s.calls_sent)}});
      if (const auto hello = c->hello_info()) {
        tip = hello->server.name + " " + hello->server.version + " · Python " + hello->server.python + "\n" +
              hello->paths.state_dir;
      }
    }
    if (!store.bridge_error().empty()) {
      tip += (tip.empty() ? "" : "\n") + store.bridge_error();
    }
    l.label(line).tip(tip.empty() ? std::string(ctx.tr("logs.bridge.tip")) : tip);
    l.log_view("log", store.bridge_log(), fill_units(ctx, 2.0f));
  }
};

}  // namespace

std::unique_ptr<Editor> make_logs_editor(const EditorType &type)
{
  return std::make_unique<LogsEditor>(type);
}

std::unique_ptr<Editor> make_bridge_log_editor(const EditorType &type)
{
  return std::make_unique<BridgeLogEditor>(type);
}

}  // namespace stk::app
