/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_table_editor.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/platform/file_dialog.hh"
#include "archive_controls.hh"
#include "stk/app/project_data_labels.hh"
#include "project_review_view.hh"
#include "project_discussion_view.hh"
#include "project_simulation_view.hh"
#include "project_navigation.hh"
#include "path_picker.hh"
#include "project_labels.hh"
#include "editor_text.hh"

#include <algorithm>
#include <filesystem>
#include <unordered_map>

namespace stk::app {
namespace {

using io::Json;

class ProjectEditor final : public Editor {
 public:
  explicit ProjectEditor(const EditorType &type) : Editor(type) {}

  bool show_view(const std::string_view view) override
  {
    if (view != "review" && view != "data" && view != "discussion" && view != "files" && view != "runs" && view != "location") { return false; }
    project_view_ = view == "review" ? 1 : view == "discussion" ? 2 : view == "files" ? 3 : view == "runs" ? 4 : view == "location" ? 5 : 0;
    return true;
  }
  bool can_change_project_selection(const std::string_view project_id) const override
  {
    return tables_.can_change_project_selection(project_id);
  }
  bool has_unsaved_changes() const override { return tables_.has_unsaved_changes(); }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    workspace_link(row, ctx);
    auto &state = ctx.store.project();
    state.sync();
    row.button("project_ai", ctx.tr("editor.ai.title"), [ctx] {
      ctx.defer([area = &ctx.area] {
        for (int i = 0; i < area->tab_count(); ++i) {
          if (area->tab(i).type().id == kEditorAI) { area->set_active_tab(i); return; }
        }
        area->add_tab(kEditorAI);
      });
    }).width(7);
    row.button("project_refresh", ctx.tr("project.refresh"), [&state] { state.refresh(); })
        .width(5)
        .disable(!state.ready() || !state.project() || state.busy());
    row.button("project_close", ctx.tr("project.close"), [&state] { state.close(); })
        .width(9)
        .disable(!state.project() || state.busy());
    row.button("project_undo", ctx.tr("project.undo"), [&state] { state.undo(); })
        .width(4).disable(!state.ready() || state.busy() || !state.can_undo());
    row.button("project_redo", ctx.tr("project.redo"), [&state] { state.redo(); })
        .width(4).disable(!state.ready() || state.busy() || !state.can_redo());
  }

  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    if (!state.ready()) {
      layout.paragraph(ctx.tr("project.bridge_required"));
    }
    if (!state.error().empty()) {
      layout.paragraph(state.error());
    }
    if (!state.notice().empty()) {
      layout.paragraph(state.notice());
    }
    if (state.busy()) {
      layout.label(ctx.tr("project.busy"));
    }
    const bool location_only = project_view_ == 5;
    if (location_only) { layout.label(ctx.tr("project.location")); }
    if (auto *panel = location_only ? &layout.scope("project_location") :
        layout.panel("project_location", ctx.tr("project.location"), !state.project())) {
      auto &location = panel->prop(ctx.tr("project.directory")).row(true);
      location.text_field("directory", ui::bind(directory_));
      directory_picker_.button(location, ctx, "browse_directory", &directory_,
                               {.mode = platform::FileDialogMode::OpenFolder, .title_key = "project.directory_dialog"});
      directory_picker_.draw_error(*panel);
      panel->prop(ctx.tr("project.name")).text_field("name", ui::bind(name_));
      auto &buttons = panel->row();
      buttons.button("open", ctx.tr("project.open"), [this, &state] {
        state.open(path());
      }).disable(!state.ready() || state.busy() || directory_.empty());
      buttons.button("create", ctx.tr("project.create"), [this, &state] {
        state.create(path(), name_);
      }).disable(!state.ready() || state.busy() || directory_.empty() || name_.empty());
    }
    recent_controls(layout, ctx, state);
    if (location_only) { return; }
    if (!state.project()) {
      layout.paragraph(ctx.tr("project.intro"));
      return;
    }
    layout.label(state.project()->name);
    layout.paragraph(state.project()->directory);
    layout.label(ctx.store.catalog().format("project.revision", {{"revision", std::to_string(state.project()->revision)}}));
    if (!state.loaded()) {
      return;
    }
    const bool editable = state.ready() && !state.busy();
    if (project_view_ == 3) {
      layout.label(ctx.tr("project.files.title"));
      file_controls(layout, ctx, state, editable, true);
      if (state.table() && state.table_id() == io::get_string(state.file_index(), "table_id")) {
        tables_.grid(layout, ctx, state);
        if (tables_.selected_visible(state)) { tables_.cell(layout, ctx, state, editable, [this] { project_view_ = 1; }); }
      }
      return;
    }
    if (project_view_ == 4) {
      layout.label(ctx.tr("project.runs.title"));
      run_controls(layout, ctx, state, editable, true);
      return;
    }
    if (state.project()->format_version < kProjectFormatVersion) {
      hint(layout, ctx, "project.upgrade_hint");
      layout.button("upgrade_project", ctx.tr("project.upgrade"), [&state] { state.upgrade(); }).disable(!editable);
    }
    layout.tabs("project_view", {std::string(ctx.tr("project.review.data")), std::string(ctx.tr("project.review.title")),
                               std::string(ctx.tr("discussion.title"))},
                ui::bind(project_view_));
    if (project_view_ == 1) {
      review_view_.draw(layout, ctx, state);
      return;
    }
    if (project_view_ == 2) {
      discussion_view_.draw(layout, ctx, state, project_view_);
      return;
    }
    if (auto *panel = layout.panel("project_backup", ctx.tr("project.backup_title"), false)) {
      panel->paragraph(ctx.tr("project.backup_hint"));
      panel->button("backup", ctx.tr("project.backup"), [&state] { state.backup(); }).disable(!editable);
    }
    simulation_view_.draw(layout, ctx, state);
    simulation_view_.draw_pet_studies(layout, ctx, state);
    simulation_view_.draw_batches(layout, ctx, state);
    file_controls(layout, ctx, state, editable);
    snapshot_controls(layout, ctx, state, editable);
    run_controls(layout, ctx, state, editable);
    csv_controls(layout, ctx, state, editable);
    tables_.controls(layout, ctx, state, editable);
    const auto *table = state.table();
    if (!table) {
      return;
    }
    tables_.fields(layout, ctx, state, editable);
    tables_.sweep(layout, ctx, state, editable);
    tables_.grid(layout, ctx, state);
    if (tables_.selected_visible(state)) { tables_.cell(layout, ctx, state, editable, [this] { project_view_ = 1; }); }
    else if (!state.record_id().empty()) { layout.paragraph(ctx.tr("project.filter.hidden_selection")); }
    tables_.management(layout, ctx, state, editable);
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
    std::error_code error;
    const auto single_path = paths.size() == 1 ? core::path_from_utf8(paths.front()) : std::filesystem::path();
    const bool directory = paths.size() == 1 && std::filesystem::is_directory(single_path, error);
    if (state.loaded() && !paths.empty() &&
        (paths.size() > 1 || (single_path.filename() != "project.sqlite3" && !directory))) {
      return state.index_files(paths);
    }
    if (paths.size() != 1) {
      return false;
    }
    directory_ = paths.front();
    const std::string suffix = "project.sqlite3";
    if (directory_.size() > suffix.size() && directory_.ends_with(suffix)) {
      const auto slash = directory_.find_last_of("/\\");
      if (slash != std::string::npos) {
        directory_ = directory_.substr(0, slash + 1);
      }
    }
    ctx.store.project().sync();
    return ctx.store.project().open(path());
  }

  nlohmann::json save_state() const override
  {
    return {{"directory", directory_}, {"name", name_}};
  }

  bool load_state(const nlohmann::json &value) override
  {
    if (!value.is_object()) {
      return false;
    }
    if (value.contains("directory") && value["directory"].is_string()) {
      directory_ = value["directory"].get<std::string>();
    }
    if (value.contains("name") && value["name"].is_string()) {
      name_ = value["name"].get<std::string>();
    }
    return true;
  }

 private:
  void file_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable,
                     const bool standalone = false)
  {
    if (file_project_ != state.project()->id) {
      file_project_ = state.project()->id;
      file_paths_.clear();
    }
    auto *panel = standalone ? &layout.scope("project_files") : layout.panel("project_files", ctx.tr("project.files.title"), false);
    if (!panel) { return; }
    hint(*panel, ctx, "project.files.hint");
    panel->text_area("paths", ui::bind(file_paths_), {.max_length = 65536, .mono = true, .visible_lines = 3});
    files_picker_.draw_error(*panel);
    auto &actions = panel->row();
    files_picker_.button(actions, ctx, "browse_files", &file_paths_,
                         {.title_key = "project.files.dialog", .multiple = true, .still_current = same_project(state)});
    actions.button("index", ctx.tr("project.files.index"), [this, &state] {
      state.index_files(platform::split_path_list(file_paths_));
    }).disable(!editable || state.project()->format_version < 3 || file_paths_.empty());
    const std::string table_id = io::get_string(state.file_index(), "table_id");
    actions.button("show", ctx.tr("project.files.show"), [&state, table_id] { state.select_table(table_id); })
        .disable(table_id.empty());
    auto &folder = panel->row();
    folder.button("folder", ctx.tr("project.files.folder"), [&state] { state.open_folder(false); }).disable(!editable);
    folder.button("code_folder", ctx.tr("project.files.code_folder"), [&state] { state.open_folder(true); }).disable(!editable);
    if (!table_id.empty() && !state.file_index().value("compatible", false)) {
      panel->paragraph(ctx.tr("project.files.incompatible"));
    }
    if (state.selected_file()) {
      const auto *table = state.table();
      const auto &fields = state.file_index().at("fields");
      for (const auto &key : {"path", "location", "state"}) {
        const std::string id = io::get_string(fields, key);
        for (size_t column = 0; column < table->fields.size(); ++column) {
          if (table->fields[column].id == id) {
            panel->paragraph(std::string(ctx.tr(std::string("project.files.") + key)) + ": " +
                             table->text(state.selected_record(), int(column)));
          }
        }
      }
      auto &row = panel->row();
      row.button("refresh", ctx.tr("project.files.refresh"), [&state] { state.refresh_file(); }).disable(!editable);
      row.button("open", ctx.tr("project.files.open"), [&state] { state.open_file(false); }).disable(!editable);
      row.button("code", ctx.tr("project.files.code"), [&state] { state.open_file(true); }).disable(!editable);
      auto &viewer = ctx.store.viewer();
      viewer.refresh_metadata();
      std::vector<std::string> names, ids;
      for (const auto &preset : viewer.presets()) {
        if (!preset.accepts_field_file()) { continue; }
        ids.push_back(preset.id);
        names.push_back(std::string(ctx.store.catalog().tr_or("props.preset." + preset.id, preset.name)));
      }
      if (!viewer.presets_loaded()) { panel->label(ctx.tr("props.preset.loading")); }
      if (!viewer.metadata_error().empty()) { panel->paragraph(viewer.metadata_error()); }
      panel->prop(ctx.tr("project.files.viewer_preset")).dropdown("viewer_preset", std::move(names), {
        [this, ids] { const auto it = std::find(ids.begin(), ids.end(), file_preset_); return it == ids.end() ? -1 : int(it - ids.begin()); },
        [this, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { file_preset_ = ids[i]; } }
      });
      panel->button("view", ctx.tr("project.files.view"), [this, &state] { state.view_file(file_preset_); }).disable(!editable);
      hint(*panel, ctx, "project.files.viewer_hint");
    }
  }

  void snapshot_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto *panel = layout.panel("input_snapshots", ctx.tr("project.snapshots.title"), false);
    if (!panel) { return; }
    hint(*panel, ctx, "project.snapshots.hint");
    const bool enabled = editable && state.project()->format_version >= 4;
    auto &actions = panel->row();
    actions.button("capture", ctx.tr("project.snapshots.capture"), [&state] { state.capture_file(); })
        .disable(!enabled || !state.selected_file());
    actions.button("list", ctx.tr("project.snapshots.list"), [&state] { state.load_input_snapshots(); }).disable(!enabled);
    const auto &snapshots = state.input_snapshots();
    if (snapshots.empty()) { panel->paragraph(ctx.tr("project.snapshots.empty")); return; }
    std::vector<std::string> names, ids;
    for (const auto &snapshot : snapshots) {
      ids.push_back(io::get_string(snapshot, "id"));
      names.push_back(std::to_string(io::get_int(snapshot, "revision", 0)) + " · " + ids.back().substr(0, 8));
    }
    if (std::find(ids.begin(), ids.end(), input_snapshot_) == ids.end()) { input_snapshot_ = ids.back(); }
    panel->prop(ctx.tr("project.snapshots.version")).dropdown("version", std::move(names), {
      [this, ids] { return int(std::find(ids.begin(), ids.end(), input_snapshot_) - ids.begin()); },
      [this, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { input_snapshot_ = ids[i]; } }
    });
    const size_t index = size_t(std::find(ids.begin(), ids.end(), input_snapshot_) - ids.begin());
    const auto &snapshot = snapshots.at(index);
    panel->paragraph(input_snapshot_);
    panel->paragraph(io::get_string(snapshot, "created_at"));
    for (const auto &file : snapshot.at("manifest").at("files")) {
      panel->paragraph(io::get_string(file, "name") + " · " + std::to_string(io::get_int(file, "size", 0)) + " B");
      panel->paragraph("SHA-256: " + io::get_string(file, "sha256"));
    }
    panel->button("verify", ctx.tr("project.snapshots.verify"), [&state, id = input_snapshot_] {
      state.verify_input_snapshot(id);
    }).disable(!enabled);
    const auto &check = state.input_verification();
    if (io::get_string(check, "snapshot_id") == input_snapshot_) {
      panel->paragraph(ctx.tr(check.value("ok", false) ? "project.snapshots.valid" : "project.snapshots.invalid"));
      for (const auto &file : check.at("files")) {
        if (io::get_string(file, "state") != "ok") { panel->paragraph(io::get_string(file, "error")); }
      }
    }
  }

  std::string run_consent_id_;
  bool allow_stale_run_ = false;

  /** A chosen path belongs to the project shown when the dialog was opened. */
  static std::function<bool()> same_project(ProjectState &state)
  {
    const std::string id = state.project() ? state.project()->id : std::string();
    return [&state, id] { return state.project() && state.project()->id == id; };
  }

  void csv_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    if (csv_project_ != state.project()->id) {
      csv_project_ = state.project()->id;
      csv_source_.clear(); csv_destination_.clear(); csv_name_.clear(); csv_error_.clear();
      csv_types_ = csv_units_ = "{}";
    }
    auto *panel = layout.panel("project_csv", ctx.tr("project.csv.title"), false);
    if (!panel) { return; }
    panel->paragraph(ctx.tr("project.csv.import_hint"));
    auto &source = panel->prop(ctx.tr("project.csv.source")).row(true);
    source.text_field("source", ui::bind(csv_source_));
    csv_source_picker_.button(source, ctx, "browse_source", &csv_source_,
                              {.title_key = "project.csv.source_dialog", .still_current = same_project(state)});
    csv_source_picker_.draw_error(*panel);
    panel->prop(ctx.tr("project.csv.name")).text_field("name", ui::bind(csv_name_));
    panel->checkbox("tsv", ctx.tr("project.csv.tsv"), ui::bind(csv_tsv_));
    if (auto *types = panel->panel("types", ctx.tr("project.csv.types"), false)) {
      types->paragraph(ctx.tr("project.csv.types_hint"));
      types->text_area("types", ui::bind(csv_types_), {.max_length = 65536, .mono = true, .visible_lines = 2});
      types->label(ctx.tr("project.csv.units"));
      types->text_area("units", ui::bind(csv_units_), {.max_length = 65536, .mono = true, .visible_lines = 2});
    }
    if (!csv_error_.empty()) { panel->paragraph(csv_error_); }
    panel->button("import", ctx.tr("project.csv.import"), [this, &state] {
      csv_error_.clear();
      try {
        const auto sources = platform::split_path_list(csv_source_);
        state.import_csv(sources.size() == 1 ? sources.front() : csv_source_, csv_name_,
                         io::parse_json(csv_types_), io::parse_json(csv_units_), csv_tsv_ ? "\t" : ",");
      }
      catch (const std::exception &error) { csv_error_ = error.what(); }
    }).disable(!editable || csv_source_.empty() || csv_name_.empty());
    panel->paragraph(ctx.tr("project.csv.export_hint"));
    if (state.table()) { panel->label(state.table()->name); }
    auto &destination = panel->prop(ctx.tr("project.csv.destination")).row(true);
    destination.text_field("destination", ui::bind(csv_destination_));
    csv_destination_picker_.button(destination, ctx, "browse_destination", &csv_destination_, {
        .mode = platform::FileDialogMode::SaveFile, .title_key = "project.csv.destination_dialog",
        .file_name = (state.table() ? state.table()->name : std::string("table")) + (csv_tsv_ ? ".tsv" : ".csv"),
        .still_current = same_project(state)});
    csv_destination_picker_.draw_error(*panel);
    panel->button("export", ctx.tr("project.csv.export"), [this, &state] {
      const auto paths = platform::split_path_list(csv_destination_);
      state.export_csv(paths.size() == 1 ? paths.front() : csv_destination_, csv_tsv_ ? "\t" : ",");
    }).disable(!editable || !state.table() || csv_destination_.empty());
  }

  void recent_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    auto *panel = layout.panel("project_recent", ctx.tr("project.recent.title"), !state.project());
    if (!panel) { return; }
    if (!state.recent_loaded() && !state.recent_loading()) { state.load_recent(); }
    panel->button("reload", ctx.tr("project.refresh"), [&state] { state.load_recent(); })
        .disable(!state.ready() || state.recent_loading());
    if (!state.recent_error().empty()) { panel->paragraph(state.recent_error()); }
    const auto &entries = state.recent();
    if (entries.empty()) { panel->paragraph(ctx.tr("project.recent.empty")); return; }
    std::vector<std::vector<std::string>> cells;
    int selected = -1;
    for (const auto &entry : entries) {
      const auto directory = io::get_string(entry, "directory");
      if (directory == recent_directory_) { selected = int(cells.size()); }
      cells.push_back({io::get_string(entry, "name"), directory});
    }
    ui::TableSpec table;
    table.columns = {{std::string(ctx.tr("project.name")), 10.0f}, {std::string(ctx.tr("project.directory")), 28.0f}};
    table.rows = int(cells.size());
    table.visible_rows = float(std::clamp(int(cells.size()), 2, 5));
    table.data_version = state.version();
    table.cell = [cells = std::move(cells)](int row, int column) { return cells.at(row).at(column); };
    table.selected = {[selected] { return selected; }, [this, &state](int row) {
      if (row >= 0 && size_t(row) < state.recent().size()) { recent_directory_ = io::get_string(state.recent()[row], "directory"); }
    }};
    panel->table("projects", std::move(table));
    if (selected < 0) { return; }
    const auto entry = entries[selected];
    panel->paragraph(io::get_string(entry, "directory"));
    panel->paragraph(io::get_string(entry, "last_opened"));
    auto &buttons = panel->row();
    buttons.button("open", ctx.tr("project.open"), [&state, entry] { state.open_recent(entry); })
        .disable(!state.ready() || state.busy() || state.recent_loading());
    buttons.button("forget", ctx.tr("project.recent.forget"), [&state, entry] {
      state.forget_recent(io::get_string(entry, "directory"));
    }).disable(!state.ready() || state.recent_loading());
    panel->paragraph(ctx.tr("project.recent.hint"));
  }

  void run_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable,
                    const bool standalone = false)
  {
    auto *panel = standalone ? &layout.scope("project_runs") : layout.panel("project_runs", ctx.tr("project.runs.title"), false);
    if (!panel) { return; }
    hint(*panel, ctx, "project.runs.hint");
    state.sync_archive();  // archived runs leave the list unless switched to them (format 11)
    const bool enabled = editable && state.project()->format_version >= 5;
    auto &pages = panel->row();
    pages.button("list", ctx.tr("project.runs.list"), [&state] { state.load_runs(); }).disable(!enabled);
    pages.button("previous", ctx.tr("project.runs.previous"), [&state] {
      state.load_runs(std::max<int64_t>(0, state.runs_offset() - 100));
    }).disable(!enabled || state.runs_offset() == 0);
    pages.button("next", ctx.tr("project.runs.next"), [&state] { state.load_runs(state.runs_next_offset()); })
        .disable(!enabled || state.runs_next_offset() < 0);
    archive_switch(*panel, ctx, "simulation_run", {[&state] { return state.show_archived_runs(); },
        [&state](const bool show) { state.set_show_archived_runs(show); }}, "runs_show_archived");
    if (state.runs().empty()) { panel->paragraph(ctx.tr("project.runs.empty")); return; }
    const auto status_text = [&ctx](const Json &run) {
      const std::string task = io::get_string(run, "task_state");
      return std::string(ctx.tr(task.empty() ? "project.runs." + io::get_string(run, "submission") : "jobs.state." + task));
    };
    std::vector<std::vector<std::string>> cells;
    for (const auto &run : state.runs()) {
      cells.push_back({io::get_string(run, "label"), status_text(run),
                       std::string(ctx.tr("project.runs." + io::get_string(run, "parameter_state"))),
                       io::get_string(run, "connection")});
    }
    ui::TableSpec table;
    table.columns = {{std::string(ctx.tr("project.runs.label")), 10.0f},
                     {std::string(ctx.tr("project.runs.status")), 8.0f},
                     {std::string(ctx.tr("project.runs.parameters")), 8.0f},
                     {std::string(ctx.tr("project.runs.connection")), 10.0f}};
    table.rows = int(cells.size());
    table.visible_rows = float(std::clamp(int(cells.size()), 2, 5));
    table.data_version = state.version();
    table.cell = [cells = std::move(cells)](int row, int column) { return cells.at(row).at(column); };
    table.selected = {[&state] { return state.selected_run(); }, [&state](int row) {
      if (row >= 0 && size_t(row) < state.runs().size()) { state.select_run(io::get_string(state.runs()[row], "id")); }
    }};
    panel->table("runs", std::move(table));
    const auto &run = state.run();
    if (run.empty() || io::get_string(run, "id") != state.run_id()) { return; }
    const auto &plan = run.at("plan"), &status = run.at("status");
    const auto &parameters = plan.at("parameters");
    panel->label(io::get_string(plan, "label"));
    panel->paragraph(io::get_string(plan, "connection") + " · " + io::get_string(plan, "created_at", io::get_string(run, "created_at")));
    panel->paragraph(ctx.tr("project.runs." + io::get_string(run, "parameter_state")));
    const Json task = status.value("task", Json::object());
    if (!task.empty()) {
      panel->paragraph(std::string(ctx.tr("project.runs.task")) + ": " + io::get_string(task, "id") + " · " +
                       std::string(ctx.tr("jobs.state." + io::get_string(task, "state"))));
    }
    if (status.contains("action")) {
      panel->paragraph(std::string(ctx.tr("project.runs.action")) + ": " +
                       std::string(ctx.tr("project.runs." + io::get_string(status.at("action"), "state"))));
    }
    if (status.contains("error") && status.at("error").is_object()) {
      panel->paragraph(io::get_string(status.at("error"), "message"));
    }
    panel->paragraph(std::string(ctx.tr("project.runs.command")) + ": " + plan.at("spec").at("argv").dump());
    if (run_consent_id_ != state.run_id()) { run_consent_id_ = state.run_id(); allow_stale_run_ = false; }
    const bool first = io::get_string(status, "submission") == "prepared";
    const bool stale = io::get_string(run, "parameter_state") != "current";
    const bool archived = archived_notice(*panel, ctx, "simulation_run", state.run_id());
    if (first && stale) { panel->checkbox("allow_stale", ctx.tr("project.runs.allow_stale"), ui::bind(allow_stale_run_)); }
    auto &actions = panel->row();
    actions.button("submit", ctx.tr(first ? "project.runs.submit" : "project.runs.recover"), [this, &state] {
      state.submit_run(allow_stale_run_);
    }).disable(!enabled || !task.empty() || (first && stale && !allow_stale_run_) || archived);
    actions.button("refresh", ctx.tr("project.runs.refresh"), [&state] { state.refresh_run(); }).disable(!enabled);
    const auto task_state = io::get_string(task, "state");
    const bool terminal = task_state == "succeeded" || task_state == "failed" || task_state == "cancelled";
    actions.button("cancel", ctx.tr("project.runs.cancel"), [&state] { state.cancel_run(); })
        .disable(!enabled || task.empty() || terminal);
    // Only once nothing runs on the Runtime (a task in an unknown state may be archived too).
    archive_button(actions, ctx, "simulation_run", state.run_id(), "archive", false,
                   enabled && (task.empty() || terminal || task_state == "unknown"));
    panel->button("source", ctx.tr("project.runs.source"), [&state, parameters] {
      state.select_table(io::get_string(parameters, "table_id"));
      state.select_record(io::get_string(parameters, "record_id"));
    }).disable(io::get_string(run, "parameter_state") == "missing");
    if (auto *detail = panel->panel("frozen", ctx.tr("project.runs.frozen"), false)) {
      detail->paragraph(std::string(ctx.tr("project.runs.identity")) + ": " + state.run_id());
      detail->paragraph("SHA-256: " + io::get_string(run, "sha256"));
      detail->paragraph(std::string(ctx.tr("project.runs.workspace")) + ": " + io::get_string(plan.at("spec"), "workspace_id"));
      ui::TableSpec values;
      values.columns = {{std::string(ctx.tr("project.field")), 9.0f}, {std::string(ctx.tr("project.value")), 14.0f},
                        {std::string(ctx.tr("project.unit")), 5.0f}};
      values.rows = int(parameters.at("fields").size());
      values.visible_rows = float(std::clamp(values.rows, 1, 6));
      values.data_version = state.version();
      values.cell = [parameters](int row, int column) {
        const auto &field = parameters.at("fields").at(row);
        const std::string id = io::get_string(field, "id");
        if (column == 0) { return io::get_string(field, "name"); }
        if (column == 2) { return io::get_string(parameters.at("effective_units"), id); }
        const auto &data = parameters.at("values");
        if (!data.contains(id)) { return std::string(); }
        return data.at(id).is_string() ? data.at(id).get<std::string>() : data.at(id).dump();
      };
      detail->table("parameters", std::move(values));
      for (const auto &file : plan.at("inputs")) {
        detail->paragraph(io::get_string(file, "path") + " · " + std::to_string(io::get_int(file, "size", 0)) + " B");
        detail->paragraph("SHA-256: " + io::get_string(file, "sha256"));
      }
    }
  }

  std::string path() const
  {
    const auto paths = platform::split_path_list(directory_);
    return paths.size() == 1 ? paths.front() : directory_;
  }


  int project_view_ = 0;
  ProjectTableEditor tables_;
  ProjectReviewView review_view_;
  ProjectDiscussionView discussion_view_;
  ProjectSimulationView simulation_view_;
  std::string directory_, name_, recent_directory_;
  std::string file_project_, file_paths_;
  std::string csv_project_, csv_source_, csv_destination_, csv_name_, csv_error_, csv_types_ = "{}", csv_units_ = "{}";
  PathPicker directory_picker_, files_picker_, csv_source_picker_, csv_destination_picker_;
  bool csv_tsv_ = false;
  std::string input_snapshot_;
  std::string file_preset_ = "volume";
};

}  // namespace

std::unique_ptr<Editor> make_project_editor(const EditorType &type)
{
  return std::make_unique<ProjectEditor>(type);
}

}  // namespace stk::app
