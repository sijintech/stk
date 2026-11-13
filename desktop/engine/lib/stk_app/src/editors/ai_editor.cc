/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "workspace_fields.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/project_agent.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/app/shell.hh"
#include "stk/core/utf8.hh"
#include "stk/wm/window.hh"
#include "stk/ui/utf8.hh"
#include "archive_controls.hh"
#include "model_gate.hh"
#include "project_context_picker.hh"
#include "project_navigation.hh"
#include "project_labels.hh"
#include "editor_text.hh"
#include "saved_conversation.hh"
#include "simulation_target.hh"
#include "stk/app/jobs_state.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
#include <list>
#include <map>
#include <optional>
#include <set>
#include <unordered_map>
#include <utility>

namespace stk::app {
namespace {
using io::Json;

constexpr float kConversationWidth = 880.0f;

std::string conversation_title(std::string_view text)
{
  std::string title;
  for (size_t pos = 0; pos < text.size();) {
    size_t length = 0;
    const auto cp = ui::utf8::decode(text, pos, &length);
    pos += length;
    if (cp < 0x20 || (cp >= 0x7f && cp <= 0x9f) || ui::utf8::is_space(cp) ||
        cp == 0x61c || cp == 0x200e || cp == 0x200f || (cp >= 0x202a && cp <= 0x202e) ||
        (cp >= 0x2066 && cp <= 0x2069)) {
      if (!title.empty() && title.back() != ' ') { title += ' '; }
    }
    else { ui::utf8::append(title, cp); }
  }
  if (!title.empty() && title.back() == ' ') { title.pop_back(); }
  return core::utf8::truncate_display(title, 80);
}

ui::Layout &focused_conversation_column(ui::Layout &layout)
{
  const auto &style = layout.ctx().style();
  const float usable = layout.block().rect().w - 2.0f * style.panel_margin;
  const float gutter = std::ceil(std::max(0.0f, usable - kConversationWidth * style.scale) / 2.0f);
  if (gutter == 0.0f) { return layout; }
  auto &row = layout.row(true);
  row.separator(gutter / style.unit);
  auto &column = row.column();
  row.separator(gutter / style.unit);
  return column;
}

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

/** Wraps for the font the LogView draws with: monospace unless the caller clears the view's mono. */
ui::LogBuffer wrapped_text(std::string text, const float width, EditorContext &ctx, const bool mono)
{
  ui::LogBuffer normalized(std::numeric_limits<size_t>::max()), result(std::numeric_limits<size_t>::max());
  normalized.append(text);
  text.clear();
  for (size_t i = 0; i < normalized.line_count(); ++i) { text += std::string(normalized.line(i)) + "\n"; }
  if (ctx.ui) {
    const auto &style = ctx.ui->style();
    for (const auto &line : ui::break_lines(text, width, ctx.ui->measurer(), mono ? style.mono : style.font)) {
      result.append(text.substr(line.begin, line.end - line.begin) + "\n");
    }
  }
  else { result.append(text); }
  return result;
}

/** LogView scrolls vertically only. Wrap on UTF-8 boundaries without dropping even a space inside a JSON value. */
std::optional<ui::LogBuffer> frozen_plan_text(const std::string &text, const float width, EditorContext &ctx)
{
  if (!ctx.ui || width <= 0) { return std::nullopt; }
  ui::LogBuffer result(std::numeric_limits<size_t>::max());
  size_t begin = 0;
  float used = 0;
  for (size_t p = 0; p < text.size();) {
    const size_t next = ui::utf8::next(text, p);
    if (text[p] == '\n') {
      result.append(text.substr(begin, p - begin) + "\n"); begin = next; used = 0;
    }
    else {
      const float advance = ctx.ui->measurer().width(std::string_view(text).substr(p, next - p), ctx.ui->style().mono);
      if (advance > width) { return std::nullopt; }  // cannot show a complete glyph: never unlock approval
      if (used + advance > width && p > begin) {
        result.append(text.substr(begin, p - begin) + "\n"); begin = p; used = 0;
      }
      used += advance;
    }
    p = next;
  }
  if (begin < text.size()) { result.append(text.substr(begin) + "\n"); }
  return result;
}

class AIEditor final : public Editor {
 public:
  explicit AIEditor(const EditorType &type) : Editor(type) {}
  void on_area_removed() override { ++run_detail_owner_epoch_; }

  nlohmann::json save_workspace_state() const override
  {
    Json drafts = Json::array();
    for (const auto &[key, draft] : drafts_) {
      const auto split = key.rfind('\n');
      if (split == std::string::npos) { continue; }
      drafts.push_back({{"project", key.substr(split + 1)}, {"text", draft.text},
                        {"agent_text", draft.agent_text}, {"intent", draft.intent}});
    }
    for (const auto &[project, draft] : workspace_drafts_) {
      drafts.push_back({{"project", project}, {"text", draft.text}, {"agent_text", draft.agent_text}, {"intent", draft.intent}});
    }
    return {{"version", 1}, {"drafts", drafts}};
  }
  bool load_workspace_state(const nlohmann::json &value) override
  {
    if (!workspace_fields(value, {}, {}, {}, {"drafts"}) || !value.contains("drafts") ||
        !value.at("drafts").is_array() || value.at("drafts").size() > 128) { return false; }
    std::unordered_map<std::string, Draft> drafts;
    for (const auto &item : value.at("drafts")) {
      if (!item.is_object() || !item.contains("project") || !item.at("project").is_string() ||
          !item.contains("text") || !item.at("text").is_string() || !item.contains("agent_text") ||
          !item.at("agent_text").is_string() || !item.contains("intent") || !item.at("intent").is_number_integer() ||
          item.at("intent").get<int64_t>() < 0 || item.at("intent").get<int64_t>() > 3 ||
          io::get_string(item, "project").size() > 64 || drafts.count(io::get_string(item, "project"))) { return false; }
      Draft draft; draft.text = io::get_string(item, "text"); draft.agent_text = io::get_string(item, "agent_text");
      draft.intent = int(io::get_int(item, "intent", 0)); drafts.emplace(io::get_string(item, "project"), std::move(draft));
    }
    workspace_drafts_ = std::move(drafts); return true;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    const auto *screen = ctx.area.screen();
    const bool focused = screen && screen->maximized() == &ctx.area && ctx.area.shell().workbench_is_focused(*screen);
    auto &state = ctx.store.project();
    state.sync();
    workspace_link(row, ctx, focused);
    if (focused) {
      auto showing_question = [this, weak = lifetime(), &state] { return !weak.expired() && shows_question_page(state); };
      if (auto literature = ctx.area.shell().focused_literature_action(ctx.area, std::move(showing_question))) {
        const auto label = ctx.tr("workbench.open_literature");
        const auto &style = row.ctx().style();
        row.button("ai_open_literature", label, std::move(literature))
            .width((row.ctx().measurer().width(label, style.font) + 2 * style.text_margin) / style.unit);
      }
    }
    row.button("ai_tables", ctx.tr("editor.project.title"), [ctx] { show_tables(ctx); }).width(7);
    if (state.project()) { row.label(state.project()->name); }
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    const auto *screen = ctx.area.screen();
    const bool focused = screen && screen->maximized() == &ctx.area && ctx.area.shell().workbench_is_focused(*screen);
    auto &state = ctx.store.project();
    state.sync();
    // Any page of this editor that does not draw the open linked-task detail (another purpose, project, session or
    // a card that is gone) closes it, so it never reappears later over another state.
    struct DetailFrame {
      AIEditor &self; ProjectState &state;
      ~DetailFrame() { if (!self.run_detail_drawn_) { self.close_run_detail(state, false); } }
    } detail_frame{*this, state};
    run_detail_drawn_ = false;
    if (!state.ready()) { layout.paragraph(ctx.tr("project.bridge_required")); return; }
    if (!state.project()) {
      layout.paragraph(ctx.tr("ai.open_project"));
      auto &actions = layout.row().alignment(ui::LayoutAlign::Left);
      actions.button("ai_open_project", ctx.tr("project.location"), [ctx] { show_tables(ctx); });
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
      transcript_positions_.clear();
      shown_context_.clear(); captured_.reset();
      proposal_navigation_error_.clear();
      picker_.close();
    }
    // Unsent input belongs to its project even when another project becomes active. It is
    // intentionally not part of layout JSON; only explicitly prepared questions are persisted.
    const std::string key = state.project()->directory + "\n" + state.project()->id;
    active_draft_ = key;
    auto &draft = project_draft(*state.project(), key);
    if (shows_saved_questions(discussion, opening, focused)) {
      opened_history_ = true; // Browsing has no implicit question selection.
      discussion.sync_archive();
      const auto &page = discussion.page("requests");
      if (!page.loaded && !state.busy() && !discussion.busy()) {
        discussion.load_page("requests", page.offset, true);
      }
      auto &header = layout.row();
      header.label(ctx.tr("ai.history"));
      header.button("ai_close_saved_questions", ctx.tr("ui.close"), [this, store = &ctx.store] {
        saved_questions_handle_.clear();
        store->changed();
      }).width(6);
      if (!discussion.error().empty()) { layout.paragraph(discussion.error()); }
      else if (discussion.busy() && page.items.empty()) { layout.label(ctx.tr("workbench.history.loading")); }
      else if (page.loaded && page.items.empty()) { layout.label(ctx.tr("workbench.history.empty")); }
      draw_saved_questions(layout, ctx, state, true);
      return;
    }
    saved_questions_handle_.clear();
    // Agent sessions (format 13): a fourth purpose with its own view (steps, wait cards, record).
    auto &agent = state.agent();
    if (!pending_session_.empty()) {
      // A session another page asked to show: only in its own project, and not while a message is being saved.
      if (!pending_project_.empty() && pending_project_ != state.project()->id) { pending_session_.clear(); }
      else if (agent.supported() && !agent.busy()) {
        draft.intent = kAgentIntent;
        agent.select(pending_session_);
        pending_session_.clear();
      }
    }
    if (draft.intent == kAgentIntent) {
      if (!agent.supported()) { draft.intent = 0; }
      else {
        auto &body = focused ? focused_conversation_column(layout) : layout;
        agent_view(body, ctx, state, draft, focused);
        return;
      }
    }
    if (!discussion.provider_loaded() && !discussion.busy() && !state.busy()) { discussion.load_provider(); }
    if (!draft.model_initialized && discussion.provider_loaded() && !discussion.provider().empty()) {
      draft.model = io::get_string(discussion.provider(), "model");
      draft.model_initialized = true;
    }
    model_has_text_ = !draft.model.empty();
    poll(ctx, discussion);
    auto &body = focused ? focused_conversation_column(layout) : layout;
    const bool compose_first = focused && compose_handle_ == opening;
    if (focused && !compose_first && !discussion.exchange_request().empty()) {
      auto title = conversation_title(io::get_string(discussion.exchange_question(), "text"));
      if (title.empty()) { title = ctx.tr("ai.history"); }
      body.label(title).tip(title);
    }
    if (compose_first) {
      const auto visibility = std::exchange(compose_focus_visibility_, std::nullopt);
      const bool focus = visibility && *visibility == screen->visibility_epoch();
      body.block().set_scroll_scope("ai_question_composer", focus);
      const auto &input = question_composer(body, ctx, state, draft, key, true);
      if (focus && ctx.ui) { ctx.ui->restore_focus_next_frame(input.key); }
      draw_return_to_question(body, ctx, state);
    }
    if (!focused) { body.paragraph(ctx.tr("ai.intro")); }
    if (!state.error().empty()) { body.paragraph(state.error()); }
    if (!discussion.error().empty()) { body.paragraph(discussion.error()); }
    if (!discussion.exchange_error().empty()) { body.paragraph(discussion.exchange_error()); }
    if (!proposal_navigation_error_.empty() &&
        proposal_navigation_request_ == io::get_string(discussion.exchange_request(), "id")) {
      body.paragraph(proposal_navigation_error_);
    }
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    const float scale = ctx.ui ? ctx.ui->style().unit / 20.0f : 1.0f;
    if (!focused && width >= 920.0f * scale) {
      auto &columns = layout.split(0.32f);
      auto &left = columns.column();
      auto &right = columns.column();
      source(left, ctx, state, false);
      if (!picker_.active()) { configuration(left, ctx, state, draft); }
      conversation(right, ctx, state, draft, key, true);
    }
    else {
      bool settings_open = false;
      const auto panel_key = focused ? "ai_workbench_context_settings" : "ai_context_settings";
      if (auto *panel = body.panel(panel_key, ctx.tr("ai.context_settings"), !focused && discussion.context().empty())) {
        settings_open = true;
        source(*panel, ctx, state, true);
        if (!picker_.active()) { configuration(*panel, ctx, state, draft); }
      }
      conversation(body, ctx, state, draft, key, false, settings_open, focused, compose_first);
    }
  }

 private:
  void draw_return_to_question(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    auto &discussion = state.discussion();
    const auto request = discussion.exchange_id();
    if (request.empty() || io::get_string(discussion.exchange_request(), "id") != request) { return; }
    auto *area = &ctx.area;
    auto *screen = area->screen();
    const auto handle = state.project()->handle;
    const auto current = [this, weak = lifetime(), area, screen, visibility = screen->visibility_epoch(),
                          activity = area->activity_epoch(), compose = compose_generation_,
                          &state, handle, &discussion, request, exchange = discussion.exchange_generation()] {
      return !weak.expired() && area->screen() == screen && screen->visibility_epoch() == visibility &&
          screen->maximized() == area && area->activity_epoch() == activity && area->shell().workbench_is_focused(*screen) &&
          state.project() && state.project()->handle == handle && compose_generation_ == compose &&
          discussion.exchange_generation() == exchange && discussion.exchange_id() == request &&
          io::get_string(discussion.exchange_request(), "id") == request;
    };
    layout.row().alignment(ui::LayoutAlign::Left).button("ai_return_question", ctx.tr("ai.return_question"),
        [this, current, handle, ui = ctx.ui, key = layout.block().name() + "/ai_transcript", store = &ctx.store] {
      if (!current() || compose_handle_ != handle) { return; }
      compose_handle_.clear();
      compose_focus_visibility_.reset();
      if (ui) {
        ui->restore_focus_next_frame(key, [this, current] { return current() && compose_handle_.empty(); });
      }
      store->changed();
    });
  }

  /** ``endpoint`` is a model endpoint ID (empty: the built-in Token Plan). ``automatic``: the service chooses the
   * endpoint and model for each question (models.route, S1d); the default where the service offers it. */
  struct Draft {
    std::string text, model, endpoint, agent_text;
    bool model_initialized = false, automatic = true, allow_prepare = false;
    int intent = 0;
    SimulationTarget run_target;  // draft controls only; never restored as an active authorization
  };
  static constexpr int kAgentIntent = 3;

  bool shows_saved_questions(const ProjectDiscussion &discussion, const std::string &opening, bool focused) const
  {
    return focused && saved_questions_handle_ == opening && discussion.recent_requests_supported();
  }

  bool shows_question_page(ProjectState &state) const
  {
    const auto &project = state.project();
    const auto &discussion = state.discussion();
    return project && state.ready() && state.loaded() && discussion.generation_supported() &&
           !shows_saved_questions(discussion, project->handle, true) && !shows_or_opens_agent(state);
  }

  bool shows_or_opens_agent(ProjectState &state) const
  {
    if (!state.agent().supported()) { return false; }
    const auto &project = *state.project();
    if (!pending_session_.empty() && (pending_project_.empty() || pending_project_ == project.id)) { return true; }
    if (const auto restored = workspace_drafts_.find(project.id); restored != workspace_drafts_.end()) {
      return restored->second.intent == kAgentIntent;
    }
    const auto draft = drafts_.find(project.directory + "\n" + project.id);
    return draft != drafts_.end() && draft->second.intent == kAgentIntent;
  }

  Draft &project_draft(const bridge::ProjectInfo &project, const std::string &key)
  {
    if (const auto restored = workspace_drafts_.find(project.id); restored != workspace_drafts_.end()) {
      drafts_[key] = std::move(restored->second);
      workspace_drafts_.erase(restored);
    }
    return drafts_[key];
  }

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

  using TranscriptPositions = std::list<std::pair<std::string, ui::LogViewPosition>>;

  static ui::LogViewPosition *transcript_position(TranscriptPositions &positions, const std::string &id)
  {
    // A loading or failed read has no request record. Its blank view must not clamp a saved position.
    if (id.empty()) { return nullptr; }
    const auto found = std::find_if(positions.begin(), positions.end(), [&](const auto &entry) { return entry.first == id; });
    if (found != positions.end()) {
      positions.splice(positions.end(), positions, found);
    }
    else {
      if (positions.size() >= 32) { positions.pop_front(); }
      positions.emplace_back(id, ui::LogViewPosition{});
    }
    return &positions.back().second;
  }

  void draw_saved_questions(ui::Layout &body, EditorContext &ctx, ProjectState &state, const bool browsing = false)
  {
    auto &discussion = state.discussion();
    const bool enabled = !state.busy() && !discussion.busy();
    const std::string handle = state.project()->handle;
    const auto &page = discussion.page("requests");
    std::vector<std::string> ids, titles;
    for (const auto &item : page.items) {
      ids.push_back(io::get_string(item, "id"));
      titles.push_back(io::get_string(item.at("configuration"), "model") + " · " +
          std::string(ctx.tr("discussion.requests." + io::get_string(item, "status"))) + " · " + ids.back().substr(0, 8));
    }
    auto &history = body.row();
    history.dropdown("ai_history", std::move(titles), {
      [ids, &discussion] {
        const auto id = io::get_string(discussion.exchange_request(), "id");
        const auto it = std::find(ids.begin(), ids.end(), id);
        return it == ids.end() ? -1 : int(it - ids.begin());
      },
      [this, ids, &discussion, &state, handle, browsing, area = &ctx.area](int index) {
        if (!state.project() || state.project()->handle != handle || index < 0 || size_t(index) >= ids.size()) { return; }
        const auto &id = ids[size_t(index)];
        if (browsing) {
          if (auto open = area->shell().saved_conversation_action(*area, id)) { open(); }
        }
        else if (discussion.load_exchange(id)) {
          opened_history_ = true;
          compose_handle_.clear();
        }
      }
    }).disable(!enabled || discussion.exchange_busy() || ids.empty());
    history.button("ai_history_refresh", ctx.tr("ai.refresh_history"), [&discussion, &state, handle, offset = page.offset] {
      if (state.project() && state.project()->handle == handle) { discussion.load_page("requests", offset); }
    }).width(6).disable(!enabled);
    archive_switch(body, ctx, "request", {[&discussion] { return discussion.show_archived("requests"); },
        [&discussion](const bool show) { discussion.set_show_archived("requests", show); }}, "ai_history_show_archived");
    if (page.offset > 0 || page.next >= 0) {
      auto &pages = body.row();
      pages.button("ai_previous", ctx.tr("project.drafts.previous"), [&discussion, &state, handle, offset = page.offset] {
        if (state.project() && state.project()->handle == handle) {
          discussion.load_page("requests", std::max<int64_t>(0, offset - 100));
        }
      }).disable(!enabled || page.offset == 0);
      pages.button("ai_next", ctx.tr("project.drafts.next"), [&discussion, &state, handle, next = page.next] {
        if (state.project() && state.project()->handle == handle) { discussion.load_page("requests", next); }
      }).disable(!enabled || page.next < 0);
    }
  }

  void conversation(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft,
                    const std::string &key, const bool wide, const bool settings_open = false,
                    const bool focused = false, const bool compose_first = false)
  {
    auto &discussion = state.discussion();
    const bool enabled = !state.busy() && !discussion.busy();
    const std::string handle = state.project()->handle;
    advance_auto(ctx, state);
    const auto &page = discussion.page("requests");
    const bool history_on_rail = focused && discussion.recent_requests_supported();
    if (!discussion.exchange_id().empty()) { opened_history_ = true; }
    if (!compose_first) {
      discussion.sync_archive();  // Archived questions leave the list unless switched to them.
      // The accepted exchange and the rail do not depend on the separate paginated history.
      if (!page.loaded && enabled && (!history_on_rail || discussion.exchange_id().empty())) {
        discussion.load_page("requests", page.offset, true);
      }
      if (!opened_history_ && page.loaded && !page.items.empty() && enabled && !discussion.exchange_busy()) {
        opened_history_ = discussion.load_exchange(io::get_string(page.items.back(), "id"));
      }
    }
    if (!history_on_rail) {
      layout.label(ctx.tr("ai.history"));
      draw_saved_questions(layout, ctx, state);
    }
    const auto request = discussion.exchange_request();
    const auto question = discussion.exchange_question();
    const auto reply = discussion.exchange_reply();
    const auto progress = discussion.exchange_progress();
    const auto context = discussion.exchange_context();
    const std::string id = io::get_string(request, "id"), status = io::get_string(request, "status");
    const auto model = io::get_string(request.value("configuration", Json::object()), "model");
    const bool pending = status == "pending";
    const bool active = status == "running" || status == "uncertain";
    const bool cancel_requested = io::get_bool(request, "cancel_requested", false);
    const auto current = [&discussion, &state, handle, id] {
      return state.project() && state.project()->handle == handle && io::get_string(discussion.exchange_request(), "id") == id;
    };
    // A list read marks its page loaded at dispatch. Wait for it to settle before using the empty layout.
    const bool compact_empty = focused && (compose_first || (page.loaded && page.items.empty())) && request.empty() &&
                               discussion.exchange_id().empty() && !discussion.busy() && !discussion.exchange_busy() &&
                               discussion.error().empty();
    const bool parameter_request = request.contains("prompt_version") && structured_proposal(request.at("prompt_version"));
    const bool sweep_request = io::get_string(request, "prompt_version") == "stk.parameter-sweep/1";
    const auto &style = layout.ctx().style();
    const float unit = style.unit;
    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    // Reserve region padding, the split gutter and the log scrollbar. Use the same
    // font as LogView; line breaks affect display only, never the saved reply.
    // The focused workbench reads the conversation in the regular UI font; the split view keeps monospace.
    const bool transcript_mono = !focused;
    const float conversation_width = focused ? std::min(layout.block().rect().w, kConversationWidth * style.scale) :
        width * (wide ? 0.68f : 1.0f);
    const float wrap_width = std::max(unit, conversation_width - 4 * unit);
    const std::string content = question.dump() + reply.dump() + progress.dump() + std::to_string(wrap_width) +
        std::to_string(unit) + (transcript_mono ? "/mono/" : "/regular/") + std::string(ctx.tr("ai.you"));
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
      transcript_ = wrapped_text(std::move(text), wrap_width, ctx, transcript_mono);
      raw_reply_ = wrapped_text(io::get_string(reply, "text"), wrap_width, ctx, true);
    }
    if (!request.empty()) {
      auto summary = std::string(ctx.tr("discussion.requests." + status)) + " · " + model;
      if (!focused) { summary += " · " + id.substr(0, 8); }
      layout.paragraph(summary);
      if (!focused) { request_source(layout, ctx, request, context); }
      if (discussion.following()) { layout.label(ctx.tr("ai.following")); }
      else if (active) { layout.paragraph(ctx.tr("ai.paused")); }
      if (focused && active && cancel_requested) { layout.paragraph(ctx.tr("discussion.requests.cancel_requested")); }
      if (request.contains("error_code") && request["error_code"].is_string()) { layout.paragraph(request["error_code"].get<std::string>()); }
      if (auto_ && auto_->key == key && (auto_->request_id == id || auto_->previous_id == id)) {
        if (!auto_->notice.empty()) { layout.paragraph(auto_->notice); }
        if (!auto_->starting_notice.empty()) { layout.paragraph(auto_->starting_notice); }
      }
      archived_notice(layout, ctx, "request", id);
    }
    else if (!compose_first) {
      if (compact_empty) { layout.label(ctx.tr("workbench.question_start"), ui::Align::Center); }
      else { layout.paragraph(ctx.tr(discussion.exchange_busy() ? "ai.loading" : "ai.empty")); }
    }
    if (!compact_empty) {
      const float height = ctx.draw ? float(ctx.draw->rect.height()) : 800.0f;
      const float candidate_space = parameter_request && status == "completed" ? 4.0f : 0.0f;
      const float transcript_units = wide ? std::clamp(height / unit - 23.0f - candidate_space, 5.0f, 22.0f) :
          settings_open ? 6.0f : std::clamp(height / unit - 25.0f - candidate_space, 6.0f, 22.0f);
      layout.log_view("ai_transcript", transcript_, transcript_units, transcript_position(transcript_positions_, id))
          .mono = transcript_mono;
    }
    if (!compact_empty && (!focused || !id.empty())) {
      const bool archived = ctx.store.archive().archived("request", id);
      // An automatic question whose local model is not running yet is sent once STK has started it.
      const bool auto_request = auto_ && auto_->key == key && auto_->request_id == id && !id.empty();
      const auto blocked = request.empty() || (auto_request && io::get_bool(auto_->current, "start", false)) ? std::string() :
          send_blocked(ctx, discussion, io::get_string(request.value("configuration", Json::object()), "adapter"), &context);
      if (pending && !blocked.empty()) {
        if (blocked != "ai.missing_key") { layout.paragraph(ctx.tr(blocked)); }
        else if (focused && !archived) { layout.paragraph(ctx.tr("ai.send.key_required")); }
      }
      auto &actions = layout.row();
      if (focused) { actions.alignment(ui::LayoutAlign::Left); }
      if (!focused || (pending && !archived)) {
        // The saved question goes to the model frozen in it, named on the button.
        const auto send_text = model.empty() ? std::string(ctx.tr("ai.send_saved")) :
            ctx.store.catalog().format("ai.send_saved_model", {{"model", model}});
        actions.button("ai_send_saved", send_text, [this, &discussion, current, id, auto_request] {
          if (!current()) { return; }
          if (auto_request && auto_ && auto_->request_id == id) {  // started (and sent) next frame; again after a refusal
            auto_->send = true;
            auto_->sent = false;
            return;
          }
          discussion.start_request(id);
        }).disable(!enabled || !pending || archived || !blocked.empty() ||
                   (auto_request && auto_ && auto_->send && !auto_->sent));
      }
      actions.button("ai_refresh_reply", ctx.tr("ai.refresh"), [&discussion, current] {
        if (current()) { discussion.refresh_exchange(); }
      }).disable(!enabled || id.empty() || discussion.exchange_busy());
      if (!focused || ((pending || active) && !cancel_requested)) {
        actions.button("ai_cancel", ctx.tr("discussion.requests.cancel"), [&discussion, current, id] {
          if (current()) { discussion.cancel_request(id); }
        }).disable(!enabled || (!pending && !active));
      }
      if (active) {
        auto &recovery = focused ? actions : layout;
        recovery.button("ai_recover", ctx.tr("discussion.requests.recover"), [&discussion, current, id] {
          if (current()) { discussion.recover_request(id); }
        }).disable(!enabled);
      }
      if (!focused || !active) { archive_button(actions, ctx, "request", id, "ai_archive", false, enabled && !active); }
    }
    if (parameter_request && status == "completed") { proposal_actions(layout, ctx, state, handle, id, enabled); }
    if (!compose_first) {
      layout.separator();
      question_composer(layout, ctx, state, draft, key, focused);
    }
    if (auto *details = layout.panel("ai_scope_detail", ctx.tr("ai.scope_detail"), false)) {
      hint(*details, ctx, "ai.single_turn");
      if (!id.empty()) {
        const auto context_id = io::get_string(request, "context_id");
        if (focused) {
          request_source(*details, ctx, request, context);
          const auto show_id = [&](std::string_view kind, const std::string &value) {
            const auto suffix = std::string(kind) + "_id";
            auto &row = details->row();
            row.paragraph(ctx.store.catalog().format("ai." + suffix, {{"id", value}}));
            auto *window = ctx.draw ? ctx.draw->window : nullptr;
            const auto label = ctx.tr("ai.copy_" + suffix);
            row.button("ai_copy_" + suffix, label, [window, value, current, weak = lifetime()] {
              if (window && !weak.expired() && current()) { window->manager().set_clipboard_text(value); }
            }).width((layout.ctx().measurer().width(label, style.font) + 2 * style.text_margin) / style.unit)
              .disable(!window);
          };
          show_id("request", id);
          show_id("context", context_id);
        }
        else { details->paragraph(id); details->paragraph(context_id); }
      }
      if (parameter_request && !reply.empty()) {
        details->label(ctx.tr("ai.raw_reply"));
        details->log_view("ai_raw_reply", raw_reply_, 6);
      }
    }
    if (history_on_rail && !compose_first) {
      if (auto *history = layout.panel("ai_all_saved_questions", ctx.tr("ai.history"), false)) {
        if (!page.loaded && enabled) { discussion.load_page("requests", page.offset, true); }
        draw_saved_questions(*history, ctx, state);
      }
    }
  }

  void request_source(ui::Layout &layout, EditorContext &ctx, const Json &request, const Json &context)
  {
    layout.paragraph(ctx.store.catalog().format("ai.request_source", {
        {"revision", std::to_string(io::get_int(request, "source_revision", -1))},
        {"title", io::get_string(context, "title")}}));
  }

  ui::Widget &question_composer(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft,
                                const std::string &key, const bool focused)
  {
    auto &discussion = state.discussion();
    const bool enabled = !state.busy() && !discussion.busy();
    const std::string handle = state.project()->handle;
    layout.label(ctx.tr("ai.compose"));
    intent_dropdown(layout, ctx, state, draft);
    if (draft.intent >= 1 && !discussion.edit_proposals_supported()) { layout.paragraph(ctx.tr("ai.edits_unavailable")); }
    if (draft.intent == 2) { hint(layout, ctx, "ai.intent_sweep.hint"); }
    const auto context_id = io::get_string(discussion.context(), "id");
    const auto *target = chosen_endpoint(ctx, draft);
    const auto adapter = target ? io::get_string(*target, "adapter") : std::string();
    bool manual_model_ready = model_has_text_;
    if (target && !io::get_bool(*target, "builtin", false)) {
      const auto offered = target->value("models", Json::array());
      manual_model_ready = std::find(offered.begin(), offered.end(), draft.model) != offered.end();
    }
    const bool choose_automatically = automatic(ctx, draft);
    const auto ranked = choose_automatically ? route(ctx, state, draft) : Json();
    const bool can_prepare = enabled && !picker_.active() && !discussion.exchange_busy() && !context_id.empty() &&
        (choose_automatically ? ranked.is_object() && ranked.value("choice", Json()).is_object() : manual_model_ready) &&
        !discussion.provider().empty() && (draft.intent < 1 || discussion.edit_proposals_supported());
    const auto prepare = [this, weak = lifetime(), &discussion, &state, handle, key, context_id, adapter,
                          choose_automatically, ranked, can_prepare, intent = draft.intent] {
      if (weak.expired() || !can_prepare || !state.project() || state.project()->handle != handle ||
          state.busy() || discussion.busy() || discussion.exchange_busy() || active_draft_ != key || picker_.active() ||
          io::get_string(discussion.context(), "id") != context_id) { return; }
      const auto &current = drafts_.at(key);
      if (current.text.empty() || current.intent != intent) { return; }
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
          compose_handle_.clear();
          proposal_navigation_error_.clear();
        }
        return;
      }
      if (discussion.prepare_question(context_id, current.text, current.model, prompt, adapter)) {
        auto_.reset();
        opened_history_ = true;
        compose_handle_.clear();
        proposal_navigation_error_.clear();
      }
    };
    // The focused workbench draws the field, why preparing is blocked and the action on one card, like the Web
    // composer; a box only nests the layout, so keys, IDs and focus order stay those of the split view.
    auto &composer = focused ? layout.box() : layout;
    // Active toolkit edits must disappear on project switch before a new binding is installed.
    auto &input = composer.text_area("ai_question/" + handle, ui::bind(draft.text),
                                     {.max_length = 65536, .visible_lines = 4, .on_submit = prepare,
                                      .submit_when_focused = true, .preserve_on_escape = true});
    const bool has_question = ctx.ui && ctx.ui->editing() == input.id && ctx.ui->edit_state() ?
        !ctx.ui->edit_state()->text().empty() : !draft.text.empty();
    composer.paragraph(ctx.tr(focused && discussion.context().empty() ? "ai.no_context" : "ai.prepare_hint"));
    if (picker_.active()) { composer.paragraph(ctx.tr("ai.scope.finish_first")); }
    auto &actions = focused ? composer.row().alignment(ui::LayoutAlign::Right) : layout;
    actions.button("ai_prepare", ctx.tr("ai.prepare"), prepare).disable(!can_prepare || !has_question)
        .tip(ctx.tr("ai.prepare.shortcut"));
    return input;
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

  void intent_dropdown(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft)
  {
    std::vector<std::string> intents = {std::string(ctx.tr("ai.intent_discuss")), std::string(ctx.tr("ai.intent_edits")),
                                        std::string(ctx.tr("ai.intent_sweep"))};
    if (state.agent().supported()) { intents.push_back(std::string(ctx.tr("ai.intent_agent"))); }
    layout.prop(ctx.tr("ai.intent")).dropdown("ai_intent/" + state.project()->handle, std::move(intents), ui::bind(draft.intent));
  }

 public:
  bool can_reveal_saved(const ProjectState &state) const
  {
    return state.project() && (opening_ != state.project()->handle || !picker_.active()) &&
           (pending_session_.empty() || (!pending_project_.empty() && pending_project_ != state.project()->id));
  }

  bool saved_dispatch_safe(ProjectState &state, const std::string &request_id,
                           DeferredAgentStartCheck agent_start) const
  {
    const auto &project = *state.project();
    const auto &discussion = state.discussion();
    if (agent_start != DeferredAgentStartCheck::Skip && state.agent().deferred_start_pending() &&
        discussion.generation_supported() &&
        !shows_saved_questions(discussion, project.handle, agent_start == DeferredAgentStartCheck::Focused) &&
        shows_or_opens_agent(state)) {
      return false;
    }
    if (!auto_ || auto_->key != project.directory + "\n" + project.id) { return true; }
    // A history link cannot resume an armed model start or an automatic fallback.
    if (auto_->prepare || (auto_->send && !auto_->sent)) { return false; }
    if (!auto_->send || auto_->request_id != request_id) { return true; }
    const auto &request = discussion.exchange_request();
    const auto status = io::get_string(request, "status");
    return io::get_string(request, "id") == request_id &&
           (status == "completed" || status == "cancelled" || status == "uncertain" ||
            (status == "failed" && io::get_string(request, "error_code") != "adapter_failed"));
  }

  bool reveal_saved(ProjectState &state, const std::string &request_id)
  {
    if (!state.discussion().load_exchange(request_id)) { return false; }
    saved_questions_handle_.clear();
    compose_handle_.clear();
    const auto &project = *state.project();
    auto &draft = project_draft(project, project.directory + "\n" + project.id);
    if (draft.intent == kAgentIntent) { draft.intent = 0; }
    opened_history_ = true;
    return true;
  }

  bool reveal_saved_question_history(const ProjectState &state)
  {
    if (!state.project()) { return false; }
    saved_questions_handle_ = state.project()->handle;
    compose_handle_.clear();
    return true;
  }

  bool reveal_question_composer(const ProjectState &state, const uint64_t visibility)
  {
    if (!state.project()) { return false; }
    const auto &project = *state.project();
    auto &draft = project_draft(project, project.directory + "\n" + project.id);
    if (draft.intent == kAgentIntent) { draft.intent = 0; }
    saved_questions_handle_.clear();
    compose_handle_ = project.handle;
    ++compose_generation_;
    compose_focus_visibility_ = visibility;
    return true;
  }

  bool reveal_saved_agent(ProjectState &state, const std::string &session_id)
  {
    auto &agent = state.agent();
    if (!agent.select_history_session(session_id)) { return false; }
    saved_questions_handle_.clear();
    compose_handle_.clear();
    const auto &project = *state.project();
    project_draft(project, project.directory + "\n" + project.id).intent = kAgentIntent;
    return true;
  }

  /** {"session_id"}: show that agent session (for example from a Home attention item). */
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &) override
  {
    const auto session = io::get_string(target, "session_id");
    if (session.empty()) { return false; }
    saved_questions_handle_.clear();
    compose_handle_.clear();
    pending_session_ = session;  // taken by the next draw (navigation redraws the area)
    pending_project_ = io::get_string(target, "project_id");
    return true;
  }

 private:
  static bool selected_agent_loaded(const ProjectAgent &agent)
  {
    const auto &view = agent.view();
    const auto session = view.find("session");
    return !agent.selected().empty() && session != view.end() &&
           io::get_string(*session, "id") == agent.selected();
  }

  static void poll_agent(EditorContext &ctx, ProjectAgent &agent)
  {
    const double now = clock_seconds(), wake = agent.pump(now);
    auto *wm = ctx.area.shell().window_manager();
    if (!wm || !std::isfinite(wake) || (agent.wake_scheduled > now && agent.wake_scheduled <= wake + 1e-4)) { return; }
    agent.wake_scheduled = wake;
    const auto delay = uint64_t(std::clamp((wake - now) * 1000.0 + 1.0, 1.0, 60000.0));
    wm->add_timer(delay, 0, [store = &ctx.store] { store->changed(); });
  }

  /** One line per step of the session, in words: what the person said, which tool ran at which level and how it
   * ended, the agent's answers, decisions on its cards and why it stopped. */
  static std::string agent_steps(const Json &view, EditorContext &ctx)
  {
    const auto &catalog = ctx.store.catalog();
    std::string text;
    const auto line = [&text](const std::string &value) { text += value + "\n"; };
    for (const auto &event : view.value("events", Json::array())) {
      const auto kind = io::get_string(event, "kind");
      if (kind == "user_turn") {
        line("");
        line(std::string(ctx.tr("ai.you")) + "\n" + io::get_string(event, "text"));
      }
      else if (kind == "model_completed" && !io::get_string(event, "text").empty()) {
        line(std::string(ctx.tr("ai.agent.says")) + "\n" + io::get_string(event, "text"));
      }
      else if (kind == "tool_called") {
        const auto tool = io::get_string(event, "tool");
        line(catalog.format("ai.agent.step", {{"level", std::string(catalog.tr_or("ai.agent.level." + io::get_string(event, "level"), "?"))},
                                              {"tool", std::string(catalog.tr_or("ai.agent.tool." + tool, tool))}}));
      }
      else if (kind == "tool_result") {
        const auto status = io::get_string(event, "status");
        std::string detail;
        if (status == "error") {
          try { detail = io::get_string(Json::parse(io::get_string(event, "content")).value("data", Json::object()), "error"); }
          catch (const std::exception &) {}
        }
        line("  " + catalog.format("ai.agent.result." + (status == "ok" || status == "error" ? status : std::string("unknown")),
                                   {{"error", detail}}));
      }
      else if (kind == "model_settled") {
        line(catalog.format("ai.agent.settled", {{"status", std::string(ctx.tr("discussion.requests." + io::get_string(event, "status")))},
                                                 {"code", io::get_string(event, "code")}}));
      }
      else if (kind == "approval_decided") {
        const auto by = event.value("by", Json::object());
        line(catalog.format("ai.agent.decided." + io::get_string(event, "decision"),
                            {{"user", io::get_string(by, "user")}, {"host", io::get_string(by, "host")}}));
      }
      else if (kind == "approval_receipt") {
        const auto outcome = io::get_string(event, "outcome");
        if (!outcome.empty()) { line(std::string(catalog.tr_or("ai.agent.run.outcome." + outcome, outcome))); }
        else { line(!event.value("ok", false) ? catalog.format("ai.agent.receipt_failed", {{"error", io::get_string(event, "error")}}) :
             event.contains("applied_revision") ? catalog.format("ai.agent.receipt_ok", {{"revision", std::to_string(io::get_int(event, "applied_revision", -1))}})
                                                : std::string(ctx.tr("ai.agent.receipt_done"))); }
      }
      else if (kind == "policy" && event.contains("fallback")) {
        line(catalog.format("ai.agent.fallback", {{"model", io::get_string(event.at("fallback"), "model")}}));
      }
      else if (kind == "cancel_requested") { line(std::string(ctx.tr("ai.agent.cancel_requested"))); }
      else if (kind == "stopped") {
        const auto reason = io::get_string(event, "reason");
        line(std::string(catalog.tr_or("ai.agent.stopped." + reason, reason)));
      }
    }
    return text;
  }

  void agent_sessions(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool enabled)
  {
    auto &agent = state.agent();
    const auto &catalog = ctx.store.catalog();
    // Sessions, newest first; the first entry starts a new one.
    std::vector<std::string> ids = {""}, titles = {std::string(ctx.tr("ai.agent.new_session"))};
    for (const auto &session : agent.sessions()) {
      ids.push_back(io::get_string(session, "id"));
      titles.push_back(agent_session_label(session) + " · " +
          std::string(catalog.tr_or("ai.agent.state." + io::get_string(session, "state"), io::get_string(session, "state"))));
    }
    if (!agent.selected().empty() && std::find(ids.begin(), ids.end(), agent.selected()) == ids.end()) {
      ids.push_back(agent.selected()); titles.push_back(agent.selected().substr(0, 8));
    }
    auto &sessions = layout.row();
    sessions.dropdown("ai_agent_session", std::move(titles), {
      [ids, &agent] { const auto at = std::find(ids.begin(), ids.end(), agent.selected()); return at == ids.end() ? 0 : int(at - ids.begin()); },
      [ids, &agent, &state, handle = state.project()->handle](const int index) {
        if (state.project() && state.project()->handle == handle && index >= 0 && size_t(index) < ids.size()) { agent.select(ids[size_t(index)]); }
      }}).disable(!enabled);
    sessions.button("ai_agent_refresh", ctx.tr("ai.refresh_history"), [&agent] { agent.load_list(); agent.draft_changed(""); }).width(6);
  }

  void agent_view(ui::Layout &layout, EditorContext &ctx, ProjectState &state, Draft &draft, const bool focused)
  {
    auto &agent = state.agent();
    const auto &catalog = ctx.store.catalog();
    const std::string handle = state.project()->handle;
    if (agent_opening_ != handle) {
      agent_opening_ = handle; shown_agent_.clear(); agent_timeline_.clear(); agent_navigation_error_.clear();
      agent_transcript_positions_.clear();
      timeline_session_.clear();
      draft.allow_prepare = false;  // reopening a project restores its text, never permission to prepare
    }
    poll_agent(ctx, agent);
    if (timeline_session_ != agent.selected()) {
      if (auto *position = transcript_position(agent_transcript_positions_, timeline_session_)) {
        position->follow = false;
      }
      timeline_session_ = agent.selected();
    }
    const bool enabled = !state.busy() && !agent.busy();
    const auto &view = agent.view();
    const bool session_loaded = selected_agent_loaded(agent);
    if (focused && session_loaded) {
      const auto selected = std::find_if(agent.sessions().begin(), agent.sessions().end(), [&agent](const Json &item) {
        return io::get_string(item, "id") == agent.selected();
      });
      const auto title = agent_session_label(selected != agent.sessions().end() ? *selected : view.at("session"));
      layout.label(title).tip(title);
    }
    intent_dropdown(layout, ctx, state, draft);
    const auto intro = agent.runs_supported() ? "ai.agent.intro_runs" : "ai.agent.intro";
    if (!focused) { hint(layout, ctx, intro); }
    if (!agent.error().empty()) { layout.paragraph(agent.error()); }
    if (!agent_navigation_error_.empty()) { layout.paragraph(agent_navigation_error_); }
    // The planner: a model on this computer or the organization's network (v1), chosen by the service.
    const auto &route = agent.route();
    const auto choice = route.value("choice", Json());
    const auto planner = !agent.route_loaded() ? std::string(ctx.tr("models.auto.reading")) : choice.is_object() ?
        catalog.format("ai.agent.planner", {{"name", io::get_string(choice, "name")}, {"model", io::get_string(choice, "model")},
            {"location", std::string(ctx.tr("models.location." + io::get_string(choice, "location")))}}) :
        std::string(ctx.tr("ai.agent.no_planner"));
    if (focused) {
      if (auto *sessions = layout.panel("ai_agent_sessions", ctx.tr("workbench.history.agent_sessions"), false)) {
        agent_sessions(*sessions, ctx, state, enabled);
        hint(*sessions, ctx, intro);
        if (choice.is_object()) { sessions->paragraph(planner); }
      }
    }
    else {
      layout.paragraph(planner);
      agent_sessions(layout, ctx, state, enabled);
    }
    const auto state_name = io::get_string(view, "state");
    const bool running = agent.running();
    if (session_loaded) {
      layout.paragraph(running ? std::string(ctx.tr("ai.agent.running")) :
          std::string(catalog.tr_or("ai.agent.state." + state_name, state_name)));
      const auto &style = layout.ctx().style();
      const float unit = style.unit;
      const float width = focused ? std::min(layout.block().rect().w, kConversationWidth * style.scale) :
          layout.block().rect().w;
      const float wrap_width = std::max(unit, width - 4 * unit);
      // As for the question transcript: the regular UI font when focused, monospace in the split view.
      const bool timeline_mono = !focused;
      const auto shown = io::get_string(view, "chain_sha256") + std::to_string(wrap_width) + (timeline_mono ? "/mono" : "/regular");
      if (shown_agent_ != shown) {
        shown_agent_ = shown;
        agent_timeline_ = wrapped_text(agent_steps(view, ctx), wrap_width, ctx, timeline_mono);
      }
      const float height = ctx.draw ? float(ctx.draw->rect.height()) : 800.0f;
      layout.log_view("ai_agent_timeline", agent_timeline_, std::clamp(height / unit - 24.0f, 6.0f, 22.0f),
                      transcript_position(agent_transcript_positions_, agent.selected())).mono = timeline_mono;
      agent_cards(layout, ctx, state, view);
      agent_run_cards(layout, ctx, state);
      const auto show_usage = [&](ui::Layout &where) {
        const auto usage = view.value("usage", Json::object());
        if (usage.empty()) { return; }
        const auto planner = usage.value("planner", Json::object()), requests = usage.value("requests", Json::object());
        where.paragraph(catalog.format("ai.agent.usage", {{"turns", std::to_string(io::get_int(planner, "turns", 0))},
            {"planner", std::to_string(io::get_int(planner, "input_tokens", 0) + io::get_int(planner, "output_tokens", 0))},
            {"requests", std::to_string(io::get_int(requests, "requests", 0))},
            {"request_tokens", std::to_string(io::get_int(requests, "input_tokens", 0) + io::get_int(requests, "output_tokens", 0))}}));
      };
      if (!focused) { show_usage(layout); }
      auto &actions = layout.row();
      actions.button("ai_agent_cancel", ctx.tr("discussion.requests.cancel"), [&agent] { agent.cancel(); })
          .disable(!enabled || !running);
      actions.button("ai_agent_continue", ctx.tr("ai.agent.continue"), [&agent] { agent.start(); })
          .disable(!enabled || running || state_name != "ready" || agent.target_pending()).tip(ctx.tr("ai.agent.continue.tip"));
      if (auto *record = layout.panel("ai_agent_record", ctx.tr("ai.agent.record"), false)) {
        if (focused) { show_usage(*record); }
        record->paragraph(catalog.format("ai.agent.chain", {{"events", std::to_string(io::get_int(view, "total", 0))},
            {"digest", io::get_string(view, "chain_sha256").substr(0, 16)}}));
        auto &checks = record->row();
        checks.button("ai_agent_verify", ctx.tr("ai.agent.verify"), [&agent] { agent.verify(); }).disable(!enabled);
        checks.button("ai_agent_recover", ctx.tr("discussion.requests.recover"), [&agent] { agent.recover(); })
            .disable(!enabled || running).tip(ctx.tr("ai.agent.recover.tip"));
        const auto &check = agent.verification();
        if (!check.empty()) {
          record->paragraph(check.value("ok", false) ? std::string(ctx.tr("ai.agent.verified")) :
              catalog.format("ai.agent.verify_failed", {{"count", std::to_string(check.value("problems", Json::array()).size())}}));
          for (const auto &problem : check.value("problems", Json::array())) { record->paragraph(problem.get<std::string>()); }
        }
      }
      if (state_name == "ended") { layout.paragraph(ctx.tr("ai.agent.ended")); }
    }
    else if (!agent.selected().empty()) { layout.paragraph(ctx.tr("ai.loading")); }
    layout.separator();
    Json simulation = nullptr;
    bool target_valid = true;
    std::string connection;
    std::optional<Json> options;
    if (agent.runs_supported()) {
      layout.checkbox("ai_agent_allow_prepare", ctx.tr("ai.agent.run.allow_prepare"), ui::bind(draft.allow_prepare))
          .disable(!enabled || running).tip(ctx.tr("ai.agent.run.allow_prepare.tip"));
      if (draft.allow_prepare) {
        auto &target = layout.box();
        hint(target, ctx, "ai.agent.run.target_hint");
        connection = draft.run_target.runtime_controls(target, ctx);
        options = draft.run_target.options_controls(target, ctx, "muferro/1");
        target_valid = draft.run_target.matches(ctx.store.jobs(), connection, options);
        if (target_valid) { simulation = {{"connection", connection}, {"options", *options}}; }
      }
      else { hint(layout, ctx, "ai.agent.run.disabled"); }
      const auto configured = agent.view().value("run_target", Json());
      if (configured.is_object()) {
        layout.paragraph(catalog.format("ai.agent.run.configured", {
            {"runtime", SimulationTarget::runtime_name(ctx, io::get_string(configured, "connection"))}}));
      }
      if (agent.target_pending()) { hint(layout, ctx, "ai.agent.run.target_pending"); }
      if (!agent.selected().empty()) {
        const auto session = agent.selected();
        layout.button("ai_agent_set_target", ctx.tr(draft.allow_prepare ? "ai.agent.run.set_target" : "ai.agent.run.clear_target"),
            [&agent, &state, &draft, store = &ctx.store, handle, session, simulation, connection, options] {
          if (!state.project() || state.project()->handle != handle || agent.selected() != session ||
              !selected_agent_loaded(agent)) { return; }
          if (!simulation.is_null() && (!draft.allow_prepare || !draft.run_target.matches(store->jobs(), connection, options))) { return; }
          agent.set_run_target(simulation);
        }).disable(!enabled || !session_loaded || running || !target_valid);
      }
    }
    // A message the service saved is no longer a draft (the same words typed again stay in the box).
    if (const auto sent = agent.take_sent(); !sent.empty()) {
      if (sent == draft.agent_text) { draft.agent_text.clear(); }
      ctx.store.changed();  // The history rail was built before this receipt was shown.
    }
    const bool new_session = agent.selected().empty();
    const auto session = agent.selected();
    const bool with_target = agent.runs_supported();
    const bool can_send = enabled && !running && state_name != "ready" && state_name != "ended" && target_valid &&
        (new_session ? choice.is_object() : session_loaded);
    const auto send = [this, weak = lifetime(), &agent, &state, store = &ctx.store, handle, session, &draft, with_target,
                       simulation, connection, options, can_send, selection = agent.selection_epoch()] {
      if (weak.expired() || !can_send || !state.project() || state.project()->handle != handle || state.busy() ||
          agent.busy() || agent.running() || agent.selection_epoch() != selection || agent.selected() != session ||
          draft.intent != kAgentIntent || draft.agent_text.empty() ||
          (!session.empty() && (!selected_agent_loaded(agent) || io::get_string(agent.view(), "state") == "ready"))) { return; }
      if (with_target && (draft.allow_prepare != !simulation.is_null() ||
          (!simulation.is_null() && !draft.run_target.matches(store->jobs(), connection, options)))) { return; }
      const bool sent = with_target ? agent.ask(draft.agent_text, simulation) : agent.ask(draft.agent_text);
      if (sent && !session.empty()) {
        transcript_position(agent_transcript_positions_, session)->follow = true;
      }
    };
    // Focused: the field, why sending is unavailable and the right-aligned action share one card (as the question).
    auto &composer = focused ? layout.box() : layout;
    auto &input = composer.text_area("ai_agent_text/" + handle, ui::bind(draft.agent_text),
                                     {.max_length = 8192, .visible_lines = 3, .on_submit = send,
                                      .submit_when_focused = true, .preserve_on_escape = true});
    if (focused && !choice.is_object()) { composer.paragraph(planner); }
    const bool has_text = ctx.ui && ctx.ui->editing() == input.id && ctx.ui->edit_state() ?
        !ctx.ui->edit_state()->text().empty() : !draft.agent_text.empty();
    auto &actions = focused ? composer.row().alignment(ui::LayoutAlign::Right) : layout;
    actions.button("ai_agent_send", ctx.tr(new_session ? "ai.agent.start" : "ai.agent.say"), send)
        .disable(!can_send || !has_text).tip(ctx.tr("ai.agent.send.shortcut"));
  }

  void agent_run_cards(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    auto &agent = state.agent();
    if (!agent.runs_supported()) { return; }
    const auto handle = state.project()->handle, session = agent.selected();
    const auto &catalog = ctx.store.catalog();
    const bool enabled = !state.busy() && !agent.busy();
    // Buffers are transient and tied to the displayed opening/session and exact complete result.
    const auto origin = handle + "\n" + session;
    if (run_plan_origin_ != origin) {
      run_plan_origin_ = origin; run_plan_text_.clear(); run_plan_logs_.clear(); run_plan_readable_.clear();
    }
    // A linked-task detail belongs to this editor, opening, session selection and card (switching away and back
    // to the same session ID is another selection); hiding and showing the page again also closes it.
    const auto selection = agent.selection_epoch();
    const auto *screen = ctx.area.screen();
    const auto detail_origin = origin + "\n" + std::to_string(selection) + "\n" +
        std::to_string(reinterpret_cast<uintptr_t>(screen)) + "\n" +
        std::to_string(screen ? screen->visibility_epoch() : 0) + "\n" + std::to_string(ctx.area.activity_epoch()) +
        "\n" + std::to_string(run_detail_owner_epoch_);
    for (const auto &entry : agent.run_cards()) {
      const auto item = entry.at("item");
      const auto id = io::get_string(item, "item_id"), sha = io::get_string(item, "plan_sha256");
      auto &card = layout.box();
      card.paragraph(catalog.format("ai.agent.run.card", {{"run", io::get_string(item, "run_id")}}));
      card.paragraph(catalog.format("ai.agent.run.digest", {{"digest", sha},
          {"revision", std::to_string(io::get_int(item, "expected_revision", -1))}}));
      const auto bound = [&state, &agent, handle, session] {
        return state.project() && state.project()->handle == handle && agent.selected() == session;
      };
      card.button("ai_agent_run_read/" + id, ctx.tr("ai.agent.run.read_plan"), [&agent, bound, item] {
        if (bound()) { agent.read_run_plan(item); }
      }).disable(!enabled);
      bool displayed = false;
      if (const auto *plan = agent.run_plan(item); plan && ctx.ui) {
        const auto key = id + "\n" + sha;
        const std::string text = plan->dump(2);  // complete JSON, including resources, inputs and every task
        // Reserve root/card padding, text margins and the vertical scrollbar; rewrap after resize or font changes.
        const auto &style = ctx.ui->style();
        const float width = layout.block().rect().w - 8 * style.unit - 2 * style.text_margin - style.scrollbar;
        const auto signature = std::to_string(width) + "/" + std::to_string(style.mono.size_px) + "\n" + text;
        if (run_plan_text_[key] != signature) {
          run_plan_text_[key] = signature;
          auto buffer = frozen_plan_text(text, width, ctx);
          run_plan_readable_[key] = buffer.has_value();
          if (buffer) { run_plan_logs_[key] = std::move(*buffer); }
        }
        if (run_plan_readable_[key]) {
          card.paragraph(ctx.tr("ai.agent.run.full_plan"));
          card.log_view("ai_agent_run_plan/" + id, run_plan_logs_.at(key), 14);
          displayed = true;
        }
        else { hint(card, ctx, "ai.agent.run.read_first"); }
      }
      else { hint(card, ctx, "ai.agent.run.read_first"); }
      const auto receipt = entry.value("receipt", Json());
      const bool consumed = entry.value("decision", Json()).is_object() || receipt.is_object();
      if (consumed) {
        const auto outcome = io::get_string(receipt, "outcome", "pending");
        card.paragraph(std::string(catalog.tr_or("ai.agent.run.outcome." + outcome, outcome)));
        const auto status = io::get_string(receipt, "run_status");
        if (!status.empty()) {
          card.paragraph(catalog.format("ai.agent.run.status", {
              {"status", std::string(catalog.tr_or("workflow.run.status." + status, status))}}));
        }
        hint(card, ctx, "ai.agent.run.observe_only");
        card.button("ai_agent_run_observe/" + id, ctx.tr("ai.agent.run.observe"), [&agent, bound, item] {
          if (bound()) { agent.observe_run(item); }
        }).disable(!enabled);
        if (agent.can_read_run_detail(item)) {
          // The detail can be read during another agent call. Project transitions disable the entry.
          auto &entry_button = card.button("ai_agent_run_detail/" + id, ctx.tr("ai.agent.run.detail"), {});
          entry_button.on_click = [this, weak = lifetime(), &agent, bound, item, detail_origin, selection, ui = ctx.ui,
                                   area = &ctx.area, screen, activity = ctx.area.activity_epoch(),
                                   visibility = screen ? screen->visibility_epoch() : 0, store = &ctx.store,
                                   project_scope = ctx.store.project_scope_epoch(), entry = entry_button.key,
                                   owner = run_detail_owner_epoch_] {
            if (weak.expired() || owner != run_detail_owner_epoch_ || !bound() || run_detail_.ticket ||
                agent.selection_epoch() != selection ||
                area->screen() != screen || area->activity_epoch() != activity ||
                (screen && screen->visibility_epoch() != visibility) || store->project_scope_epoch() != project_scope) {
              return;
            }
            if (const auto ticket = agent.read_run_detail(item)) { run_detail_ = {ticket, detail_origin, item, entry, ui}; }
          };
          entry_button.disable(state.busy()).tip(ctx.tr("ai.agent.run.detail.tip"));
        }
      }
      else {
        if (io::get_int(item, "expected_revision", -1) != state.project()->revision) { hint(card, ctx, "ai.agent.run.stale"); }
        auto &actions = card.row();
        actions.button("ai_agent_run_start/" + id, ctx.tr("ai.agent.run.approve"), [&agent, bound, item] {
          if (bound()) { agent.decide_run(item, "start"); }
        }).disable(!displayed || !agent.can_decide_run(item, "start"));
        actions.button("ai_agent_run_decline/" + id, ctx.tr("ai.agent.run.decline"), [&agent, bound, item] {
          if (bound()) { agent.decide_run(item, "decline"); }
        }).disable(!agent.can_decide_run(item, "decline"));
      }
    }
    run_detail_panel(ctx, state, detail_origin);
  }

  /** The open linked-task detail as a positioned modal, like the Web 「关联任务」 dialog: a right-side panel of
   * 420 px on wide windows, a full-width bottom sheet at or below 700 px. Esc or Close return to the card's entry. */
  void run_detail_panel(EditorContext &ctx, ProjectState &state, const std::string &origin)
  {
    if (!run_detail_.ticket || !ctx.ui || run_detail_.ui != ctx.ui || run_detail_.origin != origin) { return; }
    auto &agent = state.agent();
    const auto *detail = agent.run_detail(run_detail_.ticket, run_detail_.item);
    if (!detail) { return; }  // closed by the frame guard in draw_main
    run_detail_drawn_ = true;
    const auto &catalog = ctx.store.catalog();
    const auto &style = ctx.ui->style();
    const auto window = ctx.ui->window_size();
    const bool narrow = window.x <= 700.0f * ctx.ui->scale();
    ui::ModalOptions options;
    options.has_pos = true;  // the modal clamps its frame into the window: x = right edge, y = bottom edge
    options.height = window.y * (narrow ? 0.8f : 1.0f);
    if (narrow) { options.width_units = window.x / style.unit; options.pos = {0, window.y}; }
    else { options.width_units = std::min(21.0f, window.x / style.unit); options.pos = {window.x, 0}; }
    const auto close = [this, weak = lifetime(), &state, ticket = run_detail_.ticket, owner = run_detail_owner_epoch_] {
      if (!weak.expired() && owner == run_detail_owner_epoch_ && run_detail_.ticket == ticket) {
        close_run_detail(state, true);
      }
    };
    const auto ticket = run_detail_.ticket;
    const auto *files = agent.run_files(ticket, run_detail_.item);
    const auto *preview = files ? agent.run_file_preview(ticket, run_detail_.item) : nullptr;
    // One panel: the tasks, then a task's frozen snapshot files, then one file's text (the Web dialog's pages).
    auto &panel = ctx.ui->modal("ai_agent_run_detail_panel",
        ctx.tr(preview ? "ai.agent.run.preview" : files ? "ai.agent.run.files" : "ai.agent.run.detail"), close, options);
    const char *page = preview ? "preview" : files ? "files" : "tasks";
    const int64_t file_entry = files ? io::get_int(*files, "entry", -1) : -1;
    const int64_t preview_entry = preview ? io::get_int(*preview, "file", -1) : -1;
    if (run_detail_focus_ticket_ != ticket) {
      for (const auto *scope : {"tasks", "files", "preview"}) { panel.block().set_scroll_scope(scope, true); }
      run_detail_files_scroll_entry_ = -1;
      run_detail_preview_scroll_entry_ = -1;
    }
    const bool reset_scroll = preview ? preview_entry != run_detail_preview_scroll_entry_ :
        files && file_entry != run_detail_files_scroll_entry_;
    panel.block().set_scroll_scope(page, reset_scroll);
    if (files) { run_detail_files_scroll_entry_ = file_entry; }
    run_detail_preview_scroll_entry_ = preview_entry;
    const auto &close_button = panel.row().alignment(ui::LayoutAlign::Right)
        .button("ai_agent_run_detail_close", ctx.tr("ui.close"), close).width(5);
    if (run_detail_focus_ticket_ != run_detail_.ticket) {
      run_detail_focus_ticket_ = run_detail_.ticket;
      ctx.ui->focus_modal_next_frame(close_button.key);
    }
    const float width = options.width_units * style.unit - 2 * style.panel_margin - 2 * style.text_margin -
        style.scrollbar - 2 * style.pixel;
    const float rows = std::clamp(options.height / style.unit - 10.0f, 4.0f, 30.0f);
    if (preview) { run_file_preview_page(panel, ctx, state, *files, *preview, width, rows); return; }
    if (files) { run_files_page(panel, ctx, state, *detail, *files); return; }
    panel.paragraph(catalog.format("ai.agent.run.card", {{"run", io::get_string(run_detail_.item, "run_id")}}));
    const auto state_name = io::get_string(*detail, "state");
    if (state_name == "reading") { panel.paragraph(ctx.tr("ai.agent.run.detail.reading")); return; }
    if (state_name == "mismatch") { panel.paragraph(ctx.tr("ai.agent.run.detail.mismatch")); return; }
    if (state_name != "ready") {
      panel.paragraph(ctx.tr("ai.agent.run.detail.unavailable"));
      panel.button("ai_agent_run_detail_retry", ctx.tr("ai.agent.run.read_retry"),
                   [this, weak = lifetime(), &agent, ticket, owner = run_detail_owner_epoch_] {
        if (weak.expired() || owner != run_detail_owner_epoch_ || run_detail_.ticket != ticket) { return; }
        const auto *current = agent.run_detail(ticket, run_detail_.item);
        if (!current || io::get_string(*current, "state") != "unavailable") { return; }
        if (const auto next = agent.read_run_detail(run_detail_.item)) {
          agent.close_run_detail(ticket);
          run_detail_.ticket = next;
        }
      }).disable(state.busy());
      return;
    }
    const auto status = io::get_string(*detail, "status");
    std::string counts;
    const auto count_map = detail->value("counts", Json::object());
    for (const auto &[name, count] : count_map.items()) {
      counts += (counts.empty() ? "" : " · ") + std::string(catalog.tr_or("workflow.run.task." + name, name)) + " " +
          std::to_string(count.get<int64_t>());
    }
    panel.paragraph(catalog.format("ai.agent.run.detail.status", {
        {"status", std::string(io::get_bool(*detail, "complete", false) ? ctx.tr("workflow.run.complete") :
                                   catalog.tr_or("workflow.run.status." + status, status))},
        {"counts", counts}}));
    if (io::get_bool(*detail, "stop_error", false)) { panel.paragraph(ctx.tr("ai.agent.run.detail.stop_error")); }
    // A ticket's projection is set once (reading, then its result): rewrap only for another ticket, width, font or
    // language.
    const auto signature = std::to_string(run_detail_.ticket) + "/" + state_name + "/" + std::to_string(width) + "/" +
        std::to_string(style.mono.size_px) + "/" + std::string(ctx.tr("ai.agent.run.detail.task"));
    if (run_detail_text_ != signature) {
      run_detail_text_ = signature;
      run_detail_log_ = wrapped_text(run_detail_lines(*detail, ctx), width, ctx, true);
    }
    // Tasks whose produced frozen snapshot can list files, each with its own entry below the list.
    std::vector<std::pair<size_t, const Json *>> entries;
    if (agent.can_read_run_files(ticket, run_detail_.item) && detail->contains("tasks")) {
      for (const auto &task : detail->at("tasks")) {  // by reference: the pointers are used below
        if (!task.is_object() || !task.contains("produced")) { continue; }
        const auto &produced = task.at("produced");
        if (produced.is_object() && produced.contains("files_entry")) {
          entries.emplace_back(produced.at("files_entry").get<size_t>(), &task);
        }
      }
    }
    // The context keeps this list's scroll while a snapshot's files are shown, so Back returns to the same place.
    panel.log_view("ai_agent_run_detail_tasks", run_detail_log_,
                   std::min(std::max(4.0f, rows - float(entries.size())),
                            float(std::max<size_t>(run_detail_log_.line_count(), 1)) + 0.5f));
    for (const auto &[entry, task] : entries) {
      const auto row = io::get_int(*task, "row", -1);
      // The files page's Back has this key too, so keyboard focus returns to this exact entry.
      panel.button("ai_agent_run_detail_files/" + std::to_string(entry),
          catalog.format("ai.agent.run.files.open", {{"row", row < 0 ? std::string("?") : std::to_string(row)},
                                                       {"step", io::get_string(*task, "step")}}),
          [this, weak = lifetime(), &agent, ticket, item = run_detail_.item, entry, owner = run_detail_owner_epoch_,
           page = run_detail_page_epoch_] {
        if (weak.expired() || owner != run_detail_owner_epoch_ || run_detail_.ticket != ticket ||
            page != run_detail_page_epoch_) { return; }
        if (agent.read_run_files(ticket, item, entry)) { ++run_detail_page_epoch_; }
      }).disable(state.busy()).tip(ctx.tr("ai.agent.run.files.open.tip"));
    }
  }

  /** A task's frozen snapshot files: each output record with its manifest size, and Preview for small text. */
  void run_files_page(ui::Layout &panel, EditorContext &ctx, ProjectState &state, const Json &detail, const Json &files)
  {
    auto &agent = state.agent();
    const auto &catalog = ctx.store.catalog();
    const auto ticket = run_detail_.ticket;
    const auto entry = io::get_int(files, "entry", 0);
    const auto guard = [this, weak = lifetime(), ticket, owner = run_detail_owner_epoch_, page = run_detail_page_epoch_] {
      return !weak.expired() && owner == run_detail_owner_epoch_ && run_detail_.ticket == ticket &&
          page == run_detail_page_epoch_;
    };
    const auto &back = panel.button("ai_agent_run_detail_files/" + std::to_string(entry), ctx.tr("ai.agent.run.files.back"),
                 [this, guard, &agent, ticket] {
      if (!guard()) { return; }
      ++run_detail_page_epoch_;
      agent.close_run_files(ticket);
    });
    static const Json none = Json::array();
    for (const auto &task : detail.contains("tasks") ? detail.at("tasks") : none) {  // no copy
      if (!task.is_object() || !task.contains("produced")) { continue; }
      const auto &produced = task.at("produced");
      if (!produced.is_object() || produced.value("files_entry", Json()) != Json(entry)) { continue; }
      const auto row = io::get_int(task, "row", -1);
      panel.paragraph(catalog.format("ai.agent.run.files.source", {{"id", io::get_string(produced, "snapshot_id")},
          {"row", row < 0 ? std::string("?") : std::to_string(row)}, {"step", io::get_string(task, "step")}}));
      break;
    }
    const auto state_name = io::get_string(files, "state");
    if (state_name == "reading") { panel.paragraph(ctx.tr("ai.agent.run.files.reading")); return; }
    if (state_name == "mismatch") { panel.paragraph(ctx.tr("ai.agent.run.files.mismatch")); return; }
    if (state_name != "ready") {
      panel.paragraph(ctx.tr("ai.agent.run.files.unavailable"));
      panel.button("ai_agent_run_files_retry", ctx.tr("ai.agent.run.read_retry"),
                   [this, guard, &agent, ticket, item = run_detail_.item, entry, ui = ctx.ui, key = back.key] {
        if (!guard()) { return; }
        if (agent.read_run_files(ticket, item, size_t(entry))) {
          ++run_detail_page_epoch_;
          ui->focus_modal_next_frame(key);
        }
      }).disable(state.busy());
      return;
    }
    const auto listed = files.value("files", Json::array());
    for (size_t i = 0; i < listed.size(); ++i) {
      const auto &file = listed.at(i);
      const auto output = io::get_string(file, "output"), name = io::get_string(file, "name");
      const auto label = core::utf8::truncate_display(output == name ? name : output + " · " + name, 40) + " · " +
          catalog.format("ai.agent.run.files.size", {{"size", std::to_string(io::get_int(file, "size", 0))}});
      auto &line = panel.row();
      line.label(label).tip(output == name ? name : output + " · " + name);
      const auto kind = io::get_string(file, "preview");
      if (kind == "text") {
        // The preview's Back has this key too, so keyboard focus returns to this exact file.
        line.button("ai_agent_run_detail_preview/" + std::to_string(i), ctx.tr("ai.agent.run.preview.open"),
                    [this, guard, &agent, ticket, item = run_detail_.item, i] {
          if (!guard()) { return; }
          if (agent.read_run_file_preview(ticket, item, i)) {
            ++run_detail_page_epoch_;
            run_preview_position_ = {0.0f, false};
          }
        }).width(5).disable(state.busy()).tip(ctx.tr("ai.agent.run.preview.open.tip"));
      }
      else { line.label(ctx.tr(kind == "large" ? "ai.agent.run.preview.large" : "ai.agent.run.preview.format")); }
    }
    if (const auto more = io::get_int(files, "more", 0); more > 0) {
      panel.paragraph(catalog.format("ai.agent.run.files.more", {{"count", std::to_string(more)}}));
    }
  }

  /** One frozen text file, shown literally in a log view that starts at its first line. */
  void run_file_preview_page(ui::Layout &panel, EditorContext &ctx, ProjectState &state, const Json &files,
                             const Json &preview, const float width, const float rows)
  {
    auto &agent = state.agent();
    const auto ticket = run_detail_.ticket;
    const auto file = io::get_int(preview, "file", 0);
    panel.button("ai_agent_run_detail_preview/" + std::to_string(file), ctx.tr("ai.agent.run.preview.back"),
                 [this, weak = lifetime(), &agent, ticket, owner = run_detail_owner_epoch_,
                  page = run_detail_page_epoch_] {
      if (weak.expired() || owner != run_detail_owner_epoch_ || run_detail_.ticket != ticket ||
          page != run_detail_page_epoch_) { return; }
      ++run_detail_page_epoch_;
      agent.close_run_file_preview(ticket);
      run_preview_text_.clear();
      run_preview_log_.clear();
    });
    panel.paragraph(io::get_string(preview, "name"));
    const auto state_name = io::get_string(preview, "state");
    if (state_name == "reading") { panel.paragraph(ctx.tr("ai.agent.run.preview.reading")); return; }
    if (state_name == "mismatch") { panel.paragraph(ctx.tr("ai.agent.run.preview.mismatch")); return; }
    if (state_name == "not_text") { panel.paragraph(ctx.tr("ai.agent.run.preview.not_text")); return; }
    if (state_name != "ready") { panel.paragraph(ctx.tr("ai.agent.run.preview.unavailable")); return; }
    if (!preview.contains("text") || !preview.at("text").is_string()) { return; }
    const auto &text = preview.at("text").get_ref<const std::string &>();  // up to 256 KiB: not copied per frame
    if (text.empty()) { panel.paragraph(ctx.tr("ai.agent.run.preview.empty")); return; }
    const auto &style = ctx.ui->style();
    // A ready preview of one ticket's entry and file is always the same verified bytes: rewrap only for another
    // file, width or font.
    const auto signature = std::to_string(ticket) + "/" + std::to_string(io::get_int(files, "entry", 0)) + "/" +
        std::to_string(file) + "/" + std::to_string(width) + "/" + std::to_string(style.mono.size_px);
    if (run_preview_text_ != signature) {
      run_preview_text_ = signature;
      // Every character is kept (spaces included) and wrapped on code point boundaries.
      auto buffer = frozen_plan_text(text, width, ctx);
      run_preview_log_ = buffer ? std::move(*buffer) : wrapped_text(text, width, ctx, true);
    }
    panel.log_view("ai_agent_run_detail_preview_text", run_preview_log_,
                   std::min(rows, float(std::max<size_t>(run_preview_log_.line_count(), 1)) + 0.5f),
                   &run_preview_position_, false);
  }

  static std::string run_detail_lines(const Json &detail, EditorContext &ctx)
  {
    const auto &catalog = ctx.store.catalog();
    std::string text;
    for (const auto &task : detail.value("tasks", Json::array())) {
      const auto status = io::get_string(task, "status"), task_id = io::get_string(task, "task_id");
      const auto row = io::get_int(task, "row", -1);
      text += catalog.format("ai.agent.run.detail.task", {{"row", row < 0 ? std::string("?") : std::to_string(row)},
          {"step", io::get_string(task, "step")}, {"attempt", std::to_string(io::get_int(task, "attempt", 0))},
          {"status", std::string(catalog.tr_or("workflow.run.task." + status, status))}});
      if (!task_id.empty()) { text += " · " + catalog.format("ai.agent.run.detail.task_id", {{"id", task_id}}); }
      text += "\n";
      const auto produced = task.value("produced", Json());
      if (!produced.is_object()) { continue; }
      if (const auto snapshot = io::get_string(produced, "snapshot_id"); !snapshot.empty()) {
        text += "  " + (produced.contains("file_count") ?
            catalog.format("ai.agent.run.detail.snapshot", {{"id", snapshot},
                           {"count", std::to_string(io::get_int(produced, "file_count", 0))}}) :
            catalog.format("ai.agent.run.detail.snapshot_only", {{"id", snapshot}})) + "\n";
      }
      if (const auto files = produced.value("files", Json::array()); !files.empty()) {
        std::string names;
        for (const auto &name : files) { names += (names.empty() ? "" : ", ") + name.get<std::string>(); }
        const auto hidden = io::get_int(produced, "file_count", 0) - int64_t(files.size());
        if (hidden > 0) { names += " " + catalog.format("ai.agent.run.detail.more_files", {{"count", std::to_string(hidden)}}); }
        text += "  " + catalog.format("ai.agent.run.detail.files", {{"names", names}}) + "\n";
      }
      if (const auto directory = io::get_string(produced, "directory"); !directory.empty()) {
        text += "  " + catalog.format("ai.agent.run.detail.directory", {{"directory", directory}}) + "\n";
      }
      if (const auto analysis = io::get_string(produced, "analysis_run_id"); !analysis.empty()) {
        text += "  " + catalog.format("ai.agent.run.detail.analysis", {{"id", analysis}}) + "\n";
      }
    }
    if (const auto more = io::get_int(detail, "more", 0); more > 0) {
      text += catalog.format("ai.agent.run.detail.more_tasks", {{"count", std::to_string(more)}}) + "\n";
    }
    if (text.empty()) { text = std::string(ctx.tr("ai.agent.run.detail.no_tasks")) + "\n"; }
    return text;
  }

  /** Forget the open detail; ``restore`` returns focus to the exact entry of the card that opened it. */
  void close_run_detail(ProjectState &state, const bool restore)
  {
    if (!run_detail_.ticket) { return; }
    state.agent().close_run_detail(run_detail_.ticket);
    if (restore && run_detail_.ui) { run_detail_.ui->restore_focus_next_frame(run_detail_.entry); }
    run_detail_ = {};
    run_detail_text_.clear(); run_detail_log_.clear();
    run_preview_text_.clear(); run_preview_log_.clear();
  }

  /** What the session waits for: a draft to review and apply (through the session, project.agent.decide), then the
   * rows it added to run from the workflow editor. */
  void agent_cards(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const Json &view)
  {
    auto &agent = state.agent();
    const auto &catalog = ctx.store.catalog();
    const std::string handle = state.project()->handle;
    const bool enabled = !state.busy() && !agent.busy() && !agent.running();
    for (const auto &item : view.value("awaiting", Json::array())) {
      const auto kind = io::get_string(item, "kind"), item_id = io::get_string(item, "item_id");
      if (kind == "start_run") { continue; }
      auto &card = layout.box();
      if (kind == "apply_draft") {
        const auto draft_id = io::get_string(item, "draft_id");
        agent.track_draft(draft_id);  // so the review page knows this session waits on it
        card.paragraph(catalog.format("ai.agent.wait_apply", {{"title", io::get_string(item, "title")}}));
        const bool current = io::get_int(item, "base_revision", -1) == state.project()->revision;
        if (!current) { card.paragraph(ctx.tr("ai.edits_stale")); }
        std::weak_ptr<bool> weak = alive_;
        card.button("ai_agent_review/" + item_id, ctx.tr("ai.agent.open_review"), [this, weak, &agent, &state, handle, draft_id,
            shell = &ctx.area.shell(), screen = ctx.area.screen(), store = &ctx.store] {
          if (!state.project() || state.project()->handle != handle) { return; }
          agent_navigation_error_.clear();
          const auto revision = state.project()->revision;
          const auto review_generation = state.review_generation();
          const auto valid = [weak, &state, handle] { return weak.lock() && state.project() && state.project()->handle == handle; };
          agent.read_draft(draft_id, [this, weak, valid, shell, screen, store, handle, revision, review_generation](const Json &draft) {
            if (!valid()) { return; }
            shell->open_saved_review(screen, handle, revision, draft, review_generation, valid, [this, weak, store](bridge::Result<Json> opened) {
              if (!weak.lock()) { return; }
              agent_navigation_error_ = opened.ok() ? "" : opened.error().message;
              store->changed();
            });
          });
        }).disable(!enabled || !current || !agent.decide_supported()).tip(ctx.tr("ai.agent.open_review.tip"));
      }
      else if (kind == "run_rows") {
        const auto rows = item.value("rows", Json::array());
        card.paragraph(catalog.format("ai.agent.wait_run", {{"count", std::to_string(rows.size())}}));
        auto *shell = &ctx.area.shell();
        auto *screen = ctx.area.screen();
        const auto self = lifetime();
        const Json target = {{"table_id", io::get_string(item, "table_id")}, {"rows", rows}};
        card.button("ai_agent_run_rows/" + item_id, catalog.format("ai.run_new_rows", {{"count", std::to_string(rows.size())}}),
            [shell, screen, self, target] {
          shell->open_target_later(screen, kEditorWorkflow, target, [self] { return !self.expired(); });
        }).disable(shell->text_input_active()).tip(ctx.tr("ai.run_new_rows.tip"));
      }
    }
  }

  std::unordered_map<std::string, Draft> drafts_, workspace_drafts_;
  std::string active_draft_, opening_, shown_context_, shown_exchange_;
  bool opened_history_ = false;
  std::string saved_questions_handle_, compose_handle_;
  uint64_t compose_generation_ = 0;
  std::optional<uint64_t> compose_focus_visibility_;
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
  TranscriptPositions transcript_positions_, agent_transcript_positions_;
  std::string pending_session_, pending_project_, agent_opening_, shown_agent_, timeline_session_, agent_navigation_error_;
  ui::LogBuffer agent_timeline_;
  std::string run_plan_origin_;
  std::map<std::string, std::string> run_plan_text_;
  std::map<std::string, ui::LogBuffer> run_plan_logs_;
  std::map<std::string, bool> run_plan_readable_;
  // The open linked-task detail (memory only; never in save_workspace_state, a draft or a request).
  struct OpenRunDetail {
    uint64_t ticket = 0;
    std::string origin;  // opening handle, session, selection epoch, screen and its visibility/activity epochs
    Json item;           // the exact card
    std::string entry;   // the full key of the card's entry, for focus restore
    ui::Context *ui = nullptr;
  } run_detail_;
  uint64_t run_detail_owner_epoch_ = 0;
  uint64_t run_detail_focus_ticket_ = 0;
  int64_t run_detail_files_scroll_entry_ = -1;
  int64_t run_detail_preview_scroll_entry_ = -1;
  uint64_t run_detail_page_epoch_ = 0;
  bool run_detail_drawn_ = false;
  std::string run_detail_text_;
  ui::LogBuffer run_detail_log_;
  // The open file preview's wrapped text and reading position (memory only, like the detail).
  std::string run_preview_text_;
  ui::LogBuffer run_preview_log_;
  ui::LogViewPosition run_preview_position_{0.0f, false};
};
}  // namespace

bool can_reveal_saved_conversation(const Editor &editor, const ProjectState &project)
{
  const auto *ai = dynamic_cast<const AIEditor *>(&editor);
  return ai && ai->can_reveal_saved(project);
}

bool saved_conversation_dispatch_safe(const Editor &editor, ProjectState &project, const std::string &request_id,
                                      DeferredAgentStartCheck agent_start)
{
  const auto *ai = dynamic_cast<const AIEditor *>(&editor);
  return !ai || ai->saved_dispatch_safe(project, request_id, agent_start);
}

bool reveal_saved_conversation(Editor &editor, ProjectState &project, const std::string &request_id)
{
  auto *ai = dynamic_cast<AIEditor *>(&editor);
  return ai && ai->reveal_saved(project, request_id);
}

bool reveal_saved_question_history(Editor &editor, const ProjectState &project)
{
  auto *ai = dynamic_cast<AIEditor *>(&editor);
  return ai && ai->reveal_saved_question_history(project);
}

bool reveal_question_composer(Editor &editor, const ProjectState &project, const uint64_t visibility)
{
  auto *ai = dynamic_cast<AIEditor *>(&editor);
  return ai && ai->reveal_question_composer(project, visibility);
}

bool reveal_saved_agent_session(Editor &editor, ProjectState &project, const std::string &session_id)
{
  auto *ai = dynamic_cast<AIEditor *>(&editor);
  return ai && ai->reveal_saved_agent(project, session_id);
}

std::string agent_session_label(const io::Json &session)
{
  auto label = conversation_title(io::get_string(session, "first_message"));
  return label.empty() ? io::get_string(session, "id").substr(0, 8) : label;
}

std::unique_ptr<Editor> make_ai_editor(const EditorType &type)
{
  return std::make_unique<AIEditor>(type);
}
}  // namespace stk::app
