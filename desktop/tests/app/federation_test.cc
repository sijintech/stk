/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/federation_state.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"
#include "stk/io/payload.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
const std::string table_id = "00000000-0000-4000-8000-000000000001";
const std::string feature_id = "00000000-0000-4000-8000-000000000002";
const std::string target_id = "00000000-0000-4000-8000-000000000003";
const std::string training_row = "00000000-0000-4000-8000-000000000004";
const std::string heldout_row = "00000000-0000-4000-8000-000000000005";
const std::string run_id = "00000000-0000-4000-8000-000000000006";

// Strict production bridge, private plan/owner ledgers and exact numerical capsules.
// Only transport is replaced by an in-process trusted owner endpoint. No training/model request.
constexpr const char *kBridge = R"PY(
from pathlib import Path
from copy import deepcopy
import hashlib
import struct
import sys
import threading
import time
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.backends import RuntimeBackend
from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.__main__ import main
from suan.federation.node import NodeFederationService
from suan.federation.owner import NodeOwnerService
from suan.federation import inputs
from suan.federation.coordinator import FederationCoordinator
from suan.federation.protocol import model_layout, training_spec_sha256
from suan.federation.updates import encode_arrays
from uuid import UUID
control = Path(sys.argv.pop(1))
node = NodeFederationService(object(), control.parent / 'private-node', None,
                             workspace_root=control.parent / 'public-workspaces')
coordinator_root = control.parent / 'synthetic-coordinator'
owner = NodeOwnerService(node, coordinator_root=coordinator_root)
counter_lock = threading.Lock()
def count(method):
    with counter_lock, control.with_suffix('.calls').open('a', encoding='utf-8') as f:
        f.write(method + '\n')
def seed_candidates(request, grant):
    # Coherent synthetic provenance for UI acceptance only: no Flower, fitting or network.
    settings, identity = request['spec'], request['run_id']
    coordinator = FederationCoordinator(coordinator_root, None, None)
    if (coordinator_root / identity / 'run.json').exists(): return
    def model(weight, bias, kind='model'):
        return encode_arrays([{**layout, 'data':struct.pack('<d', value)}
                              for layout, value in zip(model_layout(settings), (weight, bias))], kind=kind)
    manifest = {'format':'stk.federation-run/1', 'run_id':identity,
                'coordinator_device_id':'a'*32, 'coordinator_id':request['coordinator_id'],
                'spec_sha256':training_spec_sha256(settings), 'max_rounds':2,
                'participants':[{'node_id':str(i)*32, 'participant_id':str(i)*64,
                                 'grant_id':str(UUID(int=800+i)), 'dataset_sha256':str(i+3)*64}
                                for i in (1,2,3)]}
    coordinator.create(manifest, settings, model(0., 0.))
    for number, weight, bias in ((1,2.,0.), (2,1.,3.)):
        current = coordinator.prepare_round(identity); raw = model(weight, bias)
        receipt = {'format':'stk.federation-aggregate-result/1', 'run_id':identity, 'round':number,
                   'source_model_sha256':current['model']['sha256'],
                   'spec_sha256':manifest['spec_sha256'], 'participants':[p['participant_id'] for p in manifest['participants']],
                   'model_sha256':hashlib.sha256(raw).hexdigest(), 'model_bytes':len(raw), 'num_examples':3,
                   'framework':{'name':'flwr','version':'1.42.0'}, 'metrics':{'loss':0.}}
        folder = coordinator_root / identity / str(number)
        inputs.write_bytes(folder / 'candidate.bin', raw)
        current.update(state='aggregated', receipt=receipt, candidate_sha256=receipt['model_sha256'])
        coordinator._save(folder / 'round.json', current)
        delta = model(0., 0., 'delta')
        metadata = {'format':'stk.federation-update/1', 'run_id':identity, 'round':number,
                    'participant_id':request['participant_id'], 'model_sha256':current['model']['sha256'],
                    'spec_sha256':manifest['spec_sha256'], 'dataset_sha256':request['dataset_sha256'],
                    'grant_id':grant['grant_id'], 'update_sha256':hashlib.sha256(delta).hexdigest(),
                    'update_bytes':len(delta), 'num_examples':1, 'metrics':{'loss':0.}, 'masked':False}
        node.registry.prepare_update(grant['grant_id'], metadata, delta, model_sha256=current['model']['sha256'])
    count('synthetic_candidate_seed')
class Client:
    url = 'http://127.0.0.1:8765'
    def federation_owner(self, method, params):
        count(method)
        if method == 'grants.approve' and control.with_suffix('.generic_approve').exists():
            raise BridgeError('conflict', 'Synthetic unknown owner outcome')
        result = owner.call(method, params)
        if (method == 'grants.approve' and result['state'] == 'completed'
                and control.with_suffix('.seed_candidates').exists()):
            seed_candidates(params['request'], result['result'])
        return result
original = Bridge.__init__
def init(self, *args, **kwargs):
    original(self, *args, **kwargs)
    self.connections.backend = lambda connection, node=None: RuntimeBackend(connection, Client())
    self.connections.list = lambda: [
        {'id':'runtime:lab','kind':'runtime','name':'Trusted owner Runtime','url':Client.url},
        {'id':'hub:blocked','kind':'hub','name':'Hub is not owner access','url':None}]
Bridge.__init__ = init
send = Bridge.send
def controlled_send(self, message, method=None):
    if method == 'project.federation.prepare' and 'result' in message:
        if control.with_suffix('.wrong_prepare').exists():
            message = deepcopy(message)
            message['result']['plan']['plan_id'] = '00000000-0000-4000-8000-000000000009'
        if control.with_suffix('.prepare_internal').exists():
            message = {'id':message['id'], 'error':{'code':'internal_error',
                       'message':'Synthetic local prepare observation failed', 'retryable':False}}
    if method == 'federation.owner.grants.approve' and 'error' in message:
        message = deepcopy(message)
        data = message['error'].get('data') or {}
        proof = data.get('rejection')
        if proof:
            if control.with_suffix('.proof_sha').exists(): proof['request_sha256'] = 'c' * 64
            if control.with_suffix('.proof_id').exists(): proof['operation_id'] = '00000000-0000-4000-8000-000000000009'
            if control.with_suffix('.proof_method').exists(): proof['method'] = 'grants.revoke'
            if control.with_suffix('.proof_extra').exists(): proof['extra'] = True
            if control.with_suffix('.proof_generation').exists(): proof['generation'] = True
            if control.with_suffix('.proof_upper').exists(): proof['request_sha256'] = 'C' * 64
            if control.with_suffix('.proof_envelope').exists(): data['operation_id'] = '00000000-0000-4000-8000-000000000009'
    suffix = ('write' if method == 'federation.owner.grants.approve' else
              'info' if method == 'federation.owner.info' else
              'plan' if method == 'project.federation.get' else
              'prepare' if method == 'project.federation.prepare' else None)
    if suffix and 'result' in message and control.with_suffix('.hold_' + suffix).exists():
        control.with_suffix('.' + suffix + '_held').write_text('constructed', encoding='utf-8')
        def deliver():
            end = time.monotonic() + 30
            while not control.with_suffix('.' + suffix + '_release').exists():
                if time.monotonic() >= end: return
                time.sleep(.01)
            send(self, message, method)
            control.with_suffix('.' + suffix + '_sent').write_text('sent', encoding='utf-8')
        threading.Thread(target=deliver, daemon=True).start()
        return
    send(self, message, method)
Bridge.send = controlled_send
raise SystemExit(main())
)PY";

TEST(FederationState, OfflineSyncAndDetachNeverExecuteOrClearIndependentDrafts)
{
  AppStore store; auto &state = store.federation(); auto first = state.new_view(), second = state.new_view();
  state.sync(first); state.sync(second); EXPECT_FALSE(state.supported());
  first->plan_id = FederationState::new_uuid(); first->operation_id = FederationState::new_uuid(); first->uncertain = true;
  second->plan = {{"source", "second"}}; const auto epoch = second->draft_epoch;
  EXPECT_FALSE(state.load_connections(first)); EXPECT_FALSE(state.write(first, "grants.revoke", {{"grant_id", run_id}}));
  EXPECT_FALSE(state.set_connection(first, "hub:blocked"));
  state.invalidate_draft(first, true); state.detach(first);
  EXPECT_TRUE(first->uncertain); EXPECT_FALSE(first->operation_id.empty());
  EXPECT_EQ(second->draft_epoch, epoch); EXPECT_EQ(second->plan.at("source"), "second");
}

TEST(FederationState, EvaluationAdmissionRequiresEveryAbsoluteAndBaselineGate)
{
  Json value = {{"state", "passed"}, {"receipt_sha256", std::string(64, 'a')},
    {"gate", Json::array({{{"passed", true}, {"absolute_ok", true}, {"baseline_ok", true}}})}};
  EXPECT_TRUE(FederationState::evaluation_passed(value));
  for (const auto key : {"passed", "absolute_ok", "baseline_ok"}) {
    auto bad = value; bad["gate"][0][key] = false; EXPECT_FALSE(FederationState::evaluation_passed(bad));
  }
  value["gate"] = Json::array(); EXPECT_FALSE(FederationState::evaluation_passed(value));
  value["state"] = "failed"; EXPECT_FALSE(FederationState::evaluation_passed(value));
}

TEST(FederationEditor, WorkspaceRestoresOnlyBoundedDraftsAndNoConnectionOrOperation)
{
  EditorRegistry registry; register_builtin_editors(registry); auto a = registry.create(kEditorFederation), b = registry.create(kEditorFederation);
  ASSERT_TRUE(a); ASSERT_TRUE(b); auto value = a->save_workspace_state();
  value["source_project"] = run_id; value["table_id"] = table_id; value["source_revision"] = 1;
  value["features"] = {feature_id}; value["targets"] = {target_id}; value["roles"] = {{training_row, 1}, {heldout_row, 2}};
  value["text"]["learning_rate"] = "1e-"; value["thresholds"] = {{"Pressure", "2e-"}}; value["strategy"] = 1;
  ASSERT_TRUE(a->load_workspace_state(value)); EXPECT_TRUE(a->has_unsaved_changes());
  ASSERT_TRUE(b->load_workspace_state(a->save_workspace_state())); EXPECT_EQ(b->save_workspace_state(), value);
  EXPECT_FALSE(value.contains("connection")); EXPECT_FALSE(value.contains("operation_id")); EXPECT_FALSE(value.contains("plan"));
  const auto before = b->save_workspace_state();
  for (const auto bad : std::vector<Json>{{{"connection", "runtime:old"}}, {{"owner_id", run_id}}, {{"roles", {{training_row, 3}}}},
       {{"text", {{"unknown", "value"}}}}, {{"text", {{"run_id", false}}}}, {{"strategy", 2}}, {{"source_revision", true}}}) {
    EXPECT_FALSE(b->load_workspace_state(bad)); EXPECT_EQ(b->save_workspace_state(), before);
  }
}

class FederationBridge : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"federation-native"}; bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1200}; std::unique_ptr<bridge::Client> client;
  AppStore &store() { return f.shell->store(); }
  FederationState &state() { return store().federation(); }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *p = std::getenv("STK_BRIDGE_TEST_PYTHON"); p && *p) { python = p; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    ASSERT_FALSE(python.empty()) << "An installed test Python is required";
    { std::ofstream script(dir.path() / "bridge.py"); script << kBridge; ASSERT_TRUE(script.good()); }
    bridge::ClientOptions options; options.executor = loop.executor(); options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = dir.str() + "/state";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/control", "--stdio", "--state-dir", options.state_dir,
      "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store().set_bridge(client.get()); store().project().sync();
    ASSERT_TRUE(store().project().create(dir.str() + "/project", "Public synthetic numeric owner test"));
    ASSERT_TRUE(loop.pump_until([&] { store().project().sync(); return store().project().ready() && store().project().loaded() && !store().project().busy(); }));
    Json commands = Json::array({
      {{"op", "create_table"}, {"id", table_id}, {"name", "Independent numeric rows"}},
      {{"op", "add_field"}, {"id", feature_id}, {"table_id", table_id}, {"name", "Temperature"}, {"type", "number"}, {"unit", "K"}},
      {{"op", "add_field"}, {"id", target_id}, {"table_id", table_id}, {"name", "Pressure"}, {"type", "number"}, {"unit", "Pa"}},
      {{"op", "add_record"}, {"id", training_row}, {"table_id", table_id}},
      {{"op", "add_record"}, {"id", heldout_row}, {"table_id", table_id}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", training_row}, {"field_id", feature_id}, {"value", 1.0}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", training_row}, {"field_id", target_id}, {"value", 2.0}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", heldout_row}, {"field_id", feature_id}, {"value", 3.0}},
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", heldout_row}, {"field_id", target_id}, {"value", 6.0}}});
    ASSERT_FALSE(call("project.apply", {{"handle", store().project().project()->handle}, {"expected_revision", 0}, {"commands", commands}}).is_null());
    store().project().refresh(); ASSERT_TRUE(loop.pump_until([&] { return store().project().ready() && store().project().project()->revision == 1; }));
  }
  void TearDown() override
  {
    release("write"); release("info"); release("plan"); release("prepare"); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  Json call(const std::string &method, Json params)
  {
    std::optional<bridge::Result<Json>> result;
    client->call(method, std::move(params)).then([&](auto reply) { result = std::move(reply); });
    if (!loop.pump_until([&] { return result.has_value(); }, 30) || !result->ok()) {
      ADD_FAILURE() << method << ": " << (result ? result->error().describe() : "timeout"); return nullptr;
    }
    return result->value();
  }
  void settle(const FederationState::ViewPtr &view)
  {
    ASSERT_TRUE(loop.pump_until([&] { state().sync(view); return !view->reading(); })); ASSERT_TRUE(view->error.empty()) << view->error;
  }
  void marker(const std::string &name) { std::ofstream file(dir.path() / ("control." + name)); file << "marker"; }
  void release(const std::string &name) { marker(name + "_release"); }
  int count(const std::string &method)
  {
    std::ifstream file(dir.path() / "control.calls"); std::string line; int n = 0;
    while (std::getline(file, line)) { n += line == method; } return n;
  }
  FederationState::ViewPtr prepared()
  {
    auto view = state().new_view(); state().sync(view);
    EXPECT_TRUE(state().set_connection(view, "runtime:lab")); EXPECT_TRUE(state().read(view, "info")); settle(view);
    EXPECT_TRUE(state().load_rows(view, table_id)); settle(view);
    EXPECT_TRUE(state().prepare(view, plan_params()));
    settle(view); return view;
  }
  Json plan_params()
  {
    const auto &p = *store().project().project();
    return {{"handle", p.handle}, {"expected_revision", p.revision}, {"table_id", table_id},
      {"plan_id", FederationState::new_uuid()}, {"training_dataset_id", FederationState::new_uuid()}, {"holdout_dataset_id", FederationState::new_uuid()},
      {"feature_ids", {feature_id}}, {"target_ids", {target_id}}, {"training_rows", {training_row}}, {"holdout_rows", {heldout_row}}};
  }
  Json grant_request(const FederationState::ViewPtr &view)
  {
    const auto &manifest = view->registration.at("datasets")[0].at("manifest");
    Json spec = {{"format", "stk.federation-training-spec/1"}, {"trainer", "linear-regression/1"}, {"dtype", "f64"},
      {"normalization", "none"}, {"features", {{{"name", "Temperature"}, {"unit", "K"}}}}, {"targets", {{{"name", "Pressure"}, {"unit", "Pa"}}}},
      {"steps", 2}, {"learning_rate", .01}, {"strategy", "fedavg"}, {"proximal_mu", 0.0}};
    return {{"dataset_id", manifest.at("dataset_id")}, {"dataset_sha256", manifest.at("dataset_sha256")},
      {"source_sha256", view->registration.at("source_sha256")}, {"spec", spec}, {"run_id", run_id},
      {"coordinator_id", std::string(64, 'a')}, {"participant_id", std::string(64, 'b')}, {"max_rounds", 2}};
  }
};

TEST_F(FederationBridge, PrepareKeepsRawArraysPrivateAndRegisterIsSeparateFromConsent)
{
  auto view = prepared(); ASSERT_TRUE(view->plan.is_object()); EXPECT_FALSE(view->plan.dump().find("\"x\"") != std::string::npos);
  EXPECT_EQ(count("datasets.register"), 0); EXPECT_FALSE(fs::exists(dir.path() / "private-node"));
  const auto before = call("project.snapshot", {{"handle", store().project().project()->handle}});
  ASSERT_TRUE(state().register_plan(view)); settle(view);
  EXPECT_EQ(count("datasets.register"), 1); EXPECT_TRUE(view->registration.is_object()); EXPECT_EQ(count("grants.approve"), 0);
  EXPECT_EQ(call("project.snapshot", {{"handle", store().project().project()->handle}}), before);
  EXPECT_FALSE(state().set_connection(view, "hub:blocked"));
  const auto writes = count("datasets.register"); state().sync(view); state().detach(view); state().sync(view);
  EXPECT_EQ(count("datasets.register"), writes);
}

TEST_F(FederationBridge, LostWriteReplyAndSameClientReplacementOnlyQueryOriginalIdentity)
{
  auto view = prepared(); ASSERT_TRUE(state().register_plan(view)); settle(view);
  marker("hold_write"); ASSERT_TRUE(state().write(view, "grants.approve", grant_request(view)));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.write_held"); }));
  const auto identity = view->operation_id; EXPECT_EQ(count("grants.approve"), 1);
  store().set_bridge(nullptr); store().set_bridge(client.get()); state().sync(view);
  EXPECT_TRUE(view->uncertain); EXPECT_EQ(view->operation_id, identity);
  EXPECT_FALSE(state().write(view, "grants.approve", grant_request(view))); EXPECT_EQ(count("grants.approve"), 1);
  ASSERT_TRUE(state().check_operation(view)); settle(view);
  EXPECT_FALSE(view->uncertain); EXPECT_EQ(view->operation_id, identity); EXPECT_EQ(view->operation.at("result").at("grant_id"), identity);
  release("write"); ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.write_sent"); }));
  EXPECT_EQ(count("grants.approve"), 1);
}

TEST_F(FederationBridge, EarlierOwnerReadCannotOverwriteCompletedWriteGeneration)
{
  auto view = prepared(); ASSERT_TRUE(state().register_plan(view)); settle(view);
  marker("hold_info"); ASSERT_TRUE(state().read(view, "info"));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.info_held"); }));
  ASSERT_TRUE(state().write(view, "grants.approve", grant_request(view))); settle(view);
  const auto generation = view->info.at("generation"); release("info");
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.info_sent"); })); loop.run_ready();
  EXPECT_EQ(view->info.at("generation"), generation); EXPECT_EQ(count("grants.approve"), 1);
}

TEST_F(FederationBridge, OldEvaluationAndActivationButtonsCannotSubmitAnotherIdentity)
{
  auto view = prepared(); ASSERT_TRUE(state().register_plan(view)); settle(view);
  view->evaluation = {{"state", "passed"}, {"evaluation_id", run_id}, {"receipt_sha256", std::string(64, 'a')},
    {"gate", Json::array({{{"passed", true}, {"absolute_ok", true}, {"baseline_ok", true}}})}};
  EXPECT_FALSE(state().write(view, "models.admit", {{"evaluation_id", table_id}, {"receipt_sha256", std::string(64, 'a')},
    {"expected_active_version", nullptr}, {"expected_active_generation", 0}}));
  EXPECT_FALSE(state().write(view, "evaluations.evaluate", {{"evaluation_id", run_id}, {"plan_sha256", std::string(64, 'b')}}));
  view->models = {{"spec_sha256", std::string(64, 'a')}, {"active_version", "v1"}, {"generation", 2},
    {"versions", Json::array({{{"version", "v1"}}, {{"version", "v2"}}})}};
  EXPECT_FALSE(state().write(view, "models.activate", {{"spec_sha256", std::string(64, 'a')}, {"version", "v2"},
    {"expected_active_version", "v1"}, {"expected_active_generation", 1}}));
  view->models = nullptr;
  EXPECT_FALSE(state().write(view, "models.activate", {{"spec_sha256", std::string(64, 'a')}, {"version", "v2"},
    {"expected_active_version", "v1"}, {"expected_active_generation", 2}}));
  EXPECT_EQ(count("models.admit"), 0); EXPECT_EQ(count("models.activate"), 0); EXPECT_EQ(count("evaluations.evaluate"), 0);
}

TEST_F(FederationBridge, RapidPlanSelectionAndRejectedPreparePreserveAcceptedOriginalIdentity)
{
  auto view = prepared(); const auto first = view->plan_id; marker("hold_plan");
  ASSERT_TRUE(state().load_plan(view, first));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.plan_held"); }));
  EXPECT_FALSE(state().load_plan(view, FederationState::new_uuid())); EXPECT_EQ(view->plan_id, first);
  EXPECT_TRUE(view->plan.is_null()); EXPECT_FALSE(state().register_plan(view));
  release("plan"); settle(view); ASSERT_EQ(view->plan.at("plan_id"), first);
  marker("hold_prepare"); const auto original = plan_params(); ASSERT_TRUE(state().prepare(view, original));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.prepare_held"); }));
  EXPECT_FALSE(state().prepare(view, plan_params())); EXPECT_EQ(view->plan_id, io::get_string(original, "plan_id"));
  release("prepare"); settle(view); EXPECT_EQ(view->plan.at("plan_id"), original.at("plan_id"));
}

TEST_F(FederationBridge, MissingOriginalObservationDoesNotUnlockAnotherWrite)
{
  auto view = state().new_view(); state().sync(view); ASSERT_TRUE(state().set_connection(view, "runtime:lab"));
  ASSERT_TRUE(state().read(view, "info")); settle(view);
  view->operation_id = FederationState::new_uuid(); view->operation_method = "grants.approve"; view->uncertain = true;
  ASSERT_TRUE(state().check_operation(view)); ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  EXPECT_TRUE(view->uncertain); EXPECT_EQ(view->error, "federation.not_observed");
  EXPECT_FALSE(state().write(view, "grants.revoke", {{"grant_id", run_id}})); EXPECT_EQ(count("grants.revoke"), 0);
}

TEST_F(FederationBridge, StaleOwnerProofBindsNegativeZeroRequestAndRequiresExplicitFreshInfo)
{
  auto view = prepared(); ASSERT_TRUE(state().register_plan(view)); settle(view);
  const auto stale_info = view->info; const auto other_id = FederationState::new_uuid();
  call("federation.owner.grants.approve", {{"connection", view->connection}, {"operation_id", other_id},
    {"owner_id", stale_info.at("owner_id")}, {"expected_generation", stale_info.at("generation")}, {"request", grant_request(view)}});
  auto request = grant_request(view); request["spec"]["proximal_mu"] = -0.0;
  ASSERT_TRUE(state().write(view, "grants.approve", request));
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  const auto rejected_id = view->operation_id;
  ASSERT_TRUE(view->rejection.is_object()); EXPECT_FALSE(view->uncertain); EXPECT_TRUE(view->info.is_null());
  EXPECT_EQ(view->rejection.at("operation_id"), rejected_id);
  EXPECT_EQ(view->rejection.at("request_sha256"), view->operation_request_sha256);
  EXPECT_EQ(count("grants.approve"), 2); EXPECT_FALSE(state().write(view, "grants.approve", request));
  state().detach(view); state().sync(view); EXPECT_EQ(count("grants.approve"), 2);
  ASSERT_TRUE(state().check_operation(view)); ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  EXPECT_EQ(view->operation_id, rejected_id); EXPECT_FALSE(view->uncertain); EXPECT_EQ(count("grants.approve"), 2);
  auto reopened = state().new_view(); state().sync(reopened); ASSERT_TRUE(state().set_connection(reopened, "runtime:lab"));
  reopened->info = stale_info;
  ASSERT_TRUE(state().read(reopened, "operations.local", {{"offset", 0}, {"limit", 20}})); settle(reopened);
  EXPECT_TRUE(reopened->info.is_null());
  auto found = std::find_if(reopened->local_operations.begin(), reopened->local_operations.end(), [&](const Json &item) {
    return item.at("operation_id") == rejected_id;
  });
  ASSERT_NE(found, reopened->local_operations.end()); EXPECT_EQ(found->at("state"), "rejected");
  ASSERT_TRUE(state().select_operation(reopened, *found)); EXPECT_FALSE(reopened->uncertain);
  EXPECT_EQ(reopened->rejection, view->rejection); EXPECT_FALSE(state().write(reopened, "grants.approve", request));
  ASSERT_TRUE(state().read(reopened, "info")); settle(reopened); const auto fresh_info = reopened->info;
  ASSERT_TRUE(state().select_operation(reopened, *found)); EXPECT_EQ(reopened->info, fresh_info);
  ASSERT_TRUE(state().write(reopened, "grants.approve", request)); settle(reopened);
  EXPECT_NE(reopened->operation_id, rejected_id); EXPECT_EQ(count("grants.approve"), 3);
  EXPECT_TRUE(reopened->rejection.is_null());
}

TEST_F(FederationBridge, RegistrationRejectionRetainsPrivatePlanAndOriginalConnection)
{
  auto stale = prepared(), current = prepared(); const auto plan = stale->plan;
  ASSERT_TRUE(state().register_plan(current)); settle(current);
  ASSERT_TRUE(state().register_plan(stale)); ASSERT_TRUE(loop.pump_until([&] { return !stale->reading(); }));
  ASSERT_TRUE(stale->rejection.is_object()); EXPECT_FALSE(stale->uncertain); EXPECT_TRUE(stale->info.is_null());
  EXPECT_EQ(stale->plan, plan); EXPECT_EQ(stale->operation_plan_id, stale->plan_id);
  EXPECT_EQ(stale->operation_connection, "runtime:lab"); EXPECT_TRUE(stale->operation_request_sha256.empty());
  const auto original = stale->operation_id; ASSERT_TRUE(state().check_operation(stale));
  ASSERT_TRUE(loop.pump_until([&] { return !stale->reading(); })); EXPECT_FALSE(stale->uncertain);
  EXPECT_EQ(count("datasets.register"), 2); EXPECT_FALSE(state().register_plan(stale));
  const auto records = call("federation.owner.operations.local", {{"connection", "runtime:lab"}, {"offset", 0}, {"limit", 20}});
  auto found = std::find_if(records.at("operations").begin(), records.at("operations").end(), [&](const Json &item) {
    return item.at("operation_id") == original;
  });
  ASSERT_NE(found, records.at("operations").end()); EXPECT_EQ(found->at("plan_id"), stale->plan_id);
  ASSERT_TRUE(state().read(stale, "info")); settle(stale); ASSERT_TRUE(state().register_plan(stale)); settle(stale);
  EXPECT_NE(stale->operation_id, original); EXPECT_EQ(count("datasets.register"), 3);
}

TEST_F(FederationBridge, InvalidOwnerRequestProofDoesNotReserveAnOperationOrCreateConsent)
{
  auto view = prepared(); ASSERT_TRUE(state().register_plan(view)); settle(view);
  auto request = grant_request(view); request["source_sha256"] = std::string(64, 'c');
  ASSERT_TRUE(state().write(view, "grants.approve", request));
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  ASSERT_TRUE(view->rejection.is_object()); EXPECT_EQ(view->rejection.at("reason"), "invalid_request");
  EXPECT_FALSE(view->uncertain); EXPECT_TRUE(view->info.is_null());
  const auto reply = call("federation.owner.operations.get", {{"connection", view->connection}, {"operation_id", view->operation_id}});
  EXPECT_TRUE(reply.at("operation").is_null());
  EXPECT_EQ(io::python_json_dumps(reply.at("rejection"), true, true), io::python_json_dumps(view->rejection, true, true));
  EXPECT_TRUE(call("federation.owner.grants.list", {{"connection", view->connection}, {"offset", 0}, {"limit", 20}}).at("items").empty());
  EXPECT_EQ(count("grants.approve"), 1); EXPECT_FALSE(state().write(view, "grants.approve", grant_request(view)));
}

TEST_F(FederationBridge, ForgedOrGenericErrorNeverUnlocksOriginalOwnerWrite)
{
  auto original = prepared(); ASSERT_TRUE(state().register_plan(original)); settle(original);
  const auto stale_info = original->info;
  call("federation.owner.grants.approve", {{"connection", original->connection}, {"operation_id", FederationState::new_uuid()},
    {"owner_id", stale_info.at("owner_id")}, {"expected_generation", stale_info.at("generation")}, {"request", grant_request(original)}});
  for (const std::string name : {"proof_sha", "proof_id", "proof_method", "proof_extra", "proof_generation", "proof_upper", "proof_envelope", "generic_approve"}) {
    SCOPED_TRACE(name); auto view = state().new_view(); state().sync(view);
    ASSERT_TRUE(state().set_connection(view, "runtime:lab")); view->info = stale_info;
    marker(name); ASSERT_TRUE(state().write(view, "grants.approve", grant_request(original)));
    ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
    const auto id = view->operation_id; EXPECT_TRUE(view->uncertain); EXPECT_TRUE(view->rejection.is_null());
    EXPECT_FALSE(state().write(view, "grants.approve", grant_request(original)));
    EXPECT_FALSE(state().set_connection(view, "local"));
    EXPECT_FALSE(state().select_operation(view, {{"connection", "runtime:lab"}, {"operation_id", FederationState::new_uuid()}}));
    EXPECT_EQ(view->operation_id, id); fs::remove(dir.path() / ("control." + name));
    ASSERT_TRUE(state().check_operation(view)); ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
    EXPECT_EQ(view->uncertain, name == "generic_approve");
  }
  EXPECT_EQ(count("grants.approve"), 9);
}

TEST_F(FederationBridge, InvalidCellPreparationKeepsDraftAndAllowsExplicitCorrectedNewIdentity)
{
  auto view = prepared(); const auto draft = view->draft_epoch;
  const auto edit = [&](const Json &value) {
    const auto p = *store().project().project();
    call("project.apply", {{"handle", p.handle}, {"expected_revision", p.revision}, {"commands", Json::array({
      {{"op", "set_cell"}, {"table_id", table_id}, {"record_id", heldout_row}, {"field_id", target_id}, {"value", value}}})}});
    store().project().refresh();
    EXPECT_TRUE(loop.pump_until([&] { return store().project().ready() && store().project().loaded() && !store().project().busy() && store().project().project()->revision == p.revision + 1; }));
  };
  edit(nullptr); ASSERT_TRUE(state().load_rows(view, table_id)); settle(view);
  const auto bad = plan_params(); ASSERT_TRUE(state().prepare(view, bad));
  ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
  EXPECT_FALSE(view->error.empty()); EXPECT_FALSE(view->plan_uncertain); EXPECT_EQ(view->plan_id, io::get_string(bad, "plan_id"));
  EXPECT_EQ(view->draft_epoch, draft); EXPECT_EQ(view->table_id, table_id); EXPECT_TRUE(view->plan.is_null());
  edit(6.0); ASSERT_TRUE(state().load_rows(view, table_id)); settle(view);
  const auto good = plan_params(); ASSERT_TRUE(state().prepare(view, good)); settle(view);
  EXPECT_NE(view->plan_id, io::get_string(bad, "plan_id")); EXPECT_EQ(view->plan.at("plan_id"), good.at("plan_id"));
  EXPECT_EQ(count("datasets.register"), 0); EXPECT_EQ(count("grants.approve"), 0);
}

TEST_F(FederationBridge, LostPreparationReplyKeepsOriginalIdentityUntilExplicitLookup)
{
  auto view = prepared(); marker("hold_prepare"); const auto params = plan_params();
  ASSERT_TRUE(state().prepare(view, params));
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.prepare_held"); }));
  state().detach(view); EXPECT_TRUE(view->plan_uncertain);
  EXPECT_FALSE(state().prepare(view, plan_params())); EXPECT_EQ(view->plan_id, io::get_string(params, "plan_id"));
  release("prepare"); ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "control.prepare_sent"); }));
  EXPECT_TRUE(view->plan.is_null()); ASSERT_TRUE(state().load_plan(view, view->plan_id)); settle(view);
  EXPECT_FALSE(view->plan_uncertain); EXPECT_EQ(view->plan.at("plan_id"), params.at("plan_id"));
  EXPECT_EQ(count("datasets.register"), 0);
}

TEST_F(FederationBridge, InternalOrMismatchedPreparationReplyNeverPermitsAnotherPreparation)
{
  auto view = prepared();
  for (const std::string name : {"prepare_internal", "wrong_prepare"}) {
    SCOPED_TRACE(name); const auto params = plan_params(); marker(name);
    ASSERT_TRUE(state().prepare(view, params)); ASSERT_TRUE(loop.pump_until([&] { return !view->reading(); }));
    EXPECT_TRUE(view->plan_uncertain); EXPECT_TRUE(view->plan.is_null());
    EXPECT_FALSE(state().prepare(view, plan_params())); EXPECT_EQ(view->plan_id, io::get_string(params, "plan_id"));
    fs::remove(dir.path() / ("control." + name)); ASSERT_TRUE(state().load_plan(view, view->plan_id)); settle(view);
    EXPECT_FALSE(view->plan_uncertain); EXPECT_EQ(view->plan.at("plan_id"), params.at("plan_id"));
  }
  EXPECT_EQ(count("datasets.register"), 0);
}

struct FederationLayout { const char *language; int width, height; float scale; const char *name; };
void PrintTo(const FederationLayout &layout, std::ostream *out) { *out << layout.name; }
class FederationMouse : public FederationBridge, public ::testing::WithParamInterface<FederationLayout> {
 protected:
  int clicks = 0, wheels = 0;
  Json viewer, draft; std::shared_ptr<io::Payload> shown;
  uint64_t camera = 0, payload = 0;
  void frame() { f.screen.run_deferred(); f.drv->frame(); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  void wait_text(const std::string &text)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      frame();
      for (const auto &block : f.screen.ui()->blocks()) { for (const auto &w : block->widgets()) {
        if (w.text.find(text) != std::string::npos) { return true; }
      } }
      return false;
    }, 30)) << text;
  }
  void active_display(const std::string &version, int generation)
  {
    ASSERT_NO_FATAL_FAILURE(wait_text(std::string(store().tr("federation.active")) + " " + version + " · " + std::to_string(generation)));
  }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *w = widget(key); return w && w->enabled; }, 30)) << key;
  }
  void reveal(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget(key));
    for (int i = 0; i < 24; ++i) {
      const auto *w = widget(key); const auto clip = w->rect.intersect(w->clip);
      if (std::abs(clip.h - w->rect.h) <= 1 && std::abs(clip.w - w->rect.w) <= 1) { return; }
      wm::Event event; event.type = wm::EventType::Wheel;
      event.x = int(w->clip.cx()); event.y = f.screen.rect().ymax - 1 - int(w->clip.cy());
      event.wheel_y = w->rect.cy() > w->clip.cy() ? -3 : 3;
      ASSERT_TRUE(f.drv->send(event)) << key; ++wheels; frame();
    }
    FAIL() << "Widget cannot be revealed through normal scrolling: " << key;
  }
  void click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(reveal(key)); const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key; ++clicks; frame();
  }
  void tab(const std::string &key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(reveal(key)); const auto *w = widget(key);
    ASSERT_EQ(w->type, ui::WidgetType::Tabs); ASSERT_LT(size_t(index), w->items.size());
    const int x = int(w->rect.x + w->rect.w * (float(index) + .5f) / float(w->items.size()));
    const int y = f.screen.rect().ymax - 1 - int(w->rect.cy());
    ASSERT_TRUE(f.drv->click(x, y)); ++clicks; frame();
  }
  void text(const std::string &key, const std::string &value)
  {
    ASSERT_NO_FATAL_FAILURE(click(key));
#ifdef __APPLE__
    f.drv->key(wm::Key::A, wm::ModOS);
#else
    f.drv->key(wm::Key::A, wm::ModCtrl);
#endif
    auto event = ui::Event::text_input(value); event.time = double(++f.drv->time_ms) / 1000.;
    f.screen.ui()->handle_event(event); frame(); f.drv->key(wm::Key::Enter); frame();
    ASSERT_NE(widget(key), nullptr); EXPECT_EQ(widget(key)->string.value(), value) << key;
  }
  void select(const std::string &key, int index)
  {
    ASSERT_NO_FATAL_FAILURE(click(key)); const ui::Widget *option = nullptr;
    for (const auto &block : f.screen.ui()->blocks()) { for (const auto &w : block->widgets()) {
      if (w.type == ui::WidgetType::MenuItem && w.menu_index == index) { option = &w; }
    } }
    ASSERT_NE(option, nullptr) << key; const auto clip = option->rect.intersect(option->clip);
    ASSERT_FALSE(clip.empty()); ASSERT_TRUE(f.drv->click(int(clip.cx()), f.screen.rect().ymax - 1 - int(clip.cy())));
    ++clicks; frame();
  }
  void start_layout()
  {
    const auto layout = GetParam(); store().set_language(layout.language);
    f.drv = std::make_unique<wmtest::ScreenDriver>(f.screen, layout.width, layout.height, layout.scale);
    auto &area = f.area("a4"); ASSERT_TRUE(area.set_tabs({kEditorFederation, kEditorPython}, 0));
    f.screen.set_maximized(&area); area.set_toolbar_open(false); area.set_sidebar_open(false);
    draft = area.tab(1).save_workspace_state(); draft["source"] = "print('keep federation hidden draft')";
    ASSERT_TRUE(area.tab(1).load_workspace_state(draft)); ASSERT_TRUE(area.tab(1).has_unsaved_changes());
    draft = area.tab(1).save_workspace_state();
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store().viewer().open_payload(shown, "Existing synthetic Viewer result");
    viewer = store().viewer().save_workspace_state(); camera = store().viewer().camera_serial(); payload = store().viewer().payload_serial();
  }
  Json completed(const std::string &method, int expected)
  {
    Json latest; bool observed = loop.pump_until([&] {
      const auto records = call("federation.owner.operations.local", {{"connection", "runtime:lab"}, {"offset", 0}, {"limit", 20}});
      int found = 0; latest = nullptr;
      if (records.is_object()) { for (const auto &record : records.at("operations")) {
        if (record.at("method") == method && record.at("state") == "completed") {
          ++found; const auto &receipt = record.at("receipt");
          if (latest.is_null() || io::get_int(receipt, "generation", 0) > io::get_int(latest, "generation", 0)) { latest = receipt; }
        }
      } }
      frame(); return found == expected;
    }, 30);
    EXPECT_TRUE(observed) << method << " completed count " << expected; return latest;
  }
  void data_flow()
  {
    ASSERT_NO_FATAL_FAILURE(click("federation_connections"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("federation_connection"));
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *w = widget("federation_connection"); return w && w->items.size() == 1; }));
    ASSERT_NO_FATAL_FAILURE(select("federation_connection", 0));
  ASSERT_NO_FATAL_FAILURE(click("federation_owner_info"));
    ASSERT_NO_FATAL_FAILURE(select("federation_table", 0));
  ASSERT_NO_FATAL_FAILURE(click("federation_load_table"));
    ASSERT_NO_FATAL_FAILURE(click("federation_feature/" + feature_id));
  ASSERT_NO_FATAL_FAILURE(click("federation_target/" + target_id));
    ASSERT_NO_FATAL_FAILURE(click("federation_row/" + training_row + "/1"));
  ASSERT_NO_FATAL_FAILURE(click("federation_row/" + heldout_row + "/2"));
    ASSERT_NO_FATAL_FAILURE(click("federation_prepare"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("federation_register"));
    EXPECT_EQ(count("datasets.register"), 0);
  ASSERT_NO_FATAL_FAILURE(click("federation_register"));
    ASSERT_TRUE(completed("datasets.register", 1).is_object()); EXPECT_EQ(clicks, 13);
  }
  void expect_preserved()
  {
    EXPECT_EQ(store().viewer().base_payload(), shown); EXPECT_EQ(store().viewer().camera_serial(), camera);
    EXPECT_EQ(store().viewer().payload_serial(), payload); EXPECT_EQ(store().viewer().save_workspace_state(), viewer);
    EXPECT_EQ(f.area("a4").tab(1).save_workspace_state(), draft); EXPECT_TRUE(f.area("a4").tab(1).has_unsaved_changes());
    EXPECT_TRUE(store().scripts().history().empty()); EXPECT_FALSE(fs::exists(dir.path() / "public-workspaces"));
  }
  void evidence(const std::string &scenario, const std::string &result)
  {
    const auto layout = GetParam(); const std::string start = std::string(layout.language) + " " + std::to_string(layout.width) + "x" + std::to_string(layout.height) +
      " scale=" + std::to_string(layout.scale) + "; a4 maximized Federation Data; project revision1, no selection/plan, owner connection unselected, hidden Python draft, existing Viewer";
    RecordProperty("starting_layout", start); RecordProperty("mouse_clicks", clicks); RecordProperty("wheel_events", wheels); RecordProperty("result", result);
    std::cout << "FEDERATION_UI_EVIDENCE " << Json({{"scenario", scenario}, {"starting_layout", start},
      {"mouse_clicks", clicks}, {"wheel_events", wheels}, {"result", result}, {"scope", "CPU mouse/keyboard events; synthetic provenance; no training/network or OS/GPU evidence"}}).dump() << '\n';
  }
};

TEST_P(FederationMouse, ExplicitMouseFreezeAndRegisterKeepViewerAndHiddenDraft)
{
  ASSERT_NO_FATAL_FAILURE(start_layout());
  ASSERT_NO_FATAL_FAILURE(data_flow()); EXPECT_EQ(count("grants.approve"), 0);
  expect_preserved(); evidence("freeze-register", "two private capsules registered; no consent, training, send or activation; Viewer and hidden draft unchanged");
}

TEST_P(FederationMouse, ConsentHeldoutEvaluationAdmissionExplicitActivationAndRollback)
{
  marker("seed_candidates");
  ASSERT_NO_FATAL_FAILURE(start_layout());
  ASSERT_NO_FATAL_FAILURE(data_flow());
  ASSERT_NO_FATAL_FAILURE(tab("federation_sections", 1));
  ASSERT_NO_FATAL_FAILURE(text("federation_run_id", run_id));
  ASSERT_NO_FATAL_FAILURE(text("federation_coordinator_id", std::string(64, 'a')));
  ASSERT_NO_FATAL_FAILURE(text("federation_participant_id", std::string(64, 'b')));
  ASSERT_NO_FATAL_FAILURE(text("federation_max_rounds", "2"));
  ASSERT_NO_FATAL_FAILURE(text("federation_steps", "2"));
  ASSERT_NO_FATAL_FAILURE(text("federation_learning_rate", "0.01"));
  ASSERT_NO_FATAL_FAILURE(click("federation_approve"));
  const auto grant_op = completed("grants.approve", 1); ASSERT_TRUE(grant_op.is_object());
  const auto grant = grant_op.at("result"); const auto spec_sha = io::get_string(grant, "spec_sha256");
  EXPECT_EQ(count("synthetic_candidate_seed"), 1);
  ASSERT_NO_FATAL_FAILURE(click("federation_grants"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("federation_revoke/" + io::get_string(grant, "grant_id")));
  ASSERT_NO_FATAL_FAILURE(click("federation_audit"));
  const auto audit = call("federation.owner.audit.list", {{"connection", "runtime:lab"}, {"offset", 0}, {"limit", 20}});
  ASSERT_EQ(audit.at("items").size(), 2u);
  for (const auto &item : audit.at("items")) {
    EXPECT_EQ(item.at("state"), "prepared"); EXPECT_FALSE(item.contains("payload"));
    const auto id = io::get_string(item, "update_id");
  ASSERT_NO_FATAL_FAILURE(wait_text(id.substr(0, 8) + "…" + id.substr(id.size() - 8)));
  }
  ASSERT_NO_FATAL_FAILURE(tab("federation_sections", 2));
  ASSERT_NO_FATAL_FAILURE(click("federation_candidate"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("federation_threshold/Pressure")); EXPECT_TRUE(widget("federation_threshold/Pressure")->string.value().empty());
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("", 0));
  const auto models = [&] { return call("federation.owner.models.list", {{"connection", "runtime:lab"}, {"spec_sha256", spec_sha}}); };
  auto current = models(); EXPECT_TRUE(current.at("active_version").is_null()); EXPECT_EQ(current.at("generation"), 0);
  ASSERT_TRUE(loop.pump_until([&] { frame(); return widget("federation_prepare_evaluation") && widget("federation_threshold/Pressure"); }));
  EXPECT_FALSE(widget("federation_prepare_evaluation")->enabled); EXPECT_TRUE(widget("federation_threshold/Pressure")->string.value().empty());
  ASSERT_NO_FATAL_FAILURE(text("federation_threshold/Pressure", "0"));
  ASSERT_NO_FATAL_FAILURE(click("federation_prepare_evaluation"));
  const auto first_plan = completed("evaluations.prepare", 1); ASSERT_TRUE(first_plan.is_object());
  EXPECT_EQ(first_plan.at("result").at("plan").at("thresholds")[0].at("max_rmse"), 0.0);
  EXPECT_TRUE(first_plan.at("result").at("plan").at("active").at("version").is_null());
  EXPECT_EQ(first_plan.at("result").at("plan").at("active").at("generation"), 0);
  ASSERT_NO_FATAL_FAILURE(click("federation_evaluate")); const auto first_eval = completed("evaluations.evaluate", 1); ASSERT_TRUE(first_eval.is_object());
  EXPECT_EQ(first_eval.at("result").at("state"), "passed");
  EXPECT_EQ(first_eval.at("result").at("metrics").at("candidate")[0].at("rmse"), 0.0);
  EXPECT_EQ(first_eval.at("result").at("metrics").at("baseline")[0].at("rmse"), 6.0);
  EXPECT_TRUE(models().at("versions").empty());
  ASSERT_NO_FATAL_FAILURE(click("federation_admit"));
  const auto first_admit = completed("models.admit", 1); ASSERT_TRUE(first_admit.is_object()); EXPECT_EQ(first_admit.at("result").at("version"), "v1");
  current = models(); EXPECT_TRUE(current.at("active_version").is_null()); EXPECT_EQ(current.at("generation"), 0);
  frame(); EXPECT_EQ(widget("federation_activate/v1"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("", 0));
  ASSERT_NO_FATAL_FAILURE(click("federation_activate/v1"));
  ASSERT_TRUE(completed("models.activate", 1).is_object());
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("v1", 1));
  current = models(); EXPECT_EQ(current.at("active_version"), "v1"); EXPECT_EQ(current.at("generation"), 1);
  ASSERT_NO_FATAL_FAILURE(text("federation_round", "2"));
  ASSERT_NO_FATAL_FAILURE(click("federation_candidate"));
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("v1", 1));
  ASSERT_NO_FATAL_FAILURE(text("federation_threshold/Pressure", "0"));
  ASSERT_NO_FATAL_FAILURE(click("federation_prepare_evaluation")); const auto second_plan = completed("evaluations.prepare", 2); ASSERT_TRUE(second_plan.is_object());
  EXPECT_EQ(second_plan.at("result").at("plan").at("active").at("version"), "v1");
  EXPECT_EQ(second_plan.at("result").at("plan").at("active").at("generation"), 1);
  ASSERT_NO_FATAL_FAILURE(click("federation_evaluate")); const auto second_eval = completed("evaluations.evaluate", 2); ASSERT_TRUE(second_eval.is_object());
  EXPECT_EQ(second_eval.at("result").at("state"), "passed");
  EXPECT_EQ(second_eval.at("result").at("metrics").at("baseline")[0].at("rmse"), 0.0);
  ASSERT_NO_FATAL_FAILURE(click("federation_admit")); ASSERT_TRUE(completed("models.admit", 2).is_object());
  current = models(); EXPECT_EQ(current.at("active_version"), "v1"); EXPECT_EQ(current.at("generation"), 1);
  ASSERT_EQ(current.at("versions").size(), 2u); EXPECT_NE(current.at("versions")[0].at("model").at("sha256"), current.at("versions")[1].at("model").at("sha256"));
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("v1", 1));
  ASSERT_NO_FATAL_FAILURE(click("federation_activate/v2"));
  ASSERT_TRUE(completed("models.activate", 2).is_object());
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("v2", 2));
  current = models(); EXPECT_EQ(current.at("active_version"), "v2"); EXPECT_EQ(current.at("generation"), 2);
  ASSERT_NO_FATAL_FAILURE(click("federation_activate/v1")); ASSERT_TRUE(completed("models.activate", 3).is_object());
  ASSERT_NO_FATAL_FAILURE(click("federation_models"));
  ASSERT_NO_FATAL_FAILURE(active_display("v1", 3));
  current = models(); EXPECT_EQ(current.at("active_version"), "v1"); EXPECT_EQ(current.at("generation"), 3);
  ASSERT_NO_FATAL_FAILURE(tab("federation_sections", 1));
  ASSERT_NO_FATAL_FAILURE(click("federation_grants"));
  ASSERT_NO_FATAL_FAILURE(click("federation_revoke/" + io::get_string(grant, "grant_id"))); ASSERT_TRUE(completed("grants.revoke", 1).is_object());
  ASSERT_NO_FATAL_FAILURE(click("federation_grants"));
  ASSERT_NO_FATAL_FAILURE(click("federation_audit"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *w = widget("federation_revoke/" + io::get_string(grant, "grant_id")); return w && !w->enabled; }));
  const auto grants = call("federation.owner.grants.list", {{"connection", "runtime:lab"}, {"offset", 0}, {"limit", 20}});
  ASSERT_EQ(grants.at("items").size(), 1u); EXPECT_FALSE(grants.at("items")[0].at("active").get<bool>());
  EXPECT_EQ(call("federation.owner.audit.list", {{"connection", "runtime:lab"}, {"offset", 0}, {"limit", 20}}).at("items"), audit.at("items"));
  EXPECT_EQ(clicks, 50); EXPECT_EQ(count("models.activate"), 3); EXPECT_EQ(count("synthetic_candidate_seed"), 1);
  expect_preserved(); evidence("consent-evaluation-versions", "explicit consent, two audited synthetic candidates, empty threshold explicitly entered as0, heldout gates passed; Admit leaves active pointer unchanged, explicit v1 activation/v2 activation/v1 rollback generations1/2/3; grant revoked, audit retained; Viewer and hidden draft unchanged");
}
INSTANTIATE_TEST_SUITE_P(LanguagesWidthsAndScales, FederationMouse, ::testing::Values(
  FederationLayout{"en", 1440, 1200, 1, "EnglishWide1x"}, FederationLayout{"zh_CN", 1000, 1200, 1, "ChineseNarrow1x"},
  FederationLayout{"en", 2160, 1800, 1.5f, "EnglishWide1p5x"}, FederationLayout{"zh_CN", 2000, 2400, 2, "ChineseNarrow2x"}),
  [](const ::testing::TestParamInfo<FederationLayout> &info) { return info.param.name; });
}  // namespace
}  // namespace stk::app
