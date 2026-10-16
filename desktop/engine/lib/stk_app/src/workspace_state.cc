/* SPDX-License-Identifier: GPL-2.0-or-later */
/** Portable desktop snapshots: all editor trees are verified before replacing live state. */
#include "stk/app/shell.hh"

#include <algorithm>
#include <fstream>
#include <map>
#include <random>
#include <set>
#include <stdexcept>
#include <utility>

#include "stk/app/editor_area.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/app/workspace_transfer.hh"
#include "stk/core/mmap.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "stk/wm/window.hh"

namespace stk::app {
namespace {
using io::Json;
using bridge::Error;
using bridge::ErrorCode;
namespace fs = std::filesystem;

Error workspace_error(const std::string &text, ErrorCode code = ErrorCode::Conflict)
{
  return Error::make(code, text);
}
std::string workspace_session(const bridge::Client *client)
{
  return client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
}
void require(bool condition, const char *message)
{
  if (!condition) { throw std::invalid_argument(message); }
}
void require_loaded(bool condition, const std::string *error, const char *message)
{
  if (!condition) { throw std::invalid_argument(error && !error->empty() ? *error : message); }
}
void keys(const Json &value, const std::set<std::string> &required, const std::set<std::string> &optional = {})
{
  require(value.is_object(), "Workspace state needs an object");
  for (const auto &name : required) { require(value.contains(name), "Workspace state is missing a required key"); }
  for (auto it = value.begin(); it != value.end(); ++it) {
    require(required.count(it.key()) || optional.count(it.key()), "Unknown workspace state setting");
  }
}
std::string text(const Json &value)
{
  require(value.is_string(), "Workspace text setting is invalid");
  const auto result = value.get<std::string>();
  require(result.size() <= 32768 && result.find('\0') == std::string::npos, "Workspace text exceeds its bounds");
  return result;
}
void safe_file(const fs::path &path)
{
  require(path.is_absolute(), "Workspace payload must use an absolute local path");
  auto checked = path;
#ifdef __APPLE__
  // Darwin exposes these fixed system directories through root-owned aliases.
  // Accept only an alias that actually has the standard /private target; every
  // application/resource component still passes the ordinary no-symlink walk.
  for (const char *name : {"var", "tmp", "etc"}) {
    const auto alias = fs::path("/") / name;
    const auto relative = path.lexically_relative(alias);
    if (relative.empty() || relative.is_absolute() || *relative.begin() == "..") { continue; }
    std::error_code ec;
    const auto status = fs::symlink_status(alias, ec);
    if (ec || !fs::is_symlink(status)) { continue; }
    const auto target = fs::read_symlink(alias, ec);
    if (ec) { continue; }
    const auto absolute_target = target.is_absolute() ? target : alias.parent_path() / target;
    const auto expected = fs::path("/private") / name;
    if (absolute_target.lexically_normal() == expected) { checked = expected / relative; break; }
  }
#endif
  for (auto current = checked; !current.empty(); current = current.parent_path()) {
    std::error_code ec;
    const auto status = fs::symlink_status(current, ec);
    require(!ec && !fs::is_symlink(status), "Workspace payload paths cannot contain symbolic links");
    if (current == current.root_path()) { break; }
  }
  require(path.extension() == ".stkp" && fs::is_regular_file(checked), "Workspace Viewer payload is missing or invalid");
}
Json workspace_origin(Json state)
{
  // These are read-only bridge metadata caches, populated independently of any
  // desktop edit. Keep them in the portable snapshot, but do not interpret their
  // arrival as a user's change while importing another workspace.
  auto &viewer = state.at("app").at("viewer");
  viewer.erase("presets");
  viewer.erase("catalog");
  viewer.erase("colormaps");
  return state;
}
void replace_area_state(nlohmann::json &node, const wm::Screen &screen)
{
  if (node.contains("area")) {
    auto &area = node.at("area");
    const auto *live = dynamic_cast<const EditorArea *>(screen.find_area(area.at("id").get<std::string>()));
    require(live != nullptr, "Workspace contains an unsupported area");
    area["state"] = live->save_workspace_state();
  }
  else {
    for (auto &child : node.at("children")) { replace_area_state(child, screen); }
  }
}
void require_workspace_editors(const nlohmann::json &root)
{
  std::vector<std::pair<const nlohmann::json *, int>> pending{{&root, 0}};
  size_t nodes = 0;
  while (!pending.empty()) {
    const auto [node, depth] = pending.back(); pending.pop_back();
    // The ordinary Screen parser permits at most 64 leaves and depth 16. Bound
    // this marker preflight too, before constructing any temporary editors.
    require(++nodes <= 127 && depth <= 16 && node->is_object(), "Invalid workspace editor tree");
    if (node->contains("area")) {
      const auto &area = node->at("area");
      require(area.is_object() && area.contains("state") && area.at("state").is_object() &&
              area.at("state").contains("workspace") && area.at("state").at("workspace").is_boolean() &&
              area.at("state").at("workspace").get<bool>(),
              "Desktop workspace requires complete editor state with its workspace marker");
    }
    else {
      require(node->contains("children") && node->at("children").is_array() && node->at("children").size() <= 32,
              "Invalid workspace editor tree");
      for (const auto &child : node->at("children")) { pending.emplace_back(&child, depth + 1); }
    }
  }
}
void check_snapshot(const std::optional<bridge::ProjectInfo> &project, const Json &snapshot,
                    const std::string &table, const std::string &record)
{
  if (!project) {
    require(table.empty() && record.empty(), "A workspace without a project cannot select a table record");
    return;
  }
  require(!project->handle.empty() && snapshot.is_object() && snapshot.contains("project") &&
      io::get_string(snapshot.at("project"), "id") == project->id &&
      io::get_int(snapshot.at("project"), "revision", -1) == project->revision &&
      snapshot.contains("tables") && snapshot.at("tables").is_array(), "Workspace project snapshot is inconsistent");
  bool found_table = table.empty(), found_record = record.empty();
  for (const auto &raw : snapshot.at("tables")) {
    const auto parsed = ProjectTable::from_json(raw);
    if (parsed.id == table) {
      found_table = true;
      for (const auto &row : parsed.records) { if (row.id == record) { found_record = true; } }
    }
  }
  require(found_table && found_record, "Workspace selected table or record is missing");
}
struct Staging {
  fs::path directory;
  Staging()
  {
    std::random_device random;
    for (int attempt = 0; attempt < 16; attempt++) {
      const auto name = "stk-workspace-" + std::to_string(random()) + "-" + std::to_string(random());
      // The OS temp directory on macOS may use the trusted /var alias. Resolve
      // this application-owned parent before creating a new private directory;
      // resource files themselves still pass strict no-symlink checks.
      directory = fs::canonical(fs::temp_directory_path()) / name;
      if (fs::create_directory(directory)) {
        fs::permissions(directory, fs::perms::owner_all, fs::perm_options::replace);
        return;
      }
    }
    throw std::runtime_error("Cannot create private workspace staging directory");
  }
  ~Staging() { std::error_code ec; fs::remove_all(directory, ec); }
};
}  // namespace

struct AppShell::WorkspacePrepared {
  Json state;
  std::vector<wm::LayoutFile> layouts;
  std::vector<std::unique_ptr<wm::Screen>> trees;
  std::shared_ptr<const io::Payload> payload;
  std::string table, record;
  bool adopt_project = false;
  std::optional<bridge::ProjectInfo> project;
  Json snapshot;
};

WorkspaceTransfer &AppShell::workspace_transfer()
{
  if (!workspace_transfer_) { workspace_transfer_ = std::make_unique<WorkspaceTransfer>(*this); }
  return *workspace_transfer_;
}

Json AppShell::capture_workspace() const
{
  Json windows = Json::array();
  require(!screens_.empty() && screens_.size() <= 16, "Workspace needs 1 to 16 installed windows");
  for (const auto *screen : screens_) {
    const wm::Window *window = nullptr;
    if (wm_) {
      for (const auto &candidate : wm_->windows()) {
        if (&candidate->screen() == screen) { window = candidate.get(); break; }
      }
    }
    auto layout = capture_layout(*screen, window);
    replace_area_state(layout.screen.at("root"), *screen);
    windows.push_back(Json(wm::layout_to_json(layout)));
  }
  // Controller accessors materialize CPU-only empty states when this shell has not drawn yet.
  auto &store = const_cast<AppStore &>(store_);
  Json result = {{"format", "stk.desktop.workspace-state"}, {"version", 1}, {"windows", windows},
      {"app", {{"project_selection", {{"table_id", store.project().table_id()}, {"record_id", store.project().record_id()}}},
                {"viewer", store.viewer().save_workspace_state()}}}};
  require(result.dump().size() <= 8 * 1024 * 1024, "Workspace editor state exceeds 8 MiB");
  return result;
}

std::shared_ptr<AppShell::WorkspacePrepared> AppShell::prepare_workspace(const Json &state, std::string *error)
{
  try {
    require(!store_.has_open_result(), "A Viewer source is waiting to open; restore was not applied");
    keys(state, {"format", "version", "windows", "app"});
    require(io::get_string(state, "format") == "stk.desktop.workspace-state" && state.at("version").is_number_integer() &&
            state.at("version") == 1 && state.at("windows").is_array() && !state.at("windows").empty() &&
            state.at("windows").size() <= 16 && state.dump().size() <= 8 * 1024 * 1024,
            "Unsupported or oversized desktop workspace state");
    const auto &app = state.at("app");
    keys(app, {"project_selection", "viewer"}, {"viewer_payload_path"});
    keys(app.at("project_selection"), {"table_id", "record_id"});
    auto prepared = std::make_shared<WorkspacePrepared>();
    prepared->state = state;
    prepared->table = text(app.at("project_selection").at("table_id"));
    prepared->record = text(app.at("project_selection").at("record_id"));
    if (app.contains("viewer_payload_path")) {
      const auto path = core::path_from_utf8(text(app.at("viewer_payload_path")));
      safe_file(path);
      prepared->payload = std::make_shared<const io::Payload>(io::read_stkp(path));
    }
    AppStore temporary_store;
    if (error) { error->clear(); }
    require_loaded(temporary_store.viewer().load_workspace_state(app.at("viewer"), prepared->payload, error), error,
                   "Invalid workspace Viewer settings");
    for (const auto &raw : state.at("windows")) {
      wm::LayoutFile layout;
      if (error) { error->clear(); }
      require_loaded(wm::layout_from_json(nlohmann::json(raw), layout, error), error, "Invalid workspace window layout");
      require(layout.screen.contains("root"), "Missing workspace editor tree");
      require_workspace_editors(layout.screen.at("root"));
      const auto languages = store_.catalog().languages();
      require(std::find(languages.begin(), languages.end(), layout.language) != languages.end(),
              "Workspace requests an unavailable language");
      if (!prepared->layouts.empty()) {
        require(layout.language == prepared->layouts.front().language && layout.ui_scale == prepared->layouts.front().ui_scale,
                "Workspace window language and UI scale must agree");
      }
      auto tree = std::make_unique<wm::Screen>();
      tree->set_area_factory([this](const std::string &kind) -> std::unique_ptr<wm::Area> {
        if (!registry_.find(kind)) { return nullptr; }
        return std::make_unique<EditorArea>(*this, kind);
      });
      if (error) { error->clear(); }
      require_loaded(tree->from_json(layout.screen, error), error, "Invalid workspace editor tree");
      prepared->layouts.push_back(std::move(layout));
      prepared->trees.push_back(std::move(tree));
    }
    return prepared;
  }
  catch (const std::exception &e) {
    if (error) { *error = e.what(); }
    return {};
  }
}

bool AppShell::commit_workspace(const std::shared_ptr<WorkspacePrepared> &prepared, std::string *error)
{
  std::vector<wm::Window *> created;
  const auto cleanup = [&]() {
    if (!wm_) { return; }
    for (auto *window : created) { wm_->close_window(window); }
    created.clear();
  };
  try {
    require(prepared && !text_input_active() && !has_unsaved_changes() && !store_.project().busy() && !store_.scripts().busy() &&
            !store_.has_open_result(),
            "Current work changed or has unsaved drafts; restore was not applied");
    if (prepared->adopt_project) { check_snapshot(prepared->project, prepared->snapshot, prepared->table, prepared->record); }
    else {
      const auto &project = store_.project();
      if (!prepared->table.empty()) {
        const auto table = std::find_if(project.tables().begin(), project.tables().end(), [&](const auto &t) { return t.id == prepared->table; });
        require(table != project.tables().end(), "Workspace selected table does not belong to the current project");
        if (!prepared->record.empty()) {
          require(std::any_of(table->records.begin(), table->records.end(), [&](const auto &r) { return r.id == prepared->record; }),
                  "Workspace selected record does not belong to the current table");
        }
      }
      else { require(prepared->record.empty(), "Workspace selected record needs its table"); }
    }
    if (wm_) {
      for (const auto &layout : prepared->layouts) {
        wm::WindowOptions options;
        options.width = layout.window.width > 0 ? layout.window.width : kDefaultWindowWidth;
        options.height = layout.window.height > 0 ? layout.window.height : kDefaultWindowHeight;
        options.x = layout.window.has_position ? layout.window.x : 0;
        options.y = layout.window.has_position ? layout.window.y : 0;
        options.maximized = layout.window.maximized;
        std::string why;
        auto *window = wm_->open_window(options, why);
        require(window != nullptr, "Cannot create all restored native windows");
        created.push_back(window);
      }
    }
    else {
      workspace_screens_.reserve(workspace_screens_.size() + prepared->trees.size());
      screens_.reserve(std::max(screens_.size(), prepared->trees.size()));
    }
    require(!store_.has_open_result(), "A Viewer source is waiting to open; restore was not applied");
    if (prepared->adopt_project) {
      if (!store_.project().adopt_workspace_project(prepared->project, prepared->snapshot,
            prepared->table, prepared->record, error)) { cleanup(); return false; }
    }
    else if (store_.project().project()) {
      const auto &project = *store_.project().project();
      if (!prepared->record.empty()) {
        const auto selected = store_.project().request_select(project.handle, project.revision, prepared->table, prepared->record);
        if (!selected) { cleanup(); if (error) { *error = selected.error().message; } return false; }
      }
      else {
        // The explicit scripting select API requires a record UUID. Empty projects
        // and empty tables have a legitimate empty record selection.
        store_.project().select_table(prepared->table);
        store_.project().select_record({});
      }
    }
    // Viewer input has already passed identical CPU validation. No source files are opened,
    // evaluations scheduled or programs submitted by this adoption.
    if (error) { error->clear(); }
    require_loaded(store_.viewer().load_workspace_state(prepared->state.at("app").at("viewer"), prepared->payload, error), error,
                   "Cannot adopt verified workspace Viewer settings");
    const auto previous = screens_;
    if (wm_) {
      for (size_t i = 0; i < created.size(); i++) {
        install(created[i]->screen(), created[i]);
        created[i]->screen().adopt_tree_from(*prepared->trees[i]);
      }
      for (auto *screen : previous) { forget(*screen); }
      std::vector<wm::Window *> obsolete;
      for (const auto &candidate : wm_->windows()) {
        if (std::find(previous.begin(), previous.end(), &candidate->screen()) != previous.end()) { obsolete.push_back(candidate.get()); }
      }
      auto *manager = wm_;
      const auto weak = lifetime();
      manager->post([manager, weak, obsolete = std::move(obsolete)] {
        if (weak.expired()) { return; }
        for (auto *window : obsolete) {
          const auto &all = manager->windows();
          if (std::any_of(all.begin(), all.end(), [window](const auto &item) { return item.get() == window; })) {
            manager->close_window(window);
          }
        }
      });
      created.clear();
    }
    else {
      for (size_t i = 0; i < prepared->trees.size(); i++) {
        if (i < previous.size()) { previous[i]->adopt_tree_from(*prepared->trees[i]); }
        else {
          auto screen = std::move(prepared->trees[i]);
          install(*screen, nullptr);
          workspace_screens_.push_back(std::move(screen));
        }
      }
      for (size_t i = prepared->trees.size(); i < previous.size(); i++) { forget(*previous[i]); previous[i]->clear(); }
      std::erase_if(workspace_screens_, [this](const auto &screen) { return !has_screen(screen.get()); });
    }
    set_language(prepared->layouts.front().language);
    set_ui_scale(prepared->layouts.front().ui_scale);
    store_.changed();
    if (error) { error->clear(); }
    return true;
  }
  catch (const std::exception &e) {
    cleanup();
    if (error) { *error = e.what(); }
    return false;
  }
}

bool AppShell::apply_workspace(const Json &state, std::string *error)
{
  if (workspace_busy_ || text_input_active() || has_unsaved_changes() || store_.project().busy() || store_.scripts().busy() || store_.has_open_result()) {
    if (error) { *error = "Current work has active input, pending operations or unsaved drafts"; }
    return false;
  }
  const auto prepared = prepare_workspace(state, error);
  return prepared && commit_workspace(prepared, error);
}

bool AppShell::export_workspace(const std::string &path, ScriptState::Completion complete)
{
  auto *client = store_.bridge();
  if (workspace_busy_ || text_input_active() || store_.project().busy() || store_.has_open_result() || !client || workspace_session(client).empty()) { return false; }
  const auto hello = client->hello_info();
  if (!hello || !hello->has_method("workspace.export")) { return false; }
  try {
    auto state = capture_workspace();
    auto staging = std::make_shared<Staging>();
    Json resources = Json::array();
    std::vector<std::pair<fs::path, bool>> included;
    const auto inside = [](const fs::path &candidate, const fs::path &parent) {
      const auto relative = candidate.lexically_normal().lexically_relative(parent.lexically_normal());
      return !relative.empty() && !relative.is_absolute() && *relative.begin() != "..";
    };
    const auto inside_project = [&](const fs::path &local) {
      const auto &project = store_.project().project();
      return project && inside(local, core::path_from_utf8(project->directory));
    };
    if (const auto payload = store_.viewer().base_payload()) {
      std::map<std::string, core::SharedBytes> buffers;
      for (const auto &buffer : payload->buffers) { buffers.emplace(buffer.sha256, buffer.bytes); }
      const auto packed = io::pack_stkp(payload->manifest, buffers);
      const auto temporary = staging->directory / "viewer.stkp";
      core::write_file_atomic(temporary, packed);
      const auto temporary_text = core::path_to_utf8(temporary);
      state["app"]["viewer_payload_path"] = temporary_text;
      resources.push_back({{"id", "viewer-payload"}, {"path", temporary_text}});
      included.emplace_back(temporary.lexically_normal(), false);
    }
    const auto &source = store_.viewer().source();
    if (!source.path.empty()) {
      const auto local = core::path_from_utf8(source.path);
      std::error_code ec;
      if (local.is_absolute() && fs::exists(local, ec) && !inside_project(local)) {
        resources.push_back({{"id", "viewer-source"}, {"path", source.path}});
        included.emplace_back(local.lexically_normal(), fs::is_directory(local, ec));
      }
    }
    size_t editor_file = 0;
    for (const auto *screen : screens_) {
      for (const auto *base : screen->areas()) {
        const auto *area = dynamic_cast<const EditorArea *>(base);
        if (!area) { continue; }
        for (int i = 0; i < area->tab_count(); i++) {
          for (const auto &declared : area->tab(i).workspace_resource_paths()) {
            const auto path = text(Json(declared));
            const auto local = core::path_from_utf8(path);
            require(local.is_absolute(), "Editor workspace resources must use absolute local paths");
            if (inside_project(local)) { continue; }
            const auto normalized = local.lexically_normal();
            const bool covered = std::any_of(included.begin(), included.end(), [&](const auto &resource) {
              return normalized == resource.first || (resource.second && inside(normalized, resource.first));
            });
            if (covered) { continue; }
            resources.push_back({{"id", "editor-file-" + std::to_string(editor_file++)}, {"path", path}});
            // Missing explicitly opened resources still reach the backend, so the
            // archive reports the missing dependency rather than silently omitting it.
            included.emplace_back(normalized, false);
          }
        }
      }
    }
    Json params = {{"path", path}, {"state", state}, {"resources", resources}};
    if (store_.project().project()) {
      params["handle"] = store_.project().project()->handle;
      params["expected_revision"] = store_.project().project()->revision;
    }
    bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never; options.timeout_s = 3600;
    workspace_busy_ = true;
    const auto weak = lifetime();
    const auto session = workspace_session(client);
    client->call("workspace.export", std::move(params), options).then(
      [this, weak, client, session, staging, complete = std::move(complete)](bridge::Result<Json> result) mutable {
        if (weak.expired()) { return; }
        workspace_busy_ = false;
        if (store_.bridge() != client || workspace_session(client) != session) {
          if (complete) { complete(workspace_error("The bridge changed during workspace export; the request was not replayed")); }
        }
        else if (complete) { complete(std::move(result)); }
        store_.changed();
      });
    store_.changed();
    return true;
  }
  catch (const std::exception &e) {
    if (complete) { complete(workspace_error(e.what(), ErrorCode::InvalidParams)); }
    return true;
  }
}

bool AppShell::import_workspace(const std::string &source, const std::string &destination,
                                 const std::string &expected_sha256, ScriptState::Completion complete,
                                 const bool allow_incomplete)
{
  Json params = {{"path", source}, {"destination", destination}};
  if (!expected_sha256.empty()) { params["expected_sha256"] = expected_sha256; }
  return receive_workspace("workspace.import", std::move(params), std::move(complete), allow_incomplete);
}

bool AppShell::open_workspace(const std::string &directory, ScriptState::Completion complete, const bool allow_incomplete)
{
  return receive_workspace("workspace.open", {{"directory", directory}}, std::move(complete), allow_incomplete);
}

bool AppShell::receive_workspace(const std::string &method, Json params, ScriptState::Completion complete,
                                  const bool allow_incomplete)
{
  auto *client = store_.bridge();
  if (workspace_busy_ || text_input_active() || has_unsaved_changes() || store_.project().busy() || store_.scripts().busy() ||
      store_.has_open_result() || !client || workspace_session(client).empty()) { return false; }
  const auto hello = client->hello_info();
  if (!hello || !hello->has_method(method)) { return false; }
  Json original;
  try { original = workspace_origin(capture_workspace()); }
  catch (const std::exception &) { return false; }
  const auto weak = lifetime();
  const auto session = workspace_session(client);
  const auto &visible = store_.project().project();
  const auto handle = visible ? visible->handle : std::string();
  const auto revision = visible ? visible->revision : -1;
  const auto payload = store_.viewer().base_payload();
  const auto payload_serial = store_.viewer().payload_serial();
  const auto camera_serial = store_.viewer().camera_serial();
  const auto current = [this, weak, client, session, handle, revision, original, payload, payload_serial,
                        camera_serial](std::string *reason = nullptr) {
    if (weak.expired() || store_.bridge() != client || workspace_session(client) != session || text_input_active() ||
        has_unsaved_changes() || store_.project().busy() || store_.scripts().busy() || store_.has_open_result()) {
      if (reason) { *reason = "bridge session, active input, drafts or pending operations"; }
      return false;
    }
    const auto &project = store_.project().project();
    if ((project ? project->handle : std::string()) != handle || (project ? project->revision : -1) != revision) {
      if (reason) { *reason = "project handle or revision"; }
      return false;
    }
    const auto &viewer = store_.viewer();
    if (viewer.base_payload() != payload || viewer.payload_serial() != payload_serial || viewer.camera_serial() != camera_serial) {
      if (reason) { *reason = "Viewer payload or camera source"; }
      return false;
    }
    try {
      const auto captured = workspace_origin(capture_workspace());
      if (captured == original) { return true; }
      if (reason) {
        // Report only the structural location. Never put draft contents, paths,
        // project values or other serialized workspace data in diagnostics.
        const auto changes = Json::diff(original, captured);
        *reason = "workspace settings";
        if (!changes.empty()) { *reason += " at " + io::get_string(changes.front(), "path"); }
      }
      return false;
    }
    catch (const std::exception &) { return false; }
  };
  const auto finish = [this, weak, complete = std::move(complete)](bridge::Result<Json> result) {
    if (weak.expired()) { return; }
    workspace_busy_ = false;
    if (complete) { complete(std::move(result)); }
    store_.changed();
  };
  bridge::CallOptions options; options.retry = bridge::CallOptions::Retry::Never; options.timeout_s = 3600;
  workspace_busy_ = true;
  client->call(method, std::move(params), options).then(
    [this, weak, client, session, options, current, finish, allow_incomplete](bridge::Result<Json> response) mutable {
      if (weak.expired()) { return; }
      if (!response) { finish(response.error()); return; }
      std::string changed;
      if (!current(&changed)) { finish(workspace_error("Workspace target changed while reading (" + changed + "); the current desktop was preserved")); return; }
      const Json result = response.value();
      if (!io::get_bool(result, "complete", false) && !allow_incomplete) {
        finish(workspace_error("Workspace has missing dependencies; explicitly accept its diagnostics before restoring")); return;
      }
      std::string error;
      std::shared_ptr<WorkspacePrepared> prepared;
      try {
        const auto &state = result.at("state");
        const auto &app = state.at("app");
        if (app.contains("viewer_payload_path")) {
          const auto payload_path = core::path_from_utf8(text(app.at("viewer_payload_path"))).lexically_normal();
          const auto directory = core::path_from_utf8(text(result.at("directory"))).lexically_normal();
          const auto relative = payload_path.lexically_relative(directory);
          require(!relative.empty() && !relative.is_absolute() && *relative.begin() != "..",
                  "Restored Viewer payload must belong to the imported workspace");
        }
        prepared = prepare_workspace(state, &error);
      }
      catch (const std::exception &e) { error = e.what(); }
      if (!prepared) { finish(workspace_error(error, ErrorCode::InvalidParams)); return; }
      prepared->adopt_project = true;
      const auto adopt = [this, weak, client, session, current, finish, result, prepared]() {
        if (weak.expired()) { return; }
        std::string changed;
        if (!current(&changed)) {
          if (prepared->project && store_.bridge() == client && workspace_session(client) == session) { client->project_close(prepared->project->handle); }
          finish(workspace_error("Workspace target changed while preparing (" + changed + "); the current desktop was preserved")); return;
        }
        std::string error;
        if (!commit_workspace(prepared, &error)) {
          if (prepared->project && store_.bridge() == client && workspace_session(client) == session &&
              (!store_.project().project() || store_.project().project()->handle != prepared->project->handle)) {
            client->project_close(prepared->project->handle);
          }
          finish(workspace_error(error)); return;
        }
        finish(result);
      };
      const auto schedule_adopt = [this, weak, adopt, finish]() {
        if (weak.expired()) { return; }
        if (wm_) {
          if (!wm_->post(adopt)) { finish(workspace_error("Cannot queue workspace adoption")); }
        }
        else if (!screens_.empty()) { screens_.front()->defer(adopt); screens_.front()->tag_redraw(); }
        else { finish(workspace_error("The workspace target window was closed")); }
      };
      const auto directory = result.find("project_directory");
      if (directory == result.end() || directory->is_null()) { schedule_adopt(); return; }
      Json open = {{"directory", text(*directory)}};
      if (result.contains("project") && result.at("project").is_object()) {
        open["expected_id"] = io::get_string(result.at("project"), "id");
      }
      client->call("project.open", std::move(open), options).then(
        [this, weak, client, session, options, current, finish, prepared, schedule_adopt](bridge::Result<Json> opened) mutable {
          if (weak.expired()) { return; }
          if (!opened) { finish(opened.error()); return; }
          try { prepared->project = bridge::ProjectInfo::from_json(opened.value().at("project")); }
          catch (const std::exception &) { finish(workspace_error("Invalid workspace project-open response")); return; }
          std::string changed;
          if (!current(&changed)) {
            if (store_.bridge() == client && workspace_session(client) == session) { client->project_close(prepared->project->handle); }
            finish(workspace_error("Workspace target changed while opening its project (" + changed + ")")); return;
          }
          client->call("project.snapshot", {{"handle", prepared->project->handle}}, options).then(
            [this, weak, client, session, finish, prepared, schedule_adopt](bridge::Result<Json> snapshot) mutable {
              if (weak.expired()) { return; }
              if (!snapshot) {
                if (store_.bridge() == client && workspace_session(client) == session) { client->project_close(prepared->project->handle); }
                finish(snapshot.error()); return;
              }
              try { prepared->snapshot = snapshot.value().at("snapshot"); }
              catch (const std::exception &) {
                if (store_.bridge() == client && workspace_session(client) == session) { client->project_close(prepared->project->handle); }
                finish(workspace_error("Invalid workspace project snapshot response")); return;
              }
              schedule_adopt();
            });
        });
    });
  store_.changed();
  return true;
}

}  // namespace stk::app
