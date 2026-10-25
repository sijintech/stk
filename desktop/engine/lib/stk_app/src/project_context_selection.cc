/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/project_context_selection.hh"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace stk::app {
namespace {
template<typename Items>
std::unordered_map<std::string, size_t> object_order(const Items &items)
{
  std::unordered_map<std::string, size_t> order;
  order.reserve(items.size());
  for (size_t i = 0; i < items.size(); ++i) {
    if (items[i].id.empty() || !order.emplace(items[i].id, i).second) {
      throw std::invalid_argument("Context selection requires distinct, nonempty object IDs");
    }
  }
  return order;
}

template<typename Items> std::vector<std::string> object_ids(const Items &items)
{
  std::vector<std::string> ids;
  ids.reserve(items.size());
  for (const auto &item : items) { ids.push_back(item.id); }
  return ids;
}
}  // namespace

void ProjectContextSelection::pin(std::string handle, int64_t revision, const ProjectTable &table,
                                  const std::string &seed_record)
{
  if (handle.empty() || revision < 0 || table.id.empty()) {
    throw std::invalid_argument("Context selection requires an opening handle, revision and table");
  }
  ProjectTable snapshot = table;
  if (table.loaded_records() > table.records.size() || table.record_offset < 0 ||
      table.record_offset > table.total_records() ||
      int64_t(table.loaded_records()) > table.total_records() - table.record_offset) {
    throw std::invalid_argument("Invalid context table page");
  }
  // A shared selection may append a row from another page without its global ordinal.
  // The picker reads that row's actual page before seeding the independent scope.
  snapshot.records.resize(table.loaded_records());
  auto row_order = object_order(snapshot.records);
  for (auto &[id, position] : row_order) { position += size_t(table.record_offset); }
  auto field_order = object_order(table.fields);
  std::vector<std::string> rows, fields;
  if (row_order.contains(seed_record) && !table.fields.empty() && table.fields.size() <= max_fields) {
    rows.push_back(seed_record);
    fields = object_ids(table.fields);
  }
  handle_ = std::move(handle);
  revision_ = revision;
  table_ = std::move(snapshot);
  row_order_ = std::move(row_order);
  field_order_ = std::move(field_order);
  rows_ = std::move(rows);
  fields_ = std::move(fields);
  ++generation_;
}

int64_t ProjectContextSelection::row_position(const std::string &id) const
{
  const auto found = row_order_.find(id);
  return found == row_order_.end() ? -1 : int64_t(found->second);
}

bool ProjectContextSelection::merge_page(const std::string &handle, int64_t revision,
                                          const ProjectTable &page, uint64_t generation)
{
  if (!accepts(generation) || !current(handle, revision) || page.id != table_.id ||
      page.total_records() != table_.total_records() || page.record_offset < 0 ||
      page.record_offset > page.total_records() || page.loaded_records() != page.records.size() ||
      int64_t(page.records.size()) > page.total_records() - page.record_offset ||
      page.fields.size() != table_.fields.size()) { return false; }
  for (size_t i = 0; i < page.fields.size(); ++i) {
    const auto &a = page.fields[i], &b = table_.fields[i];
    if (a.id != b.id || a.name != b.name || a.type != b.type || a.unit != b.unit || a.options != b.options) { return false; }
  }
  std::unordered_map<std::string, size_t> order;
  ProjectTable next = page;
  for (size_t i = 0; i < page.records.size(); ++i) {
    const auto &id = page.records[i].id;
    const auto position = size_t(page.record_offset) + i;
    if (id.empty() || !order.emplace(id, position).second ||
        (row_order_.contains(id) && row_order_.at(id) != position)) { return false; }
    for (const auto &selected : rows_) {
      if (row_order_.at(selected) == position && selected != id) { return false; }
    }
  }
  for (const auto &row : table_.records) {
    if (row_checked(row.id) && !order.contains(row.id)) {
      next.records.push_back(row);
      order.emplace(row.id, row_order_.at(row.id));
    }
  }
  table_ = std::move(next);
  row_order_ = std::move(order);
  ++generation_;
  return true;
}

void ProjectContextSelection::reset()
{
  handle_.clear();
  revision_ = -1;
  table_ = {};
  row_order_.clear();
  field_order_.clear();
  rows_.clear();
  fields_.clear();
  ++generation_;
}

bool ProjectContextSelection::current(const std::string &handle, int64_t revision) const
{
  return !handle_.empty() && handle_ == handle && revision_ == revision;
}

bool ProjectContextSelection::row_checked(const std::string &id) const
{
  return std::find(rows_.begin(), rows_.end(), id) != rows_.end();
}

bool ProjectContextSelection::field_checked(const std::string &id) const
{
  return std::find(fields_.begin(), fields_.end(), id) != fields_.end();
}

bool ProjectContextSelection::accepts(uint64_t generation) const
{
  return !handle_.empty() && generation == generation_;
}

bool ProjectContextSelection::replace(std::vector<std::string> &selection,
                                     std::vector<std::string> next)
{
  if (selection != next) {
    selection = std::move(next);
    ++generation_;
  }
  return true;
}

bool ProjectContextSelection::set(std::vector<std::string> &selection,
                                 const std::unordered_map<std::string, size_t> &order, size_t limit,
                                 const std::string &id, bool checked, uint64_t generation)
{
  if (!accepts(generation) || !order.contains(id)) { return false; }
  const auto found = std::find(selection.begin(), selection.end(), id);
  if (checked == (found != selection.end())) { return true; }
  if (checked) {
    if (selection.size() >= limit) { return false; }
    const size_t position = order.at(id);
    const auto where = std::lower_bound(selection.begin(), selection.end(), position,
                                       [&](const auto &item, size_t index) { return order.at(item) < index; });
    selection.insert(where, id);
  }
  else { selection.erase(found); }
  ++generation_;
  return true;
}

bool ProjectContextSelection::set_row(const std::string &id, bool checked, uint64_t generation)
{
  return set(rows_, row_order_, max_rows, id, checked, generation);
}

bool ProjectContextSelection::set_field(const std::string &id, bool checked, uint64_t generation)
{
  return set(fields_, field_order_, max_fields, id, checked, generation);
}

bool ProjectContextSelection::all_rows(uint64_t generation)
{
  if (!accepts(generation) || !table_.records_complete || table_.records.size() > max_rows) { return false; }
  return replace(rows_, object_ids(table_.records));
}

bool ProjectContextSelection::all_fields(uint64_t generation)
{
  if (!accepts(generation) || table_.fields.size() > max_fields) { return false; }
  return replace(fields_, object_ids(table_.fields));
}

bool ProjectContextSelection::clear_rows(uint64_t generation)
{
  return accepts(generation) && replace(rows_, {});
}

bool ProjectContextSelection::clear_fields(uint64_t generation)
{
  return accepts(generation) && replace(fields_, {});
}

bool ProjectContextSelection::valid() const
{
  return !handle_.empty() && !rows_.empty() && !fields_.empty() && rows_.size() <= max_rows &&
         fields_.size() <= max_fields && cell_count() <= max_cells;
}

}  // namespace stk::app
