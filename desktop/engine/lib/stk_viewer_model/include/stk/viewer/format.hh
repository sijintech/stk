/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Number formatting of overlay labels (spec §6.7 scalar_bar `format`): the Python format-spec subset
 * `[sign][#][0][width][,][.precision][e E f F g G %]` and `[sign][#][0][width][,]d`, exactly as
 * suan.render.payload.format_label (the offscreen renderer) and web/src/colormaps.ts formatNumber:
 *
 *  - ties round half to even on the exact binary value (the exact decimal expansion of the double);
 *  - `d` formats the value rounded to the nearest integer, ties to even (Python round());
 *  - a label that shows zero never carries a minus sign (-0.0001 with `.2f` is "0.00");
 *  - non-finite values print as inf / -inf / nan (also with `d`);
 *  - formats outside the subset fall back to `.3g`. */

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::viewer {

/** Parsed label format; nullopt when outside the subset. */
struct LabelFormat {
  char sign = '-'; /* '-', '+' or ' ' */
  bool alternate = false;
  bool zero_pad = false;
  int width = 0;
  bool grouping = false;
  int precision = -1; /* -1: default */
  char type = 0;      /* 0 (none), e E f F g G % d */
};
std::optional<LabelFormat> parse_label_format(std::string_view spec);

/** A scalar-bar label: `value` formatted with `spec` (see above). */
std::string format_label(double value, std::string_view spec = ".3g");

struct ScalarBarTick {
  double fraction; /* 0 at the low end, 1 at the high end */
  double value;
  std::string label;
};
/** `count` (clamped to 2..20) evenly spaced labels from lo to hi (web Legend.tsx ScalarBar, offscreen). */
std::vector<ScalarBarTick> scalar_bar_ticks(double lo, double hi, int count = 5, std::string_view spec = ".3g");

}  // namespace stk::viewer
