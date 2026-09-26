/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/volume.hh"

#include <algorithm>
#include <cmath>
#include <limits>

namespace stk::viewer {

using io::Json;

dmat4 VolumeGrid::index_to_local() const
{
  const auto &d = direction;
  dmat4 axes = dmat4::from_rows({{{d[0], d[1], d[2], origin.x},
                                  {d[3], d[4], d[5], origin.y},
                                  {d[6], d[7], d[8], origin.z},
                                  {0.0, 0.0, 0.0, 1.0}}});
  return axes * dmat4::scale(spacing);
}

double VolumeGrid::unit_distance() const
{
  return std::min({spacing.x, spacing.y, spacing.z});
}

namespace {

template<typename T>
std::array<double, 2> stored_range_impl(std::span<const T> values, double denominator)
{
  double lo = std::numeric_limits<double>::infinity(), hi = -lo;
  for (const T value : values) {
    const double v = double(value);
    if (std::isfinite(v)) {
      lo = std::min(lo, v);
      hi = std::max(hi, v);
    }
  }
  if (!(hi >= lo)) {
    return {0, 1};
  }
  lo /= denominator;
  hi /= denominator;
  if (lo == hi) {
    const double value = lo;
    lo = value - 0.5;
    hi = value + 0.5;
    if (lo == hi) {
      lo = std::nextafter(value, -std::numeric_limits<double>::infinity());
      hi = std::nextafter(value, std::numeric_limits<double>::infinity());
    }
  }
  return {lo, hi};
}

double number_or(const Json &object, const char *key, double fallback)
{
  const auto it = object.find(key);
  return it != object.end() && io::is_finite_number(*it) ? it->get<double>() : fallback;
}

dvec3 vec3_of(const Json &value)
{
  return {value[0].get<double>(), value[1].get<double>(), value[2].get<double>()};
}

}  // namespace

std::array<double, 2> stored_range(std::span<const float> values)
{
  return stored_range_impl(values, 1.0);
}

std::array<double, 2> stored_range(std::span<const uint8_t> values, bool normalized)
{
  return stored_range_impl(values, normalized ? 255.0 : 1.0);
}

std::array<double, 2> stored_range(std::span<const uint16_t> values, bool normalized)
{
  return stored_range_impl(values, normalized ? 65535.0 : 1.0);
}

/* GCC folds the two identical sort comparators below (array<double, 4> and array<double, 2>) and then
 * reports a false -Warray-bounds in sanitizer builds. */
#if defined(__GNUC__) && !defined(__clang__)
#  pragma GCC diagnostic push
#  pragma GCC diagnostic ignored "-Warray-bounds"
#endif
VolumeTransfer volume_transfer(const io::Payload &payload, const Json &layer)
{
  VolumeTransfer tf;
  const Json &grid = layer.at("grid");
  for (int i = 0; i < 3; i++) {
    tf.grid.dimensions[size_t(i)] = grid.at("dimensions")[size_t(i)].get<int64_t>();
  }
  tf.grid.origin = vec3_of(grid.at("origin"));
  tf.grid.spacing = vec3_of(grid.at("spacing"));
  if (const auto it = grid.find("direction"); it != grid.end() && it->is_array() && it->size() == 9) {
    for (size_t i = 0; i < 9; i++) {
      tf.grid.direction[i] = (*it)[i].get<double>();
    }
  }
  tf.value_scale = number_or(layer, "value_scale", 1.0);
  tf.value_offset = number_or(layer, "value_offset", 0.0);
  if (const auto it = layer.find("value_range"); it != layer.end() && it->is_array() && it->size() == 2) {
    tf.value_range = {(*it)[0].get<double>(), (*it)[1].get<double>()};
  }
  tf.nearest = io::get_string(layer, "sampling", "linear") == "nearest";
  tf.shade = io::get_bool(layer, "shade", false);
  const Json &function = layer.at("transfer_function");
  const std::string colormap_id = function.at("colormap").get<std::string>();
  const std::optional<Colormap> colormap = resolve_colormap(payload, colormap_id);
  tf.categorical = colormap && colormap->categorical;
  const std::array<double, 2> range{function.at("range")[0].get<double>(), function.at("range")[1].get<double>()};
  tf.color_points = volume_color_points(colormap ? &*colormap : nullptr, range, &tf.warnings);
  std::sort(tf.color_points.begin(), tf.color_points.end(),
            [](const std::array<double, 4> &a, const std::array<double, 4> &b) { return a[0] < b[0]; });
  /* vtkPiecewiseFunction::AddPoint (offscreen) and vtk.js addPoint (web): points sorted by value, a
   * repeated value replaces the earlier point. */
  for (const Json &point : function.at("opacity")) {
    const double value = point[0].get<double>(), alpha = std::clamp(point[1].get<double>(), 0.0, 1.0);
    const auto same = std::find_if(tf.opacity_points.begin(), tf.opacity_points.end(),
                                   [&](const auto &p) { return p[0] == value; });
    if (same != tf.opacity_points.end()) {
      (*same)[1] = alpha;
    }
    else {
      tf.opacity_points.push_back({value, alpha});
    }
  }
  std::sort(tf.opacity_points.begin(), tf.opacity_points.end(),
            [](const std::array<double, 2> &a, const std::array<double, 2> &b) { return a[0] < b[0]; });
  return tf;
}
#if defined(__GNUC__) && !defined(__clang__)
#  pragma GCC diagnostic pop
#endif

RGB evaluate_color(const std::vector<std::array<double, 4>> &points, double value)
{
  if (points.empty()) {
    return {0, 0, 0};
  }
  if (!(value > points.front()[0])) {
    return {points.front()[1], points.front()[2], points.front()[3]};
  }
  if (value >= points.back()[0]) {
    return {points.back()[1], points.back()[2], points.back()[3]};
  }
  const auto upper = std::upper_bound(points.begin(), points.end(), value,
                                      [](double v, const std::array<double, 4> &p) { return v < p[0]; });
  const auto &b = *upper;
  const auto &a = *(upper - 1);
  const double t = b[0] > a[0] ? (value - a[0]) / (b[0] - a[0]) : 0.0;
  return {a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t};
}

double evaluate_opacity(const std::vector<std::array<double, 2>> &points, double value)
{
  if (points.empty()) {
    return 0.0;
  }
  if (!(value > points.front()[0])) {
    return points.front()[1];
  }
  if (value >= points.back()[0]) {
    return points.back()[1];
  }
  /* numpy.interp: the rightmost segment whose left end is <= value. */
  const auto upper = std::upper_bound(points.begin(), points.end(), value,
                                      [](double v, const std::array<double, 2> &p) { return v < p[0]; });
  const auto &b = *upper;
  const auto &a = *(upper - 1);
  const double t = b[0] > a[0] ? (value - a[0]) / (b[0] - a[0]) : 0.0;
  return a[1] + (b[1] - a[1]) * t;
}

std::vector<std::array<float, 4>> transfer_lut(const VolumeTransfer &tf, double stored_lo, double stored_hi, int size)
{
  size = std::max(2, size);
  std::vector<std::array<float, 4>> lut(static_cast<size_t>(size));
  for (int i = 0; i < size; i++) {
    const double stored = stored_lo + (i + 0.5) / size * (stored_hi - stored_lo);
    const double physical = tf.stored_to_physical(stored);
    const RGB c = evaluate_color(tf.color_points, physical);
    lut[size_t(i)] = {float(c[0]), float(c[1]), float(c[2]), float(evaluate_opacity(tf.opacity_points, physical))};
  }
  return lut;
}

double opacity_correction(double alpha, double step, double unit_distance)
{
  if (!(unit_distance > 0) || alpha <= 0) {
    return std::max(0.0, alpha);
  }
  if (alpha >= 1) {
    return 1.0;
  }
  return 1.0 - std::pow(1.0 - alpha, step / unit_distance);
}

std::vector<std::array<double, 2>> categorical_opacity(double lo, double hi, double alpha)
{
  if (hi < 0) {
    return {{lo, 0.0}, {hi, 0.0}};
  }
  if (lo >= 0) {
    return {{lo, alpha}, {hi, alpha}};
  }
  return {{lo, 0.0}, {-0.5, 0.0}, {-0.499, alpha}, {hi, alpha}};
}

}  // namespace stk::viewer
