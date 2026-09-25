/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * AppStore: the application state shared by all editors and windows. Editors read it while
 * building their UI every frame and change it from widget callbacks; #changed tags the windows
 * for redraw. WP3 holds the placeholders (language, UI scale, bridge state, connection, logs,
 * dropped files); WP8-WP10 extend it with the bridge client, connections, tasks and viewer data.
 * Main thread only (background services hand results over with WindowManager::post).
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "stk/ui/i18n.hh"
#include "stk/ui/log_buffer.hh"
#include "stk/ui/ui.hh"

namespace stk::bridge {
class Client;
}

namespace stk::app {

class ViewerState;

/**
 * A request to show a result in the Viewer (raised by the Jobs editor, "Open in viewer"; consumed
 * by the Viewer editor, which also brings a Viewer area to the front). Either a task on a
 * connection or local paths (a result directory, a payload directory / .stkp, or a run directory
 * for local graph evaluation).
 */
struct OpenResultRequest {
  std::string connection;   /**< Bridge connection id ("local", "runtime:<name>", "hub:<name>"). */
  std::string node;         /**< Hub node, empty for Runtime / local connections. */
  std::string workspace_id; /**< Optional. */
  std::string task_id;      /**< Empty when opening local paths. */
  std::string preset;       /**< Graph preset to evaluate; empty = let the Viewer choose. */
  std::vector<std::string> local_paths;
};

/** State of the Python bridge child process (driven by stk_bridge from WP8 on). */
enum class BridgeState : uint8_t { NotStarted, Starting, Ready, Restarting, Failed, Stopping };
/** Catalog key of a bridge state ("app.status.bridge.ready", ...). */
const char *bridge_state_key(BridgeState state);

class AppStore {
 public:
  AppStore();
  ~AppStore();

  ui::Catalog &catalog()
  {
    return catalog_;
  }
  const ui::Catalog &catalog() const
  {
    return catalog_;
  }
  std::string_view tr(std::string_view key) const
  {
    return catalog_.tr(key);
  }
  const std::string &language() const
  {
    return catalog_.language();
  }
  void set_language(const std::string &language);

  /** User UI scale (multiplied with the display DPI factor). */
  float ui_scale() const
  {
    return ui_scale_;
  }
  void set_ui_scale(float scale);

  BridgeState bridge_state() const
  {
    return bridge_;
  }
  void set_bridge_state(BridgeState state);
  /** Why the bridge failed or last restarted (status-bar tooltip); empty when fine. */
  const std::string &bridge_error() const
  {
    return bridge_error_;
  }
  void set_bridge_error(std::string error);
  /** Active connection (Runtime profile or hub); empty = not connected. */
  const std::string &connection() const
  {
    return connection_;
  }
  void set_connection(std::string connection);

  /** The bridge client, or null (headless renders, --no-bridge). Not owned. */
  bridge::Client *bridge() const
  {
    return bridge_client_;
  }
  void set_bridge(bridge::Client *client)
  {
    bridge_client_ = client;
  }

  /** Queues a request for the Viewer (replaces an unconsumed one) and calls #changed. */
  void request_open_result(OpenResultRequest request);
  /** Takes the pending request, if any (the Viewer editor calls this while building its UI). */
  std::optional<OpenResultRequest> take_open_result();
  bool has_open_result() const
  {
    return pending_open_.has_value();
  }

  /** The result shown by the Viewer, Properties and Probe editors (WP10; created on first use). */
  ViewerState &viewer();

  /** Application log (Logs editor) and bridge stderr / protocol log (Bridge log editor). */
  ui::LogBuffer &app_log()
  {
    return app_log_;
  }
  ui::LogBuffer &bridge_log()
  {
    return bridge_log_;
  }
  /** Appends one line to the application log, prefixed with #clock() when set. */
  void log(std::string_view line);

  /** Timestamp for log lines ("HH:MM:SS"); unset in headless renders so they stay deterministic. */
  std::function<std::string()> clock;
  /** Shows a toast in the windows (set by the shell). */
  std::function<void(const std::string &text, ui::ToastKind kind)> toast;
  /** Called on every change (the shell tags the windows for redraw). */
  std::function<void()> on_change;
  void changed();
  uint64_t version() const
  {
    return version_;
  }

 private:
  ui::Catalog catalog_;
  float ui_scale_ = 1.0f;
  BridgeState bridge_ = BridgeState::NotStarted;
  std::string bridge_error_;
  std::string connection_;
  bridge::Client *bridge_client_ = nullptr;
  std::optional<OpenResultRequest> pending_open_;
  std::unique_ptr<ViewerState> viewer_;
  ui::LogBuffer app_log_{20000};
  ui::LogBuffer bridge_log_{20000};
  uint64_t version_ = 0;
};

}  // namespace stk::app
