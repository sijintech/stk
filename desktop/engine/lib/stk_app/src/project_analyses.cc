/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_analyses.hh"

#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"

#include <stdexcept>
#include <limits>

namespace stk::app {
using io::Json;
namespace {
bool same_json(const Json &a, const Json &b)
{
  return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true);
}
bool valid_summary(const Json &value)
{
  if (!value.is_object() || !value.contains("id") || !value.at("id").is_string() ||
      !value.contains("name") || !(value.at("name").is_null() || value.at("name").is_string()) ||
      !value.contains("format") || !(value.at("format").is_null() || value.at("format").is_string()) ||
      !value.contains("error") || !value.at("error").is_string()) { return false; }
  const auto state = io::get_string(value, "state");
  return state == "readable" || state == "invalid" || state == "unsupported";
}
}  // namespace

ProjectAnalyses::ProjectAnalyses(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectAnalyses::~ProjectAnalyses()
{
  if (uncertain_) { store_.log("Analysis save reply unavailable; inspect document " + pending_id()); }
  *alive_ = false;
  if (future_) { future_->cancel(); }
}

void ProjectAnalyses::changed() { ++version_; store_.changed(); }

void ProjectAnalyses::reset()
{
  ++epoch_; ++selected_version_;
  busy_ = uncertain_ = false;
  selected_revision_ = -1;
  page_ = selected_ = pending_ = nullptr;
  error_.clear(); notice_.clear();
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}

void ProjectAnalyses::sync()
{
  project_.sync();
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    // Retain the recovery identity in the local log even when this UI opening becomes invalid.
    if (uncertain_) { store_.log("Analysis save reply unavailable; inspect document " + pending_id()); }
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
}

bool ProjectAnalyses::supported() const
{
  if (!client_ || !project_.ready() || !project_.loaded() || handle_.empty() ||
      project_.project()->handle != handle_ || project_.project()->format_version < 3) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"project.analyses.create", "project.analyses.update", "project.analyses.get", "project.analyses.list"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectAnalyses::stale() const
{
  return !selected_.is_null() && (!project_.project() || project_.project()->handle != handle_ ||
      project_.project()->revision != selected_revision_);
}

bool ProjectAnalyses::page_stale() const
{
  return !page_.is_null() && (!project_.project() || project_.project()->handle != handle_ ||
      project_.project()->revision != io::get_int(page_, "revision", -1));
}

std::string ProjectAnalyses::pending_id() const { return io::get_string(pending_, "analysis_id"); }

bool ProjectAnalyses::call(const std::string &method, Json params,
                           std::function<void(const Json &)> done,
                           std::function<void(const bridge::Error &)> failed)
{
  sync();
  if (!supported() || busy_ || project_.busy()) { return false; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  params["handle"] = handle_;
  busy_ = true; error_.clear(); notice_.clear();
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call(method, params, options);
  future_->then([this, weak, epoch, done = std::move(done), failed = std::move(failed)](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_) { return; }
    busy_ = false; future_.reset();
    if (!result) {
      error_ = result.error().describe();
      if (failed) { failed(result.error()); }
      // External writers do not necessarily emit an event on this bridge.
      if (result.error().code == bridge::ErrorCode::Conflict) { project_.refresh(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &error) {
        error_ = error.what();
        if (failed) { failed(bridge::Error::make(bridge::ErrorCode::InternalError, error_)); }
      }
    }
    changed();
  });
  changed();
  return true;
}

bool ProjectAnalyses::load_page(const int64_t offset)
{
  if (offset < 0) { return false; }
  return call("project.analyses.list", {{"offset", offset}, {"limit", 50}}, [this, offset](const Json &result) {
    if (!result.is_object() || io::get_int(result, "revision", -1) < 0 ||
        io::get_int(result, "offset", -1) != offset || io::get_int(result, "total", -1) < 0 ||
        !result.contains("compatible") || !result.at("compatible").is_boolean() ||
        !result.contains("analyses") || !result.at("analyses").is_array() || result.at("analyses").size() > 50) {
      throw std::runtime_error("Invalid analysis document list response");
    }
    for (const auto &analysis : result.at("analyses")) {
      if (!valid_summary(analysis)) { throw std::runtime_error("Invalid analysis document summary"); }
    }
    page_ = result;
    if (project_.project() && result.at("revision") != project_.project()->revision) { project_.refresh(); }
  });
}

void ProjectAnalyses::accept_read(const Json &response, const std::string &id)
{
  if (!response.is_object() || io::get_int(response, "revision", -1) < 0 ||
      !response.contains("analysis") || !valid_summary(response.at("analysis")) ||
      response.at("analysis").at("id") != id || !response.at("analysis").contains("document")) {
    throw std::runtime_error("Invalid analysis document response");
  }
  const auto &analysis = response.at("analysis");
  if ((analysis.at("state") == "readable") != analysis.at("document").is_object()) {
    throw std::runtime_error("Analysis document readability does not match its definition");
  }
  selected_ = analysis;
  selected_revision_ = response.at("revision").get<int64_t>();
  ++selected_version_;
  if (project_.project() && selected_revision_ != project_.project()->revision) { project_.refresh(); }
}

bool ProjectAnalyses::load(const std::string &id)
{
  if (id.empty()) { return false; }
  return call("project.analyses.get", {{"analysis_id", id}}, [this, id](const Json &result) { accept_read(result, id); });
}

bool ProjectAnalyses::write(const std::string &method, const std::string &id, const std::string &name,
                            const Json &document, const int64_t revision)
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain_ || revision < 0 ||
      revision == std::numeric_limits<int64_t>::max()) { return false; }
  const Json params = {{"analysis_id", id}, {"name", name}, {"document", document}, {"expected_revision", revision}};
  pending_ = params;
  // From dispatch until a validated receipt or definite server rejection, this identity may exist.
  uncertain_ = true;
  const bool accepted = call(method, params, [this, params](const Json &result) {
    if (!result.is_object() || io::get_int(result, "revision", -1) != params.at("expected_revision").get<int64_t>() + 1 ||
        io::get_string(result, "record_id") != params.at("analysis_id").get<std::string>()) {
      throw std::runtime_error("Invalid analysis save receipt; inspect its existing identity before saving again");
    }
    selected_ = {{"id", params.at("analysis_id")}, {"name", params.at("name")}, {"format", "stk.analysis-document/1"},
        {"state", "readable"}, {"error", ""}, {"document", params.at("document")}};
    selected_revision_ = result.at("revision").get<int64_t>(); ++selected_version_;
    uncertain_ = false; pending_ = nullptr; page_ = nullptr;
    notice_ = "analysis_documents.saved";
    project_.refresh();
  }, [this](const bridge::Error &error) {
    if (!error.local && (error.code == bridge::ErrorCode::InvalidParams || error.code == bridge::ErrorCode::Conflict ||
        error.code == bridge::ErrorCode::NotFound || error.code == bridge::ErrorCode::Unsupported)) {
      uncertain_ = false; pending_ = nullptr;
    }
    else { store_.log("Analysis save reply unavailable; inspect document " + pending_id()); }
  });
  if (!accepted) { uncertain_ = false; pending_ = nullptr; }
  return accepted;
}

bool ProjectAnalyses::save_new(const std::string &name, const Json &document)
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain_) { return false; }
  const auto hex = new_idempotency_key();
  const auto id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" +
      hex.substr(16, 4) + "-" + hex.substr(20);
  return write("project.analyses.create", id, name, document, project_.project()->revision);
}

bool ProjectAnalyses::rename(const std::string &name)
{
  sync();
  if (selected_.is_null() || io::get_string(selected_, "state") != "readable" || stale()) { return false; }
  return write("project.analyses.update", selected_.at("id").get<std::string>(), name,
               selected_.at("document"), selected_revision_);
}

bool ProjectAnalyses::replace_parameters(const Json &parameters, const uint64_t expected_selected_version)
{
  sync();
  if (!parameters.is_object() || selected_version_ != expected_selected_version || selected_.is_null() ||
      io::get_string(selected_, "state") != "readable" || stale()) { return false; }
  auto document = selected_.at("document");
  document["parameters"] = parameters;
  return write("project.analyses.update", selected_.at("id").get<std::string>(),
               selected_.at("name").get<std::string>(), document, selected_revision_);
}

bool ProjectAnalyses::check_pending()
{
  sync();
  if (!uncertain_ || pending_.is_null()) { return false; }
  const auto pending = pending_;
  const auto id = pending.at("analysis_id").get<std::string>();
  return call("project.analyses.get", {{"analysis_id", id}}, [this, pending, id](const Json &result) {
    accept_read(result, id);
    const bool matches = selected_.at("name") == pending.at("name") &&
        same_json(selected_.at("document"), pending.at("document"));
    // This is a current observation, not a recovered original transaction receipt.
    uncertain_ = false; pending_ = nullptr; page_ = nullptr;
    notice_ = matches ? "analysis_documents.recovered" : "analysis_documents.recovered_changed";
    project_.refresh();
  }, [this](const bridge::Error &error) {
    if (!error.local && error.code == bridge::ErrorCode::NotFound) {
      uncertain_ = false; pending_ = nullptr;
      notice_ = "analysis_documents.not_found";
      project_.refresh();
    }
  });
}
}  // namespace stk::app
