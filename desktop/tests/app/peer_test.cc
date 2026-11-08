/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include <gtest/gtest-spi.h>
#include "stk/app/app_store.hh"
#include "stk/app/peer_state.hh"
#include "stk/core/sha256.hh"
#include "stk/app/project_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include "stk/app/editor.hh"
#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include <chrono>
#include <cstdlib>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>

namespace stk::app {
namespace {
using io::Json;
const std::string id = "00000000-0000-4000-8000-000000000001";

TEST(PeerState, SyncAndDetachNeverDispatchOrLoseOriginalIdentitiesAndOtherViews)
{
  AppStore store; auto &state = store.peers(); auto first = state.new_view(), second = state.new_view();
  first->operation_id = id; first->uncertain = true;
  first->originals[id] = {"files.send", std::string(64, 'a')};
  second->values["private-draft"] = {{"text", "keep"}};
  state.sync(first); state.sync(second); state.pump(first);
  EXPECT_FALSE(state.supported()); EXPECT_FALSE(state.read(first, "info"));
  EXPECT_FALSE(state.act(first, "identity.initialize", {{"display_name", "Device"}}));
  state.detach(first);
  EXPECT_EQ(first->operation_id, id); EXPECT_TRUE(first->uncertain);
  EXPECT_EQ(first->originals.at(id).action, "files.send");
  EXPECT_EQ(second->values.at("private-draft").at("text"), "keep");
  EXPECT_FALSE(state.read(first, "files.send"));
  EXPECT_FALSE(state.act(first, "model.endpoints.set", Json::object()));
}

TEST(PeerState, RequestHashMatchesPythonTypesNegativeZeroAndSignalDigest)
{
  EXPECT_EQ(PeerState::request_sha256("files.send", {{"operation_id", id}, {"timeout", -0.0}}),
            "bff1aa3ba62dfdff1f2dfa665faaacac63c8b6eceddeb968ec4887b85ea16dd2");
  EXPECT_EQ(PeerState::request_sha256("files.send", {{"timeout", 0}, {"operation_id", id}}),
            "a7f3d871ac99feade10f803c79ba40027fadc2215855c8aee4a0e4eba7dfe6a9");
  EXPECT_EQ(PeerState::request_sha256("connections.push_signal", {{"operation_id", id}, {"signal_text", "测试 signal"}}),
            "55071a8e0e2f5c77252b50804c213928230b81e97c872e1d62b7866dd43671d7");
  EXPECT_NE(PeerState::request_sha256("files.send", {{"operation_id", id}, {"timeout", 0.0}}),
            PeerState::request_sha256("files.send", {{"operation_id", id}, {"timeout", 0}}));
  EXPECT_THROW(PeerState::request_sha256("connections.push_signal", Json::object()), std::exception);
}

TEST(PeerState, OriginalActionAndFullRequestDigestBindReceiptWithoutGrantingPermission)
{
  PeerState::Expected expected{"files.send", std::string(64, 'a')};
  Json value = {{"operation_id", id}, {"action", "files.send"}, {"request_sha256", expected.request_sha256},
    {"state", "running"}, {"connection_id", id}, {"transfer_id", id}, {"result", nullptr}, {"error", nullptr}};
  EXPECT_TRUE(PeerState::operation_matches(value, id, &expected));
  for (const auto &bad : std::vector<Json>{{{"operation_id", PeerState::new_uuid()}}, {{"action", "files.recover"}},
       {{"request_sha256", std::string(64, 'b')}}, {{"state", "authorized"}}, {{"connection_id", "old-connection"}},
       {{"result", Json::array()}}, {{"error", {{"code", "unavailable"}}}}, {{"private_key", "not-allowed"}}}) {
    auto changed = value; changed.update(bad);
    EXPECT_FALSE(PeerState::operation_matches(changed, id, &expected));
  }
  AppStore store; auto &state = store.peers(); auto view = state.new_view();
  ASSERT_TRUE(state.select_operation(view, value));
  EXPECT_EQ(view->operation_id, id);
  EXPECT_FALSE(state.supported());
  EXPECT_FALSE(state.act(view, "files.send", {{"operation_id", id}}));
  auto recovery = value; recovery["action"] = "identity.recover";
  PeerState::Expected recovery_expected{"identity.recover", std::string(64, 'a')};
  EXPECT_TRUE(PeerState::operation_matches(recovery, id, &recovery_expected));
}

TEST(PeersEditor, WorkspaceKeepsOnlyBoundedPortableDraftsAndRejectsChangesAtomically)
{
  EditorRegistry registry; register_builtin_editors(registry);
  auto first = registry.create(kEditorPeers), second = registry.create(kEditorPeers);
  ASSERT_TRUE(first); ASSERT_TRUE(second); auto value = first->save_workspace_state();
  value["section"] = 2; value["source_project"] = id; value["source_revision"] = 1;
  value["drafts"]["display_name"] = "Public draft"; value["drafts"]["snapshot_id"] = id;
  value["drafts"]["record_ids"] = id; value["drafts"]["helper_prefix"] = "/explicit/installation";
  value["drafts"]["target"] = "/explicit/absent-target";
  ASSERT_TRUE(first->load_workspace_state(value)); ASSERT_TRUE(first->has_unsaved_changes());
  ASSERT_TRUE(second->load_workspace_state(first->save_workspace_state())); EXPECT_EQ(second->save_workspace_state(), value);
  for (const auto key : {"signal", "connection_id", "operation_id", "grant_id", "session_id", "remote_key", "remote_peer", "remote_owner", "plan"}) {
    EXPECT_FALSE(value.contains(key)); EXPECT_FALSE(value.at("drafts").contains(key));
    auto bad = value; bad["drafts"][key] = "not-portable";
    EXPECT_FALSE(second->load_workspace_state(bad)); EXPECT_EQ(second->save_workspace_state(), value);
  }
  for (const auto change : std::vector<Json>{{{"source_revision", true}}, {{"source_project", "wrong"}},
      {{"section", 4}}, {{"connection_id", id}}, {{"drafts", {{"display_name", "incomplete"}}}}}) {
    auto bad = value; bad.update(change); EXPECT_FALSE(second->load_workspace_state(bad)); EXPECT_EQ(second->save_workspace_state(), value);
  }
  auto bad = value; bad["drafts"]["display_name"] = std::string(4097, 'x');
  EXPECT_FALSE(second->load_workspace_state(bad)); EXPECT_EQ(second->save_workspace_state(), value);
  EXPECT_EQ(first->save_state(), (Json{{"version", 1}, {"section", 2}}));
}

// Real production Bridge/PeerService. The test controls only response delivery
// and public synthetic project setup; it never substitutes the owner service.
constexpr const char *kPeerBridge = R"PY(
from pathlib import Path
import json
import os
import sys
import threading
import time
from uuid import uuid4
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.peer import PeerService
from suan.desktop_bridge.projects import ProjectSessions
from suan.desktop_bridge.__main__ import main
from suan.project.store import ProjectStore
control = Path(sys.argv.pop(1))
def publish(path, text):
    # Write-then-replace: a JSON fixture file that exists already holds its complete text.
    pending = path.with_name(path.name + '.tmp')
    pending.write_text(text, encoding='utf-8'); pending.replace(path)
seeds = []
for label in ('first', 'second'):
    project = ProjectStore.create(control.parent / label, 'Public synthetic peer source')
    (project.directory / 'selected.bin').write_bytes(label.encode())
    (project.directory / 'another.bin').write_bytes(b'other public synthetic bytes')
    records = project.files.index([str(project.directory / 'selected.bin'), str(project.directory / 'another.bin')], expected_revision=0)['record_ids']
    snapshot = project.snapshots.capture(records, expected_revision=1)['snapshot']
    seeds.append({'path':str(project.directory), 'snapshot_id':snapshot['id'], 'record_ids':records})
publish(control.with_suffix('.seed.json'), json.dumps(seeds))
lock = threading.Lock()
counts = {}
draw_results = {}
call = PeerService.call
def counted(self, action, params):
    with lock, control.with_suffix('.calls').open('a') as out:
        out.write(action + '\n')
        counts[action] = counts.get(action, 0) + 1
        index = counts[action]
    if action in {'files.offer', 'files.send'}:
        target = control.with_suffix('.' + action.split('.')[1] + '_request_' + str(index) + '.json')
        pending = target.with_suffix('.tmp')
        pending.write_text(json.dumps(params), encoding='utf-8'); pending.replace(target)
    return call(self, action, params)
PeerService.call = counted
send = Bridge.send
def controlled(self, message, method=None):
    # Synthetic public DTO draw fixture only: it proves UI parsing/explicit
    # dispatch, never device authentication, a host grant, or a real connection.
    if control.with_suffix('.draw_host').exists() and 'result' in message:
        import hashlib
        if method == 'peer.connections.list':
            message['result'] = {'connections':[{'connection_id':'00000000-0000-4000-8000-000000000009',
                'peer_id':'a'*64, 'state':'ready', 'error':None}]}
        if method == 'peer.sessions.host':
            op = message['result']['operation']
            remote = {'format':'stk.peer-device/1', 'owner_id':'00000000-0000-4000-8000-000000000008',
                'peer_id':hashlib.sha256(bytes.fromhex('11'*32)).hexdigest(), 'public_key':'11'*32, 'display_name':'Synthetic draw recipient'}
            hosted = {'format':'stk.peer-sharing-session/1', 'session_id':'00000000-0000-4000-8000-000000000007',
                'session_epoch':1, 'host':self.peers.identity.info()['card'], 'recipient':remote, 'expires_at':time.time()+600}
            op.update(state='completed', error=None, result={'format':'stk.peer-pairing-operation/1',
                'operation_id':op['operation_id'], 'kind':'host_session', 'request_sha256':'c'*64,
                'result':{'offer':hosted, 'role':'host'}})
        if method == 'peer.files.query':
            op = message['result']['operation']
            op.update(state='completed', error=None, result={'session_id':'00000000-0000-4000-8000-000000000007',
                'transfer_id':op['transfer_id'], 'manifest_sha256':'a'*64, 'state':'accepted',
                'grant_id':op['operation_id'],
                'files':[{'file_id':'00000000-0000-4000-8000-000000000004', 'bytes':1, 'committed_bytes':0,
                          'next_sequence':0, 'verified_sha256':None}],
                'operation':None, 'completion':None})
        if method in {'peer.sessions.host', 'peer.files.query'}:
            suffix = 'host' if method == 'peer.sessions.host' else 'query'
            op = message['result']['operation']
            if control.with_suffix('.uncertain_' + suffix).exists():
                op.update(state='uncertain', result=None, error=None)
            draw_results[op['operation_id']] = json.loads(json.dumps(op))
            publish(control.with_suffix('.' + suffix + '_operation.json'), json.dumps(op))
        if method == 'peer.operations.get' and message['result']['operation'] is not None:
            original = message['result']['operation']['operation_id']
            if original in draw_results:
                message['result']['operation'] = json.loads(json.dumps(draw_results[original]))
        if method == 'peer.operations.list':
            message['result']['operations'] = [json.loads(json.dumps(draw_results.get(op['operation_id'],op)))
                                               for op in message['result']['operations']]
    suffix = {'peer.info':'info', 'peer.identity.initialize':'initialize',
              'project.peer.files.prepare':'prepare', 'project.snapshots.get':'snapshot'}.get(method)
    if suffix and 'result' in message and control.with_suffix('.hold_' + suffix).exists():
        control.with_suffix('.' + suffix + '_held').write_text('held')
        until = time.monotonic() + 25
        while not control.with_suffix('.' + suffix + '_release').exists() and time.monotonic() < until:
            time.sleep(.005)
    if method == 'peer.identity.initialize' and 'result' in message and control.with_suffix('.wrong_hash').exists():
        message['result']['operation']['request_sha256'] = 'b' * 64
    send(self, message, method)
    if suffix and 'result' in message:
        control.with_suffix('.' + suffix + '_sent').write_text('sent')
Bridge.send = controlled

# Optional installed-helper acceptance fixture. Connection setup and the
# recipient's explicit consent use the production public service API. Every
# sender receipt, query and DATA transfer remains real; no DTO draw marker is set.
initialize_bridge = Bridge.__init__
shutdown_bridge = Bridge.shutdown
def native_initialize(self, *args, **kwargs):
    initialize_bridge(self, *args, **kwargs)
    prefix = os.environ.get('STK_TEST_PEER_INSTALLATION')
    if not prefix:
        return
    remote_projects = ProjectSessions(control.parent / 'remote-project-state')
    remote = PeerService(control.parent / 'receiving-device', remote_projects)
    self._test_native_remote = remote
    self._test_native_projects = remote_projects
    receiving = os.environ.get('STK_TEST_PEER_ROLE') == 'receiver'
    services = [self.peers, remote]
    def uid(): return str(uuid4())
    for i, service in enumerate(services):
        assert service.call('identity.initialize', {'operation_id':uid(), 'display_name':'Public native device '+str(i)})['operation']['state'] == 'completed'
    cards = [service.call('info', {})['identity']['card'] for service in services]
    connections, authentication = [], []
    for i, service in enumerate(services):
        card = cards[1-i]
        assert service.call('pins.verify', {'operation_id':uid(), 'card':card, 'expected_peer_id':card['peer_id']})['operation']['state'] == 'completed'
        opened = service.call('connections.open', {'operation_id':uid(), 'peer_id':card['peer_id'],
                              'helper_prefix':prefix, 'offerer':i == 0, 'route':'udp'})['operation']
        assert opened['state'] == 'completed'
        connections.append(opened['result']['connection_id'])
    for service, connection in zip(services, connections):
        operation = uid(); authentication.append(operation)
        assert service.call('connections.authenticate', {'operation_id':operation, 'connection_id':connection})['operation']['state'] == 'running'
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        for i, service in enumerate(services):
            signal = service.call('connections.signals', {'connection_id':connections[i]})['signal_text']
            if signal is not None:
                assert services[1-i].call('connections.push_signal', {'operation_id':uid(),
                    'connection_id':connections[1-i], 'signal_text':signal})['operation']['state'] == 'completed'
        states = [service.call('operations.get', {'operation_id':operation})['operation']['state']
                  for service, operation in zip(services, authentication)]
        if all(state == 'completed' for state in states): break
        assert all(state in {'running','completed'} for state in states)
        time.sleep(.01)
    else:
        raise RuntimeError('Installed helper authentication did not finish')
    metadata = {'connection_id':connections[0]}
    if receiving:
        source = ProjectStore(seeds[0]['path'])
        handle = remote_projects.open({'directory':str(source.directory)})['project']['handle']
        hosted = remote.call('sessions.host', {'operation_id':uid(), 'connection_id':connections[1],
            'lifetime':300, 'session_id':None})['operation']
        assert hosted['state'] == 'completed'
        session = hosted['result']['result']['offer']
        prepared = remote.call('files.prepare', {'operation_id':uid(), 'handle':handle,
            'expected_revision':source.info()['revision'], 'snapshot_id':seeds[0]['snapshot_id'],
            'record_ids':seeds[0]['record_ids']})['operation']
        assert prepared['state'] == 'completed'
        plan = prepared['result']
        offered = remote.call('files.offer', {'operation_id':uid(), 'connection_id':connections[1],
            'plan_id':plan['plan_id'], 'database_generation':plan['database_generation'],
            'session_id':session['session_id'], 'transfer_id':None})['operation']
        assert offered['state'] == 'completed'
        metadata['transfer_id'] = offered['result']['transfer_id']
    publish(control.with_suffix('.native.json'), json.dumps(metadata))
    self._test_native_stop = threading.Event()
    def recipient():
        try:
            while not self._test_native_stop.wait(.01):
                if receiving:
                    if not control.with_suffix('.start_sender').exists(): continue
                    transfer = metadata['transfer_id']
                    queried = remote.call('files.query', {'operation_id':uid(), 'connection_id':connections[1],
                        'transfer_id':transfer, 'original_operation_id':None})['operation']
                    assert queried['state'] == 'completed' and queried['result']['state'] == 'accepted'
                    operation = uid()
                    admitted = remote.call('files.send', {'operation_id':operation, 'connection_id':connections[1],
                        'transfer_id':transfer, 'grant_id':queried['result']['grant_id'], 'resume':False, 'timeout':60})['operation']
                    assert admitted['state'] == 'running'
                    deadline = time.monotonic() + 60
                    while not self._test_native_stop.wait(.01) and time.monotonic() < deadline:
                        finished = remote.call('operations.get', {'operation_id':operation})['operation']
                        if finished['state'] != 'running': break
                    assert finished['state'] == 'completed' and finished['result']['state'] == 'complete'
                    pending = control.with_suffix('.native_complete.tmp')
                    pending.write_text(json.dumps(finished)); pending.replace(control.with_suffix('.native_complete.json'))
                    return
                if not control.with_suffix('.approve_receiver').exists(): continue
                transfers = remote.call('files.list', {'role':'receiver'})['transfers']
                if not transfers: continue
                assert len(transfers) == 1
                transfer = transfers[0]['transfer_id']
                reviewed = remote.call('files.get', {'role':'receiver', 'transfer_id':transfer})
                assert len(reviewed['manifest']['files']) == 2
                target = control.parent / 'received'
                assert not target.exists()
                accepted = remote.call('files.accept', {'operation_id':uid(), 'connection_id':connections[1],
                    'transfer_id':transfer, 'offer_operation_id':reviewed['offer']['offer_operation_id'], 'target':str(target)})['operation']
                assert accepted['state'] == 'completed'
                pending = control.with_suffix('.native_accept.tmp')
                pending.write_text(json.dumps({'transfer_id':transfer})); pending.replace(control.with_suffix('.native_accept.json'))
                return
        except Exception as error:
            control.with_suffix('.native_error').write_text(type(error).__name__)
    self._test_native_thread = threading.Thread(target=recipient, daemon=True)
    self._test_native_thread.start()

def native_shutdown(self):
    stop = getattr(self, '_test_native_stop', None)
    if stop is not None: stop.set()
    try:
        shutdown_bridge(self)
    finally:
        remote = getattr(self, '_test_native_remote', None)
        if remote is not None: remote.shutdown()
        thread = getattr(self, '_test_native_thread', None)
        if thread is not None: thread.join(5)
        projects = getattr(self, '_test_native_projects', None)
        if projects is not None: projects.shutdown()
Bridge.__init__ = native_initialize
Bridge.shutdown = native_shutdown

native_send = Bridge.send
def native_receipts(self, message, method=None):
    operation = message.get('result', {}).get('operation') if isinstance(message.get('result'), dict) else None
    if os.environ.get('STK_TEST_PEER_INSTALLATION') and isinstance(operation, dict) and operation.get('state') == 'completed':
        suffix = {'files.offer':'native_offer', 'files.send':'native_complete', 'files.accept':'native_accept'}.get(operation.get('action'))
        if suffix:
            pending = control.with_suffix('.' + suffix + '.tmp')
            pending.write_text(json.dumps(operation)); pending.replace(control.with_suffix('.' + suffix + '.json'))
    if os.environ.get('STK_TEST_PEER_ROLE') == 'receiver' and method == 'peer.files.get' and 'result' in message:
        transfer = message['result']['transfer']
        pending = control.with_suffix('.native_details.tmp')
        pending.write_text(json.dumps({'state':transfer['state'], 'transfer_id':transfer['transfer_id']}))
        pending.replace(control.with_suffix('.native_details.json'))
    native_send(self, message, method)
Bridge.send = native_receipts
main()
)PY";

class PeerBridge : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"peer-controller"}; bridge::test::ManualLoop loop;
  wmtest::AppFixture fixture{"en", 1, 1440, 1200}; AppStore &store = fixture.shell->store();
  std::unique_ptr<bridge::Client> client; Json seeds;
  virtual bool native_helpers() const { return false; }
  virtual const char *native_role() const { return "sender"; }
  PeerState &state() { return store.peers(); }
  void marker(const std::string &name) { std::ofstream out(dir.path() / ("control." + name)); out << "marker"; }
  void wait_marker(const std::string &name)
  {
    ASSERT_TRUE(loop.pump_until([&] { return std::filesystem::exists(dir.path() / ("control." + name)); }));
  }
  // JSON fixture files are published by the bridge script with write-then-replace (publish()), so a
  // name that exists already holds its complete text. A stream that failed to open or read nothing must
  // not reach the parser: nlohmann reports it as "attempting to parse an empty input".
  enum class Published { Missing, Unreadable, Empty, Invalid, Complete };
  struct Reading { Published kind = Published::Missing; Json value; std::string cause = "not read"; };
  /** One attempt; the cause names a state only, never file content or a path. */
  static Reading read_published(const std::filesystem::path &path)
  {
    std::error_code error;
    const auto status = std::filesystem::status(path, error);
    if (status.type() == std::filesystem::file_type::not_found) { return {Published::Missing, {}, "not published"}; }
    if (error) { return {Published::Unreadable, {}, "status unavailable"}; }
    if (status.type() != std::filesystem::file_type::regular) { return {Published::Unreadable, {}, "not a regular file"}; }
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) { return {Published::Unreadable, {}, "published but could not be opened"}; }
    std::string text;
    try {  // A filebuf read error can throw (libstdc++ underflow) instead of setting a stream flag.
      text.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
    }
    catch (const std::exception &) { return {Published::Unreadable, {}, "published but the read failed"}; }
    if (in.bad()) { return {Published::Unreadable, {}, "published but the read failed"}; }
    if (text.empty()) { return {Published::Empty, {}, "published but empty"}; }
    Json value = Json::parse(text, nullptr, false);
    if (value.is_discarded()) { return {Published::Invalid, {}, "not valid JSON (" + std::to_string(text.size()) + " bytes)"}; }
    return {Published::Complete, std::move(value), "complete"};
  }
  /** Waits within the usual budget until control.<name> is complete JSON and adopts it. A missing,
   * unopenable or empty file is retried; non-empty invalid content cannot become valid under
   * write-then-replace, so it fails at once. Every failure names the file and its last state. */
  bool published(const std::string &name, Json &out, double timeout_s = 30.0,
                 const std::function<void(const Reading &)> &observed = {})
  {
    const auto path = dir.path() / ("control." + name);
    Reading last;
    const bool settled = loop.pump_until([&] {
      last = read_published(path);
      if (observed) { observed(last); }
      return last.kind == Published::Complete || last.kind == Published::Invalid;
    }, timeout_s);
    if (settled && last.kind == Published::Complete) { out = std::move(last.value); return true; }
    ADD_FAILURE() << "fixture file control." << name
                  << (settled ? " is permanently bad: " : " was not complete before the deadline; last state: ") << last.cause;
    return false;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *p = std::getenv("STK_BRIDGE_TEST_PYTHON"); p && *p) { python = p; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    ASSERT_FALSE(python.empty());
    { std::ofstream out(dir.path() / "bridge.py"); out << kPeerBridge; ASSERT_TRUE(out.good()); }
    bridge::ClientOptions options; options.executor = loop.executor(); options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = dir.str() + "/state";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.env["STK_TEST_PEER_INSTALLATION"] = std::nullopt;
    options.env["STK_TEST_PEER_ROLE"] = std::nullopt;
    if (native_helpers()) {
      const char *prefix = std::getenv("STK_TEST_PEER_INSTALLATION");
      ASSERT_TRUE(prefix && *prefix) << "An explicit installed helper prefix is required";
      options.env["STK_TEST_PEER_INSTALLATION"] = prefix;
      options.env["STK_TEST_PEER_ROLE"] = native_role();
    }
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/control", "--stdio", "--state-dir", options.state_dir,
      "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store.set_bridge(client.get());
    ASSERT_TRUE(published("seed.json", seeds));
    ASSERT_EQ(seeds.size(), 2u);
  }
  void TearDown() override
  {
    for (const auto suffix : {"info", "initialize", "prepare", "snapshot"}) { marker(std::string(suffix) + "_release"); }
    store.set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  int calls(const std::string &action)
  {
    std::ifstream in(dir.path() / "control.calls"); std::string line; int count = 0;
    while (std::getline(in, line)) { count += line == action; } return count;
  }
  void settle(const PeerState::ViewPtr &view)
  {
    ASSERT_TRUE(loop.pump_until([&] { state().sync(view); return !view->reading(); }));
    ASSERT_TRUE(view->error.empty()) << view->error;
  }
  void open_source(const int index)
  {
    store.project().sync();
    ASSERT_TRUE(store.project().open(seeds.at(index).at("path").get<std::string>()));
    ASSERT_TRUE(loop.pump_until([&] { store.project().sync(); return store.project().ready() && store.project().loaded() && !store.project().busy(); }));
  }
  Json prepare(const PeerState::ViewPtr &view, int index)
  {
    if (calls("identity.initialize") == 0) {
      EXPECT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Public source fixture"}})); settle(view);
    }
    EXPECT_TRUE(state().act(view, "files.prepare", {{"snapshot_id", seeds.at(index).at("snapshot_id")},
                                                     {"record_ids", seeds.at(index).at("record_ids")}}));
    settle(view); return view->operation;
  }
};

TEST_F(PeerBridge, ActualIdentityRecoveryUsesNewExplicitOperationWithoutReplayingInitialization)
{
  auto view = state().new_view(); state().sync(view); ASSERT_TRUE(state().supported());
  state().sync(view); state().pump(view);
  EXPECT_EQ(calls("info"), 0); EXPECT_EQ(calls("identity.initialize"), 0);
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Public controller test"}})); settle(view);
  ASSERT_EQ(io::get_string(view->operation, "state"), "completed"); const auto original = view->operation_id;
  ASSERT_TRUE(state().act(view, "identity.recover", {{"original_operation_id", original}})); settle(view);
  EXPECT_EQ(io::get_string(view->operation, "action"), "identity.recover");
  EXPECT_EQ(io::get_string(view->operation, "state"), "completed");
  EXPECT_EQ(view->operation.at("result").at("original_operation_id"), original);
  EXPECT_EQ(calls("identity.initialize"), 1); EXPECT_EQ(calls("identity.recover"), 1);
  EXPECT_FALSE(state().act(view, "identity.initialize", {{"operation_id", original}, {"display_name", "Public controller test"}}));
  EXPECT_EQ(calls("identity.initialize"), 1);
}

TEST_F(PeerBridge, HistoricalPreparationCannotBorrowLaterProjectOriginOrSourceSelection)
{
  auto view = state().new_view(); state().sync(view); open_source(0);
  const auto first = prepare(view, 0); ASSERT_EQ(io::get_string(first, "state"), "completed");
  const auto old_plan = view->values.at("files.prepare"); ASSERT_TRUE(state().source_current(view));
  state().invalidate_draft(view); EXPECT_TRUE(state().source_current(view)); // Other form input is independent.
  ASSERT_TRUE(state().set_connection(view, PeerState::new_uuid())); EXPECT_TRUE(state().source_current(view));
  open_source(1); state().sync(view); EXPECT_FALSE(state().source_current(view));
  const auto second = prepare(view, 1); const auto current_plan = view->values.at("files.prepare");
  ASSERT_NE(current_plan, old_plan); ASSERT_TRUE(state().source_current(view));
  ASSERT_TRUE(state().select_operation(view, first)); ASSERT_TRUE(state().check_operation(view)); settle(view);
  EXPECT_EQ(view->values.at("files.prepare"), current_plan); EXPECT_TRUE(state().source_current(view));
  state().invalidate_draft(view, true); EXPECT_FALSE(state().source_current(view)); EXPECT_FALSE(view->values.contains("files.prepare"));
  ASSERT_TRUE(state().select_operation(view, second)); ASSERT_TRUE(state().check_operation(view)); settle(view);
  EXPECT_FALSE(view->values.contains("files.prepare")); EXPECT_FALSE(state().source_current(view));
}

TEST_F(PeerBridge, NewPreparationClearsOldPlanAndRejectsReplyAfterChangedSourceSelection)
{
  auto view = state().new_view(); state().sync(view); open_source(0); prepare(view, 0);
  ASSERT_TRUE(state().source_current(view)); marker("hold_prepare");
  ASSERT_TRUE(state().act(view, "files.prepare", {{"snapshot_id", seeds.at(0).at("snapshot_id")}, {"record_ids", seeds.at(0).at("record_ids")}}));
  EXPECT_FALSE(view->values.contains("files.prepare")); EXPECT_FALSE(state().source_current(view)); wait_marker("prepare_held");
  const auto original = view->operation_id; state().invalidate_draft(view, true); marker("prepare_release");
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); })); EXPECT_TRUE(view->uncertain);
  ASSERT_TRUE(state().check_operation(view)); settle(view); EXPECT_EQ(view->operation_id, original);
  EXPECT_EQ(io::get_string(view->operation, "state"), "completed");
  EXPECT_FALSE(view->values.contains("files.prepare")); EXPECT_FALSE(state().source_current(view));
}

TEST_F(PeerBridge, OtherFormDraftEditsDoNotInvalidateFrozenPreparationResponse)
{
  auto view = state().new_view(); state().sync(view); open_source(0);
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Independent form drafts"}})); settle(view);
  marker("hold_prepare");
  ASSERT_TRUE(state().act(view, "files.prepare", {{"snapshot_id", seeds.at(0).at("snapshot_id")}, {"record_ids", seeds.at(0).at("record_ids")}}));
  wait_marker("prepare_held"); state().invalidate_draft(view); marker("prepare_release"); settle(view);
  EXPECT_EQ(io::get_string(view->operation, "state"), "completed"); EXPECT_TRUE(state().source_current(view));
}

TEST_F(PeerBridge, ExplicitSnapshotReadsUseCurrentSourceAndRejectDelayedSelection)
{
  auto view = state().new_view(); state().sync(view); open_source(0);
  EXPECT_FALSE(state().read_source(view, "project.snapshots.capture", Json::object()));
  EXPECT_FALSE(state().read_source(view, "project.snapshots.get", Json::object()));
  ASSERT_TRUE(state().read_source(view, "project.snapshots.list_summaries", {{"limit", 64}})); settle(view);
  ASSERT_EQ(view->values.at("snapshots").at("total"), 1);
  ASSERT_TRUE(state().read_source(view, "project.snapshots.get", {{"snapshot_id", seeds.at(0).at("snapshot_id")}})); settle(view);
  EXPECT_EQ(view->values.at("snapshot").at("snapshot").at("id"), seeds.at(0).at("snapshot_id"));
  state().invalidate_draft(view, true);
  EXPECT_TRUE(view->values.contains("snapshot")); // Checking another file retains the immutable selection page.
  view->values.erase("snapshot"); marker("hold_snapshot");
  ASSERT_TRUE(state().read_source(view, "project.snapshots.get", {{"snapshot_id", seeds.at(0).at("snapshot_id")}})); wait_marker("snapshot_held");
  state().invalidate_draft(view, true); marker("snapshot_release");
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); })); EXPECT_FALSE(view->values.contains("snapshot"));
}

TEST_F(PeerBridge, DetachBridgeEpochAndWrongOriginalHashKeepUnknownIdentityWithoutReissue)
{
  auto view = state().new_view(); state().sync(view); marker("hold_initialize");
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Retained original"}})); wait_marker("initialize_held");
  const auto original = view->operation_id;
  state().detach(view); marker("initialize_release"); wait_marker("initialize_sent"); loop.run_ready();
  EXPECT_TRUE(view->uncertain); EXPECT_EQ(view->operation_id, original); EXPECT_TRUE(view->originals.contains(original));
  EXPECT_FALSE(view->values.contains("identity.initialize")); EXPECT_EQ(calls("identity.initialize"), 1);
  store.set_bridge(nullptr); state().sync(view); store.set_bridge(client.get()); state().sync(view);
  ASSERT_TRUE(state().check_operation(view)); settle(view); EXPECT_EQ(io::get_string(view->operation, "state"), "completed");
  EXPECT_FALSE(view->values.contains("identity.initialize")); EXPECT_EQ(calls("identity.initialize"), 1);
}

TEST_F(PeerBridge, WrongOriginalHashIsRejectedAndConnectionChangeDropsOnlyConnectionResults)
{
  auto view = state().new_view(); state().sync(view); marker("wrong_hash");
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Wrong hash response"}}));
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  EXPECT_EQ(view->error, "peer.invalid_response"); EXPECT_TRUE(view->uncertain); EXPECT_EQ(calls("identity.initialize"), 1);
  EXPECT_FALSE(view->values.contains("identity.initialize"));
  for (const auto key : {"connections.signals", "sessions.host", "files.offer", "files.query", "files.accept"}) {
    view->values[key] = Json::object();
  }
  view->values["files.prepare"] = {{"plan_id", id}}; view->values["private-draft"] = {{"text", "keep"}};
  ASSERT_TRUE(state().set_connection(view, PeerState::new_uuid()));
  for (const auto key : {"connections.signals", "sessions.host", "files.offer", "files.query", "files.accept"}) {
    EXPECT_FALSE(view->values.contains(key));
  }
  EXPECT_TRUE(view->values.contains("files.prepare")); EXPECT_EQ(view->values.at("private-draft").at("text"), "keep");
}

TEST_F(PeerBridge, HistoricalConnectionResultsStayObservationsAfterDraftOrConnectionChanges)
{
  auto view = state().new_view(); state().sync(view); marker("draw_host");
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "History origin fixture"}})); settle(view);
  const std::string connection = "00000000-0000-4000-8000-000000000009";
  ASSERT_TRUE(state().set_connection(view, connection));
  ASSERT_TRUE(state().act(view, "sessions.host", {{"connection_id", connection}, {"lifetime", 600}, {"session_id", nullptr}})); settle(view);
  ASSERT_TRUE(view->values.contains("sessions.host"));
  state().invalidate_draft(view); view->values.erase("sessions.host");
  ASSERT_TRUE(state().check_operation(view)); settle(view);
  EXPECT_EQ(io::get_string(view->operation, "state"), "completed");
  EXPECT_FALSE(view->values.contains("sessions.host"));
  ASSERT_TRUE(state().act(view, "sessions.host", {{"connection_id", connection}, {"lifetime", 600}, {"session_id", nullptr}})); settle(view);
  ASSERT_TRUE(view->values.contains("sessions.host")); const auto original = view->operation;
  ASSERT_TRUE(state().set_connection(view, PeerState::new_uuid()));
  ASSERT_TRUE(state().set_connection(view, connection)); // Same ID does not restore the previous connection generation.
  ASSERT_TRUE(state().select_operation(view, original)); ASSERT_TRUE(state().check_operation(view)); settle(view);
  EXPECT_FALSE(view->values.contains("sessions.host"));
}

TEST_F(PeerBridge, OlderHostAndQueryReceiptsCannotReplaceNewerSameActionResultWithoutAnyDraftEdit)
{
  auto view = state().new_view(); state().sync(view); marker("draw_host");
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Repeated action fixture"}})); settle(view);
  const std::string connection = "00000000-0000-4000-8000-000000000009";
  ASSERT_TRUE(state().set_connection(view, connection));
  for (const auto &[action, params] : std::vector<std::pair<std::string, Json>>{
      {"sessions.host", {{"connection_id", connection}, {"lifetime", 600}, {"session_id", nullptr}}},
      {"files.query", {{"connection_id", connection}, {"transfer_id", id}, {"original_operation_id", nullptr}}}}) {
    SCOPED_TRACE(action);
    const auto draft = view->draft_epoch, selected = view->connection_epoch;
    ASSERT_TRUE(state().act(view, action, params)); settle(view); const auto first = view->operation;
    ASSERT_TRUE(view->values.contains(action)); const auto old_result = view->values.at(action);
    ASSERT_TRUE(state().act(view, action, params)); settle(view);
    ASSERT_TRUE(view->values.contains(action)); const auto newest = view->values.at(action);
    ASSERT_NE(newest, old_result); EXPECT_EQ(view->draft_epoch, draft); EXPECT_EQ(view->connection_epoch, selected);
    ASSERT_TRUE(state().select_operation(view, first)); ASSERT_TRUE(state().check_operation(view)); settle(view);
    EXPECT_EQ(view->operation, first); // The historical observation remains readable.
    EXPECT_TRUE(view->values.at(action) == newest) << "History replaced a newer current result";
  }
}

TEST_F(PeerBridge, NewUncertainHostAndQueryClearPriorSuccessWhileLocallyRejectedActionsKeepIt)
{
  auto view = state().new_view(); state().sync(view); marker("draw_host");
  ASSERT_TRUE(state().act(view, "identity.initialize", {{"display_name", "Uncertain newer action fixture"}})); settle(view);
  const std::string connection = "00000000-0000-4000-8000-000000000009";
  ASSERT_TRUE(state().set_connection(view, connection));
  for (const auto &[action, params] : std::vector<std::pair<std::string, Json>>{
      {"sessions.host", {{"connection_id", connection}, {"lifetime", 600}, {"session_id", nullptr}}},
      {"files.query", {{"connection_id", connection}, {"transfer_id", id}, {"original_operation_id", nullptr}}}}) {
    SCOPED_TRACE(action);
    ASSERT_TRUE(state().act(view, action, params)); settle(view); const auto first = view->operation;
    ASSERT_TRUE(view->values.contains(action)); const auto result = view->values.at(action);
    auto duplicate = params; duplicate["operation_id"] = view->operation_id; const auto count = calls(action);
    EXPECT_FALSE(state().act(view, action, duplicate)); EXPECT_EQ(calls(action), count);
    EXPECT_TRUE(view->values.at(action) == result); EXPECT_EQ(view->operation, first);
    const auto suffix = action == "sessions.host" ? "uncertain_host" : "uncertain_query"; marker(suffix);
    ASSERT_TRUE(state().act(view, action, params));
    EXPECT_FALSE(view->values.contains(action)); // Cleared at admission, before the response arrives.
    settle(view); ASSERT_EQ(io::get_string(view->operation, "state"), "uncertain");
    EXPECT_FALSE(view->values.contains(action));
    EXPECT_FALSE(state().act(view, action, duplicate)); EXPECT_EQ(calls(action), count + 1);
    ASSERT_TRUE(state().select_operation(view, first)); ASSERT_TRUE(state().check_operation(view)); settle(view);
    EXPECT_EQ(view->operation, first); EXPECT_FALSE(view->values.contains(action));
    std::filesystem::remove(dir.path() / (std::string("control.") + suffix));
  }
}

TEST_F(PeerBridge, FixtureJsonIsAdoptedOnlyWhenCompleteAndPermanentlyBadContentFailsAtOnceWithItsCause)
{
  const auto path = dir.path() / "control.probe.json";
  const std::string complete = R"({"session_id":"00000000-0000-4000-8000-000000000007"})";
  const auto expected = Json::parse(complete);
  const auto publish = [&](const std::string &text) {  // The bridge script's write-then-replace, in C++.
    const auto pending = dir.path() / "control.probe.json.tmp";
    { std::ofstream out(pending, std::ios::binary); out << text; ASSERT_TRUE(out.good()); }
    std::filesystem::rename(pending, path);
  };
  // The pre-fix reader parsed an unchecked stream: a file that could not be opened (here: missing) and an
  // empty file both become nlohmann's "attempting to parse an empty input", the message of the CI failure.
  // (A directory is platform-specific: libstdc++ opens it and its read throws a non-JSON ios_failure.)
  const std::vector<std::pair<std::string, std::function<void()>>> unreadable{
      {"not opened", [] {}}, {"empty", [&] { std::ofstream(path).close(); }}};
  for (const auto &[label, make] : unreadable) {
    SCOPED_TRACE(label); make();
    try {
      std::ifstream in(path); Json value; in >> value; ADD_FAILURE() << "an unreadable file parsed";
    }
    catch (const Json::parse_error &error) {
      EXPECT_EQ(error.id, 101); EXPECT_NE(std::string(error.what()).find("empty input"), std::string::npos);
    }
  }
  std::filesystem::remove(path);
  // One attempt distinguishes every state.
  EXPECT_EQ(read_published(path).kind, Published::Missing);
  std::filesystem::create_directory(path); EXPECT_EQ(read_published(path).kind, Published::Unreadable);
  std::filesystem::remove(path);
  ASSERT_NO_FATAL_FAILURE(publish("")); EXPECT_EQ(read_published(path).kind, Published::Empty);
  ASSERT_NO_FATAL_FAILURE(publish(complete.substr(0, 30)));
  auto partial = read_published(path); EXPECT_EQ(partial.kind, Published::Invalid);
  EXPECT_EQ(partial.cause, "not valid JSON (30 bytes)"); // A state and a size, never the content.
  ASSERT_NO_FATAL_FAILURE(publish(complete));
  auto whole = read_published(path); EXPECT_EQ(whole.kind, Published::Complete); EXPECT_EQ(whole.value, expected);
  // While it waits, an unreadable or empty file is never adopted; the complete text published later is.
  for (const auto &[label, make] : std::vector<std::pair<std::string, std::function<void()>>>{
           {"unreadable", [&] { std::filesystem::create_directory(path); }}, {"empty", [&] { publish(""); }}}) {
    SCOPED_TRACE(label); std::filesystem::remove(path); make();
    std::vector<Published> seen; Json value = Json::object();
    EXPECT_TRUE(published("probe.json", value, 5.0, [&](const Reading &reading) {
      seen.push_back(reading.kind);
      if (seen.size() == 2) { std::filesystem::remove(path); publish(complete); }
    }));
    ASSERT_EQ(seen.size(), 3u); EXPECT_NE(seen.at(0), Published::Complete); EXPECT_EQ(seen.at(0), seen.at(1));
    EXPECT_EQ(seen.at(2), Published::Complete); EXPECT_EQ(value, expected);
  }
  // Permanently bad content fails at once with its cause; nothing is adopted and the wait is not spent.
  ASSERT_NO_FATAL_FAILURE(publish(complete.substr(0, 30)));
  Json kept = Json::object(); bool ok = true; const auto started = std::chrono::steady_clock::now();
  EXPECT_NONFATAL_FAILURE(ok = published("probe.json", kept, 5.0),
                          "fixture file control.probe.json is permanently bad: not valid JSON (30 bytes)");
  EXPECT_FALSE(ok); EXPECT_EQ(kept, Json::object());
  EXPECT_LT(std::chrono::steady_clock::now() - started, std::chrono::seconds(2));
  // A file never published, or still empty or unreadable at the deadline, fails with its last state.
  EXPECT_NONFATAL_FAILURE(ok = published("absent.json", kept, 0.2),
                          "fixture file control.absent.json was not complete before the deadline; last state: not published");
  EXPECT_FALSE(ok);
  ASSERT_NO_FATAL_FAILURE(publish(""));
  EXPECT_NONFATAL_FAILURE(ok = published("probe.json", kept, 0.2), "last state: published but empty");
  EXPECT_FALSE(ok);
  std::filesystem::remove(path); std::filesystem::create_directory(path);
  EXPECT_NONFATAL_FAILURE(ok = published("probe.json", kept, 0.2), "last state: not a regular file");
  EXPECT_FALSE(ok); EXPECT_EQ(kept, Json::object()); std::filesystem::remove(path);
}

class PeerMouse : public PeerBridge {
 protected:
  int clicks = 0, wheels = 0;
  Json held_viewer, held_hidden;
  std::shared_ptr<io::Payload> held_payload;
  uint64_t held_camera = 0, held_serial = 0;
  void frame() { fixture.screen.run_deferred(); fixture.drv->frame(); }
  const ui::Widget *widget(const std::string &key) { return fixture.screen.ui()->find(key); }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *w = widget(key); return w && w->enabled; })) << key;
  }
  void reveal(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget(key));
    for (int i = 0; i < 24; ++i) {
      const auto *w = widget(key); const auto clip = w->rect.intersect(w->clip);
      if (std::abs(clip.h - w->rect.h) <= 1 && std::abs(clip.w - w->rect.w) <= 1) { return; }
      wm::Event event; event.type = wm::EventType::Wheel; event.x = int(w->clip.cx());
      event.y = fixture.screen.rect().ymax - 1 - int(w->clip.cy()); event.wheel_y = w->rect.cy() > w->clip.cy() ? -3 : 3;
      ASSERT_TRUE(fixture.drv->send(event)); ++wheels; frame();
    }
    FAIL() << "Peer control is not reachable through normal scrolling: " << key;
  }
  void click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(reveal(key)); const auto [x, y] = fixture.widget_center(key);
    ASSERT_TRUE(fixture.drv->click(x, y)); ++clicks; frame();
  }
  void text(const std::string &key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
#ifdef __APPLE__
    fixture.drv->key(wm::Key::A, wm::ModOS);
#else
    fixture.drv->key(wm::Key::A, wm::ModCtrl);
#endif
    auto event = ui::Event::text_input(value); event.time = double(++fixture.drv->time_ms) / 1000.;
    fixture.screen.ui()->handle_event(event); frame(); fixture.drv->key(wm::Key::Enter); frame();
    ASSERT_NE(widget(key), nullptr); EXPECT_EQ(widget(key)->string.value(), value);
  }
  void start_layout(const char *type)
  {
    auto &area = fixture.area("a4"); ASSERT_TRUE(area.set_tabs({type, kEditorPython}, 0));
    fixture.screen.set_maximized(&area); area.set_toolbar_open(false); area.set_sidebar_open(false);
    auto draft = area.tab(1).save_workspace_state(); draft["source"] = "print('keep hidden peer navigation draft')";
    ASSERT_TRUE(area.tab(1).load_workspace_state(draft)); held_hidden = area.tab(1).save_workspace_state();
    store.viewer().set_auto_evaluate(false); store.viewer().prefetch_neighbours = false;
    held_payload = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store.viewer().open_payload(held_payload, "Public navigation Viewer fixture");
    // Complete the pre-existing passive metadata reads before the fixed
    // preservation baseline and counted interaction start.
    ASSERT_TRUE(loop.pump_until([&] {
      store.viewer().pump();
      return !store.viewer().presets().empty() && store.viewer().catalog().is_object() && store.viewer().colormaps();
    }));
    held_viewer = store.viewer().save_workspace_state(); held_camera = store.viewer().camera_serial(); held_serial = store.viewer().payload_serial();
    if (std::string(type) == kEditorPeers) {
      auto state = area.tab(0).save_workspace_state(); state["section"] = 2; ASSERT_TRUE(area.tab(0).load_workspace_state(state));
    }
    frame();
  }
  void preserved()
  {
    EXPECT_EQ(fixture.area("a4").tab(1).save_workspace_state(), held_hidden);
    EXPECT_TRUE(fixture.area("a4").tab(1).has_unsaved_changes());
    EXPECT_TRUE(store.viewer().save_workspace_state() == held_viewer) << "Viewer workspace changed";
    EXPECT_EQ(store.viewer().camera_serial(), held_camera);
    EXPECT_EQ(store.viewer().payload_serial(), held_serial); EXPECT_EQ(store.viewer().base_payload(), held_payload);
  }
  Json recorded(const std::string &name)
  {
    Json value; published(name, value); return value;  // A failure is already reported with its cause.
  }
  void query_history(const std::string &operation)
  {
    if (!widget("peer_operations")) { ASSERT_NO_FATAL_FAILURE(click("peer_history")); }
    ASSERT_NO_FATAL_FAILURE(click("peer_operations"));
    ASSERT_NO_FATAL_FAILURE(click("peer_operation/" + operation));
    const auto expected = calls("operations.get");
    ASSERT_NO_FATAL_FAILURE(click("peer_operation_check"));
    const auto version = store.version();
    ASSERT_TRUE(loop.pump_until([&] { frame(); return calls("operations.get") > expected && store.version() > version &&
      widget("peer_operation_check") && widget("peer_operation_check")->enabled; }));
  }
};

#ifdef STK_PEER_NATIVE_ACCEPTANCE
class PeerNativeMouse : public PeerMouse {
 protected:
  bool native_helpers() const override { return true; }
};

class PeerNativeReceiverMouse : public PeerNativeMouse {
 protected:
  const char *native_role() const override { return "receiver"; }
};

TEST_F(PeerNativeMouse, ExplicitSenderClicksUseActualInstalledHelpersAndReceiverApproval)
{
  open_source(0); start_layout(kEditorPeers);
  const auto connected = recorded("native.json").at("connection_id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(click("peers_refresh"));
  ASSERT_NO_FATAL_FAILURE(click("peer_select_connection/" + connected));
  ASSERT_NO_FATAL_FAILURE(click("peer_load_snapshots"));
  ASSERT_NO_FATAL_FAILURE(click("peer_snapshot/" + seeds.at(0).at("snapshot_id").get<std::string>()));
  for (const auto &record : seeds.at(0).at("record_ids")) {
    ASSERT_NO_FATAL_FAILURE(click("peer_file/" + record.get<std::string>()));
  }
  ASSERT_NO_FATAL_FAILURE(click("peer_prepare"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return calls("files.prepare") == 1 && widget("peer_host") && widget("peer_host")->enabled; }));
  ASSERT_NE(widget("peer_offer"), nullptr); EXPECT_FALSE(widget("peer_offer")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("peer_host"));
  ASSERT_NO_FATAL_FAILURE(click("peer_offer"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return std::filesystem::exists(dir.path() / "control.native_offer.json"); }));
  const auto offered = recorded("native_offer.json");
  ASSERT_EQ(offered.at("state"), "completed");
  const auto transfer = offered.at("result").at("transfer_id").get<std::string>();
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "received"));
  ASSERT_NO_FATAL_FAILURE(click("peer_list_files"));
  ASSERT_NO_FATAL_FAILURE(click("peer_transfer/" + transfer));
  ASSERT_NO_FATAL_FAILURE(wait_widget("peer_file_detail"));
  marker("approve_receiver");
  ASSERT_TRUE(loop.pump_until([&] { frame(); return std::filesystem::exists(dir.path() / "control.native_accept.json") ||
    std::filesystem::exists(dir.path() / "control.native_error"); }));
  ASSERT_FALSE(std::filesystem::exists(dir.path() / "control.native_error"));
  ASSERT_EQ(recorded("native_accept.json").at("transfer_id"), transfer);
  ASSERT_NO_FATAL_FAILURE(click("peer_query"));
  ASSERT_NO_FATAL_FAILURE(click("peer_send"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return std::filesystem::exists(dir.path() / "control.native_complete.json"); }));
  const auto complete = recorded("native_complete.json");
  ASSERT_EQ(complete.at("state"), "completed"); EXPECT_EQ(complete.at("result").at("state"), "complete");
  for (const auto &[name, expected] : std::vector<std::pair<std::string, std::string>>{
         {"selected.bin", "first"}, {"another.bin", "other public synthetic bytes"}}) {
    std::ifstream input(dir.path() / "received" / name, std::ios::binary); ASSERT_TRUE(input.good());
    const std::string bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    EXPECT_EQ(bytes, expected);
  }
  preserved();
  std::cout << "PEER_INSTALLED_MOUSE 1440x1200 scale1 en maximized-a4 sender authenticated-start clicks=" << clicks
            << " wheels=" << wheels << " actualInstalledHelpers=true syntheticDTO=false receiverApproval=explicitFixture Viewer+hiddenPython=preserved\n";
}

TEST_F(PeerNativeReceiverMouse, ExplicitRecipientClicksReviewAcceptAndReceiveActualFrozenBytes)
{
  start_layout(kEditorPeers);
  auto draft = fixture.area("a4").tab(0).save_workspace_state(); draft["section"] = 3;
  ASSERT_TRUE(fixture.area("a4").tab(0).load_workspace_state(draft)); frame();
  const auto metadata = recorded("native.json");
  const auto connection = metadata.at("connection_id").get<std::string>();
  const auto transfer = metadata.at("transfer_id").get<std::string>();
  ASSERT_NO_FATAL_FAILURE(click("peers_refresh"));
  ASSERT_NO_FATAL_FAILURE(click("peer_select_connection/" + connection));
  ASSERT_NO_FATAL_FAILURE(click("peer_list_files"));
  ASSERT_NO_FATAL_FAILURE(click("peer_transfer/" + transfer));
  ASSERT_NO_FATAL_FAILURE(text("peer_target", (dir.path() / "received").string()));
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "received"));
  ASSERT_NO_FATAL_FAILURE(click("peer_accept"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return std::filesystem::exists(dir.path() / "control.native_accept.json"); }));
  ASSERT_EQ(recorded("native_accept.json").at("state"), "completed");
  marker("start_sender");
  ASSERT_TRUE(loop.pump_until([&] { frame(); return std::filesystem::exists(dir.path() / "control.native_complete.json") ||
    std::filesystem::exists(dir.path() / "control.native_error"); }));
  ASSERT_FALSE(std::filesystem::exists(dir.path() / "control.native_error"));
  ASSERT_EQ(recorded("native_complete.json").at("result").at("state"), "complete");
  ASSERT_NO_FATAL_FAILURE(click("peer_file_detail"));
  ASSERT_TRUE(loop.pump_until([&] {
    frame(); std::ifstream input(dir.path() / "control.native_details.json"); Json status;
    if (!input.good()) { return false; } input >> status;
    return status.at("state") == "complete" && status.at("transfer_id") == transfer;
  }));
  for (const auto &[name, expected] : std::vector<std::pair<std::string, std::string>>{
         {"selected.bin", "first"}, {"another.bin", "other public synthetic bytes"}}) {
    std::ifstream input(dir.path() / "received" / name, std::ios::binary); ASSERT_TRUE(input.good());
    const std::string bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    EXPECT_EQ(bytes, expected);
  }
  preserved();
  std::cout << "PEER_INSTALLED_RECEIVER_MOUSE 1440x1200 scale1 en maximized-a4 offered-start clicks=" << clicks
            << " wheels=" << wheels << " actualInstalledHelpers=true syntheticDTO=false sender=explicitFixture Viewer+hiddenPython=preserved\n";
}
#endif

TEST_F(PeerMouse, ActualClicksSelectTwoFilesHostReceiptEnablesOfferAndPreservesOtherDraftAndViewer)
{
  open_source(0); auto setup = state().new_view(); state().sync(setup);
  ASSERT_TRUE(state().act(setup, "identity.initialize", {{"display_name", "Public UI fixture"}})); settle(setup);
  marker("draw_host"); auto &area = fixture.area("a4"); ASSERT_TRUE(area.set_tabs({kEditorPeers, kEditorPython}, 0));
  fixture.screen.set_maximized(&area); area.set_toolbar_open(false); area.set_sidebar_open(false);
  auto drafts = area.tab(1).save_workspace_state(); drafts["source"] = "print('keep hidden peer draft')";
  ASSERT_TRUE(area.tab(1).load_workspace_state(drafts)); drafts = area.tab(1).save_workspace_state();
  store.viewer().set_auto_evaluate(false); store.viewer().prefetch_neighbours = false;
  auto shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  store.viewer().open_payload(shown, "Existing public synthetic Viewer");
  const auto viewer = store.viewer().save_workspace_state(); const auto camera = store.viewer().camera_serial(), payload = store.viewer().payload_serial();
  auto draft = area.tab(0).save_workspace_state(); draft["section"] = 2; ASSERT_TRUE(area.tab(0).load_workspace_state(draft));
  frame(); EXPECT_EQ(calls("sessions.host"), 0); EXPECT_EQ(calls("files.offer"), 0);
  ASSERT_NO_FATAL_FAILURE(click("peers_refresh"));
  ASSERT_NO_FATAL_FAILURE(click("peer_select_connection/00000000-0000-4000-8000-000000000009"));
  ASSERT_NO_FATAL_FAILURE(click("peer_load_snapshots"));
  ASSERT_NO_FATAL_FAILURE(click("peer_snapshot/" + seeds.at(0).at("snapshot_id").get<std::string>()));
  const auto first = seeds.at(0).at("record_ids").at(0).get<std::string>(), second = seeds.at(0).at("record_ids").at(1).get<std::string>();
  ASSERT_NO_FATAL_FAILURE(click("peer_file/" + first)); ASSERT_NE(widget("peer_file/" + second), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("peer_file/" + second)); ASSERT_NE(widget("peer_file/" + first), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("peer_prepare"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return calls("files.prepare") == 1 && widget("peer_host") && widget("peer_host")->enabled; }));
  ASSERT_NE(widget("peer_offer"), nullptr); EXPECT_FALSE(widget("peer_offer")->enabled);
  ASSERT_NO_FATAL_FAILURE(click("peer_host"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("peer_offer"));
  EXPECT_EQ(calls("sessions.host"), 1); EXPECT_EQ(calls("files.offer"), 0);
  ASSERT_NO_FATAL_FAILURE(click("peer_offer"));
  Json offered; ASSERT_TRUE(published("offer_request_1.json", offered));
  EXPECT_EQ(offered.at("session_id"), "00000000-0000-4000-8000-000000000007");
  ASSERT_TRUE(loop.pump_until([&] { frame(); return widget("peer_session_id") && widget("peer_session_id")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(text("peer_session_id", "00000000-0000-4000-8000-000000000006"));
  ASSERT_NO_FATAL_FAILURE(click("peer_offer"));
  ASSERT_TRUE(published("offer_request_2.json", offered)); EXPECT_EQ(calls("files.offer"), 2);
  EXPECT_EQ(offered.at("session_id"), "00000000-0000-4000-8000-000000000006");
  EXPECT_EQ(area.tab(1).save_workspace_state(), drafts); EXPECT_TRUE(area.tab(1).has_unsaved_changes());
  EXPECT_EQ(store.viewer().save_workspace_state(), viewer); EXPECT_EQ(store.viewer().camera_serial(), camera);
  EXPECT_EQ(store.viewer().payload_serial(), payload); EXPECT_EQ(store.viewer().base_payload(), shown);
  const auto saved = area.tab(0).save_workspace_state();
  EXPECT_FALSE(saved.at("drafts").contains("session_id")); EXPECT_FALSE(saved.at("drafts").contains("signal"));
  std::cout << "PEER_CPU_MOUSE 1440x1200 scale1 en maximized-a4 send-tab two-frozen-files clicks=" << clicks << " wheels=" << wheels
            << " syntheticHostDTO=true realBridge=true Viewer+hiddenPython=preserved\n";
}

TEST_F(PeerMouse, HistoricalHostAndQueryReceiptsCannotOverrideExplicitSessionAndGrantDrafts)
{
  ASSERT_NO_FATAL_FAILURE(open_source(0)); auto setup = state().new_view(); state().sync(setup);
  ASSERT_TRUE(state().act(setup, "identity.initialize", {{"display_name", "History draw fixture"}})); settle(setup);
  marker("draw_host");
  ASSERT_NO_FATAL_FAILURE(start_layout(kEditorPeers));
  ASSERT_NO_FATAL_FAILURE(click("peers_refresh"));
  ASSERT_NO_FATAL_FAILURE(click("peer_select_connection/00000000-0000-4000-8000-000000000009"));
  ASSERT_NO_FATAL_FAILURE(click("peer_load_snapshots"));
  ASSERT_NO_FATAL_FAILURE(click("peer_snapshot/" + seeds.at(0).at("snapshot_id").get<std::string>()));
  ASSERT_NO_FATAL_FAILURE(click("peer_file/" + seeds.at(0).at("record_ids").at(0).get<std::string>()));
  ASSERT_NO_FATAL_FAILURE(click("peer_prepare"));
  ASSERT_NO_FATAL_FAILURE(click("peer_host"));
  const auto hosted = recorded("host_operation.json");
  const std::string chosen_session = "00000000-0000-4000-8000-000000000006";
  ASSERT_NO_FATAL_FAILURE(text("peer_session_id", chosen_session));
  ASSERT_NO_FATAL_FAILURE(query_history(io::get_string(hosted, "operation_id")));
  ASSERT_NO_FATAL_FAILURE(click("peer_offer"));
  EXPECT_EQ(recorded("offer_request_1.json").at("session_id"), chosen_session);
  ASSERT_NO_FATAL_FAILURE(text("peer_transfer_id", "00000000-0000-4000-8000-000000000003"));
  ASSERT_NO_FATAL_FAILURE(click("peer_query")); const auto queried = recorded("query_operation.json");
  const std::string chosen_grant = "00000000-0000-4000-8000-000000000002";
  ASSERT_NO_FATAL_FAILURE(text("peer_grant_id", chosen_grant));
  ASSERT_NO_FATAL_FAILURE(query_history(io::get_string(queried, "operation_id")));
  ASSERT_NO_FATAL_FAILURE(click("peer_send"));
  EXPECT_EQ(recorded("send_request_1.json").at("grant_id"), chosen_grant);
  preserved();
  if (!HasFailure()) { std::cout << "PEER_HISTORY_MOUSE 1440x1200 scale1 en maximized-a4 sender clicks=" << clicks << " wheels=" << wheels
            << " syntheticHostAndQueryDTO=true realBridge=true manualSession+grant=preserved\n"; }
}

TEST_F(PeerMouse, FilesShareOpensSenderWithSelectedRecordInOneClickWithoutChangingViewerOrHiddenDraft)
{
  ASSERT_NO_FATAL_FAILURE(open_source(0));
  ASSERT_NO_FATAL_FAILURE(start_layout(kEditorFiles));
  const auto &project = store.project().project(); ASSERT_TRUE(project);
  const auto record = seeds.at(0).at("record_ids").at(0).get<std::string>(); std::string error;
  ASSERT_TRUE(fixture.area("a4").editor().navigate({{"record_id", record}, {"project_handle", project->handle},
      {"expected_revision", project->revision}}, {}, error)) << error;
  ASSERT_NO_FATAL_FAILURE(wait_widget("files_share_peer")); EXPECT_EQ(calls("files.prepare"), 0);
  ASSERT_NO_FATAL_FAILURE(click("files_share_peer"));
  Editor *peers = nullptr;
  ASSERT_TRUE(loop.pump_until([&] {
    frame(); for (const auto &leaf : fixture.screen.areas()) {
      if (auto *area = dynamic_cast<EditorArea *>(leaf)) {
        for (int i = 0; i < area->tab_count(); ++i) { if (area->tab(i).type().id == kEditorPeers) { peers = &area->tab(i); } }
      }
    }
    return peers && peers->save_workspace_state().at("drafts").at("record_ids") == record;
  }));
  ASSERT_NE(peers, nullptr); EXPECT_EQ(peers->save_workspace_state().at("section"), 2);
  EXPECT_EQ(peers->save_workspace_state().at("source_project"), project->id); EXPECT_EQ(calls("files.prepare"), 0);
  EXPECT_EQ(calls("sessions.host"), 0); EXPECT_EQ(calls("files.offer"), 0); EXPECT_EQ(clicks, 1); preserved();
  if (!HasFailure()) { std::cout << "PEER_FILES_ENTRY_MOUSE 1440x1200 scale1 en maximized-a4 Files selected-registered-record clicks=" << clicks
            << " wheels=" << wheels << " result=Peers-section2+record-draft noRPCsend=true Viewer+hiddenPython=preserved\n"; }
}
}  // namespace
}  // namespace stk::app
