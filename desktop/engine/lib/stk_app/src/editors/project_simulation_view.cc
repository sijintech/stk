/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "project_simulation_view.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/platform/file_dialog.hh"

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
}  // namespace stk::app
