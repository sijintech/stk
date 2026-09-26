/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/png.hh"

#include "stk/core/mmap.hh"

#include <spng.h>

#include <cstdlib>
#include <cstring>
#include <memory>

namespace stk::io {

namespace {

struct ContextDeleter {
  void operator()(spng_ctx *ctx) const
  {
    spng_ctx_free(ctx);
  }
};
using Context = std::unique_ptr<spng_ctx, ContextDeleter>;

[[noreturn]] void fail(const char *what, int error)
{
  throw PngError(std::string(what) + ": " + spng_strerror(error));
}

uint8_t color_type(uint32_t channels)
{
  switch (channels) {
    case 1:
      return SPNG_COLOR_TYPE_GRAYSCALE;
    case 2:
      return SPNG_COLOR_TYPE_GRAYSCALE_ALPHA;
    case 3:
      return SPNG_COLOR_TYPE_TRUECOLOR;
    case 4:
      return SPNG_COLOR_TYPE_TRUECOLOR_ALPHA;
    default:
      throw PngError("PNG images have 1 to 4 channels");
  }
}

}  // namespace

std::vector<uint8_t> encode_png(const uint8_t *pixels,
                                uint32_t width,
                                uint32_t height,
                                uint32_t channels,
                                size_t stride,
                                const PngOptions &options)
{
  if (width == 0 || height == 0) {
    throw PngError("PNG images need a positive size");
  }
  const size_t row_bytes = size_t(width) * channels;
  if (stride == 0) {
    stride = row_bytes;
  }
  if (stride < row_bytes) {
    throw PngError("stride is smaller than a row");
  }
  Context ctx(spng_ctx_new(SPNG_CTX_ENCODER));
  if (!ctx) {
    throw PngError("cannot create a PNG encoder");
  }
  spng_set_option(ctx.get(), SPNG_ENCODE_TO_BUFFER, 1);
  spng_set_option(ctx.get(), SPNG_IMG_COMPRESSION_LEVEL, options.compression_level);
  spng_ihdr ihdr{};
  ihdr.width = width;
  ihdr.height = height;
  ihdr.bit_depth = 8;
  ihdr.color_type = color_type(channels);
  if (int error = spng_set_ihdr(ctx.get(), &ihdr)) {
    fail("PNG header", error);
  }
  int error;
  if (stride == row_bytes) {
    error = spng_encode_image(ctx.get(), pixels, row_bytes * height, SPNG_FMT_PNG, SPNG_ENCODE_FINALIZE);
  }
  else {
    error = spng_encode_image(ctx.get(), nullptr, 0, SPNG_FMT_PNG, SPNG_ENCODE_PROGRESSIVE | SPNG_ENCODE_FINALIZE);
    for (uint32_t y = 0; !error && y < height; y++) {
      error = spng_encode_row(ctx.get(), pixels + y * stride, row_bytes);
    }
    if (error == SPNG_EOI) {
      error = 0;
    }
  }
  if (error) {
    fail("PNG encode", error);
  }
  size_t length = 0;
  void *buffer = spng_get_png_buffer(ctx.get(), &length, &error);
  if (!buffer) {
    fail("PNG encode", error);
  }
  std::vector<uint8_t> out(static_cast<uint8_t *>(buffer), static_cast<uint8_t *>(buffer) + length);
  std::free(buffer);
  return out;
}

std::vector<uint8_t> encode_png(const Image &image, const PngOptions &options)
{
  if (image.pixels.size() != size_t(image.width) * image.height * image.channels) {
    throw PngError("image pixel buffer size does not match its dimensions");
  }
  return encode_png(image.pixels.data(), image.width, image.height, image.channels, 0, options);
}

void write_png(const std::filesystem::path &path, const Image &image, const PngOptions &options)
{
  const std::vector<uint8_t> data = encode_png(image, options);
  core::write_file_atomic(path, data);
}

Image decode_png(std::span<const uint8_t> data, const PngLimits &limits)
{
  Context ctx(spng_ctx_new(0));
  if (!ctx) {
    throw PngError("cannot create a PNG decoder");
  }
  spng_set_image_limits(ctx.get(), limits.max_width, limits.max_height);
  spng_set_chunk_limits(ctx.get(), 64u << 20, 64u << 20);
  if (int error = spng_set_png_buffer(ctx.get(), data.data(), data.size())) {
    fail("PNG buffer", error);
  }
  spng_ihdr ihdr{};
  if (int error = spng_get_ihdr(ctx.get(), &ihdr)) {
    fail("PNG header", error);
  }
  if (uint64_t(ihdr.width) * ihdr.height > limits.max_pixels) {
    throw PngError("PNG image is larger than the pixel limit");
  }
  size_t length = 0;
  if (int error = spng_decoded_image_size(ctx.get(), SPNG_FMT_RGBA8, &length)) {
    fail("PNG size", error);
  }
  Image image(ihdr.width, ihdr.height, 4);
  if (length != image.pixels.size()) {
    throw PngError("unexpected decoded PNG size");
  }
  if (int error = spng_decode_image(ctx.get(), image.pixels.data(), length, SPNG_FMT_RGBA8, SPNG_DECODE_TRNS)) {
    fail("PNG decode", error);
  }
  return image;
}

Image read_png(const std::filesystem::path &path, const PngLimits &limits)
{
  const core::SharedBytes bytes = core::SharedBytes::from_file(path, false);
  return decode_png(bytes.span(), limits);
}

}  // namespace stk::io
