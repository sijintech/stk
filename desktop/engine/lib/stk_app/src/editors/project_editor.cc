/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/core/paths.hh"
#include "stk/platform/file_dialog.hh"

#include <algorithm>
#include <filesystem>

namespace stk::app {
namespace {

using io::Json;
const std::vector<std::string> field_types = {"text", "integer", "number", "boolean", "json"};

class ProjectEditor final : public Editor {
 public:
  explicit ProjectEditor(const EditorType &type) : Editor(type) {}

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    auto &state = ctx.store.project();
    state.sync();
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
    if (auto *panel = layout.panel("project_location", ctx.tr("project.location"), !state.project())) {
      panel->prop(ctx.tr("project.directory")).text_field("directory", ui::bind(directory_));
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
    if (state.project()->format_version < 5) {
      layout.paragraph(ctx.tr("project.upgrade_hint"));
      layout.button("upgrade_project", ctx.tr("project.upgrade"), [&state] { state.upgrade(); }).disable(!editable);
    }
    if (auto *panel = layout.panel("project_backup", ctx.tr("project.backup_title"), false)) {
      panel->paragraph(ctx.tr("project.backup_hint"));
      panel->button("backup", ctx.tr("project.backup"), [&state] { state.backup(); }).disable(!editable);
    }
    file_controls(layout, ctx, state, editable);
    snapshot_controls(layout, ctx, state, editable);
    run_controls(layout, ctx, state, editable);
    csv_controls(layout, ctx, state, editable);
    table_controls(layout, ctx, state, editable);
    const auto *table = state.table();
    if (!table) {
      return;
    }
    field_controls(layout, ctx, state, editable);
    draw_table(layout, ctx, state);
    draw_cell(layout, ctx, state, editable);
    manage_objects(layout, ctx, state, editable);
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
  void file_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    if (file_project_ != state.project()->id) {
      file_project_ = state.project()->id;
      file_paths_.clear();
    }
    auto *panel = layout.panel("project_files", ctx.tr("project.files.title"), false);
    if (!panel) { return; }
    panel->paragraph(ctx.tr("project.files.hint"));
    panel->text_area("paths", ui::bind(file_paths_), {.max_length = 65536, .mono = true, .visible_lines = 3});
    auto &actions = panel->row();
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
      panel->paragraph(ctx.tr("project.files.viewer_hint"));
    }
  }

  void snapshot_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto *panel = layout.panel("input_snapshots", ctx.tr("project.snapshots.title"), false);
    if (!panel) { return; }
    panel->paragraph(ctx.tr("project.snapshots.hint"));
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
    panel->prop(ctx.tr("project.csv.source")).text_field("source", ui::bind(csv_source_));
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
    panel->prop(ctx.tr("project.csv.destination")).text_field("destination", ui::bind(csv_destination_));
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

  void run_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto *panel = layout.panel("project_runs", ctx.tr("project.runs.title"), false);
    if (!panel) { return; }
    panel->paragraph(ctx.tr("project.runs.hint"));
    const bool enabled = editable && state.project()->format_version >= 5;
    auto &pages = panel->row();
    pages.button("list", ctx.tr("project.runs.list"), [&state] { state.load_runs(); }).disable(!enabled);
    pages.button("previous", ctx.tr("project.runs.previous"), [&state] {
      state.load_runs(std::max<int64_t>(0, state.runs_offset() - 100));
    }).disable(!enabled || state.runs_offset() == 0);
    pages.button("next", ctx.tr("project.runs.next"), [&state] { state.load_runs(state.runs_next_offset()); })
        .disable(!enabled || state.runs_next_offset() < 0);
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
    if (first && stale) { panel->checkbox("allow_stale", ctx.tr("project.runs.allow_stale"), ui::bind(allow_stale_run_)); }
    auto &actions = panel->row();
    actions.button("submit", ctx.tr(first ? "project.runs.submit" : "project.runs.recover"), [this, &state] {
      state.submit_run(allow_stale_run_);
    }).disable(!enabled || !task.empty() || (first && stale && !allow_stale_run_));
    actions.button("refresh", ctx.tr("project.runs.refresh"), [&state] { state.refresh_run(); }).disable(!enabled);
    const auto task_state = io::get_string(task, "state");
    const bool terminal = task_state == "succeeded" || task_state == "failed" || task_state == "cancelled";
    actions.button("cancel", ctx.tr("project.runs.cancel"), [&state] { state.cancel_run(); })
        .disable(!enabled || task.empty() || terminal);
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

  void manage_objects(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    const auto *table = state.table();
    if (!table) { return; }
    if (std::none_of(table->fields.begin(), table->fields.end(), [this](const auto &field) { return field.id == cell_field_; })) {
      cell_field_ = table->fields.empty() ? std::string() : table->fields.front().id;
    }
    // Name/delete drafts have the same revision precondition as cell edits. Switching the
    // target resets them; a background revision change keeps a dirty draft for review.
    const std::string identity = state.project()->id + table->id + cell_field_ + state.record_id();
    if (identity != manage_identity_ || (!manage_dirty_ && manage_revision_ != state.project()->revision)) {
      manage_identity_ = identity;
      manage_revision_ = state.project()->revision;
      rename_table_ = table->name;
      rename_field_.clear();
      for (const auto &field : table->fields) {
        if (field.id == cell_field_) { rename_field_ = field.name; }
      }
      manage_dirty_ = false;
      pending_manage_ = false;
    }
    else if (pending_manage_ && !state.busy()) {
      pending_manage_ = false;
      if (state.error().empty()) { manage_identity_.clear(); }
    }
    auto *panel = layout.panel("manage_objects", ctx.tr("project.manage"), false);
    if (!panel) { return; }
    const bool current = editable && manage_revision_ == state.project()->revision;
    if (manage_revision_ != state.project()->revision) {
      panel->paragraph(ctx.tr("project.draft_stale"));
    }
    panel->prop(ctx.tr("project.table")).text_field("rename_table", {
      [this] { return rename_table_; },
      [this](std::string value) { rename_table_ = std::move(value); manage_dirty_ = true; }
    });
    const std::string table_id = table->id;
    panel->button("save_table_name", ctx.tr("project.rename_table"), [this, &state, table_id] {
      pending_manage_ = state.apply(Json::array({{{"op", "rename_table"}, {"id", table_id}, {"name", rename_table_}}}), manage_revision_);
    }).disable(!current || rename_table_.empty());
    if (!table->fields.empty()) {
      std::vector<std::string> names, ids;
      for (const auto &field : table->fields) { names.push_back(field.name); ids.push_back(field.id); }
      panel->prop(ctx.tr("project.field")).dropdown("manage_field", std::move(names), {
        [this, ids] { return int(std::find(ids.begin(), ids.end(), cell_field_) - ids.begin()); },
        [this, ids](int index) { if (index >= 0 && size_t(index) < ids.size()) { cell_field_ = ids[index]; } }
      });
      panel->prop(ctx.tr("project.field_name")).text_field("rename_field", {
        [this] { return rename_field_; },
        [this](std::string value) { rename_field_ = std::move(value); manage_dirty_ = true; }
      });
      const std::string field_id = cell_field_;
      panel->button("save_field_name", ctx.tr("project.rename_field"), [this, &state, field_id] {
        pending_manage_ = state.apply(Json::array({{{"op", "rename_field"}, {"id", field_id}, {"name", rename_field_}}}), manage_revision_);
      }).disable(!current || rename_field_.empty());
    }
    panel->button("reload_names", ctx.tr("project.reload_names"), [this] { manage_identity_.clear(); });
    if (state.project()->format_version >= 3) {
      panel->paragraph(ctx.tr("project.delete_hint"));
      auto &buttons = panel->row();
      const std::string record_id = state.record_id(), field_id = cell_field_;
      buttons.button("delete_record", ctx.tr("project.delete_record"), [this, &state, record_id] {
        pending_manage_ = state.apply(Json::array({{{"op", "delete_record"}, {"id", record_id}}}), manage_revision_);
      }).disable(!current || state.selected_record() < 0);
      buttons.button("delete_field", ctx.tr("project.delete_field"), [this, &state, field_id] {
        pending_manage_ = state.apply(Json::array({{{"op", "delete_field"}, {"id", field_id}}}), manage_revision_);
      }).disable(!current || table->fields.empty());
      buttons.button("delete_table", ctx.tr("project.delete_table"), [this, &state, table_id] {
        pending_manage_ = state.apply(Json::array({{{"op", "delete_table"}, {"id", table_id}}}), manage_revision_);
      }).disable(!current);
    }
  }

  std::string path() const
  {
    const auto paths = platform::split_path_list(directory_);
    return paths.size() == 1 ? paths.front() : directory_;
  }

  void table_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto &box = layout.box();
    std::vector<std::string> names, ids;
    for (const auto &table : state.tables()) {
      names.push_back(table.name);
      ids.push_back(table.id);
    }
    if (!names.empty()) {
      box.prop(ctx.tr("project.table")).dropdown("table", std::move(names), {
        [&state, ids] {
          const auto it = std::find(ids.begin(), ids.end(), state.table_id());
          return it == ids.end() ? -1 : int(it - ids.begin());
        },
        [&state, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { state.select_table(ids[i]); } }
      });
    }
    auto &row = box.row();
    row.text_field("table_name", ui::bind(table_name_), {.placeholder = std::string(ctx.tr("project.table_name"))});
    row.button("add_table", ctx.tr("project.add_table"), [this, &state] {
      state.apply(Json::array({{{"op", "create_table"}, {"name", table_name_}}}));
    }).disable(!editable || table_name_.empty());
  }

  void field_controls(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    auto *panel = layout.panel("project_structure", ctx.tr("project.structure"), false);
    if (!panel) {
      return;
    }
    panel->prop(ctx.tr("project.field_name")).text_field("field_name", ui::bind(field_name_));
    std::vector<std::string> types;
    for (const auto &type : field_types) {
      types.emplace_back(ctx.tr("project.type." + type));
    }
    panel->prop(ctx.tr("project.field_type")).dropdown("field_type", std::move(types), ui::bind(field_type_));
    const bool numeric = field_type_ == 1 || field_type_ == 2;
    panel->prop(ctx.tr("project.unit")).text_field("unit", ui::bind(unit_)).disable(!numeric);
    const std::string table = state.table_id();
    panel->button("add_field", ctx.tr("project.add_field"), [this, &state, table] {
      Json command = {{"op", "add_field"}, {"table_id", table}, {"name", field_name_}, {"type", field_types[field_type_]}};
      if ((field_type_ == 1 || field_type_ == 2) && !unit_.empty()) {
        command["unit"] = unit_;
      }
      state.apply(Json::array({command}));
    }).disable(!editable || field_name_.empty());
  }

  void draw_table(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
  {
    const auto &table = *state.table();
    ui::TableSpec spec;
    spec.columns.push_back({std::string(ctx.tr("project.record")), 6.0f});
    const bool file_table = table.id == io::get_string(state.file_index(), "table_id");
    const Json file_fields = file_table ? state.file_index().value("fields", Json::object()) : Json::object();
    for (const auto &field : table.fields) {
      const bool numeric = field.type == "integer" || field.type == "number";
      const float width = !file_table ? 8.0f : field.id == io::get_string(file_fields, "path") ? 12.0f :
                          field.id == io::get_string(file_fields, "name") ? 8.0f : 5.0f;
      spec.columns.push_back({field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"), width, true, numeric});
    }
    spec.rows = int(table.records.size());
    spec.visible_rows = float(std::clamp(int(table.records.size()), 3, 9));
    spec.data_version = state.version();
    spec.cell = [&state](int row, int col) {
      const auto *table = state.table();
      if (!table || row < 0 || size_t(row) >= table->records.size()) {
        return std::string();
      }
      return col == 0 ? table->records[row].id.substr(0, 8) : table->text(row, col - 1);
    };
    spec.selected = {[&state] { return state.selected_record(); }, [&state](int row) {
      const auto *table = state.table();
      if (table && row >= 0 && size_t(row) < table->records.size()) {
        state.select_record(table->records[row].id);
      }
    }};
    spec.compare = [&state](int a, int b, int column) {
      const auto *table = state.table();
      if (!table) { return 0; }
      if (column > 0) { return table->compare(a, b, column - 1); }
      const auto &left = table->records[a].id, &right = table->records[b].id;
      return int(left > right) - int(left < right);
    };
    spec.cell_color = [&state](int row, int column) -> ui::Color {
      const auto *table = state.table();
      const Json *result = table && column > 0 ? table->evaluation(row, column - 1) : nullptr;
      // Match Jobs' failure text colour; theme.state.error is a dark background tint.
      return result && io::get_string(*result, "state") == "error" ? ui::Color::rgb(0xff6e6e) : ui::Color{0, 0, 0, 0};
    };
    layout.scope(table.id).table("records", std::move(spec));
    const std::string id = table.id;
    layout.button("add_record", ctx.tr("project.add_record"), [&state, id] {
      state.apply(Json::array({{{"op", "add_record"}, {"table_id", id}}}));
    }).disable(!state.ready() || state.busy());
  }

  void load_cell(ProjectState &state, const ProjectField &field)
  {
    const int column = int(&field - state.table()->fields.data());
    const auto *value = state.table()->cell(state.selected_record(), column);
    cell_text_ = !value ? std::string() : value->is_string() ? value->get<std::string>() : value->dump();
    // JSON fields containing a string need JSON quotes; text fields do not.
    if (value && field.type == "json") {
      cell_text_ = value->dump();
    }
    cell_mode_ = 0;
    expression_.clear();
    bindings_ = "{}";
    selected_binding_.clear();
    source_table_.clear();
    source_record_.clear();
    source_field_.clear();
    if (const Json *definition = state.table()->definition(state.selected_record(), column)) {
      const std::string kind = io::get_string(*definition, "kind");
      if (kind == "reference") {
        cell_mode_ = 1;
        source_record_ = io::get_string(definition->at("source"), "record_id");
        source_field_ = io::get_string(definition->at("source"), "field_id");
        for (const auto &table : state.tables()) {
          for (const auto &candidate : table.fields) {
            if (candidate.id == source_field_) { source_table_ = table.id; }
          }
        }
      }
      else if (kind == "expression") {
        cell_mode_ = 2;
        expression_ = io::get_string(*definition, "expression");
        bindings_ = definition->at("bindings").dump(2);
      }
    }
    draft_revision_ = state.project()->revision;
    draft_dirty_ = false;
    literal_error_.clear();
  }

  void source_controls(ui::Layout &box, EditorContext &ctx, ProjectState &state)
  {
    std::vector<std::string> tables{std::string(ctx.tr("project.source_pick"))}, table_ids{""};
    const ProjectTable *source = nullptr;
    for (const auto &table : state.tables()) {
      tables.push_back(table.name);
      table_ids.push_back(table.id);
      if (table.id == source_table_) { source = &table; }
    }
    box.prop(ctx.tr("project.source_table")).dropdown("source_table", std::move(tables), {
      [this, table_ids] {
        const auto found = std::find(table_ids.begin(), table_ids.end(), source_table_);
        return found == table_ids.end() ? 0 : int(found - table_ids.begin());
      },
      [this, table_ids](int index) {
        if (index >= 0 && size_t(index) < table_ids.size()) {
          source_table_ = table_ids[index]; source_record_.clear(); source_field_.clear(); draft_dirty_ = true;
        }
      }
    });
    if (!source) {
      if (!source_record_.empty() || !source_field_.empty()) {
        box.paragraph(ctx.tr("project.source_missing"));
        box.paragraph(source_record_ + " / " + source_field_);
      }
      return;
    }
    std::vector<std::string> records{std::string(ctx.tr("project.source_pick"))}, record_ids{""};
    for (size_t i = 0; i < source->records.size(); ++i) {
      records.push_back(std::to_string(i + 1) + " · " + source->records[i].id.substr(0, 8));
      record_ids.push_back(source->records[i].id);
    }
    box.prop(ctx.tr("project.source_record")).dropdown("source_record", std::move(records), {
      [this, record_ids] {
        const auto found = std::find(record_ids.begin(), record_ids.end(), source_record_);
        return found == record_ids.end() ? 0 : int(found - record_ids.begin());
      },
      [this, record_ids](int index) {
        if (index >= 0 && size_t(index) < record_ids.size()) { source_record_ = record_ids[index]; draft_dirty_ = true; }
      }
    });
    std::vector<std::string> fields{std::string(ctx.tr("project.source_pick"))}, field_ids{""};
    for (const auto &field : source->fields) {
      fields.push_back(field.name + (field.unit.empty() ? "" : " (" + field.unit + ")"));
      field_ids.push_back(field.id);
    }
    box.prop(ctx.tr("project.source_field")).dropdown("source_field", std::move(fields), {
      [this, field_ids] {
        const auto found = std::find(field_ids.begin(), field_ids.end(), source_field_);
        return found == field_ids.end() ? 0 : int(found - field_ids.begin());
      },
      [this, field_ids](int index) {
        if (index >= 0 && size_t(index) < field_ids.size()) { source_field_ = field_ids[index]; draft_dirty_ = true; }
      }
    });
  }

  void binding_table(ui::Layout &box, EditorContext &ctx, ProjectState &state)
  {
    std::vector<std::string> names;
    std::vector<std::vector<std::string>> rows;
    try {
      const Json bindings = io::parse_json(bindings_);
      if (!bindings.is_object()) { throw std::runtime_error("not an object"); }
      for (const auto &[name, source] : bindings.items()) {
        const std::string record = source.is_object() ? io::get_string(source, "record_id") : "";
        const std::string field = source.is_object() ? io::get_string(source, "field_id") : "";
        std::vector<std::string> row{name, std::string(ctx.tr("project.binding_missing")), record.substr(0, 8), field.substr(0, 8), ""};
        for (const auto &table : state.tables()) {
          for (size_t c = 0; c < table.fields.size(); ++c) {
            if (table.fields[c].id != field) { continue; }
            for (size_t r = 0; r < table.records.size(); ++r) {
              if (table.records[r].id == record) {
                row[1] = table.name;
                row[2] = std::to_string(r + 1) + " · " + record.substr(0, 8);
                row[3] = table.fields[c].name;
                row[4] = table.text(int(r), int(c));
              }
            }
          }
        }
        names.push_back(name);
        rows.push_back(std::move(row));
      }
    }
    catch (const std::exception &) {
      box.paragraph(ctx.tr("project.error.bindings"));
    }
    ui::TableSpec spec;
    spec.columns = {{std::string(ctx.tr("project.binding_name")), 5},
                    {std::string(ctx.tr("project.source_table")), 8},
                    {std::string(ctx.tr("project.source_record")), 7},
                    {std::string(ctx.tr("project.source_field")), 8},
                    {std::string(ctx.tr("project.value")), 6}};
    spec.rows = int(rows.size());
    spec.visible_rows = float(std::clamp(int(rows.size()), 1, 4));
    spec.data_version = state.version() + uint64_t(std::hash<std::string>{}(bindings_));
    spec.cell = [rows](int row, int col) { return rows[size_t(row)][size_t(col)]; };
    spec.selected = {
      [this, names] {
        const auto found = std::find(names.begin(), names.end(), selected_binding_);
        return found == names.end() ? -1 : int(found - names.begin());
      },
      [this, names](int index) { if (index >= 0 && size_t(index) < names.size()) { selected_binding_ = names[index]; } }
    };
    box.table("binding_rows", std::move(spec));
    box.button("remove_binding", ctx.tr("project.remove_binding"), [this] {
      try {
        Json bindings = io::parse_json(bindings_);
        if (!bindings.is_object()) { return; }
        bindings.erase(selected_binding_);
        bindings_ = bindings.dump(2);
        selected_binding_.clear();
        draft_dirty_ = true;
      }
      catch (const std::exception &) { literal_error_ = "project.error.bindings"; }
    }).disable(std::find(names.begin(), names.end(), selected_binding_) == names.end());
  }

  void draw_cell(ui::Layout &layout, EditorContext &ctx, ProjectState &state, const bool editable)
  {
    const auto &table = *state.table();
    if (table.fields.empty() || state.selected_record() < 0) {
      layout.paragraph(ctx.tr("project.empty_table"));
      return;
    }
    std::vector<std::string> names, ids;
    for (const auto &field : table.fields) {
      names.push_back(field.name);
      ids.push_back(field.id);
    }
    auto it = std::find(ids.begin(), ids.end(), cell_field_);
    if (it == ids.end()) {
      cell_field_ = ids.front();
      it = ids.begin();
    }
    const auto &field = table.fields[size_t(it - ids.begin())];
    const std::string identity = state.project()->id + table.id + state.record_id() + field.id;
    if (identity != draft_identity_ || (!draft_dirty_ && draft_revision_ != state.project()->revision)) {
      draft_identity_ = identity;
      load_cell(state, field);
      pending_cell_ = false;
    }
    else if (pending_cell_ && !state.busy()) {
      pending_cell_ = false;
      if (state.error().empty()) {
        load_cell(state, field);
      }
    }
    auto &box = layout.box();
    box.label(ctx.tr("project.cell_editor"));
    box.prop(ctx.tr("project.field")).dropdown("cell_field", std::move(names), {
      [this, ids] { return int(std::find(ids.begin(), ids.end(), cell_field_) - ids.begin()); },
      [this, ids](int i) { if (i >= 0 && size_t(i) < ids.size()) { cell_field_ = ids[i]; } }
    });
    const bool version2 = state.project()->format_version >= 2;
    if (version2) {
      box.prop(ctx.tr("project.definition")).dropdown("cell_mode", {
        std::string(ctx.tr("project.mode.literal")), std::string(ctx.tr("project.mode.reference")),
        std::string(ctx.tr("project.mode.expression"))}, {
        [this] { return cell_mode_; }, [this](int mode) { cell_mode_ = mode; draft_dirty_ = true; literal_error_.clear(); }
      });
    }
    if (cell_mode_ == 0) {
      box.prop(ctx.tr("project.value")).text_field("cell_value", {
        [this] { return cell_text_; },
        [this](std::string text) { cell_text_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
      }, {.mono = field.type != "text"});
    }
    else if (cell_mode_ == 1) {
      source_controls(box, ctx, state);
    }
    else {
      box.prop(ctx.tr("project.expression")).text_field("expression", {
        [this] { return expression_; },
        [this](std::string text) { expression_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
      }, {.max_length = 4096, .mono = true});
      box.label(ctx.tr("project.bindings"));
      binding_table(box, ctx, state);
      if (auto *panel = box.panel("add_binding", ctx.tr("project.add_binding"), false)) {
        panel->prop(ctx.tr("project.binding_name")).text_field("binding_name", ui::bind(binding_name_));
        source_controls(*panel, ctx, state);
        panel->button("insert_binding", ctx.tr("project.insert_binding"), [this] {
          try {
            Json bindings = io::parse_json(bindings_);
            if (!bindings.is_object()) { literal_error_ = "project.error.bindings"; return; }
            bindings[binding_name_] = {{"record_id", source_record_}, {"field_id", source_field_}};
            bindings_ = bindings.dump(2);
            selected_binding_ = binding_name_;
            draft_dirty_ = true;
            literal_error_.clear();
          }
          catch (const std::exception &) { literal_error_ = "project.error.bindings"; }
        }).disable(source_record_.empty() || source_field_.empty() || binding_name_.empty());
      }
      if (auto *panel = box.panel("bindings_raw", ctx.tr("project.bindings_advanced"), false)) {
        panel->text_area("bindings", {
          [this] { return bindings_; },
          [this](std::string text) { bindings_ = std::move(text); draft_dirty_ = true; literal_error_.clear(); }
        }, {.max_length = 32768, .mono = true, .visible_lines = 4});
      }
    }
    const int column = int(&field - table.fields.data());
    if (const Json *evaluation = table.evaluation(state.selected_record(), column)) {
      if (io::get_string(*evaluation, "state") == "error") {
        const Json &error = evaluation->at("error");
        box.paragraph(std::string(ctx.tr("project.evaluation_error")) + " · " + io::get_string(error, "code") +
                      ": " + io::get_string(error, "message"));
      }
      else {
        box.label(std::string(ctx.tr("project.computed_value")) + " " + table.text(state.selected_record(), column) +
                  " " + io::get_string(*evaluation, "unit"));
      }
    }
    if (draft_revision_ != state.project()->revision) {
      box.paragraph(ctx.tr("project.draft_stale"));
    }
    if (!literal_error_.empty()) {
      box.paragraph(ctx.tr(literal_error_));
    }
    const Json target = {{"op", "set_cell"}, {"table_id", table.id}, {"record_id", state.record_id()}, {"field_id", field.id}};
    const std::string type = field.type;
    auto &buttons = box.row();
    buttons.button("save_cell", ctx.tr("project.save_cell"), [this, &state, target, type] {
      Json command = target;
      if (cell_mode_ == 0) {
        auto value = project_literal(type, cell_text_, literal_error_);
        if (!value) { return; }
        command["value"] = *value;
      }
      else if (cell_mode_ == 1) {
        if (source_record_.empty() || source_field_.empty()) { literal_error_ = "project.error.reference"; return; }
        command["op"] = "set_reference";
        command["source"] = {{"record_id", source_record_}, {"field_id", source_field_}};
      }
      else {
        try {
          Json bindings = io::parse_json(bindings_);
          if (!bindings.is_object()) { literal_error_ = "project.error.bindings"; return; }
          command["op"] = "set_expression";
          command["expression"] = expression_;
          command["bindings"] = std::move(bindings);
        }
        catch (const std::exception &) { literal_error_ = "project.error.bindings"; return; }
      }
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    buttons.button("null_cell", ctx.tr("project.null_cell"), [this, &state, target] {
      Json command = target;
      command["value"] = nullptr;
      pending_cell_ = state.apply(Json::array({command}), draft_revision_);
    }).disable(!editable || draft_revision_ != state.project()->revision);
    if (version2) {
      buttons.button("unset_cell", ctx.tr("project.unset_cell"), [this, &state, target] {
        Json command = target;
        command["op"] = "unset_cell";
        pending_cell_ = state.apply(Json::array({command}), draft_revision_);
      }).disable(!editable || draft_revision_ != state.project()->revision);
    }
    buttons.button("reload_cell", ctx.tr("project.reload_cell"), [this] {
      draft_identity_.clear();
    });
    box.paragraph(ctx.tr(cell_mode_ == 0 ? "project.cell_hint" : "project.expression_hint"));
  }

  std::string directory_, name_, table_name_, field_name_, unit_, cell_field_, recent_directory_;
  std::string file_project_, file_paths_;
  std::string csv_project_, csv_source_, csv_destination_, csv_name_, csv_error_, csv_types_ = "{}", csv_units_ = "{}";
  bool csv_tsv_ = false;
  std::string input_snapshot_;
  std::string cell_text_, draft_identity_, literal_error_;
  std::string expression_, bindings_ = "{}", binding_name_ = "base";
  std::string selected_binding_;
  std::string file_preset_ = "volume";
  std::string source_table_, source_record_, source_field_;
  int cell_mode_ = 0;
  int field_type_ = 2;
  int64_t draft_revision_ = -1;
  bool draft_dirty_ = false;
  bool pending_cell_ = false;
  std::string manage_identity_, rename_table_, rename_field_;
  int64_t manage_revision_ = -1;
  bool manage_dirty_ = false, pending_manage_ = false;
};

}  // namespace

std::unique_ptr<Editor> make_project_editor(const EditorType &type)
{
  return std::make_unique<ProjectEditor>(type);
}

}  // namespace stk::app
