/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * RGBA8 images as read back from the GPU (offscreen exports, goldens, clipboard images), with
 * PNG I/O through stk_io (libspng). Decoding accepts any PNG and yields RGBA8.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace stk::gfx {

struct Image {
  int width = 0;
  int height = 0;
  /** RGBA8, rows top to bottom (row 0 is the top of the picture). */
  std::vector<uint8_t> rgba;

  bool empty() const
  {
    return width <= 0 || height <= 0;
  }
  const uint8_t *px(int x, int y) const
  {
    return &rgba[(size_t(y) * width + x) * 4];
  }
  uint8_t *px(int x, int y)
  {
    return &rgba[(size_t(y) * width + x) * 4];
  }
  /** Pixel with a bottom-left origin (GPU / window-space convention). */
  const uint8_t *px_bl(int x, int y) const
  {
    return px(x, height - 1 - y);
  }
};

/** Encodes RGBA8 as PNG. */
bool png_encode(const uint8_t *rgba, int width, int height, std::vector<uint8_t> &r_bytes);
/** Decodes a PNG into RGBA8. */
bool png_decode(const uint8_t *data, size_t size, Image &r_img, std::string &r_error);

bool png_write(const std::string &path, const Image &img);
bool png_read(const std::string &path, Image &r_img, std::string &r_error);

}  // namespace stk::gfx
