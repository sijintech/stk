/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/gfx/offscreen.hh"

#include <cstring>
#include <vector>

#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_matrix.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"

namespace stk::gfx {

using namespace blender;

/** Blender's `GLA_PIXEL_OFS`: sub-pixel offset of the UI projection so that integer coordinates
 * rasterize (lines, rectangle edges, glyph quads) exactly as in Blender's window manager. */
static constexpr float kPixelOffset = 0.375f;

void push_pixel_space(const int width, const int height)
{
  GPU_matrix_push_projection();
  GPU_matrix_ortho_set(-kPixelOffset,
                       float(width) - kPixelOffset,
                       -kPixelOffset,
                       float(height) - kPixelOffset,
                       -100.0f,
                       100.0f);
  GPU_matrix_push();
  GPU_matrix_identity_set();
}

void pop_pixel_space()
{
  GPU_matrix_pop();
  GPU_matrix_pop_projection();
}

std::unique_ptr<Offscreen> Offscreen::create(const int width, const int height, std::string &r_error)
{
  if (width <= 0 || height <= 0 || width > 16384 || height > 16384) {
    r_error = "invalid offscreen size " + std::to_string(width) + "x" + std::to_string(height);
    return nullptr;
  }
  if (!GPU_context_active_get()) {
    r_error = "no active GPU context";
    return nullptr;
  }
  char err[256] = "";
  GPUOffScreen *ofs = GPU_offscreen_create(width,
                                           height,
                                           false,
                                           gpu::TextureFormat::UNORM_8_8_8_8,
                                           GPU_TEXTURE_USAGE_HOST_READ | GPU_TEXTURE_USAGE_SHADER_READ,
                                           false,
                                           err);
  if (!ofs) {
    r_error = err[0] ? err : "GPU_offscreen_create failed";
    return nullptr;
  }
  std::unique_ptr<Offscreen> result(new Offscreen());
  result->ofs_ = ofs;
  result->width_ = width;
  result->height_ = height;
  return result;
}

Offscreen::~Offscreen()
{
  if (ofs_) {
    GPU_offscreen_free(ofs_);
  }
}

void Offscreen::bind()
{
  GPU_offscreen_bind(ofs_, true);
}

void Offscreen::unbind()
{
  GPU_offscreen_unbind(ofs_, true);
}

Image Offscreen::read()
{
  Image img;
  img.width = width_;
  img.height = height_;
  img.rgba.resize(size_t(width_) * height_ * 4);
  std::vector<uint8_t> bottom_up(img.rgba.size());
  GPU_finish();
  GPU_offscreen_read_color(ofs_, GPU_DATA_UBYTE, bottom_up.data());
  const size_t stride = size_t(width_) * 4;
  for (int y = 0; y < height_; y++) {
    memcpy(&img.rgba[size_t(height_ - 1 - y) * stride], &bottom_up[size_t(y) * stride], stride);
  }
  return img;
}

gpu::Texture *Offscreen::color_texture()
{
  return GPU_offscreen_color_texture(ofs_);
}

bool render_offscreen(const int width,
                      const int height,
                      const std::function<void()> &draw,
                      Image &r_image,
                      std::string &r_error)
{
  r_image = Image{};
  GPUContext *ctx = GPU_context_active_get();
  if (!ctx) {
    r_error = "no active GPU context";
    return false;
  }
  GPU_render_begin();
  GPU_context_begin_frame(ctx);
  std::unique_ptr<Offscreen> ofs = Offscreen::create(width, height, r_error);
  if (ofs) {
    ofs->bind();
    push_pixel_space(width, height);
    draw();
    pop_pixel_space();
    r_image = ofs->read();
    ofs->unbind();
    ofs.reset();
  }
  GPU_context_end_frame(ctx);
  GPU_render_end();
  return !r_image.empty();
}

}  // namespace stk::gfx
