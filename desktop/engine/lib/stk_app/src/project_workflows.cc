/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_workflows.hh"

#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/workflow_draft.hh"
#include "stk/app/project_state.hh"

#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
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

ProjectWorkflows::ProjectWorkflows(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectWorkflows::~ProjectWorkflows()
{
  *alive_ = false;
  if (future_) { future_->cancel(); }
  if (check_future_) { check_future_->cancel(); }
  if (compilation_future_) { compilation_future_->cancel(); }
}

void ProjectWorkflows::changed() { ++version_; store_.changed(); }

void ProjectWorkflows::reset()
{
  ++epoch_; ++selected_version_;
  busy_ = uncertain_ = false;
  selected_revision_ = -1;
  page_ = selected_ = validation_ = choices_ = runs_ = run_ = stale_ = nullptr; ++run_version_;
  error_.clear(); notice_.clear();
  candidate_.reset();
  clear_compilation();
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  auto check = std::move(check_future_); check_future_.reset();
  if (check) { check->cancel(); }
  changed();
}

void ProjectWorkflows::sync()
{
  project_.sync();
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const std::string session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || handle != handle_) {
    client_ = client; session_ = session; handle_ = handle;
    reset();
  }
}

bool ProjectWorkflows::supported() const
{
  if (!client_ || !project_.ready() || !project_.loaded() || handle_.empty() ||
      project_.project()->handle != handle_ || project_.project()->format_version < 3) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"project.workflows.get", "project.workflows.list", "project.workflows.validate"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

bool ProjectWorkflows::stale() const
{
  if (selected_.is_null()) { return false; }
  if (!project_.project() || project_.project()->handle != handle_) { return true; }
  const auto revision = project_.project()->revision;
  return revision != selected_revision_ ||
      (!validation_.is_null() && io::get_int(validation_, "revision", -1) != revision);
}

bool ProjectWorkflows::page_stale() const
{
  return !page_.is_null() && (!project_.project() || project_.project()->handle != handle_ ||
      project_.project()->revision != io::get_int(page_, "revision", -1));
}

bool ProjectWorkflows::call(const std::string &method, Json params, std::function<void(const Json &)> done,
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
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_) { return; }
    busy_ = false; future_.reset();
    if (!result) {
      error_ = result.error().describe();
      if (failed) { failed(result.error()); }
      if (result.error().code == bridge::ErrorCode::Conflict) { project_.refresh(); }
    }
    else {
      try { done(result.value()); }
      catch (const std::exception &error) { error_ = error.what(); }
    }
    changed();
  });
  changed();
  return true;
}

bool ProjectWorkflows::load_page(const int64_t offset)
{
  if (offset < 0) { return false; }
  Json params = {{"offset", offset}, {"limit", 50}};
  if (list_archived_) { params["archived"] = *list_archived_; }
  return call("project.workflows.list", std::move(params), [this, offset](const Json &result) {
    if (!result.is_object() || io::get_int(result, "revision", -1) < 0 ||
        io::get_int(result, "offset", -1) != offset || io::get_int(result, "total", -1) < 0 ||
        !result.contains("workflows") || !result.at("workflows").is_array() || result.at("workflows").size() > 50) {
      throw std::runtime_error("Invalid workflow list response");
    }
    for (const auto &workflow : result.at("workflows")) {
      if (!valid_summary(workflow)) { throw std::runtime_error("Invalid workflow summary"); }
    }
    page_ = result;
    if (project_.project() && result.at("revision") != project_.project()->revision) { project_.refresh(); }
  });
}

bool ProjectWorkflows::load(const std::string &id)
{
  if (id.empty()) { return false; }
  sync();
  if (!supported() || busy_ || project_.busy()) { return false; }
  if (io::get_string(selected_, "id") != id) { clear_compilation(); }
  return call("project.workflows.get", {{"workflow_id", id}}, [this, id](const Json &response) {
    if (!response.is_object() || io::get_int(response, "revision", -1) < 0 || !response.contains("workflow") ||
        !valid_summary(response.at("workflow")) || response.at("workflow").at("id") != id ||
        !response.at("workflow").contains("document") ||
        (response.at("workflow").at("state") == "readable") != response.at("workflow").at("document").is_object()) {
      throw std::runtime_error("Invalid workflow response");
    }
    if (io::get_string(selected_, "id") != id) { runs_ = run_ = stale_ = nullptr; clear_compilation(); ++run_version_; }  // another workflow's runs
    selected_ = response.at("workflow");
    selected_revision_ = response.at("revision").get<int64_t>();
    validation_ = nullptr; uncertain_ = false;
    ++selected_version_;
    validate_selected();
  });
}

bool ProjectWorkflows::validate_selected()
{
  if (selected_.is_null() || !validation_.is_null() || io::get_string(selected_, "state") != "readable") { return false; }
  const auto id = io::get_string(selected_, "id");
  const auto document = selected_.at("document");
  const auto epoch = epoch_;
  // The check describes exactly the document shown; a newer read replaces both.
  return call("project.workflows.validate", {{"document", document}}, [this, id, epoch, document](const Json &result) {
    if (epoch != epoch_ || io::get_string(selected_, "id") != id || selected_.at("document") != document) { return; }
    if (!result.is_object() || io::get_int(result, "revision", -1) < 0 || !result.contains("ok") ||
        !result.at("ok").is_boolean() || !result.contains("issues") || !result.at("issues").is_array() ||
        !result.contains("steps") || !result.at("steps").is_array() ||
        result.at("steps").size() != document.at("steps").size()) {
      throw std::runtime_error("Invalid workflow validation response");
    }
    validation_ = result;
    ++selected_version_;
  });
}

bool ProjectWorkflows::reload()
{
  sync();
  if (selected_.is_null()) { return load_page(page_.is_null() ? 0 : io::get_int(page_, "offset", 0)); }
  return load(io::get_string(selected_, "id"));
}
void ProjectWorkflows::clear_selection()
{
  selected_ = validation_ = runs_ = run_ = stale_ = nullptr; selected_revision_ = -1; ++run_version_;
  candidate_.reset(); page_ = nullptr;
  clear_compilation();
  ++selected_version_;
  changed();
}

bool ProjectWorkflows::load_choices()
{
  return call("project.workflows.choices", Json::object(), [this](const Json &result) {
    if (!result.is_object() || io::get_int(result, "revision", -1) < 0) { throw std::runtime_error("Invalid workflow choices response"); }
    for (const auto *key : {"tables", "snapshots", "analyses", "templates"}) {
      if (!result.contains(key) || !result.at(key).is_array()) { throw std::runtime_error("Invalid workflow choices response"); }
    }
    choices_ = result;
  });
}

bool ProjectWorkflows::write(const std::string &method, const std::string &id, const std::string &name,
                             const Json &document, const int64_t revision)
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain_ || revision < 0) { return false; }
  try { check_workflow_document(document); }
  catch (const std::exception &) { return false; }
  const auto hello = client_->hello_info();
  if (!hello || !hello->has_method(method)) { return false; }
  // From dispatch until a receipt or a definite rejection the write may have happened.
  uncertain_ = true;
  const bool sent = call(method, {{"workflow_id", id}, {"name", name}, {"document", document}, {"expected_revision", revision}},
      [this, id, name, document, revision](const Json &result) {
    if (!result.is_object() || io::get_int(result, "revision", -1) != revision + 1 || io::get_string(result, "record_id") != id) {
      throw std::runtime_error("Invalid workflow save receipt; read the workflow again before saving");
    }
    // The receipt confirms exactly this document; it is checked again by validate_selected().
    selected_ = {{"id", id}, {"name", name}, {"format", document.at("format")}, {"state", "readable"}, {"error", ""},
                 {"document", document}};
    selected_revision_ = result.at("revision").get<int64_t>();
    validation_ = nullptr; ++selected_version_;
    uncertain_ = false; notice_ = "workflow.saved"; page_ = nullptr;
    project_.refresh();
  }, [this](const bridge::Error &error) {
    // A definite rejection means nothing was written; anything else (a lost reply) stays uncertain.
    if (!error.local && (error.code == bridge::ErrorCode::InvalidParams || error.code == bridge::ErrorCode::Conflict ||
        error.code == bridge::ErrorCode::NotFound || error.code == bridge::ErrorCode::Unsupported)) {
      uncertain_ = false;
    }
  });
  if (!sent) { uncertain_ = false; }
  return sent;
}

bool ProjectWorkflows::create(const std::string &name, const Json &document)
{
  sync();
  if (!supported() || !project_.project()) { return false; }
  const auto hex = new_idempotency_key();
  const auto id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" + hex.substr(16, 4) + "-" + hex.substr(20);
  return write("project.workflows.create", id, name, document, project_.project()->revision);
}

bool ProjectWorkflows::update(const std::string &name, const Json &document, const uint64_t expected_selected_version)
{
  sync();
  if (selected_.is_null() || selected_version_ != expected_selected_version || io::get_string(selected_, "state") != "readable" ||
      stale()) { return false; }
  return write("project.workflows.update", io::get_string(selected_, "id"), name, document, selected_revision_);
}

bool ProjectWorkflows::check(const Json &document, AnalysisCandidateKey key)
{
  sync();
  if (!supported() || key.handle != handle_ || key.session != session_) { return false; }
  const auto ticket = candidate_.begin(std::move(key));
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  if (check_future_) { check_future_->cancel(); }
  check_future_ = client_->call("project.workflows.validate", {{"handle", handle_}, {"document", document}}, options);
  check_future_->then([this, weak, epoch, ticket](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_) { return; }
    if (result) { candidate_.finish(ticket, result.value()); }
    else { candidate_.fail(ticket, result.error().describe()); }
    changed();
  });
  changed();
  return true;
}
bool ProjectWorkflows::runs_supported() const
{
  if (!supported() || project_.project()->format_version < 10) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"project.workflow_runs.prepare", "project.workflow_runs.get", "project.workflow_runs.list",
                             "project.workflow_runs.start", "project.workflow_runs.cancel", "project.workflow_runs.recover"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

void ProjectWorkflows::accept_run(const Json &result)
{
  if (!result.is_object() || !result.contains("run") || !result.at("run").is_object() ||
      !result.at("run").contains("tasks") || !result.at("run").at("tasks").is_array()) {
    throw std::runtime_error("Invalid workflow run response");
  }
  if (io::get_string(run_, "id") != io::get_string(result.at("run"), "id")) { clear_compilation(); }
  run_ = result.at("run");
  ++run_version_;
}

bool ProjectWorkflows::run_call(const std::string &method, Json params)
{
  if (!runs_supported()) { return false; }
  return call(method, std::move(params), [this](const Json &result) { accept_run(result); });
}

bool ProjectWorkflows::load_runs()
{
  if (!runs_supported() || selected_.is_null()) { return false; }
  const auto workflow = io::get_string(selected_, "id");
  Json params = {{"workflow_id", workflow}, {"limit", 20}};
  if (runs_archived_) { params["archived"] = *runs_archived_; }
  return call("project.workflow_runs.list", std::move(params), [this, workflow](const Json &result) {
    if (!result.is_object() || !result.contains("runs") || !result.at("runs").is_array()) {
      throw std::runtime_error("Invalid workflow run list response");
    }
    if (io::get_string(selected_, "id") != workflow) { return; }
    runs_ = result; ++run_version_;
  });
}

bool ProjectWorkflows::load_run(const std::string &run_id)
{
  sync();
  if (run_id.empty() || !runs_supported() || busy_ || project_.busy()) { return false; }
  if (io::get_string(run_, "id") != run_id) { clear_compilation(); }
  return run_call("project.workflow_runs.get", {{"run_id", run_id}});
}

bool ProjectWorkflows::run_rows(const std::vector<std::string> &rows, Json simulation)
{
  sync();
  if (!runs_supported() || selected_.is_null() || rows.empty() || stale() || busy_ || project_.busy()) { return false; }
  const auto hex = new_idempotency_key();
  const auto run_id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" + hex.substr(16, 4) + "-" + hex.substr(20);
  // Prepared at the revision the workflow was read at: a later edit refuses instead of running something else.
  Json params = {{"workflow_id", io::get_string(selected_, "id")}, {"rows", rows}, {"run_id", run_id},
                 {"expected_revision", selected_revision_}};
  if (simulation.is_object()) { params["simulation"] = std::move(simulation); }  // {connection, options} for MuFerro steps
  return call("project.workflow_runs.prepare", std::move(params), [this, run_id](const Json &result) {
    accept_run(result);
    runs_ = nullptr;  // the list gains this run when read again
    call("project.workflow_runs.start", {{"run_id", run_id}}, [this](const Json &started) { accept_run(started); });
  });
}

bool ProjectWorkflows::load_run_staleness()
{
  if (run_.is_null() || !runs_supported()) { return false; }
  const auto hello = client_->hello_info();
  if (!hello || !hello->has_method("project.workflow_runs.stale")) { return false; }
  const auto run_id = io::get_string(run_, "id");
  return call("project.workflow_runs.stale", {{"run_id", run_id}}, [this, run_id](const Json &result) {
    if (!result.is_object() || io::get_string(result, "run_id") != run_id || !result.contains("rows") || !result.at("rows").is_array()) {
      throw std::runtime_error("Invalid workflow run staleness response");
    }
    stale_ = result; ++run_version_;
  });
}

bool ProjectWorkflows::start_run()
{
  return !run_.is_null() && run_call("project.workflow_runs.start", {{"run_id", io::get_string(run_, "id")}});
}

bool ProjectWorkflows::cancel_run()
{
  return !run_.is_null() && run_call("project.workflow_runs.cancel", {{"run_id", io::get_string(run_, "id")}});
}

bool ProjectWorkflows::recover_run()
{
  return !run_.is_null() && run_call("project.workflow_runs.recover", {{"run_id", io::get_string(run_, "id")}});
}

bool ProjectWorkflows::compilations_supported() const
{
  if (!runs_supported()) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *method : {"project.workflow_runs.compilation", "project.workflow_runs.compilation_log",
                              "project.workflow_runs.compilation_source"}) {
    if (!hello || !hello->has_method(method)) { return false; }
  }
  return true;
}

void ProjectWorkflows::clear_compilation()
{
  ++compilation_generation_;
  compilation_key_ = compilation_ = compilation_log_ = nullptr;
  compilation_text_.clear(); compilation_error_.clear();
  compilation_decoder_ = {};
  compilation_busy_ = false;
  auto old = std::move(compilation_future_); compilation_future_.reset();
  if (old) { old->cancel(); }
}

bool ProjectWorkflows::compilation_call(const std::string &method, Json params,
                                      std::function<void(const Json &)> done)
{
  sync();
  if (!compilations_supported() || compilation_busy_ || compilation_key_.is_null() || project_.busy()) { return false; }
  const auto epoch = epoch_, generation = compilation_generation_;
  const auto key = compilation_key_;
  const std::weak_ptr<bool> weak = alive_;
  params.update(key); params["handle"] = handle_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  compilation_busy_ = true; compilation_error_.clear();
  compilation_future_ = client_->call(method, params, options);
  compilation_future_->then([this, weak, epoch, generation, key, done = std::move(done)](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_ || generation != compilation_generation_ || compilation_key_ != key ||
        io::get_string(run_, "id") != io::get_string(key, "run_id")) { return; }
    compilation_busy_ = false; compilation_future_.reset();
    if (!result) { compilation_error_ = result.error().describe(); }
    else {
      try {
        const auto &response = result.value();
        for (const auto &[name, value] : key.items()) {
          if (!response.is_object() || !response.contains(name) || response.at(name) != value) {
            throw std::runtime_error("Compilation evidence belongs to a different attempt");
          }
        }
        done(response);
      }
      catch (const std::exception &error) { compilation_error_ = error.what(); }
    }
    changed();
  });
  changed();
  return true;
}

bool ProjectWorkflows::load_compilation(const std::string &step, const std::string &row, const int64_t attempt)
{
  sync();
  if (!compilations_supported() || run_.is_null() || attempt < 1 || project_.busy()) { return false; }
  const auto frozen = run_.at("steps").find(step);
  if (frozen == run_.at("steps").end() || io::get_string(*frozen, "template") != "latex-compile/1") { return false; }
  bool found = false;
  for (const auto &task : run_.at("tasks")) {
    if (io::get_string(task, "step") == step && io::get_string(task, "row") == row && io::get_int(task, "attempt", 0) >= attempt) {
      found = true; break;
    }
  }
  if (!found) { return false; }
  clear_compilation();
  compilation_key_ = {{"run_id", io::get_string(run_, "id")}, {"step", step}, {"row", row}, {"attempt", attempt}};
  return compilation_call("project.workflow_runs.compilation", Json::object(), [this](const Json &response) {
    if (!response.contains("receipt") || !response.at("receipt").is_object() ||
        io::get_string(response.at("receipt"), "format") != "stk.latex-compile/1") {
      throw std::runtime_error("Invalid compilation receipt");
    }
    compilation_ = response;
  });
}

bool ProjectWorkflows::load_compilation_log(const std::string &stream, const int64_t offset)
{
  if (compilation_.is_null() || offset < 0 ||
      (stream != "stdout.txt" && stream != "stderr.txt" && stream != "compiler.txt")) { return false; }
  if (offset != 0 && (io::get_string(compilation_log_, "stream") != stream ||
      io::get_int(compilation_log_, "next_offset", -1) != offset)) { return false; }
  return compilation_call("project.workflow_runs.compilation_log", {{"stream", stream}, {"offset", offset}, {"limit", 8192}},
      [this, stream, offset](const Json &response) {
    if (io::get_string(response, "attempt_id") != io::get_string(compilation_.at("receipt"), "attempt_id") ||
        io::get_string(response, "stream") != stream || io::get_int(response, "offset", -1) != offset) {
      throw std::runtime_error("Compilation log page identity does not match");
    }
    const auto encoded = io::get_string(response, "data");
    if (encoded.size() > 10924) { throw std::runtime_error("Compilation log page exceeds its budget"); }
    const auto bytes = bridge::decode_base64(encoded);
    if (!bytes || bytes->size() > 8192 || io::get_int(response, "next_offset", -1) != offset + int64_t(bytes->size())) {
      throw std::runtime_error("Invalid compilation log page");
    }
    if (offset == 0) { compilation_decoder_ = {}; }
    const std::string raw(bytes->begin(), bytes->end());
    compilation_text_ = compilation_decoder_.feed(raw);
    if (bytes->size() < 8192 && io::get_bool(response, "terminal", false)) { compilation_text_ += compilation_decoder_.finish(); }
    compilation_log_ = response;
  });
}

bool ProjectWorkflows::read_compilation_source(const size_t diagnostic, std::function<void(const Json &)> done)
{
  if (compilation_.is_null() || !project_.project()) { return false; }
  const auto &receipt = compilation_.at("receipt");
  if (!receipt.contains("diagnostics") || !receipt.at("diagnostics").is_array() || diagnostic >= receipt.at("diagnostics").size()) { return false; }
  const auto expected = receipt.at("diagnostics")[diagnostic];
  const auto attempt_id = io::get_string(receipt, "attempt_id");
  const auto revision = project_.project()->revision;
  return compilation_call("project.workflow_runs.compilation_source", {{"diagnostic", diagnostic}, {"expected_revision", revision}},
      [this, expected, diagnostic, revision, attempt_id, done = std::move(done)](const Json &response) {
    if (!project_.project() || project_.project()->revision != revision || io::get_int(response, "revision", -1) != revision ||
        io::get_string(response, "attempt_id") != attempt_id || io::get_int(response, "diagnostic", -1) != int64_t(diagnostic)) {
      throw std::runtime_error("Compilation source selection is no longer current");
    }
    for (const auto *key : {"record_id", "source_sha256", "line", "column"}) {
      if (!response.contains(key) || response.at(key) != expected.at(key)) { throw std::runtime_error("Compilation source identity does not match"); }
    }
    done(response);
  });
}
}  // namespace stk::app
