/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include "stk/io/schema.hh"
#include <string>

namespace stk::app {
/** Literature wire rules preserve numeric token types. JSON Schema's integer
 * also accepts 3.0, while the local service requires an actual integer token. */
inline bool literature_token_types(const io::Json &value, const io::Json &shape)
{
  if (!shape.is_object()) { return true; }
  if (shape.contains("type")) {
    const auto &type = shape.at("type");
    if (type == "integer" && !io::is_integer_token(value)) { return false; }
  }
  if (shape.contains("const") && io::python_json_dumps(value, true, true) != io::python_json_dumps(shape.at("const"), true, true)) { return false; }
  for (const auto key : {"anyOf", "oneOf"}) {
    if (shape.contains(key)) {
      bool valid = false;
      for (const auto &branch : shape.at(key)) {
        if (io::check_value(value, branch).empty() && literature_token_types(value, branch)) { valid = true; break; }
      }
      if (!valid) { return false; }
    }
  }
  if (shape.contains("allOf")) {
    for (const auto &branch : shape.at("allOf")) { if (!literature_token_types(value, branch)) { return false; } }
  }
  if (value.is_object()) {
    for (auto it = value.begin(); it != value.end(); ++it) {
      if (shape.contains("properties") && shape.at("properties").contains(it.key())) {
        if (!literature_token_types(it.value(), shape.at("properties").at(it.key()))) { return false; }
      }
      else if (shape.contains("additionalProperties") && shape.at("additionalProperties").is_object() &&
          !literature_token_types(it.value(), shape.at("additionalProperties"))) { return false; }
    }
  }
  if (value.is_array()) {
    for (size_t index = 0; index < value.size(); ++index) {
      if (shape.contains("prefixItems") && index < shape.at("prefixItems").size()) {
        if (!literature_token_types(value[index], shape.at("prefixItems")[index])) { return false; }
      }
      else if (shape.contains("items") && !literature_token_types(value[index], shape.at("items"))) { return false; }
    }
  }
  return true;
}
inline bool literature_shape(const io::Json &value, const io::Json &shape)
{
  return io::check_value(value, shape).empty() && literature_token_types(value, shape);
}
}  // namespace stk::app
