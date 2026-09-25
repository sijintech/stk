/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Tolerant PNG golden comparison for the application screen exports (drivers differ in
 * anti-aliasing and glyph rasterization):
 *   stk-png-diff IMAGE GOLDEN [--tol 48] [--max-frac 0.02] [--update]
 * Fails when the sizes differ or more than `max-frac` of the pixels differ by more than `tol` in
 * any channel. --update copies IMAGE over GOLDEN instead.
 */

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "stk/gfx/image.hh"

int main(int argc, char **argv)
{
  std::string image, golden;
  int tol = 48;
  double max_frac = 0.02;
  bool update = false;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--tol") && i + 1 < argc) {
      tol = atoi(argv[++i]);
    }
    else if (!strcmp(argv[i], "--max-frac") && i + 1 < argc) {
      max_frac = atof(argv[++i]);
    }
    else if (!strcmp(argv[i], "--update")) {
      update = true;
    }
    else if (image.empty()) {
      image = argv[i];
    }
    else if (golden.empty()) {
      golden = argv[i];
    }
    else {
      fprintf(stderr, "usage: %s IMAGE GOLDEN [--tol N] [--max-frac F] [--update]\n", argv[0]);
      return 2;
    }
  }
  if (image.empty() || golden.empty()) {
    fprintf(stderr, "usage: %s IMAGE GOLDEN [--tol N] [--max-frac F] [--update]\n", argv[0]);
    return 2;
  }
  stk::gfx::Image a, b;
  std::string err;
  if (!stk::gfx::png_read(image, a, err)) {
    fprintf(stderr, "stk-png-diff: %s: %s\n", image.c_str(), err.c_str());
    return 1;
  }
  if (update) {
    if (!stk::gfx::png_write(golden, a)) {
      fprintf(stderr, "stk-png-diff: cannot write %s\n", golden.c_str());
      return 1;
    }
    printf("updated %s\n", golden.c_str());
    return 0;
  }
  if (!stk::gfx::png_read(golden, b, err)) {
    fprintf(stderr, "stk-png-diff: %s: %s\n", golden.c_str(), err.c_str());
    return 1;
  }
  if (a.width != b.width || a.height != b.height) {
    fprintf(stderr, "stk-png-diff: size %dx%d differs from the golden %dx%d\n", a.width, a.height, b.width, b.height);
    return 1;
  }
  long bad = 0;
  for (size_t i = 0; i + 3 < a.rgba.size(); i += 4) {
    int d = 0;
    for (int c = 0; c < 3; c++) {
      d = std::max(d, std::abs(int(a.rgba[i + c]) - int(b.rgba[i + c])));
    }
    bad += d > tol;
  }
  const double frac = double(bad) / (double(a.width) * a.height);
  printf("stk-png-diff: %ld / %d pixels differ by > %d (%.3f%%, limit %.3f%%)\n", bad, a.width * a.height, tol,
         frac * 100.0, max_frac * 100.0);
  if (frac > max_frac) {
    fprintf(stderr, "stk-png-diff: FAILED against %s\n", golden.c_str());
    return 1;
  }
  printf("PASS\n");
  return 0;
}
