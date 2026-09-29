/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/ui/log_buffer.hh"
#include "stk/app/project_table_view.hh"
#include <memory>
#include <string>
#include <vector>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

class ProjectDiscussionView {
 public:
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state, int &project_view);
 private:
  void capture_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
  void captured_cells(ui::Layout &layout, EditorContext &ctx);
  std::string project_, title_, text_, table_, row_, field_, selected_, shown_context_, shown_message_;
  std::vector<std::string> rows_, fields_;
  int category_ = 0;
  ui::LogBuffer context_details_, message_text_;
  std::shared_ptr<const CapturedProjectTable> captured_;
  std::string captured_error_;
  int captured_selected_ = 0, captured_detail_ = -1;
  ui::LogBuffer cell_details_;
};
}  // namespace stk::app
