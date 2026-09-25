# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_viewer_gpu: the stk.payload/2 viewer on Blender's GPU module (layers, overlays, id-buffer
# picking, tiled export, GPU buffer budget). GLSL in src/glsl is embedded at build time and
# compiled at runtime through Blender's shader create-info system (see src/shaders.hh).
# Also adds desktop/tools/stk_render (headless renderer) and desktop/tests/viewer (label "viewer").

if(NOT TARGET stk_blender OR NOT TARGET stk_gfx)
  message(STATUS "stk_viewer_gpu: skipped (needs the vendored engine and stk_gfx)")
  return()
endif()
set(_stk_engine_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
get_filename_component(_stk_desktop_dir ${_stk_engine_dir}/.. ABSOLUTE)
if(NOT TARGET stk_viewer_model)
  add_subdirectory(${_stk_engine_dir}/lib/stk_viewer_model ${CMAKE_BINARY_DIR}/engine/lib/stk_viewer_model)
endif()

set(_glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_common_lib.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_mesh_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_glyph_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_line_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_surface_frag.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_point_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_point_frag.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_slice_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_slice_frag.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_volume_vert.glsl
  ${CMAKE_CURRENT_LIST_DIR}/src/glsl/stk_volume_frag.glsl
)
set(_glsl_cc ${CMAKE_CURRENT_BINARY_DIR}/stk_viewer_glsl.cc)
string(REPLACE ";" "|" _glsl_arg "${_glsl}")
add_custom_command(OUTPUT ${_glsl_cc}
  COMMAND ${CMAKE_COMMAND} "-DOUT=${_glsl_cc}" "-DSOURCES=${_glsl_arg}"
          -P ${CMAKE_CURRENT_LIST_DIR}/cmake/embed_glsl.cmake
  DEPENDS ${_glsl} ${CMAKE_CURRENT_LIST_DIR}/cmake/embed_glsl.cmake
  COMMENT "Embedding stk_viewer_gpu GLSL"
  VERBATIM)

add_library(stk_viewer_gpu STATIC
  src/overlays.cc
  src/render.cc
  src/resources.cc
  src/scene.cc
  src/shaders.cc
  src/viewer.cc
  ${_glsl_cc}
)
target_include_directories(stk_viewer_gpu
  PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include
  PRIVATE ${CMAKE_CURRENT_LIST_DIR}/src)
# ShaderCreateInfo (runtime-registered create infos) lives in the GPU module's intern/.
target_include_directories(stk_viewer_gpu SYSTEM PRIVATE
  ${_stk_engine_dir}/third_party/blender/src/source/blender/gpu/intern)
target_compile_features(stk_viewer_gpu PUBLIC cxx_std_20)
target_link_libraries(stk_viewer_gpu PUBLIC stk_viewer_model stk_io stk_gfx stk_blender PRIVATE stk_core)
if(MSVC)
  target_compile_options(stk_viewer_gpu PRIVATE /W3 /utf-8)
else()
  target_compile_options(stk_viewer_gpu PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()

if(EXISTS ${_stk_desktop_dir}/tools/stk_render/CMakeLists.txt)
  add_subdirectory(${_stk_desktop_dir}/tools/stk_render ${CMAKE_BINARY_DIR}/tools/stk_render)
endif()
option(STK_VIEWER_BUILD_TESTS "Build the stk_viewer_gpu tests (desktop/tests/viewer)" ON)
if(STK_VIEWER_BUILD_TESTS AND EXISTS ${_stk_desktop_dir}/tests/viewer/CMakeLists.txt)
  add_subdirectory(${_stk_desktop_dir}/tests/viewer ${CMAKE_BINARY_DIR}/tests/viewer)
endif()
