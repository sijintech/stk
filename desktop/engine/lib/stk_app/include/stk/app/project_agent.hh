/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/bridge/client.hh"

#include <map>
#include <optional>
#include <string>

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

/** Agent sessions of the open project (project.agent.*, format 13; docs/design/agent-harness.md): the planner's
 * route, the list of sessions, the selected session's steps, and who made a draft, message, request or context.
 * Asking saves the message, then starts the agent in the service, which answers in the background; the selected
 * session is read again every second while it runs. A draft the agent saved is applied or discarded only by a
 * person through project.agent.decide (ProjectState routes the review page's buttons there). Sessions never change
 * the project's revision; replies of a replaced project opening are ignored. */
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
  bool busy() const { return busy_; }
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

  /** Select a session ("" starts a new one with the next message). */
  void select(const std::string &session_id);
  const std::string &selected() const { return selected_; }
  /** The selected session (agentSessionView, with usage), empty until read. */
  const io::Json &view() const { return view_; }
  bool running() const { return view_.value("running", false); }
  /** Save ``text`` as the selected session's next message (or a new session's first) and start the agent. */
  bool ask(const std::string &text);
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
  bool call(const std::string &method, io::Json params, std::function<void(const io::Json &)> done);
  bool read(const std::string &method, io::Json params, bool &flight, std::function<void(const io::Json &)> done,
            std::function<void()> failed = {});
  void adopt(const io::Json &view);

  AppStore &store_;
  ProjectState &project_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0, version_ = 0;
  bool busy_ = false;
  std::string error_;
  io::Json route_ = io::Json::object(), sessions_ = io::Json::array(), view_ = io::Json::object();
  io::Json verification_ = io::Json::object();
  bool route_loaded_ = false, list_loaded_ = false, route_reading_ = false, list_reading_ = false;
  // A read asked once is not asked again until something changes (a failed read is not repeated every frame).
  bool route_asked_ = false, list_asked_ = false;
  bool view_reading_ = false, view_pending_ = false, owner_reading_ = false, session_reading_ = false, was_running_ = false;
  bool start_pending_ = false;  // a saved message whose start was refused while the project was busy
  std::string selected_, sent_;
  std::map<std::string, io::Json> owners_;          // "kind:id" -> {owner} (or {owner: null, failed: true})
  std::map<std::string, io::Json> session_views_;   // session ID -> its view (the sessions of tracked drafts)
  struct Attempt { std::string text, session_id, turn_id; bool create = false; } attempt_;
  double due_ = 0;
};
}  // namespace stk::app
