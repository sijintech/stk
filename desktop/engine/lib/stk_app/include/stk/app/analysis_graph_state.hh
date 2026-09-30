/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_graph_view.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/future.hh"

#include <memory>
#include <optional>

namespace stk::app {

/** Editor-local, read-only inspection. sync() never pumps/evaluates the Viewer. Only validate()
 * sends a bridge request, for the exact graph and submitted parameters currently inspected.
 * Results from another configuration, bridge session, mode, or destroyed editor are ignored. */
class AnalysisGraphState {
 public:
  explicit AnalysisGraphState(ViewerState &viewer);
  ~AnalysisGraphState();
  AnalysisGraphState(const AnalysisGraphState &) = delete;
  AnalysisGraphState &operator=(const AnalysisGraphState &) = delete;

  void sync();
  void show_displayed(bool displayed);
  bool displayed() const { return displayed_; }
  const std::shared_ptr<const ViewerGraphInspection> &inspection() const { return inspection_; }
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
  ViewerState &viewer_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bool displayed_ = false, validating_ = false;
  uint64_t generation_ = 0;
  bridge::Client *bridge_ = nullptr;
  std::string session_;
  std::shared_ptr<const ViewerGraphInspection> inspection_;
  std::optional<ViewerGraphConfiguration> configuration_;
  io::Json catalog_, validation_;
  std::shared_ptr<const AnalysisGraphView> view_;
  std::string error_, validation_error_;
  std::optional<bridge::Future<io::Json>> validation_future_;
};

}  // namespace stk::app
