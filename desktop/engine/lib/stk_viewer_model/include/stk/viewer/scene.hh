/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Payload-level helpers of the viewer: scene bounds, probe targets, overlay anchors and legend items
 * (web/src/camera.ts payloadBounds, payload.ts probeOf, Legend.tsx). */

#include "stk/io/payload.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer/colormap.hh"

#include <optional>
#include <string>
#include <vector>

namespace stk::viewer {

/** Bounds relative to render_origin: the manifest's `bounds`, else computed from every 3D layer
 * (positions, slice-image quads and volume grid corners, each shifted by its layer origin). */
Bounds payload_bounds(const io::Payload &payload);
Bounds computed_bounds(const io::Payload &payload);

/** Where view.probe should read for a layer (spec §6 pick.probe, falling back to the layer node). */
struct ProbeRef {
  std::string node, dataset;
};
std::optional<ProbeRef> probe_of(const io::Json &layer);

/** Overlay anchor of an overlay layer (its valid `anchor`, else the kind's default). */
std::string overlay_anchor(const io::Json &layer);

struct LegendItem {
  int64_t value;
  std::string name;
  RGBA8 color;
};
/** Items of a categorical legend: `values` (default every entry), unknown values named by their number. */
std::vector<LegendItem> legend_items(const CategoricalColormap &colormap, const io::Json &values);

}  // namespace stk::viewer
