/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace stk::app {
class AppStore;

/** Owner-only federation UI. Sync/detach/reopen never dispatch an RPC or execute a mutation. */
class FederationState {
 public:
  struct Pending;
  struct View {
    ~View();
    io::Json connections = io::Json::array(), table, plan, plans = io::Json::array();
    io::Json info, registration, grants, audit, candidate, evaluation, models, operation, rejection;
    io::Json local_operations = io::Json::array();
    std::string connection, table_id, plan_id, operation_id, operation_method, error;
    // The bridge binds private registration and reopened intents to their complete original request.
    // Visible requests additionally retain the Python-compatible, type-preserving request digest.
    std::string operation_connection, operation_plan_id, operation_request_sha256;
    std::string source_handle, source_project;
    int64_t source_revision = -1, row_offset = 0, row_total = 0;
    uint64_t version = 0, draft_epoch = 0, selection_epoch = 0, lifetime_epoch = 0;
    bool uncertain = false, plan_uncertain = false;
    bool busy() const { return pending.contains("write") || pending.contains("prepare"); }
    bool reading() const { return !pending.empty(); }
   private:
    friend class FederationState;
    std::map<std::string, std::shared_ptr<Pending>> pending;
  };
  using ViewPtr = std::shared_ptr<View>;
  explicit FederationState(AppStore &store);
  ~FederationState();
  ViewPtr new_view();
  void sync(const ViewPtr &);
  bool supported() const;
  void detach(const ViewPtr &);
  void invalidate_draft(const ViewPtr &, bool data_changed = false);
  bool source_current(const ViewPtr &) const;
  bool set_connection(const ViewPtr &, const std::string &);
  bool load_connections(const ViewPtr &);
  bool load_rows(const ViewPtr &, const std::string &table_id, int64_t offset = 0);
  bool prepare(const ViewPtr &, io::Json params);
  bool load_plan(const ViewPtr &, const std::string &plan_id);
  bool load_plans(const ViewPtr &);
  bool register_plan(const ViewPtr &);
  bool read(const ViewPtr &, const std::string &method, io::Json params = io::Json::object());
  bool write(const ViewPtr &, const std::string &method, io::Json request);
  bool check_operation(const ViewPtr &);
  bool recover_operation(const ViewPtr &);
  bool select_operation(const ViewPtr &, const io::Json &);
  /** UUIDs are operation identities only, never authentication material. */
  static std::string new_uuid();
  static bool runtime_connection(std::string_view);
  static bool evaluation_passed(const io::Json &);

 private:
  using Apply = std::function<void(View &, const io::Json &)>;
  bool call(const ViewPtr &, const std::string &slot, const std::string &method, io::Json,
            Apply, bool draft = false);
  bool owner_write(const ViewPtr &, const std::string &, io::Json, const std::string &rpc = {});
  void accept_operation(View &, const io::Json &, bool queried = false);
  bool accept_rejection(View &, const io::Json &, bool historical = false);
  void follow_source();
  AppStore &store_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string session_;
  uint64_t epoch_ = 1, store_bridge_epoch_ = 0, project_scope_epoch_ = 0;
  std::vector<std::weak_ptr<View>> views_;
};
}  // namespace stk::app
