/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * JSON adapters for the form builder:
 *  - JSON Schema fragments (stk.catalog/1 node params) to SchemaNode;
 *  - stk_io's parameter forms (preset/graph parameters that inherit the schema, stage and
 *    annotations of the node params referencing them through {"$param": name}) to SchemaNode;
 *  - form values back to JSON.
 * stk::io::Json is nlohmann::ordered_json, so members keep their declaration order.
 */
#pragma once

#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "stk/io/catalog.hh"
#include "stk/ui/form.hh"

namespace stk::ui {

/**
 * Converts a JSON Schema fragment. Top-level objects (depth 0) become SchemaType::Object with
 * their properties; nested objects, variable-length arrays and unrecognised shapes become Json.
 * Recognised anyOf shapes: step (integer >= 0 | "latest" | "first"), T | null (nullable T),
 * field references (string | {name, component}) -> String.
 */
SchemaNode schema_from_json(const nlohmann::json &schema, const std::string &name = {}, int depth = 0);
SchemaNode schema_from_json(const nlohmann::ordered_json &schema, const std::string &name = {}, int depth = 0);

/** The params schema of a catalog node type. */
SchemaNode node_params_schema(const stk::io::NodeType &node);
/** By id ("stk.source.muferro_frame@1") or unversioned type, from a stk.catalog/1 document. */
SchemaNode node_params_schema(const stk::io::Json &catalog, std::string_view node_id);

/**
 * Form schema of graph parameters from stk::io::parameter_forms(): each declaration ({name, type,
 * default, minimum, maximum, choices, label, description, unit}) keeps what it declares and
 * inherits the rest (limits, x-stk-widget, x-stk-group, x-stk-unit, x-stk-title-zh, description)
 * from the referencing node params; the stage is stk_io's (data | client).
 */
SchemaNode form_schema(const std::vector<stk::io::ParameterForm> &forms);
/** preset_schema = form_schema(parameter_forms(preset.graph, Catalog::from_json(catalog))). */
SchemaNode preset_schema(const stk::io::Json &preset, const stk::io::Json &catalog);

FormValue form_value_from_json(const nlohmann::json &v);
FormValue form_value_from_json(const nlohmann::ordered_json &v);
/** Integers stay integers, Json-typed members are parsed back from their text. */
nlohmann::json form_value_to_json(const FormValue &v, const SchemaNode &node);
/** {name: value} for every member of `object` present in the model. */
nlohmann::json form_values_to_json(const FormModel &model, const SchemaNode &object);
nlohmann::ordered_json form_values_to_ordered_json(const FormModel &model, const SchemaNode &object);

}  // namespace stk::ui
