/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* GPU programs of the viewer, written against Blender's shader create-info system
 * (gpu::shader::ShaderCreateInfo: vertex inputs, stage interfaces, push constants, storage buffers,
 * samplers) and registered at runtime: the GLSL (src/glsl, embedded at build time) goes through
 * the same shader_tool source processor that Blender runs on Python shaders
 * (GPU_shader_preprocess_source), then the backend compiler (GLSL for OpenGL, SPIR-V through
 * shaderc for Vulkan, MSL for Metal). Each program has a colour variant and an id-pass variant
 * (STK_ID_PASS: uvec2 (layer tag, element) output for picking). */

#include <string>

namespace blender::gpu {
class Shader;
}

namespace stk::viewer_gpu {

enum class Program { Mesh, Glyph, Line, Point, Slice, Volume, Count };

/* Resource slots shared with the draw code. */
namespace slot {
/* storage buffers */
inline constexpr int pos = 0;  /* positions (glyph: mesh soup) */
inline constexpr int idx = 1;  /* indices (glyph: instances) */
inline constexpr int nrm = 2;  /* normals (points: radii) */
inline constexpr int cval = 3; /* colour values */
/* samplers */
inline constexpr int lut = 0;   /* 259-texel LUT (mesh/glyph/line/point), slice image, volume data */
inline constexpr int tf = 1;    /* volume transfer function */
inline constexpr int depth = 2; /* volume: opaque scene depth */
}  // namespace slot

class ShaderCache {
 public:
  ShaderCache() = default;
  ~ShaderCache();
  ShaderCache(const ShaderCache &) = delete;
  ShaderCache &operator=(const ShaderCache &) = delete;

  /** The compiled program (compiled on first use); nullptr when compilation failed (see error()). */
  blender::gpu::Shader *get(Program program, bool id_pass);
  const std::string &error() const
  {
    return error_;
  }
  void clear();

 private:
  blender::gpu::Shader *shaders_[int(Program::Count)][2] = {};
  bool failed_[int(Program::Count)][2] = {};
  std::string error_;
};

}  // namespace stk::viewer_gpu
