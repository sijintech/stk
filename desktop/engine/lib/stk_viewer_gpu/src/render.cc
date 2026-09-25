/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "render.hh"

#include <algorithm>
#include <cmath>

#include "GPU_batch.hh"
#include "GPU_framebuffer.hh"
#include "GPU_immediate.hh"
#include "GPU_matrix.hh"
#include "GPU_shader.hh"
#include "GPU_state.hh"
#include "GPU_storage_buffer.hh"
#include "GPU_texture.hh"

#include "stk/gfx/fonts.hh"

namespace stk::viewer_gpu {

using namespace blender;
using viewer::dmat4;
using viewer::dvec3;

/* -------------------------------------------------------------------- */
/* Targets */

ColorTarget::~ColorTarget()
{
  release();
}

void ColorTarget::release()
{
  if (fb) {
    GPU_framebuffer_free(fb);
    fb = nullptr;
  }
  if (fb_color) {
    GPU_framebuffer_free(fb_color);
    fb_color = nullptr;
  }
  if (color) {
    GPU_texture_free(color);
    color = nullptr;
  }
  if (depth) {
    GPU_texture_free(depth);
    depth = nullptr;
  }
  width = height = 0;
}

bool ColorTarget::ensure(const int w, const int h, std::string &error)
{
  if (w == width && h == height && fb) {
    return true;
  }
  release();
  const eGPUTextureUsage usage = GPU_TEXTURE_USAGE_ATTACHMENT | GPU_TEXTURE_USAGE_SHADER_READ |
                                 GPU_TEXTURE_USAGE_HOST_READ;
  color = GPU_texture_create_2d("stk_viewer_color", w, h, 1, gpu::TextureFormat::UNORM_8_8_8_8, usage, nullptr);
  depth = GPU_texture_create_2d("stk_viewer_depth", w, h, 1, gpu::TextureFormat::SFLOAT_32_DEPTH, usage, nullptr);
  if (!color || !depth) {
    error = "cannot create " + std::to_string(w) + "x" + std::to_string(h) + " render target";
    release();
    return false;
  }
  GPU_texture_filter_mode(depth, false);
  fb = GPU_framebuffer_create("stk_viewer_fb");
  const GPUAttachment main[2] = {GPU_ATTACHMENT_TEXTURE(depth), GPU_ATTACHMENT_TEXTURE(color)};
  GPU_framebuffer_config_array(fb, main, 2);
  fb_color = GPU_framebuffer_create("stk_viewer_fb_color");
  const GPUAttachment color_only[2] = {GPU_ATTACHMENT_NONE, GPU_ATTACHMENT_TEXTURE(color)};
  GPU_framebuffer_config_array(fb_color, color_only, 2);
  char err[256] = "";
  if (!GPU_framebuffer_check_valid(fb, err)) {
    error = std::string("render target: ") + err;
    release();
    return false;
  }
  width = w;
  height = h;
  return true;
}

IdTarget::~IdTarget()
{
  release();
}

void IdTarget::release()
{
  if (fb) {
    GPU_framebuffer_free(fb);
    fb = nullptr;
  }
  if (ids) {
    GPU_texture_free(ids);
    ids = nullptr;
  }
  if (depth) {
    GPU_texture_free(depth);
    depth = nullptr;
  }
  width = height = 0;
}

bool IdTarget::ensure(const int w, const int h, std::string &error)
{
  if (w == width && h == height && fb) {
    return true;
  }
  release();
  const eGPUTextureUsage usage = GPU_TEXTURE_USAGE_ATTACHMENT | GPU_TEXTURE_USAGE_HOST_READ;
  ids = GPU_texture_create_2d("stk_viewer_ids", w, h, 1, gpu::TextureFormat::UINT_32_32, usage, nullptr);
  depth = GPU_texture_create_2d("stk_viewer_id_depth", w, h, 1, gpu::TextureFormat::SFLOAT_32_DEPTH, usage, nullptr);
  if (!ids || !depth) {
    error = "cannot create the id target";
    release();
    return false;
  }
  fb = GPU_framebuffer_create("stk_viewer_id_fb");
  const GPUAttachment att[2] = {GPU_ATTACHMENT_TEXTURE(depth), GPU_ATTACHMENT_TEXTURE(ids)};
  GPU_framebuffer_config_array(fb, att, 2);
  width = w;
  height = h;
  return true;
}

/* -------------------------------------------------------------------- */
/* Matrices */

TileMatrices tile_matrices(const viewer::CameraPose &pose,
                           const viewer::Bounds &bounds,
                           const int full_w,
                           const int full_h,
                           const TileRect &tile)
{
  TileMatrices out;
  const viewer::ClipRange clip = viewer::clip_range(pose, bounds);
  out.near_z = clip.near_z;
  out.far_z = clip.far_z;
  out.camera = viewer::camera_matrices(pose, double(full_w) / double(std::max(1, full_h)), clip);
  /* NDC of the full image -> NDC of the tile [x0, x0 + w] x [y0, y0 + h] (pixels, bottom-left). */
  dmat4 t = dmat4::identity();
  const double W = full_w, H = full_h, w = tile.width, h = tile.height;
  t.m[0][0] = W / w;
  t.m[1][1] = H / h;
  t.m[3][0] = (W - 2.0 * tile.x - w) / w;
  t.m[3][1] = (H - 2.0 * tile.y - h) / h;
  out.projection = t * out.camera.projection;
  return out;
}

namespace {

void set_mat4(gpu::Shader *sh, const char *name, const dmat4 &m)
{
  const std::array<float, 16> f = m.to_float();
  GPU_shader_uniform_mat4(sh, name, reinterpret_cast<const float(*)[4]>(f.data()));
}

void set_ivec4(gpu::Shader *sh, const char *name, const int v[4])
{
  GPU_shader_uniform_int_ex(sh, GPU_shader_get_uniform(sh, name), 4, 1, v);
}

struct Light {
  bool enabled = true;
  float ambient = 0.0f, intensity = 1.0f;
  bool kit = true; /* vtkLightKit (three_point) vs VTK's automatic headlight */
};

Light light_of(const GpuScene &scene, const FrameParams &params)
{
  const std::string &preset = params.lighting.empty() ? scene.lighting : params.lighting;
  Light l;
  l.intensity = float(scene.light_intensity);
  if (preset == "none") {
    l.enabled = false;
  }
  else if (preset == "headlight") {
    l.kit = false;
    l.intensity = 1.0f;
  }
  return l;
}

constexpr uint64_t kMaxVerticesPerDraw = uint64_t(3) << 24;

struct Common {
  dmat4 mvp, mv, proj;
  int flags = 0;
  int tag = 0;
  float misc[4] = {0, 0, 0, 0};
};

void bind_common(gpu::Shader *sh, const Common &c, const ColorBinding &color, const Light &light, bool lighting,
                 float opacity, int base)
{
  set_mat4(sh, "u_mvp", c.mvp);
  set_mat4(sh, "u_mv", c.mv);
  GPU_shader_uniform_4fv(sh, "u_solid", color.solid.data());
  const float l[4] = {light.ambient, light.intensity, opacity, light.kit ? 1.0f : 0.0f};
  GPU_shader_uniform_4fv(sh, "u_light", l);
  const int flags = c.flags | color.flags() | (lighting && light.enabled ? flag::lighting : 0);
  const int params[4] = {flags, c.tag, base, 0};
  set_ivec4(sh, "u_params", params);
  GPU_shader_uniform_4fv(sh, "u_misc", c.misc);
}

}  // namespace

/* -------------------------------------------------------------------- */
/* Layers */

bool Renderer::layer_shown(const DrawLayer &layer, const FrameParams &params) const
{
  if (layer.disabled) {
    return false;
  }
  if (params.hidden && params.hidden->count(layer.id)) {
    return false;
  }
  if (params.shown && params.shown->count(layer.id)) {
    return true;
  }
  return layer.payload_visible;
}

void Renderer::draw_layer(const GpuScene &scene,
                          const DrawLayer &layer,
                          const FrameParams &params,
                          const bool id_pass,
                          FrameStats &stats)
{
  const TileMatrices tm = tile_matrices(params.camera, scene.render_bounds, params.full_width, params.full_height,
                                        params.tile);
  const dmat4 mv = tm.camera.model_view(layer.offset);
  Common c;
  c.mv = mv;
  c.mvp = tm.projection * mv;
  c.proj = tm.projection;
  c.tag = layer.index + 1;
  c.flags = params.camera.parallel ? flag::parallel : 0;
  const Light light = light_of(scene, params);
  const float px = params.pixel_scale;
  gpu::Batch *batch = GPU_batch_procedural_triangles_get();

  auto draw_chunks = [&](gpu::Shader *sh, uint64_t elements, uint64_t verts_per, auto &&bind_base) {
    const uint64_t per_draw = std::max<uint64_t>(1, kMaxVerticesPerDraw / verts_per);
    for (uint64_t first = 0; first < elements; first += per_draw) {
      const uint64_t n = std::min(per_draw, elements - first);
      bind_base(int(first));
      GPU_batch_draw_advanced(batch, 0, int(n * verts_per), 0, 1);
    }
    (void)sh;
  };

  auto draw_lines = [&](const LineData &d, const ColorBinding &color, bool lighting, uint64_t segments) {
    gpu::Shader *sh = shaders_.get(Program::Line, id_pass);
    if (!sh || segments == 0) {
      return;
    }
    GPU_batch_set_shader(batch, sh);
    Common lc = c;
    lc.flags |= (d.has_index ? flag::has_index : 0) | (d.index_u16 ? flag::index_u16 : 0);
    lc.misc[0] = d.width_px * px;
    lc.misc[2] = float(params.tile.width);
    lc.misc[3] = float(params.tile.height);
    GPU_storagebuf_bind(d.pos->ssbo, slot::pos);
    GPU_storagebuf_bind(d.idx->ssbo, slot::idx);
    GPU_storagebuf_bind(color.values->ssbo, slot::cval);
    GPU_texture_bind(color.lut->texture, slot::lut);
    draw_chunks(sh, segments, 6, [&](int base) { bind_common(sh, lc, color, light, lighting, layer.opacity, base); });
    stats.segments += segments;
  };

  switch (layer.kind) {
    case LayerKind::Triangles: {
      size_t level = layer.finest_mesh_level();
      if (level >= layer.mesh.size()) {
        return;
      }
      if (params.lod && level > 0) {
        std::vector<uint64_t> counts;
        for (size_t i = 0; i <= level; i++) {
          counts.push_back(layer.mesh[i].triangles);
        }
        level = params.lod->triangle_level(counts);
        while (level > 0 && !layer.mesh[level].usable) {
          level--;
        }
      }
      const MeshLevel &m = layer.mesh[level];
      gpu::Shader *sh = shaders_.get(Program::Mesh, id_pass);
      if (!sh) {
        return;
      }
      GPU_batch_set_shader(batch, sh);
      Common mc = c;
      mc.flags |= (m.has_index ? flag::has_index : 0) | (m.index_u16 ? flag::index_u16 : 0) |
                  (m.has_normals ? flag::has_normals : 0) | (layer.flat_shading ? flag::flat_shading : 0);
      GPU_storagebuf_bind(m.pos->ssbo, slot::pos);
      GPU_storagebuf_bind(m.idx->ssbo, slot::idx);
      GPU_storagebuf_bind(m.nrm->ssbo, slot::nrm);
      GPU_storagebuf_bind(m.color.values->ssbo, slot::cval);
      GPU_texture_bind(m.color.lut->texture, slot::lut);
      draw_chunks(sh, m.triangles, 3,
                  [&](int base) { bind_common(sh, mc, m.color, light, layer.lighting, layer.opacity, base); });
      stats.triangles += m.triangles;
      if (layer.edges_visible && !id_pass) {
        draw_lines(layer.edges, layer.edges.color, false, layer.edges.segments);
      }
      break;
    }
    case LayerKind::Lines:
      draw_lines(layer.lines, layer.lines.color, layer.lighting, layer.lines.segments);
      break;
    case LayerKind::Points: {
      const PointData &d = layer.points;
      const uint64_t n = params.lod ? params.lod->point_prefix(d.count, d.shuffled) : d.count;
      gpu::Shader *sh = shaders_.get(Program::Point, id_pass);
      if (!sh || n == 0) {
        return;
      }
      GPU_batch_set_shader(batch, sh);
      Common pc = c;
      pc.flags |= (d.world_spheres ? flag::world_spheres : 0) | (d.radii_cpu.empty() ? 0 : flag::radii) |
                  (d.spheres && !d.world_spheres ? flag::round_sprites : 0);
      pc.misc[0] = d.size_px * px;
      pc.misc[1] = d.radius;
      pc.misc[2] = float(params.tile.width);
      pc.misc[3] = float(params.tile.height);
      set_mat4(sh, "u_proj", tm.projection);
      GPU_storagebuf_bind(d.pos->ssbo, slot::pos);
      GPU_storagebuf_bind(d.radii->ssbo, slot::nrm);
      GPU_storagebuf_bind(d.color.values->ssbo, slot::cval);
      GPU_texture_bind(d.color.lut->texture, slot::lut);
      draw_chunks(sh, n, 6, [&](int base) { bind_common(sh, pc, d.color, light, layer.lighting, layer.opacity, base); });
      stats.points += n;
      break;
    }
    case LayerKind::Instances: {
      const GlyphData &g = layer.glyphs;
      const uint64_t n = params.lod ? params.lod->instance_prefix(g.count, g.shuffled) : g.count;
      if (g.line_shape) {
        draw_lines(g.lines, g.lines.color, false, n);
        stats.instances += n;
        return;
      }
      gpu::Shader *sh = shaders_.get(Program::Glyph, id_pass);
      if (!sh || n == 0 || g.mesh_vertices == 0) {
        return;
      }
      GPU_batch_set_shader(batch, sh);
      GPU_storagebuf_bind(g.mesh->ssbo, slot::pos);
      GPU_storagebuf_bind(g.inst->ssbo, slot::idx);
      GPU_storagebuf_bind(g.color.values->ssbo, slot::cval);
      GPU_texture_bind(g.color.lut->texture, slot::lut);
      const uint64_t per_draw = std::max<uint64_t>(1, kMaxVerticesPerDraw / g.mesh_vertices);
      for (uint64_t first = 0; first < n; first += per_draw) {
        const uint64_t count = std::min(per_draw, n - first);
        bind_common(sh, c, g.color, light, layer.lighting, layer.opacity, int(first));
        GPU_batch_draw_advanced(batch, 0, int(g.mesh_vertices), 0, int(count));
      }
      stats.instances += n;
      break;
    }
    case LayerKind::SliceImage: {
      const SliceData &s = layer.slice;
      gpu::Shader *sh = shaders_.get(Program::Slice, id_pass);
      if (!sh || !s.texture) {
        return;
      }
      GPU_batch_set_shader(batch, sh);
      Common sc = c;
      sc.misc[0] = float(s.width);
      sc.misc[1] = float(s.height);
      bind_common(sh, sc, s.color, light, layer.lighting, layer.opacity, 0);
      const float o[4] = {float(s.origin.x), float(s.origin.y), float(s.origin.z), 0};
      const float u[4] = {float(s.u.x), float(s.u.y), float(s.u.z), 0};
      const float v[4] = {float(s.v.x), float(s.v.y), float(s.v.z), 0};
      GPU_shader_uniform_4fv(sh, "u_plane_origin", o);
      GPU_shader_uniform_4fv(sh, "u_plane_u", u);
      GPU_shader_uniform_4fv(sh, "u_plane_v", v);
      GPU_texture_bind(s.texture->texture, slot::lut);
      GPU_batch_draw_advanced(batch, 0, 6, 0, 1);
      break;
    }
    default:
      break;
  }
}

void Renderer::draw_volume(const GpuScene &scene,
                           const DrawLayer &layer,
                           const FrameParams &params,
                           ColorTarget &target)
{
  const VolumeData &v = layer.volume;
  if (v.levels.empty()) {
    return;
  }
  size_t level = v.levels.size() - 1;
  if (params.lod && v.levels.size() > 1) {
    std::vector<uint64_t> voxels;
    for (const VolumeLevel &l : v.levels) {
      voxels.push_back(l.voxels);
    }
    level = params.lod->volume_level(voxels);
  }
  const VolumeLevel &lv = v.levels[level];
  gpu::Shader *sh = shaders_.get(Program::Volume, false);
  if (!sh) {
    return;
  }
  const TileMatrices tm = tile_matrices(params.camera, scene.render_bounds, params.full_width, params.full_height,
                                        params.tile);
  const dmat4 index_to_eye = tm.camera.model_view(layer.offset) * lv.grid.index_to_local();
  const dmat4 eye_to_index = index_to_eye.inverted();
  const dmat4 inv_proj = tm.projection.inverted();
  const double unit = lv.grid.unit_distance();
  const double step = (params.lod ? params.lod->volume_step() : 0.5) * unit;

  gpu::Batch *batch = GPU_batch_procedural_triangles_get();
  GPU_batch_set_shader(batch, sh);
  set_mat4(sh, "u_inv_proj", inv_proj);
  set_mat4(sh, "u_eye_to_index", eye_to_index);
  const float vol[4] = {float(lv.dims[0]), float(lv.dims[1]), float(lv.dims[2]), float(step)};
  const float vol2[4] = {float(unit), float(lv.stored_lo), float(lv.stored_hi), float(lv.tex_scale)};
  GPU_shader_uniform_4fv(sh, "u_vol", vol);
  GPU_shader_uniform_4fv(sh, "u_vol2", vol2);
  const float light[4] = {0, 0, layer.opacity, 0};
  GPU_shader_uniform_4fv(sh, "u_light", light);
  GPU_texture_bind(lv.texture->texture, slot::lut);
  GPU_texture_bind(lv.tf->texture, slot::tf);
  GPU_texture_bind(target.depth, slot::depth);
  GPU_batch_draw_advanced(batch, 0, 3, 0, 1);
  GPU_texture_unbind(target.depth);
}

/* -------------------------------------------------------------------- */
/* Frame */

void Renderer::draw_background(const GpuScene &scene, const FrameParams &params)
{
  /* Vertical gradient (VTK GradientBackground: Background at the bottom, Background2 at the top). */
  const auto &c1 = scene.background;
  const auto &c2 = *scene.background2;
  GPU_matrix_push_projection();
  GPU_matrix_push();
  GPU_matrix_identity_set();
  GPU_matrix_ortho_set(float(params.tile.x), float(params.tile.x + params.tile.width), float(params.tile.y),
                       float(params.tile.y + params.tile.height), -1.0f, 1.0f);
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
  const uint col = GPU_vertformat_attr_add(format, "color", gpu::VertAttrType::SFLOAT_32_32_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_SMOOTH_COLOR);
  immBegin(GPU_PRIM_TRI_STRIP, 4);
  const float W = float(params.full_width), H = float(params.full_height);
  immAttr4f(col, c1[0], c1[1], c1[2], 1.0f);
  immVertex2f(pos, 0, 0);
  immAttr4f(col, c1[0], c1[1], c1[2], 1.0f);
  immVertex2f(pos, W, 0);
  immAttr4f(col, c2[0], c2[1], c2[2], 1.0f);
  immVertex2f(pos, 0, H);
  immAttr4f(col, c2[0], c2[1], c2[2], 1.0f);
  immVertex2f(pos, W, H);
  immEnd();
  immUnbindProgram();
  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

FrameStats Renderer::draw(const GpuScene &scene, const FrameParams &params, ColorTarget &target)
{
  FrameStats stats;
  GPU_framebuffer_bind(target.fb);
  const bool transparent = params.transparent || scene.transparent;
  const double4 clear = transparent ? double4(0, 0, 0, 0) :
                                      double4(scene.background[0], scene.background[1], scene.background[2], 1.0);
  GPU_framebuffer_clear_color_depth(target.fb, clear, 1.0f);
  GPU_depth_test(GPU_DEPTH_NONE);
  GPU_blend(GPU_BLEND_NONE);
  if (scene.background2 && !transparent) {
    draw_background(scene, params);
  }
  /* Opaque layers. */
  GPU_depth_test(GPU_DEPTH_LESS_EQUAL);
  GPU_depth_mask(true);
  GPU_blend(GPU_BLEND_ALPHA_PREMULT);
  for (const DrawLayer &layer : scene.layers) {
    if (layer.kind == LayerKind::Volume || layer.kind == LayerKind::Overlay || !layer_shown(layer, params) ||
        layer.translucent())
    {
      continue;
    }
    draw_layer(scene, layer, params, false, stats);
  }
  /* Volumes, clipped by the opaque depth. */
  bool any_volume = false;
  for (const DrawLayer &layer : scene.layers) {
    if (layer.kind == LayerKind::Volume && layer_shown(layer, params)) {
      if (!any_volume) {
        GPU_framebuffer_bind(target.fb_color);
        GPU_depth_test(GPU_DEPTH_NONE);
        GPU_depth_mask(false);
        any_volume = true;
      }
      draw_volume(scene, layer, params, target);
    }
  }
  /* Translucent layers (payload order), depth-tested without writing depth. */
  GPU_framebuffer_bind(target.fb);
  GPU_depth_test(GPU_DEPTH_LESS_EQUAL);
  GPU_depth_mask(false);
  for (const DrawLayer &layer : scene.layers) {
    if (layer.kind == LayerKind::Volume || layer.kind == LayerKind::Overlay || !layer_shown(layer, params) ||
        !layer.translucent())
    {
      continue;
    }
    draw_layer(scene, layer, params, false, stats);
  }
  GPU_depth_mask(true);
  GPU_depth_test(GPU_DEPTH_NONE);
  if (params.overlays) {
    GPU_framebuffer_bind(target.fb_color);
    draw_overlays(scene, params);
  }
  GPU_blend(GPU_BLEND_NONE);
  return stats;
}

void Renderer::draw_ids(const GpuScene &scene, const FrameParams &params, IdTarget &target)
{
  GPU_framebuffer_bind(target.fb);
  GPU_framebuffer_clear_color_depth(target.fb, double4(0, 0, 0, 0), 1.0f);
  GPU_blend(GPU_BLEND_NONE);
  GPU_depth_test(GPU_DEPTH_LESS_EQUAL);
  GPU_depth_mask(true);
  FrameStats stats;
  for (const DrawLayer &layer : scene.layers) {
    if (!layer.pickable() || !layer_shown(layer, params)) {
      continue;
    }
    draw_layer(scene, layer, params, true, stats);
  }
  GPU_depth_test(GPU_DEPTH_NONE);
}

}  // namespace stk::viewer_gpu
