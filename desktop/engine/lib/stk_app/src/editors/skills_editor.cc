/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Skills editor: installed catalog and project-owned version snapshots.
 * It shows each skill's identity, entry, inputs, parameters, outputs, dependencies, availability
 * and examples. Explicit project writes pin, upgrade, restore or copy an analysis; none run it.
 */
#include "workspace_fields.hh"
#include "project_navigation.hh"

#include "stk/app/skill_catalog.hh"
#include "stk/app/project_skills.hh"
#include "stk/app/project_analyses.hh"
#include "stk/app/project_workflows.hh"
#include "stk/app/analysis_document.hh"
#include "editor_text.hh"

#include <algorithm>
#include <map>

namespace stk::app {
namespace {

std::string joined(const io::Json &values, const std::string &empty)
{
  std::string text;
  if (values.is_array()) {
    for (const auto &value : values) {
      if (!value.is_string()) { continue; }
      text += (text.empty() ? "" : ", ") + value.get<std::string>();
    }
  }
  return text.empty() ? empty : text;
}

const io::Json &member(const io::Json &object, const char *key)
{
  static const io::Json null;
  if (!object.is_object()) { return null; }
  const auto found = object.find(key);
  return found == object.end() ? null : *found;
}

class SkillsEditor final : public Editor {
  static constexpr size_t kBindingTextBytes = 256 * 1024;
  static constexpr size_t kBindingDraftBytes = 1024 * 1024;
 public:
  explicit SkillsEditor(const EditorType &type) : Editor(type) {}

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &skills = ctx.store.skills();
    skills.sync();
    if (!project_skills_) { project_skills_ = std::make_unique<ProjectSkills>(ctx.store); }
    project_skills_->sync();
    auto &top = layout.row();
    workspace_link(top, ctx);
    top.label(ctx.tr("skills.title"));
    publication_status(layout, ctx);
    auto &tabs = layout.row();
    tabs.button("skills_library_tab", ctx.tr("skills.library"), [this] { project_view_ = false; });
    tabs.button("skills_project_tab", ctx.tr("skills.project.title"), [this] { project_view_ = true; });
    if (project_view_) { project_view(layout, ctx); return; }
    hint(layout, ctx, "skills.intro");
    if (!skills.bridge_ready()) {
      layout.paragraph(ctx.tr("skills.bridge_wait"));
      return;
    }
    if (!skills.supported()) {
      layout.paragraph(ctx.tr("skills.unsupported"));
      return;
    }
    skills.ensure_loaded();

    auto &search = layout.row();
    ui::TextFieldOptions options;
    options.placeholder = std::string(ctx.tr("skills.query"));
    options.max_length = SkillCatalogState::kMaxQuery;
    options.on_submit = [&skills, this] { skills.search(query_); };
    search.text_field("skills_query", ui::bind(query_), options);
    search.button("skills_search", ctx.tr("skills.search"), [&skills, this] { skills.search(query_); }).width(5);
    search.button("skills_refresh", ctx.tr("skills.refresh"), [&skills] { skills.refresh(); }).width(6);

    if (!skills.error().empty()) { layout.paragraph(skills.error()); }
    if (skills.loading()) { layout.label(ctx.tr("skills.loading")); }
    if (skills.problem_count() > 0) { problems(layout, ctx, skills); }

    const float width = ctx.draw ? float(ctx.draw->rect.width()) : 1280.0f;
    const float scale = ctx.ui ? ctx.ui->style().unit / 20.0f : 1.0f;
    if (width >= 920.0f * scale) {
      auto &columns = layout.split(0.36f);
      auto &left = columns.column();
      auto &right = columns.column();
      rows(left, ctx, skills, 14.0f);
      detail(right, ctx, skills);
    }
    else {
      rows(layout, ctx, skills, 6.0f);
      detail(layout, ctx, skills);
    }
  }

  nlohmann::json save_workspace_state() const override
  {
    io::Json drafts = io::Json::object();
    for (const auto &[key, text] : binding_drafts_) {
      if (key.substr(0, 36) == saved_project_id_) { drafts[key] = text; }
    }
    return {{"version", 1}, {"query", query_}, {"project_view", project_view_},
            {"project_id", saved_project_id_}, {"selected_id", saved_skill_id_}, {"binding_drafts", drafts}};
  }
  bool load_workspace_state(const nlohmann::json &value) override
  {
    if (!workspace_fields(value, {"query", "project_id", "selected_id"}, {}, {"project_view"}, {"binding_drafts"}, kBindingDraftBytes + kBindingTextBytes)) { return false; }
    const auto project = value.value("project_id", std::string());
    const auto selected = value.value("selected_id", std::string());
    if ((!project.empty() && !canonical_uuid(project)) || (!selected.empty() && !canonical_uuid(selected))) { return false; }
    std::map<std::string, std::string> drafts;
    if (value.contains("binding_drafts")) {
      const auto &saved = value.at("binding_drafts");
      if (!saved.is_object() || saved.dump().size() > kBindingDraftBytes) { return false; }
      for (const auto &[key, text] : saved.items()) {
        if (key.size() != 138 || key[36] != ':' || key[73] != ':' ||
            !canonical_uuid(key.substr(0, 36)) || !canonical_uuid(key.substr(37, 36)) ||
            key.substr(74).find_first_not_of("0123456789abcdef") != std::string::npos ||
            !text.is_string() || text.get_ref<const std::string &>().size() > kBindingTextBytes) { return false; }
        drafts[key] = text.get<std::string>();
      }
    }
    binding_drafts_ = std::move(drafts); ++binding_version_;
    query_ = value.value("query", std::string());
    project_view_ = value.value("project_view", false);
    saved_project_id_ = project; saved_skill_id_ = selected;
    restore_selection_ = true; return true;
  }

 private:
  bool writable(EditorContext &ctx) const
  {
    return project_skills_ && project_skills_->supported() && !project_skills_->busy() &&
        !project_skills_->uncertain() && !ctx.store.skills().publication_busy() && !ctx.store.skills().publication_uncertain() &&
        !ctx.store.project().busy() &&
        !ctx.area.shell().has_unsaved_changes() && !ctx.area.shell().text_input_active();
  }
  std::function<void()> mutation(EditorContext &ctx, std::string action, io::Json params,
                                  std::string catalog_ref = {}, std::string catalog_hash = {}, uint64_t source_version = 0)
  {
    const auto weak = lifetime();
    auto *area = &ctx.area;
    const auto shell_weak = area->shell().lifetime();
    const auto epoch = project_skills_->epoch();
    auto *store = &ctx.store;
    return [this, weak, shell_weak, area, store, epoch, action = std::move(action), params = std::move(params),
            catalog_ref = std::move(catalog_ref), catalog_hash = std::move(catalog_hash), source_version] {
      if (weak.expired() || shell_weak.expired() || &area->editor() != this ||
          area->shell().has_unsaved_changes() || area->shell().text_input_active()) { return; }
      if (!catalog_ref.empty() && (store->skills().selected() != catalog_ref ||
          io::get_string(store->skills().detail(), "content_sha256") != catalog_hash)) { return; }
      if (action == "publish_analysis" && (!analysis_source_ || analysis_source_->busy() || analysis_source_->stale() ||
          analysis_source_->selected_version() != source_version ||
          source_selected_id_ != io::get_string(params, "analysis_id") ||
          io::get_string(analysis_source_->selected(), "id") != io::get_string(params, "analysis_id"))) { return; }
      if (action == "publish_workflow" && (!workflow_source_ || workflow_source_->busy() || workflow_source_->stale() ||
          workflow_source_->selected_version() != source_version ||
          workflow_source_selected_id_ != io::get_string(params, "workflow_id") ||
          io::get_string(workflow_source_->selected(), "id") != io::get_string(params, "workflow_id"))) { return; }
      if (action == "create_workflow" && binding_version_ != source_version) { return; }
      if (project_skills_->write(action, params, epoch)) { project_view_ = true; }
    };
  }
  void publication_status(ui::Layout &layout, EditorContext &ctx)
  {
    auto &catalog = ctx.store.skills();
    if (!catalog.publication_error().empty()) { layout.paragraph(catalog.publication_error()); }
    if (catalog.publication_busy()) { layout.label(ctx.tr("skills.user.publishing")); }
    if (catalog.publication_uncertain()) {
      layout.paragraph(ctx.store.catalog().format("skills.user.uncertain", {
          {"id", io::get_string(catalog.publication_pending(), "publication_id")}}));
      const auto publication_id = io::get_string(catalog.publication_pending(), "publication_id");
      layout.button("skill_publication_check", ctx.tr("skills.user.check"), [&catalog, publication_id] {
        if (io::get_string(catalog.publication_pending(), "publication_id") == publication_id) { catalog.check_publication(); }
      })
          .disable(catalog.publication_busy());
    }
    if (!catalog.publication_notice().empty()) { layout.paragraph(ctx.tr(catalog.publication_notice())); }
    if (catalog.publication().is_object()) {
      layout.label(io::get_string(catalog.publication().at("skill"), "ref"));
    }
  }
  void publish_global(ui::Layout &layout, EditorContext &ctx)
  {
    auto &saved = *project_skills_;
    auto &catalog = ctx.store.skills();
    if (!catalog.publication_supported()) { return; }
    const auto epoch = saved.epoch();
    const auto digest = io::get_string(saved.selected().at("active"), "content_sha256");
    const auto selected = saved.selected_id();
    const auto revision = saved.revision();
    const auto publication_generation = catalog.publication_generation();
    auto *area = &ctx.area;
    const auto weak = lifetime(), shell_weak = area->shell().lifetime();
    const auto action = [this, weak, shell_weak, area, &catalog, epoch, selected, revision, digest, publication_generation](const std::string &mode) {
      return [this, weak, shell_weak, area, &catalog, epoch, selected, revision, digest, publication_generation, mode] {
        if (weak.expired() || shell_weak.expired() || &area->editor() != this ||
            area->shell().has_unsaved_changes() || area->shell().text_input_active()) { return; }
        project_skills_->sync();
        if (catalog.publication_generation() != publication_generation || project_skills_->selected_id() != selected ||
            project_skills_->revision() != revision) { return; }
        catalog.publish(*project_skills_, mode, epoch, digest);
      };
    };
    layout.paragraph(ctx.tr("skills.user.publish_hint"));
    layout.button("project_skill_publish_global", ctx.tr("skills.user.publish"), action("exact"))
        .disable(!writable(ctx) || !saved.current());
    if (catalog.publication_conflict(saved)) {
      layout.paragraph(ctx.tr("skills.user.conflict"));
      layout.button("project_skill_publish_global_new_version", ctx.tr("skills.user.new_version"), action("new_version"))
          .disable(!writable(ctx) || !saved.current());
    }
  }
  void publish_analysis(ui::Layout &layout, EditorContext &ctx)
  {
    auto &saved = *project_skills_;
    if (!saved.can_publish()) { return; }
    auto *panel = layout.panel("project_skill_publish", ctx.tr("skills.project.publish"), false);
    if (!panel) { return; }
    if (!analysis_source_) { analysis_source_ = std::make_unique<ProjectAnalyses>(ctx.store); }
    auto &source = *analysis_source_;
    source.sync(); source.set_archive_filter(false);
    if (source.epoch() != source_epoch_) {
      source_epoch_ = source.epoch(); source_page_revision_ = source_detail_revision_ = -1; source_selected_id_.clear();
    }
    if (!source.busy() && !ctx.store.project().busy()) {
      if (source_page_revision_ != saved.revision()) {
        source_page_revision_ = saved.revision(); source.load_page();
      }
      else if (!source_selected_id_.empty() && source.stale() && source_detail_revision_ != saved.revision()) {
        source_detail_revision_ = saved.revision(); source.load(source_selected_id_);
      }
    }
    panel->paragraph(ctx.tr("skills.project.publish_hint"));
    const auto weak = lifetime();
    const auto source_epoch = source.epoch();
    panel->button("project_skill_sources_refresh", ctx.tr("skills.refresh"), [this, weak, source_epoch] {
      if (weak.expired() || !analysis_source_) { return; }
      analysis_source_->sync();
      if (analysis_source_->epoch() != source_epoch || analysis_source_->busy()) { return; }
      source_page_revision_ = source_detail_revision_ = -1;
    }).disable(source.busy());
    if (source.busy()) { panel->label(ctx.tr("skills.loading")); }
    if (!source.error().empty()) { panel->paragraph(source.error()); }
    const auto &page = source.page();
    if (page.is_object()) {
      const auto items = page.at("analyses");
      if (items.empty()) { panel->paragraph(ctx.tr("skills.project.no_analyses")); }
      else {
        const auto epoch = source.epoch();
        ui::ListSpec spec;
        spec.count = int(items.size()); spec.rows = std::min(4.0f, float(items.size()));
        spec.text = [items](int i) {
          return i >= 0 && size_t(i) < items.size() ? io::get_string(items[size_t(i)], "name") : std::string();
        };
        spec.selected = {[this, weak, items] {
          if (weak.expired()) { return -1; }
          for (size_t i = 0; i < items.size(); ++i) {
            if (io::get_string(items[i], "id") == source_selected_id_) { return int(i); }
          }
          return -1;
        }, [this, weak, items, epoch](int i) {
          if (weak.expired() || !analysis_source_) { return; }
          auto &source = *analysis_source_;
          source.sync();
          if (source.epoch() == epoch && !source.busy() && i >= 0 && size_t(i) < items.size()) {
            source_selected_id_ = io::get_string(items[size_t(i)], "id");
            source.load(source_selected_id_);
          }
        }};
        panel->virtual_list("project_skill_sources", std::move(spec));
      }
      const auto offset = io::get_int(page, "offset", 0);
      const auto load_page = [this, weak, source_epoch](int64_t target) {
        if (weak.expired() || !analysis_source_) { return; }
        analysis_source_->sync();
        if (analysis_source_->epoch() == source_epoch) { analysis_source_->load_page(target); }
      };
      auto &pages = panel->row();
      pages.button("project_skill_sources_previous", ctx.tr("skills.previous"), [load_page, offset] { load_page(std::max(int64_t(0), offset - 50)); })
          .disable(source.busy() || offset == 0);
      pages.button("project_skill_sources_next", ctx.tr("skills.next"), [load_page, offset] { load_page(offset + 50); })
          .disable(source.busy() || offset + int64_t(items.size()) >= io::get_int(page, "total", 0));
    }
    const auto &item = source.selected();
    if (!item.is_object() || io::get_string(item, "id") != source_selected_id_) { return; }
    if (io::get_string(item, "state") != "readable") { panel->paragraph(io::get_string(item, "error")); return; }
    const auto title = io::get_string(item, "name");
    const auto &document = item.at("document");
    auto description = io::get_string(document.at("graph"), "description");
    if (description.empty()) { description = title; }
    panel->label(title); panel->paragraph(description);
    const bool enabled = writable(ctx) && !source.busy() && !source.stale() && source.error().empty();
    const auto params = [&](bool create) {
      return io::Json{{"analysis_id", item.at("id")}, {"project_skill_id", create ? ProjectSkills::new_id() : saved.selected_id()},
          {"create", create}, {"name", title}, {"description", description}, {"expected_revision", saved.revision()}};
    };
    panel->button("project_skill_publish_new", ctx.tr("skills.project.publish_new"),
        mutation(ctx, "publish_analysis", params(true), {}, {}, source.selected_version())).disable(!enabled);
    if (saved.current()) {
      const auto &versions = saved.selected().at("document").at("versions");
      if (!versions.empty() && io::get_string(versions.front().at("definition").at("entry"), "kind") == "graph.document") {
        panel->button("project_skill_publish_version", ctx.tr("skills.project.publish_version"),
            mutation(ctx, "publish_analysis", params(false), {}, {}, source.selected_version())).disable(!enabled);
      }
    }
  }
  void publish_workflow(ui::Layout &layout, EditorContext &ctx)
  {
    auto &saved = *project_skills_;
    if (!saved.can_publish_workflow()) { return; }
    auto *panel = layout.panel("project_skill_workflow_publish", ctx.tr("skills.project.publish_workflow"), false);
    if (!panel) { return; }
    if (!workflow_source_) { workflow_source_ = std::make_unique<ProjectWorkflows>(ctx.store); }
    auto &source = *workflow_source_;
    source.sync(); source.set_archive_filters(false, false);
    if (source.epoch() != workflow_source_epoch_) {
      workflow_source_epoch_ = source.epoch(); workflow_source_page_revision_ = workflow_source_detail_revision_ = -1; workflow_source_selected_id_.clear();
    }
    if (!source.busy() && !ctx.store.project().busy()) {
      if (workflow_source_page_revision_ != saved.revision()) {
        workflow_source_page_revision_ = saved.revision(); source.load_page();
      }
      else if (!workflow_source_selected_id_.empty() && source.stale() && workflow_source_detail_revision_ != saved.revision()) {
        workflow_source_detail_revision_ = saved.revision(); source.load(workflow_source_selected_id_);
      }
    }
    panel->paragraph(ctx.tr("skills.project.publish_workflow_hint"));
    const auto weak = lifetime();
    const auto source_epoch = source.epoch();
    panel->button("project_skill_workflow_sources_refresh", ctx.tr("skills.refresh"), [this, weak, source_epoch] {
      if (weak.expired() || !workflow_source_) { return; }
      workflow_source_->sync();
      if (workflow_source_->epoch() != source_epoch || workflow_source_->busy()) { return; }
      workflow_source_page_revision_ = workflow_source_detail_revision_ = -1;
    }).disable(source.busy());
    if (source.busy()) { panel->label(ctx.tr("skills.loading")); }
    if (!source.error().empty()) { panel->paragraph(source.error()); }
    const auto &page = source.page();
    if (page.is_object()) {
      const auto items = page.at("workflows");
      if (items.empty()) { panel->paragraph(ctx.tr("skills.project.no_workflows")); }
      else {
        const auto epoch = source.epoch();
        ui::ListSpec spec;
        spec.count = int(items.size()); spec.rows = std::min(4.0f, float(items.size()));
        spec.text = [items](int i) {
          return i >= 0 && size_t(i) < items.size() ? io::get_string(items[size_t(i)], "name") : std::string();
        };
        spec.selected = {[this, weak, items] {
          if (weak.expired()) { return -1; }
          for (size_t i = 0; i < items.size(); ++i) {
            if (io::get_string(items[i], "id") == workflow_source_selected_id_) { return int(i); }
          }
          return -1;
        }, [this, weak, items, epoch](int i) {
          if (weak.expired() || !workflow_source_) { return; }
          auto &source = *workflow_source_;
          source.sync();
          if (source.epoch() == epoch && !source.busy() && i >= 0 && size_t(i) < items.size()) {
            workflow_source_selected_id_ = io::get_string(items[size_t(i)], "id");
            source.load(workflow_source_selected_id_);
          }
        }};
        panel->virtual_list("project_skill_workflow_sources", std::move(spec));
      }
      const auto offset = io::get_int(page, "offset", 0);
      const auto load_page = [this, weak, source_epoch](int64_t target) {
        if (weak.expired() || !workflow_source_) { return; }
        workflow_source_->sync();
        if (workflow_source_->epoch() == source_epoch) { workflow_source_->load_page(target); }
      };
      auto &pages = panel->row();
      pages.button("project_skill_workflow_sources_previous", ctx.tr("skills.previous"), [load_page, offset] { load_page(std::max(int64_t(0), offset - 50)); })
          .disable(source.busy() || offset == 0);
      pages.button("project_skill_workflow_sources_next", ctx.tr("skills.next"), [load_page, offset] { load_page(offset + 50); })
          .disable(source.busy() || offset + int64_t(items.size()) >= io::get_int(page, "total", 0));
    }
    const auto &item = source.selected();
    if (!item.is_object() || io::get_string(item, "id") != workflow_source_selected_id_) { return; }
    if (io::get_string(item, "state") != "readable") { panel->paragraph(io::get_string(item, "error")); return; }
    const auto title = io::get_string(item, "name");
    const auto description = title;
    panel->label(title); panel->paragraph(description);
    const bool enabled = writable(ctx) && !source.busy() && !source.stale() && source.error().empty();
    const auto params = [&](bool create) {
      return io::Json{{"workflow_id", item.at("id")}, {"project_skill_id", create ? ProjectSkills::new_id() : saved.selected_id()},
          {"create", create}, {"name", title}, {"description", description}, {"expected_revision", saved.revision()}};
    };
    panel->button("project_skill_workflow_publish_new", ctx.tr("skills.project.publish_new"),
        mutation(ctx, "publish_workflow", params(true), {}, {}, source.selected_version())).disable(!enabled);
    if (saved.current()) {
      const auto &versions = saved.selected().at("document").at("versions");
      if (!versions.empty() && io::get_string(versions.front().at("definition").at("entry"), "kind") == "workflow.document") {
        panel->button("project_skill_workflow_publish_version", ctx.tr("skills.project.publish_version"),
            mutation(ctx, "publish_workflow", params(false), {}, {}, source.selected_version())).disable(!enabled);
      }
    }
  }
  void project_view(ui::Layout &layout, EditorContext &ctx)
  {
    auto &saved = *project_skills_;
    hint(layout, ctx, "skills.project.intro");
    if (!saved.supported()) { layout.paragraph(ctx.tr("skills.project.unavailable")); return; }
    const auto project_id = ctx.store.project().project()->id;
    if (restore_selection_ && saved_project_id_ == project_id && !saved_skill_id_.empty() && !saved.busy()) {
      saved.select(saved_skill_id_); restore_selection_ = false;
    }
    else if (saved_project_id_ != project_id) {
      restore_selection_ = false; saved_skill_id_.clear();
    }
    saved_project_id_ = project_id;
    if (!saved.selected_id().empty()) { saved_skill_id_ = saved.selected_id(); }
    saved.ensure_loaded();
    auto &actions = layout.row();
    actions.button("project_skills_refresh", ctx.tr("skills.refresh"), [&saved] { saved.refresh(); }).disable(saved.busy() || saved.uncertain());
    if (saved.uncertain()) {
      actions.button("project_skills_check", ctx.tr("skills.project.check"), [&saved] { saved.check_pending(); }).disable(saved.busy());
      layout.paragraph(ctx.tr("skills.project.uncertain"));
    }
    if (saved.busy()) { layout.label(ctx.tr("skills.loading")); }
    if (!saved.error().empty()) { layout.paragraph(saved.error()); }
    if (!saved.notice().empty()) { layout.paragraph(ctx.tr(saved.notice())); }
    publish_analysis(layout, ctx);
    publish_workflow(layout, ctx);
    const auto &page = saved.page();
    if (page.is_object()) {
      const auto &items = page.at("skills");
      if (items.empty()) { layout.paragraph(ctx.tr("skills.project.empty")); }
      else {
        ui::ListSpec spec;
        spec.count = int(items.size()); spec.rows = std::min(6.0f, float(items.size()));
        const auto epoch = saved.epoch();
        spec.text = [items](int i) {
          if (i < 0 || size_t(i) >= items.size()) { return std::string(); }
          const auto &item = items[size_t(i)];
          return io::get_string(item, "name") + " · " + io::get_string(member(item, "active"), "ref");
        };
        spec.selected = {[items, &saved] {
          for (size_t i = 0; i < items.size(); ++i) {
            if (io::get_string(items[i], "id") == saved.selected_id()) { return int(i); }
          }
          return -1;
        }, [items, &saved, epoch](int i) {
          saved.sync();
          if (saved.epoch() == epoch && i >= 0 && size_t(i) < items.size()) { saved.select(io::get_string(items[size_t(i)], "id")); }
        }};
        layout.virtual_list("project_skills_list", std::move(spec)).disable(saved.busy() || saved.uncertain());
      }
      const auto offset = io::get_int(page, "offset", 0);
      auto &pages = layout.row();
      pages.button("project_skills_previous", ctx.tr("skills.previous"), [&saved, offset] { saved.load_page(std::max(int64_t(0), offset - 50)); })
          .disable(saved.busy() || saved.uncertain() || offset == 0);
      pages.button("project_skills_next", ctx.tr("skills.next"), [&saved, offset] { saved.load_page(offset + 50); })
          .disable(saved.busy() || saved.uncertain() || offset + int64_t(items.size()) >= io::get_int(page, "total", 0));
    }
    if (!saved.selected().is_object()) { return; }
    const auto &item = saved.selected();
    if (io::get_string(item, "state") != "readable") { layout.paragraph(io::get_string(item, "error")); return; }
    const auto &active = item.at("active");
    layout.label(skill_text(active.at("title"), ctx.store.language()));
    layout.label(io::get_string(active, "ref"));
    layout.paragraph(ctx.store.catalog().format("skills.content_hash", {{"hash", io::get_string(active, "content_sha256")}}));
    const io::Json *workflow_template = nullptr;
    for (const auto &snapshot : item.at("document").at("versions")) {
      if (snapshot.at("content_sha256") != active.at("content_sha256")) { continue; }
      const auto &definition = snapshot.at("definition");
      const auto &templ = snapshot.at("template");
      const bool workflow = io::get_string(definition.at("entry"), "kind") == "workflow.document";
      if (workflow) { workflow_template = &templ; }
      layout.paragraph(skill_text(definition.at("summary"), ctx.store.language()));
      if (auto *contract = layout.panel("project_skill_contract", ctx.tr("skills.project.contract"), false)) {
        if (workflow) {
          const auto &document = templ.at("workflows").at(templ.at("root").get<std::string>()).at("document");
          const auto &interface = member(document, "interface");
          for (const auto *section : {"inputs", "parameters", "outputs"}) {
            contract->label(ctx.tr(std::string("skills.") + section));
            const auto &ports = member(interface, section);
            for (auto it = ports.begin(); it != ports.end(); ++it) {
              contract->label((ports.is_object() ? it.key() : io::get_string(*it, "name")) + " · " + io::get_string(*it, "type"));
            }
          }
          contract->paragraph(ctx.store.catalog().format("skills.project.workflow_closure", {
              {"workflows", std::to_string(templ.at("workflows").size())},
              {"analyses", std::to_string(templ.at("analyses").size())}}));
        }
        else {
          contract->label(ctx.tr("skills.inputs"));
          for (const auto &binding : templ.at("bindings")) { contract->label(io::get_string(binding, "name")); }
          contract->label(ctx.tr("skills.parameters"));
          const auto &graph = templ.at("graph");
          for (const auto &parameter : member(graph, "parameters")) { contract->label(io::get_string(parameter, "name")); }
          contract->label(ctx.tr("skills.outputs"));
          if (templ.contains("outputs")) { contract->paragraph(joined(templ.at("outputs"), "—")); }
          else { for (const auto &output : graph.at("outputs").items()) { contract->label(output.key()); } }
        }
      }
      break;
    }
    const bool enabled = writable(ctx) && saved.current();
    publish_global(layout, ctx);
    if (auto *versions = layout.panel("project_skills_versions", ctx.tr("skills.project.versions"), true)) {
      for (const auto &version : item.at("versions")) {
        const auto digest = io::get_string(version, "content_sha256");
        auto &row = versions->row();
        row.label(io::get_string(version, "ref"));
        row.button("project_skill_restore_" + digest, ctx.tr("skills.project.restore"), mutation(ctx, "restore",
            {{"project_skill_id", saved.selected_id()}, {"content_sha256", digest}, {"expected_revision", saved.revision()}}))
            .disable(!enabled || version.at("content_sha256") == active.at("content_sha256"));
      }
    }
    const auto &candidate = ctx.store.skills().detail();
    int64_t latest = 0;
    for (const auto &version : item.at("versions")) { latest = std::max(latest, io::get_int(version, "version", 0)); }
    if (io::get_string(candidate, "id") == io::get_string(active, "skill_id") && io::get_int(candidate, "version", 0) > latest) {
      layout.paragraph(ctx.store.catalog().format("skills.project.upgrade_to", {{"ref", io::get_string(candidate, "ref")},
          {"hash", io::get_string(candidate, "content_sha256")}}));
      layout.button("project_skill_upgrade", ctx.tr("skills.project.upgrade"), mutation(ctx, "upgrade",
          {{"project_skill_id", saved.selected_id()}, {"version", candidate.at("version")},
           {"content_sha256", candidate.at("content_sha256")}, {"expected_revision", saved.revision()}},
          io::get_string(candidate, "ref"), io::get_string(candidate, "content_sha256"))).disable(!enabled);
    }
    if (workflow_template) { workflow_instance(layout, ctx, *workflow_template, enabled); }
    else {
      layout.button("project_skill_create_analysis", ctx.tr("skills.project.create_analysis"), mutation(ctx, "create_analysis",
          {{"project_skill_id", saved.selected_id()}, {"content_sha256", active.at("content_sha256")},
           {"analysis_id", ProjectSkills::new_id()}, {"name", item.at("name")}, {"expected_revision", saved.revision()}})).disable(!enabled);
    }
    if (!saved.analysis_id().empty()) {
      layout.paragraph(ctx.store.catalog().format("skills.project.analysis_created", {{"id", saved.analysis_id()}}));
      layout.button("project_skill_open_analysis", ctx.tr("skills.project.open_analysis"), editor_navigation_action(ctx, kEditorAnalysisGraph));
    }
  }
  void workflow_instance(ui::Layout &layout, EditorContext &ctx, const io::Json &templ, bool enabled)
  {
    auto &saved = *project_skills_;
    const auto &item = saved.selected();
    const auto digest = io::get_string(item.at("active"), "content_sha256");
    const auto &dependencies = templ.at("dependencies");
    const auto project_id = ctx.store.project().project()->id;
    const auto key = project_id + ":" + saved.selected_id() + ":" + digest;
    if (!binding_drafts_.count(key)) {
      io::Json bindings = io::Json::object();
      const bool same_project = io::get_string(templ.at("source"), "project_id") == project_id;
      for (const auto *kind : {"tables", "fields", "snapshots"}) {
        bindings[kind] = io::Json::object();
        for (const auto &[id, dependency] : dependencies.at(kind).items()) {
          bindings[kind][id] = same_project ? id : std::string();
        }
      }
      // Refuse a new draft if restoring many old versions exhausted the workspace budget.
      auto candidate = binding_drafts_;
      candidate[key] = bindings.dump(2);
      if (candidate[key].size() > kBindingTextBytes || io::Json(candidate).dump().size() > kBindingDraftBytes) {
        layout.paragraph(ctx.tr("skills.project.bindings_full")); return;
      }
      binding_drafts_ = std::move(candidate);
    }
    layout.paragraph(ctx.tr("skills.project.workflow_create_hint"));
    const auto cache_key = key + ":" + std::to_string(saved.epoch());
    if (auto *details = layout.panel("project_skill_workflow_dependencies", ctx.tr("skills.project.workflow_dependencies"), false)) {
      if (dependency_cache_key_ != cache_key) {
        dependency_rows_.clear();
        for (const auto *kind : {"tables", "fields", "snapshots"}) {
          auto rows = std::make_shared<std::vector<std::string>>();
          for (const auto &[id, dependency] : dependencies.at(kind).items()) {
            if (std::string(kind) == "snapshots") {
              rows->push_back(id + " · " + io::get_string(dependency, "sha256"));
              for (const auto &file : member(dependency, "files")) {
                rows->push_back(id + " · " + io::get_string(file, "name"));
              }
            }
            else {
              auto description = io::get_string(dependency, "name");
              if (std::string(kind) == "fields") {
                description += " · " + io::get_string(dependency, "type") + " · " + io::get_string(dependency, "unit") +
                    " · " + io::get_string(dependency, "table_id");
              }
              rows->push_back(id + " · " + description);
            }
          }
          dependency_rows_[kind] = std::move(rows);
        }
        dependency_cache_key_ = cache_key;
      }
      for (const auto *kind : {"tables", "fields", "snapshots"}) {
        details->label(ctx.tr(std::string("skills.project.dependency_") + kind));
        const auto rows = dependency_rows_.at(kind);
        if (rows->empty()) { details->label("—"); continue; }
        ui::ListSpec spec;
        spec.count = int(rows->size()); spec.rows = std::min(5.0f, float(rows->size()));
        spec.text = [rows](int i) { return i >= 0 && size_t(i) < rows->size() ? rows->at(size_t(i)) : std::string(); };
        spec.selected = {[] { return -1; }, [](int) {}};
        details->virtual_list(std::string("project_skill_dependencies_") + kind, std::move(spec));
      }
      details->label(ctx.tr("skills.dependencies"));
      details->paragraph(joined(member(templ, "templates"), "—"));
    }
    layout.label(ctx.tr("skills.project.workflow_bindings"));
    const auto weak = lifetime();
    ui::TextFieldOptions options;
    options.multiline = options.mono = true; options.visible_lines = 5; options.max_length = kBindingTextBytes;
    auto *binding_store = &ctx.store;
    const auto binding_handle = binding_store->project().project()->handle;
    const auto binding_epoch = saved.epoch();
    const auto binding_skill = saved.selected_id();
    const auto binding_current = [this, weak, key, binding_store, binding_handle, binding_epoch, binding_skill, project_id, digest] {
      if (weak.expired() || !binding_drafts_.count(key)) { return false; }
      const auto &project = binding_store->project().project();
      return project && project->id == project_id && project->handle == binding_handle &&
          project_skills_->epoch() == binding_epoch && project_skills_->selected_id() == binding_skill &&
          io::get_string(member(project_skills_->selected(), "active"), "content_sha256") == digest;
    };
    layout.text_field("project_skill_workflow_bindings", {
        [this, key, binding_current] { return binding_current() ? binding_drafts_.at(key) : std::string(); },
        [this, weak, key, binding_current](const std::string &text) {
          if (weak.expired()) { return; }
          project_skills_->sync();
          if (!binding_current() || text.size() > kBindingTextBytes) { return; }
          auto candidate = binding_drafts_; candidate[key] = text;
          if (io::Json(candidate).dump().size() > kBindingDraftBytes) { return; }
          if (binding_drafts_.at(key) != text) { binding_drafts_[key] = text; ++binding_version_; }
        }}, options).disable(saved.busy() || saved.uncertain());
    if (binding_cache_key_ != cache_key || binding_cache_version_ != binding_version_) {
      binding_cache_ = nullptr;
      try { binding_cache_ = parse_parameter_json(binding_drafts_.at(key)); }
      catch (const std::exception &) { /* Preserve the exact invalid draft until the user repairs it. */ }
      binding_cache_valid_ = binding_cache_.is_object() && binding_cache_.size() == 3;
      for (const auto *kind : {"tables", "fields", "snapshots"}) {
        const auto &mapping = member(binding_cache_, kind);
        binding_cache_valid_ = binding_cache_valid_ && mapping.is_object() && mapping.size() == dependencies.at(kind).size();
        for (const auto &[id, dependency] : dependencies.at(kind).items()) {
          binding_cache_valid_ = binding_cache_valid_ && mapping.contains(id) && mapping.at(id).is_string() &&
              canonical_uuid(mapping.at(id).get<std::string>());
        }
      }
      binding_cache_key_ = cache_key; binding_cache_version_ = binding_version_;
    }
    const auto &bindings = binding_cache_;
    const bool valid = binding_cache_valid_;
    if (!valid) { layout.paragraph(ctx.tr("skills.project.workflow_bindings_invalid")); }
    layout.button("project_skill_create_workflow", ctx.tr("skills.project.create_workflow"), mutation(ctx, "create_workflow",
        {{"project_skill_id", saved.selected_id()}, {"content_sha256", digest},
         {"workflow_id", ProjectSkills::new_id()}, {"name", item.at("name")}, {"bindings", bindings},
         {"expected_revision", saved.revision()}}, {}, {}, binding_version_))
        .disable(!enabled || !valid || !saved.can_create_workflow());
    if (!saved.workflow_id().empty()) {
      layout.paragraph(ctx.store.catalog().format("skills.project.workflow_created", {{"id", saved.workflow_id()}}));
      auto *area = &ctx.area;
      auto *shell = &area->shell();
      auto *store = &ctx.store;
      const auto shell_weak = shell->lifetime();
      const auto handle = store->project().project()->handle;
      const io::Json target = {{"workflow_id", saved.workflow_id()}, {"handle", handle}};
      const auto epoch = saved.epoch();
      const auto created = saved.workflow_id();
      auto guard = [this, weak, shell_weak, store, handle, epoch, created] {
        return !weak.expired() && !shell_weak.expired() && store->project().project() &&
            store->project().project()->handle == handle && project_skills_->epoch() == epoch &&
            project_skills_->workflow_id() == created;
      };
      layout.button("project_skill_open_workflow", ctx.tr("skills.project.open_workflow"), [shell, area, weak, target, guard] {
        if (guard()) { shell->open_in_area_later(area, weak, kEditorWorkflow, target, guard, true); }
      }).disable(shell->text_input_active());
    }
  }
  void rows(ui::Layout &layout, EditorContext &ctx, SkillCatalogState &skills, const float visible)
  {
    const auto &items = skills.skills();
    if (skills.loaded() && items.empty()) {
      layout.paragraph(ctx.tr("skills.empty"));
    }
    if (!items.empty()) {
      layout.label(ctx.store.catalog().format("skills.count", {
          {"from", std::to_string(skills.offset() + 1)},
          {"to", std::to_string(skills.offset() + int64_t(items.size()))},
          {"total", std::to_string(skills.total())}}));
      ui::ListSpec spec;
      spec.count = int(items.size());
      // Row text may be produced after this frame's context is gone: capture store-owned data only.
      const std::string language = ctx.store.language();
      const ui::Catalog *catalog = &ctx.store.catalog();
      spec.text = [catalog, &items, language](const int i) {
        if (i < 0 || size_t(i) >= items.size()) { return std::string(); }  // a reply replaced the rows
        const auto &row = items[size_t(i)];
        return skill_text(row.title, language) + "  ·  " + row.ref + "  ·  " +
            source_text(*catalog, row.source) + "  ·  " + kind_text(*catalog, row.entry_kind) + "  ·  " + status_text(*catalog, row.status);
      };
      spec.selected = {[&items, &skills] {
                         const auto found = std::find_if(items.begin(), items.end(), [&](const SkillSummary &row) {
                           return row.ref == skills.selected();
                         });
                         return found == items.end() ? -1 : int(found - items.begin());
                       },
                       [&items, &skills](const int i) {
                         if (i >= 0 && size_t(i) < items.size()) { skills.select(items[size_t(i)].ref); }
                       }};
      spec.rows = std::min(visible, float(items.size()));
      layout.virtual_list("skills_list", std::move(spec));
    }
    auto &pages = layout.row();
    pages.button("skills_previous", ctx.tr("skills.previous"), [&skills] { skills.previous_page(); })
        .disable(skills.offset() == 0 || skills.loading());
    pages.button("skills_next", ctx.tr("skills.next"), [&skills] { skills.next_page(); })
        .disable(!skills.has_next() || skills.loading());
  }

  static std::string bounded_default(const io::Json &value)
  {
    if (value.is_object()) { return "{…} (" + std::to_string(value.size()) + ")"; }
    if (value.is_array()) { return "[…] (" + std::to_string(value.size()) + ")"; }
    if (!value.is_string()) { return value.dump(); }
    const auto &text = value.get_ref<const std::string &>();
    size_t end = std::min(size_t(160), text.size());
    while (end > 0 && end < text.size() && (static_cast<unsigned char>(text[end]) & 0xc0) == 0x80) { --end; }
    return io::Json(text.substr(0, end)).dump() + (end < text.size() ? " …" : "");
  }
  static std::string source_text(const ui::Catalog &catalog, const std::string &source)
  {
    return source == "builtin" || source == "user" ? std::string(catalog.tr("skills.source." + source)) : source;
  }
  static std::string kind_text(const ui::Catalog &catalog, const std::string &kind)
  {
    return kind == "graph.preset" || kind == "graph.document" || kind == "workflow.document" ?
        std::string(catalog.tr("skills.kind." + kind)) : kind;
  }
  static std::string status_text(const ui::Catalog &catalog, const std::string &status)
  {
    if (status == "available" || status == "limited" || status == "unavailable" || status == "unchecked") {
      return std::string(catalog.tr("skills.status." + status));
    }
    return status;
  }

  void problems(ui::Layout &layout, EditorContext &ctx, const SkillCatalogState &skills)
  {
    const auto title = ctx.store.catalog().format("skills.problems", {{"count", std::to_string(skills.problem_count())}});
    if (auto *panel = layout.panel("skills_problems", title, false)) {
      for (const auto &problem : skills.problems()) {
        std::string line = io::get_string(problem, "file") + " · " + io::get_string(problem, "code");
        const auto path = io::get_string(problem, "path");
        if (!path.empty()) { line += " · " + path; }
        panel->label(line);
        panel->paragraph(io::get_string(problem, "message"));
      }
    }
  }

  void detail(ui::Layout &layout, EditorContext &ctx, const SkillCatalogState &skills)
  {
    const auto &skill = skills.detail();
    if (skills.selected().empty()) {
      layout.paragraph(ctx.tr("skills.select"));
      return;
    }
    if (skills.detail_loading()) { layout.label(ctx.tr("skills.detail_loading")); }
    if (!skills.detail_error().empty()) { layout.paragraph(skills.detail_error()); }
    if (!skill.is_object()) { return; }
    const std::string language = ctx.store.language();
    auto &catalog = ctx.store.catalog();
    auto &head = layout.box();
    head.label(skill_text(member(skill, "title"), language));
    head.label(io::get_string(skill, "ref"));
    head.label(source_text(catalog, io::get_string(skill, "source")) + " · " +
               kind_text(catalog, io::get_string(member(skill, "entry"), "kind")));
    head.paragraph(catalog.format("skills.content_hash", {{"hash", io::get_string(skill, "content_sha256")}}));
    head.paragraph(skill_text(member(skill, "summary"), language));
    if (project_skills_->supported()) {
      head.button("project_skill_pin", ctx.tr("skills.project.pin"), mutation(ctx, "pin",
          {{"skill_id", skill.at("id")}, {"version", skill.at("version")}, {"content_sha256", skill.at("content_sha256")},
           {"project_skill_id", ProjectSkills::new_id()}, {"expected_revision", project_skills_->revision()}},
          io::get_string(skill, "ref"), io::get_string(skill, "content_sha256")))
          .disable(!writable(ctx) || skills.detail_loading() || io::get_string(skill, "ref") != skills.selected());
    }

    const auto &availability = member(skill, "availability");
    auto &state = layout.box();
    state.label(catalog.format("skills.availability_line", {
        {"status", status_text(catalog, io::get_string(availability, "status"))}}));
    if (!member(availability, "unavailable_outputs").empty()) {
      state.paragraph(catalog.format("skills.unavailable_outputs", {
          {"outputs", joined(member(availability, "unavailable_outputs"), "")}}));
    }
    for (const auto &issue : member(availability, "issues")) {
      state.paragraph(io::get_string(issue, "code") + ": " + io::get_string(issue, "message"));
    }

    const auto &entry = member(skill, "entry");
    auto &run = layout.box();
    run.label(ctx.tr("skills.entry"));
    if (io::get_string(entry, "kind") == "graph.preset") {
      run.paragraph(catalog.format("skills.entry_text", {{"kind", io::get_string(entry, "kind")},
          {"preset", io::get_string(entry, "preset")}, {"operation", io::get_string(entry, "operation")}}));
      run.paragraph(ctx.tr("skills.run_hint"));
    }
    else { run.paragraph(ctx.tr("skills.user.use_hint")); }
    if (const auto &method = member(skill, "method"); method.is_object()) {
      run.paragraph(catalog.format("skills.project.workflow_closure", {
          {"workflows", std::to_string(io::get_int(method, "workflow_count", 0))},
          {"analyses", std::to_string(io::get_int(method, "analysis_count", 0))}}));
      const auto &data = member(method, "data_dependencies");
      run.paragraph(catalog.format("skills.user.data_dependencies", {
          {"tables", std::to_string(io::get_int(data, "tables", 0))},
          {"fields", std::to_string(io::get_int(data, "fields", 0))},
          {"snapshots", std::to_string(io::get_int(data, "snapshots", 0))}}));
    }
    const auto &guide = member(skill, "guide");
    run.paragraph(guide.is_object() ? catalog.format("skills.guide", {{"pack", io::get_string(guide, "pack")}}) :
                                      std::string(ctx.tr("skills.no_guide")));

    if (auto *panel = layout.panel("skills_inputs", ctx.tr("skills.inputs"), true)) {
      for (const auto &input : member(skill, "inputs")) {
        const auto kind = io::get_string(input, "kind");
        panel->label(io::get_string(input, "name") + " (" + (kind == "binding" ? std::string(ctx.tr("skills.binding")) : kind) + ")");
        panel->paragraph(io::get_string(input, "description"));
      }
    }
    if (auto *panel = layout.panel("skills_parameters", ctx.tr("skills.parameters"), true)) {
      for (const auto &parameter : member(skill, "parameters")) {
        std::string line = io::get_string(parameter, "name") + " : " + io::get_string(parameter, "type");
        const auto &fallback = member(parameter, "default");
        if (parameter.is_object() && parameter.contains("default")) {
          const auto cache_key = io::get_string(skill, "ref") + ":" + io::get_string(skill, "content_sha256");
          if (default_cache_key_ != cache_key) { default_cache_key_ = cache_key; default_previews_.clear(); }
          const auto name = io::get_string(parameter, "name");
          if (!default_previews_.count(name)) { default_previews_[name] = bounded_default(fallback); }
          line += " = " + default_previews_.at(name);
        }
        panel->label(line);
        const auto label = io::get_string(parameter, "label"), description = io::get_string(parameter, "description");
        if (!label.empty() || !description.empty()) {
          panel->paragraph(label + (label.empty() || description.empty() ? "" : " — ") + description);
        }
      }
    }
    if (auto *panel = layout.panel("skills_outputs", ctx.tr("skills.outputs"), true)) {
      for (const auto &output : member(skill, "outputs")) {
        const auto &kind = member(output, "type");
        panel->label(io::get_string(output, "name") + " : " + (kind.is_string() ? kind.get<std::string>() : "?") +
                     "  ←  " + io::get_string(output, "from"));
      }
    }
    if (auto *panel = layout.panel("skills_dependencies", ctx.tr("skills.dependencies"), true)) {
      const auto &dependencies = member(skill, "dependencies");
      const auto &nodes = member(dependencies, "nodes");
      int64_t installed = 0;
      for (const auto &node : nodes) {
        if (io::get_bool(node, "available", false)) { ++installed; }
      }
      panel->label(catalog.format("skills.nodes", {{"available", std::to_string(installed)},
                                                   {"total", std::to_string(nodes.is_array() ? nodes.size() : 0)}}));
      for (const auto &node : nodes) {
        if (!io::get_bool(node, "available", false)) {
          panel->paragraph(catalog.format("skills.node_missing", {{"type", io::get_string(node, "type")}}));
        }
      }
      for (const auto &module : member(dependencies, "python")) {
        const auto scope = joined(member(module, "outputs"), std::string(ctx.tr("skills.all_outputs")));
        panel->label(catalog.format(io::get_bool(module, "available", false) ? "skills.module_ok" : "skills.module_missing",
                                    {{"module", io::get_string(module, "module")}, {"outputs", scope}}));
        panel->paragraph(skill_text(member(module, "purpose"), language));
      }
      for (const auto &capability : member(dependencies, "runtime")) {
        panel->label(catalog.format("skills.not_checked", {
            {"capability", io::get_string(capability, "capability")},
            {"outputs", joined(member(capability, "outputs"), std::string(ctx.tr("skills.all_outputs")))}}));
        panel->paragraph(skill_text(member(capability, "purpose"), language));
      }
    }
    if (auto *panel = layout.panel("skills_examples", ctx.tr("skills.examples"), true)) {
      for (const auto &example : member(skill, "examples")) {
        panel->label(skill_text(member(example, "title"), language));
        const auto &parameters = member(example, "parameters");
        panel->paragraph(catalog.format("skills.example_text", {
            {"parameters", parameters.is_object() ? parameters.dump() : std::string("{}")},
            {"outputs", joined(member(example, "outputs"), std::string(ctx.tr("skills.all_outputs")))}}));
      }
    }
  }

  std::string query_, default_cache_key_;
  std::map<std::string, std::string> default_previews_;
  std::unique_ptr<ProjectSkills> project_skills_;
  std::unique_ptr<ProjectAnalyses> analysis_source_;
  std::string source_selected_id_;
  std::unique_ptr<ProjectWorkflows> workflow_source_;
  std::string workflow_source_selected_id_;
  uint64_t workflow_source_epoch_ = 0, binding_version_ = 0;
  int64_t workflow_source_page_revision_ = -1, workflow_source_detail_revision_ = -1;
  std::map<std::string, std::string> binding_drafts_;
  std::string dependency_cache_key_, binding_cache_key_;
  std::map<std::string, std::shared_ptr<const std::vector<std::string>>> dependency_rows_;
  io::Json binding_cache_;
  uint64_t binding_cache_version_ = 0;
  bool binding_cache_valid_ = false;
  uint64_t source_epoch_ = 0;
  int64_t source_page_revision_ = -1, source_detail_revision_ = -1;
  bool project_view_ = false, restore_selection_ = false;
  std::string saved_project_id_, saved_skill_id_;
};

}  // namespace
std::unique_ptr<Editor> make_skills_editor(const EditorType &type)
{
  return std::make_unique<SkillsEditor>(type);
}
}  // namespace stk::app
