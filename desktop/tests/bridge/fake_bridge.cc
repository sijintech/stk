/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-bridge-fake: a scripted stand-in for `python -m suan.desktop_bridge --stdio` (POSIX), used by
 * the stk_bridge unit tests to produce exact framing, ordering and failure cases.
 *
 * Methods: hello, echo {..} -> {params}, slow {ms} -> {slept}, hold {tag} (answered in reverse
 * order once `release` arrives), split {text} (the response written a few bytes at a time),
 * oversize / badutf8 / badjson (junk lines first, then the response), interleave {n} (events
 * around the response), partial_crash (half a line, then _exit), logs.subscribe (a fake log
 * stream from `offsets`), unsubscribe, stats -> {unsubscribes}, anything else -> {method}.
 *
 * Options:
 *   --max-line N          limits.max_line_bytes in hello (default 4096)
 *   --state FILE          marker file for the *-once options (shared across restarts)
 *   --die-once-on M       _exit(1) when request M arrives the first time
 *   --exit-at-start N     exit with N before reading anything
 *   --hello-delay-once MS delay the first instance's hello answer
 *   --busy                answer every request with busy (data.state_dir), exit 3 at EOF
 *   --ignore-eof          keep running after stdin EOF (until killed)
 *   --grandchild          start `sleep 300` in the same process group
 *   --stderr-noise        write stderr lines (one with invalid UTF-8) at start
 *   --log-text T          the fake log stream's text (default: CJK lines), 7-byte chunks every
 *                         --log-interval MS (default 15)
 *   --jobs DIR            a fake Runtime and hub for the Jobs editor tests (fake_jobs.cc; its own
 *                         options: --review-policy P, --review-refuse, --forget-inspected-once,
 *                         --local-uninitialized, --submit-fail N)
 *
 * Graph methods (WP10 viewer tests):
 *   --presets-dir DIR     graph.presets lists DIR/<id>.json (suan/graph/presets)
 *   --catalog FILE        graph.catalog returns FILE (stk.catalog/1)
 *   --payload-dir DIR     graph.evaluate delivers this payload (directory form) for every step, its
 *                         buffers copied into --blob-dir DIR; view.time.step names the step
 *   --eval-delay-ms MS    graph.evaluate answers after MS (graph.cancel {eval_id} answers the
 *                         pending evaluation with `cancelled` at once)
 *   --client-params A,B   parameters of the client stage (default "view"): changing only these
 *                         re-runs the view nodes; others re-run the data nodes; a (params, step)
 *                         seen before evaluates nothing (the bridge's node cache)
 * graph.progress events (node.started / node.finished) precede each answer; `stats` also counts
 * evaluations, cancels and probes. colormaps.list returns two 256-entry ramps; probe answers a
 * fixed sample at the requested position.
 */

#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <spawn.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <filesystem>
#include <map>
#include <memory>
#include <set>
#include <sstream>

#include "stk/core/utf8.hh"
#include "stk/io/json.hh"

#include "fake_jobs.hh"

extern char **environ;

using stk::io::Json;

namespace {

std::mutex g_out;
int g_max_line = 4096;
std::string g_state;
std::string g_die_once_on;
int g_hello_delay_once = 0;
bool g_busy = false;
bool g_ignore_eof = false;
std::string g_log_text;
int g_log_interval = 15;
std::string g_jobs_dir;
std::atomic<int> g_unsubscribes{0};
std::atomic<bool> g_stop{false};

void write_raw(const std::string &bytes)
{
  std::lock_guard lock(g_out);
  size_t done = 0;
  while (done < bytes.size()) {
    const ssize_t n = write(1, bytes.data() + done, bytes.size() - done);
    if (n <= 0) {
      return;
    }
    done += size_t(n);
  }
}

void send(const Json &message)
{
  write_raw(message.dump(-1, ' ', false, nlohmann::json::error_handler_t::strict) + "\n");
}

void respond(const Json &id, const Json &result)
{
  send(Json{{"id", id}, {"result", result}});
}

void respond_error(const Json &id, const std::string &code, const std::string &message, const Json &data = nullptr)
{
  Json error = {{"code", code}, {"message", message}, {"retryable", code == "busy" || code == "unavailable"}};
  if (!data.is_null()) {
    error["data"] = data;
  }
  send(Json{{"id", id}, {"error", error}});
}

/** Markers in the shared state file: "<key>\n" lines. */
bool once(const std::string &key)
{
  if (g_state.empty()) {
    return true;
  }
  std::ifstream in(g_state);
  std::string line;
  while (std::getline(in, line)) {
    if (line == key) {
      return false;
    }
  }
  std::ofstream out(g_state, std::ios::app);
  out << key << "\n";
  return true;
}

std::string default_log_text()
{
  std::string text;
  for (int i = 0; i < 40; i++) {
    text += "第" + std::to_string(i) + "步 能量 −1.5e-3 🧲\n";
  }
  return text + "结束";
}

/** A fake logs.subscribe stream: chunks of ~7 bytes on character boundaries from `offset`. */
void run_logs(const std::string sub, const std::string stream, int64_t offset)
{
  const std::string &text = g_log_text;
  while (!g_stop.load() && offset < int64_t(text.size())) {
    size_t end = std::min(text.size(), size_t(offset) + 7);
    while (end < text.size() && (uint8_t(text[end]) & 0xC0) == 0x80) {
      end++; /* never split a character: offsets stay on boundaries */
    }
    send(Json{{"event", "logs.chunk"},
              {"data",
               {{"sub", sub},
                {"stream", stream},
                {"text", text.substr(size_t(offset), end - size_t(offset))},
                {"offset", offset},
                {"next_offset", int64_t(end)}}}});
    offset = int64_t(end);
    std::this_thread::sleep_for(std::chrono::milliseconds(g_log_interval));
  }
  if (!g_stop.load()) {
    send(Json{{"event", "logs.end"}, {"data", {{"sub", sub}, {"offsets", {{stream, offset}}}}}});
  }
}

std::string hex32()
{
  static std::atomic<uint64_t> counter{1};
  char buffer[40];
  snprintf(buffer, sizeof(buffer), "%016llx%016llx", (unsigned long long)getpid(),
           (unsigned long long)counter.fetch_add(1));
  return buffer;
}

void spawn_grandchild()
{
  pid_t pid;
  char sleep_path[] = "/bin/sleep";
  char arg[] = "300";
  char *argv[] = {sleep_path, arg, nullptr};
  posix_spawn(&pid, sleep_path, nullptr, nullptr, argv, environ); /* same process group */
  std::cerr << "grandchild " << pid << std::endl;
}

/* ---- Graph methods (WP10) ---- */

std::string g_presets_dir, g_catalog, g_payload_dir, g_blob_dir;
int g_eval_delay_ms = 0;
std::set<std::string> g_client_params = {"view"};
std::atomic<int> g_evaluations{0}, g_cancels{0}, g_probes{0};
std::mutex g_graph;
/* eval_id -> cancelled flag of evaluations waiting for their delay. */
std::map<std::string, std::shared_ptr<std::atomic<bool>>> g_pending;
/* Per preset: the last parameters without the step, and the (parameters, step) already evaluated. */
std::map<std::string, Json> g_last_params;
std::set<std::string> g_seen;

const std::vector<std::string> kDataNodes = {"run", "polar", "domains", "surfaces", "surface_layer", "box", "legend", "axes"};
const std::vector<std::string> kClientNodes = {"camera", "scene"};
const std::vector<std::string> kStepNodes = {"polar", "domains", "surfaces", "surface_layer", "legend", "scene"};
const std::vector<int> kSteps = {0, 1, 2};

Json read_file_json(const std::string &path)
{
  std::ifstream in(path, std::ios::binary);
  std::stringstream ss;
  ss << in.rdbuf();
  return stk::io::parse_json(ss.str());
}

std::string base64(const std::vector<uint8_t> &data)
{
  static const char *t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  size_t i = 0;
  for (; i + 2 < data.size(); i += 3) {
    const uint32_t v = (uint32_t(data[i]) << 16) | (uint32_t(data[i + 1]) << 8) | data[i + 2];
    out += t[(v >> 18) & 63];
    out += t[(v >> 12) & 63];
    out += t[(v >> 6) & 63];
    out += t[v & 63];
  }
  if (i + 1 == data.size()) {
    const uint32_t v = uint32_t(data[i]) << 16;
    out += t[(v >> 18) & 63];
    out += t[(v >> 12) & 63];
    out += "==";
  }
  else if (i + 2 == data.size()) {
    const uint32_t v = (uint32_t(data[i]) << 16) | (uint32_t(data[i + 1]) << 8);
    out += t[(v >> 18) & 63];
    out += t[(v >> 12) & 63];
    out += t[(v >> 6) & 63];
    out += '=';
  }
  return out;
}

Json graph_presets()
{
  Json list = Json::array();
  std::vector<std::filesystem::path> files;
  std::error_code ec;
  for (std::filesystem::directory_iterator it(g_presets_dir, ec), end; !ec && it != end; it.increment(ec)) {
    if (it->path().extension() == ".json") {
      files.push_back(it->path());
    }
  }
  std::sort(files.begin(), files.end());
  for (const auto &f : files) {
    const Json doc = read_file_json(f.string());
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

Json colormaps_list()
{
  Json maps = Json::array();
  for (const char *name : {"grey", "reds"}) {
    const bool grey = std::strcmp(name, "grey") == 0;
    std::vector<uint8_t> lut(1024);
    for (int i = 0; i < 256; i++) {
      lut[size_t(i) * 4] = uint8_t(i);
      lut[size_t(i) * 4 + 1] = grey ? uint8_t(i) : 0;
      lut[size_t(i) * 4 + 2] = grey ? uint8_t(i) : 0;
      lut[size_t(i) * 4 + 3] = 255;
    }
    maps.push_back({{"name", name}, {"lut_rgba8", base64(lut)}});
  }
  return Json{{"colormaps", maps},
              {"aliases", Json::object()},
              {"categorical_palettes", Json::array()},
              {"reserved_colors", Json::object()},
              {"nan_color", Json::array({0.5, 0.5, 0.5, 1.0})}};
}

/** The payload of one step: the fixture with view.time.step set, its buffers in the blob dir. */
Json step_manifest(const int step)
{
  Json manifest = read_file_json(g_payload_dir + "/manifest.json");
  for (Json &b : manifest["buffers"]) {
    const std::string sha = b.value("sha256", "");
    const std::filesystem::path dst = std::filesystem::path(g_blob_dir) / sha.substr(0, 2) / sha;
    std::error_code ec;
    if (!std::filesystem::exists(dst, ec)) {
      std::filesystem::create_directories(dst.parent_path(), ec);
      std::filesystem::copy_file(std::filesystem::path(g_payload_dir) / (sha + ".bin"), dst, ec);
    }
    b["uri"] = "sha256:" + sha;
  }
  if (manifest.contains("view") && manifest["view"].is_object()) {
    manifest["view"]["time"] = Json{{"step", step}};
  }
  return manifest;
}

int resolve_step(const Json &value)
{
  if (value.is_number()) {
    const int v = int(value.get<double>());
    int best = kSteps.front();
    for (const int s : kSteps) {
      if (s <= v) {
        best = s;
      }
    }
    return best;
  }
  if (value.is_string() && value.get<std::string>() == "first") {
    return kSteps.front();
  }
  return kSteps.back();
}

/** The evaluation result of a request (evaluated nodes as the bridge's node cache gives them). */
Json evaluate_request(const Json &params)
{
  const Json request = params.value("request", Json::object());
  const std::string preset = request.value("preset", "");
  const Json parameters = request.value("parameters", Json::object());
  const int step = resolve_step(parameters.value("step", Json("latest")));
  Json rest = parameters;
  rest.erase("step");
  std::vector<std::string> evaluated;
  {
    std::lock_guard lock(g_graph);
    const std::string seen_key = preset + "|" + rest.dump() + "|" + std::to_string(step);
    const auto last = g_last_params.find(preset);
    if (last == g_last_params.end()) {
      evaluated = kDataNodes;
      evaluated.insert(evaluated.end(), kClientNodes.begin(), kClientNodes.end());
    }
    else if (g_seen.count(seen_key)) {
      evaluated = {};
    }
    else {
      bool data_changed = false, client_changed = false;
      std::set<std::string> names;
      for (auto it = rest.begin(); it != rest.end(); ++it) {
        names.insert(it.key());
      }
      for (auto it = last->second.begin(); it != last->second.end(); ++it) {
        names.insert(it.key());
      }
      for (const std::string &n : names) {
        if (rest.value(n, Json()) != last->second.value(n, Json())) {
          (g_client_params.count(n) ? client_changed : data_changed) = true;
        }
      }
      if (data_changed) {
        evaluated = kDataNodes;
        evaluated.insert(evaluated.end(), kClientNodes.begin(), kClientNodes.end());
      }
      else if (client_changed) {
        evaluated = kClientNodes;
      }
      else {
        evaluated = kStepNodes;
      }
    }
    g_last_params[preset] = rest;
    g_seen.insert(seen_key);
  }
  Json outputs = Json::object();
  const Json names = request.value("outputs", Json::array({"view"}));
  const std::string out_name = names.is_array() && !names.empty() ? names[0].get<std::string>() : "view";
  outputs[out_name] = Json{{"type", "payload"}, {"manifest", step_manifest(step)}};
  Json choices = Json::array();
  for (const int s : kSteps) {
    choices.push_back(s);
  }
  Json ev = Json::array();
  for (const std::string &n : evaluated) {
    ev.push_back(n);
  }
  const int nodes = int(kDataNodes.size() + kClientNodes.size());
  return Json{{"result",
               {{"schema", "stk.graph-result/1"},
                {"graph_sha256", std::string(64, '0')},
                {"graph_hash", "sha256:" + std::string(64, '0')},
                {"profile", request.value("profile", "desktop")},
                {"outputs", outputs},
                {"parameters", {{"step", {{"value", step}, {"choices", choices}}}}},
                {"keys", Json::object()},
                {"evaluated", ev},
                {"timings", Json::object()},
                {"cache", {{"hits", nodes - int(evaluated.size())}, {"misses", int(evaluated.size())}}},
                {"warnings", Json::array()}}},
              {"blob_dir", g_blob_dir}};
}

void progress_events(const std::string &eval_id, const Json &result)
{
  for (const Json &n : result["result"]["evaluated"]) {
    send(Json{{"event", "graph.progress"},
              {"data", {{"eval_id", eval_id}, {"event", {{"type", "node.started"}, {"node", n}}}}}});
    send(Json{{"event", "graph.progress"},
              {"data", {{"eval_id", eval_id}, {"event", {{"type", "node.finished"}, {"node", n}}}}}});
  }
}

}  // namespace

int main(int argc, char **argv)
{
  bool grandchild = false, stderr_noise = false;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    const auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
    if (a == "--max-line") {
      g_max_line = std::atoi(next().c_str());
    }
    else if (a == "--state") {
      g_state = next();
    }
    else if (a == "--die-once-on") {
      g_die_once_on = next();
    }
    else if (a == "--exit-at-start") {
      return std::atoi(next().c_str());
    }
    else if (a == "--hello-delay-once") {
      g_hello_delay_once = std::atoi(next().c_str());
    }
    else if (a == "--busy") {
      g_busy = true;
    }
    else if (a == "--ignore-eof") {
      g_ignore_eof = true;
    }
    else if (a == "--grandchild") {
      grandchild = true;
    }
    else if (a == "--stderr-noise") {
      stderr_noise = true;
    }
    else if (a == "--log-text") {
      g_log_text = next();
    }
    else if (a == "--log-interval") {
      g_log_interval = std::atoi(next().c_str());
    }
    else if (a == "--presets-dir") {
      g_presets_dir = next();
    }
    else if (a == "--catalog") {
      g_catalog = next();
    }
    else if (a == "--payload-dir") {
      g_payload_dir = next();
    }
    else if (a == "--blob-dir") {
      g_blob_dir = next();
    }
    else if (a == "--eval-delay-ms") {
      g_eval_delay_ms = std::atoi(next().c_str());
    }
    else if (a == "--client-params") {
      g_client_params.clear();
      std::stringstream ss(next());
      std::string item;
      while (std::getline(ss, item, ',')) {
        g_client_params.insert(item);
      }
    }
    else if (a == "--jobs") {
      g_jobs_dir = next();
    }
  }
  if (g_log_text.empty()) {
    g_log_text = default_log_text();
  }
  signal(SIGPIPE, SIG_IGN);
  if (grandchild) {
    spawn_grandchild();
  }
  if (stderr_noise) {
    std::cerr << "fake bridge: 启动 ok\n";
    std::cerr << "bad bytes: \xff\xfe end\n";
    std::cerr << "no newline at the end" << std::flush;
  }

  if (!g_jobs_dir.empty()) {
    fake_jobs::init(g_jobs_dir, std::vector<std::string>(argv + 1, argv + argc), [](const Json &m) { send(m); });
  }
  std::vector<std::thread> threads;
  std::deque<std::pair<Json, Json>> held;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) {
      continue;
    }
    Json request;
    try {
      request = stk::io::parse_json(line);
    }
    catch (const std::exception &) {
      respond_error(nullptr, "parse_error", "not JSON");
      continue;
    }
    const Json id = request.value("id", Json());
    const std::string method = request.value("method", std::string());
    const Json params = request.contains("params") ? request["params"] : Json::object();
    if (g_busy) {
      respond_error(id, "busy", "Another STK desktop bridge is using the state directory /fake/state",
                    Json{{"state_dir", "/fake/state"}});
      continue;
    }
    if (!g_die_once_on.empty() && method == g_die_once_on && once("die:" + method)) {
      _exit(1);
    }
    if (!g_jobs_dir.empty() && fake_jobs::handle(id, method, params)) {
      continue;
    }
    if (method == "hello") {
      if (g_hello_delay_once > 0 && once("hello-delay")) {
        std::this_thread::sleep_for(std::chrono::milliseconds(g_hello_delay_once));
      }
      respond(id, Json{{"protocol", 1},
                       {"server",
                        {{"name", "stk-bridge-fake"},
                         {"version", "0.0.1"},
                         {"python", "none"},
                         {"platform", "test"},
                         {"pid", int64_t(getpid())}}},
                       {"methods", Json::array({"hello", "echo", "logs.subscribe", "unsubscribe"})},
                       {"events", Json::array({"logs.chunk", "logs.end"})},
                       {"limits",
                        {{"max_line_bytes", g_max_line},
                         {"max_inflight", 64},
                         {"watch_interval_s", 2.0},
                         {"log_chunk_bytes", 262144},
                         {"transfer_chunk_bytes", 1048576}}},
                       {"paths",
                        {{"state_dir", "/fake/state"},
                         {"cache_dir", "/fake/cache"},
                         {"blob_dir", "/fake/cache/blobs"},
                         {"download_dir", "/fake/cache/downloads"}}},
                       {"resumed_transfers", Json::array()}});
    }
    else if (method == "echo") {
      respond(id, Json{{"params", params}});
    }
    else if (method == "slow") {
      const int ms = params.value("ms", 100);
      threads.emplace_back([id, ms] {
        std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        respond(id, Json{{"slept", ms}});
      });
    }
    else if (method == "hold") {
      held.emplace_back(id, params);
    }
    else if (method == "release") {
      while (!held.empty()) {
        respond(held.back().first, Json{{"tag", held.back().second.value("tag", Json())}});
        held.pop_back();
      }
      respond(id, Json{{"released", true}});
    }
    else if (method == "split") {
      const std::string text = Json{{"id", id}, {"result", {{"text", params.value("text", "")}}}}.dump(
                                   -1, ' ', false, nlohmann::json::error_handler_t::strict) +
                               "\n";
      std::lock_guard lock(g_out);
      for (size_t i = 0; i < text.size(); i += 3) {
        const std::string part = text.substr(i, 3);
        if (write(1, part.data(), part.size()) < 0) {
          break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
      }
    }
    else if (method == "oversize") {
      write_raw("{\"event\":\"x\",\"data\":{\"pad\":\"" + std::string(size_t(g_max_line) * 2, 'x') + "\"}}\n");
      respond(id, Json{{"after", "oversize"}});
    }
    else if (method == "badutf8") {
      write_raw("{\"event\":\"x\",\"data\":{\"t\":\"\xff\xfe\"}}\n");
      respond(id, Json{{"after", "badutf8"}});
    }
    else if (method == "badjson") {
      write_raw("not json at all\n");
      write_raw("{\"id\":" + id.dump() + ",\"result\":{},\"result\":{}}\n"); /* duplicate key */
      write_raw("{\"event\":\"x\",\"data\":{\"v\":NaN}}\n");
      write_raw("[1,2,3]\n");
      write_raw("{\"id\":" + id.dump() + ",\"result\":{\"a\":1},\"error\":{}}\n"); /* both */
      respond(id, Json{{"after", "badjson"}});
    }
    else if (method == "interleave") {
      const int n = params.value("n", 3);
      for (int i = 0; i < n; i++) {
        send(Json{{"event", "test.tick"}, {"data", {{"i", i}}}});
      }
      respond(id, Json{{"n", n}});
      for (int i = n; i < 2 * n; i++) {
        send(Json{{"event", "test.tick"}, {"data", {{"i", i}}}});
      }
    }
    else if (method == "partial_crash") {
      write_raw("{\"id\":" + id.dump() + ",\"result\":{\"cut");
      _exit(1);
    }
    else if (method == "logs.subscribe") {
      const std::string sub = hex32();
      const std::string stream = "stdout";
      int64_t offset = 0;
      if (params.contains("offsets") && params["offsets"].contains(stream)) {
        offset = params["offsets"][stream].get<int64_t>();
      }
      respond(id, Json{{"sub", sub}});
      threads.emplace_back([sub, stream, offset] { run_logs(sub, stream, offset); });
    }
    else if (method == "events.subscribe") {
      /* 30 monitoring events of 10 bytes each: batches of one, from `offset`. */
      const std::string sub = hex32();
      const int64_t start = params.value("offset", int64_t(0));
      respond(id, Json{{"sub", sub}});
      threads.emplace_back([sub, start] {
        int64_t offset = start;
        while (!g_stop.load() && offset < 300) {
          send(Json{{"event", "events.batch"},
                    {"data",
                     {{"sub", sub},
                      {"events", Json::array({{{"i", offset / 10}}})},
                      {"invalid", Json::array()},
                      {"offset", offset},
                      {"next_offset", offset + 10}}}});
          offset += 10;
          std::this_thread::sleep_for(std::chrono::milliseconds(g_log_interval));
        }
        if (!g_stop.load()) {
          send(Json{{"event", "events.end"}, {"data", {{"sub", sub}, {"next_offset", offset}}}});
        }
      });
    }
    else if (method == "unsubscribe") {
      g_unsubscribes++;
      respond(id, Json{{"ok", true}});
    }
    else if (method == "stats") {
      respond(id, Json{{"unsubscribes", g_unsubscribes.load()},
                       {"evaluations", g_evaluations.load()},
                       {"cancels", g_cancels.load()},
                       {"probes", g_probes.load()}});
    }
    else if (method == "graph.presets" && !g_presets_dir.empty()) {
      respond(id, graph_presets());
    }
    else if (method == "graph.catalog" && !g_catalog.empty()) {
      respond(id, Json{{"catalog", read_file_json(g_catalog)}});
    }
    else if (method == "colormaps.list") {
      respond(id, colormaps_list());
    }
    else if (method == "graph.evaluate" && !g_payload_dir.empty()) {
      g_evaluations++;
      const std::string eval_id = params.value("eval_id", "");
      Json result;
      try {
        result = evaluate_request(params);
      }
      catch (const std::exception &e) {
        respond_error(id, "internal_error", e.what());
        continue;
      }
      if (g_eval_delay_ms <= 0) {
        progress_events(eval_id, result);
        respond(id, result);
      }
      else {
        auto cancelled = std::make_shared<std::atomic<bool>>(false);
        {
          std::lock_guard lock(g_graph);
          g_pending[eval_id] = cancelled;
        }
        threads.emplace_back([id, eval_id, result, cancelled] {
          const auto until = std::chrono::steady_clock::now() + std::chrono::milliseconds(g_eval_delay_ms);
          while (!cancelled->load() && !g_stop.load() && std::chrono::steady_clock::now() < until) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
          }
          {
            std::lock_guard lock(g_graph);
            g_pending.erase(eval_id);
          }
          if (cancelled->load()) {
            respond_error(id, "cancelled", "Evaluation " + eval_id + " was cancelled");
            return;
          }
          progress_events(eval_id, result);
          respond(id, result);
        });
      }
    }
    else if (method == "graph.cancel") {
      const std::string eval_id = params.value("eval_id", "");
      bool found = false;
      {
        std::lock_guard lock(g_graph);
        if (auto it = g_pending.find(eval_id); it != g_pending.end()) {
          it->second->store(true);
          found = true;
        }
      }
      if (found) {
        g_cancels++;
      }
      respond(id, Json{{"cancelled", found}});
    }
    else if (method == "probe") {
      g_probes++;
      const Json pick = params.value("pick", Json::object());
      const Json position = params.value("position", Json::array({0.0, 0.0, 0.0}));
      respond(id, Json{{"target", {{"binding", "run"}, {"path", "Polar.00000002.dat"}, {"node", pick.value("node", "")}}},
                       {"sample",
                        {{"position", position},
                         {"values", Json::array({0.25, -0.5, 0.75})},
                         {"units", "unspecified"},
                         {"interpolation", "trilinear"},
                         {"source", "original_point_data"}}}});
    }
    else {
      respond(id, Json{{"method", method}});
    }
  }
  /* EOF */
  if (g_ignore_eof) {
    while (true) {
      std::this_thread::sleep_for(std::chrono::seconds(1));
    }
  }
  g_stop = true;
  if (!g_jobs_dir.empty()) {
    fake_jobs::shutdown();
  }
  for (std::thread &t : threads) {
    t.join();
  }
  return g_busy ? 3 : 0;
}
