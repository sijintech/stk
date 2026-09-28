/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
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
  std::string source_, options_ = R"({"backend":"local","ranks":1,"threads_per_rank":1})";
  std::string project_, error_;
  std::vector<std::string> batch_selection_;
  std::string batch_id_, batch_member_;
};
}  // namespace stk::app
