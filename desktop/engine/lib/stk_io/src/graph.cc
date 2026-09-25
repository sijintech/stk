/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/graph.hh"

#include "stk/core/sha256.hh"
#include "stk/io/schema.hh"

#include <algorithm>
#include <set>

namespace stk::io {

namespace {

const Json *get(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

std::string string_or(const Json &object, std::string_view key)
{
  const Json *value = get(object, key);
  return value && value->is_string() ? value->get<std::string>() : std::string();
}

bool lower_alpha(char c)
{
  return c >= 'a' && c <= 'z';
}
bool id_char(char c)
{
  return lower_alpha(c) || (c >= '0' && c <= '9') || c == '_';
}

/* Python str() of a JSON value used as a sort key. */
std::string python_sort_key(const Json *value)
{
  if (!value || value->is_null()) {
    return "None";
  }
  if (value->is_string()) {
    return value->get<std::string>();
  }
  if (value->is_boolean()) {
    return value->get<bool>() ? "True" : "False";
  }
  return python_str(*value);
}

}  // namespace

bool is_graph_id(std::string_view id)
{
  if (id.empty() || id.size() > 64 || !lower_alpha(id[0])) {
    return false;
  }
  return std::all_of(id.begin() + 1, id.end(), id_char);
}

std::optional<TypeRef> parse_type(std::string_view type)
{
  /* ^([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)@([1-9][0-9]*)$ */
  const size_t at = type.rfind('@');
  if (at == std::string_view::npos) {
    return std::nullopt;
  }
  const std::string_view head = type.substr(0, at), version = type.substr(at + 1);
  if (version.empty() || version[0] < '1' || version[0] > '9' || version.size() > 9 ||
      !std::all_of(version.begin(), version.end(), [](char c) { return c >= '0' && c <= '9'; }))
  {
    return std::nullopt;
  }
  std::vector<std::string_view> parts;
  size_t start = 0;
  for (;;) {
    const size_t dot = head.find('.', start);
    parts.push_back(head.substr(start, dot == std::string_view::npos ? std::string_view::npos : dot - start));
    if (dot == std::string_view::npos) {
      break;
    }
    start = dot + 1;
  }
  if (parts.size() != 3) {
    return std::nullopt;
  }
  for (std::string_view part : parts) {
    if (part.empty() || !lower_alpha(part[0]) || !std::all_of(part.begin(), part.end(), id_char)) {
      return std::nullopt;
    }
  }
  return TypeRef{std::string(parts[0]), std::string(parts[1]), std::string(parts[2]), std::stoi(std::string(version))};
}

std::optional<std::pair<std::string, std::string>> parse_port_ref(std::string_view ref)
{
  const size_t dot = ref.find('.');
  if (dot == std::string_view::npos || ref.find('.', dot + 1) != std::string_view::npos) {
    return std::nullopt;
  }
  const std::string_view node = ref.substr(0, dot), port = ref.substr(dot + 1);
  if (!is_graph_id(node) || !is_graph_id(port)) {
    return std::nullopt;
  }
  return std::make_pair(std::string(node), std::string(port));
}

const GraphInput *GraphNode::input(std::string_view port) const
{
  for (const GraphInput &in : inputs) {
    if (in.port == port) {
      return &in;
    }
  }
  return nullptr;
}

Graph Graph::from_json(const Json &document)
{
  if (!document.is_object()) {
    throw GraphModelError("a graph must be a JSON object");
  }
  Graph graph;
  graph.raw = document;
  graph.schema = string_or(document, "schema");
  if (graph.schema != kGraphSchema) {
    throw GraphModelError("schema must be 'stk.graph/1'", "/schema");
  }
  graph.id = string_or(document, "id");
  graph.name = string_or(document, "name");
  graph.description = string_or(document, "description");
  graph.catalog = document.value("catalog", Json());
  graph.time = document.value("time", Json());
  if (const Json *parameters = get(document, "parameters")) {
    if (!parameters->is_array()) {
      throw GraphModelError("'parameters' must be a list", "/parameters");
    }
    for (size_t i = 0; i < parameters->size(); i++) {
      const Json &item = (*parameters)[i];
      const std::string path = "/parameters/" + std::to_string(i);
      if (!item.is_object() || !get(item, "name") || !item["name"].is_string()) {
        throw GraphModelError("a parameter needs a name", path);
      }
      GraphParameter p;
      p.raw = item;
      p.name = item["name"].get<std::string>();
      p.type = string_or(item, "type");
      p.has_default = item.contains("default");
      p.default_value = item.value("default", Json());
      p.choices = item.value("choices", Json());
      p.minimum = item.value("minimum", Json());
      p.maximum = item.value("maximum", Json());
      p.unit = string_or(item, "unit");
      p.label = string_or(item, "label");
      p.description = string_or(item, "description");
      graph.parameters.push_back(std::move(p));
    }
  }
  const Json *nodes = get(document, "nodes");
  if (!nodes || !nodes->is_array()) {
    throw GraphModelError("'nodes' must be a list", "/nodes");
  }
  for (size_t i = 0; i < nodes->size(); i++) {
    const Json &item = (*nodes)[i];
    const std::string path = "/nodes/" + std::to_string(i);
    if (!item.is_object() || !get(item, "id") || !item["id"].is_string() || !get(item, "type") ||
        !item["type"].is_string())
    {
      throw GraphModelError("a node needs string 'id' and 'type'", path);
    }
    GraphNode node;
    node.raw = item;
    node.id = item["id"].get<std::string>();
    node.type = item["type"].get<std::string>();
    node.label = string_or(item, "label");
    if (const Json *params = get(item, "params")) {
      if (!params->is_object()) {
        throw GraphModelError("params must be an object", path + "/params");
      }
      node.params = *params;
    }
    if (const Json *inputs = get(item, "inputs")) {
      if (!inputs->is_object()) {
        throw GraphModelError("inputs must be an object", path + "/inputs");
      }
      for (auto it = inputs->begin(); it != inputs->end(); ++it) {
        GraphInput input;
        input.port = it.key();
        input.is_list = it.value().is_array();
        const Json links = input.is_list ? it.value() : Json::array({it.value()});
        for (const Json &link : links) {
          const Json *from = get(link, "from");
          const auto ref = from && from->is_string() ? parse_port_ref(from->get_ref<const std::string &>()) : std::nullopt;
          if (!ref) {
            throw GraphModelError("a link is {\"from\": \"node.port\"}", path + "/inputs/" + pointer_token(it.key()));
          }
          input.links.push_back({ref->first, ref->second, string_or(link, "as")});
        }
        node.inputs.push_back(std::move(input));
      }
    }
    graph.nodes.push_back(std::move(node));
  }
  const Json *outputs = get(document, "outputs");
  if (!outputs || !outputs->is_object()) {
    throw GraphModelError("'outputs' must be an object", "/outputs");
  }
  for (auto it = outputs->begin(); it != outputs->end(); ++it) {
    const auto ref = it.value().is_string() ? parse_port_ref(it.value().get_ref<const std::string &>()) : std::nullopt;
    if (!ref) {
      throw GraphModelError("an output is \"node.port\"", "/outputs/" + pointer_token(it.key()));
    }
    graph.outputs.push_back({it.key(), ref->first, ref->second});
  }
  return graph;
}

const GraphNode *Graph::node(std::string_view id) const
{
  for (const GraphNode &n : nodes) {
    if (n.id == id) {
      return &n;
    }
  }
  return nullptr;
}

const GraphParameter *Graph::parameter(std::string_view name) const
{
  for (const GraphParameter &p : parameters) {
    if (p.name == name) {
      return &p;
    }
  }
  return nullptr;
}

std::vector<std::string> Graph::upstream(std::string_view node_id) const
{
  std::vector<std::string> order;
  std::set<std::string, std::less<>> seen;
  std::vector<std::string> stack{std::string(node_id)};
  while (!stack.empty()) {
    const std::string current = stack.back();
    stack.pop_back();
    const GraphNode *n = node(current);
    if (!n) {
      continue;
    }
    for (const GraphInput &input : n->inputs) {
      for (const GraphLink &link : input.links) {
        if (link.node != node_id && seen.insert(link.node).second) {
          order.push_back(link.node);
          stack.push_back(link.node);
        }
      }
    }
  }
  return order;
}

std::string graph_hash(const Json &graph)
{
  static const std::set<std::string, std::less<>> graph_skip = {"id", "name", "description", "ui"};
  static const std::set<std::string, std::less<>> node_skip = {"label", "description", "ui"};
  if (!graph.is_object()) {
    throw GraphModelError("a graph must be a JSON object");
  }
  const auto starts_x = [](const std::string &key) { return key.rfind("x-", 0) == 0; };
  Json result = Json::object();
  for (auto it = graph.begin(); it != graph.end(); ++it) {
    if (!graph_skip.count(it.key()) && !starts_x(it.key())) {
      result[it.key()] = it.value();
    }
  }
  if (const Json *nodes = get(graph, "nodes"); nodes && nodes->is_array()) {
    std::vector<Json> items;
    for (const Json &node : *nodes) {
      if (node.is_object()) {
        Json filtered = Json::object();
        for (auto it = node.begin(); it != node.end(); ++it) {
          if (!node_skip.count(it.key()) && !starts_x(it.key())) {
            filtered[it.key()] = it.value();
          }
        }
        items.push_back(std::move(filtered));
      }
      else {
        items.push_back(node);
      }
    }
    std::stable_sort(items.begin(), items.end(), [](const Json &a, const Json &b) {
      const std::string ka = a.is_object() ? python_sort_key(get(a, "id")) : std::string();
      const std::string kb = b.is_object() ? python_sort_key(get(b, "id")) : std::string();
      return ka < kb;
    });
    result["nodes"] = Json(items);
  }
  if (const Json *parameters = get(graph, "parameters"); parameters && parameters->is_array()) {
    std::vector<Json> items;
    for (const Json &item : *parameters) {
      if (item.is_object()) {
        Json filtered = Json::object();
        for (auto it = item.begin(); it != item.end(); ++it) {
          if (!node_skip.count(it.key())) {
            filtered[it.key()] = it.value();
          }
        }
        items.push_back(std::move(filtered));
      }
      else {
        items.push_back(item);
      }
    }
    std::stable_sort(items.begin(), items.end(), [](const Json &a, const Json &b) {
      const std::string ka = a.is_object() ? python_sort_key(get(a, "name")) : std::string();
      const std::string kb = b.is_object() ? python_sort_key(get(b, "name")) : std::string();
      return ka < kb;
    });
    result["parameters"] = Json(items);
  }
  return "sha256:" + core::Sha256::hex(canonical_json(result));
}

Json parameter_schema(const Json &declaration)
{
  const std::string kind = string_or(declaration, "type");
  Json schema;
  if (kind == "number" || kind == "integer" || kind == "boolean" || kind == "string") {
    schema = {{"type", kind}};
  }
  else if (kind == "step") {
    schema = {{"anyOf", Json::array({Json{{"type", "integer"}, {"minimum", 0}}, Json{{"enum", {"latest", "first"}}}})}};
  }
  else if (kind == "vector3" || kind == "int3") {
    schema = {{"type", "array"},
              {"items", {{"type", kind == "vector3" ? "number" : "integer"}}},
              {"minItems", 3},
              {"maxItems", 3}};
  }
  else if (kind == "range") {
    schema = {{"type", "array"},
              {"prefixItems",
               Json::array({Json{{"type", Json::array({"number", "null"})}}, Json{{"type", Json::array({"number", "null"})}}})},
              {"minItems", 2},
              {"maxItems", 2}};
  }
  else if (kind == "enum") {
    schema = {{"enum", declaration.value("choices", Json::array())}};
  }
  else if (kind == "json") {
    schema = Json::object();
  }
  else {
    throw GraphModelError("Unknown parameter type '" + kind + "'");
  }
  if (kind == "number" || kind == "integer") {
    for (const char *key : {"minimum", "maximum"}) {
      const Json *bound = get(declaration, key);
      if (bound && is_finite_number(*bound)) {
        schema[key] = *bound;
      }
    }
  }
  if (const Json *choices = get(declaration, "choices"); choices && kind != "enum" && choices->is_array()) {
    schema = {{"allOf", Json::array({schema, Json{{"enum", *choices}}})}};
  }
  return schema;
}

Json parameter_values(const Json &graph, const Json &overrides)
{
  Json values = Json::object();
  if (const Json *parameters = get(graph, "parameters"); parameters && parameters->is_array()) {
    for (const Json &item : *parameters) {
      const Json *name = get(item, "name");
      if (name && name->is_string() && item.contains("default")) {
        values[name->get<std::string>()] = item["default"];
      }
    }
  }
  if (overrides.is_object()) {
    for (auto it = overrides.begin(); it != overrides.end(); ++it) {
      values[it.key()] = it.value();
    }
  }
  return values;
}

std::vector<ParamRef> find_param_refs(const Json &value, const std::string &path)
{
  std::vector<ParamRef> found;
  if (value.is_object()) {
    if (const Json *name = get(value, "$param")) {
      if (value.size() != 1) {
        found.push_back({path, std::nullopt, "a $param reference must be an object with the single key '$param'"});
      }
      else if (!name->is_string() || !is_graph_id(name->get_ref<const std::string &>())) {
        found.push_back({path, std::nullopt, "the '$param' value must be a parameter name"});
      }
      else {
        found.push_back({path, name->get<std::string>(), std::nullopt});
      }
      return found;
    }
    for (auto it = value.begin(); it != value.end(); ++it) {
      if (it.key().rfind('$', 0) == 0) {
        found.push_back({pointer_join(path, it.key()), std::nullopt, "reserved key '" + it.key() + "'"});
      }
    }
    for (auto it = value.begin(); it != value.end(); ++it) {
      if (it.key().rfind('$', 0) != 0) {
        for (ParamRef &ref : find_param_refs(it.value(), pointer_join(path, it.key()))) {
          found.push_back(std::move(ref));
        }
      }
    }
  }
  else if (value.is_array()) {
    for (size_t i = 0; i < value.size(); i++) {
      for (ParamRef &ref : find_param_refs(value[i], pointer_join(path, i))) {
        found.push_back(std::move(ref));
      }
    }
  }
  return found;
}

Json substitute_params(const Json &value, const Json &values)
{
  if (value.is_object()) {
    if (value.size() == 1 && value.contains("$param")) {
      const Json &name = value["$param"];
      if (!name.is_string() || !values.is_object() || !values.contains(name.get<std::string>())) {
        throw GraphModelError("unknown parameter " + python_json_dumps(name));
      }
      return values[name.get<std::string>()];
    }
    Json out = Json::object();
    for (auto it = value.begin(); it != value.end(); ++it) {
      out[it.key()] = substitute_params(it.value(), values);
    }
    return out;
  }
  if (value.is_array()) {
    Json out = Json::array();
    for (const Json &item : value) {
      out.push_back(substitute_params(item, values));
    }
    return out;
  }
  return value;
}

}  // namespace stk::io
