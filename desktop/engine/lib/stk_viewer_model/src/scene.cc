/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/viewer/scene.hh"

#include "stk/viewer/volume.hh"

#include <algorithm>

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

std::optional<dvec3> vec3(const Json *value)
{
  if (!value || !value->is_array() || value->size() != 3) {
    return std::nullopt;
  }
  for (const Json &v : *value) {
    if (!io::is_finite_number(v)) {
      return std::nullopt;
    }
  }
  return dvec3{(*value)[0].get<double>(), (*value)[1].get<double>(), (*value)[2].get<double>()};
}

}  // namespace

Bounds computed_bounds(const io::Payload &payload)
{
  Bounds b = Bounds::empty();
  const dvec3 render_origin = dvec3::from(payload.render_origin);
  for (const Json &layer : payload.layers()) {
    const std::string type = io::get_string(layer, "type");
    const Json *visible = get(layer, "visible");
    if (visible && visible->is_boolean() && !visible->get<bool>()) {
      continue;
    }
    const dvec3 offset = dvec3::from(payload.layer_origin(layer)) - render_origin;
    if (type == "triangles" || type == "lines" || type == "points" || type == "instances") {
      const Json *positions = get(layer, "positions");
      if (!positions || !positions->is_string() || !payload.has_accessor(positions->get<std::string>())) {
        continue;
      }
      const auto p = payload.view<float>(positions->get<std::string>());
      for (size_t i = 0; i + 2 < p.size(); i += 3) {
        b.expand(offset + dvec3{p[i], p[i + 1], p[i + 2]});
      }
    }
    else if (type == "slice_image") {
      const Json *plane = get(layer, "plane");
      const auto o = vec3(plane ? get(*plane, "origin") : nullptr);
      const auto u = vec3(plane ? get(*plane, "u") : nullptr);
      const auto v = vec3(plane ? get(*plane, "v") : nullptr);
      if (o && u && v) {
        for (const dvec3 &c : {*o, *o + *u, *o + *v, *o + *u + *v}) {
          b.expand(offset + c);
        }
      }
    }
    else if (type == "volume") {
      const VolumeTransfer tf = volume_transfer(payload, layer);
      const dmat4 m = tf.grid.index_to_local();
      const auto &n = tf.grid.dimensions;
      for (int corner = 0; corner < 8; corner++) {
        const dvec3 ijk{(corner & 1) ? double(n[0] - 1) : 0.0, (corner & 2) ? double(n[1] - 1) : 0.0,
                        (corner & 4) ? double(n[2] - 1) : 0.0};
        b.expand(offset + m.transform_point(ijk));
      }
    }
  }
  return b;
}

Bounds payload_bounds(const io::Payload &payload)
{
  const Json *bounds = get(payload.manifest, "bounds");
  if (bounds && bounds->is_array() && bounds->size() == 2) {
    const auto lo = vec3(&(*bounds)[0]);
    const auto hi = vec3(&(*bounds)[1]);
    if (lo && hi) {
      return {*lo, *hi};
    }
  }
  const Bounds computed = computed_bounds(payload);
  return computed.valid() ? computed : Bounds{};
}

std::optional<ProbeRef> probe_of(const Json &layer)
{
  const Json *pick = get(layer, "pick");
  const Json *probe = pick ? get(*pick, "probe") : nullptr;
  const auto text = [](const Json *v) {
    return v && v->is_string() ? v->get<std::string>() : std::string();
  };
  std::string node = text(probe ? get(*probe, "node") : nullptr);
  if (node.empty()) {
    node = text(get(layer, "node"));
  }
  if (node.empty()) {
    return std::nullopt;
  }
  return ProbeRef{node, text(probe ? get(*probe, "dataset") : nullptr)};
}

std::string overlay_anchor(const Json &layer)
{
  static const char *anchors[] = {"top_left", "top", "top_right", "left", "center", "right",
                                  "bottom_left", "bottom", "bottom_right"};
  const std::string anchor = io::get_string(layer, "anchor");
  if (std::find(std::begin(anchors), std::end(anchors), anchor) != std::end(anchors)) {
    return anchor;
  }
  const std::string kind = io::get_string(layer, "kind");
  if (kind == "scalar_bar") {
    return "right";
  }
  if (kind == "legend") {
    return "top_right";
  }
  if (kind == "orientation_legend") {
    return "bottom_right";
  }
  if (kind == "axes_triad") {
    return "bottom_left";
  }
  return "top_left";
}

std::vector<LegendItem> legend_items(const CategoricalColormap &colormap, const Json &values)
{
  std::vector<LegendItem> items;
  if (values.is_array()) {
    for (const Json &v : values) {
      if (!v.is_number_integer()) {
        continue;
      }
      const int64_t value = v.get<int64_t>();
      const auto entry = std::find_if(colormap.entries.begin(), colormap.entries.end(),
                                      [&](const CategoryEntry &e) { return e.value == value; });
      if (entry != colormap.entries.end()) {
        items.push_back({entry->value, entry->name, entry->color});
      }
      else {
        items.push_back({value, std::to_string(value), colormap.unknown});
      }
    }
    return items;
  }
  for (const CategoryEntry &e : colormap.entries) {
    items.push_back({e.value, e.name, e.color});
  }
  return items;
}

}  // namespace stk::viewer
