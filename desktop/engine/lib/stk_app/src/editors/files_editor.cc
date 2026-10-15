/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_file_tree.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/app/viewer_state.hh"
#include "project_navigation.hh"
#include <algorithm>
#include <cctype>

namespace stk::app {
namespace {
using io::Json;
class FilesEditor final : public Editor {
 public:
  explicit FilesEditor(const EditorType &type) : Editor(type) {}
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &) override
  {
    if (!target.is_object() || io::get_string(target, "record_id").empty() ||
        io::get_string(target, "project_handle").empty() || !target.contains("expected_revision") ||
        !target.at("expected_revision").is_number_integer() || io::get_int(target, "expected_revision", -1) < 0) { return false; }
    pending_record_ = io::get_string(target, "record_id");
    pending_handle_ = io::get_string(target, "project_handle");
    pending_revision_ = io::get_int(target, "expected_revision", -1);
    navigation_error_.clear();
    return true;
  }
  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx); attach(ctx);
    const auto weak = lifetime();
    row.button("files_refresh", ctx.tr("files.refresh"), [this, weak] {
      if (!weak.expired()) { tree_->refresh(); }
    }).width(ctx.draw && ctx.ui ? std::min(4.0f, float(ctx.draw->rect.width()) / ctx.ui->style().unit * .35f) : 4.0f)
      .disable(!tree_->supported() || tree_->busy());
  }
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx);
    auto &project = ctx.store.project();
    if (!project.project()) {
      layout.paragraph(ctx.tr("files.no_project"));
      layout.button("files_project", ctx.tr("workspace.open_project_button"), project_navigation_action(ctx, "project"));
      return;
    }
    layout.label(project.project()->name);
    layout.paragraph(project.project()->directory);
    if (!tree_->supported()) { layout.paragraph(ctx.tr("files.unsupported")); return; }
    if (!tree_->loaded() && !tree_->busy() && tree_->error().empty()) { tree_->refresh(); }
    if (!pending_record_.empty() && project.loaded()) {
      if (pending_handle_ != project.project()->handle || pending_revision_ != project.project()->revision ||
          !tree_->select_record(pending_record_)) { navigation_error_ = std::string(ctx.tr("files.record_missing")); }
      pending_record_.clear();
    }
    if (tree_->busy()) { layout.label(ctx.tr("files.loading")); }
    if (!tree_->error().empty()) { layout.paragraph(tree_->error()); }
    if (!navigation_error_.empty()) { layout.paragraph(navigation_error_); }
    layout.paragraph(ctx.tr("files.intro"));
    std::vector<Json> rows;
    flatten("", 0, rows);
    const auto version = tree_->version();
    const auto weak = lifetime();
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("files.name")), 20}, {std::string(ctx.tr("files.status")), 12}};
    spec.rows = int(rows.size()); spec.visible_rows = float(std::min(18, std::max(1, spec.rows)));
    spec.data_version = version;
    std::vector<std::vector<std::string>> cells;
    int selected = -1;
    for (size_t i = 0; i < rows.size(); ++i) {
      const auto &entry = rows[i];
      const auto path = io::get_string(entry, "path"), kind = io::get_string(entry, "kind");
      const auto name = std::string(size_t(io::get_int(entry, "depth", 0)) * 2, ' ') +
          (kind == "directory" ? (tree_->expanded(path) ? "▾ " : "▸ ") : "  ") + io::get_string(entry, "name");
      const auto state = io::get_string(entry, "state");
      std::string status(ctx.tr(io::get_bool(entry, "registered", false) ? "files.registered" : "files.unregistered"));
      if (state != "present") { status += " · " + std::string(ctx.tr("files." + state)); }
      else if (kind == "link" || kind == "other") { status += " · " + std::string(ctx.tr("files." + kind)); }
      cells.push_back({name, status});
      if (!io::get_bool(tree_->selected(), "index_only", false) && io::get_string(tree_->selected(), "path") == path) { selected = int(i); }
    }
    spec.cell = [cells](int row, int column) { return cells.at(size_t(row)).at(size_t(column)); };
    spec.selected = {[selected] { return selected; }, [this, weak, version, rows](int row) {
      if (!weak.expired() && tree_->version() == version && row >= 0 && size_t(row) < rows.size()) { tree_->select(rows[size_t(row)]); }
    }};
    layout.table("files_tree", std::move(spec));
    if (rows.empty() && tree_->loaded()) { layout.label(ctx.tr("files.empty")); }
    const auto item = tree_->selected();
    const auto selected_path = io::get_string(item, "path");
    const bool directory = io::get_string(item, "kind") == "directory" && !io::get_bool(item, "index_only", false);
    auto &actions = layout.row();
    actions.button("files_toggle", ctx.tr(tree_->expanded(selected_path) ? "files.collapse" : "files.expand"),
        [this, weak, version, selected_path] {
          if (!weak.expired() && tree_->version() == version) { tree_->toggle(selected_path); }
        }).disable(tree_->busy() || !directory);
    const auto slash = selected_path.rfind('/');
    const auto page = directory ? selected_path : slash == std::string::npos ? std::string() : selected_path.substr(0, slash);
    const auto found = tree_->pages().find(page);
    const bool more = found != tree_->pages().end() && found->second.contains("next_offset") && !found->second.at("next_offset").is_null();
    actions.button("files_more", ctx.tr("files.more"), [this, weak, version, page] {
      if (!weak.expired() && tree_->version() == version) { tree_->more(page); }
    }).disable(tree_->busy() || !more);
    for (const auto &[path, value] : tree_->pages()) {
      if (io::get_bool(value, "truncated", false)) { layout.paragraph(ctx.tr("files.limit")); break; }
    }
    registrations(layout, ctx);
    details(layout, ctx);
  }
 private:
  void attach(EditorContext &ctx)
  {
    ctx.store.project().sync();
    if (!tree_) {
      const auto shell = ctx.area.shell().lifetime();
      tree_ = std::make_unique<ProjectFileTree>(ctx.store, [shell] { return !shell.expired(); });
    }
    tree_->sync();
  }
  void flatten(const std::string &path, const int depth, std::vector<Json> &rows) const
  {
    const auto found = tree_->pages().find(path);
    if (found == tree_->pages().end() || depth > 32) { return; }
    for (auto item : found->second.at("entries")) {
      if (rows.size() >= 8192) { return; }
      item["depth"] = depth; rows.push_back(item);
      const auto child = io::get_string(item, "path");
      if (io::get_string(item, "kind") == "directory" && tree_->expanded(child)) { flatten(child, depth + 1, rows); }
    }
  }
  void registrations(ui::Layout &layout, EditorContext &ctx)
  {
    const auto found = tree_->pages().find("");
    auto *panel = layout.panel("files_registered", ctx.tr("files.index_title"), false);
    if (!panel || found == tree_->pages().end()) { return; }
    panel->paragraph(ctx.tr("files.index_hint"));
    const auto rows = found->second.at("registrations");
    if (io::get_bool(found->second, "registrations_truncated", false)) { panel->paragraph(ctx.tr("files.index_limit")); }
    ui::TableSpec spec; spec.rows = int(rows.size()); spec.visible_rows = float(std::min(6, std::max(1, spec.rows)));
    spec.columns = {{std::string(ctx.tr("files.name")), 15}, {std::string(ctx.tr("files.status")), 12}};
    std::vector<std::vector<std::string>> cells;
    for (const auto &row : rows) {
      const auto location = io::get_string(row, "location");
      cells.push_back({io::get_string(row, "name"), std::string(ctx.tr(location == "project" ? "files.registered" : "files.external")) +
          " · " + io::get_string(row, "state")});
    }
    const auto weak = lifetime(); const auto version = tree_->version(); spec.data_version = version;
    spec.cell = [cells](int row, int column) { return cells.at(size_t(row)).at(size_t(column)); };
    spec.selected = {[] { return -1; }, [this, weak, version, rows](int row) {
      if (!weak.expired() && tree_->version() == version && row >= 0 && size_t(row) < rows.size()) { tree_->select_record(io::get_string(rows[size_t(row)], "id")); }
    }};
    panel->table("files_registrations", std::move(spec));
  }
  void details(ui::Layout &layout, EditorContext &ctx)
  {
    const auto item = tree_->selected(); if (!item.is_object()) { return; }
    layout.label(ctx.tr("files.selected"));
    layout.paragraph(io::get_string(item, "path"));
    const bool indexed = io::get_bool(item, "index_only", false);
    if (indexed) {
      layout.paragraph(ctx.tr("files.index_hint"));
      layout.paragraph(io::get_string(item, "location") + " · " + io::get_string(item, "state"));
    }
    const auto kind = io::get_string(item, "kind");
    const bool blocked = tree_->busy() || kind == "link" || kind == "other" || (!indexed && io::get_string(item, "state") != "present");
    auto extension = io::get_string(item, "path");
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    const bool python = extension.size() >= 3 && extension.substr(extension.size() - 3) == ".py" && kind != "directory";
    const auto weak = lifetime(); const auto version = tree_->version();
    auto *shell = &ctx.area.shell(); auto *area = &ctx.area;
    auto *store = &ctx.store;
    const auto handle = store->project().project()->handle;
    const auto revision = store->project().project()->revision;
    const auto shell_lifetime = shell->lifetime();
    const auto valid = [this, weak, shell_lifetime, shell, area, store, handle, revision, item] {
      if (weak.expired() || shell_lifetime.expired() || !shell->has_area(area) || &area->editor() != this) { return false; }
      auto &project = store->project(); project.sync(); tree_->sync();
      return project.loaded() && !project.busy() && project.project() &&
          project.project()->handle == handle && project.project()->revision == revision && tree_->selected() == item;
    };
    auto *screen = ctx.area.screen();
    layout.button("files_open_code", ctx.tr("files.open_code"), [this, version, shell, screen, valid] {
      if (!valid() || tree_->version() != version) { return; }
      tree_->resolve([shell, screen, valid](const std::string &path) {
        if (valid()) { shell->open_target_later(screen, kEditorPython, {{"path", path}}, valid); }
      });
    }).disable(blocked || !python);
    auto &viewer = ctx.store.viewer(); viewer.refresh_metadata();
    std::vector<std::string> names{std::string(ctx.tr("files.automatic"))}, ids{std::string()};
    for (const auto &preset : viewer.presets()) { names.push_back(preset.name); ids.push_back(preset.id); }
    layout.dropdown("files_preset", std::move(names), {[this, ids] {
      const auto it = std::find(ids.begin(), ids.end(), preset_); return it == ids.end() ? 0 : int(it - ids.begin());
    }, [this, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { preset_ = ids[size_t(i)]; } }});
    const auto viewer_version = viewer.version();
    layout.button("files_open_viewer", ctx.tr("files.open_viewer"), [this, version, store, screen, valid, viewer_version, preset = preset_] {
      if (!valid() || !screen || tree_->version() != version || store->viewer().version() != viewer_version) { return; }
      tree_->resolve([store, screen, preset, valid, viewer_version](const std::string &path) {
        if (!valid()) { return; }
        screen->defer([store, preset, path, valid, viewer_version] {
          if (!valid() || store->viewer().version() != viewer_version || store->has_open_result()) { return; }
          OpenResultRequest request; request.local_paths = {path}; request.preset = preset; store->request_open_result(std::move(request));
        });
      });
    }).disable(blocked || python);
  }
  std::unique_ptr<ProjectFileTree> tree_;
  std::string pending_record_, pending_handle_, navigation_error_, preset_;
  int64_t pending_revision_ = -1;
};
}  // namespace
std::unique_ptr<Editor> make_files_editor(const EditorType &type) { return std::make_unique<FilesEditor>(type); }
}  // namespace stk::app
