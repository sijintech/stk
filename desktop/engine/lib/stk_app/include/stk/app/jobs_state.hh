/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * JobsState: the model and controller behind the Jobs, Transfers, Logs and Bridge-log editors
 * (the successor of the legacy PyQt Tasks tab, suan/gui/Tab/runtime_tab.py). One instance per
 * AppStore (AppStore::jobs()); every editor showing jobs reads it while building its UI and calls
 * its operations from widget callbacks. Main thread only: bridge results arrive through the client's
 * executor (the main loop), and every callback is dropped once this object is gone or once the
 * user switched connection / workspace / task in the meantime (the legacy tab's "epoch").
 *
 * Data flow (docs/specs/stk-desktop-bridge-v1.md):
 *   connections.list / check / add_runtime / pair_hub / remove / local / local_start
 *   hub.devices (nodes) / templates / policy / actions / action / review / subscribe
 *   workspace.list / create / files
 *   upload.start / download.start / transfer.* + transfer.updated   (Transfers editor)
 *   task.submit (idempotency key, retry policy) / task.cancel / task.artifacts / task.get
 *   watch (task snapshots are state, not deltas: each replaces the list)
 *   logs.subscribe (stdout + stderr, UTF-8 safe) / events.subscribe (monitoring summary)
 *
 * Closing the app never stops jobs: nothing here cancels a task on detach or destruction
 * (subscriptions are dropped; the bridge pauses transfers at EOF and resumes them next time).
 */
#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "stk/app/jobs_spec.hh"
#include "stk/bridge/client.hh"
#include "stk/ui/log_buffer.hh"
#include "stk/ui/ui.hh"

namespace stk::io {
struct Image;
}
namespace stk::platform {
class FileDialog;
}

namespace stk::app {

class AppStore;

/** A Runtime task record (TaskRecord, or a hub node snapshot entry without its spec). */
struct TaskRow {
  std::string id, name, state, backend, reason, workspace_id, created_at, updated_at;
  bool cancel_requested = false;
  std::optional<int64_t> exit_code;
  Json raw;

  static TaskRow from_json(const Json &task);
  /** succeeded / failed / cancelled */
  bool terminal() const;
  /** Cancel requested and not finished yet (shown as "cancelling"). */
  bool cancelling() const
  {
    return cancel_requested && !terminal();
  }
  /** The name, else the first 12 characters of the id (the legacy table's first column). */
  std::string label() const;
};

/** Health of a connection (connections.check; the local Runtime also reports its supervisor). */
enum class Health : uint8_t { Unknown, Checking, Online, Degraded, Offline };

struct ConnectionRow {
  bridge::ConnectionInfo info;
  Health health = Health::Unknown;
  /** Why it is degraded or offline (the bridge's message), or the node count of a hub. */
  std::string detail;
};

struct NodeRow {
  std::string id, name;
  bool online = false;
};

struct WorkspaceRow {
  std::string id, name, created_at;
};

/** A summary of a task's monitoring events (docs/specs/stk-events-v1.md), folded incrementally. */
struct EventsSummary {
  int64_t count = 0, invalid = 0, frames = 0, checkpoints = 0, warnings = 0, errors = 0;
  std::string app;                   /**< run.started app */
  std::optional<double> fraction;    /**< progress fraction (or completed / total steps) */
  int64_t step = -1, total_steps = -1;
  std::string phase;                 /**< progress phase or the latest run.phase */
  std::string last_message;          /**< latest message text ("warning: ...") */
  std::map<std::string, std::string> metrics; /**< latest value per metric name */
  std::string completed;             /**< run.completed status */
  std::string verification;          /**< verification status */
  bool ended = false;                /**< events.end received */
  bool unsupported = false;          /**< the Runtime publishes no events */

  void add(const Json &event);
};

/** An artifact of the selected task and its download. */
struct ArtifactRow {
  bridge::FileEntry file;
  std::string transfer_id; /**< Its download (empty before one started). */
  std::string local;       /**< Where the verified file is. */
  enum class Verify : uint8_t { None, Pending, Ok, Mismatch } verify = Verify::None;
};

/** A decoded PNG shown in the image widget. */
struct Preview {
  std::string path;
  int width = 0, height = 0;
  uint64_t texture = 0; /**< 0 without a GPU (the editor shows the size instead). */
  std::string error;
};

enum class SubmitState : uint8_t {
  Idle,
  Sending,  /**< task.submit in flight */
  Waiting,  /**< an automatic retry is scheduled */
  Review,   /**< a hub action waits for review (the same key is re-sent after approval) */
  Done,     /**< the task exists (task_id) */
  Failed,   /**< "Retry last submission" re-sends the same key */
};

struct Submission {
  std::string key; /**< Idempotency key: one per submit, reused by every retry of it. */
  bridge::TaskSubmitParams params;
  std::string label; /**< Name or command, for messages. */
  SubmitState state = SubmitState::Idle;
  int attempts = 0;
  std::string task_id;
  std::optional<bridge::HubActionSummary> action;
  std::optional<bridge::Error> error;
};

/** A hub action waiting for review (hub.actions) and what this bridge knows about it. */
struct ReviewItem {
  bridge::HubActionSummary action;
  std::string kind;      /**< action kind (task.submit, workspace.import, graph.evaluate, ...) */
  Json request;          /**< the full request once inspected (hub.action) */
  bool inspected = false; /**< hub.action was read by the *current* bridge process */
  bool busy = false;
  bool reinspecting = false; /**< read again after review_not_inspected (keeps the message) */
  std::string message;   /**< the last outcome (refusal, error) */
};

/** Feedback line of the Jobs editor (the legacy tab's status label). */
struct JobsStatus {
  std::string text;
  ui::ToastKind kind = ui::ToastKind::Info;
};

class JobsState {
 public:
  explicit JobsState(AppStore &store);
  ~JobsState();
  JobsState(const JobsState &) = delete;
  JobsState &operator=(const JobsState &) = delete;

  /* ---- Bridge ---- */

  /** Uses `client` (null detaches: subscriptions and listeners are dropped, jobs keep running). */
  void attach(bridge::Client *client);
  bridge::Client *client() const
  {
    return client_;
  }
  /** Attached and the bridge said hello. */
  bool ready() const;
  /** Attaches AppStore::bridge() when it changed (editors call it while drawing). */
  void sync();

  /* ---- Hooks (set by the application; tests leave or fake them) ---- */

  /** Uploads an RGBA8 image as a GPU texture (0 on failure); unset = previews without pixels. */
  std::function<uint64_t(const io::Image &)> create_texture;
  std::function<void(uint64_t)> free_texture;
  /** Native file dialog (not owned); null = the editors' path field only. */
  platform::FileDialog *file_dialog = nullptr;
  /** Runs `fn` after `seconds` on the main loop (retry backoff); unset = at once. */
  std::function<void(double seconds, std::function<void()> fn)> schedule;
  /** Opens a local file with the system (default: stk::platform::open_with_system). */
  std::function<bool(const std::string &path, std::string *error)> open_external;

  /* ---- Feedback ---- */

  const JobsStatus &status() const
  {
    return status_;
  }
  void set_status(std::string text, ui::ToastKind kind = ui::ToastKind::Info);
  /** Bumped on every change (editors use it for table data versions). */
  uint64_t version() const
  {
    return version_;
  }

  /* ---- Connections ---- */

  const std::vector<ConnectionRow> &connections() const
  {
    return connections_;
  }
  const std::string &active_id() const
  {
    return active_;
  }
  const ConnectionRow *active() const;
  bool hub() const;
  void refresh_connections();
  /** Connects (health check, nodes / templates / policy for hubs, workspaces); "" disconnects. */
  void select_connection(const std::string &id);
  void check_connection(const std::string &id);
  /** The connection to pick once the list is known (saved with the layout). */
  void set_preferred(std::string connection, std::string node, std::string workspace);

  using Done = std::function<void(const std::optional<bridge::Error> &)>;
  void add_runtime(const bridge::AddRuntimeParams &params, Done done = {});
  void pair_hub(const bridge::PairHubParams &params, Done done = {});
  /** Forgets the connection (a Runtime profile is also gone from `suan connect`). */
  void remove_connection(const std::string &id, Done done = {});

  const std::optional<bridge::LocalRuntimeStatus> &local_status() const
  {
    return local_;
  }
  bool local_busy() const
  {
    return local_busy_;
  }
  void refresh_local();
  /** Starts the local Runtime's API and supervisor (connections.local_start). */
  void start_local();

  /* ---- Hub ---- */

  const std::vector<NodeRow> &nodes() const
  {
    return nodes_;
  }
  const std::string &node() const
  {
    return node_;
  }
  void select_node(const std::string &id);
  /** Template names (hub.templates). */
  const std::vector<std::string> &templates() const
  {
    return templates_;
  }
  const std::optional<bridge::HubPolicy> &policy() const
  {
    return policy_;
  }
  const std::vector<ReviewItem> &reviews() const
  {
    return reviews_;
  }
  void refresh_actions();
  /** Reads the full request (hub.action); required before approving. */
  void inspect(const std::string &action_id);
  void review(const std::string &action_id, bool approve);

  /* ---- Workspaces ---- */

  const std::vector<WorkspaceRow> &workspaces() const
  {
    return workspaces_;
  }
  const std::string &workspace() const
  {
    return workspace_;
  }
  void select_workspace(const std::string &id);
  void refresh_workspaces();
  void create_workspace(const std::string &name, Done done = {});
  /** Input files of the workspace (workspace.files). */
  const std::vector<bridge::FileEntry> &workspace_files() const
  {
    return files_;
  }
  void refresh_files();
  /** Downloads a workspace input file (verified) to `dest` (empty: the bridge's download dir)
   * and opens it (#open_local), as the legacy tab did. */
  void download_input(const std::string &path, const std::string &dest = {});

  /* ---- Uploads and transfers ---- */

  /** Uploads files / folders into the current workspace; without one they wait as pending. */
  void upload(const std::vector<std::string> &paths);
  /** A folder's contents go to the workspace root (the legacy Tasks tab's layout, `remote: "."`);
   * off: under the folder's name. */
  bool folder_into_root = true;
  const std::vector<std::string> &pending_uploads() const
  {
    return pending_;
  }
  void start_pending();
  void clear_pending();
  /** All transfers the bridge knows (newest first). */
  const std::vector<bridge::Transfer> &transfers() const
  {
    return transfers_;
  }
  const bridge::Transfer *transfer(const std::string &id) const;
  void refresh_transfers();
  void resume_transfer(const std::string &id);
  void cancel_transfer(const std::string &id);
  /** Uploads into the current workspace that have not completed (submitting waits for them). */
  int uploads_in_flight() const;

  /* ---- Submit ---- */

  SubmitForm &form()
  {
    return form_;
  }
  std::vector<FormIssue> validate() const;
  /** Validates and sends the form with a new idempotency key; false (status set) when invalid. */
  bool submit();
  /** Sends the last submission again with the same key. */
  void retry_submission();
  const std::optional<Submission> &submission() const
  {
    return submission_;
  }

  /* ---- Tasks ---- */

  const std::vector<TaskRow> &tasks() const
  {
    return tasks_;
  }
  /** Time of the last watch snapshot (0 before the first). */
  double snapshot_time() const
  {
    return snapshot_time_;
  }
  const std::string &selected() const
  {
    return selected_;
  }
  const TaskRow *selected_task() const;
  void select_task(const std::string &id);
  void cancel_task(const std::string &id);
  /** One task.list now (the watch keeps the list current by itself). */
  void refresh_tasks();

  /* ---- Task detail ---- */

  /** stdout + stderr (stderr lines prefixed "[stderr] "), and each stream alone. */
  ui::LogBuffer &log_all()
  {
    return log_all_;
  }
  ui::LogBuffer &log_stdout()
  {
    return log_out_;
  }
  ui::LogBuffer &log_stderr()
  {
    return log_err_;
  }
  bool logs_ended() const
  {
    return logs_ended_;
  }
  const EventsSummary &events() const
  {
    return events_;
  }
  const std::vector<ArtifactRow> &artifacts() const
  {
    return artifacts_;
  }
  void refresh_artifacts();
  /** Downloads (sha256-verified by the bridge, checked again here) to `dest` (absolute; empty:
   * the bridge's download directory, and the file is opened when verified: see #open_local).
   * PNGs are previewed when done. */
  void download_artifact(const std::string &path, const std::string &dest = {});
  const Preview &preview() const
  {
    return preview_;
  }
  /** Decodes a local PNG (stk_io) into the preview (a texture when create_texture is set). */
  void show_preview(const std::string &local_path);
  void clear_preview();
  /** Opens a downloaded file: PNG preview, .stkp / .vtk / result directories in the Viewer
   * (AppStore::request_open_result with local_paths), else the system's application. */
  void open_local(const std::string &local_path);
  /** Asks the Viewer to show the selected task (AppStore::request_open_result). */
  void open_in_viewer();

  /* ---- Model updates (bridge callbacks; public for tests and goldens) ---- */

  void apply_connections(std::vector<bridge::ConnectionInfo> list);
  void apply_workspaces(const Json &workspaces);
  void apply_snapshot(const Json &tasks, double time);
  void apply_transfer(const bridge::Transfer &transfer);
  void apply_actions(const Json &actions);
  void apply_nodes(const Json &devices);
  void apply_check(const bridge::ConnectionCheck &check);
  /** Artifacts of the selected task (downloads already known are kept). */
  void apply_artifacts(const std::vector<bridge::FileEntry> &files);

 private:
  struct Alive;
  template<class T, class F> void on(bridge::Future<T> future, F fn);
  void changed();
  void fail(const std::string &what, const bridge::Error &error);
  void on_state(bridge::BridgeState state);
  void on_ready(bool restarted);
  void connect_active();
  void rewatch();
  void resubscribe_detail();
  void send_submission();
  void submission_result(const bridge::Result<bridge::Submitted> &result);
  void maybe_resend_after_review();
  void on_hub_event(const bridge::HubEvent &event);
  void download_done(const bridge::Transfer &t);
  void verify_download(ArtifactRow &row);
  void release_preview();
  bridge::Target target() const;
  std::string connection_label() const;
  void publish_connection();
  void start_upload(const std::string &path);

  AppStore &store_;
  std::shared_ptr<Alive> alive_;
  bridge::Client *client_ = nullptr;
  bridge::ListenerHandle state_listener_, transfer_listener_;
  bridge::BridgeState bridge_state_ = bridge::BridgeState::Stopped;
  bool seen_ready_ = false;
  uint64_t version_ = 0;
  JobsStatus status_;

  /* Connections. */
  std::vector<ConnectionRow> connections_;
  std::string active_;
  uint64_t conn_epoch_ = 0; /**< bumped when the connection changes */
  uint64_t epoch_ = 0;      /**< bumped when the connection, node or workspace changes */
  std::string preferred_connection_, preferred_node_, preferred_workspace_;
  /** A workspace this client just created: kept listed and selected until the listing catches
   * up (a hub lists workspaces from the node's heartbeat snapshot, a few seconds stale). */
  struct CreatedWorkspace {
    WorkspaceRow row;
    std::chrono::steady_clock::time_point at;
  };
  std::optional<CreatedWorkspace> created_workspace_;
  std::optional<bridge::LocalRuntimeStatus> local_;
  bool local_busy_ = false;

  /* Hub. */
  std::vector<NodeRow> nodes_;
  std::string node_;
  std::vector<std::string> templates_;
  std::optional<bridge::HubPolicy> policy_;
  std::vector<ReviewItem> reviews_;
  std::map<std::string, Json> inspected_; /**< action id -> full request, this bridge process */
  bridge::Subscription hub_sub_;

  /* Workspaces. */
  std::vector<WorkspaceRow> workspaces_;
  std::string workspace_;
  std::vector<bridge::FileEntry> files_;

  /* Transfers. */
  std::vector<std::string> pending_;
  std::vector<bridge::Transfer> transfers_;
  std::set<std::string> upload_ids_; /**< uploads started from here (status messages) */
  std::map<std::string, std::string> download_for_; /**< transfer id -> artifact path */
  std::set<std::string> open_after_;                /**< downloads opened when verified */

  /* Submit. */
  SubmitForm form_;
  std::optional<Submission> submission_;

  /* Tasks. */
  std::vector<TaskRow> tasks_;
  double snapshot_time_ = 0.0;
  bridge::Subscription watch_;
  std::string selected_;
  uint64_t detail_epoch_ = 0;
  std::string artifacts_for_state_; /**< the task state artifacts were listed in */

  /* Detail. */
  ui::LogBuffer log_all_{10000}, log_out_{10000}, log_err_{10000};
  bool logs_ended_ = false;
  bridge::Subscription logs_sub_, events_sub_;
  EventsSummary events_;
  std::vector<ArtifactRow> artifacts_;
  Preview preview_;
};

/**
 * Sets JobsState::create_texture / free_texture to textures of the GPU module (RGBA8, rows top to
 * bottom, as stk_ui's image widget samples them). Needs the GPU context of the windows (stk_gfx);
 * call JobsState::clear_preview() and reset the hooks before the window manager is destroyed.
 */
void use_gpu_textures(JobsState &jobs);

/** Catalog key of a task state ("jobs.state.running"; unknown states map to their own text). */
std::string task_state_key(const std::string &state);
/** Colour of a task state for tables (theme state colours; alpha 0 = default text). */
ui::Color task_state_color(const ui::Theme &theme, const TaskRow &task);
/** "12.3 MiB" */
std::string format_bytes(int64_t bytes);

}  // namespace stk::app
