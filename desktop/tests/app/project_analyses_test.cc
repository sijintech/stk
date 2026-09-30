/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_analyses.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
using Result = bridge::Result<Json>;
namespace fs = std::filesystem;

Json saved_document()
{
  return {{"format", "stk.analysis-document/1"},
      {"graph", {{"schema", "stk.graph/1"}, {"nodes", Json::array({{{"id", "run"},
          {"type", "stk.source.muferro_run@1"}, {"params", {{"binding", "run"}}}}})},
          {"outputs", {{"frames", "run.frames"}}}}},
      {"parameters", Json::object()}, {"outputs", Json::array({"frames"})}};
}

std::string exact_document(const Json &document)
{
  // Backend cells canonicalize object keys; submitted numeric types remain significant.
  return io::python_json_dumps(document, true, true);
}

// The normal Python bridge performs all real SQLite work and protocol validation. Only its
// outgoing analysis response can be held/dropped/altered, after the write has already committed.
// This works with Windows pipes too and never requires the POSIX native fake or a model provider.
constexpr const char *kAnalysisBridge = R"PY(
import copy
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
    path = control / 'mode'
    mode = path.read_text(encoding='utf-8') if path.exists() else ''
    if method in ('project.analyses.create', 'project.analyses.update') and 'result' in message:
        if mode == 'lost':
            return
        if mode == 'malformed':
            message = copy.deepcopy(message)
            message['result']['record_id'] = '00000000-0000-4000-8000-000000000000'
    if method == 'project.analyses.get' and 'result' in message and mode == 'hold':
        (control / 'held').write_text('ready', encoding='utf-8')
        while not (control / 'release').exists():
            if self.closing.wait(0.01):
                return
    return original_send(self, message, method)

Bridge._run, Bridge.send = run, send
main()
)PY";

class ProjectAnalysesPython : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir directory{"project-analyses"};
  AppStore store;
  std::unique_ptr<bridge::Client> client, peer;
  std::unique_ptr<ProjectAnalyses> analyses;
  std::shared_ptr<const ViewerGraphInspection> viewer_before;
  std::string python;

  ProjectState &project() { return store.project(); }

  void write_text(const fs::path &path, const std::string &value)
  {
    std::ofstream out(path, std::ios::binary); out << value; ASSERT_TRUE(out.good());
  }

  void start_client(std::unique_ptr<bridge::Client> &target, const std::string &name, const bool controlled)
  {
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = directory.str() + "/" + name;
    options.cache_dir = directory.str() + "/cache-" + name;
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = directory.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = directory.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.executor = loop.executor(); options.strict = options.validate = true;
    if (controlled) {
      options.command = {python, "-u", core::path_to_utf8(directory.path() / "bridge.py"), directory.str(),
          "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
      options.call_timeout_s = 5;
    }
    target = bridge::Client::create(options);
    ASSERT_TRUE(target->start()); ASSERT_TRUE(target->wait_ready(60)) << target->bridge_log().text();
  }

  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON for saved analysis integration"; }
    ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "bridge.py", kAnalysisBridge));
    ASSERT_NO_FATAL_FAILURE(start_client(client, "bridge", true));
    loop.run_ready(); store.set_bridge(client.get()); project().sync();
    ASSERT_TRUE(loop.pump_until([&] { return project().ready(); }, 30));
    ASSERT_TRUE(project().create(directory.str() + "/project", "Saved analyses"));
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && project().loaded() && !project().recent_loading(); }, 30))
        << project().error();
    analyses = std::make_unique<ProjectAnalyses>(store);
    ASSERT_TRUE(analyses->supported());
    viewer_before = store.viewer().graph_inspection();
  }

  void TearDown() override
  {
    if (viewer_before) { EXPECT_EQ(store.viewer().graph_inspection(), viewer_before); }
    EXPECT_EQ(store.viewer().evaluations_started(), 0); EXPECT_FALSE(store.viewer().evaluating());
    analyses.reset(); project().attach(nullptr); store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    if (peer) { peer->close(); EXPECT_EQ(peer->stats().schema_violations, 0u); }
    loop.run_ready();
  }

  void settled()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !analyses->busy() && !project().busy() && !project().recent_loading(); }, 30))
        << analyses->error() << project().error() << client->bridge_log().text();
  }

  void call(bridge::Client &target, const std::string &method, Json params, Json &out)
  {
    std::optional<Result> result;
    target.call(method, std::move(params)).then([&](auto value) { result = std::move(value); });
    ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); }, 30)) << target.bridge_log().text();
    ASSERT_TRUE(result->ok()) << result->error().describe();
    out = result->value();
  }

  void call(const std::string &method, Json params, Json &out) { call(*client, method, std::move(params), out); }

  Json calls(const std::string &method)
  {
    Json matches = Json::array(); std::ifstream file(directory.path() / "calls.jsonl"); std::string line;
    while (std::getline(file, line)) {
      const auto entry = io::parse_json(line);
      if (entry.at("method") == method) { matches.push_back(entry.at("params")); }
    }
    return matches;
  }

  void create_one()
  {
    ASSERT_TRUE(analyses->save_new("Saved graph", saved_document()));
    ASSERT_NO_FATAL_FAILURE(settled());
    ASSERT_FALSE(analyses->selected().is_null()) << analyses->error();
    ASSERT_EQ(analyses->selected_revision(), 1);
  }

  std::string field_id(const std::string &name)
  {
    for (const auto &table : project().tables()) {
      for (const auto &field : table.fields) { if (field.name == name) { return field.id; } }
    }
    ADD_FAILURE() << "Missing analysis field " << name;
    return {};
  }
};

TEST_F(ProjectAnalysesPython, ConstructionReadsAndSyncDoNotCreateAnythingOrTouchTheViewer)
{
  const auto before = client->stats().calls_sent;
  ProjectAnalyses other(store);
  for (int i = 0; i < 4; ++i) { other.sync(); }
  EXPECT_EQ(client->stats().calls_sent, before);
  EXPECT_TRUE(other.page().is_null()); EXPECT_TRUE(other.selected().is_null());
  ASSERT_TRUE(analyses->load_page()); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->page().at("total"), 0); EXPECT_TRUE(analyses->page().at("analyses").empty());
  EXPECT_TRUE(project().tables().empty()); EXPECT_EQ(project().project()->revision, 0);
  EXPECT_FALSE(analyses->rename("Nothing selected")); EXPECT_FALSE(analyses->check_pending());
  EXPECT_TRUE(calls("project.analyses.create").empty()); EXPECT_TRUE(calls("graph.evaluate").empty());
}

TEST_F(ProjectAnalysesPython, OneSaveIsOneUndoableEditAndReopensUnderTheSameRecordIdentity)
{
  ASSERT_NO_FATAL_FAILURE(create_one());
  const auto identity = analyses->selected().at("id").get<std::string>();
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(saved_document()));
  EXPECT_FALSE(analyses->uncertain()); EXPECT_TRUE(analyses->pending_id().empty());
  Json history; ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", analyses->handle()}}, history));
  ASSERT_EQ(history.at("history").size(), 1u);
  ASSERT_EQ(calls("project.analyses.create").size(), 1u);
  EXPECT_EQ(calls("project.analyses.create")[0].at("analysis_id"), identity);
  ASSERT_TRUE(project().undo()); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(project().tables().empty()); EXPECT_TRUE(analyses->stale());
  EXPECT_FALSE(analyses->rename("Cannot rename an undone selection"));
  ASSERT_TRUE(project().redo()); ASSERT_NO_FATAL_FAILURE(settled());
  const auto old_handle = analyses->handle();
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(settled()); analyses->sync();
  EXPECT_FALSE(analyses->supported()); EXPECT_TRUE(analyses->selected().is_null());
  ASSERT_TRUE(project().open(directory.str() + "/project")); ASSERT_NO_FATAL_FAILURE(settled()); analyses->sync();
  ASSERT_NE(analyses->handle(), old_handle);
  ASSERT_TRUE(analyses->load(identity)); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->selected().at("id"), identity);
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(saved_document()));
  EXPECT_EQ(analyses->selected_revision(), 3);
  EXPECT_EQ(calls("project.analyses.create").size(), 1u);
}

TEST_F(ProjectAnalysesPython, RenameDetectsAnExternalRevisionAndNeverRebasesTheOldDocument)
{
  ASSERT_NO_FATAL_FAILURE(create_one());
  const auto identity = analyses->selected().at("id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(start_client(peer, "peer", false));
  Json opened, result;
  ASSERT_NO_FATAL_FAILURE(call(*peer, "project.open", {{"directory", directory.str() + "/project"}}, opened));
  auto external = saved_document(); external["outputs"] = Json::array();
  ASSERT_NO_FATAL_FAILURE(call(*peer, "project.analyses.update", {{"handle", opened.at("project").at("handle")},
      {"analysis_id", identity}, {"name", "External writer"}, {"document", external}, {"expected_revision", 1}}, result));
  EXPECT_EQ(project().project()->revision, 1); EXPECT_FALSE(analyses->stale());
  ASSERT_TRUE(analyses->rename("Stale rename")); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_FALSE(analyses->uncertain()); EXPECT_TRUE(analyses->pending_id().empty());
  EXPECT_NE(analyses->error().find("conflict"), std::string::npos);
  EXPECT_EQ(project().project()->revision, 2); EXPECT_TRUE(analyses->stale());
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(saved_document()));
  ASSERT_TRUE(analyses->load(identity)); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(external)); EXPECT_FALSE(analyses->stale());
  ASSERT_TRUE(analyses->rename("Renamed only")); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->selected().at("name"), "Renamed only");
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(external)); EXPECT_EQ(analyses->selected_revision(), 3);
  EXPECT_EQ(calls("project.analyses.create").size(), 1u); EXPECT_EQ(calls("project.analyses.update").size(), 2u);
}

class ProjectAnalysesUnreadable : public ProjectAnalysesPython, public ::testing::WithParamInterface<bool> {};
TEST_P(ProjectAnalysesUnreadable, InvalidAndFutureRowsStayInspectableAndCannotBeRenamed)
{
  ASSERT_NO_FATAL_FAILURE(create_one());
  const auto identity = analyses->selected().at("id").get<std::string>();
  const bool future = GetParam();
  const Json value = future ? Json("stk.analysis-document/2") : Json{{"broken", true}};
  const Json command = {{"op", "set_cell"}, {"table_id", project().tables()[0].id},
      {"record_id", identity}, {"field_id", field_id(future ? "Format" : "Graph")}, {"value", value}};
  const Json params = {{"handle", analyses->handle()}, {"expected_revision", 1},
      {"commands", Json::array({command})}};
  Json result;
  ASSERT_NO_FATAL_FAILURE(call("project.apply", params, result));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(analyses->load(identity)); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->selected().at("state"), future ? "unsupported" : "invalid");
  EXPECT_TRUE(analyses->selected().at("document").is_null());
  EXPECT_FALSE(analyses->selected().at("error").get<std::string>().empty());
  EXPECT_FALSE(analyses->rename("Do not repair implicitly"));
  ASSERT_TRUE(analyses->load_page()); ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_EQ(analyses->page().at("analyses").size(), 1u);
  EXPECT_EQ(analyses->page().at("analyses")[0].at("state"), future ? "unsupported" : "invalid");
  EXPECT_TRUE(calls("project.analyses.update").empty()); EXPECT_EQ(project().project()->revision, 2);
}
INSTANTIATE_TEST_SUITE_P(Rows, ProjectAnalysesUnreadable, ::testing::Bool(),
    [](const ::testing::TestParamInfo<bool> &info) { return info.param ? "Future" : "Invalid"; });

class ProjectAnalysesUncertain : public ProjectAnalysesPython, public ::testing::WithParamInterface<const char *> {};
TEST_P(ProjectAnalysesUncertain, AmbiguousCommittedSaveUsesOnlyExplicitReadbackOfItsOriginalUuid)
{
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "mode", GetParam()));
  ASSERT_TRUE(analyses->save_new("Saved graph", saved_document()));
  const auto identity = analyses->pending_id(); ASSERT_FALSE(identity.empty());
  EXPECT_TRUE(analyses->uncertain()); EXPECT_FALSE(analyses->save_new("Duplicate", saved_document()));
  ASSERT_NO_FATAL_FAILURE(settled());
  ASSERT_TRUE(analyses->uncertain()) << analyses->error(); EXPECT_EQ(analyses->pending_id(), identity);
  EXPECT_FALSE(analyses->save_new("Duplicate", saved_document()));
  EXPECT_EQ(project().project()->revision, 1); EXPECT_EQ(calls("project.analyses.create").size(), 1u);
  ASSERT_TRUE(analyses->check_pending()); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_FALSE(analyses->uncertain()); EXPECT_TRUE(analyses->pending_id().empty());
  EXPECT_EQ(analyses->selected().at("id"), identity);
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(saved_document()));
  EXPECT_EQ(analyses->notice(), "analysis_documents.recovered");
  EXPECT_EQ(calls("project.analyses.create").size(), 1u); EXPECT_TRUE(calls("project.analyses.update").empty());
  ASSERT_EQ(calls("project.analyses.get").size(), 1u);
  EXPECT_EQ(calls("project.analyses.get")[0].at("analysis_id"), identity);
  Json history; ASSERT_NO_FATAL_FAILURE(call("project.history", {{"handle", analyses->handle()}}, history));
  EXPECT_EQ(history.at("history").size(), 1u);
}
INSTANTIATE_TEST_SUITE_P(Replies, ProjectAnalysesUncertain, ::testing::Values("malformed", "lost"),
    [](const ::testing::TestParamInfo<const char *> &info) { return std::string(info.param); });

TEST_F(ProjectAnalysesPython, DefiniteServerRejectionClearsRecoveryStateWithoutCreatingARecord)
{
  ASSERT_TRUE(analyses->save_new(" ", saved_document())); // Wire-valid, rejected by stored-name validation.
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_FALSE(analyses->uncertain()); EXPECT_TRUE(analyses->pending_id().empty());
  EXPECT_FALSE(analyses->check_pending()); EXPECT_FALSE(analyses->error().empty());
  EXPECT_EQ(project().project()->revision, 0); EXPECT_TRUE(project().tables().empty());
  ASSERT_TRUE(analyses->save_new("Corrected", saved_document())); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(project().project()->revision, 1);
}

TEST_F(ProjectAnalysesPython, LateReadCannotPopulateAnotherProject)
{
  ASSERT_NO_FATAL_FAILURE(create_one());
  const auto identity = analyses->selected().at("id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "mode", "hold"));
  ASSERT_TRUE(analyses->load(identity));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  ASSERT_TRUE(project().create(directory.str() + "/other-project", "Other"));
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy() && project().loaded() && !project().recent_loading(); }, 30));
  const auto new_handle = project().project()->handle;
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "release", "ready"));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->handle(), new_handle); EXPECT_TRUE(analyses->selected().is_null());
  EXPECT_TRUE(analyses->page().is_null()); EXPECT_FALSE(analyses->uncertain());
  EXPECT_EQ(project().project()->revision, 0); EXPECT_TRUE(project().tables().empty());
}

TEST_F(ProjectAnalysesPython, ReplacementBridgeFencesTheOldReadEvenWhenTheProjectUuidIsTheSame)
{
  ASSERT_NO_FATAL_FAILURE(create_one());
  const auto identity = analyses->selected().at("id").get<std::string>();
  const auto project_id = project().project()->id;
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "mode", "hold"));
  ASSERT_TRUE(analyses->load(identity));
  ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(directory.path() / "held"); }, 30));
  ASSERT_NO_FATAL_FAILURE(start_client(peer, "replacement", false));
  store.set_bridge(peer.get()); project().sync();
  ASSERT_TRUE(loop.pump_until([&] { return project().loaded() && !project().busy() && !project().recent_loading(); }, 30));
  EXPECT_EQ(project().project()->id, project_id);
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "release", "ready"));
  ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_TRUE(analyses->selected().is_null()); EXPECT_FALSE(analyses->uncertain());
  EXPECT_EQ(analyses->handle(), project().project()->handle);
  ASSERT_TRUE(analyses->load(identity)); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(analyses->selected().at("id"), identity);
  EXPECT_EQ(calls("project.analyses.create").size(), 1u);
}

TEST_F(ProjectAnalysesPython, DestroyedControllerIgnoresItsReplyAndLogsAnUncertainSaveIdentity)
{
  ASSERT_NO_FATAL_FAILURE(write_text(directory.path() / "mode", "lost"));
  ASSERT_TRUE(analyses->save_new("Saved graph", saved_document()));
  const auto identity = analyses->pending_id();
  ASSERT_TRUE(loop.pump_until([&] { return project().project()->revision == 1 && !project().busy(); }, 30));
  ASSERT_TRUE(analyses->busy());
  store.app_log().clear(); analyses.reset();
  std::string log;
  for (size_t line = 0; line < store.app_log().line_count(); ++line) { log += store.app_log().line(line); }
  EXPECT_NE(log.find(identity), std::string::npos);
  loop.run_ready();
  analyses = std::make_unique<ProjectAnalyses>(store);
  EXPECT_TRUE(analyses->selected().is_null()); EXPECT_FALSE(analyses->uncertain());
  ASSERT_TRUE(analyses->load(identity)); ASSERT_NO_FATAL_FAILURE(settled());
  EXPECT_EQ(exact_document(analyses->selected().at("document")), exact_document(saved_document()));
  EXPECT_EQ(calls("project.analyses.create").size(), 1u);
}

}  // namespace
}  // namespace stk::app
