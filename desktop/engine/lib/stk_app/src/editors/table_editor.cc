/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include "stk/app/table_workbench.hh"
#include "project_navigation.hh"

namespace stk::app {
namespace {

/** A table-only editor. ProjectState owns the shared data and selection; the component owns
 * this tab's filter and unsaved cell/name drafts. Project management stays in ProjectEditor. */
class TableEditor final : public Editor {
 public:
  explicit TableEditor(const EditorType &type) : Editor(type) {}
  bool show_view(const std::string_view view) override { return view == "data"; }
  bool can_change_project_selection(const std::string_view project_id) const override
  {
    return tables_.can_change_project_selection(project_id);
  }
  bool has_unsaved_changes() const override { return tables_.has_unsaved_changes(); }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    row.button("table_project", ctx.tr("project.location"), project_navigation_action(ctx, "project")).width(8);
    row.button("project_refresh", ctx.tr("project.refresh"), [&state] { state.refresh(); })
        .width(5).disable(!state.ready() || !state.project() || state.busy());
    row.button("project_undo", ctx.tr("project.undo"), [&state] { state.undo(); })
        .width(4).disable(!state.ready() || state.busy() || !state.can_undo());
    row.button("project_redo", ctx.tr("project.redo"), [&state] { state.redo(); })
        .width(4).disable(!state.ready() || state.busy() || !state.can_redo());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    if (!state.ready()) { layout.paragraph(ctx.tr("project.bridge_required")); }
    if (!state.error().empty()) { layout.paragraph(state.error()); }
    if (!state.notice().empty()) { layout.paragraph(state.notice()); }
    if (state.busy()) { layout.label(ctx.tr("project.busy")); }
    if (!state.project()) {
      layout.paragraph(ctx.tr("project.intro"));
      layout.button("table_open_project", ctx.tr("project.location"), project_navigation_action(ctx, "project"));
      return;
    }
    if (!state.loaded()) { return; }
    tables_.draw(layout, ctx);
  }
  nlohmann::json save_state() const override { return tables_.save_state(); }
  bool load_state(const nlohmann::json &state) override { return tables_.load_state(state); }
  nlohmann::json save_workspace_state() const override { return tables_.save_workspace_state(); }
  bool load_workspace_state(const nlohmann::json &state) override { return tables_.load_workspace_state(state); }

 private:
  TableWorkbench tables_;
};
}  // namespace

std::unique_ptr<Editor> make_table_editor(const EditorType &type)
{
  return std::make_unique<TableEditor>(type);
}
}  // namespace stk::app
