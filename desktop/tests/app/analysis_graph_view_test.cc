/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_view.hh"
#include "stk/core/utf8.hh"
#include "stk/io/catalog.hh"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;

io::PortSpec port(std::string name, bool multi = false)
{
  io::PortSpec result;
  result.name = std::move(name);
  result.types = {"dataset"};
  result.accepts = {"image", "polydata"};
  result.required = !multi;
  result.multi = multi;
  return result;
}

io::Catalog catalog()
{
  io::Catalog result;
  io::NodeType source;
  source.id = "stk.source.data@1";
  source.title_en = "Data source";
  source.title_zh = "数据来源";
  source.stage = "source";
  source.outputs = {port("out")};
  io::NodeType filter;
  filter.id = "stk.filter.transform@1";
  filter.stage = "data";
  filter.inputs = {port("in"), port("extras", true)};
  filter.outputs = {port("out")};
  io::NodeType sink;
  sink.id = "stk.output.result@1";
  sink.stage = "output";
  sink.inputs = {port("in"), port("extras", true)};
  sink.outputs = {port("out")};
  result.nodes = {source, filter, sink};
  return result;
}

Json node(const std::string &id, const std::string &family = "filter", Json inputs = Json::object())
{
  const std::string name = family == "source" ? "data" : family == "output" ? "result" : "transform";
  return {{"id", id}, {"type", "stk." + family + "." + name + "@1"}, {"inputs", std::move(inputs)}};
}

io::Graph graph(Json nodes, Json outputs = {{"result", "end.out"}})
{
  return io::Graph::from_json({{"schema", "stk.graph/1"}, {"nodes", std::move(nodes)}, {"outputs", std::move(outputs)}});
}

const AnalysisGraphParameter &parameter(const AnalysisGraphNode &node, const std::string &name)
{
  const auto found = std::find_if(node.parameters.begin(), node.parameters.end(), [&](const auto &item) { return item.name == name; });
  if (found == node.parameters.end()) { throw std::logic_error("Missing test parameter"); }
  return *found;
}

bool has_issue(const AnalysisGraphView &view, const std::string &code)
{
  return std::any_of(view.issues.begin(), view.issues.end(), [&](const auto &item) { return item.code == code; });
}

TEST(AnalysisGraphView, LayeredDagRetainsDocumentOrderAndUsesDeclaredTypedSocketPositions)
{
  const auto types = catalog();
  const auto source = graph(Json::array({
      node("end", "output", {{"in", {{"from", "middle.out"}}}}),
      node("middle", "filter", {{"in", {{"from", "start.out"}}}}),
      node("start", "source"), node("independent", "source")}));
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.nodes.size(), 4u);
  EXPECT_EQ(view.nodes[0].id, "end");
  EXPECT_EQ(view.nodes[1].id, "middle");
  EXPECT_EQ(view.nodes[2].id, "start");
  EXPECT_LT(view.nodes[2].rect.x, view.nodes[1].rect.x);
  EXPECT_LT(view.nodes[1].rect.x, view.nodes[0].rect.x);
  EXPECT_EQ(view.nodes[2].rect.x, view.nodes[3].rect.x);
  EXPECT_LT(view.nodes[2].rect.y, view.nodes[3].rect.y);
  EXPECT_EQ(view.nodes[2].title_zh, "数据来源");
  EXPECT_EQ(view.nodes[2].stage, "source");
  ASSERT_EQ(view.nodes[0].inputs.size(), 2u);
  EXPECT_EQ(view.nodes[0].inputs[0].name, "in");
  EXPECT_EQ(view.nodes[0].inputs[1].name, "extras");
  EXPECT_TRUE(view.nodes[0].inputs[0].required);
  EXPECT_TRUE(view.nodes[0].inputs[1].multi);
  EXPECT_EQ(view.nodes[0].inputs[0].type_text, "dataset (image | polydata)");
  ASSERT_EQ(view.edges.size(), 2u);
  EXPECT_EQ(view.edges[0].source, 1);
  EXPECT_EQ(view.edges[0].target, 0);
  EXPECT_EQ(view.edges[0].from, view.nodes[1].outputs[0].point);
  EXPECT_EQ(view.edges[0].to, view.nodes[0].inputs[0].point);
  EXPECT_TRUE(view.edges[0].diagnostic.empty());
  EXPECT_EQ(view.nodes[0].inputs[0].point.x, view.nodes[0].rect.x);
  EXPECT_EQ(view.nodes[1].outputs[0].point.x, view.nodes[1].rect.x + view.nodes[1].rect.width);
  EXPECT_EQ(view.outputs[0].node_index, 0);
  EXPECT_TRUE(view.outputs[0].diagnostic.empty());
  EXPECT_TRUE(view.issues.empty());
  const auto again = analysis_graph_view(source, &types);
  EXPECT_EQ(again.bounds, view.bounds);
  for (size_t i = 0; i < view.nodes.size(); ++i) { EXPECT_EQ(again.nodes[i].rect, view.nodes[i].rect); }
}

TEST(AnalysisGraphView, OrderedMultiInputsPreserveDuplicateLinksAliasesAndTheirOriginalIndices)
{
  const auto types = catalog();
  const auto source = graph(Json::array({node("a", "source"), node("b", "source"),
      node("end", "output", {{"extras", Json::array({{{"from", "b.out"}, {"as", "right"}},
          {{"from", "a.out"}, {"as", "left"}}, {{"from", "b.out"}, {"as", "again"}}})}})}));
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.edges.size(), 3u);
  EXPECT_EQ(view.edges[0].source_node, "b");
  EXPECT_EQ(view.edges[1].source_node, "a");
  EXPECT_EQ(view.edges[2].source_node, "b");
  EXPECT_EQ(view.edges[0].alias, "right");
  EXPECT_EQ(view.edges[1].alias, "left");
  EXPECT_EQ(view.edges[2].alias, "again");
  for (size_t i = 0; i < 3; ++i) {
    EXPECT_EQ(view.edges[i].link_index, i);
    EXPECT_EQ(view.edges[i].input, 1);
    EXPECT_EQ(view.edges[i].to, view.nodes[2].inputs[1].point);
  }
  EXPECT_EQ(view.nodes[1].outputs.size(), 1u);
}

TEST(AnalysisGraphView, UnknownTypesKeepParametersAndInferredPortsWithoutClaimingValidation)
{
  auto unknown = node("private_node");
  unknown["type"] = "plugin.filter.unavailable@3";
  unknown["inputs"] = {{"custom_in", {{"from", "start.out"}}}};
  unknown["params"] = {{"choice", false}};
  const auto types = catalog();
  const auto source = graph(Json::array({node("start", "source"), unknown,
      node("end", "output", {{"in", {{"from", "private_node.custom_out"}}}})}));
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.nodes.size(), 3u);
  const auto &item = view.nodes[1];
  EXPECT_FALSE(item.known_type);
  EXPECT_EQ(item.type, "plugin.filter.unavailable@3");
  ASSERT_EQ(item.inputs.size(), 1u);
  ASSERT_EQ(item.outputs.size(), 1u);
  EXPECT_EQ(item.inputs[0].name, "custom_in");
  EXPECT_EQ(item.outputs[0].name, "custom_out");
  EXPECT_FALSE(item.inputs[0].declared);
  EXPECT_EQ(item.inputs[0].type_text, "?");
  EXPECT_EQ(parameter(item, "choice").value_text, "false");
  EXPECT_FALSE(parameter(item, "choice").declared);
  EXPECT_EQ(view.edges[0].diagnostic, "unknown_type");
  EXPECT_EQ(view.edges[1].diagnostic, "unknown_type");
  EXPECT_TRUE(has_issue(view, "unknown_type"));
  const auto without_catalog = analysis_graph_view(source);
  EXPECT_EQ(without_catalog.nodes.size(), 3u);
  EXPECT_FALSE(without_catalog.nodes[0].known_type);
  EXPECT_EQ(without_catalog.edges.size(), 2u);
}

TEST(AnalysisGraphView, MissingNodesAndPortsRemainExplicitRatherThanConnectingToAnotherObject)
{
  const auto types = catalog();
  const auto source = graph(Json::array({node("start", "source"),
      node("end", "output", {{"in", {{"from", "start.not_declared"}}},
                              {"extras", Json::array({{{"from", "gone.out"}}})}})}),
      {{"result", "end.out"}, {"absent", "gone.out"}, {"bad_port", "start.also_missing"}});
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.edges.size(), 2u);
  EXPECT_EQ(view.edges[0].diagnostic, "missing_port");
  EXPECT_EQ(view.edges[0].source, 0);
  EXPECT_FALSE(view.nodes[0].outputs[size_t(view.edges[0].output)].declared);
  EXPECT_EQ(view.edges[1].diagnostic, "missing_node");
  EXPECT_EQ(view.edges[1].source, -1);
  EXPECT_EQ(view.edges[1].source_node, "gone");
  EXPECT_EQ(view.edges[1].from.x, view.edges[1].to.x - 60);
  EXPECT_EQ(view.outputs[1].diagnostic, "missing_node");
  EXPECT_EQ(view.outputs[2].diagnostic, "missing_port");
  EXPECT_TRUE(has_issue(view, "missing_node"));
  EXPECT_TRUE(has_issue(view, "missing_port"));
  EXPECT_TRUE(std::isfinite(view.bounds.width));
}

TEST(AnalysisGraphView, DuplicateIdsDoNotResolveLinksOrOutputsToTheFirstDuplicate)
{
  const auto types = catalog();
  const auto source = graph(Json::array({node("same", "source"), node("same", "source"),
      node("end", "output", {{"in", {{"from", "same.out"}}}})}), {{"result", "same.out"}});
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.nodes.size(), 3u);
  EXPECT_TRUE(view.nodes[0].ambiguous_id);
  EXPECT_TRUE(view.nodes[1].ambiguous_id);
  EXPECT_EQ(view.edges[0].source, -1);
  EXPECT_EQ(view.edges[0].diagnostic, "ambiguous_node");
  EXPECT_EQ(view.outputs[0].node_index, -1);
  EXPECT_EQ(view.outputs[0].diagnostic, "ambiguous_node");
  EXPECT_TRUE(has_issue(view, "duplicate_id"));
  EXPECT_NE(view.nodes[0].rect.y, view.nodes[1].rect.y);
}

TEST(AnalysisGraphView, SccLayoutMarksOnlyCycleMembersAndPlacesTheirDescendantsLater)
{
  const auto types = catalog();
  const auto source = graph(Json::array({
      node("a", "filter", {{"in", {{"from", "b.out"}}}}),
      node("b", "filter", {{"in", {{"from", "a.out"}}}}),
      node("end", "output", {{"in", {{"from", "b.out"}}}}),
      node("self", "filter", {{"in", {{"from", "self.out"}}}}), node("independent", "source")}));
  const auto view = analysis_graph_view(source, &types);
  EXPECT_TRUE(view.nodes[0].cyclic);
  EXPECT_TRUE(view.nodes[1].cyclic);
  EXPECT_FALSE(view.nodes[2].cyclic);
  EXPECT_TRUE(view.nodes[3].cyclic);
  EXPECT_FALSE(view.nodes[4].cyclic);
  EXPECT_EQ(view.nodes[0].rect.x, view.nodes[1].rect.x);
  EXPECT_LT(view.nodes[1].rect.x, view.nodes[2].rect.x);
  EXPECT_TRUE(has_issue(view, "cycle"));
  for (const auto &item : view.nodes) {
    EXPECT_TRUE(std::isfinite(item.rect.x));
    EXPECT_TRUE(std::isfinite(item.rect.y));
    EXPECT_GT(item.rect.height, 0);
  }
}

TEST(AnalysisGraphView, PositionsHonorContractCoordinatesAndRejectNonfiniteMalformedOrHugeValues)
{
  const auto types = catalog();
  auto source = graph(Json::array({node("a", "source"), node("b", "source"), node("c", "source"),
      node("d", "source"), node("end", "source")}));
  source.raw["ui"] = {{"positions", {
      {"a", Json::array({-15, 25.5})}, {"b", Json::array({std::numeric_limits<double>::infinity(), 0})},
      {"c", Json::array({1e9, 0})}, {"d", Json::array({"wrong", 0})}, {"end", Json::array({1, 2, 3})}}}};
  const auto view = analysis_graph_view(source, &types);
  EXPECT_TRUE(view.nodes[0].supplied_position);
  EXPECT_EQ(view.nodes[0].rect.x, -15);
  EXPECT_EQ(view.nodes[0].rect.y, 25.5);
  for (size_t i = 1; i < view.nodes.size(); ++i) {
    EXPECT_FALSE(view.nodes[i].supplied_position);
    EXPECT_TRUE(std::isfinite(view.nodes[i].rect.x));
    EXPECT_TRUE(std::isfinite(view.nodes[i].rect.y));
  }
  EXPECT_LE(view.bounds.x, -15);
  EXPECT_TRUE(has_issue(view, "invalid_position"));
  EXPECT_TRUE(std::isinf(source.raw["ui"]["positions"]["b"][0].get<double>()));
}

TEST(AnalysisGraphView, ParameterSummariesDistinguishNullDefaultMissingAndExactIntegerValues)
{
  auto types = catalog();
  io::ParamSpec optional;
  optional.name = "optional";
  optional.has_default = true;
  optional.default_value = nullptr;
  io::ParamSpec gain;
  gain.name = "gain";
  gain.has_default = true;
  gain.default_value = 2;
  gain.stage = "data";
  gain.unit = "K";
  io::ParamSpec required;
  required.name = "binding";
  required.required = true;
  types.nodes[0].params = {optional, gain, required};
  auto source_node = node("end", "source");
  source_node["params"] = {{"gain", nullptr}, {"extra", INT64_MAX}};
  const auto source = graph(Json::array({source_node}));
  const auto view = analysis_graph_view(source, &types);
  const auto &item = view.nodes[0];
  EXPECT_EQ(parameter(item, "optional").origin, "default");
  EXPECT_EQ(parameter(item, "optional").value_text, "null");
  EXPECT_EQ(parameter(item, "gain").origin, "explicit");
  EXPECT_EQ(parameter(item, "gain").value_text, "null");
  EXPECT_EQ(parameter(item, "gain").stage, "data");
  EXPECT_EQ(parameter(item, "gain").unit, "K");
  EXPECT_EQ(parameter(item, "binding").origin, "missing");
  EXPECT_TRUE(parameter(item, "binding").required);
  EXPECT_TRUE(parameter(item, "binding").value_text.empty());
  EXPECT_EQ(parameter(item, "extra").value_text, "9223372036854775807");
  EXPECT_FALSE(parameter(item, "extra").declared);
}

TEST(AnalysisGraphView, ParamReferencesKeepLinksAndDeclarationDefaultsWithoutSubstitution)
{
  auto source_node = node("end", "source");
  source_node["params"] = {{"direct", {{"$param", "step"}}},
      {"nested", {{"a/b~c", Json::array({{{"$param", "unset"}}, {{"$param", "duplicate"}}})}}}};
  auto source = graph(Json::array({source_node}));
  io::GraphParameter step;
  step.name = "step"; step.has_default = true; step.default_value = "latest";
  io::GraphParameter duplicate;
  duplicate.name = "duplicate"; duplicate.has_default = true; duplicate.default_value = 1;
  source.parameters = {step, duplicate, duplicate};
  const auto view = analysis_graph_view(source);
  const auto &direct = parameter(view.nodes[0], "direct");
  EXPECT_EQ(direct.value_text, "{\"$param\":\"step\"}");
  ASSERT_EQ(direct.references.size(), 1u);
  EXPECT_EQ(direct.references[0].parameter, "step");
  EXPECT_TRUE(direct.references[0].path.empty());
  EXPECT_TRUE(direct.references[0].has_default);
  EXPECT_EQ(direct.references[0].default_text, "latest");
  const auto &nested = parameter(view.nodes[0], "nested");
  ASSERT_EQ(nested.references.size(), 2u);
  EXPECT_EQ(nested.references[0].path, "/a~1b~0c/0");
  EXPECT_FALSE(nested.references[0].has_default);
  EXPECT_FALSE(nested.references[1].has_default) << "Duplicate declarations must not pick an arbitrary default";
  EXPECT_TRUE(nested.references_complete);
  EXPECT_EQ(source.nodes[0].params["direct"]["$param"], "step");
}

TEST(AnalysisGraphView, SummariesAndReferenceDiscoveryDoNotSerializeLargeInvisibleSuffixes)
{
  io::Graph source;
  io::GraphNode item;
  item.id = "source";
  item.type = "plugin.source.data@1";
  item.label = std::string(100000, 'x');
  Json array = Json::array();
  for (int i = 0; i < 10000; ++i) { array.push_back(i); }
  array.push_back(std::string("\xc3", 1)); // dump() fails; the invisible suffix must not be formatted.
  item.params["huge"] = std::move(array);
  Json nested = std::string("\xc3", 1);
  for (int i = 0; i < 80; ++i) { nested = Json::array({std::move(nested)}); }
  item.params["deep"] = std::move(nested);
  source.nodes.push_back(std::move(item));
  EXPECT_THROW(source.nodes[0].params["huge"].dump(), Json::type_error);
  const auto view = analysis_graph_view(source);
  EXPECT_LE(view.nodes[0].label.size(), AnalysisGraphView::summary_bytes);
  for (const auto &value : view.nodes[0].parameters) {
    EXPECT_LE(value.value_text.size(), AnalysisGraphView::summary_bytes);
    EXPECT_TRUE(core::utf8::is_valid(value.value_text));
    EXPECT_TRUE(value.value_text.ends_with("…"));
    EXPECT_FALSE(value.references_complete);
  }
  EXPECT_EQ(source.nodes[0].params["huge"].size(), 10001u);
  EXPECT_EQ(source.nodes[0].label.size(), 100000u);
}

TEST(AnalysisGraphView, Utf8LabelsAndReferenceListsHaveExplicitBoundedSummaries)
{
  io::Graph source;
  io::GraphNode item;
  item.id = "source";
  item.type = "plugin.source.data@1";
  for (int i = 0; i < 100; ++i) { item.label += "温度🧪\n"; }
  item.params["refs"] = Json::array();
  for (int i = 0; i < 40; ++i) { item.params["refs"].push_back({{"$param", "p"}}); }
  source.nodes.push_back(std::move(item));
  const auto view = analysis_graph_view(source);
  EXPECT_LE(view.nodes[0].label.size(), AnalysisGraphView::summary_bytes);
  EXPECT_TRUE(core::utf8::is_valid(view.nodes[0].label));
  EXPECT_EQ(view.nodes[0].label.find('\n'), std::string::npos);
  const auto &value = parameter(view.nodes[0], "refs");
  EXPECT_EQ(value.references.size(), 32u);
  EXPECT_FALSE(value.references_complete);
  EXPECT_EQ(value.references[31].path, "/31");
}

TEST(AnalysisGraphView, CapsReportOmissionsAndRetainTheOriginalGraphForInspection)
{
  auto types = catalog();
  types.nodes[0].inputs.clear();
  types.nodes[0].outputs.clear();
  for (int i = 0; i < 150; ++i) {
    types.nodes[0].inputs.push_back(port("in" + std::to_string(i)));
    types.nodes[0].outputs.push_back(port("out" + std::to_string(i)));
  }
  io::Graph source;
  io::GraphNode item;
  item.id = "one"; item.type = types.nodes[0].id;
  for (int i = 0; i < 150; ++i) { item.params["p" + std::to_string(i)] = i; }
  io::GraphInput input;
  input.port = "in0";
  for (int i = 0; i < 4100; ++i) { input.links.push_back({"one", "out0", {}}); }
  item.inputs.push_back(std::move(input));
  source.nodes.push_back(std::move(item));
  for (int i = 0; i < 260; ++i) { source.outputs.push_back({"o" + std::to_string(i), "one", "out0"}); }
  const auto view = analysis_graph_view(source, &types);
  ASSERT_EQ(view.nodes.size(), 1u);
  EXPECT_EQ(view.nodes[0].inputs.size(), 128u);
  EXPECT_EQ(view.nodes[0].outputs.size(), 128u);
  EXPECT_EQ(view.nodes[0].parameters.size(), 128u);
  EXPECT_EQ(view.nodes[0].omitted_inputs, 22u);
  EXPECT_EQ(view.nodes[0].omitted_outputs, 22u);
  EXPECT_EQ(view.nodes[0].omitted_parameters, 22u);
  EXPECT_EQ(view.edges.size(), 4096u);
  EXPECT_EQ(view.omitted_edges, 4u);
  EXPECT_EQ(view.outputs.size(), 256u);
  EXPECT_EQ(view.omitted_outputs, 4u);
  EXPECT_TRUE(has_issue(view, "display_limit"));
  EXPECT_EQ(source.nodes[0].inputs[0].links.size(), 4100u);
  EXPECT_EQ(source.outputs.size(), 260u);
  EXPECT_EQ(source.nodes[0].params.size(), 150u);
}

TEST(AnalysisGraphView, MissingEndpointDiagnosticsRemainBounded)
{
  auto source = graph(Json::array({node("end", "output")}));
  io::GraphInput input;
  input.port = "in";
  for (int i = 0; i < 400; ++i) { input.links.push_back({"missing" + std::to_string(i), "out", {}}); }
  source.nodes[0].inputs.push_back(std::move(input));
  const auto types = catalog();
  const auto view = analysis_graph_view(source, &types);
  EXPECT_EQ(view.issues.size(), AnalysisGraphView::max_issues);
  EXPECT_EQ(view.omitted_issues, 144u);
  EXPECT_EQ(view.edges.size(), 400u);
  EXPECT_EQ(view.edges.back().source_node, "missing399");
}

TEST(AnalysisGraphView, RejectsUnboundedIdentityAndNodeCountsWithoutTruncatingTheGraph)
{
  io::Graph source;
  for (int i = 0; i < 201; ++i) {
    io::GraphNode item;
    item.id = "n" + std::to_string(i); item.type = "plugin.source.data@1";
    source.nodes.push_back(std::move(item));
  }
  EXPECT_THROW(analysis_graph_view(source), std::invalid_argument);
  EXPECT_EQ(source.nodes.size(), 201u);
  source.nodes.resize(1);
  source.nodes[0].id.assign(1025, 'x');
  EXPECT_THROW(analysis_graph_view(source), std::invalid_argument);
  source.nodes.clear();
  const auto empty = analysis_graph_view(source);
  EXPECT_TRUE(empty.nodes.empty());
  EXPECT_EQ(empty.bounds, (AnalysisGraphRect{}));
  EXPECT_TRUE(has_issue(empty, "no_nodes"));
}

}  // namespace
}  // namespace stk::app
