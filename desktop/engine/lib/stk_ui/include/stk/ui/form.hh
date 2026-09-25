/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Forms generated from JSON Schema (the stk.catalog/1 node parameter subset) and the catalog's
 * form annotations: x-stk-widget, x-stk-stage (data | client), x-stk-group, x-stk-unit,
 * x-stk-advanced, x-stk-title-zh; title/description become label/tooltip; default/minimum/maximum
 * (and the exclusive variants) drive the value and the number limits.
 *
 * The builder takes a small SchemaNode tree so ui_core does not depend on stk_io; form_json.hh
 * converts nlohmann::json (catalog node params, preset parameters) into it.
 */
#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "stk/ui/ui.hh"

namespace stk::ui {

/** A form value: JSON null, boolean, number, string or a fixed-size number array. */
struct FormValue {
  enum class Kind : uint8_t { Null, Bool, Number, String, Array };
  Kind kind = Kind::Null;
  bool b = false;
  double num = 0.0;
  std::string str;
  std::vector<double> arr;

  static FormValue null() { return {}; }
  static FormValue boolean(bool v);
  static FormValue number(double v);
  static FormValue string(std::string v);
  static FormValue array(std::vector<double> v);
  bool is_null() const { return kind == Kind::Null; }
  /** Short text for display and debugging ("null", "true", "0.1", "latest", "[1, 2, 3]"). */
  std::string to_string() const;
  bool operator==(const FormValue &o) const;
};

enum class SchemaType : uint8_t {
  Object,
  Number,
  Integer,
  Boolean,
  String,
  Enum,
  NumberArray, /**< Fixed-size array of numbers (vector3, int3, range). */
  Step,        /**< integer >= 0 | "latest" | "first" (stk graph step). */
  Json,        /**< Anything else: edited as JSON text. */
};
const char *schema_type_name(SchemaType t);

struct SchemaNode {
  SchemaType type = SchemaType::Json;
  std::string name;
  std::string title;
  std::string title_zh;
  std::string description;
  std::string description_zh;
  std::optional<double> minimum;
  std::optional<double> maximum;
  bool exclusive_min = false;
  bool exclusive_max = false;
  std::vector<FormValue> enum_values;
  std::optional<FormValue> default_value;
  bool nullable = false;
  int items = 0;              /**< NumberArray size. */
  bool integer_items = false; /**< int3 */
  std::string pattern;
  std::string widget;       /**< x-stk-widget */
  std::string stage;        /**< x-stk-stage: "data" | "client" */
  std::string group;        /**< x-stk-group */
  std::string unit;         /**< x-stk-unit */
  std::string quantity;     /**< x-stk-quantity */
  std::string choices_from; /**< x-stk-choices-from */
  bool advanced = false;    /**< x-stk-advanced */
  std::vector<SchemaNode> properties; /**< Object members, in declaration order. */

  const SchemaNode *property(std::string_view name) const;
};

/** Values edited by a form, keyed by property name. */
class FormModel {
 public:
  /** Fills values that are missing with the schema defaults (null when there is none). */
  void init_defaults(const SchemaNode &object);
  bool has(const std::string &name) const { return values_.count(name) != 0; }
  FormValue get(const std::string &name) const;
  void set(const std::string &name, FormValue v);
  const std::map<std::string, FormValue> &values() const { return values_; }
  /** Incremented on every set(). */
  uint64_t version() const { return version_; }
  /** Called after a widget changed a value. */
  std::function<void(const std::string &name, const FormValue &value)> on_change;

 private:
  std::map<std::string, FormValue> values_;
  uint64_t version_ = 0;
};

enum class StageFilter : uint8_t { All, Data, Client };

struct FormOptions {
  StageFilter stages = StageFilter::All;
  /** Group members by x-stk-group into collapsible panels. */
  bool group_panels = true;
  /** Show x-stk-advanced members inline (otherwise in a collapsed "Advanced" panel). */
  bool show_advanced = false;
  /** Language for title vs x-stk-title-zh; empty = the catalog's current language. */
  std::string lang;
  /** Colormaps offered by x-stk-widget "colormap" string fields. */
  std::shared_ptr<const std::vector<ColormapItem>> colormaps;
  /** Browse button for x-stk-widget "path"/"file" fields (WP9 wires native file dialogs). */
  std::function<void(const std::string &name)> on_browse;
};

/** Localized label of a schema member (title, x-stk-title-zh, or the prettified name). */
std::string schema_label(const SchemaNode &node, std::string_view lang);

/**
 * Builds the widgets for every member of `object` into `layout` (Blender property-split rows).
 * Widget keys are the member names ("min_magnitude", "spacing/0", "step/mode", ...).
 */
void build_form(Layout &layout, const SchemaNode &object, FormModel &model, const FormOptions &opts = {});

}  // namespace stk::ui
