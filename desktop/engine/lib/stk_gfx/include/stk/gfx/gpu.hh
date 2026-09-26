/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Engine bootstrap on the vendored Blender GPU module: process runtime (guarded allocator with
 * leak detection, logging, threads), GPU backend selection, the main GPU context, the font stack
 * and the global UI scale.
 *
 * Typical use (see desktop/app/main.cc):
 *
 *   stk::gfx::Runtime runtime;                          // first thing in main()
 *   GHOST_ISystem *system = ...;                        // stk_wm (GUI) or create_background_system()
 *   auto gpu = stk::gfx::Gpu::create(*system, opts, err);
 *   ... draw ...
 *   gpu.reset();                                        // after all windows are gone
 *
 * Only this library, stk_wm, ui_gpu and stk_viewer_gpu include Blender headers; everything in
 * this header is plain C++ apart from the opaque GHOST / GPU forward declarations.
 */
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>

#include "stk/gfx/fonts.hh"

class GHOST_ISystem;
class GHOST_IContext;
struct GHOST_GPUSettings;
namespace blender {
struct GPUContext;
}

namespace stk::gfx {

/* -------------------------------------------------------------------- */
/** \name Process runtime
 * \{ */

struct RuntimeOptions {
  /** Abort at exit when guardedalloc blocks leak (Blender's `--debug-memory` behavior). */
  bool fail_on_leak = true;
};

/**
 * Process-wide bootstrap of the vendored Blender runtime: guarded allocator with leak detection,
 * CLOG and the thread API. Construct exactly one, first in `main()`, before any other engine call;
 * it must outlive every other engine object.
 */
class Runtime {
 public:
  explicit Runtime(const RuntimeOptions &options = {});
  ~Runtime();
  Runtime(const Runtime &) = delete;
  Runtime &operator=(const Runtime &) = delete;

  /** Number of guardedalloc blocks currently allocated (0 at a clean shutdown). */
  static unsigned int memory_blocks_in_use();
};

/** \} */

/* -------------------------------------------------------------------- */
/** \name Backend selection
 * \{ */

enum class Backend { Auto, OpenGL, Vulkan, Metal };

/** "auto", "opengl", "vulkan", "metal". */
const char *backend_id(Backend backend);
/** Accepts the ids above plus "gl" and "vk" (case-insensitive). */
bool parse_backend(std::string_view text, Backend &r_backend);
/** Compiled into this build (Auto is always true). */
bool backend_compiled(Backend backend);
/** OpenGL on Linux and Windows, Metal on macOS. */
Backend platform_default_backend();
/**
 * Resolves the requested backend: `requested` (e.g. `--gpu-backend`) when not empty, else
 * `$STK_GPU_BACKEND`, else #platform_default_backend. Fails for unknown or uncompiled backends.
 * `Auto` is kept as is and means "first backend that initializes" (see #Gpu::create).
 */
bool resolve_backend(std::string_view requested, Backend &r_backend, std::string &r_error);

/** \} */

/* -------------------------------------------------------------------- */
/** \name GPU module + main context
 * \{ */

struct GpuOptions {
  Backend backend = Backend::Auto;
  /** Datafiles root override (see #locate_datafiles); empty = automatic. */
  std::string datafiles;
  bool load_fonts = true;
  /** Request debug GPU contexts (validation layers / KHR_debug). */
  bool debug = false;
};

/**
 * The GPU module bound to a GHOST system. Owns the main offscreen GPU context (used for resource
 * creation and headless rendering; window contexts share its resources) and the font stack.
 *
 * Destroy it after every window context has been discarded and before disposing the GHOST
 * system. Not thread-safe: use from the main thread only.
 */
class Gpu {
 public:
  /**
   * Called once the backend is selected and before the main context exists, to create the
   * first window and its GPU context with `settings`. Returning false tries the next backend.
   * Needed because the first GPU context decides process-wide state (e.g. the Vulkan instance
   * only enables window-surface extensions when the first context has a window, as in
   * Blender, which also creates its windows before the offscreen context).
   */
  using FirstContextFn = std::function<bool(Backend backend, const GHOST_GPUSettings &settings)>;

  /**
   * Binds the GPU module to `system`, selects the backend (for `Auto`: the platform default
   * first, then the others that are compiled in), runs `first_context` (GUI), creates the main
   * offscreen context, runs `GPU_init()` and loads the fonts. Leaves the main context active.
   */
  static std::unique_ptr<Gpu> create(GHOST_ISystem &system,
                                     const GpuOptions &options,
                                     std::string &r_error,
                                     const FirstContextFn &first_context = {});
  ~Gpu();
  Gpu(const Gpu &) = delete;
  Gpu &operator=(const Gpu &) = delete;

  /** The backend actually in use (never Auto). */
  Backend backend() const
  {
    return backend_;
  }
  /** "OpenGL" / "Vulkan" / "Metal". */
  const char *backend_name() const;
  /** "vendor | renderer | version" of the active device. */
  std::string device_info() const;

  /** GHOST settings for creating a window that matches this backend. */
  GHOST_GPUSettings window_settings() const;

  /** Makes the main offscreen context current (GHOST and GPU module). */
  void activate_main();
  blender::GPUContext *main_context() const
  {
    return gpu_context_;
  }
  GHOST_ISystem &system() const
  {
    return *system_;
  }

  const FontStack &fonts() const
  {
    return fonts_;
  }

 private:
  Gpu() = default;

  GHOST_ISystem *system_ = nullptr;
  GHOST_IContext *ghost_context_ = nullptr;
  blender::GPUContext *gpu_context_ = nullptr;
  Backend backend_ = Backend::Auto;
  bool debug_ = false;
  FontStack fonts_;
};

/**
 * Creates the GHOST system for headless use: an off-screen capable display system when one is
 * reachable, otherwise GHOST's headless system (EGL surfaceless / headless Vulkan).
 * Returns nullptr on failure. Dispose with #dispose_system.
 */
GHOST_ISystem *create_background_system(std::string &r_error);
void dispose_system();

/** \} */

/* -------------------------------------------------------------------- */
/** \name UI scale
 * \{ */

/**
 * Sets Blender's global UI scale (`U.dpi`, `U.scale_factor`, `U.pixelsize`),
 * which the GPU module and BLF read. `scale` = native DPI factor x user scale (1.0 = 96 DPI).
 * Call before drawing a window whose scale differs from the previous one.
 */
void set_ui_scale(float scale);
float ui_scale();
/** Line width in pixels for the current UI scale (Blender's `U.pixelsize`). */
float ui_pixel_size();

/** \} */

}  // namespace stk::gfx
