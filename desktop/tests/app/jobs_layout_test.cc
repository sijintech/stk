/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The Jobs editor's UI without a GPU (fake text measurer): layout goldens of the maximized
 * Jobs area with demo content (en / zh), drops, and the dialogs driven with synthesized events
 * against the fake bridge (Add Runtime, the path-field fallback of the file dialog, cancel). */

#include <cstdlib>
#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "../wm/support.hh"
#include "../bridge/fake_jobs.hh"
#include "jobs_support.hh"
#include "stk/app/jobs_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/io/payload.hh"
#include "stk/platform/file_dialog.hh"

namespace stk::jobstest {
namespace {

using wmtest::AppFixture;

std::string golden_path(const std::string &name)
{
  return std::string(STK_JOBS_GOLDEN_DIR) + "/" + name;
}

void check_golden(const std::string &got, const std::string &name)
{
  const std::string path = golden_path(name);
  if (const char *u = std::getenv("STK_UPDATE_GOLDENS"); u && *u == '1') {
    std::filesystem::create_directories(std::filesystem::path(path).parent_path());
    ASSERT_TRUE(wmtest::write_text(path, got)) << path;
    GTEST_SKIP() << "updated " << path;
  }
  const std::string want = wmtest::read_text(path);
  ASSERT_FALSE(want.empty()) << "missing golden " << path << " (run with STK_UPDATE_GOLDENS=1)";
  EXPECT_EQ(got, want) << "layout differs from " << path;
}

class JobsLayoutGolden : public ::testing::TestWithParam<const char *> {};

TEST_P(JobsLayoutGolden, MaximizedJobsEditorWithDemoContent)
{
  const std::string lang = GetParam();
  AppFixture f(lang, 1.0f, 1280, 800);
  app::JobsState &jobs = f.shell->store().jobs();
  populate_demo(jobs);
  f.screen.set_maximized(&f.tab("a1", app::kEditorJobs));
  f.drv->frame();
  const std::string got = wmtest::dump_screen(f.screen);
  /* The demo content is on screen. */
  const ui::Widget *table = f.screen.ui()->find("a1/main/tasks/tasks");
  ASSERT_NE(table, nullptr);
  EXPECT_EQ(table->table->rows, 5);
  EXPECT_EQ(table->table->cell(0, 0), "铁电畴 300K");
  EXPECT_EQ(table->table->cell(4, 1), std::string(f.shell->store().tr("jobs.state.cancelling")));
  const ui::Color failed = table->table->cell_color(3, 1), queued = table->table->cell_color(1, 1);
  EXPECT_GT(failed.a, 0);
  EXPECT_GT(failed.r, failed.g); /* red */
  EXPECT_EQ(queued.a, 0);        /* default text colour */
  EXPECT_NE(f.screen.ui()->find("a1/main/detail/task_log"), nullptr);
  EXPECT_NE(f.screen.ui()->find("a1/main/submit/name"), nullptr);
  check_golden(got, "jobs_layout_" + lang + ".json");
}

INSTANTIATE_TEST_SUITE_P(JobsLayout, JobsLayoutGolden, ::testing::Values("en", "zh"),
                         [](const ::testing::TestParamInfo<const char *> &i) { return std::string(i.param); });

TEST(JobsLayout, DropsOnJobsAndTransfersQueueUploads)
{
  AppFixture f("en");
  app::EditorArea &bottom = f.tab("a4", app::kEditorTransfers);
  f.drv->frame();
  auto drop = [&](wm::Area &a, std::vector<std::string> paths) {
    const auto [x, y] = AppFixture::center(a.find_region("main")->rect());
    wm::Event e;
    e.type = wm::EventType::Drop;
    e.x = x;
    e.y = y;
    e.paths = std::move(paths);
    const bool r = f.drv->send(e);
    f.drv->frame();
    return r;
  };
  EXPECT_TRUE(drop(f.tab("a1", app::kEditorJobs), {"/data/run1/phi.bin"}));
  EXPECT_TRUE(drop(bottom, {"/data/run1/input.toml"}));
  const app::JobsState &jobs = f.shell->store().jobs();
  ASSERT_EQ(jobs.pending_uploads().size(), 2u);
  const ui::Widget *t = f.screen.ui()->find("a4/main/transfers");
  ASSERT_NE(t, nullptr);
  EXPECT_EQ(t->table->rows, 2);
  EXPECT_EQ(t->table->cell(1, 0), "input.toml");
  EXPECT_EQ(t->table->cell(1, 4), std::string(f.shell->store().tr("transfers.state.pending")));
  EXPECT_NE(f.screen.ui()->find("a1/main/workspace/pending"), nullptr);
}

/** The application screen with its JobsState on the fake bridge (dialogs, fallback paths). */
struct UiOnFake {
  bridge::test::ManualLoop loop;
  bridge::test::TempDir dir{"jobs-ui"};
  AppFixture f{"en", 1.0f, 1280, 900};
  std::unique_ptr<bridge::Client> client;

  explicit UiOnFake(bool f03 = false, bool with_viewer = false)
  {
    std::vector<std::string> args{"--jobs", dir.str() + "/model"};
    if (f03) {
      args.push_back("--f03");
    }
    if (with_viewer) {
      args.insert(args.end(), {"--payload-dir", STK_DESKTOP_DIR "/tests/viewer/fixtures/muferro_domains",
                              "--presets-dir", STK_REPO_ROOT "/suan/graph/presets",
                              "--catalog", STK_REPO_ROOT "/docs/specs/catalog/stk-catalog-m1.json",
                              "--blob-dir", dir.str() + "/blobs"});
    }
    client = bridge::Client::create(bridge::test::fake_options(args, loop.executor()));
    f.shell->store().set_bridge(client.get());
    jobs().open_external = [](const std::string &, std::string *) { return true; };
    jobs().attach(client.get());
    client->start();
    f.screen.set_maximized(&f.tab("a1", app::kEditorJobs));
  }
  ~UiOnFake()
  {
    jobs().attach(nullptr);
    f.shell->store().set_bridge(nullptr);
    client->close();
    loop.run_ready();
  }
  app::JobsState &jobs()
  {
    return f.shell->store().jobs();
  }
  bool pump(const std::function<bool()> &until)
  {
    return loop.pump_until([&] {
      f.drv->frame();
      return until();
    }, 20.0);
  }
  const ui::Widget *find(const std::string &key)
  {
    f.drv->frame();
    return f.screen.ui()->find(key);
  }
  void click(const std::string &key)
  {
    const auto [x, y] = f.widget_center(key);
    f.drv->click(x, y);
    f.drv->frame();
  }
  void type(const std::string &key, const std::string &text)
  {
    click(key);
    f.drv->key(wm::Key::A, wm::ModCtrl);
    for (size_t i = 0; i < text.size();) {
      size_t n = 1;
      while (i + n < text.size() && (uint8_t(text[i + n]) & 0xC0) == 0x80) {
        n++;
      }
      f.drv->key(wm::Key::Unknown, wm::ModNone, text.substr(i, n));
      i += n;
    }
    f.drv->key(wm::Key::Enter);
    f.drv->frame();
  }
};

TEST(JobsLayout, OpenCancelDialogDisablesDispatchAfterItsTaskOrScopeChanges)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  for (const std::string_view change : {"terminal", "revoked", "scope"}) {
    SCOPED_TRACE(change);
    UiOnFake u(true);
    app::JobsState &jobs = u.jobs();
    ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
    jobs.select_connection("hub:mesh");
    ASSERT_TRUE(u.pump([&] { return !jobs.tasks().empty(); }));
    jobs.select_task(fake_jobs::kF03Task);
    ASSERT_TRUE(u.pump([&] { return jobs.selected_task_observation() == app::TaskObservation::Verified; }));
    u.click("a1/main/tasks/cancel_task");
    ASSERT_NE(u.find("jobs_dialog_a1/ok"), nullptr);
    ASSERT_TRUE(u.find("jobs_dialog_a1/ok")->enabled);

    if (change == "terminal") {
      jobs.apply_snapshot(io::Json::array({{{"id", jobs.selected()}, {"workspace_id", jobs.workspace()},
                                             {"state", "succeeded"}}}), 100.0);
    }
    else if (change == "revoked") {
      jobs.apply_nodes(io::Json::array({{{"id", jobs.node()}, {"role", "node"}, {"revoked", 1}}}));
    }
    else {
      jobs.select_connection("runtime:lab");
    }
    ASSERT_NE(u.find("jobs_dialog_a1/ok"), nullptr);
    EXPECT_FALSE(u.find("jobs_dialog_a1/ok")->enabled);
    u.click("jobs_dialog_a1/ok");
    bool drained = false;
    u.client->call("connections.list").then([&](const bridge::Result<io::Json> &) { drained = true; });
    ASSERT_TRUE(u.pump([&] { return drained; }));
    EXPECT_EQ(wmtest::read_text(u.dir.str() + "/model/methods.log").find("task.cancel\n"), std::string::npos);
  }
}

TEST(JobsLayout, FocusedTasksShowTheQueueAndRequireOpeningTheDraftToSubmit)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const auto workspace = jobs.workspace();
  u.f.shell->open_workbench(u.f.screen);
  u.f.screen.run_deferred();
  const auto navigate = [&](const char *key) {
    ASSERT_NE(u.find(key), nullptr);
    u.click(key);
    u.f.screen.run_deferred();
    u.f.drv->frame();
  };
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_tasks"));
  ASSERT_EQ(u.f.screen.maximized(), &u.f.area("a1"));
  const std::string base = "a1/main/focused_jobs/";
  const auto *queue = u.find(base + "tasks/tasks");
  ASSERT_NE(queue, nullptr);
  const auto queue_top = queue->rect.y;
  const auto *environment = u.find(base + "environment");
  ASSERT_NE(environment, nullptr);
  EXPECT_LT(queue_top, environment->rect.y);
  ASSERT_NE(jobs.active(), nullptr);
  EXPECT_NE(environment->text.find(jobs.active()->info.name), std::string::npos);
  EXPECT_EQ(u.find(base + "environment/conn/connection"), nullptr);
  EXPECT_EQ(u.find(base + "submit/submit_form"), nullptr);
  EXPECT_EQ(u.find("a1/header/submit"), nullptr);

  u.click(base + "environment");
  ASSERT_NE(u.find(base + "environment/conn/connection"), nullptr);
  EXPECT_EQ(jobs.workspace(), workspace);
  u.click(base + "environment");
  u.click(base + "submit");
  ASSERT_NE(u.find(base + "submit/submit_form"), nullptr);
  u.type(base + "submit/name", "Focused draft");
  EXPECT_EQ(jobs.form().name, "Focused draft");
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_results"));
  u.f.drv->ctx.rect.xmax = 680;
  u.f.drv->frame();
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_tasks"));
  const auto *name = u.find(base + "submit/name");
  ASSERT_NE(name, nullptr);
  EXPECT_EQ(name->string.value(), "Focused draft");
  EXPECT_EQ(jobs.workspace(), workspace);
  EXPECT_FALSE(jobs.submission());
  EXPECT_EQ(wmtest::read_text(u.dir.str() + "/model/methods.log").find("task.submit\n"), std::string::npos);
  u.click(base + "submit/submit_form");
  ASSERT_TRUE(u.pump([&] { return jobs.submission() && jobs.submission()->state == app::SubmitState::Done; }));
}

TEST(JobsLayout, FocusedTaskEnvironmentGuidesSetupAndHonorsDisclosure)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  auto &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string workspace = jobs.workspace();
  jobs.select_workspace("");
  jobs.form().name = "Unsubmitted task draft";
  u.f.shell->open_workbench(u.f.screen);
  u.f.screen.run_deferred();
  u.f.drv->frame();
  u.click("workbench_tasks");
  ASSERT_TRUE(u.f.shell->workbench_is_focused(u.f.screen));

  const std::string panel = "a1/main/focused_jobs/environment";
  const std::string picker = panel + "/workspace/workspace";
  const auto *control = u.find(picker);
  ASSERT_NE(control, nullptr);  // Setup is already open before a workspace is selected.
  ASSERT_TRUE(u.f.screen.ui()->focus_widget(control->id));
  ASSERT_TRUE(u.f.drv->key(wm::Key::Enter));
  ASSERT_TRUE(u.f.drv->key(wm::Key::End));
  ASSERT_TRUE(u.f.drv->key(wm::Key::Enter));
  EXPECT_EQ(jobs.workspace(), workspace);
  EXPECT_EQ(u.find(picker), nullptr);
  const auto *header = u.find(panel);
  ASSERT_NE(header, nullptr);
  EXPECT_EQ(u.f.screen.ui()->focused(), header->id);

  jobs.select_workspace("");
  EXPECT_NE(u.find(picker), nullptr);
  jobs.select_workspace(workspace);
  EXPECT_NE(u.find(picker), nullptr);  // After setup has retired, recovery stays open.
  u.click(panel);
  jobs.select_workspace("");
  EXPECT_EQ(u.find(picker), nullptr);  // An explicit close wins even after losing scope.
  u.click(panel);
  jobs.select_workspace(workspace);
  EXPECT_NE(u.find(picker), nullptr);  // An explicit open also survives scope changes.
  EXPECT_EQ(jobs.form().name, "Unsubmitted task draft");
  EXPECT_FALSE(jobs.submission());
  EXPECT_EQ(wmtest::read_text(u.dir.str() + "/model/methods.log").find("task.submit\n"), std::string::npos);
}

TEST(JobsLayout, ANewWorkspaceShowsTheFirstTaskFormAndRequiresExplicitSubmit)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  auto &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string old_workspace = jobs.workspace();
  jobs.select_workspace("");
  jobs.form().name = "First task draft";
  u.f.shell->open_workbench(u.f.screen);
  u.f.screen.run_deferred();
  u.f.drv->frame();
  u.click("workbench_tasks");
  ASSERT_TRUE(u.f.shell->workbench_is_focused(u.f.screen));

  const std::string base = "a1/main/focused_jobs/";
  const std::string environment = base + "environment";
  const std::string create = environment + "/workspace/new_workspace";
  const std::string submit = base + "submit/submit_form";
  const auto create_workspace = [&](const std::string &name) {
    ASSERT_NE(u.find(create), nullptr);
    u.click(create);
    u.type("jobs_dialog_a1/name", name);
    u.click("jobs_dialog_a1/ok");
  };
  EXPECT_EQ(u.find(submit), nullptr);
  ASSERT_NO_FATAL_FAILURE(create_workspace("New synthetic workspace"));
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty() && jobs.workspace() != old_workspace; }));
  const std::string created = jobs.workspace();
  ASSERT_EQ(u.find(create), nullptr);  // The untouched setup disclosure folded after adoption.
  ASSERT_NE(u.find(submit), nullptr);
  const auto *name = u.find(base + "submit/name");
  ASSERT_NE(name, nullptr);
  EXPECT_EQ(name->string.value(), "First task draft");
  EXPECT_FALSE(jobs.submission());
  {
    wm::Screen other;
    u.f.shell->install(other, nullptr);
    u.f.shell->build_default_layout(other);
    struct ForgetScreen {
      app::AppShell *shell;
      wm::Screen &screen;
      ~ForgetScreen() { shell->forget(screen); }
    } cleanup{u.f.shell.get(), other};
    wmtest::ScreenDriver driver(other, 680, 900, 1);
    u.f.shell->open_workbench(other);
    other.run_deferred();
    driver.frame();
    const auto *tasks = other.ui()->find("workbench_tasks");
    ASSERT_NE(tasks, nullptr);
    driver.click(int(tasks->rect.cx()), other.rect().ymax - 1 - int(tasks->rect.cy()));
    other.run_deferred();
    driver.frame();
    ASSERT_NE(other.ui()->find(base + "submit"), nullptr);
    EXPECT_EQ(other.ui()->find(submit), nullptr);
  }
  const auto methods = [&] { return wmtest::read_text(u.dir.str() + "/model/methods.log"); };
  EXPECT_EQ(methods().find("task.submit\n"), std::string::npos);
  u.click(submit);
  ASSERT_TRUE(u.pump([&] { return jobs.submission() && jobs.submission()->state == app::SubmitState::Done; }));
  const auto log = methods();
  const auto sent = log.find("task.submit\n");
  ASSERT_NE(sent, std::string::npos);
  EXPECT_EQ(log.find("task.submit\n", sent + 1), std::string::npos);
  EXPECT_EQ(jobs.workspace(), created);

  jobs.select_workspace(old_workspace);
  EXPECT_NE(u.find(submit), nullptr);  // Preserve the open form when changing the intended destination.
  jobs.select_workspace(created);
  ASSERT_NE(u.find(submit), nullptr);
  u.click(base + "submit");
  ASSERT_EQ(u.find(submit), nullptr);
  u.click(environment);
  ASSERT_NO_FATAL_FAILURE(create_workspace("New synthetic workspace"));
  // The real bridge posts its reply to the manual loop. Replace the dialog before processing it.
  u.click("jobs_dialog_a1/cancel");
  ASSERT_NE(u.find(create), nullptr);
  u.click(create);
  u.type("jobs_dialog_a1/name", "Keep this workspace draft");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty() && jobs.workspace() != created; }));
  const auto *workspace_name = u.find("jobs_dialog_a1/name");
  ASSERT_NE(workspace_name, nullptr);
  EXPECT_EQ(workspace_name->string.value(), "Keep this workspace draft");
  u.click("jobs_dialog_a1/cancel");
  EXPECT_EQ(u.find(submit), nullptr);  // Manual collapse takes precedence for a later creation.
  jobs.select_workspace(old_workspace);
  EXPECT_EQ(u.find(submit), nullptr);
  EXPECT_EQ(jobs.form().name, "First task draft");
  EXPECT_EQ(methods().find("task.submit\n", sent + 1), std::string::npos);
}

TEST(JobsLayout, OpeningATaskResultKeepsTheFocusedWorkbench)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  auto &jobs = u.jobs();
  auto &store = u.f.shell->store();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string task(32, 'c');
  const auto workspace = jobs.workspace();
  jobs.apply_snapshot(io::Json::array({{{"id", task}, {"workspace_id", workspace},
                                        {"name", "Result task"}, {"state", "succeeded"}}}), 100.0);
  jobs.select_task(task);
  u.f.shell->open_workbench(u.f.screen);
  u.f.screen.run_deferred();
  const auto navigate = [&](const std::string &key) {
    ASSERT_NE(u.find(key), nullptr);
    u.click(key);
    u.f.screen.run_deferred();
    u.f.drv->frame();
  };
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_tasks"));
  auto *jobs_editor = &u.f.area("a1").editor();
  auto *viewer_editor = &u.f.area("a2").editor();
  const std::string base = "a1/main/focused_jobs/";
  u.click(base + "submit");
  u.type(base + "submit/name", "Keep the draft");

  ASSERT_NO_FATAL_FAILURE(navigate(base + "tasks/open_viewer"));
  ASSERT_EQ(u.f.screen.maximized(), &u.f.area("a2"));
  EXPECT_TRUE(u.f.shell->workbench_is_focused(u.f.screen));
  EXPECT_EQ(&u.f.area("a2").editor(), viewer_editor);
  EXPECT_EQ(store.viewer().source().task_id, task);
  EXPECT_EQ(store.viewer().source().workspace_id, workspace);
  EXPECT_EQ(store.viewer().source().connection, "runtime:lab");
  EXPECT_TRUE(store.viewer().fit_initial_view());
  const auto source_camera = store.viewer().camera_serial();
  const auto source_payload = store.viewer().payload_serial();
  const auto evaluations = store.viewer().evaluations_started();
  ASSERT_NO_FATAL_FAILURE(navigate("result_source"));
  const auto *fields = u.find("viewer_source_details/fields");
  ASSERT_NE(fields, nullptr);
  ASSERT_TRUE(fields->list);
  std::string details;
  for (int row = 0; row < fields->list->count; ++row) {
    details += fields->list->text(row) + "\n";
  }
  EXPECT_NE(details.find("runtime:lab"), std::string::npos);
  EXPECT_NE(details.find(workspace), std::string::npos);
  EXPECT_NE(details.find(task), std::string::npos);
  u.f.drv->key(wm::Key::Space, wm::ModCtrl);
  EXPECT_EQ(u.f.screen.maximized(), &u.f.area("a2"));
  u.f.drv->key(wm::Key::Numpad1);
  EXPECT_TRUE(u.f.area("a2").editor().save_workspace_state().at("pending_preset").is_null());
  u.f.drv->key(wm::Key::Tab);
  u.f.drv->key(wm::Key::Esc);
  EXPECT_EQ(u.find("viewer_source_details/fields"), nullptr);
  u.f.drv->key(wm::Key::Enter);
  ASSERT_NE(u.find("viewer_source_details/fields"), nullptr);
  ASSERT_NO_FATAL_FAILURE(navigate("viewer_source_details/close"));
  EXPECT_EQ(u.find("viewer_source_details/fields"), nullptr);
  EXPECT_EQ(store.viewer().camera_serial(), source_camera);
  EXPECT_EQ(store.viewer().payload_serial(), source_payload);
  EXPECT_EQ(store.viewer().evaluations_started(), evaluations);
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_tasks"));
  EXPECT_EQ(&u.f.area("a1").editor(), jobs_editor);
  EXPECT_EQ(jobs.selected(), task);
  ASSERT_NE(u.find(base + "submit/name"), nullptr);
  EXPECT_EQ(u.find(base + "submit/name")->string.value(), "Keep the draft");
  EXPECT_FALSE(jobs.submission());

  // A selection that changes before the deferred open must leave the current view intact.
  const auto task_action = u.find(base + "tasks/open_viewer")->on_click;
  task_action();
  jobs.select_task("");
  jobs.select_task(task);
  const auto source_version = store.viewer().version();
  u.f.screen.run_deferred();
  EXPECT_EQ(u.f.screen.maximized(), &u.f.area("a1"));
  EXPECT_EQ(store.viewer().version(), source_version);

  const auto stale_page_action = u.find(base + "tasks/open_viewer")->on_click;
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_home"));
  ASSERT_NO_FATAL_FAILURE(navigate("workbench_tasks"));
  stale_page_action();
  u.f.screen.run_deferred();
  EXPECT_EQ(u.f.screen.maximized(), &u.f.area("a1"));
  EXPECT_EQ(store.viewer().version(), source_version);

  // An older request from the split view must not replace the focused result afterwards.
  const auto focused_action = u.find(base + "tasks/open_viewer")->on_click;
  app::OpenResultRequest queued;
  queued.task_id = std::string(32, 'd');
  store.request_open_result(std::move(queued));
  focused_action();
  u.f.screen.run_deferred();
  u.f.drv->frame();
  EXPECT_FALSE(store.has_open_result());
  EXPECT_EQ(u.f.screen.maximized(), &u.f.area("a2"));
  EXPECT_EQ(store.viewer().source().task_id, task);

  ASSERT_NO_FATAL_FAILURE(navigate("workbench_split"));
  ASSERT_NO_FATAL_FAILURE(navigate("a1/main/tasks/open_viewer"));
  EXPECT_EQ(u.f.screen.maximized(), nullptr);
  EXPECT_EQ(&u.f.area("a2").editor(), viewer_editor);
  EXPECT_EQ(store.viewer().source().task_id, task);
  EXPECT_FALSE(store.viewer().fit_initial_view());
  EXPECT_EQ(wmtest::read_text(u.dir.str() + "/model/methods.log").find("task.submit\n"), std::string::npos);
}

TEST(JobsLayout, FocusedTaskResultReturnKeepsSameAreaScrollAndLauncher)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  auto &jobs = u.jobs();
  auto &shared = u.f.area("a1");
  auto &other = u.f.area("a2");
  ASSERT_TRUE(shared.add_tab(app::kEditorViewer, false));
  for (int i = 0; i < other.tab_count(); ++i) {
    if (other.tab(i).type().id == app::kEditorViewer) {
      ASSERT_TRUE(other.set_tab_type(i, app::kEditorFiles));
    }
  }
  u.f.drv->ctx.rect.ymax = 540;
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string task(32, 'c');
  jobs.apply_snapshot(io::Json::array({{{"id", task}, {"workspace_id", jobs.workspace()},
                                        {"name", "Result task"}, {"state", "succeeded"}}}), 100.0);
  jobs.select_task(task);
  jobs.form().name = "Keep the draft";
  u.f.shell->open_workbench(u.f.screen);
  u.f.drv->frame();
  u.click("workbench_tasks");
  ASSERT_EQ(u.f.screen.maximized(), &shared);
  auto *original = &shared.editor();
  ASSERT_EQ(original->type().id, app::kEditorJobs);
  const std::string body = "a1/main/focused_jobs/";
  u.click(body + "submit");
  const auto [x, y] = u.f.widget_center(body + "environment");
  wm::Event wheel;
  wheel.type = wm::EventType::Wheel;
  wheel.x = x;
  wheel.y = y;
  wheel.wheel_y = -1;
  u.f.drv->send(wheel);
  const std::string launcher_key = body + "tasks/open_viewer";
  const auto *launcher = u.find(launcher_key);
  ASSERT_NE(launcher, nullptr);
  const float scroll = launcher->block->scroll();
  ASSERT_GT(scroll, 0.0f);

  u.click(launcher_key);
  ASSERT_EQ(u.f.screen.maximized(), &shared);
  ASSERT_EQ(shared.editor().type().id, app::kEditorViewer);
  EXPECT_EQ(u.f.shell->store().viewer().source().task_id, task);
  u.click("workbench_tasks");
  ASSERT_EQ(u.f.screen.maximized(), &shared);
  ASSERT_EQ(&shared.editor(), original);
  launcher = u.find(launcher_key);
  ASSERT_NE(launcher, nullptr);
  EXPECT_EQ(launcher->block->scroll(), scroll);
  EXPECT_EQ(u.f.screen.ui()->focused(), launcher->id);
  EXPECT_EQ(jobs.selected(), task);
  EXPECT_EQ(jobs.form().name, "Keep the draft");
  EXPECT_FALSE(jobs.submission());

  u.click(launcher_key);
  ASSERT_EQ(shared.editor().type().id, app::kEditorViewer);
  const std::string newer_task(32, 'd');
  jobs.apply_snapshot(io::Json::array({{{"id", newer_task}, {"workspace_id", jobs.workspace()},
                                        {"name", "Other task"}, {"state", "succeeded"}}}), 101.0);
  jobs.select_task(newer_task);
  u.click("workbench_tasks");
  EXPECT_EQ(jobs.selected(), newer_task);
  launcher = u.find(launcher_key);
  ASSERT_NE(launcher, nullptr);
  EXPECT_NE(u.f.screen.ui()->focused(), launcher->id);
}

TEST(JobsLayout, RevisitingAnAcceptedTaskKeepsTheDisplayedResult)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u(false, true);
  auto &jobs = u.jobs();
  auto &viewer = u.f.shell->store().viewer();
  viewer.prefetch_neighbours = false;
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string task(32, 'c'), other_task(32, 'd');
  const auto workspace = jobs.workspace();
  const auto apply_tasks = [&] {
    jobs.apply_snapshot(io::Json::array({
        {{"id", task}, {"workspace_id", workspace}, {"name", "Result task"}, {"state", "succeeded"}},
        {{"id", other_task}, {"workspace_id", workspace}, {"name", "Other task"}, {"state", "succeeded"}}}), 100.0);
  };
  apply_tasks();
  jobs.select_task(task);
  u.f.shell->open_workbench(u.f.screen);
  u.f.drv->frame();
  u.click("workbench_tasks");
  const std::string base = "a1/main/focused_jobs/";
  u.click(base + "submit");
  u.type(base + "submit/name", "Keep the draft");
  u.click(base + "tasks/open_viewer");
  const auto settled = [&] { return viewer.payload() && !viewer.evaluating(); };
  ASSERT_TRUE(u.pump(settled)) << viewer.eval_error();
  ASSERT_TRUE(viewer.graph_inspection()->shown_configuration);
  const auto initial_step = viewer.shown_step();
  viewer.set_step_index(0);
  ASSERT_TRUE(u.pump([&] { return settled() && viewer.shown_step() != initial_step; })) << viewer.eval_error();
  app::PickInfo pick;
  pick.probe_node = "frame";
  pick.physical = {1, 2, 3};
  viewer.set_pick(pick);
  ASSERT_TRUE(u.pump([&] { return viewer.probe().status == app::ProbeState::Status::Done; }));
  const auto step = viewer.shown_step();
  const auto camera = viewer.camera_serial();
  const auto payload = viewer.payload();
  const auto probe = viewer.probe().serial;
  const auto evaluations = viewer.evaluations_started();

  u.click("workbench_tasks");
  u.click(base + "tasks/open_viewer");
  const auto *revisited_area = dynamic_cast<const app::EditorArea *>(u.f.screen.maximized());
  ASSERT_NE(revisited_area, nullptr);
  EXPECT_EQ(revisited_area->editor().type().id, app::kEditorViewer);
  EXPECT_EQ(viewer.shown_step(), step);
  EXPECT_EQ(viewer.camera_serial(), camera);
  EXPECT_EQ(viewer.payload(), payload);
  EXPECT_EQ(viewer.probe().serial, probe);
  EXPECT_EQ(viewer.probe().status, app::ProbeState::Status::Done);
  EXPECT_EQ(viewer.evaluations_started(), evaluations);
  u.click("workbench_tasks");
  ASSERT_NE(u.find(base + "submit/name"), nullptr);
  EXPECT_EQ(u.find(base + "submit/name")->string.value(), "Keep the draft");
  EXPECT_EQ(jobs.selected(), task);

  jobs.select_task(other_task);
  ASSERT_NE(u.find(base + "tasks/open_viewer"), nullptr);
  u.click(base + "tasks/open_viewer");
  ASSERT_TRUE(u.pump([&] { return settled() && viewer.source().task_id == other_task; })) << viewer.eval_error();
  EXPECT_EQ(viewer.shown_step(), initial_step);
  EXPECT_GT(viewer.evaluations_started(), evaluations);
  const auto accepted_request = jobs.selected_result_request();
  ASSERT_TRUE(accepted_request);
  EXPECT_TRUE(viewer.can_revisit_task_result(*accepted_request));
  bridge::ConnectionCheck check;
  check.id = "runtime:lab";
  check.error = bridge::Error::make(bridge::ErrorCode::Unauthorized, "Credential check denied");
  jobs.apply_check(check);
  EXPECT_FALSE(viewer.can_revisit_task_result(*accepted_request));
  check.ok = true;
  check.error.reset();
  jobs.apply_check(check);
  const auto after_recheck = jobs.selected_result_request();
  ASSERT_TRUE(after_recheck);
  EXPECT_FALSE(viewer.can_revisit_task_result(*after_recheck));
  const auto before_recheck_open = viewer.evaluations_started();

  u.click("workbench_tasks");
  u.click(base + "tasks/open_viewer");
  ASSERT_TRUE(u.pump(settled)) << viewer.eval_error();
  EXPECT_GT(viewer.evaluations_started(), before_recheck_open);
  const auto before_reselect = viewer.evaluations_started();

  u.click("workbench_tasks");
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return jobs.workspace() == workspace; }));
  apply_tasks();
  jobs.select_task(other_task);
  ASSERT_NE(u.find(base + "tasks/open_viewer"), nullptr);
  u.click(base + "tasks/open_viewer");
  ASSERT_TRUE(u.pump([&] { return settled() && viewer.evaluations_started() > before_reselect; })) << viewer.eval_error();
  EXPECT_EQ(viewer.source().task_id, other_task);
}

TEST(JobsLayout, FocusedResultSourceWrapsAndScrollsLongLocalLabels)
{
  AppFixture f("en", 1.0f, 680, 1000);
  auto &viewer = f.shell->store().viewer();
  const auto payload = std::make_shared<io::Payload>(io::read_stkp(
      std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
  std::string label = "/local/";
  for (int i = 0; i < 160; ++i) { label += "subdirectory/"; }
  label += "result.stkp\nTAIL";
  viewer.open_payload(payload, label);
  f.shell->open_workbench(f.screen, true);
  f.drv->frame();
  auto *ui = f.screen.ui();
  const auto [x, y] = f.widget_center("result_source");
  f.drv->click(x, y);
  f.drv->frame();
  const auto *fields = ui->find("viewer_source_details/fields");
  ASSERT_NE(fields, nullptr);
  ASSERT_TRUE(fields->list);
  ASSERT_GT(fields->list->count, int(fields->list->rows));
  EXPECT_NE(fields->list->text(0).find("Payload"), std::string::npos);
  EXPECT_NE(fields->list->text(fields->list->count - 1).find("\\x0ATAIL"), std::string::npos);
  const auto fields_id = fields->id;
  f.drv->key(wm::Key::Tab);
  EXPECT_EQ(ui->focused(), fields_id);
  f.drv->key(wm::Key::End);
  f.drv->frame();
  EXPECT_GT(ui->scroll_of(fields_id), 0.0f);
  f.drv->key(wm::Key::Esc);
  f.drv->frame();
  EXPECT_EQ(ui->find("viewer_source_details/fields"), nullptr);
  ASSERT_NE(ui->find("result_source"), nullptr);
  EXPECT_EQ(ui->focused(), ui->find("result_source")->id);
  EXPECT_EQ(viewer.base_payload(), payload);
}

TEST(JobsLayout, AddRuntimeDialogAndThePathFieldFallback)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  /* Add Runtime: the dialog opens, validates, and connects to the new profile. */
  u.click("a1/main/conn/add_runtime");
  ASSERT_NE(u.find("jobs_dialog_a1/token"), nullptr);
  EXPECT_TRUE(u.find("jobs_dialog_a1/token")->text_opts.password);
  u.click("jobs_dialog_a1/ok");
  EXPECT_NE(u.find("jobs_dialog_a1/ok"), nullptr); /* still open: no name */
  u.type("jobs_dialog_a1/name", "cluster");
  u.type("jobs_dialog_a1/token", "s3cret");
  u.click("jobs_dialog_a1/ok");
  ASSERT_TRUE(u.pump([&] { return jobs.active_id() == "runtime:cluster"; }));
  ASSERT_TRUE(u.pump([&] { return u.f.screen.ui()->find("jobs_dialog_a1/ok") == nullptr; }));
  /* The status bar shows the connection. */
  EXPECT_NE(u.f.shell->store().connection().find("cluster"), std::string::npos);
  /* The bridge's copy of the token never reaches the UI state. */
  EXPECT_EQ(u.f.shell->store().connection().find("s3cret"), std::string::npos);

  /* Back to the lab Runtime; no native dialog here: "Upload files…" asks for paths instead. */
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string file = (u.dir.path() / "数据.bin").string();
  std::ofstream(file) << "12345";
  u.click("a1/main/workspace/upload_files");
  ASSERT_NE(u.find("jobs_dialog_a1/paths"), nullptr);
  u.type("jobs_dialog_a1/paths", "relative/path");
  u.click("jobs_dialog_a1/ok");
  ASSERT_NE(u.find("jobs_dialog_a1/paths"), nullptr); /* refused: not absolute */
  u.type("jobs_dialog_a1/paths", "file://" + file);
  u.click("jobs_dialog_a1/ok");
  ASSERT_TRUE(u.pump([&] { return jobs.workspace_files().size() == 1; }));
  EXPECT_EQ(jobs.workspace_files()[0].path, "数据.bin");
}

TEST(JobsLayout, ManagedSSHConfigurationAndConnectionButtons)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  u.click("a1/main/conn/add_runtime");
  u.type("jobs_dialog_a1/name", "ssh-cluster");
  u.type("jobs_dialog_a1/token", "s3cret");
  u.click("jobs_dialog_a1/managed_ssh");
  ASSERT_NE(u.find("jobs_dialog_a1/ssh_host"), nullptr);
  u.click("jobs_dialog_a1/ok");
  ASSERT_NE(u.find("jobs_dialog_a1/ssh_host"), nullptr); /* missing Host keeps the dialog */
  u.type("jobs_dialog_a1/ssh_host", "cluster-alias");
  u.click("jobs_dialog_a1/ok");
  ASSERT_TRUE(u.pump([&] { return jobs.active_id() == "runtime:ssh-cluster" && jobs.active() &&
                                jobs.active()->health == app::Health::Online; }));
  EXPECT_EQ(jobs.active()->info.raw["ssh"]["host"], "cluster-alias");
  ASSERT_NE(u.find("a1/main/conn/ssh_disconnect"), nullptr);
  u.click("a1/main/conn/ssh_disconnect");
  ASSERT_TRUE(u.pump([&] { return jobs.active()->info.raw["ssh"]["state"] == "stopped"; }));
  EXPECT_EQ(jobs.active()->health, app::Health::Offline);
  u.click("a1/main/conn/ssh_connect");
  ASSERT_TRUE(u.pump([&] { return jobs.active()->info.raw["ssh"]["state"] == "ready" &&
                                jobs.active()->health == app::Health::Online; }));
}

TEST(JobsLayout, SubmitFromTheFormWithAChineseName)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  /* IME: preedit, then the committed text (as GHOST delivers on Wayland / macOS / Windows). */
  u.click("a1/main/submit/name");
  wm::Event e;
  e.type = wm::EventType::ImeStart;
  u.f.drv->send(e);
  e.type = wm::EventType::ImeUpdate;
  e.ime.composite = "tie dian chou";
  e.ime.cursor = int(e.ime.composite.size());
  u.f.drv->send(e);
  u.f.drv->frame();
  EXPECT_TRUE(jobs.form().name.empty()); /* preedit is not text yet */
  e.ime = {};
  e.ime.result = "铁电畴";
  u.f.drv->send(e);
  e.type = wm::EventType::ImeEnd;
  e.ime = {};
  u.f.drv->send(e);
  u.f.drv->key(wm::Key::Unknown, wm::ModNone, " ");
  u.f.drv->key(wm::Key::Unknown, wm::ModNone, "3");
  u.f.drv->key(wm::Key::Enter);
  u.f.drv->frame();
  EXPECT_EQ(jobs.form().name, "铁电畴 3");
  u.click("a1/main/submit/submit_form");
  ASSERT_TRUE(u.pump([&] { return jobs.submission() && jobs.submission()->state == app::SubmitState::Done; }));
  ASSERT_TRUE(u.pump([&] {
    for (const app::TaskRow &t : jobs.tasks()) {
      if (t.name == "铁电畴 3") {
        return true;
      }
    }
    return false;
  }));
  /* Cancel through the confirmation dialog. */
  u.click("a1/main/tasks/cancel_task");
  if (u.find("jobs_dialog_a1/ok")) {
    u.click("jobs_dialog_a1/ok");
  }
}

/** A native dialog stand-in: answers at once with the scripted result and records the request. */
class ScriptedDialog final : public platform::FileDialog {
 public:
  std::string name() const override
  {
    return "scripted";
  }
  void open(const platform::FileDialogRequest &request, std::function<void(platform::FileDialogResult)> done) override
  {
    requests.push_back(request);
    done(next);
  }
  platform::FileDialogResult next;
  std::vector<platform::FileDialogRequest> requests;
};

TEST(JobsLayout, NativeDialogPathsAndItsFallback)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  ScriptedDialog dialog;
  jobs.file_dialog = &dialog;
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::filesystem::path folder = u.dir.path() / "输入";
  std::filesystem::create_directories(folder);
  std::ofstream(folder / "a.json") << "{}";
  /* The native dialog picks a folder: uploaded without a path field. */
  dialog.next.paths = {folder.string()};
  u.click("a1/main/workspace/upload_folder");
  ASSERT_EQ(dialog.requests.size(), 1u);
  EXPECT_EQ(dialog.requests[0].mode, platform::FileDialogMode::OpenFolder);
  EXPECT_EQ(u.find("jobs_dialog_a1/paths"), nullptr);
  ASSERT_TRUE(u.pump([&] { return jobs.workspace_files().size() == 1; }));
  EXPECT_EQ(jobs.workspace_files()[0].path, "a.json"); /* contents at the workspace root */
  /* Cancelled: nothing happens. */
  dialog.next = {};
  u.click("a1/main/workspace/upload_files");
  EXPECT_EQ(u.find("jobs_dialog_a1/paths"), nullptr);
  /* The dialog cannot run (no portal, zenity missing ...): the path field takes over. */
  dialog.next.error = "zenity: exited with status 255";
  u.click("a1/main/workspace/upload_files");
  ASSERT_NE(u.find("jobs_dialog_a1/paths"), nullptr);
  jobs.file_dialog = nullptr;
}

TEST(JobsLayout, PathListsFromTheFallbackField)
{
  EXPECT_EQ(platform::split_path_list("/a/b; /c d/e ;;"), (std::vector<std::string>{"/a/b", "/c d/e"}));
  EXPECT_EQ(platform::split_path_list("/x\n  '/y z'\n\n"), (std::vector<std::string>{"/x", "/y z"}));
  EXPECT_EQ(platform::split_path_list("file:///tmp/%E6%95%B0%E6%8D%AE%20a.bin"),
            (std::vector<std::string>{"/tmp/数据 a.bin"}));
  const std::vector<std::string> home = platform::split_path_list("~/data");
  ASSERT_EQ(home.size(), 1u);
  EXPECT_TRUE(platform::is_absolute_path(home[0]));
  EXPECT_FALSE(platform::is_absolute_path("relative/x"));
}

TEST(JobsLayout, TransfersEditorResumesAndCancels)
{
  if (std::string(STK_BRIDGE_FAKE).empty()) {
    GTEST_SKIP() << "stk-bridge-fake is not built on this platform";
  }
  UiOnFake u;
  app::JobsState &jobs = u.jobs();
  u.f.screen.set_maximized(nullptr);
  app::EditorArea &bottom = u.f.tab("a4", app::kEditorTransfers);
  u.f.screen.set_maximized(&bottom);
  ASSERT_TRUE(u.pump([&] { return jobs.ready() && !jobs.connections().empty(); }));
  jobs.select_connection("runtime:lab");
  ASSERT_TRUE(u.pump([&] { return !jobs.workspace().empty(); }));
  const std::string file = (u.dir.path() / "interrupted-upload.bin").string();
  std::ofstream(file) << std::string(1000, 'x');
  jobs.upload({file});
  ASSERT_TRUE(u.pump([&] { return !jobs.transfers().empty() && jobs.transfers()[0].state == "interrupted"; }));
  const ui::Widget *t = u.find("a4/main/transfers");
  ASSERT_NE(t, nullptr);
  EXPECT_EQ(t->table->cell(0, 4), std::string(u.f.shell->store().tr("transfers.state.interrupted")));
  EXPECT_EQ(t->table->cell(0, 2), "50");
  /* Select the first row (below the header row), then Resume. */
  {
    const ui::Widget *tw = u.find("a4/main/transfers");
    const float unit = u.f.screen.ui()->style().unit;
    const int x = int(tw->rect.x + 3 * unit);
    const int y = u.f.screen.rect().ymax - 1 - int(tw->rect.y + 1.5f * unit);
    u.f.drv->click(x, y);
    u.f.drv->frame();
  }
  ASSERT_TRUE(u.find("a4/main/resume")->enabled);
  const std::string transfer_id = jobs.transfers()[0].id;
  ASSERT_TRUE(u.find("a4/main/cancel")->enabled);
  u.click("a4/main/cancel");
  ASSERT_TRUE(u.pump([&] { return jobs.transfers()[0].state == "cancelled"; }));
  EXPECT_FALSE(u.find("a4/main/cancel")->enabled);
  ASSERT_TRUE(u.find("a4/main/resume")->enabled);
  u.click("a4/main/resume");
  ASSERT_TRUE(u.pump([&] { return jobs.transfers()[0].state == "completed"; }));
  ASSERT_EQ(jobs.transfers().size(), 1u);
  EXPECT_EQ(jobs.transfers()[0].id, transfer_id);
  EXPECT_EQ(u.find("a4/main/transfers")->table->cell(0, 2), "100");
  EXPECT_FALSE(u.find("a4/main/resume")->enabled);
  EXPECT_FALSE(u.find("a4/main/cancel")->enabled); /* finished */
}

}  // namespace
}  // namespace stk::jobstest
