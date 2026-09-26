/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/form_json.hh"

#include <cctype>
#include <cmath>
#include <map>

namespace stk::ui {

template<class json> FormValue value_from_json(const json &v);
template<class json> SchemaNode schema_impl(const json &schema, const std::string &name, int depth);

namespace {

template<class json> std::string text_of(const json &j, bool zh)
{
  if (j.is_string()) {
    return j.template get<std::string>();
  }
  if (j.is_object()) {
    const char *k = zh ? "zh" : "en";
    if (j.contains(k) && j[k].is_string()) {
      return j[k].template get<std::string>();
    }
    if (!zh && j.contains("en") && j["en"].is_string()) {
      return j["en"].template get<std::string>();
    }
  }
  return {};
}

template<class json> bool is_type(const json &s, const char *t)
{
  if (!s.is_object() || !s.contains("type")) {
    return false;
  }
  const json &ty = s["type"];
  if (ty.is_string()) {
    return ty.template get<std::string>() == t;
  }
  if (ty.is_array()) {
    for (const json &x : ty) {
      if (x.is_string() && x.template get<std::string>() == t) {
        return true;
      }
    }
  }
  return false;
}

template<class json> bool is_null_schema(const json &s)
{
  return s.is_object() && s.size() == 1 && is_type(s, "null");
}

template<class json> bool is_step(const json &branches)
{
  if (!branches.is_array() || branches.size() != 2) {
    return false;
  }
  bool has_int = false, has_enum = false;
  for (const json &b : branches) {
    if (is_type(b, "integer")) {
      has_int = true;
    }
    else if (b.is_object() && b.contains("enum") && b["enum"].is_array()) {
      bool ok = true;
      for (const json &e : b["enum"]) {
        ok &= e.is_string() && (e == "latest" || e == "first");
      }
      has_enum = ok;
    }
  }
  return has_int && has_enum;
}

template<class json> void annotations(const json &s, SchemaNode &n)
{
  if (!s.is_object()) {
    return;
  }
  auto str = [&](const char *k, std::string &dst) {
    if (s.contains(k) && s[k].is_string()) {
      dst = s[k].template get<std::string>();
    }
  };
  if (s.contains("title")) {
    n.title = text_of(s["title"], false);
    if (s["title"].is_object()) {
      n.title_zh = text_of(s["title"], true);
    }
  }
  str("x-stk-title-zh", n.title_zh);
  if (s.contains("description")) {
    n.description = text_of(s["description"], false);
    if (s["description"].is_object()) {
      n.description_zh = text_of(s["description"], true);
    }
  }
  str("x-stk-widget", n.widget);
  str("x-stk-stage", n.stage);
  str("x-stk-group", n.group);
  str("x-stk-unit", n.unit);
  str("x-stk-quantity", n.quantity);
  str("x-stk-choices-from", n.choices_from);
  str("pattern", n.pattern);
  if (s.contains("x-stk-advanced") && s["x-stk-advanced"].is_boolean()) {
    n.advanced = s["x-stk-advanced"].template get<bool>();
  }
  auto num = [&](const char *k, std::optional<double> &dst) {
    if (s.contains(k) && s[k].is_number()) {
      dst = s[k].template get<double>();
      return true;
    }
    return false;
  };
  if (!num("minimum", n.minimum) && num("exclusiveMinimum", n.minimum)) {
    n.exclusive_min = true;
  }
  if (!num("maximum", n.maximum) && num("exclusiveMaximum", n.maximum)) {
    n.exclusive_max = true;
  }
}

/** Fixed-size numeric array (items number/integer with minItems == maxItems, or prefixItems). */
template<class json> bool number_array(const json &s, SchemaNode &n)
{
  if (!is_type(s, "array")) {
    return false;
  }
  if (s.contains("prefixItems") && s["prefixItems"].is_array()) {
    n.nullable_items = !s["prefixItems"].empty();
    for (const json &p : s["prefixItems"]) {
      if (!is_type(p, "number") && !is_type(p, "integer")) {
        return false;
      }
      n.nullable_items &= is_type(p, "null");
    }
    n.items = int(s["prefixItems"].size());
    return n.items > 0 && n.items <= 4;
  }
  if (!s.contains("items") || !s.contains("minItems") || !s.contains("maxItems") || s["minItems"] != s["maxItems"]) {
    return false;
  }
  const json &it = s["items"];
  if (!is_type(it, "number") && !is_type(it, "integer")) {
    return false;
  }
  n.integer_items = is_type(it, "integer") && !is_type(it, "number");
  n.items = s["minItems"].template get<int>();
  if (it.contains("minimum") && it["minimum"].is_number()) {
    n.minimum = it["minimum"].template get<double>();
  }
  if (it.contains("maximum") && it["maximum"].is_number()) {
    n.maximum = it["maximum"].template get<double>();
  }
  return n.items > 0 && n.items <= 4;
}

/** Classifies a non-anyOf branch; returns false for Json. */
template<class json> bool classify(const json &s, SchemaNode &n, int depth)
{
  if (!s.is_object()) {
    return false;
  }
  if (s.contains("enum") && s["enum"].is_array()) {
    n.type = SchemaType::Enum;
    for (const json &e : s["enum"]) {
      if (e.is_null()) {
        n.nullable = true;
      }
      n.enum_values.push_back(value_from_json(e));
    }
    return true;
  }
  if (s.contains("const")) {
    return false;
  }
  if (is_type(s, "null") && !is_type(s, "number") && !is_type(s, "integer") && !is_type(s, "string") &&
      !is_type(s, "boolean"))
  {
    return false;
  }
  if (is_type(s, "null")) {
    n.nullable = true;
  }
  if (is_type(s, "number")) {
    n.type = SchemaType::Number;
  }
  else if (is_type(s, "integer")) {
    n.type = SchemaType::Integer;
  }
  else if (is_type(s, "boolean")) {
    n.type = SchemaType::Boolean;
  }
  else if (is_type(s, "string")) {
    n.type = SchemaType::String;
  }
  else if (is_type(s, "object") && depth == 0) {
    n.type = SchemaType::Object;
    if (s.contains("properties") && s["properties"].is_object()) {
      for (const auto &[k, v] : s["properties"].items()) {
        n.properties.push_back(schema_impl(v, k, depth + 1));
      }
    }
  }
  else if (number_array(s, n)) {
    n.type = SchemaType::NumberArray;
  }
  else {
    return false;
  }
  return true;
}

}  // namespace

template<class json> FormValue value_from_json(const json &v)
{
  if (v.is_null()) {
    return FormValue::null();
  }
  if (v.is_boolean()) {
    return FormValue::boolean(v.template get<bool>());
  }
  if (v.is_number()) {
    return FormValue::number(v.template get<double>());
  }
  if (v.is_string()) {
    return FormValue::string(v.template get<std::string>());
  }
  if (v.is_array()) {
    std::vector<double> a;
    std::vector<bool> nulls;
    for (const json &x : v) {
      if (!x.is_number() && !x.is_null()) {
        return FormValue::string(v.dump());
      }
      a.push_back(x.is_null() ? 0.0 : x.template get<double>());
      nulls.push_back(x.is_null());
    }
    FormValue value = FormValue::array(std::move(a));
    value.arr_null = std::move(nulls);
    return value;
  }
  return FormValue::string(v.dump());
}

template<class json> SchemaNode schema_impl(const json &schema, const std::string &name, int depth)
{
  SchemaNode n;
  n.name = name;
  annotations(schema, n);
  bool ok = false;
  const char *combo = schema.is_object() ? (schema.contains("anyOf") ? "anyOf" : (schema.contains("oneOf") ? "oneOf" : nullptr)) : nullptr;
  if (combo && schema[combo].is_array()) {
    const json &br = schema[combo];
    if (is_step(br)) {
      n.type = SchemaType::Step;
      ok = true;
    }
    else {
      std::vector<const json *> rest;
      for (const json &b : br) {
        if (is_null_schema(b)) {
          n.nullable = true;
        }
        else {
          rest.push_back(&b);
        }
      }
      if (rest.size() == 1) {
        SchemaNode inner;
        annotations(*rest[0], inner);
        if (classify(*rest[0], inner, depth + 1) && inner.type != SchemaType::Object) {
          const bool nullable = n.nullable || inner.nullable;
          SchemaNode ann = n;
          n = inner;
          n.name = name;
          n.nullable = nullable;
          /* Outer annotations win. */
          n.title = ann.title.empty() ? n.title : ann.title;
          n.title_zh = ann.title_zh.empty() ? n.title_zh : ann.title_zh;
          n.description = ann.description.empty() ? n.description : ann.description;
          n.description_zh = ann.description_zh;
          n.widget = ann.widget;
          n.stage = ann.stage;
          n.group = ann.group;
          n.unit = ann.unit;
          n.quantity = ann.quantity;
          n.choices_from = ann.choices_from;
          n.advanced = ann.advanced;
          if (ann.minimum) {
            n.minimum = ann.minimum;
            n.exclusive_min = ann.exclusive_min;
          }
          if (ann.maximum) {
            n.maximum = ann.maximum;
            n.exclusive_max = ann.exclusive_max;
          }
          ok = true;
        }
      }
      else if (n.widget == "field") {
        /* Field reference: "Polar" or {name, component}; edited by name. */
        n.type = SchemaType::String;
        ok = true;
      }
    }
  }
  else if (schema.is_object() && schema.contains("allOf") && schema["allOf"].is_array()) {
    /* parameter_schema() with choices: {"allOf": [base, {"enum": [...]}]} */
    for (const json &b : schema["allOf"]) {
      if (b.is_object() && b.contains("enum")) {
        ok = classify(b, n, depth);
      }
    }
  }
  else {
    ok = classify(schema, n, depth);
  }
  if (!ok) {
    n.type = SchemaType::Json;
  }
  if (schema.is_object() && schema.contains("default")) {
    const json &d = schema["default"];
    n.default_value = (n.type == SchemaType::Json && !d.is_null()) ? FormValue::string(d.is_string() ? d.template get<std::string>() : d.dump())
                                                                   : value_from_json(d);
  }
  return n;
}

namespace {

using stk::io::Json;

/** Fills what `n` does not declare from `src` (limits, annotations). */
void inherit(SchemaNode &n, const SchemaNode &src)
{
  if (!n.minimum && src.minimum) {
    n.minimum = src.minimum;
    n.exclusive_min = src.exclusive_min;
  }
  if (!n.maximum && src.maximum) {
    n.maximum = src.maximum;
    n.exclusive_max = src.exclusive_max;
  }
  auto fill = [](std::string &dst, const std::string &from) {
    if (dst.empty()) {
      dst = from;
    }
  };
  fill(n.stage, src.stage);
  fill(n.widget, src.widget);
  fill(n.group, src.group);
  fill(n.unit, src.unit);
  fill(n.quantity, src.quantity);
  fill(n.title_zh, src.title_zh);
  fill(n.description, src.description);
  fill(n.description_zh, src.description_zh);
  fill(n.choices_from, src.choices_from);
  fill(n.pattern, src.pattern);
  n.advanced = n.advanced || src.advanced;
  if (n.type == SchemaType::Json && src.type != SchemaType::Json && src.type != SchemaType::Object) {
    n.type = src.type;
    n.enum_values = src.enum_values;
    n.items = src.items;
    n.integer_items = src.integer_items;
    n.nullable_items = src.nullable_items;
  }
}

/** A stk.graph/1 parameter declaration {name, type, default, minimum, maximum, choices, label,
 * description, unit} (suan.graph.schema.parameter_schema types). */
SchemaNode declaration_node(const Json &decl)
{
  SchemaNode n;
  n.name = decl.value("name", std::string());
  const std::string kind = decl.value("type", std::string("json"));
  if (kind == "number") {
    n.type = SchemaType::Number;
  }
  else if (kind == "integer") {
    n.type = SchemaType::Integer;
  }
  else if (kind == "boolean") {
    n.type = SchemaType::Boolean;
  }
  else if (kind == "string") {
    n.type = SchemaType::String;
  }
  else if (kind == "step") {
    n.type = SchemaType::Step;
  }
  else if (kind == "vector3" || kind == "int3") {
    n.type = SchemaType::NumberArray;
    n.items = 3;
    n.integer_items = kind == "int3";
    n.widget = kind;
  }
  else if (kind == "range") {
    n.type = SchemaType::NumberArray;
    n.items = 2;
    n.widget = "range";
    n.nullable_items = true;
  }
  else if (kind == "enum") {
    n.type = SchemaType::Enum;
  }
  else {
    n.type = SchemaType::Json;
  }
  if (decl.contains("choices") && decl["choices"].is_array()) {
    n.type = SchemaType::Enum;
    for (const Json &c : decl["choices"]) {
      n.enum_values.push_back(value_from_json(c));
    }
  }
  if (decl.contains("minimum") && decl["minimum"].is_number()) {
    n.minimum = decl["minimum"].template get<double>();
  }
  if (decl.contains("maximum") && decl["maximum"].is_number()) {
    n.maximum = decl["maximum"].template get<double>();
  }
  if (decl.contains("label")) {
    n.title = text_of(decl["label"], false);
  }
  if (decl.contains("description")) {
    n.description = text_of(decl["description"], false);
  }
  if (decl.contains("unit") && decl["unit"].is_string()) {
    n.unit = decl["unit"].template get<std::string>();
  }
  if (decl.contains("default")) {
    n.default_value = n.type == SchemaType::Json ? FormValue::string(decl["default"].dump())
                                                 : value_from_json(decl["default"]);
  }
  return n;
}

}  // namespace

SchemaNode form_schema(const std::vector<stk::io::ParameterForm> &forms)
{
  SchemaNode root;
  root.type = SchemaType::Object;
  for (const stk::io::ParameterForm &f : forms) {
    SchemaNode n = declaration_node(f.declaration);
    n.name = f.name;
    /* Annotations of the first reference, then the limits of every referencing node param
     * (form.schema is {"allOf": [declared, node-param schemas...]}). */
    SchemaNode ann;
    annotations(f.annotations, ann);
    inherit(n, ann);
    if (f.schema.is_object() && f.schema.contains("allOf") && f.schema["allOf"].is_array()) {
      const Json &all = f.schema["allOf"];
      for (size_t i = 1; i < all.size(); i++) {
        inherit(n, schema_impl(all[i], n.name, 1));
      }
    }
    /* stk_io decides the stage (data when any reference is data-stage or a source/filter/analysis
     * node), matching suan.graph. */
    if (!f.stage.empty()) {
      n.stage = f.stage;
    }
    if (n.widget.empty()) {
      n.widget = f.widget;
    }
    root.properties.push_back(std::move(n));
  }
  return root;
}

SchemaNode node_params_schema(const stk::io::NodeType &node)
{
  SchemaNode n = schema_impl(node.params_schema, node.id, 0);
  n.title = node.title_en;
  n.title_zh = node.title_zh;
  n.description = node.description_en;
  n.description_zh = node.description_zh;
  return n;
}

SchemaNode node_params_schema(const stk::io::Json &catalog, std::string_view node_id)
{
  try {
    const stk::io::Catalog cat = stk::io::Catalog::from_json(catalog);
    std::string id(node_id);
    const stk::io::NodeType *node = cat.find(id);
    if (!node && id.find('@') == std::string::npos) {
      for (const stk::io::NodeType &t : cat.nodes) {
        if (t.type == id) {
          node = &t;
        }
      }
    }
    if (node) {
      return node_params_schema(*node);
    }
  }
  catch (const std::exception &) {
  }
  SchemaNode empty;
  empty.type = SchemaType::Object;
  return empty;
}

SchemaNode preset_schema(const stk::io::Json &preset, const stk::io::Json &catalog)
{
  SchemaNode root;
  try {
    const stk::io::Catalog cat = stk::io::Catalog::from_json(catalog);
    const stk::io::Json &graph = preset.contains("graph") ? preset["graph"] : preset;
    root = form_schema(stk::io::parameter_forms(graph, cat));
  }
  catch (const std::exception &) {
    root.type = SchemaType::Object;
  }
  root.name = preset.value("id", std::string());
  root.title = preset.value("name", std::string());
  return root;
}

template<class json> json value_to_json(const FormValue &v, const SchemaNode &node)
{
  switch (v.kind) {
    case FormValue::Kind::Null:
      return nullptr;
    case FormValue::Kind::Bool:
      return v.b;
    case FormValue::Kind::Number:
      if ((node.type == SchemaType::Integer || node.type == SchemaType::Step) && std::floor(v.num) == v.num &&
          std::fabs(v.num) < 9.0e15)
      {
        return int64_t(v.num);
      }
      return v.num;
    case FormValue::Kind::String:
      if (node.type == SchemaType::Json) {
        json parsed = json::parse(v.str, nullptr, false);
        return parsed.is_discarded() ? json(v.str) : parsed;
      }
      return v.str;
    case FormValue::Kind::Array: {
      json a = json::array();
      for (size_t i = 0; i < v.arr.size(); i++) {
        const double d = v.arr[i];
        if (i < v.arr_null.size() && v.arr_null[i]) {
          a.push_back(nullptr);
        }
        else if (node.integer_items && std::floor(d) == d) {
          a.push_back(int64_t(d));
        }
        else {
          a.push_back(d);
        }
      }
      return a;
    }
  }
  return nullptr;
}

template<class json> json values_to_json(const FormModel &model, const SchemaNode &object)
{
  json out = json::object();
  for (const SchemaNode &p : object.properties) {
    if (model.has(p.name)) {
      out[p.name] = value_to_json<json>(model.get(p.name), p);
    }
  }
  return out;
}


/* Public overloads: nlohmann::json (sorted keys) and nlohmann::ordered_json (= stk::io::Json,
 * declaration order, preferred for forms). */
SchemaNode schema_from_json(const nlohmann::json &schema, const std::string &name, int depth)
{
  return schema_impl(schema, name, depth);
}
SchemaNode schema_from_json(const nlohmann::ordered_json &schema, const std::string &name, int depth)
{
  return schema_impl(schema, name, depth);
}
FormValue form_value_from_json(const nlohmann::json &v)
{
  return value_from_json(v);
}
FormValue form_value_from_json(const nlohmann::ordered_json &v)
{
  return value_from_json(v);
}
nlohmann::json form_value_to_json(const FormValue &v, const SchemaNode &node)
{
  return value_to_json<nlohmann::json>(v, node);
}
nlohmann::json form_values_to_json(const FormModel &model, const SchemaNode &object)
{
  return values_to_json<nlohmann::json>(model, object);
}
nlohmann::ordered_json form_values_to_ordered_json(const FormModel &model, const SchemaNode &object)
{
  return values_to_json<nlohmann::ordered_json>(model, object);
}

}  // namespace stk::ui
