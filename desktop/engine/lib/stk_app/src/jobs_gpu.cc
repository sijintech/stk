/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file GPU textures for the Jobs editor's PNG preview (the only GPU code of stk_app). */

#include "stk/app/jobs_state.hh"

#include <cstdint>

#include "GPU_texture.hh"
#include "stk/io/png.hh"

namespace stk::app {

void use_gpu_textures(JobsState &jobs)
{
  namespace bgpu = blender::gpu;
  using namespace blender;
  jobs.create_texture = [](const io::Image &img) -> uint64_t {
    if (img.width == 0 || img.height == 0 || img.channels != 4 || img.pixels.size() < size_t(img.width) * img.height * 4) {
      return 0;
    }
    bgpu::Texture *tex = GPU_texture_create_2d("stk-jobs-preview", int(img.width), int(img.height), 1,
                                               bgpu::TextureFormat::UNORM_8_8_8_8, GPU_TEXTURE_USAGE_SHADER_READ,
                                               nullptr);
    if (!tex) {
      return 0;
    }
    GPU_texture_update(tex, GPU_DATA_UBYTE, img.pixels.data());
    GPU_texture_filter_mode(tex, true);
    return uint64_t(uintptr_t(tex));
  };
  jobs.free_texture = [](const uint64_t handle) {
    if (handle) {
      GPU_texture_free(reinterpret_cast<bgpu::Texture *>(uintptr_t(handle)));
    }
  };
}

}  // namespace stk::app
