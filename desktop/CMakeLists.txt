# SPDX-License-Identifier: GPL-2.0-or-later
#
# STK desktop engine (GPL-2.0-or-later). See desktop/README.md.

cmake_minimum_required(VERSION 3.24)
# Minimum macOS; must be set before project(). Blender 5.2 itself needs 11.2, but stk_core uses
# std::format, whose floating-point support in libc++ (std::to_chars) needs macOS 13.3.
set(CMAKE_OSX_DEPLOYMENT_TARGET "13.3" CACHE STRING "Minimum macOS version")
project(stk_desktop VERSION 0.1.0 LANGUAGES C CXX)
if(APPLE)
  # Enabled here, in the directory common to every target that links the .mm-containing libs.
  enable_language(OBJCXX)
endif()

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

# Install layout and packaging (packaging/packaging.cmake; desktop/README.md "Packaging"). Set
# before the targets exist: CMAKE_INSTALL_RPATH is read when a target is created.
option(STK_DESKTOP_RELOCATABLE
  "Package builds: compile no source-tree fallbacks (fonts, catalogs, the suan package) into the binaries" OFF)
if(STK_DESKTOP_RELOCATABLE)
  foreach(_opt STK_GFX_SOURCE_DATAFILES_FALLBACK STK_APP_SOURCE_I18N_FALLBACK STK_DESKTOP_SOURCE_PYTHON_FALLBACK)
    set(${_opt} OFF CACHE BOOL "Forced off by STK_DESKTOP_RELOCATABLE" FORCE)
  endforeach()
endif()
if(APPLE)
  # STK.app: the executables in Contents/MacOS, data in Contents/Resources (the exe-relative
  # lookups of stk_gfx and stk_app try ../Resources/datafiles and ../Resources/i18n).
  set(STK_INSTALL_BINDIR "STK.app/Contents/MacOS")
  set(STK_INSTALL_DATADIR "STK.app/Contents/Resources")
  set(STK_INSTALL_DOCDIR "STK.app/Contents/Resources/licenses")
  # No install RPATH: the vcpkg dependencies are static, nothing is bundled (and rewriting load
  # commands would invalidate the linker's ad-hoc signature).
  set(STK_INSTALL_LIBDIR "STK.app/Contents/Frameworks")
else()
  set(STK_INSTALL_BINDIR "bin")
  set(STK_INSTALL_DATADIR "share/stk-desktop")
  set(STK_INSTALL_DOCDIR "share/doc/stk-desktop")
  set(STK_INSTALL_LIBDIR "lib/stk-desktop")
  if(UNIX)
    # Bundled non-system libraries (packaging/bundle_linux_libs.py) sit in lib/stk-desktop.
    set(CMAKE_INSTALL_RPATH "\$ORIGIN/../lib/stk-desktop")
  endif()
endif()

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
foreach(_lib stk_core stk_io stk_viewer_model stk_gfx stk_viewer_gpu stk_ui stk_wm stk_platform stk_bridge stk_app)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/engine/lib/${_lib}/CMakeLists.txt")
    add_subdirectory(engine/lib/${_lib})
  endif()
endforeach()

# The application and the GPU / window tests need the vendored engine (stk_gfx + stk_wm).
if(TARGET stk_wm)
  add_subdirectory(app)
  add_subdirectory(tests/wm)
endif()

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/unit/CMakeLists.txt")
  add_subdirectory(tests/unit)
endif()
# stk_bridge tests (label `bridge`); they use the googletest that tests/unit provides.
if(TARGET stk_bridge AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/bridge/CMakeLists.txt")
  add_subdirectory(tests/bridge)
endif()
# Application editor tests (label `app`; desktop/tests/app/*.cmake, one file per work package:
# viewer.cmake WP10, jobs.cmake WP9).
if(TARGET stk_app AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/app/CMakeLists.txt")
  add_subdirectory(tests/app)
endif()

# install() of the executables, licences and bundle metadata; CPack (TGZ on Linux, ZIP on macOS).
if(TARGET stk-desktop)
  include("${CMAKE_CURRENT_SOURCE_DIR}/packaging/packaging.cmake")
endif()
