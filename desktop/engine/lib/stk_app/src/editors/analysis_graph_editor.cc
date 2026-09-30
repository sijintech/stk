/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/analysis_parameter_draft.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/project_analyses.hh"
#include "stk/app/project_analysis_runs.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/ui/gpu_painter.hh"
#include "stk/wm/window.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <set>

namespace stk::app {
namespace {
using io::Json;
using Rows = std::vector<std::vector<std::string>>;

std::string summary(const Json &value) { return project_value_summary(value, 240); }
std::string text(const std::string &value) { return summary(Json(value)); }
void omitted(ui::Layout &layout, EditorContext &ctx, const size_t count)
{
  if (count) { layout.paragraph(ctx.store.catalog().format("analysis_graph.omitted_count", {{"count", std::to_string(count)}})); }
}

void table(ui::Layout &layout, std::string_view key, std::vector<ui::TableColumn> columns,
           Rows rows, const uint64_t version, float visible = 5)
{
  ui::TableSpec spec;
  spec.columns = std::move(columns);
  spec.rows = int(rows.size());
  spec.visible_rows = std::max(1.0f, std::min(visible, float(spec.rows)));
  spec.data_version = version;
  spec.cell = [rows = std::move(rows)](const int row, const int col) {
    return row >= 0 && size_t(row) < rows.size() && col >= 0 && size_t(col) < rows[size_t(row)].size() ?
        rows[size_t(row)][size_t(col)] : std::string();
  };
  layout.table(key, std::move(spec));
}

class AnalysisGraphEditor final : public Editor {
 public:
  explicit AnalysisGraphEditor(const EditorType &type) : Editor(type) {}
  ~AnalysisGraphEditor() override { *alive_ = false; }
  bool draws_gpu() const override { return true; }
  bool has_sidebar() const override { return true; }
  ui::Color main_background(const ui::Theme &) const override { return {0, 0, 0, 0}; }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx);
    const std::weak_ptr<bool> weak = alive_;
    row.button("graph_fit", ctx.tr("analysis_graph.fit"), [this, weak] {
      if (const auto live = weak.lock(); live && *live) { fit_ = true; focus_selected_ = false; redraw(); }
    }).width(3).disable(!state_->view());
    row.button("graph_focus_node", ctx.tr("analysis_graph.focus_node"), [this, weak] {
      if (const auto live = weak.lock(); live && *live) { focus_selected_ = true; redraw(); }
    }).width(5).disable(!selected_);
    auto *shell = &ctx.area.shell();
    auto *screen = ctx.area.screen();
    row.button("graph_viewer", ctx.tr("analysis_graph.view_3d"), [weak, shell, screen] {
      const auto live = weak.lock();
      if (!live || !*live || !screen) { return; }
      shell->activate_editor_later(screen, kEditorViewer, true, [weak] {
        const auto still_live = weak.lock();
        return still_live && *still_live;
      });
    }).width(3).tip(ctx.tr("analysis_graph.view_3d.tip"));
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    const std::weak_ptr<bool> weak = alive_;
    auto *shell = &ctx.area.shell();
    const auto mode = state_->source();
    std::vector<std::string> modes{std::string(ctx.tr("analysis_graph.desired")), std::string(ctx.tr("analysis_graph.displayed")),
        std::string(ctx.tr("analysis_documents.tab")), std::string(ctx.tr("analysis_runs.graph_tab"))};
    ui::Binding<int> mode_binding{[mode] { return int(mode); }, [this, weak, shell](const int value) {
          if (const auto live = weak.lock(); live && *live && value >= 0 && value <= 3 && !shell->text_input_active()) {
            ++navigation_generation_;
            if (value == 3) { state_->show_run(); }
            else if (value == 2) { state_->show_saved(); }
            else { state_->show_displayed(value == 1); }
            redraw();
          }
        }};
    const bool narrow = ctx.draw && ctx.draw->rect.width() < 560 * ctx.draw->ui_scale;
    auto &selector = narrow ? layout.dropdown("graph_mode", std::move(modes), std::move(mode_binding)) :
        layout.tabs("graph_mode", std::move(modes), std::move(mode_binding));
    selector.disable(shell->text_input_active());
    if (!state_->view()) {
      layout.paragraph(ctx.tr(mode == AnalysisGraphState::Source::Run ? "analysis_runs.no_frozen_graph" :
          state_->saved() ? "analysis_documents.no_document" :
          state_->displayed() ? "analysis_graph.no_displayed_graph" : "analysis_graph.no_desired_graph"));
      if (!state_->error().empty()) { layout.paragraph(text(state_->error())); }
      return;
    }
    const auto &view = *state_->view();
    const std::string caption = ctx.store.catalog().format("analysis_graph.canvas_caption",
        {{"nodes", std::to_string(view.nodes.size())}, {"edges", std::to_string(view.edges.size())}});
    layout.label(caption).tip(ctx.tr("analysis_graph.navigation"));
    // Two fixed-height UI rows occupy this band; drawing and pointer coordinates use the same offset.
    canvas_top_ = 3.0f * (ctx.ui ? ctx.ui->style().unit : 20.0f);
  }

  void draw_sidebar(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    if (state_->catalog_loading()) { layout.paragraph(ctx.tr("analysis_graph.catalog_loading")); }
    if (!state_->catalog_error().empty()) {
      layout.paragraph(ctx.tr("analysis_graph.catalog_unavailable"));
      layout.paragraph(text(state_->catalog_error()));
    }
    if (state_->saved()) {
      const std::weak_ptr<bool> weak = alive_;
      layout.tabs("analysis_saved_section", {std::string(ctx.tr("analysis_runs.definition")),
          std::string(ctx.tr("analysis_runs.title"))}, {[value = saved_section_] { return value; },
          [this, weak](const int value) {
        const auto live = weak.lock();
        if (live && *live && value >= 0 && value <= 1 && value != saved_section_) {
          ++navigation_generation_; saved_section_ = value; redraw();
        }
      }});
      if (saved_section_ == 1) { runs_panel(layout, ctx); return; }
    }
    if (state_->source() == AnalysisGraphState::Source::Run) {
      if (parameter_edits()) { layout.paragraph(ctx.tr("analysis_runs.saved_draft_preserved")); }
      const std::weak_ptr<bool> weak = alive_;
      auto *shell = &ctx.area.shell();
      const auto navigation = navigation_generation_;
      layout.button("analysis_run_return_saved", ctx.tr("analysis_runs.return_saved"), [this, weak, shell, navigation] {
        if (const auto live = weak.lock(); live && *live && !shell->text_input_active() &&
            navigation_generation_ == navigation && state_->source() == AnalysisGraphState::Source::Run) {
          ++navigation_generation_; state_->show_saved(); saved_section_ = 0; redraw();
        }
      }).disable(shell->text_input_active());
    }
    else {
      if (state_->saved() || parameter_edits()) { parameter_panel(layout, ctx); }
      documents_panel(layout, ctx);
    }
    source_panel(layout, ctx);
    if (!state_->view()) { return; }
    node_panel(layout, ctx);
    parameters_panel(layout, ctx);
    outputs_panel(layout, ctx);
    validation_panel(layout, ctx);
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
    if (state_->view()) {
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
    if (!ctx.draw || !state_->view()) { return false; }
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
      if (event.button == wm::MouseButton::Left) {
        selected_ = canvas_.hit(x, y); selected_parameter_ = 0; redraw(); return true;
      }
      if (event.button == wm::MouseButton::Middle || event.button == wm::MouseButton::Right) {
        dragging_ = true; last_x_ = x; last_y_ = y; return true;
      }
    }
    if (event.type == wm::EventType::Wheel) {
      if (event.precise) {
        canvas_.pan(event.wheel_x, event.wheel_y);
      }
      else if (event.modifiers & wm::ModShift) {
        canvas_.pan(24.0 * ui_scale_ * event.wheel_y, 0);
      }
      else {
        const double amount = std::clamp(event.wheel_y, -10.0f, 10.0f);
        canvas_.zoom_at(std::exp(amount * 0.13), x, y);
      }
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
    if (event.type != wm::EventType::KeyDown || (event.key != wm::Key::Home && event.key != wm::Key::F)) { return false; }
    attach(ctx);
    focus_selected_ = event.key == wm::Key::F;
    fit_ = !focus_selected_;
    redraw(); return true;
  }

  nlohmann::json save_state() const override
  {
    nlohmann::json result = {{"displayed", state_ ? state_->displayed() : initial_displayed_}};
    if (state_ ? state_->saved() : initial_saved_) { result["saved"] = true; }
    if (state_ ? state_->source() == AnalysisGraphState::Source::Run : initial_run_) { result["run"] = true; }
    return result;
  }
  bool load_state(const nlohmann::json &value) override
  {
    if (!value.is_object() || (value.contains("displayed") && !value.at("displayed").is_boolean()) ||
        (value.contains("saved") && !value.at("saved").is_boolean()) ||
        (value.contains("run") && !value.at("run").is_boolean())) { return false; }
    ++navigation_generation_;
    initial_displayed_ = value.value("displayed", false);
    initial_saved_ = value.value("saved", false);
    initial_run_ = value.value("run", false);
    if (state_) {
      state_->show_displayed(initial_displayed_);
      if (initial_saved_) { state_->show_saved(); }
      state_->clear_run();
      if (initial_run_) { state_->show_run(); }
    }
    return true;
  }

 private:
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::unique_ptr<AnalysisGraphState> state_;
  std::unique_ptr<ProjectAnalyses> documents_;
  std::unique_ptr<ProjectAnalysisRuns> runs_;
  uint64_t document_epoch_ = 0, document_version_ = 0;
  uint64_t navigation_generation_ = 0, document_navigation_ = 0;
  std::string document_name_;
  AnalysisParameterDraft parameter_draft_;
  std::optional<std::string> parameter_key_;
  std::string parameter_buffer_, parameter_original_, parameter_error_;
  bool parameter_buffer_changed_ = false, parameter_detached_ = false, parameter_saving_ = false;
  uint64_t parameter_epoch_ = 0, parameter_selection_ = 0, parameter_save_generation_ = 0, parameter_save_version_ = 0;
  ui::Context *parameter_ui_ = nullptr;
  ui::WidgetId parameter_input_id_ = 0;
  int saved_section_ = 0, snapshot_index_ = -1, file_index_ = -1, output_index_ = -1, mapping_index_ = -1;
  uint64_t runs_epoch_ = 0, run_selection_ = 0, bindings_generation_ = 0;
  std::string binding_name_ = "data", binding_path_, binding_error_;
  Json bindings_ = Json::object();
  AnalysisGraphCanvas canvas_;
  AppStore *store_ = nullptr;
  std::shared_ptr<const AnalysisGraphView> canvas_view_;
  std::optional<size_t> selected_;
  int selected_parameter_ = 0;
  bool fit_ = true, focus_selected_ = false, dragging_ = false, initial_displayed_ = false, initial_saved_ = false, initial_run_ = false;
  double last_x_ = 0, last_y_ = 0, ui_scale_ = 1;
  float canvas_top_ = 60;

  void redraw() { if (store_) { store_->changed(); } }
  bool parameter_text_active() const
  {
    return parameter_ui_ && parameter_input_id_ && parameter_ui_->editing() == parameter_input_id_;
  }
  bool parameter_edits() const
  {
    return parameter_draft_.dirty() || parameter_buffer_changed_ || parameter_text_active();
  }
  bool parameter_current() const
  {
    const auto &project = store_->project().project();
    return parameter_draft_.pinned() && !parameter_detached_ && project &&
        parameter_epoch_ == documents_->epoch() && parameter_selection_ == documents_->selected_version() &&
        parameter_draft_.current(project->handle, project->revision) &&
        parameter_draft_.analysis_id() == io::get_string(documents_->selected(), "id");
  }
  void clear_parameter_draft()
  {
    parameter_draft_.reset(); parameter_key_.reset(); parameter_buffer_.clear(); parameter_original_.clear();
    parameter_error_.clear(); parameter_buffer_changed_ = parameter_detached_ = parameter_saving_ = false;
    parameter_input_id_ = 0;
  }
  Json parameter_declaration(const std::string &name) const
  {
    if (!parameter_draft_.pinned()) { return nullptr; }
    const auto &graph = parameter_draft_.baseline_document().at("graph");
    const auto declarations = graph.find("parameters");
    if (declarations != graph.end() && declarations->is_array()) {
      for (const auto &declaration : *declarations) {
        if (io::get_string(declaration, "name") == name) { return declaration; }
      }
    }
    return nullptr;
  }
  bool parameter_literal() const
  {
    if (!parameter_key_) { return false; }
    const auto declaration = parameter_declaration(*parameter_key_);
    if (io::get_string(declaration, "type") != "string") { return false; }
    auto value = parameter_draft_.override_value(*parameter_key_);
    if (!value && declaration.contains("default")) { value = declaration.at("default"); }
    // Stored editable definitions may contain a non-string under a string declaration.
    // Show its exact JSON until the user explicitly replaces it with a string.
    return !value || value->is_string();
  }
  void parameter_buffer_from_value()
  {
    parameter_buffer_.clear(); parameter_error_.clear(); parameter_buffer_changed_ = false;
    if (parameter_key_) {
      auto value = parameter_draft_.override_value(*parameter_key_);
      const auto declaration = parameter_declaration(*parameter_key_);
      if (!value && declaration.is_object() && declaration.contains("default")) { value = declaration.at("default"); }
      if (value) {
        parameter_buffer_ = parameter_literal() && value->is_string() ? value->get<std::string>() :
            io::python_json_dumps(*value, false, true);
      }
    }
    parameter_original_ = parameter_buffer_;
    parameter_input_id_ = 0;
  }
  void pin_parameters()
  {
    const auto &selected = documents_->selected();
    try {
      if (!parameter_draft_.pinned() || parameter_draft_.analysis_id() != io::get_string(selected, "id")) {
        parameter_key_.reset();
      }
      parameter_draft_.pin(documents_->handle(), io::get_string(selected, "id"), documents_->selected_revision(),
                          io::get_string(selected, "name"), selected.at("document"));
      if (parameter_key_ && !parameter_draft_.has_override(*parameter_key_) && parameter_declaration(*parameter_key_).is_null()) {
        parameter_key_.reset();
      }
      parameter_epoch_ = documents_->epoch(); parameter_selection_ = documents_->selected_version();
      parameter_detached_ = parameter_saving_ = false;
      parameter_buffer_from_value();
    }
    catch (const std::exception &error) { parameter_error_ = error.what(); parameter_detached_ = true; }
  }
  void parameter_panel(ui::Layout &layout, EditorContext &ctx)
  {
    if (!parameter_draft_.pinned()) { return; }
    auto *panel = layout.panel("analysis_parameter_panel", ctx.tr("analysis_parameters.title"), true);
    if (!panel) { return; }
    const std::weak_ptr<bool> weak = alive_;
    const auto generation = parameter_draft_.generation(), version = parameter_draft_.version();
    const auto valid = [this, weak, generation] {
      const auto live = weak.lock();
      if (!live || !*live || parameter_draft_.generation() != generation) { return false; }
      documents_->sync();
      return true;
    };
    const bool unavailable = !parameter_current();
    const bool busy = documents_->busy() || documents_->uncertain() || ctx.store.project().busy();
    const bool blocked = busy || unavailable;
    panel->paragraph(ctx.tr("analysis_parameters.hint"));
    if (parameter_edits()) { panel->paragraph(ctx.tr("analysis_parameters.dirty")); }
    if (unavailable) {
      panel->paragraph(ctx.tr("analysis_parameters.stale"));
      panel->paragraph(text(parameter_draft_.analysis_id()));
    }
    if (!parameter_error_.empty()) { panel->paragraph(text(parameter_error_)); }
    auto &actions = panel->row();
    const auto selection = parameter_selection_;
    actions.button("analysis_parameters_save", ctx.tr("analysis_parameters.save"), [this, valid, version, selection] {
      if (!valid() || !parameter_current() || (parameter_ui_ && parameter_ui_->text_input_active()) || parameter_buffer_changed_ ||
          parameter_draft_.version() != version || !parameter_draft_.dirty() ||
          documents_->selected_version() != selection) { return; }
      if (documents_->replace_parameters(parameter_draft_.parameters(), selection)) {
        parameter_saving_ = true; parameter_save_generation_ = parameter_draft_.generation();
        parameter_save_version_ = parameter_draft_.version(); document_navigation_ = navigation_generation_;
      }
    }).disable(blocked || !parameter_draft_.dirty() || parameter_buffer_changed_ || (parameter_ui_ && parameter_ui_->text_input_active()));
    actions.button("analysis_parameters_discard", ctx.tr("analysis_parameters.discard"), [this, valid] {
      if (!valid() || documents_->busy() || documents_->uncertain() || parameter_text_active()) { return; }
      clear_parameter_draft();
      if (!documents_->selected().is_null() && io::get_string(documents_->selected(), "state") == "readable") {
        pin_parameters();
      }
      redraw();
    }).disable(busy || parameter_text_active() || (!parameter_edits() && !unavailable));

    std::vector<std::string> names;
    std::set<std::string> seen;
    const auto &graph = parameter_draft_.baseline_document().at("graph");
    if (const auto declarations = graph.find("parameters"); declarations != graph.end() && declarations->is_array()) {
      for (const auto &declaration : *declarations) {
        const auto name = io::get_string(declaration, "name");
        if (seen.insert(name).second) { names.push_back(name); }
      }
    }
    const auto parameters = parameter_draft_.parameters();
    // Retain a removed unknown row until save/discard, so removal can be inspected or reversed.
    for (const auto *values : {&parameter_draft_.baseline_document().at("parameters"), &parameters}) {
      for (const auto &[name, unused] : values->items()) { if (seen.insert(name).second) { names.push_back(name); } }
    }
    Rows rows; int selected = -1;
    for (size_t i = 0; i < names.size(); ++i) {
      const auto &name = names[i]; const auto declaration = parameter_declaration(name);
      const auto value = parameter_draft_.override_value(name);
      const bool has_default = declaration.is_object() && declaration.contains("default");
      rows.push_back({name.empty() ? "\"\"" : text(name),
          value ? text(io::python_json_dumps(*value, false, true)) :
              has_default ? text(io::python_json_dumps(declaration.at("default"), false, true)) : std::string(),
          io::get_string(declaration, "type", "JSON"),
          std::string(ctx.tr(value ? "analysis_parameters.submitted" : has_default ? "analysis_parameters.default" : "analysis_parameters.absent"))});
      if (parameter_key_ && *parameter_key_ == name) { selected = int(i); }
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("analysis_graph.parameter")), 6}, {std::string(ctx.tr("analysis_graph.value")), 10},
        {std::string(ctx.tr("analysis_graph.type")), 5}, {std::string(ctx.tr("analysis_graph.origin")), 6}};
    spec.rows = int(rows.size()); spec.visible_rows = float(std::min(5, std::max(1, spec.rows)));
    spec.data_version = version;
    spec.cell = [rows](const int row, const int col) { return rows.at(size_t(row)).at(size_t(col)); };
    spec.selected = {[selected] { return selected; }, [this, valid, version, names](const int index) {
      if (!valid() || !parameter_current() || documents_->busy() || documents_->uncertain() ||
          parameter_text_active() || parameter_buffer_changed_ || parameter_draft_.version() != version ||
          index < 0 || size_t(index) >= names.size()) { return; }
      parameter_key_ = names[size_t(index)]; parameter_buffer_from_value(); redraw();
    }};
    panel->table("analysis_parameters", std::move(spec)).disable(blocked || parameter_buffer_changed_ || parameter_text_active());
    if (!parameter_key_) { return; }
    const auto key = *parameter_key_;
    panel->label(key.empty() ? "\"\"" : text(key));
    panel->paragraph(ctx.tr(parameter_literal() ? "analysis_parameters.literal_hint" : "analysis_parameters.json_hint"));
    auto &scope = panel->scope("parameter/" + std::to_string(generation) + "/" + std::to_string(selected));
    auto &input = scope.text_field("analysis_parameter_value", {[value = parameter_buffer_] { return value; },
        [this, valid, key](const std::string &value) {
      // Keep the typed buffer even if a project/bridge change detached this draft while typing.
      if (valid() && parameter_key_ && *parameter_key_ == key) {
        parameter_buffer_ = value; parameter_buffer_changed_ = value != parameter_original_; parameter_error_.clear(); redraw();
      }
    }}, {.max_length = AnalysisParameterDraft::max_text_bytes, .mono = true});
    parameter_input_id_ = input.id; input.disable(blocked);
    auto &values = panel->row();
    values.button("analysis_parameter_apply", ctx.tr("analysis_parameters.apply_value"), [this, valid, key] {
      if (!valid() || !parameter_current() || documents_->busy() || documents_->uncertain() || parameter_text_active() ||
          !parameter_key_ || *parameter_key_ != key) { return; }
      const auto result = parameter_draft_.set_text(key, parameter_buffer_, parameter_literal() ?
          AnalysisParameterDraft::TextMode::LiteralString : AnalysisParameterDraft::TextMode::Json, parameter_draft_.generation());
      if (result.accepted) { parameter_buffer_from_value(); }
      else { parameter_error_ = result.error; parameter_buffer_changed_ = true; }
      redraw();
    }).disable(blocked || parameter_text_active());
    values.button("analysis_parameter_null", ctx.tr("analysis_parameters.set_null"), [this, valid, key] {
      if (!valid() || !parameter_current() || documents_->busy() || documents_->uncertain() || parameter_text_active() ||
          parameter_buffer_changed_ || !parameter_key_ || *parameter_key_ != key) { return; }
      const auto result = parameter_draft_.set(key, nullptr, parameter_draft_.generation());
      if (result.accepted) { parameter_buffer_from_value(); } else { parameter_error_ = result.error; }
      redraw();
    }).disable(blocked || parameter_text_active() || parameter_buffer_changed_);
    panel->button("analysis_parameter_remove", ctx.tr("analysis_parameters.remove"), [this, valid, key] {
      if (!valid() || !parameter_current() || documents_->busy() || documents_->uncertain() || parameter_text_active() ||
          parameter_buffer_changed_ || !parameter_key_ || *parameter_key_ != key) { return; }
      const auto result = parameter_draft_.remove(key, parameter_draft_.generation());
      if (result.accepted) { parameter_buffer_from_value(); } else { parameter_error_ = result.error; }
      redraw();
    }).disable(blocked || parameter_text_active() || parameter_buffer_changed_ || !parameter_draft_.has_override(key));
  }
  void place_canvas(const double width, const double height)
  {
    if (!fit_ && !focus_selected_) { return; }
    if (!canvas_.fit(width, height, ui_scale_)) { return; }
    fit_ = false;
    if (focus_selected_ && selected_ && canvas_view_ && *selected_ < canvas_view_->nodes.size()) {
      canvas_.zoom_at(1.0 / canvas_.zoom(), width / 2, height / 2);
      const auto &rect = canvas_view_->nodes[*selected_].rect;
      const auto center = canvas_.to_screen({rect.x + rect.width / 2, rect.y + rect.height / 2});
      canvas_.pan(width / 2 - center.x, height / 2 - center.y);
    }
    focus_selected_ = false;
  }
  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store;
    parameter_ui_ = ctx.ui;
    if (!state_) {
      state_ = std::make_unique<AnalysisGraphState>(ctx.store.viewer());
      state_->show_displayed(initial_displayed_);
      if (initial_saved_) { state_->show_saved(); }
      if (initial_run_) { state_->show_run(); }
      documents_ = std::make_unique<ProjectAnalyses>(ctx.store);
      runs_ = std::make_unique<ProjectAnalysisRuns>(ctx.store);
    }
    documents_->sync();
    if (document_epoch_ != documents_->epoch()) {
      if (parameter_edits()) {
        if (parameter_text_active() && parameter_ui_->edit_state()) {
          parameter_buffer_ = parameter_ui_->edit_state()->text(); parameter_buffer_changed_ = true;
        }
        parameter_detached_ = true; parameter_saving_ = false;
      }
      else { clear_parameter_draft(); }
      document_epoch_ = documents_->epoch(); document_name_.clear();
      state_->clear_document();
    }
    if (document_version_ != documents_->selected_version()) {
      document_version_ = documents_->selected_version();
      const auto &selected = documents_->selected();
      if (!selected.is_null()) {
        bool preserve_name = false;
        if (selected.at("state") == "readable") {
          const bool recovered = parameter_saving_ && !parameter_detached_ && parameter_epoch_ == documents_->epoch() &&
              parameter_draft_.generation() == parameter_save_generation_ && parameter_draft_.version() == parameter_save_version_ &&
              parameter_draft_.matches(io::get_string(selected, "id"), io::get_string(selected, "name"), selected.at("document"));
          preserve_name = recovered && document_name_ != parameter_draft_.name();
          if (!parameter_edits() || recovered) { pin_parameters(); }
          else if (parameter_draft_.pinned()) { parameter_detached_ = true; parameter_saving_ = false; }
        }
        if (!preserve_name) { document_name_ = io::get_string(selected, "name"); }
        const bool activate = document_navigation_ == navigation_generation_;
        state_->clear_document();
        if (activate) { state_->show_saved(); }
        if (selected.at("state") == "readable") {
          state_->open_document(documents_->handle(), io::get_string(selected, "id"),
              documents_->selected_revision(), selected.at("document"), activate);
        }
      }
    }
    if (parameter_saving_ && !documents_->busy() && !documents_->uncertain() && !documents_->error().empty()) {
      parameter_saving_ = false;
    }
    state_->sync();
    state_->ensure_catalog();
    runs_->sync();
    if (runs_epoch_ != runs_->epoch()) {
      runs_epoch_ = runs_->epoch(); snapshot_index_ = file_index_ = output_index_ = mapping_index_ = -1;
      bindings_ = Json::object(); binding_name_ = "data"; binding_path_.clear(); binding_error_.clear();
      ++bindings_generation_;
    }
    if (run_selection_ != runs_->selection_generation()) {
      run_selection_ = runs_->selection_generation(); output_index_ = -1;
    }
    if (canvas_view_ != state_->view()) {
      canvas_view_ = state_->view();
      canvas_.set_view(canvas_view_);
      selected_ = canvas_view_ && !canvas_view_->nodes.empty() ? std::optional<size_t>(0) : std::nullopt;
      selected_parameter_ = 0; fit_ = true; focus_selected_ = false; dragging_ = false;
    }
  }

  bool result_corresponds() const
  {
    if (!state_->inspection()) { return false; }
    const auto &inspection = *state_->inspection();
    if (!inspection.shown_graph_verified.value_or(false)) { return false; }
    return state_->displayed() ? bool(inspection.shown_configuration) : inspection.shown_matches_desired.value_or(false);
  }

  void poll_runs(EditorContext &ctx)
  {
    const double now = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    const double wake = runs_->pump(now);
    auto *manager = ctx.area.shell().window_manager();
    if (!manager || !std::isfinite(wake) ||
        (runs_->wake_scheduled > now && runs_->wake_scheduled <= wake + 1e-4)) { return; }
    runs_->wake_scheduled = wake;
    const auto delay = uint64_t(std::clamp((wake - now) * 1000.0 + 1.0, 1.0, 60000.0));
    const std::weak_ptr<bool> weak = alive_;
    manager->add_timer(delay, 0, [this, weak] {
      const auto live = weak.lock(); if (live && *live) { redraw(); }
    });
  }

  void runs_panel(ui::Layout &layout, EditorContext &ctx)
  {
    poll_runs(ctx);
    if (!runs_->supported()) {
      layout.paragraph(ctx.tr(ctx.store.project().project() && ctx.store.project().project()->format_version < 9 ?
          "analysis_runs.upgrade" : "analysis_runs.unavailable"));
      return;
    }
    layout.paragraph(ctx.tr("analysis_runs.canvas_hint"));
    if (parameter_edits()) { layout.paragraph(ctx.tr("analysis_parameters.run_guard")); }
    if (!state_->document_id().empty()) { layout.label(text(state_->document_id())); }
    const std::weak_ptr<bool> weak = alive_;
    const auto epoch = runs_->epoch();
    const auto valid = [this, weak, epoch] {
      const auto live = weak.lock();
      if (!live || !*live) { return false; }
      runs_->sync(); return runs_->epoch() == epoch;
    };
    const bool blocked = runs_->busy() || ctx.store.project().busy();
    if (!runs_->error().empty()) { layout.paragraph(text(runs_->error())); }
    if (runs_->uncertain()) {
      layout.paragraph(ctx.tr("analysis_runs.uncertain"));
      layout.label(text(runs_->pending_id()));
      layout.button("analysis_run_check", ctx.tr("analysis_runs.check"), [this, valid] {
        if (valid()) { runs_->check_pending(); }
      }).disable(blocked);
    }
    if (auto *prepare = layout.panel("analysis_run_prepare_panel", ctx.tr("analysis_runs.prepare_title"), runs_->run().is_null())) {
      binding_controls(*prepare, ctx, valid, blocked);
      const auto generation = state_->generation(), bindings_generation = bindings_generation_;
      const auto id = state_->document_id(), snapshot = selected_snapshot_id();
      const auto revision = state_->document_revision();
      const auto bindings = bindings_;
      prepare->paragraph(ctx.tr("analysis_runs.prepare_hint"));
      if (id.empty()) { prepare->paragraph(ctx.tr("analysis_runs.select_definition")); }
      else {
        prepare->label(text(id));
        prepare->label(ctx.store.catalog().format("analysis_documents.revision", {{"revision", std::to_string(revision)}}));
        if (state_->document_stale()) { prepare->paragraph(ctx.tr("analysis_runs.stale_definition")); }
      }
      prepare->button("analysis_run_prepare", ctx.tr("analysis_runs.prepare"),
          [this, valid, generation, bindings_generation, id, revision, snapshot, bindings] {
        if (!valid() || parameter_edits()) { return; }
        state_->sync();
        if (state_->saved() && state_->generation() == generation && bindings_generation_ == bindings_generation &&
            state_->document_id() == id && !state_->document_stale()) {
          runs_->prepare(id, revision, snapshot, bindings);
        }
      }).disable(blocked || parameter_edits() || runs_->uncertain() || id.empty() || state_->document_stale() || snapshot.empty() || bindings.empty());
    }
    if (auto *history = layout.panel("analysis_run_history", ctx.tr("analysis_runs.history"), runs_->run().is_null())) {
      history->button("analysis_run_list", ctx.tr("analysis_runs.refresh"), [this, valid] {
        if (valid()) { runs_->load_page(runs_->offset()); }
      }).disable(blocked);
      if (!runs_->page().is_null()) {
        const auto rows = runs_->page().at("runs");
        if (rows.empty()) { history->paragraph(ctx.tr("analysis_runs.empty")); }
        else {
          ui::TableSpec spec;
          spec.columns = {{std::string(ctx.tr("analysis_documents.name")), 9},
              {std::string(ctx.tr("analysis_documents.state")), 7}, {"ID", 10}};
          spec.rows = int(rows.size()); spec.visible_rows = float(std::min(4, spec.rows));
          spec.data_version = runs_->version();
          Rows cells; int selected = -1;
          for (size_t i = 0; i < rows.size(); ++i) {
            if (io::get_string(runs_->run(), "id") == io::get_string(rows[i], "id")) { selected = int(i); }
            cells.push_back({text(io::get_string(rows[i], "analysis_name")),
                std::string(ctx.tr("analysis_runs.status." + io::get_string(rows[i], "status"))),
                io::get_string(rows[i], "id").substr(0, 8)});
          }
          spec.cell = [cells](const int row, const int column) { return cells.at(size_t(row)).at(size_t(column)); };
          const auto offset = runs_->offset();
          spec.selected = {[selected] { return selected; }, [this, valid, rows, offset](const int row) {
            if (valid() && runs_->offset() == offset && row >= 0 && size_t(row) < rows.size()) {
              runs_->load(rows[size_t(row)].at("id").get<std::string>());
            }
          }};
          history->table("analysis_run_rows", std::move(spec)).disable(blocked);
        }
        auto &buttons = history->row();
        const auto offset = runs_->offset(), next = io::get_int(runs_->page(), "next_offset", -1);
        buttons.button("analysis_run_previous", ctx.tr("analysis_documents.previous"), [this, valid, offset] {
          if (valid()) { runs_->load_page(std::max<int64_t>(0, offset - 50)); }
        }).disable(blocked || offset == 0);
        buttons.button("analysis_run_next", ctx.tr("analysis_documents.next"), [this, valid, next] {
          if (valid()) { runs_->load_page(next); }
        }).disable(blocked || next < 0);
      }
    }
    run_controls(layout, ctx, valid, blocked);
  }

  std::string selected_snapshot_id() const
  {
    const auto &snapshots = runs_->snapshots();
    return snapshot_index_ >= 0 && size_t(snapshot_index_) < snapshots.size() ?
        io::get_string(snapshots[size_t(snapshot_index_)], "id") : std::string();
  }

  void binding_controls(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid, const bool blocked)
  {
    layout.paragraph(ctx.tr("analysis_runs.snapshot_hint"));
    layout.button("analysis_run_snapshots", ctx.tr("analysis_runs.load_snapshots"), [this, valid] {
      if (valid() && runs_->load_snapshots()) {
        // A refreshed list can have a different ordering; retain explicit mappings only by
        // forcing an explicit selection again, never reinterpret an old list index.
        snapshot_index_ = file_index_ = mapping_index_ = -1;
        bindings_ = Json::object(); binding_path_.clear(); ++bindings_generation_;
      }
    }).disable(blocked || !bindings_.empty());
    const auto snapshots = runs_->snapshots();
    std::vector<std::string> labels{std::string(ctx.tr("analysis_runs.choose_snapshot"))};
    for (const auto &snapshot : snapshots) {
      labels.push_back(io::get_string(snapshot, "id").substr(0, 8) + " · " +
          std::to_string(snapshot.at("manifest").at("files").size()) + " " + std::string(ctx.tr("analysis_runs.files")));
    }
    layout.dropdown("analysis_run_snapshot", std::move(labels), {[selected = snapshot_index_ + 1] { return selected; },
        [this, valid, snapshots](const int index) {
      if (!valid() || index < 0 || size_t(index) > snapshots.size() || !bindings_.empty()) { return; }
      snapshot_index_ = index - 1; file_index_ = mapping_index_ = -1;
      binding_path_.clear(); binding_error_.clear(); ++bindings_generation_;
    }}).disable(blocked || snapshots.empty() || !bindings_.empty());
    omitted(layout, ctx, runs_->omitted_snapshots());
    if (snapshot_index_ < 0 || size_t(snapshot_index_) >= snapshots.size()) { return; }
    const auto snapshot_id = selected_snapshot_id();
    const auto files = snapshots[size_t(snapshot_index_)].at("manifest").at("files");
    std::vector<std::string> names{std::string(ctx.tr("analysis_runs.choose_file"))};
    for (const auto &file : files) { names.push_back(text(io::get_string(file, "name"))); }
    layout.dropdown("analysis_run_file", std::move(names), {[selected = file_index_ + 1] { return selected; },
        [this, valid, files, snapshot_id](const int index) {
      if (!valid() || selected_snapshot_id() != snapshot_id || index < 0 || size_t(index) > files.size()) { return; }
      file_index_ = index - 1;
      binding_path_ = file_index_ >= 0 ? io::get_string(files[size_t(file_index_)], "name") : std::string();
    }}).disable(blocked);
    const auto draft_field = [this, valid, snapshot_id](std::string *value) {
      return ui::Binding<std::string>{[copy = *value] { return copy; }, [this, valid, snapshot_id, value](const std::string &input) {
        if (valid() && selected_snapshot_id() == snapshot_id) { *value = input; }
      }};
    };
    layout.prop(ctx.tr("analysis_runs.binding")).text_field("analysis_run_binding", draft_field(&binding_name_), {.max_length = 64}).disable(blocked);
    layout.prop(ctx.tr("analysis_runs.relative_path")).text_field("analysis_run_path", draft_field(&binding_path_), {.max_length = 1024}).disable(blocked);
    layout.button("analysis_run_add_file", ctx.tr("analysis_runs.add_file"), [this, valid, files, snapshot_id] {
      if (!valid() || selected_snapshot_id() != snapshot_id || file_index_ < 0 || size_t(file_index_) >= files.size()) { return; }
      size_t count = 0; for (const auto &binding : bindings_) { count += binding.size(); }
      if (binding_name_.empty() || binding_path_.empty() || count >= 100 ||
          (!bindings_.contains(binding_name_) && bindings_.size() >= 32) ||
          (bindings_.contains(binding_name_) && bindings_.at(binding_name_).contains(binding_path_))) {
        binding_error_ = std::string(store_->tr("analysis_runs.mapping_invalid")); redraw(); return;
      }
      bindings_[binding_name_][binding_path_] = files[size_t(file_index_)].at("record_id");
      binding_error_.clear(); ++bindings_generation_; redraw();
    }).disable(blocked || file_index_ < 0);
    if (!binding_error_.empty()) { layout.paragraph(binding_error_); }
    Rows rows; std::vector<std::pair<std::string, std::string>> keys;
    for (auto binding = bindings_.begin(); binding != bindings_.end(); ++binding) {
      for (auto file = binding.value().begin(); file != binding.value().end(); ++file) {
        rows.push_back({text(binding.key()), text(file.key()), file.value().get<std::string>().substr(0, 8)});
        keys.emplace_back(binding.key(), file.key());
      }
    }
    if (!rows.empty()) {
      ui::TableSpec spec;
      spec.columns = {{std::string(ctx.tr("analysis_runs.binding")), 5},
          {std::string(ctx.tr("analysis_runs.relative_path")), 10}, {"ID", 6}};
      spec.rows = int(rows.size()); spec.visible_rows = float(std::min(4, spec.rows)); spec.data_version = bindings_generation_;
      spec.cell = [rows](const int row, const int column) { return rows.at(size_t(row)).at(size_t(column)); };
      const auto generation = bindings_generation_;
      spec.selected = {[index = mapping_index_] { return index; }, [this, valid, generation](const int index) {
        if (valid() && bindings_generation_ == generation) { mapping_index_ = index; }
      }};
      layout.table("analysis_run_bindings", std::move(spec)).disable(blocked);
      auto &buttons = layout.row();
      buttons.button("analysis_run_remove_file", ctx.tr("analysis_runs.remove_file"), [this, valid, generation, keys] {
        if (!valid() || bindings_generation_ != generation || mapping_index_ < 0 || size_t(mapping_index_) >= keys.size()) { return; }
        const auto &[binding, path] = keys[size_t(mapping_index_)];
        bindings_[binding].erase(path); if (bindings_[binding].empty()) { bindings_.erase(binding); }
        mapping_index_ = -1; ++bindings_generation_; redraw();
      }).disable(blocked || mapping_index_ < 0 || size_t(mapping_index_) >= keys.size());
      buttons.button("analysis_run_clear_files", ctx.tr("analysis_runs.clear_files"), [this, valid] {
        if (valid()) { bindings_ = Json::object(); mapping_index_ = -1; ++bindings_generation_; redraw(); }
      }).disable(blocked);
    }
  }

  void run_controls(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid, const bool blocked)
  {
    const auto &run = runs_->run();
    if (run.is_null()) { return; }
    const auto id = io::get_string(run, "id"), status = io::get_string(run, "status");
    const auto selection = runs_->selection_generation();
    const auto same_run = [this, valid, id, selection] {
      return valid() && runs_->selection_generation() == selection && io::get_string(runs_->run(), "id") == id;
    };
    auto *shell = &ctx.area.shell();
    auto &box = layout.box();
    box.label(text(io::get_string(run, "analysis_name")));
    box.label(ctx.tr("analysis_runs.status." + status));
    box.paragraph(id);
    box.label(ctx.store.catalog().format("analysis_documents.revision", {{"revision", std::to_string(io::get_int(run, "source_revision", -1))}}));
    if (!run.at("error").is_null()) { box.paragraph(text(io::get_string(run.at("error"), "message"))); }
    const bool partial = !run.at("result").is_null() && run.at("result").at("has_errors").get<bool>();
    if (partial) { box.paragraph(ctx.tr("analysis_runs.partial")); }
    if (status == "unknown") { box.paragraph(ctx.tr("analysis_runs.unknown_hint")); }
    if (status == "running" || status == "cancel_requested") {
      box.paragraph(ctx.tr(runs_->following() ? "analysis_runs.following" : "analysis_runs.follow_stopped"));
    }
    const auto plan = io::get_string(run, "plan_sha256");
    const auto navigation = navigation_generation_;
    box.button("analysis_run_inspect", ctx.tr("analysis_runs.inspect"), [this, same_run, plan, shell, navigation] {
      if (!same_run() || runs_->busy() || store_->project().busy() || shell->text_input_active() ||
          navigation_generation_ != navigation || !state_->saved() || saved_section_ != 1 ||
          io::get_string(runs_->run(), "plan_sha256") != plan) { return; }
      if (state_->open_frozen_run(runs_->handle(), runs_->run())) { ++navigation_generation_; redraw(); }
    }).disable(blocked || shell->text_input_active());
    auto &actions = box.row();
    actions.button("analysis_run_start", ctx.tr("analysis_runs.start"), [this, same_run] {
      if (same_run()) { runs_->start(); }
    }).disable(blocked || runs_->uncertain() || status != "prepared");
    actions.button("analysis_run_cancel", ctx.tr("analysis_runs.cancel"), [this, same_run] {
      if (same_run()) { runs_->cancel(); }
    }).disable(blocked || runs_->uncertain() || (status != "prepared" && status != "running" && status != "cancel_requested"));
    box.button("analysis_run_refresh", ctx.tr("analysis_runs.refresh_selected"), [this, same_run, id] {
      if (same_run()) { runs_->load(id); }
    }).disable(blocked);
    box.button("analysis_run_recover", ctx.tr("analysis_runs.recover"), [this, same_run] {
      if (same_run()) { runs_->recover(); }
    }).disable(blocked || runs_->uncertain() || (status != "running" && status != "cancel_requested"))
      .tip(ctx.tr("analysis_runs.recover_hint"));
    if (auto *frozen = box.panel("analysis_run_frozen", ctx.tr("analysis_runs.frozen"), false)) {
      frozen->paragraph(io::get_string(run, "snapshot_id"));
      frozen->paragraph(io::get_string(run, "plan_sha256"));
      Rows rows;
      for (auto binding = run.at("bindings").begin(); binding != run.at("bindings").end(); ++binding) {
        for (auto file = binding.value().begin(); file != binding.value().end(); ++file) {
          rows.push_back({text(binding.key()), text(file.key()), io::get_string(file.value(), "sha256")});
        }
      }
      table(*frozen, "analysis_run_frozen_files", {{std::string(ctx.tr("analysis_runs.binding")), 5},
          {std::string(ctx.tr("analysis_runs.relative_path")), 10}, {"SHA-256", 12}}, std::move(rows), runs_->version());
      frozen->label(ctx.tr("analysis_graph.submitted"));
      Rows parameters;
      for (const auto &[name, value] : run.at("document").at("parameters").items()) {
        const char *type = value.is_null() ? "discussion.cells.null" : value.is_string() ? "project.type.text" :
            value.is_boolean() ? "project.type.boolean" : value.is_number_integer() ? "project.type.integer" :
            value.is_number() ? "project.type.number" : "project.type.json";
        parameters.push_back({text(name), std::string(ctx.tr(type)), summary(value)});
      }
      if (parameters.empty()) { frozen->paragraph("{}"); }
      else {
        table(*frozen, "analysis_run_frozen_parameters", {{std::string(ctx.tr("analysis_graph.parameter")), 8},
            {std::string(ctx.tr("analysis_graph.type")), 7}, {std::string(ctx.tr("analysis_graph.value")), 12}},
            std::move(parameters), runs_->version());
      }
      frozen->label(ctx.tr("analysis_graph.outputs"));
      Rows outputs;
      for (const auto &output : run.at("document").at("outputs")) { outputs.push_back({summary(output)}); }
      if (outputs.empty()) { frozen->paragraph("[]"); }
      else {
        table(*frozen, "analysis_run_frozen_outputs", {{std::string(ctx.tr("analysis_graph.output")), 12}},
            std::move(outputs), runs_->version(), 3);
      }
      frozen->paragraph(ctx.tr("analysis_runs.budget"));
    }
    box.button("analysis_run_read_result", ctx.tr("analysis_runs.read_result"), [this, same_run] {
      if (same_run() && runs_->read_result()) { output_index_ = -1; }
    }).disable(blocked || run.at("result").is_null());
    if (runs_->result().is_null()) { return; }
    const auto outputs = runs_->payload_outputs();
    if (outputs.empty()) { box.paragraph(ctx.tr("analysis_runs.no_payload")); return; }
    std::vector<std::string> choices{std::string(ctx.tr("analysis_runs.choose_output"))};
    choices.insert(choices.end(), outputs.begin(), outputs.end());
    box.dropdown("analysis_run_output", std::move(choices), {[selected = output_index_ + 1] { return selected; },
        [this, same_run, outputs](const int index) {
      if (same_run() && index >= 0 && size_t(index) <= outputs.size()) { output_index_ = index - 1; }
    }}).disable(blocked);
    auto *screen = ctx.area.screen();
    box.paragraph(ctx.tr("analysis_runs.viewer_hint"));
    box.button("analysis_run_show", ctx.tr("analysis_runs.show"), [this, same_run, shell, screen, outputs, id] {
      if (!same_run() || output_index_ < 0 || size_t(output_index_) >= outputs.size()) { return; }
      const auto target = shell->analysis_payload_target(screen);
      if (!target) { if (store_->toast) { store_->toast(target.error().message, ui::ToastKind::Warning); } return; }
      const auto output = outputs[size_t(output_index_)];
      const auto payload = runs_->decode_payload(output);
      if (!payload || !same_run()) { return; }
      const auto label = io::get_string(runs_->run(), "analysis_name") + " · " + id.substr(0, 8) + " / " + output;
      shell->open_analysis_payload(screen, runs_->handle(), target.value(), payload, label, same_run,
          [this, same_run](bridge::Result<Json> result) {
        if (same_run() && !result && store_->toast) { store_->toast(result.error().message, ui::ToastKind::Warning); }
      });
    }).disable(blocked || output_index_ < 0 || size_t(output_index_) >= outputs.size());
  }

  void documents_panel(ui::Layout &layout, EditorContext &ctx)
  {
    // Separate panel keys keep the Viewer modes compact while making the saved-document browser
    // immediately available when the user selects its tab.
    auto *panel = layout.panel(state_->saved() ? "graph_saved_documents" : "graph_documents",
        ctx.tr("analysis_documents.title"), state_->saved());
    if (!panel) { return; }
    if (!documents_->supported()) {
      panel->paragraph(ctx.tr("analysis_documents.open_project"));
      return;
    }
    const std::weak_ptr<bool> weak = alive_;
    const auto epoch = documents_->epoch();
    const auto selection_version = documents_->selected_version();
    const auto valid = [this, weak, epoch] {
      const auto live = weak.lock();
      if (!live || !*live) { return false; }
      documents_->sync();
      return documents_->epoch() == epoch;
    };
    const bool blocked = documents_->busy() || ctx.store.project().busy();
    if (!documents_->error().empty()) { panel->paragraph(text(documents_->error())); }
    if (!documents_->notice().empty()) { panel->paragraph(ctx.tr(documents_->notice())); }
    if (documents_->uncertain()) {
      panel->paragraph(ctx.tr("analysis_documents.uncertain"));
      panel->label(text(documents_->pending_id()));
      panel->button("analysis_check_save", ctx.tr("analysis_documents.check_save"), [this, valid] {
        if (valid() && documents_->check_pending()) { document_navigation_ = navigation_generation_; }
      }).disable(blocked);
    }
    panel->prop(ctx.tr("analysis_documents.name")).text_field(
        "analysis_name/" + std::to_string(epoch) + "/" + std::to_string(selection_version),
        {[name = document_name_] { return name; }, [this, valid, selection_version](const std::string &value) {
          if (valid() && documents_->selected_version() == selection_version) { document_name_ = value; }
        }}, {.max_length = 256}).disable(blocked || parameter_edits());
    const auto generation = state_->generation();
    const auto *definition = state_->definition();
    const Json candidate = definition ? Json{{"format", "stk.analysis-document/1"}, {"graph", definition->graph},
        {"parameters", definition->parameters}, {"outputs", definition->requested_outputs}} : Json();
    panel->button("analysis_save", ctx.tr("analysis_documents.save_new"), [this, valid, generation, candidate] {
      if (!valid() || parameter_edits()) { return; }
      state_->sync();
      if (state_->generation() == generation && !candidate.is_null() && documents_->save_new(document_name_, candidate)) {
        document_navigation_ = navigation_generation_;
      }
    }).disable(blocked || parameter_edits() || documents_->uncertain() || candidate.is_null());
    if (!documents_->selected().is_null() && state_->saved()) {
      const auto selected_id = io::get_string(documents_->selected(), "id");
      panel->button("analysis_reload", ctx.tr("analysis_documents.reload"), [this, valid, selected_id] {
        if (valid() && !parameter_edits() && io::get_string(documents_->selected(), "id") == selected_id && documents_->load(selected_id)) {
          document_navigation_ = navigation_generation_;
        }
      }).disable(blocked || parameter_edits());
      panel->button("analysis_rename", ctx.tr("analysis_documents.rename"), [this, valid, selection_version] {
        if (valid() && !parameter_edits() && documents_->selected_version() == selection_version && documents_->rename(document_name_)) {
          document_navigation_ = navigation_generation_;
        }
      }).disable(blocked || parameter_edits() || documents_->uncertain() || documents_->stale() ||
          io::get_string(documents_->selected(), "state") != "readable");
      if (!io::get_string(documents_->selected(), "error").empty()) {
        panel->paragraph(text(io::get_string(documents_->selected(), "error")));
      }
    }
    panel->paragraph(ctx.tr("analysis_documents.save_hint"));
    const auto offset = documents_->page().is_null() ? 0 : io::get_int(documents_->page(), "offset", 0);
    panel->button("analysis_list", ctx.tr("analysis_documents.refresh"), [this, valid, offset] {
      if (valid()) { documents_->load_page(offset); }
    }).disable(blocked);
    const auto page = documents_->page();
    if (page.is_null()) { return; }
    if (!io::get_string(page, "error").empty()) { panel->paragraph(text(io::get_string(page, "error"))); }
    if (documents_->page_stale()) { panel->paragraph(ctx.tr("analysis_documents.list_stale")); }
    const auto rows = page.at("analyses");
    if (rows.empty()) { panel->paragraph(ctx.tr("analysis_documents.empty")); }
    else {
      ui::TableSpec spec;
      spec.columns = {{std::string(ctx.tr("analysis_documents.name")), 10},
          {std::string(ctx.tr("analysis_documents.state")), 7}, {"ID", 18}};
      spec.rows = int(rows.size()); spec.visible_rows = float(std::min(5, spec.rows));
      spec.data_version = documents_->version();
      Rows cells;
      int selected_row = -1;
      for (size_t i = 0; i < rows.size(); ++i) {
        const auto &item = rows[i];
        if (io::get_string(documents_->selected(), "id") == io::get_string(item, "id")) { selected_row = int(i); }
        cells.push_back({text(io::get_string(item, "name")), std::string(ctx.tr("analysis_documents.state." + io::get_string(item, "state"))),
            text(io::get_string(item, "id"))});
      }
      spec.cell = [cells](const int row, const int column) { return cells.at(size_t(row)).at(size_t(column)); };
      const auto revision = io::get_int(page, "revision", -1);
      spec.selected = {[selected_row] { return selected_row; }, [this, valid, rows, revision, offset](const int row) {
        if (valid() && !parameter_edits() && row >= 0 && size_t(row) < rows.size() &&
            io::get_int(documents_->page(), "revision", -1) == revision &&
            io::get_int(documents_->page(), "offset", -1) == offset && documents_->load(io::get_string(rows[size_t(row)], "id"))) {
          document_navigation_ = navigation_generation_;
        }
      }};
      panel->table("analysis_documents", std::move(spec)).disable(blocked || parameter_edits());
    }
    auto &buttons = panel->row();
    buttons.button("analysis_previous", ctx.tr("analysis_documents.previous"), [this, valid, offset] {
      if (valid()) { documents_->load_page(std::max<int64_t>(0, offset - 50)); }
    }).disable(blocked || offset == 0);
    const auto next = offset + int64_t(rows.size());
    buttons.button("analysis_next", ctx.tr("analysis_documents.next"), [this, valid, next] {
      if (valid()) { documents_->load_page(next); }
    }).disable(blocked || next >= io::get_int(page, "total", 0));
  }

  void source_panel(ui::Layout &layout, EditorContext &ctx)
  {
    if (state_->source() == AnalysisGraphState::Source::Run) {
      auto *panel = layout.panel("graph_run_source", ctx.tr("analysis_runs.frozen"), true);
      if (!panel) { return; }
      panel->paragraph(ctx.tr("analysis_runs.frozen_definition"));
      const auto *run = state_->frozen_run();
      if (!run) { panel->paragraph(ctx.tr("analysis_runs.no_frozen_graph")); return; }
      Rows provenance{
          {std::string(ctx.tr("analysis_runs.run_id")), run->id},
          {std::string(ctx.tr("analysis_documents.name")), text(run->analysis_name)},
          {std::string(ctx.tr("analysis_runs.analysis_id")), run->analysis_id},
          {std::string(ctx.tr("analysis_runs.source_revision")), std::to_string(run->source_revision)},
          {std::string(ctx.tr("jobs.info.created")), run->created_at},
          {std::string(ctx.tr("analysis_runs.snapshot_id")), run->snapshot_id},
          {std::string(ctx.tr("analysis_runs.snapshot_hash")), run->snapshot_sha256},
          {std::string(ctx.tr("analysis_runs.plan_hash")), run->plan_sha256}};
      table(*panel, "graph_run_provenance", {{std::string(ctx.tr("analysis_graph.parameter")), 9},
          {std::string(ctx.tr("analysis_graph.value")), 22}}, std::move(provenance), state_->generation(), 4);
      Rows files;
      for (const auto &[binding, entries] : run->bindings.items()) {
        for (const auto &[path, file] : entries.items()) {
          files.push_back({text(binding), text(path), io::get_string(file, "sha256")});
        }
      }
      table(*panel, "graph_run_files", {{std::string(ctx.tr("analysis_runs.binding")), 5},
          {std::string(ctx.tr("analysis_runs.relative_path")), 9}, {"SHA-256", 16}}, std::move(files), state_->generation(), 3);
      panel->paragraph(ctx.tr("analysis_documents.catalog_defaults"));
      return;
    }
    auto *panel = layout.panel("graph_source", ctx.tr("analysis_graph.source"), true);
    if (!panel) { return; }
    if (state_->saved()) {
      panel->paragraph(ctx.tr("analysis_documents.definition_only"));
      if (!state_->document_id().empty()) {
        panel->label(text(state_->document_id()));
        panel->label(ctx.store.catalog().format("analysis_documents.revision", {{"revision", std::to_string(state_->document_revision())}}));
        if (state_->document_stale()) { panel->paragraph(ctx.tr("analysis_documents.stale")); }
      }
      panel->paragraph(ctx.tr("analysis_documents.catalog_defaults"));
      return;
    }
    const auto &inspection = *state_->inspection();
    if (const auto *config = state_->configuration()) {
      panel->paragraph(text(config->source.label()));
      panel->label(text(config->preset_id)).tip(text(config->source.path));
    }
    else { panel->paragraph(ctx.tr("analysis_graph.unavailable")); }
    if (inspection.shown_configuration && !inspection.shown_graph_verified.value_or(false)) {
      panel->paragraph(ctx.tr(inspection.shown_graph_verified ? "analysis_graph.graph_mismatch" : "analysis_graph.graph_unverified"));
    }
    panel->paragraph(ctx.tr(inspection.shown_matches_desired ?
        (*inspection.shown_matches_desired ? "analysis_graph.same_configuration" : "analysis_graph.different_configuration") :
        "analysis_graph.no_comparison"));
    if (inspection.evaluating) { panel->label(ctx.tr("analysis_graph.evaluating")); }
    if (!inspection.pending_edit.empty()) { panel->label(ctx.tr("analysis_graph.pending")); }
    if (!inspection.error.empty()) { panel->paragraph(text(inspection.error)); }
    if (inspection.shown_evaluation) {
      panel->label(text(inspection.shown_evaluation->eval_id)).tip(ctx.tr("analysis_graph.receipt"));
      if (inspection.shown_evaluation->from_cache) { panel->paragraph(ctx.tr("analysis_graph.from_cache")); }
    }
    panel->paragraph(ctx.tr("analysis_graph.freshness"));
  }

  void node_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("graph_node", ctx.tr("analysis_graph.node"), true);
    if (!panel) { return; }
    const auto view = state_->view();
    std::vector<std::string> labels;
    for (const auto &node : view->nodes) { labels.push_back(text(node.id) + " / " + node.label); }
    const int selected = selected_ ? int(*selected_) : -1;
    const std::weak_ptr<bool> weak = alive_;
    panel->dropdown("graph_node_select", std::move(labels), {[selected] { return selected; },
        [this, weak, view](const int value) {
          if (const auto live = weak.lock(); live && *live && view == state_->view() && value >= 0 && size_t(value) < view->nodes.size()) {
            selected_ = size_t(value); selected_parameter_ = 0; focus_selected_ = true; redraw();
          }
        }});
    if (!selected_ || *selected_ >= view->nodes.size()) { return; }
    const auto &node = view->nodes[*selected_];
    panel->paragraph(text(node.type));
    panel->label(text(node.stage));
    if (!node.known_type) { panel->paragraph(ctx.tr("analysis_graph.unknown_type")); }
    if (node.cyclic) { panel->paragraph(ctx.tr("analysis_graph.cycle")); }
    if (node.ambiguous_id) { panel->paragraph(ctx.tr("analysis_graph.duplicate_id")); }
    const auto *inspection = state_->inspection().get();
    if (result_corresponds() && inspection && inspection->shown_result && inspection->shown_result->was_evaluated(node.id)) {
      panel->paragraph(ctx.tr("analysis_graph.executed_receipt"));
    }
    Rows ports;
    for (const auto &port : node.inputs) {
      ports.push_back({std::string(ctx.tr("analysis_graph.input")), text(port.name), port.type_text,
          std::string(ctx.tr(port.multi ? "analysis_graph.multi" : port.required ? "analysis_graph.required" : "analysis_graph.optional"))});
    }
    for (const auto &port : node.outputs) {
      ports.push_back({std::string(ctx.tr("analysis_graph.output")), text(port.name), port.type_text, ""});
    }
    table(*panel, "graph_ports", {{std::string(ctx.tr("analysis_graph.direction")), 4},
          {std::string(ctx.tr("analysis_graph.port")), 6}, {std::string(ctx.tr("analysis_graph.type")), 12},
          {std::string(ctx.tr("analysis_graph.cardinality")), 5}}, std::move(ports), state_->generation() * 201 + *selected_, 5);
    omitted(*panel, ctx, node.omitted_inputs + node.omitted_outputs);
    Rows links;
    size_t link_count = 0;
    for (const auto &edge : view->edges) {
      if (edge.source != int(*selected_) && edge.target != int(*selected_)) { continue; }
      ++link_count;
      if (links.size() == 128) { continue; }
      links.push_back({text(edge.source_node + "." + edge.source_port), text(edge.target_node + "." + edge.target_port),
          std::to_string(edge.link_index + 1), text(edge.alias), edge.diagnostic});
    }
    if (!links.empty()) {
      table(*panel, "graph_links", {{std::string(ctx.tr("analysis_graph.from")), 9}, {std::string(ctx.tr("analysis_graph.to")), 9},
          {"#", 2}, {std::string(ctx.tr("analysis_graph.alias")), 6}, {std::string(ctx.tr("analysis_graph.issue")), 9}},
          std::move(links), state_->generation() * 201 + *selected_, 4);
    }
    if (link_count > 128) { omitted(*panel, ctx, link_count - 128); }
    if (node.parameters.empty()) { return; }
    ui::TableSpec parameters;
    parameters.columns = {{std::string(ctx.tr("analysis_graph.parameter")), 7}, {std::string(ctx.tr("analysis_graph.value")), 12},
        {std::string(ctx.tr("analysis_graph.origin")), 6}};
    parameters.rows = int(node.parameters.size()); parameters.visible_rows = float(std::min(5, parameters.rows));
    parameters.data_version = state_->generation() * 201 + *selected_;
    const auto node_index = *selected_;
    parameters.selected = {[selected = selected_parameter_] { return selected; },
        [this, weak, view, node_index](const int value) {
          if (const auto live = weak.lock(); live && *live && view == state_->view() && selected_ == node_index &&
              value >= 0 && size_t(value) < view->nodes[node_index].parameters.size()) { selected_parameter_ = value; redraw(); }
        }};
    std::vector<std::string> origins;
    for (const auto &parameter : node.parameters) { origins.push_back(std::string(ctx.tr("analysis_graph.origin." + parameter.origin))); }
    parameters.cell = [view, node_index, origins](const int row, const int col) {
      const auto &param = view->nodes[node_index].parameters[size_t(row)];
      return col == 0 ? text(param.name) : col == 1 ? param.value_text : origins[size_t(row)];
    };
    panel->table("graph_node_parameters", std::move(parameters));
    omitted(*panel, ctx, node.omitted_parameters);
    if (selected_parameter_ < 0 || size_t(selected_parameter_) >= node.parameters.size()) { return; }
    const auto &parameter = node.parameters[size_t(selected_parameter_)];
    panel->paragraph(text(parameter.name) + " = " + parameter.value_text);
    if (!parameter.unit.empty()) { panel->label(text(parameter.unit)); }
    if (!parameter.references_complete) { panel->paragraph(ctx.tr("analysis_graph.references_incomplete")); }
    for (const auto &reference : parameter.references) {
      panel->paragraph("$" + text(reference.parameter) + "  " + text(reference.path));
      const auto *configuration = state_->definition();
      if (configuration && configuration->parameters.contains(reference.parameter)) {
        panel->paragraph(std::string(ctx.tr("analysis_graph.submitted")) + ": " + summary(configuration->parameters.at(reference.parameter)));
      }
      if (reference.has_default) {
        panel->paragraph(std::string(ctx.tr("analysis_graph.declared_default")) + ": " + reference.default_text);
      }
    }
  }

  void parameters_panel(ui::Layout &layout, EditorContext &ctx)
  {
    const bool frozen = state_->source() == AnalysisGraphState::Source::Run;
    auto *panel = layout.panel("graph_parameters", ctx.tr("analysis_graph.graph_parameters"), frozen);
    if (!panel || !state_->definition()) { return; }
    Rows rows;
    const auto &parameters = state_->definition()->parameters;
    if (parameters.is_object()) {
      for (auto it = parameters.begin(); it != parameters.end() && rows.size() < 64; ++it) {
        std::string resolved;
        if (result_corresponds() && state_->inspection()) {
          const auto &values = state_->inspection()->shown_resolved_parameters;
          if (values.is_object() && values.contains(it.key())) { resolved = summary(values.at(it.key())); }
        }
        if (frozen) {
          const auto &value = it.value();
          const char *type = value.is_null() ? "discussion.cells.null" : value.is_string() ? "project.type.text" :
              value.is_boolean() ? "project.type.boolean" : value.is_number_integer() ? "project.type.integer" :
              value.is_number() ? "project.type.number" : "project.type.json";
          rows.push_back({it.key().empty() ? "\"\"" : text(it.key()), text(io::python_json_dumps(value, false, true)),
              std::string(ctx.tr(type))});
        }
        else { rows.push_back({text(it.key()), summary(it.value()), resolved}); }
      }
    }
    table(*panel, "graph_parameter_values", {{std::string(ctx.tr("analysis_graph.parameter")), frozen ? 6.0f : 8.0f},
        {std::string(ctx.tr("analysis_graph.submitted")), 10},
        {std::string(ctx.tr(frozen ? "analysis_graph.type" : "analysis_graph.resolved")), frozen ? 5.0f : 10.0f}},
        std::move(rows), state_->generation());
    if (parameters.size() > 64) { omitted(*panel, ctx, parameters.size() - 64); }
  }

  void outputs_panel(ui::Layout &layout, EditorContext &ctx)
  {
    const bool frozen = state_->source() == AnalysisGraphState::Source::Run;
    auto *panel = layout.panel("graph_outputs", ctx.tr("analysis_graph.outputs"), frozen);
    if (!panel || !state_->definition()) { return; }
    Rows rows;
    const auto &config = *state_->definition();
    const auto *inspection = state_->inspection().get();
    const auto *result = inspection && inspection->shown_result ? &*inspection->shown_result : nullptr;
    for (const auto &output : state_->view()->outputs) {
      const bool requested = std::find(config.requested_outputs.begin(), config.requested_outputs.end(), output.name) != config.requested_outputs.end();
      std::string available = std::string(ctx.tr("analysis_graph.no_result"));
      if (result_corresponds() && result) {
        if (const auto *value = result->output(output.name)) { available = text(value->type); }
      }
      const auto request = std::string(ctx.tr(requested ? "analysis_graph.requested" : "analysis_graph.not_requested"));
      const auto endpoint = text(output.node + "." + output.port);
      rows.push_back({text(output.name), frozen ? request : endpoint, frozen ? endpoint : request});
      if (!frozen) { rows.back().push_back(available); }
    }
    std::vector<ui::TableColumn> columns{{std::string(ctx.tr("analysis_graph.output")), 6},
        {std::string(ctx.tr(frozen ? "analysis_graph.request" : "analysis_graph.port")), frozen ? 9.0f : 10.0f},
        {std::string(ctx.tr(frozen ? "analysis_graph.port" : "analysis_graph.request")), frozen ? 10.0f : 9.0f}};
    if (!frozen) { columns.push_back({std::string(ctx.tr("analysis_graph.result")), 7}); }
    table(*panel, "graph_output_rows", std::move(columns), std::move(rows), state_->generation());
    omitted(*panel, ctx, state_->view()->omitted_outputs);
    panel->paragraph(ctx.tr(frozen ? "analysis_runs.result_not_inspected" : "analysis_graph.no_fetch"));
  }

  void validation_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("graph_validation", ctx.tr("analysis_graph.validation"), true);
    if (!panel) { return; }
    const std::weak_ptr<bool> weak = alive_;
    const auto generation = state_->generation();
    panel->button("graph_validate", ctx.tr(state_->validating() ? "analysis_graph.validating" : "analysis_graph.validate"), [this, weak, generation] {
      if (const auto live = weak.lock(); live && *live) {
        state_->sync();
        if (generation == state_->generation()) { state_->validate(); }
      }
    }).disable(state_->validating() || !state_->validation_available());
    if (!state_->validation_error().empty()) { panel->paragraph(text(state_->validation_error())); }
    const auto &response = state_->validation();
    if (!response.is_null()) {
      panel->paragraph(ctx.tr(response.at("ok").get<bool>() ? "analysis_graph.valid" : "analysis_graph.invalid"));
      Rows issues;
      const auto &reported = response.at("issues");
      for (size_t index = 0; index < std::min<size_t>(reported.size(), 256); ++index) {
        const auto &issue = reported[index];
        if (!issue.is_object()) { continue; }
        issues.push_back({text(io::get_string(issue, "node")), text(io::get_string(issue, "code")),
            text(io::get_string(issue, "path")), text(io::get_string(issue, "message"))});
      }
      if (!issues.empty()) {
        table(*panel, "graph_validation_issues", {{std::string(ctx.tr("analysis_graph.node")), 6},
            {std::string(ctx.tr("analysis_graph.issue")), 8}, {std::string(ctx.tr("analysis_graph.path")), 12},
            {std::string(ctx.tr("analysis_graph.message")), 20}}, std::move(issues), state_->generation());
      }
      if (response.at("issues").size() > 256) { omitted(*panel, ctx, response.at("issues").size() - 256); }
    }
    else if (!state_->validating()) { panel->paragraph(ctx.tr("analysis_graph.not_validated")); }
    const auto &view = *state_->view();
    if (!view.issues.empty()) {
      panel->label(ctx.tr("analysis_graph.presentation_issues"));
      Rows issues;
      for (const auto &issue : view.issues) { issues.push_back({text(issue.node), text(issue.code), text(issue.path), text(issue.message)}); }
      table(*panel, "graph_presentation_issues", {{std::string(ctx.tr("analysis_graph.node")), 6},
          {std::string(ctx.tr("analysis_graph.issue")), 9}, {std::string(ctx.tr("analysis_graph.path")), 12},
          {std::string(ctx.tr("analysis_graph.message")), 20}}, std::move(issues), state_->generation(), 3);
    }
    omitted(*panel, ctx, view.omitted_edges + view.omitted_issues);
  }
};
}  // namespace

std::unique_ptr<Editor> make_analysis_graph_editor(const EditorType &type)
{
  return std::make_unique<AnalysisGraphEditor>(type);
}

}  // namespace stk::app
