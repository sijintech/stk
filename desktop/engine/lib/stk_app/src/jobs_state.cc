/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/jobs_state.hh"

#include <algorithm>
#include <cmath>
#include <cctype>
#include <cstdio>
#include <filesystem>
#include <fstream>

#include "stk/app/app_store.hh"
#include "stk/core/paths.hh"
#include "stk/core/sha256.hh"
#include "stk/io/png.hh"
#include "stk/platform/file_dialog.hh"

namespace stk::app {

using bridge::Error;
using bridge::ErrorCode;

namespace {

std::string get_str(const Json &j, const char *key)
{
  if (j.is_object()) {
    const auto it = j.find(key);
    if (it != j.end() && it->is_string()) {
      return it->get<std::string>();
    }
  }
  return {};
}

std::string file_name(const std::string &path)
{
  std::string p = path;
  while (p.size() > 1 && (p.back() == '/' || p.back() == '\\')) {
    p.pop_back();
  }
  const size_t s = p.find_last_of("/\\");
  return s == std::string::npos ? p : p.substr(s + 1);
}

bool ends_with_ci(const std::string &s, std::string_view suffix)
{
  if (s.size() < suffix.size()) {
    return false;
  }
  for (size_t i = 0; i < suffix.size(); i++) {
    if (std::tolower(uint8_t(s[s.size() - suffix.size() + i])) != std::tolower(uint8_t(suffix[i]))) {
      return false;
    }
  }
  return true;
}

/** Retryable in the sense of the retry policy: the same request may succeed later. */
bool retry_worthy(const Error &e)
{
  return e.retryable || e.code == ErrorCode::Unavailable || e.code == ErrorCode::Timeout ||
         (e.code == ErrorCode::Busy && e.retryable);
}

std::string number_text(const Json &v)
{
  if (v.is_number_integer()) {
    return std::to_string(v.get<int64_t>());
  }
  if (v.is_number()) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%.6g", v.get<double>());
    return buf;
  }
  if (v.is_string()) {
    return v.get<std::string>();
  }
  return v.dump();
}

}  // namespace

/* -------------------------------------------------------------------- */
/** \name Rows
 * \{ */

TaskRow TaskRow::from_json(const Json &task)
{
  TaskRow r;
  r.raw = task;
  r.id = get_str(task, "id");
  r.state = get_str(task, "state");
  r.reason = get_str(task, "reason");
  r.created_at = get_str(task, "created_at");
  r.updated_at = get_str(task, "updated_at");
  const Json &spec = task.is_object() && task.contains("spec") ? task["spec"] : Json();
  r.name = get_str(task, "name");
  if (r.name.empty()) {
    r.name = get_str(spec, "name");
  }
  r.backend = get_str(spec, "backend");
  if (r.backend.empty()) {
    r.backend = get_str(task, "backend");
  }
  r.workspace_id = get_str(task, "workspace_id");
  if (r.workspace_id.empty()) {
    r.workspace_id = get_str(spec, "workspace_id");
  }
  if (task.is_object() && task.contains("cancel_requested") && task["cancel_requested"].is_boolean()) {
    r.cancel_requested = task["cancel_requested"].get<bool>();
  }
  if (task.is_object() && task.contains("exit_code") && task["exit_code"].is_number_integer()) {
    r.exit_code = task["exit_code"].get<int64_t>();
  }
  return r;
}

bool TaskRow::terminal() const
{
  return state == "succeeded" || state == "failed" || state == "cancelled";
}

std::string TaskRow::label() const
{
  return name.empty() ? id.substr(0, 12) : name;
}

void EventsSummary::add(const Json &event)
{
  if (!event.is_object()) {
    return;
  }
  count++;
  const std::string type = get_str(event, "type");
  const Json &d = event.contains("data") && event["data"].is_object() ? event["data"] : Json::object();
  auto num = [&](const char *k) -> std::optional<double> {
    if (d.contains(k) && d[k].is_number()) {
      return d[k].get<double>();
    }
    return std::nullopt;
  };
  if (type == "run.started") {
    app = get_str(d, "app");
    if (auto t = num("total_steps")) {
      total_steps = int64_t(*t);
    }
  }
  else if (type == "run.phase") {
    phase = get_str(d, "name");
  }
  else if (type == "progress") {
    if (auto s = num("step")) {
      step = int64_t(*s);
    }
    if (auto t = num("total_steps")) {
      total_steps = int64_t(*t);
    }
    if (auto f = num("fraction")) {
      fraction = std::clamp(*f, 0.0, 1.0);
    }
    else if (auto c = num("completed_steps"); c && total_steps > 0) {
      fraction = std::clamp(*c / double(total_steps), 0.0, 1.0);
    }
    if (const std::string p = get_str(d, "phase"); !p.empty()) {
      phase = p;
    }
  }
  else if (type == "metrics") {
    if (d.contains("values") && d["values"].is_object()) {
      for (auto it = d["values"].begin(); it != d["values"].end(); ++it) {
        metrics[it.key()] = number_text(*it);
      }
    }
    if (auto s = num("step")) {
      step = std::max(step, int64_t(*s));
    }
  }
  else if (type == "frame") {
    frames++;
  }
  else if (type == "checkpoint") {
    checkpoints++;
  }
  else if (type == "message") {
    const std::string level = get_str(d, "level");
    if (level == "warning") {
      warnings++;
    }
    else if (level == "error") {
      errors++;
    }
    last_message = (level.empty() ? std::string() : level + ": ") + get_str(d, "text");
  }
  else if (type == "run.completed") {
    completed = get_str(d, "status");
  }
  else if (type == "verification") {
    verification = get_str(d, "status");
  }
}

std::string task_state_key(const std::string &state)
{
  static const char *const known[] = {"preparing", "submitting", "queued", "running", "succeeded",
                                      "failed",    "cancelled",  "unknown"};
  for (const char *k : known) {
    if (state == k) {
      return std::string("jobs.state.") + k;
    }
  }
  return state;
}

ui::Color task_state_color(const ui::Theme & /*theme*/, const TaskRow &task)
{
  /* Text colours readable on the dark list background (the theme's state colours are meant for
   * backgrounds and are too dark for text). */
  constexpr ui::Color kRunning = ui::Color::rgb(0x6fa8ff);
  constexpr ui::Color kSucceeded = ui::Color::rgb(0x7dcf6f);
  constexpr ui::Color kFailed = ui::Color::rgb(0xff6e6e);
  constexpr ui::Color kWarning = ui::Color::rgb(0xe8a93c);
  if (task.cancelling()) {
    return kWarning;
  }
  if (task.state == "succeeded") {
    return kSucceeded;
  }
  if (task.state == "failed") {
    return kFailed;
  }
  if (task.state == "cancelled" || task.state == "unknown") {
    return kWarning;
  }
  if (task.state == "running") {
    return kRunning;
  }
  return {0, 0, 0, 0};
}

std::string format_bytes(const int64_t bytes)
{
  const char *units[] = {"B", "KiB", "MiB", "GiB", "TiB"};
  double v = double(std::max<int64_t>(0, bytes));
  int u = 0;
  while (v >= 1024.0 && u < 4) {
    v /= 1024.0;
    u++;
  }
  char buf[32];
  if (u == 0) {
    snprintf(buf, sizeof(buf), "%lld B", (long long)bytes);
  }
  else {
    snprintf(buf, sizeof(buf), v < 10 ? "%.2f %s" : (v < 100 ? "%.1f %s" : "%.0f %s"), v, units[u]);
  }
  return buf;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name JobsState: bridge
 * \{ */

struct JobsState::Alive {
  JobsState *self;
};

template<class T, class F> void JobsState::on(bridge::Future<T> future, F fn)
{
  if (!future.valid()) {
    return;
  }
  std::weak_ptr<Alive> weak = alive_;
  future.then([weak, fn = std::move(fn)](bridge::Result<T> result) mutable {
    if (weak.lock()) {
      fn(result);
    }
  });
}

JobsState::JobsState(AppStore &store) : store_(store), alive_(std::make_shared<Alive>(Alive{this}))
{
  open_external = [](const std::string &path, std::string *error) {
    return platform::open_with_system(path, error);
  };
}

JobsState::~JobsState()
{
  /* Callbacks already queued on the executor find the weak pointer expired. Nothing is cancelled:
   * closing the app never stops jobs. */
  alive_.reset();
  attach(nullptr);
  release_preview();
}

void JobsState::changed()
{
  version_++;
  store_.changed();
}

void JobsState::set_status(std::string text, const ui::ToastKind kind)
{
  status_ = {std::move(text), kind};
  store_.log(status_.text);
}

void JobsState::fail(const std::string &what, const Error &error)
{
  set_status(store_.catalog().format("jobs.status.failed", {{"what", what}, {"error", error.message}}),
             ui::ToastKind::Error);
  changed();
}

bool JobsState::ready() const
{
  return client_ && bridge_state_ == bridge::BridgeState::Ready;
}

void JobsState::sync()
{
  if (store_.bridge() != client_) {
    attach(store_.bridge());
  }
}

void JobsState::attach(bridge::Client *client)
{
  if (client == client_) {
    return;
  }
  state_listener_.reset();
  transfer_listener_.reset();
  watch_.unsubscribe();
  logs_sub_.unsubscribe();
  events_sub_.unsubscribe();
  hub_sub_.unsubscribe();
  client_ = client;
  bridge_state_ = bridge::BridgeState::Stopped;
  seen_ready_ = false;
  inspected_.clear();
  if (!client_) {
    return;
  }
  std::weak_ptr<Alive> weak = alive_;
  state_listener_ = client_->on_state([weak](bridge::BridgeState s, const std::optional<Error> &) {
    if (auto a = weak.lock()) {
      a->self->on_state(s);
    }
  });
  transfer_listener_ = client_->on_transfer([weak](const bridge::Transfer &t) {
    if (auto a = weak.lock()) {
      a->self->apply_transfer(t);
    }
  });
  on_state(client_->state());
}

void JobsState::on_state(const bridge::BridgeState state)
{
  if (state == bridge_state_) {
    return;
  }
  bridge_state_ = state;
  if (state == bridge::BridgeState::Restarting || state == bridge::BridgeState::Failed) {
    /* A new bridge process has read no hub action: approvals need hub.action again. */
    inspected_.clear();
    for (ReviewItem &r : reviews_) {
      r.inspected = false;
    }
  }
  if (state == bridge::BridgeState::Ready) {
    const bool restarted = seen_ready_;
    seen_ready_ = true;
    on_ready(restarted);
  }
  changed();
}

void JobsState::on_ready(const bool restarted)
{
  refresh_connections();
  refresh_transfers();
  if (restarted) {
    /* Subscriptions replay by themselves; reads that may have been lost are repeated. */
    if (!active_.empty()) {
      check_connection(active_);
      if (hub()) {
        refresh_actions();
      }
    }
    if (submission_ && submission_->state == SubmitState::Sending) {
      /* task.submit is re-sent by the client with its key; nothing to do. */
    }
  }
}

bridge::Target JobsState::target() const
{
  return {active_, hub() ? node_ : std::string()};
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Connections
 * \{ */

const ConnectionRow *JobsState::active() const
{
  for (const ConnectionRow &c : connections_) {
    if (c.info.id == active_) {
      return &c;
    }
  }
  return nullptr;
}

bool JobsState::hub() const
{
  if (const ConnectionRow *c = active()) {
    return c->info.kind == "hub";
  }
  return active_.rfind("hub:", 0) == 0;
}

void JobsState::set_preferred(std::string connection, std::string node, std::string workspace)
{
  preferred_connection_ = std::move(connection);
  preferred_node_ = std::move(node);
  preferred_workspace_ = std::move(workspace);
  if (active_.empty() && !preferred_connection_.empty()) {
    for (const ConnectionRow &c : connections_) {
      if (c.info.id == preferred_connection_) {
        select_connection(preferred_connection_);
        break;
      }
    }
  }
}

void JobsState::refresh_connections()
{
  if (!ready()) {
    return;
  }
  on(client_->connections_list(), [this](const bridge::Result<std::vector<bridge::ConnectionInfo>> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.connections")), r.error());
      return;
    }
    apply_connections(r.value());
  });
  refresh_local();
}

void JobsState::apply_connections(std::vector<bridge::ConnectionInfo> list)
{
  std::vector<ConnectionRow> rows;
  for (bridge::ConnectionInfo &info : list) {
    ConnectionRow row;
    for (const ConnectionRow &old : connections_) {
      if (old.info.id == info.id) {
        row = old;
      }
    }
    row.info = std::move(info);
    rows.push_back(std::move(row));
  }
  connections_ = std::move(rows);
  bool active_listed = active_.empty();
  for (const ConnectionRow &c : connections_) {
    if (c.info.id == active_) {
      active_listed = true;
    }
  }
  if (!active_listed) {
    select_connection("");
  }
  if (active_.empty() && !preferred_connection_.empty()) {
    for (const ConnectionRow &c : connections_) {
      if (c.info.id == preferred_connection_) {
        select_connection(preferred_connection_);
        break;
      }
    }
  }
  publish_connection();
  changed();
}

std::string JobsState::connection_label() const
{
  const ConnectionRow *c = active();
  if (!c) {
    return active_;
  }
  const char *health_key = "conn.health.unknown";
  switch (c->health) {
    case Health::Unknown: health_key = "conn.health.unknown"; break;
    case Health::Checking: health_key = "conn.health.checking"; break;
    case Health::Online: health_key = "conn.health.online"; break;
    case Health::Degraded: health_key = "conn.health.degraded"; break;
    case Health::Offline: health_key = "conn.health.offline"; break;
  }
  std::string name = c->info.kind == "local" ? std::string(store_.tr("conn.local")) : c->info.name;
  if (c->info.kind == "hub" && !node_.empty()) {
    for (const NodeRow &n : nodes_) {
      if (n.id == node_) {
        name += " / " + (n.name.empty() ? n.id.substr(0, 8) : n.name);
      }
    }
  }
  return store_.catalog().format("conn.status", {{"name", name}, {"health", std::string(store_.tr(health_key))}});
}

void JobsState::publish_connection()
{
  store_.set_connection(active_.empty() ? std::string() : connection_label());
}

void JobsState::select_connection(const std::string &id)
{
  conn_epoch_++;
  epoch_++;
  detail_epoch_++;
  active_ = id;
  watch_.unsubscribe();
  hub_sub_.unsubscribe();
  logs_sub_.unsubscribe();
  events_sub_.unsubscribe();
  nodes_.clear();
  node_.clear();
  templates_.clear();
  policy_.reset();
  reviews_.clear();
  workspaces_.clear();
  workspace_.clear();
  files_.clear();
  tasks_.clear();
  snapshot_time_ = 0.0;
  selected_.clear();
  log_all_.clear();
  log_out_.clear();
  log_err_.clear();
  events_ = {};
  artifacts_.clear();
  release_preview();
  form_.use_template = false;
  if (!id.empty()) {
    preferred_connection_ = id;
    connect_active();
  }
  publish_connection();
  changed();
}

void JobsState::connect_active()
{
  if (!ready() || active_.empty()) {
    return;
  }
  const uint64_t epoch = conn_epoch_;
  const std::string conn = active_;
  set_status(store_.catalog().format("jobs.status.connecting", {{"name", conn}}));
  check_connection(conn);
  if (conn == "local") {
    refresh_local();
  }
  if (!hub()) {
    refresh_workspaces();
    return;
  }
  on(client_->hub_devices(conn), [this, epoch](const bridge::Result<Json> &r) {
    if (epoch != conn_epoch_) {
      return;
    }
    if (!r) {
      fail(std::string(store_.tr("jobs.op.nodes")), r.error());
      return;
    }
    apply_nodes(r.value());
  });
  on(client_->hub_templates(conn), [this, epoch](const bridge::Result<Json> &r) {
    if (epoch != conn_epoch_ || !r) {
      return;
    }
    templates_.clear();
    const Json &t = r.value().contains("templates") ? r.value()["templates"] : Json();
    if (t.is_object()) {
      for (auto it = t.begin(); it != t.end(); ++it) {
        templates_.push_back(it.key());
      }
    }
    else if (t.is_array()) {
      for (const Json &e : t) {
        if (e.is_string()) {
          templates_.push_back(e.get<std::string>());
        }
        else if (!get_str(e, "name").empty()) {
          templates_.push_back(get_str(e, "name"));
        }
      }
    }
    if (form_.template_name.empty() && !templates_.empty()) {
      form_.template_name = templates_.front();
    }
    changed();
  });
  if (client_->hello_info() && client_->hello_info()->has_method("hub.policy")) {
    on(client_->hub_policy(conn), [this, epoch](const bridge::Result<bridge::HubPolicy> &r) {
      if (epoch != conn_epoch_ || !r) {
        return;
      }
      policy_ = r.value();
      changed();
    });
  }
  refresh_actions();
  bridge::HubEventHandlers h;
  std::weak_ptr<Alive> weak = alive_;
  h.on_event = [weak, epoch](const bridge::HubEvent &e) {
    if (auto a = weak.lock(); a && a->self->conn_epoch_ == epoch) {
      a->self->on_hub_event(e);
    }
  };
  h.on_error = [weak, epoch](const Error &e, bool final) {
    if (auto a = weak.lock(); a && a->self->conn_epoch_ == epoch && final) {
      a->self->fail(std::string(a->self->store_.tr("jobs.op.hub_events")), e);
    }
  };
  hub_sub_ = client_->subscribe_hub({conn, 0}, std::move(h));
}

void JobsState::check_connection(const std::string &id)
{
  if (!ready() || id.empty()) {
    return;
  }
  for (ConnectionRow &c : connections_) {
    if (c.info.id == id) {
      c.health = Health::Checking;
    }
  }
  publish_connection();
  changed();
  on(client_->connections_check(id), [this, id](const bridge::Result<bridge::ConnectionCheck> &r) {
    if (r) {
      apply_check(r.value());
    }
    else {
      bridge::ConnectionCheck failed;
      failed.id = id;
      failed.ok = false;
      failed.error = r.error();
      apply_check(failed);
    }
  });
}

void JobsState::apply_check(const bridge::ConnectionCheck &check)
{
  const std::string &id = check.id;
  for (ConnectionRow &c : connections_) {
    if (c.info.id != id) {
      continue;
    }
    if (!check.ok) {
      c.health = Health::Offline;
      c.detail = check.error ? check.error->message : std::string();
    }
    else {
      const Json &h = check.health;
      c.health = Health::Online;
      c.detail.clear();
      if (h.is_object() && h.contains("supervisor_running") && h["supervisor_running"].is_boolean() &&
          !h["supervisor_running"].get<bool>())
      {
        c.health = Health::Degraded;
        c.detail = std::string(store_.tr("conn.supervisor_stopped"));
      }
      if (h.is_object() && h.contains("online") && h["online"].is_boolean() && !h["online"].get<bool>()) {
        c.health = Health::Degraded;
        c.detail = std::string(store_.tr("conn.node_offline"));
      }
      if (check.nodes) {
        c.detail = store_.catalog().format("conn.nodes", {{"count", std::to_string(*check.nodes)}});
      }
      if (h.is_object() && h.contains("api_version") && h["api_version"].is_number_integer() &&
          h["api_version"].get<int64_t>() != 1)
      {
        c.health = Health::Degraded;
        c.detail = std::string(store_.tr("conn.api_mismatch"));
      }
    }
    if (id == active_) {
      const std::string msg = c.health == Health::Online ?
                                  std::string(store_.tr("jobs.status.connected")) :
                                  store_.catalog().format("jobs.status.connected_degraded", {{"detail", c.detail}});
      set_status(msg, c.health == Health::Online ? ui::ToastKind::Success :
                      (c.health == Health::Degraded ? ui::ToastKind::Warning : ui::ToastKind::Error));
    }
  }
  publish_connection();
  changed();
}

void JobsState::add_runtime(const bridge::AddRuntimeParams &params, Done done)
{
  if (!ready()) {
    if (done) {
      done(Error::make(ErrorCode::Unavailable, std::string(store_.tr("jobs.status.no_bridge"))));
    }
    return;
  }
  on(client_->connections_add_runtime(params), [this, done](const bridge::Result<bridge::ConnectionInfo> &r) {
    if (!r) {
      if (done) {
        done(r.error());
      }
      fail(std::string(store_.tr("jobs.op.add_runtime")), r.error());
      return;
    }
    const std::string id = r.value().id;
    set_status(store_.catalog().format("jobs.status.added", {{"name", r.value().name}}), ui::ToastKind::Success);
    preferred_connection_ = id;
    refresh_connections();
    select_connection(id);
    if (done) {
      done(std::nullopt);
    }
  });
}

void JobsState::pair_hub(const bridge::PairHubParams &params, Done done)
{
  if (!ready()) {
    if (done) {
      done(Error::make(ErrorCode::Unavailable, std::string(store_.tr("jobs.status.no_bridge"))));
    }
    return;
  }
  on(client_->connections_pair_hub(params), [this, done](const bridge::Result<bridge::ConnectionInfo> &r) {
    if (!r) {
      if (done) {
        done(r.error());
      }
      fail(std::string(store_.tr("jobs.op.pair_hub")), r.error());
      return;
    }
    const std::string id = r.value().id;
    set_status(store_.catalog().format("jobs.status.paired", {{"name", r.value().name}}), ui::ToastKind::Success);
    preferred_connection_ = id;
    refresh_connections();
    select_connection(id);
    if (done) {
      done(std::nullopt);
    }
  });
}

void JobsState::remove_connection(const std::string &id, Done done)
{
  if (!ready()) {
    if (done) {
      done(Error::make(ErrorCode::Unavailable, std::string(store_.tr("jobs.status.no_bridge"))));
    }
    return;
  }
  on(client_->connections_remove(id), [this, id, done](const bridge::Result<Json> &r) {
    if (!r) {
      if (done) {
        done(r.error());
      }
      fail(std::string(store_.tr("jobs.op.remove")), r.error());
      return;
    }
    if (active_ == id) {
      select_connection("");
    }
    if (preferred_connection_ == id) {
      preferred_connection_.clear();
    }
    set_status(store_.catalog().format("jobs.status.removed", {{"name", id}}));
    refresh_connections();
    if (done) {
      done(std::nullopt);
    }
  });
}

void JobsState::refresh_local()
{
  if (!ready()) {
    return;
  }
  on(client_->connections_local(), [this](const bridge::Result<bridge::LocalRuntimeStatus> &r) {
    if (r) {
      local_ = r.value();
      changed();
    }
  });
}

void JobsState::start_local()
{
  if (!ready() || local_busy_) {
    return;
  }
  local_busy_ = true;
  set_status(std::string(store_.tr("jobs.status.local_starting")));
  changed();
  /* As the legacy tab: an uninitialized local Runtime is set up first. */
  const bool initialize = local_ && !local_->initialized;
  on(client_->connections_local_start(initialize), [this](const bridge::Result<bridge::LocalRuntimeStatus> &r) {
    local_busy_ = false;
    if (!r) {
      fail(std::string(store_.tr("jobs.op.local_start")), r.error());
      return;
    }
    local_ = r.value();
    if (!local_->error.empty()) {
      set_status(local_->error, ui::ToastKind::Warning);
    }
    else {
      set_status(std::string(store_.tr("jobs.status.local_started")), ui::ToastKind::Success);
    }
    refresh_connections();
    if (active_ == "local") {
      check_connection("local");
      refresh_workspaces();
    }
    changed();
  });
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Hub
 * \{ */

void JobsState::apply_nodes(const Json &devices)
{
  nodes_.clear();
  const Json &list = devices.is_object() && devices.contains("devices") ? devices["devices"] : devices;
  if (list.is_array()) {
    for (const Json &d : list) {
      if (get_str(d, "role") != "node") {
        continue;
      }
      NodeRow n;
      n.id = get_str(d, "id");
      n.name = get_str(d, "name");
      n.online = d.contains("online") && d["online"].is_boolean() && d["online"].get<bool>();
      nodes_.push_back(std::move(n));
    }
  }
  bool listed = false;
  for (const NodeRow &n : nodes_) {
    listed |= n.id == node_;
  }
  if (!listed) {
    std::string pick;
    for (const NodeRow &n : nodes_) {
      if (n.id == preferred_node_) {
        pick = n.id;
      }
    }
    if (pick.empty()) {
      for (const NodeRow &n : nodes_) {
        if (n.online) {
          pick = n.id;
          break;
        }
      }
    }
    if (pick.empty() && !nodes_.empty()) {
      pick = nodes_.front().id;
    }
    if (!pick.empty()) {
      select_node(pick);
    }
  }
  publish_connection();
  changed();
}

void JobsState::select_node(const std::string &id)
{
  if (id == node_) {
    return;
  }
  epoch_++;
  detail_epoch_++;
  node_ = id;
  preferred_node_ = id;
  watch_.unsubscribe();
  logs_sub_.unsubscribe();
  events_sub_.unsubscribe();
  workspaces_.clear();
  workspace_.clear();
  files_.clear();
  tasks_.clear();
  selected_.clear();
  artifacts_.clear();
  refresh_workspaces();
  publish_connection();
  changed();
}

void JobsState::refresh_actions()
{
  if (!ready() || !hub()) {
    return;
  }
  const uint64_t epoch = conn_epoch_;
  on(client_->hub_actions(active_), [this, epoch](const bridge::Result<Json> &r) {
    if (epoch != conn_epoch_) {
      return;
    }
    if (!r) {
      fail(std::string(store_.tr("jobs.op.actions")), r.error());
      return;
    }
    apply_actions(r.value().contains("actions") ? r.value()["actions"] : Json::array());
  });
}

void JobsState::apply_actions(const Json &actions)
{
  std::vector<ReviewItem> next;
  std::map<std::string, std::string> states;
  if (actions.is_array()) {
    for (const Json &a : actions) {
      bridge::HubActionSummary s = bridge::HubActionSummary::from_json(a);
      std::string kind = s.kind;
      if (kind.empty() && a.contains("request")) {
        kind = get_str(a["request"], "kind");
      }
      states[s.id] = s.state;
      if (!s.in_review()) {
        continue;
      }
      ReviewItem item;
      for (const ReviewItem &old : reviews_) {
        if (old.action.id == s.id) {
          item = old;
        }
      }
      item.action = s;
      item.kind = kind;
      if (auto it = inspected_.find(s.id); it != inspected_.end()) {
        item.inspected = true;
        item.request = it->second;
      }
      else {
        item.inspected = false;
      }
      next.push_back(std::move(item));
    }
  }
  reviews_ = std::move(next);
  /* A submission waiting for review: re-send its key once the action left review. */
  if (submission_ && submission_->state == SubmitState::Review && submission_->action) {
    const auto it = states.find(submission_->action->id);
    if (it != states.end() && it->second != "review") {
      submission_->action->state = it->second;
      if (it->second == "rejected") {
        submission_->state = SubmitState::Failed;
        submission_->error = Error::make(ErrorCode::RemoteError, std::string(store_.tr("jobs.submit.rejected")), false);
        set_status(std::string(store_.tr("jobs.submit.rejected")), ui::ToastKind::Error);
      }
      else {
        send_submission();
      }
    }
  }
  changed();
}

void JobsState::on_hub_event(const bridge::HubEvent &event)
{
  if (event.kind == "actions.changed" || event.kind.rfind("action", 0) == 0) {
    refresh_actions();
  }
  else if (event.kind == "devices.changed") {
    const uint64_t epoch = conn_epoch_;
    on(client_->hub_devices(active_), [this, epoch](const bridge::Result<Json> &r) {
      if (epoch == conn_epoch_ && r) {
        apply_nodes(r.value());
      }
    });
  }
}

void JobsState::inspect(const std::string &action_id)
{
  if (!ready() || !hub()) {
    return;
  }
  for (ReviewItem &r : reviews_) {
    if (r.action.id == action_id) {
      r.busy = true;
    }
  }
  changed();
  const uint64_t epoch = conn_epoch_;
  on(client_->hub_action(active_, action_id), [this, epoch, action_id](const bridge::Result<Json> &r) {
    if (epoch != conn_epoch_) {
      return;
    }
    for (ReviewItem &item : reviews_) {
      if (item.action.id != action_id) {
        continue;
      }
      item.busy = false;
      if (!r) {
        item.message = r.error().message;
        continue;
      }
      const Json &a = r.value().contains("action") ? r.value()["action"] : r.value();
      item.request = a.contains("request") ? a["request"] : a;
      item.inspected = true;
      if (item.reinspecting) {
        item.reinspecting = false; /* keep "read again, approve again" */
      }
      else {
        item.message.clear();
      }
      inspected_[action_id] = item.request;
    }
    changed();
  });
}

void JobsState::review(const std::string &action_id, const bool approve)
{
  if (!ready() || !hub()) {
    return;
  }
  ReviewItem *item = nullptr;
  for (ReviewItem &r : reviews_) {
    if (r.action.id == action_id) {
      item = &r;
    }
  }
  if (approve && (!item || !item->inspected)) {
    if (item) {
      item->message = std::string(store_.tr("jobs.review.inspect_first"));
    }
    changed();
    return;
  }
  if (item) {
    item->busy = true;
  }
  changed();
  const uint64_t epoch = conn_epoch_;
  on(client_->hub_review(active_, action_id, approve), [this, epoch, action_id, approve](const bridge::Result<Json> &r) {
    if (epoch != conn_epoch_) {
      return;
    }
    ReviewItem *it = nullptr;
    for (ReviewItem &x : reviews_) {
      if (x.action.id == action_id) {
        it = &x;
      }
    }
    if (it) {
      it->busy = false;
    }
    if (r) {
      set_status(store_.catalog().format(approve ? "jobs.review.approved" : "jobs.review.rejected",
                                         {{"id", action_id.substr(0, 12)}}),
                 ui::ToastKind::Success);
      refresh_actions();
      changed();
      return;
    }
    const Error &e = r.error();
    std::string msg;
    if (e.code == ErrorCode::Unauthorized && e.data.is_object() && get_str(e.data, "reason") == "review_policy") {
      const std::string policy = policy_ ? policy_->review_policy : std::string();
      msg = store_.catalog().format("jobs.review.policy_refused",
                                    {{"policy", policy.empty() ? std::string("?") : policy}, {"message", e.message}});
    }
    else if (e.code == ErrorCode::ReviewNotInspected) {
      /* The bridge restarted since the request was read: read it again, then ask again. */
      inspected_.erase(action_id);
      if (it) {
        it->inspected = false;
        it->reinspecting = true;
        it->message = std::string(store_.tr("jobs.review.reinspect"));
      }
      msg = std::string(store_.tr("jobs.review.reinspect"));
      inspect(action_id);
    }
    else {
      msg = e.message;
    }
    if (it) {
      it->message = msg;
    }
    set_status(msg, ui::ToastKind::Error);
    changed();
  });
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Workspaces
 * \{ */

void JobsState::refresh_workspaces()
{
  if (!ready() || active_.empty() || (hub() && node_.empty())) {
    return;
  }
  const uint64_t epoch = epoch_;
  on(client_->workspace_list(target()), [this, epoch](const bridge::Result<Json> &r) {
    if (epoch != epoch_) {
      return;
    }
    if (!r) {
      fail(std::string(store_.tr("jobs.op.workspaces")), r.error());
      return;
    }
    apply_workspaces(r.value().contains("workspaces") ? r.value()["workspaces"] : Json::array());
  });
}

void JobsState::apply_workspaces(const Json &workspaces)
{
  workspaces_.clear();
  if (workspaces.is_array()) {
    for (const Json &w : workspaces) {
      workspaces_.push_back({get_str(w, "id"), get_str(w, "name"), get_str(w, "created_at")});
    }
  }
  bool listed = false;
  for (const WorkspaceRow &w : workspaces_) {
    listed |= w.id == workspace_;
  }
  if (!listed) {
    std::string pick;
    for (const WorkspaceRow &w : workspaces_) {
      if (w.id == preferred_workspace_) {
        pick = w.id;
      }
    }
    if (pick.empty() && !workspaces_.empty()) {
      pick = workspaces_.front().id;
    }
    workspace_.clear();
    select_workspace(pick);
  }
  changed();
}

void JobsState::select_workspace(const std::string &id)
{
  if (id == workspace_ && (id.empty() || watch_.active())) {
    return;
  }
  epoch_++;
  detail_epoch_++;
  workspace_ = id;
  if (!id.empty()) {
    preferred_workspace_ = id;
  }
  files_.clear();
  tasks_.clear();
  snapshot_time_ = 0.0;
  selected_.clear();
  logs_sub_.unsubscribe();
  events_sub_.unsubscribe();
  log_all_.clear();
  log_out_.clear();
  log_err_.clear();
  events_ = {};
  artifacts_.clear();
  release_preview();
  rewatch();
  refresh_files();
  if (!workspace_.empty() && !pending_.empty()) {
    start_pending();
  }
  changed();
}

void JobsState::rewatch()
{
  watch_.unsubscribe();
  if (!ready() || active_.empty() || workspace_.empty()) {
    return;
  }
  bridge::WatchParams p;
  p.target = target();
  p.workspace_id = workspace_;
  bridge::WatchHandlers h;
  std::weak_ptr<Alive> weak = alive_;
  const uint64_t epoch = epoch_;
  h.on_snapshot = [weak, epoch](const bridge::WatchSnapshot &s) {
    if (auto a = weak.lock(); a && a->self->epoch_ == epoch) {
      a->self->apply_snapshot(s.tasks, s.time);
    }
  };
  h.on_error = [weak, epoch](const Error &e, bool final) {
    if (auto a = weak.lock(); a && a->self->epoch_ == epoch) {
      a->self->fail(std::string(a->self->store_.tr("jobs.op.watch")), e);
    }
  };
  watch_ = client_->watch(p, std::move(h));
}

void JobsState::create_workspace(const std::string &name, Done done)
{
  if (!ready() || active_.empty() || (hub() && node_.empty())) {
    if (done) {
      done(Error::make(ErrorCode::Unavailable, std::string(store_.tr("jobs.status.connect_first"))));
    }
    return;
  }
  const uint64_t epoch = epoch_;
  on(client_->workspace_create(target(), name, new_idempotency_key()),
     [this, epoch, done, name](const bridge::Result<bridge::Submitted> &r) {
       if (done) {
         done(r ? std::nullopt : std::optional<Error>(r.error()));
       }
       if (epoch != epoch_) {
         return;
       }
       if (!r) {
         fail(std::string(store_.tr("jobs.op.create_workspace")), r.error());
         return;
       }
       if (r.value().object.is_object()) {
         preferred_workspace_ = get_str(r.value().object, "id");
         workspace_.clear();
         set_status(store_.catalog().format("jobs.status.workspace_created", {{"name", name}}), ui::ToastKind::Success);
       }
       else if (r.value().action && r.value().action->in_review()) {
         set_status(std::string(store_.tr("jobs.status.in_review")), ui::ToastKind::Warning);
         refresh_actions();
       }
       refresh_workspaces();
     });
}

void JobsState::refresh_files()
{
  if (!ready() || workspace_.empty()) {
    return;
  }
  const uint64_t epoch = epoch_;
  on(client_->workspace_files(target(), workspace_), [this, epoch](const bridge::Result<std::vector<bridge::FileEntry>> &r) {
    if (epoch != epoch_) {
      return;
    }
    if (!r) {
      fail(std::string(store_.tr("jobs.op.files")), r.error());
      return;
    }
    files_ = r.value();
    changed();
  });
}

void JobsState::download_input(const std::string &path, const std::string &dest)
{
  if (!ready() || workspace_.empty()) {
    return;
  }
  bridge::DownloadParams p;
  p.target = target();
  p.workspace_id = workspace_;
  p.path = path;
  p.dest = dest;
  p.idempotency_key = new_idempotency_key();
  on(client_->download_start(p), [this](const bridge::Result<bridge::Transfer> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.download")), r.error());
      return;
    }
    /* As the legacy tab: a downloaded input file is opened (preview, Viewer or the system). */
    open_after_.insert(r.value().id);
    apply_transfer(r.value());
  });
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Transfers
 * \{ */

void JobsState::upload(const std::vector<std::string> &paths)
{
  if (paths.empty()) {
    return;
  }
  if (!ready() || active_.empty() || workspace_.empty()) {
    for (const std::string &p : paths) {
      if (pending_.size() < 500 && std::find(pending_.begin(), pending_.end(), p) == pending_.end()) {
        pending_.push_back(p);
      }
    }
    set_status(store_.catalog().format("jobs.status.pending", {{"count", std::to_string(pending_.size())}}),
               ui::ToastKind::Warning);
    changed();
    return;
  }
  for (const std::string &p : paths) {
    start_upload(p);
  }
}

void JobsState::start_upload(const std::string &path)
{
  bridge::UploadParams p;
  p.target = target();
  p.workspace_id = workspace_;
  p.source = path;
  std::error_code ec;
  if (folder_into_root && std::filesystem::is_directory(core::path_from_utf8(path), ec)) {
    p.remote = "."; /* the folder's contents at the workspace root */
  }
  p.idempotency_key = new_idempotency_key();
  on(client_->upload_start(p), [this, path](const bridge::Result<bridge::Transfer> &r) {
    if (!r) {
      fail(store_.catalog().format("jobs.op.upload", {{"file", file_name(path)}}), r.error());
      return;
    }
    upload_ids_.insert(r.value().id);
    set_status(store_.catalog().format("jobs.status.uploading", {{"file", file_name(path)}}));
    apply_transfer(r.value());
  });
}

void JobsState::start_pending()
{
  if (!ready() || workspace_.empty() || pending_.empty()) {
    return;
  }
  std::vector<std::string> paths;
  paths.swap(pending_);
  for (const std::string &p : paths) {
    start_upload(p);
  }
  changed();
}

void JobsState::clear_pending()
{
  pending_.clear();
  changed();
}

const bridge::Transfer *JobsState::transfer(const std::string &id) const
{
  for (const bridge::Transfer &t : transfers_) {
    if (t.id == id) {
      return &t;
    }
  }
  return nullptr;
}

void JobsState::refresh_transfers()
{
  if (!ready()) {
    return;
  }
  on(client_->transfer_list(), [this](const bridge::Result<std::vector<bridge::Transfer>> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.transfers")), r.error());
      return;
    }
    std::vector<bridge::Transfer> list = r.value();
    std::stable_sort(list.begin(), list.end(), [](const bridge::Transfer &a, const bridge::Transfer &b) {
      return a.created_at > b.created_at;
    });
    transfers_ = std::move(list);
    changed();
  });
}

void JobsState::apply_transfer(const bridge::Transfer &t)
{
  bool found = false;
  bool was_finished = false;
  for (bridge::Transfer &x : transfers_) {
    if (x.id == t.id) {
      was_finished = x.finished();
      x = t;
      found = true;
    }
  }
  if (!found) {
    transfers_.insert(transfers_.begin(), t);
  }
  if (t.finished() && !was_finished) {
    if (t.kind == "download") {
      download_done(t);
    }
    else if (t.kind == "upload") {
      if (t.state == "completed") {
        if (upload_ids_.count(t.id)) {
          set_status(store_.catalog().format("jobs.status.uploaded", {{"count", std::to_string(t.files_total)}}),
                     ui::ToastKind::Success);
        }
        if (t.workspace_id == workspace_) {
          refresh_files();
        }
      }
      else if (t.state == "failed" && t.error) {
        fail(store_.catalog().format("jobs.op.upload", {{"file", file_name(t.local)}}), *t.error);
      }
    }
  }
  else if (t.kind == "upload" && t.action && t.action->in_review() && upload_ids_.count(t.id)) {
    set_status(store_.catalog().format("transfers.review", {{"id", t.action->id.substr(0, 12)}}),
               ui::ToastKind::Warning);
    refresh_actions();
  }
  changed();
}

void JobsState::resume_transfer(const std::string &id)
{
  if (!ready()) {
    return;
  }
  on(client_->transfer_resume(id), [this](const bridge::Result<bridge::Transfer> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.resume")), r.error());
      return;
    }
    apply_transfer(r.value());
  });
}

void JobsState::cancel_transfer(const std::string &id)
{
  if (!ready()) {
    return;
  }
  on(client_->transfer_cancel(id), [this](const bridge::Result<bridge::Transfer> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.cancel_transfer")), r.error());
      return;
    }
    apply_transfer(r.value());
  });
}

int JobsState::uploads_in_flight() const
{
  int n = 0;
  for (const bridge::Transfer &t : transfers_) {
    if (t.kind == "upload" && !t.finished() && t.connection == active_ && t.workspace_id == workspace_ &&
        !workspace_.empty())
    {
      n++;
    }
  }
  return n;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Submit
 * \{ */

std::vector<FormIssue> JobsState::validate() const
{
  return validate_form(form_, workspace_, hub());
}

bool JobsState::submit()
{
  const std::vector<FormIssue> issues = validate();
  if (!issues.empty()) {
    const FormIssue &i = issues.front();
    std::string text(store_.tr(i.key));
    for (const auto &[k, v] : i.args) {
      const std::string ph = "{" + k + "}";
      for (size_t p = text.find(ph); p != std::string::npos; p = text.find(ph, p + v.size())) {
        text.replace(p, ph.size(), v);
      }
    }
    set_status(text, ui::ToastKind::Error);
    changed();
    return false;
  }
  if (!ready() || active_.empty()) {
    set_status(std::string(store_.tr("jobs.status.connect_first")), ui::ToastKind::Error);
    changed();
    return false;
  }
  if (uploads_in_flight() > 0) {
    set_status(std::string(store_.tr("jobs.status.wait_uploads")), ui::ToastKind::Warning);
    changed();
    return false;
  }
  if (submission_ && (submission_->state == SubmitState::Sending || submission_->state == SubmitState::Waiting)) {
    return false;
  }
  Submission s;
  s.key = new_idempotency_key();
  s.params.target = target();
  s.params.idempotency_key = s.key;
  if (hub() && form_.use_template) {
    s.params.template_name = form_.template_name;
    s.params.workspace_id = workspace_;
    s.label = form_.template_name;
  }
  else {
    s.params.spec = form_to_spec(form_, workspace_);
    s.label = form_.name.empty() ? form_.program : form_.name;
  }
  submission_ = std::move(s);
  send_submission();
  return true;
}

void JobsState::retry_submission()
{
  if (!submission_ || submission_->state == SubmitState::Sending || submission_->state == SubmitState::Done) {
    return;
  }
  submission_->attempts = 0;
  send_submission();
}

void JobsState::send_submission()
{
  if (!submission_ || !client_) {
    return;
  }
  submission_->state = SubmitState::Sending;
  submission_->attempts++;
  submission_->error.reset();
  set_status(store_.catalog().format("jobs.status.submitting", {{"name", submission_->label}}));
  changed();
  const std::string key = submission_->key;
  on(client_->task_submit(submission_->params), [this, key](const bridge::Result<bridge::Submitted> &r) {
    if (!submission_ || submission_->key != key) {
      return;
    }
    submission_result(r);
  });
}

void JobsState::submission_result(const bridge::Result<bridge::Submitted> &r)
{
  Submission &s = *submission_;
  if (r) {
    const bridge::Submitted &v = r.value();
    s.action = v.action;
    if (v.object.is_object() && !get_str(v.object, "id").empty()) {
      s.state = SubmitState::Done;
      s.task_id = get_str(v.object, "id");
      set_status(store_.catalog().format("jobs.status.submitted", {{"id", s.task_id}}), ui::ToastKind::Success);
      if (s.params.target.connection == active_) {
        select_task(s.task_id);
      }
    }
    else if (v.action && v.action->in_review()) {
      s.state = SubmitState::Review;
      set_status(store_.catalog().format("jobs.submit.review", {{"id", v.action->id.substr(0, 12)}}),
                 ui::ToastKind::Warning);
      refresh_actions();
    }
    else {
      /* The action is queued or running on the node: ask again with the same key. */
      s.state = SubmitState::Waiting;
      const std::string key = s.key;
      std::weak_ptr<Alive> weak = alive_;
      auto again = [weak, key]() {
        if (auto a = weak.lock(); a && a->self->submission_ && a->self->submission_->key == key &&
                                   a->self->submission_->state == SubmitState::Waiting)
        {
          a->self->send_submission();
        }
      };
      schedule ? schedule(2.0, again) : again();
    }
    changed();
    return;
  }
  const Error &e = r.error();
  s.error = e;
  if (retry_worthy(e) && s.attempts <= std::max(0, form_.retry.auto_retries) && e.code != ErrorCode::ShuttingDown) {
    s.state = SubmitState::Waiting;
    const double delay = std::max(0.0, form_.retry.backoff_s) * std::pow(2.0, double(s.attempts - 1));
    set_status(store_.catalog().format("jobs.submit.retrying",
                                       {{"error", e.message}, {"attempt", std::to_string(s.attempts + 1)}}),
               ui::ToastKind::Warning);
    const std::string key = s.key;
    std::weak_ptr<Alive> weak = alive_;
    auto again = [weak, key]() {
      if (auto a = weak.lock(); a && a->self->submission_ && a->self->submission_->key == key &&
                                 a->self->submission_->state == SubmitState::Waiting)
      {
        a->self->send_submission();
      }
    };
    schedule ? schedule(delay, again) : again();
  }
  else {
    s.state = SubmitState::Failed;
    set_status(store_.catalog().format("jobs.submit.failed", {{"error", e.message}}), ui::ToastKind::Error);
  }
  changed();
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Tasks and detail
 * \{ */

void JobsState::apply_snapshot(const Json &tasks, const double time)
{
  std::vector<TaskRow> rows;
  if (tasks.is_array()) {
    for (const Json &t : tasks) {
      rows.push_back(TaskRow::from_json(t));
    }
  }
  tasks_ = std::move(rows);
  snapshot_time_ = time;
  if (const TaskRow *sel = selected_task()) {
    /* Artifacts appear once the task is finished (the Runtime lists them only then). */
    if (sel->terminal() && artifacts_for_state_ != sel->state) {
      refresh_artifacts();
    }
  }
  changed();
}

const TaskRow *JobsState::selected_task() const
{
  for (const TaskRow &t : tasks_) {
    if (t.id == selected_) {
      return &t;
    }
  }
  return nullptr;
}

void JobsState::select_task(const std::string &id)
{
  if (id == selected_) {
    return;
  }
  detail_epoch_++;
  selected_ = id;
  logs_sub_.unsubscribe();
  events_sub_.unsubscribe();
  log_all_.clear();
  log_out_.clear();
  log_err_.clear();
  logs_ended_ = false;
  events_ = {};
  artifacts_.clear();
  artifacts_for_state_.clear();
  release_preview();
  resubscribe_detail();
  changed();
}

void JobsState::resubscribe_detail()
{
  if (!ready() || selected_.empty()) {
    return;
  }
  std::weak_ptr<Alive> weak = alive_;
  const uint64_t epoch = detail_epoch_;
  bridge::LogsParams lp;
  lp.target = target();
  lp.task_id = selected_;
  lp.streams = {"stdout", "stderr"};
  bridge::LogsHandlers lh;
  /* Per-stream partial lines, so the combined view never interleaves half lines. */
  auto partial = std::make_shared<std::map<std::string, std::string>>();
  lh.on_chunk = [weak, epoch, partial](const bridge::LogChunk &c) {
    auto a = weak.lock();
    if (!a || a->self->detail_epoch_ != epoch) {
      return;
    }
    JobsState &s = *a->self;
    const bool err = c.stream == "stderr";
    (err ? s.log_err_ : s.log_out_).append(c.text);
    std::string &part = (*partial)[c.stream];
    part += c.text;
    size_t nl;
    std::string lines;
    while ((nl = part.find('\n')) != std::string::npos) {
      lines += (err ? "[stderr] " : "") + part.substr(0, nl + 1);
      part.erase(0, nl + 1);
    }
    if (!lines.empty()) {
      s.log_all_.append(lines);
    }
    s.changed();
  };
  lh.on_end = [weak, epoch, partial](const bridge::LogsEnd &) {
    auto a = weak.lock();
    if (!a || a->self->detail_epoch_ != epoch) {
      return;
    }
    JobsState &s = *a->self;
    for (auto &[stream, part] : *partial) {
      if (!part.empty()) {
        s.log_all_.append((stream == "stderr" ? "[stderr] " : "") + part + "\n");
        part.clear();
      }
    }
    s.logs_ended_ = true;
    s.changed();
  };
  lh.on_error = [weak, epoch](const Error &e, bool final) {
    auto a = weak.lock();
    if (!a || a->self->detail_epoch_ != epoch) {
      return;
    }
    if (final) {
      a->self->fail(std::string(a->self->store_.tr("jobs.op.logs")), e);
    }
  };
  logs_sub_ = client_->subscribe_logs(lp, std::move(lh));

  bridge::EventsParams ep;
  ep.target = target();
  ep.task_id = selected_;
  bridge::EventsHandlers eh;
  eh.on_batch = [weak, epoch](const bridge::EventsBatch &b) {
    auto a = weak.lock();
    if (!a || a->self->detail_epoch_ != epoch) {
      return;
    }
    JobsState &s = *a->self;
    if (b.events.is_array()) {
      for (const Json &e : b.events) {
        s.events_.add(e);
      }
    }
    if (b.invalid.is_array()) {
      s.events_.invalid += int64_t(b.invalid.size());
    }
    s.changed();
  };
  eh.on_end = [weak, epoch](const bridge::EventsEnd &) {
    auto a = weak.lock();
    if (a && a->self->detail_epoch_ == epoch) {
      a->self->events_.ended = true;
      a->self->changed();
    }
  };
  eh.on_error = [weak, epoch](const Error &e, bool final) {
    auto a = weak.lock();
    if (!a || a->self->detail_epoch_ != epoch) {
      return;
    }
    if (e.code == ErrorCode::Unsupported) {
      a->self->events_.unsupported = true;
      a->self->changed();
    }
  };
  events_sub_ = client_->subscribe_events(ep, std::move(eh));
  refresh_artifacts();
}

void JobsState::cancel_task(const std::string &id)
{
  if (!ready() || id.empty()) {
    return;
  }
  on(client_->task_cancel(target(), id, new_idempotency_key()), [this, id](const bridge::Result<bridge::Submitted> &r) {
    if (!r) {
      fail(std::string(store_.tr("jobs.op.cancel")), r.error());
      return;
    }
    if (r.value().action && r.value().action->in_review()) {
      set_status(std::string(store_.tr("jobs.status.in_review")), ui::ToastKind::Warning);
      refresh_actions();
    }
    else {
      set_status(store_.catalog().format("jobs.status.cancel_requested", {{"id", id.substr(0, 12)}}));
    }
    changed();
  });
}

void JobsState::refresh_tasks()
{
  if (!ready() || workspace_.empty()) {
    return;
  }
  const uint64_t epoch = epoch_;
  on(client_->task_list(target(), workspace_), [this, epoch](const bridge::Result<Json> &r) {
    if (epoch != epoch_) {
      return;
    }
    if (!r) {
      fail(std::string(store_.tr("jobs.op.tasks")), r.error());
      return;
    }
    apply_snapshot(r.value().contains("tasks") ? r.value()["tasks"] : Json::array(), snapshot_time_);
  });
  refresh_files();
  if (!watch_.active()) {
    rewatch();
  }
}

void JobsState::refresh_artifacts()
{
  if (!ready() || selected_.empty()) {
    return;
  }
  const TaskRow *t = selected_task();
  artifacts_for_state_ = t ? t->state : std::string();
  const uint64_t epoch = detail_epoch_;
  on(client_->task_artifacts(target(), selected_),
     [this, epoch](const bridge::Result<std::vector<bridge::FileEntry>> &r) {
       if (epoch != detail_epoch_) {
         return;
       }
       if (!r) {
         if (r.error().code != ErrorCode::NotFound) {
           fail(std::string(store_.tr("jobs.op.artifacts")), r.error());
         }
         return;
       }
       apply_artifacts(r.value());
     });
}

void JobsState::apply_artifacts(const std::vector<bridge::FileEntry> &files)
{
  std::vector<ArtifactRow> rows;
  for (const bridge::FileEntry &f : files) {
    ArtifactRow row;
    for (const ArtifactRow &old : artifacts_) {
      if (old.file.path == f.path) {
        row = old;
      }
    }
    row.file = f;
    rows.push_back(std::move(row));
  }
  artifacts_ = std::move(rows);
  changed();
}

void JobsState::download_artifact(const std::string &path, const std::string &dest)
{
  if (!ready() || selected_.empty()) {
    return;
  }
  bridge::DownloadParams p;
  p.target = target();
  p.task_id = selected_;
  p.path = path;
  p.dest = dest;
  p.idempotency_key = new_idempotency_key();
  for (ArtifactRow &a : artifacts_) {
    if (a.file.path == path) {
      a.verify = ArtifactRow::Verify::Pending;
    }
  }
  changed();
  const uint64_t epoch = detail_epoch_;
  const bool open_after = dest.empty();
  on(client_->download_start(p), [this, path, epoch, open_after](const bridge::Result<bridge::Transfer> &r) {
    if (!r) {
      for (ArtifactRow &a : artifacts_) {
        if (a.file.path == path) {
          a.verify = ArtifactRow::Verify::None;
        }
      }
      fail(store_.catalog().format("jobs.op.download_file", {{"file", path}}), r.error());
      return;
    }
    download_for_[r.value().id] = path;
    if (open_after) {
      open_after_.insert(r.value().id);
    }
    if (epoch == detail_epoch_) {
      for (ArtifactRow &a : artifacts_) {
        if (a.file.path == path) {
          a.transfer_id = r.value().id;
        }
      }
    }
    apply_transfer(r.value());
  });
}

void JobsState::download_done(const bridge::Transfer &t)
{
  const auto it = download_for_.find(t.id);
  ArtifactRow *row = nullptr;
  for (ArtifactRow &a : artifacts_) {
    if (a.transfer_id == t.id || (it != download_for_.end() && a.file.path == it->second && t.task_id == selected_)) {
      row = &a;
    }
  }
  if (t.state != "completed") {
    if (row) {
      row->verify = ArtifactRow::Verify::None;
    }
    if (t.error) {
      fail(store_.catalog().format("jobs.op.download_file", {{"file", t.remote}}), *t.error);
    }
    return;
  }
  const bool open = open_after_.erase(t.id) > 0;
  if (!row) {
    set_status(store_.catalog().format("jobs.status.downloaded", {{"path", t.local}}), ui::ToastKind::Success);
    if (open) {
      open_local(t.local);
    }
    return;
  }
  row->transfer_id = t.id;
  row->local = t.local;
  verify_download(*row);
  if (row->verify == ArtifactRow::Verify::Ok) {
    set_status(store_.catalog().format("jobs.status.downloaded", {{"path", t.local}}), ui::ToastKind::Success);
    if (ends_with_ci(row->local, ".png")) {
      show_preview(row->local);
    }
    else if (open) {
      /* "Download" (not "Save as") opens the result, as the legacy tab's double-click did. */
      open_local(row->local);
    }
  }
  else {
    set_status(store_.catalog().format("jobs.status.verify_failed", {{"path", t.local}}), ui::ToastKind::Error);
  }
}

void JobsState::verify_download(ArtifactRow &row)
{
  /* The bridge moved the file into place only after its sha256 matched; this re-reads it so the
   * UI's "verified" mark is about the bytes on disk now. Large files keep the bridge's check. */
  constexpr int64_t kMaxLocalCheck = int64_t(256) << 20;
  if (row.file.size > kMaxLocalCheck || row.file.sha256.empty()) {
    row.verify = ArtifactRow::Verify::Ok;
    return;
  }
  std::ifstream in(core::path_from_utf8(row.local), std::ios::binary);
  if (!in) {
    row.verify = ArtifactRow::Verify::Mismatch;
    return;
  }
  core::Sha256 h;
  std::vector<char> buf(1 << 16);
  while (in) {
    in.read(buf.data(), std::streamsize(buf.size()));
    if (in.gcount() > 0) {
      h.update(buf.data(), size_t(in.gcount()));
    }
  }
  const core::Sha256::Digest d = h.finish();
  row.verify = core::to_hex(d) == row.file.sha256 ? ArtifactRow::Verify::Ok : ArtifactRow::Verify::Mismatch;
}

void JobsState::release_preview()
{
  if (preview_.texture && free_texture) {
    free_texture(preview_.texture);
  }
  preview_ = {};
}

void JobsState::clear_preview()
{
  release_preview();
  changed();
}

void JobsState::show_preview(const std::string &local_path)
{
  release_preview();
  preview_.path = local_path;
  try {
    const io::Image img = io::read_png(core::path_from_utf8(local_path));
    preview_.width = int(img.width);
    preview_.height = int(img.height);
    if (create_texture) {
      preview_.texture = create_texture(img);
    }
  }
  catch (const std::exception &e) {
    preview_.error = e.what();
  }
  changed();
}

void JobsState::open_local(const std::string &local_path)
{
  if (ends_with_ci(local_path, ".png")) {
    show_preview(local_path);
    return;
  }
  std::error_code ec;
  if (ends_with_ci(local_path, ".stkp") || ends_with_ci(local_path, ".vtk") ||
      std::filesystem::is_directory(core::path_from_utf8(local_path), ec))
  {
    OpenResultRequest req;
    req.connection = active_;
    req.node = hub() ? node_ : std::string();
    req.workspace_id = workspace_;
    req.local_paths = {local_path};
    store_.request_open_result(std::move(req));
    return;
  }
  std::string error;
  if (!open_external || !open_external(local_path, &error)) {
    set_status(store_.catalog().format("jobs.status.open_failed", {{"path", local_path}, {"error", error}}),
               ui::ToastKind::Error);
    changed();
  }
}

void JobsState::open_in_viewer()
{
  if (selected_.empty()) {
    return;
  }
  OpenResultRequest req;
  req.connection = active_;
  req.node = hub() ? node_ : std::string();
  req.workspace_id = workspace_;
  req.task_id = selected_;
  store_.request_open_result(std::move(req));
  set_status(store_.catalog().format("jobs.status.open_viewer", {{"id", selected_.substr(0, 12)}}));
}

/** \} */

}  // namespace stk::app
