# SPDX-License-Identifier: GPL-2.0-or-later
#
# Prefix hints for the no-sudo user sysroot populated by fetch-sysroot.sh.
# Usable as a toolchain file (-DCMAKE_TOOLCHAIN_FILE=.../stk-sysroot.cmake) or
# included from desktop/CMakeLists.txt (done automatically on Linux when the
# sysroot exists). It only adds search prefixes; the host compiler and libc are
# used unchanged, so this is not a CMAKE_SYSROOT.

if(NOT DEFINED STK_SYSROOT)
  if(DEFINED ENV{STK_SYSROOT})
    set(STK_SYSROOT "$ENV{STK_SYSROOT}")
  else()
    set(STK_SYSROOT "$ENV{HOME}/opt/stk-sysroot")
  endif()
endif()
set(STK_SYSROOT "${STK_SYSROOT}" CACHE PATH "User sysroot with STK desktop build dependencies")

if(EXISTS "${STK_SYSROOT}/usr/include")
  set(STK_SYSROOT_FOUND TRUE)
  set(STK_SYSROOT_LIBDIR "${STK_SYSROOT}/usr/lib/x86_64-linux-gnu")
  list(PREPEND CMAKE_PREFIX_PATH "${STK_SYSROOT}/usr")
  list(PREPEND CMAKE_INCLUDE_PATH "${STK_SYSROOT}/usr/include")
  list(PREPEND CMAKE_LIBRARY_PATH "${STK_SYSROOT_LIBDIR}")
  list(PREPEND CMAKE_PROGRAM_PATH "${STK_SYSROOT}/usr/bin")
  # Binaries built here run against sysroot-only runtime libraries (EGL, glvnd).
  list(APPEND CMAKE_BUILD_RPATH "${STK_SYSROOT_LIBDIR}")
  # glvnd looks up EGL vendors (Mesa) through this directory at runtime.
  set(STK_SYSROOT_EGL_VENDOR_DIR "${STK_SYSROOT}/usr/share/glvnd/egl_vendor.d")
else()
  set(STK_SYSROOT_FOUND FALSE)
endif()
