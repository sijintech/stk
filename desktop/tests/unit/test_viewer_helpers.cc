/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/viewer/colormap.hh"
#include "stk/viewer/geometry.hh"
#include "stk/viewer/volume.hh"

#include <gtest/gtest.h>

#include <cmath>
#include <limits>

using namespace stk;
using namespace stk::viewer;
using io::Json;

TEST(LayerScalarsParity, PythonPayloadsAndScalarSelection)
{
  const Json fixture = test::fixture_json("viewer_helpers.json");
  for (const Json &c : fixture["scalars"]) {
    SCOPED_TRACE(c["name"].get<std::string>());
    const io::Payload payload = io::decode_stkp(core::SharedBytes::from_vector(
        test::base64_decode(c["stkp"].get<std::string>())));
    const Json &layer = *payload.layer("points");
    const Json &spec = layer["appearance"]["color"];
    const auto scalars = layer_scalars(payload, layer, spec);
    ASSERT_TRUE(scalars);
    EXPECT_EQ(scalars->association, "point");
    EXPECT_EQ(scalars->categorical, c["categorical"].get<bool>());
    ASSERT_EQ(scalars->values.size(), c["values"].size());
    for (size_t i = 0; i < scalars->values.size(); i++) {
      const double expected = test::fixture_number(c["values"][i]);
      if (std::isnan(expected)) {
        EXPECT_TRUE(std::isnan(scalars->values[i]));
      }
      else {
        EXPECT_DOUBLE_EQ(scalars->values[i], expected);
      }
    }
    if (c["range"].is_null()) {
      EXPECT_FALSE(scalars->range);
    }
    else {
      ASSERT_TRUE(scalars->range);
      EXPECT_EQ((*scalars->range)[0], c["range"][0].get<double>());
      EXPECT_EQ((*scalars->range)[1], c["range"][1].get<double>());
    }
    EXPECT_EQ(scalars->colormap, c["colormap"].is_null() ? std::nullopt :
        std::optional<std::string>(c["colormap"].get<std::string>()));
    const ColorResult colors = layer_colors(payload, layer, spec, scalars->values.size(), "point");
    EXPECT_EQ(colors.range, scalars->range);
    EXPECT_EQ(colors.categorical, scalars->categorical);
    if (!scalars->categorical) {
      const ContinuousColormap grey = grey_colormap();
      for (size_t i = 0; i < scalars->values.size(); i++) {
        EXPECT_EQ(colors.colors[i], grey.map(scalars->values[i], (*scalars->range)[0], (*scalars->range)[1]));
      }
    }
  }
}

TEST(LayerScalars, AbsentAttributesAndCellAssociation)
{
  const io::Payload payload = io::read_directory(test::example_dir());
  Json layer = *payload.layer("domains");
  EXPECT_FALSE(layer_scalars(payload, layer, Json()));
  EXPECT_FALSE(layer_scalars(payload, layer, {{"by", "solid"}}));
  EXPECT_FALSE(layer_scalars(payload, layer, {{"by", "direction"}}));
  EXPECT_FALSE(layer_scalars(payload, layer, {{"by", "attribute"}, {"attribute", "missing"}}));
  const auto name = layer["attributes"].begin().key();
  layer["attributes"][name]["association"] = "cell";
  const Json spec{{"by", "attribute"}, {"attribute", name}};
  const auto scalars = layer_scalars(payload, layer, spec);
  ASSERT_TRUE(scalars);
  EXPECT_EQ(scalars->association, "cell");
  const auto colors = layer_colors(payload, layer, spec, scalars->values.size(), "point");
  ASSERT_FALSE(colors.warnings.empty());
  EXPECT_NE(colors.warnings[0].find("association differs"), std::string::npos);
}

TEST(SmoothNormalsParity, NumpyAreaWeightedNormalsForBothIndexWidths)
{
  const Json fixture = test::fixture_json("viewer_helpers.json");
  for (const Json &c : fixture["normals"]) {
    SCOPED_TRACE(c["name"].get<std::string>());
    const std::vector<float> positions = c["positions"].get<std::vector<float>>();
    const std::vector<uint32_t> indices32 = c["indices"].get<std::vector<uint32_t>>();
    const std::vector<uint16_t> indices16(indices32.begin(), indices32.end());
    for (const IndexSpan &indices : {IndexSpan(std::span<const uint32_t>(indices32)),
                                     IndexSpan(std::span<const uint16_t>(indices16))}) {
      const auto normals = smooth_normals(positions, indices);
      ASSERT_EQ(normals.size(), c["normals"].size());
      for (size_t i = 0; i < normals.size(); i++) {
        EXPECT_FLOAT_EQ(normals[i], c["normals"][i].get<float>()) << "component " << i;
      }
    }
  }
}

TEST(SmoothNormals, SequentialTrianglesAndInvalidFaces)
{
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const std::vector<float> positions{0, 0, 0, 2, 0, 0, 0, 2, 0, nan, 0, 0, 99};
  const std::vector<float> expected{0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0};
  EXPECT_EQ(smooth_normals(positions), expected);
  const std::vector<uint32_t> indices{0, 1, 2, 0, 1, 3, 0, 1, 900, 0, 1};
  EXPECT_EQ(smooth_normals(positions, std::span<const uint32_t>(indices)), expected);
  EXPECT_TRUE(smooth_normals({}).empty());
}

TEST(SmoothNormals, FiniteAcrossFloat32Scales)
{
  for (const float scale : {1e-30f, 1.0f, 1e30f}) {
    const std::vector<float> positions{0, 0, 0, scale, 0, 0, 0, scale, 0};
    const std::vector<float> expected{0, 0, 1, 0, 0, 1, 0, 0, 1};
    EXPECT_EQ(smooth_normals(positions), expected);
  }
}

TEST(StoredRange, StoredSamplesAndNormalizedIntegerDomains)
{
  const std::vector<uint8_t> bytes{1, 128, 255};
  const std::vector<uint16_t> shorts{1, 1024, 65535};
  EXPECT_EQ(stored_range(bytes), (std::array<double, 2>{1, 255}));
  EXPECT_EQ(stored_range(bytes, true), (std::array<double, 2>{1.0 / 255, 1}));
  EXPECT_EQ(stored_range(shorts), (std::array<double, 2>{1, 65535}));
  EXPECT_EQ(stored_range(shorts, true), (std::array<double, 2>{1.0 / 65535, 1}));
  const std::vector<float> values{NAN, INFINITY, -INFINITY, -3.5f, 7.25f};
  EXPECT_EQ(stored_range(values), (std::array<double, 2>{-3.5, 7.25}));
}

TEST(StoredRange, EmptyNonfiniteAndConstantSamples)
{
  EXPECT_EQ(stored_range(std::span<const float>{}), (std::array<double, 2>{0, 1}));
  EXPECT_EQ(stored_range(std::span<const uint8_t>{}, true), (std::array<double, 2>{0, 1}));
  const std::vector<float> invalid{NAN, INFINITY, -INFINITY};
  EXPECT_EQ(stored_range(invalid), (std::array<double, 2>{0, 1}));
  const std::vector<float> constant{8.0f, 8.0f};
  EXPECT_EQ(stored_range(constant), (std::array<double, 2>{7.5, 8.5}));
  const std::vector<uint16_t> normalized{65535, 65535};
  EXPECT_EQ(stored_range(normalized, true), (std::array<double, 2>{0.5, 1.5}));
  for (const float value : {std::numeric_limits<float>::max(), -std::numeric_limits<float>::max()}) {
    const auto range = stored_range(std::span<const float>(&value, 1));
    EXPECT_TRUE(std::isfinite(range[0]));
    EXPECT_TRUE(std::isfinite(range[1]));
    EXPECT_LT(range[0], value);
    EXPECT_GT(range[1], value);
  }
}

TEST(VolumeFloatTexture, AllNegativeValuesCannotBecomeHoles)
{
  std::vector<float> values{-1.0e38f, -7.5e37f, -5.0e37f};
  const auto original = values;
  const auto range = normalize_volume_floats(values);
  EXPECT_EQ(range, (std::array<double, 2>{double(original.front()), double(original.back())}));
  EXPECT_FLOAT_EQ(values.front(), 0.0f);
  EXPECT_NEAR(values[1], 0.5f, 2.0f * std::numeric_limits<float>::epsilon());
  EXPECT_FLOAT_EQ(values.back(), 1.0f);
  for (const float value : values) {
    EXPECT_GE(value, 0.0f);
    EXPECT_GT(value, kVolumeHoleThreshold);
  }
}

TEST(VolumeFloatTexture, OppositeExtremeValuesDoNotOverflow)
{
  std::vector<float> values{-3.0e38f, 0.0f, 3.0e38f};
  const auto range = normalize_volume_floats(values);
  EXPECT_GT(range[1] - range[0], double(std::numeric_limits<float>::max()));
  EXPECT_TRUE(std::isfinite(range[1] - range[0]));
  EXPECT_EQ(values, (std::vector<float>{0.0f, 0.5f, 1.0f}));
}

TEST(VolumeFloatTexture, SubnormalRangeRetainsEndpointsAndZero)
{
  const float tiny = std::numeric_limits<float>::denorm_min();
  std::vector<float> values{-tiny, 0.0f, tiny};
  EXPECT_EQ(normalize_volume_floats(values), (std::array<double, 2>{-double(tiny), double(tiny)}));
  EXPECT_EQ(values, (std::vector<float>{0.0f, 0.5f, 1.0f}));
}

TEST(VolumeFloatTexture, ConstantsAcrossFloat32ScalesUseExpandedDomain)
{
  for (const float value : {0.0f, -0.0f, std::numeric_limits<float>::denorm_min(),
                            -std::numeric_limits<float>::denorm_min(), 1.0e-30f, -1.0e-30f,
                            std::ldexp(1.0f, 100), -std::ldexp(1.0f, 100),
                            std::numeric_limits<float>::max(), -std::numeric_limits<float>::max()}) {
    SCOPED_TRACE(value);
    std::vector<float> values(3, value);
    const auto range = normalize_volume_floats(values);
    EXPECT_TRUE(std::isfinite(range[0]));
    EXPECT_TRUE(std::isfinite(range[1]));
    EXPECT_LT(range[0], double(value));
    EXPECT_GT(range[1], double(value));
    /* Adjacent doubles around an exact power of two have unequal spacing. The normalized
     * constant need not be 0.5; inverse mapping is bounded by the upload's relative precision. */
    const double t = (double(value) - range[0]) / (range[1] - range[0]);
    for (const float uploaded : values) {
      EXPECT_TRUE(std::isfinite(uploaded));
      EXPECT_GT(uploaded, 0.0f);
      EXPECT_LT(uploaded, 1.0f);
      EXPECT_FLOAT_EQ(uploaded, float(t));
      EXPECT_NEAR(range[0] + double(uploaded) * (range[1] - range[0]), double(value),
                  (range[1] - range[0]) * std::numeric_limits<float>::epsilon());
    }
  }
}

TEST(VolumeFloatTexture, MissingSamplesUseSeparateFiniteDomain)
{
  EXPECT_EQ(normalize_volume_floats({}), (std::array<double, 2>{0.0, 1.0}));
  std::vector<float> missing{NAN, INFINITY, -INFINITY};
  EXPECT_EQ(normalize_volume_floats(missing), (std::array<double, 2>{0.0, 1.0}));
  EXPECT_EQ(missing, std::vector<float>(3, kVolumeHoleValue));
  std::vector<float> mixed{NAN, -1.0e38f, INFINITY, -5.0e37f, -INFINITY};
  normalize_volume_floats(mixed);
  EXPECT_EQ(mixed, (std::vector<float>{kVolumeHoleValue, 0.0f, kVolumeHoleValue, 1.0f, kVolumeHoleValue}));
  EXPECT_LT(kVolumeHoleValue, kVolumeHoleThreshold);
  EXPECT_LT(kVolumeHoleThreshold, 0.0f);
  for (const float value : mixed) {
    EXPECT_TRUE(std::isfinite(value));
  }
}

TEST(VolumeFloatTexture, OriginalDomainReconstructsSignedValuesAndPhysicalTransfer)
{
  const std::vector<float> original{-37.0f, -16.25f, -0.125f, 0.0f, 4.5f, 81.0f};
  auto uploaded = original;
  const auto range = normalize_volume_floats(uploaded);
  const double width = range[1] - range[0];
  VolumeTransfer tf;
  tf.value_scale = 3.0;
  tf.value_offset = -8.0;
  tf.color_points = {{-119.0, 0.0, 0.0, 1.0}, {235.0, 1.0, 0.0, 0.0}};
  tf.opacity_points = {{-119.0, 0.1}, {235.0, 0.9}};
  for (size_t i = 0; i < original.size(); i++) {
    const double recovered = range[0] + double(uploaded[i]) * width;
    EXPECT_NEAR(recovered, original[i], width * std::numeric_limits<float>::epsilon());
    EXPECT_NEAR(tf.stored_to_physical(recovered), tf.stored_to_physical(original[i]),
                width * tf.value_scale * std::numeric_limits<float>::epsilon());
  }
  /* Normalization changes texture coordinates only; the LUT still spans original physical units. */
  const auto lut = transfer_lut(tf, range[0], range[1], 16);
  for (size_t i = 0; i < lut.size(); i++) {
    const double t = (double(i) + 0.5) / double(lut.size());
    EXPECT_NEAR(lut[i][0], t, 1e-7);
    EXPECT_NEAR(lut[i][2], 1.0 - t, 1e-7);
    EXPECT_NEAR(lut[i][3], 0.1 + 0.8 * t, 1e-7);
  }
}
