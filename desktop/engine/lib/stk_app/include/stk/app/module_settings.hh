/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <optional>
#include <string>

namespace stk::app {
class AppStore;

/** Optional software modules of this computer (modules.*, docs/design/multiscale-engines.md): simulation engines
 * (LAMMPS, ABACUS) and modeling tools. Each is detected where it is already installed and used as it is; a missing one
 * is installed by the service from conda-forge after the person asks (network setting must allow the internet).
 * Read again after modules.progress or an own change; replies of a replaced bridge are ignored. */
class ModuleSettings {
 public:
  explicit ModuleSettings(AppStore &store);
  ~ModuleSettings();
  ModuleSettings(const ModuleSettings &) = delete;
  ModuleSettings &operator=(const ModuleSettings &) = delete;

  /** Follow the bridge and read when due (cheap to call every frame). */
  void sync();
  /** The service lists modules (modules.list). */
  bool supported() const;
  /** The service installs and removes them (desktop-only methods). */
  bool installable() const;
  bool loaded() const { return loaded_; }
  bool busy() const { return read_.has_value() || write_.has_value(); }
  /** A search of this computer is running (it may take a while; installing and cancelling still work). */
  bool detecting() const { return detect_.has_value(); }
  /** {root, platform, modules: [...]} or null until read. */
  const io::Json &listing() const { return listing_; }
  const std::string &error() const { return error_; }
  uint64_t version() const { return version_; }
  /** Look again (installs nothing). Done once by itself when this computer was never searched. */
  bool detect();
  /** ``action``: install, cancel or remove. */
  bool act(const std::string &action, const std::string &id);

 private:
  void reset();
  bool call(const std::string &method, io::Json params, std::optional<bridge::Future<io::Json>> &slot);

  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle listener_;
  std::string session_, error_;
  uint64_t epoch_ = 0, version_ = 0;
  bool stale_ = true, loaded_ = false, searched_ = false;
  io::Json listing_;
  std::optional<bridge::Future<io::Json>> read_, write_, detect_;
};
}  // namespace stk::app
