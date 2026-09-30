/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/project_state.hh"

#include "stk/bridge/client.hh"
#include "stk/io/catalog.hh"

namespace stk::app {
namespace {
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

void AnalysisGraphState::sync()
{
  if (!document_handle_.empty()) {
    const auto &project = viewer_.store().project().project();
    if (!project || project->handle != document_handle_) {
      document_handle_.clear(); document_id_.clear(); document_revision_ = -1;
      document_definition_.reset();
      if (saved_) { invalidate_validation(); dirty_ = true; }
    }
  }
  auto *bridge = viewer_.store().bridge();
  const std::string session = bridge && bridge->state() == bridge::BridgeState::Ready ?
      std::to_string(bridge->bridge_pid()) + ":" + std::to_string(bridge->stats().spawned) : std::string();
  const auto &catalog = viewer_.catalog();
  if (!dirty_ && viewer_version_ == viewer_.version() && bridge == bridge_ && session == session_) { return; }
  const auto next = saved_ ? nullptr : viewer_.graph_inspection();
  const std::optional<ViewerGraphConfiguration> configuration = saved_ ? std::nullopt :
      (displayed_ ? next->shown_configuration : next->desired);
  std::optional<AnalysisGraphDefinition> definition = saved_ ? document_definition_ : std::nullopt;
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

void AnalysisGraphState::show_displayed(const bool displayed)
{
  if (!saved_ && displayed == displayed_) { sync(); return; }
  saved_ = false;
  displayed_ = displayed;
  invalidate_validation();
  // Force a comparison with the newly selected provenance, even if the Viewer did not change.
  dirty_ = true;
  sync();
  viewer_.store().changed();
}

void AnalysisGraphState::show_saved()
{
  if (saved_) { sync(); return; }
  saved_ = true;
  invalidate_validation();
  dirty_ = true;
  sync();
  viewer_.store().changed();
}

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
  if (activate) { saved_ = true; }
  if (saved_) { invalidate_validation(); dirty_ = true; sync(); }
  viewer_.store().changed();
  return true;
}

void AnalysisGraphState::clear_document()
{
  document_definition_.reset(); document_handle_.clear(); document_id_.clear(); document_revision_ = -1;
  if (saved_) { invalidate_validation(); dirty_ = true; sync(); }
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
