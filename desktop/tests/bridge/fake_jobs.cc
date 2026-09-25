/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The `--jobs DIR` mode of stk-bridge-fake (WP9): an in-memory Runtime and control hub behind the
 * Jobs editor's methods, so the editor state machines run against the real stk_bridge client with
 * exact, fast and scriptable behaviour. The model is saved in DIR/model.json after every change,
 * so it survives a bridge restart (like the real Runtime / hub); what one bridge process knows
 * (inspected hub actions, subscriptions) does not. DIR/methods.log records every request method.
 *
 * Connections: local (initialized, stopped until connections.local_start), runtime:lab, hub:mesh
 * (node "node1" online, template "muferro-small", review policy from --review-policy, default
 * "any"); connections.add_runtime / pair_hub / remove edit the list ("runtime:down" is unreachable,
 * a Runtime named "bad" is refused as unauthorized).
 * Tasks: queued, running after 0.2 s, succeeded after 0.6 s (a name containing "slow" runs for
 * 60 s); cancel_requested ends them as cancelled at the next tick. Artifacts once finished:
 * result.png (a 64x48 RGBA gradient) and out/summary.txt. task.submit is idempotent per key (a
 * different spec under a used key is `conflict`); `--submit-fail N` answers the first N submits
 * with `unavailable` (retryable). Through the hub, a template runs at once, a custom spec becomes
 * a task.submit action in review until approved (hub.action first; --review-refuse makes the
 * hub refuse approvals with unauthorized / review_policy; --forget-inspected-once drops the first
 * approval's inspection as a bridge restart would; --local-uninitialized lists `local` as
 * not_initialized until connections.local_start {initialize: true}). Uploads of a source whose name contains
 * "interrupt" stop half-way as `interrupted` until transfer.resume. Uploads complete after two progress
 * events (through the hub: bytes done, then action "review" until the workspace.import is
 * approved); downloads write the artifact bytes to `dest` (default DIR/downloads/...).
 * Logs: stdout and stderr lines per task (CJK), then logs.end; events: a short monitoring run.
 */

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <unistd.h>

#include "stk/core/sha256.hh"
#include "stk/io/json.hh"
#include "stk/io/png.hh"

#include "fake_jobs.hh"

namespace fake_jobs {

using stk::io::Json;
namespace fs = std::filesystem;

namespace {

struct Options {
  std::string dir;
  std::string review_policy = "any";
  bool review_refuse = false;
  bool forget_inspected_once = false;
  bool local_uninitialized = false;
  int submit_fail = 0;
} g_opt;

SendFn g_send;
std::mutex g_m;
Json g_model;               /* guarded by g_m */
std::set<std::string> g_inspected;
std::map<std::string, Json> g_watches;  /* sub -> {connection, node, workspace_id, last} */
std::set<std::string> g_hub_subs;
std::atomic<bool> g_stop{false};
std::thread g_ticker;
std::vector<std::thread> g_threads;
uint64_t g_counter = 1;

double now_s()
{
  return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string iso(double t)
{
  const time_t secs = time_t(t);
  struct tm tm_utc;
  gmtime_r(&secs, &tm_utc);
  char buf[64];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d+00:00", tm_utc.tm_year + 1900, tm_utc.tm_mon + 1,
           tm_utc.tm_mday, tm_utc.tm_hour, tm_utc.tm_min, tm_utc.tm_sec);
  return buf;
}

std::string hex32(const std::string &seed)
{
  return stk::core::Sha256::hex(seed + ":" + std::to_string(g_counter++) + ":" + std::to_string(now_s())).substr(0, 32);
}

void save_locked()
{
  std::ofstream(g_opt.dir + "/model.json") << g_model.dump(1);
}

void record(const std::string &method)
{
  std::ofstream(g_opt.dir + "/methods.log", std::ios::app) << method << "\n";
}

void respond(const Json &id, const Json &result)
{
  g_send(Json{{"id", id}, {"result", result}});
}

void error(const Json &id, const std::string &code, const std::string &message, const Json &data = nullptr,
           bool retryable = false)
{
  Json e = {{"code", code}, {"message", message}, {"retryable", retryable}};
  if (!data.is_null()) {
    e["data"] = data;
  }
  g_send(Json{{"id", id}, {"error", e}});
}

void event(const std::string &name, const Json &data)
{
  g_send(Json{{"event", name}, {"data", data}});
}

std::vector<uint8_t> result_png()
{
  stk::io::Image img(64, 48, 4);
  for (uint32_t y = 0; y < img.height; y++) {
    for (uint32_t x = 0; x < img.width; x++) {
      uint8_t *p = img.pixel(x, y);
      p[0] = uint8_t(x * 4);
      p[1] = uint8_t(y * 5);
      p[2] = uint8_t(255 - x * 3);
      p[3] = 255;
    }
  }
  return stk::io::encode_png(img);
}

std::string summary_text()
{
  return "能量 −1.5e-3\nsteps 100\n";
}

Json artifacts_of(const Json &task)
{
  const std::vector<uint8_t> png = result_png();
  const std::string txt = summary_text();
  (void)task;
  return Json::array({{{"path", "result.png"}, {"size", int64_t(png.size())},
                       {"sha256", stk::core::Sha256::hex(png.data(), png.size())}, {"media_type", "image/png"}},
                      {{"path", "out/summary.txt"}, {"size", int64_t(txt.size())},
                       {"sha256", stk::core::Sha256::hex(txt)}, {"media_type", "text/plain"}}});
}

std::string artifact_bytes(const std::string &path)
{
  if (path == "result.png") {
    const std::vector<uint8_t> png = result_png();
    return std::string(png.begin(), png.end());
  }
  return summary_text();
}

void init_model()
{
  std::ifstream in(g_opt.dir + "/model.json");
  if (in) {
    std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    try {
      g_model = stk::io::parse_json(text);
      return;
    }
    catch (...) {
    }
  }
  g_model = Json::object();
  g_model["connections"] = Json::array(
      {{{"id", "local"}, {"kind", "local"}, {"name", "local"}, {"url", "http://127.0.0.1:8765"}, {"state", "initialized"}},
       {{"id", "runtime:lab"}, {"kind", "runtime"}, {"name", "lab"}, {"url", "http://127.0.0.1:9876"}},
       {{"id", "hub:mesh"}, {"kind", "hub"}, {"name", "mesh"}, {"url", "https://hub.example"},
        {"device_id", "dev1"}, {"profile", "desktop"}}});
  g_model["local_running"] = false;
  g_model["local_initialized"] = !g_opt.local_uninitialized;
  if (g_opt.local_uninitialized) {
    g_model["connections"][0]["state"] = "not_initialized";
    g_model["connections"][0]["url"] = nullptr;
  }
  g_model["workspaces"] = Json::object();  /* "<connection>|<node>" -> [ws] */
  g_model["files"] = Json::object();       /* ws id -> [file] */
  g_model["tasks"] = Json::array();
  g_model["keys"] = Json::object();        /* key -> task id */
  g_model["actions"] = Json::array();
  g_model["transfers"] = Json::array();
  g_model["submits"] = 0;
  /* One workspace per Runtime connection to start with. */
  g_model["workspaces"]["runtime:lab|"] = Json::array(
      {{{"id", "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0"}, {"name", "默认工作区"}, {"created_at", iso(now_s() - 3600)}}});
  g_model["workspaces"]["hub:mesh|node1"] = Json::array(
      {{{"id", "b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1"}, {"name", "hub-ws"}, {"created_at", iso(now_s() - 3600)}}});
  save_locked();
}

std::string scope(const Json &p)
{
  return p.value("connection", std::string()) + "|" + p.value("node", std::string());
}

Json *find_by_id(Json &array, const std::string &id)
{
  for (Json &x : array) {
    if (x.value("id", std::string()) == id) {
      return &x;
    }
  }
  return nullptr;
}

/** A task's public record with its state advanced to `t`. */
void advance_task_locked(Json &task, double t)
{
  const std::string state = task["state"].get<std::string>();
  if (state == "succeeded" || state == "failed" || state == "cancelled") {
    return;
  }
  if (task.value("cancel_requested", false)) {
    task["state"] = "cancelled";
    task["reason"] = "Cancelled by request";
    task["updated_at"] = iso(t);
    return;
  }
  const double age = t - task["t0"].get<double>();
  const bool slow = task["spec"].value("name", std::string()).find("slow") != std::string::npos;
  std::string next = "queued";
  if (age >= 0.2) {
    next = "running";
  }
  if (age >= (slow ? 60.0 : 0.6)) {
    next = "succeeded";
  }
  if (next != state) {
    task["state"] = next;
    task["updated_at"] = iso(t);
    if (next == "succeeded") {
      task["exit_code"] = 0;
    }
  }
}

Json public_task(const Json &task, bool hub)
{
  Json out = task;
  out.erase("t0");
  out.erase("scope");
  out.erase("key");
  if (hub) {
    /* Hub snapshots carry no spec: name and workspace_id instead. */
    out["name"] = task["spec"].value("name", std::string());
    out["workspace_id"] = task["spec"].value("workspace_id", std::string());
    out.erase("spec");
  }
  return out;
}

Json tasks_for_locked(const std::string &sc, const std::string &ws)
{
  Json list = Json::array();
  const bool hub = sc.rfind("hub:", 0) == 0;
  for (auto it = g_model["tasks"].rbegin(); it != g_model["tasks"].rend(); ++it) {
    Json &t = *it;
    advance_task_locked(t, now_s());
    if (t["scope"] == sc && (ws.empty() || t["spec"].value("workspace_id", std::string()) == ws)) {
      list.push_back(public_task(t, hub));
    }
  }
  return list;
}

Json new_task_locked(const Json &spec, const std::string &sc, const std::string &key)
{
  const double t = now_s();
  Json task = {{"id", hex32("task")}, {"spec", spec}, {"state", "queued"}, {"created_at", iso(t)},
               {"updated_at", iso(t)}, {"backend_id", nullptr}, {"exit_code", nullptr}, {"reason", ""},
               {"cancel_requested", false}, {"t0", t}, {"scope", sc}, {"key", key}};
  g_model["tasks"].push_back(task);
  g_model["keys"][sc + "|" + key] = task["id"];
  return task;
}

Json action_summary(const Json &a)
{
  Json s = {{"id", a["id"]}, {"node_id", a["node_id"]}, {"state", a["state"]}, {"error", a.value("error", Json())},
            {"review_reason", a.value("review_reason", Json())}, {"created", a["created"]}, {"updated", a["updated"]},
            {"kind", a["request"]["kind"]}};
  return s;
}

void hub_changed_locked()
{
  static int64_t cursor = 0;
  cursor++;
  for (const std::string &sub : g_hub_subs) {
    event("hub.event", {{"sub", sub}, {"cursor", cursor}, {"kind", "actions.changed"}, {"payload", Json::object()}});
  }
}

Json *transfer_locked(const std::string &id)
{
  return find_by_id(g_model["transfers"], id);
}

void emit_transfer(const Json &t)
{
  Json pub = t;
  pub.erase("steps");
  event("transfer.updated", {{"transfer", pub}});
}

/** Advances uploads / downloads one step per tick (each change is a transfer.updated event). */
void tick_transfers_locked()
{
  for (Json &t : g_model["transfers"]) {
    const std::string state = t["state"].get<std::string>();
    if (state == "completed" || state == "failed" || state == "cancelled" || state == "interrupted") {
      continue;
    }
    const bool hub = t.value("connection", std::string()).rfind("hub:", 0) == 0;
    if (t.contains("action") && t["action"].is_object()) {
      /* Through a hub: waiting for the workspace.import review. */
      Json *a = find_by_id(g_model["actions"], t["action"]["id"].get<std::string>());
      if (a && (*a)["state"] == "succeeded") {
        t["state"] = "completed";
        t["files_done"] = t["files_total"];
        Json &files = g_model["files"][t["workspace_id"].get<std::string>()];
        if (!files.is_array()) {
          files = Json::array();
        }
        for (const Json &f : t["files"]) {
          files.push_back(f);
        }
        t["action"] = action_summary(*a);
        t["updated_at"] = iso(now_s());
        emit_transfer(t);
      }
      else if (a && (*a)["state"] == "rejected") {
        t["state"] = "failed";
        t["error"] = {{"code", "remote_error"}, {"message", "The action was rejected in review"}, {"retryable", false}};
        t["action"] = action_summary(*a);
        emit_transfer(t);
      }
      continue;
    }
    int steps = t.value("steps", 0);
    t["steps"] = steps + 1;
    t["updated_at"] = iso(now_s());
    if (steps == 0) {
      t["state"] = "running";
      t["bytes_done"] = t["bytes_total"].get<int64_t>() / 2;
    }
    else if (steps == 1 && t["local"].get<std::string>().find("interrupt") != std::string::npos &&
             !t.value("resumed", false))
    {
      /* A source named "*interrupt*" stops half-way, as after a crash; transfer.resume continues. */
      t["state"] = "interrupted";
    }
    else if (t["kind"] == "upload" && hub) {
      t["bytes_done"] = t["bytes_total"];
      const double tn = now_s();
      Json action = {{"id", hex32("import")}, {"node_id", t["node"]}, {"state", "review"},
                     {"review_reason", "workspace.import writes into the workspace"},
                     {"request", {{"kind", "workspace.import"},
                                  {"payload", {{"workspace_id", t["workspace_id"]}, {"files", t["files"]}}}}},
                     {"created", iso(tn)}, {"updated", iso(tn)}, {"error", nullptr}};
      g_model["actions"].push_back(action);
      t["action"] = action_summary(action);
      hub_changed_locked();
    }
    else {
      t["state"] = "completed";
      t["bytes_done"] = t["bytes_total"];
      t["files_done"] = t["files_total"];
      if (t["kind"] == "download") {
        const std::string bytes = artifact_bytes(t["remote"].get<std::string>());
        const fs::path dest(t["local"].get<std::string>());
        fs::create_directories(dest.parent_path());
        std::ofstream(dest, std::ios::binary) << bytes;
      }
      else {
        Json &files = g_model["files"][t["workspace_id"].get<std::string>()];
        if (!files.is_array()) {
          files = Json::array();
        }
        for (const Json &f : t["files"]) {
          files.push_back(f);
        }
      }
    }
    emit_transfer(t);
  }
}

void ticker()
{
  while (!g_stop.load()) {
    {
      std::lock_guard lock(g_m);
      for (auto &[sub, w] : g_watches) {
        const Json tasks = tasks_for_locked(w["scope"].get<std::string>(), w["workspace_id"].get<std::string>());
        if (!w.contains("last") || w["last"] != tasks) {
          w["last"] = tasks;
          event("watch.snapshot", {{"sub", sub}, {"tasks", tasks}, {"time", now_s()}});
        }
      }
      tick_transfers_locked();
      save_locked();
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(60));
  }
}

void run_logs(const std::string sub, const std::string task_id, const Json streams, const Json offsets)
{
  std::map<std::string, std::string> text;
  text["stdout"] = "开始计算 " + task_id.substr(0, 6) + "\n第1步 能量 −1.5e-3\n第2步 能量 −1.6e-3\n完成\n";
  text["stderr"] = "警告：网格较粗\n";
  std::map<std::string, int64_t> pos;
  for (const Json &s : streams) {
    const std::string name = s.get<std::string>();
    pos[name] = offsets.is_object() ? offsets.value(name, int64_t(0)) : 0;
  }
  bool more = true;
  while (more && !g_stop.load()) {
    more = false;
    for (auto &[name, p] : pos) {
      const std::string &t = text[name];
      if (p >= int64_t(t.size())) {
        continue;
      }
      size_t end = t.find('\n', size_t(p));
      end = end == std::string::npos ? t.size() : end + 1;
      event("logs.chunk", {{"sub", sub}, {"stream", name}, {"text", t.substr(size_t(p), end - size_t(p))},
                           {"offset", p}, {"next_offset", int64_t(end)}, {"bytes", int64_t(end) - p}});
      p = int64_t(end);
      more = true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  if (!g_stop.load()) {
    Json offs = Json::object();
    for (auto &[name, p] : pos) {
      offs[name] = p;
    }
    event("logs.end", {{"sub", sub}, {"offsets", offs}});
  }
}

void run_events(const std::string sub, int64_t offset)
{
  const Json all = Json::array({
      {{"v", 1}, {"seq", 1}, {"type", "run.started"}, {"src", "program"}, {"data", {{"app", "muFerro"}, {"total_steps", 100}}}},
      {{"v", 1}, {"seq", 2}, {"type", "progress"}, {"src", "program"}, {"data", {{"step", 50}, {"total_steps", 100}, {"fraction", 0.5}}}},
      {{"v", 1}, {"seq", 3}, {"type", "metrics"}, {"src", "program"}, {"data", {{"step", 50}, {"values", {{"total_energy", -1.5e-3}}}}}},
      {{"v", 1}, {"seq", 4}, {"type", "frame"}, {"src", "program"}, {"data", {{"dataset", "Polar"}, {"step", 50}, {"path", "Polar.00000050.dat"}}}},
      {{"v", 1}, {"seq", 5}, {"type", "message"}, {"src", "program"}, {"data", {{"level", "warning"}, {"text", "网格较粗"}}}},
      {{"v", 1}, {"seq", 6}, {"type", "progress"}, {"src", "program"}, {"data", {{"step", 100}, {"total_steps", 100}, {"fraction", 1.0}}}},
      {{"v", 1}, {"seq", 7}, {"type", "run.completed"}, {"src", "program"}, {"data", {{"status", "succeeded"}}}},
  });
  const int64_t line = 100;
  while (!g_stop.load() && offset / line < int64_t(all.size())) {
    event("events.batch", {{"sub", sub}, {"events", Json::array({all[size_t(offset / line)]})}, {"invalid", Json::array()},
                           {"offset", offset}, {"next_offset", offset + line}, {"bytes", line}});
    offset += line;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  if (!g_stop.load()) {
    event("events.end", {{"sub", sub}, {"next_offset", offset}});
  }
}

Json connection_locked(const std::string &id)
{
  for (const Json &c : g_model["connections"]) {
    if (c["id"] == id) {
      return c;
    }
  }
  return nullptr;
}

}  // namespace

void init(const std::string &dir, std::vector<std::string> args, SendFn send)
{
  g_opt.dir = dir;
  for (size_t i = 0; i < args.size(); i++) {
    if (args[i] == "--review-policy" && i + 1 < args.size()) {
      g_opt.review_policy = args[++i];
    }
    else if (args[i] == "--review-refuse") {
      g_opt.review_refuse = true;
    }
    else if (args[i] == "--forget-inspected-once") {
      g_opt.forget_inspected_once = true;
    }
    else if (args[i] == "--local-uninitialized") {
      g_opt.local_uninitialized = true;
    }
    else if (args[i] == "--submit-fail" && i + 1 < args.size()) {
      g_opt.submit_fail = std::atoi(args[++i].c_str());
    }
  }
  g_send = std::move(send);
  fs::create_directories(dir);
  {
    std::lock_guard lock(g_m);
    init_model();
  }
  g_ticker = std::thread(ticker);
}

void shutdown()
{
  g_stop = true;
  if (g_ticker.joinable()) {
    g_ticker.join();
  }
  for (std::thread &t : g_threads) {
    t.join();
  }
  std::ofstream(g_opt.dir + "/methods.log", std::ios::app) << "EOF\n";
}

bool handle(const Json &id, const std::string &method, const Json &p)
{
  record(method);
  std::lock_guard lock(g_m);
  const std::string sc = scope(p);
  const std::string conn = p.value("connection", std::string());
  if (method == "hello") {
    respond(id, Json{{"protocol", 1},
                     {"server", {{"name", "stk-bridge-fake"}, {"version", "0.0.1"}, {"python", "none"}, {"platform", "test"},
                                 {"pid", int64_t(getpid())}}},
                     {"methods", Json::array({"hello", "connections.list", "connections.check", "connections.add_runtime",
                                              "connections.remove", "connections.pair_hub", "connections.local",
                                              "connections.local_start", "hub.devices", "hub.templates", "hub.actions",
                                              "hub.action", "hub.review", "hub.policy", "hub.subscribe", "workspace.list",
                                              "workspace.create", "workspace.files", "upload.start", "download.start",
                                              "transfer.list", "transfer.get", "transfer.resume", "transfer.cancel",
                                              "task.submit", "task.list", "task.get", "task.cancel", "task.artifacts",
                                              "watch", "logs.subscribe", "events.subscribe", "unsubscribe"})},
                     {"events", Json::array({"transfer.updated", "watch.snapshot", "logs.chunk", "logs.end", "events.batch",
                                             "events.end", "hub.event", "subscription.error"})},
                     {"limits", {{"max_line_bytes", 16777216}, {"max_inflight", 64}, {"watch_interval_s", 2.0},
                                 {"log_chunk_bytes", 262144}, {"transfer_chunk_bytes", 1048576}}},
                     {"paths", {{"state_dir", g_opt.dir}, {"cache_dir", g_opt.dir}, {"blob_dir", g_opt.dir + "/blobs"},
                                {"download_dir", g_opt.dir + "/downloads"}}},
                     {"resumed_transfers", Json::array()}});
    return true;
  }
  if (method == "connections.list") {
    respond(id, {{"connections", g_model["connections"]}});
    return true;
  }
  if (method == "connections.check") {
    const std::string cid = p.value("id", std::string());
    const Json c = connection_locked(cid);
    if (c.is_null()) {
      error(id, "not_found", "Unknown connection");
    }
    else if (cid == "runtime:down") {
      respond(id, {{"id", cid}, {"ok", false}, {"error", {{"code", "unavailable"}, {"message", "The Runtime cannot be reached"},
                                                           {"retryable", true}}}});
    }
    else if (c["kind"] == "hub") {
      respond(id, {{"id", cid}, {"ok", true}, {"health", {{"ok", true}}}, {"nodes", 1}});
    }
    else if (c["kind"] == "local" && !g_model["local_running"].get<bool>()) {
      respond(id, {{"id", cid}, {"ok", false}, {"error", {{"code", "unavailable"}, {"message", "The local Runtime API is not running"},
                                                           {"retryable", true}}}});
    }
    else {
      respond(id, {{"id", cid}, {"ok", true}, {"health", {{"api_version", 1}, {"supervisor_running", true}}}});
    }
    return true;
  }
  if (method == "connections.add_runtime") {
    const std::string name = p.value("name", std::string());
    if (name == "bad") {
      error(id, "unauthorized", "The Runtime refused the stored token (401)");
      return true;
    }
    Json c = {{"id", "runtime:" + name}, {"kind", "runtime"}, {"name", name}, {"url", p.value("url", std::string())}};
    g_model["connections"].push_back(c);
    g_model["workspaces"]["runtime:" + name + "|"] = Json::array();
    save_locked();
    respond(id, {{"connection", c}});
    return true;
  }
  if (method == "connections.pair_hub") {
    const std::string name = p.value("name", std::string());
    Json c = {{"id", "hub:" + name}, {"kind", "hub"}, {"name", name}, {"url", p.value("url", std::string())},
              {"device_id", "dev-" + name}};
    g_model["connections"].push_back(c);
    save_locked();
    respond(id, {{"connection", c}});
    return true;
  }
  if (method == "connections.remove") {
    const std::string cid = p.value("id", std::string());
    Json &list = g_model["connections"];
    for (size_t i = 0; i < list.size(); i++) {
      if (list[i]["id"] == cid) {
        list.erase(i);
        save_locked();
        respond(id, {{"removed", cid}});
        return true;
      }
    }
    error(id, "not_found", "Unknown connection");
    return true;
  }
  if (method == "connections.local" || method == "connections.local_start") {
    if (method == "connections.local_start") {
      if (!g_model["local_initialized"].get<bool>()) {
        if (!p.value("initialize", false)) {
          error(id, "not_found", "No local Runtime is initialized on this computer");
          return true;
        }
        g_model["local_initialized"] = true;
        g_model["connections"][0]["state"] = "initialized";
        g_model["connections"][0]["url"] = "http://127.0.0.1:8765";
      }
      g_model["local_running"] = true;
      g_model["workspaces"]["local|"] = Json::array();
      save_locked();
    }
    const bool running = g_model["local_running"].get<bool>();
    respond(id, {{"initialized", g_model["local_initialized"].get<bool>()}, {"api_running", running},
                 {"supervisor_running", running},
                 {"url", "http://127.0.0.1:8765"}, {"state_dir", "/fake/runtime"}});
    return true;
  }
  if (method == "hub.devices") {
    respond(id, {{"devices", Json::array({{{"id", "node1"}, {"name", "gpu-node"}, {"role", "node"}, {"online", true},
                                           {"snapshot", Json::object()}},
                                          {{"id", "dev1"}, {"name", "STK Desktop"}, {"role", "client"}, {"online", true},
                                           {"snapshot", Json::object()}}})}});
    return true;
  }
  if (method == "hub.templates") {
    respond(id, {{"templates", {{"muferro-small", {{"argv", Json::array({"@python", "-m", "suan.mupro", "run"})}}}}}});
    return true;
  }
  if (method == "hub.policy") {
    respond(id, {{"policy", {{"device_profile", "desktop"}, {"desktop_auto", true}, {"desktop_auto_bytes", 268435456},
                             {"graph_auto_seconds", 300.0}, {"uploads", true}, {"upload_max_bytes", 1073741824},
                             {"upload_chunk_bytes", 1048576}, {"upload_quota_bytes", 4294967296LL},
                             {"import_max_files", 4096}, {"import_request_bytes", 4194304},
                             {"action_request_bytes", 1048576}, {"read_kinds", Json::array({"task.logs"})},
                             {"review_policy", g_opt.review_policy}}}});
    return true;
  }
  if (method == "hub.actions") {
    Json list = Json::array();
    for (const Json &a : g_model["actions"]) {
      Json x = a;
      x.erase("result");
      list.push_back(x); /* like the hub's listing: kind only inside request */
    }
    respond(id, {{"actions", list}});
    return true;
  }
  if (method == "hub.action") {
    const std::string aid = p.value("action_id", std::string());
    Json *a = find_by_id(g_model["actions"], aid);
    if (!a) {
      error(id, "not_found", "Action not found");
      return true;
    }
    g_inspected.insert(aid);
    respond(id, {{"action", *a}});
    return true;
  }
  if (method == "hub.review") {
    const std::string aid = p.value("action_id", std::string());
    const bool approved = p.value("approved", false);
    Json *a = find_by_id(g_model["actions"], aid);
    if (!a) {
      error(id, "not_found", "Action not found");
      return true;
    }
    if (approved && g_opt.forget_inspected_once) {
      /* As if the bridge had restarted between hub.action and hub.review. */
      g_opt.forget_inspected_once = false;
      g_inspected.clear();
    }
    if (approved && !g_inspected.count(aid)) {
      error(id, "review_not_inspected", "Read the action with hub.action before approving it");
      return true;
    }
    if (approved && g_opt.review_refuse) {
      error(id, "unauthorized", "This device may not approve its own action (review policy not-self)",
            {{"action_id", aid}, {"reason", "review_policy"}});
      return true;
    }
    (*a)["state"] = approved ? "succeeded" : "rejected";
    (*a)["updated"] = iso(now_s());
    if (approved && (*a)["request"]["kind"] == "task.submit") {
      const Json task = new_task_locked((*a)["request"]["payload"]["spec"], (*a)["scope"].get<std::string>(),
                                        (*a)["key"].get<std::string>());
      (*a)["result"] = public_task(task, true);
    }
    save_locked();
    hub_changed_locked();
    respond(id, {{"action", action_summary(*a)}});
    return true;
  }
  if (method == "hub.subscribe") {
    const std::string sub = hex32("hubsub");
    g_hub_subs.insert(sub);
    respond(id, {{"sub", sub}});
    return true;
  }
  if (method == "workspace.list") {
    Json list = g_model["workspaces"].value(sc, Json::array());
    respond(id, {{"workspaces", list}});
    return true;
  }
  if (method == "workspace.create") {
    Json ws = {{"id", hex32("ws")}, {"name", p.value("name", std::string())}, {"created_at", iso(now_s())}};
    Json &list = g_model["workspaces"][sc];
    if (!list.is_array()) {
      list = Json::array();
    }
    list.push_back(ws);
    save_locked();
    Json out = {{"workspace", ws}};
    if (conn.rfind("hub:", 0) == 0) {
      out["action"] = {{"id", hex32("wsaction")}, {"kind", "workspace.create"}, {"state", "succeeded"},
                       {"node_id", p.value("node", std::string())}};
    }
    respond(id, out);
    return true;
  }
  if (method == "workspace.files") {
    respond(id, {{"files", g_model["files"].value(p.value("workspace_id", std::string()), Json::array())}});
    return true;
  }
  if (method == "upload.start") {
    const fs::path source(p.value("source", std::string()));
    std::error_code ec;
    Json files = Json::array();
    int64_t total = 0;
    std::string remote = p.value("remote", source.filename().string());
    const bool into_root = remote == ".";
    if (into_root && !fs::is_directory(source, ec)) {
      remote = source.filename().string();
    }
    if (fs::is_directory(source, ec)) {
      for (auto it = fs::recursive_directory_iterator(source, ec); it != fs::recursive_directory_iterator(); ++it) {
        if (it->is_regular_file(ec) && !it->is_symlink(ec)) {
          const int64_t size = int64_t(it->file_size(ec));
          const std::string rel = fs::relative(it->path(), source, ec).generic_string();
          files.push_back({{"path", into_root ? rel : remote + "/" + rel},
                           {"size", size}, {"sha256", std::string(64, '0')}});
          total += size;
        }
      }
    }
    else if (fs::is_regular_file(source, ec)) {
      total = int64_t(fs::file_size(source, ec));
      files.push_back({{"path", remote}, {"size", total}, {"sha256", std::string(64, '0')}});
    }
    else {
      error(id, "invalid_params", "The upload source does not exist");
      return true;
    }
    const double t = now_s();
    Json tr = {{"id", hex32("up")}, {"kind", "upload"}, {"state", "queued"}, {"connection", conn},
               {"node", p.value("node", Json())}, {"workspace_id", p["workspace_id"]}, {"task_id", nullptr},
               {"local", source.string()}, {"remote", remote}, {"bytes_done", 0}, {"bytes_total", total},
               {"files_done", 0}, {"files_total", int64_t(files.size())}, {"current", nullptr}, {"sha256", nullptr},
               {"error", nullptr}, {"action", nullptr}, {"created_at", iso(t)}, {"updated_at", iso(t)}, {"files", files}};
    g_model["transfers"].push_back(tr);
    save_locked();
    Json pub = tr;
    pub.erase("files");
    respond(id, {{"transfer", pub}});
    return true;
  }
  if (method == "download.start") {
    const std::string path = p.value("path", std::string());
    const std::string owner = p.contains("task_id") ? p["task_id"].get<std::string>() : p.value("workspace_id", std::string());
    std::string dest = p.value("dest", std::string());
    if (dest.empty()) {
      dest = g_opt.dir + "/downloads/fake/" + owner + "/" + path;
    }
    const std::string bytes = artifact_bytes(path);
    const double t = now_s();
    Json tr = {{"id", hex32("down")}, {"kind", "download"}, {"state", "queued"}, {"connection", conn},
               {"node", p.value("node", Json())}, {"workspace_id", p.value("workspace_id", Json())},
               {"task_id", p.value("task_id", Json())}, {"local", dest}, {"remote", path}, {"bytes_done", 0},
               {"bytes_total", int64_t(bytes.size())}, {"files_done", 0}, {"files_total", 1}, {"current", path},
               {"sha256", stk::core::Sha256::hex(bytes)}, {"error", nullptr}, {"action", nullptr},
               {"created_at", iso(t)}, {"updated_at", iso(t)}, {"files", Json::array()}};
    g_model["transfers"].push_back(tr);
    save_locked();
    Json pub = tr;
    pub.erase("files");
    respond(id, {{"transfer", pub}});
    return true;
  }
  if (method == "transfer.list") {
    Json list = Json::array();
    for (const Json &t : g_model["transfers"]) {
      Json pub = t;
      pub.erase("files");
      pub.erase("steps");
      list.push_back(pub);
    }
    respond(id, {{"transfers", list}});
    return true;
  }
  if (method == "transfer.get" || method == "transfer.resume" || method == "transfer.cancel") {
    Json *t = transfer_locked(p.value("id", std::string()));
    if (!t) {
      error(id, "not_found", "Transfer not found");
      return true;
    }
    if (method == "transfer.cancel" && (*t)["state"] != "completed") {
      (*t)["state"] = "cancelled";
      if ((*t)["action"].is_object()) {
        if (Json *a = find_by_id(g_model["actions"], (*t)["action"]["id"].get<std::string>())) {
          (*a)["state"] = "rejected";
          hub_changed_locked();
        }
      }
    }
    if (method == "transfer.resume" && ((*t)["state"] == "interrupted" || (*t)["state"] == "failed")) {
      (*t)["state"] = "running";
      (*t)["error"] = nullptr;
      (*t)["steps"] = 1;
      (*t)["resumed"] = true;
    }
    save_locked();
    Json pub = *t;
    pub.erase("files");
    pub.erase("steps");
    respond(id, {{"transfer", pub}});
    return true;
  }
  if (method == "task.submit") {
    const std::string key = p.value("idempotency_key", std::string());
    const int fails = g_opt.submit_fail;
    const int submits = g_model["submits"].get<int>() + 1;
    g_model["submits"] = submits;
    save_locked();
    if (submits <= fails) {
      error(id, "unavailable", "The Runtime cannot be reached (fake)", nullptr, true);
      return true;
    }
    Json spec = p.value("spec", Json());
    const bool hub = conn.rfind("hub:", 0) == 0;
    if (hub && p.contains("template")) {
      spec = {{"workspace_id", p["workspace_id"]}, {"argv", Json::array({"@python", "-m", "suan.mupro", "run"})},
              {"name", p["template"]}, {"backend", "local"}};
    }
    const std::string kkey = sc + "|" + key;
    if (g_model["keys"].contains(kkey)) {
      Json *t = find_by_id(g_model["tasks"], g_model["keys"][kkey].get<std::string>());
      if (t && !hub && (*t)["spec"] != spec) {
        error(id, "conflict", "Idempotency key reused with a different request");
        return true;
      }
      advance_task_locked(*t, now_s());
      Json out = {{"task", public_task(*t, hub)}};
      respond(id, out);
      return true;
    }
    if (hub && !p.contains("template")) {
      /* Custom command through the hub: an action in review, keyed by the idempotency key. */
      for (const Json &a : g_model["actions"]) {
        if (a.value("key", std::string()) == key) {
          Json out = {{"action", action_summary(a)}};
          if (a["state"] == "succeeded" && a.contains("result")) {
            out["task"] = a["result"];
          }
          else if (a["state"] == "rejected") {
            error(id, "remote_error", "The action was rejected in review", {{"action", action_summary(a)}});
            return true;
          }
          respond(id, out);
          return true;
        }
      }
      const double t = now_s();
      Json action = {{"id", hex32("submit")}, {"node_id", p.value("node", std::string())}, {"state", "review"},
                     {"review_reason", "custom task.submit"}, {"key", key}, {"scope", sc},
                     {"request", {{"kind", "task.submit"}, {"payload", {{"spec", spec}}}}},
                     {"created", iso(t)}, {"updated", iso(t)}, {"error", nullptr}};
      g_model["actions"].push_back(action);
      save_locked();
      hub_changed_locked();
      respond(id, {{"action", action_summary(action)}});
      return true;
    }
    const Json task = new_task_locked(spec, sc, key);
    save_locked();
    Json out = {{"task", public_task(task, hub)}};
    if (hub) {
      out["action"] = {{"id", hex32("tpl")}, {"kind", "task.submit"}, {"state", "succeeded"}, {"node_id", p.value("node", std::string())}};
    }
    respond(id, out);
    return true;
  }
  if (method == "task.list") {
    respond(id, {{"tasks", tasks_for_locked(sc, p.value("workspace_id", std::string()))}});
    return true;
  }
  if (method == "task.get" || method == "task.cancel" || method == "task.artifacts") {
    Json *t = find_by_id(g_model["tasks"], p.value("task_id", std::string()));
    if (!t) {
      error(id, "not_found", "Task not found");
      return true;
    }
    advance_task_locked(*t, now_s());
    const bool hub = conn.rfind("hub:", 0) == 0;
    if (method == "task.cancel") {
      (*t)["cancel_requested"] = true;
      save_locked();
      respond(id, {{"task", public_task(*t, hub)}});
    }
    else if (method == "task.get") {
      respond(id, {{"task", public_task(*t, hub)}});
    }
    else {
      const std::string state = (*t)["state"].get<std::string>();
      const bool done = state == "succeeded" || state == "failed" || state == "cancelled";
      respond(id, {{"artifacts", done ? artifacts_of(*t) : Json::array()}});
    }
    return true;
  }
  if (method == "watch") {
    const std::string sub = hex32("watch");
    g_watches[sub] = {{"scope", sc}, {"workspace_id", p.value("workspace_id", std::string())}};
    respond(id, {{"sub", sub}});
    return true;
  }
  if (method == "logs.subscribe") {
    const std::string sub = hex32("logs");
    respond(id, {{"sub", sub}});
    const Json streams = p.value("streams", Json::array({"stdout", "stderr"}));
    g_threads.emplace_back(run_logs, sub, p.value("task_id", std::string()), streams, p.value("offsets", Json()));
    return true;
  }
  if (method == "events.subscribe") {
    const std::string sub = hex32("events");
    respond(id, {{"sub", sub}});
    g_threads.emplace_back(run_events, sub, p.value("offset", int64_t(0)));
    return true;
  }
  if (method == "unsubscribe") {
    const std::string sub = p.value("sub", std::string());
    g_watches.erase(sub);
    g_hub_subs.erase(sub);
    respond(id, {{"ok", true}});
    return true;
  }
  return false;
}

}  // namespace fake_jobs
