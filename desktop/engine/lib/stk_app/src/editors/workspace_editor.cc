/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_navigation.hh"

namespace stk::app {
namespace {

class WorkspaceEditor final : public Editor {
 public:
  explicit WorkspaceEditor(const EditorType &type) : Editor(type) {}

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &project = ctx.store.project();
    project.sync();
    layout.label(ctx.tr("workspace.title"));
    layout.paragraph(ctx.tr("workspace.intro"));
    if (project.project()) {
      layout.label(project.project()->name);
      layout.paragraph(project.project()->directory);
      layout.label(ctx.store.catalog().format("project.revision", {{"revision", std::to_string(project.project()->revision)}}));
    }
    else { layout.paragraph(ctx.tr("workspace.open_project")); }
    if (!project.error().empty()) { layout.paragraph(project.error()); }
    const bool available = project.ready() && project.loaded() && !project.busy();
    auto action = [&](const char *page, const char *title, const char *hint, bool enabled) {
      auto &box = layout.box();
      const std::string destination(page);
      box.button(std::string("workspace_") + page, ctx.tr(title),
                 project_navigation_action(ctx, destination)).disable(!enabled);
      box.paragraph(ctx.tr(hint));
    };
    action("conversation", "workspace.conversation", "workspace.conversation_hint", available);
    action("files", "workspace.files", "workspace.files_hint", available);
    action("workflows", "workspace.workflows", "workspace.workflows_hint", available);
    auto &runs = layout.box();
    runs.label(ctx.tr("workspace.runs"));
    runs.paragraph(ctx.tr("workspace.runs_hint"));
    for (const auto *page : {"analysis_runs", "simulation_runs"}) {
      runs.button(std::string("workspace_") + page, ctx.tr(std::string("workspace.") + page),
          project_navigation_action(ctx, page)).disable(!available);
    }
    action("data", "workspace.data", "workspace.data_hint", available);
    action("project", "project.location", "workspace.project_hint", !project.busy());
  }
};

}  // namespace
std::unique_ptr<Editor> make_workspace_editor(const EditorType &type)
{
  return std::make_unique<WorkspaceEditor>(type);
}
}  // namespace stk::app
