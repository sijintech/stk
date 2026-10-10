/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/project_agent.hh"
#include "stk/app/project_attention.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_archive.hh"
#include "stk/app/project_data_labels.hh"
#include "stk/app/model_settings.hh"
#include "stk/app/jobs_state.hh"
#include "stk/core/paths.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <cmath>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iterator>
#include "stk/platform/file_dialog.hh"

namespace stk::app {
namespace {

using io::Json;

const std::string table_id = "11111111-1111-4111-8111-111111111111";
const std::string field_id = "22222222-2222-4222-8222-222222222222";
const std::string record_id = "33333333-3333-4333-8333-333333333333";

Json sample_commands()
{
  return Json::array({
      {{"op", "create_table"}, {"id", table_id}, {"name", "Cases"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", field_id},
       {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"table_id", table_id}, {"id", record_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", field_id}, {"value", 300}},
  });
}

Json set_cell(const int value)
{
  return Json::array({{{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id},
                       {"field_id", field_id}, {"value", value}}});
}

TEST(ProjectTable, LiteralTypesPreservePrecisionAndRejectInvalidInput)
{
  std::string error;
  EXPECT_EQ(project_literal("text", "  中文\n", error)->get<std::string>(), "  中文\n");
  EXPECT_EQ(project_literal("text", "", error)->get<std::string>(), "");
  EXPECT_EQ(project_literal("integer", "9223372036854775807", error)->get<int64_t>(), INT64_MAX);
  EXPECT_EQ(project_literal("integer", "-9223372036854775808", error)->get<int64_t>(), INT64_MIN);
  EXPECT_FALSE(project_literal("integer", "9223372036854775808", error));
  EXPECT_FALSE(project_literal("integer", "-9223372036854775809", error));
  EXPECT_FALSE(project_literal("integer", "3.0", error));
  EXPECT_FALSE(project_literal("integer", "true", error));
  EXPECT_FALSE(project_literal("number", "true", error));
  EXPECT_FALSE(project_literal("number", "NaN", error));
  EXPECT_FALSE(project_literal("number", "1e999", error));
  EXPECT_FALSE(project_literal("boolean", "1", error));
  EXPECT_FALSE(project_literal("json", "[broken", error));
  EXPECT_FALSE(project_literal("unknown", "null", error));
  ASSERT_TRUE(project_literal("number", "1e-12", error));
  EXPECT_EQ(project_literal("number", "1e-12", error)->get<double>(), 1e-12);
  EXPECT_TRUE(project_literal("boolean", "false", error)->is_boolean());
  EXPECT_TRUE(project_literal("number", "null", error)->is_null());
  EXPECT_EQ(project_literal("json", "{\"a\":[1,true,null]}", error)->at("a").size(), 3u);
  EXPECT_TRUE(error.empty());
}

TEST(ProjectTable, SweepAxesParseTypedRangesAndListsLikeLiterals)
{
  std::string error;
  const auto range = project_sweep_axis("number", true, " 300 ", "400", "3", "", error);
  ASSERT_TRUE(range);
  EXPECT_EQ(range->values, 3u);
  EXPECT_EQ(range->axis, Json({{"start", 300}, {"stop", 400}, {"count", 3}}));
  EXPECT_FALSE(project_sweep_axis("integer", true, "1.5", "4", "3", "", error));
  EXPECT_EQ(error, "project.sweep.error.range");
  EXPECT_FALSE(project_sweep_axis("number", true, "null", "4", "3", "", error));
  EXPECT_EQ(error, "project.sweep.error.range");
  for (const char *count : {"0", "1001", "2.5", ""}) {
    EXPECT_FALSE(project_sweep_axis("number", true, "1", "2", count, "", error)) << count;
    EXPECT_EQ(error, "project.sweep.error.count");
  }
  EXPECT_FALSE(project_sweep_axis("text", true, "a", "b", "2", "", error));
  EXPECT_EQ(error, "project.sweep.error.range_type");
  EXPECT_FALSE(project_sweep_axis("json", false, "", "", "", "[1]", error));
  EXPECT_EQ(error, "project.sweep.error.type");
  const auto text = project_sweep_axis("text", false, "", "", "", " bulk , 薄膜 ", error);
  ASSERT_TRUE(text);
  EXPECT_EQ(text->axis, Json({{"values", {"bulk", "薄膜"}}}));
  const auto flags = project_sweep_axis("boolean", false, "", "", "", "true,false", error);
  ASSERT_TRUE(flags);
  EXPECT_EQ(flags->values, 2u);
  const auto big = project_sweep_axis("integer", false, "", "", "", "9223372036854775807, -1", error);
  ASSERT_TRUE(big);
  EXPECT_EQ(big->axis.at("values").at(0).get<int64_t>(), INT64_MAX);
  EXPECT_TRUE(error.empty());
  for (const char *list : {"", "1,", "1,,2", "1, null", "1, x", "true"}) {
    EXPECT_FALSE(project_sweep_axis("number", false, "", "", "", list, error)) << list;
    EXPECT_EQ(error, "project.sweep.error.list");
  }
}

TEST(ProjectTable, NumericOrderingUsesEvaluatedValuesAndPreservesInt64Precision)
{
  ProjectTable table;
  table.fields = {{"n", "Value", "number", "K"}};
  table.records = {{"a", {{"n", 10}}, {{"n", {{"kind", "expression"}}}}},
                   {"b", {{"n", 2}}, {{"n", {{"kind", "reference"}}}}},
                   {"c", Json::object()},
                   {"d", {{"n", 1}}, Json::object(), {{"n", {{"state", "error"}, {"error", {{"code", "cycle"}}}}}}}};
  EXPECT_EQ(table.text(0, 0), "= 10");
  EXPECT_GT(table.compare(0, 1, 0), 0);
  EXPECT_LT(table.compare(1, 0, 0), 0);
  EXPECT_EQ(table.compare(0, 0, 0), 0);
  EXPECT_GT(table.compare(2, 1, 0), 0);
  EXPECT_GT(table.compare(3, 1, 0), 0);
  EXPECT_EQ(table.compare(2, 3, 0), 0);
  table.fields[0].type = "integer";
  table.records[0].values["n"] = int64_t(9223372036854775807LL);
  table.records[1].values["n"] = int64_t(9223372036854775806LL);
  EXPECT_GT(table.compare(0, 1, 0), 0);
  table.records[0].values["n"] = int64_t(-9223372036854775807LL - 1);
  EXPECT_LT(table.compare(0, 1, 0), 0);
}

TEST(ProjectFiles, VscodeUrlsEncodePathDataAndRejectAmbiguousLocations)
{
  EXPECT_EQ(platform::vscode_file_url("/tmp/hello world#?.md"), "vscode://file/tmp/hello%20world%23%3F.md");
  EXPECT_EQ(platform::vscode_file_url("C:\\Research\\温度.py"), "vscode://file/C:/Research/%E6%B8%A9%E5%BA%A6.py");
  EXPECT_EQ(platform::vscode_file_url("/tmp/%file"), "vscode://file/tmp/%25file");
  EXPECT_TRUE(platform::vscode_file_url("relative/file.py").empty());
  EXPECT_TRUE(platform::vscode_file_url("/tmp/ambiguous:12").empty());
  EXPECT_TRUE(platform::vscode_file_url("\\\\server\\share\\file.py").empty());
  EXPECT_TRUE(platform::vscode_file_url(std::string("/tmp/a\0b", 8)).empty());
  std::string error;
  EXPECT_FALSE(platform::open_with_system("", &error));
  EXPECT_FALSE(error.empty());
}

TEST(ProjectTable, ValuesFollowFieldIdsAndDistinguishUnsetFromNull)
{
  ProjectTable table = ProjectTable::from_json({
      {"id", table_id}, {"name", "Cases"},
      {"fields", Json::array({{{"id", "a"}, {"name", "Renamed"}, {"type", "integer"}, {"unit", nullptr}},
                              {{"id", "b"}, {"name", "Optional"}, {"type", "json"}, {"unit", nullptr}}})},
      {"records", Json::array({{{"id", record_id}, {"values", {{"a", INT64_MAX}, {"b", nullptr}}}},
                               {{"id", "empty"}, {"values", Json::object()}}})}});
  EXPECT_EQ(table.text(0, 0), "9223372036854775807");
  EXPECT_EQ(table.text(0, 1), "null");
  EXPECT_EQ(table.cell(1, 1), nullptr);
  EXPECT_EQ(table.cell(-1, 0), nullptr);
  EXPECT_EQ(table.cell(0, 2), nullptr);
  std::swap(table.fields[0], table.fields[1]);
  EXPECT_EQ(table.text(0, 1), "9223372036854775807");
}

TEST(ProjectReview, StableIdentityDistinguishesUnsetNullInt64AndRejectsWrongBase)
{
  Json table = {{"id", table_id}, {"name", "Before"},
      {"fields", Json::array({{{"id", field_id}, {"name", "Value"}, {"type", "integer"}}})},
      {"records", Json::array({{{"id", record_id}, {"values", Json::object()}}})}};
  const std::vector<ProjectTable> before = {ProjectTable::from_json(table)};
  table["name"] = "Renamed";
  table["records"][0]["values"][field_id] = nullptr;
  Json result = {{"persisted", false}, {"base_revision", 3}, {"proposed_revision", 4},
      {"commands", Json::array({{{"op", "set_cell"}}})},
      {"snapshot", {{"project", {{"id", "project"}, {"revision", 4}}}, {"tables", Json::array({table})}}}};
  auto review = ProjectReview::from_preview("project", 3, before, result);
  ASSERT_EQ(review.differences.size(), 2u);
  EXPECT_EQ(review.differences[0].kind, "table");
  const auto &cell = review.differences[1];
  EXPECT_FALSE(cell.before);
  ASSERT_TRUE(cell.after);
  EXPECT_TRUE(cell.after->at("value").is_null());
  EXPECT_EQ(cell.field_id, field_id);
  result["snapshot"]["tables"][0]["records"][0]["values"][field_id] = INT64_MAX;
  review = ProjectReview::from_preview("project", 3, {ProjectTable::from_json(table)}, result);
  ASSERT_EQ(review.differences.size(), 1u);
  EXPECT_EQ(review.differences[0].after->at("value").get<int64_t>(), INT64_MAX);
  EXPECT_TRUE(review.differences[0].before->at("value").is_null());
  EXPECT_THROW(ProjectReview::from_preview("different", 3, before, result), std::exception);
  EXPECT_THROW(ProjectReview::from_preview("project", 2, before, result), std::exception);
  result["persisted"] = true;
  EXPECT_THROW(ProjectReview::from_preview("project", 3, before, result), std::exception);
}

TEST(ProjectLayout, EditorAvailableWithoutBridgeAndPersistsLocation)
{
  wmtest::AppFixture f("zh_CN");
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().load_state({{"directory", "/tmp/项目"}, {"name", "扫描"}}));
  f.screen.set_maximized(&area);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/project_location/directory"), nullptr);
  EXPECT_EQ(area.editor().save_state()["directory"], "/tmp/项目");
  EXPECT_FALSE(f.shell->store().project().ready());
  EXPECT_FALSE(f.shell->store().project().create("/tmp/must-not-create", "No bridge"));
}

TEST(ProjectLayout, FileMenuOpensOneProjectTabAndKeepsViewer)
{
  wmtest::AppFixture f;
  f.drv->frame();
  const auto menu = f.screen.ui()->find("file")->menu;
  const auto it = std::find_if(menu.begin(), menu.end(), [&](const auto &entry) {
    return entry.text == f.shell->store().tr("editor.project.title");
  });
  ASSERT_NE(it, menu.end());
  it->action();
  f.drv->frame();
  auto &area = f.area("a2");
  ASSERT_EQ(area.tab_count(), 2);
  EXPECT_EQ(area.editor().type().id, kEditorProject);
  EXPECT_EQ(area.tab(0).type().id, kEditorViewer);
  it->action();
  f.drv->frame();
  EXPECT_EQ(area.tab_count(), 2);
}

TEST(ProjectLayout, OpenResultCreatesAViewerTabWhenTheLayoutHasNone)
{
  wmtest::AppFixture f;
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&f.area("a1"));
  OpenResultRequest request;
  request.local_paths = {std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"};
  f.shell->store().request_open_result(request);
  f.drv->frame();
  f.screen.run_deferred();
  f.drv->frame();
  ASSERT_TRUE(f.shell->store().viewer().payload());
  EXPECT_FALSE(f.shell->store().has_open_result());
  auto *shown = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(shown, nullptr);
  EXPECT_EQ(shown->editor().type().id, kEditorViewer);
  EXPECT_EQ(shown->tab_count(), 3);  // Workspace and Jobs keep their tabs
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorProject);
}

class ProjectPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"project-app"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;

  ProjectState &state() { return f.shell->store().project(); }
  virtual void configure_bridge(bridge::ClientOptions &, const std::string &) {}

  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) {
      python = env;
    }
    if (python.empty()) {
      python = bridge::find_executable("python3").value_or("");
    }
    if (python.empty()) {
      GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run the project bridge integration";
    }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = "fixture-model";
    options.env["STK_PROJECTS_DIR"] = dir.str() + "/projects";  // The example project never lands in $HOME.
    options.executor = loop.executor();
    options.strict = options.validate = true;
    configure_bridge(options, python);
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    state().sync();
    ASSERT_TRUE(loop.pump_until([&] { return state().ready(); }, 60)) << client->bridge_log().text();
  }

  void TearDown() override
  {
    state().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) {
      client->close();
    }
    loop.run_ready();
  }

  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !state().busy() && !state().discussion().busy(); }, 30)) << client->bridge_log().text();
  }

  void populated()
  {
    ASSERT_TRUE(state().create(dir.str() + "/project", "扫描"));
    settled();
    ASSERT_TRUE(state().loaded()) << state().error();
    ASSERT_TRUE(state().apply(sample_commands()));
    settled();
    ASSERT_EQ(state().tables().size(), 1u);
    ASSERT_EQ(state().project()->revision, 1);
  }

  void saved_request(const std::string &id)
  {
    auto &discussion = state().discussion();
    if (discussion.context().empty()) {
      ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Request scope")); settled();
      ASSERT_TRUE(discussion.add_message("Explain these saved values; do not execute code.")); settled();
    }
    std::optional<bridge::Result<Json>> result;
    client->call("project.requests.create", {{"handle", state().project()->handle}, {"request_id", id},
        {"message_id", discussion.message().at("id")},
        {"configuration", {{"adapter", "test-controlled"}, {"model", "fixture-v1"}}}})
        .then([&](auto r) { result = r; });
    ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); }));
    ASSERT_TRUE(result->ok()) << result->error().describe();
    ASSERT_EQ(result->value().at("request").at("status"), Json("pending"));
  }

  /** Ask the built-in Token Plan explicitly instead of "Automatic", the default since S1d (with private data and no
   * model on this computer, Automatic has no candidate, so these tests choose the Token Plan as they did before). */
  void choose_token_plan(const std::string &area = "a2")
  {
    const auto key = area + "/main/ai_endpoint";
    ASSERT_TRUE(loop.pump_until([&] {
      f.screen.run_deferred(); f.drv->frame();
      const auto *dropdown = f.screen.ui()->find(key);
      return dropdown && dropdown->items.size() > 1;
    }, 30)) << client->bridge_log().text();
    const auto *dropdown = f.screen.ui()->find(key);
    const auto found = std::find_if(dropdown->items.begin(), dropdown->items.end(),
                                    [](const auto &item) { return item.find("Alibaba Token Plan") != std::string::npos; });
    ASSERT_NE(found, dropdown->items.end());
    dropdown->index.assign(int(found - dropdown->items.begin()));
    f.drv->frame();
  }

  void ai_frame()
  {
    // Provider/history reads are queued by drawing; local exchange reads remain
    // independent of the legacy discussion busy flag.
    for (int i = 0; i < 4; ++i) {
      f.drv->frame();
      ASSERT_TRUE(loop.pump_until([&] {
        state().discussion().pump(std::chrono::duration<double>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
        return !state().busy() && !state().discussion().busy() && !state().discussion().exchange_busy();
      }, 30)) << client->bridge_log().text();
    }
    f.drv->frame();
  }
};

class ProjectStream : public ProjectPython {
 protected:
  virtual bool legacy() const { return false; }
  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    options.command = {python, std::string(STK_REPO_ROOT) + "/desktop/tests/bridge/stream_bridge.py",
        dir.str(), legacy() ? "legacy" : "progress", "--stdio", "--state-dir", options.state_dir,
        "--cache-dir", options.cache_dir, "--strict"};
  }

  void prepare_stream()
  {
    populated();
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
    f.screen.set_maximized(&area); ai_frame();
    auto &discussion = state().discussion();
    // The Token Plan endpoint is external: only data labelled public may be sent to it.
    std::optional<bridge::Result<Json>> labelled;
    client->call("project.labels.set", {{"handle", state().project()->handle}, {"label", "public"},
        {"items", Json::array({{{"kind", "table"}, {"id", table_id}}})}}).then([&](auto value) { labelled = value; });
    ASSERT_TRUE(loop.pump_until([&] { return labelled.has_value(); }));
    ASSERT_TRUE(labelled->ok()) << labelled->error().describe();
    ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Streaming scope")); settled();
    ASSERT_TRUE(discussion.prepare_question(discussion.context().at("id"), "Explain the temperature", "fixture-model"));
    settled(); ai_frame();
    ASSERT_EQ(discussion.exchange_request().at("status"), "pending");
  }

  void start_stream()
  {
    auto &discussion = state().discussion();
    ASSERT_TRUE(discussion.start_request(discussion.exchange_request().at("id"))); settled();
    ASSERT_TRUE(loop.pump_until([&] { return std::filesystem::exists(dir.str() + "/first"); }, 30));
    read_exchange();
  }

  void read_exchange()
  {
    ASSERT_TRUE(state().discussion().refresh_exchange());
    ai_frame();
  }

  void advance(int step) { std::ofstream(dir.str() + "/advance") << step; }

  void completion()
  {
    advance(2);
    auto &discussion = state().discussion();
    ASSERT_TRUE(loop.pump_until([&] {
      discussion.pump(std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count());
      return discussion.exchange_request().value("status", "") == "completed";
    }, 30)) << discussion.exchange_error() << client->bridge_log().text();
    ai_frame();
  }

  std::string transcript()
  {
    const auto *widget = f.screen.ui()->find("a2/main/ai_transcript");
    if (!widget || !widget->log) { return {}; }
    std::string text;
    for (size_t i = 0; i < widget->log->line_count(); ++i) { text += std::string(widget->log->line(i)) + "\n"; }
    return text;
  }
};

TEST_F(ProjectStream, TemporaryReplyIsIncrementalAndOnlyCompletedReplyIsSaved)
{
  prepare_stream(); start_stream();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.progress_supported());
  ASSERT_FALSE(discussion.exchange_progress().empty()) << discussion.exchange_error();
  EXPECT_EQ(discussion.exchange_progress().at("text"), "温度 ");
  EXPECT_EQ(discussion.exchange_progress().at("text_bytes"), 7);
  EXPECT_TRUE(discussion.exchange_reply().empty());
  EXPECT_NE(transcript().find("temporary reply (not saved yet)"), std::string::npos);
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  advance(1);
  ASSERT_TRUE(loop.pump_until([&] { return std::filesystem::exists(dir.str() + "/second"); }));
  read_exchange();
  EXPECT_EQ(discussion.exchange_progress().at("text"), "温度 300");
  const auto second = discussion.exchange_progress();
  read_exchange();
  EXPECT_EQ(discussion.exchange_progress(), second); // A snapshot is replaced, never appended twice.
  EXPECT_NE(transcript().find("温度 300"), std::string::npos);
  completion();
  EXPECT_TRUE(discussion.exchange_progress().empty());
  EXPECT_EQ(discussion.exchange_reply().at("text"), "温度 300 K。");
  EXPECT_EQ(transcript().find("temporary reply"), std::string::npos);
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 2u);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectStream, CancellationHidesTemporaryReplyButCanObserveValidLateCompletion)
{
  prepare_stream(); start_stream();
  auto &discussion = state().discussion();
  ASSERT_FALSE(discussion.exchange_progress().empty());
  ASSERT_TRUE(discussion.cancel_request(discussion.exchange_request().at("id")));
  EXPECT_TRUE(discussion.exchange_progress().empty());
  settled(); ai_frame();
  EXPECT_TRUE(discussion.exchange_progress().empty());
  EXPECT_TRUE(discussion.exchange_reply().empty());
  EXPECT_EQ(discussion.exchange_request().at("cancel_requested"), true);
  EXPECT_EQ(transcript().find("温度 "), std::string::npos);
  completion();
  EXPECT_EQ(discussion.exchange_reply().at("text"), "温度 300 K。");
  EXPECT_TRUE(discussion.exchange_progress().empty());
}

TEST_F(ProjectStream, SwitchingProjectsClearsPartialReplyAndReopeningReadsItsOriginalOwner)
{
  prepare_stream(); start_stream();
  auto &discussion = state().discussion();
  const auto id = discussion.exchange_request().at("id").get<std::string>();
  ASSERT_FALSE(discussion.exchange_progress().empty());
  ASSERT_TRUE(discussion.refresh_exchange()); // Leave this reply queued while the handle changes.
  ASSERT_TRUE(state().create(dir.str() + "/second-project", "Other project")); settled(); ai_frame();
  EXPECT_TRUE(discussion.exchange_request().empty());
  EXPECT_TRUE(discussion.exchange_progress().empty());
  EXPECT_EQ(transcript().find("温度 "), std::string::npos);
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled(); ai_frame();
  ASSERT_TRUE(discussion.load_exchange(id)); ai_frame();
  ASSERT_FALSE(discussion.exchange_progress().empty()) << discussion.exchange_error();
  EXPECT_EQ(discussion.exchange_progress().at("text"), "温度 ");
  completion();
  EXPECT_EQ(discussion.exchange_reply().at("text"), "温度 300 K。");
}

class ProjectLegacyStream : public ProjectStream {
 protected:
  bool legacy() const override { return true; }
};

TEST_F(ProjectLegacyStream, OlderBridgeFallsBackToSavedStatusAndCompletion)
{
  prepare_stream(); start_stream();
  auto &discussion = state().discussion();
  EXPECT_FALSE(discussion.progress_supported());
  EXPECT_TRUE(discussion.exchange_progress().empty());
  EXPECT_EQ(discussion.exchange_request().at("status"), "running");
  completion();
  EXPECT_EQ(discussion.exchange_reply().at("text"), "温度 300 K。");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

class ProjectProposal : public ProjectPython {
 protected:
  void prepare_suggestion()
  {
    populated();
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
    f.screen.set_maximized(&area); ai_frame();
    auto &discussion = state().discussion();
    ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Parameter scope")); settled();
    ASSERT_TRUE(discussion.edit_proposals_supported());
    f.drv->frame();
    ASSERT_NO_FATAL_FAILURE(choose_token_plan());
    const auto handle = state().project()->handle;
    f.screen.ui()->find("a2/main/ai_intent/" + handle)->index.assign(1);
    f.screen.ui()->find("a2/main/ai_question/" + handle)->string.assign("Raise the temperature to 350 K.");
    f.drv->frame();
    click("ai_prepare");
    ASSERT_EQ(discussion.exchange_request().at("prompt_version"), "stk.parameter-edits/1");
    ASSERT_EQ(discussion.exchange_request().at("status"), "pending");
  }

  void completed_suggestion(const std::string &replacement = "")
  {
    prepare_suggestion();
    auto &discussion = state().discussion();
    const auto request = discussion.exchange_request();
    const Json response = {{"format", "stk.parameter-edits/1"}, {"context_id", request.at("context_id")},
        {"base_revision", 1}, {"summary", "Raise the selected temperature to 350 K."},
        {"edits", Json::array({{{"record_id", record_id}, {"field_id", field_id}, {"value", 350}}})}};
    auto &scripts = f.shell->store().scripts();
    ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
    ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
        "s=ProjectStore(" + Json(dir.str() + "/project").dump() + ")\nowner=str(uuid4())\n"
        "s.requests._claim(" + request.at("id").dump() + ", executor_id=owner)\n"
        "s.requests._complete(" + request.at("id").dump() + ", executor_id=owner, text=" +
            Json(replacement.empty() ? response.dump() : replacement).dump() + ")"));
    ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
    ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
    ASSERT_TRUE(discussion.refresh_exchange()); ai_frame();
    ASSERT_EQ(discussion.exchange_request().at("status"), "completed");
    ASSERT_TRUE(discussion.exchange_edit_proposal().at("draft").is_null());
  }

  void click(const std::string &key, bool wait = true)
  {
    const auto *widget = f.screen.ui()->find("a2/main/" + key);
    ASSERT_NE(widget, nullptr); ASSERT_TRUE(widget->enabled);
    const auto [x, y] = f.widget_center("a2/main/" + key);
    f.drv->click(x, y);
    if (wait) { settled(); f.screen.run_deferred(); ai_frame(); }
  }
};

TEST_F(ProjectProposal, SweepSuggestionBecomesADraftOfNewRowsThatAppliesLikeAManualSweep)
{
  // The third purpose asks for a sweep shape; STK expands it into new rows only when saved as a draft (P2 L1).
  populated();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area); ai_frame();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Sweep scope")); settled();
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(choose_token_plan());
  const auto handle = state().project()->handle;
  f.screen.ui()->find("a2/main/ai_intent/" + handle)->index.assign(2);
  f.screen.ui()->find("a2/main/ai_question/" + handle)->string.assign("Try 310, 320 and 330 K.");
  f.drv->frame();
  click("ai_prepare");
  const auto request = discussion.exchange_request();
  ASSERT_EQ(request.at("prompt_version"), "stk.parameter-sweep/1");
  const Json response = {{"format", "stk.parameter-sweep/1"}, {"context_id", request.at("context_id")}, {"base_revision", 1},
      {"summary", "Three temperatures around the current case."}, {"base_record_id", record_id},
      {"axes", Json::array({{{"field_id", field_id}, {"values", {310, 320, 330}}}})}, {"mode", "product"}};
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s=ProjectStore(" + Json(dir.str() + "/project").dump() + ")\nowner=str(uuid4())\n"
      "s.requests._claim(" + request.at("id").dump() + ", executor_id=owner)\n"
      "s.requests._complete(" + request.at("id").dump() + ", executor_id=owner, text=" + Json(response.dump()).dump() + ")"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  ASSERT_TRUE(discussion.refresh_exchange()); ai_frame();
  const auto *log = f.screen.ui()->find("a2/main/ai_transcript")->log;
  std::string shown;
  for (size_t i = 0; i < log->line_count(); ++i) { shown += std::string(log->line(i)) + "\n"; }
  EXPECT_NE(shown.find("AI · Sweep proposal"), std::string::npos) << shown;
  EXPECT_NE(shown.find("Based on selected row 1, every combination of the values:"), std::string::npos) << shown;
  EXPECT_NE(shown.find("· Temperature: 310, 320, 330"), std::string::npos) << shown;
  click("ai_save_edits");
  const auto draft = discussion.exchange_edit_proposal().at("draft");
  ASSERT_EQ(draft.at("status"), "pending");
  size_t added = 0;
  for (const auto &command : draft.at("commands")) { added += command.at("op") == "add_record"; }
  EXPECT_EQ(added, 3u);
  EXPECT_EQ(state().table()->records.size(), 1u);  // nothing added before applying
  click("ai_open_edits");
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().apply_review()); settled();
  ASSERT_EQ(state().table()->records.size(), 4u);
  EXPECT_EQ(state().table()->text(1, 0), "310");
  EXPECT_EQ(state().table()->text(3, 0), "330");
  // L2: the applied sweep's rows open in a workflow over this table, only they checked; nothing runs by itself.
  std::optional<bridge::Result<Json>> created;
  client->call("project.workflows.create", {{"handle", state().project()->handle}, {"workflow_id", "44444444-4444-4444-8444-444444444444"},
      {"name", "Scan"}, {"expected_revision", state().project()->revision}, {"document", {{"format", "stk.workflow/1"}, {"ui", Json::object()},
       {"steps", {{{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
                  {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
                   {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", field_id}}}}}}}}}}})
      .then([&](auto result) { created = result; });
  ASSERT_TRUE(loop.pump_until([&] { return created.has_value(); }));
  ASSERT_TRUE(created->ok()) << created->error().describe();
  state().refresh(); settled();
  f.screen.set_maximized(&area); ai_frame();
  click("ai_run_rows");
  auto *workflow = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(workflow, nullptr);
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    const auto *start = f.screen.ui()->find("workflow_run_start");
    return workflow->editor().type().id == kEditorWorkflow && start && start->text == "Run the 3 selected rows";
  }, 30));
  EXPECT_FALSE(f.screen.ui()->find("workflow_run_row/1")->boolean.value());  // the base row stays out
  for (const auto *row : {"workflow_run_row/2", "workflow_run_row/3", "workflow_run_row/4"}) {
    EXPECT_TRUE(f.screen.ui()->find(row)->boolean.value()) << row;
  }
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectProposal, PreparedPurposeIsFrozenAndTextModeKeepsItsDefaultContract)
{
  prepare_suggestion();
  auto &discussion = state().discussion();
  const auto request = discussion.exchange_request();
  const auto question = discussion.exchange_question();
  f.screen.ui()->find("a2/main/ai_intent/" + state().project()->handle)->index.assign(0);
  f.drv->frame();
  EXPECT_EQ(discussion.exchange_request(), request);
  click("ai_prepare");
  EXPECT_EQ(discussion.exchange_request().at("prompt_version"), "stk.text/1");
  EXPECT_NE(discussion.exchange_request().at("id"), request.at("id"));
  EXPECT_EQ(discussion.exchange_question().at("id"), question.at("id"));
  EXPECT_EQ(discussion.exchange_request().at("status"), "pending");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectProposal, SuggestionIsSavedThenOpenedAndAppliedThroughItsDurableReceipt)
{
  completed_suggestion();
  auto &discussion = state().discussion();
  const auto request_id = discussion.exchange_request().at("id").get<std::string>();
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_open_edits")->enabled);
  const auto *log = f.screen.ui()->find("a2/main/ai_transcript")->log;
  std::string shown;
  for (size_t i = 0; i < log->line_count(); ++i) { shown += std::string(log->line(i)); }
  EXPECT_NE(shown.find("Temperature: 350"), std::string::npos);
  EXPECT_EQ(shown.find("stk.parameter-edits/1"), std::string::npos);
  click("ai_save_edits");
  const auto draft = discussion.exchange_edit_proposal().at("draft");
  EXPECT_EQ(draft.at("status"), "pending");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_TRUE(state().saved_review().empty());
  click("ai_open_edits");
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().can_apply_review());
  ASSERT_NE(f.screen.maximized(), nullptr);
  EXPECT_EQ(dynamic_cast<EditorArea *>(f.screen.maximized())->editor().type().id, kEditorProject);
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().can_apply_review());
  ASSERT_TRUE(state().apply_review()); settled();
  EXPECT_EQ(state().saved_review().at("id"), draft.at("id"));
  EXPECT_EQ(state().saved_review().at("status"), "applied");
  EXPECT_EQ(state().table()->text(0, 0), "350");
  f.screen.set_maximized(&f.area("a2")); ai_frame();
  EXPECT_EQ(discussion.exchange_edit_proposal().at("draft").at("status"), "applied");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_open_edits")->enabled);
  ASSERT_TRUE(state().undo()); settled();
  state().discard_review();
  f.screen.set_maximized(&f.area("a2")); ai_frame();
  ASSERT_TRUE(discussion.load_exchange(request_id)); ai_frame();
  EXPECT_EQ(discussion.exchange_edit_proposal().at("draft").at("id"), draft.at("id"));
  EXPECT_EQ(discussion.exchange_edit_proposal().at("draft").at("status"), "applied");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_save_edits")->enabled);
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_open_edits")->enabled);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectProposal, ExistingAndInterveningReviewAreNeverReplacedByAIHandoff)
{
  completed_suggestion(); click("ai_save_edits");
  const auto original = set_cell(999).dump();
  state().set_review_source(original);
  click("ai_open_edits");
  EXPECT_EQ(state().review_source(), original);
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(f.screen.maximized(), &f.area("a2"));
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorAI);
  state().discard_review(); ai_frame();
  click("ai_open_edits", false);
  state().set_review_source("An intervening unsaved review");
  state().discard_review();
  settled(); f.screen.run_deferred(); ai_frame();
  EXPECT_EQ(state().review_source(), "[]");
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorAI);
  EXPECT_EQ(state().project()->revision, 1);
}

TEST_F(ProjectProposal, ClosedOriginEditorFencesQueuedProposalNavigation)
{
  completed_suggestion(); click("ai_save_edits");
  click("ai_open_edits", false);
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorViewer));
  settled(); f.screen.run_deferred(); f.drv->frame();
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(state().review_source(), "[]");
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
  EXPECT_EQ(f.screen.maximized(), &f.area("a2"));
}

TEST_F(ProjectProposal, DiscardedSuggestionUpdatesWithoutManuallyRefreshingTheExchange)
{
  completed_suggestion(); click("ai_save_edits"); click("ai_open_edits");
  const auto id = state().saved_review().at("id").get<std::string>();
  ASSERT_TRUE(state().discard_saved_draft(id)); settled();
  f.screen.set_maximized(&f.area("a2")); ai_frame();
  EXPECT_EQ(state().discussion().exchange_edit_proposal().at("draft").at("status"), "discarded");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_save_edits")->enabled);
  EXPECT_FALSE(f.screen.ui()->find("a2/main/ai_open_edits")->enabled);
  EXPECT_EQ(state().project()->revision, 1);
}

TEST_F(ProjectProposal, DeeplyNestedInvalidSuggestionStaysPlainTextAndCannotSaveADraft)
{
  const auto text = std::string("{\"format\":\"stk.parameter-edits/1\",\"summary\":\"Malformed suggestion\",\"edits\":[{") +
      "\"record_id\":\"" + record_id + "\",\"field_id\":\"" + field_id + "\",\"value\":" +
      std::string(24000, '[') + "0" + std::string(24000, ']') + "}]}";
  completed_suggestion(text);
  auto &discussion = state().discussion();
  EXPECT_EQ(discussion.exchange_reply().at("text"), text);
  ASSERT_NE(f.screen.ui()->find("a2/main/ai_transcript"), nullptr);
  click("ai_save_edits");
  EXPECT_FALSE(discussion.error().empty());
  EXPECT_TRUE(discussion.exchange_edit_proposal().at("draft").is_null());
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(state().project()->revision, 1);
}

TEST_F(ProjectProposal, ConversionStaysInOriginalProjectAndIsRecoveredOnlyByReading)
{
  completed_suggestion();
  auto &discussion = state().discussion();
  const auto request_id = discussion.exchange_request().at("id").get<std::string>();
  ASSERT_TRUE(discussion.propose_exchange_edits());
  ASSERT_TRUE(state().create(dir.str() + "/other-project", "Other project")); settled(); ai_frame();
  EXPECT_TRUE(discussion.exchange_edit_proposal().empty());
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(state().project()->revision, 0);
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled(); ai_frame();
  ASSERT_TRUE(discussion.load_exchange(request_id)); ai_frame();
  ASSERT_FALSE(discussion.exchange_edit_proposal().at("draft").is_null());
  EXPECT_EQ(discussion.exchange_edit_proposal().at("draft").at("status"), "pending");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_TRUE(state().saved_review().empty());
}

class ProjectScope : public ProjectPython {
 protected:
  const std::string second_row = "44444444-4444-4444-8444-444444444444";
  const std::string second_field = "55555555-5555-4555-8555-555555555555";
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  void open_picker()
  {
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
    f.screen.set_maximized(&area); ai_frame();
    ASSERT_NE(widget("ai_choose_scope"), nullptr);
    const auto [x, y] = f.widget_center("a2/main/ai_choose_scope");
    f.drv->click(x, y); ai_frame();
    ASSERT_NE(widget("ai_scope_capture"), nullptr);
  }
  void more_cells()
  {
    ASSERT_TRUE(state().apply(Json::array({
      {{"op", "add_record"}, {"table_id", table_id}, {"id", second_row}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", second_field}, {"name", "Note"}, {"type", "text"}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second_row}, {"field_id", field_id}, {"value", 325}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second_row}, {"field_id", second_field}, {"value", "Do not include"}}
    }))); settled();
  }
};

TEST_F(ProjectScope, CapturesCheckedRowsAndFieldsWithoutChangingSelectionOrSavedQuestion)
{
  populated(); more_cells();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Original")); settled();
  const auto original = discussion.context();
  ASSERT_TRUE(discussion.load_provider()); settled();
  ASSERT_TRUE(discussion.prepare_question(original.at("id"), "Original question", "fixture-model")); ai_frame();
  const auto question = discussion.exchange_question(), request = discussion.exchange_request();
  const auto shared_row = state().record_id();
  open_picker();
  widget("ai_scope_all")->on_click(); f.drv->frame();
  widget("ai_scope_kind")->index.assign(1); f.drv->frame();
  widget("ai_scope_field/" + second_field)->boolean.assign(false); f.drv->frame();
  ASSERT_TRUE(widget("ai_scope_capture")->enabled);
  const auto *preview = widget("ai_scope_cells"); ASSERT_NE(preview, nullptr);
  ASSERT_EQ(preview->table->rows, 2);
  EXPECT_EQ(preview->table->cell(0, 2), "300"); EXPECT_EQ(preview->table->cell(1, 2), "325");
  const auto [x, y] = f.widget_center("a2/main/ai_scope_capture"); f.drv->click(x, y); ai_frame();
  ASSERT_NE(discussion.context().at("id"), original.at("id"));
  EXPECT_EQ(discussion.context().at("selection").at("record_ids"), Json::array({record_id, second_row}));
  EXPECT_EQ(discussion.context().at("selection").at("field_ids"), Json::array({field_id}));
  EXPECT_EQ(discussion.context().at("source_revision"), 2);
  EXPECT_EQ(discussion.exchange_request(), request); EXPECT_EQ(discussion.exchange_question(), question);
  EXPECT_EQ(discussion.exchange_context(), original);
  EXPECT_EQ(state().record_id(), shared_row); EXPECT_EQ(state().table_id(), table_id);
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectScope, StaleRevisionKeepsOldPreviewAndRequiresExplicitEmptyReload)
{
  populated(); open_picker();
  const auto old_capture = widget("ai_scope_capture")->on_click;
  const auto old_checkbox = widget("ai_scope_row/" + record_id)->boolean;
  ASSERT_TRUE(state().apply(set_cell(321))); settled(); ai_frame();
  ASSERT_NE(widget("ai_scope_reload"), nullptr);
  EXPECT_FALSE(widget("ai_scope_capture")->enabled);
  EXPECT_EQ(widget("ai_scope_cells")->table->cell(0, 2), "300");
  old_capture(); old_checkbox.assign(false);
  EXPECT_FALSE(state().discussion().busy()); EXPECT_TRUE(state().discussion().context().empty());
  widget("ai_scope_reload")->on_click(); f.drv->frame();
  EXPECT_FALSE(widget("ai_scope_capture")->enabled); EXPECT_EQ(widget("ai_scope_cells"), nullptr);
  widget("ai_scope_row/" + record_id)->boolean.assign(true); f.drv->frame();
  widget("ai_scope_kind")->index.assign(1); f.drv->frame();
  widget("ai_scope_field/" + field_id)->boolean.assign(true); f.drv->frame();
  EXPECT_EQ(widget("ai_scope_cells")->table->cell(0, 2), "321");
  old_capture(); EXPECT_TRUE(state().discussion().context().empty());
  widget("ai_scope_capture")->on_click(); ai_frame();
  EXPECT_EQ(state().discussion().context().at("source_revision"), 2);
}

TEST_F(ProjectScope, OldWidgetsCannotCaptureAfterScopeChangeProjectSwitchOrEditorClose)
{
  populated(); more_cells(); open_picker();
  const auto old_capture = widget("ai_scope_capture")->on_click;
  widget("ai_scope_row/" + second_row)->boolean.assign(true); f.drv->frame();
  old_capture(); EXPECT_TRUE(state().discussion().context().empty());
  const auto previous = widget("ai_scope_capture")->on_click;
  ASSERT_TRUE(state().create(dir.str() + "/other", "Other")); settled();
  ASSERT_TRUE(state().apply(sample_commands())); settled(); ai_frame();
  previous(); EXPECT_TRUE(state().discussion().context().empty());
  EXPECT_EQ(widget("ai_scope_capture"), nullptr);
  widget("ai_choose_scope")->on_click(); f.drv->frame();
  const auto closed = widget("ai_scope_capture")->on_click;
  const auto closed_tabs = widget("ai_scope_kind")->index;
  ASSERT_TRUE(f.area("a2").set_tab_type(f.area("a2").active_tab(), kEditorProject)); f.drv->frame();
  closed(); EXPECT_EQ(closed_tabs.value(), 0); closed_tabs.assign(1);
  EXPECT_TRUE(state().discussion().context().empty());
  EXPECT_FALSE(state().discussion().busy());
}

TEST_F(ProjectScope, CaptureFailureRetainsScopeUntilExplicitReload)
{
  populated(); open_picker();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nimport json\nProjectStore(" +
      Json(dir.str() + "/project").dump() + ").apply(json.loads(" + Json(set_cell(700).dump()).dump() + "), expected_revision=1)"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  EXPECT_EQ(state().project()->revision, 1); // No event from the independent writer.
  widget("ai_scope_capture")->on_click(); ai_frame();
  ASSERT_NE(widget("ai_scope_capture"), nullptr);
  EXPECT_FALSE(widget("ai_scope_capture")->enabled);
  ASSERT_FALSE(state().discussion().error().empty());
  EXPECT_TRUE(state().discussion().context().empty());
  EXPECT_TRUE(widget("ai_scope_row/" + record_id)->boolean.value());
  EXPECT_EQ(widget("ai_scope_cells")->table->cell(0, 2), "300");
  EXPECT_EQ(state().project()->revision, 2);
  ASSERT_NE(widget("ai_scope_reload"), nullptr);
}

TEST_F(ProjectScope, ChoosingNewScopeBlocksPrepareAgainstPreviouslySavedData)
{
  populated(); auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Original")); settled();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area); ai_frame();
  ASSERT_NO_FATAL_FAILURE(choose_token_plan());
  widget("ai_question/" + state().project()->handle)->string.assign("Question to prepare"); f.drv->frame();
  ASSERT_TRUE(widget("ai_prepare")->enabled);
  const auto old_prepare = widget("ai_prepare")->on_click;
  const auto old_choose = widget("ai_choose_scope")->on_click;
  old_choose(); f.drv->frame();
  widget("ai_scope_clear")->on_click(); f.drv->frame();
  EXPECT_FALSE(widget("ai_prepare")->enabled);
  old_prepare(); EXPECT_TRUE(discussion.exchange_request().empty());
  old_choose(); f.drv->frame(); // Must not reset the user's cleared scope.
  EXPECT_FALSE(widget("ai_scope_row/" + record_id)->boolean.value());
  widget("ai_scope_cancel")->on_click(); f.drv->frame();
  EXPECT_TRUE(widget("ai_prepare")->enabled);
  widget("ai_prepare")->on_click(); ai_frame();
  EXPECT_EQ(discussion.exchange_context().at("title"), "Original");
}

TEST_F(ProjectScope, SwitchingTablesClearsScopeWithoutRetargetingSharedSelection)
{
  populated();
  const std::string other_table = "77777777-7777-4777-8777-777777777777";
  ASSERT_TRUE(state().apply(Json::array({
    {{"op", "create_table"}, {"id", other_table}, {"name", "Other table"}},
    {{"op", "add_record"}, {"table_id", other_table}, {"id", second_row}},
    {{"op", "add_field"}, {"table_id", other_table}, {"id", second_field}, {"name", "Flag"}, {"type", "boolean"}}
  }))); settled();
  state().select_table(table_id); open_picker();
  const auto old_capture = widget("ai_scope_capture")->on_click;
  widget("ai_scope_table")->index.assign(1); f.drv->frame();
  EXPECT_FALSE(widget("ai_scope_capture")->enabled);
  widget("ai_scope_row/" + second_row)->boolean.assign(true); f.drv->frame();
  widget("ai_scope_kind")->index.assign(1); f.drv->frame();
  widget("ai_scope_field/" + second_field)->boolean.assign(true); f.drv->frame();
  old_capture(); EXPECT_TRUE(state().discussion().context().empty());
  widget("ai_scope_capture")->on_click(); ai_frame();
  EXPECT_EQ(state().discussion().context().at("selection").at("table_id"), other_table);
  EXPECT_EQ(state().table_id(), table_id); EXPECT_EQ(state().record_id(), record_id);
}

TEST_F(ProjectScope, PaginatedSelectionRejectsOversizeProductThenAllowsExplicitSubset)
{
  populated();
  Json commands = Json::array();
  for (int i = 1; i < 17; ++i) {
    commands.push_back({{"op", "add_record"}, {"table_id", table_id},
        {"id", std::to_string(40000000 + i) + "-4444-4444-8444-444444444444"}});
  }
  for (int i = 1; i < 60; ++i) {
    commands.push_back({{"op", "add_field"}, {"table_id", table_id}, {"name", "Parameter " + std::to_string(i)},
        {"type", "number"}, {"id", std::to_string(50000000 + i) + "-5555-4555-8555-555555555555"}});
  }
  ASSERT_TRUE(state().apply(commands)); settled(); open_picker();
  widget("ai_scope_next")->on_click(); f.drv->frame();
  ASSERT_NE(widget("ai_scope_row/40000008-4444-4444-8444-444444444444"), nullptr);
  EXPECT_EQ(widget("ai_scope_row/" + record_id), nullptr);
  widget("ai_scope_all")->on_click(); f.drv->frame();
  EXPECT_FALSE(widget("ai_scope_capture")->enabled); // 17 * 60 = 1020.
  EXPECT_EQ(widget("ai_scope_cells")->table->rows, 1020);
  widget("ai_scope_kind")->index.assign(1); f.drv->frame();
  widget("ai_scope_field/" + field_id)->boolean.assign(false); f.drv->frame();
  EXPECT_FALSE(widget("ai_scope_capture")->enabled); // 17 * 59 = 1003.
  widget("ai_scope_field/50000001-5555-4555-8555-555555555555")->boolean.assign(false); f.drv->frame();
  ASSERT_TRUE(widget("ai_scope_capture")->enabled);
  widget("ai_scope_capture")->on_click(); ai_frame();
  EXPECT_EQ(state().discussion().context().at("selection").at("record_ids").size(), 17u);
  EXPECT_EQ(state().discussion().context().at("selection").at("field_ids").size(), 58u);
  EXPECT_EQ(state().project()->revision, 2);
}

TEST_F(ProjectPython, HomeCreatesTheOfflineExampleProjectAndOpensIt)
{
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorWorkspace));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  ASSERT_NE(widget("workspace_demo"), nullptr);
  ASSERT_TRUE(widget("workspace_demo")->enabled);
  widget("workspace_demo")->on_click();
  f.drv->frame();
  EXPECT_FALSE(widget("workspace_demo")->enabled);  // One example at a time.
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return state().loaded() && !state().busy(); }, 300))
      << state().error() << client->bridge_log().text();
  EXPECT_TRUE(state().error().empty()) << state().error();
  EXPECT_EQ(state().project()->name, "STK example / 示例项目");
  // Resolved by the service (/private/var on macOS, backslashes on Windows): compare paths, not strings.
  const auto made = core::path_from_utf8(state().project()->directory);
  EXPECT_TRUE(std::filesystem::equivalent(made.parent_path(), core::path_from_utf8(dir.str() + "/projects")))
      << state().project()->directory;
  EXPECT_EQ(core::path_to_utf8(made.filename()).rfind("stk-example-", 0), 0u) << state().project()->directory;
  size_t parameter_rows = 0;
  for (const auto &table : state().tables()) {
    if (table.name == "Cases / 算例" || table.name == "Results / 结果") { parameter_rows += table.records.size(); }
  }
  EXPECT_EQ(parameter_rows, 6u);
  f.drv->frame();
  EXPECT_EQ(widget("workspace_demo"), nullptr);  // Offered only while no project is open.
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, AIKeySetInTheAppIsUsedForTheSessionOrRememberedAndNeverShownOrLogged)
{
  populated();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &discussion = state().discussion();
  const auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  ASSERT_TRUE(discussion.key_settings_supported());
  ASSERT_TRUE(loop.pump_until([&] { ai_frame(); return discussion.provider_loaded() && !discussion.busy(); }, 30));
  EXPECT_FALSE(discussion.provider().value("configured", true));
  ASSERT_NE(widget("ai_key_settings/ai_key"), nullptr) << "The key panel opens while no key is set.";
  EXPECT_FALSE(widget("ai_key_settings/ai_key_save")->enabled);
  EXPECT_FALSE(widget("ai_key_settings/ai_key_clear")->enabled);
  // Low-entropy stand-ins (never real credentials) that still pass the key format check.
  const std::string session_key = "placeholder-" + std::string(16, 's'), saved_key = "placeholder-" + std::string(16, 'r');
  widget("ai_key_settings/ai_key")->string.assign(session_key); ai_frame();
  ASSERT_TRUE(widget("ai_key_settings/ai_key_save")->enabled);
  widget("ai_key_settings/ai_key_save")->on_click(); ai_frame();
  ASSERT_TRUE(loop.pump_until([&] { ai_frame(); return !discussion.busy(); }, 30));
  EXPECT_TRUE(discussion.error().empty()) << discussion.error();
  EXPECT_TRUE(discussion.provider().value("configured", false));
  EXPECT_EQ(discussion.provider().value("key_source", ""), "session");
  ASSERT_NE(widget("ai_key_settings/ai_key"), nullptr);
  EXPECT_TRUE(widget("ai_key_settings/ai_key")->string.value().empty());  // Handed over, not kept in the field.
  const auto key_file = core::path_from_utf8(dir.str() + "/bridge/token-plan-key.json");
  EXPECT_FALSE(std::filesystem::exists(key_file));

  widget("ai_key_settings/ai_key_remember")->boolean.assign(true);
  widget("ai_key_settings/ai_key")->string.assign(saved_key); ai_frame();
  widget("ai_key_settings/ai_key_save")->on_click();
  ASSERT_TRUE(loop.pump_until([&] { ai_frame(); return !discussion.busy(); }, 30));
  EXPECT_EQ(discussion.provider().value("key_source", ""), "saved");
  ASSERT_TRUE(std::filesystem::exists(key_file));
#ifndef _WIN32
  EXPECT_EQ(std::filesystem::status(key_file).permissions() & std::filesystem::perms::all,
            std::filesystem::perms::owner_read | std::filesystem::perms::owner_write);
#endif
  ASSERT_TRUE(widget("ai_key_settings/ai_key_clear")->enabled);
  widget("ai_key_settings/ai_key_clear")->on_click();
  ASSERT_TRUE(loop.pump_until([&] { ai_frame(); return !discussion.busy(); }, 30));
  EXPECT_FALSE(discussion.provider().value("configured", true));
  EXPECT_FALSE(std::filesystem::exists(key_file));
  // Neither key appears in the service log, the app log or anything the bridge replied.
  const auto log = client->bridge_log().text();
  EXPECT_EQ(log.find(session_key), std::string::npos);
  EXPECT_EQ(log.find(saved_key), std::string::npos);
  for (auto *buffer : {&f.shell->store().app_log(), &f.shell->store().bridge_log()}) {
    for (size_t i = 0; i < buffer->line_count(); ++i) {
      const std::string line(buffer->line(i));
      EXPECT_EQ(line.find("placeholder-"), std::string::npos) << line;
    }
  }
  EXPECT_EQ(discussion.provider().dump().find("placeholder-"), std::string::npos);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, AIWorkspaceFirstTypedQuestionPreparesOnceWithoutSending)
{
  populated();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area); f.drv->frame();
  const auto [open_x, open_y] = f.widget_center("a2/header/project_ai");
  f.drv->click(open_x, open_y); f.screen.run_deferred();
  ASSERT_EQ(area.editor().type().id, kEditorAI);
  ai_frame();
  auto &discussion = state().discussion();
  const auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  ASSERT_TRUE(widget("ai_capture")->enabled);
  const auto [capture_x, capture_y] = f.widget_center("a2/main/ai_capture");
  f.drv->click(capture_x, capture_y); ai_frame();
  ASSERT_FALSE(discussion.context().empty());
  EXPECT_EQ(discussion.context().at("source_revision"), 1);
  EXPECT_FALSE(widget("ai_prepare")->enabled);
  ASSERT_NO_FATAL_FAILURE(choose_token_plan());
  const auto input_key = "a2/main/ai_question/" + state().project()->handle;
  const auto [x, y] = f.widget_center(input_key);
  f.drv->click(x, y);
  const std::string question = "Explain this temperature. 请保留原始参数。";
  f.drv->key(wm::Key::Unknown, wm::ModNone, question); f.drv->frame();
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), question);
  EXPECT_TRUE(f.screen.ui()->find(input_key)->string.value().empty()); // Not yet blurred.
  ASSERT_TRUE(widget("ai_prepare")->enabled);
  const auto [prepare_x, prepare_y] = f.widget_center("a2/main/ai_prepare");
  f.drv->click(prepare_x, prepare_y); ai_frame();
  ASSERT_FALSE(discussion.exchange_request().empty()) << discussion.exchange_error();
  const auto request = discussion.exchange_request();
  EXPECT_EQ(discussion.exchange_question().at("text"), question);
  EXPECT_EQ(request.at("status"), "pending");
  EXPECT_TRUE(request.at("executor_id").is_null());
  EXPECT_FALSE(widget("ai_send_saved")->enabled); // Empty fixture key; never call a real model.
  const auto [again_x, again_y] = f.widget_center("a2/main/ai_prepare");
  f.drv->click(again_x, again_y); ai_frame();
  EXPECT_EQ(discussion.exchange_request().at("id"), request.at("id"));
  ASSERT_EQ(discussion.page("requests").items.size(), 1u);
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, AIUsageShowsProviderReceiptsAndTheSendButtonNamesTheModel)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Usage scope")); settled();
  ASSERT_TRUE(discussion.load_provider()); settled();
  ASSERT_TRUE(discussion.prepare_question(discussion.context().at("id"), "Explain the saved values", "fixture-model")); settled();
  const std::string id = discussion.exchange_request().at("id");
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area); ai_frame();
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text == text) { return &item; } }
    }
    return static_cast<const ui::Widget *>(nullptr);
  };
  // The saved question goes to the model frozen in it (U2); nothing is sent here.
  const auto *send = f.screen.ui()->find("a2/main/ai_send_saved");
  ASSERT_NE(send, nullptr);
  EXPECT_EQ(send->text, "Send this saved question (fixture-model)");
  EXPECT_FALSE(send->enabled);  // empty fixture key
  // The usage read is passive (it never makes the conversation busy), so wait for what it shows.
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return shows("No completed requests in this project yet.") != nullptr; }, 30));
  // A reply completed with the provider's receipt is counted once the exchange is read again.
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\nowner = str(uuid4())\n"
      "s.requests._claim('" + id + "', executor_id=owner)\n"
      "s.requests._complete('" + id + "', executor_id=owner, text='ok', "
      "metadata={'model': 'fixture-model-2026', 'input_tokens': 1840, 'output_tokens': 212})"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  ASSERT_TRUE(discussion.refresh_exchange());
  const std::string used = "This project used 1,840 input · 212 output tokens (1 completed requests, provider receipts)";
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return shows(used) != nullptr; }, 30));
  const auto *usage = shows(used);
  ASSERT_NE(usage, nullptr);
  EXPECT_NE(usage->tooltip.find("fixture-model-2026: 1 requests · 1,840 input · 212 output"), std::string::npos) << usage->tooltip;
  EXPECT_EQ(state().project()->revision, 1);  // reading usage changes nothing
}

TEST_F(ProjectPython, AIWorkspaceActiveDraftAndStaleButtonsStayWithTheirProject)
{
  populated();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area); ai_frame();
  auto *capture = f.screen.ui()->find("a2/main/ai_capture");
  ASSERT_NE(capture, nullptr);
  const auto old_capture = capture->on_click;
  const auto first_handle = state().project()->handle;
  const auto first_input = "a2/main/ai_question/" + first_handle;
  const auto [x, y] = f.widget_center(first_input);
  f.drv->click(x, y); f.drv->key(wm::Key::Unknown, wm::ModNone, "Draft for the first project");
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "Draft for the first project");
  ASSERT_TRUE(state().create(dir.str() + "/second", "Second")); settled();
  ASSERT_TRUE(state().apply(sample_commands())); settled();
  // No intermediate empty frame: active toolkit editing must not bind to B.
  ai_frame();
  EXPECT_EQ(f.screen.ui()->find(first_input), nullptr);
  auto *second_input = f.screen.ui()->find("a2/main/ai_question/" + state().project()->handle);
  ASSERT_NE(second_input, nullptr);
  EXPECT_TRUE(second_input->string.value().empty());
  EXPECT_FALSE(f.screen.ui()->text_input_active());
  old_capture();
  EXPECT_FALSE(state().discussion().busy());
  EXPECT_TRUE(state().discussion().context().empty());
  const auto [bx, by] = f.widget_center("a2/main/ai_question/" + state().project()->handle);
  f.drv->click(bx, by); f.drv->key(wm::Key::Unknown, wm::ModNone, "Second project draft");
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled(); ai_frame();
  EXPECT_NE(state().project()->handle, first_handle);
  EXPECT_EQ(f.screen.ui()->find("a2/main/ai_question/" + state().project()->handle)->string.value(),
            "Draft for the first project");
  EXPECT_TRUE(state().discussion().page("requests").items.empty());
  ASSERT_TRUE(state().open(dir.str() + "/second")); settled(); ai_frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/ai_question/" + state().project()->handle)->string.value(),
            "Second project draft");
  EXPECT_TRUE(state().discussion().page("requests").items.empty());
}

TEST_F(ProjectPython, AIWorkspaceLongBilingualReplyWrapsWhenResizedAndRemainsSavedVerbatim)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Saved scope")); settled();
  ASSERT_TRUE(discussion.load_provider()); settled();
  ASSERT_TRUE(discussion.prepare_question(discussion.context().at("id"), "Explain the saved values", "fixture-model")); settled();
  const std::string id = discussion.exchange_request().at("id");
  std::string answer;
  for (int i = 0; i < 50; ++i) { answer += "The saved temperature is 300 K.\t\t\t\t这是受控显示样例，未调用模型。"; }
  answer += " END_OF_SAVED_REPLY";
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\nowner = str(uuid4())\n"
      "s.requests._claim('" + id + "', executor_id=owner)\n"
      "s.requests._complete('" + id + "', executor_id=owner, text=" + Json(answer).dump() + ")"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  ASSERT_TRUE(discussion.refresh_exchange());
  ASSERT_TRUE(loop.pump_until([&] { return !discussion.exchange_busy(); }));
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area); ai_frame();
  size_t wide_lines = 0;
  const auto check = [&] {
    const auto *view = f.screen.ui()->find("a2/main/ai_transcript");
    ASSERT_NE(view, nullptr); ASSERT_NE(view->log, nullptr);
    EXPECT_GT(view->log->line_count(), 20u);
    std::string shown;
    for (size_t i = 0; i < view->log->line_count(); ++i) {
      EXPECT_LE(f.measurer.width(view->log->line(i), f.screen.ui()->style().mono),
                view->rect.w - 2 * f.screen.ui()->style().unit);
      shown += view->log->line(i);
    }
    EXPECT_NE(shown.find("END_OF_SAVED_REPLY"), std::string::npos);
    EXPECT_NE(shown.find("这是受控显示样例"), std::string::npos);
    EXPECT_EQ(discussion.exchange_reply().at("text"), answer);
  };
  check(); wide_lines = f.screen.ui()->find("a2/main/ai_transcript")->log->line_count();
  f.drv->ctx.rect = {0, 0, 760, 1000}; ai_frame(); check();
  EXPECT_GT(f.screen.ui()->find("a2/main/ai_transcript")->log->line_count(), wide_lines);
  EXPECT_EQ(discussion.page("requests").items.front().at("status"), "completed");
  EXPECT_EQ(state().project()->revision, 1);
}

TEST_F(ProjectPython, AIWorkspaceMultipleAreasShareTheDisplayedRequestIdentity)
{
  populated();
  const std::string first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const std::string second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  ASSERT_NO_FATAL_FAILURE(saved_request(first));
  ASSERT_NO_FATAL_FAILURE(saved_request(second));
  ASSERT_TRUE(f.area("a1").set_tab_type(0, kEditorAI));
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorAI));
  ai_frame();
  auto &discussion = state().discussion();
  const auto check = [&](const std::string &id) {
    for (const auto *area : {"a1", "a2"}) {
      const auto *history = f.screen.ui()->find(std::string(area) + "/main/ai_history");
      ASSERT_NE(history, nullptr);
      const int index = history->index.value();
      ASSERT_GE(index, 0);
      ASSERT_LT(size_t(index), discussion.page("requests").items.size());
      EXPECT_EQ(discussion.page("requests").items[size_t(index)].at("id"), id);
    }
    EXPECT_EQ(discussion.exchange_request().at("id"), id);
  };
  ASSERT_TRUE(discussion.load_exchange(first)); ai_frame(); check(first);
  const auto &items = discussion.page("requests").items;
  const int index = items.front().at("id") == second ? 0 : 1;
  f.screen.ui()->find("a1/main/ai_history")->index.assign(index); ai_frame(); check(second);
  ASSERT_TRUE(discussion.cancel_request(second)); ai_frame(); check(second);
  EXPECT_EQ(discussion.exchange_request().at("status"), "cancelled");
  EXPECT_TRUE(discussion.exchange_reply().empty());
}

TEST_F(ProjectPython, RequestRecordsCancelAndReopenWithoutExecuting)
{
  populated();
  const std::string id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_NO_FATAL_FAILURE(saved_request(id));
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.requests_supported());
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto frame = [&] { for (int i = 0; i < 3; ++i) { f.drv->frame(); settled(); } f.drv->frame(); };
  const auto widget = [&](const char *key) { return f.screen.ui()->find(std::string("a2/main/") + key); };
  frame();
  widget("message_composer/text")->string.assign("Unsubmitted note");
  widget("discussion_category")->index.assign(3); frame();
  ASSERT_EQ(discussion.page("requests").items.size(), 1u);
  ASSERT_TRUE(widget("open_discussion_item")->enabled); widget("open_discussion_item")->on_click(); frame();
  ASSERT_EQ(io::get_string(discussion.generation_request(), "id"), id);
  ASSERT_NE(widget("request_details"), nullptr);
  ASSERT_TRUE(widget("request_cancel")->enabled);
  const auto cancel = widget("request_cancel")->on_click;
  cancel(); frame();
  EXPECT_EQ(discussion.generation_request().at("status"), Json("cancelled"));
  const auto cancelled = io::canonical_json(discussion.generation_request());
  EXPECT_FALSE(widget("request_cancel")->enabled);
  cancel(); frame();
  EXPECT_EQ(io::canonical_json(discussion.generation_request()), cancelled);
  widget("request_message")->on_click(); frame();
  ASSERT_NE(widget("message_composer/text"), nullptr);
  EXPECT_EQ(widget("message_composer/text")->string.value(), "Unsubmitted note");
  EXPECT_EQ(state().project()->revision, 1);
  ASSERT_TRUE(state().close()); settled();
  EXPECT_TRUE(discussion.generation_request().empty());
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled();
  ASSERT_TRUE(discussion.load_page("requests")); settled();
  EXPECT_TRUE(discussion.generation_request().empty());
  ASSERT_TRUE(discussion.load_request(id)); settled();
  EXPECT_EQ(io::canonical_json(discussion.generation_request()), cancelled);
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RequestButtonsAndRepliesStayBoundToTheirOriginalTarget)
{
  populated();
  const std::string first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  ASSERT_NO_FATAL_FAILURE(saved_request(first));
  ASSERT_NO_FATAL_FAILURE(saved_request(second));
  auto &discussion = state().discussion();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto frame = [&] { for (int i = 0; i < 3; ++i) { f.drv->frame(); settled(); } f.drv->frame(); };
  frame(); f.screen.ui()->find("a2/main/discussion_category")->index.assign(3); frame();
  ASSERT_TRUE(discussion.load_request(first)); frame();
  const auto old_cancel = f.screen.ui()->find("a2/main/request_cancel")->on_click;
  ASSERT_TRUE(discussion.load_request(second)); frame();
  old_cancel(); settled();
  EXPECT_EQ(io::get_string(discussion.generation_request(), "id"), second);
  EXPECT_EQ(io::get_string(discussion.generation_request(), "status"), "pending");
  ASSERT_TRUE(discussion.load_request(first)); settled();
  EXPECT_EQ(io::get_string(discussion.generation_request(), "status"), "pending");
  ASSERT_TRUE(discussion.load_request(first));
  ASSERT_TRUE(state().create(dir.str() + "/other", "Other project")); settled();
  old_cancel(); settled();
  EXPECT_TRUE(discussion.generation_request().empty());
  ASSERT_TRUE(discussion.load_page("requests")); settled();
  EXPECT_TRUE(discussion.page("requests").items.empty());
  EXPECT_EQ(state().project()->revision, 0);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RequestCompletionRefreshOpensOnlyItsSavedResponse)
{
  populated();
  const std::string id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_NO_FATAL_FAILURE(saved_request(id));
  auto &discussion = state().discussion();
  const auto context_id = discussion.context().at("id");
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto frame = [&] { for (int i = 0; i < 3; ++i) { f.drv->frame(); settled(); } f.drv->frame(); };
  const auto widget = [&](const char *key) { return f.screen.ui()->find(std::string("a2/main/") + key); };
  frame(); widget("discussion_category")->index.assign(3); frame();
  ASSERT_TRUE(discussion.load_request(id)); frame();
  EXPECT_FALSE(widget("request_result")->enabled);
  ASSERT_TRUE(state().apply(set_cell(350))); settled();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  // A controlled local completion fixture, not a model provider or UI-generated response.
  const std::string source = "from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\nowner = str(uuid4())\n"
      "s.requests._claim('" + id + "', executor_id=owner)\n"
      "s.requests._complete('" + id + "', executor_id=owner, text='Saved fixture response; no code is executed')";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  EXPECT_EQ(io::get_string(discussion.generation_request(), "status"), "pending");
  frame(); widget("request_reload")->on_click(); frame();
  EXPECT_EQ(io::get_string(discussion.generation_request(), "status"), "completed");
  ASSERT_EQ(discussion.page("requests").items.size(), 1u);
  EXPECT_EQ(discussion.page("requests").items.front().at("status"), "completed");
  ASSERT_TRUE(widget("request_result")->enabled);
  EXPECT_FALSE(widget("request_cancel")->enabled);
  widget("request_result")->on_click(); frame();
  EXPECT_EQ(discussion.message().at("context_id"), context_id);
  EXPECT_EQ(discussion.message().at("role"), Json("assistant"));
  EXPECT_EQ(discussion.message().at("text"), Json("Saved fixture response; no code is executed"));
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_FALSE(state().review());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RequestPreparationUsesSavedMessageAndMissingKeyNeverClaims)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Explicit model scope")); settled();
  ASSERT_TRUE(discussion.add_message("Explain the saved parameter")); settled();
  const auto message = discussion.message().at("id");
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto frame = [&] { for (int i = 0; i < 3; ++i) { f.drv->frame(); settled(); } f.drv->frame(); };
  const auto widget = [&](const char *key) { return f.screen.ui()->find(std::string("a2/main/") + key); };
  frame(); widget("message_composer/text")->string.assign("Unsubmitted draft is not model input");
  widget("discussion_category")->index.assign(3); frame();
  ASSERT_TRUE(discussion.generation_supported());
  EXPECT_FALSE(discussion.provider().at("configured").get<bool>());
  ASSERT_NE(widget("request_prepare/model"), nullptr);
  EXPECT_EQ(widget("request_prepare/model")->string.value(), "fixture-model");
  ASSERT_TRUE(widget("request_prepare/prepare")->enabled);
  const auto prepare = widget("request_prepare/prepare")->on_click;
  prepare(); frame();
  ASSERT_FALSE(discussion.generation_request().empty());
  const auto request = discussion.generation_request();
  EXPECT_EQ(request.at("message_id"), message);
  EXPECT_EQ(request.at("configuration").at("model"), "fixture-model");
  EXPECT_EQ(request.at("status"), "pending");
  prepare(); frame();
  EXPECT_EQ(discussion.generation_request().at("id"), request.at("id"));
  EXPECT_FALSE(widget("request_start")->enabled);
  // The service also enforces preflight if a client bypasses the disabled native button.
  ASSERT_TRUE(discussion.start_request(request.at("id").get<std::string>())); settled();
  EXPECT_FALSE(discussion.error().empty());
  ASSERT_TRUE(discussion.load_request(request.at("id").get<std::string>())); settled();
  EXPECT_EQ(discussion.generation_request().at("status"), "pending");
  EXPECT_TRUE(discussion.generation_request().at("executor_id").is_null());
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  frame(); widget("request_message")->on_click(); frame();
  EXPECT_EQ(widget("message_composer/text")->string.value(), "Unsubmitted draft is not model input");
  ASSERT_TRUE(discussion.add_message("A different saved question")); settled();
  const auto original = discussion.generation_request().at("id");
  prepare(); settled();  // A button built for the old message cannot prepare from the new one.
  EXPECT_EQ(discussion.generation_request().at("id"), original);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RequestRecoveryExplicitlyChecksAbandonedExecutionWithoutSending)
{
  populated();
  const std::string id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_NO_FATAL_FAILURE(saved_request(id));
  auto &discussion = state().discussion();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\n"
      "s.requests._claim('" + id + "', executor_id=str(uuid4()))"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto frame = [&] { for (int i = 0; i < 3; ++i) { f.drv->frame(); settled(); } f.drv->frame(); };
  const auto widget = [&](const char *key) { return f.screen.ui()->find(std::string("a2/main/") + key); };
  frame(); widget("discussion_category")->index.assign(3); frame();
  ASSERT_TRUE(discussion.load_request(id)); frame();
  EXPECT_EQ(discussion.generation_request().at("status"), "running");
  ASSERT_TRUE(widget("request_recover")->enabled);
  widget("request_recover")->on_click(); frame();
  EXPECT_EQ(discussion.generation_request().at("status"), "uncertain");
  EXPECT_EQ(discussion.generation_request().at("error_code"), "executor_lost");
  EXPECT_FALSE(widget("request_recover")->enabled);
  EXPECT_FALSE(widget("request_start")->enabled);
  EXPECT_FALSE(widget("request_result")->enabled);
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExchangePreparationFreezesContextAndReusesSavedQuestionWithoutSending)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Prepared scope")); settled();
  const auto context = discussion.context();
  const auto context_id = context.at("id").get<std::string>();
  ASSERT_TRUE(discussion.load_provider()); settled();
  ASSERT_TRUE(state().apply(set_cell(350))); settled();
  ASSERT_TRUE(discussion.prepare_question(context_id, "Explain the saved temperature", "fixture-model")); settled();
  ASSERT_FALSE(discussion.exchange_request().empty()) << discussion.exchange_error();
  const auto request = discussion.exchange_request(), question = discussion.exchange_question();
  EXPECT_EQ(io::canonical_json(discussion.exchange_context()), io::canonical_json(context));
  EXPECT_EQ(request.at("source_revision"), 1);
  EXPECT_EQ(request.at("message_id"), question.at("id"));
  EXPECT_EQ(question.at("text"), "Explain the saved temperature");
  EXPECT_EQ(request.at("status"), "pending");
  EXPECT_TRUE(request.at("executor_id").is_null());
  EXPECT_TRUE(discussion.exchange_reply().empty());
  EXPECT_TRUE(discussion.message().empty());
  EXPECT_FALSE(discussion.following());
  EXPECT_TRUE(std::isinf(discussion.pump(100)));
  ASSERT_TRUE(discussion.prepare_question(context_id, "Explain the saved temperature", "fixture-model")); settled();
  ASSERT_TRUE(discussion.exchange_error().empty()) << discussion.exchange_error();
  EXPECT_EQ(io::canonical_json(discussion.exchange_request()), io::canonical_json(request));
  EXPECT_EQ(io::canonical_json(discussion.exchange_question()), io::canonical_json(question));
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  ASSERT_TRUE(discussion.load_page("requests")); settled();
  EXPECT_EQ(discussion.page("requests").items.size(), 1u);
  ASSERT_TRUE(discussion.prepare_question(context_id, "A second saved question", "fixture-model")); settled();
  EXPECT_NE(discussion.exchange_request().at("id"), request.at("id"));
  EXPECT_NE(discussion.exchange_question().at("id"), question.at("id"));
  EXPECT_EQ(discussion.exchange_request().at("status"), "pending");
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExchangePreparationFailureKeepsOneQuestionAndPublishesNoPartialBundle)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Saved scope")); settled();
  const auto context_id = discussion.context().at("id").get<std::string>();
  ASSERT_TRUE(discussion.load_provider()); settled();
  // The question save succeeds before request configuration validation rejects the model.
  ASSERT_TRUE(discussion.prepare_question(context_id, "Retain my saved question", "invalid//model")); settled();
  EXPECT_FALSE(discussion.exchange_error().empty());
  EXPECT_FALSE(discussion.exchange_busy());
  EXPECT_TRUE(discussion.exchange_request().empty());
  EXPECT_TRUE(discussion.exchange_context().empty());
  EXPECT_TRUE(discussion.exchange_question().empty());
  EXPECT_TRUE(discussion.exchange_reply().empty());
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  ASSERT_EQ(discussion.page("messages").items.size(), 1u);
  const auto question_id = discussion.page("messages").items.front().at("id");
  ASSERT_TRUE(discussion.prepare_question(context_id, "Retain my saved question", "invalid//model")); settled();
  EXPECT_FALSE(discussion.exchange_error().empty());
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  ASSERT_EQ(discussion.page("messages").items.size(), 1u);
  EXPECT_EQ(discussion.page("messages").items.front().at("id"), question_id);
  ASSERT_TRUE(discussion.prepare_question(context_id, "Retain my saved question", "fixture-model")); settled();
  ASSERT_FALSE(discussion.exchange_question().empty()) << discussion.exchange_error();
  EXPECT_EQ(discussion.exchange_question().at("id"), question_id);
  EXPECT_EQ(discussion.exchange_request().at("status"), "pending");
  EXPECT_TRUE(discussion.exchange_error().empty());
  ASSERT_TRUE(discussion.load_page("requests")); settled();
  EXPECT_EQ(discussion.page("requests").items.size(), 1u);
}

TEST_F(ProjectPython, ExchangeFollowingReadsSavedCompletionWithoutChangingLegacySelection)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Original scope")); settled();
  const auto context = discussion.context();
  const auto context_id = context.at("id").get<std::string>();
  ASSERT_TRUE(discussion.load_provider()); settled();
  ASSERT_TRUE(discussion.prepare_question(context_id, "Explain my saved input", "fixture-model")); settled();
  const auto id = discussion.exchange_request().at("id").get<std::string>();
  const auto question = discussion.exchange_question();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  const auto fixture = [&](const std::string &operation) {
    EXPECT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
        "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\n" + operation));
    EXPECT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
    EXPECT_EQ(scripts.status().at("run").at("state"), "succeeded");
  };
  fixture("s.requests._claim('" + id + "', executor_id=str(uuid4()))");
  ASSERT_TRUE(discussion.refresh_exchange());
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(100); return !discussion.exchange_busy(); }));
  ASSERT_TRUE(discussion.following());
  EXPECT_EQ(discussion.exchange_request().at("status"), "running");
  ASSERT_TRUE(discussion.load_page("requests")); settled();
  ASSERT_EQ(discussion.page("requests").items.size(), 1u);
  EXPECT_EQ(discussion.page("requests").items.front().at("status"), "running");
  EXPECT_DOUBLE_EQ(discussion.pump(100), 101);
  ASSERT_TRUE(state().apply(set_cell(350))); settled();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Later browsing scope")); settled();
  ASSERT_TRUE(discussion.add_message("Unrelated saved note")); settled();
  const auto legacy_context = discussion.context(), legacy_message = discussion.message();
  fixture("r = s.requests.get('" + id + "')\n"
      "s.requests._complete('" + id + "', executor_id=r['executor_id'], text='Saved local answer: 300 K')");
  EXPECT_TRUE(std::isinf(discussion.pump(101)));
  EXPECT_TRUE(discussion.exchange_busy());
  EXPECT_FALSE(discussion.busy());
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(101); return !discussion.exchange_busy(); }));
  EXPECT_EQ(discussion.exchange_request().at("status"), "completed");
  EXPECT_EQ(discussion.page("requests").items.front().at("status"), "completed");
  EXPECT_EQ(io::canonical_json(discussion.exchange_context()), io::canonical_json(context));
  EXPECT_EQ(io::canonical_json(discussion.exchange_question()), io::canonical_json(question));
  EXPECT_EQ(discussion.exchange_reply().at("text"), "Saved local answer: 300 K");
  EXPECT_EQ(discussion.exchange_reply().at("id"), discussion.exchange_request().at("assistant_message_id"));
  EXPECT_EQ(discussion.context(), legacy_context);
  EXPECT_EQ(discussion.message(), legacy_message);
  EXPECT_FALSE(discussion.following());
  EXPECT_TRUE(std::isinf(discussion.pump(102)));
  // A retained Prepare identity must reopen its existing answer, never erase or resend it.
  ASSERT_TRUE(discussion.load_context(context_id)); settled();
  ASSERT_TRUE(discussion.prepare_question(context_id, "Explain my saved input", "fixture-model")); settled();
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(103); return !discussion.exchange_busy(); }));
  ASSERT_TRUE(discussion.exchange_error().empty()) << discussion.exchange_error();
  EXPECT_EQ(discussion.exchange_request().at("id"), id);
  EXPECT_EQ(discussion.exchange_request().at("status"), "completed");
  EXPECT_EQ(io::canonical_json(discussion.exchange_question()), io::canonical_json(question));
  EXPECT_EQ(discussion.exchange_reply().at("text"), "Saved local answer: 300 K");
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExchangeFollowingIsBoundedAndExplicitRefreshResumesWithoutRecovery)
{
  populated();
  const std::string id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_NO_FATAL_FAILURE(saved_request(id));
  auto &discussion = state().discussion();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }));
  ASSERT_TRUE(scripts.execute("from suan.project import ProjectStore\nfrom uuid import uuid4\n"
      "s = ProjectStore(" + Json(dir.str() + "/project").dump() + ")\n"
      "s.requests._claim('" + id + "', executor_id=str(uuid4()))"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  ASSERT_TRUE(discussion.load_exchange(id));
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(100); return !discussion.exchange_busy(); }));
  EXPECT_TRUE(discussion.following());
  EXPECT_DOUBLE_EQ(discussion.pump(100), 101);
  const auto before = client->stats().calls_sent;
  EXPECT_TRUE(std::isinf(discussion.pump(190)));
  EXPECT_FALSE(discussion.following());
  EXPECT_TRUE(std::isinf(discussion.pump(1000)));
  loop.run_ready();
  EXPECT_EQ(client->stats().calls_sent, before);
  EXPECT_EQ(discussion.exchange_request().at("status"), "running");
  ASSERT_TRUE(discussion.refresh_exchange());
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(1000); return !discussion.exchange_busy(); }));
  EXPECT_TRUE(discussion.following());
  EXPECT_DOUBLE_EQ(discussion.pump(1000), 1001);
  EXPECT_EQ(discussion.exchange_request().at("status"), "running");
  // Recovery remains an explicit action and the refreshed observation follows uncertain results too.
  ASSERT_TRUE(discussion.recover_request(id)); settled();
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(1000); return !discussion.exchange_busy(); }));
  EXPECT_EQ(discussion.exchange_request().at("status"), "uncertain");
  EXPECT_TRUE(discussion.following());
  EXPECT_TRUE(discussion.exchange_reply().empty());
}

TEST_F(ProjectPython, ExchangeReadsDoNotBlockCancelOrPublishAnOlderSnapshot)
{
  populated();
  const std::string id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_NO_FATAL_FAILURE(saved_request(id));
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.load_exchange(id));
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(100); return !discussion.exchange_busy(); }));
  ASSERT_EQ(discussion.exchange_request().at("status"), "pending");
  ASSERT_TRUE(discussion.refresh_exchange());
  ASSERT_TRUE(discussion.exchange_busy());
  EXPECT_FALSE(discussion.busy());
  // The older get response is queued while cancellation changes this request.
  ASSERT_TRUE(discussion.cancel_request(id));
  ASSERT_TRUE(loop.pump_until([&] {
    discussion.pump(100);
    return !discussion.exchange_busy() && !discussion.busy() && !state().busy();
  }));
  ASSERT_FALSE(discussion.exchange_request().empty()) << discussion.exchange_error();
  EXPECT_EQ(discussion.exchange_request().at("status"), "cancelled");
  EXPECT_EQ(discussion.generation_request().at("status"), "cancelled");
  EXPECT_FALSE(discussion.following());
  EXPECT_TRUE(discussion.exchange_reply().empty());
  EXPECT_EQ(discussion.exchange_question().at("id"), discussion.exchange_request().at("message_id"));
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExchangeSelectionReadErrorsAndProjectCloseFenceIncompleteBundles)
{
  populated();
  const std::string first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const std::string second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const std::string missing = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
  ASSERT_NO_FATAL_FAILURE(saved_request(first));
  auto &discussion = state().discussion();
  ASSERT_TRUE(state().apply(set_cell(350))); settled();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Another scope")); settled();
  ASSERT_TRUE(discussion.add_message("Another question")); settled();
  ASSERT_NO_FATAL_FAILURE(saved_request(second));
  const auto second_context = discussion.context(), second_question = discussion.message();
  ASSERT_TRUE(discussion.load_exchange(first));
  ASSERT_TRUE(discussion.load_exchange(second));
  EXPECT_TRUE(discussion.exchange_request().empty());
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(100); return !discussion.exchange_busy(); }));
  ASSERT_EQ(discussion.exchange_request().at("id"), second);
  EXPECT_EQ(io::canonical_json(discussion.exchange_context()), io::canonical_json(second_context));
  EXPECT_EQ(io::canonical_json(discussion.exchange_question()), io::canonical_json(second_question));
  ASSERT_TRUE(discussion.load_exchange(missing));
  ASSERT_TRUE(loop.pump_until([&] { discussion.pump(100); return !discussion.exchange_busy(); }));
  EXPECT_FALSE(discussion.exchange_error().empty());
  EXPECT_TRUE(discussion.exchange_request().empty());
  EXPECT_TRUE(discussion.exchange_context().empty());
  EXPECT_TRUE(discussion.exchange_question().empty());
  EXPECT_TRUE(discussion.exchange_reply().empty());
  EXPECT_FALSE(discussion.following());
  const auto before = client->stats().calls_sent;
  EXPECT_TRUE(std::isinf(discussion.pump(1000)));
  loop.run_ready();
  EXPECT_EQ(client->stats().calls_sent, before);
  ASSERT_TRUE(discussion.load_exchange(first));
  ASSERT_TRUE(state().close()); settled();
  EXPECT_TRUE(discussion.exchange_request().empty());
  EXPECT_FALSE(discussion.exchange_busy());
  EXPECT_FALSE(discussion.following());
  EXPECT_TRUE(std::isinf(discussion.pump(2000)));
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled();
  EXPECT_TRUE(discussion.exchange_request().empty());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

Json filtered_commands()
{
  const std::string group = "55555555-5555-4555-8555-555555555555";
  Json commands = Json::array({{{"op", "add_field"}, {"table_id", table_id}, {"id", group}, {"name", "Group"}, {"type", "text"}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", group}, {"value", "Hidden"}}});
  const int values[] = {20, 3, 1, 9};
  for (int i = 0; i < 4; ++i) {
    const auto id = std::to_string(40000001 + i) + "-4444-4444-8444-444444444444";
    commands.push_back({{"op", "add_record"}, {"table_id", table_id}, {"id", id}});
    commands.push_back({{"op", "set_cell"}, {"table_id", table_id}, {"record_id", id}, {"field_id", field_id}, {"value", values[i]}});
    commands.push_back({{"op", "set_cell"}, {"table_id", table_id}, {"record_id", id}, {"field_id", group}, {"value", i < 2 ? "Red" : "Blue"}});
  }
  return commands;
}

TEST_F(ProjectPython, TableFilterSortAndEditKeepRecordIdentityAcrossEqualSizeQueries)
{
  populated();
  ASSERT_TRUE(state().apply(filtered_commands())); settled();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject)); f.screen.set_maximized(&area);
  auto frame = [&] { f.drv->frame(); settled(); f.drv->frame(); };
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto records = table_id + "/records";
  frame();
  widget("table_search")->string.assign("RED"); frame();
  ASSERT_NE(widget(records), nullptr);
  ASSERT_EQ(widget(records)->table->rows, 2);
  EXPECT_EQ(widget(records)->table->selected.value(), -1);
  EXPECT_EQ(state().record_id(), record_id); // Hiding the selection does not choose another record.
  EXPECT_EQ(widget("save_cell"), nullptr);
  const auto click = [&](bool header) {
    const auto rect = widget(records)->rect;
    const auto style = f.screen.ui()->style();
    const float y = rect.y + style.pixel + style.unit * (header ? 0.5f : 1.5f);
    f.drv->click(int(rect.x + style.pixel + style.unit * 8), f.screen.rect().ymax - 1 - int(y));
    frame();
  };
  click(true); click(false);
  EXPECT_EQ(state().record_id(), "40000002-4444-4444-8444-444444444444");
  ASSERT_NE(widget("cell_value"), nullptr);
  widget("cell_value")->string.assign("4"); frame();
  widget("save_cell")->on_click(); frame();
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().table()->text(1, 0), "20");
  EXPECT_EQ(state().table()->text(2, 0), "4");
  const auto old_save = widget("save_cell")->on_click;
  const auto old_selection = widget(records)->table->selected;
  widget("table_search")->string.assign("blue");
  old_save(); old_selection.assign(0); // Blur can update search before a new frame is drawn.
  settled();
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().record_id(), "40000002-4444-4444-8444-444444444444");
  frame();
  ASSERT_EQ(widget(records)->table->rows, 2);
  EXPECT_EQ(widget(records)->table->selected.value(), -1);
  old_save(); settled();
  EXPECT_EQ(state().project()->revision, 3);
  click(false);
  EXPECT_EQ(state().record_id(), "40000003-4444-4444-8444-444444444444");
  const auto chosen = state().record_id();
  widget("table_clear_search")->on_click(); frame();
  EXPECT_EQ(widget(records)->table->rows, 5);
  EXPECT_EQ(state().record_id(), chosen);
  ASSERT_TRUE(state().undo()); frame();
  EXPECT_EQ(state().table()->text(2, 0), "3");
  widget("table_search")->string.assign("missing text"); frame();
  EXPECT_EQ(widget(records)->table->rows, 0);
  EXPECT_EQ(state().record_id(), chosen);
  EXPECT_EQ(widget("save_cell"), nullptr);
}

TEST_F(ProjectPython, SweepPanelAddsTypedRowsAsOneUndoableEditAndNeverRetargetsAPlan)
{
  populated();
  const std::string steps = "44444444-4444-4444-8444-000000000001", derived = "44444444-4444-4444-8444-000000000002";
  ASSERT_TRUE(state().apply(Json::array({
      {{"op", "add_field"}, {"table_id", table_id}, {"id", steps}, {"name", "Steps"}, {"type", "integer"}},
      {{"op", "add_field"}, {"table_id", table_id}, {"id", derived}, {"name", "Derived"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "set_expression"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", derived},
       {"expression", "base + quantity(10, \"K\")"}, {"bindings", {{"base", {{"record_id", record_id}, {"field_id", field_id}}}}}},
  })));
  settled();
  ASSERT_EQ(state().project()->revision, 2);
  ASSERT_TRUE(state().supports_sweep());
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject)); f.screen.set_maximized(&area);
  auto frame = [&] { f.drv->frame(); settled(); f.drv->frame(); };
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_sweep/" + key); };
  frame();
  ASSERT_EQ(widget("axis0/start"), nullptr);  // Collapsed until asked for.
  const auto [x, y] = f.widget_center("a2/main/project_sweep");
  f.drv->click(x, y); frame();
  ASSERT_NE(widget("axis0/start"), nullptr);
  EXPECT_EQ(widget("axis0/field")->index.value(), 0);  // Temperature (number): an evenly spaced range.
  EXPECT_FALSE(widget("apply_sweep")->enabled);
  widget("axis0/start")->string.assign("300");
  widget("axis0/stop")->string.assign("400");
  widget("axis0/count")->string.assign("3");
  frame();
  ASSERT_TRUE(widget("apply_sweep")->enabled);
  EXPECT_EQ(widget("apply_sweep")->text, "Add 3 rows");
  widget("add_axis")->on_click(); frame();
  ASSERT_NE(widget("axis1/field"), nullptr);
  EXPECT_EQ(widget("axis1/field")->index.value(), 1);  // The next field no other parameter uses: Steps.
  widget("axis1/field")->index.assign(0); frame();  // The same field twice is refused before asking Python.
  EXPECT_FALSE(widget("apply_sweep")->enabled);
  widget("axis1/field")->index.assign(1); frame();
  widget("axis1/kind")->index.assign(1); frame();
  widget("axis1/values")->string.assign("10, 2.5"); frame();  // Not integers.
  EXPECT_FALSE(widget("apply_sweep")->enabled);
  widget("axis1/values")->string.assign("10, 20"); frame();
  EXPECT_EQ(widget("apply_sweep")->text, "Add 6 rows");
  widget("combine")->index.assign(1); frame();  // Pairing 3 with 2 values is refused before asking Python.
  EXPECT_FALSE(widget("apply_sweep")->enabled);
  widget("combine")->index.assign(0); frame();
  state().select_record(record_id); frame();
  ASSERT_TRUE(widget("copy_selected")->enabled);
  EXPECT_TRUE(widget("copy_selected")->boolean.value());
  // One edit holds 1000 commands: 150 x 2 rows need 3 each, or 4 with the copied formula.
  widget("axis0/count")->string.assign("150"); frame();
  EXPECT_FALSE(widget("apply_sweep")->enabled);
  widget("copy_selected")->boolean.assign(false); frame();
  EXPECT_TRUE(widget("apply_sweep")->enabled);
  EXPECT_EQ(widget("apply_sweep")->text, "Add 300 rows");
  widget("copy_selected")->boolean.assign(true);
  widget("axis0/count")->string.assign("3"); frame();
  widget("apply_sweep")->on_click(); frame();
  ASSERT_TRUE(state().error().empty()) << state().error();
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().notice(), "Added 6 rows.");
  const auto *table = state().table();
  ASSERT_EQ(table->records.size(), 7u);
  EXPECT_EQ(state().record_id(), table->records[1].id);  // The first new row is selected.
  EXPECT_EQ(table->text(1, 0), "300");
  EXPECT_EQ(table->text(1, 1), "10");
  EXPECT_EQ(table->text(6, 0), "400");
  EXPECT_EQ(table->text(6, 1), "20");
  for (size_t row = 1; row < 7; ++row) {
    // The copied formula reads each new row's own temperature, not the base row's.
    const auto *definition = table->definition(int(row), 2);
    ASSERT_NE(definition, nullptr);
    EXPECT_EQ(definition->at("bindings").at("base").at("record_id"), table->records[row].id);
  }
  ASSERT_TRUE(state().undo()); settled();
  EXPECT_EQ(state().table()->records.size(), 1u);

  // A plan made before another writer's edit is dropped, never applied at the newer revision.
  const auto revision = state().project()->revision;
  ASSERT_TRUE(state().sweep(table_id, Json::array({{{"field_id", field_id}, {"values", {1, 2}}}}), "", "product"));
  EXPECT_FALSE(state().sweep(table_id, Json::array({{{"field_id", field_id}, {"values", {3}}}}), "", "product"));  // Busy.
  std::optional<bridge::Result<Json>> other;
  client->project_apply(state().project()->handle, revision, set_cell(500)).then([&](auto result) { other = result; });
  ASSERT_TRUE(loop.pump_until([&] { return other.has_value(); }));
  settled();
  ASSERT_TRUE(other->ok()) << other->error().message;
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().table()->records.size(), 1u);
  EXPECT_EQ(state().project()->revision, revision + 1);
  EXPECT_EQ(state().table()->text(0, 0), "500");
}

/** A native dialog stand-in: keeps each request and answers only when the test says so. */
class HeldDialog final : public platform::FileDialog {
 public:
  std::string name() const override { return "held"; }
  void open(const platform::FileDialogRequest &request, std::function<void(platform::FileDialogResult)> done) override
  {
    requests.push_back(request);
    pending = std::move(done);
  }
  void answer(std::vector<std::string> paths, std::string error = {})
  {
    auto done = std::move(pending);
    pending = {};
    ASSERT_TRUE(done);
    done({std::move(paths), std::move(error)});
  }
  std::vector<platform::FileDialogRequest> requests;
  std::function<void(platform::FileDialogResult)> pending;
};

TEST_F(ProjectPython, BrowseButtonsOnlyFillPathFieldsAndDropAnswersForAnotherProject)
{
  auto &jobs = f.shell->store().jobs();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject)); f.screen.set_maximized(&area);
  auto frame = [&] { f.drv->frame(); settled(); f.drv->frame(); };
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  auto open_panel = [&](const std::string &key) {
    const auto [x, y] = f.widget_center("a2/main/" + key);
    f.drv->click(x, y);
    frame();
  };
  frame();
  ASSERT_NE(widget("project_location/directory"), nullptr);
  EXPECT_EQ(widget("project_location/browse_directory"), nullptr);  // No native dialog: typing only.
  HeldDialog dialog;
  jobs.file_dialog = &dialog;
  struct Reset { app::JobsState &jobs; ~Reset() { jobs.file_dialog = nullptr; } } reset{jobs};
  frame();
  ASSERT_NE(widget("project_location/browse_directory"), nullptr);
  widget("project_location/browse_directory")->on_click();
  ASSERT_EQ(dialog.requests.size(), 1u);
  EXPECT_EQ(dialog.requests[0].mode, platform::FileDialogMode::OpenFolder);
  EXPECT_EQ(dialog.requests[0].title, "Choose the project folder");
  dialog.answer({dir.str() + "/chosen"}); frame();
  EXPECT_EQ(widget("project_location/directory")->string.value(), dir.str() + "/chosen");
  EXPECT_FALSE(state().project());  // Choosing a folder neither opens nor creates a project.
  widget("project_location/browse_directory")->on_click();
  dialog.answer({}, "zenity: exited with status 255"); frame();  // The field stays; the reason is shown.
  EXPECT_EQ(widget("project_location/directory")->string.value(), dir.str() + "/chosen");

  populated(); frame();
  const auto revision = state().project()->revision;
  open_panel("project_csv");
  ASSERT_NE(widget("project_csv/browse_source"), nullptr);
  widget("project_csv/browse_source")->on_click();
  EXPECT_EQ(dialog.requests.back().mode, platform::FileDialogMode::OpenFiles);
  dialog.answer({"/data/a.csv", "/data/b.csv"}); frame();
  EXPECT_EQ(widget("project_csv/source")->string.value(), "/data/a.csv");  // One input file.
  widget("project_csv/browse_destination")->on_click();
  EXPECT_EQ(dialog.requests.back().mode, platform::FileDialogMode::SaveFile);
  EXPECT_EQ(dialog.requests.back().file_name, "Cases.csv");
  dialog.answer({"/data/out.csv"}); frame();
  EXPECT_EQ(widget("project_csv/destination")->string.value(), "/data/out.csv");

  open_panel("project_files");
  ASSERT_NE(widget("project_files/browse_files"), nullptr);
  widget("project_files/browse_files")->on_click();
  dialog.answer({"/x/1.dat", "/x/2.dat"}); frame();
  widget("project_files/browse_files")->on_click();
  dialog.answer({"/x/3.dat"}); frame();
  EXPECT_EQ(widget("project_files/paths")->string.value(), "/x/1.dat\n/x/2.dat\n/x/3.dat");  // Files add up.

  open_panel("project_simulation");
  ASSERT_NE(widget("project_simulation/simulation_browse"), nullptr);
  widget("project_simulation/simulation_browse")->on_click();
  EXPECT_EQ(dialog.requests.back().mode, platform::FileDialogMode::OpenFolder);
  dialog.answer({"/cases/one"}); frame();
  EXPECT_EQ(widget("project_simulation/simulation_source")->string.value(), "/cases/one");
  EXPECT_EQ(state().project()->revision, revision);  // Nothing was imported, indexed or exported.

  // An answer that arrives after another project was opened is dropped, not written into its fields.
  widget("project_csv/browse_source")->on_click();
  ASSERT_TRUE(state().create(dir.str() + "/other", "Other")); settled(); frame();
  EXPECT_EQ(widget("project_csv/source")->string.value(), "");
  dialog.answer({"/data/late.csv"}); frame();
  EXPECT_EQ(widget("project_csv/source")->string.value(), "");

  ASSERT_TRUE(area.set_tab_type(0, kEditorPython)); frame();
  open_panel("python_file");
  ASSERT_NE(widget("python_file/python_browse"), nullptr);
  widget("python_file/python_browse")->on_click();
  dialog.answer({"/scripts/a.py"}); frame();
  EXPECT_EQ(widget("python_file/python_path")->string.value(), "/scripts/a.py");
  EXPECT_TRUE(f.shell->store().scripts().history().empty());  // Choosing a script does not run it.
}

TEST_F(ProjectPython, TableFiltersBelongToEachAreaWhileSelectionRemainsShared)
{
  populated();
  ASSERT_TRUE(state().apply(filtered_commands())); settled();
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorProject));
  ASSERT_TRUE(f.area("a3").set_tab_type(0, kEditorProject));
  const auto widget = [&](const std::string &area, const std::string &key) { return f.screen.ui()->find(area + "/main/" + key); };
  const auto records = table_id + "/records";
  f.drv->frame();
  ASSERT_NE(widget("a2", "table_search"), nullptr); ASSERT_NE(widget("a3", "table_search"), nullptr);
  widget("a2", "table_search")->string.assign("red");
  widget("a3", "table_search")->string.assign("blue");
  f.drv->frame();
  ASSERT_EQ(widget("a2", records)->table->rows, 2);
  ASSERT_EQ(widget("a3", records)->table->rows, 2);
  widget("a2", records)->table->selected.assign(0); f.drv->frame();
  EXPECT_EQ(state().record_id(), "40000001-4444-4444-8444-444444444444");
  EXPECT_EQ(widget("a3", records)->table->selected.value(), -1);
  EXPECT_EQ(widget("a3", "table_search")->string.value(), "blue");
  widget("a3", records)->table->selected.assign(1); f.drv->frame();
  EXPECT_EQ(state().record_id(), "40000004-4444-4444-8444-444444444444");
  EXPECT_EQ(widget("a2", records)->table->selected.value(), -1);
  EXPECT_EQ(widget("a2", "table_search")->string.value(), "red");
  widget("a2", "table_errors_only")->boolean.assign(true); f.drv->frame();
  EXPECT_EQ(widget("a2", records)->table->rows, 0);
  EXPECT_EQ(widget("a3", records)->table->rows, 2);
  EXPECT_EQ(state().project()->revision, 2);
}

TEST_F(ProjectPython, DiscussionCellGridReadsOnlyCapturedValuesAfterLiveEditsAndDeletion)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Frozen values")); settled();
  const auto original = io::canonical_json(discussion.context());
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  auto frame = [&] { f.drv->frame(); settled(); f.drv->frame(); };
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  frame();
  ASSERT_NE(widget("captured_cells/rows"), nullptr);
  EXPECT_EQ(widget("captured_cells/rows")->table->rows, 1);
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 1), "Temperature / K");
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 2), "300");
  ASSERT_TRUE(state().apply(set_cell(350))); frame();
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 2), "300");
  ASSERT_TRUE(state().apply(Json::array({{{"op", "delete_field"}, {"id", field_id}}}))); frame();
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 1), "Temperature / K");
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 2), "300");
  EXPECT_EQ(io::canonical_json(discussion.context()), original);
  const auto *detail = widget("captured_cells/cell_details"); ASSERT_NE(detail, nullptr);
  const ui::Vec2 point{detail->rect.x + detail->rect.w / 2, detail->rect.y + detail->rect.h / 2};
  f.screen.ui()->handle_event(ui::Event::mouse_down(point));
  f.screen.ui()->handle_event(ui::Event::mouse_up(point)); frame();
  ASSERT_NE(widget("captured_cells/cell_details/value"), nullptr);
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Missing field now")); frame();
  ASSERT_NE(widget("captured_cells/rows"), nullptr);
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 2), "—");
  EXPECT_EQ(widget("captured_cells/rows")->table->cell(0, 3), "Field missing");
  EXPECT_EQ(state().project()->revision, 3);
}

TEST_F(ProjectPython, DiscussionCaptureKeepsOriginalValuesAndRestoresWithoutExecuting)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.supported());
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Initial / 初始"));
  settled();
  ASSERT_FALSE(discussion.context().empty()) << discussion.error();
  const auto context = discussion.context();
  const auto context_id = io::get_string(context, "id");
  EXPECT_EQ(context.at("source_revision"), Json(1));
  EXPECT_EQ(context.at("content").at("value").at("records")[0].at("literals").at(field_id).at("value"), Json(300));
  ASSERT_TRUE(discussion.add_message("Please compare this parameter.\n```python\nraise Exception('never run')\n```"));
  settled();
  const auto message = discussion.message();
  ASSERT_FALSE(message.empty()) << discussion.error();
  ASSERT_TRUE(discussion.add_message(io::get_string(message, "text")));
  settled();
  EXPECT_EQ(io::canonical_json(discussion.message()), io::canonical_json(message)); // Repeated click is the same retained request.
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Initial / 初始"));
  settled();
  EXPECT_EQ(io::canonical_json(discussion.context()), io::canonical_json(context));
  ASSERT_TRUE(state().apply(set_cell(350)));
  settled();
  EXPECT_EQ(io::canonical_json(discussion.context()), io::canonical_json(context));
  state().select_record("");
  EXPECT_EQ(io::canonical_json(discussion.context()), io::canonical_json(context));
  ASSERT_TRUE(state().close()); settled();
  EXPECT_TRUE(discussion.context().empty()); EXPECT_TRUE(discussion.message().empty());
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled();
  ASSERT_TRUE(discussion.load_page("contexts")); settled();
  ASSERT_EQ(discussion.page("contexts").items.size(), 1u);
  EXPECT_EQ(discussion.page("contexts").items[0].at("id"), Json(context_id));
  EXPECT_FALSE(discussion.page("contexts").items[0].at("content").contains("value"));
  EXPECT_TRUE(discussion.context().empty());
  ASSERT_TRUE(discussion.load_context(context_id)); settled();
  EXPECT_EQ(io::canonical_json(discussion.context()), io::canonical_json(context));
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  ASSERT_EQ(discussion.page("messages").items.size(), 1u);
  ASSERT_TRUE(discussion.load_message(io::get_string(message, "id"))); settled();
  EXPECT_EQ(io::canonical_json(discussion.message()), io::canonical_json(message));
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_FALSE(state().review());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DiscussionLinksSavedDraftAtCapturedBaseAndKeepsOriginAfterUndo)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Source")); settled();
  ASSERT_TRUE(discussion.add_message("Raise this value to 350 K.")); settled();
  const auto message = discussion.message();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().save_review("350 K")); settled();
  const auto draft = state().saved_review();
  ASSERT_TRUE(discussion.link_review()); settled();
  ASSERT_FALSE(discussion.origin().empty()) << discussion.error();
  const auto origin = discussion.origin();
  EXPECT_EQ(origin.at("message_id"), message.at("id"));
  EXPECT_EQ(origin.at("context_id"), discussion.context().at("id"));
  EXPECT_EQ(origin.at("draft_id"), draft.at("id"));
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(discussion.link_review()); settled();
  EXPECT_EQ(io::canonical_json(discussion.origin()), io::canonical_json(origin));
  ASSERT_TRUE(state().apply_review()); settled();
  ASSERT_TRUE(state().undo()); settled();
  ASSERT_TRUE(discussion.load_origin(io::get_string(draft, "id"))); settled();
  EXPECT_EQ(io::canonical_json(discussion.origin()), io::canonical_json(origin));
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  state().discard_review();
  state().set_review_source(set_cell(400).dump());
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().save_review("Different base")); settled();
  ASSERT_TRUE(discussion.link_review()); settled();
  EXPECT_FALSE(discussion.error().empty());
  EXPECT_EQ(io::canonical_json(discussion.origin()), io::canonical_json(origin));
  ASSERT_TRUE(discussion.load_page("proposals", 0, true)); settled();
  EXPECT_FALSE(discussion.error().empty());
  ASSERT_EQ(discussion.page("proposals").items.size(), 1u);
  EXPECT_EQ(io::canonical_json(discussion.page("proposals").items[0]), io::canonical_json(origin));
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DiscussionPendingResponsesCannotCrossProjectOrBridgeRestart)
{
  populated();
  auto &discussion = state().discussion();
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Old project"));
  ASSERT_TRUE(state().create(dir.str() + "/other", "Other"));
  settled();
  EXPECT_EQ(state().project()->name, "Other");
  EXPECT_TRUE(discussion.context().empty());
  ASSERT_TRUE(discussion.load_page("contexts")); settled();
  EXPECT_TRUE(discussion.page("contexts").items.empty());
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled();
  ASSERT_TRUE(discussion.load_page("contexts")); settled();
  ASSERT_EQ(discussion.page("contexts").items.size(), 1u);
  const auto id = io::get_string(discussion.page("contexts").items[0], "id");
  ASSERT_TRUE(discussion.load_context(id)); settled();
  ASSERT_TRUE(discussion.add_message("Saved before restart")); settled();
  const auto old_handle = state().project()->handle;
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] { return state().ready() && state().loaded() && !state().busy() && state().project()->handle != old_handle; }, 60));
  EXPECT_TRUE(discussion.context().empty());
  EXPECT_TRUE(discussion.message().empty());
  EXPECT_FALSE(state().review());
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  ASSERT_EQ(discussion.page("messages").items.size(), 1u);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, DiscussionNativeControlsCaptureAndSaveWithoutOverwritingNewInput)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion"));
  f.screen.set_maximized(&area);
  auto frame = [&] { f.drv->frame(); settled(); f.drv->frame(); };
  auto widget = [&](const char *name) -> const ui::Widget * { return f.screen.ui()->find(std::string("a2/main/") + name); };
  frame();
  ASSERT_NE(widget("context_capture/title"), nullptr);
  widget("context_capture/title")->string.assign("Native capture");
  ASSERT_NE(widget("context_capture/use_selection"), nullptr);
  ASSERT_TRUE(widget("context_capture/use_selection")->enabled);
  widget("context_capture/use_selection")->on_click();
  frame();
  ASSERT_TRUE(widget("context_capture/capture")->enabled);
  widget("context_capture/capture")->on_click();
  frame();
  auto &discussion = state().discussion();
  ASSERT_FALSE(discussion.context().empty()) << discussion.error();
  EXPECT_EQ(discussion.context().at("selection").at("record_ids"), Json::array({record_id}));
  EXPECT_EQ(discussion.context().at("selection").at("field_ids"), Json::array({field_id}));
  ASSERT_NE(widget("message_composer/text"), nullptr);
  widget("message_composer/text")->string.assign("Original text");
  frame();
  ASSERT_TRUE(widget("message_composer/save_message")->enabled);
  widget("message_composer/save_message")->on_click();
  widget("message_composer/text")->string.assign("New text while save is pending");
  frame();
  ASSERT_FALSE(discussion.message().empty()) << discussion.error();
  EXPECT_EQ(discussion.message().at("text"), Json("Original text"));
  EXPECT_EQ(widget("message_composer/text")->string.value(), "New text while save is pending");
  const auto save_for_old_context = widget("message_composer/save_message")->on_click;
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Different context")); settled();
  save_for_old_context(); // A retained button cannot silently retarget its message to another context.
  EXPECT_FALSE(discussion.busy());
  ASSERT_TRUE(discussion.load_page("messages")); settled();
  EXPECT_EQ(discussion.page("messages").items.size(), 1u);
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().save_review("UI proposal")); settled();
  frame();
  ASSERT_TRUE(widget("link_review")->enabled);
  widget("link_review")->on_click();
  frame();
  ASSERT_FALSE(discussion.origin().empty()) << discussion.error();
  widget("discussion_category")->index.assign(2);
  frame();
  ASSERT_TRUE(widget("open_discussion_item")->enabled);
  widget("open_discussion_item")->on_click();
  frame();
  EXPECT_EQ(widget("project_view")->index.value(), 1); // The same saved draft needs no destructive reload.
  ASSERT_NE(widget("review_apply"), nullptr);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, SavedDraftReopensWithStableIdsAndRequiresFreshReviewBeforeAtomicApply)
{
  populated();
  state().set_review_source(Json::array({{{"op", "create_table"}, {"name", "Saved proposal"}}}).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().review());
  const auto commands = state().review()->commands;
  ASSERT_TRUE(state().save_review("Saved / 草案"));
  settled();
  const auto saved = state().saved_review();
  ASSERT_FALSE(saved.empty()) << state().drafts_error();
  const auto id = io::get_string(saved, "id");
  EXPECT_EQ(io::canonical_json(saved.at("commands")), io::canonical_json(commands));
  EXPECT_TRUE(state().can_apply_review()); // Canonical storage may reorder object keys, never commands.
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().tables().size(), 1u);
  ASSERT_TRUE(state().close());
  settled();
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_TRUE(state().saved_review().empty());
  ASSERT_TRUE(state().load_drafts());
  settled();
  ASSERT_EQ(state().drafts().size(), 1u);
  EXPECT_EQ(state().drafts()[0].at("id"), Json(id));
  ASSERT_TRUE(state().load_draft(id));
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().apply_review());
  EXPECT_EQ(io::canonical_json(io::parse_json(state().review_source())), io::canonical_json(commands));
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().review());
  EXPECT_EQ(io::canonical_json(state().review()->commands), io::canonical_json(commands));
  ASSERT_TRUE(state().apply_review());
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().saved_review().at("status"), Json("applied"));
  ASSERT_EQ(state().tables().size(), 2u);
  EXPECT_EQ(state().tables()[1].id, commands[0].at("id").get<std::string>());
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().tables().size(), 1u);
  std::optional<bridge::Result<Json>> replay;
  client->call("project.drafts.apply", {{"handle", state().project()->handle}, {"draft_id", id},
                                       {"expected_revision", 1}}).then([&](auto result) { replay = result; });
  ASSERT_TRUE(loop.pump_until([&] { return replay.has_value(); }));
  ASSERT_TRUE(replay->ok()) << replay->error().describe();
  EXPECT_EQ(replay->value().at("revision"), Json(2));
  EXPECT_EQ(replay->value().at("replayed"), Json(true));
  state().refresh();
  settled();
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, SavedDraftStaysAtItsBaseUntilExplicitCopyAndDiscardKeepsAudit)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().save_review("Original"));
  settled();
  const auto original = io::get_string(state().saved_review(), "id");
  ASSERT_FALSE(original.empty()) << state().drafts_error();
  state().discard_review();
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  ASSERT_TRUE(state().load_draft(original));
  settled();
  EXPECT_FALSE(state().preview());
  EXPECT_FALSE(state().can_apply_review());
  EXPECT_FALSE(state().review_error().empty());
  EXPECT_EQ(io::get_int(state().saved_review(), "base_revision", -1), 1);
  EXPECT_EQ(state().table()->text(0, 0), "500");
  ASSERT_TRUE(state().copy_saved_review());
  settled();
  ASSERT_TRUE(state().review());
  EXPECT_EQ(state().review()->base_revision, 2);
  EXPECT_TRUE(state().saved_review().empty());
  ASSERT_TRUE(state().save_review("New proposal"));
  settled();
  const auto replacement = io::get_string(state().saved_review(), "id");
  EXPECT_NE(replacement, original);
  ASSERT_TRUE(state().discard_saved_draft(original));
  settled();
  EXPECT_EQ(state().saved_review().at("id"), Json(replacement));
  EXPECT_TRUE(state().can_apply_review());
  ASSERT_TRUE(state().load_drafts());
  settled();
  ASSERT_EQ(state().drafts().size(), 2u);
  EXPECT_EQ(state().drafts()[0].at("status"), Json("discarded"));
  EXPECT_EQ(state().drafts()[1].at("status"), Json("pending"));
  EXPECT_EQ(state().project()->revision, 2);
  ASSERT_TRUE(state().discard_saved_draft(replacement));
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().preview());
  EXPECT_FALSE(state().can_apply_review());
  EXPECT_EQ(state().project()->revision, 2);
}

TEST_F(ProjectPython, SavedDraftCallbacksPreserveNewInputAndRestartOnlyReloadsMetadata)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().save_review("Finishing save"));
  state().set_review_source("new unsaved input");
  settled();
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(state().review_source(), "new unsaved input");
  ASSERT_TRUE(state().load_drafts());
  settled();
  ASSERT_EQ(state().drafts().size(), 1u);
  const auto id = io::get_string(state().drafts()[0], "id");
  EXPECT_FALSE(state().load_draft(id));
  state().discard_review();
  ASSERT_TRUE(state().load_draft(id));
  state().set_review_source("typed during load");
  settled();
  EXPECT_TRUE(state().saved_review().empty());
  EXPECT_EQ(state().review_source(), "typed during load");
  state().discard_review();
  ASSERT_TRUE(state().load_draft(id));
  settled();
  ASSERT_TRUE(state().preview());
  settled();
  const auto old_handle = state().project()->handle;
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] {
    return state().loaded() && !state().busy() && state().project()->handle != old_handle;
  }, 60));
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().review_source(), "[]");
  EXPECT_TRUE(state().saved_review().empty());
  ASSERT_TRUE(state().load_drafts());
  settled();
  ASSERT_EQ(state().drafts().size(), 1u);
  EXPECT_EQ(state().drafts()[0].at("id"), Json(id));
  EXPECT_EQ(state().project()->revision, 1);
}

TEST_F(ProjectPython, SavedDraftNativePanelSavesLoadsReviewsAndAppliesThroughSharedState)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("review"));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/saved_reviews");
  f.drv->click(x, y);
  f.drv->frame();
  settled();
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  ASSERT_NE(widget("saved_reviews/draft_title"), nullptr);
  widget("saved_reviews/draft_title")->string.assign("Native saved proposal");
  f.drv->frame();
  ASSERT_TRUE(widget("saved_reviews/save_review")->enabled);
  widget("saved_reviews/save_review")->on_click();
  settled();
  EXPECT_FALSE(state().saved_review().empty()) << state().drafts_error();
  EXPECT_EQ(state().project()->revision, 1);
  f.drv->frame();
  settled();
  f.drv->frame();
  ASSERT_NE(widget("saved_reviews/draft_rows"), nullptr);
  widget("review_discard")->on_click();
  f.drv->frame();
  ASSERT_TRUE(widget("saved_reviews/load_draft")->enabled);
  widget("saved_reviews/load_draft")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(widget("review_apply"), nullptr);
  widget("review_preview")->on_click();
  settled();
  f.drv->frame();
  ASSERT_NE(widget("review_apply"), nullptr);
  ASSERT_TRUE(widget("review_apply")->enabled);
  widget("review_apply")->on_click();
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_EQ(state().saved_review().at("status"), Json("applied"));
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, SavedDraftErrorsSurviveAutomaticListRefreshAndConflictsRefreshTheProject)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("review"));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/saved_reviews");
  f.drv->click(x, y);
  f.drv->frame();
  settled();
  ASSERT_TRUE(state().save_review("   "));
  settled();
  ASSERT_FALSE(state().drafts_error().empty());
  const auto error = state().drafts_error();
  f.drv->frame(); // An automatic list refresh must not hide the failed operation.
  settled();
  f.drv->frame();
  EXPECT_EQ(state().drafts_error(), error);
  EXPECT_EQ(state().project()->revision, 1);
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  const auto source = "from suan.project import ProjectStore\nimport json\nProjectStore(" +
      Json(dir.str() + "/project").dump() + ").apply(json.loads(" + Json(set_cell(700).dump()).dump() + "), expected_revision=1)";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  EXPECT_EQ(state().project()->revision, 1);
  ASSERT_TRUE(state().save_review("Conflict"));
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "700");
  EXPECT_FALSE(state().can_apply_review());
  EXPECT_FALSE(state().drafts_error().empty());
  EXPECT_TRUE(state().drafts().empty());
}

TEST_F(ProjectPython, ReviewAllocatesStableIdsWithoutWritingAndAppliesOnceWithUndo)
{
  populated();
  state().set_review_source(Json::array({{{"op", "create_table"}, {"name", "Draft / 草案"}}}).dump());
  ASSERT_TRUE(state().preview());
  EXPECT_FALSE(state().apply_review());
  settled();
  ASSERT_TRUE(state().review()) << state().review_error();
  const auto review = state().review();
  EXPECT_EQ(review->base_revision, 1);
  EXPECT_EQ(review->proposed_revision, 2);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().tables().size(), 1u);
  ASSERT_EQ(review->differences.size(), 1u);
  const auto &change = review->differences.front();
  EXPECT_EQ(change.kind, "table");
  EXPECT_FALSE(change.before);
  ASSERT_TRUE(change.after);
  EXPECT_EQ(change.after->at("name"), "Draft / 草案");
  EXPECT_EQ(change.table_id, io::get_string(review->commands.front(), "id"));
  ASSERT_TRUE(state().can_apply_review());
  ASSERT_TRUE(state().apply_review());
  EXPECT_FALSE(state().apply_review());
  settled();
  ASSERT_EQ(state().tables().size(), 2u);
  EXPECT_EQ(state().tables().back().id, change.table_id);
  EXPECT_EQ(state().project()->revision, 2);
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(state().project()->revision, 3);
  ASSERT_TRUE(state().redo());
  settled();
  EXPECT_EQ(state().tables().back().id, change.table_id);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ReviewShowsDownstreamValuesAndAllErrorsWithoutRevisionOnlyNoise)
{
  populated();
  const std::string derived = "55555555-5555-4555-8555-555555555555";
  const std::string failed = "66666666-6666-4666-8666-666666666666";
  Json commands = Json::array();
  for (const auto &id : {derived, failed}) {
    commands.push_back({{"op", "add_field"}, {"id", id}, {"table_id", table_id}, {"name", id}, {"type", "number"}, {"unit", "K"}});
    commands.push_back({{"op", "set_expression"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", id},
      {"expression", id == derived ? "base * 2" : "base / 0"},
      {"bindings", {{"base", {{"record_id", record_id}, {"field_id", field_id}}}}}});
  }
  ASSERT_TRUE(state().apply(commands));
  settled();
  state().set_review_source(set_cell(450).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().review()) << state().review_error();
  const auto review = state().review();
  ASSERT_EQ(review->differences.size(), 2u);
  ASSERT_EQ(review->errors.size(), 1u);
  EXPECT_EQ(review->errors.front().before, review->errors.front().after);
  EXPECT_EQ(review->errors.front().field_id, failed);
  for (const auto &entry : review->differences) {
    EXPECT_EQ(entry.kind, "cell");
    EXPECT_EQ(entry.before->at("value"), entry.field_id == derived ? 600 : 300);
    EXPECT_EQ(entry.after->at("value"), entry.field_id == derived ? 900 : 450);
  }
  EXPECT_EQ(state().table()->text(0, 1), "= 600");
  state().set_review_source(Json::array({{{"op", "delete_table"}, {"id", table_id}}}).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().review());
  // One table, three fields, one record and all three populated cells (including the error).
  ASSERT_EQ(state().review()->differences.size(), 8u);
  for (const auto &entry : state().review()->differences) {
    EXPECT_TRUE(entry.before);
    EXPECT_FALSE(entry.after);
  }
  EXPECT_TRUE(state().review()->errors.empty());
  EXPECT_EQ(state().tables().size(), 1u);
}

TEST_F(ProjectPython, ReviewDraftChangesDiscardPendingResultsAndRejectInvalidInput)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  state().set_review_source(set_cell(400).dump());
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().apply_review());
  ASSERT_TRUE(state().preview());
  state().discard_review();
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().review_source(), "[]");
  for (const auto &source : {std::string("{"), std::string("{}"), std::string("[]"), std::string(256 * 1024 + 1, ' ')}) {
    state().set_review_source(source);
    EXPECT_FALSE(state().preview());
    EXPECT_FALSE(state().review_error().empty());
    EXPECT_FALSE(state().busy());
  }
  state().set_review_source(Json::array({{{"op", "not_an_edit"}}}).dump());
  ASSERT_TRUE(state().preview());
  settled();
  EXPECT_FALSE(state().review_error().empty());
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, ReviewStaysStaleAfterEditsAndIsClearedOnCloseOrRestart)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().review());
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  EXPECT_EQ(state().review()->base_revision, 1);
  EXPECT_FALSE(state().can_apply_review());
  EXPECT_FALSE(state().apply_review());
  ASSERT_TRUE(state().preview());
  settled();
  EXPECT_EQ(state().review()->base_revision, 2);
  ASSERT_TRUE(state().can_apply_review());
  const auto handle = state().project()->handle;
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] {
    return state().loaded() && !state().busy() && state().project()->handle != handle;
  }, 60));
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().review_source(), "[]");
  EXPECT_EQ(state().table()->text(0, 0), "500");
  state().set_review_source(set_cell(600).dump());
  ASSERT_TRUE(state().preview());
  settled();
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_EQ(state().review_source(), "[]");
}

TEST_F(ProjectPython, ReviewApplyChecksUnobservedExternalRevisionAndNeverRebases)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  const auto source = "from suan.project import ProjectStore\nimport json\nProjectStore(" +
      Json(dir.str() + "/project").dump() + ").apply(json.loads(" + Json(set_cell(700).dump()).dump() + "), expected_revision=1)";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  EXPECT_EQ(state().project()->revision, 1); // Direct store writes send no bridge event.
  ASSERT_TRUE(state().apply_review());
  settled();
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "700");
}

TEST_F(ProjectPython, ReviewCellUIShowsDiffInvalidatesEditedDraftAndAppliesExplicitly)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  widget("cell_value")->string.assign("375");
  ASSERT_TRUE(widget("review_cell")->enabled);
  widget("review_cell")->on_click();
  settled();
  f.drv->frame();
  ASSERT_NE(widget("review_rows"), nullptr);
  EXPECT_EQ(widget("review_rows")->table->rows, 1);
  EXPECT_EQ(widget("review_rows")->table->cell(0, 2), "300");
  EXPECT_EQ(widget("review_rows")->table->cell(0, 3), "375");
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(widget("review_apply")->enabled);
  // Even a callback retained from a prior frame must recheck the current draft.
  const auto apply = widget("review_apply")->on_click;
  if (!f.screen.ui()->find("a2/main/review_json/review_source")) {  // The JSON editor is folded away.
    const auto [json_x, json_y] = f.widget_center("a2/main/review_json");
    f.drv->click(json_x, json_y); f.drv->frame();
  }
  widget("review_json/review_source")->string.assign(set_cell(425).dump());
  apply();
  EXPECT_FALSE(state().busy());
  EXPECT_FALSE(state().review());
  f.drv->frame();
  EXPECT_EQ(widget("review_apply"), nullptr);
  widget("review_preview")->on_click();
  settled();
  apply(); // A new candidate must not be applied by a callback displaying the previous candidate.
  EXPECT_FALSE(state().busy());
  EXPECT_EQ(state().project()->revision, 1);
  ASSERT_TRUE(state().review());
  f.drv->frame();
  ASSERT_TRUE(widget("review_apply")->enabled);
  widget("review_apply")->on_click();
  settled();
  EXPECT_EQ(state().table()->text(0, 0), "425");
  EXPECT_EQ(state().project()->revision, 2);
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, ReviewApplyClickCommitsPendingTextAndCannotApplyTheOldCandidate)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview());
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/project_view")->index.assign(1);
  f.drv->frame();
  if (!f.screen.ui()->find("a2/main/review_json/review_source")) {  // The JSON editor is folded away.
    const auto [json_x, json_y] = f.widget_center("a2/main/review_json");
    f.drv->click(json_x, json_y); f.drv->frame();
  }
  const auto [x, y] = f.widget_center("a2/main/review_json/review_source");
  f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::A, primary);
  f.drv->key(wm::Key::Unknown, wm::ModNone, set_cell(400).dump());
  EXPECT_EQ(state().review_source(), set_cell(350).dump()); // Input is still being edited.
  const auto [apply_x, apply_y] = f.widget_center("a2/main/review_apply");
  f.drv->click(apply_x, apply_y); // Blur commits the text before the button action runs.
  EXPECT_EQ(state().review_source(), set_cell(400).dump());
  EXPECT_FALSE(state().review());
  EXPECT_FALSE(state().busy());
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, SharedSelectionPersistsAcrossRefreshConflictCloseAndReopen)
{
  populated();
  ASSERT_TRUE(state().table());
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().record_id(), record_id);
  ASSERT_TRUE(state().apply(set_cell(350)));
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().record_id(), record_id);
  ASSERT_TRUE(state().apply(set_cell(400), 1));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().table()->text(0, 0), "350");
  const std::string identity = state().project()->id;
  const std::string handle = state().project()->handle;
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_FALSE(state().project());
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  EXPECT_EQ(state().project()->id, identity);
  EXPECT_NE(state().project()->handle, handle);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, BridgeRestartReopensWithoutReplayingEdits)
{
  populated();
  const auto before = *state().project();
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] {
    return state().loaded() && !state().busy() && state().project()->handle != before.handle;
  }, 60));
  EXPECT_EQ(state().project()->id, before.id);
  EXPECT_NE(state().project()->handle, before.handle);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, RecentProjectsReopenAfterRestartAndForgetOnlyHistoryThroughButtons)
{
  populated();
  const auto before = *state().project();
  ASSERT_TRUE(state().close());
  settled();
  const auto previous_pid = client->bridge_pid();
  client->shutdown_bridge();
  ASSERT_TRUE(loop.pump_until([&] { return state().ready() && client->state() == bridge::BridgeState::Ready &&
      client->bridge_pid() != 0 && client->bridge_pid() != previous_pid; }, 60));
  EXPECT_FALSE(state().project());
  state().load_recent();
  ASSERT_TRUE(loop.pump_until([&] { return state().recent_loaded() && !state().recent_loading(); }, 30));
  ASSERT_EQ(state().recent().size(), 1u);
  EXPECT_EQ(state().recent()[0]["id"], before.id);
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto *table = f.screen.ui()->find("a2/main/project_recent/projects");
  ASSERT_NE(table, nullptr);
  ASSERT_TRUE(table->table);
  table->table->selected.assign(0);
  f.drv->frame();
  auto *open = f.screen.ui()->find("a2/main/project_recent/open");
  ASSERT_NE(open, nullptr);
  open->on_click();
  settled();
  ASSERT_TRUE(state().loaded()) << state().error();
  EXPECT_EQ(state().project()->id, before.id);
  EXPECT_NE(state().project()->handle, before.handle);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(loop.pump_until([&] { return !state().recent_loading(); }, 30));
  f.drv->frame();
  auto *forget = f.screen.ui()->find("a2/main/project_recent/forget");
  ASSERT_NE(forget, nullptr);
  forget->on_click();
  ASSERT_TRUE(loop.pump_until([&] { return !state().recent_loading(); }, 30));
  EXPECT_TRUE(state().recent().empty());
  EXPECT_TRUE(state().loaded());
  EXPECT_EQ(state().project()->revision, before.revision);
  EXPECT_TRUE(std::filesystem::is_regular_file(core::path_from_utf8(before.directory) / "project.sqlite3"));
  state().refresh();
  settled();
  EXPECT_EQ(state().table()->text(0, 0), "300");
}

TEST_F(ProjectPython, RecentIdentityGuardKeepsTheCurrentlyOpenProject)
{
  populated();
  const auto before = *state().project();
  ASSERT_TRUE(loop.pump_until([&] { return state().recent_loaded() && !state().recent_loading(); }, 30));
  Json wrong = state().recent().front();
  wrong["id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  ASSERT_TRUE(state().open_recent(wrong));
  settled();
  EXPECT_FALSE(state().error().empty());
  ASSERT_TRUE(state().loaded());
  EXPECT_EQ(state().project()->handle, before.handle);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().recent().front()["id"], before.id);
}

TEST_F(ProjectPython, CsvButtonsImportTypedRowsExportAndUndoAsOneEdit)
{
  ASSERT_TRUE(state().create(dir.str() + "/project", "CSV"));
  settled();
  const auto source = dir.str() + "/输入.csv", output = dir.str() + "/输出.csv";
  { std::ofstream file(core::path_from_utf8(source)); file << "Temperature,Note\n300,prepared\n350,中文\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto [x, y] = f.widget_center("a2/main/project_csv");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_csv/" + key); };
  ASSERT_NE(widget("source"), nullptr);
  widget("source")->string.assign(source);
  widget("name")->string.assign("Imported cases");
  auto [tx, ty] = f.widget_center("a2/main/project_csv/types");
  f.drv->click(tx, ty);
  f.drv->frame();
  ASSERT_NE(widget("types/types"), nullptr);
  widget("types/types")->string.assign(R"({"Temperature":"number"})");
  widget("types/units")->string.assign(R"({"Temperature":"K"})");
  widget("import")->on_click();
  settled();
  ASSERT_TRUE(state().error().empty()) << state().error();
  ASSERT_EQ(state().tables().size(), 1u);
  ASSERT_EQ(state().table()->records.size(), 2u);
  const auto identity = state().table_id();
  EXPECT_EQ(state().table()->fields[0].type, "number");
  EXPECT_EQ(state().table()->fields[0].unit, "K");
  EXPECT_EQ(state().table()->text(1, 0), "350");
  EXPECT_EQ(state().table()->text(1, 1), "中文");
  EXPECT_EQ(state().project()->revision, 1);
  f.drv->frame();
  widget("destination")->string.assign(output);
  widget("export")->on_click();
  settled();
  EXPECT_TRUE(state().error().empty()) << state().error();
  EXPECT_FALSE(state().notice().empty());
  EXPECT_TRUE(std::filesystem::is_regular_file(core::path_from_utf8(output)));
  EXPECT_EQ(state().project()->revision, 1);
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_TRUE(state().tables().empty());
  EXPECT_TRUE(std::filesystem::is_regular_file(core::path_from_utf8(output)));
  ASSERT_TRUE(state().redo());
  settled();
  EXPECT_EQ(state().table_id(), identity);
  EXPECT_EQ(state().table()->text(1, 0), "350");
  f.drv->frame();
  widget("export")->on_click();
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().project()->revision, 3);
  { std::ofstream file(core::path_from_utf8(source)); file << "Temperature,Note\ntrue,bad\n"; }
  f.drv->frame();
  widget("import")->on_click();
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, TableEditorSavesTypedValuesThroughSharedModel)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto *value = f.screen.ui()->find("a2/main/cell_value");
  ASSERT_NE(value, nullptr);
  auto *save = f.screen.ui()->find("a2/main/save_cell");
  ASSERT_NE(save, nullptr);
  // Drive the real bindings/callbacks rather than a second mutation implementation.
  value->string.assign("420.5");
  save->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 0), "420.5");
  value = f.screen.ui()->find("a2/main/cell_value");
  ASSERT_NE(value, nullptr);
  value->string.assign("true");
  f.screen.ui()->find("a2/main/save_cell")->on_click();
  EXPECT_FALSE(state().busy());
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "420.5");
}

TEST_F(ProjectPython, ExternalEditPreservesDraftAndRequiresReload)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/cell_value")->string.assign("450");
  std::optional<bridge::Result<Json>> edited;
  client->project_apply(state().project()->handle, 1, set_cell(500)).then([&](auto result) { edited = result; });
  ASSERT_TRUE(loop.pump_until([&] {
    return edited.has_value() && !state().busy() && state().project()->revision == 2;
  }));
  ASSERT_TRUE(edited->ok());
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "450");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  EXPECT_EQ(state().table()->text(0, 0), "500");
  f.screen.ui()->find("a2/main/reload_cell")->on_click();
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "500");
  EXPECT_TRUE(f.screen.ui()->find("a2/main/save_cell")->enabled);
}

TEST_F(ProjectPython, ReferenceAndExpressionEditorsPreserveDefinitionsAndShowErrors)
{
  populated();
  const std::string derived = "55555555-5555-4555-8555-555555555555";
  ASSERT_TRUE(state().apply(Json::array({{{"op", "add_field"}, {"id", derived}, {"table_id", table_id},
                                        {"name", "Derived"}, {"type", "number"}, {"unit", "K"}}})));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  widget("cell_field")->index.assign(1);
  f.drv->frame();
  widget("cell_mode")->index.assign(1);
  f.drv->frame();
  widget("source_table")->index.assign(1);
  f.drv->frame();
  widget("source_record")->index.assign(1);
  widget("source_field")->index.assign(1);
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 300");
  ASSERT_NE(state().table()->definition(0, 1), nullptr);
  EXPECT_EQ(state().table()->definition(0, 1)->at("source").at("field_id"), field_id);
  EXPECT_EQ(widget("cell_mode")->index.value(), 1);
  widget("cell_mode")->index.assign(2);
  f.drv->frame();
  widget("expression")->string.assign("base + quantity(10, \"K\")");
  const auto [x, y] = f.widget_center("a2/main/bindings_raw");
  f.drv->click(x, y);
  f.drv->frame();
  ASSERT_NE(widget("bindings_raw/bindings"), nullptr);
  widget("bindings_raw/bindings")->string.assign(Json{{"base", {{"record_id", record_id}, {"field_id", field_id}}}}.dump());
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 310");
  EXPECT_EQ(widget("cell_mode")->index.value(), 2);
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "= 510");
  widget("expression")->string.assign("base / 0");
  widget("save_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 1), "#division_by_zero");
  EXPECT_EQ(widget("expression")->string.value(), "base / 0");
  widget("unset_cell")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->definition(0, 1), nullptr);
  EXPECT_EQ(state().table()->cell(0, 1), nullptr);
  EXPECT_EQ(widget("cell_mode")->index.value(), 0);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ExpressionDraftSurvivesExternalDependencyChanges)
{
  populated();
  const std::string derived = "55555555-5555-4555-8555-555555555555";
  ASSERT_TRUE(state().apply(Json::array({
    {{"op", "add_field"}, {"id", derived}, {"table_id", table_id}, {"name", "Derived"}, {"type", "number"}, {"unit", "K"}},
    {{"op", "set_expression"}, {"table_id", table_id}, {"record_id", record_id}, {"field_id", derived},
     {"expression", "base * 2"}, {"bindings", {{"base", {{"record_id", record_id}, {"field_id", field_id}}}}}}
  })));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/cell_field")->index.assign(1);
  f.drv->frame();
  f.screen.ui()->find("a2/main/expression")->string.assign("base * 3");
  std::optional<bridge::Result<Json>> edited;
  client->project_apply(state().project()->handle, 2, set_cell(500)).then([&](auto result) { edited = result; });
  ASSERT_TRUE(loop.pump_until([&] { return edited.has_value() && !state().busy() && state().project()->revision == 3; }));
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/expression")->string.value(), "base * 3");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  EXPECT_EQ(state().table()->text(0, 1), "= 1000");
  f.screen.ui()->find("a2/main/reload_cell")->on_click();
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/expression")->string.value(), "base * 2");
}

TEST_F(ProjectPython, ExplicitUpgradeCreatesBackupAndRefreshesFormat)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  const std::string source = "import sqlite3\nwith sqlite3.connect(" + Json(dir.str() + "/project/project.sqlite3").dump() +
      ") as db:\n    db.execute('DROP TABLE project_agent_objects')\n    db.execute('DROP TABLE project_agent_events')\n    db.execute('DROP TABLE project_agent_sessions')\n    db.execute('DROP TABLE project_labels')\n    db.execute('DROP TABLE project_archive')\n    db.execute('DROP TABLE workflow_run_events')\n    db.execute('DROP TABLE workflow_run_plans')\n    db.execute('DROP TABLE analysis_run_events')\n    db.execute('DROP TABLE analysis_run_plans')\n    db.execute('DROP TABLE project_requests')\n    db.execute('DROP TABLE project_proposals')\n    db.execute('DROP TABLE project_messages')\n    db.execute('DROP TABLE project_contexts')\n    db.execute('DROP TABLE project_drafts')\n    db.execute('DROP TABLE run_observations')\n    db.execute('DROP TABLE run_plans')\n    db.execute('DROP TABLE project_snapshots')\n    db.execute('DROP TABLE edit_journal')\n    db.execute('DROP TABLE evaluations')\n    db.execute('DROP TABLE definitions')\n    db.execute('PRAGMA user_version=1')";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  state().refresh();
  settled();
  ASSERT_EQ(state().project()->format_version, 1);
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/upgrade_project"), nullptr);
  f.screen.ui()->find("a2/main/upgrade_project")->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().project()->format_version, 13);
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(f.screen.ui()->find("a2/main/upgrade_project"), nullptr);
  EXPECT_FALSE(state().notice().empty());
  size_t backups = 0;
  for (const auto &entry : std::filesystem::directory_iterator(dir.str() + "/project/backups")) {
    if (entry.path().extension() == ".sqlite3") { ++backups; }
  }
  EXPECT_EQ(backups, 1u);
  ASSERT_TRUE(state().backup());
  settled();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DestroyingStateDropsQueuedCallbacks)
{
  auto temporary = std::make_unique<ProjectState>(f.shell->store());
  temporary->attach(client.get());
  ASSERT_TRUE(temporary->create(dir.str() + "/temporary", "Temporary"));
  temporary.reset();
  std::optional<bridge::Result<std::vector<bridge::ProjectInfo>>> listed;
  client->project_list().then([&](auto result) { listed = result; });
  ASSERT_TRUE(loop.pump_until([&] { return listed.has_value(); }));
  EXPECT_TRUE(listed->ok());
  EXPECT_FALSE(state().project());
}

TEST_F(ProjectPython, PersistentUndoRedoButtonsAndNewEditsShareTheProjectHistory)
{
  populated();
  ASSERT_TRUE(state().apply(set_cell(450)));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  auto undo = [&] { return f.screen.ui()->find("a2/header/project_undo"); };
  auto redo = [&] { return f.screen.ui()->find("a2/header/project_redo"); };
  ASSERT_NE(undo(), nullptr);
  ASSERT_TRUE(undo()->enabled);
  EXPECT_FALSE(redo()->enabled);
  f.screen.ui()->find("a2/main/cell_value")->string.assign("Unsaved draft");
  undo()->on_click();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(f.screen.ui()->find("a2/main/cell_value")->string.value(), "Unsaved draft");
  EXPECT_FALSE(f.screen.ui()->find("a2/main/save_cell")->enabled);
  ASSERT_TRUE(redo()->enabled);
  ASSERT_TRUE(state().close());
  settled();
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  f.drv->frame();
  ASSERT_TRUE(redo()->enabled);
  redo()->on_click();
  settled();
  EXPECT_EQ(state().table()->text(0, 0), "450");
  EXPECT_EQ(state().project()->revision, 4);
  ASSERT_TRUE(state().undo());
  settled();
  ASSERT_TRUE(state().apply(set_cell(600)));
  settled();
  EXPECT_FALSE(state().can_redo());
  EXPECT_EQ(state().table()->text(0, 0), "600");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ObjectManagementRenamesDeletesAndUndoRestoresStableSelection)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/manage_objects");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/manage_objects/" + key); };
  ASSERT_NE(widget("rename_table"), nullptr);
  widget("rename_table")->string.assign("Renamed cases");
  widget("save_table_name")->on_click();
  settled();
  f.drv->frame();
  f.drv->frame();
  EXPECT_EQ(state().table()->name, "Renamed cases");
  EXPECT_EQ(state().table_id(), table_id);
  widget("rename_field")->string.assign("");
  f.drv->frame();
  ASSERT_NE(widget("rename_field"), nullptr);  // Empty text must not hide its own input.
  widget("rename_field")->string.assign("Temperature renamed");
  widget("save_field_name")->on_click();
  settled();
  f.drv->frame();
  f.drv->frame();
  EXPECT_EQ(state().table()->fields[0].name, "Temperature renamed");
  EXPECT_EQ(state().table()->fields[0].id, field_id);
  ASSERT_TRUE(widget("delete_record")->enabled);
  widget("delete_record")->on_click();
  settled();
  f.drv->frame();
  EXPECT_TRUE(state().table()->records.empty());
  ASSERT_TRUE(state().undo());
  settled();
  f.drv->frame();
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(widget("delete_table")->enabled);
  widget("delete_table")->on_click();
  settled();
  EXPECT_TRUE(state().tables().empty());
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().table_id(), table_id);
  EXPECT_EQ(state().record_id(), record_id);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RenameDraftRejectsExternalRevisionUntilExplicitReload)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/manage_objects");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/manage_objects/" + key); };
  widget("rename_table")->string.assign("Draft name");
  ASSERT_TRUE(state().apply(set_cell(500)));
  settled();
  f.drv->frame();
  EXPECT_EQ(widget("rename_table")->string.value(), "Draft name");
  EXPECT_FALSE(widget("save_table_name")->enabled);
  EXPECT_FALSE(widget("delete_table")->enabled);
  widget("reload_names")->on_click();
  f.drv->frame();
  EXPECT_EQ(widget("rename_table")->string.value(), "Cases");
  EXPECT_TRUE(widget("save_table_name")->enabled);
}

TEST_F(ProjectPython, FileIndexButtonsResolveBeforeLaunchingAndRefreshWithoutChangingFiles)
{
  populated();
  const std::string path = dir.str() + "/project/笔记 #1.md";
  { std::ofstream file(core::path_from_utf8(path)); file << "# Notes\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_files");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_files/" + key); };
  ASSERT_NE(widget("paths"), nullptr);
  widget("paths")->string.assign("笔记 #1.md");
  f.drv->frame();
  widget("index")->on_click();
  settled();
  f.drv->frame();
  ASSERT_TRUE(state().selected_file()) << state().error();
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 1), "笔记 #1.md");
  int system_calls = 0, code_calls = 0;
  state().open_external = [&](const std::string &opened, std::string *) {
    EXPECT_TRUE(std::filesystem::equivalent(core::path_from_utf8(opened), core::path_from_utf8(path)));
    ++system_calls; return true;
  };
  state().open_vscode = [&](const std::string &opened, std::string *) {
    EXPECT_TRUE(std::filesystem::equivalent(core::path_from_utf8(opened), core::path_from_utf8(path)));
    ++code_calls; return true;
  };
  widget("open")->on_click();
  settled();
  f.drv->frame();
  widget("code")->on_click();
  settled();
  EXPECT_EQ(system_calls, 1);
  EXPECT_EQ(code_calls, 1);
  EXPECT_EQ(state().project()->revision, 2);  // Resolving/opening is not an edit.
  std::filesystem::remove(core::path_from_utf8(path));
  ASSERT_TRUE(state().open_file(false));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(system_calls, 1);  // A stale 'present' observation cannot launch a missing path.
  f.drv->frame();
  widget("refresh")->on_click();
  settled();
  EXPECT_EQ(state().table()->text(0, 6), "missing");
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_EQ(state().table()->text(0, 6), "present");
  EXPECT_FALSE(std::filesystem::exists(core::path_from_utf8(path)));
  state().open_external = platform::open_with_system;
  state().open_vscode = platform::open_with_vscode;
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, IndexedPayloadOpensAHiddenViewerAndMissingFilesDoNotReplaceIt)
{
  populated();
  const auto path = core::path_from_utf8(dir.str() + "/project/结果.stkp");
  std::filesystem::copy_file(std::filesystem::path(STK_REPO_ROOT) / "desktop/tests/viewer/fixtures/muferro_domains.stkp", path);
  ASSERT_TRUE(state().index_files({core::path_to_utf8(path)}));
  settled();
  auto &area = f.area("a2");
  area.add_tab(kEditorProject); // Keep the Viewer hidden behind this tab.
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_files");
  f.drv->click(x, y);
  f.drv->frame();
  auto *button = f.screen.ui()->find("a2/main/project_files/view");
  ASSERT_NE(button, nullptr);
  button->on_click();
  settled();
  EXPECT_TRUE(state().error().empty()) << state().error();
  f.drv->frame();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_EQ(area.editor().type().id, kEditorViewer);
  EXPECT_EQ(area.tab_count(), 2);
  EXPECT_EQ(f.screen.maximized(), &area);
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(viewer.payload());
  EXPECT_EQ(viewer.source().kind, SourceKind::Payload);
  EXPECT_EQ(state().project()->revision, 2);
  const auto key = viewer.source().key();
  std::filesystem::remove(path);
  ASSERT_TRUE(state().view_file("volume"));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_FALSE(f.shell->store().has_open_result());
  EXPECT_EQ(viewer.source().key(), key);
}

TEST_F(ProjectPython, IndexedFieldsRequireACompatiblePresetAndPreserveTheExactFilename)
{
  populated();
  const auto path = core::path_from_utf8(dir.str() + "/project/场.vtk");
  { std::ofstream file(path); file << "field placeholder"; }
  ASSERT_TRUE(state().index_files({core::path_to_utf8(path)}));
  settled();
  auto &viewer = f.shell->store().viewer();
  viewer.refresh_metadata();
  ASSERT_TRUE(loop.pump_until([&] { viewer.pump(); return viewer.presets_loaded(); }, 60));
  ASSERT_TRUE(state().view_file("muferro-domains"));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_FALSE(f.shell->store().has_open_result());
  ASSERT_TRUE(state().view_file("slice"));
  settled();
  EXPECT_TRUE(state().error().empty()) << state().error();
  const auto request = f.shell->store().take_open_result();
  ASSERT_TRUE(request);
  EXPECT_EQ(request->preset, "slice");
  ASSERT_EQ(request->local_paths.size(), 1u);
  EXPECT_TRUE(std::filesystem::equivalent(core::path_from_utf8(request->local_paths[0]), path));
  EXPECT_EQ(classify_path(request->local_paths[0]).field_file, "场.vtk");
  EXPECT_EQ(state().project()->revision, 2);
  const auto text = core::path_from_utf8(dir.str() + "/project/notes.md");
  { std::ofstream file(text); file << "# notes"; }
  ASSERT_TRUE(state().index_files({core::path_to_utf8(text)}));
  settled();
  ASSERT_TRUE(state().view_file("volume"));
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_FALSE(f.shell->store().has_open_result());
}

TEST_F(ProjectPython, InputSnapshotsPersistBeyondSourceRemovalAndTableUndo)
{
  populated();
  const std::string path = dir.str() + "/project/input.dat";
  { std::ofstream file(core::path_from_utf8(path)); file << "frozen inputs"; }
  ASSERT_TRUE(state().index_files({path}));
  settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/input_snapshots");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/input_snapshots/" + key); };
  ASSERT_NE(widget("capture"), nullptr);
  ASSERT_TRUE(widget("capture")->enabled);
  widget("capture")->on_click();
  settled();
  f.drv->frame();
  ASSERT_EQ(state().input_snapshots().size(), 1u) << state().error();
  const Json snapshot = state().input_snapshots().front();
  const std::string id = io::get_string(snapshot, "id");
  EXPECT_EQ(state().project()->revision, 3);
  std::filesystem::remove(core::path_from_utf8(path));
  widget("verify")->on_click();
  settled();
  EXPECT_TRUE(state().input_verification().value("ok", false)) << state().error();
  ASSERT_TRUE(state().undo());  // Undo the index edit, never the historical input copy.
  settled();
  EXPECT_EQ(state().project()->revision, 4);
  EXPECT_TRUE(state().file_index().empty());
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_TRUE(state().input_snapshots().empty());
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  ASSERT_TRUE(state().load_input_snapshots());
  settled();
  ASSERT_EQ(state().input_snapshots().size(), 1u);
  EXPECT_EQ(state().input_snapshots().front(), snapshot);
  ASSERT_TRUE(state().verify_input_snapshot(id));
  settled();
  EXPECT_TRUE(state().input_verification().value("ok", false));
  const std::string hash = io::get_string(snapshot.at("manifest").at("files").front(), "sha256");
  std::filesystem::remove(core::path_from_utf8(dir.str() + "/project/.stk/objects/sha256/" + hash.substr(0, 2) + "/" + hash.substr(2)));
  ASSERT_TRUE(state().verify_input_snapshot(id));
  settled();
  EXPECT_FALSE(state().input_verification().value("ok", true));
  EXPECT_EQ(state().input_verification().at("files").front().at("state"), "missing");
  EXPECT_EQ(state().project()->revision, 4);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, DroppedFilesRegisterInCurrentProjectAndUndoRemovesOnlyTheIndex)
{
  populated();
  const std::string path = dir.str() + "/project/input.dat";
  { std::ofstream file(path); file << "1 2 3\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  auto context = area.context(nullptr, nullptr);
  ASSERT_TRUE(area.editor().on_drop({path}, context));
  settled();
  EXPECT_TRUE(state().selected_file());
  ASSERT_TRUE(state().undo());
  settled();
  EXPECT_TRUE(std::filesystem::exists(path));
  EXPECT_EQ(state().tables().size(), 1u);
  EXPECT_EQ(state().table_id(), table_id);
  EXPECT_TRUE(state().file_index().empty());
}

TEST_F(ProjectPython, FrozenRunTableLoadsWithoutExecutionAndTracksParameterChanges)
{
  populated();
  std::optional<bridge::Result<Json>> response;
  client->call("connections.add_runtime", {{"name", "offline"}, {"url", "http://127.0.0.1:1"},
                                            {"token", "test-only"}, {"check", false}})
      .then([&](auto result) { response = result; });
  ASSERT_TRUE(loop.pump_until([&] { return response.has_value(); }));
  ASSERT_TRUE(response->ok()) << response->error().message;
  response.reset();
  client->call("project.runs.prepare", {{"handle", state().project()->handle}, {"connection", "runtime:offline"},
      {"expected_revision", 1}, {"entries", Json::array({{
        {"table_id", table_id}, {"record_id", record_id}, {"label", "300 K"},
        {"spec", {{"workspace_id", std::string(32, 'a')}, {"argv", Json::array({"solver", "--temperature", "300"})}}}
      }})}}).then([&](auto result) { response = result; });
  ASSERT_TRUE(loop.pump_until([&] { return response.has_value() && !state().busy() && state().project()->revision == 2; }));
  ASSERT_TRUE(response->ok()) << response->error().message;
  const std::string run_id = response->value().at("run_ids").front();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto *panel = f.screen.ui()->find("a2/main/project_runs");
  ASSERT_NE(panel, nullptr);
  const auto [x, y] = f.widget_center("a2/main/project_runs");
  f.drv->click(x, y);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/project_runs/list"), nullptr);
  f.screen.ui()->find("a2/main/project_runs/list")->on_click();
  settled();
  f.drv->frame();
  ASSERT_EQ(state().runs().size(), 1u);
  EXPECT_EQ(state().run_id(), run_id);
  EXPECT_EQ(state().run().at("status").at("submission"), "prepared");
  EXPECT_EQ(state().run().at("parameter_state"), "current");
  EXPECT_TRUE(f.screen.ui()->find("a2/main/project_runs/submit")->enabled);
  EXPECT_FALSE(f.screen.ui()->find("a2/main/project_runs/cancel")->enabled);
  EXPECT_TRUE(state().error().empty());  // The saved endpoint is offline; list/get do not contact it.
  ASSERT_TRUE(state().apply(set_cell(400)));
  settled();
  state().sync();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().run().at("parameter_state"), "changed");
  EXPECT_EQ(state().run().at("plan").at("parameters").at("values").at(field_id), 300);
  EXPECT_FALSE(f.screen.ui()->find("a2/main/project_runs/submit")->enabled);
  ASSERT_NE(f.screen.ui()->find("a2/main/project_runs/allow_stale"), nullptr);
  EXPECT_FALSE(f.screen.ui()->find("a2/main/project_runs/allow_stale")->boolean.value());
  // Calling the controller directly still reaches the backend's independent stale-plan guard.
  ASSERT_TRUE(state().submit_run());
  settled();
  EXPECT_FALSE(state().error().empty());
  EXPECT_EQ(state().run().at("status").at("submission"), "prepared");
  ASSERT_TRUE(state().close());
  settled();
  EXPECT_TRUE(state().runs().empty());
  EXPECT_TRUE(state().run().empty());
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  ASSERT_TRUE(state().load_runs());
  settled();
  EXPECT_EQ(state().run_id(), run_id);
  EXPECT_EQ(state().project()->revision, 3);
  EXPECT_EQ(state().run().at("status").at("submission"), "prepared");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, RunButtonsSubmitRefreshAndCancelOneTaskWithoutChangingTableRevision)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  const std::string source = "import sys\nsys.path.insert(0, " + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/app").dump() +
      ")\nfrom run_peer import Peer\nfrom suan.desktop_bridge.connections import ConnectionStore\n"
      "peer = Peer()\nConnectionStore(" + Json(dir.str() + "/bridge").dump() + ").add_runtime('peer', peer.url, 'test-only', check=False)\n"
      "plan = stk.project.runs.prepare([{'table_id': " + Json(table_id).dump() + ", 'record_id': " + Json(record_id).dump() +
      ", 'spec': {'workspace_id': 'a' * 32, 'argv': ['solver']}}], connection='runtime:peer', expected_revision=1)\n"
      "assert peer.submit_count == 0";
  ASSERT_TRUE(scripts.execute(source));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy() && !state().busy(); }, 30))
      << scripts.status().dump() << "\n" << client->bridge_log().text();
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  ASSERT_TRUE(state().load_runs());
  settled();
  ASSERT_EQ(state().runs().size(), 1u) << state().error();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  settled();
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_runs");
  f.drv->click(x, y);
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_runs/" + key); };
  ASSERT_NE(widget("submit"), nullptr);
  ASSERT_TRUE(widget("submit")->enabled);
  widget("submit")->on_click();
  settled();
  state().sync();
  settled();
  f.drv->frame();
  ASSERT_EQ(state().run().at("status").at("submission"), "accepted") << state().error();
  EXPECT_EQ(state().run().at("status").at("task").at("state"), "queued");
  EXPECT_FALSE(widget("submit")->enabled);
  ASSERT_TRUE(widget("refresh")->enabled);
  widget("refresh")->on_click();
  settled();
  state().sync();
  settled();
  f.drv->frame();
  ASSERT_TRUE(widget("cancel")->enabled);
  widget("cancel")->on_click();
  settled();
  state().sync();
  settled();
  f.drv->frame();
  EXPECT_EQ(state().run().at("status").at("task").at("state"), "cancelled");
  EXPECT_FALSE(widget("cancel")->enabled);
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(state().table()->text(0, 0), "300");
  ASSERT_TRUE(scripts.execute("assert peer.submit_count == 1\nassert peer.cancel_count == 1\npeer.close()"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  EXPECT_EQ(scripts.status().at("run").at("state"), "succeeded");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, MuFerroImportButtonUsesTheSharedWorkflowAndBindsProjectIdentity)
{
  populated();
  const auto source = core::path_from_utf8(dir.str() + "/案例 case");
  std::filesystem::create_directories(source);
  { std::ofstream file(source / "input.toml");
    file << "material = 'material.toml'\n[system]\nsimulation_grid = [4,3,2]\n"
            "temperature = 298\ntimestep_total = 3\ndt = 0.01\n[output]\ninterval = 2\n"; }
  { std::ofstream file(source / "material.toml"); file << "[landau]\na1 = '3.8e5*(TEM-479)'\n"; }
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_simulation");
  f.drv->click(x, y);
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return scripts.ready() && !scripts.busy(); }, 30));
  f.drv->frame();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_simulation/" + key); };
  ASSERT_NE(widget("simulation_source"), nullptr);
  widget("simulation_source")->string.assign(core::path_to_utf8(source));
  f.drv->frame();
  ASSERT_TRUE(widget("simulation_import")->enabled);
  const auto import = widget("simulation_import")->on_click;
  import();
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy() && !state().busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  state().select_table("27e50c45-2d61-523c-a56b-f505bbd595c5");
  ASSERT_NE(state().table(), nullptr);
  EXPECT_EQ(state().table()->records.size(), 1u);
  EXPECT_EQ(state().table()->text(0, 1), "298");
  EXPECT_TRUE(state().runs().empty());
  // A callback from a previously displayed project cannot import into a new project.
  ASSERT_TRUE(state().create(dir.str() + "/other", "Other"));
  settled();
  import();
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy(); }, 30));
  EXPECT_EQ(scripts.status().at("run").at("state"), "failed");
  EXPECT_EQ(state().project()->revision, 0);
  EXPECT_TRUE(state().tables().empty());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

#ifdef __linux__
class SimulationPython : public ProjectPython {
 protected:
  void TearDown() override
  {
    auto &scripts = f.shell->store().scripts();
    loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy(); }, 30);
    if (scripts.ready() && !scripts.busy()) {
      scripts.execute("if '_simulation_runtime' in globals():\n    _simulation_runtime.close()");
      loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy(); }, 30);
    }
    ProjectPython::TearDown();
  }
};

TEST_F(SimulationPython, NativeMuFerroButtonsPrepareSubmitCollectViewAndReopenOffline)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  auto &jobs = f.shell->store().jobs();
  auto &viewer = f.shell->store().viewer();
  auto python_done = [&] {
    ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy() && !state().busy(); }, 60));
    std::string output;
    for (size_t i = 0; i < scripts.output().line_count(); ++i) { output += scripts.output().line(i); output += '\n'; }
    ASSERT_TRUE(scripts.error().empty()) << scripts.error();
    ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded") << output;
  };
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  ASSERT_TRUE(scripts.execute("import sys\nsys.path.insert(0, " + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/app").dump() +
      ")\nfrom simulation_fixture import SimulationRuntime\nfrom suan.desktop_bridge.connections import ConnectionStore\n"
      "_simulation_runtime = SimulationRuntime(" + Json(dir.str() + "/simulation-runtime").dump() + ")\n"
      "ConnectionStore(" + Json(dir.str() + "/bridge").dump() +
      ").add_runtime('simulation-test', _simulation_runtime.url, _simulation_runtime.config['token'], check=False)"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  jobs.sync();
  jobs.refresh_connections();
  ASSERT_TRUE(loop.pump_until([&] {
    return std::any_of(jobs.connections().begin(), jobs.connections().end(), [](const auto &item) { return item.info.id == "runtime:simulation-test"; });
  }, 30));
  jobs.select_connection("runtime:simulation-test");
  std::string source;
  { std::ifstream file(core::path_from_utf8(dir.str() + "/simulation-runtime/source.txt")); std::getline(file, source); }
  ASSERT_FALSE(source.empty());
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_simulation");
  f.drv->click(x, y);
  f.drv->frame();
  auto click = [&](const std::string &id) {
    ASSERT_TRUE(loop.pump_until([&] {
      f.screen.run_deferred();
      f.drv->frame();
      const auto *widget = f.screen.ui()->find("a2/main/" + id);
      return widget && widget->enabled;
    }, 30)) << id << " project busy=" << state().busy() << " script=" << scripts.status().dump()
            << " run=" << state().run().dump();
    const auto *widget = f.screen.ui()->find("a2/main/" + id);
    ASSERT_NE(widget, nullptr) << id;
    ASSERT_TRUE(widget->enabled) << id;
    widget->on_click();
  };
  auto *input = f.screen.ui()->find("a2/main/project_simulation/simulation_source");
  ASSERT_NE(input, nullptr);
  input->string.assign(source);
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_import"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  state().select_table("27e50c45-2d61-523c-a56b-f505bbd595c5");
  ASSERT_NE(state().table(), nullptr);
  ASSERT_EQ(state().table()->records.size(), 1u);
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_prepare"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  ASSERT_TRUE(state().load_runs());
  settled();
  ASSERT_EQ(state().runs().size(), 1u) << state().error();
  const auto run = state().run_id();
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_prepare"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  ASSERT_TRUE(scripts.execute("assert _simulation_runtime.client.tasks() == []\nassert len(stk.project.runs.list()['runs']) == 1"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  f.drv->frame();
  const auto [rx, ry] = f.widget_center("a2/main/project_runs");
  f.drv->click(rx, ry);
  ASSERT_NO_FATAL_FAILURE(click("project_runs/submit"));
  settled();
  ASSERT_TRUE(loop.pump_until([&] {
    if (state().busy()) { return false; }
    const auto status = state().run().value("status", Json::object());
    const auto task = status.value("task", Json::object());
    const auto phase = io::get_string(task, "state");
    if (phase == "succeeded" || phase == "failed" || phase == "cancelled") { return true; }
    state().refresh_run();
    return false;
  }, 90));
  ASSERT_EQ(state().run().at("status").at("task").at("state"), "succeeded") << state().run().dump();
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_logs"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_collect"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  state().select_table("04d7cc6c-5da5-5c92-a860-f3368f7b376d");
  ASSERT_NE(state().table(), nullptr);
  ASSERT_EQ(state().table()->records.size(), 1u);
  const double energy = state().table()->records[0].values.at("782e3845-2a32-5871-a1d6-d6d5b82451e1");
  const char *prefix = std::getenv("STK_TEST_MUPRO_PREFIX");
  EXPECT_NEAR(energy, prefix && *prefix ? -727.9144455 : -3.375, 1e-5);
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_collect"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  ASSERT_TRUE(scripts.execute("assert len(_simulation_runtime.client.tasks()) == 1\n_simulation_runtime.close()"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  // Close and reopen after the Runtime has stopped. The saved result still opens locally.
  ASSERT_TRUE(state().close());
  settled();
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  settled();
  ASSERT_TRUE(state().load_runs());
  settled();
  ASSERT_EQ(state().run_id(), run);
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); viewer.pump(); return viewer.presets_loaded() && scripts.desktop_ready(); }, 30));
  ASSERT_NO_FATAL_FAILURE(click("project_simulation/simulation_view"));
  ASSERT_NO_FATAL_FAILURE(python_done());
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); viewer.pump(); return bool(viewer.payload()) || !viewer.eval_error().empty(); }, 60));
  ASSERT_TRUE(viewer.payload()) << viewer.eval_error();
  EXPECT_FALSE(viewer.payload()->layers().empty());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}
TEST_F(SimulationPython, NativeBatchButtonsPersistAndSubmitEachMemberOnce)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  auto &jobs = f.shell->store().jobs();
  auto done = [&] {
    ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy() && !state().busy(); }, 90));
    std::string output;
    for (size_t i = 0; i < scripts.output().line_count(); ++i) { output += scripts.output().line(i); output += '\n'; }
    ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded") << output;
  };
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  ASSERT_TRUE(scripts.execute("import sys, time\nsys.path.insert(0, " + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/app").dump() +
      ")\nfrom simulation_fixture import SimulationRuntime\nfrom suan.desktop_bridge.connections import ConnectionStore\n"
      "_simulation_runtime = SimulationRuntime(" + Json(dir.str() + "/batch-runtime").dump() + ")\n"
      "ConnectionStore(" + Json(dir.str() + "/bridge").dump() +
      ").add_runtime('batch-test', _simulation_runtime.url, _simulation_runtime.config['token'], check=False)\n"
      "p = stk.project\nfirst = stk.muferro.import_case(_simulation_runtime.source, expected_revision=p.snapshot()['project']['revision'])['record_id']\n"
      "for _ in range(2):\n    stk.muferro.clone_case(first, expected_revision=p.snapshot()['project']['revision'])"));
  ASSERT_NO_FATAL_FAILURE(done());
  jobs.sync();
  jobs.refresh_connections();
  ASSERT_TRUE(loop.pump_until([&] {
    return std::any_of(jobs.connections().begin(), jobs.connections().end(), [](const auto &item) { return item.info.id == "runtime:batch-test"; });
  }, 30));
  jobs.select_connection("runtime:batch-test");
  state().select_table("27e50c45-2d61-523c-a56b-f505bbd595c5");
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_batches");
  f.drv->click(x, y);
  auto click = [&](const std::string &id) {
    ASSERT_TRUE(loop.pump_until([&] {
      f.screen.run_deferred(); f.drv->frame();
      const auto *widget = f.screen.ui()->find("a2/main/project_batches/" + id);
      return widget && widget->enabled;
    }, 30)) << id;
    f.screen.ui()->find("a2/main/project_batches/" + id)->on_click();
  };
  ASSERT_NO_FATAL_FAILURE(click("all"));
  ASSERT_NO_FATAL_FAILURE(click("create"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("create"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("from suan.workflows.batches import TABLE_ID as BT\nbatches = next(t for t in p.snapshot()['tables'] if t['id']==BT)\n"
      "assert len(batches['records'])==1\nbatch = batches['records'][0]['id']\nassert len(stk.batches.inspect(batch)['items'])==3"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_prepare"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_prepare"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("assert len(p.runs.list()['runs'])==3\nassert not _simulation_runtime.client.tasks()"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_submit"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_submit"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("assert len(_simulation_runtime.client.tasks())==3\ndeadline=time.monotonic()+60\n"
      "while any(t['state'] not in {'succeeded','failed','cancelled'} for t in _simulation_runtime.client.tasks()) and time.monotonic()<deadline:\n    time.sleep(.05)\n"
      "assert all(t['state']=='succeeded' for t in _simulation_runtime.client.tasks())"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_refresh"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("all_collect"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("assert all(i['last_operation']['ok'] and i['state']=='succeeded' for i in stk.batches.inspect(batch)['items'])\n_simulation_runtime.close()"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(state().close()); settled();
  ASSERT_TRUE(state().open(dir.str() + "/project")); settled();
  f.drv->frame();
  const auto *members = f.screen.ui()->find("a2/main/project_batches/members");
  ASSERT_NE(members, nullptr);
  ASSERT_TRUE(members->table);
  EXPECT_EQ(members->table->rows, 3);
  state().select_table("04d7cc6c-5da5-5c92-a860-f3368f7b376d");
  ASSERT_NE(state().table(), nullptr);
  EXPECT_EQ(state().table()->records.size(), 3u);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}
TEST_F(SimulationPython, RunSelectedRowsUsesThePickedRuntimeAndSubmitsEachRowOnce)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  auto &jobs = f.shell->store().jobs();
  auto done = [&] {
    ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy() && !state().busy(); }, 90));
    std::string output;
    for (size_t i = 0; i < scripts.output().line_count(); ++i) { output += scripts.output().line(i); output += '\n'; }
    ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded") << output;
  };
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  ASSERT_TRUE(scripts.execute("import sys, time\nsys.path.insert(0, " + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/app").dump() +
      ")\nfrom simulation_fixture import SimulationRuntime\nfrom suan.desktop_bridge.connections import ConnectionStore\n"
      "_simulation_runtime = SimulationRuntime(" + Json(dir.str() + "/run-runtime").dump() + ")\n"
      "ConnectionStore(" + Json(dir.str() + "/bridge").dump() +
      ").add_runtime('run-test', _simulation_runtime.url, _simulation_runtime.config['token'], check=False)\n"
      "p = stk.project\nfirst = stk.muferro.import_case(_simulation_runtime.source, expected_revision=p.snapshot()['project']['revision'])['record_id']\n"
      "for _ in range(2):\n    stk.muferro.clone_case(first, expected_revision=p.snapshot()['project']['revision'])"));
  ASSERT_NO_FATAL_FAILURE(done());
  jobs.sync();
  jobs.refresh_connections();
  ASSERT_TRUE(loop.pump_until([&] {
    return std::any_of(jobs.connections().begin(), jobs.connections().end(), [](const auto &item) { return item.info.id == "runtime:run-test"; });
  }, 30));
  ASSERT_TRUE(jobs.active_id().empty());
  state().select_table("27e50c45-2d61-523c-a56b-f505bbd595c5");
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_batches");
  f.drv->click(x, y);
  auto widget = [&](const std::string &id) {
    f.screen.run_deferred(); f.drv->frame();
    return f.screen.ui()->find("a2/main/project_batches/" + id);
  };
  auto click = [&](const std::string &id) {
    ASSERT_TRUE(loop.pump_until([&] { const auto *w = widget(id); return w && w->enabled; }, 30)) << id;
    widget(id)->on_click();
  };
  ASSERT_NO_FATAL_FAILURE(click("all"));
  ASSERT_NE(widget("runtime"), nullptr);
  EXPECT_FALSE(widget("run_selected")->enabled);  // No Runtime chosen yet.
  widget("runtime")->index.assign(0);  // Only saved direct/SSH Runtimes are offered.
  EXPECT_EQ(jobs.active_id(), "runtime:run-test");
  ASSERT_TRUE(loop.pump_until([&] { const auto *w = widget("run_selected"); return w && w->enabled; }, 30));
  EXPECT_EQ(widget("run_selected")->text, "Run 3 selected rows on run-test");
  // A cluster backend needs a time limit before anything can be run; the fields edit the same JSON.
  widget("backend")->index.assign(1);
  ASSERT_NE(widget("walltime"), nullptr);
  EXPECT_FALSE(widget("run_selected")->enabled);
  widget("backend")->index.assign(0);
  EXPECT_EQ(widget("walltime"), nullptr);
  widget("threads_per_rank")->number.assign(2);
  ASSERT_TRUE(widget("run_selected")->enabled);
  EXPECT_EQ(widget("threads_per_rank")->number.value(), 2);
  ASSERT_NO_FATAL_FAILURE(click("run_selected"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("from suan.workflows.batches import TABLE_ID as BT\nbatches = next(t for t in p.snapshot()['tables'] if t['id']==BT)\n"
      "assert len(batches['records'])==1\nbatch = batches['records'][0]['id']\nintent = stk.batches.inspect(batch)\n"
      "assert intent['connection']=='runtime:run-test'\n"
      "assert batches['records'][0]['values']['" + std::string("1c728eb5-5c6d-505d-bed4-914def1c4dac") + "']['options']=={'backend':'local','ranks':1,'threads_per_rank':2}\n"
      "assert len(_simulation_runtime.client.tasks())==3 and len(p.runs.list()['runs'])==3"));
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_NO_FATAL_FAILURE(click("run_selected"));  // Same rows and options: the same batch, plans and tasks.
  ASSERT_NO_FATAL_FAILURE(done());
  ASSERT_TRUE(scripts.execute("assert len(_simulation_runtime.client.tasks())==3 and len(p.runs.list()['runs'])==3\n"
      "deadline=time.monotonic()+60\n"
      "while any(t['state'] not in {'succeeded','failed','cancelled'} for t in _simulation_runtime.client.tasks()) and time.monotonic()<deadline:\n    time.sleep(.05)\n"
      "_simulation_runtime.close()"));
  ASSERT_NO_FATAL_FAILURE(done());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

class WorkflowSimulationPython : public SimulationPython {
 protected:
  void configure_bridge(bridge::ClientOptions &options, const std::string &) override
  {
    options.env["STK_WORKFLOW_POLL_SECONDS"] = "0.05";  // follow the loopback Runtime's tasks quickly
  }
};

TEST_F(WorkflowSimulationPython, MuFerroWorkflowRunsEveryRowOnThePickedRuntime)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  auto &jobs = f.shell->store().jobs();
  auto done = [&] {
    ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); return !scripts.busy() && !state().busy(); }, 90));
    std::string output;
    for (size_t i = 0; i < scripts.output().line_count(); ++i) { output += scripts.output().line(i); output += '\n'; }
    ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded") << output;
  };
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  // Three MuFerro case rows and a workflow cases -> MuFerro on a loopback Runtime with the synthetic solver.
  ASSERT_TRUE(scripts.execute("import sys, time, uuid\nsys.path.insert(0, " + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/app").dump() +
      ")\nfrom simulation_fixture import SimulationRuntime\nfrom suan.desktop_bridge.connections import ConnectionStore\n"
      "from suan.workflows.muferro import TABLE_ID, RESULT_TABLE_ID\n"
      "_simulation_runtime = SimulationRuntime(" + Json(dir.str() + "/workflow-runtime").dump() + ")\n"
      "ConnectionStore(" + Json(dir.str() + "/bridge").dump() +
      ").add_runtime('run-test', _simulation_runtime.url, _simulation_runtime.config['token'], check=False)\n"
      "p = stk.project\nfirst = stk.muferro.import_case(_simulation_runtime.source, expected_revision=p.snapshot()['project']['revision'])['record_id']\n"
      "for _ in range(2):\n    stk.muferro.clone_case(first, expected_revision=p.snapshot()['project']['revision'])\n"
      "p.workflows.create('MuFerro scan', {'format': 'stk.workflow/1', 'ui': {}, 'steps': ["
      "{'id': 'cases', 'kind': 'table', 'ref': {'table': TABLE_ID}}, {'id': 'simulate', 'kind': 'simulation', "
      "'ref': {'template': 'muferro/1'}, 'inputs': {'rows': {'from': 'cases.rows'}}}]}, workflow_id=str(uuid.uuid4()), "
      "expected_revision=p.snapshot()['project']['revision'])"));
  ASSERT_NO_FATAL_FAILURE(done());
  jobs.sync();
  jobs.refresh_connections();
  ASSERT_TRUE(loop.pump_until([&] {
    return std::any_of(jobs.connections().begin(), jobs.connections().end(), [](const auto &item) { return item.info.id == "runtime:run-test"; });
  }, 30));
  state().refresh();
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }, 30));
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorWorkflow));
  f.screen.set_maximized(&area);
  area.find_region(EditorArea::kSidebar)->set_size_1x(560);
  auto widget = [&](const std::string &id) { f.screen.run_deferred(); f.drv->frame(); return f.screen.ui()->find(id); };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  ASSERT_TRUE(loop.pump_until([&] { const auto *w = widget("workflow_run_start"); return w && shows("All references and links are valid."); }, 60));
  // A MuFerro step needs a Runtime: nothing can be run until one is picked here.
  EXPECT_FALSE(widget("workflow_run_start")->enabled);
  EXPECT_TRUE(shows("Choose an available Runtime connection"));
  ASSERT_NE(widget("workflow_run_panel/runtime"), nullptr);
  widget("workflow_run_panel/runtime")->index.assign(0);
  EXPECT_EQ(jobs.active_id(), "runtime:run-test");
  ASSERT_TRUE(loop.pump_until([&] { const auto *w = widget("workflow_run_start"); return w && w->enabled; }, 30));
  EXPECT_EQ(widget("workflow_run_start")->text, "Run the 3 selected rows on run-test");
  widget("workflow_run_start")->on_click();
  // Every row is submitted, followed and collected by the service; the panel follows the run.
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return shows("All done · 3/3 done"); }, 120));
  const auto *grid = widget("workflow_run_tasks");
  ASSERT_NE(grid, nullptr); ASSERT_EQ(grid->table->rows, 3);
  grid->table->selected.assign(0);
  f.drv->frame();
  EXPECT_TRUE(shows("simulate: simulation run "));  // the row's simulation run and Runtime task
  EXPECT_TRUE(shows(" · Done"));
  // P2 L3: the run's MuFerro result rows become a new conversation context and the AI assistant opens on it.
  ASSERT_NE(widget("workflow_run_ask_results"), nullptr);
  EXPECT_EQ(widget("workflow_run_ask_results")->text, "Ask about the results of these 3 rows");
  auto &discussion = state().discussion();
  widget("workflow_run_ask_results")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    auto *maximized = dynamic_cast<EditorArea *>(f.screen.maximized());
    return !discussion.busy() && maximized && maximized->editor().type().id == kEditorAI && !discussion.context().empty();
  }, 30));
  const auto context = discussion.context();
  EXPECT_EQ(context.at("title"), "Results of MuFerro scan (3 rows)");
  EXPECT_EQ(context.at("selection").at("record_ids").size(), 3u);
  EXPECT_EQ(context.at("selection").at("field_ids").size(), 3u);  // temperature, final step, energy
  ASSERT_TRUE(scripts.execute("assert len(_simulation_runtime.client.tasks()) == 3, _simulation_runtime.client.tasks()\n"
      "results = next(t for t in p.snapshot()['tables'] if t['id'] == RESULT_TABLE_ID)\nassert len(results['records']) == 3\n"
      "run = p.workflow_runs.list()['runs'][0]\nassert p.workflow_runs.get(run['id'])['simulation']['connection'] == 'runtime:run-test'\n"
      "_simulation_runtime.close()"));
  ASSERT_NO_FATAL_FAILURE(done());
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

#endif


/** Pumps frames until `condition` holds (archive reads finish on their own, outside the project's busy flag). */
#define STK_UNTIL(condition) \
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return (condition); }, 30)) << client->bridge_log().text()

TEST_F(ProjectPython, ArchivedDraftsLeaveTheSavedListAndApplyOnlyAsCopies)
{
  populated();
  state().set_review_source(set_cell(350).dump());
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().save_review("Kept for later")); settled();
  state().discard_review();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("review"));
  f.screen.set_maximized(&area); f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/saved_reviews");
  f.drv->click(x, y);
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/saved_reviews/" + key); };
  STK_UNTIL(widget("draft_rows") && widget("draft_archive") && widget("draft_archive")->enabled);
  EXPECT_TRUE(widget("load_draft")->enabled);
  EXPECT_EQ(widget("drafts_show_archived"), nullptr);
  widget("draft_archive")->on_click();
  STK_UNTIL(!widget("draft_rows") && widget("drafts_show_archived"));
  EXPECT_EQ(widget("drafts_show_archived")->text, "Show archived (1)");
  widget("drafts_show_archived")->boolean.assign(true);
  // Only archived drafts. One can be loaded to look at but is neither discarded nor applied as it is; a copy can be.
  STK_UNTIL(widget("draft_rows") && widget("draft_archive") && widget("draft_archive")->text == "Restore" &&
            widget("draft_archive")->enabled && widget("load_draft")->enabled);
  EXPECT_FALSE(widget("discard_saved_draft")->enabled);
  EXPECT_EQ(state().project()->revision, 1);  // archiving is not an edit
  widget("load_draft")->on_click();
  auto page = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  STK_UNTIL(!state().saved_review().empty() && !state().busy() && page("review_copy_saved") && page("review_copy_saved")->enabled);
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  EXPECT_TRUE(shows("Archived: it is not applied or discarded as it is."));
  page("review_copy_saved")->on_click();
  STK_UNTIL(state().saved_review().empty() && !state().busy() && page("review_apply") && page("review_apply")->enabled);
  page("review_apply")->on_click();
  STK_UNTIL(!state().busy() && state().project()->revision == 2);
  EXPECT_EQ(state().table()->text(0, 0), "350");
  // The archived draft itself is unchanged; restored, it is listed again.
  STK_UNTIL(widget("draft_rows") && widget("draft_archive") && widget("draft_archive")->enabled);
  widget("draft_archive")->on_click();
  STK_UNTIL(!widget("draft_rows"));
  widget("drafts_show_archived")->boolean.assign(false);
  STK_UNTIL(widget("draft_rows") && widget("load_draft") && widget("load_draft")->enabled && !widget("drafts_show_archived"));
  EXPECT_EQ(state().drafts().at(0).at("status"), "pending");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ArchivedQuestionsLeaveTheAIHistoryAndArchivedContextsCanStillBeAsked)
{
  populated();
  const std::string first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  ASSERT_NO_FATAL_FAILURE(saved_request(first));
  ASSERT_NO_FATAL_FAILURE(saved_request(second));
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &discussion = state().discussion();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  ASSERT_NE(widget("ai_history"), nullptr);
  EXPECT_EQ(widget("ai_history")->items.size(), 2u);
  ASSERT_TRUE(discussion.load_exchange(first)); ai_frame();
  STK_UNTIL(widget("ai_archive") && widget("ai_archive")->enabled);
  widget("ai_archive")->on_click();
  // The shown question stays, marked as not to be sent; the history leaves it out until switched to archived ones.
  STK_UNTIL(widget("ai_history") && widget("ai_history")->items.size() == 1 && shows("Archived: this question is not sent."));
  EXPECT_FALSE(widget("ai_send_saved")->enabled);
  EXPECT_EQ(discussion.page("requests").items.front().at("id"), second);
  EXPECT_EQ(widget("ai_archive")->text, "Restore");
  ASSERT_NE(widget("ai_history_show_archived"), nullptr);
  widget("ai_history_show_archived")->boolean.assign(true);
  STK_UNTIL(discussion.page("requests").loaded && !discussion.busy() && discussion.page("requests").items.size() == 1 &&
            discussion.page("requests").items.front().at("id") == first);
  widget("ai_history_show_archived")->boolean.assign(false);
  STK_UNTIL(discussion.page("requests").loaded && !discussion.busy() && discussion.page("requests").items.size() == 1 &&
            discussion.page("requests").items.front().at("id") == second);
  // An archived context can still be asked about: a new message and question are new objects.
  const auto context = io::get_string(discussion.context(), "id");
  ASSERT_FALSE(context.empty());
  ASSERT_TRUE(f.shell->store().archive().set("context", {context}, true));
  STK_UNTIL(f.shell->store().archive().archived("context", context) && !f.shell->store().archive().busy() &&
            !discussion.busy() && !state().busy());
  ASSERT_TRUE(discussion.add_message("A follow-up about the archived context")); settled();
  EXPECT_TRUE(discussion.error().empty()) << discussion.error();
  ASSERT_NO_FATAL_FAILURE(saved_request("cccccccc-cccc-4ccc-8ccc-cccccccccccc"));
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ArchivedSimulationRunsLeaveTheRunListAndCannotBeSubmitted)
{
  populated();
  std::optional<bridge::Result<Json>> response;
  client->call("connections.add_runtime", {{"name", "offline"}, {"url", "http://127.0.0.1:1"},
                                            {"token", "test-only"}, {"check", false}})
      .then([&](auto result) { response = result; });
  ASSERT_TRUE(loop.pump_until([&] { return response.has_value(); }));
  ASSERT_TRUE(response->ok()) << response->error().message;
  response.reset();
  client->call("project.runs.prepare", {{"handle", state().project()->handle}, {"connection", "runtime:offline"},
      {"expected_revision", 1}, {"entries", Json::array({{
        {"table_id", table_id}, {"record_id", record_id}, {"label", "300 K"},
        {"spec", {{"workspace_id", std::string(32, 'a')}, {"argv", Json::array({"solver", "--temperature", "300"})}}}
      }})}}).then([&](auto result) { response = result; });
  ASSERT_TRUE(loop.pump_until([&] { return response.has_value(); }));
  ASSERT_TRUE(response->ok()) << response->error().message;
  state().refresh(); settled();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_runs");
  f.drv->click(x, y);
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_runs/" + key); };
  STK_UNTIL(widget("list") && widget("list")->enabled);
  widget("list")->on_click();
  STK_UNTIL(state().runs().size() == 1 && widget("archive") && widget("archive")->enabled && widget("submit")->enabled);
  const auto revision = state().project()->revision;
  widget("archive")->on_click();
  STK_UNTIL(state().runs().empty() && !state().busy() && widget("runs_show_archived"));
  widget("runs_show_archived")->boolean.assign(true);
  STK_UNTIL(state().runs().size() == 1 && !state().busy() && widget("archive") && widget("archive")->text == "Restore");
  EXPECT_FALSE(widget("submit")->enabled);
  STK_UNTIL(widget("archive")->enabled);
  widget("archive")->on_click();
  STK_UNTIL(state().runs().empty() && !state().busy());
  widget("runs_show_archived")->boolean.assign(false);
  STK_UNTIL(state().runs().size() == 1 && !state().busy() && widget("submit") && widget("submit")->enabled);
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ArchivedBatchesLeaveTheSavedBatchesUntilRestored)
{
  populated();
  // A saved batch is a row of the batches table (suan/workflows/batches.py); only its name is read here.
  const std::string batches = "9ab21772-9bc4-56ab-94e1-f3f1049fb398", name = "4c8c8e0b-e625-54b9-aa39-cfbddef20d7c";
  const std::string kept = "44444444-4444-4444-8444-444444444444", shelved = "55555555-5555-4555-8555-555555555555";
  ASSERT_TRUE(state().apply(Json::array({
      {{"op", "create_table"}, {"id", batches}, {"name", "Simulation batches"}},
      {{"op", "add_field"}, {"table_id", batches}, {"id", name}, {"name", "Name"}, {"type", "text"}},
      {{"op", "add_record"}, {"table_id", batches}, {"id", kept}},
      {{"op", "set_cell"}, {"table_id", batches}, {"record_id", kept}, {"field_id", name}, {"value", "Kept batch"}},
      {{"op", "add_record"}, {"table_id", batches}, {"id", shelved}},
      {{"op", "set_cell"}, {"table_id", batches}, {"record_id", shelved}, {"field_id", name}, {"value", "Old batch"}}})));
  settled();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/project_batches");
  f.drv->click(x, y);
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/project_batches/" + key); };
  // The last batch is shown first.
  STK_UNTIL(widget("saved") && widget("saved")->items.size() == 2 && widget("batch_archive") && widget("batch_archive")->enabled);
  ASSERT_EQ(widget("saved")->index.value(), 1);
  widget("batch_archive")->on_click();
  STK_UNTIL(widget("saved") && widget("saved")->items.size() == 1 && widget("batches_show_archived"));
  EXPECT_EQ(widget("saved")->items.front(), "Kept batch");
  widget("batches_show_archived")->boolean.assign(true);
  STK_UNTIL(widget("saved")->items.size() == 1 && widget("saved")->items.front() == "Old batch" &&
            widget("batch_archive") && widget("batch_archive")->text == "Restore" && widget("batch_archive")->enabled);
  widget("batch_archive")->on_click();
  STK_UNTIL(widget("saved") && widget("saved")->items.empty());
  widget("batches_show_archived")->boolean.assign(false);
  STK_UNTIL(widget("saved") && widget("saved")->items.size() == 2 && !widget("batches_show_archived"));
  EXPECT_EQ(state().project()->revision, 2);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, ArchivedContextsLeaveTheDiscussionListAndStillTakeMessages)
{
  populated();
  ASSERT_NO_FATAL_FAILURE(saved_request("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"));
  auto &discussion = state().discussion();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("discussion")); f.screen.set_maximized(&area);
  const auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  STK_UNTIL(discussion.page("contexts").loaded && !discussion.busy() && discussion.page("contexts").items.size() == 1 &&
            widget("discussion_context_archive") && widget("discussion_context_archive")->enabled);
  widget("message_composer/text")->string.assign("A note about these values");
  STK_UNTIL(widget("message_composer/save_message") && widget("message_composer/save_message")->enabled);
  widget("discussion_context_archive")->on_click();
  // The shown context stays and can still be discussed: a message is a new object, the context itself never changes.
  STK_UNTIL(discussion.page("contexts").loaded && !discussion.busy() && discussion.page("contexts").items.empty() &&
            widget("discussion_show_archived/contexts") && widget("discussion_context_archive")->text == "Restore");
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  EXPECT_TRUE(shows("Archived: it still can be asked about"));
  ASSERT_TRUE(widget("message_composer/save_message")->enabled);
  widget("message_composer/save_message")->on_click();
  STK_UNTIL(!discussion.busy() && discussion.error().empty() &&
            io::get_string(discussion.message(), "text") == "A note about these values");
  widget("discussion_show_archived/contexts")->boolean.assign(true);
  STK_UNTIL(discussion.page("contexts").loaded && !discussion.busy() && discussion.page("contexts").items.size() == 1 &&
            widget("discussion_context_archive")->enabled);
  widget("discussion_context_archive")->on_click();
  STK_UNTIL(discussion.page("contexts").loaded && !discussion.busy() && discussion.page("contexts").items.empty() &&
            widget("discussion_context_archive")->text == "Archive");
  widget("discussion_show_archived/contexts")->boolean.assign(false);
  STK_UNTIL(discussion.page("contexts").loaded && !discussion.busy() && discussion.page("contexts").items.size() == 1 &&
            widget("message_composer/save_message")->enabled);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, TablesArePrivateUntilLabelledPublicOnTheDataPage)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  auto &labels = f.shell->store().data_labels();
  // Format 13: private, structure public (names, fields, units and row counts only) or public.
  STK_UNTIL(widget("table_label") && widget("table_label")->enabled);
  EXPECT_EQ(widget("table_label")->index.value(), 0);
  widget("table_label")->index.assign(2);
  STK_UNTIL(labels.is_public("table", table_id) && !labels.busy());
  std::optional<bridge::Result<Json>> listed;
  client->call("project.labels.list", {{"handle", state().project()->handle}}).then([&](auto value) { listed = value; });
  ASSERT_TRUE(loop.pump_until([&] { return listed.has_value(); }));
  ASSERT_TRUE(listed->ok());
  ASSERT_EQ(listed->value().at("items").size(), 1u);
  EXPECT_EQ(listed->value().at("items")[0].at("id"), table_id);
  widget("table_label")->index.assign(1);
  STK_UNTIL(labels.label("table", table_id) == "structure" && !labels.busy());
  EXPECT_FALSE(labels.is_public("table", table_id));  // its values stay private
  STK_UNTIL(widget("table_label") && widget("table_label")->index.value() == 1);
  widget("table_label")->index.assign(0);
  STK_UNTIL(labels.label("table", table_id) == "private" && !labels.busy());
  EXPECT_EQ(state().project()->revision, 1);  // labelling is not an edit
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, AFormat12ProjectKeepsThePublicCheckbox)
{
  populated();
  auto &scripts = f.shell->store().scripts();
  ASSERT_TRUE(loop.pump_until([&] { return scripts.ready() && !scripts.busy(); }, 30));
  // Format 12: no agent sessions, labels are public or private only.
  ASSERT_TRUE(scripts.execute("import sqlite3\nwith sqlite3.connect(" + Json(dir.str() + "/project/project.sqlite3").dump() +
      ") as db:\n    for table in ('project_agent_objects', 'project_agent_events', 'project_agent_sessions'):\n"
      "        db.execute('DROP TABLE ' + table)\n    db.execute('PRAGMA user_version=12')"));
  ASSERT_TRUE(loop.pump_until([&] { return !scripts.busy(); }, 30));
  ASSERT_EQ(scripts.status().at("run").at("state"), "succeeded");
  state().refresh(); settled();
  ASSERT_EQ(state().project()->format_version, 12);
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.screen.set_maximized(&area);
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  STK_UNTIL(widget("table_public") && widget("table_public")->enabled);
  EXPECT_EQ(widget("table_label"), nullptr);
  EXPECT_FALSE(f.shell->store().data_labels().structure_supported());
  widget("table_public")->boolean.assign(true);
  STK_UNTIL(f.shell->store().data_labels().is_public("table", table_id) && !f.shell->store().data_labels().busy());
  EXPECT_FALSE(state().agent().supported());  // no agent purpose in a format-12 project
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(ProjectPython, AIQuestionsGoToTheChosenEndpointAndPrivateDataStaysOffExternalOnes)
{
  populated();
  ASSERT_NO_FATAL_FAILURE(saved_request("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"));  // its context and question
  const std::string token_plan = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";  // the same question to the built-in (external) Token Plan
  std::optional<bridge::Result<Json>> created;
  client->call("project.requests.create", {{"handle", state().project()->handle}, {"request_id", token_plan},
      {"message_id", state().discussion().message().at("id")},
      {"configuration", {{"adapter", "aliyun-token-plan/1"}, {"model", "fixture-v1"}}}}).then([&](auto value) { created = value; });
  ASSERT_TRUE(loop.pump_until([&] { return created.has_value(); }));
  ASSERT_TRUE(created->ok()) << created->error().describe();
  std::optional<bridge::Result<Json>> keyed;
  client->call("ai.credentials.set", {{"key", "abcdefghijklmnopqrstu"}}).then([&](auto value) { keyed = value; });
  ASSERT_TRUE(loop.pump_until([&] { return keyed.has_value(); }));
  ASSERT_TRUE(keyed->ok());
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &discussion = state().discussion();
  auto &models = f.shell->store().models();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  ASSERT_TRUE(discussion.load_exchange(token_plan)); ai_frame();
  // The Token Plan is external and the table is private: the saved question is not sent, and the reason is shown.
  STK_UNTIL(models.loaded() && widget("ai_endpoint") && shows("This question's data is private"));
  EXPECT_FALSE(widget("ai_send_saved")->enabled);
  ASSERT_TRUE(f.shell->store().data_labels().set("table", {table_id}, true));
  STK_UNTIL(!shows("This question's data is private") && widget("ai_send_saved") && widget("ai_send_saved")->enabled);
  // The network setting is checked too.
  ASSERT_TRUE(models.set_network("offline"));
  STK_UNTIL(!models.busy() && models.network() == "offline" && shows("The network setting does not allow this question's endpoint."));
  EXPECT_FALSE(widget("ai_send_saved")->enabled);
  // An endpoint on this computer is added from the settings and chosen; the next question goes to it.
  ASSERT_TRUE(models.add_endpoint("laptop", "Laptop llama.cpp", "http://127.0.0.1:9/v1", {"qwen2.5-7b-instruct"}, ""));
  STK_UNTIL(!models.busy() && models.endpoint("laptop") != nullptr);
  ASSERT_EQ(io::get_string(*models.endpoint("laptop"), "location"), "local");
  ASSERT_NE(widget("ai_endpoint"), nullptr);
  const auto &items = widget("ai_endpoint")->items;
  const auto found = std::find_if(items.begin(), items.end(), [](const auto &item) { return item.find("Laptop llama.cpp") != std::string::npos; });
  ASSERT_NE(found, items.end());
  EXPECT_NE(found->find("this computer"), std::string::npos);
  widget("ai_endpoint")->index.assign(int(found - items.begin()));
  STK_UNTIL(widget("ai_endpoint_model") && widget("ai_endpoint_model")->items.size() == 1);
  widget(std::string("ai_question/") + state().project()->handle)->string.assign("Explain the temperature.");
  STK_UNTIL(widget("ai_prepare") && widget("ai_prepare")->enabled);
  widget("ai_prepare")->on_click();
  STK_UNTIL(!discussion.exchange_request().empty() && !discussion.exchange_busy() &&
            io::get_string(discussion.exchange_request().at("configuration"), "adapter") == "openai-compatible/1:laptop");
  EXPECT_EQ(io::get_string(discussion.exchange_request().at("configuration"), "model"), "qwen2.5-7b-instruct");
  // A local endpoint takes private data and is allowed offline: its saved question may be sent.
  ASSERT_TRUE(f.shell->store().data_labels().set("table", {table_id}, false));
  STK_UNTIL(!f.shell->store().data_labels().busy() && widget("ai_send_saved") && widget("ai_send_saved")->enabled);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

class LocalModelsPython : public ProjectPython {
 protected:
  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    options.command = {python, std::string(STK_REPO_ROOT) + "/desktop/tests/bridge/local_models_bridge.py",
        dir.str(), "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
  }
};

TEST_F(LocalModelsPython, AutomaticQuestionsFallBackFromAnUnreachableModelAndStartALocalOne)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &models = f.shell->store().models();
  auto &discussion = state().discussion();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Automatic scope")); settled();
  STK_UNTIL(models.loaded() && models.route_supported());
  // Private data and only the Token Plan (external): Automatic has no model, says why, and nothing can be prepared.
  widget("ai_question/" + state().project()->handle)->string.assign("Why do domains form?");
  const auto texts = [&] {
    std::string all;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (!item.text.empty()) { all += item.text + " | "; } }
    }
    return all;
  };
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame();
    return shows("No model can answer this question") && shows("This question's data is private"); }, 30)) << texts();
  EXPECT_FALSE(widget("ai_prepare")->enabled);
  // A model installed on this computer (not started) and an endpoint here that cannot be reached.
  ASSERT_TRUE(models.local_action("install", "tiny-q4"));
  const auto installed = [&] {
    for (const auto &item : models.local().value("installed", Json::array())) {
      if (io::get_string(item, "id") == "tiny-q4") { return true; }
    }
    return false;
  };
  STK_UNTIL(!models.busy() && installed());
  ASSERT_TRUE(models.add_endpoint("a-gone", "A gone", "http://127.0.0.1:9/v1", {"m"}, ""));
  STK_UNTIL(!models.busy() && models.endpoint("a-gone") != nullptr);
  // A question takes the nearest ready model first: the unreachable one, then the local model that must be started.
  STK_UNTIL(shows("Automatic: A gone") && widget("ai_prepare") && widget("ai_prepare")->enabled);
  widget("ai_prepare")->on_click();
  STK_UNTIL(io::get_string(discussion.exchange_request().value("configuration", Json::object()), "adapter") ==
                "openai-compatible/1:a-gone" && widget("ai_send_saved") && widget("ai_send_saved")->enabled);
  const std::string first = discussion.exchange_request().at("id");
  widget("ai_send_saved")->on_click();
  // Nothing reached "A gone" (refused before sending): the question goes to the next candidate as a new request,
  // whose model STK starts first.
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    return io::get_string(discussion.exchange_request().value("configuration", Json::object()), "adapter") ==
               "openai-compatible/1:local-tiny-q4" && io::get_string(discussion.exchange_request(), "status") == "completed"; }, 60))
      << discussion.exchange_request().dump() << "\n" << models.local().dump() << "\n" << client->bridge_log().text();
  EXPECT_NE(discussion.exchange_request().at("id"), first);
  EXPECT_EQ(io::get_string(discussion.exchange_reply(), "text"), "Domain walls move under the applied field.");
  EXPECT_TRUE(shows("A gone could not be reached or refused the question; asking Tiny chat instead."));
  // The attempt that never reached anything stays recorded as failed (not uncertain).
  std::optional<bridge::Result<Json>> earlier;
  client->call("project.requests.get", {{"handle", state().project()->handle}, {"request_id", first}})
      .then([&](auto value) { earlier = value; });
  ASSERT_TRUE(loop.pump_until([&] { return earlier.has_value(); }));
  ASSERT_TRUE(earlier->ok()) << earlier->error().describe();
  EXPECT_EQ(io::get_string(earlier->value().at("request"), "status"), "failed");
  EXPECT_EQ(io::get_string(earlier->value().at("request"), "error_code"), "adapter_failed");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(LocalModelsPython, AnAutomaticQuestionWhoseLocalModelCannotStartGoesToTheNextOne)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &models = f.shell->store().models();
  auto &discussion = state().discussion();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  const auto installed = [&](const std::string &entry) {
    const auto &local = models.local();
    if (!local.is_object()) { return false; }
    for (const auto &item : local.value("installed", Json::array())) {
      if (io::get_string(item, "id") == entry) { return true; }
    }
    return false;
  };
  ASSERT_TRUE(discussion.capture(table_id, {record_id}, {field_id}, "Start scope")); settled();
  STK_UNTIL(models.loaded() && models.local_supported());
  // Two models on this computer, neither running; "Broken chat" ranks first (same tier, by name) but its server exits.
  ASSERT_TRUE(models.local_action("install", "broken-q4"));
  STK_UNTIL(!models.busy() && installed("broken-q4"));
  ASSERT_TRUE(models.local_action("install", "tiny-q4"));
  STK_UNTIL(!models.busy() && installed("tiny-q4"));
  widget("ai_question/" + state().project()->handle)->string.assign("Why do domains form?");
  STK_UNTIL(shows("Automatic: Broken chat") && shows("STK starts it when the question is sent") &&
            widget("ai_prepare") && widget("ai_prepare")->enabled);
  widget("ai_prepare")->on_click();
  STK_UNTIL(io::get_string(discussion.exchange_request().value("configuration", Json::object()), "model") == "broken-q4" &&
            widget("ai_send_saved") && widget("ai_send_saved")->enabled);
  widget("ai_send_saved")->on_click();
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    return io::get_string(discussion.exchange_request().value("configuration", Json::object()), "model") == "tiny-q4" &&
           io::get_string(discussion.exchange_request(), "status") == "completed"; }, 60))
      << discussion.exchange_request().dump() << "\n" << models.local().dump() << "\n" << client->bridge_log().text();
  EXPECT_TRUE(shows("Broken chat could not be started; asking Tiny chat instead."));
  EXPECT_EQ(io::get_string(discussion.exchange_reply(), "text"), "Domain walls move under the applied field.");
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(LocalModelsPython, AModelIsInstalledStartedAndOfferedAsALocalEndpointFromTheAssistant)
{
  populated();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  ai_frame();
  auto &models = f.shell->store().models();
  auto widget = [&](const std::string &key) { return f.screen.ui()->find("a2/main/" + key); };
  const auto open = [&](const std::string &key) {
    STK_UNTIL(widget(key) != nullptr);
    const auto [x, y] = f.widget_center("a2/main/" + key);
    f.drv->click(x, y);
    f.drv->frame();
  };
  const auto shows = [&](const std::string &text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  };
  STK_UNTIL(models.loaded() && models.local_supported());
  ASSERT_NO_FATAL_FAILURE(open("ai_model_settings"));
  ASSERT_NO_FATAL_FAILURE(open("ai_model_settings/ai_local_models"));
  // The catalog entry fits (it needs almost nothing) and is recommended; the hardware is summarized.
  STK_UNTIL(!models.recommendations().is_null() && shows("recommended") && shows("This computer:") && shows("GB free disk"));
  const std::string scope = "ai_model_settings/ai_local_models/";
  STK_UNTIL(widget(scope + "ai_local_install/tiny-q4") && widget(scope + "ai_local_install/tiny-q4")->enabled);
  widget(scope + "ai_local_install/tiny-q4")->on_click();
  STK_UNTIL(widget(scope + "ai_local_start/tiny-q4") && widget(scope + "ai_local_start/tiny-q4")->enabled);
  widget(scope + "ai_local_start/tiny-q4")->on_click();
  // On failure, say why: the service's view of the server and the server's own log.
  const auto server_report = [&] {
    std::ifstream log(dir.str() + "/bridge/models/local/logs/tiny-q4.log");
    const std::string text((std::istreambuf_iterator<char>(log)), std::istreambuf_iterator<char>());
    const auto *progress = models.progress("tiny-q4");
    return "local: " + models.local().dump() + "\nprogress: " + (progress ? progress->dump() : std::string("none")) +
           "\nserver log: " + text + "\n" + client->bridge_log().text();
  };
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    return models.endpoint("local-tiny-q4") != nullptr && widget(scope + "ai_local_stop/tiny-q4") != nullptr; }, 60))
      << server_report();
  EXPECT_EQ(io::get_string(*models.endpoint("local-tiny-q4"), "location"), "local");
  // STK manages its key, and the endpoint is removed with the model, not on its own.
  EXPECT_TRUE(io::get_bool(*models.endpoint("local-tiny-q4"), "managed", false));
  STK_UNTIL(widget("ai_model_settings/ai_endpoint_remove/local-tiny-q4") != nullptr);
  EXPECT_FALSE(widget("ai_model_settings/ai_endpoint_remove/local-tiny-q4")->enabled);
  // The assistant offers it like any other endpoint. (The endpoint list and the local list are read separately: wait
  // for the panel to catch up rather than expecting both in the same frame.)
  const auto offered = [&] {
    const auto *endpoints = widget("ai_endpoint");
    return endpoints && std::any_of(endpoints->items.begin(), endpoints->items.end(), [](const auto &item) {
      return item.find("Tiny chat") != std::string::npos && item.find("this computer") != std::string::npos; });
  };
  STK_UNTIL(offered() && shows("Running"));
  widget(scope + "ai_local_stop/tiny-q4")->on_click();
  STK_UNTIL(widget(scope + "ai_local_start/tiny-q4") && widget(scope + "ai_local_start/tiny-q4")->enabled &&
            shows("Installed, not running"));
  // Removing deletes the files and the endpoint.
  widget(scope + "ai_local_remove/tiny-q4")->on_click();
  STK_UNTIL(models.endpoint("local-tiny-q4") == nullptr && widget(scope + "ai_local_install/tiny-q4") != nullptr);
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

/** Agent sessions (S2b, docs/design/agent-harness.md) with a real service whose model is scripted
 * (desktop/tests/bridge/agent_bridge.py): it outlines, captures the rows, proposes a sweep of three new rows. */
class AgentPython : public ProjectPython {
 protected:
  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    std::filesystem::create_directories(dir.str() + "/agent-control");
    options.command = {python, std::string(STK_REPO_ROOT) + "/desktop/tests/bridge/agent_bridge.py", dir.str() + "/agent-control",
        "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
  }

  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find("a2/main/" + key); }

  std::string timeline()
  {
    std::string shown;
    if (const auto *log = widget("ai_agent_timeline"); log && log->log) {
      for (size_t i = 0; i < log->log->line_count(); ++i) { shown += std::string(log->log->line(i)) + "\n"; }
    }
    return shown;
  }

  /** Open the AI assistant on the agent purpose and ask; the session waits for the person when it returns. */
  void ask_agent(const std::string &text)
  {
    populated();
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
    f.screen.set_maximized(&area);
    const auto handle = state().project()->handle;
    STK_UNTIL(widget("ai_intent/" + handle) != nullptr && state().agent().supported());
    f.screen.ui()->find("a2/main/ai_intent/" + handle)->index.assign(3);
    STK_UNTIL(state().agent().route_loaded() && widget("ai_agent_text/" + handle) != nullptr);
    EXPECT_EQ(io::get_string(state().agent().route().at("choice"), "endpoint"), "laptop");
    f.screen.ui()->find("a2/main/ai_agent_text/" + handle)->string.assign(text);
    STK_UNTIL(widget("ai_agent_send") && widget("ai_agent_send")->enabled);
    widget("ai_agent_send")->on_click();
    STK_UNTIL(io::get_string(state().agent().view(), "state") == "awaiting" && !state().agent().running());
  }
};

TEST_F(AgentPython, TheAgentsDraftIsAppliedFromItsCardThroughTheSession)
{
  ASSERT_NO_FATAL_FAILURE(ask_agent("Scan the temperature of the first case."));
  auto &agent = state().agent();
  const auto view = agent.view();
  STK_UNTIL(timeline().find("Propose a parameter-sweep draft") != std::string::npos);
  const auto shown = timeline();
  EXPECT_NE(shown.find("[read] Look at the project's structure"), std::string::npos) << shown;
  EXPECT_NE(shown.find("[record] Capture rows"), std::string::npos) << shown;
  EXPECT_NE(shown.find("I saved a draft."), std::string::npos) << shown;
  ASSERT_EQ(view.at("awaiting").size(), 1u);
  const auto item = view.at("awaiting")[0];
  const auto draft_id = io::get_string(item, "draft_id");
  EXPECT_EQ(state().project()->revision, 1);  // the agent saved a draft, nothing else
  EXPECT_EQ(state().table()->records.size(), 1u);
  // The card opens the draft in the review page; applying there goes through the session.
  STK_UNTIL(widget("ai_agent_review/" + io::get_string(item, "item_id")) &&
            widget("ai_agent_review/" + io::get_string(item, "item_id"))->enabled);
  widget("ai_agent_review/" + io::get_string(item, "item_id"))->on_click();
  STK_UNTIL(io::get_string(state().saved_review(), "id") == draft_id &&
            (agent.track_draft(draft_id), agent.draft_state(draft_id) == AgentDraft::Waiting));
  ASSERT_TRUE(agent.awaiting_for_draft(draft_id).has_value());
  ASSERT_TRUE(state().preview()); settled();
  ASSERT_TRUE(state().apply_review());
  STK_UNTIL(!state().busy() && state().project()->revision == 2 && io::get_string(state().saved_review(), "status") == "applied");
  EXPECT_EQ(state().table()->records.size(), 4u);
  // The decision and its receipt are in the session; the card now asks to run the new rows.
  f.screen.set_maximized(&f.area("a2"));
  STK_UNTIL(io::get_string(agent.view(), "state") == "awaiting" &&
            io::get_string(agent.view().at("awaiting")[0], "kind") == "run_rows");
  std::vector<std::string> kinds;
  for (const auto &event : agent.view().at("events")) { kinds.push_back(io::get_string(event, "kind")); }
  const auto decided = std::find(kinds.begin(), kinds.end(), "approval_decided");
  ASSERT_NE(decided, kinds.end());
  EXPECT_NE(std::find(decided, kinds.end(), "approval_receipt"), kinds.end());
  STK_UNTIL(timeline().find("approved applying the draft") != std::string::npos);
  EXPECT_NE(widget("ai_agent_run_rows/rows:" + draft_id), nullptr);
  // The record checks out, and the Home list shows the session waiting for the person.
  ASSERT_TRUE(agent.verify());
  STK_UNTIL(!agent.verification().empty());
  EXPECT_TRUE(agent.verification().value("ok", false)) << agent.verification().dump();
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(AgentPython, DiscardingTheAgentsDraftIsRecordedInTheSession)
{
  ASSERT_NO_FATAL_FAILURE(ask_agent("Scan the temperature of the first case."));
  auto &agent = state().agent();
  const auto draft_id = io::get_string(agent.view().at("awaiting")[0], "draft_id");
  // Discarding goes through the session once its draft is known to wait there (the card already tracks it).
  STK_UNTIL((agent.track_draft(draft_id), agent.draft_state(draft_id) == AgentDraft::Waiting));
  ASSERT_TRUE(state().discard_saved_draft(draft_id));
  STK_UNTIL(!state().busy() && io::get_string(agent.view(), "state") == "idle");
  const auto &events = agent.view().at("events");
  const auto decided = std::find_if(events.begin(), events.end(), [](const Json &event) {
    return io::get_string(event, "kind") == "approval_decided";
  });
  ASSERT_NE(decided, events.end());
  EXPECT_EQ(io::get_string(*decided, "decision"), "discard");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(state().table()->records.size(), 1u);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(AgentPython, SessionsAppearInTheAttentionListAndOpenInTheAssistant)
{
  ASSERT_NO_FATAL_FAILURE(ask_agent("Scan the temperature of the first case."));
  const auto session = state().agent().selected();
  const auto draft_id = io::get_string(state().agent().view().at("awaiting")[0], "draft_id");
  // A new session is chosen in the assistant; Home lists the waiting one.
  state().agent().select("");
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorWorkspace));
  f.screen.set_maximized(&area);
  auto &attention = f.shell->store().attention();
  const auto listed = [&]() -> Json {
    if (!attention.result().is_object()) { return Json(); }
    for (const auto &entry : attention.result().value("items", Json::array())) {
      if (io::get_string(entry, "kind") == "agent_session" && io::get_string(entry, "id") == session) { return entry; }
    }
    return Json();
  };
  // Sessions never change the revision: read the list again until the session shows.
  STK_UNTIL((attention.sync(), !attention.busy()) && (listed().is_object() || (attention.refresh(), false)));
  const auto item = listed();
  EXPECT_EQ(io::get_string(item, "status"), "awaiting");
  EXPECT_EQ(io::get_string(item, "group"), "needs_you");
  const auto key = io::get_string(item, "key");
  STK_UNTIL(widget("workspace_attention_open/" + key) && widget("workspace_attention_open/" + key)->enabled);
  EXPECT_EQ(widget("workspace_attention_archive/" + key), nullptr);  // sessions cannot be archived in v1
  widget("workspace_attention_open/" + key)->on_click();
  STK_UNTIL(dynamic_cast<EditorArea *>(f.screen.maximized()) &&
            dynamic_cast<EditorArea *>(f.screen.maximized())->editor().type().id == kEditorAI &&
            state().agent().selected() == session && state().agent().view().contains("awaiting"));
  // The review page names the session that proposed the draft.
  STK_UNTIL(state().agent().owner("draft", draft_id) != nullptr);
  EXPECT_EQ(io::get_string(state().agent().owner("draft", draft_id)->at("owner"), "session_id"), session);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(AgentPython, ARunningSessionCanBeCancelledAndItsDraftsWait)
{
  std::ofstream(dir.str() + "/agent-control/hold") << "1";
  populated();
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  f.screen.set_maximized(&area);
  const auto handle = state().project()->handle;
  STK_UNTIL(widget("ai_intent/" + handle) != nullptr && state().agent().supported());
  f.screen.ui()->find("a2/main/ai_intent/" + handle)->index.assign(3);
  STK_UNTIL(state().agent().route_loaded() && widget("ai_agent_text/" + handle) != nullptr);
  f.screen.ui()->find("a2/main/ai_agent_text/" + handle)->string.assign("Look at the project.");
  STK_UNTIL(widget("ai_agent_send") && widget("ai_agent_send")->enabled);
  widget("ai_agent_send")->on_click();
  // The planner turn is held: the session runs, sending is off and Cancel is on.
  STK_UNTIL(state().agent().running() && widget("ai_agent_cancel") && widget("ai_agent_cancel")->enabled);
  EXPECT_FALSE(widget("ai_agent_send")->enabled);
  EXPECT_TRUE(f.screen.ui()->find("a2/main/ai_agent_text/" + handle)->string.value().empty());  // the saved message left the box
  widget("ai_agent_cancel")->on_click();
  std::filesystem::remove(dir.str() + "/agent-control/hold");
  STK_UNTIL(!state().agent().running() && io::get_string(state().agent().view(), "stop_reason") == "cancelled");
  EXPECT_EQ(state().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

#undef STK_UNTIL

}  // namespace
}  // namespace stk::app
