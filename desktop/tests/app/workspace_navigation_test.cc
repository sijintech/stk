/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>
#include "stk/app/model_settings.hh"
#include "stk/app/project_agent.hh"
#include "stk/app/project_archive.hh"
#include "stk/app/project_attention.hh"
#include "stk/app/project_discussion.hh"
#include "stk/app/project_state.hh"
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
#include <iterator>

namespace stk::app {
namespace {
using io::Json;

TEST(WorkspaceNavigation, EmptyWorkspaceHasOnlyProjectManagementAndSurvivesShellClosure)
{
  wmtest::AppFixture f;
  auto &area = f.area("a2");
  ASSERT_TRUE(area.set_tab_type(0, kEditorWorkspace));
  f.screen.set_maximized(&area); f.drv->frame();
  for (const auto *page : {"conversation", "files", "workflows", "analyses", "analysis_runs", "simulation_runs", "data"}) {
    const auto *w = f.screen.ui()->find(std::string("workspace_") + page);
    ASSERT_NE(w, nullptr); EXPECT_FALSE(w->enabled);
  }
  auto action = f.screen.ui()->find("workspace_project")->on_click;
  action(); f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);
  auto &target = f.area("a1");
  EXPECT_EQ(target.editor().type().id, kEditorProject);
  EXPECT_NE(f.screen.ui()->find("project_location/directory"), nullptr);
  auto back = f.screen.ui()->find("project_workspace")->on_click;
  back(); f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(area.editor().type().id, kEditorWorkspace);
  action = f.screen.ui()->find("workspace_project")->on_click;
  f.shell.reset();
  action(); back(); // Screens may outlive the shell in headless integrations.
}

bool shows(const wmtest::AppFixture &f, const std::string &text)
{
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &widget : block->widgets()) { if (widget.text == text) { return true; } }
  }
  return false;
}

/** The focused composer card: the box drawn exactly around the field and the action row below it (box padding
 * on every side, as Layout::box places its children). Null when no such surface was drawn. */
const ui::DrawCmd *composer_card(const ui::Context &ui, const ui::Widget &input, const ui::Widget &action)
{
  const float pad = ui.style().box_space;
  const auto near = [](float a, float b) { return std::abs(a - b) <= 1.0f; };
  for (const auto &command : ui.draw_list().cmds) {
    if (command.type == ui::CmdType::RoundBox && near(command.rect.x, input.rect.x - pad) &&
        near(command.rect.x1(), input.rect.x1() + pad) && near(command.rect.y, input.rect.y - pad) &&
        near(command.rect.y1(), action.rect.y1() + pad) && command.rect.contains(ui::Vec2{action.rect.cx(), action.rect.cy()})) {
      return &command;
    }
  }
  return nullptr;
}

/** The split view and ordinary maximization keep the stacked composer: no card, the action as wide as the field. */
void expect_split_composer(const ui::Context &ui, const ui::Widget *input, const ui::Widget *action)
{
  ASSERT_NE(input, nullptr);
  ASSERT_NE(action, nullptr);
  ASSERT_EQ(input->rect.intersect(input->clip), input->rect) << "the field must be drawn for the check to count";
  EXPECT_EQ(composer_card(ui, *input, *action), nullptr);
  EXPECT_EQ(action->rect.x, input->rect.x);
  EXPECT_EQ(action->rect.w, input->rect.w);
}

TEST(WorkspaceNavigation, GuidedWorkspaceRemainsAvailableAndOpensJobsAndViewerWithoutAProject)
{
  wmtest::AppFixture f;
  auto &home = f.area("a1");
  ASSERT_EQ(home.editor().type().id, kEditorFiles);
  for (int i = 0; i < home.tab_count(); ++i) {
    if (home.tab(i).type().id == kEditorWorkspace) { home.set_active_tab(i); break; }
  }
  ASSERT_EQ(home.editor().type().id, kEditorWorkspace);
  const int original_tabs = home.tab_count();
  f.screen.set_maximized(&home); // Explicitly expose the optional guide's buttons in this test.
  f.drv->frame();
  EXPECT_TRUE(shows(f, "1. Project  ·  next"));
  EXPECT_TRUE(shows(f, "3. Where to run"));
  EXPECT_FALSE(f.screen.ui()->find("workspace_data")->enabled);
  ASSERT_TRUE(f.screen.ui()->find("workspace_runtime")->enabled);
  auto [x, y] = f.widget_center("workspace_runtime");
  f.drv->click(x, y); f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(home.editor().type().id, kEditorJobs);
  EXPECT_EQ(home.tab_count(), original_tabs);
  for (int i = 0; i < home.tab_count(); ++i) {
    if (home.tab(i).type().id == kEditorWorkspace) { home.set_active_tab(i); break; }
  }
  f.screen.set_maximized(&home); f.drv->frame();
  std::tie(x, y) = f.widget_center("workspace_viewer");
  f.drv->click(x, y); f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);  // explicit navigation restores the peer panes
  EXPECT_EQ(f.area("a2").editor().type().id, kEditorViewer);
  EXPECT_EQ(home.editor().type().id, kEditorWorkspace);
}

TEST(WorkspaceNavigation, FocusedSectionsReuseEditorsAndRestoreTheSplitView)
{
  wmtest::AppFixture f;
  const auto areas = f.screen.areas();
  auto *viewer = &f.area("a2").editor();
  auto &state = f.shell->store().viewer();
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  state.open_payload(payload, "Existing result");
  const auto click = [&](const std::string &key) {
    const auto [x, y] = f.widget_center(key);
    f.drv->click(x, y);
    f.screen.run_deferred();
    f.drv->frame();
  };
  const auto expect_nav_paint = [&](const std::string &key, bool current) {
    auto &ctx = *f.screen.ui();
    const auto *button = ctx.find(key);
    ASSERT_NE(button, nullptr);
    const auto &commands = ctx.draw_list().cmds;
    const auto box = std::find_if(commands.begin(), commands.end(), [&](const ui::DrawCmd &cmd) {
      return cmd.type == ui::CmdType::RoundBox && cmd.rect == button->rect;
    });
    ASSERT_NE(box, commands.end());
    const auto &theme = ctx.theme();
    EXPECT_EQ(box->color, current ? theme.menu_item.inner_sel.blend(theme.header_back, 0.6f) : theme.pulldown.inner);
    EXPECT_EQ(box->outline, current ? theme.link : theme.pulldown.outline);
    if (current) {
      const auto label = std::find_if(commands.begin(), commands.end(), [&](const ui::DrawCmd &cmd) {
        return cmd.type == ui::CmdType::Text && cmd.text == button->text;
      });
      ASSERT_NE(label, commands.end());
      EXPECT_EQ(label->color, theme.menu_item.text_sel);
    }
  };
  f.drv->frame();
  const auto shown = state.payload();
  const auto camera = state.camera_serial();
  ASSERT_NE(f.screen.ui()->find("tool_workbench"), nullptr);
  click("tool_workbench");
  auto *home = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(home, nullptr);
  auto *conversation = &home->editor();
  ASSERT_EQ(conversation->type().id, kEditorAI);
  EXPECT_EQ(f.screen.ui()->find("tool_files"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("editor_type"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("tabs"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("area_menu"), nullptr);
  EXPECT_NE(f.screen.ui()->find("ai_tables"), nullptr);
  const auto *rail = home->find_region("workbench_rail");
  ASSERT_NE(rail, nullptr);
  EXPECT_FALSE(rail->rect().empty());
  EXPECT_EQ(home->find_region("main")->rect().xmin, rail->rect().xmax);
  const auto *home_button = f.screen.ui()->find("workbench_home");
  ASSERT_NE(home_button, nullptr);
  EXPECT_FALSE(home_button->enabled);
  expect_nav_paint("workbench_home", true);
  expect_nav_paint("workbench_split", false);

  click("workbench_tasks");
  auto *tasks = dynamic_cast<EditorArea *>(f.screen.maximized());
  ASSERT_NE(tasks, nullptr);
  EXPECT_EQ(tasks->editor().type().id, kEditorJobs);
  // Window/scale changes relocate the same controls without switching the active editor.
  f.drv->ctx.rect.xmax = 650;
  f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), tasks);
  EXPECT_TRUE(tasks->find_region("workbench_rail")->rect().empty());
  EXPECT_FALSE(tasks->find_region("workbench_strip")->rect().empty());
  expect_nav_paint("workbench_tasks", true);
  EXPECT_EQ(f.screen.ui()->find("editor_type"), nullptr);
  EXPECT_EQ(f.screen.ui()->find("area_menu"), nullptr);
  EXPECT_EQ(f.screen.ui()->find(tasks->id() + "/header/submit"), nullptr);
  EXPECT_NE(f.screen.ui()->find("focused_jobs/submit"), nullptr);
  EXPECT_NE(f.screen.ui()->find("refresh"), nullptr);
  click("workbench_results");
  ASSERT_EQ(f.screen.maximized(), &f.area("a2"));
  EXPECT_EQ(f.screen.ui()->find("editor_type"), nullptr);
  EXPECT_NE(f.screen.ui()->find("open"), nullptr);
  EXPECT_NE(f.screen.ui()->find("export"), nullptr);
  EXPECT_EQ(&f.area("a2").editor(), viewer);
  EXPECT_EQ(state.payload(), shown);
  EXPECT_EQ(state.camera_serial(), camera);
  click("workbench_home");
  ASSERT_EQ(f.screen.maximized(), home);
  EXPECT_EQ(&home->editor(), conversation);
  ASSERT_NE(f.screen.ui()->find("workbench_split"), nullptr);
  click("workbench_split");
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.areas(), areas);
  EXPECT_EQ(&f.area("a2").editor(), viewer);
  EXPECT_EQ(state.base_payload(), payload);
  EXPECT_EQ(state.camera_serial(), camera);
  EXPECT_NE(f.screen.ui()->find("tool_files"), nullptr);
  EXPECT_NE(f.screen.ui()->find("editor_type"), nullptr);
  EXPECT_NE(f.screen.ui()->find("area_menu"), nullptr);
}

TEST(WorkspaceNavigation, SavedFocusedWorkbenchAndOrdinaryMaximizationRestoreSeparately)
{
  wmtest::AppFixture source;
  source.shell->open_workbench(source.screen, true);
  source.drv->frame();
  ASSERT_EQ(source.screen.maximized(), &source.area("a2"));
  ASSERT_NE(source.screen.ui()->find("workbench_results"), nullptr);
  const auto saved = source.shell->capture_layout(source.screen, nullptr);
  ASSERT_EQ(saved.screen.at("workbench_focused"), true);

  wmtest::AppFixture reopened;
  ASSERT_TRUE(reopened.shell->apply_layout(reopened.screen, saved));
  reopened.drv->frame();
  ASSERT_EQ(reopened.screen.maximized(), &reopened.area("a2"));
  EXPECT_NE(reopened.screen.ui()->find("workbench_split"), nullptr);
  EXPECT_EQ(reopened.screen.areas().size(), source.screen.areas().size());

  auto invalid = saved;
  invalid.screen["maximized"] = nullptr;
  auto *viewer = &reopened.area("a2").editor();
  EXPECT_FALSE(reopened.shell->apply_layout(reopened.screen, invalid));
  EXPECT_EQ(reopened.screen.maximized(), &reopened.area("a2"));
  EXPECT_EQ(&reopened.area("a2").editor(), viewer);

  auto legacy = saved;
  legacy.screen.erase("workbench_focused");
  ASSERT_TRUE(reopened.shell->apply_layout(reopened.screen, legacy));
  reopened.drv->frame();
  EXPECT_EQ(reopened.screen.maximized(), &reopened.area("a2"));
  EXPECT_EQ(reopened.screen.ui()->find("workbench_split"), nullptr);
  EXPECT_NE(reopened.screen.ui()->find("tool_workbench"), nullptr);
}

class WorkspaceNavigationPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"workspace-navigation"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1280, 1000};
  std::unique_ptr<bridge::Client> client;
  ProjectState &project() { return f.shell->store().project(); }
  EditorArea &home() { return f.area("a1"); }
  const ui::Widget *widget(const std::string &key) { return f.screen.ui()->find(key); }
  std::string handle() { return project().project()->handle; }
  void idle()
  {
    ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
    ASSERT_TRUE(project().error().empty()) << project().error();
    f.drv->frame();
  }
  void go(const char *page)
  {
    f.shell->open_project_page_later(&f.screen, page, handle());
    f.screen.run_deferred(); f.drv->frame();
  }
  EditorArea &destination(const std::string &type)
  {
    for (auto *base : f.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base);
      if (area && area->editor().type().id == type) { return *area; }
    }
    ADD_FAILURE() << "No active destination: " << type;
    return home();
  }
  virtual void configure_bridge(bridge::ClientOptions &, const std::string &) {}
  void SetUp() override
  {
    std::string python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) { python = env; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge"; options.cache_dir = dir.str() + "/cache";
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime";
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = "";
    options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    configure_bridge(options, python);
    client = bridge::Client::create(options);
    ASSERT_TRUE(client->start()); ASSERT_TRUE(client->wait_ready(60)); loop.run_ready();
    f.shell->store().set_bridge(client.get()); project().sync();
    ASSERT_TRUE(project().create(dir.str() + "/project", "Workspace navigation"));
    ASSERT_NO_FATAL_FAILURE(idle()); ASSERT_TRUE(project().loaded());
    // This navigation fixture explicitly chooses one destination per editor. The product's
    // default and old saved layouts have separate coverage; shared AppFixture stays unchanged.
    ASSERT_TRUE(home().set_tabs({kEditorWorkspace, kEditorJobs, kEditorFiles}, 0));
    ASSERT_TRUE(f.area("a2").set_tabs({kEditorViewer, kEditorProject, kEditorTable}, 1));
    ASSERT_TRUE(f.area("a3").set_tabs({kEditorProperties, kEditorAI}, 1));
    ASSERT_TRUE(f.area("a4").set_tabs({kEditorLogs, kEditorAnalysisGraph}, 1));
    f.screen.set_maximized(&home()); f.drv->frame();
  }
  void TearDown() override
  {
    EXPECT_EQ(f.shell->store().viewer().evaluations_started(), 0);
    EXPECT_FALSE(f.shell->store().viewer().payload());
    project().attach(nullptr); f.shell->store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(WorkspaceNavigationPython, TheNextStepFollowsTheProjectAndItsParameters)
{
  // A fresh project has no parameter rows yet: parameters come next.
  EXPECT_TRUE(shows(f, "2. Parameters  ·  next"));
  EXPECT_TRUE(shows(f, "Open: Workspace navigation"));
  const std::string table = "11111111-1111-4111-8111-111111111111", record = "22222222-2222-4222-8222-222222222222";
  ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Cases"}},
      {{"op", "add_record"}, {"id", record}, {"table_id", table}}})));
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_TRUE(shows(f, "Parameter tables: 1 · rows: 1"));
  EXPECT_TRUE(shows(f, "3. Where to run  ·  next"));  // no Runtime in this test environment
  EXPECT_FALSE(shows(f, "2. Parameters  ·  next"));
}

TEST_F(WorkspaceNavigationPython, FocusedConversationKeepsDataAndModelControlsOnDemand)
{
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 720;
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto &discussion = project().discussion();
    return discussion.page("requests").loaded && !discussion.busy();
  }, 30));
  ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  ASSERT_TRUE(project().discussion().recent_requests_supported());
  const std::string question = "ai_question/" + handle();
  ASSERT_NE(widget(question), nullptr);
  widget(question)->string.assign("An unsent question about these cases.");
  const auto expect_composer_in_view = [&] {
    for (const std::string &key : {question, std::string("ai_prepare")}) {
      const auto *control = widget(key);
      ASSERT_NE(control, nullptr);
      EXPECT_GE(control->rect.y, control->clip.y);
      EXPECT_LE(control->rect.y1(), control->clip.y1());
    }
    // The field, why preparing is blocked and Prepare share one card, Prepare on its right and unclipped.
    const auto &ui = *f.screen.ui();
    const auto *input = widget(question), *prepare = widget("ai_prepare");
    const auto *card = composer_card(ui, *input, *prepare);
    ASSERT_NE(card, nullptr) << "no card drawn around the question and Prepare";
    EXPECT_EQ(prepare->rect.x1(), input->rect.x1());
    EXPECT_LT(prepare->rect.w, input->rect.w * 0.5f);
    EXPECT_GE(prepare->rect.w, ui.measurer().width(prepare->text, ui.style().font) + 2 * ui.style().text_margin);
    bool status_on_card = false;
    for (const auto &block : ui.blocks()) {
      for (const auto &item : block->widgets()) {
        status_on_card |= item.text == f.shell->store().tr("ai.no_context") && item.rect.y > input->rect.y1() &&
            item.rect.y1() <= prepare->rect.y && item.rect.x >= card->rect.x && item.rect.x1() <= card->rect.x1();
      }
    }
    EXPECT_TRUE(status_on_card) << "the reason Prepare is unavailable sits on the card above it";
    EXPECT_EQ(widget("ai_transcript"), nullptr);
    EXPECT_EQ(widget("ai_send_saved"), nullptr);
    EXPECT_EQ(widget("ai_history"), nullptr);
    EXPECT_NE(widget("ai_all_saved_questions"), nullptr);
    EXPECT_TRUE(shows(f, "Start with a scientific question"));
    EXPECT_TRUE(shows(f, "No context captured yet. Capture a record before preparing a question."));
    EXPECT_FALSE(shows(f, "Ask about selected data. Each request sends only its saved question and captured context."));
    EXPECT_FALSE(widget("ai_prepare")->enabled);
  };
  ASSERT_NO_FATAL_FAILURE(expect_composer_in_view());
  ASSERT_NE(widget("ai_workbench_context_settings"), nullptr);
  EXPECT_EQ(widget("ai_capture"), nullptr);
  const auto click = [&](const char *key) {
    const auto [x, y] = f.widget_center(key);
    f.drv->click(x, y);
    f.screen.run_deferred();
    f.drv->frame();
  };
  click("ai_workbench_context_settings");
  EXPECT_NE(widget("ai_capture"), nullptr);
  click("ai_workbench_context_settings");
  EXPECT_EQ(widget("ai_capture"), nullptr);
  click("workbench_results");
  f.drv->ctx.rect.xmax = 680;
  f.drv->ctx.rect.ymax = 620;
  f.drv->frame();
  click("workbench_home");
  ASSERT_NO_FATAL_FAILURE(expect_composer_in_view());
  ASSERT_NE(widget(question), nullptr);
  EXPECT_EQ(widget(question)->string.value(), "An unsent question about these cases.");
  EXPECT_EQ(widget("ai_capture"), nullptr);
  EXPECT_TRUE(project().discussion().context().empty());
  EXPECT_TRUE(project().discussion().exchange_id().empty());
  EXPECT_EQ(project().project()->revision, 0);
}

TEST_F(WorkspaceNavigationPython, FocusedOverviewAndWorkbenchNameDifferentDestinations)
{
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 900;
  f.drv->ctx.ui_scale = 2.0f;
  auto &viewer = f.shell->store().viewer();
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  viewer.open_payload(payload, "Existing result");
  const auto camera = viewer.camera_serial();
  auto *viewer_editor = &f.area("a2").tab(0);
  auto *overview_editor = &home().editor();
  const auto areas = f.screen.areas();
  auto &other = f.area("a3");
  auto *other_conversation = &other.editor();
  ASSERT_EQ(other_conversation->type().id, kEditorAI);
  f.screen.set_maximized(&other);
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  f.drv->frame();
  const auto question = "ai_question/" + handle();
  ASSERT_NE(widget(question), nullptr);
  widget(question)->string.assign("A different AI editor's unsent question");
  ASSERT_TRUE(home().add_tab(kEditorAI));
  f.screen.set_maximized(&home());
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  f.drv->frame();
  ASSERT_EQ(f.screen.maximized(), &home());
  auto *conversation = &home().editor();
  ASSERT_NE(conversation, other_conversation);
  ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  const auto *overview = widget("project_workspace");
  ASSERT_NE(overview, nullptr);
  EXPECT_EQ(overview->text, "Overview");
  const auto &ui = *f.screen.ui();
  EXPECT_GE(overview->rect.w, ui.measurer().width("Overview", ui.style().font) + 2 * ui.style().text_margin);
  ASSERT_NE(widget(question), nullptr);
  widget(question)->string.assign("Keep my question while checking the overview");
  const auto click = [&](const char *key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    EXPECT_TRUE(f.drv->click(x, y)) << key;
  };

  ASSERT_NO_FATAL_FAILURE(click("project_workspace"));
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.areas(), areas);
  EXPECT_EQ(&home().editor(), overview_editor);
  EXPECT_EQ(&other.editor(), other_conversation);
  EXPECT_NE(widget("workspace_project"), nullptr);
  ASSERT_NE(widget("project_workspace"), nullptr);
  EXPECT_EQ(widget("project_workspace")->text, "Home");
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(f.screen.maximized(), &home());
  EXPECT_EQ(&home().editor(), conversation);
  ASSERT_NE(widget(question), nullptr);
  EXPECT_EQ(widget(question)->string.value(), "Keep my question while checking the overview");
  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  EXPECT_EQ(&f.area("a2").editor(), viewer_editor);
  EXPECT_EQ(viewer.base_payload(), payload);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(project().project()->revision, 0);
  viewer.close();
}

TEST_F(WorkspaceNavigationPython, FocusedOverviewDoesNotOverrideLaterSplitNavigation)
{
  ASSERT_TRUE(home().add_tab(kEditorAI));
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  f.drv->frame();
  ASSERT_EQ(f.screen.maximized(), &home());
  auto &other = f.area("a3");
  ASSERT_EQ(other.editor().type().id, kEditorAI);
  const auto click = [&](const char *key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    EXPECT_TRUE(f.drv->click(x, y)) << key;
  };
  ASSERT_NO_FATAL_FAILURE(click("project_workspace"));
  ASSERT_EQ(f.screen.maximized(), nullptr);
  ASSERT_EQ(home().editor().type().id, kEditorWorkspace);

  // A manual tab change in the split has superseded the overview, even if the
  // user then returns to the same overview and both AI editors are still alive.
  home().set_active_tab(2);
  home().set_active_tab(0);
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(f.screen.maximized(), &other);
  EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
  EXPECT_EQ(project().project()->revision, 0);
}

TEST_F(WorkspaceNavigationPython, VisibleButtonsReuseEditorsAndRevealFilesAndBothRunHistories)
{
  auto &viewer = f.shell->store().viewer();
  ASSERT_TRUE(viewer.open_path(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  const auto payload = viewer.payload(); ASSERT_TRUE(payload);
  const auto source = viewer.source().key();
  const auto camera = viewer.camera_serial();
  const auto revision = project().project()->revision;
  auto *tables = &f.area("a2").editor(), *ai = &f.area("a3").editor(), *graph = &f.area("a4").editor();
  auto *files = &home().tab(2);
  const int n2 = f.area("a2").tab_count(), n3 = f.area("a3").tab_count(), n4 = f.area("a4").tab_count();
  const auto click = [&](const char *page) {
    f.screen.set_maximized(&home()); f.drv->frame();
    const auto key = std::string("workspace_") + page;
    ASSERT_NE(widget(key), nullptr); ASSERT_TRUE(widget(key)->enabled);
    const auto [x, y] = f.widget_center(key); f.drv->click(x, y); f.screen.run_deferred(); f.drv->frame();
  };
  ASSERT_NO_FATAL_FAILURE(click("files"));
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(&destination(kEditorFiles).editor(), files); EXPECT_NE(widget("files_tree"), nullptr);
  EXPECT_EQ(widget(destination(kEditorFiles).id() + "/main/project_view"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("simulation_runs"));
  EXPECT_EQ(&destination(kEditorProject).editor(), tables); EXPECT_NE(widget("project_runs/list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("analysis_runs"));
  EXPECT_EQ(&destination(kEditorAnalysisGraph).editor(), graph); ASSERT_NE(widget("analysis_saved_section"), nullptr);
  EXPECT_EQ(widget("analysis_saved_section")->index.value(), 1); EXPECT_NE(widget("analysis_run_list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("analyses"));
  EXPECT_EQ(&destination(kEditorAnalysisGraph).editor(), graph); EXPECT_EQ(widget("graph_mode")->index.value(), 2);
  EXPECT_EQ(widget("analysis_saved_section")->index.value(), 0); EXPECT_NE(widget("analysis_list"), nullptr);
  go("workspace"); ASSERT_NO_FATAL_FAILURE(click("conversation"));
  EXPECT_EQ(&destination(kEditorAI).editor(), ai);
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(project().project()->revision, revision);
  EXPECT_EQ(f.area("a2").tab_count(), n2); EXPECT_EQ(f.area("a3").tab_count(), n3); EXPECT_EQ(f.area("a4").tab_count(), n4);
  EXPECT_EQ(viewer.payload(), payload); EXPECT_EQ(viewer.source().key(), source);
  EXPECT_EQ(viewer.camera_serial(), camera); EXPECT_EQ(viewer.evaluations_started(), 0);
  viewer.close();
}

TEST_F(WorkspaceNavigationPython, FilesShowsExistingIndexWithoutEditingOrChangingSelection)
{
  { std::ofstream file(dir.path() / "input.txt"); file << "input fixture"; }
  ASSERT_TRUE(project().index_files({core::path_to_utf8(dir.path() / "input.txt")}));
  ASSERT_NO_FATAL_FAILURE(idle());
  const auto revision = project().project()->revision;
  const auto table = io::get_string(project().file_index(), "table_id"); ASSERT_FALSE(table.empty());
  const auto snapshot = project().tables();
  const auto selected = project().table_id(), record = project().record_id();
  go("files");
  EXPECT_EQ(project().table_id(), selected); EXPECT_EQ(project().record_id(), record);
  EXPECT_EQ(project().project()->revision, revision);
  f.screen.set_maximized(&destination(kEditorFiles)); f.drv->frame();
  const auto *panel = widget("files_registered"); ASSERT_NE(panel, nullptr);
  const auto [x, y] = f.widget_center(panel->key); f.drv->click(x, y);
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget("files_registrations") != nullptr; }, 30));
  EXPECT_EQ(widget("files_registrations")->table->rows, 1);
  EXPECT_EQ(project().tables().size(), snapshot.size());
}

TEST_F(WorkspaceNavigationPython, OldActionsRefuseProjectSwitchCloseReopenAndDestroyedSource)
{
  auto old = widget("workspace_files")->on_click;
  const auto original = handle();
  ASSERT_TRUE(project().close()); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().open(dir.str() + "/project")); ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_NE(handle(), original);
  const auto layout = f.screen.to_json(); old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), layout);
  old = widget("workspace_files")->on_click;
  ASSERT_TRUE(project().create(dir.str() + "/other", "Other project")); ASSERT_NO_FATAL_FAILURE(idle());
  old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), layout);
  old = widget("workspace_files")->on_click;
  ASSERT_TRUE(home().set_tab_type(0, kEditorLogs)); const auto destroyed = f.screen.to_json();
  old(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), destroyed);
}

TEST_F(WorkspaceNavigationPython, IndependentFilesKeepsCellDraftsInHiddenTabsAndOtherWindows)
{
  const std::string table = "aabbccdd-1111-4111-8111-111111111111";
  const std::string field = "aabbccdd-2222-4222-8222-222222222222";
  const std::string record = "aabbccdd-3333-4333-8333-333333333333";
  ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Parameters"}},
      {{"op", "add_field"}, {"id", field}, {"table_id", table}, {"name", "Temperature"}, {"type", "number"}},
      {{"op", "add_record"}, {"id", record}, {"table_id", table}},
      {{"op", "set_cell"}, {"table_id", table}, {"record_id", record}, {"field_id", field}, {"value", 300}}
  })));
  ASSERT_NO_FATAL_FAILURE(idle());
  { std::ofstream file(dir.path() / "input.txt"); file << "input fixture"; }
  ASSERT_TRUE(project().index_files({core::path_to_utf8(dir.path() / "input.txt")}));
  ASSERT_NO_FATAL_FAILURE(idle());
  project().select_table(table); project().select_record(record); go("data");
  f.screen.set_maximized(&destination(kEditorTable)); f.drv->frame();
  ASSERT_EQ(project().table_id(), table);
  const auto revision = project().project()->revision;
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *grid = widget("records");
    return grid && grid->table && grid->table->rows == 1 && grid->table->cell(0, 1) == "300";
  }, 30));
  const auto *details = widget("table_details");
  ASSERT_NE(details, nullptr); ASSERT_TRUE(details->enabled && details->on_click);
  details->on_click(); f.drv->frame();
  ASSERT_NE(widget("cell_value"), nullptr); widget("cell_value")->string.assign("1e"); f.drv->frame();
  ASSERT_FALSE(f.area("a2").editor().can_change_project_selection(project().project()->id));
  go("workspace"); f.area("a2").set_active_tab(0); // Keep the dirty Project editor hidden behind Viewer.

  wm::Screen other; f.shell->install(other, nullptr); f.shell->build_default_layout(other);
  struct ForgetScreen {
    AppShell *shell; wm::Screen *screen;
    ~ForgetScreen() { shell->forget(*screen); }
  } cleanup{f.shell.get(), &other};
  wmtest::ScreenDriver driver(other, 1000, 1000, 1);
  auto *area = dynamic_cast<EditorArea *>(other.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorProject)); other.set_maximized(area); driver.frame();
  const auto *cell = other.ui()->find("cell_value"); ASSERT_NE(cell, nullptr);
  const auto layout = f.screen.to_json(), other_layout = other.to_json();
  ASSERT_EQ(project().table_id(), table);
  ASSERT_FALSE(f.area("a2").tab(2).can_change_project_selection(project().project()->id));
  go("files");
  EXPECT_NE(f.screen.to_json(), layout); EXPECT_EQ(other.to_json(), other_layout);
  EXPECT_EQ(destination(kEditorFiles).editor().type().id, kEditorFiles);
  EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().record_id(), record);
  cell->string.assign("2e"); driver.frame();
  ASSERT_FALSE(area->editor().can_change_project_selection(project().project()->id));

  go("data"); f.screen.set_maximized(&destination(kEditorTable)); f.drv->frame();
  ASSERT_NE(widget("cell_value"), nullptr);
  EXPECT_EQ(widget("cell_value")->string.value(), "1e");
  ASSERT_NE(widget("reload_cell"), nullptr); widget("reload_cell")->on_click(); f.drv->frame();
  go("workspace");
  go("files"); EXPECT_EQ(destination(kEditorFiles).editor().type().id, kEditorFiles);
  EXPECT_EQ(project().table_id(), table);
  ASSERT_NE(other.ui()->find("cell_value"), nullptr);
  EXPECT_EQ(other.ui()->find("cell_value")->string.value(), "2e");
  ASSERT_NE(other.ui()->find("reload_cell"), nullptr); other.ui()->find("reload_cell")->on_click(); driver.frame();
  go("data");
  f.screen.set_maximized(&destination(kEditorTable)); f.drv->frame();
  ASSERT_NE(widget("manage_objects"), nullptr);
  const auto [x, y] = f.widget_center("manage_objects"); f.drv->click(x, y); f.drv->frame();
  ASSERT_NE(widget("manage_objects/rename_table"), nullptr);
  widget("manage_objects/rename_table")->string.assign("Unsaved table name"); f.drv->frame();
  go("workspace");
  go("files"); EXPECT_EQ(destination(kEditorFiles).editor().type().id, kEditorFiles);
  EXPECT_EQ(project().table_id(), table);
  go("data"); f.screen.set_maximized(&destination(kEditorTable)); f.drv->frame();
  ASSERT_NE(widget("manage_objects/rename_table"), nullptr);
  EXPECT_EQ(widget("manage_objects/rename_table")->string.value(), "Unsaved table name");
  ASSERT_NE(widget("manage_objects/reload_names"), nullptr); widget("manage_objects/reload_names")->on_click(); f.drv->frame();
  go("files"); EXPECT_EQ(project().table_id(), table); EXPECT_EQ(project().record_id(), record);
  EXPECT_NE(widget("files_tree"), nullptr); EXPECT_EQ(project().project()->revision, revision);
}

TEST_F(WorkspaceNavigationPython, DeferredNavigationRefusesChangedSourceAndClosedScreen)
{
  auto action = widget("workspace_files")->on_click;
  action(); ASSERT_TRUE(home().add_tab(kEditorLogs)); const auto changed = f.screen.to_json();
  f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), changed);
  home().set_active_tab(0); f.drv->frame();
  action = widget("workspace_files")->on_click; action();
  f.shell->forget(f.screen); const auto closed = f.screen.to_json();
  f.screen.run_deferred(); action(); EXPECT_EQ(f.screen.to_json(), closed);
}

TEST_F(WorkspaceNavigationPython, FullTabsDoNotReplaceAnEditorOrChangeSelection)
{
  for (auto *base : f.screen.areas()) {
    auto *area = dynamic_cast<EditorArea *>(base); ASSERT_NE(area, nullptr);
    for (int i = 0; i < area->tab_count(); ++i) {
      if (area->tab(i).type().id == kEditorFiles) { ASSERT_TRUE(area->set_tab_type(i, kEditorLogs)); }
    }
    while (area->tab_count() < 16) { ASSERT_TRUE(area->add_tab(kEditorLogs, false)); }
  }
  f.drv->frame(); const auto layout = f.screen.to_json(); const auto selected = project().table_id();
  go("files"); EXPECT_EQ(f.screen.to_json(), layout); EXPECT_EQ(project().table_id(), selected);
}

TEST_F(WorkspaceNavigationPython, AnotherWindowActiveInputPreventsProjectNavigation)
{
  wm::Screen other; f.shell->install(other, nullptr); f.shell->build_default_layout(other);
  struct ForgetScreen {
    AppShell *shell; wm::Screen *screen;
    ~ForgetScreen() { shell->forget(*screen); }
  } cleanup{f.shell.get(), &other};
  wmtest::ScreenDriver driver(other, 1000, 800, 1);
  auto *area = dynamic_cast<EditorArea *>(other.find_area("a2")); ASSERT_NE(area, nullptr);
  ASSERT_TRUE(area->set_tab_type(0, kEditorPython)); other.set_maximized(area); driver.frame();
  const auto *source = other.ui()->find("python_source"); ASSERT_NE(source, nullptr);
  driver.click(int(source->rect.cx()), other.rect().ymax - 1 - int(source->rect.cy()));
  ASSERT_TRUE(other.ui()->text_input_active());
  const auto text = other.ui()->edit_state()->text(); const auto layout = f.screen.to_json();
  go("files"); EXPECT_EQ(f.screen.to_json(), layout); EXPECT_EQ(other.ui()->edit_state()->text(), text);
  driver.key(wm::Key::Esc); go("files"); EXPECT_EQ(destination(kEditorFiles).editor().type().id, kEditorFiles);
}

TEST_F(WorkspaceNavigationPython, ReturningToConversationKeepsItsUnsentQuestion)
{
  go("conversation");
  const auto key = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(key) != nullptr; }, 30));
  widget(key)->string.assign("Compare these cases without starting a simulation.");
  f.drv->frame(); ASSERT_NE(widget("project_workspace"), nullptr);
  widget("project_workspace")->on_click(); f.screen.run_deferred(); f.drv->frame();
  ASSERT_EQ(destination(kEditorWorkspace).editor().type().id, kEditorWorkspace);
  go("conversation");
  ASSERT_NE(widget(key), nullptr);
  EXPECT_EQ(widget(key)->string.value(), "Compare these cases without starting a simulation.");
  EXPECT_EQ(project().project()->revision, 0);
}

class SavedConversationNavigationPython : public WorkspaceNavigationPython {
 protected:
  static constexpr const char *kFirst = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  static constexpr const char *kSecond = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  static constexpr const char *kTable = "11111111-1111-4111-8111-111111111111";
  static constexpr const char *kRow = "22222222-2222-4222-8222-222222222222";
  static constexpr const char *kField = "33333333-3333-4333-8333-333333333333";

  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    const auto script = dir.path() / "observe.py";
    std::ofstream(script) << R"PY(
from pathlib import Path
from suan.desktop_bridge import server
from suan.desktop_bridge.__main__ import main
from suan.desktop_bridge.literature import LiteratureService
from suan.desktop_bridge.protocol import BridgeError
from suan.project.agent_sessions import HARNESS, digest
from uuid import uuid4

literature_call = LiteratureService.call
def traced_literature(self, action, params):
    with Path(__file__).with_name("literature_calls").open("a") as trace:
        trace.write(action + "\n")
    return literature_call(self, action, params)
LiteratureService.call = traced_literature

original = server.Bridge.__init__
def init(self, *args, **kwargs):
    original(self, *args, **kwargs)
    create = self.methods["project.requests.create"]
    add_message = self.methods["project.discussion.add"]
    get_agent = self.methods["project.agent.get"]
    def read_agent(params, call):
        fail = Path(__file__).with_name("fail_next_agent_read")
        if fail.exists():
            fail.unlink()
            raise BridgeError("unavailable", "fixture agent history read failed")
        return get_agent(params, call)
    def save(params, call):
        if Path(__file__).with_name("forbid_question_preparation").exists():
            return unexpected(params, call)
        result = create(params, call)
        seed = Path(__file__).with_name("seed_agent_history")
        if seed.exists():
            seed.unlink()
            sessions = self.projects._get(params["handle"]).agent_sessions
            for identity, text in (("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Agent\nAlpha"),
                                   ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "Agent Bravo")):
                turn = str(uuid4())
                sessions.create(identity, {"id": identity, "harness": HARNESS}, text,
                                turn_id=turn, request_sha256=digest({"text": text, "turn_id": turn}))
        status_seed = Path(__file__).with_name("request_status")
        if status_seed.exists():
            status = status_seed.read_text()
            status_seed.unlink()
            requests = self.projects._get(params["handle"]).requests
            request = result["request"]["id"]
            if status == "cancelled":
                result["request"] = requests.cancel(request)
            else:
                owner = str(uuid4())
                running, claimed = requests._claim(request, executor_id=owner)
                assert claimed
                if status == "completed":
                    answer = Path(__file__).with_name("saved_answer")
                    text = answer.read_text() if answer.exists() else "Saved answer"
                    answer.unlink(missing_ok=True)
                    result["request"] = requests._complete(request, executor_id=owner, text=text)
                elif status == "uncertain-cancel":
                    result["request"] = requests.cancel(request)
                elif status in ("failed", "uncertain"):
                    code = {"failed": "adapter_failed", "uncertain": "transport_uncertain"}[status]
                    result["request"] = requests._settle(request, executor_id=owner, status=status, code=code)
                else:
                    assert status == "running"
                    result["request"] = running
        return result
    def unexpected(params, call):
        Path(__file__).with_name("unexpected_write").touch()
        raise BridgeError("unavailable", "fixture forbids writes during navigation")
    def add(params, call):
        if Path(__file__).with_name("forbid_question_preparation").exists():
            return unexpected(params, call)
        return add_message(params, call)
    self.methods["project.requests.create"] = save
    self.methods["project.discussion.add"] = add
    self.methods["project.agent.get"] = read_agent
    def observe(method, original_read):
        def read(params, call):
            with Path(__file__).with_name("history_reads").open("a") as trace:
                trace.write(method + "\n")
            return original_read(params, call)
        return read
    for method in ("project.requests.list", "project.requests.get", "project.requests.progress", "project.conversations.search"):
        self.methods[method] = observe(method, self.methods[method])
    if Path(__file__).with_name("legacy_conversation_search").exists():
        self.methods.pop("project.conversations.search")
    for method in ("project.requests.start", "project.agent.create", "project.agent.say",
                   "project.agent.start", "project.agent.run_target", "project.agent.run_decide",
                   "models.local.start", "project.attention.viewed"):
        self.methods[method] = unexpected

server.Bridge.__init__ = init
main()
)PY";
    options.command = {python, "-u", core::path_to_utf8(script), "--stdio", "--state-dir",
                       options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
  }

  void prepare_table()
  {
    ASSERT_TRUE(project().apply(Json::array({
        {{"op", "create_table"}, {"id", kTable}, {"name", "Saved results"}},
        {{"op", "add_field"}, {"id", kField}, {"table_id", kTable}, {"name", "Value"}, {"type", "number"}},
        {{"op", "add_record"}, {"id", kRow}, {"table_id", kTable}},
        {{"op", "set_cell"}, {"table_id", kTable}, {"record_id", kRow}, {"field_id", kField}, {"value", 300}}
    })));
    ASSERT_NO_FATAL_FAILURE(idle());
  }

  void save_question(const char *id, const char *question, bool completed = false)
  {
    save_question_state(id, question, completed ? "completed" : "pending");
  }

  void save_question_state(const char *id, const char *question, const std::string &status,
                           const char *adapter = "test-controlled")
  {
    auto &discussion = project().discussion();
    ASSERT_TRUE(discussion.capture(kTable, {kRow}, {kField}, question));
    ASSERT_TRUE(loop.pump_until([&] { return !discussion.busy(); }, 30)) << discussion.error();
    ASSERT_TRUE(discussion.add_message(question));
    ASSERT_TRUE(loop.pump_until([&] { return !discussion.busy(); }, 30)) << discussion.error();
    ASSERT_TRUE(discussion.message().contains("id")) << discussion.error();
    if (status != "pending") { std::ofstream(dir.path() / "request_status") << status; }
    std::optional<bridge::Result<Json>> result;
    client->call("project.requests.create",
                 {{"handle", handle()}, {"request_id", id}, {"message_id", discussion.message().at("id")},
                  {"configuration", {{"adapter", status == "completed" ? "test-completed" : adapter},
                                     {"model", "fixture-v1"}}}})
        .then([&](auto reply) { result = std::move(reply); });
    ASSERT_TRUE(loop.pump_until([&] { return result.has_value(); }, 30));
    ASSERT_TRUE(result->ok()) << result->error().describe();
    ASSERT_EQ(result->value().at("request").at("status"), status == "uncertain-cancel" ? "uncertain" : status);
  }

  /** literature.* actions the bridge served, in order (traced by the fixture's wrapper). */
  std::vector<std::string> literature_calls()
  {
    std::vector<std::string> calls;
    std::ifstream trace(dir.path() / "literature_calls");
    for (std::string line; std::getline(trace, line);) { calls.push_back(line); }
    return calls;
  }

  std::string attention_key(const char *id, const char *status)
  {
    return std::string("workspace_attention_open/request:") + id + ":" + status;
  }

  void show_attention(const char *id, const char *status = "pending")
  {
    f.screen.set_maximized(&home());
    auto &attention = f.shell->store().attention();
    const auto key = attention_key(id, status);
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      if (widget(key)) { return true; }
      if (!attention.busy()) { attention.refresh(); }
      return false;
    }, 30)) << attention.error();
    ASSERT_TRUE(widget(key)->enabled);
  }

  void TearDown() override
  {
    WorkspaceNavigationPython::TearDown();
    EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
  }
};

TEST_F(SavedConversationNavigationPython, AttentionReopensEachSavedQuestionAndKeepsBothDrafts)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  auto &discussion = project().discussion();
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "First saved question"));
  const auto first_context = discussion.context();
  ASSERT_NO_FATAL_FAILURE(save_question(kSecond, "Second saved question", true));
  const auto compose_context = discussion.context();
  ASSERT_NE(first_context, compose_context);

  go("conversation");
  const auto question = "ai_question/" + handle();
  const auto intent = "ai_intent/" + handle();
  const auto agent_text = "ai_agent_text/" + handle();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(question) != nullptr; }, 30));
  widget(question)->string.assign("Unsent discussion draft");
  ASSERT_NE(widget(intent), nullptr);
  widget(intent)->index.assign(3);
  f.drv->frame();
  ASSERT_NE(widget(agent_text), nullptr);
  widget(agent_text)->string.assign("Unsent agent draft");

  const auto open = [&](const char *id, const char *text, const char *status, const Json &context) {
    ASSERT_NO_FATAL_FAILURE(show_attention(id, status));
    widget(attention_key(id, status))->on_click();
    f.screen.run_deferred();
    EXPECT_EQ(f.screen.maximized(), nullptr);
    EXPECT_EQ(discussion.exchange_id(), id);
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      return !discussion.exchange_busy() && io::get_string(discussion.exchange_question(), "text") == text;
    }, 30)) << discussion.exchange_error();
    EXPECT_EQ(io::get_string(discussion.exchange_request(), "id"), id);
    EXPECT_EQ(io::get_string(discussion.exchange_request(), "status"), status);
    EXPECT_EQ(io::get_string(discussion.exchange_context(), "id"), io::get_string(context, "id"));
    EXPECT_EQ(discussion.context(), compose_context);
    ASSERT_NE(widget(question), nullptr);
    EXPECT_EQ(widget(question)->string.value(), "Unsent discussion draft");
  };
  ASSERT_NO_FATAL_FAILURE(open(kFirst, "First saved question", "pending", first_context));
  ASSERT_NO_FATAL_FAILURE(open(kSecond, "Second saved question", "completed", compose_context));
  EXPECT_EQ(io::get_string(discussion.exchange_reply(), "text"), "Saved answer");
  ASSERT_NE(widget(intent), nullptr);
  widget(intent)->index.assign(3);
  f.drv->frame();
  ASSERT_NE(widget(agent_text), nullptr);
  EXPECT_EQ(widget(agent_text)->string.value(), "Unsent agent draft");
  EXPECT_EQ(project().project()->revision, 1);
}

TEST_F(SavedConversationNavigationPython, AttentionRefusesSourceABAAndTheReopenedProjectHandle)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Saved before reopening"));
  ASSERT_NO_FATAL_FAILURE(show_attention(kFirst));
  auto open = widget(attention_key(kFirst, "pending"))->on_click;
  open();
  home().set_active_tab(1);
  home().set_active_tab(0);
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.maximized(), &home());
  EXPECT_TRUE(project().discussion().exchange_id().empty());

  ASSERT_NO_FATAL_FAILURE(show_attention(kFirst));
  open = widget(attention_key(kFirst, "pending"))->on_click;
  open();
  const auto original = handle();
  const auto project_id = project().project()->id;
  ASSERT_TRUE(project().close());
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_TRUE(loop.pump_until([&] { return !project().busy(); }, 30));
  ASSERT_TRUE(project().loaded());
  ASSERT_EQ(project().project()->id, project_id);
  ASSERT_NE(handle(), original);
  open();
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.maximized(), &home());
  EXPECT_TRUE(project().discussion().exchange_id().empty());
}

TEST_F(SavedConversationNavigationPython, UnreadAgentSessionCannotSendOrSetATarget)
{
  go("conversation");
  auto &agent = project().agent();
  ASSERT_TRUE(agent.supported());
  const auto intent = "ai_intent/" + handle();
  const auto text = "ai_agent_text/" + handle();
  ASSERT_NE(widget(intent), nullptr);
  widget(intent)->index.assign(3);
  // An ID can outlive its saved session in a history menu. Keep the draft while confirming it.
  agent.select(kFirst);
  f.drv->frame();
  ASSERT_NE(widget(text), nullptr);
  widget(text)->string.assign("An unsent agent draft");
  const auto verify = [&] {
    ASSERT_NE(widget("ai_agent_send"), nullptr);
    EXPECT_FALSE(widget("ai_agent_send")->enabled);
    widget("ai_agent_send")->on_click();
    if (agent.runs_supported()) {
      ASSERT_NE(widget("ai_agent_set_target"), nullptr);
      EXPECT_FALSE(widget("ai_agent_set_target")->enabled);
      widget("ai_agent_set_target")->on_click();
    }
    EXPECT_EQ(widget(text)->string.value(), "An unsent agent draft");
    EXPECT_EQ(agent.selected(), kFirst);
    EXPECT_FALSE(agent.busy());
  };
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(verify());
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !agent.error().empty(); }, 30));
  EXPECT_TRUE(agent.view().empty());
  ASSERT_NO_FATAL_FAILURE(verify());
  EXPECT_EQ(project().project()->revision, 0);
}

TEST_F(SavedConversationNavigationPython, RecentQuestionsOpenFromTasksAndResultsAtBothWidths)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "First saved question"));
  ASSERT_NO_FATAL_FAILURE(save_question(kSecond, "Second saved question", true));
  auto &discussion = project().discussion();
  const auto compose_context = discussion.context();
  const auto question = "ai_question/" + handle();
  const auto click = [&](const std::string &key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred();
    f.drv->frame();
  };
  const auto wait_for_question = [&](const char *id) {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      return !discussion.exchange_busy() && !discussion.busy() &&
             io::get_string(discussion.exchange_request(), "id") == id && widget(question);
    }, 30)) << discussion.exchange_error();
    ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  };

  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  ASSERT_NO_FATAL_FAILURE(wait_for_question(kSecond));
  EXPECT_NE(widget("ai_transcript"), nullptr);
  EXPECT_EQ(widget("ai_history"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("ai_all_saved_questions"));
  EXPECT_NE(widget("ai_history"), nullptr);
  EXPECT_NE(widget("ai_history_refresh"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("ai_all_saved_questions"));
  EXPECT_EQ(widget("ai_history"), nullptr);
  widget(question)->string.assign("Draft stays in the workbench");
  auto *conversation = f.screen.maximized();
  ASSERT_NO_FATAL_FAILURE(click("workbench_tasks"));
  ASSERT_EQ(dynamic_cast<EditorArea &>(*f.screen.maximized()).editor().type().id, kEditorJobs);
  const auto first = std::string("workbench_question/") + kFirst;
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(first) && widget(first)->enabled; }, 30));
  ASSERT_NO_FATAL_FAILURE(click(first));
  ASSERT_NO_FATAL_FAILURE(wait_for_question(kFirst));
  EXPECT_EQ(f.screen.maximized(), conversation);
  EXPECT_EQ(io::get_string(discussion.exchange_question(), "text"), "First saved question");
  EXPECT_EQ(widget(question)->string.value(), "Draft stays in the workbench");

  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  auto *results = f.screen.maximized();
  const auto camera = f.shell->store().viewer().camera_serial();
  f.drv->ctx.rect.xmax = 680;
  f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), results);
  EXPECT_EQ(widget(first), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  const ui::Widget *second = nullptr;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &candidate : block->widgets()) {
      if (candidate.type == ui::WidgetType::MenuItem && candidate.text.ends_with("Second saved question")) {
        second = &candidate;
      }
    }
  }
  ASSERT_NE(second, nullptr);
  EXPECT_EQ(second->menu_index, 2);  // Compose and browse come before the newest question.
  const auto key = second->key;
  ASSERT_NO_FATAL_FAILURE(click(key));
  ASSERT_NO_FATAL_FAILURE(wait_for_question(kSecond));
  EXPECT_EQ(f.screen.maximized(), conversation);
  EXPECT_EQ(io::get_string(discussion.exchange_reply(), "text"), "Saved answer");
  EXPECT_EQ(widget(question)->string.value(), "Draft stays in the workbench");
  EXPECT_EQ(discussion.context(), compose_context);
  EXPECT_EQ(project().project()->revision, 1);
  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  EXPECT_EQ(f.screen.maximized(), results);
  EXPECT_EQ(f.shell->store().viewer().camera_serial(), camera);

  // A changed list must close an open menu before the old row can name another question.
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  const auto menu_id = widget("workbench_history")->id;
  auto &archive = f.shell->store().archive();
  ASSERT_TRUE(archive.set("request", {kSecond}, true));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *items = discussion.recent_requests();
    return items && items->size() == 1 && io::get_string(items->front(), "request_id") == kFirst;
  }, 30)) << discussion.recent_requests_error();
  ASSERT_NE(widget("workbench_history"), nullptr);
  EXPECT_NE(widget("workbench_history")->id, menu_id);
  EXPECT_EQ(widget(key), nullptr);
  EXPECT_EQ(f.screen.maximized(), results);
  EXPECT_EQ(discussion.exchange_id(), kSecond);
  ASSERT_NO_FATAL_FAILURE(click("workbench_home"));
  ASSERT_NO_FATAL_FAILURE(click("ai_all_saved_questions"));
  ASSERT_TRUE(discussion.busy());  // The unarchived list began reading when Workbench reopened.
  ASSERT_NO_FATAL_FAILURE(click("ai_history_show_archived"));
  EXPECT_TRUE(discussion.show_archived("requests"));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto &page = discussion.page("requests");
    return page.loaded && page.items.size() == 1 && io::get_string(page.items.front(), "id") == kSecond;
  }, 30)) << discussion.error();
  EXPECT_EQ(widget(question)->string.value(), "Draft stays in the workbench");
}

TEST_F(SavedConversationNavigationPython, SearchOpensAnOlderQuestionWithoutWritingOrLosingTheDraft)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Old lattice comparison"));
  for (int index = 0; index < 9; ++index) {
    const auto id = "cccccccc-cccc-4ccc-8ccc-ccccccccccc" + std::to_string(index);
    ASSERT_NO_FATAL_FAILURE(save_question(id.c_str(), "Newer temperature result"));
  }
  std::ofstream(dir.path() / "forbid_question_preparation").put('\n');
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  const auto click = [&](const std::string &key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred(); f.drv->frame();
  };
  auto &discussion = project().discussion();
  const auto input = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return discussion.recent_requests() && widget(input); }, 30));
  ASSERT_EQ(widget(std::string("workbench_question/") + kFirst), nullptr);
  widget(input)->string.assign("Keep this local draft");
  const auto camera = f.shell->store().viewer().camera_serial();

  for (bool narrow : {false, true}) {
    ASSERT_NO_FATAL_FAILURE(click("workbench_tasks"));
    const auto visible = discussion.exchange_id();
    f.drv->ctx.rect.xmax = narrow ? 680 : 1600;
    f.drv->frame();
    if (narrow) {
      ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
      std::string launcher;
      for (const auto &block : f.screen.ui()->blocks()) {
        for (const auto &item : block->widgets()) {
          if (item.type == ui::WidgetType::MenuItem && item.text == "Search conversations") { launcher = item.key; }
        }
      }
      ASSERT_FALSE(launcher.empty());
      ASSERT_NO_FATAL_FAILURE(click(launcher));
    }
    else { ASSERT_NO_FATAL_FAILURE(click("workbench_search_conversations")); }
    const auto *query = widget("conversation_search/query");
    ASSERT_NE(query, nullptr);
    EXPECT_EQ(f.screen.ui()->focused(), query->id);
    if (narrow) {
      const auto newer = "conversation_search/open/question/cccccccc-cccc-4ccc-8ccc-ccccccccccc0";
      ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, "temperature"));
      ASSERT_TRUE(f.drv->key(wm::Key::Enter)); f.drv->frame();
      ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(newer) && widget(newer)->enabled; }, 30));
      ASSERT_TRUE(f.drv->key(wm::Key::Enter)); f.screen.run_deferred(); f.drv->frame();
      ASSERT_NE(widget(newer), nullptr);
      EXPECT_EQ(discussion.exchange_id(), visible);
      ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, " "));
      ASSERT_TRUE(f.drv->key(wm::Key::Home, wm::ModShift));
    }
    ASSERT_TRUE(f.drv->key(wm::Key::Unknown, wm::ModNone, "comparison lattice"));
    if (!narrow) {
      f.drv->ctx.rect.xmax = 680;
      f.drv->frame();
      const auto *resized_query = widget("conversation_search/query");
      ASSERT_NE(resized_query, nullptr);
      ASSERT_EQ(f.screen.ui()->focused(), resized_query->id);
      ASSERT_NE(f.screen.ui()->edit_state(), nullptr);
      EXPECT_EQ(f.screen.ui()->edit_state()->text(), "comparison lattice");
    }
    ASSERT_TRUE(f.drv->key(wm::Key::Enter)); f.drv->frame();
    const auto match = std::string("conversation_search/open/question/") + kFirst;
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(match) && widget(match)->enabled; }, 30));
    if (!narrow) {
      f.drv->ctx.rect.xmax = 1600;
      f.drv->frame();
      ASSERT_NE(widget(match), nullptr);
      ASSERT_TRUE(widget(match)->enabled);
    }
    EXPECT_EQ(discussion.exchange_id(), visible);
    wm::Event repeated;
    repeated.type = wm::EventType::KeyDown;
    repeated.key = wm::Key::Enter;
    repeated.is_repeat = true;
    ASSERT_TRUE(f.drv->send(repeated));
    f.screen.run_deferred(); f.drv->frame();
    ASSERT_NE(widget(match), nullptr);
    EXPECT_EQ(discussion.exchange_id(), visible);
    if (narrow) { ASSERT_NO_FATAL_FAILURE(click(match)); }
    else { ASSERT_TRUE(f.drv->key(wm::Key::Enter)); f.screen.run_deferred(); f.drv->frame(); }
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame(); return !discussion.exchange_busy() && widget(input) && discussion.exchange_id() == kFirst;
    }, 30));
    EXPECT_EQ(io::get_string(discussion.exchange_question(), "text"), "Old lattice comparison");
    EXPECT_EQ(widget(input)->string.value(), "Keep this local draft");
    EXPECT_EQ(f.shell->store().viewer().camera_serial(), camera);
    EXPECT_EQ(project().project()->revision, 1);
    EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
    EXPECT_EQ(widget("conversation_search/query"), nullptr);
  }

  f.drv->ctx.rect.xmax = 1600;
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("workbench_search_conversations"));
  f.drv->ctx.rect.xmax = 680;
  f.drv->frame();
  ASSERT_NE(widget("conversation_search/query"), nullptr);
  ASSERT_TRUE(f.drv->key(wm::Key::Esc));
  f.drv->frame();
  ASSERT_EQ(widget("conversation_search/query"), nullptr);
  ASSERT_NE(widget("workbench_history"), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), widget("workbench_history")->id);
  f.drv->ctx.rect.xmax = 1600;
  f.drv->frame();
  EXPECT_EQ(widget("conversation_search/query"), nullptr);
}

class LegacyConversationSearchPython : public SavedConversationNavigationPython {
 protected:
  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    SavedConversationNavigationPython::configure_bridge(options, python);
    std::ofstream(dir.path() / "legacy_conversation_search").put('\n');
  }
};

TEST_F(LegacyConversationSearchPython, OlderBridgeKeepsRecentHistoryWithoutTheSearchAction)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Saved on an older bridge"));
  f.drv->ctx.rect.xmax = 1600;
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  const auto existing = std::string("workbench_question/") + kFirst;
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(existing) && widget(existing)->enabled; }, 30));
  ASSERT_TRUE(client->hello_info());
  EXPECT_FALSE(client->hello_info()->has_method("project.conversations.search"));
  EXPECT_EQ(widget("workbench_search_conversations"), nullptr);
  EXPECT_NE(widget("workbench_saved_questions"), nullptr);
}

TEST_F(SavedConversationNavigationPython, BrowseSavedQuestionsBeyondTheRecentRailWithoutSelectingOrWriting)
{
  auto &state = project();
  auto &discussion = state.discussion();
  auto &viewer = f.shell->store().viewer();
  struct CloseViewer {
    ViewerState &state;
    ~CloseViewer() { state.close(); }
  } close_viewer{viewer};
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  {
    std::ofstream answer(dir.path() / "saved_answer");
    answer << "Saved answer\n";
    for (int line = 0; line < 90; ++line) { answer << "Older reply row " << line << '\n'; }
  }
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Question older than the recent list", true));
  for (char digit = '1'; digit <= '8'; ++digit) {
    const std::string id = std::string(8, digit) + "-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    ASSERT_NO_FATAL_FAILURE(save_question(id.c_str(), "Newer saved question"));
  }
  std::ofstream(dir.path() / "forbid_question_preparation").put('\n');
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) +
      "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  viewer.open_payload(payload, "Already open");
  f.shell->open_workbench(f.screen, true);
  f.screen.run_deferred();
  f.drv->frame();
  auto *results = f.screen.maximized();
  ASSERT_NE(results, nullptr);
  const auto camera = viewer.camera_serial();
  const auto reads = [&] {
    std::ifstream log(dir.path() / "history_reads");
    std::vector<std::string> methods;
    for (std::string line; std::getline(log, line);) { methods.push_back(std::move(line)); }
    return methods;
  };
  const auto click = [&](const std::string &key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred();
    f.drv->frame();
  };
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *recent = discussion.recent_requests();
    return recent && recent->size() == 8;
  }, 30));
  ASSERT_EQ(widget(std::string("workbench_question/") + kFirst), nullptr);
  ASSERT_TRUE(discussion.exchange_id().empty());
  const auto before = reads();
  ASSERT_NO_FATAL_FAILURE(click("workbench_saved_questions"));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *history = widget("ai_history");
    return history && history->items.size() == 9 && history->enabled;
  }, 30));
  ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  auto *ai = f.screen.maximized();
  ASSERT_NE(ai, results);
  EXPECT_TRUE(discussion.exchange_id().empty());
  const auto loaded = reads();
  ASSERT_EQ(loaded.size(), before.size() + 1);
  EXPECT_EQ(loaded.back(), "project.requests.list");
  const auto context = discussion.context();
  ASSERT_NO_FATAL_FAILURE(click("ai_history"));
  ASSERT_TRUE(f.drv->key(wm::Key::Home));
  ASSERT_TRUE(f.drv->key(wm::Key::Enter));
  f.screen.run_deferred();
  const auto draft = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return !discussion.exchange_busy() && discussion.exchange_id() == kFirst && widget(draft);
  }, 30));
  EXPECT_EQ(io::get_string(discussion.exchange_question(), "text"), "Question older than the recent list");
  EXPECT_TRUE(io::get_string(discussion.exchange_reply(), "text").starts_with("Saved answer\n"));
  EXPECT_EQ(discussion.context(), context);
  EXPECT_EQ(f.screen.maximized(), ai);
  widget(draft)->string.assign("Keep the unsent question");
  const auto selected = discussion.exchange_request();
  const auto reading_position = [&] {
    const auto *transcript = widget("ai_transcript");
    return transcript ? f.screen.ui()->scroll_of(transcript->id) : -1.0f;
  };
  const auto page_up = [&] {
    ASSERT_NO_FATAL_FAILURE(click("ai_transcript"));
    const auto tail = reading_position();
    ASSERT_TRUE(f.drv->key(wm::Key::PageUp));
    f.drv->frame();
    EXPECT_GT(reading_position(), 0.0f);
    EXPECT_LT(reading_position(), tail);
  };
  const auto return_and_check = [&](const float scroll, const std::string &text) {
    ASSERT_NO_FATAL_FAILURE(click("ai_return_question"));
    EXPECT_EQ(widget("ai_return_question"), nullptr);
    EXPECT_EQ(f.screen.maximized(), ai);
    ASSERT_NE(widget("ai_transcript"), nullptr);
    ASSERT_NE(widget(draft), nullptr);
    EXPECT_LT(widget("ai_transcript")->rect.y, widget(draft)->rect.y);
    EXPECT_EQ(f.screen.ui()->focused(), widget("ai_transcript")->id);
    EXPECT_EQ(reading_position(), scroll);
    EXPECT_EQ(widget(draft)->string.value(), text);
    EXPECT_EQ(discussion.exchange_request(), selected);
    EXPECT_EQ(discussion.context(), context);
  };
  ASSERT_NO_FATAL_FAILURE(page_up());
  const auto wide_position = reading_position();
  const auto before_wide_return = reads();
  ASSERT_NO_FATAL_FAILURE(click("workbench_write_question"));
  ASSERT_NE(widget(draft), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), widget(draft)->id);
  ASSERT_NE(widget("ai_return_question"), nullptr);
  const auto stale_return = widget("ai_return_question")->on_click;
  ASSERT_TRUE(f.drv->key(wm::Key::X, wm::ModNone, "x"));
  ASSERT_TRUE(f.screen.ui()->text_input_active());
  ASSERT_NO_FATAL_FAILURE(return_and_check(wide_position, "Keep the unsent questionx"));
  EXPECT_EQ(reads(), before_wide_return);
  ASSERT_TRUE(f.drv->key(wm::Key::PageDown));
  f.drv->frame();
  ASSERT_GT(reading_position(), wide_position);

  const auto after_page = reading_position();
  ASSERT_NO_FATAL_FAILURE(click("workbench_write_question"));
  stale_return();
  f.drv->frame();
  ASSERT_NE(widget("ai_return_question"), nullptr);
  ASSERT_NO_FATAL_FAILURE(return_and_check(after_page, "Keep the unsent questionx"));
  EXPECT_EQ(reads(), before_wide_return);

  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  ASSERT_EQ(f.screen.maximized(), results);
  f.drv->ctx.rect.xmax = 680;
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  const auto *browse = widget("workbench_history");
  ASSERT_NE(browse, nullptr);
  std::string entry;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) {
      if (item.type == ui::WidgetType::MenuItem && item.text == f.shell->store().tr("ai.history")) { entry = item.key; }
    }
  }
  ASSERT_FALSE(entry.empty());
  const auto warm = reads();
  ASSERT_NO_FATAL_FAILURE(click(entry));
  ASSERT_EQ(f.screen.maximized(), ai);
  ASSERT_NE(widget("ai_history"), nullptr);
  EXPECT_EQ(reads(), warm);
  EXPECT_EQ(discussion.exchange_id(), kFirst);
  ASSERT_NO_FATAL_FAILURE(click("ai_close_saved_questions"));
  ASSERT_NE(widget(draft), nullptr);
  EXPECT_EQ(widget(draft)->string.value(), "Keep the unsent questionx");
  EXPECT_EQ(discussion.exchange_id(), kFirst);
  ASSERT_NO_FATAL_FAILURE(page_up());
  const auto narrow_position = reading_position();
  const auto before_narrow_return = reads();
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  std::string compose_entry;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) {
      if (item.type == ui::WidgetType::MenuItem && item.text == f.shell->store().tr("ai.write_question")) {
        compose_entry = item.key;
      }
    }
  }
  ASSERT_FALSE(compose_entry.empty());
  ASSERT_NO_FATAL_FAILURE(click(compose_entry));
  ASSERT_NE(widget(draft), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), widget(draft)->id);
  discussion.set_show_archived("requests", true);
  f.drv->frame();
  ASSERT_FALSE(discussion.page("requests").loaded);
  ASSERT_TRUE(f.drv->key(wm::Key::Y, wm::ModNone, "y"));
  ASSERT_NO_FATAL_FAILURE(return_and_check(narrow_position, "Keep the unsent questionxy"));
  EXPECT_FALSE(discussion.page("requests").loaded);
  EXPECT_EQ(reads(), before_narrow_return);
  discussion.set_show_archived("requests", false);
  ASSERT_TRUE(f.drv->key(wm::Key::PageDown));
  f.drv->frame();
  EXPECT_GT(reading_position(), narrow_position);
  EXPECT_EQ(viewer.payload(), payload);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(state.project()->revision, 1);

  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  ASSERT_NO_FATAL_FAILURE(click(entry));
  ASSERT_NE(widget("ai_close_saved_questions"), nullptr);
  const auto directory = state.project()->directory;
  const auto old_handle = handle();
  ASSERT_TRUE(state.close());
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(widget("ai_close_saved_questions"), nullptr);
  ASSERT_TRUE(state.open(directory));
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_NE(handle(), old_handle);
  EXPECT_EQ(widget("ai_close_saved_questions"), nullptr);
  const auto reopened = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(reopened) != nullptr; }, 30));
  EXPECT_EQ(widget(reopened)->string.value(), "Keep the unsent questionxy");
}

TEST_F(SavedConversationNavigationPython, FocusedQuestionShowsOnlyApplicableActionsAndKeepsExactDetails)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  struct Case {
    const char *id, *seed, *status, *error;
    bool send, cancel, recover, archive;
  };
  const Case cases[] = {
      {kFirst, "pending", "pending", "", true, true, false, true},
      {kSecond, "completed", "completed", "", false, false, false, true},
      {"cccccccc-cccc-4ccc-8ccc-cccccccccccc", "running", "running", "", false, true, true, false},
      {"dddddddd-dddd-4ddd-8ddd-dddddddddddd", "uncertain", "uncertain", "transport_uncertain", false, true, true, false},
      {"eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "uncertain-cancel", "uncertain", "cancel_unconfirmed", false, false, true, false},
      {"ffffffff-ffff-4fff-8fff-ffffffffffff", "failed", "failed", "adapter_failed", false, false, false, true},
      {"99999999-9999-4999-8999-999999999999", "cancelled", "cancelled", "cancelled_before_start", false, false, false, true},
  };
  for (const auto &item : cases) {
    ASSERT_NO_FATAL_FAILURE(save_question_state(item.id, "Compare\n  captured temperature", item.seed, "aliyun-token-plan/1"));
  }
  std::ofstream(dir.path() / "forbid_question_preparation").put('\n');
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 1000;
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  auto &discussion = project().discussion();
  const auto wait_for = [&](auto ready) {
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return ready(); }, 30)) << discussion.exchange_error();
  };
  const auto show = [&](const Case &item) {
    ASSERT_TRUE(discussion.load_exchange(item.id));
    ASSERT_NO_FATAL_FAILURE(wait_for([&] {
      const auto &request = discussion.exchange_request();
      return io::get_string(request, "id") == item.id && io::get_string(request, "status") == item.status &&
          !discussion.busy() && !discussion.exchange_busy() && widget("ai_refresh_reply") &&
          widget("ai_refresh_reply")->enabled && widget("ai_transcript");
    }));
  };
  const auto contains_text = [&](std::string_view text) {
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &item : block->widgets()) {
        if (item.text.find(text) != std::string::npos) { return true; }
      }
    }
    return false;
  };
  ASSERT_NO_FATAL_FAILURE(wait_for([&] { return widget("ai_prepare") && !discussion.busy(); }));
  for (const auto &item : cases) {
    SCOPED_TRACE(item.seed);
    ASSERT_NO_FATAL_FAILURE(show(item));
    const auto tr = [&](const std::string &key) { return f.shell->store().tr(key); };
    const ui::Widget *title = nullptr;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &entry : block->widgets()) {
        if (entry.type == ui::WidgetType::Label && entry.text == "Compare captured temperature") { title = &entry; }
      }
    }
    ASSERT_NE(title, nullptr);
    EXPECT_LT(title->rect.y, widget("ai_transcript")->rect.y);
    EXPECT_TRUE(contains_text(std::string(tr(std::string("discussion.requests.") + item.status)) + " · fixture-v1"));
    EXPECT_FALSE(contains_text("This question uses:"));
    EXPECT_FALSE(contains_text(std::string_view(item.id).substr(0, 8)));
    EXPECT_EQ(widget("ai_send_saved") != nullptr, item.send);
    EXPECT_EQ(widget("ai_cancel") != nullptr, item.cancel);
    EXPECT_EQ(widget("ai_recover") != nullptr, item.recover);
    EXPECT_EQ(widget("ai_archive") != nullptr, item.archive);
    if (item.cancel && widget("ai_cancel")) { EXPECT_TRUE(widget("ai_cancel")->enabled); }
    if (item.recover && widget("ai_recover")) { EXPECT_TRUE(widget("ai_recover")->enabled); }
    if (*item.error) { EXPECT_TRUE(contains_text(item.error)); }
    if (item.send) {
      ASSERT_NE(widget("ai_send_saved"), nullptr);
      EXPECT_EQ(widget("ai_send_saved")->text, "Send this saved question (fixture-v1)");
      EXPECT_FALSE(widget("ai_send_saved")->enabled);
      EXPECT_TRUE(contains_text(tr("ai.send.key_required")));
    }
    EXPECT_EQ(contains_text(tr("discussion.requests.cancel_requested")), std::string_view(item.seed) == "uncertain-cancel");
  }

  ASSERT_NO_FATAL_FAILURE(show(cases[1]));
  const auto [x, y] = f.widget_center("ai_scope_detail");
  ASSERT_TRUE(f.drv->click(x, y));
  f.drv->frame();
  EXPECT_TRUE(contains_text("This question uses: Compare\n  captured temperature · revision 1"));
  EXPECT_TRUE(contains_text(std::string("Request ID · ") + kSecond));
  EXPECT_TRUE(contains_text("Context ID · " + io::get_string(discussion.exchange_request(), "context_id")));
  EXPECT_NE(widget("ai_copy_request_id"), nullptr);
  EXPECT_NE(widget("ai_copy_context_id"), nullptr);

  f.drv->ctx.rect.xmax = 680;
  f.drv->ctx.rect.ymax = 900;
  ASSERT_NO_FATAL_FAILURE(show(cases[0]));
  ASSERT_NE(widget("ai_archive"), nullptr);
  ASSERT_TRUE(widget("ai_archive")->enabled);
  widget("ai_archive")->on_click();
  ASSERT_NO_FATAL_FAILURE(wait_for([&] { return widget("ai_archive") && widget("ai_archive")->text == "Restore" &&
      widget("ai_archive")->enabled; }));
  EXPECT_EQ(widget("ai_send_saved"), nullptr);
  EXPECT_TRUE(contains_text("Archived: this question is not sent."));
  widget("ai_archive")->on_click();
  ASSERT_NO_FATAL_FAILURE(wait_for([&] { return !project().busy() && !discussion.busy() &&
      widget("ai_archive") && widget("ai_archive")->text == "Archive" && widget("ai_cancel") && widget("ai_cancel")->enabled; }));
  ASSERT_NE(widget("ai_send_saved"), nullptr);
  widget("ai_cancel")->on_click();
  ASSERT_TRUE(discussion.busy());  // The explicit action dispatched after the archive-driven list refresh.
  ASSERT_NO_FATAL_FAILURE(wait_for([&] {
    return io::get_string(discussion.exchange_request(), "status") == "cancelled" && widget("ai_archive");
  }));
  EXPECT_EQ(widget("ai_send_saved"), nullptr);
  EXPECT_EQ(widget("ai_cancel"), nullptr);
  EXPECT_EQ(project().project()->revision, 1);
  EXPECT_EQ(client->stats().schema_violations, 0u);
}

TEST_F(SavedConversationNavigationPython, RecentQuestionsRestoreTheScrolledTranscript)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  {
    std::ofstream answer(dir.path() / "saved_answer");
    for (int line = 0; line < 90; ++line) { answer << "Alpha reply row " << line << '\n'; }
  }
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Alpha", true));
  ASSERT_NO_FATAL_FAILURE(save_question(kSecond, "Bravo", true));
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 1100;
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();

  auto &discussion = project().discussion();
  const auto wait_for = [&](const char *id) {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      return !discussion.exchange_busy() && io::get_string(discussion.exchange_request(), "id") == id &&
             widget("ai_transcript");
    }, 30)) << discussion.exchange_error();
  };
  const auto choose = [&](const char *id) {
    const auto key = std::string("workbench_question/") + id;
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(key) && widget(key)->enabled; }, 30));
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y));
    f.screen.run_deferred();
    f.drv->frame();
    ASSERT_EQ(discussion.exchange_id(), id);
    ASSERT_TRUE(discussion.exchange_request().empty());  // The loading frame is drawn before accepting the reply.
    ASSERT_NO_FATAL_FAILURE(wait_for(id));
  };
  const auto position = [&] {
    const auto *view = widget("ai_transcript");
    EXPECT_NE(view, nullptr);
    return view ? f.screen.ui()->scroll_of(view->id) : -1.0f;
  };

  ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
  ASSERT_NO_FATAL_FAILURE(choose(kFirst));
  const float tail = position();
  ASSERT_GT(tail, 0.0f);  // A first visit follows the tail.
  const auto [x, y] = f.widget_center("ai_transcript");
  wm::Event wheel;
  wheel.type = wm::EventType::Wheel;
  wheel.x = x; wheel.y = y; wheel.wheel_y = 10;
  ASSERT_TRUE(f.drv->send(wheel));
  f.drv->frame();
  const float reading = position();
  ASSERT_GT(reading, 0.0f);
  ASSERT_LT(reading, tail);
  const auto draft_key = "ai_question/" + handle();
  ASSERT_NE(widget(draft_key), nullptr);
  widget(draft_key)->string.assign("Unsent navigation draft");

  ASSERT_NO_FATAL_FAILURE(choose(kSecond));
  EXPECT_EQ(position(), 0.0f);
  EXPECT_EQ(io::get_string(discussion.exchange_reply(), "text"), "Saved answer");
  ASSERT_NO_FATAL_FAILURE(choose(kFirst));
  EXPECT_EQ(position(), reading);
  ASSERT_NE(widget(draft_key), nullptr);
  EXPECT_EQ(widget(draft_key)->string.value(), "Unsent navigation draft");

  // A second AI instance in the same area uses the same layout key and its own reading position.
  auto &area = dynamic_cast<EditorArea &>(*f.screen.maximized());
  const int original = area.active_tab();
  ASSERT_TRUE(area.add_tab(kEditorAI));
  f.drv->frame();
  EXPECT_EQ(position(), tail);
  area.set_active_tab(original);
  f.drv->frame();
  EXPECT_EQ(position(), reading);
  EXPECT_EQ(project().project()->revision, 1);

  const auto opening = handle();
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_NE(handle(), opening);
  ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
  ASSERT_NO_FATAL_FAILURE(choose(kFirst));
  EXPECT_EQ(position(), tail);
}

TEST_F(SavedConversationNavigationPython, WriteQuestionFocusesTheExistingDraftFromTasksAndResults)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  {
    std::ofstream answer(dir.path() / "saved_answer");
    for (int word = 0; word < 32; ++word) { answer << "Conversation wrapping "; }
    answer << '\n';
    for (int line = 0; line < 90; ++line) { answer << "Saved reply row " << line << '\n'; }
  }
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Read this saved question", true));
  std::ofstream(dir.path() / "forbid_question_preparation").put('\n');

  auto &discussion = project().discussion();
  auto &viewer = f.shell->store().viewer();
  struct CloseViewer {
    ViewerState &state;
    ~CloseViewer() { state.close(); }
  } close_viewer{viewer};
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) +
      "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  viewer.open_payload(payload, "Already open");
  const auto camera = viewer.camera_serial();
  const auto context = discussion.context();
  const auto draft = "ai_question/" + handle();
  const auto read_count = [&] {
    std::ifstream log(dir.path() / "history_reads");
    return std::count(std::istreambuf_iterator<char>(log), std::istreambuf_iterator<char>(), '\n');
  };
  const auto click = [&](const std::string &key) {
    ASSERT_NE(widget(key), nullptr) << key;
    ASSERT_TRUE(widget(key)->enabled) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred();
    f.drv->frame();
  };
  const auto reading_position = [&] {
    const auto *view = widget("ai_transcript");
    return view ? f.screen.ui()->scroll_of(view->id) : -1.0f;
  };
  // The focused transcript wraps and draws with the regular UI font. Roles stay on their own lines, and
  // the reply keeps its words and hard line breaks.
  size_t question_drawn = 0;
  const auto expect_proportional_transcript = [&](const ui::Widget &transcript, const ui::Context &ui) {
    const auto &style = ui.style();
    const auto &log = *transcript.log;
    EXPECT_FALSE(transcript.mono);
    // A line wrapped for the monospace font never exceeds this bound (the wrap width, plus the
    // panel margins and scrollbar the column reserves). Wrapped for the regular font, some lines do.
    const float mono_bound = transcript.rect.w + 2 * style.panel_margin + style.scrollbar - 4 * style.unit;
    float widest_mono = 0.0f;
    std::string paragraph;
    size_t assistant = 0, rows = 0;
    for (size_t line = 0; line < log.line_count(); ++line) {
      const auto text = log.line(line);
      EXPECT_LE(ui.measurer().width(text, style.font), transcript.rect.w - 2 * style.text_margin) << text;
      widest_mono = std::max(widest_mono, ui.measurer().width(text, style.mono));
      if (text == f.shell->store().tr("ai.assistant")) { assistant = line; }
      else if (text.starts_with("Saved reply row ")) {
        EXPECT_EQ(text, "Saved reply row " + std::to_string(rows)); ++rows;
      }
      else if (assistant > 0 && rows == 0) { paragraph += std::string(text) + " "; }
    }
    ASSERT_GT(log.line_count(), 2u);
    EXPECT_EQ(log.line(0), f.shell->store().tr("ai.you"));
    EXPECT_EQ(log.line(1), "Read this saved question");
    EXPECT_EQ(log.line(2), "");
    EXPECT_EQ(assistant, 3u);
    EXPECT_EQ(rows, 90u);
    std::string expected;
    for (int word = 0; word < 32; ++word) { expected += "Conversation wrapping "; }
    EXPECT_EQ(paragraph, expected);
    EXPECT_GT(widest_mono, mono_bound) << "the transcript was wrapped for the monospace font";
    size_t drawn = 0;
    for (const auto &command : ui.draw_list().cmds) {
      if (command.type != ui::CmdType::Text || !transcript.rect.contains(command.pos)) { continue; }
      EXPECT_EQ(command.font.kind, ui::FontKind::Regular) << command.text;
      ++drawn;
    }
    EXPECT_GT(drawn, 0u);

    // The question is one right-aligned block of its label and text, measured with the drawn font; the blank
    // line and the reply start at the left. The block's edge leaves room for the scrollbar.
    ASSERT_NE(transcript.log_blocks, nullptr);
    ASSERT_EQ(transcript.log_blocks->size(), 1u);
    const auto &block = transcript.log_blocks->front();
    EXPECT_EQ(block.first_line, 0u);
    EXPECT_EQ(block.lines, 2u);
    EXPECT_FLOAT_EQ(block.width, std::max(ui.measurer().width(log.line(0), style.font),
                                          ui.measurer().width(log.line(1), style.font)));
    const float wrap = std::max(style.unit, std::min(transcript.block->rect().w, 880.0f * style.scale) - 4 * style.unit);
    EXPECT_LE(block.width, std::floor(0.85f * wrap));
    const ui::Rect body = transcript.rect.inset(style.pixel, style.pixel);
    const float left = body.x + style.text_margin;
    const float edge = body.x1() - (style.scrollbar + 2 * style.pixel) - style.text_margin;
    const float row = std::round(style.font.size_px * 1.4f), pad = std::round(0.2f * style.unit);
    const auto metrics = ui.measurer().metrics(style.font);
    const float scroll = ui.scroll_of(transcript.id);
    const ui::Rect visible = transcript.rect.intersect(transcript.clip);
    question_drawn = 0;
    for (const auto &command : ui.draw_list().cmds) {
      if (command.type != ui::CmdType::Text || !visible.contains(command.pos) || command.text == ui.tr("ui.log.follow")) {
        continue;
      }
      const float top = command.pos.y - row * 0.5f - (metrics.ascent - metrics.descent) * 0.5f;
      const auto line = size_t(std::lround((top - body.y - pad + scroll) / row));
      ASSERT_LT(line, log.line_count()) << command.text;
      ASSERT_EQ(log.line(line), command.text);
      if (line >= block.lines) { EXPECT_FLOAT_EQ(command.pos.x, left) << command.text; continue; }
      EXPECT_FLOAT_EQ(command.pos.x, std::round(edge - block.width)) << command.text << ": one left edge";
      if (ui.measurer().width(command.text, style.font) == block.width) {
        EXPECT_NEAR(command.pos.x + block.width, edge, 1.0f) << command.text << ": the wider line reaches the edge";
      }
      ++question_drawn;
    }
  };
  // Scroll the transcript to its start, as a reader would with the wheel, to see the question.
  const auto wheel_to_question = [&] {
    const auto [x, y] = f.widget_center("ai_transcript");
    wm::Event up;
    up.type = wm::EventType::Wheel;
    up.x = x; up.y = y; up.wheel_y = 100;
    ASSERT_TRUE(f.drv->send(up));
    f.drv->frame();
    ASSERT_EQ(reading_position(), 0.0f);
  };
  const auto expect_column = [&] {
    const auto *transcript = widget("ai_transcript");
    const auto *input = widget(draft);
    const auto *prepare = widget("ai_prepare");
    ASSERT_NE(transcript, nullptr);
    ASSERT_NE(input, nullptr);
    ASSERT_NE(prepare, nullptr);
    const auto &block = input->block->rect();
    const auto &ui = *f.screen.ui();
    const auto &style = ui.style();
    const float scrollbar = input->block->content_height() > block.h ? style.scrollbar : 0.0f;
    const float available = block.w - 2 * style.panel_margin;
    const float cap = 880.0f * style.scale;
    // The field, its status and the right-aligned action share one card as wide as the transcript column.
    const auto *card = composer_card(ui, *input, *prepare);
    ASSERT_NE(card, nullptr) << "no card drawn around the question and Prepare";
    EXPECT_NEAR(card->rect.w, std::min(available, cap) - scrollbar, 2.0f);
    EXPECT_LE(card->rect.w, cap);
    EXPECT_NEAR(card->rect.cx(), block.cx() - scrollbar * 0.5f, 1.0f);
    EXPECT_EQ(transcript->rect.x, card->rect.x);
    EXPECT_EQ(transcript->rect.w, card->rect.w);
    EXPECT_EQ(prepare->rect.x1(), input->rect.x1());
    EXPECT_LT(prepare->rect.w, input->rect.w * 0.5f);
    EXPECT_GE(prepare->rect.w, ui.measurer().width(prepare->text, style.font) + 2 * style.text_margin);
    ASSERT_NE(transcript->log, nullptr);
    ASSERT_NO_FATAL_FAILURE(expect_proportional_transcript(*transcript, ui));
  };

  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 900;
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return discussion.recent_requests() && !discussion.busy() && !discussion.exchange_busy() &&
           discussion.exchange_id() == kFirst && widget(draft) && widget("ai_transcript");
  }, 30)) << discussion.exchange_error();
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_LT(widget("ai_transcript")->rect.y, widget(draft)->rect.y);
  auto *conversation = f.screen.maximized();
  const auto selected = discussion.exchange_request();
  const float tail = reading_position();
  ASSERT_GT(tail, 0.0f);
  const auto [x, y] = f.widget_center("ai_transcript");
  wm::Event wheel;
  wheel.type = wm::EventType::Wheel;
  wheel.x = x; wheel.y = y; wheel.wheel_y = 10;
  ASSERT_TRUE(f.drv->send(wheel));
  f.drv->frame();
  const float reading = reading_position();
  ASSERT_GT(reading, 0.0f);
  ASSERT_LT(reading, tail);
  widget(draft)->string.assign("Unsent question ");

  ASSERT_NO_FATAL_FAILURE(click("workbench_tasks"));
  ASSERT_EQ(dynamic_cast<EditorArea &>(*f.screen.maximized()).editor().type().id, kEditorJobs);
  const auto before = read_count();
  ASSERT_NO_FATAL_FAILURE(click("workbench_write_question"));
  ASSERT_EQ(f.screen.maximized(), conversation);
  ASSERT_NE(widget(draft), nullptr);
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(f.screen.ui()->focused(), widget(draft)->id);
  EXPECT_LT(widget(draft)->rect.y, widget("ai_transcript")->rect.y);
  EXPECT_EQ(widget(draft)->rect.intersect(widget(draft)->clip), widget(draft)->rect);
  EXPECT_EQ(reading_position(), reading);
  EXPECT_EQ(discussion.exchange_request(), selected);
  EXPECT_EQ(read_count(), before);
  ASSERT_TRUE(f.drv->key(wm::Key::A, wm::ModNone, "a"));
  ASSERT_TRUE(f.drv->key(wm::Key::Tab, wm::ModShift));
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question a");

  const auto stale = widget("workbench_write_question")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  auto *results = f.screen.maximized();
  stale();
  f.screen.run_deferred();
  EXPECT_EQ(f.screen.maximized(), results);
  f.drv->ctx.rect.xmax = 680;
  f.drv->ctx.rect.ymax = 620;
  f.drv->frame();
  ASSERT_EQ(f.screen.maximized(), results);
  ASSERT_EQ(widget("workbench_write_question"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  std::string compose_entry;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &item : block->widgets()) {
      if (item.type == ui::WidgetType::MenuItem && item.text == f.shell->store().tr("ai.write_question")) {
        compose_entry = item.key;
      }
    }
  }
  ASSERT_FALSE(compose_entry.empty());
  ASSERT_NO_FATAL_FAILURE(click(compose_entry));
  ASSERT_EQ(f.screen.maximized(), conversation);
  ASSERT_NE(widget(draft), nullptr);
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(f.screen.ui()->focused(), widget(draft)->id);
  EXPECT_LT(widget(draft)->rect.y, widget("ai_transcript")->rect.y);
  EXPECT_EQ(widget(draft)->rect.intersect(widget(draft)->clip), widget(draft)->rect);
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question a");
  ASSERT_TRUE(f.drv->key(wm::Key::B, wm::ModNone, "b"));
  ASSERT_TRUE(f.drv->key(wm::Key::Tab, wm::ModShift));
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");
  EXPECT_EQ(discussion.exchange_request(), selected);
  EXPECT_EQ(discussion.context(), context);
  EXPECT_EQ(read_count(), before);
  EXPECT_EQ(viewer.payload(), payload);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(project().project()->revision, 1);

  const float narrow_reading = reading_position();
  ASSERT_GT(narrow_reading, 0.0f);
  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  const auto history_launcher = widget("workbench_history")->id;
  ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
  ASSERT_TRUE(f.screen.ui()->popup_open());
  ASSERT_TRUE(f.drv->key(wm::Key::Esc));
  EXPECT_FALSE(f.screen.ui()->popup_open());
  EXPECT_EQ(f.screen.ui()->focused(), history_launcher);
  EXPECT_EQ(f.screen.maximized(), results);
  EXPECT_EQ(discussion.exchange_request(), selected);
  ASSERT_TRUE(f.drv->key(wm::Key::Enter));
  ASSERT_TRUE(f.screen.ui()->popup_open());
  ASSERT_TRUE(f.drv->key(wm::Key::Home));
  ASSERT_TRUE(f.drv->key(wm::Key::Enter));
  f.screen.run_deferred();
  f.drv->frame();
  ASSERT_EQ(f.screen.maximized(), conversation);
  ASSERT_NE(widget(draft), nullptr);
  EXPECT_EQ(f.screen.ui()->focused(), widget(draft)->id);
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");
  EXPECT_EQ(reading_position(), narrow_reading);
  EXPECT_EQ(discussion.exchange_request(), selected);
  EXPECT_EQ(read_count(), before);

  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 900;
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click(std::string("workbench_question/") + kFirst));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return !discussion.exchange_busy() && discussion.exchange_request() == selected &&
           widget("ai_transcript") && widget(draft);
  }, 30)) << discussion.exchange_error();
  EXPECT_LT(widget("ai_transcript")->rect.y, widget(draft)->rect.y);
  EXPECT_EQ(reading_position(), reading);
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");

  f.drv->ctx.ui_scale = 1.25f;
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");
  // The new size re-measures the block: the question reaches the edge in the larger font.
  ASSERT_NO_FATAL_FAILURE(wheel_to_question());
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(question_drawn, 2u);

  // The split view keeps its monospace transcript. Returning wraps for the regular font again.
  ASSERT_NO_FATAL_FAILURE(click("workbench_split"));
  ASSERT_EQ(f.screen.maximized(), nullptr);
  const auto *split = widget("ai_transcript");
  ASSERT_NE(split, nullptr);
  EXPECT_TRUE(split->mono);
  EXPECT_EQ(split->log_blocks, nullptr) << "the split view keeps one left-aligned text";
  size_t mono_drawn = 0;
  for (const auto &command : f.screen.ui()->draw_list().cmds) {
    if (command.type != ui::CmdType::Text || !split->rect.contains(command.pos)) { continue; }
    if (command.text == f.shell->store().tr("ui.log.follow")) { continue; }
    EXPECT_EQ(command.font.kind, ui::FontKind::Mono) << command.text;
    ++mono_drawn;
  }
  EXPECT_GT(mono_drawn, 0u);
  EXPECT_EQ(discussion.exchange_request(), selected);
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  ASSERT_EQ(f.screen.maximized(), conversation);
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");
  EXPECT_EQ(discussion.exchange_request(), selected);

  // In a narrow window, ordinary maximization of the same editor wraps to the same width as the
  // focused column, so only the font separates the cached lines. It shows monospace lines again.
  f.drv->ctx.ui_scale = 1.0f;
  f.drv->ctx.rect.xmax = 680;
  f.drv->ctx.rect.ymax = 1000;
  f.drv->frame();
  ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  ASSERT_NO_FATAL_FAILURE(expect_column());
  ASSERT_NO_FATAL_FAILURE(wheel_to_question());
  ASSERT_NO_FATAL_FAILURE(expect_column());
  EXPECT_EQ(question_drawn, 2u) << "the narrow column right-aligns the question too";
  f.screen.set_maximized(nullptr);
  f.screen.set_maximized(conversation);
  f.drv->frame();
  ASSERT_FALSE(f.shell->workbench_is_focused(f.screen));
  const auto *maximized = widget("ai_transcript");
  ASSERT_NE(maximized, nullptr);
  ASSERT_NE(maximized->log, nullptr);
  EXPECT_TRUE(maximized->mono);
  EXPECT_EQ(maximized->log_blocks, nullptr);
  const auto &style = f.screen.ui()->style();
  for (size_t line = 0; line < maximized->log->line_count(); ++line) {
    EXPECT_LE(f.screen.ui()->measurer().width(maximized->log->line(line), style.mono),
              maximized->rect.w - 2 * style.text_margin) << maximized->log->line(line);
  }
  // Ordinary maximization keeps the split view's composer: no card, and Prepare as wide as the field.
  ASSERT_NO_FATAL_FAILURE(expect_split_composer(*f.screen.ui(), widget(draft), widget("ai_prepare")));
  EXPECT_EQ(widget(draft)->string.value(), "Unsent question ab");
  EXPECT_EQ(discussion.exchange_request(), selected);
  EXPECT_EQ(project().project()->revision, 1);
}

TEST_F(SavedConversationNavigationPython, WriteQuestionDoesNotOpenSavedHistoryOnFirstVisit)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Saved question remains available", true));
  std::ofstream(dir.path() / "forbid_question_preparation").put('\n');
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 900;
  f.shell->open_workbench(f.screen, true);
  f.screen.run_deferred();
  auto &discussion = project().discussion();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return discussion.recent_requests() && !discussion.busy() && widget("workbench_write_question") &&
           widget("workbench_write_question")->enabled;
  }, 30));
  ASSERT_TRUE(discussion.exchange_id().empty());
  const auto [x, y] = f.widget_center("workbench_write_question");
  ASSERT_TRUE(f.drv->click(x, y));
  f.screen.run_deferred();
  const auto key = "ai_question/" + handle();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return !discussion.busy() && widget(key);
  }, 30));
  EXPECT_EQ(f.screen.ui()->focused(), widget(key)->id);
  EXPECT_TRUE(discussion.exchange_id().empty());
  EXPECT_EQ(widget("ai_transcript"), nullptr);
  EXPECT_EQ(widget("ai_return_question"), nullptr);
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "history_reads"));
}

TEST_F(SavedConversationNavigationPython, OpenCompactHistoryIsolatesViewerInputUntilDismissed)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Saved question"));
  auto &viewer = f.shell->store().viewer();
  const std::string path = std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp";
  const auto original = std::make_shared<io::Payload>(io::read_stkp(path));
  viewer.open_payload(original, "Already open");
  f.drv->ctx.rect.xmax = 680;
  f.shell->open_workbench(f.screen, true);
  f.screen.run_deferred();
  auto &area = f.area("a2");
  ASSERT_EQ(f.screen.maximized(), &area);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    const auto *questions = project().discussion().recent_requests();
    return questions && !questions->empty() && widget("workbench_history");
  }, 30));

  const auto launcher = widget("workbench_history")->id;
  const auto [hx, hy] = f.widget_center("workbench_history");
  ASSERT_TRUE(f.drv->click(hx, hy));
  ASSERT_TRUE(f.screen.ui()->popup_open());
  const auto &rect = area.find_region("main")->rect();
  const int x = rect.xmin + 32;
  const int y = (rect.ymin + rect.ymax) / 2;
  f.drv->move(x, y);
  ASSERT_TRUE(area.editor().save_workspace_state().at("pending_preset").is_null());
  EXPECT_TRUE(f.drv->key(wm::Key::Numpad1));
  EXPECT_TRUE(area.editor().save_workspace_state().at("pending_preset").is_null());

  wm::Event drop;
  drop.type = wm::EventType::DragEnter;
  drop.x = x;
  drop.y = y;
  EXPECT_FALSE(f.drv->send(drop));
  drop.type = wm::EventType::DragOver;
  EXPECT_FALSE(f.drv->send(drop));
  drop.type = wm::EventType::Drop;
  drop.paths = {path};
  EXPECT_FALSE(f.drv->send(drop));
  EXPECT_EQ(viewer.base_payload().get(), original.get());

  EXPECT_TRUE(f.drv->key(wm::Key::DownArrow));
  EXPECT_TRUE(f.screen.ui()->popup_open());
  ASSERT_TRUE(f.drv->key(wm::Key::Esc));
  EXPECT_FALSE(f.screen.ui()->popup_open());
  EXPECT_EQ(f.screen.ui()->focused(), launcher);
  EXPECT_TRUE(f.drv->key(wm::Key::Numpad1));
  EXPECT_FALSE(area.editor().save_workspace_state().at("pending_preset").is_null());
  EXPECT_TRUE(f.drv->send(drop));
  EXPECT_NE(viewer.base_payload().get(), original.get());
  viewer.close();
}

TEST_F(SavedConversationNavigationPython, AgentHistorySeparatesIdentitiesAndKeepsBothDrafts)
{
  ASSERT_NO_FATAL_FAILURE(prepare_table());
  std::ofstream(dir.path() / "seed_agent_history") << "1";
  ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Ordinary question"));
  auto &discussion = project().discussion();
  auto &agent = project().agent();
  ASSERT_TRUE(agent.supported());
  const auto question = "ai_question/" + handle();
  const auto agent_text = "ai_agent_text/" + handle();
  const auto intent = "ai_intent/" + handle();
  const auto ordinary = std::string("workbench_question/") + kFirst;
  const auto first = std::string("workbench_agent_session/") + kFirst;
  const auto click = [&](const std::string &key) {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred();
    f.drv->frame();
  };
  const auto wait_for_agent = [&](const char *id, const char *text) {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      return widget(agent_text) && io::get_string(agent.view().value("session", Json::object()), "id") == id;
    }, 30)) << agent.error();
    ASSERT_EQ(agent.selected(), id);
    EXPECT_EQ(io::get_string(agent.view().at("events").at(0), "text"), text);
    EXPECT_FALSE(agent.running());
    EXPECT_EQ(widget(agent_text)->string.value(), "Unsent agent text");
    EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
  };

  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return widget(question) && widget(ordinary) && widget(first) && !discussion.exchange_busy();
  }, 30));
  auto *conversation = f.screen.maximized();
  widget(question)->string.assign("Unsent ordinary text");
  ASSERT_NE(widget(intent), nullptr);
  widget(intent)->index.assign(3);
  f.drv->frame();
  ASSERT_NE(widget(agent_text), nullptr);
  widget(agent_text)->string.assign("Unsent agent text");
  ASSERT_NO_FATAL_FAILURE(click("workbench_tasks"));
  ASSERT_NE(widget(first), nullptr);
  EXPECT_TRUE(widget(first)->text.ends_with("Agent Alpha"));
  std::ofstream(dir.path() / "fail_next_agent_read") << "1";
  ASSERT_NO_FATAL_FAILURE(click(first));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return agent.error() == "fixture agent history read failed" && widget(agent_text);
  }, 30));
  EXPECT_TRUE(agent.view().empty());
  ASSERT_NE(widget("ai_agent_send"), nullptr);
  EXPECT_FALSE(widget("ai_agent_send")->enabled);
  ASSERT_NO_FATAL_FAILURE(click(first));
  ASSERT_NO_FATAL_FAILURE(wait_for_agent(kFirst, "Agent\nAlpha"));
  EXPECT_EQ(f.screen.maximized(), conversation);

  // The two ledgers may use the same UUID. Reselecting the agent still supersedes an old question callback.
  ASSERT_NE(widget(ordinary), nullptr);
  const auto stale = widget(ordinary)->on_click;
  const auto exchange = discussion.exchange_generation();
  const auto selection = agent.selection_epoch();
  ASSERT_NO_FATAL_FAILURE(click(first));
  EXPECT_EQ(agent.selection_epoch(), selection);
  stale();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_NE(widget(agent_text), nullptr);
  EXPECT_EQ(discussion.exchange_generation(), exchange);

  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  auto *results = f.screen.maximized();
  f.drv->ctx.rect.xmax = 680;
  f.drv->frame();
  const auto choose = [&](const char *text) {
    ASSERT_NO_FATAL_FAILURE(click("workbench_history"));
    std::string key;
    bool question_group = false, agent_group = false;
    for (const auto &block : f.screen.ui()->blocks()) {
      for (const auto &candidate : block->widgets()) {
        if (candidate.type != ui::WidgetType::MenuItem) { continue; }
        question_group |= !candidate.enabled && candidate.text == "Recent questions";
        agent_group |= !candidate.enabled && candidate.text == "Agent sessions";
        if (candidate.text.ends_with(text)) { key = candidate.key; }
      }
    }
    EXPECT_TRUE(question_group);
    EXPECT_TRUE(agent_group);
    ASSERT_FALSE(key.empty()) << text;
    ASSERT_NO_FATAL_FAILURE(click(key));
  };
  ASSERT_NO_FATAL_FAILURE(choose("Agent Bravo"));
  ASSERT_NO_FATAL_FAILURE(wait_for_agent(kSecond, "Agent Bravo"));
  ASSERT_NO_FATAL_FAILURE(choose("Ordinary question"));
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return widget(question) && io::get_string(discussion.exchange_question(), "text") == "Ordinary question";
  }, 30));
  EXPECT_EQ(widget(question)->string.value(), "Unsent ordinary text");
  EXPECT_EQ(f.screen.maximized(), conversation);
  EXPECT_EQ(project().project()->revision, 1);
  ASSERT_NO_FATAL_FAILURE(click("workbench_results"));
  EXPECT_EQ(f.screen.maximized(), results);
}

TEST_F(WorkspaceNavigationPython, CapturedConversationOpensWhileOnlyTheProjectCatalogIsRefreshing)
{
  const std::string table = "11111111-1111-4111-8111-111111111111";
  const std::string row = "22222222-2222-4222-8222-222222222222";
  const std::string field = "33333333-3333-4333-8333-333333333333";
  ASSERT_TRUE(project().apply(Json::array({
      {{"op", "create_table"}, {"id", table}, {"name", "Frozen results"}},
      {{"op", "add_field"}, {"id", field}, {"table_id", table}, {"name", "Value"}, {"type", "number"}},
      {{"op", "add_record"}, {"id", row}, {"table_id", table}},
      {{"op", "set_cell"}, {"table_id", table}, {"record_id", row}, {"field_id", field}, {"value", 300}}
  })));
  ASSERT_NO_FATAL_FAILURE(idle());
  auto &discussion = project().discussion();
  const auto opened_handle = handle();
  bool captured = false;
  ASSERT_TRUE(discussion.capture(table, {row}, {field}, "Frozen results", [&](bool ok) {
    captured = ok;
    if (ok) { f.shell->open_project_page_later(&f.screen, "conversation", opened_handle); }
  }));
  ASSERT_TRUE(discussion.busy());
  // Pump bridge replies without running Screen's deferred navigation queue.
  ASSERT_TRUE(loop.pump_until([&] { return !discussion.busy(); }, 30)) << discussion.error();
  ASSERT_TRUE(captured); ASSERT_FALSE(discussion.context().empty());
  const auto context = discussion.context();
  project().refresh();
  ASSERT_TRUE(project().busy()); // Do not pump the bridge before executing the queued navigation.
  f.screen.run_deferred(); f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(destination(kEditorAI).editor().type().id, kEditorAI);
  EXPECT_EQ(discussion.context(), context);
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_EQ(discussion.context(), context);
}

TEST_F(WorkspaceNavigationPython, ARefreshDoesNotOpenUncapturedConversationOrOtherProjectPages)
{
  ASSERT_TRUE(project().discussion().context().empty());
  project().refresh(); ASSERT_TRUE(project().busy());
  go("conversation"); EXPECT_EQ(f.screen.maximized(), &home());
  go("files"); EXPECT_EQ(f.screen.maximized(), &home());
  ASSERT_NO_FATAL_FAILURE(idle());
}

// Fixed start: two completed saved questions (the first with a long reply), the focused Workbench
// on the AI tab of the third area, and another AI instance active in the first area. The split's
// new Literature tab goes to the fourth area, so both conversations stay drawn there, and the
// ordinary Workbench navigation (the first active AI tab) differs from the exact return.
class FocusedLiteraturePython : public SavedConversationNavigationPython {
 protected:
  EditorArea &origin() { return f.area("a3"); }
  EditorArea &other() { return home(); }
  ProjectDiscussion &discussion() { return project().discussion(); }
  void click(const std::string &key)
  {
    ASSERT_NE(widget(key), nullptr) << key;
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y)) << key;
    f.screen.run_deferred();
    f.drv->frame();
  }
  void wait_for(const char *id)
  {
    ASSERT_TRUE(loop.pump_until([&] {
      f.drv->frame();
      return !discussion().exchange_busy() && !discussion().busy() &&
             io::get_string(discussion().exchange_request(), "id") == id && widget("ai_transcript");
    }, 30)) << discussion().exchange_error();
  }
  float position()
  {
    const auto *view = widget("ai_transcript");
    EXPECT_NE(view, nullptr);
    return view ? f.screen.ui()->scroll_of(view->id) : -1.0f;
  }
  std::string draft_key() { return "ai_question/" + handle(); }
  std::string draft() { return widget(draft_key()) ? widget(draft_key())->string.value() : std::string("<missing>"); }
  EditorArea *literature()
  {
    for (auto *base : f.screen.areas()) {
      auto *area = dynamic_cast<EditorArea *>(base);
      if (area && area->editor().type().id == kEditorLiterature) { return area; }
    }
    return nullptr;
  }
  void start(int width = 1600, int height = 1000)
  {
    ASSERT_NO_FATAL_FAILURE(prepare_table());
    {
      std::ofstream answer(dir.path() / "saved_answer");
      for (int line = 0; line < 90; ++line) { answer << "Alpha reply row " << line << '\n'; }
    }
    ASSERT_NO_FATAL_FAILURE(save_question(kFirst, "Alpha", true));
    ASSERT_NO_FATAL_FAILURE(save_question(kSecond, "Bravo", true));
    revision = project().project()->revision;
    ASSERT_EQ(origin().editor().type().id, kEditorAI);
    conversation = &origin().editor();
    ASSERT_TRUE(other().add_tab(kEditorAI));
    ASSERT_EQ(other().editor().type().id, kEditorAI);
    ASSERT_NE(&other().editor(), conversation);
    f.drv->ctx.rect.xmax = 1600;
    f.drv->ctx.rect.ymax = 1000;
    ASSERT_NO_FATAL_FAILURE(focus_origin());
    ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
    ASSERT_EQ(&origin().editor(), conversation);
    // Choose the older question from the rail, then move away from the tail of its reply.
    const auto key = std::string("workbench_question/") + kFirst;
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return widget(key) && widget(key)->enabled; }, 30));
    const auto [x, y] = f.widget_center(key);
    ASSERT_TRUE(f.drv->click(x, y));
    f.screen.run_deferred();
    f.drv->frame();
    ASSERT_EQ(discussion().exchange_id(), kFirst);
    // Loading frame: the selected question is not yet adopted, so there is no entry.
    ASSERT_TRUE(discussion().exchange_request().empty());
    EXPECT_EQ(widget("ai_open_literature"), nullptr);
    ASSERT_NO_FATAL_FAILURE(wait_for(kFirst));
    const auto [tx, ty] = f.widget_center("ai_transcript");
    wm::Event wheel;
    wheel.type = wm::EventType::Wheel;
    wheel.x = tx; wheel.y = ty; wheel.wheel_y = 10;
    ASSERT_TRUE(f.drv->send(wheel));
    f.drv->frame();
    ASSERT_NE(widget(draft_key()), nullptr);
    widget(draft_key())->string.assign("Unsent question kept while reading literature");
    f.drv->ctx.rect.xmax = width;
    f.drv->ctx.rect.ymax = height;
    f.drv->frame();
    ASSERT_EQ(f.screen.maximized(), &origin());
    ASSERT_NE(widget("ai_open_literature"), nullptr);
  }
  /** Focus the Workbench on the origin conversation, as its area was maximized before. */
  void focus_origin()
  {
    f.screen.set_maximized(&origin());
    f.shell->open_workbench(f.screen);
    f.screen.run_deferred();
    f.drv->frame();
    ASSERT_EQ(f.screen.maximized(), &origin());
    ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  }
  /** The exact return: the same AI instance, question, reading position and draft. */
  void expect_same_conversation(float reading, uint64_t exchange)
  {
    EXPECT_EQ(f.screen.maximized(), &origin());
    EXPECT_EQ(&origin().editor(), conversation);
    EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
    EXPECT_EQ(discussion().exchange_id(), kFirst);
    EXPECT_EQ(discussion().exchange_generation(), exchange);
    EXPECT_EQ(position(), reading);
    EXPECT_EQ(draft(), "Unsent question kept while reading literature");
  }
  void prepare_automatic_question(EditorArea &area, const std::string &text, std::string &request,
                                  std::function<void()> &send)
  {
    auto &models = f.shell->store().models();
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return models.loaded() && !models.busy(); }, 30));
    ASSERT_TRUE(models.route_supported());
    ASSERT_TRUE(models.add_endpoint("a-gone", "A gone", "http://127.0.0.1:9/v1", {"m"}, ""));
    ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !models.busy() && models.endpoint("a-gone"); }, 30));
    const auto prefix = area.id() + "/main/";
    ASSERT_NE(widget(prefix + draft_key()), nullptr);
    widget(prefix + draft_key())->string.assign(text);
    ASSERT_TRUE(loop.pump_until([&] {
      f.screen.run_deferred(); f.drv->frame();
      return widget(prefix + "ai_prepare") && widget(prefix + "ai_prepare")->enabled;
    }, 30));
    widget(prefix + "ai_prepare")->on_click();
    ASSERT_TRUE(loop.pump_until([&] {
      f.screen.run_deferred(); f.drv->frame();
      request = io::get_string(discussion().exchange_request(), "id");
      return !request.empty() && request != kFirst && request != kSecond && !discussion().exchange_busy() &&
             widget(prefix + "ai_send_saved") && widget(prefix + "ai_send_saved")->enabled;
    }, 30)) << discussion().exchange_error();
    ASSERT_EQ(io::get_string(discussion().exchange_request().at("configuration"), "adapter"), "openai-compatible/1:a-gone");
    ASSERT_EQ(io::get_string(discussion().exchange_request(), "status"), "pending");
    send = widget(prefix + "ai_send_saved")->on_click;
    ASSERT_TRUE(send);
    revision = project().project()->revision;
  }
  void TearDown() override
  {
    if (project().project()) { EXPECT_EQ(project().project()->revision, revision); }
    SavedConversationNavigationPython::TearDown();
  }
  Editor *conversation = nullptr;
  int64_t revision = -1;
};

TEST_F(FocusedLiteraturePython, OneClickEachWayKeepsTheQuestionDraftAndReadingPositionAtBothWidths)
{
  ASSERT_NO_FATAL_FAILURE(start());
  const auto areas = f.screen.areas();
  auto *other_conversation = &other().editor();
  for (const auto &[width, height] : {std::pair{1600, 1000}, std::pair{680, 900}}) {
    SCOPED_TRACE(width);
    f.drv->ctx.rect.xmax = width;
    f.drv->ctx.rect.ymax = height;
    f.drv->frame();
    const bool wide = width > 700;
    ASSERT_EQ(f.screen.maximized(), &origin());
    EXPECT_EQ(origin().find_region("workbench_rail")->rect().empty(), !wide);
    EXPECT_EQ(origin().find_region("workbench_strip")->rect().empty(), wide);
    ASSERT_NE(widget("ai_open_literature"), nullptr);
    EXPECT_EQ(widget("ai_open_literature")->text, "Open literature");
    EXPECT_NE(widget("project_workspace"), nullptr);  // The overview entry stays beside it.
    const float reading = position();
    EXPECT_GE(reading, 0.0f);
    const auto exchange = discussion().exchange_generation();

    ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
    EXPECT_EQ(f.screen.maximized(), nullptr);
    ASSERT_NE(literature(), nullptr);
    EXPECT_EQ(f.screen.areas(), areas);
    EXPECT_EQ(&origin().editor(), conversation);
    EXPECT_EQ(&other().editor(), other_conversation);  // Both conversations stay shown, never replaced.
    EXPECT_EQ(discussion().exchange_id(), kFirst);
    EXPECT_NE(widget("literature_refresh"), nullptr);
    EXPECT_TRUE(literature_calls().empty());  // Opening and drawing it is passive.

    ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
    ASSERT_NO_FATAL_FAILURE(expect_same_conversation(reading, exchange));
    if (!wide) {
      // The strip keeps three sections, Split view and History; the entry is not a section.
      for (const auto *key : {"workbench_home", "workbench_tasks", "workbench_results", "workbench_split",
                              "workbench_history"}) {
        EXPECT_NE(widget(key), nullptr) << key;
      }
    }
    EXPECT_TRUE(literature_calls().empty());
  }

  // The overview keeps its own exact return.
  const float reading = position();
  const auto exchange = discussion().exchange_generation();
  ASSERT_NO_FATAL_FAILURE(click("project_workspace"));
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_NE(widget("workspace_project"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  ASSERT_NO_FATAL_FAILURE(expect_same_conversation(reading, exchange));

  // An explicit refresh on the literature page keeps its original metadata reads only.
  f.drv->ctx.rect.xmax = 1600;
  f.drv->ctx.rect.ymax = 1000;
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_NE(literature(), nullptr);
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    return widget("literature_refresh") && widget("literature_refresh")->enabled;
  }, 30));
  widget("literature_refresh")->on_click();  // The page's own explicit action (it may be scrolled in a small area).
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    return literature_calls().size() >= 2 && widget("literature_refresh") && widget("literature_refresh")->enabled;
  }, 30));
  auto calls = literature_calls();
  std::sort(calls.begin(), calls.end());
  EXPECT_EQ(calls, (std::vector<std::string>{"encoder.info", "info"}));  // No library or scope is selected.
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(f.screen.maximized(), &origin());
  EXPECT_EQ(&origin().editor(), conversation);
  EXPECT_EQ(discussion().exchange_id(), kFirst);
  EXPECT_EQ(draft(), "Unsent question kept while reading literature");
  EXPECT_EQ(literature_calls().size(), 2u);
}

TEST_F(FocusedLiteraturePython, ChangedIdentityReturnsByTheCurrentWorkbenchWithoutTheOldQuestion)
{
  ASSERT_NO_FATAL_FAILURE(start());
  // A retained entry is stale after a tab change in its area, and after another question is shown.
  auto stale = widget("ai_open_literature")->on_click;
  const int tab = origin().active_tab();
  origin().set_active_tab(tab == 0 ? 1 : 0);
  origin().set_active_tab(tab);
  stale();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), &origin());
  EXPECT_EQ(literature(), nullptr);
  ASSERT_NE(widget("ai_open_literature"), nullptr);
  stale = widget("ai_open_literature")->on_click;
  ASSERT_TRUE(discussion().load_exchange(kSecond));
  ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
  stale();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_EQ(f.screen.maximized(), &origin());
  EXPECT_EQ(literature(), nullptr);
  ASSERT_TRUE(discussion().load_exchange(kFirst));
  ASSERT_NO_FATAL_FAILURE(wait_for(kFirst));

  // The exact return first, so the following fallbacks are distinguishable from it.
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_NE(literature(), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(f.screen.maximized(), &origin());
  EXPECT_EQ(discussion().exchange_id(), kFirst);

  // Another window selects the other saved question while this one shows the literature.
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_NE(literature(), nullptr);
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !discussion().busy() && !discussion().exchange_busy(); }, 30));
  {
    wm::Screen window;
    f.shell->install(window, nullptr);
    f.shell->build_default_layout(window);
    struct ForgetScreen {
      AppShell *shell; wm::Screen *screen;
      ~ForgetScreen() { shell->forget(*screen); }
    } cleanup{f.shell.get(), &window};
    wmtest::ScreenDriver driver(window, 1000, 800, 1);
    auto *area = dynamic_cast<EditorArea *>(window.find_area("a3"));
    ASSERT_NE(area, nullptr);
    ASSERT_TRUE(area->set_tab_type(area->active_tab(), kEditorAI));
    driver.frame();
    auto select = f.shell->saved_conversation_action(*area, kSecond);
    ASSERT_TRUE(select);
    select();
    window.run_deferred();
    ASSERT_TRUE(loop.pump_until([&] { driver.frame(); return !discussion().exchange_busy(); }, 30));
    ASSERT_EQ(discussion().exchange_id(), kSecond);
  }
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
  EXPECT_EQ(f.screen.maximized(), &other());  // The current layout's conversation, not the recorded one.
  EXPECT_EQ(discussion().exchange_id(), kSecond);  // The old question is not selected again.

  // A manual tab change in the split supersedes the return.
  ASSERT_NO_FATAL_FAILURE(focus_origin());
  ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  auto *shown = literature();
  ASSERT_NE(shown, nullptr);
  const int literature_tab = shown->active_tab();
  shown->set_active_tab(literature_tab == 0 ? 1 : 0);
  shown->set_active_tab(literature_tab);
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
  EXPECT_EQ(f.screen.maximized(), &other());
  EXPECT_EQ(discussion().exchange_id(), kSecond);

  // Closing and reopening the project gives a new opening handle; the old record has no effect.
  ASSERT_NO_FATAL_FAILURE(focus_origin());
  ASSERT_NO_FATAL_FAILURE(wait_for(kSecond));
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_NE(literature(), nullptr);
  const auto opening = handle();
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(project().open(dir.str() + "/project"));
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_NE(handle(), opening);
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_TRUE(f.shell->workbench_is_focused(f.screen));
  EXPECT_EQ(f.screen.maximized(), &other());
  EXPECT_NE(discussion().exchange_id(), kFirst);
  EXPECT_TRUE(literature_calls().empty());
}

TEST_F(FocusedLiteraturePython, AnArmedQuestionInAnotherSplitTabKeepsTheConversationShown)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_NO_FATAL_FAILURE(click("workbench_split"));
  ASSERT_EQ(f.screen.maximized(), nullptr);
  std::string armed;
  std::function<void()> send;
  ASSERT_NO_FATAL_FAILURE(prepare_automatic_question(other(), "Armed question in the other tab", armed, send));
  send();  // Armed: sent when that tab is drawn next.
  ASSERT_NO_FATAL_FAILURE(focus_origin());  // Draws only the origin conversation.
  ASSERT_TRUE(loop.pump_until([&] { f.drv->frame(); return !discussion().exchange_busy(); }, 30));
  ASSERT_EQ(discussion().exchange_id(), armed);
  ASSERT_NE(widget("ai_open_literature"), nullptr);

  // Entering the split would draw the armed tab, so the conversation stays shown.
  for (int attempt = 0; attempt < 2; ++attempt) {
    ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
    EXPECT_EQ(f.screen.maximized(), &origin());
    EXPECT_EQ(literature(), nullptr);
    EXPECT_EQ(&origin().editor(), conversation);
    EXPECT_EQ(draft(), "Unsent question kept while reading literature");
  }
  EXPECT_EQ(io::get_string(discussion().exchange_request(), "status"), "pending");
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));  // No start or model call.

  // Once that tab is no longer shown in its area, both directions work and it stays unsent.
  const auto exchange = discussion().exchange_generation();
  other().set_active_tab(0);
  f.drv->frame();
  ASSERT_NE(widget("ai_open_literature"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  EXPECT_EQ(f.screen.maximized(), nullptr);
  ASSERT_NE(literature(), nullptr);
  EXPECT_NE(other().editor().type().id, kEditorAI);
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(f.screen.maximized(), &origin());
  EXPECT_EQ(&origin().editor(), conversation);
  EXPECT_EQ(discussion().exchange_id(), armed);
  EXPECT_EQ(discussion().exchange_generation(), exchange);
  EXPECT_EQ(draft(), "Unsent question kept while reading literature");
  EXPECT_EQ(io::get_string(discussion().exchange_request(), "status"), "pending");
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
  EXPECT_TRUE(literature_calls().empty());
}

TEST_F(FocusedLiteraturePython, WorkbenchReturnDoesNotDispatchAnArmedQuestionInItsHiddenTab)
{
  ASSERT_NO_FATAL_FAILURE(start());
  ASSERT_TRUE(origin().add_tab(kEditorLiterature, false));
  f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(click("workbench_split"));
  std::string prepared;
  std::function<void()> send;
  ASSERT_NO_FATAL_FAILURE(prepare_automatic_question(origin(), "Question in the hidden tab", prepared, send));
  ASSERT_NO_FATAL_FAILURE(focus_origin());
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_EQ(literature(), &origin());
  ASSERT_EQ(f.screen.maximized(), nullptr);
  send();
  const auto exchange = discussion().exchange_generation();
  ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
  EXPECT_EQ(literature(), &origin());
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(discussion().exchange_id(), prepared);
  EXPECT_EQ(discussion().exchange_generation(), exchange);
  EXPECT_EQ(io::get_string(discussion().exchange_request(), "status"), "pending");
  ASSERT_NO_FATAL_FAILURE(idle());
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
  EXPECT_TRUE(literature_calls().empty());
}

TEST_F(FocusedLiteraturePython, HistoryAndAgentPagesHideTheEntryAndRejectRetainedCallbacks)
{
  ASSERT_NO_FATAL_FAILURE(start());
  auto stale = widget("ai_open_literature")->on_click;
  ASSERT_NO_FATAL_FAILURE(click("workbench_saved_questions"));
  ASSERT_NE(widget("ai_close_saved_questions"), nullptr);
  EXPECT_EQ(widget("ai_open_literature"), nullptr);
  stale();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_NE(widget("ai_close_saved_questions"), nullptr);
  EXPECT_EQ(literature(), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("ai_close_saved_questions"));
  ASSERT_NE(widget("ai_open_literature"), nullptr);
  stale = widget("ai_open_literature")->on_click;
  ASSERT_TRUE(project().agent().supported());
  const auto *intent = widget("ai_intent/" + handle());
  ASSERT_NE(intent, nullptr);
  intent->index.assign(3);
  f.drv->frame();
  ASSERT_NE(widget("ai_agent_text/" + handle()), nullptr);
  EXPECT_EQ(widget("ai_open_literature"), nullptr);
  stale();
  f.screen.run_deferred();
  f.drv->frame();
  EXPECT_NE(widget("ai_agent_text/" + handle()), nullptr);
  EXPECT_EQ(discussion().exchange_id(), kFirst);
  EXPECT_EQ(literature(), nullptr);
  EXPECT_TRUE(literature_calls().empty());
}

TEST_F(FocusedLiteraturePython, NoEntryWithoutAnAdoptedSavedQuestion)
{
  revision = project().project()->revision;
  ASSERT_TRUE(home().add_tab(kEditorAI));
  f.screen.set_maximized(&home());
  f.shell->open_workbench(f.screen);
  f.screen.run_deferred();
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return discussion().page("requests").loaded && !discussion().busy() && widget("ai_prepare");
  }, 30));
  ASSERT_TRUE(f.shell->workbench_is_focused(f.screen));
  EXPECT_TRUE(discussion().exchange_id().empty());
  EXPECT_NE(widget("project_workspace"), nullptr);
  EXPECT_EQ(widget("ai_open_literature"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("workbench_split"));
  ASSERT_TRUE(project().close());
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_FALSE(project().project());
  EXPECT_EQ(widget("ai_open_literature"), nullptr);
  ASSERT_NE(widget("tool_literature"), nullptr);
  ASSERT_NO_FATAL_FAILURE(click("tool_literature"));
  EXPECT_NE(literature(), nullptr);
  EXPECT_TRUE(literature_calls().empty());
}

// A legacy bridge (no project.agent.run_*) whose first agent message is saved while the project
// reads: the real ProjectAgent then keeps its Start for later. The wrapper runs the observing
// fixture's script unchanged and replaces only what this scenario needs: the session is saved
// directly in the project's ledger (the product's create needs a model route, which the fixture
// has none of), a Start is refused before any executor, and one project read can be held.
// ``agent_calls`` separates the three kinds: "request" (sent at once), "start" and "read".
class DeferredAgentStartLiteraturePython : public FocusedLiteraturePython {
 protected:
  static constexpr const char *kRefusedStart = "fixture refuses the agent start";

  void configure_bridge(bridge::ClientOptions &options, const std::string &python) override
  {
    FocusedLiteraturePython::configure_bridge(options, python);
    const auto script = dir.path() / "legacy_agent.py";
    std::ofstream(script) << R"PY(
import runpy
import threading
from pathlib import Path
from suan.desktop_bridge import __main__ as entry
from suan.desktop_bridge import server
from suan.desktop_bridge.protocol import BridgeError
from suan.project.agent_sessions import HARNESS, digest

here = Path(__file__).parent
serve = entry.main

def trace(kind, method):
    with (here / "agent_calls").open("a") as out:
        out.write(kind + " " + method + "\n")

def main():
    observed = server.Bridge.__init__
    def init(self, *args, **kwargs):
        observed(self, *args, **kwargs)
        for method in ("project.agent.run_target", "project.agent.run_plan", "project.agent.run_decide",
                       "project.agent.run_observe"):
            del self.methods[method]
        def create(params, call):
            trace("request", "project.agent.create")
            sessions = self.projects._get(params["handle"]).agent_sessions
            identity, text, turn = params["session_id"], params["text"], params["turn_id"]
            return sessions.create(identity, {"id": identity, "harness": HARNESS}, text, turn_id=turn,
                                   request_sha256=digest({"text": text, "turn_id": turn}))
        def start(params, call):
            trace("start", "project.agent.start")
            raise BridgeError("unavailable", "fixture refuses the agent start")
        def reading(method, original):
            def read(params, call):
                trace("read", method)
                return original(params, call)
            return read
        catalog = self.methods["project.catalog"]
        def held_catalog(params, call):
            gate = here / "hold_project_read"
            if gate.exists():
                (here / "project_read_held").touch()
                released = threading.Event()
                for _ in range(6000):
                    if not gate.exists() or released.wait(0.01):
                        break
            return catalog(params, call)
        self.methods["project.agent.create"] = create
        self.methods["project.agent.start"] = start
        for method in ("project.agent.route", "project.agent.list", "project.agent.get"):
            self.methods[method] = reading(method, self.methods[method])
        self.methods["project.catalog"] = held_catalog
    server.Bridge.__init__ = init
    serve()

entry.main = main
runpy.run_path(str(here / "observe.py"), run_name="__main__")
)PY";
    options.command[2] = core::path_to_utf8(script);
  }

  std::vector<std::string> agent_calls()
  {
    std::vector<std::string> calls;
    std::ifstream trace(dir.path() / "agent_calls");
    for (std::string line; std::getline(trace, line);) { calls.push_back(line); }
    return calls;
  }
  /** How many calls of one kind ("request", "start" or "read") the bridge received. */
  int agent_calls(const std::string &kind)
  {
    const auto calls = agent_calls();
    return int(std::count_if(calls.begin(), calls.end(), [&](const auto &line) { return line.starts_with(kind + " "); }));
  }
  /** Exactly the one saved message, no Start, and nothing the observing fixture forbids. */
  void expect_start_still_deferred()
  {
    auto &agent = project().agent();
    EXPECT_TRUE(agent.deferred_start_pending());
    EXPECT_FALSE(agent.busy());
    EXPECT_FALSE(project().busy());
    EXPECT_TRUE(agent.error().empty()) << agent.error();
    EXPECT_EQ(agent_calls("request"), 1);
    EXPECT_EQ(agent_calls("start"), 0);
    EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
  }
};

TEST_F(DeferredAgentStartLiteraturePython, LiteratureEntryAndReturnKeepADeferredLegacyAgentStartUndispatched)
{
  ASSERT_NO_FATAL_FAILURE(start());
  auto &agent = project().agent();
  ASSERT_TRUE(agent.supported());
  ASSERT_FALSE(agent.runs_supported());  // Legacy: a saved message is followed by Start, with no target.

  // The other conversation is left in Agent mode, then hidden behind the focused question.
  ASSERT_NO_FATAL_FAILURE(click("workbench_split"));
  ASSERT_EQ(f.screen.maximized(), nullptr);
  const int agent_tab = other().active_tab();
  ASSERT_EQ(other().editor().type().id, kEditorAI);
  const auto prefix = other().id() + "/main/";
  ASSERT_NE(widget(prefix + "ai_intent/" + handle()), nullptr);
  widget(prefix + "ai_intent/" + handle())->index.assign(3);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return widget(prefix + "ai_agent_text/" + handle()) && agent.route_loaded() && agent.list_loaded();
  }, 30)) << agent.error();
  ASSERT_NO_FATAL_FAILURE(focus_origin());
  ASSERT_NO_FATAL_FAILURE(wait_for(kFirst));
  ASSERT_NE(widget("ai_open_literature"), nullptr);
  EXPECT_EQ(widget("ai_agent_text/" + handle()), nullptr);
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_TRUE(agent.selected().empty());
  ASSERT_FALSE(agent.busy());
  ASSERT_EQ(agent_calls("request"), 0);
  ASSERT_EQ(agent_calls("start"), 0);
  ASSERT_GE(agent_calls("read"), 2);  // The route and the session list, read while that tab was drawn.

  // The message is sent while the project is idle; its saved reply arrives during a project read
  // that the bridge holds, so the real Start is refused locally and kept for later.
  std::ofstream(dir.path() / "hold_project_read") << "1";
  ASSERT_TRUE(agent.ask("Deferred legacy agent message"));
  ASSERT_TRUE(agent.busy());
  project().refresh();
  ASSERT_TRUE(project().busy());
  ASSERT_TRUE(loop.pump_until([&] {
    return agent.deferred_start_pending() && std::filesystem::exists(dir.path() / "project_read_held");
  }, 30)) << agent.error();
  EXPECT_TRUE(project().busy());
  EXPECT_FALSE(agent.busy());
  const auto session = agent.selected();
  ASSERT_FALSE(session.empty());
  EXPECT_EQ(io::get_string(agent.view().at("session"), "id"), session);
  EXPECT_FALSE(agent.running());
  EXPECT_FALSE(agent.history_selection_available());
  EXPECT_EQ(agent_calls("request"), 1);
  EXPECT_EQ(agent_calls("start"), 0);
  const int reads_before_idle = agent_calls("read");

  // The project becomes idle while only the question is drawn: nothing resumes the Start.
  std::filesystem::remove(dir.path() / "hold_project_read");
  ASSERT_NO_FATAL_FAILURE(idle());
  ASSERT_NO_FATAL_FAILURE(wait_for(kFirst));
  for (int frame = 0; frame < 3; ++frame) { loop.run_ready(); f.drv->frame(); }
  ASSERT_NO_FATAL_FAILURE(expect_start_still_deferred());
  ASSERT_EQ(f.screen.maximized(), &origin());
  ASSERT_NE(widget("ai_open_literature"), nullptr);
  const float reading = position();
  const auto exchange = discussion().exchange_generation();
  const auto selection = agent.selection_epoch();

  // Entering the split would draw the Agent tab, whose next draw sends the Start.
  for (int attempt = 0; attempt < 2; ++attempt) {
    ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
    loop.run_ready();
    f.drv->frame();
    EXPECT_EQ(literature(), nullptr);
    ASSERT_NO_FATAL_FAILURE(expect_same_conversation(reading, exchange));
    ASSERT_NO_FATAL_FAILURE(expect_start_still_deferred());
  }
  EXPECT_EQ(other().active_tab(), agent_tab);
  EXPECT_EQ(agent.selected(), session);
  EXPECT_EQ(agent.selection_epoch(), selection);

  // With the Agent tab no longer shown in its area, the entry opens and the Start still waits.
  other().set_active_tab(0);
  f.drv->frame();
  ASSERT_NE(other().editor().type().id, kEditorAI);
  ASSERT_NO_FATAL_FAILURE(click("ai_open_literature"));
  ASSERT_EQ(f.screen.maximized(), nullptr);
  ASSERT_NE(literature(), nullptr);
  ASSERT_NE(literature(), &origin());
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return !project().busy() && !discussion().busy() && !discussion().exchange_busy();
  }, 30));
  ASSERT_NO_FATAL_FAILURE(expect_start_still_deferred());

  // The recorded return is superseded by a tab change in the split; no conversation is shown
  // any more, so the ordinary Workbench destination is the first AI tab: the hidden Agent tab.
  ASSERT_EQ(origin().active_tab(), 1);
  origin().set_active_tab(0);
  f.drv->frame();
  ASSERT_NE(origin().editor().type().id, kEditorAI);
  auto *shown = literature();
  for (int attempt = 0; attempt < 2; ++attempt) {
    ASSERT_NO_FATAL_FAILURE(click("tool_workbench"));
    loop.run_ready();
    f.drv->frame();
    EXPECT_EQ(f.screen.maximized(), nullptr);
    EXPECT_FALSE(f.shell->workbench_is_focused(f.screen));
    EXPECT_EQ(literature(), shown);
    EXPECT_EQ(other().active_tab(), 0);
    EXPECT_EQ(origin().active_tab(), 0);
    ASSERT_NO_FATAL_FAILURE(expect_start_still_deferred());
  }
  EXPECT_EQ(agent.selected(), session);
  EXPECT_EQ(agent.selection_epoch(), selection);
  EXPECT_EQ(discussion().exchange_id(), kFirst);
  EXPECT_EQ(discussion().exchange_generation(), exchange);
  EXPECT_TRUE(literature_calls().empty());
  // Until here every agent call after the saved message was a read, if anything.
  EXPECT_EQ(agent_calls().size(), size_t(1 + agent_calls("read")));
  EXPECT_GE(agent_calls("read"), reads_before_idle);

  // Control: the Start was really waiting. Showing the Agent tab is what sends it, exactly once,
  // and the bridge refuses it before any executor or model.
  other().set_active_tab(agent_tab);
  ASSERT_TRUE(loop.pump_until([&] {
    f.drv->frame();
    return agent_calls("start") == 1 && !agent.busy() && !agent.error().empty();
  }, 30));
  EXPECT_EQ(agent.error(), kRefusedStart);
  EXPECT_FALSE(agent.deferred_start_pending());
  for (int frame = 0; frame < 3; ++frame) { loop.run_ready(); f.drv->frame(); }
  EXPECT_EQ(agent_calls("start"), 1);
  EXPECT_EQ(agent_calls("request"), 1);
  EXPECT_FALSE(agent.running());
  EXPECT_FALSE(std::filesystem::exists(dir.path() / "unexpected_write"));
}

}  // namespace
}  // namespace stk::app
