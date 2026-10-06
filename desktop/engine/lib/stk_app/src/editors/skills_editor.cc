/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Skills editor: read-only browsing of the versioned skill catalog (skills.list / skills.get).
 * It shows each skill's identity, entry, inputs, parameters, outputs, dependencies, availability
 * and examples. Nothing here runs a skill, prepares a run, changes a project or calls a model.
 */
#include "project_navigation.hh"

#include "stk/app/skill_catalog.hh"
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
    auto &top = layout.row();
    workspace_link(top, ctx);
    top.label(ctx.tr("skills.title"));
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

 private:
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
};

}  // namespace
std::unique_ptr<Editor> make_skills_editor(const EditorType &type)
{
  return std::make_unique<SkillsEditor>(type);
}
}  // namespace stk::app
