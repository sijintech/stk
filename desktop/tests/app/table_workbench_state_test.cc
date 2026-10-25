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
  virtual bridge::ClientOptions options()
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

class ProjectPagingPython : public TableWorkbenchPython {
 protected:
  bridge::ClientOptions options() override
  {
    auto value = TableWorkbenchPython::options();
    const auto script = directory.path() / "paged_bridge.py";
    std::ofstream out(script);
    out << R"PY(
from suan.project import ProjectStore
from suan.desktop_bridge.__main__ import main
from pathlib import Path
def forbidden_snapshot(self):
    raise AssertionError('Native opening must not request a full snapshot')
ProjectStore.snapshot = forbidden_snapshot
original_read = ProjectStore.read_table
def concurrent_read(self, table_id, **kwargs):
    marker = Path(__file__).with_name('concurrent-edit')
    if marker.exists():
        if marker.read_text() != 'continuous':
            marker.unlink()
        self.apply([{'op': 'rename_table', 'id': table_id, 'name': 'Concurrent edit'}],
                   expected_revision=kwargs['expected_revision'])
    return original_read(self, table_id, **kwargs)
ProjectStore.read_table = concurrent_read
main()
)PY";
    out.close();
    value.command = {python, "-u", script.string(), "--stdio", "--state-dir", value.state_dir,
                     "--cache-dir", value.cache_dir, "--strict"};
    return value;
  }
  std::string identity(int n, char prefix = 'a') const
  {
    const auto tail = std::to_string(n);
    return std::string(1, prefix) + "0000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
  }
  void many_records()
  {
    for (int batch = 0; batch < 3; ++batch) {
      Json commands = Json::array();
      for (int i = batch * 300; i < (batch + 1) * 300; ++i) {
        commands.push_back({{"op", "add_record"}, {"table_id", table_a}, {"id", identity(i)}});
        commands.push_back({{"op", "set_cell"}, {"table_id", table_a}, {"record_id", identity(i)},
                            {"field_id", counter}, {"value", INT64_MAX - int64_t(i)}});
      }
      ASSERT_TRUE(project().apply(commands)); ASSERT_NO_FATAL_FAILURE(idle());
    }
  }
  bridge::Result<Json> choose(const std::string &table_id, const std::string &record_id)
  {
    std::optional<bridge::Result<Json>> result;
    project().request_select_async(project().project()->handle, project().project()->revision,
        table_id, record_id, [&](auto value) { result = std::move(value); });
    if (!loop.pump_until([&] { return result.has_value(); }, 30)) {
      return bridge::Error::make(bridge::ErrorCode::Timeout, "Selection did not complete");
    }
    return std::move(*result);
  }
};

TEST_F(ProjectPagingPython, OpeningLargeProjectReadsCatalogAndOnlySelectedRecordPage)
{
  ASSERT_NO_FATAL_FAILURE(many_records());
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().open(directory.str() + "/project")); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().loaded());
  ASSERT_EQ(project().tables().size(), 2u);
  EXPECT_EQ(project().tables()[0].total_records(), 902);
  EXPECT_EQ(project().tables()[0].records.size(), 200u);
  EXPECT_FALSE(project().tables()[0].records_complete);
  EXPECT_EQ(project().tables()[1].total_records(), 1);
  EXPECT_TRUE(project().tables()[1].records.empty());
  EXPECT_EQ(project().tables()[1].fields.front().name, "Batch");
  const auto selected = choose(table_a, identity(899));
  ASSERT_TRUE(selected) << selected.error().describe();
  EXPECT_EQ(project().record_id(), identity(899));
  EXPECT_EQ(project().table()->record_offset, 800);
  EXPECT_EQ(project().table()->records.size(), 102u);
  EXPECT_EQ(project().table()->cell(project().selected_record(), 1)->get<int64_t>(), INT64_MAX - 899);
  const auto missing = choose(table_a, identity(9999));
  ASSERT_FALSE(missing); EXPECT_EQ(missing.error().code, bridge::ErrorCode::NotFound);
  EXPECT_EQ(project().record_id(), identity(899));
  EXPECT_EQ(project().table()->record_offset, 800);
  ASSERT_TRUE(choose(table_b, row_b));
  EXPECT_EQ(project().record_id(), row_b);
  EXPECT_EQ(project().table()->text(0, 0), "Synthetic batch B");
}

TEST_F(ProjectPagingPython, ConcurrentEditBetweenCatalogAndRecordsReloadsOneConsistentRevision)
{
  const auto revision = project().project()->revision;
  { std::ofstream marker(directory.path() / "concurrent-edit"); marker << "synthetic change"; }
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().loaded());
  EXPECT_EQ(project().project()->revision, revision + 1);
  ASSERT_NE(project().table(), nullptr);
  EXPECT_EQ(project().table()->name, "Concurrent edit");
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().table()->cell(project().selected_record(), 1)->get<int64_t>(), INT64_MAX);
}

TEST_F(ProjectPagingPython, ContinuousConcurrentEditsStopAfterBoundedReadsAndAllowExplicitRefresh)
{
  const auto revision = project().project()->revision;
  const auto marker_path = directory.path() / "concurrent-edit";
  { std::ofstream marker(marker_path); marker << "continuous"; }
  project().refresh();
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
  EXPECT_FALSE(project().loaded());
  EXPECT_FALSE(project().error().empty());
  EXPECT_EQ(project().project()->revision, revision); // No partial revision was published.
  std::filesystem::remove(marker_path);
  project().refresh();
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
  ASSERT_TRUE(project().loaded());
  EXPECT_EQ(project().project()->revision, revision + 4); // Initial attempt plus three fresh reads.
  EXPECT_EQ(project().record_id(), row_a);
}

TEST_F(ProjectPagingPython, CatalogContinuesAcrossStructurePagesAtOneRevision)
{
  Json commands = Json::array();
  for (int i = 0; i < 201; ++i) {
    commands.push_back({{"op", "create_table"}, {"id", identity(i, 'b')}, {"name", "Table " + std::to_string(i)}});
  }
  ASSERT_TRUE(project().apply(commands)); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_EQ(project().tables().size(), 203u);
  EXPECT_EQ(project().tables().back().id, identity(200, 'b'));
  EXPECT_TRUE(project().tables().back().records_complete);
  EXPECT_EQ(project().tables().back().total_records(), 0);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().project()->revision, 2);
}

TEST_F(ProjectPagingPython, CancelledUnloadedSelectionLeavesSelectionAndCacheUnchanged)
{
  ASSERT_TRUE(project().tables()[1].records.empty());
  std::optional<bridge::Result<Json>> result;
  bool caller_live = true;
  project().request_select_async(project().project()->handle, project().project()->revision, table_b, row_b,
      [&](auto value) { result = std::move(value); }, [&] { return caller_live; });
  EXPECT_TRUE(project().busy());
  caller_live = false;
  ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); }, 30));
  ASSERT_FALSE(*result); EXPECT_EQ(result->error().code, bridge::ErrorCode::Cancelled);
  EXPECT_EQ(project().table_id(), table_a); EXPECT_EQ(project().record_id(), row_a);
  EXPECT_TRUE(project().tables()[1].records.empty());
  EXPECT_FALSE(project().busy());
}

TEST_F(ProjectPagingPython, RefreshOfDeletedSelectionFallsBackWithinTheNewRevision)
{
  ASSERT_NO_FATAL_FAILURE(many_records());
  ASSERT_TRUE(choose(table_a, identity(899)));
  ASSERT_TRUE(project().apply(Json::array({{{"op", "delete_record"}, {"id", identity(899)}}})));
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().table()->record_offset, 0);
  EXPECT_EQ(project().table()->total_records(), 901);
  EXPECT_EQ(project().table()->records.size(), 200u);
}

TEST_F(ProjectPagingPython, ReadingAnotherPagePreservesSelectionWithOneExtraRecord)
{
  ASSERT_NO_FATAL_FAILURE(many_records());
  ASSERT_TRUE(project().load_table_page(table_a, 400)); ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().table()->record_offset, 400);
  EXPECT_EQ(project().table()->loaded_records(), 200u);
  EXPECT_EQ(project().table()->records.size(), 201u);
  EXPECT_EQ(project().table()->cell(project().selected_record(), 0)->get<int>(), 300);
  project().sync(); EXPECT_FALSE(project().busy());
  ASSERT_TRUE(project().load_table_page(table_a, 600)); ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().table()->records.size(), 201u);
  EXPECT_EQ(project().table()->total_records(), 902);
}

TEST_F(ProjectPagingPython, IndependentPageReadKeepsSharedSelectionAndCache)
{
  ASSERT_NO_FATAL_FAILURE(many_records());
  std::optional<bridge::Result<ProjectTable>> result;
  ASSERT_TRUE(project().read_table_page(table_a, 0, 8, identity(899), [&](auto value) { result = std::move(value); }));
  EXPECT_FALSE(project().busy());
  ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); }, 30));
  ASSERT_TRUE(*result) << result->error().describe();
  EXPECT_EQ(result->value().record_offset, 896);
  EXPECT_EQ(result->value().records.size(), 6u);
  EXPECT_EQ(result->value().records.back().values.at(counter).get<int64_t>(), INT64_MAX - 899);
  EXPECT_EQ(project().table_id(), table_a); EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().table()->record_offset, 0); EXPECT_EQ(project().table()->records.size(), 200u);
}

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

TEST_F(TableWorkbenchPython, IndependentRecordPagesPreserveTypesAndExpireOnSourceChanges)
{
  const auto revision = project().project()->revision;
  TableWorkbenchState other(store);
  ASSERT_TRUE(table->query({{"offset", 1}, {"limit", 1}}));
  ASSERT_TRUE(other.query({{"offset", 0}, {"limit", 1},
      {"definition", {{"version", 1}, {"kind", "grid"},
                       {"columns", Json::array({{{"field_id", counter}}})}}}}));
  EXPECT_EQ(table->query_table(), nullptr);
  ASSERT_NO_FATAL_FAILURE(read());
  ASSERT_TRUE(loop.pump_until([&] { return !other.busy(); }, 30));
  ASSERT_TRUE(other.error().empty()) << other.error();
  ASSERT_NE(table->query_table(), nullptr);
  ASSERT_NE(other.query_table(), nullptr);
  ASSERT_EQ(table->query_table()->records.size(), 1u);
  ASSERT_EQ(other.query_table()->records.size(), 1u);
  EXPECT_EQ(table->query_table()->records[0].id, row_a2);
  EXPECT_EQ(other.query_table()->records[0].id, row_a);
  EXPECT_TRUE(table->query_table()->cell(0, 0)->is_null());
  EXPECT_EQ(table->query_table()->cell(0, 1), nullptr);
  EXPECT_EQ(other.query_table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  // Omitted view columns remain available in record details without loading other rows.
  EXPECT_EQ(other.query_table()->fields.size(), 3u);
  EXPECT_EQ(*other.query_table()->cell(0, 0), 300);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().project()->revision, revision);
  ASSERT_TRUE(table->query({{"offset", 0}, {"limit", 1}}));
  EXPECT_EQ(table->query_table(), nullptr);
  table->cancel();
  ASSERT_TRUE(loop.pump_until([&] { return !table->busy(); }, 30));
  EXPECT_EQ(table->query_table(), nullptr);
  EXPECT_NE(other.query_table(), nullptr);
  project().select_table(table_b);
  EXPECT_EQ(other.query_table(), nullptr);
  other.sync();
  EXPECT_EQ(other.query_table(), nullptr);
}

TEST_F(TableWorkbenchPython, QuerySelectionCachesOneExtraRecordAndHonorsDraftAndRevisionGuards)
{
  std::optional<bridge::Result<Json>> snapshot;
  client->project_snapshot(project().project()->handle).then([&](auto value) { snapshot = std::move(value); });
  ASSERT_TRUE(loop.pump_until([&] { return snapshot.has_value(); }, 30));
  ASSERT_TRUE(snapshot->ok());
  auto metadata = snapshot->value();
  metadata["tables"][0]["records"] = Json::array();
  const auto info = project().project();
  ASSERT_TRUE(project().adopt_workspace_project(info, metadata, table_a, {}));
  ASSERT_TRUE(table->query());
  ASSERT_NO_FATAL_FAILURE(read());
  ASSERT_TRUE(table->select_record(row_a2));
  EXPECT_EQ(project().record_id(), row_a2);
  ASSERT_EQ(project().table()->records.size(), 1u);
  EXPECT_TRUE(project().table()->cell(project().selected_record(), 0)->is_null());
  project().set_selection_guard([] { return false; });
  EXPECT_FALSE(table->select_record(row_a));
  EXPECT_EQ(project().record_id(), row_a2);
  EXPECT_EQ(project().table()->records.size(), 1u);
  project().set_selection_guard({});
  EXPECT_FALSE(project().select_read_record(info->handle, info->revision + 1, table_a, table->query_table()->records[0]));
  EXPECT_FALSE(project().select_read_record(info->handle, info->revision, table_b, table->query_table()->records[0]));
  ASSERT_TRUE(table->select_record(row_a));
  EXPECT_EQ(project().record_id(), row_a);
  ASSERT_EQ(project().table()->records.size(), 1u);
  EXPECT_EQ(project().table()->cell(0, 1)->get<int64_t>(), INT64_MAX);
  EXPECT_FALSE(table->select_record(row_b));
  EXPECT_EQ(project().project()->revision, info->revision);
  ASSERT_TRUE(project().apply(Json::array({{{"op", "set_cell"}, {"table_id", table_a},
      {"record_id", row_a}, {"field_id", temperature}, {"value", 301}}})));
  EXPECT_FALSE(table->select_record(row_a2));
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_FALSE(table->select_record(row_a2));
  // Refresh replaces the cache; later selection must not erase a freshly loaded real row.
  project().select_record(row_a2);
  EXPECT_EQ(project().table()->records.size(), 2u);
  EXPECT_EQ(project().record_id(), row_a2);
}

TEST_F(TableWorkbenchPython, ReviewReadsCompleteBaseInsteadOfTreatingUncachedRecordsAsAdded)
{
  std::optional<bridge::Result<Json>> snapshot;
  client->project_snapshot(project().project()->handle).then([&](auto value) { snapshot = std::move(value); });
  ASSERT_TRUE(loop.pump_until([&] { return snapshot.has_value(); }, 30));
  ASSERT_TRUE(snapshot->ok());
  auto partial = snapshot->value();
  partial["tables"][0]["records"].erase(partial["tables"][0]["records"].begin() + 1);
  partial["tables"][1]["records"] = Json::array();
  const auto info = project().project();
  ASSERT_TRUE(project().adopt_workspace_project(info, partial, table_a, row_a));
  ASSERT_EQ(project().tables()[0].records.size(), 1u);
  ASSERT_TRUE(project().tables()[1].records.empty());
  project().set_review_source(Json::array({{{"op", "set_cell"}, {"table_id", table_a},
      {"record_id", row_a}, {"field_id", temperature}, {"value", 305}}}).dump());
  ASSERT_TRUE(project().preview());
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().review()) << project().review_error();
  ASSERT_EQ(project().review()->differences.size(), 1u);
  const auto &change = project().review()->differences.front();
  EXPECT_EQ(change.kind, "cell");
  EXPECT_EQ(change.record_id, row_a);
  EXPECT_EQ(change.before->at("value"), 300);
  EXPECT_EQ(change.after->at("value"), 305);
  EXPECT_EQ(project().project()->revision, info->revision);
  EXPECT_EQ(project().tables()[0].records.size(), 1u);
  EXPECT_TRUE(project().tables()[1].records.empty());
  EXPECT_TRUE(project().can_apply_review());
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
  ASSERT_NO_FATAL_FAILURE(idle()); // Shared selected-row page is asynchronous after switching tables.
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
