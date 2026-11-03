/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;

/** Explicit desktop peer actions. Sync, detach and restoration never dispatch RPCs. */
class PeerState {
 public:
  struct Pending;
  struct Expected {
    std::string action, request_sha256, bridge_session;
    std::string source_handle, source_project;
    int64_t source_revision = -1;
    uint64_t prepare_epoch = 0, bridge_epoch = 0, draft_epoch = 0, connection_epoch = 0;
  };
  struct View {
    ~View();
    std::map<std::string, io::Json> values;
    std::map<std::string, Expected> originals;
    io::Json operation;
    std::string connection, operation_id, error;
    std::string source_handle, source_project, prepared_operation_id;
    int64_t source_revision = -1;
    uint64_t draft_epoch = 0, prepare_epoch = 0, connection_epoch = 0, selection_epoch = 0, lifetime_epoch = 0, version = 0;
    double follow_until = 0, next_poll = 0;
    bool uncertain = false;
    bool busy() const { return pending.contains("write"); }
    bool reading() const { return !pending.empty(); }
   private:
    friend class PeerState;
    std::map<std::string, std::shared_ptr<Pending>> pending;
    std::map<std::string, std::string> latest_operations;
  };
  using ViewPtr = std::shared_ptr<View>;
  explicit PeerState(AppStore &);
  ~PeerState();
  ViewPtr new_view();
  void sync(const ViewPtr &);
  bool supported() const;
  void detach(const ViewPtr &);
  void invalidate_draft(const ViewPtr &, bool source = false);
  bool set_connection(const ViewPtr &, const std::string &);
  bool source_current(const ViewPtr &) const;
  bool read(const ViewPtr &, const std::string &method, io::Json params = io::Json::object());
  bool read_source(const ViewPtr &, const std::string &method, io::Json params = io::Json::object());
  bool act(const ViewPtr &, const std::string &action, io::Json params);
  bool check_operation(const ViewPtr &);
  bool select_operation(const ViewPtr &, const io::Json &);
  void follow(const ViewPtr &);
  void pump(const ViewPtr &);
  static std::string new_uuid();
  static std::string request_sha256(const std::string &action, io::Json params);
  static bool operation_matches(const io::Json &, const std::string &id, const Expected * = nullptr);

 private:
  using Apply = std::function<void(View &, const io::Json &)>;
  bool call(const ViewPtr &, const std::string &slot, const std::string &rpc, io::Json, Apply,
            bool draft = false, bool source = false);
  void accept_operation(View &, const io::Json &);
  void follow_source();
  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string session_;
  uint64_t epoch_ = 1, bridge_epoch_ = 0, project_epoch_ = 0;
  std::vector<std::weak_ptr<View>> views_;
};
}  // namespace stk::app
