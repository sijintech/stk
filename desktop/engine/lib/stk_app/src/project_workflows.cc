/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_workflows.hh"

#include "stk/app/app_store.hh"
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
}

void ProjectWorkflows::changed() { ++version_; store_.changed(); }

void ProjectWorkflows::reset()
{
  ++epoch_; ++selected_version_;
  busy_ = false;
  selected_revision_ = -1;
  page_ = selected_ = validation_ = nullptr;
  error_.clear();
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
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

bool ProjectWorkflows::call(const std::string &method, Json params, std::function<void(const Json &)> done)
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
  future_->then([this, weak, epoch, done = std::move(done)](bridge::Result<Json> result) {
    const auto alive = weak.lock();
    if (!alive || !*alive) { return; }
    sync();
    if (epoch != epoch_) { return; }
    busy_ = false; future_.reset();
    if (!result) { error_ = result.error().describe(); }
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
  return call("project.workflows.list", {{"offset", offset}, {"limit", 50}}, [this, offset](const Json &result) {
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
  return call("project.workflows.get", {{"workflow_id", id}}, [this, id](const Json &response) {
    if (!response.is_object() || io::get_int(response, "revision", -1) < 0 || !response.contains("workflow") ||
        !valid_summary(response.at("workflow")) || response.at("workflow").at("id") != id ||
        !response.at("workflow").contains("document") ||
        (response.at("workflow").at("state") == "readable") != response.at("workflow").at("document").is_object()) {
      throw std::runtime_error("Invalid workflow response");
    }
    selected_ = response.at("workflow");
    selected_revision_ = response.at("revision").get<int64_t>();
    validation_ = nullptr;
    ++selected_version_;
    if (selected_.at("state") != "readable") { return; }
    const auto document = selected_.at("document");
    const auto epoch = epoch_;
    // The check describes exactly the document just read; a newer read replaces both.
    call("project.workflows.validate", {{"document", document}}, [this, id, epoch, document](const Json &result) {
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
  });
}

bool ProjectWorkflows::reload()
{
  sync();
  if (selected_.is_null()) { return load_page(page_.is_null() ? 0 : io::get_int(page_, "offset", 0)); }
  return load(io::get_string(selected_, "id"));
}
}  // namespace stk::app
