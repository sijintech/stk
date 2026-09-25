/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Glyph geometry parity with the VTK sources of suan/render/offscreen.py glyph_source (spec §6.5):
 * points (1e-6), polygons (identical), normals and the vtkTriangleFilter triangle count. */
#include "support.hh"

#include "stk/viewer/glyph.hh"

#include <gtest/gtest.h>

using namespace stk;
using namespace stk::viewer;
using io::Json;

TEST(GlyphParity, VtkSourcesPointForPoint)
{
  const Json fixture = test::fixture_json("glyph_vtk.json");
  int count = 0;
  for (const Json &c : fixture["glyphs"]) {
    const auto shape = parse_glyph_shape(c["shape"].get<std::string>());
    ASSERT_TRUE(shape.has_value());
    const GlyphMesh mesh = glyph_mesh(*shape, c["resolution"].get<int>(), c["center"].get<bool>());
    const std::string what = c["shape"].get<std::string>() + " res " + std::to_string(c["resolution"].get<int>()) +
                             (c["center"].get<bool>() ? " centred" : "");
    ASSERT_EQ(mesh.points.size(), c["points"].size()) << what;
    for (size_t i = 0; i < mesh.points.size(); i++) {
      for (size_t k = 0; k < 3; k++) {
        EXPECT_NEAR(mesh.points[i][k], c["points"][i][k].get<double>(), 1e-6) << what << " point " << i;
      }
    }
    ASSERT_EQ(mesh.polygons.size(), c["polygons"].size()) << what;
    for (size_t i = 0; i < mesh.polygons.size(); i++) {
      EXPECT_EQ(Json(mesh.polygons[i]), c["polygons"][i]) << what << " polygon " << i;
    }
    EXPECT_EQ(mesh.lines.size(), c["lines"].get<size_t>()) << what;
    EXPECT_EQ(mesh.triangles().size() / 3, c["triangles"].get<size_t>()) << what;
    if (c["normals"].is_null()) {
      EXPECT_TRUE(mesh.normals.empty()) << what;
    }
    else {
      ASSERT_EQ(mesh.normals.size(), c["normals"].size()) << what;
      for (size_t i = 0; i < mesh.normals.size(); i++) {
        for (size_t k = 0; k < 3; k++) {
          EXPECT_NEAR(mesh.normals[i][k], c["normals"][i][k].get<double>(), 1e-6) << what;
        }
      }
    }
    count++;
  }
  std::printf("[glyph parity] %d glyph meshes identical to VTK %s sources\n", count,
              fixture["vtk"].get<std::string>().c_str());
}

TEST(Glyph, InstanceScalesAndTransforms)
{
  const std::vector<float> dirs{3, 4, 0, 0, 0, 0, -1, 0, 0, std::nanf(""), 0, 0};
  const auto uniform = instance_scales(dirs, {}, GlyphScale{ScaleMode::Uniform, 0.5, ""});
  EXPECT_DOUBLE_EQ(uniform[0], 0.5);
  EXPECT_TRUE(std::isnan(uniform[1])); /* |d| = 0: not drawn */
  EXPECT_TRUE(std::isnan(uniform[3])); /* non-finite direction */
  const auto magnitude = instance_scales(dirs, {}, GlyphScale{ScaleMode::Magnitude, 2.0, ""});
  EXPECT_DOUBLE_EQ(magnitude[0], 10.0);
  const std::vector<double> attr{1, 2, 2, 0, 0, 0, -4, 0, 0, 1, 1, 1};
  const auto by_attribute = instance_scales(dirs, {}, GlyphScale{ScaleMode::Attribute, 1.0, "a"}, attr, 3);
  EXPECT_DOUBLE_EQ(by_attribute[0], 3.0);
  EXPECT_DOUBLE_EQ(by_attribute[2], 4.0);
  const std::vector<float> explicit_scales{-2, 1, 1, 1};
  EXPECT_DOUBLE_EQ(instance_scales(dirs, explicit_scales, {})[0], 2.0); /* offscreen draws |s| */
  EXPECT_EQ(GlyphScale::from_json(io::parse_json(R"({"by": "magnitude", "factor": 0.25})")).factor, 0.25);

  for (const dvec3 d : {dvec3{3, 4, 0}, dvec3{-1, 0, 0}, dvec3{1, 0, 0}, dvec3{0, 0, -2}, dvec3{-1, -1e-9, 0}}) {
    const dmat4 m = instance_matrix({10, 20, 30}, d, 2.0);
    const dvec3 tip = m.transform_point({1, 0, 0});
    const dvec3 expected = dvec3{10, 20, 30} + normalize(d) * 2.0;
    EXPECT_NEAR(length(tip - expected), 0.0, 1e-12) << d.x << "," << d.y << "," << d.z;
    EXPECT_NEAR(m.determinant(), 8.0, 1e-9); /* a rotation (no mirror) times scale^3 */
  }
  const GlyphMesh cube = glyph_mesh(GlyphShape::Cube);
  std::vector<std::array<float, 3>> positions, normals;
  cube.flat(positions, normals);
  EXPECT_EQ(positions.size(), 36u);
}
