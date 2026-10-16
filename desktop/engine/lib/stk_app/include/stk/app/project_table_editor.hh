/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

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
  io::Json save_workspace_state() const;
  bool load_workspace_state(const io::Json &);
  /** Select a field from a companion grid; refuses to abandon this component's draft. */
  void select_field(std::string_view id);
  /** A companion grid supplies its visible stable rows, preserving this form's stale-action fence. */
  void set_visible_records(std::vector<std::string> ids);
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
