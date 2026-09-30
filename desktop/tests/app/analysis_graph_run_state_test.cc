/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/analysis_document.hh"
#include "stk/app/analysis_graph_state.hh"
#include "stk/app/analysis_parameter_draft.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
using Source = AnalysisGraphState::Source;
using Reply = bridge::Result<Json>;
namespace fs = std::filesystem;
constexpr const char *analysis_id = "6835d6d2-e148-4416-99e5-9d4dc85f4f12";
constexpr const char *run_id = "ad5dfb3f-94a1-4cd2-a1e7-c731c84c2b42";
constexpr const char *other_run_id = "3a6bd004-f773-4cbd-8e45-c86070dbb281";

Json small_document()
{
  return {{"format", "stk.analysis-document/1"}, {"graph", {{"schema", "stk.graph/1"},
      {"nodes", Json::array({{{"id", "source"}, {"type", "fixture.source.scalar@1"}}})},
      {"outputs", {{"value", "source.value"}}}}}, {"parameters", Json::object()},
      {"outputs", Json::array({"value"})}};
}
std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }

TEST(AnalysisDocumentBounds, SharedGuardKeepsDocumentDepthRelativeToItsOwnRoot)
{
  auto document = small_document();
  Json value = 0;
  for (int i = 0; i < 62; ++i) { value = Json::array({std::move(value)}); }
  document["parameters"]["nested"] = std::move(value);
  EXPECT_NO_THROW(check_analysis_document_bounds(document));
  Json wrapper = {{"document", document}};
  EXPECT_THROW(check_analysis_json_bounds(wrapper), std::invalid_argument);
  EXPECT_NO_THROW(check_analysis_document_bounds(wrapper.at("document")));
  document["parameters"]["nested"] = Json::array({std::move(document["parameters"]["nested"])});
  EXPECT_THROW(check_analysis_document_bounds(document), std::invalid_argument);
}

TEST(AnalysisDocumentBounds, ExtractedGuardRejectsMalformedOrUnboundedDataBeforeCopy)
{
  auto document = small_document();
  document["parameters"]["value"] = std::numeric_limits<double>::infinity();
  EXPECT_THROW(check_analysis_document_bounds(document), std::invalid_argument);
  document["parameters"]["value"] = std::string(AnalysisDocumentLimits::max_parameters_bytes, 'a');
  EXPECT_THROW(check_analysis_document_bounds(document), std::invalid_argument);
  document["parameters"].clear(); document["outputs"] = Json::array({"value", "value"});
  EXPECT_THROW(check_analysis_document_bounds(document), std::invalid_argument);
  Json deep = 0;
  for (int i = 0; i < 10000; ++i) { deep = Json::array({std::move(deep)}); }
  EXPECT_THROW(check_analysis_json_bounds(deep), std::invalid_argument);
}

class AnalysisGraphRunState : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"analysis-graph-run-state"};
  AppStore store;
  ViewerState &viewer = store.viewer();
  ProjectState &project = store.project();
  std::unique_ptr<bridge::Client> client;
  Json document, run, requested_bindings;
  std::string snapshot_id;
  int64_t revision = -1;

  std::string handle() const { return project.project()->handle; }
  void call(const std::string &method, Json params, Json &out)
  {
    auto result = std::make_shared<std::optional<Reply>>();
    auto future = client->call(method, std::move(params));
    future.then([result](auto value) { *result = std::move(value); });
    const bool finished = loop.pump_until([&] { return result->has_value(); }, 30);
    if (!finished) { future.cancel(); }
    ASSERT_TRUE(finished) << client->bridge_log().text();
    ASSERT_TRUE(result->value().ok()) << result->value().error().describe();
    out = result->value().value();
  }
  void settled_project()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project.busy() && !project.recent_loading(); }, 30))
        << project.error() << client->bridge_log().text();
  }
  void prepare(const char *identity, Json &result)
  {
    Json reply;
    ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.prepare", {{"handle", handle()},
        {"run_id", identity}, {"analysis_id", analysis_id}, {"expected_revision", revision},
        {"snapshot_id", snapshot_id}, {"bindings", requested_bindings}}, reply));
    result = reply.at("run");
  }
  void queued_validation(AnalysisGraphState &state)
  {
    loop.run_ready();
    ASSERT_TRUE(state.validate());
    ASSERT_TRUE(bridge::test::wait_until([&] { return loop.queued() > 0; }, 30));
    ASSERT_TRUE(state.validating()); ASSERT_TRUE(state.validation().is_null());
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for frozen run inspection"; }
    viewer.set_auto_evaluate(false); viewer.prefetch_neighbours = false;
    const auto preset = io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json");
    viewer.set_metadata({{"presets", Json::array({preset})}},
        io::read_json_file(fs::path(STK_REPO_ROOT) / "docs/specs/catalog/stk-catalog-m1.json"));
    bridge::ClientOptions options;
    options.python.configured = python; options.state_dir = directory.str() + "/bridge";
    options.cache_dir = directory.str() + "/cache"; options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime"; options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)) << client->bridge_log().text();
    loop.run_ready(); store.set_bridge(client.get()); project.sync();
    ASSERT_TRUE(project.create(directory.str() + "/project", "Frozen graph inspection"));
    ASSERT_NO_FATAL_FAILURE(settled_project()); ASSERT_TRUE(project.loaded());
    std::ofstream file(directory.path() / "input.dat", std::ios::binary);
    file << "Snapshot input bytes; inspection must not parse or evaluate this file.\n";
    file.close(); ASSERT_TRUE(file.good());
    Json indexed, snapshot, saved;
    ASSERT_NO_FATAL_FAILURE(call("project.files.index", {{"handle", handle()}, {"expected_revision", 0},
        {"paths", Json::array({core::path_to_utf8(directory.path() / "input.dat")})}}, indexed));
    const auto record_id = indexed.at("record_ids")[0];
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()},
        {"expected_revision", indexed.at("revision")}, {"record_ids", Json::array({record_id})}}, snapshot));
    snapshot_id = snapshot.at("snapshot").at("id").get<std::string>();
    document = {{"format", "stk.analysis-document/1"}, {"graph", preset.at("graph")},
        {"parameters", {{"path", "input.dat"}, {"field", "input"}, {"component", 1}, {"unit", nullptr}}},
        {"outputs", Json::array({"view"})}};
    requested_bindings = {{"data", {{"input.dat", record_id}}}};
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", analysis_id},
        {"name", "Signed scalar α"}, {"document", document}, {"expected_revision", snapshot.at("revision")}}, saved));
    revision = saved.at("revision").get<int64_t>(); project.refresh();
    ASSERT_NO_FATAL_FAILURE(settled_project());
    ASSERT_NO_FATAL_FAILURE(prepare(run_id, run));
    ASSERT_EQ(run.at("status"), "prepared");
    loop.run_ready();
  }
  void TearDown() override
  {
    EXPECT_EQ(viewer.evaluations_started(), 0); EXPECT_FALSE(viewer.evaluating());
    viewer.close(); project.attach(nullptr); store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(AnalysisGraphRunState, PreparedRunInspectionCopiesOnlyFrozenDefinitionAndProvenanceWithoutIo)
{
  AnalysisGraphState state(viewer);
  const auto calls = client->stats().calls_sent, viewer_version = viewer.version();
  const auto viewer_inspection = viewer.graph_inspection();
  const auto source = run;
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  ASSERT_EQ(state.source(), Source::Run); ASSERT_TRUE(state.view()); ASSERT_TRUE(state.definition());
  ASSERT_NE(state.frozen_run(), nullptr);
  EXPECT_FALSE(state.inspection()); EXPECT_FALSE(state.configuration()); EXPECT_FALSE(state.saved());
  EXPECT_EQ(state.frozen_run()->id, run_id); EXPECT_EQ(state.frozen_run()->analysis_id, analysis_id);
  EXPECT_EQ(state.frozen_run()->project_id, project.project()->id);
  EXPECT_EQ(state.frozen_run()->analysis_name, "Signed scalar α");
  EXPECT_EQ(state.frozen_run()->source_revision, revision);
  EXPECT_EQ(state.frozen_run()->snapshot_id, snapshot_id);
  EXPECT_EQ(state.frozen_run()->plan_sha256, source.at("plan_sha256").get<std::string>());
  EXPECT_EQ(state.frozen_run()->snapshot_sha256, source.at("snapshot_sha256").get<std::string>());
  EXPECT_EQ(state.frozen_run()->created_at, source.at("created_at").get<std::string>());
  EXPECT_EQ(state.frozen_run()->bindings, source.at("bindings"));
  EXPECT_EQ(exact(state.definition()->parameters), exact(document.at("parameters")));
  EXPECT_EQ(exact(state.definition()->graph), exact(document.at("graph")));
  EXPECT_EQ(state.definition()->requested_outputs, (std::vector<std::string>{"view"}));
  run["document"]["parameters"]["component"] = 999;
  run["bindings"]["data"]["input.dat"]["size"] = 0;
  run["analysis_name"] = "Mutable caller"; run["status"] = "running";
  for (int i = 0; i < 5; ++i) { state.sync(); }
  EXPECT_EQ(state.definition()->parameters.at("component"), 1);
  EXPECT_EQ(state.frozen_run()->bindings, source.at("bindings"));
  EXPECT_EQ(state.frozen_run()->analysis_name, "Signed scalar α");
  EXPECT_EQ(client->stats().calls_sent, calls); EXPECT_EQ(viewer.version(), viewer_version);
  EXPECT_EQ(viewer.graph_inspection(), viewer_inspection); EXPECT_EQ(project.project()->revision, revision);
}

TEST_F(AnalysisGraphRunState, ProjectAdvanceAndDefinitionDeletionNeverRebaseHistoricalRun)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  const auto generation = state.generation();
  const auto view = state.view();
  Json changed = document, updated;
  changed["parameters"]["component"] = 0;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Changed definition"}, {"document", changed}, {"expected_revision", revision}}, updated));
  project.refresh(); ASSERT_NO_FATAL_FAILURE(settled_project()); state.sync();
  EXPECT_EQ(state.generation(), generation); EXPECT_EQ(state.view(), view);
  EXPECT_EQ(state.definition()->parameters.at("component"), 1);
  EXPECT_EQ(state.frozen_run()->source_revision, revision);
  ASSERT_TRUE(state.open_document(handle(), analysis_id, project.project()->revision, changed, false));
  EXPECT_EQ(state.source(), Source::Run); EXPECT_FALSE(state.document_stale());
  ASSERT_TRUE(project.apply(Json::array({{{"op", "delete_record"}, {"id", analysis_id}}})));
  ASSERT_NO_FATAL_FAILURE(settled_project()); state.sync();
  EXPECT_TRUE(state.document_stale()); EXPECT_EQ(state.generation(), generation);
  ASSERT_TRUE(state.frozen_run()); EXPECT_EQ(state.definition()->parameters.at("component"), 1);
  Json read;
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.get", {{"handle", handle()}, {"run_id", run_id}}, read));
  EXPECT_EQ(exact(read.at("run").at("document")), exact(document));
  ASSERT_TRUE(state.open_frozen_run(handle(), read.at("run")));
}

TEST_F(AnalysisGraphRunState, SavedDefinitionAndLocalDraftSurviveAllSourceSwitches)
{
  AnalysisGraphState state(viewer);
  auto saved = document; saved["parameters"]["component"] = 0;
  ASSERT_TRUE(state.open_document(handle(), analysis_id, revision, saved));
  AnalysisParameterDraft draft;
  draft.pin(handle(), analysis_id, revision, "Local draft", saved);
  ASSERT_TRUE(draft.set("component", uint64_t(9007199254740993ULL), draft.generation()).accepted);
  const auto local = exact(draft.candidate_document());
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  state.show_saved(); EXPECT_TRUE(state.saved()); EXPECT_FALSE(state.displayed());
  ASSERT_TRUE(state.definition()); EXPECT_EQ(state.definition()->parameters.at("component"), 0);
  state.show_displayed(true); EXPECT_TRUE(state.displayed()); EXPECT_EQ(state.source(), Source::Displayed);
  state.show_displayed(false); EXPECT_EQ(state.source(), Source::Current);
  state.show_run(); ASSERT_TRUE(state.definition()); EXPECT_EQ(state.definition()->parameters.at("component"), 1);
  EXPECT_TRUE(draft.dirty()); EXPECT_EQ(exact(draft.candidate_document()), local);
  state.clear_run(); EXPECT_EQ(state.source(), Source::Run); EXPECT_FALSE(state.frozen_run()); EXPECT_FALSE(state.definition());
  state.show_saved(); ASSERT_TRUE(state.definition()); EXPECT_EQ(state.definition()->parameters.at("component"), 0);
  EXPECT_EQ(state.document_id(), analysis_id); EXPECT_TRUE(draft.dirty());
}

TEST_F(AnalysisGraphRunState, OtherRunReadsAndLifecycleChangesCannotRetargetPinnedGraph)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  const auto generation = state.generation();
  Json another, cancelled;
  ASSERT_NO_FATAL_FAILURE(prepare(other_run_id, another));
  ASSERT_NO_FATAL_FAILURE(call("project.analysis_runs.cancel", {{"handle", handle()}, {"run_id", run_id}}, cancelled));
  EXPECT_EQ(cancelled.at("run").at("status"), "cancelled");
  state.sync(); EXPECT_EQ(state.frozen_run()->id, run_id); EXPECT_EQ(state.generation(), generation);
  ASSERT_TRUE(state.open_frozen_run(handle(), another));
  EXPECT_EQ(state.frozen_run()->id, other_run_id); EXPECT_GT(state.generation(), generation);
  ASSERT_TRUE(state.open_frozen_run(handle(), cancelled.at("run")));
  EXPECT_EQ(state.frozen_run()->id, run_id); EXPECT_FALSE(state.inspection());
}

TEST_F(AnalysisGraphRunState, InvalidIdentityNumericBoundsAndBindingsPreservePreviousModeAndSnapshot)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_document(handle(), analysis_id, revision, document));
  ASSERT_TRUE(state.open_frozen_run(handle(), run)); state.show_saved();
  const auto generation = state.generation();
  const auto view = state.view();
  auto reject = [&](const Json &value) {
    EXPECT_FALSE(state.open_frozen_run(handle(), value));
    EXPECT_EQ(state.source(), Source::Saved); EXPECT_EQ(state.generation(), generation); EXPECT_EQ(state.view(), view);
    ASSERT_TRUE(state.frozen_run()); EXPECT_EQ(state.frozen_run()->id, run_id);
  };
  auto invalid = run; invalid["id"] = "AD5DFB3F-94A1-4CD2-A1E7-C731C84C2B42"; reject(invalid);
  invalid = run; invalid["project_id"] = other_run_id; reject(invalid);
  invalid = run; invalid["source_revision"] = true; reject(invalid);
  invalid = run; invalid["source_revision"] = 1.0; reject(invalid);
  invalid = run; invalid["source_revision"] = std::numeric_limits<uint64_t>::max(); reject(invalid);
  invalid = run; invalid["source_revision"] = -1; reject(invalid);
  invalid = run; invalid["plan_sha256"] = std::string(64, 'g'); reject(invalid);
  invalid = run; invalid["analysis_name"] = std::string(1025, 'x'); reject(invalid);
  invalid = run; invalid["analysis_name"] = std::string("\xc0\x80", 2); reject(invalid);
  invalid = run; invalid["created_at"] = nullptr; reject(invalid);
  invalid = run; invalid["bindings"]["data"]["input.dat"]["size"] = -1; reject(invalid);
  invalid = run; invalid["bindings"]["data"]["input.dat"]["size"] = 256ULL * 1024 * 1024 + 1; reject(invalid);
  invalid = run; invalid["bindings"]["data"]["input.dat"]["size"] = 256ULL * 1024 * 1024;
  invalid["bindings"]["data"]["second.dat"] = run.at("bindings").at("data").at("input.dat"); reject(invalid);
  invalid = run; invalid["bindings"]["data"]["input.dat"]["extra"] = 1; reject(invalid);
  invalid = run; invalid["bindings"]["data"][std::string(1025, 'x')] = run.at("bindings").at("data").at("input.dat"); reject(invalid);
  invalid = run;
  for (int i = 0; i < 100; ++i) { invalid["bindings"]["data"]["file" + std::to_string(i)] = run.at("bindings").at("data").at("input.dat"); }
  reject(invalid);
  EXPECT_FALSE(state.open_frozen_run("other-opening", run));
  EXPECT_EQ(state.generation(), generation);
}

TEST_F(AnalysisGraphRunState, DocumentDepthAndRawLimitsAreCheckedBeforeAdoptingAReplacement)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  const auto generation = state.generation();
  auto invalid = run; invalid["document"]["parameters"]["huge"] = std::string(384 * 1024, 'x');
  EXPECT_FALSE(state.open_frozen_run(handle(), invalid));
  invalid = run; invalid["document"]["parameters"]["value"] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(state.open_frozen_run(handle(), invalid));
  invalid = run; invalid["document"]["outputs"] = Json::array({"missing"});
  EXPECT_FALSE(state.open_frozen_run(handle(), invalid));
  invalid = run; invalid["document"]["graph"]["nodes"][0]["id"] = 42;
  EXPECT_FALSE(state.open_frozen_run(handle(), invalid));
  Json deep = 0;
  for (int i = 0; i < 10000; ++i) { deep = Json::array({std::move(deep)}); }
  invalid = run; invalid["document"]["parameters"]["nested"] = std::move(deep);
  EXPECT_FALSE(state.open_frozen_run(handle(), invalid));
  EXPECT_EQ(state.generation(), generation); EXPECT_EQ(state.frozen_run()->id, run_id);
  auto boundary = run; Json accepted = 0;
  for (int i = 0; i < 62; ++i) { accepted = Json::array({std::move(accepted)}); }
  boundary["document"]["parameters"]["nested"] = std::move(accepted);
  ASSERT_TRUE(state.open_frozen_run(handle(), boundary));
  EXPECT_EQ(exact(state.definition()->parameters), exact(boundary.at("document").at("parameters")));
  boundary["document"]["outputs"] = Json::array();
  ASSERT_TRUE(state.open_frozen_run(handle(), boundary)); EXPECT_TRUE(state.definition()->requested_outputs.empty());
}

TEST_F(AnalysisGraphRunState, ExplicitValidationUsesFrozenParametersAndCurrentCatalogOnly)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  auto live = document; live["parameters"]["component"] = -1;
  ASSERT_TRUE(state.open_document(handle(), analysis_id, revision, live, false));
  const auto calls = client->stats().calls_sent;
  ASSERT_TRUE(state.validate());
  ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30));
  ASSERT_TRUE(state.validation().is_object()) << state.validation_error();
  EXPECT_EQ(state.validation().at("ok"), true); EXPECT_EQ(client->stats().calls_sent, calls + 1);
  state.show_saved(); ASSERT_TRUE(state.validate());
  ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30));
  ASSERT_TRUE(state.validation().is_object()) << state.validation_error();
  EXPECT_EQ(state.validation().at("ok"), false);
  EXPECT_FALSE(state.inspection()); EXPECT_EQ(project.project()->revision, revision);
}

TEST_F(AnalysisGraphRunState, UnconsumedLifecycleAndResultFieldsAreNeverTraversedOrCopied)
{
  AnalysisGraphState state(viewer);
  // The public method consumes a previously validated run. Synthetic unconsumed extensions
  // exercise its copy boundary, without claiming that these are valid wire lifecycle values.
  Json deep = 0;
  for (int i = 0; i < 10000; ++i) { deep = Json::array({std::move(deep)}); }
  run["result"] = std::move(deep);
  run["error"] = std::string(1024 * 1024, 'x');
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  EXPECT_EQ(exact(state.definition()->graph), exact(document.at("graph")));
  EXPECT_EQ(state.frozen_run()->id, run_id);
  EXPECT_FALSE(state.inspection()); EXPECT_FALSE(state.configuration());
  run["result"] = nullptr; run["error"] = nullptr;
  state.sync(); EXPECT_EQ(state.frozen_run()->id, run_id);
}

TEST_F(AnalysisGraphRunState, SameGraphDifferentRunDiscardsQueuedValidationAndRequiresExplicitRetry)
{
  Json another; ASSERT_NO_FATAL_FAILURE(prepare(other_run_id, another));
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  ASSERT_NO_FATAL_FAILURE(queued_validation(state));
  const auto generation = state.generation();
  ASSERT_TRUE(state.open_frozen_run(handle(), another)); loop.run_ready();
  EXPECT_GT(state.generation(), generation); EXPECT_FALSE(state.validating()); EXPECT_TRUE(state.validation().is_null());
  EXPECT_EQ(state.frozen_run()->id, other_run_id);
  ASSERT_TRUE(state.validate()); ASSERT_TRUE(loop.pump_until([&] { return !state.validating(); }, 30));
  ASSERT_TRUE(state.validation().is_object()); EXPECT_EQ(state.validation().at("ok"), true);
}

TEST_F(AnalysisGraphRunState, ClosedAndReopenedProjectClearsEvenAnInactiveFrozenSnapshot)
{
  AnalysisGraphState state(viewer);
  const auto old_handle = handle();
  ASSERT_TRUE(state.open_frozen_run(old_handle, run)); state.show_displayed(false);
  ASSERT_TRUE(project.close()); ASSERT_NO_FATAL_FAILURE(settled_project()); state.sync();
  EXPECT_FALSE(state.frozen_run()); EXPECT_EQ(state.source(), Source::Current);
  ASSERT_TRUE(project.open(directory.str() + "/project")); ASSERT_NO_FATAL_FAILURE(settled_project());
  ASSERT_TRUE(project.loaded()); EXPECT_NE(handle(), old_handle); state.show_run();
  EXPECT_FALSE(state.definition()); EXPECT_FALSE(state.frozen_run());
  EXPECT_FALSE(state.open_frozen_run(old_handle, run));
  ASSERT_TRUE(state.open_frozen_run(handle(), run)); EXPECT_EQ(state.frozen_run()->id, run_id);
}

TEST_F(AnalysisGraphRunState, DetachedSessionDiscardsQueuedValidationAndFrozenSourceWithoutViewerWork)
{
  AnalysisGraphState state(viewer);
  ASSERT_TRUE(state.open_frozen_run(handle(), run));
  ASSERT_NO_FATAL_FAILURE(queued_validation(state));
  const auto viewer_version = viewer.version();
  store.set_bridge(nullptr); loop.run_ready(); // Callback itself must sync and fence this change.
  EXPECT_FALSE(state.frozen_run()); EXPECT_FALSE(state.definition()); EXPECT_FALSE(state.validating());
  EXPECT_TRUE(state.validation().is_null()); EXPECT_EQ(state.source(), Source::Run);
  EXPECT_EQ(viewer.version(), viewer_version); EXPECT_FALSE(state.open_frozen_run(handle(), run));
  store.set_bridge(client.get()); state.sync();
  EXPECT_FALSE(state.frozen_run()); ASSERT_TRUE(state.open_frozen_run(handle(), run));
  state.show_saved(); store.set_bridge(nullptr); state.sync();
  EXPECT_FALSE(state.frozen_run()); EXPECT_EQ(state.source(), Source::Saved);
}

TEST_F(AnalysisGraphRunState, StoppedReadySessionAndDestroyedControllerRejectLateValidation)
{
  auto state = std::make_unique<AnalysisGraphState>(viewer);
  ASSERT_TRUE(state->open_frozen_run(handle(), run));
  ASSERT_NO_FATAL_FAILURE(queued_validation(*state)); state.reset(); loop.run_ready();
  AnalysisGraphState next(viewer);
  ASSERT_TRUE(next.open_frozen_run(handle(), run));
  ASSERT_TRUE(next.validate()); client->close(); next.sync(); loop.run_ready();
  EXPECT_FALSE(next.frozen_run()); EXPECT_FALSE(next.definition()); EXPECT_FALSE(next.validation_available());
  EXPECT_FALSE(next.validating()); EXPECT_TRUE(next.validation().is_null());
}

}  // namespace
}  // namespace stk::app
