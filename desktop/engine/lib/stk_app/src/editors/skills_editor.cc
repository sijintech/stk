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
#include "stk/app/analysis_document.hh"
#include "editor_text.hh"

#include <algorithm>

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
    return {{"version", 1}, {"query", query_}, {"project_view", project_view_},
            {"project_id", saved_project_id_}, {"selected_id", saved_skill_id_}};
  }
  bool load_workspace_state(const nlohmann::json &value) override
  {
    if (!workspace_fields(value, {"query", "project_id", "selected_id"}, {}, {"project_view"}, {}, 65536)) { return false; }
    const auto project = value.value("project_id", std::string());
    const auto selected = value.value("selected_id", std::string());
    if ((!project.empty() && !canonical_uuid(project)) || (!selected.empty() && !canonical_uuid(selected))) { return false; }
    query_ = value.value("query", std::string());
    project_view_ = value.value("project_view", false);
    saved_project_id_ = project; saved_skill_id_ = selected;
    restore_selection_ = true; return true;
  }

 private:
  bool writable(EditorContext &ctx) const
  {
    return project_skills_ && project_skills_->supported() && !project_skills_->busy() &&
        !project_skills_->uncertain() && !ctx.store.project().busy() &&
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
      if (project_skills_->write(action, params, epoch)) { project_view_ = true; }
    };
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
        layout.virtual_list("project_skills_list", std::move(spec));
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
    for (const auto &snapshot : item.at("document").at("versions")) {
      if (snapshot.at("content_sha256") != active.at("content_sha256")) { continue; }
      const auto &definition = snapshot.at("definition");
      const auto &templ = snapshot.at("template");
      layout.paragraph(skill_text(definition.at("summary"), ctx.store.language()));
      if (auto *contract = layout.panel("project_skill_contract", ctx.tr("skills.project.contract"), false)) {
        contract->label(ctx.tr("skills.inputs"));
        for (const auto &binding : templ.at("bindings")) { contract->label(io::get_string(binding, "name")); }
        contract->label(ctx.tr("skills.parameters"));
        const auto &graph = templ.at("graph");
        for (const auto &parameter : member(graph, "parameters")) { contract->label(io::get_string(parameter, "name")); }
        contract->label(ctx.tr("skills.outputs"));
        if (templ.contains("outputs")) { contract->paragraph(joined(templ.at("outputs"), "—")); }
        else { for (const auto &output : graph.at("outputs").items()) { contract->label(output.key()); } }
      }
      break;
    }
    const bool enabled = writable(ctx) && saved.current();
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
    layout.button("project_skill_create_analysis", ctx.tr("skills.project.create_analysis"), mutation(ctx, "create_analysis",
        {{"project_skill_id", saved.selected_id()}, {"content_sha256", active.at("content_sha256")},
         {"analysis_id", ProjectSkills::new_id()}, {"name", item.at("name")}, {"expected_revision", saved.revision()}})).disable(!enabled);
    if (!saved.analysis_id().empty()) {
      layout.paragraph(ctx.store.catalog().format("skills.project.analysis_created", {{"id", saved.analysis_id()}}));
      layout.button("project_skill_open_analysis", ctx.tr("skills.project.open_analysis"), editor_navigation_action(ctx, kEditorAnalysisGraph));
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
        return skill_text(row.title, language) + "  ·  " + row.ref + "  ·  " + status_text(*catalog, row.status);
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

  static std::string status_text(const ui::Catalog &catalog, const std::string &status)
  {
    if (status == "available" || status == "limited" || status == "unavailable") {
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
    run.paragraph(catalog.format("skills.entry_text", {{"kind", io::get_string(entry, "kind")},
                                                       {"preset", io::get_string(entry, "preset")},
                                                       {"operation", io::get_string(entry, "operation")}}));
    run.paragraph(ctx.tr("skills.run_hint"));
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
        if (parameter.is_object() && parameter.contains("default")) { line += " = " + fallback.dump(); }
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

  std::string query_;
  std::unique_ptr<ProjectSkills> project_skills_;
  std::unique_ptr<ProjectAnalyses> analysis_source_;
  std::string source_selected_id_;
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
