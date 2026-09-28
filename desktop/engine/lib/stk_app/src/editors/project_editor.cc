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
    spec.visible_rows = 9;
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
    layout.scope(table.id).table("records", std::move(spec));
    const std::string id = table.id;
    layout.button("add_record", ctx.tr("project.add_record"), [&state, id] {
      state.apply(Json::array({{{"op", "add_record"}, {"table_id", id}}}));
    }).disable(!state.ready() || state.busy());
  }

  void load_cell(ProjectState &state, const ProjectField &field)
  {
    const auto *value = state.table()->cell(state.selected_record(), int(&field - state.table()->fields.data()));
    cell_text_ = !value ? std::string() : value->is_string() ? value->get<std::string>() : value->dump();
    // JSON fields containing a string need JSON quotes; text fields do not.
    if (value && field.type == "json") {
      cell_text_ = value->dump();
    }
    draft_revision_ = state.project()->revision;
    draft_dirty_ = false;
    literal_error_.clear();
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
    box.prop(ctx.tr("project.value")).text_field("cell_value", {
      [this] { return cell_text_; },
      [this](std::string text) { cell_text_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
    }, {.mono = field.type != "text"});
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
      auto value = project_literal(type, cell_text_, literal_error_);
      if (value) {
        Json command = target;
        command["value"] = *value;
        pending_cell_ = state.apply(Json::array({command}), draft_revision_);
      }
    }).disable(!editable || draft_revision_ != state.project()->revision);
    buttons.button("null_cell", ctx.tr("project.null_cell"), [this, &state, target] {
      Json command = target;
      command["value"] = nullptr;
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    buttons.button("reload_cell", ctx.tr("project.reload_cell"), [this] {
      draft_identity_.clear();
    });
    box.paragraph(ctx.tr("project.cell_hint"));
  }

  std::string directory_, name_, table_name_, field_name_, unit_, cell_field_;
  std::string cell_text_, draft_identity_, literal_error_;
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
