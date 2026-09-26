/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "shaders.hh"

#include "glsl_sources.hh"

#include <cstdio>
#include <optional>

#include "GPU_shader.hh"
#include "gpu_shader_create_info.hh"

namespace stk::viewer_gpu {

using namespace blender;
using namespace blender::gpu::shader;

namespace {

/* Stage interfaces. The create info references them until the program is compiled, so they live
 * as long as one compilation (ShaderCache::get); static objects would keep guardedalloc blocks
 * until exit, which the application's leak check at shutdown counts. */
struct Interfaces {
  std::optional<StageInterfaceInfo> surface, point, slice, volume;
};

StageInterfaceInfo &surface_iface(Interfaces &store)
{
  if (!store.surface) {
    StageInterfaceInfo &i = store.surface.emplace("stk_surface_iface", "");
    i.smooth(Type::float3_t, "v_eye");
    i.smooth(Type::float3_t, "v_nrm");
    i.smooth(Type::float_t, "v_t");
    i.flat(Type::float_t, "v_tf");
    i.smooth(Type::float4_t, "v_rgba");
    i.flat(Type::float4_t, "v_rgbaf");
    i.flat(Type::uint_t, "v_id");
    i.flat(Type::int_t, "v_nan");
  }
  return *store.surface;
}

StageInterfaceInfo &point_iface(Interfaces &store)
{
  if (!store.point) {
    StageInterfaceInfo &i = store.point.emplace("stk_point_iface", "");
    i.smooth(Type::float3_t, "v_eye");
    i.flat(Type::float3_t, "v_center");
    i.smooth(Type::float2_t, "v_corner");
    i.flat(Type::float_t, "v_radius");
    i.flat(Type::float_t, "v_t");
    i.flat(Type::float4_t, "v_rgba");
    i.flat(Type::uint_t, "v_id");
    i.flat(Type::int_t, "v_nan");
  }
  return *store.point;
}

StageInterfaceInfo &slice_iface(Interfaces &store)
{
  if (!store.slice) {
    StageInterfaceInfo &i = store.slice.emplace("stk_slice_iface", "");
    i.smooth(Type::float3_t, "v_eye");
    i.smooth(Type::float2_t, "v_uv");
  }
  return *store.slice;
}

StageInterfaceInfo &volume_iface(Interfaces &store)
{
  if (!store.volume) {
    StageInterfaceInfo &i = store.volume.emplace("stk_volume_iface", "");
    i.no_perspective(Type::float2_t, "v_ndc");
  }
  return *store.volume;
}

void common_3d(ShaderCreateInfo &info)
{
  info.push_constant(Type::float4x4_t, "u_mvp");
  info.push_constant(Type::float4x4_t, "u_mv");
  info.push_constant(Type::float4_t, "u_solid");
  info.push_constant(Type::float4_t, "u_light");
  info.push_constant(Type::int4_t, "u_params");
  info.push_constant(Type::float4_t, "u_misc");
}

void color_resources(ShaderCreateInfo &info)
{
  info.storage_buf(slot::cval, Qualifier::read, "uint", "s_cval[]");
  info.sampler(slot::lut, ImageType::Float2D, "s_lut");
}

void outputs(ShaderCreateInfo &info, const bool id_pass)
{
  if (id_pass) {
    info.define("STK_ID_PASS");
    info.fragment_out(0, Type::uint2_t, "out_id");
  }
  else {
    info.fragment_out(0, Type::float4_t, "out_color");
  }
}

struct Sources {
  std::string vert, frag;
};

Sources describe(const Program program, const bool id_pass, ShaderCreateInfo &info, Interfaces &ifaces)
{
  const std::string common = glsl::stk_common_lib;
  Sources s;
  outputs(info, id_pass);
  switch (program) {
    case Program::Mesh:
      common_3d(info);
      color_resources(info);
      info.storage_buf(slot::pos, Qualifier::read, "float", "s_pos[]");
      info.storage_buf(slot::idx, Qualifier::read, "uint", "s_idx[]");
      info.storage_buf(slot::nrm, Qualifier::read, "float", "s_nrm[]");
      info.vertex_out(surface_iface(ifaces));
      s.vert = common + glsl::stk_mesh_vert;
      s.frag = common + glsl::stk_surface_frag;
      break;
    case Program::Glyph:
      common_3d(info);
      color_resources(info);
      info.storage_buf(slot::pos, Qualifier::read, "float", "s_pos[]");
      info.storage_buf(slot::idx, Qualifier::read, "float", "s_inst[]");
      info.vertex_out(surface_iface(ifaces));
      s.vert = common + glsl::stk_glyph_vert;
      s.frag = common + glsl::stk_surface_frag;
      break;
    case Program::Line:
      common_3d(info);
      color_resources(info);
      info.storage_buf(slot::pos, Qualifier::read, "float", "s_pos[]");
      info.storage_buf(slot::idx, Qualifier::read, "uint", "s_idx[]");
      info.vertex_out(surface_iface(ifaces));
      s.vert = common + glsl::stk_line_vert;
      s.frag = common + glsl::stk_surface_frag;
      break;
    case Program::Point:
      common_3d(info);
      color_resources(info);
      info.push_constant(Type::float4x4_t, "u_proj");
      info.storage_buf(slot::pos, Qualifier::read, "float", "s_pos[]");
      info.storage_buf(slot::nrm, Qualifier::read, "float", "s_rad[]");
      info.vertex_out(point_iface(ifaces));
      info.depth_write(DepthWrite::ANY);
      s.vert = common + glsl::stk_point_vert;
      s.frag = common + glsl::stk_point_frag;
      break;
    case Program::Slice:
      common_3d(info);
      info.define("STK_NO_COLOR_LIB");
      info.push_constant(Type::float4_t, "u_plane_origin");
      info.push_constant(Type::float4_t, "u_plane_u");
      info.push_constant(Type::float4_t, "u_plane_v");
      info.sampler(slot::lut, ImageType::Float2D, "s_img");
      info.vertex_out(slice_iface(ifaces));
      s.vert = common + glsl::stk_slice_vert;
      s.frag = common + glsl::stk_slice_frag;
      break;
    case Program::Volume:
      info.push_constant(Type::float4x4_t, "u_inv_proj");
      info.push_constant(Type::float4x4_t, "u_eye_to_index");
      info.push_constant(Type::float4_t, "u_vol");
      info.push_constant(Type::float4_t, "u_vol2");
      info.push_constant(Type::float4_t, "u_light");
      info.sampler(slot::lut, ImageType::Float3D, "s_vol");
      info.sampler(slot::tf, ImageType::Float2D, "s_tf");
      info.sampler(slot::depth, ImageType::Depth2D, "s_depth");
      info.vertex_out(volume_iface(ifaces));
      s.vert = glsl::stk_volume_vert;
      s.frag = glsl::stk_volume_frag;
      break;
    case Program::Count:
      break;
  }
  return s;
}

const char *program_name(const Program program)
{
  switch (program) {
    case Program::Mesh:
      return "stk_viewer_mesh";
    case Program::Glyph:
      return "stk_viewer_glyph";
    case Program::Line:
      return "stk_viewer_line";
    case Program::Point:
      return "stk_viewer_point";
    case Program::Slice:
      return "stk_viewer_slice";
    case Program::Volume:
      return "stk_viewer_volume";
    case Program::Count:
      break;
  }
  return "stk_viewer";
}

/**
 * GPU_shader_create_from_info_python without the draw colour-management library (not vendored):
 * our sources replace the runtime-generated `gpu_shader_python_{vert,frag}.glsl` placeholders
 * registered by the GPU module and go through the same source processor.
 */
gpu::Shader *compile(ShaderCreateInfo &info, const Sources &sources, std::string &r_error)
{
  info.builtins_ |= BuiltinBits::NO_BUFFER_TYPE_LINTING;
  info.builtins_ |= BuiltinBits::NO_PREPROCESSOR;
  info.generated_sources.append({"gpu_shader_python_typedef_lib.glsl", {}, "\n"});
  /* Resources are emitted by the backend as CREATE_INFO_RES_<frequency>_<info name> macros, which a
   * source expands where it wants them (Blender's shader_tool writes the same placeholder). */
  std::string resources = "\n";
  for (const char *freq : {"PASS", "BATCH", "GEOMETRY"}) {
    const std::string macro = std::string("CREATE_INFO_RES_") + freq + "_" + info.name_;
    resources += "#ifdef " + macro + "\n" + macro + "\n#endif\n";
  }
  auto preprocess = [&](const std::string &src) {
    std::string out = resources;
    out += GPU_shader_preprocess_source(src, info);
    return out;
  };
  const std::string vert = preprocess(sources.vert);
  const std::string frag = preprocess(sources.frag);
  info.vertex_source("gpu_shader_python_vert.glsl");
  info.generated_sources.append({"gpu_shader_python_vert.glsl", {"gpu_shader_python_typedef_lib.glsl"}, vert});
  info.fragment_source("gpu_shader_python_frag.glsl");
  info.generated_sources.append({"gpu_shader_python_frag.glsl", {"gpu_shader_python_typedef_lib.glsl"}, frag});
  char err[128] = "";
  if (!GPU_shader_create_info_check_error(reinterpret_cast<const GPUShaderCreateInfo *>(&info), err)) {
    r_error = err;
    return nullptr;
  }
  return GPU_shader_create_from_info(reinterpret_cast<const GPUShaderCreateInfo *>(&info));
}

}  // namespace

ShaderCache::~ShaderCache()
{
  clear();
}

void ShaderCache::clear()
{
  for (auto &pair : shaders_) {
    for (gpu::Shader *&shader : pair) {
      if (shader) {
        GPU_shader_free(shader);
        shader = nullptr;
      }
    }
  }
  for (auto &pair : failed_) {
    pair[0] = pair[1] = false;
  }
}

gpu::Shader *ShaderCache::get(const Program program, const bool id_pass)
{
  const int p = int(program), v = id_pass ? 1 : 0;
  if (shaders_[p][v] || failed_[p][v]) {
    return shaders_[p][v];
  }
  std::string name = std::string(program_name(program)) + (id_pass ? "_id" : "");
  Interfaces ifaces; /* outlives `info` (declared first) */
  ShaderCreateInfo info(name.c_str());
  const Sources sources = describe(program, id_pass, info, ifaces);
  std::string err;
  gpu::Shader *shader = compile(info, sources, err);
  if (!shader) {
    error_ = name + ": " + (err.empty() ? std::string("compilation failed (see the GPU log)") : err);
    failed_[p][v] = true;
    std::fprintf(stderr, "stk_viewer_gpu: %s\n", error_.c_str());
    return nullptr;
  }
  shaders_[p][v] = shader;
  return shader;
}

}  // namespace stk::viewer_gpu
