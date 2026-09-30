/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/project_state.hh"

#include "stk/bridge/client.hh"
#include "stk/io/catalog.hh"
#include "stk/core/utf8.hh"

#include <limits>

namespace stk::app {
namespace {
bool hexadecimal(std::string_view value, const size_t length)
{
  if (value.size() != length) { return false; }
  for (const char c : value) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) { return false; }
  }
  return true;
}
bool uuid(std::string_view value)
{
  if (value.size() != 36) { return false; }
  for (size_t i = 0; i < value.size(); ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') { return false; }
    }
    else if (!hexadecimal(value.substr(i, 1), 1)) { return false; }
  }
  return true;
}
bool text(const io::Json &object, const char *key, size_t bytes, size_t characters)
{
  const auto it = object.find(key);
  if (it == object.end() || !it->is_string()) { return false; }
  const auto &value = it->get_ref<const std::string &>();
  return !value.empty() && value.size() <= bytes && core::utf8::is_valid(value) &&
      value.find('\0') == std::string::npos && core::utf8::count_code_points(value) <= characters;
}
bool nonnegative_int(const io::Json &value, const uint64_t maximum)
{
  if (!value.is_number_integer()) { return false; }
  return value.is_number_unsigned() ? value.get<uint64_t>() <= maximum :
      value.get<int64_t>() >= 0 && uint64_t(value.get<int64_t>()) <= maximum;
}
bool frozen_bindings(const io::Json &bindings)
{
  // No path is resolved or opened here. The backend validates portable path semantics and
  // manifest membership; this guards every copied UI value and the published resource limits.
  constexpr uint64_t max_bytes = 256 * 1024 * 1024;
  if (!bindings.is_object() || bindings.empty() || bindings.size() > 32) { return false; }
  size_t count = 0;
  uint64_t total = 0;
  for (const auto &[name, files] : bindings.items()) {
    if (name.empty() || name.size() > 64 || name.front() < 'a' || name.front() > 'z') { return false; }
    for (const char c : name) {
      if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) { return false; }
    }
    if (!files.is_object() || files.empty() || files.size() > 100 - count) { return false; }
    count += files.size();
    for (const auto &[path, file] : files.items()) {
      if (path.empty() || path.size() > 1024 || !core::utf8::is_valid(path) ||
          path.find('\0') != std::string::npos || !file.is_object() || file.size() != 3 ||
          !text(file, "record_id", 36, 36) || !uuid(file.at("record_id").get_ref<const std::string &>()) ||
          !text(file, "sha256", 64, 64) || !hexadecimal(file.at("sha256").get_ref<const std::string &>(), 64) ||
          !file.contains("size") || !nonnegative_int(file.at("size"), max_bytes - total)) { return false; }
      total += file.at("size").get<uint64_t>();
    }
  }
  return true;
}
bool frozen_source(const io::Json &run, const std::string &project_id)
{
  if (!run.is_object() || !run.contains("document") || !run.contains("bindings") ||
      !run.contains("source_revision") ||
      !nonnegative_int(run.at("source_revision"), uint64_t(std::numeric_limits<int64_t>::max()))) { return false; }
  for (const char *key : {"id", "project_id", "analysis_id", "snapshot_id"}) {
    if (!text(run, key, 36, 36) || !uuid(run.at(key).get_ref<const std::string &>())) { return false; }
  }
  for (const char *key : {"snapshot_sha256", "plan_sha256"}) {
    if (!text(run, key, 64, 64) || !hexadecimal(run.at(key).get_ref<const std::string &>(), 64)) { return false; }
  }
  return run.at("project_id") == project_id && text(run, "analysis_name", 1024, 256) &&
      text(run, "created_at", 256, 64) && frozen_bindings(run.at("bindings"));
}
std::string bridge_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
bool same_json(const io::Json &a, const io::Json &b)
{
  // JSON equality alone conflates integer 1 with float 1.0. Preserve the submitted types while
  // ignoring object key order, consistently with Viewer configuration comparison.
  return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true);
}
bool same_source(const ViewerSource &a, const ViewerSource &b)
{
  return a.kind == b.kind && a.path == b.path && a.field_file == b.field_file &&
         a.connection == b.connection && a.node == b.node && a.workspace_id == b.workspace_id &&
         a.task_id == b.task_id && a.series == b.series;
}
bool same_configuration(const std::optional<ViewerGraphConfiguration> &a,
                        const std::optional<ViewerGraphConfiguration> &b)
{
  if (!a || !b) { return bool(a) == bool(b); }
  return same_source(a->source, b->source) && a->preset_id == b->preset_id &&
         same_json(a->graph, b->graph) && same_json(a->parameters, b->parameters) && a->requested_outputs == b->requested_outputs;
}
bool same_definition(const std::optional<AnalysisGraphDefinition> &a,
                     const std::optional<AnalysisGraphDefinition> &b)
{
  if (!a || !b) { return bool(a) == bool(b); }
  return same_json(a->graph, b->graph) && same_json(a->parameters, b->parameters) &&
         a->requested_outputs == b->requested_outputs;
}
}  // namespace

AnalysisGraphState::AnalysisGraphState(ViewerState &viewer) : viewer_(viewer) { sync(); }
AnalysisGraphState::~AnalysisGraphState()
{
  *alive_ = false;
  if (validation_future_) { validation_future_->cancel(); }
  if (catalog_future_) { catalog_future_->cancel(); }
}

const ViewerGraphConfiguration *AnalysisGraphState::configuration() const
{
  return configuration_ ? &*configuration_ : nullptr;
}

void AnalysisGraphState::invalidate_validation()
{
  ++generation_;
  validating_ = false;
  validation_ = nullptr;
  validation_error_.clear();
  auto old = std::move(validation_future_);
  validation_future_.reset();
  if (old) { old->cancel(); }
}

void AnalysisGraphState::reset_catalog_request()
{
  ++catalog_request_generation_;
  catalog_requested_ = catalog_loading_ = false;
  independent_catalog_ = nullptr;
  catalog_error_.clear();
  auto old = std::move(catalog_future_);
  catalog_future_.reset();
  if (old) { old->cancel(); }
}

bool AnalysisGraphState::ensure_catalog()
{
  sync();
  if (!catalog_.is_null() || !bridge_ || session_.empty() || catalog_requested_) { return false; }
  catalog_requested_ = true;
  const auto hello = bridge_->hello_info();
  if (!hello || !hello->has_method("graph.catalog")) {
    catalog_error_ = "This bridge does not provide a node catalog";
    viewer_.store().changed();
    return false;
  }
  catalog_loading_ = true;
  const auto request = ++catalog_request_generation_;
  auto *client = bridge_;
  const auto session = session_;
  const std::weak_ptr<bool> weak = alive_;
  catalog_future_ = client->graph_catalog();
  catalog_future_->then([this, weak, request, client, session](bridge::Result<io::Json> result) {
    const auto live = weak.lock();
    if (!live || !*live || request != catalog_request_generation_ ||
        viewer_.store().bridge() != client || bridge_session(client) != session) { return; }
    catalog_future_.reset();
    catalog_loading_ = false;
    if (!result) { catalog_error_ = result.error().message; }
    else {
      try {
        const auto &catalog = result.value().at("catalog");
        (void)io::Catalog::from_json(catalog);
        independent_catalog_ = catalog;
        catalog_error_.clear();
        dirty_ = true;
        sync();
      }
      catch (const std::exception &error) { catalog_error_ = error.what(); }
    }
    viewer_.store().changed();
  });
  viewer_.store().changed();
  return true;
}

void AnalysisGraphState::sync()
{
  if (!document_handle_.empty()) {
    const auto &project = viewer_.store().project().project();
    if (!project || project->handle != document_handle_) {
      document_handle_.clear(); document_id_.clear(); document_revision_ = -1;
      document_definition_.reset();
      if (saved()) { invalidate_validation(); dirty_ = true; }
    }
  }
  auto *bridge = viewer_.store().bridge();
  const std::string session = bridge_session(bridge);
  if (run_source_) {
    const auto &project = viewer_.store().project().project();
    if (!project || project->handle != run_handle_ || bridge != bridge_ || session != session_) {
      run_source_.reset(); run_definition_.reset(); run_handle_.clear();
      if (source_ == Source::Run) { invalidate_validation(); dirty_ = true; }
    }
  }
  if (bridge != bridge_ || session != session_) { reset_catalog_request(); }
  if (!viewer_.catalog().is_null() && (catalog_loading_ || !catalog_error_.empty())) {
    // A separately opened Viewer may have obtained metadata while this controller waited.
    // Its available cache wins; do not keep reporting an obsolete failure/loading state.
    reset_catalog_request();
  }
  const auto &catalog = viewer_.catalog().is_null() ? independent_catalog_ : viewer_.catalog();
  if (!dirty_ && viewer_version_ == viewer_.version() && bridge == bridge_ && session == session_) { return; }
  const bool detached = source_ == Source::Saved || source_ == Source::Run;
  const auto next = detached ? nullptr : viewer_.graph_inspection();
  const std::optional<ViewerGraphConfiguration> configuration = detached ? std::nullopt :
      (displayed() ? next->shown_configuration : next->desired);
  std::optional<AnalysisGraphDefinition> definition = saved() ? document_definition_ :
      (source_ == Source::Run ? run_definition_ : std::nullopt);
  if (configuration) { definition = {configuration->graph, configuration->parameters, configuration->requested_outputs}; }
  const bool catalog_changed = !same_json(catalog, catalog_);
  const bool changed = !same_configuration(configuration_, configuration) ||
      !same_definition(definition_, definition) || catalog_changed;
  const bool graph_changed = bool(definition_) != bool(definition) || catalog_changed ||
      (definition_ && definition && !same_json(definition_->graph, definition->graph));
  if (changed || bridge != bridge_ || session != session_) { invalidate_validation(); }
  bridge_ = bridge;
  session_ = session;
  inspection_ = next;
  viewer_version_ = viewer_.version();
  dirty_ = false;
  if (!changed) { return; }
  configuration_ = configuration;
  definition_ = std::move(definition);
  catalog_ = catalog;
  if (!graph_changed) { return; }
  view_.reset();
  error_.clear();
  if (!definition_) { return; }
  try {
    const io::Graph graph = io::Graph::from_json(definition_->graph);
    std::optional<io::Catalog> types;
    if (!catalog_.is_null()) { types = io::Catalog::from_json(catalog_); }
    view_ = std::make_shared<const AnalysisGraphView>(analysis_graph_view(graph, types ? &*types : nullptr));
  }
  catch (const std::exception &error) { error_ = error.what(); }
}

void AnalysisGraphState::set_source(const Source source)
{
  if (source_ == source) { sync(); return; }
  source_ = source;
  invalidate_validation();
  // Source identity is significant even when graph/parameters happen to be identical.
  dirty_ = true;
  sync();
  viewer_.store().changed();
}

void AnalysisGraphState::show_displayed(const bool displayed)
{
  set_source(displayed ? Source::Displayed : Source::Current);
}

void AnalysisGraphState::show_saved() { set_source(Source::Saved); }
void AnalysisGraphState::show_run() { set_source(Source::Run); }

bool AnalysisGraphState::open_document(const std::string &handle, const std::string &analysis_id,
                                     const int64_t revision, const io::Json &document, const bool activate)
{
  const auto &project = viewer_.store().project().project();
  if (!project || handle.empty() || project->handle != handle || analysis_id.empty() || revision < 0 ||
      !document.is_object() || io::get_string(document, "format") != "stk.analysis-document/1" ||
      !document.contains("graph") || !document.at("graph").is_object() ||
      !document.contains("parameters") || !document.at("parameters").is_object() ||
      !document.contains("outputs") || !document.at("outputs").is_array()) { return false; }
  AnalysisGraphDefinition definition{document.at("graph"), document.at("parameters"), {}};
  for (const auto &output : document.at("outputs")) {
    if (!output.is_string()) { return false; }
    definition.requested_outputs.push_back(output.get<std::string>());
  }
  document_definition_ = std::move(definition);
  document_handle_ = handle; document_id_ = analysis_id; document_revision_ = revision;
  if (activate) { source_ = Source::Saved; }
  if (saved()) { invalidate_validation(); dirty_ = true; sync(); }
  viewer_.store().changed();
  return true;
}

void AnalysisGraphState::clear_document()
{
  document_definition_.reset(); document_handle_.clear(); document_id_.clear(); document_revision_ = -1;
  if (saved()) { invalidate_validation(); dirty_ = true; sync(); }
  viewer_.store().changed();
}

bool AnalysisGraphState::open_frozen_run(const std::string &handle, const io::Json &run)
{
  // Inspect only the immutable fields consumed here. A valid document has depth <=64 relative
  // to its own root, while the journal adds a wrapper and permits a larger 512 KiB plan plus
  // 16 KiB lifecycle record. Applying document limits to that wrapper would reject valid runs.
  const auto &project = viewer_.store().project().project();
  auto *client = viewer_.store().bridge();
  const auto session = bridge_session(client);
  if (!project || handle.empty() || project->handle != handle || session.empty()) { return false; }
  try {
    if (!frozen_source(run, project->id)) { return false; }
    const auto &document = run.at("document");
    check_analysis_document_bounds(document);
    (void)io::Graph::from_json(document.at("graph"));
    // Every consumed subtree is now bounded. Never copy lifecycle/result/error or turn them
    // into a current Viewer receipt. Missing submitted parameters stay missing.
    AnalysisGraphDefinition definition{document.at("graph"), document.at("parameters"), {}};
    for (const auto &output : document.at("outputs")) {
      definition.requested_outputs.push_back(output.get<std::string>());
    }
    AnalysisGraphRunSource source;
    source.id = run.at("id").get<std::string>();
    source.project_id = run.at("project_id").get<std::string>();
    source.analysis_id = run.at("analysis_id").get<std::string>();
    source.analysis_name = run.at("analysis_name").get<std::string>();
    source.created_at = run.at("created_at").get<std::string>();
    source.snapshot_id = run.at("snapshot_id").get<std::string>();
    source.snapshot_sha256 = run.at("snapshot_sha256").get<std::string>();
    source.plan_sha256 = run.at("plan_sha256").get<std::string>();
    source.source_revision = run.at("source_revision").get<int64_t>();
    source.bindings = run.at("bindings");
    // Synchronize old session state only after all validation/copies succeed, preserving the
    // previous view on rejection. The new source is fenced to this exact ready session.
    sync();
    run_source_ = std::move(source); run_definition_ = std::move(definition); run_handle_ = handle;
    source_ = Source::Run;
    invalidate_validation(); dirty_ = true; sync();
    viewer_.store().changed();
    return true;
  }
  catch (const std::exception &) { return false; }
}

void AnalysisGraphState::clear_run()
{
  run_source_.reset(); run_definition_.reset(); run_handle_.clear();
  if (source_ == Source::Run) { invalidate_validation(); dirty_ = true; sync(); }
  viewer_.store().changed();
}

bool AnalysisGraphState::document_stale() const
{
  const auto &project = viewer_.store().project().project();
  return !document_handle_.empty() && (!project || project->handle != document_handle_ ||
      project->revision != document_revision_);
}

bool AnalysisGraphState::validation_available() const
{
  if (!definition_ || !view_ || !bridge_ || session_.empty()) { return false; }
  const auto hello = bridge_->hello_info();
  return hello && hello->has_method("graph.validate");
}

bool AnalysisGraphState::validate()
{
  sync();
  if (validating_ || !validation_available()) { return false; }
  invalidate_validation();
  validating_ = true;
  const uint64_t generation = generation_;
  const std::weak_ptr<bool> weak = alive_;
  validation_future_ = bridge_->graph_validate(definition_->graph, definition_->parameters);
  validation_future_->then([this, weak, generation](bridge::Result<io::Json> result) {
    const auto live = weak.lock();
    if (!live || !*live) { return; }
    sync();
    if (generation != generation_) { return; }
    validating_ = false;
    validation_future_.reset();
    if (!result) { validation_error_ = result.error().message; }
    else if (!result.value().is_object() || !result.value().contains("ok") ||
             !result.value().at("ok").is_boolean() || !result.value().contains("issues") ||
             !result.value().at("issues").is_array())
    {
      validation_error_ = "Invalid graph validation response";
    }
    else { validation_ = std::move(result).value(); }
    viewer_.store().changed();
  });
  viewer_.store().changed();
  return true;
}

}  // namespace stk::app
