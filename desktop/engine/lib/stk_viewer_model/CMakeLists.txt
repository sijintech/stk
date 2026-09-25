# SPDX-License-Identifier: GPL-2.0-or-later
# stk_viewer_model: CPU-only viewer logic (successor of blender/.../space_stk/stk_scene.hh): float64
# camera and presets, camera-relative matrices, pick refinement, colormap binning, glyph geometry,
# label formatting, volume transfer functions, LOD policy. Never includes GHOST, GPU or Blender headers.
set(_stk_engine_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
if(NOT TARGET stk_io)
  add_subdirectory(${_stk_engine_dir}/lib/stk_io ${CMAKE_BINARY_DIR}/engine/lib/stk_io)
endif()

add_library(stk_viewer_model STATIC
  src/math.cc
  src/camera.cc
  src/picking.cc
  src/colormap.cc
  src/format.cc
  src/glyph.cc
  src/volume.cc
  src/lod.cc
  src/scene.cc
)
target_include_directories(stk_viewer_model PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_viewer_model PUBLIC cxx_std_20)
set_target_properties(stk_viewer_model PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(stk_viewer_model PUBLIC stk_io stk_core)
if(MSVC)
  target_compile_options(stk_viewer_model PRIVATE /utf-8)
endif()
# No FMA contraction: float results must be bit-identical on every compiler/CPU (parity with Python/web).
if(MSVC)
  target_compile_options(stk_viewer_model PRIVATE /fp:precise)
else()
  target_compile_options(stk_viewer_model PRIVATE -ffp-contract=off)
endif()
if(COMMAND stk_target_warnings)
  stk_target_warnings(stk_viewer_model)
endif()
