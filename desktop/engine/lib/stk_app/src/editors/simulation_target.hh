/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include <optional>
#include <string>

namespace stk::ui { class Layout; }
namespace stk::app {
struct EditorContext;

/** Where a simulation runs: a saved direct or SSH Runtime profile and the muferro_spec execution options,
 * shared by the simulation batch panel and the workflow run panel. */
class SimulationTarget {
 public:
  /** Runtime picker (choosing one makes it the active connection). Returns the active Runtime's id when
   * it is a direct/SSH profile and not offline, else "". */
  std::string runtime_controls(ui::Layout &panel, EditorContext &ctx);
  /** Execution options as fields over one JSON object, with the raw JSON folded away. Returns the options
   * to send, or nullopt (with the reason shown) when they cannot be used. */
  std::optional<io::Json> options_controls(ui::Layout &panel, EditorContext &ctx);
  /** The profile's display name, or its id without the "runtime:" prefix. */
  static std::string runtime_name(EditorContext &ctx, const std::string &connection);

 private:
  std::string options_ = R"({"backend":"local","ranks":1,"threads_per_rank":1})";
};
}  // namespace stk::app
