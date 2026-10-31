/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/federation_state.hh"
#include "stk/app/app_store.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/core/sha256.hh"
#include <algorithm>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
std::string session(bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
void cancel(std::map<std::string, std::shared_ptr<FederationState::Pending>> &);
bool invalidate_older_info(FederationState::View &view, const Json &fact)
{
  if (view.info.is_object() && fact.is_object() &&
      (view.info.value("owner_id", Json()) != fact.value("owner_id", Json()) ||
       io::get_int(view.info, "generation", -1) < io::get_int(fact, "generation", -1))) {
    view.info = nullptr; ++view.selection_epoch; return true;
  }
  return false;
}
bool local_prepare_rejected(const bridge::Error &error)
{
  // Only a received local preparation business refusal permits a new explicit preparation.
  // Transport, cancellation, internal and malformed-response failures retain the original plan.
  return !error.local && (error.code == bridge::ErrorCode::InvalidParams ||
      error.code == bridge::ErrorCode::Conflict || error.code == bridge::ErrorCode::NotFound);
}
}
struct FederationState::Pending { std::optional<bridge::Future<Json>> future; };
namespace {
void cancel(std::map<std::string, std::shared_ptr<FederationState::Pending>> &pending)
{
  auto old = std::move(pending); pending.clear();
  for (auto &[slot, request] : old) { if (request->future) { request->future->cancel(); } }
}
}
FederationState::View::~View() { cancel(pending); }
FederationState::FederationState(AppStore &store) : store_(store) {}
FederationState::~FederationState()
{
  *alive_ = false;
  for (const auto &weak : views_) { if (auto view = weak.lock()) { detach(view); } }
}
FederationState::ViewPtr FederationState::new_view()
{
  auto view = std::make_shared<View>(); views_.push_back(view); return view;
}
std::string FederationState::new_uuid()
{
  auto value = new_idempotency_key(); value[12] = '4'; value[16] = "89ab"[(value[16] % 4)];
  return value.substr(0, 8) + "-" + value.substr(8, 4) + "-" + value.substr(12, 4) + "-" +
         value.substr(16, 4) + "-" + value.substr(20);
}
bool FederationState::runtime_connection(const std::string_view value)
{
  return value == "local" || (value.starts_with("runtime:") && value.size() > 8);
}
bool FederationState::evaluation_passed(const Json &value)
{
  if (!value.is_object() || io::get_string(value, "state") != "passed" ||
      !value.contains("gate") || !value.at("gate").is_array() || value.at("gate").empty() ||
      io::get_string(value, "receipt_sha256").size() != 64) { return false; }
  return std::all_of(value.at("gate").begin(), value.at("gate").end(), [](const Json &gate) {
    return gate.is_object() && gate.value("passed", Json()) == true &&
           gate.value("absolute_ok", Json()) == true && gate.value("baseline_ok", Json()) == true;
  });
}
void FederationState::detach(const ViewPtr &view)
{
  if (view->pending.contains("write")) { view->uncertain = true; }
  if (view->pending.contains("prepare")) { view->plan_uncertain = true; }
  ++view->lifetime_epoch; cancel(view->pending);
}
void FederationState::follow_source()
{
  auto *current = store_.bridge(); const auto identity = session(current);
  const bool bridge_changed = current != client_ || identity != session_ || store_.bridge_epoch() != store_bridge_epoch_;
  const bool project_changed = store_.project_scope_epoch() != project_scope_epoch_;
  if (!bridge_changed && !project_changed) { return; }
  client_ = current; session_ = identity; store_bridge_epoch_ = store_.bridge_epoch();
  project_scope_epoch_ = store_.project_scope_epoch(); ++epoch_;
  std::erase_if(views_, [](const auto &weak) { return weak.expired(); });
  for (const auto &weak : views_) { if (auto view = weak.lock()) {
    detach(view); ++view->version; ++view->selection_epoch;
    // Keep drafts, frozen plan identity and unknown operation identity for explicit recovery.
    // No old handle or owner generation can authorize a write after a bridge replacement.
    if (bridge_changed) {
      view->info = nullptr; view->grants = view->audit = view->candidate = view->evaluation = view->models = nullptr;
      view->connections = Json::array();
    }
  } }
}
void FederationState::sync(const ViewPtr &) { follow_source(); }
bool FederationState::supported() const
{
  const auto hello = client_ && !session_.empty() ? client_->hello_info() : std::nullopt;
  return hello && hello->has_method("project.federation.prepare") && hello->has_method("federation.owner.info");
}
bool FederationState::source_current(const ViewPtr &view) const
{
  const auto &project = store_.project(); const auto &info = project.project();
  return project.ready() && project.loaded() && !project.busy() && info && view->source_handle == info->handle && view->source_project == info->id &&
      view->source_revision == info->revision;
}
void FederationState::invalidate_draft(const ViewPtr &view, const bool data_changed)
{
  ++view->draft_epoch; ++view->version;
  if (data_changed && !view->plan_uncertain) { view->plan = view->registration = nullptr; view->plan_id.clear(); }
}
bool FederationState::set_connection(const ViewPtr &view, const std::string &value)
{
  follow_source();
  if (!runtime_connection(value) || view->busy() || view->uncertain) { return false; }
  if (view->connection == value) { return true; }
  detach(view); ++view->selection_epoch; view->connection = value;
  view->info = view->registration = view->grants = view->audit = view->candidate = view->evaluation = view->models = view->operation = nullptr;
  view->rejection = nullptr; view->operation_id.clear(); view->operation_method.clear();
  view->operation_connection.clear(); view->operation_plan_id.clear(); view->operation_request_sha256.clear();
  view->local_operations = Json::array(); view->error.clear(); ++view->version; return true;
}
bool FederationState::call(const ViewPtr &view, const std::string &slot, const std::string &method,
                          Json params, Apply apply, const bool draft)
{
  follow_source();
  if (!supported() || view->busy() || view->pending.contains(slot) || !client_->hello_info()->has_method(method)) { return false; }
  if (slot == "write" || slot == "prepare") {
    // Reads issued before an explicit write cannot replace its fresh owner generation or result.
    ++view->selection_epoch; cancel(view->pending);
  }
  const auto epoch = epoch_, lifetime = view->lifetime_epoch, source = view->draft_epoch,
             selection = view->selection_epoch, bridge_epoch = store_.bridge_epoch(), scope = store_.project_scope_epoch();
  const auto request = std::make_shared<Pending>(); view->pending[slot] = request;
  const std::weak_ptr<View> weak = view; const std::weak_ptr<bool> alive = alive_;
  const std::weak_ptr<Pending> pending = request;
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  request->future = client_->call(method, std::move(params), options);
  request->future->then([this, alive, weak, pending, epoch, lifetime, source, selection, bridge_epoch, scope, slot,
                        apply = std::move(apply), draft](bridge::Result<Json> result) {
    const auto live = alive.lock(); if (!live || !*live) { return; }
    const auto view = weak.lock(); const auto request = pending.lock();
    if (!view || !request || store_.bridge() != client_ || store_.bridge_epoch() != bridge_epoch ||
        session(store_.bridge()) != session_ || store_.project_scope_epoch() != scope || epoch_ != epoch ||
        view->lifetime_epoch != lifetime || !view->pending.contains(slot) || view->pending.at(slot) != request) { return; }
    view->pending.erase(slot);
    if (selection != view->selection_epoch || (draft && source != view->draft_epoch)) { ++view->version; store_.changed(); return; }
    if (!result) {
      view->error = result.error().message;
      if (slot == "write") {
        view->uncertain = true;
        const auto &error = result.error();
        if (!error.local && error.code == bridge::ErrorCode::Conflict && error.data.is_object() &&
            error.data.size() == 2 && error.data.value("operation_id", Json()) == view->operation_id &&
            error.data.contains("rejection")) { accept_rejection(*view, error.data.at("rejection")); }
      }
      if (slot == "prepare") { view->plan_uncertain = !local_prepare_rejected(result.error()); }
    }
    else {
      try { view->error.clear(); apply(*view, result.value()); }
      catch (const std::exception &) {
        view->error = "federation.invalid_response";
        if (slot == "write") { view->uncertain = true; }
        if (slot == "prepare") { view->plan_uncertain = true; }
      }
    }
    ++view->version; store_.changed();
  });
  store_.changed(); return true;
}
bool FederationState::load_connections(const ViewPtr &view)
{
  return call(view, "connections", "connections.list", Json::object(), [](View &v, const Json &reply) {
    Json values = Json::array();
    for (const auto &item : reply.at("connections")) { if (runtime_connection(io::get_string(item, "id"))) { values.push_back(item); } }
    v.connections = std::move(values);
  });
}
bool FederationState::load_rows(const ViewPtr &view, const std::string &table_id, const int64_t offset)
{
  const auto &project = store_.project().project(); if (!project || !store_.project().ready() || !store_.project().loaded() || store_.project().busy() || offset < 0) { return false; }
  const auto info = *project;
  return call(view, "rows", "project.table.read", {{"handle", info.handle}, {"expected_revision", info.revision},
      {"table_id", table_id}, {"offset", offset}, {"limit", 20}}, [info, table_id](View &v, const Json &reply) {
    if (io::get_string(reply, "project_id") != info.id || io::get_int(reply, "revision", -1) != info.revision ||
        io::get_string(reply.at("table"), "id") != table_id) { throw std::invalid_argument("table"); }
    v.table = reply.at("table"); v.table_id = table_id; v.row_offset = io::get_int(reply, "offset", 0);
    v.row_total = io::get_int(reply, "total", 0); v.source_handle = info.handle; v.source_project = info.id; v.source_revision = info.revision;
  });
}
bool FederationState::prepare(const ViewPtr &view, Json params)
{
  follow_source();
  if (!source_current(view) || view->uncertain || view->plan_uncertain) { return false; }
  const auto id = io::get_string(params, "plan_id");
  const bool started = call(view, "prepare", "project.federation.prepare", std::move(params), [id](View &v, const Json &reply) {
    const auto plan = reply.at("plan");
    if (io::get_string(plan, "plan_id") != id) { throw std::invalid_argument("plan"); }
    v.plan = plan; v.plan_uncertain = false; v.registration = nullptr;
  }, true);
  if (started) { view->plan_id = id; view->plan = view->registration = nullptr; }
  return started;
}
bool FederationState::load_plan(const ViewPtr &view, const std::string &plan_id)
{
  follow_source();
  const auto &project = store_.project().project(); if (!project || !store_.project().ready()) { return false; }
  const bool started = call(view, "plan", "project.federation.get", {{"handle", project->handle}, {"plan_id", plan_id}},
      [plan_id](View &v, const Json &reply) {
        const auto plan = reply.at("plan"); if (io::get_string(plan, "plan_id") != plan_id) { throw std::invalid_argument("plan"); }
        v.plan = plan; v.plan_uncertain = false;
      });
  if (started) { view->plan_id = plan_id; view->plan = view->registration = nullptr; }
  return started;
}
bool FederationState::load_plans(const ViewPtr &view)
{
  const auto &project = store_.project().project(); if (!project || !store_.project().ready()) { return false; }
  return call(view, "plans", "project.federation.list", {{"handle", project->handle}, {"offset", 0}, {"limit", 20}},
      [](View &v, const Json &reply) { v.plans = reply.at("plans"); });
}
void FederationState::accept_operation(View &v, const Json &reply, const bool queried)
{
  if (reply.is_null()) { v.uncertain = true; v.error = "federation.not_observed"; return; }
  if (io::get_string(reply, "operation_id") != v.operation_id || io::get_string(reply, "method") != v.operation_method ||
      io::get_string(reply, "format") != "stk.federation-owner-operation/1" ||
      (!v.operation_request_sha256.empty() && io::get_string(reply, "request_sha256") != v.operation_request_sha256) ||
      (!v.operation_connection.empty() && v.operation_connection != v.connection)) { throw std::invalid_argument("operation"); }
  v.operation = reply; v.rejection = nullptr; v.uncertain = io::get_string(reply, "state") != "completed";
  if (!queried) {
    const auto generation = std::max(io::get_int(v.info, "generation", 0), io::get_int(reply, "generation", 0));
    v.info = {{"format", "stk.federation-owner-info/1"}, {"owner_id", reply.at("owner_id")}, {"generation", generation}};
  }
  else { invalidate_older_info(v, reply); }
  if (v.uncertain || !reply.contains("result")) { return; }
  const auto &result = reply.at("result");
  if (v.operation_method == "datasets.register") { v.registration = result; }
  else if (v.operation_method.starts_with("evaluations.")) { v.evaluation = result; }
  else if (v.operation_method == "models.activate" || v.operation_method == "models.admit") { v.models = nullptr; }
  else if (v.operation_method.starts_with("grants.")) { v.grants = nullptr; }
  else if (v.operation_method == "operations.recover" && result.contains("operation")) {
    const auto &original = result.at("operation");
    v.operation_id = io::get_string(original, "operation_id"); v.operation_method = io::get_string(original, "method");
    v.operation_request_sha256.clear(); v.operation_plan_id.clear();
    v.uncertain = io::get_string(original, "state") != "completed";
  }
}
bool FederationState::accept_rejection(View &v, const Json &proof, const bool historical)
{
  static const std::set<std::string> fields = {"format", "operation_id", "method", "request_sha256", "owner_id", "generation", "reason"};
  if (!proof.is_object() || proof.size() != fields.size()) { return false; }
  for (auto it = proof.begin(); it != proof.end(); ++it) { if (!fields.contains(it.key())) { return false; } }
  const auto reason = io::get_string(proof, "reason"), digest = io::get_string(proof, "request_sha256");
  if (io::get_string(proof, "format") != "stk.federation-owner-rejection/1" ||
      io::get_string(proof, "operation_id") != v.operation_id || io::get_string(proof, "method") != v.operation_method ||
      !canonical_uuid(io::get_string(proof, "owner_id")) || !core::is_sha256_hex(digest) ||
      !proof.at("generation").is_number_integer() || !io::is_safe_integer(proof.at("generation")) ||
      io::get_int(proof, "generation", -1) < 0 || (reason != "stale_owner" && reason != "invalid_request") ||
      (!v.operation_request_sha256.empty() && digest != v.operation_request_sha256) ||
      v.operation_connection != v.connection) { return false; }
  // Complete registration arrays and historical intents stay bridge-private. The bridge verifies
  // their full immutable request before delivering this closed proof; no null/4xx inference here.
  v.rejection = proof; v.operation = nullptr; v.uncertain = false; v.error = "federation.rejected";
  if (!historical) { v.info = nullptr; ++v.selection_epoch; }
  else { invalidate_older_info(v, proof); }
  return true;
}
bool FederationState::owner_write(const ViewPtr &view, const std::string &method, Json params, const std::string &rpc)
{
  follow_source();
  const auto target = rpc.empty() ? "federation.owner." + method : rpc;
  if (!supported() || !client_->hello_info()->has_method(target) || !runtime_connection(view->connection) ||
      !view->info.is_object() || view->uncertain || view->busy()) { return false; }
  view->operation_id = new_uuid(); view->operation_method = method;
  params["connection"] = view->connection; params["operation_id"] = view->operation_id;
  params["owner_id"] = view->info.at("owner_id"); params["expected_generation"] = view->info.at("generation");
  view->operation_connection = view->connection;
  view->operation_plan_id = method == "datasets.register" ? view->plan_id : std::string();
  view->operation_request_sha256.clear(); view->rejection = nullptr; view->operation = nullptr;
  if (method != "datasets.register") {
    auto original = params; original.erase("connection");
    // inputs.canonical sorts keys and preserves -0.0 and numeric types, unlike canonical_json.
    view->operation_request_sha256 = core::Sha256::hex(io::python_json_dumps(original, true, true));
  }
  return call(view, "write", target, std::move(params),
      [this](View &v, const Json &reply) { accept_operation(v, reply); });
}
bool FederationState::register_plan(const ViewPtr &view)
{
  if (!source_current(view) || !view->plan.is_object() || view->plan_uncertain || view->pending.contains("plan") ||
      io::get_string(view->plan, "plan_id") != view->plan_id) { return false; }
  const auto &project = *store_.project().project();
  if (view->plan.at("source").value("project_id", std::string()) != project.id ||
      io::get_int(view->plan.at("source"), "revision", -1) != project.revision) { return false; }
  return owner_write(view, "datasets.register", {{"handle", project.handle}, {"expected_revision", project.revision},
      {"plan_id", view->plan_id}}, "project.federation.register");
}
bool FederationState::read(const ViewPtr &view, const std::string &method, Json params)
{
  static const std::set<std::string> methods = {"info", "datasets.list", "grants.list", "audit.list", "candidates.get",
      "evaluations.get", "models.list", "operations.local"};
  if (!methods.contains(method) || !runtime_connection(view->connection)) { return false; }
  const auto expected = params;
  params["connection"] = view->connection;
  return call(view, method, "federation.owner." + method, std::move(params), [method, expected](View &v, const Json &reply) {
    if (method == "info") { v.info = reply; }
    else if (method == "grants.list") { v.grants = reply; }
    else if (method == "audit.list") { v.audit = reply; }
    else if (method == "candidates.get") {
      if (reply.value("run_id", Json()) != expected.value("run_id", Json()) || reply.value("round", Json()) != expected.value("round", Json())) { throw std::invalid_argument("candidate"); }
      if (v.candidate.is_null() || v.candidate != reply) { v.evaluation = nullptr; ++v.selection_epoch; }
      if (io::get_string(v.candidate, "spec_sha256") != io::get_string(reply, "spec_sha256")) { v.models = nullptr; }
      v.candidate = reply;
    }
    else if (method == "evaluations.get") {
      if (reply.value("evaluation_id", Json()) != expected.value("evaluation_id", Json())) { throw std::invalid_argument("evaluation"); }
      v.evaluation = reply;
    }
    else if (method == "models.list") {
      if (reply.value("spec_sha256", Json()) != expected.value("spec_sha256", Json())) { throw std::invalid_argument("models"); }
      v.models = reply;
    }
    else if (method == "operations.local") {
      v.local_operations = reply.at("operations");
      for (const auto &record : v.local_operations) {
        invalidate_older_info(v, record.value("receipt", Json()));
        invalidate_older_info(v, record.value("rejection", Json()));
      }
    }
  }, method == "candidates.get" || method == "evaluations.get");
}
bool FederationState::write(const ViewPtr &view, const std::string &method, Json request)
{
  static const std::set<std::string> methods = {"grants.approve", "grants.revoke", "evaluations.prepare", "evaluations.evaluate",
      "models.admit", "models.activate"};
  if (!methods.contains(method)) { return false; }
  if (method == "models.admit" && (!evaluation_passed(view->evaluation) ||
      request.value("evaluation_id", Json()) != view->evaluation.value("evaluation_id", Json()) ||
      request.value("receipt_sha256", Json()) != view->evaluation.value("receipt_sha256", Json()))) { return false; }
  if (method == "evaluations.evaluate" && (!view->evaluation.is_object() || io::get_string(view->evaluation, "state") != "prepared" ||
      request.value("evaluation_id", Json()) != view->evaluation.value("evaluation_id", Json()) ||
      request.value("plan_sha256", Json()) != view->evaluation.value("plan_sha256", Json()))) { return false; }
  if (method == "models.activate") {
    const auto &models = view->models;
    if (!models.is_object() || !models.contains("versions") || !models.at("versions").is_array() ||
        request.value("spec_sha256", Json()) != models.value("spec_sha256", Json()) ||
        request.value("expected_active_version", Json()) != models.value("active_version", Json()) ||
        request.value("expected_active_generation", Json()) != models.value("generation", Json()) ||
        std::none_of(models.at("versions").begin(), models.at("versions").end(), [&](const Json &version) {
          return request.value("version", Json()) == version.value("version", Json());
        })) { return false; }
  }
  return owner_write(view, method, {{"request", std::move(request)}});
}
bool FederationState::check_operation(const ViewPtr &view)
{
  if (view->operation_id.empty() || !runtime_connection(view->connection)) { return false; }
  return call(view, "operation", "federation.owner.operations.get", {{"connection", view->connection}, {"operation_id", view->operation_id}},
      [this](View &v, const Json &reply) {
        const auto &operation = reply.at("operation"), &proof = reply.at("rejection");
        if (!proof.is_null()) {
          if (!operation.is_null() || !accept_rejection(v, proof)) { throw std::invalid_argument("rejection"); }
        }
        else { accept_operation(v, operation, true); }
      });
}
bool FederationState::recover_operation(const ViewPtr &view)
{
  if (!view->uncertain || view->operation_id.empty() || view->operation_method == "operations.recover" || !view->info.is_object()) { return false; }
  const auto old = view->operation_id, method = view->operation_method; view->uncertain = false;
  if (owner_write(view, "operations.recover", {{"request", {{"operation_id", old}}}})) { return true; }
  view->operation_id = old; view->operation_method = method; view->uncertain = true; return false;
}
bool FederationState::select_operation(const ViewPtr &view, const Json &record)
{
  if (view->busy() || !record.is_object() || io::get_string(record, "connection") != view->connection ||
      (view->uncertain && io::get_string(record, "operation_id") != view->operation_id)) { return false; }
  view->operation_id = io::get_string(record, "operation_id"); view->operation_method = io::get_string(record, "method");
  view->operation_connection = view->connection; view->operation_plan_id = io::get_string(record, "plan_id");
  view->operation_request_sha256.clear(); view->rejection = nullptr;
  view->operation = record.value("receipt", Json()); view->uncertain = io::get_string(record, "state") != "completed";
  if (io::get_string(record, "state") == "rejected") {
    if (!view->operation.is_null() || !accept_rejection(*view, record.value("rejection", Json()), true)) {
      view->uncertain = true; view->error = "federation.invalid_response";
    }
  }
  else { invalidate_older_info(*view, view->operation); }
  ++view->selection_epoch; ++view->version; return !view->operation_id.empty();
}
}  // namespace stk::app
