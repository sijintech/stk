/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_state.hh"
#include "stk/app/app_store.hh"
#include "stk/app/analysis_document.hh"

#include <algorithm>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {
constexpr int64_t page_limit = 200;

ProjectTable record_page(const Json &value, const bridge::ProjectInfo &project, const ProjectTable &metadata)
{
  if (value.at("project_id") != project.id || value.at("revision") != project.revision ||
      value.at("format_version") != project.format_version || value.at("table").at("id") != metadata.id) {
    throw std::invalid_argument("Table page belongs to another project or revision");
  }
  auto table = ProjectTable::from_json(value.at("table"));
  table.record_count = value.at("total").get<int64_t>();
  table.record_offset = value.at("offset").get<int64_t>();
  if (table.record_count != metadata.total_records() || table.record_offset < 0 ||
      table.records.size() > size_t(page_limit) || (!table.records.empty() &&
      (table.record_offset > table.record_count || int64_t(table.records.size()) > table.record_count - table.record_offset))) {
    throw std::invalid_argument("Invalid table page boundaries");
  }
  std::set<std::string> ids;
  for (const auto &record : table.records) {
    if (!canonical_uuid(record.id) || !ids.insert(record.id).second) { throw std::invalid_argument("Invalid record identity"); }
  }
  table.first_record_id = metadata.first_record_id;
  table.records_complete = table.record_offset == 0 && int64_t(table.records.size()) == table.record_count;
  return table;
}

Json read_params(const bridge::ProjectInfo &project, const std::string &table_id,
                 const int64_t offset, const std::string &record_id)
{
  Json params = {{"handle", project.handle}, {"expected_revision", project.revision},
                 {"table_id", table_id}, {"offset", offset}, {"limit", page_limit}};
  if (!record_id.empty()) { params["record_id"] = record_id; }
  return params;
}
}  // namespace

ProjectTable ProjectTable::from_catalog(const Json &value)
{
  auto table = from_json({{"id", value.at("id")}, {"name", value.at("name")},
                         {"fields", value.at("fields")}, {"records", Json::array()}});
  table.record_count = value.at("record_count").get<int64_t>();
  table.first_record_id = value.at("first_record_id").is_null() ? std::string() : value.at("first_record_id").get<std::string>();
  if (!canonical_uuid(table.id) || table.record_count < 0 ||
      (table.record_count == 0 ? !table.first_record_id.empty() : !canonical_uuid(table.first_record_id))) {
    throw std::invalid_argument("Invalid table catalog");
  }
  table.records_complete = table.record_count == 0;
  return table;
}

void ProjectRead::validate() const
{
  if (project.handle.empty() || !canonical_uuid(project.id) || project.revision < 0) {
    throw std::invalid_argument("Invalid project read identity");
  }
  bool found_table = table_id.empty(), found_record = record_id.empty();
  std::set<std::string> ids;
  for (const auto &table : tables) {
    if (!canonical_uuid(table.id) || !ids.insert(table.id).second || table.total_records() < 0 ||
        table.record_offset < 0 || table.record_offset > table.total_records() ||
        table.loaded_records() > table.records.size() ||
        int64_t(table.loaded_records()) > table.total_records() - table.record_offset) {
      throw std::invalid_argument("Invalid project table read");
    }
    if (table.id != table_id) { continue; }
    found_table = true;
    for (const auto &record : table.records) { if (record.id == record_id) { found_record = true; } }
  }
  if (!found_table || !found_record) { throw std::invalid_argument("Selected project table or record is missing"); }
}

ProjectRead ProjectRead::from_snapshot(const bridge::ProjectInfo &info, const Json &snapshot,
                                       std::string table, std::string record)
{
  if (snapshot.at("project").at("id") != info.id || snapshot.at("project").at("revision") != info.revision ||
      snapshot.at("format_version") != info.format_version || !snapshot.at("tables").is_array()) {
    throw std::invalid_argument("Project snapshot does not match its opened identity and revision");
  }
  ProjectRead read;
  read.project = info; read.table_id = std::move(table); read.record_id = std::move(record);
  for (const auto &value : snapshot.at("tables")) { read.tables.push_back(ProjectTable::from_json(value)); }
  read.file_index = snapshot.value("file_index", Json::object());
  read.edit_history = snapshot.value("edit_history", Json::object());
  read.validate();
  return read;
}

namespace {
class CatalogReader : public std::enable_shared_from_this<CatalogReader> {
 public:
  CatalogReader(ProjectPageRequest request, bridge::ProjectInfo project, std::string table,
                std::string record, bool exact, std::function<void(bridge::Result<ProjectRead>)> complete)
      : request_(std::move(request)), opened_(std::move(project)), table_(std::move(table)),
        record_(std::move(record)), exact_(exact), complete_(std::move(complete)) {}

  void start()
  {
    value_ = {}; value_.project = opened_; total_ = -1; table_ids_.clear();
    value_.table_id = table_; value_.record_id = record_;
    catalog(0);
  }

 private:
  void fail(const bridge::Error &error)
  {
    if (!exact_ && error.code == bridge::ErrorCode::Conflict && restarts_ < 3) {
      ++restarts_; start(); return;
    }
    auto complete = std::move(complete_);
    if (complete) { complete(error); }
  }
  void invalid(const std::exception &error)
  {
    fail(bridge::Error::make(bridge::ErrorCode::InvalidParams, error.what()));
  }
  void finish()
  {
    try { value_.validate(); }
    catch (const std::exception &error) { invalid(error); return; }
    auto complete = std::move(complete_);
    if (complete) { complete(std::move(value_)); }
  }
  void catalog(int64_t offset)
  {
    Json params = {{"handle", opened_.handle}, {"offset", offset}, {"limit", page_limit}};
    if (exact_ || offset) { params["expected_revision"] = value_.project.revision; }
    request_("project.catalog", std::move(params),
        [self = shared_from_this(), offset](const bridge::Result<Json> &result) { self->catalog_ready(offset, result); });
  }
  void catalog_ready(int64_t offset, const bridge::Result<Json> &result)
  {
    if (!result) { fail(result.error()); return; }
    std::optional<int64_t> next;
    try {
      const auto &page = result.value();
      const auto revision = page.at("project").at("revision").get<int64_t>();
      const auto total = page.at("total").get<int64_t>();
      if (page.at("project").at("id") != opened_.id || revision < opened_.revision ||
          page.at("offset") != offset || !page.at("tables").is_array() ||
          page.at("tables").size() > size_t(page_limit) || total < 0 ||
          ((exact_ || offset) && (revision != value_.project.revision ||
                                 page.at("format_version") != value_.project.format_version)) ||
          (offset && total != total_)) {
        throw std::invalid_argument("Invalid or inconsistent project catalog page");
      }
      if (!offset) {
        value_.project.revision = revision;
        value_.project.format_version = page.at("format_version").get<int>();
        value_.project.name = page.at("project").at("name").get<std::string>();
        total_ = total;
        value_.file_index = page.value("file_index", Json::object());
        value_.edit_history = page.value("edit_history", Json::object());
      }
      for (const auto &item : page.at("tables")) {
        auto table = ProjectTable::from_catalog(item);
        if (!table_ids_.insert(table.id).second) { throw std::invalid_argument("Duplicate table in catalog"); }
        value_.tables.push_back(std::move(table));
      }
      if (!page.at("next_offset").is_null()) {
        next = page.at("next_offset").get<int64_t>();
        if (*next <= offset || *next != int64_t(value_.tables.size()) || *next >= total) {
          throw std::invalid_argument("Invalid catalog continuation");
        }
      }
      else if (int64_t(value_.tables.size()) != total) { throw std::invalid_argument("Incomplete project catalog"); }
    }
    catch (const std::exception &error) { invalid(error); return; }
    if (next) { catalog(*next); return; }
    auto selected = std::find_if(value_.tables.begin(), value_.tables.end(),
                                 [this](const auto &table) { return table.id == table_; });
    if (exact_) {
      if (table_.empty() && record_.empty()) { finish(); return; }
      if (selected == value_.tables.end() || (!record_.empty() && !selected->total_records())) {
        fail(bridge::Error::make(bridge::ErrorCode::NotFound, "Workspace selected table or record is missing")); return;
      }
    }
    else {
      if (selected == value_.tables.end()) { selected = value_.tables.begin(); }
      if (selected == value_.tables.end()) { value_.table_id.clear(); value_.record_id.clear(); finish(); return; }
      value_.table_id = selected->id;
      value_.record_id = selected->id == table_ && !record_.empty() ? record_ : selected->first_record_id;
    }
    if (!selected->total_records()) { value_.record_id.clear(); finish(); return; }
    records(value_.record_id);
  }
  void records(const std::string &record)
  {
    request_("project.table.read", read_params(value_.project, value_.table_id, 0, record),
        [self = shared_from_this(), record](const bridge::Result<Json> &result) { self->records_ready(record, result); });
  }
  void records_ready(const std::string &record, const bridge::Result<Json> &result)
  {
    auto selected = std::find_if(value_.tables.begin(), value_.tables.end(),
                                 [this](const auto &table) { return table.id == value_.table_id; });
    if (!result) {
      if (!exact_ && result.error().code == bridge::ErrorCode::NotFound && record != selected->first_record_id) {
        value_.record_id = selected->first_record_id; records(value_.record_id); return;
      }
      fail(result.error()); return;
    }
    try {
      auto page = record_page(result.value(), value_.project, *selected);
      if (!record.empty() && std::none_of(page.records.begin(), page.records.end(),
                                          [&](const auto &row) { return row.id == record; })) {
        throw std::invalid_argument("Selected record missing from its page");
      }
      *selected = std::move(page);
    }
    catch (const std::exception &error) { invalid(error); return; }
    finish();
  }
  ProjectPageRequest request_;
  bridge::ProjectInfo opened_;
  std::string table_, record_;
  bool exact_;
  std::function<void(bridge::Result<ProjectRead>)> complete_;
  ProjectRead value_;
  int64_t total_ = -1;
  std::set<std::string> table_ids_;
  int restarts_ = 0;
};
}  // namespace

void read_project_pages(ProjectPageRequest request, const bridge::ProjectInfo &project,
                        std::string table, std::string record, bool exact,
                        std::function<void(bridge::Result<ProjectRead>)> complete)
{
  std::make_shared<CatalogReader>(std::move(request), project, std::move(table), std::move(record),
                                  exact, std::move(complete))->start();
}

bool ProjectState::paged_reads_supported() const
{
  if (!ready()) { return false; }
  const auto hello = client_->hello_info();
  return hello && hello->has_method("project.catalog") && hello->has_method("project.table.read");
}

void ProjectState::page_request(const std::string &method, Json params,
                               std::function<void(const bridge::Result<Json> &)> complete)
{
  // The general ProjectState callback guard lives in project_state.cc, with its template.
  const std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  auto *client = client_;
  bridge::CallOptions options;
  options.retry = bridge::CallOptions::Retry::Never;
  client->call(method, std::move(params), options).then(
      [this, weak, epoch, client, complete = std::move(complete)](const bridge::Result<Json> &result) {
    if (!weak.expired() && epoch == epoch_ && client == client_ && client == store_.bridge()) { complete(result); }
  });
}

void ProjectState::load_catalog()
{
  read_project_pages([this](const std::string &method, Json params, auto complete) {
    page_request(method, std::move(params), std::move(complete));
  }, *project_, table_id_, record_id_, false, [this](bridge::Result<ProjectRead> result) {
    fetching_ = false;
    if (!result) { snapshot_ready_ = false; fail(result.error()); return; }
    auto &read = result.value();
    project_ = std::move(read.project);
    tables_ = std::move(read.tables);
    file_index_ = std::move(read.file_index);
    undo_revision_ = io::get_int(read.edit_history, "undo_revision", -1);
    redo_revision_ = io::get_int(read.edit_history, "redo_revision", -1);
    table_id_ = std::move(read.table_id); record_id_ = std::move(read.record_id);
    read_table_id_.clear(); read_record_id_.clear();
    snapshot_ready_ = true; selection_read_failed_ = false; runs_dirty_ = true;
    validate_selection(); changed();
    if (dirty_revision_ > project_->revision) { refresh(); }
  });
}

bool ProjectState::read_table_page(const std::string &table_id, const int64_t offset, const int64_t limit,
                                    const std::string &record_id,
                                    std::function<void(bridge::Result<ProjectTable>)> complete)
{
  if (!paged_reads_supported() || !loaded() || busy() || offset < 0 || limit < 1 || limit > page_limit ||
      (!record_id.empty() && offset)) { return false; }
  const auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
  if (table == tables_.end()) { return false; }
  const auto source = *project_;
  auto params = read_params(source, table_id, offset, record_id);
  params["limit"] = limit;
  page_request("project.table.read", std::move(params),
      [this, source, table_id, offset, limit, record_id, complete = std::move(complete)](const bridge::Result<Json> &result) {
    if (!project_ || !loaded() || project_->handle != source.handle || project_->revision != source.revision ||
        dirty_revision_ > source.revision) {
      complete(bridge::Error::make(bridge::ErrorCode::Conflict, "Project changed during table read")); return;
    }
    if (!result) { complete(result.error()); return; }
    std::optional<ProjectTable> page;
    try {
      const auto metadata = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
      if (metadata == tables_.end()) { throw std::invalid_argument("Table disappeared during read"); }
      page = record_page(result.value(), source, *metadata);
      if (page->records.size() > size_t(limit) || (record_id.empty() && page->record_offset != offset) ||
          (!record_id.empty() && std::none_of(page->records.begin(), page->records.end(),
              [&](const auto &r) { return r.id == record_id; }))) {
        throw std::invalid_argument("Table read returned another range");
      }
    }
    catch (const std::exception &error) {
      complete(bridge::Error::make(bridge::ErrorCode::InvalidParams, error.what())); return;
    }
    complete(std::move(*page));
  });
  return true;
}

bool ProjectState::load_table_page(const std::string &table_id, const int64_t offset, const std::string &record_id)
{
  if (!paged_reads_supported() || busy() || !loaded() || offset < 0 || (!record_id.empty() && offset)) { return false; }
  const auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
  if (table == tables_.end()) { return false; }
  const auto source = *project_;
  fetching_ = table_page_loading_ = true;
  error_.clear();
  failed_pages_.erase(table_id);
  page_request("project.table.read", read_params(source, table_id, offset, record_id),
               [this, source, table_id, record_id](const bridge::Result<Json> &result) {
    fetching_ = table_page_loading_ = false;
    if (!project_ || project_->handle != source.handle || project_->revision != source.revision || dirty_revision_ > source.revision) {
      changed(); refresh(); return;
    }
    if (!result) {
      failed_pages_.insert(table_id);
      selection_read_failed_ = table_id == table_id_;
      fail(result.error());
      if (result.error().code == bridge::ErrorCode::Conflict) { refresh(); }
      return;
    }
    try {
      auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
      if (table == tables_.end()) { throw std::invalid_argument("Table changed during read"); }
      auto page = record_page(result.value(), source, *table);
      if (!record_id.empty() && std::none_of(page.records.begin(), page.records.end(), [&](const auto &r) { return r.id == record_id; })) {
        throw std::invalid_argument("Selected record missing from its page");
      }
      std::optional<ProjectRecord> selected;
      if (table_id == table_id_ && selected_record() >= 0) { selected = table->records[size_t(selected_record())]; }
      if (read_table_id_ == table_id) { release_read_record(); }
      *table = std::move(page);
      if (selected && !table->records_complete && std::none_of(table->records.begin(), table->records.end(),
          [&](const auto &r) { return r.id == selected->id; })) {
        table->records.push_back(std::move(*selected)); read_table_id_ = table_id; read_record_id_ = record_id_;
      }
      selection_read_failed_ = false;
      validate_selection(); changed();
    }
    catch (const std::exception &error) {
      failed_pages_.insert(table_id);
      selection_read_failed_ = table_id == table_id_;
      fail(bridge::Error::make(bridge::ErrorCode::InvalidParams, error.what()));
    }
  });
  changed();
  return true;
}
void ProjectState::request_select_async(const std::string &handle, const int64_t expected_revision,
                                        const std::string &table_id, const std::string &record_id,
                                        std::function<void(bridge::Result<Json>)> complete,
                                        std::function<bool()> still_current)
{
  using bridge::Error;
  using bridge::ErrorCode;
  if (still_current && !still_current()) { complete(Error::make(ErrorCode::Cancelled, "Selection request expired")); return; }
  const auto immediate = request_select(handle, expected_revision, table_id, record_id);
  if (immediate || immediate.error().code != ErrorCode::NotFound || !paged_reads_supported()) {
    complete(immediate); return;
  }
  const auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
  if (table == tables_.end() || table->records_complete) { complete(immediate); return; }
  const auto source = *project_;
  busy_ = true;
  page_request("project.table.read", read_params(source, table_id, 0, record_id),
               [this, source, table_id, record_id, complete = std::move(complete), still_current = std::move(still_current)]
               (const bridge::Result<Json> &result) {
    busy_ = false;
    if (still_current && !still_current()) {
      changed(); complete(Error::make(ErrorCode::Cancelled, "Selection request expired")); return;
    }
    const auto current = request_selection(source.handle);
    if (!current || !project_ || project_->revision != source.revision) {
      changed(); refresh();
      complete(current ? Error::make(ErrorCode::Conflict, "Project changed during selection") : current.error()); return;
    }
    if (!result) {
      changed();
      if (result.error().code == ErrorCode::Conflict) { refresh(); }
      complete(result.error()); return;
    }
    if (selection_guard_ && !selection_guard_()) {
      changed(); complete(Error::make(ErrorCode::Busy, "Finish unsaved edits before changing project selection")); return;
    }
    try {
      const auto table = std::find_if(tables_.begin(), tables_.end(), [&](const auto &t) { return t.id == table_id; });
      if (table == tables_.end()) { throw std::invalid_argument("Selected table disappeared"); }
      auto page = record_page(result.value(), source, *table);
      if (std::none_of(page.records.begin(), page.records.end(), [&](const auto &r) { return r.id == record_id; })) {
        throw std::invalid_argument("Selected record missing from its page");
      }
      release_read_record();
      *table = std::move(page);
      table_id_ = table_id; record_id_ = record_id; selection_read_failed_ = false;
    }
    catch (const std::exception &error) {
      changed(); complete(Error::make(ErrorCode::InvalidParams, error.what())); return;
    }
    changed(); complete(request_selection(source.handle));
  });
  changed();
}
}  // namespace stk::app
