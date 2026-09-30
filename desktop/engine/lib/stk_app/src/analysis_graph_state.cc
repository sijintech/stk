/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_state.hh"

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
  auto *bridge = viewer_.store().bridge();
  const std::string session = bridge && bridge->state() == bridge::BridgeState::Ready ?
      std::to_string(bridge->bridge_pid()) + ":" + std::to_string(bridge->stats().spawned) : std::string();
  const auto next = viewer_.graph_inspection();
  const auto &catalog = viewer_.catalog();
  if (next == inspection_ && bridge == bridge_ && session == session_) { return; }
  const auto &configuration = displayed_ ? next->shown_configuration : next->desired;
  const bool catalog_changed = !same_json(catalog, catalog_);
  const bool changed = !same_configuration(configuration_, configuration) || catalog_changed;
  const bool graph_changed = bool(configuration_) != bool(configuration) || catalog_changed ||
      (configuration_ && configuration && !same_json(configuration_->graph, configuration->graph));
  if (changed || bridge != bridge_ || session != session_) { invalidate_validation(); }
  bridge_ = bridge;
  session_ = session;
  inspection_ = next;
  if (!changed) { return; }
  configuration_ = configuration;
  catalog_ = catalog;
  if (!graph_changed) { return; }
  view_.reset();
  error_.clear();
  if (!configuration_) { return; }
  try {
    const io::Graph graph = io::Graph::from_json(configuration_->graph);
    std::optional<io::Catalog> types;
    if (!catalog_.is_null()) { types = io::Catalog::from_json(catalog_); }
    view_ = std::make_shared<const AnalysisGraphView>(analysis_graph_view(graph, types ? &*types : nullptr));
  }
  catch (const std::exception &error) { error_ = error.what(); }
}

void AnalysisGraphState::show_displayed(const bool displayed)
{
  if (displayed == displayed_) { sync(); return; }
  displayed_ = displayed;
  invalidate_validation();
  // Force a comparison with the newly selected provenance, even if the Viewer did not change.
  inspection_.reset();
  sync();
  viewer_.store().changed();
}

bool AnalysisGraphState::validation_available() const
{
  if (!configuration_ || !view_ || !bridge_ || session_.empty()) { return false; }
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
  validation_future_ = bridge_->graph_validate(configuration_->graph, configuration_->parameters);
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
