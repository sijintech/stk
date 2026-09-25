/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "support.hh"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include <gtest/gtest.h>

#include "stk/core/mmap.hh"
#include "stk/core/sha256.hh"

namespace stk::viewer_gpu::test {

gfx::Gpu *g_gpu = nullptr;
std::string g_backend;

gfx::Gpu &gpu()
{
  return *g_gpu;
}

std::string backend_id()
{
  return g_backend;
}

std::filesystem::path repo_root()
{
  return STK_REPO_ROOT;
}

std::filesystem::path fixtures_dir()
{
  return repo_root() / "desktop" / "tests" / "viewer" / "fixtures";
}

std::filesystem::path golden_dir()
{
  return repo_root() / "desktop" / "tests" / "viewer" / "golden";
}

std::filesystem::path out_dir()
{
  std::filesystem::path p = STK_VIEWER_TEST_OUT;
  std::filesystem::create_directories(p);
  return p;
}

bool update_goldens()
{
  const char *v = std::getenv("STK_UPDATE_GOLDENS");
  return v && std::string(v) == "1";
}

/* -------------------------------------------------------------------- */

PayloadBuilder::PayloadBuilder(std::array<double, 3> render_origin)
{
  manifest_ = io::Json::object();
  manifest_["schema"] = "stk.payload/2";
  manifest_["render_origin"] = {render_origin[0], render_origin[1], render_origin[2]};
  manifest_["length_unit"] = "unspecified";
  manifest_["buffers"] = io::Json::array();
  manifest_["accessors"] = io::Json::array();
  manifest_["layers"] = io::Json::array();
}

void PayloadBuilder::add(const std::string &id, std::vector<uint8_t> bytes, const std::string &type,
                         const int components, const size_t count)
{
  const std::string sha = core::Sha256::hex(bytes.data(), bytes.size());
  const std::string buffer_id = "b_" + id;
  manifest_["buffers"].push_back({{"id", buffer_id},
                                  {"uri", "sha256:" + sha},
                                  {"sha256", sha},
                                  {"byteLength", bytes.size()},
                                  {"encoding", "raw"}});
  manifest_["accessors"].push_back({{"id", id},
                                    {"buffer", buffer_id},
                                    {"byteOffset", 0},
                                    {"count", count},
                                    {"type", type},
                                    {"components", components}});
  blobs_[sha] = std::move(bytes);
}

std::shared_ptr<const io::Payload> PayloadBuilder::build() const
{
  std::map<std::string, core::SharedBytes> blobs;
  for (const auto &[sha, bytes] : blobs_) {
    blobs[sha] = core::SharedBytes::copy_of(bytes);
  }
  return std::make_shared<const io::Payload>(io::decode(manifest_, std::move(blobs)));
}

/* -------------------------------------------------------------------- */

namespace {

std::vector<double> luma(const gfx::Image &img)
{
  std::vector<double> y(size_t(img.width) * img.height);
  for (size_t i = 0; i < y.size(); i++) {
    const uint8_t *p = &img.rgba[i * 4];
    y[i] = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2];
  }
  return y;
}

}  // namespace

double ssim(const gfx::Image &a, const gfx::Image &b)
{
  if (a.width != b.width || a.height != b.height || a.empty()) {
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

double differing_fraction(const gfx::Image &a, const gfx::Image &b, const int tolerance, int *max_diff)
{
  if (a.width != b.width || a.height != b.height) {
    return 1.0;
  }
  size_t count = 0;
  int worst = 0;
  const size_t n = size_t(a.width) * a.height;
  for (size_t i = 0; i < n; i++) {
    int d = 0;
    for (int k = 0; k < 4; k++) {
      d = std::max(d, std::abs(int(a.rgba[i * 4 + k]) - int(b.rgba[i * 4 + k])));
    }
    worst = std::max(worst, d);
    if (d > tolerance) {
      count++;
    }
  }
  if (max_diff) {
    *max_diff = worst;
  }
  return double(count) / double(n);
}

std::vector<uint8_t> chroma_mask(const gfx::Image &img, const int threshold)
{
  std::vector<uint8_t> m(size_t(img.width) * img.height);
  for (size_t i = 0; i < m.size(); i++) {
    const uint8_t *p = &img.rgba[i * 4];
    const int hi = std::max({p[0], p[1], p[2]}), lo = std::min({p[0], p[1], p[2]});
    m[i] = hi - lo > threshold ? 1 : 0;
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

size_t count_color(const gfx::Image &img, std::array<uint8_t, 3> rgb)
{
  size_t n = 0;
  for (size_t i = 0; i + 3 < img.rgba.size(); i += 4) {
    n += (img.rgba[i] == rgb[0] && img.rgba[i + 1] == rgb[1] && img.rgba[i + 2] == rgb[2]) ? 1 : 0;
  }
  return n;
}

size_t count_hue(const gfx::Image &img, std::array<uint8_t, 3> rgb, const double tolerance)
{
  const double rmax = std::max({rgb[0], rgb[1], rgb[2], uint8_t(1)});
  const double want[3] = {rgb[0] / rmax, rgb[1] / rmax, rgb[2] / rmax};
  size_t n = 0;
  for (size_t i = 0; i + 3 < img.rgba.size(); i += 4) {
    const double m = std::max({img.rgba[i], img.rgba[i + 1], img.rgba[i + 2]});
    if (m <= 30) {
      continue;
    }
    /* Lighting darkens (and a light kit brightens a little): no match far above the colour itself. */
    bool ok = m <= rmax * 1.15 + 5;
    for (int k = 0; k < 3 && ok; k++) {
      ok = std::abs(img.rgba[i + size_t(k)] / m - want[k]) <= tolerance;
    }
    n += ok ? 1 : 0;
  }
  return n;
}

std::map<std::array<uint8_t, 3>, size_t> histogram(const gfx::Image &img)
{
  std::map<std::array<uint8_t, 3>, size_t> h;
  for (size_t i = 0; i + 3 < img.rgba.size(); i += 4) {
    h[{img.rgba[i], img.rgba[i + 1], img.rgba[i + 2]}]++;
  }
  return h;
}

gfx::Image render(Viewer &viewer, const std::string &name, const ExportOptions &options)
{
  gfx::Image img;
  std::string err;
  EXPECT_TRUE(viewer.render_image(options, img, err)) << err;
  gfx::png_write((out_dir() / (name + "_" + backend_id() + ".png")).string(), img);
  return img;
}

double compare_golden(const gfx::Image &img, const std::string &golden)
{
  const std::filesystem::path path = golden_dir() / golden;
  if (update_goldens() && backend_id() == "vulkan") {
    std::filesystem::create_directories(golden_dir());
    gfx::png_write(path.string(), img);
    return 1.0;
  }
  gfx::Image ref;
  std::string err;
  if (!gfx::png_read(path.string(), ref, err)) {
    ADD_FAILURE() << "golden " << path << ": " << err;
    return 0.0;
  }
  EXPECT_EQ(ref.width, img.width);
  EXPECT_EQ(ref.height, img.height);
  return ssim(img, ref);
}

}  // namespace stk::viewer_gpu::test
