/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/colormap.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>

namespace stk::viewer {

using io::Json;

namespace {

const Json *get(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

std::vector<double> json_numbers(const Json *value)
{
  std::vector<double> out;
  if (value && value->is_array()) {
    for (const Json &v : *value) {
      out.push_back(v.is_number() ? v.get<double>() : std::numeric_limits<double>::quiet_NaN());
    }
  }
  return out;
}

const Json *own_attribute(const Json &layer, const Json *name)
{
  const Json *attributes = get(layer, "attributes");
  if (!attributes || !attributes->is_object() || !name || !name->is_string()) {
    return nullptr;
  }
  const Json *attr = get(*attributes, name->get_ref<const std::string &>());
  return attr && attr->is_object() ? attr : nullptr;
}

std::optional<std::array<double, 2>> finite_pair(const Json *value)
{
  if (!value || !value->is_array() || value->size() != 2 || !io::is_finite_number((*value)[0]) ||
      !io::is_finite_number((*value)[1]))
  {
    return std::nullopt;
  }
  return std::array<double, 2>{(*value)[0].get<double>(), (*value)[1].get<double>()};
}

}  // namespace

uint8_t to_byte(double c)
{
  const double v = std::floor(255.0 * c + 0.5);
  if (!(v > 0)) {
    return 0;
  }
  return v >= 255 ? 255 : uint8_t(v);
}

RGBA8 rgba8(std::span<const double> c, RGBA8 fallback)
{
  if (c.size() < 3) {
    return fallback;
  }
  return {to_byte(c[0]), to_byte(c[1]), to_byte(c[2]), to_byte(c.size() > 3 ? c[3] : 1.0)};
}

RGBA8 rgba8_json(const Json *color, RGBA8 fallback)
{
  const std::vector<double> values = json_numbers(color);
  return rgba8(values, fallback);
}

RGB hsl_to_rgb(double h, double s, double l)
{
  const double c = (1 - std::abs(2 * l - 1)) * s;
  const double hp = std::fmod(std::fmod(h, 360.0) + 360.0, 360.0) / 60.0;
  const double x = c * (1 - std::abs(std::fmod(hp, 2.0) - 1));
  double r, g, b;
  if (hp < 1) {
    r = c, g = x, b = 0;
  }
  else if (hp < 2) {
    r = x, g = c, b = 0;
  }
  else if (hp < 3) {
    r = 0, g = c, b = x;
  }
  else if (hp < 4) {
    r = 0, g = x, b = c;
  }
  else if (hp < 5) {
    r = x, g = 0, b = c;
  }
  else {
    r = c, g = 0, b = x;
  }
  const double m = l - c / 2;
  return {r + m, g + m, b + m};
}

RGB orientation_hsl(double px, double py, double pz, double M, double l0, double l1)
{
  const double m = std::hypot(px, py, pz);
  const double mxy = std::hypot(px, py);
  if (!(M > 0) || m == 0 || !std::isfinite(m)) {
    return hsl_to_rgb(0, 0, l0 + (l1 - l0) / 2);
  }
  if (mxy < 1e-5 * M) {
    return hsl_to_rgb(0, 0, l0 + (l1 - l0) * std::min(1.0, std::max(0.0, (pz + M) / (2 * M))));
  }
  const double h = std::atan2(py, px) * 180.0 / std::numbers::pi;
  return hsl_to_rgb(h, std::min(m / M, 1.0), l0 + (l1 - l0) * (pz / m + 1) / 2);
}

RGB categorical_color(double v)
{
  if (v == 0) {
    return {0.75, 0.75, 0.75};
  }
  if (v == -1) {
    return {1, 1, 1};
  }
  if (v < -1 || std::floor(v) != v || !std::isfinite(v)) {
    return {0.5, 0.5, 0.5};
  }
  const double i = v - 1;
  static constexpr double lightness[3] = {0.5, 0.38, 0.62};
  return hsl_to_rgb(std::fmod(i * 137.50776405003785, 360.0), 0.65, lightness[size_t(std::fmod(i, 3.0))]);
}

int lut_index(double v, double lo, double hi)
{
  if (std::isnan(v)) {
    return -2;
  }
  const double t = hi == lo ? 0.5 : (v - lo) / (hi - lo);
  if (t < 0) {
    return -1;
  }
  if (t > 1) {
    return 256;
  }
  return std::min(255, int(std::floor(t * 256)));
}

RGBA8 ContinuousColormap::map(double v, double lo, double hi) const
{
  const int i = lut_index(v, lo, hi);
  if (i == -2) {
    return nan;
  }
  if (i == -1) {
    return below;
  }
  if (i == 256) {
    return above;
  }
  return lut[size_t(i)];
}

std::array<RGBA8, 259> ContinuousColormap::texture() const
{
  std::array<RGBA8, 259> texels{};
  texels[0] = below;
  for (size_t i = 0; i < 256; i++) {
    texels[i + 1] = lut[i];
  }
  texels[257] = above;
  texels[258] = nan;
  return texels;
}

int ContinuousColormap::texel(double v, double lo, double hi)
{
  const int i = lut_index(v, lo, hi);
  return i == -2 ? 258 : i + 1;
}

RGBA8 CategoricalColormap::map(double v) const
{
  if (!std::isfinite(v) || std::floor(v) != v || std::abs(v) > 9.2e18) {
    return unknown;
  }
  const auto it = lookup.find(int64_t(v));
  return it == lookup.end() ? unknown : it->second;
}

ContinuousColormap grey_colormap()
{
  ContinuousColormap cm;
  cm.id = "grey";
  cm.name = "gray";
  for (int i = 0; i < 256; i++) {
    cm.lut[size_t(i)] = {uint8_t(i), uint8_t(i), uint8_t(i), 255};
  }
  cm.nan = {128, 128, 128, 255};
  cm.below = cm.lut[0];
  cm.above = cm.lut[255];
  return cm;
}

std::optional<Colormap> resolve_colormap(const io::Payload &payload, std::string_view id)
{
  const Json *spec = payload.colormap(id);
  if (!spec) {
    return std::nullopt;
  }
  Colormap out;
  const Json *categorical = get(*spec, "categorical");
  if (categorical && io::py_truthy(*categorical)) {
    CategoricalColormap cm;
    cm.id = io::get_string(*spec, "id");
    cm.name = io::get_string(*spec, "name");
    if (const Json *entries = get(*spec, "entries"); entries && entries->is_array()) {
      for (const Json &entry : *entries) {
        const Json *value = get(entry, "value");
        if (!value || !value->is_number_integer()) {
          continue;
        }
        CategoryEntry e{value->get<int64_t>(), io::get_string(entry, "name"), rgba8_json(get(entry, "color"))};
        cm.lookup[e.value] = e.color;
        cm.entries.push_back(std::move(e));
      }
    }
    cm.unknown = rgba8_json(get(*spec, "unknown_color"));
    out.categorical = std::move(cm);
    return out;
  }
  ContinuousColormap cm;
  cm.id = io::get_string(*spec, "id");
  cm.name = io::get_string(*spec, "name");
  const auto lut = payload.view<uint8_t>(spec->at("lut").get<std::string>());
  for (size_t i = 0; i < 256; i++) {
    cm.lut[i] = {lut[4 * i], lut[4 * i + 1], lut[4 * i + 2], lut[4 * i + 3]};
  }
  cm.nan = rgba8_json(get(*spec, "nan_color"));
  const Json *below = get(*spec, "below_color");
  const Json *above = get(*spec, "above_color");
  cm.below = below && !below->is_null() ? rgba8_json(below) : cm.lut[0];
  cm.above = above && !above->is_null() ? rgba8_json(above) : cm.lut[255];
  out.continuous = std::move(cm);
  return out;
}

std::vector<double> scalar_values(std::span<const double> values, int components, const Json &component)
{
  components = std::max(1, components);
  const size_t n = values.size() / size_t(components);
  std::vector<double> out(n);
  const bool magnitude = (component.is_string() && component == "magnitude") ||
                         (component.is_null() && components > 1);
  const bool numeric = component.is_number();
  /* JavaScript Math.min(component, components - 1) as an index; NaN/huge values never reach an int cast. */
  const double wanted = numeric ? component.get<double>() : 0.0;
  const int c = !(wanted == wanted) ? -1 : wanted >= components - 1 ? components - 1 : wanted < 0 ? -1 : int(wanted);
  for (size_t i = 0; i < n; i++) {
    if (!magnitude) {
      out[i] = c >= 0 ? values[i * size_t(components) + size_t(c)] : std::numeric_limits<double>::quiet_NaN();
      continue;
    }
    double s = 0;
    for (int k = 0; k < components; k++) {
      const double x = values[i * size_t(components) + size_t(k)];
      s += x * x;
    }
    out[i] = std::sqrt(s);
  }
  return out;
}

std::array<double, 2> finite_range(std::span<const double> values)
{
  double lo = std::numeric_limits<double>::infinity(), hi = -lo;
  for (double v : values) {
    if (std::isfinite(v)) {
      lo = std::min(lo, v);
      hi = std::max(hi, v);
    }
  }
  return lo <= hi ? std::array<double, 2>{lo, hi} : std::array<double, 2>{0.0, 1.0};
}

std::vector<std::array<double, 4>> volume_color_points(const Colormap *colormap,
                                                       std::array<double, 2> range,
                                                       std::vector<std::string> *warnings)
{
  std::vector<std::array<double, 4>> points;
  if (colormap && colormap->categorical && !colormap->categorical->entries.empty()) {
    for (const CategoryEntry &e : colormap->categorical->entries) {
      const double r = e.color[0] / 255.0, g = e.color[1] / 255.0, b = e.color[2] / 255.0;
      points.push_back({double(e.value) - 0.499, r, g, b});
      points.push_back({double(e.value) + 0.499, r, g, b});
    }
    return points;
  }
  ContinuousColormap cm;
  if (colormap && colormap->continuous) {
    cm = *colormap->continuous;
  }
  else {
    if (warnings) {
      warnings->push_back("volume colormap is not a continuous LUT; using grey");
    }
    cm = grey_colormap();
  }
  const auto [lo, hi] = range;
  if (hi == lo) {
    points.push_back({lo, cm.lut[128][0] / 255.0, cm.lut[128][1] / 255.0, cm.lut[128][2] / 255.0});
  }
  else {
    for (int i = 0; i < 256; i++) {
      const RGBA8 &c = cm.lut[size_t(i)];
      points.push_back({lo + ((i + 0.5) / 256) * (hi - lo), c[0] / 255.0, c[1] / 255.0, c[2] / 255.0});
    }
  }
  return points;
}

ColorResult layer_colors(const io::Payload &payload,
                         const Json &layer,
                         const Json &spec,
                         size_t count,
                         std::string_view association,
                         std::span<const float> vectors,
                         int vector_components)
{
  ColorResult result;
  const std::string layer_id = io::get_string(layer, "id");
  if (const Json *solid = get(spec, "solid"); solid && solid->is_array() && solid->size() >= 3) {
    const std::vector<double> values = json_numbers(solid);
    result.solid = {values[0], values[1], values[2], values.size() > 3 ? values[3] : 1.0};
  }
  const Json *by = get(spec, "by");
  if (!spec.is_object() || !by || !by->is_string() || *by == "solid" || by->get_ref<const std::string &>().empty()) {
    return result;
  }
  if (*by == "direction") {
    std::vector<double> source(vectors.begin(), vectors.end());
    int components = vector_components;
    bool have = !vectors.empty();
    if (const Json *name = get(spec, "attribute"); name && name->is_string()) {
      if (const Json *attr = own_attribute(layer, name)) {
        const std::string accessor = io::get_string(*attr, "accessor");
        const std::vector<float> floats = payload.floats(accessor);
        source.assign(floats.begin(), floats.end());
        components = int(payload.accessor(accessor).components);
        have = true;
      }
    }
    if (!have || components < 3) {
      result.warnings.push_back("layer " + layer_id + " has no 3-component vectors for direction colouring");
      return result;
    }
    double M = 0;
    if (const Json *max = get(spec, "max_magnitude"); max && max->is_number()) {
      M = max->get<double>();
    }
    const size_t stride = size_t(components);
    if (!(M > 0)) {
      M = 0;
      for (size_t i = 0; i < count && (i + 1) * stride <= source.size(); i++) {
        const double m = std::hypot(source[i * stride], source[i * stride + 1], source[i * stride + 2]);
        if (m > M) {
          M = m; /* NaN magnitudes are ignored, as `Math.max(M, NaN || 0)` */
        }
      }
    }
    double l0 = 0, l1 = 1;
    if (const auto lightness = finite_pair(get(spec, "lightness_range"))) {
      l0 = (*lightness)[0];
      l1 = (*lightness)[1];
    }
    result.colors.resize(count);
    for (size_t i = 0; i < count; i++) {
      const bool inside = (i + 1) * stride <= source.size();
      const double nan = std::numeric_limits<double>::quiet_NaN();
      const RGB c = orientation_hsl(inside ? source[i * stride] : nan, inside ? source[i * stride + 1] : nan,
                                    inside ? source[i * stride + 2] : nan, M, l0, l1);
      result.colors[i] = {to_byte(c[0]), to_byte(c[1]), to_byte(c[2]), 255};
    }
    return result;
  }
  const Json *name = get(spec, "attribute");
  const Json *attr = own_attribute(layer, name);
  if (!attr) {
    result.warnings.push_back("layer " + layer_id + " has no colour attribute");
    return result;
  }
  if (io::get_string(*attr, "association", "point") != association) {
    result.warnings.push_back("layer " + layer_id + ": the colour attribute association differs from the layer's");
  }
  const std::string accessor_id = io::get_string(*attr, "accessor");
  const io::PayloadAccessor &accessor = payload.accessor(accessor_id);
  std::optional<Colormap> cm;
  const Json *colormap_id = get(spec, "colormap");
  if (!colormap_id || colormap_id->is_null()) {
    colormap_id = get(*attr, "palette");
  }
  if (colormap_id && colormap_id->is_string()) {
    cm = resolve_colormap(payload, colormap_id->get_ref<const std::string &>());
    result.colormap = colormap_id->get<std::string>();
  }
  const Json *attr_categorical = get(*attr, "categorical");
  const bool categorical = (attr_categorical && attr_categorical->is_boolean() && attr_categorical->get<bool>()) ||
                           (cm && cm->categorical);
  const Json *component = get(spec, "component");
  const Json null_component;
  if (categorical) {
    const std::vector<double> raw = payload.doubles(accessor_id);
    const Json first = (component && component->is_number()) ? *component : Json(0);
    const std::vector<double> values = scalar_values(raw, int(accessor.components), first);
    const CategoricalColormap *palette = cm && cm->categorical ? &*cm->categorical : nullptr;
    if (!palette) {
      result.warnings.push_back("layer " + layer_id + ": categorical attribute without a palette; using stk:categorical");
    }
    result.colors.resize(count);
    for (size_t i = 0; i < count; i++) {
      const double v = i < values.size() ? values[i] : std::numeric_limits<double>::quiet_NaN();
      if (palette) {
        result.colors[i] = palette->map(v);
      }
      else {
        const RGB c = categorical_color(v);
        result.colors[i] = {to_byte(c[0]), to_byte(c[1]), to_byte(c[2]), 255};
      }
    }
    result.categorical = true;
    result.nearest = true;
    return result;
  }
  ContinuousColormap lut;
  if (cm && cm->continuous) {
    lut = *cm->continuous;
  }
  else {
    result.warnings.push_back("layer " + layer_id + " names no continuous colormap; using grey");
    lut = grey_colormap();
  }
  std::vector<double> raw;
  if (accessor.normalized) {
    const std::vector<float> floats = payload.floats(accessor_id);
    raw.assign(floats.begin(), floats.end());
  }
  else {
    raw = payload.doubles(accessor_id);
  }
  const std::vector<double> values =
      scalar_values(raw, int(accessor.components), component ? *component : null_component);
  std::optional<std::array<double, 2>> range = finite_pair(get(spec, "range"));
  if (!range) {
    range = finite_pair(get(*attr, "range"));
  }
  if (!range) {
    /* The accessor min/max hint of the chosen component (scalar use only). */
    const bool scalar_component = accessor.components == 1 || (component && component->is_number());
    const Json *accessor_json = nullptr;
    for (const Json &a : payload.manifest["accessors"]) {
      if (io::get_string(a, "id") == accessor_id) {
        accessor_json = &a;
      }
    }
    const double wanted = component && component->is_number() ? component->get<double>() : 0.0;
    const int c = wanted >= 0 && wanted < 1e6 ? int(wanted) : -1;
    if (scalar_component && accessor_json) {
      const std::vector<double> min = json_numbers(get(*accessor_json, "min"));
      const std::vector<double> max = json_numbers(get(*accessor_json, "max"));
      if (c >= 0 && size_t(c) < min.size() && size_t(c) < max.size() && std::isfinite(min[size_t(c)]) &&
          std::isfinite(max[size_t(c)]))
      {
        range = std::array<double, 2>{min[size_t(c)], max[size_t(c)]};
      }
    }
  }
  if (!range) {
    range = finite_range(values);
  }
  result.colors.resize(count);
  for (size_t i = 0; i < count; i++) {
    result.colors[i] = lut.map(i < values.size() ? values[i] : std::numeric_limits<double>::quiet_NaN(),
                               (*range)[0], (*range)[1]);
  }
  result.range = range;
  const Json *interpolate = get(spec, "interpolate");
  result.nearest = interpolate && interpolate->is_string() && *interpolate == "nearest";
  return result;
}

}  // namespace stk::viewer
