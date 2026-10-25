/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_skills.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/schema.hh"
#include "stk/core/sha256.hh"

#include <limits>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;

ProjectSkills::ProjectSkills(AppStore &store) : store_(store), project_(store.project()) { sync(); }
ProjectSkills::~ProjectSkills()
{
  log_pending(); *alive_ = false;
  if (future_) { future_->cancel(); }
}
void ProjectSkills::changed() { store_.changed(); }
void ProjectSkills::log_pending()
{
  if (uncertain()) {
    store_.log("Skill write reply unavailable; inspect existing " + io::get_string(pending_, "method") +
               " object " + io::get_string(pending_, "id"));
  }
}
void ProjectSkills::sync()
{
  project_.sync();
  auto *client = store_.bridge();
  const auto handle = project_.project() ? project_.project()->handle : std::string();
  const auto session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client_ == client && session_ == session && handle_ == handle) { return; }
  log_pending(); ++epoch_;
  client_ = client; handle_ = handle; session_ = session;
  page_ = selected_ = pending_ = nullptr;
  selected_id_.clear(); analysis_id_.clear(); error_.clear(); notice_.clear();
  page_attempt_ = selected_attempt_ = selected_revision_ = -1;
  busy_ = false;
  auto old = std::move(future_); future_.reset();
  if (old) { old->cancel(); }
  changed();
}
bool ProjectSkills::supported() const
{
  if (!client_ || store_.bridge() != client_ || session_.empty() || !project_.ready() ||
      !project_.loaded() || !project_.project() || project_.project()->handle != handle_ ||
      project_.project()->format_version < 3) { return false; }
  const auto hello = client_->hello_info();
  for (const auto *action : {"list", "get", "pin", "upgrade", "restore", "create_analysis"}) {
    if (!hello || !hello->has_method(std::string("project.skills.") + action)) { return false; }
  }
  return true;
}
int64_t ProjectSkills::revision() const
{
  return supported() ? project_.project()->revision : -1;
}
bool ProjectSkills::current() const
{
  return supported() && selected_.is_object() && selected_revision_ == revision() &&
      io::get_string(selected_, "id") == selected_id_ && io::get_string(selected_, "state") == "readable";
}
bool ProjectSkills::call(const std::string &method, Json params,
                         std::function<void(const Json &)> done,
                         std::function<void(const bridge::Error &)> failed)
{
  sync();
  if (!supported() || busy_ || project_.busy()) { return false; }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  params["handle"] = handle_;
  busy_ = true; error_.clear(); notice_.clear();
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never;
  future_ = client_->call(method, params, options);
  future_->then([this, weak, epoch, method, done = std::move(done), failed = std::move(failed)](bridge::Result<Json> result) {
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
      try {
        const auto &schema = bridge::ProtocolSchema::embedded().resolved("#/$defs/methods/" + method + "/result");
        if (!io::check_value(result.value(), schema).empty()) { throw std::runtime_error("Invalid saved skill response"); }
        done(result.value());
      }
      catch (const std::exception &error) {
        error_ = error.what();
        if (failed) { failed(bridge::Error::make(bridge::ErrorCode::InternalError, error_)); }
      }
    }
    changed();
  });
  changed(); return true;
}
bool ProjectSkills::load_page(const int64_t offset)
{
  if (offset < 0 || busy_ || uncertain()) { return false; }
  const auto attempted = revision();
  const bool accepted = call("project.skills.list", {{"offset", offset}, {"limit", 50}}, [this, offset](const Json &result) {
    if (io::get_int(result, "offset", -1) != offset || result.at("skills").size() > 50) {
      throw std::runtime_error("Invalid saved skill page");
    }
    page_ = result;
    if (io::get_int(result, "revision", -1) != revision()) { project_.refresh(); }
  });
  if (accepted) { page_attempt_ = attempted; }
  return accepted;
}
void ProjectSkills::accept_read(const Json &response, const std::string &id)
{
  const auto &item = response.at("skill");
  if (item.at("id") != id) { throw std::runtime_error("Saved skill response belongs to another object"); }
  if (item.at("state") == "readable") {
    const auto &document = item.at("document");
    check_analysis_json_bounds(document);
    std::set<int64_t> versions;
    Json summaries = Json::array();
    bool active = false;
    for (const auto &snapshot : document.at("versions")) {
      const auto &definition = snapshot.at("definition");
      const auto &digest = snapshot.at("content_sha256");
      const Json content = {{"definition", definition}, {"template", snapshot.at("template")}};
      if (core::Sha256::hex(io::python_json_dumps(content, true, true)) != digest.get<std::string>() ||
          !versions.insert(definition.at("version").get<int64_t>()).second ||
          definition.at("id") != item.at("active").at("skill_id")) {
        throw std::runtime_error("Saved skill content or version identity is invalid");
      }
      const Json summary = {{"skill_id", definition.at("id")}, {"version", definition.at("version")},
          {"ref", definition.at("id").get<std::string>() + "@" + std::to_string(definition.at("version").get<int64_t>())},
          {"title", definition.at("title")}, {"content_sha256", digest}};
      summaries.push_back(summary);
      if (digest == document.at("active")) {
        active = true;
        if (summary != item.at("active")) {
          throw std::runtime_error("Saved skill active version does not match its content");
        }
      }
    }
    if (!active) { throw std::runtime_error("Saved skill active version is missing"); }
    if (summaries != item.at("versions")) { throw std::runtime_error("Saved skill summaries do not match their content"); }
  }
  selected_ = item; selected_revision_ = response.at("revision").get<int64_t>();
  if (selected_revision_ != revision()) { project_.refresh(); }
}
bool ProjectSkills::load_selected()
{
  if (!canonical_uuid(selected_id_)) { return false; }
  const auto id = selected_id_;
  const auto attempted = revision();
  const bool accepted = call("project.skills.get", {{"project_skill_id", id}},
      [this, id](const Json &result) { accept_read(result, id); });
  if (accepted) { selected_attempt_ = attempted; }
  return accepted;
}
void ProjectSkills::ensure_loaded()
{
  sync();
  if (!supported() || busy_ || project_.busy() || uncertain()) { return; }
  if (page_attempt_ != revision()) { load_page(io::get_int(page_, "offset", 0)); return; }
  if (!selected_id_.empty() && selected_attempt_ != revision()) { load_selected(); }
}
bool ProjectSkills::refresh()
{
  sync();
  if (busy_ || uncertain()) { return false; }
  selected_attempt_ = -1;
  return load_page();
}
bool ProjectSkills::select(const std::string &id)
{
  sync();
  if (!supported() || busy_ || uncertain() || !canonical_uuid(id)) { return false; }
  selected_id_ = id; selected_ = nullptr; selected_revision_ = selected_attempt_ = -1;
  return load_selected();
}
std::string ProjectSkills::new_id()
{
  const auto hex = new_idempotency_key();
  return hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" +
      hex.substr(16, 4) + "-" + hex.substr(20);
}
bool ProjectSkills::write(const std::string &action, Json params, const uint64_t expected_epoch)
{
  sync();
  const auto rev = revision();
  if (!supported() || busy_ || project_.busy() || uncertain() || expected_epoch != epoch_ || rev < 0 ||
      rev == std::numeric_limits<int64_t>::max() || io::get_int(params, "expected_revision", -1) != rev ||
      (action != "pin" && action != "upgrade" && action != "restore" && action != "create_analysis")) { return false; }
  if (action != "pin" && (!current() || io::get_string(params, "project_skill_id") != selected_id_)) { return false; }
  const auto id = io::get_string(params, action == "create_analysis" ? "analysis_id" : "project_skill_id");
  if (!canonical_uuid(id)) { return false; }
  const auto method = "project.skills." + action;
  pending_ = {{"method", method}, {"id", id}, {"analysis", action == "create_analysis"}};
  const bool accepted = call(method, params, [this, rev, id, action](const Json &result) {
    if (io::get_int(result, "revision", -1) != rev + 1 || io::get_string(result, "record_id") != id) {
      throw std::runtime_error("Invalid saved skill write receipt; check its existing identity");
    }
    pending_ = nullptr; page_attempt_ = selected_attempt_ = -1;
    if (action == "create_analysis") { analysis_id_ = id; }
    else { selected_id_ = id; selected_ = nullptr; }
    notice_ = "skills.project.saved"; project_.refresh();
  }, [this](const bridge::Error &error) {
    if (!error.local && (error.code == bridge::ErrorCode::InvalidParams || error.code == bridge::ErrorCode::Conflict ||
        error.code == bridge::ErrorCode::NotFound || error.code == bridge::ErrorCode::Unsupported)) { pending_ = nullptr; }
    else { log_pending(); }
  });
  if (!accepted) { pending_ = nullptr; }
  return accepted;
}
bool ProjectSkills::check_pending()
{
  sync();
  if (!uncertain()) { return false; }
  const auto id = pending_.at("id").get<std::string>();
  const bool analysis = pending_.at("analysis").get<bool>();
  return call(analysis ? "project.analyses.get" : "project.skills.get",
      {{analysis ? "analysis_id" : "project_skill_id", id}}, [this, id, analysis](const Json &result) {
        if (analysis) {
          if (result.at("analysis").at("id") != id) { throw std::runtime_error("Analysis identity mismatch"); }
          analysis_id_ = id;
        }
        else { selected_id_ = id; accept_read(result, id); }
        pending_ = nullptr; page_attempt_ = selected_attempt_ = -1;
        notice_ = "skills.project.observed"; project_.refresh();
      }, [this](const bridge::Error &error) {
        if (!error.local && error.code == bridge::ErrorCode::NotFound) {
          pending_ = nullptr; notice_ = "skills.project.missing"; project_.refresh();
        }
      });
}
}  // namespace stk::app
