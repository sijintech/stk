/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_archive.hh"

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

namespace stk::app {
using io::Json;

ProjectArchive::ProjectArchive(AppStore &store) : store_(store), project_(store.project()) {}

ProjectArchive::~ProjectArchive()
{
  *alive_ = false;
  if (read_) { read_->cancel(); }
  if (write_) { write_->cancel(); }
}

void ProjectArchive::changed() { store_.changed(); }

void ProjectArchive::reset()
{
  ++epoch_;
  if (!ids_.empty()) { ids_.clear(); ++version_; }
  error_.clear(); stale_ = true; read_once_ = noticed_ = false;
  for (auto *future : {&read_, &write_}) {
    auto old = std::move(*future); future->reset();
    if (old) { old->cancel(); }
  }
  changed();
}

bool ProjectArchive::supported() const
{
  if (!client_ || handle_.empty() || !project_.project() || project_.project()->handle != handle_ ||
      project_.project()->format_version < 11) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.archive.set") && hello->has_method("project.archive.list");
}

void ProjectArchive::sync()
{
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    if (client != client_) {
      listener_ = {};
      const std::weak_ptr<bool> weak = alive_;
      if (client) {
        listener_ = client->on_event("project.archive.changed", [this, weak](const auto &, const Json &data) {
          if (const auto alive = weak.lock(); alive && *alive && io::get_string(data, "handle") == handle_) {
            stale_ = noticed_ = true; store_.changed();
          }
        });
      }
    }
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
  if (stale_ && supported() && !busy()) { read(); }
}

bool ProjectArchive::read()
{
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  stale_ = false;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  read_ = client_->call("project.archive.list", {{"handle", handle_}}, options);
  read_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    read_.reset();
    if (!result) { error_ = result.error().describe(); changed(); return; }
    std::map<std::string, std::set<std::string>> ids;
    for (const auto &item : result.value().value("items", Json::array())) {
      ids[io::get_string(item, "kind")].insert(io::get_string(item, "id"));
    }
    error_.clear();
    const bool differ = ids != ids_;
    if (differ) { ids_ = std::move(ids); }
    if ((differ && read_once_) || noticed_) { ++version_; }
    read_once_ = true; noticed_ = false;
    changed();
  });
  return true;
}

bool ProjectArchive::archived(const std::string &kind, const std::string &id) const
{
  const auto found = ids_.find(kind);
  return found != ids_.end() && found->second.count(id) != 0;
}

int64_t ProjectArchive::count(const std::string &kind) const
{
  const auto found = ids_.find(kind);
  return found == ids_.end() ? 0 : int64_t(found->second.size());
}

bool ProjectArchive::set(const std::string &kind, const std::vector<std::string> &ids, const bool archived,
                         const bool include_runs)
{
  sync();
  if (!supported() || write_ || ids.empty() || ids.size() > 100) { return false; }
  Json items = Json::array();
  for (const auto &id : ids) { items.push_back({{"kind", kind}, {"id", id}}); }
  Json params = {{"handle", handle_}, {"items", items}, {"archived", archived}};
  if (include_runs) { params["include_runs"] = true; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  write_ = client_->call("project.archive.set", std::move(params), options);
  write_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    write_.reset();
    if (!result) {
      error_ = result.error().describe();
      if (store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
    }
    else { noticed_ = true; }
    stale_ = true;  // read again: the event may also arrive, reading twice is harmless
    changed();
  });
  changed();
  return true;
}
}  // namespace stk::app
