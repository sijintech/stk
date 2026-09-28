/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_state.hh"

#include <algorithm>
#include <limits>

#include "stk/app/app_store.hh"
#include "stk/app/viewer_state.hh"
#include "stk/platform/file_dialog.hh"

namespace stk::app {

using io::Json;

ProjectTable ProjectTable::from_json(const Json &value)
{
  ProjectTable table;
  table.id = io::get_string(value, "id");
  table.name = io::get_string(value, "name");
  for (const auto &field : value.at("fields")) {
    table.fields.push_back({io::get_string(field, "id"), io::get_string(field, "name"),
                            io::get_string(field, "type"), io::get_string(field, "unit")});
  }
  for (const auto &record : value.at("records")) {
    table.records.push_back({io::get_string(record, "id"), record.at("values"),
                             record.value("definitions", Json::object()), record.value("evaluations", Json::object())});
  }
  return table;
}

const Json *ProjectTable::cell(const int row, const int column) const
{
  if (row < 0 || column < 0 || size_t(row) >= records.size() || size_t(column) >= fields.size()) {
    return nullptr;
  }
  const auto &values = records[row].values;
  const auto it = values.find(fields[column].id);
  return it == values.end() ? nullptr : &*it;
}

std::string ProjectTable::text(const int row, const int column) const
{
  if (const Json *result = evaluation(row, column); result && io::get_string(*result, "state") == "error") {
    return "#" + io::get_string(result->at("error"), "code");
  }
  const Json *value = cell(row, column);
  const std::string text = !value ? std::string() : value->is_string() ? value->get<std::string>() : value->dump();
  return definition(row, column) ? "= " + text : text;
}

int ProjectTable::compare(const int row_a, const int row_b, const int column) const
{
  if (column < 0 || size_t(column) >= fields.size()) { return 0; }
  if (fields[column].type == "integer" || fields[column].type == "number") {
    const auto *a = cell(row_a, column), *b = cell(row_b, column);
    auto valid = [&](const Json *value, int row) {
      const auto *computed = evaluation(row, column);
      return value && value->is_number() && !(computed && io::get_string(*computed, "state") == "error");
    };
    const bool a_valid = valid(a, row_a), b_valid = valid(b, row_b);
    if (!a_valid || !b_valid) { return int(b_valid) - int(a_valid); }
    // JSON compares integer pairs without conversion to double, preserving the full int64 range.
    return int(*a > *b) - int(*a < *b);
  }
  const auto a = text(row_a, column), b = text(row_b, column);
  return int(a > b) - int(a < b);
}

const Json *ProjectTable::definition(const int row, const int column) const
{
  if (row < 0 || column < 0 || size_t(row) >= records.size() || size_t(column) >= fields.size()) {
    return nullptr;
  }
  const auto it = records[row].definitions.find(fields[column].id);
  return it == records[row].definitions.end() ? nullptr : &*it;
}

const Json *ProjectTable::evaluation(const int row, const int column) const
{
  if (row < 0 || column < 0 || size_t(row) >= records.size() || size_t(column) >= fields.size()) {
    return nullptr;
  }
  const auto it = records[row].evaluations.find(fields[column].id);
  return it == records[row].evaluations.end() ? nullptr : &*it;
}

std::optional<Json> project_literal(const std::string_view type, const std::string_view text, std::string &error_key)
{
  error_key.clear();
  if (type == "text") {
    return Json(std::string(text));
  }
  try {
    Json value = io::parse_json(text);
    bool valid = false;
    if (type == "json") {
      valid = true;
    }
    else if (type == "boolean") {
      valid = value.is_null() || value.is_boolean();
    }
    else if (type == "number") {
      valid = value.is_null() || io::is_finite_number(value);
    }
    else if (type == "integer") {
      valid = value.is_null() || (value.is_number_integer() &&
              (!value.is_number_unsigned() || value.get<uint64_t>() <= uint64_t(std::numeric_limits<int64_t>::max())));
    }
    if (valid) {
      return value;
    }
  }
  catch (const std::exception &) {
  }
  error_key = "project.error.literal";
  return std::nullopt;
}

ProjectState::ProjectState(AppStore &store) : store_(store)
{
  open_external = platform::open_with_system;
  open_vscode = platform::open_with_vscode;
}

ProjectState::~ProjectState()
{
  alive_.reset();
  state_listener_.reset();
  changed_listener_.reset();
  closed_listener_.reset();
  runs_listener_.reset();
}

template<class T, class F> void ProjectState::on(bridge::Future<T> future, F fn)
{
  std::weak_ptr<bool> weak = alive_;
  const uint64_t epoch = epoch_;
  future.then([this, weak, epoch, fn = std::move(fn)](bridge::Result<T> result) mutable {
    if (weak.lock() && epoch == epoch_) {
      fn(result);
    }
  });
}

void ProjectState::changed()
{
  ++version_;
  store_.changed();
}

void ProjectState::fail(const bridge::Error &error)
{
  error_ = error.message;
  store_.log(error_);
  changed();
}

bool ProjectState::ready() const
{
  if (!client_ || bridge_state_ != bridge::BridgeState::Ready) {
    return false;
  }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.apply");
}

void ProjectState::sync()
{
  if (client_ != store_.bridge()) {
    attach(store_.bridge());
  }
  if (runs_loaded_ && runs_dirty_ && ready() && loaded() && !busy()) {
    load_runs(runs_offset_);
  }
}

void ProjectState::attach(bridge::Client *client)
{
  if (client == client_) {
    return;
  }
  state_listener_.reset();
  changed_listener_.reset();
  closed_listener_.reset();
  runs_listener_.reset();
  ++epoch_;
  clear_review();
  ++recent_epoch_;
  recent_loaded_ = recent_loading_ = recent_dirty_ = false;
  recent_.clear();
  recent_error_.clear();
  busy_ = fetching_ = snapshot_ready_ = false;
  if (project_) {
    project_->handle.clear();
  }
  client_ = client;
  bridge_state_ = bridge::BridgeState::Stopped;
  if (!client_) {
    changed();
    return;
  }
  std::weak_ptr<bool> weak = alive_;
  state_listener_ = client_->on_state([this, weak](bridge::BridgeState state, const auto &) {
    if (weak.lock()) {
      on_state(state);
    }
  });
  changed_listener_ = client_->on_event("project.changed", [this, weak](const auto &, const Json &data) {
    if (weak.lock() && project_ && io::get_string(data, "handle") == project_->handle) {
      dirty_revision_ = std::max(dirty_revision_, io::get_int(data, "revision", -1));
      if (dirty_revision_ > project_->revision) {
        refresh();
      }
    }
  });
  closed_listener_ = client_->on_event("project.closed", [this, weak](const auto &, const Json &data) {
    if (weak.lock() && project_ && io::get_string(data, "handle") == project_->handle) {
      ++epoch_;
      clear();
      changed();
    }
  });
  runs_listener_ = client_->on_event("project.runs.changed", [this, weak](const auto &, const Json &data) {
    if (weak.lock() && project_ && io::get_string(data, "handle") == project_->handle) {
      runs_dirty_ = true;
      changed();
    }
  });
  on_state(client_->state());
}

void ProjectState::on_state(const bridge::BridgeState state)
{
  if (state == bridge_state_) {
    return;
  }
  bridge_state_ = state;
  if (state != bridge::BridgeState::Ready) {
    ++epoch_;
    clear_review();
    ++recent_epoch_;
    recent_loaded_ = recent_loading_ = recent_dirty_ = false;
    recent_.clear();
    recent_error_.clear();
    busy_ = fetching_ = snapshot_ready_ = false;
    if (project_) {
      project_->handle.clear();
    }
  }
  else if (project_ && ready()) {
    start_open(project_->directory, {}, false, project_->id);
  }
  changed();
}

void ProjectState::load_recent()
{
  if (!ready()) { return; }
  const auto hello = client_->hello_info();
  if (!hello || !hello->has_method("project.recent")) { recent_loaded_ = true; return; }
  if (recent_loading_) { recent_dirty_ = true; return; }
  recent_loading_ = true;
  recent_dirty_ = false;
  const auto generation = recent_epoch_;
  std::weak_ptr<bool> weak = alive_;
  client_->call("project.recent").then([this, weak, generation](const bridge::Result<Json> &result) {
    if (!weak.lock() || generation != recent_epoch_) { return; }
    recent_loading_ = false;
    recent_loaded_ = true;
    if (result.ok()) {
      recent_ = result.value().at("projects");
      recent_error_ = io::get_string(result.value(), "warning");
    }
    else { recent_error_ = result.error().describe(); }
    changed();
    if (recent_dirty_) { load_recent(); }
  });
  changed();
}

bool ProjectState::forget_recent(const std::string &directory)
{
  if (!ready() || recent_loading_) { return false; }
  recent_loading_ = true;
  const auto generation = recent_epoch_;
  std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  client_->call("project.forget", {{"directory", directory}}, options).then(
      [this, weak, generation](const bridge::Result<Json> &result) {
    if (!weak.lock() || generation != recent_epoch_) { return; }
    recent_loading_ = false;
    if (!result.ok()) { recent_error_ = result.error().describe(); changed(); return; }
    load_recent();
  });
  changed();
  return true;
}

bool ProjectState::open_recent(const Json &entry)
{
  return start_open(io::get_string(entry, "directory"), {}, false, io::get_string(entry, "id"));
}

bool ProjectState::create(const std::string &directory, const std::string &name)
{
  return start_open(directory, name, true);
}

bool ProjectState::open(const std::string &directory,
                         std::function<void(bridge::Result<bridge::ProjectInfo>)> complete)
{
  return start_open(directory, {}, false, {}, std::move(complete));
}

bool ProjectState::start_open(const std::string &directory, const std::string &name, const bool create,
                              std::string expected_id,
                              std::function<void(bridge::Result<bridge::ProjectInfo>)> complete)
{
  if (!ready() || busy()) {
    return false;
  }
  ++epoch_;
  busy_ = true;
  clear_review();
  error_.clear();
  notice_.clear();
  const auto hello = client_->hello_info();
  const std::string guard = hello && hello->has_method("project.recent") ? expected_id : std::string();
  on(create ? client_->project_create(directory, name) : client_->project_open(directory, guard),
     [this, expected_id = std::move(expected_id), complete = std::move(complete)](const bridge::Result<bridge::ProjectInfo> &result) {
       busy_ = false;
       if (!result.ok()) {
         fail(result.error());
         if (complete) { complete(result.error()); }
         return;
       }
       if (!expected_id.empty() && result.value().id != expected_id) {
         client_->project_close(result.value().handle);
         error_ = std::string(store_.tr("project.error.replaced"));
         changed();
         if (complete) { complete(bridge::Error::make(bridge::ErrorCode::Conflict, error_)); }
         return;
       }
       const bool same = project_ && project_->id == result.value().id;
       if (project_ && !project_->handle.empty() && project_->handle != result.value().handle) {
         client_->project_close(project_->handle);
       }
       project_ = result.value();
       snapshot_ready_ = false;
       dirty_revision_ = project_->revision;
       if (!same) {
         tables_.clear();
         clear_runs();
         input_snapshots_ = Json::array();
         input_verification_ = Json::object();
         table_id_.clear();
         record_id_.clear();
       }
       refresh();
       load_recent();
       if (complete) { complete(*project_); }
     });
  changed();
  return true;
}

void ProjectState::clear()
{
  clear_review();
  notice_.clear();
  project_.reset();
  clear_runs();
  tables_.clear();
  file_index_ = Json::object();
  input_snapshots_ = Json::array();
  input_verification_ = Json::object();
  table_id_.clear();
  record_id_.clear();
  busy_ = fetching_ = snapshot_ready_ = false;
  dirty_revision_ = -1;
  undo_revision_ = redo_revision_ = -1;
}

bool ProjectState::close(std::function<void(bridge::Result<bool>)> complete)
{
  if (busy() || !project_) {
    return false;
  }
  if (!ready() || project_->handle.empty()) {
    ++epoch_;
    clear();
    error_.clear();
    changed();
    if (complete) { complete(true); }
    return true;
  }
  busy_ = true;
  on(client_->project_close(project_->handle), [this, complete = std::move(complete)](const bridge::Result<bool> &result) {
    busy_ = false;
    if (!result.ok()) {
      fail(result.error());
      if (complete) { complete(result.error()); }
      return;
    }
    ++epoch_;
    clear();
    error_.clear();
    changed();
    if (complete) { complete(result.value()); }
  });
  changed();
  return true;
}

void ProjectState::refresh()
{
  if (!ready() || busy() || !project_ || project_->handle.empty()) {
    return;
  }
  fetching_ = true;
  on(client_->project_snapshot(project_->handle), [this](const bridge::Result<Json> &result) {
    fetching_ = false;
    if (!result.ok()) {
      snapshot_ready_ = false;
      fail(result.error());
      return;
    }
    std::vector<ProjectTable> tables;
    for (const auto &value : result.value().at("tables")) {
      tables.push_back(ProjectTable::from_json(value));
    }
    tables_ = std::move(tables);
    file_index_ = result.value().value("file_index", Json::object());
    project_->revision = io::get_int(result.value().at("project"), "revision", 0);
    project_->format_version = int(io::get_int(result.value(), "format_version", 1));
    const auto &history = result.value().value("edit_history", Json::object());
    undo_revision_ = io::get_int(history, "undo_revision", -1);
    redo_revision_ = io::get_int(history, "redo_revision", -1);
    snapshot_ready_ = true;
    runs_dirty_ = true;
    validate_selection();
    changed();
    if (dirty_revision_ > project_->revision) {
      refresh();
    }
  });
  changed();
}

bool ProjectState::apply(Json commands, const std::optional<int64_t> expected_revision)
{
  if (!ready() || busy() || !loaded() || project_->handle.empty()) {
    return false;
  }
  busy_ = true;
  error_.clear();
  notice_.clear();
  on(client_->project_apply(project_->handle, expected_revision.value_or(project_->revision), commands), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result.ok()) {
      fail(result.error());
      /* Refresh a conflicting snapshot, preserving the error for review. Never replay edits. */
      refresh();
      return;
    }
    dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    refresh();
  });
  changed();
  return true;
}

void ProjectState::clear_review()
{
  ++review_generation_;
  review_.reset();
  review_source_ = "[]";
  review_error_.clear();
}

void ProjectState::discard_review()
{
  clear_review();
  changed();
}

void ProjectState::set_review_source(std::string source)
{
  if (source == review_source_) { return; }
  ++review_generation_;
  review_source_ = std::move(source);
  review_.reset();
  review_error_.clear();
  changed();
}

bool ProjectState::preview_supported() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return ready() && hello && hello->has_method("project.preview");
}

bool ProjectState::preview()
{
  if (!preview_supported() || busy() || !loaded() || project_->handle.empty()) { return false; }
  ++review_generation_;
  review_.reset();
  review_error_.clear();
  Json commands;
  try {
    // Keep the interactive editor bounded; the bridge/store impose their own independent limits.
    if (review_source_.size() > 256 * 1024) { throw std::invalid_argument("size"); }
    commands = io::parse_json(review_source_);
    if (!commands.is_array() || commands.empty() || commands.size() > 1000) {
      throw std::invalid_argument("commands");
    }
  }
  catch (const std::exception &) {
    review_error_ = std::string(store_.tr("project.review.invalid"));
    changed();
    return false;
  }
  busy_ = true;
  const auto generation = review_generation_;
  const auto base = project_->revision;
  const auto id = project_->id;
  on(client_->project_preview(project_->handle, base, commands),
     [this, generation, base, id, before = tables_](const bridge::Result<Json> &result) {
    busy_ = false;
    if (generation == review_generation_) {
      if (!result.ok()) { review_error_ = result.error().describe(); }
      else {
        try { review_ = std::make_shared<ProjectReview>(ProjectReview::from_preview(id, base, before, result.value())); }
        catch (const std::exception &) { review_error_ = std::string(store_.tr("project.review.invalid_result")); }
      }
    }
    changed();
    // Read conflicts and queued external edits, without replaying or rebasing this draft.
    if (!result.ok() || dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::can_apply_review() const
{
  return ready() && !busy() && loaded() && review_ && !project_->handle.empty() &&
         review_->project_id == project_->id && review_->base_revision == project_->revision &&
         dirty_revision_ <= review_->base_revision;
}

bool ProjectState::apply_review()
{
  if (!can_apply_review()) { return false; }
  const auto review = review_;
  // Consume before sending: a failed/uncertain write must never leave a one-click replay behind.
  ++review_generation_;
  review_.reset();
  return apply(review->commands, review->base_revision);
}

bool ProjectState::backup()
{
  if (!ready() || busy() || !loaded() || project_->handle.empty()) {
    return false;
  }
  busy_ = true;
  error_.clear();
  notice_.clear();
  on(client_->project_backup(project_->handle), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) {
      fail(result.error());
    }
    else {
      notice_ = store_.catalog().format("project.backup_saved", {{"path", io::get_string(result.value(), "path")}});
      changed();
    }
    if (project_ && dirty_revision_ > project_->revision) {
      refresh();
    }
  });
  changed();
  return true;
}

bool ProjectState::upgrade()
{
  if (!ready() || busy() || !loaded() || project_->handle.empty()) {
    return false;
  }
  busy_ = true;
  error_.clear();
  notice_.clear();
  on(client_->project_upgrade(project_->handle, project_->revision), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) {
      fail(result.error());
    }
    else {
      const Json &backup = result.value().at("backup");
      if (backup.is_object()) {
        notice_ = store_.catalog().format("project.backup_saved", {{"path", io::get_string(backup, "path")}});
      }
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    }
    refresh();
  });
  changed();
  return true;
}

bool ProjectState::undo() { return restore_edit(false); }
bool ProjectState::redo() { return restore_edit(true); }

bool ProjectState::restore_edit(const bool redo)
{
  if (!ready() || busy() || !loaded() || project_->handle.empty() || !(redo ? can_redo() : can_undo())) {
    return false;
  }
  busy_ = true;
  error_.clear();
  notice_.clear();
  auto future = redo ? client_->project_redo(project_->handle, project_->revision) :
                       client_->project_undo(project_->handle, project_->revision);
  on(std::move(future), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) {
      fail(result.error());
    }
    else {
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    }
    refresh();
  });
  changed();
  return true;
}

bool ProjectState::selected_file() const
{
  return loaded() && file_index_.value("compatible", false) &&
         table_id_ == io::get_string(file_index_, "table_id") && selected_record() >= 0;
}

bool ProjectState::index_files(const std::vector<std::string> &paths) { return edit_files(paths, true); }
bool ProjectState::refresh_file() { return selected_file() && edit_files({record_id_}, false); }

bool ProjectState::import_csv(const std::string &source, const std::string &name, const Json &types,
                              const Json &units, const std::string &delimiter)
{
  if (!ready() || busy() || !loaded()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  on(client_->call("project.csv.import", {{"handle", project_->handle}, {"expected_revision", project_->revision},
      {"source", source}, {"name", name}, {"types", types}, {"units", units}, {"delimiter", delimiter}}, options),
      [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result.ok()) { fail(result.error()); }
    else {
      table_id_ = io::get_string(result.value(), "table_id");
      const auto &records = result.value().at("record_ids");
      record_id_ = records.empty() ? std::string() : records.front().get<std::string>();
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    }
    refresh();
  });
  changed();
  return true;
}

bool ProjectState::export_csv(const std::string &destination, const std::string &delimiter)
{
  if (!ready() || busy() || !loaded() || !table()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  on(client_->call("project.csv.export", {{"handle", project_->handle}, {"expected_revision", project_->revision},
      {"table_id", table_id_}, {"destination", destination}, {"delimiter", delimiter}}, options),
      [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result.ok()) { fail(result.error()); }
    else { notice_ = store_.catalog().format("project.csv.saved", {{"path", io::get_string(result.value(), "path")}}); changed(); }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::edit_files(const std::vector<std::string> &items, const bool index)
{
  if (!ready() || busy() || !loaded() || project_->format_version < 3 || items.empty()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  auto future = index ? client_->project_files_index(project_->handle, project_->revision, items) :
                        client_->project_files_refresh(project_->handle, project_->revision, items);
  on(std::move(future), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); }
    else {
      table_id_ = io::get_string(result.value(), "table_id");
      const auto &records = result.value().at("record_ids");
      if (!records.empty()) { record_id_ = records.front().get<std::string>(); }
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    }
    refresh();
  });
  changed();
  return true;
}

bool ProjectState::open_file(const bool vscode)
{
  if (!ready() || busy() || !selected_file()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  on(client_->project_files_resolve(project_->handle, project_->revision, record_id_),
     [this, vscode](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); refresh(); }
    else {
      const auto &open = vscode ? open_vscode : open_external;
      if (!open || !open(io::get_string(result.value(), "path"), &error_)) {
        if (error_.empty()) { error_ = std::string(store_.tr("project.files.open_failed")); }
        store_.log(error_);
      }
      changed();
    }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::view_file(const std::string &preset)
{
  if (!ready() || busy() || !selected_file()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  on(client_->project_files_resolve(project_->handle, project_->revision, record_id_),
     [this, preset](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); refresh(); }
    else {
      const auto path = io::get_string(result.value(), "path");
      const auto source = classify_path(path, &error_);
      if (source.kind != SourceKind::None) {
        const auto *info = store_.viewer().preset(preset);
        if (source.evaluates() && (!info || !info->accepts_field_file())) {
          error_ = std::string(store_.tr("project.files.viewer_preset_required"));
        }
        else {
          OpenResultRequest request;
          request.local_paths = {path};
          if (source.evaluates()) { request.preset = preset; }
          store_.request_open_result(std::move(request));
        }
      }
      if (!error_.empty()) { store_.log(error_); }
      changed();
    }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::open_folder(const bool vscode)
{
  if (!loaded() || busy()) { return false; }
  error_.clear();
  const auto &open = vscode ? open_vscode : open_external;
  const bool result = open && open(project_->directory, &error_);
  if (!result && error_.empty()) { error_ = std::string(store_.tr("project.files.open_failed")); }
  changed();
  return result;
}

bool ProjectState::capture_file()
{
  if (!ready() || busy() || !selected_file() || project_->format_version < 4) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  input_verification_ = Json::object();
  on(client_->project_snapshots_capture(project_->handle, project_->revision, {record_id_}),
     [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); }
    else {
      const Json &snapshot = result.value().at("snapshot");
      input_snapshots_.push_back(snapshot);
      notice_ = store_.catalog().format("project.snapshots.saved", {{"id", io::get_string(snapshot, "id")}});
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    }
    refresh();
  });
  changed();
  return true;
}

bool ProjectState::load_input_snapshots()
{
  if (!ready() || busy() || !loaded() || project_->format_version < 4) { return false; }
  busy_ = true;
  error_.clear();
  input_verification_ = Json::object();
  on(client_->project_snapshots_list(project_->handle), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); }
    else {
      input_snapshots_ = result.value().at("snapshots");
      dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
      changed();
    }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::verify_input_snapshot(const std::string &id)
{
  if (!ready() || busy() || !loaded() || project_->format_version < 4 || id.empty()) { return false; }
  busy_ = true;
  error_.clear();
  input_verification_ = Json::object();
  on(client_->project_snapshots_verify(project_->handle, id), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); }
    else { input_verification_ = result.value(); changed(); }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

void ProjectState::clear_runs()
{
  runs_ = Json::array();
  run_ = Json::object();
  run_id_.clear();
  runs_offset_ = 0;
  runs_next_offset_ = -1;
  runs_loaded_ = runs_dirty_ = false;
}

bool ProjectState::load_runs(const int64_t offset)
{
  if (!ready() || busy() || !loaded() || project_->format_version < 5 || offset < 0) { return false; }
  busy_ = true;
  runs_dirty_ = false;
  error_.clear();
  on(client_->project_runs_list(project_->handle, offset), [this, offset](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); return; }
    runs_ = result.value().at("runs");
    runs_offset_ = offset;
    runs_next_offset_ = io::get_int(result.value(), "next_offset", -1);
    runs_loaded_ = true;
    dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
    if (selected_run() < 0) {
      run_id_ = runs_.empty() ? std::string() : io::get_string(runs_.front(), "id");
      run_ = Json::object();
    }
    changed();
    if (!run_id_.empty()) { select_run(run_id_); }
    else if (dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

int ProjectState::selected_run() const
{
  for (size_t i = 0; i < runs_.size(); ++i) {
    if (io::get_string(runs_[i], "id") == run_id_) { return int(i); }
  }
  return -1;
}

bool ProjectState::select_run(const std::string &id) { return run_operation("get", id); }
bool ProjectState::submit_run(const bool allow_stale) { return run_operation("submit", run_id_, allow_stale); }
bool ProjectState::refresh_run() { return run_operation("refresh", run_id_); }
bool ProjectState::cancel_run() { return run_operation("cancel", run_id_); }

bool ProjectState::run_operation(const std::string &action, const std::string &id, const bool allow_stale)
{
  if (!ready() || busy() || !loaded() || project_->format_version < 5 || id.empty()) { return false; }
  busy_ = true;
  error_.clear();
  notice_.clear();
  if (run_id_ != id) { run_ = Json::object(); }
  run_id_ = id;
  auto future = action == "submit" ? client_->project_runs_submit(project_->handle, id, allow_stale) :
                action == "cancel" ? client_->project_runs_cancel(project_->handle, id) :
                action == "refresh" ? client_->project_runs_refresh(project_->handle, id) :
                client_->project_runs_get(project_->handle, id);
  on(std::move(future), [this, action](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result) { fail(result.error()); }
    else {
      run_ = result.value().at("run");
      dirty_revision_ = std::max(dirty_revision_, io::get_int(run_, "parameter_revision", -1));
      if (action != "get") { runs_dirty_ = true; }
      changed();
    }
    if (project_ && dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

const ProjectTable *ProjectState::table() const
{
  const auto it = std::find_if(tables_.begin(), tables_.end(), [this](const auto &t) { return t.id == table_id_; });
  return it == tables_.end() ? nullptr : &*it;
}

void ProjectState::select_table(std::string id)
{
  if (id != table_id_) {
    table_id_ = std::move(id);
    record_id_.clear();
    validate_selection();
    changed();
  }
}

void ProjectState::select_record(std::string id)
{
  record_id_ = std::move(id);
  validate_selection();
  changed();
}

int ProjectState::selected_record() const
{
  const auto *t = table();
  if (t) {
    for (size_t i = 0; i < t->records.size(); ++i) {
      if (t->records[i].id == record_id_) {
        return int(i);
      }
    }
  }
  return -1;
}

void ProjectState::validate_selection()
{
  if (!table()) {
    table_id_ = tables_.empty() ? std::string() : tables_.front().id;
  }
  if (const auto *t = table(); t && selected_record() < 0) {
    record_id_ = t->records.empty() ? std::string() : t->records.front().id;
  }
}

}  // namespace stk::app
