/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;

Json graph_test_presets()
{
  return {{"presets", Json::array({io::read_json_file(fs::path(STK_REPO_ROOT) /
      "suan/graph/presets/muferro-domains.json")})}};
}
Json graph_test_catalog()
{
  return io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json");
}

TEST(AnalysisGraphState, ConstructionAndRepeatedInspectionHaveNoBridgeOrEvaluationSideEffects)
{
  bridge::test::TempDir dir{"graph-state-offline"};
  AppStore store;
  auto &viewer = store.viewer();
  AnalysisGraphState empty(viewer);
  EXPECT_FALSE(empty.configuration()); EXPECT_FALSE(empty.view());
  EXPECT_FALSE(empty.validation_available()); EXPECT_FALSE(empty.validate());
  viewer.set_metadata(graph_test_presets(), graph_test_catalog());
  fs::create_directories(dir.path() / "run");
  ASSERT_TRUE(viewer.open_path(core::path_to_utf8(dir.path() / "run"), "muferro-domains"));
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.configuration()); ASSERT_TRUE(state.view());
  const auto view = state.view();
  const auto inspection = state.inspection();
  const auto generation = state.generation();
  for (int i = 0; i < 5; ++i) { state.sync(); EXPECT_FALSE(state.validate()); }
  EXPECT_EQ(state.view(), view); EXPECT_EQ(state.inspection(), inspection);
  EXPECT_EQ(state.generation(), generation);
  EXPECT_EQ(viewer.evaluations_started(), 0); EXPECT_FALSE(viewer.evaluating());
  EXPECT_TRUE(state.validation().is_null());
}

class AnalysisGraphPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"analysis-graph-state"};
  AppStore store;
  ViewerState &viewer = store.viewer();
  Json presets = graph_test_presets(), catalog = graph_test_catalog();
  std::unique_ptr<bridge::Client> client, replacement;

  void start_client(std::unique_ptr<bridge::Client> &target, const std::string &name,
                    const bool reject_catalog = false)
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for graph validation integration"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/" + name;
    options.cache_dir = dir.str() + "/cache-" + name;
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    if (reject_catalog) {
      const auto script = dir.path() / "catalog-error.py";
      std::ofstream stream(script);
      stream << "from suan.desktop_bridge.graphs import GraphService\n"
                "from suan.desktop_bridge.protocol import BridgeError\n"
                "from suan.desktop_bridge.__main__ import main\n"
                "def unavailable(self):\n"
                "    raise BridgeError('unavailable', 'fixture catalog unavailable')\n"
                "GraphService.catalog = unavailable\n"
                "main()\n";
      stream.close(); ASSERT_TRUE(stream.good());
      options.command = {python, "-u", core::path_to_utf8(script), "--stdio", "--state-dir",
          options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    }
    target = bridge::Client::create(options);
    ASSERT_TRUE(target->start());
    ASSERT_TRUE(target->wait_ready(60)) << target->bridge_log().text();
  }

  void SetUp() override
  {
    viewer.prefetch_neighbours = false;
    viewer.set_auto_evaluate(false);
    viewer.set_metadata(presets, catalog);
    fs::create_directories(dir.path() / "run");
    // Opening before attaching a bridge records intent, but cannot evaluate the empty run.
    ASSERT_TRUE(viewer.open_path(core::path_to_utf8(dir.path() / "run"), "muferro-domains"));
    ASSERT_EQ(viewer.evaluations_started(), 0);
    ASSERT_NO_FATAL_FAILURE(start_client(client, "bridge"));
    if (!client) { return; }
    loop.run_ready();
    store.set_bridge(client.get());
    // Deliberately never call ViewerState::pump: only graph.validate is under test.
  }

  void TearDown() override
  {
    EXPECT_EQ(viewer.evaluations_started(), 0);
    EXPECT_FALSE(viewer.evaluating());
    viewer.close(); store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    if (replacement) { replacement->close(); EXPECT_EQ(replacement->stats().schema_violations, 0u); }
    loop.run_ready();
  }

  void queued_response(AnalysisGraphState &state)
  {
    ASSERT_EQ(loop.queued(), 0u);
    ASSERT_TRUE(state.validate());
    ASSERT_TRUE(bridge::test::wait_until([&] { return loop.queued() > 0; }, 30)) << client->bridge_log().text();
    ASSERT_TRUE(state.validating());
    ASSERT_TRUE(state.validation().is_null());
  }

  void settled(AnalysisGraphState &state)
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30)) << client->bridge_log().text();
  }
};

TEST_F(AnalysisGraphPython, OnlyExplicitValidationCallsTheBridgeAndNeverEvaluates)
{
  const auto before = client->stats().calls_sent;
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.validation_available());
  for (int i = 0; i < 5; ++i) { state.sync(); }
  EXPECT_EQ(client->stats().calls_sent, before);
  ASSERT_TRUE(state.validate()); EXPECT_FALSE(state.validate());
  ASSERT_NO_FATAL_FAILURE(settled(state));
  ASSERT_TRUE(state.validation().is_object()) << state.validation_error();
  EXPECT_EQ(state.validation().at("ok"), true);
  EXPECT_TRUE(state.validation().at("issues").empty());
  EXPECT_EQ(client->stats().calls_sent, before + 1);
  const auto accepted = state.validation();
  state.sync(); EXPECT_EQ(state.validation(), accepted);
}

TEST_F(AnalysisGraphPython, InvalidGraphReportsRealValidationIssuesWithoutEvaluating)
{
  presets["presets"][0]["graph"]["nodes"][0]["type"] = "fixture.unknown@1";
  viewer.set_metadata(presets, catalog);
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.view());
  ASSERT_TRUE(state.validate());
  ASSERT_NO_FATAL_FAILURE(settled(state));
  ASSERT_TRUE(state.validation().is_object()) << state.validation_error();
  EXPECT_EQ(state.validation().at("ok"), false);
  EXPECT_FALSE(state.validation().at("issues").empty());
  EXPECT_TRUE(state.validation_error().empty());
}

TEST_F(AnalysisGraphPython, ParameterOnlyChangesKeepTopologyAndCanvasPanButDiscardValidation)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.validate()); ASSERT_NO_FATAL_FAILURE(settled(state));
  ASSERT_EQ(state.validation().at("ok"), true);
  const auto view = state.view();
  AnalysisGraphCanvas canvas;
  canvas.set_view(view); ASSERT_TRUE(canvas.fit(900, 600));
  ASSERT_TRUE(canvas.pan(73, -51)); ASSERT_TRUE(canvas.zoom_at(1.4, 300, 200));
  const auto x = canvas.pan_x(), y = canvas.pan_y(), zoom = canvas.zoom();
  const auto generation = state.generation();
  viewer.set_parameter("min_magnitude", ui::FormValue::number(0.75));
  state.sync(); canvas.set_view(state.view());
  EXPECT_EQ(state.view(), view); EXPECT_GT(state.generation(), generation);
  EXPECT_EQ(state.configuration()->parameters.at("min_magnitude"), 0.75);
  EXPECT_TRUE(state.validation().is_null());
  EXPECT_DOUBLE_EQ(canvas.pan_x(), x); EXPECT_DOUBLE_EQ(canvas.pan_y(), y); EXPECT_DOUBLE_EQ(canvas.zoom(), zoom);
}

enum class GraphChange { Parameters, Source, Catalog, Mode, Bridge, NumericType };
class AnalysisGraphStale : public AnalysisGraphPython, public ::testing::WithParamInterface<GraphChange> {};

TEST_P(AnalysisGraphStale, QueuedResponseCannotValidateAChangedConfigurationOrSession)
{
  AnalysisGraphState state(viewer);
  ASSERT_NO_FATAL_FAILURE(queued_response(state));
  const auto generation = state.generation();
  const auto view = state.view();
  switch (GetParam()) {
    case GraphChange::Parameters:
      viewer.set_parameter("min_magnitude", ui::FormValue::number(0.75));
      break;
    case GraphChange::Source:
      store.set_bridge(nullptr);
      fs::create_directories(dir.path() / "other-run");
      ASSERT_TRUE(viewer.open_path(core::path_to_utf8(dir.path() / "other-run"), "muferro-domains"));
      store.set_bridge(client.get());
      break;
    case GraphChange::Catalog:
      catalog["generated_by"] = "updated-catalog-fixture";
      viewer.set_metadata(presets, catalog);
      break;
    case GraphChange::Mode:
      state.show_displayed(true);
      break;
    case GraphChange::Bridge:
      ASSERT_NO_FATAL_FAILURE(start_client(replacement, "replacement"));
      store.set_bridge(replacement.get());
      break;
    case GraphChange::NumericType:
      // nlohmann equality considers these equal; the submitted graph contract does not.
      ASSERT_TRUE(presets["presets"][0]["graph"]["nodes"][10]["params"]["width"].is_number_integer());
      presets["presets"][0]["graph"]["nodes"][10]["params"]["width"] = 1600.0;
      viewer.set_metadata(presets, catalog);
      break;
  }
  // No intervening state.sync/frame: the old callback must notice the change itself.
  loop.run_ready();
  EXPECT_GT(state.generation(), generation);
  EXPECT_FALSE(state.validating()); EXPECT_TRUE(state.validation().is_null());
  EXPECT_TRUE(state.validation_error().empty());
  if (GetParam() == GraphChange::Parameters || GetParam() == GraphChange::Source || GetParam() == GraphChange::Bridge) {
    EXPECT_EQ(state.view(), view);
  }
  if (GetParam() == GraphChange::Mode) { EXPECT_FALSE(state.configuration()); state.show_displayed(false); }
  ASSERT_TRUE(state.validate()); ASSERT_NO_FATAL_FAILURE(settled(state));
  EXPECT_TRUE(state.validation().is_object()) << state.validation_error();
}

INSTANTIATE_TEST_SUITE_P(Configuration, AnalysisGraphStale,
    ::testing::Values(GraphChange::Parameters, GraphChange::Source, GraphChange::Catalog,
                      GraphChange::Mode, GraphChange::Bridge, GraphChange::NumericType),
    [](const ::testing::TestParamInfo<GraphChange> &info) {
      switch (info.param) {
        case GraphChange::Parameters: return "Parameters";
        case GraphChange::Source: return "Source";
        case GraphChange::Catalog: return "Catalog";
        case GraphChange::Mode: return "Mode";
        case GraphChange::Bridge: return "Bridge";
        case GraphChange::NumericType: return "NumericType";
      }
      return "Unknown";
    });

TEST_F(AnalysisGraphPython, DestroyedControllerAndClosedBridgeCannotAcceptAnOldReply)
{
  auto state = std::make_unique<AnalysisGraphState>(viewer);
  ASSERT_NO_FATAL_FAILURE(queued_response(*state));
  state.reset();
  loop.run_ready(); // The continuation retains only a weak lifetime guard.
  AnalysisGraphState next(viewer);
  ASSERT_TRUE(next.validate()); ASSERT_NO_FATAL_FAILURE(settled(next));
  ASSERT_EQ(next.validation().at("ok"), true);
  client->close(); next.sync(); loop.run_ready();
  EXPECT_FALSE(next.validation_available()); EXPECT_FALSE(next.validate());
  EXPECT_TRUE(next.validation().is_null()); EXPECT_FALSE(next.validating());
}

class AnalysisGraphCatalogPython : public AnalysisGraphPython {
 protected:
  void SetUp() override
  {
    viewer.prefetch_neighbours = false;
    viewer.set_auto_evaluate(false);
    ASSERT_NO_FATAL_FAILURE(start_client(client, "catalog-bridge"));
    if (!client) { return; }
    loop.run_ready(); store.set_bridge(client.get());
    ASSERT_TRUE(viewer.catalog().is_null());
  }

  void catalog_settled(AnalysisGraphState &state)
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state.catalog_loading(); }, 30)) << client->bridge_log().text();
  }

  void catalog_queued(AnalysisGraphState &state)
  {
    ASSERT_TRUE(state.ensure_catalog());
    ASSERT_TRUE(bridge::test::wait_until([&] { return loop.queued() > 0; }, 30));
    ASSERT_TRUE(state.catalog_loading());
  }
};

TEST_F(AnalysisGraphCatalogPython, SavedFirstOpenReadsKnownNodeMetadataWithoutTouchingViewer)
{
  auto &project = store.project(); project.sync();
  ASSERT_TRUE(project.create(dir.str() + "/project", "Analysis only"));
  ASSERT_TRUE(loop.pump_until([&] { return project.loaded() && !project.busy() && !project.recent_loading(); }, 30));
  const auto inspection = viewer.graph_inspection();
  const auto version = viewer.version();
  const auto calls = client->stats().calls_sent;
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_document(project.project()->handle, "087f9bca-672d-4b19-9293-302224afca5a", 0,
      {{"format", "stk.analysis-document/1"}, {"graph", presets.at("presets")[0].at("graph")},
       {"parameters", Json::object()}, {"outputs", Json::array()}}));
  ASSERT_TRUE(state.view());
  EXPECT_FALSE(state.view()->nodes.front().known_type);
  EXPECT_EQ(client->stats().calls_sent, calls); // Construction, open and sync remain request-free.
  ASSERT_TRUE(state.ensure_catalog()); EXPECT_FALSE(state.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(catalog_settled(state));
  EXPECT_TRUE(state.catalog_error().empty()) << state.catalog_error();
  ASSERT_TRUE(state.view());
  for (const auto &node : state.view()->nodes) { EXPECT_TRUE(node.known_type) << node.type; }
  for (int i = 0; i < 5; ++i) { state.sync(); EXPECT_FALSE(state.ensure_catalog()); }
  EXPECT_EQ(client->stats().calls_sent, calls + 1);
  EXPECT_TRUE(viewer.catalog().is_null());
  EXPECT_EQ(viewer.version(), version); EXPECT_EQ(viewer.graph_inspection(), inspection);
  EXPECT_FALSE(state.inspection()); EXPECT_FALSE(state.configuration());
}

TEST_F(AnalysisGraphCatalogPython, PendingViewerWaitingForMetadataIsNeverStartedByAnalysisMetadata)
{
  store.set_bridge(nullptr);
  fs::create_directories(dir.path() / "pending");
  ASSERT_TRUE(viewer.open_path(core::path_to_utf8(dir.path() / "pending"), "muferro-domains"));
  store.set_bridge(client.get());
  const auto inspection = viewer.graph_inspection();
  const auto version = viewer.version();
  const auto calls = client->stats().calls_sent;
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(catalog_settled(state));
  EXPECT_TRUE(state.catalog_error().empty());
  EXPECT_EQ(client->stats().calls_sent, calls + 1);
  EXPECT_EQ(viewer.version(), version); EXPECT_EQ(viewer.graph_inspection(), inspection);
  EXPECT_TRUE(viewer.catalog().is_null()); EXPECT_FALSE(viewer.presets_loaded());
  EXPECT_EQ(viewer.evaluations_started(), 0); EXPECT_FALSE(viewer.evaluating());
}

TEST_F(AnalysisGraphPython, ExistingViewerCatalogIsReusedWithoutAnotherRequest)
{
  const auto calls = client->stats().calls_sent;
  AnalysisGraphState state(viewer);
  EXPECT_FALSE(state.ensure_catalog()); EXPECT_FALSE(state.catalog_loading());
  EXPECT_TRUE(state.catalog_error().empty()); EXPECT_EQ(client->stats().calls_sent, calls);
  ASSERT_TRUE(state.view());
  for (const auto &node : state.view()->nodes) { EXPECT_TRUE(node.known_type) << node.type; }
}

TEST_F(AnalysisGraphCatalogPython, QueuedCatalogFromDetachedSessionCannotBecomeTheNewCache)
{
  AnalysisGraphState state(viewer);
  ASSERT_NO_FATAL_FAILURE(catalog_queued(state));
  store.set_bridge(nullptr); // No intervening sync: the callback itself must detect detachment.
  loop.run_ready(); state.sync();
  EXPECT_FALSE(state.catalog_loading()); EXPECT_TRUE(state.catalog_error().empty());
  EXPECT_FALSE(state.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(start_client(replacement, "new-catalog-bridge"));
  loop.run_ready(); store.set_bridge(replacement.get());
  const auto calls = replacement->stats().calls_sent;
  ASSERT_TRUE(state.ensure_catalog()); // Old response did not populate an unscoped cache.
  ASSERT_NO_FATAL_FAILURE(catalog_settled(state));
  EXPECT_TRUE(state.catalog_error().empty()); EXPECT_EQ(replacement->stats().calls_sent, calls + 1);
}

TEST_F(AnalysisGraphCatalogPython, DestroyedControllerRejectsQueuedCatalogAndNewControllerReadsIndependently)
{
  auto state = std::make_unique<AnalysisGraphState>(viewer);
  ASSERT_NO_FATAL_FAILURE(catalog_queued(*state));
  state.reset(); loop.run_ready();
  EXPECT_TRUE(viewer.catalog().is_null());
  AnalysisGraphState next(viewer);
  ASSERT_TRUE(next.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(catalog_settled(next));
  EXPECT_TRUE(next.catalog_error().empty());
}

TEST_F(AnalysisGraphCatalogPython, CatalogFailureIsVisibleAndRepeatedFramesDoNotRetry)
{
  ASSERT_NO_FATAL_FAILURE(start_client(replacement, "unavailable-catalog-bridge", true));
  loop.run_ready(); store.set_bridge(replacement.get());
  AnalysisGraphState state(viewer);
  const auto calls = replacement->stats().calls_sent;
  ASSERT_TRUE(state.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(catalog_settled(state));
  EXPECT_NE(state.catalog_error().find("fixture catalog unavailable"), std::string::npos);
  for (int i = 0; i < 5; ++i) { state.sync(); EXPECT_FALSE(state.ensure_catalog()); }
  EXPECT_EQ(replacement->stats().calls_sent, calls + 1);
  EXPECT_TRUE(viewer.catalog().is_null());
  store.set_bridge(client.get()); state.sync();
  EXPECT_TRUE(state.catalog_error().empty());
  ASSERT_TRUE(state.ensure_catalog());
  ASSERT_NO_FATAL_FAILURE(catalog_settled(state));
  EXPECT_TRUE(state.catalog_error().empty());
}

}  // namespace
}  // namespace stk::app
