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
 */

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

#include "stk/core/utf8.hh"
#include "stk/io/json.hh"

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
      respond(id, Json{{"unsubscribes", g_unsubscribes.load()}});
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
  for (std::thread &t : threads) {
    t.join();
  }
  return g_busy ? 3 : 0;
}
