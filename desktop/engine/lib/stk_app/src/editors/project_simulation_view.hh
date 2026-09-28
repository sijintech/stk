/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include <string>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

/** Native controls call the same bundled Python workflow available as stk.muferro. */
class ProjectSimulationView {
 public:
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
 private:
  std::string source_, options_ = R"({"backend":"local","ranks":1,"threads_per_rank":1})";
  std::string project_, error_;
};
}  // namespace stk::app
