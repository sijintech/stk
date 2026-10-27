/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reports_generation_view.hh"
#include "reports_create_view.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/project_report_generation.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/core/clock.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/json.hh"
#include "stk/wm/window.hh"
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
using Token = ProjectReportGeneration::Token;
constexpr size_t workspace_limit = 768 * 1024;
std::string hash(const Json &v) { return core::Sha256::hex(io::python_json_dumps(v, true, true)); }
bool same_token(Token a, Token b) { return a.epoch == b.epoch && a.edit == b.edit; }
bool valid_text(const std::string &value, size_t limit)
{
  return value.size() <= limit && core::utf8::is_valid(value) && value.find('\0') == std::string::npos;
}
// Bound the untrusted workspace tree before either JSON type conversion or copying.
bool budget(const nlohmann::json &state)
{
  struct Item { const nlohmann::json *value; size_t depth; };
  std::vector<Item> todo{{&state, 0}}; size_t left = workspace_limit;
  while (!todo.empty()) {
    const auto item = todo.back(); todo.pop_back(); const auto &v = *item.value;
    if (item.depth > 64 || !left) { return false; } --left;
    if (v.is_string()) {
      const auto &s = v.get_ref<const std::string &>();
      if (s.size() > left || !valid_text(s, workspace_limit)) { return false; } left -= s.size();
    }
    else if (v.is_structured()) {
      if (v.size() > left || todo.size() > left - v.size()) { return false; }
      for (auto i = v.begin(); i != v.end(); ++i) {
        if (v.is_object()) { if (i.key().size() > left) { return false; } left -= i.key().size(); }
        todo.push_back({&i.value(), item.depth + 1});
      }
    }
    else if (v.is_number_float() && !std::isfinite(v.get<double>())) { return false; }
    else if (v.is_binary() || v.is_discarded()) { return false; }
  }
  return true;
}
bool valid(const nlohmann::json &state)
{
  if (!state.is_object() || !budget(state)) { return false; }
  if (state.empty()) { return true; }
  if (state.size() != 8 || !state.contains("version") || !state.at("version").is_number_integer() || state.at("version") != 1) { return false; }
  for (const char *key : {"project_id", "context_id", "question", "adapter", "model"}) {
    if (!state.contains(key) || !state.at(key).is_string()) { return false; }
  }
  const auto project = state.at("project_id").get<std::string>(), context = state.at("context_id").get<std::string>();
  if ((!project.empty() && !canonical_uuid(project)) || (!context.empty() && !canonical_uuid(context)) ||
      !valid_text(state.at("question").get_ref<const std::string &>(), 65536) ||
      !valid_text(state.at("adapter").get_ref<const std::string &>(), 128) ||
      !valid_text(state.at("model").get_ref<const std::string &>(), 128) ||
      !state.contains("inputs") || !ReportsCreateView::valid_input_workspace_state(state.at("inputs")) ||
      !state.contains("generation") || !state.at("generation").is_object()) { return false; }
  if (project.empty() && (!context.empty() || !state.at("question").get_ref<const std::string &>().empty() ||
      !state.at("adapter").get_ref<const std::string &>().empty() || !state.at("model").get_ref<const std::string &>().empty())) { return false; }
  for (const char *key : {"inputs", "generation"}) {
    const auto &child = state.at(key);
    if (!child.empty() && child.contains("project_id")) {
      const auto id = child.at("project_id").get<std::string>();
      if (!id.empty() && !project.empty() && id != project) { return false; }
    }
  }
  return state.at("generation").empty() || ProjectReportGeneration::valid_workspace_state(state.at("generation"));
}
std::vector<std::string> pages(const std::string &text)
{
  std::vector<std::string> result;
  for (size_t offset = 0; offset < text.size();) {
    auto part = std::string(core::utf8::truncate_bytes(std::string_view(text).substr(offset), 2048));
    if (part.empty()) { break; } offset += part.size(); result.push_back(std::move(part));
  }
  if (result.empty()) { result.emplace_back(); } return result;
}
} // namespace

class ReportsGenerationView::Impl {
 public:
  ReportsCreateView inputs{ReportsCreateView::Mode::GenerationInputs};
  std::unique_ptr<ProjectReportGeneration> controller;
  nlohmann::json staged = nlohmann::json::object();
  AppStore *store = nullptr;
  std::shared_ptr<bool> alive = std::make_shared<bool>(true);
  std::string project_id, context_id, question, adapter, model, error;
  uint64_t epoch = 0, edit = 0;
  std::array<uint64_t, 4> text_versions{};
  struct FieldVersion { uint64_t version; std::string value, scope; };
  std::array<std::shared_ptr<FieldVersion>, 4> text_fields;
  bool acknowledge = false, wake_scheduled = false;
  uint64_t evidence_version = std::numeric_limits<uint64_t>::max();
  std::vector<std::string> evidence_pages, reply_pages;
  int evidence_page = 0, reply_page = 0;
  ~Impl() { *alive = false; }
  void changed() { ++edit; error.clear(); if (store) { store->changed(); } }
  void attach(AppStore &next)
  {
    if (!controller) {
      store = &next; controller = std::make_unique<ProjectReportGeneration>(next);
      if (!staged.empty()) { controller->load_workspace_state(staged); staged = nlohmann::json::object(); }
    }
    controller->sync();
  }
  bool dirty() const
  {
    const bool saved = controller ? io::get_string(controller->draft(), "phase") == "saved" :
        (!staged.empty() && staged.value("phase", "") == "saved");
    return inputs.dirty() || !question.empty() || !context_id.empty() || !adapter.empty() || !model.empty() ||
        (controller ? controller->dirty() : !staged.empty() && !saved);
  }
  std::function<bool()> guard(bool local_only = false)
  {
    const auto weak = std::weak_ptr<bool>(alive); const auto e = epoch, v = edit, input_version = inputs.version();
    const auto t = controller->token();
    return [this, weak, e, v, t, local_only, input_version] {
      if (weak.expired() || e != epoch || v != edit || !controller || !same_token(t, controller->token())) { return false; }
      if (local_only) { return true; }
      if (inputs.version() != input_version) { return false; }
      const auto &p = store->project();
      return p.ready() && p.loaded() && p.project() && !p.busy() &&
          (project_id.empty() || project_id == p.project()->id);
    };
  }
  void bind_project() { if (store->project().project()) { project_id = store->project().project()->id; } }
  ui::Binding<std::string> text_binding(size_t index, const std::string &key,
                                       std::function<bool()> available, bool local_question = false)
  {
    // A Tab commit can enter the next field before another frame is built. Bind
    // each field to its own version, retaining strict scope and request identity.
    // Sibling edits must not turn the next field's getter into an empty string.
    const auto weak = std::weak_ptr<bool>(alive);
    const auto e = epoch, controller_epoch = controller->token().epoch;
    const auto *p = store->project().project() ? &*store->project().project() : nullptr;
    const auto id = p ? p->id : std::string(), handle = p ? p->handle : std::string();
    const auto revision = p ? p->revision : int64_t(-1);
    const auto request = io::get_string(controller->draft(), "request_id");
    const auto phase = io::get_string(controller->draft(), "phase");
    const auto value = local_question ? question : io::get_string(controller->draft(), key);
    const auto scope = io::python_json_dumps(Json::array({e, controller_epoch, id, handle, revision, request, phase}), true, true);
    auto &ticket = text_fields.at(index);
    // TextEdit retains the binding from the frame where editing began. All later
    // frames in that same field scope must share its commit ticket, so committing
    // it also keeps the currently installed getter usable before the next frame.
    if (!ticket || ticket->version != text_versions.at(index) || ticket->value != value || ticket->scope != scope) {
      ticket = std::make_shared<FieldVersion>(FieldVersion{text_versions.at(index), value, scope});
    }
    const auto field = ticket;
    const auto current = [this, weak, e, controller_epoch, id, handle, revision, request, phase,
                          index, key, field, local_question] {
      if (weak.expired() || e != epoch || !controller || controller->token().epoch != controller_epoch ||
          text_fields.at(index) != field) { return false; }
      const auto &project = store->project(); const auto *p = project.project() ? &*project.project() : nullptr;
      if (!project.ready() || !project.loaded() || !p || p->id != id || p->handle != handle || p->revision != revision ||
          text_versions.at(index) != field->version || io::get_string(controller->draft(), "request_id") != request) { return false; }
      const auto now = io::get_string(controller->draft(), "phase");
      if (now != phase && !(phase == "saved" && now == "completed")) { return false; }
      return (local_question ? question : io::get_string(controller->draft(), key)) == field->value;
    };
    return {[this, current, key, local_question] {
      return current() ? (local_question ? question : io::get_string(controller->draft(), key)) : std::string();
    }, [this, current, available, index, key, field, local_question](const std::string &value) {
      if (!current() || !available() || controller->busy() || controller->pending() || store->project().busy()) { return; }
      if (local_question) {
        if (!valid_text(value, 65536)) { return; }
        bind_project(); question = value; changed();
      }
      else if (!controller->edit(controller->token(), key, value)) { return; }
      field->version = ++text_versions.at(index); field->value = value;
      if (store) { store->changed(); }
    }};
  }
  void reset_form()
  {
    ++epoch; inputs.load_workspace_state(nlohmann::json::object()); project_id.clear(); context_id.clear();
    question.clear(); adapter.clear(); model.clear(); acknowledge = false; evidence_pages.clear(); reply_pages.clear();
    evidence_version = std::numeric_limits<uint64_t>::max(); evidence_page = reply_page = 0; changed();
  }
  void poll(EditorContext &ctx)
  {
    const auto now = core::monotonic_seconds(), wake = controller->pump(now);
    auto *wm = ctx.area.shell().window_manager();
    if (!wm || wake_scheduled || !std::isfinite(wake) || wake < 0) { return; }
    const auto weak = std::weak_ptr<bool>(alive);
    wake_scheduled = true;
    const auto id = wm->add_timer(uint64_t(std::clamp((wake - now) * 1000 + 1, 1.0, 60000.0)), 0,
      [this, weak] { if (!weak.expired()) { wake_scheduled = false; store->changed(); } });
    if (!id) { wake_scheduled = false; }
  }
  void details(ui::Layout &box, EditorContext &ctx)
  {
    if (controller->version() != evidence_version) {
      evidence_version = controller->version();
      evidence_pages = pages(controller->frozen_input().is_object() ? io::python_json_dumps(controller->frozen_input(), true, true) : "");
      reply_pages = pages(io::get_string(controller->response(), "text"));
      evidence_page = std::clamp(evidence_page, 0, int(evidence_pages.size()) - 1);
      reply_page = std::clamp(reply_page, 0, int(reply_pages.size()) - 1);
    }
    auto show = [&](const char *key, const char *label, const std::vector<std::string> &values, int &selected) {
      if (auto *panel = box.panel(key, ctx.tr(label), false)) {
        panel->paragraph(values.at(size_t(selected)));
        panel->label(std::to_string(selected + 1) + " / " + std::to_string(values.size()));
        auto &row = panel->row(); const auto current = guard(true); const auto at = selected; int *page = &selected;
        row.button(std::string(key) + "_previous", ctx.tr("reports.previous"), [this, current, page, at] {
          if (current() && *page == at && at > 0) { --*page; store->changed(); }
        }).disable(at == 0);
        row.button(std::string(key) + "_next", ctx.tr("reports.next"), [this, current, page, at, count = int(values.size())] {
          if (current() && *page == at && at + 1 < count) { ++*page; store->changed(); }
        }).disable(at + 1 >= int(values.size()));
      }
    };
    if (controller->frozen_input().is_object()) { show("reports_generation_evidence", "reports.generation.evidence", evidence_pages, evidence_page); }
    if (controller->response().is_object()) { show("reports_generation_reply", "reports.generation.reply", reply_pages, reply_page); }
  }
  void draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> available)
  {
    attach(ctx.store); poll(ctx);
    if (project_id.empty() && inputs.dirty()) {
      project_id = inputs.save_workspace_state().value("project_id", "");
    }
    auto *panel = layout.panel("reports_generation_panel", ctx.tr("reports.generation.panel"), false);
    if (!panel) { return; }
    auto &box = *panel; auto *shell = &ctx.area.shell(); auto &g = *controller;
    const auto token = g.token(); const auto current = guard(), local = guard(true);
    const auto &draft = g.draft(); const auto phase = io::get_string(draft, "phase");
    const bool text_active = shell->text_input_active();
    const auto bound_project = !project_id.empty() ? project_id : io::get_string(draft, "project_id");
    const bool other_project = !bound_project.empty() && (!store->project().project() || store->project().project()->id != bound_project);
    const bool blocked = g.busy() || !available() || store->project().busy() || other_project;
    box.paragraph(ctx.tr("reports.generation.intro"));
    if (!error.empty()) { box.paragraph(ctx.tr(error)); }
    if (!g.error().empty()) { box.paragraph(ctx.tr(g.error())); }
    if (g.busy()) { box.label(ctx.tr("project.busy")); }
    if (other_project) { box.paragraph(ctx.tr("reports.create.other_project")); }
    const bool finished = phase == "completed" || phase == "saved" || phase == "terminal";
    const bool needs_ack = g.pending() || (io::get_bool(draft, "send_attempted", false) && !finished);
    if (dirty() || phase == "saved") {
      if (needs_ack) {
        box.checkbox("reports_generation_abandon", ctx.tr("reports.generation.abandon"),
          {[this, local] { return local() && acknowledge; }, [this, local](bool value) {
            if (local() && !controller->busy()) { acknowledge = value; if (store) { store->changed(); } }
          }}).disable(g.busy());
      }
      box.button("reports_generation_discard", ctx.tr(phase == "saved" ? "reports.generation.new" : "reports.generation.discard"),
        [this, local, token, shell, needs_ack] {
          if (local() && !shell->text_input_active() && (!needs_ack || acknowledge) &&
              controller->discard(token, !needs_ack || acknowledge)) { reset_form(); }
        }).disable(g.busy() || text_active || (needs_ack && !acknowledge));
    }
    if (other_project) { return; }
    if (!g.supported()) { box.paragraph(ctx.tr("reports.generation.unsupported")); return; }
    if (phase == "draft") {
      inputs.draw(box, ctx, [this, available] { return available() && controller && !controller->busy() && io::get_string(controller->draft(), "phase") == "draft"; });
      const auto current = guard(); // The picker may have synchronized its scope during draw.
      const auto reviewed = inputs.reviewed_input();
      std::vector<std::string> context_ids, context_names;
      if (reviewed) {
        for (const auto &source : reviewed->sources) {
          if (io::get_string(source, "kind") != "context") { continue; }
          const auto &c = source.at("context"); context_ids.push_back(io::get_string(c, "id"));
          context_names.push_back(io::get_string(c, "title") + " · " + io::get_string(c, "id").substr(0, 8));
        }
      }
      box.prop(ctx.tr("reports.generation.context")).dropdown("reports_generation_context", context_names,
        {[this, current, context_ids] {
          if (!current()) { return -1; } const auto i = std::find(context_ids.begin(), context_ids.end(), context_id);
          return i == context_ids.end() ? -1 : int(i - context_ids.begin());
        }, [this, current, context_ids, shell](int i) {
          if (current() && !controller->busy() && !shell->text_input_active() && i >= 0 && size_t(i) < context_ids.size()) {
            bind_project(); context_id = context_ids[size_t(i)]; changed();
          }
        }}).disable(blocked || context_ids.empty());
      if (!reviewed || context_ids.empty()) { box.paragraph(ctx.tr("reports.generation.review_required")); }
      auto &settings = store->models(); settings.sync();
      std::vector<std::string> adapters, endpoint_names;
      if (settings.loaded()) {
        for (const auto &endpoint : settings.endpoints()) {
          adapters.push_back(io::get_string(endpoint, "adapter"));
          endpoint_names.push_back(io::get_string(endpoint, "name") + " · " + std::string(ctx.tr("models.location." + io::get_string(endpoint, "location"))));
        }
      }
      const auto settings_version = settings.version();
      box.prop(ctx.tr("models.endpoint")).dropdown("reports_generation_endpoint", endpoint_names,
        {[this, current, adapters] {
          if (!current()) { return -1; } const auto i = std::find(adapters.begin(), adapters.end(), adapter);
          return i == adapters.end() ? -1 : int(i - adapters.begin());
        }, [this, current, adapters, settings_version, shell](int i) {
          if (current() && !shell->text_input_active() && store->models().version() == settings_version && i >= 0 && size_t(i) < adapters.size()) {
            bind_project(); adapter = adapters[size_t(i)]; model.clear(); changed();
          }
        }}).disable(blocked || !settings.loaded() || settings.busy());
      std::vector<std::string> models;
      if (const auto *endpoint = settings.by_adapter(adapter); endpoint && endpoint->contains("models") && endpoint->at("models").is_array()) {
        for (const auto &item : endpoint->at("models")) { if (item.is_string()) { models.push_back(item.get<std::string>()); } }
      }
      box.prop(ctx.tr("discussion.requests.model")).dropdown("reports_generation_model", models,
        {[this, current, models] {
          if (!current()) { return -1; } const auto i = std::find(models.begin(), models.end(), model);
          return i == models.end() ? -1 : int(i - models.begin());
        }, [this, current, models, settings_version, shell](int i) {
          if (current() && !shell->text_input_active() && store->models().version() == settings_version && i >= 0 && size_t(i) < models.size()) {
            bind_project(); model = models[size_t(i)]; changed();
          }
        }}).disable(blocked || models.empty());
      box.label(ctx.tr("reports.generation.question"));
      box.text_area("reports_generation_question", text_binding(0, "question", available, true),
                    {.max_length = 65536, .visible_lines = 3}).disable(blocked);
      box.paragraph(ctx.tr("reports.generation.commit_text"));
      const bool context_chosen = std::find(context_ids.begin(), context_ids.end(), context_id) != context_ids.end();
      const bool model_chosen = !adapter.empty() && std::find(models.begin(), models.end(), model) != models.end();
      box.button("reports_generation_prepare", ctx.tr("reports.generation.prepare"), [this, current, available, shell] {
        if (!current() || !available() || shell->text_input_active()) { return; }
        const auto input = inputs.reviewed_input();
        if (!input || !store->project().project() || input->project_id != store->project().project()->id || input->revision != store->project().project()->revision) { return; }
        const Json *context = nullptr; Json selected = Json::array(), assets = Json::array();
        for (const auto &source : input->sources) {
          selected.push_back({{"kind", source.at("kind")}, {"id", source.at("id")}});
          if (io::get_string(source, "kind") == "context" && io::get_string(source, "id") == context_id) { context = &source.at("context"); }
        }
        for (const auto &asset : input->assets) { assets.push_back({{"record_id", asset.at("record_id")}, {"path", asset.at("path")}}); }
        if (!context) { return; }
        Json selection = {{"expected_revision", input->revision}, {"sources", selected}, {"expected_sources_sha256", hash(input->sources)},
            {"snapshot_id", input->snapshot_id}, {"assets", assets}};
        if (controller->set_input(controller->token(), *context, question, {{"adapter", adapter}, {"model", model}}, selection,
            input->sources, input->assets, input->snapshot_sha256)) { controller->prepare(controller->token()); }
      }).disable(blocked || text_active || !context_chosen || !model_chosen || !visible_text(question));
      return;
    }
    box.paragraph(ctx.tr("reports.generation.frozen"));
    box.label(std::string(ctx.tr("reports.generation.request")) + io::get_string(draft, "request_id"));
    const auto status = io::get_string(g.request(), "status");
    box.label(ctx.tr("reports.generation.phase." + phase));
    if (!status.empty()) { box.label(ctx.tr("discussion.requests." + status)); }
    if (g.pending()) { box.paragraph(ctx.tr("reports.generation.pending")); }
    box.button("reports_generation_check", ctx.tr("reports.generation.check"), [this, current, available, token, shell] {
      if (current() && available() && !shell->text_input_active()) { controller->check_pending(token); }
    }).disable(blocked || text_active || io::get_string(draft, "request_id").empty());
    if (phase == "message_saved") {
      box.button("reports_generation_prepare", ctx.tr("reports.generation.continue_prepare"), [this, current, available, token, shell] {
        if (current() && available() && !shell->text_input_active()) { controller->prepare(token); }
      }).disable(blocked || text_active);
    }
    if (phase == "prepared" && !io::get_bool(draft, "send_attempted", false)) {
      const auto reason = g.send_blocked();
      if (!reason.empty()) { box.paragraph(ctx.tr(reason)); }
      box.button("reports_generation_start", ctx.tr("reports.generation.start"), [this, current, available, token, shell] {
        if (current() && available() && !shell->text_input_active()) { controller->start(token); }
      }).disable(blocked || text_active || !reason.empty());
    }
    if (status == "pending" || status == "running" || status == "uncertain") {
      box.button("reports_generation_cancel", ctx.tr("reports.generation.cancel"), [this, current, available, token, shell] {
        if (current() && available() && !shell->text_input_active()) { controller->cancel(token); }
      }).disable(blocked || text_active || (g.pending() && phase != "start_pending") || io::get_bool(g.request(), "cancel_requested", false));
      if (status != "pending") {
        box.button("reports_generation_recover", ctx.tr("reports.generation.recover"), [this, current, available, token, shell] {
          if (current() && available() && !shell->text_input_active()) { controller->recover(token); }
        }).disable(blocked || text_active || g.pending());
      }
      box.paragraph(ctx.tr("reports.generation.cancel_note"));
    }
    if (phase == "completed" || phase == "saved" || phase == "save_pending" || io::get_bool(draft, "body_initialized", false)) {
      const bool editable = !blocked && !g.pending();
      box.prop(ctx.tr("reports.create.title")).text_field("reports_generation_name", text_binding(1, "name", available), {.max_length = 256}).disable(!editable);
      box.prop(ctx.tr("reports.create.path")).text_field("reports_generation_path", text_binding(2, "entry_path", available), {.max_length = 1024}).disable(!editable);
      box.label(ctx.tr("reports.generation.body"));
      box.text_area("reports_generation_body", text_binding(3, "body", available), {.max_length = 65536, .mono = true, .visible_lines = 8}).disable(!editable);
      box.paragraph(ctx.tr("reports.generation.commit_text"));
      box.paragraph(ctx.tr("reports.generation.body_limit"));
      box.button("reports_generation_save", ctx.tr("reports.generation.save"), [this, current, available, token, shell] {
        if (current() && available() && !shell->text_input_active()) { controller->create_report(token); }
      }).disable(blocked || text_active || phase != "completed" || !g.response().is_object() ||
          !visible_text(io::get_string(draft, "body")) || !visible_text(io::get_string(draft, "name")));
    }
    details(box, ctx);
  }
};

ReportsGenerationView::ReportsGenerationView() : impl_(std::make_unique<Impl>()) {}
ReportsGenerationView::~ReportsGenerationView() = default;
void ReportsGenerationView::draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> available)
{ impl_->draw(layout, ctx, std::move(available)); }
bool ReportsGenerationView::dirty() const { return impl_->dirty(); }
std::optional<ReportsGenerationView::Created> ReportsGenerationView::take_created()
{
  if (!impl_->controller) { return {}; }
  auto value = impl_->controller->take_created(); if (!value) { return {}; }
  impl_->reset_form();
  return Created{value->project_id, value->report_id, value->source_sha256};
}
nlohmann::json ReportsGenerationView::save_workspace_state() const
{
  const auto &s = *impl_;
  if (!s.dirty() && (!s.controller || io::get_string(s.controller->draft(), "phase") != "saved")) { return nlohmann::json::object(); }
  return {{"version", 1}, {"project_id", s.project_id}, {"context_id", s.context_id}, {"question", s.question},
      {"adapter", s.adapter}, {"model", s.model}, {"inputs", s.inputs.save_workspace_state()},
      {"generation", s.controller ? s.controller->save_workspace_state() : s.staged}};
}
bool ReportsGenerationView::valid_workspace_state(const nlohmann::json &state)
{ try { return valid(state); } catch (...) { return false; } }
bool ReportsGenerationView::load_workspace_state(const nlohmann::json &state)
{
  if (!valid_workspace_state(state)) { return false; }
  auto &s = *impl_; ++s.epoch; s.controller.reset(); s.staged = nlohmann::json::object(); s.reset_form();
  if (state.empty()) { return true; }
  s.project_id = state.at("project_id").get<std::string>(); s.context_id = state.at("context_id").get<std::string>();
  s.question = state.at("question").get<std::string>(); s.adapter = state.at("adapter").get<std::string>(); s.model = state.at("model").get<std::string>();
  s.inputs.load_workspace_state(state.at("inputs")); s.staged = state.at("generation");
  return true;
}
} // namespace stk::app
