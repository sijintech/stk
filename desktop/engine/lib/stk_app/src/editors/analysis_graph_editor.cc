/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
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
    const bool saved = state_->saved();
    layout.tabs("graph_mode", {std::string(ctx.tr("analysis_graph.desired")), std::string(ctx.tr("analysis_graph.displayed")),
        std::string(ctx.tr("analysis_documents.tab"))},
        {[displayed, saved] { return saved ? 2 : displayed ? 1 : 0; }, [this, weak](const int value) {
          if (const auto live = weak.lock(); live && *live && value >= 0 && value <= 2) {
            ++navigation_generation_;
            if (value == 2) { state_->show_saved(); }
            else { state_->show_displayed(value == 1); }
            redraw();
          }
        }});
    if (!state_->view()) {
      layout.paragraph(ctx.tr(saved ? "analysis_documents.no_document" :
          displayed ? "analysis_graph.no_displayed_graph" : "analysis_graph.no_desired_graph"));
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
        if (live && *live && value >= 0 && value <= 1) { saved_section_ = value; redraw(); }
      }});
      if (saved_section_ == 1) { runs_panel(layout, ctx); return; }
    }
    documents_panel(layout, ctx);
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
    return result;
  }
  bool load_state(const nlohmann::json &value) override
  {
    if (!value.is_object() || (value.contains("displayed") && !value.at("displayed").is_boolean()) ||
        (value.contains("saved") && !value.at("saved").is_boolean())) { return false; }
    initial_displayed_ = value.value("displayed", false);
    initial_saved_ = value.value("saved", false);
    if (state_) {
      state_->show_displayed(initial_displayed_);
      if (initial_saved_) { state_->show_saved(); }
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
  int saved_section_ = 0, snapshot_index_ = -1, file_index_ = -1, output_index_ = -1, mapping_index_ = -1;
  uint64_t runs_epoch_ = 0, run_selection_ = 0, bindings_generation_ = 0;
  std::string binding_name_ = "data", binding_path_, binding_error_;
  Json bindings_ = Json::object();
  AnalysisGraphCanvas canvas_;
  AppStore *store_ = nullptr;
  std::shared_ptr<const AnalysisGraphView> canvas_view_;
  std::optional<size_t> selected_;
  int selected_parameter_ = 0;
  bool fit_ = true, focus_selected_ = false, dragging_ = false, initial_displayed_ = false, initial_saved_ = false;
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
      if (initial_saved_) { state_->show_saved(); }
      documents_ = std::make_unique<ProjectAnalyses>(ctx.store);
      runs_ = std::make_unique<ProjectAnalysisRuns>(ctx.store);
    }
    documents_->sync();
    if (document_epoch_ != documents_->epoch()) {
      document_epoch_ = documents_->epoch(); document_name_.clear();
      state_->clear_document();
    }
    if (document_version_ != documents_->selected_version()) {
      document_version_ = documents_->selected_version();
      const auto &selected = documents_->selected();
      if (!selected.is_null()) {
        document_name_ = io::get_string(selected, "name");
        const bool activate = document_navigation_ == navigation_generation_;
        state_->clear_document();
        if (activate) { state_->show_saved(); }
        if (selected.at("state") == "readable") {
          state_->open_document(documents_->handle(), io::get_string(selected, "id"),
              documents_->selected_revision(), selected.at("document"), activate);
        }
      }
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
    if (state_->saved()) { return false; }
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
        if (!valid()) { return; }
        state_->sync();
        if (state_->saved() && state_->generation() == generation && bindings_generation_ == bindings_generation &&
            state_->document_id() == id && !state_->document_stale()) {
          runs_->prepare(id, revision, snapshot, bindings);
        }
      }).disable(blocked || runs_->uncertain() || id.empty() || state_->document_stale() || snapshot.empty() || bindings.empty());
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
    const auto run = runs_->run();
    if (run.is_null()) { return; }
    const auto id = io::get_string(run, "id"), status = io::get_string(run, "status");
    const auto selection = runs_->selection_generation();
    const auto same_run = [this, valid, id, selection] {
      return valid() && runs_->selection_generation() == selection && io::get_string(runs_->run(), "id") == id;
    };
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
    auto *shell = &ctx.area.shell(); auto *screen = ctx.area.screen();
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
        }}, {.max_length = 256}).disable(blocked);
    const auto generation = state_->generation();
    const auto *definition = state_->definition();
    const Json candidate = definition ? Json{{"format", "stk.analysis-document/1"}, {"graph", definition->graph},
        {"parameters", definition->parameters}, {"outputs", definition->requested_outputs}} : Json();
    panel->button("analysis_save", ctx.tr("analysis_documents.save_new"), [this, valid, generation, candidate] {
      if (!valid()) { return; }
      state_->sync();
      if (state_->generation() == generation && !candidate.is_null() && documents_->save_new(document_name_, candidate)) {
        document_navigation_ = navigation_generation_;
      }
    }).disable(blocked || documents_->uncertain() || candidate.is_null());
    if (!documents_->selected().is_null() && state_->saved()) {
      const auto selected_id = io::get_string(documents_->selected(), "id");
      panel->button("analysis_reload", ctx.tr("analysis_documents.reload"), [this, valid, selected_id] {
        if (valid() && io::get_string(documents_->selected(), "id") == selected_id && documents_->load(selected_id)) {
          document_navigation_ = navigation_generation_;
        }
      }).disable(blocked);
      panel->button("analysis_rename", ctx.tr("analysis_documents.rename"), [this, valid, selection_version] {
        if (valid() && documents_->selected_version() == selection_version && documents_->rename(document_name_)) {
          document_navigation_ = navigation_generation_;
        }
      }).disable(blocked || documents_->uncertain() || documents_->stale() ||
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
        if (valid() && row >= 0 && size_t(row) < rows.size() &&
            io::get_int(documents_->page(), "revision", -1) == revision &&
            io::get_int(documents_->page(), "offset", -1) == offset && documents_->load(io::get_string(rows[size_t(row)], "id"))) {
          document_navigation_ = navigation_generation_;
        }
      }};
      panel->table("analysis_documents", std::move(spec)).disable(blocked);
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
    auto *panel = layout.panel("graph_parameters", ctx.tr("analysis_graph.graph_parameters"), false);
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
        rows.push_back({text(it.key()), summary(it.value()), resolved});
      }
    }
    table(*panel, "graph_parameter_values", {{std::string(ctx.tr("analysis_graph.parameter")), 8},
        {std::string(ctx.tr("analysis_graph.submitted")), 10}, {std::string(ctx.tr("analysis_graph.resolved")), 10}},
        std::move(rows), state_->generation());
    if (parameters.size() > 64) { omitted(*panel, ctx, parameters.size() - 64); }
  }

  void outputs_panel(ui::Layout &layout, EditorContext &ctx)
  {
    auto *panel = layout.panel("graph_outputs", ctx.tr("analysis_graph.outputs"), false);
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
      rows.push_back({text(output.name), text(output.node + "." + output.port),
          std::string(ctx.tr(requested ? "analysis_graph.requested" : "analysis_graph.not_requested")), available});
    }
    table(*panel, "graph_output_rows", {{std::string(ctx.tr("analysis_graph.output")), 6},
        {std::string(ctx.tr("analysis_graph.port")), 10}, {std::string(ctx.tr("analysis_graph.request")), 9},
        {std::string(ctx.tr("analysis_graph.result")), 7}}, std::move(rows), state_->generation());
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
