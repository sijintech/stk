/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/module_settings.hh"

#include "stk/app/app_store.hh"

namespace stk::app {
using io::Json;

ModuleSettings::ModuleSettings(AppStore &store) : store_(store) {}

ModuleSettings::~ModuleSettings()
{
  *alive_ = false;
  if (read_) { read_->cancel(); }
  if (write_) { write_->cancel(); }
  if (detect_) { detect_->cancel(); }
}

void ModuleSettings::reset()
{
  ++epoch_; ++version_;
  listing_ = Json(); stale_ = true; loaded_ = false; searched_ = false; error_.clear();
  for (auto *future : {&read_, &write_, &detect_}) {
    auto old = std::move(*future); future->reset();
    if (old) { old->cancel(); }
  }
}

bool ModuleSettings::supported() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return hello && hello->has_method("modules.list") && hello->has_method("modules.detect");
}

bool ModuleSettings::installable() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return supported() && hello->has_method("modules.install") && hello->has_method("modules.cancel") &&
         hello->has_method("modules.remove");
}

void ModuleSettings::sync()
{
  auto *client = store_.bridge();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_) {
    if (client != client_) {
      listener_ = {};
      const std::weak_ptr<bool> weak = alive_;
      if (client) {
        listener_ = client->on_event("modules.progress", [this, weak](const auto &, const Json &) {
          if (const auto alive = weak.lock(); alive && *alive) { stale_ = true; store_.changed(); }
        });
      }
    }
    client_ = client; session_ = session;
    reset();
  }
  if (stale_ && supported() && !read_) { call("modules.list", Json::object(), read_); }
  // Never searched (a fresh computer): look once by itself, so "not found" is never said before looking.
  if (loaded_ && !searched_ && !detect_ && listing_.value("detected_at", Json()).is_null()) {
    searched_ = true;
    call("modules.detect", Json::object(), detect_);
  }
}

bool ModuleSettings::call(const std::string &method, Json params, std::optional<bridge::Future<Json>> &slot)
{
  if (!client_ || slot) { return false; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  const bool read = &slot == &read_;
  if (read) { stale_ = false; }
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  slot = client_->call(method, std::move(params), options);
  slot->then([this, weak, epoch, read, &slot](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive || epoch != epoch_) { return; }
    slot.reset();
    if (!result) {
      error_ = result.error().message;
      if (!read && store_.toast) { store_.toast(error_, ui::ToastKind::Warning); }
      if (!read) { stale_ = true; }  // what the service now says, whatever the request did
    }
    else {
      error_.clear();
      if (result.value().contains("modules")) { listing_ = result.value(); loaded_ = true; }
      else { stale_ = true; }  // a job: read the listing again
    }
    ++version_;
    store_.changed();
  });
  store_.changed();
  return true;
}

bool ModuleSettings::detect()
{
  sync();
  searched_ = true;
  return supported() && call("modules.detect", Json::object(), detect_);
}

bool ModuleSettings::act(const std::string &action, const std::string &id)
{
  sync();
  if (!installable() || (action != "install" && action != "cancel" && action != "remove")) { return false; }
  return call("modules." + action, {{"id", id}}, write_);
}
}  // namespace stk::app
