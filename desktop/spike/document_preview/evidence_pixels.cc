/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "evidence_pixels.hh"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <vector>

namespace stk::document_preview {
bool evidence_marker(const io::Image &image, int page)
{
  if ((page != 1 && page != 2) || image.channels != 4 || !image.width || !image.height ||
      image.width > 8192 || image.height > 8192 ||
      uint64_t(image.width) * image.height > 16 * 1024 * 1024 ||
      image.pixels.size() != size_t(image.width) * image.height * 4) { return false; }
  const auto color = [&](uint32_t x, uint32_t y) {
    const auto *p = image.pixel(x, y);
    if (p[3] < 240) { return -1; }
    for (int i = 0; i < 6; ++i) {
      const auto &c = kEvidenceColors[i];
      if (std::abs(int(p[0]) - c[0]) <= 20 && std::abs(int(p[1]) - c[1]) <= 20 &&
          std::abs(int(p[2]) - c[2]) <= 20) { return page == 1 ? i : 5 - i; }
    }
    return -1;
  };
  // PDF raster scaling can mix the two adjacent stripe colors across one or
  // two pixels, even for a single image with /Interpolate false. Admit only an
  // opaque mixture on that exact RGB segment; a background gap or third color
  // must not join otherwise unrelated color runs.
  const auto transition = [&](uint32_t x, uint32_t y, int before, double &blend) {
    const auto *p = image.pixel(x, y);
    if (p[3] < 240) { return false; }
    const auto &from = kEvidenceColors[page == 1 ? before : 5 - before];
    const auto &to = kEvidenceColors[page == 1 ? before + 1 : 4 - before];
    double numerator = 0, denominator = 0;
    for (int c = 0; c < 3; ++c) {
      const int delta = int(to[c]) - from[c];
      numerator += (int(p[c]) - from[c]) * delta;
      denominator += delta * delta;
    }
    blend = numerator / denominator;
    if (blend <= 0 || blend >= 1) { return false; }
    for (int c = 0; c < 3; ++c) {
      if (std::abs(p[c] - (from[c] + blend * (int(to[c]) - from[c]))) > 2) { return false; }
    }
    return true;
  };
  uint32_t prior_x = 0, prior_width = 0;
  int rows = 0;
  for (uint32_t y = 0; y < image.height; ++y) {
    bool found = false;
    for (uint32_t x = 0; x < image.width;) {
      if (color(x, y) != 0) { ++x; continue; }
      const uint32_t start = x;
      std::array<uint32_t, 6> solid_widths{};
      std::array<uint32_t, 5> transition_widths{};
      int n = 0;
      for (; n < 6; ++n) {
        const uint32_t begin = x;
        while (x < image.width && color(x, y) == n) { ++x; }
        const uint32_t width = x - begin;
        if (width < 8 || width > 160) { break; }
        solid_widths[n] = width;
        if (n < 5) {
          const uint32_t edge = x;
          double previous_blend = 0;
          while (x < image.width && color(x, y) == -1 && x - edge < 2) {
            double blend = 0;
            if (!transition(x, y, n, blend) || blend + .02 < previous_blend) { break; }
            previous_blend = blend;
            ++x;
          }
          transition_widths[n] = x - edge;
          if (x == image.width || color(x, y) != n + 1) { break; }
        }
      }
      // Split each admitted transition evenly between its neighbours. In half
      // pixels this retains the original 8..160px widths and <=2px difference,
      // without treating their mixed boundary as missing solid-color content.
      uint32_t min_width = UINT32_MAX, max_width = 0;
      if (n == 6) {
        for (size_t i = 0; i < solid_widths.size(); ++i) {
          const auto width = 2 * solid_widths[i] + (i ? transition_widths[i - 1] : 0) +
              (i + 1 < solid_widths.size() ? transition_widths[i] : 0);
          min_width = std::min(min_width, width);
          max_width = std::max(max_width, width);
        }
      }
      if (n == 6 && min_width >= 16 && max_width <= 320 && max_width - min_width <= 4) {
        const auto width = x - start;
        rows = rows && std::abs(int(start) - int(prior_x)) <= 1 &&
                               std::abs(int(width) - int(prior_width)) <= 2 ? rows + 1 : 1;
        prior_x = start;
        prior_width = width;
        if (rows >= 8) { return true; }
        found = true;
        break;
      }
      if (x == start) { ++x; }
    }
    if (!found) { rows = 0; }
  }
  return false;
}

namespace {
struct TextRun {
  int begin, end, ink;
};
struct TextBand {
  int row, tone, left, right, top, bottom;
  double cell;
};
constexpr std::array<std::array<int, 4>, 3> kTextRuns = {{
    {2, 4, 3, 5}, {5, 2, 4, 3}, {3, 5, 2, 4}}};

bool aligned(const TextBand &a, const TextBand &b)
{
  return a.tone == b.tone && std::abs(a.left - b.left) <= 2 &&
         std::abs(a.right - b.right) <= 2 && std::abs(a.cell - b.cell) <= .25;
}
bool full_height(const TextBand &band)
{
  const int height = band.bottom - band.top;
  return height >= std::max(6.0, .8 * band.cell) && height <= 3 * band.cell;
}
}  // namespace

bool evidence_text_marker(const io::Image &image)
{
  if (image.channels != 4 || !image.width || !image.height || image.width > 8192 ||
      image.height > 8192 || uint64_t(image.width) * image.height > 16 * 1024 * 1024 ||
      image.pixels.size() != size_t(image.width) * image.height * 4) { return false; }

  const int width = int(image.width), height = int(image.height);
  // Keep mid-tones and colored pixels out of both foreground and background.
  // Antialiasing may soften glyph edges; the solid block interiors must remain
  // opaque, neutral and at least 112 levels apart from the surrounding page.
  std::vector<int8_t> tones(size_t(width) * height);
  for (size_t i = 0; i < tones.size(); ++i) {
    const auto *p = image.pixels.data() + 4 * i;
    const int low = std::min({p[0], p[1], p[2]});
    const int high = std::max({p[0], p[1], p[2]});
    if (p[3] >= 240 && high - low <= 24) {
      tones[i] = high <= 72 ? -1 : low >= 184 ? 1 : 0;
    }
  }
  const auto background = [&](int left, int right, int y, int tone) {
    if (left < 0 || right > width || left >= right || y < 0 || y >= height) { return false; }
    int count = 0;
    for (int x = left; x < right; ++x) { count += tones[size_t(y) * width + x] == -tone; }
    return count * 10 >= (right - left) * 9;
  };

  std::vector<TextBand> bands;
  std::vector<size_t> prior, current;
  std::vector<TextRun> runs;
  for (int y = 0; y < height; ++y) {
    current.clear();
    for (const int tone : {-1, 1}) {
      runs.clear();
      const auto *line = tones.data() + size_t(y) * width;
      for (int x = 0; x < width;) {
        if (line[x] != tone) { ++x; continue; }
        const int begin = x;
        while (x < width && line[x] == tone) { ++x; }
        // A full-block glyph can have a one/two-pixel seam at fractional/DPI
        // boundaries. This cannot bridge the >=8px two-space separator.
        if (!runs.empty() && begin - runs.back().end <= 2) {
          runs.back().ink += x - begin;
          runs.back().end = x;
        }
        else { runs.push_back({begin, x, x - begin}); }
      }
      for (size_t i = 0; i + 4 <= runs.size(); ++i) {
        const double cell = (runs[i + 3].end - runs[i].begin) / 20.0;
        if (cell < 4 || cell > 40) { continue; }
        const double tolerance = std::max(2.5, .3 * cell);
        bool gaps_ok = true;
        for (int j = 0; j < 3; ++j) {
          const int end = runs[i + j].end, next = runs[i + j + 1].begin;
          const int trim = std::max(1, int(std::ceil(.2 * cell)));
          if (std::abs(next - end - 2 * cell) > tolerance ||
              !background(end + trim, next - trim, y, tone)) { gaps_ok = false; break; }
        }
        const int left = runs[i].begin, right = runs[i + 3].end;
        const int margin = int(std::ceil(cell));
        const int edge = std::max(2, int(std::ceil(.3 * cell)));
        if (!gaps_ok || !background(left - margin, left - edge, y, tone) ||
            !background(right + edge, right + margin, y, tone)) { continue; }
        for (int row = 0; row < 3; ++row) {
          bool widths_ok = true;
          for (int j = 0; j < 4; ++j) {
            const auto &run = runs[i + j];
            const int span = run.end - run.begin;
            if (std::abs(span - kTextRuns[row][j] * cell) > tolerance ||
                run.ink * 5 < span * 4) { widths_ok = false; break; }
          }
          if (!widths_ok) { continue; }
          TextBand candidate{row, tone, left, right, y, y + 1, cell};
          size_t index = bands.size();
          for (const size_t p : prior) {
            if (bands[p].row == row && bands[p].bottom == y && aligned(bands[p], candidate)) {
              index = p;
              bands[p].bottom = y + 1;
              break;
            }
          }
          if (index == bands.size()) {
            // Hostile/noisy screenshots cannot grow an unbounded candidate list.
            if (bands.size() >= 8192) { return false; }
            bands.push_back(candidate);
          }
          current.push_back(index);
        }
      }
    }
    prior.swap(current);
  }

  const auto follows = [&](const TextBand &a, const TextBand &b) {
    const int gap = b.top - a.bottom;
    return b.row == a.row + 1 && aligned(a, b) && full_height(b) && gap >= 1 &&
           gap <= 2 * a.cell &&
           std::abs((b.bottom - b.top) - (a.bottom - a.top)) <= std::max(2.0, .25 * a.cell) &&
           background(a.left, a.right, (a.bottom + b.top) / 2, a.tone);
  };
  // Bands are in increasing top-row order. Require a single three-line block,
  // not individually matching fragments at unrelated places in the viewport.
  for (size_t i = 0; i < bands.size(); ++i) {
    const auto &a = bands[i];
    if (a.row != 0 || !full_height(a) || !background(a.left, a.right, a.top - 2, a.tone)) { continue; }
    for (size_t j = i + 1; j < bands.size(); ++j) {
      const auto &b = bands[j];
      if (b.top > a.bottom + 2 * a.cell) { break; }
      if (!follows(a, b)) { continue; }
      for (size_t k = j + 1; k < bands.size(); ++k) {
        const auto &c = bands[k];
        if (c.top > b.bottom + 2 * b.cell) { break; }
        if (follows(b, c) &&
            std::abs((c.top - b.top) - (b.top - a.top)) <= std::max(2.0, .25 * a.cell) &&
            background(c.left, c.right, c.bottom + 1, c.tone)) { return true; }
      }
    }
  }
  return false;
}
}  // namespace stk::document_preview
