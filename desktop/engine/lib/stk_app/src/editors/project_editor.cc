/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include "stk/platform/file_dialog.hh"

#include <algorithm>

namespace stk::app {
namespace {

using io::Json;
const std::vector<std::string> field_types = {"text", "integer", "number", "boolean", "json"};

class ProjectEditor final : public Editor {
 public:
  explicit ProjectEditor(const EditorType &type) : Editor(type) {}

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    row.button("project_refresh", ctx.tr("project.refresh"), [&state] { state.refresh(); })
        .width(5)
        .disable(!state.ready() || !state.project() || state.busy());
    row.button("project_close", ctx.tr("project.close"), [&state] { state.close(); })
        .width(9)
        .disable(!state.project() || state.busy());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    if (!state.ready()) {
      layout.paragraph(ctx.tr("project.bridge_required"));
    }
    if (!state.error().empty()) {
      layout.paragraph(state.error());
    }
    if (!state.notice().empty()) {
      layout.paragraph(state.notice());
    }
    if (state.busy()) {
      layout.label(ctx.tr("project.busy"));
    }
    if (auto *panel = layout.panel("project_location", ctx.tr("project.location"), !state.project())) {
      panel->prop(ctx.tr("project.directory")).text_field("directory", ui::bind(directory_));
      panel->prop(ctx.tr("project.name")).text_field("name", ui::bind(name_));
      auto &buttons = panel->row();
      buttons.button("open", ctx.tr("project.open"), [this, &state] {
        state.open(path());
      }).disable(!state.ready() || state.busy() || directory_.empty());
      buttons.button("create", ctx.tr("project.create"), [this, &state] {
        state.create(path(), name_);
      }).disable(!state.ready() || state.busy() || directory_.empty() || name_.empty());
    }
    if (!state.project()) {
      layout.paragraph(ctx.tr("project.intro"));
      return;
    }
    layout.label(state.project()->name);
    layout.paragraph(state.project()->directory);
    layout.label(ctx.store.catalog().format("project.revision", {{"revision", std::to_string(state.project()->revision)}}));
    if (!state.loaded()) {
      return;
    }
    const bool editable = state.ready() && !state.busy();
    if (state.project()->format_version < 2) {
      layout.paragraph(ctx.tr("project.upgrade_hint"));
      layout.button("upgrade_project", ctx.tr("project.upgrade"), [&state] { state.upgrade(); }).disable(!editable);
    }
    if (auto *panel = layout.panel("project_backup", ctx.tr("project.backup_title"), false)) {
      panel->paragraph(ctx.tr("project.backup_hint"));
      panel->button("backup", ctx.tr("project.backup"), [&state] { state.backup(); }).disable(!editable);
    }
    table_controls(layout, ctx, state, editable);
    const auto *table = state.table();
    if (!table) {
      return;
    }
    field_controls(layout, ctx, state, editable);
    draw_table(layout, ctx, state);
    draw_cell(layout, ctx, state, editable);
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    if (paths.size() != 1) {
      return false;
    }
    directory_ = paths.front();
    const std::string suffix = "project.sqlite3";
    if (directory_.size() > suffix.size() && directory_.ends_with(suffix)) {
      const auto slash = directory_.find_last_of("/\\");
      if (slash != std::string::npos) {
        directory_ = directory_.substr(0, slash + 1);
      }
    }
    ctx.store.project().sync();
    return ctx.store.project().open(path());
  }

  nlohmann::json save_state() const override
  {
    return {{"directory", directory_}, {"name", name_}};
  }

  bool load_state(const nlohmann::json &value) override
  {
    if (!value.is_object()) {
      return false;
    }
    if (value.contains("directory") && value["directory"].is_string()) {
      directory_ = value["directory"].get<std::string>();
    }
    if (value.contains("name") && value["name"].is_string()) {
      name_ = value["name"].get<std::string>();
    }
    return true;
  }

 private:
  std::string path() const
  {
    const auto paths = platform::split_path_list(directory_);
    return paths.size() == 1 ? paths.front() : directory_;
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
        [&state, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { state.select_table(ids[i]); } }
      });
    }
    auto &row = box.row();
    row.text_field("table_name", ui::bind(table_name_), {.placeholder = std::string(ctx.tr("project.table_name"))});
    row.button("add_table", ctx.tr("project.add_table"), [this, &state] {
      state.apply(Json::array({{{"op", "create_table"}, {"name", table_name_}}}));
    }).disable(!editable || table_name_.empty());
  }

  void field_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto *panel = layout.panel("project_structure", ctx.tr("project.structure"), false);
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
    panel->button("add_field", ctx.tr("project.add_field"), [this, &state, table] {
      Json command = {{"op", "add_field"}, {"table_id", table}, {"name", field_name_}, {"type", field_types[field_type_]}};
      if ((field_type_ == 1 || field_type_ == 2) && !unit_.empty()) {
        command["unit"] = unit_;
      }
      state.apply(Json::array({command}));
    }).disable(!editable || field_name_.empty());
  }

  void draw_table(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    const auto &table = *state.table();
    ui::TableSpec spec;
    spec.columns.push_back({std::string(ctx.tr("project.record")), 6.0f});
    for (const auto &field : table.fields) {
      const bool numeric = field.type == "integer" || field.type == "number";
      spec.columns.push_back({field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"), 8.0f, true, numeric});
    }
    spec.rows = int(table.records.size());
    spec.visible_rows = float(std::clamp(int(table.records.size()), 3, 9));
    spec.data_version = state.version();
    spec.cell = [&state](int row, int col) {
      const auto *table = state.table();
      if (!table || row < 0 || size_t(row) >= table->records.size()) {
        return std::string();
      }
      return col == 0 ? table->records[row].id.substr(0, 8) : table->text(row, col - 1);
    };
    spec.selected = {[&state] { return state.selected_record(); }, [&state](int row) {
      const auto *table = state.table();
      if (table && row >= 0 && size_t(row) < table->records.size()) {
        state.select_record(table->records[row].id);
      }
    }};
    spec.cell_color = [&state](int row, int column) -> ui::Color {
      const auto *table = state.table();
      const Json *result = table && column > 0 ? table->evaluation(row, column - 1) : nullptr;
      // Match Jobs' failure text colour; theme.state.error is a dark background tint.
      return result && io::get_string(*result, "state") == "error" ? ui::Color::rgb(0xff6e6e) : ui::Color{0, 0, 0, 0};
    };
    layout.scope(table.id).table("records", std::move(spec));
    const std::string id = table.id;
    layout.button("add_record", ctx.tr("project.add_record"), [&state, id] {
      state.apply(Json::array({{{"op", "add_record"}, {"table_id", id}}}));
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
    box.label(ctx.tr("project.cell_editor"));
    box.prop(ctx.tr("project.field")).dropdown("cell_field", std::move(names), {
      [this, ids] { return int(std::find(ids.begin(), ids.end(), cell_field_) - ids.begin()); },
      [this, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { cell_field_ = ids[i]; } }
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
    const Json target = {{"op", "set_cell"}, {"table_id", table.id}, {"record_id", state.record_id()}, {"field_id", field.id}};
    const std::string type = field.type;
    auto &buttons = box.row();
    buttons.button("save_cell", ctx.tr("project.save_cell"), [this, &state, target, type] {
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
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    buttons.button("null_cell", ctx.tr("project.null_cell"), [this, &state, target] {
      Json command = target;
      command["value"] = nullptr;
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    if (version2) {
      buttons.button("unset_cell", ctx.tr("project.unset_cell"), [this, &state, target] {
        Json command = target;
        command["op"] = "unset_cell";
        pending_cell_ = state.apply(Json::array({command}), draft_revision_);
      }).disable(!editable || draft_revision_ != state.project()->revision);
    }
    buttons.button("reload_cell", ctx.tr("project.reload_cell"), [this] {
      draft_identity_.clear();
    });
    box.paragraph(ctx.tr(cell_mode_ == 0 ? "project.cell_hint" : "project.expression_hint"));
  }

  std::string directory_, name_, table_name_, field_name_, unit_, cell_field_;
  std::string cell_text_, draft_identity_, literal_error_;
  std::string expression_, bindings_ = "{}", binding_name_ = "base";
  std::string selected_binding_;
  std::string source_table_, source_record_, source_field_;
  int cell_mode_ = 0;
  int field_type_ = 2;
  int64_t draft_revision_ = -1;
  bool draft_dirty_ = false;
  bool pending_cell_ = false;
};

}  // namespace

std::unique_ptr<Editor> make_project_editor(const EditorType &type)
{
  return std::make_unique<ProjectEditor>(type);
}

}  // namespace stk::app
