/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Colour mapping parity: suan/render/colormaps.py (lut_index, hsl, orientation, stk:categorical,
 * rgba8) and web/src/colormaps.ts (lutIndex, layerColors for every layer of the payload fixtures,
 * volumeColorPoints). */
#include "support.hh"

#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "stk/viewer/colormap.hh"

#include <gtest/gtest.h>

#include <cmath>

using namespace stk;
using namespace stk::viewer;
using io::Json;

namespace {

void expect_rgb(const RGB &got, const Json &want, double tol, const std::string &what)
{
  for (size_t k = 0; k < 3; k++) {
    EXPECT_NEAR(got[k], want[k].get<double>(), tol) << what << " channel " << k;
  }
}

std::string hex(const std::vector<RGBA8> &colors)
{
  std::vector<uint8_t> bytes;
  for (const RGBA8 &c : colors) {
    bytes.insert(bytes.end(), c.begin(), c.end());
  }
  return core::to_hex(bytes);
}

io::Payload fixture_payload(const std::string &name)
{
  return name == "example" ? io::read_directory(test::example_dir())
                           : io::read_stkp(test::fixtures_dir() / "payload" / "scenes" / (name + ".stkp"));
}

}  // namespace

TEST(ColormapParity, LutIndexMatchesPythonAndWeb)
{
  const Json fixture_1 = test::fixture_json("colormap_cases.json");
  for (const Json &c : fixture_1["lut_index"]) {
    EXPECT_EQ(lut_index(test::fixture_number(c["v"]), c["lo"].get<double>(), c["hi"].get<double>()), c["index"].get<int>())
        << c.dump();
  }
  const Json fixture_2 = test::fixture_json("web_vectors.json");
  for (const Json &c : fixture_2["lut"]) {
    EXPECT_EQ(lut_index(test::fixture_number(c["v"]), c["lo"].get<double>(), c["hi"].get<double>()), c["index"].get<int>())
        << c.dump();
  }
}

TEST(ColormapParity, HslOrientationAndCategoricalColours)
{
  const Json py = test::fixture_json("colormap_cases.json");
  const Json web = test::fixture_json("web_vectors.json");
  for (const Json *cases : {&py["hsl"], &web["hsl"]}) {
    for (const Json &c : *cases) {
      expect_rgb(hsl_to_rgb(c["hsl"][0].get<double>(), c["hsl"][1].get<double>(), c["hsl"][2].get<double>()), c["rgb"],
                 1e-12, c.dump());
    }
  }
  for (const Json *cases : {&py["orientation"], &web["orientation"]}) {
    for (const Json &c : *cases) {
      const RGB rgb = orientation_hsl(c["p"][0].get<double>(), c["p"][1].get<double>(), c["p"][2].get<double>(),
                                      c["M"].get<double>(), c["l"][0].get<double>(), c["l"][1].get<double>());
      expect_rgb(rgb, c["rgb"], 1e-12, c.dump());
    }
  }
  for (const Json *cases : {&py["categorical"], &web["categorical"]}) {
    for (const Json &c : *cases) {
      expect_rgb(categorical_color(c["v"].get<double>()), c["rgb"], 1e-12, c.dump());
    }
  }
  for (const Json &c : py["rgba8"]) {
    std::vector<double> values;
    for (const Json &v : c["c"]) {
      values.push_back(v.get<double>());
    }
    const RGBA8 got = rgba8(values);
    for (size_t k = 0; k < 4; k++) {
      EXPECT_EQ(got[k], c["rgba"][k].get<int>()) << c.dump();
    }
  }
}

TEST(ColormapParity, LayerColoursMatchTheWebViewer)
{
  const Json web = test::fixture_json("web_vectors.json")["payloads"];
  int layers = 0;
  size_t tuples = 0;
  for (auto it = web.begin(); it != web.end(); ++it) {
    const io::Payload p = fixture_payload(it.key());
    for (const Json &expected : it.value()["colors"]) {
      const Json &layer = *p.layer(expected["layer"].get<std::string>());
      const Json appearance = layer.value("appearance", Json::object());
      const Json spec = appearance.value("color", Json());
      std::vector<float> vectors;
      if (layer["type"] == "instances") {
        vectors = p.floats(layer["directions"].get<std::string>());
      }
      const std::string association = expected["association"].get<std::string>();
      const ColorResult r = layer_colors(p, layer, spec, expected["count"].get<size_t>(),
                                         layer["type"] == "slice_image" ? "point" : association, vectors);
      const std::string what = it.key() + "/" + expected["layer"].get<std::string>();
      if (expected["colors"].is_null()) {
        EXPECT_TRUE(r.colors.empty()) << what;
      }
      else {
        EXPECT_EQ(hex(r.colors), expected["colors"].get<std::string>()) << what;
        tuples += r.colors.size();
      }
      EXPECT_EQ(r.categorical, expected["categorical"].get<bool>()) << what;
      EXPECT_EQ(r.nearest, expected["nearest"].get<bool>()) << what;
      if (!expected["range"].is_null()) {
        ASSERT_TRUE(r.range.has_value()) << what;
        EXPECT_EQ((*r.range)[0], expected["range"][0].get<double>()) << what;
        EXPECT_EQ((*r.range)[1], expected["range"][1].get<double>()) << what;
      }
      for (size_t k = 0; k < 3; k++) {
        EXPECT_EQ(r.solid[k], expected["solid"][k].get<double>()) << what;
      }
      layers++;
    }
    for (const Json &expected : it.value()["volumes"]) {
      const Json &layer = *p.layer(expected["layer"].get<std::string>());
      const auto cm = resolve_colormap(p, layer["transfer_function"]["colormap"].get<std::string>());
      const auto points = volume_color_points(cm ? &*cm : nullptr,
                                              {layer["transfer_function"]["range"][0].get<double>(),
                                               layer["transfer_function"]["range"][1].get<double>()});
      ASSERT_EQ(points.size(), expected["points"].size());
      for (size_t i = 0; i < points.size(); i++) {
        for (size_t k = 0; k < 4; k++) {
          EXPECT_EQ(points[i][k], expected["points"][i][k].get<double>());
        }
      }
    }
  }
  std::printf("[colormap parity] %d layers, %zu tuples coloured identically to web layerColors\n", layers, tuples);
  EXPECT_GE(layers, 10);
}

TEST(Colormap, GpuTextureBinsExactly)
{
  const ContinuousColormap grey = grey_colormap();
  const auto texture = grey.texture();
  EXPECT_EQ(ContinuousColormap::texel(-0.1, 0, 1), 0);
  EXPECT_EQ(ContinuousColormap::texel(0.0, 0, 1), 1);
  EXPECT_EQ(ContinuousColormap::texel(1.0, 0, 1), 256);
  EXPECT_EQ(ContinuousColormap::texel(1.5, 0, 1), 257);
  EXPECT_EQ(ContinuousColormap::texel(std::nan(""), 0, 1), 258);
  for (double v : {0.0, 0.1, 0.5, 0.999, 1.0, -1.0, 2.0}) {
    EXPECT_EQ(texture[size_t(ContinuousColormap::texel(v, 0, 1))], grey.map(v, 0, 1)) << v;
  }
  CategoricalColormap palette;
  palette.lookup[7] = {1, 2, 3, 255};
  EXPECT_EQ(palette.map(7.0), (RGBA8{1, 2, 3, 255}));
  EXPECT_EQ(palette.map(7.5), palette.unknown); /* categorical values are never interpolated */
  EXPECT_EQ(palette.map(-0.0 + 7), (RGBA8{1, 2, 3, 255}));
}
