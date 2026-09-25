# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_wm: GHOST glue (window manager, windows, event loop, DPI, clipboard, cursors, IME, drag and
# drop) and the screen / area / region layout. See include/stk/wm/*.hh.

if(NOT TARGET stk_gfx)
  message(STATUS "stk_wm: skipped (needs stk_gfx)")
  return()
endif()

add_library(stk_wm STATIC
  src/ghost_native.cc
  src/post_queue.cc
  src/screen.cc
  src/window.cc
)
target_include_directories(stk_wm PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(stk_wm PUBLIC cxx_std_20)
target_link_libraries(stk_wm PUBLIC stk_gfx)
# ghost_native.cc includes GHOST's internal system classes: it must see exactly the definitions
# the GHOST library was compiled with (WITH_GHOST_X11, WITH_X11_XINPUT, ...), or the class
# layouts could differ.
set_source_files_properties(src/ghost_native.cc PROPERTIES
  COMPILE_DEFINITIONS "$<TARGET_PROPERTY:bf_intern_ghost,COMPILE_DEFINITIONS>")
if(MSVC)
  target_compile_options(stk_wm PRIVATE /W3)
else()
  target_compile_options(stk_wm PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()
