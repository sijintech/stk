/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/app_store.hh"

#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/module_settings.hh"
#include "stk/app/materials_state.hh"
#include "stk/app/project_archive.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/project_attention.hh"
#include "stk/app/skill_catalog.hh"
#include "stk/app/viewer_state.hh"

#include <algorithm>
#include <cmath>
#include <exception>
#include <utility>

namespace stk::app {

struct ProjectScopeSubscription::State {
  bool active = true;
  std::function<void()> callback;
};
ProjectScopeSubscription::~ProjectScopeSubscription() { reset(); }
ProjectScopeSubscription::ProjectScopeSubscription(ProjectScopeSubscription &&) noexcept = default;
ProjectScopeSubscription &ProjectScopeSubscription::operator=(ProjectScopeSubscription &&other) noexcept
{
  if (this != &other) { reset(); state_ = std::move(other.state_); }
  return *this;
}
void ProjectScopeSubscription::reset() noexcept
{
  auto old = std::move(state_);
  if (old) { old->active = false; old->callback = nullptr; }
}

const char *bridge_state_key(const BridgeState state)
{
  switch (state) {
    case BridgeState::NotStarted: return "app.status.bridge.not_started";
    case BridgeState::Starting: return "app.status.bridge.starting";
    case BridgeState::Ready: return "app.status.bridge.ready";
    case BridgeState::Restarting: return "app.status.bridge.restarting";
    case BridgeState::Failed: return "app.status.bridge.failed";
    case BridgeState::Stopping: return "app.status.bridge.stopping";
  }
  return "app.status.bridge.not_started";
}

AppStore::AppStore() = default;

AppStore::~AppStore()
{
  /* The editors' states call changed() from their callbacks and refer to this store: drop them
   * (jobs first: its subscriptions may feed the viewer) before the rest of the store. */
  on_change = nullptr;
  for (const auto &weak : project_scope_observers_) {
    if (auto state = weak.lock()) { state->active = false; state->callback = nullptr; }
  }
  project_scope_observers_.clear();
  attention_.reset();
  archive_.reset();
  data_labels_.reset();
  models_.reset();
  modules_.reset();
  materials_.reset();
  skills_.reset();
  scripts_.reset();
  project_.reset();
  jobs_.reset();
  viewer_.reset();
}

ProjectState &AppStore::project()
{
  if (!project_) {
    project_ = std::make_unique<ProjectState>(*this);
  }
  return *project_;
}

ProjectDataLabels &AppStore::data_labels()
{
  if (!data_labels_) {
    data_labels_ = std::make_unique<ProjectDataLabels>(*this);
  }
  return *data_labels_;
}

ModelSettings &AppStore::models()
{
  if (!models_) {
    models_ = std::make_unique<ModelSettings>(*this);
  }
  return *models_;
}

ModuleSettings &AppStore::modules()
{
  if (!modules_) {
    modules_ = std::make_unique<ModuleSettings>(*this);
  }
  return *modules_;
}

MaterialsState &AppStore::materials()
{
  if (!materials_) { materials_ = std::make_unique<MaterialsState>(*this); }
  return *materials_;
}

ProjectArchive &AppStore::archive()
{
  if (!archive_) {
    archive_ = std::make_unique<ProjectArchive>(*this);
  }
  return *archive_;
}

ProjectAttention &AppStore::attention()
{
  if (!attention_) {
    attention_ = std::make_unique<ProjectAttention>(*this);
  }
  return *attention_;
}

SkillCatalogState &AppStore::skills()
{
  if (!skills_) {
    skills_ = std::make_unique<SkillCatalogState>(*this);
  }
  return *skills_;
}

ScriptState &AppStore::scripts()
{
  if (!scripts_) {
    scripts_ = std::make_unique<ScriptState>(*this);
  }
  return *scripts_;
}

void AppStore::set_bridge(bridge::Client *client)
{
  if (bridge_client_ != client) { ++bridge_epoch_; invalidate_project_scope(); }
  bridge_client_ = client;
  if (scripts_) {
    scripts_->sync();
  }
}

ProjectScopeSubscription AppStore::observe_project_scope(std::function<void()> callback)
{
  ProjectScopeSubscription subscription;
  if (!callback) { return subscription; }
  subscription.state_ = std::make_shared<ProjectScopeSubscription::State>();
  subscription.state_->callback = std::move(callback);
  std::erase_if(project_scope_observers_, [](const auto &weak) { return weak.expired(); });
  project_scope_observers_.push_back(subscription.state_);
  return subscription;
}

void AppStore::invalidate_project_scope()
{
  const auto epoch = ++project_scope_epoch_;
  const auto observers = project_scope_observers_;
  std::erase_if(project_scope_observers_, [](const auto &weak) { return weak.expired(); });
  std::exception_ptr failure;
  for (const auto &weak : observers) {
    auto state = weak.lock();
    if (!state || !state->active || !state->callback) { continue; }
    // A callback may destroy its own token. Keep its invocation alive independently.
    auto callback = state->callback;
    try { callback(); }
    catch (...) { if (!failure) { failure = std::current_exception(); } }
    if (project_scope_epoch_ != epoch) { break; }
  }
  // One misbehaving listener must not leave another owner's resource session usable.
  if (failure) { std::rethrow_exception(failure); }
}

JobsState &AppStore::jobs()
{
  if (!jobs_) {
    jobs_ = std::make_unique<JobsState>(*this);
  }
  return *jobs_;
}

ViewerState &AppStore::viewer()
{
  if (!viewer_) {
    viewer_ = std::make_unique<ViewerState>(*this);
  }
  return *viewer_;
}

void AppStore::set_language(const std::string &language)
{
  if (language != catalog_.language()) {
    catalog_.set_language(language);
    changed();
  }
}

void AppStore::set_ui_scale(const float scale)
{
  const float s = std::isfinite(scale) ? std::clamp(scale, 0.25f, 4.0f) : 1.0f;
  if (s != ui_scale_) {
    ui_scale_ = s;
    changed();
  }
}

void AppStore::set_bridge_state(const BridgeState state)
{
  if (state != bridge_) {
    if (state != BridgeState::Ready) { invalidate_project_scope(); }
    bridge_ = state;
    changed();
  }
}

void AppStore::set_bridge_error(std::string error)
{
  if (error != bridge_error_) {
    bridge_error_ = std::move(error);
    changed();
  }
}

void AppStore::set_connection(std::string connection)
{
  if (connection != connection_) {
    connection_ = std::move(connection);
    changed();
  }
}

void AppStore::log(std::string_view line)
{
  std::string s;
  if (clock) {
    s = clock() + "  ";
  }
  s.append(line);
  s.push_back('\n');
  app_log_.append(s);
  changed();
}

void AppStore::changed()
{
  version_++;
  if (on_change) {
    on_change();
  }
}

void AppStore::request_open_result(OpenResultRequest request)
{
  pending_open_ = std::move(request);
  changed();
}

std::optional<OpenResultRequest> AppStore::take_open_result()
{
  std::optional<OpenResultRequest> request = std::move(pending_open_);
  pending_open_.reset();
  if (request && request->still_current && !request->still_current()) { return std::nullopt; }
  return request;
}

}  // namespace stk::app
