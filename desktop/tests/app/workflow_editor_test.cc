/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/analysis_graph_canvas.hh"
#include "stk/app/editor_area.hh"
#include "stk/app/project_archive.hh"
#include "stk/app/project_state.hh"
#include "stk/app/project_workflows.hh"
#include "stk/app/workflow_draft.hh"
#include "stk/app/viewer_state.hh"
#include "stk/app/workflow_view.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <algorithm>
#include <cmath>
#include <tuple>
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
using Reply = bridge::Result<Json>;
namespace fs = std::filesystem;

Json port(const std::string &name, const std::string &type, const bool required = false)
{
  Json value = {{"name", name}, {"type", type}};
  if (required) { value["required"] = true; }
  return value;
}

Json summary(const std::string &id, const std::string &kind, Json name, Json inputs, Json outputs)
{
  return {{"id", id}, {"kind", kind}, {"name", std::move(name)}, {"content_sha256", nullptr}, {"file_count", nullptr},
          {"inputs", std::move(inputs)}, {"outputs", std::move(outputs)}, {"parameters", Json::array()}};
}

WorkflowViewText words()
{
  WorkflowViewText text;
  text.kinds = {{"table", "Table"}, {"files", "Files"}, {"analysis", "Analysis"}};
  return text;
}

TEST(WorkflowView, StepsBecomeTypedNodesWithOrderLinksPositionsAndFlags)
{
  const Json document = {{"format", "stk.workflow/1"}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", "t"}}}},
      {{"id", "fields"}, {"kind", "files"}, {"ref", {{"snapshot", "s"}}}, {"after", {"cases"}}},
      {{"id", "view"}, {"kind", "analysis"}, {"ref", {{"analysis", "a"}}}, {"label", "Field view"},
       {"inputs", {{"data", {{"from", "fields.files"}}}}}},
      {{"id", "gone"}, {"kind", "analysis"}, {"ref", {{"analysis", "b"}}}, {"inputs", {{"data", {{"from", "fields.files"}}}}}}}},
      {"ui", {{"positions", {{"cases", {0, 0}}, {"view", {600, 40}}}}}}};
  auto files = summary("fields", "files", nullptr, Json::array(), Json::array({port("files", "files")}));
  files["file_count"] = 3;
  const Json validation = {{"revision", 4}, {"ok", false}, {"omitted_issues", 0},
      {"issues", {{{"code", "missing_reference"}, {"step", "gone"}, {"path", "steps/3/ref"}, {"message", "m"}}}},
      {"steps", {summary("cases", "table", "Cases", Json::array(), Json::array({port("rows", "rows")})), files,
                 summary("view", "analysis", "Temperature", Json::array({port("data", "files", true)}),
                         Json::array({port("image", "result"), port("view", "result")})),
                 summary("gone", "analysis", nullptr, Json::array(), Json::array())}}};
  const auto view = workflow_graph_view(document, validation, words());
  ASSERT_EQ(view.nodes.size(), 4u);
  EXPECT_EQ(view.nodes[0].label, "Table · Cases");
  EXPECT_EQ(view.nodes[1].label, "Files · 3 files");
  EXPECT_EQ(view.nodes[2].label, "Analysis · Field view");  // a step label wins over the referenced name
  EXPECT_EQ(view.nodes[3].label, "Analysis · gone");
  EXPECT_EQ(view.nodes[2].stage, "analysis");
  EXPECT_TRUE(view.nodes[2].known_type);
  EXPECT_FALSE(view.nodes[3].known_type);  // unresolved: only the ports its links name
  EXPECT_TRUE(view.nodes[3].flagged); EXPECT_FALSE(view.nodes[2].flagged);
  ASSERT_EQ(view.nodes[2].outputs.size(), 2u);
  EXPECT_EQ(view.nodes[2].inputs.at(0).type_text, "files"); EXPECT_TRUE(view.nodes[2].inputs.at(0).required);
  // The execution order is a link from the done socket to the after socket.
  ASSERT_EQ(view.nodes[0].outputs.back().name, "(done)");
  ASSERT_EQ(view.nodes[1].inputs.back().name, "(after)");
  int order = 0, data = 0;
  for (const auto &edge : view.edges) {
    if (edge.source_port == "(done)" && edge.target_node == "fields" && edge.diagnostic.empty()) { ++order; }
    if (edge.source_node == "fields" && edge.target_node == "view" && edge.diagnostic.empty()) { ++data; }
  }
  EXPECT_EQ(order, 1); EXPECT_EQ(data, 1);
  EXPECT_EQ(view.nodes[0].rect.x, 0); EXPECT_EQ(view.nodes[2].rect.x, 600); EXPECT_EQ(view.nodes[2].rect.y, 40);
  EXPECT_TRUE(view.issues.empty());  // synthetic types are not reported; the reply carries the issues

  auto other = validation;
  other["steps"].erase(1);
  EXPECT_THROW(workflow_graph_view(document, other, words()), std::invalid_argument);
  other = validation; other["steps"][0]["id"] = "renamed";
  EXPECT_THROW(workflow_graph_view(document, other, words()), std::invalid_argument);
}

TEST(WorkflowView, OrderCyclesAreMarkedOnTheCanvas)
{
  const Json document = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "a"}, {"kind", "table"}, {"ref", {{"table", "t"}}}, {"after", {"b"}}},
      {{"id", "b"}, {"kind", "table"}, {"ref", {{"table", "t"}}}, {"after", {"a"}}}}}};
  const Json validation = {{"revision", 1}, {"ok", false}, {"omitted_issues", 0}, {"issues", Json::array()},
      {"steps", {summary("a", "table", "T", Json::array(), Json::array({port("rows", "rows")})),
                 summary("b", "table", "T", Json::array(), Json::array({port("rows", "rows")}))}}};
  const auto view = workflow_graph_view(document, validation, words());
  EXPECT_TRUE(view.nodes[0].cyclic); EXPECT_TRUE(view.nodes[1].cyclic);
}

TEST(WorkflowView, ProvisionalSummariesKeepUnchangedStepsUntilTheCandidateIsChecked)
{
  const Json saved = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", "t"}}}},
      {{"id", "view"}, {"kind", "analysis"}, {"ref", {{"analysis", "a"}}}}}}};
  const Json checked = {{"revision", 7}, {"ok", true}, {"omitted_issues", 0}, {"issues", Json::array()},
      {"steps", {summary("cases", "table", "Cases", Json::array(), Json::array({port("rows", "rows")})),
                 summary("view", "analysis", "View", Json::array({port("data", "files", true)}), Json::array({port("view", "result")}))}}};
  auto candidate = saved;
  candidate["steps"][1]["ref"]["analysis"] = "b";  // a changed reference is unresolved until checked
  candidate["steps"].push_back({{"id", "added"}, {"kind", "files"}, {"ref", {{"snapshot", "s"}}}});
  const auto provisional = workflow_provisional_validation(candidate, {{&saved, &checked}});
  ASSERT_EQ(provisional.at("steps").size(), 3u);
  EXPECT_EQ(provisional.at("steps")[0], checked.at("steps")[0]);
  EXPECT_TRUE(provisional.at("steps")[1].at("outputs").empty());
  EXPECT_EQ(provisional.at("steps")[2].at("id"), "added");
  EXPECT_TRUE(provisional.at("issues").empty());
  const auto view = workflow_graph_view(candidate, provisional, words());
  EXPECT_TRUE(view.nodes[0].known_type); EXPECT_FALSE(view.nodes[1].known_type); EXPECT_FALSE(view.nodes[2].known_type);
  // A later candidate check comes first: the added step keeps its summary through the next edit.
  Json checked_candidate = {{"revision", 8}, {"steps", {checked.at("steps")[0],
      summary("view", "analysis", "B", Json::array(), Json::array({port("view", "result")})),
      summary("added", "files", nullptr, Json::array(), Json::array({port("files", "files")}))}}};
  auto next = candidate;
  next["steps"][2]["label"] = "Inputs";
  const auto merged = workflow_provisional_validation(next, {{&candidate, &checked_candidate}, {&saved, &checked}});
  EXPECT_EQ(merged.at("steps")[1].at("name"), "B");
  EXPECT_EQ(merged.at("steps")[2].at("outputs").size(), 1u);
  EXPECT_EQ(merged.at("revision"), 8);
}

constexpr const char *kRecordingBridge = R"PY(
import json
from pathlib import Path
import sys
import threading
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main

control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run = Bridge._run

def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method}, ensure_ascii=True) + '\n')
    return original_run(self, identity, method, params)

Bridge._run = run
main()
)PY";

constexpr const char *table_id = "11111111-1111-4111-8111-111111111111";
constexpr const char *field_id = "12121212-1212-4121-8121-121212121212";
constexpr const char *analysis_id = "6b0f5c3e-2d1a-4c9e-9f7b-3a8e5d4c2b10";
constexpr const char *other_analysis = "7c1f6d4f-3e2b-4d0f-8a8c-4b9f6e5d3c21";
constexpr const char *workflow_id = "8d2a7e50-4f3c-4e1a-9b9d-5cae7f6e4d32";
constexpr const char *broken_id = "9e3b8f61-5a4d-4f2b-8cae-6dbf8a7f5e43";

class WorkflowEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"workflow-ui"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 2200};
  std::unique_ptr<bridge::Client> client;
  int64_t revision = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  EditorArea &area() { return f.area("a2"); }
  std::string handle() { return project().project()->handle; }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  bool shows(const std::string &text)
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  }
  size_t calls(const std::string &method)
  {
    size_t count = 0; std::ifstream file(directory.path() / "calls.jsonl"); std::string line;
    while (std::getline(file, line)) { if (io::parse_json(line).at("method") == method) { ++count; } }
    return count;
  }
  void call(const std::string &method, Json params, Json &out)
  {
    auto reply = std::make_shared<std::optional<Reply>>(); auto future = client->call(method, std::move(params));
    future.then([reply](auto value) { *reply = std::move(value); });
    const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
    if (!done) { future.cancel(); }
    ASSERT_TRUE(done) << client->bridge_log().text();
    ASSERT_TRUE(reply->value().ok()) << method << ": " << reply->value().error().describe(); out = reply->value().value();
    if (out.contains("revision") && out.at("revision").is_number_integer()) { revision = out.at("revision").get<int64_t>(); }
  }
  void frames_until(const std::function<bool()> &condition)
  {
    ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return condition(); }, 30))
        << client->bridge_log().text();
  }
  void click(const std::string &key)
  {
    const auto *value = widget(key); ASSERT_NE(value, nullptr) << key; ASSERT_TRUE(value->enabled) << key;
    ASSERT_TRUE(value->on_click); value->on_click(); f.screen.run_deferred(); f.drv->frame();
  }
  Json analysis_document()
  {
    return {{"format", "stk.analysis-document/1"},
        {"graph", io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/volume.json").at("graph")},
        {"parameters", {{"path", "field.vtk"}}}, {"outputs", Json::array({"view"})}};
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const auto *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for workflows"; }
    { std::ofstream file(directory.path() / "bridge.py"); file << kRecordingBridge; ASSERT_TRUE(file.good()); }
    bridge::ClientOptions options;
    options.python.configured = python; options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime"; options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), directory.str(), "--stdio",
        "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    options.executor = loop.executor(); options.strict = options.validate = true; options.call_timeout_s = 10;
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    const auto root = core::path_to_utf8(directory.path() / "project");
    ASSERT_TRUE(project().create(root, "Workflow navigation"));
    ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
    Json out;
    ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", 0}, {"commands", {
        {{"op", "create_table"}, {"id", table_id}, {"name", "Cases"}},
        {{"op", "add_field"}, {"id", field_id}, {"table_id", table_id}, {"name", "Colormap"}, {"type", "text"}}}}}, out));
    const auto field = directory.path() / "project" / "field.vtk";  // native separators on every platform
    { std::ofstream file(field); file << "not read\n"; }
    ASSERT_NO_FATAL_FAILURE(call("project.files.index", {{"handle", handle()}, {"expected_revision", revision},
        {"paths", {core::path_to_utf8(field)}}}, out));
    const auto record = out.at("record_ids").at(0).get<std::string>();
    ASSERT_NO_FATAL_FAILURE(call("project.snapshots.capture", {{"handle", handle()}, {"expected_revision", revision},
        {"record_ids", {record}}}, out));
    const auto snapshot = out.at("snapshot").at("id").get<std::string>();
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", analysis_id},
        {"name", "Temperature field"}, {"document", analysis_document()}, {"expected_revision", revision}}, out));
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", other_analysis},
        {"name", "Other analysis"}, {"document", analysis_document()}, {"expected_revision", revision}}, out));
    const Json workflow = {{"format", "stk.workflow/1"}, {"steps", {
        {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
        {{"id", "fields"}, {"kind", "files"}, {"ref", {{"snapshot", snapshot}}}, {"after", {"cases"}}},
        {{"id", "temperature"}, {"kind", "analysis"}, {"ref", {{"analysis", analysis_id}}},
         {"inputs", {{"data", {{"from", "fields.files"}}}}}}}},
        {"ui", {{"positions", {{"cases", {0, 0}}, {"fields", {260, 0}}, {"temperature", {520, 0}}}}}}};
    ASSERT_NO_FATAL_FAILURE(call("project.workflows.create", {{"handle", handle()}, {"workflow_id", workflow_id},
        {"name", "Temperature scan"}, {"document", workflow}, {"expected_revision", revision}}, out));
    const Json broken = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
        {{"id", "lost"}, {"kind", "analysis"}, {"ref", {{"analysis", "00000000-0000-4000-8000-000000000000"}}}}}}};
    ASSERT_NO_FATAL_FAILURE(call("project.workflows.create", {{"handle", handle()}, {"workflow_id", broken_id},
        {"name", "Broken"}, {"document", broken}, {"expected_revision", revision}}, out));
    project().refresh();
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && project().project()->revision == revision; }, 30));
    ASSERT_TRUE(area().set_tab_type(0, kEditorWorkflow));
    f.screen.set_maximized(&area()); area().find_region(EditorArea::kSidebar)->set_size_1x(560); f.drv->frame();
    // The first workflow is shown and checked without a click.
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("All references and links are valid."); }));
  }
  void TearDown() override
  {
    EXPECT_EQ(calls("graph.evaluate"), 0u); EXPECT_EQ(calls("project.analysis_runs.prepare"), 0u);
    EXPECT_EQ(store().viewer().evaluations_started(), 0);
    project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  void activate(const std::string &type)
  {
    for (int i = 0; i < area().tab_count(); ++i) {
      if (area().tab(i).type().id == type) { area().set_active_tab(i); f.drv->frame(); return; }
    }
    FAIL() << "no " << type << " tab";
  }
  /** Choose the dropdown entry containing `label`. */
  void choose(const std::string &key, const std::string &label)
  {
    const auto *dropdown = widget(key); ASSERT_NE(dropdown, nullptr) << key; ASSERT_TRUE(dropdown->enabled) << key;
    const auto found = std::find_if(dropdown->items.begin(), dropdown->items.end(),
        [&](const std::string &item) { return item.find(label) != std::string::npos; });
    std::string listed;
    for (const auto &item : dropdown->items) { listed += "\n  " + item; }
    ASSERT_NE(found, dropdown->items.end()) << label << listed;
    dropdown->index.assign(int(found - dropdown->items.begin())); f.drv->frame();
  }
  std::string sidebar()
  {
    std::string out;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (!item.text.empty() && (item.key.find("workflow") != std::string::npos || item.key.find('#') != std::string::npos)) {
          out += "\n" + item.key + " | " + item.text + (item.enabled ? "" : " (disabled)");
        }
      }
    }
    return out;
  }
  Json stored()
  {
    Json out;
    call("project.workflows.get", {{"handle", handle()}, {"workflow_id", workflow_id}}, out);
    return out.at("workflow");
  }
  /** Select a step through the editor's own navigation (the canvas click is covered by the view tests). */
  void select(const std::string &step)
  {
    std::string reason;
    ASSERT_TRUE(area().editor().navigate({{"workflow_id", workflow_id}, {"step", step}}, {}, reason));
    f.drv->frame();
  }
};

TEST_F(WorkflowEditorPython, ShowsStepsAndEntersAndLeavesTheAnalysisInTheSameArea)
{
  EXPECT_TRUE(shows("Temperature scan · 3 steps"));
  auto *workflow_editor = &area().editor();
  const int tabs = area().tab_count();
  ASSERT_NO_FATAL_FAILURE(select("cases"));
  EXPECT_TRUE(shows("Parameter table · Cases"));
  ASSERT_NE(widget("workflow_open_table"), nullptr);
  ASSERT_NO_FATAL_FAILURE(select("temperature"));
  EXPECT_TRUE(shows("Analysis · Temperature field"));
  EXPECT_TRUE(shows("Input data (files) ← fields.files"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_enter_analysis"));
  // The analysis opens in a new analysis-graph tab of the same area, read on its next sync.
  ASSERT_EQ(area().tab_count(), tabs + 1);
  EXPECT_EQ(area().editor().type().id, kEditorAnalysisGraph);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_breadcrumb_workflow") != nullptr &&
      widget("graph_mode") && widget("graph_mode")->index.value() == 2 && shows("Temperature field"); }));
  EXPECT_EQ(widget("analysis_breadcrumb_workflow")->text, "‹ Temperature scan");
  EXPECT_TRUE(shows("› Temperature field"));
  auto *analysis_editor = &area().editor();

  ASSERT_NO_FATAL_FAILURE(click("analysis_breadcrumb_workflow"));
  f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(&area().editor(), workflow_editor);
  EXPECT_TRUE(shows("Analysis · Temperature field"));  // the step is still selected
  // Entering again reuses the analysis tab.
  ASSERT_NO_FATAL_FAILURE(click("workflow_enter_analysis"));
  EXPECT_EQ(&area().editor(), analysis_editor); EXPECT_EQ(area().tab_count(), tabs + 1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_breadcrumb_workflow") != nullptr; }));
}

TEST_F(WorkflowEditorPython, UnsavedEditsOfAnotherAnalysisAreNeverReplaced)
{
  ASSERT_NO_FATAL_FAILURE(select("temperature"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_enter_analysis"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_breadcrumb_workflow") != nullptr; }));
  auto *analysis_editor = &area().editor();
  ASSERT_NO_FATAL_FAILURE(click("analysis_list"));  // the saved-analysis list is read explicitly
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_documents") != nullptr; }));
  // Open the other analysis from the list and leave an unsaved change in it.
  const auto *list = widget("analysis_documents");
  int row = -1;
  for (int i = 0; i < list->table->rows; ++i) { if (list->table->cell(i, 0) == "Other analysis") { row = i; } }
  ASSERT_GE(row, 0); list->table->selected.assign(row);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_outputs_clear") && widget("analysis_outputs_clear")->enabled &&
      widget("analysis_breadcrumb_workflow") == nullptr; }));  // the breadcrumb no longer describes the shown analysis
  ASSERT_NO_FATAL_FAILURE(click("analysis_outputs_clear"));
  ASSERT_TRUE(widget("analysis_parameters_save") && widget("analysis_parameters_save")->enabled);
  // Back to the workflow through its tab, then try to enter the step's analysis.
  ASSERT_NO_FATAL_FAILURE(activate(kEditorWorkflow));
  ASSERT_NO_FATAL_FAILURE(select("temperature"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_enter_analysis"));
  EXPECT_EQ(area().editor().type().id, kEditorWorkflow);  // refused: the area stays on the workflow
  ASSERT_NO_FATAL_FAILURE(activate(kEditorAnalysisGraph));
  EXPECT_EQ(&area().editor(), analysis_editor);
  ASSERT_TRUE(widget("analysis_parameters_save") && widget("analysis_parameters_save")->enabled);  // the draft is intact
  const auto *documents = widget("analysis_documents"); ASSERT_NE(documents, nullptr);
  const int shown = documents->table->selected.value();
  ASSERT_GE(shown, 0); EXPECT_EQ(documents->table->cell(shown, 0), "Other analysis");
}

TEST_F(WorkflowEditorPython, MissingReferencesAreListedAndTheBreadcrumbEndsWithTheProject)
{
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  const auto *list = widget("workflow_list"); ASSERT_EQ(list->table->rows, 2);
  list->table->selected.assign(1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found"); }));
  ASSERT_NE(widget("workflow_issue/0"), nullptr);
  EXPECT_EQ(widget("workflow_issue/0")->text, "lost · Referenced object not found");
  ASSERT_NO_FATAL_FAILURE(click("workflow_issue/0"));
  EXPECT_TRUE(shows("Analysis · lost"));
  ASSERT_NE(widget("workflow_enter_analysis"), nullptr);
  EXPECT_FALSE(widget("workflow_enter_analysis")->enabled);  // nothing to open

  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  list = widget("workflow_list"); list->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("All references and links are valid."); }));
  ASSERT_NO_FATAL_FAILURE(select("temperature"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_enter_analysis"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_breadcrumb_workflow") != nullptr; }));
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  EXPECT_EQ(widget("analysis_breadcrumb_workflow"), nullptr);
}

TEST_F(WorkflowEditorPython, EachWorkflowKeepsItsViewAndStepAndTheLayoutReopensTheLastOne)
{
  const auto memory = [&](const std::string &id) -> nlohmann::json {
    const auto state = area().editor().save_state();  // kept alive while its views are searched
    for (const auto &view : state.at("views")) { if (view.at("workflow") == id) { return view; } }
    return nullptr;
  };
  // The canvas is placed when it is drawn or receives pointer events (these tests draw no GPU frames).
  const auto rect = area().find_region(EditorArea::kMain)->rect();
  // Shown views are kept once the editor has settled (no read in flight).
  const auto hover = [&] {
    f.drv->move(rect.xmin + rect.width() / 3, rect.ymin + rect.height() / 2); f.drv->frame();
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  };
  // Temperature scan: a step selected and the canvas zoomed in away from the fitted view.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(select("fields"));
  ASSERT_NO_FATAL_FAILURE(hover());
  const auto fitted = memory(workflow_id);
  ASSERT_FALSE(fitted.is_null());
  wm::Event wheel;
  wheel.type = wm::EventType::Wheel; wheel.x = rect.xmin + rect.width() / 3; wheel.y = rect.ymin + rect.height() / 2; wheel.wheel_y = 3;
  f.drv->send(wheel); f.drv->frame();
  const auto zoomed = memory(workflow_id);
  EXPECT_EQ(zoomed.at("step"), "fields");
  ASSERT_GT(zoomed.at("zoom").get<double>(), fitted.at("zoom").get<double>() * 1.2);
  // Another workflow is fitted on its own; coming back restores the zoom, the centre and the step.
  widget("workflow_list")->table->selected.assign(1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found"); }));
  ASSERT_NO_FATAL_FAILURE(hover());
  EXPECT_FALSE(memory(broken_id).is_null());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  widget("workflow_list")->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("All references and links are valid."); }));
  ASSERT_NO_FATAL_FAILURE(hover());
  const auto back = memory(workflow_id);
  EXPECT_NEAR(back.at("zoom").get<double>(), zoomed.at("zoom").get<double>(), 1e-9);
  EXPECT_NEAR(back.at("x").get<double>(), zoomed.at("x").get<double>(), 1e-6);
  EXPECT_NEAR(back.at("y").get<double>(), zoomed.at("y").get<double>(), 1e-6);
  EXPECT_EQ(back.at("step"), "fields");
  EXPECT_TRUE(shows("Selected step")) << sidebar();
  // The layout keeps the views and the workflow shown last: a new editor reopens Broken (not the first
  // workflow) and later shows Temperature scan as it was left.
  widget("workflow_list")->table->selected.assign(1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found"); }));
  ASSERT_NO_FATAL_FAILURE(hover());
  const auto state = area().editor().save_state();
  EXPECT_EQ(state.at("shown").at("workflow"), broken_id);
  EXPECT_EQ(state.at("shown").at("project"), project().project()->id);
  ASSERT_TRUE(area().set_tab_type(0, kEditorWorkspace)); f.drv->frame();
  ASSERT_TRUE(area().set_tab_type(0, kEditorWorkflow));
  ASSERT_TRUE(area().editor().load_state(state));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  widget("workflow_list")->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("All references and links are valid."); }));
  ASSERT_NO_FATAL_FAILURE(hover());
  EXPECT_NEAR(memory(workflow_id).at("zoom").get<double>(), zoomed.at("zoom").get<double>(), 1e-9);
  EXPECT_EQ(memory(workflow_id).at("step"), "fields");
  // Malformed layout state is refused (the application falls back to the default layout).
  EXPECT_FALSE(area().editor().load_state({{"views", "none"}}));
  EXPECT_FALSE(area().editor().load_state({{"views", {{{"project", "p"}, {"workflow", "w"}, {"x", 0}, {"y", 0}, {"zoom", -1},
                                                       {"step", ""}, {"run", ""}}}}}));
  EXPECT_TRUE(area().editor().load_state(Json::object()));
}

TEST_F(WorkflowEditorPython, HomeSearchFindsWorkflowsAnalysesAndFilesAndOpensThem)
{
  f.shell->restore_split_layout(&f.screen);
  ASSERT_EQ(f.area("a1").editor().type().id, kEditorWorkspace);
  const auto find = [&](const std::string &query) {
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workspace_search") && widget("workspace_search")->enabled; }));
    widget("workspace_search_text")->string.assign(query);
    ASSERT_NO_FATAL_FAILURE(click("workspace_search"));
  };
  ASSERT_NO_FATAL_FAILURE(find("TEMPERATURE"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Workflows (1)") && shows("Saved analyses (1)"); }));
  ASSERT_NO_FATAL_FAILURE(click("workspace_search_open/0"));  // the workflow comes first
  ASSERT_NO_FATAL_FAILURE(frames_until([&] {
    auto *maximized = dynamic_cast<EditorArea *>(f.screen.maximized());
    return maximized && maximized->editor().type().id == kEditorWorkflow && shows("Temperature scan · 3 steps");
  }));
  // A file opens the file page with its row selected.
  f.shell->restore_split_layout(&f.screen);
  ASSERT_NO_FATAL_FAILURE(find("field.vtk"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Files (1)"); }));
  EXPECT_FALSE(shows("Nothing found"));
  ASSERT_NO_FATAL_FAILURE(click("workspace_search_open/0"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] {
    auto *maximized = dynamic_cast<EditorArea *>(f.screen.maximized());
    return maximized && maximized->editor().type().id == kEditorProject && !project().record_id().empty();
  }));
  EXPECT_EQ(project().table_id(), "becb9ec9-1a27-5d31-8aa3-5402f09f43a9");  // the file index
  ASSERT_NE(project().table(), nullptr);
  EXPECT_EQ(project().table()->text(project().selected_record(), 0), "field.vtk");
  // Nothing found is said plainly; searching never changes the project.
  f.shell->restore_split_layout(&f.screen);
  f.tab("a1", kEditorWorkspace); f.drv->frame();  // the file page took Home's area
  const auto before = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(find("no such words"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Nothing found for “no such words”."); }));
  EXPECT_EQ(project().project()->revision, before);
  EXPECT_FALSE(shows("The project changed after this search"));
  // A later edit marks the shown results as possibly out of date (they are not re-read by themselves).
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", before},
      {"commands", {{{"op", "add_record"}, {"id", "18181818-1818-4181-8181-181818181818"}, {"table_id", table_id}}}}}, out));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("The project changed after this search; search again to update the results."); }));
  EXPECT_EQ(calls("project.search"), 3u);
}

TEST_F(WorkflowEditorPython, ClosingTheProjectBeforeTheAnalysisIsReadLeavesNoWayBack)
{
  ASSERT_NO_FATAL_FAILURE(select("temperature"));
  const auto reads = calls("project.analyses.get");
  const auto *enter = widget("workflow_enter_analysis"); ASSERT_TRUE(enter && enter->enabled);
  enter->on_click(); f.screen.run_deferred();  // accepted; the analysis is read on the next frame
  ASSERT_EQ(area().editor().type().id, kEditorAnalysisGraph);
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().project(); }));
  f.drv->frame();
  EXPECT_EQ(widget("analysis_breadcrumb_workflow"), nullptr);
  // The next project never receives the old request.
  ASSERT_TRUE(project().create(core::path_to_utf8(directory.path() / "next"), "Next project"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().loaded() && !project().busy(); }));
  for (int i = 0; i < 5; ++i) { loop.run_ready(); f.drv->frame(); }
  EXPECT_EQ(widget("analysis_breadcrumb_workflow"), nullptr);
  EXPECT_EQ(calls("project.analyses.get"), reads);
}

TEST_F(WorkflowEditorPython, DraftEditsSaveExactlyAndCandidateChecksAreKeyed)
{
  ProjectWorkflows workflows(store());
  ASSERT_TRUE(workflows.load(workflow_id));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !workflows.busy() && !workflows.validation().is_null(); }));
  const auto &selected = workflows.selected();
  WorkflowDraft draft;
  draft.pin(handle(), workflow_id, workflows.selected_revision(), selected.at("name").get<std::string>(), selected.at("document"));
  const auto generation = draft.generation();
  const auto added = draft.add_step("analysis", "analysis", other_analysis, std::pair{780.0, 0.0}, generation);
  ASSERT_TRUE(added.accepted) << added.error;
  ASSERT_TRUE(draft.set_after(added.id, {"temperature"}, generation).accepted);
  ASSERT_TRUE(draft.set_parameter("temperature", "colormap", Json("cividis"), generation).accepted);
  ASSERT_TRUE(draft.set_label("temperature", std::string("Field view"), generation).accepted);
  ASSERT_TRUE(draft.move_steps({{"cases", {0, 120}}}, generation).accepted);
  ASSERT_TRUE(draft.set_name("Temperature scan v2", generation).accepted);

  // The candidate check describes this candidate only; the new analysis step still lacks its input.
  AnalysisCandidateKey key{handle(), workflow_id, workflows.session(), workflows.selected_revision(),
                           draft.generation(), draft.check_version()};
  ASSERT_TRUE(workflows.check(draft.document(), key));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !workflows.candidate().pending(); }));
  const auto *checked = workflows.candidate().result(key);
  ASSERT_NE(checked, nullptr) << workflows.candidate().error(key);
  ASSERT_EQ(checked->at("issues").size(), 1u);
  EXPECT_EQ(checked->at("issues")[0].at("code"), "missing_input");
  EXPECT_EQ(checked->at("steps")[3].at("name"), "Other analysis");
  auto other = key; ++other.version;
  EXPECT_EQ(workflows.candidate().result(other), nullptr);

  // Saving stores exactly the candidate (name included) at the read revision.
  ASSERT_TRUE(workflows.update(draft.name(), draft.document(), workflows.selected_version()));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !workflows.busy() && !workflows.uncertain() &&
      io::get_string(workflows.selected(), "name") == "Temperature scan v2"; }));
  Json stored;
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.get", {{"handle", handle()}, {"workflow_id", workflow_id}}, stored));
  EXPECT_EQ(io::python_json_dumps(stored.at("workflow").at("document"), true, true), io::python_json_dumps(draft.document(), true, true));
  EXPECT_EQ(stored.at("workflow").at("name"), "Temperature scan v2");
  EXPECT_EQ(workflows.notice(), "workflow.saved");
  // A stale read revision is refused by storage and nothing is written.
  const auto after = project().project()->revision;
  WorkflowDraft stale; stale.pin(handle(), workflow_id, after - 1, "Stale", draft.document());
  EXPECT_FALSE(workflows.update("Stale", stale.document(), workflows.selected_version() + 1));  // not the read selection

  // A new, empty workflow under a fresh UUID.
  const Json empty = {{"format", "stk.workflow/1"}, {"steps", Json::array()}, {"ui", Json::object()}};
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_TRUE(workflows.create("Empty workflow", empty));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !workflows.busy() && io::get_string(workflows.selected(), "name") == "Empty workflow"; }));
  EXPECT_NE(io::get_string(workflows.selected(), "id"), workflow_id);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));  // reads wait for the project refresh
  ASSERT_TRUE(workflows.load_choices());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !workflows.busy() && !workflows.choices().is_null(); }));
  EXPECT_EQ(workflows.choices().at("analyses").size(), 2u);
  EXPECT_EQ(workflows.choices().at("tables").size(), 1u);  // the managed tables are not parameter tables
}

struct WorkflowCanvasProbe {
  AnalysisGraphView view;
  AnalysisGraphCanvas canvas;
  wm::Rect rect;
  double top = 0;
  std::pair<int, int> window(AnalysisGraphPoint point) const
  {
    const auto screen = canvas.to_screen(point);
    return {rect.xmin + int(std::lround(screen.x)), rect.ymax - 1 - int(std::lround(screen.y + top))};
  }
  const AnalysisGraphNode &node(const std::string &id) const
  {
    return *std::find_if(view.nodes.begin(), view.nodes.end(), [&](const auto &n) { return n.id == id; });
  }
  std::pair<int, int> port(const std::string &id, const std::string &name, bool output) const
  {
    const auto &ports = output ? node(id).outputs : node(id).inputs;
    return window(std::find_if(ports.begin(), ports.end(), [&](const auto &p) { return p.name == name; })->point);
  }
};

TEST_F(WorkflowEditorPython, EditsAddLinkBindAndSaveTheCandidate)
{
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_add_object") && widget("workflow_add_object")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(choose("workflow_add_kind", "Analysis"));
  ASSERT_NO_FATAL_FAILURE(choose("workflow_add_object", "Other analysis"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_add_step"));
  // The candidate shows at once; its check reports the new step's open input.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Temperature scan · 4 steps (unsaved)") &&
      shows("1 problems after the changes"); }));
  EXPECT_TRUE(shows("Added step analysis"));
  EXPECT_TRUE(shows("Analysis · Other analysis"));  // the new step is selected
  ASSERT_NO_FATAL_FAILURE(choose("workflow_input/data/source", "fields.files"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("After the changes all references and links are valid."); }));
  ASSERT_NO_FATAL_FAILURE(choose("workflow_param/colormap/mode", "Parameter table field"));
  ASSERT_NE(widget("workflow_param/colormap/field"), nullptr) << sidebar();
  EXPECT_EQ(widget("workflow_param/colormap/field")->items.at(0), "Cases · Colormap");
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_save") && widget("workflow_save")->enabled; }));
  const auto before = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(click("workflow_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return project().project()->revision == before + 1 &&
      shows("Temperature scan · 4 steps") && !shows("(unsaved)") && shows("All references and links are valid."); }));
  const auto saved = stored();
  const auto &step = saved.at("document").at("steps")[3];
  EXPECT_EQ(step.at("id"), "analysis");
  EXPECT_EQ(step.at("ref").at("analysis"), other_analysis);
  EXPECT_EQ(step.at("inputs").at("data").at("from"), "fields.files");
  EXPECT_EQ(step.at("parameters").at("colormap"), Json({{"$field", field_id}}));
  EXPECT_TRUE(saved.at("document").at("ui").at("positions").contains("analysis"));
}

TEST_F(WorkflowEditorPython, CanvasGesturesRefuseMismatchedTypesOrderStepsAndMove)
{
  const auto document = stored().at("document");
  Json validation;
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.validate", {{"handle", handle()}, {"document", document}}, validation));
  WorkflowViewText text;
  text.kinds = {{"table", "Parameter table"}, {"files", "Input files"}, {"simulation", "Simulation"}, {"analysis", "Analysis"}};
  auto probe = std::make_shared<WorkflowCanvasProbe>();
  probe->view = workflow_graph_view(document, validation, text);
  probe->rect = area().find_region(EditorArea::kMain)->rect();
  probe->top = 1.5 * f.screen.ui()->style().unit;
  probe->canvas.set_view(std::make_shared<const AnalysisGraphView>(probe->view));
  ASSERT_TRUE(probe->canvas.fit(probe->rect.width(), probe->rect.height() - probe->top, 1));
  ASSERT_GE(probe->canvas.zoom(), 0.5);  // sockets are hit only when labels are shown
  // Canvas edits wait for the editor's reads (choices, runs) to finish, like the panel buttons.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_add_step") && widget("workflow_add_step")->enabled; }));
  // rows into a files input is refused locally and changes nothing.
  auto [sx, sy] = probe->port("cases", "rows", true);
  auto [tx, ty] = probe->port("temperature", "data", false);
  f.drv->drag(sx, sy, tx, ty, 6);
  EXPECT_TRUE(shows("Port types differ: rows → files"));
  EXPECT_FALSE(shows("(unsaved)"));
  // Any output dropped on (after) orders the steps: fields after temperature closes a cycle.
  std::tie(sx, sy) = probe->port("temperature", "view", true);
  std::tie(tx, ty) = probe->port("fields", "(after)", false);
  f.drv->drag(sx, sy, tx, ty, 6);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("(unsaved)") && shows("problems after the changes"); }));
  EXPECT_TRUE(shows("Dependency cycle"));
  // Moving a step writes its position once, on release.
  const auto &cases = probe->node("cases").rect;
  const auto [x0, y0] = probe->window({cases.x + cases.width / 2, cases.y + 20});
  f.drv->drag(x0, y0, x0, y0 + 90, 6);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_save") && widget("workflow_save")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_save"));
  // Waits for the bridge's replies (a fixed number of frames is too short on slow runners).
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  ASSERT_TRUE(widget("workflow_list") && widget("workflow_list")->enabled) << sidebar();
  const auto saved = stored().at("document");
  EXPECT_EQ(saved.at("steps")[1].at("after"), Json::array({"cases", "temperature"}));
  // Window y grows upwards, so +90 window pixels is up the canvas.
  EXPECT_NEAR(saved.at("ui").at("positions").at("cases")[1].get<double>(), cases.y - 90 / probe->canvas.zoom(), 2.0);
}

TEST_F(WorkflowEditorPython, DeleteRemovesTheSelectedStepAndDiscardRestores)
{
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(select("fields"));
  const auto [cx, cy] = wmtest::AppFixture::center(area().find_region(EditorArea::kMain)->rect());
  f.drv->move(cx, cy);
  f.drv->key(wm::Key::Delete);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Temperature scan · 2 steps (unsaved)") && shows("Removed step fields"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("problems after the changes"); }));  // temperature lost its input
  EXPECT_TRUE(shows("Required input not linked"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_discard"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Temperature scan · 3 steps") && !shows("(unsaved)"); }));
  EXPECT_EQ(stored().at("document").at("steps").size(), 3u);
}

TEST_F(WorkflowEditorPython, OtherEditsKeepUnsavedChangesButAChangedWorkflowDetachesThem)
{
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_name") && widget("workflow_rename"); }));
  widget("workflow_name")->string.assign("Renamed scan"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_rename") && widget("workflow_rename")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_rename"));
  EXPECT_TRUE(shows("Renamed to Renamed scan"));
  // An unrelated project edit moves the revision; the unchanged workflow keeps the edits.
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", {
      {{"op", "add_record"}, {"id", "13131313-1313-4131-8131-131313131313"}, {"table_id", table_id}}}}}, out));
  project().refresh();
  f.drv->frame();
  EXPECT_TRUE(shows("Reading the workflow again")) << sidebar();  // Save is unavailable for a reason the panel states
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision == revision &&
      widget("workflow_save") && widget("workflow_save")->enabled; }));
  EXPECT_TRUE(shows("Renamed to Renamed scan"));
  ASSERT_NO_FATAL_FAILURE(click("workflow_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return stored().at("name") == "Renamed scan" && !shows("Renamed to"); }));
  revision = project().project()->revision;
  // Edits of a workflow that then changes elsewhere cannot be saved; discarding shows the current one.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_name") && widget("workflow_rename"); }));
  widget("workflow_name")->string.assign("Local name"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_rename") && widget("workflow_rename")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_rename"));
  auto other = stored();
  other["document"]["steps"].erase(1);
  other["document"]["steps"][1].erase("inputs");
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.update", {{"handle", handle()}, {"workflow_id", workflow_id},
      {"name", "Changed elsewhere"}, {"document", other.at("document")}, {"expected_revision", project().project()->revision}}, out));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("changed elsewhere and the local edits"); }));
  EXPECT_EQ(widget("workflow_save"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("workflow_discard"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Changed elsewhere · 2 steps"); }));
}

TEST_F(WorkflowEditorPython, NewAndDeletedWorkflowsAreOrdinaryUndoableEdits)
{
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_new") && widget("workflow_new")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_new"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Workflow 3 · 0 steps"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_delete") && widget("workflow_delete")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_delete"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->table &&
      widget("workflow_list")->table->rows == 2 && !project().busy(); }));
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->table &&
      widget("workflow_list")->table->rows == 3; }));
}

TEST_F(WorkflowEditorPython, RunPanelRunsChosenRowsAndOpensTheirAnalysisRuns)
{
  // A runnable version: cases (temperature per row) -> synthetic solver -> the temperature analysis.
  const std::string temperature = "14141414-1414-4141-8141-141414141414";
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", {
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table_id}, {"name", "T"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"id", "15151515-1515-4151-8151-151515151515"}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", "15151515-1515-4151-8151-151515151515"}, {"field_id", temperature}, {"value", 300}},
      {{"op", "add_record"}, {"id", "16161616-1616-4161-8161-161616161616"}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", "16161616-1616-4161-8161-161616161616"}, {"field_id", temperature}, {"value", 340}}}}}, out));
  const Json runnable = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
      {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
       {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", temperature}}}}}},
      {{"id", "temperature"}, {"kind", "analysis"}, {"ref", {{"analysis", analysis_id}}},
       {"inputs", {{"data", {{"from", "simulate.files"}}}}}}}}};
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.update", {{"handle", handle()}, {"workflow_id", workflow_id}, {"name", "Temperature scan"},
      {"document", runnable}, {"expected_revision", revision}}, out));
  project().refresh();
  // Waits for the bridge's replies (a fixed number of frames is too short on slow runners).
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_run_start") && widget("workflow_run_start")->enabled; }));
  ASSERT_TRUE(widget("workflow_run_start") && widget("workflow_run_start")->enabled) << sidebar();
  EXPECT_EQ(widget("workflow_run_start")->text, "Run the 2 selected rows");
  ASSERT_NE(widget("workflow_run_row/2"), nullptr);
  EXPECT_NE(widget("workflow_run_row/2")->text.find("T 340 K"), std::string::npos);
  ASSERT_NO_FATAL_FAILURE(click("workflow_run_start"));
  // The service executes it; the panel follows until both rows are done.
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return shows("All done · 4/4 done"); }, 120))
      << sidebar();
  const auto *grid = widget("workflow_run_tasks"); ASSERT_NE(grid, nullptr); ASSERT_EQ(grid->table->rows, 2);
  EXPECT_EQ(grid->table->cell(1, 1), "Done"); EXPECT_EQ(grid->table->cell(1, 2), "Done");
  grid->table->selected.assign(1); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("workflow_run_open/temperature"));
  // The analysis graph opens that analysis run on its Runs side.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return area().editor().type().id == kEditorAnalysisGraph &&
      widget("analysis_saved_section") && widget("analysis_saved_section")->index.value() == 1; }));
  EXPECT_EQ(calls("project.workflow_runs.prepare"), 1u);
  EXPECT_EQ(calls("project.workflow_runs.start"), 1u);
}

TEST_F(WorkflowEditorPython, ChangedValuesMarkRowsStaleAndOnlyThoseRunAgain)
{
  const std::string temperature = "14141414-1414-4141-8141-141414141414", first = "15151515-1515-4151-8151-151515151515",
                    second = "16161616-1616-4161-8161-161616161616";
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", {
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table_id}, {"name", "T"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"id", first}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", first}, {"field_id", temperature}, {"value", 300}},
      {{"op", "add_record"}, {"id", second}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second}, {"field_id", temperature}, {"value", 340}}}}}, out));
  const Json runnable = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
      {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
       {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", temperature}}}}}}}}};
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.update", {{"handle", handle()}, {"workflow_id", workflow_id}, {"name", "Temperature scan"},
      {"document", runnable}, {"expected_revision", revision}}, out));
  project().refresh();
  // Waits for the bridge's replies (a fixed number of frames is too short on slow runners).
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_run_start") && widget("workflow_run_start")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_run_start"));
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return shows("All done · 2/2 done"); }, 60)) << sidebar();
  // The second row's temperature changes: only that row is stale, with the reason, and it alone runs again.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", project().project()->revision},
      {"commands", {{{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second}, {"field_id", temperature}, {"value", 345}}}}}, out));
  project().refresh();
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return shows("1 rows have stale results"); }, 30)) << sidebar();
  const auto *grid = widget("workflow_run_tasks"); ASSERT_NE(grid, nullptr);
  EXPECT_EQ(grid->table->cell(0, 0), "1"); EXPECT_EQ(grid->table->cell(1, 0), "2 · stale");
  grid->table->selected.assign(1); f.drv->frame();
  EXPECT_TRUE(shows("simulate: T 340 → 345")) << sidebar();
  // Waits for the bridge's replies (a fixed number of frames is too short on slow runners).
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_run_stale") && widget("workflow_run_stale")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_run_stale"));
  ASSERT_TRUE(loop.pump_until([&] { f.screen.run_deferred(); f.drv->frame(); return shows("All done · 1/1 done"); }, 60)) << sidebar();
  EXPECT_EQ(calls("project.workflow_runs.prepare"), 2u);
}

TEST_F(WorkflowEditorPython, HomeListsAFailedRunFirstAndOpensItInTheWorkflowEditor)
{
  // Row 2 asks the synthetic solver for -5 K, which it refuses: the run stops with one failed task.
  const std::string temperature = "14141414-1414-4141-8141-141414141414", first = "15151515-1515-4151-8151-151515151515",
                    second = "16161616-1616-4161-8161-161616161616", run_id = "17171717-1717-4171-8171-171717171717";
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", {
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table_id}, {"name", "T"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"id", first}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", first}, {"field_id", temperature}, {"value", 300}},
      {{"op", "add_record"}, {"id", second}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second}, {"field_id", temperature}, {"value", -5}}}}}, out));
  const Json runnable = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
      {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
       {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", temperature}}}}}}}}};
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.update", {{"handle", handle()}, {"workflow_id", workflow_id}, {"name", "Temperature scan"},
      {"document", runnable}, {"expected_revision", revision}}, out));
  ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.prepare", {{"handle", handle()}, {"workflow_id", workflow_id},
      {"rows", {first, second}}, {"run_id", run_id}, {"expected_revision", revision}}, out));
  ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.start", {{"handle", handle()}, {"run_id", run_id}}, out));
  for (int i = 0; i < 600 && io::get_string(out.value("run", Json::object()), "status") != "stopped"; ++i) {
    loop.pump_until([] { return false; }, 0.05);
    ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.get", {{"handle", handle()}, {"run_id", run_id}}, out));
  }
  ASSERT_EQ(io::get_string(out.at("run"), "status"), "stopped");
  project().refresh();
  // Home lists it under "Needs you" and the status bar counts it.
  f.shell->restore_split_layout(&f.screen);
  ASSERT_EQ(f.area("a1").editor().type().id, kEditorWorkspace);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Failed · Workflow run · Temperature scan · 1/2 done"); }));
  EXPECT_TRUE(shows("Needs you (1)"));
  ASSERT_NE(widget("status_attention"), nullptr);
  EXPECT_EQ(widget("status_attention")->text, "Needs you: 1");
  std::string open;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) {
      if (const auto at = item.key.find("workspace_attention_open/workflow_run:" + run_id); at != std::string::npos) {
        open = item.key.substr(at);
      }
    }
  }
  ASSERT_FALSE(open.empty());
  ASSERT_NO_FATAL_FAILURE(click(open));
  // The workflow editor opens that run; opening it marked the item viewed, so the count is gone.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] {
    auto *maximized = dynamic_cast<EditorArea *>(f.screen.maximized());
    return maximized && maximized->editor().type().id == kEditorWorkflow && shows("Stopped · 1/2 done · 1 failed");
  }));
  EXPECT_EQ(widget("status_attention"), nullptr);
  EXPECT_EQ(calls("project.attention.viewed"), 1u);
  // The shown run belongs to this workflow's view (U4): another workflow and back shows it again.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  widget("workflow_list")->table->selected.assign(1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found") && !shows("1/2 done · 1 failed"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->enabled; }));
  widget("workflow_list")->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Stopped · 1/2 done · 1 failed"); }));
  EXPECT_EQ(calls("project.workflow_runs.prepare"), 1u);  // browsing never prepares or starts another run
  EXPECT_EQ(calls("project.workflow_runs.start"), 1u);
}

TEST_F(WorkflowEditorPython, ArchivedWorkflowsLeaveTheListAndStayReadOnlyUntilRestored)
{
  // A prepared (never started) run, archived together with its workflow.
  const std::string row = "15151515-1515-4151-8151-151515151515", run_id = "17171717-1717-4171-8171-171717171717";
  Json out;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision}, {"commands", {
      {{"op", "add_record"}, {"id", row}, {"table_id", table_id}}}}}, out));
  ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.prepare", {{"handle", handle()}, {"workflow_id", workflow_id},
      {"rows", {row}}, {"run_id", run_id}, {"expected_revision", revision}}, out));
  project().refresh();
  // Another workflow and back lists the run prepared outside the editor.
  const auto idle = [&] { return widget("workflow_list") && widget("workflow_list")->enabled && !project().busy(); };
  ASSERT_NO_FATAL_FAILURE(frames_until(idle));
  widget("workflow_list")->table->selected.assign(1);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("1 problems found"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until(idle));
  widget("workflow_list")->table->selected.assign(0);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_runs") && widget("workflow_runs")->table->rows == 1 &&
      widget("workflow_archive") && widget("workflow_archive")->enabled && !project().busy(); }));
  const auto before = project().project()->revision;
  EXPECT_EQ(widget("workflow_archive")->text, "Archive");
  EXPECT_EQ(widget("workflow_show_archived"), nullptr);  // nothing archived yet
  ASSERT_NO_FATAL_FAILURE(click("workflow_archive"));
  // Left out of the list but still shown, read-only and not runnable; its run went with it.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Archived: read-only until restored.") && widget("workflow_list") &&
      widget("workflow_list")->table->rows == 1 && !widget("workflow_runs"); }));
  EXPECT_TRUE(shows("This workflow is archived; restore it to run it.")) << sidebar();
  ASSERT_NE(widget("workflow_add_step"), nullptr); EXPECT_FALSE(widget("workflow_add_step")->enabled);
  EXPECT_EQ(widget("workflow_archive")->text, "Restore");
  ASSERT_NE(widget("workflow_show_archived"), nullptr);
  EXPECT_EQ(widget("workflow_show_archived")->text, "Show archived (1)");
  // Switched, the lists show only what is archived.
  widget("workflow_show_archived")->boolean.assign(true);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->table->rows == 1 &&
      widget("workflow_list")->table->cell(0, 0) == "Temperature scan"; }));
  ASSERT_NE(widget("workflow_runs_show_archived"), nullptr);
  widget("workflow_runs_show_archived")->boolean.assign(true);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_runs") && widget("workflow_runs")->table->rows == 1; }));
  // Restored with its run: editable again, and archiving never changed the project's revision.
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_archive") && widget("workflow_archive")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("workflow_archive"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !shows("Archived: read-only") && !widget("workflow_list") && !widget("workflow_runs"); }));
  widget("workflow_show_archived")->boolean.assign(false);
  widget("workflow_runs_show_archived")->boolean.assign(false);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("workflow_list") && widget("workflow_list")->table->rows == 2 &&
      widget("workflow_runs") && widget("workflow_runs")->table->rows == 1 && widget("workflow_add_step")->enabled; }));
  EXPECT_EQ(widget("workflow_show_archived"), nullptr);
  EXPECT_EQ(widget("workflow_archive")->text, "Archive");
  EXPECT_EQ(project().project()->revision, before);
  EXPECT_EQ(calls("project.archive.set"), 2u);
  EXPECT_EQ(calls("project.workflow_runs.start"), 0u);
}

TEST_F(WorkflowEditorPython, ArchivedAnalysesAreProblemsAndHomeArchivesAFailedRun)
{
  // A step whose analysis is archived is a problem until the analysis is restored (nothing is saved meanwhile).
  ASSERT_TRUE(store().archive().set("analysis", {analysis_id}, true));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Referenced analysis is archived") && shows("1 problems found"); }));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !store().archive().busy(); }));
  ASSERT_TRUE(store().archive().set("analysis", {analysis_id}, false));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("All references and links are valid."); }));
  // A failed run listed under "Needs you" is archived from Home: it leaves the list and the status bar count.
  const std::string temperature = "14141414-1414-4141-8141-141414141414", first = "15151515-1515-4151-8151-151515151515",
                    second = "16161616-1616-4161-8161-161616161616", run_id = "17171717-1717-4171-8171-171717171717";
  Json out;
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", project().project()->revision}, {"commands", {
      {{"op", "add_field"}, {"id", temperature}, {"table_id", table_id}, {"name", "T"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_record"}, {"id", first}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", first}, {"field_id", temperature}, {"value", 300}},
      {{"op", "add_record"}, {"id", second}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", second}, {"field_id", temperature}, {"value", -5}}}}}, out));
  const Json runnable = {{"format", "stk.workflow/1"}, {"ui", Json::object()}, {"steps", {
      {{"id", "cases"}, {"kind", "table"}, {"ref", {{"table", table_id}}}},
      {{"id", "simulate"}, {"kind", "simulation"}, {"ref", {{"template", "demo-synthetic/1"}}},
       {"inputs", {{"rows", {{"from", "cases.rows"}}}}}, {"parameters", {{"temperature", {{"$field", temperature}}}}}}}}};
  ASSERT_NO_FATAL_FAILURE(call("project.workflows.update", {{"handle", handle()}, {"workflow_id", workflow_id}, {"name", "Temperature scan"},
      {"document", runnable}, {"expected_revision", revision}}, out));
  ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.prepare", {{"handle", handle()}, {"workflow_id", workflow_id},
      {"rows", {first, second}}, {"run_id", run_id}, {"expected_revision", revision}}, out));
  ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.start", {{"handle", handle()}, {"run_id", run_id}}, out));
  for (int i = 0; i < 600 && io::get_string(out.value("run", Json::object()), "status") != "stopped"; ++i) {
    loop.pump_until([] { return false; }, 0.05);
    ASSERT_NO_FATAL_FAILURE(call("project.workflow_runs.get", {{"handle", handle()}, {"run_id", run_id}}, out));
  }
  ASSERT_EQ(io::get_string(out.at("run"), "status"), "stopped");
  project().refresh();
  f.shell->restore_split_layout(&f.screen);
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return shows("Failed · Workflow run · Temperature scan · 1/2 done"); }));
  ASSERT_NE(widget("status_attention"), nullptr);
  std::string shelve;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) {
      if (const auto at = item.key.find("workspace_attention_archive/workflow_run:" + run_id); at != std::string::npos) {
        shelve = item.key.substr(at);
      }
    }
  }
  ASSERT_FALSE(shelve.empty());
  EXPECT_EQ(widget(shelve)->text, "Archive");
  const auto before = project().project()->revision;
  ASSERT_NO_FATAL_FAILURE(click(shelve));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !shows("Failed · Workflow run") && !widget("status_attention"); }));
  EXPECT_EQ(project().project()->revision, before);
  EXPECT_EQ(calls("project.attention.viewed"), 0u);  // archived, not merely seen
  EXPECT_EQ(calls("project.workflow_runs.start"), 1u);
}

}  // namespace
}  // namespace stk::app
