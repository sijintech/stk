/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/ui/form_json.hh"
#include "support.hh"

using namespace stk::ui;
using stk::ui::test::Harness;
using nlohmann::json;

namespace {
SchemaNode volume_schema()
{
  const auto catalog = json::parse(test::read_text(std::string(STK_REPO_ROOT) + "/docs/specs/catalog/stk-catalog-m1.json"));
  const auto preset = json::parse(test::read_text(std::string(STK_REPO_ROOT) + "/suan/graph/presets/volume.json"));
  const SchemaNode all = preset_schema(preset, catalog);
  SchemaNode only;
  only.type = SchemaType::Object;
  only.properties = {*all.property("opacity")};
  return only;
}

struct TransferForm : ::testing::Test {
  Harness h;
  SchemaNode schema = volume_schema();
  FormModel model;
  void SetUp() override
  {
    h.window = {300, 700};
    h.ui = [&](Context &ctx) { build_form(ctx.block("form", {0, 0, 300, 700}).layout(), schema, model); };
    h.frame();
  }
  json points() { return form_values_to_json(model, schema)["opacity"]; }
  void edit(const char *key, const char *value)
  {
    h.click(key);
    h.type(value);
    h.key(Key::Enter);
  }
};
}

TEST_F(TransferForm, AddEditRemoveRoundTripsAndClamps)
{
  EXPECT_EQ(schema.properties[0].stage, "client");
  EXPECT_EQ(h.w("opacity").type, WidgetType::PanelHeader);
  EXPECT_EQ(h.w("opacity/preview").type, WidgetType::CurvePreview);
  EXPECT_FALSE(h.w("opacity/preview").focusable());
  EXPECT_FALSE(h.w("opacity/0/remove").enabled);
  int changes = 0;
  model.on_change = [&](const std::string &name, const FormValue &) { EXPECT_EQ(name, "opacity"); changes++; };
  h.click("opacity/add");
  EXPECT_EQ(points(), json::parse("[[0,0],[0.5,0.4],[1,0.8]]"));
  edit("opacity/1/x", "0.1234567890123");
  EXPECT_DOUBLE_EQ(points()[1][0].get<double>(), 0.1234567890123);
  edit("opacity/1/alpha", "2");
  EXPECT_EQ(points()[1][1], 1);
  edit("opacity/1/x", "-5");
  EXPECT_EQ(points()[1][0], 0);
  EXPECT_EQ(h.w("opacity/preview").curve[1].y, 1);
  h.click("opacity/1/remove");
  EXPECT_EQ(points(), json::parse("[[0,0],[1,0.8]]"));
  EXPECT_FALSE(h.w("opacity/1/remove").enabled);
  EXPECT_EQ(changes, 5);
}

TEST_F(TransferForm, AutomaticResetAndInvalidImportedValues)
{
  h.click("opacity/auto");
  EXPECT_TRUE(points().is_null());
  EXPECT_EQ(h.ctx->find("opacity/preview"), nullptr) << "automatic categorical opacity is not a scalar ramp";
  h.click("opacity/auto");
  EXPECT_EQ(points(), json::parse("[[0,0],[1,0.8]]"));
  model.set("opacity", FormValue::string(" null \n"));
  h.frame();
  EXPECT_TRUE(h.w("opacity/auto").boolean.value());
  h.click("opacity/reset");
  EXPECT_FALSE(points().is_null());
  for (const char *invalid : {"oops", "[]", "[[0,0]]", "[[0,0],[2,1]]", "[[0,0],[1,-1]]",
                              "[[false,0],[1,1]]", "[[0,0],[1,1,0]]", "[[0,0],[1,1e999]]"}) {
    model.set("opacity", FormValue::string(invalid));
    const uint64_t version = model.version();
    h.frame();
    EXPECT_NE(h.ctx->find("opacity/json"), nullptr) << invalid;
    EXPECT_EQ(h.ctx->find("opacity/preview"), nullptr);
    EXPECT_EQ(model.version(), version) << "drawing does not replace imported invalid values";
    h.click("opacity/reset");
    EXPECT_EQ(points(), json::parse("[[0,0],[1,0.8]]"));
  }
}

TEST_F(TransferForm, LimitsSortingAndDuplicatePositions)
{
  model.set("opacity", FormValue::string("[[1,0.2],[0,0],[1,0.8]]"));
  h.frame();
  EXPECT_EQ(h.w("opacity/0/x").number.value(), 0);
  h.click("opacity/add");
  EXPECT_EQ(points(), json::parse("[[0,0],[0.5,0.4],[1,0.2],[1,0.8]]"))
      << "insertion interpolates the effective curve; duplicate positions use the last alpha";
  model.set("opacity", FormValue::string("[[0.5,0.1],[0.5,0.9]]"));
  h.frame();
  h.click("opacity/add");
  EXPECT_EQ(points(), json::parse("[[0.25,0.9],[0.5,0.1],[0.5,0.9]]"));
  json max = json::array();
  for (int i = 0; i < 64; i++) {
    max.push_back({double(i) / 63, 0.5});
  }
  model.set("opacity", FormValue::string(max.dump()));
  h.frame();
  EXPECT_FALSE(h.w("opacity/add").enabled);
  max.push_back({1, 1});
  model.set("opacity", FormValue::string(max.dump()));
  h.frame();
  EXPECT_NE(h.ctx->find("opacity/json"), nullptr);
}

TEST_F(TransferForm, PreviewUsesLastDuplicateAndEndpointExtensions)
{
  model.set("opacity", FormValue::string("[[0.25,0.1],[0.25,0.6],[0.75,0.6]]"));
  h.frame();
  const auto &w = h.w("opacity/preview");
  const Rect plot = w.rect.inset(5 * h.ctx->style().pixel, 5 * h.ctx->style().pixel);
  int segments = 0;
  for (const DrawCmd &cmd : h.ctx->draw_list().cmds) {
    if (cmd.type == CmdType::Triangle && cmd.p[0].x >= plot.x && cmd.p[0].x <= plot.x1() &&
        cmd.p[0].y >= plot.y && cmd.p[0].y <= plot.y1()) {
      segments++;
      EXPECT_NEAR(cmd.p[0].y, plot.y1() - 0.6 * plot.h, h.ctx->style().pixel + 0.001);
    }
  }
  EXPECT_EQ(segments, 6) << "three horizontal segments including both endpoint extensions";
}
