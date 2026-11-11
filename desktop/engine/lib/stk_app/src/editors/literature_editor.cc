/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/literature_page.hh"
#include "stk/app/literature_state.hh"
#include "stk/app/shell.hh"
#include "stk/core/utf8.hh"
#include "stk/wm/window.hh"
#include "project_navigation.hh"
#include <algorithm>
#include <array>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
class LiteratureEditor final : public Editor {
 public:
  explicit LiteratureEditor(const EditorType &type) : Editor(type), text_(defaults())
  {
    static uint64_t next = 0;
    scope_ = "literature-instance-" + std::to_string(++next);
  }
  ~LiteratureEditor() override
  {
    layout_.reset();
    if (view_) { view_->on_content_invalidated = {}; }
    release_page();
  }
  bool has_unsaved_changes() const override { return saved_text() != defaults() || authorized_; }
  void on_area_removed() override
  {
    suspend(); layout_.reset(); observed_screen_ = nullptr; area_ = nullptr;
  }
  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx); workspace_link(row, ctx);
    row.button("literature_refresh", ctx.tr("literature.refresh"), [this, live = guard()] {
      if (live()) { refresh(); }
    }).width(4).disable(!state_->supported() || view_->busy());
  }
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx); ui_ = ctx.ui; fields_.clear(); auto &body = layout.scope(scope_);
    if (!state_->supported()) { body.paragraph(ctx.tr("literature.unsupported")); return; }
    state_->pump(view_); advance_citation_open(); wake(ctx);
    body.tabs("literature_sections", {std::string(ctx.tr("literature.reading")),
      std::string(ctx.tr("literature.library")), std::string(ctx.tr("literature.encoder")),
      std::string(ctx.tr("literature.history"))},
      {[this] { return section_; }, [this, live = guard()](int n) {
        if (live() && n >= 0 && n < 4) { section_ = n; }
      }});
    if (!error_.empty()) { body.paragraph(ctx.tr(error_)); }
    if (!view_->error.empty()) {
      body.paragraph(view_->error.starts_with("literature.") ? std::string(ctx.tr(view_->error)) : view_->error);
    }
    if (view_->uncertain) { body.paragraph(ctx.tr("literature.uncertain")); }
    if (view_->operation.is_object()) {
      body.label(io::get_string(view_->operation, "action") + " · " + io::get_string(view_->operation, "state"));
    }
    if (section_ == 0) { reading(body, ctx); }
    else if (section_ == 1) { library(body, ctx); }
    else if (section_ == 2) { encoder(body, ctx); }
    else { history(body, ctx); }
    body.button("literature_discard", ctx.tr("literature.discard"), [this, live = guard()] {
      if (live() && !view_->busy()) {
        text_ = defaults(); authorized_ = false;
        state_->invalidate_import_draft(view_); state_->invalidate_query_draft(view_);
        state_->invalidate_encoder_draft(view_); import_review_.clear(); encoder_review_.clear();
        ++input_generation_;
      }
    }).disable(view_->busy() || !has_unsaved_changes());
  }
  nlohmann::json save_state() const override { return {{"version", 1}, {"section", section_}}; }
  bool load_state(const nlohmann::json &state) override
  {
    const Json v = state;
    if (!v.is_object() || v.size() != 2 || !v.contains("version") || !v.at("version").is_number_integer() || v.at("version") != 1 ||
        !v.contains("section") || !v.at("section").is_number_integer() ||
        io::get_int(v, "section", -1) < 0 || io::get_int(v, "section", -1) > 3) { return false; }
    section_ = int(io::get_int(v, "section", 0)); return true;
  }
  nlohmann::json save_workspace_state() const override
  {
    return {{"version", 1}, {"section", section_}, {"query", saved_text().at("query")},
      {"corpus", view_ ? view_->corpus : restored_corpus_},
      {"scopes", view_ ? view_->scopes : restored_scopes_}};
  }
  bool load_workspace_state(const nlohmann::json &state) override
  {
    const Json v = state;
    try {
      check_analysis_json_bounds(v, 16 * 1024);
      const std::set<std::string> keys{"version", "section", "query", "corpus", "scopes"};
      if (!v.is_object() || v.size() != keys.size()) { return false; }
      for (auto it = v.begin(); it != v.end(); ++it) { if (!keys.contains(it.key())) { return false; } }
      if (!v.at("query").is_string() || v.at("query").get_ref<const std::string &>().size() > 4096 ||
          !v.at("corpus").is_string() || (!io::get_string(v, "corpus").empty() &&
          !LiteratureState::corpus_id(io::get_string(v, "corpus"))) || !v.at("scopes").is_array() || v.at("scopes").size() > 8 ||
          !v.at("version").is_number_integer() || v.at("version") != 1 || !v.at("section").is_number_integer() ||
          io::get_int(v, "section", -1) < 0 || io::get_int(v, "section", -1) > 3) { return false; }
      std::vector<std::string> scopes;
      for (const auto &s : v.at("scopes")) {
        if (!s.is_string() || !LiteratureState::corpus_id(s.get<std::string>())) { return false; }
        scopes.push_back(s.get<std::string>());
      }
      auto sorted = scopes; std::sort(sorted.begin(), sorted.end());
      if (std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end()) { return false; }
      if (state_ && view_) { state_->detach(view_); }
      release_page(); text_ = defaults(); text_["query"] = io::get_string(v, "query");
      restored_corpus_ = io::get_string(v, "corpus"); restored_scopes_ = std::move(scopes);
      restore_selection_ = true; authorized_ = false; import_review_.clear(); encoder_review_.clear();
      section_ = int(io::get_int(v, "section", 0)); ui_ = nullptr; fields_.clear();
      wake_scheduled_ = false; ++generation_; ++input_generation_; return true;
    }
    catch (const std::exception &) { return false; }
  }
 private:
  LiteratureState *state_ = nullptr;
  LiteratureState::ViewPtr view_;
  AppStore *store_ = nullptr; EditorArea *area_ = nullptr; ui::Context *ui_ = nullptr;
  wm::Screen *observed_screen_ = nullptr;
  wm::Screen::LayoutObserver layout_;
  std::weak_ptr<void> shell_;
  std::map<std::string, std::string> text_;
  std::map<ui::WidgetId, std::string> fields_;
  std::string scope_, error_, import_review_, encoder_review_, render_request_, adopted_render_, restored_corpus_;
  struct CitationOpen {
    std::string resolve_id;
    uint64_t page_epoch;
    std::function<bool()> live;
  };
  std::optional<CitationOpen> citation_open_;
  std::vector<std::string> restored_scopes_;
  bool restore_selection_ = false, authorized_ = false, wake_scheduled_ = false, hidden_ = false;
  uint64_t generation_ = 0, input_generation_ = 0, view_lifetime_ = 0, texture_ = 0;
  std::function<void(uint64_t)> free_texture_;
  LiteraturePage page_;
  // Keep the framing identity across a texture release so reopening the exact page preserves its view.
  Json viewed_page_;
  std::shared_ptr<const std::vector<std::array<ui::Vec2, 4>>> highlights_;
  int section_ = 0, basis_ = 0; int64_t versions_offset_ = 0, operations_offset_ = 0;
  size_t text_page_ = 0;
  size_t history_page_ = 0;
  std::string history_operation_, history_summary_;
  static std::map<std::string, std::string> defaults()
  {
    return {{"name", ""}, {"source", ""}, {"title", ""}, {"query", ""}, {"assets", ""},
      {"evidence", ""}, {"approved_by", ""}, {"recover", ""}};
  }
  std::map<std::string, std::string> saved_text() const
  {
    auto text = text_;
    if (ui_ && ui_->edit_state()) {
      const auto i = fields_.find(ui_->editing());
      if (i != fields_.end()) { text[i->second] = ui_->edit_state()->text(); }
    }
    return text;
  }
  void release_page()
  {
    citation_open_.reset();
    if (texture_ && free_texture_) { free_texture_(texture_); }
    texture_ = 0; free_texture_ = {}; page_.clear(); highlights_.reset();
    render_request_.clear(); adopted_render_.clear(); text_page_ = 0;
    history_operation_.clear(); history_summary_.clear(); history_page_ = 0;
  }
  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store; area_ = &ctx.area; shell_ = ctx.area.shell().lifetime();
    hidden_ = false;
    if (observed_screen_ != ctx.area.screen()) {
      layout_.reset(); observed_screen_ = ctx.area.screen();
      if (observed_screen_) {
        const auto weak = lifetime();
        const auto visibility = [this, weak] {
          if (!weak.expired() && area_ && observed_screen_ &&
              (&area_->editor() != this || (observed_screen_->maximized() && observed_screen_->maximized() != area_))) { suspend(); }
        };
        layout_ = observed_screen_->observe_layout([visibility](const wm::DrawContext &) { visibility(); }, visibility);
      }
    }
    if (!state_) {
      state_ = &store_->literature(); view_ = state_->new_view();
      view_->on_content_invalidated = [this] { release_page(); };
    }
    state_->sync(view_);
    if (view_lifetime_ != view_->lifetime_epoch) {
      view_lifetime_ = view_->lifetime_epoch; import_review_.clear(); encoder_review_.clear();
      authorized_ = false; wake_scheduled_ = false; ++generation_;
    }
    if (restore_selection_) {
      state_->set_corpus(view_, restored_corpus_); state_->set_scopes(view_, restored_scopes_);
      restore_selection_ = false; // Local draft only: no metadata read, resolve, render or inference.
    }
  }
  void suspend()
  {
    if (hidden_) { return; }
    text_ = saved_text();
    if (state_ && view_) { state_->detach(view_); }
    release_page(); authorized_ = false; import_review_.clear(); encoder_review_.clear();
    ui_ = nullptr; fields_.clear(); wake_scheduled_ = false; hidden_ = true;
    ++generation_; ++input_generation_;
  }
  std::function<bool()> guard(bool source = false) const
  {
    const auto weak = lifetime(), shell = shell_; const auto area = area_;
    auto *client = store_->bridge();
    const auto pid = client ? client->bridge_pid() : 0;
    const auto spawned = client ? client->stats().spawned : 0;
    const auto generation = generation_, life = view_->lifetime_epoch, bridge = store_->bridge_epoch(),
      corpus = view_->corpus_epoch, scopes = view_->scope_epoch, query = view_->query_epoch,
      imported = view_->import_epoch, encoded = view_->encoder_draft_epoch;
    return [this, weak, shell, area, client, pid, spawned, generation, life, bridge, corpus, scopes, query, imported, encoded, source] {
      return !weak.expired() && !shell.expired() && !hidden_ && area_ == area && area_ && &area_->editor() == this &&
        area_->screen() && (!area_->screen()->maximized() || area_->screen()->maximized() == area_) &&
        store_ && view_ && generation_ == generation && view_->lifetime_epoch == life &&
        store_->bridge_epoch() == bridge && store_->bridge() == client &&
        (!client || (client->state() == bridge::BridgeState::Ready && client->bridge_pid() == pid && client->stats().spawned == spawned)) &&
        view_->corpus_epoch == corpus && view_->scope_epoch == scopes &&
        (!source || (view_->query_epoch == query && view_->import_epoch == imported && view_->encoder_draft_epoch == encoded));
    };
  }
  const Json &value(const std::string &key) const
  {
    static const Json empty;
    const auto i = view_->values.find(key); return i == view_->values.end() ? empty : i->second;
  }
  bool idle() const { return !view_->busy() && !view_->working(); }
  bool known(const std::string &id) const { return state_->corpus_info(id) != nullptr; }
  void refresh()
  {
    state_->read(view_, "info"); state_->read(view_, "encoder.info");
    std::set<std::string> scopes(view_->scopes.begin(), view_->scopes.end());
    if (!view_->corpus.empty()) { scopes.insert(view_->corpus); }
    for (const auto &id : scopes) { state_->read(view_, "corpora.info", {{"corpus_id", id}}); }
  }
  void choose_corpus(const std::string &id)
  {
    state_->set_corpus(view_, id); state_->set_scopes(view_, {id});
    authorized_ = false; import_review_.clear(); versions_offset_ = 0;
    state_->read(view_, "corpora.info", {{"corpus_id", id}});
    state_->read(view_, "versions.list", {{"corpus_id", id}, {"offset", 0}, {"limit", 20}});
  }
  std::function<bool()> input_guard() const
  {
    const auto weak = lifetime(), shell = shell_; const auto area = area_;
    const auto generation = input_generation_;
    // Local text remains editable across metadata invalidation and Bridge restarts. It carries
    // no authority; its commit invalidates the relevant review instead of borrowing a new one.
    return [this, weak, shell, area, generation] {
      return !weak.expired() && !shell.expired() && area_ == area && area_ &&
        &area_->editor() == this && input_generation_ == generation && state_ && view_;
    };
  }
  void field(ui::Layout &body, EditorContext &ctx, const std::string &key, const char *label, int kind = 0)
  {
    auto &w = body.prop(ctx.tr(label)).text_field("literature_" + key,
      {[this, key] { return text_.at(key); }, [this, key, kind, live = input_guard()](std::string text) {
        if (!live() || text_.at(key) == text) { return; }
        text_[key] = std::move(text); error_.clear();
        if (kind == 1) { state_->invalidate_import_draft(view_); import_review_.clear(); }
        if (kind == 2) { state_->invalidate_query_draft(view_); }
        if (kind == 3) { state_->invalidate_encoder_draft(view_); encoder_review_.clear(); }
      }}, {.max_length = size_t(key == "source" || key == "assets" ? 4096 : key == "evidence" ? 2048 : 256)});
    fields_[w.id] = key; w.disable(!idle());
  }
  bool act(const std::string &method, Json params)
  {
    // A new render must never reuse the prior GPU texture or pixel overlays.
    if (method == "pages.render") { release_page(); }
    if (!state_->act(view_, method, std::move(params))) { error_ = "literature.invalid_params"; return false; }
    error_.clear();
    if (method == "import.review") { import_review_ = view_->operation_id; }
    if (method == "encoder.review") { encoder_review_ = view_->operation_id; }
    if (method == "pages.render") { render_request_ = view_->operation_id; adopted_render_.clear(); }
    return true;
  }
  void open_citation(const Json &citation)
  {
    if (!state_->set_citation(view_, citation)) { error_ = "literature.invalid_params"; return; }
    if (act("citations.resolve", {{"scopes", view_->scopes}, {"citation", citation}})) {
      citation_open_ = CitationOpen{view_->operation_id, view_->page_epoch, guard(true)};
    }
  }
  void advance_citation_open()
  {
    if (!citation_open_) { return; }
    if (section_ != 0 || !citation_open_->live() || view_->page_epoch != citation_open_->page_epoch ||
        view_->operation_id != citation_open_->resolve_id) {
      citation_open_.reset(); return;
    }
    const auto &resolved = value("citations.resolve");
    if (!resolved.is_object()) {
      if (!view_->reading() && view_->follow_until <= 0) { citation_open_.reset(); }
      return;
    }
    // Only this current, accepted resolve can continue the user's explicit page-open request.
    if (!idle() || io::get_string(view_->operation, "state") != "completed") { return; }
    const Json citation = view_->citation;
    citation_open_.reset();
    if (resolved.at("citation") != citation) { return; }
    act("pages.render", {{"scopes", view_->scopes}, {"citation", citation}, {"long_edge", 1600}});
  }
  void action(ui::Layout &row, EditorContext &ctx, const char *key, const char *label,
              const std::string &method, std::function<Json()> params, bool enabled = true)
  {
    // Read current form values after the normal text-field commit. The controller independently
    // binds this request; review consumers below additionally require that exact current review.
    row.button(key, ctx.tr(label), [this, method, params = std::move(params), live = guard()] {
      if (live() && idle()) {
        try { act(method, params()); }
        catch (const std::exception &) { error_ = "literature.invalid_params"; }
      }
    }).disable(!enabled || !idle());
  }
  void reviewed_action(ui::Layout &row, EditorContext &ctx, const char *key, const char *label,
                       const std::string &method, Json params, bool enabled = true)
  {
    // Approval belongs to the exact review displayed in this frame, including its generation.
    // A cached control cannot silently approve a newer review that arrived in the meantime.
    row.button(key, ctx.tr(label), [this, method, params = std::move(params), live = guard(true)] {
      if (live() && idle()) { act(method, params); }
    }).disable(!enabled || !idle());
  }
  void wake(EditorContext &ctx)
  {
    auto *wm = ctx.area.shell().window_manager();
    if (!wm || wake_scheduled_ || view_->follow_until <= 0) { return; }
    const auto weak = lifetime(), shell = shell_; const auto generation = generation_, life = view_->lifetime_epoch;
    wake_scheduled_ = true;
    if (!wm->add_timer(300, 0, [this, weak, shell, generation, life] {
      if (weak.expired() || generation_ != generation) { return; }
      wake_scheduled_ = false;
      if (!shell.expired() && view_ && view_->lifetime_epoch == life && store_) { store_->changed(); }
    })) { wake_scheduled_ = false; }
  }
  void corpora(ui::Layout &body, EditorContext &ctx, bool search)
  {
    body.label(ctx.tr(search ? "literature.scopes" : "literature.choose_library"));
    const auto &info = value("info");
    if (!info.is_object()) { body.paragraph(ctx.tr("literature.refresh_first")); return; }
    for (const auto &item : info.at("corpora")) {
      const auto id = io::get_string(item, "corpus_id"), name = io::get_string(item, "name");
      if (search) {
        const bool selected = std::find(view_->scopes.begin(), view_->scopes.end(), id) != view_->scopes.end();
        body.checkbox("literature_scope/" + id, name, {[selected] { return selected; },
          [this, id, live = guard()](bool selected) {
            if (!live() || !idle()) { return; }
            auto scopes = view_->scopes; std::erase(scopes, id); if (selected) { scopes.push_back(id); }
            if (state_->set_scopes(view_, scopes) && selected) { state_->read(view_, "corpora.info", {{"corpus_id", id}}); }
          }}).disable(!idle());
      }
      else {
        body.button("literature_corpus/" + id, name, [this, id, live = guard()] {
          if (live() && idle()) { choose_corpus(id); }
        }).disable(!idle());
      }
    }
  }
  void library(ui::Layout &body, EditorContext &ctx)
  {
    field(body, ctx, "name", "literature.name");
    action(body, ctx, "literature_create", "literature.create", "corpora.create", [this] { return Json{{"name", text_.at("name")}}; });
    if (value("corpora.create").is_object()) {
      const auto id = io::get_string(value("corpora.create"), "corpus_id");
      body.button("literature_created", ctx.tr("literature.open_created"), [this, id, live = guard()] {
        if (live() && idle()) { choose_corpus(id); }
      }).disable(!idle());
    }
    corpora(body, ctx, false);
    if (view_->corpus.empty()) { return; }
    field(body, ctx, "source", "literature.source", 1); field(body, ctx, "title", "literature.title", 1);
    body.prop(ctx.tr("literature.authorization")).dropdown("literature_basis",
      {std::string(ctx.tr("literature.open_access")), std::string(ctx.tr("literature.self_authored"))},
      {[this] { return basis_; }, [this, live = guard()](int n) {
        if (live() && idle() && n >= 0 && n < 2) {
          basis_ = n; authorized_ = false; state_->invalidate_import_draft(view_); import_review_.clear();
        }
      }}).disable(!idle());
    field(body, ctx, "evidence", "literature.evidence", 1); field(body, ctx, "approved_by", "literature.approved_by", 1);
    body.checkbox("literature_authorized", ctx.tr("literature.authorized"), {[this] { return authorized_; },
      [this, live = guard()](bool enabled) {
        if (live() && idle()) { authorized_ = enabled; state_->invalidate_import_draft(view_); import_review_.clear(); }
      }}).disable(!idle());
    action(body, ctx, "literature_import_review", "literature.review_import", "import.review", [this] {
      if (!authorized_) { throw std::invalid_argument("authorization"); }
      return Json{{"corpus_id", view_->corpus}, {"source", text_.at("source")},
        {"document_id", LiteratureState::new_uuid()}, {"title", text_.at("title")},
        {"authorization", {{"basis", basis_ ? "self_authored" : "open_access"},
          {"evidence", text_.at("evidence")}, {"approved_by", text_.at("approved_by")}}}};
    }, authorized_ && known(view_->corpus));
    const auto &review = value("import.review");
    if (review.is_object() && !import_review_.empty()) {
      body.paragraph(io::get_string(review, "source")); body.paragraph(io::get_string(review, "title"));
      body.paragraph(io::get_string(review, "source_sha256") + " · " + std::to_string(io::get_int(review, "source_bytes", 0)));
      body.paragraph(io::get_string(review.at("authorization"), "evidence"));
      reviewed_action(body, ctx, "literature_import_commit", "literature.commit_import", "import.commit",
        {{"review_id", import_review_}, {"review_sha256", LiteratureState::checksum(review)}}, authorized_);
    }
    auto &row = body.row();
    row.button("literature_versions", ctx.tr("literature.versions"), [this, live = guard()] {
      if (live()) { state_->read(view_, "versions.list", {{"corpus_id", view_->corpus}, {"offset", versions_offset_}, {"limit", 20}}); }
    }).disable(!idle() || !known(view_->corpus));
    if (value("versions.list").is_object()) {
      const auto &versions = value("versions.list").at("versions");
      for (const auto &v : versions) {
        const auto id = io::get_string(v, "version_id");
        body.button("literature_version/" + id, io::get_string(v, "title") + " · " +
          std::string(ctx.tr(io::get_bool(v, "active", false) ? "literature.available" : "literature.revoked")),
          [this, id, live = guard()] { if (live() && idle()) { state_->set_version(view_, id); } }).disable(!idle());
      }
      pagination(body, ctx, "versions", versions_offset_, versions.size(), 20);
    }
    auto &actions = body.row();
    action(actions, ctx, "literature_index", "literature.index", "index.start", [this] {
      return Json{{"corpus_id", view_->corpus}, {"version_id", view_->version_id}};
    }, known(view_->corpus) && !view_->version_id.empty());
    action(actions, ctx, "literature_revoke", "literature.revoke", "versions.revoke", [this] {
      return Json{{"corpus_id", view_->corpus}, {"version_id", view_->version_id}};
    }, known(view_->corpus) && !view_->version_id.empty());
    field(body, ctx, "recover", "literature.original_import");
    action(body, ctx, "literature_recover", "literature.recover", "import.recover", [this] {
      return Json{{"corpus_id", view_->corpus}, {"original_operation_id", text_.at("recover")}};
    }, known(view_->corpus));
  }
  void encoder(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("literature.encoder_explanation")); field(body, ctx, "assets", "literature.assets", 3);
    action(body, ctx, "literature_encoder_review", "literature.review_encoder", "encoder.review", [this] {
      return Json{{"assets", text_.at("assets")}};
    });
    if (value("encoder.review").is_object() && !encoder_review_.empty()) {
      const auto &r = value("encoder.review"); body.paragraph(io::get_string(r, "assets"));
      body.paragraph(io::get_string(r, "fingerprint"));
      reviewed_action(body, ctx, "literature_encoder_select", "literature.select_encoder", "encoder.select",
        {{"review_id", encoder_review_}, {"review_sha256", LiteratureState::checksum(r)},
          {"expected_generation", io::get_int(state_->encoder_info(), "generation", -1)}});
    }
    const auto &e = state_->encoder_info();
    body.paragraph(ctx.tr(e.is_object() && e.contains("selection") && !e.at("selection").is_null() ?
      "literature.encoder_selected" : "literature.encoder_missing"));
    const auto *info = state_->corpus_info(view_->corpus);
    action(body, ctx, "literature_build", "literature.build", "dense.build", [this] {
      return Json{{"corpus_id", view_->corpus}, {"expected_generation", io::get_int(*state_->corpus_info(view_->corpus), "generation", -1)},
        {"encoder_generation", io::get_int(state_->encoder_info(), "generation", -1)}};
    }, info && e.is_object() && e.contains("selection") && !e.at("selection").is_null());
  }
  void reading(ui::Layout &body, EditorContext &ctx)
  {
    corpora(body, ctx, true); field(body, ctx, "query", "literature.query", 2);
    const auto &e = state_->encoder_info();
    const bool ready = !view_->scopes.empty() && std::all_of(view_->scopes.begin(), view_->scopes.end(), [this](const auto &id) { return known(id); }) &&
      e.is_object() && e.contains("selection") && !e.at("selection").is_null();
    action(body, ctx, "literature_search", "literature.search", "search", [this] {
      return Json{{"scopes", view_->scopes}, {"query", text_.at("query")},
        {"encoder_generation", io::get_int(state_->encoder_info(), "generation", -1)}, {"limit", 20}};
    }, ready);
    if (!ready) { body.paragraph(ctx.tr("literature.search_prerequisites")); }
    if (value("search").is_object()) {
      int n = 0;
      for (const auto &hit : value("search").at("hits")) {
        const auto citation = hit.at("citation");
        const auto text = io::get_string(hit, "text");
        const auto number = n++;
        const auto label = std::string(ctx.tr("literature.open_citation")) + " · " + std::to_string(number + 1) +
          " · " + std::string(ctx.tr("literature.page")) + " " +
          std::to_string(io::get_int(citation.at("inner"), "page_index", 0) + 1) + " · " +
          std::string(core::utf8::truncate_bytes(text, 80));
        body.button("literature_hit/" + std::to_string(number), label,
          [this, citation, live = guard(true)] { if (live() && idle()) { open_citation(citation); } }).disable(!idle());
        body.paragraph(core::utf8::truncate_bytes(text, 1024));
        if (text.size() > 1024) { body.paragraph(ctx.tr("literature.excerpt")); }
      }
    }
    auto &row = body.row();
    action(row, ctx, "literature_resolve", "literature.resolve", "citations.resolve", [this] {
      return Json{{"scopes", view_->scopes}, {"citation", view_->citation}};
    }, view_->citation.is_object());
    action(row, ctx, "literature_render", "literature.render", "pages.render", [this] {
      return Json{{"scopes", view_->scopes}, {"citation", view_->citation}, {"long_edge", 1600}};
    }, view_->citation.is_object() && value("citations.resolve").is_object());
    const auto &resolved = value("citations.resolve");
    if (resolved.is_object()) {
      const auto &text = resolved.at("text").get_ref<const std::string &>();
      std::vector<size_t> offsets{0};
      while (offsets.back() < text.size()) { offsets.push_back(offsets.back() + core::utf8::truncate_bytes(std::string_view(text).substr(offsets.back()), 4096).size()); }
      text_page_ = std::min(text_page_, offsets.size() > 1 ? offsets.size() - 2 : size_t(0));
      const auto begin = offsets[text_page_], end = offsets.size() > 1 ? offsets[text_page_ + 1] : begin;
      body.paragraph(text.substr(begin, end - begin));
      auto &pages = body.row();
      pages.button("literature_text_previous", ctx.tr("literature.previous"), [this, live = guard(true)] { if (live() && text_page_) { --text_page_; } }).disable(text_page_ == 0);
      pages.button("literature_text_next", ctx.tr("literature.next"), [this, live = guard(true)] { if (live()) { ++text_page_; } }).disable(text_page_ + 2 >= offsets.size());
    }
    bool refit = false;
    const auto &rendered = value("pages.render");
    if (!render_request_.empty() && adopted_render_ != render_request_ && resolved.is_object() && rendered.is_object()) {
      const auto request = render_request_;
      if (page_.adopt(resolved, rendered)) {
        const auto &citation = page_.citation();
        const auto &inner = citation.at("inner");
        const auto &base = inner.contains("base") ? inner.at("base") : inner;
        auto frame = Json::array({citation.at("corpus_id"), citation.at("database_id"), base.at("version_id"),
                                  base.at("source_sha256"), base.at("page_index"), rendered.at("image").at("sha256")});
        refit = frame != viewed_page_;
        viewed_page_ = std::move(frame);
        auto quads = std::make_shared<std::vector<std::array<ui::Vec2, 4>>>();
        for (const auto &q : *page_.highlights()) {
          std::array<ui::Vec2, 4> points;
          for (size_t i = 0; i < 4; ++i) { points[i] = {float(q.points[i][0]), float(q.points[i][1])}; }
          quads->push_back(points);
        }
        highlights_ = std::move(quads);
      }
      adopted_render_ = request;
    }
    if (!page_.error().empty()) { body.paragraph(ctx.tr(page_.error())); }
    if (page_.ready()) {
      auto &jobs = ctx.store.jobs();
      if (!texture_ && jobs.create_texture && jobs.free_texture) {
        free_texture_ = jobs.free_texture; texture_ = jobs.create_texture(*page_.image());
      }
      auto &image = body.image("literature_page",
                               {texture_, int(page_.image()->width), int(page_.image()->height), 18, highlights_});
      if (refit) { body.ctx().reset_image_view(image.id); }
    }
  }
  void pagination(ui::Layout &body, EditorContext &ctx, const std::string &kind, int64_t &offset, size_t count, int64_t limit)
  {
    auto &row = body.row();
    for (const int direction : {-1, 1}) {
      const auto next = offset + direction * limit;
      row.button("literature_" + kind + (direction < 0 ? "_previous" : "_next"), ctx.tr(direction < 0 ? "literature.previous" : "literature.next"),
        [this, kind, next, selected = &offset, live = guard() ] {
          if (!live() || !idle()) { return; }
          Json p{{"offset", next}, {"limit", kind == "versions" ? 20 : 50}};
          if (kind == "versions") { p["corpus_id"] = view_->corpus; }
          if (state_->read(view_, kind + ".list", std::move(p))) { *selected = next; }
        }).disable(!idle() || next < 0 || next > 4096 || (direction > 0 && count < size_t(limit)));
    }
  }
  void history(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("literature.history_explanation"));
    body.button("literature_operations", ctx.tr("literature.operations"), [this, live = guard()] {
      if (live()) { state_->read(view_, "operations.list", {{"offset", operations_offset_}, {"limit", 50}}); }
    }).disable(!idle());
    if (value("operations.list").is_object()) {
      const auto &operations = value("operations.list").at("operations");
      for (const auto &op : operations) {
        body.button("literature_operation/" + io::get_string(op, "operation_id"), io::get_string(op, "action") + " · " + io::get_string(op, "state"),
          [this, op, live = guard()] { if (live() && idle()) { state_->select_operation(view_, op); import_review_.clear(); encoder_review_.clear(); authorized_ = false; } }).disable(!idle());
      }
      pagination(body, ctx, "operations", operations_offset_, operations.size(), 50);
    }
    if (!view_->operation_id.empty()) {
      body.paragraph(view_->operation_id);
      auto &row = body.row();
      row.button("literature_check", ctx.tr("literature.check"), [this, live = guard()] { if (live()) { state_->check_operation(view_); } }).disable(view_->busy());
      row.button("literature_result", ctx.tr("literature.result"), [this, live = guard()] { if (live()) { state_->load_result(view_); } }).disable(view_->busy());
      if (!view_->historical_result.is_null()) {
        body.paragraph(ctx.tr("literature.history_result"));
        if (history_operation_ != view_->operation_id) {
          auto summary = view_->historical_result;
          if (summary.is_object()) {
            if (summary.contains("image") && summary.at("image").is_object()) { summary["image"].erase("data_base64"); }
            summary.erase("characters"); summary.erase("highlights");
          }
          history_summary_ = summary.dump(2, ' ', false); history_operation_ = view_->operation_id; history_page_ = 0;
        }
        body.paragraph(ctx.tr("literature.history_summary"));
        std::vector<size_t> offsets{0};
        while (offsets.back() < history_summary_.size()) {
          offsets.push_back(offsets.back() + core::utf8::truncate_bytes(std::string_view(history_summary_).substr(offsets.back()), 4096).size());
        }
        history_page_ = std::min(history_page_, offsets.size() > 1 ? offsets.size() - 2 : size_t(0));
        const auto begin = offsets[history_page_], end = offsets.size() > 1 ? offsets[history_page_ + 1] : begin;
        body.paragraph(history_summary_.substr(begin, end - begin));
        auto &pages = body.row();
        pages.button("literature_history_previous", ctx.tr("literature.previous"), [this, live = guard()] {
          if (live() && history_page_) { --history_page_; }
        }).disable(history_page_ == 0);
        pages.button("literature_history_next", ctx.tr("literature.next"), [this, live = guard()] {
          if (live()) { ++history_page_; }
        }).disable(history_page_ + 2 >= offsets.size());
      }
    }
  }
};
}  // namespace
std::unique_ptr<Editor> make_literature_editor(const EditorType &type) { return std::make_unique<LiteratureEditor>(type); }
}  // namespace stk::app
