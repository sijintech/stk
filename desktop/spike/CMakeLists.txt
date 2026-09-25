# SPDX-License-Identifier: GPL-2.0-or-later
#
# Phase 0 extraction spike: headless GHOST + GPU + BLF render to PNG with a golden check.

add_executable(stk-gpu-spike gpu_spike.cc)
# stk_gfx provides the PNG codec (moved there from the spike's png_min).
target_link_libraries(stk-gpu-spike PRIVATE stk_blender stk_gfx)
target_compile_features(stk-gpu-spike PRIVATE cxx_std_20)
target_compile_definitions(stk-gpu-spike PRIVATE STK_BLENDER_DATAFILES_DIR="${STK_BLENDER_DATAFILES}")

set(_golden "${CMAKE_CURRENT_SOURCE_DIR}/golden/gpu_spike.png")
set(STK_SPIKE_VK_ICD "/usr/share/vulkan/icd.d/lvp_icd.json" CACHE FILEPATH
    "Vulkan ICD used by the spike test (default: Mesa lavapipe)")

# Headless: never pick up a desktop session; software drivers only.
set(_env
  "DISPLAY="
  "WAYLAND_DISPLAY="
  "STK_BLENDER_DATAFILES=${STK_BLENDER_DATAFILES}"
  # Keep the Vulkan SPIR-V / pipeline caches inside the build tree.
  "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache"
)
if(STK_SYSROOT_FOUND)
  # epoxy dlopen()s libEGL.so.1, which only exists in the sysroot on this host.
  list(APPEND _env
    "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}"
    "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()

if(STK_GPU_VULKAN)
  add_test(NAME gpu_spike_vulkan
    COMMAND stk-gpu-spike --backend vulkan --out ${CMAKE_CURRENT_BINARY_DIR}/gpu_spike_vulkan.png
            --golden ${_golden})
  set_tests_properties(gpu_spike_vulkan PROPERTIES LABELS "gpu" TIMEOUT 300
    ENVIRONMENT "${_env};VK_DRIVER_FILES=${STK_SPIKE_VK_ICD};VK_ICD_FILENAMES=${STK_SPIKE_VK_ICD}")
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  add_test(NAME gpu_spike_opengl
    COMMAND stk-gpu-spike --backend opengl --out ${CMAKE_CURRENT_BINARY_DIR}/gpu_spike_opengl.png
            --golden ${_golden})
  set_tests_properties(gpu_spike_opengl PROPERTIES LABELS "gpu" TIMEOUT 300
    ENVIRONMENT "${_env};EGL_PLATFORM=surfaceless;LIBGL_ALWAYS_SOFTWARE=1")
endif()

# The guardedalloc leak check must be able to fail: leak on purpose; the detector aborts at exit,
# so the test passes only if the process does NOT exit cleanly.
if(UNIX)
  add_test(NAME gpu_spike_leak_selftest
    COMMAND sh -c "! \"$<TARGET_FILE:stk-gpu-spike>\" --leak-selftest 2>&1")
endif()
