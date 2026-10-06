/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Workspace: the start page. It walks a new user through the main path (project → parameters →
 * where to run → run → results), shows each step's state from what the app already knows and
 * marks the next step. Buttons only navigate; nothing here runs, sends or changes data.
 */
#include "project_navigation.hh"

#include "../app_theme.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/viewer_state.hh"

namespace stk::app {
namespace {

/* Tables the project manages itself (suan.project.analyses / suan.project.files). */
constexpr const char *kAnalysesTable = "a32844df-b03d-576b-a200-c7080ae8e97e";
constexpr const char *kFilesTable = "becb9ec9-1a27-5d31-8aa3-5402f09f43a9";

const char *health_key(const Health health)
{
  switch (health) {
    case Health::Online: return "workspace.health.online";
    case Health::Checking: return "workspace.health.checking";
    case Health::Degraded: return "workspace.health.degraded";
    case Health::Offline: return "workspace.health.offline";
    case Health::Unknown: break;
  }
  return "workspace.health.unknown";
}

class WorkspaceEditor final : public Editor {
 public:
  explicit WorkspaceEditor(const EditorType &type) : Editor(type) {}

  // The same panel tone as Jobs, Properties and Logs beside it in the default layout.
  ui::Color main_background(const ui::Theme & /*theme*/) const override { return theme::kListBack; }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &project = ctx.store.project();
    project.sync();
    auto &jobs = ctx.store.jobs();
    jobs.sync();
    auto &catalog = ctx.store.catalog();
    layout.label(ctx.tr("workspace.title"));
    layout.paragraph(ctx.tr("workspace.intro"));
    service(layout, ctx);
    if (!project.error().empty()) { layout.paragraph(project.error()); }

    const auto &info = project.project();
    const bool available = project.ready() && project.loaded() && !project.busy();
    size_t tables = 0, records = 0;
    if (info) {
      for (const auto &table : project.tables()) {
        if (table.id == kAnalysesTable || table.id == kFilesTable) { continue; }
        ++tables;
        records += table.records.size();
      }
    }
    const auto *runtime = jobs.active();
    const bool runtime_ready = runtime && runtime->health == Health::Online;
    // The first step that is not done yet; steps 4-5 depend on the user's intent.
    const int next = !info ? 1 : records == 0 ? 2 : !runtime_ready ? 3 : 4;

    {
      auto &box = step(layout, ctx, 1, "workspace.step.project", next);
      box.paragraph(info ? catalog.format("workspace.status.project", {{"name", info->name}}) :
                           std::string(ctx.tr("workspace.status.no_project")));
      button(box, ctx, "project", "workspace.open_project_button", !project.busy());
    }
    {
      auto &box = step(layout, ctx, 2, "workspace.step.parameters", next);
      box.paragraph(info ? catalog.format("workspace.status.tables", {{"tables", std::to_string(tables)},
                                                                      {"records", std::to_string(records)}}) :
                           std::string(ctx.tr("workspace.status.needs_project")));
      button(box, ctx, "data", "workspace.data", available);
    }
    {
      auto &box = step(layout, ctx, 3, "workspace.step.runtime", next);
      if (runtime) {
        box.paragraph(catalog.format("workspace.status.runtime", {
            {"name", runtime->info.name.empty() ? runtime->info.id : runtime->info.name},
            {"health", std::string(ctx.tr(health_key(runtime->health)))}}));
      }
      else { box.paragraph(ctx.tr("workspace.status.no_runtime")); }
      auto &row = box.row();
      row.button("workspace_runtime", ctx.tr("workspace.runtime"), editor_navigation_action(ctx, kEditorJobs, true));
    }
    {
      auto &box = step(layout, ctx, 4, "workspace.step.run", next);
      box.paragraph(ctx.tr(info ? "workspace.status.run" : "workspace.status.needs_project"));
      auto &row = box.row();
      for (const auto *page : {"simulation_runs", "analysis_runs"}) {
        row.button(std::string("workspace_") + page, ctx.tr(std::string("workspace.") + page),
                   project_navigation_action(ctx, page)).disable(!available);
      }
    }
    {
      auto &box = step(layout, ctx, 5, "workspace.step.results", next);
      const auto &viewer = ctx.store.viewer();
      box.paragraph(viewer.payload() ? std::string(ctx.tr("workspace.status.result_shown")) :
                                       std::string(ctx.tr("workspace.status.no_result")));
      auto &row = box.row();
      row.button("workspace_workflows", ctx.tr("workspace.workflows"), project_navigation_action(ctx, "workflows"))
          .disable(!available);
      row.button("workspace_viewer", ctx.tr("workspace.viewer"), editor_navigation_action(ctx, kEditorViewer, false));
    }

    // Tools used along the way rather than steps of their own.
    auto &more = layout.box();
    more.label(ctx.tr("workspace.more"));
    auto &tools = more.row();
    tools.button("workspace_conversation", ctx.tr("workspace.conversation"), project_navigation_action(ctx, "conversation"))
        .disable(!available);
    tools.button("workspace_files", ctx.tr("workspace.files"), project_navigation_action(ctx, "files")).disable(!available);
    // The skill library is shared across projects: reachable with or without one.
    tools.button("workspace_skills", ctx.tr("workspace.skills"), editor_navigation_action(ctx, kEditorSkills));
  }

 private:
  static void service(ui::Layout &layout, EditorContext &ctx)
  {
    // The background Python service in plain words; nothing to say once it is ready.
    switch (ctx.store.bridge_state()) {
      case BridgeState::Ready: return;
      case BridgeState::Failed: {
        layout.paragraph(ctx.store.catalog().format("workspace.service.failed", {{"error", ctx.store.bridge_error()}}));
        return;
      }
      case BridgeState::Starting: layout.paragraph(ctx.tr("workspace.service.starting")); return;
      case BridgeState::Restarting: layout.paragraph(ctx.tr("workspace.service.restarting")); return;
      case BridgeState::Stopping:
      case BridgeState::NotStarted: layout.paragraph(ctx.tr("workspace.service.not_started")); return;
    }
  }

  static ui::Layout &step(ui::Layout &layout, EditorContext &ctx, const int number, const char *title, const int next)
  {
    auto &box = layout.box();
    std::string heading = std::to_string(number) + ". " + std::string(ctx.tr(title));
    if (number == next) { heading += "  ·  " + std::string(ctx.tr("workspace.next")); }
    auto &label = box.label(heading);
    if (number == next) { label.backdrop(); }
    return box;
  }

  static void button(ui::Layout &box, EditorContext &ctx, const char *page, const char *text, const bool enabled)
  {
    auto &row = box.row();
    row.button(std::string("workspace_") + page, ctx.tr(text), project_navigation_action(ctx, page)).disable(!enabled);
  }
};

}  // namespace
std::unique_ptr<Editor> make_workspace_editor(const EditorType &type)
{
  return std::make_unique<WorkspaceEditor>(type);
}
}  // namespace stk::app
