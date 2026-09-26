/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/viewer_gpu/viewer.hh"

#include "render.hh"
#include "scene.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <set>

#include "GPU_capabilities.hh"
#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_immediate.hh"
#include "GPU_matrix.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"

#include "stk/gfx/fonts.hh"
#include "stk/gfx/image.hh"
#include "stk/viewer/picking.hh"

namespace stk::viewer_gpu {

using namespace blender;
using viewer::dvec3;

std::shared_ptr<const io::Payload> load_payload(const std::filesystem::path &path)
{
  std::filesystem::path p = path;
  if (std::filesystem::is_directory(p) || p.filename() == "manifest.json") {
    return std::make_shared<const io::Payload>(io::read_directory(p));
  }
  return std::make_shared<const io::Payload>(io::read_stkp(p));
}

namespace {

/** GPU_render_begin / begin_frame around standalone GPU work (exports, picking). */
class FrameScope {
 public:
  FrameScope()
  {
    ctx_ = GPU_context_active_get();
    if (ctx_) {
      GPU_render_begin();
      GPU_context_begin_frame(ctx_);
    }
  }
  ~FrameScope()
  {
    if (ctx_) {
      GPU_context_end_frame(ctx_);
      GPU_render_end();
    }
  }
  bool ok() const
  {
    return ctx_ != nullptr;
  }

 private:
  GPUContext *ctx_ = nullptr;
};

}  // namespace

struct Viewer::Impl {
  const gfx::FontStack &fonts;
  ViewerOptions options;
  ResourceCache cache;
  Renderer renderer;
  viewer::LodPolicy lod;

  std::map<std::string, std::unique_ptr<GpuScene>> scenes;
  GpuScene *current = nullptr;
  std::shared_ptr<const io::Payload> payload;
  uint64_t clock = 0;

  viewer::CameraPose camera;
  bool has_camera = false;
  std::set<std::string> hidden, shown;
  bool overlays = true;
  std::string lighting;

  ColorTarget view_target;
  IdTarget id_target;
  float last_scale = 1.0f;
  int last_width = 0, last_height = 0;
  double last_frame_ms = 0;
  FrameStats last_stats;

  Impl(const gfx::FontStack &f, ViewerOptions o)
      : fonts(f), options(o), cache(o.gpu_budget_bytes), renderer(f), lod(o.lod, o.target_frame_ms)
  {
  }

  ~Impl()
  {
    view_target.release();
    id_target.release();
    current = nullptr;
    scenes.clear();
    cache.clear();
  }

  GpuScene *scene_for(std::shared_ptr<const io::Payload> p)
  {
    const std::string key = scene_key(*p);
    auto it = scenes.find(key);
    if (it == scenes.end()) {
      std::unique_ptr<GpuScene> s = build_scene(std::move(p), cache);
      it = scenes.emplace(key, std::move(s)).first;
    }
    it->second->last_use = ++clock;
    return it->second.get();
  }

  /** Drop other scenes (least recently used first) and unreferenced buffers above the budget. */
  void enforce_budget()
  {
    const uint64_t budget = cache.budget();
    cache.evict(budget);
    while (cache.resident() > budget) {
      GpuScene *oldest = nullptr;
      for (auto &[key, s] : scenes) {
        if (s.get() != current && (!oldest || s->last_use < oldest->last_use)) {
          oldest = s.get();
        }
      }
      if (!oldest) {
        break;
      }
      scenes.erase(oldest->key);
      cache.evict(budget);
    }
  }

  FrameParams params(int full_w, int full_h, const TileRect &tile, float pixel_scale, bool use_lod)
  {
    FrameParams p;
    p.full_width = full_w;
    p.full_height = full_h;
    p.tile = tile;
    p.pixel_scale = pixel_scale;
    p.camera = camera;
    p.overlays = overlays;
    p.lighting = lighting;
    p.hidden = &hidden;
    p.shown = &shown;
    p.lod = use_lod ? &lod : nullptr;
    return p;
  }

  void reset_camera()
  {
    if (!current) {
      return;
    }
    const io::Json *view = nullptr;
    if (auto it = payload->manifest.find("view"); it != payload->manifest.end()) {
      view = &*it;
    }
    static const io::Json empty = io::Json::object();
    camera = viewer::camera_pose(view ? *view : empty, dvec3::from(payload->render_origin), current->bounds);
    has_camera = true;
  }
};

/* -------------------------------------------------------------------- */

Viewer::Viewer(const gfx::FontStack &fonts, ViewerOptions options) : impl_(std::make_unique<Impl>(fonts, options)) {}

Viewer::~Viewer() = default;

void Viewer::set_payload(std::shared_ptr<const io::Payload> payload)
{
  Impl &m = *impl_;
  if (!payload) {
    m.current = nullptr;
    m.payload.reset();
    return;
  }
  const std::string previous_signature = m.current ? m.current->camera_signature : std::string();
  const bool had = m.current != nullptr;
  GpuScene *scene = m.scene_for(payload);
  m.current = scene;
  m.payload = std::move(payload);
  if (!had || !m.has_camera || scene->camera_signature != previous_signature) {
    m.reset_camera();
  }
  m.enforce_budget();
}

const std::shared_ptr<const io::Payload> &Viewer::payload() const
{
  return impl_->payload;
}

void Viewer::prefetch(std::shared_ptr<const io::Payload> payload)
{
  if (!payload) {
    return;
  }
  Impl &m = *impl_;
  GpuScene *s = m.scene_for(std::move(payload));
  /* A prefetched scene counts as recently used, but never above the current one. */
  if (m.current) {
    s->last_use = std::min(s->last_use, m.current->last_use);
    m.current->last_use = ++m.clock;
  }
  m.enforce_budget();
}

void Viewer::trim()
{
  Impl &m = *impl_;
  for (auto it = m.scenes.begin(); it != m.scenes.end();) {
    it = it->second.get() == m.current ? std::next(it) : m.scenes.erase(it);
  }
  m.cache.trim();
}

const viewer::CameraPose &Viewer::camera() const
{
  return impl_->camera;
}

void Viewer::set_camera(const viewer::CameraPose &pose)
{
  impl_->camera = pose;
  impl_->has_camera = true;
}

void Viewer::set_camera_preset(const viewer::CameraPreset preset)
{
  Impl &m = *impl_;
  const viewer::CameraPose old = m.camera;
  m.camera = viewer::fit_camera(bounds(), preset, old.view_angle_deg, 1.0, old.parallel);
  m.has_camera = true;
}

void Viewer::reset_camera()
{
  impl_->reset_camera();
}

viewer::Bounds Viewer::bounds() const
{
  return impl_->current ? impl_->current->bounds : viewer::Bounds{};
}

void Viewer::set_interacting(const bool interacting)
{
  impl_->lod.set_interacting(interacting);
}

viewer::LodPolicy &Viewer::lod_policy()
{
  return impl_->lod;
}

std::vector<LayerInfo> Viewer::layers() const
{
  std::vector<LayerInfo> out;
  const Impl &m = *impl_;
  if (!m.current) {
    return out;
  }
  FrameParams p;
  p.hidden = &m.hidden;
  p.shown = &m.shown;
  for (const DrawLayer &L : m.current->layers) {
    LayerInfo info;
    info.id = L.id;
    info.name = L.name;
    info.type = L.type;
    info.kind = L.overlay.kind;
    info.layer_kind = L.kind;
    info.visible = m.renderer.layer_shown(L, p);
    info.pickable = L.pickable();
    info.elements = L.elements();
    info.lod_levels = L.kind == LayerKind::Triangles ? L.mesh.size() :
                      L.kind == LayerKind::Volume    ? L.volume.levels.size() :
                                                       1;
    out.push_back(std::move(info));
  }
  return out;
}

void Viewer::set_layer_visible(std::string_view layer_id, const bool visible)
{
  const std::string id(layer_id);
  if (visible) {
    impl_->hidden.erase(id);
    impl_->shown.insert(id);
  }
  else {
    impl_->shown.erase(id);
    impl_->hidden.insert(id);
  }
}

bool Viewer::layer_visible(std::string_view layer_id) const
{
  for (const LayerInfo &l : layers()) {
    if (l.id == layer_id) {
      return l.visible;
    }
  }
  return false;
}

void Viewer::set_overlays_visible(const bool visible)
{
  impl_->overlays = visible;
}

void Viewer::set_lighting(std::string preset)
{
  impl_->lighting = std::move(preset);
}

/* -------------------------------------------------------------------- */
/* Drawing */

void Viewer::render(const int width, const int height, const float ui_scale)
{
  Impl &m = *impl_;
  std::string err;
  if (!m.current || width <= 0 || height <= 0 || !m.view_target.ensure(width, height, err)) {
    return;
  }
  const auto t0 = std::chrono::steady_clock::now();
  m.last_width = width;
  m.last_height = height;
  m.last_scale = ui_scale;
  const FrameParams p = m.params(width, height, {0, 0, width, height}, ui_scale, true);
  m.last_stats = m.renderer.draw(*m.current, p, m.view_target);
  const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
  m.last_frame_ms = ms;
  m.lod.report_frame(ms);
}

void Viewer::draw(const RegionRect &region, const float ui_scale)
{
  Impl &m = *impl_;
  gpu::FrameBuffer *target = GPU_framebuffer_active_get();
  render(region.width, region.height, ui_scale);
  if (!m.view_target.color) {
    return;
  }
  GPU_framebuffer_bind(target);
  GPU_viewport(region.x, region.y, region.width, region.height);
  GPU_matrix_push_projection();
  GPU_matrix_push();
  GPU_matrix_identity_set();
  GPU_matrix_ortho_set(0, float(region.width), 0, float(region.height), -1, 1);
  GPU_blend(GPU_BLEND_ALPHA_PREMULT);
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
  const uint uv = GPU_vertformat_attr_add(format, "texCoord", gpu::VertAttrType::SFLOAT_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_IMAGE_COLOR);
  immUniformColor4f(1, 1, 1, 1);
  immBindTexture("image", m.view_target.color);
  immBegin(GPU_PRIM_TRI_FAN, 4);
  const float w = float(region.width), h = float(region.height);
  immAttr2f(uv, 0, 0);
  immVertex2f(pos, 0, 0);
  immAttr2f(uv, 1, 0);
  immVertex2f(pos, w, 0);
  immAttr2f(uv, 1, 1);
  immVertex2f(pos, w, h);
  immAttr2f(uv, 0, 1);
  immVertex2f(pos, 0, h);
  immEnd();
  immUnbindProgram();
  GPU_blend(GPU_BLEND_NONE);
  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

gpu::Texture *Viewer::texture() const
{
  return impl_->view_target.color;
}

/* -------------------------------------------------------------------- */
/* Picking */

PickResult Viewer::pick(const double x, const double y)
{
  return pick(x, y, impl_->last_width > 0 ? impl_->last_width : 800, impl_->last_height > 0 ? impl_->last_height : 600);
}

PickResult Viewer::pick(const double x, const double y, const int width, const int height)
{
  Impl &m = *impl_;
  PickResult result;
  if (!m.current || width <= 0 || height <= 0) {
    return result;
  }
  const int px = int(std::floor(x)), py = int(std::floor(y));
  if (px < 0 || py < 0 || px >= width || py >= height) {
    return result;
  }
  /* The id pass renders only a small window around the cursor (an off-axis tile of the view). */
  constexpr int r = 4, n = 2 * r + 1;
  const int row_from_bottom = height - 1 - py;
  const TileRect tile{px - r, row_from_bottom - r, n, n};
  std::vector<uint32_t> ids(size_t(n) * n * 2, 0);
  {
    FrameScope frame;
    std::string err;
    if (!frame.ok() || !m.id_target.ensure(n, n, err)) {
      return result;
    }
    const FrameParams p = m.params(width, height, tile, m.last_scale, false);
    m.renderer.draw_ids(*m.current, p, m.id_target);
    GPU_finish();
    GPU_texture_read(m.id_target.ids, GPU_DATA_UINT, 0, ids.data());
    GPU_framebuffer_restore();
  }
  /* Candidates by distance from the centre pixel. */
  struct Cand {
    int d2;
    uint32_t tag, element;
  };
  std::vector<Cand> cands;
  for (int j = 0; j < n; j++) {
    for (int i = 0; i < n; i++) {
      const uint32_t tag = ids[(size_t(j) * n + i) * 2], element = ids[(size_t(j) * n + i) * 2 + 1];
      if (tag != 0) {
        cands.push_back({(i - r) * (i - r) + (j - r) * (j - r), tag, element});
      }
    }
  }
  std::stable_sort(cands.begin(), cands.end(), [](const Cand &a, const Cand &b) { return a.d2 < b.d2; });
  const viewer::Viewport viewport{double(width), double(height)};
  const viewer::Ray ray = viewer::pixel_ray(m.camera, viewport, x, y);
  const viewer::ClipRange clip = viewer::clip_range(m.camera, m.current->render_bounds);
  const dvec3 origin = dvec3::from(m.payload->render_origin);
  std::set<std::pair<uint32_t, uint32_t>> tried;
  /* Refine only visible candidates in this tile. A miss must not trigger an exhaustive search of
   * a potentially huge layer, nor prevent testing its other candidates near the cursor. */
  constexpr viewer::PickMode mode = viewer::PickMode::CandidateOnly;
  for (const Cand &c : cands) {
    if (!tried.insert({c.tag, c.element}).second) {
      continue;
    }
    const int index = int(c.tag) - 1;
    if (index < 0 || size_t(index) >= m.current->layers.size()) {
      continue;
    }
    const DrawLayer &L = m.current->layers[size_t(index)];
    std::optional<viewer::PickHit> hit;
    uint32_t element = c.element;
    switch (L.kind) {
      case LayerKind::Triangles: {
        const size_t finest = L.finest_mesh_level();
        if (finest >= L.mesh.size()) {
          break;
        }
        const MeshLevel &lv = L.mesh[finest];
        viewer::LayerGeometry g{lv.positions, lv.indices, origin, L.layer_origin};
        hit = viewer::pick_triangles(ray, g, c.element, mode);
        break;
      }
      case LayerKind::Points: {
        const PointData &d = L.points;
        viewer::LayerGeometry g{d.positions, std::span<const uint32_t>(), origin, L.layer_origin};
        if (d.world_spheres) {
          hit = viewer::pick_spheres(ray, g, d.radius, d.radii_cpu, c.element, mode);
        }
        else {
          hit = viewer::pick_points(m.camera, viewport, x, y, g, d.size_px * m.last_scale, c.element, mode);
        }
        break;
      }
      case LayerKind::Instances: {
        const GlyphData &gd = L.glyphs;
        if (c.element >= gd.kept.size()) {
          break;
        }
        element = gd.kept[c.element];
        if (gd.line_shape) {
          viewer::LayerGeometry g{gd.lines.positions, std::span<const uint32_t>(), origin, L.layer_origin};
          hit = viewer::pick_segments(m.camera, viewport, x, y, g, gd.lines.width_px * m.last_scale,
                                      c.element, mode, clip);
          if (hit) {
            hit->element = element;
          }
          break;
        }
        viewer::LayerGeometry g{gd.positions, std::span<const uint32_t>(), origin, L.layer_origin};
        hit = viewer::pick_glyphs(ray, g, gd.directions, gd.scales, gd.glyph, element, mode);
        break;
      }
      case LayerKind::SliceImage: {
        const SliceData &s = L.slice;
        hit = viewer::pick_slice_image(ray, s.origin, s.u, s.v, s.width, s.height, origin, L.layer_origin);
        break;
      }
      case LayerKind::Lines: {
        const LineData &d = L.lines;
        viewer::LayerGeometry g{d.positions, std::span<const uint32_t>(d.pairs), origin, L.layer_origin};
        hit = viewer::pick_segments(m.camera, viewport, x, y, g, d.width_px * m.last_scale,
                                    c.element, mode, clip);
        break;
      }
      default:
        break;
    }
    if (!hit) {
      continue;
    }
    result.hit = true;
    result.layer_id = L.id;
    result.layer_type = L.type;
    result.layer_index = L.index;
    result.element = hit->element;
    result.distance = hit->t;
    result.local = hit->local;
    result.physical = hit->physical;
    result.barycentric = hit->barycentric;
    result.probe = L.probe;
    result.gpu_candidate = element;
    break;
  }
  return result;
}

/* -------------------------------------------------------------------- */
/* Export */

bool Viewer::render_image(const ExportOptions &options, gfx::Image &r_image, std::string &error)
{
  Impl &m = *impl_;
  if (!m.current) {
    error = "no payload";
    return false;
  }
  const int mag = options.magnification;
  if (mag < 1 || mag > 8) {
    error = "magnification must be an integer from 1 to 8";
    return false;
  }
  const int w = options.width > 0 ? options.width : m.current->viewport_width;
  const int h = options.height > 0 ? options.height : m.current->viewport_height;
  const int W = w * mag, H = h * mag;
  if (W > 65536 || H > 65536) {
    error = "image too large";
    return false;
  }
  int tile = options.tile_size > 0 ? options.tile_size : std::min(4096, GPU_max_texture_size());
  tile = std::max(16, std::min(tile, GPU_max_texture_size()));
  r_image = gfx::Image{};
  r_image.width = W;
  r_image.height = H;
  r_image.rgba.assign(size_t(W) * H * 4, 0);
  const bool saved_overlays = m.overlays;
  m.overlays = options.overlays && saved_overlays;
  const bool transparent = options.transparent || m.current->transparent;
  {
    FrameScope frame;
    if (!frame.ok()) {
      error = "no active GPU context";
      m.overlays = saved_overlays;
      return false;
    }
    ColorTarget target;
    std::vector<uint8_t> pixels;
    for (int ty = 0; ty < H; ty += tile) {
      for (int tx = 0; tx < W; tx += tile) {
        const int tw = std::min(tile, W - tx), th = std::min(tile, H - ty);
        if (!target.ensure(tw, th, error)) {
          m.overlays = saved_overlays;
          return false;
        }
        FrameParams p = m.params(W, H, {tx, ty, tw, th}, float(mag), false);
        p.transparent = options.transparent;
        m.renderer.draw(*m.current, p, target);
        GPU_finish();
        pixels.resize(size_t(tw) * th * 4);
        GPU_texture_read(target.color, GPU_DATA_UBYTE, 0, pixels.data());
        for (int j = 0; j < th; j++) {
          /* Texture row j (from the bottom) of the tile -> image row from the top. */
          const int row = H - 1 - (ty + j);
          std::memcpy(&r_image.rgba[(size_t(row) * W + tx) * 4], &pixels[size_t(j) * tw * 4], size_t(tw) * 4);
        }
      }
    }
    GPU_framebuffer_restore();
  }
  m.overlays = saved_overlays;
  for (size_t i = 0; i < r_image.rgba.size(); i += 4) {
    uint8_t *p = &r_image.rgba[i];
    if (!transparent) {
      p[3] = 255;
    }
    else if (p[3] > 0 && p[3] < 255) {
      /* Premultiplied -> straight alpha. */
      for (int k = 0; k < 3; k++) {
        p[k] = uint8_t(std::min(255, int(std::lround(p[k] * 255.0 / p[3]))));
      }
    }
  }
  return true;
}

bool Viewer::export_png(const std::filesystem::path &path, const ExportOptions &options, std::string &error)
{
  gfx::Image img;
  if (!render_image(options, img, error)) {
    return false;
  }
  if (!gfx::png_write(path.string(), img)) {
    error = "cannot write " + path.string();
    return false;
  }
  return true;
}

GpuStats Viewer::stats() const
{
  const Impl &m = *impl_;
  GpuStats s;
  s.resident_bytes = m.cache.resident();
  s.budget_bytes = m.cache.budget();
  s.buffers = m.cache.size();
  s.evictions = m.cache.evictions();
  s.uploads = m.cache.uploads();
  s.cache_hits = m.cache.hits();
  s.cached_scenes = m.scenes.size();
  s.last_frame_ms = m.last_frame_ms;
  s.drawn_triangles = m.last_stats.triangles;
  s.drawn_instances = m.last_stats.instances;
  s.drawn_points = m.last_stats.points;
  s.drawn_segments = m.last_stats.segments;
  return s;
}

std::vector<std::string> Viewer::warnings() const
{
  return impl_->current ? impl_->current->warnings : std::vector<std::string>{};
}

}  // namespace stk::viewer_gpu
