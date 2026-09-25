/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/layout_math.hh"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace stk::wm {

/** Rounds non-negative float shares summing to `total` to integers with the same sum. */
static std::vector<int> round_largest_remainder(const std::vector<double> &want, const int total)
{
  const size_t n = want.size();
  std::vector<int> out(n);
  std::vector<double> rem(n);
  long sum = 0;
  for (size_t i = 0; i < n; i++) {
    const double w = std::max(0.0, want[i]);
    out[i] = int(std::floor(w + 1e-9));
    rem[i] = w - out[i];
    sum += out[i];
  }
  long left = long(total) - sum;
  std::vector<size_t> order(n);
  std::iota(order.begin(), order.end(), size_t(0));
  /* Largest remainder first; ties go to the earlier child (deterministic). */
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return rem[a] > rem[b] + 1e-9; });
  for (size_t k = 0; left > 0 && n > 0; k = (k + 1) % n) {
    out[order[k]]++;
    left--;
  }
  while (left < 0 && n > 0) {
    /* Only reachable through float noise: take pixels back from the largest child. */
    const size_t i = size_t(std::max_element(out.begin(), out.end()) - out.begin());
    out[i]--;
    left++;
  }
  return out;
}

std::vector<int> distribute_sizes(const int avail_in, const std::vector<float> &factors, const std::vector<int> &mins_in)
{
  const size_t n = factors.size();
  if (n == 0) {
    return {};
  }
  const int avail = std::max(0, avail_in);
  std::vector<double> f(n);
  std::vector<int> mins(n, 0);
  double fsum = 0.0;
  for (size_t i = 0; i < n; i++) {
    f[i] = (std::isfinite(factors[i]) && factors[i] > 0.0f) ? double(factors[i]) : 0.0;
    fsum += f[i];
    mins[i] = i < mins_in.size() ? std::max(0, mins_in[i]) : 0;
  }
  if (fsum <= 0.0) {
    std::fill(f.begin(), f.end(), 1.0);
    fsum = double(n);
  }
  const long min_sum = std::accumulate(mins.begin(), mins.end(), 0L);
  std::vector<double> want(n, 0.0);
  if (min_sum >= avail) {
    /* Not enough room for the minimums: shrink them proportionally. */
    for (size_t i = 0; i < n; i++) {
      want[i] = min_sum > 0 ? double(avail) * mins[i] / double(min_sum) : double(avail) / double(n);
    }
    return round_largest_remainder(want, avail);
  }
  std::vector<bool> pinned(n, false);
  for (size_t iter = 0; iter <= n; iter++) {
    double free = double(avail);
    double free_f = 0.0;
    for (size_t i = 0; i < n; i++) {
      if (pinned[i]) {
        free -= mins[i];
      }
      else {
        free_f += f[i];
      }
    }
    bool violated = false;
    for (size_t i = 0; i < n; i++) {
      if (pinned[i]) {
        want[i] = mins[i];
        continue;
      }
      want[i] = free_f > 0.0 ? free * f[i] / free_f : 0.0;
    }
    for (size_t i = 0; i < n; i++) {
      if (!pinned[i] && want[i] < double(mins[i]) - 1e-9) {
        pinned[i] = true;
        violated = true;
      }
    }
    if (!violated) {
      break;
    }
    if (std::all_of(pinned.begin(), pinned.end(), [](bool p) { return p; })) {
      /* Everything pinned yet room left (only when all factors of the rest were 0). */
      for (size_t i = 0; i < n; i++) {
        want[i] = mins[i];
      }
      want[n - 1] += double(avail - min_sum);
      break;
    }
  }
  std::vector<int> out = round_largest_remainder(want, avail);
  /* Rounding cannot take a child below an integer minimum it had in floating point, but guard
   * against float noise anyway by moving pixels from the largest child. */
  for (size_t i = 0; i < n; i++) {
    while (out[i] < mins[i]) {
      size_t donor = n;
      for (size_t j = 0; j < n; j++) {
        if (j != i && out[j] > mins[j] && (donor == n || out[j] - mins[j] > out[donor] - mins[donor])) {
          donor = j;
        }
      }
      if (donor == n) {
        break;
      }
      out[donor]--;
      out[i]++;
    }
  }
  return out;
}

int clamp_pair(const int total, const int want_a, const int min_a, const int min_b)
{
  if (total <= 0) {
    return 0;
  }
  if (min_a + min_b > total) {
    /* Cannot satisfy both: share the pixels in proportion to the minimums. */
    const int s = min_a + min_b;
    return s > 0 ? int(std::lround(double(total) * min_a / s)) : total / 2;
  }
  return std::clamp(want_a, min_a, total - min_b);
}

}  // namespace stk::wm
