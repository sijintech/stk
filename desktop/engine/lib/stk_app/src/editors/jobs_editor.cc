/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Jobs editor (WP9): connections (Runtime profiles, hub pairing, the local Runtime),
 * workspaces and their input files, uploads (file dialog, path field, drag and drop), the submit
 * form, the task list (watch snapshots), task detail (logs, monitoring events, artifacts with
 * verified downloads and PNG preview, open in viewer) and, for hubs, the review panel. All data and
 * bridge traffic is in JobsState (AppStore::jobs()); this class keeps only per-area UI state.
 */

#include <cmath>
#include <cstdio>

#include "stk/app/jobs_state.hh"
#include "stk/platform/file_dialog.hh"

#include "../app_theme.hh"
#include "jobs_common.hh"

namespace stk::app {

namespace jobs_ui {

std::string issue_text(const AppStore &store, const FormIssue &issue)
{
  std::string text(store.tr(issue.key));
  for (const auto &[k, v] : issue.args) {
    const std::string ph = "{" + k + "}";
    for (size_t p = text.find(ph); p != std::string::npos; p = text.find(ph, p + v.size())) {
      text.replace(p, ph.size(), v);
    }
  }
  return text;
}

std::string short_time(const std::string &iso)
{
  /* YYYY-MM-DDTHH:MM:SS... */
  if (iso.size() >= 19 && iso[10] == 'T') {
    return iso.substr(5, 5) + " " + iso.substr(11, 8);
  }
  return iso;
}

std::string transfer_state_text(const AppStore &store, const bridge::Transfer &t)
{
  if (t.kind == "upload" && t.action && t.action->in_review() && !t.finished()) {
    return std::string(store.tr("transfers.state.review"));
  }
  static const char *const known[] = {"queued", "running", "interrupted", "completed", "failed", "cancelled"};
  for (const char *k : known) {
    if (t.state == k) {
      return std::string(store.tr(std::string("transfers.state.") + k));
    }
  }
  return t.state;
}

}  // namespace jobs_ui

namespace {

using namespace jobs_ui;

enum class Dialog : uint8_t { None, AddRuntime, PairHub, Remove, NewWorkspace, CancelTask, Paths };
enum class PathPurpose : uint8_t { UploadFiles, UploadFolder, SaveArtifact, SaveInput, TokenFile };

class JobsEditor final : public Editor {
 public:
  explicit JobsEditor(const EditorType &type) : Editor(type), alive_(std::make_shared<bool>(true)) {}
  ~JobsEditor() override
  {
    *alive_ = false;
  }

  ui::Color main_background(const ui::Theme & /*theme*/) const override
  {
    return theme::kListBack;
  }

  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    const std::string_view label = ctx.tr("jobs.submit");
    row.button("submit", label, [&jobs]() { jobs.submit(); })
        .width(fit_units(ctx, label))
        .disable(!jobs.ready() || jobs.workspace().empty())
        .tip(ctx.tr("jobs.submit.tip"));
    const std::string_view refresh = ctx.tr("jobs.refresh");
    row.button("refresh", refresh, [&jobs]() {
         jobs.refresh_connections();
         jobs.refresh_workspaces();
         jobs.refresh_tasks();
         jobs.refresh_transfers();
       })
        .width(fit_units(ctx, refresh))
        .disable(!jobs.ready());
  }

  void draw_main(ui::Layout &l, EditorContext &ctx) override
  {
    store_ = &ctx.store;
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    if (!prefs_applied_) {
      prefs_applied_ = true;
      if (!pref_connection_.empty()) {
        jobs.set_preferred(pref_connection_, pref_node_, pref_workspace_);
      }
    }
    status_line(l, ctx, jobs);
    connection_panel(l, ctx, jobs);
    workspace_panel(l, ctx, jobs);
    submit_panel(l, ctx, jobs);
    tasks_panel(l, ctx, jobs);
    detail_panel(l, ctx, jobs);
    review_panel(l, ctx, jobs);
    dialogs(ctx, jobs);
  }

  bool on_drop(const std::vector<std::string> &paths, EditorContext &ctx) override
  {
    JobsState &jobs = ctx.store.jobs();
    jobs.sync();
    jobs.upload(paths);
    ctx.store.log(ctx.store.catalog().format(
        "jobs.drop.queued",
        {{"count", std::to_string(paths.size())}, {"editor", std::string(ctx.tr(type().title_key))}}));
    return true;
  }

  nlohmann::json save_state() const override
  {
    nlohmann::json j = nlohmann::json::object();
    std::string conn = pref_connection_, node = pref_node_, ws = pref_workspace_;
    if (store_) {
      JobsState &jobs = store_->jobs();
      if (!jobs.active_id().empty()) {
        conn = jobs.active_id();
        node = jobs.node();
        ws = jobs.workspace();
      }
    }
    if (!conn.empty()) {
      j["connection"] = conn;
    }
    if (!node.empty()) {
      j["node"] = node;
    }
    if (!ws.empty()) {
      j["workspace"] = ws;
    }
    if (detail_tab_ != 0) {
      j["detail_tab"] = detail_tab_;
    }
    return j;
  }

  bool load_state(const nlohmann::json &state) override
  {
    if (!state.is_object()) {
      return true;
    }
    auto str = [&](const char *k) {
      const auto it = state.find(k);
      return it != state.end() && it->is_string() ? it->get<std::string>() : std::string();
    };
    pref_connection_ = str("connection");
    pref_node_ = str("node");
    pref_workspace_ = str("workspace");
    if (const auto it = state.find("detail_tab"); it != state.end() && it->is_number_integer()) {
      detail_tab_ = std::clamp(it->get<int>(), 0, 3);
    }
    prefs_applied_ = false;
    return true;
  }

 private:
  /* ---- Status ---- */

  void status_line(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    std::string text;
    if (!ctx.store.bridge()) {
      text = std::string(ctx.tr("jobs.status.no_bridge"));
    }
    else if (!jobs.ready()) {
      text = std::string(ctx.tr("jobs.status.bridge_wait"));
    }
    else if (!jobs.status().text.empty()) {
      text = jobs.status().text;
    }
    else {
      text = std::string(ctx.tr("jobs.status.hint"));
    }
    l.label(text).tip(text + "\n" + std::string(ctx.tr("jobs.status.jobs_survive")));
  }

  /* ---- Connection ---- */

  static std::string connection_name(EditorContext &ctx, const ConnectionRow &c)
  {
    if (c.info.kind == "local") {
      return std::string(ctx.tr(c.info.state == "not_initialized" ? "conn.local.unset" : "conn.local"));
    }
    return c.info.name + " (" + std::string(ctx.tr(c.info.kind == "hub" ? "conn.kind.hub" : "conn.kind.runtime")) + ")";
  }

  static const char *health_key(const Health h)
  {
    switch (h) {
      case Health::Unknown: return "conn.health.unknown";
      case Health::Checking: return "conn.health.checking";
      case Health::Online: return "conn.health.online";
      case Health::Degraded: return "conn.health.degraded";
      case Health::Offline: return "conn.health.offline";
    }
    return "conn.health.unknown";
  }

  void connection_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    ui::Layout *p = l.panel("conn", ctx.tr("jobs.panel.connection"));
    if (!p) {
      return;
    }
    const bool ready = jobs.ready();
    std::vector<std::string> items{std::string(ctx.tr("conn.none"))};
    std::vector<std::string> ids{""};
    int sel = 0;
    for (const ConnectionRow &c : jobs.connections()) {
      if (c.info.id == jobs.active_id()) {
        sel = int(items.size());
      }
      items.push_back(connection_name(ctx, c));
      ids.push_back(c.info.id);
    }
    ui::Layout &row = p->row(true);
    row.dropdown("connection", items,
                 {[sel]() { return sel; },
                  [&jobs, ids](int i) {
                    if (i >= 0 && i < int(ids.size())) {
                      jobs.select_connection(ids[size_t(i)]);
                    }
                  }})
        .disable(!ready)
        .tip(ctx.tr("conn.pick.tip"));
    const std::string_view check = ctx.tr("conn.check");
    row.button("check", check, [&jobs]() { jobs.check_connection(jobs.active_id()); })
        .width(fit_units(ctx, check))
        .disable(!ready || jobs.active_id().empty())
        .tip(ctx.tr("conn.check.tip"));
    const ConnectionRow *active = jobs.active();
    const std::string_view remove = ctx.tr("conn.remove");
    row.button("remove", remove, [this, &jobs]() {
         remove_id_ = jobs.active_id();
         open_dialog(Dialog::Remove);
       })
        .width(fit_units(ctx, remove))
        .disable(!ready || !active || active->info.kind == "local")
        .tip(ctx.tr("conn.remove.tip"));
    if (const ConnectionRow *c = jobs.active()) {
      std::string h(ctx.tr(health_key(c->health)));
      if (!c->detail.empty()) {
        h += " · " + c->detail;
      }
      p->label(ctx.store.catalog().format("conn.health", {{"state", h}})).tip(c->info.url);
    }
    ui::Layout &r2 = p->row(false);
    r2.button("add_runtime", ctx.tr("conn.add_runtime"), [this]() { open_dialog(Dialog::AddRuntime); })
        .disable(!ready)
        .tip(ctx.tr("conn.add_runtime.tip"));
    r2.button("pair_hub", ctx.tr("conn.pair_hub"), [this]() { open_dialog(Dialog::PairHub); })
        .disable(!ready)
        .tip(ctx.tr("conn.pair_hub.tip"));

    /* The local Runtime: status and start (the legacy tab started it on "Connect"). */
    if (const auto &local = jobs.local_status(); local && (jobs.active_id() == "local" || jobs.active_id().empty())) {
      std::string state;
      if (!local->initialized) {
        state = std::string(ctx.tr("conn.local.not_initialized"));
      }
      else if (local->api_running && local->supervisor_running) {
        state = std::string(ctx.tr("conn.local.running"));
      }
      else if (local->api_running) {
        state = std::string(ctx.tr("conn.local.supervisor_stopped"));
      }
      else {
        state = std::string(ctx.tr("conn.local.stopped"));
      }
      ui::Layout &r3 = p->row(true);
      r3.label(ctx.store.catalog().format("conn.local.status", {{"state", state}}))
          .tip(local->state_dir + (local->error.empty() ? std::string() : "\n" + local->error));
      const std::string_view start = ctx.tr(jobs.local_busy() ? "conn.local.starting" : "conn.local.start");
      r3.button("local_start", start, [&jobs]() { jobs.start_local(); })
          .width(fit_units(ctx, start))
          .disable(!ready || jobs.local_busy() || (local->api_running && local->supervisor_running))
          .tip(ctx.tr("conn.local.start.tip"));
    }

    if (jobs.hub()) {
      std::vector<std::string> nodes;
      std::vector<std::string> node_ids;
      int nsel = -1;
      for (const NodeRow &n : jobs.nodes()) {
        if (n.id == jobs.node()) {
          nsel = int(nodes.size());
        }
        nodes.push_back((n.name.empty() ? n.id.substr(0, 8) : n.name) +
                        (n.online ? "" : " (" + std::string(ctx.tr("conn.node.offline")) + ")"));
        node_ids.push_back(n.id);
      }
      ui::Layout &v = p->prop(ctx.tr("conn.node"), ctx.tr("conn.node.tip"));
      if (nodes.empty()) {
        v.label(ctx.tr("conn.node.none")).disable();
      }
      else {
        v.dropdown("node", nodes, {[nsel]() { return nsel; }, [&jobs, node_ids](int i) {
                                     if (i >= 0 && i < int(node_ids.size())) {
                                       jobs.select_node(node_ids[size_t(i)]);
                                     }
                                   }});
      }
      if (const auto &pol = jobs.policy()) {
        p->label(ctx.store.catalog().format(
                     "conn.hub.policy",
                     {{"profile", pol->device_profile.empty() ? std::string("-") : pol->device_profile},
                      {"review", pol->review_policy.empty() ? std::string("-") : pol->review_policy}}))
            .disable();
      }
    }
  }

  /* ---- Workspace, inputs, uploads ---- */

  void workspace_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    ui::Layout *p = l.panel("workspace", ctx.tr("jobs.panel.workspace"));
    if (!p) {
      return;
    }
    const bool connected = jobs.ready() && !jobs.active_id().empty() && (!jobs.hub() || !jobs.node().empty());
    std::vector<std::string> items;
    std::vector<std::string> ids;
    int sel = -1;
    for (const WorkspaceRow &w : jobs.workspaces()) {
      if (w.id == jobs.workspace()) {
        sel = int(items.size());
      }
      items.push_back(w.name.empty() ? w.id.substr(0, 12) : w.name);
      ids.push_back(w.id);
    }
    ui::Layout &row = p->row(true);
    if (items.empty()) {
      row.label(ctx.tr(connected ? "jobs.workspace.none" : "jobs.workspace.connect_first")).disable();
    }
    else {
      row.dropdown("workspace", items, {[sel]() { return sel; }, [&jobs, ids](int i) {
                                          if (i >= 0 && i < int(ids.size())) {
                                            jobs.select_workspace(ids[size_t(i)]);
                                          }
                                        }});
    }
    const std::string_view create = ctx.tr("jobs.workspace.new");
    row.button("new_workspace", create, [this]() { open_dialog(Dialog::NewWorkspace); })
        .width(fit_units(ctx, create))
        .disable(!connected);

    ui::Layout &up = p->row(false);
    up.button("upload_files", ctx.tr("jobs.upload.files"), [this, &store = ctx.store, &jobs]() {
        pick(store, jobs, PathPurpose::UploadFiles);
      })
        .disable(!connected)
        .tip(ctx.tr("jobs.upload.tip"));
    up.button("upload_folder", ctx.tr("jobs.upload.folder"), [this, &store = ctx.store, &jobs]() {
        pick(store, jobs, PathPurpose::UploadFolder);
      })
        .disable(!connected)
        .tip(ctx.tr("jobs.upload.tip"));
    p->checkbox("folder_root", ctx.tr("jobs.upload.folder_root"), ui::bind(jobs.folder_into_root))
        .tip(ctx.tr("jobs.upload.folder_root.tip"));

    /* Input files of the workspace; Enter / double-click downloads one (verified). */
    const std::vector<bridge::FileEntry> &files = jobs.workspace_files();
    if (!files.empty()) {
      ui::ListSpec spec;
      spec.count = int(files.size());
      spec.text = [&files](int i) {
        const bridge::FileEntry &f = files[size_t(i)];
        return f.path + "  (" + format_bytes(f.size) + ")";
      };
      spec.selected = ui::bind(input_sel_);
      spec.rows = std::min(4.0f, float(files.size()));
      spec.on_activate = [this, &store = ctx.store, &jobs, &files](int i) {
        if (i >= 0 && i < int(files.size())) {
          input_path_ = files[size_t(i)].path;
          pick(store, jobs, PathPurpose::SaveInput);
        }
      };
      p->virtual_list("inputs", std::move(spec)).tip(ctx.tr("jobs.inputs.tip"));
    }
    else if (!jobs.workspace().empty()) {
      p->label(ctx.tr("jobs.inputs.none")).disable();
    }

    /* Files dropped or picked before a workspace was chosen. */
    if (!jobs.pending_uploads().empty()) {
      p->label(ctx.store.catalog().format("jobs.pending", {{"count", std::to_string(jobs.pending_uploads().size())}}));
      ui::ListSpec spec;
      const std::vector<std::string> &pending = jobs.pending_uploads();
      spec.count = int(pending.size());
      spec.text = [&pending](int i) { return file_name(pending[size_t(i)]); };
      spec.rows = std::min(4.0f, float(pending.size()));
      p->virtual_list("pending", std::move(spec));
      ui::Layout &pr = p->row(false);
      pr.button("pending_start", ctx.tr("jobs.pending.start"), [&jobs]() { jobs.start_pending(); })
          .disable(!connected || jobs.workspace().empty());
      pr.button("pending_clear", ctx.tr("jobs.pending.clear"), [&jobs]() { jobs.clear_pending(); });
    }

    /* Uploads into this workspace that are still moving (the Transfers editor lists all). */
    int shown = 0;
    for (const bridge::Transfer &t : jobs.transfers()) {
      if (t.kind != "upload" || t.finished() || t.workspace_id != jobs.workspace() || shown >= 4) {
        continue;
      }
      const float f = t.bytes_total > 0 ? float(double(t.bytes_done) / double(t.bytes_total)) : 0.0f;
      std::string text = file_name(t.local) + " · " + transfer_state_text(ctx.store, t);
      if (t.action && t.action->in_review()) {
        text += " · " + std::string(ctx.tr("transfers.review_hint"));
      }
      p->progress(f, text).tip(t.local);
      shown++;
    }
  }

  /* ---- Submit form ---- */

  void submit_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    ui::Layout *p = l.panel("submit", ctx.tr("jobs.panel.submit"));
    if (!p) {
      return;
    }
    SubmitForm &f = jobs.form();
    const bool hub = jobs.hub();
    if (hub) {
      ui::Layout &v = p->prop(ctx.tr("jobs.form.mode"), ctx.tr("jobs.form.mode.tip"));
      v.dropdown("mode", {std::string(ctx.tr("jobs.form.mode.template")), std::string(ctx.tr("jobs.form.mode.custom"))},
                 {[&f]() { return f.use_template ? 0 : 1; }, [&f](int i) { f.use_template = i == 0; }});
      if (f.use_template) {
        std::vector<std::string> names = jobs.templates();
        int tsel = -1;
        for (size_t i = 0; i < names.size(); i++) {
          if (names[i] == f.template_name) {
            tsel = int(i);
          }
        }
        ui::Layout &t = p->prop(ctx.tr("jobs.form.template"));
        if (names.empty()) {
          t.label(ctx.tr("jobs.form.template.none")).disable();
        }
        else {
          t.dropdown("template", names, {[tsel]() { return tsel; }, [&f, names](int i) {
                                           if (i >= 0 && i < int(names.size())) {
                                             f.template_name = names[size_t(i)];
                                           }
                                         }});
        }
      }
      else {
        p->label(ctx.tr("jobs.form.custom_review")).disable();
      }
    }
    if (!hub || !f.use_template) {
      p->prop(ctx.tr("jobs.form.name"), ctx.tr("jobs.form.name.tip"))
          .text_field("name", ui::bind(f.name), {.placeholder = std::string(ctx.tr("jobs.form.name.placeholder"))});
      p->prop(ctx.tr("jobs.form.program"), ctx.tr("jobs.form.program.tip"))
          .text_field("program", ui::bind(f.program), {.mono = true});
      p->prop(ctx.tr("jobs.form.arguments"), ctx.tr("jobs.form.arguments.tip"))
          .text_field("arguments", ui::bind(f.arguments),
                      {.placeholder = std::string(ctx.tr("jobs.form.arguments.placeholder")), .mono = true});
      std::vector<std::string> backends;
      for (const char *b : kBackends) {
        backends.push_back(std::string(ctx.tr(std::string("jobs.backend.") + b)));
      }
      p->prop(ctx.tr("jobs.form.backend")).dropdown("backend", backends, ui::bind(f.backend));

      if (ui::Layout *r = p->panel("resources", ctx.tr("jobs.panel.resources"), false)) {
        r->prop(ctx.tr("jobs.form.layout"), ctx.tr("jobs.form.layout.tip"))
            .dropdown("layout", {std::string(ctx.tr("jobs.form.layout.threads")), std::string(ctx.tr("jobs.form.layout.mpi"))},
                      {[&f]() { return f.layout == LayoutMode::Mpi ? 1 : 0; },
                       [&f](int i) { f.layout = i == 1 ? LayoutMode::Mpi : LayoutMode::Threads; }});
        ui::NumberProps pos;
        pos.integer = true;
        pos.min = 1;
        pos.max = 2147483647;
        pos.step = 1;
        ui::NumberProps opt = pos;
        opt.min = 0;
        if (f.layout == LayoutMode::Threads) {
          r->prop(ctx.tr("jobs.form.cpus")).number("cpus", "", ui::bind_int(f.cpus), pos);
        }
        else {
          r->prop(ctx.tr("jobs.form.ranks")).number("ranks", "", ui::bind_int(f.ranks), opt);
          r->prop(ctx.tr("jobs.form.threads_per_rank"), ctx.tr("jobs.form.zero_default"))
              .number("threads_per_rank", "", ui::bind_int(f.threads_per_rank), opt);
        }
        r->prop(ctx.tr("jobs.form.nodes")).number("nodes", "", ui::bind_int(f.nodes), pos);
        ui::NumberProps mem = opt;
        mem.unit = std::string(ctx.tr("jobs.unit.mb"));
        r->prop(ctx.tr("jobs.form.memory"), ctx.tr("jobs.form.zero_default"))
            .number("memory_mb", "", ui::bind_int(f.memory_mb), mem);
        ui::NumberProps wall = opt;
        wall.unit = std::string(ctx.tr("jobs.unit.s"));
        r->prop(ctx.tr("jobs.form.walltime"), ctx.tr("jobs.form.zero_default"))
            .number("walltime", "", ui::bind_int(f.walltime_s), wall);
        r->prop(ctx.tr("jobs.form.gpus")).number("gpus", "", ui::bind_int(f.gpus), opt);
        r->prop(ctx.tr("jobs.form.queue")).text_field("queue", ui::bind(f.queue));
        r->prop(ctx.tr("jobs.form.account")).text_field("account", ui::bind(f.account));
      }
      if (ui::Layout *a = p->panel("advanced", ctx.tr("jobs.panel.advanced"), false)) {
        a->prop(ctx.tr("jobs.form.outputs"), ctx.tr("jobs.form.outputs.tip"))
            .text_field("outputs", ui::bind(f.outputs), {.placeholder = "result.png out/*.dat", .mono = true});
        a->prop(ctx.tr("jobs.form.env"), ctx.tr("jobs.form.env.tip"))
            .text_field("env", ui::bind(f.env), {.placeholder = "OMP_PROC_BIND=close", .mono = true});
      }
    }
    if (ui::Layout *rp = p->panel("retry", ctx.tr("jobs.panel.retry"), false)) {
      ui::NumberProps n;
      n.integer = true;
      n.min = 0;
      n.max = 10;
      n.step = 1;
      rp->prop(ctx.tr("jobs.form.auto_retries"), ctx.tr("jobs.form.auto_retries.tip"))
          .number("auto_retries", "", ui::bind_int(f.retry.auto_retries), n);
      ui::NumberProps b;
      b.min = 0;
      b.max = 600;
      b.step = 0.5;
      b.precision = 1;
      b.unit = std::string(ctx.tr("jobs.unit.s"));
      rp->prop(ctx.tr("jobs.form.backoff")).number("backoff", "", ui::Binding<double>{
          [&f]() { return f.retry.backoff_s; }, [&f](double v) { f.retry.backoff_s = v; }}, b);
    }

    /* Validation (live) and the submission's state. */
    const std::vector<FormIssue> issues = jobs.validate();
    if (!issues.empty() && !jobs.workspace().empty()) {
      p->label(issue_text(ctx.store, issues.front())).tip(issue_text(ctx.store, issues.front()));
    }
    const int uploading = jobs.uploads_in_flight();
    ui::Layout &br = p->row(false);
    br.button("submit_form", ctx.tr("jobs.submit"), [&jobs]() { jobs.submit(); })
        .disable(!jobs.ready() || jobs.workspace().empty() || uploading > 0)
        .tip(uploading > 0 ? ctx.tr("jobs.status.wait_uploads") : ctx.tr("jobs.submit.tip"));
    const auto &sub = jobs.submission();
    br.button("retry", ctx.tr("jobs.submit.retry"), [&jobs]() { jobs.retry_submission(); })
        .disable(!sub || !(sub->state == SubmitState::Failed || sub->state == SubmitState::Review) || !jobs.ready())
        .tip(ctx.tr("jobs.submit.retry.tip"));
    if (sub) {
      std::string s;
      switch (sub->state) {
        case SubmitState::Idle: break;
        case SubmitState::Sending: s = std::string(ctx.tr("jobs.submit.state.sending")); break;
        case SubmitState::Waiting: s = std::string(ctx.tr("jobs.submit.state.waiting")); break;
        case SubmitState::Review:
          s = ctx.store.catalog().format("jobs.submit.state.review",
                                         {{"id", sub->action ? sub->action->id.substr(0, 12) : std::string()}});
          break;
        case SubmitState::Done:
          s = ctx.store.catalog().format("jobs.submit.state.done", {{"id", sub->task_id.substr(0, 12)}});
          break;
        case SubmitState::Failed:
          s = ctx.store.catalog().format("jobs.submit.state.failed",
                                         {{"error", sub->error ? sub->error->message : std::string()}});
          break;
      }
      if (!s.empty()) {
        p->label(s).tip(ctx.store.catalog().format("jobs.submit.key", {{"key", sub->key}}));
      }
    }
  }

  /* ---- Task list ---- */

  void tasks_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    ui::Layout *p = l.panel("tasks", ctx.tr("jobs.panel.tasks"));
    if (!p) {
      return;
    }
    const std::vector<TaskRow> &tasks = jobs.tasks();
    const TaskRow *sel = jobs.selected_task();
    ui::Layout &row = p->row(false);
    row.button("cancel_task", ctx.tr("jobs.task.cancel"), [this, &jobs]() {
         cancel_id_ = jobs.selected();
         open_dialog(Dialog::CancelTask);
       })
        .disable(!jobs.ready() || !sel || sel->terminal() || sel->cancel_requested)
        .tip(ctx.tr("jobs.task.cancel.tip"));
    row.button("open_viewer", ctx.tr("jobs.task.open_viewer"), [&jobs]() { jobs.open_in_viewer(); })
        .disable(jobs.selected().empty())
        .tip(ctx.tr("jobs.task.open_viewer.tip"));

    ui::TableSpec t;
    t.columns = {{std::string(ctx.tr("jobs.col.name")), 7.0f},
                 {std::string(ctx.tr("jobs.col.state")), 4.0f},
                 {std::string(ctx.tr("jobs.col.backend")), 3.5f},
                 {std::string(ctx.tr("jobs.col.submitted")), 5.5f},
                 {std::string(ctx.tr("jobs.col.reason")), 8.0f}};
    t.rows = int(tasks.size());
    AppStore &store = ctx.store;
    t.cell = [&tasks, &store](int r, int c) -> std::string {
      const TaskRow &task = tasks[size_t(r)];
      switch (c) {
        case 0: return task.label();
        case 1:
          return task.cancelling() ? std::string(store.tr("jobs.state.cancelling")) :
                                     std::string(store.tr(task_state_key(task.state)));
        case 2:
          return task.backend.empty() ? std::string("-") :
                                        std::string(store.catalog().tr_or("jobs.backend." + task.backend, task.backend));
        case 3: return short_time(task.created_at);
        default: return task.reason;
      }
    };
    const ui::Theme theme = ctx.ui ? ctx.ui->theme() : ui::Theme::blender_dark();
    t.cell_color = [&tasks, theme](int r, int c) -> ui::Color {
      return c == 1 ? task_state_color(theme, tasks[size_t(r)]) : ui::Color{0, 0, 0, 0};
    };
    t.selected = {[&tasks, &jobs]() {
                    for (size_t i = 0; i < tasks.size(); i++) {
                      if (tasks[i].id == jobs.selected()) {
                        return int(i);
                      }
                    }
                    return -1;
                  },
                  [&tasks, &jobs](int i) {
                    if (i >= 0 && i < int(tasks.size())) {
                      jobs.select_task(tasks[size_t(i)].id);
                    }
                  }};
    t.visible_rows = 6.0f;
    t.data_version = jobs.version();
    p->table("tasks", std::move(t));
    if (tasks.empty()) {
      p->label(ctx.tr(jobs.workspace().empty() ? "jobs.tasks.no_workspace" : "jobs.tasks.none")).disable();
    }
  }

  /* ---- Task detail ---- */

  void detail_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    if (jobs.selected().empty()) {
      return;
    }
    const TaskRow *task = jobs.selected_task();
    const std::string title = ctx.store.catalog().format(
        "jobs.panel.detail", {{"name", task ? task->label() : jobs.selected().substr(0, 12)}});
    ui::Layout *p = l.panel("detail", title);
    if (!p) {
      return;
    }
    p->tabs("detail_tabs",
            {std::string(ctx.tr("jobs.detail.logs")), std::string(ctx.tr("jobs.detail.monitor")),
             std::string(ctx.tr("jobs.detail.artifacts")), std::string(ctx.tr("jobs.detail.info"))},
            ui::bind(detail_tab_));
    switch (detail_tab_) {
      case 0: logs_tab(*p, ctx, jobs); break;
      case 1: monitor_tab(*p, ctx, jobs); break;
      case 2: artifacts_tab(*p, ctx, jobs, task); break;
      default: info_tab(*p, ctx, jobs, task); break;
    }
  }

  void logs_tab(ui::Layout &p, EditorContext &ctx, JobsState &jobs)
  {
    ui::Layout &row = p.row(true);
    row.dropdown("log_stream",
                 {std::string(ctx.tr("jobs.logs.all")), "stdout", "stderr"}, ui::bind(log_stream_));
    row.label(ctx.tr(jobs.logs_ended() ? "jobs.logs.ended" : "jobs.logs.live")).disable();
    ui::LogBuffer &log = log_stream_ == 1 ? jobs.log_stdout() : (log_stream_ == 2 ? jobs.log_stderr() : jobs.log_all());
    p.log_view("task_log", log, 10.0f);
  }

  void monitor_tab(ui::Layout &p, EditorContext &ctx, JobsState &jobs)
  {
    const EventsSummary &e = jobs.events();
    const auto &cat = ctx.store.catalog();
    if (e.unsupported) {
      p.label(ctx.tr("jobs.monitor.unsupported")).disable();
      return;
    }
    if (e.count == 0) {
      p.label(ctx.tr(e.ended ? "jobs.monitor.none" : "jobs.monitor.waiting")).disable();
      return;
    }
    if (!e.app.empty()) {
      p.label(cat.format("jobs.monitor.app", {{"app", e.app}}));
    }
    std::string steps;
    if (e.step >= 0) {
      steps = e.total_steps > 0 ? std::to_string(e.step) + " / " + std::to_string(e.total_steps) : std::to_string(e.step);
    }
    if (e.fraction) {
      p.progress(float(*e.fraction), steps.empty() ? std::string() : steps);
    }
    else if (!steps.empty()) {
      p.label(cat.format("jobs.monitor.step", {{"step", steps}}));
    }
    if (!e.phase.empty()) {
      p.label(cat.format("jobs.monitor.phase", {{"phase", e.phase}}));
    }
    int shown = 0;
    for (const auto &[name, value] : e.metrics) {
      if (shown++ >= 6) {
        break;
      }
      p.label(name + " = " + value);
    }
    p.label(cat.format("jobs.monitor.counts", {{"events", std::to_string(e.count)},
                                                {"frames", std::to_string(e.frames)},
                                                {"checkpoints", std::to_string(e.checkpoints)},
                                                {"warnings", std::to_string(e.warnings)},
                                                {"errors", std::to_string(e.errors)}}));
    if (!e.last_message.empty()) {
      p.label(e.last_message).tip(e.last_message);
    }
    if (!e.completed.empty()) {
      p.label(cat.format("jobs.monitor.completed", {{"status", e.completed}}));
    }
    if (!e.verification.empty()) {
      p.label(cat.format("jobs.monitor.verification", {{"status", e.verification}}));
    }
    if (e.invalid > 0) {
      p.label(cat.format("jobs.monitor.invalid", {{"count", std::to_string(e.invalid)}})).disable();
    }
  }

  void artifacts_tab(ui::Layout &p, EditorContext &ctx, JobsState &jobs, const TaskRow *task)
  {
    const std::vector<ArtifactRow> &arts = jobs.artifacts();
    if (arts.empty()) {
      p.label(ctx.tr(task && task->terminal() ? "jobs.artifacts.none" : "jobs.artifacts.wait")).disable();
    }
    else {
      AppStore &store = ctx.store;
      ui::TableSpec t;
      t.columns = {{std::string(ctx.tr("jobs.col.file")), 9.0f},
                   {std::string(ctx.tr("jobs.col.size")), 4.0f, true, true},
                   {std::string(ctx.tr("jobs.col.verified")), 4.0f}};
      t.rows = int(arts.size());
      t.cell = [&arts, &store](int r, int c) -> std::string {
        const ArtifactRow &a = arts[size_t(r)];
        switch (c) {
          case 0: return a.file.path;
          case 1: return format_bytes(a.file.size);
          default:
            switch (a.verify) {
              case ArtifactRow::Verify::None: return "-";
              case ArtifactRow::Verify::Pending: return std::string(store.tr("jobs.artifacts.downloading"));
              case ArtifactRow::Verify::Ok: return std::string(store.tr("jobs.artifacts.verified"));
              case ArtifactRow::Verify::Mismatch: return std::string(store.tr("jobs.artifacts.mismatch"));
            }
            return {};
        }
      };
      const ui::Theme theme = ctx.ui ? ctx.ui->theme() : ui::Theme::blender_dark();
      t.cell_color = [&arts, theme](int r, int c) -> ui::Color {
        if (c != 2) {
          return {0, 0, 0, 0};
        }
        switch (arts[size_t(r)].verify) {
          case ArtifactRow::Verify::Ok: return theme.state.success;
          case ArtifactRow::Verify::Mismatch: return theme.state.error;
          default: return {0, 0, 0, 0};
        }
      };
      t.selected = ui::bind(art_sel_);
      t.visible_rows = std::min(5.0f, float(arts.size()));
      t.data_version = jobs.version();
      p.table("artifacts", std::move(t));
    }
    const ArtifactRow *sel = art_sel_ >= 0 && art_sel_ < int(arts.size()) ? &arts[size_t(art_sel_)] : nullptr;
    const std::string path = sel ? sel->file.path : std::string();
    const std::string local = sel ? sel->local : std::string();
    ui::Layout &row = p.row(false);
    row.button("download", ctx.tr("jobs.artifacts.download"), [&jobs, path]() {
         if (!path.empty()) {
           jobs.download_artifact(path);
         }
       })
        .disable(!sel || !jobs.ready() || sel->verify == ArtifactRow::Verify::Pending)
        .tip(ctx.tr("jobs.artifacts.download.tip"));
    row.button("save_as", ctx.tr("jobs.artifacts.save_as"), [this, &store = ctx.store, &jobs, path]() {
         if (!path.empty()) {
           artifact_path_ = path;
           pick(store, jobs, PathPurpose::SaveArtifact);
         }
       })
        .disable(!sel || !jobs.ready() || sel->verify == ArtifactRow::Verify::Pending);
    row.button("open_local", ctx.tr("jobs.artifacts.open"), [&jobs, local]() {
         if (!local.empty()) {
           jobs.open_local(local);
         }
       })
        .disable(!sel || sel->local.empty() || sel->verify != ArtifactRow::Verify::Ok)
        .tip(ctx.tr("jobs.artifacts.open.tip"));
    if (sel && !sel->transfer_id.empty()) {
      if (const bridge::Transfer *t = jobs.transfer(sel->transfer_id); t && !t->finished()) {
        const float f = t->bytes_total > 0 ? float(double(t->bytes_done) / double(t->bytes_total)) : 0.0f;
        p.progress(f, transfer_state_text(ctx.store, *t));
      }
      else if (sel->verify == ArtifactRow::Verify::Ok) {
        p.label(sel->local).tip(ctx.store.catalog().format("jobs.artifacts.sha", {{"sha", sel->file.sha256}}));
      }
    }
    const Preview &pv = jobs.preview();
    if (!pv.path.empty()) {
      p.separator();
      if (!pv.error.empty()) {
        p.label(ctx.store.catalog().format("jobs.preview.error", {{"error", pv.error}})).disable();
      }
      else {
        p.label(ctx.store.catalog().format("jobs.preview.title", {{"file", file_name(pv.path)},
                                                                  {"w", std::to_string(pv.width)},
                                                                  {"h", std::to_string(pv.height)}}));
        if (pv.texture) {
          p.image("preview", {pv.texture, pv.width, pv.height, 9.0f});
        }
        else {
          p.label(ctx.tr("jobs.preview.no_gpu")).disable();
        }
      }
    }
  }

  void info_tab(ui::Layout &p, EditorContext &ctx, JobsState &jobs, const TaskRow *task)
  {
    auto line = [&](const char *key, const std::string &value) {
      p.prop(ctx.tr(key)).label(value.empty() ? std::string("-") : value).tip(value);
    };
    line("jobs.info.id", jobs.selected());
    if (!task) {
      p.label(ctx.tr("jobs.info.not_listed")).disable();
      return;
    }
    line("jobs.info.name", task->name);
    line("jobs.info.state", std::string(ctx.tr(task_state_key(task->state))));
    line("jobs.info.backend", task->backend);
    line("jobs.info.exit_code", task->exit_code ? std::to_string(*task->exit_code) : std::string());
    line("jobs.info.reason", task->reason);
    line("jobs.info.created", task->created_at);
    line("jobs.info.updated", task->updated_at);
    if (task->raw.is_object() && task->raw.contains("spec") && task->raw["spec"].contains("argv")) {
      std::string cmd;
      for (const Json &a : task->raw["spec"]["argv"]) {
        if (a.is_string()) {
          cmd += (cmd.empty() ? "" : " ") + shlex_quote(a.get<std::string>());
        }
      }
      line("jobs.info.command", cmd);
    }
  }

  /* ---- Hub review ---- */

  void review_panel(ui::Layout &l, EditorContext &ctx, JobsState &jobs)
  {
    if (!jobs.hub()) {
      return;
    }
    const std::vector<ReviewItem> &items = jobs.reviews();
    ui::Layout *p = l.panel("review", ctx.store.catalog().format("jobs.panel.review", {{"count", std::to_string(items.size())}}));
    if (!p) {
      return;
    }
    if (items.empty()) {
      p->label(ctx.tr("jobs.review.none")).disable();
      return;
    }
    ui::TableSpec t;
    t.columns = {{std::string(ctx.tr("jobs.col.kind")), 6.0f},
                 {std::string(ctx.tr("jobs.col.id")), 5.0f},
                 {std::string(ctx.tr("jobs.col.reason")), 8.0f}};
    t.rows = int(items.size());
    t.cell = [&items](int r, int c) -> std::string {
      const ReviewItem &it = items[size_t(r)];
      switch (c) {
        case 0: return it.kind;
        case 1: return it.action.id.substr(0, 12);
        default: return it.action.review_reason;
      }
    };
    t.selected = ui::bind(review_sel_);
    t.visible_rows = std::min(4.0f, float(items.size()));
    t.data_version = jobs.version();
    p->table("reviews", std::move(t));
    const ReviewItem *sel = review_sel_ >= 0 && review_sel_ < int(items.size()) ? &items[size_t(review_sel_)] : nullptr;
    const std::string id = sel ? sel->action.id : std::string();
    ui::Layout &row = p->row(false);
    row.button("inspect", ctx.tr("jobs.review.inspect"), [&jobs, id]() { jobs.inspect(id); })
        .disable(!sel || sel->busy)
        .tip(ctx.tr("jobs.review.inspect.tip"));
    row.button("approve", ctx.tr("jobs.review.approve"), [&jobs, id]() { jobs.review(id, true); })
        .disable(!sel || sel->busy || !sel->inspected)
        .tip(ctx.tr("jobs.review.approve.tip"));
    row.button("reject", ctx.tr("jobs.review.reject"), [&jobs, id]() { jobs.review(id, false); })
        .disable(!sel || sel->busy);
    if (sel) {
      if (!sel->message.empty()) {
        p->paragraph(sel->message);
      }
      if (sel->inspected) {
        if (request_for_ != sel->action.id) {
          request_for_ = sel->action.id;
          request_log_.clear();
          request_log_.append(sel->request.dump(2) + "\n");
        }
        p->log_view("request", request_log_, 7.0f);
      }
      else {
        p->label(ctx.tr("jobs.review.not_inspected")).disable();
      }
    }
  }

  /* ---- File choosers (native dialog, else the path field) ---- */

  void pick(AppStore &store, JobsState &jobs, PathPurpose purpose)
  {
    const ui::Catalog &ctx = store.catalog();
    purpose_ = purpose;
    path_error_.clear();
    platform::FileDialogRequest req;
    switch (purpose) {
      case PathPurpose::UploadFiles:
        req.mode = platform::FileDialogMode::OpenFiles;
        req.title = std::string(ctx.tr("jobs.upload.files"));
        break;
      case PathPurpose::UploadFolder:
        req.mode = platform::FileDialogMode::OpenFolder;
        req.title = std::string(ctx.tr("jobs.upload.folder"));
        break;
      case PathPurpose::SaveArtifact:
        req.mode = platform::FileDialogMode::SaveFile;
        req.title = std::string(ctx.tr("jobs.artifacts.save_as"));
        req.file_name = file_name(artifact_path_);
        break;
      case PathPurpose::SaveInput:
        req.mode = platform::FileDialogMode::SaveFile;
        req.title = std::string(ctx.tr("jobs.inputs.save"));
        req.file_name = file_name(input_path_);
        break;
      case PathPurpose::TokenFile:
        req.mode = platform::FileDialogMode::OpenFiles;
        req.title = std::string(ctx.tr("conn.token_file"));
        break;
    }
    if (!jobs.file_dialog) {
      open_paths_dialog();
      return;
    }
    std::weak_ptr<bool> alive = alive_;
    JobsState *js = &jobs;
    jobs.file_dialog->open(req, [this, alive, js, purpose](platform::FileDialogResult r) {
      const auto a = alive.lock();
      if (!a || !*a) {
        return;
      }
      if (!r.error.empty()) {
        path_error_ = r.error;
        purpose_ = purpose;
        open_paths_dialog();
        return;
      }
      if (!r.paths.empty()) {
        purpose_ = purpose;
        use_paths(*js, r.paths);
      }
    });
  }

  void open_paths_dialog()
  {
    path_text_.clear();
    if (purpose_ == PathPurpose::SaveArtifact || purpose_ == PathPurpose::SaveInput) {
      path_text_ = file_name(purpose_ == PathPurpose::SaveArtifact ? artifact_path_ : input_path_);
    }
    /* The token-file chooser returns to the Add Runtime dialog afterwards. */
    return_to_add_ = dialog_ == Dialog::AddRuntime;
    dialog_ = Dialog::Paths;
  }

  /** Applies chosen paths; false (with path_error_) when they are unusable. */
  bool use_paths(JobsState &jobs, const std::vector<std::string> &paths)
  {
    for (const std::string &p : paths) {
      if (!platform::is_absolute_path(p)) {
        path_error_ = store_ ? store_->catalog().format("jobs.paths.not_absolute", {{"path", p}}) : p;
        return false;
      }
    }
    switch (purpose_) {
      case PathPurpose::UploadFiles:
      case PathPurpose::UploadFolder:
        jobs.upload(paths);
        break;
      case PathPurpose::SaveArtifact:
        jobs.download_artifact(artifact_path_, paths.front());
        break;
      case PathPurpose::SaveInput:
        jobs.download_input(input_path_, paths.front());
        break;
      case PathPurpose::TokenFile:
        add_token_file_ = paths.front();
        dialog_ = Dialog::AddRuntime;
        break;
    }
    return true;
  }

  /* ---- Dialogs ---- */

  void open_dialog(const Dialog d)
  {
    dialog_ = d;
    dialog_error_.clear();
    dialog_busy_ = false;
    if (d == Dialog::AddRuntime) {
      if (add_url_.empty()) {
        add_url_ = "http://127.0.0.1:9876";
      }
      add_token_.clear();
    }
    if (d == Dialog::PairHub) {
      pair_code_.clear();
      if (pair_device_.empty()) {
        pair_device_ = "STK Desktop";
      }
    }
    if (d == Dialog::NewWorkspace) {
      new_workspace_.clear();
    }
  }

  void dialogs(EditorContext &ctx, JobsState &jobs)
  {
    if (dialog_ == Dialog::None || !ctx.ui) {
      return;
    }
    const std::string key = "jobs_dialog_" + ctx.area.id();
    auto close = [this]() { dialog_ = Dialog::None; };
    ui::ModalOptions mo;
    mo.width_units = 20.0f;
    const auto &cat = ctx.store.catalog();
    switch (dialog_) {
      case Dialog::None: break;
      case Dialog::AddRuntime: {
        ui::Layout &m = ctx.ui->modal(key, ctx.tr("conn.add_runtime.title"), close, mo);
        m.paragraph(ctx.tr("conn.add_runtime.hint"));
        m.prop(ctx.tr("conn.name")).text_field("name", ui::bind(add_name_), {.placeholder = "cluster"});
        m.prop(ctx.tr("conn.url"), ctx.tr("conn.url.tip")).text_field("url", ui::bind(add_url_));
        m.prop(ctx.tr("conn.token"), ctx.tr("conn.token.tip"))
            .text_field("token", ui::bind(add_token_), {.password = true});
        ui::Layout &tf = m.prop(ctx.tr("conn.token_file"), ctx.tr("conn.token_file.tip")).row(true);
        tf.text_field("token_file", ui::bind(add_token_file_), {.mono = true});
        tf.button("browse", ctx.tr("jobs.browse"), [this, &store = ctx.store, &jobs]() {
            pick(store, jobs, PathPurpose::TokenFile);
          })
            .width(fit_units(ctx, ctx.tr("jobs.browse")));
        m.checkbox("check", ctx.tr("conn.check_now"), ui::bind(add_check_));
        dialog_footer(m, ctx, [this, &jobs, &cat]() {
          if (add_name_.empty()) {
            dialog_error_ = std::string(cat.tr("conn.err.name"));
            return;
          }
          if (add_token_.empty() == add_token_file_.empty()) {
            dialog_error_ = std::string(cat.tr("conn.err.token"));
            return;
          }
          bridge::AddRuntimeParams p;
          p.name = add_name_;
          p.url = add_url_;
          p.token = add_token_;
          p.token_file = add_token_file_;
          p.check = add_check_;
          dialog_busy_ = true;
          std::weak_ptr<bool> alive = alive_;
          jobs.add_runtime(p, [this, alive](const std::optional<bridge::Error> &e) {
            if (auto a = alive.lock(); !a || !*a) {
              return;
            }
            dialog_busy_ = false;
            if (e) {
              dialog_error_ = e->message;
            }
            else {
              add_token_.clear();
              dialog_ = Dialog::None;
            }
          });
        });
        break;
      }
      case Dialog::PairHub: {
        ui::Layout &m = ctx.ui->modal(key, ctx.tr("conn.pair_hub.title"), close, mo);
        m.paragraph(ctx.tr("conn.pair_hub.hint"));
        m.prop(ctx.tr("conn.name")).text_field("name", ui::bind(pair_name_), {.placeholder = "lab"});
        m.prop(ctx.tr("conn.url"), ctx.tr("conn.hub_url.tip")).text_field("url", ui::bind(pair_url_), {.placeholder = "https://"});
        m.prop(ctx.tr("conn.code"), ctx.tr("conn.code.tip")).text_field("code", ui::bind(pair_code_), {.password = true});
        m.prop(ctx.tr("conn.device_name")).text_field("device", ui::bind(pair_device_));
        dialog_footer(m, ctx, [this, &jobs, &cat]() {
          if (pair_name_.empty() || pair_url_.empty() || pair_code_.empty()) {
            dialog_error_ = std::string(cat.tr("conn.err.pair_fields"));
            return;
          }
          bridge::PairHubParams p{pair_name_, pair_url_, pair_code_, pair_device_};
          dialog_busy_ = true;
          std::weak_ptr<bool> alive = alive_;
          jobs.pair_hub(p, [this, alive](const std::optional<bridge::Error> &e) {
            if (auto a = alive.lock(); !a || !*a) {
              return;
            }
            dialog_busy_ = false;
            if (e) {
              dialog_error_ = e->message;
            }
            else {
              pair_code_.clear();
              dialog_ = Dialog::None;
            }
          });
        });
        break;
      }
      case Dialog::Remove: {
        ui::Layout &m = ctx.ui->modal(key, ctx.tr("conn.remove.title"), close, mo);
        const bool hub = remove_id_.rfind("hub:", 0) == 0;
        m.paragraph(cat.format(hub ? "conn.remove.warning_hub" : "conn.remove.warning_runtime", {{"name", remove_id_}}));
        dialog_footer(m, ctx, [this, &jobs]() {
          dialog_busy_ = true;
          std::weak_ptr<bool> alive = alive_;
          jobs.remove_connection(remove_id_, [this, alive](const std::optional<bridge::Error> &e) {
            if (auto a = alive.lock(); !a || !*a) {
              return;
            }
            dialog_busy_ = false;
            if (e) {
              dialog_error_ = e->message;
            }
            else {
              dialog_ = Dialog::None;
            }
          });
        }, "conn.remove.confirm");
        break;
      }
      case Dialog::NewWorkspace: {
        ui::Layout &m = ctx.ui->modal(key, ctx.tr("jobs.workspace.new_title"), close, mo);
        m.prop(ctx.tr("jobs.workspace.name")).text_field("name", ui::bind(new_workspace_));
        dialog_footer(m, ctx, [this, &jobs, &cat]() {
          if (new_workspace_.empty()) {
            dialog_error_ = std::string(cat.tr("jobs.workspace.err.name"));
            return;
          }
          dialog_busy_ = true;
          std::weak_ptr<bool> alive = alive_;
          jobs.create_workspace(new_workspace_, [this, alive](const std::optional<bridge::Error> &e) {
            if (auto a = alive.lock(); !a || !*a) {
              return;
            }
            dialog_busy_ = false;
            if (e) {
              dialog_error_ = e->message;
            }
            else {
              dialog_ = Dialog::None;
            }
          });
        });
        break;
      }
      case Dialog::CancelTask: {
        ui::Layout &m = ctx.ui->modal(key, ctx.tr("jobs.task.cancel.title"), close, mo);
        m.paragraph(cat.format("jobs.task.cancel.body", {{"id", cancel_id_.substr(0, 12)}}));
        dialog_footer(m, ctx, [this, &jobs]() {
          jobs.cancel_task(cancel_id_);
          dialog_ = Dialog::None;
        }, "jobs.task.cancel.confirm");
        break;
      }
      case Dialog::Paths: {
        const bool save = purpose_ == PathPurpose::SaveArtifact || purpose_ == PathPurpose::SaveInput;
        ui::Layout &m = ctx.ui->modal(key, ctx.tr(save ? "jobs.paths.save_title" : "jobs.paths.title"),
                                      [this]() { dialog_ = return_to_add_ ? Dialog::AddRuntime : Dialog::None; }, mo);
        m.paragraph(ctx.tr(save ? "jobs.paths.save_hint" : "jobs.paths.hint"));
        m.text_field("paths", ui::bind(path_text_), {.placeholder = "/home/me/case", .mono = true});
        if (!path_error_.empty()) {
          m.paragraph(path_error_);
        }
        ui::Layout &r = m.row().alignment(ui::LayoutAlign::Right);
        r.button("ok", ctx.tr("ui.ok"), [this, &jobs]() {
          const std::vector<std::string> paths = platform::split_path_list(path_text_);
          if (paths.empty()) {
            return;
          }
          const bool token = purpose_ == PathPurpose::TokenFile;
          if (use_paths(jobs, paths) && !token) {
            dialog_ = return_to_add_ ? Dialog::AddRuntime : Dialog::None;
          }
        });
        r.button("cancel", ctx.tr("ui.cancel"), [this]() { dialog_ = return_to_add_ ? Dialog::AddRuntime : Dialog::None; });
        break;
      }
    }
  }

  void dialog_footer(ui::Layout &m, EditorContext &ctx, std::function<void()> ok, const char *ok_key = "ui.ok")
  {
    if (!dialog_error_.empty()) {
      m.paragraph(dialog_error_);
    }
    if (dialog_busy_) {
      m.label(ctx.tr("jobs.dialog.busy")).disable();
    }
    ui::Layout &r = m.row().alignment(ui::LayoutAlign::Right);
    r.button("ok", ctx.tr(ok_key), std::move(ok)).disable(dialog_busy_);
    r.button("cancel", ctx.tr("ui.cancel"), [this]() { dialog_ = Dialog::None; });
  }

  std::shared_ptr<bool> alive_;
  AppStore *store_ = nullptr;
  std::string pref_connection_, pref_node_, pref_workspace_;
  bool prefs_applied_ = false;

  int detail_tab_ = 0;
  int log_stream_ = 0;
  int input_sel_ = -1;
  int art_sel_ = -1;
  int review_sel_ = -1;
  std::string request_for_;
  ui::LogBuffer request_log_{2000};

  Dialog dialog_ = Dialog::None;
  bool dialog_busy_ = false;
  bool return_to_add_ = false;
  std::string dialog_error_;
  std::string add_name_, add_url_, add_token_, add_token_file_;
  bool add_check_ = true;
  std::string pair_name_, pair_url_, pair_code_, pair_device_;
  std::string remove_id_, cancel_id_, new_workspace_;
  PathPurpose purpose_ = PathPurpose::UploadFiles;
  std::string path_text_, path_error_;
  std::string artifact_path_, input_path_;
};

}  // namespace

std::unique_ptr<Editor> make_jobs_editor(const EditorType &type)
{
  return std::make_unique<JobsEditor>(type);
}

}  // namespace stk::app
