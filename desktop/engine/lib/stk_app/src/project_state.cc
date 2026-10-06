/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_state.hh"
#include "stk/app/project_discussion.hh"

#include <algorithm>
#include <limits>

#include "stk/app/app_store.hh"
#include "stk/app/jobs_spec.hh"
#include "stk/app/viewer_state.hh"
#include "stk/platform/file_dialog.hh"

namespace stk::app {

using io::Json;

namespace {
bool canonical_project_uuid(const std::string_view id)
{
  if (id.size() != 36) { return false; }
  for (size_t i = 0; i < id.size(); ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) { if (id[i] != '-') { return false; } }
    else if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'a' && id[i] <= 'f'))) { return false; }
  }
  return true;
}
}  // namespace

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

namespace {
std::string_view trimmed(std::string_view text)
{
  const auto begin = text.find_first_not_of(" \t\r\n");
  if (begin == std::string_view::npos) { return {}; }
  return text.substr(begin, text.find_last_not_of(" \t\r\n") - begin + 1);
}
}  // namespace

std::optional<ProjectSweepAxis> project_sweep_axis(const std::string_view type, const bool range,
                                                   const std::string_view start, const std::string_view stop,
                                                   const std::string_view count, const std::string_view list,
                                                   std::string &error_key)
{
  constexpr size_t kMaxValues = 1000;  // suan.project.sweep.MAX_VALUES
  error_key.clear();
  if (type != "integer" && type != "number" && type != "text" && type != "boolean") {
    error_key = "project.sweep.error.type";
    return std::nullopt;
  }
  ProjectSweepAxis result;
  if (range) {
    if (type != "integer" && type != "number") {
      error_key = "project.sweep.error.range_type";
      return std::nullopt;
    }
    std::string ignored;
    const auto first = project_literal(type, trimmed(start), ignored);
    const auto last = project_literal(type, trimmed(stop), ignored);
    const auto points = project_literal("integer", trimmed(count), ignored);
    if (!first || !last || first->is_null() || last->is_null()) {
      error_key = "project.sweep.error.range";
      return std::nullopt;
    }
    if (!points || !points->is_number_integer() || points->get<int64_t>() < 1 ||
        points->get<int64_t>() > int64_t(kMaxValues)) {
      error_key = "project.sweep.error.count";
      return std::nullopt;
    }
    result.values = size_t(points->get<int64_t>());
    result.axis = {{"start", *first}, {"stop", *last}, {"count", *points}};
    return result;
  }
  Json values = Json::array();
  size_t begin = 0;
  while (begin <= list.size()) {
    const auto end = std::min(list.find(',', begin), list.size());
    const auto item = trimmed(list.substr(begin, end - begin));
    std::string ignored;
    const auto value = item.empty() ? std::nullopt : project_literal(type, item, ignored);
    if (!value || value->is_null()) {
      error_key = "project.sweep.error.list";
      return std::nullopt;
    }
    if (values.size() == kMaxValues) {
      error_key = "project.sweep.error.count";
      return std::nullopt;
    }
    values.push_back(*value);
    begin = end + 1;
  }
  result.values = values.size();
  result.axis = {{"values", std::move(values)}};
  return result;
}

ProjectState::ProjectState(AppStore &store) : store_(store)
{
  discussion_ = std::make_unique<ProjectDiscussion>(store, *this);
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
  clear_drafts();
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
    clear_drafts();
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
  clear_drafts();
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
  clear_drafts();
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

bool ProjectState::supports_demo() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return ready() && hello && hello->has_method("demo.create");
}

bool ProjectState::create_demo()
{
  if (!supports_demo() || busy() || project_) { return false; }
  busy_ = true;
  error_.clear();
  notice_ = std::string(store_.tr("project.demo.creating"));
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;  // Never build a second example on a restart.
  options.timeout_s = 300;  // It includes one local analysis run.
  on(client_->call("demo.create", Json::object(), options), [this](const bridge::Result<Json> &result) {
    busy_ = false;
    notice_.clear();
    if (!result.ok()) { fail(result.error()); return; }
    const auto directory = io::get_string(result.value(), "directory");
    if (!project_ && open(directory)) {
      notice_ = store_.catalog().format("project.demo.created", {{"path", directory}});
    }
    changed();
  });
  changed();
  return true;
}

bool ProjectState::supports_sweep() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  return ready() && hello && hello->has_method("project.sweep.plan");
}

bool ProjectState::sweep(const std::string &table_id, Json axes, const std::string &base_record_id, const std::string &mode)
{
  if (!supports_sweep() || busy() || !loaded() || project_->handle.empty()) {
    return false;
  }
  busy_ = true;
  error_.clear();
  notice_.clear();
  const auto handle = project_->handle;
  const auto revision = project_->revision;
  Json params = {{"handle", handle}, {"table_id", table_id}, {"axes", std::move(axes)}, {"mode", mode}};
  if (!base_record_id.empty()) { params["base_record_id"] = base_record_id; }
  on(client_->call("project.sweep.plan", std::move(params)), [this, handle, revision](const bridge::Result<Json> &result) {
    if (!result.ok()) {
      busy_ = false;
      fail(result.error());
      return;
    }
    const auto &value = result.value();
    // Write exactly what was planned against the revision on screen; never retarget a plan.
    if (!project_ || project_->handle != handle || project_->revision != revision ||
        io::get_int(value, "revision", -1) != revision) {
      busy_ = false;
      error_ = std::string(store_.tr("project.sweep.stale"));
      changed();
      refresh();
      return;
    }
    const auto &plan = value.at("plan");
    const auto rows = io::get_int(plan, "rows", 0);
    const auto &ids = plan.at("record_ids");
    const std::string first = ids.empty() || !ids.front().is_string() ? std::string() : ids.front().get<std::string>();
    on(client_->project_apply(handle, revision, plan.at("commands")), [this, rows, first](const bridge::Result<Json> &applied) {
      busy_ = false;
      if (!applied.ok()) {
        fail(applied.error());
        refresh();
        return;
      }
      dirty_revision_ = std::max(dirty_revision_, io::get_int(applied.value(), "revision", -1));
      notice_ = store_.catalog().format("project.sweep.done", {{"rows", std::to_string(rows)}});
      if (!first.empty()) { record_id_ = first; }
      refresh();
    });
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
  saved_review_ = save_request_ = Json::object();
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
  saved_review_ = save_request_ = Json::object();
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
  save_request_ = Json::object();
  if (!saved_review_.empty() && (io::get_string(saved_review_, "status") != "pending" ||
      io::get_int(saved_review_, "base_revision", -1) != project_->revision)) {
    review_error_ = std::string(store_.tr("project.drafts.stale"));
    changed();
    return false;
  }
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
         dirty_revision_ <= review_->base_revision &&
         (saved_review_.empty() || (io::get_string(saved_review_, "status") == "pending" &&
          io::get_int(saved_review_, "base_revision", -1) == review_->base_revision &&
          io::python_json_dumps(saved_review_.at("commands"), true, true) ==
              io::python_json_dumps(review_->commands, true, true)));
}

bridge::Result<Json> ProjectState::request_selection(const std::string &handle) const
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (client_ != store_.bridge() || !ready()) { return Error::make(ErrorCode::Unavailable, "The project bridge is not ready"); }
  if (!project_ || project_->handle != handle || dirty_revision_ > project_->revision) {
    return Error::make(ErrorCode::Conflict, "The visible project or its observed revision changed; inspect the project again");
  }
  if (busy() || !loaded()) { return Error::make(ErrorCode::Busy, "The project controller is busy"); }
  return Json{{"project_id", project_->id}, {"revision", project_->revision},
              {"table_id", table_id_.empty() ? Json(nullptr) : Json(table_id_)},
              {"record_id", record_id_.empty() ? Json(nullptr) : Json(record_id_)}};
}

bridge::Result<Json> ProjectState::request_select(const std::string &handle, const int64_t expected_revision,
                                                 const std::string &table_id, const std::string &record_id)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (expected_revision < 0 || !canonical_project_uuid(table_id) || !canonical_project_uuid(record_id)) {
    return Error::make(ErrorCode::InvalidParams, "Selection requires canonical table/record UUIDs and a nonnegative revision");
  }
  const auto current = request_selection(handle);
  if (!current.ok()) { return current.error(); }
  if (project_->revision != expected_revision) {
    return Error::make(ErrorCode::Conflict, "The visible project revision changed; inspect the project again");
  }
  const auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &value) { return value.id == table_id; });
  if (table == tables_.end() || std::none_of(table->records.begin(), table->records.end(),
                                           [&](const auto &value) { return value.id == record_id; })) {
    return Error::make(ErrorCode::NotFound, "The requested record does not belong to the requested project table");
  }
  // Validate both identities first. The interactive setters may fall back to the first row;
  // an explicit Python request must instead either select its exact target or change nothing.
  if (table_id_ != table_id || record_id_ != record_id) {
    table_id_ = table_id;
    record_id_ = record_id;
    changed();
  }
  return request_selection(handle);
}

bridge::Result<Json> ProjectState::request_review(const std::string &handle, const int64_t expected_revision,
                                                 const Json &commands)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (!ready()) { return Error::make(ErrorCode::Unavailable, "The project bridge is not ready"); }
  if (!preview_supported()) { return Error::make(ErrorCode::Unsupported, "Project preview is unavailable"); }
  if (!project_ || project_->handle != handle || project_->revision != expected_revision ||
      dirty_revision_ > expected_revision) {
    return Error::make(ErrorCode::Conflict, "The visible project or its revision changed; inspect the project again");
  }
  if (busy() || !loaded()) { return Error::make(ErrorCode::Busy, "The project controller is busy"); }
  if (review_ || review_source_ != "[]" || !review_error_.empty()) {
    return Error::make(ErrorCode::Conflict, "A review draft already exists; inspect and clear it in the desktop first");
  }
  if (!commands.is_array() || commands.empty() || commands.size() > 1000) {
    return Error::make(ErrorCode::InvalidParams, "commands must contain 1 to 1000 project edit commands");
  }
  const auto source = commands.dump();
  if (source.size() > 256 * 1024) {
    return Error::make(ErrorCode::InvalidParams, "Review commands exceed 256 KiB");
  }
  set_review_source(source);
  // Validation above makes this the same bounded read-only preview as the native editor.
  if (!preview()) { return Error::make(ErrorCode::Busy, "The project preview could not start"); }
  return Json{{"accepted", true}, {"project_id", project_->id}, {"base_revision", expected_revision}};
}

bridge::Result<Json> ProjectState::request_saved_review(const std::string &handle,
                                                       const int64_t expected_revision, const Json &draft)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (expected_revision < 0) {
    return Error::make(ErrorCode::InvalidParams, "Saved review requires a nonnegative revision");
  }
  if (client_ != store_.bridge() || !ready()) {
    return Error::make(ErrorCode::Unavailable, "The project bridge is not ready");
  }
  if (!project_ || project_->handle != handle || project_->revision != expected_revision ||
      dirty_revision_ > expected_revision) {
    return Error::make(ErrorCode::Conflict, "The visible project or its revision changed; inspect the project again");
  }
  if (busy() || !loaded()) { return Error::make(ErrorCode::Busy, "The project controller is busy"); }
  if (!preview_supported() || !drafts_supported()) {
    return Error::make(ErrorCode::Unsupported, "Saved project review is unavailable");
  }
  if (review_ || review_source_ != "[]" || !review_error_.empty() || !saved_review_.empty() || !save_request_.empty()) {
    return Error::make(ErrorCode::Conflict, "A review draft already exists; inspect and clear it in the desktop first");
  }
  if (!draft.is_object() || draft.size() != 9) {
    return Error::make(ErrorCode::InvalidParams, "Saved review requires a complete project draft");
  }
  for (const char *key : {"id", "project_id", "title", "base_revision", "commands", "created_at",
                          "status", "applied_revision", "closed_at"}) {
    if (!draft.contains(key)) {
      return Error::make(ErrorCode::InvalidParams, "Saved review requires a complete project draft");
    }
  }
  if (!draft.at("id").is_string() || !canonical_project_uuid(draft.at("id").get_ref<const std::string &>()) ||
      !draft.at("project_id").is_string() || !canonical_project_uuid(draft.at("project_id").get_ref<const std::string &>()) ||
      !draft.at("title").is_string() || draft.at("title").get_ref<const std::string &>().empty() ||
      draft.at("title").get_ref<const std::string &>().size() > 4096 ||
      !draft.at("created_at").is_string() || draft.at("created_at").get_ref<const std::string &>().empty() ||
      draft.at("created_at").get_ref<const std::string &>().size() > 64 ||
      !draft.at("base_revision").is_number_integer() || draft.at("base_revision") < 0 ||
      draft.at("base_revision") > std::numeric_limits<int64_t>::max()) {
    return Error::make(ErrorCode::InvalidParams, "Saved review has invalid identity or metadata");
  }
  if (draft.at("project_id") != project_->id || draft.at("base_revision") != expected_revision) {
    return Error::make(ErrorCode::Conflict, "Saved review belongs to a different project or base revision");
  }
  if (draft.at("status") != "pending" || !draft.at("applied_revision").is_null() || !draft.at("closed_at").is_null()) {
    return Error::make(ErrorCode::Conflict, "Only a pending saved draft can be opened for review");
  }
  const auto &commands = draft.at("commands");
  if (!commands.is_array() || commands.empty() || commands.size() > 1000 ||
      !std::all_of(commands.begin(), commands.end(), [](const auto &command) { return command.is_object(); })) {
    return Error::make(ErrorCode::InvalidParams, "Saved review requires 1 to 1000 project command objects");
  }
  std::string source;
  try {
    source = commands.dump();
    if (source.size() > 256 * 1024) {
      return Error::make(ErrorCode::InvalidParams, "Review commands exceed 256 KiB");
    }
    // A native JSON value can contain nonfinite numbers even though wire JSON
    // cannot. Do not let dump() silently change such numbers into null values.
    (void)io::parse_json(io::python_json_dumps(commands, false, true));
  }
  catch (const std::exception &) {
    return Error::make(ErrorCode::InvalidParams, "Saved review commands must contain valid finite UTF-8 JSON data");
  }
  // Retain the saved identity. set_review_source()/request_review() intentionally
  // create an unsaved proposal and would discard its atomic apply receipt path.
  ++review_generation_;
  saved_review_ = draft;
  review_source_ = std::move(source);
  review_.reset();
  review_error_.clear();
  drafts_error_.clear();
  changed();
  return Json{{"accepted", true}, {"project_id", project_->id}, {"base_revision", expected_revision},
              {"draft_id", draft.at("id")}};
}

bool ProjectState::apply_review()
{
  if (!can_apply_review()) { return false; }
  const auto review = review_;
  // Consume before sending: a failed/uncertain write must never leave a one-click replay behind.
  ++review_generation_;
  review_.reset();
  if (!saved_review_.empty()) {
    busy_ = true;
    const auto generation = review_generation_;
    const auto draft_id = io::get_string(saved_review_, "id");
    bridge::CallOptions options;
    options.retry = bridge::CallOptions::Retry::Never;
    on(client_->call("project.drafts.apply", {{"handle", project_->handle},
        {"draft_id", saved_review_.at("id")}, {"expected_revision", review->base_revision}}, options),
       [this, generation, draft_id](const bridge::Result<Json> &result) {
      busy_ = false;
      drafts_loaded_ = false;
      discussion_->draft_changed(draft_id);
      if (!result.ok()) { fail(result.error()); }
      else {
        if (generation == review_generation_) { saved_review_ = result.value().at("draft"); }
        dirty_revision_ = std::max(dirty_revision_, io::get_int(result.value(), "revision", -1));
      }
      refresh();
    });
    changed();
    return true;
  }
  return apply(review->commands, review->base_revision);
}

void ProjectState::clear_drafts()
{
  discussion_->reset();
  drafts_ = Json::array();
  drafts_error_.clear();
  drafts_loaded_ = false;
  drafts_offset_ = 0;
  drafts_next_offset_ = -1;
}

bool ProjectState::drafts_supported() const
{
  const auto hello = client_ ? client_->hello_info() : std::nullopt;
  if (!ready() || !loaded() || project_->format_version < 6 || !hello) { return false; }
  for (const auto *operation : {"save", "get", "list", "apply", "discard"}) {
    if (!hello->has_method(std::string("project.drafts.") + operation)) { return false; }
  }
  return true;
}

bool ProjectState::load_drafts(const int64_t offset, const bool preserve_error)
{
  if (!drafts_supported() || busy() || offset < 0) { return false; }
  busy_ = true;
  if (!preserve_error) { drafts_error_.clear(); }
  on(client_->call("project.drafts.list", {{"handle", project_->handle}, {"offset", offset}, {"limit", 100}}),
     [this, offset](const bridge::Result<Json> &result) {
    busy_ = false;
    drafts_loaded_ = true;
    if (!result.ok()) { drafts_error_ = result.error().describe(); }
    else {
      drafts_ = result.value().at("drafts");
      drafts_offset_ = offset;
      drafts_next_offset_ = io::get_int(result.value(), "next_offset", -1);
      for (const auto &draft : drafts_) {
        if (!saved_review_.empty() && draft.at("id") == saved_review_.at("id")) {
          for (const char *key : {"status", "applied_revision", "closed_at"}) { saved_review_[key] = draft.at(key); }
          if (io::get_string(saved_review_, "status") != "pending") { ++review_generation_; review_.reset(); }
        }
      }
    }
    changed();
    if (dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::save_review(const std::string &title)
{
  if (!drafts_supported() || !can_apply_review() || !saved_review_.empty() || title.empty()) { return false; }
  const auto review = review_;
  Json request = {{"handle", project_->handle}, {"commands", review->commands},
                  {"expected_revision", review->base_revision}, {"title", title}};
  auto previous = save_request_;
  previous.erase("draft_id");
  if (previous != request) {
    const auto hex = new_idempotency_key();
    request["draft_id"] = hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) +
                          "-" + hex.substr(16, 4) + "-" + hex.substr(20);
    save_request_ = request;
  }
  busy_ = true;
  drafts_error_.clear();
  const auto generation = review_generation_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  on(client_->call("project.drafts.save", save_request_, options), [this, generation](const bridge::Result<Json> &result) {
    busy_ = false;
    drafts_loaded_ = false;
    if (!result.ok()) { drafts_error_ = result.error().describe(); }
    else if (generation == review_generation_) {
      saved_review_ = result.value().at("draft");
      review_source_ = saved_review_.at("commands").dump();
    }
    changed();
    if (!result.ok() || dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::load_draft(const std::string &id)
{
  if (!drafts_supported() || busy() || id.empty()) { return false; }
  if (review_ || review_source_ != "[]" || !review_error_.empty() || !saved_review_.empty()) {
    drafts_error_ = std::string(store_.tr("project.drafts.clear_first"));
    changed();
    return false;
  }
  busy_ = true;
  drafts_error_.clear();
  const auto generation = review_generation_;
  on(client_->call("project.drafts.get", {{"handle", project_->handle}, {"draft_id", id}}),
     [this, generation](const bridge::Result<Json> &result) {
    busy_ = false;
    if (!result.ok()) { drafts_error_ = result.error().describe(); }
    else if (generation == review_generation_) {
      const auto &draft = result.value().at("draft");
      if (io::get_string(draft, "project_id") != project_->id || io::get_string(draft, "status") != "pending") {
        drafts_error_ = std::string(store_.tr("project.drafts.resolved"));
        drafts_loaded_ = false;
      }
      else {
        ++review_generation_;
        saved_review_ = draft;
        review_source_ = draft.at("commands").dump();
        review_.reset();
        review_error_.clear();
      }
    }
    changed();
    if (dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::discard_saved_draft(const std::string &id)
{
  if (!drafts_supported() || busy() || id.empty()) { return false; }
  busy_ = true;
  drafts_error_.clear();
  const auto generation = review_generation_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  on(client_->call("project.drafts.discard", {{"handle", project_->handle}, {"draft_id", id}}, options),
     [this, generation, id](const bridge::Result<Json> &result) {
    busy_ = false;
    drafts_loaded_ = false;
    discussion_->draft_changed(id);
    if (!result.ok()) { drafts_error_ = result.error().describe(); }
    else if (generation == review_generation_ && io::get_string(saved_review_, "id") == id) {
      ++review_generation_;
      review_.reset();
      saved_review_ = result.value().at("draft");
    }
    changed();
    if (dirty_revision_ > project_->revision) { refresh(); }
  });
  changed();
  return true;
}

bool ProjectState::copy_saved_review()
{
  if (busy() || saved_review_.empty()) { return false; }
  ++review_generation_;
  saved_review_ = save_request_ = Json::object();
  review_.reset();
  review_error_.clear();
  return preview(); // Explicitly start a new proposal at the currently displayed revision.
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
  if (const auto *t = table()) {
    if (selected_record() < 0) { record_id_ = t->records.empty() ? std::string() : t->records.front().id; }
  }
  else { record_id_.clear(); }
}

}  // namespace stk::app
