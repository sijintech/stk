/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/json.hh"
#include "stk/io/png.hh"
#include <array>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace stk::app {
/** One explicitly resolved citation page. Pure CPU; no RPC, disk, model, GPU,
 * Report identity or Viewer state. A failed replacement clears the old page. */
class LiteraturePage {
 public:
  struct Quad {
    uint32_t index = 0, start = 0, end = 0;
    std::array<std::array<double, 2>, 4> points{};
  };
  bool adopt(const io::Json &resolved, const io::Json &rendered);
  /** Geometry only, not source authority: compare the four crop-box corners in
   * pixels (0.02 tolerance), including rotated pages and large coordinate origins. */
  static bool affine_matches(const io::Json &page, uint32_t width, uint32_t height,
                             const std::array<double, 6> &matrix);
  void clear();
  bool ready() const { return image_.has_value(); }
  const std::string &error() const { return error_; }
  const io::Image *image() const { return image_ ? &*image_ : nullptr; }
  const std::vector<uint8_t> &png() const { return png_; }
  const io::Json &citation() const { return citation_; }
  /** Original image-pixel coordinates; overlays never alter the verified PNG. */
  std::shared_ptr<const std::vector<Quad>> highlights() const { return highlights_; }
 private:
  std::string error_;
  io::Json citation_;
  std::vector<uint8_t> png_;
  std::optional<io::Image> image_;
  std::shared_ptr<const std::vector<Quad>> highlights_;
};
}  // namespace stk::app
