/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/project_context_selection.hh"
#include <memory>
#include <string>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

/** Editor-local, explicitly saved capture scope. Never changes shared table selection. */
class ProjectContextPicker {
 public:
  ~ProjectContextPicker() { alive_.reset(); }
  bool active() const { return active_; }
  void close();
  void begin(ProjectState &state);
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
 private:
  ProjectContextSelection selection_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::shared_ptr<const ProjectTable> table_;
  bool active_ = false;
  int category_ = 0, row_page_ = 0, field_page_ = 0;
  std::string title_;
};
}  // namespace stk::app
