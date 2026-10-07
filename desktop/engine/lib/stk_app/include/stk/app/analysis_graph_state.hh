/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_graph_view.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/future.hh"

#include <memory>
#include <optional>

namespace stk::app {

/** An inspectable definition has no implied data source, execution, or result. */
struct AnalysisGraphDefinition {
  io::Json graph, parameters;
  std::vector<std::string> requested_outputs;
};

/** Immutable provenance captured with the same run definition. No lifecycle status, result or
 * historical execution environment is inferred from these references. */
struct AnalysisGraphRunSource {
  std::string id, project_id, analysis_id, analysis_name, created_at;
  std::string snapshot_id, snapshot_sha256, plan_sha256;
  int64_t source_revision = -1;
  io::Json bindings;
};

/** Editor-local, read-only inspection. sync() never pumps/evaluates the Viewer or sends requests.
 * ensure_catalog() reads node metadata; validate() checks the exact inspected graph/parameters.
 * Results from another configuration, bridge session, mode, or destroyed editor are ignored. */
class AnalysisGraphState {
 public:
  enum class Source { Current, Displayed, Saved, Run };
  explicit AnalysisGraphState(ViewerState &viewer);
  ~AnalysisGraphState();
  AnalysisGraphState(const AnalysisGraphState &) = delete;
  AnalysisGraphState &operator=(const AnalysisGraphState &) = delete;

  void sync();
  /** Read missing node metadata once per ready bridge session, independently of Viewer work.
   * An already available Viewer catalog is reused. No redraw-driven retries after an error. */
  bool ensure_catalog();
  bool catalog_loading() const { return catalog_loading_; }
  /** The node catalog document once read (null before). */
  const io::Json &catalog() const { return catalog_; }
  const std::string &catalog_error() const { return catalog_error_; }
  Source source() const { return source_; }
  void show_displayed(bool displayed);
  bool displayed() const { return source_ == Source::Displayed; }
  void show_saved();
  bool saved() const { return source_ == Source::Saved; }
  void show_run();
  /** Explicitly inspect an already-read run. Only bounded immutable fields are copied; no run
   * is loaded, executed, polled or attached to the Viewer. Invalid input preserves the old view.
   * An opening handle or ready bridge session change clears this snapshot in every mode. */
  bool open_frozen_run(const std::string &handle, const io::Json &run);
  void clear_run();
  const AnalysisGraphRunSource *frozen_run() const { return run_source_ ? &*run_source_ : nullptr; }
  /** Accept a copied project definition for the currently open project. Loading it never changes
   * the Viewer; the opening handle fences the document and pending validation after close/reopen. */
  bool open_document(const std::string &handle, const std::string &analysis_id,
                     int64_t revision, const io::Json &document, bool activate = true);
  void clear_document();
  const std::string &document_id() const { return document_id_; }
  int64_t document_revision() const { return document_revision_; }
  bool document_stale() const;
  const AnalysisGraphDefinition *definition() const { return definition_ ? &*definition_ : nullptr; }
  /** Null in Saved/Run mode. These definitions have no current Viewer receipt attached. */
  const std::shared_ptr<const ViewerGraphInspection> &inspection() const { return inspection_; }
  /** Only present in a Viewer mode. Saved documents and runs never fabricate a Viewer source. */
  const ViewerGraphConfiguration *configuration() const;
  const std::shared_ptr<const AnalysisGraphView> &view() const { return view_; }
  const std::string &error() const { return error_; }
  uint64_t generation() const { return generation_; }

  bool validate();
  bool validation_available() const;
  bool validating() const { return validating_; }
  /** Null until a successful response; {ok, issues}. Validation is distinct from presentation
   * diagnostics and never checks whether source file contents still match a previous run. */
  const io::Json &validation() const { return validation_; }
  const std::string &validation_error() const { return validation_error_; }

 private:
  void invalidate_validation();
  void reset_catalog_request();
  void set_source(Source source);
  ViewerState &viewer_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  Source source_ = Source::Current;
  bool validating_ = false, dirty_ = true;
  uint64_t generation_ = 0, viewer_version_ = 0;
  bridge::Client *bridge_ = nullptr;
  std::string session_;
  std::shared_ptr<const ViewerGraphInspection> inspection_;
  std::optional<ViewerGraphConfiguration> configuration_;
  std::optional<AnalysisGraphDefinition> definition_, document_definition_, run_definition_;
  std::optional<AnalysisGraphRunSource> run_source_;
  std::string run_handle_;
  std::string document_handle_, document_id_;
  int64_t document_revision_ = -1;
  io::Json catalog_, independent_catalog_, validation_;
  bool catalog_requested_ = false, catalog_loading_ = false;
  uint64_t catalog_request_generation_ = 0;
  std::shared_ptr<const AnalysisGraphView> view_;
  std::string error_, validation_error_, catalog_error_;
  std::optional<bridge::Future<io::Json>> validation_future_, catalog_future_;
};

}  // namespace stk::app
