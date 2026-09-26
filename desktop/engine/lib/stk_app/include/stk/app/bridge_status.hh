/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * BridgeStatus: mirrors a stk_bridge client into the AppStore for the status bar and the "Bridge
 * log" editor. State changes arrive through the client's executor (create the client with
 * `ClientOptions::executor = wm->executor()`), so they run on the main loop; the bridge's stderr
 * ring is copied into AppStore::bridge_log() by a main-loop timer.
 *
 *   auto client = stk::bridge::Client::create({.executor = wm->executor(), ...});
 *   stk::app::BridgeStatus status(shell.store(), *client, wm.get());
 *   client->start();
 *   ...
 *   // Tear down in reverse: status, then the client, then the window manager.
 */
#pragma once

#include <cstdint>
#include <memory>

#include "stk/app/app_store.hh"

namespace stk::bridge {
class Client;
enum class BridgeState : uint8_t;
}  // namespace stk::bridge
namespace stk::wm {
class WindowManager;
}

namespace stk::app {

/** The status-bar state for a client state. */
BridgeState to_app_state(bridge::BridgeState state);

class BridgeStatus {
 public:
  /** `wm` may be null (no log polling, e.g. tests). */
  BridgeStatus(AppStore &store, bridge::Client &client, wm::WindowManager *wm, uint64_t log_poll_ms = 250);
  ~BridgeStatus();
  BridgeStatus(const BridgeStatus &) = delete;
  BridgeStatus &operator=(const BridgeStatus &) = delete;

  /** Copies new bridge-log lines into the store now (the timer calls it). */
  void poll_log();

 private:
  struct Impl;
  /* Shared so callbacks already posted to the executor can see that this object is gone. */
  std::shared_ptr<Impl> impl_;
};

}  // namespace stk::app
