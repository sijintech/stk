/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Offscreen rendering: RGBA8 framebuffers read back to #Image, and pixel-space projection helpers
 * shared by window regions and headless exports.
 */
#pragma once

#include <functional>
#include <memory>
#include <string>

#include "stk/gfx/image.hh"

namespace blender {
struct GPUOffScreen;
namespace gpu {
class Texture;
}
}  // namespace blender

namespace stk::gfx {

/**
 * Pushes an orthographic projection where one unit is one framebuffer pixel, origin at the
 * bottom-left corner of a `width` x `height` viewport, with an identity model-view matrix.
 */
void push_pixel_space(int width, int height);
void pop_pixel_space();

/** RGBA8 offscreen framebuffer (color only). Requires an active GPU context. */
class Offscreen {
 public:
  static std::unique_ptr<Offscreen> create(int width, int height, std::string &r_error);
  ~Offscreen();
  Offscreen(const Offscreen &) = delete;
  Offscreen &operator=(const Offscreen &) = delete;

  int width() const
  {
    return width_;
  }
  int height() const
  {
    return height_;
  }
  /** Binds as the render target and sets the viewport to the full size. */
  void bind();
  /** Restores the previous framebuffer (the window back buffer). */
  void unbind();
  /** Reads the color attachment back (waits for the GPU); rows top to bottom. */
  Image read();
  blender::gpu::Texture *color_texture();

 private:
  Offscreen() = default;
  blender::GPUOffScreen *ofs_ = nullptr;
  int width_ = 0, height_ = 0;
};

/**
 * Renders one standalone frame into a new `width` x `height` offscreen target and reads it back.
 * Wraps `GPU_render_begin/end` and the frame of the active context, so it must not be called
 * while a window frame is being drawn (use #Offscreen there). `draw` runs with the offscreen bound
 * and #push_pixel_space applied.
 */
bool render_offscreen(int width,
                      int height,
                      const std::function<void()> &draw,
                      Image &r_image,
                      std::string &r_error);

}  // namespace stk::gfx
