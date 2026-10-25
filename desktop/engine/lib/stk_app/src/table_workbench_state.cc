/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/table_workbench_state.hh"

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"
#include "stk/core/sha256.hh"

#include <algorithm>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
constexpr std::array<std::string_view, 9> methods = {
    "project.table.views.list", "project.table.views.get", "project.table.query",
    "project.table.paste.plan", "project.table.objects.list_candidates", "project.table.objects.resolve",
    "project.table.csv.preview", "project.table.io.preview", "project.table.objects.preview"};

bool array_member(const Json &value, const char *key)
{
  const auto found = value.find(key);
  return found != value.end() && found->is_array();
}
bool object_member(const Json &value, const char *key)
{
  const auto found = value.find(key);
  return found != value.end() && found->is_object();
}
bool valid_view(const Json &view, const std::string &table_id)
{
  return view.is_object() && !io::get_string(view, "id").empty() &&
      io::get_string(view, "table_id") == table_id && !io::get_string(view, "name").empty() &&
      object_member(view, "definition");
}
bool valid_sha256(const std::string &value)
{
  return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}
}  // namespace

TableWorkbenchState::TableWorkbenchState(AppStore &store, std::function<bool()> owner_valid)
    : store_(store), project_(store.project()), owner_valid_(std::move(owner_valid))
{
  sync();
}
TableWorkbenchState::~TableWorkbenchState()
{
  *alive_ = false;
  for (auto &request : requests_) { if (request.future) { request.future->cancel(); } }
}
int TableWorkbenchState::method_index(const std::string_view method)
{
  const auto found = std::find(methods.begin(), methods.end(), method);
  return found == methods.end() ? -1 : int(found - methods.begin());
}
void TableWorkbenchState::changed()
{
  ++version_;
  if (!owner_valid_ || owner_valid_()) { store_.changed(); }
}
void TableWorkbenchState::reset()
{
  ++epoch_;
  query_table_.reset();
  for (auto &request : requests_) {
    ++request.generation;
    auto old = std::move(request.future);
    request.future.reset();
    request.result = nullptr;
    if (old) { old->cancel(); }
  }
  error_.clear();
  error_method_.clear();
  changed();
}
void TableWorkbenchState::sync()
{
  if (owner_valid_ && !owner_valid_()) { return; }
  project_.sync();
  auto *client = store_.bridge();
  const auto &project = project_.project();
  const auto id = project ? project->id : std::string();
  const auto handle = project ? project->handle : std::string();
  const auto table = project_.table_id();
  const auto revision = project ? project->revision : -1;
  const auto session = client && client->state() == bridge::BridgeState::Ready ?
      std::to_string(client->bridge_pid()) + ":" + std::to_string(client->stats().spawned) : std::string();
  if (client != client_ || session != session_ || id != project_id_ || handle != handle_ ||
      table != table_id_ || revision != revision_) {
    client_ = client;
    session_ = session;
    project_id_ = id;
    handle_ = handle;
    table_id_ = table;
    revision_ = revision;
    reset();
  }
}
bool TableWorkbenchState::supported() const
{
  // AppStore can detach and destroy a bridge before this editor next synchronizes. Never
  // dereference either cached controller client until it is still the current store client.
  if ((owner_valid_ && !owner_valid_()) || !client_ || store_.bridge() != client_ ||
      session_.empty() || !project_.ready() ||
      !project_.loaded() || !project_.project() || handle_.empty() ||
      project_.project()->handle != handle_ || project_.project()->revision != revision_ ||
      project_.table_id() != table_id_) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.table.query");
}
bool TableWorkbenchState::supports(const std::string_view method) const
{
  const auto index = method_index(method);
  if (index < 0 || !supported()) { return false; }
  if (index <= 3 && (table_id_.empty() || !project_.table())) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method(method);
}
bool TableWorkbenchState::busy() const
{
  return std::any_of(requests_.begin(), requests_.end(), [](const auto &request) { return request.future.has_value(); });
}
bool TableWorkbenchState::pending(const std::string_view method) const
{
  const auto index = method_index(method);
  return index >= 0 && requests_[size_t(index)].future.has_value();
}
void TableWorkbenchState::clear_error()
{
  if (error_.empty() && error_method_.empty()) { return; }
  error_.clear();
  error_method_.clear();
  changed();
}
TableWorkbenchScope TableWorkbenchState::scope() const
{
  return {project_id_, handle_, table_id_, revision_, epoch_};
}
bool TableWorkbenchState::current(const TableWorkbenchScope &source)
{
  sync();
  return supported() && source.epoch == epoch_ && source.project_id == project_id_ &&
      source.handle == handle_ && source.table_id == table_id_ && source.revision == revision_;
}
void TableWorkbenchState::cancel() { reset(); }
const Json &TableWorkbenchState::views() const { return requests_[0].result; }
const Json &TableWorkbenchState::selected_view() const { return requests_[1].result; }
const Json &TableWorkbenchState::query_result() const { return requests_[2].result; }
const ProjectTable *TableWorkbenchState::query_table() const
{
  return supported() && !requests_[2].future ? query_table_.get() : nullptr;
}
bool TableWorkbenchState::select_record(const std::string &id)
{
  sync();
  const auto *page = query_table();
  if (!page || project_.busy()) { return false; }
  const auto at = std::find_if(page->records.begin(), page->records.end(),
      [&](const auto &record) { return record.id == id; });
  return at != page->records.end() && project_.select_read_record(handle_, revision_, table_id_, *at);
}
const Json &TableWorkbenchState::candidates() const { return requests_[4].result; }
const Json &TableWorkbenchState::resolved_object() const { return requests_[5].result; }
const Json &TableWorkbenchState::csv_preview() const { return requests_[6].result; }
const Json &TableWorkbenchState::io_preview() const { return requests_[7].result; }
const Json &TableWorkbenchState::attachment_preview() const { return requests_[8].result; }
bool TableWorkbenchState::fail(const std::string &method, const std::string &message)
{
  error_method_ = method;
  error_ = message;
  changed();
  return false;
}

bool TableWorkbenchState::valid_result(const int index, const Json &result, const Json &request) const
{
  if (!result.is_object()) { return false; }
  const char *revision_key = index == 3 ? "base_revision" : "revision";
  const auto observed = result.find(revision_key);
  if (observed == result.end() || !observed->is_number_integer() ||
      io::get_int(result, revision_key, -1) != revision_) { return false; }
  if (index == 0) {
    return array_member(result, "views") && std::all_of(result.at("views").begin(), result.at("views").end(),
        [this](const Json &view) { return valid_view(view, table_id_); });
  }
  if (index == 1) {
    return object_member(result, "view") && valid_view(result.at("view"), table_id_) &&
        io::get_string(result.at("view"), "id") == io::get_string(request, "id");
  }
  if (index == 2) {
    if (io::get_string(result, "table_id") != table_id_ || !object_member(result, "definition") ||
        !array_member(result, "fields") || !array_member(result, "records") ||
        !array_member(result, "record_ids") || !array_member(result, "issues") ||
        result.at("records").size() != result.at("record_ids").size() ||
        result.at("records").size() > size_t(io::get_int(request, "limit", 200)) ||
        io::get_int(result, "total", -1) < int64_t(result.at("records").size())) { return false; }
    for (size_t row = 0; row < result.at("records").size(); ++row) {
      const auto &id = result.at("record_ids")[row];
      const auto &record = result.at("records")[row];
      if (!id.is_string() || id.get_ref<const std::string &>().empty() || !record.is_object() ||
          io::get_string(record, "id") != id.get_ref<const std::string &>() || !object_member(record, "values")) {
        return false;
      }
    }
    return true;
  }
  if (index == 3) {
    return io::get_string(result, "table_id") == table_id_ && array_member(result, "commands") &&
        !result.at("commands").empty() && result.at("commands").size() <= 1000 &&
        io::get_int(result, "command_count", -1) == int64_t(result.at("commands").size()) &&
        array_member(result, "record_ids") && array_member(result, "field_ids");
  }
  if (index == 4) {
    if (!array_member(result, "items") || result.at("items").size() > size_t(io::get_int(request, "limit", 100)) ||
        io::get_int(result, "total", -1) < int64_t(result.at("items").size())) { return false; }
    for (const auto &item : result.at("items")) {
      if (!item.is_object() || !object_member(item, "reference") ||
          io::get_string(item.at("reference"), "project_id") != project_id_ ||
          io::get_string(item.at("reference"), "kind") != io::get_string(request, "kind")) { return false; }
    }
    return true;
  }
  if (index == 5) {
    const auto state = io::get_string(result, "state");
    return object_member(result, "reference") && request.contains("reference") &&
        result.at("reference") == request.at("reference") &&
        io::get_string(result.at("reference"), "project_id") == project_id_ &&
        (state == "available" || state == "missing" || state == "stale");
  }
  if (index == 6) {
    if (!array_member(result, "columns") || result.at("columns").empty() || result.at("columns").size() > 64 ||
        !array_member(result, "rows") || result.at("rows").size() > size_t(io::get_int(request, "limit", 20)) ||
        !valid_sha256(io::get_string(result, "source_sha256")) ||
        io::get_int(result, "total_rows", -1) < int64_t(result.at("rows").size()) ||
        io::get_int(result, "total_rows", -1) > 10000 || io::get_int(result, "command_count", -1) < 0 ||
        !result.contains("truncated") || !result.at("truncated").is_boolean() ||
        !result.contains("can_import") || !result.at("can_import").is_boolean()) { return false; }
    for (const auto &column : result.at("columns")) {
      if (!column.is_object() || io::get_string(column, "name").empty() ||
          io::get_string(column, "type") != "text" || !column.contains("unit") || !column.at("unit").is_null()) {
        return false;
      }
    }
    for (const auto &row : result.at("rows")) {
      if (!row.is_array() || row.size() != result.at("columns").size() ||
          !std::all_of(row.begin(), row.end(), [](const Json &cell) { return cell.is_string(); })) { return false; }
    }
    return true;
  }
  if (index == 8) {
    const auto kind = io::get_string(result, "kind");
    const auto sha = io::get_string(result, "content_sha256");
    const auto size = io::get_int(result, "size", -1);
    if (io::get_int(result, "version", 0) != 1 || !object_member(result, "reference") ||
        !request.contains("reference") || result.at("reference") != request.at("reference") ||
        io::get_string(result.at("reference"), "project_id") != project_id_ ||
        !valid_sha256(sha) || size < 0 || size > 1024 * 1024 ||
        !result.contains("data") || !result.at("data").is_string() ||
        !result.contains("truncated") || !result.at("truncated").is_boolean()) { return false; }
    const auto &data = result.at("data").get_ref<const std::string &>();
    if (kind == "text") {
      return data.size() <= 65536 && data.size() <= size_t(size) &&
          (result.at("truncated").get<bool>() ? size > 65536 :
              (data.size() == size_t(size) && core::Sha256::hex(data) == sha));
    }
    if (kind != "png" || result.at("truncated").get<bool>() || data.size() > 1398104) { return false; }
    const auto bytes = bridge::decode_base64(data);
    return bytes && bytes->size() == size_t(size) && core::Sha256::hex(*bytes) == sha;
  }
  if (index == 7) {
    const auto format = io::get_string(result, "format");
    if (format != io::get_string(request, "format") ||
        (format != "csv" && format != "xlsx" && format != "json") ||
        !array_member(result, "columns") || result.at("columns").empty() || result.at("columns").size() > 64 ||
        !array_member(result, "rows") || result.at("rows").size() > size_t(io::get_int(request, "limit", 20)) ||
        !valid_sha256(io::get_string(result, "source_sha256")) ||
        io::get_int(result, "total_rows", -1) < int64_t(result.at("rows").size()) ||
        io::get_int(result, "total_rows", -1) > 10000 || io::get_int(result, "command_count", -1) < 0 ||
        !result.contains("can_import") || !result.at("can_import").is_boolean() ||
        !result.contains("truncated") || !result.at("truncated").is_boolean() ||
        !result.contains("schema_present") || !result.at("schema_present").is_boolean() ||
        result.at("schema_present").get<bool>() != (format == "json") ||
        !array_member(result, "sheets") || !array_member(result, "warnings")) { return false; }
    if (!result.contains("sheet") || (format == "xlsx" ? !result.at("sheet").is_string() : !result.at("sheet").is_null())) { return false; }
    for (const auto &sheet : result.at("sheets")) {
      if (!sheet.is_object() || io::get_string(sheet, "name").empty()) { return false; }
    }
    if (format == "xlsx") {
      const auto selected = io::get_string(result, "sheet");
      if (selected.empty() || std::none_of(result.at("sheets").begin(), result.at("sheets").end(),
          [&](const Json &sheet) { return io::get_string(sheet, "name") == selected; }) ||
          (request.contains("sheet") && !request.at("sheet").is_null() && request.at("sheet") != selected)) { return false; }
    }
    for (const auto &column : result.at("columns")) {
      if (!column.is_object() || io::get_string(column, "name").empty() ||
          io::get_string(column, "type").empty() || !column.contains("unit") ||
          !(column.at("unit").is_string() || column.at("unit").is_null())) { return false; }
    }
    for (const auto &row : result.at("rows")) {
      if (!row.is_array() || row.size() != result.at("columns").size()) { return false; }
      if (format != "json" && !std::all_of(row.begin(), row.end(), [](const Json &cell) { return cell.is_string(); })) { return false; }
    }
    return std::all_of(result.at("warnings").begin(), result.at("warnings").end(), [](const Json &warning) { return warning.is_string(); });
  }
  return false;
}

bool TableWorkbenchState::scoped_call(const std::string &method, Json params, Complete complete)
{
  sync();
  const auto index = method_index(method);
  if (index < 0) { return fail(method, "Unsupported table read method"); }
  if (!supports(method) || project_.busy()) { return false; }
  if (!params.is_object()) { return fail(method, "Table read parameters must be an object"); }
  if ((params.contains("handle") && params.at("handle") != handle_) ||
      (params.contains("expected_revision") && params.at("expected_revision") != revision_) ||
      ((index == 0 || index == 2 || index == 3) && params.contains("table_id") && params.at("table_id") != table_id_)) {
    return fail(method, "Table read parameters belong to a different source");
  }
  if (index == 3 && !complete) { return fail(method, "Paste planning requires an explicit result handler"); }
  params["handle"] = handle_;
  params["expected_revision"] = revision_;
  if (index == 0 || index == 2 || index == 3) { params["table_id"] = table_id_; }

  auto &request = requests_[size_t(index)];
  const auto generation = ++request.generation;
  auto old = std::move(request.future);
  request.future.reset();
  request.result = nullptr;
  if (index == 2) { query_table_.reset(); }
  if (old) { old->cancel(); }
  if (error_method_ == method) { error_.clear(); error_method_.clear(); }
  const auto epoch = epoch_;
  const std::weak_ptr<bool> weak = alive_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  request.future = client_->call(method, params, options);
  request.future->then([this, weak, epoch, index, generation, method, params = std::move(params),
                        complete = std::move(complete)](bridge::Result<Json> response) {
    const auto live = weak.lock();
    if (!live || !*live || (owner_valid_ && !owner_valid_())) { return; }
    sync();
    if (epoch != epoch_ || requests_[size_t(index)].generation != generation) { return; }
    auto &request = requests_[size_t(index)];
    request.future.reset();
    if (!response) { fail(method, response.error().describe()); return; }
    if (project_.busy()) { fail(method, "Project changed during table read; refresh the table"); return; }
    if (!valid_result(index, response.value(), params)) { fail(method, "Invalid or stale table response"); return; }
    if (index == 2) {
      try {
        const auto &value = response.value();
        query_table_ = std::make_unique<ProjectTable>(ProjectTable::from_json({
            {"id", table_id_}, {"name", project_.table()->name},
            {"fields", Json::array()}, {"records", value.at("records")}}));
        // Query fields describe the view projection. Record details also need hidden and
        // omitted fields, whose metadata is already pinned to this same project revision.
        query_table_->fields = project_.table()->fields;
      }
      catch (const std::exception &) { fail(method, "Invalid table page"); return; }
    }
    // Keep a local value: a callback may start a replacement request or destroy this editor.
    const Json value = std::move(response.value());
    if (index != 3) { request.result = value; }
    changed();
    if (complete) {
      try { complete(value); }
      catch (const std::exception &error) {
        const auto still_live = weak.lock();
        if (still_live && *still_live && (!owner_valid_ || owner_valid_())) { fail(method, error.what()); }
      }
    }
  });
  changed();
  return true;
}
bool TableWorkbenchState::load_views(Complete complete)
{
  return scoped_call(std::string(methods[0]), Json::object(), std::move(complete));
}
bool TableWorkbenchState::load_view(const std::string &id, Complete complete)
{
  return scoped_call(std::string(methods[1]), {{"id", id}}, std::move(complete));
}
bool TableWorkbenchState::query(Json request, Complete complete)
{
  return scoped_call(std::string(methods[2]), std::move(request), std::move(complete));
}
bool TableWorkbenchState::plan_paste(Json request, Complete complete)
{
  return scoped_call(std::string(methods[3]), std::move(request), std::move(complete));
}
bool TableWorkbenchState::object_candidates(Json request, Complete complete)
{
  return scoped_call(std::string(methods[4]), std::move(request), std::move(complete));
}
bool TableWorkbenchState::resolve_object(Json request, Complete complete)
{
  return scoped_call(std::string(methods[5]), std::move(request), std::move(complete));
}
}  // namespace stk::app
