/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"

namespace stk::app {

inline std::function<void()> project_navigation_action(EditorContext &ctx, std::string page)
{
  auto &project = ctx.store.project();
  const auto handle = project.project() ? project.project()->handle : std::string();
  auto *area = &ctx.area;
  auto *editor = &area->editor();
  const auto weak = editor->lifetime();
  const auto shell_weak = area->shell().lifetime();
  return [weak, shell_weak, area, editor, handle, page = std::move(page)] {
    if (shell_weak.expired() || weak.expired() || &area->editor() != editor) { return; }
    area->shell().open_project_page_later(area->screen(), page, handle, [weak, area, editor] {
      return !weak.expired() && &area->editor() == editor;
    });
  };
}

/** Global navigation (no project scope), e.g. the shared skill library. */
inline std::function<void()> editor_navigation_action(EditorContext &ctx, std::string editor_id)
{
  auto *area = &ctx.area;
  auto *editor = &area->editor();
  const auto weak = editor->lifetime();
  const auto shell_weak = area->shell().lifetime();
  return [weak, shell_weak, area, editor, editor_id = std::move(editor_id)] {
    if (shell_weak.expired() || weak.expired() || &area->editor() != editor) { return; }
    area->shell().activate_editor_later(area->screen(), editor_id, true, [weak, area, editor] {
      return !weak.expired() && &area->editor() == editor;
    });
  };
}

inline void workspace_link(ui::Layout &row, EditorContext &ctx)
{
  // Widget callbacks can be retained by a menu or an integration after this frame.
  row.button("project_workspace", ctx.tr("editor.workspace.title"),
             project_navigation_action(ctx, "workspace")).width(6);
}

}  // namespace stk::app
