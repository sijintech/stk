/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Number formatting of overlay labels (spec §6.7 scalar_bar `format`): the Python/d3 format subset
 * `[sign][#][0][width][,][.precision][e E f F g G %]` and `[sign][#][0][width][,]d`.
 *
 *  - format_label(): the reference, exactly what suan/render/offscreen.py draws: Python format(),
 *    with `d` applied to the value rounded half-to-even (Python round()).
 *  - format_number_web(): exactly web/src/colormaps.ts formatNumber (the web legend), which supports
 *    only `.Nf`, `.Ne`, `.Ng`, `.N%`, `d` (others fall back to `.3g`) and rounds ties away from zero
 *    (JavaScript toFixed/toExponential/toPrecision, Math.round).
 *
 * Both work from the exact decimal expansion of the double, so ties are decided exactly. */

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

/** Python format(value, spec) for a float and a spec of the subset (ints for `d`); throws
 * std::invalid_argument for other specs. */
std::string format_python(double value, std::string_view spec);
/** offscreen.py _label: `d` rounds half-to-even first, everything else is format_python. */
std::string format_label(double value, std::string_view spec = ".3g");
/** web/src/colormaps.ts formatNumber. */
std::string format_number_web(double value, std::string_view spec = ".3g");

struct ScalarBarTick {
  double fraction; /* 0 at the low end, 1 at the high end */
  double value;
  std::string label;
};
/** `count` (clamped to 2..20) evenly spaced labels from lo to hi (web Legend.tsx ScalarBar). */
std::vector<ScalarBarTick> scalar_bar_ticks(double lo, double hi, int count = 5, std::string_view spec = ".3g",
                                            bool web_format = false);

}  // namespace stk::viewer
