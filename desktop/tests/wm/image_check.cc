/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Checks headless exports of the sample frame (stk-desktop --headless):
 *
 * 1. Golden compare per scale, with a tolerance for rasterization differences between drivers
 *    (at most `--max-diff` of the pixels may differ by more than 40 in any channel).
 * 2. Structure: header, region and accent colors where sample_layout.hh puts them.
 * 3. CJK text crispness across scales. For every text row, the ink bounding box of "中文" and
 *    its edge sharpness are measured at each scale:
 *    - the glyph box height must scale linearly with the UI scale (text is laid out and
 *      rasterized at the target size, not a fixed size scaled up);
 *    - edge sharpness (mean of the steepest quarter of coverage steps between neighboring
 *      pixels) must stay close to the 1x value and be clearly higher than that of the 1x
 *      rendering upscaled bilinearly to the same scale: crisp text keeps ~1 px wide
 *      anti-aliased edges at every scale, an upscaled bitmap has edges `scale` pixels wide.
 *
 *   stk-wm-image-check [--golden-dir DIR] [--update-golden] [--max-diff F] SCALE=PNG...
 */

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "stk/gfx/image.hh"

#include "sample_layout.hh"

using stk::gfx::Image;
using namespace stk::app;

namespace {

int g_failures = 0;

void check(const bool ok, const std::string &what)
{
  printf("%s %s\n", ok ? "ok  " : "FAIL", what.c_str());
  if (!ok) {
    g_failures++;
  }
}

struct Input {
  float scale = 1.0f;
  std::string path;
  Image img;
};

std::string scale_tag(const float s)
{
  char buf[32];
  snprintf(buf, sizeof(buf), "%g", s);
  std::string t = buf;
  std::replace(t.begin(), t.end(), '.', '_');
  return t + "x";
}

bool near_color(const uint8_t *px, const float rgba[4], const int tol)
{
  for (int c = 0; c < 3; c++) {
    if (std::abs(int(px[c]) - int(std::lround(rgba[c] * 255.0f))) > tol) {
      return false;
    }
  }
  return true;
}

/** Text coverage of a pixel in [0, 1] (text color over the region background). */
float coverage(const uint8_t *px)
{
  const float bg = theme::kRegionBack[1] * 255.0f, fg = theme::kText[1] * 255.0f;
  const float lum = 0.25f * px[0] + 0.5f * px[1] + 0.25f * px[2];
  return std::clamp((lum - bg) / (fg - bg), 0.0f, 1.0f);
}

struct Ink {
  int xmin = 1 << 30, ymin = 1 << 30, xmax = -1, ymax = -1;
  int ink = 0, solid = 0, partial = 0;
  int height() const
  {
    return ymax >= ymin ? ymax - ymin + 1 : 0;
  }
  int width() const
  {
    return xmax >= xmin ? xmax - xmin + 1 : 0;
  }
  float edge_share() const
  {
    return ink ? float(partial) / float(ink) : 1.0f;
  }
};

/** Coverage grid of a box (bottom-left origin). */
struct Grid {
  int w = 0, h = 0;
  std::vector<float> c;
  float at(int x, int y) const
  {
    return c[size_t(y) * w + x];
  }
};

Grid crop(const Image &img, int x0, int y0, int x1, int y1)
{
  Grid g;
  x0 = std::max(0, x0);
  y0 = std::max(0, y0);
  x1 = std::min(img.width, x1);
  y1 = std::min(img.height, y1);
  g.w = std::max(0, x1 - x0);
  g.h = std::max(0, y1 - y0);
  g.c.resize(size_t(g.w) * g.h);
  for (int y = 0; y < g.h; y++) {
    for (int x = 0; x < g.w; x++) {
      g.c[size_t(y) * g.w + x] = coverage(img.px_bl(x0 + x, y0 + y));
    }
  }
  return g;
}

/** Bilinear upscale (pixel centers aligned), i.e. what a scaled 1x bitmap would look like. */
Grid upscale(const Grid &src, const float s)
{
  Grid g;
  g.w = int(std::lround(src.w * s));
  g.h = int(std::lround(src.h * s));
  g.c.resize(size_t(g.w) * g.h);
  for (int y = 0; y < g.h; y++) {
    for (int x = 0; x < g.w; x++) {
      const float fx = std::clamp((x + 0.5f) / s - 0.5f, 0.0f, float(src.w - 1));
      const float fy = std::clamp((y + 0.5f) / s - 0.5f, 0.0f, float(src.h - 1));
      const int ix = std::min(int(fx), src.w - 2 < 0 ? 0 : src.w - 2);
      const int iy = std::min(int(fy), src.h - 2 < 0 ? 0 : src.h - 2);
      const float tx = fx - ix, ty = fy - iy;
      const int ix1 = std::min(ix + 1, src.w - 1), iy1 = std::min(iy + 1, src.h - 1);
      const float a = src.at(ix, iy) * (1 - tx) + src.at(ix1, iy) * tx;
      const float b = src.at(ix, iy1) * (1 - tx) + src.at(ix1, iy1) * tx;
      g.c[size_t(y) * g.w + x] = a * (1 - ty) + b * ty;
    }
  }
  return g;
}

/** Mean of the steepest 25% of neighbor coverage steps (1.0 = hard one-pixel edges). */
float sharpness(const Grid &g)
{
  std::vector<float> steps;
  for (int y = 0; y + 1 < g.h; y++) {
    for (int x = 0; x + 1 < g.w; x++) {
      const float d = std::max(std::fabs(g.at(x + 1, y) - g.at(x, y)), std::fabs(g.at(x, y + 1) - g.at(x, y)));
      if (d > 0.02f) {
        steps.push_back(d);
      }
    }
  }
  if (steps.empty()) {
    return 0.0f;
  }
  std::sort(steps.begin(), steps.end(), std::greater<float>());
  const size_t n = std::max<size_t>(1, steps.size() / 4);
  double sum = 0.0;
  for (size_t i = 0; i < n; i++) {
    sum += steps[i];
  }
  return float(sum / n);
}

Ink measure(const Image &img, int x0, int y0, int x1, int y1)
{
  Ink r;
  x0 = std::max(0, x0);
  y0 = std::max(0, y0);
  x1 = std::min(img.width, x1);
  y1 = std::min(img.height, y1);
  for (int y = y0; y < y1; y++) {
    for (int x = x0; x < x1; x++) {
      const float c = coverage(img.px_bl(x, y));
      if (c < 0.1f) {
        continue;
      }
      r.ink++;
      if (c > 0.9f) {
        r.solid++;
      }
      else {
        r.partial++;
      }
      r.xmin = std::min(r.xmin, x);
      r.xmax = std::max(r.xmax, x);
      r.ymin = std::min(r.ymin, y);
      r.ymax = std::max(r.ymax, y);
    }
  }
  return r;
}

bool compare_golden(const Image &img, const std::string &golden_path, const double max_frac, std::string &why)
{
  Image golden;
  if (!stk::gfx::png_read(golden_path, golden, why)) {
    return false;
  }
  if (golden.width != img.width || golden.height != img.height) {
    why = "golden size differs";
    return false;
  }
  int bad = 0;
  for (size_t i = 0; i < img.rgba.size(); i += 4) {
    int d = 0;
    for (int c = 0; c < 3; c++) {
      d = std::max(d, std::abs(int(img.rgba[i + c]) - int(golden.rgba[i + c])));
    }
    bad += d > 40;
  }
  const double frac = double(bad) / (double(img.width) * img.height);
  char buf[160];
  snprintf(buf, sizeof(buf), "%d / %d pixels differ by > 40 (%.3f%%, limit %.3f%%)", bad,
           img.width * img.height, frac * 100, max_frac * 100);
  why = buf;
  return frac <= max_frac;
}

}  // namespace

int main(int argc, char **argv)
{
  std::string golden_dir;
  bool update = false;
  double max_diff = 0.01;
  std::vector<Input> inputs;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    if (a == "--golden-dir" && i + 1 < argc) {
      golden_dir = argv[++i];
    }
    else if (a == "--update-golden") {
      update = true;
    }
    else if (a == "--max-diff" && i + 1 < argc) {
      max_diff = atof(argv[++i]);
    }
    else if (a.find('=') != std::string::npos) {
      Input in;
      in.scale = float(atof(a.substr(0, a.find('=')).c_str()));
      in.path = a.substr(a.find('=') + 1);
      inputs.push_back(in);
    }
    else {
      fprintf(stderr, "usage: %s [--golden-dir DIR] [--update-golden] [--max-diff F] SCALE=PNG...\n",
              argv[0]);
      return 2;
    }
  }
  std::sort(inputs.begin(), inputs.end(), [](const Input &a, const Input &b) { return a.scale < b.scale; });
  if (inputs.empty() || inputs.front().scale <= 0.0f) {
    fprintf(stderr, "no inputs\n");
    return 2;
  }

  for (Input &in : inputs) {
    std::string err;
    if (!stk::gfx::png_read(in.path, in.img, err)) {
      check(false, "read " + in.path + ": " + err);
      return 1;
    }
    const std::string tag = scale_tag(in.scale);
    printf("== %s (%dx%d, scale %g)\n", in.path.c_str(), in.img.width, in.img.height, in.scale);

    if (!golden_dir.empty()) {
      const std::string golden = golden_dir + "/sample_" + tag + ".png";
      if (update) {
        check(stk::gfx::png_write(golden, in.img), "updated golden " + golden);
      }
      else {
        std::string why;
        const bool ok = compare_golden(in.img, golden, max_diff, why);
        check(ok, "golden " + golden + ": " + why);
      }
    }

    const SampleLayout l = sample_layout(in.img.width, in.img.height, in.scale);
    const Image &img = in.img;
    check(near_color(img.px_bl(img.width - 2, img.height - 2), theme::kHeaderBack, 3), tag + " header color");
    check(near_color(img.px_bl(img.width - 2, (l.accent_y0 + l.accent_y1) / 2), theme::kAccent, 3),
          tag + " accent line");
    check(near_color(img.px_bl(img.width - 2, img.height / 2), theme::kRegionBack, 3), tag + " region color");
  }

  /* Per-row CJK and Latin ink, then cross-scale linearity and crispness. */
  const Input &base = inputs.front();
  const size_t n_rows = kSamplePoints.size();
  for (size_t r = 0; r < n_rows; r++) {
    std::vector<Ink> cjk(inputs.size());
    std::vector<Grid> grids(inputs.size());
    for (size_t i = 0; i < inputs.size(); i++) {
      const Input &in = inputs[i];
      const SampleLayout l = sample_layout(in.img.width, in.img.height, in.scale);
      const SampleRow &row = l.rows[r];
      const int em = int(std::lround(row.px));
      cjk[i] = measure(in.img, row.cjk_x - 2, row.baseline - em / 2, row.latin_x - em / 4,
                       row.baseline + em + em / 4);
      grids[i] = crop(in.img, cjk[i].xmin - 2, cjk[i].ymin - 2, cjk[i].xmax + 3, cjk[i].ymax + 3);
      const Ink latin = measure(in.img, row.latin_x - 2, row.baseline - em / 2,
                                row.latin_x + 5 * em, row.baseline + em + em / 4);
      printf("  %gpt @%gx: CJK box %dx%d ink %d sharpness %.3f | Latin box %dx%d ink %d\n", row.points,
             in.scale, cjk[i].width(), cjk[i].height(), cjk[i].ink, sharpness(grids[i]),
             latin.width(), latin.height(), latin.ink);
      /* "中文" spans about two em horizontally and most of an em vertically. */
      const bool cjk_ok = cjk[i].height() >= int(0.6f * row.px) && cjk[i].height() <= int(1.2f * row.px) + 2 &&
                          cjk[i].width() >= int(1.6f * row.px) && cjk[i].width() <= int(2.2f * row.px) + 2;
      check(cjk_ok, "CJK glyphs present " + std::to_string(int(row.points)) + "pt @" + scale_tag(in.scale));
      check(latin.ink > int(row.px * row.px * 0.3f), "Latin glyphs present " + std::to_string(int(row.points)) +
                                                          "pt @" + scale_tag(in.scale));
    }
    for (size_t i = 1; i < inputs.size(); i++) {
      const float s = inputs[i].scale / base.scale;
      const float h0 = float(cjk[0].height()), hi = float(cjk[i].height());
      /* Glyph heights round to whole pixels: allow +-1.5 px of the 1x height plus 4%. */
      const float expect = h0 * s;
      const float tol = 1.5f * s + 0.04f * expect;
      char buf[200];
      snprintf(buf, sizeof(buf), "%gpt height %.0f px @%gx vs %.0f px @%gx (expect %.1f +- %.1f)",
               kSamplePoints[r], hi, inputs[i].scale, h0, base.scale, expect, tol);
      check(std::fabs(hi - expect) <= tol, buf);
      /* Crisp: as sharp as at 1x, and clearly sharper than the 1x rendering scaled up. */
      const float k0 = sharpness(grids[0]), ki = sharpness(grids[i]);
      const float k_up = sharpness(upscale(grids[0], s));
      snprintf(buf, sizeof(buf),
               "%gpt sharpness %.3f @%gx vs %.3f @%gx, upscaled 1x %.3f (need >= %.3f and >= %.3f)",
               kSamplePoints[r], ki, inputs[i].scale, k0, base.scale, k_up, 0.8f * k0, k_up * 1.4f);
      check(ki >= 0.8f * k0 && ki >= 1.4f * k_up, buf);
    }
  }

  printf("%s\n", g_failures ? "FAIL" : "PASS");
  return g_failures ? 1 : 0;
}
