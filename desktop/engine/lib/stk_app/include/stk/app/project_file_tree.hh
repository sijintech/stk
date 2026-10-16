/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"
#include <map>
#include <set>

namespace stk::app {
class AppStore;
class ProjectState;

/** Per-editor, asynchronous directory browser. It never changes the shared table selection. */
class ProjectFileTree {
 public:
  explicit ProjectFileTree(AppStore &store, std::function<bool()> owner_valid = {});
  ~ProjectFileTree();
  io::Json save_workspace_state() const;
  static bool check_workspace_state(const io::Json &value);
  bool load_workspace_state(const io::Json &value);
  void sync();
  bool supported() const;
  bool busy() const { return future_.has_value(); }
  bool loaded() const { return pages_.count("") != 0; }
  bool refresh();
  bool toggle(const std::string &path);
  bool more(const std::string &path);
  bool expanded(const std::string &path) const { return expanded_.count(path) != 0; }
  const std::map<std::string, io::Json> &pages() const { return pages_; }
  const io::Json &selected() const { return selected_; }
  void select(io::Json item);
  bool select_record(const std::string &id);
  bool resolve(std::function<void(const std::string &)> complete);
  const std::string &error() const { return error_; }
  uint64_t version() const { return version_; }

 private:
  bool load(const std::string &path, int offset);
  void clear();
  void changed();
  AppStore &store_;
  ProjectState &project_;
  std::function<bool()> owner_valid_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string handle_, session_, error_, workspace_project_;
  int64_t revision_ = -1;
  uint64_t epoch_ = 0, version_ = 0;
  std::map<std::string, io::Json> pages_;
  std::set<std::string> expanded_{""};
  io::Json selected_, workspace_pending_, workspace_selection_;
  std::optional<bridge::Future<io::Json>> future_;
};
}  // namespace stk::app
