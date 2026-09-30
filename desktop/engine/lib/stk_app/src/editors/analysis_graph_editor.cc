/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/ui/gpu_painter.hh"

#include <algorithm>
#include <cmath>

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
    const bool displayed = state_->displayed();
    const std::weak_ptr<bool> weak = alive_;
    layout.tabs("graph_mode", {std::string(ctx.tr("analysis_graph.desired")), std::string(ctx.tr("analysis_graph.displayed"))},
        {[displayed] { return displayed ? 1 : 0; }, [this, weak](const int value) {
          if (const auto live = weak.lock(); live && *live && (value == 0 || value == 1)) {
            state_->show_displayed(value == 1); redraw();
          }
        }});
    if (!state_->view()) {
      layout.paragraph(ctx.tr(displayed ? "analysis_graph.no_displayed_graph" : "analysis_graph.no_desired_graph"));
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

  nlohmann::json save_state() const override { return {{"displayed", state_ ? state_->displayed() : initial_displayed_}}; }
  bool load_state(const nlohmann::json &value) override
  {
    if (!value.is_object() || (value.contains("displayed") && !value.at("displayed").is_boolean())) { return false; }
    initial_displayed_ = value.value("displayed", false);
    if (state_) { state_->show_displayed(initial_displayed_); }
    return true;
  }

 private:
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::unique_ptr<AnalysisGraphState> state_;
  AnalysisGraphCanvas canvas_;
  AppStore *store_ = nullptr;
  std::shared_ptr<const AnalysisGraphView> canvas_view_;
  std::optional<size_t> selected_;
  int selected_parameter_ = 0;
  bool fit_ = true, focus_selected_ = false, dragging_ = false, initial_displayed_ = false;
  double last_x_ = 0, last_y_ = 0, ui_scale_ = 1;
  float canvas_top_ = 60;

  void redraw() { if (store_) { store_->changed(); } }
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
    if (!state_) {
      state_ = std::make_unique<AnalysisGraphState>(ctx.store.viewer());
      state_->show_displayed(initial_displayed_);
    }
    state_->sync();
    if (canvas_view_ != state_->view()) {
      canvas_view_ = state_->view();
      canvas_.set_view(canvas_view_);
      selected_ = canvas_view_ && !canvas_view_->nodes.empty() ? std::optional<size_t>(0) : std::nullopt;
      selected_parameter_ = 0; fit_ = true; focus_selected_ = false; dragging_ = false;
    }
  }

  bool result_corresponds() const
  {
    const auto &inspection = *state_->inspection();
    if (!inspection.shown_graph_verified.value_or(false)) { return false; }
    return state_->displayed() ? bool(inspection.shown_configuration) : inspection.shown_matches_desired.value_or(false);
  }

  void source_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("graph_source", ctx.tr("analysis_graph.source"), true);
    if (!panel) { return; }
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
    const auto &inspection = *state_->inspection();
    if (result_corresponds() && inspection.shown_result && inspection.shown_result->was_evaluated(node.id)) {
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
      const auto *configuration = state_->configuration();
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
    auto *panel = layout.panel("graph_parameters", ctx.tr("analysis_graph.graph_parameters"), false);
    if (!panel || !state_->configuration()) { return; }
    Rows rows;
    const auto &parameters = state_->configuration()->parameters;
    if (parameters.is_object()) {
      for (auto it = parameters.begin(); it != parameters.end() && rows.size() < 64; ++it) {
        std::string resolved;
        const auto &values = state_->inspection()->shown_resolved_parameters;
        if (result_corresponds() && values.is_object() && values.contains(it.key())) { resolved = summary(values.at(it.key())); }
        rows.push_back({text(it.key()), summary(it.value()), resolved});
      }
    }
    table(*panel, "graph_parameter_values", {{std::string(ctx.tr("analysis_graph.parameter")), 8},
        {std::string(ctx.tr("analysis_graph.submitted")), 10}, {std::string(ctx.tr("analysis_graph.resolved")), 10}},
        std::move(rows), state_->inspection()->version);
    if (parameters.size() > 64) { omitted(*panel, ctx, parameters.size() - 64); }
  }

  void outputs_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("graph_outputs", ctx.tr("analysis_graph.outputs"), false);
    if (!panel || !state_->configuration()) { return; }
    Rows rows;
    const auto &config = *state_->configuration();
    const auto &result = state_->inspection()->shown_result;
    for (const auto &output : state_->view()->outputs) {
      const bool requested = std::find(config.requested_outputs.begin(), config.requested_outputs.end(), output.name) != config.requested_outputs.end();
      std::string available = std::string(ctx.tr("analysis_graph.no_result"));
      if (result_corresponds() && result) {
        if (const auto *value = result->output(output.name)) { available = text(value->type); }
      }
      rows.push_back({text(output.name), text(output.node + "." + output.port),
          std::string(ctx.tr(requested ? "analysis_graph.requested" : "analysis_graph.not_requested")), available});
    }
    table(*panel, "graph_output_rows", {{std::string(ctx.tr("analysis_graph.output")), 6},
        {std::string(ctx.tr("analysis_graph.port")), 10}, {std::string(ctx.tr("analysis_graph.request")), 9},
        {std::string(ctx.tr("analysis_graph.result")), 7}}, std::move(rows), state_->inspection()->version);
    omitted(*panel, ctx, state_->view()->omitted_outputs);
    panel->paragraph(ctx.tr("analysis_graph.no_fetch"));
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
