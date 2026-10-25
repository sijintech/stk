/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/table_workbench.hh"
#include "stk/app/table_workbench_state.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/shell.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_editor.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/viewer_state.hh"
#include "editors/project_navigation.hh"
#include "editors/path_picker.hh"

#include <algorithm>
#include <cmath>
#include <map>
#include <numeric>
#include <unordered_map>

namespace stk::app {
using io::Json;
namespace {
std::string uuid()
{
  const auto s = new_idempotency_key();
  return s.substr(0, 8) + "-" + s.substr(8, 4) + "-" + s.substr(12, 4) + "-" + s.substr(16, 4) + "-" + s.substr(20);
}
const std::vector<std::string> types = {"text", "integer", "number", "boolean", "json", "date", "url", "single_select", "multi_select", "object"};
const std::vector<std::string> io_formats = {"csv", "xlsx", "json"};
const std::vector<std::string> kinds = {"record", "file", "snapshot_file", "analysis", "simulation", "workflow"};
std::string table_bridge_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
Json default_view()
{
  return {{"version", 1}, {"kind", "grid"}, {"columns", Json::array()},
          {"filters", {{"op", "and"}, {"conditions", Json::array()}}}, {"sorts", Json::array()},
          {"group_field_id", nullptr}, {"row_height", 32}, {"frozen_columns", 1}};
}
std::string value_text(const Json *value)
{
  return !value ? "" : value->is_string() ? value->get<std::string>() : value->dump();
}
std::string literal_text(const Json *value, const ProjectField &field)
{
  // JSON strings must retain their JSON quotes for both the editor and the TSV parser.
  // Human display can omit quotes, but reparsing that display would change "123" to 123.
  return value && field.type == "json" ? value->dump() : value_text(value);
}
std::string choice_label(const ProjectField &field, const std::string &id)
{
  for (const auto &choice : field.options.value("choices", Json::array())) {
    if (io::get_string(choice, "id") == id) { return io::get_string(choice, "label"); }
  }
  return id;
}
std::string display(const ProjectTable &table, int row, int column)
{
  const auto *v = table.cell(row, column);
  const auto &f = table.fields[size_t(column)];
  if (v && f.type == "single_select" && v->is_string()) { return choice_label(f, v->get<std::string>()); }
  if (v && f.type == "multi_select" && v->is_array()) {
    std::string s;
    for (const auto &id : *v) { if (!s.empty()) { s += " · "; } if (id.is_string()) { s += choice_label(f, id.get<std::string>()); } }
    return s;
  }
  if (v && f.type == "object" && v->is_object()) {
    return io::get_string(*v, "kind") + " · " + io::get_string(*v, "id").substr(0, 8);
  }
  return table.text(row, column);
}
bool valid_view_state(const Json &v)
{
  if (!v.is_object() || v.value("version", Json()) != 1 || !v.contains("kind") || !v["kind"].is_string() ||
      (v["kind"] != "grid" && v["kind"] != "board" && v["kind"] != "gallery") ||
      !v.contains("columns") || !v["columns"].is_array() || v["columns"].size() > 1000 ||
      !v.contains("sorts") || !v["sorts"].is_array() || v["sorts"].size() > 16 ||
      !v.contains("filters") || !v.contains("row_height") || !v["row_height"].is_number_integer() ||
      !v.contains("frozen_columns") || !v["frozen_columns"].is_number_integer()) { return false; }
  if (v["row_height"].get<int64_t>() < 24 || v["row_height"].get<int64_t>() > 240 ||
      v["frozen_columns"].get<int64_t>() < 0 || v["frozen_columns"].get<int64_t>() > 1000) { return false; }
  for (const auto &c : v["columns"]) {
    if (!c.is_object() || !c.contains("field_id") || !c["field_id"].is_string() || io::get_string(c, "field_id").size() != 36 ||
        !c.contains("width") || !io::is_finite_number(c["width"]) || c["width"].get<double>() < 48 || c["width"].get<double>() > 2048 ||
        !c.contains("hidden") || !c["hidden"].is_boolean()) { return false; }
  }
  for (const auto &s : v["sorts"]) {
    if (!s.is_object() || io::get_string(s, "field_id").size() != 36 ||
        (io::get_string(s, "direction") != "asc" && io::get_string(s, "direction") != "desc") ||
        (io::get_string(s, "nulls") != "first" && io::get_string(s, "nulls") != "last")) { return false; }
  }
  if (v.contains("group_field_id") && !v["group_field_id"].is_null() && (!v["group_field_id"].is_string() || v["group_field_id"].get_ref<const std::string &>().size() != 36)) { return false; }
  size_t terms = 0;
  std::function<bool(const Json &, int)> filter = [&](const Json &node, int depth) {
    if (++terms > 64 || depth > 6 || !node.is_object()) { return false; }
    const auto op = io::get_string(node, "op");
    if (op == "and" || op == "or") {
      if (!node.contains("conditions") || !node["conditions"].is_array()) { return false; }
      for (const auto &child : node["conditions"]) { if (!filter(child, depth + 1)) { return false; } }
      return true;
    }
    if (io::get_string(node, "field_id").size() != 36) { return false; }
    const std::vector<std::string> basic = {"eq", "ne", "contains", "gt", "gte", "lt", "lte"};
    const std::vector<std::string> empty = {"is_empty", "is_not_empty", "is_null", "is_unset", "is_error"};
    return (std::find(basic.begin(), basic.end(), op) != basic.end() && node.contains("value")) ||
           std::find(empty.begin(), empty.end(), op) != empty.end();
  };
  return filter(v["filters"], 0);
}
}

struct TableWorkbench::Impl {
  std::shared_ptr<void> alive = std::make_shared<int>(0);
  AppStore *store = nullptr;
  std::unique_ptr<TableWorkbenchState> reads;
  ProjectTableEditor advanced;
  std::string identity, project_id, handle, table_id, search, error;
  uint64_t mapping_epoch = 0;
  uint64_t selection_epoch = 0, paste_epoch = 0, object_epoch = 0, schema_epoch = 0, view_epoch = 0, csv_epoch = 0;
  int64_t seen_revision = -1;
  Json view = default_view(), paste_plan, views = Json::array();
  Json restored;
  std::string view_id, view_name, field_name, field_unit, choices_text, table_name, edit_field_id;
  Json edit_field_options = Json::object();
  int field_type = 0, view_kind = 0, group_field = 0, object_kind = 0, candidate_index = -1;
  int offset = 0, total = 0, next_offset = -1;
  int group_column = -1;
  int object_offset = 0;
  std::vector<int> rows, columns;
  ui::TableSelection selection;
  bool details = false, settings = false, new_field = false, new_table = false, paste_modal = false;
  bool object_modal = false, csv_modal = false, help = false, view_changed = false, query_needed = true;
  bool pending_edit = false, dirty = false, append_paste = true;
  bool schema_dirty = false, view_name_dirty = false;
  std::string pending_record, pending_field, object_table, object_record_id, object_field_id;
  std::function<void()> ui_complete;
  int64_t ui_base_revision = -1;
  std::string ui_handle;
  std::string viewer_preset;
  float detail_share = .65f;
  std::string draft_record, draft_field, draft_text, active_field_id, detail_field_id;
  int64_t draft_revision = -1;
  std::string draft_handle, restored_draft_project_id, workspace_schema_mode;
  bool restored_cell_draft = false;
  std::string csv_source, csv_destination, csv_name, csv_sheet, csv_notice_at_open;
  int io_format = 0, io_mode = 0, io_mapping_page = 0;
  bool csv_tsv = false;
  Json csv_preview;
  std::string csv_preview_source, csv_preview_delimiter, csv_preview_format, csv_preview_sheet;
  std::vector<int> csv_column_types;
  std::vector<std::string> csv_column_units;
  PathPicker source_picker, destination_picker;
  Json filter_rows = Json::array(), sort_rows = Json::array();
  std::string filter_value;
  int filter_field = 0, filter_op = 0, sort_field = 0, sort_direction = 0;
  bool filter_or = false;
  std::unordered_map<std::string, float> widths;

  template<class T> ui::Binding<T> bind(T &member)
  {
    auto *p = &member;
    const auto weak = std::weak_ptr<void>(alive);
    return {[weak, p] { return weak.expired() ? T{} : *p; },
            [weak, p](T v) { if (!weak.expired()) { *p = std::move(v); } }};
  }
  template<class T> ui::Binding<T> schema_bind(T &member, std::function<bool()> current)
  {
    auto result = bind(member); const auto setter = result.set;
    result.set = [this, current, setter](T value) {
      if (current()) { setter(std::move(value)); schema_dirty = true; }
    };
    return result;
  }
  bool selection_dirty() const { return dirty || schema_dirty || advanced.has_unsaved_changes(); }
  bool unsaved() const { return selection_dirty() || view_name_dirty; }
  void show_details(bool visible)
  {
    if (details != visible) { details = visible; ++selection_epoch; }
  }
  bool submit(ProjectState &state, Json commands, std::function<void()> complete)
  {
    if (state.busy() || ui_complete || !state.apply(std::move(commands))) { return false; }
    ui_handle = state.project()->handle; ui_base_revision = state.project()->revision;
    ui_complete = std::move(complete); return true;
  }
  std::function<bool()> fence(ProjectState &state, bool mapping = false)
  {
    auto *owner = store;
    auto *client = owner ? owner->bridge() : nullptr;
    const auto session = table_bridge_session(client);
    return [weak = std::weak_ptr<void>(alive), this, &state, h = state.project()->handle,
            t = state.table_id(), rev = state.project()->revision, epoch = mapping_epoch, mapping,
            owner, client, session] {
      return !weak.expired() && owner && owner->bridge() == client && !session.empty() &&
             table_bridge_session(client) == session && state.loaded() && state.project()->handle == h && state.table_id() == t &&
             state.project()->revision == rev && (!mapping || epoch == mapping_epoch);
    };
  }
  std::function<bool()> detail_fence(ProjectState &state)
  {
    return [base = fence(state, true), this, epoch = selection_epoch, rec = state.record_id(), field = detail_field_id, &state] {
      return base() && details && epoch == selection_epoch && rec == state.record_id() && field == detail_field_id;
    };
  }
  int detail_column(const ProjectState &state) const
  {
    if (!state.table()) { return -1; }
    const auto &fs = state.table()->fields;
    const auto at = std::find_if(fs.begin(), fs.end(), [this](const auto &f) { return f.id == detail_field_id; });
    return at == fs.end() ? -1 : int(at - fs.begin());
  }
  Json detail_target(const ProjectState &state, const std::string &op = "set_cell") const
  {
    return {{"op", op}, {"table_id", state.table_id()}, {"record_id", state.record_id()}, {"field_id", detail_field_id}};
  }
  bool select_detail_field(AppShell &shell, ProjectState &state, const std::string &id)
  {
    if (id == detail_field_id) { return true; }
    if (!available(shell, state)) { return false; }
    detail_field_id = active_field_id = id;
    ++selection_epoch;
    advanced.select_field(id);
    selection = {};
    for (size_t r = 0; r < rows.size(); ++r) {
      if (state.table()->records[size_t(rows[r])].id != state.record_id()) { continue; }
      for (size_t c = 0; c < columns.size(); ++c) {
        if (state.table()->fields[size_t(columns[c])].id == id) { selection = {{int(r), int(c + 1)}, {int(r), int(c + 1)}}; }
      }
    }
    return true;
  }
  bool available(AppShell &shell, ProjectState &state)
  {
    if (selection_dirty() || !shell.project_selection_available(state.project()->id)) {
      error = "project.table.selection_dirty"; return false;
    }
    return true;
  }
  void configure()
  {
    const auto filters = view.value("filters", Json::object());
    const auto op = io::get_string(filters, "op");
    // A published view may use a leaf at its root. Wrap it for the visual builder instead
    // of losing it when a second condition is added. Nested groups remain intact nodes.
    filter_rows = op == "and" || op == "or" ? filters.value("conditions", Json::array()) : Json::array({filters});
    filter_or = op == "or";
    sort_rows = view.value("sorts", Json::array());
    widths.clear();
    for (const auto &c : view.value("columns", Json::array())) {
      widths[io::get_string(c, "field_id")] = float(c.value("width", 160.0));
    }
  }
  void reset_view()
  {
    view = default_view(); view_id.clear(); view_name.clear(); search.clear(); offset = 0;
    configure(); query_needed = true; view_changed = false; ++mapping_epoch;
  }
  void sync(EditorContext &ctx, ProjectState &state)
  {
    store = &ctx.store;
    if (!reads) { reads = std::make_unique<TableWorkbenchState>(ctx.store); }
    reads->sync();
    if (ui_complete && !state.busy()) {
      auto complete = std::move(ui_complete); ui_complete = {};
      if (state.error().empty() && state.project()->handle == ui_handle && state.project()->revision == ui_base_revision + 1) { complete(); }
    }
    const auto id = state.project()->id + ":" + state.table_id();
    const bool same_project = project_id == state.project()->id;
    project_id = state.project()->id;
    if (identity != id) {
      identity = id; handle = state.project()->handle; table_id = state.table_id();
      const auto previous_search = same_project ? search : std::string();
      reset_view(); seen_revision = -1; views = Json::array(); selection = {}; detail_field_id.clear();
      search = previous_search;
      if (restored.is_object() && io::get_string(restored, "project_id") == project_id && io::get_string(restored, "table_id") == state.table_id()) {
        view = restored["view"]; view_id = io::get_string(restored, "view_id"); view_name = io::get_string(restored, "view_name"); search = io::get_string(restored, "search"); configure();
        detail_field_id = io::get_string(restored, "detail_field_id");
        if (restored.contains("workspace_parameters")) {
          const auto &p = restored.at("workspace_parameters");
          view_changed = p.at("view_changed").get<bool>(); offset = p.at("offset").get<int>();
          selection = {{p.at("anchor_row").get<int>(), p.at("anchor_column").get<int>()}, {p.at("active_row").get<int>(), p.at("active_column").get<int>()}};
        }
        restored = nullptr;
      }
      settings = new_field = new_table = paste_modal = object_modal = csv_modal = false;
    }
    if (restored_cell_draft && state.project()->id == restored_draft_project_id && state.table_id() == table_id &&
        state.project()->revision == draft_revision && state.table() &&
        std::any_of(state.table()->fields.begin(), state.table()->fields.end(), [this](const auto &f) { return f.id == draft_field; }) &&
        std::any_of(state.table()->records.begin(), state.table()->records.end(), [this](const auto &r) { return r.id == draft_record; })) {
      draft_handle = state.project()->handle; restored_cell_draft = false;
    }
    if (pending_edit && !state.busy()) {
      pending_edit = false;
      if (state.error().empty() && state.project()->handle == draft_handle && state.project()->revision == draft_revision + 1) {
        dirty = false; draft_text.clear();
        if (!pending_record.empty()) {
          state.select_record(pending_record);
          if (state.record_id() == pending_record) { active_field_id = detail_field_id = pending_field; ++selection_epoch; }
        }
      }
      pending_record.clear(); pending_field.clear();
    }
    if (state.project()->revision != seen_revision || handle != state.project()->handle) {
      seen_revision = state.project()->revision; handle = state.project()->handle;
      query_needed = true; ++mapping_epoch;
    }
    if (state.table()) {
      column_config(*state.table());
      view["frozen_columns"] = std::min(view.value("frozen_columns", 1), int(state.table()->fields.size()));
    }
    if (reads->views().is_null() && !reads->pending("project.table.views.list")) { reads->load_views(); }
    if (reads->views().is_object()) {
      views = reads->views().value("views", Json::array());
      if (!view_id.empty() && !view_changed && !view_name_dirty) {
        const auto at = std::find_if(views.begin(), views.end(), [this](const auto &v) { return io::get_string(v, "id") == view_id; });
        if (at == views.end()) { reset_view(); }
        else {
          auto definition = at->at("definition");
          for (const auto &f : state.table()->fields) {
            auto &cs = definition["columns"];
            if (std::none_of(cs.begin(), cs.end(), [&](const auto &c) { return io::get_string(c, "field_id") == f.id; })) { cs.push_back({{"field_id", f.id}, {"width", 160}, {"hidden", false}}); }
          }
          if (view != definition) { view = std::move(definition); view_name = io::get_string(*at, "name"); configure(); ++mapping_epoch; }
        }
      }
    }
    if (query_needed && reads->supported() && !state.busy()) {
      query_needed = false;
      Json request = {{"offset", offset}, {"limit", 500}};
      if (!view_id.empty() && !view_changed) { request["view_id"] = view_id; }
      else { request["definition"] = view; }
      reads->query(request);
    }
  }
  void rebuild(const ProjectState &state)
  {
    const auto &table = *state.table();
    const auto old_rows = rows, old_columns = columns;
    group_column = -1;
    if (view.contains("group_field_id") && view["group_field_id"].is_string()) {
      for (size_t i = 0; i < table.fields.size(); ++i) { if (table.fields[i].id == view["group_field_id"].get<std::string>()) { group_column = int(i); } }
    }
    rows.clear(); columns.clear();
    const auto &result = reads->query_result();
    total = int(table.records.size()); next_offset = -1;
    const bool queried = result.is_object() && result.value("revision", int64_t(-1)) == state.project()->revision &&
                         io::get_string(result, "table_id") == table.id && !query_needed && !reads->pending("project.table.query");
    if (queried) {
      const auto &ids = result.at("record_ids");
      std::unordered_map<std::string, int> indices;
      for (size_t i = 0; i < table.records.size(); ++i) { indices[table.records[i].id] = int(i); }
      for (const auto &id : ids) { auto it = indices.find(id.get<std::string>()); if (it != indices.end()) { rows.push_back(it->second); } }
      total = result.value("total", int(rows.size()));
      if (result.contains("next_offset") && result["next_offset"].is_number_integer()) { next_offset = result["next_offset"].get<int>(); }
    }
    else if (!reads->supported()) {
      rows.resize(table.records.size()); std::iota(rows.begin(), rows.end(), 0);
    }
    if (!search.empty()) {
      const auto matches = project_table_rows(table, {search, false});
      rows.erase(std::remove_if(rows.begin(), rows.end(), [&matches](int r) {
        return std::find(matches.begin(), matches.end(), r) == matches.end();
      }), rows.end());
    }
    for (const auto &c : view.value("columns", Json::array())) {
      if (c.value("hidden", false)) { continue; }
      const auto id = io::get_string(c, "field_id");
      for (size_t i = 0; i < table.fields.size(); ++i) { if (table.fields[i].id == id) { columns.push_back(int(i)); break; } }
    }
    // New columns remain visible until explicitly hidden. A saved view never loses their identities.
    for (size_t i = 0; i < table.fields.size(); ++i) {
      const auto &all = view["columns"];
      const bool specified = std::any_of(all.begin(), all.end(), [&](const auto &c) { return io::get_string(c, "field_id") == table.fields[i].id; });
      if (!specified) { columns.push_back(int(i)); }
    }
    const bool active_visible = std::any_of(columns.begin(), columns.end(), [&](int c) { return table.fields[size_t(c)].id == active_field_id; });
    const bool record_visible = std::any_of(rows.begin(), rows.end(), [&](int r) { return table.records[size_t(r)].id == state.record_id(); });
    const bool shared_selection_changed = valid(selection.active) ?
        record(state, selection.active) != state.record_id() || field(state, selection.active).id != active_field_id : active_visible && record_visible;
    if (rows != old_rows || columns != old_columns || shared_selection_changed) {
      ++mapping_epoch;
      selection = {};
      if (active_field_id.empty() && !columns.empty()) { active_field_id = table.fields[size_t(columns.front())].id; }
      for (size_t r = 0; r < rows.size(); ++r) {
        if (table.records[size_t(rows[r])].id != state.record_id()) { continue; }
        for (size_t c = 0; c < columns.size(); ++c) {
          if (table.fields[size_t(columns[c])].id == active_field_id) { selection = {{int(r), int(c + 1)}, {int(r), int(c + 1)}}; }
        }
      }
    }
    std::vector<std::string> visible_ids;
    visible_ids.reserve(rows.size());
    for (const auto r : rows) { visible_ids.push_back(table.records[size_t(r)].id); }
    advanced.set_visible_records(std::move(visible_ids));
  }
  bool valid(ui::TableCell c) const
  { return c.row >= 0 && size_t(c.row) < rows.size() && c.column > 0 && size_t(c.column - 1) < columns.size(); }
  const ProjectField &field(const ProjectState &s, ui::TableCell c) const { return s.table()->fields[size_t(columns[size_t(c.column - 1)])]; }
  std::string record(const ProjectState &s, ui::TableCell c) const { return s.table()->records[size_t(rows[size_t(c.row)])].id; }
  Json target(const ProjectState &s, ui::TableCell c, const std::string &op = "set_cell") const
  { return {{"op", op}, {"table_id", s.table_id()}, {"record_id", record(s, c)}, {"field_id", field(s, c).id}}; }
  bool select(AppShell &shell, ProjectState &state, ui::TableSelection selected)
  {
    if (selected == selection) { return true; }
    if (pending_edit && valid(selected.active)) {
      pending_record = record(state, selected.active); pending_field = field(state, selected.active).id;
      return false;
    }
    if (!valid(selected.active) || !available(shell, state)) { return false; }
    state.select_record(record(state, selected.active));
    if (state.record_id() != record(state, selected.active)) { return false; }
    selection = selected;
    ++selection_epoch;
    active_field_id = field(state, selected.active).id;
    detail_field_id = active_field_id;
    advanced.select_field(field(state, selected.active).id);
    return true;
  }
  std::string edit_value(const ProjectState &state, ui::TableCell cell) const
  {
    if (!valid(cell)) { return {}; }
    if (dirty && draft_record == record(state, cell) && draft_field == field(state, cell).id) { return draft_text; }
    const auto *value = state.table()->cell(rows[size_t(cell.row)], columns[size_t(cell.column - 1)]);
    const auto &type = field(state, cell).type;
    if (value && value->is_null() && (type == "date" || type == "url" || type == "single_select")) { return {}; }
    return literal_text(value, field(state, cell));
  }
  bool commit(ProjectState &state, ui::TableCell c, std::string text)
  {
    if (!valid(c) || state.busy()) { return false; }
    if (dirty && (draft_handle != state.project()->handle || draft_revision != state.project()->revision ||
                  draft_record != record(state, c) || draft_field != field(state, c).id)) { error = "table.draft_stale"; return false; }
    const auto &f = field(state, c);
    std::optional<Json> v;
    if (f.type == "date" || f.type == "url") { v = text.empty() ? Json(nullptr) : Json(text); }
    else if (f.type == "single_select") {
      if (text.empty()) { v = nullptr; }
      std::vector<Json> labels;
      for (const auto &choice : f.options.value("choices", Json::array())) {
        if (text == io::get_string(choice, "id")) { v = choice["id"]; break; }
        if (text == io::get_string(choice, "label")) { labels.push_back(choice["id"]); }
      }
      if (!v && labels.size() == 1) { v = labels.front(); }
      if (!v) { error = "table.choice_invalid"; return false; }
    }
    else { v = project_literal(f.type == "object" || f.type == "multi_select" ? "json" : f.type, text, error); }
    if (!v) { return false; }
    auto cmd = target(state, c); cmd["value"] = *v;
    draft_handle = state.project()->handle; draft_revision = state.project()->revision;
    draft_record = record(state, c); draft_field = f.id; draft_text = std::move(text);
    pending_edit = state.apply(Json::array({cmd}), draft_revision);
    dirty = true;
    return pending_edit;
  }
  void changed_view()
  {
    view["filters"] = {{"op", filter_or ? "or" : "and"}, {"conditions", filter_rows}};
    view["sorts"] = sort_rows; query_needed = true; view_changed = true; offset = 0; ++mapping_epoch;
  }
  void column_config(const ProjectTable &table)
  {
    for (const auto &f : table.fields) {
      auto &cs = view["columns"];
      if (std::none_of(cs.begin(), cs.end(), [&](const auto &c) { return io::get_string(c, "field_id") == f.id; })) {
        cs.push_back({{"field_id", f.id}, {"width", widths.contains(f.id) ? widths[f.id] : 160}, {"hidden", false}});
      }
    }
  }
  Json object_request() const
  {
    Json request = {{"kind", kinds[size_t(object_kind)]}, {"offset", object_offset}, {"limit", 100}};
    if (object_kind == 0) { request["table_id"] = object_table.empty() ? table_id : object_table; }
    return request;
  }
  void paste(ProjectState &state, const std::vector<int> &indices, int first_column, std::string text)
  {
    if (unsaved() || state.busy() || first_column < 1) { error = "project.table.selection_dirty"; return; }
    Json rs = Json::array(), fs = Json::array();
    for (const auto r : indices) { if (r >= 0 && size_t(r) < rows.size()) { rs.push_back(state.table()->records[size_t(rows[size_t(r)])].id); } }
    for (size_t c = size_t(first_column - 1); c < columns.size(); ++c) { fs.push_back(state.table()->fields[size_t(columns[c])].id); }
    paste_plan = nullptr; paste_modal = true; const auto generation = ++paste_epoch;
    reads->plan_paste({{"record_ids", rs}, {"field_ids", fs}, {"text", text}, {"append_rows", append_paste}, {"fit_targets", true}},
      [this, weak = std::weak_ptr<void>(alive), generation](const Json &plan) { if (!weak.expired() && paste_modal && generation == paste_epoch) { paste_plan = plan; } });
  }
  void toolbar(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    auto current = fence(state);
    auto &row = layout.row(true);
    std::vector<std::string> names, ids;
    for (const auto &t : state.tables()) { names.push_back(t.name); ids.push_back(t.id); }
    row.dropdown("table", names, {[&state, ids] {
      const auto it = std::find(ids.begin(), ids.end(), state.table_id()); return it == ids.end() ? -1 : int(it - ids.begin());
    }, [this, current, shell = &ctx.area.shell(), &state, ids](int i) {
      if (current() && i >= 0 && size_t(i) < ids.size() && ids[size_t(i)] != state.table_id() && available(*shell, state)) { state.select_table(ids[size_t(i)]); }
    }}).width(9);
    row.button("table_new", "+", [this, current] { if (current()) { ++schema_epoch; new_table = true; } }).width(1.5f).disable(state.busy() || schema_dirty).tip(ctx.tr("project.add_table"));
    row.text_field("table_search", {[this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? "" : search; },
        [this, current](std::string s) { if (current() && !selection_dirty()) { search = std::move(s); ++mapping_epoch; } }},
        {.placeholder = std::string(ctx.tr("table.search")), .max_length = 256}).width(8);
    row.button("table_settings", ctx.tr("table.views"), [this, current] { if (current()) { ++view_epoch; settings = true; } }).width(4).disable(state.busy());
    row.button("table_details", ctx.tr("table.detail"), [this, current] { if (current()) { show_details(!details); } }).width(4);
    row.menu_button("table_more", ctx.tr("table.more"), {
      {std::string(ctx.tr("project.add_field")), [this, current] { if (current()) { ++schema_epoch; new_field = true; } }},
      {std::string(ctx.tr("project.csv.title")), [this, current, &state] { if (current()) { ++csv_epoch; io_mode = 2; csv_notice_at_open = state.notice(); csv_modal = true; } }},
      {std::string(ctx.tr("table.help")), [this, current] { if (current()) { help = true; } }}
    }).width(3);
    // Saved views are a one-click tab switch. The implicit all-records view is always present.
    std::vector<std::string> labels = {std::string(ctx.tr("table.all"))}, vids = {""};
    for (const auto &v : views) { labels.push_back(io::get_string(v, "name")); vids.push_back(io::get_string(v, "id")); }
    auto &viewrow = layout.row(true);
    viewrow.tabs("table_views", labels, {[this, weak = std::weak_ptr<void>(alive), vids] {
      if (weak.expired()) { return 0; } auto at = std::find(vids.begin(), vids.end(), view_id); return at == vids.end() ? 0 : int(at - vids.begin());
    }, [this, current, shell = &ctx.area.shell(), &state, vids](int i) {
      if (!current() || i < 0 || size_t(i) >= vids.size() || !available(*shell, state)) { return; }
      reset_view(); view_id = vids[size_t(i)];
      for (const auto &v : views) { if (io::get_string(v, "id") == view_id) { view = v.at("definition"); view_name = io::get_string(v, "name"); configure(); break; } }
    }});
    viewrow.button("table_io", ctx.tr("table.io.import"), [this, current, &state] {
      if (current()) { ++csv_epoch; io_mode = 0; csv_notice_at_open = state.notice(); csv_modal = true; }
    }).width(3.5f).disable(state.busy());
    viewrow.button("table_export", ctx.tr("table.io.export"), [this, current, &state] {
      if (current()) { ++csv_epoch; io_mode = 1; csv_notice_at_open = state.notice(); csv_modal = true; }
    }).width(3.5f).disable(state.busy());
    viewrow.button("table_add_record", ctx.tr("table.add_record"), [this, current, shell = &ctx.area.shell(), &state] {
      if (current() && available(*shell, state)) { state.apply(Json::array({{{"op", "add_record"}, {"table_id", state.table_id()}}})); }
    }).width(5).disable(state.busy());
    viewrow.button("table_add_field", ctx.tr("table.add_field"), [this, current] { if (current()) { ++schema_epoch; new_field = true; } }).width(5).disable(state.busy() || schema_dirty);
  }
  void grid(ui::Layout &layout, EditorContext &ctx, ProjectState &state, float height)
  {
    const auto &t = *state.table();
    auto current = fence(state, true);
    ui::TableSpec spec;
    spec.columns.push_back({group_column >= 0 ? std::string(ctx.tr("table.group")) + " / #" : "#", group_column >= 0 ? 8.0f : 2.5f, false, false, "__record_number"});
    for (const auto c : columns) { const auto &f = t.fields[size_t(c)];
      spec.columns.push_back({f.name + (f.unit.empty() ? "" : " · " + f.unit), 7, true, f.type == "integer" || f.type == "number", f.id});
    }
    spec.row_height = std::clamp(float(view.value("row_height", 32)) / 32.0f, .5f, 12.0f);
    spec.rows = int(rows.size()); spec.visible_rows = std::max(2.0f, height / spec.row_height);
    spec.data_version = state.version() + mapping_epoch * 1000003;
    spec.frozen_columns = view.value("frozen_columns", 1);
    spec.cell = [this, current, &state](int r, int c) {
      if (!current() || r < 0 || size_t(r) >= rows.size()) { return std::string(); }
      return c == 0 ? (group_column < 0 ? "" : display(*state.table(), rows[size_t(r)], group_column) + " · ") + std::to_string(offset + r + 1)
                    : valid({r, c}) ? display(*state.table(), rows[size_t(r)], columns[size_t(c - 1)]) : std::string();
    };
    spec.compare = [this, current, &state](int a, int b, int c) {
      return current() && valid({a, c}) && valid({b, c}) ? state.table()->compare(rows[size_t(a)], rows[size_t(b)], columns[size_t(c - 1)]) : 0;
    };
    spec.on_sort = [this, current, &state](int c, bool ascending) {
      if (!current() || selection_dirty() || c <= 0 || size_t(c - 1) >= columns.size()) { return; }
      sort_rows = Json::array({{{"field_id", state.table()->fields[size_t(columns[size_t(c - 1)])].id},
                                {"direction", ascending ? "asc" : "desc"}, {"nulls", "last"}}}); changed_view();
    };
    spec.selected = {[this, current, &state] {
      if (!current()) { return -1; } for (size_t i = 0; i < rows.size(); ++i) { if (state.table()->records[size_t(rows[i])].id == state.record_id()) { return int(i); } } return -1;
    }, [this, current, shell = &ctx.area.shell(), &state](int r) {
      if (!current() || r < 0 || size_t(r) >= rows.size()) { return; }
      if (!columns.empty()) { select(*shell, state, {{r, 1}, {r, 1}}); }
      else if (available(*shell, state)) {
        const auto id = state.table()->records[size_t(rows[size_t(r)])].id;
        state.select_record(id);
        if (state.record_id() == id) { selection = {}; ++selection_epoch; show_details(true); }
      }
    }};
    spec.on_cell_select = [this, current, shell = &ctx.area.shell(), &state](int r, int c) { if (current()) { select(*shell, state, {{r, c}, {r, c}}); } };
    spec.column_width = [this, current](std::string_view key) -> std::optional<float> {
      if (!current()) { return {}; } const auto at = widths.find(std::string(key)); return at == widths.end() ? std::nullopt : std::optional<float>(at->second / 20.0f);
    };
    spec.on_column_width = [this, current, &state](std::string_view key, float w) {
      if (!current() || key == "__record_number") { return; } widths[std::string(key)] = std::clamp(w * 20.0f, 48.0f, 2048.0f);
      column_config(*state.table()); for (auto &c : view["columns"]) { if (io::get_string(c, "field_id") == key) { c["width"] = widths[std::string(key)]; } } view_changed = true;
    };
    spec.column_menu = [this, current, &state, store = &ctx.store](int c) {
      std::vector<ui::MenuEntry> entries;
      if (!current() || c <= 0 || size_t(c - 1) >= columns.size()) { return entries; }
      const auto id = state.table()->fields[size_t(columns[size_t(c - 1)])].id;
      for (const auto &[label, direction] : std::vector<std::pair<std::string, std::string>>{{"table.sort_asc", "asc"}, {"table.sort_desc", "desc"}}) {
        entries.push_back({std::string(store->tr(label)), [this, current, id, direction] {
          if (current() && !selection_dirty()) { sort_rows = Json::array({{{"field_id", id}, {"direction", direction}, {"nulls", "last"}}}); changed_view(); }
        }});
      }
      entries.push_back({std::string(store->tr("table.hide_column")), [this, current, id, &state] {
        if (!current() || selection_dirty()) { return; } column_config(*state.table());
        for (auto &col : view["columns"]) { if (io::get_string(col, "field_id") == id) { col["hidden"] = true; } } changed_view();
      }});
      entries.push_back({std::string(store->tr("table.edit_field")), [this, current, id, &state] {
        if (!current() || selection_dirty()) { return; }
        for (const auto &f : state.table()->fields) { if (f.id == id) {
          edit_field_id = id; field_name = f.name; field_unit = f.unit; edit_field_options = f.options;
          const auto at = std::find(types.begin(), types.end(), f.type); field_type = at == types.end() ? 0 : int(at - types.begin());
          choices_text.clear(); for (const auto &choice : f.options.value("choices", Json::array())) { choices_text += io::get_string(choice, "label") + "\n"; }
          ++schema_epoch; new_field = true; break;
        } }
      }});
      return entries;
    };
    if (columns.empty()) { layout.table("records", std::move(spec)); return; }
    ui::TableGridSpec grid;
    grid.first_column = 1;
    grid.selection = {[this, current] { return current() ? selection : ui::TableSelection{}; },
        [this, current, shell = &ctx.area.shell(), &state](ui::TableSelection s) { if (current()) { select(*shell, state, s); } }};
    grid.editable = [this, current, &state](ui::TableCell c) {
      if (!current() || state.busy() || !valid(c) || advanced.has_unsaved_changes()) { return false; }
      if (state.table()->definition(rows[size_t(c.row)], columns[size_t(c.column - 1)])) {
        show_details(true); advanced.select_field(field(state, c).id); return false;
      }
      return true;
    };
    grid.edit_text = [this, current, &state](ui::TableCell c) { return current() ? edit_value(state, c) : std::string(); };
    grid.on_change = [this, current, &state](ui::TableCell c, std::string s) {
      if (!current() || !valid(c) || pending_edit) { return; }
      if (!dirty) { draft_record = record(state, c); draft_field = field(state, c).id; draft_revision = state.project()->revision; draft_handle = state.project()->handle; }
      if (draft_record == record(state, c) && draft_field == field(state, c).id) { draft_text = std::move(s); dirty = true; }
    };
    grid.on_commit = [this, current, &state](ui::TableCell c, std::string s) { return current() && commit(state, c, std::move(s)); };
    grid.on_cancel = [this, current](ui::TableCell) { if (current() && !pending_edit) { dirty = false; draft_text.clear(); error.clear(); } };
    grid.export_cell = [this, current, &state](int r, int c) {
      return current() && valid({r, c}) ? literal_text(state.table()->cell(rows[size_t(r)], columns[size_t(c - 1)]), field(state, {r, c})) : std::string();
    };
    grid.on_paste = [this, current, &state](const std::vector<int> &rs, int c, std::string text) {
      if (!current()) { return false; } paste(state, rs, c, std::move(text)); return true;
    };
    grid.on_clear = [this, current, shell = &ctx.area.shell(), &state](const std::vector<int> &rs, int first, int count) {
      if (!current() || !available(*shell, state)) { return false; }
      if (rs.size() * size_t(count) > 1000) { error = "table.batch_limit"; return false; }
      Json commands = Json::array();
      for (const int r : rs) { for (int c = first; c < first + count; ++c) { if (!valid({r, c})) { return false; } commands.push_back(target(state, {r, c}, "unset_cell")); } }
      return !commands.empty() && state.apply(commands);
    };
    grid.on_toggle = [this, current, shell = &ctx.area.shell(), &state](ui::TableCell c) {
      if (!current() || !valid(c) || !available(*shell, state) || field(state, c).type != "boolean") { return false; }
      if (state.table()->definition(rows[size_t(c.row)], columns[size_t(c.column - 1)])) { show_details(true); return false; }
      const auto *v = state.table()->cell(rows[size_t(c.row)], columns[size_t(c.column - 1)]);
      auto cmd = target(state, c); cmd["value"] = !(v && v->is_boolean() && v->get<bool>()); return state.apply(Json::array({cmd}));
    };
    grid.cell_style = [this, current, &state](int r, int c) {
      if (!current() || !valid({r, c})) { return ui::TableCellStyle::Text; }
      const auto &type = field(state, {r, c}).type;
      const auto *v = state.table()->cell(rows[size_t(r)], columns[size_t(c - 1)]);
      return type == "boolean" && v && v->is_boolean() ? ui::TableCellStyle::Checkbox
           : type == "single_select" || type == "multi_select" || type == "object" ? ui::TableCellStyle::Badge : ui::TableCellStyle::Text;
    };
    grid.checked = [this, current, &state](int r, int c) {
      if (!current() || !valid({r, c})) { return false; } const auto *v = state.table()->cell(rows[size_t(r)], columns[size_t(c - 1)]); return v && v->is_boolean() && v->get<bool>();
    };
    spec.grid = std::move(grid);
    layout.table("records", std::move(spec));
  }
  void footer(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    auto &row = layout.row(true);
    row.label(std::to_string(rows.size()) + " / " + std::to_string(total) + " " + std::string(ctx.tr("table.records")));
    const auto current = fence(state);
    row.button("table_prev", "‹", [this, current] { if (current() && !selection_dirty()) { offset = std::max(0, offset - 500); query_needed = true; ++mapping_epoch; } }).width(1.5f).disable(offset == 0);
    row.button("table_next", "›", [this, current] { if (current() && !selection_dirty() && next_offset >= 0) { offset = next_offset; query_needed = true; ++mapping_epoch; } }).width(1.5f).disable(next_offset < 0);
    if (valid(selection.active)) {
      const auto &f = field(state, selection.active);
      row.label(f.name + (f.unit.empty() ? "" : " · " + f.unit));
      if (f.type == "number" || f.type == "integer") {
        long double sum = 0; int n = 0, missing = 0, errors = 0;
        for (const auto r : rows) {
          const auto *v = state.table()->cell(r, columns[size_t(selection.active.column - 1)]);
          const auto *e = state.table()->evaluation(r, columns[size_t(selection.active.column - 1)]);
          if (e && io::get_string(*e, "state") == "error") { ++errors; }
          else if (v && v->is_number()) { sum += v->get<long double>(); ++n; }
          else { ++missing; }
        }
        // Approximate aggregate only; persisted integer cells and ordering retain exact int64 values.
        row.label("Σ≈" + std::to_string(double(sum)) + " · n=" + std::to_string(n) + " · ∅=" + std::to_string(missing) + " · !=" + std::to_string(errors));
      }
    }
    if (view_changed) { row.label(ctx.tr("table.view_unsaved")); }
  }
  void view_dialog(EditorContext &ctx, ProjectState &state)
  {
    if (!settings) { return; }
    const auto current = [base = fence(state), this, generation = view_epoch] { return base() && settings && generation == view_epoch; };
    auto close = [this, weak = std::weak_ptr<void>(alive), generation = view_epoch] { if (!weak.expired() && generation == view_epoch) { ++view_epoch; settings = false; } };
    auto &box = ctx.ui->modal("table_view_dialog", ctx.tr("table.views"), close, {.width_units = 38});
    box.enabled(!state.busy());
    if (state.project()->format_version < 14) {
      box.paragraph(ctx.tr("table.upgrade"));
      box.button("table_upgrade", ctx.tr("project.upgrade"), [current, &state] { if (current()) { state.upgrade(); } }).disable(state.busy());
    }
    box.prop(ctx.tr("table.view_name")).text_field("table_view_name", {[this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? "" : view_name; },
      [this, current](std::string name) { if (current()) { view_name = std::move(name); view_name_dirty = true; } }});
    const std::vector<std::string> kind_ids = {"grid", "board", "gallery"};
    box.prop(ctx.tr("table.view_kind")).dropdown("table_view_kind", {std::string(ctx.tr("table.grid")), std::string(ctx.tr("table.board")), std::string(ctx.tr("table.gallery"))}, {
      [this, weak = std::weak_ptr<void>(alive), kind_ids] {
        if (weak.expired()) { return 0; } const auto it = std::find(kind_ids.begin(), kind_ids.end(), view.value("kind", "grid")); return it == kind_ids.end() ? 0 : int(it - kind_ids.begin());
      }, [this, current, kind_ids](int i) { if (current() && !selection_dirty() && i >= 0 && i < 3) { view["kind"] = kind_ids[size_t(i)]; changed_view(); } }
    });
    std::vector<std::string> names, ids;
    for (const auto &f : state.table()->fields) { names.push_back(f.name); ids.push_back(f.id); }
    auto group_names = names; group_names.insert(group_names.begin(), std::string(ctx.tr("table.no_group")));
    box.prop(ctx.tr("table.group")).dropdown("table_group", group_names, {
      [this, weak = std::weak_ptr<void>(alive), ids] {
        if (weak.expired() || !view.contains("group_field_id") || !view["group_field_id"].is_string()) { return 0; }
        const auto it = std::find(ids.begin(), ids.end(), view["group_field_id"].get<std::string>()); return it == ids.end() ? 0 : int(it - ids.begin()) + 1;
      }, [this, current, ids](int i) { if (current() && !selection_dirty() && i >= 0 && size_t(i) <= ids.size()) { view["group_field_id"] = i == 0 ? Json(nullptr) : Json(ids[size_t(i - 1)]); changed_view(); } }
    });
    box.prop(ctx.tr("table.freeze")).dropdown("table_freeze", {"0", "1", "2", "3"}, {
      [this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? 0 : view.value("frozen_columns", 1); },
      [this, current](int i) { if (current() && i >= 0 && i <= 3) { view["frozen_columns"] = std::min(i, int(view["columns"].size())); view_changed = true; } }
    });
    box.prop(ctx.tr("table.density")).dropdown("table_density", {std::string(ctx.tr("table.compact")), std::string(ctx.tr("table.normal")), std::string(ctx.tr("table.comfortable"))}, {
      [this, weak = std::weak_ptr<void>(alive)] { if (weak.expired()) { return 1; } const int h = view.value("row_height", 32); return h <= 24 ? 0 : h >= 48 ? 2 : 1; },
      [this, current](int i) { if (current() && i >= 0 && i < 3) { view["row_height"] = i == 0 ? 24 : i == 1 ? 32 : 48; view_changed = true; } }
    });
    if (auto *filter = box.panel("table_filters", ctx.tr("table.filters"), true)) {
      filter->dropdown("table_filter_logic", {std::string(ctx.tr("table.all_conditions")), std::string(ctx.tr("table.any_conditions"))}, {
        [this, weak = std::weak_ptr<void>(alive)] { return !weak.expired() && filter_or ? 1 : 0; },
        [this, current](int i) { if (current() && !selection_dirty()) { filter_or = i == 1; changed_view(); } }});
      const std::vector<std::string> operators = {"eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty", "is_null", "is_unset", "is_error"};
      std::vector<std::string> op_labels; for (const auto &op : operators) { op_labels.emplace_back(ctx.tr("table.filter." + op)); }
      auto &r = filter->row(true);
      r.dropdown("table_filter_field", names, {[this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? 0 : filter_field; },
        [this, current](int i) { if (current()) { filter_field = i; filter_value.clear(); } }});
      r.dropdown("table_filter_op", op_labels, bind(filter_op));
      const ProjectField *selected_field = filter_field >= 0 && size_t(filter_field) < state.table()->fields.size() ? &state.table()->fields[size_t(filter_field)] : nullptr;
      const bool choice_filter = selected_field && (selected_field->type == "single_select" || (selected_field->type == "multi_select" && filter_op == 2));
      if (choice_filter && filter_op < 7) {
        const auto choices = selected_field->options.value("choices", Json::array());
        if (filter_value.empty() && !choices.empty()) { filter_value = io::get_string(choices.front(), "id"); }
        std::vector<std::string> labels; for (const auto &choice : choices) { labels.push_back(io::get_string(choice, "label")); }
        r.dropdown("table_filter_choice", labels, {[this, current, choices] {
          if (!current()) { return -1; } for (size_t i = 0; i < choices.size(); ++i) { if (io::get_string(choices[i], "id") == filter_value) { return int(i); } } return -1;
        }, [this, current, choices](int i) { if (current() && i >= 0 && size_t(i) < choices.size()) { filter_value = io::get_string(choices[size_t(i)], "id"); } }});
      }
      else if (selected_field && selected_field->type == "boolean" && filter_op < 7) {
        if (filter_value != "true" && filter_value != "false") { filter_value = "true"; }
        r.dropdown("table_filter_boolean", {std::string(ctx.tr("table.true")), std::string(ctx.tr("table.false"))}, {
          [this, current] { return current() && filter_value == "false" ? 1 : 0; },
          [this, current](int i) { if (current()) { filter_value = i == 0 ? "true" : "false"; } }});
      }
      else { r.text_field("table_filter_value", bind(filter_value), {.placeholder = std::string(ctx.tr("table.filter_value")), .max_length = 4096}).disable(filter_op >= 7); }
      r.button("table_filter_add", "+", [this, current, ids, operators, &state] {
        if (!current() || selection_dirty() || filter_field < 0 || size_t(filter_field) >= ids.size() || filter_op < 0 || size_t(filter_op) >= operators.size()) { return; }
        const auto id = ids[size_t(filter_field)];
        Json condition = {{"field_id", id}, {"op", operators[size_t(filter_op)]}};
        if (filter_op < 7) {
          const auto &f = state.table()->fields[size_t(filter_field)];
          if (f.type == "text" || f.type == "date" || f.type == "url" || f.type == "single_select" || filter_op == 2) { condition["value"] = filter_value; }
          else { try { condition["value"] = io::parse_json(filter_value); } catch (...) { error = "table.filter_invalid"; return; } }
        }
        filter_rows.push_back(condition); changed_view();
      }).width(2).disable(ids.empty() || filter_rows.size() >= 32);
      for (size_t i = 0; i < filter_rows.size(); ++i) {
        const auto &c = filter_rows[i]; auto at = std::find(ids.begin(), ids.end(), io::get_string(c, "field_id"));
        auto &r2 = filter->scope("filter" + std::to_string(i)).row(true);
        const auto op = io::get_string(c, "op");
        if (op == "and" || op == "or") { r2.label(project_value_summary(c, 512)); }
        else { r2.label((at == ids.end() ? "?" : names[size_t(at - ids.begin())]) + " · " + std::string(ctx.tr("table.filter." + op)) + " " + (c.contains("value") ? project_value_summary(c["value"], 160) : "")); }
        r2.button("remove", "×", [this, current, i] { if (current() && !selection_dirty() && i < filter_rows.size()) { filter_rows.erase(i); changed_view(); } }).width(2);
      }
    }
    if (auto *sort = box.panel("table_sorts", ctx.tr("table.sorts"), true)) {
      auto &r = sort->row(true);
      r.dropdown("table_sort_field", names, bind(sort_field));
      r.dropdown("table_sort_direction", {std::string(ctx.tr("table.sort_asc")), std::string(ctx.tr("table.sort_desc"))}, bind(sort_direction));
      r.button("table_sort_add", "+", [this, current, ids] {
        if (!current() || selection_dirty() || sort_field < 0 || size_t(sort_field) >= ids.size()) { return; }
        const auto id = ids[size_t(sort_field)];
        for (auto &s : sort_rows) { if (io::get_string(s, "field_id") == id) { s["direction"] = sort_direction == 0 ? "asc" : "desc"; changed_view(); return; } }
        sort_rows.push_back({{"field_id", id}, {"direction", sort_direction == 0 ? "asc" : "desc"}, {"nulls", "last"}}); changed_view();
      }).width(2).disable(ids.empty() || sort_rows.size() >= 16);
      for (size_t i = 0; i < sort_rows.size(); ++i) {
        auto at = std::find(ids.begin(), ids.end(), io::get_string(sort_rows[i], "field_id"));
        auto &r2 = sort->scope("sort" + std::to_string(i)).row(true);
        r2.label((at == ids.end() ? "?" : names[size_t(at - ids.begin())]) + " · " + std::string(ctx.tr(sort_rows[i].value("direction", "asc") == "asc" ? "table.sort_asc" : "table.sort_desc")));
        r2.button("remove", "×", [this, current, i] { if (current() && !selection_dirty() && i < sort_rows.size()) { sort_rows.erase(i); changed_view(); } }).width(2);
      }
    }
    if (auto *cols = box.panel("table_columns", ctx.tr("table.columns"), false)) {
      column_config(*state.table());
      for (size_t i = 0; i < view["columns"].size(); ++i) {
        const auto id = io::get_string(view["columns"][i], "field_id");
        const auto at = std::find(ids.begin(), ids.end(), id); if (at == ids.end()) { continue; }
        auto &r = cols->scope("column" + id).row(true);
        r.checkbox("visible", names[size_t(at - ids.begin())], {
          [this, weak = std::weak_ptr<void>(alive), i] { return !weak.expired() && i < view["columns"].size() && !view["columns"][i].value("hidden", false); },
          [this, current, i](bool on) { if (current() && !selection_dirty() && i < view["columns"].size()) { view["columns"][i]["hidden"] = !on; changed_view(); } }});
        r.button("up", "↑", [this, current, i] { if (current() && !selection_dirty() && i > 0 && i < view["columns"].size()) { std::swap(view["columns"][i], view["columns"][i - 1]); changed_view(); } }).width(2).disable(i == 0);
        r.button("down", "↓", [this, current, i] { if (current() && !selection_dirty() && i + 1 < view["columns"].size()) { std::swap(view["columns"][i], view["columns"][i + 1]); changed_view(); } }).width(2).disable(i + 1 == view["columns"].size());
      }
    }
    auto &actions = box.row(true);
    actions.button("table_view_save", ctx.tr("table.save_view"), [this, current, &state] {
      if (!current() || selection_dirty()) { return; }
      const auto id = view_id.empty() ? uuid() : view_id;
      submit(state, Json::array({{{"op", "put_table_view"}, {"id", id}, {"table_id", state.table_id()}, {"name", view_name}, {"definition", view}}}),
        [this, id] { ++view_epoch; view_id = id; settings = false; view_changed = false; view_name_dirty = false; });
    }).disable(state.busy() || state.project()->format_version < 14 || view_name.empty());
    actions.button("table_view_copy", ctx.tr("table.copy_view"), [this, current] { if (current()) { view_id.clear(); view_name += " (2)"; view_changed = true; view_name_dirty = true; } }).disable(view_id.empty());
    actions.button("table_view_delete", ctx.tr("table.delete_view"), [this, current, &state] {
      if (current() && !selection_dirty() && !view_id.empty()) { submit(state, Json::array({{{"op", "delete_table_view"}, {"id", view_id}}}), [this] { reset_view(); settings = false; view_name_dirty = false; }); }
    }).disable(view_id.empty() || state.busy());
    actions.button("table_view_done", ctx.tr("table.done"), close);
    actions.button("table_view_discard", ctx.tr("table.reset_view"), [this, current] { if (current()) { reset_view(); view_name_dirty = false; settings = false; } });
  }
  void field_dialog(EditorContext &ctx, ProjectState &state)
  {
    if (!new_field && !new_table) { return; }
    const auto current = [base = fence(state), this, generation = schema_epoch] { return base() && generation == schema_epoch && (new_field || new_table); };
    auto close = [this, weak = std::weak_ptr<void>(alive), generation = schema_epoch] { if (!weak.expired() && generation == schema_epoch) { ++schema_epoch; new_field = new_table = false; edit_field_id.clear(); schema_dirty = false; field_name.clear(); field_unit.clear(); choices_text.clear(); table_name.clear(); edit_field_options = Json::object(); } };
    auto &box = ctx.ui->modal("table_schema_dialog", ctx.tr(new_table ? "project.add_table" : "project.add_field"), close, {.width_units = 30});
    box.enabled(!state.busy());
    if (new_table) {
      box.text_field("table_name", schema_bind(table_name, current), {.placeholder = std::string(ctx.tr("project.table_name"))});
      box.button("add_table", ctx.tr("project.add_table"), [this, current, &state] {
        if (current()) {
          const auto id = uuid();
          submit(state, Json::array({{{"op", "create_table"}, {"id", id}, {"name", table_name}}}), [this, &state, id] {
            new_table = false; table_name.clear(); schema_dirty = false; state.select_table(id);
          });
        }
      }).disable(state.busy() || table_name.empty());
      box.button("table_schema_cancel", ctx.tr("table.cancel"), close);
      return;
    }
    box.prop(ctx.tr("project.field_name")).text_field("field_name", schema_bind(field_name, current));
    std::vector<std::string> labels; for (const auto &t : types) { labels.emplace_back(ctx.tr("project.type." + t)); }
    box.prop(ctx.tr("project.field_type")).dropdown("field_type", labels, schema_bind(field_type, current));
    const bool numeric = field_type == 1 || field_type == 2;
    if (numeric) { box.prop(ctx.tr("project.unit")).text_field("unit", schema_bind(field_unit, current)); }
    if (field_type == 7 || field_type == 8) {
      box.paragraph(ctx.tr("table.choices_hint"));
      if (edit_field_id.empty()) { box.text_area("table_choices", schema_bind(choices_text, current), {.max_length = 8192, .visible_lines = 5}); }
      else {
        if (!edit_field_options.contains("choices")) { edit_field_options["choices"] = Json::array(); }
        const auto choices = edit_field_options["choices"];
        for (size_t i = 0; i < choices.size(); ++i) {
          const auto id = io::get_string(choices[i], "id");
          auto &row = box.scope("option" + id).row(true);
          row.text_field("label", {[this, weak = std::weak_ptr<void>(alive), id] {
            if (!weak.expired()) { for (const auto &c : edit_field_options["choices"]) { if (io::get_string(c, "id") == id) { return io::get_string(c, "label"); } } } return std::string();
          }, [this, current, id](std::string label) { if (current()) { for (auto &c : edit_field_options["choices"]) { if (io::get_string(c, "id") == id) { c["label"] = label; schema_dirty = true; } } } }});
          row.button("up", "↑", [this, current, id] {
            if (!current()) { return; } auto &cs = edit_field_options["choices"];
            for (size_t n = 1; n < cs.size(); ++n) { if (io::get_string(cs[n], "id") == id) { std::swap(cs[n], cs[n - 1]); schema_dirty = true; break; } }
          }).width(2).disable(i == 0);
          row.button("remove", "×", [this, current, id] {
            if (!current()) { return; } auto &cs = edit_field_options["choices"];
            for (auto it = cs.begin(); it != cs.end(); ++it) { if (io::get_string(*it, "id") == id) { cs.erase(it); schema_dirty = true; break; } }
          }).width(2);
        }
        box.button("table_choice_add", ctx.tr("table.add_choice"), [this, current, label = std::string(ctx.tr("table.new_choice"))] {
          if (current() && edit_field_options["choices"].size() < 256) { edit_field_options["choices"].push_back({{"id", uuid()}, {"label", label}, {"color", "#5B8FF9"}}); schema_dirty = true; }
        });
      }
    }
    if (field_type == 9) {
      box.paragraph(ctx.tr("table.object_hint"));
      if (!edit_field_options.contains("kinds")) { edit_field_options["kinds"] = kinds; }
      for (const auto &kind : kinds) {
        box.checkbox("table_allowed_" + kind, ctx.tr("table.object." + kind), {
          [this, current, kind] { if (!current()) { return false; } const auto &ks = edit_field_options["kinds"]; return std::find(ks.begin(), ks.end(), Json(kind)) != ks.end(); },
          [this, current, kind](bool on) {
            if (!current()) { return; } auto &ks = edit_field_options["kinds"]; auto at = std::find(ks.begin(), ks.end(), Json(kind));
            if (on && at == ks.end()) { ks.push_back(kind); } else if (!on && at != ks.end()) { ks.erase(at); } schema_dirty = true;
          }});
      }
    }
    if (field_type >= 5 && state.project()->format_version < 14) { box.paragraph(ctx.tr("table.upgrade")); }
    box.button("add_field", ctx.tr("project.add_field"), [this, current, &state] {
      if (!current() || field_type < 0 || size_t(field_type) >= types.size()) { return; }
      Json cmd = {{"op", "add_field"}, {"table_id", state.table_id()}, {"name", field_name}, {"type", types[size_t(field_type)]}};
      if ((field_type == 1 || field_type == 2) && !field_unit.empty()) { cmd["unit"] = field_unit; }
      if (field_type >= 5) {
        Json options = {{"version", 1}};
        if (field_type == 7 || field_type == 8) {
          options["choices"] = Json::array();
          size_t start = 0;
          while (start < choices_text.size()) {
            const auto end = choices_text.find('\n', start); auto label = choices_text.substr(start, end == std::string::npos ? end : end - start);
            if (!label.empty() && label.back() == '\r') { label.pop_back(); }
            if (!label.empty()) {
              options["choices"].push_back({{"id", uuid()}, {"label", label}, {"color", "#5B8FF9"}});
            }
            if (end == std::string::npos) { break; } start = end + 1;
          }
          if (!edit_field_id.empty()) { options["choices"] = edit_field_options["choices"]; }
        }
        if (field_type == 9) { options["kinds"] = edit_field_options.value("kinds", Json(kinds)); }
        cmd["options"] = options;
      }
      Json commands = Json::array({cmd});
      if (!edit_field_id.empty()) {
        commands = Json::array({{{"op", "rename_field"}, {"id", edit_field_id}, {"name", field_name}},
            {{"op", "set_field_schema"}, {"id", edit_field_id}, {"type", types[size_t(field_type)]},
              {"unit", (field_type == 1 || field_type == 2) && !field_unit.empty() ? Json(field_unit) : Json(nullptr)},
              {"options", cmd.value("options", Json{{"version", 1}})}}});
      }
      submit(state, commands, [this] { new_field = false; edit_field_id.clear(); field_name.clear(); field_unit.clear(); choices_text.clear(); edit_field_options = Json::object(); schema_dirty = false; });
    }).disable(state.busy() || field_name.empty() || (field_type >= 5 && state.project()->format_version < 14));
    box.button("table_schema_cancel", ctx.tr("table.cancel"), close);
  }
  void paste_dialog(EditorContext &ctx, ProjectState &state)
  {
    if (!paste_modal) { return; }
    auto close = [this, weak = std::weak_ptr<void>(alive), generation = paste_epoch] { if (!weak.expired() && generation == paste_epoch) { ++paste_epoch; paste_modal = false; paste_plan = nullptr; } };
    auto &box = ctx.ui->modal("table_paste_dialog", ctx.tr("table.paste_preview"), close, {.width_units = 34});
    if (!reads->error().empty()) { box.paragraph(reads->error()); }
    if (!paste_plan.is_object()) { box.label(ctx.tr(reads->busy() ? "table.validating" : "table.no_plan")); return; }
    box.label(std::to_string(paste_plan.value("rows", 0)) + " × " + std::to_string(paste_plan.value("columns", 0)) + " · " + std::to_string(paste_plan.value("command_count", 0)) + " " + std::string(ctx.tr("table.commands")));
    box.paragraph(ctx.tr("table.paste_hint"));
    ui::TableSpec preview;
    preview.columns = {{std::string(ctx.tr("project.field")), 10, false}, {std::string(ctx.tr("project.value")), 18, false}};
    const Json commands = paste_plan.value("commands", Json::array());
    preview.rows = int(commands.size()); preview.visible_rows = std::min(8, std::max(2, int(commands.size())));
    preview.cell = [commands](int r, int c) { const auto &cmd = commands.at(size_t(r)); return c == 0 ? io::get_string(cmd, "field_id", io::get_string(cmd, "op")) : cmd.contains("value") ? project_value_summary(cmd["value"], 512) : io::get_string(cmd, "op"); };
    box.table("table_paste_cells", std::move(preview));
    const auto source = reads->scope();
    box.button("table_paste_apply", ctx.tr("table.paste_apply"), [this, weak = std::weak_ptr<void>(alive), source, &state, commands, generation = paste_epoch] {
      if (!weak.expired() && paste_modal && generation == paste_epoch && reads->current(source) && !selection_dirty()) {
        submit(state, commands, [this, generation] { if (generation == paste_epoch) { ++paste_epoch; paste_modal = false; paste_plan = nullptr; } });
      }
    }).disable(state.busy() || paste_plan.value("base_revision", int64_t(-1)) != state.project()->revision);
    box.button("table_paste_cancel", ctx.tr("table.cancel"), close);
  }
  void object_dialog(EditorContext &ctx, ProjectState &state)
  {
    if (!object_modal) { return; }
    const int column = detail_column(state);
    if (!details || state.selected_record() < 0 || column < 0 || state.record_id() != object_record_id || detail_field_id != object_field_id) {
      object_modal = false; ++object_epoch; return;
    }
    const auto &f = state.table()->fields[size_t(column)];
    if (f.type != "object" || state.table()->definition(state.selected_record(), column)) { object_modal = false; ++object_epoch; return; }
    const auto current = [base = detail_fence(state), this, generation = object_epoch] { return base() && object_modal && generation == object_epoch; };
    auto close = [this, weak = std::weak_ptr<void>(alive), generation = object_epoch] { if (!weak.expired() && generation == object_epoch) { ++object_epoch; object_modal = false; } };
    auto &box = ctx.ui->modal("table_object_dialog", ctx.tr("table.object_picker"), close, {.width_units = 36});
    std::vector<std::string> labels;
    std::vector<int> allowed;
    const auto allowed_kinds = f.options.value("kinds", Json(kinds));
    for (size_t i = 0; i < kinds.size(); ++i) {
      if (std::find(allowed_kinds.begin(), allowed_kinds.end(), Json(kinds[i])) != allowed_kinds.end()) {
        allowed.push_back(int(i)); labels.emplace_back(ctx.tr("table.object." + kinds[i]));
      }
    }
    box.dropdown("table_object_kind", labels, {[this, weak = std::weak_ptr<void>(alive), allowed] {
      if (weak.expired()) { return -1; } const auto at = std::find(allowed.begin(), allowed.end(), object_kind);
      return at == allowed.end() ? -1 : int(at - allowed.begin());
    },
      [this, current, allowed](int i) { if (current() && i >= 0 && size_t(i) < allowed.size()) { ++object_epoch; object_offset = 0; object_kind = allowed[size_t(i)]; candidate_index = -1; reads->object_candidates(object_request()); } }});
    if (object_kind == 0) {
      std::vector<std::string> table_names, table_ids;
      for (const auto &t : state.tables()) { table_names.push_back(t.name); table_ids.push_back(t.id); }
      box.prop(ctx.tr("project.table")).dropdown("table_object_table", table_names, {
        [this, weak = std::weak_ptr<void>(alive), table_ids] {
          if (weak.expired()) { return -1; } const auto at = std::find(table_ids.begin(), table_ids.end(), object_table.empty() ? table_id : object_table);
          return at == table_ids.end() ? -1 : int(at - table_ids.begin());
        }, [this, current, table_ids](int i) {
          if (current() && i >= 0 && size_t(i) < table_ids.size()) { ++object_epoch; object_offset = 0; object_table = table_ids[size_t(i)]; candidate_index = -1; reads->object_candidates(object_request()); }
        }});
    }
    const auto result = reads->candidates();
    const auto items = result.is_object() ? result.value("items", Json::array()) : Json::array();
    if (items.empty()) { box.paragraph(ctx.tr("table.object_empty")); }
    ui::ListSpec list;
    list.count = int(items.size()); list.rows = 8;
    list.text = [items](int i) { return io::get_string(items.at(size_t(i)), "label") + " · " + io::get_string(items.at(size_t(i)), "state"); };
    list.selected = {[this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? -1 : candidate_index; },
                     [this, current](int i) { if (current()) { candidate_index = i; } }};
    box.virtual_list("table_object_candidates", std::move(list));
    auto &pages = box.row(true);
    pages.label(std::to_string(object_offset + int(items.size())) + " / " + std::to_string(result.is_object() ? result.value("total", 0) : 0));
    pages.button("table_object_prev", "‹", [this, current] {
      if (current() && object_offset > 0) { ++object_epoch; object_offset = std::max(0, object_offset - 100); candidate_index = -1; reads->object_candidates(object_request()); }
    }).width(2).disable(object_offset == 0 || reads->pending("project.table.objects.list_candidates"));
    const int next = result.is_object() && result.contains("next_offset") && result["next_offset"].is_number_integer() ? result["next_offset"].get<int>() : -1;
    pages.button("table_object_next", "›", [this, current, next] {
      if (current() && next >= 0) { ++object_epoch; object_offset = next; candidate_index = -1; reads->object_candidates(object_request()); }
    }).width(2).disable(next < 0 || reads->pending("project.table.objects.list_candidates"));
    if (candidate_index >= 0 && size_t(candidate_index) < items.size()) { box.paragraph(project_value_summary(items[size_t(candidate_index)].value("summary", Json::object()), 4096)); }
    box.button("table_object_set", ctx.tr("table.object_use"), [this, current, items, &state, shell = &ctx.area.shell()] {
      if (!current() || !available(*shell, state) || candidate_index < 0 || size_t(candidate_index) >= items.size()) { return; }
      auto cmd = detail_target(state); cmd["value"] = items[size_t(candidate_index)].at("reference");
      if (state.apply(Json::array({cmd}))) { object_modal = false; }
    }).disable(state.busy() || candidate_index < 0 || size_t(candidate_index) >= items.size());
    if (!reads->error().empty()) { box.paragraph(reads->error()); }
  }
  void record_detail(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    const int row = state.selected_record();
    const bool outside_view = std::find(rows.begin(), rows.end(), row) == rows.end();
    if (advanced.has_unsaved_changes() && (row < 0 || state.table()->fields.empty() || detail_column(state) < 0 || outside_view)) {
      layout.paragraph(ctx.tr("project.draft_stale"));
      const auto current = detail_fence(state);
      advanced.cell(layout, ctx, state, false, project_navigation_action(ctx, "review"), false, current);
      advanced.management(layout, ctx, state, false, current, false);
      return;
    }
    if (row < 0 || state.table()->fields.empty()) { layout.paragraph(ctx.tr("table.select_cell")); return; }
    if (outside_view) { layout.paragraph(ctx.tr("table.record_outside_view")); return; }
    if (detail_column(state) < 0) {
      const auto &fs = state.table()->fields;
      const auto at = std::find_if(fs.begin(), fs.end(), [this](const auto &f) { return f.id == active_field_id; });
      detail_field_id = at == fs.end() ? fs.front().id : at->id;
    }
    const int column = detail_column(state);
    advanced.select_field(detail_field_id);
    auto current = detail_fence(state);
    auto &head = layout.row(true);
    head.label(ctx.tr("table.detail"));
    head.button("table_detail_close", "×", [this, current] { if (current()) { show_details(false); } }).width(2);
    std::vector<std::string> field_names, field_ids;
    for (const auto &f : state.table()->fields) {
      const bool hidden = std::none_of(columns.begin(), columns.end(), [&](int c) { return state.table()->fields[size_t(c)].id == f.id; });
      field_names.push_back(f.name + (hidden ? " · " + std::string(ctx.tr("table.field_hidden")) : "")); field_ids.push_back(f.id);
    }
    layout.prop(ctx.tr("project.field")).dropdown("table_detail_field", field_names, {
      [this, weak = std::weak_ptr<void>(alive), field_ids] {
        if (weak.expired()) { return -1; } const auto at = std::find(field_ids.begin(), field_ids.end(), detail_field_id);
        return at == field_ids.end() ? -1 : int(at - field_ids.begin());
      }, [this, current, &state, field_ids, shell = &ctx.area.shell()](int i) {
        if (current() && i >= 0 && size_t(i) < field_ids.size()) { select_detail_field(*shell, state, field_ids[size_t(i)]); }
      }}).disable(state.busy() || selection_dirty());
    const auto &f = state.table()->fields[size_t(column)];
    const auto rec = state.record_id();
    layout.paragraph(f.name + " · " + f.type + (f.unit.empty() ? "" : " · " + f.unit));
    const auto *cell_value = state.table()->cell(row, column);
    const bool derived = state.table()->definition(row, column) != nullptr;
    if (!derived && (f.type == "single_select" || f.type == "multi_select")) {
      const auto choices = f.options.value("choices", Json::array());
      std::vector<std::string> labels = {std::string(ctx.tr("table.empty"))};
      for (const auto &choice : choices) { labels.push_back(io::get_string(choice, "label")); }
      const auto cmd = detail_target(state);
      const Json value = cell_value ? *cell_value : Json(nullptr);
      if (f.type == "single_select") {
        layout.dropdown("table_choice", labels, {[value, choices] {
          for (size_t i = 0; i < choices.size(); ++i) { if (choices[i]["id"] == value) { return int(i + 1); } } return 0;
        }, [this, current, &state, choices, cmd, shell = &ctx.area.shell()](int i) {
          if (!current() || !available(*shell, state) || i < 0 || size_t(i) > choices.size()) { return; }
          auto c = cmd; c["value"] = i == 0 ? Json(nullptr) : choices[size_t(i - 1)]["id"]; state.apply(Json::array({c}));
        }}).disable(state.busy());
      }
      else {
        for (const auto &choice : choices) {
          const auto id = io::get_string(choice, "id");
          layout.checkbox("choice" + id, io::get_string(choice, "label"), {[value, id] { return value.is_array() && std::find(value.begin(), value.end(), Json(id)) != value.end(); },
            [this, current, &state, value, cmd, id, shell = &ctx.area.shell()](bool on) {
              if (!current() || !available(*shell, state)) { return; }
              Json values = value.is_array() ? value : Json::array();
              auto at = std::find(values.begin(), values.end(), Json(id));
              if (on && at == values.end()) { values.push_back(id); } else if (!on && at != values.end()) { values.erase(at); }
              auto c = cmd; c["value"] = values; state.apply(Json::array({c}));
            }}).disable(state.busy());
        }
      }
    }
    if (f.type == "object") {
      if (!derived) {
        const auto allowed = f.options.value("kinds", Json(kinds));
        layout.button("table_pick_object", ctx.tr("table.object_picker"), [this, current, &state, allowed] {
          if (current() && !selection_dirty()) {
            if (std::find(allowed.begin(), allowed.end(), Json(kinds[size_t(object_kind)])) == allowed.end()) {
              for (size_t i = 0; i < kinds.size(); ++i) { if (std::find(allowed.begin(), allowed.end(), Json(kinds[i])) != allowed.end()) { object_kind = int(i); break; } }
            }
            ++object_epoch; object_offset = 0; object_modal = true; candidate_index = -1;
            object_record_id = state.record_id(); object_field_id = detail_field_id; reads->object_candidates(object_request());
          }
        }).disable(state.busy() || selection_dirty());
      }
      const auto *v = cell_value;
      if (v && v->is_object()) {
        layout.paragraph(project_value_summary(*v, 4096));
        layout.button("table_resolve_object", ctx.tr("table.object_resolve"), [this, current, reference = *v] { if (current()) { reads->resolve_object({{"reference", reference}}); } });
        const auto &resolved = reads->resolved_object();
        if (resolved.is_object() && resolved.value("reference", Json()) == *v) {
          layout.paragraph(io::get_string(resolved, "label") + " · " + io::get_string(resolved, "state"));
          layout.paragraph(project_value_summary(resolved.value("summary", Json::object()), 4096));
          if (resolved.contains("reason") && resolved["reason"].is_string()) { layout.paragraph(resolved["reason"].get<std::string>()); }
          if (io::get_string(*v, "kind") == "record" && io::get_string(resolved, "state") == "available") {
            layout.button("table_object_locate", ctx.tr("table.object_locate"), [this, current, &state, reference = *v, shell = &ctx.area.shell()] {
              if (current() && available(*shell, state)) { state.request_select(state.project()->handle, state.project()->revision, io::get_string(reference, "table_id"), io::get_string(reference, "id")); }
            });
          }
          if (io::get_string(*v, "kind") == "file" && io::get_string(resolved, "state") == "available") {
            auto &viewer = ctx.store.viewer(); viewer.refresh_metadata();
            std::vector<std::string> names{std::string(ctx.tr("files.automatic"))}, ids{std::string()};
            for (const auto &preset : viewer.presets()) { names.push_back(preset.name); ids.push_back(preset.id); }
            layout.dropdown("table_object_preset", names, {[this, current, ids] {
              if (!current()) { return 0; } const auto at = std::find(ids.begin(), ids.end(), viewer_preset); return at == ids.end() ? 0 : int(at - ids.begin());
            }, [this, current, ids](int i) { if (current() && i >= 0 && size_t(i) < ids.size()) { viewer_preset = ids[size_t(i)]; } }});
            layout.button("table_object_view", ctx.tr("table.object_view"), [this, current, &state, reference = *v, store = &ctx.store, version = viewer.version()] {
              if (!current() || selection_dirty()) { return; }
              state.view_file_record(io::get_string(reference, "id"), viewer_preset,
                [current, store, version] { return current() && store->viewer().version() == version; });
            }).disable(state.busy() || selection_dirty());
          }
          if ((io::get_string(*v, "kind") == "analysis" || io::get_string(*v, "kind") == "workflow") && io::get_string(resolved, "state") == "available") {
            const auto kind = io::get_string(*v, "kind"), id = io::get_string(*v, "id");
            layout.button("table_object_open", ctx.tr("table.open_object"), [current, kind, id, shell = &ctx.area.shell(), screen = ctx.area.screen()] {
              if (current() && screen) { shell->open_target_later(screen, kind == "analysis" ? kEditorAnalysisGraph : kEditorWorkflow, {{kind + "_id", id}}, current); }
            });
          }
        }
      }
    }
    // Existing source pickers, formulas, exact JSON detail, schema management and sweeps remain
    // independently reusable in the project module. They no longer occupy the grid by default.
    if (derived || std::find(types.begin(), types.begin() + 5, f.type) != types.begin() + 5 || f.type == "date" || f.type == "url") {
      advanced.cell(layout, ctx, state, !state.busy() && !dirty, project_navigation_action(ctx, "review"), false, current);
    }
    else {
      layout.paragraph(cell_value ? project_value_summary(*cell_value, 4096) : std::string(ctx.tr("table.empty")));
      auto &actions = layout.row(true);
      for (const auto &op : {std::string("set_cell"), std::string("unset_cell")}) {
        actions.button(op, ctx.tr(op == "set_cell" ? "project.null_cell" : "project.unset_cell"), [this, current, &state, op, shell = &ctx.area.shell()] {
          if (!current() || !available(*shell, state)) { return; } auto c = detail_target(state, op); if (op == "set_cell") { c["value"] = nullptr; } state.apply(Json::array({c}));
        }).disable(state.busy());
      }
    }
    advanced.sweep(layout, ctx, state, !state.busy() && !dirty, current);
    advanced.management(layout, ctx, state, !state.busy() && !dirty, current, false);
    if (!dirty) {
      layout.button("table_duplicate_record", ctx.tr("table.duplicate"), [this, current, &state, rec, shell = &ctx.area.shell()] {
        if (!current() || !available(*shell, state)) { return; }
        const auto id = uuid(); Json cmds = Json::array({{{"op", "add_record"}, {"table_id", state.table_id()}, {"id", id}}});
        const auto &record = state.table()->records[size_t(state.selected_record())];
        for (const auto &field : state.table()->fields) {
          Json c = {{"table_id", state.table_id()}, {"record_id", id}, {"field_id", field.id}};
          if (record.definitions.contains(field.id) && io::get_string(record.definitions[field.id], "kind") == "reference") { c["op"] = "set_reference"; c["source"] = record.definitions[field.id]["source"]; }
          else if (record.definitions.contains(field.id) && io::get_string(record.definitions[field.id], "kind") == "expression") { c["op"] = "set_expression"; c["expression"] = record.definitions[field.id]["expression"]; c["bindings"] = record.definitions[field.id]["bindings"]; }
          else if (record.values.contains(field.id)) { c["op"] = "set_cell"; c["value"] = record.values[field.id]; }
          else { continue; }
          cmds.push_back(c);
        }
        state.apply(cmds);
      }).disable(state.busy());
    }
  }
  void cards(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    const auto current = fence(state, true);
    const auto &t = *state.table();
    int group = -1;
    if (view.contains("group_field_id") && view["group_field_id"].is_string()) {
      for (size_t i = 0; i < t.fields.size(); ++i) { if (t.fields[i].id == view["group_field_id"].get<std::string>()) { group = int(i); } }
    }
    struct Group { std::string key, label; std::vector<int> indices; };
    std::vector<Group> groups;
    const bool board = view.value("kind", "grid") == "board";
    const bool status_board = board && group >= 0 && t.fields[size_t(group)].type == "single_select";
    const auto choices = status_board ? t.fields[size_t(group)].options.value("choices", Json::array()) : Json::array();
    if (status_board) {
      // Empty configured lanes remain usable and choice renames never change lane identity.
      for (const auto &choice : choices) { groups.push_back({"value:" + choice.at("id").dump(), io::get_string(choice, "label"), {}}); }
    }
    for (size_t r = 0; r < rows.size(); ++r) {
      std::string key = "all", label = std::string(ctx.tr("table.all"));
      if (group >= 0) {
        const auto *value = t.cell(rows[r], group), *evaluation = t.evaluation(rows[r], group);
        if (evaluation && io::get_string(*evaluation, "state") == "error") {
          key = "error:" + evaluation->at("error").dump(); label = "#" + io::get_string(evaluation->at("error"), "code");
        }
        else if (!value) { key = "unset"; label = std::string(ctx.tr("table.value_unset")); }
        else if (value->is_null()) { key = "null"; label = std::string(ctx.tr("table.value_null")); }
        else {
          key = "value:" + value->dump();
          label = t.fields[size_t(group)].type == "json" ? value->dump() : display(t, rows[r], group);
          if (label.empty()) { label = value->dump(); }
        }
      }
      auto at = std::find_if(groups.begin(), groups.end(), [&](const auto &v) { return v.key == key; });
      if (at == groups.end()) { groups.push_back({key, label, {int(r)}}); } else { at->indices.push_back(int(r)); }
    }
    const auto *region = ctx.area.find_region("main");
    const int count = std::clamp(int((region ? region->rect().width() : 600) / (11 * ctx.ui->style().unit)), 1, 4);
    auto &container = layout.grid(board ? std::max(1, std::min(count, int(groups.size()))) : count);
    for (const auto &group_data : groups) {
      const auto &group_label = group_data.label;
      const auto &indices = group_data.indices;
      auto *lane = board ? &container.column() : &container;
      if (board) { lane->label(group_label + " · " + std::to_string(indices.size()) + " " + std::string(ctx.tr("table.on_page"))); }
      for (const int r : indices) {
        const auto record_id = t.records[size_t(rows[size_t(r)])].id;
        auto &card = lane->scope("card" + record_id).box();
        card.label(columns.empty() ? record_id.substr(0, 8) : display(t, rows[size_t(r)], columns.front()));
        for (size_t c = 1; c < std::min<size_t>(columns.size(), 5); ++c) {
          const auto &f = t.fields[size_t(columns[c])]; card.paragraph(f.name + ": " + display(t, rows[size_t(r)], columns[c]));
        }
        if (status_board) {
          const auto *value = t.cell(rows[size_t(r)], group);
          const Json observed = value ? *value : Json(nullptr);
          const bool unset = !value;
          const bool derived = t.definition(rows[size_t(r)], group) != nullptr;
          const auto field_id = t.fields[size_t(group)].id;
          std::vector<std::string> labels = {std::string(ctx.tr("table.value_unset")), std::string(ctx.tr("table.value_null"))};
          for (const auto &choice : choices) { labels.push_back(io::get_string(choice, "label")); }
          card.prop(ctx.tr("table.board_state")).dropdown("table_board_state", labels, {
            [observed, unset, choices] {
              if (unset) { return 0; } if (observed.is_null()) { return 1; }
              for (size_t i = 0; i < choices.size(); ++i) { if (choices[i].at("id") == observed) { return int(i + 2); } } return -1;
            }, [this, current, &state, shell = &ctx.area.shell(), choices, record_id, field_id,
                observed, unset, derived, revision = state.project()->revision](int i) {
              if (!current() || derived || i < 0 || size_t(i) > choices.size() + 1 || !available(*shell, state)) { return; }
              const Json next = i < 2 ? Json(nullptr) : choices[size_t(i - 2)].at("id");
              if ((i == 0 && unset) || (i != 0 && !unset && observed == next)) { return; }
              Json command = {{"op", i == 0 ? "unset_cell" : "set_cell"}, {"table_id", state.table_id()}, {"record_id", record_id}, {"field_id", field_id}};
              if (i != 0) { command["value"] = next; }
              state.apply(Json::array({command}), revision);
            }}).disable(state.busy() || selection_dirty() || derived).tip(ctx.tr(derived ? "table.board_derived" : "table.board_state"));
        }
        card.button("open", ctx.tr("table.open_record"), [this, current, &state, shell = &ctx.area.shell(), record_id] {
          if (!current() || !available(*shell, state)) { return; }
          state.select_record(record_id);
          if (state.record_id() != record_id) { return; }
          if (detail_column(state) < 0 && !state.table()->fields.empty()) { detail_field_id = state.table()->fields.front().id; }
          active_field_id = detail_field_id; selection = {}; ++selection_epoch;
          advanced.select_field(detail_field_id); show_details(true);
        });
      }
    }
  }
  void csv_dialog(EditorContext &ctx, ProjectState &state)
  {
    if (!csv_modal) { return; }
    const auto current = [base = fence(state), this, generation = csv_epoch,
                          selected_format = io_format, selected_sheet = csv_sheet, tsv = csv_tsv] {
      return base() && csv_modal && generation == csv_epoch &&
             selected_format == io_format && selected_sheet == csv_sheet && tsv == csv_tsv;
    };
    auto close = [this, weak = std::weak_ptr<void>(alive), generation = csv_epoch] { if (!weak.expired() && generation == csv_epoch) { ++csv_epoch; csv_modal = false; } };
    const float modal_width = std::min(42.0f, std::max(16.0f, ctx.ui->window_size().x / ctx.ui->style().unit - 1));
    auto &box = ctx.ui->modal("table_csv_dialog", ctx.tr("table.io.title"), close, {.width_units = modal_width});
    if (!state.error().empty()) { box.paragraph(state.error()); }
    // This dialog shows completions from its own opening; historical success notices remain
    // in the shared project header and do not masquerade as the new import/export result.
    if (!state.notice().empty() && state.notice() != csv_notice_at_open) { box.paragraph(state.notice()); }
    box.prop(ctx.tr("table.io.format")).dropdown("table_io_format", {"CSV", "Excel (.xlsx)", "JSON"},
      {[this, weak = std::weak_ptr<void>(alive)] { return weak.expired() ? 0 : io_format; },
       [this, current](int value) {
         if (!current() || value < 0 || value >= int(io_formats.size()) || value == io_format) { return; }
         io_format = value; csv_sheet.clear(); csv_preview = nullptr; ++csv_epoch;
       }});
    const auto format = io_formats[size_t(io_format)];
    const std::string delimiter = csv_tsv ? "\t" : ",";
    if (io_mode != 1) {
    auto &source = box.prop(ctx.tr("project.csv.source")).row(true);
    source.text_field("table_csv_source", bind(csv_source));
    source_picker.button(source, ctx, "table_csv_browse", &csv_source, {.title_key = "project.csv.source_dialog", .still_current = current});
    source_picker.draw_error(box);
    if (format == "csv") { box.checkbox("table_csv_tsv", ctx.tr("project.csv.tsv"), bind(csv_tsv)); }
    if (format == "xlsx" && csv_preview.is_object() && csv_preview.contains("sheets")) {
      std::vector<std::string> sheets;
      for (const auto &sheet : csv_preview.at("sheets")) { sheets.push_back(io::get_string(sheet, "name")); }
      box.prop(ctx.tr("table.io.sheet")).dropdown("table_io_sheet", sheets,
        {[this, weak = std::weak_ptr<void>(alive), sheets] {
          if (weak.expired()) { return -1; }
          const auto found = std::find(sheets.begin(), sheets.end(), csv_sheet);
          return found == sheets.end() ? -1 : int(found - sheets.begin());
        }, [this, current, sheets](int value) {
          if (current() && value >= 0 && size_t(value) < sheets.size() && csv_sheet != sheets[size_t(value)]) {
            csv_sheet = sheets[size_t(value)]; ++csv_epoch;
          }
        }});
    }
    box.button("table_csv_preview", ctx.tr("table.io.preview"), [this, current, delimiter, format] {
      if (!current()) { return; }
      const auto generation = ++csv_epoch;
      const auto paths = platform::split_path_list(csv_source);
      const auto path = paths.size() == 1 ? paths.front() : csv_source;
      Json request = {{"source", path}, {"format", format}, {"limit", 20}};
      if (format == "csv") { request["delimiter"] = delimiter; }
      if (format == "xlsx" && !csv_sheet.empty()) { request["sheet"] = csv_sheet; }
      reads->scoped_call("project.table.io.preview", std::move(request),
        [this, weak = std::weak_ptr<void>(alive), path, delimiter, format, generation](const Json &result) {
          if (weak.expired() || !csv_modal || csv_epoch != generation) { return; }
          csv_preview = result; csv_preview_source = path; csv_preview_delimiter = delimiter;
          csv_preview_format = format; csv_preview_sheet = io::get_string(result, "sheet");
          csv_sheet = csv_preview_sheet;
          csv_column_types.assign(result.at("columns").size(), 0); csv_column_units.assign(result.at("columns").size(), ""); io_mapping_page = 0;
          if (csv_name.empty()) { csv_name = io::get_string(result, "table_name"); }
        });
    }).disable(csv_source.empty() || reads->pending("project.table.io.preview") || state.busy());
    const auto paths = platform::split_path_list(csv_source);
    const bool valid_preview = csv_preview.is_object() && csv_preview_source == (paths.size() == 1 ? paths.front() : csv_source) &&
        csv_preview_format == format && csv_preview_sheet == csv_sheet &&
        (format != "csv" || csv_preview_delimiter == delimiter) && csv_preview.value("revision", int64_t(-1)) == state.project()->revision;
    if (valid_preview) {
      const auto cols = csv_preview.at("columns"); const auto preview_rows = csv_preview.at("rows");
      const bool schema_present = csv_preview.value("schema_present", false);
      box.label(std::to_string(csv_preview.value("total_rows", 0)) + " " + std::string(ctx.tr("table.records")) + " · SHA256 " + io::get_string(csv_preview, "source_sha256").substr(0, 12));
      ui::TableSpec spec; for (const auto &c : cols) { spec.columns.push_back({io::get_string(c, "name"), 7, false}); }
      spec.rows = int(preview_rows.size()); spec.visible_rows = std::min(5, std::max(2, int(preview_rows.size())));
      spec.cell = [preview_rows](int r, int c) { return value_text(&preview_rows.at(size_t(r)).at(size_t(c))); };
      box.table("table_csv_preview_grid", std::move(spec));
      const int mapping_count = std::max(1, std::min(6, int(ctx.ui->window_size().y / ctx.ui->style().unit) - 18));
      const int page_count = (int(cols.size()) + mapping_count - 1) / mapping_count;
      io_mapping_page = std::clamp(io_mapping_page, 0, std::max(0, page_count - 1));
      const size_t mapping_start = size_t(io_mapping_page * mapping_count);
      const size_t mapping_end = std::min(cols.size(), mapping_start + size_t(mapping_count));
      if (page_count > 1) {
        auto &pages = box.row(true);
        pages.button("table_io_columns_prev", "‹", [this, current] { if (current() && io_mapping_page > 0) { --io_mapping_page; } }).width(2).disable(io_mapping_page == 0);
        pages.label(std::to_string(io_mapping_page + 1) + " / " + std::to_string(page_count));
        pages.button("table_io_columns_next", "›", [this, current, page_count] { if (current() && io_mapping_page + 1 < page_count) { ++io_mapping_page; } }).width(2).disable(io_mapping_page + 1 == page_count);
      }
      if (schema_present) {
        box.paragraph(ctx.tr("table.io.schema_hint"));
        if (auto *mapping = box.panel("table_csv_mapping", ctx.tr("table.csv_mapping"), true)) {
          for (size_t i = mapping_start; i < mapping_end; ++i) {
            const auto &column = cols[i];
            mapping->label(io::get_string(column, "name") + " · " + std::string(ctx.tr("project.type." + io::get_string(column, "type"))) +
                (io::get_string(column, "unit").empty() ? "" : " · " + io::get_string(column, "unit")));
          }
        }
      }
      else if (auto *mapping = box.panel("table_csv_mapping", ctx.tr("table.csv_mapping"), true)) {
        std::vector<std::string> labels; for (size_t i = 0; i < 7; ++i) { labels.emplace_back(ctx.tr("project.type." + types[i])); }
        for (size_t i = mapping_start; i < mapping_end; ++i) {
          auto &r = mapping->scope("csv_column" + std::to_string(i)).prop(io::get_string(cols[i], "name")).row(true);
          r.dropdown("type", labels, {[this, weak = std::weak_ptr<void>(alive), i] { return !weak.expired() && i < csv_column_types.size() ? csv_column_types[i] : 0; },
            [this, current, i](int value) { if (current() && i < csv_column_types.size() && value >= 0 && value < 7) { csv_column_types[i] = value; } }});
          r.text_field("unit", {[this, weak = std::weak_ptr<void>(alive), i] { return !weak.expired() && i < csv_column_units.size() ? csv_column_units[i] : ""; },
            [this, current, i](std::string value) { if (current() && i < csv_column_units.size()) { csv_column_units[i] = std::move(value); } }}, {.placeholder = std::string(ctx.tr("project.unit")), .max_length = 64})
              .disable(csv_column_types[i] != 1 && csv_column_types[i] != 2);
        }
      }
      for (const auto &warning : csv_preview.value("warnings", Json::array())) { box.paragraph(warning.get<std::string>()); }
      box.prop(ctx.tr("project.csv.name")).text_field("table_csv_name", bind(csv_name));
      box.paragraph(ctx.tr("table.io.limit"));
      box.button("table_csv_import", ctx.tr("project.csv.import"), [this, current, &state, delimiter, format, cols, schema_present] {
        const auto live_paths = platform::split_path_list(csv_source);
        const auto live_source = live_paths.size() == 1 ? live_paths.front() : csv_source;
        if (!current() || selection_dirty() || live_source != csv_preview_source) { return; }
        Json request = {{"format", format}, {"source", csv_preview_source}, {"table_name", csv_name},
                        {"expected_sha256", io::get_string(csv_preview, "source_sha256")}};
        if (format == "csv") { request["delimiter"] = delimiter; }
        if (format == "xlsx") { request["sheet"] = csv_preview_sheet; }
        if (!schema_present) {
          Json types_map = Json::object(), units_map = Json::object();
          for (size_t i = 0; i < cols.size(); ++i) {
            const auto name = io::get_string(cols[i], "name"); types_map[name] = types[size_t(csv_column_types[i])];
            if ((csv_column_types[i] == 1 || csv_column_types[i] == 2) && !csv_column_units[i].empty()) { units_map[name] = csv_column_units[i]; }
          }
          request["types"] = std::move(types_map); request["units"] = std::move(units_map);
        }
        if (state.import_table_file(std::move(request))) { ++csv_epoch; csv_modal = false; }
      }).disable(state.busy() || selection_dirty() || csv_name.empty() || !csv_preview.value("can_import", false));
    }
    if (!reads->error().empty()) { box.paragraph(reads->error()); }
    }
    if (io_mode == 2) { box.separator(); }
    if (io_mode != 0) {
    box.paragraph(ctx.tr("table.csv_export_hint"));
    if (format == "json") { box.paragraph(ctx.tr("table.io.schema_hint")); }
    if (format == "xlsx") { box.paragraph(ctx.tr("table.io.xlsx_hint")); }
    auto &destination = box.prop(ctx.tr("project.csv.destination")).row(true);
    destination.text_field("table_csv_destination", bind(csv_destination));
    destination_picker.button(destination, ctx, "table_csv_save_as", &csv_destination, {.mode = platform::FileDialogMode::SaveFile,
        .title_key = "project.csv.destination_dialog", .file_name = "table." + format,
        .still_current = [this, current, path = csv_destination] { return current() && path == csv_destination; }});
    destination_picker.draw_error(box);
    box.button("table_csv_export", ctx.tr("project.csv.export"), [this, current, &state, delimiter, format] {
      if (!current() || selection_dirty()) { return; }
      Json request = {{"format", format}, {"destination", csv_destination}, {"table_id", state.table_id()}, {"definition", view}};
      if (format == "csv") { request["delimiter"] = delimiter; }
      state.export_table_file(std::move(request));
    }).disable(state.busy() || selection_dirty() || !state.table() || csv_destination.empty());
    }
    box.button("table_io_close", ctx.tr("table.done"), close);
  }
  void draw(ui::Layout &layout, EditorContext &ctx)
  {
    auto &state = ctx.store.project();
    sync(ctx, state);
    if (!state.table()) {
      if (advanced.has_unsaved_changes()) {
        const auto current = fence(state);
        advanced.cell(layout, ctx, state, false, project_navigation_action(ctx, "review"), false, current);
        advanced.management(layout, ctx, state, false, current, false);
      }
      auto &r = layout.row();
      r.label(ctx.tr("table.no_tables")); r.button("table_first", ctx.tr("project.add_table"), [this, current = fence(state)] { if (current()) { ++schema_epoch; new_table = true; } });
      r.button("table_first_csv", ctx.tr("table.io.title"), [this, current = fence(state), &state] { if (current()) { io_mode = 0; csv_notice_at_open = state.notice(); csv_modal = true; } });
      field_dialog(ctx, state); csv_dialog(ctx, state); return;
    }
    rebuild(state);
    toolbar(layout, ctx, state);
    if (!error.empty()) { layout.paragraph(ctx.tr(error)); }
    if (!reads->error().empty()) { layout.paragraph(reads->error()); }
    if (reads->query_result().is_object()) {
      for (const auto &issue : reads->query_result().value("issues", Json::array())) { if (issue.is_string()) { layout.paragraph(issue.get<std::string>()); } }
    }
    if (schema_dirty && !new_field && !new_table) {
      auto &draft = layout.row(true);
      draft.label(ctx.tr("table.draft"));
      draft.button("table_schema_resume", ctx.tr("table.resume_draft"), [this, current = fence(state)] {
        if (current()) { ++schema_epoch; new_table = workspace_schema_mode == "table"; new_field = !new_table; }
      });
    }
    if (dirty) {
      auto &draft = layout.row(true);
      draft.label(ctx.tr(draft_revision == state.project()->revision && draft_handle == state.project()->handle ? "table.draft" : "table.draft_stale"));
      draft.button("table_draft_resume", ctx.tr("table.resume_draft"), [this, current = fence(state)] { if (current()) { show_details(true); } }).width(6);
      draft.button("table_draft_discard", ctx.tr("table.discard_draft"), [this, current = fence(state)] { if (current() && !pending_edit) { dirty = false; draft_text.clear(); error.clear(); ++mapping_epoch; } }).width(6).disable(pending_edit);
    }
    const auto *region = ctx.area.find_region("main");
    const float height = ((region ? region->rect().height() : 350) / ctx.ui->style().unit) - (dirty ? 7.5f : 6.0f);
    ui::Layout *body = &layout, *detail = nullptr;
    if (details) { auto panes = layout.splitter("table_detail_split", bind(detail_share)); body = panes.first; detail = panes.second; }
    if (view.value("kind", "grid") == "grid") { grid(*body, ctx, state, height); }
    else { cards(*body, ctx, state); }
    if (detail) { record_detail(*detail, ctx, state); }
    footer(layout, ctx, state);
    if (dirty && details) {
      auto &box = ctx.ui->modal("table_draft_dialog", ctx.tr("table.draft"), [this, weak = std::weak_ptr<void>(alive)] { if (!weak.expired()) { show_details(false); } }, {.width_units = 30});
      box.text_area("table_draft_text", bind(draft_text), {.max_length = 65536, .mono = true, .visible_lines = 5});
      box.button("table_draft_save", ctx.tr("project.save_cell"), [this, current = fence(state), &state] { if (current()) { commit(state, selection.active, draft_text); } }).disable(pending_edit || !valid(selection.active) || draft_revision != state.project()->revision || draft_handle != state.project()->handle);
      box.button("table_draft_close", ctx.tr("table.done"), [this, current = fence(state)] { if (current()) { show_details(false); } });
    }
    view_dialog(ctx, state); field_dialog(ctx, state); paste_dialog(ctx, state); object_dialog(ctx, state); csv_dialog(ctx, state);
    if (help) {
      auto close = [this, weak = std::weak_ptr<void>(alive)] { if (!weak.expired()) { help = false; } };
      auto &box = ctx.ui->modal("table_help", ctx.tr("table.help"), close, {.width_units = 32});
      box.paragraph(ctx.tr("table.help_text")); box.button("table_help_close", ctx.tr("table.done"), close);
    }
  }
};

TableWorkbench::TableWorkbench() : impl_(std::make_unique<Impl>()) {}
TableWorkbench::~TableWorkbench() = default;
bool TableWorkbench::has_unsaved_changes() const { return impl_->unsaved(); }
bool TableWorkbench::can_change_project_selection(std::string_view id) const
{ return !((impl_->dirty || impl_->schema_dirty || impl_->view_name_dirty) && impl_->project_id == id) && impl_->advanced.can_change_project_selection(id); }
void TableWorkbench::draw(ui::Layout &layout, EditorContext &ctx) { impl_->draw(layout, ctx); }
Json TableWorkbench::save_state() const
{
  return {{"version", 1}, {"details", impl_->details}, {"detail_share", impl_->detail_share},
          {"project_id", impl_->project_id}, {"table_id", impl_->table_id}, {"view", impl_->view},
          {"view_id", impl_->view_id}, {"view_name", impl_->view_name}, {"search", impl_->search}, {"detail_field_id", impl_->detail_field_id},
          {"io", {{"version", 1}, {"format", io_formats[size_t(impl_->io_format)]}, {"source", impl_->csv_source},
                  {"destination", impl_->csv_destination}, {"name", impl_->csv_name}, {"sheet", impl_->csv_sheet},
                  {"tsv", impl_->csv_tsv}, {"column_types", impl_->csv_column_types}, {"column_units", impl_->csv_column_units}}}};
}
bool TableWorkbench::load_state(const Json &value)
{
  try {
    // Earlier independent Table editors wrote an empty object. Keep the owner's saved layout.
    if (value.is_object() && value.empty()) { return true; }
    if (!value.is_object() || value.value("version", 0) != 1 || value.dump().size() > 262144 ||
        !value.contains("details") || !value["details"].is_boolean() || !value.contains("detail_share") || !io::is_finite_number(value["detail_share"])) { return false; }
    if (value.contains("view") && !valid_view_state(value["view"])) { return false; }
    for (const char *key : {"project_id", "table_id", "view_id", "view_name", "search", "detail_field_id"}) {
      if (value.contains(key) && (!value.at(key).is_string() || value.at(key).get_ref<const std::string &>().size() > 4096)) { return false; }
    }
    if (value.contains("io")) {
      const auto &v = value.at("io");
      if (!v.is_object() || v.value("version", 0) != 1 ||
          std::find(io_formats.begin(), io_formats.end(), io::get_string(v, "format")) == io_formats.end() ||
          !v.contains("tsv") || !v.at("tsv").is_boolean() || !v.contains("column_types") || !v.at("column_types").is_array() || v.at("column_types").size() > 64 ||
          !v.contains("column_units") || !v.at("column_units").is_array() || v.at("column_units").size() != v.at("column_types").size()) { return false; }
      for (const char *key : {"source", "destination", "name", "sheet"}) {
        if (!v.contains(key) || !v.at(key).is_string() || v.at(key).get_ref<const std::string &>().size() > 32768) { return false; }
      }
      for (const auto &type : v.at("column_types")) { if (!type.is_number_integer() || type.get<int64_t>() < 0 || type.get<int64_t>() > 6) { return false; } }
      for (const auto &unit : v.at("column_units")) { if (!unit.is_string() || unit.get_ref<const std::string &>().size() > 64) { return false; } }
    }
    if (value.contains("view")) { impl_->restored = value; }
    impl_->show_details(value["details"].get<bool>()); ++impl_->selection_epoch;
    impl_->detail_share = std::clamp(value["detail_share"].get<float>(), .3f, .8f);
    impl_->detail_field_id = io::get_string(value, "detail_field_id");
    if (value.contains("io")) {
      const auto &v = value.at("io");
      impl_->io_format = int(std::find(io_formats.begin(), io_formats.end(), io::get_string(v, "format")) - io_formats.begin());
      impl_->csv_source = io::get_string(v, "source"); impl_->csv_destination = io::get_string(v, "destination"); impl_->csv_name = io::get_string(v, "name"); impl_->csv_sheet = io::get_string(v, "sheet");
      impl_->csv_tsv = v.at("tsv").get<bool>(); impl_->csv_column_types = v.at("column_types").get<std::vector<int>>(); impl_->csv_column_units = v.at("column_units").get<std::vector<std::string>>();
    }
    return true;
  }
  catch (const std::exception &) { return false; }
}
Json TableWorkbench::save_workspace_state() const
{
  const auto &v = *impl_;
  return {{"version", 1}, {"layout", save_state()}, {"advanced", v.advanced.save_workspace_state()},
          {"parameters", {{"view_changed", v.view_changed}, {"view_name_dirty", v.view_name_dirty}, {"offset", v.offset},
                          {"anchor_row", v.selection.anchor.row}, {"anchor_column", v.selection.anchor.column},
                          {"active_row", v.selection.active.row}, {"active_column", v.selection.active.column},
                          {"filter_value", v.filter_value}, {"filter_field", v.filter_field}, {"filter_op", v.filter_op},
                          {"sort_field", v.sort_field}, {"sort_direction", v.sort_direction},
                          {"object_kind", v.object_kind}, {"object_table", v.object_table}, {"object_offset", v.object_offset},
                          {"append_paste", v.append_paste}, {"active_field_id", v.active_field_id}, {"viewer_preset", v.viewer_preset}}},
          {"draft", {{"dirty", v.dirty}, {"project_id", v.restored_cell_draft ? v.restored_draft_project_id : v.project_id},
                     {"record_id", v.draft_record}, {"field_id", v.draft_field}, {"revision", v.draft_revision}, {"text", v.draft_text}}},
          {"schema", {{"dirty", v.schema_dirty}, {"mode", v.new_table ? "table" : v.new_field ? "field" : v.workspace_schema_mode.empty() ? "field" : v.workspace_schema_mode},
                      {"field_name", v.field_name}, {"field_unit", v.field_unit}, {"field_type", v.field_type},
                      {"choices_text", v.choices_text}, {"table_name", v.table_name}, {"edit_field_id", v.edit_field_id}, {"options", v.edit_field_options}}}};
}
bool TableWorkbench::load_workspace_state(const Json &value)
{
  try {
    if (!value.is_object() || value.value("version", 0) != 1 || value.dump().size() > 2097152 ||
        !value.contains("layout") || !value.contains("advanced") || !value.contains("parameters") || !value.at("parameters").is_object() ||
        !value.contains("draft") || !value.at("draft").is_object() || !value.contains("schema") || !value.at("schema").is_object()) { return false; }
    const auto &p = value.at("parameters"), &d = value.at("draft"), &s = value.at("schema");
    for (const auto *part : {&p, &d, &s}) {
      for (const auto &entry : part->items()) { if (entry.value().is_string() && entry.value().get_ref<const std::string &>().size() > 65536) { return false; } }
    }
    for (const char *key : {"view_changed", "view_name_dirty", "append_paste"}) { if (!p.contains(key) || !p.at(key).is_boolean()) { return false; } }
    for (const char *key : {"filter_value", "object_table", "active_field_id", "viewer_preset"}) { if (!p.contains(key) || !p.at(key).is_string()) { return false; } }
    for (const char *key : {"offset", "anchor_row", "anchor_column", "active_row", "active_column", "filter_field", "filter_op", "sort_field", "sort_direction", "object_kind", "object_offset"}) {
      if (!p.contains(key) || !p.at(key).is_number_integer() || p.at(key).get<int64_t>() < -1 || p.at(key).get<int64_t>() > 10000) { return false; }
    }
    if (p.at("offset").get<int>() < 0 || p.at("filter_op").get<int>() < 0 || p.at("filter_op").get<int>() > 11 ||
        p.at("sort_direction").get<int>() < 0 || p.at("sort_direction").get<int>() > 1 || p.at("object_kind").get<int>() < 0 || p.at("object_kind").get<int>() >= int(kinds.size()) || p.at("object_offset").get<int>() < 0) { return false; }
    for (const char *key : {"project_id", "record_id", "field_id", "text"}) { if (!d.contains(key) || !d.at(key).is_string()) { return false; } }
    if (!d.contains("dirty") || !d.at("dirty").is_boolean() || !d.contains("revision") || !d.at("revision").is_number_integer() || d.at("revision").get<int64_t>() < -1) { return false; }
    for (const char *key : {"mode", "field_name", "field_unit", "choices_text", "table_name", "edit_field_id"}) { if (!s.contains(key) || !s.at(key).is_string()) { return false; } }
    if (!s.contains("dirty") || !s.at("dirty").is_boolean() || (s.at("mode") != "table" && s.at("mode") != "field") ||
        !s.contains("options") || !s.at("options").is_object() || !s.contains("field_type") || !s.at("field_type").is_number_integer() || s.at("field_type").get<int64_t>() < 0 || s.at("field_type").get<int64_t>() >= int(types.size())) { return false; }
    TableWorkbench next;
    if (!next.load_state(value.at("layout")) || !next.impl_->advanced.load_workspace_state(value.at("advanced"))) { return false; }
    auto &v = *next.impl_;
    v.project_id = io::get_string(value.at("layout"), "project_id"); v.table_id = io::get_string(value.at("layout"), "table_id");
    v.view = value.at("layout").value("view", default_view()); v.view_id = io::get_string(value.at("layout"), "view_id"); v.view_name = io::get_string(value.at("layout"), "view_name"); v.search = io::get_string(value.at("layout"), "search"); v.configure();
    v.restored["workspace_parameters"] = p;
    v.view_changed = p.at("view_changed").get<bool>(); v.view_name_dirty = p.at("view_name_dirty").get<bool>(); v.offset = p.at("offset").get<int>();
    v.selection = {{p.at("anchor_row").get<int>(), p.at("anchor_column").get<int>()}, {p.at("active_row").get<int>(), p.at("active_column").get<int>()}};
    v.filter_value = io::get_string(p, "filter_value"); v.filter_field = p.at("filter_field").get<int>(); v.filter_op = p.at("filter_op").get<int>(); v.sort_field = p.at("sort_field").get<int>(); v.sort_direction = p.at("sort_direction").get<int>();
    v.object_kind = p.at("object_kind").get<int>(); v.object_table = io::get_string(p, "object_table"); v.object_offset = p.at("object_offset").get<int>(); v.append_paste = p.at("append_paste").get<bool>(); v.active_field_id = io::get_string(p, "active_field_id"); v.viewer_preset = io::get_string(p, "viewer_preset");
    if (!value.at("layout").contains("detail_field_id")) {
      // Earlier format-1 workspaces let the advanced form select a different field from the grid.
      // Its draft target, rather than the grid cursor, owns the restored record detail identity.
      v.detail_field_id = io::get_string(value.at("advanced"), "cell_field", v.active_field_id);
      if (v.detail_field_id.empty()) { v.detail_field_id = v.active_field_id; }
      v.restored["detail_field_id"] = v.detail_field_id;
    }
    v.dirty = d.at("dirty").get<bool>(); v.restored_draft_project_id = io::get_string(d, "project_id"); v.restored_cell_draft = v.dirty;
    v.draft_record = io::get_string(d, "record_id"); v.draft_field = io::get_string(d, "field_id"); v.draft_text = io::get_string(d, "text"); v.draft_revision = d.at("revision").get<int64_t>();
    v.schema_dirty = s.at("dirty").get<bool>(); v.workspace_schema_mode = io::get_string(s, "mode"); v.field_name = io::get_string(s, "field_name"); v.field_unit = io::get_string(s, "field_unit"); v.field_type = s.at("field_type").get<int>(); v.choices_text = io::get_string(s, "choices_text"); v.table_name = io::get_string(s, "table_name"); v.edit_field_id = io::get_string(s, "edit_field_id"); v.edit_field_options = s.at("options");
    impl_ = std::move(next.impl_); return true;
  }
  catch (const std::exception &) { return false; }
}
}  // namespace stk::app
