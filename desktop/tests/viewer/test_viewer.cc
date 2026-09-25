/* SPDX-License-Identifier: GPL-2.0-or-later */
/* stk_viewer_gpu tests (run once per GPU backend): render goldens, exact categorical colours,
 * tiled export, id-buffer picking with float64 refinement, timestep prefetch / camera / budget,
 * LOD selection, the VTK cross-check and a 1M-triangle performance smoke test. */

#include "support.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <random>
#include <set>

#include <gtest/gtest.h>

#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_state.hh"

#include "stk/core/mmap.hh"
#include "stk/gfx/offscreen.hh"
#include "stk/viewer/camera.hh"
#include "stk/viewer/colormap.hh"

namespace stk::viewer_gpu::test {
namespace {

using viewer::dvec3;

ExportOptions size(int w, int h, int mag = 1, int tile = 0)
{
  ExportOptions o;
  o.width = w;
  o.height = h;
  o.magnification = mag;
  o.tile_size = tile;
  return o;
}

std::filesystem::path example_dir()
{
  return repo_root() / "docs" / "specs" / "examples" / "payload-v2";
}

std::array<uint8_t, 3> rgb(const viewer::RGBA8 &c)
{
  return {c[0], c[1], c[2]};
}

std::string describe(const std::array<uint8_t, 3> &c)
{
  return "(" + std::to_string(c[0]) + "," + std::to_string(c[1]) + "," + std::to_string(c[2]) + ")";
}

/** Render one frame into the viewer's internal target (inside a GPU frame, as a window would). */
void render_frame(Viewer &v, int w, int h)
{
  blender::GPUContext *ctx = blender::GPU_context_active_get();
  blender::GPU_render_begin();
  blender::GPU_context_begin_frame(ctx);
  v.render(w, h, 1.0f);
  blender::GPU_finish();
  blender::GPU_context_end_frame(ctx);
  blender::GPU_render_end();
}

/* -------------------------------------------------------------------- */
/* Render goldens (SSIM >= 0.98 on every backend against one golden). */

TEST(Golden, ExampleDirectoryAndStkp)
{
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(example_dir()));
  EXPECT_TRUE(v.warnings().empty());
  const gfx::Image dir = render(v, "example_dir", size(800, 600));
  const double s1 = compare_golden(dir, "example.png");
  EXPECT_GE(s1, 0.98);
  v.set_payload(load_payload(example_dir() / "example.stkp"));
  const gfx::Image stkp = render(v, "example_stkp", size(800, 600));
  int max_diff = 0;
  EXPECT_EQ(differing_fraction(dir, stkp, 0, &max_diff), 0.0) << "max diff " << max_diff;
  const double s2 = compare_golden(stkp, "example.png");
  EXPECT_GE(s2, 0.98);
  std::printf("example SSIM: directory %.5f, stkp %.5f\n", s1, s2);
  RecordProperty("ssim_example", std::to_string(s1));
}

TEST(Golden, MuferroDomains)
{
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(fixtures_dir() / "muferro_domains"));
  EXPECT_TRUE(v.warnings().empty());
  const gfx::Image dir = render(v, "muferro_domains_dir", size(800, 600));
  v.set_payload(load_payload(fixtures_dir() / "muferro_domains.stkp"));
  const gfx::Image stkp = render(v, "muferro_domains_stkp", size(800, 600));
  EXPECT_EQ(differing_fraction(dir, stkp, 0), 0.0);
  const double s = compare_golden(stkp, "muferro_domains.png");
  EXPECT_GE(s, 0.98);
  std::printf("muferro-domains SSIM %.5f\n", s);
  RecordProperty("ssim_muferro_domains", std::to_string(s));
}

TEST(Golden, EveryLayerType)
{
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(fixtures_dir() / "layers.stkp"));
  for (const std::string &w : v.warnings()) {
    ADD_FAILURE() << "warning: " << w;
  }
  const std::vector<LayerInfo> layers = v.layers();
  std::set<LayerKind> kinds;
  for (const LayerInfo &l : layers) {
    kinds.insert(l.layer_kind);
    EXPECT_GT(l.elements + (l.layer_kind == LayerKind::Overlay ? 1 : 0), 0u) << l.id;
  }
  for (const LayerKind k : {LayerKind::Triangles, LayerKind::SliceImage, LayerKind::Lines, LayerKind::Points,
                            LayerKind::Instances, LayerKind::Volume, LayerKind::Overlay})
  {
    EXPECT_TRUE(kinds.count(k)) << layer_kind_name(k);
  }
  const gfx::Image img = render(v, "layers", size(800, 600));
  const double s = compare_golden(img, "layers.png");
  EXPECT_GE(s, 0.98);
  std::printf("layers SSIM %.5f\n", s);
  RecordProperty("ssim_layers", std::to_string(s));
}

/* -------------------------------------------------------------------- */
/* Exact categorical colours where no lighting is applied. */

void expect_only_colors(const gfx::Image &img, const std::set<std::array<uint8_t, 3>> &allowed,
                        const std::vector<std::array<uint8_t, 3>> &required, size_t min_pixels)
{
  const auto hist = histogram(img);
  for (const auto &c : required) {
    const auto it = hist.find(c);
    EXPECT_TRUE(it != hist.end() && it->second >= min_pixels)
        << "colour " << describe(c) << " has " << (it == hist.end() ? 0 : it->second) << " pixels";
  }
  for (const auto &[c, n] : hist) {
    EXPECT_TRUE(allowed.count(c)) << "unexpected colour " << describe(c) << " (" << n << " pixels)";
  }
}

TEST(Categorical, ExampleCubesExactUnlit)
{
  Viewer v(gpu().fonts());
  auto p = load_payload(example_dir());
  v.set_payload(p);
  v.set_lighting("none");
  v.set_overlays_visible(false);
  v.set_layer_visible("arrows", false);
  v.set_layer_visible("density", false);
  const gfx::Image img = render(v, "example_unlit", size(800, 600));
  const auto pal = viewer::resolve_colormap(*p, "pal0");
  ASSERT_TRUE(pal && pal->categorical);
  std::vector<std::array<uint8_t, 3>> required;
  for (const int64_t label : {1, 7, 19}) {
    required.push_back(rgb(pal->categorical->lookup.at(label)));
  }
  std::set<std::array<uint8_t, 3>> allowed(required.begin(), required.end());
  allowed.insert({255, 255, 255}); /* background */
  allowed.insert({0, 0, 0});       /* outline */
  expect_only_colors(img, allowed, required, 2000);
}

TEST(Categorical, MuferroDomainsExactUnlit)
{
  Viewer v(gpu().fonts());
  auto p = load_payload(fixtures_dir() / "muferro_domains.stkp");
  v.set_payload(p);
  v.set_lighting("none");
  v.set_overlays_visible(false);
  const gfx::Image img = render(v, "muferro_domains_unlit", size(800, 600));
  const auto pal = viewer::resolve_colormap(*p, "pal0");
  ASSERT_TRUE(pal && pal->categorical);
  std::vector<std::array<uint8_t, 3>> required;
  for (const int64_t label : {2, 6, 13, 19}) {
    required.push_back(rgb(pal->categorical->lookup.at(label)));
  }
  std::set<std::array<uint8_t, 3>> allowed(required.begin(), required.end());
  allowed.insert({255, 255, 255});
  allowed.insert({0, 0, 0});
  expect_only_colors(img, allowed, required, 5000);
}

TEST(Categorical, MixedPointLabelsGetOneExactColourPerTriangle)
{
  Viewer v(gpu().fonts());
  auto p = load_payload(fixtures_dir() / "layers.stkp");
  v.set_payload(p);
  v.set_lighting("none");
  v.set_overlays_visible(false);
  for (const LayerInfo &l : v.layers()) {
    v.set_layer_visible(l.id, l.id == "cats");
  }
  const gfx::Image img = render(v, "layers_cats_unlit", size(800, 600));
  const io::Json *cats = p->layer("cats");
  ASSERT_TRUE(cats);
  const std::string pal_id = (*cats)["attributes"]["label"]["palette"].get<std::string>();
  const auto pal = viewer::resolve_colormap(*p, pal_id);
  ASSERT_TRUE(pal && pal->categorical);
  std::vector<std::array<uint8_t, 3>> required;
  for (const auto &e : pal->categorical->entries) {
    required.push_back(rgb(e.color));
  }
  required.push_back(rgb(pal->categorical->unknown));
  std::set<std::array<uint8_t, 3>> allowed(required.begin(), required.end());
  allowed.insert({245, 245, 245}); /* background 0.96 */
  allowed.insert({26, 26, 26});    /* edges 0.1 */
  expect_only_colors(img, allowed, required, 200);
}

/* -------------------------------------------------------------------- */
/* Exact LUT binning (spec §5): values on and next to bin edges, below, above and NaN. */

TEST(Lut, ExactBinsUnlit)
{
  const double lo = -2.0, hi = 3.0;
  std::vector<double> values;
  for (const int k : {0, 1, 17, 64, 127, 128, 129, 200, 254, 255}) {
    const double edge = lo + (hi - lo) * k / 256.0;
    values.push_back(edge);
    values.push_back(std::nextafter(edge, -1e300));
    values.push_back(std::nextafter(edge, 1e300));
  }
  values.insert(values.end(), {hi, std::nextafter(hi, 1e300), lo - 1.0, hi + 1.0,
                               std::numeric_limits<double>::quiet_NaN(), 0.5 * (lo + hi)});
  /* One quad per value (4 points of the same value), in a row. */
  PayloadBuilder b({1.0e6, 1.0e6, 1.0e6});
  std::vector<float> pos;
  std::vector<double> val;
  std::vector<uint32_t> idx;
  const size_t n = values.size();
  for (size_t q = 0; q < n; q++) {
    const float x0 = float(q), x1 = float(q) + 0.8f;
    pos.insert(pos.end(), {x0, 0, 0, x1, 0, 0, x1, 1, 0, x0, 1, 0});
    for (int k = 0; k < 4; k++) {
      val.push_back(values[q]);
    }
    const uint32_t a = uint32_t(q * 4);
    idx.insert(idx.end(), {a, a + 1, a + 2, a, a + 2, a + 3});
  }
  b.accessor("pos", pos, "f32", 3);
  b.accessor("idx", idx, "u32", 1);
  b.accessor("val", val, "f64", 1);
  /* A LUT whose 256 entries are all different, plus distinct below / above / NaN colours. */
  std::vector<uint8_t> lut;
  for (int i = 0; i < 256; i++) {
    lut.insert(lut.end(), {uint8_t(i), uint8_t(255 - i), uint8_t((i * 7) % 256), 255});
  }
  b.accessor("lut", lut, "u8", 4);
  b.manifest()["colormaps"] = {{{"id", "cm"}, {"name", "ramp"}, {"categorical", false}, {"lut", "lut"},
                                {"size", 256}, {"below_color", {0.0, 0.0, 1.0}}, {"above_color", {1.0, 0.0, 0.0}},
                                {"nan_color", {0.0, 1.0, 0.0}}}};
  b.layer({{"id", "q"},
           {"type", "triangles"},
           {"positions", "pos"},
           {"indices", "idx"},
           {"attributes", {{"v", {{"accessor", "val"}, {"association", "point"}, {"range", {lo, hi}}}}}},
           {"appearance", {{"color", {{"by", "attribute"}, {"attribute", "v"}, {"colormap", "cm"}}}}}});
  b.manifest()["view"] = {{"schema", "stk.view/1"},
                          {"camera", {{"preset", "+z"}, {"projection", "parallel"}}},
                          {"lighting", {{"preset", "none"}}}};
  auto payload = b.build();
  Viewer v(gpu().fonts());
  v.set_payload(payload);
  const int W = 2400, H = 600;
  const gfx::Image img = render(v, "lut_bins", size(W, H));
  const auto cm = viewer::resolve_colormap(*payload, "cm");
  ASSERT_TRUE(cm && cm->continuous);
  const viewer::Viewport vp{double(W), double(H)};
  int checked = 0;
  for (size_t q = 0; q < n; q++) {
    /* Several pixels of the quad, including near its triangles' shared edge. */
    for (const auto &[fx, fy] : std::vector<std::pair<double, double>>{{0.4, 0.5}, {0.1, 0.12}, {0.7, 0.9}, {0.41, 0.52}}) {
      const auto s = viewer::project(v.camera(), vp, dvec3{double(q) + 0.8 * fx, fy, 0.0});
      ASSERT_TRUE(s.has_value());
      const uint8_t *p = img.px(int(s->x), int(s->y));
      const viewer::RGBA8 want = cm->continuous->map(values[q], lo, hi);
      EXPECT_EQ(rgb(want), (std::array<uint8_t, 3>{p[0], p[1], p[2]}))
          << "value " << values[q] << " (quad " << q << ") bin " << viewer::lut_index(values[q], lo, hi);
      checked++;
    }
  }
  EXPECT_EQ(checked, int(n) * 4);
}

/* -------------------------------------------------------------------- */
/* Tiled export equals a single pass. */

void tiled_equals_single(const std::filesystem::path &payload, const std::string &name)
{
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(payload));
  const gfx::Image single = render(v, name + "_x4_single", size(200, 150, 4, 4096));
  const gfx::Image tiled = render(v, name + "_x4_tiled", size(200, 150, 4, 200));
  ASSERT_EQ(single.width, 800);
  ASSERT_EQ(tiled.height, 600);
  int max_diff = 0;
  const double frac = differing_fraction(single, tiled, 2, &max_diff);
  const double s = ssim(single, tiled);
  std::printf("%s: tiled x4 vs single pass: SSIM %.6f, %.4f%% pixels differ by > 2 (max %d)\n", name.c_str(), s,
              frac * 100, max_diff);
  EXPECT_GE(s, 0.995);
  EXPECT_LE(frac, 0.002);
}

TEST(Tiling, Tiled4xEqualsSinglePassExample)
{
  tiled_equals_single(example_dir() / "example.stkp", "example");
}

TEST(Tiling, Tiled4xEqualsSinglePassLayers)
{
  tiled_equals_single(fixtures_dir() / "layers.stkp", "layers");
}

TEST(Tiling, MagnificationScalesPixelSizes)
{
  /* A x2 export is the x1 picture at twice the resolution (overlays and line widths scale). */
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(example_dir()));
  const gfx::Image x1 = render(v, "example_x1", size(400, 300, 1));
  const gfx::Image x2 = render(v, "example_x2", size(400, 300, 2));
  ASSERT_EQ(x2.width, 800);
  gfx::Image down;
  down.width = 400;
  down.height = 300;
  down.rgba.resize(size_t(400) * 300 * 4);
  for (int y = 0; y < 300; y++) {
    for (int x = 0; x < 400; x++) {
      for (int k = 0; k < 4; k++) {
        int sum = 0;
        for (int dy = 0; dy < 2; dy++) {
          for (int dx = 0; dx < 2; dx++) {
            sum += x2.px(2 * x + dx, 2 * y + dy)[k];
          }
        }
        down.px(x, y)[k] = uint8_t((sum + 2) / 4);
      }
    }
  }
  const double s = ssim(x1, down);
  std::printf("x2 downsampled vs x1: SSIM %.4f\n", s);
  EXPECT_GE(s, 0.85);
}

/* -------------------------------------------------------------------- */
/* Picking: GPU id buffer + float64 refinement. */

struct Hit {
  int64_t tri = -1;
  long double t = 0;
  std::array<long double, 3> local{};
  long double bmin = 0;
};

/** Independent brute-force ray casting in long double (Moller-Trumbore). */
Hit brute_force(const viewer::Ray &ray, const std::vector<float> &pos, const std::vector<uint32_t> &idx,
                const dvec3 &shift)
{
  Hit best;
  for (size_t t = 0; t < idx.size() / 3; t++) {
    std::array<long double, 3> v[3];
    for (int k = 0; k < 3; k++) {
      for (int c = 0; c < 3; c++) {
        v[k][size_t(c)] = (long double)pos[size_t(idx[t * 3 + size_t(k)]) * 3 + size_t(c)] + (long double)shift[size_t(c)];
      }
    }
    const long double o[3] = {ray.origin.x, ray.origin.y, ray.origin.z};
    const long double d[3] = {ray.direction.x, ray.direction.y, ray.direction.z};
    long double e1[3], e2[3], pv[3], tv[3], qv[3];
    for (int c = 0; c < 3; c++) {
      e1[c] = v[1][size_t(c)] - v[0][size_t(c)];
      e2[c] = v[2][size_t(c)] - v[0][size_t(c)];
      tv[c] = o[c] - v[0][size_t(c)];
    }
    pv[0] = d[1] * e2[2] - d[2] * e2[1];
    pv[1] = d[2] * e2[0] - d[0] * e2[2];
    pv[2] = d[0] * e2[1] - d[1] * e2[0];
    const long double det = e1[0] * pv[0] + e1[1] * pv[1] + e1[2] * pv[2];
    if (std::fabs(det) < 1e-30L) {
      continue;
    }
    const long double inv = 1.0L / det;
    const long double u = (tv[0] * pv[0] + tv[1] * pv[1] + tv[2] * pv[2]) * inv;
    qv[0] = tv[1] * e1[2] - tv[2] * e1[1];
    qv[1] = tv[2] * e1[0] - tv[0] * e1[2];
    qv[2] = tv[0] * e1[1] - tv[1] * e1[0];
    const long double w = (d[0] * qv[0] + d[1] * qv[1] + d[2] * qv[2]) * inv;
    const long double tt = (e2[0] * qv[0] + e2[1] * qv[1] + e2[2] * qv[2]) * inv;
    if (u < 0 || w < 0 || u + w > 1 || tt < 0) {
      continue;
    }
    if (best.tri < 0 || tt < best.t) {
      best.tri = int64_t(t);
      best.t = tt;
      for (int c = 0; c < 3; c++) {
        best.local[size_t(c)] = v[0][size_t(c)] + e1[c] * u + e2[c] * w;
      }
      best.bmin = std::min({u, w, 1 - u - w});
    }
  }
  return best;
}

TEST(Picking, IdBufferAndFloat64RefinementFarFromOrigin)
{
  const std::array<double, 3> origin{1.0e6 + 0.3, 1.0e6 - 0.7, 1.0e6 + 0.11};
  PayloadBuilder b(origin);
  constexpr int N = 40;
  std::vector<float> pos;
  std::vector<uint32_t> idx;
  for (int j = 0; j <= N; j++) {
    for (int i = 0; i <= N; i++) {
      const double x = -1.0 + 2.0 * i / N, y = -1.0 + 2.0 * j / N;
      pos.insert(pos.end(), {float(x), float(y), float(0.2 * x + 0.1 * y + 0.05 * std::sin(7 * x))});
    }
  }
  for (int j = 0; j < N; j++) {
    for (int i = 0; i < N; i++) {
      const uint32_t a = uint32_t(j * (N + 1) + i), c = a + N + 2;
      idx.insert(idx.end(), {a, a + 1, c, a, c, a + N + 1});
    }
  }
  b.accessor("pos", pos, "f32", 3);
  b.accessor("idx", idx, "u32", 1);
  b.layer({{"id", "mesh"}, {"type", "triangles"}, {"positions", "pos"}, {"indices", "idx"},
           {"pick", {{"probe", {{"node", "src"}, {"dataset", "field"}}}}}});
  auto payload = b.build();
  Viewer v(gpu().fonts());
  v.set_payload(payload);
  const int W = 640, H = 480;
  const viewer::Viewport vp{double(W), double(H)};
  const dvec3 zero{0, 0, 0};
  int tested = 0, gpu_agrees = 0;
  double worst_rel = 0, worst_abs = 0;
  std::mt19937 rng(11);
  std::uniform_real_distribution<double> uv(-0.95, 0.95);
  for (int k = 0; k < 80; k++) {
    /* Pixel centres over the mesh (and a few beside it). */
    const double mx = uv(rng) * (k % 8 == 7 ? 1.3 : 1.0), my = uv(rng);
    const dvec3 local{mx, my, 0.2 * mx + 0.1 * my + 0.05 * std::sin(7 * mx)};
    const auto s = viewer::project(v.camera(), vp, local);
    ASSERT_TRUE(s.has_value());
    const double x = std::floor(s->x) + 0.5, y = std::floor(s->y) + 0.5;
    if (x < 0 || y < 0 || x >= W || y >= H) {
      continue;
    }
    const viewer::Ray ray = viewer::pixel_ray(v.camera(), vp, x, y);
    const Hit expected = brute_force(ray, pos, idx, zero);
    const PickResult r = v.pick(x, y, W, H);
    if (expected.tri < 0) {
      EXPECT_FALSE(r.hit) << "pixel " << x << "," << y;
      continue;
    }
    ASSERT_TRUE(r.hit) << "pixel " << x << "," << y;
    EXPECT_EQ(r.layer_id, "mesh");
    ASSERT_TRUE(r.probe.has_value());
    EXPECT_EQ(r.probe->node, "src");
    if (expected.bmin > 1e-6L) {
      EXPECT_EQ(int64_t(r.element), expected.tri) << "pixel " << x << "," << y;
      gpu_agrees += int64_t(r.gpu_candidate) == expected.tri ? 1 : 0;
    }
    double err2 = 0, mag2 = 0;
    for (int c = 0; c < 3; c++) {
      const long double want = (long double)origin[size_t(c)] + expected.local[size_t(c)];
      const long double diff = (long double)r.physical[size_t(c)] - want;
      err2 += double(diff * diff);
      mag2 += double(want * want);
    }
    worst_abs = std::max(worst_abs, std::sqrt(err2));
    worst_rel = std::max(worst_rel, std::sqrt(err2 / mag2));
    tested++;
  }
  std::printf("picking: %d hits, GPU candidate exact in %d, worst position error %.3e (relative %.3e)\n", tested,
              gpu_agrees, worst_abs, worst_rel);
  EXPECT_GE(tested, 60);
  EXPECT_GE(gpu_agrees, tested * 9 / 10);
  EXPECT_LE(worst_rel, 1e-9);
  RecordProperty("pick_worst_relative_error", std::to_string(worst_rel));
}

TEST(Picking, EveryPickableLayerType)
{
  auto p = load_payload(fixtures_dir() / "layers.stkp");
  Viewer v(gpu().fonts());
  v.set_payload(p);
  const int W = 800, H = 600;
  const viewer::Viewport vp{double(W), double(H)};
  auto screen = [&](const dvec3 &local) {
    const auto s = viewer::project(v.camera(), vp, local);
    EXPECT_TRUE(s.has_value());
    return s ? *s : dvec3{};
  };
  auto point_of = [&](const std::string &accessor, size_t i) {
    const std::vector<float> f = p->floats(accessor);
    return dvec3{f[i * 3], f[i * 3 + 1], f[i * 3 + 2]};
  };
  struct Case {
    std::string layer;
    dvec3 local;
    int64_t element; /* -1: any */
  };
  std::vector<Case> cases;
  cases.push_back({"balls", point_of("ball_pos", 3), 3});
  cases.push_back({"glyph_cube", point_of("g2_pos", 2), 2});
  cases.push_back({"glyph_sphere", point_of("g1_pos", 4), 4});
  cases.push_back({"slice", dvec3{-7.0 + 5.0 * 10 / 15, 1.0 + 3.75 * 6 / 11, -1.0}, 10 + 6 * 16});
  cases.push_back({"surf", point_of("surf_pos", 24 * 12 + 12), -1});
  cases.push_back({"pts", point_of("pts_pos", 7), -1});
  {
    const dvec3 a = point_of("poly_pos", 10), c = point_of("poly_pos", 11);
    cases.push_back({"poly", (a + c) * 0.5, 10});
  }
  for (const Case &c : cases) {
    const dvec3 s = screen(c.local);
    const PickResult r = v.pick(s.x, s.y, W, H);
    ASSERT_TRUE(r.hit) << c.layer;
    EXPECT_EQ(r.layer_id, c.layer) << "at " << s.x << "," << s.y;
    if (c.element >= 0 && r.layer_id == c.layer) {
      EXPECT_EQ(int64_t(r.element), c.element) << c.layer;
    }
    std::printf("pick %-12s -> %-12s element %u at (%.3f, %.3f, %.3f)\n", c.layer.c_str(), r.layer_id.c_str(),
                r.element, r.physical[0], r.physical[1], r.physical[2]);
  }
  /* Background. */
  const PickResult none = v.pick(2.5, 300.5, W, H);
  EXPECT_FALSE(none.hit);
}

/* -------------------------------------------------------------------- */
/* Timesteps: content-addressed prefetch, camera kept across steps, budget. */

std::shared_ptr<const io::Payload> variant(const io::Payload &p, const std::function<void(io::Json &)> &edit)
{
  io::Json m = p.manifest;
  edit(m);
  std::map<std::string, core::SharedBytes> blobs;
  for (const io::PayloadBuffer &b : p.buffers) {
    blobs[b.sha256] = b.bytes;
  }
  return std::make_shared<const io::Payload>(io::decode(m, std::move(blobs)));
}

TEST(Steps, PrefetchSharesBuffersAndKeepsTheCamera)
{
  auto step1 = load_payload(example_dir());
  auto step2 = variant(*step1, [](io::Json &m) { m["source"]["time"]["step"] = 2000; });
  auto other_view = variant(*step1, [](io::Json &m) {
    m["view"]["camera"] = {{"preset", "+x"}, {"projection", "perspective"}, {"view_angle_deg", 30.0}};
  });
  Viewer v(gpu().fonts());
  v.set_payload(step1);
  const GpuStats s1 = v.stats();
  v.prefetch(step2);
  const GpuStats s2 = v.stats();
  EXPECT_EQ(s2.cached_scenes, 2u);
  EXPECT_EQ(s2.uploads, s1.uploads) << "every buffer of the next step is shared (content-addressed)";
  EXPECT_EQ(s2.resident_bytes, s1.resident_bytes);
  /* The user's camera survives a step change with the same requested view. */
  viewer::CameraPose pose = v.camera();
  viewer::orbit(pose, viewer::NavigationStyle::Blender, 40, 10, {800, 600});
  v.set_camera(pose);
  v.set_payload(step2);
  EXPECT_EQ(v.camera().position, pose.position);
  EXPECT_EQ(v.stats().uploads, s1.uploads);
  /* A different requested view resets it. */
  v.set_payload(other_view);
  EXPECT_NE(v.camera().position, pose.position);
  const dvec3 dir = v.camera().direction();
  EXPECT_NEAR(dir.x, -1.0, 1e-9);
  /* Rendering a prefetched step needs no uploads. */
  const gfx::Image img = render(v, "example_plus_x", size(320, 240));
  EXPECT_FALSE(img.empty());
}

TEST(Steps, BudgetEvictsOtherSteps)
{
  ViewerOptions o;
  o.gpu_budget_bytes = 1; /* everything but the current step is evicted */
  Viewer v(gpu().fonts(), o);
  v.set_payload(load_payload(example_dir()));
  const uint64_t example_bytes = v.stats().resident_bytes;
  v.prefetch(load_payload(fixtures_dir() / "muferro_domains.stkp"));
  EXPECT_EQ(v.stats().cached_scenes, 1u);
  EXPECT_EQ(v.stats().resident_bytes, example_bytes);
  v.set_payload(load_payload(fixtures_dir() / "muferro_domains.stkp"));
  EXPECT_EQ(v.stats().cached_scenes, 1u);
  EXPECT_GT(v.stats().evictions, 0u);
  const gfx::Image img = render(v, "budget_muferro", size(320, 240));
  EXPECT_FALSE(img.empty());
}

/* -------------------------------------------------------------------- */
/* LOD selection (LodPolicy): coarse levels and shuffled prefixes while interacting. */

TEST(Lod, InteractiveBudgetSelectsCoarseLevelsAndPrefixes)
{
  PayloadBuilder b({0, 0, 0});
  auto grid = [&](const std::string &prefix, int n) {
    std::vector<float> pos;
    std::vector<uint32_t> idx;
    for (int j = 0; j <= n; j++) {
      for (int i = 0; i <= n; i++) {
        pos.insert(pos.end(), {float(i) / n, float(j) / n, 0.0f});
      }
    }
    for (int j = 0; j < n; j++) {
      for (int i = 0; i < n; i++) {
        const uint32_t a = uint32_t(j * (n + 1) + i), c = a + uint32_t(n) + 2;
        idx.insert(idx.end(), {a, a + 1, c, a, c, a + uint32_t(n) + 1});
      }
    }
    b.accessor(prefix + "_pos", pos, "f32", 3);
    b.accessor(prefix + "_idx", idx, "u32", 1);
    return uint64_t(n) * n * 2;
  };
  const uint64_t coarse = grid("lod1", 2), fine = grid("main", 60);
  b.layer({{"id", "mesh"}, {"type", "triangles"}, {"positions", "main_pos"}, {"indices", "main_idx"},
           {"lods", {{{"level", 1}, {"positions", "lod1_pos"}, {"indices", "lod1_idx"}}}}});
  std::vector<float> pts;
  for (int i = 0; i < 1000; i++) {
    pts.insert(pts.end(), {float(i % 10) / 10, float(i / 10 % 10) / 10, float(i / 100) / 10});
  }
  b.accessor("pts", pts, "f32", 3);
  b.layer({{"id", "cloud"}, {"type", "points"}, {"positions", "pts"}, {"progressive", {{"shuffled", true}, {"seed", 1}}}});
  ViewerOptions o;
  o.lod.interactive_triangles = 100;
  o.lod.interactive_points = 250;
  Viewer v(gpu().fonts(), o);
  v.set_payload(b.build());
  render_frame(v, 320, 240);
  EXPECT_EQ(v.stats().drawn_triangles, fine);
  EXPECT_EQ(v.stats().drawn_points, 1000u);
  v.set_interacting(true);
  render_frame(v, 320, 240);
  EXPECT_EQ(v.stats().drawn_triangles, coarse);
  EXPECT_LE(v.stats().drawn_points, 250u);
  EXPECT_GT(v.stats().drawn_points, 0u);
  v.set_interacting(false);
  render_frame(v, 320, 240);
  EXPECT_EQ(v.stats().drawn_triangles, fine);
}

/* -------------------------------------------------------------------- */
/* Cross-check against the offscreen VTK reference. */

TEST(CrossCheck, MuferroDomainsAgainstVtk)
{
  gfx::Image ref;
  std::string err;
  const auto ref_path = fixtures_dir() / "vtk" / "muferro_domains_nooverlays.png";
  if (!std::filesystem::exists(ref_path)) {
    GTEST_SKIP() << "no VTK reference (make_fixtures.py --vtk needs an offscreen VTK interpreter)";
  }
  ASSERT_TRUE(gfx::png_read(ref_path.string(), ref, err)) << err;
  auto p = load_payload(fixtures_dir() / "muferro_domains.stkp");
  Viewer v(gpu().fonts());
  v.set_payload(p);
  v.set_overlays_visible(false);
  const gfx::Image img = render(v, "muferro_domains_nooverlays", size(ref.width, ref.height));
  const double mask_iou = iou(chroma_mask(img), chroma_mask(ref));
  std::printf("VTK cross-check: domain mask IoU %.4f, SSIM %.4f\n", mask_iou, ssim(img, ref));
  EXPECT_GE(mask_iou, 0.9);
  RecordProperty("vtk_mask_iou", std::to_string(mask_iou));
  const auto pal = viewer::resolve_colormap(*p, "pal0");
  ASSERT_TRUE(pal && pal->categorical);
  for (const int64_t label : {2, 6, 13, 19}) {
    const auto c = rgb(pal->categorical->lookup.at(label));
    const size_t ours = count_hue(img, c), theirs = count_hue(ref, c);
    std::printf("  label %lld %s: %zu pixels here, %zu in VTK\n", (long long)label, describe(c).c_str(), ours, theirs);
    EXPECT_GT(ours, 1000u);
    EXPECT_GT(theirs, 1000u);
  }
  /* With overlays: the full reference, for the record. */
  gfx::Image full;
  if (gfx::png_read((fixtures_dir() / "vtk" / "muferro_domains.png").string(), full, err)) {
    v.set_overlays_visible(true);
    const gfx::Image mine = render(v, "muferro_domains_full", size(full.width, full.height));
    std::printf("  with overlays: mask IoU %.4f, SSIM %.4f\n", iou(chroma_mask(mine), chroma_mask(full)),
                ssim(mine, full));
  }
}

/* -------------------------------------------------------------------- */
/* Viewport API: draw() into a region of the bound framebuffer (as a window region would). */

TEST(Viewport, DrawIntoRegionMatchesExport)
{
  Viewer v(gpu().fonts());
  v.set_payload(load_payload(example_dir()));
  const gfx::Image exported = render(v, "viewport_export", size(240, 180));
  std::string err;
  blender::GPUContext *ctx = blender::GPU_context_active_get();
  blender::GPU_render_begin();
  blender::GPU_context_begin_frame(ctx);
  gfx::Image window;
  {
    std::unique_ptr<gfx::Offscreen> ofs = gfx::Offscreen::create(400, 300, err);
    ASSERT_TRUE(ofs) << err;
    ofs->bind();
    blender::GPU_clear_color(0.2f, 0.3f, 0.4f, 1.0f);
    v.draw(RegionRect{100, 40, 240, 180}, 1.0f);
    EXPECT_NE(v.texture(), nullptr);
    window = ofs->read();
    ofs->unbind();
  }
  blender::GPU_context_end_frame(ctx);
  blender::GPU_render_end();
  gfx::png_write((out_dir() / ("viewport_window_" + backend_id() + ".png")).string(), window);
  /* The region (bottom-left origin) of the window equals the exported image. */
  gfx::Image region;
  region.width = 240;
  region.height = 180;
  region.rgba.resize(size_t(240) * 180 * 4);
  for (int y = 0; y < 180; y++) {
    for (int x = 0; x < 240; x++) {
      std::memcpy(region.px(x, y), window.px(100 + x, 300 - 40 - 180 + y), 4);
    }
  }
  const double s = ssim(region, exported);
  int max_diff = 0;
  const double frac = differing_fraction(region, exported, 2, &max_diff);
  std::printf("draw(region) vs export: SSIM %.5f, %.3f%% pixels differ (max %d)\n", s, frac * 100, max_diff);
  EXPECT_GE(s, 0.99);
  /* Outside the region the window keeps its clear colour. */
  EXPECT_EQ(window.px(10, 10)[0], 51);
  EXPECT_EQ(window.px(10, 10)[2], 102);
  /* Picking uses the last drawn size. */
  const PickResult r = v.pick(120.5, 90.5);
  EXPECT_TRUE(r.hit);
}

/* -------------------------------------------------------------------- */
/* Performance smoke: 1M lit, LUT-coloured triangles. */

TEST(Perf, MillionTriangles)
{
  constexpr int n = 709; /* 709 x 709 vertices: 2 x 708^2 = 1,002,528 triangles */
  PayloadBuilder b({0, 0, 0});
  std::vector<float> pos, val;
  std::vector<uint32_t> idx;
  pos.reserve(size_t(n) * n * 3);
  for (int j = 0; j < n; j++) {
    for (int i = 0; i < n; i++) {
      const float x = float(i) / (n - 1) * 2 - 1, y = float(j) / (n - 1) * 2 - 1;
      const float z = 0.15f * std::sin(6 * x) * std::cos(5 * y);
      pos.insert(pos.end(), {x, y, z});
      val.push_back(z);
    }
  }
  idx.reserve(size_t(n - 1) * (n - 1) * 6);
  for (int j = 0; j < n - 1; j++) {
    for (int i = 0; i < n - 1; i++) {
      const uint32_t a = uint32_t(j * n + i), c = a + uint32_t(n) + 1;
      idx.insert(idx.end(), {a, a + 1, c, a, c, a + uint32_t(n)});
    }
  }
  b.accessor("pos", pos, "f32", 3);
  b.accessor("idx", idx, "u32", 1);
  b.accessor("val", val, "f32", 1);
  b.layer({{"id", "big"},
           {"type", "triangles"},
           {"positions", "pos"},
           {"indices", "idx"},
           {"attributes", {{"z", {{"accessor", "val"}, {"association", "point"}}}}},
           {"appearance", {{"color", {{"by", "attribute"}, {"attribute", "z"}}}}}});
  const auto t0 = std::chrono::steady_clock::now();
  Viewer v(gpu().fonts());
  v.set_payload(b.build());
  const double build_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
  constexpr int W = 1280, H = 720;
  const auto t1 = std::chrono::steady_clock::now();
  render_frame(v, W, H);
  const double first_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t1).count();
  std::vector<double> frames;
  for (int f = 0; f < 5; f++) {
    const auto t = std::chrono::steady_clock::now();
    render_frame(v, W, H);
    frames.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count());
  }
  std::sort(frames.begin(), frames.end());
  const double median = frames[frames.size() / 2];
  EXPECT_EQ(v.stats().drawn_triangles, uint64_t(2) * (n - 1) * (n - 1));
  std::printf("perf %s: %llu triangles at %dx%d: upload/build %.0f ms, first frame %.0f ms, median frame %.1f ms "
              "(best %.1f), GPU resident %.1f MiB\n",
              backend_id().c_str(), (unsigned long long)v.stats().drawn_triangles, W, H, build_ms, first_ms, median,
              frames.front(), v.stats().resident_bytes / 1048576.0);
  RecordProperty("million_triangles_median_ms", std::to_string(median));
  /* Budget on Mesa lavapipe / llvmpipe (software rasterizers; about 0.3 s on the 48-thread
   * development host): 3 s per frame, STK_VIEWER_PERF_BUDGET_MS overrides it. */
  double budget = 3000.0;
  if (const char *env = std::getenv("STK_VIEWER_PERF_BUDGET_MS")) {
    budget = std::atof(env);
  }
  EXPECT_LT(median, budget);
}

}  // namespace
}  // namespace stk::viewer_gpu::test
