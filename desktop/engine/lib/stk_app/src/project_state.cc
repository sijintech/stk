/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_state.hh"

#include <algorithm>
#include <limits>

#include "stk/app/app_store.hh"

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

ProjectState::ProjectState(AppStore &store) : store_(store) {}

ProjectState::~ProjectState()
{
  alive_.reset();
  state_listener_.reset();
  changed_listener_.reset();
  closed_listener_.reset();
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
}

void ProjectState::attach(bridge::Client *client)
{
  if (client == client_) {
    return;
  }
  state_listener_.reset();
  changed_listener_.reset();
  closed_listener_.reset();
  ++epoch_;
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
  error_.clear();
  notice_.clear();
  on(create ? client_->project_create(directory, name) : client_->project_open(directory),
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
         table_id_.clear();
         record_id_.clear();
       }
       refresh();
       if (complete) { complete(*project_); }
     });
  changed();
  return true;
}

void ProjectState::clear()
{
  notice_.clear();
  project_.reset();
  tables_.clear();
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
    project_->revision = io::get_int(result.value().at("project"), "revision", 0);
    project_->format_version = int(io::get_int(result.value(), "format_version", 1));
    const auto &history = result.value().value("edit_history", Json::object());
    undo_revision_ = io::get_int(history, "undo_revision", -1);
    redo_revision_ = io::get_int(history, "redo_revision", -1);
    snapshot_ready_ = true;
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
