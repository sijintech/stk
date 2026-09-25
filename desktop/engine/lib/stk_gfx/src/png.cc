/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file PNG I/O for stk::gfx::Image through stk_io (libspng + miniz). */

#include "stk/gfx/image.hh"

#include <cstring>
#include <exception>

#include "stk/core/paths.hh"
#include "stk/io/png.hh"

namespace stk::gfx {

bool png_encode(const uint8_t *rgba, const int width, const int height, std::vector<uint8_t> &r_bytes)
{
  if (!rgba || width <= 0 || height <= 0) {
    return false;
  }
  try {
    r_bytes = io::encode_png(rgba, uint32_t(width), uint32_t(height), 4);
    return true;
  }
  catch (const std::exception &) {
    return false;
  }
}

static bool to_image(io::Image &&src, Image &r_img)
{
  if (src.channels != 4 || src.width == 0 || src.height == 0) {
    return false;
  }
  r_img.width = int(src.width);
  r_img.height = int(src.height);
  r_img.rgba = std::move(src.pixels);
  return true;
}

bool png_decode(const uint8_t *data, const size_t size, Image &r_img, std::string &r_error)
{
  try {
    if (!to_image(io::decode_png(std::span<const uint8_t>(data, size)), r_img)) {
      r_error = "unexpected PNG layout";
      return false;
    }
    return true;
  }
  catch (const std::exception &e) {
    r_error = e.what();
    return false;
  }
}

bool png_write(const std::string &path, const Image &img)
{
  if (img.empty()) {
    return false;
  }
  try {
    io::Image out(uint32_t(img.width), uint32_t(img.height), 4);
    memcpy(out.pixels.data(), img.rgba.data(), out.pixels.size());
    io::write_png(core::path_from_utf8(path), out);
    return true;
  }
  catch (const std::exception &) {
    return false;
  }
}

bool png_read(const std::string &path, Image &r_img, std::string &r_error)
{
  try {
    if (!to_image(io::read_png(core::path_from_utf8(path)), r_img)) {
      r_error = "unexpected PNG layout: " + path;
      return false;
    }
    return true;
  }
  catch (const std::exception &e) {
    r_error = std::string(e.what()) + ": " + path;
    return false;
  }
}

}  // namespace stk::gfx
