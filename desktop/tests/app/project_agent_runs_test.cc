/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_agent.hh"
#include "stk/app/project_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;

// Wire fixture only: every agent method is replaced; no model, executable, connection or Runtime is used.
// The real bridge still owns project opening and protocol dispatch. New-method schemas are tested in Python.
constexpr const char *kRunWire = R"PY(
import copy
import json
from pathlib import Path
import sys
import threading
import time
from suan.desktop_bridge import server
from suan.desktop_bridge.__main__ import main
from suan.desktop_bridge.protocol import BridgeError

control = Path(sys.argv.pop(1))
original_init = server.Bridge.__init__
original_validate = server.bridge_schema.validate_params
server.bridge_schema.validate_params = lambda m, p: [] if m.startswith('project.agent.') else original_validate(m, p)

def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    sessions = {}
    calls_lock = threading.Lock()
    def session(identity):
        if identity not in sessions:
            item = {'item_id': 'approve:' + identity, 'kind': 'start_run', 'run_id': 'run:' + identity,
                    'plan_sha256': 'a' * 64, 'request_sha256': 'b' * 64, 'expected_revision': 0}
            sessions[identity] = {'session': {'id': identity}, 'state': 'awaiting', 'running': False,
                'total': 1, 'events': [], 'chain_sha256': identity, 'run_target': None, 'awaiting': [item],
                'run_approvals': [{'item': item, 'decision': None, 'receipt': None}]}
        return sessions[identity]
    def action(method, p):
        with calls_lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as out:
            out.write(json.dumps({'method': method, 'params': p}) + '\n')
        if method == 'route':
            return {'choice': {'model': 'fixture', 'endpoint': 'local-fixture'}, 'candidates': []}
        if method == 'list':
            return {'items': [{'id': s, 'first_message': s, 'state': v['state']} for s, v in sessions.items()]}
        v = session(p.get('session_id', 'session-a'))
        card = v['run_approvals'][0]
        if method in ('create', 'say'):
            v['state'] = 'ready'
            return copy.deepcopy(v)
        if method == 'run_target':
            deadline = time.monotonic() + 30
            while (control / 'hold_target').exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if (control / 'target_fail').exists():
                raise BridgeError('unavailable', 'fixture target failure')
            if 'simulation' in p:
                target = copy.deepcopy(p['simulation'])
                if target is not None:
                    target['connection_identity'] = {'kind': 'direct', 'name': 'fixture'}
                v['run_target'] = target
            if (control / 'lose_target').exists():
                raise BridgeError('unavailable', 'fixture lost target reply')
            return copy.deepcopy(v)
        if method == 'start':
            v['state'] = 'awaiting'
            return copy.deepcopy(v)
        if method == 'run_plan':
            sha = 'c' * 64 if (control / 'bad_plan').exists() else card['item']['plan_sha256']
            return {'item': copy.deepcopy(card['item']), 'run': {'id': card['item']['run_id'],
                'plan_sha256': sha, 'status': 'prepared',
                'tasks': [{'input': 'complete-input-' + ('x' * 70000) + '-complete-tail',
                    'unicode': ('中文🙂é空 格/' * 400) + '结束',
                    'path': '/tmp/' + ('nested-directory-' * 500) + '最终 input.h5'}]}}
        if method == 'run_decide':
            card['decision'] = {'decision': p['decision']}
            card['receipt'] = {'outcome': 'started' if p['decision'] == 'start' else 'declined',
                               'ok': True, 'run_status': 'completed'}
            v['awaiting'] = []
            v['state'] = 'ready'
            if (control / 'lose_decide').exists():
                raise BridgeError('unavailable', 'fixture lost decision reply')
            return {'receipt': copy.deepcopy(card['receipt']), 'revision': 0}
        if method == 'run_observe':
            return {'receipt': copy.deepcopy(card['receipt']), 'revision': 0}
        if method == 'verify':
            return {'ok': True, 'problems': []}
        if method == 'objects':
            return {'owner': None}
        result = copy.deepcopy(v)
        if method == 'get' and (control / 'omit_cards').exists():
            result['run_approvals'] = []
        return result
    names = ['route', 'create', 'say', 'start', 'cancel', 'recover', 'get', 'list', 'objects', 'verify']
    if not (control / 'legacy').exists():
        names += ['run_target', 'run_plan', 'run_decide', 'run_observe']
    else:
        for name in ['run_target', 'run_plan', 'run_decide', 'run_observe']:
            self.methods.pop('project.agent.' + name, None)
    for name in names:
        self.methods['project.agent.' + name] = lambda p, c, n=name: action(n, p)

server.Bridge.__init__ = init
main()
)PY";

class NativeAgentRuns : public ::testing::Test {
 protected:
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"native-agent-runs"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;

  ProjectState &state() { return f.shell->store().project(); }
  ProjectAgent &agent() { return state().agent(); }
  virtual bool legacy() const { return false; }
  void marker(const char *name) { std::ofstream(dir.path() / name) << "fixture"; }

  void SetUp() override
  {
    auto python = std::string(STK_BRIDGE_TEST_PYTHON_DEFAULT);
    if (const auto *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Python is required for the native agent wire fixture"; }
    if (legacy()) { marker("legacy"); }
    const auto script = dir.path() / "agent_runs_wire.py";
    std::ofstream(script) << kRunWire;
    bridge::ClientOptions options;
    options.command = {python, "-u", core::path_to_utf8(script), dir.str(), "--stdio", "--state-dir",
                       dir.str() + "/bridge", "--cache-dir", dir.str() + "/cache"};
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROJECTS_DIR"] = dir.str() + "/projects";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["PYTHONDONTWRITEBYTECODE"] = "1";
    options.executor = loop.executor();
    options.strict = options.validate = false;  // deliberately scripted views, no production model adapter
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    state().sync();
    ASSERT_TRUE(loop.pump_until([&] { return state().ready(); }, 60)) << client->bridge_log().text();
    ASSERT_TRUE(state().create(dir.str() + "/project", "Run approval fixture"));
    ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
    ASSERT_TRUE(state().loaded()) << state().error();
  }
  void TearDown() override
  {
    state().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
  }
  std::vector<Json> calls()
  {
    std::ifstream input(dir.path() / "calls.jsonl");
    std::vector<Json> items;
    for (std::string line; std::getline(input, line);) {
      if (input.eof()) { break; }  // The writer publishes each record with its final newline.
      items.push_back(Json::parse(line));
    }
    return items;
  }
  size_t count(const std::string &method)
  {
    size_t n = 0;
    for (const auto &call : calls()) { if (call.at("method") == method) { ++n; } }
    return n;
  }
  void settle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !agent().busy(); })) << agent().error();
  }
  void select(const std::string &id = "session-a")
  {
    agent().select(id);
    agent().pump(0);
    ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); })) << agent().error();
  }
  Json item() { return agent().run_cards().at(0).at("item"); }
  const ui::Widget *widget(const std::string &id) { return f.screen.ui()->find("a2/main/" + id); }
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  void open_ui()
  {
    auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
    f.screen.set_maximized(&area);
    ASSERT_TRUE(loop.pump_until([&] { frame(); return widget("ai_intent/" + state().project()->handle) != nullptr; }));
    widget("ai_intent/" + state().project()->handle)->index.assign(3);
    ASSERT_TRUE(loop.pump_until([&] { frame(); return widget("ai_agent_text/" + state().project()->handle) != nullptr; }));
  }
};

TEST_F(NativeAgentRuns, ExplicitSendSetsOrClearsTargetBeforeStartingAndLegacyAskKeepsItsContract)
{
  const Json target = {{"connection", "runtime:fixture"}, {"options", {{"backend", "local"}, {"ranks", 2}}}};
  ASSERT_TRUE(agent().ask("Prepare a run", target)); settle();
  auto requests = calls(); ASSERT_EQ(requests.size(), 3u);
  EXPECT_EQ(requests[0].at("method"), "create");
  EXPECT_EQ(requests[1].at("method"), "run_target");
  EXPECT_EQ(requests[1].at("params").at("simulation"), target);
  EXPECT_EQ(requests[2].at("method"), "start");
  ASSERT_TRUE(agent().ask("Inspect only", Json())); settle();
  requests = calls(); ASSERT_EQ(requests.size(), 6u);
  EXPECT_EQ(requests[3].at("method"), "say");
  EXPECT_TRUE(requests[4].at("params").at("simulation").is_null());
  EXPECT_EQ(requests[5].at("method"), "start");
  ASSERT_TRUE(agent().ask("Legacy message")); settle();
  EXPECT_EQ(count("run_target"), 2u); EXPECT_EQ(count("start"), 3u);
}

TEST_F(NativeAgentRuns, AQueuedCreateCannotSelectOrConfigureOrStartAfterSwitchingSessions)
{
  ASSERT_TRUE(agent().ask("First message", Json()));
  ASSERT_TRUE(bridge::test::wait_until([&] { return count("create") == 1; }));
  agent().select("session-b");
  settle();
  EXPECT_EQ(agent().selected(), "session-b"); EXPECT_FALSE(agent().busy());
  EXPECT_EQ(count("create"), 1u); EXPECT_EQ(count("run_target"), 0u); EXPECT_EQ(count("start"), 0u);
}

TEST_F(NativeAgentRuns, AQueuedTargetReplyCannotStartAfterSwitchingAwayAndBack)
{
  select();
  marker("hold_target");
  ASSERT_TRUE(agent().ask("Next", Json()));
  ASSERT_TRUE(loop.pump_until([&] { return count("run_target") == 1; }));
  agent().select("session-b"); agent().select("session-a");
  std::filesystem::remove(dir.path() / "hold_target"); settle();
  EXPECT_EQ(count("start"), 0u); EXPECT_EQ(count("run_target"), 1u);
}

TEST_F(NativeAgentRuns, FailedTargetConfigurationNeverStartsOnRefreshOrRecovery)
{
  marker("target_fail");
  ASSERT_TRUE(agent().ask("Prepare", Json())); settle();
  EXPECT_EQ(count("start"), 0u); EXPECT_FALSE(agent().error().empty());
  EXPECT_TRUE(agent().target_pending()); EXPECT_FALSE(agent().start());
  agent().draft_changed(""); agent().pump(0); loop.run_ready();
  ASSERT_TRUE(agent().recover()); settle(); agent().pump(0); loop.run_ready();
  EXPECT_EQ(count("start"), 0u); EXPECT_EQ(count("run_target"), 1u);
  std::filesystem::remove(dir.path() / "target_fail");
  ASSERT_TRUE(agent().set_run_target(Json())); settle();
  EXPECT_EQ(count("start"), 0u); // configuring a selected session is a separate explicit action
}

TEST_F(NativeAgentRuns, ExplicitSetAndClearFailuresBlockContinueAcrossSessionSwitchesUntilConfirmed)
{
  select();
  marker("target_fail");
  ASSERT_TRUE(agent().ask("Saved turn", Json())); settle();
  std::filesystem::remove(dir.path() / "target_fail");
  ASSERT_EQ(io::get_string(agent().view(), "state"), "ready");
  // A saved ready turn, with a previously configured target, needs an explicit target confirmation.
  ASSERT_TRUE(agent().set_run_target({{"connection", "runtime:fixture"}, {"options", {{"ranks", 2}}}})); settle();
  const auto before = count("start");
  for (const auto *failure : {"target_fail", "lose_target"}) {
    marker(failure);
    for (const Json &simulation : {Json(), Json{{"connection", "runtime:other"}, {"options", {{"ranks", 4}}}}}) {
      ASSERT_TRUE(agent().set_run_target(simulation));
      EXPECT_TRUE(agent().target_pending()); settle();
      EXPECT_FALSE(agent().start());
      select("session-b"); select("session-a");
      EXPECT_TRUE(agent().target_pending()); EXPECT_FALSE(agent().start());
      EXPECT_EQ(count("start"), before);
    }
    std::filesystem::remove(dir.path() / failure);
  }
  ASSERT_TRUE(agent().set_run_target(Json())); settle();
  EXPECT_FALSE(agent().target_pending()); EXPECT_EQ(count("start"), before);
  ASSERT_TRUE(agent().start()); settle(); EXPECT_EQ(count("start"), before + 1);
}

TEST_F(NativeAgentRuns, AnUnconfirmedSetReplyCannotRestoreContinueWhenItsSessionIsReselected)
{
  select(); marker("hold_target");
  ASSERT_TRUE(agent().set_run_target(Json()));
  ASSERT_TRUE(bridge::test::wait_until([&] { return count("run_target") == 1; }));
  agent().select("session-b"); agent().select("session-a");
  EXPECT_TRUE(agent().target_pending());
  std::filesystem::remove(dir.path() / "hold_target"); settle();
  EXPECT_TRUE(agent().target_pending()); EXPECT_FALSE(agent().start()); EXPECT_EQ(count("start"), 0u);
  ASSERT_TRUE(agent().set_run_target(Json())); settle();
  EXPECT_FALSE(agent().target_pending());
}

TEST_F(NativeAgentRuns, ApprovalRequiresTheCompleteMatchingPlanAndCurrentRevision)
{
  select(); const auto approval = item();
  EXPECT_FALSE(agent().can_decide_run(approval, "start"));
  marker("bad_plan"); ASSERT_TRUE(agent().read_run_plan(approval)); settle();
  EXPECT_EQ(agent().run_plan(approval), nullptr); EXPECT_FALSE(agent().can_decide_run(approval, "start"));
  std::filesystem::remove(dir.path() / "bad_plan");
  ASSERT_TRUE(agent().read_run_plan(approval)); settle();
  ASSERT_NE(agent().run_plan(approval), nullptr);
  EXPECT_GT(agent().run_plan(approval)->dump().size(), 70000u);
  EXPECT_TRUE(agent().can_decide_run(approval, "start"));
  auto changed = approval; changed["plan_sha256"] = std::string(64, 'd');
  EXPECT_FALSE(agent().can_decide_run(changed, "start"));
  ASSERT_TRUE(state().apply(Json::array({{{"op", "create_table"},
      {"id", "11111111-1111-4111-8111-111111111111"}, {"name", "Changed"}}})));
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
  EXPECT_FALSE(agent().can_decide_run(approval, "start")); EXPECT_EQ(count("run_decide"), 0u);
  EXPECT_TRUE(agent().can_decide_run(approval, "decline"));
  ASSERT_TRUE(agent().decide_run(approval, "decline")); settle();
  EXPECT_EQ(count("run_decide"), 1u);
}

TEST_F(NativeAgentRuns, APlanReplyFromAnEarlierSelectionDoesNotGrantReview)
{
  select(); const auto approval = item();
  ASSERT_TRUE(agent().read_run_plan(approval));
  ASSERT_TRUE(bridge::test::wait_until([&] { return count("run_plan") == 1; }));
  agent().select("session-b"); agent().select("session-a"); settle();
  EXPECT_EQ(agent().run_plan(approval), nullptr); EXPECT_FALSE(agent().can_decide_run(approval, "start"));
}

TEST_F(NativeAgentRuns, LostDecisionReplyOnlyAllowsOriginalObserveAfterAwaitingCardCloses)
{
  select(); const auto approval = item();
  ASSERT_TRUE(agent().read_run_plan(approval)); settle();
  marker("lose_decide"); ASSERT_TRUE(agent().decide_run(approval, "start")); settle();
  EXPECT_FALSE(agent().can_decide_run(approval, "start")); EXPECT_FALSE(agent().decide_run(approval, "decline"));
  EXPECT_EQ(agent().run_cards()[0]["receipt"]["outcome"], "uncertain");
  marker("omit_cards");
  agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return agent().view().at("awaiting").empty(); }));
  EXPECT_TRUE(agent().view().at("run_approvals").empty());
  EXPECT_EQ(agent().run_cards().size(), 1u);
  ASSERT_TRUE(agent().observe_run(approval)); settle();
  EXPECT_EQ(agent().run_cards()[0]["receipt"]["outcome"], "started");
  EXPECT_EQ(agent().run_cards()[0]["receipt"]["run_status"], "completed");
  EXPECT_EQ(count("run_decide"), 1u); EXPECT_EQ(count("run_observe"), 1u); EXPECT_EQ(count("start"), 0u);
}

TEST_F(NativeAgentRuns, SwitchingDuringADecisionKeepsItsOriginalSessionAndOnlyAllowsObserve)
{
  select(); const auto approval = item();
  ASSERT_TRUE(agent().read_run_plan(approval)); settle();
  ASSERT_TRUE(agent().decide_run(approval, "start"));
  ASSERT_TRUE(bridge::test::wait_until([&] { return count("run_decide") == 1; }));
  agent().select("session-b"); settle();
  EXPECT_EQ(agent().selected(), "session-b");
  select("session-a");
  EXPECT_FALSE(agent().can_decide_run(approval, "start"));
  EXPECT_EQ(agent().run_plan(approval), nullptr);
  ASSERT_TRUE(agent().observe_run(approval)); settle();
  EXPECT_EQ(agent().run_cards()[0]["receipt"]["outcome"], "started");
  for (const auto &call : calls()) {
    if (call.at("method") == "run_decide" || call.at("method") == "run_observe") {
      EXPECT_EQ(call.at("params").at("session_id"), "session-a");
      EXPECT_EQ(call.at("params").at("item_id"), approval.at("item_id"));
    }
  }
  EXPECT_EQ(count("run_decide"), 1u); EXPECT_EQ(count("start"), 0u);
}

TEST_F(NativeAgentRuns, UIStartsWithPreparationOffAndDisplaysEveryPlanLineBeforeApproval)
{
  select(); open_ui();
  ASSERT_NE(widget("ai_agent_allow_prepare"), nullptr);
  EXPECT_FALSE(widget("ai_agent_allow_prepare")->boolean.value());
  const auto id = io::get_string(item(), "item_id");
  ASSERT_NE(widget("ai_agent_run_start/" + id), nullptr);
  EXPECT_FALSE(widget("ai_agent_run_start/" + id)->enabled);
  widget("ai_agent_run_read/" + id)->on_click();
  ASSERT_TRUE(loop.pump_until([&] { frame(); return widget("ai_agent_run_plan/" + id) != nullptr; }));
  const auto check_complete = [&] {
    const auto *view = widget("ai_agent_run_plan/" + id);
    ASSERT_NE(view, nullptr); ASSERT_NE(view->log, nullptr);
    const auto &style = f.screen.ui()->style();
    const float available = view->rect.w - 2 * style.text_margin - style.scrollbar - 2 * style.pixel;
    std::string text;
    for (size_t i = 0; i < view->log->line_count(); ++i) {
      const auto line = view->log->line(i);
      EXPECT_LE(f.measurer.width(line, style.mono), available);
      text += line;
    }
    auto expected = agent().run_plan(item())->dump(2);
    expected.erase(std::remove(expected.begin(), expected.end(), '\n'), expected.end());
    EXPECT_EQ(text, expected);  // preserves all bytes, including Unicode, paths and spaces inside string values
    EXPECT_GT(text.size(), 70000u); EXPECT_GT(view->log->line_count(), 100u);
    EXPECT_NE(text.find("-complete-tail"), std::string::npos);
    EXPECT_NE(text.find("最终 input.h5"), std::string::npos);
    EXPECT_NE(text.find("中文🙂é空 格/"), std::string::npos);
  };
  check_complete();
  f.drv->ctx.rect = {0, 0, 640, 1000}; frame(); check_complete();
  EXPECT_TRUE(widget("ai_agent_run_start/" + id)->enabled);
  const auto saved = f.area("a2").editor().save_workspace_state();
  EXPECT_EQ(saved.dump().find("allow_prepare"), std::string::npos);
  EXPECT_EQ(saved.dump().find("plan_sha256"), std::string::npos);
  EXPECT_EQ(count("run_target"), 0u); EXPECT_EQ(count("run_decide"), 0u); EXPECT_EQ(count("start"), 0u);
}

TEST_F(NativeAgentRuns, TwoPointerClicksReadAndApproveTheOriginalPlanWithoutChangingViewerOrLayout)
{
  f.drv->ctx.rect = {0, 0, 1280, 1600};
  select(); open_ui();
  const auto layout = f.screen.arrangement();
  const auto viewer = f.shell->store().viewer().save_workspace_state();
  const auto id = io::get_string(item(), "item_id");
  int clicks = 0;
  const auto click = [&](const std::string &key) {
    const auto *control = widget(key); ASSERT_NE(control, nullptr); ASSERT_TRUE(control->enabled);
    ASSERT_GE(control->rect.y, 0); ASSERT_LE(control->rect.y1(), 1600);
    const auto [x, y] = f.widget_center("a2/main/" + key);
    ++clicks; ASSERT_TRUE(f.drv->click(x, y)); frame();
  };
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_read/" + id));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return agent().run_plan(item()) != nullptr; }));
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_start/" + id)); settle(); frame();
  EXPECT_EQ(clicks, 2); EXPECT_EQ(count("run_plan"), 1u); EXPECT_EQ(count("run_decide"), 1u);
  EXPECT_EQ(count("start"), 0u);  // these pointer clicks never resume the planner
  EXPECT_EQ(f.screen.arrangement(), layout);
  EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer);
}

class NativeAgentRunsLegacy : public NativeAgentRuns { bool legacy() const override { return true; } };
TEST_F(NativeAgentRunsLegacy, MissingCapabilitiesKeepTheOldAssistantAndHidePreparationControls)
{
  EXPECT_TRUE(agent().supported()); EXPECT_FALSE(agent().runs_supported());
  open_ui();
  EXPECT_EQ(widget("ai_agent_allow_prepare"), nullptr);
  EXPECT_FALSE(agent().ask("Unavailable preparation", Json()));
  EXPECT_EQ(count("run_target"), 0u);
  ASSERT_TRUE(agent().ask("Old assistant")); settle();
  EXPECT_EQ(count("create"), 1u); EXPECT_EQ(count("start"), 1u);
}
}  // namespace
}  // namespace stk::app
