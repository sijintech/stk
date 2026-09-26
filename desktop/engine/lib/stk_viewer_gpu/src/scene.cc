/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "scene.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <type_traits>

#include "GPU_capabilities.hh"
#include "GPU_texture.hh"

#include "stk/viewer/geometry.hh"

namespace stk::viewer_gpu {

using namespace blender;
using io::Json;
using viewer::dvec3;

namespace {

/* -------------------------------------------------------------------- */
/* JSON helpers */

const Json *member(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(std::string(key));
  return it == object.end() ? nullptr : &*it;
}

const Json &member_or_empty(const Json &object, std::string_view key)
{
  static const Json empty = Json::object();
  const Json *m = member(object, key);
  return m && m->is_object() ? *m : empty;
}

std::optional<dvec3> json_vec3(const Json *v)
{
  if (!v || !v->is_array() || v->size() != 3) {
    return std::nullopt;
  }
  dvec3 out;
  for (size_t i = 0; i < 3; i++) {
    if (!io::is_finite_number((*v)[i])) {
      return std::nullopt;
    }
    out[i] = io::number_value((*v)[i]);
  }
  return out;
}

std::optional<std::array<double, 2>> json_pair(const Json *v)
{
  if (!v || !v->is_array() || v->size() != 2 || !io::is_finite_number((*v)[0]) ||
      !io::is_finite_number((*v)[1]))
  {
    return std::nullopt;
  }
  return std::array<double, 2>{io::number_value((*v)[0]), io::number_value((*v)[1])};
}

/* -------------------------------------------------------------------- */
/* Content hashing (derived buffers) */

uint64_t fnv1a(std::span<const uint8_t> bytes, uint64_t h = 1469598103934665603ull)
{
  for (const uint8_t b : bytes) {
    h ^= b;
    h *= 1099511628211ull;
  }
  return h;
}

template<typename T> std::span<const uint8_t> as_bytes(std::span<const T> s)
{
  return {reinterpret_cast<const uint8_t *>(s.data()), s.size_bytes()};
}

template<typename T> std::string content_key(std::string_view kind, std::span<const T> data)
{
  char buf[64];
  std::snprintf(buf, sizeof(buf), ":%016llx:%zu", (unsigned long long)fnv1a(as_bytes(data)), data.size_bytes());
  return std::string(kind) + buf;
}

std::string accessor_key(const io::Payload &p, const io::PayloadAccessor &a)
{
  return "acc:" + p.buffers[a.buffer].sha256 + ":" + std::to_string(a.byte_offset) + ":" +
         std::to_string(a.byte_size());
}

template<typename T> ResourcePtr upload(ResourceCache &cache, std::string_view kind, std::span<const T> data)
{
  const std::string key = content_key(kind, data);
  if constexpr (std::is_same_v<T, float>) {
    return cache.get(key, [&] { return make_float_storage(data, "stk_viewer_derived"); });
  }
  return cache.get(key, [&] { return make_storage(as_bytes(data), "stk_viewer_derived"); });
}

/** A raw accessor upload; f32 accessors (positions, normals) pass the float upload gate. */
ResourcePtr upload_accessor(ResourceCache &cache, const io::Payload &p, const io::PayloadAccessor &a)
{
  return cache.get(accessor_key(p, a), [&] {
    const std::span<const uint8_t> bytes = p.accessor_bytes(a);
    if (a.type == io::ComponentType::F32) {
      return make_float_storage({reinterpret_cast<const float *>(bytes.data()), bytes.size() / 4},
                                "stk_viewer_accessor");
    }
    return make_storage(bytes, "stk_viewer_accessor");
  });
}

/** `values` with every non-finite value replaced by `replacement` (nullopt when all are finite). */
std::optional<std::vector<float>> finite_copy(std::span<const float> values, float replacement = 0.0f)
{
  if (std::all_of(values.begin(), values.end(), [](float v) { return std::isfinite(v); })) {
    return std::nullopt;
  }
  std::vector<float> out(values.begin(), values.end());
  for (float &v : out) {
    if (!std::isfinite(v)) {
      v = replacement;
    }
  }
  return out;
}

ResourcePtr dummy_storage(ResourceCache &cache)
{
  return cache.get("dummy16", [] { return make_storage({}, "stk_viewer_dummy"); });
}

/* -------------------------------------------------------------------- */
/* Textures */

ResourcePtr make_texture_rgba8(const char *name, int w, int h, const uint8_t *rgba, bool linear)
{
  auto r = std::make_shared<GpuResource>();
  r->texture = GPU_texture_create_2d(name, w, h, 1, gpu::TextureFormat::UNORM_8_8_8_8,
                                     GPU_TEXTURE_USAGE_SHADER_READ, nullptr);
  GPU_texture_update(r->texture, GPU_DATA_UBYTE, rgba);
  GPU_texture_filter_mode(r->texture, linear);
  GPU_texture_extend_mode(r->texture, GPU_SAMPLER_EXTEND_MODE_EXTEND);
  r->bytes = uint64_t(w) * h * 4;
  return r;
}

ResourcePtr lut_texture(ResourceCache &cache, const viewer::ContinuousColormap &cm)
{
  const std::array<viewer::RGBA8, 259> texels = cm.texture();
  std::string key = "lut:";
  key.append(reinterpret_cast<const char *>(texels.data()), sizeof(texels));
  return cache.get(key, [&] { return make_texture_rgba8("stk_viewer_lut", 259, 1, texels[0].data(), false); });
}

ResourcePtr dummy_lut(ResourceCache &cache)
{
  return lut_texture(cache, viewer::grey_colormap());
}

/* -------------------------------------------------------------------- */
/* Positions, indices */

std::span<const float> positions_of(const io::Payload &p, const std::string &id, std::vector<float> &owned)
{
  const io::PayloadAccessor &a = p.accessor(id);
  if (a.type == io::ComponentType::F32 && !a.normalized) {
    return p.view<float>(id);
  }
  owned = p.floats(id);
  return owned;
}

ResourcePtr upload_positions(ResourceCache &cache, const io::Payload &p, const std::string &id,
                             std::span<const float> positions)
{
  const io::PayloadAccessor &a = p.accessor(id);
  if (a.type == io::ComponentType::F32 && !a.normalized) {
    return upload_accessor(cache, p, a);
  }
  return upload(cache, "pos", positions);
}

struct IndexUpload {
  ResourcePtr buffer;
  bool u16 = false;
  viewer::IndexSpan span;
  std::vector<uint32_t> owned;
};

IndexUpload upload_indices(ResourceCache &cache, const io::Payload &p, const std::string &id)
{
  IndexUpload out;
  const io::PayloadAccessor &a = p.accessor(id);
  if (a.type == io::ComponentType::U32) {
    out.buffer = upload_accessor(cache, p, a);
    out.span = p.view<uint32_t>(id);
  }
  else if (a.type == io::ComponentType::U16) {
    out.buffer = upload_accessor(cache, p, a);
    out.u16 = true;
    out.span = p.view<uint16_t>(id);
  }
  else {
    const std::vector<double> d = p.doubles(id);
    out.owned.resize(d.size());
    for (size_t i = 0; i < d.size(); i++) {
      out.owned[i] = uint32_t(std::max(0.0, d[i]));
    }
    out.buffer = upload(cache, "idx", std::span<const uint32_t>(out.owned));
    out.span = std::span<const uint32_t>(out.owned);
  }
  return out;
}

uint32_t index_at(const viewer::IndexSpan &span, size_t i)
{
  return std::visit([i](auto s) -> uint32_t { return uint32_t(s[i]); }, span);
}

size_t index_count(const viewer::IndexSpan &span)
{
  return std::visit([](auto s) { return s.size(); }, span);
}

/* -------------------------------------------------------------------- */
/* Colours */

/* s_cval value of a NaN (STK_NAN_SENTINEL in stk_common_lib.glsl): the finite float with these
 * bits (-3.4028232e38). Real LUT coordinates are clamped to +-kMaxT, so they never collide. */
constexpr uint32_t kNanSentinelBits = 0xFF7FFFFEu;
constexpr float kMaxT = 1e6f; /* keeps interpolated varyings far from float32 overflow */

float nan_sentinel()
{
  float f;
  std::memcpy(&f, &kNanSentinelBits, 4);
  return f;
}

bool is_nan_sentinel(const float t)
{
  uint32_t bits;
  std::memcpy(&bits, &t, 4);
  return bits == kNanSentinelBits;
}

/** The GPU bin of a float t (stk_lut_texel in stk_common_lib.glsl, texel 258 for the sentinel). */
int gpu_texel(const float t)
{
  if (std::isnan(t) || is_nan_sentinel(t)) {
    return 258;
  }
  if (t < 0.0f) {
    return 0;
  }
  if (t > 1.0f) {
    return 257;
  }
  return 1 + std::min(255, int(std::floor(t * 256.0f)));
}

/**
 * float32 t whose GPU bin equals the exact float64 bin of v over [lo, hi] (spec §5; the model's
 * ContinuousColormap::texel). t is kept at least kBinMargin inside its bin, so interpolating equal
 * vertex values across a triangle (rounding of the barycentric sum, perspective correction) can
 * never move a fragment into a neighbouring bin; 2^-22 is 1/16384 of a bin, invisible elsewhere.
 */
float exact_t(const double v, const double lo, const double hi)
{
  constexpr float kBinMargin = 1.0f / float(1 << 22);
  if (std::isnan(v)) {
    /* No NaN on the GPU (Metal fast math): a sentinel the shaders test as an integer. */
    return nan_sentinel();
  }
  const int want = viewer::ContinuousColormap::texel(v, lo, hi);
  const double td = hi == lo ? 0.5 : (v - lo) / (hi - lo);
  float t = std::isfinite(td) ? float(std::clamp(td, -double(kMaxT), double(kMaxT))) : (td > 0 ? 2.0f : -1.0f);
  if (want == 0) { /* below */
    t = std::min(t, -kBinMargin);
  }
  else if (want == 257) { /* above */
    t = std::max(t, 1.0f + 4 * kBinMargin);
  }
  else {
    const int bin = want - 1;
    const float lo_t = float(bin) / 256.0f + kBinMargin;
    const float hi_t = bin == 255 ? 1.0f : float(bin + 1) / 256.0f - kBinMargin;
    t = std::clamp(t, lo_t, hi_t);
  }
  for (int guard = 0; guard < 64 && gpu_texel(t) != want; guard++) {
    t = std::nextafter(t, gpu_texel(t) < want ? std::numeric_limits<float>::infinity() :
                                                -std::numeric_limits<float>::infinity());
  }
  return t;
}

uint32_t pack_rgba(const viewer::RGBA8 &c)
{
  return uint32_t(c[0]) | (uint32_t(c[1]) << 8) | (uint32_t(c[2]) << 16) | (uint32_t(c[3]) << 24);
}

const Json *own_attribute(const Json &layer, const Json *name)
{
  if (!name || !name->is_string()) {
    return nullptr;
  }
  const Json *attrs = member(layer, "attributes");
  return attrs ? member(*attrs, name->get<std::string>()) : nullptr;
}

std::string attribute_association(const Json &layer, const Json &spec)
{
  const Json *attr = own_attribute(layer, member(spec, "attribute"));
  return attr && io::get_string(*attr, "association", "point") == "cell" ? "cell" : "point";
}

/**
 * Resolve the colour of `count` tuples (points or cells per `association`).
 * `primitive` (point indices of each element, `prim_size` per element) lets categorical and
 * direction point colours of multi-point elements become exact per-element colours (majority of
 * the element's points, else its first point).
 */
ColorBinding build_color(ResourceCache &cache,
                         const io::Payload &p,
                         const Json &layer,
                         const Json &spec,
                         size_t points,
                         size_t cells,
                         std::vector<std::string> &warnings,
                         std::span<const float> vectors = {},
                         const viewer::IndexSpan *primitive = nullptr,
                         int prim_size = 1,
                         const std::vector<uint32_t> *cell_of_segment = nullptr)
{
  ColorBinding out;
  const std::string association = spec.is_object() && io::get_string(spec, "by") == "attribute" ?
                                       attribute_association(layer, spec) :
                                       std::string("point");
  const size_t count = association == "cell" ? cells : points;
  viewer::ColorResult r = viewer::layer_colors(p, layer, spec, count, association, vectors, 3);
  for (std::string &w : r.warnings) {
    warnings.push_back(std::move(w));
  }
  out.solid = {float(r.solid[0]), float(r.solid[1]), float(r.solid[2]), float(r.solid[3])};
  out.lut = dummy_lut(cache);
  if (r.colors.empty()) {
    out.mode = flag::color_solid;
    out.values = dummy_storage(cache);
    out.translucent = out.solid[3] < 1.0f;
    return out;
  }
  out.cell = association == "cell";
  const bool continuous = io::get_string(spec, "by") == "attribute" && !r.categorical && r.range;
  if (continuous) {
    /* A continuous attribute result guarantees resolved scalars, using the shared normalization,
     * component and range rules of layer_colors. */
    const auto scalars = viewer::layer_scalars(p, layer, spec);
    const std::vector<double> &values = scalars->values;
    const double lo = (*r.range)[0], hi = (*r.range)[1];
    std::vector<float> t(count);
    for (size_t i = 0; i < count; i++) {
      t[i] = exact_t(i < values.size() ? values[i] : std::numeric_limits<double>::quiet_NaN(), lo, hi);
    }
    if (cell_of_segment) {
      std::vector<float> expanded(cell_of_segment->size());
      for (size_t s = 0; s < expanded.size(); s++) {
        expanded[s] = t[(*cell_of_segment)[s]];
      }
      t = std::move(expanded);
    }
    std::optional<viewer::Colormap> cm;
    if (r.colormap) {
      cm = viewer::resolve_colormap(p, *r.colormap);
    }
    out.lut = lut_texture(cache, cm && cm->continuous ? *cm->continuous : viewer::grey_colormap());
    out.mode = flag::color_lut;
    out.flat_value = r.nearest;
    out.values = upload(cache, "cval", std::span<const float>(t));
    /* Translucent when a reachable LUT entry has alpha < 255. */
    const auto texels = (cm && cm->continuous ? *cm->continuous : viewer::grey_colormap()).texture();
    for (const float v : t) {
      if (texels[size_t(gpu_texel(v))][3] < 255) {
        out.translucent = true;
        break;
      }
    }
    return out;
  }
  /* Exact RGBA per tuple. */
  std::vector<uint32_t> rgba(r.colors.size());
  bool translucent = false;
  for (size_t i = 0; i < rgba.size(); i++) {
    rgba[i] = pack_rgba(r.colors[i]);
    translucent = translucent || r.colors[i][3] < 255;
  }
  out.translucent = translucent;
  out.mode = flag::color_rgba;
  if (!out.cell && r.categorical && primitive && prim_size > 1) {
    /* Categorical point labels on triangles/segments: one exact colour per element. */
    const size_t n = index_count(*primitive) / size_t(prim_size);
    std::vector<uint32_t> per(n);
    for (size_t e = 0; e < n; e++) {
      uint32_t c[3] = {0, 0, 0};
      for (int k = 0; k < prim_size && k < 3; k++) {
        const uint32_t vi = index_at(*primitive, e * size_t(prim_size) + size_t(k));
        c[k] = vi < rgba.size() ? rgba[vi] : 0x80808080u;
      }
      per[e] = (prim_size == 3 && c[1] == c[2]) ? c[1] : c[0];
    }
    rgba = std::move(per);
    out.cell = true;
  }
  else if (out.cell && cell_of_segment) {
    std::vector<uint32_t> expanded(cell_of_segment->size());
    for (size_t s = 0; s < expanded.size(); s++) {
      expanded[s] = rgba[(*cell_of_segment)[s]];
    }
    rgba = std::move(expanded);
  }
  out.flat_value = r.nearest;
  out.values = upload(cache, "cval", std::span<const uint32_t>(rgba));
  return out;
}

/* -------------------------------------------------------------------- */
/* Layers */

struct Builder {
  ResourceCache &cache;
  const io::Payload &p;
  GpuScene &scene;

  void triangles(DrawLayer &L)
  {
    const Json &layer = *L.json;
    const Json &app = member_or_empty(layer, "appearance");
    const Json &spec = member_or_empty(app, "color");
    L.flat_shading = io::get_string(app, "shading") == "flat";
    L.lighting = io::get_bool(app, "lighting", true);
    /* LOD levels (coarse to fine) then the main arrays. */
    std::vector<Json> levels;
    if (const Json *lods = member(layer, "lods"); lods && lods->is_array()) {
      for (const Json &lod : *lods) {
        if (!lod.is_object()) {
          continue;
        }
        Json l = layer;
        for (const char *k : {"positions", "normals", "indices", "attributes"}) {
          if (lod.contains(k)) {
            l[k] = lod[k];
          }
          else if (std::string_view(k) == "normals") {
            l.erase(k);
          }
        }
        levels.push_back(std::move(l));
      }
    }
    for (size_t i = 0; i < levels.size() + 1; i++) {
      const Json &src = i < levels.size() ? levels[i] : layer;
      L.mesh.push_back(mesh_level(L, src, spec, i == levels.size()));
    }
    const Json &edges = member_or_empty(app, "edges");
    if (io::get_bool(edges, "visible", false)) {
      MeshLevel &m = L.mesh.back();
      L.edges_visible = true;
      LineData &e = L.edges;
      e.positions = m.positions;
      e.pos = m.pos;
      const size_t tris = size_t(m.triangles);
      e.pairs.resize(tris * 6);
      for (size_t t = 0; t < tris; t++) {
        uint32_t v[3];
        for (int k = 0; k < 3; k++) {
          v[k] = index_count(m.indices) ? index_at(m.indices, t * 3 + size_t(k)) : uint32_t(t * 3 + size_t(k));
        }
        const uint32_t pairs[6] = {v[0], v[1], v[1], v[2], v[2], v[0]};
        std::copy(pairs, pairs + 6, e.pairs.begin() + std::ptrdiff_t(t * 6));
      }
      e.idx = upload(cache, "edges", std::span<const uint32_t>(e.pairs));
      e.has_index = true;
      e.segments = tris * 3;
      e.width_px = float(io::get_number(edges, "width_px", 1.0));
      e.color.mode = flag::color_solid;
      std::array<double, 3> c{0, 0, 0};
      if (const Json *ec = member(edges, "color"); ec && ec->is_array() && ec->size() >= 3) {
        for (size_t k = 0; k < 3; k++) {
          c[k] = io::is_finite_number((*ec)[k]) ? io::number_value((*ec)[k]) : 0.0;
        }
      }
      e.color.solid = {float(c[0]), float(c[1]), float(c[2]), 1.0f};
      e.color.values = dummy_storage(cache);
      e.color.lut = dummy_lut(cache);
    }
  }

  MeshLevel mesh_level(DrawLayer &L, const Json &src, const Json &spec, bool finest)
  {
    MeshLevel m;
    const std::string pos_id = io::get_string(src, "positions");
    m.positions = positions_of(p, pos_id, m.owned_positions);
    m.pos = upload_positions(cache, p, pos_id, m.positions);
    const size_t points = m.positions.size() / 3;
    if (const std::string idx_id = io::get_string(src, "indices"); !idx_id.empty()) {
      IndexUpload iu = upload_indices(cache, p, idx_id);
      m.idx = iu.buffer;
      m.index_u16 = iu.u16;
      m.has_index = true;
      if (!iu.owned.empty()) {
        /* Keep converted indices alive for picking. */
        auto holder = std::make_shared<std::vector<uint32_t>>(std::move(iu.owned));
        owned_indices.push_back(holder);
        m.indices = std::span<const uint32_t>(*holder);
      }
      else {
        m.indices = iu.span;
      }
      m.triangles = index_count(m.indices) / 3;
    }
    else {
      m.idx = dummy_storage(cache);
      m.indices = std::span<const uint32_t>();
      m.triangles = points / 3;
    }
    const bool smooth = !L.flat_shading;
    if (const std::string nrm_id = io::get_string(src, "normals"); !nrm_id.empty() && smooth) {
      std::vector<float> owned;
      const std::span<const float> n = positions_of(p, nrm_id, owned);
      /* Non-finite normals become 0 (the shader lights zero normals as facing the viewer). */
      if (auto finite = finite_copy(n)) {
        m.nrm = upload(cache, "nrm", std::span<const float>(*finite));
      }
      else {
        m.nrm = owned.empty() ? upload_accessor(cache, p, p.accessor(nrm_id)) :
                                upload(cache, "nrm", std::span<const float>(owned));
      }
      m.has_normals = n.size() == m.positions.size();
    }
    else if (smooth && L.lighting) {
      viewer::IndexSpan span = m.indices;
      std::vector<uint32_t> seq;
      if (!m.has_index) {
        seq.resize(points);
        for (size_t i = 0; i < points; i++) {
          seq[i] = uint32_t(i);
        }
        span = std::span<const uint32_t>(seq);
      }
      const std::vector<float> n = viewer::smooth_normals(m.positions, span);
      m.nrm = upload(cache, "nrm", std::span<const float>(n));
      m.has_normals = true;
    }
    else {
      m.nrm = dummy_storage(cache);
    }
    std::vector<uint32_t> seq;
    viewer::IndexSpan prim = m.indices;
    if (!m.has_index) {
      seq.resize(size_t(m.triangles) * 3);
      for (size_t i = 0; i < seq.size(); i++) {
        seq[i] = uint32_t(i);
      }
      prim = std::span<const uint32_t>(seq);
    }
    m.color = build_color(cache, p, src, spec, points, size_t(m.triangles), finest ? scene.warnings : scratch, {}, &prim, 3);
    return m;
  }

  void slice(DrawLayer &L)
  {
    const Json &layer = *L.json;
    const Json &app = member_or_empty(layer, "appearance");
    const Json &spec = member_or_empty(app, "color");
    L.lighting = io::get_bool(app, "lighting", false);
    SliceData &s = L.slice;
    const Json *size = member(layer, "size");
    if (size && size->is_array() && size->size() == 2) {
      auto dim = [](const Json &v) { return v.is_number_integer() ? std::max<int64_t>(1, v.get<int64_t>()) : 1; };
      s.width = uint32_t(dim((*size)[0]));
      s.height = uint32_t(dim((*size)[1]));
    }
    const Json &plane = member_or_empty(layer, "plane");
    s.origin = json_vec3(member(plane, "origin")).value_or(dvec3{});
    s.u = json_vec3(member(plane, "u")).value_or(dvec3{1, 0, 0});
    s.v = json_vec3(member(plane, "v")).value_or(dvec3{0, 1, 0});
    const size_t n = size_t(s.width) * s.height;
    viewer::ColorResult r = viewer::layer_colors(p, layer, spec, n, "point");
    for (std::string &w : r.warnings) {
      scene.warnings.push_back(std::move(w));
    }
    std::vector<uint8_t> rgba(n * 4);
    bool translucent = false;
    if (r.colors.empty()) {
      const viewer::RGBA8 c = viewer::rgba8(std::span<const double>(r.solid.data(), 4));
      for (size_t i = 0; i < n; i++) {
        std::memcpy(&rgba[i * 4], c.data(), 4);
      }
      translucent = c[3] < 255;
    }
    else {
      for (size_t i = 0; i < n; i++) {
        std::memcpy(&rgba[i * 4], r.colors[i].data(), 4);
        translucent = translucent || r.colors[i][3] < 255;
      }
    }
    const std::string interpolate = io::get_string(spec, "interpolate", "linear");
    const bool linear = !(r.nearest || r.categorical) && interpolate != "nearest";
    const std::string key = content_key("slice", std::span<const uint8_t>(rgba)) + (linear ? ":lin" : ":nn") + ":" +
                            std::to_string(s.width);
    const int max_tex = GPU_max_texture_size();
    if (int(s.width) > max_tex || int(s.height) > max_tex) {
      scene.warnings.push_back("layer " + L.id + ": slice image exceeds the GPU texture size " +
                               std::to_string(max_tex));
      return;
    }
    s.texture = cache.get(key, [&] {
      return make_texture_rgba8("stk_viewer_slice", int(s.width), int(s.height), rgba.data(), linear);
    });
    s.color.translucent = translucent;
  }

  void lines(DrawLayer &L)
  {
    const Json &layer = *L.json;
    const Json &app = member_or_empty(layer, "appearance");
    const Json &spec = member_or_empty(app, "color");
    L.lighting = io::get_bool(app, "lighting", false);
    LineData &d = L.lines;
    d.width_px = float(io::get_number(app, "width_px", 1.0));
    const std::string pos_id = io::get_string(layer, "positions");
    d.positions = positions_of(p, pos_id, d.owned_positions);
    d.pos = upload_positions(cache, p, pos_id, d.positions);
    const size_t points = d.positions.size() / 3;
    IndexUpload iu = upload_indices(cache, p, io::get_string(layer, "indices"));
    std::vector<uint32_t> cell_of_segment;
    size_t cells = 0;
    if (io::get_string(layer, "mode", "segments") == "polylines") {
      const std::vector<double> offsets = p.doubles(io::get_string(layer, "offsets"));
      const size_t lines = offsets.empty() ? 0 : offsets.size() - 1;
      for (size_t l = 0; l < lines; l++) {
        const size_t a = size_t(offsets[l]), b = size_t(offsets[l + 1]);
        for (size_t k = a; k + 1 < b; k++) {
          d.pairs.push_back(index_at(iu.span, k));
          d.pairs.push_back(index_at(iu.span, k + 1));
          cell_of_segment.push_back(uint32_t(l));
        }
      }
      d.idx = upload(cache, "pairs", std::span<const uint32_t>(d.pairs));
      d.has_index = true;
      d.segments = d.pairs.size() / 2;
      /* web perSegment: a cell attribute with one value per segment is used as is. */
      cells = lines;
      const Json *attr = own_attribute(layer, member(spec, "attribute"));
      if (attr && io::get_string(*attr, "association") == "cell" &&
          p.accessor(io::get_string(*attr, "accessor")).count != lines)
      {
        cells = d.segments;
        cell_of_segment.clear();
      }
    }
    else {
      d.idx = iu.buffer;
      d.index_u16 = iu.u16;
      d.has_index = true;
      const size_t n = index_count(iu.span);
      d.pairs.resize(n);
      for (size_t i = 0; i < n; i++) {
        d.pairs[i] = index_at(iu.span, i);
      }
      d.segments = n / 2;
      cells = d.segments;
    }
    const viewer::IndexSpan prim = std::span<const uint32_t>(d.pairs);
    d.color = build_color(cache, p, layer, spec, points, cells, scene.warnings, {}, &prim, 2,
                          cell_of_segment.empty() ? nullptr : &cell_of_segment);
  }

  void points(DrawLayer &L)
  {
    const Json &layer = *L.json;
    const Json &app = member_or_empty(layer, "appearance");
    const Json &spec = member_or_empty(app, "color");
    PointData &d = L.points;
    const std::string pos_id = io::get_string(layer, "positions");
    d.positions = positions_of(p, pos_id, d.owned_positions);
    d.pos = upload_positions(cache, p, pos_id, d.positions);
    d.count = d.positions.size() / 3;
    d.size_px = float(io::get_number(app, "size_px", 3.0));
    d.spheres = io::get_string(app, "render_as", "points") == "spheres";
    const Json *radius = member(app, "radius");
    d.radius = radius && io::is_finite_number(*radius) ? float(io::number_value(*radius)) : 0.0f;
    const std::string radii_id = io::get_string(layer, "radii");
    d.world_spheres = d.spheres && (!radii_id.empty() || d.radius > 0);
    if (!radii_id.empty() && d.spheres) {
      d.radii_cpu = p.floats(radii_id);
      /* A non-finite radius draws (and picks) nothing, as a zero radius. */
      if (auto finite = finite_copy(d.radii_cpu)) {
        d.radii_cpu = std::move(*finite);
      }
      d.radii = upload(cache, "radii", std::span<const float>(d.radii_cpu));
    }
    else {
      d.radii = dummy_storage(cache);
    }
    if (d.world_spheres && d.radius <= 0 && radii_id.empty()) {
      d.radius = 0.5f;
    }
    d.shuffled = io::get_bool(member_or_empty(layer, "progressive"), "shuffled", false);
    L.lighting = io::get_bool(app, "lighting", d.spheres);
    d.color = build_color(cache, p, layer, spec, size_t(d.count), size_t(d.count), scene.warnings);
  }

  void instances(DrawLayer &L)
  {
    const Json &layer = *L.json;
    const Json &app = member_or_empty(layer, "appearance");
    const Json &spec = member_or_empty(app, "color");
    const Json &glyph = member_or_empty(layer, "glyph");
    GlyphData &g = L.glyphs;
    L.lighting = io::get_bool(app, "lighting", true);
    g.positions = p.floats(io::get_string(layer, "positions"));
    g.directions = p.floats(io::get_string(layer, "directions"));
    const size_t n = g.positions.size() / 3;
    std::vector<float> scales;
    if (const std::string s = io::get_string(layer, "scales"); !s.empty()) {
      scales = p.floats(s);
    }
    const viewer::GlyphScale scale = viewer::GlyphScale::from_json(member_or_empty(app, "scale"));
    std::vector<double> attribute;
    int attribute_components = 1;
    if (scales.empty() && scale.by == viewer::ScaleMode::Attribute) {
      const Json name = scale.attribute;
      if (const Json *attr = own_attribute(layer, &name)) {
        const std::string acc = io::get_string(*attr, "accessor");
        attribute = p.doubles(acc);
        attribute_components = int(p.accessor(acc).components);
      }
      else {
        scene.warnings.push_back("layer " + L.id + ": scale attribute " + scale.attribute + " is missing");
      }
    }
    g.scales = viewer::instance_scales(g.directions, scales, scale, attribute, attribute_components);
    const std::string shape_name = io::get_string(glyph, "shape", "arrow");
    std::optional<viewer::GlyphShape> shape = viewer::parse_glyph_shape(shape_name);
    if (!shape) {
      scene.warnings.push_back("layer " + L.id + ": unknown glyph shape " + shape_name + ", using arrow");
      shape = viewer::GlyphShape::Arrow;
    }
    const int resolution = int(std::clamp<int64_t>(io::get_int(glyph, "resolution", 8), 3, 256));
    const bool center = io::get_bool(glyph, "center", false);
    g.glyph = viewer::glyph_mesh(*shape, resolution, center);
    g.shuffled = io::get_bool(member_or_empty(layer, "progressive"), "shuffled", false);

    /* Colours per payload instance, gathered for the drawn ones. */
    ColorBinding all = build_color(cache, p, layer, spec, n, n, scene.warnings, g.directions);
    std::vector<float> inst;
    for (size_t i = 0; i < n; i++) {
      if (!std::isfinite(g.scales[i])) {
        continue;
      }
      /* Scales that would overflow float32 on the GPU (|entry| > 1e30) are dropped like non-finite ones. */
      const dvec3 dir{g.directions[i * 3], g.directions[i * 3 + 1], g.directions[i * 3 + 2]};
      const viewer::dmat4 m = viewer::instance_matrix(dvec3{}, dir, g.scales[i]);
      bool finite = true;
      for (int row = 0; row < 3 && finite; row++) {
        for (int col = 0; col < 3 && finite; col++) {
          finite = std::abs(m.m[size_t(col)][size_t(row)]) <= 1e30; /* false for NaN */
        }
      }
      if (finite) {
        g.kept.push_back(uint32_t(i));
      }
    }
    g.count = g.kept.size();
    ColorBinding color = all;
    if (all.mode != flag::color_solid && g.kept.size() != n) {
      std::vector<float> t;
      std::vector<uint32_t> rgba;
      /* Recompute gathered values from the payload-order buffer contents. */
      viewer::ColorResult r = viewer::layer_colors(p, layer, spec, n, "point", g.directions, 3);
      if (all.mode == flag::color_rgba) {
        for (const uint32_t i : g.kept) {
          rgba.push_back(pack_rgba(r.colors[i]));
        }
        color.values = upload(cache, "cval", std::span<const uint32_t>(rgba));
      }
      else {
        const auto scalars = viewer::layer_scalars(p, layer, spec);
        const std::vector<double> &values = scalars->values;
        for (const uint32_t i : g.kept) {
          t.push_back(exact_t(i < values.size() ? values[i] : NAN, (*r.range)[0], (*r.range)[1]));
        }
        color.values = upload(cache, "cval", std::span<const float>(t));
      }
    }
    g.color = color;
    if (*shape == viewer::GlyphShape::Line) {
      /* Line glyphs: one segment per instance (base and tip of the transformed unit segment). */
      g.line_shape = true;
      LineData &d = g.lines;
      const auto &pts = g.glyph.points;
      for (const uint32_t i : g.kept) {
        const dvec3 pos{g.positions[i * 3], g.positions[i * 3 + 1], g.positions[i * 3 + 2]};
        const dvec3 dir{g.directions[i * 3], g.directions[i * 3 + 1], g.directions[i * 3 + 2]};
        const viewer::dmat4 m = viewer::instance_matrix(pos, dir, g.scales[i]);
        for (size_t k = 0; k < 2 && k < pts.size(); k++) {
          const dvec3 q = m.transform_point(dvec3::from(pts[k]));
          d.owned_positions.insert(d.owned_positions.end(), {float(q.x), float(q.y), float(q.z)});
        }
      }
      d.positions = d.owned_positions;
      d.pos = upload(cache, "pos", std::span<const float>(d.owned_positions));
      d.idx = dummy_storage(cache);
      d.has_index = false;
      d.segments = g.kept.size();
      d.width_px = 1.0f;
      d.color = color;
      d.color.cell = true;
      L.lighting = false;
      return;
    }
    /* Mesh soup (position, normal per vertex): smooth normals where VTK provides them. */
    std::vector<float> soup;
    const std::vector<uint32_t> tris = g.glyph.triangles();
    if (!g.glyph.normals.empty()) {
      for (const uint32_t v : tris) {
        const auto &q = g.glyph.points[v];
        const auto &nn = g.glyph.normals[v];
        soup.insert(soup.end(), {q[0], q[1], q[2], nn[0], nn[1], nn[2]});
      }
    }
    else {
      std::vector<std::array<float, 3>> fp, fn;
      g.glyph.flat(fp, fn);
      for (size_t k = 0; k < fp.size(); k++) {
        soup.insert(soup.end(), {fp[k][0], fp[k][1], fp[k][2], fn[k][0], fn[k][1], fn[k][2]});
      }
    }
    g.mesh_vertices = soup.size() / 6;
    g.mesh = upload(cache, "glyph", std::span<const float>(soup));
    inst.reserve(g.kept.size() * 12);
    for (const uint32_t i : g.kept) {
      const dvec3 pos{g.positions[i * 3], g.positions[i * 3 + 1], g.positions[i * 3 + 2]};
      const dvec3 dir{g.directions[i * 3], g.directions[i * 3 + 1], g.directions[i * 3 + 2]};
      const viewer::dmat4 m = viewer::instance_matrix(pos, dir, g.scales[i]);
      inst.insert(inst.end(), {g.positions[i * 3], g.positions[i * 3 + 1], g.positions[i * 3 + 2]});
      for (int row = 0; row < 3; row++) {
        for (int col = 0; col < 3; col++) {
          inst.push_back(float(m.m[size_t(col)][size_t(row)]));
        }
      }
    }
    g.inst = upload(cache, "inst", std::span<const float>(inst));
  }

  void volume(DrawLayer &L)
  {
    const Json &layer = *L.json;
    VolumeData &v = L.volume;
    v.transfer = viewer::volume_transfer(p, layer);
    for (std::string &w : v.transfer.warnings) {
      scene.warnings.push_back(std::move(w));
    }
    struct Src {
      std::string data;
      std::array<int64_t, 3> dims;
      viewer::VolumeGrid grid;
    };
    std::vector<Src> sources;
    if (const Json *lods = member(layer, "lods"); lods && lods->is_array()) {
      for (const Json &lod : *lods) {
        const Json *dims = member(lod, "dimensions");
        const auto spacing = json_vec3(member(lod, "spacing"));
        if (!dims || !dims->is_array() || dims->size() != 3 || !spacing) {
          continue;
        }
        Src s;
        s.data = io::get_string(lod, "data");
        for (size_t k = 0; k < 3; k++) {
          s.dims[k] = (*dims)[k].is_number_integer() ? (*dims)[k].get<int64_t>() : 1;
        }
        s.grid = v.transfer.grid;
        s.grid.dimensions = s.dims;
        s.grid.spacing = *spacing;
        sources.push_back(s);
      }
    }
    sources.push_back({io::get_string(layer, "data"), v.transfer.grid.dimensions, v.transfer.grid});
    const int max3d = GPU_max_texture_3d_size();
    for (const Src &s : sources) {
      if (s.dims[0] > max3d || s.dims[1] > max3d || s.dims[2] > max3d) {
        scene.warnings.push_back("layer " + L.id + ": volume level exceeds the GPU 3D texture size " +
                                 std::to_string(max3d));
        continue;
      }
      v.levels.push_back(volume_level(L, s.data, s.dims, s.grid));
    }
  }

  VolumeLevel volume_level(DrawLayer &L,
                           const std::string &data_id,
                           const std::array<int64_t, 3> &dims,
                           const viewer::VolumeGrid &grid)
  {
    VolumeLevel lv;
    lv.dims = dims;
    lv.grid = grid;
    lv.voxels = uint64_t(dims[0]) * uint64_t(dims[1]) * uint64_t(dims[2]);
    const io::PayloadAccessor &a = p.accessor(data_id);
    const std::string key = accessor_key(p, a) + ":vol:" + std::to_string(dims[0]) + "x" +
                            std::to_string(dims[1]) + "x" + std::to_string(dims[2]);
    const bool u8 = a.type == io::ComponentType::U8;
    const bool u16 = a.type == io::ComponentType::U16;
    /* Texture value -> stored value (normalized accessors store x / 255 or x / 65535, web floats()). */
    lv.tex_scale = a.normalized ? 1.0 : u8 ? 255.0 : u16 ? 65535.0 : 1.0;
    /* Stored-value domain of the transfer-function LUT: the data range. */
    std::array<double, 2> range;
    std::vector<float> floats;
    if (u8) {
      range = viewer::stored_range(p.view<uint8_t>(data_id), a.normalized);
    }
    else if (u16) {
      range = viewer::stored_range(p.view<uint16_t>(data_id), a.normalized);
    }
    else {
      floats = p.floats(data_id);
      range = viewer::stored_range(std::span<const float>(floats));
    }
    const double lo = range[0], hi = range[1];
    lv.stored_lo = lo;
    lv.stored_hi = hi;
    /* Non-finite f32 voxels (no NaN/Inf on the GPU) become a finite value far below the data, which
     * the ray marcher skips as a hole (transparent); u8/u16 data has none. */
    if (!u8 && !u16) {
      const double gap = std::max(hi - lo, std::abs(lo)) + 1.0;
      lv.hole_below = std::max(lo - gap, -1e37);
      const float sentinel = float(std::max(lo - 2.0 * gap, -2e37));
      for (float &f : floats) {
        if (!std::isfinite(f)) {
          f = sentinel;
        }
      }
      check_finite_upload(floats, "volume data");
    }
    lv.texture = cache.get(key, [&] {
      auto r = std::make_shared<GpuResource>();
      const int w = int(dims[0]), h = int(dims[1]), d = int(dims[2]);
      const eGPUTextureUsage usage = GPU_TEXTURE_USAGE_SHADER_READ;
      if (u8) {
        r->texture = GPU_texture_create_3d("stk_viewer_volume", w, h, d, 1, gpu::TextureFormat::UNORM_8, usage, nullptr);
        GPU_texture_update(r->texture, GPU_DATA_UBYTE, p.view<uint8_t>(data_id).data());
        r->bytes = lv.voxels;
      }
      else if (u16) {
        const auto view = p.view<uint16_t>(data_id);
        std::vector<float> f(view.size());
        for (size_t i = 0; i < f.size(); i++) {
          f[i] = float(double(view[i]) / 65535.0);
        }
        r->texture = GPU_texture_create_3d("stk_viewer_volume", w, h, d, 1, gpu::TextureFormat::UNORM_16, usage, nullptr);
        GPU_texture_update(r->texture, GPU_DATA_FLOAT, f.data());
        r->bytes = lv.voxels * 2;
      }
      else {
        r->texture = GPU_texture_create_3d("stk_viewer_volume", w, h, d, 1, gpu::TextureFormat::SFLOAT_32, usage, nullptr);
        GPU_texture_update(r->texture, GPU_DATA_FLOAT, floats.data());
        r->bytes = lv.voxels * 4;
      }
      GPU_texture_extend_mode(r->texture, GPU_SAMPLER_EXTEND_MODE_EXTEND);
      return r;
    });
    GPU_texture_filter_mode(lv.texture->texture, !L.volume.transfer.nearest);
    /* Transfer-function LUT over the stored domain. */
    constexpr int kLut = 4096;
    std::vector<std::array<float, 4>> lut = viewer::transfer_lut(L.volume.transfer, lo, hi, kLut);
    std::vector<float> sanitized;
    if (check_finite_upload({lut[0].data(), lut.size() * 4}, "volume transfer function", &sanitized) > 0) {
      std::memcpy(lut[0].data(), sanitized.data(), sanitized.size() * 4);
    }
    const std::span<const float> flat(lut[0].data(), lut.size() * 4);
    const std::string tf_key = content_key("tf", flat) + (L.volume.transfer.nearest ? ":nn" : ":lin");
    lv.tf = cache.get(tf_key, [&] {
      auto r = std::make_shared<GpuResource>();
      r->texture = GPU_texture_create_2d("stk_viewer_tf", kLut, 1, 1, gpu::TextureFormat::SFLOAT_32_32_32_32,
                                         GPU_TEXTURE_USAGE_SHADER_READ, flat.data());
      GPU_texture_filter_mode(r->texture, !L.volume.transfer.nearest);
      GPU_texture_extend_mode(r->texture, GPU_SAMPLER_EXTEND_MODE_EXTEND);
      r->bytes = uint64_t(kLut) * 16;
      return r;
    });
    return lv;
  }

  void overlay(DrawLayer &L)
  {
    const Json &layer = *L.json;
    OverlayItem &o = L.overlay;
    o.kind = io::get_string(layer, "kind");
    o.anchor = viewer::overlay_anchor(layer);
    o.title = io::get_string(layer, "title");
    o.unit = io::get_string(layer, "unit");
    if (const auto off = json_pair(member(layer, "offset_px"))) {
      o.offset = *off;
      o.has_offset = true;
    }
    if (const auto size = json_pair(member(layer, "size_px"))) {
      o.size = *size;
      o.has_size = true;
    }
    const std::string cm_id = io::get_string(layer, "colormap");
    if (o.kind == "scalar_bar") {
      o.vertical = io::get_string(layer, "orientation", "vertical") != "horizontal";
      o.label_count = int(std::clamp<int64_t>(io::get_int(layer, "label_count", 5), 2, 20));
      o.format = io::get_string(layer, "format", ".3g");
      if (const auto range = json_pair(member(layer, "range"))) {
        o.range = *range;
      }
      if (auto cm = viewer::resolve_colormap(p, cm_id); cm && cm->continuous) {
        o.lut = *cm->continuous;
      }
      else {
        scene.warnings.push_back("overlay " + L.id + ": scalar bar colormap " + cm_id + " is not a continuous LUT");
      }
    }
    else if (o.kind == "legend") {
      o.columns = int(std::clamp<int64_t>(io::get_int(layer, "columns", 1), 1, 8));
      if (auto cm = viewer::resolve_colormap(p, cm_id); cm && cm->categorical) {
        const Json *values = member(layer, "values");
        o.legend = viewer::legend_items(*cm->categorical, values ? *values : Json());
      }
      else {
        scene.warnings.push_back("overlay " + L.id + ": legend colormap " + cm_id + " is not categorical");
      }
    }
    else if (o.kind == "orientation_legend") {
      if (const auto l = json_pair(member(layer, "lightness_range"))) {
        o.lightness = *l;
      }
    }
    else if (o.kind == "text") {
      o.text = io::get_string(layer, "text");
      o.font_size = io::get_number(layer, "font_size_px", 14.0);
      if (const auto c = json_vec3(member(layer, "color"))) {
        o.color = std::array<float, 3>{float(c->x), float(c->y), float(c->z)};
      }
    }
    else if (o.kind == "axes_triad") {
      if (const Json *labels = member(layer, "labels"); labels && labels->is_array() && labels->size() == 3) {
        for (size_t k = 0; k < 3; k++) {
          if ((*labels)[k].is_string()) {
            o.labels[k] = (*labels)[k].get<std::string>();
          }
        }
      }
    }
  }

  std::vector<std::string> scratch;
  std::vector<std::shared_ptr<std::vector<uint32_t>>> owned_indices;
};

LayerKind kind_of(std::string_view type)
{
  if (type == "triangles") {
    return LayerKind::Triangles;
  }
  if (type == "slice_image") {
    return LayerKind::SliceImage;
  }
  if (type == "lines") {
    return LayerKind::Lines;
  }
  if (type == "points") {
    return LayerKind::Points;
  }
  if (type == "instances") {
    return LayerKind::Instances;
  }
  if (type == "volume") {
    return LayerKind::Volume;
  }
  if (type == "overlay") {
    return LayerKind::Overlay;
  }
  return LayerKind::Unknown;
}

}  // namespace

std::string_view layer_kind_name(const LayerKind kind)
{
  switch (kind) {
    case LayerKind::Triangles:
      return "triangles";
    case LayerKind::SliceImage:
      return "slice_image";
    case LayerKind::Lines:
      return "lines";
    case LayerKind::Points:
      return "points";
    case LayerKind::Instances:
      return "instances";
    case LayerKind::Volume:
      return "volume";
    case LayerKind::Overlay:
      return "overlay";
    case LayerKind::Unknown:
      break;
  }
  return "unknown";
}

bool DrawLayer::translucent() const
{
  if (opacity < 1.0f) {
    return true;
  }
  switch (kind) {
    case LayerKind::Triangles:
      return !mesh.empty() && mesh.back().color.translucent;
    case LayerKind::Lines:
      return lines.color.translucent;
    case LayerKind::Points:
      return points.color.translucent;
    case LayerKind::Instances:
      return glyphs.color.translucent;
    case LayerKind::SliceImage:
      return slice.color.translucent;
    default:
      return false;
  }
}

uint64_t DrawLayer::elements() const
{
  switch (kind) {
    case LayerKind::Triangles:
      return mesh.empty() ? 0 : mesh.back().triangles;
    case LayerKind::Lines:
      return lines.segments;
    case LayerKind::Points:
      return points.count;
    case LayerKind::Instances:
      return glyphs.count;
    case LayerKind::SliceImage:
      return uint64_t(slice.width) * slice.height;
    case LayerKind::Volume:
      return volume.levels.empty() ? 0 : volume.levels.back().voxels;
    default:
      return 0;
  }
}

std::string scene_key(const io::Payload &payload)
{
  const std::string dump = payload.manifest.dump();
  char buf[48];
  std::snprintf(buf, sizeof(buf), "%016llx:%zu",
                (unsigned long long)fnv1a({reinterpret_cast<const uint8_t *>(dump.data()), dump.size()}),
                dump.size());
  return buf;
}

std::unique_ptr<GpuScene> build_scene(std::shared_ptr<const io::Payload> payload, ResourceCache &cache)
{
  auto scene = std::make_unique<GpuScene>();
  scene->payload = payload;
  scene->key = scene_key(*payload);
  const io::Payload &p = *payload;
  const Json &view = member_or_empty(p.manifest, "view");
  scene->camera_signature = viewer::camera_signature(view);
  scene->bounds = viewer::payload_bounds(p);
  const Json &background = member_or_empty(view, "background");
  if (const auto c = json_vec3(member(background, "color"))) {
    scene->background = {float(c->x), float(c->y), float(c->z)};
  }
  const std::string bg_type = io::get_string(background, "type", "solid");
  scene->transparent = bg_type == "transparent" || io::get_bool(member_or_empty(view, "render"), "transparent", false);
  if (bg_type == "gradient") {
    if (const auto c2 = json_vec3(member(background, "color2"))) {
      scene->background2 = std::array<float, 3>{float(c2->x), float(c2->y), float(c2->z)};
    }
  }
  const Json &lighting = member_or_empty(view, "lighting");
  scene->lighting = io::get_string(lighting, "preset", "three_point");
  scene->light_intensity = io::get_number(lighting, "intensity", 1.0);
  const Json &viewport = member_or_empty(view, "viewport");
  scene->viewport_width = int(std::clamp<int64_t>(io::get_int(viewport, "width", 800), 1, 16384));
  scene->viewport_height = int(std::clamp<int64_t>(io::get_int(viewport, "height", 600), 1, 16384));
  const Json &visibility = member_or_empty(view, "visibility");
  const dvec3 render_origin = dvec3::from(p.render_origin);

  for (const io::PayloadWarning &w : p.warnings) {
    scene->warnings.push_back("layer " + w.layer + " skipped: " + w.message);
  }
  Builder b{cache, p, *scene};
  const Json &layers = p.layers();
  int index = 0;
  for (const Json &layer : layers) {
    DrawLayer L;
    L.index = index++;
    L.json = &layer;
    L.id = io::get_string(layer, "id");
    L.type = io::get_string(layer, "type");
    L.name = io::get_string(layer, "name", L.id);
    if (L.name.empty()) {
      L.name = L.id;
    }
    L.kind = p.skipped(L.id) ? LayerKind::Unknown : kind_of(L.type);
    L.payload_visible = io::get_bool(layer, "visible", true);
    if (const Json *v = member(visibility, L.id); v && v->is_boolean() && !v->get<bool>()) {
      L.payload_visible = false;
      scene->hidden_by_view.push_back(L.id);
    }
    L.probe = viewer::probe_of(layer);
    const Json &app = member_or_empty(layer, "appearance");
    L.opacity = float(std::clamp(io::get_number(app, "opacity", 1.0), 0.0, 1.0));
    if (L.kind != LayerKind::Overlay && L.kind != LayerKind::Unknown) {
      L.layer_origin = dvec3::from(p.layer_origin(layer));
      L.offset = L.layer_origin - render_origin;
    }
    switch (L.kind) {
      case LayerKind::Triangles:
        b.triangles(L);
        break;
      case LayerKind::SliceImage:
        b.slice(L);
        break;
      case LayerKind::Lines:
        b.lines(L);
        break;
      case LayerKind::Points:
        b.points(L);
        break;
      case LayerKind::Instances:
        b.instances(L);
        break;
      case LayerKind::Volume:
        b.volume(L);
        break;
      case LayerKind::Overlay:
        b.overlay(L);
        break;
      case LayerKind::Unknown:
        /* Skipped (spec §10 warnings, reported above), like the web viewer and payload.py. */
        L.disabled = true;
        break;
    }
    scene->layers.push_back(std::move(L));
  }
  /* Storage buffers over the device limit cannot be drawn: such triangle levels are dropped (a
   * coarser LOD is drawn instead), other layers are disabled, with a warning. */
  const uint64_t max_ssbo = uint64_t(GPU_max_storage_buffer_size());
  auto too_large = [&](std::initializer_list<const ResourcePtr *> resources) -> uint64_t {
    for (const ResourcePtr *r : resources) {
      if (*r && (*r)->ssbo && max_ssbo > 0 && (*r)->bytes > max_ssbo) {
        return (*r)->bytes;
      }
    }
    return 0;
  };
  for (DrawLayer &L : scene->layers) {
    uint64_t bytes = 0;
    if (L.kind == LayerKind::Triangles) {
      for (MeshLevel &m : L.mesh) {
        if (const uint64_t b = too_large({&m.pos, &m.idx, &m.nrm, &m.color.values})) {
          m.usable = false;
          bytes = b;
        }
      }
      if (bytes && std::any_of(L.mesh.begin(), L.mesh.end(), [](const MeshLevel &m) { return m.usable; })) {
        scene->warnings.push_back("layer " + L.id + ": a level of " + std::to_string(bytes) +
                                  " bytes exceeds the GPU storage-buffer limit of " + std::to_string(max_ssbo) +
                                  " bytes; a coarser level is drawn");
        bytes = 0;
      }
    }
    else {
      bytes = too_large({&L.lines.pos, &L.lines.idx, &L.lines.color.values, &L.points.pos, &L.points.radii,
                         &L.points.color.values, &L.glyphs.mesh, &L.glyphs.inst, &L.glyphs.color.values,
                         &L.glyphs.lines.pos});
    }
    if (bytes) {
      scene->warnings.push_back("layer " + L.id + ": a buffer of " + std::to_string(bytes) +
                                " bytes exceeds the GPU storage-buffer limit of " + std::to_string(max_ssbo) +
                                " bytes; the layer is not drawn (use a coarser LOD or a smaller budget profile)");
      L.disabled = true;
    }
  }
  /* Clip-plane bounds: glyphs and spheres extend past their positions. */
  scene->render_bounds = scene->bounds;
  for (const DrawLayer &L : scene->layers) {
    if (L.kind == LayerKind::Instances) {
      const GlyphData &g = L.glyphs;
      for (const uint32_t i : g.kept) {
        const double r = std::abs(g.scales[i]);
        const dvec3 c = L.offset + dvec3{g.positions[i * 3], g.positions[i * 3 + 1], g.positions[i * 3 + 2]};
        scene->render_bounds.expand(c - dvec3{r, r, r});
        scene->render_bounds.expand(c + dvec3{r, r, r});
      }
    }
    else if (L.kind == LayerKind::Points && L.points.world_spheres) {
      const PointData &d = L.points;
      for (size_t i = 0; i < d.count; i++) {
        const double r = d.radii_cpu.empty() ? d.radius : std::abs(d.radii_cpu[i]);
        const dvec3 c = L.offset + dvec3{d.positions[i * 3], d.positions[i * 3 + 1], d.positions[i * 3 + 2]};
        if (std::isfinite(r) && viewer::is_finite(c)) {
          scene->render_bounds.expand(c - dvec3{r, r, r});
          scene->render_bounds.expand(c + dvec3{r, r, r});
        }
      }
    }
  }
  /* Converted index arrays referenced by mesh levels. */
  scene->owned_indices = std::move(b.owned_indices);
  return scene;
}

}  // namespace stk::viewer_gpu
