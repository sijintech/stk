/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include "stk/app/project_review.hh"

namespace stk::app {

class AppStore;
class ProjectDiscussion;

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
  int compare(int row_a, int row_b, int column) const;
};

/** Parse a literal editor value without lossy double conversion of int64 values. Text stays raw;
 * other types use JSON syntax. Explicit null is allowed for every field (via the UI's null action).
 * On failure returns nullopt and a catalog key, leaving the persisted cell untouched. */
std::optional<io::Json> project_literal(std::string_view type, std::string_view text, std::string &error_key);

/** One parameter-sweep axis typed into the project editor, without its field_id. A range takes
 * `start`, `stop` and a point count (integer and number fields only); a list takes comma-separated
 * values parsed like #project_literal (text items are trimmed and cannot contain commas). Null and
 * empty items are refused. `values` is the axis' value count. On failure returns nullopt and a
 * catalog key; suan.project.sweep checks the axis again when it plans the rows. */
struct ProjectSweepAxis {
  io::Json axis;
  size_t values = 0;
};
std::optional<ProjectSweepAxis> project_sweep_axis(std::string_view type, bool range, std::string_view start,
                                                   std::string_view stop, std::string_view count,
                                                   std::string_view list, std::string &error_key);

/** Main-thread project controller shared by editors. Bridge callbacks must use the UI executor.
 * All edits use revisioned project commands; snapshots are replaced together. Stale callbacks are discarded after
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

  void load_recent();
  bool forget_recent(const std::string &directory);
  bool open_recent(const io::Json &entry);
  const io::Json &recent() const { return recent_; }
  const std::string &recent_error() const { return recent_error_; }
  bool recent_loading() const { return recent_loading_; }
  bool recent_loaded() const { return recent_loaded_; }
  bool create(const std::string &directory, const std::string &name);
  bool open(const std::string &directory,
            std::function<void(bridge::Result<bridge::ProjectInfo>)> complete = {});
  bool close(std::function<void(bridge::Result<bool>)> complete = {});
  void refresh();
  bool apply(io::Json commands, std::optional<int64_t> expected_revision = std::nullopt);
  /** Whether the Python service builds the offline example project (demo.create). */
  bool supports_demo() const;
  /** Build the example project in a new folder under ~/STK Projects (suan.workflows.demo: synthetic
   * data, nothing contacts a Runtime, server or model) and open it. Only while no project is open. */
  bool create_demo();
  /** Whether the bridge plans parameter sweeps (project.sweep.plan). */
  bool supports_sweep() const;
  /** Plan rows from `axes` (suan.project.sweep) and apply them in one edit at the revision shown now.
   * A plan made against another revision or project is dropped with an error, never retargeted.
   * The first new row is selected. An empty `base_record_id` copies no other cells. */
  bool sweep(const std::string &table_id, io::Json axes, const std::string &base_record_id, const std::string &mode);
  const std::string &review_source() const { return review_source_; }
  const std::string &review_error() const { return review_error_; }
  const std::shared_ptr<const ProjectReview> &review() const { return review_; }
  uint64_t review_generation() const { return review_generation_; }
  void set_review_source(std::string source);
  bool preview_supported() const;
  bool preview();
  /** Accept an external draft only for the current handle/revision and an empty review. */
  bridge::Result<io::Json> request_review(const std::string &handle, int64_t expected_revision,
                                        const io::Json &commands);
  /** Adopt a pending saved draft into an empty review without previewing or applying it.
   * The caller must protect active text input and deferred UI navigation separately. */
  bridge::Result<io::Json> request_saved_review(const std::string &handle, int64_t expected_revision,
                                              const io::Json &draft);
  /** Shared selection, pinned to the currently opened handle. Does not focus or open an editor. */
  bridge::Result<io::Json> request_selection(const std::string &handle) const;
  bridge::Result<io::Json> request_select(const std::string &handle, int64_t expected_revision,
                                        const std::string &table_id, const std::string &record_id);
  bool can_apply_review() const;
  bool apply_review();
  void discard_review();
  bool drafts_supported() const;
  bool load_drafts(int64_t offset = 0, bool preserve_error = false);
  bool drafts_loaded() const { return drafts_loaded_; }
  const io::Json &drafts() const { return drafts_; }
  const io::Json &saved_review() const { return saved_review_; }
  const std::string &drafts_error() const { return drafts_error_; }
  int64_t drafts_offset() const { return drafts_offset_; }
  int64_t drafts_next_offset() const { return drafts_next_offset_; }
  bool save_review(const std::string &title);
  bool load_draft(const std::string &id);
  bool discard_saved_draft(const std::string &id);
  bool copy_saved_review();
  ProjectDiscussion &discussion() { return *discussion_; }
  bool import_csv(const std::string &source, const std::string &name, const io::Json &types,
                  const io::Json &units, const std::string &delimiter);
  bool export_csv(const std::string &destination, const std::string &delimiter);
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
  bool view_file(const std::string &preset);
  bool open_folder(bool vscode);
  bool capture_file();
  bool load_input_snapshots();
  bool verify_input_snapshot(const std::string &id);
  const io::Json &input_snapshots() const { return input_snapshots_; }
  const io::Json &input_verification() const { return input_verification_; }
  bool load_runs(int64_t offset = 0);
  bool select_run(const std::string &id);
  bool submit_run(bool allow_stale = false);
  bool refresh_run();
  bool cancel_run();
  const io::Json &runs() const { return runs_; }
  const io::Json &run() const { return run_; }
  const std::string &run_id() const { return run_id_; }
  int64_t runs_offset() const { return runs_offset_; }
  int64_t runs_next_offset() const { return runs_next_offset_; }
  int selected_run() const;
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
  void clear_review();
  void clear_drafts();
  void validate_selection();
  bool restore_edit(bool redo);
  bool run_operation(const std::string &action, const std::string &id, bool allow_stale = false);
  void clear_runs();
  bool edit_files(const std::vector<std::string> &items, bool index);

  AppStore &store_;
  std::unique_ptr<ProjectDiscussion> discussion_;
  bridge::Client *client_ = nullptr;
  bridge::BridgeState bridge_state_ = bridge::BridgeState::Stopped;
  bridge::ListenerHandle state_listener_, changed_listener_, closed_listener_, runs_listener_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0, recent_epoch_ = 0;
  io::Json recent_ = io::Json::array();
  std::string recent_error_;
  bool recent_loaded_ = false, recent_loading_ = false, recent_dirty_ = false;
  bool busy_ = false, fetching_ = false, snapshot_ready_ = false;
  int64_t dirty_revision_ = -1;
  int64_t undo_revision_ = -1, redo_revision_ = -1;
  std::optional<bridge::ProjectInfo> project_;
  std::vector<ProjectTable> tables_;
  std::shared_ptr<const ProjectReview> review_;
  std::string review_source_ = "[]", review_error_;
  uint64_t review_generation_ = 0;
  io::Json drafts_ = io::Json::array(), saved_review_ = io::Json::object(), save_request_ = io::Json::object();
  std::string drafts_error_;
  bool drafts_loaded_ = false;
  int64_t drafts_offset_ = 0, drafts_next_offset_ = -1;
  io::Json file_index_ = io::Json::object();
  io::Json input_snapshots_ = io::Json::array(), input_verification_ = io::Json::object();
  io::Json runs_ = io::Json::array(), run_ = io::Json::object();
  std::string run_id_;
  int64_t runs_offset_ = 0, runs_next_offset_ = -1;
  bool runs_loaded_ = false, runs_dirty_ = false;
  std::string table_id_, record_id_, error_, notice_;
};

}  // namespace stk::app
