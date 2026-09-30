/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_result_inspection.hh"
#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
using Model = AnalysisResultInspection;
Json requested() { return Json::array({"value"}); }
Json result(Json value = nullptr)
{
  return {{"schema", "stk.graph-result/1"}, {"outputs", {{"value", {{"type", "value"}, {"value", std::move(value)}}}}},
      {"errors", Json::array()}};
}
AnalysisJsonPath value_path() { return {std::string("outputs"), std::string("value"), std::string("value")}; }
std::string join(const AnalysisJsonText &text)
{
  std::string result;
  for (const auto &page : text.pages) { result += page; }
  return result;
}
Json nested(size_t count)
{
  Json value = 0;
  for (size_t i = 0; i < count; ++i) {
    auto next = Json::array(); next.push_back(std::move(value)); value = std::move(next);
  }
  return value;
}

TEST(AnalysisResultInspection, AllSevenKindsRemainOrderedAndMissingDeliveryIsExplicit)
{
  const Json names = Json::array({"table", "missing", "payload", "image", "value", "dataset", "plot", "file"});
  auto source = result(); source["outputs"] = Json::object();
  for (const char *type : {"payload", "image", "plot", "table", "value", "dataset", "file"}) {
    source["outputs"][type] = {{"type", type}};
  }
  source["outputs"]["value"]["value"] = nullptr;
  source["outputs"]["table"]["columns"] = {{"temperature", Json::array({-9.5, 0.0, 14.5})}};
  source["outputs"]["dataset"]["descriptor"] = {{"fields", Json::array({"temperature"})}};
  source["errors"] = Json::array({{{"code", "missing_file"}, {"node", "absent"}, {"message", "No input"}}});
  const auto model = Model::from_result(names, source);
  ASSERT_EQ(model->outputs().size(), names.size());
  for (size_t i = 0; i < names.size(); ++i) { EXPECT_EQ(model->outputs()[i].name, names[i].get<std::string>()); }
  EXPECT_FALSE(model->outputs()[1].delivered); EXPECT_TRUE(model->outputs()[1].delivery_type.empty());
  EXPECT_THROW(model->describe(model->outputs()[1].path), std::invalid_argument);
  EXPECT_EQ(model->outputs()[0].delivery_type, "table"); EXPECT_FALSE(model->outputs()[0].content_not_loaded);
  EXPECT_EQ(model->outputs()[2].delivery_type, "payload"); EXPECT_FALSE(model->outputs()[2].content_not_loaded);
  EXPECT_TRUE(model->outputs()[3].content_not_loaded); EXPECT_FALSE(model->outputs()[4].content_not_loaded);
  EXPECT_TRUE(model->outputs()[5].metadata_only); EXPECT_FALSE(model->outputs()[5].content_not_loaded);
  EXPECT_TRUE(model->outputs()[6].content_not_loaded); EXPECT_TRUE(model->outputs()[7].content_not_loaded);
}

TEST(AnalysisResultInspection, BlobTablesAndValuesRemainMetadataWithoutLoadingTheirContent)
{
  auto source = result();
  source["outputs"] = {{"table", {{"type", "table"}, {"blob", std::string(64, 'a')}, {"rows", 12},
      {"column_names", Json::array({"x", "y"})}, {"media_type", "application/json"}}},
      {"value", {{"type", "value"}, {"blob", std::string(64, 'b')}, {"size", 200}}}};
  const auto model = Model::from_result(Json::array({"table", "value"}), source);
  EXPECT_TRUE(model->outputs()[0].content_not_loaded); EXPECT_TRUE(model->outputs()[1].content_not_loaded);
  EXPECT_EQ(join(model->scalar_text({std::string("outputs"), std::string("table"), std::string("rows")})), "12");
  EXPECT_THROW(model->describe(value_path()), std::invalid_argument);
}

TEST(AnalysisResultInspection, NullAndUnknownDeliveryMetadataRemainVisibleWithoutCoercion)
{
  auto source = result(); source["outputs"] = {{"null_delivery", nullptr}, {"unknown", {{"type", "extension"}, {"data", true}}},
      {"wrong_type", {{"type", 17}}}};
  const auto model = Model::from_result(Json::array({"null_delivery", "unknown", "wrong_type", "missing"}), source);
  for (size_t i = 0; i < 3; ++i) { EXPECT_TRUE(model->outputs()[i].delivered); EXPECT_TRUE(model->outputs()[i].delivery_type.empty()); }
  EXPECT_EQ(model->describe(model->outputs()[0].path).type, AnalysisJsonType::Null);
  EXPECT_EQ(join(model->scalar_text(model->outputs()[0].path)), "null");
  EXPECT_FALSE(model->outputs()[3].delivered);
}

TEST(AnalysisResultInspection, EmptyExplicitSelectionAndEmptyContainersAreLegitimate)
{
  auto source = result(); source["outputs"] = Json::object();
  const auto model = Model::from_result(Json::array(), source);
  EXPECT_TRUE(model->outputs().empty()); EXPECT_TRUE(model->errors().present);
  EXPECT_EQ(model->errors().value.child_count, 0u); EXPECT_FALSE(model->warnings().present);
  const auto page = model->children({std::string("outputs")});
  EXPECT_EQ(page.total, 0u); EXPECT_TRUE(page.rows.empty()); EXPECT_FALSE(page.next_offset);
  EXPECT_EQ(join(model->path_text({})), ""); EXPECT_EQ(model->path_text({}).pages.size(), 1u);
}

TEST(AnalysisResultInspection, ScalarTypesAndScientificRepresentationsStayExact)
{
  struct Case { Json value; AnalysisJsonType type; std::string text; };
  const std::vector<Case> cases{
      {std::numeric_limits<int64_t>::min(), AnalysisJsonType::Integer, "-9223372036854775808"},
      {std::numeric_limits<uint64_t>::max(), AnalysisJsonType::UnsignedInteger, "18446744073709551615"},
      {1, AnalysisJsonType::Integer, "1"}, {uint64_t(1), AnalysisJsonType::UnsignedInteger, "1"},
      {1.0, AnalysisJsonType::Float, "1.0"}, {-0.0, AnalysisJsonType::Float, "-0.0"},
      {0.0, AnalysisJsonType::Float, "0.0"}, {1e-8, AnalysisJsonType::Float, "1e-08"},
      {true, AnalysisJsonType::Boolean, "true"}, {false, AnalysisJsonType::Boolean, "false"},
      {nullptr, AnalysisJsonType::Null, "null"}, {"", AnalysisJsonType::String, "\"\""},
      {"null", AnalysisJsonType::String, "\"null\""}, {"NaN", AnalysisJsonType::String, "\"NaN\""},
      {"Inf", AnalysisJsonType::String, "\"Inf\""}, {"-Inf", AnalysisJsonType::String, "\"-Inf\""}};
  for (const auto &item : cases) {
    const auto model = Model::from_result(requested(), result(item.value));
    EXPECT_EQ(model->describe(value_path()).type, item.type);
    EXPECT_EQ(model->describe(value_path()).preview, item.text);
    EXPECT_EQ(join(model->scalar_text(value_path())), item.text);
    EXPECT_FALSE(model->describe(value_path()).preview_truncated);
  }
}

TEST(AnalysisResultInspection, ExactEncodingHashMatchesIndependentPythonOracle)
{
  const auto source = result(Json::array({std::numeric_limits<uint64_t>::max(), std::numeric_limits<int64_t>::min(),
      1.0, -0.0, nullptr, true, false, "", "null", std::string("场 α\n\0", 8)}));
  // Python json.dumps(... ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).
  const auto model = Model::from_result(requested(), source);
  EXPECT_EQ(model->encoded_bytes(), 184u);
  EXPECT_EQ(model->encoded_sha256(), "d511e90718e3a092debebc4d04957bdc77d4f0f4b49f07db19cf6ea9b9d4c7b3");
  const auto canonical = io::canonical_json(source);
  EXPECT_NE(model->encoded_sha256(), core::Sha256::hex(canonical));
}

TEST(AnalysisResultInspection, LossyParsedLargeIntegerCannotMatchTheArchiveReceipt)
{
  const std::string archive = "{\"errors\":[],\"outputs\":{\"value\":{\"type\":\"value\",\"value\":18446744073709551617}},\"schema\":\"stk.graph-result/1\"}";
  const auto parsed = io::parse_json(archive);
  ASSERT_TRUE(parsed.at("outputs").at("value").at("value").is_number_float());
  const auto model = Model::from_result(requested(), parsed);
  EXPECT_NE(model->encoded_sha256(), core::Sha256::hex(archive));
  // Controller compares these hashes before publishing; model does not claim bigint precision.
}

TEST(AnalysisResultInspection, RawIssueDetailsAndPrimitiveIssueItemsAreAllReachable)
{
  auto source = result();
  source["errors"] = Json::array({{{"message", "Missing source"}, {"code", "io"}, {"node", "src"},
      {"path", "data/x.csv"}, {"details", {{"count", 4}}}, {"hint", "Check inputs"}, {"skipped", true}}, "raw text", nullptr, 9});
  source["warnings"] = Json::array({{{"types", Json::array({"table", "value"})}}});
  const auto model = Model::from_result(requested(), source);
  EXPECT_EQ(model->errors().value.child_count, 4u); EXPECT_EQ(model->warnings().value.child_count, 1u);
  const auto page = model->children(model->errors().path);
  EXPECT_EQ(page.rows[1].value.type, AnalysisJsonType::String); EXPECT_EQ(page.rows[2].value.type, AnalysisJsonType::Null);
  const AnalysisJsonPath path{std::string("errors"), size_t(0), std::string("details"), std::string("count")};
  EXPECT_EQ(join(model->scalar_text(path)), "4");
  EXPECT_EQ(model->children({std::string("errors"), size_t(0)}).total, 7u);
}

TEST(AnalysisResultInspection, ObjectKeysAndArrayIndicesHaveDistinctTypedPaths)
{
  const auto model = Model::from_result(requested(), result(Json{{"0", "object zero"}, {"a/b~c", Json::array({"array zero"})}, {"", false}}));
  auto path = value_path(); path.emplace_back(std::string("0"));
  EXPECT_EQ(join(model->scalar_text(path)), "\"object zero\"");
  path = value_path(); path.emplace_back(size_t(0));
  EXPECT_THROW(model->describe(path), std::invalid_argument);
  path = value_path(); path.emplace_back(std::string("a/b~c")); path.emplace_back(size_t(0));
  EXPECT_EQ(join(model->scalar_text(path)), "\"array zero\"");
  EXPECT_EQ(join(model->path_text(path)), "/outputs/value/value/a~1b~0c/0");
  const auto page = model->children(value_path());
  EXPECT_EQ(page.rows[0].label, "\"0\""); EXPECT_EQ(page.rows[2].label, "\"\"");
  EXPECT_EQ(std::get<std::string>(page.rows[0].component), "0");
  auto array_path = value_path(); array_path.emplace_back(std::string("a/b~c"));
  EXPECT_EQ(model->children(array_path).rows[0].label, "0");
}

TEST(AnalysisResultInspection, AllChildrenRemainReachableAcrossEqualSizedPages)
{
  auto value = Json::object();
  for (int i = 0; i < 130; ++i) { value["key" + std::to_string(i)] = 1000 - i; }
  const auto model = Model::from_result(requested(), result(value));
  auto page = model->children(value_path());
  ASSERT_EQ(page.rows.size(), 64u); ASSERT_TRUE(page.next_offset); EXPECT_EQ(*page.next_offset, 64u);
  EXPECT_EQ(std::get<std::string>(page.rows.front().component), "key0");
  page = model->children(value_path(), *page.next_offset);
  ASSERT_EQ(page.rows.size(), 64u); EXPECT_EQ(std::get<std::string>(page.rows.front().component), "key64");
  EXPECT_EQ(page.rows.front().value.preview, "936"); ASSERT_TRUE(page.next_offset);
  page = model->children(value_path(), *page.next_offset);
  ASSERT_EQ(page.rows.size(), 2u); EXPECT_EQ(std::get<std::string>(page.rows.back().component), "key129"); EXPECT_FALSE(page.next_offset);
  EXPECT_TRUE(model->children(value_path(), 130).rows.empty());
  EXPECT_EQ(model->children(value_path(), 129, 1).rows.size(), 1u);
  EXPECT_THROW(model->children(value_path(), 131), std::invalid_argument);
  EXPECT_THROW(model->children(value_path(), 0, 0), std::invalid_argument);
  EXPECT_THROW(model->children(value_path(), 0, 65), std::invalid_argument);
}

TEST(AnalysisResultInspection, ExactScalarChunksPreserveUtf8AndCompleteJsonEscapes)
{
  std::string value;
  for (int i = 0; i < 2000; ++i) { value += std::string("场\n\\\0α", 8); }
  const auto model = Model::from_result(requested(), result(value));
  const auto pages = model->scalar_text(value_path());
  ASSERT_GT(pages.pages.size(), 2u); EXPECT_EQ(join(pages), io::python_json_dumps(Json(value), true, true));
  EXPECT_EQ(join(pages).size(), pages.total_bytes);
  for (const auto &page : pages.pages) {
    EXPECT_LE(page.size(), Model::scalar_page_bytes); EXPECT_TRUE(core::utf8::is_valid(page));
    for (size_t offset = 0; offset < page.size();) {
      if (page[offset] == '\\') {
        ASSERT_LT(offset + 1, page.size());
        const size_t width = page[offset + 1] == 'u' ? 6 : 2;
        ASSERT_LE(offset + width, page.size()); offset += width;
      }
      else { offset += core::utf8::decode(page, offset).length; }
    }
  }
  const auto preview = model->describe(value_path());
  EXPECT_TRUE(preview.preview_truncated); EXPECT_LE(preview.preview.size(), Model::preview_bytes);
  EXPECT_TRUE(core::utf8::is_valid(preview.preview));
}

TEST(AnalysisResultInspection, EscapingAndPreviewLimitsDoNotSilentlyDropShortValues)
{
  const auto value = std::string("\"\\\b\f\n\r\t\0", 8);
  const auto model = Model::from_result(requested(), result(value));
  EXPECT_EQ(join(model->scalar_text(value_path())), "\"\\\"\\\\\\b\\f\\n\\r\\t\\u0000\"");
  EXPECT_EQ(model->describe(value_path()).preview, join(model->scalar_text(value_path())));
  for (size_t n : {size_t(237), size_t(238), size_t(239), size_t(240)}) {
    const auto sample = Model::from_result(requested(), result(std::string(n, 'x')));
    const auto preview = sample->describe(value_path());
    EXPECT_EQ(preview.preview_truncated, n + 2 > Model::preview_bytes);
    EXPECT_LE(preview.preview.size(), Model::preview_bytes);
  }
}

TEST(AnalysisResultInspection, LargeKeysAreCopiedOncePerRowWithoutRepeatingAncestorPaths)
{
  const std::string key(1024 * 1024, '~');
  const auto model = Model::from_result(requested(), result(Json{{key, { {"child", 1} }}}));
  auto page = model->children(value_path());
  ASSERT_EQ(page.rows.size(), 1u); EXPECT_TRUE(page.rows[0].label_truncated);
  EXPECT_EQ(std::get<std::string>(page.rows[0].component), key);
  auto path = value_path(); path.push_back(page.rows[0].component);
  const auto nested_page = model->children(path);
  EXPECT_EQ(std::get<std::string>(nested_page.rows[0].component), "child");
  const auto pointer = model->path_text(path);
  EXPECT_EQ(pointer.total_bytes, std::string("/outputs/value/value/").size() + 2 * key.size());
  for (const auto &chunk : pointer.pages) { EXPECT_LE(chunk.size(), 4096u); }
  EXPECT_TRUE(join(pointer).starts_with("/outputs/value/value/~0~0"));
}

TEST(AnalysisResultInspection, RootAndRequestedSelectionAreStrictlyBounded)
{
  for (const Json &invalid : {Json(), Json::object(), Json::array({"value", "value"}), Json::array({1}),
       Json::array({"Bad"}), Json::array({""}), Json::array({std::string(65, 'a')})}) {
    EXPECT_THROW(Model::from_result(invalid, result()), std::invalid_argument);
  }
  auto names = Json::array(); auto source = result(); source["outputs"] = Json::object();
  for (int i = 0; i < 256; ++i) { names.push_back("output" + std::to_string(i)); }
  EXPECT_NO_THROW(Model::from_result(names, source));
  names.push_back("extra"); EXPECT_THROW(Model::from_result(names, source), std::invalid_argument);
  for (const Json &invalid : {Json(), Json::array(), Json{{"schema", "other"}, {"outputs", Json::object()}},
       Json{{"schema", "stk.graph-result/1"}, {"outputs", Json::array()}}}) {
    EXPECT_THROW(Model::from_result(requested(), invalid), std::invalid_argument);
  }
  source = result(); source["outputs"]["unrequested"] = nullptr;
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
}

TEST(AnalysisResultInspection, DepthPreflightRejectsBeforeRecursiveCopyOrSerialization)
{
  auto valid = result(nested(61)); // root/outputs/value/value leaf at depth64
  EXPECT_NO_THROW(Model::from_result(requested(), valid));
  auto invalid = result(nested(62));
  EXPECT_THROW(Model::from_result(requested(), invalid), std::invalid_argument);
  auto deep = nested(10000);
  EXPECT_THROW(Model::from_result(requested(), deep), std::invalid_argument);
  // Object keys also occur one level below their container.
  valid = result(Json::object());
  auto value = Json{{"last", 0}};
  for (int i = 0; i < 61; ++i) { auto parent = Json::array(); parent.push_back(std::move(value)); value = std::move(parent); }
  valid["outputs"]["value"]["value"] = std::move(value);
  EXPECT_THROW(Model::from_result(requested(), valid), std::invalid_argument);
}

TEST(AnalysisResultInspection, InvalidUtf8NonfiniteAndNonJsonValuesAreRejected)
{
  for (const Json &value : {Json(std::numeric_limits<double>::infinity()), Json(-std::numeric_limits<double>::infinity()),
       Json(std::numeric_limits<double>::quiet_NaN()), Json(std::string("\xff", 1)), Json::binary({1, 2}), Json(Json::value_t::discarded)}) {
    EXPECT_THROW(Model::from_result(requested(), result(value)), std::invalid_argument);
  }
  auto source = result(); source[std::string("\xff", 1)] = 1;
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
  source = result(); source["unused"] = std::numeric_limits<double>::infinity();
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
}

TEST(AnalysisResultInspection, ExactFourMiBLimitCountsFloatsDelimitersAndEscaping)
{
  auto value = Json::array();
  for (int i = 0; i < 15000; ++i) { value.push_back(-0.0); }
  auto source = result(value); source["padding"] = "";
  const auto initial_size = io::python_json_dumps(source, true, true).size();
  source["padding"] = std::string(Model::max_result_bytes - initial_size, 'x');
  const auto model = Model::from_result(requested(), source);
  EXPECT_EQ(model->encoded_bytes(), Model::max_result_bytes);
  EXPECT_LT(io::canonical_json(source).size(), Model::max_result_bytes);
  source["padding"].get_ref<std::string &>().push_back('x');
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
  source = result(std::string(Model::max_result_bytes / 6, '\0'));
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
  source = result(); source[std::string(Model::max_result_bytes, 'k')] = 0;
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
  source = result(std::string(Model::max_result_bytes + 1, 'v'));
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
}

TEST(AnalysisResultInspection, PublicPathsAndPrimitiveNavigationAreRevalidated)
{
  const auto model = Model::from_result(requested(), result(Json::array({1})));
  auto path = value_path(); path.emplace_back(size_t(1));
  EXPECT_THROW(model->describe(path), std::invalid_argument);
  path = value_path(); path.emplace_back(std::string("0"));
  EXPECT_THROW(model->describe(path), std::invalid_argument);
  path = value_path(); path.emplace_back(size_t(0));
  EXPECT_THROW(model->children(path), std::invalid_argument);
  EXPECT_THROW(model->scalar_text(value_path()), std::invalid_argument);
  EXPECT_THROW(model->describe({std::string("missing")}), std::invalid_argument);
  EXPECT_THROW(model->describe({std::string(Model::max_result_bytes + 1, 'k')}), std::invalid_argument);
  EXPECT_THROW(model->describe({std::string("\xff", 1)}), std::invalid_argument);
  EXPECT_THROW(model->describe(AnalysisJsonPath(65, size_t(0))), std::invalid_argument);
}

TEST(AnalysisResultInspection, AcceptedSnapshotRemainsDetachedAndUnaffectedByInvalidReplacement)
{
  auto source = result(Json{{"a", 1.0}}); auto names = requested();
  const auto model = Model::from_result(names, source);
  const auto hash = model->encoded_sha256();
  source["outputs"]["value"]["value"]["a"] = 7; names.clear();
  EXPECT_EQ(join(model->scalar_text({std::string("outputs"), std::string("value"), std::string("value"), std::string("a")})), "1.0");
  EXPECT_EQ(model->outputs().size(), 1u);
  source["outputs"] = nullptr;
  EXPECT_THROW(Model::from_result(requested(), source), std::invalid_argument);
  EXPECT_EQ(model->encoded_sha256(), hash);
  EXPECT_EQ(model->children(value_path()).rows[0].value.preview, "1.0");
}
} // namespace
} // namespace stk::app
