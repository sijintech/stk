/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "gallery_wm.hh"

#include <cmath>
#include <vector>

#include "GPU_texture.hh"

namespace stk::ui::gallery {

namespace bgpu = blender::gpu;
using namespace blender;

/* -------------------------------------------------------------------- */
/* Demo texture */

uint64_t create_demo_texture(int w, int h)
{
  std::vector<uint8_t> px(size_t(w) * h * 4);
  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      /* Two domain families separated by wavy walls, shaded like a polarization map. */
      const float fx = float(x) / w, fy = float(y) / h;
      const float wall = std::sin(fx * 9.0f + 1.5f * std::sin(fy * 6.0f));
      const float v = 0.5f + 0.5f * std::tanh(wall * 4.0f);
      uint8_t *p = &px[(size_t(y) * w + x) * 4];
      p[0] = uint8_t(40 + 200 * v);
      p[1] = uint8_t(70 + 90 * (1.0f - std::fabs(wall)));
      p[2] = uint8_t(220 - 170 * v);
      p[3] = 255;
    }
  }
  bgpu::Texture *tex = GPU_texture_create_2d("stk-gallery-demo", w, h, 1, bgpu::TextureFormat::UNORM_8_8_8_8,
                                             GPU_TEXTURE_USAGE_SHADER_READ, nullptr);
  GPU_texture_update(tex, GPU_DATA_UBYTE, px.data());
  GPU_texture_filter_mode(tex, false);
  return uint64_t(uintptr_t(tex));
}

void free_texture(uint64_t handle)
{
  if (handle) {
    GPU_texture_free(reinterpret_cast<bgpu::Texture *>(uintptr_t(handle)));
  }
}

}  // namespace stk::ui::gallery
