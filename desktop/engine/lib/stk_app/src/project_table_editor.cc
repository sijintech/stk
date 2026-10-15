/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_table_editor.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/project_data_labels.hh"
#include "editors/project_labels.hh"
#include "editors/editor_text.hh"
#include <algorithm>
#include <unordered_map>

namespace stk::app {
namespace {
using io::Json;
const std::vector<std::string> field_types = {"text", "integer", "number", "boolean", "json"};
constexpr const char *kAnalysesTable = "a32844df-b03d-576b-a200-c7080ae8e97e";
}

struct ProjectTableEditor::Impl {
  bool can_change_project_selection(const std::string_view project_id) const
  {
    return !(draft_dirty_ && draft_identity_.starts_with(project_id)) &&
           !(manage_dirty_ && manage_identity_.starts_with(project_id));
  }
  bool has_unsaved_changes() const { return draft_dirty_ || manage_dirty_; }

  std::function<bool()> current_context(const ProjectState &state) const
  {
    return [weak = std::weak_ptr<void>(lifetime_), &state, handle = state.project()->handle,
            table = state.table_id(), record = state.record_id(), revision = state.project()->revision] {
      return !weak.expired() && state.loaded() && !state.busy() && state.project()->handle == handle &&
             state.project()->revision == revision && state.table_id() == table && state.record_id() == record;
    };
  }

  bool selection_available(AppShell &shell, const ProjectState &state)
  {
    if (!state.project() || !shell.project_selection_available(state.project()->id)) {
      selection_error_ = true;
      return false;
    }
    selection_error_ = false;
    return true;
  }
  void table_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto &box = layout.box();
    std::vector<std::string> names, ids;
    for (const auto &table : state.tables()) {
      names.push_back(table.name);
      ids.push_back(table.id);
    }
    if (!names.empty()) {
      box.prop(ctx.tr("project.table")).dropdown("table", std::move(names), {
        [&state, ids] {
          const auto it = std::find(ids.begin(), ids.end(), state.table_id());
          return it == ids.end() ? -1 : int(it - ids.begin());
        },
        [this, current = current_context(state), &state, ids, shell = &ctx.area.shell()](int i) {
          if (!current() || i < 0 || size_t(i) >= ids.size()) { return; }
          if (state.table_id() == ids[size_t(i)] || selection_available(*shell, state)) { state.select_table(ids[size_t(i)]); }
        }
      });
    }
    if (selection_error_) { box.paragraph(ctx.tr("project.table.selection_dirty")); }
    // Data is private unless labelled public; only public data may go to external model endpoints (format 12).
    // From format 13 a table's structure alone may be public (its names, fields, units and row count; the agent).
    auto &labels = ctx.store.data_labels();
    labels.sync();
    if (labels.supported() && labels.loaded() && !state.table_id().empty()) {
      auto *shared = &labels;
      const auto table = state.table_id();
      if (labels.structure_supported()) {
        static const std::vector<std::string> kLabels = {"private", "structure", "public"};
        box.prop(ctx.tr("labels.table_label")).dropdown("table_label", {std::string(ctx.tr("labels.private")),
            std::string(ctx.tr("labels.structure")), std::string(ctx.tr("labels.public"))}, {
          [shared, table] {
            const auto at = std::find(kLabels.begin(), kLabels.end(), shared->label("table", table));
            return at == kLabels.end() ? 0 : int(at - kLabels.begin());
          },
          [shared, table, current = current_context(state)](const int i) {
            if (current() && i >= 0 && size_t(i) < kLabels.size() && shared->label("table", table) != kLabels[i]) {
              shared->set("table", {table}, kLabels[i]);
            }
          }}).disable(labels.busy()).tip(ctx.tr("labels.table_label.tip"));
      }
      else {
        box.checkbox("table_public", ctx.tr("labels.table_public"), {
            [shared, table] { return shared->is_public("table", table); },
            [shared, table, current = current_context(state)](const bool on) {
              if (current()) { shared->set("table", {table}, on); }
            }})
            .disable(labels.busy()).tip(ctx.tr("labels.table_public.tip"));
      }
    }
    auto &row = box.row();
    row.text_field("table_name", ui::bind(table_name_), {.placeholder = std::string(ctx.tr("project.table_name"))});
    row.button("add_table", ctx.tr("project.add_table"), [this, &state, current = current_context(state)] {
      if (!current()) { return; }
      state.apply(Json::array({{{"op", "create_table"}, {"name", table_name_}}}));
    }).disable(!editable || table_name_.empty());
  }

  void field_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable, const bool expanded)
  {
    auto *panel = layout.panel("project_structure", ctx.tr("project.structure"), expanded);
    if (!panel) {
      return;
    }
    panel->prop(ctx.tr("project.field_name")).text_field("field_name", ui::bind(field_name_));
    std::vector<std::string> types;
    for (const auto &type : field_types) {
      types.emplace_back(ctx.tr("project.type." + type));
    }
    panel->prop(ctx.tr("project.field_type")).dropdown("field_type", std::move(types), ui::bind(field_type_));
    const bool numeric = field_type_ == 1 || field_type_ == 2;
    panel->prop(ctx.tr("project.unit")).text_field("unit", ui::bind(unit_)).disable(!numeric);
    const std::string table = state.table_id();
    panel->button("add_field", ctx.tr("project.add_field"), [this, &state, table, current = current_context(state)] {
      if (!current()) { return; }
      Json command = {{"op", "add_field"}, {"table_id", table}, {"name", field_name_}, {"type", field_types[field_type_]}};
      if ((field_type_ == 1 || field_type_ == 2) && !unit_.empty()) {
        command["unit"] = unit_;
      }
      state.apply(Json::array({command}));
    }).disable(!editable || field_name_.empty());
  }

  /* Parameter sweep: per-field ranges or value lists become new rows in one edit
   * (suan.project.sweep). The project's own tables (analyses, file index) are never swept. */
  struct SweepInput {
    std::string field_id, start, stop, count = "5", list;
    int kind = 0;  // 0: range (start, stop, points), 1: value list
  };
  static constexpr size_t kSweepAxes = 4;

  ui::Binding<std::string> sweep_text(const size_t index, std::string SweepInput::*member)
  {
    return {[this, index, member] { return index < sweep_.size() ? sweep_[index].*member : std::string(); },
            [this, index, member](std::string text) { if (index < sweep_.size()) { sweep_[index].*member = std::move(text); } }};
  }

  void sweep_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    const auto &table = *state.table();
    if (table.id == kAnalysesTable || table.id == io::get_string(state.file_index(), "table_id")) { return; }
    const auto identity = state.project()->handle + table.id;
    if (sweep_identity_ != identity) {
      sweep_identity_ = identity;
      sweep_.assign(1, {});
      sweep_zip_ = sweep_waiting_ = false;
      sweep_result_.clear();
    }
    auto *panel = layout.panel("project_sweep", ctx.tr("project.sweep.title"), false);
    if (!panel) { return; }
    if (!state.supports_sweep()) {
      panel->paragraph(ctx.tr("project.sweep.unavailable"));
      return;
    }
    panel->paragraph(ctx.tr("project.sweep.hint"));
    std::vector<std::string> names, ids, types;
    for (const auto &field : table.fields) {
      if (field.type == "integer" || field.type == "number" || field.type == "text" || field.type == "boolean") {
        names.push_back(field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"));
        ids.push_back(field.id);
        types.push_back(field.type);
      }
    }
    if (ids.empty()) {
      panel->paragraph(ctx.tr("project.sweep.no_fields"));
      return;
    }
    Json axes = Json::array();
    std::vector<size_t> counts;
    std::string error;
    for (size_t i = 0; i < sweep_.size(); ++i) {
      auto &input = sweep_[i];
      auto found = std::find(ids.begin(), ids.end(), input.field_id);
      if (found == ids.end()) {
        // A new axis (or one whose field was removed) takes the first field no other axis uses.
        found = std::find_if(ids.begin(), ids.end(), [this](const std::string &id) {
          return std::none_of(sweep_.begin(), sweep_.end(), [&id](const SweepInput &axis) { return axis.field_id == id; });
        });
        input.field_id = found == ids.end() ? ids.front() : *found;
        found = std::find(ids.begin(), ids.end(), input.field_id);
      }
      const auto &type = types[size_t(found - ids.begin())];
      const bool numeric = type == "integer" || type == "number";
      if (!numeric) { input.kind = 1; }
      auto &box = panel->scope("axis" + std::to_string(i)).box();
      auto &head = box.row();
      head.label(ctx.store.catalog().format("project.sweep.axis", {{"n", std::to_string(i + 1)}}));
      head.button("remove", ctx.tr("project.sweep.remove"), [this, i] {
        if (i < sweep_.size() && sweep_.size() > 1) { sweep_.erase(sweep_.begin() + std::ptrdiff_t(i)); }
      }).width(6).disable(sweep_.size() < 2);
      box.prop(ctx.tr("project.sweep.field")).dropdown("field", names, {
        [this, i, ids] {
          if (i >= sweep_.size()) { return -1; }
          const auto it = std::find(ids.begin(), ids.end(), sweep_[i].field_id);
          return it == ids.end() ? -1 : int(it - ids.begin());
        },
        [this, i, ids](int index) { if (i < sweep_.size() && index >= 0 && size_t(index) < ids.size()) { sweep_[i].field_id = ids[size_t(index)]; } }
      });
      box.prop(ctx.tr("project.sweep.kind")).dropdown("kind", {std::string(ctx.tr("project.sweep.kind_range")),
                                                                std::string(ctx.tr("project.sweep.kind_list"))}, {
        [this, i] { return i < sweep_.size() ? sweep_[i].kind : 0; },
        [this, i](int kind) { if (i < sweep_.size()) { sweep_[i].kind = kind; } }
      }).disable(!numeric);
      if (input.kind == 0) {
        auto &range = box.prop(ctx.tr("project.sweep.range")).row(true);
        range.text_field("start", sweep_text(i, &SweepInput::start), {.placeholder = std::string(ctx.tr("project.sweep.start")), .max_length = 64});
        range.text_field("stop", sweep_text(i, &SweepInput::stop), {.placeholder = std::string(ctx.tr("project.sweep.stop")), .max_length = 64});
        range.text_field("count", sweep_text(i, &SweepInput::count), {.placeholder = std::string(ctx.tr("project.sweep.count")), .max_length = 8});
      }
      else {
        box.prop(ctx.tr("project.sweep.values")).text_field("values", sweep_text(i, &SweepInput::list), {
            .placeholder = std::string(ctx.tr(type == "text" ? "project.sweep.values_text" :
                                              type == "boolean" ? "project.sweep.values_boolean" : "project.sweep.values_number")),
            .max_length = 65536});
      }
      std::string key;
      auto axis = project_sweep_axis(type, input.kind == 0, input.start, input.stop, input.count, input.list, key);
      if (std::any_of(sweep_.begin(), sweep_.begin() + std::ptrdiff_t(i), [&input](const SweepInput &other) { return other.field_id == input.field_id; })) {
        axis.reset();
        key = "project.sweep.error.duplicate";
      }
      if (!axis) {
        if (error.empty()) { error = ctx.store.catalog().format(key, {{"n", std::to_string(i + 1)}}); }
        continue;
      }
      axis->axis["field_id"] = input.field_id;
      axes.push_back(std::move(axis->axis));
      counts.push_back(axis->values);
    }
    auto &more = panel->row();
    more.button("add_axis", ctx.tr("project.sweep.add"), [this] { if (sweep_.size() < kSweepAxes) { sweep_.emplace_back(); } })
        .width(10).disable(sweep_.size() >= kSweepAxes || sweep_.size() >= ids.size());
    if (sweep_.size() > 1) {
      panel->prop(ctx.tr("project.sweep.combine")).dropdown("combine", {std::string(ctx.tr("project.sweep.product")),
                                                                         std::string(ctx.tr("project.sweep.zip"))}, {
        [this] { return sweep_zip_ ? 1 : 0; }, [this](int index) { sweep_zip_ = index == 1; }
      });
    }
    const bool zip = sweep_zip_ && sweep_.size() > 1;
    const bool has_base = state.selected_record() >= 0;
    panel->checkbox("copy_selected", ctx.tr("project.sweep.copy_selected"), ui::bind(sweep_copy_))
        .tip(ctx.tr("project.sweep.copy_tip")).disable(!has_base);
    const std::string base = sweep_copy_ && has_base ? state.record_id() : std::string();
    size_t rows = 0;
    if (error.empty()) {
      rows = zip ? counts.front() : 1;
      for (const auto count : counts) {
        if (zip && count != counts.front()) { error = std::string(ctx.tr("project.sweep.error.zip")); break; }
        if (!zip) { rows = std::min<size_t>(rows * count, 1001); }
      }
    }
    if (error.empty()) {
      // One edit holds at most 1000 commands (suan.project.sweep.MAX_COMMANDS): a new row, its swept
      // cells and each copied cell of the base row are one command each.
      size_t per_row = 1 + counts.size();
      if (!base.empty()) {
        const auto &record = table.records[size_t(state.selected_record())];
        for (const auto &field : table.fields) {
          if (std::any_of(sweep_.begin(), sweep_.end(), [&field](const SweepInput &axis) { return axis.field_id == field.id; })) { continue; }
          const auto *definition = record.definitions.is_object() && record.definitions.contains(field.id) ? &record.definitions.at(field.id) : nullptr;
          const auto kind = definition ? io::get_string(*definition, "kind") : std::string();
          per_row += kind == "expression" || kind == "reference" || (record.values.is_object() && record.values.contains(field.id)) ? 1 : 0;
        }
      }
      if (rows * per_row > 1000) {
        error = ctx.store.catalog().format("project.sweep.error.rows", {{"rows", std::to_string(1000 / per_row)}});
      }
    }
    if (!error.empty()) { panel->paragraph(error); }
    if (sweep_waiting_ && !state.busy()) {
      sweep_waiting_ = false;
      sweep_result_ = state.error().empty() ? state.notice() : state.error();
    }
    const std::string table_id = table.id;
    panel->button("apply_sweep", error.empty() ? ctx.store.catalog().format("project.sweep.apply", {{"rows", std::to_string(rows)}}) :
                                                 std::string(ctx.tr("project.sweep.apply_blocked")),
                  [this, &state, table_id, axes, base, zip, current = current_context(state)] {
                    if (!current()) { return; }
                    sweep_result_.clear();
                    sweep_waiting_ = state.sweep(table_id, axes, base, zip ? "zip" : "product");
                  })
        .disable(!editable || !error.empty());
    // The outcome next to the button as well as at the top of the page, which may be scrolled away.
    if (!sweep_result_.empty()) { panel->paragraph(sweep_result_); }
  }

  bool selected_visible(const ProjectState &state) const
  {
    return query_.text == query_cached_text_ && query_.errors_only == query_cached_errors_ &&
           std::find(visible_ids_->begin(), visible_ids_->end(), state.record_id()) != visible_ids_->end();
  }

  void draw_table(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    const auto &table = *state.table();
    const auto identity = state.project()->handle + table.id;
    if (query_handle_ != state.project()->handle) {
      query_handle_ = state.project()->handle;
      query_ = {};
    }
    if (query_identity_ != identity) {
      query_identity_ = identity;
      query_revision_ = -1;
    }
    auto &search = layout.row();
    search.text_field("table_search", ui::bind(query_.text), {
        .placeholder = std::string(ctx.tr("project.filter.search")), .max_length = 256});
    search.checkbox("table_errors_only", ctx.tr("project.filter.errors"), ui::bind(query_.errors_only));
    search.button("table_clear_search", ctx.tr("project.filter.clear"), [this] { query_ = {}; })
        .disable(query_.text.empty() && !query_.errors_only);
    if (query_revision_ != state.project()->revision || query_cached_text_ != query_.text || query_cached_errors_ != query_.errors_only) {
      query_revision_ = state.project()->revision;
      query_cached_text_ = query_.text;
      query_cached_errors_ = query_.errors_only;
      ++query_version_;
      query_error_.clear();
      auto rows = std::make_shared<std::vector<int>>();
      auto ids = std::make_shared<std::vector<std::string>>();
      auto cells = std::make_shared<std::unordered_map<uint64_t, std::string>>();
      try { *rows = project_table_rows(table, query_); }
      catch (const std::exception &error) { query_error_ = error.what(); }
      for (const auto row : *rows) { ids->push_back(table.records[size_t(row)].id); }
      visible_rows_ = std::move(rows);
      visible_ids_ = std::move(ids);
      visible_cells_ = std::move(cells);
    }
    if (!query_error_.empty()) { layout.paragraph(query_error_); }
    layout.label(ctx.store.catalog().format("project.filter.count", {
      {"shown", std::to_string(visible_rows_->size())}, {"total", std::to_string(table.records.size())}}));
    const auto rows = visible_rows_;
    const auto ids = visible_ids_;
    const auto cells = visible_cells_;
    const auto matches = [this, weak = std::weak_ptr<void>(lifetime_), &state, handle = state.project()->handle, id = table.id, revision = state.project()->revision, query_version = query_version_] {
      return !weak.expired() && query_version_ == query_version && query_.text == query_cached_text_ && query_.errors_only == query_cached_errors_ && state.project() && state.project()->handle == handle && state.table_id() == id && state.project()->revision == revision;
    };
    ui::TableSpec spec;
    spec.columns.push_back({std::string(ctx.tr("project.row_column")), 4.0f, true, true});
    const bool file_table = table.id == io::get_string(state.file_index(), "table_id");
    const Json file_fields = file_table ? state.file_index().value("fields", Json::object()) : Json::object();
    for (const auto &field : table.fields) {
      const bool numeric = field.type == "integer" || field.type == "number";
      const float width = !file_table ? 8.0f : field.id == io::get_string(file_fields, "path") ? 12.0f :
                          field.id == io::get_string(file_fields, "name") ? 8.0f : 5.0f;
      spec.columns.push_back({field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"), width, true, numeric});
    }
    spec.rows = int(rows->size());
    spec.visible_rows = float(std::clamp(spec.rows, 3, 9));
    spec.data_version = query_version_;
    spec.cell = [&state, rows, ids, cells, matches, store = &ctx.store](int row, int col) {
      if (!matches() || row < 0 || col < 0 || size_t(row) >= rows->size() || size_t(col) > state.table()->fields.size()) { return std::string(); }
      // Rows are numbered by their place in the table; the UUID is in the cell editor's tooltip and searchable.
      if (col == 0) { return std::to_string((*rows)[size_t(row)] + 1); }
      const uint64_t key = (uint64_t(uint32_t(row)) << 32) | uint32_t(col);
      if (const auto found = cells->find(key); found != cells->end()) { return found->second; }
      const auto &table = *state.table();
      const int original = (*rows)[size_t(row)], column = col - 1;
      const auto *evaluation = table.evaluation(original, column);
      std::string summary;
      if (evaluation && io::get_string(*evaluation, "state") == "error") {
        summary = formula_error_label(*store, io::get_string(evaluation->at("error"), "code"));
      }
      else {
        const auto *value = table.cell(original, column);
        summary = (table.definition(original, column) ? "= " : "") + (value ? project_value_summary(*value) : std::string());
      }
      // Cache only cells actually requested by the virtual table; never summarize an entire
      // large project just to draw its first screen. Each displayed value is bounded as well.
      if (cells->size() >= 4096) { cells->clear(); }
      cells->emplace(key, summary);
      return summary;
    };
    spec.selected = {[&state, ids, matches] {
      if (!matches()) { return -1; }
      const auto found = std::find(ids->begin(), ids->end(), state.record_id());
      return found == ids->end() ? -1 : int(found - ids->begin());
    }, [this, &state, shell = &ctx.area.shell(), ids, matches](int row) {
      if (matches() && row >= 0 && size_t(row) < ids->size()) {
        const auto &record = (*ids)[size_t(row)];
        if (state.record_id() == record || selection_available(*shell, state)) { state.select_record(record); }
      }
    }};
    std::vector<std::string> field_ids;
    for (const auto &field : table.fields) { field_ids.push_back(field.id); }
    spec.on_cell_select = [this, &state, shell = &ctx.area.shell(), ids, field_ids, matches](int row, int column) {
      if (!matches() || row < 0 || size_t(row) >= ids->size() || column <= 0 || size_t(column) > field_ids.size()
          || state.record_id() != (*ids)[size_t(row)]) { return; }
      const auto &field = field_ids[size_t(column - 1)];
      if (cell_field_ == field || selection_available(*shell, state)) { cell_field_ = field; }
    };
    spec.compare = [&state, rows, matches](int a, int b, int column) {
      if (!matches() || a < 0 || b < 0 || size_t(a) >= rows->size() || size_t(b) >= rows->size()) { return 0; }
      if (column > 0) { return state.table()->compare((*rows)[size_t(a)], (*rows)[size_t(b)], column - 1); }
      const int left = (*rows)[size_t(a)], right = (*rows)[size_t(b)];  // Row number: table order.
      return int(left > right) - int(left < right);
    };
    spec.cell_color = [&state, rows, matches](int row, int column) -> ui::Color {
      const Json *result = matches() && row >= 0 && size_t(row) < rows->size() && column > 0 ?
                           state.table()->evaluation((*rows)[size_t(row)], column - 1) : nullptr;
      return result && io::get_string(*result, "state") == "error" ? ui::Color::rgb(0xff6e6e) : ui::Color{0, 0, 0, 0};
    };
    layout.scope(table.id).table("records", std::move(spec));
    const std::string id = table.id;
    layout.button("add_record", ctx.tr("project.add_record"), [&state, id, matches] {
      if (matches()) { state.apply(Json::array({{{"op", "add_record"}, {"table_id", id}}})); }
    }).disable(!state.ready() || state.busy());
  }

  void load_cell(ProjectState &state, const ProjectField &field)
  {
    const int column = int(&field - state.table()->fields.data());
    const auto *value = state.table()->cell(state.selected_record(), column);
    cell_text_ = !value ? std::string() : value->is_string() ? value->get<std::string>() : value->dump();
    // JSON fields containing a string need JSON quotes; text fields do not.
    if (value && field.type == "json") {
      cell_text_ = value->dump();
    }
    cell_mode_ = 0;
    expression_.clear();
    bindings_ = "{}";
    selected_binding_.clear();
    source_table_.clear();
    source_record_.clear();
    source_field_.clear();
    if (const Json *definition = state.table()->definition(state.selected_record(), column)) {
      const std::string kind = io::get_string(*definition, "kind");
      if (kind == "reference") {
        cell_mode_ = 1;
        source_record_ = io::get_string(definition->at("source"), "record_id");
        source_field_ = io::get_string(definition->at("source"), "field_id");
        for (const auto &table : state.tables()) {
          for (const auto &candidate : table.fields) {
            if (candidate.id == source_field_) { source_table_ = table.id; }
          }
        }
      }
      else if (kind == "expression") {
        cell_mode_ = 2;
        expression_ = io::get_string(*definition, "expression");
        bindings_ = definition->at("bindings").dump(2);
      }
    }
    draft_revision_ = state.project()->revision;
    draft_dirty_ = false;
    literal_error_.clear();
  }

  void source_controls(ui::Layout &box, EditorContext &ctx, ProjectState &state)
  {
    std::vector<std::string> tables{std::string(ctx.tr("project.source_pick"))}, table_ids{""};
    const ProjectTable *source = nullptr;
    for (const auto &table : state.tables()) {
      tables.push_back(table.name);
      table_ids.push_back(table.id);
      if (table.id == source_table_) { source = &table; }
    }
    box.prop(ctx.tr("project.source_table")).dropdown("source_table", std::move(tables), {
      [this, table_ids] {
        const auto found = std::find(table_ids.begin(), table_ids.end(), source_table_);
        return found == table_ids.end() ? 0 : int(found - table_ids.begin());
      },
      [this, table_ids](int index) {
        if (index >= 0 && size_t(index) < table_ids.size()) {
          source_table_ = table_ids[index]; source_record_.clear(); source_field_.clear(); draft_dirty_ = true;
        }
      }
    });
    if (!source) {
      if (!source_record_.empty() || !source_field_.empty()) {
        box.paragraph(ctx.tr("project.source_missing"));
        box.paragraph(source_record_ + " / " + source_field_);
      }
      return;
    }
    std::vector<std::string> records{std::string(ctx.tr("project.source_pick"))}, record_ids{""};
    for (size_t i = 0; i < source->records.size(); ++i) {
      records.push_back(std::to_string(i + 1) + " · " + source->records[i].id.substr(0, 8));
      record_ids.push_back(source->records[i].id);
    }
    box.prop(ctx.tr("project.source_record")).dropdown("source_record", std::move(records), {
      [this, record_ids] {
        const auto found = std::find(record_ids.begin(), record_ids.end(), source_record_);
        return found == record_ids.end() ? 0 : int(found - record_ids.begin());
      },
      [this, record_ids](int index) {
        if (index >= 0 && size_t(index) < record_ids.size()) { source_record_ = record_ids[index]; draft_dirty_ = true; }
      }
    });
    std::vector<std::string> fields{std::string(ctx.tr("project.source_pick"))}, field_ids{""};
    for (const auto &field : source->fields) {
      fields.push_back(field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"));
      field_ids.push_back(field.id);
    }
    box.prop(ctx.tr("project.source_field")).dropdown("source_field", std::move(fields), {
      [this, field_ids] {
        const auto found = std::find(field_ids.begin(), field_ids.end(), source_field_);
        return found == field_ids.end() ? 0 : int(found - field_ids.begin());
      },
      [this, field_ids](int index) {
        if (index >= 0 && size_t(index) < field_ids.size()) { source_field_ = field_ids[index]; draft_dirty_ = true; }
      }
    });
  }

  void binding_table(ui::Layout &box, EditorContext &ctx, ProjectState &state)
  {
    std::vector<std::string> names;
    std::vector<std::vector<std::string>> rows;
    try {
      const Json bindings = io::parse_json(bindings_);
      if (!bindings.is_object()) { throw std::runtime_error("not an object"); }
      for (const auto &[name, source] : bindings.items()) {
        const std::string record = source.is_object() ? io::get_string(source, "record_id") : "";
        const std::string field = source.is_object() ? io::get_string(source, "field_id") : "";
        std::vector<std::string> row{name, std::string(ctx.tr("project.binding_missing")), record.substr(0, 8), field.substr(0, 8), ""};
        for (const auto &table : state.tables()) {
          for (size_t c = 0; c < table.fields.size(); ++c) {
            if (table.fields[c].id != field) { continue; }
            for (size_t r = 0; r < table.records.size(); ++r) {
              if (table.records[r].id == record) {
                row[1] = table.name;
                row[2] = std::to_string(r + 1) + " · " + record.substr(0, 8);
                row[3] = table.fields[c].name;
                row[4] = table.text(int(r), int(c));
              }
            }
          }
        }
        names.push_back(name);
        rows.push_back(std::move(row));
      }
    }
    catch (const std::exception &) {
      box.paragraph(ctx.tr("project.error.bindings"));
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("project.binding_name")), 5},
                    {std::string(ctx.tr("project.source_table")), 8},
                    {std::string(ctx.tr("project.source_record")), 7},
                    {std::string(ctx.tr("project.source_field")), 8},
                    {std::string(ctx.tr("project.value")), 6}};
    spec.rows = int(rows.size());
    spec.visible_rows = float(std::clamp(int(rows.size()), 1, 4));
    spec.data_version = state.version() + uint64_t(std::hash<std::string>{}(bindings_));
    spec.cell = [rows](int row, int col) { return rows[size_t(row)][size_t(col)]; };
    spec.selected = {
      [this, names] {
        const auto found = std::find(names.begin(), names.end(), selected_binding_);
        return found == names.end() ? -1 : int(found - names.begin());
      },
      [this, names](int index) { if (index >= 0 && size_t(index) < names.size()) { selected_binding_ = names[index]; } }
    };
    box.table("binding_rows", std::move(spec));
    box.button("remove_binding", ctx.tr("project.remove_binding"), [this] {
      try {
        Json bindings = io::parse_json(bindings_);
        if (!bindings.is_object()) { return; }
        bindings.erase(selected_binding_);
        bindings_ = bindings.dump(2);
        selected_binding_.clear();
        draft_dirty_ = true;
      }
      catch (const std::exception &) { literal_error_ = "project.error.bindings"; }
    }).disable(std::find(names.begin(), names.end(), selected_binding_) == names.end());
  }

  void draw_cell(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    const auto &table = *state.table();
    if (table.fields.empty() || state.selected_record() < 0) {
      layout.paragraph(ctx.tr("project.empty_table"));
      return;
    }
    std::vector<std::string> names, ids;
    for (const auto &field : table.fields) {
      names.push_back(field.name);
      ids.push_back(field.id);
    }
    auto it = std::find(ids.begin(), ids.end(), cell_field_);
    if (it == ids.end()) {
      cell_field_ = ids.front();
      it = ids.begin();
    }
    const auto &field = table.fields[size_t(it - ids.begin())];
    const std::string identity = state.project()->id + table.id + state.record_id() + field.id;
    if (identity != draft_identity_ || (!draft_dirty_ && draft_revision_ != state.project()->revision)) {
      draft_identity_ = identity;
      load_cell(state, field);
      pending_cell_ = false;
    }
    else if (pending_cell_ && !state.busy()) {
      pending_cell_ = false;
      if (state.error().empty()) {
        load_cell(state, field);
      }
    }
    auto &box = layout.box();
    box.label(std::string(ctx.tr("project.cell_editor")) + "  ·  " + row_label(ctx.store, &table, state.record_id()))
        .tip(state.record_id());
    box.prop(ctx.tr("project.field")).dropdown("cell_field", std::move(names), {
      [this, ids] { return int(std::find(ids.begin(), ids.end(), cell_field_) - ids.begin()); },
      [this, current = current_context(state), &state, shell = &ctx.area.shell(), ids](int i) {
        if (current() && i >= 0 && size_t(i) < ids.size() &&
            (cell_field_ == ids[size_t(i)] || selection_available(*shell, state))) { cell_field_ = ids[size_t(i)]; }
      }
    });
    const bool version2 = state.project()->format_version >= 2;
    if (version2) {
      box.prop(ctx.tr("project.definition")).dropdown("cell_mode", {
        std::string(ctx.tr("project.mode.literal")), std::string(ctx.tr("project.mode.reference")),
        std::string(ctx.tr("project.mode.expression"))}, {
        [this] { return cell_mode_; }, [this](int mode) { cell_mode_ = mode; draft_dirty_ = true; literal_error_.clear(); }
      });
    }
    if (cell_mode_ == 0) {
      box.prop(ctx.tr("project.value")).text_field("cell_value", {
        [this] { return cell_text_; },
        [this](std::string text) { cell_text_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
      }, {.mono = field.type != "text"});
    }
    else if (cell_mode_ == 1) {
      source_controls(box, ctx, state);
    }
    else {
      box.prop(ctx.tr("project.expression")).text_field("expression", {
        [this] { return expression_; },
        [this](std::string text) { expression_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
      }, {.max_length = 4096, .mono = true});
      box.label(ctx.tr("project.bindings"));
      binding_table(box, ctx, state);
      if (auto *panel = box.panel("add_binding", ctx.tr("project.add_binding"), false)) {
        panel->prop(ctx.tr("project.binding_name")).text_field("binding_name", ui::bind(binding_name_));
        source_controls(*panel, ctx, state);
        panel->button("insert_binding", ctx.tr("project.insert_binding"), [this] {
          try {
            Json bindings = io::parse_json(bindings_);
            if (!bindings.is_object()) { literal_error_ = "project.error.bindings"; return; }
            bindings[binding_name_] = {{"record_id", source_record_}, {"field_id", source_field_}};
            bindings_ = bindings.dump(2);
            selected_binding_ = binding_name_;
            draft_dirty_ = true;
            literal_error_.clear();
          }
          catch (const std::exception &) { literal_error_ = "project.error.bindings"; }
        }).disable(source_record_.empty() || source_field_.empty() || binding_name_.empty());
      }
      if (auto *panel = box.panel("bindings_raw", ctx.tr("project.bindings_advanced"), false)) {
        panel->text_area("bindings", {
          [this] { return bindings_; },
          [this](std::string text) { bindings_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
        }, {.max_length = 32768, .mono = true, .visible_lines = 4});
      }
    }
    const int column = int(&field - table.fields.data());
    if (const Json *evaluation = table.evaluation(state.selected_record(), column)) {
      if (io::get_string(*evaluation, "state") == "error") {
        const Json &error = evaluation->at("error");
        box.paragraph(std::string(ctx.tr("project.evaluation_error")) + " · " + io::get_string(error, "code") +
                      ": " + io::get_string(error, "message"));
      }
      else {
        box.label(std::string(ctx.tr("project.computed_value")) + " " + table.text(state.selected_record(), column) +
                  " " + io::get_string(*evaluation, "unit"));
      }
    }
    if (draft_revision_ != state.project()->revision) {
      box.paragraph(ctx.tr("project.draft_stale"));
    }
    if (!literal_error_.empty()) {
      box.paragraph(ctx.tr(literal_error_));
    }
    if (auto *detail = box.panel("cell_details", ctx.tr("project.cell_details"), false)) {
      detail->paragraph(field.type + (field.unit.empty() ? "" : " · " + field.unit));
      detail->paragraph("record: " + state.record_id());
      detail->paragraph("field: " + field.id);
      if (const auto *value = table.cell(state.selected_record(), column)) {
        detail->paragraph(project_value_summary(*value, 4096));
      }
      if (const auto *definition = table.definition(state.selected_record(), column)) {
        detail->paragraph(project_value_summary(*definition, 4096));
      }
      if (const auto *evaluation = table.evaluation(state.selected_record(), column)) {
        detail->paragraph(project_value_summary(*evaluation, 4096));
      }
    }
    const Json target = {{"op", "set_cell"}, {"table_id", table.id}, {"record_id", state.record_id()}, {"field_id", field.id}};
    const std::string type = field.type;
    const auto target_current = [this, weak = std::weak_ptr<void>(lifetime_), &state, target, handle = state.project()->handle, query_version = query_version_] {
      return !weak.expired() && state.loaded() && state.project()->handle == handle && query_version_ == query_version && selected_visible(state) &&
             state.table_id() == io::get_string(target, "table_id") && state.record_id() == io::get_string(target, "record_id") &&
             cell_field_ == io::get_string(target, "field_id");
    };
    auto &buttons = box.row();
    const auto edit = [this, &state, target, type, target_current](const bool review) {
      if (!target_current() || state.busy() || draft_revision_ != state.project()->revision) { return; }
      Json command = target;
      if (cell_mode_ == 0) {
        auto value = project_literal(type, cell_text_, literal_error_);
        if (!value) { return; }
        command["value"] = *value;
      }
      else if (cell_mode_ == 1) {
        if (source_record_.empty() || source_field_.empty()) { literal_error_ = "project.error.reference"; return; }
        command["op"] = "set_reference";
        command["source"] = {{"record_id", source_record_}, {"field_id", source_field_}};
      }
      else {
        try {
          Json bindings = io::parse_json(bindings_);
          if (!bindings.is_object()) { literal_error_ = "project.error.bindings"; return; }
          command["op"] = "set_expression";
          command["expression"] = expression_;
          command["bindings"] = std::move(bindings);
        }
        catch (const std::exception &) { literal_error_ = "project.error.bindings"; return; }
      }
      if (review) {
        state.set_review_source(Json::array({command}).dump(2));
        if (open_review_) { open_review_(); }
        state.preview();
      }
      else { pending_cell_ = state.apply(Json::array({command}), draft_revision_); }
    };
    buttons.button("save_cell", ctx.tr("project.save_cell"), [edit] { edit(false); })
        .disable(!editable || draft_revision_ != state.project()->revision);
    buttons.button("null_cell", ctx.tr("project.null_cell"), [this, &state, target, target_current] {
      if (!target_current()) { return; }
      Json command = target;
      command["value"] = nullptr;
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    if (version2) {
      buttons.button("unset_cell", ctx.tr("project.unset_cell"), [this, &state, target, target_current] {
        if (!target_current()) { return; }
        Json command = target;
        command["op"] = "unset_cell";
        pending_cell_ = state.apply(Json::array({command}), draft_revision_);
      }).disable(!editable || draft_revision_ != state.project()->revision);
    }
    buttons.button("reload_cell", ctx.tr("project.reload_cell"), [this, target_current] {
      if (target_current()) { draft_identity_.clear(); }
    });
    box.paragraph(ctx.tr(cell_mode_ == 0 ? "project.cell_hint" : "project.expression_hint"));
    box.button("review_cell", ctx.tr("project.review.cell_action"), [edit] { edit(true); })
        .disable(!editable || !state.preview_supported() || draft_revision_ != state.project()->revision);
  }
  void manage_objects(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    const auto *table = state.table();
    if (!table) { return; }
    if (std::none_of(table->fields.begin(), table->fields.end(), [this](const auto &field) { return field.id == cell_field_; })) {
      cell_field_ = table->fields.empty() ? std::string() : table->fields.front().id;
    }
    // Name/delete drafts have the same revision precondition as cell edits. Switching the
    // target resets them; a background revision change keeps a dirty draft for review.
    const std::string identity = state.project()->id + table->id + cell_field_ + state.record_id();
    if (identity != manage_identity_ || (!manage_dirty_ && manage_revision_ != state.project()->revision)) {
      manage_identity_ = identity;
      manage_revision_ = state.project()->revision;
      rename_table_ = table->name;
      rename_field_.clear();
      for (const auto &field : table->fields) {
        if (field.id == cell_field_) { rename_field_ = field.name; }
      }
      manage_dirty_ = false;
      pending_manage_ = false;
    }
    else if (pending_manage_ && !state.busy()) {
      pending_manage_ = false;
      if (state.error().empty()) { manage_identity_.clear(); }
    }
    auto *panel = layout.panel("manage_objects", ctx.tr("project.manage"), false);
    if (!panel) { return; }
    const bool current = editable && manage_revision_ == state.project()->revision;
    if (manage_revision_ != state.project()->revision) {
      panel->paragraph(ctx.tr("project.draft_stale"));
    }
    panel->prop(ctx.tr("project.table")).text_field("rename_table", {
      [this] { return rename_table_; },
      [this](std::string value) { rename_table_ = std::move(value); manage_dirty_ = true; }
    });
    const std::string table_id = table->id;
    const auto target_current = [this, current = current_context(state), identity = manage_identity_] {
      return current() && manage_identity_ == identity;
    };
    panel->button("save_table_name", ctx.tr("project.rename_table"), [this, &state, table_id, target_current] {
      if (!target_current()) { return; }
      pending_manage_ = state.apply(Json::array({{{"op", "rename_table"}, {"id", table_id}, {"name", rename_table_}}}), manage_revision_);
    }).disable(!current || rename_table_.empty());
    if (!table->fields.empty()) {
      std::vector<std::string> names, ids;
      for (const auto &field : table->fields) { names.push_back(field.name); ids.push_back(field.id); }
      panel->prop(ctx.tr("project.field")).dropdown("manage_field", std::move(names), {
        [this, ids] { return int(std::find(ids.begin(), ids.end(), cell_field_) - ids.begin()); },
        [this, current = current_context(state), &state, shell = &ctx.area.shell(), ids](int index) {
          if (current() && index >= 0 && size_t(index) < ids.size() &&
              (cell_field_ == ids[size_t(index)] || selection_available(*shell, state))) { cell_field_ = ids[size_t(index)]; }
        }
      });
      panel->prop(ctx.tr("project.field_name")).text_field("rename_field", {
        [this] { return rename_field_; },
        [this](std::string value) { rename_field_ = std::move(value); manage_dirty_ = true; }
      });
      const std::string field_id = cell_field_;
      panel->button("save_field_name", ctx.tr("project.rename_field"), [this, &state, field_id, target_current] {
        if (!target_current()) { return; }
        pending_manage_ = state.apply(Json::array({{{"op", "rename_field"}, {"id", field_id}, {"name", rename_field_}}}), manage_revision_);
      }).disable(!current || rename_field_.empty());
    }
    panel->button("reload_names", ctx.tr("project.reload_names"), [this, target_current] {
      if (target_current()) { manage_identity_.clear(); }
    });
    if (state.project()->format_version >= 3) {
      hint(*panel, ctx, "project.delete_hint");
      auto &buttons = panel->row();
      const std::string record_id = state.record_id(), field_id = cell_field_;
      buttons.button("delete_record", ctx.tr("project.delete_record"), [this, &state, record_id, table_id, target_current, shell = &ctx.area.shell(), handle = state.project()->handle, query_version = query_version_] {
        if (!target_current() || !selection_available(*shell, state) || !state.project() || state.project()->handle != handle || state.table_id() != table_id || state.record_id() != record_id ||
            query_version != query_version_ || !selected_visible(state)) { return; }
        pending_manage_ = state.apply(Json::array({{{"op", "delete_record"}, {"id", record_id}}}), manage_revision_);
      }).disable(!current || state.selected_record() < 0 || !selected_visible(state));
      buttons.button("delete_field", ctx.tr("project.delete_field"), [this, &state, field_id, target_current, shell = &ctx.area.shell()] {
        if (!target_current() || !selection_available(*shell, state)) { return; }
        pending_manage_ = state.apply(Json::array({{{"op", "delete_field"}, {"id", field_id}}}), manage_revision_);
      }).disable(!current || table->fields.empty());
      buttons.button("delete_table", ctx.tr("project.delete_table"), [this, &state, table_id, target_current, shell = &ctx.area.shell()] {
        if (!target_current() || !selection_available(*shell, state)) { return; }
        pending_manage_ = state.apply(Json::array({{{"op", "delete_table"}, {"id", table_id}}}), manage_revision_);
      }).disable(!current);
    }
  }

  ProjectTableQuery query_;
  std::string query_handle_, query_identity_, query_cached_text_, query_error_;
  bool query_cached_errors_ = false;
  int64_t query_revision_ = -1;
  uint64_t query_version_ = 0;
  std::shared_ptr<const std::vector<int>> visible_rows_ = std::make_shared<std::vector<int>>();
  std::shared_ptr<const std::vector<std::string>> visible_ids_ = std::make_shared<std::vector<std::string>>();
  std::shared_ptr<std::unordered_map<uint64_t, std::string>> visible_cells_ = std::make_shared<std::unordered_map<uint64_t, std::string>>();
  std::string table_name_, field_name_, unit_, cell_field_;
  std::string cell_text_, draft_identity_, literal_error_;
  std::string expression_, bindings_ = "{}", binding_name_ = "base";
  std::string selected_binding_, source_table_, source_record_, source_field_;
  int cell_mode_ = 0, field_type_ = 2;
  int64_t draft_revision_ = -1;
  bool draft_dirty_ = false, pending_cell_ = false;
  std::vector<SweepInput> sweep_ = std::vector<SweepInput>(1);
  std::string sweep_identity_, sweep_result_;
  bool sweep_zip_ = false, sweep_copy_ = true, sweep_waiting_ = false;
  std::string manage_identity_, rename_table_, rename_field_;
  int64_t manage_revision_ = -1;
  bool manage_dirty_ = false, pending_manage_ = false;
  std::function<void()> open_review_;
  std::shared_ptr<void> lifetime_ = std::make_shared<int>(0);
  bool selection_error_ = false;
};

ProjectTableEditor::ProjectTableEditor() : impl_(std::make_unique<Impl>()) {}
ProjectTableEditor::~ProjectTableEditor() = default;
bool ProjectTableEditor::can_change_project_selection(std::string_view id) const { return impl_->can_change_project_selection(id); }
bool ProjectTableEditor::has_unsaved_changes() const { return impl_->has_unsaved_changes(); }
void ProjectTableEditor::controls(ui::Layout &l, EditorContext &c, ProjectState &s, bool e) { impl_->table_controls(l, c, s, e); }
void ProjectTableEditor::fields(ui::Layout &l, EditorContext &c, ProjectState &s, bool e, bool expanded) { impl_->field_controls(l, c, s, e, expanded); }
void ProjectTableEditor::sweep(ui::Layout &l, EditorContext &c, ProjectState &s, bool e) { impl_->sweep_controls(l, c, s, e); }
void ProjectTableEditor::grid(ui::Layout &l, EditorContext &c, ProjectState &s) { impl_->draw_table(l, c, s); }
bool ProjectTableEditor::selected_visible(const ProjectState &s) const { return impl_->selected_visible(s); }
void ProjectTableEditor::cell(ui::Layout &l, EditorContext &c, ProjectState &s, bool e, std::function<void()> review) { impl_->open_review_ = std::move(review); impl_->draw_cell(l, c, s, e); }
void ProjectTableEditor::management(ui::Layout &l, EditorContext &c, ProjectState &s, bool e) { impl_->manage_objects(l, c, s, e); }
}  // namespace stk::app
