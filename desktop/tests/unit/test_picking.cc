/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Pick refinement in float64. Acceptance (WP5): pick error <= 1e-12 relative at render_origin = 1e6. */
#include "support.hh"

#include "stk/io/payload.hh"
#include "stk/viewer/picking.hh"

#include <gtest/gtest.h>

#include <limits>
#include <random>

using namespace stk;
using namespace stk::viewer;

namespace {

using LD = long double;
struct LV {
  LD x, y, z;
};
LV ld(const dvec3 &v)
{
  return {v.x, v.y, v.z};
}
LV sub(LV a, LV b)
{
  return {a.x - b.x, a.y - b.y, a.z - b.z};
}
LV add(LV a, LV b)
{
  return {a.x + b.x, a.y + b.y, a.z + b.z};
}
LV mul(LV a, LD s)
{
  return {a.x * s, a.y * s, a.z * s};
}
LD ddot(LV a, LV b)
{
  return a.x * b.x + a.y * b.y + a.z * b.z;
}
LV dcross(LV a, LV b)
{
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}

/* Exact (long double) intersection of a double ray with the plane of a float triangle, in physical units. */
LV reference_hit(const Ray &ray, const dvec3 &layer_offset, const dvec3 &a, const dvec3 &b, const dvec3 &c)
{
  const LV A = add(ld(layer_offset), ld(a)), B = add(ld(layer_offset), ld(b)), C = add(ld(layer_offset), ld(c));
  const LV n = dcross(sub(B, A), sub(C, A));
  const LV o = ld(ray.origin), d = ld(ray.direction);
  const LD t = ddot(sub(A, o), n) / ddot(d, n);
  return add(o, mul(d, t));
}

}  // namespace

TEST(Picking, TrianglePickIsExactAtRenderOrigin1e6)
{
  std::mt19937_64 rng(42);
  std::uniform_real_distribution<double> u(-2.0, 2.0);
  double worst = 0;
  for (const dvec3 render_origin : {dvec3{1e6, 1e6, 1e6}, dvec3{-1e6, 2.5e5, 1e6}}) {
    for (const dvec3 own_origin : {dvec3{0, 0, 0}, dvec3{1234.5, -0.125, 3e4}}) {
      const dvec3 layer_origin = render_origin + own_origin;
      for (int trial = 0; trial < 500; trial++) {
        std::vector<float> positions;
        for (int k = 0; k < 9; k++) {
          positions.push_back(float(u(rng)));
        }
        const std::vector<uint32_t> indices{0, 1, 2};
        const dvec3 a{positions[0], positions[1], positions[2]}, b{positions[3], positions[4], positions[5]},
            c{positions[6], positions[7], positions[8]};
        /* A target inside the triangle and a camera a few units away (relative coordinates). */
        std::uniform_real_distribution<double> w(0.05, 0.9);
        double wb = w(rng), wc = w(rng) * (1 - wb);
        const dvec3 target = own_origin + a + (b - a) * wb + (c - a) * wc;
        const dvec3 eye = target + dvec3{u(rng), u(rng), u(rng)} * 4.0 + dvec3{0, 0, 9};
        const Ray ray{eye, normalize(target - eye)};
        LayerGeometry g{positions, std::span<const uint32_t>(indices), render_origin, layer_origin};
        const auto hit = pick_triangles(ray, g);
        ASSERT_TRUE(hit.has_value());
        const LV expected_rel = reference_hit(ray, own_origin, a, b, c);
        const LV expected = add(ld(render_origin), expected_rel);
        const LD err = std::sqrt(double(ddot(sub(LV{hit->physical[0], hit->physical[1], hit->physical[2]}, expected),
                                             sub(LV{hit->physical[0], hit->physical[1], hit->physical[2]}, expected))));
        const LD rel = err / std::sqrt(double(ddot(expected, expected)));
        worst = std::max(worst, double(rel));
        ASSERT_LE(double(rel), 1e-12) << "trial " << trial;
        /* The barycentric weights reproduce the hit. */
        EXPECT_NEAR(hit->barycentric[0] + hit->barycentric[1] + hit->barycentric[2], 1.0, 1e-12);
      }
    }
  }
  std::printf("[picking] worst relative pick error at render_origin 1e6: %.3g (limit 1e-12)\n", worst);
}

TEST(Picking, IdBufferCandidateIsRefinedOrRescanned)
{
  /* Two stacked quads; the ray hits triangle 1 (front) and 3 (back). */
  const std::vector<float> positions{0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0};
  const std::vector<uint16_t> indices{0, 1, 2, 1, 3, 2, 4, 5, 6, 5, 7, 6};
  const dvec3 origin{1e6, 0, 0};
  LayerGeometry g{positions, std::span<const uint16_t>(indices), origin, origin};
  const Ray ray{{0.7, 0.6, 10}, {0, 0, -1}};
  const auto front = pick_triangles(ray, g);
  ASSERT_TRUE(front.has_value());
  EXPECT_EQ(front->element, 1u);
  EXPECT_DOUBLE_EQ(front->physical[0], 1e6 + 0.7);
  EXPECT_DOUBLE_EQ(front->physical[2], 1.0);
  EXPECT_EQ(pick_triangles(ray, g, 3u)->element, 3u); /* the id buffer names the triangle: exact refinement */
  EXPECT_EQ(pick_triangles(ray, g, 0u)->element, 1u); /* a wrong candidate falls back to the nearest hit */
  EXPECT_EQ(pick_triangles(ray, g, 3u, PickMode::CandidateOnly)->element, 3u);
  for (const auto candidate : {std::optional<uint32_t>(0), std::optional<uint32_t>(99), std::optional<uint32_t>()}) {
    EXPECT_FALSE(pick_triangles(ray, g, candidate, PickMode::CandidateOnly));
    EXPECT_EQ(pick_triangles(ray, g, candidate)->element, 1u);
  }
  EXPECT_FALSE(pick_triangles({{5, 5, 10}, {0, 0, -1}}, g).has_value());
  EXPECT_FALSE(intersect_triangle({{0.2, 0.2, 1}, {1, 0, 0}}, {0, 0, 0}, {1, 0, 0}, {0, 1, 0}).has_value());
}

TEST(Picking, PointsSpheresGlyphsAndSlices)
{
  const dvec3 origin{1e6, 1e6, 0};
  const std::vector<float> points{0, 0, 0, 1, 0, 0, 0, 0, -3};
  LayerGeometry g{points, std::span<const uint32_t>(), origin, origin};
  CameraPose pose;
  pose.position = {0, 0, 10};
  pose.focal_point = {0, 0, 0};
  pose.view_up = {0, 1, 0};
  const Viewport vp{400, 400};
  const auto s = project(pose, vp, {1, 0, 0});
  ASSERT_TRUE(s.has_value());
  const auto hit = pick_points(pose, vp, s->x + 2, s->y, g, 8);
  ASSERT_TRUE(hit.has_value());
  EXPECT_EQ(hit->element, 1u);
  EXPECT_EQ(hit->physical[0], 1e6 + 1);
  const auto centre = pick_points(pose, vp, 200, 200, g, 8); /* points 0 and 2 overlap: the nearer one */
  ASSERT_TRUE(centre.has_value());
  EXPECT_EQ(centre->element, 0u);
  EXPECT_FALSE(pick_points(pose, vp, 10, 10, g, 8).has_value());

  const auto sphere = pick_spheres({{1, 0, 10}, {0, 0, -1}}, g, 0.5);
  ASSERT_TRUE(sphere.has_value());
  EXPECT_EQ(sphere->element, 1u);
  EXPECT_NEAR(sphere->local.z, 0.5, 1e-12);

  /* One arrow along +z of length 2 at (0, 0, 0): a ray along -x at height 1.6 hits its cone. */
  const std::vector<float> one{0, 0, 0};
  const std::vector<float> dirs{0, 0, 2};
  const std::vector<double> scales = instance_scales(dirs, {}, GlyphScale{ScaleMode::Magnitude, 1.0, ""});
  ASSERT_DOUBLE_EQ(scales[0], 2.0);
  LayerGeometry glyphs{one, std::span<const uint32_t>(), origin, origin};
  const GlyphMesh arrow = glyph_mesh(GlyphShape::Arrow, 16);
  const auto gh = pick_glyphs({{5, 0, 1.6}, {-1, 0, 0}}, glyphs, dirs, scales, arrow);
  ASSERT_TRUE(gh.has_value());
  EXPECT_EQ(gh->element, 0u);
  EXPECT_NEAR(gh->local.z, 1.6, 1e-12);
  EXPECT_GT(gh->local.x, 0.0);
  EXPECT_LT(gh->local.x, 0.2 * 0.2 / 0.35 * 2 + 1e-9);
  EXPECT_FALSE(pick_glyphs({{5, 0, 2.5}, {-1, 0, 0}}, glyphs, dirs, scales, arrow).has_value());

  const auto slice = pick_slice_image({{12.2, 1.9, 5}, {0, 0, -1}}, {0, 0, 0}, {4, 0, 0}, {0, 3, 0}, 5, 4, origin,
                                      origin + dvec3{10, 0, 0});
  ASSERT_TRUE(slice.has_value());
  EXPECT_EQ(slice->element, 2u + 2u * 5u);
  EXPECT_DOUBLE_EQ(slice->physical[0], 1e6 + 10 + 2.2);
}

TEST(Picking, CandidateOnlyPointsSpheresAndGlyphsNeverFallBack)
{
  const std::vector<float> points{3, 0, 0, 0, 0, 0, 0, 0, -3};
  const std::vector<float> radii{0.25f, 0.5f, 1.0f};
  const std::vector<float> directions{1, 0, 0, 1, 0, 0, 1, 0, 0};
  const std::vector<double> scales{1, 1, 1};
  const GlyphMesh mesh = glyph_mesh(GlyphShape::Cube);
  const LayerGeometry g{points, std::span<const uint32_t>(), {}, {}};
  CameraPose pose;
  pose.position = {0, 0, 10};
  const Viewport vp{400, 400};
  const Ray ray = pixel_ray(pose, vp, 200, 200);
  for (const auto candidate : {std::optional<uint32_t>(0), std::optional<uint32_t>(99), std::optional<uint32_t>()}) {
    EXPECT_FALSE(pick_points(pose, vp, 200, 200, g, 8, candidate, PickMode::CandidateOnly));
    EXPECT_FALSE(pick_spheres(ray, g, 0.5, radii, candidate, PickMode::CandidateOnly));
    EXPECT_FALSE(pick_glyphs(ray, g, directions, scales, mesh, candidate, PickMode::CandidateOnly));
    EXPECT_EQ(pick_points(pose, vp, 200, 200, g, 8, candidate)->element, 1u);
    EXPECT_EQ(pick_spheres(ray, g, 0.5, radii, candidate)->element, 1u);
    EXPECT_EQ(pick_glyphs(ray, g, directions, scales, mesh, candidate)->element, 1u);
  }
  EXPECT_EQ(pick_points(pose, vp, 200, 200, g, 8, 2u, PickMode::CandidateOnly)->element, 2u);
  const auto sphere = pick_spheres(ray, g, 0.5, radii, 2u, PickMode::CandidateOnly);
  ASSERT_TRUE(sphere);
  EXPECT_EQ(sphere->element, 2u);
  EXPECT_DOUBLE_EQ(sphere->local.z, -2.0); /* The candidate's per-point radius is preserved. */
  EXPECT_EQ(pick_glyphs(ray, g, directions, scales, mesh, 2u, PickMode::CandidateOnly)->element, 2u);
}

TEST(Picking, SegmentsRespectWidthIndicesOriginsAndCandidates)
{
  const std::vector<float> points{-1, 0, 0, 1, 0, 0, -1, 0, -3, 1, 0, -3, -1, 1, 0, 1, 1, 0};
  const std::vector<uint16_t> u16{1, 0, 3, 2, 5, 4};
  const std::vector<uint32_t> u32{1, 0, 3, 2, 5, 4};
  const dvec3 origin{1e6, -1e6, 1e6}, offset{1234.5, -0.125, 3e4};
  CameraPose pose;
  pose.parallel = true;
  pose.parallel_scale = 2;
  pose.position = offset + dvec3{0, 0, 10};
  pose.focal_point = offset;
  const Viewport vp{400, 400};
  for (const IndexSpan indices : {IndexSpan{std::span<const uint16_t>(u16)}, IndexSpan{std::span<const uint32_t>(u32)}}) {
    const LayerGeometry g{points, indices, origin, origin + offset};
    const auto hit = pick_segments(pose, vp, 225, 201.9, g, 4);
    ASSERT_TRUE(hit);
    EXPECT_EQ(hit->element, 0u);
    EXPECT_DOUBLE_EQ(hit->physical[0], 1e6 + offset.x + 0.25);
    EXPECT_DOUBLE_EQ(hit->physical[1], -1e6 + offset.y);
    EXPECT_DOUBLE_EQ(hit->local.z, offset.z);
    EXPECT_NEAR(hit->barycentric[1], 0.375, 1e-12); /* reversed index pair */
    EXPECT_FALSE(pick_segments(pose, vp, 225, 202.1, g, 4));
    EXPECT_EQ(pick_segments(pose, vp, 225, 200, g, 4, 1u, PickMode::CandidateOnly)->element, 1u);
    for (const auto candidate : {std::optional<uint32_t>(2), std::optional<uint32_t>(99), std::optional<uint32_t>()}) {
      EXPECT_FALSE(pick_segments(pose, vp, 225, 200, g, 4, candidate, PickMode::CandidateOnly));
      EXPECT_EQ(pick_segments(pose, vp, 225, 200, g, 4, candidate)->element, 0u);
    }
  }
}

TEST(Picking, SegmentsInterpolatePerspectiveDepth)
{
  const std::vector<float> points{-1, 0, 0, 1, 0, 8};
  const LayerGeometry g{points, std::span<const uint32_t>(), {}, {}};
  CameraPose pose;
  pose.position = {0, 0, 10};
  const Viewport vp{400, 400};
  const auto a = project(pose, vp, {-1, 0, 0}), b = project(pose, vp, {1, 0, 8});
  ASSERT_TRUE(a && b);
  const double x = (a->x + b->x) / 2;
  const auto hit = pick_segments(pose, vp, x, 200, g, 2);
  ASSERT_TRUE(hit);
  EXPECT_NEAR(hit->barycentric[1], 5.0 / 6.0, 1e-12);
  EXPECT_NEAR(hit->local.x, 2.0 / 3.0, 1e-12);
  EXPECT_NEAR(hit->local.z, 20.0 / 3.0, 1e-12);
  const auto projected = project(pose, vp, hit->local);
  ASSERT_TRUE(projected);
  EXPECT_NEAR(projected->x, x, 1e-10);
}

TEST(Picking, SegmentsHandleEndpointsAndDegenerateProjections)
{
  CameraPose pose;
  pose.position = {0, 0, 10};
  const Viewport vp{400, 400};
  /* A segment parallel to the ray must choose its nearer endpoint, even when it is stored last. */
  const std::vector<float> ray_points{0, 0, -4, 0, 0, 2};
  const LayerGeometry along_ray{ray_points, std::span<const uint32_t>(), {}, {}};
  const auto hit = pick_segments(pose, vp, 200, 200, along_ray, 2);
  ASSERT_TRUE(hit);
  EXPECT_DOUBLE_EQ(hit->local.z, 2);
  EXPECT_DOUBLE_EQ(hit->t, 8);
  EXPECT_DOUBLE_EQ(hit->barycentric[1], 1);

  const std::vector<float> point{0, 0, 0, 0, 0, 0};
  const LayerGeometry degenerate{point, std::span<const uint16_t>(), {}, {}};
  EXPECT_TRUE(pick_segments(pose, vp, 200.2, 200.2, degenerate, 1));
  EXPECT_FALSE(pick_segments(pose, vp, 200.4, 200.4, degenerate, 1));
  EXPECT_TRUE(pick_segments(pose, vp, 200.4, 200, degenerate, 0)); /* minimum one-pixel footprint */

  const std::vector<float> points{-1, 0, 0, 1, 0, 0};
  const LayerGeometry segment{points, std::span<const uint32_t>(), {}, {}};
  const auto end = project(pose, vp, {1, 0, 0});
  ASSERT_TRUE(end);
  const auto endpoint = pick_segments(pose, vp, end->x + 0.9, end->y, segment, 2);
  ASSERT_TRUE(endpoint);
  EXPECT_DOUBLE_EQ(endpoint->local.x, 1);
  EXPECT_FALSE(pick_segments(pose, vp, end->x + 1.1, end->y, segment, 2));
}

TEST(Picking, SegmentsClipBeforeProjection)
{
  CameraPose pose;
  pose.position = {0, 0, 10};
  const Viewport vp{400, 400};
  const std::vector<float> crossing{-1, 0, 11, 1, 0, 0};
  const LayerGeometry g{crossing, std::span<const uint32_t>(), {}, {}};
  const auto hit = pick_segments(pose, vp, 200, 200, g, 2);
  ASSERT_TRUE(hit); /* One endpoint is behind the camera but the visible middle crosses the cursor. */
  EXPECT_NEAR(hit->local.x, 0, 1e-12);
  EXPECT_NEAR(hit->local.z, 5.5, 1e-12);
  const auto clipped = pick_segments(pose, vp, 200, 200, g, 2, 0, PickMode::CandidateOnly, ClipRange{1, 8});
  ASSERT_TRUE(clipped);
  EXPECT_NEAR(clipped->local.z, 5.5, 1e-12);
  EXPECT_FALSE(pick_segments(pose, vp, 200, 200, g, 2, 0, PickMode::CandidateOnly, ClipRange{6, 8}));

  const std::vector<float> along{0, 0, 11, 0, 0, -5};
  const std::vector<float> behind{-1, 0, 11, 1, 0, 11}, far{-1, 0, -4, 1, 0, -4};
  for (bool parallel : {false, true}) {
    pose.parallel = parallel;
    const auto near = pick_segments(pose, vp, 200, 200,
                                   {along, std::span<const uint32_t>(), {}, {}}, 2,
                                   0, PickMode::CandidateOnly, ClipRange{2, 8});
    ASSERT_TRUE(near);
    EXPECT_NEAR(near->local.z, 8, 1e-12);
    EXPECT_FALSE(pick_segments(pose, vp, 200, 200, {behind, std::span<const uint32_t>(), {}, {}}, 2));
    EXPECT_FALSE(pick_segments(pose, vp, 200, 200, {far, std::span<const uint32_t>(), {}, {}}, 2,
                               0, PickMode::CandidateOnly, ClipRange{2, 8}));
  }
  /* Orthographic cameras inside the bounds have a negative near plane. Still refine visible
   * forward geometry and keep the returned ray parameter nonnegative. */
  const std::vector<float> inside{-1, 0, 9.5f, 1, 0, 9.5f};
  const auto orthographic = pick_segments(pose, vp, 200, 200,
                                         {inside, std::span<const uint32_t>(), {}, {}}, 2,
                                         0, PickMode::CandidateOnly, ClipRange{-1, 1});
  ASSERT_TRUE(orthographic);
  EXPECT_DOUBLE_EQ(orthographic->t, 0.5);
  const auto crossing_eye = pick_segments(pose, vp, 200, 200,
                                         {along, std::span<const uint32_t>(), {}, {}}, 2,
                                         0, PickMode::CandidateOnly, ClipRange{-1, 1});
  ASSERT_TRUE(crossing_eye);
  EXPECT_DOUBLE_EQ(crossing_eye->t, 0);
}

TEST(Picking, SegmentsRejectInvalidGeometryAndInputs)
{
  CameraPose pose;
  pose.position = {0, 0, 10};
  const Viewport vp{400, 400};
  const std::vector<float> points{-1, 0, 0, 1, 0, 0};
  const std::vector<uint16_t> invalid{0, 2};
  const LayerGeometry g{points, std::span<const uint32_t>(), {}, {}};
  EXPECT_FALSE(pick_segments(pose, vp, 200, 200, {points, std::span<const uint16_t>(invalid), {}, {}}, 2));
  const std::vector<uint32_t> incomplete{0};
  EXPECT_FALSE(pick_segments(pose, vp, 200, 200, {points, std::span<const uint32_t>(incomplete), {}, {}}, 2));
  EXPECT_FALSE(pick_segments(pose, {0, 400}, 200, 200, g, 2));
  EXPECT_FALSE(pick_segments(pose, vp, std::numeric_limits<double>::quiet_NaN(), 200, g, 2));
  EXPECT_FALSE(pick_segments(pose, vp, 200, 200, g, std::numeric_limits<double>::infinity()));
  EXPECT_FALSE(pick_segments(pose, vp, 200, 200, g, 2, 0, PickMode::CandidateOnly, ClipRange{8, 2}));
}

TEST(Picking, ExamplePayloadDomains)
{
  const io::Payload p = io::read_directory(test::example_dir());
  const io::Json &layer = *p.layer("domains");
  const auto positions = p.view<float>(layer["positions"].get<std::string>());
  const auto indices = p.view<uint32_t>(layer["indices"].get<std::string>());
  const dvec3 origin = dvec3::from(p.render_origin);
  LayerGeometry g{positions, indices, origin, dvec3::from(p.layer_origin(layer))};
  /* Straight down onto the middle cube (label 7 at x = 0 relative): its top face at z = +1. */
  const auto hit = pick_triangles({{0.1, 0.2, 50}, {0, 0, -1}}, g);
  ASSERT_TRUE(hit.has_value());
  EXPECT_DOUBLE_EQ(hit->physical[0], 100.1);
  EXPECT_DOUBLE_EQ(hit->physical[1], 50.2);
  EXPECT_DOUBLE_EQ(hit->physical[2], 26.0);
}
