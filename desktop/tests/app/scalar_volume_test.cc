/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_graph_state.hh"
#include "stk/app/project_analyses.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "scalar_volume_support.hh"

#include <algorithm>
#include <cstdlib>
#include <limits>

namespace stk::app {
namespace {
using io::Json;

class ScalarVolumePython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"scalar-volume"};
  bridge::test::ManualLoop loop;
  AppStore store;
  std::unique_ptr<bridge::Client> client;
  ViewerState &viewer() { return store.viewer(); }
  ProjectState &project() { return store.project(); }

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for scalar volume integration"; }
    ASSERT_TRUE(apptest::write_signed_field(dir.path() / "signed.dat"));
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store.set_bridge(client.get());
    viewer().prefetch_neighbours = false;
    viewer().set_auto_evaluate(false);
    ASSERT_TRUE(loop.pump_until([&] {
      viewer().pump(); return viewer().presets_loaded() && !viewer().catalog().is_null();
    }, 60)) << client->bridge_log().text();
  }

  void TearDown() override
  {
    viewer().close(); project().attach(nullptr); store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }

  void open(const int component = 0, const Json &extra = Json::object())
  {
    Json parameters = {{"field", "signed"}, {"component", component}};
    for (auto it = extra.begin(); it != extra.end(); ++it) { parameters[it.key()] = it.value(); }
    ASSERT_TRUE(viewer().open_path(core::path_to_utf8(dir.path() / "signed.dat"), "scalar-volume", parameters));
    ASSERT_TRUE(loop.pump_until([&] {
      viewer().pump(); return !viewer().evaluating() && (viewer().payload() || !viewer().eval_error().empty());
    }, 60)) << client->bridge_log().text();
    ASSERT_NE(viewer().payload(), nullptr) << viewer().eval_error();
    ASSERT_TRUE(viewer().eval_error().empty()) << viewer().eval_error();
  }

  void evaluate(const bool success = true)
  {
    const auto serial = viewer().payload_serial();
    viewer().evaluate_now();
    ASSERT_TRUE(loop.pump_until([&] {
      viewer().pump(); return !viewer().evaluating() &&
          (viewer().payload_serial() != serial || !viewer().eval_error().empty());
    }, 60)) << viewer().eval_error() << client->bridge_log().text();
    EXPECT_EQ(viewer().eval_error().empty(), success) << viewer().eval_error();
  }

  void exact_values(const int component)
  {
    const auto payload = viewer().payload(); ASSERT_NE(payload, nullptr);
    const auto *layer = payload->layer("volume"); ASSERT_NE(layer, nullptr);
    EXPECT_EQ(layer->at("grid").at("dimensions"), Json::array({3, 4, 5}));
    const auto samples = payload->view<float>(layer->at("data").get<std::string>());
    ASSERT_EQ(samples.size(), 60u);
    double low = std::numeric_limits<double>::infinity(), high = -low;
    for (int z = 0; z < 5; ++z) {
      for (int y = 0; y < 4; ++y) {
        for (int x = 0; x < 3; ++x) {
          const double expected = apptest::signed_component(x, y, z, component);
          EXPECT_EQ(samples[size_t((z * 4 + y) * 3 + x)], expected);
          low = std::min(low, expected); high = std::max(high, expected);
        }
      }
    }
    EXPECT_LT(low, 0);
    EXPECT_EQ(layer->at("value_range"), Json::array({low, high}));
    EXPECT_EQ(layer->at("transfer_function").at("range"), Json::array({low, high}));
    const auto *bar = payload->layer("bar"); ASSERT_NE(bar, nullptr);
    EXPECT_EQ(bar->at("range"), Json::array({low, high}));
    const auto inspection = viewer().graph_inspection();
    EXPECT_EQ(inspection->shown_graph_verified, true);
    EXPECT_EQ(inspection->shown_matches_desired, true);
    ASSERT_TRUE(inspection->shown_configuration);
    EXPECT_EQ(inspection->shown_configuration->parameters.at("component"), component);
  }
};

TEST_F(ScalarVolumePython, ExplicitComponentsPreserveSignedCoordinatesAndIndependentRanges)
{
  ASSERT_NO_FATAL_FAILURE(open());
  ASSERT_NO_FATAL_FAILURE(exact_values(0));
  const auto original = viewer().payload();
  const int calls = viewer().evaluations_started();
  viewer().set_parameter("component", ui::FormValue::number(1));
  EXPECT_EQ(viewer().evaluations_started(), calls);
  EXPECT_EQ(viewer().payload(), original);
  EXPECT_EQ(viewer().graph_inspection()->shown_matches_desired, false);
  ASSERT_NO_FATAL_FAILURE(evaluate());
  ASSERT_NO_FATAL_FAILURE(exact_values(1));
  viewer().set_parameter("component", ui::FormValue::number(2));
  ASSERT_NO_FATAL_FAILURE(evaluate());
  ASSERT_NO_FATAL_FAILURE(exact_values(2));
}

TEST_F(ScalarVolumePython, UnitDefaultClearAndExplicitRelabelKeepTheSameNumbers)
{
  ASSERT_NO_FATAL_FAILURE(open());
  EXPECT_EQ(viewer().form().get("unit").kind, ui::FormValue::Kind::Null);
  EXPECT_FALSE(viewer().parameters().contains("unit"));
  const auto *initial = viewer().payload()->layer("volume"); ASSERT_NE(initial, nullptr);
  EXPECT_EQ(initial->at("unit"), "unspecified");
  viewer().set_parameter("unit", ui::FormValue::string("K"));
  ASSERT_NO_FATAL_FAILURE(evaluate());
  ASSERT_NO_FATAL_FAILURE(exact_values(0));
  EXPECT_EQ(viewer().payload()->layer("volume")->at("unit"), "K");
  EXPECT_EQ(viewer().payload()->layer("bar")->at("unit"), "K");
  EXPECT_NE(io::get_string(*viewer().payload()->layer("bar"), "title").find("[K]"), std::string::npos);
  viewer().set_parameter("unit", ui::FormValue());
  ASSERT_NO_FATAL_FAILURE(evaluate());
  ASSERT_NO_FATAL_FAILURE(exact_values(0));
  EXPECT_FALSE(viewer().parameters().contains("unit"));
  EXPECT_EQ(viewer().payload()->layer("volume")->at("unit"), "unspecified");
}

TEST_F(ScalarVolumePython, InvalidFieldOrComponentKeepsTheOldResultExplicitlyStale)
{
  ASSERT_NO_FATAL_FAILURE(open(1));
  const auto valid = viewer().payload();
  viewer().set_parameter("field", ui::FormValue::string("missing"));
  ASSERT_NO_FATAL_FAILURE(evaluate(false));
  EXPECT_EQ(viewer().payload(), valid);
  EXPECT_EQ(viewer().graph_inspection()->shown_matches_desired, false);
  viewer().set_parameter("field", ui::FormValue::string("signed"));
  viewer().set_parameter("component", ui::FormValue::number(3));
  ASSERT_NO_FATAL_FAILURE(evaluate(false));
  EXPECT_EQ(viewer().payload(), valid);
  EXPECT_EQ(viewer().graph_inspection()->shown_configuration->parameters.at("component"), 1);
  viewer().set_parameter("component", ui::FormValue::number(0));
  ASSERT_NO_FATAL_FAILURE(evaluate());
  ASSERT_NO_FATAL_FAILURE(exact_values(0));
}

TEST_F(ScalarVolumePython, SavedAndReopenedDefinitionRetainsFieldComponentAndUnitWithoutEvaluating)
{
  ASSERT_NO_FATAL_FAILURE(open(2, {{"unit", "K"}}));
  project().sync(); ASSERT_TRUE(project().create(dir.str() + "/project", "Signed scalar"));
  ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
  ProjectAnalyses analyses(store);
  const auto capture = viewer().graph_inspection(); ASSERT_TRUE(capture->desired);
  const auto &config = *capture->desired;
  const Json document = {{"format", "stk.analysis-document/1"}, {"graph", config.graph},
      {"parameters", config.parameters}, {"outputs", config.requested_outputs}};
  const int evaluations = viewer().evaluations_started();
  ASSERT_TRUE(analyses.save_new("Signed component 2", document));
  ASSERT_TRUE(loop.pump_until([&] { return !analyses.busy() && !project().busy(); }, 30));
  ASSERT_TRUE(analyses.error().empty()) << analyses.error();
  const auto id = analyses.selected().at("id").get<std::string>();
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && !project().project(); }, 30));
  analyses.sync();
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
  analyses.sync(); EXPECT_TRUE(analyses.selected().is_null());
  ASSERT_TRUE(analyses.load(id));
  ASSERT_TRUE(loop.pump_until([&] { return !analyses.busy() && !project().busy(); }, 30));
  ASSERT_TRUE(analyses.error().empty()) << analyses.error();
  const auto &read = analyses.selected().at("document");
  EXPECT_EQ(io::python_json_dumps(read, true, true), io::python_json_dumps(document, true, true));
  EXPECT_EQ(read.at("parameters").at("field"), "signed");
  EXPECT_EQ(read.at("parameters").at("component"), 2);
  EXPECT_EQ(read.at("parameters").at("unit"), "K");
  AnalysisGraphState graph(viewer());
  ASSERT_TRUE(graph.open_document(analyses.handle(), id, analyses.selected_revision(), read));
  EXPECT_TRUE(graph.saved()); EXPECT_FALSE(graph.inspection());
  EXPECT_EQ(viewer().graph_inspection(), capture);
  EXPECT_EQ(viewer().evaluations_started(), evaluations);
}

TEST_F(ScalarVolumePython, FiniteValuesOutsideTheDisplayEncodingFailWithoutPublishingAPayload)
{
  ASSERT_TRUE(apptest::write_signed_field(dir.path() / "huge.dat", 3, 4, 5, 1e40));
  ASSERT_TRUE(viewer().open_path(core::path_to_utf8(dir.path() / "huge.dat"), "scalar-volume",
      {{"field", "huge"}, {"component", 1}}));
  ASSERT_TRUE(loop.pump_until([&] { viewer().pump(); return !viewer().evaluating() && !viewer().eval_error().empty(); }, 60));
  EXPECT_FALSE(viewer().payload());
  EXPECT_FALSE(viewer().graph_inspection()->shown_configuration);
  EXPECT_NE(viewer().eval_error().find("float32"), std::string::npos) << viewer().eval_error();
}

}  // namespace
}  // namespace stk::app
