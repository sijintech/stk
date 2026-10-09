/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/model_settings.hh"

#include "stk/app/app_store.hh"

namespace stk::app {
using io::Json;

ModelSettings::ModelSettings(AppStore &store) : store_(store) {}

ModelSettings::~ModelSettings()
{
  *alive_ = false;
  if (read_) { read_->cancel(); }
  if (write_) { write_->cancel(); }
}

void ModelSettings::reset()
{
  ++epoch_; ++version_;
  endpoints_ = Json::array(); network_.clear(); error_.clear();
  stale_ = true; loaded_ = false;
  for (auto *future : {&read_, &write_}) {
    auto old = std::move(*future); future->reset();
    if (old) { old->cancel(); }
  }
  store_.changed();
}

bool ModelSettings::supported() const
{
  if (!client_ || client_->state() != bridge::BridgeState::Ready) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("models.list");
}

bool ModelSettings::editable() const
{
  if (!supported()) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"models.endpoints.add", "models.endpoints.remove", "models.keys.set", "models.keys.clear",
                             "models.policy.set"}) {
    if (!hello->has_method(method)) { return false; }
  }
  return true;
}

void ModelSettings::sync()
{
  auto *client = store_.bridge();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_) {
    if (client != client_) {
      listener_ = {};
      const std::weak_ptr<bool> weak = alive_;
      if (client) {
        listener_ = client->on_event("models.changed", [this, weak](const auto &, const Json &) {
          if (const auto alive = weak.lock(); alive && *alive) { stale_ = true; store_.changed(); }
        });
      }
    }
    client_ = client; session_ = session;
    reset();
  }
  if (stale_ && supported() && !busy()) { read(); }
}

bool ModelSettings::read()
{
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  stale_ = false;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  read_ = client_->call("models.list", Json::object(), options);
  read_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    read_.reset();
    if (!result) { error_ = result.error().describe(); store_.changed(); return; }
    endpoints_ = result.value().value("endpoints", Json::array());
    network_ = io::get_string(result.value().value("policy", Json::object()), "network");
    error_.clear(); loaded_ = true; ++version_;
    store_.changed();
  });
  return true;
}

bool ModelSettings::write(const std::string &method, Json params)
{
  sync();
  if (!editable() || write_) { return false; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  write_ = client_->call(method, std::move(params), options);
  write_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    write_.reset();
    if (!result) {
      error_ = result.error().message;
      if (store_.toast) { store_.toast(result.error().message, ui::ToastKind::Warning); }
    }
    else { error_.clear(); }
    stale_ = true;  // models.changed follows too; reading twice is harmless
    store_.changed();
  });
  store_.changed();
  return true;
}

const Json *ModelSettings::endpoint(const std::string &id) const
{
  for (const auto &item : endpoints_) { if (io::get_string(item, "id") == id) { return &item; } }
  return nullptr;
}

const Json *ModelSettings::by_adapter(const std::string &adapter) const
{
  for (const auto &item : endpoints_) { if (io::get_string(item, "adapter") == adapter) { return &item; } }
  return nullptr;
}

bool ModelSettings::add_endpoint(const std::string &id, const std::string &name, const std::string &base_url,
                                 const std::vector<std::string> &models, const std::string &location)
{
  Json params = {{"id", id}, {"name", name}, {"base_url", base_url}, {"models", models}};
  if (!location.empty()) { params["location"] = location; }
  return write("models.endpoints.add", std::move(params));
}

bool ModelSettings::remove_endpoint(const std::string &id) { return write("models.endpoints.remove", {{"id", id}}); }

bool ModelSettings::set_key(const std::string &id, std::string key, const bool remember)
{
  return write("models.keys.set", {{"id", id}, {"key", std::move(key)}, {"remember", remember}});
}

bool ModelSettings::clear_key(const std::string &id) { return write("models.keys.clear", {{"id", id}}); }

bool ModelSettings::set_network(const std::string &network) { return write("models.policy.set", {{"network", network}}); }
}  // namespace stk::app
