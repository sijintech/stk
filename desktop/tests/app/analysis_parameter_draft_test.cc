/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_parameter_draft.hh"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace stk::app {
namespace {
using io::Json;
using Draft = AnalysisParameterDraft;
constexpr auto identity = "04b4da9c-f614-477c-a7d9-18b58fd6f644";

Json definition(Json parameters = Json::object())
{
  return {{"format", "stk.analysis-document/1"},
      {"graph", {{"schema", "stk.graph/1"},
          {"parameters", Json::array({{{"name", "gain"}, {"type", "number"}, {"default", 2.0}}})},
          {"nodes", Json::array({{{"id", "source"}, {"type", "fixture.source.scalar@1"},
              {"params", {{"gain", {{"$param", "gain"}}}}}}})},
          {"outputs", {{"value", "source.value"}}}}},
      {"parameters", std::move(parameters)}, {"outputs", Json::array({"value"})}};
}

Draft draft(Json parameters = Json::object())
{
  Draft result;
  result.pin("project-opening", identity, 7, "Saved scalar", definition(std::move(parameters)));
  return result;
}

std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }

TEST(AnalysisParameterDraft, UnpinnedDraftRejectsEditsAndHasNoImplicitDocument)
{
  Draft model;
  EXPECT_FALSE(model.pinned()); EXPECT_FALSE(model.current("", -1)); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(model.revision(), -1); EXPECT_TRUE(model.baseline_document().is_null());
  EXPECT_TRUE(model.candidate_document().is_null()); EXPECT_EQ(model.parameters(), Json::object());
  EXPECT_FALSE(model.has_override("gain")); EXPECT_FALSE(model.override_value("gain"));
  EXPECT_FALSE(model.set("gain", 1, model.generation()).accepted);
  EXPECT_FALSE(model.set_text("gain", "1", Draft::TextMode::Json, model.generation()).accepted);
  EXPECT_FALSE(model.remove("gain", model.generation()).accepted);
  EXPECT_FALSE(model.revert(model.generation()));
  EXPECT_FALSE(model.matches(identity, "Saved scalar", definition()));
}

TEST(AnalysisParameterDraft, DetachedCopiesRetainUnknownKeysGraphOutputsAndSubmittedTypes)
{
  auto source = definition({{"gain", 1}, {"unknown/key", {{"nested", Json::array({nullptr, true, 1.0})}}}});
  Draft model; model.pin("project-opening", identity, 7, "Saved scalar", source);
  const auto original = exact(source);
  source["graph"]["nodes"].clear(); source["parameters"]["gain"] = 99; source["outputs"].clear();
  EXPECT_EQ(exact(model.baseline_document()), original);
  auto copy = model.candidate_document(); copy["parameters"]["unknown/key"] = 0;
  auto value = model.override_value("unknown/key"); ASSERT_TRUE(value); (*value)["nested"] = false;
  EXPECT_EQ(exact(model.candidate_document()), original);
  ASSERT_TRUE(model.set("gain", 3.0, model.generation()).accepted);
  const auto candidate = model.candidate_document();
  EXPECT_EQ(exact(candidate.at("graph")), exact(model.baseline_document().at("graph")));
  EXPECT_EQ(exact(candidate.at("outputs")), exact(model.baseline_document().at("outputs")));
  EXPECT_EQ(exact(candidate.at("parameters").at("unknown/key")),
            exact(model.baseline_document().at("parameters").at("unknown/key")));
  EXPECT_EQ(model.name(), "Saved scalar"); EXPECT_TRUE(model.dirty());
}

TEST(AnalysisParameterDraft, MissingNullEmptyStringAndTextNullRemainDifferent)
{
  auto model = draft(); const auto generation = model.generation();
  EXPECT_FALSE(model.has_override("gain")); // Default 2.0 is not a submitted value.
  EXPECT_FALSE(model.override_value("required"));
  ASSERT_TRUE(model.set("gain", nullptr, generation).accepted);
  ASSERT_TRUE(model.override_value("gain")); EXPECT_TRUE(model.override_value("gain")->is_null());
  ASSERT_TRUE(model.set_text("required", "", Draft::TextMode::LiteralString, generation).accepted);
  EXPECT_EQ(*model.override_value("required"), "");
  ASSERT_TRUE(model.set_text("required", "null", Draft::TextMode::LiteralString, generation).accepted);
  EXPECT_EQ(*model.override_value("required"), "null");
  ASSERT_TRUE(model.set_text("required", "null", Draft::TextMode::Json, generation).accepted);
  EXPECT_TRUE(model.override_value("required")->is_null());
  ASSERT_TRUE(model.remove("required", generation).accepted);
  EXPECT_FALSE(model.override_value("required"));
  EXPECT_EQ(model.candidate_document().at("graph").at("parameters").size(), 1u);
  EXPECT_EQ(model.candidate_document().at("graph").at("parameters")[0].at("default"), 2.0);
  ASSERT_TRUE(model.remove("gain", generation).accepted); EXPECT_FALSE(model.dirty());
}

TEST(AnalysisParameterDraft, IntegerFloatAndSignedZeroUseTypedEquality)
{
  auto model = draft({{"gain", 1}, {"zero", -0.0}, {"object", {{"a", 1}, {"b", 2.0}}}});
  const auto generation = model.generation(), initial = model.version();
  ASSERT_TRUE(model.set("object", Json{{"b", 2.0}, {"a", 1}}, generation).accepted);
  EXPECT_EQ(model.version(), initial); EXPECT_FALSE(model.dirty());
  ASSERT_TRUE(model.set("gain", 1.0, generation).accepted); EXPECT_TRUE(model.dirty());
  EXPECT_TRUE(model.override_value("gain")->is_number_float());
  ASSERT_TRUE(model.set("gain", 1, generation).accepted); EXPECT_FALSE(model.dirty());
  ASSERT_TRUE(model.set("zero", 0.0, generation).accepted); EXPECT_TRUE(model.dirty());
  ASSERT_TRUE(model.set_text("zero", "-0.0", Draft::TextMode::Json, generation).accepted);
  EXPECT_TRUE(std::signbit(model.override_value("zero")->get<double>())); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(model.generation(), generation); EXPECT_GT(model.version(), initial);
}

TEST(AnalysisParameterDraft, ExactIntegerBoundaryTokensNeverPassThroughDouble)
{
  auto model = draft(); const auto generation = model.generation();
  for (const std::string text : {"-9223372036854775808", "9223372036854775807", "18446744073709551615", "9007199254740993"}) {
    const auto edit = model.set_text("integer", text, Draft::TextMode::Json, generation);
    ASSERT_TRUE(edit.accepted) << edit.error;
    ASSERT_TRUE(model.override_value("integer")->is_number_integer());
    EXPECT_EQ(exact(*model.override_value("integer")), text);
  }
  EXPECT_EQ(model.override_value("integer")->get<uint64_t>(), UINT64_C(9007199254740993));
  for (const std::string text : {"-9223372036854775809", "18446744073709551616", "99999999999999999999999999999999"}) {
    const auto version = model.version();
    const auto edit = model.set_text("integer", text, Draft::TextMode::Json, generation);
    EXPECT_FALSE(edit.accepted) << text; EXPECT_FALSE(edit.error.empty());
    EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(*model.override_value("integer")), "9007199254740993");
  }
  ASSERT_TRUE(model.set_text("number", "1e20", Draft::TextMode::Json, generation).accepted);
  EXPECT_TRUE(model.override_value("number")->is_number_float());
  ASSERT_TRUE(model.set_text("tiny", "5e-324", Draft::TextMode::Json, generation).accepted);
  EXPECT_GT(model.override_value("tiny")->get<double>(), 0.0);
}

TEST(AnalysisParameterDraft, LiteralStringsPreserveWhitespaceQuotesBackslashesAndUnicode)
{
  auto model = draft();
  const std::string literal = "  \"温差\" \\ null\n\t ";
  ASSERT_TRUE(model.set_text("文字", literal, Draft::TextMode::LiteralString, model.generation()).accepted);
  ASSERT_TRUE(model.override_value("文字")); EXPECT_EQ(*model.override_value("文字"), literal);
  ASSERT_TRUE(model.set_text("literal", std::string("a\0b", 3), Draft::TextMode::LiteralString, model.generation()).accepted);
  EXPECT_EQ(model.override_value("literal")->get<std::string>(), std::string("a\0b", 3));
}

TEST(AnalysisParameterDraft, StrictJsonRejectsMalformedDuplicateTrailingAndNonfiniteWithoutMutation)
{
  auto model = draft({{"gain", 8}}); const auto version = model.version();
  for (const std::string text : {"", "plain text", "01", "true false", "1 trailing", "[1,]", "{\"a\":1,}",
          "{\"a\":1,\"a\":2}", "{\"a\":1,\"\\u0061\":2}", "{\"nested\":{\"\":1,\"\":2}}",
          "NaN", "Infinity", "-Infinity", "1e309", "\"\\ud800\"", "// comment\n1"}) {
    const auto result = model.set_text("gain", text, Draft::TextMode::Json, model.generation());
    EXPECT_FALSE(result.accepted) << text; EXPECT_FALSE(result.error.empty()) << text;
    EXPECT_EQ(*model.override_value("gain"), 8); EXPECT_EQ(model.version(), version); EXPECT_FALSE(model.dirty());
  }
  ASSERT_TRUE(model.set_text("gain", " {\"a\":1,\"nested\":{\"a\":2},\"list\":[null,false,3.0]} \n",
                             Draft::TextMode::Json, model.generation()).accepted);
  EXPECT_TRUE(model.override_value("gain")->at("list")[2].is_number_float());
}

TEST(AnalysisParameterDraft, InvalidUtf8AndTypedNonJsonValuesAreRejectedBeforeCopies)
{
  auto model = draft({{"gain", 8}}); const auto version = model.version();
  for (const auto &invalid : {std::string("\xff", 1), std::string("\xc0\xaf", 2), std::string("\xed\xa0\x80", 3)}) {
    EXPECT_FALSE(model.set_text("gain", invalid, Draft::TextMode::LiteralString, model.generation()).accepted);
    EXPECT_FALSE(model.set_text("gain", '"' + invalid + '"', Draft::TextMode::Json, model.generation()).accepted);
    EXPECT_FALSE(model.set("gain", Json(invalid), model.generation()).accepted);
    EXPECT_FALSE(model.set(invalid, 1, model.generation()).accepted);
    EXPECT_FALSE(model.remove(invalid, model.generation()).accepted);
  }
  EXPECT_FALSE(model.set_text("gain", "\xef\xbb\xbf" "1", Draft::TextMode::Json, model.generation()).accepted);
  for (const double invalid : {std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
                               std::numeric_limits<double>::quiet_NaN()}) {
    EXPECT_FALSE(model.set("gain", invalid, model.generation()).accepted);
  }
  EXPECT_FALSE(model.set("gain", Json::binary({1, 2}), model.generation()).accepted);
  EXPECT_FALSE(model.set("gain", Json(Json::value_t::discarded), model.generation()).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(*model.override_value("gain"), 8);
}

TEST(AnalysisParameterDraft, FullDocumentDepthIncludesParameterObjectAndKeys)
{
  auto model = draft();
  // document depth0 -> parameters1 -> value2 -> 62 arrays -> scalar depth64.
  const std::string accepted = std::string(62, '[') + "0" + std::string(62, ']');
  ASSERT_TRUE(model.set_text("nested", accepted, Draft::TextMode::Json, model.generation()).accepted);
  const auto saved = exact(model.parameters()); const auto version = model.version();
  for (const size_t count : {63u, 64u, 65u, 10000u}) {
    const auto rejected = model.set_text("nested", std::string(count, '[') + "0" + std::string(count, ']'),
                                         Draft::TextMode::Json, model.generation());
    EXPECT_FALSE(rejected.accepted) << count; EXPECT_FALSE(rejected.error.empty());
    EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(model.parameters()), saved);
  }
  Json object = Json::object();
  for (size_t i = 0; i < 62; ++i) { object = Json{{"key", std::move(object)}}; }
  ASSERT_TRUE(model.set("nested", object, model.generation()).accepted); // Empty object at depth64.
  Json keyed = Json{{"key", std::move(object)}};
  EXPECT_FALSE(model.set("nested", keyed, model.generation()).accepted); // Key at depth65.
}

TEST(AnalysisParameterDraft, ParameterByteBoundariesUseCanonicalUtf8AndRejectAtomically)
{
  auto model = draft(); const auto generation = model.generation();
  // {"a":"..."} is eight bytes plus the string's UTF-8 bytes.
  const std::string exact_fit(Draft::max_parameters_bytes - 8, 'x');
  ASSERT_TRUE(model.set("a", exact_fit, generation).accepted);
  EXPECT_EQ(io::canonical_json(model.parameters()).size(), Draft::max_parameters_bytes);
  const auto version = model.version();
  EXPECT_FALSE(model.set("a", exact_fit + "x", generation).accepted);
  EXPECT_FALSE(model.set("another", nullptr, generation).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(*model.override_value("a"), exact_fit);
  ASSERT_TRUE(model.remove("a", generation).accepted);
  // Escaping increases canonical size even when the raw text fits.
  EXPECT_FALSE(model.set_text("a", std::string(Draft::max_parameters_bytes / 2, '\n'),
                              Draft::TextMode::LiteralString, generation).accepted);
  EXPECT_FALSE(model.set_text("a", std::string(Draft::max_text_bytes + 1, ' '),
                              Draft::TextMode::Json, generation).accepted);
  ASSERT_TRUE(model.set_text("a", "温度", Draft::TextMode::LiteralString, generation).accepted);
  EXPECT_EQ(io::canonical_json(model.parameters()).size(), 14u);
}

TEST(AnalysisParameterDraft, TypedNegativeZeroArrayUsesCanonicalSizeNotASeparateRawParameterLimit)
{
  auto model = draft();
  Json values = Json::array();
  for (size_t i = 0; i < 15000; ++i) { values.push_back(-0.0); }
  ASSERT_LT(io::canonical_json(Json{{"a", values}}).size(), Draft::max_parameters_bytes);
  ASSERT_GT(io::python_json_dumps(Json{{"a", values}}, true, true).size(), Draft::max_parameters_bytes);
  const auto edit = model.set("a", values, model.generation());
  ASSERT_TRUE(edit.accepted) << edit.error;
  EXPECT_TRUE(std::signbit(model.override_value("a")->at(0).get<double>()));
  const auto version = model.version();
  const auto text = io::python_json_dumps(*model.override_value("a"), false, true);
  ASSERT_GT(text.size(), Draft::max_parameters_bytes);
  const auto roundtrip = model.set_text("a", text, Draft::TextMode::Json, model.generation());
  ASSERT_TRUE(roundtrip.accepted) << roundtrip.error;
  EXPECT_EQ(model.version(), version);
  EXPECT_EQ(exact(*model.override_value("a")), text);
}

TEST(AnalysisParameterDraft, OverrideCountLimitDoesNotDropUnknownKeysOrMaterializeDefaults)
{
  Json parameters = Json::object();
  for (size_t i = 0; i < Draft::max_overrides; ++i) { parameters["key" + std::to_string(i)] = i; }
  auto model = draft(parameters); const auto generation = model.generation();
  const auto version = model.version();
  EXPECT_FALSE(model.set("gain", 2.0, generation).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(model.parameters()), exact(parameters));
  ASSERT_TRUE(model.set("key0", true, generation).accepted);
  ASSERT_TRUE(model.remove("key1", generation).accepted);
  ASSERT_TRUE(model.set("gain", 3.0, generation).accepted);
  EXPECT_EQ(model.parameters().size(), 64u); EXPECT_FALSE(model.has_override("required"));
}

TEST(AnalysisParameterDraft, EmptyAndNonIdentifierKeysCanBeEditedRemovedAndReverted)
{
  auto model = draft({{"", nullptr}, {"参数/a~b", 1}}); const auto generation = model.generation();
  ASSERT_TRUE(model.has_override("")); EXPECT_TRUE(model.override_value("")->is_null());
  ASSERT_TRUE(model.set("", "null", generation).accepted);
  ASSERT_TRUE(model.remove("参数/a~b", generation).accepted);
  EXPECT_FALSE(model.has_override("参数/a~b"));
  ASSERT_TRUE(model.revert(generation)); EXPECT_FALSE(model.dirty());
  EXPECT_TRUE(model.override_value("")->is_null()); EXPECT_EQ(*model.override_value("参数/a~b"), 1);
}

TEST(AnalysisParameterDraft, SparseRevertAndNoOpsPreserveBaselineGeneration)
{
  auto model = draft({{"gain", 1}}); const auto generation = model.generation(), initial = model.version();
  ASSERT_TRUE(model.set("gain", 1, generation).accepted);
  ASSERT_TRUE(model.remove("not-submitted", generation).accepted);
  ASSERT_TRUE(model.revert(generation)); EXPECT_EQ(model.version(), initial);
  ASSERT_TRUE(model.set("gain", 2, generation).accepted);
  ASSERT_TRUE(model.set("new", nullptr, generation).accepted);
  ASSERT_TRUE(model.remove("new", generation).accepted);
  EXPECT_TRUE(model.dirty());
  ASSERT_TRUE(model.set("gain", 1, generation).accepted); EXPECT_FALSE(model.dirty());
  ASSERT_TRUE(model.remove("gain", generation).accepted); EXPECT_TRUE(model.dirty());
  ASSERT_TRUE(model.set("gain", 1, generation).accepted); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(model.generation(), generation); EXPECT_GT(model.version(), initial);
}

TEST(AnalysisParameterDraft, RepinResetAndStaleObservationsNeverRetargetLocalEdits)
{
  auto model = draft({{"gain", 1}}); const auto old = model.generation();
  ASSERT_TRUE(model.set("gain", 2, old).accepted);
  EXPECT_TRUE(model.current("project-opening", 7)); EXPECT_FALSE(model.current("project-opening", 8));
  EXPECT_FALSE(model.current("new-opening-same-project", 7));
  EXPECT_EQ(*model.override_value("gain"), 2); EXPECT_TRUE(model.dirty());
  model.pin("new-opening", identity, 8, "Saved scalar", definition({{"gain", 4}}));
  EXPECT_GT(model.generation(), old); EXPECT_FALSE(model.dirty());
  EXPECT_FALSE(model.set("gain", 9, old).accepted); EXPECT_FALSE(model.remove("gain", old).accepted);
  EXPECT_FALSE(model.set_text("gain", "9", Draft::TextMode::Json, old).accepted); EXPECT_FALSE(model.revert(old));
  EXPECT_EQ(*model.override_value("gain"), 4);
  const auto repinned = model.generation();
  model.reset(); EXPECT_GT(model.generation(), repinned); EXPECT_FALSE(model.pinned());
  EXPECT_FALSE(model.set("gain", 9, repinned).accepted);
  model.pin("new-opening", identity, 8, "Saved scalar", definition());
  EXPECT_FALSE(model.remove("gain", repinned).accepted);
}

TEST(AnalysisParameterDraft, FailedPinPreservesDirtyDraftAndIdentity)
{
  auto model = draft({{"gain", 1}}); ASSERT_TRUE(model.set("gain", 2, model.generation()).accepted);
  const auto original = exact(model.candidate_document());
  const auto generation = model.generation(), version = model.version();
  for (const auto &bad_id : {"wrong", "04B4da9c-f614-477c-a7d9-18b58fd6f644", "04b4da9cf614477ca7d918b58fd6f644"}) {
    EXPECT_THROW(model.pin("other", bad_id, 8, "Saved", definition()), std::invalid_argument);
  }
  EXPECT_THROW(model.pin("", identity, 8, "Saved", definition()), std::invalid_argument);
  EXPECT_THROW(model.pin("other", identity, -1, "Saved", definition()), std::invalid_argument);
  for (const auto &bad_name : {std::string(), std::string(" \t"), std::string("　"), std::string("a\0b", 3), std::string(257, 'a')}) {
    EXPECT_THROW(model.pin("other", identity, 8, bad_name, definition()), std::invalid_argument);
  }
  auto bad = definition(); bad["parameters"] = Json::array();
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", bad), std::invalid_argument);
  bad = definition(); bad["outputs"].push_back("value");
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", bad), std::invalid_argument);
  bad = definition(); bad["outputs"] = Json::array({"undeclared"});
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", bad), std::invalid_argument);
  bad = definition(); bad["extra"] = true;
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", bad), std::invalid_argument);
  EXPECT_EQ(model.generation(), generation); EXPECT_EQ(model.version(), version);
  EXPECT_EQ(exact(model.candidate_document()), original); EXPECT_EQ(model.handle(), "project-opening");
}

TEST(AnalysisParameterDraft, PinEnforcesGraphNodeParameterAndDocumentBoundsBeforeAdoption)
{
  auto model = draft(); const auto generation = model.generation();
  auto oversized = definition(); oversized["graph"]["description"] = std::string(Draft::max_graph_bytes, 'x');
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  oversized = definition(); oversized["graph"]["nodes"][0]["params"]["text"] = std::string(Draft::max_parameters_bytes, 'x');
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  oversized = definition(); oversized["graph"]["description"] = std::string(Draft::max_document_bytes, 'x');
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  oversized = definition(); oversized["parameters"]["bad"] = Json::binary({1});
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  oversized = definition();
  const auto node = oversized["graph"]["nodes"][0];
  oversized["graph"]["nodes"] = Json::array();
  for (size_t i = 0; i < 201; ++i) { auto copy = node; copy["id"] = "node" + std::to_string(i); oversized["graph"]["nodes"].push_back(copy); }
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  oversized = definition();
  oversized["graph"]["parameters"] = Json::array();
  for (size_t i = 0; i < 65; ++i) { oversized["graph"]["parameters"].push_back({{"name", "p" + std::to_string(i)}, {"type", "json"}, {"default", nullptr}}); }
  EXPECT_THROW(model.pin("other", identity, 8, "Saved", oversized), std::invalid_argument);
  EXPECT_EQ(model.generation(), generation); EXPECT_FALSE(model.dirty());
}

TEST(AnalysisParameterDraft, ReadBackMatchIsTypedFullDocumentObservationWithoutAdoption)
{
  auto model = draft({{"gain", 1}}); ASSERT_TRUE(model.set("gain", 2.0, model.generation()).accepted);
  const auto generation = model.generation(), version = model.version();
  auto observed = model.candidate_document();
  ASSERT_TRUE(model.matches(identity, "Saved scalar", observed));
  EXPECT_FALSE(model.matches("04b4da9c-f614-477c-a7d9-18b58fd6f645", "Saved scalar", observed));
  EXPECT_FALSE(model.matches(identity, "Renamed", observed));
  observed["parameters"]["gain"] = 2; EXPECT_FALSE(model.matches(identity, "Saved scalar", observed));
  observed = model.candidate_document(); observed["outputs"].clear();
  EXPECT_FALSE(model.matches(identity, "Saved scalar", observed));
  observed = model.candidate_document(); observed["graph"]["description"] = "Concurrent edit";
  EXPECT_FALSE(model.matches(identity, "Saved scalar", observed));
  EXPECT_FALSE(model.matches(identity, "Saved scalar", nullptr));
  EXPECT_EQ(model.revision(), 7); EXPECT_TRUE(model.dirty());
  EXPECT_EQ(model.generation(), generation); EXPECT_EQ(model.version(), version);
  EXPECT_EQ(model.baseline_document().at("parameters").at("gain"), 1);
}


Draft output_draft(Json parameters = Json::object(), Json requested = Json::array({"gamma", "alpha"}))
{
  auto document = definition(std::move(parameters));
  document["graph"]["outputs"] = {{"alpha", "source.value"}, {"beta", "source.value"}, {"gamma", "source.value"}};
  document["outputs"] = std::move(requested);
  Draft model;
  model.pin("project-opening", identity, 7, "Saved scalar", document);
  return model;
}

TEST(AnalysisOutputDraft, UnpinnedModelCannotSelectOutputsOrFabricateADocument)
{
  Draft model;
  EXPECT_EQ(model.outputs(), Json::array()); EXPECT_FALSE(model.output_selected("alpha"));
  EXPECT_FALSE(model.set_outputs(Json::array(), model.generation()).accepted);
  EXPECT_FALSE(model.set_output("alpha", true, model.generation()).accepted);
  EXPECT_FALSE(model.set_output("alpha", false, model.generation()).accepted);
  EXPECT_FALSE(model.dirty()); EXPECT_TRUE(model.candidate_document().is_null());
}

TEST(AnalysisOutputDraft, ExactInitialOrderAndReturnedArraysAreDetached)
{
  auto model = output_draft();
  const auto original = exact(model.baseline_document());
  EXPECT_EQ(model.outputs(), Json::array({"gamma", "alpha"}));
  EXPECT_TRUE(model.output_selected("gamma")); EXPECT_TRUE(model.output_selected("alpha"));
  EXPECT_FALSE(model.output_selected("beta")); EXPECT_FALSE(model.output_selected("unknown"));
  auto outputs = model.outputs(); outputs.clear();
  auto document = model.candidate_document(); document["outputs"] = Json::array({"beta"});
  EXPECT_EQ(exact(model.candidate_document()), original); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(model.name(), "Saved scalar"); EXPECT_EQ(model.analysis_id(), identity); EXPECT_EQ(model.revision(), 7);
}

TEST(AnalysisOutputDraft, TogglePreservesRemainingOrderAppendsAndRecognizesNoOps)
{
  auto model = output_draft();
  const auto generation = model.generation(), initial = model.version();
  ASSERT_TRUE(model.set_output("alpha", true, generation).accepted);
  ASSERT_TRUE(model.set_output("beta", false, generation).accepted);
  EXPECT_EQ(model.version(), initial); EXPECT_FALSE(model.dirty());
  ASSERT_TRUE(model.set_output("alpha", false, generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"gamma"})); EXPECT_TRUE(model.dirty());
  ASSERT_TRUE(model.set_output("beta", true, generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"gamma", "beta"}));
  ASSERT_TRUE(model.set_output("alpha", true, generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"gamma", "beta", "alpha"}));
  ASSERT_TRUE(model.set_output("beta", false, generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"gamma", "alpha"})); EXPECT_FALSE(model.dirty());
  const auto version = model.version();
  EXPECT_FALSE(model.set_output("unknown", false, generation).accepted);
  EXPECT_FALSE(model.set_output("unknown", true, generation).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(model.generation(), generation);
}

TEST(AnalysisOutputDraft, ExplicitReplacementOrderIsIntentAndNoOutputsNeverMeansAll)
{
  auto model = output_draft(); const auto generation = model.generation();
  ASSERT_TRUE(model.set_outputs(Json::array({"alpha", "gamma"}), generation).accepted);
  EXPECT_TRUE(model.dirty()); EXPECT_EQ(model.outputs(), Json::array({"alpha", "gamma"}));
  const auto version = model.version();
  ASSERT_TRUE(model.set_outputs(Json::array({"alpha", "gamma"}), generation).accepted);
  EXPECT_EQ(model.version(), version);
  ASSERT_TRUE(model.set_outputs(Json::array(), generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array()); EXPECT_EQ(model.candidate_document().at("outputs"), Json::array());
  EXPECT_FALSE(model.output_selected("alpha")); EXPECT_EQ(model.candidate_document().at("graph").at("outputs").size(), 3u);
  auto empty = output_draft(Json::object(), Json::array()); const auto clean_version = empty.version();
  ASSERT_TRUE(empty.set_outputs(Json::array(), empty.generation()).accepted);
  EXPECT_FALSE(empty.dirty()); EXPECT_EQ(empty.version(), clean_version);
  EXPECT_EQ(empty.outputs(), Json::array());
}

TEST(AnalysisOutputDraft, ClearingOutputsPreservesExactParameterTypesAndUnknownKeys)
{
  auto model = output_draft({{"", uint64_t(9007199254740993ULL)}, {"maximum", std::numeric_limits<uint64_t>::max()},
      {"minimum", std::numeric_limits<int64_t>::min()}, {"zero", -0.0}, {"null", nullptr}, {"text", "null"},
      {"unknown/path", Json::array({1, 1.0, nullptr})}});
  const auto parameters = exact(model.parameters()), graph = exact(model.baseline_document().at("graph"));
  ASSERT_TRUE(model.set("gain", 1.0, model.generation()).accepted);
  const auto changed_parameters = exact(model.parameters());
  ASSERT_TRUE(model.set_outputs(Json::array(), model.generation()).accepted);
  EXPECT_EQ(exact(model.parameters()), changed_parameters);
  EXPECT_EQ(exact(model.candidate_document().at("graph")), graph);
  ASSERT_TRUE(model.remove("gain", model.generation()).accepted);
  EXPECT_EQ(exact(model.parameters()), parameters); EXPECT_TRUE(model.outputs().empty()); EXPECT_TRUE(model.dirty());
}

TEST(AnalysisOutputDraft, ParameterSetRemoveAndRejectedRawTextPreserveOutputEdits)
{
  auto model = output_draft({{"gain", 1}}); const auto generation = model.generation();
  ASSERT_TRUE(model.set_outputs(Json::array({"beta"}), generation).accepted);
  ASSERT_TRUE(model.set("gain", 2.0, generation).accepted);
  ASSERT_TRUE(model.set_text("literal", "null", Draft::TextMode::LiteralString, generation).accepted);
  ASSERT_TRUE(model.set("nil", nullptr, generation).accepted);
  ASSERT_TRUE(model.remove("gain", generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"beta"}));
  EXPECT_TRUE(model.override_value("nil")->is_null()); EXPECT_EQ(*model.override_value("literal"), "null");
  const auto candidate = exact(model.candidate_document()); const auto version = model.version();
  EXPECT_FALSE(model.set_text("bad", "[1,", Draft::TextMode::Json, generation).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(model.candidate_document()), candidate);
  ASSERT_TRUE(model.revert(generation));
  EXPECT_EQ(*model.override_value("gain"), 1); EXPECT_FALSE(model.has_override("nil"));
  EXPECT_EQ(model.outputs(), Json::array({"gamma", "alpha"})); EXPECT_FALSE(model.dirty());
  const auto reverted = model.version(); ASSERT_TRUE(model.revert(generation)); EXPECT_EQ(model.version(), reverted);
}

TEST(AnalysisOutputDraft, InvalidArraysAndUnknownNamesRejectWithoutMutation)
{
  auto model = output_draft({{"gain", 1}});
  ASSERT_TRUE(model.set("gain", 2, model.generation()).accepted);
  ASSERT_TRUE(model.set_outputs(Json::array({"beta"}), model.generation()).accepted);
  const auto candidate = exact(model.candidate_document()); const auto version = model.version();
  for (const auto &invalid : {Json(), Json(true), Json("alpha"), Json::object(), Json::array({"alpha", "alpha"}),
       Json::array({"unknown"}), Json::array({nullptr}), Json::array({1}), Json::array({Json::object()}),
       Json::array({""}), Json::array({std::string("\xff", 1)}), Json::array({std::string(Draft::max_document_bytes, 'x')})}) {
    const auto result = model.set_outputs(invalid, model.generation());
    EXPECT_FALSE(result.accepted); EXPECT_FALSE(result.error.empty());
    EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(model.candidate_document()), candidate);
  }
  Json deep = 0;
  for (int i = 0; i < 10000; ++i) { deep = Json::array({std::move(deep)}); }
  EXPECT_FALSE(model.set_outputs(deep, model.generation()).accepted);
  EXPECT_FALSE(model.set_output(std::string(Draft::max_document_bytes, 'x'), false, model.generation()).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(exact(model.candidate_document()), candidate);
}

TEST(AnalysisOutputDraft, SelectsAtMost256DistinctDeclaredNamesEvenWhenGraphDeclaresMore)
{
  auto document = definition(); document["graph"]["outputs"] = Json::object(); document["outputs"] = Json::array();
  Json chosen = Json::array();
  for (size_t i = 0; i < 257; ++i) {
    const auto name = "output" + std::to_string(i);
    document["graph"]["outputs"][name] = "source.value";
    if (i < 256) { chosen.push_back(name); }
  }
  Draft model; model.pin("project-opening", identity, 7, "Saved scalar", document);
  ASSERT_TRUE(model.set_outputs(chosen, model.generation()).accepted);
  EXPECT_EQ(model.outputs(), chosen); EXPECT_EQ(model.outputs().size(), 256u);
  const auto version = model.version();
  EXPECT_FALSE(model.set_output("output256", true, model.generation()).accepted);
  chosen.push_back("output256"); EXPECT_FALSE(model.set_outputs(chosen, model.generation()).accepted);
  EXPECT_EQ(model.version(), version); EXPECT_EQ(model.outputs().size(), 256u);
  ASSERT_TRUE(model.set_output("output100", false, model.generation()).accepted);
  ASSERT_TRUE(model.set_output("output256", true, model.generation()).accepted);
  EXPECT_EQ(model.outputs().back(), "output256"); EXPECT_EQ(model.outputs().size(), 256u);
  ASSERT_TRUE(model.set_outputs(Json::array(), model.generation()).accepted); EXPECT_FALSE(model.dirty());
}

TEST(AnalysisOutputDraft, ParameterBoundsAreEnforcedOnTheCombinedCandidate)
{
  auto model = output_draft(); const auto generation = model.generation();
  ASSERT_TRUE(model.set_outputs(Json::array({"beta", "alpha"}), generation).accepted);
  const std::string exact_fit(Draft::max_parameters_bytes - 8, 'x');
  ASSERT_TRUE(model.set("a", exact_fit, generation).accepted);
  const auto candidate = exact(model.candidate_document()); const auto version = model.version();
  EXPECT_FALSE(model.set("a", exact_fit + "x", generation).accepted);
  EXPECT_FALSE(model.set("other", nullptr, generation).accepted);
  EXPECT_EQ(exact(model.candidate_document()), candidate); EXPECT_EQ(model.version(), version);
  ASSERT_TRUE(model.set_output("gamma", true, generation).accepted);
  EXPECT_EQ(model.outputs(), Json::array({"beta", "alpha", "gamma"}));
  EXPECT_EQ(*model.override_value("a"), exact_fit);
}

TEST(AnalysisOutputDraft, StaleCallbacksPinResetAndFailedPinKeepTheWholeDraftAtomic)
{
  auto model = output_draft(); const auto generation = model.generation();
  ASSERT_TRUE(model.set_outputs(Json::array({"beta"}), generation).accepted);
  ASSERT_TRUE(model.set("gain", 2, generation).accepted);
  const auto candidate = exact(model.candidate_document()); const auto version = model.version();
  EXPECT_FALSE(model.set_outputs(Json::array(), generation + 1).accepted);
  EXPECT_FALSE(model.set_output("beta", false, generation + 1).accepted);
  auto bad = definition(); bad["outputs"] = Json::array({"missing"});
  EXPECT_THROW(model.pin("other", identity, 8, "Changed", bad), std::invalid_argument);
  EXPECT_EQ(exact(model.candidate_document()), candidate); EXPECT_EQ(model.version(), version);
  model.pin("other", identity, 8, "Changed", definition({{"gain", 9}}));
  EXPECT_FALSE(model.dirty()); EXPECT_EQ(model.outputs(), Json::array({"value"}));
  EXPECT_FALSE(model.set_outputs(Json::array(), generation).accepted);
  EXPECT_FALSE(model.set_output("value", false, generation).accepted);
  EXPECT_EQ(*model.override_value("gain"), 9);
  const auto current = model.generation(); model.reset();
  EXPECT_FALSE(model.pinned()); EXPECT_FALSE(model.dirty()); EXPECT_EQ(model.outputs(), Json::array());
  EXPECT_FALSE(model.set_outputs(Json::array(), current).accepted);
}

TEST(AnalysisOutputDraft, ReadBackMatchingIncludesOutputOrderAndAllAcceptedParameterEdits)
{
  auto model = output_draft({{"gain", 1}});
  ASSERT_TRUE(model.set("gain", 2.0, model.generation()).accepted);
  ASSERT_TRUE(model.set_outputs(Json::array({"alpha", "gamma"}), model.generation()).accepted);
  auto candidate = model.candidate_document(); const auto version = model.version();
  EXPECT_TRUE(model.matches(identity, "Saved scalar", candidate));
  candidate["outputs"] = Json::array({"gamma", "alpha"});
  EXPECT_FALSE(model.matches(identity, "Saved scalar", candidate));
  candidate = model.candidate_document(); candidate["parameters"]["gain"] = 2;
  EXPECT_FALSE(model.matches(identity, "Saved scalar", candidate));
  candidate = model.candidate_document(); candidate["outputs"] = Json::array();
  EXPECT_FALSE(model.matches(identity, "Saved scalar", candidate));
  ASSERT_TRUE(model.set_outputs(Json::array(), model.generation()).accepted);
  EXPECT_TRUE(model.matches(identity, "Saved scalar", candidate));
  EXPECT_EQ(model.version(), version + 1); EXPECT_TRUE(model.dirty()); EXPECT_EQ(model.revision(), 7);
}

}  // namespace
}  // namespace stk::app

namespace stk::app {
namespace {
using io::Json;
using Draft = AnalysisParameterDraft;

Json linked_definition()
{
  // a -> f1 -> f2, a scene with a multi input, an aliased link and an extra link key.
  return {{"format", "stk.analysis-document/1"},
      {"graph", {{"schema", "stk.graph/1"},
          {"nodes", Json::array({
              {{"id", "a"}, {"type", "fixture.source.grid@1"}},
              {{"id", "f1"}, {"type", "fixture.filter.pass@1"}, {"inputs", {{"in", {{"from", "a.out"}}}}}},
              {{"id", "f2"}, {"type", "fixture.filter.pass@1"}, {"inputs", {{"in", {{"from", "f1.out"}}}}}, {"label", "keep"}},
              {{"id", "cam"}, {"type", "fixture.view.camera@1"}},
              {{"id", "scene"}, {"type", "fixture.view.scene@1"},
               {"inputs", {{"layers", Json::array({{{"from", "f2.out"}}})}, {"camera", {{"from", "cam.camera"}}},
                           {"aliased", {{"from", "f1.out"}, {"as", "x"}}}}}}})},
          {"outputs", {{"view", "scene.scene"}}}}},
      {"parameters", {{"gain", 1.0}}}, {"outputs", Json::array({"view"})}};
}
Draft linked()
{
  Draft result;
  result.pin("project-opening", identity, 9, "Linked", linked_definition());
  return result;
}

TEST(AnalysisLinkDraft, ReplacingOneLinkChangesOnlyThatInputAndKeepsEveryOtherByte)
{
  auto model = linked();
  EXPECT_FALSE(model.dirty()); EXPECT_FALSE(model.has_link_edits());
  EXPECT_EQ(model.link("f2", "in"), "f1.out"); EXPECT_EQ(model.baseline_link("f2", "in"), "f1.out");
  const auto version = model.version(), generation = model.generation();
  ASSERT_TRUE(model.set_link("f2", "in", std::string("a.out"), generation).accepted);
  EXPECT_TRUE(model.dirty()); EXPECT_TRUE(model.has_link_edits());
  EXPECT_EQ(model.version(), version + 1); EXPECT_EQ(model.generation(), generation);
  EXPECT_EQ(model.link("f2", "in"), "a.out"); EXPECT_EQ(model.baseline_link("f2", "in"), "f1.out");
  auto expected = linked_definition();
  expected["graph"]["nodes"][2]["inputs"]["in"] = {{"from", "a.out"}};
  EXPECT_EQ(exact(model.candidate_document()), exact(expected));
  EXPECT_EQ(exact(model.parameters()), exact(Json{{"gain", 1.0}}));  // the float stays a float
  EXPECT_EQ(model.outputs(), Json::array({"view"}));
  // Same value again is a no-op; the baseline value drops the edit.
  ASSERT_TRUE(model.set_link("f2", "in", std::string("a.out"), generation).accepted);
  EXPECT_EQ(model.version(), version + 1);
  ASSERT_TRUE(model.set_link("f2", "in", std::string("f1.out"), generation).accepted);
  EXPECT_FALSE(model.has_link_edits()); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(exact(model.candidate_document()), exact(linked_definition()));
}

TEST(AnalysisLinkDraft, DisconnectRemovesOnlyTheInputKeyAndUnlinkedInputsCanBeConnected)
{
  auto model = linked();
  ASSERT_TRUE(model.set_link("scene", "camera", std::nullopt, model.generation()).accepted);
  EXPECT_EQ(model.link("scene", "camera"), std::nullopt);
  auto expected = linked_definition();
  expected["graph"]["nodes"][4]["inputs"].erase("camera");
  EXPECT_EQ(exact(model.candidate_document()), exact(expected));
  // A node without an inputs object gains exactly one link; removing it restores the absence.
  EXPECT_TRUE(model.link_editable("cam", "extra"));
  ASSERT_TRUE(model.set_link("cam", "extra", std::string("a.out"), model.generation()).accepted);
  expected["graph"]["nodes"][3]["inputs"] = {{"extra", {{"from", "a.out"}}}};
  EXPECT_EQ(exact(model.candidate_document()), exact(expected));
  ASSERT_TRUE(model.set_link("cam", "extra", std::nullopt, model.generation()).accepted);
  EXPECT_EQ(model.link_edits().size(), 1u);
  EXPECT_FALSE(model.candidate_document()["graph"]["nodes"][3].contains("inputs"));
}

TEST(AnalysisLinkDraft, MultiAliasedUnknownShapeDuplicateAndMalformedTargetsStayReadOnly)
{
  auto document = linked_definition();
  document["graph"]["nodes"].push_back({{"id", "dup"}, {"type", "fixture.filter.pass@1"}});
  document["graph"]["nodes"].push_back({{"id", "dup"}, {"type", "fixture.filter.pass@1"}});
  document["graph"]["nodes"].push_back({{"id", "odd"}, {"type", "fixture.filter.pass@1"}, {"inputs", {{"in", {{"from", "a.out"}, {"note", 1}}}}}});
  Draft model; model.pin("project-opening", identity, 9, "Linked", document);
  const auto before = exact(model.candidate_document());
  const auto version = model.version(), generation = model.generation();
  EXPECT_FALSE(model.link_editable("scene", "layers"));   // a list (multi input)
  EXPECT_FALSE(model.link_editable("scene", "aliased"));  // "as" would be lost
  EXPECT_FALSE(model.link_editable("odd", "in"));         // unknown link key
  EXPECT_FALSE(model.link_editable("dup", "in"));         // ambiguous node id
  EXPECT_FALSE(model.link_editable("missing", "in"));
  EXPECT_FALSE(model.link_editable("f2", "Bad-Port"));
  for (const auto &[node, port] : std::vector<std::pair<std::string, std::string>>{
           {"scene", "layers"}, {"scene", "aliased"}, {"odd", "in"}, {"dup", "in"}, {"missing", "in"}, {"f2", "Bad-Port"}}) {
    EXPECT_FALSE(model.set_link(node, port, std::string("a.out"), generation).accepted) << node << "." << port;
    EXPECT_FALSE(model.set_link(node, port, std::nullopt, generation).accepted) << node << "." << port;
  }
  // Sources: malformed, unknown, ambiguous and self links are refused before validation.
  for (const auto *source : {"a", "a.", ".out", "a.out.x", "A.out", "missing.out", "dup.out", "f2.out"}) {
    EXPECT_FALSE(model.set_link("f2", "in", std::string(source), generation).accepted) << source;
  }
  EXPECT_EQ(model.version(), version); EXPECT_FALSE(model.dirty());
  EXPECT_EQ(exact(model.candidate_document()), before);
  // Port compatibility and cycles are not judged here: graph validation decides.
  EXPECT_TRUE(model.set_link("f1", "in", std::string("f2.out"), generation).accepted);
}

TEST(AnalysisLinkDraft, LinkEditsJoinParameterAndOutputEditsAndClearWithRevertPinAndStaleGenerations)
{
  auto model = linked();
  const auto generation = model.generation();
  ASSERT_TRUE(model.set_text("gain", "1e", Draft::TextMode::Json, generation).accepted == false);
  ASSERT_TRUE(model.set("gain", 3, generation).accepted);
  ASSERT_TRUE(model.set_output("view", false, generation).accepted);
  ASSERT_TRUE(model.set_link("f2", "in", std::string("a.out"), generation).accepted);
  const auto candidate = model.candidate_document();
  EXPECT_EQ(candidate.at("parameters").at("gain"), 3);
  EXPECT_TRUE(candidate.at("parameters").at("gain").is_number_integer());
  EXPECT_EQ(candidate.at("outputs"), Json::array());
  EXPECT_EQ(candidate.at("graph").at("nodes")[2].at("inputs").at("in"), Json({{"from", "a.out"}}));
  EXPECT_TRUE(model.matches(identity, "Linked", candidate));
  auto other = candidate; other["graph"]["nodes"][2]["inputs"]["in"] = {{"from", "f1.out"}};
  EXPECT_FALSE(model.matches(identity, "Linked", other));
  // A callback from before a re-pin cannot edit; revert clears every kind of edit.
  ASSERT_TRUE(model.revert(generation));
  EXPECT_FALSE(model.dirty()); EXPECT_FALSE(model.has_link_edits());
  ASSERT_TRUE(model.set_link("f2", "in", std::string("a.out"), generation).accepted);
  model.pin("project-opening", identity, 10, "Linked", linked_definition());
  EXPECT_FALSE(model.has_link_edits());
  EXPECT_FALSE(model.set_link("f2", "in", std::string("a.out"), generation).accepted);
  model.reset();
  EXPECT_FALSE(model.link_editable("f2", "in")); EXPECT_EQ(model.link("f2", "in"), std::nullopt);
}

TEST(AnalysisCandidateValidation, RepliesBindToTheLatestTicketAndCountOnlyForTheirExactKey)
{
  AnalysisCandidateValidation check;
  const AnalysisCandidateKey key{"opening", identity, "42:1", 9, 3, 5};
  EXPECT_FALSE(check.passed(key)); EXPECT_EQ(check.result(key), nullptr); EXPECT_FALSE(check.pending());
  const auto first = check.begin(key);
  EXPECT_TRUE(check.pending()); EXPECT_EQ(check.result(key), nullptr);
  const auto second = check.begin(key);
  EXPECT_FALSE(check.finish(first, {{"ok", true}, {"issues", Json::array()}}));  // stale ticket
  EXPECT_TRUE(check.pending());
  ASSERT_TRUE(check.finish(second, {{"ok", false}, {"issues", Json::array({{{"code", "cycle"}}})}}));
  ASSERT_NE(check.result(key), nullptr); EXPECT_FALSE(check.passed(key));
  EXPECT_EQ(check.result(key)->at("issues")[0].at("code"), "cycle");
  const auto third = check.begin(key);
  ASSERT_TRUE(check.finish(third, {{"ok", true}, {"issues", Json::array()}}));
  EXPECT_TRUE(check.passed(key));
  for (auto changed : {AnalysisCandidateKey{"other", identity, "42:1", 9, 3, 5},
                       AnalysisCandidateKey{"opening", "11111111-1111-4111-8111-111111111111", "42:1", 9, 3, 5},
                       AnalysisCandidateKey{"opening", identity, "43:2", 9, 3, 5},
                       AnalysisCandidateKey{"opening", identity, "42:1", 10, 3, 5},
                       AnalysisCandidateKey{"opening", identity, "42:1", 9, 4, 5},
                       AnalysisCandidateKey{"opening", identity, "42:1", 9, 3, 6}}) {
    EXPECT_FALSE(check.passed(changed)); EXPECT_EQ(check.result(changed), nullptr);
  }
  const auto fourth = check.begin(key);
  EXPECT_FALSE(check.passed(key));  // a new check replaces the old verdict
  EXPECT_FALSE(check.finish(fourth, {{"ok", "yes"}, {"issues", Json::array()}}));
  EXPECT_FALSE(check.passed(key)); EXPECT_FALSE(check.error(key).empty());
  const auto fifth = check.begin(key);
  ASSERT_TRUE(check.fail(fifth, "unavailable: restarted"));
  EXPECT_EQ(check.error(key), "unavailable: restarted"); EXPECT_FALSE(check.passed(key));
  check.reset();
  EXPECT_FALSE(check.finish(fifth, {{"ok", true}, {"issues", Json::array()}}));
  EXPECT_TRUE(check.error(key).empty());
}

}  // namespace
}  // namespace stk::app
