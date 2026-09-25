/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The bridge client: process supervision, request routing, subscriptions, replay. */

#include "stk/bridge/client.hh"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <set>
#include <thread>

#include "stk/bridge/process.hh"
#include "stk/bridge/schema.hh"
#include "stk/core/clock.hh"
#include "stk/core/paths.hh"

namespace stk::bridge {

std::string_view bridge_state_name(const BridgeState state)
{
  switch (state) {
    case BridgeState::Stopped:
      return "stopped";
    case BridgeState::Starting:
      return "starting";
    case BridgeState::Ready:
      return "ready";
    case BridgeState::Restarting:
      return "restarting";
    case BridgeState::Failed:
      return "failed";
    case BridgeState::Stopping:
      return "stopping";
  }
  return "unknown";
}

/* ============================================================================================ */
/* Subscription state */

struct Subscription::State {
  enum class Kind { Watch, Logs, Events, Hub };
  Kind kind = Kind::Watch;
  std::string method;
  Json base_params;
  std::weak_ptr<Client::Impl> client;
  LogsHandlers logs;
  EventsHandlers events;
  WatchHandlers watch;
  HubEventHandlers hub;

  /** Set by the user (unsubscribe / handle destroyed): no callback runs any more. */
  std::atomic<bool> closed{false};
  /** Ended by the bridge (end event, final error): not replayed. */
  std::atomic<bool> ended{false};

  /* Replay state, guarded by `m` (lock order: Client::Impl::mutex, then m). */
  mutable std::mutex m;
  std::string server_sub;
  bool subscribing = false;
  int subscribe_count = 0;
  std::map<std::string, int64_t> log_offsets;
  int64_t events_offset = 0;
  int64_t hub_cursor = 0;

  bool live() const
  {
    return !closed.load() && !ended.load();
  }

  /** The subscribe params for the next (re)subscription: the base plus the replay offsets. */
  Json params() const
  {
    std::lock_guard lock(m);
    Json p = base_params;
    switch (kind) {
      case Kind::Logs:
        if (!log_offsets.empty()) {
          Json offsets = p.contains("offsets") ? p["offsets"] : Json::object();
          for (const auto &[stream, offset] : log_offsets) {
            offsets[stream] = offset;
          }
          p["offsets"] = offsets;
        }
        break;
      case Kind::Events:
        if (events_offset > 0) {
          p["offset"] = events_offset;
        }
        break;
      case Kind::Hub:
        if (hub_cursor > 0) {
          p["after"] = hub_cursor;
        }
        break;
      case Kind::Watch:
        break;
    }
    return p;
  }

  void deliver_error(const Error &error, bool final) const
  {
    switch (kind) {
      case Kind::Logs:
        if (logs.on_error) {
          logs.on_error(error, final);
        }
        break;
      case Kind::Events:
        if (events.on_error) {
          events.on_error(error, final);
        }
        break;
      case Kind::Watch:
        if (watch.on_error) {
          watch.on_error(error, final);
        }
        break;
      case Kind::Hub:
        if (hub.on_error) {
          hub.on_error(error, final);
        }
        break;
    }
  }
};

/* ============================================================================================ */
/* Client implementation */

namespace {

double now_s()
{
  return core::monotonic_seconds();
}

/** Exit status of a bridge that refused to start because another bridge owns its state dir. */
constexpr int kStateDirBusyExit = 3;

}  // namespace

struct Client::Impl : std::enable_shared_from_this<Client::Impl> {
  /** One bridge process and its I/O threads. */
  struct Generation {
    uint64_t id = 0;
    std::unique_ptr<ChildProcess> child;
    std::thread reader, err_reader, writer;
    std::mutex wq_mutex;
    std::condition_variable wq_cv;
    std::deque<std::string> wq;
    bool wq_close = false; /* close stdin after the queued lines */
    bool wq_stop = false;  /* stop now */
    std::atomic<bool> eof{false};
    double started_at = 0.0;
    double hello_deadline = 0.0;
    bool hello_done = false;
    bool dead = false;
    /** The bridge answered `busy` because another bridge owns the state directory. */
    bool state_dir_busy = false;
    std::optional<Error> fatal; /* a reason not to restart */
  };

  struct Pending {
    uint64_t id = 0;
    std::string method;
    Json params;
    CallOptions options;
    std::shared_ptr<detail::FutureState<Json>> future; /* null: internal request */
    /** Internal completion (hello, subscribe), run by the reader thread under `mutex`. */
    std::function<void(const Result<Json> &)> internal;
    /** Rebuilds params right before sending (subscriptions resume from their offsets). */
    std::function<Json()> make_params;
    double deadline = 0.0; /* monotonic; 0 = none */
    bool retry_safe = false;
    int retries = 0;
    uint64_t sent_generation = 0; /* 0 = queued */
    bool bypass_ready = false;    /* hello: sent before the bridge is ready */
  };

  ClientOptions options;
  bool validate = false;
  const ProtocolSchema *schema = nullptr;

  mutable std::mutex mutex;
  std::condition_variable wake;       /* supervisor */
  std::condition_variable state_cv;   /* wait_ready */
  BridgeState state = BridgeState::Stopped;
  std::optional<Error> last_error;
  std::optional<HelloInfo> hello;
  std::shared_ptr<Generation> gen;
  uint64_t next_generation = 1;
  uint64_t next_id = 1;
  std::map<uint64_t, Pending> pending;
  int inflight = 0;
  size_t max_line = kDefaultMaxLineBytes;
  int64_t max_inflight = 64;
  std::set<std::shared_ptr<Subscription::State>> subs;
  std::map<std::string, std::shared_ptr<Subscription::State>> subs_by_server;
  std::map<std::string, std::function<void(const GraphProgress &)>> progress;
  uint64_t next_listener = 1;
  std::map<uint64_t, std::function<void(BridgeState, const std::optional<Error> &)>> state_listeners;
  std::map<uint64_t, std::pair<std::string, std::function<void(const std::string &, const Json &)>>>
      event_listeners;
  std::thread supervisor;
  bool supervisor_running = false;
  bool stop_requested = false;
  bool closing = false;
  int failures = 0;
  double next_start_at = 0.0;
  ClientStats stats;
  LogRing log;
  /** Work to hand to the executor once `mutex` is released (see Unlocker). */
  std::vector<std::function<void()>> deferred;

  explicit Impl(ClientOptions opts) : options(std::move(opts)), log(options.log_lines)
  {
    const std::optional<std::string> env = core::getenv_utf8("STK_BRIDGE_VALIDATE");
    validate = options.validate || (env && *env == "1");
    if (validate) {
      schema = &ProtocolSchema::embedded();
    }
  }

  /* -- helpers ---------------------------------------------------------------------------- */

  void post(std::function<void()> fn)
  {
    if (options.executor) {
      options.executor(std::move(fn));
    }
    else {
      fn();
    }
  }

  /** Releases `lock` and posts the deferred work. */
  void unlock_and_flush(std::unique_lock<std::mutex> &lock)
  {
    std::vector<std::function<void()>> work;
    work.swap(deferred);
    lock.unlock();
    for (auto &fn : work) {
      fn();
    }
  }

  void note(const std::string &text)
  {
    log.append_line("[stk-bridge client] " + text, LogRing::Source::Client);
  }

  void set_state_locked(const BridgeState next, std::optional<Error> error = std::nullopt)
  {
    if (error) {
      last_error = error;
    }
    if (state == next) {
      return;
    }
    state = next;
    state_cv.notify_all();
    note(std::string("state ") + std::string(bridge_state_name(next)) +
         (error ? " (" + error->describe() + ")" : std::string()));
    for (const auto &[id, fn] : state_listeners) {
      auto listener = fn;
      std::optional<Error> err = last_error;
      deferred.push_back([this, listener, next, err] { post([listener, next, err] { listener(next, err); }); });
    }
  }

  /** Completes a user future outside the lock. */
  void complete_later(const std::shared_ptr<detail::FutureState<Json>> &future, Result<Json> result)
  {
    if (future) {
      deferred.push_back([future, result = std::move(result)]() mutable { future->complete(std::move(result)); });
    }
  }

  void fail_pending_locked(Pending &p, const Error &error)
  {
    if (p.future) {
      complete_later(p.future, error);
    }
    else if (p.internal) {
      p.internal(error);
    }
  }

  /* -- sending ---------------------------------------------------------------------------- */

  bool can_send_locked(const Pending &p) const
  {
    if (!gen || gen->dead) {
      return false;
    }
    if (p.bypass_ready) {
      return true;
    }
    return gen->hello_done && state == BridgeState::Ready && inflight < max_inflight;
  }

  void send_locked(Pending &p)
  {
    if (p.make_params) {
      p.params = p.make_params();
    }
    Json message = Json::object();
    message["id"] = p.id;
    message["method"] = p.method;
    message["params"] = p.params;
    if (validate && schema->has_method(p.method)) {
      const auto issues = schema->check_request(message);
      if (!issues.empty()) {
        stats.schema_violations++;
        note("schema: request " + p.method + " " + issues[0].path + ": " + issues[0].message);
      }
    }
    std::string line;
    try {
      line = encode_line(message);
    }
    catch (const ProtocolError &error) {
      /* call() checked this; params rebuilt by make_params cannot introduce it. */
      note(std::string("cannot encode ") + p.method + ": " + error.what());
      return;
    }
    p.sent_generation = gen->id;
    inflight++;
    stats.calls_sent++;
    {
      std::lock_guard wq_lock(gen->wq_mutex);
      gen->wq.push_back(std::move(line));
    }
    gen->wq_cv.notify_one();
  }

  /** Sends queued calls in id order while the bridge is ready and below its in-flight limit. */
  void flush_locked()
  {
    for (auto &[id, p] : pending) {
      if (p.sent_generation != 0) {
        continue;
      }
      if (!can_send_locked(p)) {
        if (!p.bypass_ready && inflight >= max_inflight) {
          break;
        }
        continue;
      }
      send_locked(p);
    }
  }

  uint64_t enqueue_locked(Pending p)
  {
    p.id = next_id++;
    const uint64_t id = p.id;
    auto [it, inserted] = pending.emplace(id, std::move(p));
    if (can_send_locked(it->second)) {
      send_locked(it->second);
    }
    return id;
  }

  /* -- calls ------------------------------------------------------------------------------- */

  Future<Json> call(std::string method, Json params, const CallOptions &opts)
  {
    auto future = std::make_shared<detail::FutureState<Json>>(options.executor);
    if (params.is_null()) {
      params = Json::object();
    }
    Json message = Json::object();
    message["id"] = 0;
    message["method"] = method;
    message["params"] = params;
    std::optional<Error> local;
    try {
      const std::string line = encode_line(message);
      std::lock_guard lock(mutex);
      if (line.size() - 1 > max_line) {
        local = Error::make(ErrorCode::LineTooLong,
                            "The request is " + std::to_string(line.size() - 1) + " bytes; the bridge accepts " +
                                std::to_string(max_line));
      }
    }
    catch (const ProtocolError &error) {
      local = Error::make(ErrorCode::InvalidParams, error.what());
    }
    /* Methods the built-in schema does not know (a newer bridge's) go out unchecked. */
    if (!local && validate && schema->has_method(method)) {
      const auto issues = schema->check_request(message);
      if (!issues.empty()) {
        Json errors = Json::array();
        for (const auto &issue : issues) {
          errors.push_back({{"path", issue.path}, {"message", issue.message}});
        }
        local = Error::make(ErrorCode::InvalidParams,
                            (issues[0].path.empty() ? "/" : issues[0].path) + ": " + issues[0].message,
                            true, Json{{"errors", errors}});
      }
    }
    if (local) {
      future->complete(*local);
      return Future<Json>(future);
    }

    std::unique_lock lock(mutex);
    if (closing || state == BridgeState::Stopping) {
      lock.unlock();
      future->complete(Error::make(ErrorCode::ShuttingDown, "The bridge client is closing"));
      return Future<Json>(future);
    }
    if (state == BridgeState::Failed || state == BridgeState::Stopped) {
      const std::string why = last_error ? " (" + last_error->describe() + ")" : std::string();
      lock.unlock();
      future->complete(Error::make(ErrorCode::Unavailable, "The bridge is not running" + why));
      return Future<Json>(future);
    }
    Pending p;
    p.method = std::move(method);
    p.params = std::move(params);
    p.options = opts;
    p.future = future;
    const double timeout = opts.timeout_s < 0 ? options.call_timeout_s : opts.timeout_s;
    p.deadline = timeout > 0 ? now_s() + timeout : 0.0;
    p.retry_safe = opts.retry == CallOptions::Retry::Always ||
                   (opts.retry == CallOptions::Retry::Auto && method_is_retry_safe(p.method, p.params));
    const uint64_t id = enqueue_locked(std::move(p));
    if (timeout > 0) {
      wake.notify_all();
    }
    lock.unlock();
    std::weak_ptr<Impl> weak = weak_from_this();
    future->add_cancel_hook([weak, id] {
      if (auto self = weak.lock()) {
        self->forget_unsent(id);
      }
    });
    return Future<Json>(future);
  }

  /** A cancelled call that was not sent yet is never sent. */
  void forget_unsent(const uint64_t id)
  {
    std::lock_guard lock(mutex);
    auto it = pending.find(id);
    if (it != pending.end() && it->second.sent_generation == 0) {
      pending.erase(it);
    }
  }

  /** Fire-and-forget request (unsubscribe, graph.cancel); dropped on restart. */
  void send_internal_locked(const std::string &method, Json params)
  {
    Pending p;
    p.method = method;
    p.params = std::move(params);
    p.internal = [](const Result<Json> &) {};
    enqueue_locked(std::move(p));
  }

  /* -- subscriptions ------------------------------------------------------------------------ */

  void subscribe_locked(const std::shared_ptr<Subscription::State> &sub)
  {
    {
      std::lock_guard sl(sub->m);
      if (sub->subscribing || !sub->server_sub.empty()) {
        return;
      }
      sub->subscribing = true;
    }
    Pending p;
    p.method = sub->method;
    std::weak_ptr<Subscription::State> weak = sub;
    p.make_params = [weak]() -> Json {
      auto s = weak.lock();
      return s ? s->params() : Json::object();
    };
    p.params = sub->params();
    p.internal = [this, sub](const Result<Json> &result) { on_subscribed_locked(sub, result); };
    enqueue_locked(std::move(p));
  }

  void on_subscribed_locked(const std::shared_ptr<Subscription::State> &sub, const Result<Json> &result)
  {
    std::string server_sub;
    {
      std::lock_guard sl(sub->m);
      sub->subscribing = false;
      if (result.ok()) {
        server_sub = io::get_string(result.value(), "sub");
      }
    }
    if (!result.ok()) {
      /* Restart drops (unavailable) resubscribe after the next hello; a refusal ends it. */
      if (result.error().local && result.error().code == ErrorCode::Unavailable) {
        return;
      }
      sub->ended = true;
      subs.erase(sub);
      const Error error = result.error();
      deferred.push_back([this, sub, error] {
        post([sub, error] {
          if (!sub->closed.load()) {
            sub->deliver_error(error, true);
          }
        });
      });
      return;
    }
    if (!sub->live()) {
      if (!server_sub.empty()) {
        send_internal_locked("unsubscribe", Json{{"sub", server_sub}});
      }
      return;
    }
    {
      std::lock_guard sl(sub->m);
      sub->server_sub = server_sub;
      sub->subscribe_count++;
    }
    subs_by_server[server_sub] = sub;
  }

  void unsubscribe(const std::shared_ptr<Subscription::State> &sub)
  {
    std::unique_lock lock(mutex);
    sub->closed = true;
    subs.erase(sub);
    std::string server_sub;
    {
      std::lock_guard sl(sub->m);
      server_sub = sub->server_sub;
      sub->server_sub.clear();
    }
    if (!server_sub.empty()) {
      subs_by_server.erase(server_sub);
      if (gen && gen->hello_done && !gen->dead && !closing) {
        send_internal_locked("unsubscribe", Json{{"sub", server_sub}});
      }
    }
    unlock_and_flush(lock);
  }

  /* -- incoming ----------------------------------------------------------------------------- */

  void on_line(const std::shared_ptr<Generation> &g, std::string_view line)
  {
    if (line.empty() || line == "\r") {
      return;
    }
    Json message;
    try {
      message = decode_line(line);
    }
    catch (const ProtocolError &error) {
      std::lock_guard lock(mutex);
      stats.protocol_errors++;
      note(std::string("dropped a bridge line: ") + error.what());
      return;
    }
    std::string why;
    switch (classify_message(message, &why)) {
      case MessageKind::Invalid: {
        std::lock_guard lock(mutex);
        stats.protocol_errors++;
        note("dropped a bridge message: " + why);
        return;
      }
      case MessageKind::Response:
        on_response(g, message);
        return;
      case MessageKind::Event:
        on_event(message);
        return;
    }
  }

  void on_response(const std::shared_ptr<Generation> &g, const Json &message)
  {
    std::unique_lock lock(mutex);
    const Json &id = message["id"];
    Result<Json> result = message.contains("result") ? Result<Json>(message["result"]) :
                                                       Result<Json>(Error::from_json(message["error"]));
    if (!id.is_number_unsigned() && !id.is_number_integer()) {
      /* id null: the bridge could not read one of our lines (parse_error, line_too_long). */
      stats.protocol_errors++;
      note("the bridge rejected a request line: " +
           (result.ok() ? std::string("?") : result.error().describe()));
      if (!result.ok() && result.error().code == ErrorCode::Busy && !g->hello_done) {
        mark_state_dir_busy_locked(g, result.error());
      }
      return;
    }
    const uint64_t rid = id.get<uint64_t>();
    auto it = pending.find(rid);
    if (it == pending.end() || it->second.sent_generation != g->id) {
      return; /* cancelled or timed out earlier, or a previous bridge's */
    }
    Pending p = std::move(it->second);
    pending.erase(it);
    inflight = std::max(0, inflight - 1);
    if (validate && result.ok()) {
      const auto issues = schema->check_response(message, p.method);
      if (!issues.empty()) {
        stats.schema_violations++;
        note("schema: result of " + p.method + " " + issues[0].path + ": " + issues[0].message);
        result = Error::make(ErrorCode::InternalError, "The bridge sent a result that violates the protocol schema: " +
                                                           issues[0].path + " " + issues[0].message);
      }
    }
    if (p.internal) {
      p.internal(result);
    }
    else {
      complete_later(p.future, std::move(result));
    }
    flush_locked();
    unlock_and_flush(lock);
  }

  void mark_state_dir_busy_locked(const std::shared_ptr<Generation> &g, const Error &error)
  {
    g->state_dir_busy = true;
    g->fatal = Error::make(ErrorCode::Busy, error.message.empty() ?
                                                "Another STK desktop bridge is using this state directory" :
                                                error.message,
                           false, error.data);
    g->fatal->retryable = false;
    /* EOF makes the refusing bridge exit (status 3). */
    {
      std::lock_guard wq_lock(g->wq_mutex);
      g->wq_close = true;
    }
    g->wq_cv.notify_one();
  }

  template<typename T, typename F>
  void deliver_sub_locked(const std::shared_ptr<Subscription::State> &sub, T payload, F fn)
  {
    deferred.push_back([this, sub, payload = std::move(payload), fn]() mutable {
      post([sub, payload = std::move(payload), fn]() mutable {
        if (!sub->closed.load()) {
          fn(*sub, payload);
        }
      });
    });
  }

  /** `sub` by value: it may alias the map entry this erases. */
  void end_sub_locked(const std::shared_ptr<Subscription::State> sub)
  {
    sub->ended = true;
    std::string server_sub;
    {
      std::lock_guard sl(sub->m);
      server_sub = sub->server_sub;
      sub->server_sub.clear();
    }
    subs_by_server.erase(server_sub);
    subs.erase(sub);
  }

  void on_event(const Json &message)
  {
    const std::string name = message["event"].get<std::string>();
    const Json &data = message["data"];
    std::unique_lock lock(mutex);
    if (validate && schema->has_event(name)) { /* unknown events: a newer bridge */
      const auto issues = schema->check_event(message);
      if (!issues.empty()) {
        stats.schema_violations++;
        note("schema: event " + name + " " + issues[0].path + ": " + issues[0].message);
      }
    }
    const std::string sub_id = io::get_string(data, "sub");
    if (!sub_id.empty()) {
      auto it = subs_by_server.find(sub_id);
      if (it == subs_by_server.end()) {
        return; /* an old or unsubscribed subscription */
      }
      const std::shared_ptr<Subscription::State> sub = it->second; /* a copy: ending it erases the map entry */
      route_sub_event_locked(sub, name, data);
      unlock_and_flush(lock);
      return;
    }
    if (name == "graph.progress") {
      const std::string eval_id = io::get_string(data, "eval_id");
      auto it = progress.find(eval_id);
      if (it != progress.end()) {
        auto fn = it->second;
        GraphProgress event{eval_id, data.contains("event") ? data["event"] : Json()};
        deferred.push_back([this, fn, event] { post([fn, event] { fn(event); }); });
      }
    }
    for (const auto &[id, entry] : event_listeners) {
      if (entry.first.empty() || entry.first == name) {
        auto fn = entry.second;
        deferred.push_back([this, fn, name, data] { post([fn, name, data] { fn(name, data); }); });
      }
    }
    unlock_and_flush(lock);
  }

  void route_sub_event_locked(const std::shared_ptr<Subscription::State> &sub, const std::string &name,
                              const Json &data)
  {
    using Kind = Subscription::State::Kind;
    if (name == "subscription.error") {
      const Error error = Error::from_json(data.contains("error") ? data["error"] : Json::object());
      const bool final = io::get_bool(data, "final", false);
      if (final) {
        end_sub_locked(sub);
      }
      deliver_sub_locked(sub, std::make_pair(error, final), [](const Subscription::State &s, auto &e) {
        s.deliver_error(e.first, e.second);
      });
      return;
    }
    switch (sub->kind) {
      case Kind::Logs:
        if (name == "logs.chunk") {
          LogChunk chunk;
          chunk.stream = io::get_string(data, "stream");
          chunk.text = io::get_string(data, "text");
          chunk.offset = io::get_int(data, "offset", 0);
          chunk.next_offset = io::get_int(data, "next_offset", 0);
          {
            std::lock_guard sl(sub->m);
            auto known = sub->log_offsets.find(chunk.stream);
            if (known != sub->log_offsets.end() && chunk.offset != known->second) {
              const int64_t expected = known->second;
              if (chunk.next_offset <= expected) {
                note("dropped a duplicate logs.chunk (" + chunk.stream + " " + std::to_string(chunk.offset) + ".." +
                     std::to_string(chunk.next_offset) + ", expected " + std::to_string(expected) + ")");
                return;
              }
              if (chunk.offset < expected &&
                  int64_t(chunk.text.size()) == chunk.next_offset - chunk.offset)
              {
                /* Overlap on a character boundary (expected was a next_offset): keep the new bytes. */
                chunk.text.erase(0, size_t(expected - chunk.offset));
                chunk.offset = expected;
              }
              else {
                note("logs.chunk " + chunk.stream + " starts at " + std::to_string(chunk.offset) +
                     ", expected " + std::to_string(expected));
              }
            }
            sub->log_offsets[chunk.stream] = chunk.next_offset;
          }
          if (sub->logs.on_chunk) {
            deliver_sub_locked(sub, std::move(chunk), [](const Subscription::State &s, const LogChunk &c) {
              s.logs.on_chunk(c);
            });
          }
        }
        else if (name == "logs.end") {
          LogsEnd end;
          const Json offsets = data.contains("offsets") ? data["offsets"] : Json::object();
          for (auto it = offsets.begin(); offsets.is_object() && it != offsets.end(); ++it) {
            if (it.value().is_number_integer()) {
              end.offsets[it.key()] = it.value().get<int64_t>();
            }
          }
          {
            std::lock_guard sl(sub->m);
            for (const auto &[stream, offset] : end.offsets) {
              sub->log_offsets[stream] = offset;
            }
          }
          end_sub_locked(sub);
          if (sub->logs.on_end) {
            deliver_sub_locked(sub, std::move(end), [](const Subscription::State &s, const LogsEnd &e) {
              s.logs.on_end(e);
            });
          }
        }
        break;
      case Kind::Events:
        if (name == "events.batch") {
          EventsBatch batch;
          batch.events = data.contains("events") ? data["events"] : Json::array();
          batch.invalid = data.contains("invalid") ? data["invalid"] : Json::array();
          batch.offset = io::get_int(data, "offset", 0);
          batch.next_offset = io::get_int(data, "next_offset", 0);
          {
            std::lock_guard sl(sub->m);
            if (sub->subscribe_count > 0 && batch.next_offset <= sub->events_offset && sub->events_offset > 0) {
              note("dropped a duplicate events.batch");
              return;
            }
            sub->events_offset = batch.next_offset;
          }
          if (sub->events.on_batch) {
            deliver_sub_locked(sub, std::move(batch), [](const Subscription::State &s, const EventsBatch &b) {
              s.events.on_batch(b);
            });
          }
        }
        else if (name == "events.end") {
          EventsEnd end{io::get_int(data, "next_offset", 0)};
          {
            std::lock_guard sl(sub->m);
            sub->events_offset = std::max(sub->events_offset, end.next_offset);
          }
          end_sub_locked(sub);
          if (sub->events.on_end) {
            deliver_sub_locked(sub, end, [](const Subscription::State &s, const EventsEnd &e) { s.events.on_end(e); });
          }
        }
        break;
      case Kind::Watch:
        if (name == "watch.snapshot" && sub->watch.on_snapshot) {
          WatchSnapshot snapshot{data.contains("tasks") ? data["tasks"] : Json::array(),
                                 io::get_number(data, "time", 0.0)};
          deliver_sub_locked(sub, std::move(snapshot), [](const Subscription::State &s, const WatchSnapshot &w) {
            s.watch.on_snapshot(w);
          });
        }
        break;
      case Kind::Hub:
        if (name == "hub.event") {
          HubEvent event{io::get_int(data, "cursor", 0), io::get_string(data, "kind"),
                         data.contains("payload") ? data["payload"] : Json::object()};
          {
            std::lock_guard sl(sub->m);
            sub->hub_cursor = std::max(sub->hub_cursor, event.cursor);
          }
          if (sub->hub.on_event) {
            deliver_sub_locked(sub, std::move(event), [](const Subscription::State &s, const HubEvent &e) {
              s.hub.on_event(e);
            });
          }
        }
        break;
    }
  }

  /* -- process lifecycle -------------------------------------------------------------------- */

  std::vector<std::string> command_line(std::string &r_error) const
  {
    if (!options.command.empty()) {
      return options.command;
    }
    const std::optional<std::string> python = find_python(options.python, r_error);
    if (!python) {
      return {};
    }
    std::vector<std::string> argv = {*python};
    argv.insert(argv.end(), options.python_args.begin(), options.python_args.end());
    argv.insert(argv.end(), {"-m", "suan.desktop_bridge", "--stdio"});
    if (!options.state_dir.empty()) {
      argv.insert(argv.end(), {"--state-dir", options.state_dir});
    }
    if (!options.cache_dir.empty()) {
      argv.insert(argv.end(), {"--cache-dir", options.cache_dir});
    }
    if (options.strict) {
      argv.push_back("--strict");
    }
    return argv;
  }

  /** Spawns a bridge and sends hello (supervisor thread, `lock` held on entry and exit). */
  void spawn_locked(std::unique_lock<std::mutex> &lock)
  {
    std::string error;
    const std::vector<std::string> argv = command_line(error);
    if (argv.empty()) {
      failures = options.restart.max_failures + 1;
      set_state_locked(BridgeState::Failed, Error::make(ErrorCode::Unavailable, error));
      fail_queued_locked(Error::make(ErrorCode::Unavailable, error));
      return;
    }
    SpawnOptions spawn;
    spawn.argv = argv;
    spawn.env = options.env;
    if (!spawn.env.count("PYTHONIOENCODING")) {
      spawn.env["PYTHONIOENCODING"] = "utf-8:backslashreplace";
    }
    if (!spawn.env.count("PYTHONUNBUFFERED")) {
      spawn.env["PYTHONUNBUFFERED"] = "1";
    }
    lock.unlock();
    std::unique_ptr<ChildProcess> child = ChildProcess::spawn(spawn, error);
    lock.lock();
    if (!child) {
      const Error e = Error::make(ErrorCode::Unavailable, "Cannot start the bridge: " + error);
      note(e.message);
      schedule_restart_locked(e, true);
      return;
    }
    auto g = std::make_shared<Generation>();
    g->id = next_generation++;
    g->child = std::move(child);
    g->started_at = now_s();
    g->hello_deadline = options.hello_timeout_s > 0 ? g->started_at + options.hello_timeout_s : 0.0;
    gen = g;
    stats.spawned++;
    std::string shown;
    for (const std::string &a : argv) {
      shown += (shown.empty() ? "" : " ") + a;
    }
    note("started bridge pid " + std::to_string(g->child->pid()) + ": " + shown);
    g->reader = std::thread([this, g] { reader_main(g); });
    g->err_reader = std::thread([this, g] { stderr_main(g); });
    g->writer = std::thread([g] { writer_main(g); });

    Pending hello_call;
    hello_call.method = "hello";
    Json params = Json::object();
    params["protocol"] = kProtocolVersion;
    params["client"] = {{"name", options.client_name}, {"version", options.client_version}};
    params["resume_transfers"] = options.resume_transfers;
    hello_call.params = params;
    hello_call.bypass_ready = true;
    hello_call.internal = [this, g](const Result<Json> &result) { on_hello_locked(g, result); };
    enqueue_locked(std::move(hello_call));
  }

  void on_hello_locked(const std::shared_ptr<Generation> &g, const Result<Json> &result)
  {
    if (g != gen || g->dead || closing) {
      return;
    }
    if (!result.ok()) {
      const Error &error = result.error();
      if (error.local) {
        return; /* the bridge died before answering; the death handler restarts */
      }
      if (error.code == ErrorCode::Busy && !error.data.is_null() && error.data.contains("state_dir")) {
        mark_state_dir_busy_locked(g, error);
        note("the bridge refused to start: " + error.message);
        return;
      }
      g->fatal = error.code == ErrorCode::Unsupported ? std::optional<Error>(error) : std::nullopt;
      note("hello failed: " + error.describe());
      g->child->kill();
      return;
    }
    HelloInfo info = HelloInfo::from_json(result.value());
    if (info.protocol != kProtocolVersion) {
      g->fatal = Error::make(ErrorCode::Unsupported,
                             "The bridge speaks protocol " + std::to_string(info.protocol) + ", this app 1");
      g->child->kill();
      return;
    }
    g->hello_done = true;
    max_line = size_t(std::max<int64_t>(1024, info.limits.max_line_bytes));
    max_inflight = std::max<int64_t>(1, info.limits.max_inflight);
    note("bridge " + info.server.version + " ready (python " + info.server.python + ", pid " +
         std::to_string(info.server.pid) + ")" +
         (info.resumed_transfers.empty() ? std::string() :
                                           ", resumed " + std::to_string(info.resumed_transfers.size()) +
                                               " transfer(s)"));
    hello = std::move(info);
    set_state_locked(BridgeState::Ready);
    /* Replay subscriptions first (from their offsets), then the calls that waited. */
    for (const auto &sub : subs) {
      if (sub->live()) {
        subscribe_locked(sub);
      }
    }
    flush_locked();
  }

  void reader_main(std::shared_ptr<Generation> g)
  {
    LineSplitter splitter;
    std::vector<char> buffer(64 * 1024);
    while (true) {
      const std::ptrdiff_t n = g->child->read(ChildProcess::Stream::Stdout, buffer.data(), buffer.size());
      if (n <= 0) {
        break;
      }
      {
        std::lock_guard lock(mutex);
        splitter.set_max_line_bytes(max_line);
      }
      splitter.feed(
          std::string_view(buffer.data(), size_t(n)), [&](std::string_view line) { on_line(g, line); },
          [&](size_t length) {
            std::lock_guard lock(mutex);
            stats.protocol_errors++;
            note("dropped a bridge line of " + std::to_string(length) + " bytes (over the line limit)");
          });
    }
    if (splitter.pending() > 0) {
      std::lock_guard lock(mutex);
      note("discarded " + std::to_string(splitter.pending()) + " bytes of an unterminated final line");
    }
    g->eof = true;
    std::lock_guard lock(mutex);
    wake.notify_all();
  }

  void stderr_main(std::shared_ptr<Generation> g)
  {
    std::vector<char> buffer(16 * 1024);
    while (true) {
      const std::ptrdiff_t n = g->child->read(ChildProcess::Stream::Stderr, buffer.data(), buffer.size());
      if (n <= 0) {
        break;
      }
      log.append_bytes(std::string_view(buffer.data(), size_t(n)));
    }
    log.flush();
  }

  static void writer_main(std::shared_ptr<Generation> g)
  {
    while (true) {
      std::string line;
      {
        std::unique_lock lock(g->wq_mutex);
        g->wq_cv.wait(lock, [&] { return g->wq_stop || g->wq_close || !g->wq.empty(); });
        if (g->wq_stop) {
          return;
        }
        if (g->wq.empty()) {
          /* wq_close: EOF for the bridge after everything queued was written. */
          lock.unlock();
          g->child->close_stdin();
          return;
        }
        line = std::move(g->wq.front());
        g->wq.pop_front();
      }
      if (!g->child->write_stdin(line)) {
        return; /* the bridge is gone; the reader sees EOF */
      }
    }
  }

  void fail_queued_locked(const Error &error)
  {
    for (auto it = pending.begin(); it != pending.end();) {
      if (it->second.sent_generation == 0) {
        Pending p = std::move(it->second);
        it = pending.erase(it);
        fail_pending_locked(p, error);
      }
      else {
        ++it;
      }
    }
  }

  /** After a death (or a failed spawn): back off and restart, or give up. */
  void schedule_restart_locked(const Error &reason, const bool count_failure)
  {
    if (closing) {
      return;
    }
    if (count_failure) {
      failures++;
    }
    if (failures > options.restart.max_failures) {
      Error error = Error::make(ErrorCode::Unavailable,
                                "The bridge keeps exiting (" + std::to_string(failures) +
                                    " times in a row); last: " + reason.message);
      set_state_locked(BridgeState::Failed, error);
      fail_queued_locked(error);
      return;
    }
    const double delay = std::min(options.restart.max_backoff_s,
                                  options.restart.initial_backoff_s * std::pow(2.0, std::max(0, failures - 1)));
    next_start_at = now_s() + delay;
    stats.restarts++;
    note("restarting the bridge in " + std::to_string(int(delay * 1000)) + " ms");
    set_state_locked(BridgeState::Restarting, reason);
  }

  /** The current bridge process ended (supervisor thread; `lock` held). */
  void handle_death_locked(std::unique_lock<std::mutex> &lock, const std::shared_ptr<Generation> &g)
  {
    g->dead = true;
    if (gen == g) {
      gen = nullptr;
    }
    /* Stop the writer, then reap the process (and kill what it left in its group). */
    {
      std::lock_guard wq_lock(g->wq_mutex);
      g->wq_stop = true;
    }
    g->wq_cv.notify_all();
    lock.unlock();
    g->child->kill();
    const std::optional<ExitStatus> status = g->child->wait(-1.0);
    /* stderr: let the last lines arrive, then stop (a detached helper may hold the pipe). */
    for (int i = 0; i < 50 && !g->eof.load(); i++) {
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    g->child->abort_reads();
    if (g->reader.joinable()) {
      g->reader.join();
    }
    if (g->err_reader.joinable()) {
      g->err_reader.join();
    }
    if (g->writer.joinable()) {
      g->writer.join();
    }
    lock.lock();
    const std::string how = status ? status->describe() : std::string("unknown status");
    note("bridge pid " + std::to_string(g->child->pid()) + " ended (" + how + ")");
    const double uptime = now_s() - g->started_at;
    Error reason = Error::make(ErrorCode::Unavailable,
                               "The bridge process ended (" + how + ") while the request was in flight; it may or "
                               "may not have been carried out");

    /* In-flight calls of this bridge: re-send the idempotent ones, fail the rest. */
    inflight = 0;
    std::vector<Pending> dropped;
    for (auto it = pending.begin(); it != pending.end();) {
      Pending &p = it->second;
      if (p.sent_generation != g->id) {
        ++it;
        continue;
      }
      if (p.internal) {
        dropped.push_back(std::move(p));
        it = pending.erase(it);
        continue;
      }
      if (p.future && p.future->ready()) {
        it = pending.erase(it); /* timed out or cancelled already */
        continue;
      }
      if (p.retry_safe && p.retries < p.options.max_retries && !closing) {
        p.retries++;
        p.sent_generation = 0;
        stats.calls_retried++;
        ++it;
        continue;
      }
      Pending failed = std::move(p);
      it = pending.erase(it);
      Error error = closing ? Error::make(ErrorCode::ShuttingDown, "The bridge exited while the client was closing")
                            : reason;
      fail_pending_locked(failed, error);
    }
    for (Pending &p : dropped) {
      p.internal(Error::make(ErrorCode::Unavailable, "The bridge restarted"));
    }
    /* Subscriptions lose their bridge-side ids; they resubscribe after the next hello. */
    subs_by_server.clear();
    for (const auto &sub : subs) {
      std::lock_guard sl(sub->m);
      sub->server_sub.clear();
      sub->subscribing = false;
    }

    if (closing) {
      return;
    }
    if (g->state_dir_busy || (status && status->code == kStateDirBusyExit && !g->hello_done)) {
      Error error = g->fatal ? *g->fatal :
                               Error::make(ErrorCode::Busy,
                                           "Another STK desktop bridge is using this state directory (exit 3)");
      error.retryable = false;
      failures = options.restart.max_failures + 1;
      set_state_locked(BridgeState::Failed, error);
      fail_queued_locked(error);
      return;
    }
    if (g->fatal) {
      failures = options.restart.max_failures + 1;
      set_state_locked(BridgeState::Failed, *g->fatal);
      fail_queued_locked(*g->fatal);
      return;
    }
    if (g->hello_done && uptime >= options.restart.healthy_after_s) {
      failures = 0;
    }
    schedule_restart_locked(Error::make(ErrorCode::Unavailable, "The bridge process ended (" + how + ")"), true);
  }

  void supervisor_main()
  {
    std::unique_lock lock(mutex);
    while (!stop_requested) {
      const double now = now_s();
      /* A new bridge is due. */
      if (!gen && !closing && (state == BridgeState::Starting || state == BridgeState::Restarting) &&
          now >= next_start_at)
      {
        spawn_locked(lock);
        unlock_and_flush(lock);
        lock.lock();
        continue;
      }
      if (gen) {
        std::shared_ptr<Generation> g = gen;
        if (!g->hello_done && g->hello_deadline > 0 && now >= g->hello_deadline && !g->state_dir_busy) {
          note("no hello answer within " + std::to_string(int(options.hello_timeout_s)) + " s; killing the bridge");
          g->hello_deadline = 0;
          g->child->kill();
        }
        if (g->eof.load() || g->child->poll()) {
          handle_death_locked(lock, g);
          unlock_and_flush(lock);
          lock.lock();
          continue;
        }
      }
      /* Call timeouts. */
      double next_deadline = 0.0;
      for (auto it = pending.begin(); it != pending.end();) {
        Pending &p = it->second;
        if (p.deadline > 0 && p.deadline <= now) {
          const double timeout = p.options.timeout_s < 0 ? options.call_timeout_s : p.options.timeout_s;
          Error error = Error::make(ErrorCode::Timeout, "No answer to " + p.method + " within " +
                                                            std::to_string(timeout) + " s");
          p.deadline = 0.0;
          if (p.future) {
            complete_later(p.future, error);
          }
          if (p.sent_generation == 0) {
            it = pending.erase(it); /* never sent: forget it */
            continue;
          }
          /* Sent: keep the slot until the bridge answers (the late answer is dropped). */
        }
        else if (p.deadline > 0 && (next_deadline == 0.0 || p.deadline < next_deadline)) {
          next_deadline = p.deadline;
        }
        ++it;
      }
      if (!deferred.empty()) {
        unlock_and_flush(lock);
        lock.lock();
        continue;
      }
      /* Sleep until the next due thing; poll the process every 250 ms (its exit may not close
       * stdout when a helper inherited it). */
      double until = now + (gen ? 0.25 : 1.0);
      if (!gen && (state == BridgeState::Starting || state == BridgeState::Restarting) && !closing) {
        until = std::min(until, next_start_at);
      }
      if (gen && !gen->hello_done && gen->hello_deadline > 0) {
        until = std::min(until, gen->hello_deadline);
      }
      if (next_deadline > 0) {
        until = std::min(until, next_deadline);
      }
      const double wait_s = std::max(0.0, until - now_s());
      wake.wait_for(lock, std::chrono::microseconds(int64_t(wait_s * 1e6)));
    }
  }

  void start_supervisor_locked()
  {
    if (!supervisor_running) {
      supervisor_running = true;
      stop_requested = false;
      supervisor = std::thread([this] { supervisor_main(); });
    }
  }
};

/* ============================================================================================ */
/* Subscription handle */

Subscription::Subscription(std::shared_ptr<State> state) : state_(std::move(state)) {}

Subscription::~Subscription()
{
  unsubscribe();
}

Subscription::Subscription(Subscription &&other) noexcept : state_(std::move(other.state_)) {}

Subscription &Subscription::operator=(Subscription &&other) noexcept
{
  if (this != &other) {
    unsubscribe();
    state_ = std::move(other.state_);
  }
  return *this;
}

void Subscription::unsubscribe()
{
  if (!state_) {
    return;
  }
  std::shared_ptr<State> state = std::move(state_);
  state_ = nullptr;
  if (state->closed.exchange(true)) {
    return;
  }
  if (auto client = state->client.lock()) {
    client->unsubscribe(state);
  }
}

bool Subscription::active() const
{
  return state_ && state_->live();
}

std::string Subscription::server_id() const
{
  if (!state_) {
    return {};
  }
  std::lock_guard lock(state_->m);
  return state_->server_sub;
}

int Subscription::subscribe_count() const
{
  if (!state_) {
    return 0;
  }
  std::lock_guard lock(state_->m);
  return state_->subscribe_count;
}

std::map<std::string, int64_t> Subscription::log_offsets() const
{
  if (!state_) {
    return {};
  }
  std::lock_guard lock(state_->m);
  return state_->log_offsets;
}

int64_t Subscription::events_offset() const
{
  if (!state_) {
    return 0;
  }
  std::lock_guard lock(state_->m);
  return state_->events_offset;
}

/* ============================================================================================ */
/* Client */

std::unique_ptr<Client> Client::create(ClientOptions options)
{
  return std::unique_ptr<Client>(new Client(std::make_shared<Impl>(std::move(options))));
}

Client::Client(std::shared_ptr<Impl> impl) : impl_(std::move(impl)) {}

Client::~Client()
{
  close();
}

bool Client::start(std::string *r_error)
{
  std::unique_lock lock(impl_->mutex);
  if (impl_->state != BridgeState::Stopped && impl_->state != BridgeState::Failed) {
    return true;
  }
  if (impl_->closing) {
    if (r_error) {
      *r_error = "the client was closed";
    }
    return false;
  }
  std::string error;
  if (impl_->options.command.empty() && !find_python(impl_->options.python, error)) {
    impl_->set_state_locked(BridgeState::Failed, Error::make(ErrorCode::Unavailable, error));
    impl_->unlock_and_flush(lock);
    if (r_error) {
      *r_error = error;
    }
    return false;
  }
  impl_->failures = 0;
  impl_->next_start_at = 0.0;
  impl_->set_state_locked(BridgeState::Starting);
  impl_->start_supervisor_locked();
  impl_->wake.notify_all();
  impl_->unlock_and_flush(lock);
  return true;
}

void Client::restart()
{
  std::unique_lock lock(impl_->mutex);
  if (impl_->closing) {
    return;
  }
  if (impl_->state == BridgeState::Failed || impl_->state == BridgeState::Stopped) {
    impl_->failures = 0;
    impl_->next_start_at = 0.0;
    impl_->last_error.reset();
    impl_->set_state_locked(BridgeState::Starting);
    impl_->start_supervisor_locked();
    impl_->wake.notify_all();
  }
  impl_->unlock_and_flush(lock);
}

void Client::close(double grace_s)
{
  Impl &impl = *impl_;
  if (grace_s < 0) {
    grace_s = impl.options.shutdown_grace_s;
  }
  std::unique_lock lock(impl.mutex);
  if (impl.closing && !impl.supervisor_running) {
    return;
  }
  const bool was_closing = impl.closing;
  impl.closing = true;
  if (!was_closing) {
    impl.set_state_locked(BridgeState::Stopping);
    impl.fail_queued_locked(Error::make(ErrorCode::ShuttingDown, "The bridge client is closing"));
  }
  std::shared_ptr<Impl::Generation> g = impl.gen;
  if (g) {
    std::lock_guard wq_lock(g->wq_mutex);
    g->wq_close = true;
  }
  if (g) {
    g->wq_cv.notify_all();
  }
  impl.unlock_and_flush(lock);

  if (g) {
    /* EOF: the bridge stops subscriptions, pauses transfers and exits; jobs keep running. */
    if (!g->child->wait(grace_s)) {
      impl.note("the bridge did not exit within " + std::to_string(grace_s) + " s after EOF; terminating it");
      g->child->terminate();
      if (!g->child->wait(2.0)) {
        g->child->kill();
      }
    }
  }
  lock.lock();
  impl.stop_requested = true;
  impl.wake.notify_all();
  lock.unlock();
  if (impl.supervisor.joinable() && impl.supervisor.get_id() != std::this_thread::get_id()) {
    impl.supervisor.join();
  }
  lock.lock();
  impl.supervisor_running = false;
  /* The supervisor may have stopped before it saw the exit: reap here. */
  if (impl.gen) {
    std::shared_ptr<Impl::Generation> last = impl.gen;
    impl.handle_death_locked(lock, last);
  }
  for (auto it = impl.pending.begin(); it != impl.pending.end();) {
    Impl::Pending p = std::move(it->second);
    it = impl.pending.erase(it);
    impl.fail_pending_locked(p, Error::make(ErrorCode::ShuttingDown, "The bridge client closed"));
  }
  impl.set_state_locked(BridgeState::Stopped);
  impl.unlock_and_flush(lock);
}

BridgeState Client::state() const
{
  std::lock_guard lock(impl_->mutex);
  return impl_->state;
}

std::optional<Error> Client::last_error() const
{
  std::lock_guard lock(impl_->mutex);
  return impl_->last_error;
}

bool Client::wait_ready(const double timeout_s)
{
  std::unique_lock lock(impl_->mutex);
  impl_->state_cv.wait_for(lock, std::chrono::microseconds(int64_t(timeout_s * 1e6)), [&] {
    return impl_->state == BridgeState::Ready || impl_->state == BridgeState::Failed ||
           impl_->state == BridgeState::Stopped;
  });
  return impl_->state == BridgeState::Ready;
}

ListenerHandle Client::on_state(std::function<void(BridgeState, const std::optional<Error> &)> fn)
{
  std::lock_guard lock(impl_->mutex);
  const uint64_t id = impl_->next_listener++;
  impl_->state_listeners[id] = std::move(fn);
  std::weak_ptr<Impl> weak = impl_;
  return ListenerHandle([weak, id] {
    if (auto impl = weak.lock()) {
      std::lock_guard lock(impl->mutex);
      impl->state_listeners.erase(id);
    }
  });
}

std::optional<HelloInfo> Client::hello_info() const
{
  std::lock_guard lock(impl_->mutex);
  return impl_->hello;
}

int64_t Client::bridge_pid() const
{
  std::lock_guard lock(impl_->mutex);
  return impl_->gen && impl_->gen->child ? impl_->gen->child->pid() : 0;
}

ClientStats Client::stats() const
{
  std::lock_guard lock(impl_->mutex);
  return impl_->stats;
}

LogRing &Client::bridge_log()
{
  return impl_->log;
}

Future<Json> Client::call(std::string method, Json params, CallOptions options)
{
  return impl_->call(std::move(method), std::move(params), options);
}

ListenerHandle Client::on_event(std::string event, std::function<void(const std::string &, const Json &)> fn)
{
  std::lock_guard lock(impl_->mutex);
  const uint64_t id = impl_->next_listener++;
  impl_->event_listeners[id] = {std::move(event), std::move(fn)};
  std::weak_ptr<Impl> weak = impl_;
  return ListenerHandle([weak, id] {
    if (auto impl = weak.lock()) {
      std::lock_guard lock(impl->mutex);
      impl->event_listeners.erase(id);
    }
  });
}

ListenerHandle Client::on_transfer(std::function<void(const Transfer &)> fn)
{
  return on_event("transfer.updated", [fn = std::move(fn)](const std::string &, const Json &data) {
    if (data.is_object() && data.contains("transfer")) {
      fn(Transfer::from_json(data["transfer"]));
    }
  });
}

Subscription Client::subscribe(std::string method, Json params, std::shared_ptr<Subscription::State> state)
{
  state->method = std::move(method);
  state->base_params = std::move(params);
  state->client = impl_;
  std::unique_lock lock(impl_->mutex);
  if (impl_->closing || impl_->state == BridgeState::Failed || impl_->state == BridgeState::Stopped) {
    state->ended = true;
    const Error error = Error::make(ErrorCode::Unavailable, "The bridge is not running");
    std::shared_ptr<Subscription::State> s = state;
    impl_->deferred.push_back([impl = impl_.get(), s, error] {
      impl->post([s, error] {
        if (!s->closed.load()) {
          s->deliver_error(error, true);
        }
      });
    });
    impl_->unlock_and_flush(lock);
    return Subscription(state);
  }
  impl_->subs.insert(state);
  if (impl_->state == BridgeState::Ready) {
    impl_->subscribe_locked(state);
  }
  impl_->unlock_and_flush(lock);
  return Subscription(state);
}


Future<EvaluateResult> Client::graph_evaluate(const EvaluateParams &params,
                                              std::function<void(const GraphProgress &)> on_progress,
                                              CallOptions options)
{
  const std::string eval_id = params.eval_id;
  std::weak_ptr<Impl> weak = impl_;
  if (on_progress) {
    std::lock_guard lock(impl_->mutex);
    impl_->progress[eval_id] = std::move(on_progress);
  }
  Future<Json> raw = call("graph.evaluate", params.to_json(), options);
  /* Cancelling sends graph.cancel (hub mode: with connection and node, so the hub stops it too). */
  Target target;
  if (params.mode == "hub") {
    target = params.target;
  }
  raw.state()->add_cancel_hook([weak, eval_id, target] {
    auto impl = weak.lock();
    if (!impl) {
      return;
    }
    Json cancel = Json::object();
    cancel["eval_id"] = eval_id;
    if (!target.connection.empty()) {
      target.apply(cancel);
    }
    std::unique_lock lock(impl->mutex);
    if (impl->state == BridgeState::Ready) {
      impl->send_internal_locked("graph.cancel", cancel);
    }
    impl->unlock_and_flush(lock);
  });
  auto typed = std::make_shared<detail::FutureState<EvaluateResult>>(impl_->options.executor);
  std::weak_ptr<detail::FutureState<Json>> parent = raw.state();
  typed->add_cancel_hook([parent] {
    if (auto p = parent.lock()) {
      p->cancel();
    }
  });
  raw.state()->then(
      [weak, eval_id, typed](Result<Json> result) {
        if (auto impl = weak.lock()) {
          std::lock_guard lock(impl->mutex);
          impl->progress.erase(eval_id);
        }
        if (!result.ok()) {
          typed->complete(result.error());
          return;
        }
        try {
          typed->complete(EvaluateResult::from_json(result.value()));
        }
        catch (const std::exception &error) {
          typed->complete(Error::make(ErrorCode::InternalError, error.what()));
        }
      },
      true);
  return Future<EvaluateResult>(typed);
}

Subscription Client::subscribe_hub(const HubSubscribeParams &params, HubEventHandlers handlers)
{
  auto state = std::make_shared<Subscription::State>();
  state->kind = Subscription::State::Kind::Hub;
  state->hub = std::move(handlers);
  {
    std::lock_guard lock(state->m);
    state->hub_cursor = params.after;
  }
  return subscribe("hub.subscribe", params.to_json(), state);
}

Subscription Client::watch(const WatchParams &params, WatchHandlers handlers)
{
  auto state = std::make_shared<Subscription::State>();
  state->kind = Subscription::State::Kind::Watch;
  state->watch = std::move(handlers);
  return subscribe("watch", params.to_json(), state);
}

Subscription Client::subscribe_logs(const LogsParams &params, LogsHandlers handlers)
{
  auto state = std::make_shared<Subscription::State>();
  state->kind = Subscription::State::Kind::Logs;
  state->logs = std::move(handlers);
  {
    std::lock_guard lock(state->m);
    state->log_offsets = params.offsets;
  }
  return subscribe("logs.subscribe", params.to_json(), state);
}

Subscription Client::subscribe_events(const EventsParams &params, EventsHandlers handlers)
{
  auto state = std::make_shared<Subscription::State>();
  state->kind = Subscription::State::Kind::Events;
  state->events = std::move(handlers);
  {
    std::lock_guard lock(state->m);
    state->events_offset = params.offset;
  }
  return subscribe("events.subscribe", params.to_json(), state);
}

}  // namespace stk::bridge
