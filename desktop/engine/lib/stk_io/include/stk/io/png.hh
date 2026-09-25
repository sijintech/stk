/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* PNG encode/decode (libspng + miniz, vendored): 8-bit gray, gray+alpha, RGB and RGBA images, rows
 * top to bottom. Decoding always yields RGBA8 (palette, 16-bit and tRNS converted). */

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace stk::io {

class PngError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct Image {
  uint32_t width = 0, height = 0;
  uint32_t channels = 4; /* 1 gray, 2 gray+alpha, 3 RGB, 4 RGBA */
  std::vector<uint8_t> pixels;

  Image() = default;
  Image(uint32_t w, uint32_t h, uint32_t c = 4) : width(w), height(h), channels(c), pixels(size_t(w) * h * c) {}
  size_t stride() const
  {
    return size_t(width) * channels;
  }
  uint8_t *row(uint32_t y)
  {
    return pixels.data() + size_t(y) * stride();
  }
  const uint8_t *row(uint32_t y) const
  {
    return pixels.data() + size_t(y) * stride();
  }
  uint8_t *pixel(uint32_t x, uint32_t y)
  {
    return row(y) + size_t(x) * channels;
  }
  const uint8_t *pixel(uint32_t x, uint32_t y) const
  {
    return row(y) + size_t(x) * channels;
  }
};

struct PngOptions {
  int compression_level = 6; /* 0 (store) .. 9 */
};

/** Encode `height` rows of `width * channels` bytes each, `stride` bytes apart (0 = packed). */
std::vector<uint8_t> encode_png(const uint8_t *pixels,
                                uint32_t width,
                                uint32_t height,
                                uint32_t channels,
                                size_t stride = 0,
                                const PngOptions &options = {});
std::vector<uint8_t> encode_png(const Image &image, const PngOptions &options = {});
/** Atomic write (temporary file + rename). */
void write_png(const std::filesystem::path &path, const Image &image, const PngOptions &options = {});

struct PngLimits {
  uint32_t max_width = 1u << 16, max_height = 1u << 16;
  uint64_t max_pixels = uint64_t(1) << 30;
};

/** Decode to RGBA8; throws PngError for corrupt data (CRC, truncation) or images over the limits. */
Image decode_png(std::span<const uint8_t> data, const PngLimits &limits = {});
Image read_png(const std::filesystem::path &path, const PngLimits &limits = {});

}  // namespace stk::io
