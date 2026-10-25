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
  void pin(ProjectState &state, const ProjectTable &table, const std::string &seed = {});
  void read_page(ProjectState &state, int64_t offset, const std::string &seed = {}, bool reset = false);
  void turn_page(ProjectState &state, int64_t page);
  ProjectContextSelection selection_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::shared_ptr<const ProjectTable> table_;
  bool active_ = false, loading_ = false;
  int category_ = 0;
  int64_t row_page_ = 0, field_page_ = 0;
  uint64_t request_generation_ = 0;
  std::string title_, load_error_;
};
}  // namespace stk::app
