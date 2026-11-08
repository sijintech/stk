/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/app_store.hh"
#include "stk/app/literature_state.hh"
#include "stk/app/literature_contract.hh"
#include "stk/app/literature_page.hh"
#include "stk/app/jobs_state.hh"
#include "stk/bridge/schema.hh"
#include "stk/bridge/python.hh"
#include "stk/bridge/process.hh"
#include "stk/core/sha256.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"
#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include <cmath>
#include <iostream>
#include <thread>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <vector>

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
import json,sys,time,threading,os
control=Path(sys.argv.pop(1))
def crash_when_explicitly_requested():
    while True:
        marker=control.with_suffix('.crash')
        if marker.exists():
            marker.unlink();os._exit(7)
        time.sleep(.01)
threading.Thread(target=crash_when_explicitly_requested,daemon=True).start()
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
  bridge::test::TempDir dir{"literature-controller"}; bridge::test::ManualLoop loop;
  wmtest::AppFixture fixture{"en", 1, 1600, 1100}; AppStore &store = fixture.shell->store();
  std::unique_ptr<bridge::Client> client;
  virtual const char *service_script() const { return script; }
  virtual void service_environment(bridge::ClientOptions &) const {}
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
    ASSERT_FALSE(python.empty()); std::ofstream(dir.path() / "bridge.py") << service_script();
    bridge::ClientOptions options; options.executor = loop.executor(); options.python.configured = python;
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT; options.env["STK_STATE_DIR"] = dir.str() + "/no-runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true; options.resume_transfers = false;
    service_environment(options);
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
TEST(LiteratureEditor, PortableWorkspaceRestoresOnlyQueryAndScopesAndRejectsAuthorityAtomically)
{
  EditorRegistry registry; register_builtin_editors(registry);
  auto first = registry.create(kEditorLiterature), second = registry.create(kEditorLiterature);
  ASSERT_TRUE(first); ASSERT_TRUE(second);
  auto saved = first->save_workspace_state(); saved["query"] = "polarization 极化";
  saved["corpus"] = corpus; saved["scopes"] = Json::array({corpus}); saved["section"] = 1;
  ASSERT_TRUE(first->load_workspace_state(saved)); EXPECT_TRUE(first->has_unsaved_changes());
  ASSERT_TRUE(second->load_workspace_state(first->save_workspace_state()));
  EXPECT_EQ(second->save_workspace_state(), saved);
  for (const auto &change : std::vector<Json>{{{"authorization", true}}, {{"source", "/private.pdf"}},
      {{"assets", "/private-model"}}, {{"operation_id", id}}, {{"version", 1.0}}, {{"section", true}},
      {{"query", std::string(4097, 'x')}}, {{"corpus", "wrong"}}, {{"scopes", Json::array({corpus, corpus})}}}) {
    auto bad = saved; bad.update(change);
    EXPECT_FALSE(second->load_workspace_state(bad)); EXPECT_EQ(second->save_workspace_state(), saved);
  }
  EXPECT_FALSE(second->load_state({{"version", 1.0}, {"section", 0}}));
}

class LiteratureMouse : public LiteratureBridge, public ::testing::WithParamInterface<bool> {
 protected:
  int clicks = 0, wheels = 0;
  void SetUp() override
  {
    LiteratureBridge::SetUp();
    if (GetParam()) {
      fixture.shell->set_language("zh_CN"); fixture.drv->ctx.rect = {0, 0, 1000, 1200};
    }
    frame();
  }
  void frame() { fixture.screen.run_deferred(); fixture.drv->frame(); }
  const ui::Widget *widget(const std::string &key) const { return fixture.screen.ui()->find(key); }
  void wait_widget(const std::string &key)
  {
    ASSERT_TRUE(loop.pump_until([&] { frame(); const auto *w = widget(key); return w && w->enabled; }, 45)) << key;
  }
  void click(const std::string &key)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget(key));
    bool visible = false;
    for (int i = 0; i < 30; ++i) {
      const auto *w = widget(key); const auto clipped = w->rect.intersect(w->clip);
      if (std::abs(clipped.h - w->rect.h) <= 1 && std::abs(clipped.w - w->rect.w) <= 1) { visible = true; break; }
      wm::Event e; e.type = wm::EventType::Wheel; e.x = int(w->clip.cx());
      e.y = fixture.screen.rect().ymax - 1 - int(w->clip.cy()); e.wheel_y = w->rect.cy() > w->clip.cy() ? -3 : 3;
      ASSERT_TRUE(fixture.drv->send(e)); ++wheels; frame();
    }
    ASSERT_TRUE(visible) << key;
    const auto [x, y] = fixture.widget_center(key); ASSERT_TRUE(fixture.drv->click(x, y)); ++clicks; frame();
  }
  void section(int index)
  {
    ASSERT_NO_FATAL_FAILURE(wait_widget("literature_sections")); const auto *w = widget("literature_sections");
    const int x = int(w->rect.x + w->rect.w * (index + .5f) / 4);
    const int y = fixture.screen.rect().ymax - 1 - int(w->rect.cy());
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
    auto e = ui::Event::text_input(value); e.time = double(++fixture.drv->time_ms) / 1000.;
    fixture.screen.ui()->handle_event(e); frame(); fixture.drv->key(wm::Key::Enter); frame();
    ASSERT_NE(widget(key), nullptr); EXPECT_EQ(widget(key)->string.value(), value);
  }
  EditorArea *literature_area()
  {
    for (auto *a : fixture.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(a);
      if (area && area->editor().type().id == kEditorLiterature) { return area; }
    }
    return nullptr;
  }
};

TEST_P(LiteratureMouse, OneClickEntryIsPassiveAndPreservesViewerAndHiddenPythonDraft)
{
  auto &bottom = fixture.area("a4"); ASSERT_TRUE(bottom.set_tabs({kEditorLogs, kEditorPython}, 0));
  auto hidden = bottom.tab(1).save_workspace_state(); hidden["source"] = "print('keep exact hidden literature draft')";
  ASSERT_TRUE(bottom.tab(1).load_workspace_state(hidden));
  store.viewer().set_auto_evaluate(false); store.viewer().prefetch_neighbours = false;
  auto payload = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  store.viewer().open_payload(payload, "Public literature navigation fixture");
  ASSERT_TRUE(loop.pump_until([&] { store.viewer().pump(); return !store.viewer().presets().empty() &&
      store.viewer().catalog().is_object() && store.viewer().colormaps(); }));
  const auto viewer = store.viewer().save_workspace_state();
  const auto camera = store.viewer().camera_serial(), serial = store.viewer().payload_serial(); frame();
  ASSERT_NO_FATAL_FAILURE(click("tool_literature")); ASSERT_NE(literature_area(), nullptr);
  EXPECT_EQ(clicks, 1); EXPECT_EQ(wheels, 0); EXPECT_EQ(calls("info"), 0); EXPECT_EQ(calls("encoder.info"), 0);
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "bridge/literature"));
  EXPECT_EQ(bottom.tab(1).save_workspace_state(), hidden); EXPECT_TRUE(bottom.tab(1).has_unsaved_changes());
  EXPECT_EQ(store.viewer().save_workspace_state(), viewer); EXPECT_EQ(store.viewer().base_payload(), payload);
  EXPECT_EQ(store.viewer().camera_serial(), camera); EXPECT_EQ(store.viewer().payload_serial(), serial);
  std::cout << "LITERATURE_ENTRY layout=" << (GetParam() ? "zh_CN/1000x1200" : "en/1600x1100")
            << " scale=1 clicks=" << clicks << " wheels=" << wheels << " rpc=0 preserved=true\n";
  ASSERT_NO_FATAL_FAILURE(click("literature_refresh"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return calls("info") == 1 && calls("encoder.info") == 1; }));
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "bridge/literature"));
}

TEST_P(LiteratureMouse, OldReviewButtonCannotApproveANewerReviewAndHideKeepsLocalDrafts)
{
  ASSERT_NO_FATAL_FAILURE(click("tool_literature"));
  ASSERT_NO_FATAL_FAILURE(section(1));
  ASSERT_NO_FATAL_FAILURE(text("literature_name", "Owned UI library"));
  ASSERT_NO_FATAL_FAILURE(click("literature_create"));
  ASSERT_NO_FATAL_FAILURE(click("literature_created"));
  const auto source = dir.path() / "ui-owned.pdf";
  std::ofstream(source) << "%PDF-1.7\nSelf-authored UI byte-inspection fixture\n%%EOF\n";
  ASSERT_NO_FATAL_FAILURE(text("literature_source", source.string()));
  ASSERT_NO_FATAL_FAILURE(text("literature_title", "Owned UI document"));
  ASSERT_NO_FATAL_FAILURE(text("literature_evidence", "Self-authored public software fixture"));
  ASSERT_NO_FATAL_FAILURE(text("literature_approved_by", "Fixture owner"));
  ASSERT_NO_FATAL_FAILURE(click("literature_authorized"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_import_review"));
  ASSERT_NO_FATAL_FAILURE(click("literature_import_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_import_commit"));
  const auto old_commit = widget("literature_import_commit")->on_click;
  std::ofstream(source, std::ios::app) << "% A different set of reviewed bytes\n";
  ASSERT_NO_FATAL_FAILURE(click("literature_import_review"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_import_commit"));
  EXPECT_EQ(calls("import.review"), 2); old_commit(); frame();
  EXPECT_EQ(calls("import.commit"), 0);
  ASSERT_NE(widget("literature_import_commit"), nullptr);
  EXPECT_TRUE(widget("literature_import_commit")->enabled); // Accepted writes are synchronously busy before any queued reply.
  ASSERT_NO_FATAL_FAILURE(click("literature_import_commit"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_index")); EXPECT_EQ(calls("import.commit"), 1);
  auto *area = literature_area(); ASSERT_NE(area, nullptr);
  const int selected = area->active_tab(); const auto before = area->editor().save_workspace_state();
  ASSERT_TRUE(area->add_tab(kEditorLogs)); area->set_active_tab(area->tab_count() - 1); frame();
  area->set_active_tab(selected); frame();
  EXPECT_EQ(area->editor().save_workspace_state(), before);
  ASSERT_NE(widget("literature_source"), nullptr);
  EXPECT_EQ(widget("literature_source")->string.value(), source.string());
  EXPECT_EQ(widget("literature_title")->string.value(), "Owned UI document");
  EXPECT_FALSE(widget("literature_authorized")->boolean.value());
  EXPECT_EQ(calls("import.review"), 2); EXPECT_EQ(calls("import.commit"), 1);
  std::cout << "LITERATURE_IMPORT layout=" << (GetParam() ? "zh_CN/1000x1200" : "en/1600x1100")
            << " scale=1 clicks=" << clicks << " wheels=" << wheels << " review=2 commit=1 stale_approval_rejected=true\n";
}

TEST_P(LiteratureMouse, ActiveTextSurvivesCorpusInvalidationAndBridgeReattachmentWithoutDispatch)
{
  auto v = state().new_view(); const auto scope = create(v); ASSERT_FALSE(scope.empty());
  ASSERT_NO_FATAL_FAILURE(click("tool_literature")); auto *area = literature_area(); ASSERT_NE(area, nullptr);
  auto draft = area->editor().save_workspace_state(); draft["corpus"] = scope; draft["scopes"] = Json::array({scope});
  ASSERT_TRUE(area->editor().load_workspace_state(draft)); frame();
  ASSERT_NO_FATAL_FAILURE(click("literature_query"));
  const auto type = [&](const std::string &text) {
    auto e = ui::Event::text_input(text); e.time = double(++fixture.drv->time_ms) / 1000.;
    fixture.screen.ui()->handle_event(e); frame();
  };
  type("keep corpus draft 极化");
  ASSERT_NO_FATAL_FAILURE(commit(v, scope)); // Another view changes this library's generation.
  frame(); fixture.drv->key(wm::Key::Enter); frame();
  ASSERT_NE(widget("literature_query"), nullptr);
  EXPECT_EQ(widget("literature_query")->string.value(), "keep corpus draft 极化");
  ASSERT_NO_FATAL_FAILURE(click("literature_query"));
  fixture.drv->key(wm::Key::End); type(" and reconnect");
  const auto before = calls("info"); store.set_bridge(nullptr); store.set_bridge(client.get());
  frame(); fixture.drv->key(wm::Key::Enter); frame();
  EXPECT_EQ(widget("literature_query")->string.value(), "keep corpus draft 极化 and reconnect");
  EXPECT_EQ(calls("info"), before); EXPECT_EQ(calls("search"), 0); EXPECT_EQ(calls("pages.render"), 0);
}

TEST_P(LiteratureMouse, CachedActionRefusesSameClientRestartBeforeItsStateListenerRuns)
{
  ASSERT_NO_FATAL_FAILURE(click("tool_literature"));
  ASSERT_NO_FATAL_FAILURE(section(1));
  ASSERT_NO_FATAL_FAILURE(text("literature_name", "Original local draft"));
  const auto original = widget("literature_create")->on_click;
  const auto before_hide = store.version();
  fixture.screen.set_maximized(&fixture.area("a2")); original(); // No ready/layout callback has run yet.
  EXPECT_EQ(store.version(), before_hide); EXPECT_EQ(calls("corpora.create"), 0);
  fixture.screen.set_maximized(nullptr); frame();
  const auto spawned = client->stats().spawned, epoch = store.bridge_epoch();
  marker("crash"); const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(45);
  // Deliberately do not pump ManualLoop: queued state notifications have not invalidated the UI.
  while ((client->stats().spawned == spawned || client->state() != bridge::BridgeState::Ready) &&
         std::chrono::steady_clock::now() < deadline) { std::this_thread::sleep_for(std::chrono::milliseconds(5)); }
  ASSERT_GT(client->stats().spawned, spawned); ASSERT_EQ(client->state(), bridge::BridgeState::Ready);
  ASSERT_EQ(store.bridge_epoch(), epoch); const auto version = store.version(); original();
  EXPECT_EQ(store.version(), version); // Reject before the controller can rebind to the new process.
  EXPECT_EQ(calls("corpora.create"), 0);
  loop.run_ready(); frame(); ASSERT_NO_FATAL_FAILURE(click("literature_create"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_created")); EXPECT_EQ(calls("corpora.create"), 1);
}

INSTANTIATE_TEST_SUITE_P(FixedLayouts, LiteratureMouse, ::testing::Bool());

#ifdef STK_LITERATURE_REAL_ASSETS_ACCEPTANCE
// This wrapper observes owned requests/replies without replacing any DTO or
// inference. Interpreter selection is trusted Bridge construction, never UI/RPC.
constexpr const char *real_assets_script = R"PY(
from pathlib import Path
import json,sys,threading,os
control=Path(sys.argv.pop(1))
sys.path.insert(0,str(Path(os.environ['PYTHONPATH'])/'tests'))
from test_literature_pdf import make_pdf
(control.parent/'real-owned.pdf').write_bytes(make_pdf([[
    'A solar cell converts sunlight into electrical energy.',
    'Self-authored solar cell sunlight software fixture; no experimental measurements.'
]]))
from suan.desktop_bridge import server
from suan.desktop_bridge.literature import LiteratureService
BaseBridge=server.Bridge
lock=threading.Lock()
calls=LiteratureService.call
def observed_call(self,action,params):
    with lock:
        with control.with_suffix('.calls').open('a') as f:f.write(action+'\n')
        with control.with_suffix('.requests').open('a') as f:
            f.write(json.dumps({'action':action,'params':params},allow_nan=False)+'\n')
    return calls(self,action,params)
LiteratureService.call=observed_call
class TrustedBridge(BaseBridge):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,
            literature_parser_python=os.environ['STK_LITERATURE_TEST_PYTHON'],
            literature_encoder_python=os.environ['STK_LITERATURE_E5_PYTHON'],**kwargs)
    def send(self,message,method=None):
        if method and method.startswith('literature.') and 'result' in message:
            with lock,control.with_suffix('.replies').open('a') as f:
                f.write(json.dumps({'method':method,'result':message['result']},allow_nan=False)+'\n')
        return super().send(message,method)
server.Bridge=TrustedBridge
from suan.desktop_bridge.__main__ import main
raise SystemExit(main())
)PY";

class LiteratureRealAssets : public LiteratureMouse {
 protected:
  static constexpr const char *manifest_sha = "301ef8fcc5b1cf59cb7f55cd7bbc07e5f852f3deca2f89f4f1c548d20b1c2d71";
  std::string parser_python_, encoder_python_, assets_;
  struct Capture {
    std::map<uint64_t, io::Image> uploaded;
    std::set<uint64_t> live_textures;
    std::vector<std::string> events;
    uint64_t next_texture = 1;
  };
  // The editor copies its free hook. Its capture must outlive this derived
  // fixture even if setup/assertions fail and base-owned UI destruction is late.
  std::shared_ptr<Capture> capture_ = std::make_shared<Capture>();
  const char *service_script() const override { return real_assets_script; }
  void service_environment(bridge::ClientOptions &options) const override
  {
    options.env["STK_LITERATURE_TEST_PYTHON"] = parser_python_;
    options.env["STK_LITERATURE_E5_PYTHON"] = encoder_python_;
    options.env["HF_HUB_OFFLINE"] = "1"; options.env["TRANSFORMERS_OFFLINE"] = "1";
  }
  static std::string required_environment(const char *key)
  {
    const char *value = std::getenv(key);
    if (!value || !*value) { ADD_FAILURE() << "Explicit installed asset is required: " << key; return {}; }
    return value;
  }
  void SetUp() override
  {
    parser_python_ = required_environment("STK_LITERATURE_TEST_PYTHON");
    encoder_python_ = required_environment("STK_LITERATURE_E5_PYTHON");
    assets_ = required_environment("STK_LITERATURE_E5_ASSETS");
    const auto selected_sha = required_environment("STK_LITERATURE_E5_MANIFEST_SHA256");
    ASSERT_FALSE(parser_python_.empty()); ASSERT_FALSE(encoder_python_.empty()); ASSERT_FALSE(assets_.empty());
    ASSERT_EQ(selected_sha, manifest_sha) << "This acceptance requires the reviewed, fixed E5 manifest";
    for (const auto &path : {parser_python_, encoder_python_}) {
      ASSERT_TRUE(std::filesystem::path(path).is_absolute());
      ASSERT_TRUE(std::filesystem::is_regular_file(path)) << "Required interpreter is absent: " << path;
    }
    ASSERT_TRUE(std::filesystem::path(assets_).is_absolute());
    const auto manifest = std::filesystem::path(assets_) / "manifest.json";
    ASSERT_TRUE(std::filesystem::is_regular_file(manifest));
    ASSERT_LE(std::filesystem::file_size(manifest), 16384u);
    ASSERT_EQ(core::Sha256::hex(wmtest::read_text(manifest.string())), manifest_sha);
    ASSERT_NO_FATAL_FAILURE(LiteratureMouse::SetUp());
    ASSERT_TRUE(std::filesystem::is_regular_file(dir.path() / "real-owned.pdf"));
    auto &jobs = store.jobs();
    jobs.create_texture = [capture = capture_](const io::Image &image) {
      const auto handle = capture->next_texture++;
      EXPECT_TRUE(capture->live_textures.empty()) << "Replacement must release the prior texture before upload";
      capture->uploaded[handle] = image; capture->live_textures.insert(handle);
      capture->events.push_back("create/" + std::to_string(handle)); return handle;
    };
    jobs.free_texture = [capture = capture_](uint64_t handle) {
      EXPECT_EQ(capture->live_textures.erase(handle), 1u);
      capture->events.push_back("free/" + std::to_string(handle));
    };
  }
  void TearDown() override
  {
    LiteratureBridge::TearDown(); // Bridge invalidation releases the editor's copied free hook first.
    state().sync({}); // Also covers a failed setup/close with no queued state notification.
    EXPECT_TRUE(capture_->live_textures.empty());
    store.jobs().create_texture = {}; store.jobs().free_texture = {};
  }
  std::vector<Json> observations(const char *suffix) const
  {
    std::ifstream input(dir.path() / (std::string("control.") + suffix));
    std::vector<Json> result; std::string line;
    while (std::getline(input, line)) {
      // A concurrent append may expose its last incomplete line. Retry on the
      // next poll, without treating it as a completed receipt or printing bytes.
      if (line.size() > 8 * 1024 * 1024) { ADD_FAILURE() << "Owned observation exceeds protocol budget"; break; }
      auto value = Json::parse(line, nullptr, false);
      if (!value.is_discarded()) { result.push_back(std::move(value)); }
    }
    return result;
  }
  std::vector<Json> results(const std::string &action) const
  {
    std::set<std::string> seen; std::vector<Json> result;
    for (const auto &record : observations("replies")) {
      if (io::get_string(record, "method") != "literature.operations.result") { continue; }
      const auto &envelope = record.at("result"); const auto &op = envelope.at("operation");
      if (io::get_string(op, "action") == action && seen.insert(io::get_string(op, "operation_id")).second) {
        result.push_back(envelope);
      }
    }
    return result;
  }
  int reply_count(const std::string &method) const
  {
    int n = 0;
    for (const auto &record : observations("replies")) { n += io::get_string(record, "method") == "literature." + method; }
    return n;
  }
  int total_calls() const
  {
    std::ifstream input(dir.path() / "control.calls"); std::string line; int n = 0;
    while (std::getline(input, line)) { ++n; } return n;
  }
  bool enabled(const std::string &key) const { const auto *w = widget(key); return w && w->enabled; }
  void wait_result(const std::string &action, size_t ordinal, const std::function<bool()> &adopted, double timeout = 90)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      frame(); return results(action).size() >= ordinal && calls(action) >= int(ordinal) && adopted();
    }, timeout)) << "UI did not adopt original result: " << action << " #" << ordinal;
    ASSERT_EQ(calls(action), int(ordinal));
    const auto envelope = results(action).at(ordinal - 1); const auto &op = envelope.at("operation");
    ASSERT_EQ(io::get_string(op, "state"), "completed");
    ASSERT_TRUE(LiteratureState::operation_matches(op, io::get_string(op, "operation_id")));
    ASSERT_EQ(LiteratureState::checksum(envelope.at("result")), io::get_string(op, "result_sha256"));
    bool original = false;
    for (const auto &request : observations("requests")) {
      if (io::get_string(request, "action") == action &&
          io::get_string(request.at("params"), "operation_id") == io::get_string(op, "operation_id")) {
        EXPECT_EQ(LiteratureState::request_sha256(action, request.at("params")), io::get_string(op, "request_sha256"));
        original = true;
      }
    }
    EXPECT_TRUE(original) << "Result must bind the actual owned UI request";
  }
  void verify_page(const Json &resolved, const Json &rendered)
  {
    LiteraturePage expected; ASSERT_TRUE(expected.adopt(resolved, rendered)) << expected.error();
    ASSERT_TRUE(expected.ready()); ASSERT_TRUE(expected.highlights()); ASSERT_FALSE(expected.highlights()->empty());
    EXPECT_EQ(core::Sha256::hex(expected.png()), io::get_string(rendered.at("image"), "sha256"));
    const auto *w = widget("literature_page"); ASSERT_NE(w, nullptr); ASSERT_NE(w->image.texture, 0u);
    ASSERT_TRUE(capture_->uploaded.contains(w->image.texture)); ASSERT_TRUE(capture_->live_textures.contains(w->image.texture));
    const auto &actual = capture_->uploaded.at(w->image.texture);
    EXPECT_EQ(actual.width, expected.image()->width); EXPECT_EQ(actual.height, expected.image()->height);
    EXPECT_EQ(actual.channels, 4u); EXPECT_EQ(actual.pixels.size(), expected.image()->pixels.size());
    EXPECT_EQ(core::Sha256::hex(actual.pixels), core::Sha256::hex(expected.image()->pixels));
    EXPECT_EQ(w->image.width, int(actual.width)); EXPECT_EQ(w->image.height, int(actual.height));
    ASSERT_TRUE(w->image.highlights); ASSERT_EQ(w->image.highlights->size(), expected.highlights()->size());
    for (size_t i = 0; i < expected.highlights()->size(); ++i) {
      for (size_t p = 0; p < 4; ++p) {
        EXPECT_FLOAT_EQ(w->image.highlights->at(i)[p].x, float(expected.highlights()->at(i).points[p][0]));
        EXPECT_FLOAT_EQ(w->image.highlights->at(i)[p].y, float(expected.highlights()->at(i).points[p][1]));
      }
    }
  }
};

TEST_P(LiteratureRealAssets, OwnedPdfAndPinnedE5ThroughExplicitCpuUiPreserveViewerDraftAndRevocation)
{
  // Fixture seeding and the two lifecycle injections below are not counted as
  // mouse navigation. All literature business actions use ordinary input events.
  auto &bottom = fixture.area("a4"); ASSERT_TRUE(bottom.set_tabs({kEditorLogs, kEditorPython}, 0));
  auto hidden = bottom.tab(1).save_workspace_state();
  hidden["source"] = "print('keep exact hidden real literature draft')\n# 未运行草稿";
  ASSERT_TRUE(bottom.tab(1).load_workspace_state(hidden));
  store.viewer().set_auto_evaluate(false); store.viewer().prefetch_neighbours = false;
  auto payload = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  store.viewer().open_payload(payload, "Public owned real literature UI fixture");
  ASSERT_TRUE(loop.pump_until([&] { store.viewer().pump(); return !store.viewer().presets().empty() &&
      store.viewer().catalog().is_object() && store.viewer().colormaps(); }));
  const auto viewer = store.viewer().save_workspace_state();
  const auto camera = store.viewer().camera_serial(), serial = store.viewer().payload_serial(); frame();

  ASSERT_NO_FATAL_FAILURE(click("tool_literature")); ASSERT_NE(literature_area(), nullptr);
  EXPECT_EQ(clicks, 1); EXPECT_EQ(wheels, 0); EXPECT_EQ(total_calls(), 0);
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "bridge/literature"));
  ASSERT_NO_FATAL_FAILURE(click("literature_refresh"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return calls("info") == 1 && calls("encoder.info") == 1 && enabled("literature_refresh"); }));
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "bridge/literature"));
  ASSERT_NO_FATAL_FAILURE(section(1));
  ASSERT_NO_FATAL_FAILURE(text("literature_name", "Owned real PDFium E5 UI library"));
  ASSERT_NO_FATAL_FAILURE(click("literature_create"));
  ASSERT_NO_FATAL_FAILURE(wait_result("corpora.create", 1, [&] { return enabled("literature_created"); }));
  const auto scope = io::get_string(results("corpora.create").at(0).at("result"), "corpus_id");
  ASSERT_TRUE(LiteratureState::corpus_id(scope));
  ASSERT_NO_FATAL_FAILURE(click("literature_created"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return state().corpus_info(scope) && enabled("literature_source"); }));
  const auto source = dir.path() / "real-owned.pdf";
  ASSERT_NO_FATAL_FAILURE(text("literature_source", source.string()));
  ASSERT_NO_FATAL_FAILURE(text("literature_title", "Self-authored solar cell software fixture"));
  ASSERT_NO_FATAL_FAILURE(click("literature_basis"));
  fixture.drv->key(wm::Key::End); fixture.drv->key(wm::Key::Enter); frame();
  ASSERT_EQ(widget("literature_basis")->index.value(), 1);
  ASSERT_NO_FATAL_FAILURE(text("literature_evidence", "Self-authored generated software-test PDF; no third-party or private data"));
  ASSERT_NO_FATAL_FAILURE(text("literature_approved_by", "Owned fixture author"));
  ASSERT_NO_FATAL_FAILURE(click("literature_authorized"));
  ASSERT_TRUE(widget("literature_authorized")->boolean.value());
  ASSERT_NO_FATAL_FAILURE(click("literature_import_review"));
  ASSERT_NO_FATAL_FAILURE(wait_result("import.review", 1, [&] { return enabled("literature_import_commit"); }));
  const auto reviewed = results("import.review").at(0); const auto &review = reviewed.at("result");
  const auto review_id = io::get_string(reviewed.at("operation"), "operation_id");
  EXPECT_EQ(review.at("authorization").at("basis"), "self_authored");
  EXPECT_EQ(review.at("authorization").at("approved_by"), "Owned fixture author");
  EXPECT_EQ(io::get_string(review, "source_sha256"), core::Sha256::hex(wmtest::read_text(source.string())));
  ASSERT_NO_FATAL_FAILURE(click("literature_import_commit"));
  ASSERT_NO_FATAL_FAILURE(wait_result("import.commit", 1, [&] { return enabled("literature_index"); }));
  const auto version = io::get_string(results("import.commit").at(0).at("result").at("receipt"), "version_id");
  ASSERT_FALSE(version.empty());
  ASSERT_NO_FATAL_FAILURE(click("literature_index"));
  ASSERT_NO_FATAL_FAILURE(wait_result("index.start", 1, [&] {
    const auto r = results("index.start"); const auto *info = state().corpus_info(scope);
    return !r.empty() && info && info->at("generation") == r.at(0).at("result").at("receipt").at("generation") && enabled("literature_index");
  }));

  ASSERT_NO_FATAL_FAILURE(section(2));
  ASSERT_NO_FATAL_FAILURE(text("literature_assets", assets_));
  ASSERT_NO_FATAL_FAILURE(click("literature_encoder_review"));
  ASSERT_NO_FATAL_FAILURE(wait_result("encoder.review", 1, [&] { return enabled("literature_encoder_select"); }));
  const auto encoder_review = results("encoder.review").at(0).at("result");
  EXPECT_EQ(io::get_string(encoder_review, "assets_sha256"), manifest_sha);
  EXPECT_EQ(io::get_string(encoder_review, "python"), encoder_python_);
  ASSERT_NO_FATAL_FAILURE(click("literature_encoder_select"));
  ASSERT_NO_FATAL_FAILURE(wait_result("encoder.select", 1, [&] {
    const auto &info = state().encoder_info();
    return info.is_object() && info.at("selection").is_object() &&
      info.at("selection").at("fingerprint") == encoder_review.at("fingerprint") && enabled("literature_build");
  }));
  ASSERT_NO_FATAL_FAILURE(click("literature_build"));
  ASSERT_NO_FATAL_FAILURE(wait_result("dense.build", 1, [&] {
    const auto r = results("dense.build"); const auto *info = state().corpus_info(scope);
    return !r.empty() && info && info->at("dense_generation") == r.at(0).at("result").at("receipt").at("generation") && enabled("literature_build");
  }, 630));
  EXPECT_GE(io::get_int(results("dense.build").at(0).at("result").at("receipt"), "windows", 0), 1);

  ASSERT_NO_FATAL_FAILURE(section(0));
  ASSERT_NO_FATAL_FAILURE(click("literature_refresh"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return enabled("literature_scope/" + scope) && enabled("literature_query"); }));
  EXPECT_TRUE(widget("literature_scope/" + scope)->boolean.value());
  ASSERT_NO_FATAL_FAILURE(text("literature_query", "solar cell sunlight"));
  ASSERT_NO_FATAL_FAILURE(click("literature_search"));
  ASSERT_NO_FATAL_FAILURE(wait_result("search", 1, [&] { return enabled("literature_hit/0"); }, 145));
  const auto search = results("search").at(0).at("result"); ASSERT_FALSE(search.at("hits").empty());
  const auto hit = search.at("hits").at(0); EXPECT_EQ(io::get_string(hit, "corpus_id"), scope);
  EXPECT_NE(io::get_string(hit, "text").find("sunlight"), std::string::npos);
  ASSERT_NO_FATAL_FAILURE(click("literature_hit/0"));
  ASSERT_NO_FATAL_FAILURE(click("literature_resolve"));
  ASSERT_NO_FATAL_FAILURE(wait_result("citations.resolve", 1, [&] { return enabled("literature_render"); }));
  const auto resolved = results("citations.resolve").at(0).at("result");
  EXPECT_EQ(resolved.at("citation"), hit.at("citation")); EXPECT_EQ(resolved.at("text"), hit.at("text"));
  EXPECT_EQ(resolved.at("parser").at("pypdfium2"), "5.14.0");
  EXPECT_EQ(resolved.at("text_status"), "mapped"); EXPECT_EQ(resolved.at("structure_status"), "unreviewed");
  ASSERT_NO_FATAL_FAILURE(click("literature_render"));
  ASSERT_NO_FATAL_FAILURE(wait_result("pages.render", 1, [&] { return widget("literature_page") && capture_->live_textures.size() == 1; }));
  const auto rendered = results("pages.render").at(0).at("result");
  EXPECT_EQ(rendered.at("source_sha256"), review.at("source_sha256"));
  ASSERT_NO_FATAL_FAILURE(verify_page(resolved, rendered));
  const auto first_texture = widget("literature_page")->image.texture;
  ASSERT_NO_FATAL_FAILURE(click("literature_render"));
  EXPECT_TRUE(capture_->live_textures.empty()) << "Normal render input releases prior pixels before reply adoption";
  ASSERT_EQ(capture_->events.size(), 2u); EXPECT_EQ(capture_->events.back(), "free/" + std::to_string(first_texture));
  ASSERT_NO_FATAL_FAILURE(wait_result("pages.render", 2, [&] { return widget("literature_page") && capture_->live_textures.size() == 1; }));
  ASSERT_NO_FATAL_FAILURE(verify_page(resolved, results("pages.render").at(1).at("result")));
  const auto second_texture = widget("literature_page")->image.texture; EXPECT_NE(second_texture, first_texture);
  EXPECT_EQ(results("pages.render").at(1).at("result").at("image").at("sha256"), rendered.at("image").at("sha256"));

  ASSERT_NO_FATAL_FAILURE(section(1));
  ASSERT_NO_FATAL_FAILURE(click("literature_revoke"));
  EXPECT_TRUE(capture_->live_textures.empty()) << "Revoke input must clear real content before queued RPC replies run";
  EXPECT_EQ(capture_->events.back(), "free/" + std::to_string(second_texture));
  ASSERT_NO_FATAL_FAILURE(wait_result("versions.revoke", 1, [&] { return enabled("literature_revoke"); }));
  EXPECT_FALSE(results("versions.revoke").at(0).at("result").at("receipt").at("active").get<bool>());
  ASSERT_NO_FATAL_FAILURE(section(0)); EXPECT_EQ(widget("literature_page"), nullptr);
  ASSERT_NE(widget("literature_resolve"), nullptr); EXPECT_FALSE(widget("literature_resolve")->enabled);
  EXPECT_FALSE(widget("literature_render")->enabled);
  ASSERT_NO_FATAL_FAILURE(section(3));
  ASSERT_NO_FATAL_FAILURE(click("literature_operations"));
  ASSERT_NO_FATAL_FAILURE(click("literature_operation/" + review_id));
  ASSERT_NO_FATAL_FAILURE(click("literature_check"));
  ASSERT_NO_FATAL_FAILURE(wait_widget("literature_result"));
  const auto prior_results = reply_count("operations.result");
  ASSERT_NO_FATAL_FAILURE(click("literature_result"));
  ASSERT_TRUE(loop.pump_until([&] { frame(); return reply_count("operations.result") > prior_results && widget("literature_history_previous"); }));
  ASSERT_NO_FATAL_FAILURE(section(1)); EXPECT_EQ(widget("literature_import_commit"), nullptr);
  EXPECT_FALSE(widget("literature_authorized")->boolean.value());
  EXPECT_EQ(calls("import.commit"), 1); EXPECT_EQ(calls("encoder.select"), 1); EXPECT_EQ(calls("pages.render"), 2);

  auto *area = literature_area(); ASSERT_NE(area, nullptr);
  const auto draft = area->editor().save_workspace_state(); const auto before_lifecycle = total_calls();
  const int tab = area->active_tab(); ASSERT_TRUE(area->add_tab(kEditorLogs));
  area->set_active_tab(area->tab_count() - 1); frame(); area->set_active_tab(tab); frame();
  store.set_bridge(nullptr); store.set_bridge(client.get()); frame(); loop.run_ready(); frame();
  EXPECT_EQ(total_calls(), before_lifecycle); EXPECT_EQ(area->editor().save_workspace_state(), draft);
  EXPECT_EQ(widget("literature_source")->string.value(), source.string());
  EXPECT_FALSE(widget("literature_authorized")->boolean.value()); EXPECT_EQ(widget("literature_import_commit"), nullptr);
  EXPECT_EQ(bottom.tab(1).save_workspace_state(), hidden); EXPECT_TRUE(bottom.tab(1).has_unsaved_changes());
  EXPECT_EQ(store.viewer().save_workspace_state(), viewer); EXPECT_EQ(store.viewer().base_payload(), payload);
  EXPECT_EQ(store.viewer().camera_serial(), camera); EXPECT_EQ(store.viewer().payload_serial(), serial);
  EXPECT_EQ(capture_->events, (std::vector<std::string>{"create/1", "free/1", "create/2", "free/2"}));
  std::cout << "LITERATURE_REAL_ASSETS layout=" << (GetParam() ? "zh_CN/1000x1200" : "en/1600x1100")
            << " scale=1 clicks=" << clicks << " wheels=" << wheels
            << " lifecycle_injections=2 fixture_seeding=2 cpu_ui_only=true os_gpu_presentation=false"
            << " original_receipts=true real_pdfium=true real_e5=true render=2 textures=2/2"
            << " revoke_sync_clear=true historical_authority=false viewer_hidden_draft_preserved=true\n";
}
INSTANTIATE_TEST_SUITE_P(RealAssets, LiteratureRealAssets, ::testing::Bool());
#endif
}  // namespace
}  // namespace stk::app
