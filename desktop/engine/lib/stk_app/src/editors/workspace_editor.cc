/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Workspace: the start page. It walks a new user through the main path (project → parameters →
 * where to run → run → results), shows each step's state from what the app already knows and
 * marks the next step. Buttons only navigate; nothing here runs, sends or changes data.
 */
#include "archive_controls.hh"
#include "editor_text.hh"
#include "project_navigation.hh"

#include "../app_theme.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/module_settings.hh"
#include "stk/app/project_attention.hh"
#include "stk/app/project_search.hh"
#include "stk/app/viewer_state.hh"

namespace stk::app {
namespace {

/* Tables the project manages itself (suan.project.analyses / suan.project.files). */
constexpr const char *kAnalysesTable = "a32844df-b03d-576b-a200-c7080ae8e97e";
constexpr const char *kFilesTable = "becb9ec9-1a27-5d31-8aa3-5402f09f43a9";
constexpr const char *kWorkflowsTable = "88c4e1a0-7427-5d9d-a8f7-49ff00175f26";  // suan/project/workflows.py TABLE_ID

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
    if (project.busy() && !project.notice().empty()) { layout.paragraph(project.notice()); }
    attention(layout, ctx);
    search(layout, ctx);

    const auto &info = project.project();
    const bool available = project.ready() && project.loaded() && !project.busy();
    size_t tables = 0, records = 0;
    if (info) {
      for (const auto &table : project.tables()) {
        if (table.id == kAnalysesTable || table.id == kFilesTable || table.id == kWorkflowsTable) { continue; }
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
      if (!info && project.supports_demo()) {
        // A first look without a server: synthetic data walking the same steps (suan.workflows.demo).
        auto &row = box.row();
        row.button("workspace_demo", ctx.tr("workspace.demo"), [&project] { project.create_demo(); })
            .tip(ctx.tr("workspace.demo.tip")).disable(project.busy());
      }
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
      row.button("workspace_analyses", ctx.tr("workspace.analyses"), project_navigation_action(ctx, "analyses"))
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
    tools.button("workspace_workflows", ctx.tr("workspace.workflows"), project_navigation_action(ctx, "workflows"))
        .disable(!available);
    // The skill library is shared across projects: reachable with or without one.
    tools.button("workspace_skills", ctx.tr("workspace.skills"), editor_navigation_action(ctx, kEditorSkills));
    modules(layout, ctx);
  }

 private:
  /** Optional computation modules (docs/design/multiscale-engines.md): engines for each scale and modeling tools.
   * What is already installed on this computer is detected and used; a missing module is installed on request. */
  void modules(ui::Layout &layout, EditorContext &ctx)
  {
    auto &modules = ctx.store.modules();
    modules.sync();
    if (!modules.supported()) { return; }
    auto *box = layout.panel("workspace_modules", ctx.tr("workspace.modules"), false);
    if (!box) { return; }
    auto &catalog = ctx.store.catalog();
    auto *settings = &modules;
    hint(*box, ctx, "workspace.modules.hint");
    if (!modules.error().empty()) { box->paragraph(modules.error()); }
    if (!modules.loaded()) { box->paragraph(ctx.tr("workspace.modules.reading")); }
    if (modules.detecting()) { box->paragraph(ctx.tr("workspace.modules.detecting")); }
    auto &models = ctx.store.models();
    models.sync();
    const bool online = models.network() == "internet";
    box->button("workspace_modules_detect", ctx.tr("workspace.modules.detect"), [settings] { settings->detect(); })
        .disable(modules.detecting());
    if (!modules.loaded()) { return; }
    for (const auto &item : modules.listing().value("modules", io::Json::array())) {
      const auto id = io::get_string(item, "id"), state = io::get_string(item, "state");
      box->label(io::get_string(item, "name") + " · " + std::string(catalog.tr_or("workspace.modules.scale." +
          io::get_string(item, "scale"), io::get_string(item, "scale"))) + " · " + io::get_string(item, "license"))
          .tip(io::get_string(item, "purpose") + "\n" + io::get_string(item, "homepage"));
      std::string status(catalog.tr_or("workspace.modules.state." + state, state));
      if (!io::get_string(item, "version").empty()) { status += " · " + io::get_string(item, "version"); }
      const auto programs = item.value("programs", io::Json::object());
      if (!programs.empty() && programs.begin()->is_string()) { status += " · " + programs.begin()->get<std::string>(); }
      const auto job = item.value("job", io::Json());
      if (job.is_object()) {
        const auto log = job.value("log", io::Json::array());
        if (state == "installing" && !log.empty()) { status += " · " + log.back().get<std::string>(); }
        if (!io::get_string(job, "error").empty() && state == "missing") { status += " · " + io::get_string(job, "error"); }
      }
      box->paragraph(status);
      if (!modules.installable()) { continue; }
      auto &row = box->row();
      if (state == "missing") {
        row.button("workspace_module_install/" + id, catalog.format("workspace.modules.install",
            {{"size", std::to_string(io::get_int(item, "approximate_mb", 0))}}), [settings, id] { settings->act("install", id); })
            .width(8).disable(modules.busy() || !online || !io::get_bool(item, "installable", false))
            .tip(ctx.tr(online ? "workspace.modules.install.tip" : "models.local.needs_internet"));
      }
      else if (state == "installing") {
        row.button("workspace_module_cancel/" + id, ctx.tr("models.local.cancel"), [settings, id] { settings->act("cancel", id); })
            .width(5);
      }
      else if (state == "installed") {
        row.button("workspace_module_remove/" + id, ctx.tr("models.local.remove"), [settings, id] { settings->act("remove", id); })
            .width(5).disable(modules.busy());
      }
    }
  }

  /** Find names and text in the open project (UX package U3): searching starts on Enter or the
   * button, results are grouped by kind and open where they live. Reads only. */
  void search(ui::Layout &layout, EditorContext &ctx)
  {
    if (!search_) { search_ = std::make_unique<ProjectSearch>(ctx.store); }
    search_->sync();
    if (!search_->supported()) { return; }
    auto &catalog = ctx.store.catalog();
    auto &box = layout.box();
    box.label(ctx.tr("workspace.search.title"));
    auto *state = search_.get();
    const auto weak = lifetime();
    auto start = [this, weak, state] {
      if (!weak.expired()) { state->search(search_text_); }
    };
    auto &row = box.row();
    row.text_field("workspace_search_text", ui::bind(search_text_), {
        .placeholder = std::string(ctx.tr("workspace.search.placeholder")), .max_length = 200, .on_submit = start});
    row.button("workspace_search", ctx.tr("workspace.search.button"), start).width(4).disable(state->busy());
    if (state->busy()) { box.paragraph(ctx.tr("workspace.search.searching")); }
    if (!state->error().empty()) { box.paragraph(state->error()); }
    const auto &result = state->result();
    if (!result.is_object()) { return; }
    const auto &results = result.at("results");
    const auto *info = ctx.store.project().project() ? &*ctx.store.project().project() : nullptr;
    if (info && io::get_int(result, "revision", -1) != info->revision) {
      box.paragraph(ctx.tr("workspace.search.stale"));  // results are not followed by themselves
    }
    if (results.empty()) {
      box.paragraph(catalog.format("workspace.search.none", {{"query", io::get_string(result, "query")}}));
      return;
    }
    std::string kind;
    for (size_t i = 0; i < results.size(); ++i) {
      const auto &item = results[i];
      if (io::get_string(item, "kind") != kind) {
        kind = io::get_string(item, "kind");
        box.label(catalog.format("workspace.search.group", {
            {"kind", std::string(catalog.tr_or("workspace.search.kind." + kind, kind))},
            {"count", std::to_string(io::get_int(member(result, "counts"), kind.c_str(), 0))}}));
      }
      auto &line = box.row();
      line.label(result_text(ctx, item)).tip(io::get_string(item, "text"));
      const auto open = navigation(ctx, item.value("target", io::Json::object()));
      line.button("workspace_search_open/" + std::to_string(i), ctx.tr("workspace.search.open"), [open] {
        if (open) { open(); }
      }).width(3).disable(!open);
    }
    if (io::get_bool(result, "truncated", false)) { box.paragraph(ctx.tr("workspace.search.truncated")); }
  }

  static const io::Json &member(const io::Json &value, const char *key)
  {
    static const io::Json kNull;
    return value.is_object() && value.contains(key) ? value.at(key) : kNull;
  }

  /** "Cases · note · row 2: thin film …", "Scan", "field.vtk · /data/case-1/field.vtk", ... */
  static std::string result_text(EditorContext &ctx, const io::Json &item)
  {
    auto &catalog = ctx.store.catalog();
    const auto kind = io::get_string(item, "kind"), name = io::get_string(item, "name"), text = io::get_string(item, "text");
    if (kind == "field") { return io::get_string(item, "table") + " · " + name; }
    if (kind == "cell") {
      return catalog.format("workspace.search.cell", {{"table", io::get_string(item, "table")}, {"field", name},
          {"row", std::to_string(io::get_int(item, "row", 0))}, {"text", text}});
    }
    if (kind == "file") { return name.empty() ? text : name + " · " + text; }
    if (kind == "draft") {
      const auto status = io::get_string(item, "status");
      return name + " · " + std::string(catalog.tr_or("workspace.search.draft." + status, status));
    }
    if (kind == "message") {
      return std::string(ctx.tr(io::get_string(item, "role") == "assistant" ? "workspace.search.assistant" : "workspace.search.you")) +
          "：" + text;
    }
    return name;
  }

  /** What needs a person, what runs and what finished (UX package U1); failures first. Opening an item
   * navigates to it and marks it viewed; nothing here runs or changes the project. */
  void attention(ui::Layout &layout, EditorContext &ctx)
  {
    auto &state = ctx.store.attention();
    state.sync();
    if (!state.supported()) { return; }
    auto &box = layout.box();
    box.label(ctx.tr("workspace.attention.title"));
    static const io::Json kNone = io::Json::array();
    const auto &items = state.result().is_object() ? state.result().at("items") : kNone;
    if (!state.error().empty()) { box.paragraph(state.error()); }
    std::vector<const io::Json *> needs, running, done;
    for (const auto &item : items) {
      const auto group = io::get_string(item, "group");
      if (group == "needs_you" && !io::get_bool(item, "viewed", false)) { needs.push_back(&item); }
      else if (group == "running") { running.push_back(&item); }
      else if (group == "done" && !io::get_bool(item, "viewed", false)) { done.push_back(&item); }
    }
    if (needs.empty() && running.empty() && done.empty()) {
      box.paragraph(ctx.tr(state.result().is_null() ? "workspace.attention.loading" : "workspace.attention.none"));
      return;
    }
    auto &catalog = ctx.store.catalog();
    const auto group = [&](const char *title, const std::vector<const io::Json *> &list, size_t limit, bool seen) {
      if (list.empty()) { return; }
      box.label(catalog.format(title, {{"count", std::to_string(list.size())}}));
      for (size_t i = 0; i < list.size() && i < limit; ++i) { entry(box, ctx, *list[i], seen); }
      if (list.size() > limit) {
        box.paragraph(catalog.format("workspace.attention.more", {{"count", std::to_string(list.size() - limit)}}));
      }
    };
    group("workspace.attention.needs_you", needs, 6, true);
    group("workspace.attention.running", running, 4, false);
    group("workspace.attention.done", done, 4, true);
    if (!done.empty()) {
      std::vector<std::string> keys;
      for (const auto *item : done) { keys.push_back(io::get_string(*item, "key")); }
      auto *attention = &state;
      box.button("workspace_attention_seen_all", ctx.tr("workspace.attention.seen_all"), [attention, keys] {
        attention->mark_viewed(keys);
      });
    }
  }

  /** One line ("失败 · 工作流运行 · 温度扫描 · 完成 1/2") with Open and, unless running, Seen. */
  void entry(ui::Layout &box, EditorContext &ctx, const io::Json &item, const bool seen)
  {
    auto &catalog = ctx.store.catalog();
    const auto kind = io::get_string(item, "kind"), status = io::get_string(item, "status"), key = io::get_string(item, "key");
    std::string detail;
    if (item.contains("counts") && item.at("counts").is_object()) {
      int64_t total = 0;
      for (const auto &[name, value] : item.at("counts").items()) {
        (void)name;
        if (value.is_number_integer()) { total += value.get<int64_t>(); }
      }
      detail = " · " + catalog.format("workspace.attention.counts", {{"done", std::to_string(io::get_int(item.at("counts"), "succeeded", 0))},
                                                                   {"total", std::to_string(total)}});
    }
    const auto name = io::get_string(item, "name");
    const std::string text = std::string(catalog.tr_or("workspace.attention.state." + status, status)) + " · " +
        std::string(catalog.tr_or("workspace.attention.kind." + kind, kind)) + (name.empty() ? std::string() : " · " + name) + detail;
    auto &row = box.row();
    auto &label = row.label(text);
    if (const auto error = io::get_string(item, "error"); !error.empty()) { label.tip(error); }
    auto *attention = &ctx.store.attention();
    const auto open = navigation(ctx, item.value("target", io::Json::object()));
    row.button("workspace_attention_open/" + key, ctx.tr("workspace.attention.open"), [attention, key, open, seen] {
      if (seen) { attention->mark_viewed({key}); }
      if (open) { open(); }
    }).width(3).disable(!open);
    if (seen) {
      row.button("workspace_attention_seen/" + key, ctx.tr("workspace.attention.seen"), [attention, key] {
        attention->mark_viewed({key});
      }).width(3);
      // Put away for good (format 11): it leaves this list and its own list until restored there. Agent sessions
      // cannot be archived yet (v1); "seen" puts them aside.
      if (kind != "agent_session") {
        if (auto *shelve = archive_button(row, ctx, kind, io::get_string(item, "id"), "workspace_attention_archive/" + key)) {
          shelve->width(3);
        }
      }
    }
  }

  /** Where an attention item lives: an editor with a target, or a project page. */
  std::function<void()> navigation(EditorContext &ctx, const io::Json &target)
  {
    const auto page = io::get_string(target, "page");
    if (page == "data" || page == "files") {
      // A search result names its table and row; open the page with them selected.
      const auto handle = ctx.store.project().project() ? ctx.store.project().project()->handle : std::string();
      auto *area = &ctx.area;
      auto *editor = &area->editor();
      const auto weak = editor->lifetime();
      const auto table = io::get_string(target, "table_id"), record = io::get_string(target, "record_id");
      return [area, editor, weak, handle, page, table, record] {
        if (weak.expired() || &area->editor() != editor) { return; }
        area->shell().open_project_page_later(area->screen(), page, handle, [weak, area, editor] {
          return !weak.expired() && &area->editor() == editor;
        }, table, record);
      };
    }
    if (!page.empty()) { return project_navigation_action(ctx, page); }
    const auto editor = io::get_string(target, "editor");
    if (editor != kEditorWorkflow && editor != kEditorAnalysisGraph && editor != kEditorAI) { return {}; }
    auto *shell = &ctx.area.shell();
    auto *screen = ctx.area.screen();
    const auto weak = lifetime();
    return [shell, screen, weak, editor, target] {
      if (weak.expired()) { return; }
      shell->open_target_later(screen, editor, target, [weak] { return !weak.expired(); });
    };
  }

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

  std::unique_ptr<ProjectSearch> search_;
  std::string search_text_;
};

}  // namespace
std::unique_ptr<Editor> make_workspace_editor(const EditorType &type)
{
  return std::make_unique<WorkspaceEditor>(type);
}
}  // namespace stk::app
