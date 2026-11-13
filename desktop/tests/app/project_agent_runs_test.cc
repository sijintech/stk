/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_agent.hh"
#include "stk/app/project_discussion.hh"
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
#include <map>
#include <optional>
#include <vector>

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
original_send = server.Bridge.send
original_validate = server.bridge_schema.validate_params
server.bridge_schema.validate_params = lambda m, p: ([] if m.startswith('project.agent.') or m == 'project.workflow_runs.get'
                                                      else original_validate(m, p))

def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    sessions = {}
    calls_lock = threading.Lock()
    gets = [0]  # selected-session reads (no limit), numbered in the order the service takes them
    def session(identity):
        if identity not in sessions:
            item = {'item_id': 'approve:' + identity, 'kind': 'start_run', 'run_id': 'run:' + identity,
                    'plan_sha256': 'a' * 64, 'request_sha256': 'b' * 64, 'expected_revision': 0}
            sessions[identity] = {'session': {'id': identity}, 'state': 'awaiting', 'running': False,
                'total': 1, 'events': [], 'chain_sha256': identity, 'run_target': None, 'awaiting': [item],
                'run_approvals': [{'item': item, 'decision': None, 'receipt': None}]}
            if (control / 'consumed').exists():
                # The first card has its decision and receipt; a second card still waits for a decision.
                pending = dict(item, item_id='approve2:' + identity, run_id='run2:' + identity, plan_sha256='f' * 64)
                sessions[identity].update(state='ready', awaiting=[pending], run_approvals=[
                    {'item': item, 'decision': {'decision': 'start'},
                     'receipt': {'outcome': 'started', 'ok': True, 'run_status': 'stopped'}},
                    {'item': pending, 'decision': None, 'receipt': None}])
            if (control / 'answered').exists():
                sessions[identity].update(state='answered', awaiting=[])
            if (control / 'long_timeline').exists():
                events = [{'kind': 'user_turn', 'turn': i, 'text': 'Saved message %d' % i} for i in range(50)]
                sessions[identity].update(events=events, total=len(events))
        return sessions[identity]
    details = [0]
    def run_get(p):
        with calls_lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as out:
            out.write(json.dumps({'method': 'workflow_runs.get', 'params': p}) + '\n')
            details[0] += 1
            serial = details[0]
        # Tokens as for get: detail N is held while hold_detail existed, until detail_release_N.
        if (control / 'hold_detail').exists():
            (control / ('detail_held_%d' % serial)).write_text('held')
            deadline = time.monotonic() + 10
            while not (control / ('detail_release_%d' % serial)).exists() and time.monotonic() < deadline:
                time.sleep(0.01)
        if (control / 'run_missing').exists():
            raise BridgeError('not_found', 'fixture run missing %d at /private/fixture/path' % serial)
        rows = [{'id': 'row-1', 'number': 3, 'values': {'secret_value': 'row-secret'}},
                {'id': 'row-2', 'number': 7, 'values': {}}]
        tasks = [
            {'step': 'simulate\u202eevil\nline', 'row': 'row-1', 'attempt': 2, 'status': 'succeeded', 'error': None,
             'updated_at': 'now', 'progress': {'attempt': 2, 'stage': 'collecting', 'state': 'done',
                                               'task_id': '0123456789abcdef0123', 'simulation_run_id': 'sim-secret'},
             'produced': {'directory': 'results/run/simulate/row-1', 'snapshot_id': 'fedcba9876543210',
                          'files': {'输出🙂' + '长' * 300 + '-tail': 'record-1', 'scalar.vti': 'record-2'}}},
            {'step': 'analyse', 'row': 'row-1', 'attempt': 1, 'status': 'failed', 'error': 'error-secret',
             'updated_at': 'now', 'progress': None,
             'produced': {'analysis_run_id': 'abcdef0123456789', 'snapshot_id': '1111222233334444',
                          'directory': '../escape-secret'}},
            {'step': 'collect', 'row': 'row-2', 'attempt': 1, 'status': 'succeeded', 'error': None, 'updated_at': 'now',
             'progress': None, 'produced': {'directory': '/absolute-secret/dir', 'files': {}}},
        ] + [{'step': 'simulate', 'row': 'row-2', 'attempt': 0, 'status': 'pending', 'error': None, 'updated_at': None,
              'progress': None, 'produced': None} for _ in range(198)]
        if (control / 'produced.json').exists():
            # Real frozen snapshots captured by the test: task index -> its produced object.
            for index, produced in json.loads((control / 'produced.json').read_text()).items():
                tasks[int(index)]['produced'] = produced
        run = {'id': p['run_id'], 'project_id': 'project-secret', 'plan_sha256': 'e' * 64 if (control / 'run_mismatch').exists()
               else ('a' * 64 if p['run_id'].startswith('run:') else 'f' * 64),
               'status': 'stopped', 'complete': False, 'stop_error': 'stop-secret', 'executor_id': 'executor-secret',
               'owner': {'host': 'host-secret', 'pid': 4242}, 'simulation': {'connection': 'endpoint-secret'},
               'directory': '/private/results-secret', 'parameters': {'x': 'parameter-secret'}, 'rows': rows,
               'counts': {'succeeded': 2, 'failed': 1, 'pending': 198}, 'tasks': tasks}
        return {'run': run, 'fixture_serial': serial}
    def action(method, p):
        serial = None
        with calls_lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as out:
            out.write(json.dumps({'method': method, 'params': p}) + '\n')
            if method == 'get' and 'limit' not in p:
                gets[0] += 1
                serial = gets[0]
        if serial is not None:
            # Per-call tokens: get N is held while hold_get existed when it arrived, until release_N; fail_get_N
            # makes it an error. The send wrapper records when the actual response has been written.
            if (control / 'hold_get').exists():
                (control / ('held_%d' % serial)).write_text('held')
                deadline = time.monotonic() + 10
                while not (control / ('release_%d' % serial)).exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
            if (control / ('fail_get_%d' % serial)).exists():
                raise BridgeError('unavailable', 'fixture get failure %d' % serial)
            result = copy.deepcopy(session(p.get('session_id', 'session-a')))
            if (control / 'grow_timeline_b').exists() and p.get('session_id') == 'session-b':
                result['events'].append({'kind': 'model_completed', 'text': 'A late reply in session B'})
                result['chain_sha256'] += '-late'
                result['total'] += 1
            result['get_serial'] = serial  # same total for every read: only this tells old and new replies apart
            if (control / 'omit_cards').exists():
                result['run_approvals'] = []
            return result
        if method == 'route':
            return {'choice': {'model': 'fixture', 'endpoint': 'local-fixture'}, 'candidates': []}
        if method == 'list':
            return {'items': [{'id': s, 'first_message': s, 'state': v['state']} for s, v in sessions.items()]}
        v = session(p.get('session_id', 'session-a'))
        card = v['run_approvals'][0]
        if method in ('create', 'say'):
            v['state'] = 'ready'
            if (control / 'lose_say').exists():
                raise BridgeError('unavailable', 'fixture lost message reply')
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
    self.methods['project.workflow_runs.get'] = lambda p, c: run_get(p)
    # The real snapshot and file methods, logged. Snapshot reads are numbered: snapshot read N is held while
    # hold_snapshot existed, until snapshot_release_N; resolve_* markers alter a real resolve reply.
    snapshot_reads = [0]
    def logged(name, original):
        def call(p, c):
            serial = None
            with calls_lock, (control / 'calls.jsonl').open('a', encoding='utf-8') as out:
                out.write(json.dumps({'method': name, 'params': p}) + '\n')
                if name in ('snapshots.get', 'snapshots.resolve'):
                    snapshot_reads[0] += 1
                    serial = snapshot_reads[0]
            replying.serial = serial  # the reply is sent from this thread (see send)
            if serial is not None and (control / 'hold_snapshot').exists():
                (control / ('snapshot_held_%d' % serial)).write_text('held')
                deadline = time.monotonic() + 10
                while not (control / ('snapshot_release_%d' % serial)).exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
            if name == 'snapshots.resolve' and (control / 'resolve_fail').exists():
                raise BridgeError('not_found', 'fixture resolve failure at /private/fixture/path')
            result = original(p, c)
            if name == 'snapshots.resolve':
                result = dict(result)
                if (control / 'resolve_wrong_sha').exists():
                    result['sha256'] = '0' * 64
                if (control / 'resolve_wrong_size').exists():
                    result['size'] += 1
                if (control / 'resolve_wrong_record').exists():
                    result['record_id'] = '00000000-0000-4000-8000-000000000000'
                if (control / 'resolve_changed_bytes').exists():
                    data = bytearray(Path(result['path']).read_bytes())
                    data[0] ^= 1  # same size, other bytes
                    changed = control / 'changed-object'
                    changed.write_bytes(bytes(data))
                    result['path'] = str(changed)
                if (control / 'resolve_symlink').exists():
                    link = control / 'linked-object'
                    link.unlink(missing_ok=True)
                    link.symlink_to(result['path'])
                    result['path'] = str(link)
            return result
        return call
    for method in list(self.methods):
        if method.startswith('project.snapshots.') or method.startswith('project.files.'):
            self.methods[method] = logged(method[len('project.'):], self.methods[method])
    for name in ('get', 'resolve'):
        if (control / ('no_snapshot_' + name)).exists():
            self.methods.pop('project.snapshots.' + name, None)

replying = threading.local()

def send(self, message, method=None):
    flushed = original_send(self, message, method)
    if flushed and method in ('project.snapshots.get', 'project.snapshots.resolve'):
        serial = getattr(replying, 'serial', None)
        if serial is not None:
            (control / ('snapshot_replied_%d' % serial)).write_text('replied')
            replying.serial = None
    if flushed and method == 'project.agent.get':
        serial = message.get('result', {}).get('get_serial')
        failure = message.get('error', {}).get('message', '')
        prefix = 'fixture get failure '
        if serial is None and failure.startswith(prefix):
            serial = int(failure[len(prefix):])
        if serial is not None:
            (control / ('replied_%d' % serial)).write_text('replied')
    if flushed and method == 'project.workflow_runs.get':
        serial = message.get('result', {}).get('fixture_serial')
        failure = message.get('error', {}).get('message', '')
        prefix = 'fixture run missing '
        if serial is None and failure.startswith(prefix):
            serial = int(failure[len(prefix):].split(' ')[0])
        if serial is not None:
            (control / ('detail_replied_%d' % serial)).write_text('replied')
    return flushed

server.Bridge.__init__ = init
server.Bridge.send = send
main()
)PY";

class NativeAgentRuns : public ::testing::Test {
 protected:
  NativeAgentRuns() = default;
  /** Another shell language and window (the narrow Chinese row of the acceptance). */
  NativeAgentRuns(const char *language, int width, int height) : f{language, 1, width, height} {}
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"native-agent-runs"};
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;

  ProjectState &state() { return f.shell->store().project(); }
  ProjectAgent &agent() { return state().agent(); }
  virtual bool legacy() const { return false; }
  /** A marker the wire fixture reads at start (a capability the bridge then does not offer). */
  virtual const char *capability_marker() const { return nullptr; }
  void marker(const char *name) { std::ofstream(dir.path() / name) << "fixture"; }

  void SetUp() override
  {
    auto python = std::string(STK_BRIDGE_TEST_PYTHON_DEFAULT);
    if (const auto *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Python is required for the native agent wire fixture"; }
    if (legacy()) { marker("legacy"); }
    if (const auto *name = capability_marker()) { marker(name); }
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
  bool exists(const std::string &name) { return std::filesystem::exists(dir.path() / name); }
  /** The selected-session reads (project.agent.get without a limit), in the order the service took them. */
  std::vector<Json> gets()
  {
    std::vector<Json> items;
    for (const auto &call : calls()) {
      if (call.at("method") == "get" && !call.at("params").contains("limit")) { items.push_back(call); }
    }
    return items;
  }
  void held(int n) { ASSERT_TRUE(bridge::test::wait_until([&] { return exists("held_" + std::to_string(n)); }, 5)); }
  /** Let held get ``n`` answer, then make sure its reply reached the controller: a later list reply follows it. */
  void release(int n)
  {
    marker(("release_" + std::to_string(n)).c_str());
    ASSERT_TRUE(bridge::test::wait_until([&] { return exists("replied_" + std::to_string(n)); }, 5));
    auto answer = std::make_shared<std::optional<bridge::Result<Json>>>();
    client->call("project.agent.list", {{"handle", state().project()->handle}, {"limit", 1}})
        .then([answer](bridge::Result<Json> result) { *answer = std::move(result); });
    ASSERT_TRUE(loop.pump_until([&] { return answer->has_value(); }, 10));
    ASSERT_TRUE(answer->value().ok()) << answer->value().error().describe();
  }
  /** Let held linked-task read ``n`` answer, then make sure its reply reached the controller (a later reply). */
  void detail_release(int n)
  {
    marker(("detail_release_" + std::to_string(n)).c_str());
    ASSERT_TRUE(bridge::test::wait_until([&] { return exists("detail_replied_" + std::to_string(n)); }, 5));
    auto answer = std::make_shared<std::optional<bridge::Result<Json>>>();
    client->call("project.agent.list", {{"handle", state().project()->handle}, {"limit", 1}})
        .then([answer](bridge::Result<Json> result) { *answer = std::move(result); });
    ASSERT_TRUE(loop.pump_until([&] { return answer->has_value(); }, 10));
  }
  void detail_held(int n)
  {
    ASSERT_TRUE(bridge::test::wait_until([&] { return exists("detail_held_" + std::to_string(n)); }, 5));
  }
  /** The consumed card (first) and the card that still waits for a decision (second). */
  Json consumed_item() { return agent().run_cards().at(0).at("item"); }
  Json pending_item() { return agent().run_cards().at(1).at("item"); }
  /** Every agent action the detail must never send. */
  void expect_no_agent_actions()
  {
    for (const auto *method : {"run_plan", "run_decide", "run_observe", "run_target", "create", "say", "start"}) {
      EXPECT_EQ(count(method), 0u) << method;
    }
  }
  /** One bridge call answered before returning (fixture setup only). */
  Json sync_call(const std::string &method, Json params)
  {
    auto answer = std::make_shared<std::optional<bridge::Result<Json>>>();
    client->call(method, std::move(params)).then([answer](bridge::Result<Json> result) { *answer = std::move(result); });
    EXPECT_TRUE(loop.pump_until([&] { return answer->has_value(); }, 30)) << method;
    if (!answer->has_value()) { return Json(); }
    EXPECT_TRUE(answer->value().ok()) << method << ": " << answer->value().error().describe();
    return answer->value().ok() ? answer->value().value() : Json();
  }
  /** Project files of a simulation's outputs, really indexed and captured into one frozen snapshot. */
  struct Captured { std::string snapshot_id; std::map<std::string, std::string> records; };
  Captured capture_outputs()
  {
    const std::vector<std::pair<std::string, std::string>> files = {
        {"notes.txt", "<b>bold</b> <script>alert(1)</script>\r\nline two\rhidden\x1b[31mred\x1b[0m\ttab "
                      "\xe2\x80\xae" "evil\n中文🙂\n"},
        {"big.log", std::string(300 * 1024, 'x') + "\n"},
        {"binary.out", std::string("\xff\xfe\x00", 3) + " not UTF-8"},
        {"scalar.vti", "<VTKFile type=\"ImageData\"/>\n"},
        {"page.html", "<html><body><h1>Not previewed</h1></body></html>\n"},
        {"empty.txt", ""}};
    const auto outputs = dir.path() / "project" / "results" / "run";
    std::filesystem::create_directories(outputs);
    Json paths = Json::array();
    for (const auto &[name, bytes] : files) {
      std::ofstream(outputs / name, std::ios::binary) << bytes;
      paths.push_back(core::path_to_utf8(outputs / name));
    }
    const auto handle = state().project()->handle;
    const auto indexed = sync_call("project.files.index", {{"handle", handle},
        {"expected_revision", state().project()->revision}, {"paths", paths}});
    const auto captured = sync_call("project.snapshots.capture", {{"handle", handle},
        {"expected_revision", indexed.at("revision")}, {"record_ids", indexed.at("record_ids")}});
    EXPECT_TRUE(loop.pump_until([&] {
      return !state().busy() && state().project()->revision == captured.at("revision").get<int64_t>();
    }, 30));
    Captured result{captured.at("snapshot").at("id").get<std::string>(), {}};
    for (size_t i = 0; i < files.size(); ++i) {
      result.records[files[i].first] = indexed.at("record_ids").at(i).get<std::string>();
    }
    return result;
  }
  /** Task 0 produces six outputs (two named differently than their files); task 2 only notes.txt. */
  Captured produce()
  {
    auto captured = capture_outputs();
    const auto &r = captured.records;
    write_produced({{"0", {{"directory", "results/run"}, {"snapshot_id", captured.snapshot_id},
        {"files", {{"notes", r.at("notes.txt")}, {"big", r.at("big.log")}, {"binary.out", r.at("binary.out")},
                   {"scalar.vti", r.at("scalar.vti")}, {"page.html", r.at("page.html")},
                   {"empty.txt", r.at("empty.txt")}}}}},
        {"2", {{"snapshot_id", captured.snapshot_id}, {"files", {{"notes.txt", r.at("notes.txt")}}}}}});
    return captured;
  }
  void write_produced(const Json &produced) { std::ofstream(dir.path() / "produced.json") << produced.dump(); }
  void snapshot_held(int n)
  {
    ASSERT_TRUE(bridge::test::wait_until([&] { return exists("snapshot_held_" + std::to_string(n)); }, 5));
  }
  /** Let held snapshot read ``n`` answer, then make sure its reply reached the controller (a later reply). */
  void snapshot_release(int n)
  {
    marker(("snapshot_release_" + std::to_string(n)).c_str());
    ASSERT_TRUE(bridge::test::wait_until([&] { return exists("snapshot_replied_" + std::to_string(n)); }, 5));
    sync_call("project.agent.list", {{"handle", state().project()->handle}, {"limit", 1}});
  }
  /** A ready detail of the consumed card (one workflow_runs.get). */
  uint64_t ready_detail(const Json &card)
  {
    const auto ticket = agent().read_run_detail(card);
    EXPECT_NE(ticket, 0u);
    EXPECT_TRUE(loop.pump_until([&] {
      const auto *detail = agent().run_detail(ticket, card);
      return detail && io::get_string(*detail, "state") != "reading";
    }));
    return ticket;
  }
  std::string files_state(uint64_t ticket, const Json &card)
  {
    const auto *files = agent().run_files(ticket, card);
    return files ? io::get_string(*files, "state") : std::string("closed");
  }
  std::string preview_state(uint64_t ticket, const Json &card)
  {
    const auto *preview = agent().run_file_preview(ticket, card);
    return preview ? io::get_string(*preview, "state") : std::string("closed");
  }
  bool settle_files(uint64_t ticket, const Json &card)
  {
    return loop.pump_until([&] { return files_state(ticket, card) != "reading"; });
  }
  bool settle_preview(uint64_t ticket, const Json &card)
  {
    return loop.pump_until([&] { return preview_state(ticket, card) != "reading"; });
  }
  void list_ready()
  {
    agent().pump(0);
    ASSERT_TRUE(loop.pump_until([&] { return agent().list_loaded() && agent().route_loaded(); })) << agent().error();
  }
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

TEST_F(NativeAgentRuns, AHeldReadOfAnEarlierSelectionNeitherFillsTheReselectedSessionNorBlocksItsRead)
{
  ASSERT_NO_FATAL_FAILURE(list_ready());
  marker("hold_get");
  agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(1));
  agent().select("session-b"); agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(2));  // the reselection reads at once; the earlier flight does not hold its guard
  auto requests = gets(); ASSERT_EQ(requests.size(), 2u);
  for (const auto &call : requests) { EXPECT_EQ(call.at("params").at("session_id"), "session-a"); }
  ASSERT_NO_FATAL_FAILURE(release(1));
  EXPECT_TRUE(agent().view().empty()) << agent().view().dump();  // same session ID, earlier selection
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  agent().draft_changed(""); agent().pump(0); loop.run_ready();
  EXPECT_EQ(gets().size(), 2u);  // the old completion did not clear the newer flight's guard
  ASSERT_NO_FATAL_FAILURE(release(2));
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  EXPECT_EQ(io::get_int(agent().view(), "get_serial", 0), 2);
  std::filesystem::remove(dir.path() / "hold_get");
  agent().pump(0);  // the refresh asked while the current read was in flight still follows
  ASSERT_TRUE(loop.pump_until([&] { return io::get_int(agent().view(), "get_serial", 0) == 3; }));
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_EQ(count("start"), 0u); EXPECT_EQ(count("create"), 0u); EXPECT_EQ(count("say"), 0u);
  EXPECT_EQ(count("run_target"), 0u); EXPECT_EQ(count("run_decide"), 0u);
}

TEST_F(NativeAgentRuns, ALateSuccessOfAnEarlierSelectionIsNotAdoptedForTheSameSessionID)
{
  ASSERT_NO_FATAL_FAILURE(list_ready());
  marker("hold_get");
  agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(1));
  std::filesystem::remove(dir.path() / "hold_get");
  agent().select("session-b"); agent().select("session-a");  // A -> B -> A before the first read answers
  ASSERT_NO_FATAL_FAILURE(release(1));
  EXPECT_TRUE(agent().view().empty()) << agent().view().dump();
  agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  EXPECT_EQ(io::get_int(agent().view(), "get_serial", 0), 2);
  EXPECT_EQ(gets().size(), 2u);
}

TEST_F(NativeAgentRuns, AnErrorOfAnEarlierSelectionIsNotShownButTheCurrentReadsErrorIs)
{
  ASSERT_NO_FATAL_FAILURE(list_ready());
  marker("hold_get"); marker("fail_get_1"); marker("fail_get_2");
  agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(1));
  std::filesystem::remove(dir.path() / "hold_get");
  agent().select("session-b"); agent().select("session-a");
  ASSERT_NO_FATAL_FAILURE(release(1));
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_TRUE(agent().view().empty());
  agent().pump(0);  // the reselection's own read, which fails too
  ASSERT_TRUE(loop.pump_until([&] { return !agent().error().empty(); }));
  EXPECT_NE(agent().error().find("fixture get failure 2"), std::string::npos) << agent().error();
  EXPECT_TRUE(agent().view().empty());
  agent().draft_changed(""); agent().pump(0);  // its failure released the guard: a current refresh reads again
  ASSERT_TRUE(loop.pump_until([&] { return io::get_int(agent().view(), "get_serial", 0) == 3; }));
  EXPECT_EQ(gets().size(), 3u);
}

TEST_F(NativeAgentRuns, AHeldReadDoesNotDelayAnotherSessionOrTheNewSessionFallback)
{
  ASSERT_NO_FATAL_FAILURE(list_ready());
  marker("hold_get");
  agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(1));
  std::filesystem::remove(dir.path() / "hold_get");
  agent().select("session-b"); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }, 10));
  EXPECT_EQ(io::get_string(agent().view().at("session"), "id"), "session-b");
  EXPECT_EQ(io::get_int(agent().view(), "get_serial", 0), 2);
  agent().select(""); agent().pump(0);  // a new session's first message: nothing to read
  EXPECT_EQ(gets().size(), 2u);
  ASSERT_NO_FATAL_FAILURE(release(1));
  EXPECT_EQ(agent().selected(), ""); EXPECT_TRUE(agent().view().empty());
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  agent().select("session-a"); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  EXPECT_EQ(io::get_int(agent().view(), "get_serial", 0), 3);
  EXPECT_EQ(count("start"), 0u); EXPECT_EQ(count("create"), 0u);
}

TEST_F(NativeAgentRuns, AHeldReadOfAReplacedProjectOpeningIsIgnoredAfterReopening)
{
  ASSERT_NO_FATAL_FAILURE(list_ready());
  marker("hold_get");
  agent().select("session-a"); agent().pump(0);
  ASSERT_NO_FATAL_FAILURE(held(1));
  std::filesystem::remove(dir.path() / "hold_get");
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
  ASSERT_TRUE(state().loaded()) << state().error();
  EXPECT_EQ(agent().selected(), "");
  ASSERT_NO_FATAL_FAILURE(list_ready());
  ASSERT_NO_FATAL_FAILURE(release(1));
  EXPECT_TRUE(agent().view().empty()); EXPECT_TRUE(agent().error().empty()) << agent().error();
  agent().select("session-a"); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  EXPECT_EQ(io::get_int(agent().view(), "get_serial", 0), 2);
}

TEST_F(NativeAgentRuns, SyncSessionListReadsOnlyTheListUnderItsGuardsAndTheSelectionEpochOnlyAdvances)
{
  ASSERT_TRUE(calls().empty());
  const auto epoch = agent().selection_epoch();
  agent().select("session-a");  // a session read is now pending; only pump sends it
  EXPECT_EQ(agent().selection_epoch(), epoch + 1);
  agent().select("session-a"); EXPECT_EQ(agent().selection_epoch(), epoch + 1);
  ASSERT_TRUE(agent().sync_session_list());
  EXPECT_FALSE(agent().sync_session_list());  // in flight
  ASSERT_TRUE(loop.pump_until([&] { return agent().list_loaded(); }));
  EXPECT_FALSE(agent().sync_session_list());  // asked once, until something changes
  agent().draft_changed("");
  const auto version = agent().version();
  ASSERT_TRUE(agent().sync_session_list());
  ASSERT_TRUE(loop.pump_until([&] { return agent().version() > version; }));
  const auto requests = calls(); ASSERT_EQ(requests.size(), 2u);
  for (const auto &call : requests) { EXPECT_EQ(call.at("method"), "list"); }
  EXPECT_TRUE(agent().view().empty()); EXPECT_FALSE(agent().route_loaded()); EXPECT_FALSE(agent().busy());
  agent().select("session-b"); agent().select("session-a");
  EXPECT_EQ(agent().selection_epoch(), epoch + 3);
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
  ASSERT_TRUE(state().loaded()) << state().error();
  EXPECT_GT(agent().selection_epoch(), epoch + 3);  // reopening never repeats an earlier epoch
  EXPECT_EQ(agent().selected(), "");
  ASSERT_TRUE(agent().sync_session_list());  // reset forgets the asked list
  ASSERT_TRUE(loop.pump_until([&] { return agent().list_loaded(); }));
  EXPECT_EQ(count("list"), 3u); EXPECT_EQ(calls().size(), 3u);
}

TEST_F(NativeAgentRuns, HistorySelectionWaitsForExplicitSendsAndTheirUnsurfacedReceiptOnly)
{
  select();
  EXPECT_TRUE(agent().history_selection_available());
  marker("hold_target");
  ASSERT_TRUE(agent().ask("Next", Json()));
  EXPECT_FALSE(agent().history_selection_available());  // the send is in flight
  ASSERT_TRUE(loop.pump_until([&] { return count("run_target") == 1; }));
  EXPECT_FALSE(agent().history_selection_available());  // its explicit target is in flight
  std::filesystem::remove(dir.path() / "hold_target"); settle();
  EXPECT_EQ(count("start"), 1u);
  EXPECT_FALSE(agent().history_selection_available());  // the sent text is not surfaced yet
  EXPECT_EQ(agent().take_sent(), "Next");
  EXPECT_TRUE(agent().history_selection_available());
  marker("lose_say");
  ASSERT_TRUE(agent().ask("Lost reply", Json())); settle();
  EXPECT_FALSE(agent().error().empty());
  EXPECT_FALSE(agent().history_selection_available());  // a second click must reuse the lost send's IDs
  const auto before = calls().size();
  const auto epoch = agent().selection_epoch();
  agent().select("session-b");  // an explicit choice stays available and sends nothing
  EXPECT_EQ(agent().selection_epoch(), epoch + 1); EXPECT_EQ(calls().size(), before);
  EXPECT_TRUE(agent().history_selection_available());
  std::filesystem::remove(dir.path() / "lose_say");
  agent().pump(0); ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  marker("target_fail");
  ASSERT_TRUE(agent().set_run_target(Json()));
  EXPECT_FALSE(agent().history_selection_available());
  settle();
  EXPECT_TRUE(agent().target_pending());  // an unconfirmed target survives selection by design
  EXPECT_TRUE(agent().history_selection_available());
  EXPECT_EQ(count("start"), 1u); EXPECT_EQ(count("run_decide"), 0u); EXPECT_EQ(count("say"), 2u);
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

TEST_F(NativeAgentRuns, LinkedTasksReadOnlyABoundedProjectionOfTheExactConsumedCard)
{
  marker("consumed");
  select();
  ASSERT_EQ(agent().run_cards().size(), 2u);
  const auto consumed = consumed_item(), pending = pending_item();
  EXPECT_TRUE(agent().can_read_run_detail(consumed));
  EXPECT_FALSE(agent().can_read_run_detail(pending));  // a card waiting for a decision has no linked tasks
  EXPECT_EQ(agent().read_run_detail(pending), 0u);
  auto other = consumed; other["plan_sha256"] = std::string(64, 'd');
  EXPECT_EQ(agent().read_run_detail(other), 0u);  // not a card of this session
  const auto chain = io::get_string(agent().view(), "chain_sha256");
  const auto total = io::get_int(agent().view(), "total", -1);
  const auto revision = state().project()->revision;
  const auto decline = agent().can_decide_run(pending, "decline");
  const auto session_reads = gets().size();
  const auto ticket = agent().read_run_detail(consumed);
  ASSERT_NE(ticket, 0u);
  EXPECT_FALSE(agent().busy());  // a passive read keeps every other control as it was
  EXPECT_EQ(agent().can_decide_run(pending, "decline"), decline);
  ASSERT_NE(agent().run_detail(ticket, consumed), nullptr);
  EXPECT_EQ(io::get_string(*agent().run_detail(ticket, consumed), "state"), "reading");
  EXPECT_EQ(agent().run_detail(ticket, pending), nullptr);
  ASSERT_TRUE(loop.pump_until([&] {
    const auto *detail = agent().run_detail(ticket, consumed);
    return detail && io::get_string(*detail, "state") != "reading";
  }));
  const auto detail = *agent().run_detail(ticket, consumed);
  ASSERT_EQ(io::get_string(detail, "state"), "ready") << detail.dump();
  ASSERT_EQ(count("workflow_runs.get"), 1u);
  for (const auto &call : calls()) {
    if (call.at("method") != "workflow_runs.get") { continue; }
    EXPECT_EQ(call.at("params").at("run_id"), consumed.at("run_id"));
    EXPECT_EQ(call.at("params").at("handle"), state().project()->handle);
    EXPECT_EQ(call.at("params").size(), 2u);
  }
  EXPECT_EQ(io::get_string(detail, "status"), "stopped");
  EXPECT_TRUE(detail.at("stop_error").get<bool>());  // only that it stopped with an error, not the text
  EXPECT_EQ(detail.at("counts").size(), 3u);
  EXPECT_EQ(detail.at("counts").at("succeeded"), 2); EXPECT_EQ(detail.at("counts").at("failed"), 1);
  EXPECT_EQ(detail.at("counts").at("pending"), 198);
  const auto &tasks = detail.at("tasks");
  ASSERT_EQ(tasks.size(), 200u);
  EXPECT_EQ(detail.at("more"), 1);
  EXPECT_EQ(tasks[0].at("row"), 3);
  EXPECT_EQ(tasks[0].at("attempt"), 2);
  EXPECT_EQ(tasks[0].at("step"), "simulate evil line");  // controls and the bidirectional override become spaces
  EXPECT_EQ(tasks[0].at("task_id"), "01234567");
  EXPECT_EQ(tasks[0].at("stage"), "collecting");
  const auto &produced = tasks[0].at("produced");
  EXPECT_EQ(produced.at("snapshot_id"), "fedcba98");
  EXPECT_EQ(produced.at("file_count"), 2);
  EXPECT_EQ(produced.at("directory"), "results/run/simulate/row-1");
  ASSERT_EQ(produced.at("files").size(), 2u);
  bool long_name = false;
  for (const auto &name : produced.at("files")) {
    const auto text = name.get<std::string>();
    if (text.starts_with("输出🙂")) {
      long_name = true;
      EXPECT_TRUE(text.ends_with("…")) << text;
      EXPECT_EQ(text.find("-tail"), std::string::npos);
      EXPECT_LE(text.size(), 80u * 4);
    }
  }
  EXPECT_TRUE(long_name);
  EXPECT_FALSE(tasks[1].contains("task_id"));  // no progress: no Runtime task ID
  EXPECT_EQ(tasks[1].at("produced").at("analysis_run_id"), "abcdef01");
  EXPECT_FALSE(tasks[1].at("produced").contains("directory"));  // a parent step is never shown
  EXPECT_FALSE(tasks[2].at("produced").contains("directory"));  // nor an absolute path
  EXPECT_EQ(tasks[2].at("row"), 7);
  const auto dumped = detail.dump();
  for (const auto *hidden : {"secret", "4242", "/private", "0123456789abcdef", "fedcba9876543210", "record-"}) {
    EXPECT_EQ(dumped.find(hidden), std::string::npos) << hidden;
  }
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_EQ(io::get_string(agent().view(), "chain_sha256"), chain);
  EXPECT_EQ(io::get_int(agent().view(), "total", -1), total);
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(gets().size(), session_reads);
  agent().close_run_detail(ticket);
  EXPECT_EQ(agent().run_detail(ticket, consumed), nullptr);
  loop.run_ready();
  EXPECT_EQ(count("workflow_runs.get"), 1u);  // closing reads nothing
  expect_no_agent_actions();
}

TEST_F(NativeAgentRuns, LateLinkedTaskRepliesAreDroppedAfterCloseReopenReselectionReopeningOrALostCard)
{
  marker("consumed"); marker("hold_detail");
  select();
  const auto card = consumed_item();
  const auto settled = [&](uint64_t ticket) {
    const auto *detail = agent().run_detail(ticket, card);
    return detail ? io::get_string(*detail, "state") : std::string("closed");
  };
  // Close then reopen the same card (ABA): only the newest ticket takes its own reply.
  const auto first = agent().read_run_detail(card); ASSERT_NE(first, 0u);
  ASSERT_NO_FATAL_FAILURE(detail_held(1));
  agent().close_run_detail(first);
  const auto second = agent().read_run_detail(card); ASSERT_NE(second, 0u); ASSERT_NE(second, first);
  ASSERT_NO_FATAL_FAILURE(detail_held(2));
  ASSERT_NO_FATAL_FAILURE(detail_release(1));
  EXPECT_EQ(settled(first), "closed");
  EXPECT_EQ(settled(second), "reading");
  ASSERT_NO_FATAL_FAILURE(detail_release(2));
  EXPECT_EQ(settled(second), "ready");
  // Switching away and back to the same session is another selection.
  const auto third = agent().read_run_detail(card); ASSERT_NE(third, 0u);
  ASSERT_NO_FATAL_FAILURE(detail_held(3));
  EXPECT_EQ(settled(second), "ready");  // another ticket of the same card keeps its own result
  agent().select("session-b"); agent().select("session-a"); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  EXPECT_EQ(settled(second), "closed"); EXPECT_EQ(settled(third), "closed");
  ASSERT_NO_FATAL_FAILURE(detail_release(3));
  EXPECT_EQ(settled(third), "closed");
  // Reopening the project replaces the opening.
  const auto fourth = agent().read_run_detail(card); ASSERT_NE(fourth, 0u);
  ASSERT_NO_FATAL_FAILURE(detail_held(4));
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  EXPECT_EQ(settled(fourth), "closed");  // The old handle is still present while the open request is in flight.
  EXPECT_EQ(agent().read_run_detail(card), 0u);
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
  ASSERT_NO_FATAL_FAILURE(detail_release(4));
  ASSERT_NO_FATAL_FAILURE(select());
  EXPECT_EQ(settled(fourth), "closed");
  // The card leaves the session's cards while its read is held.
  const auto fifth = agent().read_run_detail(card); ASSERT_NE(fifth, 0u);
  ASSERT_NO_FATAL_FAILURE(detail_held(5));
  marker("omit_cards");
  const auto serial = io::get_int(agent().view(), "get_serial", 0);
  agent().draft_changed(""); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return io::get_int(agent().view(), "get_serial", 0) > serial; }));
  EXPECT_FALSE(agent().can_read_run_detail(card));
  EXPECT_EQ(settled(fifth), "closed");
  ASSERT_NO_FATAL_FAILURE(detail_release(5));
  EXPECT_EQ(settled(fifth), "closed");
  EXPECT_EQ(agent().read_run_detail(card), 0u);
  EXPECT_EQ(count("workflow_runs.get"), 5u);
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  expect_no_agent_actions();
}

TEST_F(NativeAgentRuns, AMissingOrDifferentRunStaysOnItsCardWithoutTouchingTheSession)
{
  marker("consumed"); marker("run_missing");
  select();
  const auto card = consumed_item(), pending = pending_item();
  const auto session_reads = gets().size(), lists = count("list");
  const auto decline = agent().can_decide_run(pending, "decline");
  const auto missing = agent().read_run_detail(card);
  ASSERT_TRUE(loop.pump_until([&] {
    const auto *detail = agent().run_detail(missing, card);
    return detail && io::get_string(*detail, "state") != "reading";
  }));
  const auto failed = *agent().run_detail(missing, card);
  EXPECT_EQ(failed, Json({{"state", "unavailable"}}));  // never the service's message or path
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_FALSE(agent().busy());
  EXPECT_EQ(agent().can_decide_run(pending, "decline"), decline);
  EXPECT_EQ(agent().selected(), "session-a");
  std::filesystem::remove(dir.path() / "run_missing"); marker("run_mismatch");
  agent().close_run_detail(missing);
  const auto mismatch = agent().read_run_detail(card);
  ASSERT_TRUE(loop.pump_until([&] {
    const auto *detail = agent().run_detail(mismatch, card);
    return detail && io::get_string(*detail, "state") != "reading";
  }));
  EXPECT_EQ(*agent().run_detail(mismatch, card), Json({{"state", "mismatch"}}));  // no tasks of another plan
  loop.run_ready();
  EXPECT_EQ(gets().size(), session_reads); EXPECT_EQ(count("list"), lists);
  EXPECT_EQ(count("workflow_runs.get"), 2u);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRuns, SnapshotFilesListOnlyTheTasksValidatedOutputsAndPreviewSmallTextLiterally)
{
  marker("consumed");
  const auto captured = produce();
  select();
  const auto card = consumed_item();
  const auto ticket = ready_detail(card);
  const auto detail = *agent().run_detail(ticket, card);
  ASSERT_EQ(io::get_string(detail, "state"), "ready") << detail.dump();
  // Entries for the tasks that produced a snapshot and output records; the IDs themselves stay private.
  EXPECT_EQ(detail.at("tasks").at(0).at("produced").at("files_entry"), 0);
  EXPECT_FALSE(detail.at("tasks").at(1).at("produced").contains("files_entry"));  // snapshot, no records
  EXPECT_EQ(detail.at("tasks").at(2).at("produced").at("files_entry"), 1);
  for (const auto &[name, record] : captured.records) { EXPECT_EQ(detail.dump().find(record), std::string::npos); }
  EXPECT_EQ(detail.dump().find(captured.snapshot_id), std::string::npos);
  ASSERT_TRUE(agent().can_read_run_files(ticket, card));
  const auto chain = io::get_string(agent().view(), "chain_sha256");
  const auto total = io::get_int(agent().view(), "total", -1);
  const auto revision = state().project()->revision;
  const auto session_reads = gets().size();
  const auto writes = count("files.index") + count("snapshots.capture");
  EXPECT_FALSE(agent().read_run_files(ticket, card, 2));  // no third entry
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 0));  // nothing listed yet
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0));
  EXPECT_FALSE(agent().busy());
  EXPECT_EQ(files_state(ticket, card), "reading");
  ASSERT_TRUE(settle_files(ticket, card));
  const auto files = *agent().run_files(ticket, card);
  ASSERT_EQ(io::get_string(files, "state"), "ready") << files.dump();
  ASSERT_EQ(count("snapshots.get"), 1u);
  for (const auto &call : calls()) {
    if (call.at("method") == "snapshots.get") {
      EXPECT_EQ(call.at("params"), Json({{"handle", state().project()->handle}, {"snapshot_id", captured.snapshot_id}}));
    }
  }
  const Json expected = Json::parse(R"([
    {"output": "notes", "name": "notes.txt", "size": 90, "preview": "text"},
    {"output": "big", "name": "big.log", "size": 307201, "preview": "large"},
    {"output": "binary.out", "name": "binary.out", "size": 13, "preview": "text"},
    {"output": "scalar.vti", "name": "scalar.vti", "size": 28, "preview": "format"},
    {"output": "page.html", "name": "page.html", "size": 49, "preview": "format"},
    {"output": "empty.txt", "name": "empty.txt", "size": 0, "preview": "text"}])");
  EXPECT_EQ(files.at("files"), expected) << files.dump();
  EXPECT_EQ(files.at("more"), 0);
  const auto listed = files.dump();
  for (const auto &[name, record] : captured.records) { EXPECT_EQ(listed.find(record), std::string::npos); }
  for (const auto *hidden : {"results/run", "/project", ".stk", "sha256"}) { EXPECT_EQ(listed.find(hidden), std::string::npos) << hidden; }
  // A large or unsupported file is never resolved, so the service never hashes it for a preview.
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 1));
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 3));
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 4));
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 6));
  EXPECT_EQ(count("snapshots.resolve"), 0u);
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0));
  EXPECT_EQ(preview_state(ticket, card), "reading");
  ASSERT_TRUE(settle_preview(ticket, card));
  const auto preview = *agent().run_file_preview(ticket, card);
  ASSERT_EQ(io::get_string(preview, "state"), "ready") << preview.dump();
  EXPECT_EQ(io::get_string(preview, "name"), "notes.txt");
  // HTML stays markup text; CRLF is one line end; a lone CR, ESC and the bidirectional override are shown.
  EXPECT_EQ(io::get_string(preview, "text"), "<b>bold</b> <script>alert(1)</script>\nline two\\u{d}hidden\\u{1b}[31mred"
            "\\u{1b}[0m\ttab \\u{202e}evil\n中文🙂\n");
  ASSERT_EQ(count("snapshots.resolve"), 1u);
  for (const auto &call : calls()) {
    if (call.at("method") == "snapshots.resolve") {
      EXPECT_EQ(call.at("params"), Json({{"handle", state().project()->handle}, {"snapshot_id", captured.snapshot_id},
                                         {"record_id", captured.records.at("notes.txt")}}));
    }
  }
  EXPECT_EQ(preview.dump().find(dir.str()), std::string::npos);
  EXPECT_EQ(preview.dump().find(".stk"), std::string::npos);
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 2));
  ASSERT_TRUE(settle_preview(ticket, card));
  EXPECT_EQ(*agent().run_file_preview(ticket, card), Json({{"state", "not_text"}, {"file", 2}, {"name", "binary.out"}}));
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 5));
  ASSERT_TRUE(settle_preview(ticket, card));
  EXPECT_EQ(preview_state(ticket, card), "ready");
  EXPECT_EQ(io::get_string(*agent().run_file_preview(ticket, card), "text"), "");
  // Back to the list, then to the tasks: nothing more is read.
  agent().close_run_file_preview(ticket);
  EXPECT_EQ(preview_state(ticket, card), "closed");
  EXPECT_EQ(files_state(ticket, card), "ready");
  agent().close_run_files(ticket);
  EXPECT_EQ(files_state(ticket, card), "closed");
  EXPECT_EQ(io::get_string(*agent().run_detail(ticket, card), "state"), "ready");
  // The other task's entry lists only its own output record of the same snapshot.
  ASSERT_TRUE(agent().read_run_files(ticket, card, 1));
  ASSERT_TRUE(settle_files(ticket, card));
  EXPECT_EQ(agent().run_files(ticket, card)->at("files"),
            Json::parse(R"([{"output": "notes.txt", "name": "notes.txt", "size": 90, "preview": "text"}])"));
  loop.run_ready();
  EXPECT_EQ(count("snapshots.get"), 2u);
  EXPECT_EQ(count("snapshots.resolve"), 3u);
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  EXPECT_EQ(count("files.index") + count("snapshots.capture"), writes);
  for (const auto *method : {"snapshots.verify", "snapshots.list", "files.resolve", "files.refresh", "files.remove"}) {
    EXPECT_EQ(count(method), 0u) << method;
  }
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_EQ(io::get_string(agent().view(), "chain_sha256"), chain);
  EXPECT_EQ(io::get_int(agent().view(), "total", -1), total);
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(gets().size(), session_reads);
  agent().close_run_detail(ticket);
  EXPECT_EQ(files_state(ticket, card), "closed");
  expect_no_agent_actions();
}

TEST_F(NativeAgentRuns, MismatchedTamperedOrUnreadableSnapshotFilesAreNeverShown)
{
  marker("consumed");
  const auto captured = produce();
  select();
  const auto card = consumed_item();
  // A produced record that the frozen manifest does not list: nothing is listed, nothing is resolved.
  write_produced({{"0", {{"snapshot_id", captured.snapshot_id},
      {"files", {{"notes", captured.records.at("notes.txt")}, {"ghost", "00000000-0000-4000-8000-000000000000"}}}}}});
  auto ticket = ready_detail(card);
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_TRUE(settle_files(ticket, card));
  EXPECT_EQ(*agent().run_files(ticket, card), Json({{"state", "mismatch"}, {"entry", 0}}));
  EXPECT_FALSE(agent().read_run_file_preview(ticket, card, 0));
  agent().close_run_detail(ticket);
  // A snapshot the project does not have.
  write_produced({{"0", {{"snapshot_id", "00000000-0000-4000-8000-000000000001"},
      {"files", {{"notes", captured.records.at("notes.txt")}}}}}});
  ticket = ready_detail(card);
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_TRUE(settle_files(ticket, card));
  EXPECT_EQ(*agent().run_files(ticket, card), Json({{"state", "unavailable"}, {"entry", 0}}));
  agent().close_run_detail(ticket);
  // Malformed IDs offer no entry at all.
  write_produced({{"0", {{"snapshot_id", "not-a-snapshot"}, {"files", {{"notes", captured.records.at("notes.txt")}}}}},
                  {"2", {{"snapshot_id", captured.snapshot_id}, {"files", {{"notes", "record-1"}}}}}});
  ticket = ready_detail(card);
  EXPECT_FALSE(agent().run_detail(ticket, card)->at("tasks").at(0).at("produced").contains("files_entry"));
  EXPECT_FALSE(agent().run_detail(ticket, card)->at("tasks").at(2).at("produced").contains("files_entry"));
  EXPECT_FALSE(agent().read_run_files(ticket, card, 0));
  agent().close_run_detail(ticket);
  EXPECT_EQ(count("snapshots.get"), 2u);
  EXPECT_EQ(count("snapshots.resolve"), 0u);
  // A resolve reply of another identity, digest or size, bytes that changed, a final link or a failure.
  produce();
  ticket = ready_detail(card);
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_TRUE(settle_files(ticket, card));
  ASSERT_EQ(files_state(ticket, card), "ready");
  const std::vector<std::pair<const char *, const char *>> cases = {
      {"resolve_wrong_sha", "mismatch"}, {"resolve_wrong_size", "mismatch"}, {"resolve_wrong_record", "mismatch"},
      {"resolve_changed_bytes", "mismatch"}, {"resolve_symlink", "unavailable"}, {"resolve_fail", "unavailable"}};
  for (const auto &[name, expected] : cases) {
    marker(name);
    ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)) << name;
    ASSERT_TRUE(settle_preview(ticket, card)) << name;
    EXPECT_EQ(*agent().run_file_preview(ticket, card), Json({{"state", expected}, {"file", 0}, {"name", "notes.txt"}})) << name;
    std::filesystem::remove(dir.path() / name);
  }
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)); ASSERT_TRUE(settle_preview(ticket, card));
  EXPECT_EQ(preview_state(ticket, card), "ready");  // the frozen object itself was never changed
  EXPECT_EQ(count("snapshots.resolve"), cases.size() + 1);
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_FALSE(agent().busy());
  expect_no_agent_actions();
}

TEST_F(NativeAgentRuns, LateSnapshotRepliesAreDroppedAfterBackCloseAnotherListReselectionOrReopening)
{
  marker("consumed");
  produce();
  select();
  const auto card = consumed_item();
  auto ticket = ready_detail(card);
  marker("hold_snapshot");
  // Back to the tasks while the list is read.
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(1));
  agent().close_run_files(ticket);
  ASSERT_NO_FATAL_FAILURE(snapshot_release(1));
  EXPECT_EQ(files_state(ticket, card), "closed");
  // Another task's list replaces the first one; the first reply does not fill it.
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(2));
  ASSERT_TRUE(agent().read_run_files(ticket, card, 1)); ASSERT_NO_FATAL_FAILURE(snapshot_held(3));
  ASSERT_NO_FATAL_FAILURE(snapshot_release(2));
  EXPECT_EQ(files_state(ticket, card), "reading");
  ASSERT_NO_FATAL_FAILURE(snapshot_release(3));
  ASSERT_EQ(files_state(ticket, card), "ready");
  EXPECT_EQ(agent().run_files(ticket, card)->at("entry"), 1);
  EXPECT_EQ(agent().run_files(ticket, card)->at("files").size(), 1u);
  // Back to the list while a preview is read, then the same file again (ABA): only the newest reply counts.
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(4));
  agent().close_run_file_preview(ticket);
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(5));
  ASSERT_NO_FATAL_FAILURE(snapshot_release(4));
  EXPECT_EQ(preview_state(ticket, card), "reading");
  ASSERT_NO_FATAL_FAILURE(snapshot_release(5));
  EXPECT_EQ(preview_state(ticket, card), "ready");
  // Closing the detail during a preview read.
  agent().close_run_file_preview(ticket);
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(6));
  agent().close_run_detail(ticket);
  ASSERT_NO_FATAL_FAILURE(snapshot_release(6));
  EXPECT_EQ(preview_state(ticket, card), "closed"); EXPECT_EQ(files_state(ticket, card), "closed");
  // Switching away and back to the same session during a list read.
  std::filesystem::remove(dir.path() / "hold_snapshot");
  ticket = ready_detail(card);
  marker("hold_snapshot");
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(7));
  agent().select("session-b"); agent().select("session-a"); agent().pump(0);
  ASSERT_TRUE(loop.pump_until([&] { return !agent().view().empty(); }));
  ASSERT_NO_FATAL_FAILURE(snapshot_release(7));
  EXPECT_EQ(files_state(ticket, card), "closed");
  EXPECT_EQ(agent().run_detail(ticket, card), nullptr);
  // Reopening the project during a preview read: entries are disabled while it opens, and nothing comes back.
  std::filesystem::remove(dir.path() / "hold_snapshot");
  ticket = ready_detail(card);
  ASSERT_TRUE(agent().read_run_files(ticket, card, 0)); ASSERT_TRUE(settle_files(ticket, card));
  marker("hold_snapshot");
  ASSERT_TRUE(agent().read_run_file_preview(ticket, card, 0)); ASSERT_NO_FATAL_FAILURE(snapshot_held(9));
  ASSERT_TRUE(state().open(dir.str() + "/project"));
  EXPECT_EQ(preview_state(ticket, card), "closed");
  EXPECT_FALSE(agent().read_run_files(ticket, card, 0));
  ASSERT_TRUE(loop.pump_until([&] { return !state().busy(); }));
  ASSERT_NO_FATAL_FAILURE(snapshot_release(9));
  ASSERT_NO_FATAL_FAILURE(select());
  EXPECT_EQ(preview_state(ticket, card), "closed");
  EXPECT_EQ(agent().run_detail(ticket, card), nullptr);
  EXPECT_EQ(count("snapshots.get"), 5u);
  EXPECT_EQ(count("snapshots.resolve"), 4u);
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  expect_no_agent_actions();
}

/** The acceptance rows of docs/design/native-conversation-references.md 5.2 from the workbench rail. */
class NativeAgentRunDetailUI : public NativeAgentRuns {
 protected:
  using NativeAgentRuns::NativeAgentRuns;
  int clicks = 0;
  void click(const std::string &key)
  {
    const auto *control = f.screen.ui()->find(key);
    ASSERT_NE(control, nullptr) << key; ASSERT_TRUE(control->enabled) << key;
    const auto [x, y] = f.widget_center(key);
    ++clicks; ASSERT_TRUE(f.drv->click(x, y)) << key; frame();
  }
  const ui::Block *panel()
  {
    for (const auto &block : f.screen.ui()->blocks()) {
      if (block->kind() == ui::Block::Kind::Modal) { return block.get(); }
    }
    return nullptr;
  }
  /** Both sessions exist in the fixture, none is selected, and the workbench rail lists them. */
  void open_rail(const char *ready = "workbench_agent_session/session-a")
  {
    marker("consumed");
    select("session-b"); select("session-a");
    agent().select("");
    agent().draft_changed("");
    f.shell->open_workbench(f.screen);
    f.screen.run_deferred();
    ASSERT_TRUE(loop.pump_until([&] {
      frame();
      const auto &discussion = state().discussion();
      const bool history_ready = !discussion.recent_requests_supported() || discussion.recent_requests();
      return history_ready && agent().list_loaded() && agent().sessions().size() == 2 &&
             f.screen.ui()->find(ready) != nullptr;
    }, 30)) << agent().error();
  }
  void open_session_a()
  {
    ASSERT_NO_FATAL_FAILURE(click("workbench_agent_session/session-a"));
    ASSERT_TRUE(loop.pump_until([&] {
      frame(); return f.screen.ui()->find("ai_agent_run_detail/approve:session-a") != nullptr;
    }, 30)) << agent().error();
  }
  /** The panel's wrapped lines joined without spaces (a wrap may drop the space it breaks at). */
  std::string panel_text()
  {
    const auto *tasks = f.screen.ui()->find("ai_agent_run_detail_tasks");
    std::string text;
    for (size_t i = 0; tasks && tasks->log && i < tasks->log->line_count(); ++i) { text += std::string(tasks->log->line(i)); }
    text.erase(std::remove(text.begin(), text.end(), ' '), text.end());
    return text;
  }
  void wait_ready()
  {
    ASSERT_TRUE(loop.pump_until([&] {
      frame(); return f.screen.ui()->find("ai_agent_run_detail_tasks") != nullptr;
    }, 30));
  }
  std::string entry() { return "ai_agent_run_detail/approve:session-a"; }
  /** Texts of the open panel's labels and paragraphs, in drawing order. */
  std::vector<std::string> panel_labels()
  {
    std::vector<std::string> texts;
    if (const auto *modal = panel()) {
      for (const auto &w : modal->widgets()) {
        if (w.type == ui::WidgetType::Label || w.type == ui::WidgetType::Paragraph) { texts.push_back(w.text); }
      }
    }
    return texts;
  }
  bool has_label(const std::string &text)
  {
    const auto texts = panel_labels();
    return std::find(texts.begin(), texts.end(), text) != texts.end();
  }
  void wait_for(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); return f.screen.ui()->find(key) != nullptr; }, 30)) << key;
  }
  /** The preview's wrapped lines joined without spaces (tabs are expanded to spaces). */
  std::string preview_text()
  {
    const auto *log = f.screen.ui()->find("ai_agent_run_detail_preview_text");
    std::string text;
    for (size_t i = 0; log && log->log && i < log->log->line_count(); ++i) { text += std::string(log->log->line(i)); }
    text.erase(std::remove(text.begin(), text.end(), ' '), text.end());
    return text;
  }
  void tab_to(const std::string &key)
  {
    for (int i = 0; i < 12 && f.screen.ui()->focused() != id(key); ++i) { ASSERT_TRUE(f.drv->key(wm::Key::Tab)); frame(); }
    ASSERT_NE(id(key), 0u) << key;
    ASSERT_EQ(f.screen.ui()->focused(), id(key)) << key;
  }
  void expect_no_saved_file_state(const Captured &captured)
  {
    for (auto *area : f.screen.areas()) {
      const auto *editor_area = dynamic_cast<const EditorArea *>(area);
      if (!editor_area) { continue; }
      const auto saved = editor_area->editor().save_workspace_state().dump();
      std::vector<std::string> hidden = {captured.snapshot_id, "notes.txt", "alert(1)", "results/run", "files_entry"};
      for (const auto &[name, record] : captured.records) { hidden.push_back(record); }
      for (const auto &text : hidden) { EXPECT_EQ(saved.find(text), std::string::npos) << text; }
    }
  }
  ui::WidgetId id(const std::string &key)
  {
    const auto *found = f.screen.ui()->find(key); return found ? found->id : 0;
  }
};

TEST_F(NativeAgentRunDetailUI, FocusedConversationKeepsTheCompleteSessionListAvailableOnDemand)
{
  f.drv->ctx.rect = {0, 0, 1600, 1100};
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  const auto draft = "ai_agent_text/" + state().project()->handle;
  ASSERT_NE(f.screen.ui()->find(draft), nullptr);
  f.screen.ui()->find(draft)->string.assign("An unsent question");
  frame();
  EXPECT_EQ(f.screen.ui()->find("ai_agent_session"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_refresh"), nullptr);
  EXPECT_NE(f.screen.ui()->find("workbench_agent_session/session-b"), nullptr);
  const auto before = calls();
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_sessions"));
  const auto *sessions = f.screen.ui()->find("ai_agent_session");
  ASSERT_NE(sessions, nullptr);
  ASSERT_FALSE(sessions->items.empty());
  EXPECT_EQ(sessions->items.front(), "New session");
  EXPECT_NE(f.screen.ui()->find("ai_agent_refresh"), nullptr);
  EXPECT_EQ(calls(), before);
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_sessions"));
  EXPECT_EQ(f.screen.ui()->find("ai_agent_session"), nullptr);
  ASSERT_NE(f.screen.ui()->find(draft), nullptr);
  EXPECT_EQ(f.screen.ui()->find(draft)->string.value(), "An unsent question");
  EXPECT_EQ(agent().selected(), "session-a");
  EXPECT_EQ(calls(), before);
}

TEST_F(NativeAgentRunDetailUI, ConversationShortcutSendsOnceThroughTheExistingAgentAction)
{
  f.drv->ctx.rect = {0, 0, 1600, 1400};
  marker("answered");
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  const auto input = "ai_agent_text/" + state().project()->handle;
  ASSERT_NO_FATAL_FAILURE(click(input));
  ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, "Check the frozen results")); frame();
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();
  EXPECT_EQ(count("say"), 0u);
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "Check the frozen results\n");
  ASSERT_TRUE(f.drv->key(wm::Key::Esc)); frame();
  EXPECT_EQ(count("say"), 0u);
  EXPECT_EQ(f.screen.ui()->editing(), 0u);
  EXPECT_EQ(f.screen.ui()->focused(), id(input));
  ASSERT_NE(f.screen.ui()->find(input), nullptr);
  EXPECT_EQ(f.screen.ui()->find(input)->string.value(), "Check the frozen results\n");
  ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, "Use the saved file")); frame();
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "Check the frozen results\nUse the saved file");
  const auto *send = f.screen.ui()->find("ai_agent_send");
  ASSERT_NE(send, nullptr);
  ASSERT_TRUE(send->enabled);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  ASSERT_TRUE(f.drv->key(wm::Key::Enter, primary));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return !agent().busy() && count("start") == 1u; }, 30));
  EXPECT_EQ(count("say"), 1u);
  EXPECT_EQ(count("run_target"), 1u);
  EXPECT_EQ(count("run_decide"), 0u);
  ASSERT_NE(f.screen.ui()->find(input), nullptr);
  EXPECT_TRUE(f.screen.ui()->find(input)->string.value().empty());
  EXPECT_EQ(f.screen.ui()->focused(), id(input));
}

TEST_F(NativeAgentRunDetailUI, ExplicitSendFollowsTheTimelineAndOtherSessionsKeepTheirOwnPosition)
{
  f.drv->ctx.rect = {0, 0, 1600, 1400};
  marker("answered"); marker("long_timeline");
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  const auto timeline_key = "ai_agent_timeline";
  const auto scroll = [&] {
    const auto *timeline = f.screen.ui()->find(timeline_key);
    return timeline ? f.screen.ui()->scroll_of(timeline->id) : -1.0f;
  };
  const auto tail = scroll();
  ASSERT_GT(tail, 100.0f);
  ASSERT_NO_FATAL_FAILURE(click(timeline_key));
  ASSERT_TRUE(f.drv->key(wm::Key::PageUp)); frame();
  const auto reading = scroll();
  EXPECT_LT(reading, tail);
  ASSERT_NO_FATAL_FAILURE(click("workbench_agent_session/session-b"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return scroll() == tail; }, 30));
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  EXPECT_FLOAT_EQ(scroll(), reading);
  marker("grow_timeline_b");
  ASSERT_NO_FATAL_FAILURE(click("workbench_agent_session/session-b"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame(); return agent().view().value("chain_sha256", std::string()) == "session-b-late";
  }, 30));
  EXPECT_FLOAT_EQ(scroll(), tail);
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  EXPECT_FLOAT_EQ(scroll(), reading);
  EXPECT_EQ(count("say"), 0u);

  const auto input = "ai_agent_text/" + state().project()->handle;
  ASSERT_NO_FATAL_FAILURE(click(input));
  ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, "Follow the next reply")); frame();
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_send"));
  EXPECT_FLOAT_EQ(scroll(), tail);
  ASSERT_TRUE(loop.pump_until([&] { frame(); return !agent().busy() && count("start") == 1u; }, 30));
  EXPECT_EQ(count("say"), 1u);
  EXPECT_EQ(count("run_decide"), 0u);
}

TEST_F(NativeAgentRunDetailUI, WideWindowOpensARightPanelInTwoClicksAndReturnsFocusWithoutSideEffects)
{
  f.drv->ctx.rect = {0, 0, 1600, 1100};
  ASSERT_NO_FATAL_FAILURE(open_rail());
  const auto layout = f.screen.arrangement();
  const auto viewer = f.shell->store().viewer().save_workspace_state();
  const auto camera = f.shell->store().viewer().camera_serial();
  const auto exchange = state().discussion().exchange_id();
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  const auto agent_text = "ai_agent_text/" + state().project()->handle;
  ASSERT_NE(f.screen.ui()->find(agent_text), nullptr);
  f.screen.ui()->find(agent_text)->string.assign("Unsent agent words");
  frame();
  // The card that still waits for a decision has no linked tasks, and approval stays locked as before.
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail/approve2:session-a"), nullptr);
  ASSERT_NE(f.screen.ui()->find("ai_agent_run_start/approve2:session-a"), nullptr);
  EXPECT_FALSE(f.screen.ui()->find("ai_agent_run_start/approve2:session-a")->enabled);
  const auto chain = io::get_string(agent().view(), "chain_sha256");
  const auto total = io::get_int(agent().view(), "total", -1);
  const auto revision = state().project()->revision;
  const auto *timeline = f.screen.ui()->find("ai_agent_timeline");
  ASSERT_NE(timeline, nullptr);
  const float scrollbar = f.screen.ui()->style().scrollbar;
  EXPECT_NEAR(timeline->rect.w, 880.0f, scrollbar);
  EXPECT_NEAR(timeline->rect.cx(), (1600.0f + 144.0f) / 2.0f, scrollbar / 2.0f + 1.0f);
  const auto reading = f.screen.ui()->scroll_of(timeline->id);
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_EQ(clicks, 2);
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  const auto *modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_FLOAT_EQ(modal->frame().x1(), 1600.0f);  // right-anchored, 420 px like the Web dialog
  EXPECT_FLOAT_EQ(modal->frame().w, 420.0f);
  EXPECT_FLOAT_EQ(modal->frame().y, 0.0f);
  EXPECT_FLOAT_EQ(modal->frame().h, 1100.0f);
  EXPECT_TRUE(f.screen.ui()->native_view_interaction_blocked());  // the Viewer below takes no input
  ASSERT_NE(id("ai_agent_run_detail_close"), 0u);
  EXPECT_EQ(f.screen.ui()->focused(), id("ai_agent_run_detail_close"));
  const auto *tasks = f.screen.ui()->find("ai_agent_run_detail_tasks");
  ASSERT_NE(tasks, nullptr); ASSERT_NE(tasks->log, nullptr);
  const auto text = panel_text();
  EXPECT_NE(text.find("Row3·simulateevilline·attempt2·Done·task01234567Frozensnapshotfedcba98·2files"), std::string::npos) << text;
  EXPECT_NE(text.find("Frozensnapshot11112222Analysisrunabcdef01Row7·collect"), std::string::npos) << text;
  EXPECT_NE(text.find("Projectfiles:输出🙂长"), std::string::npos);
  EXPECT_NE(text.find("…,scalar.vti"), std::string::npos);
  EXPECT_NE(text.find("Projectdirectory:results/run/simulate/row-1"), std::string::npos);
  EXPECT_NE(text.find("1moretasksarenotshown."), std::string::npos);
  EXPECT_EQ(text.find("secret"), std::string::npos);
  // The long list scrolls inside the panel.
  wm::Event wheel; wheel.type = wm::EventType::Wheel; wheel.x = int(tasks->rect.cx());
  wheel.y = f.screen.rect().ymax - 1 - int(tasks->rect.cy()); wheel.wheel_y = -3;
  ASSERT_TRUE(f.drv->send(wheel)); frame();
  EXPECT_GT(f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_run_detail_tasks")->id), 0.0f);
  const auto first_close = f.screen.ui()->find("ai_agent_run_detail_close")->on_click;
  // Esc closes and focus returns to the card's entry.
  ASSERT_TRUE(f.drv->key(wm::Key::Esc)); frame(); frame();
  EXPECT_EQ(panel(), nullptr);
  ASSERT_NE(id(entry()), 0u);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  // Enter on the entry opens again (one more read); the Close button closes and restores focus too.
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_EQ(count("workflow_runs.get"), 2u);
  first_close(); frame();
  ASSERT_NE(panel(), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_close")); frame();
  EXPECT_EQ(panel(), nullptr);
  ASSERT_NE(id(entry()), 0u);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(count("workflow_runs.get"), 2u);
  EXPECT_EQ(f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_timeline")->id), reading);
  EXPECT_EQ(io::get_string(agent().view(), "chain_sha256"), chain);
  EXPECT_EQ(io::get_int(agent().view(), "total", -1), total);
  EXPECT_EQ(agent().selected(), "session-a");
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(state().discussion().exchange_id(), exchange);
  EXPECT_EQ(f.screen.arrangement(), layout);
  EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer);
  EXPECT_EQ(f.shell->store().viewer().camera_serial(), camera);
  EXPECT_EQ(f.screen.ui()->find(agent_text)->string.value(), "Unsent agent words");
  for (auto *area : f.screen.areas()) {
    const auto *editor_area = dynamic_cast<const EditorArea *>(area);
    if (!editor_area) { continue; }
    const auto saved = editor_area->editor().save_workspace_state().dump();
    for (const auto *hidden : {"run:session-a", "\"tasks\"", "snapshot_id", "fedcba98"}) {
      EXPECT_EQ(saved.find(hidden), std::string::npos) << hidden;
    }
  }
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailUI, ReselectingTheSessionDropsTheOpenDetailWithoutReadingAgain)
{
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  ASSERT_TRUE(agent().select_history_session("session-b"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return io::get_string(agent().view().value("session", Json::object()), "id") == "session-b"; }));
  EXPECT_EQ(panel(), nullptr);
  ASSERT_TRUE(agent().select_history_session("session-a"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return f.screen.ui()->find(entry()) != nullptr; }));
  frame();
  EXPECT_EQ(panel(), nullptr);  // returning does not reopen or read again
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  // A page change that hides the conversation (here the workbench's result page) closes it as well.
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  f.shell->open_workbench(f.screen, true); f.screen.run_deferred(); frame(); frame();
  EXPECT_EQ(panel(), nullptr);
  f.shell->open_workbench(f.screen); f.screen.run_deferred();
  ASSERT_TRUE(loop.pump_until([&] { frame(); return f.screen.ui()->find(entry()) != nullptr; }, 30));
  frame();
  EXPECT_EQ(panel(), nullptr);
  EXPECT_EQ(count("workflow_runs.get"), 2u);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailUI, AFailedReadStaysInTheOpenedPanelOfSessionA)
{
  marker("run_missing");
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_TRUE(loop.pump_until([&] {
    frame();
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &w : block->widgets()) { if (w.text == "This run cannot be read.") { return true; } }
    }
    return false;
  }, 30));
  EXPECT_EQ(agent().selected(), "session-a");
  EXPECT_TRUE(agent().error().empty()) << agent().error();
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailUI, WideWindowViewsAndPreviewsSnapshotFilesInTheSamePanelAndGoesBackToEachPlace)
{
  f.drv->ctx.rect = {0, 0, 1600, 1100};
  const auto captured = produce();  // real project files in one frozen snapshot, before the fixed start
  ASSERT_NO_FATAL_FAILURE(open_rail());
  const auto layout = f.screen.arrangement();
  const auto viewer = f.shell->store().viewer().save_workspace_state();
  const auto camera = f.shell->store().viewer().camera_serial();
  const auto exchange = state().discussion().exchange_id();
  const auto revision = state().project()->revision;
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  const auto agent_text = "ai_agent_text/" + state().project()->handle;
  f.screen.ui()->find(agent_text)->string.assign("Unsent agent words");
  frame();
  const auto chain = io::get_string(agent().view(), "chain_sha256");
  const auto total = io::get_int(agent().view(), "total", -1);
  const auto reading = f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_timeline")->id);
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  const auto *tasks = f.screen.ui()->find("ai_agent_run_detail_tasks");
  wm::Event wheel; wheel.type = wm::EventType::Wheel; wheel.x = int(tasks->rect.cx());
  wheel.y = f.screen.rect().ymax - 1 - int(tasks->rect.cy()); wheel.wheel_y = 2;
  ASSERT_TRUE(f.drv->send(wheel)); frame();
  const auto tasks_position = f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_run_detail_tasks")->id);
  ASSERT_NE(f.screen.ui()->find("ai_agent_run_detail_files/0"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0")->text, "View files · Row 3 · simulate evil line");
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/1")->text, "View files · Row 7 · collect");
  const auto stale_files = f.screen.ui()->find("ai_agent_run_detail_files/0")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_files/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/0"));
  const auto *modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_EQ(modal->title(), "Snapshot files");
  EXPECT_FLOAT_EQ(modal->frame().x1(), 1600.0f);  // the same right panel
  EXPECT_FLOAT_EQ(modal->frame().w, 420.0f);
  EXPECT_FLOAT_EQ(modal->frame().y, 0.0f);
  EXPECT_FLOAT_EQ(modal->frame().y1(), 1100.0f);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_tasks"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0")->text, "Back to linked tasks");
  EXPECT_TRUE(has_label("notes · notes.txt · 90 bytes")) << ::testing::PrintToString(panel_labels());
  EXPECT_TRUE(has_label("big · big.log · 307201 bytes"));
  EXPECT_TRUE(has_label("Over 256 KiB"));
  EXPECT_TRUE(has_label("No text preview"));
  for (const auto *absent : {"ai_agent_run_detail_preview/1", "ai_agent_run_detail_preview/3", "ai_agent_run_detail_preview/4"}) {
    EXPECT_EQ(f.screen.ui()->find(absent), nullptr) << absent;  // large, VTI and HTML files have no preview
  }
  EXPECT_NE(f.screen.ui()->find("ai_agent_run_detail_preview/2"), nullptr);
  EXPECT_NE(f.screen.ui()->find("ai_agent_run_detail_preview/5"), nullptr);
  const auto stale_preview = f.screen.ui()->find("ai_agent_run_detail_preview/0")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_preview/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview_text"));
  stale_files(); stale_preview(); frame();
  modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_EQ(modal->title(), "File preview");
  EXPECT_FLOAT_EQ(modal->frame().x1(), 1600.0f);
  EXPECT_FLOAT_EQ(modal->frame().w, 420.0f);
  EXPECT_FLOAT_EQ(modal->frame().h, 1100.0f);
  EXPECT_TRUE(has_label("notes.txt"));
  const auto text = preview_text();
  EXPECT_NE(text.find("<b>bold</b><script>alert(1)</script>linetwo\\u{d}hidden\\u{1b}[31mred\\u{1b}[0mtab\\u{202e}evil中文🙂"),
            std::string::npos) << text;
  EXPECT_EQ(f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_run_detail_preview_text")->id), 0.0f);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "Back to snapshot files");
  const auto stale_back = f.screen.ui()->find("ai_agent_run_detail_preview/0")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_preview/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/5"));
  stale_back(); frame();
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "Preview");
  EXPECT_EQ(panel()->title(), "Snapshot files");
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_files/0"));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  frame();
  EXPECT_EQ(panel()->title(), "Linked tasks");
  EXPECT_EQ(f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_run_detail_tasks")->id), tasks_position);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0")->text, "View files · Row 3 · simulate evil line");
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_close")); frame();
  EXPECT_EQ(panel(), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(clicks, 7);  // session, linked tasks, view files, preview, back, back, close
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  EXPECT_EQ(count("snapshots.get"), 1u);
  EXPECT_EQ(count("snapshots.resolve"), 1u);
  EXPECT_EQ(count("snapshots.verify"), 0u);
  EXPECT_EQ(f.screen.ui()->scroll_of(f.screen.ui()->find("ai_agent_timeline")->id), reading);
  EXPECT_EQ(io::get_string(agent().view(), "chain_sha256"), chain);
  EXPECT_EQ(io::get_int(agent().view(), "total", -1), total);
  EXPECT_EQ(agent().selected(), "session-a");
  EXPECT_EQ(state().project()->revision, revision);
  EXPECT_EQ(state().discussion().exchange_id(), exchange);
  EXPECT_EQ(f.screen.arrangement(), layout);
  EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer);
  EXPECT_EQ(f.shell->store().viewer().camera_serial(), camera);
  EXPECT_EQ(f.screen.ui()->find(agent_text)->string.value(), "Unsent agent words");
  expect_no_saved_file_state(captured);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailUI, KeyboardFocusReturnsToTheExactEntryAndFileAfterEachBack)
{
  f.drv->ctx.rect = {0, 0, 1600, 1100};
  produce();
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  ASSERT_NO_FATAL_FAILURE(tab_to("ai_agent_run_detail_files/1"));
  const auto second = id("ai_agent_run_detail_files/1");
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();
  // The files page's Back takes the place (and focus) of the entry that opened it.
  EXPECT_EQ(f.screen.ui()->focused(), second);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/1")->text, "Back to linked tasks");
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/0"));
  ASSERT_NO_FATAL_FAILURE(tab_to("ai_agent_run_detail_preview/0"));
  const auto file = id("ai_agent_run_detail_preview/0");
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();
  EXPECT_EQ(f.screen.ui()->focused(), file);
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview_text"));
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "Back to snapshot files");
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();  // Back to the list: focus on the same file's Preview
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/0"));
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "Preview");
  EXPECT_EQ(f.screen.ui()->focused(), file);
  ASSERT_NO_FATAL_FAILURE(tab_to("ai_agent_run_detail_files/1"));
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();  // Back to the tasks: focus on the same entry
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/1")->text, "View files · Row 7 · collect");
  EXPECT_EQ(f.screen.ui()->focused(), second);
  // Esc from the files page closes the whole panel and returns to the card's entry.
  ASSERT_TRUE(f.drv->key(wm::Key::Enter)); frame();
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/0"));
  ASSERT_TRUE(f.drv->key(wm::Key::Esc)); frame(); frame();
  EXPECT_EQ(panel(), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(count("snapshots.get"), 2u);
  EXPECT_EQ(count("snapshots.resolve"), 1u);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailUI, ReselectingTheSessionDropsAnOpenPreviewAndCloseReturnsToTheCard)
{
  produce();
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_files/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/2"));
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_preview/2"));  // binary.out: not UTF-8
  ASSERT_TRUE(loop.pump_until([&] { frame(); return has_label("This file cannot be previewed as UTF-8 text."); }, 30));
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview_text"), nullptr);
  ASSERT_TRUE(agent().select_history_session("session-b"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return io::get_string(agent().view().value("session", Json::object()), "id") == "session-b"; }));
  EXPECT_EQ(panel(), nullptr);
  ASSERT_TRUE(agent().select_history_session("session-a"));
  ASSERT_NO_FATAL_FAILURE(wait_for(entry()));
  frame();
  EXPECT_EQ(panel(), nullptr);  // returning neither reopens nor reads again
  // Close from the preview page goes straight back to the card's entry.
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_files/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/5"));
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_preview/5"));  // empty.txt
  ASSERT_TRUE(loop.pump_until([&] { frame(); return has_label("Empty file"); }, 30));
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_close")); frame();
  EXPECT_EQ(panel(), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(count("workflow_runs.get"), 2u);
  EXPECT_EQ(count("snapshots.get"), 2u);
  EXPECT_EQ(count("snapshots.resolve"), 2u);
  expect_no_agent_actions();
}

class NativeAgentRunDetailNarrowUI : public NativeAgentRunDetailUI {
 protected:
  NativeAgentRunDetailNarrowUI() : NativeAgentRunDetailUI("zh_CN", 680, 1000) {}

  void open_narrow_session_a()
  {
    // History popups close if a different set of rows arrives. The measured route starts with settled history.
    ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
    ASSERT_TRUE(f.screen.ui()->popup_open());
    std::string items;
    for (const auto &block : f.screen.ui()->blocks()) {
      if (block->kind() != ui::Block::Kind::Popup) { continue; }
      for (const auto &candidate : block->widgets()) {
        if (candidate.type != ui::WidgetType::MenuItem) { continue; }
        if (candidate.enabled && candidate.text.ends_with("session-a")) {
          const auto key = candidate.key;
          ASSERT_NO_FATAL_FAILURE(click(key));
          ASSERT_NO_FATAL_FAILURE(wait_for(entry()));
          return;
        }
        items += candidate.text + (candidate.enabled ? "\n" : " (off)\n");
      }
    }
    FAIL() << "Enabled session-a is missing from settled history\n" << items;
  }
};

TEST_F(NativeAgentRunDetailNarrowUI, NarrowChineseWindowOpensABottomSheetFromHistoryInThreeClicks)
{
  ASSERT_NO_FATAL_FAILURE(open_rail("workbench_history"));
  ASSERT_NE(f.screen.ui()->find("workbench_history"), nullptr);
  const auto layout = f.screen.arrangement();
  const auto viewer = f.shell->store().viewer().save_workspace_state();
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(open_narrow_session_a());
  EXPECT_FALSE(f.screen.ui()->popup_open());
  EXPECT_EQ(f.screen.ui()->find(entry())->text, "关联任务");
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_EQ(clicks, 3);
  const auto *modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_FLOAT_EQ(modal->frame().x, 0.0f);  // a full-width bottom sheet, like the Web dialog below 700 px
  EXPECT_FLOAT_EQ(modal->frame().w, 680.0f);
  EXPECT_FLOAT_EQ(modal->frame().y1(), 1000.0f);
  EXPECT_FLOAT_EQ(modal->frame().h, 800.0f);
  const auto *tasks = f.screen.ui()->find("ai_agent_run_detail_tasks");
  ASSERT_NE(tasks, nullptr);
  const auto &style = f.screen.ui()->style();
  const float available = tasks->rect.w - 2 * style.text_margin - style.scrollbar - 2 * style.pixel;
  for (size_t i = 0; i < tasks->log->line_count(); ++i) {
    EXPECT_LE(f.measurer.width(tasks->log->line(i), style.mono), available);
  }
  const auto text = panel_text();
  EXPECT_NE(text.find("第3行·simulateevilline·第2次尝试·完成·任务01234567冻结快照fedcba98·2个文件"), std::string::npos) << text;
  EXPECT_NE(text.find("项目文件：输出🙂长"), std::string::npos) << text;
  ASSERT_TRUE(f.drv->key(wm::Key::Esc)); frame(); frame();
  EXPECT_EQ(panel(), nullptr);
  ASSERT_NE(id(entry()), 0u);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  EXPECT_EQ(f.screen.arrangement(), layout);
  EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer);
  expect_no_agent_actions();
}

TEST_F(NativeAgentRunDetailNarrowUI, NarrowChineseBottomSheetPreviewsAFileInFiveClicksAndEscReturnsToTheCard)
{
  const auto captured = produce();
  ASSERT_NO_FATAL_FAILURE(open_rail("workbench_history"));
  const auto layout = f.screen.arrangement();
  const auto viewer = f.shell->store().viewer().save_workspace_state();
  clicks = 0;
  ASSERT_NO_FATAL_FAILURE(open_narrow_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0")->text, "查看文件 · 第 3 行 · simulate evil line");
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_files/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview/0"));
  const auto *modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_EQ(modal->title(), "快照文件");
  EXPECT_FLOAT_EQ(modal->frame().x, 0.0f);  // the same full-width bottom sheet
  EXPECT_FLOAT_EQ(modal->frame().w, 680.0f);
  EXPECT_FLOAT_EQ(modal->frame().y1(), 1000.0f);
  EXPECT_FLOAT_EQ(modal->frame().h, 800.0f);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0")->text, "返回关联任务");
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "预览");
  EXPECT_TRUE(has_label("big · big.log · 307201 字节"));
  EXPECT_TRUE(has_label("超过 256 KiB"));
  ASSERT_NO_FATAL_FAILURE(click("ai_agent_run_detail_preview/0"));
  ASSERT_NO_FATAL_FAILURE(wait_for("ai_agent_run_detail_preview_text"));
  EXPECT_EQ(clicks, 5);  // history, session, linked tasks, view files, preview
  modal = panel(); ASSERT_NE(modal, nullptr);
  EXPECT_EQ(modal->title(), "文件预览");
  EXPECT_FLOAT_EQ(modal->frame().x, 0.0f);
  EXPECT_FLOAT_EQ(modal->frame().w, 680.0f);
  EXPECT_FLOAT_EQ(modal->frame().y1(), 1000.0f);
  EXPECT_FLOAT_EQ(modal->frame().h, 800.0f);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_preview/0")->text, "返回快照文件");
  const auto *log = f.screen.ui()->find("ai_agent_run_detail_preview_text");
  const auto &style = f.screen.ui()->style();
  const float available = log->rect.w - 2 * style.text_margin - style.scrollbar - 2 * style.pixel;
  for (size_t i = 0; i < log->log->line_count(); ++i) { EXPECT_LE(f.measurer.width(log->log->line(i), style.mono), available); }
  EXPECT_NE(preview_text().find("<script>alert(1)</script>"), std::string::npos) << preview_text();
  ASSERT_TRUE(f.drv->key(wm::Key::Esc)); frame(); frame();
  EXPECT_EQ(panel(), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), id(entry()));
  EXPECT_EQ(count("workflow_runs.get"), 1u);
  EXPECT_EQ(count("snapshots.get"), 1u);
  EXPECT_EQ(count("snapshots.resolve"), 1u);
  EXPECT_EQ(f.screen.arrangement(), layout);
  EXPECT_EQ(f.shell->store().viewer().save_workspace_state(), viewer);
  expect_no_saved_file_state(captured);
  expect_no_agent_actions();
}

/** An older bridge without project.snapshots.resolve: the linked tasks stay as before, without file entries. */
class NativeAgentRunFilesWithoutResolveUI : public NativeAgentRunDetailUI {
  const char *capability_marker() const override { return "no_snapshot_resolve"; }
};
TEST_F(NativeAgentRunFilesWithoutResolveUI, LinkedTasksShowNoFileEntriesAndReadNoSnapshot)
{
  produce();
  ASSERT_NO_FATAL_FAILURE(open_rail());
  ASSERT_NO_FATAL_FAILURE(open_session_a());
  ASSERT_NO_FATAL_FAILURE(click(entry()));
  ASSERT_NO_FATAL_FAILURE(wait_ready());
  EXPECT_NE(panel_text().find("Frozensnapshot"), std::string::npos);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/0"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("ai_agent_run_detail_files/1"), nullptr);
  EXPECT_EQ(count("snapshots.get"), 0u);
  EXPECT_EQ(count("snapshots.resolve"), 0u);
  expect_no_agent_actions();
}

class NativeAgentRunFilesWithoutGet : public NativeAgentRuns {
  const char *capability_marker() const override { return "no_snapshot_get"; }
};
TEST_F(NativeAgentRunFilesWithoutGet, ADetailCannotListFilesWithoutTheSnapshotRead)
{
  marker("consumed");
  produce();
  select();
  const auto card = consumed_item();
  const auto ticket = ready_detail(card);
  ASSERT_EQ(io::get_string(*agent().run_detail(ticket, card), "state"), "ready");
  EXPECT_FALSE(agent().can_read_run_files(ticket, card));
  EXPECT_FALSE(agent().read_run_files(ticket, card, 0));
  EXPECT_EQ(agent().run_files(ticket, card), nullptr);
  EXPECT_EQ(count("snapshots.get"), 0u);
  expect_no_agent_actions();
}

class NativeAgentRunsLegacy : public NativeAgentRuns { bool legacy() const override { return true; } };
TEST_F(NativeAgentRunsLegacy, MissingCapabilitiesKeepTheOldAssistantAndHidePreparationControls)
{
  EXPECT_TRUE(agent().supported()); EXPECT_FALSE(agent().runs_supported());
  open_ui();
  EXPECT_EQ(widget("ai_agent_allow_prepare"), nullptr);
  EXPECT_TRUE(agent().run_cards().empty());  // no card, so no linked-task entry or read
  EXPECT_FALSE(agent().ask("Unavailable preparation", Json()));
  EXPECT_EQ(count("run_target"), 0u);
  ASSERT_TRUE(agent().ask("Old assistant")); settle();
  EXPECT_EQ(count("create"), 1u); EXPECT_EQ(count("start"), 1u);
}
}  // namespace
}  // namespace stk::app
