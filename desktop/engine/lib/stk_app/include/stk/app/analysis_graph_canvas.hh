/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_graph_view.hh"
#include "stk/ui/draw_list.hh"

#include <memory>
#include <optional>
#include <string_view>
#include <utility>

namespace stk::app {

/** CPU-only, read-only graph canvas. Coordinates are physical pixels local to its viewport,
 * origin top-left. Drawing changes neither the graph nor selection and performs no GPU calls.
 * Pan/zoom are ephemeral; a different view pointer resets them. The caller owns event routing. */
class AnalysisGraphCanvas {
 public:
  static constexpr double min_zoom = 0.00001, max_zoom = 2.5;
  /** A different view resets pan/zoom unless `keep_transform` (an edited version of the same graph). */
  void set_view(std::shared_ptr<const AnalysisGraphView> view, bool keep_transform = false);
  const std::shared_ptr<const AnalysisGraphView> &view() const { return view_; }

  /** Fit the immutable bounds with 32*ui_scale pixel padding, reduced for tiny viewports.
   * Finite, positive dimensions and a UI scale in [0.25,8] are required. Invalid input, empty
   * views or invalid bounds return false and retain the existing transform. */
  bool fit(double width, double height, double ui_scale = 1);
  bool pan(double dx, double dy);
  /** Show graph point `center` in the middle of a width x height viewport at `zoom` (clamped to the
   * limits), independent of the previous transform: restores a remembered view at any window size or
   * UI scale. Invalid input or an empty view returns false and retains the transform. */
  bool look_at(AnalysisGraphPoint center, double zoom, double width, double height, double ui_scale = 1);
  /** The graph point in the middle of the last fitted or drawn viewport, if there was one. */
  std::optional<AnalysisGraphPoint> center() const;
  /** Preserve the world point under the physical-pixel anchor; invalid inputs return false. */
  bool zoom_at(double factor, double x, double y);
  /** Last drawn node wins for overlap; points outside the last fit/draw viewport cannot hit. */
  std::optional<size_t> hit(double x, double y) const;
  struct PortHit {
    size_t node = 0, port = 0;
    bool output = false;
  };
  /** The declared or referenced port whose socket is nearest within 8 UI pixels, if any. */
  std::optional<PortHit> hit_port(double x, double y) const;
  /** A link being dragged, in viewport pixels (drawn over the graph until cleared). */
  void set_pending_link(std::optional<std::pair<AnalysisGraphPoint, AnalysisGraphPoint>> link) { pending_link_ = link; }

  /** Clipped background/grid, curves, nodes and typed ports. Fine labels are hidden at overview
   * zooms. A DPI change preserves the world point at the viewport center without implicitly
   * fitting; ordinary viewport resizing preserves pan/zoom. Call fit explicitly when desired.
   * Invalid dimensions/scales return an empty list. Only the model's bounded visible entries
   * are drawn; malformed geometry is skipped before conversion from double to float. */
  ui::DrawList draw_list(double width, double height, double ui_scale,
                        const ui::TextMeasurer &measurer, std::string_view language,
                        std::optional<size_t> selected = {});

  double zoom() const { return zoom_; }
  double pan_x() const { return pan_x_; }
  double pan_y() const { return pan_y_; }
  double ui_scale() const { return ui_scale_; }
  AnalysisGraphPoint to_screen(AnalysisGraphPoint point) const;
  AnalysisGraphPoint to_graph(AnalysisGraphPoint point) const;

 private:
  std::shared_ptr<const AnalysisGraphView> view_;
  std::optional<std::pair<AnalysisGraphPoint, AnalysisGraphPoint>> pending_link_;
  double zoom_ = 1, pan_x_ = 0, pan_y_ = 0, ui_scale_ = 1;
  double width_ = 0, height_ = 0;
};

}  // namespace stk::app
