/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/project_table_view.hh"
#include "stk/core/utf8.hh"

#include <cstdint>

namespace stk::app {
namespace {
using io::Json;

Json included(Json value) { return {{"state", "included"}, {"value", std::move(value)}}; }
Json excluded(const std::string &reason = "value_limit")
{
  return {{"state", "omitted"}, {"reason", reason}, {"size_bytes", 12345}, {"sha256", std::string(64, 'a')}};
}

Json field(const std::string &id, const std::string &type = "json")
{
  return {{"id", id}, {"name", "Saved " + id}, {"type", type}, {"unit", type == "number" ? Json("K") : Json(nullptr)}};
}

Json record(const std::string &id, Json literals = Json::object(), Json definitions = Json::object(),
            Json evaluations = Json::object())
{
  return {{"id", id}, {"literals", std::move(literals)}, {"definitions", std::move(definitions)},
          {"evaluations", std::move(evaluations)}};
}

Json context(Json fields, Json records)
{
  Json field_ids = Json::array(), record_ids = Json::array();
  for (const auto &item : fields) { field_ids.push_back(item.at("id")); }
  for (const auto &item : records) { record_ids.push_back(item.at("id")); }
  return {{"id", "saved-context"}, {"source_revision", 7},
          {"selection", {{"table_id", "table"}, {"record_ids", record_ids}, {"field_ids", field_ids}}},
          {"content", {{"state", "included"}, {"value", {{"table", {{"id", "table"}, {"name", "Saved table"}}},
            {"fields", std::move(fields)}, {"records", std::move(records)}}}}}};
}

TEST(ProjectTableView, SearchUsesStableOriginalRowsLiteralUnicodeAndErrorText)
{
  ProjectTable table;
  table.fields = {{"text", "Do not search this title", "text", ""}, {"number", "Number", "integer", ""}};
  table.records = {
      {"record-AAA", {{"text", "Alpha 温度"}, {"number", INT64_MAX}}},
      {"record-BBB", {{"text", "ALPHABET"}}, {{"number", {{"kind", "expression"}}}},
       {{"number", {{"state", "error"}, {"error", {{"code", "missing_reference"}, {"message", "Missing SOURCE"}}}}}}},
      {"record-CCC", {{"text", "Γάμμα"}, {"number", 2}}},
  };
  EXPECT_EQ(project_table_rows(table, {}), (std::vector<int>{0, 1, 2}));
  EXPECT_EQ(project_table_rows(table, {"alpha"}), (std::vector<int>{0, 1}));
  EXPECT_EQ(project_table_rows(table, {"温度"}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"RECORD-bbb"}), (std::vector<int>{1}));
  EXPECT_EQ(project_table_rows(table, {"9223372036854775807"}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"source"}), (std::vector<int>{1}));
  EXPECT_EQ(project_table_rows(table, {"#missing_reference"}), (std::vector<int>{1}));
  EXPECT_EQ(project_table_rows(table, {"", true}), (std::vector<int>{1}));
  EXPECT_EQ(project_table_rows(table, {"alpha", true}), (std::vector<int>{1}));
  EXPECT_TRUE(project_table_rows(table, {"温度", true}).empty());
  EXPECT_TRUE(project_table_rows(table, {"γ"}).empty()) << "Only ASCII letters ignore case";
  EXPECT_TRUE(project_table_rows(table, {"title"}).empty()) << "Column names must not match every row";
  EXPECT_THROW(project_table_rows(table, {std::string(257, 'a')}), std::invalid_argument);
  EXPECT_THROW(project_table_rows(table, {std::string("\xc3", 1)}), std::invalid_argument);
  EXPECT_EQ(table.records[0].values.at("number").get<int64_t>(), INT64_MAX);
}

TEST(ProjectTableView, FilteringRespondsToValuesWithoutRenumberingRows)
{
  ProjectTable table;
  table.fields = {{"f", "Value", "text", ""}};
  table.records = {{"first", {{"f", "match"}}}, {"second", {{"f", "else"}}}};
  EXPECT_EQ(project_table_rows(table, {"match"}), (std::vector<int>{0}));
  table.records[0].values["f"] = "else";
  table.records[1].values["f"] = "match";
  EXPECT_EQ(project_table_rows(table, {"match"}), (std::vector<int>{1}));
  table.records.clear();
  EXPECT_TRUE(project_table_rows(table, {"match", true}).empty());
}

TEST(ProjectTableView, ValueSummariesKeepExactNumbersAndBoundUtf8AndNestedJson)
{
  EXPECT_EQ(project_value_summary(Json(INT64_MAX)), "9223372036854775807");
  EXPECT_EQ(project_value_summary(Json(INT64_MIN)), "-9223372036854775808");
  EXPECT_EQ(project_value_summary(Json(nullptr)), "null");
  EXPECT_EQ(project_value_summary(Json(false)), "false");
  EXPECT_EQ(project_value_summary(Json("a\nb\t\r")), "a\\nb\\t\\r");
  for (size_t maximum = 0; maximum < 24; ++maximum) {
    const auto summary = project_value_summary(Json("温度扫描🧪参数温度扫描"), maximum);
    EXPECT_LE(summary.size(), maximum);
    EXPECT_TRUE(core::utf8::is_valid(summary));
  }
  const Json huge = {{"nested", Json::array({{{"data", std::string(256 * 1024, 'x')}}})}};
  const auto summary = project_value_summary(huge);
  EXPECT_LE(summary.size(), 160u);
  EXPECT_TRUE(summary.ends_with("…"));
  EXPECT_EQ(huge.at("nested")[0].at("data").get_ref<const std::string &>().size(), 256 * 1024u);
}

TEST(ProjectTableView, BoundedJsonSummariesDoNotSerializeInvisibleArraySuffixOrDeepNesting)
{
  Json array = Json::array();
  for (int i = 0; i < 10000; ++i) { array.push_back(i); }
  // A deliberately unencodable sentinel proves that the invisible suffix is never serialized.
  array.push_back(std::string("\xc3", 1));
  EXPECT_THROW(array.dump(), Json::type_error);
  const auto summary = project_value_summary(array, 80);
  EXPECT_LE(summary.size(), 80u);
  EXPECT_TRUE(summary.starts_with("[0,1,2,"));
  EXPECT_TRUE(summary.ends_with("…"));
  EXPECT_TRUE(core::utf8::is_valid(summary));

  Json nested = std::string("\xc3", 1);
  for (int i = 0; i < 100; ++i) { nested = Json::array({std::move(nested)}); }
  const auto deep = project_value_summary(nested);
  EXPECT_LE(deep.size(), 160u);
  EXPECT_TRUE(deep.ends_with("…"));
  EXPECT_TRUE(core::utf8::is_valid(deep));
  const Json small = {{"a\"b", Json::array({1, "温度\n", nullptr, false})}};
  EXPECT_EQ(project_value_summary(small), small.dump());
}

TEST(ProjectTableView, QueriesDoNotInspectUnneededFieldsAfterAMatch)
{
  ProjectTable table;
  table.fields = {{"first", "First", "text", ""}, {"ignored", "Ignored", "json", ""}};
  table.records = {{"record-id", {{"first", "needle"}, {"ignored", {{"invalid", std::string("\xc3", 1)}}}}}};
  EXPECT_EQ(project_table_rows(table, {}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"record-id"}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"needle"}), (std::vector<int>{0}));
  table.records[0].definitions["first"] = {{"kind", "expression"}};
  table.records[0].evaluations["first"] = {
      {"state", "error"}, {"error", {{"code", "needle"}, {"message", "Needle error"}}}};
  EXPECT_EQ(project_table_rows(table, {"", true}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"record-id", true}), (std::vector<int>{0}));
  EXPECT_EQ(project_table_rows(table, {"needle", true}), (std::vector<int>{0}));
}

TEST(CapturedProjectTable, PreservesSelectedOrderMissingObjectsNullAndUnset)
{
  auto saved = context(Json::array({field("f1"), field("f2", "number")}),
                       Json::array({record("r1", {{"f1", included(nullptr)}}),
                                    record("r2", {{"f2", included(310)}})}));
  saved["selection"]["record_ids"] = Json::array({"r2", "missing-row", "r1"});
  saved["selection"]["field_ids"] = Json::array({"f2", "f1", "missing-field"});
  const auto before = saved;
  const auto view = project_context_table(saved);
  ASSERT_EQ(view.cells.size(), 9u);
  EXPECT_TRUE(view.omission_reason.empty());
  EXPECT_EQ(view.cells[0].record_id, "r2");
  EXPECT_EQ(view.cells[0].field_id, "f2");
  EXPECT_EQ(view.cells[0].field_name, "Saved f2");
  EXPECT_EQ(view.cells[0].type, "number");
  EXPECT_EQ(view.cells[0].unit, "K");
  EXPECT_EQ(view.cells[0].status, "literal");
  EXPECT_EQ(view.cells[0].value_text, "310");
  EXPECT_EQ(view.cells[1].status, "unset");
  EXPECT_FALSE(view.cells[1].details.contains("literal"));
  EXPECT_EQ(view.cells[2].field_id, "missing-field");
  EXPECT_EQ(view.cells[2].status, "missing_field");
  EXPECT_TRUE(view.cells[2].incomplete);
  EXPECT_EQ(view.cells[3].record_id, "missing-row");
  EXPECT_EQ(view.cells[3].status, "missing_record");
  EXPECT_EQ(view.cells[6].status, "unset");
  EXPECT_EQ(view.cells[7].status, "null");
  EXPECT_EQ(view.cells[7].value_text, "null");
  EXPECT_TRUE(view.cells[7].details.at("literal").at("value").is_null());
  EXPECT_EQ(saved, before);
  saved["content"]["value"]["table"] = nullptr;
  const auto missing = project_context_table(saved);
  ASSERT_EQ(missing.cells.size(), 9u);
  for (const auto &cell : missing.cells) { EXPECT_EQ(cell.status, "missing_table"); EXPECT_TRUE(cell.incomplete); }
}

TEST(CapturedProjectTable, UsesSavedEvaluationAndRetainsReferenceAndErrorDetails)
{
  const Json definition = included({{"kind", "reference"}, {"source", {{"record_id", "not-loaded"}, {"field_id", "outside-selection"}}}});
  const Json result = included({{"state", "ok"}, {"value", INT64_MAX}, {"unit", nullptr}, {"evaluated_revision", 3}});
  const Json error = included({{"state", "error"}, {"error", {{"code", "missing_reference"}, {"message", "Saved error text"}}}});
  auto saved = context(Json::array({field("f1", "integer"), field("f2")}),
      Json::array({record("r1", Json::object(), {{"f1", definition}, {"f2", definition}}, {{"f1", result}, {"f2", error}})}));
  const auto view = project_context_table(saved);
  ASSERT_EQ(view.cells.size(), 2u);
  EXPECT_EQ(view.cells[0].status, "evaluated");
  EXPECT_EQ(view.cells[0].value_text, "= 9223372036854775807");
  EXPECT_FALSE(view.cells[0].incomplete);
  EXPECT_EQ(view.cells[0].details.at("definition"), definition);
  EXPECT_EQ(view.cells[0].details.at("evaluation"), result);
  EXPECT_EQ(view.cells[1].status, "formula_error");
  EXPECT_EQ(view.cells[1].value_text, "#missing_reference");
  EXPECT_EQ(view.cells[1].details.at("evaluation"), error);
  saved["content"]["value"]["records"][0]["evaluations"].erase("f1");
  const auto unavailable = project_context_table(saved);
  EXPECT_EQ(unavailable.cells[0].status, "evaluation_unavailable");
  EXPECT_TRUE(unavailable.cells[0].incomplete);
  EXPECT_EQ(unavailable.cells[0].value_text, "—") << "No reference is resolved or formula evaluated";
}

TEST(CapturedProjectTable, OmissionsRemainInspectableAndWholeOmissionProducesNoFakeCells)
{
  const Json definition = included({{"kind", "expression"}, {"expression", "1 / 0"}, {"bindings", Json::object()}});
  const Json result = included({{"state", "ok"}, {"value", 12}, {"unit", nullptr}});
  auto saved = context(Json::array({field("literal"), field("unavailable"), field("large-result"), field("hidden-definition")}),
      Json::array({record("r1", {{"literal", excluded()}},
        {{"unavailable", definition}, {"large-result", definition}, {"hidden-definition", excluded()}},
        {{"unavailable", excluded("evaluation_unavailable")}, {"large-result", excluded()}, {"hidden-definition", result}})}));
  const auto view = project_context_table(saved);
  ASSERT_EQ(view.cells.size(), 4u);
  EXPECT_EQ(view.cells[0].status, "omitted");
  EXPECT_EQ(view.cells[0].details.at("literal"), excluded());
  EXPECT_EQ(view.cells[1].status, "evaluation_unavailable");
  EXPECT_EQ(view.cells[2].status, "omitted");
  EXPECT_EQ(view.cells[3].status, "evaluated");
  EXPECT_EQ(view.cells[3].value_text, "= 12");
  for (const auto &cell : view.cells) { EXPECT_TRUE(cell.incomplete); }
  saved["content"] = {{"state", "omitted"}, {"reason", "context_limit"}, {"size_bytes", 300000}, {"sha256", std::string(64, 'a')}};
  const auto omitted = project_context_table(saved);
  EXPECT_TRUE(omitted.cells.empty());
  EXPECT_EQ(omitted.omission_reason, "context_limit");
}

TEST(CapturedProjectTable, RequiresFullContentAndKeepsFullValuesBehindBoundedSummaries)
{
  const Json literal = included(Json{{"text", std::string(16000, 'x')}});
  auto saved = context(Json::array({field("f")}), Json::array({record("r", {{"f", literal}})}));
  const auto view = project_context_table(saved);
  ASSERT_EQ(view.cells.size(), 1u);
  EXPECT_LE(view.cells[0].value_text.size(), 160u);
  EXPECT_EQ(view.cells[0].details.at("literal"), literal);
  saved["content"].erase("value");
  EXPECT_THROW(project_context_table(saved), std::invalid_argument);
}

}  // namespace
}  // namespace stk::app
