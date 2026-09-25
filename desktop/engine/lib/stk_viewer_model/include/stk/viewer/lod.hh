/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Level-of-detail policy of the viewer (spec §6.1 `lods`, §6.4/§6.5 `progressive`, §6.6 volume
 * `lods`, §7 budgets). Payload producers already enforce the profile budget; the client additionally
 * keeps interaction smooth: while the camera moves it draws coarser triangle/volume levels, a prefix
 * of shuffled instances/points and larger ray-march steps, then refines when the view settles. A
 * quality scale adapts to the measured frame time (multiplicative decrease, slow recovery). */

#include <cstddef>
#include <cstdint>
#include <span>

namespace stk::viewer {

struct LodBudget {
  /* spec §7 "desktop" profile */
  uint64_t triangles = 20'000'000;
  uint64_t instances = 5'000'000;
  uint64_t points = 20'000'000;
  uint64_t voxels = uint64_t(1024) * 1024 * 1024;
  /* budgets while interacting (camera moving) */
  uint64_t interactive_triangles = 2'000'000;
  uint64_t interactive_instances = 500'000;
  uint64_t interactive_points = 2'000'000;
  uint64_t interactive_voxels = uint64_t(256) * 256 * 256;
};

class LodPolicy {
 public:
  explicit LodPolicy(LodBudget budget = {}, double target_frame_ms = 1000.0 / 60.0);

  /** Report the GPU time of the last frame; adapts quality() in [min_quality, 1]. */
  void report_frame(double milliseconds);
  double quality() const
  {
    return quality_;
  }
  void set_interacting(bool interacting)
  {
    interacting_ = interacting;
  }
  bool interacting() const
  {
    return interacting_;
  }

  /**
   * Triangle level to draw: `levels` are the triangle counts ordered coarse to fine, the last one
   * being the full mesh (payload `lods` + main arrays). Returns the finest index within the budget
   * (0 when even the coarsest exceeds it).
   */
  size_t triangle_level(std::span<const uint64_t> levels) const;
  /** Voxel level (coarse to fine, last = full data), as triangle_level. */
  size_t volume_level(std::span<const uint64_t> voxels) const;
  /** Number of instances/points to draw from a shuffled (progressive) layer: a prefix within budget;
   * layers that are not shuffled are drawn completely. */
  uint64_t instance_prefix(uint64_t total, bool shuffled) const;
  uint64_t point_prefix(uint64_t total, bool shuffled) const;
  /** Ray-march step in units of the smallest spacing (0.5 when idle, as vtk.js sampleDistance). */
  double volume_step() const;

 private:
  uint64_t scaled(uint64_t full, uint64_t interactive) const;

  LodBudget budget_;
  double target_ms_;
  double quality_ = 1.0;
  bool interacting_ = false;
};

}  // namespace stk::viewer
