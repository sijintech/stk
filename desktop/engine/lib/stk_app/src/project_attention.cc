/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_attention.hh"

#include "stk/app/app_store.hh"
#include "stk/app/project_archive.hh"
#include "stk/app/project_state.hh"

#include <algorithm>

namespace stk::app {
using io::Json;

ProjectAttention::ProjectAttention(AppStore &store) : store_(store), project_(store.project()) {}

ProjectAttention::~ProjectAttention()
{
  *alive_ = false;
  if (future_) { future_->cancel(); }
}

void ProjectAttention::changed() { ++version_; store_.changed(); }

void ProjectAttention::reset()
{
  ++epoch_;
  result_ = nullptr; error_.clear(); read_revision_ = -1; stale_ = false;
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}

bool ProjectAttention::supported() const
{
  if (!client_ || handle_.empty() || !project_.project() || project_.project()->handle != handle_) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.attention.list") && hello->has_method("project.attention.viewed");
}

void ProjectAttention::sync()
{
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    if (client != client_) {
      runs_listener_ = {};
      const std::weak_ptr<bool> weak = alive_;
      if (client) {
        runs_listener_ = client->on_event("project.runs.changed", [this, weak](const auto &, const Json &data) {
          if (const auto alive = weak.lock(); alive && *alive && io::get_string(data, "handle") == handle_) { stale_ = true; changed(); }
        });
      }
    }
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
  auto &archive = store_.archive();
  archive.sync();
  if (!supported() || future_ || project_.busy()) { return; }
  const auto revision = project_.project()->revision;
  // Archiving never changes the revision: a changed archived set reads again too.
  const bool due = result_.is_null() || revision != read_revision_ || stale_ || archive.version() != read_archive_ ||
      (polling() && std::chrono::steady_clock::now() - read_at_ >= std::chrono::milliseconds(kPollMs));
  if (due) { refresh(); }
}

bool ProjectAttention::polling() const
{
  return result_.is_object() && io::get_int(result_.value("counts", Json::object()), "running", 0) > 0;
}

int64_t ProjectAttention::needs_you() const
{
  return result_.is_object() ? io::get_int(result_.value("counts", Json::object()), "needs_you", 0) : 0;
}

bool ProjectAttention::refresh()
{
  if (!supported() || future_) { return false; }
  const auto epoch = epoch_;
  const auto revision = project_.project()->revision;
  const std::weak_ptr<bool> weak = alive_;
  read_at_ = std::chrono::steady_clock::now();
  read_revision_ = revision; read_archive_ = store_.archive().version();
  stale_ = false;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call("project.attention.list", {{"handle", handle_}}, options);
  future_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    future_.reset();
    if (!result) { error_ = result.error().describe(); }
    else if (!result.value().is_object() || !result.value().contains("items") || !result.value().at("items").is_array()) {
      error_ = "Invalid attention response";
    }
    else { result_ = result.value(); error_.clear(); }
    changed();
  });
  return true;
}

bool ProjectAttention::mark_viewed(std::vector<std::string> keys)
{
  if (!supported() || keys.empty()) { return false; }
  // Shown as viewed at once; the reply is not waited for (the next read reflects the stored marks).
  if (result_.is_object()) {
    for (auto &item : result_["items"]) {
      if (std::find(keys.begin(), keys.end(), io::get_string(item, "key")) != keys.end()) { item["viewed"] = true; }
    }
    auto &counts = result_["counts"];
    int64_t needs = 0, done = 0;
    for (const auto &item : result_["items"]) {
      if (io::get_bool(item, "viewed", false)) { continue; }
      if (io::get_string(item, "group") == "needs_you") { ++needs; }
      if (io::get_string(item, "group") == "done") { ++done; }
    }
    counts["needs_you"] = needs; counts["unviewed_done"] = done;
  }
  // A read already on its way may predate the marks: drop it and read again once they are stored.
  if (future_) {
    ++epoch_;
    auto old = std::move(future_); future_.reset();
    old->cancel();
  }
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  client_->call("project.attention.viewed", {{"handle", handle_}, {"keys", keys}}, options)
      .then([this, weak, epoch](bridge::Result<Json> result) {
        const auto alive = weak.lock();
        if (!alive || !*alive || epoch != epoch_) { return; }
        if (!result) { error_ = result.error().describe(); }
        stale_ = true;
        changed();
      });
  changed();
  return true;
}
}  // namespace stk::app
