/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

#include <array>

namespace stk::app {
class AppStore;
class ProjectState;
struct ProjectTable;

/** A source token for a read or a deferred UI action. An opened handle is never persisted. */
struct TableWorkbenchScope {
  std::string project_id, handle, table_id;
  int64_t revision = -1;
  uint64_t epoch = 0;
};

/** Per-editor table read controller. Callbacks run on the bridge's UI executor. All reads are
 * revision checked and scoped to the current project, selected table and bridge session. A
 * reconnect cancels pending reads and clears results; it never replays a write. Paste planning
 * only returns commands: the caller explicitly applies them through ProjectState at base_revision.
 */
class TableWorkbenchState {
 public:
  using Complete = std::function<void(const io::Json &)>;

  /** owner_valid represents permanent owner lifetime, never temporary tab visibility. */
  explicit TableWorkbenchState(AppStore &store, std::function<bool()> owner_valid = {});
  ~TableWorkbenchState();
  TableWorkbenchState(const TableWorkbenchState &) = delete;
  TableWorkbenchState &operator=(const TableWorkbenchState &) = delete;

  void sync();
  bool supported() const;
  bool supports(std::string_view method) const;
  bool busy() const;
  bool pending(std::string_view method) const;
  const std::string &error() const { return error_; }
  const std::string &error_method() const { return error_method_; }
  void clear_error();
  uint64_t version() const { return version_; }
  TableWorkbenchScope scope() const;
  /** Synchronizes first, so a queued UI action cannot use a result after a source switch. */
  bool current(const TableWorkbenchScope &source);
  /** Drop outstanding callbacks and cached results without sending any project mutation. */
  void cancel();

  const io::Json &views() const;
  const io::Json &selected_view() const;
  const io::Json &query_result() const;
  /** The current query's complete records in display order, independent of the shared snapshot.
   * Null while loading or after its project, revision, table or bridge session changes. */
  const ProjectTable *query_table() const;
  /** Select a record from this editor's current verified query without another read. */
  bool select_record(const std::string &id);
  const io::Json &candidates() const;
  const io::Json &resolved_object() const;
  const io::Json &csv_preview() const;
  const io::Json &io_preview() const;
  const io::Json &attachment_preview() const;

  bool load_views(Complete complete = {});
  bool load_view(const std::string &id, Complete complete = {});
  /** Request keys: view_id OR definition, offset, limit. The current table is injected. */
  bool query(io::Json request = io::Json::object(), Complete complete = {});
  /** Request keys: record_ids, field_ids, text, optional delimiter/append_rows. No writes. */
  bool plan_paste(io::Json request, Complete complete);
  /** Request keys: kind, optional target table_id (record candidates), offset, limit. */
  bool object_candidates(io::Json request, Complete complete = {});
  /** Request keys: reference. Resolution is metadata-only and never opens or executes it. */
  bool resolve_object(io::Json request, Complete complete = {});
  /** Only the documented project.table read/plan methods are accepted. The source handle
   * and revision are injected; supplied reserved keys must already match the current source.
   * A new call of the same method cancels the older callback, independently of other methods. */
  bool scoped_call(const std::string &method, io::Json request, Complete complete = {});

 private:
  struct Request {
    std::optional<bridge::Future<io::Json>> future;
    io::Json result;
    uint64_t generation = 0;
  };
  static int method_index(std::string_view method);
  void reset();
  void changed();
  bool fail(const std::string &method, const std::string &message);
  bool valid_result(int index, const io::Json &result, const io::Json &request) const;

  AppStore &store_;
  ProjectState &project_;
  std::function<bool()> owner_valid_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bridge::Client *client_ = nullptr;
  std::string project_id_, handle_, table_id_, session_, error_, error_method_;
  int64_t revision_ = -1;
  uint64_t epoch_ = 0, version_ = 0;
  std::array<Request, 9> requests_;
  std::unique_ptr<ProjectTable> query_table_;
};
}  // namespace stk::app
