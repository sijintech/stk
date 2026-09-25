/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/gfx/gpu.hh"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <optional>
#include <vector>

#include "MEM_guardedalloc.h"

#include "CLG_log.h"

#include "BLI_threads.h"
#include "BLI_vector.hh"

#include "DNA_userdef_types.h"

#include "GHOST_IContext.hh"
#include "GHOST_ISystem.hh"

#include "GPU_context.hh"
#include "GPU_init_exit.hh"
#include "GPU_platform.hh"

#include "BLF_api.hh"

#include "IMB_imbuf.hh"

#include "stk/core/paths.hh"
#include "stk/gfx/image.hh"

namespace stk::gfx {

using namespace blender;

/* -------------------------------------------------------------------- */
/** \name Runtime
 * \{ */

static int g_runtime_count = 0;

Runtime::Runtime(const RuntimeOptions &options)
{
  if (g_runtime_count++ != 0) {
    fprintf(stderr, "stk::gfx::Runtime: constructed more than once\n");
    abort();
  }
  /* Same order as Blender's `main()`: allocator first, before anything allocates. */
  MEM_use_guarded_allocator();
  MEM_init_memleak_detection();
  if (options.fail_on_leak) {
    MEM_enable_fail_on_memleak();
  }
  CLG_init();
  BLI_threadapi_init();
}

Runtime::~Runtime()
{
  BLI_threadapi_exit();
  CLG_exit();
  g_runtime_count--;
}

unsigned int Runtime::memory_blocks_in_use()
{
  return MEM_get_memory_blocks_in_use();
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Backend selection
 * \{ */

const char *backend_id(const Backend backend)
{
  switch (backend) {
    case Backend::Auto:
      return "auto";
    case Backend::OpenGL:
      return "opengl";
    case Backend::Vulkan:
      return "vulkan";
    case Backend::Metal:
      return "metal";
  }
  return "?";
}

bool parse_backend(std::string_view text, Backend &r_backend)
{
  std::string s(text);
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return char(std::tolower(c)); });
  if (s == "auto") {
    r_backend = Backend::Auto;
  }
  else if (s == "opengl" || s == "gl") {
    r_backend = Backend::OpenGL;
  }
  else if (s == "vulkan" || s == "vk") {
    r_backend = Backend::Vulkan;
  }
  else if (s == "metal") {
    r_backend = Backend::Metal;
  }
  else {
    return false;
  }
  return true;
}

bool backend_compiled(const Backend backend)
{
  switch (backend) {
    case Backend::Auto:
      return true;
    case Backend::OpenGL:
#ifdef WITH_OPENGL_BACKEND
      return true;
#else
      return false;
#endif
    case Backend::Vulkan:
#ifdef WITH_VULKAN_BACKEND
      return true;
#else
      return false;
#endif
    case Backend::Metal:
#ifdef WITH_METAL_BACKEND
      return true;
#else
      return false;
#endif
  }
  return false;
}

Backend platform_default_backend()
{
#if defined(__APPLE__)
  return Backend::Metal;
#else
  return backend_compiled(Backend::OpenGL) ? Backend::OpenGL : Backend::Vulkan;
#endif
}

bool resolve_backend(std::string_view requested, Backend &r_backend, std::string &r_error)
{
  std::string_view source = "--gpu-backend";
  const std::optional<std::string> env = core::getenv_utf8("STK_GPU_BACKEND");
  if (requested.empty() && env && !env->empty()) {
    requested = *env;
    source = "$STK_GPU_BACKEND";
  }
  if (requested.empty()) {
    r_backend = platform_default_backend();
    return true;
  }
  Backend backend;
  if (!parse_backend(requested, backend)) {
    r_error = std::string(source) + ": unknown GPU backend '" + std::string(requested) +
              "' (expected auto, opengl, vulkan or metal)";
    return false;
  }
  if (!backend_compiled(backend)) {
    r_error = std::string(source) + ": GPU backend '" + backend_id(backend) +
              "' is not compiled into this build";
    return false;
  }
  r_backend = backend;
  return true;
}

static GPUBackendType to_gpu_backend(const Backend backend)
{
  switch (backend) {
    case Backend::OpenGL:
      return GPU_BACKEND_OPENGL;
    case Backend::Vulkan:
      return GPU_BACKEND_VULKAN;
    case Backend::Metal:
      return GPU_BACKEND_METAL;
    case Backend::Auto:
      break;
  }
  return GPU_BACKEND_NONE;
}

static GHOST_TDrawingContextType to_ghost_context_type(const Backend backend)
{
  switch (backend) {
#ifdef WITH_OPENGL_BACKEND
    case Backend::OpenGL:
      return GHOST_kDrawingContextTypeOpenGL;
#endif
#ifdef WITH_VULKAN_BACKEND
    case Backend::Vulkan:
      return GHOST_kDrawingContextTypeVulkan;
#endif
#if defined(__APPLE__) && defined(WITH_METAL_BACKEND)
    case Backend::Metal:
      return GHOST_kDrawingContextTypeMetal;
#endif
    default:
      break;
  }
  return GHOST_kDrawingContextTypeNone;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name IMB codec hook (GHOST clipboard / drag & drop images)
 * \{ */

static bool codec_decode(const unsigned char *mem, size_t size, uint8_t **r_rgba, int *r_w, int *r_h)
{
  Image img;
  std::string err;
  if (!png_decode(mem, size, img, err)) {
    return false;
  }
  /* ImBuf byte buffers are bottom-up. */
  const size_t stride = size_t(img.width) * 4;
  uint8_t *rgba = MEM_new_array_uninitialized<uint8_t>(stride * img.height, "stk png decode");
  for (int y = 0; y < img.height; y++) {
    memcpy(rgba + size_t(img.height - 1 - y) * stride, img.px(0, y), stride);
  }
  *r_rgba = rgba;
  *r_w = img.width;
  *r_h = img.height;
  return true;
}

static bool codec_encode_png(const uint8_t *rgba, int w, int h, Vector<uint8_t> &r_bytes)
{
  const size_t stride = size_t(w) * 4;
  std::vector<uint8_t> top_down(stride * h);
  for (int y = 0; y < h; y++) {
    memcpy(&top_down[size_t(h - 1 - y) * stride], rgba + size_t(y) * stride, stride);
  }
  std::vector<uint8_t> bytes;
  if (!png_encode(top_down.data(), w, h, bytes)) {
    return false;
  }
  r_bytes.clear();
  r_bytes.extend(Span<uint8_t>(bytes.data(), int64_t(bytes.size())));
  return true;
}

static const StkImbufCodec g_png_codec = {codec_decode, codec_encode_png};

/** \} */

/* -------------------------------------------------------------------- */
/** \name Gpu
 * \{ */

GHOST_ISystem *create_background_system(std::string &r_error)
{
  if (GHOST_ISystem::getSystem()) {
    r_error = "a GHOST system already exists";
    return nullptr;
  }
  if (GHOST_ISystem::createSystemBackground() != GHOST_kSuccess) {
    r_error = "GHOST_ISystem::createSystemBackground failed";
    return nullptr;
  }
  return GHOST_ISystem::getSystem();
}

void dispose_system()
{
  if (GHOST_ISystem::getSystem()) {
    GHOST_ISystem::disposeSystem();
  }
}

static GHOST_GPUSettings make_settings(const Backend backend, const bool debug)
{
  GHOST_GPUSettings settings = {0};
  settings.context_type = to_ghost_context_type(backend);
  settings.preferred_device = GPU_backend_preferred_device_get();
  if (debug) {
    settings.flags |= GHOST_gpuDebugContext;
  }
  return settings;
}

std::unique_ptr<Gpu> Gpu::create(GHOST_ISystem &system,
                                 const GpuOptions &options,
                                 std::string &r_error,
                                 const FirstContextFn &first_context)
{
  if (GPU_is_init()) {
    r_error = "the GPU module is already initialized";
    return nullptr;
  }
  std::unique_ptr<Gpu> gpu(new Gpu());
  gpu->system_ = &system;
  gpu->debug_ = options.debug;
  GPU_backend_ghost_system_set(&system);

  std::vector<Backend> candidates;
  if (options.backend == Backend::Auto) {
    candidates.push_back(platform_default_backend());
    for (const Backend b : {Backend::Metal, Backend::OpenGL, Backend::Vulkan}) {
      if (backend_compiled(b) && b != candidates.front()) {
        candidates.push_back(b);
      }
    }
  }
  else {
    candidates.push_back(options.backend);
  }

  std::string attempts;
  for (const Backend backend : candidates) {
    if (!backend_compiled(backend)) {
      attempts += std::string(" ") + backend_id(backend) + ": not compiled;";
      continue;
    }
    GPU_backend_type_selection_set(to_gpu_backend(backend));
    if (!GPU_backend_supported()) {
      attempts += std::string(" ") + backend_id(backend) + ": not supported;";
      continue;
    }
    if (first_context && !first_context(backend, make_settings(backend, options.debug))) {
      attempts += std::string(" ") + backend_id(backend) + ": window creation failed;";
      continue;
    }
    GHOST_IContext *ghost_ctx = system.createOffscreenContext(make_settings(backend, options.debug));
    if (!ghost_ctx) {
      attempts += std::string(" ") + backend_id(backend) + ": context creation failed;";
      if (first_context) {
        /* The window context of this backend already exists: no fallback possible. */
        break;
      }
      continue;
    }
    ghost_ctx->activateDrawingContext();
    gpu->ghost_context_ = ghost_ctx;
    gpu->gpu_context_ = GPU_context_create(nullptr, ghost_ctx);
    gpu->backend_ = backend;
    break;
  }
  if (!gpu->gpu_context_) {
    GPU_backend_type_selection_set(GPU_BACKEND_NONE);
    GPU_backend_ghost_system_set(nullptr);
    gpu->system_ = nullptr;
    r_error = "no usable GPU backend:" + attempts;
    return nullptr;
  }
  GPU_context_active_set(gpu->gpu_context_);
  GPU_init();

  stk_imbuf_set_codec(&g_png_codec);

  if (options.load_fonts) {
    BLF_init();
    std::string tried;
    const std::string datafiles = locate_datafiles(options.datafiles, &tried);
    if (datafiles.empty()) {
      r_error = "font data not found; tried:" + tried;
      return nullptr; /* The destructor unwinds GPU and BLF. */
    }
    if (!fonts_load(datafiles, gpu->fonts_, r_error)) {
      return nullptr;
    }
  }
  return gpu;
}

Gpu::~Gpu()
{
  if (!gpu_context_) {
    return;
  }
  activate_main();
  /* Blender's order: fonts, GPU module, context, GHOST context. */
  BLF_exit();
  stk_imbuf_set_codec(nullptr);
  GPU_exit();
  GPU_context_discard(gpu_context_);
  gpu_context_ = nullptr;
  system_->disposeContext(ghost_context_);
  ghost_context_ = nullptr;
  GPU_backend_type_selection_set(GPU_BACKEND_NONE);
  GPU_backend_ghost_system_set(nullptr);
}

const char *Gpu::backend_name() const
{
  return GPU_backend_get_name();
}

std::string Gpu::device_info() const
{
  auto s = [](const char *p) { return std::string(p ? p : "?"); };
  return s(GPU_platform_vendor()) + " | " + s(GPU_platform_renderer()) + " | " +
         s(GPU_platform_version());
}

GHOST_GPUSettings Gpu::window_settings() const
{
  return make_settings(backend_, debug_);
}

void Gpu::activate_main()
{
  ghost_context_->activateDrawingContext();
  GPU_context_active_set(gpu_context_);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name UI scale (mirrors WM_window_dpi_set_userdef)
 * \{ */

void set_ui_scale(float scale)
{
  if (!(scale > 0.0f) || !std::isfinite(scale)) {
    scale = 1.0f;
  }
  scale = std::clamp(scale, 0.25f, 8.0f);
  U.ui_scale = 1.0f;
  U.dpi = int(std::lround(72.0f * scale));
  const int pixelsize = std::max(1, U.dpi / 64);
  U.pixelsize = float(pixelsize);
  U.virtual_pixel = (pixelsize == 1) ? VIRTUAL_PIXEL_NATIVE : VIRTUAL_PIXEL_DOUBLE;
  /* Keep the exact (possibly fractional) scale instead of the rounded DPI. */
  U.scale_factor = scale;
  U.inv_scale_factor = 1.0f / scale;
  /* Widget unit is 20 pixels at 1x: 18 scaled units plus line-width borders. */
  U.widget_unit = short(std::lround(18.0f * scale) + 2 * pixelsize);
}

float ui_scale()
{
  return U.scale_factor > 0.0f ? U.scale_factor : 1.0f;
}

float ui_pixel_size()
{
  return U.pixelsize > 0.0f ? U.pixelsize : 1.0f;
}

/** \} */

}  // namespace stk::gfx
