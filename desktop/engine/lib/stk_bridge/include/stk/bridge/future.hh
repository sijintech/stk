/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Result<T> (a value or a protocol Error) and Future<T>, the handle of one bridge call.
 *
 *   client.task_get({"runtime:cluster"}, id).then([](Result<Json> r) {
 *     if (r) show(r.value()); else toast(r.error().message);   // on the main loop
 *   });
 *
 * Continuations run on the client's executor (the main loop, see stk::wm::WindowManager::executor),
 * never while a client lock is held. A future completes exactly once: with the bridge's response,
 * or locally with `timeout`, `cancelled`, `unavailable` (restart) or `shutting_down`.
 */
#pragma once

#include <chrono>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#include "stk/bridge/protocol.hh"

namespace stk::bridge {

/** Runs a task somewhere (main loop post); empty = run inline on the calling thread. */
using Executor = std::function<void(std::function<void()>)>;

template<typename T> class Result {
 public:
  using value_type = T;
  Result(T value) : v_(std::in_place_index<0>, std::move(value)) {}
  Result(Error error) : v_(std::in_place_index<1>, std::move(error)) {}

  bool ok() const
  {
    return v_.index() == 0;
  }
  explicit operator bool() const
  {
    return ok();
  }
  /** The value; throws BridgeException on an error result. */
  const T &value() const &
  {
    check();
    return std::get<0>(v_);
  }
  T &value() &
  {
    check();
    return std::get<0>(v_);
  }
  T &&value() &&
  {
    check();
    return std::get<0>(std::move(v_));
  }
  /** The error (only valid when !ok()). */
  const Error &error() const
  {
    return std::get<1>(v_);
  }

 private:
  void check() const
  {
    if (v_.index() != 0) {
      throw BridgeException(std::get<1>(v_));
    }
  }
  std::variant<T, Error> v_;
};

namespace detail {

template<typename T> class FutureState : public std::enable_shared_from_this<FutureState<T>> {
 public:
  explicit FutureState(Executor executor) : executor_(std::move(executor)) {}

  /** First completion wins; false when the future was already complete. */
  bool complete(Result<T> result)
  {
    std::function<void(Result<T>)> continuation;
    bool inline_continuation = false;
    {
      std::lock_guard lock(mutex_);
      if (result_) {
        return false;
      }
      result_.emplace(std::move(result));
      continuation = std::move(continuation_);
      inline_continuation = inline_;
      cancel_hooks_.clear();
    }
    cv_.notify_all();
    if (continuation) {
      run(std::move(continuation), inline_continuation);
    }
    return true;
  }

  bool ready()
  {
    std::lock_guard lock(mutex_);
    return result_.has_value();
  }

  Result<T> get()
  {
    std::unique_lock lock(mutex_);
    cv_.wait(lock, [this] { return result_.has_value(); });
    return *result_;
  }

  std::optional<Result<T>> wait_for(std::chrono::milliseconds timeout)
  {
    std::unique_lock lock(mutex_);
    if (!cv_.wait_for(lock, timeout, [this] { return result_.has_value(); })) {
      return std::nullopt;
    }
    return *result_;
  }

  /** `inline_run`: run on the completing thread (internal chaining), else on the executor. */
  void then(std::function<void(Result<T>)> fn, bool inline_run = false)
  {
    {
      std::lock_guard lock(mutex_);
      if (!result_) {
        continuation_ = std::move(fn);
        inline_ = inline_run;
        return;
      }
    }
    run(std::move(fn), inline_run);
  }

  /** Hooks run (once, outside locks, in order) by cancel() while the future is pending. */
  void add_cancel_hook(std::function<void()> hook)
  {
    std::lock_guard lock(mutex_);
    if (!result_) {
      cancel_hooks_.push_back(std::move(hook));
    }
  }

  void cancel()
  {
    std::vector<std::function<void()>> hooks;
    {
      std::lock_guard lock(mutex_);
      if (result_) {
        return;
      }
      hooks.swap(cancel_hooks_);
    }
    complete(Error::make(ErrorCode::Cancelled, "The call was cancelled by the client"));
    for (auto &hook : hooks) {
      hook();
    }
  }

  const Executor &executor() const
  {
    return executor_;
  }

 private:
  /** Runs `fn(stored result)` inline or on the executor. */
  void run(std::function<void(Result<T>)> fn, bool inline_run)
  {
    std::shared_ptr<FutureState> self = this->shared_from_this();
    auto task = [self, fn = std::move(fn)]() mutable {
      std::optional<Result<T>> result;
      {
        std::lock_guard lock(self->mutex_);
        result = self->result_;
      }
      fn(std::move(*result));
    };
    if (inline_run || !executor_) {
      task();
    }
    else {
      executor_(std::move(task));
    }
  }

  Executor executor_;
  std::mutex mutex_;
  std::condition_variable cv_;
  std::optional<Result<T>> result_;
  std::function<void(Result<T>)> continuation_;
  bool inline_ = false;
  std::vector<std::function<void()>> cancel_hooks_;
};

}  // namespace detail

template<typename T> class Future {
 public:
  using State = detail::FutureState<T>;
  Future() = default;
  explicit Future(std::shared_ptr<State> state) : state_(std::move(state)) {}

  bool valid() const
  {
    return state_ != nullptr;
  }
  bool ready() const
  {
    return state_ && state_->ready();
  }
  /** Blocks until the result is known. Never call it on the main loop thread when the client
   * delivers to that loop and the call waits on work posted there. */
  Result<T> get() const
  {
    return state_->get();
  }
  std::optional<Result<T>> wait_for(std::chrono::milliseconds timeout) const
  {
    return state_->wait_for(timeout);
  }
  /** `fn(result)` once known, on the client's executor. One continuation per future. */
  const Future &then(std::function<void(Result<T>)> fn) const
  {
    state_->then(std::move(fn));
    return *this;
  }
  /**
   * Completes the future with a local `cancelled` error now; a late response is dropped.
   * The protocol has no request cancellation (§3): calls with their own cancel method send it
   * (graph.evaluate -> graph.cancel {eval_id}); other calls still run to completion in the bridge.
   */
  void cancel() const
  {
    if (state_) {
      state_->cancel();
    }
  }

  /** A future of `fn(value)`; errors pass through, an exception from `fn` becomes internal_error.
   * Cancelling the mapped future cancels this one. */
  template<typename F> auto map(F fn) const -> Future<std::invoke_result_t<F, const T &>>
  {
    using U = std::invoke_result_t<F, const T &>;
    auto next = std::make_shared<detail::FutureState<U>>(state_->executor());
    std::weak_ptr<State> parent = state_;
    next->add_cancel_hook([parent] {
      if (auto p = parent.lock()) {
        p->cancel();
      }
    });
    state_->then(
        [next, fn = std::move(fn)](Result<T> result) mutable {
          if (!result.ok()) {
            next->complete(result.error());
            return;
          }
          try {
            next->complete(Result<U>(fn(result.value())));
          }
          catch (const BridgeException &error) {
            next->complete(error.error());
          }
          catch (const std::exception &error) {
            next->complete(Error::make(ErrorCode::InternalError,
                                       std::string("Unexpected result from the bridge: ") + error.what()));
          }
        },
        true);
    return Future<U>(next);
  }

  const std::shared_ptr<State> &state() const
  {
    return state_;
  }

 private:
  std::shared_ptr<State> state_;
};

/** A ready future (tests, local failures). */
template<typename T> Future<T> make_ready_future(Result<T> result, Executor executor = {})
{
  auto state = std::make_shared<detail::FutureState<T>>(std::move(executor));
  state->complete(std::move(result));
  return Future<T>(state);
}

}  // namespace stk::bridge
