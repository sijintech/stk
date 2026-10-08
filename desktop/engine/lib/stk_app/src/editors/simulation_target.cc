/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "simulation_target.hh"
#include "project_navigation.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "editor_text.hh"
#include <algorithm>

namespace stk::app {
namespace {
using io::Json;
const std::vector<std::string> kSimulationBackends = {"local", "slurm", "pbs"};
}  // namespace

std::string SimulationTarget::runtime_controls(ui::Layout &panel, EditorContext &ctx)
{
  auto &jobs = ctx.store.jobs();
  std::vector<std::string> names, ids;
  std::string active;
  for (const auto &row : jobs.connections()) {
    if (row.info.kind != "runtime") { continue; }  // Batches and plans name a saved direct or SSH Runtime.
    ids.push_back(row.info.id);
    names.push_back((row.info.name.empty() ? row.info.id : row.info.name) + "  ·  " + std::string(ctx.tr(health_key(row.health))));
    if (row.info.id == jobs.active_id() && row.health != Health::Offline) { active = row.info.id; }
  }
  auto &line = panel.prop(ctx.tr("simulation.runtime")).row(true);
  if (ids.empty()) { line.label(ctx.tr("simulation.no_runtime")); }
  else {
    line.dropdown("runtime", std::move(names), {
      [&jobs, ids] { const auto it = std::find(ids.begin(), ids.end(), jobs.active_id()); return it == ids.end() ? -1 : int(it - ids.begin()); },
      [&jobs, ids](int i) { if (i >= 0 && size_t(i) < ids.size() && ids[size_t(i)] != jobs.active_id()) { jobs.select_connection(ids[size_t(i)]); } }
    });
  }
  line.button("manage_runtimes", ctx.tr("simulation.manage_runtimes"), editor_navigation_action(ctx, kEditorJobs, true)).width(6);
  return active;
}

std::optional<Json> SimulationTarget::options_controls(ui::Layout &panel, EditorContext &ctx)
{
  const Json options = Json::parse(options_, nullptr, false);
  const bool valid = options.is_object();
  // Each field edits one key of the same JSON object, so keys only the advanced text sets are kept.
  const auto set = [this](const std::string &key, Json value) {
    Json edited = Json::parse(options_, nullptr, false);
    if (!edited.is_object()) { return; }
    if (value.is_null()) { edited.erase(key); }
    else { edited[key] = std::move(value); }
    options_ = edited.dump();
  };
  const auto number = [this](const char *key, const double fallback) {
    const Json current = Json::parse(options_, nullptr, false);
    return current.is_object() && current.contains(key) && current.at(key).is_number() ? current.at(key).get<double>() : fallback;
  };
  const std::string backend = valid && options.value("backend", Json("local")).is_string() ? options.value("backend", std::string("local")) : "local";
  std::vector<std::string> backend_names;
  for (const auto &name : kSimulationBackends) { backend_names.emplace_back(ctx.tr("simulation.backend." + name)); }
  panel.prop(ctx.tr("simulation.backend")).dropdown("backend", std::move(backend_names), {
    [backend] { const auto it = std::find(kSimulationBackends.begin(), kSimulationBackends.end(), backend); return it == kSimulationBackends.end() ? -1 : int(it - kSimulationBackends.begin()); },
    [set](int i) { if (i >= 0 && size_t(i) < kSimulationBackends.size()) { set("backend", kSimulationBackends[size_t(i)]); } }
  }).disable(!valid);
  const ui::NumberProps count{.min = 1, .max = 65536, .step = 1, .integer = true};
  panel.prop(ctx.tr("simulation.ranks")).number("ranks", "", {
    [number] { return number("ranks", 1); }, [set](double value) { set("ranks", int64_t(value)); }}, count).disable(!valid);
  panel.prop(ctx.tr("simulation.threads")).number("threads_per_rank", "", {
    [number] { return number("threads_per_rank", 1); }, [set](double value) { set("threads_per_rank", int64_t(value)); }}, count).disable(!valid);
  const bool cluster = backend != "local";
  if (cluster) {
    panel.prop(ctx.tr("simulation.walltime")).number("walltime", "", {
      [number] { return std::max(1.0, number("walltime_seconds", 0) / 60.0); },
      [set](double minutes) { set("walltime_seconds", int64_t(minutes) * 60); }},
      {.min = 1, .max = 60 * 24 * 30, .step = 10, .integer = true}).disable(!valid);
  }
  if (auto *advanced = panel.panel("advanced_options", ctx.tr("simulation.options_advanced"), false)) {
    hint(*advanced, ctx, "simulation.options_hint");
    advanced->text_field("options", ui::bind(options_), {.max_length = 65536, .mono = true});
  }
  if (!valid) {
    panel.paragraph(ctx.tr("simulation.options_invalid"));
    return std::nullopt;
  }
  if (cluster && !options.contains("walltime_seconds")) {
    panel.paragraph(ctx.tr("simulation.walltime_required"));
    return std::nullopt;
  }
  return options;
}

std::string SimulationTarget::runtime_name(EditorContext &ctx, const std::string &connection)
{
  for (const auto &row : ctx.store.jobs().connections()) {
    if (row.info.id == connection && !row.info.name.empty()) { return row.info.name; }
  }
  return connection.rfind("runtime:", 0) == 0 ? connection.substr(8) : connection;
}
}  // namespace stk::app
