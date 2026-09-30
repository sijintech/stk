/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_analysis_runs.hh"

#include "stk/app/app_store.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/core/paths.hh"
#include "stk/io/blob_cache.hh"
#include "stk/io/graph.hh"
#include "stk/io/payload.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
bool active(const Json &run)
{
  const auto status = io::get_string(run, "status");
  return status == "running" || status == "cancel_requested";
}
bool same_json(const Json &a, const Json &b)
{
  return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true);
}
bool bounded_run_metadata(const Json &run, const bool full)
{
  if (!run.is_object() || run.size() != (full ? 21 : 19)) { return false; }
  for (const auto *key : {"id", "project_id", "analysis_id", "analysis_name", "snapshot_id", "snapshot_sha256", "plan_sha256",
       "profile", "status", "created_at", "updated_at"}) {
    if (!run.contains(key) || !run.at(key).is_string() || run.at(key).get_ref<const std::string &>().size() > 1024) { return false; }
  }
  for (const auto *key : {"started_at", "finished_at", "cancel_requested_at", "executor_id"}) {
    if (!run.contains(key) || (!run.at(key).is_null() && (!run.at(key).is_string() ||
        run.at(key).get_ref<const std::string &>().size() > 128))) { return false; }
  }
  if (!run.contains("source_revision") || !run.at("source_revision").is_number_integer() ||
      !run.contains("budget") || !run.at("budget").is_object() || run.at("budget").size() != 2 ||
      !run.at("budget").contains("max_seconds") || !run.at("budget").contains("max_output_bytes") ||
      !run.at("budget").at("max_seconds").is_number_integer() || !run.at("budget").at("max_output_bytes").is_number_integer() ||
      !run.contains("error") || !run.contains("result") ||
      (full && (!run.contains("document") || !run.contains("bindings")))) { return false; }
  const auto &error = run.at("error");
  if (!error.is_null() && (!error.is_object() || error.size() != 2 || !error.contains("code") || !error.contains("message") ||
      !error.at("code").is_string() || !error.at("message").is_string() ||
      error.at("code").get_ref<const std::string &>().size() > 128 || error.at("message").get_ref<const std::string &>().size() > 4096)) { return false; }
  const auto &receipt = run.at("result");
  if (!receipt.is_null()) {
    if (!receipt.is_object() || receipt.size() != 7) { return false; }
    for (const auto *key : {"directory", "manifest_sha256", "graph_hash"}) {
      if (!receipt.contains(key) || !receipt.at(key).is_string() || receipt.at(key).get_ref<const std::string &>().size() > 1024) { return false; }
    }
    for (const auto *key : {"has_payload", "has_errors"}) { if (!receipt.contains(key) || !receipt.at(key).is_boolean()) { return false; } }
    for (const auto *key : {"output_count", "size_bytes"}) { if (!receipt.contains(key) || !receipt.at(key).is_number_integer()) { return false; } }
  }
  return true;
}
bool valid_run(const Json &run, const std::string &project, const bool full)
{
  if (!bounded_run_metadata(run, full) || io::get_string(run, "id").empty() || io::get_string(run, "project_id") != project ||
      io::get_int(run, "source_revision", -1) < 0 || io::get_string(run, "analysis_id").empty() ||
      io::get_string(run, "snapshot_id").empty() || io::get_string(run, "plan_sha256").size() != 64 ||
      !run.contains("result") || !run.contains("error")) { return false; }
  const auto status = io::get_string(run, "status");
  if (status != "prepared" && status != "running" && status != "cancel_requested" &&
      status != "succeeded" && status != "failed" && status != "cancelled" && status != "unknown") { return false; }
  if (!run.at("error").is_null() && (!run.at("error").is_object() ||
      !run.at("error").contains("message") || !run.at("error").at("message").is_string())) { return false; }
  const auto &result = run.at("result");
  if (!result.is_null() && (!result.is_object() || !result.contains("has_payload") ||
      !result.at("has_payload").is_boolean() || !result.contains("has_errors") ||
      !result.at("has_errors").is_boolean() || io::get_string(result, "manifest_sha256").size() != 64)) { return false; }
  if (status == "succeeded" && (result.is_null() || result.at("has_errors").get<bool>())) { return false; }
  if (full) {
    if (!run.contains("document") || !run.at("document").is_object() ||
        io::get_string(run.at("document"), "format") != "stk.analysis-document/1" ||
        !run.at("document").contains("graph") || !run.at("document").at("graph").is_object() ||
        !run.at("document").contains("parameters") || !run.at("document").at("parameters").is_object() ||
        !run.at("document").contains("outputs") || !run.at("document").at("outputs").is_array() ||
        !run.contains("bindings") || !run.at("bindings").is_object()) { return false; }
  }
  return true;
}
}  // namespace

ProjectAnalysisRuns::ProjectAnalysisRuns(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectAnalysisRuns::~ProjectAnalysisRuns()
{
  if (uncertain_) { store_.log("Analysis run reply unavailable; inspect run " + pending_id_); }
  *alive_ = false;
  if (future_) { future_->cancel(); }
}
void ProjectAnalysisRuns::changed() { ++version_; store_.changed(); }
const Json &ProjectAnalysisRuns::result() const
{
  static const Json empty;
  return result_inspection_ ? result_inspection_->result() : empty;
}
void ProjectAnalysisRuns::clear_result()
{
  result_inspection_.reset(); blob_dir_.clear(); ++result_generation_;
}
void ProjectAnalysisRuns::reset()
{
  ++epoch_; ++selection_generation_;
  busy_ = uncertain_ = following_ = clock_seen_ = false;
  error_.clear(); pending_id_.clear(); blob_dir_.clear();
  page_ = run_ = nullptr; snapshots_ = Json::array(); clear_result();
  reusable_inputs_.reset(); ++reusable_inputs_generation_;
  omitted_snapshots_ = 0; offset_ = 0; now_ = due_ = wake_scheduled = 0; deadline_ = -1;
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}
void ProjectAnalysisRuns::sync()
{
  project_.sync();
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    if (uncertain_) { store_.log("Analysis run reply unavailable; inspect run " + pending_id_); }
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
}
bool ProjectAnalysisRuns::supported() const
{
  if (!client_ || session_.empty() || !project_.ready() || !project_.loaded() || handle_.empty() ||
      project_.project()->handle != handle_ || project_.project()->format_version < 9) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"project.analysis_runs.prepare", "project.analysis_runs.get", "project.analysis_runs.list",
       "project.analysis_runs.start", "project.analysis_runs.cancel", "project.analysis_runs.recover",
       "project.analysis_runs.result", "project.snapshots.list"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}
bool ProjectAnalysisRuns::reusable_inputs_supported() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return supported() && hello && hello->has_method("project.snapshots.get");
}

bool ProjectAnalysisRuns::call(const std::string &method, Json params,
                              std::function<void(const Json &)> done,
                              std::function<void(const bridge::Error &)> failed)
{
  sync();
  if (!supported() || busy_ || project_.busy()) { return false; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  params["handle"] = handle_;
  busy_ = true; error_.clear();
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call(method, params, options);
  future_->then([this, weak, epoch, done = std::move(done), failed = std::move(failed)](bridge::Result<Json> result) {
    const auto live = weak.lock();
    if (!live || !*live) { return; }
    sync();
    if (epoch != epoch_) { return; }
    busy_ = false; future_.reset();
    if (!result) {
      error_ = result.error().describe(); following_ = false;
      if (failed) { failed(result.error()); }
      if (result.error().code == bridge::ErrorCode::Conflict) { project_.refresh(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &error) {
        error_ = error.what(); following_ = false;
        if (failed) { failed(bridge::Error::make(bridge::ErrorCode::InternalError, error_)); }
      }
    }
    changed();
  });
  changed();
  return true;
}
void ProjectAnalysisRuns::accept_run(const Json &value, const std::string &id)
{
  if (!project_.project() || !valid_run(value, project_.project()->id, true) || value.at("id") != id) {
    throw std::runtime_error("Invalid analysis run response");
  }
  if (!run_.is_null() && run_.at("id") == id && run_.at("plan_sha256") != value.at("plan_sha256")) {
    throw std::runtime_error("The frozen analysis run identity changed");
  }
  if (run_.is_null() || run_.at("id") != id) {
    ++selection_generation_; clear_result();
    reusable_inputs_.reset(); ++reusable_inputs_generation_;
  }
  else if (!same_json(run_.at("result"), value.at("result"))) { clear_result(); }
  run_ = value;
  if (!page_.is_null()) {
    for (auto &item : page_.at("runs")) {
      if (item.at("id") == id) { item = value; item.erase("document"); item.erase("bindings"); break; }
    }
  }
  if (!active(run_)) { following_ = false; wake_scheduled = 0; }
  due_ = now_ + 1;
}
void ProjectAnalysisRuns::follow()
{
  following_ = active(run_);
  deadline_ = clock_seen_ ? now_ + 90 : -1;
  due_ = now_ + 1;
}
bool ProjectAnalysisRuns::load_snapshots()
{
  return call("project.snapshots.list", Json::object(), [this](const Json &result) {
    const auto &values = result.at("snapshots");
    if (!values.is_array()) { throw std::runtime_error("Invalid input snapshot list"); }
    Json kept = Json::array();
    for (const auto &snapshot : values) {
      if (!snapshot.is_object() || io::get_string(snapshot, "id").empty() ||
          !snapshot.contains("manifest") || !snapshot.at("manifest").is_object() ||
          !snapshot.at("manifest").contains("files") || !snapshot.at("manifest").at("files").is_array() ||
          io::get_string(snapshot.at("manifest"), "project_id") != project_.project()->id) {
        throw std::runtime_error("Invalid input snapshot manifest");
      }
      if (kept.size() < 100) { kept.push_back(snapshot); }
    }
    omitted_snapshots_ = values.size() - kept.size(); snapshots_ = std::move(kept);
  });
}
bool ProjectAnalysisRuns::load_page(const int64_t offset)
{
  if (offset < 0) { return false; }
  return call("project.analysis_runs.list", {{"offset", offset}, {"limit", 50}}, [this, offset](const Json &result) {
    const auto &rows = result.at("runs"), &next = result.at("next_offset");
    if (!rows.is_array() || rows.size() > 50 ||
        (!next.is_null() && (!next.is_number_integer() || next.get<int64_t>() <= offset))) {
      throw std::runtime_error("Invalid analysis run list");
    }
    for (const auto &row : rows) {
      if (!valid_run(row, project_.project()->id, false)) { throw std::runtime_error("Invalid analysis run summary"); }
    }
    page_ = result; offset_ = offset;
  });
}
bool ProjectAnalysisRuns::read(const std::string &id, const bool begin_following)
{
  if (id.empty()) { return false; }
  return call("project.analysis_runs.get", {{"run_id", id}}, [this, id, begin_following](const Json &result) {
    accept_run(result.at("run"), id);
    if (pending_id_ == id) { uncertain_ = false; pending_id_.clear(); }
    if (begin_following) { follow(); }
  }, [this, id](const bridge::Error &error) {
    if (error.code == bridge::ErrorCode::NotFound && !error.local && pending_id_ == id) {
      uncertain_ = false; pending_id_.clear();
    }
  });
}
bool ProjectAnalysisRuns::load(const std::string &id)
{
  const bool accepted = read(id, true);
  if (accepted) {
    ++selection_generation_; following_ = false;
    reusable_inputs_.reset(); ++reusable_inputs_generation_;
  }
  return accepted;
}
bool ProjectAnalysisRuns::prepare(const std::string &analysis_id, const int64_t revision,
                                 const std::string &snapshot_id, const Json &bindings)
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain_ || revision < 0 ||
      project_.project()->revision != revision || analysis_id.empty() || snapshot_id.empty() || !bindings.is_object()) { return false; }
  const auto hex = new_idempotency_key();
  const auto id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" +
      hex.substr(16, 4) + "-" + hex.substr(20);
  pending_id_ = id; uncertain_ = true;
  const bool accepted = call("project.analysis_runs.prepare", {{"run_id", id}, {"analysis_id", analysis_id},
      {"snapshot_id", snapshot_id}, {"bindings", bindings}, {"expected_revision", revision}},
      [this, id, analysis_id, snapshot_id, revision](const Json &result) {
    const auto &run = result.at("run");
    if (io::get_string(run, "analysis_id") != analysis_id || io::get_string(run, "snapshot_id") != snapshot_id ||
        io::get_int(run, "source_revision", -1) != revision || io::get_string(run, "status") != "prepared") {
      throw std::runtime_error("Analysis preparation returned a different frozen source");
    }
    accept_run(run, id); uncertain_ = false; pending_id_.clear(); following_ = false;
  }, [this](const bridge::Error &error) {
    if (!error.local && (error.code == bridge::ErrorCode::InvalidParams || error.code == bridge::ErrorCode::Conflict ||
        error.code == bridge::ErrorCode::NotFound || error.code == bridge::ErrorCode::Unsupported)) {
      uncertain_ = false; pending_id_.clear();
    }
  });
  if (accepted) { ++selection_generation_; reusable_inputs_.reset(); ++reusable_inputs_generation_; }
  else { uncertain_ = false; pending_id_.clear(); }
  return accepted;
}
bool ProjectAnalysisRuns::command(const std::string &name)
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain_ || run_.is_null()) { return false; }
  const auto status = io::get_string(run_, "status");
  if ((name == "start" && status != "prepared") ||
      (name == "cancel" && status != "prepared" && !active(run_)) ||
      (name == "recover" && !active(run_))) { return false; }
  const auto id = run_.at("id").get<std::string>();
  uncertain_ = true; pending_id_ = id;
  const bool accepted = call("project.analysis_runs." + name, {{"run_id", id}}, [this, id](const Json &result) {
    accept_run(result.at("run"), id); uncertain_ = false; pending_id_.clear(); follow();
  }, [this](const bridge::Error &error) {
    if (!error.local && (error.code == bridge::ErrorCode::Busy || error.code == bridge::ErrorCode::InvalidParams ||
        error.code == bridge::ErrorCode::Conflict || error.code == bridge::ErrorCode::NotFound ||
        error.code == bridge::ErrorCode::Unsupported)) {
      uncertain_ = false; pending_id_.clear();
    }
  });
  if (!accepted) { uncertain_ = false; pending_id_.clear(); }
  return accepted;
}
bool ProjectAnalysisRuns::start() { return command("start"); }
bool ProjectAnalysisRuns::cancel() { return command("cancel"); }
bool ProjectAnalysisRuns::recover() { return command("recover"); }
bool ProjectAnalysisRuns::check_pending() { return !pending_id_.empty() && load(pending_id_); }
bool ProjectAnalysisRuns::read_reusable_inputs()
{
  sync();
  if (!reusable_inputs_supported() || busy_ || project_.busy() || uncertain_ || run_.is_null()) { return false; }
  AnalysisInputReusePlan plan;
  try { plan = analysis_input_reuse_plan(run_, project_.project()->id); }
  catch (const std::exception &error) { error_ = error.what(); changed(); return false; }
  const auto selection = selection_generation_;
  const auto snapshot = plan.snapshot_id;
  return call("project.snapshots.get", {{"snapshot_id", snapshot}}, [this, plan = std::move(plan), selection](const Json &response) {
    if (selection_generation_ != selection || run_.is_null() || io::get_string(run_, "id") != plan.run_id ||
        io::get_string(run_, "plan_sha256") != plan.plan_sha256) { return; }
    auto reused = analysis_reused_inputs(plan, response.at("snapshot"));
    reusable_inputs_ = std::move(reused); ++reusable_inputs_generation_;
  });
}

bool ProjectAnalysisRuns::read_result()
{
  sync();
  if (run_.is_null() || run_.at("result").is_null()) { return false; }
  const auto id = run_.at("id").get<std::string>();
  const auto selection = selection_generation_;
  return call("project.analysis_runs.result", {{"run_id", id}}, [this, id, selection](const Json &response) {
    if (selection != selection_generation_) { return; }
    const auto &run = response.at("run"), &document = response.at("result");
    if (!project_.project() || !valid_run(run, project_.project()->id, true) ||
        io::get_string(run, "id") != id || run_.is_null() || io::get_string(run_, "id") != id ||
        !run.at("result").is_object()) { throw std::runtime_error("Invalid archived analysis run"); }
    // Bound both immutable plans before comparing or hashing their recursive values.
    check_analysis_document_bounds(run.at("document"));
    check_analysis_document_bounds(run_.at("document"));
    analysis_input_reuse_plan(run, project_.project()->id);
    analysis_input_reuse_plan(run_, project_.project()->id);
    for (const auto *key : {"id", "project_id", "created_at", "analysis_id", "analysis_name", "snapshot_id", "snapshot_sha256", "profile", "plan_sha256"}) {
      for (const auto *candidate : {&run, static_cast<const Json *>(&run_)}) {
        if (!candidate->contains(key) || !candidate->at(key).is_string() || candidate->at(key).get_ref<const std::string &>().size() > 1024) {
          throw std::runtime_error("Invalid frozen analysis metadata");
        }
      }
    }
    for (const auto *candidate : {&run, static_cast<const Json *>(&run_)}) {
      const auto &budget = candidate->at("budget");
      if (!budget.is_object() || budget.size() != 2 || !budget.contains("max_seconds") || !budget.contains("max_output_bytes") ||
          !budget.at("max_seconds").is_number_integer() || !budget.at("max_output_bytes").is_number_integer() ||
          budget.at("max_seconds") != 300 || budget.at("max_output_bytes") != 268435456) {
        throw std::runtime_error("Invalid frozen analysis budget");
      }
    }
    for (const auto *key : {"id", "project_id", "source_revision", "created_at", "analysis_id", "analysis_name",
         "document", "snapshot_id", "snapshot_sha256", "bindings", "profile", "budget", "plan_sha256"}) {
      if (!same_json(run.at(key), run_.at(key))) { throw std::runtime_error("The frozen analysis run identity changed"); }
    }
    auto inspector = AnalysisResultInspection::from_result(run.at("document").at("outputs"), document);
    const auto &receipt = run.at("result");
    auto blob_dir = response.at("blob_dir").get<std::string>();
    const auto graph_hash = io::graph_hash(run.at("document").at("graph"));
    const bool has_errors = document.contains("errors") && !document.at("errors").is_null() && !document.at("errors").empty();
    bool has_payload = false;
    for (const auto &output : inspector->outputs()) { has_payload |= output.delivered && output.delivery_type == "payload"; }
    if (!core::path_from_utf8(blob_dir).is_absolute() ||
        io::get_string(document, "graph_hash") != graph_hash ||
        io::get_string(document, "graph_sha256") != graph_hash.substr(7) ||
        io::get_string(receipt, "graph_hash") != graph_hash.substr(7) ||
        io::get_string(receipt, "manifest_sha256") != inspector->encoded_sha256() ||
        io::get_int(receipt, "output_count", -1) != int64_t(document.at("outputs").size()) ||
        io::get_int(receipt, "size_bytes", -1) < int64_t(inspector->encoded_bytes()) ||
        receipt.at("has_payload") != has_payload || receipt.at("has_errors") != has_errors) {
      throw std::runtime_error("The archived result does not match its verified receipt");
    }
    // All fallible semantic validation precedes publication. A failed refresh preserves the
    // previously verified run/result/blob/model bundle; no stale JSON can acquire a new receipt.
    accept_run(run, id);
    result_inspection_ = std::move(inspector); blob_dir_ = std::move(blob_dir); ++result_generation_;
  });
}
std::vector<std::string> ProjectAnalysisRuns::payload_outputs() const
{
  std::vector<std::string> outputs;
  if (!result().is_object()) { return outputs; }
  for (auto it = result().at("outputs").begin(); it != result().at("outputs").end(); ++it) {
    if (io::get_string(it.value(), "type") == "payload" && it.value().contains("manifest") &&
        it.value().at("manifest").is_object()) { outputs.push_back(it.key()); }
  }
  return outputs;
}
std::shared_ptr<const io::Payload> ProjectAnalysisRuns::decode_payload(const std::string &output)
{
  sync();
  if (!supported() || busy_ || result().is_null() || blob_dir_.empty() || output.empty()) { return nullptr; }
  try {
    const auto &selected = result().at("outputs").at(output);
    if (io::get_string(selected, "type") != "payload") { throw std::runtime_error("Select a payload output"); }
    const io::BlobCache blobs(core::path_from_utf8(blob_dir_));
    return std::make_shared<const io::Payload>(io::decode_manifest(selected.at("manifest"), blobs.provider(false)));
  }
  catch (const std::exception &error) { error_ = error.what(); changed(); return nullptr; }
}
double ProjectAnalysisRuns::pump(const double now_seconds)
{
  const double never = std::numeric_limits<double>::infinity();
  if (!std::isfinite(now_seconds)) { return never; }
  sync();
  now_ = now_seconds;
  if (!clock_seen_) { clock_seen_ = true; due_ = now_ + 1; }
  if (!supported() || run_.is_null() || !following_) { return never; }
  if (deadline_ < 0) { deadline_ = now_ + 90; }
  if (now_ >= deadline_ || !active(run_)) { following_ = false; changed(); return never; }
  if (busy_ || project_.busy() || uncertain_) { return never; }
  if (now_ >= due_) { read(run_.at("id").get<std::string>(), false); return never; }
  return std::min(due_, deadline_);
}
}  // namespace stk::app
