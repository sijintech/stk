/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Node catalog (stk.catalog/1, docs/specs/catalog/stk-catalog-m1.json), presets
 * (suan/graph/presets/<id>.json) and the parameter forms generated from them: every form field comes
 * from a JSON Schema plus its x-stk-* annotations (x-stk-stage, x-stk-widget, x-stk-group,
 * x-stk-unit, ...). A preset parameter inherits the schema of the node params that reference it
 * through {"$param": name}. */

#include "stk/io/graph.hh"
#include "stk/io/json.hh"
#include "stk/io/schema.hh"

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::io {

inline constexpr std::string_view kCatalogSchema = "stk.catalog/1";

struct PortSpec {
  std::string name;
  std::vector<std::string> types; /* one type, or a union such as ["scene", "plot"] */
  std::vector<std::string> accepts;
  std::vector<std::string> kinds; /* output: "kind" (one) or a list of possible kinds */
  std::string kind_from;
  std::string value_type;
  bool required = false;
  bool multi = false;
};

struct ParamSpec {
  std::string name;
  Json schema;
  bool required = false;
  bool has_default = false;
  Json default_value;
  std::string stage;  /* x-stk-stage: "data" or "client" */
  std::string widget; /* x-stk-widget */
  std::string group, unit, quantity, title_zh, field_of, choices_from;
  bool advanced = false;
};

struct NodeType {
  std::string id;   /* "stk.filter.contour@1" */
  std::string type; /* "stk.filter.contour" */
  int version = 0, impl_version = 0;
  std::string stage, category, cache;
  std::string title_en, title_zh, description_en, description_zh;
  std::vector<PortSpec> inputs, outputs;
  Json params_schema;
  std::vector<ParamSpec> params; /* in declaration order */
  bool time_dependent = false, deterministic = true, stretch = false;
  Json raw;

  const ParamSpec *param(std::string_view name) const;
  const PortSpec *input(std::string_view name) const;
  const PortSpec *output(std::string_view name) const;
  /** The node family: the middle segment of the type id ("filter"). */
  std::string family() const;
};

struct Catalog {
  std::string schema;
  std::map<std::string, int> namespaces;
  Json port_types, kinds, value_types;
  std::vector<std::string> client_types;
  std::vector<NodeType> nodes;

  static Catalog from_json(const Json &document);
  static Catalog load(const std::filesystem::path &path);
  const NodeType *find(std::string_view id) const;
};

/** An issue of validate_node_params (codes as stk-graph-v1 §11). */
struct ParamIssue {
  std::string code; /* unknown_param, missing_param, invalid_param, param_ref_type, bad_param_ref, reserved_key */
  std::string message;
  std::string path; /* pointer into the graph document ("/nodes/<index>/params/...") */
  bool operator==(const ParamIssue &) const = default;
};

/**
 * The params checks that suan.graph.schema.validate_graph applies to one node of a known type:
 * `$param` references against the declared graph parameters, unknown params, schema violations
 * after substituting parameter values, and missing required params. `declared` maps valid parameter
 * names to their effective values; `named` lists every parameter name in the graph.
 */
std::vector<ParamIssue> validate_node_params(const NodeType &type,
                                             std::string_view node_id,
                                             const Json &params,
                                             const Json &declared_values,
                                             const std::vector<std::string> &named,
                                             const std::string &node_path);

struct PresetBinding {
  std::string name, description;
};

struct Preset {
  std::string id, name, description;
  std::vector<PresetBinding> bindings;
  Json graph;

  /** A preset file: {"id", "name", "description", "bindings", "graph"} or a bare stk.graph/1 document. */
  static Preset from_json(const Json &document, std::string_view id);
  static Preset load(const std::filesystem::path &path);
  /** Every *.json preset in a directory (sorted by id); ids must match ^[a-z0-9][a-z0-9_-]*$. */
  static std::vector<Preset> load_directory(const std::filesystem::path &directory);
};

/** One field of a generated parameter form. */
struct ParameterForm {
  std::string name;
  Json declaration;               /* the graph parameter entry */
  Json schema;                    /* declaration schema, allOf the referencing node-param schemas */
  Json annotations;               /* x-stk-* / title / description of the first reference */
  std::vector<std::string> references; /* "node.param/pointer" of every {"$param": name} */
  std::string stage;              /* "data" if any reference is data-stage (or a source/filter/analysis node) */
  std::string widget;             /* x-stk-widget of the first reference, else derived from the type */
};

/** Parameter forms of a graph against a catalog, in declaration order. */
std::vector<ParameterForm> parameter_forms(const Json &graph, const Catalog &catalog);

/** The sub-schema at a JSON pointer inside values of `schema` (properties, additionalProperties,
 * prefixItems, items; anyOf/oneOf/allOf branches that define it are combined with anyOf). Returns
 * `true` (any value) when the location is unconstrained. */
Json schema_at(const Json &schema, std::string_view pointer);

}  // namespace stk::io
