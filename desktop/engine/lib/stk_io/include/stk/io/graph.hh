/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* stk.graph/1 documents (docs/specs/stk-graph-v1.md): a typed model for the UI plus the helpers of
 * suan.graph.schema that clients need without Python: graph_hash (identical to Python's),
 * parameter_schema, $param discovery/substitution and port/type references. Full graph validation
 * (port lattice, cycles) stays in Python (bridge method graph.validate); node parameters can be
 * checked locally with validate_node_params() in catalog.hh. */

#include "stk/io/json.hh"

#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace stk::io {

inline constexpr std::string_view kGraphSchema = "stk.graph/1";

class GraphModelError : public std::runtime_error {
 public:
  GraphModelError(const std::string &message, std::string path = {})
      : std::runtime_error(path.empty() ? message : path + ": " + message), path_(std::move(path))
  {
  }
  const std::string &path() const
  {
    return path_;
  }

 private:
  std::string path_;
};

/** Graph-level parameter types (stk-graph-v1 §2.2). */
inline constexpr std::string_view kParameterTypes[] = {
    "number", "integer", "boolean", "string", "step", "vector3", "int3", "range", "enum", "json"};

struct GraphParameter {
  std::string name;
  std::string type;
  bool has_default = false;
  Json default_value;
  Json choices;  /* null when absent */
  Json minimum;  /* null when absent */
  Json maximum;
  std::string unit, label, description;
  Json raw;
};

struct GraphLink {
  std::string node;
  std::string port;
  std::string alias; /* "as", empty when absent */
};

struct GraphInput {
  std::string port;
  std::vector<GraphLink> links;
  bool is_list = false; /* written as a list (multi ports) */
};

struct GraphNode {
  std::string id;
  std::string type;
  Json params = Json::object();
  std::vector<GraphInput> inputs;
  std::string label;
  Json raw;

  const GraphInput *input(std::string_view port) const;
};

struct GraphOutput {
  std::string name;
  std::string node;
  std::string port;
};

/** A lenient typed view of a graph document (unknown keys and node types are kept in `raw`). */
struct Graph {
  std::string schema, id, name, description;
  Json catalog; /* {"stk": 1} or null */
  std::vector<GraphParameter> parameters;
  Json time;    /* null when absent */
  std::vector<GraphNode> nodes;
  std::vector<GraphOutput> outputs;
  Json raw;

  /** Throws GraphModelError when the document is not an stk.graph/1 object with nodes/outputs of the right shapes. */
  static Graph from_json(const Json &document);
  const GraphNode *node(std::string_view id) const;
  const GraphParameter *parameter(std::string_view name) const;
  /** Node ids upstream of `node_id` (links followed transitively), excluding it. */
  std::vector<std::string> upstream(std::string_view node_id) const;
};

struct TypeRef {
  std::string ns, family, name;
  int major = 0;
};
/** "stk.filter.contour@1" -> {stk, filter, contour, 1}. */
std::optional<TypeRef> parse_type(std::string_view type);
/** "src.out" -> {"src", "out"}. */
std::optional<std::pair<std::string, std::string>> parse_port_ref(std::string_view ref);
/** ^[a-z][a-z0-9_]{0,63}$ */
bool is_graph_id(std::string_view id);

/** "sha256:<hex>" of the evaluation-relevant graph content (suan.graph.schema.graph_hash). */
std::string graph_hash(const Json &graph);

/** JSON Schema fragment of a graph parameter declaration (suan.graph.schema.parameter_schema);
 * throws GraphModelError for an unknown type. */
Json parameter_schema(const Json &declaration);

/** Effective parameter values: declared defaults updated by `overrides` (an object). */
Json parameter_values(const Json &graph, const Json &overrides = Json::object());

struct ParamRef {
  std::string pointer;
  std::optional<std::string> name;    /* the referenced parameter */
  std::optional<std::string> problem; /* malformed reference or reserved key */
};
/** '$'-keys inside a param value (suan.graph.schema.find_param_refs). */
std::vector<ParamRef> find_param_refs(const Json &value, const std::string &path = {});

/** Replace every {"$param": name} with values[name]; throws GraphModelError for an unknown name. */
Json substitute_params(const Json &value, const Json &values);

}  // namespace stk::io
