/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Jobs editor's state against the real Python bridge (--strict, client-side schema checks)
 * and a loopback STK Runtime (jobs_fixture.py, 127.0.0.1 only): add the Runtime profile, create a
 * workspace, upload a folder, submit a small task, see it in the watched list, stream its logs,
 * download its PNG artifact with the sha256 verified and decode the preview, then submit a slower
 * task, close the app (JobsState detached, bridge closed) and check that the task still ran to
 * completion. Skipped with the reason when Python, the bridge or the Runtime cannot run here.
 */

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>

#include <gtest/gtest.h>

#include "stk/bridge/process.hh"
#include "stk/core/sha256.hh"
#include "stk/io/json.hh"
#include "stk/io/png.hh"

#include "jobs_support.hh"

namespace stk::jobstest {
namespace {

using bridge::ChildProcess;
using bridge::SpawnOptions;
using io::Json;

std::string repo_root()
{
  return STK_REPO_ROOT;
}

std::string fixture()
{
  return desktop_dir() + "/tests/app/jobs_fixture.py";
}

/** The interpreter, or "" with `why`. */
std::string python(std::string &why)
{
  std::string py;
  if (const char *env = getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) {
    py = env;
  }
  else if (std::string(STK_BRIDGE_TEST_PYTHON_DEFAULT).size() > 0) {
    py = STK_BRIDGE_TEST_PYTHON_DEFAULT;
  }
  else if (auto found = bridge::find_executable("python3")) {
    py = *found;
  }
  if (py.empty() || !bridge::find_executable(py)) {
    why = "no Python interpreter (set STK_BRIDGE_TEST_PYTHON)";
    return "";
  }
  SpawnOptions o;
  o.argv = {py, fixture(), "check"};
  o.env["PYTHONPATH"] = repo_root();
  std::string err;
  auto child = ChildProcess::spawn(o, err);
  if (!child) {
    why = err;
    return "";
  }
  child->close_stdin();
  std::string out;
  char buf[512];
  std::ptrdiff_t n;
  while ((n = child->read(ChildProcess::Stream::Stdout, buf, sizeof(buf))) > 0) {
    out.append(buf, size_t(n));
  }
  const auto st = child->wait(120);
  if (!st || !st->success()) {
    why = py + ": " + out;
    return "";
  }
  return py;
}

/** jobs_fixture.py runtime: a Runtime on 127.0.0.1 answering line commands. */
struct Runtime {
  std::unique_ptr<ChildProcess> process;
  std::thread drain;
  std::shared_ptr<std::string> err = std::make_shared<std::string>();
  Json info;

  std::string start(const std::string &py, const std::string &dir)
  {
    SpawnOptions o;
    o.argv = {py, fixture(), "runtime", dir};
    o.env["PYTHONPATH"] = repo_root();
    std::string e;
    process = ChildProcess::spawn(o, e);
    if (!process) {
      return e;
    }
    ChildProcess *p = process.get();
    auto text = err;
    drain = std::thread([p, text] {
      char buf[2048];
      std::ptrdiff_t n;
      while ((n = p->read(ChildProcess::Stream::Stderr, buf, sizeof(buf))) > 0) {
        text->append(buf, size_t(n));
      }
    });
    const std::string line = read_line();
    if (line.empty()) {
      stop();
      return "the Runtime fixture did not start: " + err->substr(err->size() > 1500 ? err->size() - 1500 : 0);
    }
    info = io::parse_json(line);
    return {};
  }
  std::string read_line()
  {
    std::string line;
    char c;
    while (process->read(ChildProcess::Stream::Stdout, &c, 1) == 1 && c != '\n') {
      line += c;
    }
    return line;
  }
  Json command(const std::string &cmd)
  {
    process->write_stdin(cmd + "\n");
    const std::string line = read_line();
    return line.empty() ? Json() : io::parse_json(line);
  }
  void stop()
  {
    if (!process) {
      return;
    }
    process->close_stdin();
    if (!process->wait(40)) {
      process->kill();
      process->wait(-1);
    }
    process->abort_reads();
    if (drain.joinable()) {
      drain.join();
    }
    process.reset();
  }
  ~Runtime()
  {
    stop();
  }
};

TEST(JobsPython, WorkspaceUploadSubmitLogsVerifiedDownloadAndJobsSurviveClosing)
{
  std::string why;
  const std::string py = python(why);
  if (py.empty()) {
    GTEST_SKIP() << why;
  }
  bridge::test::TempDir dir("jobs-py");
  Runtime rt;
  if (const std::string e = rt.start(py, dir.str() + "/runtime"); !e.empty()) {
    GTEST_SKIP() << e;
  }
  bridge::test::ManualLoop loop;
  app::AppStore store;
  load_catalogs(store, "zh");
  bridge::ClientOptions o;
  o.python.configured = py;
  o.state_dir = dir.str() + "/state";
  o.cache_dir = dir.str() + "/cache";
  o.strict = true;
  o.validate = true;
  o.executor = loop.executor();
  o.env["PYTHONPATH"] = repo_root();
  o.env["STK_PROFILES_FILE"] = dir.str() + "/profiles/connections.json";
  o.env["STK_STATE_DIR"] = dir.str() + "/no-local-runtime";
  o.env["STK_DESKTOP_BRIDGE_DIR"] = std::nullopt;
  o.env["STK_RUNTIME_URL"] = std::nullopt;
  o.env["STK_RUNTIME_TOKEN"] = std::nullopt;
  o.env["MPLCONFIGDIR"] = dir.str() + "/mpl";
  std::unique_ptr<bridge::Client> client = bridge::Client::create(std::move(o));
  app::JobsState &j = store.jobs();
  int textures = 0;
  j.create_texture = [&](const io::Image &img) -> uint64_t {
    return img.width == 32 && img.height == 16 ? uint64_t(++textures) : 0;
  };
  j.free_texture = [](uint64_t) {};
  j.open_external = [](const std::string &, std::string *) { return true; };
  j.schedule = [&](double, std::function<void()> fn) { loop.executor()(std::move(fn)); };
  store.set_bridge(client.get());
  j.attach(client.get());
  ASSERT_TRUE(client->start());
  auto pump = [&](const std::function<bool()> &until, double s = 60.0) { return loop.pump_until(until, s); };
  ASSERT_TRUE(pump([&] { return j.ready(); })) << "bridge did not start";

  /* 1. The Runtime profile (token file: the token never passes through the app). */
  bridge::AddRuntimeParams add;
  add.name = "rt";
  add.url = rt.info["url"].get<std::string>();
  add.token_file = rt.info["token_file"].get<std::string>();
  std::optional<bridge::Error> err;
  bool done = false;
  j.add_runtime(add, [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(pump([&] { return done; }));
  ASSERT_FALSE(err) << err->describe();
  /* Connected: the fixture ticks its supervisor in-process, so the Runtime may report its
   * supervisor service as not running (shown as "connected with problems", like the legacy tab). */
  ASSERT_TRUE(pump([&] {
    return j.active() && (j.active()->health == app::Health::Online || j.active()->health == app::Health::Degraded);
  })) << j.status().text;
  EXPECT_NE(store.connection().find("rt"), std::string::npos);

  /* 2. A workspace. */
  done = false;
  j.create_workspace("桌面测试", [&](const std::optional<bridge::Error> &e) {
    err = e;
    done = true;
  });
  ASSERT_TRUE(pump([&] { return done; }));
  ASSERT_FALSE(err) << err->describe();
  ASSERT_TRUE(pump([&] {
    for (const app::WorkspaceRow &w : j.workspaces()) {
      if (w.id == j.workspace() && w.name == "桌面测试") {
        return true;
      }
    }
    return false;
  }));

  /* 3. Upload a folder (verified by the bridge; its contents at the workspace root, remote "."),
   * listed as workspace inputs. */
  const std::string case_dir = dir.str() + "/case";
  {
    SpawnOptions co;
    co.argv = {py, fixture(), "case", case_dir};
    co.env["PYTHONPATH"] = repo_root();
    std::string e;
    auto c = ChildProcess::spawn(co, e);
    ASSERT_TRUE(c) << e;
    c->close_stdin();
    ASSERT_TRUE(c->wait(60)->success());
  }
  j.upload({case_dir});
  ASSERT_TRUE(pump([&] { return j.workspace_files().size() == 3; })) << j.status().text;
  {
    std::vector<std::string> paths;
    for (const bridge::FileEntry &e : j.workspace_files()) {
      paths.push_back(e.path);
    }
    std::sort(paths.begin(), paths.end());
    EXPECT_EQ(paths, (std::vector<std::string>{"input.json", "job.py", "sub/notes.txt"}));
  }
  EXPECT_EQ(j.uploads_in_flight(), 0);

  /* 4. Submit a small task; it shows up in the watched list and succeeds. */
  j.form().name = "铁电畴 测试";
  j.form().program = "{python}";
  j.form().arguments = "job.py 0";
  ASSERT_TRUE(j.submit()) << j.status().text;
  ASSERT_TRUE(pump([&] { return j.submission()->state == app::SubmitState::Done; })) << j.status().text;
  const std::string first = j.submission()->task_id;
  ASSERT_TRUE(pump([&] {
    const app::TaskRow *t = j.selected_task();
    return t && t->id == first && t->state == "succeeded";
  }, 120.0)) << j.status().text;

  /* 5. Logs streamed (stdout and stderr), complete. */
  ASSERT_TRUE(pump([&] { return j.logs_ended(); }));
  std::string all;
  for (size_t i = 0; i < j.log_all().line_count(); i++) {
    all += std::string(j.log_all().line(i)) + "\n";
  }
  EXPECT_NE(all.find("第4步 能量"), std::string::npos) << all;
  EXPECT_NE(all.find("[stderr] 警告：这是测试"), std::string::npos) << all;
  EXPECT_NE(all.find("结束"), std::string::npos) << all;

  /* 6. The PNG artifact: downloaded, sha256 verified, decoded for the preview. */
  ASSERT_TRUE(pump([&] {
    for (const app::ArtifactRow &a : j.artifacts()) {
      if (a.file.path == "result.png") {
        return true;
      }
    }
    return false;
  }));
  std::string sha;
  for (const app::ArtifactRow &a : j.artifacts()) {
    if (a.file.path == "result.png") {
      sha = a.file.sha256;
    }
  }
  j.download_artifact("result.png");
  ASSERT_TRUE(pump([&] {
    for (const app::ArtifactRow &a : j.artifacts()) {
      if (a.file.path == "result.png") {
        return a.verify == app::ArtifactRow::Verify::Ok;
      }
    }
    return false;
  })) << j.status().text;
  std::string local;
  for (const app::ArtifactRow &a : j.artifacts()) {
    if (a.file.path == "result.png") {
      local = a.local;
    }
  }
  {
    std::ifstream in(local, std::ios::binary);
    const std::string bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    EXPECT_EQ(core::Sha256::hex(bytes), sha);
  }
  EXPECT_EQ(j.preview().width, 32);
  EXPECT_EQ(j.preview().height, 16);
  EXPECT_EQ(textures, 1);
  EXPECT_TRUE(j.preview().error.empty()) << j.preview().error;

  /* 7. A slower task; close the app while it runs. */
  j.form().name = "关闭后继续";
  j.form().arguments = "job.py 4";
  ASSERT_TRUE(j.submit());
  ASSERT_TRUE(pump([&] { return j.submission()->state == app::SubmitState::Done; }));
  const std::string second = j.submission()->task_id;
  ASSERT_TRUE(pump([&] {
    const app::TaskRow *t = j.selected_task();
    return t && t->id == second && t->state == "running";
  }, 120.0));
  j.attach(nullptr);
  store.set_bridge(nullptr);
  client->close();
  loop.run_ready();
  std::string bridge_log;
  for (const bridge::LogRing::Line &l : client->bridge_log().lines_after(0)) {
    bridge_log += l.text + "\n";
  }
  client.reset();
  const Json after = rt.command("task " + second);
  EXPECT_NE(after.value("state", std::string()), "cancelled");
  EXPECT_FALSE(after.value("cancel_requested", true));
  const Json finished = rt.command("wait " + second + " 60");
  EXPECT_EQ(finished.value("state", std::string()), "succeeded") << finished.dump();
  rt.stop();
  /* No token in the bridge's output. */
  std::ifstream token_file(add.token_file);
  std::string token;
  std::getline(token_file, token);
  EXPECT_FALSE(token.empty());
  EXPECT_EQ(bridge_log.find(token), std::string::npos);
  std::string app_log;
  for (size_t i = 0; i < store.app_log().line_count(); i++) {
    app_log += std::string(store.app_log().line(i)) + "\n";
  }
  EXPECT_EQ(app_log.find(token), std::string::npos);
  /* No bridge or Runtime helper of this test is left. */
  EXPECT_TRUE(bridge::test::wait_until([&] { return bridge::test::processes_matching(dir.str()).empty(); }, 15))
      << bridge::test::processes_matching(dir.str()).size() << " stray process(es) under " << dir.str();
}

}  // namespace
}  // namespace stk::jobstest
