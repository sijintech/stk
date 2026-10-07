/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_search.hh"

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

namespace stk::app {
using io::Json;

ProjectSearch::ProjectSearch(AppStore &store) : store_(store), project_(store.project()) {}

ProjectSearch::~ProjectSearch()
{
  *alive_ = false;
  if (future_) { future_->cancel(); }
}

void ProjectSearch::changed() { ++version_; store_.changed(); }

void ProjectSearch::clear()
{
  ++epoch_;
  result_ = nullptr; error_.clear();
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}

bool ProjectSearch::supported() const
{
  if (!client_ || handle_.empty() || !project_.project() || project_.project()->handle != handle_) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.search");
}

void ProjectSearch::sync()
{
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    client_ = client; session_ = session; handle_ = handle;
    clear();
  }
}

bool ProjectSearch::search(const std::string &query)
{
  sync();
  const auto first = query.find_first_not_of(" \t\r\n");
  if (!supported() || first == std::string::npos) { return false; }
  const auto trimmed = query.substr(first, query.find_last_not_of(" \t\r\n") - first + 1);
  if (trimmed.size() > 800) { return false; }  // 200 characters of at most 4 bytes
  if (future_) { ++epoch_; auto old = std::move(future_); future_.reset(); old->cancel(); }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  error_.clear();
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call("project.search", {{"handle", handle_}, {"query", trimmed}, {"limit", 100}}, options);
  future_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    future_.reset();
    if (!result) { error_ = result.error().describe(); }
    else if (!result.value().is_object() || !result.value().contains("results") || !result.value().at("results").is_array()) {
      error_ = "Invalid search response";
    }
    else { result_ = result.value(); }
    changed();
  });
  changed();
  return true;
}
}  // namespace stk::app
