/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/project_review.hh"
#include "stk/ui/log_buffer.hh"
#include <memory>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

/** View-local selection/scroll content; the transient draft itself is shared by ProjectState. */
class ProjectReviewView {
 public:
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
 private:
  std::shared_ptr<const ProjectReview> shown_;
  int selected_ = 0, category_ = 0, details_row_ = -1, details_category_ = -1;
  ui::LogBuffer details_, commands_;
};
}  // namespace stk::app
