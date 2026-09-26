/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Form builder against the stk.catalog/1 catalog and the muferro-domains preset. */
#include <gtest/gtest.h>

#include "stk/ui/form_json.hh"
#include "support.hh"

using namespace stk::ui;
using nlohmann::ordered_json;
using stk::ui::test::Harness;

namespace {

const ordered_json &catalog()
{
  static const ordered_json c =
      ordered_json::parse(test::read_text(std::string(STK_REPO_ROOT) + "/docs/specs/catalog/stk-catalog-m1.json"));
  return c;
}

const ordered_json &preset()
{
  static const ordered_json p =
      ordered_json::parse(test::read_text(std::string(STK_REPO_ROOT) + "/suan/graph/presets/muferro-domains.json"));
  return p;
}

std::vector<std::string> names(const SchemaNode &n)
{
  std::vector<std::string> out;
  for (const SchemaNode &p : n.properties) {
    out.push_back(p.name);
  }
  return out;
}

}  // namespace

TEST(FormSchema, PresetParametersInheritNodeSchemas)
{
  const SchemaNode s = preset_schema(preset(), catalog());
  ASSERT_EQ(s.type, SchemaType::Object);
  EXPECT_EQ(names(s), (std::vector<std::string>{"step", "min_magnitude", "max_angle_deg", "film_detection",
                                                "smooth_iterations", "view"}));
  const SchemaNode &step = *s.property("step");
  EXPECT_EQ(step.type, SchemaType::Step);
  EXPECT_EQ(step.stage, "data") << "inherited from stk.source.muferro_frame params.step";
  EXPECT_EQ(step.widget, "step");
  EXPECT_EQ(step.choices_from, "evaluator");

  const SchemaNode &mm = *s.property("min_magnitude");
  EXPECT_EQ(mm.type, SchemaType::Number);
  EXPECT_EQ(mm.minimum, 0.0);
  EXPECT_FALSE(mm.maximum.has_value());
  EXPECT_EQ(mm.unit, "unspecified");
  EXPECT_EQ(mm.stage, "data");
  EXPECT_EQ(mm.title, "|P| threshold");
  ASSERT_TRUE(mm.default_value);
  EXPECT_EQ(mm.default_value->num, 0.1);
  EXPECT_NE(mm.description.find("unclassified"), std::string::npos);

  const SchemaNode &ang = *s.property("max_angle_deg");
  EXPECT_EQ(ang.minimum, 0.0);
  EXPECT_EQ(ang.maximum, 180.0);
  EXPECT_FALSE(ang.exclusive_min) << "the preset declares an inclusive minimum";

  const SchemaNode &film = *s.property("film_detection");
  EXPECT_EQ(film.type, SchemaType::Boolean);
  EXPECT_EQ(film.default_value->b, true) << "the preset default wins over the node default (false)";

  const SchemaNode &it = *s.property("smooth_iterations");
  EXPECT_EQ(it.type, SchemaType::Integer);
  EXPECT_EQ(it.minimum, 0.0);
  EXPECT_EQ(it.maximum, 500.0);
  EXPECT_EQ(it.stage, "data");

  const SchemaNode &view = *s.property("view");
  EXPECT_EQ(view.type, SchemaType::Enum);
  ASSERT_EQ(view.enum_values.size(), 7u);
  EXPECT_EQ(view.enum_values[0].str, "iso");
  EXPECT_EQ(view.stage, "client") << "inherited from stk.view.camera params.preset";
}

TEST(FormSchema, CatalogNodeParams)
{
  const SchemaNode s = node_params_schema(catalog(), "stk.source.muferro_frame@1");
  EXPECT_EQ(names(s), (std::vector<std::string>{"dataset", "step", "policy", "spacing", "origin", "length_unit", "unit",
                                                "quantity", "precision"}));
  EXPECT_EQ(s.title_zh, "muFerro \xe5\xb8\xa7");
  EXPECT_EQ(s.property("dataset")->type, SchemaType::String);
  EXPECT_EQ(s.property("dataset")->pattern, "^[A-Za-z][A-Za-z0-9_]{0,7}$");
  EXPECT_EQ(s.property("step")->type, SchemaType::Step);
  EXPECT_EQ(s.property("policy")->type, SchemaType::Enum);
  const SchemaNode &sp = *s.property("spacing");
  EXPECT_EQ(sp.type, SchemaType::NumberArray);
  EXPECT_EQ(sp.items, 3);
  EXPECT_TRUE(sp.nullable);
  EXPECT_EQ(sp.widget, "vector3");
  EXPECT_TRUE(sp.default_value && sp.default_value->is_null());
  EXPECT_EQ(s.property("quantity")->type, SchemaType::String);
  EXPECT_TRUE(s.property("quantity")->nullable);

  /* Every catalog node converts; members keep declaration order. */
  for (const auto &node : catalog()["nodes"]) {
    const SchemaNode n = node_params_schema(catalog(), node["id"].get<std::string>());
    EXPECT_EQ(n.type, SchemaType::Object) << node["id"];
    EXPECT_EQ(n.properties.size(), node["params"]["properties"].size()) << node["id"];
  }
  const SchemaNode cam = node_params_schema(catalog(), "stk.view.camera");
  EXPECT_TRUE(cam.property("zoom")->exclusive_min);
  EXPECT_EQ(cam.property("preset")->stage, "client");
}

TEST(FormSchema, JsonSchemaShapes)
{
  auto conv = [](const char *text) { return schema_from_json(ordered_json::parse(text), "x", 1); };
  EXPECT_EQ(conv(R"({"type": ["number", "null"]})").type, SchemaType::Number);
  EXPECT_TRUE(conv(R"({"type": ["number", "null"]})").nullable);
  const SchemaNode a = conv(R"({"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}], "title": "N"})");
  EXPECT_EQ(a.type, SchemaType::Integer);
  EXPECT_TRUE(a.nullable);
  EXPECT_EQ(a.minimum, 1.0);
  EXPECT_EQ(a.title, "N");
  const SchemaNode ex = conv(R"({"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 180})");
  EXPECT_TRUE(ex.exclusive_min && ex.exclusive_max);
  EXPECT_EQ(conv(R"({"allOf": [{"type": "string"}, {"enum": ["a", "b"]}]})").type, SchemaType::Enum);
  const SchemaNode range = conv(R"({"type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}], "minItems": 2, "maxItems": 2})");
  EXPECT_EQ(range.type, SchemaType::NumberArray);
  EXPECT_EQ(range.items, 2);
  EXPECT_EQ(conv(R"({"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 32})").type, SchemaType::Json);
  EXPECT_EQ(conv(R"({"type": "object", "properties": {"a": {"type": "number"}}})").type, SchemaType::Json);
  const SchemaNode t = conv(R"({"type": "string", "title": {"en": "Name", "zh": "名称"}, "x-stk-group": "g", "x-stk-advanced": true})");
  EXPECT_EQ(t.title, "Name");
  EXPECT_EQ(t.title_zh, "\xe5\x90\x8d\xe7\xa7\xb0");
  EXPECT_EQ(t.group, "g");
  EXPECT_TRUE(t.advanced);
  const SchemaNode j = conv(R"({"anyOf": [{"const": "all"}, {"type": "array"}], "default": "all", "x-stk-widget": "json"})");
  EXPECT_EQ(j.type, SchemaType::Json);
  EXPECT_EQ(j.default_value->str, "all");
}

TEST(FormBuilder, PresetFormWidgetsAndEditing)
{
  Harness h;
  const SchemaNode s = preset_schema(preset(), catalog());
  FormModel model;
  int changes = 0;
  model.on_change = [&](const std::string &, const FormValue &) { changes++; };
  h.window = {420, 700};
  h.ui = [&](Context &ctx) { build_form(ctx.block("form", {0, 0, 420, 700}).layout(), s, model); };
  h.frame();
  EXPECT_EQ(h.w("step/mode").type, WidgetType::Dropdown);
  EXPECT_EQ(h.ctx->find("step"), nullptr) << "no step number while 'latest'";
  EXPECT_EQ(h.w("min_magnitude").type, WidgetType::Number);
  EXPECT_EQ(h.w("max_angle_deg").type, WidgetType::Slider);
  EXPECT_EQ(h.w("film_detection").type, WidgetType::Checkbox);
  EXPECT_EQ(h.w("smooth_iterations").type, WidgetType::Number);
  EXPECT_TRUE(h.w("smooth_iterations").props.integer);
  EXPECT_EQ(h.w("smooth_iterations").props.max, 500.0);
  EXPECT_EQ(h.w("view").type, WidgetType::Dropdown);
  EXPECT_EQ(h.w("view").items[0], "\xe7\xad\x89\xe8\xbd\xb4\xe6\xb5\x8b") << "enum.iso in zh";
  EXPECT_EQ(h.w("min_magnitude").props.unit, "") << "no suffix for 'unspecified'";
  const std::string tip = h.w("min_magnitude").tooltip;
  EXPECT_NE(tip.find("unclassified"), std::string::npos);
  EXPECT_NE(tip.find("\xe5\x8d\x95\xe4\xbd\x8d\xef\xbc\x9a\xe5\x8d\x95\xe4\xbd\x8d\xe6\x9c\xaa\xe6\x8c\x87\xe5\xae\x9a"),
            std::string::npos)
      << "unit line (单位：单位未指定) in the tooltip: " << tip;
  /* zh labels come from the param.* glossary when the schema has no x-stk-title-zh. */
  bool label = false;
  for (const auto &b : h.ctx->blocks()) {
    for (const Widget &w : b->widgets()) {
      label |= w.type == WidgetType::Label && w.text == "|P| \xe9\x98\x88\xe5\x80\xbc";
    }
  }
  EXPECT_TRUE(label);

  /* Defaults, then edits through events. */
  EXPECT_EQ(model.get("film_detection").b, true);
  h.click("min_magnitude");
  h.type("0.25");
  h.key(Key::Enter);
  EXPECT_EQ(model.get("min_magnitude").num, 0.25);
  h.click("film_detection");
  EXPECT_FALSE(model.get("film_detection").b);
  h.click("view");
  h.click("popup/2");
  EXPECT_EQ(model.get("view").str, "-x");
  h.click("step/mode");
  h.click("popup/2");
  EXPECT_EQ(model.get("step").kind, FormValue::Kind::Number);
  ASSERT_NE(h.ctx->find("step"), nullptr) << "step number appears";
  h.click("step");
  h.type("12");
  h.key(Key::Enter);
  EXPECT_GT(changes, 4);

  const nlohmann::json out = form_values_to_json(model, s);
  EXPECT_EQ(out["step"], 12);
  EXPECT_TRUE(out["step"].is_number_integer());
  EXPECT_EQ(out["min_magnitude"], 0.25);
  EXPECT_EQ(out["max_angle_deg"], 180.0);
  EXPECT_EQ(out["film_detection"], false);
  EXPECT_TRUE(out["smooth_iterations"].is_number_integer());
  EXPECT_EQ(out["smooth_iterations"], 30);
  EXPECT_EQ(out["view"], "-x");
}

TEST(FormBuilder, StageFilterAndEnglishTitles)
{
  Harness h;
  h.catalog.set_language("en");
  const SchemaNode s = preset_schema(preset(), catalog());
  FormModel model;
  FormOptions opts;
  opts.stages = StageFilter::Client;
  h.ui = [&](Context &ctx) { build_form(ctx.block("form", {0, 0, 420, 700}).layout(), s, model, opts); };
  h.frame();
  EXPECT_NE(h.ctx->find("view"), nullptr);
  EXPECT_EQ(h.ctx->find("min_magnitude"), nullptr);
  EXPECT_EQ(h.ctx->find("step/mode"), nullptr);
  opts.stages = StageFilter::Data;
  h.frame();
  EXPECT_EQ(h.ctx->find("view"), nullptr);
  bool label = false;
  for (const auto &b : h.ctx->blocks()) {
    for (const Widget &w : b->widgets()) {
      label |= w.type == WidgetType::Label && w.text == "|P| threshold";
    }
  }
  EXPECT_TRUE(label);
}

TEST(FormBuilder, GroupsAdvancedUnitsAndColormaps)
{
  /* Connector-style parameters (suan/connectors/mupro/inputs.py annotations). */
  const ordered_json schema = ordered_json::parse(R"({
    "type": "object",
    "properties": {
      "name": {"type": "string", "title": "Name"},
      "nx": {"type": "integer", "minimum": 1, "title": "Grid points", "x-stk-group": "system",
             "x-stk-unit": "grid_index", "default": 64},
      "dt": {"type": "number", "exclusiveMinimum": 0, "title": "Time step", "x-stk-group": "system",
             "x-stk-unit": "nm", "default": 0.01},
      "material": {"type": "string", "title": "Material file", "x-stk-widget": "file", "x-stk-group": "material"},
      "cmap": {"type": "string", "x-stk-widget": "colormap", "default": "plasma"},
      "seed": {"type": "integer", "x-stk-advanced": true, "default": 7}
    }
  })");
  const SchemaNode s = schema_from_json(schema);
  Harness h;
  h.window = {420, 700};
  FormModel model;
  std::vector<std::string> browsed;
  FormOptions opts;
  opts.on_browse = [&](const std::string &n) { browsed.push_back(n); };
  opts.colormaps = std::make_shared<std::vector<ColormapItem>>(
      std::vector<ColormapItem>{{"viridis", {Color::rgb(0x440154), Color::rgb(0xfde725)}},
                                {"plasma", {Color::rgb(0x0d0887), Color::rgb(0xf0f921)}}});
  h.ui = [&](Context &ctx) { build_form(ctx.block("form", {0, 0, 420, 700}).layout(), s, model, opts); };
  h.frame();
  /* Groups become panels (open), advanced members a collapsed panel. */
  EXPECT_EQ(h.w("group.system").type, WidgetType::PanelHeader);
  EXPECT_EQ(h.w("group.material").type, WidgetType::PanelHeader);
  EXPECT_NE(h.w("group.system/nx").key.find("group.system"), std::string::npos);
  EXPECT_EQ(h.w("advanced").type, WidgetType::PanelHeader);
  EXPECT_EQ(h.ctx->find("seed"), nullptr) << "advanced panel starts collapsed";
  h.click("advanced");
  EXPECT_NE(h.ctx->find("seed"), nullptr);
  EXPECT_EQ(model.get("seed").num, 7.0);
  /* Units: localized suffix for real units; grid_index localized too. */
  EXPECT_EQ(h.w("dt").props.unit, "nm");
  EXPECT_TRUE(h.w("dt").props.exclusive_min);
  EXPECT_EQ(h.w("nx").props.unit, "\xe7\xbd\x91\xe6\xa0\xbc\xe7\xb4\xa2\xe5\xbc\x95") << "unit.grid_index (zh)";
  /* x-stk-widget: file -> text field + browse button; colormap -> colormap dropdown. */
  h.click("material/browse");
  EXPECT_EQ(browsed, (std::vector<std::string>{"material"}));
  EXPECT_EQ(h.w("cmap").type, WidgetType::ColormapDropdown);
  EXPECT_EQ(h.w("cmap").index.value(), 1);
  h.click("cmap");
  h.click("popup/0");
  EXPECT_EQ(model.get("cmap").str, "viridis");
  /* Values round-trip to JSON with integers kept integral. */
  const nlohmann::json out = form_values_to_json(model, s);
  EXPECT_TRUE(out["nx"].is_number_integer());
  EXPECT_EQ(out["cmap"], "viridis");
  EXPECT_TRUE(out["name"].is_null());
}

TEST(FormBuilder, NodeFormNullableVectorsAndExclusiveLimits)
{
  Harness h;
  const SchemaNode frame = node_params_schema(catalog(), "stk.source.muferro_frame");
  const SchemaNode cam = node_params_schema(catalog(), "stk.view.camera");
  FormModel fm, cm;
  h.window = {420, 900};
  h.ui = [&](Context &ctx) {
    Layout &l = ctx.block("form", {0, 0, 420, 900}).layout();
    build_form(l.scope("frame"), frame, fm);
    build_form(l.scope("camera"), cam, cm);
  };
  h.frame();
  EXPECT_TRUE(fm.get("spacing").is_null());
  ASSERT_NE(h.ctx->find("frame/spacing/set"), nullptr);
  EXPECT_EQ(h.ctx->find("frame/spacing/0"), nullptr);
  h.click("frame/spacing/set");
  ASSERT_EQ(fm.get("spacing").kind, FormValue::Kind::Array);
  ASSERT_NE(h.ctx->find("frame/spacing/2"), nullptr);
  EXPECT_EQ(h.w("frame/spacing/2").text, "Z");
  h.click("frame/spacing/1");
  h.type("0.5");
  h.key(Key::Enter);
  EXPECT_EQ(fm.get("spacing").arr, (std::vector<double>{0, 0.5, 0}));
  /* Nullable string: empty text means null. */
  h.click("frame/quantity");
  h.type("polarization");
  h.key(Key::Enter);
  EXPECT_EQ(fm.get("quantity").str, "polarization");
  h.click("frame/quantity");
  h.key(Key::A, MOD_CTRL);
  h.key(Key::Backspace);
  h.key(Key::Enter);
  EXPECT_TRUE(fm.get("quantity").is_null());
  /* exclusiveMinimum 0: typing 0 keeps the value strictly positive. */
  h.click("camera/zoom");
  h.type("0");
  h.key(Key::Enter);
  EXPECT_GT(cm.get("zoom").num, 0.0);
}
