/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_discussion_view.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include <algorithm>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
void toggle(std::vector<std::string> &items, const std::string &id, size_t limit)
{
  const auto it = std::find(items.begin(), items.end(), id);
  if (it != items.end()) { items.erase(it); }
  else if (!id.empty() && items.size() < limit) { items.push_back(id); }
}
int index(const std::vector<std::string> &ids, const std::string &id)
{
  const auto it = std::find(ids.begin(), ids.end(), id);
  return it == ids.end() ? -1 : int(it - ids.begin());
}
}  // namespace

void ProjectDiscussionView::capture_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  auto &discussion = state.discussion();
  auto *panel = layout.panel("context_capture", ctx.tr("discussion.capture_title"), discussion.context().empty());
  if (!panel) { return; }
  const bool enabled = !state.busy() && !discussion.busy();
  panel->paragraph(ctx.tr("discussion.capture_hint"));
  panel->prop(ctx.tr("discussion.name")).text_field("title", ui::bind(title_), {.max_length = 1024});
  const auto *current = state.table();
  panel->button("use_selection", ctx.tr("discussion.use_selection"), [this, &state] {
    const auto *table = state.table();
    if (!table || state.record_id().empty() || table->fields.size() > 64) { return; }
    table_ = table->id;
    rows_ = {state.record_id()};
    fields_.clear();
    for (const auto &field : table->fields) { fields_.push_back(field.id); }
    row_ = state.record_id();
    field_ = fields_.empty() ? std::string() : fields_.front();
  }).disable(!enabled || !current || state.record_id().empty() || current->fields.empty() || current->fields.size() > 64);
  std::vector<std::string> names, ids;
  for (const auto &table : state.tables()) { ids.push_back(table.id); names.push_back(table.name); }
  panel->prop(ctx.tr("discussion.table")).dropdown("table", std::move(names), {
    [this, ids] { return index(ids, table_); }, [this, ids](int selected) {
      if (selected < 0 || size_t(selected) >= ids.size() || table_ == ids[size_t(selected)]) { return; }
      table_ = ids[size_t(selected)]; rows_.clear(); fields_.clear(); row_.clear(); field_.clear();
    }
  });
  const auto table = std::find_if(state.tables().begin(), state.tables().end(), [&](const auto &value) { return value.id == table_; });
  if (table != state.tables().end()) {
    std::vector<std::string> row_ids, row_names, field_ids, field_names;
    for (size_t i = 0; i < table->records.size(); ++i) {
      row_ids.push_back(table->records[i].id);
      row_names.push_back(table->records[i].id.substr(0, 8) + " · " + table->text(int(i), 0).substr(0, 80));
    }
    for (const auto &field : table->fields) {
      field_ids.push_back(field.id); field_names.push_back(field.name + (field.unit.empty() ? "" : " / " + field.unit));
    }
    panel->prop(ctx.tr("discussion.row")).dropdown("record", std::move(row_names), {
      [this, row_ids] { return index(row_ids, row_); }, [this, row_ids](int selected) {
        if (selected >= 0 && size_t(selected) < row_ids.size()) { row_ = row_ids[size_t(selected)]; }
      }
    });
    auto &rows = panel->row();
    rows.button("toggle_row", ctx.tr("discussion.toggle_row"), [this] { toggle(rows_, row_, 100); }).disable(!enabled || row_.empty());
    rows.button("all_rows", ctx.tr("discussion.all_rows"), [this, row_ids] { rows_ = row_ids; }).disable(!enabled || row_ids.size() > 100);
    rows.button("clear_rows", ctx.tr("discussion.clear"), [this] { rows_.clear(); }).disable(!enabled);
    panel->prop(ctx.tr("discussion.field")).dropdown("field", std::move(field_names), {
      [this, field_ids] { return index(field_ids, field_); }, [this, field_ids](int selected) {
        if (selected >= 0 && size_t(selected) < field_ids.size()) { field_ = field_ids[size_t(selected)]; }
      }
    });
    auto &fields = panel->row();
    fields.button("toggle_field", ctx.tr("discussion.toggle_field"), [this] { toggle(fields_, field_, 64); }).disable(!enabled || field_.empty());
    fields.button("all_fields", ctx.tr("discussion.all_fields"), [this, field_ids] { fields_ = field_ids; }).disable(!enabled || field_ids.size() > 64);
    fields.button("clear_fields", ctx.tr("discussion.clear"), [this] { fields_.clear(); }).disable(!enabled);
  }
  panel->label(ctx.store.catalog().format("discussion.selection", {
    {"rows", std::to_string(rows_.size())}, {"fields", std::to_string(fields_.size())},
    {"cells", std::to_string(rows_.size() * fields_.size())}}));
  if (auto *selection = panel->panel("selected_ids", ctx.tr("discussion.selected_ids"), false)) {
    selection->paragraph(table_);
    for (const auto &row : rows_) { selection->paragraph(row); }
    for (const auto &field : fields_) { selection->paragraph(field); }
  }
  panel->button("capture", ctx.tr("discussion.capture"), [this, &discussion, &state, handle = state.project()->handle] {
    if (state.project() && state.project()->handle == handle) { discussion.capture(table_, rows_, fields_, title_); }
  }).disable(!enabled || table_.empty() || title_.empty() || rows_.empty() || fields_.empty() || rows_.size() * fields_.size() > 1000);
}

void ProjectDiscussionView::captured_cells(ui::Layout &layout, EditorContext &ctx)
{
  if (!captured_error_.empty()) { layout.paragraph(captured_error_); }
  if (!captured_) { return; }
  if (!captured_->omission_reason.empty()) { layout.paragraph(ctx.tr("discussion.cells.omitted")); return; }
  auto *panel = layout.panel("captured_cells", ctx.tr("discussion.cells.title"), true);
  if (!panel || captured_->cells.empty()) { return; }
  const auto captured = captured_;
  captured_selected_ = std::clamp(captured_selected_, 0, int(captured->cells.size()) - 1);
  ui::TableSpec spec;
  spec.columns = {{std::string(ctx.tr("discussion.cells.record")), 8}, {std::string(ctx.tr("discussion.cells.field")), 12},
      {std::string(ctx.tr("discussion.cells.value")), 13, false}, {std::string(ctx.tr("discussion.cells.status")), 11}};
  spec.rows = int(captured->cells.size());
  spec.visible_rows = float(std::min(spec.rows, 5));
  spec.data_version = uint64_t(std::hash<std::string>{}(shown_context_));
  spec.selected = {[this, captured] { return captured_ == captured ? captured_selected_ : -1; },
      [this, captured](int row) { if (captured_ == captured && row >= 0 && size_t(row) < captured->cells.size()) { captured_selected_ = row; } }};
  spec.cell = [captured, store = &ctx.store](int row, int col) {
    const auto &cell = captured->cells[size_t(row)];
    if (col == 0) { return cell.record_id.substr(0, 8); }
    if (col == 1) { return (cell.field_name.empty() ? cell.field_id.substr(0, 8) : cell.field_name) +
                          (cell.unit.empty() ? "" : " / " + cell.unit); }
    if (col == 2) { return cell.value_text; }
    return std::string(store->tr("discussion.cells." + (cell.status == "omitted" ? std::string("omitted_value") : cell.status)));
  };
  spec.cell_color = [captured](int row, int) {
    const auto &cell = captured->cells[size_t(row)];
    return cell.status == "formula_error" ? ui::Color::rgb(0xff6e6e) : cell.incomplete ?
           ui::Color::rgb(0xffba66) : ui::Color{0, 0, 0, 0};
  };
  panel->table("rows", std::move(spec));
  const auto &cell = captured->cells[size_t(captured_selected_)];
  if (cell.incomplete) { panel->paragraph(ctx.tr("discussion.cells.incomplete")); }
  if (captured_detail_ != captured_selected_) {
    captured_detail_ = captured_selected_;
    cell_details_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
    cell_details_.append(cell.details.dump(2));
  }
  if (auto *detail = panel->panel("cell_details", ctx.tr("discussion.cells.details"), false)) {
    detail->log_view("value", cell_details_, 6);
  }
}

void ProjectDiscussionView::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state, int &project_view)
{
  auto &discussion = state.discussion();
  if (project_ != state.project()->id) {
    project_ = state.project()->id;
    title_.clear(); text_.clear(); table_.clear(); row_.clear(); field_.clear(); selected_.clear();
    rows_.clear(); fields_.clear(); shown_context_.clear(); shown_message_.clear();
    context_details_.clear(); message_text_.clear(); shown_request_.clear(); request_details_.clear();
    captured_.reset(); captured_error_.clear();
    model_.clear(); model_initialized_ = false;
  }
  layout.paragraph(ctx.tr("discussion.hint"));
  if (!discussion.supported()) { layout.paragraph(ctx.tr("discussion.unsupported")); return; }
  const bool enabled = !state.busy() && !discussion.busy();
  if (!discussion.error().empty()) { layout.paragraph(discussion.error()); }
  if (!state.drafts_error().empty()) { layout.paragraph(state.drafts_error()); }
  if (category_ != 3) { capture_controls(layout, ctx, state); }
  layout.tabs("discussion_category", {std::string(ctx.tr("discussion.contexts")), std::string(ctx.tr("discussion.messages")),
      std::string(ctx.tr("discussion.proposals")), std::string(ctx.tr("discussion.requests"))},
      {[this] { return category_; }, [this](int value) { category_ = value; selected_.clear(); }});
  if (category_ == 3 && !discussion.requests_supported()) { layout.paragraph(ctx.tr("discussion.requests.unsupported")); return; }
  const std::string kind = category_ == 0 ? "contexts" : category_ == 1 ? "messages" : category_ == 2 ? "proposals" : "requests";
  if (category_ == 3) {
    layout.paragraph(ctx.tr("discussion.requests.hint"));
    request_controls(layout, ctx, state);
  }
  const auto &page = discussion.page(kind);
  if (!page.loaded && enabled) { discussion.load_page(kind, page.offset, true); }
  const auto items = page.items;
  if (!items.empty()) {
    if (std::none_of(items.begin(), items.end(), [&](const auto &item) { return item.at("id") == selected_; })) {
      selected_ = io::get_string(items.front(), "id");
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("discussion.name")), 18},
                    {std::string(ctx.tr(kind == "requests" ? "discussion.requests.status" : "discussion.source")), 13}};
    spec.rows = int(items.size()); spec.visible_rows = float(std::min(spec.rows, 3));
    spec.data_version = discussion.version() * 4 + uint64_t(category_);
    spec.selected = {[this, items] {
      for (size_t i = 0; i < items.size(); ++i) { if (items[i].at("id") == selected_) { return int(i); } }
      return -1;
    }, [this, items](int value) { if (value >= 0 && size_t(value) < items.size()) { selected_ = io::get_string(items[size_t(value)], "id"); } }};
    spec.cell = [items, kind, store = &ctx.store](int row, int col) {
      const auto &item = items[size_t(row)];
      if (kind == "requests") {
        return col == 0 ? io::get_string(item.at("configuration"), "model") + " / " + io::get_string(item, "id").substr(0, 8) :
                         std::string(store->tr("discussion.requests." + io::get_string(item, "status")));
      }
      if (col == 0) { return (kind == "contexts" ? io::get_string(item, "title") : kind == "messages" ?
          std::string(store->tr("discussion.role." + io::get_string(item, "role"))) : io::get_string(item, "draft_id").substr(0, 8)) +
          " / " + io::get_string(item, "id").substr(0, 8); }
      return kind == "contexts" ? std::to_string(io::get_int(item, "source_revision", -1)) :
             kind == "messages" ? io::get_string(item, "context_id").substr(0, 8) : io::get_string(item, "message_id").substr(0, 8);
    };
    layout.table("discussion_rows", std::move(spec));
  }
  else { layout.label(ctx.tr("discussion.empty")); }
  auto &actions = layout.row();
  actions.button("open_discussion_item", ctx.tr(category_ == 2 ? "discussion.open_review" : "discussion.open"),
      [this, &discussion, &state, &project_view, kind, items, id = selected_, handle = state.project()->handle] {
    if (!state.project() || state.project()->handle != handle) { return; }
    if (kind == "contexts") { discussion.load_context(id); }
    else if (kind == "messages") { discussion.load_message(id); }
    else if (kind == "requests") { discussion.load_request(id); }
    else {
      const auto chosen = std::find_if(items.begin(), items.end(), [&](const auto &item) { return item.at("id") == id; });
      if (chosen != items.end()) {
        const auto draft_id = io::get_string(*chosen, "draft_id");
        if (io::get_string(state.saved_review(), "id") == draft_id || state.load_draft(draft_id)) { project_view = 1; }
      }
    }
  }).disable(!enabled || items.empty());
  actions.button("discussion_refresh", ctx.tr("discussion.refresh"), [&discussion, kind, offset = page.offset] {
    discussion.load_page(kind, offset);
  }).disable(!enabled);
  actions.button("discussion_previous", ctx.tr("project.drafts.previous"), [&discussion, kind, offset = page.offset] {
    discussion.load_page(kind, std::max(int64_t(0), offset - 100));
  }).disable(!enabled || page.offset == 0);
  actions.button("discussion_next", ctx.tr("project.drafts.next"), [&discussion, kind, offset = page.next] {
    discussion.load_page(kind, offset);
  }).disable(!enabled || page.next < 0);

  if (category_ == 3) { request_details(layout, ctx, state); return; }

  const auto &context = discussion.context();
  if (!context.empty()) {
    layout.paragraph(ctx.store.catalog().format("discussion.context_summary", {{"title", io::get_string(context, "title")},
        {"revision", std::to_string(io::get_int(context, "source_revision", -1))}, {"id", io::get_string(context, "id")}}));
    if (io::get_int(context, "source_revision", -1) != state.project()->revision) { layout.paragraph(ctx.tr("discussion.stale")); }
    if (context.value("omitted_values", 0) > 0 || io::get_string(context.at("content"), "state") == "omitted" ||
        context.at("diagnostics").value("table_missing", false) || !context.at("diagnostics").at("record_ids").empty() ||
        !context.at("diagnostics").at("field_ids").empty()) { layout.paragraph(ctx.tr("discussion.incomplete")); }
    if (shown_context_ != io::get_string(context, "id")) {
      shown_context_ = io::get_string(context, "id");
      context_details_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
      context_details_.append(context.dump(2));
      captured_.reset(); captured_error_.clear();
      captured_selected_ = 0; captured_detail_ = -1;
      try { captured_ = std::make_shared<CapturedProjectTable>(project_context_table(context)); }
      catch (const std::exception &error) { captured_error_ = error.what(); }
    }
    captured_cells(layout, ctx);
    if (auto *details = layout.panel("context_details", ctx.tr("discussion.details"), false)) {
      details->log_view("value", context_details_, 8);
    }
  }
  if (auto *composer = layout.panel("message_composer", ctx.tr("discussion.compose"), true)) {
    composer->paragraph(ctx.tr("discussion.compose_hint"));
    composer->text_area("text", ui::bind(text_), {.max_length = 65536, .visible_lines = 3});
    composer->button("save_message", ctx.tr("discussion.save_message"),
        [this, &discussion, &state, handle = state.project()->handle, id = io::get_string(context, "id")] {
      if (state.project() && state.project()->handle == handle && io::get_string(discussion.context(), "id") == id) {
        discussion.add_message(text_);
      }
    })
        .disable(!enabled || context.empty() || text_.empty());
  }
  const auto &message = discussion.message();
  if (!message.empty()) {
    layout.paragraph(ctx.store.catalog().format("discussion.message_summary", {{"id", io::get_string(message, "id")},
        {"role", std::string(ctx.tr("discussion.role." + io::get_string(message, "role")))},
        {"context", io::get_string(message, "context_id")}}));
    if (shown_message_ != io::get_string(message, "id")) {
      shown_message_ = io::get_string(message, "id");
      message_text_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
      message_text_.append(io::get_string(message, "text"));
    }
    layout.log_view("message_text", message_text_, 4);
    auto &message_actions = layout.row();
    message_actions.button("message_context", ctx.tr("discussion.message_context"), [&discussion, id = io::get_string(message, "context_id")] {
      discussion.load_context(id);
    }).disable(!enabled);
    message_actions.button("link_review", ctx.tr("discussion.link_review"),
        [&discussion, &state, handle = state.project()->handle, id = io::get_string(message, "id"),
         draft = io::get_string(state.saved_review(), "id")] {
      if (state.project() && state.project()->handle == handle && io::get_string(discussion.message(), "id") == id &&
          io::get_string(state.saved_review(), "id") == draft) { discussion.link_review(); }
    })
        .disable(!enabled || state.saved_review().empty());
    layout.paragraph(ctx.tr("discussion.link_hint"));
  }
}

void ProjectDiscussionView::request_details(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  auto &discussion = state.discussion();
  const auto &request = discussion.generation_request();
  if (request.empty()) { return; }
  const auto id = io::get_string(request, "id"), status = io::get_string(request, "status");
  layout.paragraph(id + " · " + std::string(ctx.tr("discussion.requests." + status)));
  layout.paragraph(ctx.store.catalog().format("discussion.requests.summary", {
      {"model", io::get_string(request.at("configuration"), "model")},
      {"revision", std::to_string(io::get_int(request, "source_revision", -1))},
      {"context", io::get_string(request, "context_id")}}));
  if (request.value("cancel_requested", false)) { layout.paragraph(ctx.tr("discussion.requests.cancel_requested")); }
  if (status == "running" || status == "uncertain") { layout.paragraph(ctx.tr("discussion.requests.verify")); }
  const auto serialized = request.dump(2);
  if (shown_request_ != serialized) {
    shown_request_ = serialized;
    request_details_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
    request_details_.append(serialized);
  }
  if (auto *details = layout.panel("request_details", ctx.tr("discussion.requests.details"), false)) {
    details->log_view("value", request_details_, 8);
  }
  const bool enabled = !state.busy() && !discussion.busy();
  const auto current = [&discussion, &state, handle = state.project()->handle, id] {
    return state.project() && state.project()->handle == handle && io::get_string(discussion.generation_request(), "id") == id;
  };
  auto &actions = layout.row();
  actions.button("request_start", ctx.tr("discussion.requests.start"), [&discussion, current, id] {
    if (current()) { discussion.start_request(id); }
  }).disable(!enabled || status != "pending" || !discussion.generation_supported() ||
      !discussion.provider().value("configured", false) ||
      io::get_string(request.at("configuration"), "adapter") != io::get_string(discussion.provider(), "adapter"));
  actions.button("request_reload", ctx.tr("discussion.requests.refresh"), [&discussion, current, id] {
    if (current()) { discussion.load_request(id); }
  }).disable(!enabled);
  actions.button("request_cancel", ctx.tr("discussion.requests.cancel"), [&discussion, current, id] {
    if (current()) { discussion.cancel_request(id); }
  }).disable(!enabled || status == "completed" || status == "failed" || status == "cancelled");
  actions.button("request_recover", ctx.tr("discussion.requests.recover"), [&discussion, current, id] {
    if (current()) { discussion.recover_request(id); }
  }).disable(!enabled || status != "running" || !discussion.generation_supported());
  auto &links = layout.row();
  links.button("request_message", ctx.tr("discussion.requests.message"),
      [this, &discussion, current, message = io::get_string(request, "message_id")] {
    if (current() && discussion.load_message(message)) { category_ = 1; }
  }).disable(!enabled);
  const bool completed = status == "completed" && request.contains("result") && request.at("result").is_object();
  links.button("request_result", ctx.tr("discussion.requests.result"),
      [this, &discussion, current, message = completed ? io::get_string(request.at("result"), "message_id") : std::string()] {
    if (current() && !message.empty() && discussion.load_message(message)) { category_ = 1; }
  }).disable(!enabled || !completed);
}

void ProjectDiscussionView::request_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  auto &discussion = state.discussion();
  if (!discussion.generation_supported()) { return; }
  if (!discussion.provider_loaded() && !state.busy() && !discussion.busy()) { discussion.load_provider(); }
  auto *panel = layout.panel("request_prepare", ctx.tr("discussion.requests.prepare_title"), true);
  if (!panel) { return; }
  const auto &provider = discussion.provider();
  if (!provider.empty()) {
    panel->paragraph("Alibaba Token Plan · " + io::get_string(provider, "base_url"));
    panel->paragraph(ctx.tr(provider.value("configured", false) ? "discussion.requests.key_ready" : "discussion.requests.key_missing"));
    if (!model_initialized_) { model_ = io::get_string(provider, "model"); model_initialized_ = true; }
  }
  panel->button("provider_refresh", ctx.tr("discussion.requests.provider_refresh"),
      [&discussion, &state, handle = state.project()->handle] {
    if (state.project() && state.project()->handle == handle) { discussion.load_provider(); }
  }).disable(state.busy() || discussion.busy());
  panel->prop(ctx.tr("discussion.requests.model")).text_field("model", ui::bind(model_), {.max_length = 128});
  const auto &message = discussion.message();
  const bool user_message = !message.empty() && io::get_string(message, "role") == "user";
  panel->paragraph(user_message ? ctx.store.catalog().format("discussion.requests.input", {
      {"message", io::get_string(message, "id")}, {"context", io::get_string(message, "context_id")}}) :
      std::string(ctx.tr("discussion.requests.select_message")));
  panel->button("prepare", ctx.tr("discussion.requests.prepare"),
      [this, &discussion, &state, handle = state.project()->handle, id = io::get_string(message, "id")] {
    if (state.project() && state.project()->handle == handle && io::get_string(discussion.message(), "id") == id) {
      discussion.create_request(model_);
    }
  }).disable(state.busy() || discussion.busy() || provider.empty() || !user_message || model_.empty());
}
}  // namespace stk::app
