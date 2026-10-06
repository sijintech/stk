/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
using Reply = bridge::Result<Json>;
namespace fs = std::filesystem;
constexpr const char *analysis_id = "6b0f5c3e-2d1a-4c9e-9f7b-3a8e5d4c2b10";
std::string exact(const Json &value) { return io::python_json_dumps(value, true, true); }
// Records every bridge method (to prove what was and was not sent) and can hold validation replies.
constexpr const char *kLinksBridge = R"PY(
import json
from pathlib import Path
import sys
import threading
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main

control = Path(sys.argv.pop(1))
lock = threading.Lock()
original_run, original_send = Bridge._run, Bridge.send

def run(self, identity, method, params):
    with lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'method': method, 'params': params}, ensure_ascii=True) + '\n')
    return original_run(self, identity, method, params)

def send(self, message, method=None):
    if method == 'project.analyses.update' and 'result' in message and (control / 'lost').exists():
        return  # the write happened; its reply never arrives
    if method == 'graph.validate' and 'result' in message and (control / 'hold').exists():
        (control / 'held').write_text('ready', encoding='utf-8')
        while not (control / 'release').exists():
            if self.closing.wait(0.01):
                return
    return original_send(self, message, method)

Bridge._run, Bridge.send = run, send
main()
)PY";

class AnalysisLinksEditorPython : public ::testing::Test {
 protected:
  bridge::test::TempDir directory{"analysis-links-ui"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 2200};
  std::unique_ptr<bridge::Client> client;
  Json document;
  int64_t revision = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  ViewerState &viewer() { return store().viewer(); }
  EditorArea &area() { return f.area("a2"); }
  std::string handle() { return project().project()->handle; }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  const ui::Widget *source(const std::string &node, const std::string &port)
  {
    return widget("analysis_link/" + node + "/" + port + "/analysis_link_source");
  }
  std::string dump()
  {
    std::string out;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.key.find("link") != std::string::npos || item.text.find("Select a node") != std::string::npos) {
          out += "\n" + item.key + " | " + item.text;
        }
      }
    }
    return out;
  }
  bool shows(const std::string &text)
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) { if (item.text.find(text) != std::string::npos) { return true; } }
    }
    return false;
  }
  Json calls(const std::string &method)
  {
    Json result = Json::array(); std::ifstream file(directory.path() / "calls.jsonl"); std::string line;
    while (std::getline(file, line)) { auto item = io::parse_json(line); if (item.at("method") == method) { result.push_back(item.at("params")); } }
    return result;
  }
  void call(const std::string &method, Json params, Json &out)
  {
    auto reply = std::make_shared<std::optional<Reply>>(); auto future = client->call(method, std::move(params));
    future.then([reply](auto value) { *reply = std::move(value); });
    const bool done = loop.pump_until([&] { return reply->has_value(); }, 30);
    if (!done) { future.cancel(); }
    ASSERT_TRUE(done) << client->bridge_log().text();
    ASSERT_TRUE(reply->value().ok()) << reply->value().error().describe(); out = reply->value().value();
  }
  void read(Json &out) { ASSERT_NO_FATAL_FAILURE(call("project.analyses.get", {{"handle", handle()}, {"analysis_id", analysis_id}}, out)); }
  void frames_until(const std::function<bool()> &condition)
  {
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return condition(); }, 30)) << client->bridge_log().text();
  }
  void click(const std::string &key)
  {
    const auto *value = widget(key); ASSERT_NE(value, nullptr) << key; ASSERT_TRUE(value->enabled) << key;
    ASSERT_TRUE(value->on_click); value->on_click(); f.drv->frame();
  }
  void select_node(const std::string &id)
  {
    const auto *nodes = widget("graph_node_select"); ASSERT_NE(nodes, nullptr);
    const auto found = std::find_if(nodes->items.begin(), nodes->items.end(),
        [&](const std::string &item) { return item.rfind(id + " / ", 0) == 0; });
    ASSERT_NE(found, nodes->items.end()) << id;
    nodes->index.assign(int(found - nodes->items.begin())); f.drv->frame();
  }
  /** Choose a dropdown entry of node.port by its label prefix (e.g. "component.out"). */
  void link(const std::string &node, const std::string &port, const std::string &label)
  {
    ASSERT_NO_FATAL_FAILURE(select_node(node));
    const auto *dropdown = source(node, port); ASSERT_NE(dropdown, nullptr) << node << "." << port << dump();
    ASSERT_TRUE(dropdown->enabled);
    const auto found = std::find_if(dropdown->items.begin(), dropdown->items.end(),
        [&](const std::string &item) { return item.rfind(label, 0) == 0; });
    std::string listed;
    for (const auto &item : dropdown->items) { listed += "\n  " + item; }
    ASSERT_NE(found, dropdown->items.end()) << label << listed << dump();
    dropdown->index.assign(int(found - dropdown->items.begin())); f.drv->frame();
  }
  void validate()
  {
    const auto before = calls("graph.validate").size();
    ASSERT_NO_FATAL_FAILURE(click("analysis_links_validate"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return calls("graph.validate").size() == before + 1 &&
        widget("analysis_links_validate") && widget("analysis_links_validate")->enabled; }));
  }
  bool save_enabled()
  {
    const auto *save = widget("analysis_parameters_save");
    return save && save->enabled;
  }
  void save()
  {
    ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision > revision &&
        widget("analysis_parameters_save") && !widget("analysis_parameters_save")->enabled; }));
  }
  Json issues()
  {
    // The issue table is the candidate validation reply as shown.
    const auto *table = widget("analysis_links_issues");
    Json codes = Json::array();
    if (table && table->table) {
      for (int row = 0; row < table->table->rows; ++row) { codes.push_back(table->table->cell(row, 1)); }
    }
    return codes;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const auto *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for link editing"; }
    { std::ofstream file(directory.path() / "bridge.py"); file << kLinksBridge; ASSERT_TRUE(file.good()); }
    bridge::ClientOptions options;
    options.python.configured = python; options.state_dir = directory.str() + "/bridge"; options.cache_dir = directory.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime"; options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), directory.str(), "--stdio",
        "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    options.executor = loop.executor(); options.strict = options.validate = true; options.call_timeout_s = 10;
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    viewer().set_auto_evaluate(false); viewer().prefetch_neighbours = false;
    ASSERT_TRUE(project().create(directory.str() + "/project", "Link edits"));
    ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy(); }, 30));
    document = {{"format", "stk.analysis-document/1"},
        {"graph", io::read_json_file(fs::path(STK_REPO_ROOT) / "suan/graph/presets/scalar-volume.json").at("graph")},
        {"parameters", {{"path", "input.dat"}, {"field", "input"}, {"component", 1}, {"unit", nullptr}}},
        {"outputs", Json::array({"view"})}};
    Json saved;
    ASSERT_NO_FATAL_FAILURE(call("project.analyses.create", {{"handle", handle()}, {"analysis_id", analysis_id},
        {"name", "Linked analysis"}, {"document", document}, {"expected_revision", 0}}, saved));
    revision = saved.at("revision").get<int64_t>(); project().refresh();
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(area().set_tab_type(0, kEditorAnalysisGraph)); ASSERT_TRUE(area().editor().load_state({{"saved", true}}));
    f.screen.set_maximized(&area()); area().find_region(EditorArea::kSidebar)->set_size_1x(560); f.drv->frame();
    ASSERT_NO_FATAL_FAILURE(click("analysis_list"));
    ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_documents") != nullptr; }));
    widget("analysis_documents")->table->selected.assign(0);
    // Wait for the node catalog too: without it every input is read-only.
    ASSERT_NO_FATAL_FAILURE(frames_until([&] {
      const auto *ports = widget("graph_ports");
      return widget("analysis_parameters") && widget("graph_node_select") && ports && ports->table && ports->table->rows > 0 &&
          ports->table->cell(0, 2) != "?" && !shows("Reading the node catalog");
    }));
    // The Links panel starts collapsed; open it the way a user does.
    ASSERT_EQ(widget("analysis_links_validate"), nullptr);
    ASSERT_NE(widget("analysis_links_panel"), nullptr);
    const auto [x, y] = f.widget_center(widget("analysis_links_panel")->key);
    f.drv->click(x, y); f.drv->frame();
    ASSERT_NE(widget("analysis_links_validate"), nullptr) << dump();
  }
  void TearDown() override
  {
    // Validation, editing and saving never evaluate, prepare or start anything, nor touch the Viewer.
    EXPECT_EQ(viewer().evaluations_started(), 0); EXPECT_FALSE(viewer().evaluating()); EXPECT_FALSE(viewer().payload());
    EXPECT_TRUE(calls("graph.evaluate").empty()); EXPECT_TRUE(calls("project.analysis_runs.prepare").empty());
    EXPECT_TRUE(calls("project.analysis_runs.start").empty());
    viewer().close(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); } loop.run_ready();
  }
};

TEST_F(AnalysisLinksEditorPython, ValidatedReplacementSavesOneCasUpdateChangingOnlyThatLinkAndUndoRestores)
{
  ASSERT_NO_FATAL_FAILURE(link("box", "in", "component.out"));
  EXPECT_TRUE(shows("box.in: src.out → component.out"));
  // Saving a link change needs an explicit passing validation of this exact candidate.
  EXPECT_FALSE(save_enabled());
  const auto save_old = widget("analysis_parameters_save")->on_click;
  save_old(); loop.run_ready();
  EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_NO_FATAL_FAILURE(validate());
  EXPECT_TRUE(shows("passed static validation")); EXPECT_TRUE(issues().empty());
  const auto checked = calls("graph.validate").back();
  auto expected = document;
  for (auto &node : expected["graph"]["nodes"]) { if (node.at("id") == "box") { node["inputs"]["in"] = {{"from", "component.out"}}; } }
  EXPECT_EQ(exact(checked.at("graph")), exact(expected.at("graph")));
  EXPECT_EQ(exact(checked.at("parameters")), exact(expected.at("parameters")));
  ASSERT_TRUE(save_enabled());
  ASSERT_NO_FATAL_FAILURE(save());
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
  EXPECT_EQ(current.at("analysis").at("name"), "Linked analysis");
  ASSERT_EQ(calls("project.analyses.update").size(), 1u);
  EXPECT_EQ(calls("project.analyses.update")[0].at("expected_revision"), revision);
  EXPECT_EQ(project().project()->revision, revision + 1);
  EXPECT_FALSE(shows("box.in: src.out"));  // the draft adopted the saved candidate
  ASSERT_TRUE(project().undo());
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy(); }));
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
}

TEST_F(AnalysisLinksEditorPython, LostSaveReplyIsReadBackAndAdoptedWithoutResubmitting)
{
  ASSERT_NO_FATAL_FAILURE(link("box", "in", "component.out"));
  ASSERT_NO_FATAL_FAILURE(validate());
  { std::ofstream lost(directory.path() / "lost"); }
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameters_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_check_save") && widget("analysis_check_save")->enabled; }));
  // While the outcome is unknown no further link edit or check can be made.
  const auto *pending = source("box", "in");
  EXPECT_TRUE(!pending || !pending->enabled) << dump();
  ASSERT_NE(widget("analysis_links_validate"), nullptr) << dump();
  EXPECT_FALSE(widget("analysis_links_validate")->enabled);
  fs::remove(directory.path() / "lost");
  ASSERT_NO_FATAL_FAILURE(click("analysis_check_save"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && !widget("analysis_check_save") &&
      widget("analysis_links_validate") && !save_enabled(); }));
  EXPECT_EQ(calls("project.analyses.update").size(), 1u);  // read back, never sent again
  EXPECT_FALSE(shows("box.in: src.out"));
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  EXPECT_EQ(current.at("analysis").at("document").at("graph").at("nodes")[4].at("inputs").at("in"), Json({{"from", "component.out"}}));
}

TEST_F(AnalysisLinksEditorPython, TypeMismatchAndCycleAreReportedAndSaveStaysDisabled)
{
  ASSERT_NO_FATAL_FAILURE(link("volume", "in", "camera.camera"));
  ASSERT_NO_FATAL_FAILURE(validate());
  EXPECT_TRUE(shows("candidate is invalid"));
  const auto mismatch = issues();
  EXPECT_NE(std::find(mismatch.begin(), mismatch.end(), "port_mismatch"), mismatch.end()) << mismatch.dump();
  EXPECT_FALSE(save_enabled());
  // component -> volume -> component: graph.validate reports the cycle.
  ASSERT_NO_FATAL_FAILURE(link("volume", "in", "component.out"));
  ASSERT_NO_FATAL_FAILURE(link("component", "in", "volume.layer"));
  EXPECT_EQ(widget("analysis_links_issues"), nullptr);  // the earlier verdict is not shown for a new candidate
  ASSERT_NO_FATAL_FAILURE(validate());
  const auto cycle = issues();
  EXPECT_NE(std::find(cycle.begin(), cycle.end(), "cycle"), cycle.end()) << cycle.dump();
  EXPECT_FALSE(save_enabled());
  EXPECT_TRUE(calls("project.analyses.update").empty());
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current)); EXPECT_EQ(exact(current.at("analysis").at("document")), exact(document));
}

TEST_F(AnalysisLinksEditorPython, LateRepliesAndLaterEditsOrRevisionsInvalidateAPassingCheck)
{
  ASSERT_NO_FATAL_FAILURE(link("box", "in", "component.out"));
  ASSERT_NO_FATAL_FAILURE(validate());
  ASSERT_TRUE(save_enabled());
  // Any further edit makes a different candidate: the old pass no longer counts.
  ASSERT_NO_FATAL_FAILURE(link("volume", "in", "src.out"));
  EXPECT_FALSE(save_enabled()); EXPECT_FALSE(shows("passed static validation"));
  // A reply that arrives after another edit belongs to the earlier candidate and is not adopted.
  { std::ofstream hold(directory.path() / "hold"); }
  ASSERT_NO_FATAL_FAILURE(click("analysis_links_validate"));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  ASSERT_NO_FATAL_FAILURE(link("volume", "in", "component.out"));
  fs::remove(directory.path() / "hold");
  { std::ofstream release(directory.path() / "release"); }
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return widget("analysis_links_validate") && widget("analysis_links_validate")->enabled; }));
  EXPECT_FALSE(save_enabled()); EXPECT_FALSE(shows("passed static validation"));
  // A passing check followed by an external project revision leaves the draft detached instead.
  ASSERT_NO_FATAL_FAILURE(validate());
  ASSERT_TRUE(save_enabled());
  Json applied;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", {{"handle", handle()}, {"expected_revision", revision},
      {"commands", Json::array({{{"op", "create_table"}, {"id", "77777777-7777-4777-8777-777777777777"}, {"name", "Other"}}})}}, applied));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && project().project()->revision == revision + 1; }));
  EXPECT_FALSE(save_enabled());
  EXPECT_TRUE(calls("project.analyses.update").empty());
}

TEST_F(AnalysisLinksEditorPython, MultiInputsAreReadOnlyRequiredInputsKeepALinkAndOptionalOnesDisconnect)
{
  ASSERT_NO_FATAL_FAILURE(select_node("scene"));
  EXPECT_EQ(source("scene", "layers"), nullptr);
  EXPECT_TRUE(shows("multi-input lists are not edited"));
  const auto *camera = source("scene", "camera"); ASSERT_NE(camera, nullptr);
  EXPECT_EQ(camera->items.front(), "Disconnect (optional input)");
  ASSERT_NO_FATAL_FAILURE(select_node("volume"));
  const auto *required = source("volume", "in"); ASSERT_NE(required, nullptr);
  EXPECT_EQ(std::count_if(required->items.begin(), required->items.end(),
      [](const std::string &item) { return item.find("Disconnect") != std::string::npos || item == "not connected"; }), 0);
  // The candidate list is every other declared output, not a type-filtered guess.
  EXPECT_NE(std::find_if(required->items.begin(), required->items.end(),
      [](const std::string &item) { return item.rfind("camera.camera", 0) == 0; }), required->items.end());
  ASSERT_NO_FATAL_FAILURE(link("scene", "camera", "Disconnect"));
  ASSERT_NO_FATAL_FAILURE(validate());
  ASSERT_TRUE(save_enabled()) << issues().dump();
  ASSERT_NO_FATAL_FAILURE(save());
  Json current;
  ASSERT_NO_FATAL_FAILURE(read(current));
  auto expected = document;
  for (auto &node : expected["graph"]["nodes"]) { if (node.at("id") == "scene") { node["inputs"].erase("camera"); } }
  EXPECT_EQ(exact(current.at("analysis").at("document")), exact(expected));
}

TEST_F(AnalysisLinksEditorPython, UnknownNodeTypesStayReadOnly)
{
  auto unknown = document;
  unknown["graph"]["nodes"].push_back({{"id", "future"}, {"type", "fixture.unknown.node@1"}, {"inputs", {{"in", {{"from", "src.out"}}}}}});
  Json saved;
  ASSERT_NO_FATAL_FAILURE(call("project.analyses.update", {{"handle", handle()}, {"analysis_id", analysis_id},
      {"name", "Linked analysis"}, {"document", unknown}, {"expected_revision", revision}}, saved));
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(frames_until([&] { return !project().busy() && widget("analysis_reload") && widget("analysis_reload")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(click("analysis_reload"));
  ASSERT_NO_FATAL_FAILURE(frames_until([&] {
    const auto *nodes = widget("graph_node_select");
    return nodes && std::any_of(nodes->items.begin(), nodes->items.end(), [](const std::string &item) { return item.rfind("future / ", 0) == 0; });
  }));
  ASSERT_NO_FATAL_FAILURE(select_node("future"));
  EXPECT_EQ(source("future", "in"), nullptr);
  EXPECT_TRUE(shows("node type is not in the catalog"));
}

TEST_F(AnalysisLinksEditorPython, InvalidParameterTextIsKeptAndBlocksLinkEditsUntilResolved)
{
  ASSERT_NO_FATAL_FAILURE(link("box", "in", "component.out"));
  // Pick a parameter and leave invalid raw text in its editor.
  const auto *table = widget("analysis_parameters"); ASSERT_NE(table, nullptr);
  int row = -1;
  for (int index = 0; index < table->table->rows; ++index) { if (table->table->cell(index, 0) == "component") { row = index; } }
  ASSERT_GE(row, 0); table->table->selected.assign(row); f.drv->frame();
  const auto *input = widget("analysis_parameter_value"); ASSERT_NE(input, nullptr);
  input->string.assign("1e"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_parameter_apply"));
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  ASSERT_NO_FATAL_FAILURE(select_node("volume"));
  EXPECT_FALSE(source("volume", "in")->enabled);
  EXPECT_FALSE(widget("analysis_links_validate")->enabled);
  EXPECT_FALSE(save_enabled());
  EXPECT_EQ(widget("analysis_parameter_value")->string.value(), "1e");
  EXPECT_TRUE(shows("box.in: src.out → component.out"));  // the accepted link edit survives too
  EXPECT_TRUE(calls("graph.validate").empty()); EXPECT_TRUE(calls("project.analyses.update").empty());
}

}  // namespace
}  // namespace stk::app
