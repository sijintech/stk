/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/io/payload.hh"
#include "stk/viewer/lod.hh"
#include "stk/viewer/scene.hh"
#include "stk/viewer/volume.hh"

#include <gtest/gtest.h>

#include <cmath>

using namespace stk;
using namespace stk::viewer;
using io::Json;

TEST(VolumeParity, OpacityFunctionsMatchPython)
{
  const Json py = test::fixture_json("colormap_cases.json");
  for (const Json &c : py["categorical_opacity"]) {
    const auto points = categorical_opacity(c["range"][0].get<double>(), c["range"][1].get<double>());
    ASSERT_EQ(points.size(), c["points"].size());
    for (size_t i = 0; i < points.size(); i++) {
      EXPECT_EQ(points[i][0], c["points"][i][0].get<double>());
      EXPECT_EQ(points[i][1], c["points"][i][1].get<double>());
    }
  }
  for (const Json &c : py["opacity"]) {
    std::vector<std::array<double, 2>> points;
    for (const Json &p : c["points"]) {
      points.push_back({p[0].get<double>(), p[1].get<double>()});
    }
    /* colormaps.opacity_at sorts (value, alpha) pairs; the renderers (VTK/vtk.js AddPoint) keep the last
     * point of a duplicated value instead, as volume_transfer() does. */
    std::sort(points.begin(), points.end());
    EXPECT_DOUBLE_EQ(evaluate_opacity(points, c["v"].get<double>()), c["alpha"].get<double>()) << c.dump();
  }
}

TEST(Volume, TransferFunctionOfTheExample)
{
  const io::Payload p = io::read_directory(test::example_dir());
  const VolumeTransfer tf = volume_transfer(p, *p.layer("density"));
  EXPECT_EQ(tf.grid.dimensions, (std::array<int64_t, 3>{8, 8, 8}));
  EXPECT_DOUBLE_EQ(tf.grid.unit_distance(), std::min({tf.grid.spacing.x, tf.grid.spacing.y, tf.grid.spacing.z}));
  EXPECT_EQ(tf.color_points.size(), 256u);
  EXPECT_FALSE(tf.categorical);
  const auto lut = transfer_lut(tf, 0, 255, 256);
  ASSERT_EQ(lut.size(), 256u);
  /* Texel i samples the physical value at its centre. */
  const double physical = tf.stored_to_physical(0 + (100 + 0.5) / 256 * 255);
  const RGB c = evaluate_color(tf.color_points, physical);
  EXPECT_FLOAT_EQ(lut[100][0], float(c[0]));
  EXPECT_FLOAT_EQ(lut[100][3], float(evaluate_opacity(tf.opacity_points, physical)));
  /* Grid transform and bounds. */
  const dmat4 m = tf.grid.index_to_local();
  const dvec3 corner = m.transform_point({7, 7, 7});
  EXPECT_DOUBLE_EQ(corner.x, tf.grid.origin.x + 7 * tf.grid.spacing.x);
  const Bounds b = computed_bounds(p);
  EXPECT_TRUE(b.valid());
  EXPECT_LE(b.lo.x, tf.grid.origin.x);
}

TEST(Volume, CategoricalStepsAndOpacityCorrection)
{
  std::vector<std::array<double, 4>> points;
  for (int label : {1, 2, 5}) {
    points.push_back({label - 0.499, double(label), 0, 0});
    points.push_back({label + 0.499, double(label), 0, 0});
  }
  for (int label : {1, 2, 5}) {
    EXPECT_DOUBLE_EQ(evaluate_color(points, label)[0], label); /* exactly its colour */
    EXPECT_DOUBLE_EQ(evaluate_color(points, label + 0.3)[0], label);
  }
  EXPECT_DOUBLE_EQ(evaluate_color(points, -10)[0], 1.0); /* clamped */
  EXPECT_DOUBLE_EQ(evaluate_color(points, 99)[0], 5.0);
  EXPECT_DOUBLE_EQ(opacity_correction(0.3, 1.0, 1.0), 0.3);
  EXPECT_NEAR(opacity_correction(0.3, 2.0, 1.0), 1 - 0.7 * 0.7, 1e-15);
  EXPECT_NEAR(opacity_correction(0.3, 0.5, 0.5), 0.3, 1e-15); /* independent of the absolute spacing */
  EXPECT_DOUBLE_EQ(opacity_correction(1.0, 0.1, 1.0), 1.0);
}

TEST(Lod, PolicyFollowsBudgetsInteractionAndFrameTime)
{
  LodBudget budget;
  budget.triangles = 1000;
  budget.interactive_triangles = 100;
  budget.instances = 500;
  budget.interactive_instances = 50;
  LodPolicy policy(budget, 16.0);
  const std::vector<uint64_t> levels{50, 400, 5000};
  EXPECT_EQ(policy.triangle_level(levels), 1u);
  policy.set_interacting(true);
  EXPECT_EQ(policy.triangle_level(levels), 0u);
  EXPECT_EQ(policy.instance_prefix(10000, true), 50u);
  EXPECT_EQ(policy.instance_prefix(10000, false), 10000u);
  EXPECT_GT(policy.volume_step(), 1.0);
  policy.set_interacting(false);
  EXPECT_DOUBLE_EQ(policy.volume_step(), 0.5);
  EXPECT_EQ(policy.instance_prefix(10000, true), 500u);
  for (int i = 0; i < 10; i++) {
    policy.report_frame(64.0);
  }
  EXPECT_LT(policy.quality(), 0.3);
  EXPECT_LT(policy.instance_prefix(10000, true), 500u);
  for (int i = 0; i < 200; i++) {
    policy.report_frame(2.0);
  }
  EXPECT_DOUBLE_EQ(policy.quality(), 1.0);
  const std::vector<uint64_t> none{};
  EXPECT_EQ(policy.volume_level(none), 0u);
}

TEST(Scene, BoundsProbeAnchorsAndLegend)
{
  const io::Payload p = io::read_directory(test::example_dir());
  const Bounds manifest = payload_bounds(p);
  const Bounds computed = computed_bounds(p);
  EXPECT_TRUE(manifest.valid());
  EXPECT_LE(computed.lo.x, manifest.lo.x + 1e-6);
  const Json layer = io::parse_json(R"({"id": "x", "node": "surface", "pick": {"probe": {"node": "src", "dataset": "Polar"}}})");
  EXPECT_EQ(probe_of(layer)->node, "src");
  EXPECT_EQ(probe_of(io::parse_json(R"({"node": "surface"})"))->node, "surface");
  EXPECT_FALSE(probe_of(io::parse_json(R"({"id": "x"})")).has_value());
  EXPECT_EQ(overlay_anchor(io::parse_json(R"({"kind": "scalar_bar"})")), "right");
  EXPECT_EQ(overlay_anchor(io::parse_json(R"({"kind": "legend", "anchor": "bottom"})")), "bottom");
  const auto cm = resolve_colormap(p, "pal0");
  ASSERT_TRUE(cm && cm->categorical);
  const auto items = legend_items(*cm->categorical, io::parse_json("[1, 7, 19, 999]"));
  ASSERT_EQ(items.size(), 4u);
  EXPECT_EQ(items[0].name, "T[100]");
  EXPECT_EQ(items[3].name, "999");
  EXPECT_EQ(items[3].color, cm->categorical->unknown);
}
