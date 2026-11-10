/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
class SimulationTarget;
struct EditorContext;

/** Explicit diagnostic actions with a bridge-owned durable journal; no project or Python edits. */
class SimulationPreflight {
 public:
  ~SimulationPreflight() { alive_.reset(); }
  void suspend();
  void draw(ui::Layout &panel, EditorContext &ctx, ProjectState &state, SimulationTarget &target,
            const std::string &connection, const io::Json &options, std::function<bool()> current);
 private:
  using Clock = std::chrono::steady_clock;
  using Current = std::function<bool()>;
  void request(EditorContext ctx, const std::string &method, const io::Json &params, Current current,
               std::function<void(const io::Json &)> receive);
  void accept_record(const io::Json &reply, const std::string &expected_id,
                     const EditorContext &ctx, const Current &current);
  bool active_ = false, describe_busy_ = false, spaces_busy_ = false, records_busy_ = false, action_busy_ = false;
  bool spaces_loaded_ = false, records_loaded_ = false, auto_poll_ = false;
  bool metadata_failed_ = false;
  uint64_t epoch_ = 0;
  std::string project_, connection_, identity_, workspace_, selected_, error_, created_request_;
  io::Json spaces_ = io::Json::array(), records_ = io::Json::array();
  Current previous_current_;
  Clock::time_point next_poll_{}, poll_deadline_{};
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
};
} // namespace stk::app
