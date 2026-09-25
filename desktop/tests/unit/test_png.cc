/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "support.hh"

#include "stk/io/png.hh"

#include <gtest/gtest.h>

using namespace stk;
using io::Json;

TEST(Png, DecodesEveryColourTypeToRgba8)
{
  const Json cases = test::fixture_json("png/cases.json");
  for (const Json &c : cases["decode"]) {
    const io::Image image = io::read_png(test::fixtures_dir() / "png" / (c["name"].get<std::string>() + ".png"));
    ASSERT_EQ(image.width, c["width"].get<uint32_t>());
    ASSERT_EQ(image.height, c["height"].get<uint32_t>());
    ASSERT_EQ(image.channels, 4u);
    const Json &rgba = c["rgba"];
    for (size_t i = 0; i < rgba.size(); i++) {
      for (size_t k = 0; k < 4; k++) {
        EXPECT_EQ(image.pixels[4 * i + k], rgba[i][k].get<int>()) << c["name"] << " pixel " << i;
      }
    }
  }
  for (const Json &name : cases["invalid"]) {
    EXPECT_THROW(io::read_png(test::fixtures_dir() / "png" / name.get<std::string>()), io::PngError) << name;
  }
  const std::vector<uint8_t> junk{1, 2, 3};
  EXPECT_THROW(io::decode_png(junk), io::PngError);
}

TEST(Png, EncodeRoundTripsWithStrideAndChannels)
{
  const auto dir = test::scratch_dir("png");
  for (uint32_t channels = 1; channels <= 4; channels++) {
    const uint32_t w = 37, h = 11;
    const size_t stride = w * channels + 5;
    std::vector<uint8_t> pixels(stride * h, 0xAB);
    for (uint32_t y = 0; y < h; y++) {
      for (uint32_t x = 0; x < w * channels; x++) {
        pixels[y * stride + x] = uint8_t((x * 7 + y * 13) & 0xFF);
      }
    }
    const std::vector<uint8_t> png = io::encode_png(pixels.data(), w, h, channels, stride);
    const io::Image back = io::decode_png(png);
    ASSERT_EQ(back.width, w);
    for (uint32_t y = 0; y < h; y++) {
      for (uint32_t x = 0; x < w; x++) {
        const uint8_t *src = pixels.data() + y * stride + x * channels;
        const uint8_t *dst = back.pixel(x, y);
        const uint8_t gray = src[0];
        const uint8_t expect[4] = {channels >= 3 ? src[0] : gray, channels >= 3 ? src[1] : gray,
                                   channels >= 3 ? src[2] : gray,
                                   channels == 4 ? src[3] : channels == 2 ? src[1] : uint8_t(255)};
        for (int k = 0; k < 4; k++) {
          ASSERT_EQ(dst[k], expect[k]) << channels << " " << x << "," << y;
        }
      }
    }
  }
  io::Image image(3, 2, 4);
  image.pixel(2, 1)[0] = 200;
  io::write_png(dir / "out.png", image, {9});
  EXPECT_EQ(io::read_png(dir / "out.png").pixel(2, 1)[0], 200);
  io::PngLimits limits;
  limits.max_pixels = 5;
  EXPECT_THROW(io::read_png(dir / "out.png", limits), io::PngError);
  EXPECT_THROW(io::encode_png(image.pixels.data(), 0, 1, 4), io::PngError);
}
