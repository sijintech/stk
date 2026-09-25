/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The Jobs editor's UI without a GPU (fake text measurer): layout goldens of the maximized
 * Jobs area with demo content (en / zh), drops, and the dialogs driven with synthesized events
 * against the fake bridge (Add Runtime, the path-field fallback of the file dialog, cancel). */

#include <cstdlib>
#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "../wm/support.hh"
#include "jobs_support.hh"
#include "stk/app/jobs_state.hh"
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
  f.screen.set_maximized(&f.area("a1"));
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
  app::EditorArea &bottom = f.area("a4");
  bottom.set_active_tab(2); /* Transfers */
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
  EXPECT_TRUE(drop(f.area("a1"), {"/data/run1/phi.bin"}));
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

  UiOnFake()
  {
    client = bridge::Client::create(bridge::test::fake_options({"--jobs", dir.str() + "/model"}, loop.executor()));
    f.shell->store().set_bridge(client.get());
    jobs().open_external = [](const std::string &, std::string *) { return true; };
    jobs().attach(client.get());
    client->start();
    f.screen.set_maximized(&f.area("a1"));
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
  EXPECT_EQ(jobs.workspace_files()[0].path, "输入/a.json");
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
  app::EditorArea &bottom = u.f.area("a4");
  bottom.set_active_tab(2); /* Transfers */
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
  u.click("a4/main/resume");
  ASSERT_TRUE(u.pump([&] { return jobs.transfers()[0].state == "completed"; }));
  EXPECT_EQ(u.find("a4/main/transfers")->table->cell(0, 2), "100");
  EXPECT_FALSE(u.find("a4/main/cancel")->enabled); /* finished */
}

}  // namespace
}  // namespace stk::jobstest
