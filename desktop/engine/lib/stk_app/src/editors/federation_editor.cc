/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/federation_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/shell.hh"
#include "stk/core/sha256.hh"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <map>
#include <set>

namespace stk::app {
namespace {
using io::Json;
constexpr size_t kMaxRows = 1000;
std::string short_id(const std::string &value)
{
  return value.size() <= 20 ? value : value.substr(0, 8) + "…" + value.substr(value.size() - 8);
}
std::optional<double> number(const std::string &text, double low, double high)
{
  double value = 0; const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
  return parsed.ec == std::errc() && parsed.ptr == text.data() + text.size() && std::isfinite(value) && value >= low && value <= high ?
      std::optional<double>(value) : std::nullopt;
}
std::optional<int64_t> integer(const std::string &text, int64_t low, int64_t high)
{
  int64_t value = 0; const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
  return parsed.ec == std::errc() && parsed.ptr == text.data() + text.size() && value >= low && value <= high ?
      std::optional<int64_t>(value) : std::nullopt;
}
class FederationEditor final : public Editor {
 public:
  explicit FederationEditor(const EditorType &type) : Editor(type)
  {
    static uint64_t identity = 0; scope_ = "federation-instance-" + std::to_string(++identity);
    text_ = defaults();
  }
  bool has_unsaved_changes() const override
  {
    return dirty_ || text_ != defaults() || !thresholds_.empty() || dtype_ != 1 || strategy_ != 0 ||
      (ui_ && ui_->edit_state() && fields_.contains(ui_->editing()));
  }
  bool can_change_project_selection(std::string_view) const override { return !has_unsaved_changes(); }
  void on_area_removed() override
  {
    text_ = saved_text(); thresholds_ = saved_thresholds(); if (state_ && view_) { state_->detach(view_); }
    ui_ = nullptr; fields_.clear(); ++generation_;
  }
  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx);
    row.button("federation_connections", ctx.tr("federation.connections"), [this, live = guard()] {
      if (live()) { state_->load_connections(view_); }
    }).width(5).disable(view_->busy());
  }
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx); ui_ = ctx.ui; fields_.clear();
    auto &body = layout.scope(scope_);
    if (!state_->supported()) { body.paragraph(ctx.tr("federation.unsupported")); return; }
    body.paragraph(ctx.tr("federation.intro"));
    connection(body, ctx);
    body.tabs("federation_sections", {std::string(ctx.tr("federation.data")), std::string(ctx.tr("federation.consent")),
        std::string(ctx.tr("federation.evaluation"))}, {[this] { return section_; }, [this, live = guard()](int value) {
          if (live() && value >= 0 && value <= 2) { section_ = value; }
        }});
    if (!error_.empty()) { body.paragraph(ctx.tr(error_)); }
    if (!view_->error.empty()) { body.paragraph(view_->error.starts_with("federation.") ? std::string(ctx.tr(view_->error)) : view_->error); }
    if (view_->busy()) { body.label(ctx.tr("federation.busy")); }
    if (view_->uncertain) { body.paragraph(ctx.tr("federation.uncertain")); }
    recovery(body, ctx);
    if (section_ == 0) { data(body, ctx); }
    else if (section_ == 1) { consent(body, ctx); }
    else { evaluation(body, ctx); }
  }
  nlohmann::json save_state() const override { return {{"version", 1}, {"section", section_}}; }
  bool load_state(const nlohmann::json &state) override
  {
    const Json value = state;
    if (!value.is_object() || value.size() > 2 || (value.contains("version") && value.at("version") != 1) ||
        (value.contains("section") && (!value.at("section").is_number_integer() || io::get_int(value, "section", -1) < 0 || io::get_int(value, "section", -1) > 2))) { return false; }
    for (auto it = value.begin(); it != value.end(); ++it) { if (it.key() != "version" && it.key() != "section") { return false; } }
    section_ = int(io::get_int(value, "section", 0)); return true;
  }
  nlohmann::json save_workspace_state() const override
  {
    return {{"version", 1}, {"section", section_}, {"text", saved_text()}, {"source_project", source_project_},
      {"source_revision", source_revision_}, {"table_id", table_id_}, {"features", features_}, {"targets", targets_},
      {"roles", roles_}, {"thresholds", saved_thresholds()}, {"dtype", dtype_}, {"strategy", strategy_}};
  }
  bool load_workspace_state(const nlohmann::json &state) override
  {
    const Json value = state;
    if (!value.is_object() || value.dump().size() > 256 * 1024) { return false; }
    const std::set<std::string> allowed = {"version", "section", "text", "source_project", "source_revision", "table_id", "features", "targets", "roles", "thresholds", "dtype", "strategy"};
    for (auto it = value.begin(); it != value.end(); ++it) { if (!allowed.contains(it.key())) { return false; } }
    if ((value.contains("version") && value.at("version") != 1) ||
        (value.contains("section") && (!value.at("section").is_number_integer() || io::get_int(value, "section", -1) < 0 || io::get_int(value, "section", -1) > 2)) ||
        (value.contains("source_revision") && (!value.at("source_revision").is_number_integer() || io::get_int(value, "source_revision", -2) < -1))) { return false; }
    for (const auto key : {"dtype", "strategy"}) {
      if (value.contains(key) && (!value.at(key).is_number_integer() || io::get_int(value, key, -1) < 0 || io::get_int(value, key, -1) > 1)) { return false; }
    }
    for (const auto key : {"source_project", "table_id"}) {
      if (value.contains(key) && (!value.at(key).is_string() || value.at(key).get_ref<const std::string &>().size() > 36)) { return false; }
    }
    auto valid_list = [&](const char *key, size_t maximum) {
      if (!value.contains(key)) { return true; }
      const auto &list = value.at(key); if (!list.is_array() || list.size() > maximum) { return false; }
      std::set<std::string> seen;
      for (const auto &item : list) { if (!item.is_string() || item.get_ref<const std::string &>().size() > 36 || !seen.insert(item.get<std::string>()).second) { return false; } }
      return true;
    };
    if (!valid_list("features", 64) || !valid_list("targets", 16)) { return false; }
    if (value.contains("text")) {
      if (!value.at("text").is_object() || value.at("text").size() > defaults().size()) { return false; }
      for (auto it = value.at("text").begin(); it != value.at("text").end(); ++it) {
        if (!defaults().contains(it.key()) || !it.value().is_string() || it.value().get_ref<const std::string &>().size() > 128 ||
            it.value().get_ref<const std::string &>().find('\0') != std::string::npos) { return false; }
      }
    }
    if (value.contains("roles")) {
      if (!value.at("roles").is_object() || value.at("roles").size() > kMaxRows) { return false; }
      for (auto it = value.at("roles").begin(); it != value.at("roles").end(); ++it) {
        if (it.key().size() > 36 || !it.value().is_number_integer() || it.value().get<int64_t>() < 1 || it.value().get<int64_t>() > 2) { return false; }
      }
    }
    if (value.contains("thresholds")) {
      if (!value.at("thresholds").is_object() || value.at("thresholds").size() > 16) { return false; }
      for (auto it = value.at("thresholds").begin(); it != value.at("thresholds").end(); ++it) {
        if (it.key().size() > 128 || !it.value().is_string() || it.value().get_ref<const std::string &>().size() > 128 ||
            it.value().get_ref<const std::string &>().find('\0') != std::string::npos) { return false; }
      }
    }
    if (state_ && view_) { state_->detach(view_); state_->invalidate_draft(view_, true); }
    ui_ = nullptr; fields_.clear(); ++generation_;
    text_ = defaults(); if (value.contains("text")) { for (auto it = value.at("text").begin(); it != value.at("text").end(); ++it) { text_[it.key()] = it.value().get<std::string>(); } }
    section_ = int(io::get_int(value, "section", 0)); source_project_ = io::get_string(value, "source_project");
    dtype_ = int(io::get_int(value, "dtype", 1)); strategy_ = int(io::get_int(value, "strategy", 0));
    source_revision_ = io::get_int(value, "source_revision", -1); table_id_ = io::get_string(value, "table_id");
    features_ = value.value("features", std::vector<std::string>()); targets_ = value.value("targets", std::vector<std::string>());
    roles_ = value.value("roles", std::map<std::string, int>()); thresholds_ = value.value("thresholds", std::map<std::string, std::string>());
    dirty_ = !source_project_.empty() || !table_id_.empty() || !features_.empty() || !targets_.empty() || !roles_.empty() || !thresholds_.empty() || text_ != defaults();
    return true;
  }
 private:
  FederationState *state_ = nullptr; FederationState::ViewPtr view_;
  AppStore *store_ = nullptr; EditorArea *area_ = nullptr; ui::Context *ui_ = nullptr;
  std::weak_ptr<void> shell_; std::map<ui::WidgetId, std::string> fields_;
  std::map<std::string, std::string> text_, thresholds_;
  std::map<std::string, int> roles_; std::vector<std::string> features_, targets_;
  std::string scope_, source_project_, table_id_, error_, grant_id_, selected_version_;
  int64_t source_revision_ = -1; int section_ = 0, dtype_ = 1, strategy_ = 0;
  uint64_t generation_ = 0; bool dirty_ = false;
  static std::map<std::string, std::string> defaults()
  {
    return {{"run_id", ""}, {"coordinator_id", ""}, {"participant_id", ""}, {"max_rounds", "1"},
      {"steps", "20"}, {"learning_rate", "0.01"}, {"proximal_mu", ""}, {"round", "1"}};
  }
  std::map<std::string, std::string> saved_text() const
  {
    auto values = text_;
    if (ui_ && ui_->edit_state()) { const auto found = fields_.find(ui_->editing()); if (found != fields_.end() && values.contains(found->second)) { values[found->second] = ui_->edit_state()->text(); } }
    return values;
  }
  std::map<std::string, std::string> saved_thresholds() const
  {
    auto values = thresholds_;
    if (ui_ && ui_->edit_state()) {
      const auto found = fields_.find(ui_->editing());
      if (found != fields_.end() && found->second.starts_with("threshold/")) { values[found->second.substr(10)] = ui_->edit_state()->text(); }
    }
    return values;
  }
  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store; area_ = &ctx.area; shell_ = ctx.area.shell().lifetime();
    if (!state_) { state_ = &ctx.store.federation(); view_ = state_->new_view(); }
    state_->sync(view_);
  }
  std::function<bool()> guard(const bool draft = false) const
  {
    const auto weak = lifetime(); const auto shell = shell_; const auto generation = generation_, origin = view_ ? view_->lifetime_epoch : 0,
      source = view_ ? view_->draft_epoch : 0, selection = view_ ? view_->selection_epoch : 0,
      bridge = store_ ? store_->bridge_epoch() : 0, project = store_ ? store_->project_scope_epoch() : 0;
    const auto area = area_;
    return [this, weak, shell, generation, origin, source, selection, bridge, project, area, draft] {
      return !weak.expired() && !shell.expired() && store_ && area && area_ == area && &area->editor() == this && view_ &&
        generation == generation_ && view_->lifetime_epoch == origin && view_->selection_epoch == selection && store_->bridge_epoch() == bridge &&
        store_->project_scope_epoch() == project && (!draft || view_->draft_epoch == source);
    };
  }
  void changed(const bool data = false)
  {
    dirty_ = true; error_.clear(); state_->invalidate_draft(view_, data); store_->changed();
  }
  void field(ui::Layout &body, EditorContext &ctx, const std::string &key, const char *label)
  {
    auto &widget = body.prop(ctx.tr(label)).text_field("federation_" + key,
      {[this, key] { return text_.at(key); }, [this, key, live = guard()](std::string value) {
        if (live() && !view_->busy() && value != text_[key]) {
          text_[key] = std::move(value);
          if (key == "run_id" || key == "round") { view_->candidate = view_->evaluation = view_->models = nullptr; ++view_->selection_epoch; }
          changed();
        }
      }}, {.max_length = 128});
    widget.disable(view_->busy()); fields_[widget.id] = key;
  }
  void connection(ui::Layout &body, EditorContext &ctx)
  {
    std::vector<std::string> ids, names;
    for (const auto &row : view_->connections) { ids.push_back(io::get_string(row, "id")); names.push_back(io::get_string(row, "name", io::get_string(row, "id"))); }
    body.prop(ctx.tr("federation.connection")).dropdown("federation_connection", names,
      {[ids, id = view_->connection] { const auto it = std::find(ids.begin(), ids.end(), id); return it == ids.end() ? -1 : int(it - ids.begin()); },
       [this, ids, live = guard()](int index) { if (live() && index >= 0 && size_t(index) < ids.size()) { state_->set_connection(view_, ids[size_t(index)]); } }}).disable(view_->busy() || view_->uncertain);
    body.button("federation_owner_info", ctx.tr("federation.owner_info"), [this, live = guard()] { if (live()) { state_->read(view_, "info"); } }).disable(view_->connection.empty() || view_->busy());
    if (view_->info.is_object()) {
      body.label(std::string(ctx.tr("federation.owner")) + ": " + short_id(io::get_string(view_->info, "owner_id")) +
        " · " + std::string(ctx.tr("federation.generation")) + " " + std::to_string(io::get_int(view_->info, "generation", 0)));
    }
  }
  void recovery(ui::Layout &body, EditorContext &ctx)
  {
    auto &row = body.row();
    row.button("federation_local_operations", ctx.tr("federation.previous_operations"), [this, live = guard()] {
      if (live()) { state_->read(view_, "operations.local", {{"offset", 0}, {"limit", 20}}); }
    }).disable(view_->connection.empty() || view_->busy());
    row.button("federation_discard_forms", ctx.tr("federation.discard_forms"), [this, live = guard()] {
      if (live() && !view_->busy() && !view_->uncertain) {
        text_ = defaults(); dtype_ = 1; strategy_ = 0; reset_selection();
        view_->candidate = view_->evaluation = view_->models = nullptr; ++view_->selection_epoch;
      }
    }).disable(view_->busy() || view_->uncertain || !has_unsaved_changes());
    if (!view_->operation_id.empty()) {
      row.button("federation_check_operation", ctx.tr("federation.check_operation"), [this, live = guard()] { if (live()) { state_->check_operation(view_); } }).disable(view_->busy());
      if (view_->uncertain) { row.button("federation_recover_operation", ctx.tr("federation.recover_operation"), [this, live = guard()] { if (live()) { state_->recover_operation(view_); } }).disable(view_->busy() || !view_->info.is_object() || view_->operation_method == "operations.recover"); }
      body.label(short_id(view_->operation_id) + " · " + view_->operation_method);
      if (view_->rejection.is_object() && view_->error != "federation.rejected") { body.paragraph(ctx.tr("federation.rejected")); }
    }
    for (const auto &item : view_->local_operations) {
      const auto id = io::get_string(item, "operation_id");
      body.button("federation_operation/" + id, short_id(id) + " · " + io::get_string(item, "method") + " · " + std::string(ctx.tr("federation.state." + io::get_string(item, "state"))),
        [this, item, live = guard()] { if (live()) { state_->select_operation(view_, item); } }).disable(view_->busy() || view_->uncertain);
    }
  }
  bool source_matches() const
  {
    const auto &project = store_->project().project();
    return project && project->id == source_project_ && project->revision == source_revision_ && state_->source_current(view_) && table_id_ == view_->table_id;
  }
  void reset_selection()
  {
    const auto &project = store_->project().project();
    source_project_ = project ? project->id : ""; source_revision_ = project ? project->revision : -1;
    features_.clear(); targets_.clear(); roles_.clear(); thresholds_.clear();
    state_->invalidate_draft(view_, true); dirty_ = false; ++generation_;
  }
  void data(ui::Layout &body, EditorContext &ctx)
  {
    auto &project = store_->project();
    if (!project.loaded() || !project.project()) { body.paragraph(ctx.tr("federation.open_project")); return; }
    std::vector<std::string> ids, names;
    for (const auto &table : project.tables()) { ids.push_back(table.id); names.push_back(table.name); }
    body.prop(ctx.tr("federation.table")).dropdown("federation_table", names,
      {[ids, selected = table_id_] { const auto it = std::find(ids.begin(), ids.end(), selected); return it == ids.end() ? -1 : int(it - ids.begin()); },
       [this, ids, live = guard()](int index) { if (live() && !view_->busy() && index >= 0 && size_t(index) < ids.size() && !dirty_) { table_id_ = ids[size_t(index)]; reset_selection(); } }}).disable(view_->busy() || dirty_);
    const bool same_draft_source = project.project()->id == source_project_ && project.project()->revision == source_revision_;
    auto &read = body.row();
    read.button("federation_load_table", ctx.tr("federation.load_table"), [this, live = guard()] {
      if (live() && !table_id_.empty()) {
        const auto &project = store_->project().project();
        if (project && (project->id != source_project_ || project->revision != source_revision_)) { reset_selection(); }
        state_->load_rows(view_, table_id_, 0);
      }
    }).disable(view_->busy() || table_id_.empty() || (dirty_ && !same_draft_source));
    read.button("federation_discard_draft", ctx.tr("federation.discard_draft"), [this, live = guard()] { if (live() && !view_->busy()) { reset_selection(); } }).disable(view_->busy() || !dirty_);
    read.button("federation_saved_plans", ctx.tr("federation.saved_plans"), [this, live = guard()] { if (live()) { state_->load_plans(view_); } }).disable(view_->busy());
    for (const auto &plan : view_->plans) {
      const auto id = io::get_string(plan, "plan_id");
      body.button("federation_plan/" + id, short_id(id), [this, id, live = guard()] { if (live()) { state_->load_plan(view_, id); } }).disable(view_->busy() || dirty_ || view_->plan_uncertain);
    }
    if (!view_->table.is_object()) { body.paragraph(ctx.tr("federation.select_data")); show_plan(body, ctx); return; }
    if (!source_matches()) { body.paragraph(ctx.tr("federation.stale_source")); show_plan(body, ctx); return; }
    body.paragraph(ctx.tr("federation.numeric_hint"));
    for (const auto &item : view_->table.at("fields")) {
      const auto id = io::get_string(item, "id"), type = io::get_string(item, "type");
      if (type != "number" && type != "integer") { continue; }
      auto &row = body.row();
      row.label(io::get_string(item, "name") + " [" + io::get_string(item, "unit", "unspecified") + "]");
      choose(row, ctx, features_, id, "feature"); choose(row, ctx, targets_, id, "target");
    }
    body.label(std::string(ctx.tr("federation.rows")) + " " + std::to_string(view_->row_offset + 1) + "–" +
      std::to_string(std::min(view_->row_total, view_->row_offset + int64_t(view_->table.at("records").size()))) + " / " + std::to_string(view_->row_total));
    for (const auto &record : view_->table.at("records")) {
      const auto id = io::get_string(record, "id"); auto &row = body.row();
      row.label(short_id(id));
      for (int role = 1; role <= 2; ++role) {
        row.checkbox("federation_row/" + id + "/" + std::to_string(role), ctx.tr(role == 1 ? "federation.training" : "federation.holdout"),
          {[this, id, role] { const auto it = roles_.find(id); return it != roles_.end() && it->second == role; },
           [this, id, role, live = guard()](bool value) {
             if (!live() || view_->busy() || view_->plan_uncertain || (!roles_.contains(id) && roles_.size() >= kMaxRows)) { return; }
             if (value) { roles_[id] = role; } else { roles_.erase(id); } changed(true);
           }}).disable(view_->busy() || view_->plan_uncertain);
      }
    }
    auto &pages = body.row();
    pages.button("federation_rows_previous", ctx.tr("federation.previous"), [this, live = guard()] { if (live()) { state_->load_rows(view_, table_id_, std::max<int64_t>(0, view_->row_offset - 20)); } }).disable(view_->busy() || view_->row_offset == 0);
    pages.button("federation_rows_next", ctx.tr("federation.next"), [this, live = guard()] { if (live()) { state_->load_rows(view_, table_id_, view_->row_offset + 20); } }).disable(view_->busy() || view_->row_offset + 20 >= view_->row_total);
    std::vector<std::string> training, holdout;
    for (const auto &[id, role] : roles_) { (role == 1 ? training : holdout).push_back(id); }
    body.label(std::string(ctx.tr("federation.training")) + " " + std::to_string(training.size()) + " · " +
      std::string(ctx.tr("federation.holdout")) + " " + std::to_string(holdout.size()));
    body.button("federation_prepare", ctx.tr("federation.prepare"), [this, training, holdout, live = guard(true)] {
      if (!live() || !source_matches()) { return; }
      const auto &project = *store_->project().project();
      state_->prepare(view_, {{"handle", project.handle}, {"expected_revision", project.revision}, {"table_id", table_id_},
        {"plan_id", FederationState::new_uuid()}, {"training_dataset_id", FederationState::new_uuid()}, {"holdout_dataset_id", FederationState::new_uuid()},
        {"feature_ids", features_}, {"target_ids", targets_}, {"training_rows", training}, {"holdout_rows", holdout}});
    }).disable(view_->busy() || view_->uncertain || view_->plan_uncertain || features_.empty() || targets_.empty() || training.empty() || holdout.empty());
    if (view_->plan_uncertain) {
      body.paragraph(ctx.tr("federation.plan_uncertain"));
      body.button("federation_check_plan", ctx.tr("federation.check_plan"), [this, live = guard()] { if (live()) { state_->load_plan(view_, view_->plan_id); } }).disable(view_->busy());
    }
    show_plan(body, ctx);
  }
  void choose(ui::Layout &row, EditorContext &ctx, std::vector<std::string> &selected, const std::string &id, const char *role)
  {
    row.checkbox("federation_" + std::string(role) + "/" + id, ctx.tr("federation." + std::string(role)),
      {[&selected, id] { return std::find(selected.begin(), selected.end(), id) != selected.end(); },
       [this, &selected, id, role = std::string(role), live = guard()](bool value) {
         if (!live() || view_->busy() || view_->plan_uncertain) { return; }
         auto &other = role == "feature" ? targets_ : features_;
         if (value && selected.size() < (role == "feature" ? 64 : 16)) {
           if (std::find(selected.begin(), selected.end(), id) == selected.end()) { selected.push_back(id); }
           std::erase(other, id);
         }
         else if (!value) { std::erase(selected, id); }
         changed(true);
       }}).disable(view_->busy() || view_->plan_uncertain);
  }
  void show_plan(ui::Layout &body, EditorContext &ctx)
  {
    if (!view_->plan.is_object()) { return; }
    const auto &plan = view_->plan;
    body.separator(); body.label(ctx.tr("federation.frozen_card"));
    const auto &source = plan.at("source");
    body.label(short_id(io::get_string(source, "project_id")) + " · " + short_id(io::get_string(source, "table_id")) + " · " +
      std::to_string(io::get_int(source, "revision", 0)));
    for (const auto role : {"features", "targets"}) {
      std::string fields = std::string(ctx.tr(role == std::string("features") ? "federation.feature" : "federation.target")) + ": ";
      for (const auto &field : source.at(role)) { if (fields.back() != ' ') { fields += ", "; } fields += io::get_string(field, "name") + " [" + io::get_string(field, "unit") + "]"; }
      body.paragraph(fields);
    }
    body.paragraph(io::get_string(plan, "source_sha256"));
    for (const auto &dataset : plan.at("datasets")) {
      const auto &manifest = dataset.at("manifest");
      body.label(std::string(ctx.tr("federation." + io::get_string(dataset, "role"))) + " · " +
        std::to_string(io::get_int(manifest, "num_examples", 0)) + " · " + short_id(io::get_string(manifest, "dataset_id")));
      body.paragraph(io::get_string(manifest, "dataset_sha256"));
    }
    body.label(std::to_string(io::get_int(plan, "bytes", 0)) + " bytes");
    body.button("federation_register", ctx.tr("federation.register"), [this, live = guard(true)] { if (live()) { state_->register_plan(view_); } }).disable(
      view_->busy() || view_->uncertain || view_->plan_uncertain || !view_->info.is_object() || !state_->source_current(view_) ||
      (store_->project().project() && io::get_int(plan.at("source"), "revision", -1) != store_->project().project()->revision));
    if (view_->registration.is_object()) { body.paragraph(ctx.tr("federation.registered")); }
  }
  Json training_spec() const
  {
    if (!view_->plan.is_object()) { return nullptr; }
    const auto steps = integer(text_.at("steps"), 1, 1000);
    const auto rate = number(text_.at("learning_rate"), 1e-300, 1);
    const auto mu = strategy_ == 0 ? std::optional<double>(0) : number(text_.at("proximal_mu"), 1e-300, 100);
    if (!steps || !rate || !mu) { return nullptr; }
    Json features = Json::array(), targets = Json::array();
    const auto &source = view_->registration.is_object() ? view_->registration.at("source") : view_->plan.at("source");
    for (const auto &field : source.at("features")) { features.push_back({{"name", field.at("name")}, {"unit", field.at("unit")}}); }
    for (const auto &field : source.at("targets")) { targets.push_back({{"name", field.at("name")}, {"unit", field.at("unit")}}); }
    return {{"format", "stk.federation-training-spec/1"}, {"trainer", "linear-regression/1"}, {"features", features}, {"targets", targets},
      {"dtype", dtype_ == 0 ? "f32" : "f64"}, {"normalization", "none"}, {"steps", *steps}, {"learning_rate", *rate},
      {"strategy", strategy_ == 0 ? "fedavg" : "fedprox"}, {"proximal_mu", *mu}};
  }
  const Json *dataset(const std::string &role) const
  {
    if (!view_->registration.is_object() || !view_->registration.contains("datasets")) { return nullptr; }
    for (const auto &item : view_->registration.at("datasets")) { if (io::get_string(item, "role") == role) { return &item.at("manifest"); } }
    return nullptr;
  }
  void consent(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("federation.consent_hint"));
    field(body, ctx, "run_id", "federation.run"); field(body, ctx, "coordinator_id", "federation.coordinator");
    field(body, ctx, "participant_id", "federation.participant"); field(body, ctx, "max_rounds", "federation.max_rounds");
    field(body, ctx, "steps", "federation.steps"); field(body, ctx, "learning_rate", "federation.learning_rate");
    body.prop(ctx.tr("federation.dtype")).dropdown("federation_dtype", {"f32", "f64"}, {[this] { return dtype_; }, [this, live = guard()](int value) { if (live() && !view_->busy() && value >= 0 && value <= 1) { dtype_ = value; changed(); } }}).disable(view_->busy());
    body.prop(ctx.tr("federation.strategy")).dropdown("federation_strategy", {"FedAvg", "FedProx"}, {[this] { return strategy_; }, [this, live = guard()](int value) { if (live() && !view_->busy() && value >= 0 && value <= 1) { strategy_ = value; changed(); } }}).disable(view_->busy());
    if (strategy_ == 1) { field(body, ctx, "proximal_mu", "federation.proximal_mu"); }
    const auto spec = training_spec(); const auto rounds = integer(text_.at("max_rounds"), 1, 1000); const auto *training = dataset("training");
    body.button("federation_approve", ctx.tr("federation.approve"), [this, spec, rounds, live = guard(true)] {
      if (!live() || !rounds || !dataset("training")) { return; }
      state_->write(view_, "grants.approve", {{"dataset_id", dataset("training")->at("dataset_id")},
        {"dataset_sha256", dataset("training")->at("dataset_sha256")}, {"source_sha256", view_->registration.at("source_sha256")},
        {"spec", spec}, {"run_id", text_.at("run_id")}, {"coordinator_id", text_.at("coordinator_id")},
        {"participant_id", text_.at("participant_id")}, {"max_rounds", *rounds}});
    }).disable(view_->busy() || view_->uncertain || !view_->info.is_object() || !training || spec.is_null() || !rounds ||
      !canonical_uuid(text_.at("run_id")) || !core::is_sha256_hex(text_.at("coordinator_id")) || !core::is_sha256_hex(text_.at("participant_id")));
    auto &read = body.row();
    read.button("federation_grants", ctx.tr("federation.grants"), [this, live = guard()] { if (live()) { state_->read(view_, "grants.list", {{"offset", 0}, {"limit", 20}}); } }).disable(view_->busy() || view_->connection.empty());
    read.button("federation_audit", ctx.tr("federation.audit"), [this, live = guard()] { if (live()) { state_->read(view_, "audit.list", {{"offset", 0}, {"limit", 20}}); } }).disable(view_->busy() || view_->connection.empty());
    if (view_->grants.is_object()) { for (const auto &grant : view_->grants.at("items")) {
      const auto id = io::get_string(grant, "grant_id"); auto &row = body.row();
      row.label(short_id(id) + " · " + short_id(io::get_string(grant, "run_id")) + " · " + std::to_string(io::get_int(grant, "max_rounds", 0)));
      row.button("federation_revoke/" + id, ctx.tr("federation.revoke"), [this, id, live = guard()] { if (live()) { state_->write(view_, "grants.revoke", {{"grant_id", id}}); } }).disable(view_->busy() || view_->uncertain || !grant.value("active", false));
    } }
    if (view_->audit.is_object()) { for (const auto &item : view_->audit.at("items")) {
      body.paragraph(short_id(io::get_string(item, "update_id")) + " · " + std::to_string(io::get_int(item, "round", 0)) + " · " + std::string(ctx.tr("federation.state." + io::get_string(item, "state"))));
      body.paragraph(io::get_string(item, "model_sha256"));
      if (item.contains("metadata") && item.at("metadata").is_object()) {
        const auto &metadata = item.at("metadata");
        body.label(std::string(ctx.tr("federation.examples")) + " " + std::to_string(io::get_int(metadata, "num_examples", 0)) +
          " · " + std::to_string(io::get_int(metadata, "update_bytes", 0)) + " bytes");
        body.paragraph(io::get_string(metadata, "update_sha256"));
      }
    } }
  }
  void evaluation(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("federation.evaluation_hint"));
    field(body, ctx, "run_id", "federation.run"); field(body, ctx, "round", "federation.round");
    const auto round = integer(text_.at("round"), 1, 1000);
    body.button("federation_candidate", ctx.tr("federation.candidate"), [this, round, live = guard(true)] {
      if (live() && round) { state_->read(view_, "candidates.get", {{"run_id", text_.at("run_id")}, {"round", *round}}); }
    }).disable(view_->busy() || view_->connection.empty() || !canonical_uuid(text_.at("run_id")) || !round);
    if (!view_->candidate.is_object()) { return; }
    const auto candidate = view_->candidate; const auto spec_sha = io::get_string(candidate, "spec_sha256");
    body.paragraph(io::get_string(candidate.at("model"), "sha256"));
    body.label(std::string(ctx.tr("federation.examples")) + " " + std::to_string(io::get_int(candidate, "num_examples", 0)));
    body.button("federation_models", ctx.tr("federation.versions"), [this, spec_sha, live = guard()] { if (live()) { state_->read(view_, "models.list", {{"spec_sha256", spec_sha}}); } }).disable(view_->busy());
    Json thresholds = Json::array(); bool valid_thresholds = true;
    for (const auto &target : candidate.at("spec").at("targets")) {
      const auto name = io::get_string(target, "name"), unit = io::get_string(target, "unit"); thresholds_.try_emplace(name);
      auto &widget = body.prop(name + " [" + unit + "] RMSE ≤").text_field("federation_threshold/" + name,
        {[this, name] { return thresholds_.at(name); }, [this, name, live = guard()](std::string value) {
          if (live() && !view_->busy() && thresholds_.at(name) != value) {
            thresholds_[name] = std::move(value); view_->evaluation = nullptr; ++view_->selection_epoch; changed();
          }
        }}, {.max_length = 128});
      widget.disable(view_->busy()); fields_[widget.id] = "threshold/" + name;
      const auto maximum = number(thresholds_[name], 0, 1e300); valid_thresholds = valid_thresholds && bool(maximum);
      if (maximum) { thresholds.push_back({{"name", name}, {"unit", unit}, {"max_rmse", *maximum}}); }
    }
    const auto *heldout = dataset("holdout"); const bool model_source = view_->models.is_object() && io::get_string(view_->models, "spec_sha256") == spec_sha && view_->models.contains("versions");
    body.button("federation_prepare_evaluation", ctx.tr("federation.prepare_evaluation"), [this, candidate, thresholds, live = guard(true)] {
      if (!live() || !dataset("holdout") || !view_->models.is_object()) { return; }
      state_->write(view_, "evaluations.prepare", {{"evaluation_id", FederationState::new_uuid()}, {"run_id", candidate.at("run_id")}, {"round", candidate.at("round")},
        {"dataset_id", dataset("holdout")->at("dataset_id")}, {"dataset_sha256", dataset("holdout")->at("dataset_sha256")},
        {"candidate_sha256", candidate.at("model").at("sha256")}, {"base_model_sha256", candidate.at("base_model").at("sha256")},
        {"spec_sha256", candidate.at("spec_sha256")}, {"thresholds", thresholds},
        {"expected_active_version", view_->models.at("active_version")}, {"expected_active_generation", view_->models.at("generation")}});
    }).disable(view_->busy() || view_->uncertain || !heldout || !valid_thresholds || !model_source || !view_->info.is_object());
    if (view_->evaluation.is_object()) {
      const auto eval = view_->evaluation; const auto state = io::get_string(eval, "state");
      body.label(std::string(ctx.tr("federation.state." + state)) + " · " + short_id(io::get_string(eval, "evaluation_id")));
      if (state == "prepared") { body.button("federation_evaluate", ctx.tr("federation.evaluate"), [this, eval, live = guard()] {
        if (live()) { state_->write(view_, "evaluations.evaluate", {{"evaluation_id", eval.at("evaluation_id")}, {"plan_sha256", eval.at("plan_sha256")}}); }
      }).disable(view_->busy() || view_->uncertain); }
      if (eval.contains("metrics") && eval.at("metrics").is_object()) {
        for (const auto role : {"candidate", "base", "baseline"}) {
          const auto rows = eval.at("metrics").value(role, Json::array());
          if (!rows.is_array() || rows.empty()) { continue; }
          body.label(ctx.tr("federation.metric." + std::string(role)));
          for (const auto &metric : rows) { body.label(io::get_string(metric, "name") + " RMSE " + metric.at("rmse").dump() + " " + io::get_string(metric, "unit")); }
        }
      }
      if (eval.contains("gate") && eval.at("gate").is_array()) { for (const auto &gate : eval.at("gate")) {
        body.label(io::get_string(gate, "name") + " ≤ " + gate.at("max_rmse").dump() + " " + io::get_string(gate, "unit") +
          " · " + std::string(ctx.tr(gate.value("passed", false) ? "federation.pass" : "federation.fail")));
      } }
      body.button("federation_admit", ctx.tr("federation.admit"), [this, eval, live = guard()] {
        if (live()) { const auto &active = eval.at("plan").at("active"); state_->write(view_, "models.admit", {{"evaluation_id", eval.at("evaluation_id")},
          {"receipt_sha256", eval.at("receipt_sha256")}, {"expected_active_version", active.at("version")}, {"expected_active_generation", active.at("generation")}}); }
      }).disable(view_->busy() || view_->uncertain || !FederationState::evaluation_passed(eval));
    }
    if (model_source) {
      const auto models = view_->models;
      body.label(std::string(ctx.tr("federation.active")) + " " + io::get_string(models, "active_version") + " · " + std::to_string(io::get_int(models, "generation", 0)));
      for (const auto &item : models.at("versions")) {
        const auto version = io::get_string(item, "version"); auto &row = body.row(); row.label(version + " · " + short_id(io::get_string(item.at("model"), "sha256")));
        row.button("federation_activate/" + version, ctx.tr("federation.activate"), [this, models, version, live = guard()] {
          if (live()) { state_->write(view_, "models.activate", {{"spec_sha256", models.at("spec_sha256")}, {"version", version},
            {"expected_active_version", models.at("active_version")}, {"expected_active_generation", models.at("generation")}}); }
        }).disable(view_->busy() || view_->uncertain || models.at("active_version") == version);
      }
    }
    body.paragraph(ctx.tr("federation.rollback_hint"));
  }
};
}  // namespace
std::unique_ptr<Editor> make_federation_editor(const EditorType &type) { return std::make_unique<FederationEditor>(type); }
}  // namespace stk::app
