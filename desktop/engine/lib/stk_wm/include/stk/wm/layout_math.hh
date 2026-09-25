/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Integer layout arithmetic of the screen tree (no GHOST / GPU; unit tested).
 */
#pragma once

#include <vector>

namespace stk::wm {

/**
 * Splits `avail` pixels between children by `factors` (normalized; non-positive or non-finite
 * factors count as 0, all-zero means equal shares) while giving each child at least `mins[i]`.
 * Children below their minimum are pinned to it and the rest is shared by the others in
 * proportion to their factors. When the minimums alone exceed `avail`, the pixels are shared in
 * proportion to the minimums. Rounding uses the largest-remainder method, so the result always
 * sums to `avail` (for avail >= 0) and never drops below a satisfiable minimum.
 */
std::vector<int> distribute_sizes(int avail, const std::vector<float> &factors, const std::vector<int> &mins);

/**
 * New sizes of the pair (a, b) when a is resized to `want_a`: the pair keeps its total, and both
 * keep their minimums when possible. Returns the size given to a.
 */
int clamp_pair(int total, int want_a, int min_a, int min_b);

}  // namespace stk::wm
