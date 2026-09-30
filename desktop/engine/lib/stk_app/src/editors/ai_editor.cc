/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/shell.hh"
#include "stk/wm/window.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <unordered_map>

namespace stk::app {
namespace {
using io::Json;

double clock_seconds()
{
  return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

void show_tables(EditorContext ctx)
{
  ctx.defer([area = &ctx.area] {
    for (int i = 0; i < area->tab_count(); ++i) {
      if (area->tab(i).type().id == kEditorProject) {
        area->set_active_tab(i); area->editor().show_view("data"); return;
      }
    }
    area->add_tab(kEditorProject);
  });
}

class AIEditor final : public Editor {
 public:
  explicit AIEditor(const EditorType &type) : Editor(type) {}

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    row.button("ai_tables", ctx.tr("editor.project.title"), [ctx] { show_tables(ctx); }).width(7);
    auto &state = ctx.store.project();
    state.sync();
    if (state.project()) { row.label(state.project()->name); }
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    if (!state.ready()) { layout.paragraph(ctx.tr("project.bridge_required")); return; }
    if (!state.project()) {
      layout.paragraph(ctx.tr("ai.open_project"));
      layout.button("ai_open_project", ctx.tr("project.location"), [ctx] { show_tables(ctx); });
      return;
    }
    if (!state.loaded()) { layout.label(ctx.tr("project.busy")); return; }
    auto &discussion = state.discussion();
    if (!discussion.generation_supported()) {
      layout.paragraph(ctx.tr("discussion.requests.unsupported"));
      layout.button("ai_upgrade", ctx.tr("project.upgrade"), [&state] { state.upgrade(); })
          .disable(state.busy() || state.project()->format_version >= 8);
      return;
    }
    const std::string opening = state.project()->handle;
    if (opening_ != opening) {
      opening_ = opening;
      opened_history_ = false;
      shown_exchange_.clear(); transcript_.clear();
      shown_context_.clear(); captured_.reset();
    }
    // Unsent input belongs to its project even when another project becomes active. It is
    // intentionally not part of layout JSON; only explicitly prepared questions are persisted.
    const std::string key = state.project()->directory + "\n" + state.project()->id;
    active_draft_ = key;
    auto &draft = drafts_[key];
    if (!discussion.provider_loaded() && !discussion.busy() && !state.busy()) { discussion.load_provider(); }
    if (!draft.model_initialized && discussion.provider_loaded() && !discussion.provider().empty()) {
      draft.model = io::get_string(discussion.provider(), "model");
      draft.model_initialized = true;
    }
    model_has_text_ = !draft.model.empty();
    poll(ctx, discussion);
    layout.paragraph(ctx.tr("ai.intro"));
    if (!state.error().empty()) { layout.paragraph(state.error()); }
    if (!discussion.error().empty()) { layout.paragraph(discussion.error()); }
    if (!discussion.exchange_error().empty()) { layout.paragraph(discussion.exchange_error()); }
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    const float scale = ctx.ui ? ctx.ui->style().unit / 20.0f : 1.0f;
    if (width >= 920.0f * scale) {
      auto &columns = layout.split(0.32f);
      auto &left = columns.column();
      auto &right = columns.column();
      source(left, ctx, state, false);
      configuration(left, ctx, state, draft);
      conversation(right, ctx, state, draft, key, true);
    }
    else {
      bool settings_open = false;
      if (auto *panel = layout.panel("ai_context_settings", ctx.tr("ai.context_settings"), discussion.context().empty())) {
        settings_open = true;
        source(*panel, ctx, state, true);
        configuration(*panel, ctx, state, draft);
      }
      conversation(layout, ctx, state, draft, key, false, settings_open);
    }
  }

 private:
  struct Draft { std::string text, model; bool model_initialized = false; };

  void poll(EditorContext &ctx, ProjectDiscussion &discussion)
  {
    const double now = clock_seconds(), wake = discussion.pump(now);
    auto *wm = ctx.area.shell().window_manager();
    if (!wm || !std::isfinite(wake) ||
        (discussion.exchange_wake_scheduled > now && discussion.exchange_wake_scheduled <= wake + 1e-4)) { return; }
    discussion.exchange_wake_scheduled = wake;
    const auto delay = uint64_t(std::clamp((wake - now) * 1000.0 + 1.0, 1.0, 60000.0));
    wm->add_timer(delay, 0, [store = &ctx.store] { store->changed(); });
  }

  void source(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool compact)
  {
    auto &discussion = state.discussion();
    auto &box = layout.box();
    box.label(ctx.tr("ai.context_title"));
    const auto *table = state.table();
    if (table) {
      box.paragraph(table->name + " · " + state.record_id().substr(0, 8));
      box.paragraph(ctx.store.catalog().format("ai.selection", {{"fields", std::to_string(table->fields.size())}}));
    }
    else { box.paragraph(ctx.tr("ai.select_record")); }
    box.button("ai_capture", ctx.tr("ai.capture"), [&state, &discussion, handle = state.project()->handle,
        revision = state.project()->revision,
        table_id = state.table_id(), record_id = state.record_id()] {
      if (!state.project() || state.project()->handle != handle || state.project()->revision != revision ||
          state.table_id() != table_id || state.record_id() != record_id) { return; }
      const auto *selected = state.table();
      if (!selected || record_id.empty() || selected->fields.empty() || selected->fields.size() > 64) { return; }
      std::vector<std::string> fields;
      for (const auto &field : selected->fields) { fields.push_back(field.id); }
      discussion.capture(table_id, {record_id}, fields, selected->name);
    }).disable(state.busy() || discussion.busy() || !table || state.record_id().empty() ||
               (table && (table->fields.empty() || table->fields.size() > 64)));
    box.button("ai_select_data", ctx.tr("ai.select_data"), [ctx] { show_tables(ctx); });
    const auto &context = discussion.context();
    if (context.empty()) { box.paragraph(ctx.tr("ai.no_context")); return; }
    const auto identity = io::get_string(context, "id");
    const auto revision = io::get_int(context, "source_revision", -1);
    box.paragraph(ctx.store.catalog().format("ai.captured", {{"title", io::get_string(context, "title")},
        {"revision", std::to_string(revision)}}));
    const auto selection = context.value("selection", Json::object());
    const auto rows = selection.value("record_ids", Json::array()).size();
    const auto fields = selection.value("field_ids", Json::array()).size();
    box.label(ctx.store.catalog().format("discussion.selection", {{"rows", std::to_string(rows)},
        {"fields", std::to_string(fields)}, {"cells", std::to_string(rows * fields)}}));
    if (revision != state.project()->revision) { box.paragraph(ctx.tr("ai.stale_context")); }
    if (shown_context_ != identity) {
      shown_context_ = identity;
      captured_.reset();
      try { captured_ = std::make_shared<CapturedProjectTable>(project_context_table(context)); }
      catch (const std::exception &) { /* Existing discussion page retains raw diagnostics. */ }
    }
    if (!captured_) { box.paragraph(ctx.tr("ai.context_unreadable")); return; }
    if (!captured_->omission_reason.empty()) { box.paragraph(ctx.tr("discussion.cells.omitted")); return; }
    const auto captured = captured_;
    if (std::any_of(captured->cells.begin(), captured->cells.end(), [](const auto &cell) { return cell.incomplete; })) {
      box.paragraph(ctx.tr("discussion.cells.incomplete"));
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("discussion.cells.record")), 8},
                    {std::string(ctx.tr("discussion.cells.field")), 9},
                    {std::string(ctx.tr("discussion.cells.value")), 9, false},
                    {std::string(ctx.tr("discussion.cells.status")), 9}};
    spec.rows = int(captured->cells.size()); spec.visible_rows = float(std::min(spec.rows, 4));
    spec.data_version = uint64_t(std::hash<std::string>{}(identity));
    spec.cell = [captured, store = &ctx.store](int row, int col) {
      const auto &cell = captured->cells[size_t(row)];
      if (col == 0) { return cell.record_id.substr(0, 8); }
      if (col == 1) { return cell.field_name + (cell.unit.empty() ? "" : " / " + cell.unit); }
      if (col == 2) { return cell.value_text; }
      return std::string(store->tr("discussion.cells." + (cell.status == "omitted" ? std::string("omitted_value") : cell.status)));
    };
    if (auto *preview = box.panel("ai_context_preview", ctx.tr("discussion.cells.title"), !compact)) {
      preview->table("ai_context_cells", std::move(spec));
    }
    box.paragraph(ctx.tr("ai.context_hint"));
  }

  void configuration(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft)
  {
    auto &discussion = state.discussion();
    auto &box = layout.box();
    box.label("Alibaba Token Plan");
    auto &model = box.prop(ctx.tr("discussion.requests.model")).text_field("ai_model/" + state.project()->handle, {
      [&draft] { return draft.model; }, [&draft](const std::string &value) { draft.model = value; draft.model_initialized = true; }
    }, {.max_length = 128});
    model_has_text_ = ctx.ui && ctx.ui->editing() == model.id && ctx.ui->edit_state() ?
        !ctx.ui->edit_state()->text().empty() : !draft.model.empty();
    const bool configured = discussion.provider().value("configured", false);
    box.paragraph(ctx.tr(configured ? "ai.configured" : "ai.missing_key"));
    box.button("ai_provider_refresh", ctx.tr("discussion.requests.provider_refresh"), [&discussion, &state, handle = state.project()->handle] {
      if (state.project() && state.project()->handle == handle) { discussion.load_provider(); }
    })
        .disable(state.busy() || discussion.busy());
  }

  void conversation(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft,
                    const std::string &key, const bool wide, const bool settings_open = false)
  {
    auto &discussion = state.discussion();
    const bool enabled = !state.busy() && !discussion.busy();
    const std::string handle = state.project()->handle;
    const auto &page = discussion.page("requests");
    if (!page.loaded && enabled) { discussion.load_page("requests", page.offset, true); }
    const auto items = page.items;
    if (!discussion.exchange_request().empty()) { opened_history_ = true; }
    if (!opened_history_ && page.loaded && !items.empty() && enabled && !discussion.exchange_busy()) {
      opened_history_ = discussion.load_exchange(io::get_string(items.back(), "id"));
    }
    std::vector<std::string> ids, titles;
    for (const auto &item : items) {
      ids.push_back(io::get_string(item, "id"));
      titles.push_back(io::get_string(item.at("configuration"), "model") + " · " +
          std::string(ctx.tr("discussion.requests." + io::get_string(item, "status"))) + " · " + ids.back().substr(0, 8));
    }
    layout.label(ctx.tr("ai.history"));
    auto &history = layout.row();
    history.dropdown("ai_history", std::move(titles), {
      [ids, &discussion] {
        const auto id = io::get_string(discussion.exchange_request(), "id");
        const auto it = std::find(ids.begin(), ids.end(), id);
        return it == ids.end() ? -1 : int(it - ids.begin());
      },
      [this, ids, &discussion, &state, handle](int index) {
        if (!state.project() || state.project()->handle != handle || index < 0 || size_t(index) >= ids.size()) { return; }
        if (discussion.load_exchange(ids[size_t(index)])) { opened_history_ = true; }
      }
    }).disable(!enabled || discussion.exchange_busy() || ids.empty());
    history.button("ai_history_refresh", ctx.tr("ai.refresh_history"), [&discussion, &state, handle, offset = page.offset] {
      if (state.project() && state.project()->handle == handle) { discussion.load_page("requests", offset); }
    }).width(6).disable(!enabled);
    if (page.offset > 0 || page.next >= 0) {
      auto &pages = layout.row();
      pages.button("ai_previous", ctx.tr("project.drafts.previous"), [&discussion, &state, handle, offset = page.offset] {
        if (state.project() && state.project()->handle == handle) {
          discussion.load_page("requests", std::max<int64_t>(0, offset - 100));
        }
      }).disable(!enabled || page.offset == 0);
      pages.button("ai_next", ctx.tr("project.drafts.next"), [&discussion, &state, handle, next = page.next] {
        if (state.project() && state.project()->handle == handle) { discussion.load_page("requests", next); }
      }).disable(!enabled || page.next < 0);
    }
    const auto request = discussion.exchange_request();
    const auto question = discussion.exchange_question();
    const auto reply = discussion.exchange_reply();
    const auto progress = discussion.exchange_progress();
    const auto context = discussion.exchange_context();
    const std::string id = io::get_string(request, "id"), status = io::get_string(request, "status");
    const float unit = ctx.ui ? ctx.ui->style().unit : 20.0f;
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    // Reserve region padding, the split gutter and the log scrollbar. Use the same
    // font as LogView; line breaks affect display only, never the saved reply.
    const float wrap_width = std::max(unit, width * (wide ? 0.68f : 1.0f) - 4 * unit);
    const std::string content = question.dump() + reply.dump() + progress.dump() + std::to_string(wrap_width) +
        std::to_string(unit) + std::string(ctx.tr("ai.you"));
    if (shown_exchange_ != content) {
      shown_exchange_ = content;
      transcript_ = ui::LogBuffer(std::numeric_limits<size_t>::max());
      std::string text;
      if (!question.empty()) { text += std::string(ctx.tr("ai.you")) + "\n" + io::get_string(question, "text") + "\n\n"; }
      if (!reply.empty()) { text += std::string(ctx.tr("ai.assistant")) + "\n" + io::get_string(reply, "text"); }
      else if (!progress.empty() && !io::get_string(progress, "text").empty()) {
        text += std::string(ctx.tr("ai.temporary_reply")) + "\n" + io::get_string(progress, "text");
      }
      // Measure what the log actually displays: tabs expand before wrapping,
      // and terminal escape bytes do not count towards visible line width.
      ui::LogBuffer normalized(std::numeric_limits<size_t>::max());
      normalized.append(text);
      text.clear();
      for (size_t i = 0; i < normalized.line_count(); ++i) { text += std::string(normalized.line(i)) + "\n"; }
      if (ctx.ui) {
        for (const auto &line : ui::break_lines(text, wrap_width, ctx.ui->measurer(), ctx.ui->style().mono)) {
          transcript_.append(text.substr(line.begin, line.end - line.begin) + "\n");
        }
      }
      else { transcript_.append(text); }
    }
    if (!request.empty()) {
      layout.paragraph(std::string(ctx.tr("discussion.requests." + status)) + " · " +
          io::get_string(request.at("configuration"), "model") + " · " + id.substr(0, 8));
      layout.paragraph(ctx.store.catalog().format("ai.request_source", {{"revision", std::to_string(io::get_int(request, "source_revision", -1))},
          {"title", io::get_string(context, "title")}}));
      if (discussion.following()) { layout.label(ctx.tr("ai.following")); }
      else if (status == "running" || status == "uncertain") { layout.paragraph(ctx.tr("ai.paused")); }
      if (request.contains("error_code") && request["error_code"].is_string()) { layout.paragraph(request["error_code"].get<std::string>()); }
    }
    else { layout.paragraph(ctx.tr(discussion.exchange_busy() ? "ai.loading" : "ai.empty")); }
    const float height = ctx.draw ? float(ctx.draw->rect.height()) : 800.0f;
    const float transcript_units = wide ? std::clamp(height / unit - 22.0f, 5.0f, 22.0f) :
        settings_open ? 6.0f : std::clamp(height / unit - 24.0f, 6.0f, 22.0f);
    layout.log_view("ai_transcript", transcript_, transcript_units);
    auto &actions = layout.row();
    actions.button("ai_send_saved", ctx.tr("ai.send_saved"), [&discussion, &state, handle, id] {
      if (state.project() && state.project()->handle == handle && io::get_string(discussion.exchange_request(), "id") == id) {
        discussion.start_request(id);
      }
    }).disable(!enabled || status != "pending" || !discussion.provider().value("configured", false) ||
               request.value("configuration", Json::object()).value("adapter", "") != discussion.provider().value("adapter", ""));
    actions.button("ai_refresh_reply", ctx.tr("ai.refresh"), [&discussion, &state, handle, id] {
      if (state.project() && state.project()->handle == handle && io::get_string(discussion.exchange_request(), "id") == id) {
        discussion.refresh_exchange();
      }
    })
        .disable(!enabled || id.empty() || discussion.exchange_busy());
    actions.button("ai_cancel", ctx.tr("discussion.requests.cancel"), [&discussion, &state, handle, id] {
      if (state.project() && state.project()->handle == handle && io::get_string(discussion.exchange_request(), "id") == id) {
        discussion.cancel_request(id);
      }
    }).disable(!enabled || (status != "pending" && status != "running" && status != "uncertain"));
    if (status == "running" || status == "uncertain") {
      layout.button("ai_recover", ctx.tr("discussion.requests.recover"), [&discussion, &state, handle, id] {
        if (state.project() && state.project()->handle == handle && io::get_string(discussion.exchange_request(), "id") == id) {
          discussion.recover_request(id);
        }
      }).disable(!enabled);
    }
    layout.separator();
    layout.label(ctx.tr("ai.compose"));
    // Active toolkit edits must disappear on project switch before a new binding is installed.
    auto &input = layout.text_area("ai_question/" + handle, ui::bind(draft.text), {.max_length = 65536, .visible_lines = 4});
    const bool has_question = ctx.ui && ctx.ui->editing() == input.id && ctx.ui->edit_state() ?
        !ctx.ui->edit_state()->text().empty() : !draft.text.empty();
    layout.paragraph(ctx.tr("ai.prepare_hint"));
    const auto context_id = io::get_string(discussion.context(), "id");
    layout.button("ai_prepare", ctx.tr("ai.prepare"), [this, &discussion, &state, handle, key, context_id] {
      if (!state.project() || state.project()->handle != handle || active_draft_ != key) { return; }
      const auto &current = drafts_.at(key);
      if (discussion.prepare_question(context_id, current.text, current.model)) {
        opened_history_ = true;
      }
    }).disable(!enabled || discussion.exchange_busy() || context_id.empty() || !has_question || !model_has_text_ || discussion.provider().empty());
    if (auto *details = layout.panel("ai_scope_detail", ctx.tr("ai.scope_detail"), false)) {
      details->paragraph(ctx.tr("ai.single_turn"));
      if (!id.empty()) { details->paragraph(id); details->paragraph(io::get_string(request, "context_id")); }
    }
  }

  std::unordered_map<std::string, Draft> drafts_;
  std::string active_draft_, opening_, shown_context_, shown_exchange_;
  bool opened_history_ = false;
  bool model_has_text_ = false;
  std::shared_ptr<const CapturedProjectTable> captured_;
  ui::LogBuffer transcript_;
};
}  // namespace

std::unique_ptr<Editor> make_ai_editor(const EditorType &type)
{
  return std::make_unique<AIEditor>(type);
}
}  // namespace stk::app
