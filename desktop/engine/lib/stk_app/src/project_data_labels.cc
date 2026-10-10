/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_data_labels.hh"

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

namespace stk::app {
using io::Json;

ProjectDataLabels::ProjectDataLabels(AppStore &store) : store_(store), project_(store.project()) {}

ProjectDataLabels::~ProjectDataLabels()
{
  *alive_ = false;
  if (read_) { read_->cancel(); }
  if (write_) { write_->cancel(); }
}

void ProjectDataLabels::reset()
{
  ++epoch_; ++version_;
  labels_.clear(); stale_ = true; loaded_ = false;
  for (auto *future : {&read_, &write_}) {
    auto old = std::move(*future); future->reset();
    if (old) { old->cancel(); }
  }
  store_.changed();
}

bool ProjectDataLabels::supported() const
{
  if (!client_ || handle_.empty() || !project_.project() || project_.project()->handle != handle_ ||
      project_.project()->format_version < 12) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.labels.set") && hello->has_method("project.labels.list");
}

bool ProjectDataLabels::structure_supported() const
{
  return supported() && project_.project()->format_version >= 13;
}

void ProjectDataLabels::sync()
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
        listener_ = client->on_event("project.labels.changed", [this, weak](const auto &, const Json &data) {
          if (const auto alive = weak.lock(); alive && *alive && io::get_string(data, "handle") == handle_) {
            stale_ = true; store_.changed();
          }
        });
      }
    }
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
  if (stale_ && supported() && !busy()) { read(); }
}

bool ProjectDataLabels::read()
{
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  stale_ = false;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  Json params = {{"handle", handle_}};
  if (structure_supported()) { params["include_structure"] = true; }  // older services refuse the parameter
  read_ = client_->call("project.labels.list", params, options);
  read_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    read_.reset();
    if (!result) { store_.changed(); return; }
    std::map<std::string, std::map<std::string, std::string>> labels;
    for (const auto &item : result.value().value("items", Json::array())) {
      const auto label = io::get_string(item, "label");
      labels[io::get_string(item, "kind")][io::get_string(item, "id")] = label.empty() ? "public" : label;
    }
    if (labels != labels_ || !loaded_) { labels_ = std::move(labels); ++version_; }
    loaded_ = true;
    store_.changed();
  });
  return true;
}

bool ProjectDataLabels::is_public(const std::string &kind, const std::string &id) const
{
  return label(kind, id) == "public";
}

std::string ProjectDataLabels::label(const std::string &kind, const std::string &id) const
{
  const auto found = labels_.find(kind);
  if (found == labels_.end()) { return "private"; }
  const auto label = found->second.find(id);
  return label == found->second.end() ? "private" : label->second;
}

bool ProjectDataLabels::set(const std::string &kind, const std::vector<std::string> &ids, const bool make_public)
{
  return set(kind, ids, std::string(make_public ? "public" : "private"));
}

bool ProjectDataLabels::set(const std::string &kind, const std::vector<std::string> &ids, const std::string &label)
{
  sync();
  if (!supported() || write_ || ids.empty() || ids.size() > 100) { return false; }
  if (label != "public" && label != "private" && (label != "structure" || kind != "table" || !structure_supported())) {
    return false;
  }
  Json items = Json::array();
  for (const auto &id : ids) { items.push_back({{"kind", kind}, {"id", id}}); }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  write_ = client_->call("project.labels.set", {{"handle", handle_}, {"items", items},
                                                {"label", label}}, options);
  write_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    write_.reset();
    if (!result && store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
    stale_ = true;
    store_.changed();
  });
  store_.changed();
  return true;
}
}  // namespace stk::app
