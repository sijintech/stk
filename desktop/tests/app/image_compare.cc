/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * stk-viewer-image-compare: image metrics of the viewer tests (the same SSIM and chroma-mask IoU
 * as desktop/tests/viewer).
 *
 *   stk-viewer-image-compare IMAGE REFERENCE [--ssim-min S] [--iou-min I] [--update]
 *
 * Prints "ssim=<s> iou=<i>" and fails (exit 1) when a given minimum is not met. --update copies
 * IMAGE over REFERENCE (golden refresh). Exit 2: usage or unreadable images.
 */

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

#include "stk/gfx/image.hh"

namespace {

std::vector<double> luma(const stk::gfx::Image &img)
{
  std::vector<double> y(size_t(img.width) * img.height);
  for (size_t i = 0; i < y.size(); i++) {
    const uint8_t *p = &img.rgba[i * 4];
    y[i] = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2];
  }
  return y;
}

/** Structural similarity of the luma (8x8 windows, stride 4). */
double ssim(const stk::gfx::Image &a, const stk::gfx::Image &b)
{
  if (a.width != b.width || a.height != b.height || a.width < 8 || a.height < 8) {
    return 0.0;
  }
  const std::vector<double> ya = luma(a), yb = luma(b);
  constexpr int win = 8, stride = 4;
  constexpr double c1 = (0.01 * 255) * (0.01 * 255), c2 = (0.03 * 255) * (0.03 * 255);
  double total = 0;
  int n = 0;
  for (int y0 = 0; y0 + win <= a.height; y0 += stride) {
    for (int x0 = 0; x0 + win <= a.width; x0 += stride) {
      double ma = 0, mb = 0;
      for (int y = y0; y < y0 + win; y++) {
        for (int x = x0; x < x0 + win; x++) {
          ma += ya[size_t(y) * a.width + x];
          mb += yb[size_t(y) * a.width + x];
        }
      }
      ma /= win * win;
      mb /= win * win;
      double va = 0, vb = 0, cov = 0;
      for (int y = y0; y < y0 + win; y++) {
        for (int x = x0; x < x0 + win; x++) {
          const double da = ya[size_t(y) * a.width + x] - ma, db = yb[size_t(y) * a.width + x] - mb;
          va += da * da;
          vb += db * db;
          cov += da * db;
        }
      }
      va /= win * win - 1;
      vb /= win * win - 1;
      cov /= win * win - 1;
      total += ((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2));
      n++;
    }
  }
  return n ? total / n : 0.0;
}

/** Pixels that are clearly coloured (chroma max - min > 40): the domain surfaces. */
std::vector<uint8_t> chroma_mask(const stk::gfx::Image &img)
{
  std::vector<uint8_t> m(size_t(img.width) * img.height);
  for (size_t i = 0; i < m.size(); i++) {
    const uint8_t *p = &img.rgba[i * 4];
    const int hi = std::max({p[0], p[1], p[2]}), lo = std::min({p[0], p[1], p[2]});
    m[i] = hi - lo > 40 ? 1 : 0;
  }
  return m;
}

double iou(const std::vector<uint8_t> &a, const std::vector<uint8_t> &b)
{
  size_t inter = 0, uni = 0;
  for (size_t i = 0; i < std::min(a.size(), b.size()); i++) {
    inter += (a[i] && b[i]) ? 1 : 0;
    uni += (a[i] || b[i]) ? 1 : 0;
  }
  return uni ? double(inter) / double(uni) : 1.0;
}

}  // namespace

int main(int argc, char **argv)
{
  std::vector<std::string> files;
  double ssim_min = -1, iou_min = -1;
  bool update = false;
  for (int i = 1; i < argc; i++) {
    if (!std::strcmp(argv[i], "--ssim-min") && i + 1 < argc) {
      ssim_min = std::atof(argv[++i]);
    }
    else if (!std::strcmp(argv[i], "--iou-min") && i + 1 < argc) {
      iou_min = std::atof(argv[++i]);
    }
    else if (!std::strcmp(argv[i], "--update")) {
      update = true;
    }
    else {
      files.emplace_back(argv[i]);
    }
  }
  if (files.size() != 2) {
    std::fprintf(stderr, "usage: %s IMAGE REFERENCE [--ssim-min S] [--iou-min I] [--update]\n", argv[0]);
    return 2;
  }
  if (update) {
    std::error_code ec;
    std::filesystem::create_directories(std::filesystem::path(files[1]).parent_path(), ec);
    std::filesystem::copy_file(files[0], files[1], std::filesystem::copy_options::overwrite_existing, ec);
    std::printf("updated %s%s\n", files[1].c_str(), ec ? (" FAILED: " + ec.message()).c_str() : "");
    return ec ? 1 : 0;
  }
  stk::gfx::Image a, b;
  std::string err;
  if (!stk::gfx::png_read(files[0], a, err) || !stk::gfx::png_read(files[1], b, err)) {
    std::fprintf(stderr, "cannot read: %s\n", err.c_str());
    return 2;
  }
  if (a.width != b.width || a.height != b.height) {
    std::printf("size differs: %dx%d vs %dx%d\n", a.width, a.height, b.width, b.height);
    return 1;
  }
  const double s = ssim(a, b), m = iou(chroma_mask(a), chroma_mask(b));
  std::printf("ssim=%.4f iou=%.4f\n", s, m);
  bool ok = true;
  if (ssim_min >= 0 && s < ssim_min) {
    std::printf("SSIM %.4f below %.4f\n", s, ssim_min);
    ok = false;
  }
  if (iou_min >= 0 && m < iou_min) {
    std::printf("mask IoU %.4f below %.4f\n", m, iou_min);
    ok = false;
  }
  return ok ? 0 : 1;
}
