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
  if (local_read_) { local_read_->cancel(); }
  if (recommend_read_) { recommend_read_->cancel(); }
  if (route_read_) { route_read_->cancel(); }
}

void ModelSettings::reset()
{
  ++epoch_; ++version_;
  endpoints_ = Json::array(); network_.clear(); error_.clear();
  local_ = recommendations_ = nullptr; progress_ = Json::object(); recommendations_failed_ = false;
  routes_.clear(); route_reading_.clear();
  stale_ = local_stale_ = true; loaded_ = false;
  for (auto *future : {&read_, &write_, &local_read_, &recommend_read_, &route_read_}) {
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
      listener_ = {}; progress_listener_ = {};
      const std::weak_ptr<bool> weak = alive_;
      if (client) {
        listener_ = client->on_event("models.changed", [this, weak](const auto &, const Json &) {
          if (const auto alive = weak.lock(); alive && *alive) { stale_ = local_stale_ = true; store_.changed(); }
        });
        progress_listener_ = client->on_event("models.local.progress", [this, weak](const auto &, const Json &data) {
          const auto alive = weak.lock();
          if (!alive || !*alive) { return; }
          const auto entry = io::get_string(data, "id");
          if (!entry.empty()) { progress_[entry] = data; }
          if (io::get_string(data, "state") != "running") { local_stale_ = true; }  // finished, failed or cancelled: read again
          store_.changed();
        });
      }
    }
    client_ = client; session_ = session;
    reset();
  }
  if (stale_ && supported() && !busy()) { read(); }
  if (local_stale_ && local_supported() && !local_read_) { read_local(); }
}

bool ModelSettings::local_supported() const
{
  if (!supported()) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"models.local.list", "models.local.recommendations", "models.local.install", "models.local.import",
                             "models.local.cancel", "models.local.start", "models.local.stop", "models.local.remove"}) {
    if (!hello->has_method(method)) { return false; }
  }
  return true;
}

bool ModelSettings::read_local()
{
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  local_stale_ = false;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  local_read_ = client_->call("models.local.list", Json::object(), options);
  local_read_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    local_read_.reset();
    if (result) { local_ = result.value(); ++version_; }
    else { error_ = result.error().message; }
    store_.changed();
  });
  return true;
}

bool ModelSettings::load_recommendations()
{
  sync();
  if (!local_supported() || recommend_read_) { return false; }
  recommendations_failed_ = false;
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  recommend_read_ = client_->call("models.local.recommendations", Json::object(), options);
  recommend_read_->then([this, weak, epoch](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    recommend_read_.reset();
    if (result) { recommendations_ = result.value(); ++version_; }
    else { error_ = result.error().message; recommendations_failed_ = true; }
    store_.changed();
  });
  store_.changed();
  return true;
}

const Json *ModelSettings::progress(const std::string &entry) const
{
  const auto found = progress_.find(entry);
  return found == progress_.end() ? nullptr : &*found;
}

bool ModelSettings::local_action(const std::string &action, const std::string &entry)
{
  if (!local_supported()) { return false; }
  progress_.erase(entry);  // a new action: its own events follow
  return write("models.local." + action, {{"id", entry}});
}

bool ModelSettings::import_local(const std::string &entry, const std::string &path)
{
  if (!local_supported()) { return false; }
  return write("models.local.import", {{"id", entry}, {"path", path}});
}

bool ModelSettings::route_supported() const
{
  return supported() && client_->hello_info()->has_method("models.route");
}

const Json &ModelSettings::route(const std::string &key, const std::string &handle, const std::string &context_id,
                                 const std::string &prompt_version)
{
  sync();
  if (!route_supported() || context_id.empty()) { return null_; }
  if (const auto found = routes_.find(key); found != routes_.end()) { return found->second; }
  if (route_read_) { return null_; }  // one read at a time; this key is read next
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  route_reading_ = key;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  route_read_ = client_->call("models.route", {{"handle", handle}, {"context_id", context_id}, {"prompt_version", prompt_version}},
                              options);
  route_read_->then([this, weak, epoch, key](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    route_read_.reset();
    route_reading_.clear();
    if (routes_.size() >= 64) { routes_.clear(); }  // keys carry versions: old ones are not asked again
    // An error is kept too, under its key: not asked again until something the route depends on changes.
    routes_[key] = result ? result.value() : Json{{"error", result.error().message}};
    store_.changed();  // not version_: callers key the route by it, and the route does not change the settings
  });
  return null_;
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
    stale_ = local_stale_ = true;  // read both after the change (models.changed may follow too; reading twice is harmless)
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
                                 const std::vector<std::string> &models, const std::string &location, const std::string &tier)
{
  Json params = {{"id", id}, {"name", name}, {"base_url", base_url}, {"models", models}};
  if (!location.empty()) { params["location"] = location; }
  if (!tier.empty()) { params["tier"] = tier; }
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
