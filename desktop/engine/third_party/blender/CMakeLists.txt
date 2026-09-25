# SPDX-License-Identifier: GPL-2.0-or-later
#
# Our own build of the vendored Blender subset (no upstream CMake):
#   host tools : datatoc, shader_tool (+ the glsl_to_c step)
#   libraries  : bf_intern_guardedalloc, bf_intern_clog, bf_blenlib (subset, no TBB/OIIO),
#                bf_gpu_shaders, bf_gpu (OpenGL/Vulkan; Metal on Apple), bf_intern_ghost
#                (X11/Wayland/headless; Cocoa on Apple; Win32 on Windows), bf_blenfont
#   shims      : stk_blender_shims (G, U, BKE_appdir, IMB, gpu_pass stubs, ...)
#   intern     : bf_intern_eigen (Blender's C API over header-only Eigen)
#
# Source lists are taken from the vendored tree (src/, upstream layout), which
# vendor.py already restricts to the whitelist in manifest.json.

set(BF "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(BF_SHIMS "${CMAKE_CURRENT_SOURCE_DIR}/shims")
set(BF_GEN "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(BF_GPU "${BF}/source/blender/gpu")
set(BF_GHOST "${BF}/intern/ghost")

if(NOT EXISTS "${BF_GPU}/GPU_context.hh")
  message(FATAL_ERROR "Vendored Blender sources missing: run engine/third_party/blender/vendor.py")
endif()

if(APPLE)
  # OBJCXX itself is enabled in desktop/CMakeLists.txt (the directory that links these libs).
  set(_gl_default OFF)
  set(_vk_default OFF)
  set(_mtl_default ON)
else()
  set(_gl_default ON)
  set(_vk_default ON)
  set(_mtl_default OFF)
endif()
option(STK_GPU_OPENGL "GPU module: OpenGL backend" ${_gl_default})
option(STK_GPU_VULKAN "GPU module: Vulkan backend" ${_vk_default})
option(STK_GPU_METAL "GPU module: Metal backend (Apple only)" ${_mtl_default})
if(UNIX AND NOT APPLE)
  option(STK_GHOST_X11 "GHOST: X11 back-end" ON)
  option(STK_GHOST_WAYLAND "GHOST: Wayland back-end" ON)
else()
  set(STK_GHOST_X11 OFF)
  set(STK_GHOST_WAYLAND OFF)
endif()
if(STK_GPU_METAL AND NOT APPLE)
  message(FATAL_ERROR "STK_GPU_METAL requires Apple")
endif()

# --------------------------------------------------------------------------------------------
# Dependencies

find_package(Threads REQUIRED)
find_package(Freetype REQUIRED)
find_package(ZLIB REQUIRED)
find_path(ZSTD_INCLUDE_DIR zstd.h REQUIRED)
find_library(ZSTD_LIBRARY NAMES zstd zstd_static libzstd REQUIRED)
find_path(FMT_INCLUDE_DIR fmt/format.h REQUIRED)
find_path(EIGEN3_INCLUDE_DIR Eigen/Core PATH_SUFFIXES eigen3 REQUIRED)
if(WIN32)
  # BLI_threads.h and the GPU module include <pthread.h> unconditionally (upstream: pthreads4w).
  find_package(PThreads4W REQUIRED)
endif()
if(STK_GPU_OPENGL OR WIN32)
  # Win32 GHOST includes <epoxy/wgl.h> even without the OpenGL backend.
  find_path(EPOXY_INCLUDE_DIR epoxy/gl.h REQUIRED)
  find_library(EPOXY_LIBRARY NAMES epoxy epoxy-0 REQUIRED)
endif()
if(STK_GPU_VULKAN)
  find_package(Vulkan REQUIRED)
  find_path(SHADERC_INCLUDE_DIR shaderc/shaderc.hpp HINTS ${Vulkan_INCLUDE_DIRS} REQUIRED)
  find_library(SHADERC_LIBRARY NAMES shaderc_shared shaderc shaderc_combined
               HINTS "$ENV{VULKAN_SDK}/lib" REQUIRED)
endif()
if(STK_GHOST_X11)
  find_package(X11 REQUIRED COMPONENTS Xi Xfixes Xrender Xxf86vm)
endif()
if(STK_GHOST_WAYLAND)
  find_path(WAYLAND_CLIENT_INCLUDE_DIR wayland-client.h REQUIRED)
  find_library(WAYLAND_CLIENT_LIBRARY wayland-client REQUIRED)
  find_library(WAYLAND_EGL_LIBRARY wayland-egl REQUIRED)
  find_library(WAYLAND_CURSOR_LIBRARY wayland-cursor REQUIRED)
  find_path(XKBCOMMON_INCLUDE_DIR xkbcommon/xkbcommon.h REQUIRED)
  find_library(XKBCOMMON_LIBRARY xkbcommon REQUIRED)
  find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
  find_path(WAYLAND_PROTOCOLS_DIR stable/xdg-shell/xdg-shell.xml
            PATH_SUFFIXES share/wayland-protocols REQUIRED)
endif()

# --------------------------------------------------------------------------------------------
# Common settings shared by every vendored target.

add_library(bf_common INTERFACE)
target_compile_features(bf_common INTERFACE cxx_std_20)
target_include_directories(bf_common INTERFACE
  "${BF_SHIMS}"
  "${BF}/source/blender/blenlib"
  "${BF}/source/blender/makesdna"
  "${BF}/source/blender/blenkernel"
  "${BF}/source/blender/editors/include"
  "${BF}/intern/guardedalloc"
  "${BF}/intern/clog"
  "${BF}/intern/atomic"
  "${BF}/intern/profile"
  "${BF}/extern/fast_float"
)
target_include_directories(bf_common SYSTEM INTERFACE "${FMT_INCLUDE_DIR}")
target_compile_definitions(bf_common INTERFACE
  __LITTLE_ENDIAN__
  FMT_HEADER_ONLY=1
  $<$<BOOL:${STK_GPU_OPENGL}>:WITH_OPENGL_BACKEND>
  $<$<BOOL:${STK_GPU_VULKAN}>:WITH_VULKAN_BACKEND>
  $<$<BOOL:${STK_GPU_METAL}>:WITH_METAL_BACKEND>
  # Debug builds abort on BLI_assert (as Blender developer builds do).
  $<$<CONFIG:Debug>:WITH_ASSERT_ABORT>
)
if(MSVC)
  target_compile_options(bf_common INTERFACE /J /bigobj /Zc:preprocessor /utf-8
    $<$<COMPILE_LANGUAGE:CXX>:/Zc:__cplusplus>)
  target_compile_definitions(bf_common INTERFACE
    WIN32 WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0603
    NOMINMAX _USE_MATH_DEFINES _CRT_SECURE_NO_DEPRECATE _CRT_NONSTDC_NO_DEPRECATE
    BLENDER_WIN_APPID="stk.desktop" BLENDER_WIN_APPID_FRIENDLY_NAME="STK Desktop")
else()
  target_compile_options(bf_common INTERFACE
    -funsigned-char -fno-strict-aliasing -ffp-contract=off)
  target_compile_definitions(bf_common INTERFACE
    _LARGEFILE_SOURCE _FILE_OFFSET_BITS=64 _LARGEFILE64_SOURCE)
endif()
target_link_libraries(bf_common INTERFACE Threads::Threads ${CMAKE_DL_LIBS})
if(WIN32)
  target_link_libraries(bf_common INTERFACE PThreads4W::PThreads4W)
endif()

function(bf_add_lib name)
  add_library(${name} STATIC ${ARGN})
  target_link_libraries(${name} PUBLIC bf_common)
  # Upstream code is not ours to fix: no warnings for the vendored libraries themselves (PRIVATE,
  # so the engine's own targets that include these headers keep their warnings).
  target_compile_options(${name} PRIVATE $<IF:$<BOOL:${MSVC}>,/w,-w>)
endfunction()

# --------------------------------------------------------------------------------------------
# intern + extern helpers

bf_add_lib(bf_intern_guardedalloc
  ${BF}/intern/guardedalloc/intern/leak_detector.cc
  ${BF}/intern/guardedalloc/intern/mallocn.cc
  ${BF}/intern/guardedalloc/intern/mallocn_guarded_impl.cc
  ${BF}/intern/guardedalloc/intern/mallocn_lockfree_impl.cc
  ${BF}/intern/guardedalloc/intern/memory_usage.cc
)

bf_add_lib(bf_intern_clog ${BF}/intern/clog/clog.cc)
target_compile_definitions(bf_intern_clog PRIVATE WITH_CLOG_PTHREADS)
target_link_libraries(bf_intern_clog PUBLIC bf_intern_guardedalloc)

bf_add_lib(extern_xxhash ${BF}/extern/xxhash/xxhash.c)
target_include_directories(extern_xxhash PUBLIC ${BF}/extern/xxhash)

bf_add_lib(extern_wcwidth ${BF}/extern/wcwidth/wcwidth.c)
target_include_directories(extern_wcwidth PUBLIC ${BF}/extern/wcwidth)

if(WIN32)
  bf_add_lib(bf_intern_utfconv ${BF}/intern/utfconv/utfconv.cc ${BF}/intern/utfconv/utf_winfunc.cc)
  target_include_directories(bf_intern_utfconv PUBLIC ${BF}/intern/utfconv)
  bf_add_lib(bf_intern_uriconvert ${BF}/intern/uriconvert/uri_convert.cc)
  target_include_directories(bf_intern_uriconvert PUBLIC ${BF}/intern/uriconvert)
endif()

if(STK_GPU_VULKAN)
  bf_add_lib(extern_vulkan_memory_allocator ${BF}/extern/vulkan_memory_allocator/vk_mem_alloc_impl.cc)
  target_include_directories(extern_vulkan_memory_allocator SYSTEM PUBLIC
    ${BF}/extern/vulkan_memory_allocator ${Vulkan_INCLUDE_DIRS})
endif()

bf_add_lib(bf_intern_eigen
  ${BF}/intern/eigen/intern/eigenvalues.cc ${BF}/intern/eigen/intern/linear_solver.cc
  ${BF}/intern/eigen/intern/matrix.cc ${BF}/intern/eigen/intern/svd.cc)
target_include_directories(bf_intern_eigen PUBLIC ${BF}/intern/eigen)
target_include_directories(bf_intern_eigen SYSTEM PUBLIC ${EIGEN3_INCLUDE_DIR})
target_compile_definitions(bf_intern_eigen PUBLIC EIGEN_MALLOC_ALREADY_ALIGNED=0)

# --------------------------------------------------------------------------------------------
# blenlib subset (see manifest.json "files")

set(BLI "${BF}/source/blender/blenlib/intern")
file(GLOB BLENLIB_SRC CONFIGURE_DEPENDS "${BLI}/*.cc")
list(FILTER BLENLIB_SRC EXCLUDE REGEX "/(winstuff|winstuff_dir|system_win32)\\.cc$")
# The math *_inline.cc files are headers (#pragma once, included by BLI_math_*.h through
# BLI_MATH_DO_INLINE); upstream marks them HEADER_FILE_ONLY. GCC honours #pragma once in the main
# file and skips the re-include, Clang/MSVC do not and report redefinitions.
list(FILTER BLENLIB_SRC EXCLUDE REGEX "/math_[a-z_]+_inline\\.cc$")
if(WIN32)
  list(APPEND BLENLIB_SRC ${BLI}/winstuff.cc ${BLI}/winstuff_dir.cc ${BLI}/winstuff_registration.cc
    ${BLI}/system_win32.cc)
endif()
if(APPLE)
  list(APPEND BLENLIB_SRC ${BLI}/fileops_apple.mm ${BLI}/storage_apple.mm)
endif()
bf_add_lib(bf_blenlib ${BLENLIB_SRC})
target_include_directories(bf_blenlib SYSTEM PRIVATE ${ZSTD_INCLUDE_DIR})
target_link_libraries(bf_blenlib PUBLIC bf_intern_guardedalloc bf_intern_clog bf_intern_eigen
  extern_xxhash extern_wcwidth
  ZLIB::ZLIB ${ZSTD_LIBRARY})
if(WIN32)
  target_link_libraries(bf_blenlib PUBLIC bf_intern_utfconv bf_intern_uriconvert dbghelp shlwapi
    comctl32 dxgi)
elseif(APPLE)
  target_link_libraries(bf_blenlib PUBLIC "-framework Foundation")
endif()

# --------------------------------------------------------------------------------------------
# STK shims (G, U, BKE_appdir, BKE_material, UI theme, IMB, gpu_pass)

bf_add_lib(stk_blender_shims ${BF_SHIMS}/stk_blender_shims.cc)
target_include_directories(stk_blender_shims PRIVATE ${BF_GPU})
target_compile_definitions(stk_blender_shims PRIVATE
  STK_BLENDER_DATAFILES_DIR="${BF}/release/datafiles")
target_link_libraries(stk_blender_shims PUBLIC bf_blenlib)

# --------------------------------------------------------------------------------------------
# Host tools: datatoc + shader_tool

add_executable(datatoc ${BF}/source/blender/datatoc/datatoc.cc)
target_compile_features(datatoc PRIVATE cxx_std_20)
if(MSVC)
  # Upstream applies these globally; the host tools do not link bf_common.
  set(_bf_host_msvc_flags /utf-8 /bigobj /Zc:__cplusplus /Zc:preprocessor)
  target_compile_options(datatoc PRIVATE ${_bf_host_msvc_flags})
endif()

file(GLOB SHADER_TOOL_SRC CONFIGURE_DEPENDS "${BF_GPU}/shader_tool/*.cc")
list(APPEND SHADER_TOOL_SRC ${BF_GPU}/shader_tool/lexit/lexit.cc)
add_executable(shader_tool ${SHADER_TOOL_SRC})
target_compile_features(shader_tool PRIVATE cxx_std_20)
if(MSVC)
  target_compile_options(shader_tool PRIVATE ${_bf_host_msvc_flags} /w)
else()
  target_compile_options(shader_tool PRIVATE -w)
endif()
list(FILTER SHADER_TOOL_SRC EXCLUDE REGEX "/shader_tool\\.cc$")  # Library part for bf_gpu.

# --------------------------------------------------------------------------------------------
# GLSL -> C (port of upstream glsl_to_c: shader_tool then datatoc)

include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/gpu_glsl_sources.cmake)

set(GLSL_SRC ${STK_GPU_GLSL_SRC})
if(STK_GPU_VULKAN)
  list(APPEND GLSL_SRC ${STK_GPU_VULKAN_BACKEND_GLSL_SRC})
endif()
if(STK_GPU_METAL)
  list(APPEND GLSL_SRC ${STK_GPU_MTL_BACKEND_GLSL_SRC})
endif()
set(GLSL_INC . intern shaders shaders/common shaders/infos shaders/material vulkan/shaders)
set(_glsl_inc_abs "")
foreach(_inc ${GLSL_INC})
  list(APPEND _glsl_inc_abs "${BF_GPU}/${_inc}")
endforeach()

set(GPU_GEN "${BF_GEN}/gpu")
set(SHADER_C "")
set(_src_list "")
set(_meta_list "")
set(_info_list "")
foreach(_f ${GLSL_SRC})
  set(_in "${BF_GPU}/${_f}")
  set(_tmp "${GPU_GEN}/${_f}.tmp")
  set(_out "${GPU_GEN}/${_f}.c")
  add_custom_command(
    OUTPUT ${_tmp} ${GPU_GEN}/${_f}.hh ${GPU_GEN}/${_f}.info ${GPU_GEN}/${_f}.d
    DEPFILE ${GPU_GEN}/${_f}.d
    COMMAND shader_tool ${_in} ${_tmp} ${GPU_GEN}/${_f}.hh ${GPU_GEN}/${_f}.info ${GPU_GEN}/${_f}.d ${_glsl_inc_abs}
    DEPENDS ${_in} shader_tool
    COMMENT "shader_tool ${_f}")
  add_custom_command(
    OUTPUT ${_out}
    COMMAND datatoc ${_tmp} ${_out}
    DEPENDS ${_tmp} datatoc)
  list(APPEND SHADER_C ${_out})
  get_filename_component(_name ${_f} NAME)
  string(REPLACE "." "_" _sym "${_name}")
  string(APPEND _src_list "SHADER_SOURCE(${_sym}_tmp, \"${_name}\", \"${_f}\")\n")
  string(APPEND _meta_list "#include \"${_f}.hh\"\n")
  string(APPEND _info_list "#include \"${_f}.info\"\n")
endforeach()
if(STK_GPU_METAL)
  foreach(_f ${STK_GPU_MSL_SRC})
    add_custom_command(OUTPUT ${GPU_GEN}/${_f}.c
      COMMAND datatoc ${BF_GPU}/${_f} ${GPU_GEN}/${_f}.c
      DEPENDS ${BF_GPU}/${_f} datatoc)
    list(APPEND SHADER_C ${GPU_GEN}/${_f}.c)
  endforeach()
endif()
file(GENERATE OUTPUT ${GPU_GEN}/glsl_gpu_source_list.h CONTENT "${_src_list}")
file(GENERATE OUTPUT ${GPU_GEN}/glsl_gpu_metadata_list.hh CONTENT "${_meta_list}")
file(GENERATE OUTPUT ${GPU_GEN}/glsl_gpu_infos_list.hh CONTENT "${_info_list}")

# Shim: the draw, compositor and OCIO shader libraries are not vendored.
foreach(_mod draw compositor ocio)
  file(GENERATE OUTPUT ${GPU_GEN}/glsl_${_mod}_source_list.h CONTENT "/* STK: no ${_mod} shaders. */\n")
  file(GENERATE OUTPUT ${GPU_GEN}/glsl_${_mod}_metadata_list.hh CONTENT "/* STK: no ${_mod} shaders. */\n")
endforeach()
file(GENERATE OUTPUT ${GPU_GEN}/glsl_compositor_infos_list.hh CONTENT "/* STK: no compositor shaders. */\n")
file(GENERATE OUTPUT ${GPU_GEN}/glsl_ocio_infos_list.hh CONTENT "/* STK: no OCIO shaders. */\n")
# init_draw_infos() amends `eevee_deferred_tile_classify` for a Qualcomm workaround: give it a
# local, unregistered placeholder so the upstream function compiles unchanged.
file(GENERATE OUTPUT ${GPU_GEN}/glsl_draw_infos_list.hh CONTENT
  "/* STK: no draw shaders. Placeholder for the Qualcomm workaround in init_draw_infos(). */\nShaderCreateInfo eevee_deferred_tile_classify(\"eevee_deferred_tile_classify\");\n")

add_library(bf_gpu_shaders STATIC ${SHADER_C})
set_target_properties(bf_gpu_shaders PROPERTIES LINKER_LANGUAGE C)

# --------------------------------------------------------------------------------------------
# bf_gpu

file(GLOB GPU_SRC CONFIGURE_DEPENDS "${BF_GPU}/intern/*.cc")
list(FILTER GPU_SRC EXCLUDE REGEX "/gpu_shader_info_baked\\.cc$")
list(APPEND GPU_SRC ${SHADER_TOOL_SRC})
if(STK_GPU_OPENGL)
  file(GLOB _gl CONFIGURE_DEPENDS "${BF_GPU}/opengl/*.cc")
  list(APPEND GPU_SRC ${_gl})
endif()
if(STK_GPU_VULKAN)
  file(GLOB _vk CONFIGURE_DEPENDS
    "${BF_GPU}/vulkan/*.cc" "${BF_GPU}/vulkan/render_graph/*.cc" "${BF_GPU}/vulkan/render_graph/nodes/*.cc")
  list(APPEND GPU_SRC ${_vk})
endif()
if(STK_GPU_METAL)
  file(GLOB _mtl CONFIGURE_DEPENDS "${BF_GPU}/metal/*.mm" "${BF_GPU}/metal/*.cc")
  list(APPEND GPU_SRC ${_mtl})
endif()

bf_add_lib(bf_gpu ${GPU_SRC})
if(NOT STK_GPU_VULKAN)
  # gpu_context.cc uses blender::Mutex without including BLI_mutex.hh; upstream gets it through
  # vk_backend.hh (every upstream Windows/Linux build has Vulkan). Provide it without a patch.
  if(MSVC)
    set(_force_mutex /FIBLI_mutex.hh)
  else()
    set(_force_mutex -include BLI_mutex.hh)
  endif()
  set_property(SOURCE ${BF_GPU}/intern/gpu_context.cc APPEND PROPERTY COMPILE_OPTIONS ${_force_mutex})
endif()
target_include_directories(bf_gpu
  PUBLIC ${BF_GPU}
  PRIVATE
    ${BF_GPU}/intern ${BF_GPU}/dummy ${BF_GPU}/opengl ${BF_GPU}/vulkan ${BF_GPU}/metal
    ${BF_GPU}/metal/kernels ${BF_GPU}/vulkan/shaders ${BF_GPU}/shaders/infos ${BF_GPU}/shaders/common
    ${BF_GPU}/shaders ${GPU_GEN} ${BF_GHOST})
target_link_libraries(bf_gpu PUBLIC bf_blenlib bf_gpu_shaders stk_blender_shims)
if(STK_GPU_OPENGL)
  target_include_directories(bf_gpu SYSTEM PUBLIC ${EPOXY_INCLUDE_DIR})
  target_link_libraries(bf_gpu PUBLIC ${EPOXY_LIBRARY})
endif()
if(STK_GPU_VULKAN)
  target_include_directories(bf_gpu SYSTEM PRIVATE ${SHADERC_INCLUDE_DIR})
  target_link_libraries(bf_gpu PUBLIC Vulkan::Vulkan ${SHADERC_LIBRARY} extern_vulkan_memory_allocator)
endif()
if(STK_GPU_METAL)
  target_link_libraries(bf_gpu PUBLIC "-framework Metal" "-framework QuartzCore" "-framework Foundation")
endif()

# --------------------------------------------------------------------------------------------
# bf_intern_ghost

set(GHOST_SRC
  intern/GHOST_Buttons.cc intern/GHOST_CallbackEventConsumer.cc intern/GHOST_Context.cc
  intern/GHOST_ContextNone.cc intern/GHOST_EventManager.cc intern/GHOST_ISystem.cc
  intern/GHOST_ISystemPaths.cc intern/GHOST_ModifierKeys.cc intern/GHOST_PathUtils.cc
  intern/GHOST_Rect.cc intern/GHOST_System.cc intern/GHOST_TimerManager.cc intern/GHOST_Window.cc
  intern/GHOST_WindowManager.cc)
set(GHOST_DEFS "")
set(GHOST_LIBS "")
if(STK_GPU_VULKAN)
  list(APPEND GHOST_SRC intern/GHOST_ContextVK.cc)
  list(APPEND GHOST_LIBS Vulkan::Vulkan extern_vulkan_memory_allocator)
endif()
if(STK_GPU_OPENGL)
  list(APPEND GHOST_LIBS ${EPOXY_LIBRARY})
endif()
if(APPLE)
  list(APPEND GHOST_SRC intern/GHOST_SystemCocoa.mm intern/GHOST_WindowCocoa.mm
    intern/GHOST_SystemPathsCocoa.mm)
  if(STK_GPU_METAL)
    list(APPEND GHOST_SRC intern/GHOST_ContextMTL.mm)
  endif()
  list(APPEND GHOST_LIBS "-framework CoreServices" "-framework Foundation" "-framework IOKit"
    "-framework AppKit" "-framework Cocoa" "-framework Carbon" "-framework Metal" "-framework QuartzCore")
elseif(WIN32)
  list(APPEND GHOST_SRC intern/GHOST_ContextD3D.cc intern/GHOST_DropTargetWin32.cc
    intern/GHOST_SystemWin32.cc intern/GHOST_TrackpadWin32.cc intern/GHOST_WindowWin32.cc
    intern/GHOST_Wintab.cc intern/GHOST_ContextWGL.cc intern/GHOST_ImeWin32.cc
    intern/GHOST_SystemPathsWin32.cc)
  list(APPEND GHOST_LIBS bf_intern_utfconv dwmapi imm32 shcore dxgi d3d11 opengl32 version comctl32
    ${EPOXY_LIBRARY})
  set(GHOST_EXTRA_INC ${BF}/extern/wintab/include)
else()
  list(APPEND GHOST_SRC intern/GHOST_SystemPathsUnix.cc)
  if(STK_GPU_OPENGL)
    list(APPEND GHOST_SRC intern/GHOST_ContextEGL.cc)
  endif()
  if(STK_GHOST_X11)
    list(APPEND GHOST_SRC intern/GHOST_SystemX11.cc intern/GHOST_WindowX11.cc intern/GHOST_DropTargetX11.cc)
    if(STK_GPU_OPENGL)
      list(APPEND GHOST_SRC intern/GHOST_ContextGLX.cc)
    endif()
    list(APPEND GHOST_DEFS WITH_GHOST_X11 WITH_X11_XINPUT WITH_X11_XFIXES WITH_XDND)
    if(EXISTS "${X11_INCLUDE_DIR}/X11/XF86keysym.h")
      list(APPEND GHOST_DEFS WITH_XF86KEYSYM)
    endif()
    bf_add_lib(extern_xdnd ${BF}/extern/xdnd/xdnd.c)
    target_compile_definitions(extern_xdnd PRIVATE HAVE_SYS_TIME_H)
    target_include_directories(extern_xdnd PUBLIC ${BF}/extern/xdnd)
    target_link_libraries(extern_xdnd PUBLIC X11::X11)
    list(APPEND GHOST_LIBS extern_xdnd X11::X11 X11::Xi X11::Xfixes X11::Xrender X11::Xxf86vm)
  endif()
  if(STK_GHOST_WAYLAND)
    list(APPEND GHOST_SRC intern/GHOST_SystemWayland.cc intern/GHOST_WindowWayland.cc
      intern/GHOST_WindowWaylandCSD.cc)
    list(APPEND GHOST_DEFS WITH_GHOST_WAYLAND WITH_GHOST_CSD HAVE_MEMFD_CREATE HAVE_POLL
      WITH_GHOST_WAYLAND_APP_ID=stk-desktop)
    list(APPEND GHOST_LIBS ${WAYLAND_CLIENT_LIBRARY} ${WAYLAND_EGL_LIBRARY} ${WAYLAND_CURSOR_LIBRARY}
      ${XKBCOMMON_LIBRARY})
    set(_wl "${BF_GEN}/libwayland")
    foreach(_xml
        stable/xdg-shell/xdg-shell.xml
        unstable/xdg-decoration/xdg-decoration-unstable-v1.xml
        unstable/xdg-output/xdg-output-unstable-v1.xml
        staging/xdg-activation/xdg-activation-v1.xml
        staging/fractional-scale/fractional-scale-v1.xml
        stable/viewporter/viewporter.xml
        staging/color-management/color-management-v1.xml
        unstable/pointer-constraints/pointer-constraints-unstable-v1.xml
        unstable/relative-pointer/relative-pointer-unstable-v1.xml
        unstable/pointer-gestures/pointer-gestures-unstable-v1.xml
        stable/tablet/tablet-v2.xml
        unstable/primary-selection/primary-selection-unstable-v1.xml
        unstable/text-input/text-input-unstable-v3.xml
        staging/cursor-shape/cursor-shape-v1.xml
        staging/xdg-toplevel-icon/xdg-toplevel-icon-v1.xml)
      get_filename_component(_n ${_xml} NAME_WLE)
      add_custom_command(OUTPUT ${_wl}/${_n}-client-protocol.h ${_wl}/${_n}-client-protocol.c
        COMMAND ${CMAKE_COMMAND} -E make_directory ${_wl}
        COMMAND ${WAYLAND_SCANNER} client-header ${WAYLAND_PROTOCOLS_DIR}/${_xml} ${_wl}/${_n}-client-protocol.h
        COMMAND ${WAYLAND_SCANNER} private-code ${WAYLAND_PROTOCOLS_DIR}/${_xml} ${_wl}/${_n}-client-protocol.c
        DEPENDS ${WAYLAND_PROTOCOLS_DIR}/${_xml})
      list(APPEND GHOST_GEN_SRC ${_wl}/${_n}-client-protocol.c ${_wl}/${_n}-client-protocol.h)
    endforeach()
  endif()
endif()
list(TRANSFORM GHOST_SRC PREPEND "${BF_GHOST}/")
bf_add_lib(bf_intern_ghost ${GHOST_SRC} ${GHOST_GEN_SRC})
target_include_directories(bf_intern_ghost PUBLIC ${BF_GHOST} PRIVATE ${BF_GPU} ${GHOST_EXTRA_INC})
target_compile_definitions(bf_intern_ghost PRIVATE ${GHOST_DEFS})
# Public: it changes the GHOST_IWindow interface (beginIME / endIME) that stk_wm calls.
target_compile_definitions(bf_intern_ghost PUBLIC WITH_INPUT_IME)
target_link_libraries(bf_intern_ghost PUBLIC bf_blenlib stk_blender_shims ${GHOST_LIBS})
if(STK_GPU_OPENGL OR WIN32)
  target_include_directories(bf_intern_ghost SYSTEM PRIVATE ${EPOXY_INCLUDE_DIR})
endif()
if(STK_GHOST_WAYLAND)
  target_include_directories(bf_intern_ghost SYSTEM PRIVATE
    ${_wl} ${WAYLAND_CLIENT_INCLUDE_DIR} ${XKBCOMMON_INCLUDE_DIR})
endif()
target_link_libraries(bf_gpu PUBLIC bf_intern_ghost)

# --------------------------------------------------------------------------------------------
# bf_blenfont (no SVG icons: WITH_HEADLESS only affects the icon code in BLF)

file(GLOB BLF_SRC CONFIGURE_DEPENDS "${BF}/source/blender/blenfont/intern/*.cc")
list(FILTER BLF_SRC EXCLUDE REGEX "/blf_font_win32_compat\\.cc$")
if(WIN32)
  list(APPEND BLF_SRC ${BF}/source/blender/blenfont/intern/blf_font_win32_compat.cc)
endif()
bf_add_lib(bf_blenfont ${BLF_SRC})
target_include_directories(bf_blenfont PUBLIC ${BF}/source/blender/blenfont)
target_compile_definitions(bf_blenfont PRIVATE WITH_HEADLESS)
target_link_libraries(bf_blenfont PUBLIC bf_gpu bf_blenlib Freetype::Freetype stk_blender_shims)

# Everything the engine needs, as one link target.
add_library(stk_blender INTERFACE)
target_link_libraries(stk_blender INTERFACE bf_blenfont bf_gpu bf_intern_ghost bf_blenlib stk_blender_shims)
if(WIN32)
  # Every executable linking the engine gets the application manifest (Common Controls 6, UTF-8
  # code page), as upstream embeds blender.exe.manifest.
  target_sources(stk_blender INTERFACE "${PROJECT_SOURCE_DIR}/cmake/windows/stk-desktop.manifest")
endif()
set(STK_BLENDER_DATAFILES "${BF}/release/datafiles" CACHE INTERNAL "Vendored Blender datafiles (fonts)")
