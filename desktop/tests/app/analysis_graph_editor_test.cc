/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/script_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/wm/layout_store.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cmath>
#include <cstdlib>
#include <filesystem>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;

class AnalysisGraphEditorTest : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"analysis-graph-editor"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  Json presets = {{"presets", Json::array({io::read_json_file(fs::path(STK_REPO_ROOT) /
      "suan/graph/presets/muferro-domains.json")})}};
  Json catalog = io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json");

  ViewerState &viewer() { return f.shell->store().viewer(); }
  EditorArea &area() { return f.area("a2"); }
  const ui::Widget *widget(const char *key) { return f.screen.ui()->find(key); }

  void SetUp() override
  {
    viewer().prefetch_neighbours = false;
    viewer().set_auto_evaluate(false);
    viewer().set_metadata(presets, catalog);
    fs::create_directories(dir.path() / "run");
    ASSERT_TRUE(viewer().open_path(core::path_to_utf8(dir.path() / "run"), "muferro-domains"));
    ASSERT_TRUE(area().set_tab_type(0, kEditorAnalysisGraph));
    f.screen.set_maximized(&area());
    area().find_region(EditorArea::kSidebar)->set_size_1x(370);
    f.drv->frame();
    ASSERT_EQ(viewer().evaluations_started(), 0);
  }

  void TearDown() override { EXPECT_EQ(viewer().evaluations_started(), 0); }

  bool has_text(const std::string &text)
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.text.find(text) != std::string::npos) { return true; }
      }
    }
    return false;
  }

  int row_named(const ui::TableSpec &table, const std::string &name)
  {
    for (int row = 0; row < table.rows; ++row) { if (table.cell(row, 0) == name) { return row; } }
    return -1;
  }

  void select_node(const int index)
  {
    ASSERT_NE(widget("graph_node_select"), nullptr);
    widget("graph_node_select")->index.assign(index);
    f.drv->frame();
    ASSERT_EQ(widget("graph_node_select")->index.value(), index);
  }
};

TEST_F(AnalysisGraphEditorTest, InspectorDistinguishesExplicitCatalogDefaultsNullAndParameterReferences)
{
  ASSERT_NE(widget("graph_fit"), nullptr); EXPECT_TRUE(widget("graph_fit")->enabled);
  ASSERT_NE(widget("graph_validate"), nullptr); EXPECT_FALSE(widget("graph_validate")->enabled);
  ASSERT_NO_FATAL_FAILURE(select_node(2)); // Orientation classification.
  ASSERT_NE(widget("graph_node_parameters"), nullptr);
  ASSERT_TRUE(widget("graph_node_parameters")->table);
  auto table = *widget("graph_node_parameters")->table;
  const int threshold = row_named(table, "min_magnitude");
  const int offset = row_named(table, "component_offset");
  const int directions = row_named(table, "directions");
  ASSERT_GE(threshold, 0); ASSERT_GE(offset, 0); ASSERT_GE(directions, 0);
  EXPECT_EQ(table.cell(threshold, 2), f.shell->store().tr("analysis_graph.origin.explicit"));
  EXPECT_EQ(table.cell(offset, 2), f.shell->store().tr("analysis_graph.origin.default"));
  EXPECT_EQ(table.cell(offset, 1), "0");
  EXPECT_EQ(table.cell(directions, 1), "null");
  EXPECT_EQ(table.cell(directions, 2), f.shell->store().tr("analysis_graph.origin.default"));
  table.selected.assign(threshold); f.drv->frame();
  EXPECT_TRUE(has_text("$min_magnitude"));
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.submitted")) + ": 0.1"));
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.declared_default")) + ": 0.1"));
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  f.drv->frame();
  EXPECT_EQ(widget("graph_node_select")->index.value(), 2);
  EXPECT_EQ(widget("graph_node_parameters")->table->selected.value(), threshold);
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.submitted")) + ": 0.75"));
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.declared_default")) + ": 0.1"));
  ASSERT_NE(widget("graph_links"), nullptr);
  EXPECT_GT(widget("graph_links")->table->rows, 0);
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.freshness"))));

  // A supplied null has a different origin from the same catalog default.
  presets["presets"][0]["graph"]["nodes"][2]["params"]["directions"] = nullptr;
  viewer().set_metadata(presets, catalog); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(select_node(2));
  table = *widget("graph_node_parameters")->table;
  const int explicit_null = row_named(table, "directions"); ASSERT_GE(explicit_null, 0);
  EXPECT_EQ(table.cell(explicit_null, 1), "null");
  EXPECT_EQ(table.cell(explicit_null, 2), f.shell->store().tr("analysis_graph.origin.explicit"));
}

TEST_F(AnalysisGraphEditorTest, MissingRequiredParameterAndUnavailableDisplayedGraphStayVisibleAsSuch)
{
  presets["presets"][0]["graph"]["nodes"][0]["params"].erase("binding");
  viewer().set_metadata(presets, catalog); f.drv->frame();
  ASSERT_TRUE(widget("graph_node_parameters")->table);
  const auto table = *widget("graph_node_parameters")->table;
  const int binding = row_named(table, "binding"); ASSERT_GE(binding, 0);
  EXPECT_EQ(table.cell(binding, 2), f.shell->store().tr("analysis_graph.origin.missing"));
  ASSERT_NE(widget("graph_mode"), nullptr);
  widget("graph_mode")->index.assign(1); f.drv->frame();
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.no_displayed_graph"))));
  EXPECT_EQ(widget("graph_node_parameters"), nullptr);
  EXPECT_EQ(widget("graph_validate"), nullptr);
  EXPECT_FALSE(widget("graph_fit")->enabled);
  widget("graph_mode")->index.assign(0); f.drv->frame();
  EXPECT_NE(widget("graph_node_parameters"), nullptr);
}

TEST_F(AnalysisGraphEditorTest, ParameterEditKeepsPannedCanvasAndSelectionDuringCpuPicking)
{
  AnalysisGraphState model(viewer());
  ASSERT_TRUE(model.view()); ASSERT_GT(model.view()->nodes.size(), 2u);
  AnalysisGraphCanvas expected;
  expected.set_view(model.view()); ASSERT_TRUE(expected.fit(1000, 640));
  wm::DrawContext draw; draw.rect = {0, 0, 1000, 700}; draw.ui_scale = 1;
  EditorContext ctx{f.shell->store(), area(), f.screen.ui(), &draw};
  auto event = [&](const wm::EventType type, const int x, const int y, const wm::MouseButton button) {
    wm::Event e; e.type = type; e.x = x; e.y = y; e.button = button;
    return area().editor().handle_gpu_event(e, ctx);
  };
  ASSERT_TRUE(event(wm::EventType::MouseDown, 500, 300, wm::MouseButton::Middle));
  ASSERT_TRUE(event(wm::EventType::MouseMove, 650, 220, wm::MouseButton::Middle));
  ASSERT_TRUE(event(wm::EventType::MouseUp, 650, 220, wm::MouseButton::Middle));
  ASSERT_TRUE(expected.pan(150, 80));
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  const auto &rect = model.view()->nodes[2].rect;
  const auto point = expected.to_screen({rect.x + rect.width / 2, rect.y + rect.height / 2});
  ASSERT_TRUE(event(wm::EventType::MouseDown, int(std::floor(point.x)), int(std::floor(699 - 60 - point.y)), wm::MouseButton::Left));
  f.drv->frame();
  ASSERT_NE(widget("graph_node_select"), nullptr);
  EXPECT_EQ(widget("graph_node_select")->index.value(), 2);
  // A reset-to-fit bug would hit elsewhere: the same node is displaced by 150 x 80 pixels.
}

TEST_F(AnalysisGraphEditorTest, OldBindingsAndQueuedNavigationDoNotSurviveClosingTheirEditor)
{
  ASSERT_NO_FATAL_FAILURE(select_node(2));
  const auto mode = widget("graph_mode")->index;
  const auto node = widget("graph_node_select")->index;
  const auto parameters = *widget("graph_node_parameters")->table;
  const auto retained_cell = parameters.cell(0, 0);
  const auto fit = widget("graph_fit")->on_click;
  const auto validate = widget("graph_validate")->on_click;
  const auto navigate = widget("graph_viewer")->on_click;
  ASSERT_TRUE(navigate); navigate();
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs));
  const auto layout = f.screen.to_json();
  mode.assign(1); node.assign(0); parameters.selected.assign(0);
  fit(); validate(); navigate(); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), layout);
  EXPECT_EQ(parameters.cell(0, 0), retained_cell); // Retained rows own their immutable model.
  EXPECT_EQ(area().editor().type().id, kEditorLogs);
}

TEST_F(AnalysisGraphEditorTest, NavigationPreservesTheGraphInstanceAndHonorsItsOriginScreen)
{
  Editor *graph = &area().editor();
  const auto navigate = widget("graph_viewer")->on_click;
  ASSERT_TRUE(navigate); navigate();
  EXPECT_EQ(&area().editor(), graph); // Structural changes are deferred.
  f.screen.run_deferred();
  ASSERT_NE(f.screen.maximized(), nullptr);
  EXPECT_EQ(dynamic_cast<EditorArea *>(f.screen.maximized())->editor().type().id, kEditorViewer);
  EXPECT_EQ(&area().tab(0), graph);
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAnalysisGraph, true).ok());
  EXPECT_EQ(&area().editor(), graph);
  f.drv->frame();
  const auto retained = widget("graph_viewer")->on_click;
  retained();
  f.shell->forget(f.screen);
  const auto before = f.screen.to_json();
  f.screen.run_deferred(); retained(); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
}

TEST_F(AnalysisGraphEditorTest, NavigationCallbackFromADestroyedScreenCannotTargetAnotherWindow)
{
  auto screen = std::make_unique<wm::Screen>();
  f.shell->install(*screen, nullptr); f.shell->build_default_layout(*screen);
  auto *other = dynamic_cast<EditorArea *>(screen->find_area("a2")); ASSERT_NE(other, nullptr);
  ASSERT_TRUE(other->set_tab_type(0, kEditorAnalysisGraph));
  screen->set_maximized(other);
  wmtest::ScreenDriver driver(*screen, 1280, 1000, 1); driver.frame();
  const auto *button = screen->ui()->find("graph_viewer"); ASSERT_NE(button, nullptr);
  const auto retained = button->on_click;
  retained();
  f.shell->forget(*screen); screen.reset();
  const auto layout = f.screen.to_json();
  retained(); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), layout);
}

TEST_F(AnalysisGraphEditorTest, ExistingLayoutVersionRoundTripsGraphModeTabsAndSplitGeometry)
{
  ASSERT_TRUE(area().editor().load_state({{"displayed", true}}));
  ASSERT_FALSE(area().editor().load_state({{"displayed", "yes"}}));
  ASSERT_TRUE(area().add_tab(kEditorLogs, false));
  area().set_weight(0.37f); f.area("a1").set_weight(0.26f);
  f.drv->frame();
  const auto saved = f.screen.to_json();
  const auto path = dir.path() / "graph-layout.json";
  ASSERT_TRUE(f.shell->save(f.screen, nullptr, path));
  wmtest::AppFixture reopened;
  ASSERT_TRUE(reopened.shell->restore(reopened.screen, path));
  reopened.drv->frame();
  EXPECT_EQ(reopened.screen.to_json(), saved);
  EXPECT_EQ(reopened.area("a2").tab(0).type().id, kEditorAnalysisGraph);
  EXPECT_EQ(reopened.area("a2").tab(0).save_state(), (nlohmann::json{{"displayed", true}}));
  EXPECT_EQ(reopened.screen.maximized(), &reopened.area("a2"));
  const auto document = io::read_json_file(path);
  EXPECT_EQ(document.at("format"), "stk.desktop.layout"); EXPECT_EQ(document.at("version"), 1);
}

class AnalysisGraphEditorPython : public AnalysisGraphEditorTest {
 protected:
  bridge::test::ManualLoop loop;
  std::unique_ptr<bridge::Client> client;

  void SetUp() override
  {
    ASSERT_NO_FATAL_FAILURE(AnalysisGraphEditorTest::SetUp());
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for graph editor integration"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)) << client->bridge_log().text();
    loop.run_ready(); f.shell->store().set_bridge(client.get());
    // AppShell installs the Python/UI integration independently of this editor. Wait for both
    // startup chains (script.open -> script.read and script.catalog -> ui.attach) before counting
    // graph requests or holding an individual validation callback in the main-loop queue.
    auto &scripts = f.shell->store().scripts();
    ASSERT_TRUE(loop.pump_until([&] {
      return scripts.ready() && scripts.desktop_ready() && scripts.status().contains("cursor");
    }, 30)) << scripts.error() << client->bridge_log().text();
    EXPECT_TRUE(scripts.status().at("run").is_null());
    f.drv->frame();
  }

  void TearDown() override
  {
    viewer().close(); f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready(); AnalysisGraphEditorTest::TearDown();
  }
};

TEST_F(AnalysisGraphEditorPython, RetainedValidateButtonRefusesChangedIntentUntilANewFrame)
{
  const auto *button = widget("graph_validate"); ASSERT_NE(button, nullptr); ASSERT_TRUE(button->enabled);
  const auto retained = button->on_click;
  const auto before = client->stats().calls_sent;
  viewer().set_parameter("min_magnitude", ui::FormValue::number(0.75));
  retained();
  EXPECT_EQ(client->stats().calls_sent, before);
  f.drv->frame();
  ASSERT_TRUE(widget("graph_validate")->enabled); widget("graph_validate")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame(); return has_text(std::string(f.shell->store().tr("analysis_graph.valid")));
  }, 30)) << client->bridge_log().text();
  EXPECT_EQ(client->stats().calls_sent, before + 1);
  EXPECT_EQ(viewer().evaluations_started(), 0);
}

TEST_F(AnalysisGraphEditorPython, ClosingTheEditorDropsAnAlreadyQueuedValidationResponse)
{
  const auto *button = widget("graph_validate"); ASSERT_NE(button, nullptr); ASSERT_TRUE(button->enabled);
  ASSERT_EQ(loop.queued(), 0u); button->on_click();
  ASSERT_TRUE(bridge::test::wait_until([&] { return loop.queued() > 0; }, 30));
  ASSERT_TRUE(area().set_tab_type(0, kEditorLogs));
  loop.run_ready();
  ASSERT_TRUE(area().set_tab_type(0, kEditorAnalysisGraph)); f.drv->frame();
  EXPECT_TRUE(has_text(std::string(f.shell->store().tr("analysis_graph.not_validated"))));
  EXPECT_FALSE(has_text(std::string(f.shell->store().tr("analysis_graph.valid"))));
  ASSERT_NE(widget("graph_validate"), nullptr); EXPECT_TRUE(widget("graph_validate")->enabled);
}

}  // namespace
}  // namespace stk::app
