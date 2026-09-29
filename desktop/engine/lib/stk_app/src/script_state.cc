/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/script_state.hh"

#include <algorithm>

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

namespace stk::app {
using io::Json;

ScriptState::ScriptState(AppStore &store) : store_(store) {}

ScriptState::~ScriptState()
{
  alive_.reset();
  state_listener_.reset();
  changed_listener_.reset();
  ui_listener_.reset();
}

template<class F> void ScriptState::on(bridge::Future<Json> future, F fn)
{
  std::weak_ptr<bool> weak = alive_;
  const uint64_t epoch = epoch_;
  future.then([this, weak, epoch, fn = std::move(fn)](bridge::Result<Json> result) mutable {
    if (weak.lock() && epoch == epoch_) {
      fn(result);
    }
  });
}

void ScriptState::sync()
{
  if (client_ != store_.bridge()) {
    attach(store_.bridge());
  }
}

void ScriptState::attach(bridge::Client *client)
{
  if (client == client_) {
    return;
  }
  state_listener_.reset();
  changed_listener_.reset();
  ui_listener_.reset();
  client_ = client;
  bridge_state_ = bridge::BridgeState::Stopped;
  on_state(bridge::BridgeState::Stopped);
  if (!client_) {
    return;
  }
  std::weak_ptr<bool> weak = alive_;
  state_listener_ = client_->on_state([this, weak](auto state, const auto &) {
    if (weak.lock()) {
      on_state(state);
    }
  });
  changed_listener_ = client_->on_event("script.changed", [this, weak](const auto &, const Json &data) {
    if (weak.lock() && !session_.empty() && io::get_string(data, "session") == session_) {
      dirty_ = true;
      refresh();
    }
  });
  ui_listener_ = client_->on_event("ui.request", [this, weak](const auto &, const Json &data) {
    if (weak.lock()) {
      ui_request(data);
    }
  });
  on_state(client_->state());
}

void ScriptState::on_state(const bridge::BridgeState state)
{
  bridge_state_ = state;
  if (state != bridge::BridgeState::Ready) {
    ++epoch_;
    if (!session_.empty()) {
      append("\n" + std::string(store_.tr("script.session_reset")) + "\n");
    }
    session_.clear();
    ui_session_.clear();
    awaiting_run_.clear();
    status_ = Json::object();
    cursor_ = 0;
    opening_ = starting_ = reading_ = dirty_ = interrupting_ = ui_attaching_ = false;
  }
  else if (client_ && session_.empty() && !opening_) {
    const auto hello = client_->hello_info();
    if (!hello || !hello->has_method("script.open")) {
      store_.changed();
      return;
    }
    attach_ui();
    opening_ = true;
    on(client_->call("script.open"), [this](const auto &result) {
      opening_ = false;
      if (!result.ok()) {
        fail(result.error());
        return;
      }
      session_ = io::get_string(result.value(), "session");
      status_ = result.value();
      error_.clear();
      cursor_ = 0;
      refresh();
    });
  }
  store_.changed();
}

bool ScriptState::ready() const
{
  return client_ && bridge_state_ == bridge::BridgeState::Ready && !session_.empty();
}

bool ScriptState::busy() const
{
  const auto state = io::get_string(status_, "state");
  return opening_ || starting_ || interrupting_ || state == "running" || state == "stopping";
}

void ScriptState::fail(const bridge::Error &error)
{
  error_ = error.describe();
  store_.changed();
}

void ScriptState::append(const std::string_view text)
{
  raw_output_.append(text);
  if (raw_output_.size() > (1 << 20)) {
    /* LogBuffer bounds lines, not an endless line. Bound bytes here as well, retaining a tail
     * on a UTF-8 boundary and amortizing rebuilding under large output floods. */
    size_t cut = raw_output_.size() - (1 << 19);
    while (cut < raw_output_.size() && (uint8_t(raw_output_[cut]) & 0xc0) == 0x80) {
      ++cut;
    }
    raw_output_.erase(0, cut);
    output_.clear();
    output_.append(raw_output_);
  }
  else {
    output_.append(text);
  }
}

void ScriptState::clear_output()
{
  raw_output_.clear();
  output_.clear();
  store_.changed();
}

void ScriptState::refresh()
{
  if (!ready()) {
    return;
  }
  if (reading_) {
    dirty_ = true;
    return;
  }
  reading_ = true;
  dirty_ = false;
  on(client_->call("script.read", {{"session", session_}, {"cursor", cursor_}}), [this](const auto &result) {
    reading_ = false;
    if (!result.ok()) {
      fail(result.error());
      return;
    }
    status_ = result.value();
    cursor_ = io::get_int(status_, "cursor", cursor_);
    if (io::get_bool(status_, "truncated", false)) {
      append("\n" + std::string(store_.tr("script.output_truncated")) + "\n");
    }
    append(io::get_string(status_, "text"));
    const auto run = status_.find("run");
    if (run != status_.end() && run->is_object() && !awaiting_run_.empty() &&
        io::get_string(*run, "id") == awaiting_run_) {
      awaiting_run_.clear();
      starting_ = false;
    }
    if (run != status_.end() && run->is_object() && run->contains("error") && (*run)["error"].is_object()) {
      const auto id = io::get_string(*run, "id");
      if (id != reported_error_) {
        reported_error_ = id;
        append(bridge::Error::from_json((*run)["error"]).describe() + "\n");
      }
    }
    store_.changed();
    if (dirty_ || cursor_ < io::get_int(status_, "output_end", cursor_)) {
      refresh();
    }
  });
}

bool ScriptState::start(Json params)
{
  sync();
  if (!ready() || busy()) {
    return false;
  }
  params["session"] = session_;
  auto &project = store_.project();
  project.sync();
  if (project.project() && !project.project()->handle.empty()) {
    params["project_handle"] = project.project()->handle;
  }
  starting_ = true;
  error_.clear();
  on(client_->call("script.execute", std::move(params)), [this](const auto &result) {
    if (!result.ok()) {
      starting_ = false;
      fail(result.error());
    }
    else {
      /* An event read might already know that this run finished: do not overwrite it with a
       * stale running flag. A new read establishes the current state. */
      awaiting_run_ = io::get_string(result.value(), "run");
      refresh();
    }
    store_.changed();
  });
  store_.changed();
  return true;
}

bool ScriptState::execute(const std::string &source)
{
  if (!start({{"source", source}})) {
    return false;
  }
  if (history_.empty() || history_.back() != source) {
    history_.push_back(source);
    if (history_.size() > 100) {
      history_.erase(history_.begin());
    }
  }
  return true;
}

bool ScriptState::execute_file(const std::string &path)
{
  return start({{"path", path}});
}

bool ScriptState::interrupt()
{
  if (!ready() || interrupting_) {
    return false;
  }
  interrupting_ = true;
  on(client_->call("script.interrupt", {{"session", session_}}), [this](const auto &result) {
    interrupting_ = false;
    if (!result.ok()) {
      fail(result.error());
    }
    refresh();
  });
  store_.changed();
  return true;
}

void ScriptState::set_ui_handler(UIHandler handler)
{
  ui_handler_ = std::move(handler);
  if (ui_handler_) {
    attach_ui();
  }
}

void ScriptState::attach_ui()
{
  if (!client_ || bridge_state_ != bridge::BridgeState::Ready || !ui_handler_ || !ui_session_.empty() || ui_attaching_) {
    return;
  }
  const auto hello = client_->hello_info();
  if (!hello || !hello->has_method("ui.attach")) { return; }
  ui_attaching_ = true;
  const auto attach = [this](const Json &advertised) {
    if (!ui_handler_) { ui_attaching_ = false; return; }
    Json operations = Json::array();
    for (const auto *name : {"layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close", "project.review",
                             "viewer.status", "viewer.presets", "viewer.open", "viewer.close", "viewer.configure", "viewer.preset",
                             "viewer.evaluate", "viewer.cancel", "viewer.layer", "viewer.step", "viewer.play", "viewer.reset_camera"}) {
      if (std::find(advertised.begin(), advertised.end(), Json(name)) != advertised.end()) { operations.push_back(name); }
    }
    on(client_->call("ui.attach", {{"operations", operations}}), [this](const auto &result) {
      ui_attaching_ = false;
      if (result.ok()) { ui_session_ = io::get_string(result.value(), "session"); }
      else { fail(result.error()); }
      store_.changed();
    });
  };
  if (!hello->has_method("script.catalog")) {
    attach(Json::array({"layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close"}));
    return;
  }
  // Older bridges advertise the original six operations. Do not let a new UI capability
  // make their whole desktop attachment fail validation.
  on(client_->call("script.catalog"), [this, attach](const auto &result) {
    if (!result.ok()) { ui_attaching_ = false; fail(result.error()); return; }
    attach(result.value().at("ui_operations"));
  });
}

void ScriptState::ui_request(const Json &data)
{
  if (!client_ || ui_session_.empty() || io::get_string(data, "session") != ui_session_) {
    return;
  }
  const auto request = io::get_string(data, "request"), session = ui_session_;
  std::weak_ptr<bool> weak = alive_;
  const auto epoch = epoch_;
  Completion reply = [this, weak, epoch, request, session](bridge::Result<Json> result) {
    if (!weak.lock() || epoch != epoch_ || !client_ || session != ui_session_) {
      return;
    }
    Json params = {{"session", session}, {"request", request}};
    params[result.ok() ? "result" : "error"] = result.ok() ? result.value() : result.error().to_json();
    client_->call("ui.reply", std::move(params));
  };
  if (!ui_handler_) {
    reply(bridge::Error::make(bridge::ErrorCode::Unavailable, "No desktop executor is attached"));
    return;
  }
  ui_handler_(io::get_string(data, "operation"), data.at("params"), io::get_int(data, "expires_at_ms", 0),
              [this, weak, epoch, session] {
                return weak.lock() && epoch == epoch_ && client_ && session == ui_session_;
              },
              std::move(reply));
}

}  // namespace stk::app
