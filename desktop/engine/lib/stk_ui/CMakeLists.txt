# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_ui: Blender-style UI toolkit.
#   stk_ui_core  blocks, layout, widgets, theme, i18n, text editing, forms (no GPU/GHOST includes;
#                builds anywhere, including MSVC and macOS, with STK_DESKTOP_WITH_BLENDER=OFF)
#   stk_ui_gpu   Painter on the GPU module's immediate mode + widget-base shader, BLF text measurer
#                on WP1's font stack (only when stk_gfx exists, i.e. with the vendored engine)
#   stk_ui       convenience interface target (core + gpu when available)
#
# Also adds desktop/tests/ui (gtest, labels "ui" and "gpu") and desktop/tools/widget_gallery, so
# the root CMakeLists.txt needs no change (it adds engine/lib/* automatically).

set(_stk_desktop_dir ${CMAKE_CURRENT_LIST_DIR}/../../..)
get_filename_component(_stk_desktop_dir ${_stk_desktop_dir} ABSOLUTE)

option(STK_UI_BUILD_TESTS "Build the stk_ui tests (desktop/tests/ui)" ON)
option(STK_UI_BUILD_GALLERY "Build the widget gallery (desktop/tools/widget_gallery)" ON)

# ui_core depends on stk_core (UTF-8) and stk_io (catalog models, parameter forms, nlohmann_json);
# all CPU-only, so ui_core still builds with STK_DESKTOP_WITH_BLENDER=OFF.
foreach(_dep stk_core stk_io)
  if(NOT TARGET ${_dep})
    add_subdirectory(${_stk_desktop_dir}/engine/lib/${_dep} ${CMAKE_BINARY_DIR}/engine/lib/${_dep})
  endif()
endforeach()

add_library(stk_ui_core STATIC
  src/core/basics.cc
  src/core/context.cc
  src/core/draw.cc
  src/core/form.cc
  src/core/form_json.cc
  src/core/geom.cc
  src/core/golden.cc
  src/core/i18n.cc
  src/core/layout.cc
  src/core/number.cc
  src/core/text.cc
  src/core/text_edit.cc
  src/core/theme.cc
  src/core/utf8.cc
)
target_include_directories(stk_ui_core PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_ui_core PUBLIC cxx_std_20)
target_link_libraries(stk_ui_core PUBLIC stk_core stk_io stk_nlohmann_json)
set_target_properties(stk_ui_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(stk_ui_core PRIVATE /W4 /permissive- /utf-8)
  target_compile_options(stk_ui_core INTERFACE /utf-8)
else()
  target_compile_options(stk_ui_core PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

add_library(stk_ui INTERFACE)
target_link_libraries(stk_ui INTERFACE stk_ui_core)

if(TARGET stk_gfx)
  add_library(stk_ui_gpu STATIC
    src/gpu/gpu_painter.cc
  )
  target_include_directories(stk_ui_gpu PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
  target_link_libraries(stk_ui_gpu PUBLIC stk_ui_core stk_gfx stk_blender)
  target_link_libraries(stk_ui INTERFACE stk_ui_gpu)
endif()

# The gallery directory always provides the core-only screen library used by the layout goldens;
# the widget_gallery executable itself needs stk_ui_gpu.
if(EXISTS ${_stk_desktop_dir}/tools/widget_gallery/CMakeLists.txt)
  add_subdirectory(${_stk_desktop_dir}/tools/widget_gallery ${CMAKE_BINARY_DIR}/tools/widget_gallery)
endif()
if(STK_UI_BUILD_TESTS AND EXISTS ${_stk_desktop_dir}/tests/ui/CMakeLists.txt)
  add_subdirectory(${_stk_desktop_dir}/tests/ui ${CMAKE_BINARY_DIR}/tests/ui)
endif()
