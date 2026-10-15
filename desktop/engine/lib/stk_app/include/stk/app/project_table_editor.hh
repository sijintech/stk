/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <functional>
#include <memory>
#include <string_view>

namespace stk::ui { class Layout; }

namespace stk::app {
struct EditorContext;
class ProjectState;

/** Reusable project-table controls. Owns view/draft state only; the project,
 * values, definitions and revisions remain in the shared ProjectState/service. */
class ProjectTableEditor {
 public:
  ProjectTableEditor();
  ~ProjectTableEditor();
  ProjectTableEditor(const ProjectTableEditor &) = delete;
  ProjectTableEditor &operator=(const ProjectTableEditor &) = delete;

  bool can_change_project_selection(std::string_view project_id) const;
  bool has_unsaved_changes() const;
  void controls(ui::Layout &, EditorContext &, ProjectState &, bool editable);
  void fields(ui::Layout &, EditorContext &, ProjectState &, bool editable, bool expanded = false);
  void sweep(ui::Layout &, EditorContext &, ProjectState &, bool editable);
  void grid(ui::Layout &, EditorContext &, ProjectState &);
  bool selected_visible(const ProjectState &) const;
  void cell(ui::Layout &, EditorContext &, ProjectState &, bool editable, std::function<void()> open_review);
  void management(ui::Layout &, EditorContext &, ProjectState &, bool editable);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace stk::app
