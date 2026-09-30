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
  auto row_order = object_order(table.records);
  auto field_order = object_order(table.fields);
  ProjectTable snapshot = table;
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
  if (!accepts(generation) || table_.records.size() > max_rows) { return false; }
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
