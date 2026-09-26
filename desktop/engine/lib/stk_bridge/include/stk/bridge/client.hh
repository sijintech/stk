/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk::bridge::Client: the desktop app's side of the STK desktop bridge protocol v1
 * (docs/specs/stk-desktop-bridge-v1.md). It spawns `python -m suan.desktop_bridge --stdio`,
 * speaks NDJSON over the child's stdin / stdout, matches responses to calls, routes events to
 * subscriptions, drains stderr into the "Bridge log", and restarts the bridge when it dies.
 *
 *   stk::bridge::ClientOptions options;
 *   options.executor = wm->executor();          // callbacks run on the main loop
 *   auto client = stk::bridge::Client::create(options);
 *   client->start();
 *   client->colormaps_list().then([](auto r) { ... });
 *   auto sub = client->subscribe_logs({{"runtime:cluster"}, task_id}, {.on_chunk = ...});
 *
 * Threads: a supervisor thread (spawn, hello, restarts, timeouts), and per bridge process a
 * stdout reader, a stderr reader and a stdin writer. Every user callback (future continuations,
 * subscription and event handlers, state listeners) is posted to `ClientOptions::executor`,
 * never run under a client lock; with no executor they run on the client's threads.
 *
 * Restart and replay (liveness is the process itself: EOF on stdout or its exit, never the
 * cadence of `watch`):
 *
 * | In flight when the bridge dies            | What the client does                                    |
 * |-------------------------------------------|---------------------------------------------------------|
 * | reads (list/get/check/catalog/presets/...) | sent again to the new bridge (same id)                 |
 * | task.submit (key), workspace.create /      | sent again: the idempotency key returns the first      |
 * | task.cancel / upload.start / download.start| result (Runtime key, hub action id, or the transfer    |
 * | with idempotency_key                       | the key names in the journal)                          |
 * | graph.evaluate mode=hub                    | sent again: the action id derives from eval_id         |
 * | graph.evaluate mode=local                  | fails `unavailable` (the evaluation died with it)      |
 * | everything else (add_runtime, pair_hub,    | fails `unavailable` (retryable): it may or may not     |
 * | review, upload/download.start without a    | have happened; the caller decides (transfers resume    |
 * | key, transfer.*, local_start, graph.cancel)| by themselves, see hello below)                        |
 * | hub.review approval                        | the new bridge forgot the inspection: run hub.action   |
 * |                                            | again before approving (spec §7)                       |
 * | logs.subscribe                             | re-subscribed with offsets = last next_offset / stream |
 * | events.subscribe                           | re-subscribed with offset = last next_offset           |
 * | hub.subscribe                              | re-subscribed with after = last cursor                 |
 * | watch                                      | re-subscribed (the first snapshot follows at once)     |
 * | transfers                                  | the new bridge's hello {resume_transfers: true}        |
 * |                                            | resumes interrupted journals (HelloInfo::resumed_...)  |
 *
 * Calls made while the bridge is starting or restarting wait (within their timeout) and are sent
 * once `hello` succeeded; in the Failed state they fail at once with `unavailable`. Retries per
 * call are bounded (CallOptions::max_retries). Restarts back off exponentially; after
 * `RestartPolicy::max_failures` consecutive short-lived bridges the client enters Failed until
 * #restart. A bridge refused because another bridge holds its state directory (hello answered
 * `busy` with data.state_dir, exit status 3; spec §1) is Failed at once with that non-retryable
 * `busy` error, never restarted in a loop. A protocol mismatch (`unsupported`) is Failed as well.
 * #close closes the bridge's stdin (the bridge stops subscriptions and pauses
 * transfers; Runtime tasks and hub actions keep running), waits up to the grace period, then
 * terminates the process group.
 */
#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "stk/bridge/future.hh"
#include "stk/bridge/log_ring.hh"
#include "stk/bridge/protocol.hh"
#include "stk/bridge/python.hh"
#include "stk/bridge/types.hh"

namespace stk::bridge {

enum class BridgeState : uint8_t {
  Stopped,    /* not started, or closed */
  Starting,   /* first bridge process: spawned, waiting for hello */
  Ready,      /* hello answered; calls flow */
  Restarting, /* the bridge died; a new one is scheduled or saying hello */
  Failed,     /* gave up (spawn impossible, repeated crashes, protocol mismatch); see last_error */
  Stopping,   /* close() in progress */
};
std::string_view bridge_state_name(BridgeState state);

struct RestartPolicy {
  double initial_backoff_s = 0.25;
  double max_backoff_s = 10.0;
  /** A bridge that stayed up this long resets the failure count. */
  double healthy_after_s = 30.0;
  /** Consecutive failures (died before `healthy_after_s`, or never said hello) before Failed. */
  int max_failures = 5;
};

struct ClientOptions {
  /** Python interpreter lookup (setting, STK_PYTHON, bundled, PATH). */
  PythonLookup python;
  /** Extra interpreter arguments before `-m suan.desktop_bridge` (e.g. "-X", "utf8"). */
  std::vector<std::string> python_args;
  /** --state-dir / --cache-dir (empty: the bridge's defaults). */
  std::string state_dir, cache_dir;
  /** --strict: the bridge validates everything it sends (tests, CI). */
  bool strict = false;
  /** Validate every message both ways against the schema (debug; also STK_BRIDGE_VALIDATE=1).
   * Violations go to the bridge log; an invalid result fails its call with internal_error. */
  bool validate = false;
  /** Environment changes for the bridge process (PYTHONPATH, STK_PROFILES_FILE, ...). */
  std::map<std::string, std::optional<std::string>> env;
  /** Full command instead of the Python bridge (tests: a scripted fake bridge). */
  std::vector<std::string> command;
  /** Where callbacks run (stk::wm::WindowManager::executor()); empty: the client's threads. */
  Executor executor;

  std::string client_name = "stk-desktop";
  std::string client_version = "0";
  /** hello {resume_transfers} (spec default true). */
  bool resume_transfers = true;

  /** Default per-call timeout (0 = none). A timeout fails the call locally with `timeout`. */
  double call_timeout_s = 120.0;
  /** How long a new bridge may take to answer hello before it is killed and restarted. */
  double hello_timeout_s = 60.0;
  /** close(): how long the bridge may take to exit after EOF before it is terminated. */
  double shutdown_grace_s = 10.0;
  RestartPolicy restart;
  /** Stderr ring ("Bridge log" panel). */
  size_t log_lines = 4000;
};

struct CallOptions {
  /** Seconds; < 0 uses ClientOptions::call_timeout_s, 0 = none. */
  double timeout_s = -1.0;
  enum class Retry : uint8_t { Auto, Never, Always };
  /** Re-send after a bridge restart: Auto follows method_is_retry_safe (see the table above). */
  Retry retry = Retry::Auto;
  int max_retries = 2;
};

struct LogsHandlers {
  std::function<void(const LogChunk &)> on_chunk;
  std::function<void(const LogsEnd &)> on_end;
  /** `final`: the subscription ended (subscribe refused, or subscription.error final). */
  std::function<void(const Error &, bool final)> on_error;
};
struct EventsHandlers {
  std::function<void(const EventsBatch &)> on_batch;
  std::function<void(const EventsEnd &)> on_end;
  std::function<void(const Error &, bool final)> on_error;
};
struct WatchHandlers {
  std::function<void(const WatchSnapshot &)> on_snapshot;
  std::function<void(const Error &, bool final)> on_error;
};
struct HubEventHandlers {
  std::function<void(const HubEvent &)> on_event;
  std::function<void(const Error &, bool final)> on_error;
};

class Client;

/**
 * A subscription (watch, logs, events, hub events) that survives bridge restarts. RAII: the
 * destructor unsubscribes; after that no callback of it runs (callbacks already posted to the
 * executor are skipped). Move-only.
 */
class Subscription {
 public:
  struct State;
  Subscription() = default;
  explicit Subscription(std::shared_ptr<State> state);
  ~Subscription();
  Subscription(Subscription &&other) noexcept;
  Subscription &operator=(Subscription &&other) noexcept;
  Subscription(const Subscription &) = delete;
  Subscription &operator=(const Subscription &) = delete;

  /** Stops it (sends `unsubscribe` when the bridge has it); idempotent. */
  void unsubscribe();
  /** Not unsubscribed and not ended (end event, final error). */
  bool active() const;
  /** The bridge's current sub id ("" while (re)subscribing). */
  std::string server_id() const;
  /** How often it was (re)subscribed (1 + replays). */
  int subscribe_count() const;
  /** logs: the next byte offset per stream (what a replay resumes from). */
  std::map<std::string, int64_t> log_offsets() const;
  /** events: the next byte offset. */
  int64_t events_offset() const;

 private:
  std::shared_ptr<State> state_;
};

/** RAII registration of a listener (state changes, events); removes it on destruction. */
class ListenerHandle {
 public:
  ListenerHandle() = default;
  explicit ListenerHandle(std::function<void()> remove) : remove_(std::move(remove)) {}
  ~ListenerHandle()
  {
    reset();
  }
  ListenerHandle(ListenerHandle &&other) noexcept : remove_(std::move(other.remove_))
  {
    other.remove_ = nullptr;
  }
  ListenerHandle &operator=(ListenerHandle &&other) noexcept
  {
    if (this != &other) {
      reset();
      remove_ = std::move(other.remove_);
      other.remove_ = nullptr;
    }
    return *this;
  }
  void reset()
  {
    if (remove_) {
      auto remove = std::move(remove_);
      remove_ = nullptr;
      remove();
    }
  }

 private:
  std::function<void()> remove_;
};

struct ClientStats {
  uint64_t spawned = 0;       /* bridge processes started */
  uint64_t restarts = 0;      /* restarts after a death */
  uint64_t calls_sent = 0;    /* request lines written (incl. re-sends) */
  uint64_t calls_retried = 0; /* re-sent after a restart */
  uint64_t protocol_errors = 0;
  uint64_t schema_violations = 0;
};

class Client {
 public:
  static std::unique_ptr<Client> create(ClientOptions options);
  /** close(): EOF to the bridge, grace period, then terminate. */
  ~Client();
  Client(const Client &) = delete;
  Client &operator=(const Client &) = delete;

  /** Spawns the bridge and says hello in the background. False (state Failed) when it cannot be
   * spawned at all (no Python); `r_error` says why. */
  bool start(std::string *r_error = nullptr);
  /** Leaves Failed: resets the failure count and starts a new bridge. */
  void restart();
  /** Graceful shutdown (idempotent); pending calls fail with `shutting_down`. grace < 0: options. */
  void close(double grace_s = -1.0);

  BridgeState state() const;
  /** The error that led to Failed (or the last restart), if any. */
  std::optional<Error> last_error() const;
  /** Blocks until Ready (true), Failed / Stopped (false) or the timeout. Not on the executor's
   * thread when callbacks are posted there. */
  bool wait_ready(double timeout_s);
  /** `fn(state, error)` on every change (via the executor). */
  ListenerHandle on_state(std::function<void(BridgeState, const std::optional<Error> &)> fn);
  /** The current bridge's hello result (nullopt before the first hello). */
  std::optional<HelloInfo> hello_info() const;
  /** The current bridge process id (0 when none). */
  int64_t bridge_pid() const;
  ClientStats stats() const;
  /** The bridge's stderr and the client's lifecycle notes. */
  LogRing &bridge_log();

  /** Any method: `params` defaults to {}. The future completes on the executor. */
  Future<Json> call(std::string method, Json params = Json::object(), CallOptions options = {});

  /** Events not tied to a subscription or call: transfer.updated, graph.progress and anything a
   * newer bridge sends. `event` empty = every such event. */
  ListenerHandle on_event(std::string event, std::function<void(const std::string &event, const Json &data)> fn);
  ListenerHandle on_transfer(std::function<void(const Transfer &)> fn);

  /* -- Session ---------------------------------------------------------------------------- */
  Future<Json> shutdown_bridge();

  /* -- Connections (§6) ------------------------------------------------------------------- */
  Future<std::vector<ConnectionInfo>> connections_list();
  Future<ConnectionInfo> connections_add_runtime(const AddRuntimeParams &params);
  Future<Json> connections_remove(const std::string &id);
  Future<ConnectionCheck> connections_check(const std::string &id);
  Future<ConnectionInfo> connections_pair_hub(const PairHubParams &params);
  Future<LocalRuntimeStatus> connections_local();
  /** `initialize`: set up an uninitialized local Runtime first (suan server init defaults). */
  Future<LocalRuntimeStatus> connections_local_start(bool initialize = false);

  /* -- Hub (§7) ----------------------------------------------------------------------------- */
  Future<Json> hub_devices(const std::string &connection);
  Future<Json> hub_templates(const std::string &connection);
  Future<Json> hub_actions(const std::string &connection);
  /** Reads the full request and marks it inspected (needed before approving). */
  Future<Json> hub_action(const std::string &connection, const std::string &action_id);
  /** An approval the hub's review policy refuses is `unauthorized` with data.reason "review_policy". */
  Future<Json> hub_review(const std::string &connection, const std::string &action_id, bool approved);
  /** The hub's limits for this device (desktop auto-run cap, uploads, review policy; WP11). */
  Future<HubPolicy> hub_policy(const std::string &connection);
  Subscription subscribe_hub(const HubSubscribeParams &params, HubEventHandlers handlers);

  /* -- Workspaces and tasks (§7) ------------------------------------------------------------ */
  Future<Json> workspace_list(const Target &target);
  Future<Submitted> workspace_create(const Target &target, const std::string &name,
                                     const std::string &idempotency_key = {});
  Future<std::vector<FileEntry>> workspace_files(const Target &target, const std::string &workspace_id);
  Future<Submitted> task_submit(const TaskSubmitParams &params);
  Future<Json> task_list(const Target &target, const std::string &workspace_id = {});
  Future<Json> task_get(const Target &target, const std::string &task_id);
  Future<Submitted> task_cancel(const Target &target, const std::string &task_id,
                                const std::string &idempotency_key = {});
  Future<std::vector<FileEntry>> task_artifacts(const Target &target, const std::string &task_id);

  /* -- Subscriptions (§8) ------------------------------------------------------------------- */
  Subscription watch(const WatchParams &params, WatchHandlers handlers);
  Subscription subscribe_logs(const LogsParams &params, LogsHandlers handlers);
  Subscription subscribe_events(const EventsParams &params, EventsHandlers handlers);

  /* -- Transfers (§9) ----------------------------------------------------------------------- */
  Future<Transfer> upload_start(const UploadParams &params);
  Future<Transfer> download_start(const DownloadParams &params);
  Future<std::vector<Transfer>> transfer_list();
  Future<Transfer> transfer_get(const std::string &id);
  Future<Transfer> transfer_resume(const std::string &id);
  Future<Transfer> transfer_cancel(const std::string &id);
  Future<BlobEnsureResult> blob_ensure(const std::vector<std::string> &sha256, const std::string &connection = {});

  /* -- Graphs, probes, colormaps (§10) ------------------------------------------------------ */
  Future<Json> graph_catalog();
  Future<Json> graph_presets();
  Future<Json> graph_validate(const Json &graph, const Json &parameters = nullptr);
  /** `on_progress` receives graph.progress of this eval_id (via the executor). Cancelling the
   * future sends graph.cancel {eval_id} (with connection / node in hub mode). */
  Future<EvaluateResult> graph_evaluate(const EvaluateParams &params,
                                        std::function<void(const GraphProgress &)> on_progress = {},
                                        CallOptions options = {});
  /** With `target` (hub connection + node) it also cancels a hub evaluation this bridge is not
   * waiting for, e.g. one started before a bridge restart. */
  Future<CancelResult> graph_cancel(const std::string &eval_id, const Target &target = {});
  Future<Json> probe(const ProbeParams &params);
  Future<ColormapList> colormaps_list();

  struct Impl;

 private:
  explicit Client(std::shared_ptr<Impl> impl);
  Subscription subscribe(std::string method, Json params, std::shared_ptr<Subscription::State> state);
  std::shared_ptr<Impl> impl_;
};

}  // namespace stk::bridge
