/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include "path_picker.hh"
#include "simulation_target.hh"
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace stk::ui { class Layout; }
namespace stk::app {
class ProjectState;
struct EditorContext;

/** Native controls call the shared built-in MuFerro/LAMMPS workflows. */
class ProjectSimulationView {
 public:
  void draw(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
  void draw_batches(ui::Layout &layout, EditorContext &ctx, ProjectState &state);
 private:
  void sync_project(ProjectState &state);
  void select_engine(int index);
  bool context_current(const ProjectState &state, const std::string &project, const std::string &handle, uint64_t generation) const;
  SimulationTarget target_;
  SimulationTarget lammps_target_;
  int engine_ = 0;
  uint64_t generation_ = 0;
  std::string source_;
  std::string script_;
  std::string project_, handle_, observed_table_, error_;
  PathPicker source_picker_;
  std::vector<std::string> batch_selection_;
  std::string batch_id_, batch_member_;
  bool show_archived_batches_ = false;  // the saved batches show only archived ones
};
}  // namespace stk::app
