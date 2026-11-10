/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "simulation_preflight.hh"
#include "simulation_target.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/bridge/client.hh"
#include "stk/wm/window.hh"
#include <algorithm>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
Json preflight_options(const Json &source)
{
  Json result = {{"backend", "local"}, {"name", ""}};
  for (const auto *key : {"backend", "walltime_seconds", "memory_mb", "queue", "account", "name"}) {
    if (source.contains(key)) { result[key] = source.at(key); }
  }
  return result;
}
const Json *find_record(const Json &records, const std::string &id)
{
  const auto found = std::find_if(records.begin(), records.end(), [&](const Json &r) { return io::get_string(r, "id") == id; });
  return found == records.end() ? nullptr : &*found;
}
bool pending(const Json &record)
{
  const auto phase = io::get_string(record, "phase");
  return phase == "prepared" || phase == "creating_workspace" || phase == "submitting" || phase == "unknown" || phase == "accepted" || phase == "running";
}
} // namespace

void SimulationPreflight::suspend()
{
  if (!active_) { return; }
  ++epoch_; active_ = false; auto_poll_ = false;
  describe_busy_ = spaces_busy_ = records_busy_ = action_busy_ = false;
  identity_.clear(); spaces_loaded_ = records_loaded_ = false;
  created_request_.clear();
  metadata_failed_ = false;
  previous_current_ = {};
}

void SimulationPreflight::request(EditorContext ctx, const std::string &method, const Json &params,
                                  Current current, std::function<void(const Json &)> receive)
{
  auto *client = ctx.store.bridge();
  if (!client || !current()) { return; }
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  const auto weak = std::weak_ptr<bool>(alive_);
  auto *area = &ctx.area;
  client->call(method, params, options).then([this, weak, current = std::move(current), receive = std::move(receive), area]
      (const bridge::Result<Json> &reply) {
    if (weak.expired() || !current()) { return; }
    if (!reply) {
      describe_busy_ = spaces_busy_ = records_busy_ = action_busy_ = false;
      auto_poll_ = false; error_ = reply.error().message;
      metadata_failed_ = true;
      // A failed submission may have been accepted. Recover its journal through list; never POST here.
      records_loaded_ = false;
    }
    else {
      try { receive(reply.value()); }
      catch (const std::exception &error) { action_busy_ = false; auto_poll_ = false; error_ = error.what(); }
    }
    area->tag_redraw();
  });
}

void SimulationPreflight::accept_record(const Json &reply, const std::string &expected_id,
                                        const EditorContext &ctx, const Current &current)
{
  const auto &record = reply.at("record");
  if (io::get_string(record, "project_id") != project_ ||
      io::get_string(record.at("request"), "connection") != connection_) {
    throw std::runtime_error("The diagnostic record belongs to another project or execution environment");
  }
  const auto id = io::get_string(record, "id");
  if (id != expected_id || io::get_string(record.at("request"), "idempotency_key") != expected_id) {
    throw std::runtime_error("The diagnostic reply belongs to another request");
  }
  auto found = std::find_if(records_.begin(), records_.end(), [&](const Json &r) { return io::get_string(r, "id") == id; });
  if (found == records_.end()) { records_.insert(records_.begin(), record); }
  else { *found = record; }
  selected_ = id;
  action_busy_ = false;
  const auto phase = io::get_string(record, "phase");
  if (phase != "accepted" && phase != "running") { auto_poll_ = false; }
  if (phase == "finished" && id == created_request_ && workspace_.empty() && record.at("workspace_id").is_string()) {
    workspace_ = record.at("workspace_id").get<std::string>();
    if (std::none_of(spaces_.begin(), spaces_.end(), [&](const Json &row) { return io::get_string(row, "id") == workspace_; })) {
      spaces_.push_back({{"id", workspace_}, {"name", "STK MuPRO preflight"}});
    }
    created_request_.clear();
    ++epoch_; // Retained callbacks from the previous new-workspace selection are now stale.
  }
  constexpr uint64_t poll_interval_ms = 500;
  next_poll_ = Clock::now() + std::chrono::milliseconds(poll_interval_ms);
  if (auto_poll_ && next_poll_ < poll_deadline_ && current()) {
    if (auto *manager = ctx.area.shell().window_manager()) {
      // The normal window sleeps after drawing the accepted/running state.
      // Wake it for the next observation, provided the original view is still visible.
      manager->add_timer(poll_interval_ms + 1, 0, [area = &ctx.area, current] {
        if (current()) { area->tag_redraw(); }
      });
    }
  }
}

void SimulationPreflight::draw(ui::Layout &panel, EditorContext &ctx, ProjectState &state,
                               SimulationTarget &target, const std::string &connection,
                               const Json &source_options, Current current)
{
  if (previous_current_ && !previous_current_()) { suspend(); }
  auto *store = &ctx.store;
  auto *client = store->bridge();
  const auto hello = client ? client->hello_info() : std::nullopt;
  if (!hello || !hello->has_method("mupro.preflight.reserve") || !hello->has_method("mupro.preflight.refresh")) {
    panel.paragraph(ctx.tr("preflight.upgrade")); return;
  }
  if (connection.empty() || store->jobs().hub()) { panel.paragraph(ctx.tr("preflight.choose_runtime")); return; }
  const auto &project = *state.project();
  if (project_ != project.id || connection_ != connection) {
    suspend();
    if (project_ != project.id) { records_ = Json::array(); selected_.clear(); }
    project_ = project.id; connection_ = connection; workspace_.clear(); spaces_ = Json::array();
    if (const auto *record = find_record(records_, selected_);
        record && io::get_string(record->at("request"), "connection") != connection) { selected_.clear(); }
  }
  active_ = true;
  auto *area = &ctx.area;
  auto *shell = &area->shell();
  auto *screen = area->screen();
  if (!screen) { return; }
  auto *origin = &area->editor();
  const auto parent_path = area->id() + "/main/project_simulation";
  const auto *parent_header = ctx.ui ? ctx.ui->find(parent_path) : nullptr;
  const auto *header = ctx.ui ? ctx.ui->find(parent_path + "/execution_preflight") : nullptr;
  if (!parent_header || !header) { suspend(); return; }
  const auto parent_id = parent_header->id;
  const auto panel_id = header->id;
  auto *ui_context = ctx.ui;
  const auto weak = std::weak_ptr<bool>(alive_);
  const auto guard = [this, weak, current = std::move(current), store, client, area, shell, screen, origin,
      project_id = project.id, handle = project.handle, version = state.version(), &state, &target,
      bridge_epoch = store->bridge_epoch(), scope_epoch = store->project_scope_epoch(), pid = client->bridge_pid(),
      connection_epoch = store->jobs().connection_epoch(), option_epoch = target.options_epoch(),
      area_epoch = area->activity_epoch(), visibility_epoch = screen->visibility_epoch(), epoch = epoch_,
      ui_context, parent_id, parent_epoch = ui_context->panel_epoch(parent_id),
      panel_id, panel_epoch = ui_context->panel_epoch(panel_id)] {
    return !weak.expired() && active_ && epoch_ == epoch && store->bridge() == client &&
        store->bridge_epoch() == bridge_epoch && store->project_scope_epoch() == scope_epoch && client->bridge_pid() == pid &&
        state.ready() && state.project() && state.project()->id == project_id && state.project()->handle == handle && state.version() == version &&
        store->jobs().connection_epoch() == connection_epoch && target.options_epoch() == option_epoch &&
        shell->has_area(area) && area->screen() == screen && area->activity_epoch() == area_epoch &&
        screen->ui() == ui_context &&
        ui_context->panel_open(parent_id, false) && ui_context->panel_epoch(parent_id) == parent_epoch &&
        ui_context->panel_open(panel_id, false) && ui_context->panel_epoch(panel_id) == panel_epoch &&
        screen->visibility_epoch() == visibility_epoch && &area->editor() == origin &&
        (!screen->maximized() || screen->maximized() == area) && current();
  };
  previous_current_ = guard;
  const Json options = preflight_options(source_options);
  if (identity_.empty() && !describe_busy_ && !metadata_failed_) {
    describe_busy_ = true;
    request(ctx, "mupro.preflight.describe", {{"connection", connection}}, guard, [this](const Json &reply) {
      describe_busy_ = false;
      if (io::get_string(reply, "connection") != connection_) { throw std::runtime_error("Execution environment identity does not match"); }
      identity_ = io::get_string(reply, "connection_identity");
    });
  }
  if (!spaces_loaded_ && !spaces_busy_ && !metadata_failed_) {
    spaces_busy_ = true;
    request(ctx, "workspace.list", {{"connection", connection}}, guard, [this](const Json &reply) {
      spaces_busy_ = false; spaces_loaded_ = true; spaces_ = reply.at("workspaces");
    });
  }
  if (!records_loaded_ && !records_busy_ && !metadata_failed_) {
    records_busy_ = true;
    request(ctx, "mupro.preflight.list", {{"project_id", project_}}, guard, [this](const Json &reply) {
      records_busy_ = false; records_loaded_ = true; records_ = reply.at("records");
      if (!find_record(records_, selected_)) {
        selected_.clear();
        for (const auto &record : records_) {
          if (io::get_string(record.at("request"), "connection") == connection_) { selected_ = io::get_string(record, "id"); break; }
        }
      }
    });
  }
  std::vector<std::string> ids = {""}, names = {std::string(ctx.tr("preflight.new_workspace"))};
  for (const auto &row : spaces_) {
    if (ids.size() >= 257) { break; }
    ids.push_back(io::get_string(row, "id")); names.push_back(io::get_string(row, "name", ids.back()));
  }
  const auto selected_space = std::find_if(spaces_.begin(), spaces_.end(), [&](const Json &row) { return io::get_string(row, "id") == workspace_; });
  const bool workspace_available = workspace_.empty() || selected_space != spaces_.end();
  if (!workspace_.empty() && std::find(ids.begin(), ids.end(), workspace_) == ids.end()) {
    if (ids.size() == 257) { ids.pop_back(); names.pop_back(); }
    ids.push_back(workspace_);
    names.push_back(selected_space == spaces_.end() ? workspace_ : io::get_string(*selected_space, "name", workspace_));
  }
  panel.prop(ctx.tr("preflight.workspace")).dropdown("preflight_workspace", std::move(names), {
    [this, ids] { const auto it = std::find(ids.begin(), ids.end(), workspace_); return it == ids.end() ? 0 : int(it - ids.begin()); },
    [this, ids, guard](int i) { if (guard() && i >= 0 && size_t(i) < ids.size() && workspace_ != ids[size_t(i)]) {
      workspace_ = ids[size_t(i)]; ++epoch_; auto_poll_ = false; action_busy_ = false;
    } }
  }).disable(action_busy_);
  const bool duplicate = std::any_of(records_.begin(), records_.end(), [&](const Json &r) {
    return io::get_string(r.at("request"), "connection") == connection_ && r.at("request").at("options") == options && pending(r);
  });
  const Json params = {{"project_id", project_}, {"connection", connection_}, {"expected_connection_identity", identity_},
                       {"workspace_id", workspace_.empty() ? Json(nullptr) : Json(workspace_)}, {"options", options}};
  panel.button("preflight_submit", ctx.tr(workspace_.empty() ? "preflight.create_check" : "preflight.check"),
      [this, ctx, guard, params] {
    if (!guard() || action_busy_) { return; }
    auto request_params = params;
    const auto key = new_idempotency_key();
    request_params["idempotency_key"] = key;
    created_request_ = params.at("workspace_id").is_null() ? key : "";
    action_busy_ = true; error_.clear(); auto_poll_ = true;
    poll_deadline_ = Clock::now() + std::chrono::seconds(120);
    // No execution RPC is sent until the durable reservation has been acknowledged.
    request(ctx, "mupro.preflight.reserve", request_params, guard, [this, ctx, guard, key](const Json &reply) {
      accept_record(reply, key, ctx, guard);
      if (!guard() || io::get_string(reply.at("record"), "phase") != "prepared") { return; }
      action_busy_ = true; auto_poll_ = true;
      request(ctx, "mupro.preflight.retry", {{"project_id", project_}, {"id", key}}, guard,
          [this, ctx, guard, key](const Json &sent) { accept_record(sent, key, ctx, guard); });
    });
  }).disable(identity_.empty() || !records_loaded_ || metadata_failed_ || !workspace_available || action_busy_ || duplicate);
  panel.paragraph(ctx.tr("preflight.effect"));
  if (!error_.empty()) { panel.paragraph(error_); }
  if (metadata_failed_) {
    panel.button("preflight_reload", ctx.tr("preflight.reload"), [this, guard] {
      if (!guard()) { return; }
      suspend(); error_.clear();
    });
  }
  std::vector<std::string> record_ids, record_names;
  for (const auto &r : records_) {
    if (io::get_string(r.at("request"), "connection") != connection_) { continue; }
    record_ids.push_back(io::get_string(r, "id"));
    record_names.push_back(io::get_string(r, "created_at") + " · " + std::string(ctx.tr("preflight.status." + io::get_string(r, "phase"))));
  }
  if (record_ids.empty()) { return; }
  panel.prop(ctx.tr("preflight.history")).dropdown("preflight_history", std::move(record_names), {
    [this, record_ids] { const auto it = std::find(record_ids.begin(), record_ids.end(), selected_); return it == record_ids.end() ? -1 : int(it - record_ids.begin()); },
    [this, record_ids, guard](int i) { if (guard() && i >= 0 && size_t(i) < record_ids.size() && selected_ != record_ids[size_t(i)]) {
      selected_ = record_ids[size_t(i)]; ++epoch_; auto_poll_ = false; action_busy_ = false;
    } }
  });
  const auto *record = find_record(records_, selected_);
  if (!record) { return; }
  const auto phase = io::get_string(*record, "phase");
  const auto task_id = io::get_string(*record, "task_id");
  panel.paragraph(std::string(ctx.tr("preflight.status." + phase)) + (task_id.empty() ? "" : " · " + task_id));
  panel.paragraph(std::string(ctx.tr("preflight.saved_backend")) + ": " +
      std::string(ctx.tr("simulation.backend." + io::get_string(record->at("request").at("options"), "backend"))));
  const Json selected_params = {{"project_id", project_}, {"id", selected_}};
  if ((phase == "prepared" || phase == "unknown") && task_id.empty()) {
    panel.paragraph(ctx.tr(phase == "prepared" ? "preflight.saved" : "preflight.uncertain"));
    panel.paragraph(std::string(ctx.tr("preflight.request_id")) + ": " + selected_);
    const bool creates_workspace = record->at("request").at("workspace_id").is_null();
    panel.button("preflight_retry", ctx.tr(phase == "prepared" ? "preflight.start_saved" : "preflight.retry"), [this, ctx, guard, selected_params, creates_workspace] {
      if (!guard() || action_busy_) { return; }
      action_busy_ = true; error_.clear(); auto_poll_ = true; poll_deadline_ = Clock::now() + std::chrono::seconds(120);
      if (creates_workspace && workspace_.empty()) { created_request_ = io::get_string(selected_params, "id"); }
      request(ctx, "mupro.preflight.retry", selected_params, guard, [this, ctx, guard, selected_params](const Json &reply) {
        accept_record(reply, io::get_string(selected_params, "id"), ctx, guard);
      });
    }).disable(action_busy_);
  }
  const auto refresh = [this, ctx, guard, selected_params] {
    if (!guard() || action_busy_) { return; }
    action_busy_ = true; error_.clear();
    request(ctx, "mupro.preflight.refresh", selected_params, guard, [this, ctx, guard, selected_params](const Json &reply) {
      accept_record(reply, io::get_string(selected_params, "id"), ctx, guard);
    });
  };
  panel.button("preflight_refresh", ctx.tr("preflight.refresh"), [this, guard, refresh] {
    if (!guard()) { return; }
    auto_poll_ = true; poll_deadline_ = Clock::now() + std::chrono::seconds(120); refresh();
  }).disable(action_busy_);
  if (!record->at("error").is_null()) { panel.paragraph(io::get_string(record->at("error"), "message")); }
  const auto &result = record->at("result");
  if (!result.is_null()) {
    const auto &observation = result.at("observation");
    panel.paragraph(ctx.tr("preflight.summary." + io::get_string(observation, "summary")));
    panel.paragraph(io::get_string(observation, "observed_at"));
    for (const auto &check : observation.at("checks")) {
      panel.label(std::string(ctx.tr("preflight.item." + io::get_string(check, "id"))) + ": " +
                  std::string(ctx.tr("preflight.value." + io::get_string(check, "status"))));
    }
    panel.paragraph(ctx.tr("preflight.unverified"));
  }
  if (auto_poll_ && !action_busy_ && Clock::now() < poll_deadline_ && Clock::now() >= next_poll_ &&
      (phase == "accepted" || phase == "running")) { refresh(); }
}
} // namespace stk::app
