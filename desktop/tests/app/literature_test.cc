/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/app_store.hh"
#include "stk/app/literature_state.hh"
#include "stk/app/literature_contract.hh"
#include "stk/bridge/schema.hh"
#include "stk/bridge/python.hh"
#include "stk/bridge/process.hh"
#include "stk/core/sha256.hh"
#include "../bridge/support.hh"
#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
const std::string id = "00000000-0000-4000-8000-000000000001";
const std::string corpus = "local_00000000000040008000000000000001";
TEST(LiteratureState, SyncDetachAndOtherViewsPreserveDraftsAndOriginalIdsWithoutDispatch)
{
  AppStore store; auto &state = store.literature(); auto a = state.new_view(), b = state.new_view();
  a->operation_id = id; a->uncertain = true; a->originals[id].action = "import.commit";
  b->values["private-draft"] = "keep"; a->values["pages.render"] = {{"old", true}};
  int invalidated = 0; a->on_content_invalidated = [&] { ++invalidated; };
  state.sync(a); state.sync(b); state.pump(a); state.detach(a);
  EXPECT_FALSE(state.supported()); EXPECT_EQ(a->operation_id, id); EXPECT_TRUE(a->uncertain);
  EXPECT_EQ(a->originals.at(id).action, "import.commit"); EXPECT_EQ(b->values.at("private-draft"), "keep");
  EXPECT_FALSE(a->values.contains("pages.render")); EXPECT_EQ(invalidated, 1);
  EXPECT_FALSE(state.read(a, "search")); EXPECT_FALSE(state.act(a, "models.policy.set", Json::object()));
}
TEST(LiteratureState, ReceiptAndRequestKeepExactActionHashAndNumericTokens)
{
  LiteratureState::Expected e; e.action = "import.commit"; e.request_sha256 = std::string(64, 'a');
  Json op = {{"operation_id", id}, {"action", e.action}, {"request_sha256", e.request_sha256},
      {"state", "running"}, {"result_sha256", nullptr}, {"error", nullptr}};
  EXPECT_TRUE(LiteratureState::operation_matches(op, id, &e));
  for (const auto &change : std::vector<Json>{{{"action", "import.review"}}, {{"request_sha256", std::string(64, 'b')}},
      {{"state", "completed"}}, {{"extra", true}}, {{"result_sha256", std::string(64, 'b')}}}) {
    auto bad = op; bad.update(change); EXPECT_FALSE(LiteratureState::operation_matches(bad, id, &e));
  }
  EXPECT_NE(LiteratureState::request_sha256("dense.build", {{"operation_id", id}, {"timeout", 1}}),
      LiteratureState::request_sha256("dense.build", {{"operation_id", id}, {"timeout", 1.0}}));
  EXPECT_NE(LiteratureState::checksum({{"x", -0.0}}), LiteratureState::checksum({{"x", 0.0}}));
  const auto &shape = bridge::ProtocolSchema::embedded().resolved("#/$defs/methods/literature.dense.build/params");
  Json params = {{"operation_id", id}, {"corpus_id", corpus}, {"expected_generation", 0.0}, {"encoder_generation", 0}};
  ASSERT_TRUE(io::check_value(params, shape).empty()); EXPECT_FALSE(literature_token_types(params, shape));
  params["expected_generation"] = 0; EXPECT_TRUE(literature_shape(params, shape));
}

// The service is real. Markers delay or corrupt selected wire replies only;
// synthetic negative replies are never counted as model/parser acceptance.
constexpr const char *script = R"PY(
from pathlib import Path
import json,sys,time,threading
control=Path(sys.argv.pop(1))
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.literature import LiteratureService
from suan.desktop_bridge.__main__ import main
calls=LiteratureService.call
lock=threading.Lock()
def counted(self,action,params):
    with lock,control.with_suffix('.calls').open('a') as f:f.write(action+'\n')
    return calls(self,action,params)
LiteratureService.call=counted
send=Bridge.send
held=set()
def controlled(self,message,method=None):
    if 'result' in message:
        key={'literature.import.review':'review','literature.operations.result':'result','literature.corpora.info':'info'}.get(method)
        if key and control.with_suffix('.hold_'+key).exists() and key not in held:
            held.add(key);control.with_suffix('.held_'+key).write_text('held')
            until=time.monotonic()+35
            while not control.with_suffix('.release_'+key).exists() and time.monotonic()<until:time.sleep(.005)
        if method=='literature.corpora.info' and control.with_suffix('.wrong_database').exists():
            message['result']['database_id']='00000000-0000-4000-8000-000000000099'
    send(self,message,method)
Bridge.send=controlled
main()
)PY";
class LiteratureBridge : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"literature-controller"}; bridge::test::ManualLoop loop; AppStore store;
  std::unique_ptr<bridge::Client> client;
  LiteratureState &state() { return store.literature(); }
  void marker(const std::string &name) { std::ofstream(dir.path() / ("control." + name)) << "marker"; }
  bool exists(const std::string &name) { return std::filesystem::exists(dir.path() / ("control." + name)); }
  int calls(const std::string &action)
  {
    std::ifstream input(dir.path() / "control.calls"); int n = 0; std::string line;
    while (std::getline(input, line)) { n += line == action; } return n;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *p = std::getenv("STK_BRIDGE_TEST_PYTHON"); p && *p) { python = p; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    ASSERT_FALSE(python.empty()); std::ofstream(dir.path() / "bridge.py") << script;
    bridge::ClientOptions options; options.executor = loop.executor(); options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = dir.str() + "/no-runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true; options.resume_transfers = false;
    options.command = {python,"-u",dir.str()+"/bridge.py",dir.str()+"/control","--stdio","--strict","--state-dir",options.state_dir,"--cache-dir",options.cache_dir};
    client = bridge::Client::create(options); ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60));
    loop.run_ready(); store.set_bridge(client.get());
  }
  void TearDown() override
  {
    for (const auto key : {"review","result","info"}) { marker(std::string("release_") + key); }
    store.set_bridge(nullptr); if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
  void settle(const LiteratureState::ViewPtr &view)
  {
    ASSERT_TRUE(loop.pump_until([&] { state().sync(view); state().pump(view); return !view->reading() && view->follow_until == 0; }, 45));
    ASSERT_TRUE(view->error.empty()) << view->error;
  }
  std::string create(const LiteratureState::ViewPtr &view)
  {
    EXPECT_TRUE(state().act(view,"corpora.create",{{"name","Owned native fixture"}})); settle(view);
    EXPECT_TRUE(view->values.contains("corpora.create"))
        << "Create operation state=" << io::get_string(view->operation,"state")
        << "; error_code=" << (view->operation.contains("error") && view->operation.at("error").is_object() ?
            io::get_string(view->operation.at("error"),"code") : std::string());
    if (!view->values.contains("corpora.create")) { return {}; }
    const auto id = io::get_string(view->values.at("corpora.create"),"corpus_id"); EXPECT_TRUE(state().set_corpus(view,id));
    EXPECT_TRUE(state().read(view,"corpora.info",{{"corpus_id",id}})); settle(view); return id;
  }
  Json review_params(const std::string &scope, const std::string &title = "Owned")
  {
    // Import review/commit inspect frozen bytes, not a scientific parser claim.
    const auto file = dir.path() / "owned.pdf";
    if (!std::filesystem::exists(file)) { std::ofstream(file) << "%PDF-1.7\nSelf-authored byte-inspection fixture\n%%EOF\n"; }
    return {{"corpus_id",scope},{"source",file.string()},{"document_id",id},{"title",title},
      {"authorization",{{"basis","self_authored"},{"evidence","Self-authored software test"},{"approved_by","Fixture owner"}}}};
  }
  void commit(const LiteratureState::ViewPtr &view, const std::string &scope)
  {
    ASSERT_TRUE(state().act(view,"import.review",review_params(scope))); settle(view);
    ASSERT_TRUE(view->values.contains("import.review")); const auto review = view->operation_id;
    const auto sha = LiteratureState::checksum(view->values.at("import.review"));
    ASSERT_TRUE(state().act(view,"import.commit",{{"review_id",review},{"review_sha256",sha}})); settle(view);
    ASSERT_TRUE(view->values.contains("import.commit"));
  }
};
TEST_F(LiteratureBridge, StartupSyncReopenAndDetachDoNotDispatchOrCreateALibrary)
{
  auto a=state().new_view(),b=state().new_view(); state().sync(a); state().sync(b); state().pump(a); state().detach(a);
  EXPECT_TRUE(state().supported()); EXPECT_FALSE(std::filesystem::exists(dir.path()/"bridge/literature")); EXPECT_EQ(calls("info"),0);
  EXPECT_TRUE(state().read(b,"info")); settle(b); EXPECT_EQ(calls("info"),1);
  EXPECT_FALSE(std::filesystem::exists(dir.path()/"bridge/literature"));
}
TEST_F(LiteratureBridge, ActualCorpusKeepsCallerUuidAndPassivelyReopensWithoutReissue)
{
  auto v=state().new_view(); const auto scope=create(v); ASSERT_FALSE(scope.empty()); const auto original=v->operation_id;
  EXPECT_EQ(calls("corpora.create"),1); state().detach(v); state().sync(v); state().pump(v); EXPECT_EQ(calls("corpora.create"),1);
  EXPECT_EQ(v->operation_id,original); ASSERT_TRUE(state().check_operation(v)); settle(v);
  EXPECT_EQ(io::get_string(v->operation,"state"),"completed"); EXPECT_EQ(calls("corpora.create"),1);
}
TEST_F(LiteratureBridge, QueryDraftDoesNotInvalidateAnExplicitImportReview)
{
  auto v=state().new_view(); const auto scope=create(v); marker("hold_review");
  ASSERT_TRUE(state().act(v,"import.review",review_params(scope)));
  ASSERT_TRUE(loop.pump_until([&] {return exists("held_review");})); state().invalidate_query_draft(v); marker("release_review"); settle(v);
  EXPECT_TRUE(v->values.contains("import.review")); EXPECT_EQ(calls("import.review"),1);
}
TEST_F(LiteratureBridge, ChangedImportDraftCannotAdoptHeldReceiptOrCommitHistoricalReview)
{
  auto v=state().new_view(); const auto scope=create(v); marker("hold_review");
  ASSERT_TRUE(state().act(v,"import.review",review_params(scope))); const auto original=v->operation_id;
  ASSERT_TRUE(loop.pump_until([&] {return exists("held_review");})); state().invalidate_import_draft(v); marker("release_review"); settle(v);
  EXPECT_FALSE(v->values.contains("import.review")); EXPECT_TRUE(v->uncertain); EXPECT_EQ(v->operation_id,original);
  ASSERT_TRUE(state().check_operation(v)); settle(v); ASSERT_TRUE(state().load_result(v)); settle(v);
  EXPECT_FALSE(v->historical_result.is_null()); EXPECT_FALSE(v->values.contains("import.review"));
  EXPECT_FALSE(state().act(v,"import.commit",{{"review_id",original},{"review_sha256",LiteratureState::checksum(v->historical_result)}}));
  EXPECT_EQ(calls("import.review"),1); EXPECT_EQ(calls("import.commit"),0);
}
TEST_F(LiteratureBridge, SameBridgeDetachReattachEpochRejectsHeldReplyButPreservesOriginalObservation)
{
  auto v=state().new_view(); const auto scope=create(v); marker("hold_review"); ASSERT_TRUE(state().act(v,"import.review",review_params(scope)));
  const auto original=v->operation_id; ASSERT_TRUE(loop.pump_until([&] {return exists("held_review");}));
  store.set_bridge(nullptr); store.set_bridge(client.get()); state().sync(v); marker("release_review");
  ASSERT_TRUE(loop.pump_until([&] {return !v->reading();})); EXPECT_EQ(v->operation_id,original); EXPECT_FALSE(v->values.contains("import.review"));
  ASSERT_TRUE(state().check_operation(v)); settle(v); EXPECT_EQ(io::get_string(v->operation,"state"),"completed"); EXPECT_EQ(calls("import.review"),1);
}
TEST_F(LiteratureBridge, ProjectScopeChangesDoNotBecomeLibraryAuthorityOrLoseDrafts)
{
  auto v=state().new_view(); const auto scope=create(v); ASSERT_TRUE(state().set_scopes(v,{scope}));
  v->values["private-draft"]="keep"; const auto epoch=v->corpus_epoch,life=v->lifetime_epoch;
  store.invalidate_project_scope(); state().sync(v);
  EXPECT_EQ(v->corpus_epoch,epoch); EXPECT_EQ(v->lifetime_epoch,life); EXPECT_EQ(v->values.at("private-draft"),"keep");
  EXPECT_EQ(io::get_string(*state().corpus_info(scope),"corpus_id"),scope);
}
TEST_F(LiteratureBridge, DatabaseReplacementCannotRelabelEitherTabsCachedContent)
{
  auto a=state().new_view(),b=state().new_view(); const auto scope=create(a);
  ASSERT_TRUE(state().set_scopes(a,{scope})); ASSERT_TRUE(state().set_scopes(b,{scope}));
  a->values["pages.render"]={{"synthetic-negative-cache",true}}; b->values["search"]={{"synthetic-negative-cache",true}};
  b->values["import-draft"]="keep"; int invalidated=0; a->on_content_invalidated=[&] {++invalidated;}; b->on_content_invalidated=[&] {++invalidated;};
  marker("wrong_database"); ASSERT_TRUE(state().read(a,"corpora.info",{{"corpus_id",scope}}));
  ASSERT_TRUE(loop.pump_until([&] {return !a->reading();})); EXPECT_EQ(a->error,"literature.invalid_response");
  EXPECT_FALSE(a->values.contains("pages.render")); EXPECT_FALSE(b->values.contains("search")); EXPECT_EQ(b->values.at("import-draft"),"keep");
  EXPECT_GE(invalidated,2); EXPECT_EQ(state().corpus_info(scope),nullptr);
}
TEST_F(LiteratureBridge, ExplicitRevokeClearsAllTabsBeforeRpcAndKeepsTheOriginalCompletion)
{
  auto a=state().new_view(),b=state().new_view(); const auto scope=create(a); commit(a,scope);
  ASSERT_FALSE(a->version_id.empty()); ASSERT_TRUE(state().set_scopes(a,{scope})); ASSERT_TRUE(state().set_scopes(b,{scope}));
  a->values["pages.render"]={{"synthetic-negative-cache",true}}; b->values["search"]={{"synthetic-negative-cache",true}};
  b->values["query-draft"]="keep"; ASSERT_TRUE(state().act(a,"versions.revoke",{{"corpus_id",scope},{"version_id",a->version_id}}));
  EXPECT_FALSE(a->values.contains("pages.render")); EXPECT_FALSE(b->values.contains("search")); EXPECT_EQ(b->values.at("query-draft"),"keep");
  const auto original=a->operation_id; settle(a); EXPECT_EQ(a->operation_id,original); ASSERT_TRUE(a->values.contains("versions.revoke"));
  EXPECT_FALSE(a->values.at("versions.revoke").at("receipt").at("active").get<bool>()); EXPECT_EQ(calls("versions.revoke"),1);
}
TEST_F(LiteratureBridge, InterpreterFieldsAndUnpublishedActionsAreRefusedBeforeRpc)
{
  auto v=state().new_view(); state().sync(v);
  EXPECT_FALSE(state().act(v,"encoder.review",{{"assets","/tmp/assets"},{"python","/tmp/arbitrary"}}));
  EXPECT_FALSE(state().act(v,"models.local.start",{{"entry","owned"}})); EXPECT_EQ(calls("encoder.review"),0);
  EXPECT_FALSE(state().read(v,"operations.result",{{"operation_id",id},{"expected_request_sha256",std::string(64,'a')}}));
}
TEST_F(LiteratureBridge, OriginalNotFoundKeepsTheUnknownIdAndCannotBecomeANewAttempt)
{
  auto v=state().new_view(); state().sync(v); v->operation_id=id; v->uncertain=true;
  v->originals[id].action="corpora.create"; v->originals[id].request_sha256=std::string(64,'a');
  ASSERT_TRUE(state().check_operation(v)); settle(v); EXPECT_EQ(v->operation_id,id); EXPECT_TRUE(v->uncertain);
  EXPECT_FALSE(state().load_result(v)); EXPECT_FALSE(state().act(v,"corpora.create",{{"operation_id",id},{"name","Never reissue"}}));
  state().sync(v);state().pump(v);EXPECT_EQ(calls("operations.get"),1);EXPECT_EQ(calls("corpora.create"),0);
}
TEST_F(LiteratureBridge, OlderResultCannotReplaceANewerSameActionEvenWithoutADraftEdit)
{
  auto v=state().new_view(); const auto scope=create(v); marker("hold_result");
  ASSERT_TRUE(state().act(v,"import.review",review_params(scope,"Old review")));
  ASSERT_TRUE(loop.pump_until([&] {state().pump(v);return exists("held_result");})); const auto old=v->operation_id;
  ASSERT_TRUE(state().act(v,"import.review",review_params(scope,"New review"))); const auto current=v->operation_id; EXPECT_NE(old,current);
  marker("release_result"); settle(v); ASSERT_TRUE(v->values.contains("import.review"));
  EXPECT_EQ(v->values.at("import.review").at("title"),"New review");EXPECT_EQ(v->operation_id,current);EXPECT_EQ(calls("import.review"),2);
}
TEST_F(LiteratureBridge, DetachedHistoricalReviewCannotRestoreCurrentCommitAuthority)
{
  auto v=state().new_view();const auto scope=create(v);ASSERT_TRUE(state().act(v,"import.review",review_params(scope)));settle(v);
  ASSERT_TRUE(v->values.contains("import.review"));const auto original=v->operation_id;const auto review_sha=LiteratureState::checksum(v->values.at("import.review"));
  state().detach(v);state().sync(v);ASSERT_TRUE(state().load_result(v));settle(v);
  EXPECT_FALSE(v->historical_result.is_null());EXPECT_FALSE(v->values.contains("import.review"));
  EXPECT_FALSE(state().act(v,"import.commit",{{"review_id",original},{"review_sha256",review_sha}}));EXPECT_EQ(calls("import.commit"),0);
}
}  // namespace
}  // namespace stk::app
