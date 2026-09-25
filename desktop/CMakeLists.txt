# SPDX-License-Identifier: GPL-2.0-or-later
#
# STK desktop engine (GPL-2.0-or-later). See desktop/README.md.

cmake_minimum_required(VERSION 3.24)
project(stk_desktop LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_OBJCXX_STANDARD 20)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type" FORCE)
endif()

option(STK_DESKTOP_WITH_BLENDER "Build the vendored Blender GHOST + GPU + BLF engine" ON)
option(STK_DESKTOP_BUILD_SPIKE "Build the Phase 0 GPU extraction spike" ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/sysroot/stk-sysroot.cmake")
  if(STK_SYSROOT_FOUND)
    message(STATUS "STK sysroot: ${STK_SYSROOT}")
  else()
    message(STATUS "STK sysroot not found at ${STK_SYSROOT}; using system packages")
  endif()
endif()

enable_testing()

if(STK_DESKTOP_WITH_BLENDER)
  add_subdirectory(engine/third_party/blender)
  if(STK_DESKTOP_BUILD_SPIKE)
    add_subdirectory(spike)
  endif()
endif()

# Engine libraries owned by other work packages plug in when present. The
# pure-CPU ones (stk_core, stk_io, stk_viewer_model) must build with
# STK_DESKTOP_WITH_BLENDER=OFF.
foreach(_lib stk_core stk_io stk_viewer_model stk_viewer_gpu stk_ui stk_wm stk_platform stk_bridge stk_app)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/engine/lib/${_lib}/CMakeLists.txt")
    add_subdirectory(engine/lib/${_lib})
  endif()
endforeach()

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/unit/CMakeLists.txt")
  add_subdirectory(tests/unit)
endif()
