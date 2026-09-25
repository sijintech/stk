/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/bridge_status.hh"

#include "stk/bridge/client.hh"
#include "stk/wm/window.hh"

namespace stk::app {

BridgeState to_app_state(const bridge::BridgeState state)
{
  switch (state) {
    case bridge::BridgeState::Stopped: return BridgeState::NotStarted;
    case bridge::BridgeState::Starting: return BridgeState::Starting;
    case bridge::BridgeState::Ready: return BridgeState::Ready;
    case bridge::BridgeState::Restarting: return BridgeState::Restarting;
    case bridge::BridgeState::Failed: return BridgeState::Failed;
    case bridge::BridgeState::Stopping: return BridgeState::Stopping;
  }
  return BridgeState::NotStarted;
}

struct BridgeStatus::Impl {
  AppStore &store;
  bridge::Client &client;
  wm::WindowManager *wm;
  bridge::ListenerHandle listener;
  uint64_t timer = 0;
  uint64_t last_seq = 0;
};

BridgeStatus::BridgeStatus(AppStore &store, bridge::Client &client, wm::WindowManager *wm, const uint64_t log_poll_ms)
    : impl_(std::make_shared<Impl>(Impl{store, client, wm, {}, 0, 0}))
{
  Impl *d = impl_.get();
  store.set_bridge_state(to_app_state(client.state()));
  /* Runs on the client's executor: the main loop when it is WindowManager::executor(). A call
   * posted before this object was destroyed finds the weak pointer expired. */
  std::weak_ptr<Impl> weak = impl_;
  d->listener = client.on_state([weak](bridge::BridgeState s, const std::optional<bridge::Error> &err) {
    if (const std::shared_ptr<Impl> live = weak.lock()) {
      live->store.set_bridge_error(err ? err->message : std::string());
      live->store.set_bridge_state(to_app_state(s));
    }
  });
  if (wm && log_poll_ms > 0) {
    d->timer = wm->add_timer(log_poll_ms, log_poll_ms, [this]() { poll_log(); });
  }
}

BridgeStatus::~BridgeStatus()
{
  if (impl_->timer && impl_->wm) {
    impl_->wm->remove_timer(impl_->timer);
  }
  /* The listener handle unregisters itself. */
}

void BridgeStatus::poll_log()
{
  Impl &d = *impl_;
  const std::vector<bridge::LogRing::Line> lines = d.client.bridge_log().lines_after(d.last_seq);
  if (lines.empty()) {
    return;
  }
  std::string chunk;
  for (const bridge::LogRing::Line &l : lines) {
    chunk += l.text;
    chunk += '\n';
    d.last_seq = l.seq;
  }
  d.store.bridge_log().append(chunk);
  d.store.changed();
}

}  // namespace stk::app
