# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_bridge: the desktop app's client of the STK desktop bridge (python -m suan.desktop_bridge
# --stdio, docs/specs/stk-desktop-bridge-v1.md): process spawn (posix_spawn / CreateProcessW +
# job object), NDJSON framing, futures, subscriptions, restart and replay. See
# include/stk/bridge/client.hh. CPU only: no GHOST / GPU headers; callbacks reach the main loop
# through an executor (stk::wm::WindowManager::executor()).

set(_stk_engine_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
if(NOT TARGET stk_io)
  add_subdirectory(${_stk_engine_dir}/lib/stk_io ${CMAKE_BINARY_DIR}/engine/lib/stk_io)
endif()

# The protocol schema is built in (validation in debug / CI runs): generated from the MIT schema
# file of the Python package, the single source of truth.
get_filename_component(STK_BRIDGE_SCHEMA
  "${CMAKE_CURRENT_LIST_DIR}/../../../../suan/contracts/schemas/desktop-bridge-1.schema.json" ABSOLUTE)
set(_schema_inc "${CMAKE_CURRENT_BINARY_DIR}/generated/desktop_bridge_schema.inc")
add_custom_command(
  OUTPUT "${_schema_inc}"
  COMMAND ${CMAKE_COMMAND} -DINPUT=${STK_BRIDGE_SCHEMA} -DOUTPUT=${_schema_inc} -DNAME=desktop_bridge_schema
          -P ${CMAKE_CURRENT_LIST_DIR}/cmake/embed_file.cmake
  DEPENDS "${STK_BRIDGE_SCHEMA}" "${CMAKE_CURRENT_LIST_DIR}/cmake/embed_file.cmake"
  COMMENT "Embedding desktop-bridge-1.schema.json")

set(_sources
  src/api.cc
  src/client.cc
  src/log_ring.cc
  src/protocol.cc
  src/python.cc
  src/schema.cc
  src/types.cc
  "${_schema_inc}"
)
if(WIN32)
  list(APPEND _sources src/process_win32.cc)
else()
  list(APPEND _sources src/process_posix.cc)
endif()

add_library(stk_bridge STATIC ${_sources})
target_include_directories(stk_bridge
  PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include
  PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/generated)
target_compile_features(stk_bridge PUBLIC cxx_std_20)
set_target_properties(stk_bridge PROPERTIES POSITION_INDEPENDENT_CODE ON)
find_package(Threads REQUIRED)
target_link_libraries(stk_bridge PUBLIC stk_io stk_core Threads::Threads)
if(WIN32)
  target_compile_definitions(stk_bridge PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
endif()
if(MSVC)
  target_compile_options(stk_bridge PRIVATE /utf-8 /bigobj)
endif()
if(COMMAND stk_target_warnings)
  stk_target_warnings(stk_bridge)
elseif(NOT MSVC)
  target_compile_options(stk_bridge PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
