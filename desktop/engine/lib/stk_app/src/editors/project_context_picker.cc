/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_context_picker.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"

#include <algorithm>

namespace stk::app {
namespace {
constexpr int page_size = 8;
std::string cell_summary(const ProjectTable &table, int row, int field, size_t max_bytes)
{
  if (const auto *evaluation = table.evaluation(row, field);
      evaluation && io::get_string(*evaluation, "state") == "error") {
    return "#" + io::get_string(evaluation->at("error"), "code");
  }
  const auto *value = table.cell(row, field);
  return (table.definition(row, field) ? "= " : "") +
      (value ? project_value_summary(*value, max_bytes) : std::string());
}
}

void ProjectContextPicker::close()
{
  active_ = false;
  selection_.reset();
  table_.reset();
}

void ProjectContextPicker::begin(ProjectState &state)
{
  if (!state.loaded() || state.busy() || state.discussion().busy() || state.tables().empty()) { return; }
  const auto &table = state.table() ? *state.table() : state.tables().front();
  selection_.pin(state.project()->handle, state.project()->revision, table, state.record_id());
  table_ = std::make_shared<const ProjectTable>(selection_.table());
  title_ = table.name;
  row_page_ = field_page_ = category_ = 0;
  active_ = true;
}

void ProjectContextPicker::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  if (!active_ || !state.project()) { return; }
  auto &box = layout.box();
  box.label(ctx.tr("ai.scope.title"));
  box.paragraph(ctx.tr("ai.scope.hint"));
  const auto generation = selection_.generation();
  std::weak_ptr<bool> weak = alive_;
  const auto live = [this, weak, generation] {
    return weak.lock() && active_ && selection_.generation() == generation;
  };
  const auto valid = [this, live, &state] {
    return live() && state.loaded() && !state.busy() && !state.discussion().busy() &&
        selection_.current(state.project()->handle, state.project()->revision);
  };
  const bool current = selection_.current(state.project()->handle, state.project()->revision);
  const bool enabled = valid();
  const auto table = table_;
  std::vector<std::string> names, ids;
  for (const auto &item : state.tables()) { ids.push_back(item.id); names.push_back(item.name); }
  box.prop(ctx.tr("discussion.table")).dropdown("ai_scope_table", std::move(names), {
    [ids, id = table->id] {
      const auto found = std::find(ids.begin(), ids.end(), id);
      return found == ids.end() ? -1 : int(found - ids.begin());
    }, [this, valid, &state, ids](int index) {
      if (!valid() || index < 0 || size_t(index) >= ids.size() || ids[size_t(index)] == selection_.table().id) { return; }
      const auto found = std::find_if(state.tables().begin(), state.tables().end(), [&](const auto &item) { return item.id == ids[size_t(index)]; });
      if (found == state.tables().end()) { return; }
      selection_.pin(state.project()->handle, state.project()->revision, *found);
      table_ = std::make_shared<const ProjectTable>(selection_.table());
      title_ = found->name;
      row_page_ = field_page_ = category_ = 0;
    }
  }).disable(!enabled);
  box.label(ctx.store.catalog().format("ai.scope.revision", {{"revision", std::to_string(selection_.revision())}}));
  if (!current) {
    box.paragraph(ctx.tr("ai.scope.stale"));
    const auto handle = state.project()->handle;
    const auto revision = state.project()->revision;
    box.button("ai_scope_reload", ctx.tr("ai.scope.reload"), [this, live, &state, handle, revision] {
      if (!live() || !state.loaded() || state.busy() || state.discussion().busy() ||
          state.project()->handle != handle || state.project()->revision != revision) { return; }
      const auto found = std::find_if(state.tables().begin(), state.tables().end(), [&](const auto &item) { return item.id == selection_.table().id; });
      if (found == state.tables().end()) {
        if (state.tables().empty()) { close(); return; }
        selection_.pin(handle, revision, state.tables().front());
        title_ = state.tables().front().name;
      }
      else { selection_.pin(handle, revision, *found); }
      table_ = std::make_shared<const ProjectTable>(selection_.table()); // Reload clears scope; no live rebasing.
      row_page_ = field_page_ = 0;
    }).disable(state.busy() || state.discussion().busy());
  }
  // A new opening/generation must not inherit an active text edit from an old scope.
  box.prop(ctx.tr("discussion.name")).text_field("ai_scope_name/" + selection_.handle() + "/" + std::to_string(generation), {
    [this, live] { return live() ? title_ : std::string(); },
    [this, valid](const std::string &value) { if (valid()) { title_ = value; } }
  }, {.max_length = 1024}).disable(!enabled);
  box.tabs("ai_scope_kind", {std::string(ctx.tr("ai.scope.rows")), std::string(ctx.tr("ai.scope.fields"))}, {
    [category = category_] { return category; }, [this, live](int value) { if (live() && (value == 0 || value == 1)) { category_ = value; } }
  });
  const bool records = category_ == 0;
  const int total = int(records ? table->records.size() : table->fields.size());
  int &page = records ? row_page_ : field_page_;
  page = std::clamp(page, 0, std::max(0, (total - 1) / page_size));
  const int shown_page = page;
  const size_t selected_count = records ? selection_.rows().size() : selection_.fields().size();
  const size_t limit = records ? ProjectContextSelection::max_rows : ProjectContextSelection::max_fields;
  auto &bulk = box.row();
  bulk.button("ai_scope_all", ctx.tr(records ? "discussion.all_rows" : "discussion.all_fields"),
      [this, valid, generation, records] {
    if (valid()) { if (records) { selection_.all_rows(generation); } else { selection_.all_fields(generation); } }
  }).disable(!enabled || size_t(total) > limit || total == 0);
  bulk.button("ai_scope_clear", ctx.tr("discussion.clear"), [this, valid, generation, records] {
    if (valid()) { if (records) { selection_.clear_rows(generation); } else { selection_.clear_fields(generation); } }
  }).disable(!enabled || selected_count == 0);
  for (int i = page * page_size; i < std::min(total, (page + 1) * page_size); ++i) {
    const auto id = records ? table->records[size_t(i)].id : table->fields[size_t(i)].id;
    const bool checked = records ? selection_.row_checked(id) : selection_.field_checked(id);
    std::string name, detail;
    if (records) {
      name = std::to_string(i + 1) + " · " + id.substr(0, 8);
      if (!table->fields.empty()) { name += " · " + cell_summary(*table, i, 0, 64); }
      detail = id;
    }
    else {
      const auto &field = table->fields[size_t(i)];
      name = project_value_summary(io::Json(field.name + (field.unit.empty() ? "" : " / " + field.unit)), 96);
      detail = field.name + " · " + field.type + (field.unit.empty() ? "" : " / " + field.unit) + "\n" + id;
    }
    box.checkbox("ai_scope_" + std::string(records ? "row/" : "field/") + id, name, {
      [checked] { return checked; }, [this, valid, generation, records, id](bool value) {
        if (valid()) { if (records) { selection_.set_row(id, value, generation); } else { selection_.set_field(id, value, generation); } }
      }
    }).tip(detail).disable(!enabled || (!checked && selected_count >= limit));
  }
  if (total > page_size) {
    auto &pages = box.row();
    pages.button("ai_scope_previous", ctx.tr("project.drafts.previous"), [this, live, records, shown_page] {
      if (live()) { (records ? row_page_ : field_page_) = std::max(0, shown_page - 1); }
    }).disable(page == 0);
    pages.label(ctx.store.catalog().format("ai.scope.page", {{"page", std::to_string(page + 1)},
        {"pages", std::to_string((total + page_size - 1) / page_size)}}));
    pages.button("ai_scope_next", ctx.tr("project.drafts.next"), [this, live, records, shown_page] {
      if (live()) { (records ? row_page_ : field_page_) = shown_page + 1; }
    }).disable((page + 1) * page_size >= total);
  }
  box.label(ctx.store.catalog().format("discussion.selection", {
    {"rows", std::to_string(selection_.rows().size())}, {"fields", std::to_string(selection_.fields().size())},
    {"cells", std::to_string(selection_.cell_count())}}));
  if (selection_.cell_count() > ProjectContextSelection::max_cells) { box.paragraph(ctx.tr("ai.scope.limit")); }
  if (!selection_.rows().empty() && !selection_.fields().empty()) {
    if (auto *preview = box.panel("ai_scope_preview", ctx.tr("ai.scope.preview"), true)) {
      std::vector<int> rows, fields;
      for (size_t i = 0; i < table->records.size(); ++i) { if (selection_.row_checked(table->records[i].id)) { rows.push_back(int(i)); } }
      for (size_t i = 0; i < table->fields.size(); ++i) { if (selection_.field_checked(table->fields[i].id)) { fields.push_back(int(i)); } }
      ui::TableSpec spec;
      spec.columns = {{std::string(ctx.tr("discussion.cells.record")), 7}, {std::string(ctx.tr("discussion.cells.field")), 9},
          {std::string(ctx.tr("project.value")), 10, false}};
      spec.rows = int(rows.size() * fields.size()); spec.visible_rows = float(std::min(spec.rows, 4));
      spec.data_version = generation;
      spec.cell = [table, rows, fields](int index, int col) {
        const int row = rows[size_t(index) / fields.size()], field = fields[size_t(index) % fields.size()];
        if (col == 0) { return std::to_string(row + 1) + " · " + table->records[size_t(row)].id.substr(0, 8); }
        if (col == 1) { const auto &f = table->fields[size_t(field)]; return f.name + (f.unit.empty() ? "" : " / " + f.unit); }
        return cell_summary(*table, row, field, 160);
      };
      preview->table("ai_scope_cells", std::move(spec));
    }
  }
  box.paragraph(ctx.tr("ai.scope.capture_hint"));
  box.button("ai_scope_capture", ctx.tr("discussion.capture"), [this, live, valid, &state] {
    if (valid() && selection_.valid() && !title_.empty()) {
      state.discussion().capture(selection_.table().id, selection_.rows(), selection_.fields(), title_,
          [this, live](bool saved) { if (live() && saved) { close(); } });
    }
  }).disable(!enabled || !selection_.valid() || title_.empty());
  box.button("ai_scope_cancel", ctx.tr("ai.scope.close"), [this, live] { if (live()) { close(); } });
}
}  // namespace stk::app
