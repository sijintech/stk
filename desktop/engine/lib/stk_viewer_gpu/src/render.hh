/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Frame rendering of a GpuScene: render targets, the opaque / volume / translucent / overlay passes,
 * the id pass, and off-axis tile projections (a tile of a W x H image renders exactly the pixels a
 * single W x H pass would). */

#include "scene.hh"
#include "shaders.hh"

#include "stk/viewer/camera.hh"
#include "stk/viewer/lod.hh"

#include <functional>
#include <set>
#include <string>

namespace blender::gpu {
class FrameBuffer;
class Texture;
}  // namespace blender::gpu

namespace stk::gfx {
struct FontStack;
}

namespace stk::viewer_gpu {

/** RGBA8 colour + depth (fb) and colour-only (fb_color) framebuffers of one size. */
struct ColorTarget {
  int width = 0, height = 0;
  blender::gpu::Texture *color = nullptr, *depth = nullptr;
  blender::gpu::FrameBuffer *fb = nullptr, *fb_color = nullptr;

  ~ColorTarget();
  void release();
  bool ensure(int w, int h, std::string &error);
};

/** RG32UI (layer tag, element) + depth, for picking. */
struct IdTarget {
  int width = 0, height = 0;
  blender::gpu::Texture *ids = nullptr, *depth = nullptr;
  blender::gpu::FrameBuffer *fb = nullptr;

  ~IdTarget();
  void release();
  bool ensure(int w, int h, std::string &error);
};

struct TileRect {
  int x = 0, y = 0, width = 0, height = 0; /* in full-image pixels, bottom-left origin */
};

struct FrameParams {
  int full_width = 1, full_height = 1; /* the whole image */
  TileRect tile;                       /* the part drawn now (== whole image without tiling) */
  float pixel_scale = 1.0f;            /* px per logical px: ui scale x magnification */
  viewer::CameraPose camera;
  bool overlays = true;
  bool transparent = false;
  std::string lighting; /* preset override; empty = scene's */
  const std::set<std::string> *hidden = nullptr;
  const std::set<std::string> *shown = nullptr; /* explicitly shown (overrides payload visibility) */
  viewer::LodPolicy *lod = nullptr;
};

struct FrameStats {
  uint64_t triangles = 0, instances = 0, points = 0, segments = 0;
};

class Renderer {
 public:
  explicit Renderer(const gfx::FontStack &fonts) : fonts_(fonts) {}

  ShaderCache &shaders()
  {
    return shaders_;
  }

  /** Draw the scene into `target` (bound and cleared here). */
  FrameStats draw(const GpuScene &scene, const FrameParams &params, ColorTarget &target);
  /** Draw pickable layers into `target` (tag = layer index + 1, element). */
  void draw_ids(const GpuScene &scene, const FrameParams &params, IdTarget &target);

  bool layer_shown(const DrawLayer &layer, const FrameParams &params) const;

 private:
  void draw_layer(const GpuScene &scene, const DrawLayer &layer, const FrameParams &params, bool id_pass,
                  FrameStats &stats);
  void draw_volume(const GpuScene &scene, const DrawLayer &layer, const FrameParams &params, ColorTarget &target);
  void draw_overlays(const GpuScene &scene, const FrameParams &params);
  void draw_background(const GpuScene &scene, const FrameParams &params);

  const gfx::FontStack &fonts_;
  ShaderCache shaders_;
};

/** Camera matrices of a tile (projection with the off-axis tile transform). */
struct TileMatrices {
  viewer::CameraMatrices camera;
  viewer::dmat4 projection; /* tile projection */
  double near_z = 0, far_z = 1;
};
TileMatrices tile_matrices(const viewer::CameraPose &pose, const viewer::Bounds &bounds, int full_w, int full_h,
                           const TileRect &tile);

}  // namespace stk::viewer_gpu
