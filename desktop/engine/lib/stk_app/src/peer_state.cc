/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/peer_state.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/core/clock.hh"
#include "stk/core/sha256.hh"
#include <algorithm>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
const std::set<std::string> actions = {"identity.initialize", "identity.rotate", "identity.revoke", "identity.recover", "pins.verify", "pins.revoke",
  "connections.open", "connections.push_signal", "connections.authenticate", "connections.close", "sessions.host", "sessions.revoke",
  "files.prepare", "files.offer", "files.accept", "files.send", "files.query", "files.recover", "files.cancel", "files.revoke"};
const std::set<std::string> reads = {"info", "operations.list", "pins.list", "connections.list", "connections.signals", "sessions.list", "files.list", "files.get"};
std::string session(bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
void cancel(std::map<std::string, std::shared_ptr<PeerState::Pending>> &);
void clear_prepared(PeerState::View &view)
{
  view.values.erase("files.prepare"); view.prepared_operation_id.clear();
  view.source_handle.clear(); view.source_project.clear(); view.source_revision = -1;
}
}
struct PeerState::Pending { std::optional<bridge::Future<Json>> future; };
namespace {
void cancel(std::map<std::string, std::shared_ptr<PeerState::Pending>> &pending)
{
  auto old = std::move(pending); pending.clear();
  for (auto &[slot, request] : old) { if (request->future) { request->future->cancel(); } }
}
}
PeerState::View::~View() { cancel(pending); }
PeerState::PeerState(AppStore &store) : store_(store) {}
PeerState::~PeerState()
{
  *alive_ = false;
  for (const auto &weak : views_) { if (auto view = weak.lock()) { detach(view); } }
}
PeerState::ViewPtr PeerState::new_view()
{
  auto view = std::make_shared<View>(); views_.push_back(view); return view;
}
std::string PeerState::new_uuid()
{
  auto value = new_idempotency_key(); value[12] = '4'; value[16] = "89ab"[value[16] % 4];
  return value.substr(0, 8) + "-" + value.substr(8, 4) + "-" + value.substr(12, 4) + "-" + value.substr(16, 4) + "-" + value.substr(20);
}
std::string PeerState::request_sha256(const std::string &action, Json params)
{
  check_analysis_json_bounds(params, 2 * 1024 * 1024);
  if (action == "connections.push_signal") {
    params["signal_text"] = core::Sha256::hex(params.at("signal_text").get<std::string>());
  }
  return core::Sha256::hex(io::python_json_dumps(Json{{"action", action}, {"params", std::move(params)}}, true, true));
}
bool PeerState::operation_matches(const Json &value, const std::string &id, const Expected *expected)
{
  try {
    check_analysis_json_bounds(value, 2 * 1024 * 1024);
    static const std::set<std::string> keys = {"operation_id", "action", "request_sha256", "state", "connection_id", "transfer_id", "result", "error"};
    if (!value.is_object() || value.size() != keys.size() || !canonical_uuid(id) || io::get_string(value, "operation_id") != id ||
        !actions.contains(io::get_string(value, "action")) || !core::is_sha256_hex(io::get_string(value, "request_sha256"))) { return false; }
    for (auto it = value.begin(); it != value.end(); ++it) { if (!keys.contains(it.key())) { return false; } }
    for (const auto key : {"connection_id", "transfer_id"}) {
      if (!value.at(key).is_null() && (!value.at(key).is_string() || !canonical_uuid(value.at(key).get<std::string>()))) { return false; }
    }
    const auto state = io::get_string(value, "state");
    if (state != "running" && state != "completed" && state != "uncertain") { return false; }
    if (!value.at("result").is_null() && !value.at("result").is_object()) { return false; }
    const auto &error = value.at("error");
    if (!error.is_null() && (!error.is_object() || error.size() != 2 || !error.contains("code") || !error.contains("message") ||
        !error.at("code").is_string() || !error.at("message").is_string() || io::get_string(error, "code").size() > 64 || io::get_string(error, "message").size() > 256)) { return false; }
    return !expected || (io::get_string(value, "action") == expected->action && io::get_string(value, "request_sha256") == expected->request_sha256);
  }
  catch (const std::exception &) { return false; }
}
void PeerState::detach(const ViewPtr &view)
{
  if (view->pending.contains("write")) { view->uncertain = true; }
  ++view->lifetime_epoch; view->follow_until = view->next_poll = 0; cancel(view->pending);
}
void PeerState::follow_source()
{
  auto *current = store_.bridge(); const auto identity = session(current);
  const bool bridge_changed = current != client_ || identity != session_ || store_.bridge_epoch() != bridge_epoch_;
  if (!bridge_changed && store_.project_scope_epoch() == project_epoch_) { return; }
  client_ = current; session_ = identity; bridge_epoch_ = store_.bridge_epoch(); project_epoch_ = store_.project_scope_epoch(); ++epoch_;
  std::erase_if(views_, [](const auto &weak) { return weak.expired(); });
  for (const auto &weak : views_) { if (auto view = weak.lock()) {
    detach(view); ++view->selection_epoch; ++view->version;
    ++view->prepare_epoch; clear_prepared(*view); view->values.erase("snapshots"); view->values.erase("snapshot");
    if (bridge_changed) { view->connection.clear(); view->values.clear(); view->latest_operations.clear(); }
  } }
}
void PeerState::sync(const ViewPtr &) { follow_source(); }
bool PeerState::supported() const
{
  const auto hello = client_ && !session_.empty() ? client_->hello_info() : std::nullopt;
  return hello && hello->has_method("peer.info") && hello->has_method("peer.connections.open") && hello->has_method("project.peer.files.prepare");
}
void PeerState::invalidate_draft(const ViewPtr &view, const bool source)
{
  ++view->draft_epoch; ++view->version;
  if (source) { ++view->prepare_epoch; clear_prepared(*view); }
}
bool PeerState::set_connection(const ViewPtr &view, const std::string &value)
{
  follow_source();
  if (!canonical_uuid(value) || view->busy()) { return false; }
  if (value == view->connection) { return true; }
  detach(view); ++view->selection_epoch; ++view->connection_epoch; view->connection = value;
  for (const auto key : {"connections.signals", "sessions.host", "files.offer", "files.query", "files.accept"}) {
    view->values.erase(key);
  }
  ++view->version; return true;
}
bool PeerState::source_current(const ViewPtr &view) const
{
  const auto &project = store_.project(); const auto &info = project.project();
  const auto origin = view->originals.find(view->prepared_operation_id);
  return store_.bridge() == client_ && store_.bridge_epoch() == bridge_epoch_ &&
         store_.project_scope_epoch() == project_epoch_ && origin != view->originals.end() &&
         origin->second.action == "files.prepare" && origin->second.bridge_session == session_ &&
         origin->second.bridge_epoch == bridge_epoch_ &&
        origin->second.prepare_epoch == view->prepare_epoch && view->values.contains("files.prepare") &&
         view->values.at("files.prepare").is_object() &&
         info && project.ready() && project.loaded() && !project.busy() &&
         origin->second.source_handle == info->handle && origin->second.source_project == info->id &&
         origin->second.source_revision == info->revision && view->source_handle == info->handle &&
         view->source_project == info->id && view->source_revision == info->revision;
}
bool PeerState::call(const ViewPtr &view, const std::string &slot, const std::string &rpc, Json params, Apply apply,
                     const bool draft, const bool source_bound)
{
  follow_source();
  if (!supported() || view->pending.contains(slot) || !client_->hello_info()->has_method(rpc)) { return false; }
  if (slot == "write" && view->busy()) { return false; }
  if (slot == "write") { ++view->selection_epoch; cancel(view->pending); }
  const auto epoch = epoch_, lifetime = view->lifetime_epoch, selection = view->selection_epoch, source = view->draft_epoch,
             prepare = view->prepare_epoch,
             bridge_epoch = store_.bridge_epoch(), project_epoch = store_.project_scope_epoch();
  const auto request = std::make_shared<Pending>(); view->pending[slot] = request;
  const std::weak_ptr<bool> alive = alive_; const std::weak_ptr<View> weak = view;
  const std::weak_ptr<Pending> pending = request;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  request->future = client_->call(rpc, std::move(params), options);
  request->future->then([this, alive, weak, pending, epoch, lifetime, selection, source, prepare, bridge_epoch, project_epoch, slot, draft, source_bound,
                        apply = std::move(apply)](bridge::Result<Json> result) {
    const auto live = alive.lock(); const auto view = weak.lock(); const auto request = pending.lock();
    if (!live || !*live || !view || !request || store_.bridge() != client_ || store_.bridge_epoch() != bridge_epoch ||
        session(store_.bridge()) != session_ || store_.project_scope_epoch() != project_epoch || epoch_ != epoch ||
        view->lifetime_epoch != lifetime || !view->pending.contains(slot) || view->pending.at(slot) != request) { return; }
    view->pending.erase(slot);
    if (view->selection_epoch != selection || (draft && view->draft_epoch != source) ||
        (source_bound && view->prepare_epoch != prepare)) {
      if (slot == "write") { view->uncertain = true; }
      ++view->version; store_.changed(); return;
    }
    if (!result) {
      view->error = result.error().message;
      if (slot == "write") { view->uncertain = true; }
      view->follow_until = 0;
    }
    else {
      try { check_analysis_json_bounds(result.value(), 2 * 1024 * 1024); apply(*view, result.value()); view->error.clear(); }
      catch (const std::exception &) { view->error = "peer.invalid_response"; if (slot == "write") { view->uncertain = true; } view->follow_until = 0; }
    }
    ++view->version; store_.changed();
  });
  store_.changed(); return true;
}
void PeerState::accept_operation(View &view, const Json &reply)
{
  const auto &operation = reply.at("operation");
  if (operation.is_null()) { view.uncertain = true; view.follow_until = 0; return; }
  const auto id = io::get_string(operation, "operation_id"); const auto found = view.originals.find(id);
  if (id != view.operation_id || !operation_matches(operation, id, found == view.originals.end() ? nullptr : &found->second)) {
    throw std::invalid_argument("peer operation");
  }
  view.operation = operation; view.uncertain = io::get_string(operation, "state") == "uncertain";
  const auto action = io::get_string(operation, "action");
  const auto latest = view.latest_operations.find(action);
  if (io::get_string(operation, "state") == "completed" && operation.at("result").is_object() &&
      found != view.originals.end() && found->second.bridge_session == session_ && found->second.bridge_epoch == bridge_epoch_ &&
      latest != view.latest_operations.end() && latest->second == id) {
    // A historical preparation cannot become a plan for a different project/handle.
    // History stays observable, but cannot restore a result into a changed
    // form or connection (including switching away and back to the same ID).
    bool current = found->second.draft_epoch == view.draft_epoch &&
                   found->second.connection_epoch == view.connection_epoch;
    if (action == "files.prepare") {
      const auto &project = store_.project(); const auto &info = project.project();
      current = info && project.ready() && project.loaded() && !project.busy() &&
          found->second.prepare_epoch == view.prepare_epoch && found->second.source_handle == info->handle &&
          found->second.source_project == info->id && found->second.source_revision == info->revision;
      if (current) {
        view.prepared_operation_id = id; view.source_handle = found->second.source_handle;
        view.source_project = found->second.source_project; view.source_revision = found->second.source_revision;
      }
    }
    if (current) { view.values[action] = operation.at("result"); }
  }
  if (io::get_string(operation, "state") != "running") { view.follow_until = 0; }
  view.next_poll = core::monotonic_seconds() + .3;
}
bool PeerState::read(const ViewPtr &view, const std::string &method, Json params)
{
  if (!reads.contains(method)) { return false; }
  std::string key = method;
  if ((method == "files.list" || method == "files.get") && params.contains("role") && params.at("role").is_string()) { key += "." + params.at("role").get<std::string>(); }
  return call(view, key, "peer." + method, std::move(params), [key](View &v, const Json &reply) { v.values[key] = reply; });
}
bool PeerState::read_source(const ViewPtr &view, const std::string &method, Json params)
{
  follow_source();
  if ((method != "project.snapshots.list_summaries" && method != "project.snapshots.get") || !params.is_object()) { return false; }
  const auto &project = store_.project(); const auto &info = project.project();
  if (!info || !project.ready() || !project.loaded() || project.busy()) { return false; }
  const auto handle = info->handle, identity = info->id; const auto revision = info->revision;
  params["handle"] = handle;
  const bool page = method == "project.snapshots.list_summaries";
  if (page) { params["expected_revision"] = revision; }
  const auto snapshot = page ? std::string() : io::get_string(params, "snapshot_id");
  if (!page && !canonical_uuid(snapshot)) { return false; }
  const std::string key = page ? "snapshots" : "snapshot";
  return call(view, key, method, std::move(params), [this, key, page, handle, identity, revision, snapshot](View &v, const Json &reply) {
    const auto &project = store_.project(); const auto &info = project.project();
    if (!info || !project.ready() || !project.loaded() || project.busy() || info->handle != handle ||
        info->id != identity || info->revision != revision) { return; }
    if (page ? io::get_int(reply, "revision", -1) != revision :
        io::get_string(reply.at("snapshot"), "id") != snapshot) { throw std::invalid_argument("peer source response"); }
    v.values[key] = reply;
  }, false, true);
}
bool PeerState::act(const ViewPtr &view, const std::string &action, Json params)
{
  follow_source();
  const auto rpc = action == "files.prepare" ? "project.peer.files.prepare" : "peer." + action;
  if (!actions.contains(action) || !params.is_object() || view->busy() || view->originals.size() >= 128 ||
      !supported() || !client_->hello_info()->has_method(rpc)) { return false; }
  Expected expected;
  if (action == "files.prepare") {
    const auto &project = store_.project(); const auto &info = project.project();
    if (!info || !project.ready() || !project.loaded() || project.busy()) { return false; }
    params["handle"] = info->handle; params["expected_revision"] = info->revision;
    expected.source_handle = info->handle; expected.source_project = info->id;
    expected.source_revision = info->revision; expected.prepare_epoch = view->prepare_epoch;
  }
  if (!params.contains("operation_id")) { params["operation_id"] = new_uuid(); }
  if (!params.at("operation_id").is_string() || !canonical_uuid(params.at("operation_id").get<std::string>())) { return false; }
  const auto id = params.at("operation_id").get<std::string>();
  if (view->originals.contains(id)) { return false; } // Old writes are queried, never reissued.
  try { expected.action = action; expected.request_sha256 = request_sha256(action, params);
        expected.bridge_session = session_; expected.bridge_epoch = bridge_epoch_;
        expected.draft_epoch = view->draft_epoch; expected.connection_epoch = view->connection_epoch; }
  catch (const std::exception &) { view->error = "peer.invalid_params"; return false; }
  const auto previous_id = view->operation_id; const auto previous_operation = view->operation; const auto previous_uncertain = view->uncertain;
  const auto latest = view->latest_operations.find(action);
  const auto previous_latest = latest == view->latest_operations.end() ? std::string() : latest->second;
  const auto cached = view->values.find(action); const bool had_result = cached != view->values.end();
  const Json previous_result = had_result ? cached->second : Json();
  const auto admission_epoch = epoch_, previous_prepare_epoch = view->prepare_epoch;
  const auto previous_prepared = view->prepared_operation_id, previous_handle = view->source_handle, previous_project = view->source_project;
  const auto previous_revision = view->source_revision;
  if (action == "files.prepare") { ++view->prepare_epoch; expected.prepare_epoch = view->prepare_epoch; clear_prepared(*view); }
  else { view->values.erase(action); }
  // A new admitted attempt supersedes the old success even if its response is
  // unknown. Only an unissued local admission failure can restore that cache.
  view->latest_operations[action] = id;
  view->originals[id] = expected; view->operation_id = id; view->operation = nullptr; view->uncertain = true;
  const bool accepted = call(view, "write", rpc, std::move(params), [this](View &v, const Json &reply) { accept_operation(v, reply); },
                             action != "files.prepare", action == "files.prepare");
  if (accepted) { follow(view); }
  else {
    view->originals.erase(id); view->operation_id = previous_id; view->operation = previous_operation; view->uncertain = previous_uncertain;
    const auto current = view->latest_operations.find(action);
    if (current != view->latest_operations.end() && current->second == id) {
      if (previous_latest.empty()) { view->latest_operations.erase(current); }
      else { current->second = previous_latest; }
    }
    // Never undo a bridge/project invalidation discovered by call().
    if (epoch_ == admission_epoch && view->draft_epoch == expected.draft_epoch && view->connection_epoch == expected.connection_epoch) {
      if (had_result) { view->values[action] = previous_result; }
      if (action == "files.prepare") {
        view->prepare_epoch = previous_prepare_epoch; view->prepared_operation_id = previous_prepared;
        view->source_handle = previous_handle; view->source_project = previous_project; view->source_revision = previous_revision;
      }
    }
  }
  return accepted;
}
bool PeerState::check_operation(const ViewPtr &view)
{
  if (view->busy() || !canonical_uuid(view->operation_id)) { return false; }
  return call(view, "operation", "peer.operations.get", {{"operation_id", view->operation_id}},
              [this](View &v, const Json &reply) { accept_operation(v, reply); });
}
bool PeerState::select_operation(const ViewPtr &view, const Json &value)
{
  follow_source(); const auto id = io::get_string(value, "operation_id");
  if (view->busy() || !operation_matches(value, id)) { return false; }
  const auto found = view->originals.find(id);
  if (found != view->originals.end() && !operation_matches(value, id, &found->second)) { return false; }
  detach(view); ++view->selection_epoch; view->operation_id = id; view->operation = value;
  view->uncertain = io::get_string(value, "state") == "uncertain"; ++view->version; return true;
}
void PeerState::follow(const ViewPtr &view)
{
  view->follow_until = core::monotonic_seconds() + 90; view->next_poll = core::monotonic_seconds() + .3;
}
void PeerState::pump(const ViewPtr &view)
{
  follow_source(); const auto now = core::monotonic_seconds();
  if (view->follow_until <= now) { view->follow_until = 0; return; }
  if (view->busy() || view->pending.contains("operation") || now < view->next_poll) { return; }
  if (!check_operation(view)) { view->follow_until = 0; }
}
}  // namespace stk::app
