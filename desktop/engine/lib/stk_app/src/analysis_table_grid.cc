/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_table_grid.hh"

#include "stk/io/graph.hh"

#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace stk::app {
namespace {
void require(const bool valid, const char *message)
{
  if (!valid) { throw std::invalid_argument(message); }
}
} // namespace

std::shared_ptr<const AnalysisTableGrid> AnalysisTableGrid::from_output(
    std::shared_ptr<const AnalysisResultInspection> model, const std::string &output)
{
  require(bool(model) && io::is_graph_id(output), "An inline table requires a verified result and output identity");
  const auto &outputs = model->result().at("outputs");
  const auto found = outputs.find(output);
  require(found != outputs.end() && found->is_object() && found->contains("type") && found->at("type") == "table",
          "The selected output is not a delivered table");
  const auto &table = *found;
  require(!table.contains("blob"), "Blob-backed table content is not loaded");
  require(table.contains("column_names") && table.at("column_names").is_array() &&
      table.contains("columns") && table.at("columns").is_object() &&
      table.contains("units") && table.at("units").is_object(), "Invalid inline table metadata");
  const auto &names = table.at("column_names"), &values = table.at("columns"), &units = table.at("units");
  require(names.size() == values.size(), "Inline table column names and values must match exactly");
  // No raw/unverified JSON enters this adapter. Borrow names while checking every structure;
  // do not copy arbitrary keys, units or columns until the whole table is known consistent.
  // ordered_json object lookup is linear. Index once before walking declared column order.
  std::map<std::string_view, const io::Json *> value_index, unit_index;
  for (const auto &[name, value] : values.items()) { value_index.emplace(name, &value); }
  for (const auto &[name, unit] : units.items()) { unit_index.emplace(name, &unit); }
  std::set<std::string_view> distinct;
  size_t rows = 0;
  for (size_t index = 0; index < names.size(); ++index) {
    require(names[index].is_string(), "Inline table column names must be strings");
    const auto &name = names[index].get_ref<const std::string &>();
    require(distinct.insert(name).second, "Inline table column names must be distinct");
    const auto column = value_index.find(name);
    require(column != value_index.end() && column->second->is_array(), "Inline table columns must be named arrays");
    if (index == 0) { rows = column->second->size(); }
    require(column->second->size() == rows, "Inline table columns must have equal row counts");
  }
  for (const auto &[name, unit] : units.items()) {
    require(distinct.contains(name) && unit.is_string() && !unit.get_ref<const std::string &>().empty(),
            "Inline table units must be nonempty strings for declared columns");
  }
  auto grid = std::shared_ptr<AnalysisTableGrid>(new AnalysisTableGrid);
  grid->inspection_ = std::move(model); grid->output_ = output; grid->row_count_ = rows;
  for (size_t index = 0; index < names.size(); ++index) {
    AnalysisTableColumn column;
    column.index = index; column.name = names[index].get_ref<const std::string &>();
    const auto label = grid->inspection_->describe({std::string("outputs"), output, std::string("column_names"), index});
    column.label = label.preview; column.label_truncated = label.preview_truncated;
    const auto unit = unit_index.find(column.name);
    if (unit != unit_index.end()) {
      column.has_unit = true; column.unit = unit->second->get_ref<const std::string &>();
    }
    grid->columns_.push_back(std::move(column));
  }
  return grid;
}

AnalysisTablePage AnalysisTableGrid::page(const size_t row_offset, const size_t column_offset,
                                         const size_t row_limit, const size_t column_limit) const
{
  require(row_offset <= row_count_ && column_offset <= columns_.size() && row_limit >= 1 &&
      row_limit <= row_page_size && column_limit >= 1 && column_limit <= column_page_size,
      "Invalid inline table row or column page");
  AnalysisTablePage page;
  page.row_offset = row_offset; page.column_offset = column_offset;
  page.total_rows = row_count_; page.total_columns = columns_.size();
  const size_t row_end = row_offset + std::min(row_limit, row_count_ - row_offset);
  const size_t column_end = column_offset + std::min(column_limit, columns_.size() - column_offset);
  page.rows.resize(row_end - row_offset);
  for (size_t column = column_offset; column < column_end; ++column) {
    page.columns.push_back(column);
    // Resolve/copy a potentially long column identity once per visible column, never per
    // cell. Existing property pages borrow the immutable array and format <=64 children.
    auto properties = inspection_->children(column_path(column), row_offset, row_limit);
    for (size_t row = 0; row < properties.rows.size(); ++row) {
      page.rows[row].push_back(std::move(properties.rows[row].value));
    }
  }
  if (row_end < row_count_) { page.next_row_offset = row_end; }
  if (column_end < columns_.size()) { page.next_column_offset = column_end; }
  return page;
}

AnalysisJsonPath AnalysisTableGrid::column_path(const size_t column) const
{
  require(column < columns_.size(), "The inline table column does not exist");
  return {std::string("outputs"), output_, std::string("columns"), columns_[column].name};
}
AnalysisJsonPath AnalysisTableGrid::cell_path(const size_t row, const size_t column) const
{
  require(row < row_count_, "The inline table row does not exist");
  auto path = column_path(column); path.emplace_back(row); return path;
}
AnalysisJsonPath AnalysisTableGrid::column_name_path(const size_t column) const
{
  require(column < columns_.size(), "The inline table column does not exist");
  return {std::string("outputs"), output_, std::string("column_names"), column};
}
AnalysisJsonPath AnalysisTableGrid::unit_path(const size_t column) const
{
  require(column < columns_.size() && columns_[column].has_unit, "The inline table unit is not specified");
  return {std::string("outputs"), output_, std::string("units"), columns_[column].name};
}
AnalysisJsonDescription AnalysisTableGrid::unit_description(const size_t column) const
{
  return inspection_->describe(unit_path(column));
}
} // namespace stk::app
