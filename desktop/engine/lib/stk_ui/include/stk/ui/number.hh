/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Number field model: limits, display formatting (fixed or scientific) and parsing of typed
 * values (scientific notation, full-width digits from CJK input methods, unit suffix and simple
 * arithmetic such as "1/3" or "2*pi").
 */
#pragma once

#include <limits>
#include <optional>
#include <string>
#include <string_view>

namespace stk::ui {

struct NumberProps {
  /** Hard limits: values are always clamped to these. */
  double min = -std::numeric_limits<double>::infinity();
  double max = std::numeric_limits<double>::infinity();
  /** JSON Schema exclusiveMinimum/exclusiveMaximum semantics for `min`/`max`. */
  bool exclusive_min = false;
  bool exclusive_max = false;
  /** Soft limits: slider range and the natural drag range. NaN = use the hard limit. */
  double soft_min = std::numeric_limits<double>::quiet_NaN();
  double soft_max = std::numeric_limits<double>::quiet_NaN();
  /** Arrow-click increment; dragging moves one step per step_px (UI units, scaled). */
  double step = 0.1;
  /** Decimals shown (ignored for integers). */
  int precision = 3;
  bool integer = false;
  /** Display suffix (already localized), also accepted after typed values. */
  std::string unit;

  double soft_lo() const;
  double soft_hi() const;
};

/** Clamps to the hard limits; exclusive limits keep one display quantum inside. */
double clamp_number(double v, const NumberProps &props);

/**
 * Display text: integers as-is; floats with `precision` decimals, switching to scientific notation
 * ("1.000e-04") when the fixed form would show no significant digit or is too long.
 */
std::string format_number(double v, const NumberProps &props);
/** Round-trip text for editing ("0.001", "1e-05", "42"). */
std::string format_number_edit(double v, const NumberProps &props);

/** Parses typed text; returns nullopt (and a reason in *err) when invalid. Does not clamp. */
std::optional<double> parse_number(std::string_view text, const NumberProps &props, std::string *err = nullptr);

}  // namespace stk::ui
