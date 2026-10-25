/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "evidence_pixels.hh"
#include <gtest/gtest.h>
#include <algorithm>
namespace stk::document_preview {
namespace {
io::Image fixture(int page, int scale = 1)
{
  io::Image image(320 * scale, 100 * scale);
  std::fill(image.pixels.begin(), image.pixels.end(), 255);
  for (int y = 12 * scale; y < 36 * scale; ++y) {
    for (int x = 0; x < 120 * scale; ++x) {
      auto *p = image.pixel(31 * scale + x, y);
      const auto &color = kEvidenceColors[page == 1 ? x / (20 * scale) : 5 - x / (20 * scale)];
      std::copy(color.begin(), color.end(), p);
    }
  }
  return image;
}
TEST(DocumentEvidence, PngRoundTripIdentifiesDistinctPagesAtBothDpiScales)
{
  for (const int scale : {1, 2}) {
    for (const int page : {1, 2}) {
      const auto png = io::encode_png(fixture(page, scale));
      const auto decoded = io::decode_png(png);
      EXPECT_TRUE(evidence_marker(decoded, page));
      EXPECT_FALSE(evidence_marker(decoded, 3 - page));
    }
  }
}
TEST(DocumentEvidence, BlackFlatAndScatteredColorsDoNotProveNativeContent)
{
  io::Image image(320, 100);
  EXPECT_FALSE(evidence_marker(image, 1));
  std::fill(image.pixels.begin(), image.pixels.end(), 255);
  EXPECT_FALSE(evidence_marker(image, 1));
  for (size_t i = 0; i < kEvidenceColors.size(); ++i) {
    for (int y = 10; y < 34; ++y) for (int x = 0; x < 20; ++x) {
      std::copy(kEvidenceColors[i].begin(), kEvidenceColors[i].end(), image.pixel(40 * i + x, y));
    }
  }
  EXPECT_FALSE(evidence_marker(image, 1));
  EXPECT_FALSE(evidence_marker(image, 2));
}
TEST(DocumentEvidence, CroppedIncompleteStripeAndInvalidBufferFailClosed)
{
  auto image = fixture(1);
  for (uint32_t y = 15; y < image.height; ++y) {
    std::fill_n(image.row(y), image.stride(), 0);
  }
  EXPECT_FALSE(evidence_marker(image, 1));
  image = fixture(1);
  image.pixels.pop_back();
  EXPECT_FALSE(evidence_marker(image, 1));
  image.width = 0xffffffffu;
  EXPECT_FALSE(evidence_marker(image, 1));
}
}  // namespace
}  // namespace stk::document_preview
