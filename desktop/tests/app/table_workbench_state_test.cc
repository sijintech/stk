/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"
#include "stk/app/table_workbench_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"

#include <cstdlib>
#include <fstream>
#include <limits>

namespace stk::app {
namespace {
using io::Json;
const std::string table_a = "11111111-1111-4111-8111-111111111111";
const std::string temperature = "22222222-2222-4222-8222-222222222222";
const std::string counter = "33333333-3333-4333-8333-333333333333";
const std::string row_a = "44444444-4444-4444-8444-444444444444";
const std::string table_b = "55555555-5555-4555-8555-555555555555";
const std::string label = "66666666-6666-4666-8666-666666666666";
const std::string row_b = "77777777-7777-4777-8777-777777777777";
const std::string saved_view = "88888888-8888-4888-8888-888888888888";
const std::string row_a2 = "99999999-9999-4999-8999-999999999999";
const std::string phase = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const std::string dry = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

Json seed_commands()
{
  return Json::array({
      {{"op", "create_table"}, {"id", table_a}, {"name", "Synthetic PET samples"}},
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table_a}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"id", counter}, {"table_id", table_a}, {"name", "Exact counter"}, {"type", "integer"}},
      {{"op", "add_field"}, {"id", phase}, {"table_id", table_a}, {"name", "State"}, {"type", "single_select"},
       {"options", {{"version", 1}, {"choices", Json::array({{{"id", dry}, {"label", "Dry"}, {"color", "#123456"}}})}}}},
      {{"op", "add_record"}, {"id", row_a}, {"table_id", table_a}},
      {{"op", "add_record"}, {"id", row_a2}, {"table_id", table_a}},
      {{"op", "set_cell"}, {"table_id", table_a}, {"record_id", row_a}, {"field_id", temperature}, {"value", 300}},
      {{"op", "set_cell"}, {"table_id", table_a}, {"record_id", row_a}, {"field_id", counter}, {"value", std::numeric_limits<int64_t>::max()}},
      {{"op", "set_cell"}, {"table_id", table_a}, {"record_id", row_a}, {"field_id", phase}, {"value", dry}},
      {{"op", "set_cell"}, {"table_id", table_a}, {"record_id", row_a2}, {"field_id", temperature}, {"value", nullptr}},
      {{"op", "create_table"}, {"id", table_b}, {"name", "Synthetic batches"}},
      {{"op", "add_field"}, {"id", label}, {"table_id", table_b}, {"name", "Batch"}, {"type", "text"}},
      {{"op", "add_record"}, {"id", row_b}, {"table_id", table_b}},
      {{"op", "set_cell"}, {"table_id", table_b}, {"record_id", row_b}, {"field_id", label}, {"value", "Synthetic batch B"}},
  });
}

class TableWorkbenchPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"table-workbench"};
  bridge::test::ManualLoop loop;
  AppStore store;
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<TableWorkbenchState> table;
  std::string python;
  ProjectState &project() { return store.project(); }
  bridge::ClientOptions options()
  {
    bridge::ClientOptions value;
    value.python.configured = python;
    value.executor = loop.executor();
    value.state_dir = directory.str() + "/bridge";
    value.cache_dir = directory.str() + "/cache";
    value.env["PYTHONPATH"] = STK_REPO_ROOT;
    value.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    value.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    value.env["STK_TOKEN_PLAN_API_KEY"] = "";
    value.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    value.strict = value.validate = true;
    return value;
  }
  void idle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  void read()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !table->busy(); }, 30));
    ASSERT_TRUE(table->error().empty()) << table->error();
  }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    client = bridge::Client::create(options());
    ASSERT_TRUE(client->start());
    ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready();
    store.set_bridge(client.get());
    project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "Synthetic table workbench"));
    ASSERT_NO_FATAL_FAILURE(idle());
    ASSERT_TRUE(project().apply(seed_commands()));
    ASSERT_NO_FATAL_FAILURE(idle());
    project().select_table(table_a);
    table = std::make_unique<TableWorkbenchState>(store);
    ASSERT_TRUE(table->supported());
  }
  void TearDown() override
  {
    table.reset();
    EXPECT_EQ(store.viewer().evaluations_started(), 0);
    project().attach(nullptr);
    store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(TableWorkbenchPython, QueriesTypedValuesAndFieldOptionsWithoutEditingOrOpeningViewer)
{
  const auto revision = project().project()->revision;
  ASSERT_EQ(project().project()->format_version, 14);
  ASSERT_EQ(project().table()->fields.back().options.at("choices").at(0).at("id"), dry);
  ASSERT_TRUE(table->load_views());
  ASSERT_TRUE(table->query());
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_TRUE(table->views().at("views").empty());
  const auto &result = table->query_result();
  EXPECT_EQ(result.at("table_id"), table_a);
  ASSERT_EQ(result.at("record_ids"), Json::array({row_a, row_a2}));
  EXPECT_EQ(result.at("records").at(0).at("values").at(counter).get<int64_t>(), std::numeric_limits<int64_t>::max());
  EXPECT_TRUE(result.at("records").at(1).at("values").at(temperature).is_null());
  EXPECT_FALSE(result.at("records").at(1).at("values").contains(counter));
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table_id(), table_a);
}

TEST_F(TableWorkbenchPython, PasteOnlyPlansUntilExplicitApplyAndUndoRestoresExactValues)
{
  const auto revision = project().project()->revision;
  Json plan;
  ASSERT_TRUE(table->plan_paste({{"record_ids", Json::array({row_a, row_a2})},
      {"field_ids", Json::array({temperature, counter})},
      {"text", "310\t9223372036854775806\n320\t-9223372036854775807"}}, [&](const Json &value) { plan = value; }));
  ASSERT_NO_FATAL_FAILURE(read());
  ASSERT_EQ(plan.at("base_revision"), revision);
  ASSERT_EQ(plan.at("command_count"), 4);
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(project().table()->cell(0, 0)->get<int>(), 300);
  ASSERT_TRUE(project().apply(plan.at("commands"), plan.at("base_revision").get<int64_t>()));
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_C(9223372036854775806));
  EXPECT_EQ(project().table()->cell(1, 1)->get<int64_t>(), -INT64_C(9223372036854775807));
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), std::numeric_limits<int64_t>::max());
  EXPECT_TRUE(project().table()->cell(1, 0)->is_null());
  EXPECT_EQ(project().table()->cell(1, 1), nullptr);
}

TEST_F(TableWorkbenchPython, ListsSavedViewsAndResolvesExplicitOtherTableRecordCandidates)
{
  ASSERT_TRUE(project().apply(Json::array({{{"op", "put_table_view"}, {"id", saved_view},
      {"table_id", table_a}, {"name", "By temperature"}, {"definition", {{"version", 1}, {"kind", "grid"}}}}})));
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(table->load_views());
  ASSERT_TRUE(table->load_view(saved_view));
  ASSERT_TRUE(table->object_candidates({{"kind", "record"}, {"table_id", table_b}}));
  ASSERT_NO_FATAL_FAILURE(read());
  ASSERT_EQ(table->views().at("views").size(), 1u);
  EXPECT_EQ(table->selected_view().at("view").at("id"), saved_view);
  const auto &items = table->candidates().at("items");
  ASSERT_EQ(items.size(), 1u);
  EXPECT_EQ(items.at(0).at("reference").at("table_id"), table_b);
  EXPECT_EQ(items.at(0).at("reference").at("id"), row_b);
  ASSERT_TRUE(table->resolve_object({{"reference", items.at(0).at("reference")}}));
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_EQ(table->resolved_object().at("state"), "available");
  EXPECT_EQ(project().table_id(), table_a);
}

TEST_F(TableWorkbenchPython, ReplacementAndTableSwitchDropOldCallbacks)
{
  bool old_called = false;
  ASSERT_TRUE(table->query({{"offset", 0}, {"limit", 1}}, [&](const Json &) { old_called = true; }));
  ASSERT_TRUE(table->query({{"offset", 1}, {"limit", 1}}));
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_FALSE(old_called);
  EXPECT_EQ(table->query_result().at("record_ids"), Json::array({row_a2}));
  const auto source = table->scope();
  ASSERT_TRUE(table->query(Json::object(), [&](const Json &) { old_called = true; }));
  project().select_table(table_b);
  table->sync();
  EXPECT_FALSE(table->current(source));
  EXPECT_TRUE(table->query_result().is_null());
  ASSERT_TRUE(table->query());
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_FALSE(old_called);
  EXPECT_EQ(table->query_result().at("table_id"), table_b);
  EXPECT_EQ(table->query_result().at("record_ids"), Json::array({row_b}));
}

TEST_F(TableWorkbenchPython, RevisionChangeInvalidatesPendingPlanAndSourceToken)
{
  const auto source = table->scope();
  bool called = false;
  ASSERT_TRUE(table->plan_paste({{"record_ids", Json::array({row_a})}, {"field_ids", Json::array({temperature})},
      {"text", "310"}}, [&](const Json &) { called = true; }));
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", table_a},
      {"record_id", row_a}, {"field_id", temperature}, {"value", 305}}})));
  ASSERT_NO_FATAL_FAILURE(idle());
  table->sync();
  EXPECT_FALSE(called);
  EXPECT_FALSE(table->busy());
  EXPECT_FALSE(table->current(source));
  EXPECT_EQ(project().table()->cell(0, 0)->get<int>(), 305);
  ASSERT_TRUE(table->query());
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_EQ(table->query_result().at("revision"), project().project()->revision);
}

TEST_F(TableWorkbenchPython, ErrorsAreVisibleAndGenericCallsCannotMutateOrRetarget)
{
  const auto revision = project().project()->revision;
  EXPECT_FALSE(table->scoped_call("project.apply", {{"commands", Json::array()}}));
  EXPECT_FALSE(table->error().empty());
  EXPECT_FALSE(table->query({{"table_id", table_b}}));
  EXPECT_FALSE(table->error().empty());
  bool called = false;
  ASSERT_TRUE(table->plan_paste({{"record_ids", Json::array({row_a})}, {"field_ids", Json::array({temperature})},
      {"text", "invalid number"}}, [&](const Json &) { called = true; }));
  ASSERT_TRUE(loop.pump_until([&] { return !table->busy(); }, 30));
  EXPECT_FALSE(called);
  EXPECT_FALSE(table->error().empty());
  EXPECT_EQ(table->error_method(), "project.table.paste.plan");
  EXPECT_EQ(project().project()->revision, revision);
  table->clear_error();
  EXPECT_TRUE(table->error().empty());
}

TEST_F(TableWorkbenchPython, DisconnectClearsPendingReadsAndNewBridgeNeverReplaysThem)
{
  bool called = false;
  const auto source = table->scope();
  const auto id = project().project()->id;
  ASSERT_TRUE(table->query(Json::object(), [&](const Json &) { called = true; }));
  store.set_bridge(nullptr);
  table->sync();
  client->close();
  loop.run_ready();
  EXPECT_FALSE(called);
  EXPECT_FALSE(table->supported());
  EXPECT_FALSE(table->busy());
  EXPECT_TRUE(table->query_result().is_null());
  client = bridge::Client::create(options());
  ASSERT_TRUE(client->start());
  ASSERT_TRUE(client->wait_ready(60));
  loop.run_ready();
  store.set_bridge(client.get());
  table->sync();
  ASSERT_TRUE(loop.pump_until([&] { table->sync(); return project().loaded() && !project().busy(); }, 30));
  EXPECT_EQ(project().project()->id, id);
  EXPECT_FALSE(table->current(source));
  EXPECT_FALSE(called);
  EXPECT_TRUE(table->query_result().is_null());
  EXPECT_EQ(client->stats().calls_retried, 0u);
  ASSERT_TRUE(table->query());
  ASSERT_NO_FATAL_FAILURE(read());
  EXPECT_EQ(table->query_result().at("table_id"), table_a);
}

TEST_F(TableWorkbenchPython, CapabilityChecksRejectDetachedBridgeBeforeTheNextSync)
{
  ASSERT_TRUE(table->supported());
  store.set_bridge(nullptr);
  EXPECT_FALSE(table->supported());
  EXPECT_FALSE(table->supports("project.table.query"));
  client->close();
  client.reset();
  // ProjectState and the read controller have not synchronized; both still cache the old
  // pointer. Const capability checks must reject it without touching the destroyed client.
  EXPECT_FALSE(table->supported());
  EXPECT_FALSE(table->supports("project.table.csv.preview"));
  table->sync();
  EXPECT_FALSE(table->supported());
}

TEST_F(TableWorkbenchPython, DestroyedAndInvalidOwnersCannotReceiveAQueuedCompletion)
{
  bool called = false;
  auto doomed = std::make_unique<TableWorkbenchState>(store);
  ASSERT_TRUE(doomed->query(Json::object(), [&](const Json &) { called = true; }));
  doomed.reset();
  bool owner_live = true;
  TableWorkbenchState guarded(store, [&] { return owner_live; });
  ASSERT_TRUE(guarded.query(Json::object(), [&](const Json &) { called = true; }));
  const auto version = guarded.version();
  owner_live = false;  // Owner predicates represent permanent lifetime invalidation, not tab visibility.
  bool marker = false;
  client->project_snapshot(project().project()->handle).then([&](auto response) {
    EXPECT_TRUE(response); marker = true;
  });
  ASSERT_TRUE(loop.pump_until([&] { return marker; }, 30));
  EXPECT_FALSE(called);
  EXPECT_EQ(guarded.version(), version);
  EXPECT_TRUE(guarded.query_result().is_null());
}

TEST_F(TableWorkbenchPython, CsvPreviewWorksInAnEmptyProjectAndChangedBytesCannotBeImported)
{
  const auto source = directory.str() + "/synthetic.csv";
  std::ofstream(source, std::ios::binary) << "Sample,Temperature\n\"synthetic, A\",300\nsynthetic B,\n";
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().create(directory.str() + "/empty", "Synthetic empty project"));
  ASSERT_NO_FATAL_FAILURE(idle());
  table->sync();
  ASSERT_TRUE(project().tables().empty());
  EXPECT_TRUE(table->supports("project.table.csv.preview"));
  EXPECT_FALSE(table->supports("project.table.query"));
  ASSERT_TRUE(table->scoped_call("project.table.csv.preview", {{"source", source}, {"limit", 1}}));
  ASSERT_NO_FATAL_FAILURE(read());
  const auto preview = table->csv_preview();
  ASSERT_EQ(preview.at("columns").size(), 2u);
  EXPECT_EQ(preview.at("columns").at(0).at("name"), "Sample");
  EXPECT_EQ(preview.at("rows"), Json::array({Json::array({"synthetic, A", "300"})}));
  EXPECT_EQ(preview.at("total_rows"), 2);
  EXPECT_TRUE(preview.at("truncated").get<bool>());
  EXPECT_TRUE(preview.at("can_import").get<bool>());
  EXPECT_EQ(project().project()->revision, 0);
  EXPECT_TRUE(project().tables().empty());

  std::ofstream(source, std::ios::binary | std::ios::trunc) << "Sample,Temperature\nsynthetic changed,999\n";
  bool done = false, conflict = false;
  bridge::CallOptions never;
  never.retry = bridge::CallOptions::Retry::Never;
  client->call("project.csv.import", {{"handle", project().project()->handle}, {"source", source},
      {"name", "Must not be imported"}, {"expected_revision", 0},
      {"expected_sha256", preview.at("source_sha256")}}, never).then([&](auto result) {
    conflict = !result && result.error().code == bridge::ErrorCode::Conflict;
    done = true;
  });
  ASSERT_TRUE(loop.pump_until([&] { return done; }, 30));
  EXPECT_TRUE(conflict);
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().project()->revision, 0);
  EXPECT_TRUE(project().tables().empty());
}
}  // namespace
}  // namespace stk::app
