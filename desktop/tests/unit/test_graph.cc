/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Graph, catalog, preset and result models; parity with suan.graph.schema (graph_hash,
 * canonical_json, parameter_schema, find_param_refs and the node-param checks of validate_graph). */
#include "support.hh"

#include "stk/io/catalog.hh"
#include "stk/io/graph.hh"
#include "stk/io/result.hh"

#include <gtest/gtest.h>

using namespace stk;
using io::Json;

namespace {

io::Catalog m1_catalog()
{
  return io::Catalog::load(test::repo_root() / "docs" / "specs" / "catalog" / "stk-catalog-m1.json");
}

}  // namespace

TEST(GraphParity, HashAndCanonicalJsonMatchPython)
{
  const Json fixture_1 = test::fixture_json("graph_cases.json");
  for (const Json &c : fixture_1["hashes"]) {
    EXPECT_EQ(io::canonical_json(c["graph"]), c["canonical"].get<std::string>()) << c["name"];
    EXPECT_EQ(io::graph_hash(c["graph"]), c["hash"].get<std::string>()) << c["name"];
  }
}

TEST(GraphParity, ParameterSchemasAndRefs)
{
  const Json cases = test::fixture_json("graph_cases.json");
  for (const Json &c : cases["parameter_schemas"]) {
    EXPECT_EQ(io::canonical_json(io::parameter_schema(c["declaration"])), io::canonical_json(c["schema"]))
        << c["declaration"].dump();
  }
  for (const Json &c : cases["refs"]) {
    const std::vector<io::ParamRef> refs = io::find_param_refs(c["value"], "/p");
    ASSERT_EQ(refs.size(), c["refs"].size()) << c["value"].dump();
    for (size_t i = 0; i < refs.size(); i++) {
      EXPECT_EQ(refs[i].pointer, c["refs"][i][0].get<std::string>());
      EXPECT_EQ(refs[i].name.value_or(""), c["refs"][i][1].is_null() ? "" : c["refs"][i][1].get<std::string>());
      EXPECT_EQ(refs[i].problem.value_or(""), c["refs"][i][2].is_null() ? "" : c["refs"][i][2].get<std::string>());
    }
  }
  EXPECT_EQ(io::substitute_params(io::parse_json(R"({"a":[{"$param":"x"},{"b":{"$param":"y"}}]})"),
                                  io::parse_json(R"({"x":1,"y":"z"})")),
            io::parse_json(R"({"a":[1,{"b":"z"}]})"));
  EXPECT_THROW(io::substitute_params(io::parse_json(R"({"$param":"q"})"), Json::object()), io::GraphModelError);
}

TEST(GraphParity, NodeParamIssuesMatchValidateGraph)
{
  const io::Catalog catalog = m1_catalog();
  const Json fixture_2 = test::fixture_json("graph_cases.json");
  for (const Json &c : fixture_2["node_issues"]) {
    const Json &graph = c["graph"];
    /* Declared (valid) parameters and their values, as validate_graph computes them. */
    Json values = Json::object();
    std::vector<std::string> named;
    for (const Json &item : graph["parameters"]) {
      const std::string name = item["name"].get<std::string>();
      named.push_back(name);
      if (io::check_value(item["default"], io::parameter_schema(item)).empty()) {
        values[name] = item["default"];
      }
    }
    std::vector<io::ParamIssue> got;
    for (size_t i = 0; i < graph["nodes"].size(); i++) {
      const Json &node = graph["nodes"][i];
      const io::NodeType *type = catalog.find(node["type"].get<std::string>());
      if (!type) {
        continue;
      }
      for (io::ParamIssue &issue : io::validate_node_params(*type, node["id"].get<std::string>(),
                                                            node.value("params", Json::object()), values, named,
                                                            "/nodes/" + std::to_string(i)))
      {
        got.push_back(std::move(issue));
      }
    }
    ASSERT_EQ(got.size(), c["issues"].size()) << c["preset"] << " " << (got.empty() ? "" : got[0].message);
    for (size_t i = 0; i < got.size(); i++) {
      EXPECT_EQ(got[i].code, c["issues"][i]["code"].get<std::string>());
      EXPECT_EQ(got[i].path, c["issues"][i]["path"].get<std::string>());
      EXPECT_EQ(got[i].message, c["issues"][i]["message"].get<std::string>());
    }
  }
}

TEST(Graph, ModelsPresetsAndForms)
{
  const io::Catalog catalog = m1_catalog();
  EXPECT_EQ(catalog.namespaces.at("stk"), 1);
  const io::NodeType *contour = catalog.find("stk.filter.contour@1");
  ASSERT_NE(contour, nullptr);
  EXPECT_EQ(contour->family(), "filter");
  EXPECT_EQ(contour->title_zh, "等值面");
  ASSERT_NE(contour->param("field"), nullptr);
  EXPECT_EQ(contour->param("field")->stage, "data");
  EXPECT_EQ(contour->param("field")->widget, "field");
  EXPECT_TRUE(contour->param("field")->required);

  const std::vector<io::Preset> presets = io::Preset::load_directory(test::repo_root() / "suan" / "graph" / "presets");
  ASSERT_EQ(presets.size(), 7u);
  for (const io::Preset &preset : presets) {
    const io::Graph graph = io::Graph::from_json(preset.graph);
    EXPECT_FALSE(graph.nodes.empty()) << preset.id;
    EXPECT_FALSE(graph.outputs.empty()) << preset.id;
    for (const io::GraphNode &node : graph.nodes) {
      EXPECT_NE(catalog.find(node.type), nullptr) << node.type;
    }
    for (const io::ParameterForm &form : io::parameter_forms(preset.graph, catalog)) {
      EXPECT_FALSE(form.references.empty()) << preset.id << " " << form.name;
      /* The default value satisfies the generated form schema. */
      EXPECT_TRUE(io::check_value(form.declaration["default"], form.schema).empty())
          << preset.id << " " << form.name << " " << form.schema.dump();
    }
  }
  const auto domains = std::find_if(presets.begin(), presets.end(), [](const io::Preset &p) { return p.id == "muferro-domains"; });
  ASSERT_NE(domains, presets.end());
  EXPECT_EQ(domains->bindings.at(0).name, "run");
  std::map<std::string, io::ParameterForm> forms;
  for (io::ParameterForm &form : io::parameter_forms(domains->graph, catalog)) {
    forms[form.name] = std::move(form);
  }
  ASSERT_TRUE(forms.count("step"));
  EXPECT_EQ(forms["step"].stage, "data");
  EXPECT_EQ(forms["step"].widget, "step");
  ASSERT_TRUE(forms.count("view"));
  EXPECT_EQ(forms["view"].stage, "client");
  const io::Graph graph = io::Graph::from_json(domains->graph);
  EXPECT_FALSE(graph.upstream("scene").empty());
  EXPECT_THROW(io::Graph::from_json(Json::object()), io::GraphModelError);
  EXPECT_TRUE(io::parse_type("stk.filter.contour@1").has_value());
  EXPECT_FALSE(io::parse_type("stk.filter.contour@0").has_value());
  EXPECT_FALSE(io::parse_type("stk.Filter.contour@1").has_value());
  EXPECT_EQ(io::parse_port_ref("src.out")->second, "out");
  EXPECT_FALSE(io::parse_port_ref("src.out.x").has_value());
  EXPECT_EQ(io::schema_at(io::parse_json(R"({"type":"object","properties":{"a":{"type":"array","prefixItems":[{"type":"integer"}]}}})"),
                          "/a/0"),
            io::parse_json(R"({"type":"integer"})"));
}

TEST(Graph, ResultAndSeriesModels)
{
  const Json doc = io::parse_json(R"({
    "schema": "stk.graph-result/1", "graph_sha256": "ab", "graph_hash": "sha256:ab", "profile": "web",
    "outputs": {
      "view": {"type": "payload", "manifest": {"schema": "stk.payload/2", "buffers": [
        {"id": "b0", "uri": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
         "sha256": "1111111111111111111111111111111111111111111111111111111111111111", "byteLength": 8}]}},
      "image": {"type": "image", "blob": "2222222222222222222222222222222222222222222222222222222222222222",
                "media_type": "image/png", "size": 123, "width": 1600, "height": 1200},
      "energy": {"type": "plot", "blob": "3333333333333333333333333333333333333333333333333333333333333333",
                 "media_type": "image/svg+xml", "size": 1,
                 "data_blob": "4444444444444444444444444444444444444444444444444444444444444444"},
      "info": {"type": "value", "value": {"detected": true}}},
    "parameters": {"step": {"value": 1000, "choices": [0, 500, 1000]}},
    "keys": {"polar": {"data": "d", "full": "f"}}, "evaluated": ["scene", "png"], "timings": {"scene": 0.5},
    "cache": {"hits": 5, "misses": 3},
    "warnings": [{"code": "payload_reduced", "message": "m", "path": "/outputs/view", "node": "scene", "hint": null,
                  "severity": "warning", "details": {"layer": "vol"}}],
    "errors": [{"code": "frame_not_found", "message": "m", "path": "", "node": "polar", "hint": null,
                "severity": "error", "skipped": ["scene"]}]})");
  const io::GraphResult result = io::GraphResult::from_json(doc);
  EXPECT_EQ(result.outputs.size(), 4u);
  EXPECT_NE(result.output("view")->manifest(), nullptr);
  EXPECT_EQ(result.output("image")->media_type(), "image/png");
  EXPECT_EQ(result.blobs().size(), 4u);
  EXPECT_EQ(result.parameters.at("step").choices.size(), 3u);
  EXPECT_TRUE(result.was_evaluated("scene"));
  EXPECT_FALSE(result.evaluated_any({"src", "cut"})); /* a client-stage change re-ran no data node */
  EXPECT_EQ(result.cache_hits, 5);
  EXPECT_EQ(result.warnings.at(0).details["layer"], "vol");
  EXPECT_EQ(result.errors.at(0).skipped.at(0), "scene");
  const io::Series series = io::Series::from_json(io::parse_json(
      R"({"schema": "stk.series/1", "parameter": "step", "frames": [{"step": 0, "outputs": {"image": "image.00000000.png"}}]})"));
  EXPECT_EQ(series.frames.at(0).outputs.at("image"), "image.00000000.png");
  EXPECT_EQ(io::Series::from_json(series.to_json()).frames.size(), 1u);
}
