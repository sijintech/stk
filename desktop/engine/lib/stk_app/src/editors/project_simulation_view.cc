/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "workspace_fields.hh"
#include "project_simulation_view.hh"
#include "archive_controls.hh"
#include "project_navigation.hh"
#include "project_labels.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/jobs_spec.hh"
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

io::Json ProjectSimulationView::save_workspace_state() const
{
  if (!workspace_pending_.is_null()) { return workspace_pending_; }
  return {{"version", 1}, {"project", project_}, {"engine", engine_}, {"source", source_}, {"script", script_},
    {"study_recipe", study_recipe_}, {"study_id", study_id_}, {"batch_id", batch_id_},
    {"batch_member", batch_member_}, {"batch_selection", batch_selection_}, {"archived_batches", show_archived_batches_},
    {"muferro_target", target_.save_workspace_state()}, {"lammps_target", lammps_target_.save_workspace_state()}};
}
bool ProjectSimulationView::load_workspace_state(const Json &value)
{
  if (!workspace_fields(value, {"project", "source", "script", "study_recipe", "study_id", "batch_id", "batch_member"},
      {"engine"}, {"archived_batches"}, {"batch_selection", "muferro_target", "lammps_target"}, 1024 * 1024)) { return false; }
  if (!value.contains("batch_selection") || !value.at("batch_selection").is_array() || value.at("batch_selection").size() > 1000 ||
      !std::all_of(value.at("batch_selection").begin(), value.at("batch_selection").end(), [](const Json &item) {
        return item.is_string() && item.get_ref<const std::string &>().size() <= 64;
      })) { return false; }
  SimulationTarget muferro, lammps;
  if (!muferro.load_workspace_state(value.value("muferro_target", Json::object())) ||
      !lammps.load_workspace_state(value.value("lammps_target", Json::object()))) { return false; }
  workspace_pending_ = value; ++generation_; return true;
}

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
  study_id_.clear();
  study_create_pending_ = false;
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
    study_id_.clear();
    study_create_pending_ = false;
    study_recipe_ = "{}";
  }
  if (!workspace_pending_.is_null() && io::get_string(workspace_pending_, "project") == project_) {
    const auto value = std::move(workspace_pending_); workspace_pending_ = nullptr;
    engine_ = std::clamp(int(io::get_int(value, "engine", 0)), 0, 1);
    source_ = value.value("source", std::string()); script_ = value.value("script", std::string());
    study_recipe_ = value.value("study_recipe", std::string("{}")); study_id_ = value.value("study_id", std::string());
    batch_id_ = value.value("batch_id", std::string()); batch_member_ = value.value("batch_member", std::string());
    batch_selection_ = value.at("batch_selection").get<std::vector<std::string>>();
    show_archived_batches_ = value.value("archived_batches", false);
    target_.load_workspace_state(value.at("muferro_target")); lammps_target_.load_workspace_state(value.at("lammps_target"));
    observed_table_ = state.table_id(); ++generation_;
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
  panel->button("simulation_prepare", ctx.tr("simulation.prepare"), [this, &state, &scripts, &jobs, project, handle, generation, revision, record, connection, options, engine] {
    if (!context_current(state, project, handle, generation) || state.record_id() != record || state.table_id() != engine.cases) { return; }
    error_.clear();
    if (!(engine_ == 1 ? lammps_target_ : target_).matches(jobs, connection, options)) { return; }
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
    actions.button("simulation_structure", ctx.tr("simulation.structure"), [this, &state, &scripts, project, handle, generation, revision, run] {
      if (!context_current(state, project, handle, generation) || state.run_id() != run) { return; }
      execute(scripts, "lammps/1", "view_structure", {{"project_id", project}, {"expected_revision", revision}, {"run_id", run}});
    }).disable(!enabled || !succeeded || !scripts.desktop_ready());
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

void ProjectSimulationView::draw_pet_studies(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  sync_project(state);
  if (engine_ != 1) { return; }
  auto *panel = layout.panel("project_pet_study", ctx.tr("pet_study.title"), false);
  if (!panel) { return; }
  if (state.project()->format_version < 13) { panel->paragraph(ctx.tr("pet_study.format")); return; }
  constexpr auto table_id = "9e571686-b05d-51f5-b243-be046b33ae40";
  constexpr auto name_id = "70efa784-8a37-5b0f-9a8d-ca5e7d6fe3dd";
  auto &scripts = ctx.store.scripts();
  scripts.sync();
  if (!scripts.error().empty()) { panel->paragraph(scripts.error()); }
  auto &jobs = ctx.store.jobs();
  jobs.sync();
  const bool enabled = state.ready() && !state.busy() && scripts.ready() && !scripts.busy();
  const auto project = state.project()->id;
  const auto handle = state.project()->handle;
  const auto generation = generation_;
  const auto revision = state.project()->revision;
  const auto run_action = [&scripts](const std::string &action, const Json &parameters) {
    return scripts.execute("import json as _stk_json\nfrom suan.workflows.pet_study_native import native_action as _stk_pet\n"
                    "_stk_pet(stk, " + Json(action).dump() + ", _stk_json.loads(" + Json(parameters.dump()).dump() + ")); None");
  };
  hint(*panel, ctx, "pet_study.hint");
  panel->prop(ctx.tr("pet_study.recipe")).text_field("pet_study_recipe", ui::bind(study_recipe_));
  hint(*panel, ctx, "pet_study.recipe_hint");
  const auto connection = lammps_target_.runtime_controls(*panel, ctx);
  const auto options = lammps_target_.options_controls(*panel, ctx, "lammps/1");
  const auto recipe = Json::parse(study_recipe_, nullptr, false);
  const bool recipe_valid = recipe.is_object();
  if (!recipe_valid) { panel->paragraph(ctx.tr("pet_study.invalid_recipe")); }
  panel->button("pet_study_create", ctx.tr("pet_study.create"),
      [this, &state, &jobs, project, handle, generation, revision, connection, options, recipe, text = study_recipe_, run_action] {
    if (!context_current(state, project, handle, generation) || study_recipe_ != text || !options || !recipe.is_object()) { return; }
    if (!lammps_target_.matches(jobs, connection, options)) { return; }
    const auto hex = new_idempotency_key();
    const auto id = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) + "-" +
                    hex.substr(16, 4) + "-" + hex.substr(20);
    if (run_action("create", {{"project_id", project}, {"expected_revision", revision}, {"connection", connection},
                              {"recipe", recipe}, {"options", *options}, {"study_id", id}})) {
      // Keep the explicit new selection while the project table is arriving.
      // A failed create must never make Start silently select an older study.
      study_id_ = id;
      study_create_pending_ = true;
    }
  }).disable(!enabled || connection.empty() || !options || !recipe_valid);
  std::vector<std::string> ids, names;
  for (const auto &table : state.tables()) {
    if (table.id != table_id) { continue; }
    for (const auto &row : table.records) {
      ids.push_back(row.id);
      names.push_back(row_label(ctx.store, &table, row.id) + " · " + io::get_string(row.values, name_id, row.id));
    }
  }
  const bool selection_found = std::find(ids.begin(), ids.end(), study_id_) != ids.end();
  if (selection_found) { study_create_pending_ = false; }
  if (!study_create_pending_ && !ids.empty() && !selection_found) { study_id_ = ids.back(); }
  panel->prop(ctx.tr("pet_study.saved")).dropdown("pet_study_saved", std::move(names), {
    [this, ids] { const auto found = std::find(ids.begin(), ids.end(), study_id_); return found == ids.end() ? -1 : int(found - ids.begin()); },
    [this, &state, project, handle, generation, ids](int index) {
      if (context_current(state, project, handle, generation) && index >= 0 && size_t(index) < ids.size()) {
        study_id_ = ids[size_t(index)];
        study_create_pending_ = false;
      }
    }
  });
  const auto study = study_id_;
  const bool selected = std::find(ids.begin(), ids.end(), study) != ids.end();
  if (selected) {
    for (const auto &table : state.tables()) {
      if (table.id != table_id) { continue; }
      for (const auto &row : table.records) {
        if (row.id != study) { continue; }
        const auto intent = row.values.value("a97aee9c-0517-54a6-bc1f-bab47bb99be6", Json());
        if (intent.is_object()) {
          panel->label(ctx.store.catalog().format("pet_study.frozen_target", {
              {"runtime", SimulationTarget::runtime_name(ctx, io::get_string(intent, "connection"))}}));
        }
      }
    }
  }
  auto &actions = panel->row();
  for (const std::string action : {"get", "start", "cancel", "recover"}) {
    actions.button("pet_study_" + action, ctx.tr("pet_study." + action),
        [this, &state, project, handle, generation, revision, study, action, run_action] {
      if (!context_current(state, project, handle, generation) || study_id_ != study) { return; }
      run_action(action, {{"project_id", project}, {"expected_revision", revision}, {"study_id", study}});
    }).disable(!enabled || !selected);
  }
  panel->button("pet_study_workflows", ctx.tr("pet_study.workflows"), editor_navigation_action(ctx, "workflow", false));
  panel->button("pet_study_analyses", ctx.tr("pet_study.analyses"), editor_navigation_action(ctx, kEditorAnalysisGraph, false));
  panel->log_view("pet_study_output", scripts.output(), 6);
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
             [this, &state, &scripts, &jobs, project, handle, generation, members, batch_params, engine, connection, options] {
               if (!context_current(state, project, handle, generation) || batch_selection_ != members) { return; }
               if (!(engine_ == 1 ? lammps_target_ : target_).matches(jobs, connection, options)) { return; }
               error_.clear(); execute(scripts, engine.id, "batch_run", batch_params());
             })
      .disable(!can_run);
  run_row.button("create", ctx.tr("batch.create"), [this, &state, &scripts, &jobs, project, handle, generation, members, batch_params, engine, connection, options] {
    if (!context_current(state, project, handle, generation) || batch_selection_ != members) { return; }
    if (!(engine_ == 1 ? lammps_target_ : target_).matches(jobs, connection, options)) { return; }
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
