/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace stk::app {
class AppStore;
class ProjectState;

/** An open item of an agent session that a person decides on the session's card (an ``apply_draft`` item). */
struct AgentItem {
  std::string session_id, item_id, draft_id, draft_sha256;
  int64_t base_revision = -1;
};

/** What a draft means to the agent sessions: no session waits on it, or who made it is not read yet (``None``); its
 * session waits for a person's decision (``Waiting``); its session runs, so a decision must wait (``Running``); an
 * agent made it but its session is not read yet (``Unknown``). */
enum class AgentDraft { Unknown, None, Waiting, Running };

/** The full frozen snapshot ID and (output name, record ID) pairs of one task of a linked-task detail. */
struct AgentRunOutputs { std::string snapshot_id; std::vector<std::pair<std::string, std::string>> records; };

/** Agent sessions of the open project (project.agent.*, format 13; docs/design/agent-harness.md): the planner's
 * route, the list of sessions, the selected session's steps, and who made a draft, message, request or context.
 * Asking saves the message, then starts the agent in the service, which answers in the background; the selected
 * session is read again every second while it runs. A draft the agent saved is applied or discarded only by a
 * person through project.agent.decide (ProjectState routes the review page's buttons there). Sessions never change
 * the project's revision; replies of a replaced project opening are ignored, and a read of the selected session
 * answers only the selection that asked (even after switching away and back to the same session). */
class ProjectAgent {
 public:
  ProjectAgent(AppStore &store, ProjectState &project) : store_(store), project_(project) {}
  ~ProjectAgent() { alive_.reset(); }
  ProjectAgent(const ProjectAgent &) = delete;
  ProjectAgent &operator=(const ProjectAgent &) = delete;

  void reset();
  /** The service runs agent sessions and the project is format 13 or later. */
  bool supported() const;
  /** The service takes a person's decision on a session's draft (desktop only). */
  bool decide_supported() const;
  /** Desktop-only preparation and one-use run approvals; older bridges keep the existing assistant. */
  bool runs_supported() const;
  bool busy() const { return busy_; }
  /** A saved legacy message whose Start is still waiting to be dispatched. */
  bool deferred_start_pending() const { return start_pending_; }
  uint64_t version() const { return version_; }
  const std::string &error() const { return error_; }

  /** project.agent.route: the planner candidates on this computer or the organization's network. */
  bool route_loaded() const { return route_loaded_; }
  const io::Json &route() const { return route_; }
  bool load_route();
  /** Newest sessions first ({id, first_message, state, turn, stop_reason, awaiting}). */
  bool list_loaded() const { return list_loaded_; }
  const io::Json &sessions() const { return sessions_; }
  bool load_list();
  /** Load only the session list (for the rail) under the same once-asked and in-flight guards as pump: no session
   * read, start or other call is sent. Returns whether a list read was sent. */
  bool sync_session_list();

  /** Select a session ("" starts a new one with the next message). */
  void select(const std::string &session_id);
  const std::string &selected() const { return selected_; }
  /** Changes whenever the selected session changes (and on reset); never repeats within a controller. */
  uint64_t selection_epoch() const { return selection_; }
  /** Whether passive history navigation may change the selection now: no explicit call is in flight, and nothing a
   * selection change would drop is waiting (a deferred start, a lost send's reusable IDs, a sent message the editor
   * has not taken). Navigation only; it grants no permission, and an explicit select stays available. */
  bool history_selection_available() const;
  /** Read an existing session from history, retrying an unsuccessful selection of the same ID. */
  bool select_history_session(const std::string &session_id);
  /** The selected session (agentSessionView, with usage), empty until read. */
  const io::Json &view() const { return view_; }
  bool running() const { return view_.value("running", false); }
  /** Save ``text`` as the selected session's next message (or a new session's first) and start the agent. */
  bool ask(const std::string &text);
  /** Save a message, explicitly set (or clear with null) its preparation target, then start. */
  bool ask(const std::string &text, const io::Json &simulation);
  bool set_run_target(const io::Json &simulation);
  bool target_pending() const { return pending_targets_.count(selected_) != 0; }
  /** Cards include consumed decisions and locally uncertain calls, so Observe remains available. */
  io::Json run_cards() const;
  bool read_run_plan(const io::Json &item);
  const io::Json *run_plan(const io::Json &item) const;
  bool can_decide_run(const io::Json &item, const std::string &decision) const;
  bool decide_run(const io::Json &item, const std::string &decision);
  bool observe_run(const io::Json &item);
  /** Read-only linked-task detail of a consumed run card (docs/design/native-conversation-references.md 4.3): the
   * selected session shows ``item`` with a decision or receipt, and the service reads workflow runs. */
  bool can_read_run_detail(const io::Json &item) const;
  /** Send one project.workflow_runs.get for the card's run. Returns the ticket that owns its reply (0: not sent).
   * Never plans, observes, decides, starts, saves or sends; never sets busy() or error(). */
  uint64_t read_run_detail(const io::Json &item);
  /** A bounded local projection while ``ticket`` still belongs to the current card: {state: reading | ready |
   * unavailable | mismatch, ...}; nullptr once closed, superseded, reselected or reopened. Memory only. */
  const io::Json *run_detail(uint64_t ticket, const io::Json &item) const;
  /** Forget ``ticket``; its late reply is then dropped. */
  void close_run_detail(uint64_t ticket);
  /** The ready detail of ``ticket`` may list its produced frozen snapshots' files: the service reads and resolves
   * snapshots. Each task with a snapshot and output records is one files entry (its ``files_entry`` index). */
  bool can_read_run_files(uint64_t ticket, const io::Json &item) const;
  /** One project.snapshots.get for the exact snapshot of files entry ``entry`` (from the validated workflow reply),
   * replacing an earlier list and preview of the ticket. Passive like read_run_detail; false when not sent. */
  bool read_run_files(uint64_t ticket, const io::Json &item, size_t entry);
  /** {state: reading | ready | unavailable | mismatch, entry, files: [{output, name, size, preview: text | large |
   * format}], more}: only the entry's output records, each cross-checked with the manifest. Never an ID or path. */
  const io::Json *run_files(uint64_t ticket, const io::Json &item) const;
  /** Back to the tasks: forget the list and its preview (late replies are dropped). */
  void close_run_files(uint64_t ticket);
  /** One project.snapshots.resolve for listed file ``file`` when its manifest size and name allow a text preview
   * (nothing is resolved, so nothing is hashed, otherwise). The reply must name the manifest's snapshot, record,
   * digest and size; the frozen object is read once with no final link, and its bytes must hash to the manifest. */
  bool read_run_file_preview(uint64_t ticket, const io::Json &item, size_t file);
  /** {state: reading | ready | unavailable | mismatch | not_text, file, name, text}: ``text`` is the complete UTF-8
   * content with controls, bidirectional and invisible format characters shown as \u{hex} (CRLF is one line end). */
  const io::Json *run_file_preview(uint64_t ticket, const io::Json &item) const;
  /** Back to the list (late replies are dropped). */
  void close_run_file_preview(uint64_t ticket);
  /** Answer the message that waits (after a refusal, or when a run was lost). */
  bool start();
  bool cancel();
  bool recover();
  bool verify();
  const io::Json &verification() const { return verification_; }
  /** Read a draft a session waits on (to open it in the review page). */
  bool read_draft(const std::string &draft_id, std::function<void(const io::Json &)> done);

  /** Which session and step made an object ({owner: null | {session_id, event_id, turn}}), or nullptr until read. */
  const io::Json *owner(const std::string &kind, const std::string &id);
  /** Read who made ``draft_id`` and, for an agent's draft, its session (call while a draft is shown). */
  void track_draft(const std::string &draft_id);
  /** From what ``track_draft`` read: whether a session waits on the draft (its item in ``item``). */
  AgentDraft draft_state(const std::string &draft_id, AgentItem *item = nullptr) const;
  /** The open ``apply_draft`` item for ``draft_id`` (``draft_state`` is ``Waiting``), if any. */
  std::optional<AgentItem> awaiting_for_draft(const std::string &draft_id) const;
  /** A draft was applied, discarded or decided: read the sessions again. */
  void draft_changed(const std::string &draft_id);
  /** The text of a message the service saved since the last call (the editor then clears its box). */
  std::string take_sent() { auto value = std::move(sent_); sent_.clear(); return value; }

  /** Read what is due; returns when to be called again (infinity: nothing to follow). */
  double pump(double now);
  double wake_scheduled = 0;

 private:
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done,
            std::function<void()> failed = {});
  /** ``selection_scoped``: the reply (success or error) is dropped once the selection changed; select() then
   * releases ``flight`` for the new selection, so the dropped reply must not touch it. */
  bool read(const std::string &method, io::Json params, bool &flight, std::function<void(const io::Json &)> done,
            std::function<void()> failed = {}, bool selection_scoped = false);
  void adopt(const io::Json &view);
  bool ask_impl(const std::string &text, std::optional<io::Json> simulation);
  bool configure_target(const io::Json &simulation, bool start_after);
  bool current_run_item(const io::Json &item, bool awaiting) const;
  std::string run_key(const io::Json &item) const;

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0, selection_ = 0;
  bool busy_ = false;
  std::string error_;
  io::Json route_ = io::Json::object(), sessions_ = io::Json::array(), view_ = io::Json::object();
  io::Json verification_ = io::Json::object();
  bool route_loaded_ = false, list_loaded_ = false, route_reading_ = false, list_reading_ = false;
  // A read asked once is not asked again until something changes (a failed read is not repeated every frame).
  bool route_asked_ = false, list_asked_ = false;
  bool view_reading_ = false, view_pending_ = false, owner_reading_ = false, session_reading_ = false, was_running_ = false;
  bool start_pending_ = false;  // a saved message whose start was refused while the project was busy
  std::set<std::string> pending_targets_; // unconfirmed Set/Clear, retained across session selection changes
  std::string selected_, sent_;
  std::map<std::string, io::Json> owners_;          // "kind:id" -> {owner} (or {owner: null, failed: true})
  std::map<std::string, io::Json> session_views_;   // session ID -> its view (the sessions of tracked drafts)
  // Transient only: never restored as execution permission or a reviewed plan.
  std::map<std::string, io::Json> run_plans_, run_actions_;
  // Linked-task details by ticket: the exact card that asked and its projection (never a full plan or a path).
  // ``produced`` keeps the full snapshot and record IDs of each files entry privately (not in ``view``); a list
  // keeps each listed record's manifest identity. ``step`` changes with every file read or back, fencing replies.
  struct RunFile { std::string record_id, name, sha256; int64_t size = -1; bool text = false; };
  struct RunDetail {
    io::Json item, view;
    uint64_t project_scope;
    std::vector<AgentRunOutputs> produced;
    io::Json files, preview;  // null while not shown
    size_t entry = 0;
    std::vector<RunFile> listed;
    uint64_t step = 0;
  };
  bool run_files_current(uint64_t ticket, const io::Json &item) const;
  std::map<uint64_t, RunDetail> run_details_;
  uint64_t run_detail_ticket_ = 0;  // never repeats within a controller, so a closed ticket cannot come back
  struct Attempt { std::string text, session_id, turn_id; bool create = false; } attempt_;
  double due_ = 0;
};
}  // namespace stk::app
