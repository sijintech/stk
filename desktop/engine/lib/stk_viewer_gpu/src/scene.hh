/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* GPU scene of one payload: every layer turned into GPU resources and draw parameters (the port of
 * web/src/layers.ts buildScene and volume.ts buildVolume), plus the CPU views that picking needs. */

#include "resources.hh"

#include "stk/io/payload.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer/colormap.hh"
#include "stk/viewer/glyph.hh"
#include "stk/viewer/picking.hh"
#include "stk/viewer/scene.hh"
#include "stk/viewer/volume.hh"
#include "stk/viewer_gpu/viewer.hh"

#include <array>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace stk::viewer_gpu {

/* Must match stk_common_lib.glsl. */
namespace flag {
inline constexpr int color_solid = 0;
inline constexpr int color_lut = 1;
inline constexpr int color_rgba = 2;
inline constexpr int cell = 4;
inline constexpr int flat_value = 8;
inline constexpr int lighting = 16;
inline constexpr int index_u16 = 32;
inline constexpr int has_index = 64;
inline constexpr int has_normals = 128;
inline constexpr int flat_shading = 256;
inline constexpr int parallel = 512;
inline constexpr int radii = 1024;
inline constexpr int world_spheres = 2048;
inline constexpr int round_sprites = 4096;
}  // namespace flag

/** Colour source of a layer (spec §5 colour spec, resolved). */
struct ColorBinding {
  int mode = flag::color_solid;
  bool cell = false;       /* one value per element (triangle, segment) instead of per point */
  bool flat_value = false; /* nearest sampling of point values */
  bool translucent = false;
  std::array<float, 4> solid{0.8f, 0.8f, 0.8f, 1.0f};
  ResourcePtr values; /* s_cval */
  ResourcePtr lut;    /* 259x1 RGBA8 */
  int flags() const
  {
    return mode | (cell ? flag::cell : 0) | (flat_value ? flag::flat_value : 0);
  }
};

struct MeshLevel {
  uint64_t triangles = 0;
  bool usable = true; /* false: a buffer exceeds the GPU storage-buffer limit */
  ResourcePtr pos, idx, nrm;
  bool has_index = false, index_u16 = false, has_normals = false;
  ColorBinding color;
  /* CPU views for picking (payload-owned, or `owned_*`). */
  std::span<const float> positions;
  viewer::IndexSpan indices;
  std::vector<float> owned_positions;
};

struct LineData {
  uint64_t segments = 0;
  ResourcePtr pos, idx;
  bool has_index = false, index_u16 = false;
  ColorBinding color;
  float width_px = 1.0f;
  std::span<const float> positions;
  std::vector<float> owned_positions;
  std::vector<uint32_t> pairs; /* CPU copy of the segment index pairs (picking) */
};

struct PointData {
  uint64_t count = 0;
  ResourcePtr pos, radii;
  ColorBinding color;
  bool shuffled = false;
  bool spheres = false;       /* render_as "spheres" */
  bool world_spheres = false; /* spheres with a world radius (appearance.radius or radii) */
  float size_px = 3.0f;
  float radius = 0.0f;
  std::span<const float> positions;
  std::vector<float> owned_positions;
  std::vector<float> radii_cpu;
};

struct GlyphData {
  uint64_t count = 0;         /* drawn instances */
  uint64_t mesh_vertices = 0; /* triangle-soup vertices of the glyph mesh */
  ResourcePtr mesh, inst;
  ColorBinding color;
  bool shuffled = false;
  bool line_shape = false; /* "line" glyphs are drawn as segments (LineData) */
  LineData lines;
  viewer::GlyphMesh glyph;
  std::vector<uint32_t> kept; /* drawn instance -> payload instance index */
  /* CPU data for picking (payload order). */
  std::vector<float> positions, directions;
  std::vector<double> scales;
};

struct SliceData {
  ResourcePtr texture;
  viewer::dvec3 origin, u, v; /* relative to the layer origin */
  uint32_t width = 1, height = 1;
  ColorBinding color; /* solid/opacity only */
};

struct VolumeLevel {
  std::array<int64_t, 3> dims{1, 1, 1};
  viewer::VolumeGrid grid;
  ResourcePtr texture;
  double tex_scale = 1.0;           /* texture value -> stored value */
  double stored_lo = 0, stored_hi = 1; /* domain of the transfer-function LUT */
  ResourcePtr tf;
  uint64_t voxels = 0;
};

struct VolumeData {
  std::vector<VolumeLevel> levels; /* coarse to fine */
  viewer::VolumeTransfer transfer;
};

struct OverlayItem {
  std::string kind, anchor, title, unit, format = ".3g", text;
  std::array<double, 2> offset{12, 12};
  bool has_offset = false;
  std::array<double, 2> size{0, 0};
  bool has_size = false;
  bool vertical = true;
  int label_count = 5;
  std::array<double, 2> range{0, 1};
  std::optional<viewer::ContinuousColormap> lut;
  std::vector<viewer::LegendItem> legend;
  int columns = 1;
  std::array<double, 2> lightness{0, 1};
  double font_size = 14;
  std::optional<std::array<float, 3>> color;
  std::array<std::string, 3> labels{"x", "y", "z"};
};

struct DrawLayer {
  LayerKind kind = LayerKind::Unknown;
  int index = -1;
  std::string id, name, type;
  const io::Json *json = nullptr;
  viewer::dvec3 layer_origin; /* absolute */
  viewer::dvec3 offset;       /* layer origin - render_origin */
  bool payload_visible = true;
  bool disabled = false; /* skipped by validation, or over a GPU limit: never drawn */
  bool lighting = false;
  bool flat_shading = false;
  float opacity = 1.0f;
  std::optional<viewer::ProbeRef> probe;

  std::vector<MeshLevel> mesh; /* coarse to fine; last = the main arrays */
  bool edges_visible = false;  /* triangles appearance.edges */
  LineData edges;
  LineData lines;
  PointData points;
  GlyphData glyphs;
  SliceData slice;
  VolumeData volume;
  OverlayItem overlay;

  /** The finest drawable triangle level (mesh.size() when none). */
  size_t finest_mesh_level() const
  {
    for (size_t i = mesh.size(); i > 0; i--) {
      if (mesh[i - 1].usable) {
        return i - 1;
      }
    }
    return mesh.size();
  }
  bool pickable() const
  {
    return kind == LayerKind::Triangles || kind == LayerKind::SliceImage || kind == LayerKind::Lines ||
           kind == LayerKind::Points || kind == LayerKind::Instances;
  }
  bool translucent() const;
  uint64_t elements() const;
};

struct GpuScene {
  std::shared_ptr<const io::Payload> payload;
  std::vector<DrawLayer> layers;
  std::vector<std::string> warnings;
  viewer::Bounds bounds;        /* payload bounds (camera fitting, as the web viewer) */
  viewer::Bounds render_bounds; /* bounds plus glyph and sphere extents (clip planes) */
  std::string camera_signature;
  std::string key;
  std::array<float, 3> background{1, 1, 1};
  std::optional<std::array<float, 3>> background2; /* gradient top colour */
  bool transparent = false;
  std::string lighting = "three_point";
  double light_intensity = 1.0;
  int viewport_width = 800, viewport_height = 600;
  std::vector<std::string> hidden_by_view; /* view.visibility false */
  std::vector<std::shared_ptr<std::vector<uint32_t>>> owned_indices;
  uint64_t last_use = 0;
};

/** A payload identity (manifest content), used to find cached scenes. */
std::string scene_key(const io::Payload &payload);

/** Build every layer (GPU uploads through `cache`). Throws io::PayloadError on malformed layers. */
std::unique_ptr<GpuScene> build_scene(std::shared_ptr<const io::Payload> payload, ResourceCache &cache);

}  // namespace stk::viewer_gpu
