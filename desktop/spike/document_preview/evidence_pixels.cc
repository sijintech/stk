/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "evidence_pixels.hh"
#include <algorithm>
#include <cstdlib>

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
  uint32_t prior_x = 0, prior_width = 0;
  int rows = 0;
  for (uint32_t y = 0; y < image.height; ++y) {
    bool found = false;
    for (uint32_t x = 0; x < image.width;) {
      if (color(x, y) != 0) { ++x; continue; }
      const uint32_t start = x;
      uint32_t min_width = UINT32_MAX, max_width = 0;
      int n = 0;
      for (; n < 6; ++n) {
        const uint32_t begin = x;
        while (x < image.width && color(x, y) == n) { ++x; }
        const uint32_t width = x - begin;
        if (width < 8 || width > 160) { break; }
        min_width = std::min(min_width, width);
        max_width = std::max(max_width, width);
      }
      if (n == 6 && max_width - min_width <= 2) {
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
}  // namespace stk::document_preview
