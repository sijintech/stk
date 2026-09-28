/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/bridge/client.hh"
#include "stk/ui/log_buffer.hh"

namespace stk::app {

class AppStore;

/** Shared Python session and local desktop executor binding. Main thread only. No source is
 * replayed on bridge restart, and closing a console area does not end its worker. */
class ScriptState {
 public:
  using Completion = std::function<void(bridge::Result<io::Json>)>;
  using UIHandler = std::function<void(const std::string &, const io::Json &, int64_t,
                                        std::function<bool()>, Completion)>;

  explicit ScriptState(AppStore &store);
  ~ScriptState();
  void sync();
  void attach(bridge::Client *client);
  void set_ui_handler(UIHandler handler);
  bool ready() const;
  bool busy() const;
  bool desktop_ready() const { return !ui_session_.empty(); }
  const std::string &session() const { return session_; }
  const io::Json &status() const { return status_; }
  const std::string &error() const { return error_; }
  const ui::LogBuffer &output() const { return output_; }
  const std::vector<std::string> &history() const { return history_; }

  bool execute(const std::string &source);
  bool execute_file(const std::string &path);
  bool interrupt();
  void refresh();
  void clear_output();

 private:
  template<class F> void on(bridge::Future<io::Json> future, F fn);
  void on_state(bridge::BridgeState state);
  void attach_ui();
  void ui_request(const io::Json &data);
  bool start(io::Json params);
  void append(std::string_view text);
  void fail(const bridge::Error &error);

  AppStore &store_;
  bridge::Client *client_ = nullptr;
  bridge::BridgeState bridge_state_ = bridge::BridgeState::Stopped;
  bridge::ListenerHandle state_listener_, changed_listener_, ui_listener_;
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  uint64_t epoch_ = 0;
  std::string session_, ui_session_, error_, reported_error_, raw_output_, awaiting_run_;
  int64_t cursor_ = 0;
  bool opening_ = false, starting_ = false, reading_ = false, dirty_ = false, interrupting_ = false, ui_attaching_ = false;
  io::Json status_ = io::Json::object();
  ui::LogBuffer output_{10000};
  std::vector<std::string> history_;
  UIHandler ui_handler_;
};

}  // namespace stk::app
