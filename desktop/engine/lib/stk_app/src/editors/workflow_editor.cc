/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Workflow editor (P3 W3b/W3c, docs/design/project-workflows.md): shows a project workflow on the
 * analysis graph canvas, lists its validation issues and the selected step, navigates to the
 * object a step references, and edits the workflow as an unsaved candidate (WorkflowDraft) that is
 * checked with project.workflows.validate and saved explicitly. An analysis step opens in an
 * analysis graph tab of the same area with a breadcrumb back here. Reading and navigation do not
 * execute; explicit run controls prepare and start frozen runs through the shared service.
 */
#include "workspace_fields.hh"
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "project_record_pages.hh"
#include "stk/app/project_workflows.hh"
#include "stk/app/shell.hh"
#include "stk/app/workflow_draft.hh"
#include "stk/app/workflow_view.hh"
#include "stk/io/graph.hh"
#include "stk/io/schema.hh"
#include "stk/ui/gpu_painter.hh"
#include "archive_controls.hh"
#include "project_navigation.hh"
#include "editor_text.hh"
#include "simulation_target.hh"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <optional>
#include <set>

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

/** The reference key each step kind holds (suan/project/workflows.py REF_KEYS). */
const char *ref_key(const std::string &kind)
{
  if (kind == "table") { return "table"; }
  if (kind == "files") { return "snapshot"; }
  if (kind == "simulation") { return "template"; }
  if (kind == "workflow") { return "workflow"; }
  return "analysis";
}

constexpr const char *kKinds[] = {"table", "files", "simulation", "analysis", "workflow"};

/** What a workflow showed when it was last on screen (UX package U4): the graph point in the middle of
 * the canvas and the zoom (independent of window size and UI scale), the selected step and the shown run. */
struct ViewMemory {
  std::string project, workflow;
  bool placed = false;  // x, y and zoom are known (the canvas was drawn)
  double x = 0, y = 0, zoom = 1;
  std::string step, run;
};
constexpr size_t kMemoryLimit = 50;
std::atomic<uint64_t> workflow_ui_sequence{0};

class WorkflowEditor final : public Editor {
 public:
  explicit WorkflowEditor(const EditorType &type) : Editor(type) {}
  bool has_unsaved_changes() const override
  {
    return draft_.dirty() || unapplied_text_edits() || (!workspace_restore_.is_null() && workspace_restore_dirty_);
  }
  bool can_change_project_selection(const std::string_view project_id) const override
  {
    if (!workspace_restore_.is_null() && io::get_string(workspace_restore_, "project") == project_id) {
      return !workspace_restore_dirty_;
    }
    return !store_ || !store_->project().project() || store_->project().project()->id != project_id ||
        (!draft_.dirty() && !unapplied_text_edits());
  }
  ~WorkflowEditor() override { *alive_ = false; }
  bool draws_gpu() const override { return true; }
  bool has_sidebar() const override { return true; }
  ui::Color main_background(const ui::Theme &) const override { return {0, 0, 0, 0}; }

  bool shows_navigation_target(const nlohmann::json &target) const override
  {
    return store_ && store_->project().project() && draft_.pinned() &&
        store_->project().project()->handle == draft_.handle() &&
        io::get_string(member(target, "breadcrumb"), "handle") == draft_.handle() &&
        io::get_string(target, "workflow_id") == draft_.workflow_id();
  }

  /** {"workflow_id", "step"?, "run_id"?}: show that workflow (read on the next sync) and select the step;
   * or {"table_id", "rows"} (P2 L2, rows an AI sweep added): show a workflow over that table with only those rows
   * checked to run. Refused while unsaved edits of another workflow are pending. Never starts a run. */
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &origin, std::string &reason) override
  {
    if (!target.is_object()) { return false; }
    std::set<std::string> rows;
    if (const auto found = target.find("rows"); found != target.end() && found->is_array()) {
      for (const auto &row : *found) { if (row.is_string() && rows.size() < 100) { rows.insert(row.get<std::string>()); } }
    }
    const auto rows_table = io::get_string(target, "table_id");
    if (!target.contains("workflow_id")) {
      if (rows_table.empty() || rows.empty()) { return false; }
      if ((draft_.dirty() || unapplied_text_edits()) && io::get_string(workflows_ ? workflows_->selected() : Json(), "table_id") != rows_table) {
        reason = "workflow.navigate_unsaved";
        return false;
      }
      reopen_.reset();
      want_rows_table_ = rows_table; want_rows_ = std::move(rows); want_table_ = rows_table; rows_notice_.clear();
      redraw();
      return true;
    }
    if (!target.at("workflow_id").is_string() || target.at("workflow_id").get_ref<const std::string &>().empty()) { return false; }
    const auto id = target.at("workflow_id").get<std::string>();
    if ((draft_.dirty() || unapplied_text_edits()) && draft_.workflow_id() != id) {
      reason = "workflow.navigate_unsaved";
      return false;
    }
    if (unapplied_text_edits() && target.contains("step") && io::get_string(target, "step") != selected_id_) {
      reason = "workflow.edit.unapplied_text";
      return false;
    }
    breadcrumb_ = nullptr;
    if (const auto crumb = member(target, "breadcrumb"); crumb.is_object()) {
      breadcrumb_ = crumb; breadcrumb_child_ = id; breadcrumb_origin_ = origin;
      if (shows_navigation_target(target) && !target.contains("step") && !target.contains("run_id")) {
        redraw(); return true;  // Keep this child's selection, view and any unapplied text.
      }
    }
    reopen_.reset();  // an explicit target wins over the workflow the layout last showed
    if (workflows_ && io::get_string(workflows_->selected(), "id") != id) { leave(); }
    want_step_ = io::get_string(target, "step");
    want_run_ = io::get_string(target, "run_id");  // for example from a Home attention item
    want_run_workflow_ = id;
    if (!workflows_ || io::get_string(workflows_->selected(), "id") != id) { pending_ = id; }
    else { selected_id_ = want_step_; want_step_.clear(); shown_ = {}; }
    redraw();
    return true;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx);
    attach(ctx);
    breadcrumb(row, ctx);
    history_controls(row, ctx);
    const std::weak_ptr<bool> weak = alive_;
    row.button("workflow_fit", ctx.tr("analysis_graph.fit"), [this, weak] {
      if (const auto live = weak.lock(); live && *live) { fit_ = true; redraw(); }
    }).width(3).disable(!view_);
    row.button("workflow_reload", ctx.tr("workflow.reload"), [this, weak] {
      if (const auto live = weak.lock(); live && *live && !draft_.dirty() && !unapplied_text_edits()) { workflows_->reload(); }
    }).width(4).disable(!workflows_->supported() || workflows_->busy() || draft_.dirty() || unapplied_text_edits());
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
    const bool candidate = candidate_shown_;
    layout.label(ctx.store.catalog().format(candidate ? "workflow.caption_candidate" : "workflow.caption",
        {{"name", candidate ? draft_.name() : io::get_string(selected, "name")}, {"steps", std::to_string(view_->nodes.size())}}))
        .tip(ctx.tr(editable(ctx) ? "workflow.navigation_edit" : "workflow.navigation"));
    canvas_top_ = 1.5f * (ctx.ui ? ctx.ui->style().unit : 20.0f);
  }

  void draw_sidebar(ui::Layout &layout, EditorContext &ctx) override
  {
    parameter_ui_ = ctx.ui;
    attach(ctx);
    // Tabs in one area share its UI Context. A unique instance scope prevents an inactive tab
    // from mistaking another workflow editor's live text for its own during workspace capture.
    auto &body = layout.scope(ui_scope_);
    hint(body, ctx, "workflow.intro");
    if (!ctx.store.project().project() || !workflows_->supported()) { return; }
    list_panel(body, ctx);
    if (!rows_notice_.empty()) { body.paragraph(ctx.tr(rows_notice_)); }
    if (workflows_->selected().is_null()) { return; }
    status(body, ctx);
    edit_panel(body, ctx);
    interface_panel(body, ctx);
    run_panel(body, ctx);
    issues_panel(body, ctx);
    step_panel(body, ctx);
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
      auto content = canvas_.draw_list(width, height - top, ui_scale_, measure, ctx.store.language(), selected_index());
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

  /** Remembered views and the workflow shown last, saved with the layout (U4). */
  nlohmann::json save_state() const override
  {
    auto memories = memory_;
    if (auto memory = snapshot()) { keep(memories, std::move(*memory)); }
    Json views = Json::array();
    for (const auto &memory : memories) {
      Json view = {{"project", memory.project}, {"workflow", memory.workflow}, {"step", memory.step}, {"run", memory.run}};
      if (memory.placed) { view["x"] = memory.x; view["y"] = memory.y; view["zoom"] = memory.zoom; }
      views.push_back(std::move(view));
    }
    Json state = {{"views", std::move(views)}};
    const auto shown = workflows_ ? io::get_string(workflows_->selected(), "id") : std::string();
    if (store_ && store_->project().project() && !shown.empty()) {
      state["shown"] = {{"project", store_->project().project()->id}, {"workflow", shown}};
    }
    else if (reopen_) { state["shown"] = {{"project", reopen_->first}, {"workflow", reopen_->second}}; }
    return state;
  }

  bool load_state(const nlohmann::json &state) override
  {
    if (!state.is_object()) { return false; }
    const auto text = [](const Json &value, const char *key, const size_t limit) {
      return value.contains(key) && value.at(key).is_string() && value.at(key).get_ref<const std::string &>().size() <= limit;
    };
    const auto number = [](const Json &value, const char *key) {
      return value.contains(key) && value.at(key).is_number() && std::isfinite(value.at(key).get<double>());
    };
    std::vector<ViewMemory> loaded;
    if (state.contains("views")) {
      const auto &views = state.at("views");
      if (!views.is_array() || views.size() > kMemoryLimit) { return false; }
      for (const auto &view : views) {
        const bool placed = view.is_object() && (view.contains("x") || view.contains("y") || view.contains("zoom"));
        if (!view.is_object() || !text(view, "project", 64) || !text(view, "workflow", 64) || !text(view, "step", 256) ||
            !text(view, "run", 64) || (placed && (!number(view, "x") || !number(view, "y") || !number(view, "zoom") ||
                                                  view.at("zoom").get<double>() <= 0))) { return false; }
        ViewMemory memory{view.at("project").get<std::string>(), view.at("workflow").get<std::string>(), placed};
        if (placed) { memory.x = view.at("x").get<double>(); memory.y = view.at("y").get<double>(); memory.zoom = view.at("zoom").get<double>(); }
        memory.step = view.at("step").get<std::string>();
        memory.run = view.at("run").get<std::string>();
        loaded.push_back(std::move(memory));
      }
    }
    std::optional<std::pair<std::string, std::string>> shown;
    if (state.contains("shown")) {
      const auto &value = state.at("shown");
      if (!value.is_object() || !text(value, "project", 64) || !text(value, "workflow", 64)) { return false; }
      shown = std::pair{value.at("project").get<std::string>(), value.at("workflow").get<std::string>()};
    }
    memory_ = std::move(loaded);
    reopen_ = std::move(shown);
    return true;
  }

  nlohmann::json save_workspace_state() const override
  {
    if (!workspace_restore_.is_null()) { return workspace_restore_; }
    std::map<std::string, std::string> literals, modes;
    // Browsing a clean value is a cache read, not an unsaved edit. Export only real drafts;
    // otherwise visiting many steps makes the workspace grow with display-only buffers.
    for (const auto &key : literal_dirty_) {
      if (const auto found = literal_text_.find(key); found != literal_text_.end()) { literals.emplace(key, found->second); }
    }
    auto name = name_text_, label = label_text_;
    if (parameter_ui_ && parameter_ui_->edit_state()) {
      const auto &text = parameter_ui_->edit_state()->text();
      if (parameter_text_active()) { literals[parameter_inputs_.at(parameter_ui_->editing())] = text; }
      else if (name_input_id_ && name_input_id_ == parameter_ui_->editing()) { name = text; }
      else if (label_input_id_ && label_input_id_ == parameter_ui_->editing()) { label = text; }
    }
    for (const auto &[key, text] : literals) {
      (void)text;
      const auto found = literal_modes_.find(key);
      modes[key] = found == literal_modes_.end() ? "json" : found->second;
    }
    return {{"version", 1}, {"layout", save_state()}, {"project", store_ && store_->project().project() ? store_->project().project()->id : std::string()},
      {"draft", draft_.save_workspace_state()}, {"name_text", name}, {"label_text", label}, {"literal_text", literals},
      {"literal_modes", modes}, {"parameter_modes", parameter_modes_},
      {"add_kind", add_kind_}, {"add_object", add_object_}, {"archived", show_archived_}, {"archived_runs", show_archived_runs_},
      {"target", target_.save_workspace_state()}};
  }
  bool load_workspace_state(const nlohmann::json &value) override
  {
    if (!workspace_fields(value, {"project", "name_text", "label_text"}, {"add_kind", "add_object"}, {"archived", "archived_runs"},
        {"layout", "draft", "literal_text", "literal_modes", "parameter_modes", "target"}) || !value.contains("layout") || !value.contains("draft") ||
        !value.contains("literal_text") || !value.at("literal_text").is_object() ||
        value.at("literal_text").size() > WorkflowDocumentLimits::max_steps * WorkflowDocumentLimits::max_parameters) { return false; }
    for (const auto &[key, item] : value.at("literal_text").items()) { (void)key; if (!item.is_string()) { return false; } }
    for (const char *key : {"literal_modes", "parameter_modes"}) {
      if (!value.contains(key)) { continue; }
      const auto &entries = value.at(key);
      if (!entries.is_object() || entries.size() > WorkflowDocumentLimits::max_steps * WorkflowDocumentLimits::max_parameters) { return false; }
      for (const auto &[name, item] : entries.items()) {
        (void)name;
        if (std::string_view(key) == "literal_modes") {
          if (!item.is_string() || (item != "json" && item != "string")) { return false; }
        }
        else if (!item.is_number_integer() || item.get<int64_t>() < 0 || item.get<int64_t>() > 3) { return false; }
      }
    }
    WorkflowDraft checked;
    SimulationTarget target;
    if ((!value.at("draft").is_null() && !checked.load_workspace_state(value.at("draft"), "workspace-validation")) ||
        !target.load_workspace_state(value.value("target", Json::object())) || !load_state(value.at("layout"))) { return false; }
    bool dirty = false;
    if (checked.pinned()) {
      dirty = checked.dirty() || value.value("name_text", std::string()) != checked.name() || !value.at("literal_text").empty();
      // Hidden tabs have no live draft or UI yet. Protect their unapplied step label before
      // the first frame, using the same saved selection that will own the restored text.
      std::string step_id;
      for (const auto &memory : memory_) {
        if (memory.project == io::get_string(value, "project") && memory.workflow == checked.workflow_id()) { step_id = memory.step; }
      }
      const auto *step = checked.step(step_id);
      dirty = dirty || value.value("label_text", std::string()) != (step ? io::get_string(*step, "label") : std::string());
    }
    workspace_restore_ = value; workspace_restore_dirty_ = dirty; return true;
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
    if (event.type == wm::EventType::FocusOut) { dragging_ = false; cancel_drag(); return false; }
    if (event.type == wm::EventType::MouseMove && dragging_) {
      canvas_.pan(x - last_x_, y - last_y_); last_x_ = x; last_y_ = y; redraw(); return true;
    }
    if (event.type == wm::EventType::MouseMove && drag_ != Drag::None) { drag_move(x, y); return true; }
    if (event.type == wm::EventType::MouseUp && dragging_) { dragging_ = false; return true; }
    if (event.type == wm::EventType::MouseUp && drag_ != Drag::None) { drag_finish(ctx, x, y); return true; }
    if (y < 0 || y >= rect.height() - canvas_top_) { return false; }
    if (event.type == wm::EventType::MouseDown) {
      if (event.button == wm::MouseButton::Left) {
        if (unapplied_text_edits()) { refuse(std::string(ctx.tr("workflow.edit.unapplied_text"))); return true; }
        // Editing: drag from an output socket to an input to link, or drag a step to move it.
        if (editable(ctx)) {
          if (const auto port = canvas_.hit_port(x, y); port && port->output) {
            const auto &node = view_->nodes[port->node];
            if (!node.ambiguous_id) {
              const auto &output = node.outputs[port->port];
              drag_ = Drag::Link; link_node_ = node.id; link_port_ = output.name; link_type_ = output.type_text;
              link_from_ = output.point;
              canvas_.set_pending_link(std::pair{canvas_.to_screen(link_from_), AnalysisGraphPoint{x, y}});
              redraw(); return true;
            }
          }
        }
        const auto hit = canvas_.hit(x, y);
        selected_id_ = hit ? view_->nodes[*hit].id : std::string();
        if (hit && editable(ctx) && !view_->nodes[*hit].ambiguous_id) {
          drag_ = Drag::Node; drag_node_ = *hit; drag_moved_ = false;
          press_x_ = x; press_y_ = y; drag_dx_ = drag_dy_ = 0;
        }
        redraw(); return true;
      }
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
    if (event.type != wm::EventType::KeyDown) { return false; }
    attach(ctx);
    if (!(event.modifiers & wm::ModAlt) && (event.modifiers & (wm::ModCtrl | wm::ModOS)) &&
        (event.key == wm::Key::Z || event.key == wm::Key::Y)) {
      if (!history_ready(ctx.area.shell())) { return false; }
      apply_history(event.key == wm::Key::Y || (event.modifiers & wm::ModShift));
      return true;
    }
    if (event.key == wm::Key::Delete) {
      // Delete removes the selected step of the candidate (same as the panel button).
      if (!editable(ctx) || unapplied_text_edits() || selected_id_.empty()) { return false; }
      remove_step(selected_id_);
      return true;
    }
    if (event.key != wm::Key::Home) { return false; }
    fit_ = true; redraw(); return true;
  }

 private:
  enum class Drag { None, Node, Link };

  void redraw() { if (store_) { store_->changed(); } }
  void refuse(const std::string &message)
  {
    edit_error_ = message;
    if (store_ && store_->toast) { store_->toast(message, ui::ToastKind::Warning); }
    redraw();
  }

  std::optional<size_t> selected_index() const
  {
    if (!view_ || selected_id_.empty()) { return std::nullopt; }
    for (size_t i = 0; i < view_->nodes.size(); ++i) {
      if (view_->nodes[i].id == selected_id_) { return i; }
    }
    return std::nullopt;
  }

  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store;
    if (!workflows_) { workflows_ = std::make_unique<ProjectWorkflows>(ctx.store); }
    remember();  // before a project change resets what is shown
    workflows_->sync();
    if (epoch_ != workflows_->epoch()) {
      epoch_ = workflows_->epoch();
      view_.reset(); canvas_.set_view(nullptr); selected_id_.clear(); view_error_.clear(); shown_ = {};
      auto_selected_ = false; refreshed_revision_ = page_revision_ = choices_revision_ = listed_revision_ = -1;
      runs_listed_.clear(); page_archive_.clear(); runs_archive_.clear();
      run_unchecked_.clear(); run_only_.reset(); run_rows_table_.clear(); run_row_ = -1;
      checked_document_ = checked_validation_ = nullptr;
      draft_.reset(); workspace_detached_ = false; requested_.reset(); cancel_drag();
    }
    if (workflows_->supported() && !workflows_->busy()) { request(ctx); }
    sync_draft(ctx);
    if (!workspace_restore_.is_null() && project_id(ctx) == io::get_string(workspace_restore_, "project")) {
      const auto &saved_draft = workspace_restore_.at("draft");
      const auto &selected = workflows_->selected();
      if (saved_draft.is_null() || (!selected.is_null() && io::get_string(selected, "id") == io::get_string(saved_draft, "workflow_id"))) {
        const auto value = std::move(workspace_restore_); workspace_restore_ = nullptr;
        if (!value.at("draft").is_null()) {
          draft_.load_workspace_state(value.at("draft"), ctx.store.project().project()->handle); requested_.reset();
          workspace_detached_ = workflows_->selected_revision() != draft_.revision() ||
            io::get_string(selected, "name") != draft_.baseline_name() || !selected.contains("document") ||
              io::python_json_dumps(selected.at("document"), true, true) != io::python_json_dumps(draft_.baseline(), true, true);
        }
        name_text_ = value.value("name_text", std::string()); label_text_ = value.value("label_text", std::string());
        literal_text_ = value.at("literal_text").get<std::map<std::string, std::string>>();
        literal_modes_ = value.value("literal_modes", Json::object()).get<std::map<std::string, std::string>>();
        parameter_modes_ = value.value("parameter_modes", Json::object()).get<std::map<std::string, int>>();
        literal_original_.clear(); literal_dirty_.clear();
        parameter_workflow_ = draft_.workflow_id();
        for (const auto &[key, text] : literal_text_) {
          const auto slash = key.find('/');
          const auto *step = slash == std::string::npos ? nullptr : draft_.step(key.substr(0, slash));
          const auto current = key.rfind("$interface/", 0) == 0 ? interface_default(key.substr(11)) :
              step ? parameter_value(member(member(*step, "parameters"), key.substr(slash + 1).c_str())) : Json();
          // Legacy workspace text was always JSON. New plain strings declare their mode explicitly.
          if (!literal_modes_.contains(key)) { literal_modes_[key] = "json"; }
          const bool plain = literal_modes_.at(key) == "string" && current.is_string();
          literal_original_[key] = plain ? current.get<std::string>() : current.dump();
          if (text != literal_original_[key]) { literal_dirty_.insert(key); }
        }
        name_source_ = {draft_.generation(), draft_.version()};
        auto restored_step = selected_id_;
        if (value.at("layout").contains("views")) {
          for (const auto &memory : value.at("layout").at("views")) {
            if (io::get_string(memory, "project") == project_id(ctx) && io::get_string(memory, "workflow") == draft_.workflow_id()) {
              restored_step = io::get_string(memory, "step");
            }
          }
        }
        label_source_ = std::make_tuple(restored_step, draft_.generation(), draft_.version());
        literal_source_.clear();
        for (const auto &[key, text] : literal_text_) {
          (void)text; literal_source_[key] = std::make_tuple(key, draft_.generation(), draft_.version());
        }
        add_kind_ = std::clamp(int(io::get_int(value, "add_kind", 3)), 0, int(std::size(kKinds)) - 1); add_object_ = int(io::get_int(value, "add_object", 0));
        show_archived_ = value.value("archived", false); show_archived_runs_ = value.value("archived_runs", false);
        target_.load_workspace_state(value.at("target"));
      }
      else if (!workflows_->busy()) { pending_ = io::get_string(saved_draft, "workflow_id"); }
    }
    if (editable(ctx) && candidate_edits()) {
      // Every candidate is checked as soon as it changes (latest only); positions and the name keep a check valid.
      const auto key = candidate_key(ctx);
      if (!requested_ || *requested_ != key) {
        if (workflows_->check(draft_.document(), key)) { requested_ = key; }
      }
    }
    rebuild(ctx);
  }

  /** At most one read per frame: a navigation target, the first page, re-reading after project
   * changes (never under unsaved edits), a pending check, choices for adding steps, the first workflow. */
  void request(EditorContext &ctx)
  {
    const auto revision = ctx.store.project().project() ? ctx.store.project().project()->revision : -1;
    // Lists leave archived objects out unless switched to them (format 11); archiving never changes the revision,
    // so a changed archived set or filter reads the lists again by itself.
    const auto list_filter = archive_filter(ctx, show_archived_), runs_filter = archive_filter(ctx, show_archived_runs_);
    workflows_->set_archive_filters(list_filter, runs_filter);
    const auto archive_key = [&ctx](const std::optional<bool> &filter) {
      return std::string(!filter ? "-" : *filter ? "1" : "0") + ":" + std::to_string(ctx.store.archive().version());
    };
    if (pending_) {
      if (workflows_->load(*pending_)) { pending_.reset(); auto_selected_ = true; }
    }
    else if (workflows_->page().is_null() && listed_revision_ != revision && !ctx.store.project().busy()) {
      // The first page, and again after a save or delete dropped it (once per revision).
      if (workflows_->load_page(0)) { listed_revision_ = revision; page_archive_ = archive_key(list_filter); }
    }
    else if (!workflows_->page().is_null() && page_archive_ != archive_key(list_filter) && !ctx.store.project().busy()) {
      if (workflows_->load_page(0)) { page_archive_ = archive_key(list_filter); }
    }
    else if (!workflows_->runs().is_null() && runs_archive_ != archive_key(runs_filter) && !ctx.store.project().busy()) {
      if (workflows_->load_runs()) { runs_archive_ = archive_key(runs_filter); }
    }
    else if (workflows_->stale() && refreshed_revision_ != revision && !ctx.store.project().busy()) {
      // Referenced analyses, tables or snapshots may have changed: read and check again, once per revision.
      // Unsaved edits survive when the workflow itself did not change (see sync_draft).
      refreshed_revision_ = revision;
      workflows_->reload();
    }
    else if (workflows_->validation().is_null() && io::get_string(workflows_->selected(), "state") == "readable" &&
             !ctx.store.project().busy()) {
      workflows_->validate_selected();  // after a save, once the project has settled
    }
    else if (workflows_->page_stale() && page_revision_ != revision && !ctx.store.project().busy()) {
      page_revision_ = revision;
      workflows_->load_page(io::get_int(workflows_->page(), "offset", 0));
    }
    else if (!want_run_.empty() && workflows_->runs_supported() && io::get_string(workflows_->selected(), "id") == want_run_workflow_) {
      if (workflows_->load_run(want_run_)) { want_run_.clear(); run_row_ = -1; }
    }
    else if (run_due()) {
      // A run in progress is followed by reading it again (the service executes it; nothing runs here).
      last_poll_ = std::chrono::steady_clock::now();
      workflows_->load_run(io::get_string(workflows_->run(), "id"));
    }
    else if (stale_due(revision)) {
      // Once a run has stopped, compare it with the current definitions (again after every project change).
      stale_key_ = io::get_string(workflows_->run(), "id") + "@" + std::to_string(revision);
      workflows_->load_run_staleness();
    }
    else if (workflows_->runs_supported() && !workflows_->selected().is_null() && workflows_->runs().is_null() &&
             runs_listed_ != io::get_string(workflows_->selected(), "id") + "@" + std::to_string(revision) &&
             !ctx.store.project().busy()) {
      // Once per workflow and revision (another workflow shown in the same revision lists its own runs).
      runs_listed_ = io::get_string(workflows_->selected(), "id") + "@" + std::to_string(revision);
      if (workflows_->load_runs()) { runs_archive_ = archive_key(runs_filter); }
    }
    else if (editable(ctx) && choices_revision_ != revision && !ctx.store.project().busy()) {
      choices_revision_ = revision;
      workflows_->load_choices();
    }
    else if (!want_table_.empty() && !workflows_->page().is_null() && !ctx.store.project().busy()) {
      // Rows from an AI sweep: keep the shown workflow when it runs that table, else the first one that does.
      const auto table = std::exchange(want_table_, std::string());
      if (io::get_string(workflows_->selected(), "table_id") != table) {
        std::string found;
        for (const auto &row : member(workflows_->page(), "workflows")) {
          if (io::get_string(row, "table_id") == table && io::get_string(row, "state") == "readable" &&
              !ctx.store.archive().archived("workflow", io::get_string(row, "id"))) { found = io::get_string(row, "id"); break; }
        }
        if (found.empty()) { rows_notice_ = "workflow.run.no_workflow_for_rows"; want_rows_.clear(); }
        else { leave(); auto_selected_ = true; selected_id_.clear(); workflows_->load(found); }
      }
    }
    else if (!auto_selected_ && workflows_->selected().is_null() && !workflows_->page().is_null()) {
      // Show the first workflow right away; most projects have one.
      auto_selected_ = true;
      const auto &rows = member(workflows_->page(), "workflows");
      std::string first = rows.empty() ? std::string() : io::get_string(rows.at(0), "id");
      if (reopen_ && reopen_->first == project_id(ctx)) {
        for (const auto &row : rows) { if (io::get_string(row, "id") == reopen_->second) { first = reopen_->second; } }
      }
      reopen_.reset();
      if (!first.empty()) { workflows_->load(first); }
    }
  }

  /** Pin the draft to the shown workflow while it has no edits; after a save the stored document
   * equals the candidate and the draft moves to the new revision. Edits survive a newer read of the
   * same, unchanged workflow; edits of a workflow changed elsewhere stay detached until discarded. */
  void sync_draft(EditorContext &ctx)
  {
    const auto &selected = workflows_->selected();
    const auto &project = ctx.store.project().project();
    if (selected.is_null() || io::get_string(selected, "state") != "readable" || !project) {
      if (!draft_.dirty() && draft_.pinned()) { draft_.reset(); }
      return;
    }
    const auto id = io::get_string(selected, "id"), name = io::get_string(selected, "name");
    const auto revision = workflows_->selected_revision();
    const bool here = draft_.pinned() && draft_.workflow_id() == id && draft_.revision() == revision &&
        draft_.handle() == project->handle;
    if (here && workspace_detached_ && !draft_.dirty()) {
      try { draft_.pin(project->handle, id, revision, name, selected.at("document")); workspace_detached_ = false; }
      catch (const std::exception &error) { edit_error_ = error.what(); }
    }
    if (here) { return; }
    // A newer read of an unchanged workflow keeps the edits; a changed one leaves them detached.
    if ((draft_.dirty() || draft_.can_undo() || draft_.can_redo()) && draft_.workflow_id() == id && draft_.handle() == project->handle &&
        draft_.rebase(revision, name, selected.at("document"))) { requested_.reset(); return; }
    if (!draft_.dirty() || draft_.matches(id, name, selected.at("document"))) {
      try { draft_.pin(project->handle, id, revision, name, selected.at("document")); requested_.reset(); }
      catch (const std::exception &error) { draft_.reset(); edit_error_ = error.what(); }
    }
  }

  bool candidate_edits() const { return draft_.dirty() && !draft_.matches(draft_.workflow_id(), draft_.name(), draft_.baseline()); }

  /** The draft edits exactly the workflow shown, at the revision it was read at. */
  bool draft_current() const
  {
    const auto &selected = workflows_->selected();
    return !workspace_detached_ && draft_.pinned() && !selected.is_null() && draft_.workflow_id() == io::get_string(selected, "id") &&
        draft_.revision() == workflows_->selected_revision();
  }
  bool detached() const { return draft_.dirty() && !draft_current(); }
  bool editable(EditorContext &ctx) const
  {
    return draft_current() && !workflows_->stale() && !workflows_->busy() && !workflows_->uncertain() &&
        !ctx.store.project().busy() && !ctx.area.shell().text_input_active() && !archived(ctx);
  }
  /** The shown workflow is archived: it cannot be changed (it still runs as it is) until restored or copied. */
  bool archived(EditorContext &ctx) const
  {
    return ctx.store.archive().archived("workflow", io::get_string(workflows_->selected(), "id"));
  }

  AnalysisCandidateKey candidate_key(EditorContext &ctx) const
  {
    const auto &project = ctx.store.project().project();
    return {project ? project->handle : std::string(), draft_.workflow_id(), workflows_->session(),
            draft_.revision(), draft_.generation(), draft_.check_version()};
  }
  const Json *checked(EditorContext &ctx) const
  {
    return candidate_edits() && draft_current() ? workflows_->candidate().result(candidate_key(ctx)) : nullptr;
  }

  WorkflowViewText words(EditorContext &ctx) const
  {
    WorkflowViewText text;
    for (const auto *kind : kKinds) { text.kinds[kind] = std::string(ctx.tr(std::string("workflow.kind.") + kind)); }
    text.after = std::string(ctx.tr("workflow.port.after"));
    text.done = std::string(ctx.tr("workflow.port.done"));
    text.files = std::string(ctx.tr("workflow.files_count"));
    return text;
  }

  /** What the canvas and panels show: the unsaved candidate (with its check, or provisional
   * summaries until the check arrives; changed steps marked) or the saved workflow. */
  void rebuild(EditorContext &ctx)
  {
    const auto *result = checked(ctx);
    const auto key = std::make_tuple(workflows_->selected_version(), draft_.generation(), draft_.version(),
                                     result != nullptr, std::string(ctx.store.language()));
    if (shown_ && *shown_ == key) { return; }
    shown_ = key;
    const auto &selected = workflows_->selected();
    const auto previous = view_ ? view_->id : std::string();
    view_error_.clear();
    if (selected.is_null() || io::get_string(selected, "state") != "readable") {
      view_.reset(); canvas_.set_view(nullptr); shown_document_ = shown_validation_ = nullptr; candidate_shown_ = false;
      return;
    }
    candidate_shown_ = candidate_edits() && draft_current();
    if (candidate_shown_) {
      shown_document_ = draft_.document();
      if (result) { checked_document_ = shown_document_; checked_validation_ = *result; shown_validation_ = *result; }
      else {
        // Until this candidate's check arrives, steps keep the summaries of the last checked candidate or the saved workflow.
        shown_validation_ = workflow_provisional_validation(shown_document_, {{&checked_document_, &checked_validation_},
            {&selected.at("document"), &workflows_->validation()}});
      }
    }
    else {
      if (workflows_->validation().is_null()) { return; }  // the saved workflow is shown once checked
      shown_document_ = selected.at("document");
      shown_validation_ = workflows_->validation();
    }
    // Registered templates have catalog names (the service reports their English name).
    for (auto &summary : shown_validation_["steps"]) {
      if (io::get_string(summary, "kind") != "simulation") { continue; }
      const auto &steps = shown_document_.at("steps");
      for (const auto &step : steps) {
        if (io::get_string(step, "id") != io::get_string(summary, "id")) { continue; }
        auto key = "workflow.template." + io::get_string(member(step, "ref"), "template");  // demo-synthetic/1 -> demo_synthetic_1
        std::replace_if(key.begin() + 18, key.end(), [](const char c) { return !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')); }, '_');
        if (ctx.store.catalog().has(std::string(ctx.store.language()), key)) { summary["name"] = std::string(ctx.tr(key)); }
      }
    }
    try {
      auto view = std::make_shared<AnalysisGraphView>(workflow_graph_view(shown_document_, shown_validation_, words(ctx)));
      const auto edited = candidate_shown_ ? draft_.edited_steps() : std::set<std::string>{};
      for (auto &node : view->nodes) { node.edited = edited.count(node.id) != 0; }
      view->id = io::get_string(selected, "id");
      const bool same = view->id == previous && view_project_ == project_id(ctx);
      view_project_ = project_id(ctx);
      view_ = std::move(view);
      if (drag_ == Drag::None) { canvas_.set_view(view_, same); }
      if (!same) {
        fit_ = true;
        restore_.reset();
        if (const auto *memory = remembered(project_id(ctx), view_->id)) {
          restore_ = *memory;  // applied instead of fitting once the canvas size is known
          if (want_step_.empty()) { selected_id_ = memory->step; }
          if (want_run_.empty() && !memory->run.empty()) { want_run_ = memory->run; want_run_workflow_ = view_->id; }
        }
      }
      if (!want_step_.empty()) { selected_id_ = want_step_; want_step_.clear(); }
    }
    catch (const std::exception &error) {
      view_.reset(); canvas_.set_view(nullptr);
      view_error_ = error.what();
    }
  }

  void place_canvas(const double width, const double height)
  {
    if (restore_ && view_ && restore_->workflow == view_->id) {
      const auto memory = *restore_;
      restore_.reset();
      if (memory.placed && canvas_.look_at({memory.x, memory.y}, memory.zoom, width, height, ui_scale_)) { fit_ = false; return; }
    }
    if (!fit_ || !canvas_.fit(width, height, ui_scale_)) { return; }
    fit_ = false;
  }

  static std::string project_id(const EditorContext &ctx)
  {
    const auto &project = ctx.store.project().project();
    return project ? project->id : std::string();
  }

  const ViewMemory *remembered(const std::string &project, const std::string &workflow) const
  {
    for (const auto &memory : memory_) {
      if (memory.project == project && memory.workflow == workflow) { return &memory; }
    }
    return nullptr;
  }

  /** What the shown workflow shows now (U4), once it is settled: read, not being dragged, and no other
   * workflow on its way. The canvas part is known once it was placed; until then the restored or
   * remembered one is kept. */
  std::optional<ViewMemory> snapshot() const
  {
    if (!view_ || !workflows_ || drag_ != Drag::None || pending_ || workflows_->busy() ||
        io::get_string(workflows_->selected(), "id") != view_->id || view_project_.empty()) { return std::nullopt; }
    ViewMemory memory{view_project_, view_->id};
    memory.step = selected_id_;
    const auto &run = workflows_->run();
    if (!want_run_.empty() && want_run_workflow_ == view_->id) { memory.run = want_run_; }  // still being read
    else if (!run.is_null() && io::get_string(run, "workflow_id") == view_->id) { memory.run = io::get_string(run, "id"); }
    const auto center = canvas_.center();
    const ViewMemory *known = restore_ && restore_->workflow == view_->id ? &*restore_ : remembered(view_project_, view_->id);
    if (!fit_ && !restore_ && center) {
      memory.placed = true; memory.x = center->x; memory.y = center->y; memory.zoom = canvas_.zoom();
    }
    else if (known && known->placed) {
      memory.placed = true; memory.x = known->x; memory.y = known->y; memory.zoom = known->zoom;
    }
    return memory;
  }

  static void keep(std::vector<ViewMemory> &memories, ViewMemory memory)
  {
    std::erase_if(memories, [&](const ViewMemory &old) { return old.project == memory.project && old.workflow == memory.workflow; });
    memories.push_back(std::move(memory));
    if (memories.size() > kMemoryLimit) { memories.erase(memories.begin()); }
  }

  /** Keep the shown workflow's view among the most recent kMemoryLimit (every frame and before leaving it). */
  void remember()
  {
    if (auto memory = snapshot()) { keep(memory_, std::move(*memory)); }
  }

  /** The shown workflow is about to be replaced by another: keep its view first. */
  void leave()
  {
    remember();
    restore_.reset();
  }

  void breadcrumb(ui::Layout &row, EditorContext &ctx)
  {
    if (!breadcrumb_.is_object()) { return; }
    const auto &project = ctx.store.project().project();
    if (!project || project->handle != io::get_string(breadcrumb_, "handle")) { breadcrumb_ = nullptr; return; }
    const auto shown = io::get_string(workflows_->selected(), "id");
    if (shown != breadcrumb_child_ && pending_ != breadcrumb_child_) { return; }
    auto *shell = &ctx.area.shell(); auto *area = &ctx.area;
    const auto self = lifetime(), origin = breadcrumb_origin_;
    const auto crumb = breadcrumb_;
    row.button("workflow_breadcrumb_parent", ctx.store.catalog().format("workflow.interface.back",
        {{"name", io::get_string(crumb, "workflow_name")}}), [this, shell, area, self, origin, crumb, ok = valid()] {
      if (!ok() || !store_->project().project() || store_->project().project()->handle != io::get_string(crumb, "handle")) { return; }
      shell->return_in_area_later(area, self, origin, kEditorWorkflow,
          {{"workflow_id", io::get_string(crumb, "workflow_id")}, {"step", io::get_string(crumb, "step")}});
    }).width(7).disable(shell->text_input_active());
  }

  Json interface_value() const
  {
    if (draft_.pinned() && member(draft_.document(), "interface").is_object()) { return draft_.document().at("interface"); }
    return {{"inputs", Json::object()}, {"outputs", Json::object()}, {"parameters", Json::array()}};
  }

  Json interface_default(const std::string &name) const
  {
    const auto boundary = interface_value();
    for (const auto &item : boundary.at("parameters")) {
      if (io::get_string(item, "name") == name) { return member(item, "default"); }
    }
    return nullptr;
  }

  bool composed_document() const { return draft_.pinned() && member(draft_.document(), "format") == "stk.workflow/2"; }
  bool wrapped_literal(const Json &value) const
  {
    return composed_document() && value.is_object() && value.size() == 1 && value.contains("$literal");
  }
  Json parameter_value(const Json &value) const { return wrapped_literal(value) ? value.at("$literal") : value; }
  Json parameter_literal(const Json &value) const
  {
    return composed_document() && value.is_object() && value.size() == 1 &&
        (value.contains("$field") || value.contains("$param") || value.contains("$literal")) ? Json{{"$literal", value}} : value;
  }

  static std::string interface_name(const Json &items, const std::string &base)
  {
    std::set<std::string> names;
    if (items.is_object()) { for (const auto &[name, value] : items.items()) { (void)value; names.insert(name); } }
    else { for (const auto &item : items) { names.insert(io::get_string(item, "name")); } }
    if (!names.contains(base)) { return base; }
    for (int i = 2; ; ++i) {
      auto name = base.substr(0, 56) + "_" + std::to_string(i);
      if (!names.contains(name)) { return name; }
    }
  }

  static bool interface_parameter_fits(const Json &origin, const Json &target)
  {
    const auto type = io::get_string(origin, "type"), wanted = io::get_string(target, "type");
    const bool compatible = type == wanted || (type == "integer" && (wanted == "number" || wanted == "step")) ||
        (type == "json" && (wanted == "vector3" || wanted == "int3" || wanted == "range"));
    return compatible && (io::get_string(target, "unit").empty() || io::get_string(origin, "unit") == io::get_string(target, "unit"));
  }

  void remove_interface(const std::string &direction, const std::string &name)
  {
    auto boundary = interface_value();
    const auto result = draft_.edit_group(draft_.generation(), [&](WorkflowDraft &draft) -> WorkflowDraft::EditResult {
      if (direction == "parameters") {
        Json kept = Json::array(), fallback;
        for (const auto &item : boundary.at("parameters")) {
          if (io::get_string(item, "name") == name) { fallback = item.at("default"); }
          else { kept.push_back(item); }
        }
        boundary["parameters"] = kept;
        const auto steps = draft.document().at("steps");
        for (const auto &step : steps) {
          for (const auto &[parameter, value] : member(step, "parameters").items()) {
            if (value == Json{{"$param", name}}) {
              const auto edit = draft.set_parameter(io::get_string(step, "id"), parameter, parameter_literal(fallback), draft.generation());
              if (!edit.accepted) { return edit; }
            }
          }
        }
      }
      else {
        boundary[direction].erase(name);
        if (direction == "inputs") {
          const auto steps = draft.document().at("steps");
          for (const auto &step : steps) {
            for (const auto &[port, link] : member(step, "inputs").items()) {
              if (io::get_string(link, "from") == "$input." + name) {
                const auto edit = draft.set_link(io::get_string(step, "id"), port, std::nullopt, draft.generation());
                if (!edit.accepted) { return edit; }
              }
            }
          }
          auto &outputs = boundary["outputs"];
          for (auto it = outputs.begin(); it != outputs.end();) {
            if (io::get_string(it.value(), "from") == "$input." + name) { it = outputs.erase(it); }
            else { ++it; }
          }
        }
      }
      return draft.set_interface(boundary, draft.generation());
    });
    edited(result);
  }

  void interface_panel(ui::Layout &layout, EditorContext &ctx)
  {
    if (!draft_.pinned()) { return; }
    auto *panel = layout.panel("workflow_interface", ctx.tr("workflow.interface.title"), false);
    if (!panel) { return; }
    panel->paragraph(ctx.tr("workflow.interface.hint"));
    const auto boundary = interface_value();
    const auto guard = edit_guard(ctx);
    const bool can = editable(ctx);
    for (const char *direction : {"inputs", "outputs"}) {
      panel->label(ctx.tr(std::string("workflow.interface.") + direction));
      for (const auto &[name, port] : boundary.at(direction).items()) {
        auto &row = panel->row();
        row.label(name + " · " + io::get_string(port, "type") +
                  (port.contains("from") ? " ← " + io::get_string(port, "from") : std::string()));
        row.button(std::string("workflow_interface_remove/") + direction + "/" + name, ctx.tr("workflow.interface.remove"),
            [this, guard, direction = std::string(direction), name] {
          if (guard() && !unapplied_text_edits()) { remove_interface(direction, name); }
        }).width(4).disable(!can || unapplied_text_edits());
      }
    }
    Json defaults = Json::object();
    for (const auto &parameter : boundary.at("parameters")) {
      const auto name = io::get_string(parameter, "name");
      defaults[name] = member(parameter, "default");
      panel->button("workflow_interface_remove/parameters/" + name,
          ctx.store.catalog().format("workflow.interface.remove_parameter", {{"name", name}}), [this, guard, name] {
        if (guard() && !unapplied_text_edits()) { remove_interface("parameters", name); }
      }).disable(!can || unapplied_text_edits());
    }
    auto &scope = panel->scope("workflow_interface_defaults");
    parameters(scope, ctx, guard, {{"id", "$interface"}, {"parameters", defaults}},
               {{"parameters", boundary.at("parameters")}}, can, true);
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
  /** A deferred edit applies only while this editor, its project opening and the draft generation are unchanged. */
  std::function<bool()> edit_guard(EditorContext &ctx)
  {
    auto ok = valid();
    const auto generation = draft_.generation(), version = draft_.version();
    auto *shell = &ctx.area.shell();
    return [this, ok, generation, version, shell] {
      return ok() && draft_.generation() == generation && draft_.version() == version && draft_current() && !workflows_->busy() &&
          !workflows_->uncertain() && !workflows_->stale() && !shell->text_input_active();
    };
  }
  void edited(const WorkflowDraft::EditResult &result)
  {
    if (result.accepted) { edit_error_.clear(); redraw(); }
    else { refuse(result.error); }
  }
  bool history_ready(const AppShell &shell) const
  {
    const auto &project = store_->project().project();
    return project && project->handle == draft_.handle() && project->revision == draft_.revision() && draft_current() &&
        !workflows_->busy() && !workflows_->uncertain() && !workflows_->stale() && !store_->project().busy() &&
        !shell.text_input_active() && !unapplied_text_edits() && drag_ == Drag::None &&
        !store_->archive().archived("workflow", draft_.workflow_id());
  }
  void apply_history(const bool forward)
  {
    if (forward ? !draft_.can_redo() : !draft_.can_undo()) { return; }
    const auto check = draft_.check_version();
    const auto result = forward ? draft_.redo(draft_.generation()) : draft_.undo(draft_.generation());
    if (result.accepted) {
      if (draft_.check_version() != check) { requested_.reset(); }
      clear_parameter_text();
      name_text_ = draft_.name(); name_source_ = {draft_.generation(), draft_.version()};
      label_text_ = draft_.step(selected_id_) ? io::get_string(*draft_.step(selected_id_), "label") : std::string();
      label_source_ = {selected_id_, draft_.generation(), draft_.version()};
      shown_.reset();
    }
    edited(result);
  }
  void history_controls(ui::Layout &row, EditorContext &ctx)
  {
    const std::weak_ptr<bool> weak = alive_;
    auto *shell = &ctx.area.shell();
    const auto generation = draft_.generation(), version = draft_.version();
    const auto ready = [this, weak, shell, shell_weak = shell->lifetime(), generation, version] {
      const auto live = weak.lock();
      return live && *live && !shell_weak.expired() && draft_.generation() == generation && draft_.version() == version &&
          history_ready(*shell);
    };
    row.button("workflow_undo", ctx.tr("editor_history.undo"), [this, ready] {
      if (ready()) { apply_history(false); }
    }).width(3).disable(!ready() || !draft_.can_undo()).tip(ctx.tr("editor_history.undo.tip"));
    row.button("workflow_redo", ctx.tr("editor_history.redo"), [this, ready] {
      if (ready()) { apply_history(true); }
    }).width(3).disable(!ready() || !draft_.can_redo()).tip(ctx.tr("editor_history.redo.tip"));
  }

  /** Place steps that have no saved position where they are drawn, so adding or removing a step
   * does not rearrange the others. */
  WorkflowDraft::EditResult freeze_layout(WorkflowDraft &draft) const
  {
    if (!view_) { return {true, {}}; }
    std::map<std::string, std::pair<double, double>> positions;
    for (const auto &node : view_->nodes) {
      if (!node.supplied_position && !node.ambiguous_id) { positions[node.id] = {node.rect.x, node.rect.y}; }
    }
    if (positions.empty()) { return {true, {}}; }
    return draft.move_steps(positions, draft.generation());
  }
  WorkflowDraft::EditResult structural_edit(const std::function<WorkflowDraft::EditResult(WorkflowDraft &)> &change)
  {
    return draft_.edit_group(draft_.generation(), [this, &change](WorkflowDraft &draft) {
      const auto positioned = freeze_layout(draft);
      return positioned.accepted ? change(draft) : positioned;
    });
  }

  void remove_step(const std::string &id)
  {
    if (unapplied_text_edits()) { return; }
    const auto result = structural_edit([&id](WorkflowDraft &draft) { return draft.remove_step(id, draft.generation()); });
    if (result.accepted) { selected_id_.clear(); }
    edited(result);
  }

  void cancel_drag()
  {
    if (drag_ == Drag::Node && view_) { canvas_.set_view(view_, true); }
    drag_ = Drag::None; drag_moved_ = false;
    canvas_.set_pending_link(std::nullopt);
  }
  void drag_move(const double x, const double y)
  {
    if (drag_ == Drag::Link) {
      canvas_.set_pending_link(std::pair{canvas_.to_screen(link_from_), AnalysisGraphPoint{x, y}});
      redraw(); return;
    }
    if (!drag_moved_ && std::hypot(x - press_x_, y - press_y_) < 4 * ui_scale_) { return; }
    const double scale = canvas_.zoom() * canvas_.ui_scale();
    if (!view_ || drag_node_ >= view_->nodes.size() || !(scale > 0)) { cancel_drag(); return; }
    drag_moved_ = true; drag_dx_ = (x - press_x_) / scale; drag_dy_ = (y - press_y_) / scale;
    // Only the picture moves while dragging; the candidate changes once, on release.
    canvas_.set_view(std::make_shared<const AnalysisGraphView>(analysis_graph_view_moved(*view_, drag_node_, drag_dx_, drag_dy_)), true);
    redraw();
  }
  void drag_finish(EditorContext &ctx, const double x, const double y)
  {
    const auto drag = std::exchange(drag_, Drag::None);
    canvas_.set_pending_link(std::nullopt);
    if (view_) { canvas_.set_view(view_, true); }
    if (!view_ || !editable(ctx)) { drag_moved_ = false; redraw(); return; }
    if (drag == Drag::Node && drag_moved_ && drag_node_ < view_->nodes.size()) {
      const auto &node = view_->nodes[drag_node_];
      edited(draft_.move_steps({{node.id, {node.rect.x + drag_dx_, node.rect.y + drag_dy_}}}, draft_.generation()));
    }
    if (drag == Drag::Link) {
      const auto port = canvas_.hit_port(x, y);
      if (port && !port->output) {
        const auto &target = view_->nodes[port->node];
        const auto &input = target.inputs[port->port];
        const auto after = std::string(ctx.tr("workflow.port.after"));
        if (target.ambiguous_id) { refuse(std::string(ctx.tr("workflow.edit.cannot_link"))); }
        else if (input.name == after) {
          // Any output dropped on the after socket orders the steps.
          std::vector<std::string> steps;
          if (const auto *step = draft_.step(target.id)) {
            for (const auto &before : member(*step, "after")) { steps.push_back(before.get<std::string>()); }
          }
          if (std::find(steps.begin(), steps.end(), link_node_) == steps.end()) { steps.push_back(link_node_); }
          edited(draft_.set_after(target.id, steps, draft_.generation()));
          if (draft_.step(target.id)) { selected_id_ = target.id; }
        }
        else if (!input.declared || input.type_text != link_type_) {
          refuse(ctx.store.catalog().format("workflow.edit.type_mismatch", {{"source", link_type_}, {"target", input.type_text}}));
        }
        else {
          edited(draft_.set_link(target.id, input.name, link_node_ + "." + link_port_, draft_.generation()));
          selected_id_ = target.id;
        }
      }
    }
    drag_moved_ = false;
    redraw();
  }

  void list_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("workflow_list_panel", ctx.tr("workflow.list"), true);
    if (!panel) { return; }
    auto ok = valid();
    const bool locked = draft_.dirty() || unapplied_text_edits() || workflows_->uncertain();
    archive_switch(*panel, ctx, "workflow", show_archived_, "workflow_show_archived");
    const auto page = workflows_->page();
    if (page.is_null()) { panel->paragraph(ctx.tr(workflows_->busy() ? "workflow.loading" : "workflow.choose")); }
    else {
      if (!io::get_string(page, "error").empty()) { panel->paragraph(clipped(io::get_string(page, "error"))); }
      const auto &rows = member(page, "workflows");
      if (rows.empty()) { panel->paragraph(ctx.tr("workflow.empty")); }
      else {
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
        spec.selected = {[selected_row] { return selected_row; }, [this, ok, rows, revision](const int row) {
          if (ok() && !draft_.dirty() && !unapplied_text_edits() && row >= 0 && size_t(row) < rows.size() &&
              io::get_int(workflows_->page(), "revision", -1) == revision) {
            if (io::get_string(rows[size_t(row)], "id") != io::get_string(workflows_->selected(), "id")) { leave(); }
            auto_selected_ = true; selected_id_.clear();
            workflows_->load(io::get_string(rows[size_t(row)], "id"));
          }
        }};
        panel->table("workflow_list", std::move(spec)).disable(workflows_->busy() || locked);
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
    }
    // A new, empty workflow; the name can be changed before or after saving its first steps.
    const auto total = page.is_null() ? int64_t(0) : io::get_int(page, "total", 0);
    const auto name = ctx.store.catalog().format("workflow.new_name", {{"n", std::to_string(total + 1)}});
    panel->button("workflow_new", ctx.tr("workflow.new"), [this, ok, name] {
      if (!ok() || draft_.dirty() || unapplied_text_edits()) { return; }
      selected_id_.clear();
      workflows_->create(name, Json{{"format", "stk.workflow/1"}, {"steps", Json::array()}, {"ui", Json::object()}});
    }).disable(workflows_->busy() || locked || ctx.store.project().busy());
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
    if (workflows_->stale() && !draft_.dirty()) { layout.paragraph(ctx.tr("workflow.stale")); }
    if (workflows_->uncertain()) { layout.paragraph(ctx.tr("workflow.uncertain")); }
    if (!workflows_->notice().empty() && !draft_.dirty()) { layout.paragraph(ctx.tr(workflows_->notice())); }
    if (!workflows_->error().empty()) { layout.paragraph(clipped(workflows_->error(), 512)); }
    archived_notice(layout, ctx, "workflow", io::get_string(selected, "id"));
    auto &shelf = layout.row();
    archive_button(shelf, ctx, "workflow", io::get_string(selected, "id"), "workflow_archive", true,
                   !draft_.dirty() && !unapplied_text_edits() && !workflows_->busy() && !workflows_->uncertain());
    if (io::get_string(selected, "state") == "readable") {
      // A copy is a new, active workflow: the way to change an archived one without restoring it.
      const auto name = ctx.store.catalog().format("workflow.copy_name", {{"name", io::get_string(selected, "name")}});
      const auto document = selected.at("document");
      shelf.button("workflow_copy", ctx.tr("workflow.copy"), [this, ok = valid(), name, document] {
        if (ok() && !draft_.dirty() && !unapplied_text_edits()) { selected_id_.clear(); workflows_->create(name, document); }
      }).disable(draft_.dirty() || unapplied_text_edits() || workflows_->busy() || workflows_->uncertain() || ctx.store.project().busy())
          .tip(ctx.tr("workflow.copy.tip"));
    }
  }

  /** Name, adding steps, the pending changes, their check, Save/Discard and Delete. */
  void edit_panel(ui::Layout &layout, EditorContext &ctx)
  {
    if (io::get_string(workflows_->selected(), "state") != "readable") { return; }
    const auto count = change_count();
    auto *panel = layout.panel("workflow_edit_panel", count ? ctx.store.catalog().format("workflow.edit.title_count",
        {{"count", std::to_string(count)}}) : std::string(ctx.tr("workflow.edit.title")), true);
    if (!panel) { return; }
    auto &catalog = ctx.store.catalog();
    auto guard = edit_guard(ctx);
    const bool can = editable(ctx);
    if (detached()) {
      panel->paragraph(ctx.tr("workflow.edit.detached"));
      panel->button("workflow_discard", ctx.tr("workflow.edit.discard"), [this, ok = valid()] {
        if (ok() && draft_.revert(draft_.generation())) { clear_parameter_text(); draft_.reset(); requested_.reset(); redraw(); }
      });
      return;
    }
    // The name is a field of the stored record, saved with the document.
    if (!ctx.area.shell().text_input_active() && name_source_ != std::make_pair(draft_.generation(), draft_.version()) &&
        (name_source_.first != draft_.generation() || name_text_ == draft_.name())) {
      name_text_ = draft_.name(); name_source_ = {draft_.generation(), draft_.version()};
    }
    auto &name = panel->row();
    ui::TextFieldOptions options; options.max_length = 1024;
    auto &name_input = name.text_field("workflow_name", ui::bind(name_text_), options);
    name_input_id_ = name_input.id;
    name.button("workflow_rename", ctx.tr("workflow.edit.rename"), [this, guard] {
      if (guard()) { edited(draft_.set_name(name_text_, draft_.generation())); }
    }).width(4).disable(!can || name_text_ == draft_.name());

    add_step(*panel, ctx, guard, can);

    if (draft_.dirty()) {
      for (const auto &id : draft_.edited_steps()) {
        panel->paragraph(catalog.format(draft_.baseline().is_null() || !step_in(draft_.baseline(), id) ?
            "workflow.edit.change_added" : "workflow.edit.change_step", {{"step", id}}));
      }
      for (const auto &step : member(draft_.baseline(), "steps")) {
        const auto id = io::get_string(step, "id");
        if (!draft_.step(id)) { panel->paragraph(catalog.format("workflow.edit.change_removed", {{"step", id}})); }
      }
      if (draft_.name() != draft_.baseline_name()) {
        panel->paragraph(catalog.format("workflow.edit.change_name", {{"name", clipped(draft_.name(), 80)}}));
      }
    }
    const auto *result = checked(ctx);
    const bool checking = candidate_edits() && !result && workflows_->candidate().pending();
    if (candidate_edits()) {
      if (checking) { panel->paragraph(ctx.tr("workflow.edit.checking")); }
      else if (result) {
        const auto issues = member(*result, "issues").size() + size_t(io::get_int(*result, "omitted_issues", 0));
        panel->paragraph(issues ? catalog.format("workflow.edit.candidate_issues", {{"count", std::to_string(issues)}}) :
                                  std::string(ctx.tr("workflow.edit.candidate_valid")));
      }
      else if (const auto error = workflows_->candidate().error(candidate_key(ctx)); !error.empty()) {
        panel->paragraph(clipped(error, 256));
      }
    }
    if (!edit_error_.empty()) { panel->paragraph(clipped(edit_error_, 256)); }
    if (unapplied_text_edits()) { panel->paragraph(ctx.tr("workflow.edit.unapplied_text")); }
    if (draft_.dirty() && !can) {
      // Why Save is unavailable for a moment (detached edits have their own message above).
      panel->paragraph(ctx.tr(ctx.area.shell().text_input_active() ? "workflow.edit.finish_text" : "workflow.edit.rereading"));
    }
    auto &actions = panel->row();
    const auto version = workflows_->selected_version();
    // Drafts may be saved with issues (they stay listed); only the check of this candidate must be in.
    const bool ready = !candidate_edits() || result || !workflows_->candidate().error(candidate_key(ctx)).empty();
    actions.button("workflow_save", ctx.tr("workflow.edit.save"), [this, guard, version] {
      if (guard() && !unapplied_text_edits() && draft_.dirty()) { workflows_->update(draft_.name(), draft_.document(), version); }
    }).disable(!can || unapplied_text_edits() || !draft_.dirty() || !ready);
    actions.button("workflow_discard", ctx.tr("workflow.edit.discard"), [this, ok = valid()] {
      if (ok() && draft_.revert(draft_.generation())) {
        clear_parameter_text(); name_text_ = draft_.name(); name_source_ = {draft_.generation(), draft_.version()};
        label_source_ = {}; requested_.reset(); edit_error_.clear(); redraw();
      }
    }).disable((!draft_.dirty() && !unapplied_text_edits()) || !draft_.pinned() || ctx.area.shell().text_input_active());
    // Deleting is an ordinary undoable table edit of the managed workflow table.
    const auto id = io::get_string(workflows_->selected(), "id");
    auto *project = &ctx.store.project();
    actions.button("workflow_delete", ctx.tr("workflow.edit.delete"), [this, guard, project, id] {
      if (!guard() || draft_.dirty() || unapplied_text_edits()) { return; }
      if (project->apply(Json::array({{{"op", "delete_record"}, {"id", id}}}))) {
        workflows_->clear_selection(); draft_.reset(); selected_id_.clear(); auto_selected_ = false; shown_ = {};
        if (store_ && store_->toast) { store_->toast(std::string(store_->tr("workflow.edit.deleted")), ui::ToastKind::Info); }
      }
    }).disable(!can || draft_.dirty() || unapplied_text_edits()).tip(ctx.tr("workflow.edit.delete.tip"));
  }

  /** Added or changed steps, removed steps and a renamed workflow. */
  size_t change_count() const
  {
    if (!draft_.dirty()) { return 0; }
    size_t count = draft_.edited_steps().size() + (draft_.name() != draft_.baseline_name());
    for (const auto &step : member(draft_.baseline(), "steps")) { count += draft_.step(io::get_string(step, "id")) ? 0 : 1; }
    return std::max<size_t>(count, 1);  // moves alone count as one change
  }

  static bool step_in(const Json &document, const std::string &id)
  {
    for (const auto &step : member(document, "steps")) { if (io::get_string(step, "id") == id) { return true; } }
    return false;
  }

  /** Kind and object dropdowns from project.workflows.choices, placed right of the selection. */
  void add_step(ui::Layout &panel, EditorContext &ctx, const std::function<bool()> &guard, const bool can)
  {
    const auto &choices = workflows_->choices();
    std::vector<std::string> kinds;
    for (const auto *kind : kKinds) { kinds.push_back(std::string(ctx.tr(std::string("workflow.kind.") + kind))); }
    add_kind_ = std::clamp(add_kind_, 0, int(std::size(kKinds)) - 1);
    const std::string kind = kKinds[add_kind_];
    std::vector<std::string> labels, values;
    const auto list = [&](const char *key) -> const Json & { return member(choices, key); };
    if (kind == "table") {
      for (const auto &table : list("tables")) { labels.push_back(clipped(io::get_string(table, "name"), 60)); values.push_back(io::get_string(table, "id")); }
    }
    else if (kind == "files") {
      for (const auto &snapshot : list("snapshots")) {
        const auto files = member(snapshot, "file_count");
        labels.push_back(io::get_string(snapshot, "created_at").substr(0, 19) +
            (files.is_number_integer() ? "  · " + ctx.store.catalog().format("workflow.files_count", {{"count", std::to_string(files.get<int64_t>())}}) : std::string()));
        values.push_back(io::get_string(snapshot, "id"));
      }
    }
    else if (kind == "simulation") {
      for (const auto &item : list("templates")) {
        labels.push_back(io::get_string(item, "name") + " (" + io::get_string(item, "id") + ")"); values.push_back(io::get_string(item, "id"));
      }
    }
    else if (kind == "workflow") {
      for (const auto &item : list("workflows")) {
        if (io::get_string(item, "id") == draft_.workflow_id()) { continue; }
        labels.push_back(clipped(io::get_string(item, "name"), 60)); values.push_back(io::get_string(item, "id"));
      }
    }
    else {
      for (const auto &analysis : list("analyses")) { labels.push_back(clipped(io::get_string(analysis, "name"), 60)); values.push_back(io::get_string(analysis, "id")); }
    }
    add_object_ = values.empty() ? 0 : std::clamp(add_object_, 0, int(values.size()) - 1);
    auto &row = panel.row();
    row.dropdown("workflow_add_kind", std::move(kinds), ui::bind(add_kind_)).width(5).disable(!can);
    const bool empty = values.empty();
    if (empty) { labels.push_back(std::string(ctx.tr(choices.is_null() ? "workflow.edit.choices_loading" : "workflow.edit.no_objects"))); }
    row.dropdown("workflow_add_object", std::move(labels), ui::bind(add_object_)).disable(!can || empty);
    panel.button("workflow_add_step", ctx.tr("workflow.edit.add_step"), [this, guard, kind, values] {
      if (!guard() || unapplied_text_edits() || values.empty() || add_object_ < 0 || size_t(add_object_) >= values.size()) { return; }
      const auto result = structural_edit([&](WorkflowDraft &draft) {
        return draft.add_step(kind, ref_key(kind), values[size_t(add_object_)], place(), draft.generation());
      });
      if (result.accepted) { selected_id_ = result.id; fit_ = true; }  // refit so the new step is in view
      edited(result);
    }).disable(!can || empty);
  }

  /** Right of the selected step (or of the rightmost one), moved down past steps already there. */
  std::optional<std::pair<double, double>> place() const
  {
    if (!view_ || view_->nodes.empty()) { return std::pair{0.0, 0.0}; }
    const AnalysisGraphRect *anchor = nullptr;
    if (const auto index = selected_index()) { anchor = &view_->nodes[*index].rect; }
    else {
      for (const auto &node : view_->nodes) { if (!anchor || node.rect.x > anchor->x) { anchor = &node.rect; } }
    }
    double x = anchor->x + anchor->width + 80, y = anchor->y;
    for (bool moved = true; moved;) {
      moved = false;
      for (const auto &node : view_->nodes) {
        if (std::abs(node.rect.x - x) < anchor->width && std::abs(node.rect.y - y) < node.rect.height + 20) {
          y = node.rect.y + node.rect.height + 30; moved = true;
        }
      }
    }
    return std::pair{x, y};
  }

  /** Read the shown run again while the service executes it (at most twice a second); once it stops, the
   * run list is read again for its final counts. */
  bool run_due()
  {
    const auto &run = workflows_->run();
    if (run.is_null() || !workflows_->runs_supported()) { return false; }
    const auto status = io::get_string(run, "status");
    if (status != "running" && status != "cancel_requested") {
      // Retried until the read is accepted (the project is often busy while a run registers outputs).
      if (status == "stopped" && run_finished_ != io::get_string(run, "id") && workflows_->load_runs()) {
        run_finished_ = io::get_string(run, "id");
      }
      return false;
    }
    run_finished_.clear();
    return std::chrono::steady_clock::now() - last_poll_ > std::chrono::milliseconds(500);
  }

  bool stale_due(const int64_t revision) const
  {
    const auto &run = workflows_->run();
    return !run.is_null() && io::get_string(run, "status") == "stopped" && workflows_->runs_supported() &&
        stale_key_ != io::get_string(run, "id") + "@" + std::to_string(revision) && !store_->project().busy();
  }

  /** "simulate: T 325 → 330 K" and the like, for a stale task. */
  std::string run_step_label(const std::string &step) const
  {
    const auto &path = member(member(member(workflows_->run(), "composition"), "step_paths"), step.c_str());
    if (!path.is_array()) { return step; }
    std::string label;
    for (const auto &part : path) { if (part.is_string()) { label += (label.empty() ? "" : " › ") + part.get<std::string>(); } }
    return label.empty() ? step : label;
  }

  std::string reason_text(EditorContext &ctx, const std::string &step, const Json &reason) const
  {
    auto &catalog = ctx.store.catalog();
    const auto code = io::get_string(reason, "code");
    const auto value = [](const Json &v) { return v.is_string() ? v.get<std::string>() : v.dump(); };
    return catalog.format("workflow.run.reason." + code, {{"step", run_step_label(step)}, {"name", io::get_string(reason, "name")},
        {"before", value(member(reason, "before"))}, {"after", value(member(reason, "after"))},
        {"upstream", run_step_label(io::get_string(reason, "step"))}});
  }

  /** The parameter table of the saved workflow's single table step (runs take their rows from it). */
  const ProjectTable *run_table(EditorContext &ctx) const
  {
    if (member(workflows_->validation(), "execution").is_object()) {
      const auto id = io::get_string(workflows_->validation().at("execution"), "table_id");
      for (const auto &table : ctx.store.project().tables()) { if (table.id == id) { return &table; } }
      return nullptr;
    }
    const auto &document = member(workflows_->selected(), "document");
    const Json *only = nullptr;
    int count = 0;
    for (const auto &step : member(document, "steps")) {
      if (io::get_string(step, "kind") == "table") { only = &step; ++count; }
    }
    if (count != 1) { return nullptr; }
    const auto id = io::get_string(member(*only, "ref"), "table");
    for (const auto &table : ctx.store.project().tables()) { if (table.id == id) { return &table; } }
    return nullptr;
  }

  std::string row_text(EditorContext &ctx, const ProjectTable &table, const ProjectRecord &record, size_t number) const
  {
    // The values this workflow takes from the row, so rows are recognizable (for example "T 325 K").
    std::set<std::string> used;
    for (const auto &step : member(member(workflows_->selected(), "document"), "steps")) {
      for (const auto &[name, value] : member(step, "parameters").items()) {
        (void)name;
        if (value.is_object() && value.contains("$field") && value.at("$field").is_string()) { used.insert(value.at("$field").get<std::string>()); }
      }
    }
    if (remote_steps()) {
      // A MuFerro step takes the whole case row: name it by its text and unit-bearing fields (case, temperature).
      for (const auto &field : table.fields) {
        if (field.type == "text" || !field.unit.empty()) { used.insert(field.id); }
      }
    }
    std::string values;
    for (const auto &field : table.fields) {
      if (!used.count(field.id) || !record.values.is_object() || !record.values.contains(field.id)) { continue; }
      const auto &value = record.values.at(field.id);
      values += "  · " + field.name + " " + (value.is_string() ? value.get<std::string>() : value.dump()) +
          (field.unit.empty() ? std::string() : " " + field.unit);
    }
    return ctx.store.catalog().format("workflow.run.row", {{"n", std::to_string(number)}, {"values", values}});
  }

  void run_panel(ui::Layout &layout, EditorContext &ctx)
  {
    if (io::get_string(workflows_->selected(), "state") != "readable") { return; }
    auto *panel = layout.panel("workflow_run_panel", ctx.tr("workflow.run.title"), true);
    if (!panel) { return; }
    const auto &project = ctx.store.project().project();
    if (!project) { return; }
    if (project->format_version < 10) { panel->paragraph(ctx.tr("workflow.run.needs_upgrade")); return; }
    if (!workflows_->runs_supported()) { panel->paragraph(ctx.tr("workflow.run.unsupported")); return; }
    hint(*panel, ctx, "workflow.run.intro");
    auto &catalog = ctx.store.catalog();
    auto ok = valid();
    const bool idle = !workflows_->busy() && !ctx.store.project().busy() && !workflows_->stale();
    const auto *table = run_table(ctx);
    std::string blocked;
    if (unapplied_text_edits()) { blocked = "workflow.edit.unapplied_text"; }
    else if (draft_.dirty()) { blocked = "workflow.run.save_first"; }
    else if (!member(member(member(workflows_->selected(), "document"), "interface"), "inputs").empty()) { blocked = "workflow.interface.run_parent"; }
    else if (!io::get_bool(workflows_->validation(), "ok", false)) { blocked = "workflow.run.fix_first"; }
    else if (!table) { blocked = "workflow.run.no_table"; }
    if (!blocked.empty()) { panel->paragraph(ctx.tr(blocked)); }
    if (table) {
      if (!project_record_pages(*panel, ctx, ctx.store.project(), *table, ok, 100)) { return; }
      // Rows are chosen unless unchecked here, so rows added later are included too.
      if (run_rows_table_ != table->id) { run_rows_table_ = table->id; run_unchecked_.clear(); run_only_.reset(); }
      if (!want_rows_.empty() && table->id == want_rows_table_ && want_table_.empty()) {
        // An explicit handoff remains a whitelist across pages; unloaded rows must never
        // cause this to fall back to running every record on the currently visible page.
        run_only_ = std::move(want_rows_); want_rows_.clear(); run_unchecked_.clear();
        if (std::none_of(table->records.begin(), table->records.end(), [&](const auto &r) { return run_only_->count(r.id); })) {
          ctx.store.project().load_table_page(table->id, 0, *run_only_->begin());
        }
      }
      for (size_t i = 0; i < table->loaded_records() && i < 100; ++i) {
        const auto id = table->records[i].id;
        panel->checkbox("workflow_run_row/" + std::to_string(i + 1), row_text(ctx, *table, table->records[i], size_t(table->record_offset) + i + 1),
            {[this, id] { return run_only_ ? run_only_->count(id) != 0 : run_unchecked_.count(id) == 0; }, [this, ok, id](const bool on) {
              if (!ok()) { return; }
              if (run_only_) { if (on && run_only_->size() < 100) { run_only_->insert(id); } else if (!on) { run_only_->erase(id); } }
              else if (on) { run_unchecked_.erase(id); } else { run_unchecked_.insert(id); }
              redraw();
            }}).disable(ctx.store.project().busy() || (run_only_ && run_only_->size() >= 100 && !run_only_->count(id)));
      }
      if (table->total_records() > 100) { panel->paragraph(ctx.tr("workflow.run.row_limit")); }
      auto &choose = panel->row();
      std::vector<std::string> all;
      for (size_t i = 0; i < table->loaded_records() && i < 100; ++i) { all.push_back(table->records[i].id); }
      size_t combined = run_only_ ? run_only_->size() : 0;
      if (run_only_) { for (const auto &id : all) { combined += !run_only_->count(id); } }
      choose.button("workflow_run_all", ctx.tr("workflow.run.all"), [this, ok, all, combined] {
        if (!ok() || combined > 100) { return; }
        for (const auto &id : all) { if (run_only_) { run_only_->insert(id); } else { run_unchecked_.erase(id); } }
        redraw();
      }).width(4).disable(ctx.store.project().busy() || combined > 100);
      choose.button("workflow_run_none", ctx.tr("workflow.run.none"), [this, ok, all] {
        if (!ok()) { return; }
        if (run_only_) { for (const auto &id : all) { run_only_->erase(id); } }
        else { run_unchecked_.insert(all.begin(), all.end()); }
        redraw();
      }).width(4).disable(ctx.store.project().busy());
      std::vector<std::string> rows;
      if (run_only_) { rows.assign(run_only_->begin(), run_only_->end()); }
      else {
        for (size_t i = 0; i < table->loaded_records() && i < 100; ++i) {
          const auto &id = table->records[i].id;
          if (!run_unchecked_.count(id)) { rows.push_back(id); }
        }
      }
      // MuFerro steps run on a Runtime connection chosen here and frozen in the run (W5).
      Json simulation;
      bool target_ready = true;
      std::string start_text = catalog.format("workflow.run.start", {{"count", std::to_string(rows.size())}});
      if (remote_steps()) {
        hint(*panel, ctx, "workflow.run.remote_intro");
        const auto connection = target_.runtime_controls(*panel, ctx);
        const auto options = target_.options_controls(*panel, ctx);
        target_ready = !connection.empty() && options.has_value() && !ctx.store.jobs().hub();
        if (target_ready) {
          simulation = {{"connection", connection}, {"options", *options}};
          start_text = catalog.format("workflow.run.start_on", {{"count", std::to_string(rows.size())},
                                                                {"runtime", SimulationTarget::runtime_name(ctx, connection)}});
        }
        else { panel->paragraph(ctx.tr("workflow.run.choose_runtime")); }
      }
      panel->button("workflow_run_start", start_text, [this, ok, rows, simulation, state = &ctx.store.project(),
                    table_id = table->id, offset = table->record_offset] {
        if (!ok() || state->busy() || draft_.dirty() || unapplied_text_edits()) { return; }
        if (!member(member(member(workflows_->selected(), "document"), "interface"), "inputs").empty()) { return; }
        for (const auto &live : state->tables()) {
          if (live.id == table_id && live.record_offset == offset) { run_row_ = -1; workflows_->run_rows(rows, simulation); return; }
        }
      }).disable(!blocked.empty() || rows.empty() || rows.size() > 100 || !idle || ctx.store.project().busy() || !target_ready);
    }
    runs_list(*panel, ctx);
    run_detail(*panel, ctx);
  }

  /** The run's results back to the conversation (P2 L3): its MuFerro result rows (temperature, final step,
   * energy) captured as a new context, then the AI assistant opens on it. Reads and captures only. */
  void results_question(ui::Layout &panel, EditorContext &ctx, const Json &run)
  {
    std::vector<std::string> results;
    std::string result_table;
    for (const auto &task : member(run, "tasks")) {
      const auto record = io::get_string(member(task, "produced"), "result_record_id");
      if (io::get_string(task, "status") != "succeeded" || record.empty()) { continue; }
      const auto step = io::get_string(task, "step");
      const auto engine = io::get_string(member(member(run, "steps"), step.c_str()), "template");
      const std::string table = engine == "muferro/1" ? "04d7cc6c-5da5-5c92-a860-f3368f7b376d" :
          engine == "lammps/1" ? "3f63a5bf-fc98-5c23-b211-7dcb31a5b173" : "";
      if (table.empty() || (!result_table.empty() && result_table != table)) { return; }
      result_table = table;
      if (std::find(results.begin(), results.end(), record) == results.end()) { results.push_back(record); }
    }
    if (results.empty() || results.size() > 100) { return; }
    const ProjectTable *table = nullptr;
    for (const auto &candidate : ctx.store.project().tables()) {
      // The frozen execution identifies its engine's result table; row pages are
      // irrelevant to finding its field metadata or capturing exact produced IDs.
      if (candidate.id == result_table) {
        table = &candidate;
      }
    }
    if (!table) { return; }
    std::vector<std::string> fields;
    for (const auto &field : table->fields) {
      if (field.type == "number" || field.type == "integer") { fields.push_back(field.id); }  // not file lists or IDs
    }
    auto &discussion = ctx.store.project().discussion();
    const auto title = ctx.store.catalog().format("workflow.run.results_title", {{"name", io::get_string(run, "workflow_name")},
                                                                                 {"count", std::to_string(results.size())}});
    auto open = project_navigation_action(ctx, "conversation");
    auto ok = valid();
    const auto table_id = table->id;
    panel.button("workflow_run_ask_results", ctx.store.catalog().format("workflow.run.ask_results", {{"count", std::to_string(results.size())}}),
        [ok, &discussion, table_id, results, fields, title, open] {
      if (!ok()) { return; }
      discussion.capture(table_id, results, fields, title, [ok, open](const bool captured) { if (captured && ok() && open) { open(); } });
    }).disable(fields.empty() || discussion.busy() || ctx.store.project().busy() || !discussion.supported())
        .tip(ctx.tr("workflow.run.ask_results.tip"));
  }

  /** Whether the shown workflow has a simulation step that runs on a Runtime (muferro/1;
   * suan/workflows/templates.py marks such templates ``remote``). */
  /** Whether the shown workflow has a simulation step that runs on a Runtime: a template the service reports as
   * remote (any registered engine; docs/design/multiscale-engines.md), or muferro/1 for services older than that flag. */
  bool remote_steps() const
  {
    if (io::get_bool(member(workflows_->validation(), "execution"), "requires_runtime", false)) { return true; }
    const auto &templates = member(workflows_->choices(), "templates");
    for (const auto &step : member(member(workflows_->selected(), "document"), "steps")) {
      if (io::get_string(step, "kind") != "simulation") { continue; }
      const auto id = io::get_string(member(step, "ref"), "template");
      bool reported = false;
      for (const auto &item : templates) {
        if (io::get_string(item, "id") == id && item.contains("remote")) {
          reported = true;
          if (io::get_bool(item, "remote", false)) { return true; }
        }
      }
      if (!reported && id == "muferro/1") { return true; }
    }
    return false;
  }

  void runs_list(ui::Layout &panel, EditorContext &ctx)
  {
    const auto &runs = member(workflows_->runs(), "runs");
    archive_switch(panel, ctx, "workflow_run", show_archived_runs_, "workflow_runs_show_archived", false);
    if (runs.empty()) { return; }
    panel.label(ctx.tr("workflow.run.runs"));
    std::vector<std::vector<std::string>> cells;
    int selected = -1;
    for (size_t i = 0; i < runs.size(); ++i) {
      const auto &entry = runs[i];
      if (io::get_string(entry, "id") == io::get_string(workflows_->run(), "id")) { selected = int(i); }
      const auto status = io::get_string(entry, "status");
      const auto done = io::get_int(member(entry, "counts"), "succeeded", 0);
      int64_t total = 0;
      for (const auto &[name, value] : member(entry, "counts").items()) { (void)name; total += value.get<int64_t>(); }
      cells.push_back({io::get_string(entry, "created_at").substr(0, 19), std::to_string(io::get_int(entry, "rows", 0)),
                       std::string(ctx.tr(io::get_bool(entry, "complete", false) ? "workflow.run.complete" : "workflow.run.status." + status)),
                       std::to_string(done) + "/" + std::to_string(total)});
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("workflow.run.column.time")), 9}, {std::string(ctx.tr("workflow.run.column.rows")), 3},
                    {std::string(ctx.tr("workflow.run.column.status")), 5}, {std::string(ctx.tr("workflow.run.column.done")), 4}};
    spec.rows = int(runs.size()); spec.visible_rows = float(std::min(4, spec.rows));
    spec.data_version = workflows_->run_version();
    spec.cell = [cells](const int row, const int column) { return cells.at(size_t(row)).at(size_t(column)); };
    auto ok = valid();
    spec.selected = {[selected] { return selected; }, [this, ok, runs](const int row) {
      if (ok() && row >= 0 && size_t(row) < runs.size()) { run_row_ = -1; workflows_->load_run(io::get_string(runs[size_t(row)], "id")); }
    }};
    panel.table("workflow_runs", std::move(spec)).disable(workflows_->busy());
  }

  void run_detail(ui::Layout &panel, EditorContext &ctx)
  {
    const auto &run = workflows_->run();
    if (run.is_null() || io::get_string(run, "workflow_id") != io::get_string(workflows_->selected(), "id")) { return; }
    auto &catalog = ctx.store.catalog();
    const auto status = io::get_string(run, "status");
    const auto &counts = member(run, "counts");
    int64_t total = 0;
    for (const auto &[name, value] : counts.items()) { (void)name; total += value.get<int64_t>(); }
    const auto failed = io::get_int(counts, "failed", 0) + io::get_int(counts, "interrupted", 0);
    panel.paragraph(catalog.format("workflow.run.summary", {
        {"status", std::string(ctx.tr(io::get_bool(run, "complete", false) ? "workflow.run.complete" : "workflow.run.status." + status))},
        {"done", std::to_string(io::get_int(counts, "succeeded", 0))}, {"total", std::to_string(total)},
        {"failed", failed ? catalog.format("workflow.run.failed_count", {{"count", std::to_string(failed)}}) : std::string()}}));
    const auto run_id = io::get_string(run, "id");
    const bool run_archived = archived_notice(panel, ctx, "workflow_run", run_id);
    // Rows x steps: each cell is the task's latest attempt (ADE pattern 1: a step is a task, each execution an attempt).
    const auto &order = member(run, "order");
    const auto &rows = member(run, "rows");
    std::map<std::pair<std::string, std::string>, const Json *> tasks;
    for (const auto &task : member(run, "tasks")) { tasks[{io::get_string(task, "step"), io::get_string(task, "row")}] = &task; }
    // Staleness of this run against the current definitions (W4c), when read for this run.
    const auto &stale = workflows_->run_staleness();
    std::map<std::string, const Json *> stale_rows;
    if (io::get_string(stale, "run_id") == io::get_string(run, "id")) {
      for (const auto &row : member(stale, "rows")) { stale_rows[io::get_string(row, "id")] = &row; }
    }
    std::vector<std::vector<std::string>> cells;
    std::vector<std::vector<std::string>> states;
    std::vector<std::string> outdated;
    for (const auto &row : rows) {
      const auto row_id = io::get_string(row, "id");
      const auto found_row = stale_rows.find(row_id);
      const bool row_stale = found_row != stale_rows.end() && io::get_bool(*found_row->second, "stale", false);
      if (row_stale) { outdated.push_back(row_id); }
      std::vector<std::string> line{std::to_string(io::get_int(row, "number", 0)) +
                                    (row_stale ? " · " + std::string(ctx.tr("workflow.run.stale_mark")) : std::string())}, state{""};
      for (const auto &step : order) {
        const auto found = tasks.find({step.get<std::string>(), row_id});
        const auto task_status = found == tasks.end() ? std::string("pending") : io::get_string(*found->second, "status");
        const auto attempt = found == tasks.end() ? int64_t(0) : io::get_int(*found->second, "attempt", 0);
        const bool step_stale = row_stale && !member(member(*found_row->second, "steps"), step.get_ref<const std::string &>().c_str()).empty();
        // A remote attempt shows where its Runtime task is (submitted, queued, running, collecting).
        const auto &progress = found == tasks.end() ? Json() : member(*found->second, "progress");
        const bool remote = task_status == "running" && progress.is_object() && io::get_int(progress, "attempt", 0) == attempt;
        line.push_back(std::string(ctx.tr(remote ? "workflow.run.stage." + io::get_string(progress, "stage") : "workflow.run.task." + task_status)) +
                       (attempt > 1 ? " #" + std::to_string(attempt) : std::string()) +
                       (step_stale ? " · " + std::string(ctx.tr("workflow.run.stale_mark")) : std::string()));
        state.push_back(step_stale && task_status == "succeeded" ? "stale" : task_status);
      }
      cells.push_back(std::move(line)); states.push_back(std::move(state));
    }
    if (!outdated.empty()) {
      panel.paragraph(catalog.format("workflow.run.stale_summary", {{"count", std::to_string(outdated.size())}}));
    }
    if (const auto &stopped = member(run, "stop_error"); stopped.is_object()) {
      panel.paragraph(catalog.format("workflow.run.stopped_error", {{"message", clipped(io::get_string(stopped, "message"), 300)}}));
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("workflow.run.row_column")), 4}};
    for (const auto &step : order) { spec.columns.push_back({run_step_label(step.get<std::string>()), 6}); }
    spec.rows = int(rows.size()); spec.visible_rows = float(std::min(8, spec.rows));
    spec.data_version = workflows_->run_version();
    spec.cell = [cells](const int row, const int column) { return cells.at(size_t(row)).at(size_t(column)); };
    spec.cell_color = [states](const int row, const int column) -> ui::Color {
      const auto &value = states.at(size_t(row)).at(size_t(column));
      if (value == "failed" || value == "interrupted") { return ui::Color::rgb(0xE07A7A); }
      if (value == "succeeded") { return ui::Color::rgb(0x8FCB9B); }
      if (value == "running" || value == "stale") { return ui::Color::rgb(0xE8C46A); }
      return {0, 0, 0, 0};
    };
    const int chosen = run_row_;
    spec.selected = {[chosen] { return chosen; }, [this](const int row) { run_row_ = row; redraw(); }};
    panel.table("workflow_run_tasks", std::move(spec));
    results_question(panel, ctx, run);
    if (run_row_ >= 0 && size_t(run_row_) < rows.size()) {
      const auto row_id = io::get_string(rows[size_t(run_row_)], "id");
      if (const auto found = stale_rows.find(row_id); found != stale_rows.end()) {
        for (const auto &step : order) {
          for (const auto &reason : member(member(*found->second, "steps"), step.get_ref<const std::string &>().c_str())) {
            panel.paragraph(reason_text(ctx, step.get<std::string>(), reason));
          }
        }
      }
      for (const auto &step : order) {
        const auto found = tasks.find({step.get<std::string>(), row_id});
        if (found == tasks.end()) { continue; }
        const auto &task = *found->second;
        const auto &error = member(task, "error");
        if (error.is_object()) {
          panel.paragraph(catalog.format("workflow.run.task_error", {{"step", run_step_label(step.get<std::string>())},
              {"message", clipped(io::get_string(error, "message"), 300)}}));
        }
        if (const auto &progress = member(task, "progress"); progress.is_object() && !io::get_string(progress, "simulation_run_id").empty()) {
          const auto task_id = io::get_string(progress, "task_id");
          panel.paragraph(catalog.format("workflow.run.remote_detail", {{"step", run_step_label(step.get<std::string>())},
              {"run", io::get_string(progress, "simulation_run_id").substr(0, 8)},
              {"task", task_id.empty() ? std::string("—") : task_id.substr(0, 12)},
              {"state", std::string(ctx.tr(io::get_string(task, "status") == "running" ? "workflow.run.stage." + io::get_string(progress, "stage")
                                                                                      : "workflow.run.task." + io::get_string(task, "status")))}}));
        }
        const auto analysis_run = io::get_string(member(task, "produced"), "analysis_run_id");
        const auto &frozen = member(member(run, "steps"), step.get_ref<const std::string &>().c_str());
        if (!analysis_run.empty()) {
          auto *shell = &ctx.area.shell();
          auto *area = &ctx.area;
          const auto self = lifetime();
          const Json target = {{"analysis_id", io::get_string(frozen, "analysis_id")}, {"analysis_run_id", analysis_run}};
          panel.button("workflow_run_open/" + step.get<std::string>(),
              catalog.format("workflow.run.open_analysis", {{"step", run_step_label(step.get<std::string>())}}), [shell, area, self, target] {
            shell->open_in_area_later(area, self, kEditorAnalysisGraph, target);
          }).disable(shell->text_input_active());
        }
      }
    }
    else { panel.paragraph(ctx.tr("workflow.run.pick_row")); }
    auto ok = valid();
    // Old results stay; stale rows run again as a new run over the current definitions (never rewriting this one).
    const bool can_run = !draft_.dirty() && !unapplied_text_edits() && io::get_bool(workflows_->validation(), "ok", false) && !workflows_->stale() &&
        !workflows_->busy() && !ctx.store.project().busy();
    // Stale rows run again where this run ran (its frozen Runtime connection and options, if any).
    Json simulation;
    if (const auto &frozen = member(run, "simulation"); frozen.is_object()) {
      simulation = {{"connection", io::get_string(frozen, "connection")}, {"options", member(frozen, "options")}};
    }
    panel.button("workflow_run_stale", catalog.format("workflow.run.rerun_stale", {{"count", std::to_string(outdated.size())}}),
        [this, ok, outdated, simulation] {
          if (ok() && !draft_.dirty() && !unapplied_text_edits()) { run_row_ = -1; workflows_->run_rows(outdated, simulation); }
        })
        .disable(outdated.empty() || status != "stopped" || !can_run).tip(ctx.tr("workflow.run.rerun_stale.tip"));
    auto &actions = panel.row();
    actions.button("workflow_run_retry", ctx.tr("workflow.run.retry"), [this, ok] { if (ok()) { workflows_->start_run(); } })
        .disable(status != "stopped" || io::get_bool(run, "complete", false) || workflows_->busy() || run_archived);
    actions.button("workflow_run_cancel", ctx.tr("workflow.run.cancel"), [this, ok] { if (ok()) { workflows_->cancel_run(); } })
        .disable(status != "running" || workflows_->busy());
    actions.button("workflow_run_recover", ctx.tr("workflow.run.recover"), [this, ok] { if (ok()) { workflows_->recover_run(); } })
        .disable((status != "running" && status != "cancel_requested") || workflows_->busy())
        .tip(ctx.tr("workflow.run.recover.tip"));
    archive_button(actions, ctx, "workflow_run", run_id, "workflow_run_archive", false,
                   status != "running" && status != "cancel_requested" && !workflows_->busy());
  }

  void issues_panel(ui::Layout &layout, EditorContext &ctx)
  {
    const auto &issues = member(shown_validation_, "issues");
    if (issues.empty()) { return; }
    auto *panel = layout.panel("workflow_issues_panel", ctx.tr(candidate_shown_ ? "workflow.issues_candidate" : "workflow.issues"), true);
    if (!panel) { return; }
    const std::weak_ptr<bool> weak = alive_;
    for (size_t i = 0; i < issues.size() && i < 64; ++i) {
      const auto &issue = issues[i];
      const auto code = io::get_string(issue, "code"), step = io::get_string(issue, "step");
      const auto title = ctx.store.catalog().tr_or("workflow.issue." + code, code);
      panel->button("workflow_issue/" + std::to_string(i), clipped(step + " · " + std::string(title), 80),
                    [this, weak, step] {
        if (const auto live = weak.lock(); live && *live) { selected_id_ = step; redraw(); }
      }).tip(clipped(io::get_string(issue, "message"), 512) + "\n" + io::get_string(issue, "path"));
    }
    if (issues.size() > 64) {
      panel->paragraph(ctx.store.catalog().format("workflow.more_issues", {{"count", std::to_string(issues.size() - 64)}}));
    }
  }

  /** The fields of the parameter tables this workflow's table steps reference, in table order. */
  std::vector<std::pair<std::string, std::string>> workflow_fields(EditorContext &ctx, const Json &parameter) const
  {
    std::set<std::string> tables;
    for (const auto &step : member(shown_document_, "steps")) {
      if (io::get_string(step, "kind") == "table") { tables.insert(io::get_string(member(step, "ref"), "table")); }
    }
    std::vector<std::pair<std::string, std::string>> fields;
    for (const auto &table : ctx.store.project().tables()) {
      if (!tables.count(table.id)) { continue; }
      for (const auto &field : table.fields) {
        // Keep exactly the backend's FIELD_PARAMETER_TYPES and exact-unit policy. In particular,
        // select values are choice UUIDs, not business enum labels, and are not string fields.
        const auto type = io::get_string(parameter, "type"), unit = io::get_string(parameter, "unit");
        const bool compatible = (field.type == "number" && type == "number") ||
            (field.type == "integer" && (type == "integer" || type == "number" || type == "step")) ||
            (field.type == "text" && (type == "string" || type == "enum")) ||
            (field.type == "boolean" && type == "boolean") ||
            (field.type == "json" && (type == "json" || type == "vector3" || type == "int3" || type == "range"));
        if (compatible && (unit.empty() || field.unit == unit)) {
          fields.push_back({field.id, table.name + " · " + field.name});
        }
      }
    }
    return fields;
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
    const auto index = selected_index();
    const auto &steps = member(shown_document_, "steps");
    const auto &summaries = member(shown_validation_, "steps");
    if (!index || *index >= steps.size() || *index >= summaries.size()) { panel->paragraph(ctx.tr("workflow.pick_step")); return; }
    const auto &step = steps[*index];
    const auto &summary = summaries[*index];
    const auto kind = io::get_string(step, "kind"), id = io::get_string(step, "id");
    auto &catalog = ctx.store.catalog();
    const bool can = editable(ctx) && !view_->nodes[*index].ambiguous_id;
    auto guard = edit_guard(ctx);
    panel->label(view_->nodes[*index].label);
    panel->paragraph(catalog.format("workflow.step_id", {{"id", id}, {"kind", std::string(catalog.tr_or("workflow.kind." + kind, kind))}}));
    const auto name = io::get_string(summary, "name");
    if (!name.empty()) { panel->paragraph(catalog.format("workflow.references", {{"name", clipped(name)}})); }
    if (member(summary, "file_count").is_number_integer()) {
      panel->paragraph(catalog.format("workflow.files_count", {{"count", std::to_string(member(summary, "file_count").get<int64_t>())}}));
    }
    const auto hash = io::get_string(summary, "content_sha256");
    if (!hash.empty()) { panel->paragraph(catalog.format("workflow.content_hash", {{"hash", hash.substr(0, 12)}})); }
    const bool label_active = ctx.ui && label_input_id_ && ctx.ui->editing() == label_input_id_;
    if (can || label_active) { label_editor(*panel, ctx, guard, step); }
    inputs(*panel, ctx, guard, step, summary, can);
    for (const auto &port : member(summary, "outputs")) {
      panel->paragraph(catalog.format("workflow.output", {{"port", io::get_string(port, "name")}, {"type", io::get_string(port, "type")}}));
      const auto name = io::get_string(port, "name"), type = io::get_string(port, "type");
      const auto boundary = interface_value();
      bool published = false;
      for (const auto &value : boundary.at("outputs")) { published |= io::get_string(value, "from") == id + "." + name; }
      panel->button("workflow_publish_output/" + name, ctx.tr("workflow.interface.publish_output"), [this, guard, id, name, type] {
        if (!guard() || unapplied_text_edits()) { return; }
        auto next = interface_value();
        const auto public_name = interface_name(next.at("outputs"), name);
        next["outputs"][public_name] = {{"type", type}, {"from", id + "." + name}};
        edited(draft_.set_interface(next, draft_.generation()));
      }).disable(!can || published || unapplied_text_edits() || boundary.at("outputs").size() >= 32);
    }
    after_editor(*panel, ctx, guard, step, can);
    parameters(*panel, ctx, guard, step, summary, can);
    if (can) {
      panel->button("workflow_remove_step", ctx.tr("workflow.edit.remove_step"), [this, guard, id] {
        if (guard()) { remove_step(id); }
      });
    }
    action(*panel, ctx, step, summary);
  }

  void label_editor(ui::Layout &panel, EditorContext &ctx, const std::function<bool()> &guard, const Json &step)
  {
    const auto id = io::get_string(step, "id");
    const auto source = std::make_tuple(id, draft_.generation(), draft_.version());
    const auto *previous = draft_.step(std::get<0>(label_source_));
    const bool pending = std::get<1>(label_source_) == draft_.generation() && previous &&
        label_text_ != io::get_string(*previous, "label");
    if (!ctx.area.shell().text_input_active() && label_source_ != source && !pending) {
      label_text_ = io::get_string(step, "label"); label_source_ = source;
    }
    auto &row = panel.row();
    ui::TextFieldOptions options; options.max_length = 1024; options.placeholder = std::string(ctx.tr("workflow.edit.label"));
    auto &label_input = row.text_field("workflow_step_label", ui::bind(label_text_), options);
    label_input_id_ = label_input.id;
    row.button("workflow_step_label_apply", ctx.tr("workflow.edit.apply"), [this, guard, id] {
      if (guard()) { edited(draft_.set_label(id, label_text_.empty() ? std::nullopt : std::optional<std::string>(label_text_), draft_.generation())); }
    }).width(4).disable(label_text_ == io::get_string(step, "label"));
  }

  void inputs(ui::Layout &panel, EditorContext &ctx, const std::function<bool()> &guard, const Json &step, const Json &summary,
              const bool can)
  {
    auto &catalog = ctx.store.catalog();
    const auto id = io::get_string(step, "id");
    const auto &links = member(step, "inputs");
    const auto &summaries = member(shown_validation_, "steps");
    for (const auto &port : member(summary, "inputs")) {
      const auto port_name = io::get_string(port, "name"), type = io::get_string(port, "type");
      const auto &link = member(links, port_name.c_str());
      const auto current = link.is_object() ? io::get_string(link, "from") : std::string();
      if (!can) {
        panel.paragraph(link.is_object() ?
            catalog.format("workflow.input_linked", {{"port", port_name}, {"type", type}, {"source", current}}) :
            catalog.format("workflow.input_open", {{"port", port_name}, {"type", type}}));
        continue;
      }
      // Same-type outputs of other steps; an unlisted current link stays visible.
      std::vector<std::string> values{std::string()}, labels{std::string(ctx.tr("workflow.edit.not_linked"))};
      const auto boundary = interface_value();
      for (const auto &[name, input] : boundary.at("inputs").items()) {
        if (io::get_string(input, "type") == type) {
          values.push_back("$input." + name);
          labels.push_back(catalog.format("workflow.interface.input_source", {{"name", name}}));
        }
      }
      for (const auto &other : summaries) {
        const auto other_id = io::get_string(other, "id");
        if (other_id == id) { continue; }
        for (const auto &output : member(other, "outputs")) {
          if (io::get_string(output, "type") != type) { continue; }
          values.push_back(other_id + "." + io::get_string(output, "name"));
          labels.push_back(values.back());
        }
      }
      if (!current.empty() && std::find(values.begin(), values.end(), current) == values.end()) {
        values.push_back(current); labels.push_back(current + "  · " + std::string(ctx.tr("analysis_links.unlisted")));
      }
      const int index = int(std::find(values.begin(), values.end(), current) - values.begin());
      auto &scope = panel.scope("workflow_input/" + port_name);
      scope.label(catalog.format("workflow.edit.input", {{"port", port_name}, {"type", type}}));
      scope.dropdown("source", std::move(labels), {[index] { return index; }, [this, guard, values, id, port_name](const int choice) {
        if (!guard() || choice < 0 || size_t(choice) >= values.size()) { return; }
        const auto &value = values[size_t(choice)];
        edited(draft_.set_link(id, port_name, value.empty() ? std::nullopt : std::optional<std::string>(value), draft_.generation()));
      }});
      scope.button("publish", ctx.tr("workflow.interface.publish_input"), [this, guard, id, port_name, type] {
        if (!guard() || unapplied_text_edits()) { return; }
        auto boundary = interface_value();
        const auto name = interface_name(boundary.at("inputs"), port_name);
        boundary["inputs"][name] = {{"type", type}};
        edited(draft_.edit_group(draft_.generation(), [&](WorkflowDraft &draft) {
          const auto result = draft.set_interface(boundary, draft.generation());
          return result.accepted ? draft.set_link(id, port_name, "$input." + name, draft.generation()) : result;
        }));
      }).disable(!can || unapplied_text_edits() || current.rfind("$input.", 0) == 0 || boundary.at("inputs").size() >= 32);
    }
  }

  void after_editor(ui::Layout &panel, EditorContext &ctx, const std::function<bool()> &guard, const Json &step, const bool can)
  {
    auto &catalog = ctx.store.catalog();
    const auto id = io::get_string(step, "id");
    std::vector<std::string> after;
    for (const auto &before : member(step, "after")) { if (before.is_string()) { after.push_back(before.get<std::string>()); } }
    if (!can) {
      std::string text;
      for (const auto &before : after) { text += (text.empty() ? "" : ", ") + before; }
      if (!text.empty()) { panel.paragraph(catalog.format("workflow.after", {{"steps", text}})); }
      return;
    }
    for (const auto &before : after) {
      auto &scope = panel.scope("workflow_after/" + before);
      auto &row = scope.row();
      row.label(catalog.format("workflow.after", {{"steps", before}}));
      row.button("remove", ctx.tr("workflow.edit.remove"), [this, guard, id, after, before] {
        if (!guard()) { return; }
        auto next = after;
        next.erase(std::remove(next.begin(), next.end(), before), next.end());
        edited(draft_.set_after(id, next, draft_.generation()));
      }).width(4);
    }
    std::vector<std::string> others{std::string(ctx.tr("workflow.edit.add_after"))};
    for (const auto &other : member(shown_document_, "steps")) {
      const auto other_id = io::get_string(other, "id");
      if (other_id != id && std::find(after.begin(), after.end(), other_id) == after.end()) { others.push_back(other_id); }
    }
    if (others.size() > 1) {
      panel.dropdown("workflow_after_add", others, {[] { return 0; }, [this, guard, id, after, others](const int choice) {
        if (!guard() || choice <= 0 || size_t(choice) >= others.size()) { return; }
        auto next = after; next.push_back(others[size_t(choice)]);
        edited(draft_.set_after(id, next, draft_.generation()));
      }});
    }
  }

  bool parameter_text_active() const
  {
    return parameter_ui_ && parameter_inputs_.contains(parameter_ui_->editing());
  }
  bool parameter_text_edits() const { return !literal_dirty_.empty() || parameter_text_active(); }
  bool unapplied_text_edits() const
  {
    if (parameter_text_edits()) { return true; }
    if (!draft_.pinned()) { return false; }
    if (parameter_ui_ && parameter_ui_->editing() && (parameter_ui_->editing() == name_input_id_ ||
        parameter_ui_->editing() == label_input_id_)) { return true; }
    if (name_source_.first == draft_.generation() && name_text_ != draft_.name()) { return true; }
    if (std::get<1>(label_source_) == draft_.generation()) {
      if (const auto *step = draft_.step(std::get<0>(label_source_)); step && label_text_ != io::get_string(*step, "label")) { return true; }
    }
    return false;
  }
  void clear_parameter_text()
  {
    literal_text_.clear(); literal_source_.clear(); literal_original_.clear(); literal_dirty_.clear();
    literal_modes_.clear(); parameter_modes_.clear(); parameter_inputs_.clear();
  }

  /** Each declared parameter: an inherited value, a typed literal, or an explicitly chosen
   * compatible field. Text is independent of the candidate until Apply, and survives focus loss,
   * edits of other parameters and workspace migration. */
  void parameters(ui::Layout &panel, EditorContext &ctx, const std::function<bool()> &guard, const Json &step, const Json &summary,
                  const bool can, const bool interface_defaults = false)
  {
    auto &catalog = ctx.store.catalog();
    const auto id = io::get_string(step, "id");
    const auto &values = member(step, "parameters");
    const bool active = parameter_text_active();
    const auto active_key = active ? parameter_inputs_.at(parameter_ui_->editing()) : std::string();
    if (!can && !active) {
      for (const auto &[name, value] : values.items()) {
        const bool field = !interface_defaults && value.is_object() && value.size() == 1 && value.contains("$field") && value.at("$field").is_string();
        panel.paragraph(field ? catalog.format("workflow.parameter_field", {{"name", name}, {"field", field_name(ctx, value.at("$field").get<std::string>())}}) :
                                catalog.format("workflow.parameter_value", {{"name", name}, {"value", clipped((interface_defaults ? value : parameter_value(value)).dump(), 80)}}));
      }
      return;
    }
    if (parameter_workflow_ != draft_.workflow_id()) {
      clear_parameter_text(); parameter_workflow_ = draft_.workflow_id();
    }
    for (const auto &parameter : member(summary, "parameters")) {
      const auto name = io::get_string(parameter, "name");
      const auto key = id + "/" + name;
      const auto type = io::get_string(parameter, "type");
      const auto version = draft_.version();
      const auto current = [this, guard, version] { return guard() && draft_.version() == version; };
      const auto fields = workflow_fields(ctx, parameter);
      const auto &raw_value = member(values, name.c_str());
      const auto value = interface_defaults ? raw_value : parameter_value(raw_value);
      const bool bound = values.is_object() && values.contains(name);
      const bool reference = bound && !interface_defaults && !wrapped_literal(raw_value);
      const bool field = reference && value.is_object() && value.size() == 1 && value.contains("$field") && value.at("$field").is_string();
      const bool forwarded = reference && composed_document() && value.is_object() && value.size() == 1 && value.contains("$param") && value.at("$param").is_string();
      const int stored_mode = !bound ? 0 : field ? 2 : forwarded ? 3 : 1;
      const int mode = interface_defaults ? 1 : parameter_modes_.contains(key) ? parameter_modes_.at(key) : stored_mode;
      auto &scope = panel.scope("workflow_param/" + name);
      const auto label = io::get_string(parameter, "label");
      scope.label(catalog.format("workflow.edit.parameter", {{"name", name}, {"type", io::get_string(parameter, "type")},
                                                             {"label", label.empty() ? name : clipped(label, 40)}}));
      const auto unit = io::get_string(parameter, "unit"), description = io::get_string(parameter, "description");
      if (!unit.empty()) { scope.label(unit); }
      if (!description.empty()) { scope.paragraph(clipped(description, 1024)); }
      std::string bounds;
      for (const char *limit : {"minimum", "maximum"}) {
        if (parameter.contains(limit)) { bounds += (bounds.empty() ? "" : "  ") + std::string(limit) + " = " + parameter.at(limit).dump(); }
      }
      if (!bounds.empty()) { scope.label(bounds); }
      std::vector<std::string> modes{std::string(ctx.tr("workflow.edit.mode_default")), std::string(ctx.tr("workflow.edit.mode_literal")),
                                     std::string(ctx.tr("workflow.edit.mode_field")), std::string(ctx.tr("workflow.interface.parameter_mode"))};
      const auto fallback = member(parameter, "default");
      if (!interface_defaults) {
        auto &mode_row = scope.row();
        mode_row.dropdown("mode", std::move(modes), {[mode] { return mode; }, [this, current, id, name, key, fallback, mode](const int choice) {
        if (!current() || choice < 0 || choice > 3 || choice == mode) { return; }
        if (literal_dirty_.contains(key)) { refuse(std::string(store_->tr("workflow.edit.parameter_unapplied"))); return; }
        if (choice >= 2) { parameter_modes_[key] = choice; }
        else { parameter_modes_.erase(key); }
        if (choice == 0) { edited(draft_.set_parameter(id, name, std::nullopt, draft_.generation())); }
        else if (choice == 1) { edited(draft_.set_parameter(id, name, parameter_literal(fallback), draft_.generation())); }
        else { redraw(); }  // Selecting a mode is not consent to bind an arbitrary first field.
      }}).width(6).disable(!can || literal_dirty_.contains(key));
        bool publishable = bound && !field && !forwarded;
        try { publishable &= io::check_value(value, io::parameter_schema(parameter)).empty(); }
        catch (const std::exception &) { publishable = false; }
        mode_row.button("publish", ctx.tr("workflow.interface.publish_parameter"), [this, current, id, name, parameter, value] {
          if (!current() || unapplied_text_edits()) { return; }
          auto boundary = interface_value();
          const auto public_name = interface_name(boundary.at("parameters"), name);
          Json declaration = {{"name", public_name}, {"type", parameter.at("type")}, {"default", value}};
          for (const char *key : {"label", "unit", "description", "minimum", "maximum", "choices"}) {
            if (parameter.contains(key) && !parameter.at(key).is_null()) { declaration[key] = parameter.at(key); }
          }
          boundary["parameters"].push_back(declaration);
          edited(draft_.edit_group(draft_.generation(), [&](WorkflowDraft &draft) {
            const auto changed = draft.set_interface(boundary, draft.generation());
            return changed.accepted ? draft.set_parameter(id, name, Json{{"$param", public_name}}, draft.generation()) : changed;
          }));
        }).width(5).disable(!can || !publishable || unapplied_text_edits() || interface_value().at("parameters").size() >= 64)
          .tip(ctx.tr("workflow.interface.publish_parameter.tip"));
      }
      if (mode == 1) {
        auto &buffer = literal_text_[key];
        const auto source = std::make_tuple(key, draft_.generation(), draft_.version());
        if (!literal_source_.contains(key) || (literal_source_.at(key) != source && !literal_dirty_.contains(key) && !active)) {
          literal_modes_[key] = type == "string" && value.is_string() ? "string" : "json";
          buffer = literal_modes_[key] == "string" ? value.get<std::string>() : value.dump();
          literal_original_[key] = buffer; literal_source_[key] = source;
        }
        const auto commit = [this, current, id, name, key, parameter, interface_defaults](const Json &next) {
          if (!current()) { return; }
          try {
            if (!io::check_value(next, io::parameter_schema(parameter)).empty()) {
              refuse(std::string(store_->tr("workflow.edit.bad_parameter"))); return;
            }
          }
          catch (const io::GraphModelError &) { /* An unknown schema remains an editable draft. */ }
          WorkflowDraft::EditResult result;
          if (interface_defaults) {
            auto boundary = interface_value();
            for (auto &item : boundary["parameters"]) {
              if (io::get_string(item, "name") == name) { item["default"] = next; }
            }
            result = draft_.set_interface(boundary, draft_.generation());
          }
          else { result = draft_.set_parameter(id, name, parameter_literal(next), draft_.generation()); }
          if (result.accepted) { literal_dirty_.erase(key); literal_source_.erase(key); }
          edited(result);
        };
        const auto &choices = member(parameter, "choices");
        if (type == "boolean" && value.is_boolean() && !literal_dirty_.contains(key)) {
          scope.checkbox("boolean", name, {[value] { return value.get<bool>(); }, [commit](bool next) { commit(Json(next)); }}).disable(!can);
        }
        else if (type == "enum" && choices.is_array() && !choices.empty() && !literal_dirty_.contains(key)) {
          std::vector<std::string> labels{std::string(ctx.tr("workflow.edit.choose_value"))};
          int selected = 0;
          for (size_t i = 0; i < choices.size(); ++i) {
            labels.push_back(choices[i].is_string() ? choices[i].get<std::string>() : choices[i].dump());
            if (io::json_equal(choices[i], value)) { selected = int(i + 1); }
          }
          if (selected == 0) {
            labels.push_back((value.is_string() ? value.get<std::string>() : value.dump()) + " · " + std::string(ctx.tr("analysis_links.unlisted")));
            selected = int(labels.size()) - 1;
          }
          scope.dropdown("choice", std::move(labels), {[selected] { return selected; }, [commit, choices](int choice) {
            if (choice > 0 && size_t(choice) <= choices.size()) { commit(choices[size_t(choice - 1)]); }
          }}).disable(!can);
        }
        else {
          const bool plain = literal_modes_[key] == "string";
          if (plain) { scope.label(ctx.tr("workflow.edit.parameter_string")); }
          else if (type == "json" || type == "range" || type == "vector3" || type == "int3") { scope.label(ctx.tr("workflow.edit.parameter_json")); }
          else if (type != "number" && type != "integer" && type != "step" && type != "enum" && type != "boolean" && type != "string") {
            scope.paragraph(ctx.tr("workflow.edit.parameter_unknown"));
          }
          auto &row = scope.row();
          ui::TextFieldOptions options; options.max_length = 64 * 1024; options.mono = !plain;
          const auto retain = valid();
          const auto workflow = draft_.workflow_id();
          const auto generation = draft_.generation();
          auto &input = row.text_field("value", {[this, key] { return literal_text_.at(key); }, [this, retain, workflow, generation, key](std::string text) {
            // TextField commits after its active edit has ended; older project/draft callbacks
            // cannot replace a different editor's text. Invalid text remains a protected draft.
            if (!retain() || workflow != draft_.workflow_id() || generation != draft_.generation()) { return; }
            literal_text_[key] = std::move(text);
            if (literal_text_[key] == literal_original_[key]) { literal_dirty_.erase(key); }
            else { literal_dirty_.insert(key); }
            redraw();
          }}, options);
          input.disable(!can && !(active && active_key == key));
          parameter_inputs_[input.id] = key;
          const bool live_input = active && active_key == key;
          const bool pending_text = literal_dirty_.contains(key) || (live_input && parameter_ui_->edit_state() &&
              parameter_ui_->edit_state()->text() != literal_original_.at(key));
          row.button("apply", ctx.tr("workflow.edit.apply"), [this, current, key, plain, commit] {
            if (!current()) { return; }
            try { commit(plain ? Json(literal_text_.at(key)) : parse_parameter_json(literal_text_.at(key))); }
            catch (const std::exception &) { refuse(std::string(store_->tr("workflow.edit.bad_json"))); }
          }).width(4).disable((!can && !live_input) || !pending_text);
          row.button("discard", ctx.tr("workflow.edit.reset_value"), [this, current, key] {
            if (!current()) { return; }
            literal_text_[key] = literal_original_.at(key); literal_dirty_.erase(key); redraw();
          }).width(5).disable((!can && !live_input) || !pending_text);
          if (literal_dirty_.contains(key)) { scope.paragraph(ctx.tr("workflow.edit.parameter_unapplied")); }
        }
      }
      else if (mode == 2) {
        std::vector<std::string> labels{std::string(ctx.tr("workflow.edit.choose_field"))};
        int selected = 0;
        for (size_t i = 0; i < fields.size(); ++i) {
          labels.push_back(clipped(fields[i].second, 60));
          if (field && fields[i].first == value.at("$field").get<std::string>()) { selected = int(i + 1); }
        }
        if (field && selected == 0) {
          labels.push_back(field_name(ctx, value.at("$field").get<std::string>()) + "  · " + std::string(ctx.tr("analysis_links.unlisted")));
          selected = int(labels.size()) - 1; scope.paragraph(ctx.tr("workflow.edit.incompatible_field"));
        }
        if (fields.empty()) { scope.paragraph(ctx.tr("workflow.edit.no_compatible_fields")); }
        scope.dropdown("field", std::move(labels), {[selected] { return selected; }, [this, current, id, name, key, fields](const int choice) {
          if (!current() || choice <= 0 || size_t(choice) > fields.size()) { return; }
          parameter_modes_.erase(key);
          edited(draft_.set_parameter(id, name, Json{{"$field", fields[size_t(choice - 1)].first}}, draft_.generation()));
        }}).disable(!can);
      }
      else if (mode == 3) {
        std::vector<std::string> labels{std::string(ctx.tr("workflow.interface.choose_parameter"))}, names;
        int selected = 0;
        const auto boundary = interface_value();
        for (const auto &item : boundary.at("parameters")) {
          if (!interface_parameter_fits(item, parameter)) { continue; }
          const auto candidate = io::get_string(item, "name");
          names.push_back(candidate); labels.push_back(candidate);
          if (forwarded && value.at("$param") == candidate) { selected = int(names.size()); }
        }
        if (forwarded && selected == 0) {
          labels.push_back(value.at("$param").get<std::string>() + " · " + std::string(ctx.tr("analysis_links.unlisted")));
          selected = int(labels.size()) - 1;
        }
        scope.dropdown("workflow_parameter", std::move(labels), {[selected] { return selected; }, [this, current, id, name, key, names](int choice) {
          if (!current() || choice <= 0 || size_t(choice) > names.size()) { return; }
          parameter_modes_.erase(key);
          edited(draft_.set_parameter(id, name, Json{{"$param", names[size_t(choice - 1)]}}, draft_.generation()));
        }}).disable(!can);
      }
    }
  }

  void action(ui::Layout &panel, EditorContext &ctx, const Json &step, const Json &summary)
  {
    const auto kind = io::get_string(step, "kind");
    const auto &ref = member(step, "ref");
    const bool resolved = !member(summary, "inputs").empty() || !member(summary, "outputs").empty();
    if (kind == "workflow") {
      auto *shell = &ctx.area.shell();
      auto *area = &ctx.area;
      const auto self = lifetime();
      const auto &project = ctx.store.project().project();
      const Json target = {{"workflow_id", io::get_string(ref, "workflow")}, {"breadcrumb", {
          {"handle", project ? project->handle : std::string()}, {"workflow_id", draft_.workflow_id()},
          {"workflow_name", draft_.name()}, {"step", io::get_string(step, "id")}}}};
      const auto guard = edit_guard(ctx);
      panel.button("workflow_enter_subworkflow", ctx.tr("workflow.interface.enter"), [shell, area, self, target, guard] {
        shell->open_in_area_later(area, self, kEditorWorkflow, target, guard, true);
      }).disable(member(summary, "name").is_null() || workflows_->busy() || shell->text_input_active());
      return;
    }
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
  Json breadcrumb_;
  std::string breadcrumb_child_;
  std::weak_ptr<void> breadcrumb_origin_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::unique_ptr<ProjectWorkflows> workflows_;
  WorkflowDraft draft_;
  Json workspace_restore_;
  bool workspace_restore_dirty_ = false;
  bool workspace_detached_ = false;
  std::optional<AnalysisCandidateKey> requested_;
  AnalysisGraphCanvas canvas_;
  std::shared_ptr<AnalysisGraphView> view_;
  Json shown_document_, shown_validation_, checked_document_, checked_validation_;
  bool candidate_shown_ = false;
  std::optional<std::tuple<uint64_t, uint64_t, uint64_t, bool, std::string>> shown_;
  std::string selected_id_, want_step_, want_run_, want_run_workflow_, view_error_, edit_error_;
  std::optional<std::string> pending_;
  std::string name_text_, label_text_;
  std::pair<uint64_t, uint64_t> name_source_{~uint64_t(0), 0};
  std::tuple<std::string, uint64_t, uint64_t> label_source_;
  std::map<std::string, std::string> literal_text_;
  std::map<std::string, std::tuple<std::string, uint64_t, uint64_t>> literal_source_;
  std::map<std::string, std::string> literal_original_, literal_modes_;
  std::set<std::string> literal_dirty_;
  std::map<std::string, int> parameter_modes_;
  std::string parameter_workflow_;
  ui::Context *parameter_ui_ = nullptr;
  const std::string ui_scope_ = "workflow_instance_" + std::to_string(workflow_ui_sequence.fetch_add(1, std::memory_order_relaxed));
  ui::WidgetId name_input_id_ = 0, label_input_id_ = 0;
  std::map<ui::WidgetId, std::string> parameter_inputs_;
  int add_kind_ = 3, add_object_ = 0;
  uint64_t epoch_ = 0;
  int64_t refreshed_revision_ = -1, page_revision_ = -1, choices_revision_ = -1, listed_revision_ = -1;
  std::string runs_listed_;  // "workflow@revision" the runs list was last read for
  bool show_archived_ = false, show_archived_runs_ = false;  // the lists show only archived objects
  std::string page_archive_, runs_archive_;  // the archive filter and version each list was read with
  std::set<std::string> run_unchecked_;
  std::optional<std::set<std::string>> run_only_;
  std::string run_rows_table_, run_finished_, stale_key_;
  int run_row_ = -1;
  std::chrono::steady_clock::time_point last_poll_{};
  bool auto_selected_ = false, fit_ = true, dragging_ = false;
  SimulationTarget target_;  // where MuFerro steps run (W5)
  std::string want_table_, want_rows_table_, rows_notice_;  // rows to run from an AI sweep (P2 L2)
  std::set<std::string> want_rows_;
  std::vector<ViewMemory> memory_;  // most recent last
  std::string view_project_;
  std::optional<ViewMemory> restore_;
  std::optional<std::pair<std::string, std::string>> reopen_;  // (project, workflow) the layout last showed
  Drag drag_ = Drag::None;
  bool drag_moved_ = false;
  size_t drag_node_ = 0;
  double press_x_ = 0, press_y_ = 0, drag_dx_ = 0, drag_dy_ = 0;
  std::string link_node_, link_port_, link_type_;
  AnalysisGraphPoint link_from_;
  double last_x_ = 0, last_y_ = 0, ui_scale_ = 1;
  float canvas_top_ = 0;
};

}  // namespace

std::unique_ptr<Editor> make_workflow_editor(const EditorType &type)
{
  return std::make_unique<WorkflowEditor>(type);
}

}  // namespace stk::app
