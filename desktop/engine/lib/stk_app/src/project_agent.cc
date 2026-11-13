/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_agent.hh"

#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/ui/utf8.hh"

#include <algorithm>
#include <cctype>
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

bool same_run_item(const Json &a, const Json &b)
{
  if (!a.is_object() || !b.is_object()) { return false; }
  for (const auto *key : {"item_id", "kind", "run_id", "plan_sha256", "request_sha256", "expected_revision"}) {
    if (!a.contains(key) || !b.contains(key) || a.at(key) != b.at(key)) { return false; }
  }
  return io::get_string(a, "kind") == "start_run" && !io::get_string(a, "item_id").empty() &&
      !io::get_string(a, "plan_sha256").empty();
}

// Linked-task detail limits: the reply holds the complete frozen plan (up to 16 MiB); only this much is kept.
constexpr size_t kDetailTasks = 200, kDetailFiles = 20, kDetailTickets = 8;

const Json &member(const Json &object, const char *key)
{
  static const Json none;
  return object.is_object() && object.contains(key) ? object.at(key) : none;
}

/** One display line of untrusted text: controls and bidirectional overrides become spaces, at most ``columns``. */
std::string plain(const Json &value, const int columns)
{
  if (!value.is_string()) { return {}; }
  const auto &text = value.get_ref<const std::string &>();
  const size_t budget = size_t(columns) * 4 + 16;  // enough to exceed ``columns`` and show the ellipsis
  std::string out;
  for (size_t pos = 0; pos < text.size() && out.size() < budget;) {
    size_t length = 0;
    const auto cp = ui::utf8::decode(text, pos, &length);
    pos += std::max<size_t>(length, 1);
    if (cp < 0x20 || (cp >= 0x7f && cp <= 0x9f) || ui::utf8::is_space(cp) || cp == 0x61c || cp == 0x200e ||
        cp == 0x200f || (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069)) {
      if (!out.empty() && out.back() != ' ') { out += ' '; }
    }
    else { ui::utf8::append(out, cp); }
  }
  while (!out.empty() && out.back() == ' ') { out.pop_back(); }
  return core::utf8::truncate_display(out, columns);
}

std::string prefix(const Json &value) { return core::utf8::truncate_display(plain(value, 64), 8, ""); }

/** A directory inside the project only (never absolute, a drive, a backslash path or a parent step). */
std::string relative_directory(const Json &value)
{
  if (!value.is_string()) { return {}; }
  const auto &text = value.get_ref<const std::string &>();
  if (text.empty() || text.size() > 4096 || text.front() == '/' || text.find('\\') != std::string::npos ||
      text.find(':') != std::string::npos) { return {}; }
  for (size_t begin = 0; begin <= text.size();) {
    const auto end = std::min(text.find('/', begin), text.size());
    if (text.compare(begin, end - begin, "..") == 0) { return {}; }
    begin = end + 1;
  }
  return plain(value, 120);
}

// File preview limits, as the Web conversation preview: small UTF-8 text by manifest size and file name only.
constexpr int64_t kPreviewBytes = 256 * 1024;
constexpr size_t kFileEntries = 8;

/** A project UUID (projectUuid of the Bridge schema): the only snapshot and record IDs ever sent. */
bool project_uuid(const Json &value)
{
  if (!value.is_string()) { return false; }
  const auto &text = value.get_ref<const std::string &>();
  if (text.size() != 36) { return false; }
  for (size_t i = 0; i < text.size(); ++i) {
    const char c = text[i];
    if (i == 8 || i == 13 || i == 18 || i == 23) { if (c != '-') { return false; } }
    else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) { return false; }
  }
  return true;
}

bool sha256_hex(const Json &value)
{
  return value.is_string() && core::is_sha256_hex(value.get_ref<const std::string &>());
}

/** The Web preview's text formats, by the frozen file's own name (case-insensitive). */
bool text_format(const std::string &name)
{
  const auto dot = name.rfind('.');
  if (dot == std::string::npos || dot == 0) { return false; }
  std::string extension = name.substr(dot + 1);
  std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char c) { return std::tolower(c); });
  for (const auto *known : {"txt", "log", "out", "err", "csv", "tsv", "json", "md"}) {
    if (extension == known) { return true; }
  }
  return false;
}

/** Valid UTF-8 shown literally in a log view: CRLF is one line end; other controls (a lone CR, ESC, DEL, C1),
 * bidirectional and invisible format characters become \u{hex}, so none can rewind, recolor or reorder a line. */
std::string literal_text(std::string_view text)
{
  std::string out;
  out.reserve(text.size());
  for (size_t pos = 0; pos < text.size();) {
    const auto decoded = core::utf8::decode(text, pos);
    const auto cp = decoded.code_point;
    const size_t length = std::max<size_t>(decoded.length, 1);
    if (cp == '\r' && pos + 1 < text.size() && text[pos + 1] == '\n') { out += '\n'; pos += 2; continue; }
    const bool hidden = (cp < 0x20 && cp != '\n' && cp != '\t') || (cp >= 0x7f && cp <= 0x9f) || cp == 0xad ||
        cp == 0x61c || cp == 0x180e || (cp >= 0x200b && cp <= 0x200f) || (cp >= 0x2028 && cp <= 0x202e) ||
        (cp >= 0x2060 && cp <= 0x206f) || cp == 0xfeff || (cp >= 0xfff9 && cp <= 0xfffb);
    if (hidden) {
      static const char *digits = "0123456789abcdef";
      std::string hex;
      for (auto value = uint32_t(cp); value || hex.empty(); value >>= 4) { hex.insert(hex.begin(), digits[value & 15]); }
      out += "\\u{" + hex + "}";
    }
    else { out.append(text.substr(pos, length)); }
    pos += length;
  }
  return out;
}

/** The bounded projection of project.workflow_runs.get for the card ``item`` (design 4.3). Throws on a reply
 * that is not this card's run; a different frozen plan keeps only the mismatch. ``outputs`` receives the full
 * snapshot and record IDs of each task that produced both (its ``files_entry``), never part of the projection. */
Json run_detail_projection(const Json &result, const Json &item, std::vector<AgentRunOutputs> &outputs)
{
  const auto &run = member(result, "run");
  if (!run.is_object() || io::get_string(run, "id") != io::get_string(item, "run_id") ||
      !member(run, "tasks").is_array()) {
    throw std::runtime_error("The workflow run reply is not this card's run");
  }
  if (io::get_string(run, "plan_sha256") != io::get_string(item, "plan_sha256")) { return {{"state", "mismatch"}}; }
  std::map<std::string, int64_t> numbers;  // row record ID -> its row number in the frozen plan
  if (const auto &rows = member(run, "rows"); rows.is_array()) {
    for (const auto &row : rows) {
      if (row.is_object()) { numbers[io::get_string(row, "id")] = io::get_int(row, "number", -1); }
    }
  }
  Json counts = Json::object();
  if (member(run, "counts").is_object()) {
    for (const auto &[status, count] : run.at("counts").items()) {
      if (counts.size() < 16 && count.is_number_integer()) { counts[plain(Json(status), 24)] = count.get<int64_t>(); }
    }
  }
  const auto &all = run.at("tasks");
  Json tasks = Json::array();
  for (size_t i = 0; i < std::min(all.size(), kDetailTasks); ++i) {
    const auto &task = all.at(i);
    const auto row = numbers.find(io::get_string(task, "row"));
    Json line = {{"step", plain(member(task, "step"), 48)}, {"row", row == numbers.end() ? -1 : row->second},
                 {"attempt", io::get_int(task, "attempt", 0)}, {"status", plain(member(task, "status"), 24)}};
    if (const auto &progress = member(task, "progress"); progress.is_object()) {
      line["stage"] = plain(member(progress, "stage"), 24);
      line["state"] = plain(member(progress, "state"), 24);
      line["task_id"] = prefix(member(progress, "task_id"));
    }
    if (const auto &produced = member(task, "produced"); produced.is_object()) {
      Json out = Json::object();
      if (const auto snapshot = prefix(member(produced, "snapshot_id")); !snapshot.empty()) { out["snapshot_id"] = snapshot; }
      if (const auto &files = member(produced, "files"); files.is_object()) {
        Json names = Json::array();
        for (const auto &[name, record] : files.items()) {
          if (names.size() == kDetailFiles) { break; }
          names.push_back(plain(Json(name), 80));
        }
        out["file_count"] = files.size();
        out["files"] = std::move(names);
      }
      if (const auto directory = relative_directory(member(produced, "directory")); !directory.empty()) {
        out["directory"] = directory;
      }
      if (const auto analysis = prefix(member(produced, "analysis_run_id")); !analysis.empty()) {
        out["analysis_run_id"] = analysis;
      }
      // A files entry only for the exact snapshot and record IDs of this validated reply, all of them well formed.
      const auto &files = member(produced, "files");
      if (outputs.size() < kFileEntries && project_uuid(member(produced, "snapshot_id")) && files.is_object() &&
          !files.empty() && files.size() <= 100 &&
          std::all_of(files.begin(), files.end(), [](const Json &record) { return project_uuid(record); })) {
        AgentRunOutputs entry{produced.at("snapshot_id").get<std::string>(), {}};
        for (const auto &[name, record] : files.items()) { entry.records.emplace_back(name, record.get<std::string>()); }
        out["files_entry"] = outputs.size();
        outputs.push_back(std::move(entry));
      }
      if (!out.empty()) { line["produced"] = std::move(out); }
    }
    tasks.push_back(std::move(line));
  }
  return {{"state", "ready"}, {"status", plain(member(run, "status"), 24)},
          {"complete", io::get_bool(run, "complete", false)}, {"stop_error", !member(run, "stop_error").is_null()},
          {"counts", std::move(counts)}, {"tasks", std::move(tasks)},
          {"more", all.size() - std::min(all.size(), kDetailTasks)}};
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
  pending_targets_.clear();
  selected_.clear(); sent_.clear();
  owners_.clear(); session_views_.clear(); run_plans_.clear(); run_actions_.clear(); run_details_.clear();
  ++selection_;
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

bool ProjectAgent::runs_supported() const
{
  const auto hello = supported() ? store_.bridge()->hello_info() : std::nullopt;
  for (const auto *method : {"project.agent.run_target", "project.agent.run_plan", "project.agent.run_decide",
       "project.agent.run_observe"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectAgent::call(const std::string &method, Json params, std::function<void(const Json &)> done,
                        std::function<void()> failed)
{
  if (!supported() || busy_ || project_.busy()) { return false; }
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  busy_ = true;
  error_.clear();
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  const auto selection = selection_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;  // starting the agent is never repeated blindly
  store_.bridge()->call(method, params, options).then([this, weak, epoch, selection, handle, done = std::move(done),
                                                     failed = std::move(failed)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    busy_ = false;
    // Even switching away and back invalidates a chained create/target/start or decision callback.
    if (selection != selection_) {
      view_pending_ = !selected_.empty(); list_asked_ = false;
      ++version_; store_.changed(); return;
    }
    if (!result.ok()) {
      error_ = result.error().message;
      store_.log(error_);
      view_pending_ = !selected_.empty();  // the session may have changed anyway (a lost reply)
      list_asked_ = false;                 // a lost create may have made a session
      if (failed) { failed(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &exc) { error_ = exc.what(); if (failed) { failed(); } }
    }
    ++version_;
    store_.changed();
  });
  store_.changed();
  return true;
}

bool ProjectAgent::read(const std::string &method, Json params, bool &flight, std::function<void(const Json &)> done,
                        std::function<void()> failed, const bool selection_scoped)
{
  if (!supported() || flight) { return false; }
  const auto handle = project_.project()->handle;
  params["handle"] = handle;
  flight = true;
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  const auto selection = selection_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  store_.bridge()->call(method, params, options).then(
      [this, weak, epoch, selection, selection_scoped, handle, &flight, done = std::move(done),
       failed = std::move(failed)](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !project_.project() || project_.project()->handle != handle) { return; }
    // Switching away and back to the same session ID is a new selection: its own read owns ``flight`` now.
    if (selection_scoped && selection != selection_) { return; }
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
  for (auto &[key, action] : run_actions_) {
    if (key == selected_ + "\n" + io::get_string(action.at("item"), "item_id")) { action["observed"] = false; }
  }
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

bool ProjectAgent::sync_session_list()
{
  // supported() first, as in pump: an early call must not mark the list asked before it can be read.
  if (!supported() || list_asked_ || list_reading_) { return false; }
  return load_list();
}

bool ProjectAgent::history_selection_available() const
{
  // What select() would drop: a deferred start, a lost create/say's IDs (a retry reuses them), the unsurfaced sent
  // text. busy_ covers every call in flight. Unconfirmed targets and run decisions survive selection by design.
  return !busy_ && !start_pending_ && attempt_.turn_id.empty() && sent_.empty();
}

bool ProjectAgent::select_history_session(const std::string &session_id)
{
  if (session_id.empty() || !supported() || !history_selection_available()) { return false; }
  if (selected_ != session_id) {
    error_.clear();
    select(session_id);
  }
  else if (view_.empty() && !view_reading_) {
    error_.clear();
    view_pending_ = true;
    ++version_;
    store_.changed();
  }
  return true;
}

void ProjectAgent::select(const std::string &session_id)
{
  if (session_id == selected_) { return; }
  selected_ = session_id;
  ++selection_;
  start_pending_ = false;
  attempt_ = {};
  run_plans_.clear(); run_details_.clear();
  view_ = Json::object(); verification_ = Json::object();
  was_running_ = false;
  view_reading_ = false;  // an earlier selection's read no longer holds the guard; its reply is dropped
  view_pending_ = !session_id.empty();
  ++version_;
  store_.changed();
}

bool ProjectAgent::ask(const std::string &text)
{
  return ask_impl(text, std::nullopt);
}

bool ProjectAgent::ask(const std::string &text, const Json &simulation)
{
  if (!runs_supported() || (!simulation.is_null() && !simulation.is_object())) { return false; }
  return ask_impl(text, simulation);
}

bool ProjectAgent::ask_impl(const std::string &text, std::optional<Json> simulation)
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
  return call(create ? "project.agent.create" : "project.agent.say", params,
              [this, session_id, text, simulation = std::move(simulation)](const Json &result) {
    if (io::get_string(result.value("session", Json::object()), "id") != session_id) {
      throw std::runtime_error("The saved message reply belongs to another session");
    }
    attempt_ = {};
    sent_ = text;
    select(session_id);
    adopt(result);
    list_asked_ = false;
    busy_ = false;
    if (simulation) { pending_targets_.insert(session_id); configure_target(*simulation, true); }
    else if (!start()) { start_pending_ = true; }  // legacy saved message: resume when the project is not busy
  });
}

bool ProjectAgent::configure_target(const Json &simulation, const bool start_after)
{
  if (!runs_supported() || selected_.empty() || running() ||
      (!simulation.is_null() && !simulation.is_object())) { return false; }
  const auto session = selected_;
  const bool already_pending = target_pending();
  start_pending_ = false;  // an explicit target action never resumes an older deferred start
  pending_targets_.insert(session);  // before dispatch; failures and lost/stale replies cannot restore Continue
  const bool sent = call("project.agent.run_target", {{"session_id", selected_}, {"simulation", simulation}},
              [this, start_after](const Json &result) {
    if (io::get_string(result.value("session", Json::object()), "id") != selected_) {
      throw std::runtime_error("The preparation target reply belongs to another session");
    }
    adopt(result);
    pending_targets_.erase(selected_);
    if (start_after) { start(); }  // failure leaves an explicit Continue action, never a refresh-triggered start
  });
  if (!sent && !already_pending) { pending_targets_.erase(session); }
  return sent;
}

bool ProjectAgent::set_run_target(const Json &simulation)
{
  return configure_target(simulation, false);
}

std::string ProjectAgent::run_key(const Json &item) const
{
  return selected_ + "\n" + io::get_string(item, "item_id");
}

Json ProjectAgent::run_cards() const
{
  Json cards = Json::array();
  if (!runs_supported() || selected_.empty()) { return cards; }
  for (const auto &card : view_.value("run_approvals", Json::array())) {
    if (card.is_object() && card.value("item", Json()).is_object()) { cards.push_back(card); }
  }
  for (const auto &item : view_.value("awaiting", Json::array())) {
    if (io::get_string(item, "kind") != "start_run") { continue; }
    if (std::none_of(cards.begin(), cards.end(), [&](const auto &card) { return same_run_item(card.at("item"), item); })) {
      cards.push_back({{"item", item}, {"decision", nullptr}, {"receipt", nullptr}});
    }
  }
  for (const auto &[key, action] : run_actions_) {
    if (key != selected_ + "\n" + io::get_string(action.at("item"), "item_id")) { continue; }
    auto found = std::find_if(cards.begin(), cards.end(), [&](const auto &card) {
      return same_run_item(card.at("item"), action.at("item"));
    });
    if (found == cards.end()) { cards.push_back(action); }
    else {
      // A durable receipt wins over a stale local pending marker. A local decision still closes the buttons.
      if (!found->value("decision", Json()).is_object()) { (*found)["decision"] = action.at("decision"); }
      if (!found->value("receipt", Json()).is_object() || action.value("observed", false)) {
        (*found)["receipt"] = action.at("receipt");
      }
    }
  }
  return cards;
}

bool ProjectAgent::current_run_item(const Json &item, const bool awaiting) const
{
  if (!runs_supported() || selected_.empty() || !same_run_item(item, item)) { return false; }
  if (awaiting) {
    for (const auto &entry : view_.value("awaiting", Json::array())) {
      if (same_run_item(entry, item)) { return true; }
    }
    return false;
  }
  for (const auto &card : run_cards()) { if (same_run_item(card.at("item"), item)) { return true; } }
  return false;
}

bool ProjectAgent::read_run_plan(const Json &item)
{
  if (!current_run_item(item, false)) { return false; }
  const auto key = run_key(item);
  run_plans_.erase(key);
  return call("project.agent.run_plan", {{"session_id", selected_}, {"item_id", item.at("item_id")}},
              [this, key, item](const Json &result) {
    if (!same_run_item(result.at("item"), item) ||
        io::get_string(result.at("run"), "plan_sha256") != io::get_string(item, "plan_sha256")) {
      throw std::runtime_error("The frozen run plan does not match this approval");
    }
    // Keep the complete result. The editor renders every line; no excerpt can unlock approval.
    run_plans_[key] = result;
  });
}

const Json *ProjectAgent::run_plan(const Json &item) const
{
  const auto found = run_plans_.find(run_key(item));
  return found != run_plans_.end() && same_run_item(found->second.at("item"), item) ? &found->second : nullptr;
}

bool ProjectAgent::can_decide_run(const Json &item, const std::string &decision) const
{
  if ((decision != "start" && decision != "decline") || busy_ || project_.busy() || running() ||
      !current_run_item(item, true) ||
      (decision == "start" && (target_pending() || !run_plan(item) ||
        io::get_int(item, "expected_revision", -1) != project_.project()->revision))) { return false; }
  for (const auto &card : run_cards()) {
    if (same_run_item(card.at("item"), item)) {
      return card.value("decision", Json()).is_null() && card.value("receipt", Json()).is_null();
    }
  }
  return false;
}

bool ProjectAgent::decide_run(const Json &item, const std::string &decision)
{
  if (!can_decide_run(item, decision)) { return false; }
  const auto key = run_key(item);
  // Install before dispatch: even a lost reply, a session switch or a closed awaiting card only permits Observe.
  run_actions_[key] = {{"item", item}, {"decision", {{"decision", decision}}},
                       {"receipt", {{"outcome", "pending"}}}};
  const bool sent = call("project.agent.run_decide", {{"session_id", selected_}, {"item_id", item.at("item_id")},
      {"decision", decision}, {"plan_sha256", item.at("plan_sha256")}, {"expected_revision", item.at("expected_revision")}},
      [this, key](const Json &result) {
    run_actions_.at(key)["receipt"] = result.at("receipt");
    run_actions_.at(key)["observed"] = true;
    view_pending_ = true; list_asked_ = false;
  }, [this, key] { run_actions_.at(key)["receipt"] = {{"outcome", "uncertain"}, {"ok", false}}; });
  if (!sent) { run_actions_.erase(key); }
  return sent;
}

bool ProjectAgent::observe_run(const Json &item)
{
  if (!current_run_item(item, false)) { return false; }
  const auto key = run_key(item);
  return call("project.agent.run_observe", {{"session_id", selected_}, {"item_id", item.at("item_id")}},
              [this, key, item](const Json &result) {
    auto &action = run_actions_[key];
    if (action.empty()) { action = {{"item", item}, {"decision", nullptr}}; }
    action["receipt"] = result.at("receipt"); action["observed"] = true;
    view_pending_ = true; list_asked_ = false;
  });
}

bool ProjectAgent::can_read_run_detail(const Json &item) const
{
  if (!runs_supported() || selected_.empty() || !same_run_item(item, item)) { return false; }
  const auto hello = store_.bridge()->hello_info();
  if (!hello || !hello->has_method("project.workflow_runs.get")) { return false; }
  for (const auto &card : run_cards()) {
    if (same_run_item(card.at("item"), item)) {
      return card.value("decision", Json()).is_object() || card.value("receipt", Json()).is_object();
    }
  }
  return false;
}

uint64_t ProjectAgent::read_run_detail(const Json &item)
{
  if (project_.busy() || !can_read_run_detail(item)) { return 0; }
  const auto ticket = ++run_detail_ticket_;
  run_details_[ticket] = {item, {{"state", "reading"}}, store_.project_scope_epoch()};
  while (run_details_.size() > kDetailTickets) { run_details_.erase(run_details_.begin()); }
  const auto handle = project_.project()->handle;
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  const auto selection = selection_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  // A passive read: neither busy_ nor error_ changes, so no other control's enablement or message moves.
  store_.bridge()->call("project.workflow_runs.get", {{"handle", handle}, {"run_id", item.at("run_id")}}, options)
      .then([this, weak, epoch, selection, handle, ticket](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || selection != selection_ || !project_.project() ||
        project_.project()->handle != handle) { return; }
    const auto found = run_details_.find(ticket);
    if (found == run_details_.end()) { return; }  // closed, reopened (a new ticket) or evicted
    if (found->second.project_scope != store_.project_scope_epoch() ||
        !can_read_run_detail(found->second.item)) { run_details_.erase(found); }
    else if (!result.ok()) { found->second.view = {{"state", "unavailable"}}; }  // the remote message is not shown
    else {
      try { found->second.view = run_detail_projection(result.value(), found->second.item, found->second.produced); }
      catch (const std::exception &) { found->second.view = {{"state", "unavailable"}}; found->second.produced.clear(); }
    }
    ++version_;
    store_.changed();
  });
  ++version_;
  store_.changed();
  return ticket;
}

const Json *ProjectAgent::run_detail(const uint64_t ticket, const Json &item) const
{
  const auto found = run_details_.find(ticket);
  if (found == run_details_.end() || found->second.project_scope != store_.project_scope_epoch() ||
      !same_run_item(found->second.item, item) || !can_read_run_detail(item)) {
    return nullptr;
  }
  return &found->second.view;
}

void ProjectAgent::close_run_detail(const uint64_t ticket)
{
  if (run_details_.erase(ticket)) { ++version_; store_.changed(); }
}

bool ProjectAgent::can_read_run_files(const uint64_t ticket, const Json &item) const
{
  const auto *detail = run_detail(ticket, item);
  const auto hello = store_.bridge()->hello_info();
  return detail && io::get_string(*detail, "state") == "ready" && hello &&
      hello->has_method("project.snapshots.get") && hello->has_method("project.snapshots.resolve");
}

bool ProjectAgent::run_files_current(const uint64_t ticket, const Json &item) const
{
  return can_read_run_files(ticket, item) && !run_details_.at(ticket).files.is_null();
}

bool ProjectAgent::read_run_files(const uint64_t ticket, const Json &item, const size_t entry)
{
  if (project_.busy() || !can_read_run_files(ticket, item)) { return false; }
  auto &detail = run_details_.at(ticket);
  if (entry >= detail.produced.size()) { return false; }
  const auto step = ++detail.step;
  detail.entry = entry;
  detail.files = {{"state", "reading"}, {"entry", entry}};
  detail.preview = nullptr;
  detail.listed.clear();
  const auto snapshot_id = detail.produced[entry].snapshot_id;
  const auto handle = project_.project()->handle;
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  const auto selection = selection_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  store_.bridge()->call("project.snapshots.get", {{"handle", handle}, {"snapshot_id", snapshot_id}}, options)
      .then([this, weak, epoch, selection, handle, ticket, step, snapshot_id](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || selection != selection_ || !project_.project() ||
        project_.project()->handle != handle) { return; }
    const auto found = run_details_.find(ticket);
    if (found == run_details_.end() || found->second.step != step) { return; }  // closed, back or another list
    auto &detail = found->second;
    if (!run_files_current(ticket, detail.item)) { detail.files = nullptr; }
    else if (!result.ok()) { detail.files = {{"state", "unavailable"}, {"entry", detail.entry}}; }
    else {
      // The exact snapshot asked for, a well-formed manifest, and every output record of the task in it.
      const auto &snapshot = member(result.value(), "snapshot");
      const auto &manifest = member(snapshot, "manifest");
      const auto &files = member(manifest, "files");
      std::map<std::string, const Json *> by_record;
      bool valid = io::get_string(snapshot, "id") == snapshot_id && io::get_string(snapshot, "kind") == "files" &&
          io::get_string(manifest, "kind") == "files" && files.is_array() && !files.empty() && files.size() <= 100;
      for (size_t i = 0; valid && i < files.size(); ++i) {
        const auto &file = files.at(i);
        valid = project_uuid(member(file, "record_id")) && member(file, "name").is_string() &&
            sha256_hex(member(file, "sha256")) && member(file, "size").is_number_integer() &&
            file.at("size").get<int64_t>() >= 0 &&
            by_record.emplace(file.at("record_id").get<std::string>(), &file).second;
      }
      const auto &records = detail.produced[detail.entry].records;
      if (valid && std::any_of(records.begin(), records.end(), [&](const auto &record) {
            return !by_record.count(record.second);
          })) {
        detail.files = {{"state", "mismatch"}, {"entry", detail.entry}};
      }
      else if (!valid) { detail.files = {{"state", "unavailable"}, {"entry", detail.entry}}; }
      else {
        Json listed = Json::array();
        for (size_t i = 0; i < std::min(records.size(), kDetailFiles); ++i) {
          const auto &file = *by_record.at(records[i].second);
          RunFile entry{records[i].second, file.at("name").get<std::string>(), file.at("sha256").get<std::string>(),
                        file.at("size").get<int64_t>(), false};
          const bool format = text_format(entry.name);
          entry.text = format && entry.size <= kPreviewBytes;
          listed.push_back({{"output", plain(Json(records[i].first), 80)}, {"name", plain(Json(entry.name), 80)},
                            {"size", entry.size},
                            {"preview", entry.text ? "text" : (format ? "large" : "format")}});
          detail.listed.push_back(std::move(entry));
        }
        detail.files = {{"state", "ready"}, {"entry", detail.entry}, {"files", std::move(listed)},
                        {"more", records.size() - std::min(records.size(), kDetailFiles)}};
      }
    }
    ++version_;
    store_.changed();
  });
  ++version_;
  store_.changed();
  return true;
}

const Json *ProjectAgent::run_files(const uint64_t ticket, const Json &item) const
{
  return run_files_current(ticket, item) ? &run_details_.at(ticket).files : nullptr;
}

void ProjectAgent::close_run_files(const uint64_t ticket)
{
  const auto found = run_details_.find(ticket);
  if (found == run_details_.end() || found->second.files.is_null()) { return; }
  ++found->second.step;
  found->second.files = found->second.preview = nullptr;
  found->second.listed.clear();
  ++version_;
  store_.changed();
}

bool ProjectAgent::read_run_file_preview(const uint64_t ticket, const Json &item, const size_t file)
{
  if (project_.busy() || !run_files_current(ticket, item)) { return false; }
  auto &detail = run_details_.at(ticket);
  // Size and format come from the validated manifest: an unsupported or large file is never resolved (hashed).
  if (io::get_string(detail.files, "state") != "ready" || file >= detail.listed.size() ||
      !detail.listed[file].text) { return false; }
  const auto step = ++detail.step;
  const auto listed = detail.listed[file];
  const auto snapshot_id = detail.produced[detail.entry].snapshot_id;
  const auto name = detail.files.at("files").at(file).at("name");
  detail.preview = {{"state", "reading"}, {"file", file}, {"name", name}};
  const auto handle = project_.project()->handle;
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  const auto selection = selection_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  options.timeout_s = 15;
  store_.bridge()->call("project.snapshots.resolve",
                        {{"handle", handle}, {"snapshot_id", snapshot_id}, {"record_id", listed.record_id}}, options)
      .then([this, weak, epoch, selection, handle, ticket, step, snapshot_id, listed, file, name](
                bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || selection != selection_ || !project_.project() ||
        project_.project()->handle != handle) { return; }
    const auto found = run_details_.find(ticket);
    if (found == run_details_.end() || found->second.step != step) { return; }  // closed, back or another file
    auto &detail = found->second;
    if (!run_files_current(ticket, detail.item)) { detail.files = detail.preview = nullptr; detail.listed.clear(); }
    else {
      Json view = {{"state", "unavailable"}, {"file", file}, {"name", name}};  // never the message or a path
      if (result.ok()) {
        const auto &resolved = result.value();
        const auto &size = member(resolved, "size");
        if (io::get_string(resolved, "snapshot_id") != snapshot_id ||
            io::get_string(resolved, "record_id") != listed.record_id ||
            io::get_string(resolved, "sha256") != listed.sha256 || io::get_string(resolved, "name") != listed.name ||
            !size.is_number_integer() || size.get<int64_t>() != listed.size) {
          view["state"] = "mismatch";
        }
        else if (const auto path = io::get_string(resolved, "path"); !path.empty() && listed.size <= kPreviewBytes) {
          try {
            // The existing bounded reader: one regular file, no final link, exactly the manifest's size.
            const auto bytes = core::SharedBytes::read_exact_file(core::path_from_utf8(path), size_t(listed.size));
            const std::string_view text(reinterpret_cast<const char *>(bytes.data()), bytes.size());
            if (core::Sha256::hex(bytes.data(), bytes.size()) != listed.sha256) { view["state"] = "mismatch"; }
            else if (!core::utf8::is_valid(text)) { view["state"] = "not_text"; }
            else { view["state"] = "ready"; view["text"] = literal_text(text); }
          }
          catch (const std::exception &) {}  // FileError names the path: only "unavailable" is kept
        }
      }
      detail.preview = std::move(view);
    }
    ++version_;
    store_.changed();
  });
  ++version_;
  store_.changed();
  return true;
}

const Json *ProjectAgent::run_file_preview(const uint64_t ticket, const Json &item) const
{
  if (!run_files_current(ticket, item)) { return nullptr; }
  const auto &preview = run_details_.at(ticket).preview;
  return preview.is_null() ? nullptr : &preview;
}

void ProjectAgent::close_run_file_preview(const uint64_t ticket)
{
  const auto found = run_details_.find(ticket);
  if (found == run_details_.end() || found->second.preview.is_null()) { return; }
  ++found->second.step;
  found->second.preview = nullptr;
  ++version_;
  store_.changed();
}

bool ProjectAgent::start()
{
  if (selected_.empty() || target_pending()) { return false; }
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
    read("project.agent.get", {{"session_id", selected_}}, view_reading_, [this](const Json &result) { adopt(result); },
         {}, true);
    return kNever;
  }
  return following ? due_ : kNever;
}
}  // namespace stk::app
