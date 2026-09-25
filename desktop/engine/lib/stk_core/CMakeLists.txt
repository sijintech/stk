# SPDX-License-Identifier: GPL-2.0-or-later
# stk_core: logging, UTF-8, sha256, read-only file mapping, paths, thread pool, clock.
# CPU only: never includes GHOST, GPU or Blender headers (desktop engine dependency rule).
add_library(stk_core STATIC
  src/log.cc
  src/utf8.cc
  src/sha256.cc
  src/mmap.cc
  src/paths.cc
  src/thread_pool.cc
  src/clock.cc
)
target_include_directories(stk_core PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_core PUBLIC cxx_std_20)
set_target_properties(stk_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
find_package(Threads REQUIRED)
target_link_libraries(stk_core PUBLIC Threads::Threads)
if(WIN32)
  target_compile_definitions(stk_core PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
endif()
if(MSVC)
  target_compile_options(stk_core PRIVATE /utf-8)
endif()
# No FMA contraction: float results must be bit-identical on every compiler/CPU (parity with Python/web).
if(MSVC)
  target_compile_options(stk_core PRIVATE /fp:precise)
else()
  target_compile_options(stk_core PRIVATE -ffp-contract=off)
endif()
if(COMMAND stk_target_warnings)
  stk_target_warnings(stk_core)
endif()
