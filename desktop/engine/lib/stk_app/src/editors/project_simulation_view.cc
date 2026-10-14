/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_simulation_view.hh"
#include "archive_controls.hh"
#include "project_navigation.hh"
#include "project_labels.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/platform/file_dialog.hh"
#include "editor_text.hh"
#include <algorithm>

namespace stk::app {
namespace {
using io::Json;
struct Engine {
  const char *id, *name, *cases, *results, *case_name, *temperature, *result_run;
};
constexpr Engine engines[] = {
    {"muferro/1", "MuFerro", "27e50c45-2d61-523c-a56b-f505bbd595c5", "04d7cc6c-5da5-5c92-a860-f3368f7b376d",
     "b29f3eda-8426-50f5-a6d8-c2e6307f28a4", "7e96da82-9b05-5f99-981e-8bf38a2028d2", "a28fc8b4-3e43-5697-b37e-f65f1516c967"},
    {"lammps/1", "LAMMPS", "a70a9da3-fb57-5d06-9ab3-5de529a82882", "3f63a5bf-fc98-5c23-b211-7dcb31a5b173",
     "77bc2593-3729-593c-8986-22a5aa3fdd7e", "ac8845ed-e05c-5f93-916a-dd0ba11b5e8d", "c7a88cd8-bfe3-54e4-85f1-80920e2dd04d"},
};

const Engine *run_engine(const Json &run)
{
  if (!run.is_object() || !run.contains("plan") || !run.at("plan").is_object()) { return nullptr; }
  const auto parameters = run.at("plan").value("parameters", Json());
  if (!parameters.is_object()) { return nullptr; }
  const auto table = io::get_string(parameters, "table_id");
  for (const auto &engine : engines) { if (table == engine.cases) { return &engine; } }
  return nullptr;
}

bool execute(ScriptState &scripts, const std::string &engine, const std::string &action, const Json &params)
{
  // Both literals encode data only, including quotes, newlines and non-ASCII paths.
  return scripts.execute("import json as _stk_json\n"
      "from suan.workflows.native import native_action as _stk_simulation\n"
      "_stk_simulation(stk, " + Json(engine).dump() + ", " + Json(action).dump() +
      ", _stk_json.loads(" + Json(params.dump()).dump() + ")); None");
}
}  // namespace

void ProjectSimulationView::select_engine(int index)
{
  if (index < 0 || index > 1 || index == engine_) { return; }
  engine_ = index;
  ++generation_;
  source_.clear();
  script_.clear();
  error_.clear();
  batch_selection_.clear();
  batch_id_.clear();
  batch_member_.clear();
}

bool ProjectSimulationView::context_current(const ProjectState &state, const std::string &project,
                                           const std::string &handle, uint64_t generation) const
{
  return state.project() && state.project()->id == project && state.project()->handle == handle && generation_ == generation;
}

void ProjectSimulationView::sync_project(ProjectState &state)
{
  if (project_ != state.project()->id || handle_ != state.project()->handle) {
    project_ = state.project()->id;
    handle_ = state.project()->handle;
    ++generation_;
    engine_ = 0;
    observed_table_.clear();
    source_.clear();
    script_.clear();
    error_.clear();
    batch_selection_.clear();
    batch_id_.clear();
    batch_member_.clear();
  }
  if (observed_table_ != state.table_id()) {
    observed_table_ = state.table_id();
    for (int i = 0; i < 2; ++i) {
      if (observed_table_ == engines[i].cases || observed_table_ == engines[i].results) { select_engine(i); break; }
    }
  }
}

void ProjectSimulationView::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  sync_project(state);
  auto *panel = layout.panel("project_simulation", ctx.tr("simulation.title"), false);
  if (!panel) { return; }
  auto &scripts = ctx.store.scripts();
  auto &jobs = ctx.store.jobs();
  scripts.sync();
  jobs.sync();
  const bool enabled = state.ready() && !state.busy() && state.project()->format_version >= 5 && scripts.ready() && !scripts.busy();
  const auto project = state.project()->id;
  const auto handle = state.project()->handle;
  const auto generation = generation_;
  const auto revision = state.project()->revision;
  const auto record = state.record_id();
  const auto run = state.run_id();
  const Engine engine = engines[engine_];
  panel->prop(ctx.tr("simulation.engine")).dropdown("simulation_engine", {"MuFerro", "LAMMPS"}, {
    [this] { return engine_; }, [this](int index) { select_engine(index); }
  }).disable(!enabled);
  hint(*panel, ctx, engine_ == 1 ? "simulation.lammps_hint" : "simulation.hint");
  if (!error_.empty()) { panel->paragraph(error_); }
  if (!scripts.error().empty()) { panel->paragraph(scripts.error()); }
  auto &source = panel->prop(ctx.tr("simulation.directory")).row(true);
  source.text_field("simulation_source", ui::bind(source_));
  source_picker_.button(source, ctx, "simulation_browse", &source_, {
      .mode = platform::FileDialogMode::OpenFolder,
      .title_key = engine_ == 1 ? "simulation.lammps_directory_dialog" : "simulation.directory_dialog",
      .still_current = [this, &state, project, handle, generation] { return context_current(state, project, handle, generation); }});
  source_picker_.draw_error(*panel);
  if (engine_ == 1) {
    panel->prop(ctx.tr("simulation.input_script")).text_field("simulation_script", ui::bind(script_));
    hint(*panel, ctx, "simulation.script_hint");
  }
  panel->button("simulation_import", ctx.tr("simulation.import"),
                [this, &state, &scripts, project, handle, generation, revision, engine, source = source_, script = script_,
                 changed = std::string(ctx.tr("simulation.context_changed")), one = std::string(ctx.tr("simulation.one_directory"))] {
    if (!context_current(state, project, handle, generation) || source_ != source || script_ != script) { error_ = changed; return; }
    const auto paths = platform::split_path_list(source);
    if (paths.size() != 1) { error_ = one; return; }
    error_.clear();
    Json params = {{"project_id", project}, {"expected_revision", revision}, {"source", paths.front()}};
    if (std::string(engine.id) == "lammps/1" && !script.empty()) { params["script"] = script; }
    execute(scripts, engine.id, "import", params);
  }).disable(!enabled || source_.empty());
  hint(*panel, ctx, "simulation.connection_hint");
  auto &target = engine_ == 1 ? lammps_target_ : target_;
  const auto connection = target.runtime_controls(*panel, ctx);
  const auto options = target.options_controls(*panel, ctx, engine.id);
  panel->button("simulation_prepare", ctx.tr("simulation.prepare"), [this, &state, &scripts, project, handle, generation, revision, record, connection, options, engine] {
    if (!context_current(state, project, handle, generation) || state.record_id() != record || state.table_id() != engine.cases) { return; }
    error_.clear();
    execute(scripts, engine.id, "prepare", {{"project_id", project}, {"expected_revision", revision},
        {"record_id", record}, {"connection", connection}, {"options", *options}});
  }).disable(!enabled || state.table_id() != engine.cases || record.empty() || connection.empty() || !options || jobs.hub());
  hint(*panel, ctx, "simulation.run_hint");
  const bool selected = !run.empty() && !state.run().empty() && io::get_string(state.run(), "id") == run;
  bool accepted = false, succeeded = false;
  const Engine *selected_engine = selected ? run_engine(state.run()) : nullptr;
  if (selected) {
    const auto &plan = state.run().at("plan");
    const auto &status = state.run().at("status");
    accepted = status.contains("task") && status.at("task").is_object();
    succeeded = accepted && io::get_string(status.at("task"), "state") == "succeeded";
    panel->paragraph((selected_engine ? std::string(selected_engine->name) + " · " : "") + io::get_string(plan, "label"));
  }
  auto &actions = panel->row();
  actions.button("simulation_logs", ctx.tr("simulation.logs"), [this, &state, &scripts, project, handle, generation, revision, run, selected_engine] {
    if (!context_current(state, project, handle, generation) || state.run_id() != run) { return; }
    if (selected_engine) { execute(scripts, selected_engine->id, "logs", {{"project_id", project}, {"expected_revision", revision}, {"run_id", run}}); }
  }).disable(!enabled || !selected_engine || !accepted);
  actions.button("simulation_collect", ctx.tr("simulation.collect"), [this, &state, &scripts, project, handle, generation, revision, run, selected_engine] {
    if (!context_current(state, project, handle, generation) || state.run_id() != run) { return; }
    if (selected_engine) { execute(scripts, selected_engine->id, "collect", {{"project_id", project}, {"expected_revision", revision}, {"run_id", run}}); }
  }).disable(!enabled || !selected_engine || !succeeded);
  actions.button("simulation_view", ctx.tr("simulation.view"), [this, &state, &scripts, project, handle, generation, revision, run, selected_engine] {
    if (!context_current(state, project, handle, generation) || state.run_id() != run) { return; }
    if (selected_engine) { execute(scripts, selected_engine->id, "view", {{"project_id", project}, {"expected_revision", revision}, {"run_id", run}}); }
  }).disable(!enabled || !selected_engine || !succeeded ||
              (selected_engine == &engines[0] && !scripts.desktop_ready()));
  if (selected_engine == &engines[1]) {
    std::string result_record;
    for (const auto &table : state.tables()) {
      if (table.id != selected_engine->results) { continue; }
      for (const auto &row : table.records) {
        if (io::get_string(row.values, selected_engine->result_run) == run) { result_record = row.id; break; }
      }
    }
    actions.button("simulation_results", ctx.tr("simulation.results"), [this, &state, project, handle, generation, run, result_record] {
      if (!context_current(state, project, handle, generation) || state.run_id() != run) { return; }
      state.select_table(engines[1].results);
      state.select_record(result_record);
    }).disable(!enabled || result_record.empty());
    hint(*panel, ctx, "simulation.lammps_result_hint");
  }
  panel->label(ctx.tr(scripts.busy() ? "simulation.busy" : "simulation.output"));
  if (scripts.status().contains("run") && scripts.status()["run"].is_object()) {
    panel->label(ctx.tr("script.run_state." + io::get_string(scripts.status()["run"], "state")));
  }
  panel->log_view("simulation_output", scripts.output(), 6);
}

void ProjectSimulationView::draw_batches(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  sync_project(state);
  constexpr auto batches_id = "9ab21772-9bc4-56ab-94e1-f3f1049fb398";
  constexpr auto name_id = "4c8c8e0b-e625-54b9-aa39-cfbddef20d7c";
  constexpr auto intent_id = "1c728eb5-5c6d-505d-bed4-914def1c4dac";
  constexpr auto outcomes_id = "6aba8921-3964-58ec-b239-23181a122393";
  auto *panel = layout.panel("project_batches", ctx.tr("batch.title"), false);
  if (!panel) { return; }
  auto &scripts = ctx.store.scripts();
  auto &jobs = ctx.store.jobs();
  scripts.sync();
  jobs.sync();
  const bool enabled = state.ready() && !state.busy() && state.project()->format_version >= 5 && scripts.ready() && !scripts.busy();
  const auto project = state.project()->id;
  const auto handle = state.project()->handle;
  const auto generation = generation_;
  const auto revision = state.project()->revision;
  const Engine engine = engines[engine_];
  const bool case_selected = state.table_id() == engine.cases && !state.record_id().empty();
  const auto record = state.record_id();
  panel->prop(ctx.tr("simulation.engine")).dropdown("batch_engine", {"MuFerro", "LAMMPS"}, {
    [this] { return engine_; }, [this](int index) { select_engine(index); }
  }).disable(!enabled);
  hint(*panel, ctx, "batch.hint");
  auto &selection = panel->row();
  selection.button("add", ctx.tr("batch.add"), [this, &state, project, handle, generation, record] {
    if (!context_current(state, project, handle, generation) || state.record_id() != record) { return; }
    if (batch_selection_.size() < 100 && std::find(batch_selection_.begin(), batch_selection_.end(), record) == batch_selection_.end()) {
      batch_selection_.push_back(record);
    }
  }).disable(!enabled || !case_selected || batch_selection_.size() >= 100);
  selection.button("remove", ctx.tr("batch.remove"), [this, &state, project, handle, generation, record] {
    if (!context_current(state, project, handle, generation)) { return; }
    batch_selection_.erase(std::remove(batch_selection_.begin(), batch_selection_.end(), record), batch_selection_.end());
  }).disable(!enabled || std::find(batch_selection_.begin(), batch_selection_.end(), record) == batch_selection_.end());
  selection.button("all", ctx.tr("batch.all"), [this, &state, project, handle, generation, engine] {
    if (!context_current(state, project, handle, generation) || state.table_id() != engine.cases) { return; }
    batch_selection_.clear();
    for (const auto &table : state.tables()) {
      if (table.id == engine.cases && table.records.size() <= 100) {
        for (const auto &row : table.records) { batch_selection_.push_back(row.id); }
      }
    }
  }).disable(!enabled || !case_selected || state.table()->records.size() > 100);
  selection.button("clear", ctx.tr("batch.clear"), [this, &state, project, handle, generation] {
    if (context_current(state, project, handle, generation)) { batch_selection_.clear(); }
  }).disable(!enabled || batch_selection_.empty());
  panel->button("clone", ctx.tr("batch.clone"), [this, &state, &scripts, project, handle, generation, revision, record, engine] {
    if (!context_current(state, project, handle, generation) || state.record_id() != record || state.table_id() != engine.cases) { return; }
    execute(scripts, engine.id, "clone", {{"project_id", project}, {"expected_revision", revision}, {"record_id", record}});
  }).disable(!enabled || !case_selected);
  panel->label(std::string(ctx.tr("batch.selection")) + " " + std::to_string(batch_selection_.size()));
  std::vector<std::vector<std::string>> selected_cells;
  const ProjectTable *cases = nullptr;
  for (const auto &table : state.tables()) { if (table.id == engine.cases) { cases = &table; } }
  if (cases) {
    for (const auto &row : cases->records) {
      if (std::find(batch_selection_.begin(), batch_selection_.end(), row.id) != batch_selection_.end()) {
        selected_cells.push_back({row_label(ctx.store, cases, row.id) + " · " + io::get_string(row.values, engine.case_name),
            row.values.value(engine.temperature, Json()).dump()});
      }
    }
  }
  if (!selected_cells.empty()) {
    ui::TableSpec selection_table;
    selection_table.columns = {{std::string(ctx.tr("batch.case")), 12.0f},
                               {engine_ == 0 ? "K" : std::string(ctx.tr("simulation.temperature")), 8.0f}};
    selection_table.rows = int(selected_cells.size());
    selection_table.visible_rows = float(std::clamp(int(selected_cells.size()), 1, 4));
    selection_table.cell = [selected_cells](int row, int col) { return selected_cells.at(row).at(col); };
    panel->table("selection", std::move(selection_table));
  }
  auto &target = engine_ == 1 ? lammps_target_ : target_;
  const auto connection = target.runtime_controls(*panel, ctx);
  const auto options = target.options_controls(*panel, ctx, engine.id);
  const auto members = batch_selection_;
  const bool can_run = enabled && !members.empty() && !connection.empty() && options && !jobs.hub();
  const auto batch_params = [project, revision, members, connection, options, engine] {
    return Json{{"project_id", project}, {"expected_revision", revision}, {"template_id", engine.id},
                {"record_ids", members}, {"connection", connection}, {"options", options ? *options : Json::object()}};
  };
  std::string runtime_name = connection;
  for (const auto &row : jobs.connections()) {
    if (row.info.id == connection && !row.info.name.empty()) { runtime_name = row.info.name; }
  }
  auto &run_row = panel->row();
  // One explicit click saves the batch, prepares its inputs and submits the prepared rows.
  run_row.button("run_selected", can_run ? ctx.store.catalog().format("batch.run_selected", {
                 {"rows", std::to_string(members.size())}, {"runtime", runtime_name}}) : std::string(ctx.tr("batch.run_selected_blocked")),
             [this, &state, &scripts, project, handle, generation, members, batch_params, engine] {
               if (!context_current(state, project, handle, generation) || batch_selection_ != members) { return; }
               error_.clear(); execute(scripts, engine.id, "batch_run", batch_params());
             })
      .disable(!can_run);
  run_row.button("create", ctx.tr("batch.create"), [this, &state, &scripts, project, handle, generation, members, batch_params, engine] {
    if (!context_current(state, project, handle, generation) || batch_selection_ != members) { return; }
    error_.clear();
    execute(scripts, engine.id, "batch_create", batch_params());
  }).width(10).disable(!can_run);
  if (!error_.empty()) { panel->paragraph(error_); }

  std::vector<std::string> ids, names;
  std::vector<size_t> rows;  // each listed batch's record index
  const ProjectTable *batches = nullptr;
  for (const auto &table : state.tables()) { if (table.id == batches_id) { batches = &table; break; } }
  // Archived batches leave the list unless switched to them (format 11); batches are table rows, filtered here.
  auto &archive = ctx.store.archive();
  const auto filter = archive_filter(ctx, show_archived_batches_);
  archive_switch(*panel, ctx, "batch", show_archived_batches_, "batches_show_archived", false);
  if (batches) {
    for (size_t i = 0; i < batches->records.size(); ++i) {
      const auto &row = batches->records[i];
      const auto intent = row.values.value(intent_id, Json());
      const auto template_id = intent.is_object() ? io::get_string(intent, "template") : std::string();
      const bool builtin = std::any_of(std::begin(engines), std::end(engines), [&](const Engine &item) { return template_id == item.id; });
      // Keep incomplete/other records inspectable and archivable; they cannot use these execution controls.
      if (builtin && template_id != engine.id) { continue; }
      if (filter && archive.archived("batch", row.id) != *filter) { continue; }
      ids.push_back(row.id); names.push_back(io::get_string(row.values, name_id, row.id)); rows.push_back(i);
    }
  }
  if (!ids.empty() && std::find(ids.begin(), ids.end(), batch_id_) == ids.end()) { batch_id_ = ids.back(); batch_member_.clear(); }
  panel->prop(ctx.tr("batch.saved")).dropdown("saved", std::move(names), {
    [this, ids] { const auto it = std::find(ids.begin(), ids.end(), batch_id_); return it == ids.end() ? -1 : int(it - ids.begin()); },
    [this, &state, project, handle, generation, ids](int row) {
      if (context_current(state, project, handle, generation) && row >= 0 && size_t(row) < ids.size()) {
        batch_id_ = ids[row]; batch_member_.clear();
      }
    }
  });
  if (batches && std::find(ids.begin(), ids.end(), batch_id_) != ids.end()) {
    const auto index = rows.at(size_t(std::find(ids.begin(), ids.end(), batch_id_) - ids.begin()));
    const auto &values = batches->records[index].values;
    archived_notice(*panel, ctx, "batch", batch_id_);
    if (auto *button = archive_button(*panel, ctx, "batch", batch_id_, "batch_archive", false, enabled)) {
      auto archive_action = std::move(button->on_click);
      button->on_click = [this, &state, project, handle, generation, batch = batch_id_, archive_action = std::move(archive_action)] {
        if (context_current(state, project, handle, generation) && batch_id_ == batch) { archive_action(); }
      };
    }
    const Json intent = values.value(intent_id, Json());
    const Json outcomes = values.value(outcomes_id, Json());
    if (intent.is_object() && io::get_string(intent, "template") == engine.id &&
        intent.contains("entries") && intent["entries"].is_array() && outcomes.is_object() &&
        std::all_of(intent["entries"].begin(), intent["entries"].end(), [](const Json &entry) { return entry.is_object(); }) &&
        std::all_of(outcomes.begin(), outcomes.end(), [](const Json &entry) { return entry.is_object(); })) {
      const auto entries = intent["entries"];
      // The template and the saved Runtime by name; their ids stay in the frozen intent.
      const auto connection_id = io::get_string(intent, "connection");
      std::string runtime_name = connection_id.rfind("runtime:", 0) == 0 ? connection_id.substr(8) : connection_id;
      for (const auto &row : jobs.connections()) {
        if (row.info.id == connection_id && !row.info.name.empty()) { runtime_name = row.info.name; }
      }
      panel->label(std::string(engine.name) +
                   "  ·  " + std::string(ctx.tr("simulation.runtime")) + ": " + runtime_name);
      ui::TableSpec table;
      table.columns = {{std::string(ctx.tr("batch.case")), 12.0f}, {std::string(ctx.tr("batch.status")), 8.0f},
                       {std::string(ctx.tr("batch.outcome")), 16.0f}};
      table.rows = int(entries.size());
      table.visible_rows = float(std::clamp(int(entries.size()), 2, 5));
      table.data_version = state.version();
      Json names = Json::object();
      names["unprepared"] = std::string(ctx.tr("batch.unprepared"));
      for (const auto *key : {"prepared", "uncertain", "accepted", "review", "current", "changed", "missing", "error"}) {
        names[key] = std::string(ctx.tr(std::string("project.runs.") + key));
      }
      for (const auto *key : {"cancelled", "cancelling", "failed", "preparing", "queued", "running", "submitting", "succeeded", "unknown"}) {
        names[key] = std::string(ctx.tr(std::string("jobs.state.") + key));
      }
      for (const auto *key : {"prepare", "submit", "refresh", "cancel", "collect"}) {
        names[key] = std::string(ctx.tr(std::string("batch.operation_") + key));
      }
      std::vector<std::string> member_rows;
      for (const auto &entry : entries) { member_rows.push_back(row_label(ctx.store, cases, io::get_string(entry, "record_id"))); }
      table.cell = [entries, outcomes, names, member_rows, engine](int row, int column) {
        const auto id = io::get_string(entries.at(row), "record_id");
        const auto result = outcomes.value(id, Json::object());
        if (column == 0) {
          const auto values = entries.at(row).value("values", Json::object());
          return values.is_object() ? member_rows.at(size_t(row)) + " · " + io::get_string(values, "name") + " · " +
                                      values.value("temperature", Json()).dump() + (std::string(engine.id) == "muferro/1" ? " K" : "") : id;
        }
        if (column == 1) {
          const auto phase = io::get_string(result, "state", "unprepared");
          const auto parameters = io::get_string(result, "parameter_state");
          return io::get_string(names, phase, phase) + (parameters.empty() ? "" : " / " + io::get_string(names, parameters, parameters));
        }
        const auto operation = io::get_string(result, "operation");
        return io::get_string(names, operation, operation) + " " + io::get_string(result, "error");
      };
      const auto batch = batch_id_;
      table.selected = {[this, entries] {
        for (size_t i = 0; i < entries.size(); ++i) { if (io::get_string(entries[i], "record_id") == batch_member_) { return int(i); } }
        return -1;
      }, [this, &state, project, handle, generation, batch, entries](int row) {
        if (context_current(state, project, handle, generation) && batch_id_ == batch && row >= 0 && size_t(row) < entries.size()) {
          batch_member_ = io::get_string(entries[row], "record_id");
        }
      }};
      panel->table("members", std::move(table));
      auto actions = [&](const bool single) {
        auto &buttons = panel->row();
        for (const std::string operation : {"prepare", "submit", "refresh", "cancel", "collect"}) {
          const std::vector<std::string> selected = {batch_member_};
          buttons.button((single ? "one_" : "all_") + operation, ctx.tr("batch." + (single ? std::string("one_") : std::string("all_")) + operation),
            [this, &state, &scripts, project, handle, generation, revision, batch, operation, single, selected, engine] {
              if (!context_current(state, project, handle, generation) || batch_id_ != batch ||
                  (single && batch_member_ != selected.front())) { return; }
              Json params = {{"project_id", project}, {"expected_revision", revision}, {"batch_id", batch}};
              if (single) { params["record_ids"] = selected; }
              execute(scripts, engine.id, "batch_" + operation, params);
            }).disable(!enabled || (single && batch_member_.empty()));
        }
      };
      actions(false);
      actions(true);
      const Json outcome = outcomes.value(batch_member_, Json::object());
      const auto run = io::get_string(outcome, "run_id");
      const auto member = batch_member_;
      panel->button("run", ctx.tr("batch.run"), [this, &state, project, handle, generation, batch, member, run] {
        if (context_current(state, project, handle, generation) && batch_id_ == batch && batch_member_ == member) { state.select_run(run); }
      }).disable(!enabled || run.empty());
    }
    else { panel->paragraph(ctx.tr("batch.inspect_only")); }
  }
  hint(*panel, ctx, "batch.retry_hint");
  panel->log_view("output", scripts.output(), 4);
}
}  // namespace stk::app
