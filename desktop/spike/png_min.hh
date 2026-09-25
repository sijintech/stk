/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Minimal 8-bit RGBA PNG writer/reader on zlib (spike + golden compare only). */
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace stk::spike {

struct Image {
  int width = 0;
  int height = 0;
  /** RGBA8, rows top to bottom. */
  std::vector<uint8_t> rgba;

  const uint8_t *px(int x, int y) const
  {
    return &rgba[(size_t(y) * width + x) * 4];
  }
};

bool png_write(const std::string &path, const Image &img);
/** Reads 8-bit RGB/RGBA non-interlaced PNGs (all filter types). */
bool png_read(const std::string &path, Image &img, std::string &err);

}  // namespace stk::spike
