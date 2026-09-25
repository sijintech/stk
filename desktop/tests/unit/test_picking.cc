/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Pick refinement in float64. Acceptance (WP5): pick error <= 1e-12 relative at render_origin = 1e6. */
#include "support.hh"

#include "stk/io/payload.hh"
#include "stk/viewer/picking.hh"

#include <gtest/gtest.h>

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
