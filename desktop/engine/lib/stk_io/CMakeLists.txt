# SPDX-License-Identifier: GPL-2.0-or-later
# stk_io: JSON models, stk.payload/2 decode (directory, .stkp, blob cache), graph/catalog/preset/result
# models, JSON-Schema subset validator (suan.graph.schema parity), Python-compatible regex, PNG I/O.
# CPU only: never includes GHOST, GPU or Blender headers.
set(_stk_engine_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
if(NOT TARGET stk_core)
  add_subdirectory(${_stk_engine_dir}/lib/stk_core ${CMAKE_BINARY_DIR}/engine/lib/stk_core)
endif()
if(NOT TARGET stk_nlohmann_json)
  add_subdirectory(${_stk_engine_dir}/third_party/nlohmann_json ${CMAKE_BINARY_DIR}/engine/third_party/nlohmann_json)
endif()
if(NOT TARGET stk_spng)
  add_subdirectory(${_stk_engine_dir}/third_party/libspng ${CMAKE_BINARY_DIR}/engine/third_party/libspng)
endif()

add_library(stk_io STATIC
  src/json.cc
  src/payload.cc
  src/blob_cache.cc
  src/pyregex.cc
  src/schema.cc
  src/graph.cc
  src/catalog.cc
  src/result.cc
  src/png.cc
)
target_include_directories(stk_io PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_io PUBLIC cxx_std_20)
set_target_properties(stk_io PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(stk_io PUBLIC stk_core stk_nlohmann_json PRIVATE stk_spng)
if(MSVC)
  target_compile_options(stk_io PRIVATE /bigobj /utf-8)
endif()
# No FMA contraction: float results must be bit-identical on every compiler/CPU (parity with Python/web).
if(MSVC)
  target_compile_options(stk_io PRIVATE /fp:precise)
else()
  target_compile_options(stk_io PRIVATE -ffp-contract=off)
endif()
if(COMMAND stk_target_warnings)
  stk_target_warnings(stk_io)
endif()
