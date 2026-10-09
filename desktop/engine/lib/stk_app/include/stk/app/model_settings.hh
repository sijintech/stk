/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <optional>
#include <string>

namespace stk::app {
class AppStore;

/** Model endpoints of this computer and the network setting (models.*, docs/design/model-gateway.md):
 * the built-in Alibaba Token Plan endpoint and added OpenAI-compatible endpoints, each with its location
 * (local / internal / external), models, key presence (never the key) and whether the network setting allows it.
 * Read again after models.changed or an own change; replies of a replaced bridge are ignored. */
class ModelSettings {
 public:
  explicit ModelSettings(AppStore &store);
  ~ModelSettings();
  ModelSettings(const ModelSettings &) = delete;
  ModelSettings &operator=(const ModelSettings &) = delete;

  /** Follow the bridge and read when due (cheap to call every frame). */
  void sync();
  /** The service offers model endpoints (models.list). */
  bool supported() const;
  /** Changes may be made from here (the service offers models.endpoints.add and the others). */
  bool editable() const;
  bool loaded() const { return loaded_; }
  bool busy() const { return read_.has_value() || write_.has_value(); }
  const io::Json &endpoints() const { return endpoints_; }
  /** "offline", "organization" or "internet" (empty until read). */
  const std::string &network() const { return network_; }
  /** The endpoint with this ID or adapter identity, or nullptr. */
  const io::Json *endpoint(const std::string &id) const;
  const io::Json *by_adapter(const std::string &adapter) const;
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }

  bool add_endpoint(const std::string &id, const std::string &name, const std::string &base_url,
                    const std::vector<std::string> &models, const std::string &location);
  bool remove_endpoint(const std::string &id);
  /** The key goes to the local service only; it is never kept here. */
  bool set_key(const std::string &id, std::string key, bool remember);
  bool clear_key(const std::string &id);
  bool set_network(const std::string &network);

 private:
  void reset();
  bool read();
  bool write(const std::string &method, io::Json params);

  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle listener_;
  std::string session_, error_, network_;
  io::Json endpoints_ = io::Json::array();
  uint64_t epoch_ = 0, version_ = 0;
  bool stale_ = true, loaded_ = false;
  std::optional<bridge::Future<io::Json>> read_, write_;
};
}  // namespace stk::app
