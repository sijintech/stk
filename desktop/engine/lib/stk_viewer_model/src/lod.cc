/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/lod.hh"

#include <algorithm>
#include <cmath>

namespace stk::viewer {

namespace {
constexpr double kMinQuality = 0.05;
}

LodPolicy::LodPolicy(LodBudget budget, double target_frame_ms) : budget_(budget), target_ms_(target_frame_ms) {}

void LodPolicy::report_frame(double ms)
{
  if (!(ms >= 0) || !std::isfinite(ms)) {
    return;
  }
  if (ms > target_ms_ * 1.25) {
    /* Too slow: scale the work down proportionally (never below kMinQuality). */
    quality_ = std::max(kMinQuality, quality_ * std::max(0.5, target_ms_ / ms));
  }
  else if (ms < target_ms_ * 0.6) {
    quality_ = std::min(1.0, quality_ * 1.1);
  }
}

uint64_t LodPolicy::scaled(uint64_t full, uint64_t interactive) const
{
  const uint64_t base = interacting_ ? std::min(full, interactive) : full;
  return std::max<uint64_t>(1, uint64_t(double(base) * quality_));
}

size_t LodPolicy::triangle_level(std::span<const uint64_t> levels) const
{
  if (levels.empty()) {
    return 0;
  }
  const uint64_t budget = scaled(budget_.triangles, budget_.interactive_triangles);
  size_t best = 0;
  for (size_t i = 0; i < levels.size(); i++) {
    if (levels[i] <= budget) {
      best = i;
    }
  }
  return best;
}

size_t LodPolicy::volume_level(std::span<const uint64_t> voxels) const
{
  if (voxels.empty()) {
    return 0;
  }
  const uint64_t budget = scaled(budget_.voxels, budget_.interactive_voxels);
  size_t best = 0;
  for (size_t i = 0; i < voxels.size(); i++) {
    if (voxels[i] <= budget) {
      best = i;
    }
  }
  return best;
}

uint64_t LodPolicy::instance_prefix(uint64_t total, bool shuffled) const
{
  return shuffled ? std::min(total, scaled(budget_.instances, budget_.interactive_instances)) : total;
}

uint64_t LodPolicy::point_prefix(uint64_t total, bool shuffled) const
{
  return shuffled ? std::min(total, scaled(budget_.points, budget_.interactive_points)) : total;
}

double LodPolicy::volume_step() const
{
  const double base = interacting_ ? 1.5 : 0.5;
  return std::min(4.0, base / std::sqrt(std::max(quality_, kMinQuality)));
}

}  // namespace stk::viewer
