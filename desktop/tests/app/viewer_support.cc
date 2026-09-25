/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "viewer_support.hh"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <thread>

#include <unistd.h> /* getpid (the tests using this file are POSIX-only) */

#include <gtest/gtest.h>

#include "stk/bridge/process.hh"
#include "stk/io/payload.hh"

namespace fs = std::filesystem;
using stk::io::Json;

namespace stk::apptest {

std::string repo_root()
{
  return STK_REPO_ROOT;
}

fs::path fixture_payload_dir()
{
  return fs::path(repo_root()) / "desktop" / "tests" / "viewer" / "fixtures" / "muferro_domains";
}

fs::path fixture_stkp()
{
  return fs::path(repo_root()) / "desktop" / "tests" / "viewer" / "fixtures" / "muferro_domains.stkp";
}

std::string fake_bridge_path()
{
  return STK_BRIDGE_FAKE;
}

bridge::Executor ManualLoop::executor()
{
  return [this](std::function<void()> fn) {
    {
      std::lock_guard lock(mutex_);
      tasks_.push_back(std::move(fn));
    }
    cv_.notify_all();
  };
}

void ManualLoop::run_ready()
{
  while (true) {
    std::function<void()> fn;
    {
      std::lock_guard lock(mutex_);
      if (tasks_.empty()) {
        return;
      }
      fn = std::move(tasks_.front());
      tasks_.pop_front();
    }
    fn();
  }
}

bool ManualLoop::pump_until(const std::function<bool()> &until, const double timeout_s, const std::function<void()> &each)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::microseconds(int64_t(timeout_s * 1e6));
  while (true) {
    run_ready();
    if (each) {
      each();
    }
    if (until()) {
      return true;
    }
    std::unique_lock lock(mutex_);
    if (std::chrono::steady_clock::now() >= deadline) {
      return false;
    }
    cv_.wait_for(lock, std::chrono::milliseconds(5), [&] { return !tasks_.empty(); });
  }
}

TempDir::TempDir(const std::string &tag)
{
  static std::atomic<int> counter{0};
  const fs::path base = fs::path(STK_APP_TEST_SCRATCH);
  std::error_code ec;
  fs::create_directories(base, ec);
  path_ = base / (tag + "-" + std::to_string(::getpid()) + "-" + std::to_string(counter++));
  fs::remove_all(path_, ec);
  fs::create_directories(path_, ec);
}

TempDir::~TempDir()
{
  std::error_code ec;
  fs::remove_all(path_, ec);
}

bool write_text(const std::string &path, const std::string &text)
{
  std::error_code ec;
  fs::create_directories(fs::path(path).parent_path(), ec);
  std::ofstream out(path, std::ios::binary);
  out << text;
  return bool(out);
}

std::string read_text(const std::string &path)
{
  std::ifstream in(path, std::ios::binary);
  std::stringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

int run_command(const std::vector<std::string> &argv, std::string *out, const double timeout_s)
{
  bridge::SpawnOptions options;
  options.argv = argv;
  options.env["PYTHONPATH"] = repo_root();
  std::string error;
  auto child = bridge::ChildProcess::spawn(options, error);
  if (!child) {
    if (out) {
      *out = error;
    }
    return -1;
  }
  child->close_stdin();
  std::string text;
  char buffer[4096];
  std::ptrdiff_t n;
  while ((n = child->read(bridge::ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
    text.append(buffer, size_t(n));
  }
  const auto status = child->wait(timeout_s);
  if (out) {
    *out = text;
  }
  return status ? status->code : -1;
}

std::string graph_python(std::string &reason)
{
  static std::string cached, cached_reason;
  static bool probed = false;
  if (!probed) {
    probed = true;
    std::string python = "python3";
#ifdef STK_APP_TEST_PYTHON
    if (std::string(STK_APP_TEST_PYTHON).size() > 0) {
      python = STK_APP_TEST_PYTHON;
    }
#endif
    if (const char *env = std::getenv("STK_BRIDGE_TEST_PYTHON"); env && *env) {
      python = env;
    }
    std::string out;
    const int rc = run_command({python, repo_root() + "/desktop/tests/bridge/bridge_fixture.py", "check", "graph"}, &out, 120);
    if (rc == 0) {
      cached = python;
    }
    else {
      cached_reason = python + " cannot evaluate graphs locally: " + out;
    }
  }
  reason = cached_reason;
  return cached;
}

bool write_fake_run(const std::string &python, const std::string &dir)
{
  std::string out;
  return run_command({python, repo_root() + "/desktop/tests/bridge/bridge_fixture.py", "write-run", dir}, &out, 300) == 0;
}

bridge::ClientOptions python_bridge_options(const std::string &python, const std::string &dir, bridge::Executor executor)
{
  bridge::ClientOptions o;
  o.python.configured = python;
  o.state_dir = dir + "/state";
  o.cache_dir = dir + "/cache";
  o.executor = std::move(executor);
  o.env["PYTHONPATH"] = repo_root();
  o.env["STK_PROFILES_FILE"] = dir + "/profiles/connections.json";
  o.env["STK_STATE_DIR"] = dir + "/no-local-runtime";
  o.env["STK_DESKTOP_BRIDGE_DIR"] = std::nullopt;
  o.env["STK_RUNTIME_URL"] = std::nullopt;
  o.env["STK_RUNTIME_TOKEN"] = std::nullopt;
  o.env["MPLCONFIGDIR"] = dir + "/mpl";
  o.env["STK_GRAPH_CACHE"] = dir + "/graph-cache";
  o.call_timeout_s = 600;
  o.hello_timeout_s = 120;
  o.shutdown_grace_s = 10;
  return o;
}

Json repo_presets()
{
  std::vector<fs::path> files;
  for (const auto &e : fs::directory_iterator(fs::path(repo_root()) / "suan" / "graph" / "presets")) {
    if (e.path().extension() == ".json") {
      files.push_back(e.path());
    }
  }
  std::sort(files.begin(), files.end());
  Json list = Json::array();
  for (const fs::path &f : files) {
    const Json doc = io::read_json_file(f);
    const Json graph = doc.value("graph", Json::object());
    Json bindings = Json::array();
    for (const Json &b : doc.value("bindings", Json::array())) {
      bindings.push_back({{"name", b.value("name", "")}, {"description", b.value("description", "")}});
    }
    list.push_back({{"id", doc.value("id", f.stem().string())},
                    {"name", doc.value("name", f.stem().string())},
                    {"description", doc.value("description", "")},
                    {"graph", graph},
                    {"bindings", bindings},
                    {"parameters", graph.value("parameters", Json::array())}});
  }
  return Json{{"presets", list}};
}

Json repo_catalog()
{
  return io::read_json_file(fs::path(repo_root()) / "docs" / "specs" / "catalog" / "stk-catalog-m1.json");
}

namespace {

void copy_payload(const fs::path &dst)
{
  fs::create_directories(dst);
  for (const auto &e : fs::directory_iterator(fixture_payload_dir())) {
    fs::copy_file(e.path(), dst / e.path().filename(), fs::copy_options::overwrite_existing);
  }
}

Json result_doc(const std::string &payload_rel, const Json &step)
{
  const Json manifest = io::read_json_file(fixture_payload_dir() / "manifest.json");
  Json doc = {{"schema", "stk.graph-result/1"},
              {"graph_sha256", std::string(64, '0')},
              {"graph_hash", "sha256:" + std::string(64, '0')},
              {"profile", "desktop"},
              {"outputs", {{"view", {{"type", "payload"}, {"manifest", manifest}}}}},
              {"parameters", Json::object()},
              {"keys", Json::object()},
              {"evaluated", Json::array()},
              {"timings", Json::object()},
              {"cache", {{"hits", 0}, {"misses", 0}}},
              {"warnings", Json::array()},
              {"files", {{"view", payload_rel}}}};
  if (!step.is_null()) {
    doc["parameters"]["step"] = {{"value", step}, {"choices", Json::array()}};
  }
  return doc;
}

}  // namespace

void write_result_dir(const fs::path &dir, const Json &step)
{
  copy_payload(dir / "view");
  write_text((dir / "result.json").string(), result_doc("view/manifest.json", step).dump(1));
}

void write_series_dir(const fs::path &dir, const std::vector<int> &steps)
{
  Json frames = Json::array();
  for (const int s : steps) {
    char suffix[32];
    std::snprintf(suffix, sizeof(suffix), ".%08d", s);
    const std::string payload = std::string("view") + suffix;
    copy_payload(dir / payload);
    const std::string result = std::string("result") + suffix + ".json";
    write_text((dir / result).string(), result_doc(payload + "/manifest.json", s).dump(1));
    frames.push_back({{"step", s}, {"outputs", {{"view", payload + "/manifest.json"}}}, {"result", result}});
  }
  write_text((dir / "series.json").string(),
             Json{{"schema", "stk.series/1"}, {"parameter", "step"}, {"frames", frames}}.dump(1));
}

FakeViewer::FakeViewer(const std::vector<std::string> &extra_args)
{
  bridge::ClientOptions o;
  o.command = {fake_bridge_path(),
               "--max-line",
               "16777216",
               "--presets-dir",
               repo_root() + "/suan/graph/presets",
               "--catalog",
               repo_root() + "/docs/specs/catalog/stk-catalog-m1.json",
               "--payload-dir",
               fixture_payload_dir().string(),
               "--blob-dir",
               (dir.path() / "blobs").string()};
  o.command.insert(o.command.end(), extra_args.begin(), extra_args.end());
  o.executor = loop.executor();
  o.call_timeout_s = 60.0;
  o.hello_timeout_s = 30.0;
  o.shutdown_grace_s = 5.0;
  client = bridge::Client::create(std::move(o));
  std::string err;
  EXPECT_TRUE(client->start(&err)) << err;
  EXPECT_TRUE(client->wait_ready(30.0));
  loop.run_ready();
  store.set_bridge(client.get());
  vs = &store.viewer();
  vs->clock = [this]() { return t; };
}

FakeViewer::~FakeViewer()
{
  vs->close();
  store.set_bridge(nullptr);
  client->close();
  loop.run_ready();
  client.reset();
}

bool FakeViewer::pump_until(const std::function<bool()> &until, const double timeout_s)
{
  return loop.pump_until(until, timeout_s, [this]() { vs->pump(); });
}

void FakeViewer::advance(const double seconds)
{
  t += seconds;
  loop.run_ready();
  vs->pump();
}

Json FakeViewer::stats()
{
  std::optional<bridge::Result<Json>> r;
  client->call("stats").then([&](bridge::Result<Json> v) { r = std::move(v); });
  loop.pump_until([&] { return r.has_value(); }, 10.0);
  return r && r->ok() ? r->value() : Json();
}

std::string FakeViewer::run_dir()
{
  const fs::path run = dir.path() / "run";
  fs::create_directories(run);
  write_text((run / "Polar.00000000.dat").string(), "1 1 1\n");
  return run.string();
}

}  // namespace stk::apptest
