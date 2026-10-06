/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_state.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>

namespace stk::app {
namespace {
using io::Json;

class ScriptPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"scripts"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en"};
  std::unique_ptr<bridge::Client> client;

  ScriptState &state() { return f.shell->store().scripts(); }
  bool pump(const std::function<bool()> &until, const double timeout = 30)
  {
    return loop.pump_until([&] { f.screen.run_deferred(); return until(); }, timeout);
  }
  std::string output()
  {
    std::string text;
    const auto &log = state().output();
    for (size_t i = 0; i < log.line_count(); ++i) {
      text += log.line(i);
      text += '\n';
    }
    return text;
  }
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON to run Python desktop tests"; }
    bridge::ClientOptions options;
    options.python.configured = python;
    options.state_dir = dir.str() + "/bridge";
    options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = "fixture-model";
    options.executor = loop.executor();
    options.strict = options.validate = true;
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start());
    f.shell->store().set_bridge(client.get());
    ASSERT_TRUE(pump([&] { return state().ready() && state().desktop_ready() && !state().busy(); }, 60))
        << client->bridge_log().text();
  }
  void TearDown() override
  {
    f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); }
    loop.run_ready();
    EXPECT_EQ(client ? client->stats().schema_violations : 0, 0u);
  }
  void execute(const std::string &code, const std::string &expected = "succeeded")
  {
    ASSERT_TRUE(state().execute(code)) << state().error();
    ASSERT_TRUE(pump([&] { return !state().busy(); })) << client->bridge_log().text();
    ASSERT_TRUE(state().error().empty()) << state().error();
    EXPECT_EQ(state().status().at("run").at("state"), expected) << output();
  }
  void open_project()
  {
    auto &project = f.shell->store().project();
    project.sync();
    ASSERT_TRUE(project.create(dir.str() + "/project", "Review project"));
    ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy(); }));
    execute("p = stk.project\ncommands = [{'op': 'create_table', 'name': 'Proposed cases'}]\n"
            "from suan.scripting import ScriptError\n"
            "def rejected(params, code):\n"
            "    try:\n"
            "        stk.call('ui.project.review', **params)\n"
            "    except ScriptError as error:\n"
            "        assert error.code == code, str(error)\n"
            "    else:\n"
            "        raise AssertionError('unexpected acceptance')\n"
            "request = {'handle': p.handle, 'commands': commands, 'expected_revision': 0}");
  }
  void selection_project(const bool already_open = false)
  {
    if (!already_open) { ASSERT_NO_FATAL_FAILURE(open_project()); }
    execute(R"PY(
from uuid import uuid4
t1, t2, r1, r2, r3, f1 = (str(uuid4()) for _ in range(6))
p.apply([
    {'op': 'create_table', 'id': t1, 'name': 'First'},
    {'op': 'add_field', 'id': f1, 'table_id': t1, 'name': 'Label', 'type': 'text'},
    {'op': 'add_record', 'id': r1, 'table_id': t1},
    {'op': 'add_record', 'id': r2, 'table_id': t1},
    {'op': 'set_cell', 'table_id': t1, 'record_id': r1, 'field_id': f1, 'value': 'Red'},
    {'op': 'set_cell', 'table_id': t1, 'record_id': r2, 'field_id': f1, 'value': 'Blue'},
    {'op': 'create_table', 'id': t2, 'name': 'Second'},
    {'op': 'add_record', 'id': r3, 'table_id': t2},
], expected_revision=0)
def selection_rejected(params, code, operation='project.select'):
    try:
        stk.call('ui.' + operation, **params)
    except ScriptError as error:
        assert error.code == code, str(error)
    else:
        raise AssertionError('unexpected selection acceptance')
select_request = {'handle': p.handle, 'expected_revision': 1, 'table_id': t1, 'record_id': r2}
)PY");
    auto &project = f.shell->store().project();
    ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 1; }));
  }

};

TEST_F(ScriptPython, FocusNavigationPreservesLiveAiAndPythonDraftsAndProject)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  auto &area = f.area("a2"), &viewer = f.area("a1");
  ASSERT_TRUE(area.set_tab_type(0, kEditorAI));
  ASSERT_TRUE(area.add_tab(kEditorPython, false));
  ASSERT_TRUE(viewer.set_tab_type(0, kEditorViewer));
  Editor *ai = &area.tab(0), *python = &area.tab(1), *view = &viewer.tab(0);
  const auto handle = project.project()->handle;
  const auto frame = [&] {
    for (int i = 0; i < 3; ++i) {
      f.drv->frame();
      ASSERT_TRUE(pump([&] { return !project.busy() && !project.discussion().busy(); }));
    }
  };
  f.screen.set_maximized(&area); frame();
  const auto question_key = "a2/main/ai_question/" + handle;
  ASSERT_NE(f.screen.ui()->find(question_key), nullptr);
  f.screen.ui()->find(question_key)->string.assign("Unsent research question / 未发送的问题");
  execute("r = stk.ui.activate_editor('python', maximize=True)\nassert r == {'area_id': 'a2', 'editor_id': 'python', 'tab_index': 1, 'maximized': True}");
  f.drv->frame(); ASSERT_NE(f.screen.ui()->find("a2/main/python_source"), nullptr);
  f.screen.ui()->find("a2/main/python_source")->string.assign("print('keep this unexecuted draft')");
  execute("assert stk.ui.activate_editor('viewer', maximize=True)['area_id'] == 'a1'");
  EXPECT_EQ(f.screen.maximized(), &viewer);
  execute("assert stk.ui.activate_editor('ai', maximize=True)['tab_index'] == 0"); frame();
  EXPECT_EQ(f.screen.ui()->find(question_key)->string.value(), "Unsent research question / 未发送的问题");
  execute("stk.ui.activate_editor('python')"); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.ui()->find("a2/main/python_source")->string.value(), "print('keep this unexecuted draft')");
  execute("assert stk.ui.restore_split_layout() is False\nstk.ui.activate_editor('ai', maximize=True)\n"
          "assert stk.ui.restore_split_layout() is True\nassert stk.ui.restore_split_layout() is False");
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(&area.tab(0), ai); EXPECT_EQ(&area.tab(1), python); EXPECT_EQ(&viewer.tab(0), view);
  EXPECT_EQ(area.tab_count(), 2); EXPECT_EQ(project.project()->handle, handle);
  EXPECT_EQ(project.project()->revision, 0); EXPECT_TRUE(project.discussion().exchange_request().empty());
}

TEST_F(ScriptPython, FocusNavigationRunsFromSubmittedConsoleInput)
{
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area); f.drv->frame();
  Editor *original = &area.editor();
  const auto [x, y] = f.widget_center("a2/main/python_source"); f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::A, primary);
  const std::string source = "print(stk.ui.activate_editor('ai', maximize=True)['editor_id'])";
  f.drv->key(wm::Key::Unknown, wm::ModNone, source);
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  f.drv->key(wm::Key::Enter, primary);
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  ASSERT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  auto *focused = dynamic_cast<EditorArea *>(f.screen.maximized()); ASSERT_NE(focused, nullptr);
  EXPECT_EQ(focused->editor().type().id, kEditorAI);
  EXPECT_NE(output().find("ai"), std::string::npos);
  execute("stk.ui.activate_editor('python', maximize=True)"); f.drv->frame();
  EXPECT_EQ(&area.editor(), original);
  EXPECT_EQ(f.screen.ui()->find("a2/main/python_source")->string.value(), source);
}

TEST_F(ScriptPython, FocusNavigationRejectsInvalidArgumentsAndActiveTextWithoutPartialChanges)
{
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area); f.drv->frame();
  execute(R"PY(
from suan.scripting import ScriptError
def focus_rejected(operation, params, code):
    try:
        stk.call('ui.' + operation, **params)
    except ScriptError as error:
        assert error.code == code, str(error)
    else:
        raise AssertionError('unexpected focus acceptance')
for params in ({}, {'editor_id':'ai'}, {'editor_id':'ai', 'maximize':1},
               {'editor_id':42, 'maximize':True}, {'editor_id':'', 'maximize':False},
               {'editor_id':'ai', 'maximize':True, 'extra':1}, {'editor_id':'x'*129, 'maximize':True},
               {'editor_id':'unknown-editor', 'maximize':False}):
    focus_rejected('editors.activate', params, 'invalid_params')
focus_rejected('layout.unmaximize', {'extra':True}, 'invalid_params')
)PY");
  const auto before = f.screen.to_json();
  const auto [x, y] = f.widget_center("a2/main/python_source"); f.drv->click(x, y);
#ifdef __APPLE__
  f.drv->key(wm::Key::A, wm::ModOS);
#else
  f.drv->key(wm::Key::A, wm::ModCtrl);
#endif
  f.drv->key(wm::Key::Unknown, wm::ModNone, "unfinished text");
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  execute("focus_rejected('editors.activate', {'editor_id':'ai', 'maximize':True}, 'busy')\n"
          "focus_rejected('layout.unmaximize', {}, 'busy')");
  EXPECT_EQ(f.screen.to_json(), before);
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "unfinished text");
}

TEST_F(ScriptPython, FocusNavigationTargetsFirstWindowAndPreservesOtherWindowInput)
{
  struct ExtraScreen {
    AppShell &shell;
    wm::Screen screen;
    wmtest::ScreenDriver driver;
    explicit ExtraScreen(AppShell &owner) : shell(owner), driver(screen, 1280, 800, 1)
    { shell.install(screen, nullptr); shell.build_default_layout(screen); }
    ~ExtraScreen() { shell.forget(screen); }
  } extra(*f.shell);
  auto &other = extra.screen;
  auto &driver = extra.driver;
  auto *area = dynamic_cast<EditorArea *>(other.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorPython)); other.set_maximized(area);
  driver.frame();
  const auto *source = other.ui()->find("a2/main/python_source"); ASSERT_NE(source, nullptr);
  const auto center = source->rect;
  driver.click(int(center.cx()), other.rect().ymax - 1 - int(center.cy()));
#ifdef __APPLE__
  driver.key(wm::Key::A, wm::ModOS);
#else
  driver.key(wm::Key::A, wm::ModCtrl);
#endif
  driver.key(wm::Key::Unknown, wm::ModNone, "other window draft");
  ASSERT_TRUE(other.ui()->text_input_active());
  const auto saved = other.to_json();
  execute("assert stk.ui.activate_editor('ai', maximize=True)['editor_id'] == 'ai'");
  EXPECT_EQ(other.to_json(), saved); EXPECT_EQ(other.ui()->edit_state()->text(), "other window draft");
  EXPECT_NE(f.screen.maximized(), nullptr);
  execute("assert stk.ui.restore_split_layout() is True");
  EXPECT_EQ(other.to_json(), saved); EXPECT_EQ(f.screen.maximized(), nullptr);
}

TEST_F(ScriptPython, DetachedBridgeDropsQueuedFocusWithoutCreatingTabs)
{
  bool queued = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &data) {
    if (io::get_string(data, "operation") == "editors.activate") { queued = true; }
  });
  ASSERT_TRUE(state().execute("stk.ui.activate_editor('ai', maximize=True)"));
  ASSERT_TRUE(loop.pump_until([&] { return queued; }, 30));
  const auto before = f.screen.to_json();
  f.shell->store().set_bridge(nullptr); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before); EXPECT_FALSE(state().ready());
}

TEST_F(ScriptPython, ProjectSelectionReadsEmptyProjectsAndCapturesExactSelectedRows)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  execute("assert p.selection() == {'project_id': p.snapshot()['project']['id'], 'revision': 0, 'table_id': None, 'record_id': None}");
  auto &project = f.shell->store().project();
  ASSERT_NO_FATAL_FAILURE(selection_project(true));
  auto &area = f.area("a2"); ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.add_tab(kEditorPython));
  const auto layout = f.screen.to_json();
  project.set_review_source(Json::array({{{"op", "create_table"}, {"name", "Preserved review"}}}).dump());
  ASSERT_TRUE(project.preview()); ASSERT_TRUE(pump([&] { return !project.busy(); }));
  ASSERT_TRUE(project.save_review("Preserved source")); ASSERT_TRUE(pump([&] { return !project.busy(); }));
  const auto review = project.review();
  const auto saved = project.saved_review();
  execute(R"PY(
before = p.snapshot()
assert p.selection()['record_id'] == r1
result = p.select(t2, r3, expected_revision=1)
assert result == {'project_id': before['project']['id'], 'revision': 1, 'table_id': t2, 'record_id': r3}
assert p.selection() == result
selected = p.select(t1, r2, expected_revision=result['revision'])
context = p.contexts.capture(selected['table_id'], [selected['record_id']], [f1],
    expected_revision=selected['revision'], title='Selected row', context_id=str(uuid4()))
assert context['content']['value']['records'][0]['literals'][f1]['value'] == 'Blue'
assert p.snapshot() == before and len(p.history()) == 1
)PY");
  EXPECT_EQ(f.screen.to_json(), layout);
  EXPECT_EQ(area.editor().type().id, kEditorPython);
  EXPECT_EQ(project.review(), review);
  EXPECT_EQ(project.saved_review(), saved);
  EXPECT_TRUE(project.can_apply_review());
  EXPECT_EQ(project.project()->revision, 1);
}

TEST_F(ScriptPython, ProjectSelectionClearsDeletedRecordsAndTables)
{
  ASSERT_NO_FATAL_FAILURE(selection_project());
  auto &project = f.shell->store().project();
  execute("p.select(t2, r3, expected_revision=1)\np.apply([{'op': 'delete_record', 'id': r3}], expected_revision=1)");
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 2; }));
  execute("assert p.selection()['table_id'] == t2 and p.selection()['record_id'] is None\n"
          "p.apply([{'op': 'delete_table', 'id': t2}], expected_revision=2)");
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 3; }));
  execute("assert p.selection()['table_id'] == t1 and p.selection()['record_id'] == r1\n"
          "p.apply([{'op': 'delete_table', 'id': t1}], expected_revision=3)");
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 4; }));
  execute("assert p.selection() == {'project_id': p.snapshot()['project']['id'], 'revision': 4, 'table_id': None, 'record_id': None}");
}

TEST_F(ScriptPython, ProjectSelectionRejectsMalformedOrMismatchedTargetsWithoutPartialChanges)
{
  ASSERT_NO_FATAL_FAILURE(selection_project());
  execute(R"PY(
before = p.selection()
for revision in (True, -1, 1.0, '1', 2**63):
    selection_rejected(dict(select_request, expected_revision=revision), 'invalid_params')
for key in ('table_id', 'record_id'):
    for value in (None, '', 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA', '1234', 5):
        selection_rejected(dict(select_request, **{key: value}), 'invalid_params')
selection_rejected(dict(select_request, extra=True), 'invalid_params')
selection_rejected(dict(select_request, expected_revision=0), 'conflict')
selection_rejected(dict(select_request, table_id=t2, record_id=r1), 'not_found')
selection_rejected(dict(select_request, record_id=str(uuid4())), 'not_found')
selection_rejected(dict(select_request, handle='another-opening'), 'conflict')
selection_rejected({'handle': p.handle, 'unexpected': True}, 'invalid_params', 'project.selection')
assert p.selection() == before and len(p.history()) == 1
)PY");
}

TEST_F(ScriptPython, ProjectSelectionReadKeepsActiveTextAndWritePreservesIndependentFilters)
{
  ASSERT_NO_FATAL_FAILURE(selection_project());
  auto &project = f.shell->store().project();
  const auto table = project.table_id();
  const auto first = project.record_id();
  const auto second = project.table()->records[1].id;
  ASSERT_TRUE(f.area("a2").set_tab_type(0, kEditorProject));
  ASSERT_TRUE(f.area("a3").set_tab_type(0, kEditorProject));
  f.drv->frame();
  f.screen.ui()->find("a2/main/table_search")->string.assign("red");
  f.screen.ui()->find("a3/main/table_search")->string.assign("blue");
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/table_search");
  f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::A, primary);
  f.drv->key(wm::Key::Unknown, wm::ModNone, "unfinished search");
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  execute("assert p.selection()['record_id'] == r1\nselection_rejected(select_request, 'busy')");
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "unfinished search");
  EXPECT_EQ(project.record_id(), first);
  f.drv->key(wm::Key::Enter);
  f.drv->frame();
  const auto layout = f.screen.to_json();
  execute("assert p.select(t1, r2, expected_revision=1)['record_id'] == r2");
  f.drv->frame();
  EXPECT_EQ(f.screen.to_json(), layout);
  EXPECT_EQ(project.record_id(), second);
  EXPECT_EQ(f.screen.ui()->find("a2/main/table_search")->string.value(), "unfinished search");
  EXPECT_EQ(f.screen.ui()->find("a3/main/table_search")->string.value(), "blue");
  EXPECT_EQ(f.screen.ui()->find("a2/main/" + table + "/records")->table->selected.value(), -1);
  EXPECT_EQ(f.screen.ui()->find("a3/main/" + table + "/records")->table->selected.value(), 0);
  EXPECT_EQ(project.project()->revision, 1);
  execute("assert p.select(t2, r3, expected_revision=1)['record_id'] == r3");
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/table_search")->string.value(), "unfinished search");
  EXPECT_EQ(f.screen.ui()->find("a3/main/table_search")->string.value(), "blue");
  EXPECT_EQ(f.screen.ui()->find("a2/main/" + project.table_id() + "/records")->table->rows, 0);
  execute("assert p.select(t1, r2, expected_revision=1)['record_id'] == r2");
  f.drv->frame();
  EXPECT_EQ(f.screen.ui()->find("a2/main/" + table + "/records")->table->selected.value(), -1);
  EXPECT_EQ(f.screen.ui()->find("a3/main/" + table + "/records")->table->selected.value(), 0);
}

TEST_F(ScriptPython, ProjectSelectionQueuedRequestsRejectNewRevisionAndDifferentOpening)
{
  ASSERT_NO_FATAL_FAILURE(selection_project());
  auto &project = f.shell->store().project();
  const auto table = project.table_id(), record = project.record_id();
  bool queued = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &data) {
    if (io::get_string(data, "operation").rfind("project.select", 0) == 0) { queued = true; }
  });
  ASSERT_TRUE(state().execute("selection_rejected(dict(select_request, table_id=t2, record_id=r3), 'conflict')"));
  ASSERT_TRUE(loop.pump_until([&] { return queued; })); // Deliberately leave UI dispatch queued.
  ASSERT_TRUE(project.apply(Json::array({{{"op", "rename_table"}, {"id", table}, {"name", "New revision"}}})));
  ASSERT_TRUE(loop.pump_until([&] { return !project.busy(); }));
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  EXPECT_EQ(project.table_id(), table); EXPECT_EQ(project.record_id(), record);
  queued = false;
  ASSERT_TRUE(state().execute("selection_rejected({'handle': p.handle}, 'conflict', 'project.selection')"));
  ASSERT_TRUE(loop.pump_until([&] { return queued; }));
  ASSERT_TRUE(project.create(dir.str() + "/other", "Other opening"));
  ASSERT_TRUE(loop.pump_until([&] { return !project.busy(); }));
  const auto other = project.project()->id;
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  EXPECT_EQ(project.project()->id, other);
  EXPECT_TRUE(project.table_id().empty()); EXPECT_TRUE(project.record_id().empty());
  EXPECT_EQ(project.project()->revision, 0);
}

TEST_F(ScriptPython, ProjectReviewOpensNativeDifferencesAndOnlyTheApplyButtonWrites)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.add_tab(kEditorPython));
  f.screen.set_maximized(&f.area("a1"));
  execute("before = p.snapshot()\naccepted = p.review(commands, expected_revision=0)\n"
          "assert accepted == {'accepted': True, 'project_id': before['project']['id'], 'base_revision': 0}\n"
          "assert p.snapshot() == before\nassert len(p.history()) == 0");
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  ASSERT_TRUE(project.review()) << project.review_error();
  EXPECT_EQ(project.project()->revision, 0);
  EXPECT_TRUE(project.tables().empty());
  EXPECT_EQ(area.editor().type().id, kEditorProject);
  EXPECT_EQ(f.screen.maximized(), &area);
  f.drv->frame();
  ASSERT_NE(f.screen.ui()->find("a2/main/review_rows"), nullptr);
  const auto *apply = f.screen.ui()->find("a2/main/review_apply");
  ASSERT_NE(apply, nullptr);
  ASSERT_TRUE(apply->enabled);
  const auto normalized = project.review()->commands;
  ASSERT_TRUE(normalized[0].contains("id"));
  apply->on_click();
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  ASSERT_EQ(project.tables().size(), 1u);
  EXPECT_EQ(project.tables()[0].id, normalized[0]["id"].get<std::string>());
  EXPECT_EQ(project.tables()[0].name, "Proposed cases");
  EXPECT_EQ(project.project()->revision, 1);
  EXPECT_FALSE(project.review());
  ASSERT_TRUE(project.undo());
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  EXPECT_TRUE(project.tables().empty());
  EXPECT_EQ(project.project()->revision, 2);
}

TEST_F(ScriptPython, ProjectReviewRejectsStaleMalformedAndExistingDraftRequests)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  const auto screen_before = f.screen.to_json();
  execute("for changes in [{'expected_revision': -1}, {'expected_revision': True},\n"
          "                {'expected_revision': 0.5}, {'expected_revision': 2**64-1},\n"
          "                {'handle': ''}, {'handle': None}, {'unknown': 1},\n"
          "                {'commands': []}, {'commands': {}}, {'commands': commands * 1001},\n"
          "                {'commands': [{'op': 'create_table', 'name': '温' * 90000}]}]:\n"
          "    rejected({**request, **changes}, 'invalid_params')\n"
          "rejected({**request, 'handle': 'different'}, 'conflict')\n"
          "rejected({**request, 'expected_revision': 1}, 'conflict')");
  EXPECT_EQ(f.screen.to_json(), screen_before);
  EXPECT_EQ(project.review_source(), "[]");
  project.set_review_source("my unfinished JSON draft");
  execute("rejected(request, 'conflict')");
  EXPECT_EQ(project.review_source(), "my unfinished JSON draft");
  project.discard_review();
  execute("p.review(commands, expected_revision=0)");
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  ASSERT_TRUE(project.review());
  const auto candidate = project.review();
  execute("rejected(request, 'conflict')");
  EXPECT_EQ(project.review(), candidate);
  // An intervening edit invalidates Apply but does not replace the inspected candidate.
  execute("p.apply([{'op': 'create_table', 'name': 'Other edit'}], expected_revision=0)");
  ASSERT_TRUE(pump([&] { return !project.busy() && project.project()->revision == 1; }));
  EXPECT_EQ(project.review(), candidate);
  EXPECT_FALSE(project.can_apply_review());
  project.discard_review();
  execute("rejected(request, 'conflict')\np.review(commands, expected_revision=1)");
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  ASSERT_TRUE(project.review());
  EXPECT_EQ(project.review()->base_revision, 1);
  EXPECT_EQ(project.project()->revision, 1);
  // Semantic command errors appear in the review page, after acceptance, without changing data.
  project.discard_review();
  execute("assert p.review([{'op': 'unknown_operation'}], expected_revision=1)['accepted']");
  ASSERT_TRUE(pump([&] { return !project.busy(); }));
  EXPECT_FALSE(project.review());
  EXPECT_FALSE(project.review_error().empty());
  EXPECT_EQ(project.project()->revision, 1);
}

TEST_F(ScriptPython, ProjectReviewChecksIdentityAfterQueueingAndNeverRetargets)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  execute("other = stk.projects.create(" + Json(dir.str() + "/other").dump() + ", 'Other')");
  bool requested = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &data) {
    if (io::get_string(data, "operation") == "project.review") { requested = true; }
  });
  ASSERT_TRUE(state().execute("rejected(request, 'conflict')"));
  ASSERT_TRUE(loop.pump_until([&] { return requested; }, 30));
  // Leave Screen::defer queued until the visible project has switched.
  ASSERT_TRUE(project.open(dir.str() + "/other"));
  ASSERT_TRUE(loop.pump_until([&] { return project.loaded() && !project.busy(); }));
  const auto before = f.screen.to_json();
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  EXPECT_EQ(f.screen.to_json(), before);
  EXPECT_EQ(project.review_source(), "[]");
  EXPECT_FALSE(project.review());
  EXPECT_EQ(project.project()->name, "Other");
  EXPECT_EQ(project.project()->revision, 0);
  EXPECT_TRUE(project.tables().empty());
}

TEST_F(ScriptPython, ProjectReviewPreservesTextStillBeingEdited)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  ASSERT_TRUE(area.editor().show_view("review"));
  f.screen.set_maximized(&area);
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
  f.drv->key(wm::Key::Unknown, wm::ModNone, "unfinished native draft");
  EXPECT_EQ(project.review_source(), "[]"); // The text widget has not committed its binding.
  execute("rejected(request, 'busy')");
  ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "unfinished native draft");
  EXPECT_EQ(project.review_source(), "[]");
  EXPECT_FALSE(project.review());
  f.drv->key(wm::Key::Enter, primary);
  EXPECT_EQ(project.review_source(), "unfinished native draft");
  execute("rejected(request, 'conflict')");
}

TEST_F(ScriptPython, ProjectReviewRunsFromConsoleShortcutAndAddsAProjectTab)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area);
  f.drv->frame();
  f.screen.ui()->find("a2/main/python_source")->string.assign("p.review(commands, expected_revision=0)");
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/python_source");
  f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::Enter, primary);
  ASSERT_TRUE(pump([&] { return !state().busy() && !project.busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  ASSERT_TRUE(project.review()) << project.review_error();
  EXPECT_EQ(area.editor().type().id, kEditorPython);
  auto *target = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(target, nullptr);
  EXPECT_NE(target, &area);
  EXPECT_EQ(target->editor().type().id, kEditorProject);
  EXPECT_GT(target->tab_count(), 1);
  f.drv->frame();
  EXPECT_NE(f.screen.ui()->find(target->id() + "/main/review_rows"), nullptr);
  EXPECT_EQ(project.project()->revision, 0);
}

TEST_F(ScriptPython, ProjectReviewDiscardDropsPendingPreviewAndDetachedRequestsDoNothing)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  auto &project = f.shell->store().project();
  bool requested = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &data) {
    if (io::get_string(data, "operation") == "project.review") { requested = true; }
  });
  ASSERT_TRUE(state().execute("p.review(commands, expected_revision=0)"));
  ASSERT_TRUE(loop.pump_until([&] { return requested; }, 30));
  f.screen.run_deferred(); // Accept, then discard before the preview callback can run.
  EXPECT_TRUE(project.busy());
  project.discard_review();
  ASSERT_TRUE(pump([&] { return !project.busy() && !state().busy(); }));
  EXPECT_FALSE(project.review());
  EXPECT_EQ(project.review_source(), "[]");
  EXPECT_EQ(project.project()->revision, 0);
  requested = false;
  ASSERT_TRUE(state().execute("p.review(commands, expected_revision=0)"));
  ASSERT_TRUE(loop.pump_until([&] { return requested; }, 30));
  f.shell->store().set_bridge(nullptr);
  const auto before = f.screen.to_json();
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
  EXPECT_FALSE(project.review());
  EXPECT_EQ(project.review_source(), "[]");
}

TEST_F(ScriptPython, LayoutRoundTripAndInvalidLayoutKeepTheCurrentScreen)
{
  const auto original = f.screen.to_json();
  execute("import copy\nsaved = stk.ui.layout()\nprint([e['id'] for e in stk.ui.editors()])\n"
          "changed = copy.deepcopy(saved)\n"
          "changed['screen'] = {'maximized': None, 'root': {'factor': 1, 'split': 'horizontal', 'children': ["
          "{'factor': 0.65, 'area': {'id': 'left', 'type': 'viewer'}},"
          "{'factor': 0.35, 'area': {'id': 'right', 'type': 'project'}}]}}\n"
          "stk.ui.apply_layout(changed)");
  EXPECT_EQ(f.screen.areas().size(), 2u);
  EXPECT_NE(output().find("viewer"), std::string::npos);
  const auto valid = f.screen.to_json();
  execute("bad = copy.deepcopy(changed)\nbad['screen']['root']['children'][1]['area']['id'] = 'left'\nstk.ui.apply_layout(bad)", "failed");
  EXPECT_EQ(f.screen.to_json(), valid);
  EXPECT_NE(output().find("invalid_params"), std::string::npos);
  execute("stk.ui.apply_layout(saved)");
  EXPECT_EQ(f.screen.to_json(), original);
  EXPECT_EQ(state().history().size(), 3u);
}

TEST_F(ScriptPython, ScriptsAndVisibleProjectUseTheSameRevisionedState)
{
  const auto directory = dir.str() + "/project";
  execute("p = stk.projects.create(" + Json(directory).dump() + ", 'Python project')\n"
          "stk.ui.open_project(" + Json(directory).dump() + ")\n"
          "p.apply([{'op': 'create_table', 'name': 'Cases'}], expected_revision=0)");
  auto &project = f.shell->store().project();
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy() && project.project()->revision == 1; }));
  ASSERT_EQ(project.tables().size(), 1u);
  EXPECT_EQ(project.tables()[0].name, "Cases");
  execute("print(stk.ui.current_project()['revision'])\nstk.project.apply([{'op': 'rename_table', 'id': p.snapshot()['tables'][0]['id'], 'name': 'Renamed'}], expected_revision=1)");
  ASSERT_TRUE(pump([&] { return !project.busy() && project.project()->revision == 2; }));
  EXPECT_EQ(project.tables()[0].name, "Renamed");
  execute("stk.project.apply([{'op': 'create_table', 'name': 'stale'}], expected_revision=0)", "failed");
  EXPECT_EQ(project.project()->revision, 2);
  execute("stk.ui.close_project()");
  EXPECT_FALSE(project.project());
  execute("stk.ui.open_project(" + Json(directory + "/missing").dump() + ")", "failed");
  EXPECT_FALSE(project.project());
}

TEST_F(ScriptPython, InterruptAndBridgeRestartNeverReplayUserCode)
{
  ASSERT_TRUE(state().execute("answer = 42\nprint('loop started', flush=True)\nwhile True:\n    pass"));
  ASSERT_TRUE(pump([&] { return output().find("loop started") != std::string::npos; }));
  EXPECT_FALSE(state().execute("print('must not run')"));
  ASSERT_TRUE(state().interrupt());
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  EXPECT_EQ(state().status().at("run").at("state"), "cancelled");
  execute("answer", "failed");
  execute("print('one execution')");
  const auto old_session = state().session();
  client->shutdown_bridge();
  ASSERT_TRUE(pump([&] { return state().ready() && state().desktop_ready() && state().session() != old_session; }, 60))
      << client->bridge_log().text();
  ASSERT_TRUE(pump([&] { return !state().busy(); }));
  const auto text = output();
  const auto first = text.find("one execution");
  ASSERT_NE(first, std::string::npos);
  EXPECT_EQ(text.find("one execution", first + 1), std::string::npos);
  execute("print('new session')");
}

TEST_F(ScriptPython, DetachedBridgeDoesNotRunQueuedLayoutMutations)
{
  auto layout = wm::layout_to_json(f.shell->capture_layout(f.screen, nullptr));
  layout["screen"] = {{"maximized", nullptr}, {"root", {{"factor", 1},
      {"area", {{"id", "replacement"}, {"type", "viewer"}}}}}};
  // Pump only bridge callbacks until the UI request has been queued on Screen::defer.
  bool requested = false;
  auto listener = client->on_event("ui.request", [&](const auto &, const auto &) { requested = true; });
  ASSERT_TRUE(state().execute("import json\nstk.ui.apply_layout(json.loads(" + Json(layout.dump()).dump() + "))"));
  ASSERT_TRUE(loop.pump_until([&] { return requested; }, 30));
  f.shell->store().set_bridge(nullptr);
  const auto before = f.screen.to_json();
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), before);
  // The old request cannot send a reply through a replacement/detached client.
  EXPECT_FALSE(state().ready());
}

TEST_F(ScriptPython, ConsoleEditorRunsMultilineDraftAndRestoresWithoutExecuting)
{
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto *source = f.screen.ui()->find("a2/main/python_source");
  ASSERT_NE(source, nullptr);
  EXPECT_TRUE(source->text_opts.multiline);
  source->string.assign("print('console 中文')\n40 + 2");
  f.drv->frame();
  const auto [x, y] = f.widget_center("a2/main/python_source");
  f.drv->click(x, y);
#ifdef __APPLE__
  constexpr auto primary = wm::ModOS;
#else
  constexpr auto primary = wm::ModCtrl;
#endif
  f.drv->key(wm::Key::End, primary);
  f.drv->key(wm::Key::Enter, primary);
  ASSERT_TRUE(pump([&] { return !state().busy() && state().status().contains("run") && state().status()["run"].is_object(); }));
  EXPECT_EQ(state().status()["run"]["state"], "succeeded") << output();
  EXPECT_NE(output().find("console 中文"), std::string::npos);
  EXPECT_NE(output().find("42"), std::string::npos);
  const auto run = state().status()["run"]["id"];
  const auto saved = f.shell->capture_layout(f.screen, nullptr);
  f.drv->click(x, y);
  ASSERT_NE(f.screen.ui()->editing(), 0u);
  f.shell->build_default_layout(f.screen);
  EXPECT_EQ(f.screen.ui(), nullptr); // old text bindings must not outlive their editor owner
  ASSERT_TRUE(f.shell->apply_layout(f.screen, saved));
  f.drv->frame();
  const auto *restored = f.screen.ui()->find("a2/main/python_source");
  ASSERT_NE(restored, nullptr);
  EXPECT_EQ(restored->string.value(), "print('console 中文')\n40 + 2");
  auto &restored_area = f.area("a2");
  auto context = restored_area.context(nullptr, nullptr);
  ASSERT_TRUE(restored_area.editor().on_drop({dir.str() + "/selected-only.py"}, context));
  f.drv->frame();
  loop.run_ready();
  EXPECT_EQ(state().status()["run"]["id"], run);
  EXPECT_EQ(restored_area.editor().save_state()["path"], dir.str() + "/selected-only.py");
}

TEST_F(ScriptPython, ViewerPayloadControlsKeepInvalidUpdatesAndStaleSourcesOut)
{
  const std::string path = std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp";
  execute("opened = stk.viewer.open(" + Json(path).dump() + ", focus=False)\n"
          "assert stk.viewer.wait(timeout=0)['has_payload']\n"
          "key = opened['source']['key']\n"
          "assert opened['source']['kind'] == 'payload'\n"
          "layer = next(layer for layer in opened['layers'] if layer['has_opacity'])\n"
          "stk.viewer.configure(overlays=False, auto_evaluate=False, prefetch=False, fps=2.5, loop=False)\n"
          "stk.viewer.layer(layer['id'], visible=False, opacity=0.25, expected_source=key)\n"
          "saved = stk.viewer.status()\n"
          "assert not saved['overlays'] and not saved['auto_evaluate'] and saved['fps'] == 2.5\n"
          "changed = next(item for item in saved['layers'] if item['id'] == layer['id'])\n"
          "assert not changed['visible'] and changed['opacity'] == 0.25");
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(viewer.payload());
  const auto source = viewer.source().key();
  execute("stk.viewer.configure(overlays=True, fps=0)", "failed");
  EXPECT_FALSE(viewer.overlays());
  execute("stk.viewer.layer(layer['id'], visible=True, opacity=2)", "failed");
  execute("assert not next(item for item in stk.viewer.status()['layers'] if item['id'] == layer['id'])['visible']");
  execute("stk.viewer.close(expected_source='different')", "failed");
  EXPECT_EQ(viewer.source().key(), source);
  execute("stk.viewer.open('missing.stkp')", "failed");
  EXPECT_EQ(viewer.source().key(), source);
  execute("stk.viewer.configure(parameters={'unknown': 3}, overlays=True)", "failed");
  EXPECT_FALSE(viewer.overlays());
  execute("stk.viewer.step(True)", "failed");
  execute("stk.viewer.play(True)", "failed");
  const auto camera = viewer.camera_serial();
  execute("stk.viewer.reset_camera(expected_source=key)\nstk.viewer.cancel(expected_source=key)");
  EXPECT_GT(viewer.camera_serial(), camera);
  execute("stk.viewer.close(expected_source=key)\nassert stk.viewer.status()['source']['kind'] == 'none'");
  EXPECT_FALSE(viewer.payload());
}

TEST_F(ScriptPython, ViewerSeriesStepAndPlaybackUseTheSameSharedTimeline)
{
  execute("import json, shutil\nfrom pathlib import Path\n"
          "folder = Path(" + Json(dir.str() + "/series").dump() + ")\n"
          "payload = Path(" + Json(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains").dump() + ")\n"
          "manifest = json.loads((payload / 'manifest.json').read_text())\nframes = []\n"
          "for step in [1, 5]:\n"
          "    name = f'view.{step}'\n"
          "    shutil.copytree(payload, folder / name)\n"
          "    result = {'schema': 'stk.graph-result/1', 'graph_sha256': '0'*64, 'graph_hash': 'sha256:' + '0'*64,\n"
          "              'profile': 'desktop', 'outputs': {'view': {'type': 'payload', 'manifest': manifest}},\n"
          "              'parameters': {'step': {'value': step, 'choices': []}}, 'keys': {}, 'evaluated': [],\n"
          "              'timings': {}, 'cache': {'hits': 0, 'misses': 0}, 'warnings': [], 'files': {'view': name + '/manifest.json'}}\n"
          "    result_name = f'result.{step}.json'\n"
          "    (folder / result_name).write_text(json.dumps(result))\n"
          "    frames.append({'step': step, 'outputs': {'view': name + '/manifest.json'}, 'result': result_name})\n"
          "(folder / 'series.json').write_text(json.dumps({'schema': 'stk.series/1', 'parameter': 'step', 'frames': frames}))\n"
          "opened = stk.viewer.open(folder, focus=False)\n"
          "assert opened['source']['kind'] == 'result' and opened['steps'] == [1, 5]\n"
          "assert stk.viewer.step(0)['shown_step'] == 1\n"
          "stk.viewer.configure(fps=4, loop=True)\n"
          "assert stk.viewer.play()['playing']\n"
          "assert not stk.viewer.play(False)['playing']\n"
          "assert stk.viewer.step(1)['shown_step'] == 5");
  auto &viewer = f.shell->store().viewer();
  EXPECT_EQ(viewer.step_index(), 1);
  EXPECT_EQ(viewer.shown_step(), Json(5));
  execute("stk.viewer.step(2)", "failed");
  EXPECT_EQ(viewer.step_index(), 1);
  execute("stk.viewer.step(0.5)", "failed");
  EXPECT_EQ(viewer.step_index(), 1);
}

TEST_F(ScriptPython, OfflineAnalysisFileButtonPreservesCurrentWorkAndOpensItsArchivedGrid)
{
  ASSERT_NO_FATAL_FAILURE(open_project());
  const std::string payload_path = std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp";
  ASSERT_NO_FATAL_FAILURE(execute("stk.project.apply([{'op':'create_table','name':'Keep existing work'}], expected_revision=0)\n"
      "stk.viewer.open(" + Json(payload_path).dump() + ", focus=False)"));
  auto &project = f.shell->store().project();
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(pump([&] { return !project.busy() && project.project()->revision == 1 && bool(viewer.payload()); }));
  const auto previous_handle = project.project()->handle;
  const auto previous_payload = viewer.payload();
  const auto previous_source = viewer.source().key();
  const auto evaluations = viewer.evaluations_started();
  const std::string destination = dir.str() + "/new analysis project";
  const std::string runner = dir.str() + "/Run local analysis.py";
  const std::string example = std::string(STK_REPO_ROOT) + "/examples/project_analysis/offline.py";
  ASSERT_TRUE(wmtest::write_text(runner,
      "import runpy\nfrom suan.scripting import API\n"
      "before = stk.project.snapshot()\nbefore_history = stk.project.history()\ncounts = {}\n"
      "def audited(operation, params):\n"
      "    counts[operation] = counts.get(operation, 0) + 1\n"
      "    return stk.call(operation, **params)\n"
      "example = runpy.run_path(" + Json(example).dump() + ")\n"
      "offline_analysis_demo = example['create_demo'](API(audited), " + Json(destination).dump() + ", wait_seconds=30)\n"
      "assert offline_analysis_demo['status'] == 'succeeded' and offline_analysis_demo['verified_result']\n"
      "assert counts['project.analysis_runs.prepare'] == counts['project.analysis_runs.start'] == 1\n"
      "assert counts['project.analysis_runs.result'] == 1\n"
      "assert not any(op.startswith(('ui.', 'runtime.', 'graph.', 'connection.', 'model.')) for op in counts)\n"
      "assert stk.project.snapshot() == before and stk.project.history() == before_history\n"));

  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
  f.screen.set_maximized(&area);
  f.drv->frame();
  const auto script_before = state().status().at("run").at("id");
  auto context = area.context(nullptr, nullptr);
  ASSERT_TRUE(area.editor().on_drop({runner}, context));
  f.drv->frame(); loop.run_ready();
  ASSERT_FALSE(std::filesystem::exists(destination));
  EXPECT_EQ(state().status().at("run").at("id"), script_before);
  EXPECT_FALSE(state().busy());
  // Run the selected file through a real pointer click, including the scroll needed
  // to reach the file controls below the Python input and output panels.
  const auto main_rect = area.find_region(EditorArea::kMain)->ui_rect();
  f.screen.ui()->handle_event(ui::Event::wheel({main_rect.x1() - 2, main_rect.cy()}, -1000));
  f.drv->frame();
  // A drop fills the path but does not change the panel's remembered closed state.
  // Explicitly expand it, just as the Run file instructions require.
  const auto *file_panel = f.screen.ui()->find("a2/main/python_file");
  ASSERT_NE(file_panel, nullptr);
  ASSERT_EQ(file_panel->rect.intersect(main_rect), file_panel->rect);
  const auto [panel_x, panel_y] = f.widget_center(file_panel->key);
  f.drv->click(panel_x, panel_y);
  f.screen.ui()->handle_event(ui::Event::wheel({main_rect.x1() - 2, main_rect.cy()}, -1000));
  f.drv->frame();
  const auto *file_path = f.screen.ui()->find("a2/main/python_file/python_path");
  ASSERT_NE(file_path, nullptr); EXPECT_EQ(file_path->string.value(), runner);
  EXPECT_EQ(state().status().at("run").at("id"), script_before);
  const auto *run_file = f.screen.ui()->find("a2/main/python_file/python_run_file");
  ASSERT_NE(run_file, nullptr); ASSERT_TRUE(run_file->enabled);
  ASSERT_EQ(run_file->rect.intersect(main_rect), run_file->rect);
  const auto layout_before = wm::layout_to_json(f.shell->capture_layout(f.screen, nullptr));
  const auto [run_x, run_y] = f.widget_center(run_file->key);
  f.drv->click(run_x, run_y);
  ASSERT_TRUE(pump([&] {
    f.drv->frame();
    return !state().busy() && state().status().contains("run") && state().status().at("run").is_object() &&
        state().status().at("run").at("id") != script_before;
  }, 60)) << output() << client->bridge_log().text();
  ASSERT_EQ(state().status().at("run").at("state"), "succeeded") << output();
  ASSERT_TRUE(state().error().empty()) << state().error();
  EXPECT_NE(output().find("Verified synthetic inline table: 73 rows"), std::string::npos);
  EXPECT_EQ(project.project()->handle, previous_handle); EXPECT_EQ(project.project()->revision, 1);
  EXPECT_EQ(viewer.payload(), previous_payload); EXPECT_EQ(viewer.source().key(), previous_source);
  EXPECT_EQ(wm::layout_to_json(f.shell->capture_layout(f.screen, nullptr)), layout_before);
  const auto receipt = io::parse_json(wmtest::read_text(destination + "/demo.json"));
  const auto project_id = receipt.at("project_id").get<std::string>();
  const auto analysis_id = receipt.at("analysis_id").get<std::string>();
  const auto run_id = receipt.at("run_id").get<std::string>();
  ASSERT_EQ(receipt.at("revision"), 3); ASSERT_TRUE(receipt.at("synthetic").get<bool>());

  const auto widget = [&](const char *key) { return f.screen.ui()->find(key); };
  const auto wait = [&](const std::function<bool()> &condition) {
    ASSERT_TRUE(pump([&] { f.drv->frame(); return condition(); })) << output() << client->bridge_log().text();
  };
  const auto click = [&](const char *key) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled); ASSERT_TRUE(value->on_click);
    value->on_click(); f.drv->frame();
  };
  const auto toggle = [&](const char *key) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr);
    const ui::Vec2 center{value->rect.cx(), value->rect.cy()};
    f.screen.ui()->handle_event(ui::Event::mouse_down(center));
    f.screen.ui()->handle_event(ui::Event::mouse_up(center)); f.drv->frame();
  };
  const auto select = [&](const char *key, const int column, const std::string &identity) {
    const auto *value = widget(key); ASSERT_NE(value, nullptr); ASSERT_TRUE(value->enabled); ASSERT_TRUE(value->table);
    const auto table = *value->table; int row = -1;
    for (int index = 0; index < table.rows; ++index) {
      const auto cell = table.cell(index, column);
      if (cell == identity || cell == Json(identity).dump()) { row = index; }
    }
    ASSERT_GE(row, 0) << identity; table.selected.assign(row); f.drv->frame();
  };
  const auto paragraph = [&](const std::string &scope) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &value : block->widgets()) {
        if (value.type == ui::WidgetType::Paragraph && value.key.find("/" + scope + "/") != std::string::npos) { return value.text; }
      }
    }
    return std::string();
  };

  // The script never switches projects. Use the explicit native Open action next.
  ASSERT_TRUE(area.set_tab_type(0, kEditorProject));
  f.drv->frame();
  f.screen.ui()->handle_event(ui::Event::wheel({main_rect.x1() - 2, main_rect.cy()}, 1000));
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(toggle("project_location"));
  ASSERT_NE(widget("a2/main/project_location/directory"), nullptr);
  widget("a2/main/project_location/directory")->string.assign(destination); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("a2/main/project_location/open"));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return project.loaded() && !project.busy() && project.project()->id == project_id; }));
  EXPECT_EQ(project.project()->revision, 3);
  ASSERT_TRUE(area.set_tab_type(0, kEditorAnalysisGraph));
  ASSERT_TRUE(area.editor().load_state({{"saved", true}}));
  area.find_region(EditorArea::kSidebar)->set_size_1x(550); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_list"));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return widget("analysis_documents") && widget("analysis_documents")->enabled; }));
  ASSERT_NO_FATAL_FAILURE(select("analysis_documents", 2, analysis_id));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return widget("analysis_rename") && widget("analysis_rename")->enabled; }));
  ASSERT_NE(widget("analysis_saved_section"), nullptr);
  widget("analysis_saved_section")->index.assign(1); f.drv->frame();
  if (!widget("analysis_run_list")) { ASSERT_NO_FATAL_FAILURE(toggle("analysis_run_history")); }
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_list"));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return widget("analysis_run_rows") && widget("analysis_run_rows")->enabled; }));
  ASSERT_EQ(widget("analysis_run_rows")->table->rows, 1);
  ASSERT_NO_FATAL_FAILURE(select("analysis_run_rows", 2, run_id.substr(0, 8)));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return widget("analysis_run_read_result") && widget("analysis_run_read_result")->enabled; }));
  EXPECT_EQ(widget("analysis_result_outputs"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("analysis_run_read_result"));
  ASSERT_NO_FATAL_FAILURE(wait([&] { return widget("analysis_result_outputs") && widget("analysis_result_outputs")->enabled; }));
  ASSERT_EQ(widget("analysis_result_outputs")->table->rows, 1);
  ASSERT_NO_FATAL_FAILURE(select("analysis_result_outputs", 0, "table"));
  ASSERT_NO_FATAL_FAILURE(click("analysis_result_table_grid"));
  ASSERT_NE(widget("analysis_table_grid"), nullptr);
  ASSERT_NE(widget("analysis_table_grid_jump_row"), nullptr);
  ASSERT_NE(widget("analysis_table_grid_jump_column"), nullptr);
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 64);
  widget("analysis_table_grid_jump_row")->string.assign("0"); f.drv->frame();
  widget("analysis_table_grid_jump_column")->string.assign("1"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_jump"));
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"temperature_difference\"");
  EXPECT_EQ(paragraph("analysis_table_grid_unit"), "\"K\"");
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "-9.5");
  widget("analysis_table_grid_jump_row")->string.assign("72"); f.drv->frame();
  widget("analysis_table_grid_jump_column")->string.assign("9"); f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("analysis_table_grid_jump"));
  EXPECT_EQ(widget("analysis_table_grid")->table->rows, 1);
  EXPECT_EQ(widget("analysis_table_grid")->table->cell(0, 0), "72");
  EXPECT_EQ(widget("analysis_table_grid")->table->selected.value(), 0);
  EXPECT_EQ(paragraph("analysis_table_grid_name"), "\"sample_7\"");
  EXPECT_EQ(paragraph("analysis_table_grid_value"), "576");
  EXPECT_EQ(viewer.payload(), previous_payload); EXPECT_EQ(viewer.source().key(), previous_source);
  EXPECT_EQ(viewer.evaluations_started(), evaluations); EXPECT_EQ(project.project()->revision, 3);
  ASSERT_NO_FATAL_FAILURE(execute("sample = stk.project\nruns = sample.analysis_runs.list()['runs']\n"
      "assert len(runs) == 1 and runs[0]['id'] == " + Json(run_id).dump() + "\n"
      "assert runs[0]['status'] == 'succeeded'\n"
      "assert sample.analysis_runs.get(runs[0]['id'])['result']['has_payload'] is False\n"
      "assert sample.runs.list()['runs'] == [] and sample.requests.list()['requests'] == []\n"));
}

#ifndef _WIN32  // The Windows bridge test environment intentionally has no NumPy/VTK.
TEST_F(ScriptPython, OfflineWorkbenchDemoBuildsProjectAndConfiguresThreeEditorsWithoutRuntime)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(pump([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60));
  execute("from examples.project_scan.offline import create_demo\n"
          "offline_demo = create_demo(stk, " + Json(dir.str() + "/offline").dump() + ")\n"
          "assert stk.ui.current_project()['id'] == offline_demo['project_id']\n"
          "assert stk.viewer.status()['has_payload']\n"
          "assert stk.projects.open(offline_demo['directory']).runs.list()['runs'] == []");
  EXPECT_EQ(f.screen.areas().size(), 3u);
  EXPECT_NE(f.screen.find_area("demo-project"), nullptr);
  EXPECT_NE(f.screen.find_area("demo-view"), nullptr);
  EXPECT_NE(f.screen.find_area("demo-python"), nullptr);
  EXPECT_TRUE(viewer.payload());
  EXPECT_EQ(viewer.source().kind, SourceKind::RunDir);
  auto &project = f.shell->store().project();
  ASSERT_TRUE(pump([&] { return project.loaded() && !project.busy(); }));
  EXPECT_EQ(project.tables().size(), 4u);  // parameters, controls, results and the file index
  EXPECT_EQ(project.project()->revision, 5);
  execute("stk.viewer.open(offline_demo['folders'][0] + '/field.vtk', preset='volume')\n"
          "shown = stk.viewer.wait(timeout=30)\n"
          "assert shown['has_payload'] and not shown['error'], shown\n"
          "assert shown['source']['field_file'] == 'field.vtk'\n"
          "assert shown['parameters']['path'] == 'field.vtk'");
  execute("stk.ui.apply_layout(offline_demo['previous_layout'])");
  EXPECT_EQ(f.screen.areas().size(), 4u);
}

TEST_F(ScriptPython, ViewerOpensSyntheticResultsAndReevaluatesExplicitParameters)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(pump([&] { viewer.pump(); return viewer.presets_loaded() && !viewer.catalog().is_null(); }, 60));
  execute("from pathlib import Path\nfrom examples.project_scan.solver import simulate\n"
          "directory = Path(" + Json(dir.str() + "/field").dump() + ")\n"
          "simulate({'temperature_K': 300, 'size': 5}, directory)\n"
          "assert any(p['id'] == 'volume' for p in stk.viewer.presets()['presets'])\n"
          "from examples.project_scan.show import show_directory\n"
          "shown = show_directory(stk, directory, focus=False)\n"
          "assert shown['has_payload'] and not shown['error'], shown\n"
          "assert shown['preset'] == 'volume' and shown['parameters']['path'] == 'field.vtk'\n"
          "key = shown['source']['key']\n"
          "stk.viewer.configure(auto_evaluate=False, parameters={'colormap': 'cividis'}, expected_source=key)\n"
          "assert stk.viewer.status()['pending_edit'] == 'client'\n"
          "stk.viewer.evaluate(expected_source=key)\n"
          "updated = stk.viewer.wait(timeout=25)\n"
          "assert updated['has_payload'] and not updated['error'], updated\n"
          "assert updated['parameters']['colormap'] == 'cividis'\n"
          "assert updated['evaluation']['id'] != shown['evaluation']['id']");
  EXPECT_TRUE(viewer.payload());
  EXPECT_EQ(viewer.source().kind, SourceKind::RunDir);
  const auto old_parameters = viewer.parameters();
  execute("stk.viewer.configure(parameters={'colormap': 'bad', 'path': 'missing.vtk'}, overlays=False)", "failed");
  EXPECT_EQ(viewer.parameters(), old_parameters);
  EXPECT_TRUE(viewer.overlays());
  execute("stk.viewer.configure(parameters={'path': 'missing.vtk'})\nstk.viewer.evaluate()\n"
          "failed = stk.viewer.wait(timeout=25)\nassert failed['error']");
}
#endif

}  // namespace
}  // namespace stk::app
