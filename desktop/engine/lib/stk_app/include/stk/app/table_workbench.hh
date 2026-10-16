/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <memory>
#include <string_view>
#include "stk/io/json.hh"
namespace stk::ui { class Layout; }
namespace stk::app {
struct EditorContext;
/** Dedicated table workspace. Grid interaction, view state and drafts are per editor;
 * persisted values, schemas, named views and history use the shared project service. */
class TableWorkbench {
 public:
  TableWorkbench();
  ~TableWorkbench();
  bool has_unsaved_changes() const;
  bool can_change_project_selection(std::string_view project_id) const;
  void draw(ui::Layout &, EditorContext &);
  io::Json save_state() const;
  bool load_state(const io::Json &);
  io::Json save_workspace_state() const;
  bool load_workspace_state(const io::Json &);
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
