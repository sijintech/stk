/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "jobs_support.hh"

#include <chrono>
#include <fstream>
#include <thread>

#include <gtest/gtest.h>

#include "stk/io/json.hh"
#include "stk/io/png.hh"

namespace stk::jobstest {

using io::Json;

std::string desktop_dir()
{
  return STK_DESKTOP_DIR;
}

void load_catalogs(app::AppStore &store, const std::string &lang)
{
  std::string err;
  EXPECT_GE(store.catalog().load_dir(desktop_dir() + "/app/i18n", &err), 2) << err;
  store.set_language(lang == "zh" ? "zh_CN" : lang);
}

FakeJobs::FakeJobs(const std::vector<std::string> &extra, const std::string &lang)
{
  load_catalogs(store, lang);
  std::vector<std::string> args{"--jobs", jobs_dir()};
  args.insert(args.end(), extra.begin(), extra.end());
  bridge::ClientOptions o = bridge::test::fake_options(args, loop.executor());
  client = bridge::Client::create(std::move(o));
  store.set_bridge(client.get());
  jobs().schedule = [this](double, std::function<void()> fn) { loop.executor()(std::move(fn)); };
  jobs().open_external = [this](const std::string &path, std::string *) {
    opened.push_back(path);
    return true;
  };
  jobs().attach(client.get());
  std::string err;
  EXPECT_TRUE(client->start(&err)) << err;
}

FakeJobs::~FakeJobs()
{
  close();
}

void FakeJobs::close()
{
  if (!client) {
    return;
  }
  jobs().attach(nullptr);
  store.set_bridge(nullptr);
  client->close();
  loop.run_ready();
  client.reset();
}

void FakeJobs::settle(const double seconds)
{
  const auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(int64_t(seconds * 1000));
  loop.pump_until([&] { return std::chrono::steady_clock::now() >= end; }, seconds + 5.0);
}

std::vector<std::string> FakeJobs::methods() const
{
  std::vector<std::string> out;
  std::ifstream in(jobs_dir() + "/methods.log");
  std::string line;
  while (std::getline(in, line)) {
    out.push_back(line);
  }
  return out;
}

bool FakeJobs::connect(const std::string &connection)
{
  app::JobsState &j = jobs();
  if (!pump([&] { return j.ready() && !j.connections().empty(); })) {
    return false;
  }
  j.select_connection(connection);
  if (pump([&] { return !j.workspace().empty() && j.snapshot_time() > 0.0; })) {
    return true;
  }
  std::string methods;
  for (const std::string &m : this->methods()) {
    methods += m + " ";
  }
  ADD_FAILURE() << "connect(" << connection << "): status \"" << j.status().text << "\", node \"" << j.node()
                << "\", workspace \"" << j.workspace() << "\", methods: " << methods;
  return false;
}

void write_demo_png(const std::string &path)
{
  io::Image img(64, 48, 4);
  for (uint32_t y = 0; y < img.height; y++) {
    for (uint32_t x = 0; x < img.width; x++) {
      uint8_t *p = img.pixel(x, y);
      p[0] = uint8_t(x * 4);
      p[1] = uint8_t(y * 5);
      p[2] = uint8_t(255 - x * 3);
      p[3] = 255;
    }
  }
  io::write_png(path, img);
}

void populate_demo(app::JobsState &jobs, const std::string &png)
{
  jobs.apply_connections({bridge::ConnectionInfo::from_json(Json{{"id", "local"}, {"kind", "local"}, {"name", "local"},
                                                                  {"url", "http://127.0.0.1:8765"}}),
                          bridge::ConnectionInfo::from_json(Json{{"id", "runtime:lab"}, {"kind", "runtime"},
                                                                  {"name", "lab"}, {"url", "http://127.0.0.1:9876"}})});
  jobs.select_connection("runtime:lab");
  bridge::ConnectionCheck check;
  check.id = "runtime:lab";
  check.ok = true;
  check.health = Json{{"api_version", 1}, {"supervisor_running", true}};
  jobs.apply_check(check);
  jobs.apply_workspaces(Json::array({{{"id", "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0"}, {"name", "铁电畴 / domains"},
                                      {"created_at", "2026-09-25T08:00:00+00:00"}}}));
  auto task = [](const char *id, const char *name, const char *state, const char *backend, const char *reason,
                 const char *created, bool cancel = false) {
    return Json{{"id", id}, {"state", state}, {"reason", reason}, {"created_at", created},
                {"updated_at", created}, {"cancel_requested", cancel}, {"exit_code", nullptr},
                {"spec", {{"name", name}, {"backend", backend}, {"workspace_id", "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0"},
                          {"argv", Json::array({"{python}", "-m", "suan.mupro", "run", "--case", "input.toml"})}}}};
  };
  jobs.apply_snapshot(Json::array({task("11111111111111111111111111111111", "铁电畴 300K", "running", "local", "",
                                        "2026-09-25T09:12:03+00:00"),
                                   task("22222222222222222222222222222222", "domains-slurm", "queued", "slurm", "",
                                        "2026-09-25T09:10:44+00:00"),
                                   task("33333333333333333333333333333333", "弛豫 relax", "succeeded", "local", "",
                                        "2026-09-25T08:55:10+00:00"),
                                   task("44444444444444444444444444444444", "", "failed", "pbs",
                                        "Program exited with code 2", "2026-09-25T08:40:00+00:00"),
                                   task("55555555555555555555555555555555", "long run", "running", "slurm", "",
                                        "2026-09-25T08:30:00+00:00", true)}),
                      1790000000.0);
  jobs.select_task("33333333333333333333333333333333");
  jobs.log_all().append("开始计算 333333\n第1步 能量 −1.5e-3\n[stderr] 警告：网格较粗\n第2步 能量 −1.6e-3\n完成\n");
  jobs.apply_artifacts({bridge::FileEntry::from_json(Json{{"path", "result.png"}, {"size", 5120},
                                                          {"sha256", std::string(64, 'a')}, {"media_type", "image/png"}}),
                        bridge::FileEntry::from_json(Json{{"path", "out/summary.txt"}, {"size", 24},
                                                          {"sha256", std::string(64, 'b')}, {"media_type", "text/plain"}})});
  jobs.apply_transfer(bridge::Transfer::from_json(Json{{"id", "t1"}, {"kind", "upload"}, {"state", "running"},
                                                       {"connection", "runtime:lab"},
                                                       {"workspace_id", "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0"},
                                                       {"local", "/home/me/cases/input.toml"}, {"remote", "input.toml"},
                                                       {"bytes_done", 600}, {"bytes_total", 1000}, {"files_done", 0},
                                                       {"files_total", 1}, {"created_at", "2026-09-25T09:13:00+00:00"},
                                                       {"updated_at", "2026-09-25T09:13:01+00:00"}}));
  jobs.form().name = "铁电畴 300K";
  jobs.form().arguments = "-m suan.mupro run --case input.toml";
  if (!png.empty()) {
    jobs.show_preview(png);
  }
}

}  // namespace stk::jobstest
