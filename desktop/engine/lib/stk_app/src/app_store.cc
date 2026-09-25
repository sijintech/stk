/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/app_store.hh"

#include "stk/app/jobs_state.hh"
#include "stk/app/viewer_state.hh"

#include <algorithm>
#include <cmath>

namespace stk::app {

const char *bridge_state_key(const BridgeState state)
{
  switch (state) {
    case BridgeState::NotStarted: return "app.status.bridge.not_started";
    case BridgeState::Starting: return "app.status.bridge.starting";
    case BridgeState::Ready: return "app.status.bridge.ready";
    case BridgeState::Restarting: return "app.status.bridge.restarting";
    case BridgeState::Failed: return "app.status.bridge.failed";
    case BridgeState::Stopping: return "app.status.bridge.stopping";
  }
  return "app.status.bridge.not_started";
}

AppStore::AppStore() = default;

AppStore::~AppStore()
{
  /* The editors' states call changed() from their callbacks and refer to this store: drop them
   * (jobs first: its subscriptions may feed the viewer) before the rest of the store. */
  on_change = nullptr;
  jobs_.reset();
  viewer_.reset();
}

JobsState &AppStore::jobs()
{
  if (!jobs_) {
    jobs_ = std::make_unique<JobsState>(*this);
  }
  return *jobs_;
}

ViewerState &AppStore::viewer()
{
  if (!viewer_) {
    viewer_ = std::make_unique<ViewerState>(*this);
  }
  return *viewer_;
}

void AppStore::set_language(const std::string &language)
{
  if (language != catalog_.language()) {
    catalog_.set_language(language);
    changed();
  }
}

void AppStore::set_ui_scale(const float scale)
{
  const float s = std::isfinite(scale) ? std::clamp(scale, 0.25f, 4.0f) : 1.0f;
  if (s != ui_scale_) {
    ui_scale_ = s;
    changed();
  }
}

void AppStore::set_bridge_state(const BridgeState state)
{
  if (state != bridge_) {
    bridge_ = state;
    changed();
  }
}

void AppStore::set_bridge_error(std::string error)
{
  if (error != bridge_error_) {
    bridge_error_ = std::move(error);
    changed();
  }
}

void AppStore::set_connection(std::string connection)
{
  if (connection != connection_) {
    connection_ = std::move(connection);
    changed();
  }
}

void AppStore::log(std::string_view line)
{
  std::string s;
  if (clock) {
    s = clock() + "  ";
  }
  s.append(line);
  s.push_back('\n');
  app_log_.append(s);
  changed();
}

void AppStore::changed()
{
  version_++;
  if (on_change) {
    on_change();
  }
}

void AppStore::request_open_result(OpenResultRequest request)
{
  pending_open_ = std::move(request);
  changed();
}

std::optional<OpenResultRequest> AppStore::take_open_result()
{
  std::optional<OpenResultRequest> request = std::move(pending_open_);
  pending_open_.reset();
  return request;
}

}  // namespace stk::app
