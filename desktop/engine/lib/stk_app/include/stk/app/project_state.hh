/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"

namespace stk::app {

class AppStore;

/** Shared table data. Views select by UUID, never by the sorted display row. */
struct ProjectField {
  std::string id, name, type, unit;
};
struct ProjectRecord {
  std::string id;
  io::Json values;
  io::Json definitions = io::Json::object();
  io::Json evaluations = io::Json::object();
};
struct ProjectTable {
  std::string id, name;
  std::vector<ProjectField> fields;
  std::vector<ProjectRecord> records;

  static ProjectTable from_json(const io::Json &value);
  const io::Json *cell(int row, int column) const;
  const io::Json *definition(int row, int column) const;
  const io::Json *evaluation(int row, int column) const;
  std::string text(int row, int column) const;
};

/** Parse a literal editor value without lossy double conversion of int64 values. Text stays raw;
 * other types use JSON syntax. Explicit null is allowed for every field (via the UI's null action).
 * On failure returns nullopt and a catalog key, leaving the persisted cell untouched. */
std::optional<io::Json> project_literal(std::string_view type, std::string_view text, std::string &error_key);

/** Main-thread project controller shared by editors. Bridge callbacks must use the UI executor.
 * All edits use project.apply; snapshots are replaced together. Stale callbacks are discarded after
 * a switch, close or bridge restart. Restart reopens by path/UUID but never replays a mutation. */
class ProjectState {
 public:
  explicit ProjectState(AppStore &store);
  ~ProjectState();
  ProjectState(const ProjectState &) = delete;
  ProjectState &operator=(const ProjectState &) = delete;

  void sync();
  void attach(bridge::Client *client);
  bool ready() const;
  bool busy() const { return busy_ || fetching_; }
  bool loaded() const { return project_.has_value() && snapshot_ready_; }
  const std::optional<bridge::ProjectInfo> &project() const { return project_; }
  const std::vector<ProjectTable> &tables() const { return tables_; }
  const std::string &error() const { return error_; }
  const std::string &notice() const { return notice_; }
  uint64_t version() const { return version_; }

  bool create(const std::string &directory, const std::string &name);
  bool open(const std::string &directory,
            std::function<void(bridge::Result<bridge::ProjectInfo>)> complete = {});
  bool close(std::function<void(bridge::Result<bool>)> complete = {});
  void refresh();
  bool apply(io::Json commands, std::optional<int64_t> expected_revision = std::nullopt);
  bool backup();
  bool upgrade();
  bool undo();
  bool redo();
  bool can_undo() const { return loaded() && undo_revision_ >= 0; }
  bool can_redo() const { return loaded() && redo_revision_ >= 0; }
  const io::Json &file_index() const { return file_index_; }
  bool selected_file() const;
  bool index_files(const std::vector<std::string> &paths);
  bool refresh_file();
  bool open_file(bool vscode);
  bool open_folder(bool vscode);
  bool capture_file();
  bool load_input_snapshots();
  bool verify_input_snapshot(const std::string &id);
  const io::Json &input_snapshots() const { return input_snapshots_; }
  const io::Json &input_verification() const { return input_verification_; }
  std::function<bool(const std::string &, std::string *)> open_external, open_vscode;
  const ProjectTable *table() const;
  const std::string &table_id() const { return table_id_; }
  const std::string &record_id() const { return record_id_; }
  void select_table(std::string id);
  void select_record(std::string id);
  int selected_record() const;

 private:
  template<class T, class F> void on(bridge::Future<T> future, F fn);
  bool start_open(const std::string &directory, const std::string &name, bool create, std::string expected_id = {},
                  std::function<void(bridge::Result<bridge::ProjectInfo>)> complete = {});
  void on_state(bridge::BridgeState state);
  void changed();
  void fail(const bridge::Error &error);
  void clear();
  void validate_selection();
  bool restore_edit(bool redo);
  bool edit_files(const std::vector<std::string> &items, bool index);

  AppStore &store_;
  bridge::Client *client_ = nullptr;
  bridge::BridgeState bridge_state_ = bridge::BridgeState::Stopped;
  bridge::ListenerHandle state_listener_, changed_listener_, closed_listener_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0;
  bool busy_ = false, fetching_ = false, snapshot_ready_ = false;
  int64_t dirty_revision_ = -1;
  int64_t undo_revision_ = -1, redo_revision_ = -1;
  std::optional<bridge::ProjectInfo> project_;
  std::vector<ProjectTable> tables_;
  io::Json file_index_ = io::Json::object();
  io::Json input_snapshots_ = io::Json::array(), input_verification_ = io::Json::object();
  std::string table_id_, record_id_, error_, notice_;
};

}  // namespace stk::app
