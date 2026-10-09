/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/shell.hh"
#include "stk/wm/window.hh"
#include "archive_controls.hh"
#include "model_gate.hh"
#include "project_context_picker.hh"
#include "project_navigation.hh"
#include "project_labels.hh"
#include "editor_text.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <unordered_map>
#include <utility>

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

/** A sweep reply in words: its summary, the base row and each axis ("Temperature / K: 300 → 400, 5 values").
 * Display only; the backend validates the saved text before any draft exists. */
std::string sweep_reply(const Json &content, const Json &context, EditorContext &ctx, const std::string &original)
{
  if (!content.at("summary").is_string() || !content.at("axes").is_array() || content.at("axes").empty() ||
      content.at("axes").size() > 8) { return original; }
  auto &catalog = ctx.store.catalog();
  const auto &fields = context.at("content").at("value").at("fields");
  const auto &records = context.at("selection").at("record_ids");
  const auto record = std::find(records.begin(), records.end(), content.at("base_record_id"));
  std::string text = content.at("summary").get<std::string>() + "\n\n" + catalog.format("ai.sweep_base", {
      {"row", record == records.end() ? std::string("?") : std::to_string(std::distance(records.begin(), record) + 1)},
      {"mode", std::string(ctx.tr(content.value("mode", std::string()) == "zip" ? "ai.sweep_zip" : "ai.sweep_product"))}});
  for (const auto &axis : content.at("axes")) {
    if (!axis.is_object() || !axis.contains("field_id")) { return original; }
    const auto field = std::find_if(fields.begin(), fields.end(), [&](const auto &item) { return item.at("id") == axis.at("field_id"); });
    const auto name = field == fields.end() ? std::string("?") : io::get_string(*field, "name");
    std::string values;
    if (axis.contains("values") && axis.at("values").is_array()) {
      for (size_t i = 0; i < axis.at("values").size() && i < 12; ++i) { values += (i ? ", " : "") + axis.at("values")[i].dump(); }
      if (axis.at("values").size() > 12) { values += ", …"; }
    }
    else if (axis.contains("count")) {
      values = catalog.format("ai.sweep_range_count", {{"start", axis.value("start", Json()).dump()},
          {"stop", axis.value("stop", Json()).dump()}, {"count", axis.value("count", Json()).dump()}});
    }
    else {
      values = catalog.format("ai.sweep_range_step", {{"start", axis.value("start", Json()).dump()},
          {"stop", axis.value("stop", Json()).dump()}, {"step", axis.value("step", Json()).dump()}});
    }
    text += "\n" + catalog.format("ai.sweep_axis", {{"field", name}, {"values", values}});
  }
  return text;
}

std::string parameter_reply(const Json &reply, const Json &context, EditorContext &ctx)
{
  const auto original = io::get_string(reply, "text");
  // A reply is still unvalidated model text. Bound nesting before parsing or
  // serializing any value; deeply nested invalid suggestions stay plain text.
  int depth = 0;
  bool quoted = false, escaped = false;
  for (const char c : original) {
    if (escaped) { escaped = false; continue; }
    if (quoted && c == '\\') { escaped = true; continue; }
    if (c == '"') { quoted = !quoted; continue; }
    if (quoted) { continue; }
    if ((c == '{' || c == '[') && ++depth > 8) { return original; }
    if ((c == '}' || c == ']') && --depth < 0) { return original; }
  }
  try {
    const auto content = Json::parse(original);
    if (content.at("format") == "stk.parameter-sweep/1") { return sweep_reply(content, context, ctx, original); }
    if (content.at("format") != "stk.parameter-edits/1" || !content.at("summary").is_string() ||
        !content.at("edits").is_array() || content.at("edits").empty() || content.at("edits").size() > 1000) { return original; }
    std::string text = content.at("summary").get<std::string>() + "\n\n" +
        ctx.store.catalog().format("ai.suggested_changes", {{"count", std::to_string(content.at("edits").size())}});
    const auto fields = context.at("content").at("value").at("fields");
    const auto records = context.at("selection").at("record_ids");
    for (const auto &edit : content.at("edits")) {
      if (!edit.is_object() || !edit.at("field_id").is_string() || !edit.at("record_id").is_string() ||
          !edit.at("value").is_primitive()) { return original; }
      const auto field = std::find_if(fields.begin(), fields.end(), [&](const auto &item) { return item.at("id") == edit.at("field_id"); });
      const auto record = std::find(records.begin(), records.end(), edit.at("record_id"));
      const auto row = record == records.end() ? "?" : std::to_string(std::distance(records.begin(), record) + 1);
      const auto name = field == fields.end() ? "?" : io::get_string(*field, "name");
      text += "\n" + ctx.store.catalog().format("ai.suggested_cell", {{"record", row}, {"field", name},
          {"value", edit.at("value").dump()}});
    }
    // This is display formatting only. The backend compiler independently validates
    // the original saved text before any candidate can be created.
    return text;
  }
  catch (const std::exception &) { return original; }
}

ui::LogBuffer wrapped_text(std::string text, const float width, EditorContext &ctx)
{
  ui::LogBuffer normalized(std::numeric_limits<size_t>::max()), result(std::numeric_limits<size_t>::max());
  normalized.append(text);
  text.clear();
  for (size_t i = 0; i < normalized.line_count(); ++i) { text += std::string(normalized.line(i)) + "\n"; }
  if (ctx.ui) {
    for (const auto &line : ui::break_lines(text, width, ctx.ui->measurer(), ctx.ui->style().mono)) {
      result.append(text.substr(line.begin, line.end - line.begin) + "\n");
    }
  }
  else { result.append(text); }
  return result;
}

class AIEditor final : public Editor {
 public:
  explicit AIEditor(const EditorType &type) : Editor(type) {}

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx);
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
      proposal_navigation_error_.clear();
      picker_.close();
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
    if (!proposal_navigation_error_.empty() &&
        proposal_navigation_request_ == io::get_string(discussion.exchange_request(), "id")) {
      layout.paragraph(proposal_navigation_error_);
    }
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    const float scale = ctx.ui ? ctx.ui->style().unit / 20.0f : 1.0f;
    if (width >= 920.0f * scale) {
      auto &columns = layout.split(0.32f);
      auto &left = columns.column();
      auto &right = columns.column();
      source(left, ctx, state, false);
      if (!picker_.active()) { configuration(left, ctx, state, draft); }
      conversation(right, ctx, state, draft, key, true);
    }
    else {
      bool settings_open = false;
      if (auto *panel = layout.panel("ai_context_settings", ctx.tr("ai.context_settings"), discussion.context().empty())) {
        settings_open = true;
        source(*panel, ctx, state, true);
        if (!picker_.active()) { configuration(*panel, ctx, state, draft); }
      }
      conversation(layout, ctx, state, draft, key, false, settings_open);
    }
  }

 private:
  /** ``endpoint`` is a model endpoint ID (empty: the built-in Token Plan). ``automatic``: the service chooses the
   * endpoint and model for each question (models.route, S1d); the default where the service offers it. */
  struct Draft { std::string text, model, endpoint; bool model_initialized = false, automatic = true; int intent = 0; };

  /** An automatically routed question in flight (S1d): its ranked candidates, those tried, and what it waits for.
   * Fallback to the next candidate happens only when a request definitely was not sent (``adapter_failed``) or a
   * local model could not be started; an uncertain outcome is left to the person. */
  struct AutoAsk {
    std::string key, context_id, text, prompt_version;
    Json candidates = Json::array(), current = Json::object();
    std::set<std::string> tried;  // endpoint IDs
    std::string request_id, previous_id;
    std::string starting;          // the local model (catalog entry) being started for the current attempt
    bool send = false, sent = false, prepare = false;
    std::string notice;            // shown with the question: why another model answers, or that none is left
    std::string starting_notice;   // shown while a local model starts
  };
  std::optional<AutoAsk> auto_;

  static std::string prompt_version(const int intent)
  {
    return intent == 1 ? "stk.parameter-edits/1" : intent == 2 ? "stk.parameter-sweep/1" : "stk.text/1";
  }

  static bool automatic(EditorContext &ctx, const Draft &draft)
  {
    auto &models = ctx.store.models();
    return draft.automatic && models.supported() && models.loaded() && models.route_supported();
  }

  /** The service's ranking for the next question (null while it is read). Read again when the question's context or task,
   * the endpoints, local models or data labels change. */
  static const Json &route(EditorContext &ctx, ProjectState &state, const Draft &draft)
  {
    auto &models = ctx.store.models();
    auto &labels = ctx.store.data_labels();
    labels.sync();
    const auto context_id = io::get_string(state.discussion().context(), "id");
    const auto prompt = prompt_version(draft.intent);
    const bool token_plan_key = state.discussion().provider().value("configured", false);  // ai.credentials.* is not models.*
    const auto key = state.project()->handle + "|" + context_id + "|" + prompt + "|" + std::to_string(models.version()) +
                     "|" + std::to_string(labels.version()) + "|" + (token_plan_key ? "key" : "nokey");
    return models.route(key, state.project()->handle, context_id, prompt);
  }

  /** The endpoint the next question goes to, or nullptr before model settings are read (older services). */
  static const Json *chosen_endpoint(EditorContext &ctx, const Draft &draft)
  {
    auto &models = ctx.store.models();
    models.sync();
    if (!models.supported() || !models.loaded()) { return nullptr; }
    return models.endpoint(draft.endpoint.empty() ? "aliyun-token-plan" : draft.endpoint);
  }


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
    if (picker_.active()) { picker_.draw(layout, ctx, state); return; }
    auto &discussion = state.discussion();
    auto &box = layout.box();
    box.label(ctx.tr("ai.context_title"));
    const auto *table = state.table();
    if (table) {
      box.paragraph(table->name + " · " + row_label(ctx.store, table, state.record_id()));
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
    std::weak_ptr<bool> weak = alive_;
    box.button("ai_choose_scope", ctx.tr("ai.scope.choose"), [this, weak, &state,
        handle = state.project()->handle, revision = state.project()->revision] {
      if (weak.lock() && !picker_.active() && state.project() && state.project()->handle == handle &&
          state.project()->revision == revision && !state.busy() && !state.discussion().busy()) { picker_.begin(state); }
    }).disable(state.busy() || discussion.busy() || state.tables().empty());
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
    // Captured rows by their current position (the UUID start when the row is gone or moved tables).
    auto row_names = std::make_shared<std::unordered_map<std::string, std::string>>();
    for (const auto &cell : captured->cells) {
      if (row_names->count(cell.record_id)) { continue; }
      std::string label = cell.record_id.substr(0, 8);
      for (const auto &table : state.tables()) {
        const auto found = std::find_if(table.records.begin(), table.records.end(), [&cell](const auto &r) { return r.id == cell.record_id; });
        if (found != table.records.end()) { label = row_label(ctx.store, &table, cell.record_id); break; }
      }
      row_names->emplace(cell.record_id, std::move(label));
    }
    spec.cell = [captured, row_names, store = &ctx.store](int row, int col) {
      const auto &cell = captured->cells[size_t(row)];
      if (col == 0) { return row_names->at(cell.record_id); }
      if (col == 1) { return cell.field_name + (cell.unit.empty() ? "" : " / " + cell.unit); }
      if (col == 2) { return cell.value_text; }
      return std::string(store->tr("discussion.cells." + (cell.status == "omitted" ? std::string("omitted_value") : cell.status)));
    };
    if (auto *preview = box.panel("ai_context_preview", ctx.tr("discussion.cells.title"), !compact)) {
      preview->table("ai_context_cells", std::move(spec));
    }
    hint(box, ctx, "ai.context_hint");
  }

  void configuration(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft)
  {
    auto &discussion = state.discussion();
    auto &models = ctx.store.models();
    auto &box = layout.box();
    const auto *endpoint = chosen_endpoint(ctx, draft);
    const bool choose_automatically = automatic(ctx, draft);
    if (models.supported() && models.loaded()) {
      // Automatic, the built-in Token Plan or an endpoint added on this computer (docs/design/model-gateway.md).
      static const std::string kAutomatic = "\x01automatic";
      std::vector<std::string> ids, names;
      if (models.route_supported()) {
        ids.push_back(kAutomatic);
        names.push_back(std::string(ctx.tr("models.auto.option")));
      }
      for (const auto &item : models.endpoints()) {
        ids.push_back(io::get_string(item, "id"));
        names.push_back(io::get_string(item, "name") + " · " + std::string(ctx.tr("models.location." + io::get_string(item, "location"))));
      }
      auto *settings = &models;
      box.prop(ctx.tr("models.endpoint")).dropdown("ai_endpoint", std::move(names), {
        [&draft, ids, choose_automatically] {
          const auto it = std::find(ids.begin(), ids.end(), choose_automatically ? kAutomatic :
              draft.endpoint.empty() ? std::string("aliyun-token-plan") : draft.endpoint);
          return it == ids.end() ? -1 : int(it - ids.begin());
        },
        [&draft, ids, settings](const int index) {
          if (index < 0 || size_t(index) >= ids.size()) { return; }
          draft.automatic = ids[size_t(index)] == kAutomatic;
          if (draft.automatic) { return; }
          draft.endpoint = ids[size_t(index)] == "aliyun-token-plan" ? std::string() : ids[size_t(index)];
          if (const auto *chosen = settings->endpoint(ids[size_t(index)]); chosen && !io::get_bool(*chosen, "builtin", false)) {
            const auto offered = chosen->value("models", Json::array());
            draft.model = offered.empty() ? std::string() : offered.front().get<std::string>();
            draft.model_initialized = true;
          }
        }});
    }
    else { box.label("Alibaba Token Plan"); }
    // Automatic: what it will use and why; the Token Plan's key and this project's usage stay below, as for the Token Plan.
    if (choose_automatically) { automatic_choice(box, ctx, state, draft); }
    const bool builtin = choose_automatically || !endpoint || io::get_bool(*endpoint, "builtin", false);
    if (choose_automatically) {
      // No model field: the choice above names it.
    }
    else if (builtin) {
      auto &model = box.prop(ctx.tr("discussion.requests.model")).text_field("ai_model/" + state.project()->handle, {
        [&draft] { return draft.model; }, [&draft](const std::string &value) { draft.model = value; draft.model_initialized = true; }
      }, {.max_length = 128});
      model_has_text_ = ctx.ui && ctx.ui->editing() == model.id && ctx.ui->edit_state() ?
          !ctx.ui->edit_state()->text().empty() : !draft.model.empty();
    }
    else {
      std::vector<std::string> offered;
      for (const auto &name : endpoint->value("models", Json::array())) { offered.push_back(name.get<std::string>()); }
      box.prop(ctx.tr("discussion.requests.model")).dropdown("ai_endpoint_model", offered, {
        [&draft, offered] { const auto it = std::find(offered.begin(), offered.end(), draft.model); return it == offered.end() ? -1 : int(it - offered.begin()); },
        [&draft, offered](const int index) { if (index >= 0 && size_t(index) < offered.size()) { draft.model = offered[size_t(index)]; } }});
      model_has_text_ = std::find(offered.begin(), offered.end(), draft.model) != offered.end();
    }
    if (!choose_automatically && endpoint && !io::get_bool(*endpoint, "allowed", true)) { box.paragraph(ctx.tr("models.blocked")); }
    if (endpoint && !builtin) {
      endpoint_key(box, ctx, *endpoint);
      model_settings(box, ctx);
      return;
    }
    const auto &provider = discussion.provider();
    const bool configured = provider.value("configured", false);
    const auto source = io::get_string(provider, "key_source");
    box.paragraph(ctx.tr(!configured ? "ai.missing_key" : source == "environment" ? "ai.key.environment" :
                         source == "saved" ? "ai.key.saved" : source == "session" ? "ai.key.session" : "ai.configured"));
    usage(box, ctx, state);
    box.button("ai_provider_refresh", ctx.tr("discussion.requests.provider_refresh"), [&discussion, &state, handle = state.project()->handle] {
      if (state.project() && state.project()->handle == handle) { discussion.load_provider(); }
    })
        .disable(state.busy() || discussion.busy());
    if (!discussion.key_settings_supported() || provider.empty()) { return; }
    if (auto *keys = box.panel("ai_key_settings", ctx.tr("ai.key.title"), !configured)) {
      // The key goes to the local Python service only and is cleared from this field once handed over.
      auto &field = keys->text_field("ai_key", ui::bind(key_text_), {
          .placeholder = std::string(ctx.tr("ai.key.placeholder")), .max_length = 4096, .password = true});
      const bool key_typed = ctx.ui && ctx.ui->editing() == field.id && ctx.ui->edit_state() ?
          !ctx.ui->edit_state()->text().empty() : !key_text_.empty();
      keys->checkbox("ai_key_remember", ctx.tr("ai.key.remember"), ui::bind(key_remember_))
          .disable(!provider.value("can_remember", false));
      auto &row = keys->row();
      row.button("ai_key_save", ctx.tr("ai.key.save"), [this, &discussion] {
        const auto key = std::exchange(key_text_, std::string());
        if (!key.empty()) { discussion.set_key(key, key_remember_); }
      }).disable(discussion.busy() || !key_typed);
      row.button("ai_key_clear", ctx.tr("ai.key.clear"), [&discussion] { discussion.clear_key(); })
          .disable(discussion.busy() || (source != "session" && source != "saved"));
      if (source == "environment") { keys->paragraph(ctx.tr("ai.key.environment_wins")); }
      hint(*keys, ctx, "ai.key.hint");
    }
    model_settings(box, ctx);
  }

  /** What "Automatic" will use for the next question and why, or why no model can answer it. */
  void automatic_choice(ui::Layout &box, EditorContext &ctx, ProjectState &state, const Draft &draft)
  {
    const auto &ranked = route(ctx, state, draft);
    model_has_text_ = false;
    if (state.discussion().context().empty()) { box.paragraph(ctx.tr("models.auto.no_context")); return; }
    if (ranked.is_null()) { box.paragraph(ctx.tr("models.auto.reading")); return; }
    if (ranked.contains("error")) { box.paragraph(io::get_string(ranked, "error")); return; }
    const auto choice = ranked.value("choice", Json());
    if (choice.is_null()) {
      box.paragraph(ctx.tr("models.auto.none"));
      std::set<std::string> reasons;
      for (const auto &item : ranked.value("excluded", Json::array())) { reasons.insert(io::get_string(item, "reason")); }
      for (const auto &reason : reasons) { box.paragraph(ctx.tr("models.auto.excluded." + reason)); }
      return;
    }
    model_has_text_ = true;
    box.paragraph(ctx.store.catalog().format("models.auto.choice", {{"name", io::get_string(choice, "name")},
        {"model", io::get_string(choice, "model")}}));
    box.paragraph(ctx.tr(io::get_string(ranked, "task") == "simple" ? "models.auto.simple" : "models.auto.complex"));
    if (!io::get_bool(ranked, "public", false)) { box.paragraph(ctx.tr("models.auto.private")); }
    if (io::get_bool(choice, "start", false)) { box.paragraph(ctx.tr("models.auto.will_start")); }
  }

  /** Local model state by catalog entry (``stopped`` when not listed). */
  static std::string local_state(ModelSettings &models, const std::string &entry)
  {
    const auto &local = models.local();
    if (!local.is_object()) { return {}; }  // not read yet (or the read failed): neither running nor failed
    for (const auto &item : local.value("installed", Json::array())) {
      if (io::get_string(item, "id") == entry) { return io::get_string(item.value("server", Json::object()), "state"); }
    }
    return "stopped";
  }

  /** Move an automatically routed question along: attach its prepared request, start a local model it needs, send it,
   * and fall back to the next candidate when it definitely was not sent. Runs every frame; does nothing otherwise. */
  void advance_auto(EditorContext &ctx, ProjectState &state)
  {
    if (!auto_ || auto_->key != active_draft_) { return; }
    auto &discussion = state.discussion();
    auto &models = ctx.store.models();
    if (auto_->prepare) {  // the next candidate's question, once the previous exchange read has finished
      if (discussion.exchange_busy() || discussion.busy() || state.busy()) { return; }
      auto_->prepare = false;
      if (!discussion.prepare_question(auto_->context_id, auto_->text, io::get_string(auto_->current, "model"),
                                       auto_->prompt_version, io::get_string(auto_->current, "adapter"))) {
        auto_->notice = std::string(ctx.tr("models.auto.exhausted"));
        auto_->send = false;
        return;
      }
      auto_->request_id = discussion.exchange_id();
      return;
    }
    const auto &request = discussion.exchange_request();
    const auto id = io::get_string(request, "id");
    if (auto_->request_id.empty() || id != auto_->request_id || !auto_->send) { return; }
    const auto status = io::get_string(request, "status");
    if (!auto_->sent && status != "pending") {  // cancelled (or ended) before STK sent it: nothing more happens
      auto_->send = false;
      auto_->starting.clear();
      auto_->starting_notice.clear();
      return;
    }
    const auto adapter = io::get_string(auto_->current, "adapter");
    if (!auto_->starting.empty()) {
      // Only this start's events count (local_action dropped earlier ones); the list may still show an old failure.
      const auto *progress = models.progress(auto_->starting);
      const auto stage = progress ? io::get_string(*progress, "stage") : std::string();
      if (stage == "failed") { fall_back(ctx, true); return; }
      if ((stage == "running" || local_state(models, auto_->starting) == "running") && models.by_adapter(adapter)) {
        auto_->starting.clear();
        auto_->starting_notice.clear();
        auto_->sent = discussion.start_request(id);
      }
      return;
    }
    if (!auto_->sent) {
      const auto entry = io::get_string(auto_->current, "model");
      if (io::get_bool(auto_->current, "start", false) && local_state(models, entry) != "running") {
        if (!models.local_action("start", entry)) {
          if (!models.local_supported() || !models.editable()) { fall_back(ctx, true); }  // cannot be started from here
          return;  // another settings change is in flight: again next frame
        }
        auto_->starting = entry;
        auto_->starting_notice = ctx.store.catalog().format("models.auto.starting", {{"name", io::get_string(auto_->current, "name")}});
        return;
      }
      auto_->sent = discussion.start_request(id);
      return;
    }
    if (status == "failed" && io::get_string(request, "error_code") == "adapter_failed") { fall_back(ctx, false); }
  }

  /** The current candidate definitely did not receive the question (``not_started``: its local model could not be
   * started): ask the next candidate on another endpoint, as a new request. */
  void fall_back(EditorContext &ctx, const bool not_started)
  {
    const auto failed = io::get_string(auto_->current, "name");
    const Json *next = nullptr;
    for (const auto &item : auto_->candidates) {
      if (!auto_->tried.count(io::get_string(item, "endpoint"))) { next = &item; break; }
    }
    auto_->starting.clear();
    auto_->starting_notice.clear();
    if (!next) {
      auto_->notice = ctx.store.catalog().format(not_started ? "models.auto.start_exhausted" : "models.auto.exhausted_after",
                                                 {{"name", failed}});
      auto_->send = false;
      return;
    }
    auto_->tried.insert(io::get_string(*next, "endpoint"));
    auto_->current = *next;
    auto_->previous_id = auto_->request_id;
    auto_->request_id.clear();
    auto_->sent = false;
    auto_->prepare = true;
    auto_->notice = ctx.store.catalog().format(not_started ? "models.auto.start_fallback" : "models.auto.fallback",
                                               {{"name", failed}, {"next", io::get_string(*next, "name")}});
  }

  /** The key of an added endpoint (optional: local endpoints usually need none). Never shown or kept here. */
  void endpoint_key(ui::Layout &box, EditorContext &ctx, const Json &endpoint)
  {
    auto &models = ctx.store.models();
    const auto id = io::get_string(endpoint, "id");
    if (io::get_bool(endpoint, "managed", false)) {  // a local model's server: STK sets its key at each start
      box.paragraph(ctx.tr("models.key.managed"));
      return;
    }
    const auto key = endpoint.value("key", Json::object());
    const auto source = io::get_string(key, "source");
    box.paragraph(ctx.tr(!io::get_bool(key, "configured", false) ? "models.key.none" : source == "environment" ? "ai.key.environment" :
                         source == "saved" ? "ai.key.saved" : "ai.key.session"));
    if (!models.editable()) { return; }
    if (auto *keys = box.panel("ai_endpoint_key", ctx.tr("models.key.title"), false)) {
      auto &field = keys->text_field("ai_endpoint_key_text", ui::bind(key_text_), {
          .placeholder = std::string(ctx.tr("ai.key.placeholder")), .max_length = 4096, .password = true});
      const bool typed = ctx.ui && ctx.ui->editing() == field.id && ctx.ui->edit_state() ?
          !ctx.ui->edit_state()->text().empty() : !key_text_.empty();
      keys->checkbox("ai_endpoint_key_remember", ctx.tr("ai.key.remember"), ui::bind(key_remember_))
          .disable(!io::get_bool(key, "can_remember", false));
      auto &row = keys->row();
      auto *settings = &models;
      row.button("ai_endpoint_key_save", ctx.tr("ai.key.save"), [this, settings, id] {
        const auto value = std::exchange(key_text_, std::string());
        if (!value.empty()) { settings->set_key(id, value, key_remember_); }
      }).disable(models.busy() || !typed);
      row.button("ai_endpoint_key_clear", ctx.tr("ai.key.clear"), [settings, id] { settings->clear_key(id); })
          .disable(models.busy() || (source != "session" && source != "saved"));
    }
  }

  /** The network setting and the endpoints added on this computer (changed only here, never by scripts). */
  void model_settings(ui::Layout &box, EditorContext &ctx)
  {
    auto &models = ctx.store.models();
    if (!models.editable() || !models.loaded()) { return; }
    auto *panel = box.panel("ai_model_settings", ctx.tr("models.settings"), false);
    if (!panel) { return; }
    auto *settings = &models;
    const std::vector<std::string> modes = {"offline", "organization", "internet"};
    panel->prop(ctx.tr("models.network")).dropdown("ai_network", {
        std::string(ctx.tr("models.network.offline")), std::string(ctx.tr("models.network.organization")),
        std::string(ctx.tr("models.network.internet"))}, {
      [settings, modes] { const auto it = std::find(modes.begin(), modes.end(), settings->network()); return it == modes.end() ? -1 : int(it - modes.begin()); },
      [settings, modes](const int index) { if (index >= 0 && size_t(index) < modes.size()) { settings->set_network(modes[size_t(index)]); } }
    }).disable(models.busy());
    hint(*panel, ctx, "models.network.hint");
    panel->label(ctx.tr("models.added"));
    for (const auto &item : models.endpoints()) {
      if (io::get_bool(item, "builtin", false)) { continue; }
      const auto id = io::get_string(item, "id");
      auto &row = panel->row();
      row.label(io::get_string(item, "name") + " · " + std::string(ctx.tr("models.location." + io::get_string(item, "location")))).tip(
          io::get_string(item, "base_url"));
      row.button("ai_endpoint_remove/" + id, ctx.tr("models.remove"), [settings, id] { settings->remove_endpoint(id); })
          .width(4).disable(models.busy() || io::get_bool(item, "managed", false))  // removed with its local model
          .tip(io::get_bool(item, "managed", false) ? std::string(ctx.tr("models.managed_remove")) : std::string());
    }
    if (auto *add = panel->panel("ai_endpoint_add", ctx.tr("models.add.title"), false)) {
      hint(*add, ctx, "models.add.hint");
      add->prop(ctx.tr("models.add.id")).text_field("ai_endpoint_add_id", ui::bind(new_endpoint_.id), {.max_length = 32});
      add->prop(ctx.tr("models.add.name")).text_field("ai_endpoint_add_name", ui::bind(new_endpoint_.name), {.max_length = 64});
      add->prop(ctx.tr("models.add.base_url")).text_field("ai_endpoint_add_url", ui::bind(new_endpoint_.base_url),
          {.placeholder = "http://127.0.0.1:8080/v1", .max_length = 2048});
      add->prop(ctx.tr("models.add.models")).text_field("ai_endpoint_add_models", ui::bind(new_endpoint_.models), {.max_length = 2048});
      add->checkbox("ai_endpoint_add_internal", ctx.tr("models.add.internal"), ui::bind(new_endpoint_.internal));
      // How capable its models are, for the automatic choice (index 0: judged by where the endpoint is).
      add->prop(ctx.tr("models.add.tier")).dropdown("ai_endpoint_add_tier", {
          std::string(ctx.tr("models.tier.default")), std::string(ctx.tr("models.tier.tiny")), std::string(ctx.tr("models.tier.small")),
          std::string(ctx.tr("models.tier.medium")), std::string(ctx.tr("models.tier.large"))}, ui::bind(new_endpoint_.tier));
      add->button("ai_endpoint_add_button", ctx.tr("models.add.button"), [this, settings] {
        std::vector<std::string> names;
        std::string current;
        for (const char c : new_endpoint_.models + ",") {
          if (c == ',') {
            const auto begin = current.find_first_not_of(" \t"), end = current.find_last_not_of(" \t");
            if (begin != std::string::npos) { names.push_back(current.substr(begin, end - begin + 1)); }
            current.clear();
          }
          else { current.push_back(c); }
        }
        static const char *const kTiers[] = {"", "tiny", "small", "medium", "large"};
        const auto tier = new_endpoint_.tier >= 0 && new_endpoint_.tier < 5 ? kTiers[new_endpoint_.tier] : "";
        if (settings->add_endpoint(new_endpoint_.id, new_endpoint_.name, new_endpoint_.base_url, names,
                                   new_endpoint_.internal ? "internal" : "", tier)) { new_endpoint_ = {}; }
      }).disable(models.busy() || new_endpoint_.id.empty() || new_endpoint_.name.empty() || new_endpoint_.base_url.empty() ||
                 new_endpoint_.models.empty());
    }
    local_models(*panel, ctx);
    if (!models.error().empty()) { panel->paragraph(models.error()); }
  }

  /** One-click local models (S1c): hardware, the catalog with fit and recommendation, install, import, start, stop, remove.
   * Installed entries show their server's state from models.local.list; installations show live progress. */
  void local_models(ui::Layout &panel, EditorContext &ctx)
  {
    auto &models = ctx.store.models();
    if (!models.local_supported()) { return; }
    auto *box = panel.panel("ai_local_models", ctx.tr("models.local.title"), false);
    if (!box) { return; }
    auto &catalog = ctx.store.catalog();
    auto *settings = &models;
    hint(*box, ctx, "models.local.hint");
    if (!models.recommendations().is_object()) {
      if (!models.recommendations_failed()) { models.load_recommendations(); }  // once; a failure waits for "Check again"
      box->paragraph(ctx.tr(models.recommendations_failed() ? "models.local.read_failed" : "models.local.reading"));
      if (models.recommendations_failed()) {
        box->button("ai_local_refresh", ctx.tr("models.local.refresh"), [settings] { settings->load_recommendations(); });
      }
      return;
    }
    const auto gb = [](const double bytes) {
      char text[32];
      std::snprintf(text, sizeof(text), "%.1f", bytes / 1e9);
      return std::string(text);
    };
    const auto &hardware = models.recommendations().value("hardware", Json::object());
    std::string gpus;
    for (const auto &gpu : hardware.value("gpus", Json::array())) {
      gpus += (gpus.empty() ? "" : ", ") + io::get_string(gpu, "name") + " " + gb(double(io::get_int(gpu, "memory_mib", 0)) * 1048576.0) + " GB";
    }
    if (!gpus.empty() && !io::get_bool(hardware, "llama_gpu", true)) { gpus += " " + std::string(ctx.tr("models.local.gpu_unused")); }
    box->paragraph(catalog.format("models.local.hardware", {
        {"memory", gb(double(io::get_int(hardware, "memory_bytes", 0)))},
        {"available", gb(double(io::get_int(hardware, "memory_available_bytes", 0)))},
        {"disk", gb(double(io::get_int(hardware, "disk_free_bytes", 0)))},
        {"cpus", std::to_string(io::get_int(hardware, "cpu_count", 0))},
        {"gpus", gpus.empty() ? std::string(ctx.tr("models.local.no_gpu")) : gpus}}));
    const auto &local = models.local();
    std::map<std::string, Json> installed, jobs;
    if (local.is_object()) {
      for (const auto &item : local.value("installed", Json::array())) { installed[io::get_string(item, "id")] = item; }
      const Json listed_jobs = local.value("jobs", Json::object());  // kept: items() of a temporary would dangle
      for (const auto &[key, job] : listed_jobs.items()) { jobs[key] = job; }
    }
    const bool online = models.network() == "internet";
    std::vector<std::string> import_ids, import_names;
    for (const auto &entry : models.recommendations().value("entries", Json::array())) {
      const auto id = io::get_string(entry, "id");
      const bool vllm = io::get_string(entry, "runtime") == "vllm";
      const auto name = io::get_string(entry, "model") + " · " + io::get_string(entry, "quantization");
      if (!vllm) { import_ids.push_back(id); import_names.push_back(name); }
      std::string text = name + " · " + gb(double(io::get_int(entry, "total_bytes", 0))) + " GB · " +
          catalog.format("models.local.needs", {{"memory", gb(entry.value("min_memory_gb", 0.0) * 1e9)}});
      if (io::get_bool(entry, "recommended", false)) { text += " · " + std::string(ctx.tr("models.local.recommended")); }
      else if (!io::get_bool(entry, "fits", true)) {
        text += " · " + std::string(ctx.tr("models.local.reason." + io::get_string(entry, "reason")));
      }
      box->label(text).tip(io::get_string(entry, "license") + "\n" + io::get_string(entry, "commercial_use") + "\n" +
                           io::get_string(entry, "notes"));
      // The latest installation: live events while it runs, else what the service last reported.
      Json job = jobs.count(id) ? jobs[id] : Json(nullptr);
      if (const auto *live = models.progress(id); live && io::get_string(*live, "stage") != "starting" &&
          io::get_string(*live, "stage") != "running" && io::get_string(*live, "stage") != "stopped") { job = *live; }
      const bool installing = job.is_object() && io::get_string(job, "state") == "running";
      if (job.is_object() && io::get_string(job, "state") != "done") {
        const auto stage = io::get_string(job, "stage");
        const auto total = io::get_int(job, "total_bytes", 0), done = io::get_int(job, "done_bytes", 0);
        std::string line(ctx.tr("models.local.stage." + stage));
        if (stage == "weights" && total > 0) { line += " " + std::to_string(int(100.0 * double(done) / double(total))) + "%"; }
        if (!io::get_string(job, "error").empty()) { line += " · " + io::get_string(job, "error"); }
        box->paragraph(line);
      }
      auto &row = box->row();
      const auto found = installed.find(id);
      if (found == installed.end()) {
        if (vllm) { row.label(ctx.tr("models.local.vllm_manual")); continue; }
        if (installing) {
          row.button("ai_local_cancel/" + id, ctx.tr("models.local.cancel"), [settings, id] { settings->local_action("cancel", id); })
              .width(5).disable(models.busy());
        }
        else {
          row.button("ai_local_install/" + id, ctx.tr("models.local.install"), [settings, id] { settings->local_action("install", id); })
              .width(5).disable(models.busy() || !online || !io::get_bool(entry, "fits", true))
              .tip(ctx.tr(online ? "models.local.install.tip" : "models.local.needs_internet"));
        }
        continue;
      }
      const auto server = found->second.value("server", Json::object());
      const auto state = io::get_string(server, "state", "stopped");
      std::string status(ctx.tr("models.local.server." + state));
      if (!io::get_string(server, "error").empty()) { status += " · " + io::get_string(server, "error"); }
      row.label(status);
      if (!vllm) {
        if (state == "running" || state == "starting") {
          row.button("ai_local_stop/" + id, ctx.tr("models.local.stop"), [settings, id] { settings->local_action("stop", id); })
              .width(5).disable(models.busy());
        }
        else {
          row.button("ai_local_start/" + id, ctx.tr("models.local.start"), [settings, id] { settings->local_action("start", id); })
              .width(5).disable(models.busy() || installing);
        }
      }
      row.button("ai_local_remove/" + id, ctx.tr("models.local.remove"), [settings, id] { settings->local_action("remove", id); })
          .width(5).disable(models.busy() || installing);
    }
    // Offline installations: the model files (and the llama.cpp build, if none is installed) copied to this computer.
    if (auto *offline = box->panel("ai_local_import", ctx.tr("models.local.import.title"), false)) {
      hint(*offline, ctx, "models.local.import.hint");
      offline->prop(ctx.tr("models.local.import.entry")).dropdown("ai_local_import_entry", import_names, ui::bind(import_entry_));
      offline->prop(ctx.tr("models.local.import.path")).text_field("ai_local_import_path", ui::bind(import_path_), {.max_length = 4096});
      offline->button("ai_local_import_button", ctx.tr("models.local.import.button"), [this, settings, import_ids] {
        if (import_entry_ >= 0 && size_t(import_entry_) < import_ids.size() && !import_path_.empty()) {
          settings->import_local(import_ids[size_t(import_entry_)], import_path_);
        }
      }).disable(models.busy() || import_entry_ < 0 || size_t(import_entry_) >= import_ids.size() || import_path_.empty());
    }
    box->button("ai_local_refresh", ctx.tr("models.local.refresh"), [settings] { settings->load_recommendations(); })
        .disable(models.busy());
  }

  /** Tokens this project used, from the provider's receipts with completed replies (UX package U2).
   * Never an amount of money; the provider's console is authoritative. */
  static void usage(ui::Layout &box, EditorContext &ctx, ProjectState &state)
  {
    auto &discussion = state.discussion();
    if (!discussion.usage_supported()) { return; }
    if (!discussion.usage_loaded() && !state.busy()) { discussion.load_usage(); }
    const auto &usage = discussion.usage();
    if (!usage.contains("completed")) { return; }
    auto &catalog = ctx.store.catalog();
    const auto count = [&](const Json &value, const char *key) { return grouped(io::get_int(value, key, 0)); };
    if (io::get_int(usage, "completed", 0) == 0) {
      box.paragraph(ctx.tr("ai.usage.none")).tip(ctx.tr("ai.usage.tip"));
      return;
    }
    std::string text = catalog.format("ai.usage", {{"input", count(usage, "input_tokens")}, {"output", count(usage, "output_tokens")},
                                                   {"completed", count(usage, "completed")}});
    if (const auto missing = io::get_int(usage, "completed", 0) - io::get_int(usage, "reported", 0); missing > 0) {
      text += catalog.format("ai.usage.unreported", {{"count", grouped(missing)}});
    }
    std::string tip(ctx.tr("ai.usage.tip"));
    for (const auto &model : usage.at("models")) {
      tip += "\n" + catalog.format("ai.usage.model", {{"model", io::get_string(model, "model")}, {"requests", count(model, "requests")},
                                                      {"input", count(model, "input_tokens")}, {"output", count(model, "output_tokens")}});
    }
    box.paragraph(text).tip(tip);
  }

  /** 1234567 -> "1,234,567". */
  static std::string grouped(const int64_t value)
  {
    auto digits = std::to_string(value < 0 ? 0 : value);
    for (auto at = digits.size(); at > 3; at -= 3) { digits.insert(at - 3, ","); }
    return digits;
  }

  void conversation(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft,
                    const std::string &key, const bool wide, const bool settings_open = false)
  {
    auto &discussion = state.discussion();
    const bool enabled = !state.busy() && !discussion.busy();
    const std::string handle = state.project()->handle;
    advance_auto(ctx, state);
    discussion.sync_archive();  // archived questions leave the history unless switched to them
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
    archive_switch(layout, ctx, "request", {[&discussion] { return discussion.show_archived("requests"); },
        [&discussion](const bool show) { discussion.set_show_archived("requests", show); }}, "ai_history_show_archived");
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
    const bool parameter_request = request.contains("prompt_version") && structured_proposal(request.at("prompt_version"));
    const bool sweep_request = io::get_string(request, "prompt_version") == "stk.parameter-sweep/1";
    const float unit = ctx.ui ? ctx.ui->style().unit : 20.0f;
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    // Reserve region padding, the split gutter and the log scrollbar. Use the same
    // font as LogView; line breaks affect display only, never the saved reply.
    const float wrap_width = std::max(unit, width * (wide ? 0.68f : 1.0f) - 4 * unit);
    const std::string content = question.dump() + reply.dump() + progress.dump() + std::to_string(wrap_width) +
        std::to_string(unit) + std::string(ctx.tr("ai.you"));
    if (shown_exchange_ != content) {
      shown_exchange_ = content;
      std::string text;
      if (!question.empty()) { text += std::string(ctx.tr("ai.you")) + "\n" + io::get_string(question, "text") + "\n\n"; }
      if (!reply.empty()) {
        text += std::string(ctx.tr(sweep_request ? "ai.sweep_reply" : parameter_request ? "ai.parameter_reply" : "ai.assistant")) + "\n" +
            (parameter_request ? parameter_reply(reply, context, ctx) : io::get_string(reply, "text"));
      }
      else if (!progress.empty() && !io::get_string(progress, "text").empty()) {
        text += std::string(ctx.tr("ai.temporary_reply")) + "\n" + io::get_string(progress, "text");
      }
      // Measure what the log actually displays: tabs expand before wrapping,
      // and terminal escape bytes do not count towards visible line width.
      transcript_ = wrapped_text(std::move(text), wrap_width, ctx);
      raw_reply_ = wrapped_text(io::get_string(reply, "text"), wrap_width, ctx);
    }
    if (!request.empty()) {
      layout.paragraph(std::string(ctx.tr("discussion.requests." + status)) + " · " +
          io::get_string(request.at("configuration"), "model") + " · " + id.substr(0, 8));
      layout.paragraph(ctx.store.catalog().format("ai.request_source", {{"revision", std::to_string(io::get_int(request, "source_revision", -1))},
          {"title", io::get_string(context, "title")}}));
      if (discussion.following()) { layout.label(ctx.tr("ai.following")); }
      else if (status == "running" || status == "uncertain") { layout.paragraph(ctx.tr("ai.paused")); }
      if (request.contains("error_code") && request["error_code"].is_string()) { layout.paragraph(request["error_code"].get<std::string>()); }
      if (auto_ && auto_->key == key && (auto_->request_id == id || auto_->previous_id == id)) {
        if (!auto_->notice.empty()) { layout.paragraph(auto_->notice); }
        if (!auto_->starting_notice.empty()) { layout.paragraph(auto_->starting_notice); }
      }
      archived_notice(layout, ctx, "request", id);
    }
    else { layout.paragraph(ctx.tr(discussion.exchange_busy() ? "ai.loading" : "ai.empty")); }
    const float height = ctx.draw ? float(ctx.draw->rect.height()) : 800.0f;
    const float candidate_space = parameter_request && status == "completed" ? 4.0f : 0.0f;
    const float transcript_units = wide ? std::clamp(height / unit - 23.0f - candidate_space, 5.0f, 22.0f) :
        settings_open ? 6.0f : std::clamp(height / unit - 25.0f - candidate_space, 6.0f, 22.0f);
    layout.log_view("ai_transcript", transcript_, transcript_units);
    const bool archived = ctx.store.archive().archived("request", id);
    // An automatic question whose local model is not running yet is sent once STK has started it.
    const bool auto_request = auto_ && auto_->key == key && auto_->request_id == id && !id.empty();
    const auto blocked = request.empty() || (auto_request && io::get_bool(auto_->current, "start", false)) ? std::string() :
        send_blocked(ctx, discussion, io::get_string(request.value("configuration", Json::object()), "adapter"), &context);
    if (status == "pending" && !blocked.empty() && blocked != "ai.missing_key") { layout.paragraph(ctx.tr(blocked)); }
    auto &actions = layout.row();
    // The saved question goes to the model frozen in it, named on the button.
    const auto send_model = io::get_string(request.value("configuration", Json::object()), "model");
    const auto send_text = send_model.empty() ? std::string(ctx.tr("ai.send_saved")) :
        ctx.store.catalog().format("ai.send_saved_model", {{"model", send_model}});
    actions.button("ai_send_saved", send_text, [this, &discussion, &state, handle, id, auto_request] {
      if (!state.project() || state.project()->handle != handle || io::get_string(discussion.exchange_request(), "id") != id) { return; }
      if (auto_request && auto_ && auto_->request_id == id) {  // started (and sent) next frame; again after a refusal
        auto_->send = true;
        auto_->sent = false;
        return;
      }
      discussion.start_request(id);
    }).disable(!enabled || status != "pending" || archived || !blocked.empty() ||
               (auto_request && auto_ && auto_->send && !auto_->sent));
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
    archive_button(actions, ctx, "request", id, "ai_archive", false, enabled && status != "running" && status != "uncertain");
    if (parameter_request && status == "completed") { proposal_actions(layout, ctx, state, handle, id, enabled); }
    layout.separator();
    layout.label(ctx.tr("ai.compose"));
    layout.prop(ctx.tr("ai.intent")).dropdown("ai_intent/" + handle,
        {std::string(ctx.tr("ai.intent_discuss")), std::string(ctx.tr("ai.intent_edits")), std::string(ctx.tr("ai.intent_sweep"))},
        ui::bind(draft.intent));
    if (draft.intent >= 1 && !discussion.edit_proposals_supported()) { layout.paragraph(ctx.tr("ai.edits_unavailable")); }
    if (draft.intent == 2) { hint(layout, ctx, "ai.intent_sweep.hint"); }
    // Active toolkit edits must disappear on project switch before a new binding is installed.
    auto &input = layout.text_area("ai_question/" + handle, ui::bind(draft.text), {.max_length = 65536, .visible_lines = 4});
    const bool has_question = ctx.ui && ctx.ui->editing() == input.id && ctx.ui->edit_state() ?
        !ctx.ui->edit_state()->text().empty() : !draft.text.empty();
    layout.paragraph(ctx.tr("ai.prepare_hint"));
    if (picker_.active()) { layout.paragraph(ctx.tr("ai.scope.finish_first")); }
    const auto context_id = io::get_string(discussion.context(), "id");
    const auto *target = chosen_endpoint(ctx, draft);
    const auto adapter = target ? io::get_string(*target, "adapter") : std::string();
    const bool choose_automatically = automatic(ctx, draft);
    const auto ranked = choose_automatically ? route(ctx, state, draft) : Json();
    layout.button("ai_prepare", ctx.tr("ai.prepare"), [this, &discussion, &state, handle, key, context_id, adapter, choose_automatically, ranked] {
      if (!state.project() || state.project()->handle != handle || active_draft_ != key || picker_.active()) { return; }
      const auto &current = drafts_.at(key);
      const auto prompt = prompt_version(current.intent);
      if (choose_automatically) {
        const auto choice = ranked.is_object() ? ranked.value("choice", Json()) : Json();
        if (!choice.is_object()) { return; }
        AutoAsk ask;
        ask.key = key; ask.context_id = context_id; ask.text = current.text; ask.prompt_version = prompt;
        ask.candidates = ranked.value("candidates", Json::array());
        ask.current = choice;
        ask.tried.insert(io::get_string(choice, "endpoint"));
        if (discussion.prepare_question(context_id, current.text, io::get_string(choice, "model"), prompt,
                                        io::get_string(choice, "adapter"))) {
          ask.request_id = discussion.exchange_id();
          auto_ = std::move(ask);
          opened_history_ = true;
          proposal_navigation_error_.clear();
        }
        return;
      }
      if (discussion.prepare_question(context_id, current.text, current.model, prompt, adapter)) {
        auto_.reset();
        opened_history_ = true;
        proposal_navigation_error_.clear();
      }
    }).disable(!enabled || picker_.active() || discussion.exchange_busy() || context_id.empty() || !has_question ||
               !(choose_automatically ? ranked.is_object() && ranked.value("choice", Json()).is_object() : model_has_text_) ||
               discussion.provider().empty() ||
               (draft.intent >= 1 && !discussion.edit_proposals_supported()));
    if (auto *details = layout.panel("ai_scope_detail", ctx.tr("ai.scope_detail"), false)) {
      hint(*details, ctx, "ai.single_turn");
      if (!id.empty()) { details->paragraph(id); details->paragraph(io::get_string(request, "context_id")); }
      if (parameter_request && !reply.empty()) {
        details->label(ctx.tr("ai.raw_reply"));
        details->log_view("ai_raw_reply", raw_reply_, 6);
      }
    }
  }

  void proposal_actions(ui::Layout &layout, EditorContext &ctx, ProjectState &state,
                        const std::string &handle, const std::string &id, const bool enabled)
  {
    auto &discussion = state.discussion();
    const auto result = discussion.exchange_edit_proposal();
    const auto saved = result.value("draft", Json());
    const bool current = io::get_int(discussion.exchange_request(), "source_revision", -1) == state.project()->revision;
    const auto saved_status = saved.is_null() ? "" : io::get_string(saved, "status");
    if (saved_status == "applied") {
      layout.paragraph(ctx.store.catalog().format("project.drafts.applied_at", {{"revision", std::to_string(io::get_int(saved, "applied_revision", -1))}}));
    }
    else {
      layout.paragraph(ctx.tr(saved_status == "discarded" ? "ai.edits_discarded" : !current ? "ai.edits_stale" :
          saved.is_null() ? "ai.edits_not_saved" : "ai.edits_saved"));
    }
    if (!saved.is_null()) {
      layout.label(ctx.tr("project.drafts." + io::get_string(saved, "status")));
    }
    // An applied sweep added rows: run them with a workflow over that table (P2 L2). Navigation only;
    // the run panel shows only these rows checked and running still needs its own click.
    if (saved_status == "applied" && io::get_string(discussion.exchange_request(), "prompt_version") == "stk.parameter-sweep/1") {
      Json rows = Json::array();
      std::string table;
      for (const auto &command : saved.value("commands", Json::array())) {
        if (io::get_string(command, "op") == "add_record") { rows.push_back(io::get_string(command, "id")); table = io::get_string(command, "table_id"); }
      }
      if (!rows.empty()) {
        auto *shell = &ctx.area.shell();
        auto *screen = ctx.area.screen();
        const auto self = lifetime();
        const Json target = {{"table_id", table}, {"rows", rows}};
        layout.button("ai_run_rows", ctx.store.catalog().format("ai.run_new_rows", {{"count", std::to_string(rows.size())}}),
            [shell, screen, self, target] {
          shell->open_target_later(screen, kEditorWorkflow, target, [self] { return !self.expired(); });
        }).disable(!enabled || shell->text_input_active()).tip(ctx.tr("ai.run_new_rows.tip"));
      }
    }
    const auto generation = discussion.exchange_generation();
    std::weak_ptr<bool> weak = alive_;
    const auto valid = [weak, &state, &discussion, handle, id, generation] {
      return weak.lock() && state.project() && state.project()->handle == handle &&
          discussion.exchange_generation() == generation && io::get_string(discussion.exchange_request(), "id") == id;
    };
    auto &actions = layout.row();
    actions.button("ai_save_edits", ctx.tr("ai.save_edits"), [this, valid, &discussion, id] {
      if (valid()) { proposal_navigation_error_.clear(); proposal_navigation_request_ = id; discussion.propose_exchange_edits(); }
    }).disable(!enabled || discussion.exchange_busy() || !discussion.edit_proposals_supported() || !saved.is_null() || !current);
    actions.button("ai_open_edits", ctx.tr("ai.open_edits"), [this, valid, weak, &discussion, &state,
        shell = &ctx.area.shell(), screen = ctx.area.screen(), store = &ctx.store, handle, id] {
      if (!valid()) { return; }
      proposal_navigation_error_.clear();
      proposal_navigation_request_ = id;
      const auto revision = state.project()->revision;
      const auto review_generation = state.review_generation();
      discussion.read_exchange_edit_proposal([this, weak, valid, shell, screen, store, handle, revision, review_generation](const Json &fresh) {
        if (!valid()) { return; }
        if (fresh.at("draft").is_null()) { proposal_navigation_error_ = std::string(store->tr("ai.edits_not_saved")); return; }
        shell->open_saved_review(screen, handle, revision, fresh.at("draft"), review_generation, valid,
            [this, weak, store](bridge::Result<Json> opened) {
          if (!weak.lock()) { return; }
          proposal_navigation_error_ = opened.ok() ? "" : opened.error().message;
          store->changed();
        });
      });
    }).disable(!enabled || discussion.exchange_busy() || !discussion.edit_proposals_supported() || !current || saved.is_null() ||
               (!saved.is_null() && io::get_string(saved, "status") != "pending"));
  }

  std::unordered_map<std::string, Draft> drafts_;
  std::string active_draft_, opening_, shown_context_, shown_exchange_;
  bool opened_history_ = false;
  bool model_has_text_ = false;
  struct NewEndpoint { std::string id, name, base_url, models; bool internal = false; int tier = 0; } new_endpoint_;
  int import_entry_ = -1;
  std::string import_path_;
  std::string key_text_;
  bool key_remember_ = false;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::string proposal_navigation_error_, proposal_navigation_request_;
  std::shared_ptr<const CapturedProjectTable> captured_;
  ProjectContextPicker picker_;
  ui::LogBuffer transcript_, raw_reply_;
};
}  // namespace

std::unique_ptr<Editor> make_ai_editor(const EditorType &type)
{
  return std::make_unique<AIEditor>(type);
}
}  // namespace stk::app
