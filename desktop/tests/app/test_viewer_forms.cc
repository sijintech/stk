/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The Properties editor's forms for all 7 presets (JSON Schema -> stk_ui build_form,
 * grouped by x-stk-group, data vs client stage boxes), as layout goldens in zh and en (fake text
 * measurer, no GPU; STK_UPDATE_GOLDENS=1 rewrites desktop/tests/app/golden/), plus the Viewer
 * editor's sidebar and the Probe editor with a pick. */

#include <cstdlib>

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include "support.hh"
#include "viewer_support.hh"

using namespace stk;
using stk::io::Json;
using stk::wmtest::AppFixture;

namespace {

const ui::Widget *find(const AppFixture &f, const std::string &key)
{
  return f.screen.ui() ? f.screen.ui()->find(key) : nullptr;
}

bool has_label(const AppFixture &f, const std::string &prefix, const std::string &text)
{
  for (const auto &b : f.screen.ui()->blocks()) {
    if (b->name().rfind(prefix, 0) != 0) {
      continue;
    }
    for (const ui::Widget &w : b->widgets()) {
      if (w.text.find(text) != std::string::npos) {
        return true;
      }
    }
  }
  return false;
}

/** The UI blocks of one area as JSON (from the screen dump). */
nlohmann::ordered_json area_blocks(const AppFixture &f, const std::string &area)
{
  const nlohmann::ordered_json j = nlohmann::ordered_json::parse(stk::wmtest::dump_screen(f.screen));
  nlohmann::ordered_json out = nlohmann::ordered_json::array();
  for (const auto &b : j["blocks"]) {
    if (b["name"].get<std::string>().rfind(area + "/", 0) == 0) {
      out.push_back(b);
    }
  }
  return out;
}

std::string golden_text(const nlohmann::ordered_json &doc)
{
  std::string out = "{\n";
  bool first = true;
  for (auto it = doc.begin(); it != doc.end(); ++it) {
    out += first ? "" : ",\n";
    first = false;
    out += "  \"" + it.key() + "\": [\n";
    for (size_t i = 0; i < it->size(); i++) {
      out += "    " + (*it)[i].dump() + (i + 1 < it->size() ? ",\n" : "\n");
    }
    out += "  ]";
  }
  return out + "\n}\n";
}

void compare_golden(const std::string &name, const std::string &got)
{
  const std::string path = std::string(STK_APP_GOLDEN_DIR) + "/" + name;
  if (const char *u = std::getenv("STK_UPDATE_GOLDENS"); u && *u == '1') {
    ASSERT_TRUE(stk::apptest::write_text(path, got)) << path;
    return;
  }
  const std::string want = stk::apptest::read_text(path);
  ASSERT_FALSE(want.empty()) << "missing golden " << path << " (run with STK_UPDATE_GOLDENS=1)";
  EXPECT_EQ(got, want) << "layout differs from " << path;
}

class PropertiesForms : public ::testing::TestWithParam<const char *> {};

}  // namespace

TEST_P(PropertiesForms, AllPresetsMatchGoldens)
{
  const std::string lang = GetParam();
  AppFixture f(lang, 1.0f, 1280, 900);
  app::ViewerState &vs = f.shell->store().viewer();
  vs.set_metadata(stk::apptest::repo_presets(), stk::apptest::repo_catalog());
  ASSERT_EQ(vs.presets().size(), 7u);
  nlohmann::ordered_json doc = nlohmann::ordered_json::object();
  for (const app::PresetInfo &p : vs.presets()) {
    vs.select_preset(p.id);
    f.drv->frame();
    const ui::SchemaNode &schema = vs.schema();
    ASSERT_FALSE(schema.properties.empty()) << p.id;
    bool data = false, client = false;
    for (const ui::SchemaNode &m : schema.properties) {
      /* Every parameter has a widget (steps: the mode dropdown; vectors: one field per axis). */
      const bool found = find(f, m.name) || find(f, m.name + "/mode") || find(f, m.name + "/0") ||
                         find(f, m.name + "/set");
      EXPECT_TRUE(found) << p.id << ": no widget for " << m.name;
      EXPECT_TRUE(m.stage == "data" || m.stage == "client") << p.id << "." << m.name << " stage '" << m.stage << "'";
      (m.stage == "data" ? data : client) = true;
    }
    /* Data and client stages are marked. */
    EXPECT_EQ(has_label(f, "a3/", std::string(f.shell->store().tr("props.stage.data"))), data) << p.id;
    EXPECT_EQ(has_label(f, "a3/", std::string(f.shell->store().tr("props.stage.client"))), client) << p.id;
    EXPECT_TRUE(find(f, "preset")) << p.id;
    doc[p.id] = area_blocks(f, "a3");
  }
  compare_golden("props_forms_" + lang + ".json", golden_text(doc));
}

INSTANTIATE_TEST_SUITE_P(App, PropertiesForms, ::testing::Values("en", "zh"),
                         [](const ::testing::TestParamInfo<const char *> &i) { return std::string(i.param); });

TEST(ViewerEditors, ColormapParametersUseTheColormapList)
{
  AppFixture f("en", 1.0f, 1280, 900);
  app::ViewerState &vs = f.shell->store().viewer();
  vs.set_metadata(stk::apptest::repo_presets(), stk::apptest::repo_catalog());
  auto cms = std::make_shared<std::vector<ui::ColormapItem>>();
  for (const char *name : {"viridis", "plasma", "cividis", "coolwarm", "gray", "turbo"}) {
    cms->push_back({name, {ui::Color::rgb(0x000000), ui::Color::rgb(0xffffff)}});
  }
  vs.set_colormaps(cms);
  vs.select_preset("slice");
  f.drv->frame();
  const ui::Widget *w = find(f, "colormap");
  ASSERT_NE(w, nullptr);
  EXPECT_EQ(w->type, ui::WidgetType::ColormapDropdown);
  const std::string before = vs.form().get("colormap").str;
  EXPECT_FALSE(before.empty());
}

TEST(ViewerEditors, DropOnTheViewerAndTheOpenDialog)
{
  AppFixture f("en", 1.0f, 1280, 900);
  app::ViewerState &vs = f.shell->store().viewer();
  /* Drag and drop of a .stkp onto the Viewer area. */
  wm::Event e;
  e.type = wm::EventType::Drop;
  e.paths = {stk::apptest::fixture_stkp().string()};
  const auto [x, y] = AppFixture::center(f.area("a2").find_region("main")->rect());
  e.x = x;
  e.y = y;
  f.drv->send(e);
  EXPECT_EQ(vs.source().kind, app::SourceKind::Payload);
  ASSERT_NE(vs.payload(), nullptr);
  /* File > Open: the dialog takes a path (a result folder here). */
  stk::apptest::TempDir d("viewer-open-dialog");
  stk::apptest::write_result_dir(d.path() / "result");
  vs.open_dialog = true;
  f.drv->frame();
  ASSERT_NE(find(f, "viewer_open/path"), nullptr);
  vs.open_dialog_path = (d.path() / "result").string();
  f.drv->frame();
  const auto [bx, by] = f.widget_center("viewer_open/open");
  f.drv->click(bx, by);
  f.drv->frame();
  EXPECT_FALSE(vs.open_dialog);
  EXPECT_EQ(vs.source().kind, app::SourceKind::ResultDir);
  EXPECT_EQ(find(f, "viewer_open/path"), nullptr) << "closed";
  /* The export dialog: size, magnification x1..x8, transparency, overlays, sequence, path. */
  vs.export_dialog = true;
  f.drv->frame();
  for (const char *k : {"viewer_export/width", "viewer_export/height", "viewer_export/magnification",
                        "viewer_export/transparent", "viewer_export/overlays", "viewer_export/sequence",
                        "viewer_export/path", "viewer_export/export"})
  {
    EXPECT_NE(find(f, k), nullptr) << k;
  }
  EXPECT_EQ(find(f, "viewer_export/magnification")->items.size(), 8u);
}

TEST(ViewerEditors, SidebarAndProbeWithAPayload)
{
  AppFixture f("en", 1.0f, 1280, 900);
  app::ViewerState &vs = f.shell->store().viewer();
  ASSERT_TRUE(vs.open_path(stk::apptest::fixture_stkp().string())) << vs.open_error();
  f.drv->frame();
  /* Layers with visibility and opacity; camera presets; no steps for a plain payload. */
  EXPECT_NE(find(f, "surface_layer/visible"), nullptr);
  EXPECT_NE(find(f, "surface_layer/opacity"), nullptr);
  EXPECT_EQ(find(f, "legend/opacity"), nullptr) << "overlays have no opacity";
  for (const char *p : {"preset.iso", "preset.+x", "preset.-x", "preset.+y", "preset.-y", "preset.+z", "preset.-z"}) {
    EXPECT_NE(find(f, p), nullptr) << p;
  }
  EXPECT_TRUE(has_label(f, "a2/sidebar", std::string(f.shell->store().tr("viewer.steps.none"))));
  /* Toggling a layer from the sidebar. */
  auto [x, y] = f.widget_center("surface_layer/visible");
  f.drv->click(x, y);
  f.drv->frame();
  EXPECT_FALSE(vs.layers()[0].visible);
  /* The Probe editor (bottom strip, tab 1) shows a pick. */
  f.area("a4").set_active_tab(1);
  app::PickInfo pick;
  pick.layer_id = "surface_layer";
  pick.layer_name = "Domain surfaces";
  pick.layer_type = "triangles";
  pick.element = 7;
  pick.physical = {1.5, 2.25, 3.0};
  vs.set_pick(pick);
  f.drv->frame();
  EXPECT_TRUE(has_label(f, "a4/", "1.5, 2.25, 3"));
  EXPECT_TRUE(has_label(f, "a4/", "Domain surfaces"));
  EXPECT_EQ(vs.probe().status, app::ProbeState::Status::Unavailable) << "a file payload has no data source";
}
