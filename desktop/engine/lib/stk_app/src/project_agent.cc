/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_agent.hh"

#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"

#include <limits>
#include <stdexcept>

namespace stk::app {
using io::Json;

namespace {
constexpr double kFollowSeconds = 1.0;

std::string new_uuid()
{
  const auto hex = new_idempotency_key();
  return hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" + hex.substr(16, 4) + "-" + hex.substr(20);
}
}  // namespace

void ProjectAgent::reset()
{
  ++epoch_; ++version_;
  busy_ = false;
  error_.clear();
  route_ = Json::object(); sessions_ = Json::array(); view_ = Json::object(); verification_ = Json::object();
  route_loaded_ = list_loaded_ = route_reading_ = list_reading_ = route_asked_ = list_asked_ = false;
  view_reading_ = view_pending_ = owner_reading_ = session_reading_ = was_running_ = start_pending_ = false;
  selected_.clear(); sent_.clear();
  owners_.clear(); session_views_.clear();
  attempt_ = {};
  due_ = wake_scheduled = 0;
}

bool ProjectAgent::supported() const
{
  if (!project_.ready() || !project_.loaded() || project_.project()->format_version < 13) { return false; }
  const auto hello = store_.bridge()->hello_info();
  for (const auto *method : {"project.agent.route", "project.agent.create", "project.agent.say", "project.agent.start",
       "project.agent.cancel", "project.agent.recover", "project.agent.get", "project.agent.list",
       "project.agent.objects", "project.agent.verify"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectAgent::decide_supported() const
{
  const auto hello = supported() ? store_.bridge()->hello_info() : std::nullopt;
  return hello && hello->has_method("project.agent.decide");
}

bool ProjectAgent::call(const std::string &method, Json params, std::function<void(const Json &)> done)
{
  if (!supported() || busy_ || project_.busy()) { return false; }
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  busy_ = true;
  error_.clear();
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;  // starting the agent is never repeated blindly
  store_.bridge()->call(method, params, options).then([this, weak, epoch, handle, done = std::move(done)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    busy_ = false;
    if (!result.ok()) {
      error_ = result.error().message;
      store_.log(error_);
      view_pending_ = !selected_.empty();  // the session may have changed anyway (a lost reply)
      list_asked_ = false;                 // a lost create may have made a session
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &exc) { error_ = exc.what(); }
    }
    ++version_;
    store_.changed();
  });
  store_.changed();
  return true;
}

bool ProjectAgent::read(const std::string &method, Json params, bool &flight, std::function<void(const Json &)> done,
                        std::function<void()> failed)
{
  if (!supported() || flight) { return false; }
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  flight = true;
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  store_.bridge()->call(method, params, options).then(
      [this, weak, epoch, handle, &flight, done = std::move(done), failed = std::move(failed)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    flight = false;
    if (!result.ok()) {
      error_ = result.error().message;
      if (failed) { failed(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &exc) { error_ = exc.what(); }
    }
    ++version_;
    store_.changed();
  });
  return true;
}

void ProjectAgent::adopt(const Json &view)
{
  const auto id = io::get_string(view.value("session", Json::object()), "id");
  if (id.empty()) { throw std::runtime_error("The agent session reply has no session"); }
  if (id != selected_) { return; }  // another session was selected meanwhile
  // Events only ever grow: an older reply that arrives late is not shown over a newer one.
  if (!view_.empty() && io::get_string(view_.at("session"), "id") == id &&
      io::get_int(view, "total", 0) < io::get_int(view_, "total", 0)) { return; }
  const bool running = view.value("running", false);
  if (was_running_ && !running) { list_asked_ = false; session_views_.erase(id); }  // it stopped: its summary changed
  was_running_ = running;
  view_ = view;
}

bool ProjectAgent::load_route()
{
  route_asked_ = true;
  return read("project.agent.route", Json::object(), route_reading_, [this](const Json &result) {
    route_ = result;
    route_loaded_ = true;
  });
}

bool ProjectAgent::load_list()
{
  list_asked_ = true;
  return read("project.agent.list", {{"limit", 50}}, list_reading_, [this](const Json &result) {
    sessions_ = result.value("items", Json::array());
    list_loaded_ = true;
  });
}

void ProjectAgent::select(const std::string &session_id)
{
  if (session_id == selected_) { return; }
  selected_ = session_id;
  view_ = Json::object(); verification_ = Json::object();
  was_running_ = false;
  view_pending_ = !session_id.empty();
  ++version_;
  store_.changed();
}

bool ProjectAgent::ask(const std::string &text)
{
  if (text.empty() || running() || io::get_string(view_, "state") == "ended") { return false; }
  // A lost reply then a second click with the same text sends the same IDs, which the service answers with the
  // session it already made (or the message it already saved) instead of a second one.
  const bool create = selected_.empty();
  if (attempt_.text != text || attempt_.create != create || (!create && attempt_.session_id != selected_) ||
      attempt_.turn_id.empty()) {
    attempt_ = {text, create ? new_uuid() : selected_, new_uuid(), create};
  }
  const auto session_id = attempt_.session_id;
  const Json params = {{"session_id", session_id}, {"turn_id", attempt_.turn_id}, {"text", text}};
  return call(create ? "project.agent.create" : "project.agent.say", params, [this, session_id, text](const Json &result) {
    attempt_ = {};
    sent_ = text;
    selected_ = session_id;
    adopt(result);
    list_asked_ = false;
    busy_ = false;
    if (!start()) { start_pending_ = true; }  // the project was busy: start once it is not
  });
}

bool ProjectAgent::start()
{
  if (selected_.empty()) { return false; }
  start_pending_ = false;
  return call("project.agent.start", {{"session_id", selected_}}, [this](const Json &result) {
    adopt(result);
    list_asked_ = false;
    due_ = 0;
  });
}

bool ProjectAgent::cancel()
{
  if (selected_.empty()) { return false; }
  return call("project.agent.cancel", {{"session_id", selected_}}, [this](const Json &result) { adopt(result); });
}

bool ProjectAgent::recover()
{
  if (selected_.empty()) { return false; }
  return call("project.agent.recover", {{"session_id", selected_}}, [this](const Json &result) {
    adopt(result);
    list_asked_ = false;
  });
}

bool ProjectAgent::verify()
{
  if (selected_.empty()) { return false; }
  const auto id = selected_;
  return call("project.agent.verify", {{"session_id", id}}, [this, id](const Json &result) {
    if (id == selected_) { verification_ = result; }
  });
}

bool ProjectAgent::read_draft(const std::string &draft_id, std::function<void(const Json &)> done)
{
  return call("project.drafts.get", {{"draft_id", draft_id}}, [done = std::move(done)](const Json &result) {
    done(result.at("draft"));
  });
}

const Json *ProjectAgent::owner(const std::string &kind, const std::string &id)
{
  if (id.empty() || !supported()) { return nullptr; }
  const auto key = kind + ":" + id;
  if (const auto found = owners_.find(key); found != owners_.end()) { return &found->second; }
  read("project.agent.objects", {{"kind", kind}, {"object_id", id}}, owner_reading_,
       [this, key](const Json &result) { owners_[key] = result; },
       [this, key] { owners_[key] = {{"owner", nullptr}, {"failed", true}}; });
  return nullptr;
}

void ProjectAgent::track_draft(const std::string &draft_id)
{
  const auto *made = owner("draft", draft_id);
  if (!made || !made->value("owner", Json()).is_object()) { return; }
  const auto session = io::get_string(made->at("owner"), "session_id");
  if (session.empty() || session_views_.count(session) || (session == selected_ && !view_.empty()) || session_reading_) { return; }
  read("project.agent.get", {{"session_id", session}, {"limit", 1}}, session_reading_,
       [this, session](const Json &result) { session_views_[session] = result; },
       [this, session] { session_views_[session] = {{"failed", true}}; });
}

AgentDraft ProjectAgent::draft_state(const std::string &draft_id, AgentItem *item) const
{
  if (draft_id.empty() || !decide_supported()) { return AgentDraft::None; }
  // Not read yet: treated as no session's (a person may apply a draft outside a session; the session then observes
  // it). Once a draft is known to be an agent's, a decision waits for its session.
  const auto made = owners_.find("draft:" + draft_id);
  if (made == owners_.end()) { return AgentDraft::None; }
  if (!made->second.value("owner", Json()).is_object()) { return AgentDraft::None; }
  const auto session = io::get_string(made->second.at("owner"), "session_id");
  const Json *view = nullptr;
  if (session == selected_ && !view_.empty()) { view = &view_; }
  else if (const auto found = session_views_.find(session); found != session_views_.end()) { view = &found->second; }
  if (!view) { return AgentDraft::Unknown; }
  if (view->value("failed", false)) { return AgentDraft::None; }
  if (view->value("running", false)) { return AgentDraft::Running; }
  for (const auto &entry : view->value("awaiting", Json::array())) {
    if (io::get_string(entry, "kind") == "apply_draft" && io::get_string(entry, "draft_id") == draft_id) {
      if (item) {
        *item = AgentItem{session, io::get_string(entry, "item_id"), draft_id, io::get_string(entry, "draft_sha256"),
                          io::get_int(entry, "base_revision", -1)};
      }
      return AgentDraft::Waiting;
    }
  }
  return AgentDraft::None;
}

std::optional<AgentItem> ProjectAgent::awaiting_for_draft(const std::string &draft_id) const
{
  AgentItem item;
  if (draft_state(draft_id, &item) == AgentDraft::Waiting) { return item; }
  return std::nullopt;
}

void ProjectAgent::draft_changed(const std::string &)
{
  list_asked_ = false;
  view_pending_ = !selected_.empty();
  session_views_.clear();  // who made a draft never changes; what its session waits for does
  ++version_;
}

double ProjectAgent::pump(const double now)
{
  constexpr double kNever = std::numeric_limits<double>::infinity();
  if (!supported()) { return kNever; }
  if (!route_asked_ && !route_reading_) { load_route(); }
  if (!list_asked_ && !list_reading_) { load_list(); }
  if (selected_.empty() || busy_ || project_.busy()) { return kNever; }
  if (start_pending_) { start(); return kNever; }
  if (view_reading_) { return kNever; }  // the reply redraws
  const bool following = running() && now > 0;  // pump(0) (pages without a clock) only reads what is pending
  if (view_pending_ || (following && now >= due_)) {
    view_pending_ = false;
    if (now > 0) { due_ = now + kFollowSeconds; }
    read("project.agent.get", {{"session_id", selected_}}, view_reading_, [this](const Json &result) { adopt(result); });
    return kNever;
  }
  return following ? due_ : kNever;
}
}  // namespace stk::app
