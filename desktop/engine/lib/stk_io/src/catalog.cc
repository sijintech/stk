/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/catalog.hh"

#include "stk/core/paths.hh"

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

std::vector<std::string> strings(const Json *value)
{
  std::vector<std::string> out;
  if (!value) {
    return out;
  }
  if (value->is_string()) {
    out.push_back(value->get<std::string>());
  }
  else if (value->is_array()) {
    for (const Json &item : *value) {
      if (item.is_string()) {
        out.push_back(item.get<std::string>());
      }
    }
  }
  return out;
}

PortSpec port_from_json(const Json &port)
{
  PortSpec spec;
  spec.name = string_or(port, "name");
  spec.types = strings(get(port, "type"));
  spec.accepts = strings(get(port, "accepts"));
  spec.kinds = strings(get(port, "kind"));
  if (spec.kinds.empty()) {
    spec.kinds = strings(get(port, "kinds"));
  }
  spec.kind_from = string_or(port, "kind_from");
  spec.value_type = string_or(port, "value_type");
  spec.required = get_bool(port, "required", false);
  spec.multi = get_bool(port, "multi", false);
  return spec;
}

std::string localized(const Json &object, std::string_view key, std::string_view language)
{
  const Json *value = get(object, key);
  if (!value) {
    return {};
  }
  if (value->is_string()) {
    return language == "en" ? value->get<std::string>() : std::string();
  }
  return string_or(*value, language);
}

}  // namespace

const ParamSpec *NodeType::param(std::string_view name) const
{
  for (const ParamSpec &p : params) {
    if (p.name == name) {
      return &p;
    }
  }
  return nullptr;
}

const PortSpec *NodeType::input(std::string_view name) const
{
  for (const PortSpec &p : inputs) {
    if (p.name == name) {
      return &p;
    }
  }
  return nullptr;
}

const PortSpec *NodeType::output(std::string_view name) const
{
  for (const PortSpec &p : outputs) {
    if (p.name == name) {
      return &p;
    }
  }
  return nullptr;
}

std::string NodeType::family() const
{
  const auto ref = parse_type(id);
  return ref ? ref->family : std::string();
}

Catalog Catalog::from_json(const Json &document)
{
  if (!document.is_object()) {
    throw GraphModelError("a catalog must be a JSON object");
  }
  Catalog catalog;
  catalog.schema = string_or(document, "schema");
  if (catalog.schema != kCatalogSchema) {
    throw GraphModelError("schema must be 'stk.catalog/1'", "/schema");
  }
  if (const Json *namespaces = get(document, "namespaces"); namespaces && namespaces->is_object()) {
    for (auto it = namespaces->begin(); it != namespaces->end(); ++it) {
      if (it.value().is_number_integer()) {
        catalog.namespaces[it.key()] = it.value().get<int>();
      }
    }
  }
  catalog.port_types = document.value("port_types", Json());
  catalog.kinds = document.value("kinds", Json());
  catalog.value_types = document.value("value_types", Json());
  catalog.client_types = strings(get(document, "client_types"));
  const Json *nodes = get(document, "nodes");
  if (!nodes || !nodes->is_array()) {
    throw GraphModelError("'nodes' must be a list", "/nodes");
  }
  for (size_t i = 0; i < nodes->size(); i++) {
    const Json &entry = (*nodes)[i];
    const std::string path = "/nodes/" + std::to_string(i);
    NodeType type;
    type.raw = entry;
    type.id = string_or(entry, "id");
    type.type = string_or(entry, "type");
    if (!parse_type(type.id)) {
      throw GraphModelError("invalid node type id", path + "/id");
    }
    type.version = int(get_int(entry, "version", 0));
    type.impl_version = int(get_int(entry, "impl_version", 1));
    type.stage = string_or(entry, "stage");
    type.category = string_or(entry, "category");
    type.cache = get_string(entry, "cache", "memory");
    type.title_en = localized(entry, "title", "en");
    type.title_zh = localized(entry, "title", "zh");
    type.description_en = localized(entry, "description", "en");
    type.description_zh = localized(entry, "description", "zh");
    type.time_dependent = get_bool(entry, "time_dependent", false);
    type.deterministic = get_bool(entry, "deterministic", true);
    type.stretch = get_bool(entry, "stretch", false);
    if (const Json *inputs = get(entry, "inputs"); inputs && inputs->is_array()) {
      for (const Json &port : *inputs) {
        type.inputs.push_back(port_from_json(port));
      }
    }
    if (const Json *outputs = get(entry, "outputs"); outputs && outputs->is_array()) {
      for (const Json &port : *outputs) {
        type.outputs.push_back(port_from_json(port));
      }
    }
    type.params_schema = entry.value("params", Json::object());
    std::set<std::string, std::less<>> required;
    for (const std::string &name : strings(get(type.params_schema, "required"))) {
      required.insert(name);
    }
    if (const Json *properties = get(type.params_schema, "properties"); properties && properties->is_object()) {
      for (auto it = properties->begin(); it != properties->end(); ++it) {
        ParamSpec p;
        p.name = it.key();
        p.schema = it.value();
        p.has_default = it.value().contains("default") && !required.count(p.name);
        p.required = !p.has_default;
        p.default_value = p.has_default ? it.value()["default"] : Json();
        p.stage = string_or(it.value(), "x-stk-stage");
        p.widget = string_or(it.value(), "x-stk-widget");
        p.group = string_or(it.value(), "x-stk-group");
        p.unit = string_or(it.value(), "x-stk-unit");
        p.quantity = string_or(it.value(), "x-stk-quantity");
        p.title_zh = string_or(it.value(), "x-stk-title-zh");
        p.field_of = string_or(it.value(), "x-stk-field-of");
        p.choices_from = string_or(it.value(), "x-stk-choices-from");
        p.advanced = get_bool(it.value(), "x-stk-advanced", false);
        type.params.push_back(std::move(p));
      }
    }
    catalog.nodes.push_back(std::move(type));
  }
  return catalog;
}

Catalog Catalog::load(const std::filesystem::path &path)
{
  return from_json(read_json_file(path));
}

const NodeType *Catalog::find(std::string_view id) const
{
  for (const NodeType &type : nodes) {
    if (type.id == id) {
      return &type;
    }
  }
  return nullptr;
}

std::vector<ParamIssue> validate_node_params(const NodeType &type,
                                             std::string_view node_id,
                                             const Json &params,
                                             const Json &declared_values,
                                             const std::vector<std::string> &named,
                                             const std::string &node_path)
{
  std::vector<ParamIssue> issues;
  if (!params.is_object()) {
    return issues;
  }
  const std::string node(node_id);
  const std::string params_path = pointer_join(node_path, "params");
  if (canonical_json(params).size() > 64 * 1024) {
    issues.push_back({"too_large", "Params of node '" + node + "' exceed 65536 bytes", params_path});
  }
  std::map<std::string, std::vector<std::string>> refs;
  std::set<std::string, std::less<>> skip;
  for (auto it = params.begin(); it != params.end(); ++it) {
    const std::string &name = it.key();
    for (const ParamRef &ref : find_param_refs(it.value(), pointer_join(params_path, name))) {
      const bool declared = ref.name && declared_values.contains(*ref.name);
      if (ref.problem || !declared) {
        skip.insert(name);
      }
      if (ref.problem && ref.problem->rfind("reserved key", 0) == 0) {
        issues.push_back({"reserved_key", "Node '" + node + "' param '" + name + "': " + *ref.problem, ref.pointer});
      }
      else if (ref.problem) {
        issues.push_back({"bad_param_ref", "Node '" + node + "' param '" + name + "': " + *ref.problem, ref.pointer});
      }
      else if (std::find(named.begin(), named.end(), *ref.name) == named.end()) {
        issues.push_back({"bad_param_ref",
                          "Node '" + node + "' param '" + name + "' references undeclared parameter '" + *ref.name + "'",
                          ref.pointer});
      }
      else {
        refs[name].push_back(*ref.name);
      }
    }
  }
  for (auto it = params.begin(); it != params.end(); ++it) {
    const std::string &name = it.key();
    const std::string param_path = pointer_join(params_path, name);
    const ParamSpec *spec = type.param(name);
    if (!spec) {
      issues.push_back({"unknown_param", "'" + type.id + "' has no param '" + name + "'", param_path});
      continue;
    }
    if (skip.count(name)) {
      continue;
    }
    Json effective;
    try {
      effective = substitute_params(it.value(), declared_values);
    }
    catch (const GraphModelError &) {
      continue;
    }
    for (const SchemaIssue &issue : check_value(effective, spec->schema, param_path)) {
      const auto ref = refs.find(name);
      if (ref != refs.end()) {
        std::string via;
        for (const std::string &r : ref->second) {
          via += (via.empty() ? "'" : ", '") + r + "'";
        }
        issues.push_back({"param_ref_type",
                          "Node '" + node + "' param '" + name + "' (via parameter " + via + "): " + issue.message,
                          issue.path});
      }
      else {
        issues.push_back({"invalid_param", "Node '" + node + "' param '" + name + "': " + issue.message, issue.path});
      }
    }
  }
  for (const ParamSpec &spec : type.params) {
    if (spec.required && !params.contains(spec.name)) {
      issues.push_back(
          {"missing_param", "Node '" + node + "' ('" + type.id + "') needs param '" + spec.name + "'", params_path});
    }
  }
  return issues;
}

/* ------------------------------------------------------------------------------------------ */
/* Presets */

namespace {

bool is_preset_id(std::string_view id)
{
  if (id.empty() || id.size() > 64) {
    return false;
  }
  const auto ok = [](char c, bool first) {
    return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || (!first && (c == '_' || c == '-'));
  };
  for (size_t i = 0; i < id.size(); i++) {
    if (!ok(id[i], i == 0)) {
      return false;
    }
  }
  return true;
}

}  // namespace

Preset Preset::from_json(const Json &document, std::string_view id)
{
  if (!is_preset_id(id)) {
    throw GraphModelError("invalid preset id '" + std::string(id) + "'");
  }
  Preset preset;
  preset.id = std::string(id);
  if (document.is_object() && get_string(document, "schema") == kGraphSchema) {
    preset.graph = document;
  }
  else if (document.is_object() && get(document, "graph") && document["graph"].is_object()) {
    preset.graph = document["graph"];
    preset.name = string_or(document, "name");
    preset.description = string_or(document, "description");
    if (const Json *bindings = get(document, "bindings"); bindings && bindings->is_array()) {
      for (const Json &binding : *bindings) {
        if (binding.is_object()) {
          preset.bindings.push_back({string_or(binding, "name"), string_or(binding, "description")});
        }
      }
    }
  }
  else {
    throw GraphModelError("Preset '" + preset.id + "' is neither an stk.graph/1 document nor {\"graph\": {...}}");
  }
  if (preset.name.empty()) {
    preset.name = string_or(preset.graph, "name");
  }
  if (preset.name.empty()) {
    preset.name = preset.id;
  }
  if (preset.description.empty()) {
    preset.description = string_or(preset.graph, "description");
  }
  return preset;
}

Preset Preset::load(const std::filesystem::path &path)
{
  return from_json(read_json_file(path), core::path_to_utf8(path.stem()));
}

std::vector<Preset> Preset::load_directory(const std::filesystem::path &directory)
{
  std::vector<std::filesystem::path> files;
  for (const auto &entry : std::filesystem::directory_iterator(directory)) {
    if (entry.is_regular_file() && entry.path().extension() == ".json" &&
        is_preset_id(core::path_to_utf8(entry.path().stem())))
    {
      files.push_back(entry.path());
    }
  }
  std::sort(files.begin(), files.end(), [](const auto &a, const auto &b) {
    return core::path_to_utf8(a.filename()) < core::path_to_utf8(b.filename());
  });
  std::vector<Preset> presets;
  for (const auto &file : files) {
    presets.push_back(load(file));
  }
  return presets;
}

/* ------------------------------------------------------------------------------------------ */
/* Forms */

namespace {

std::vector<std::string> pointer_tokens(std::string_view pointer)
{
  std::vector<std::string> tokens;
  if (pointer.empty()) {
    return tokens;
  }
  size_t start = 1;
  for (;;) {
    const size_t slash = pointer.find('/', start);
    std::string token(pointer.substr(start, slash == std::string_view::npos ? std::string_view::npos : slash - start));
    std::string decoded;
    for (size_t i = 0; i < token.size(); i++) {
      if (token[i] == '~' && i + 1 < token.size()) {
        decoded.push_back(token[i + 1] == '1' ? '/' : '~');
        i++;
      }
      else {
        decoded.push_back(token[i]);
      }
    }
    tokens.push_back(std::move(decoded));
    if (slash == std::string_view::npos) {
      break;
    }
    start = slash + 1;
  }
  return tokens;
}

Json schema_at_tokens(const Json &schema, const std::vector<std::string> &tokens, size_t i)
{
  if (i == tokens.size()) {
    return schema;
  }
  if (!schema.is_object()) {
    return schema.is_boolean() ? schema : Json(true);
  }
  std::vector<Json> candidates;
  const std::string &token = tokens[i];
  const Json *properties = get(schema, "properties");
  if (const Json *sub = properties ? get(*properties, token) : nullptr) {
    candidates.push_back(schema_at_tokens(*sub, tokens, i + 1));
  }
  else if (const Json *extra = get(schema, "additionalProperties"); extra && extra->is_object()) {
    candidates.push_back(schema_at_tokens(*extra, tokens, i + 1));
  }
  const bool numeric = !token.empty() && std::all_of(token.begin(), token.end(), [](char c) { return c >= '0' && c <= '9'; });
  if (numeric) {
    const size_t index = size_t(std::stoull(token));
    const Json *prefix = get(schema, "prefixItems");
    if (prefix && prefix->is_array() && index < prefix->size()) {
      candidates.push_back(schema_at_tokens((*prefix)[index], tokens, i + 1));
    }
    else if (const Json *items = get(schema, "items")) {
      candidates.push_back(schema_at_tokens(*items, tokens, i + 1));
    }
  }
  for (const char *key : {"anyOf", "oneOf", "allOf"}) {
    if (const Json *branches = get(schema, key); branches && branches->is_array()) {
      for (const Json &branch : *branches) {
        Json sub = schema_at_tokens(branch, tokens, i);
        if (!(sub.is_boolean() && sub.get<bool>())) {
          candidates.push_back(std::move(sub));
        }
      }
    }
  }
  if (candidates.empty()) {
    return true;
  }
  if (candidates.size() == 1) {
    return candidates[0];
  }
  return Json{{"anyOf", candidates}};
}

std::string derived_widget(const std::string &type)
{
  if (type == "boolean") {
    return "checkbox";
  }
  if (type == "number" || type == "integer") {
    return "number";
  }
  if (type == "string") {
    return "text";
  }
  return type; /* step, vector3, int3, range, enum, json */
}

}  // namespace

Json schema_at(const Json &schema, std::string_view pointer)
{
  return schema_at_tokens(schema, pointer_tokens(pointer), 0);
}

std::vector<ParameterForm> parameter_forms(const Json &graph, const Catalog &catalog)
{
  std::vector<ParameterForm> forms;
  const Json *parameters = get(graph, "parameters");
  if (!parameters || !parameters->is_array()) {
    return forms;
  }
  const Json *nodes = get(graph, "nodes");
  for (const Json &item : *parameters) {
    const Json *name = get(item, "name");
    if (!name || !name->is_string()) {
      continue;
    }
    ParameterForm form;
    form.name = name->get<std::string>();
    form.declaration = item;
    const std::string type = string_or(item, "type");
    Json declared;
    try {
      declared = parameter_schema(item);
    }
    catch (const GraphModelError &) {
      declared = Json::object();
    }
    std::vector<Json> all{declared};
    form.annotations = Json::object();
    bool data_stage = false;
    if (nodes && nodes->is_array()) {
      for (const Json &node : *nodes) {
        const NodeType *node_type = catalog.find(string_or(node, "type"));
        const Json *params = get(node, "params");
        if (!params || !params->is_object()) {
          continue;
        }
        for (auto it = params->begin(); it != params->end(); ++it) {
          for (const ParamRef &ref : find_param_refs(it.value())) {
            if (!ref.name || *ref.name != form.name) {
              continue;
            }
            form.references.push_back(string_or(node, "id") + "." + it.key() + ref.pointer);
            const ParamSpec *spec = node_type ? node_type->param(it.key()) : nullptr;
            if (!spec) {
              continue;
            }
            const std::string family = node_type->family();
            if (spec->stage == "data" || family == "source" || family == "filter" || family == "analysis") {
              data_stage = true;
            }
            const Json sub = schema_at(spec->schema, ref.pointer);
            if (!(sub.is_boolean() && sub.get<bool>())) {
              all.push_back(sub);
            }
            if (form.references.size() == 1) {
              const Json &source = ref.pointer.empty() ? spec->schema : sub;
              if (source.is_object()) {
                for (auto a = source.begin(); a != source.end(); ++a) {
                  if (a.key().rfind("x-stk-", 0) == 0 || a.key() == "title" || a.key() == "description") {
                    form.annotations[a.key()] = a.value();
                  }
                }
              }
              form.widget = string_or(form.annotations, "x-stk-widget");
            }
          }
        }
      }
    }
    form.stage = data_stage ? "data" : "client";
    if (form.widget.empty() || type == "enum" || type == "step") {
      form.widget = derived_widget(type);
    }
    form.schema = all.size() == 1 ? all[0] : Json{{"allOf", all}};
    forms.push_back(std::move(form));
  }
  return forms;
}

}  // namespace stk::io
