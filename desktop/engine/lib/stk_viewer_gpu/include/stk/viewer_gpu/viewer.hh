/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* stk.payload/2 viewer on Blender's GPU module (docs/specs/stk-render-payload-v2.md): a port of the
 * web viewer (web/src/payload.ts, layers.ts, volume.ts, camera.ts, Legend.tsx) with the rules of the
 * offscreen VTK reference (suan/render/offscreen.py).
 *
 *  - Precision: every matrix is camera-relative float64 from stk_viewer_model (camera_matrices), cast
 *    to float32 only after the eye has been subtracted; GPU buffers hold the payload's float32
 *    positions relative to the layer origin unchanged.
 *  - Layers: lit triangles (continuous attributes binned per fragment through the model's 259-texel
 *    LUT texture, categorical and direction colours as exact per-element RGBA), slice images
 *    (texture quads), instanced glyphs (arrow, cone, sphere, cube, line), wide lines, point sprites
 *    and sphere impostors, and ray-marched volumes (transfer-function LUT, opacity per min(spacing)).
 *  - Overlays: scalar bar, categorical legend, orientation sphere, axes triad and text, drawn in
 *    pixel space with BLF (CJK through the font stack's fallback).
 *  - Picking: a GPU id pass around the cursor names (layer, element); stk_viewer_model refines the
 *    hit in float64.
 *  - Export: magnified PNGs (x1..x8) rendered in tiles with off-axis projections; a tiled image
 *    equals a single-pass one.
 *  - Buffers: content-addressed GPU buffers (payload accessors keyed by sha256), shared between
 *    timesteps, evicted LRU above a GPU memory budget; LOD selection by stk::viewer::LodPolicy.
 *
 * Requires an active GPU context (stk::gfx::Gpu) on the calling thread for every call that touches
 * the GPU (everything except the accessors). Not thread-safe. */

#include "stk/io/payload.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer/lod.hh"
#include "stk/viewer/scene.hh"

#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::gfx {
struct FontStack;
struct Image;
}  // namespace stk::gfx

namespace blender::gpu {
class Texture;
}

namespace stk::viewer_gpu {

/** Read a payload: a directory (or its manifest.json) or a .stkp file. Throws io::PayloadError. */
std::shared_ptr<const io::Payload> load_payload(const std::filesystem::path &path);

/** A region of the bound framebuffer in pixels, bottom-left origin (GPU convention). */
struct RegionRect {
  int x = 0, y = 0, width = 0, height = 0;
};

struct ViewerOptions {
  /** GPU memory budget for payload buffers and textures (bytes). Buffers of the current payload are
   * never evicted; other steps' buffers are dropped least recently used first. */
  uint64_t gpu_budget_bytes = uint64_t(1) << 30;
  viewer::LodBudget lod;
  double target_frame_ms = 1000.0 / 60.0;
  viewer::NavigationStyle navigation = viewer::NavigationStyle::Blender;
};

enum class LayerKind : uint8_t { Triangles, SliceImage, Lines, Points, Instances, Volume, Overlay, Unknown };
std::string_view layer_kind_name(LayerKind kind);

struct LayerInfo {
  std::string id, name, type, kind; /* kind: overlay kind */
  LayerKind layer_kind = LayerKind::Unknown;
  bool visible = true;              /* current visibility (payload `visible`, view.visibility, toggles) */
  bool pickable = false;
  uint64_t elements = 0;            /* triangles, segments, points, instances, voxels or samples */
  size_t lod_levels = 1;
};

struct PickResult {
  bool hit = false;
  std::string layer_id;
  std::string layer_type;
  int layer_index = -1;                 /* index in the payload's layers */
  uint32_t element = 0;                 /* triangle, segment, point, instance or sample index */
  double distance = 0;                  /* along the pixel ray (render_origin frame units) */
  viewer::dvec3 local;                  /* hit relative to render_origin */
  std::array<double, 3> physical{};     /* render_origin + local */
  std::array<double, 3> barycentric{};  /* triangles */
  std::optional<viewer::ProbeRef> probe; /* where view.probe should read */
  uint32_t gpu_candidate = 0;           /* element named by the id buffer */
};

struct ExportOptions {
  int width = 0, height = 0;   /* logical size; 0 = the payload view's viewport (else 800x600) */
  int magnification = 1;       /* 1..8: image is (width x mag) by (height x mag), pixel sizes scaled */
  int tile_size = 0;           /* max tile edge in pixels; 0 = automatic (GPU limit, <= 4096) */
  bool transparent = false;    /* keep alpha (else opaque background) */
  bool overlays = true;
};

struct GpuStats {
  uint64_t resident_bytes = 0, budget_bytes = 0;
  size_t buffers = 0, evictions = 0, uploads = 0, cache_hits = 0;
  size_t cached_scenes = 0;
  double last_frame_ms = 0;
  uint64_t drawn_triangles = 0, drawn_instances = 0, drawn_points = 0, drawn_segments = 0;
};

class Viewer {
 public:
  explicit Viewer(const gfx::FontStack &fonts, ViewerOptions options = {});
  ~Viewer();
  Viewer(const Viewer &) = delete;
  Viewer &operator=(const Viewer &) = delete;

  /**
   * Show a payload. GPU buffers are built (or reused from a prefetched/previous step). The camera is
   * kept when the payload's requested view (viewer::camera_signature) is unchanged, as the web
   * viewer does across timesteps; otherwise it is reset to the payload's camera. Layer visibility
   * toggles are kept by layer id.
   */
  void set_payload(std::shared_ptr<const io::Payload> payload);
  const std::shared_ptr<const io::Payload> &payload() const;
  /** Upload the buffers of another payload (e.g. the next and previous timestep) without showing it. */
  void prefetch(std::shared_ptr<const io::Payload> payload);
  /** Drop cached scenes and buffers that the current payload does not use. */
  void trim();

  /* Camera (relative to render_origin, as stk_viewer_model). */
  const viewer::CameraPose &camera() const;
  void set_camera(const viewer::CameraPose &pose);
  void set_camera_preset(viewer::CameraPreset preset);
  /** The payload's own camera (view.camera fitted to the bounds). */
  void reset_camera();
  viewer::Bounds bounds() const;
  /** Interaction hint for the LOD policy (coarser levels while the camera moves). */
  void set_interacting(bool interacting);
  viewer::LodPolicy &lod_policy();

  /* Layers. */
  std::vector<LayerInfo> layers() const;
  void set_layer_visible(std::string_view layer_id, bool visible);
  bool layer_visible(std::string_view layer_id) const;
  void set_overlays_visible(bool visible);
  /** Lighting override ("three_point", "headlight", "none"); empty = the payload's view.lighting. */
  void set_lighting(std::string preset);

  /**
   * Render the view into `region` of the currently bound framebuffer. The 3D scene is drawn into an
   * internal target of the region's size (with depth), then composited into the region; overlays are
   * drawn at `ui_scale` pixels per logical pixel.
   */
  void draw(const RegionRect &region, float ui_scale = 1.0f);
  /** Render into the internal target only (e.g. to show it through stk_ui's image widget). */
  void render(int width, int height, float ui_scale = 1.0f);
  /** Colour texture of the last draw()/render() (RGBA8; valid until the next call). */
  blender::gpu::Texture *texture() const;

  /** Pick at region-local pixel coordinates (continuous, y down, (0,0) = top-left corner) of the last
   * drawn size. */
  PickResult pick(double x, double y);
  /** Pick in a view of `width` x `height` pixels. */
  PickResult pick(double x, double y, int width, int height);

  /** Offscreen image (RGBA8, top row first). Returns false with `error` when the GPU fails. */
  bool render_image(const ExportOptions &options, gfx::Image &r_image, std::string &error);
  bool export_png(const std::filesystem::path &path, const ExportOptions &options, std::string &error);

  GpuStats stats() const;
  /** Warnings of the current payload (unknown layers, missing colormaps, GPU limits, ...). */
  std::vector<std::string> warnings() const;

  struct Impl;

 private:
  std::unique_ptr<Impl> impl_;
};

}  // namespace stk::viewer_gpu
