/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Support of the stk_viewer_gpu tests: the process-wide GPU (one backend per test process, from
 * --gpu-backend), synthetic payloads, and image metrics (SSIM, colour masks, palettes). */

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/io/payload.hh"
#include "stk/viewer_gpu/viewer.hh"

#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace stk::viewer_gpu::test {

/** The GPU of this test process (created in main()). */
gfx::Gpu &gpu();
/** "vulkan" / "opengl" / "metal". */
std::string backend_id();

std::filesystem::path repo_root();
std::filesystem::path fixtures_dir();
std::filesystem::path golden_dir();
/** Output directory for rendered images (build tree). */
std::filesystem::path out_dir();
bool update_goldens();

/** Build a payload in memory (for synthetic test scenes). */
class PayloadBuilder {
 public:
  explicit PayloadBuilder(std::array<double, 3> render_origin);
  /** Adds a buffer + accessor of `values` (one buffer per accessor). */
  template<typename T>
  void accessor(const std::string &id, const std::vector<T> &values, const std::string &type, int components)
  {
    std::vector<uint8_t> bytes(values.size() * sizeof(T));
    std::memcpy(bytes.data(), values.data(), bytes.size());
    add(id, std::move(bytes), type, components, values.size() / size_t(components));
  }
  io::Json &manifest()
  {
    return manifest_;
  }
  void layer(io::Json layer)
  {
    manifest_["layers"].push_back(std::move(layer));
  }
  std::shared_ptr<const io::Payload> build() const;

 private:
  void add(const std::string &id, std::vector<uint8_t> bytes, const std::string &type, int components, size_t count);
  io::Json manifest_;
  std::map<std::string, std::vector<uint8_t>> blobs_;
};

/** Structural similarity of the luma of two same-size images (8x8 windows, stride 4). */
double ssim(const gfx::Image &a, const gfx::Image &b);
/** Fraction of pixels whose max channel difference exceeds `tolerance`, and the max difference. */
double differing_fraction(const gfx::Image &a, const gfx::Image &b, int tolerance, int *max_diff = nullptr);
/** Pixels that are clearly coloured (chroma max - min > threshold). */
std::vector<uint8_t> chroma_mask(const gfx::Image &img, int threshold = 40);
double iou(const std::vector<uint8_t> &a, const std::vector<uint8_t> &b);
/** Pixels exactly equal to `rgb`. */
size_t count_color(const gfx::Image &img, std::array<uint8_t, 3> rgb);
/** Pixels whose normalized chromaticity (rgb / max) is within `tolerance` of `rgb`'s, with 30 < max <= 1.15 x
 * the colour's max + 5 (a lit version of the colour). */
size_t count_hue(const gfx::Image &img, std::array<uint8_t, 3> rgb, double tolerance = 0.06);
/** The distinct RGB colours of an image with their pixel counts. */
std::map<std::array<uint8_t, 3>, size_t> histogram(const gfx::Image &img);

/** Load, render with `options`, save to out_dir()/name.png. */
gfx::Image render(Viewer &viewer, const std::string &name, const ExportOptions &options);
/** Compare with golden_dir()/golden (written instead when update_goldens()). Returns SSIM. */
double compare_golden(const gfx::Image &img, const std::string &golden);

}  // namespace stk::viewer_gpu::test
