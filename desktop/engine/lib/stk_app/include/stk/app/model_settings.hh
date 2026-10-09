/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <optional>
#include <string>
#include <unordered_map>

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

  /** ``tier`` (tiny, small, medium, large; empty: judged by location) tells the automatic choice how capable it is. */
  bool add_endpoint(const std::string &id, const std::string &name, const std::string &base_url,
                    const std::vector<std::string> &models, const std::string &location, const std::string &tier = "");
  bool remove_endpoint(const std::string &id);
  /** The key goes to the local service only; it is never kept here. */
  bool set_key(const std::string &id, std::string key, bool remember);
  bool clear_key(const std::string &id);
  bool set_network(const std::string &network);

  /* ---- Local models (models.local.*, S1c) ---- */

  /** The service installs and serves local models. */
  bool local_supported() const;
  /** Installed entries, their servers and running installations (null until read). */
  const io::Json &local() const { return local_; }
  /** Hardware and catalog entries with fit and recommendation (null until loaded on demand). */
  const io::Json &recommendations() const { return recommendations_; }
  /** The last hardware read failed: not read again until asked (``load_recommendations``). */
  bool recommendations_failed() const { return recommendations_failed_; }
  bool load_recommendations();
  /** Live progress of an installation or server start, by catalog entry (from models.local.progress). */
  const io::Json *progress(const std::string &entry) const;
  bool local_action(const std::string &action, const std::string &entry);
  bool import_local(const std::string &entry, const std::string &path);

  /* ---- Automatic model choice (models.route, S1d) ---- */

  /** The service ranks models for a question (models.route). */
  bool route_supported() const;
  /** The ranked candidates for ``key`` (the caller's description of what was asked: project, context, task and the
   * versions it depends on), ``{"error": ...}`` when the service could not rank them, or null while it is read.
   * Each key is read once; a changed key is read again. */
  const io::Json &route(const std::string &key, const std::string &handle, const std::string &context_id,
                        const std::string &prompt_version);

 private:
  void reset();
  bool read();
  bool write(const std::string &method, io::Json params);

  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle listener_;
  std::string session_, error_, network_;
  io::Json endpoints_ = io::Json::array(), local_, recommendations_, progress_ = io::Json::object();
  bridge::ListenerHandle progress_listener_;
  std::optional<bridge::Future<io::Json>> local_read_, recommend_read_, route_read_;
  std::string route_reading_;
  std::unordered_map<std::string, io::Json> routes_;
  io::Json null_;
  bool local_stale_ = true, recommendations_failed_ = false;
  bool read_local();
  uint64_t epoch_ = 0, version_ = 0;
  bool stale_ = true, loaded_ = false;
  std::optional<bridge::Future<io::Json>> read_, write_;
};
}  // namespace stk::app
