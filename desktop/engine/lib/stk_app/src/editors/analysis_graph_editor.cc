/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/analysis_parameter_draft.hh"
#include "stk/app/analysis_table_grid.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/project_analyses.hh"
#include "stk/app/project_analysis_runs.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/ui/gpu_painter.hh"
#include "stk/wm/window.hh"
#include "project_navigation.hh"
#include "editor_text.hh"

#include <algorithm>
#include <charconv>
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

std::string bridge_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
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
  bool show_view(const std::string_view view) override
  {
    if (view != "saved" && view != "runs") { return false; }
    ++navigation_generation_;
    initial_saved_ = true; initial_run_ = false; initial_displayed_ = false;
    saved_section_ = view == "runs" ? 1 : 0;
    if (state_) { state_->show_saved(); redraw(); }
    return true;
  }
  ~AnalysisGraphEditor() override { *alive_ = false; }
  bool draws_gpu() const override { return true; }
  bool has_sidebar() const override { return true; }
  ui::Color main_background(const ui::Theme &) const override { return {0, 0, 0, 0}; }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx);
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
  AnalysisCandidateValidation candidate_check_;
  std::optional<bridge::Future<Json>> candidate_future_;
  std::string link_error_;
  std::optional<std::string> parameter_key_;
  std::optional<std::string> draft_output_key_;
  size_t draft_output_page_ = 0;
  uint64_t draft_output_page_generation_ = 0;
  std::string parameter_buffer_, parameter_original_, parameter_error_;
  bool parameter_buffer_changed_ = false, parameter_detached_ = false, parameter_saving_ = false;
  uint64_t parameter_epoch_ = 0, parameter_selection_ = 0, parameter_save_generation_ = 0, parameter_save_version_ = 0;
  ui::Context *parameter_ui_ = nullptr;
  ui::WidgetId parameter_input_id_ = 0;
  int saved_section_ = 0, snapshot_index_ = -1, file_index_ = -1, output_index_ = -1, mapping_index_ = -1;
  uint64_t runs_epoch_ = 0, run_selection_ = 0, bindings_generation_ = 0;
  uint64_t binding_name_generation_ = 0, binding_path_generation_ = 0;
  std::string binding_name_ = "data", binding_path_, binding_error_;
  Json bindings_ = Json::object();
  std::optional<AnalysisReusedInputs> reused_inputs_;
  struct InputReusePending {
    uint64_t expected_generation;
    std::function<bool()> valid;
  };
  std::optional<InputReusePending> input_reuse_pending_;
  std::string input_reuse_notice_;
  /* "Run and show": one explicit click walks prepare -> start -> wait -> read the result -> show
   * the first payload output, making the same calls as the separate buttons, each bound to the
   * run this click created. A changed project, bridge or definition, another selected run or an
   * error ends the chain without cancelling durable work; waiting is bounded by the run budget. */
  struct RunAndShow {
    enum class Stage { Preparing, Starting, Waiting, Reading } stage = Stage::Preparing;
    std::function<bool()> valid;
    std::string run_id, plan;
    uint64_t selection = 0;
    double deadline = 0;
  };
  std::optional<RunAndShow> run_and_show_;
  std::string run_and_show_key_, run_and_show_detail_;
  uint64_t run_and_show_generation_ = 0;
  std::shared_ptr<const AnalysisResultInspection> result_view_;
  uint64_t result_generation_ = 0, result_browser_generation_ = 0;
  int result_output_ = -1, result_property_ = -1;
  std::optional<AnalysisJsonPath> result_path_;
  std::shared_ptr<const AnalysisJsonPropertyPage> result_properties_;
  std::optional<AnalysisJsonDescription> result_scalar_description_;
  AnalysisJsonText result_path_text_, result_scalar_text_;
  size_t result_path_page_ = 0, result_scalar_page_ = 0;
  std::string result_browser_error_;
  std::string table_grid_jump_row_ = "0", table_grid_jump_column_ = "0", table_grid_jump_error_;
  uint64_t table_grid_jump_row_generation_ = 0, table_grid_jump_column_generation_ = 0;
  bool result_grid_mode_ = false;
  std::shared_ptr<const AnalysisTableGrid> table_grid_;
  std::shared_ptr<const AnalysisTablePage> table_grid_page_;
  std::vector<std::string> table_grid_headers_;
  std::optional<size_t> table_grid_row_, table_grid_column_;
  AnalysisJsonText table_grid_name_, table_grid_unit_, table_grid_value_;
  std::optional<AnalysisJsonDescription> table_grid_description_;
  size_t table_grid_name_page_ = 0, table_grid_unit_page_ = 0, table_grid_value_page_ = 0;
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
    parameter_draft_.reset(); parameter_key_.reset(); draft_output_key_.reset(); parameter_buffer_.clear(); parameter_original_.clear();
    draft_output_page_ = 0;
    ++draft_output_page_generation_;
    parameter_error_.clear(); parameter_buffer_changed_ = parameter_detached_ = parameter_saving_ = false;
    parameter_input_id_ = 0; link_error_.clear(); candidate_check_.reset();
  }
  AnalysisCandidateKey candidate_key() const
  {
    return {parameter_draft_.handle(), parameter_draft_.analysis_id(), bridge_session(store_ ? store_->bridge() : nullptr),
        parameter_draft_.revision(), parameter_draft_.generation(), parameter_draft_.version()};
  }
  /** Saving a link change needs a passing graph.validate of exactly this candidate. */
  bool candidate_checked() const
  {
    // Positions alone never change evaluation; every other graph edit needs a passing check.
    return !parameter_draft_.evaluative_graph_edits() || candidate_check_.passed(candidate_key());
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
        parameter_key_.reset(); draft_output_key_.reset(); draft_output_page_ = 0;
      }
      parameter_draft_.pin(documents_->handle(), io::get_string(selected, "id"), documents_->selected_revision(),
                          io::get_string(selected, "name"), selected.at("document"));
      if (parameter_key_ && !parameter_draft_.has_override(*parameter_key_) && parameter_declaration(*parameter_key_).is_null()) {
        parameter_key_.reset();
      }
      if (draft_output_key_ && !parameter_draft_.baseline_document().at("graph").at("outputs").contains(*draft_output_key_)) {
        draft_output_key_.reset();
      }
      const auto output_count = parameter_draft_.baseline_document().at("graph").at("outputs").size();
      draft_output_page_ = std::min(draft_output_page_, output_count ? (output_count - 1) / 64 : 0);
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
    hint(*panel, ctx, "analysis_parameters.hint");
    if (parameter_edits()) { panel->paragraph(ctx.tr("analysis_parameters.dirty")); }
    if (!candidate_checked()) { panel->paragraph(ctx.tr("analysis_links.validate_first")); }
    if (unavailable) {
      panel->paragraph(ctx.tr("analysis_parameters.stale"));
      panel->paragraph(text(parameter_draft_.analysis_id()));
    }
    if (!parameter_error_.empty()) { panel->paragraph(text(parameter_error_)); }
    auto &actions = panel->row();
    const auto selection = parameter_selection_;
    actions.button("analysis_parameters_save", ctx.tr("analysis_parameters.save"), [this, valid, version, selection] {
      if (!valid() || !parameter_current() || (parameter_ui_ && parameter_ui_->text_input_active()) || parameter_buffer_changed_ ||
          state_->source() == AnalysisGraphState::Source::Run ||
          parameter_draft_.version() != version || !parameter_draft_.dirty() ||
          documents_->selected_version() != selection || !candidate_checked()) { return; }
      const bool sent = parameter_draft_.graph_edited() ?
          documents_->replace_definition(parameter_draft_.candidate_document(), selection) :
          documents_->replace_submission(parameter_draft_.parameters(), parameter_draft_.outputs(), selection);
      if (sent) {
        parameter_saving_ = true; parameter_save_generation_ = parameter_draft_.generation();
        parameter_save_version_ = parameter_draft_.version(); document_navigation_ = navigation_generation_;
      }
    }).disable(blocked || !parameter_draft_.dirty() || parameter_buffer_changed_ || (parameter_ui_ && parameter_ui_->text_input_active()) ||
               !candidate_checked());
    actions.button("analysis_parameters_discard", ctx.tr("analysis_parameters.discard"), [this, valid] {
      if (!valid() || documents_->busy() || documents_->uncertain() || parameter_text_active() ||
          state_->source() == AnalysisGraphState::Source::Run) { return; }
      clear_parameter_draft();
      if (!documents_->selected().is_null() && io::get_string(documents_->selected(), "state") == "readable") {
        pin_parameters();
      }
      redraw();
    }).disable(busy || parameter_text_active() || (!parameter_edits() && !unavailable));

    if (auto *parameters = panel->panel("analysis_parameter_values_panel", ctx.tr("analysis_graph.graph_parameters"), true)) {
      parameter_values_panel(*parameters, ctx, valid, generation, version, blocked);
    }
    draft_outputs_panel(*panel, ctx, valid, generation, version, blocked);
    links_panel(*panel, ctx, valid, version, blocked);
  }

  void links_panel(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid,
                   const uint64_t version, const bool blocked)
  {
    // Collapsed by default: most saved analyses are inspected or re-parameterized, not rewired.
    auto &catalog = ctx.store.catalog();
    const auto changes = parameter_draft_.link_edits().size();
    auto *panel = layout.panel("analysis_links_panel", changes ? catalog.format("analysis_links.title_count",
        {{"count", std::to_string(changes)}}) : std::string(ctx.tr("analysis_links.title")), false);
    if (!panel) { return; }
    hint(*panel, ctx, "analysis_links.hint");
    panel->paragraph(ctx.tr("analysis_links.canvas_note"));
    if (!link_error_.empty()) { panel->paragraph(text(link_error_)); }
    const auto &edits = parameter_draft_.link_edits();
    if (!edits.empty()) {
      panel->label(catalog.format("analysis_links.pending", {{"count", std::to_string(edits.size())}}));
      size_t shown = 0;
      for (const auto &[key, source] : edits) {
        if (++shown > 32) { break; }
        const auto before = parameter_draft_.baseline_link(key.first, key.second);
        panel->paragraph(catalog.format("analysis_links.change", {{"target", text(key.first + "." + key.second)},
            {"from", before ? text(*before) : std::string(ctx.tr("analysis_links.not_connected"))},
            {"to", source ? text(*source) : std::string(ctx.tr("analysis_links.not_connected"))}}));
      }
      omitted(*panel, ctx, edits.size() > 32 ? edits.size() - 32 : 0);
    }
    const bool editing = parameter_text_active() || parameter_buffer_changed_;
    const auto view = state_->view();
    // The canvas, ports and catalog hints must describe the very definition this draft edits.
    const bool same = view && state_->saved() && !state_->document_stale() &&
        state_->document_id() == parameter_draft_.analysis_id() && state_->document_revision() == parameter_draft_.revision();
    // Without the node catalog every type would look unknown: say why nothing is editable yet.
    if (state_->catalog_loading()) { panel->paragraph(ctx.tr("analysis_links.catalog_loading")); }
    else if (!state_->catalog_error().empty()) { panel->paragraph(ctx.tr("analysis_links.catalog_needed")); }
    else if (!same || !selected_ || *selected_ >= view->nodes.size()) {
      panel->paragraph(ctx.tr("analysis_links.select_node"));
    }
    else {
      const auto &node = view->nodes[*selected_];
      panel->label(text(node.id) + " · " + text(node.type));
      for (const auto &port : node.inputs) {
        const auto current = parameter_draft_.link(node.id, port.name);
        const bool edited = edits.count({node.id, port.name}) != 0;
        panel->label(catalog.format("analysis_links.port", {{"port", text(port.name)}, {"type", port.type_text},
            {"source", current ? text(*current) : std::string(ctx.tr("analysis_links.not_connected"))}}) +
            (edited ? "  · " + std::string(ctx.tr("analysis_links.edited")) : std::string()));
        const char *reason = !node.known_type ? "analysis_links.readonly_unknown_type" :
            node.ambiguous_id ? "analysis_links.readonly_duplicate" :
            !port.declared ? "analysis_links.readonly_undeclared" :
            port.multi ? "analysis_links.readonly_multi" :
            !parameter_draft_.link_editable(node.id, port.name) ? "analysis_links.readonly_shape" : nullptr;
        if (reason) { panel->paragraph(ctx.tr(reason)); continue; }
        // Catalog types are only hints: every declared upstream output is offered and
        // graph.validate alone decides compatibility, kinds and cycles.
        std::vector<std::optional<std::string>> values;
        std::vector<std::string> labels;
        if (!port.required || !current) {
          values.push_back(std::nullopt);
          labels.push_back(std::string(ctx.tr(port.required ? "analysis_links.not_connected" : "analysis_links.disconnect")));
        }
        for (const auto &other : view->nodes) {
          if (other.id == node.id || other.ambiguous_id) { continue; }
          for (const auto &output : other.outputs) {
            if (!output.declared) { continue; }
            values.push_back(other.id + "." + output.name);
            labels.push_back(text(other.id + "." + output.name) + "  (" + output.type_text + ")");
          }
        }
        if (current && std::find(values.begin(), values.end(), current) == values.end()) {
          values.push_back(current);
          labels.push_back(text(*current) + "  · " + std::string(ctx.tr("analysis_links.unlisted")));
        }
        const auto found = std::find(values.begin(), values.end(), current);
        const int index = found == values.end() ? -1 : int(found - values.begin());
        auto &scope = panel->scope("analysis_link/" + node.id + "/" + port.name);
        scope.dropdown("analysis_link_source", std::move(labels), {[index] { return index; },
            [this, valid, values, target = node.id, input = port.name](const int choice) {
          if (!valid() || !parameter_current() || documents_->busy() || documents_->uncertain() || parameter_text_active() ||
              parameter_buffer_changed_ || choice < 0 || size_t(choice) >= values.size()) { return; }
          const auto result = parameter_draft_.set_link(target, input, values[size_t(choice)], parameter_draft_.generation());
          link_error_ = result.accepted ? std::string() : result.error;
          redraw();
        }}).disable(blocked || editing);
      }
      omitted(*panel, ctx, node.omitted_inputs);
    }

    const auto key = candidate_key();
    const bool pending = candidate_check_.pending();
    auto *client = store_->bridge();
    const auto hello = client ? client->hello_info() : std::nullopt;
    const bool can_validate = hello && hello->has_method("graph.validate") && !key.session.empty();
    panel->button("analysis_links_validate", ctx.tr(pending ? "analysis_links.validating" : "analysis_links.validate"),
        [this, valid, version] {
      if (!valid() || !parameter_current() || candidate_check_.pending() || parameter_draft_.version() != version ||
          parameter_text_active() || parameter_buffer_changed_ || !parameter_draft_.dirty()) { return; }
      auto *bridge = store_->bridge();
      const auto check = candidate_key();
      const auto ready = bridge ? bridge->hello_info() : std::nullopt;
      if (!ready || !ready->has_method("graph.validate") || check.session.empty()) { return; }
      const auto candidate = parameter_draft_.candidate_document();
      const auto ticket = candidate_check_.begin(check);
      const std::weak_ptr<bool> weak = alive_;
      // Static validation only: it never evaluates nodes, prepares a run or touches the Viewer.
      candidate_future_ = bridge->graph_validate(candidate.at("graph"), candidate.at("parameters"));
      candidate_future_->then([this, weak, ticket](bridge::Result<Json> result) {
        const auto live = weak.lock();
        if (!live || !*live) { return; }
        candidate_future_.reset();
        if (!result) { candidate_check_.fail(ticket, result.error().describe()); }
        else { candidate_check_.finish(ticket, result.value()); }
        redraw();
      });
      redraw();
    }).disable(blocked || pending || editing || !parameter_draft_.dirty() || !can_validate);
    if (const auto *response = candidate_check_.result(key)) {
      const bool ok = response->at("ok").get<bool>();
      panel->paragraph(ctx.tr(ok ? "analysis_links.valid" : "analysis_links.invalid"));
      Rows issues;
      const auto &reported = response->at("issues");
      for (size_t index = 0; index < std::min<size_t>(reported.size(), 256); ++index) {
        const auto &issue = reported[index];
        if (!issue.is_object()) { continue; }
        issues.push_back({text(io::get_string(issue, "node")), text(io::get_string(issue, "code")),
            text(io::get_string(issue, "path")), text(io::get_string(issue, "message"))});
      }
      if (!issues.empty()) {
        table(*panel, "analysis_links_issues", {{std::string(ctx.tr("analysis_graph.node")), 6},
            {std::string(ctx.tr("analysis_graph.issue")), 8}, {std::string(ctx.tr("analysis_graph.path")), 12},
            {std::string(ctx.tr("analysis_graph.message")), 20}}, std::move(issues), parameter_draft_.version(), 4);
      }
      omitted(*panel, ctx, reported.size() > 256 ? reported.size() - 256 : 0);
    }
    else if (const auto error = candidate_check_.error(key); !error.empty()) { panel->paragraph(text(error)); }
  }

  void parameter_values_panel(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid,
                              const uint64_t generation, const uint64_t version, const bool blocked)
  {
    auto *panel = &layout;

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

  void draft_outputs_panel(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid,
                           const uint64_t generation, const uint64_t version, const bool blocked)
  {
    auto *panel = layout.panel("analysis_output_panel", ctx.tr("analysis_outputs.title"), true);
    if (!panel) { return; }
    const auto requested = parameter_draft_.outputs();
    const auto &declared = parameter_draft_.baseline_document().at("graph").at("outputs");
    hint(*panel, ctx, "analysis_outputs.hint");
    panel->label(ctx.store.catalog().format("analysis_outputs.count", {{"selected", std::to_string(requested.size())},
        {"total", std::to_string(declared.size())}}));
    if (requested.empty()) { panel->paragraph(ctx.tr("analysis_outputs.empty")); }
    const auto page = draft_output_page_;
    const auto page_generation = draft_output_page_generation_;
    const auto navigation = navigation_generation_;
    const auto offset = page * 64;
    const auto editable = [this, valid, version, page_generation, navigation] {
      return valid() && parameter_current() && parameter_draft_.version() == version &&
          draft_output_page_generation_ == page_generation && navigation_generation_ == navigation &&
          state_->source() != AnalysisGraphState::Source::Run && !documents_->busy() && !documents_->uncertain() &&
          !store_->project().busy() && !parameter_buffer_changed_ && !parameter_text_active();
    };
    const bool disabled = blocked || parameter_buffer_changed_ || parameter_text_active();
    std::vector<std::string> names, all_names; Rows rows; int selected = -1;
    size_t index = 0;
    for (const auto &[name, output] : declared.items()) {
      if (declared.size() <= AnalysisParameterDraft::max_outputs) { all_names.push_back(name); }
      if (index++ < offset || names.size() == 64) { continue; }
      if (draft_output_key_ && *draft_output_key_ == name) { selected = int(names.size()); }
      names.push_back(name);
      const auto requested_name = std::find(requested.begin(), requested.end(), Json(name));
      rows.push_back({text(name), requested_name == requested.end() ? std::string(ctx.tr("analysis_graph.not_requested")) :
          std::string(ctx.tr("analysis_graph.requested")) + " #" + std::to_string(std::distance(requested.begin(), requested_name) + 1),
          output.is_string() ? text(output.get_ref<const std::string &>()) : summary(output)});
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("analysis_graph.output")), 6}, {std::string(ctx.tr("analysis_graph.request")), 9},
        {std::string(ctx.tr("analysis_graph.port")), 10}};
    spec.rows = int(rows.size()); spec.visible_rows = float(std::min(4, std::max(1, spec.rows)));
    // Both counters are monotonic: data edits and page round trips invalidate the sort cache.
    spec.data_version = version + page_generation;
    spec.cell = [rows](const int row, const int col) { return rows.at(size_t(row)).at(size_t(col)); };
    spec.selected = {[selected] { return selected; }, [this, editable, names](const int index) {
      if (!editable() || index < 0 || size_t(index) >= names.size()) { return; }
      draft_output_key_ = names[size_t(index)]; redraw();
    }};
    panel->table("analysis_output_choices", std::move(spec)).disable(disabled);
    panel->label(ctx.store.catalog().format("analysis_outputs.page", {{"first", std::to_string(names.empty() ? 0 : offset + 1)},
        {"last", std::to_string(offset + names.size())}, {"total", std::to_string(declared.size())}}));
    auto &pages = panel->row();
    pages.button("analysis_outputs_previous", ctx.tr("analysis_documents.previous"), [this, editable, page] {
      if (!editable() || page == 0) { return; }
      draft_output_page_ = page - 1; ++draft_output_page_generation_; draft_output_key_.reset(); redraw();
    }).disable(disabled || page == 0);
    pages.button("analysis_outputs_next", ctx.tr("analysis_documents.next"), [this, editable, page, total = declared.size()] {
      if (!editable() || (page + 1) * 64 >= total) { return; }
      draft_output_page_ = page + 1; ++draft_output_page_generation_; draft_output_key_.reset(); redraw();
    }).disable(disabled || offset + names.size() >= declared.size());
    if (selected >= 0 && draft_output_key_) {
      const auto name = *draft_output_key_;
      panel->label(text(name));
      panel->checkbox("analysis_output_requested", ctx.tr("analysis_outputs.requested"),
          {[selected = parameter_draft_.output_selected(name)] { return selected; },
           [this, editable, name, generation](const bool selected) {
        if (!editable() || draft_output_key_ != name) { return; }
        const auto result = parameter_draft_.set_output(name, selected, generation);
        parameter_error_ = result.accepted ? "" : result.error; redraw();
      }}).disable(disabled);
    }
    auto &actions = panel->row();
    actions.button("analysis_outputs_all", ctx.tr("analysis_outputs.all"), [this, editable, generation, all_names, total = declared.size()] {
      if (!editable()) { return; }
      if (all_names.empty() || total > AnalysisParameterDraft::max_outputs) { return; }
      const auto result = parameter_draft_.set_outputs(Json(all_names), generation);
      parameter_error_ = result.accepted ? "" : result.error; redraw();
    }).disable(disabled || names.empty() || declared.size() > AnalysisParameterDraft::max_outputs);
    if (declared.size() > AnalysisParameterDraft::max_outputs) { panel->paragraph(ctx.tr("analysis_outputs.limit")); }
    actions.button("analysis_outputs_clear", ctx.tr("analysis_outputs.clear"), [this, editable, generation] {
      if (!editable()) { return; }
      const auto result = parameter_draft_.set_outputs(Json::array(), generation);
      parameter_error_ = result.accepted ? "" : result.error; redraw();
    }).disable(disabled || requested.empty());
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
      runs_epoch_ = runs_->epoch(); output_index_ = -1; clear_input_preparation();
    }
    if (run_selection_ != runs_->selection_generation()) {
      run_selection_ = runs_->selection_generation(); output_index_ = -1;
    }
    if (input_reuse_pending_ && (runs_->reusable_inputs_generation() >= input_reuse_pending_->expected_generation || !runs_->busy())) {
      // A completion is consumed exactly once, including refusals. Later clearing/finishing text
      // must never cause a formerly rejected response to fill the preparation form.
      auto pending = std::move(*input_reuse_pending_); input_reuse_pending_.reset();
      if (runs_->reusable_inputs_generation() == pending.expected_generation && runs_->reusable_inputs() &&
          pending.valid() && input_preparation_pristine() && !ctx.area.shell().text_input_active()) {
        reused_inputs_ = *runs_->reusable_inputs(); bindings_ = reused_inputs_->bindings;
        snapshot_index_ = file_index_ = mapping_index_ = -1; binding_name_ = "data"; binding_path_.clear(); binding_error_.clear();
        input_reuse_notice_ = "analysis_inputs.copied";
        binding_form_changed();
      }
      else { input_reuse_notice_ = "analysis_inputs.not_adopted"; }
    }
    if (result_view_ != runs_->result_inspection() || result_generation_ != runs_->result_generation()) {
      result_view_ = runs_->result_inspection(); result_generation_ = runs_->result_generation();
      result_output_ = result_property_ = -1; result_path_.reset(); result_properties_.reset();
      result_scalar_description_.reset(); result_scalar_text_ = {}; result_path_text_ = {};
      result_path_page_ = result_scalar_page_ = 0; result_browser_error_.clear(); clear_table_grid(); ++result_browser_generation_;
    }
    advance_run_and_show(ctx);
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

  static double steady_seconds()
  {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
  }

  void finish_run_and_show(std::string key, std::string detail = {})
  {
    run_and_show_.reset(); ++run_and_show_generation_;
    run_and_show_key_ = std::move(key); run_and_show_detail_ = std::move(detail); redraw();
  }

  /** Shows one verified payload output in the Viewer (the Show button and the end of Run and show). */
  void show_output(AppShell *shell, wm::Screen *screen, const std::string &output, const std::function<bool()> &same_archive,
                   std::function<void(const bridge::Error &)> failed)
  {
    const auto target = shell->analysis_payload_target(screen);
    if (!target) { failed(target.error()); return; }
    const auto payload = runs_->decode_payload(output);
    if (!payload || !same_archive()) { return; }
    const auto id = io::get_string(runs_->run(), "id");
    const auto label = io::get_string(runs_->run(), "analysis_name") + " · " + id.substr(0, 8) + " / " + output;
    shell->open_analysis_payload(screen, runs_->handle(), target.value(), payload, label, same_archive,
        [same_archive, failed = std::move(failed)](bridge::Result<Json> result) {
      if (same_archive() && !result) { failed(result.error()); }
    });
  }

  void advance_run_and_show(EditorContext &ctx)
  {
    if (!run_and_show_) { return; }
    auto &chain = *run_and_show_;
    if (!chain.valid()) { finish_run_and_show("analysis_runs.auto.abandoned"); return; }
    poll_runs(ctx);  // Keep following while the run section is not shown.
    if (runs_->busy()) { return; }
    if (runs_->uncertain()) { finish_run_and_show("analysis_runs.auto.uncertain"); return; }
    if (!runs_->error().empty()) { finish_run_and_show("analysis_runs.auto.failed", runs_->error()); return; }
    const auto &run = runs_->run();
    const auto id = io::get_string(run, "id"), status = io::get_string(run, "status");
    if (chain.stage == RunAndShow::Stage::Preparing) {
      if (run.is_null() || id != chain.run_id || status != "prepared") { finish_run_and_show("analysis_runs.auto.abandoned"); return; }
      chain.plan = io::get_string(run, "plan_sha256"); chain.selection = runs_->selection_generation();
      if (!runs_->start()) { finish_run_and_show("analysis_runs.auto.abandoned"); return; }
      chain.stage = RunAndShow::Stage::Starting; redraw();
      return;
    }
    if (run.is_null() || id != chain.run_id || io::get_string(run, "plan_sha256") != chain.plan ||
        runs_->selection_generation() != chain.selection) {
      finish_run_and_show("analysis_runs.auto.abandoned"); return;
    }
    if (chain.stage == RunAndShow::Stage::Reading) {
      if (runs_->result().is_null()) { finish_run_and_show("analysis_runs.auto.failed"); return; }
      const auto outputs = runs_->payload_outputs();
      if (outputs.empty()) { finish_run_and_show("analysis_runs.auto.no_payload"); return; }
      output_index_ = 0;
      const bool partial = !run.at("result").is_null() && run.at("result").value("has_errors", false);
      const auto archive = runs_->result_generation();
      const std::weak_ptr<bool> weak = alive_;
      const auto valid = chain.valid;
      const auto same_archive = [this, weak, valid, archive, id] {
        const auto live = weak.lock();
        return live && *live && valid() && runs_->result_generation() == archive && io::get_string(runs_->run(), "id") == id;
      };
      const auto generation = run_and_show_generation_ + 1;
      finish_run_and_show(partial ? "analysis_runs.auto.shown_partial" : "analysis_runs.auto.shown", outputs.front());
      show_output(&ctx.area.shell(), ctx.area.screen(), outputs.front(), same_archive, [this, weak, generation](const bridge::Error &error) {
        const auto live = weak.lock();
        if (live && *live && run_and_show_generation_ == generation) { finish_run_and_show("analysis_runs.auto.viewer_failed", error.message); }
      });
      return;
    }
    if (status == "prepared") { finish_run_and_show("analysis_runs.auto.abandoned"); return; }  // Start was refused.
    if (status == "running" || status == "cancel_requested") {
      chain.stage = RunAndShow::Stage::Waiting;
      if (!runs_->following()) {
        // Reads stop after 90 s; keep observing this run up to its own budget, then hand back.
        if (steady_seconds() >= chain.deadline || !runs_->load(chain.run_id)) {
          finish_run_and_show("analysis_runs.auto.still_running"); return;
        }
        chain.selection = runs_->selection_generation();
      }
      return;
    }
    if (status == "succeeded" || (status == "failed" && !run.at("result").is_null())) {
      if (run.at("result").is_null() || !runs_->read_result()) { finish_run_and_show("analysis_runs.auto.no_payload"); return; }
      chain.stage = RunAndShow::Stage::Reading; redraw();
      return;
    }
    finish_run_and_show("analysis_runs.auto.ended", std::string(ctx.tr("analysis_runs.status." + status)));
  }

  void run_and_show_status(ui::Layout &layout, EditorContext &ctx)
  {
    if (run_and_show_) {
      const char *key = run_and_show_->stage == RunAndShow::Stage::Preparing ? "analysis_runs.auto.preparing" :
                        run_and_show_->stage == RunAndShow::Stage::Reading ? "analysis_runs.auto.reading" : "analysis_runs.auto.running";
      auto &row = layout.row();
      row.label(ctx.tr(key));
      const std::weak_ptr<bool> weak = alive_;
      row.button("analysis_run_and_show_stop", ctx.tr("analysis_runs.auto.stop"), [this, weak] {
        const auto live = weak.lock();
        if (live && *live && run_and_show_) { finish_run_and_show("analysis_runs.auto.stopped"); }
      }).width(6);
      return;
    }
    if (run_and_show_key_.empty()) { return; }
    layout.paragraph(ctx.store.catalog().format(run_and_show_key_, {{"detail", text(run_and_show_detail_)}}));
  }

  void runs_panel(ui::Layout &layout, EditorContext &ctx)
  {
    poll_runs(ctx);
    if (!runs_->supported()) {
      layout.paragraph(ctx.tr(ctx.store.project().project() && ctx.store.project().project()->format_version < 9 ?
          "analysis_runs.upgrade" : "analysis_runs.unavailable"));
      return;
    }
    hint(layout, ctx, "analysis_runs.canvas_hint");
    if (parameter_edits()) { layout.paragraph(ctx.tr("analysis_parameters.run_guard")); }
    if (!state_->document_id().empty()) {
      layout.label(text(document_name_.empty() ? state_->document_id() : document_name_)).tip(state_->document_id());
    }
    const std::weak_ptr<bool> weak = alive_;
    const auto epoch = runs_->epoch();
    const auto valid = [this, weak, epoch] {
      const auto live = weak.lock();
      if (!live || !*live) { return false; }
      runs_->sync(); return runs_->epoch() == epoch;
    };
    const bool blocked = runs_->busy() || ctx.store.project().busy();
    run_and_show_status(layout, ctx);
    if (!runs_->error().empty()) { layout.paragraph(text(runs_->error())); }
    if (!input_reuse_notice_.empty()) { layout.paragraph(ctx.tr(input_reuse_notice_)); }
    if (input_reuse_pending_) { layout.paragraph(ctx.tr("analysis_inputs.reading")); }
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
      hint(*prepare, ctx, "analysis_runs.prepare_hint");
      if (id.empty()) { prepare->paragraph(ctx.tr("analysis_runs.select_definition")); }
      else {
        prepare->label(text(document_name_.empty() ? id : document_name_)).tip(id);
        prepare->label(ctx.store.catalog().format("analysis_documents.revision", {{"revision", std::to_string(revision)}}));
        if (state_->document_stale()) { prepare->paragraph(ctx.tr("analysis_runs.stale_definition")); }
      }
      prepare->button("analysis_run_and_show", ctx.tr("analysis_runs.auto.button"),
          [this, valid, generation, bindings_generation, id, revision, snapshot, bindings] {
        if (!valid() || parameter_edits() || run_and_show_) { return; }
        state_->sync();
        if (!state_->saved() || state_->generation() != generation || bindings_generation_ != bindings_generation ||
            state_->document_id() != id || state_->document_stale() || !runs_->prepare(id, revision, snapshot, bindings)) { return; }
        const std::weak_ptr<bool> weak = alive_;
        const auto epoch = runs_->epoch();
        const auto handle = runs_->handle();
        RunAndShow chain;
        chain.valid = [this, weak, epoch, handle, id] {
          const auto live = weak.lock();
          return live && *live && runs_->epoch() == epoch && runs_->handle() == handle &&
                 state_->saved() && state_->document_id() == id && !state_->document_stale();
        };
        chain.run_id = runs_->pending_id();
        chain.selection = runs_->selection_generation();
        chain.deadline = steady_seconds() + 330;  // The frozen budget allows 300 s of execution.
        run_and_show_ = std::move(chain); run_and_show_key_.clear(); run_and_show_detail_.clear(); ++run_and_show_generation_;
        redraw();
      }).disable(blocked || parameter_edits() || runs_->uncertain() || id.empty() || state_->document_stale() || snapshot.empty() ||
                 bindings.empty() || run_and_show_.has_value());
      hint(*prepare, ctx, "analysis_runs.auto.hint");
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
    if (reused_inputs_) { return reused_inputs_->snapshot_id; }
    const auto &snapshots = runs_->snapshots();
    return snapshot_index_ >= 0 && size_t(snapshot_index_) < snapshots.size() ?
        io::get_string(snapshots[size_t(snapshot_index_)], "id") : std::string();
  }

  Json selected_snapshot_files() const
  {
    if (reused_inputs_) { return reused_inputs_->files; }
    const auto &snapshots = runs_->snapshots();
    return snapshot_index_ >= 0 && size_t(snapshot_index_) < snapshots.size() ?
        snapshots[size_t(snapshot_index_)].at("manifest").at("files") : Json::array();
  }

  bool input_preparation_pristine() const
  {
    return !reused_inputs_ && snapshot_index_ < 0 && file_index_ < 0 && mapping_index_ < 0 &&
        binding_name_ == "data" && binding_path_.empty() && bindings_.empty();
  }

  void binding_form_changed()
  {
    ++bindings_generation_; ++binding_name_generation_; ++binding_path_generation_;
  }

  void clear_input_preparation()
  {
    input_reuse_pending_.reset(); reused_inputs_.reset(); snapshot_index_ = file_index_ = mapping_index_ = -1;
    input_reuse_notice_.clear();
    bindings_ = Json::object(); binding_name_ = "data"; binding_path_.clear(); binding_error_.clear(); binding_form_changed();
  }

  void binding_controls(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid, const bool blocked)
  {
    auto *shell = &ctx.area.shell();
    const auto navigation = navigation_generation_;
    const auto form_generation = bindings_generation_;
    const auto same_form = [this, valid, navigation] {
      return valid() && navigation_generation_ == navigation && state_->saved() && saved_section_ == 1;
    };
    const auto form_valid = [this, same_form, form_generation] {
      return same_form() && bindings_generation_ == form_generation;
    };
    layout.button("analysis_input_preparation_clear", ctx.tr("analysis_inputs.clear"), [this, form_valid, shell, navigation] {
      if (!form_valid() || shell->text_input_active() || navigation_generation_ != navigation || !state_->saved() || saved_section_ != 1) { return; }
      clear_input_preparation(); redraw();
    }).disable(shell->text_input_active());
    if (reused_inputs_) {
      layout.paragraph(ctx.tr("analysis_inputs.reused"));
      table(layout, "analysis_reused_inputs", {{std::string(ctx.tr("analysis_graph.parameter")), 8},
          {std::string(ctx.tr("analysis_graph.value")), 22}},
          {{std::string(ctx.tr("analysis_runs.run_id")), reused_inputs_->run_id},
           {std::string(ctx.tr("analysis_runs.snapshot_id")), reused_inputs_->snapshot_id},
           {std::string(ctx.tr("analysis_runs.snapshot_hash")), reused_inputs_->snapshot_sha256}}, bindings_generation_, 3);
      layout.paragraph(ctx.tr("analysis_inputs.metadata_only"));
    }
    hint(layout, ctx, "analysis_runs.snapshot_hint");
    layout.button("analysis_run_snapshots", ctx.tr("analysis_runs.load_snapshots"), [this, form_valid] {
      if (form_valid() && input_preparation_pristine() && runs_->load_snapshots()) {
        // A refreshed list can have a different ordering; retain explicit mappings only by
        // forcing an explicit selection again, never reinterpret an old list index.
        snapshot_index_ = file_index_ = mapping_index_ = -1;
        bindings_ = Json::object(); binding_path_.clear(); binding_form_changed();
      }
    }).disable(blocked || !input_preparation_pristine());
    const auto snapshots = runs_->snapshots();
    std::vector<std::string> labels{std::string(ctx.tr("analysis_runs.choose_snapshot"))};
    for (const auto &snapshot : snapshots) {
      labels.push_back(io::get_string(snapshot, "id").substr(0, 8) + " · " +
          std::to_string(snapshot.at("manifest").at("files").size()) + " " + std::string(ctx.tr("analysis_runs.files")));
    }
    if (!reused_inputs_) { layout.dropdown("analysis_run_snapshot", std::move(labels), {[selected = snapshot_index_ + 1] { return selected; },
        [this, form_valid, snapshots](const int index) {
      if (!form_valid() || reused_inputs_ || index < 0 || size_t(index) > snapshots.size() || !bindings_.empty()) { return; }
      snapshot_index_ = index - 1; file_index_ = mapping_index_ = -1;
      binding_path_.clear(); binding_error_.clear(); binding_form_changed();
    }}).disable(blocked || snapshots.empty() || !bindings_.empty()); }
    omitted(layout, ctx, runs_->omitted_snapshots());
    const auto snapshot_id = selected_snapshot_id();
    if (snapshot_id.empty()) { return; }
    const auto files = selected_snapshot_files();
    std::vector<std::string> names{std::string(ctx.tr("analysis_runs.choose_file"))};
    for (const auto &file : files) { names.push_back(text(io::get_string(file, "name"))); }
    layout.dropdown("analysis_run_file", std::move(names), {[selected = file_index_ + 1] { return selected; },
        [this, form_valid, files, snapshot_id](const int index) {
      if (!form_valid() || selected_snapshot_id() != snapshot_id || index < 0 || size_t(index) > files.size()) { return; }
      file_index_ = index - 1;
      binding_path_ = file_index_ >= 0 ? io::get_string(files[size_t(file_index_)], "name") : std::string();
      binding_form_changed(); redraw();
    }}).disable(blocked);
    // Tab commits one field and focuses its sibling before the next redraw. Keep
    // separate text generations, while every commit still invalidates captured actions.
    // Non-text preparation changes invalidate both fields through binding_form_changed().
    const auto draft_field = [this, same_form, snapshot_id](std::string *value, uint64_t *generation) {
      return ui::Binding<std::string>{[copy = *value] { return copy; },
          [this, same_form, snapshot_id, value, generation, expected = *generation](const std::string &input) {
        if (!same_form() || selected_snapshot_id() != snapshot_id || *generation != expected) { return; }
        *value = input; ++*generation; ++bindings_generation_; redraw();
      }};
    };
    layout.prop(ctx.tr("analysis_runs.binding")).text_field("analysis_run_binding", draft_field(&binding_name_, &binding_name_generation_), {.max_length = 64}).disable(blocked);
    layout.prop(ctx.tr("analysis_runs.relative_path")).text_field("analysis_run_path", draft_field(&binding_path_, &binding_path_generation_), {.max_length = 1024}).disable(blocked);
    layout.paragraph(ctx.tr("analysis_inputs.finish_text"));
    layout.button("analysis_run_add_file", ctx.tr("analysis_runs.add_file"), [this, form_valid, files, snapshot_id, shell] {
      if (shell->text_input_active() || !form_valid() || selected_snapshot_id() != snapshot_id || file_index_ < 0 || size_t(file_index_) >= files.size()) { return; }
      size_t count = 0; for (const auto &binding : bindings_) { count += binding.size(); }
      if (binding_name_.empty() || binding_path_.empty() || count >= 100 ||
          (!bindings_.contains(binding_name_) && bindings_.size() >= 32) ||
          (bindings_.contains(binding_name_) && bindings_.at(binding_name_).contains(binding_path_))) {
        binding_error_ = std::string(store_->tr("analysis_runs.mapping_invalid")); redraw(); return;
      }
      bindings_[binding_name_][binding_path_] = files[size_t(file_index_)].at("record_id");
      binding_error_.clear(); binding_form_changed(); redraw();
    }).disable(blocked || file_index_ < 0 || shell->text_input_active());
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
      spec.selected = {[index = mapping_index_] { return index; }, [this, form_valid, generation](const int index) {
        if (form_valid() && bindings_generation_ == generation && index >= 0) { mapping_index_ = index; binding_form_changed(); redraw(); }
      }};
      layout.table("analysis_run_bindings", std::move(spec)).disable(blocked);
      auto &buttons = layout.row();
      buttons.button("analysis_run_remove_file", ctx.tr("analysis_runs.remove_file"), [this, form_valid, generation, keys] {
        if (!form_valid() || bindings_generation_ != generation || mapping_index_ < 0 || size_t(mapping_index_) >= keys.size()) { return; }
        const auto &[binding, path] = keys[size_t(mapping_index_)];
        bindings_[binding].erase(path); if (bindings_[binding].empty()) { bindings_.erase(binding); }
        mapping_index_ = -1; binding_form_changed(); redraw();
      }).disable(blocked || mapping_index_ < 0 || size_t(mapping_index_) >= keys.size());
      buttons.button("analysis_run_clear_files", ctx.tr("analysis_runs.clear_files"), [this, form_valid] {
        if (form_valid()) { bindings_ = Json::object(); mapping_index_ = -1; binding_form_changed(); redraw(); }
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
    if (!run.at("error").is_null()) { box.paragraph(text(io::get_string(run.at("error"), "message"))); }
    const bool partial = !run.at("result").is_null() && run.at("result").at("has_errors").get<bool>();
    if (partial) { box.paragraph(ctx.tr("analysis_runs.partial")); }
    if (status == "unknown") { box.paragraph(ctx.tr("analysis_runs.unknown_hint")); }
    if (status == "running" || status == "cancel_requested") {
      box.paragraph(ctx.tr(runs_->following() ? "analysis_runs.following" : "analysis_runs.follow_stopped"));
    }
    const auto plan = io::get_string(run, "plan_sha256");
    const auto navigation = navigation_generation_;
    const auto input_generation = bindings_generation_;
    const auto document_epoch = documents_->epoch(), document_version = documents_->selected_version();
    const auto target = state_->document_id();
    const auto reuse_valid = [this, same_run, navigation, input_generation, document_epoch, document_version, target, plan] {
      if (!same_run()) { return false; }
      documents_->sync();
      return navigation_generation_ == navigation && bindings_generation_ == input_generation &&
          state_->saved() && saved_section_ == 1 && !target.empty() && state_->document_id() == target &&
          documents_->epoch() == document_epoch && documents_->selected_version() == document_version &&
          io::get_string(documents_->selected(), "id") == target &&
          !documents_->busy() && !store_->project().busy() && io::get_string(runs_->run(), "plan_sha256") == plan;
    };
    box.button("analysis_run_reuse_inputs", ctx.tr("analysis_inputs.reuse"), [this, reuse_valid, shell] {
      if (!reuse_valid() || shell->text_input_active() || !input_preparation_pristine() || input_reuse_pending_) { return; }
      const auto expected = runs_->reusable_inputs_generation() + 1;
      if (runs_->read_reusable_inputs()) {
        input_reuse_pending_ = InputReusePending{expected, reuse_valid}; input_reuse_notice_.clear(); redraw();
      }
    }).disable(blocked || runs_->uncertain() || !runs_->reusable_inputs_supported() || target.empty() ||
        documents_->busy() || !input_preparation_pristine() || input_reuse_pending_ || shell->text_input_active());
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
      frozen->paragraph(id);
      frozen->label(ctx.store.catalog().format("analysis_documents.revision", {{"revision", std::to_string(io::get_int(run, "source_revision", -1))}}));
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
    result_panel(box, ctx, same_run, blocked);
    const auto outputs = runs_->payload_outputs();
    const auto archive_generation = runs_->result_generation();
    const auto same_archive = [this, same_run, archive_generation] {
      return same_run() && runs_->result_generation() == archive_generation;
    };
    if (outputs.empty()) { box.paragraph(ctx.tr("analysis_runs.no_payload")); return; }
    std::vector<std::string> choices{std::string(ctx.tr("analysis_runs.choose_output"))};
    choices.insert(choices.end(), outputs.begin(), outputs.end());
    box.dropdown("analysis_run_output", std::move(choices), {[selected = output_index_ + 1] { return selected; },
        [this, same_archive, outputs](const int index) {
      if (same_archive() && index >= 0 && size_t(index) <= outputs.size()) { output_index_ = index - 1; }
    }}).disable(blocked);
    auto *screen = ctx.area.screen();
    box.paragraph(ctx.tr("analysis_runs.viewer_hint"));
    box.button("analysis_run_show", ctx.tr("analysis_runs.show"), [this, same_archive, shell, screen, outputs] {
      if (!same_archive() || output_index_ < 0 || size_t(output_index_) >= outputs.size()) { return; }
      show_output(shell, screen, outputs[size_t(output_index_)], same_archive, [this](const bridge::Error &error) {
        if (store_->toast) { store_->toast(error.message, ui::ToastKind::Warning); }
      });
    }).disable(blocked || output_index_ < 0 || size_t(output_index_) >= outputs.size());
  }

  static bool result_container(const AnalysisJsonType type)
  {
    return type == AnalysisJsonType::Object || type == AnalysisJsonType::Array;
  }

  static const char *result_type_key(const AnalysisJsonType type)
  {
    switch (type) {
      case AnalysisJsonType::Null: return "analysis_results.type.null";
      case AnalysisJsonType::Boolean: return "analysis_results.type.boolean";
      case AnalysisJsonType::Integer: return "analysis_results.type.integer";
      case AnalysisJsonType::UnsignedInteger: return "analysis_results.type.unsigned";
      case AnalysisJsonType::Float: return "analysis_results.type.float";
      case AnalysisJsonType::String: return "analysis_results.type.string";
      case AnalysisJsonType::Array: return "analysis_results.type.array";
      case AnalysisJsonType::Object: return "analysis_results.type.object";
    }
    return "analysis_results.unknown";
  }

  void browse_result(AnalysisJsonPath path, const size_t offset = 0)
  {
    if (!result_view_) { return; }
    try {
      const auto description = result_view_->describe(path);
      std::shared_ptr<const AnalysisJsonPropertyPage> properties;
      AnalysisJsonText scalar;
      if (result_container(description.type)) { properties = std::make_shared<const AnalysisJsonPropertyPage>(result_view_->children(path, offset)); }
      else { scalar = result_view_->scalar_text(path); }
      auto path_text = result_view_->path_text(path);
      result_grid_mode_ = false;
      result_path_ = std::move(path); result_properties_ = std::move(properties); result_property_ = -1;
      result_scalar_description_ = result_container(description.type) ? std::nullopt : std::optional(description);
      result_scalar_text_ = std::move(scalar); result_path_text_ = std::move(path_text);
      result_path_page_ = result_scalar_page_ = 0; result_browser_error_.clear(); ++result_browser_generation_; redraw();
    }
    catch (const std::exception &error) { result_browser_error_ = error.what(); redraw(); }
  }

  void select_result_property(const int index)
  {
    if (!result_view_ || !result_path_ || !result_properties_ || index < 0 || size_t(index) >= result_properties_->rows.size()) { return; }
    try {
      const auto &item = result_properties_->rows[size_t(index)];
      AnalysisJsonText scalar;
      if (!result_container(item.value.type)) {
        auto path = *result_path_; path.push_back(item.component); scalar = result_view_->scalar_text(path);
      }
      result_property_ = index;
      result_scalar_description_ = result_container(item.value.type) ? std::nullopt : std::optional(item.value);
      result_scalar_text_ = std::move(scalar); result_scalar_page_ = 0; result_browser_error_.clear();
      ++result_browser_generation_; redraw();
    }
    catch (const std::exception &error) { result_browser_error_ = error.what(); redraw(); }
  }

  void result_panel(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &same_run, const bool blocked)
  {
    if (!result_view_) { return; }
    auto *panel = layout.panel("analysis_result_inspection", ctx.tr("analysis_results.title"), true);
    if (!panel) { return; }
    const auto generation = result_generation_, browser = result_browser_generation_, navigation = navigation_generation_;
    auto *shell = &ctx.area.shell();
    const auto same_view = [this, same_run, generation, navigation] {
      return same_run() && !runs_->busy() && !store_->project().busy() &&
          state_->saved() && saved_section_ == 1 && navigation_generation_ == navigation &&
          runs_->result_generation() == generation && result_generation_ == generation &&
          result_view_ == runs_->result_inspection();
    };
    const auto valid = [this, same_view, browser, shell] {
      return same_view() && result_browser_generation_ == browser && !shell->text_input_active();
    };
    const bool disabled = blocked || shell->text_input_active();
    panel->paragraph(ctx.tr("analysis_results.hint"));
    const auto model = result_view_;
    if (model->outputs().empty()) { panel->paragraph(ctx.tr("analysis_results.empty")); }
    else {
      Rows rows;
      for (const auto &output : model->outputs()) {
        rows.push_back({output.name, std::string(ctx.tr(output.delivered ? "analysis_results.delivered" : "analysis_results.missing")),
            output.delivery_type.empty() ? std::string(ctx.tr("analysis_results.unknown")) : output.delivery_type});
      }
      ui::TableSpec spec;
      spec.columns = {{std::string(ctx.tr("analysis_graph.output")), 6},
          {std::string(ctx.tr("analysis_results.delivery")), 8}, {std::string(ctx.tr("analysis_graph.type")), 8}};
      spec.rows = int(rows.size()); spec.visible_rows = float(std::min(5, spec.rows)); spec.data_version = result_browser_generation_;
      spec.cell = [rows = std::move(rows)](int row, int col) { return rows.at(size_t(row)).at(size_t(col)); };
      spec.selected = {[selected = result_output_] { return selected; }, [this, valid, model](int index) {
        if (!valid() || index < 0 || size_t(index) >= model->outputs().size()) { return; }
        clear_table_grid(); result_output_ = index;
        const auto &output = model->outputs()[size_t(index)];
        if (output.delivered) { browse_result(output.path); }
        else {
          result_path_.reset(); result_properties_.reset(); result_property_ = -1;
          result_scalar_description_.reset(); result_scalar_text_ = {}; result_path_text_ = {};
          result_browser_error_.clear(); ++result_browser_generation_; redraw();
        }
      }};
      panel->table("analysis_result_outputs", std::move(spec)).disable(disabled);
    }
    if (result_output_ >= 0 && size_t(result_output_) < model->outputs().size()) {
      const auto &output = model->outputs()[size_t(result_output_)];
      if (!output.delivered) { panel->paragraph(ctx.tr("analysis_results.missing_hint")); }
      if (output.content_not_loaded) { panel->paragraph(ctx.tr("analysis_results.not_loaded")); }
      if (output.metadata_only) { panel->paragraph(ctx.tr("analysis_results.metadata")); }
    }
    if (result_output_ >= 0 && size_t(result_output_) < model->outputs().size()) {
      const auto &output = model->outputs()[size_t(result_output_)];
      auto &views = panel->row();
      const auto name = output.name;
      views.button("analysis_result_table_grid", ctx.tr("analysis_table_grid.open"), [this, valid, model, name] {
        if (!valid()) { return; }
        try {
          auto grid = AnalysisTableGrid::from_output(model, name);
          clear_table_grid(); table_grid_ = std::move(grid);
          result_grid_mode_ = true; result_browser_error_.clear(); set_table_grid_page(0, 0);
        }
        catch (const std::exception &error) { result_browser_error_ = error.what(); result_grid_mode_ = false; ++result_browser_generation_; redraw(); }
      }).disable(disabled || !output.delivered || output.delivery_type != "table" || output.content_not_loaded);
      views.button("analysis_result_properties_view", ctx.tr("analysis_table_grid.properties"), [this, valid, model, name] {
        if (valid()) { browse_result(AnalysisJsonPath{std::string("outputs"), name}); }
      }).disable(disabled || !output.delivered);
    }
    auto &issues = panel->row();
    issues.button("analysis_result_errors", ctx.tr("analysis_results.errors"), [this, valid, model] {
      if (valid() && model->errors().present) { result_output_ = -1; browse_result(model->errors().path); }
    }).disable(disabled || !model->errors().present);
    issues.button("analysis_result_warnings", ctx.tr("analysis_results.warnings"), [this, valid, model] {
      if (valid() && model->warnings().present) { result_output_ = -1; browse_result(model->warnings().path); }
    }).disable(disabled || !model->warnings().present);
    if (!result_browser_error_.empty()) { panel->paragraph(text(result_browser_error_)); }
    if (result_grid_mode_) { table_grid_panel(*panel, ctx, valid, same_view, disabled); return; }
    if (!result_path_) { return; }
    panel->label(ctx.tr("analysis_results.path"));
    if (result_path_text_.total_bytes == 0) { panel->paragraph(ctx.tr("analysis_results.root")); }
    else { panel->scope("analysis_result_path_text").paragraph(result_path_text_.pages.at(result_path_page_)); }
    result_text_pages(*panel, ctx, valid, disabled, true);
    auto &navigation_row = panel->row();
    navigation_row.button("analysis_result_up", ctx.tr("analysis_results.up"), [this, valid] {
      if (valid() && result_path_ && !result_path_->empty()) { auto path = *result_path_; path.pop_back(); browse_result(std::move(path)); }
    }).disable(disabled || result_path_->empty());
    navigation_row.button("analysis_result_open", ctx.tr("analysis_results.open"), [this, valid] {
      if (!valid() || !result_path_ || !result_properties_ || result_property_ < 0 ||
          size_t(result_property_) >= result_properties_->rows.size()) { return; }
      const auto &property = result_properties_->rows[size_t(result_property_)];
      auto path = *result_path_; path.push_back(property.component); browse_result(std::move(path));
    }).disable(disabled || !result_properties_ || result_property_ < 0 ||
        size_t(result_property_) >= result_properties_->rows.size());
    if (result_properties_) {
      const auto page = result_properties_;
      panel->label(ctx.store.catalog().format("analysis_results.properties_page", {{"first", std::to_string(page->total ? page->offset + 1 : 0)},
          {"last", std::to_string(page->offset + page->rows.size())}, {"total", std::to_string(page->total)}}));
      ui::TableSpec spec;
      spec.columns = {{std::string(ctx.tr("analysis_results.key")), 6}, {std::string(ctx.tr("analysis_graph.value")), 10},
          {std::string(ctx.tr("analysis_graph.type")), 6}};
      spec.rows = int(page->rows.size()); spec.visible_rows = float(std::max(1, std::min(6, spec.rows)));
      spec.data_version = result_browser_generation_;
      std::vector<std::string> types; for (const auto &item : page->rows) { types.emplace_back(ctx.tr(result_type_key(item.value.type))); }
      spec.cell = [page, types = std::move(types)](int row, int column) {
        const auto &item = page->rows.at(size_t(row));
        if (column == 0) { return item.label + (item.label_truncated ? " …" : ""); }
        if (column == 1) { return item.value.preview + (item.value.preview_truncated ? " …" : ""); }
        return types.at(size_t(row));
      };
      spec.selected = {[selected = result_property_] { return selected; }, [this, valid](int index) {
        if (valid()) { select_result_property(index); }
      }};
      panel->table("analysis_result_properties", std::move(spec)).disable(disabled);
      auto &pages = panel->row();
      pages.button("analysis_result_previous", ctx.tr("analysis_documents.previous"), [this, valid, page] {
        if (valid() && result_path_ && page->offset) { browse_result(*result_path_, page->offset > 64 ? page->offset - 64 : 0); }
      }).disable(disabled || page->offset == 0);
      pages.button("analysis_result_next", ctx.tr("analysis_documents.next"), [this, valid, page] {
        if (valid() && result_path_ && page->next_offset) { browse_result(*result_path_, *page->next_offset); }
      }).disable(disabled || !page->next_offset);
    }
    if (result_scalar_description_) {
      panel->label(std::string(ctx.tr("analysis_results.exact")) + " · " + std::string(ctx.tr(result_type_key(result_scalar_description_->type))));
      panel->scope("analysis_result_scalar_text").paragraph(result_scalar_text_.pages.at(result_scalar_page_));
      result_text_pages(*panel, ctx, valid, disabled, false);
    }
  }

  void result_text_pages(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid, const bool disabled, const bool path)
  {
    const auto &value = path ? result_path_text_ : result_scalar_text_;
    auto &index = path ? result_path_page_ : result_scalar_page_;
    if (value.pages.size() <= 1) { return; }
    layout.label(ctx.store.catalog().format("analysis_results.text_page", {{"page", std::to_string(index + 1)},
        {"total", std::to_string(value.pages.size())}, {"bytes", std::to_string(value.total_bytes)}}));
    auto &buttons = layout.row();
    buttons.button(path ? "analysis_result_path_previous" : "analysis_result_scalar_previous", ctx.tr("analysis_documents.previous"), [this, valid, path] {
      if (!valid()) { return; }
      auto &page = path ? result_path_page_ : result_scalar_page_;
      if (page) { --page; ++result_browser_generation_; redraw(); }
    }).disable(disabled || index == 0);
    buttons.button(path ? "analysis_result_path_next" : "analysis_result_scalar_next", ctx.tr("analysis_documents.next"), [this, valid, path] {
      if (!valid()) { return; }
      auto &page = path ? result_path_page_ : result_scalar_page_;
      const auto &text = path ? result_path_text_ : result_scalar_text_;
      if (page + 1 < text.pages.size()) { ++page; ++result_browser_generation_; redraw(); }
    }).disable(disabled || index + 1 >= value.pages.size());
  }

  void clear_table_grid()
  {
    table_grid_jump_row_ = table_grid_jump_column_ = "0"; table_grid_jump_error_.clear();
    ++table_grid_jump_row_generation_; ++table_grid_jump_column_generation_;
    result_grid_mode_ = false; table_grid_.reset(); table_grid_page_.reset(); table_grid_headers_.clear();
    table_grid_row_.reset(); table_grid_column_.reset(); table_grid_description_.reset();
    table_grid_name_ = {}; table_grid_unit_ = {}; table_grid_value_ = {};
    table_grid_name_page_ = table_grid_unit_page_ = table_grid_value_page_ = 0;
  }

  void select_table_grid_cell(const std::optional<size_t> row, const size_t column)
  {
    if (!table_grid_ || column >= table_grid_->columns().size() || (row && *row >= table_grid_->row_count())) { return; }
    try {
      auto name = result_view_->scalar_text(table_grid_->column_name_path(column));
      AnalysisJsonText unit, value;
      std::optional<AnalysisJsonDescription> description;
      if (table_grid_->columns()[column].has_unit) { unit = result_view_->scalar_text(table_grid_->unit_path(column)); }
      if (row) {
        const auto path = table_grid_->cell_path(*row, column); description = result_view_->describe(path);
        if (!result_container(description->type)) { value = result_view_->scalar_text(path); }
      }
      table_grid_row_ = row; table_grid_column_ = column; table_grid_description_ = std::move(description);
      table_grid_name_ = std::move(name); table_grid_unit_ = std::move(unit); table_grid_value_ = std::move(value);
      table_grid_name_page_ = table_grid_unit_page_ = table_grid_value_page_ = 0;
      result_browser_error_.clear(); ++result_browser_generation_; redraw();
    }
    catch (const std::exception &error) { result_browser_error_ = error.what(); redraw(); }
  }

  void set_table_grid_page(const size_t row, const size_t column)
  {
    if (!table_grid_) { return; }
    try {
      auto page = std::make_shared<const AnalysisTablePage>(table_grid_->page(row, column));
      std::vector<std::string> headers;
      for (const auto index : page->columns) {
        const auto &item = table_grid_->columns()[index];
        std::string label = item.label + (item.label_truncated ? " …" : "");
        if (item.has_unit) {
          const auto unit = table_grid_->unit_description(index);
          label += " [" + unit.preview + (unit.preview_truncated ? " …" : "") + "]";
        }
        headers.push_back(std::move(label));
      }
      table_grid_page_ = std::move(page); table_grid_headers_ = std::move(headers);
      table_grid_row_.reset(); table_grid_column_.reset(); table_grid_description_.reset();
      table_grid_name_ = {}; table_grid_unit_ = {}; table_grid_value_ = {};
      table_grid_name_page_ = table_grid_unit_page_ = table_grid_value_page_ = 0;
      result_browser_error_.clear(); ++result_browser_generation_;
      if (!table_grid_page_->columns.empty()) { select_table_grid_cell(std::nullopt, table_grid_page_->columns.front()); }
      redraw();
    }
    catch (const std::exception &error) { result_browser_error_ = error.what(); redraw(); }
  }

  static std::optional<size_t> table_grid_coordinate(const std::string &text, const size_t count)
  {
    if (text.empty() || text.size() > 20 || !std::all_of(text.begin(), text.end(), [](const char ch) { return ch >= '0' && ch <= '9'; })) { return {}; }
    uint64_t value = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || value >= count) { return {}; }
    return size_t(value);
  }

  void table_grid_panel(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid,
                        const std::function<bool()> &same_view, const bool disabled)
  {
    if (!table_grid_ || !table_grid_page_) { return; }
    const auto grid = table_grid_; const auto page = table_grid_page_;
    const auto current = [this, valid, grid, page] { return valid() && result_grid_mode_ && table_grid_ == grid && table_grid_page_ == page; };
    // Text commits preserve the current field even if another installed window has
    // an active input. Only the explicit jump/navigation actions require all text idle.
    const auto editable = [this, same_view, grid, page] { return same_view() && result_grid_mode_ && table_grid_ == grid && table_grid_page_ == page; };
    // Independent field generations allow Tab/click to commit one field and focus
    // its sibling in the same frame; an older setter still cannot overwrite that
    // field's newer committed text. Every commit invalidates all captured Go actions.
    const auto jump_field = [this, editable](std::string *target, uint64_t *generation) {
      return ui::Binding<std::string>{[copy = *target] { return copy; },
          [this, editable, target, generation, expected = *generation](const std::string &value) {
        if (!editable() || *generation != expected || value.size() > 64) { return; }
        *target = value; ++*generation; table_grid_jump_error_.clear(); ++result_browser_generation_; redraw();
      }};
    };
    const bool input_blocked = !same_view() || !page->total_rows || !page->total_columns;
    layout.prop(ctx.tr("analysis_table_grid.source_row")).text_field("analysis_table_grid_jump_row", jump_field(&table_grid_jump_row_, &table_grid_jump_row_generation_), {.max_length = 64, .mono = true}).disable(input_blocked);
    layout.prop(ctx.tr("analysis_table_grid.source_column")).text_field("analysis_table_grid_jump_column", jump_field(&table_grid_jump_column_, &table_grid_jump_column_generation_), {.max_length = 64, .mono = true}).disable(input_blocked);
    layout.paragraph(ctx.tr("analysis_table_grid.jump_hint"));
    layout.button("analysis_table_grid_jump", ctx.tr("analysis_table_grid.jump"), [this, current, grid] {
      if (!current()) { return; }
      const auto row = table_grid_coordinate(table_grid_jump_row_, grid->row_count());
      const auto column = table_grid_coordinate(table_grid_jump_column_, grid->columns().size());
      if (!row || !column) {
        table_grid_jump_error_ = std::string(store_->tr("analysis_table_grid.jump_invalid"));
        ++result_browser_generation_; redraw(); return;
      }
      table_grid_jump_error_.clear(); set_table_grid_page(*row, *column);
      if (table_grid_page_ && table_grid_page_->row_offset == *row && table_grid_page_->column_offset == *column) { select_table_grid_cell(*row, *column); }
    }).disable(disabled || input_blocked);
    if (!table_grid_jump_error_.empty()) { layout.paragraph(table_grid_jump_error_); }
    hint(layout, ctx, "analysis_table_grid.hint");
    layout.paragraph(ctx.store.catalog().format("analysis_table_grid.range", {
        {"first", page->rows.empty() ? "—" : std::to_string(page->row_offset)},
        {"last", page->rows.empty() ? "—" : std::to_string(page->row_offset + page->rows.size() - 1)},
        {"total", std::to_string(page->total_rows)},
        {"first_column", page->columns.empty() ? "—" : std::to_string(page->column_offset)},
        {"last_column", page->columns.empty() ? "—" : std::to_string(page->columns.back())},
        {"columns", std::to_string(page->total_columns)}}));
    if (page->rows.empty()) { layout.paragraph(ctx.tr("analysis_table_grid.empty")); }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("analysis_table_grid.row")), 4, false}};
    for (const auto &title : table_grid_headers_) { spec.columns.push_back({title, 8, false}); }
    spec.rows = int(page->rows.size()); spec.visible_rows = float(std::max(1, std::min(6, spec.rows)));
    spec.data_version = result_browser_generation_;
    spec.cell = [page](int row, int column) {
      if (column == 0) { return std::to_string(page->row_offset + size_t(row)); }
      const auto &value = page->rows.at(size_t(row)).at(size_t(column - 1));
      return value.preview + (value.preview_truncated ? " …" : "");
    };
    const int selected = table_grid_row_ && *table_grid_row_ >= page->row_offset &&
        *table_grid_row_ - page->row_offset < page->rows.size() ? int(*table_grid_row_ - page->row_offset) : -1;
    spec.selected = {[selected] { return selected; }, [this, current, page](int row) {
      if (!current() || row < 0 || size_t(row) >= page->rows.size() || page->columns.empty()) { return; }
      select_table_grid_cell(page->row_offset + size_t(row), table_grid_column_.value_or(page->columns.front()));
    }};
    layout.table("analysis_table_grid", std::move(spec)).disable(disabled);
    auto &row_pages = layout.row();
    row_pages.button("analysis_table_grid_rows_previous", ctx.tr("analysis_table_grid.previous_rows"), [this, current, page] {
      if (current() && page->row_offset) { set_table_grid_page(page->row_offset >= 64 ? page->row_offset - 64 : 0, page->column_offset); }
    }).disable(disabled || page->row_offset == 0);
    row_pages.button("analysis_table_grid_rows_next", ctx.tr("analysis_table_grid.next_rows"), [this, current, page] {
      if (current() && page->next_row_offset) { set_table_grid_page(*page->next_row_offset, page->column_offset); }
    }).disable(disabled || !page->next_row_offset);
    auto &column_pages = layout.row();
    column_pages.button("analysis_table_grid_columns_previous", ctx.tr("analysis_table_grid.previous_columns"), [this, current, page] {
      if (current() && page->column_offset) { set_table_grid_page(page->row_offset, page->column_offset >= 8 ? page->column_offset - 8 : 0); }
    }).disable(disabled || page->column_offset == 0);
    column_pages.button("analysis_table_grid_columns_next", ctx.tr("analysis_table_grid.next_columns"), [this, current, page] {
      if (current() && page->next_column_offset) { set_table_grid_page(page->row_offset, *page->next_column_offset); }
    }).disable(disabled || !page->next_column_offset);
    std::vector<std::string> columns; int column_index = -1;
    for (size_t index = 0; index < page->columns.size(); ++index) {
      const auto &column = grid->columns()[page->columns[index]];
      columns.push_back(std::to_string(column.index) + " · " + column.label + (column.label_truncated ? " …" : ""));
      if (table_grid_column_ == page->columns[index]) { column_index = int(index); }
    }
    layout.prop(ctx.tr("analysis_table_grid.column")).dropdown("analysis_table_grid_column", std::move(columns),
        {[column_index] { return column_index; }, [this, current, page](int index) {
      if (current() && index >= 0 && size_t(index) < page->columns.size()) { select_table_grid_cell(table_grid_row_, page->columns[size_t(index)]); }
    }}).disable(disabled || page->columns.empty());
    if (!table_grid_column_) { return; }
    const auto &column = grid->columns()[*table_grid_column_];
    layout.label(ctx.store.catalog().format("analysis_table_grid.identity", {{"row", table_grid_row_ ? std::to_string(*table_grid_row_) : "—"},
        {"column", std::to_string(*table_grid_column_)}}));
    table_grid_text(layout, ctx, current, disabled, 0);
    if (!column.has_unit) { layout.paragraph(ctx.tr("analysis_table_grid.unit_missing")); }
    else { table_grid_text(layout, ctx, current, disabled, 1); }
    if (!table_grid_description_) { layout.paragraph(ctx.tr("analysis_table_grid.choose_row")); return; }
    layout.label(std::string(ctx.tr("analysis_results.exact")) + " · " + std::string(ctx.tr(result_type_key(table_grid_description_->type))));
    if (result_container(table_grid_description_->type)) { layout.paragraph(table_grid_description_->preview); }
    else { table_grid_text(layout, ctx, current, disabled, 2); }
    layout.button("analysis_table_grid_open_cell", ctx.tr("analysis_table_grid.open_cell"), [this, current, grid] {
      if (current() && table_grid_row_ && table_grid_column_) { browse_result(grid->cell_path(*table_grid_row_, *table_grid_column_)); }
    }).disable(disabled);
  }

  void table_grid_text(ui::Layout &layout, EditorContext &ctx, const std::function<bool()> &valid, const bool disabled, const int kind)
  {
    const auto &value = kind == 0 ? table_grid_name_ : kind == 1 ? table_grid_unit_ : table_grid_value_;
    auto &page = kind == 0 ? table_grid_name_page_ : kind == 1 ? table_grid_unit_page_ : table_grid_value_page_;
    if (value.pages.empty()) { return; }
    const std::string key = kind == 0 ? "analysis_table_grid_name" : kind == 1 ? "analysis_table_grid_unit" : "analysis_table_grid_value";
    if (kind < 2) { layout.label(ctx.tr(kind == 0 ? "analysis_table_grid.name" : "analysis_table_grid.unit")); }
    layout.scope(key).paragraph(value.pages.at(page));
    if (value.pages.size() <= 1) { return; }
    layout.label(ctx.store.catalog().format("analysis_results.text_page", {{"page", std::to_string(page + 1)},
        {"total", std::to_string(value.pages.size())}, {"bytes", std::to_string(value.total_bytes)}}));
    auto &buttons = layout.row();
    buttons.button(key + "_previous", ctx.tr("analysis_documents.previous"), [this, valid, kind] {
      if (!valid()) { return; }
      auto &index = kind == 0 ? table_grid_name_page_ : kind == 1 ? table_grid_unit_page_ : table_grid_value_page_;
      if (index) { --index; ++result_browser_generation_; redraw(); }
    }).disable(disabled || page == 0);
    buttons.button(key + "_next", ctx.tr("analysis_documents.next"), [this, valid, kind] {
      if (!valid()) { return; }
      auto &index = kind == 0 ? table_grid_name_page_ : kind == 1 ? table_grid_unit_page_ : table_grid_value_page_;
      const auto &text = kind == 0 ? table_grid_name_ : kind == 1 ? table_grid_unit_ : table_grid_value_;
      if (index + 1 < text.pages.size()) { ++index; ++result_browser_generation_; redraw(); }
    }).disable(disabled || page + 1 >= value.pages.size());
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
    hint(*panel, ctx, "analysis_documents.save_hint");
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
