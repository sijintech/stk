/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"
#include "stk/app/table_workbench_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"

#include <cstdlib>
#include <filesystem>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
const std::string samples = "d2222222-2222-4222-8222-222222222222";
const std::string evidence = "d3333333-3333-4333-8333-333333333333";
const std::string row_a = "d4444444-4444-4444-8444-444444444444";
const std::string row_b = "d5555555-5555-4555-8555-555555555555";

TEST(AppStoreOpenResult, ChecksTheGuardAtConsumptionAfterRemovingThePendingRequest)
{
  AppStore store;
  bool checked = false;
  OpenResultRequest request;
  request.local_paths = {"public-synthetic.stkp"};
  request.still_current = [&] {
    checked = true;
    EXPECT_FALSE(store.has_open_result());
    return false;
  };
  store.request_open_result(std::move(request));
  EXPECT_TRUE(store.has_open_result());
  EXPECT_FALSE(checked);
  EXPECT_FALSE(store.take_open_result());
  EXPECT_TRUE(checked);
  EXPECT_FALSE(store.has_open_result());
  OpenResultRequest ordinary;
  ordinary.local_paths = {"explicit-synthetic.stkp"};
  store.request_open_result(std::move(ordinary));
  const auto accepted = store.take_open_result();
  ASSERT_TRUE(accepted);
  EXPECT_EQ(accepted->local_paths, (std::vector<std::string>{"explicit-synthetic.stkp"}));
}

class TableObjectPreviewPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"table-object-preview"};
  bridge::test::ManualLoop loop;
  AppStore store;
  std::unique_ptr<bridge::Client> client;
  std::string file_id;
  fs::path payload_path;
  std::shared_ptr<const io::Payload> original_payload;
  ProjectState &project() { return store.project(); }
  ViewerState &viewer() { return store.viewer(); }
  void idle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(project().error().empty()) << project().error();
  }
  std::function<bool()> source_guard()
  {
    const auto handle = project().project()->handle;
    const auto revision = project().project()->revision;
    const auto table = project().table_id(), record = project().record_id();
    const auto version = viewer().version();
    return [this, handle, revision, table, record, version] {
      return project().loaded() && project().project()->handle == handle &&
          project().project()->revision == revision && project().table_id() == table &&
          project().record_id() == record && viewer().version() == version;
    };
  }
  void queue_preview()
  {
    ASSERT_TRUE(project().view_file_record(file_id, "", source_guard()));
    ASSERT_NO_FATAL_FAILURE(idle());
    ASSERT_TRUE(store.has_open_result());
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.executor = loop.executor();
    options.state_dir = directory.str() + "/bridge";
    options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready();
    store.set_bridge(client.get());
    project().sync();
    ASSERT_TRUE(project().create(directory.str() + "/project", "Synthetic file object preview"));
    ASSERT_NO_FATAL_FAILURE(idle());
    const auto fixture = fs::path(STK_REPO_ROOT) / "desktop/tests/viewer/fixtures/muferro_domains.stkp";
    payload_path = directory.path() / "project" / "public-synthetic.stkp";
    fs::copy_file(fixture, payload_path);
    ASSERT_TRUE(project().index_files({core::path_to_utf8(payload_path)}));
    ASSERT_NO_FATAL_FAILURE(idle());
    ASSERT_TRUE(project().selected_file());
    file_id = project().record_id();
    const Json reference = {{"version", 1}, {"project_id", project().project()->id}, {"kind", "file"}, {"id", file_id}};
    ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", samples}, {"name", "Synthetic samples"}},
      {{"op", "add_field"}, {"table_id", samples}, {"id", evidence}, {"name", "Evidence"}, {"type", "object"},
       {"options", {{"version", 1}, {"kinds", Json::array({"file"})}}}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_a}},
      {{"op", "add_record"}, {"table_id", samples}, {"id", row_b}},
      {{"op", "set_cell"}, {"table_id", samples}, {"record_id", row_a}, {"field_id", evidence}, {"value", reference}},
    })));
    ASSERT_NO_FATAL_FAILURE(idle());
    project().select_table(samples);
    project().select_record(row_a);
    project().sync();
    ASSERT_NO_FATAL_FAILURE(idle());
    ASSERT_NE(project().table(), nullptr);
    ASSERT_GE(project().selected_record(), 0);
    ASSERT_FALSE(project().selected_file());
    TableWorkbenchState reads(store);
    ASSERT_TRUE(reads.resolve_object({{"reference", reference}}));
    ASSERT_TRUE(loop.pump_until([&] { return !reads.busy(); }, 30));
    ASSERT_TRUE(reads.error().empty()) << reads.error();
    ASSERT_EQ(reads.resolved_object().at("state"), "available");
    original_payload = std::make_shared<io::Payload>(io::read_stkp(fixture));
    viewer().open_payload(original_payload, "Existing synthetic result");
  }
  void TearDown() override
  {
    EXPECT_EQ(viewer().evaluations_started(), 0);
    project().attach(nullptr);
    store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(TableObjectPreviewPython, IndexedObjectPreviewOpensTheVerifiedPathWithoutChangingTheTableSelection)
{
  const auto revision = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(queue_preview());
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().project()->revision, revision);
  const auto request = store.take_open_result();
  ASSERT_TRUE(request);
  ASSERT_EQ(request->local_paths.size(), 1u);
  std::error_code error;
  EXPECT_TRUE(fs::equivalent(core::path_from_utf8(request->local_paths[0]), payload_path, error));
  EXPECT_FALSE(error) << error.message();
  ASSERT_TRUE(viewer().open(*request));
  ASSERT_TRUE(loop.pump_until([&] { viewer().pump(); return viewer().base_payload() != original_payload && bool(viewer().payload()); }, 30));
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(project().record_id(), row_a);
  EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(TableObjectPreviewPython, SelectionChangedAfterResolutionRejectsTheQueuedPreviewAtConsumption)
{
  ASSERT_NO_FATAL_FAILURE(queue_preview());
  project().select_record(row_b);
  EXPECT_FALSE(store.take_open_result());
  EXPECT_FALSE(store.has_open_result());
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(project().record_id(), row_b);
  EXPECT_EQ(viewer().base_payload(), original_payload);
}

TEST_F(TableObjectPreviewPython, NewViewerSourceAfterResolutionCannotBeOverwrittenByTheQueuedPreview)
{
  ASSERT_NO_FATAL_FAILURE(queue_preview());
  const auto intervening = std::make_shared<io::Payload>(io::read_stkp(payload_path));
  viewer().open_payload(intervening, "Intervening synthetic result");
  EXPECT_FALSE(store.take_open_result());
  EXPECT_FALSE(store.has_open_result());
  EXPECT_EQ(viewer().base_payload(), intervening);
  EXPECT_EQ(project().table_id(), samples);
  EXPECT_EQ(project().record_id(), row_a);
}
}  // namespace
}  // namespace stk::app
