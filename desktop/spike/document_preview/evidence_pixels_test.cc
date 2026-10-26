/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "evidence_pixels.hh"
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <string_view>
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

// These literal text rows are deliberately independent of the recognizer's run
// table. '#' represents a full-block glyph, with optional per-glyph raster seams.
constexpr std::array<std::string_view, 3> kTextRows = {
    "##  ####  ###  #####", "#####  ##  ####  ###", "###  #####  ##  ####"};
io::Image text_fixture(const std::array<std::string_view, 3> &rows = kTextRows,
                       double cell = 8, bool dark = false, int seam = 0)
{
  const int scale = int(std::ceil(cell / 8));
  io::Image image(360 * scale, 150 * scale);
  const uint8_t back = dark ? 28 : 248, ink = dark ? 242 : 18;
  for (size_t i = 0; i < image.pixels.size(); i += 4) {
    std::fill_n(image.pixels.data() + i, 3, back);
    image.pixels[i + 3] = 255;
  }
  for (int row = 0; row < 3; ++row) {
    const int top = 20 + int(std::lround(row * 2.5 * cell));
    const int bottom = top + int(std::lround(1.75 * cell));
    for (size_t col = 0; col < rows[row].size(); ++col) {
      if (rows[row][col] != '#') { continue; }
      const int left = 31 + int(std::lround(col * cell));
      const int right = 31 + int(std::lround((col + 1) * cell));
      for (int y = top; y < bottom; ++y) for (int x = left; x < right; ++x) {
        auto *pixel = image.pixel(x, y);
        std::fill_n(pixel, 3, ink);
        // A softened final edge exercises non-binary rasterization without
        // claiming to simulate any particular browser/font implementation.
        if (seam && x >= right - seam) { std::fill_n(pixel, 3, 128); }
      }
    }
  }
  return image;
}

TEST(DocumentEvidence, TextPatternRoundTripsAtBothDpiScalesOnLightAndDarkPages)
{
  for (const double cell : {8.0, 16.0}) for (const bool dark : {false, true}) {
    const auto image = text_fixture(kTextRows, cell, dark);
    const auto decoded = io::decode_png(io::encode_png(image));
    EXPECT_TRUE(evidence_text_marker(decoded)) << "cell=" << cell << " dark=" << dark;
    EXPECT_FALSE(evidence_marker(decoded, 1));
    EXPECT_FALSE(evidence_marker(decoded, 2));
  }
}

TEST(DocumentEvidence, TextPatternAllowsFractionalCellsAndSmallRasterSeams)
{
  for (const double cell : {7.5, 10.0, 15.5, 16.0}) for (const bool dark : {false, true}) {
    EXPECT_TRUE(evidence_text_marker(text_fixture(kTextRows, cell, dark, 1)))
        << "cell=" << cell << " dark=" << dark;
    if (cell >= 15.5) {
      EXPECT_TRUE(evidence_text_marker(text_fixture(kTextRows, cell, dark, 2)))
          << "cell=" << cell << " dark=" << dark << " seam=2";
    }
  }
}

TEST(DocumentEvidence, ImageOnlyAndOpaqueFlatPagesDoNotProveBodyText)
{
  for (const int scale : {1, 2}) {
    EXPECT_FALSE(evidence_text_marker(fixture(1, scale)));
    EXPECT_FALSE(evidence_text_marker(fixture(2, scale)));
  }
  io::Image flat(360, 150);
  for (const uint8_t tone : {uint8_t(0), uint8_t(255), uint8_t(128)}) {
    for (size_t i = 0; i < flat.pixels.size(); i += 4) {
      std::fill_n(flat.pixels.data() + i, 3, tone);
      flat.pixels[i + 3] = 255;
    }
    EXPECT_FALSE(evidence_text_marker(flat));
  }
}

TEST(DocumentEvidence, ImageAndIndependentTextCanBeRequiredInTheSameViewport)
{
  io::Image combined(480, 240);
  std::fill(combined.pixels.begin(), combined.pixels.end(), 255);
  const auto stripe = fixture(1);
  const auto text = text_fixture();
  for (uint32_t y = 0; y < stripe.height; ++y) {
    std::copy_n(stripe.row(y), stripe.stride(), combined.row(y));
  }
  for (uint32_t y = 0; y < text.height; ++y) {
    std::copy_n(text.row(y), text.stride(), combined.row(y + 80));
  }
  EXPECT_TRUE(evidence_marker(combined, 1));
  EXPECT_TRUE(evidence_text_marker(combined));
  // The unchanged raster image alone must not satisfy the text predicate.
  for (uint32_t y = 80; y < combined.height; ++y) { std::fill_n(combined.row(y), combined.stride(), 255); }
  EXPECT_TRUE(evidence_marker(combined, 1));
  EXPECT_FALSE(evidence_text_marker(combined));
}

TEST(DocumentEvidence, TextPatternRequiresEveryRowInTheRightOrder)
{
  for (const bool dark : {false, true}) {
    for (int missing = 0; missing < 3; ++missing) {
      auto rows = kTextRows;
      rows[missing] = "                    ";
      EXPECT_FALSE(evidence_text_marker(text_fixture(rows, 8, dark))) << "missing=" << missing;
    }
    auto reversed = kTextRows;
    std::reverse(reversed.begin(), reversed.end());
    EXPECT_FALSE(evidence_text_marker(text_fixture(reversed, 8, dark)));
    const std::array<std::string_view, 3> repeated = {kTextRows[0], kTextRows[0], kTextRows[0]};
    EXPECT_FALSE(evidence_text_marker(text_fixture(repeated, 8, dark)));
  }
}

TEST(DocumentEvidence, TextPatternRejectsWrongRunWidthsAndSpaceWidths)
{
  auto wrong_run = kTextRows;
  wrong_run[1] = "####  ###  ####  ###";
  auto wrong_gap = kTextRows;
  wrong_gap[0] = "## ####   ###  #####";
  for (const double cell : {8.0, 16.0}) {
    EXPECT_FALSE(evidence_text_marker(text_fixture(wrong_run, cell)));
    EXPECT_FALSE(evidence_text_marker(text_fixture(wrong_gap, cell)));
  }
}

TEST(DocumentEvidence, TextPatternRequiresAlignedRowsAndConsistentLineSpacing)
{
  auto shifted = text_fixture();
  // Shift only the middle glyph row right by six pixels, retaining every glyph.
  for (int y = 40; y < 54; ++y) {
    auto *row = shifted.row(y);
    std::move_backward(row + 31 * 4, row + 191 * 4, row + 197 * 4);
    for (int x = 31; x < 37; ++x) { std::fill_n(shifted.pixel(x, y), 3, 248); }
  }
  EXPECT_FALSE(evidence_text_marker(shifted));
  auto spacing = text_fixture();
  // Move the last row down by five pixels; the first two rows stay unchanged.
  for (int y = 73; y >= 60; --y) {
    std::copy_n(spacing.row(y), spacing.stride(), spacing.row(y + 5));
  }
  for (int y = 60; y < 65; ++y) {
    for (uint32_t x = 0; x < spacing.width; ++x) { std::fill_n(spacing.pixel(x, y), 3, 248); }
  }
  EXPECT_FALSE(evidence_text_marker(spacing));
}

TEST(DocumentEvidence, NoiseAndToolbarLikeBarsCannotSubstituteForText)
{
  auto noise = text_fixture({"", "", ""});
  for (int y = 4; y < 140; y += 4) for (int x = 4; x < 350; x += 5) {
    std::fill_n(noise.pixel(x, y), 3, 18);
  }
  EXPECT_FALSE(evidence_text_marker(noise));
  const std::array<std::string_view, 3> toolbar = {
      "####  ####  ####  ####", "####  ####  ####  ####", "####  ####  ####  ####"};
  EXPECT_FALSE(evidence_text_marker(text_fixture(toolbar)));
  // Three correct horizontal scanlines do not establish three rendered lines.
  auto thin = text_fixture();
  for (int row = 0; row < 3; ++row) for (int y = 21 + row * 20; y < 34 + row * 20; ++y) {
    for (uint32_t x = 0; x < thin.width; ++x) { std::fill_n(thin.pixel(x, y), 3, 248); }
  }
  EXPECT_FALSE(evidence_text_marker(thin));
}

TEST(DocumentEvidence, TextPatternRequiresOpaqueNeutralHighContrastPixels)
{
  auto transparent = text_fixture();
  for (size_t i = 3; i < transparent.pixels.size(); i += 4) { transparent.pixels[i] = 0; }
  EXPECT_FALSE(evidence_text_marker(transparent));
  auto low_contrast = text_fixture();
  auto colored = text_fixture();
  for (size_t i = 0; i < low_contrast.pixels.size(); i += 4) {
    if (low_contrast.pixels[i] == 18) {
      std::fill_n(low_contrast.pixels.data() + i, 3, 160);
      colored.pixels[i + 1] = 160;
    }
  }
  EXPECT_FALSE(evidence_text_marker(low_contrast));
  EXPECT_FALSE(evidence_text_marker(colored));
}

TEST(DocumentEvidence, TextPatternFailsClosedForClippedRowsAndMalformedBuffers)
{
  auto image = text_fixture();
  image.height = 70;  // Third line is only partly present, with no bottom background.
  image.pixels.resize(image.stride() * image.height);
  EXPECT_FALSE(evidence_text_marker(image));
  image = text_fixture();
  image.pixels.pop_back();
  EXPECT_FALSE(evidence_text_marker(image));
  image = text_fixture();
  image.channels = 3;
  EXPECT_FALSE(evidence_text_marker(image));
  image = text_fixture();
  image.width = 0xffffffffu;
  EXPECT_FALSE(evidence_text_marker(image));
  EXPECT_FALSE(evidence_text_marker(io::Image{}));
}
}  // namespace
}  // namespace stk::document_preview
