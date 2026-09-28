/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_simulation_view.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/platform/file_dialog.hh"
#include <algorithm>

namespace stk::app {
namespace {
using io::Json;
constexpr auto cases_id = "27e50c45-2d61-523c-a56b-f505bbd595c5";

bool execute(ScriptState &scripts, const std::string &action, const Json &params)
{
  // Both literals encode data only, including quotes, newlines and non-ASCII paths.
  return scripts.execute("import json as _stk_json\n"
      "from suan.workflows.muferro import native_action as _stk_muferro\n"
      "_stk_muferro(stk, " + Json(action).dump() + ", _stk_json.loads(" + Json(params.dump()).dump() + ")); None");
}
}  // namespace

void ProjectSimulationView::draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
  if (project_ != state.project()->id) {
    project_ = state.project()->id;
    source_.clear();
    error_.clear();
    batch_selection_.clear();
    batch_id_.clear();
    batch_member_.clear();
  }
  auto *panel = layout.panel("project_simulation", ctx.tr("simulation.title"), false);
  if (!panel) { return; }
  auto &scripts = ctx.store.scripts();
  auto &jobs = ctx.store.jobs();
  scripts.sync();
  jobs.sync();
  const bool enabled = state.ready() && !state.busy() && state.project()->format_version >= 5 && scripts.ready() && !scripts.busy();
  const auto project = state.project()->id;
  const auto revision = state.project()->revision;
  const auto record = state.record_id();
  const auto run = state.run_id();
  panel->paragraph(ctx.tr("simulation.hint"));
  if (!error_.empty()) { panel->paragraph(error_); }
  if (!scripts.error().empty()) { panel->paragraph(scripts.error()); }
  panel->prop(ctx.tr("simulation.directory")).text_field("simulation_source", ui::bind(source_));
  panel->button("simulation_import", ctx.tr("simulation.import"), [this, &scripts, project, revision] {
    const auto paths = platform::split_path_list(source_);
    if (paths.size() != 1) { error_ = "Choose one case directory"; return; }
    error_.clear();
    execute(scripts, "import", {{"project_id", project}, {"expected_revision", revision}, {"source", paths.front()}});
  }).disable(!enabled || source_.empty());
  panel->paragraph(ctx.tr("simulation.connection_hint"));
  panel->label(jobs.active_id().empty() ? std::string(ctx.tr("simulation.no_connection")) : jobs.active_id());
  panel->prop(ctx.tr("simulation.options")).text_field("simulation_options", ui::bind(options_));
  const auto connection = jobs.active_id();
  panel->button("simulation_prepare", ctx.tr("simulation.prepare"), [this, &scripts, project, revision, record, connection] {
    Json options = Json::parse(options_, nullptr, false);
    if (!options.is_object()) { error_ = "Execution options must be a JSON object"; return; }
    error_.clear();
    execute(scripts, "prepare", {{"project_id", project}, {"expected_revision", revision},
        {"record_id", record}, {"connection", connection}, {"options", options}});
  }).disable(!enabled || state.table_id() != cases_id || record.empty() || connection.empty() || jobs.hub());
  panel->paragraph(ctx.tr("simulation.run_hint"));
  const bool selected = !run.empty() && !state.run().empty() && io::get_string(state.run(), "id") == run;
  bool accepted = false, succeeded = false, muferro = false;
  if (selected) {
    const auto &plan = state.run().at("plan");
    muferro = io::get_string(plan.at("parameters"), "table_id") == cases_id;
    const auto &status = state.run().at("status");
    accepted = status.contains("task") && status.at("task").is_object();
    succeeded = accepted && io::get_string(status.at("task"), "state") == "succeeded";
    panel->paragraph(io::get_string(plan, "label"));
  }
  auto &actions = panel->row();
  actions.button("simulation_logs", ctx.tr("simulation.logs"), [&scripts, project, run] {
    execute(scripts, "logs", {{"project_id", project}, {"run_id", run}});
  }).disable(!enabled || !muferro || !accepted);
  actions.button("simulation_collect", ctx.tr("simulation.collect"), [&scripts, project, run] {
    execute(scripts, "collect", {{"project_id", project}, {"run_id", run}});
  }).disable(!enabled || !muferro || !succeeded);
  actions.button("simulation_view", ctx.tr("simulation.view"), [&scripts, project, run] {
    execute(scripts, "view", {{"project_id", project}, {"run_id", run}});
  }).disable(!enabled || !muferro || !succeeded || !scripts.desktop_ready());
  panel->label(ctx.tr(scripts.busy() ? "simulation.busy" : "simulation.output"));
  if (scripts.status().contains("run") && scripts.status()["run"].is_object()) {
    panel->label(ctx.tr("script.run_state." + io::get_string(scripts.status()["run"], "state")));
  }
  panel->log_view("simulation_output", scripts.output(), 6);
}

void ProjectSimulationView::draw_batches(ui::Layout &layout, EditorContext &ctx, ProjectState &state)
{
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
  const auto revision = state.project()->revision;
  const bool case_selected = state.table_id() == cases_id && !state.record_id().empty();
  const auto record = state.record_id();
  panel->paragraph(ctx.tr("batch.hint"));
  auto &selection = panel->row();
  selection.button("add", ctx.tr("batch.add"), [this, record] {
    if (batch_selection_.size() < 100 && std::find(batch_selection_.begin(), batch_selection_.end(), record) == batch_selection_.end()) {
      batch_selection_.push_back(record);
    }
  }).disable(!enabled || !case_selected || batch_selection_.size() >= 100);
  selection.button("remove", ctx.tr("batch.remove"), [this, record] {
    batch_selection_.erase(std::remove(batch_selection_.begin(), batch_selection_.end(), record), batch_selection_.end());
  }).disable(!enabled || std::find(batch_selection_.begin(), batch_selection_.end(), record) == batch_selection_.end());
  selection.button("all", ctx.tr("batch.all"), [this, &state] {
    batch_selection_.clear();
    for (const auto &table : state.tables()) {
      if (table.id == cases_id && table.records.size() <= 100) {
        for (const auto &row : table.records) { batch_selection_.push_back(row.id); }
      }
    }
  }).disable(!enabled || !case_selected || state.table()->records.size() > 100);
  selection.button("clear", ctx.tr("batch.clear"), [this] { batch_selection_.clear(); }).disable(!enabled || batch_selection_.empty());
  panel->button("clone", ctx.tr("batch.clone"), [&scripts, project, revision, record] {
    execute(scripts, "clone", {{"project_id", project}, {"expected_revision", revision}, {"record_id", record}});
  }).disable(!enabled || !case_selected);
  panel->label(std::string(ctx.tr("batch.selection")) + " " + std::to_string(batch_selection_.size()));
  std::vector<std::vector<std::string>> selected_cells;
  for (const auto &table : state.tables()) {
    if (table.id != cases_id) { continue; }
    for (const auto &row : table.records) {
      if (std::find(batch_selection_.begin(), batch_selection_.end(), row.id) != batch_selection_.end()) {
        selected_cells.push_back({io::get_string(row.values, "b29f3eda-8426-50f5-a6d8-c2e6307f28a4") + " · " + row.id.substr(0, 8),
            row.values.value("7e96da82-9b05-5f99-981e-8bf38a2028d2", Json()).dump()});
      }
    }
  }
  if (!selected_cells.empty()) {
    ui::TableSpec selection_table;
    selection_table.columns = {{std::string(ctx.tr("batch.case")), 12.0f}, {"K", 8.0f}};
    selection_table.rows = int(selected_cells.size());
    selection_table.visible_rows = float(std::clamp(int(selected_cells.size()), 1, 4));
    selection_table.cell = [selected_cells](int row, int col) { return selected_cells.at(row).at(col); };
    panel->table("selection", std::move(selection_table));
  }
  panel->prop(ctx.tr("simulation.options")).text_field("options", ui::bind(options_));
  const auto connection = jobs.active_id();
  panel->label(connection.empty() ? std::string(ctx.tr("simulation.no_connection")) : connection);
  const auto members = batch_selection_;
  panel->button("create", ctx.tr("batch.create"), [this, &scripts, project, revision, members, connection] {
    Json options = Json::parse(options_, nullptr, false);
    if (!options.is_object()) { error_ = "Execution options must be a JSON object"; return; }
    error_.clear();
    execute(scripts, "batch_create", {{"project_id", project}, {"expected_revision", revision}, {"template_id", "muferro/1"},
        {"record_ids", members}, {"connection", connection}, {"options", options}});
  }).disable(!enabled || members.empty() || connection.empty() || jobs.hub());
  if (!error_.empty()) { panel->paragraph(error_); }

  std::vector<std::string> ids, names;
  const ProjectTable *batches = nullptr;
  for (const auto &table : state.tables()) { if (table.id == batches_id) { batches = &table; break; } }
  if (batches) {
    for (const auto &row : batches->records) { ids.push_back(row.id); names.push_back(io::get_string(row.values, name_id, row.id)); }
  }
  if (!ids.empty() && std::find(ids.begin(), ids.end(), batch_id_) == ids.end()) { batch_id_ = ids.back(); batch_member_.clear(); }
  panel->prop(ctx.tr("batch.saved")).dropdown("saved", std::move(names), {
    [this, ids] { const auto it = std::find(ids.begin(), ids.end(), batch_id_); return it == ids.end() ? -1 : int(it - ids.begin()); },
    [this, ids](int row) { if (row >= 0 && size_t(row) < ids.size()) { batch_id_ = ids[row]; batch_member_.clear(); } }
  });
  if (batches && std::find(ids.begin(), ids.end(), batch_id_) != ids.end()) {
    const auto index = std::find(ids.begin(), ids.end(), batch_id_) - ids.begin();
    const auto &values = batches->records[index].values;
    const Json intent = values.value(intent_id, Json());
    const Json outcomes = values.value(outcomes_id, Json());
    if (intent.is_object() && intent.contains("entries") && intent["entries"].is_array() && outcomes.is_object() &&
        std::all_of(intent["entries"].begin(), intent["entries"].end(), [](const Json &entry) { return entry.is_object(); }) &&
        std::all_of(outcomes.begin(), outcomes.end(), [](const Json &entry) { return entry.is_object(); })) {
      const auto entries = intent["entries"];
      panel->label(io::get_string(intent, "template") + " · " + io::get_string(intent, "connection"));
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
      table.cell = [entries, outcomes, names](int row, int column) {
        const auto id = io::get_string(entries.at(row), "record_id");
        const auto result = outcomes.value(id, Json::object());
        if (column == 0) {
          const auto values = entries.at(row).value("values", Json::object());
          return values.is_object() ? io::get_string(values, "name") + " · " + values.value("temperature", Json()).dump() + " K · " + id.substr(0, 8) : id;
        }
        if (column == 1) {
          const auto phase = io::get_string(result, "state", "unprepared");
          const auto parameters = io::get_string(result, "parameter_state");
          return io::get_string(names, phase, phase) + (parameters.empty() ? "" : " / " + io::get_string(names, parameters, parameters));
        }
        const auto operation = io::get_string(result, "operation");
        return io::get_string(names, operation, operation) + " " + io::get_string(result, "error");
      };
      table.selected = {[this, entries] {
        for (size_t i = 0; i < entries.size(); ++i) { if (io::get_string(entries[i], "record_id") == batch_member_) { return int(i); } }
        return -1;
      }, [this, entries](int row) { if (row >= 0 && size_t(row) < entries.size()) { batch_member_ = io::get_string(entries[row], "record_id"); } }};
      panel->table("members", std::move(table));
      const auto batch = batch_id_;
      auto actions = [&](const bool single) {
        auto &buttons = panel->row();
        for (const std::string operation : {"prepare", "submit", "refresh", "cancel", "collect"}) {
          const std::vector<std::string> selected = {batch_member_};
          buttons.button((single ? "one_" : "all_") + operation, ctx.tr("batch." + (single ? std::string("one_") : std::string("all_")) + operation),
            [&scripts, project, revision, batch, operation, single, selected] {
              Json params = {{"project_id", project}, {"expected_revision", revision}, {"batch_id", batch}};
              if (single) { params["record_ids"] = selected; }
              execute(scripts, "batch_" + operation, params);
            }).disable(!enabled || (single && batch_member_.empty()));
        }
      };
      actions(false);
      actions(true);
      const Json outcome = outcomes.value(batch_member_, Json::object());
      const auto run = io::get_string(outcome, "run_id");
      panel->button("run", ctx.tr("batch.run"), [&state, run] { state.select_run(run); }).disable(!enabled || run.empty());
    }
  }
  panel->paragraph(ctx.tr("batch.retry_hint"));
  panel->log_view("output", scripts.output(), 4);
}
}  // namespace stk::app
