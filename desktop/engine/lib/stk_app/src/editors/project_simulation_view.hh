/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include "path_picker.hh"
#include <optional>
#include <string>
#include <vector>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

/** Native controls call the same bundled Python workflow available as stk.muferro. */
class ProjectSimulationView {
 public:
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
  void draw_batches(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
 private:
  /** Runtime picker (direct or SSH Runtime profiles; choosing one makes it the active connection).
   * Returns the active Runtime's id when it is one of them and not offline, else "". */
  std::string runtime_controls(ui::Layout &panel, EditorContext &ctx);
  /** Execution options as fields over the shared JSON object, with the raw JSON folded away.
   * Returns the options to send, or nullopt (with the reason shown) when they cannot be used. */
  std::optional<io::Json> options_controls(ui::Layout &panel, EditorContext &ctx);
  std::string source_, options_ = R"({"backend":"local","ranks":1,"threads_per_rank":1})";
  std::string project_, error_;
  PathPicker source_picker_;
  std::vector<std::string> batch_selection_;
  std::string batch_id_, batch_member_;
};
}  // namespace stk::app
