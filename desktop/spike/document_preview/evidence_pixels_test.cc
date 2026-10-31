/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "evidence_pixels.hh"
#include "window_capture_geometry.hh"
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
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

// Independent literal RGB values and rational mixtures model raster resampling;
// these helpers neither use the recognizer's palette nor its classification rule.
constexpr std::array<std::array<uint8_t, 3>, 6> kRasterColors = {{
    {26, 78, 210}, {230, 118, 24}, {30, 174, 74},
    {154, 42, 190}, {24, 186, 202}, {218, 38, 58}}};
struct RasterStripe {
  io::Image image;
  std::array<int, 6> starts{}, widths{};
  std::array<int, 5> edges{}, seams{};
  int top = 12, height;
};
RasterStripe raster_stripe(int page, std::array<int, 6> widths,
                           std::array<int, 5> seams, int height = 13)
{
  int total = 0;
  for (const auto width : widths) { total += width; }
  for (const auto seam : seams) { total += seam; }
  RasterStripe result{io::Image(uint32_t(total + 83), 80), {}, widths, {}, seams, 12, height};
  std::fill(result.image.pixels.begin(), result.image.pixels.end(), 255);
  int x = 31;
  for (int i = 0; i < 6; ++i) {
    result.starts[i] = x;
    const auto &from = kRasterColors[page == 1 ? i : 5 - i];
    for (int y = result.top; y < result.top + height; ++y) for (int dx = 0; dx < widths[i]; ++dx) {
      std::copy(from.begin(), from.end(), result.image.pixel(x + dx, y));
    }
    x += widths[i];
    if (i == 5) { continue; }
    result.edges[i] = x;
    const auto &to = kRasterColors[page == 1 ? i + 1 : 4 - i];
    for (int j = 1; j <= seams[i]; ++j) {
      for (int y = result.top; y < result.top + height; ++y) {
        auto *pixel = result.image.pixel(x, y);
        for (int c = 0; c < 3; ++c) {
          // Fixed 1/2 or 1/3,2/3 samples, rounded once to 8-bit pixels.
          pixel[c] = uint8_t(std::lround((from[c] * (seams[i] + 1 - j) + to[c] * j) /
                                       double(seams[i] + 1)));
        }
      }
      ++x;
    }
  }
  return result;
}
void paint_stripe_columns(RasterStripe &stripe, int left, int width,
                          std::array<uint8_t, 4> color)
{
  for (int y = stripe.top; y < stripe.top + stripe.height; ++y) for (int x = left; x < left + width; ++x) {
    std::copy(color.begin(), color.end(), stripe.image.pixel(x, y));
  }
}

TEST(DocumentEvidence, ScaledRasterAllowsOnlyNarrowAdjacentColorMixturesAtDifferentSizes)
{
  for (const int cell : {12, 20, 32}) for (const int height : {8, 13, 24}) for (const int page : {1, 2}) {
    // Nonuniform solid interiors reproduce 1..2px PDF raster transitions, rather
    // than relying on one screenshot's coordinates, size or page identity.
    const auto stripe = raster_stripe(page, {cell, cell - 2, cell - 2, cell - 2, cell - 3, cell - 1},
                                      {1, 1, 1, 2, 2}, height);
    const auto decoded = io::decode_png(io::encode_png(stripe.image));
    EXPECT_TRUE(evidence_marker(decoded, page)) << "cell=" << cell << " height=" << height << " page=" << page;
    EXPECT_FALSE(evidence_marker(decoded, 3 - page));
    for (const int seam : {1, 2}) {
      const auto uniform = raster_stripe(page, {cell, cell, cell, cell, cell, cell},
                                        {seam, seam, seam, seam, seam}, height);
      EXPECT_TRUE(evidence_marker(uniform.image, page)) << "seam=" << seam << " page=" << page;
      EXPECT_FALSE(evidence_marker(uniform.image, 3 - page));
    }
  }
}

TEST(DocumentEvidence, ScaledRasterRejectsWrongOrderMissingColorsAndThirdColorTransitions)
{
  for (const int page : {1, 2}) {
    const auto original = raster_stripe(page, {20, 18, 18, 18, 17, 19}, {1, 1, 1, 2, 2});
    auto swapped = original;
    const auto &a = kRasterColors[page == 1 ? 1 : 4];
    const auto &b = kRasterColors[page == 1 ? 2 : 3];
    paint_stripe_columns(swapped, swapped.starts[1], swapped.widths[1], {b[0], b[1], b[2], 255});
    paint_stripe_columns(swapped, swapped.starts[2], swapped.widths[2], {a[0], a[1], a[2], 255});
    EXPECT_FALSE(evidence_marker(swapped.image, page));
    for (int missing = 0; missing < 6; ++missing) {
      auto incomplete = original;
      paint_stripe_columns(incomplete, incomplete.starts[missing], incomplete.widths[missing], {255, 255, 255, 255});
      EXPECT_FALSE(evidence_marker(incomplete.image, page)) << "missing=" << missing << " page=" << page;
    }
    for (const auto invalid : {std::array<uint8_t, 4>{255, 0, 255, 255},
                              std::array<uint8_t, 4>{255, 255, 255, 255},
                              std::array<uint8_t, 4>{128, 128, 128, 255},
                              std::array<uint8_t, 4>{230, 118, 24, 239}}) {
      for (int edge = 0; edge < 5; ++edge) {
        auto bad = original;
        paint_stripe_columns(bad, bad.edges[edge], bad.seams[edge], invalid);
        EXPECT_FALSE(evidence_marker(bad.image, page)) << "edge=" << edge << " page=" << page;
      }
    }
  }
}

TEST(DocumentEvidence, ScaledRasterRejectsReversedAndOffSegmentTransitionPixels)
{
  for (const int page : {1, 2}) {
    const auto original = raster_stripe(page, {20, 20, 20, 20, 20, 20}, {2, 2, 2, 2, 2});
    for (int edge = 0; edge < 5; ++edge) {
      auto reversed = original;
      for (int y = reversed.top; y < reversed.top + reversed.height; ++y) {
        auto *left = reversed.image.pixel(reversed.edges[edge], y);
        auto *right = reversed.image.pixel(reversed.edges[edge] + 1, y);
        for (int c = 0; c < 4; ++c) { std::swap(left[c], right[c]); }
      }
      EXPECT_FALSE(evidence_marker(reversed.image, page)) << "edge=" << edge << " page=" << page;
    }
    auto off_segment = original;
    // A pixel near the first pair's midpoint is still invalid if its blue
    // channel cannot come from either adjacent color's shared blend fraction.
    paint_stripe_columns(off_segment, off_segment.edges[0], 2, {128, 98, 124, 255});
    EXPECT_FALSE(evidence_marker(off_segment.image, page));
  }
}

TEST(DocumentEvidence, ScaledRasterRejectsWideGapsDistortedWidthsAndIncompleteHeight)
{
  for (const int page : {1, 2}) {
    for (int edge = 0; edge < 5; ++edge) {
      std::array<int, 5> seams = {1, 1, 1, 1, 1};
      seams[edge] = 3;
      EXPECT_FALSE(evidence_marker(raster_stripe(page, {20, 20, 20, 20, 20, 20}, seams).image, page))
          << "edge=" << edge << " page=" << page;
    }
    EXPECT_FALSE(evidence_marker(raster_stripe(page, {20, 20, 27, 20, 20, 20}, {1, 1, 1, 2, 2}).image, page));
    EXPECT_FALSE(evidence_marker(raster_stripe(page, {20, 20, 7, 20, 20, 20}, {1, 1, 1, 2, 2}).image, page));
    EXPECT_FALSE(evidence_marker(raster_stripe(page, {160, 160, 160, 160, 160, 160}, {2, 2, 2, 2, 2}).image, page));
    EXPECT_FALSE(evidence_marker(raster_stripe(page, {20, 18, 18, 18, 17, 19}, {1, 1, 1, 2, 2}, 7).image, page));
  }
}

TEST(DocumentEvidence, ScaledRasterRejectsClippedAndBackgroundLikeStripes)
{
  for (const int page : {1, 2}) {
    const auto original = raster_stripe(page, {20, 18, 18, 18, 17, 19}, {1, 1, 1, 2, 2});
    // Retain only seven solid pixels from the last color; all earlier colors
    // and every permitted transition are still present.
    io::Image clipped(uint32_t(original.starts[5] + 7), original.image.height);
    for (uint32_t y = 0; y < clipped.height; ++y) {
      std::copy_n(original.image.row(y), clipped.stride(), clipped.row(y));
    }
    EXPECT_FALSE(evidence_marker(clipped, page));
    auto pale = original;
    for (size_t i = 0; i < pale.image.pixels.size(); i += 4) for (int c = 0; c < 3; ++c) {
      pale.image.pixels[i + c] = uint8_t((3 * pale.image.pixels[i + c] + 255) / 4);
    }
    EXPECT_FALSE(evidence_marker(pale.image, page));
    auto transparent = original;
    for (size_t i = 3; i < transparent.image.pixels.size(); i += 4) { transparent.image.pixels[i] = 239; }
    EXPECT_FALSE(evidence_marker(transparent.image, page));
  }
}

TEST(DocumentEvidence, CapturedMacPdfFirstPageKeepsItsIdentityInsideTheNativeViewport)
{
  // Public synthetic OS capture from Desktop run 40472799346, head 3ac89623.
  // This replays pixels; it does not claim a new OS/browser execution.
  const auto image = io::read_png(std::filesystem::path(STK_DOCUMENT_FIXTURE_DIR) / "macos-pdf-scaled-boundaries.png");
  ASSERT_EQ(image.width, 1024u); ASSERT_EQ(image.height, 653u);
  io::Image viewport(385, 256), outside = image;
  for (uint32_t y = 0; y < viewport.height; ++y) for (uint32_t x = 0; x < viewport.width; ++x) {
    std::copy_n(image.pixel(631 + x, 200 + y), 4, viewport.pixel(x, y));
    std::fill_n(outside.pixel(631 + x, 200 + y), 4, 255);
  }
  EXPECT_TRUE(evidence_marker(viewport, 1));
  EXPECT_FALSE(evidence_marker(viewport, 2));
  EXPECT_FALSE(evidence_marker(outside, 1));
  EXPECT_FALSE(evidence_marker(outside, 2));
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

TEST(DocumentEvidence, WindowCaptureGeometryUsesTheObservedFullWindowOriginWithoutBorderTolerance)
{
  using namespace capture_geometry;
  // Exact cfb8c561 Windows WGC failure: the surface matches GetWindowRect,
  // which includes invisible resize borders, rather than DWM visible bounds.
  const Rect window{-8, 0, 1032, 736}, dwm{-1, 0, 1025, 729}, client{0, 31, 1024, 728};
  const auto full = select(1040, 736, window, dwm, client, true);
  ASSERT_TRUE(full);
  EXPECT_EQ(full->origin, Origin::FullWindowRect);
  EXPECT_EQ(full->left, 8u); EXPECT_EQ(full->top, 31u);
  EXPECT_EQ(full->right, 1032u); EXPECT_EQ(full->bottom, 728u);
  EXPECT_EQ(full->right - full->left, 1024u);
  EXPECT_EQ(full->bottom - full->top, 697u);
  const auto visible = select(1026, 729, window, dwm, client, true);
  ASSERT_TRUE(visible);
  EXPECT_EQ(visible->origin, Origin::DwmVisibleBounds);
  EXPECT_EQ(visible->left, 1u); EXPECT_EQ(visible->top, 31u);
  EXPECT_EQ(visible->right - visible->left, 1024u);
  EXPECT_FALSE(select(1041, 736, window, dwm, client, true));
  EXPECT_FALSE(select(1040, 735, window, dwm, client, true));
  EXPECT_FALSE(select(1027, 729, window, dwm, client, true));
  EXPECT_FALSE(select(1026, 730, window, dwm, client, true));
}

TEST(DocumentEvidence, WindowCaptureGeometryRequiresPhysicalDpiAndNestedPositiveRectangles)
{
  using namespace capture_geometry;
  const Rect window{-8, 0, 1032, 736}, dwm{-1, 0, 1025, 729}, client{0, 31, 1024, 728};
  EXPECT_FALSE(select(1040, 736, window, dwm, client, false));
  EXPECT_FALSE(select(1026, 729, window, dwm, client, false));
  EXPECT_FALSE(select(1040, 736, window, dwm, {-2, 31, 1024, 728}, true));
  EXPECT_FALSE(select(1040, 736, window, dwm, {0, 31, 1026, 728}, true));
  EXPECT_FALSE(select(1040, 736, window, {-9, 0, 1025, 729}, client, true));
  EXPECT_FALSE(select(1040, 736, window, {-1, 0, 1033, 729}, client, true));
  EXPECT_FALSE(select(1040, 736, window, dwm, {0, 31, 0, 728}, true));
  EXPECT_FALSE(select(1040, 736, window, dwm, {0, 31, 1024, 30}, true));
}

TEST(DocumentEvidence, WindowCaptureGeometryPreservesPhysicalPixelsAtScaledAndNegativeDesktopOrigins)
{
  using namespace capture_geometry;
  const auto scaled = select(2080, 1472, {-16, 0, 2064, 1472}, {-2, 0, 2050, 1458},
                             {0, 62, 2048, 1456}, true);
  ASSERT_TRUE(scaled);
  EXPECT_EQ(scaled->left, 16u); EXPECT_EQ(scaled->top, 62u);
  EXPECT_EQ(scaled->right - scaled->left, 2048u);
  EXPECT_EQ(scaled->bottom - scaled->top, 1394u);
  const auto negative = select(1040, 736, {-2048, -1000, -1008, -264},
      {-2041, -1000, -1015, -271}, {-2040, -969, -1016, -272}, true);
  ASSERT_TRUE(negative);
  EXPECT_EQ(negative->left, 8u); EXPECT_EQ(negative->top, 31u);
  EXPECT_EQ(negative->right - negative->left, 1024u);
}

TEST(DocumentEvidence, WindowCaptureGeometryKeepsExtentAndPixelBudgetsWithoutSignedOverflow)
{
  using namespace capture_geometry;
  EXPECT_TRUE(select(8192, 2048, {0, 0, 8192, 2048}, {0, 0, 8192, 2048}, {0, 0, 8192, 2048}, true));
  EXPECT_FALSE(select(8192, 2049, {0, 0, 8192, 2049}, {0, 0, 8192, 2049}, {0, 0, 8192, 2049}, true));
  EXPECT_FALSE(select(8193, 10, {0, 0, 8193, 10}, {0, 0, 8193, 10}, {0, 0, 8193, 10}, true));
  EXPECT_FALSE(select(0, 10, {0, 0, 1, 10}, {0, 0, 1, 10}, {0, 0, 1, 10}, true));
  EXPECT_FALSE(select(-1, 10, {0, 0, 1, 10}, {0, 0, 1, 10}, {0, 0, 1, 10}, true));
  EXPECT_FALSE(select(1040, 736, {INT32_MIN, INT32_MIN, INT32_MAX, INT32_MAX},
      {INT32_MIN, INT32_MIN, INT32_MAX, INT32_MAX}, {0, 0, 1, 1}, true));
}

TEST(DocumentEvidence, WindowCaptureContentUsesTheExactSmallerValidExtentWithoutPadding)
{
  using namespace capture_geometry;
  // Observed 38a9fd43 WGC frame: pool/item/texture match WindowRect, while
  // ContentSize matches DWM. This proves crop arithmetic, not OS pixel origin.
  const Rect window{-8, 0, 1032, 736}, dwm{-1, 0, 1025, 729}, client{0, 31, 1024, 728};
  const auto frame = select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 736,
                                  window, dwm, client, true);
  ASSERT_TRUE(frame);
  EXPECT_EQ(frame->pool.origin, Origin::FullWindowRect);
  EXPECT_EQ(frame->content.origin, Origin::DwmVisibleBounds);
  EXPECT_EQ(frame->content.left, 1u); EXPECT_EQ(frame->content.top, 31u);
  EXPECT_EQ(frame->content.right, 1025u); EXPECT_EQ(frame->content.bottom, 728u);
  EXPECT_EQ(frame->content.right - frame->content.left, 1024u);
  EXPECT_EQ(frame->content.bottom - frame->content.top, 697u);
  EXPECT_GT(frame->pool.right, 1026u);  // Allocation crop crosses valid content.
  EXPECT_LE(frame->content.right, 1026u); EXPECT_LE(frame->content.bottom, 729u);
  const auto full = select_frame(1040, 736, 1040, 736, 1040, 736, 1040, 736,
                                 window, dwm, client, true);
  ASSERT_TRUE(full);
  EXPECT_EQ(full->content.origin, Origin::FullWindowRect);
}

TEST(DocumentEvidence, WindowCaptureContentRejectsUnmatchedClippedAndUnstableExtents)
{
  using namespace capture_geometry;
  const Rect window{-8, 0, 1032, 736}, dwm{-1, 0, 1025, 729}, client{0, 31, 1024, 728};
  EXPECT_FALSE(select_frame(1027, 729, 1040, 736, 1040, 736, 1040, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1026, 730, 1040, 736, 1040, 736, 1040, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(0, 729, 1040, 736, 1040, 736, 1040, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(-1, 729, 1040, 736, 1040, 736, 1040, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1026, 729, 1026, 729, 1040, 736, 1040, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1040, 736, 1026, 729, 1026, 729, 1026, 729, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1026, 729, 1040, 736, 1040, 736, 1025, 736, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 728, window, dwm, client, true));
  EXPECT_FALSE(select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 736, window, dwm, client, false));
  EXPECT_FALSE(select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 736,
                            window, dwm, {-2, 31, 1024, 728}, true));
  EXPECT_FALSE(select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 736,
                            {-8, 0, 1024, 736}, dwm, client, true));
}

TEST(DocumentEvidence, WindowCaptureContentKeepsPhysicalNegativeOriginsAndAllocationBudgets)
{
  using namespace capture_geometry;
  const auto negative = select_frame(1026, 729, 1040, 736, 1040, 736, 1040, 736,
      {-2048, -1000, -1008, -264}, {-2041, -1000, -1015, -271}, {-2040, -969, -1016, -272}, true);
  ASSERT_TRUE(negative);
  EXPECT_EQ(negative->content.left, 1u); EXPECT_EQ(negative->content.top, 31u);
  EXPECT_EQ(negative->content.right - negative->content.left, 1024u);
  const auto scaled = select_frame(2052, 1458, 2080, 1472, 2080, 1472, 2080, 1472,
      {-16, 0, 2064, 1472}, {-2, 0, 2050, 1458}, {0, 62, 2048, 1456}, true);
  ASSERT_TRUE(scaled);
  EXPECT_EQ(scaled->content.left, 2u); EXPECT_EQ(scaled->content.top, 62u);
  EXPECT_EQ(scaled->content.right - scaled->content.left, 2048u);
  const Rect small{0, 0, 10, 10};
  EXPECT_TRUE(select_frame(10, 10, 10, 10, 10, 10, 8192, 2048, small, small, small, true));
  EXPECT_FALSE(select_frame(10, 10, 10, 10, 10, 10, 8192, 2049, small, small, small, true));
  EXPECT_FALSE(select_frame(10, 10, 10, 10, 10, 10, 8193, 10, small, small, small, true));
  EXPECT_FALSE(select_frame(10, 10, 10, 10, 10, 10, UINT32_MAX, UINT32_MAX, small, small, small, true));
  EXPECT_FALSE(select_frame(INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX,
      INT32_MAX, INT32_MAX, UINT32_MAX, UINT32_MAX,
      {INT32_MIN, INT32_MIN, INT32_MAX, INT32_MAX}, small, small, true));
}
}  // namespace
}  // namespace stk::document_preview
