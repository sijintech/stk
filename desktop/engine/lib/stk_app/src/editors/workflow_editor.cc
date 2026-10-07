/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Workflow editor (P3 W3b, docs/design/project-workflows.md): shows a project workflow on the
 * analysis graph canvas, lists its validation issues and the selected step, and navigates to the
 * object a step references. An analysis step opens in an analysis graph tab of the same area with a
 * breadcrumb back here. Read-only: nothing here edits a workflow, runs or prepares anything.
 */
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_workflows.hh"
#include "stk/app/shell.hh"
#include "stk/app/workflow_view.hh"
#include "stk/ui/gpu_painter.hh"
#include "project_navigation.hh"
#include "editor_text.hh"

#include <algorithm>
#include <cmath>
#include <optional>

namespace stk::app {
namespace {
using io::Json;

const Json &member(const Json &object, const char *key)
{
  static const Json null;
  if (!object.is_object()) { return null; }
  const auto found = object.find(key);
  return found == object.end() ? null : *found;
}

std::string clipped(std::string value, const size_t limit = 120)
{
  if (value.size() <= limit) { return value; }
  size_t cut = limit;
  while (cut > 0 && (static_cast<unsigned char>(value[cut]) & 0xC0) == 0x80) { --cut; }
  return value.substr(0, cut) + "…";
}

class WorkflowEditor final : public Editor {
 public:
  explicit WorkflowEditor(const EditorType &type) : Editor(type) {}
  ~WorkflowEditor() override { *alive_ = false; }
  bool draws_gpu() const override { return true; }
  bool has_sidebar() const override { return true; }
  ui::Color main_background(const ui::Theme &) const override { return {0, 0, 0, 0}; }

  /** {"workflow_id", "step"?}: show that workflow (read on the next sync) and select the step. */
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &) override
  {
    if (!target.is_object() || !target.contains("workflow_id") || !target.at("workflow_id").is_string() ||
        target.at("workflow_id").get_ref<const std::string &>().empty()) { return false; }
    const auto id = target.at("workflow_id").get<std::string>();
    want_step_ = io::get_string(target, "step");
    if (!workflows_ || io::get_string(workflows_->selected(), "id") != id) { pending_ = id; }
    else { select_step(want_step_); want_step_.clear(); }
    redraw();
    return true;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx);
    attach(ctx);
    const std::weak_ptr<bool> weak = alive_;
    row.button("workflow_fit", ctx.tr("analysis_graph.fit"), [this, weak] {
      if (const auto live = weak.lock(); live && *live) { fit_ = true; redraw(); }
    }).width(3).disable(!view_);
    row.button("workflow_reload", ctx.tr("workflow.reload"), [this, weak] {
      if (const auto live = weak.lock(); live && *live) { workflows_->reload(); }
    }).width(4).disable(!workflows_->supported() || workflows_->busy());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    canvas_top_ = 0;
    if (!ctx.store.project().project()) {
      layout.paragraph(ctx.tr("workflow.no_project"));
      return;
    }
    if (!workflows_->supported()) {
      layout.paragraph(ctx.tr("workflow.unsupported"));
      return;
    }
    const auto &selected = workflows_->selected();
    if (selected.is_null()) {
      layout.paragraph(ctx.tr(workflows_->busy() ? "workflow.loading" : "workflow.choose"));
      return;
    }
    if (!view_) {
      layout.paragraph(ctx.tr(io::get_string(selected, "state") != "readable" ? "workflow.unreadable" :
                              workflows_->busy() ? "workflow.checking" : "workflow.no_view"));
      if (!view_error_.empty()) { layout.paragraph(view_error_); }
      return;
    }
    layout.label(ctx.store.catalog().format("workflow.caption", {{"name", io::get_string(selected, "name")},
        {"steps", std::to_string(view_->nodes.size())}})).tip(ctx.tr("workflow.navigation"));
    canvas_top_ = 1.5f * (ctx.ui ? ctx.ui->style().unit : 20.0f);
  }

  void draw_sidebar(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    hint(layout, ctx, "workflow.intro");
    if (!ctx.store.project().project() || !workflows_->supported()) { return; }
    list_panel(layout, ctx);
    const auto &selected = workflows_->selected();
    if (selected.is_null()) { return; }
    status(layout, ctx);
    issues_panel(layout, ctx);
    step_panel(layout, ctx);
  }

  void draw_gpu(EditorContext &ctx) override
  {
    attach(ctx);
    if (!ctx.draw || !ctx.draw->fonts) { return; }
    const double width = ctx.draw->rect.width(), height = ctx.draw->rect.height();
    const double top = std::min(double(canvas_top_), height);
    ui_scale_ = ctx.draw->ui_scale;
    ui::DrawList list;
    list.rect({0, 0, float(width), float(height)}, ui::Color::rgb(0x202328));
    if (view_) {
      place_canvas(width, height - top);
      ui::gpu::BlfTextMeasurer measure(*ctx.draw->fonts);
      auto content = canvas_.draw_list(width, height - top, ui_scale_, measure, ctx.store.language(), selected_);
      for (auto &command : content.cmds) {
        command.rect.y += float(top);
        command.pos.y += float(top);
        for (auto &point : command.p) { point.y += float(top); }
        command.tria_center.y += float(top);
        list.cmds.push_back(std::move(command));
      }
    }
    ui::gpu::GpuPainter painter(*ctx.draw->fonts);
    painter.set_pixel_size(ctx.draw->ui_scale);
    painter.paint(list, {float(width), float(height)});
  }

  bool handle_gpu_event(const wm::Event &event, EditorContext &ctx) override
  {
    attach(ctx);
    if (!ctx.draw || !view_) { return false; }
    const auto rect = ctx.draw->rect;
    ui_scale_ = ctx.draw->ui_scale;
    place_canvas(rect.width(), rect.height() - canvas_top_);
    const double x = event.x - rect.xmin + 0.5;
    const double y = rect.ymax - 1 - event.y + 0.5 - canvas_top_;
    if (event.type == wm::EventType::FocusOut) { dragging_ = false; return false; }
    if (event.type == wm::EventType::MouseMove && dragging_) {
      canvas_.pan(x - last_x_, y - last_y_); last_x_ = x; last_y_ = y; redraw(); return true;
    }
    if (event.type == wm::EventType::MouseUp && dragging_) { dragging_ = false; return true; }
    if (y < 0 || y >= rect.height() - canvas_top_) { return false; }
    if (event.type == wm::EventType::MouseDown) {
      if (event.button == wm::MouseButton::Left) { selected_ = canvas_.hit(x, y); redraw(); return true; }
      if (event.button == wm::MouseButton::Middle || event.button == wm::MouseButton::Right) {
        dragging_ = true; last_x_ = x; last_y_ = y; return true;
      }
    }
    if (event.type == wm::EventType::Wheel) {
      if (event.precise) { canvas_.pan(event.wheel_x, event.wheel_y); }
      else if (event.modifiers & wm::ModShift) { canvas_.pan(24.0 * ui_scale_ * event.wheel_y, 0); }
      else { canvas_.zoom_at(std::exp(std::clamp(event.wheel_y, -10.0f, 10.0f) * 0.13), x, y); }
      redraw(); return true;
    }
    if (event.type == wm::EventType::Magnify) {
      canvas_.zoom_at(std::exp(std::clamp(double(event.magnify), -2.0, 2.0)), x, y);
      redraw(); return true;
    }
    return false;
  }

  bool on_key(const wm::Event &event, EditorContext &ctx) override
  {
    if (event.type != wm::EventType::KeyDown || event.key != wm::Key::Home) { return false; }
    attach(ctx);
    fit_ = true; redraw(); return true;
  }

 private:
  void redraw() { if (store_) { store_->changed(); } }

  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store;
    if (!workflows_) { workflows_ = std::make_unique<ProjectWorkflows>(ctx.store); }
    workflows_->sync();
    if (epoch_ != workflows_->epoch()) {
      epoch_ = workflows_->epoch();
      view_.reset(); canvas_.set_view(nullptr); selected_.reset(); view_error_.clear();
      shown_version_ = 0; listed_ = auto_selected_ = false; refreshed_revision_ = page_revision_ = -1;
    }
    if (!workflows_->supported() || workflows_->busy()) { rebuild(ctx); return; }
    const auto revision = ctx.store.project().project() ? ctx.store.project().project()->revision : -1;
    if (pending_) {
      if (workflows_->load(*pending_)) { pending_.reset(); auto_selected_ = true; }
    }
    else if (!listed_) { listed_ = workflows_->load_page(0); }
    else if (workflows_->stale() && refreshed_revision_ != revision) {
      // Referenced analyses, tables or snapshots may have changed: read and check again, once per revision.
      refreshed_revision_ = revision;
      workflows_->reload();
    }
    else if (workflows_->page_stale() && page_revision_ != revision) {
      page_revision_ = revision;
      workflows_->load_page(io::get_int(workflows_->page(), "offset", 0));
    }
    else if (!auto_selected_ && workflows_->selected().is_null() && !workflows_->page().is_null()) {
      // Show the first workflow right away; most projects have one.
      auto_selected_ = true;
      const auto &rows = member(workflows_->page(), "workflows");
      if (!rows.empty()) { workflows_->load(io::get_string(rows.at(0), "id")); }
    }
    rebuild(ctx);
  }

  void rebuild(EditorContext &ctx)
  {
    const auto language = ctx.store.language();
    if (shown_version_ == workflows_->selected_version() && language == view_language_) { return; }
    shown_version_ = workflows_->selected_version(); view_language_ = language;
    const auto &selected = workflows_->selected();
    const auto &validation = workflows_->validation();
    const auto previous = view_ ? view_->id : std::string();
    const auto previous_step = selected_ && view_ && *selected_ < view_->nodes.size() ? view_->nodes[*selected_].id : std::string();
    view_error_.clear();
    if (selected.is_null() || validation.is_null() || io::get_string(selected, "state") != "readable") {
      if (selected.is_null()) { view_.reset(); canvas_.set_view(nullptr); selected_.reset(); }
      return;
    }
    WorkflowViewText words;
    for (const auto *kind : {"table", "files", "simulation", "analysis"}) {
      words.kinds[kind] = std::string(ctx.tr(std::string("workflow.kind.") + kind));
    }
    words.after = std::string(ctx.tr("workflow.port.after"));
    words.done = std::string(ctx.tr("workflow.port.done"));
    words.files = std::string(ctx.tr("workflow.files_count"));
    try {
      auto view = std::make_shared<AnalysisGraphView>(workflow_graph_view(selected.at("document"), validation, words));
      view->id = io::get_string(selected, "id");
      const bool same = view->id == previous;
      view_ = std::move(view);
      canvas_.set_view(view_, same);
      if (!same) { fit_ = true; }
      selected_.reset();
      select_step(want_step_.empty() ? previous_step : want_step_);
      if (!want_step_.empty()) { want_step_.clear(); }
    }
    catch (const std::exception &error) {
      view_.reset(); canvas_.set_view(nullptr); selected_.reset();
      view_error_ = error.what();
    }
  }

  void select_step(const std::string &id)
  {
    if (!view_ || id.empty()) { return; }
    for (size_t i = 0; i < view_->nodes.size(); ++i) {
      if (view_->nodes[i].id == id) { selected_ = i; return; }
    }
  }

  void place_canvas(const double width, const double height)
  {
    if (!fit_ || !canvas_.fit(width, height, ui_scale_)) { return; }
    fit_ = false;
  }

  std::function<bool()> valid() const
  {
    const std::weak_ptr<bool> weak = alive_;
    const auto epoch = epoch_;
    auto *workflows = workflows_.get();
    return [weak, epoch, workflows] {
      const auto live = weak.lock();
      return live && *live && workflows->epoch() == epoch;
    };
  }

  void list_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("workflow_list_panel", ctx.tr("workflow.list"), true);
    if (!panel) { return; }
    const auto page = workflows_->page();
    if (page.is_null()) { panel->paragraph(ctx.tr(workflows_->busy() ? "workflow.loading" : "workflow.choose")); return; }
    if (!io::get_string(page, "error").empty()) { panel->paragraph(clipped(io::get_string(page, "error"))); }
    const auto &rows = member(page, "workflows");
    if (rows.empty()) { panel->paragraph(ctx.tr("workflow.empty")); return; }
    std::vector<std::vector<std::string>> cells;
    int selected_row = -1;
    for (size_t i = 0; i < rows.size(); ++i) {
      const auto &item = rows[i];
      if (io::get_string(workflows_->selected(), "id") == io::get_string(item, "id")) { selected_row = int(i); }
      cells.push_back({clipped(io::get_string(item, "name", "—")),
                       std::string(ctx.tr("analysis_documents.state." + io::get_string(item, "state")))});
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("analysis_documents.name")), 12}, {std::string(ctx.tr("analysis_documents.state")), 6}};
    spec.rows = int(rows.size()); spec.visible_rows = float(std::min(5, spec.rows));
    spec.data_version = workflows_->version();
    spec.cell = [cells](const int row, const int column) { return cells.at(size_t(row)).at(size_t(column)); };
    const auto revision = io::get_int(page, "revision", -1);
    auto ok = valid();
    spec.selected = {[selected_row] { return selected_row; }, [this, ok, rows, revision](const int row) {
      if (ok() && row >= 0 && size_t(row) < rows.size() && io::get_int(workflows_->page(), "revision", -1) == revision) {
        auto_selected_ = true;
        workflows_->load(io::get_string(rows[size_t(row)], "id"));
      }
    }};
    panel->table("workflow_list", std::move(spec)).disable(workflows_->busy());
    const auto offset = io::get_int(page, "offset", 0), total = io::get_int(page, "total", 0);
    if (total > 50) {
      auto &buttons = panel->row();
      buttons.button("workflow_previous", ctx.tr("analysis_documents.previous"), [this, ok, offset] {
        if (ok()) { workflows_->load_page(std::max<int64_t>(0, offset - 50)); }
      }).disable(workflows_->busy() || offset == 0);
      buttons.button("workflow_next", ctx.tr("analysis_documents.next"), [this, ok, offset] {
        if (ok()) { workflows_->load_page(offset + 50); }
      }).disable(workflows_->busy() || offset + 50 >= total);
    }
  }

  void status(ui::Layout &layout, EditorContext &ctx)
  {
    const auto &selected = workflows_->selected();
    const auto &validation = workflows_->validation();
    layout.label(clipped(io::get_string(selected, "name", "—")));
    if (io::get_string(selected, "state") != "readable") {
      layout.paragraph(ctx.tr("workflow.unreadable"));
      if (!io::get_string(selected, "error").empty()) { layout.paragraph(clipped(io::get_string(selected, "error"), 512)); }
    }
    else if (validation.is_null()) { layout.paragraph(ctx.tr(workflows_->busy() ? "workflow.checking" : "workflow.not_checked")); }
    else if (io::get_bool(validation, "ok", false)) { layout.paragraph(ctx.tr("workflow.valid")); }
    else {
      const auto count = member(validation, "issues").size() + size_t(io::get_int(validation, "omitted_issues", 0));
      layout.paragraph(ctx.store.catalog().format("workflow.invalid", {{"count", std::to_string(count)}}));
    }
    if (workflows_->stale()) { layout.paragraph(ctx.tr("workflow.stale")); }
    if (!workflows_->error().empty()) { layout.paragraph(clipped(workflows_->error(), 512)); }
  }

  void issues_panel(ui::Layout &layout, EditorContext &ctx)
  {
    const auto &issues = member(workflows_->validation(), "issues");
    if (issues.empty()) { return; }
    auto *panel = layout.panel("workflow_issues_panel", ctx.tr("workflow.issues"), true);
    if (!panel) { return; }
    const std::weak_ptr<bool> weak = alive_;
    for (size_t i = 0; i < issues.size() && i < 64; ++i) {
      const auto &issue = issues[i];
      const auto code = io::get_string(issue, "code"), step = io::get_string(issue, "step");
      const auto title = ctx.store.catalog().tr_or("workflow.issue." + code, code);
      panel->button("workflow_issue/" + std::to_string(i), clipped(step + " · " + std::string(title), 80),
                    [this, weak, step] {
        if (const auto live = weak.lock(); live && *live) { select_step(step); redraw(); }
      }).tip(clipped(io::get_string(issue, "message"), 512) + "\n" + io::get_string(issue, "path"));
    }
    if (issues.size() > 64) {
      panel->paragraph(ctx.store.catalog().format("workflow.more_issues", {{"count", std::to_string(issues.size() - 64)}}));
    }
  }

  std::string field_name(EditorContext &ctx, const std::string &field_id) const
  {
    for (const auto &table : ctx.store.project().tables()) {
      for (const auto &field : table.fields) {
        if (field.id == field_id) { return table.name + " · " + field.name; }
      }
    }
    return field_id.substr(0, 8);
  }

  void step_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("workflow_step_panel", ctx.tr("workflow.step"), true);
    if (!panel) { return; }
    if (!view_ || !selected_ || *selected_ >= view_->nodes.size()) { panel->paragraph(ctx.tr("workflow.pick_step")); return; }
    const auto &document = workflows_->selected().at("document");
    const auto &steps = document.at("steps");
    const auto &summaries = member(workflows_->validation(), "steps");
    const size_t index = *selected_;
    if (index >= steps.size() || index >= summaries.size()) { return; }
    const auto &step = steps[index];
    const auto &summary = summaries[index];
    const auto kind = io::get_string(step, "kind"), id = io::get_string(step, "id");
    auto &catalog = ctx.store.catalog();
    panel->label(view_->nodes[index].label);
    panel->paragraph(catalog.format("workflow.step_id", {{"id", id}, {"kind", std::string(catalog.tr_or("workflow.kind." + kind, kind))}}));
    const auto name = io::get_string(summary, "name");
    if (!name.empty()) { panel->paragraph(catalog.format("workflow.references", {{"name", clipped(name)}})); }
    if (member(summary, "file_count").is_number_integer()) {
      panel->paragraph(catalog.format("workflow.files_count", {{"count", std::to_string(member(summary, "file_count").get<int64_t>())}}));
    }
    const auto hash = io::get_string(summary, "content_sha256");
    if (!hash.empty()) { panel->paragraph(catalog.format("workflow.content_hash", {{"hash", hash.substr(0, 12)}})); }
    const auto &links = member(step, "inputs");
    for (const auto &port : member(summary, "inputs")) {
      const auto port_name = io::get_string(port, "name");
      const auto &link = member(links, port_name.c_str());
      panel->paragraph(link.is_object() ?
          catalog.format("workflow.input_linked", {{"port", port_name}, {"type", io::get_string(port, "type")},
                                                   {"source", io::get_string(link, "from")}}) :
          catalog.format("workflow.input_open", {{"port", port_name}, {"type", io::get_string(port, "type")}}));
    }
    for (const auto &port : member(summary, "outputs")) {
      panel->paragraph(catalog.format("workflow.output", {{"port", io::get_string(port, "name")}, {"type", io::get_string(port, "type")}}));
    }
    std::string after;
    for (const auto &before : member(step, "after")) {
      if (before.is_string()) { after += (after.empty() ? "" : ", ") + before.get<std::string>(); }
    }
    if (!after.empty()) { panel->paragraph(catalog.format("workflow.after", {{"steps", after}})); }
    for (const auto &[parameter, value] : member(step, "parameters").items()) {
      const bool field = value.is_object() && value.size() == 1 && value.contains("$field") && value.at("$field").is_string();
      panel->paragraph(field ? catalog.format("workflow.parameter_field", {{"name", parameter},
                                   {"field", field_name(ctx, value.at("$field").get<std::string>())}}) :
                               catalog.format("workflow.parameter_value", {{"name", parameter}, {"value", clipped(value.dump(), 80)}}));
    }
    action(*panel, ctx, step, summary);
  }

  void action(ui::Layout &panel, EditorContext &ctx, const Json &step, const Json &summary)
  {
    const auto kind = io::get_string(step, "kind");
    const auto &ref = member(step, "ref");
    const bool resolved = !member(summary, "inputs").empty() || !member(summary, "outputs").empty();
    if (kind == "analysis") {
      auto *shell = &ctx.area.shell();
      auto *area = &ctx.area;
      const auto self = lifetime();
      const auto &project = ctx.store.project().project();
      const auto &workflow = workflows_->selected();
      const Json target = {{"analysis_id", io::get_string(ref, "analysis")}, {"breadcrumb", {
          {"handle", project ? project->handle : std::string()}, {"workflow_id", io::get_string(workflow, "id")},
          {"workflow_name", io::get_string(workflow, "name")}, {"step", io::get_string(step, "id")},
          {"step_label", io::get_string(step, "label", io::get_string(summary, "name"))}}}};
      panel.button("workflow_enter_analysis", ctx.tr("workflow.enter_analysis"), [shell, area, self, target] {
        shell->open_in_area_later(area, self, kEditorAnalysisGraph, target);
      }).disable(!resolved || shell->text_input_active()).tip(ctx.tr("workflow.enter_analysis.tip"));
      return;
    }
    if (!resolved) { return; }
    if (kind == "table") {
      auto &project = ctx.store.project();
      const auto handle = project.project() ? project.project()->handle : std::string();
      auto *area = &ctx.area;
      auto *editor = this;
      const auto weak = lifetime();
      const auto table = io::get_string(ref, "table");
      panel.button("workflow_open_table", ctx.tr("workflow.open_table"), [weak, area, editor, handle, table] {
        if (weak.expired() || &area->editor() != editor) { return; }
        area->shell().open_project_page_later(area->screen(), "data", handle, [weak, area, editor] {
          return !weak.expired() && &area->editor() == editor;
        }, table);
      });
    }
    else if (kind == "files") {
      panel.button("workflow_open_files", ctx.tr("workflow.open_files"), project_navigation_action(ctx, "files"));
    }
    else if (kind == "simulation") {
      panel.button("workflow_open_simulation", ctx.tr("workflow.open_simulation"), project_navigation_action(ctx, "simulation_runs"));
    }
  }

  AppStore *store_ = nullptr;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::unique_ptr<ProjectWorkflows> workflows_;
  AnalysisGraphCanvas canvas_;
  std::shared_ptr<AnalysisGraphView> view_;
  std::optional<size_t> selected_;
  std::optional<std::string> pending_;
  std::string want_step_, view_language_, view_error_;
  uint64_t epoch_ = 0, shown_version_ = 0;
  int64_t refreshed_revision_ = -1, page_revision_ = -1;
  bool listed_ = false, auto_selected_ = false, fit_ = true, dragging_ = false;
  double last_x_ = 0, last_y_ = 0, ui_scale_ = 1;
  float canvas_top_ = 0;
};

}  // namespace

std::unique_ptr<Editor> make_workflow_editor(const EditorType &type)
{
  return std::make_unique<WorkflowEditor>(type);
}

}  // namespace stk::app
