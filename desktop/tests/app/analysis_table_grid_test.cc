/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_table_grid.hh"

#include <limits>
#include <stdexcept>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
using Grid = AnalysisTableGrid;
Json table()
{
  return {{"type", "table"}, {"column_names", Json::array({"temperature", "step"})},
      {"columns", {{"step", Json::array({0, 1, 2})}, {"temperature", Json::array({-9.5, 0.0, 14.5})}}},
      {"units", {{"temperature", "K"}}}, {"attrs", {{"origin", "test"}}}};
}
std::shared_ptr<const AnalysisResultInspection> inspection(const Json &delivery)
{
  return AnalysisResultInspection::from_result(Json::array({"table"}),
      {{"schema", "stk.graph-result/1"}, {"outputs", {{"table", delivery}}}, {"errors", Json::array()}});
}
std::shared_ptr<const Grid> grid(const Json &delivery = table())
{
  return Grid::from_output(inspection(delivery), "table");
}
std::string joined(const AnalysisJsonText &text)
{
  std::string result; for (const auto &page : text.pages) { result += page; } return result;
}

TEST(AnalysisTableGrid, AuthoritativeOrderAndSparseUnitsRemainExact)
{
  const auto result = grid();
  EXPECT_EQ(result->output(), "table"); EXPECT_EQ(result->row_count(), 3u);
  ASSERT_EQ(result->columns().size(), 2u);
  EXPECT_EQ(result->columns()[0].name, "temperature"); EXPECT_EQ(result->columns()[1].name, "step");
  EXPECT_EQ(result->columns()[0].index, 0u); EXPECT_EQ(result->columns()[1].index, 1u);
  EXPECT_EQ(result->columns()[0].label, "\"temperature\"");
  EXPECT_TRUE(result->columns()[0].has_unit); EXPECT_EQ(result->columns()[0].unit, "K");
  EXPECT_EQ(result->unit_description(0).preview, "\"K\""); EXPECT_FALSE(result->columns()[1].has_unit);
  EXPECT_TRUE(result->columns()[1].unit.empty());
  EXPECT_THROW(result->unit_path(1), std::invalid_argument);
  const auto page = result->page();
  ASSERT_EQ(page.rows.size(), 3u); EXPECT_EQ(page.columns, (std::vector<size_t>{0, 1}));
  EXPECT_EQ(page.rows[0][0].preview, "-9.5"); EXPECT_EQ(page.rows[0][1].preview, "0");
  EXPECT_EQ(page.rows[1][0].preview, "0.0"); EXPECT_EQ(page.rows[2][0].preview, "14.5");
  EXPECT_EQ(joined(result->inspection()->scalar_text(result->unit_path(0))), "\"K\"");
}

TEST(AnalysisTableGrid, ExactIntegerFloatNullAndStringTypesAreNeverInferredOrRounded)
{
  auto source = table(); source["column_names"] = Json::array({"value"}); source["units"] = Json::object();
  source["columns"] = {{"value", Json::array({std::numeric_limits<uint64_t>::max(), std::numeric_limits<int64_t>::min(),
      1, 1.0, -0.0, nullptr, "null", "", true})}};
  const auto result = grid(source); const auto page = result->page();
  const std::vector<AnalysisJsonType> types{AnalysisJsonType::UnsignedInteger, AnalysisJsonType::Integer,
      AnalysisJsonType::Integer, AnalysisJsonType::Float, AnalysisJsonType::Float, AnalysisJsonType::Null,
      AnalysisJsonType::String, AnalysisJsonType::String, AnalysisJsonType::Boolean};
  const std::vector<std::string> values{"18446744073709551615", "-9223372036854775808", "1", "1.0", "-0.0", "null", "\"null\"", "\"\"", "true"};
  ASSERT_EQ(page.rows.size(), values.size());
  for (size_t row = 0; row < values.size(); ++row) {
    EXPECT_EQ(page.rows[row][0].type, types[row]); EXPECT_EQ(page.rows[row][0].preview, values[row]);
    EXPECT_EQ(joined(result->inspection()->scalar_text(result->cell_path(row, 0))), values[row]);
  }
}

TEST(AnalysisTableGrid, MulticomponentAndStructuredCellsStayNestedAndBrowsable)
{
  auto source = table(); source["column_names"] = Json::array({"vector", "details"}); source["units"] = Json::object();
  source["columns"] = {{"vector", Json::array({Json::array({1.0, -2.0, 3.0}), Json::array({4.0, 5.0, 6.0})})},
      {"details", Json::array({{{"source", "a"}}, {{"source", "b"}}})}};
  const auto result = grid(source); const auto page = result->page();
  EXPECT_EQ(result->row_count(), 2u); EXPECT_EQ(result->columns().size(), 2u);
  EXPECT_EQ(page.rows[0][0].type, AnalysisJsonType::Array); EXPECT_EQ(page.rows[0][0].child_count, 3u);
  EXPECT_EQ(page.rows[0][1].type, AnalysisJsonType::Object);
  auto selected = result->cell_path(0, 0); selected.emplace_back(size_t(1));
  EXPECT_EQ(joined(result->inspection()->scalar_text(selected)), "-2.0");
  EXPECT_THROW(result->inspection()->scalar_text(result->cell_path(0, 0)), std::invalid_argument);
  EXPECT_EQ(result->inspection()->children(result->cell_path(1, 1)).rows[0].value.preview, "\"b\"");
}

TEST(AnalysisTableGrid, NumericEmptyUnicodeAndEscapedColumnKeysKeepTheirIdentity)
{
  auto source = table(); source["column_names"] = Json::array({"10", "", "温度", "a/b~c"});
  source["columns"] = {{"a/b~c", Json::array({4})}, {"温度", Json::array({3})}, {"", Json::array({2})}, {"10", Json::array({1})}};
  source["units"] = {{"", "unspecified"}, {"温度", "K"}};
  const auto result = grid(source); const auto page = result->page();
  for (size_t column = 0; column < 4; ++column) { EXPECT_EQ(page.rows[0][column].preview, std::to_string(column + 1)); }
  EXPECT_EQ(result->columns()[0].label, "\"10\""); EXPECT_EQ(result->columns()[1].label, "\"\"");
  EXPECT_TRUE(result->columns()[1].has_unit); EXPECT_EQ(result->columns()[1].unit, "unspecified");
  const auto path = result->cell_path(0, 3);
  EXPECT_EQ(std::get<std::string>(path[3]), "a/b~c"); EXPECT_EQ(std::get<size_t>(path[4]), 0u);
  EXPECT_EQ(joined(result->inspection()->path_text(path)), "/outputs/table/columns/a~1b~0c/0");
  EXPECT_EQ(joined(result->inspection()->scalar_text(result->column_name_path(2))), "\"温度\"");
}

TEST(AnalysisTableGrid, ZeroColumnsAndZeroLengthColumnsAreLegitimate)
{
  const Json empty{{"type", "table"}, {"column_names", Json::array()}, {"columns", Json::object()}, {"units", Json::object()}};
  const auto result = grid(empty); const auto page = result->page();
  EXPECT_EQ(result->row_count(), 0u); EXPECT_TRUE(result->columns().empty());
  EXPECT_TRUE(page.rows.empty()); EXPECT_TRUE(page.columns.empty()); EXPECT_FALSE(page.next_row_offset); EXPECT_FALSE(page.next_column_offset);
  auto source = empty; source["column_names"] = Json::array({"x", "y"});
  source["columns"] = {{"x", Json::array()}, {"y", Json::array()}};
  const auto zero = grid(source); const auto zero_page = zero->page();
  EXPECT_EQ(zero->row_count(), 0u); EXPECT_EQ(zero_page.columns.size(), 2u); EXPECT_TRUE(zero_page.rows.empty());
  EXPECT_THROW(zero->cell_path(0, 0), std::invalid_argument);
}

TEST(AnalysisTableGrid, RowAndColumnPagingReachEveryOriginalCoordinate)
{
  auto source = table(); source["column_names"] = Json::array(); source["columns"] = Json::object(); source["units"] = Json::object();
  for (size_t column = 0; column < 10; ++column) {
    const auto name = "column" + std::to_string(column); source["column_names"].push_back(name);
    auto values = Json::array(); for (size_t row = 0; row < 130; ++row) { values.push_back(row * 100 + column); }
    source["columns"][name] = std::move(values);
  }
  const auto result = grid(source);
  auto page = result->page(); ASSERT_EQ(page.rows.size(), 64u); ASSERT_EQ(page.columns.size(), 8u);
  ASSERT_TRUE(page.next_row_offset); ASSERT_TRUE(page.next_column_offset);
  EXPECT_EQ(*page.next_row_offset, 64u); EXPECT_EQ(*page.next_column_offset, 8u);
  page = result->page(64, 0); EXPECT_EQ(page.rows[0][0].preview, "6400");
  EXPECT_EQ(page.rows[63][7].preview, "12707"); EXPECT_EQ(page.total_rows, 130u); EXPECT_EQ(page.total_columns, 10u);
  page = result->page(128, 8); ASSERT_EQ(page.rows.size(), 2u); EXPECT_EQ(page.columns, (std::vector<size_t>{8, 9}));
  EXPECT_EQ(page.rows[1][1].preview, "12909"); EXPECT_FALSE(page.next_row_offset); EXPECT_FALSE(page.next_column_offset);
  EXPECT_EQ(joined(result->inspection()->scalar_text(result->cell_path(129, 9))), "12909");
  EXPECT_EQ(result->page(0, 0).rows[0][0].preview, "0");
}

TEST(AnalysisTableGrid, PagesAndSelectedCoordinatesRejectInvalidBoundaries)
{
  const auto result = grid();
  EXPECT_TRUE(result->page(3, 0).rows.empty());
  const auto empty_columns = result->page(0, 2); EXPECT_TRUE(empty_columns.columns.empty());
  ASSERT_EQ(empty_columns.rows.size(), 3u); EXPECT_TRUE(empty_columns.rows[0].empty());
  EXPECT_EQ(result->page(1, 1, 1, 1).rows[0][0].preview, "1");
  EXPECT_THROW(result->page(4, 0), std::invalid_argument);
  EXPECT_THROW(result->page(0, 3), std::invalid_argument);
  EXPECT_THROW(result->page(0, 0, 0, 1), std::invalid_argument);
  EXPECT_THROW(result->page(0, 0, 65, 1), std::invalid_argument);
  EXPECT_THROW(result->page(0, 0, 1, 0), std::invalid_argument);
  EXPECT_THROW(result->page(0, 0, 1, 9), std::invalid_argument);
  EXPECT_THROW(result->cell_path(3, 0), std::invalid_argument);
  EXPECT_THROW(result->cell_path(0, 2), std::invalid_argument);
  EXPECT_THROW(result->column_name_path(2), std::invalid_argument);
  EXPECT_THROW(result->unit_path(2), std::invalid_argument);
  EXPECT_THROW(result->page(std::numeric_limits<size_t>::max(), 0), std::invalid_argument);
}

TEST(AnalysisTableGrid, DuplicateMissingExtraAndNonArrayColumnsNeverBecomePaddedTables)
{
  std::vector<Json> invalid;
  auto source = table(); source.erase("column_names"); invalid.push_back(source);
  source = table(); source["column_names"] = nullptr; invalid.push_back(source);
  source = table(); source["column_names"] = Json::array({"temperature", "temperature"}); invalid.push_back(source);
  source = table(); source["column_names"] = Json::array({"temperature", 1}); invalid.push_back(source);
  source = table(); source["column_names"] = Json::array({"temperature", "missing"}); invalid.push_back(source);
  source = table(); source["columns"]["extra"] = Json::array({1, 2, 3}); invalid.push_back(source);
  source = table(); source["columns"].erase("step"); invalid.push_back(source);
  source = table(); source["columns"]["step"] = 1; invalid.push_back(source);
  source = table(); source["columns"]["step"] = Json::array({1, 2}); invalid.push_back(source);
  source = table(); source["columns"] = Json::array(); invalid.push_back(source);
  source = table(); source["column_names"] = Json::array(); invalid.push_back(source);
  for (const auto &value : invalid) { EXPECT_THROW(grid(value), std::invalid_argument); }
}

TEST(AnalysisTableGrid, UnitMetadataIsValidatedWithoutInventingConversionsOrDefaults)
{
  auto source = table(); source["units"] = Json::object();
  const auto missing = grid(source);
  EXPECT_FALSE(missing->columns()[0].has_unit); EXPECT_FALSE(missing->columns()[1].has_unit);
  for (const Json &unit : {Json(), Json(1), Json(true), Json(""), Json::array(), Json::object()}) {
    source = table(); source["units"]["temperature"] = unit;
    EXPECT_THROW(grid(source), std::invalid_argument);
  }
  source = table(); source["units"]["unknown"] = "K";
  EXPECT_THROW(grid(source), std::invalid_argument);
  source = table(); source.erase("units");
  EXPECT_THROW(grid(source), std::invalid_argument);
  source = table(); source["units"] = nullptr;
  EXPECT_THROW(grid(source), std::invalid_argument);
  source = table(); source["units"]["temperature"] = "mK";
  const auto unchanged = grid(source);
  EXPECT_EQ(unchanged->page().rows[0][0].preview, "-9.5"); EXPECT_EQ(unchanged->columns()[0].unit, "mK");
}

TEST(AnalysisTableGrid, BlobAndUnsupportedOutputsRemainAvailableOnlyThroughTheirProperties)
{
  auto source = table(); source["blob"] = std::string(64, 'a');
  const auto model = inspection(source); const auto digest = model->encoded_sha256();
  EXPECT_THROW(Grid::from_output(model, "table"), std::invalid_argument);
  EXPECT_EQ(model->describe({std::string("outputs"), std::string("table"), std::string("blob")}).type, AnalysisJsonType::String);
  EXPECT_EQ(model->encoded_sha256(), digest);
  source["blob"] = nullptr;
  EXPECT_THROW(grid(source), std::invalid_argument);
  source = table(); source["type"] = "value";
  EXPECT_THROW(grid(source), std::invalid_argument);
  EXPECT_THROW(Grid::from_output(model, "missing"), std::invalid_argument);
  EXPECT_THROW(Grid::from_output(model, std::string(1024 * 1024, 'a')), std::invalid_argument);
  EXPECT_THROW(Grid::from_output(nullptr, "table"), std::invalid_argument);
}

TEST(AnalysisTableGrid, SentinelsRemainStringsAndColumnCellsMayHaveDifferentJsonTypes)
{
  auto source = table(); source["column_names"] = Json::array({"mixed"}); source["units"] = Json::object();
  source["columns"] = {{"mixed", Json::array({"NaN", "Inf", "-Inf", 1.0, nullptr})}};
  const auto result = grid(source); const auto page = result->page();
  for (size_t row = 0; row < 3; ++row) { EXPECT_EQ(page.rows[row][0].type, AnalysisJsonType::String); }
  EXPECT_EQ(page.rows[0][0].preview, "\"NaN\""); EXPECT_EQ(page.rows[3][0].type, AnalysisJsonType::Float);
  EXPECT_EQ(page.rows[4][0].type, AnalysisJsonType::Null);
}

TEST(AnalysisTableGrid, ExactLongNamesUnitsAndValuesHavePagedSelectedDetails)
{
  const std::string name(1024 * 1024, '~'), unit(128 * 1024, 'u'), value(10000, 'v');
  const Json source{{"type", "table"}, {"column_names", Json::array({name})},
      {"columns", {{name, Json::array({value})}}}, {"units", {{name, unit}}}};
  const auto result = grid(source); const auto page = result->page();
  ASSERT_EQ(result->columns().size(), 1u); EXPECT_EQ(result->columns()[0].name, name); EXPECT_EQ(result->columns()[0].unit, unit);
  EXPECT_TRUE(result->columns()[0].label_truncated); EXPECT_TRUE(result->unit_description(0).preview_truncated);
  EXPECT_LE(result->columns()[0].label.size(), 240u); EXPECT_LE(result->unit_description(0).preview.size(), 240u);
  EXPECT_TRUE(page.rows[0][0].preview_truncated); EXPECT_LE(page.rows[0][0].preview.size(), 240u);
  const auto exact_name = result->inspection()->scalar_text(result->column_name_path(0));
  const auto exact_unit = result->inspection()->scalar_text(result->unit_path(0));
  const auto exact_value = result->inspection()->scalar_text(result->cell_path(0, 0));
  EXPECT_GT(exact_name.pages.size(), 1u); EXPECT_GT(exact_unit.pages.size(), 1u); EXPECT_GT(exact_value.pages.size(), 1u);
  EXPECT_EQ(joined(exact_name), '"' + name + '"'); EXPECT_EQ(joined(exact_unit), '"' + unit + '"');
  EXPECT_EQ(joined(exact_value), '"' + value + '"');
}

TEST(AnalysisTableGrid, AdapterPinsModelLifetimeAndDoesNotCopyColumnValues)
{
  auto source = table(); auto model = inspection(source);
  const auto *original = &model->result(); const std::weak_ptr<const AnalysisResultInspection> weak = model;
  const auto result = Grid::from_output(model, "table"); model.reset();
  EXPECT_FALSE(weak.expired()); EXPECT_EQ(&result->inspection()->result(), original);
  source["columns"]["temperature"][0] = 999;
  EXPECT_EQ(result->page().rows[0][0].preview, "-9.5");
  EXPECT_EQ(result->inspection()->describe({std::string("outputs"), std::string("table"), std::string("attrs"), std::string("origin")}).preview, "\"test\"");
}

TEST(AnalysisTableGrid, InvalidReplacementDoesNotChangePreviouslyAcceptedGrid)
{
  const auto accepted = grid(); const auto hash = accepted->inspection()->encoded_sha256();
  auto invalid = table(); invalid["columns"]["step"].push_back(3);
  EXPECT_THROW(grid(invalid), std::invalid_argument);
  EXPECT_EQ(accepted->inspection()->encoded_sha256(), hash); EXPECT_EQ(accepted->row_count(), 3u);
  EXPECT_EQ(accepted->page().rows[2][0].preview, "14.5");
}

TEST(AnalysisTableGrid, ManyDeclaredEmptyColumnsAndUnitsAreIndexedInSourceOrder)
{
  auto source = table(); source["column_names"] = Json::array();
  source["columns"] = Json::object(); source["units"] = Json::object();
  constexpr size_t count = 2048;
  for (size_t i = 0; i < count; ++i) {
    source["column_names"].push_back("column" + std::to_string(i));
    const auto reverse = "column" + std::to_string(count - 1 - i);
    source["columns"][reverse] = Json::array(); source["units"][reverse] = "K";
  }
  const auto result = grid(source);
  ASSERT_EQ(result->columns().size(), count); EXPECT_EQ(result->row_count(), 0u);
  EXPECT_EQ(result->columns().front().name, "column0");
  EXPECT_EQ(result->columns().back().name, "column2047"); EXPECT_EQ(result->columns().back().unit, "K");
  const auto final = result->page(0, count - 8);
  EXPECT_TRUE(final.rows.empty()); ASSERT_EQ(final.columns.size(), 8u);
  EXPECT_EQ(final.columns.back(), count - 1); EXPECT_FALSE(final.next_column_offset);
  EXPECT_EQ(result->unit_description(count - 1).preview, "\"K\"");
}
} // namespace
} // namespace stk::app
