# SPDX-License-Identifier: GPL-2.0-or-later
# stk_viewer_gpu tests (labels "viewer" and "gpu", once per GPU backend: Vulkan on Mesa lavapipe,
# OpenGL on llvmpipe through surfaceless EGL, Metal on macOS): render goldens of the spec example
# (directory and .stkp), the muferro-domains fixture and a coverage payload (SSIM >= 0.98), exact
# categorical colours, tiled x4 export vs single pass, picking (id buffer + float64 refinement at
# render_origin 1e6), timestep prefetch / camera / budget, LOD, the VTK cross-check (mask IoU >= 0.9)
# and a 1M-triangle performance smoke test (label "perf").
# Added from engine/lib/stk_viewer_gpu/CMakeLists.txt. Regenerate goldens (from Vulkan) with
# STK_UPDATE_GOLDENS=1; fixtures with fixtures/make_fixtures.py.

set(_stk_desktop_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
get_filename_component(_stk_desktop_dir ${_stk_desktop_dir} ABSOLUTE)
get_filename_component(_stk_repo_dir ${_stk_desktop_dir}/.. ABSOLUTE)

# googletest: same pinned tarball and FetchContent name as desktop/tests/unit and tests/ui (first
# declaration wins).
if(NOT TARGET GTest::gtest_main)
  if(STK_USE_SYSTEM_GTEST)
    find_package(GTest REQUIRED)
  else()
    include(FetchContent)
    set(_gtest_local "$ENV{HOME}/opt/stk-src/googletest-1.17.0.tar.gz")
    if(EXISTS "${_gtest_local}")
      set(_gtest_url "file://${_gtest_local}")
    else()
      set(_gtest_url "https://github.com/google/googletest/releases/download/v1.17.0/googletest-1.17.0.tar.gz")
    endif()
    set(STK_GTEST_URL "${_gtest_url}" CACHE STRING "googletest 1.17.0 source tarball (sha256-pinned)")
    FetchContent_Declare(googletest
      URL ${STK_GTEST_URL}
      URL_HASH SHA256=65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c
      DOWNLOAD_EXTRACT_TIMESTAMP ON)
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
    set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)
    if(NOT TARGET GTest::gtest_main)
      add_library(GTest::gtest_main ALIAS gtest_main)
    endif()
  endif()
endif()

add_executable(stk_viewer_gpu_tests main.cc support.cc test_viewer.cc)
target_link_libraries(stk_viewer_gpu_tests PRIVATE stk_viewer_gpu stk_gfx stk_io stk_core GTest::gtest)
target_compile_definitions(stk_viewer_gpu_tests PRIVATE
  STK_REPO_ROOT="${_stk_repo_dir}"
  STK_VIEWER_TEST_OUT="${CMAKE_CURRENT_BINARY_DIR}/out")
if(MSVC)
  target_compile_options(stk_viewer_gpu_tests PRIVATE /utf-8)
endif()
if(DEFINED STK_DESKTOP_BIN_DIR)
  set_target_properties(stk_viewer_gpu_tests PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
endif()

# Software rendering only, caches inside the build tree (as desktop/tests/wm).
set(STK_VIEWER_TEST_VK_ICD "/usr/share/vulkan/icd.d/lvp_icd.json" CACHE FILEPATH
    "Vulkan ICD of the viewer tests (default: Mesa lavapipe; empty = system default)")
set(_env "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless" "LIBGL_ALWAYS_SOFTWARE=1"
         "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache")
if(STK_VIEWER_TEST_VK_ICD AND EXISTS "${STK_VIEWER_TEST_VK_ICD}")
  list(APPEND _env "VK_DRIVER_FILES=${STK_VIEWER_TEST_VK_ICD}" "VK_ICD_FILENAMES=${STK_VIEWER_TEST_VK_ICD}")
endif()
if(STK_SYSROOT_FOUND)
  list(APPEND _env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()

set(_backends "")
if(STK_GPU_VULKAN)
  list(APPEND _backends vulkan)
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  list(APPEND _backends opengl)
endif()
if(STK_GPU_METAL)
  list(APPEND _backends metal)
endif()

set(_groups Golden Categorical Lut NonFinite Tiling Picking Steps Lod Viewport CrossCheck Perf)
foreach(_be ${_backends})
  foreach(_group ${_groups})
    set(_name viewer_${_be}_${_group})
    add_test(NAME ${_name}
      COMMAND stk_viewer_gpu_tests --gpu-backend ${_be} --gtest_filter=${_group}.*)
    set(_labels "viewer;gpu")
    if(_group STREQUAL "Perf")
      set(_labels "viewer;gpu;perf")
      # Timing needs the machine to itself (software rasterizers use every core).
      set_tests_properties(${_name} PROPERTIES RUN_SERIAL TRUE)
    endif()
    set_tests_properties(${_name} PROPERTIES
      LABELS "${_labels}" TIMEOUT 600 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env}"
      # A leak makes the process fail (guardedalloc's report).
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
  endforeach()
endforeach()

# stk-render smoke: export, tiling, picking and the benchmark path on the spec example.
foreach(_be ${_backends})
  add_test(NAME viewer_${_be}_stk_render
    COMMAND stk-render --gpu-backend ${_be} --payload ${_stk_repo_dir}/docs/specs/examples/payload-v2/example.stkp
            --export ${CMAKE_CURRENT_BINARY_DIR}/out/stk_render_${_be}.png --size 320x240 --scale 2 --tile 256
            --pick 160,120 --bench 2)
  set_tests_properties(viewer_${_be}_stk_render PROPERTIES
    LABELS "viewer;gpu" TIMEOUT 300 ENVIRONMENT "${_env}"
    PASS_REGULAR_EXPRESSION "\"hit\":true"
    FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|stk_viewer_gpu:")
endforeach()
