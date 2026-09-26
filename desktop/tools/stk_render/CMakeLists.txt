# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk-render: headless payload renderer (export, picking, benchmark) on stk_viewer_gpu.

add_executable(stk-render stk_render.cc)
target_link_libraries(stk-render PRIVATE stk_viewer_gpu stk_gfx stk_io)
if(DEFINED STK_DESKTOP_BIN_DIR)
  set_target_properties(stk-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
endif()
if(MSVC)
  target_compile_options(stk-render PRIVATE /utf-8)
endif()
