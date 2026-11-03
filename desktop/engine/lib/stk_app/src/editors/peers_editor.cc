/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/app_store.hh"
#include "stk/app/analysis_document.hh"
#include "stk/app/peer_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/shell.hh"
#include "stk/core/sha256.hh"
#include "stk/wm/window.hh"
#include "project_navigation.hh"
#include <algorithm>
#include <cstddef>
#include <map>
#include <set>

namespace stk::app {
namespace {
using io::Json;
std::string abbreviated(const std::string &s) { return s.size() <= 20 ? s : s.substr(0, 8) + "…" + s.substr(s.size() - 8); }
class PeersEditor final : public Editor {
 public:
  explicit PeersEditor(const EditorType &type) : Editor(type), text_(defaults())
  {
    static uint64_t next = 0; scope_ = "peers-instance-" + std::to_string(++next);
  }
  bool has_unsaved_changes() const override { return saved_text() != defaults(); }
  bool can_change_project_selection(std::string_view) const override { return !has_unsaved_changes(); }
  void on_area_removed() override
  {
    text_ = saved_text(); if (state_ && view_) { state_->detach(view_); }
    ui_ = nullptr; area_ = nullptr; fields_.clear(); wake_scheduled_ = false; ++generation_;
  }
  bool navigate(const nlohmann::json &target, const std::weak_ptr<void> &, std::string &) override
  {
    const Json value = target;
    if (!value.is_object() || !canonical_uuid(io::get_string(value, "record_id")) ||
        io::get_string(value, "project_handle").empty() || !value.contains("expected_revision") ||
        !value.at("expected_revision").is_number_integer() || io::get_int(value, "expected_revision", -1) < 0 || has_unsaved_changes()) { return false; }
    pending_navigation_ = value; section_ = 2; return true;
  }
  void draw_header(ui::Layout &row, EditorContext &ctx) override
  {
    attach(ctx); workspace_link(row, ctx);
    row.button("peers_refresh", ctx.tr("peer.refresh"), [this, live = guard()] {
      if (live()) { state_->read(view_, "info"); read_page("pins.list", "pins.list", pins_offset_, pins_offset_); state_->read(view_, "connections.list"); }
    }).width(4).disable(!state_->supported() || view_->busy());
  }
  void draw_main(ui::Layout &layout, EditorContext &ctx) override
  {
    attach(ctx); ui_ = ctx.ui; fields_.clear(); auto &body = layout.scope(scope_);
    if (!state_->supported()) { body.paragraph(ctx.tr("peer.unsupported")); return; }
    state_->pump(view_); wake(ctx);
    body.tabs("peer_sections", {std::string(ctx.tr("peer.identity")), std::string(ctx.tr("peer.connection")),
      std::string(ctx.tr("peer.send")), std::string(ctx.tr("peer.receive"))},
      {[this] { return section_; }, [this, live = guard()](int n) { if (live() && n >= 0 && n < 4) { section_ = n; } }});
    if (!error_.empty()) { body.paragraph(ctx.tr(error_)); }
    if (!view_->error.empty()) { body.paragraph(view_->error.starts_with("peer.") ? std::string(ctx.tr(view_->error)) : view_->error); }
    if (view_->uncertain) { body.paragraph(ctx.tr("peer.uncertain")); }
    if (view_->operation.is_object()) {
      body.label(abbreviated(view_->operation_id) + " · " + io::get_string(view_->operation, "action") + " · " + io::get_string(view_->operation, "state"));
    }
    if (section_ == 0) { identity(body, ctx); }
    else if (section_ == 1) { connection(body, ctx); }
    else { files(body, ctx, section_ == 2 ? "sender" : "receiver"); }
    history(body, ctx);
    body.button("peer_discard", ctx.tr("peer.discard"), [this, live = guard()] {
      if (live() && !view_->busy()) { text_ = defaults(); source_project_.clear(); source_revision_ = -1; changed(true); }
    }).disable(view_->busy() || !has_unsaved_changes());
  }
  nlohmann::json save_state() const override { return {{"version", 1}, {"section", section_}}; }
  bool load_state(const nlohmann::json &state) override
  {
    const Json value = state;
    if (!value.is_object() || value.size() > 2) { return false; }
    for (auto it = value.begin(); it != value.end(); ++it) { if (it.key() != "version" && it.key() != "section") { return false; } }
    if ((value.contains("version") && value.at("version") != 1) || (value.contains("section") &&
        (!value.at("section").is_number_integer() || io::get_int(value, "section", -1) < 0 || io::get_int(value, "section", -1) > 3))) { return false; }
    section_ = int(io::get_int(value, "section", 0)); return true;
  }
  nlohmann::json save_workspace_state() const override
  {
    auto text = saved_text(); Json drafts = Json::object();
    for (const auto &key : portable()) { drafts[key] = text.at(key); }
    return {{"version", 1}, {"section", section_}, {"drafts", drafts}, {"source_project", source_project_}, {"source_revision", source_revision_}};
  }
  bool load_workspace_state(const nlohmann::json &state) override
  {
    const Json value = state;
    try {
      check_analysis_json_bounds(value, 32 * 1024);
      const std::set<std::string> keys = {"version", "section", "drafts", "source_project", "source_revision"};
      if (!value.is_object() || value.size() != keys.size()) { return false; }
      for (auto it = value.begin(); it != value.end(); ++it) { if (!keys.contains(it.key())) { return false; } }
      if (value.at("version") != 1 || !value.at("section").is_number_integer() || io::get_int(value, "section", -1) < 0 ||
          io::get_int(value, "section", -1) > 3 || !value.at("source_project").is_string() ||
          (!io::get_string(value, "source_project").empty() && !canonical_uuid(io::get_string(value, "source_project"))) ||
          !value.at("source_revision").is_number_integer() || io::get_int(value, "source_revision", -2) < -1 ||
          !value.at("drafts").is_object() || value.at("drafts").size() != portable().size()) { return false; }
      auto drafts = defaults();
      for (auto it = value.at("drafts").begin(); it != value.at("drafts").end(); ++it) {
        if (!portable().contains(it.key()) || !it.value().is_string() || it.value().get_ref<const std::string &>().size() > 4096) { return false; }
        drafts[it.key()] = it.value().get<std::string>();
      }
      if (state_ && view_) { state_->detach(view_); state_->invalidate_draft(view_, true); }
      text_ = std::move(drafts); section_ = int(io::get_int(value, "section", 0));
      source_project_ = io::get_string(value, "source_project"); source_revision_ = io::get_int(value, "source_revision", -1);
      reset_pages(); pending_navigation_ = nullptr; ui_ = nullptr; fields_.clear(); wake_scheduled_ = false; ++generation_; return true;
    }
    catch (const std::exception &) { return false; }
  }
 private:
  PeerState *state_ = nullptr; PeerState::ViewPtr view_; AppStore *store_ = nullptr; EditorArea *area_ = nullptr;
  ui::Context *ui_ = nullptr; std::weak_ptr<void> shell_; std::map<ui::WidgetId, std::string> fields_;
  std::map<std::string, std::string> text_; std::string scope_, error_, source_project_;
  int64_t source_revision_ = -1; int section_ = 0, route_ = 0; bool offerer_ = true, wake_scheduled_ = false;
  int64_t pins_offset_ = 0, operations_offset_ = 0, sessions_offset_ = 0;
  std::map<std::string, int64_t> files_offset_ = {{"sender", 0}, {"receiver", 0}};
  static constexpr int64_t page_limit_ = 20;
  uint64_t generation_ = 0, view_lifetime_ = 0; Json pending_navigation_;
  static std::map<std::string, std::string> defaults()
  {
    return {{"display_name", ""}, {"helper_prefix", ""}, {"remote_name", ""}, {"remote_owner", ""}, {"remote_key", ""},
      {"remote_peer", ""}, {"signal", ""}, {"snapshot_id", ""}, {"record_ids", ""}, {"target", ""},
      {"transfer_id", ""}, {"grant_id", ""}, {"session_id", ""}, {"original_operation", ""}};
  }
  static const std::set<std::string> &portable()
  {
    static const std::set<std::string> keys = {"display_name", "helper_prefix", "snapshot_id", "record_ids", "target"}; return keys;
  }
  std::map<std::string, std::string> saved_text() const
  {
    auto values = text_;
    if (ui_ && ui_->edit_state()) { const auto it = fields_.find(ui_->editing()); if (it != fields_.end()) { values[it->second] = ui_->edit_state()->text(); } }
    return values;
  }
  void attach(EditorContext &ctx)
  {
    store_ = &ctx.store; area_ = &ctx.area; shell_ = ctx.area.shell().lifetime();
    if (!state_) { state_ = &store_->peers(); view_ = state_->new_view(); }
    state_->sync(view_);
    if (view_lifetime_ != view_->lifetime_epoch) {
      view_lifetime_ = view_->lifetime_epoch; wake_scheduled_ = false; ++generation_;
    }
    if (pending_navigation_.is_object()) {
      const auto &p = store_->project().project();
      if (p && p->handle == io::get_string(pending_navigation_, "project_handle") && p->revision == io::get_int(pending_navigation_, "expected_revision", -1)) {
        text_["record_ids"] = io::get_string(pending_navigation_, "record_id"); source_project_ = p->id; source_revision_ = p->revision; changed(true);
      }
      else { error_ = "peer.source_changed"; }
      pending_navigation_ = nullptr;
    }
  }
  std::function<bool()> guard(bool draft = false) const
  {
    const auto weak = lifetime(), shell = shell_; const auto epoch = generation_, life = view_ ? view_->lifetime_epoch : 0,
      selected = view_ ? view_->selection_epoch : 0, input = view_ ? view_->draft_epoch : 0,
      bridge = store_ ? store_->bridge_epoch() : 0, project = store_ ? store_->project_scope_epoch() : 0; const auto area = area_;
    return [this, weak, shell, epoch, life, selected, input, bridge, project, area, draft] {
      return !weak.expired() && !shell.expired() && area_ && area_ == area && &area->editor() == this && store_ && view_ &&
        generation_ == epoch && view_->lifetime_epoch == life && view_->selection_epoch == selected &&
        store_->bridge_epoch() == bridge && store_->project_scope_epoch() == project && (!draft || view_->draft_epoch == input);
    };
  }
  void changed(bool source = false) { error_.clear(); state_->invalidate_draft(view_, source); store_->changed(); }
  Json value(const std::string &key) const { const auto it = view_->values.find(key); return it == view_->values.end() ? Json() : it->second; }
  void reset_pages()
  {
    pins_offset_ = operations_offset_ = sessions_offset_ = 0;
    files_offset_["sender"] = files_offset_["receiver"] = 0;
    if (view_) {
      for (const auto key : {"pins.list", "operations.list", "sessions.list", "files.list.sender", "files.list.receiver"}) {
        view_->values.erase(key);
      }
    }
  }
  bool read_page(const std::string &method, const std::string &key, int64_t &offset,
                 const int64_t requested, Json params = Json::object())
  {
    if (requested < 0 || requested > 4096 || view_->busy()) { return false; }
    const auto found = view_->values.find(key);
    const bool had_page = found != view_->values.end(); const auto old = had_page ? found->second : Json();
    view_->values.erase(key); params["offset"] = requested; params["limit"] = page_limit_;
    // Clear before dispatch so an immediately delivered new page is not erased.
    // This editor generation never changes the controller's new read fences.
    if (!state_->read(view_, method, std::move(params))) {
      if (had_page && !view_->values.contains(key)) { view_->values[key] = old; }
      return false;
    }
    offset = requested; wake_scheduled_ = false; ++generation_; store_->changed(); return true;
  }
  void page_controls(ui::Layout &body, EditorContext &ctx, const std::string &widget,
                     const std::string &method, const std::string &key, const std::string &items,
                     int64_t &offset, Json params = Json::object())
  {
    const auto list = value(key);
    const auto count = list.is_object() && list.contains(items) && list.at(items).is_array() ? int64_t(list.at(items).size()) : 0;
    auto &row = body.row(); row.label(std::to_string(offset + (count ? 1 : 0)) + "–" + std::to_string(offset + count));
    for (const auto next : {false, true}) {
      const auto requested = next ? offset + page_limit_ : std::max(int64_t(0), offset - page_limit_);
      row.button(widget + (next ? "/next" : "/previous"), ctx.tr(next ? "peer.next" : "peer.previous"),
        [this, method, key, params, requested, selected_offset = &offset, live = guard()] {
          if (live()) { read_page(method, key, *selected_offset, requested, params); }
        }).disable(view_->busy() || view_->reading() || (next ? count < page_limit_ || requested > 4096 : offset == 0));
    }
  }
  void field(ui::Layout &body, EditorContext &ctx, const std::string &key, const char *label, bool source = false)
  {
    auto &w = body.prop(ctx.tr(label)).text_field("peer_" + key, {[this, key] { return text_.at(key); },
      [this, key, source, live = guard()](std::string s) {
        if (live() && !view_->busy() && text_.at(key) != s) {
          text_[key] = std::move(s);
          if (key == "grant_id" || key == "transfer_id") { view_->values.erase("files.query"); }
          if (key == "session_id") { view_->values.erase("sessions.host"); }
          if (key == "snapshot_id") { view_->values.erase("snapshot"); }
          changed(source);
        }
      }},
      {.max_length = key == "signal" ? std::size_t(400000) : std::size_t(4096)});
    w.disable(view_->busy()); fields_[w.id] = key;
  }
  void action(ui::Layout &row, EditorContext &ctx, const std::string &key, const char *label, const std::string &method, Json params, bool enabled = true)
  {
    row.button(key, ctx.tr(label), [this, method, params = std::move(params), live = guard(true)] {
      if (live() && !view_->busy()) { state_->act(view_, method, params); }
    }).disable(!enabled || view_->busy());
  }
  void copy(ui::Layout &row, EditorContext &ctx, const std::string &key, std::string text)
  {
    auto *window = ctx.draw ? ctx.draw->window : nullptr;
    row.button(key, ctx.tr("peer.copy"), [window, text = std::move(text), live = guard()] { if (live() && window) { window->manager().set_clipboard_text(text); } }).disable(!window);
  }
  void wake(EditorContext &ctx)
  {
    auto *wm = ctx.area.shell().window_manager(); if (!wm || wake_scheduled_ || view_->follow_until <= 0) { return; }
    const auto weak = lifetime(), shell = shell_; const auto epoch = generation_, life = view_->lifetime_epoch;
    const auto *area = area_; const auto *store = store_; wake_scheduled_ = true;
    const auto timer = wm->add_timer(300, 0, [this, weak, shell, epoch, life, area, store] {
      if (weak.expired() || generation_ != epoch) { return; }
      wake_scheduled_ = false;
      if (shell.expired() || !view_ || view_->lifetime_epoch != life || area_ != area || store_ != store || !store_) { return; }
      store_->changed();
    });
    if (!timer) { wake_scheduled_ = false; }
  }
  void identity(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("peer.identity_hint")); const auto info = value("info"); const auto own = info.is_object() ? info.value("identity", Json()) : Json();
    field(body, ctx, "display_name", "peer.device_name");
    action(body, ctx, "peer_initialize", "peer.initialize", "identity.initialize", {{"display_name", text_["display_name"]}}, own.is_null() && !text_["display_name"].empty());
    if (own.is_object()) {
      const auto card = own.at("card"); body.label(io::get_string(card, "display_name"));
      body.paragraph(io::get_string(card, "peer_id")); copy(body, ctx, "peer_copy_card", io::python_json_dumps(card, true, true));
      auto &row = body.row(); const auto generation = io::get_int(own, "generation", -1);
      action(row, ctx, "peer_rotate", "peer.rotate", "identity.rotate", {{"expected_generation", generation}});
      action(row, ctx, "peer_revoke_identity", "peer.revoke_identity", "identity.revoke", {{"expected_generation", generation}}, own.value("active", false));
    }
    body.paragraph(ctx.tr("peer.pin_hint"));
    field(body, ctx, "remote_name", "peer.remote_name"); field(body, ctx, "remote_owner", "peer.remote_owner");
    field(body, ctx, "remote_key", "peer.remote_key"); field(body, ctx, "remote_peer", "peer.remote_peer");
    const Json card = {{"format", "stk.peer-device/1"}, {"display_name", text_["remote_name"]}, {"owner_id", text_["remote_owner"]}, {"public_key", text_["remote_key"]}, {"peer_id", text_["remote_peer"]}};
    action(body, ctx, "peer_verify_pin", "peer.verify", "pins.verify", {{"card", card}, {"expected_peer_id", text_["remote_peer"]}},
      canonical_uuid(text_["remote_owner"]) && core::is_sha256_hex(text_["remote_key"]) && core::is_sha256_hex(text_["remote_peer"]) && !text_["remote_name"].empty());
    const auto pins = value("pins.list");
    page_controls(body, ctx, "peer_pins_page", "pins.list", "pins.list", "pins", pins_offset_);
    if (pins.is_object()) { for (const auto &pin : pins.at("pins")) {
      const auto id = io::get_string(pin.at("card"), "peer_id"); auto &row = body.row();
      row.label(io::get_string(pin.at("card"), "display_name") + " · " + abbreviated(id));
      action(row, ctx, "peer_revoke_pin/" + id, "peer.revoke_pin", "pins.revoke", {{"peer_id", id}}, pin.value("active", false));
    } }
  }
  void connection(ui::Layout &body, EditorContext &ctx)
  {
    body.paragraph(ctx.tr("peer.connection_hint")); field(body, ctx, "helper_prefix", "peer.helper_prefix");
    field(body, ctx, "remote_peer", "peer.remote_peer");
    body.checkbox("peer_offerer", ctx.tr("peer.offerer"), {[this] { return offerer_; }, [this, live = guard()](bool b) { if (live() && !view_->busy()) { offerer_ = b; changed(); } }}).disable(view_->busy());
    body.prop(ctx.tr("peer.route")).dropdown("peer_route", {"All", "UDP", "TCP", "IPv6"}, {[this] { return route_; },
      [this, live = guard()](int n) { if (live() && !view_->busy() && n >= 0 && n < 4) { route_ = n; changed(); } }}).disable(view_->busy());
    static const char *routes[] = {"all", "udp", "tcp", "ipv6"};
    action(body, ctx, "peer_open", "peer.open_connection", "connections.open", {{"helper_prefix", text_["helper_prefix"]}, {"peer_id", text_["remote_peer"]}, {"offerer", offerer_}, {"route", routes[route_]}}, !text_["helper_prefix"].empty() && core::is_sha256_hex(text_["remote_peer"]));
    connections(body, ctx);
    if (view_->connection.empty()) { return; }
    body.button("peer_signal_read", ctx.tr("peer.signal_read"), [this, live = guard()] { if (live()) { state_->read(view_, "connections.signals", {{"connection_id", view_->connection}}); } }).disable(view_->busy());
    const auto signal = value("connections.signals");
    if (signal.is_object() && signal.contains("signal_text") && signal.at("signal_text").is_string()) {
      body.paragraph(ctx.tr("peer.signal_ready")); copy(body, ctx, "peer_copy_signal", signal.at("signal_text").get<std::string>());
    }
    field(body, ctx, "signal", "peer.signal_input");
    action(body, ctx, "peer_signal_push", "peer.signal_push", "connections.push_signal", {{"connection_id", view_->connection}, {"signal_text", text_["signal"]}}, !text_["signal"].empty());
    auto &row = body.row();
    action(row, ctx, "peer_authenticate", "peer.authenticate", "connections.authenticate", {{"connection_id", view_->connection}});
    action(row, ctx, "peer_close_connection", "peer.close_connection", "connections.close", {{"connection_id", view_->connection}});
    body.paragraph(ctx.tr("peer.signal_ephemeral"));
  }
  void connections(ui::Layout &body, EditorContext &ctx)
  {
    Json rows = Json::array(); const auto list = value("connections.list");
    if (list.is_object()) { rows = list.at("connections"); }
    const auto opened = value("connections.open");
    if (opened.is_object() && std::none_of(rows.begin(), rows.end(), [&](const Json &r) { return r.at("connection_id") == opened.at("connection_id"); })) { rows.push_back(opened); }
    for (const auto &item : rows) {
      const auto id = io::get_string(item, "connection_id");
      body.button("peer_select_connection/" + id, abbreviated(io::get_string(item, "peer_id")) + " · " + io::get_string(item, "state"), [this, id, live = guard()] {
        if (live() && state_->set_connection(view_, id)) {
          text_["signal"].clear(); view_lifetime_ = view_->lifetime_epoch; wake_scheduled_ = false; ++generation_; changed();
        }
      }).disable(view_->busy());
    }
    if (!view_->connection.empty()) { body.label(std::string(ctx.tr("peer.selected_connection")) + " " + abbreviated(view_->connection)); }
  }
  std::vector<std::string> records() const
  {
    std::vector<std::string> result; std::string part;
    const auto append = [&] { if (!part.empty()) { result.push_back(part); part.clear(); } };
    for (const auto c : text_.at("record_ids")) { if (c == ',' || c == ' ' || c == '\n' || c == '\t') { append(); } else { part += c; } }
    append(); return result;
  }
  void source(ui::Layout &body, EditorContext &ctx)
  {
    auto &p = store_->project(); const auto &project = p.project();
    const bool available = project && p.loaded() && !p.busy();
    body.button("peer_load_snapshots", ctx.tr("peer.load_snapshots"), [this, live = guard()] {
      if (live()) { state_->read_source(view_, "project.snapshots.list_summaries", {{"offset", 0}, {"limit", 64}}); }
    }).disable(!available || view_->busy());
    const auto list = value("snapshots");
    if (list.is_object()) {
      const auto offset = io::get_int(list, "offset", 0), total = io::get_int(list, "total", 0); auto &page = body.row();
      for (const auto next : {false, true}) {
        const auto requested = next ? offset + 64 : std::max(int64_t(0), offset - 64);
        page.button(next ? "peer_snapshots_next" : "peer_snapshots_previous", ctx.tr(next ? "peer.next" : "peer.previous"),
          [this, requested, live = guard()] { if (live()) { state_->read_source(view_, "project.snapshots.list_summaries", {{"offset", requested}, {"limit", 64}}); } })
          .disable(view_->busy() || (next ? offset + 64 >= total : offset == 0));
      }
    }
    if (list.is_object()) { for (const auto &item : list.at("snapshots")) {
      const auto id = io::get_string(item, "id");
      body.button("peer_snapshot/" + id, io::get_string(item, "created_at") + " · " + std::to_string(io::get_int(item, "file_count", 0)), [this, id, live = guard(true)] {
        if (live()) { text_["snapshot_id"] = id; const auto &p = store_->project().project(); source_project_ = p->id; source_revision_ = p->revision; changed(true); state_->read_source(view_, "project.snapshots.get", {{"snapshot_id", id}}); }
      }).disable(view_->busy());
    } }
    field(body, ctx, "snapshot_id", "peer.snapshot_id", true); field(body, ctx, "record_ids", "peer.record_ids", true);
    const auto snapshot = value("snapshot");
    if (snapshot.is_object() && snapshot.contains("snapshot") && io::get_string(snapshot.at("snapshot"), "id") == text_["snapshot_id"]) {
      for (const auto &file : snapshot.at("snapshot").at("manifest").at("files")) {
        const auto id = io::get_string(file, "record_id"); const auto selected = records(); const bool checked = std::find(selected.begin(), selected.end(), id) != selected.end();
        body.checkbox("peer_file/" + id, io::get_string(file, "name") + " · " + std::to_string(io::get_int(file, "size", 0)), {[checked] { return checked; }, [this, id, live = guard(true)](bool enabled) {
          if (!live()) { return; } auto selected = records(); std::erase(selected, id); if (enabled && selected.size() < 64) { selected.push_back(id); }
          text_["record_ids"].clear(); for (const auto &r : selected) { if (!text_["record_ids"].empty()) { text_["record_ids"] += ","; } text_["record_ids"] += r; } changed(true);
        }}).disable(view_->busy());
      }
    }
    const auto chosen = records(); const bool valid = !chosen.empty() && chosen.size() <= 64 && std::all_of(chosen.begin(), chosen.end(), canonical_uuid);
    action(body, ctx, "peer_prepare", "peer.prepare", "files.prepare", {{"snapshot_id", text_["snapshot_id"]}, {"record_ids", chosen}}, available && valid && canonical_uuid(text_["snapshot_id"]) && project->id == source_project_ && project->revision == source_revision_);
    if (available && !source_project_.empty() && (project->id != source_project_ || project->revision != source_revision_)) { body.paragraph(ctx.tr("peer.source_changed")); }
  }
  void manifest(ui::Layout &body, const Json &m)
  {
    if (!m.is_object() || !m.contains("files")) { return; }
    for (const auto &f : m.at("files")) { body.paragraph(io::get_string(f, "name") + " · " + std::to_string(io::get_int(f, "bytes", 0)) + " · " + io::get_string(f, "sha256")); }
  }
  void sessions(ui::Layout &body, EditorContext &ctx)
  {
    field(body, ctx, "session_id", "peer.session_id");
    auto *panel = body.panel("peer_sessions", ctx.tr("peer.session_id"), false);
    if (panel) {
      panel->button("peer_list_sessions", ctx.tr("peer.refresh"), [this, live = guard()] {
        if (live()) { read_page("sessions.list", "sessions.list", sessions_offset_, sessions_offset_); }
      }).disable(view_->busy());
      page_controls(*panel, ctx, "peer_sessions_page", "sessions.list", "sessions.list", "sessions", sessions_offset_);
      const auto list = value("sessions.list");
      if (list.is_object()) { for (const auto &saved : list.at("sessions")) {
        const auto id = io::get_string(saved.at("offer"), "session_id");
        const bool host = io::get_string(saved, "role") == "host";
        const auto &remote = saved.at("offer").at(host ? "recipient" : "host");
        panel->button("peer_select_session/" + id,
          io::get_string(remote, "display_name") + " · " + abbreviated(io::get_string(remote, "peer_id")) + " · " +
            abbreviated(id) + " · " + std::string(ctx.tr(host ? "peer.host" : "peer.receive")),
          [this, id, live = guard(true)] {
            if (live()) {
              // History selects only text. Host approval/recipient Accept and
              // revocation still require their separate explicit owner actions.
              text_["session_id"] = id; view_->values.erase("sessions.host"); changed();
            }
          }).disable(view_->busy());
      } }
    }
  }
  void files(ui::Layout &body, EditorContext &ctx, const std::string &role)
  {
    const bool sender = role == "sender"; connections(body, ctx);
    if (sender) {
      body.paragraph(ctx.tr("peer.prepare_hint")); if (auto *panel = body.panel("peer_source", ctx.tr("peer.source"))) { source(*panel, ctx); }
      const auto plan = value("files.prepare"); if (plan.is_object()) { manifest(body, plan.at("manifest")); body.paragraph(io::get_string(plan, "manifest_sha256")); }
      sessions(body, ctx);
      action(body, ctx, "peer_host", "peer.host", "sessions.host", {{"connection_id", view_->connection}, {"lifetime", 600}, {"session_id", text_["session_id"].empty() ? Json() : Json(text_["session_id"])}}, !view_->connection.empty());
      const auto hosted = value("sessions.host");
      const auto session = !text_["session_id"].empty() ? text_["session_id"] :
        hosted.is_object() && hosted.contains("result") && hosted.at("result").is_object() && hosted.at("result").contains("offer") ?
        io::get_string(hosted.at("result").at("offer"), "session_id") : text_["session_id"];
      if (!session.empty()) { body.label(std::string(ctx.tr("peer.session_id")) + " " + session); }
      action(body, ctx, "peer_offer", "peer.offer", "files.offer", {{"connection_id", view_->connection}, {"plan_id", io::get_string(plan, "plan_id")}, {"database_generation", io::get_string(plan, "database_generation")}, {"session_id", session}, {"transfer_id", text_["transfer_id"].empty() ? Json() : Json(text_["transfer_id"])}}, state_->source_current(view_) && !view_->connection.empty() && canonical_uuid(session));
      action(body, ctx, "peer_revoke_session", "peer.revoke_session", "sessions.revoke", {{"session_id", session}}, canonical_uuid(session));
    }
    else {
      sessions(body, ctx);
      action(body, ctx, "peer_revoke_session", "peer.revoke_session", "sessions.revoke", {{"session_id", text_["session_id"]}}, canonical_uuid(text_["session_id"]));
    }
    body.button("peer_list_files", ctx.tr("peer.list_files"), [this, role, live = guard()] {
      if (live()) { read_page("files.list", "files.list." + role, files_offset_.at(role), files_offset_.at(role), {{"role", role}}); }
    }).disable(view_->busy());
    page_controls(body, ctx, "peer_files_page/" + role, "files.list", "files.list." + role, "transfers", files_offset_.at(role), {{"role", role}});
    const auto list = value("files.list." + role);
    if (list.is_object()) { for (const auto &t : list.at("transfers")) {
      const auto id = io::get_string(t, "transfer_id");
      body.button("peer_transfer/" + id, abbreviated(id) + " · " + io::get_string(t, "state"), [this, id, role, live = guard()] {
        if (live()) {
          text_["transfer_id"] = id; text_["grant_id"].clear(); view_->values.erase("files.query"); changed();
          state_->read(view_, "files.get", {{"role", role}, {"transfer_id", id}});
        }
      }).disable(view_->busy());
    } }
    field(body, ctx, "transfer_id", "peer.transfer_id");
    const auto id = text_["transfer_id"]; const bool selected = canonical_uuid(id), connected = !view_->connection.empty();
    body.button("peer_file_detail", ctx.tr("peer.details"), [this, id, role, live = guard(true)] { if (live()) { state_->read(view_, "files.get", {{"role", role}, {"transfer_id", id}}); } }).disable(!selected || view_->busy());
    const auto detail = value("files.get." + role); const bool reviewed = detail.is_object() && io::get_string(detail.at("transfer"), "transfer_id") == id;
    if (reviewed) { manifest(body, detail.at("manifest")); body.paragraph(io::get_string(detail.at("transfer"), "state")); body.paragraph(io::get_string(detail.at("transfer"), "manifest_sha256")); }
    if (!sender) {
      field(body, ctx, "target", "peer.target"); const auto offer = reviewed ? detail.at("offer") : Json();
      action(body, ctx, "peer_accept", "peer.accept", "files.accept", {{"connection_id", view_->connection}, {"transfer_id", id}, {"offer_operation_id", io::get_string(offer, "offer_operation_id")}, {"target", text_["target"]}}, reviewed && offer.is_object() && connected && !text_["target"].empty());
    }
    else {
      action(body, ctx, "peer_query", "peer.query", "files.query", {{"connection_id", view_->connection}, {"transfer_id", id}, {"original_operation_id", nullptr}}, connected && selected);
      const auto status = value("files.query"); const auto grant = !text_["grant_id"].empty() ? text_["grant_id"] :
        status.is_object() && io::get_string(status, "transfer_id") == id ? io::get_string(status, "grant_id") : std::string();
      if (status.is_object() && io::get_string(status, "transfer_id") == id) { body.paragraph(io::get_string(status, "state") + " · " + grant); }
      field(body, ctx, "grant_id", "peer.grant_id");
      auto &row = body.row();
      const bool sending = view_->operation.is_object() && io::get_string(view_->operation, "action") == "files.send" &&
        io::get_string(view_->operation, "state") == "running" && io::get_string(view_->operation, "transfer_id") == id;
      for (const auto resume : {false, true}) { action(row, ctx, resume ? "peer_resume" : "peer_send", resume ? "peer.resume" : "peer.send_now", "files.send", {{"connection_id", view_->connection}, {"transfer_id", id}, {"grant_id", grant}, {"resume", resume}, {"timeout", 3600}}, connected && selected && canonical_uuid(grant) && !sending); }
      action(body, ctx, "peer_cancel", "peer.cancel", "files.cancel", {{"connection_id", view_->connection}, {"transfer_id", id}, {"grant_id", grant.empty() ? Json() : Json(grant)}}, connected && selected);
    }
    action(body, ctx, "peer_file_revoke", "peer.file_revoke", "files.revoke", {{"role", role}, {"transfer_id", id}}, selected);
  }
  void history(ui::Layout &body, EditorContext &ctx)
  {
    auto *panel = body.panel("peer_history", ctx.tr("peer.history"), false); if (!panel) { return; }
    panel->button("peer_operations", ctx.tr("peer.operations"), [this, live = guard()] {
      if (live()) { read_page("operations.list", "operations.list", operations_offset_, operations_offset_); }
    }).disable(view_->busy());
    page_controls(*panel, ctx, "peer_operations_page", "operations.list", "operations.list", "operations", operations_offset_);
    const auto list = value("operations.list");
    if (list.is_object()) { for (const auto &op : list.at("operations")) {
      const auto id = io::get_string(op, "operation_id"); panel->button("peer_operation/" + id, abbreviated(id) + " · " + io::get_string(op, "action") + " · " + io::get_string(op, "state"), [this, op, live = guard()] { if (live()) { state_->select_operation(view_, op); } }).disable(view_->busy());
    } }
    if (!view_->operation_id.empty()) {
      panel->paragraph(view_->operation_id + " · " + io::get_string(view_->operation, "state"));
      panel->button("peer_operation_check", ctx.tr("peer.check_operation"), [this, live = guard()] { if (live()) { state_->check_operation(view_); } }).disable(view_->busy());
    }
    field(*panel, ctx, "original_operation", "peer.original_operation");
    const auto original = text_["original_operation"];
    action(*panel, ctx, "peer_identity_recover", "peer.identity_recover", "identity.recover", {{"original_operation_id", original}}, canonical_uuid(original));
    action(*panel, ctx, "peer_file_recover", "peer.file_recover", "files.recover", {{"connection_id", view_->connection}, {"send_operation_id", original}}, canonical_uuid(original) && !view_->connection.empty());
  }
};
}
std::unique_ptr<Editor> make_peers_editor(const EditorType &type) { return std::make_unique<PeersEditor>(type); }
}  // namespace stk::app
