# SPDX-License-Identifier: GPL-2.0-or-later
# Unit tests of the CPU-only engine libraries (stk_core, stk_io, stk_viewer_model); no GPU needed.
#
# Standalone:   cmake -S desktop/tests/unit -B desktop/build-unit -G Ninja && cmake --build desktop/build-unit
#               ctest --test-dir desktop/build-unit
# From desktop/CMakeLists.txt: add_subdirectory(tests/unit) after the engine libraries.
#
# googletest 1.17.0 is fetched with FetchContent from a pinned, hash-checked tarball: the local copy
# ~/opt/stk-src/googletest-1.17.0.tar.gz when present (offline builds), else GitHub. Set
# STK_USE_SYSTEM_GTEST=ON to use find_package(GTest) instead.
cmake_minimum_required(VERSION 3.21)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(stk_desktop_unit LANGUAGES C CXX)
  set(CMAKE_CXX_STANDARD 20)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)
  if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "" FORCE)
  endif()
  enable_testing()
endif()

set(STK_DESKTOP_DIR ${CMAKE_CURRENT_LIST_DIR}/../..)
get_filename_component(STK_DESKTOP_DIR ${STK_DESKTOP_DIR} ABSOLUTE)
get_filename_component(STK_REPO_ROOT ${STK_DESKTOP_DIR}/.. ABSOLUTE)

option(STK_UNIT_SANITIZE "Build the CPU libraries and tests with AddressSanitizer + UBSan" OFF)
option(STK_USE_SYSTEM_GTEST "Use find_package(GTest) instead of the pinned FetchContent tarball" OFF)

if(NOT COMMAND stk_target_warnings)
  function(stk_target_warnings target)
    if(MSVC)
      target_compile_options(${target} PRIVATE /W4 /permissive- /utf-8)
    else()
      target_compile_options(${target} PRIVATE -Wall -Wextra -Wno-unused-parameter)
    endif()
  endfunction()
endif()

if(STK_UNIT_SANITIZE AND NOT MSVC)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=undefined)
  add_link_options(-fsanitize=address,undefined)
endif()

foreach(_lib stk_core stk_io stk_viewer_model)
  if(NOT TARGET ${_lib})
    add_subdirectory(${STK_DESKTOP_DIR}/engine/lib/${_lib} ${CMAKE_BINARY_DIR}/engine/lib/${_lib})
  endif()
endforeach()

# googletest ------------------------------------------------------------------------------------
if(TARGET GTest::gtest_main OR TARGET gtest_main)
  # Already provided by the parent project.
  if(NOT TARGET GTest::gtest_main)
    add_library(GTest::gtest_main ALIAS gtest_main)
  endif()
elseif(STK_USE_SYSTEM_GTEST)
  find_package(GTest REQUIRED)
else()
  include(FetchContent)
  set(_gtest_local "$ENV{HOME}/opt/stk-src/googletest-1.17.0.tar.gz")
  if(EXISTS "${_gtest_local}")
    set(_gtest_url "file://${_gtest_local}")
  else()
    set(_gtest_url "https://github.com/google/googletest/releases/download/v1.17.0/googletest-1.17.0.tar.gz")
  endif()
  set(STK_GTEST_URL "${_gtest_url}" CACHE STRING "googletest 1.17.0 source tarball (sha256-pinned)")
  FetchContent_Declare(googletest
    URL ${STK_GTEST_URL}
    URL_HASH SHA256=65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c
    DOWNLOAD_EXTRACT_TIMESTAMP ON)
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)
  if(NOT TARGET GTest::gtest_main)
    add_library(GTest::gtest_main ALIAS gtest_main)
  endif()
endif()
include(GoogleTest)

# Tests -----------------------------------------------------------------------------------------
add_executable(stk_unit_tests
  test_core.cc
  test_payload.cc
  test_payload_parity.cc
  test_schema.cc
  test_regex.cc
  test_graph.cc
  test_png.cc
  test_camera.cc
  test_picking.cc
  test_colormap.cc
  test_format.cc
  test_glyph.cc
  test_volume_lod.cc
  test_viewer_helpers.cc
  test_payload_fuzz.cc
  support.cc
  fuzz/payload_fuzz_lib.cc
)
target_link_libraries(stk_unit_tests PRIVATE stk_core stk_io stk_viewer_model GTest::gtest_main)
target_include_directories(stk_unit_tests PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_compile_definitions(stk_unit_tests PRIVATE
  STK_REPO_ROOT="${STK_REPO_ROOT}"
  STK_FIXTURES_DIR="${CMAKE_CURRENT_LIST_DIR}/fixtures"
  STK_TEST_SCRATCH_DIR="${CMAKE_CURRENT_BINARY_DIR}/stk_unit_scratch")
stk_target_warnings(stk_unit_tests)
if(MSVC)
  target_compile_options(stk_unit_tests PRIVATE /bigobj)
endif()
gtest_discover_tests(stk_unit_tests DISCOVERY_TIMEOUT 60 DISCOVERY_MODE PRE_TEST PROPERTIES LABELS "unit")
add_test(NAME stk_cpu_libs_include_rule
         COMMAND ${CMAKE_COMMAND} -DLIB_DIR=${STK_DESKTOP_DIR}/engine/lib -P ${CMAKE_CURRENT_LIST_DIR}/check_includes.cmake)
set_tests_properties(stk_cpu_libs_include_rule PROPERTIES LABELS "unit")

# Payload decoder fuzzing -----------------------------------------------------------------------
# With Clang a libFuzzer target (STK_FUZZ_LIBFUZZER=ON); otherwise a standalone driver that mutates
# the fixture corpus for a given time (stk_payload_fuzz --seconds 600 --corpus <dir>).
include(CheckCXXCompilerFlag)
set(_libfuzzer OFF)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  check_cxx_compiler_flag(-fsanitize=fuzzer-no-link STK_HAVE_LIBFUZZER)
  set(_libfuzzer ${STK_HAVE_LIBFUZZER})
endif()
option(STK_FUZZ_LIBFUZZER "Build stk_payload_fuzz with libFuzzer" ${_libfuzzer})
add_executable(stk_payload_fuzz fuzz/payload_fuzz.cc fuzz/payload_fuzz_lib.cc)
target_link_libraries(stk_payload_fuzz PRIVATE stk_core stk_io stk_viewer_model)
target_compile_definitions(stk_payload_fuzz PRIVATE STK_FIXTURES_DIR="${CMAKE_CURRENT_LIST_DIR}/fixtures")
if(STK_FUZZ_LIBFUZZER)
  target_compile_definitions(stk_payload_fuzz PRIVATE STK_LIBFUZZER=1)
  target_compile_options(stk_payload_fuzz PRIVATE -fsanitize=fuzzer)
  target_link_options(stk_payload_fuzz PRIVATE -fsanitize=fuzzer)
endif()
if(STK_FUZZ_LIBFUZZER)
  add_test(NAME stk_payload_fuzz_smoke COMMAND stk_payload_fuzz -max_total_time=5 ${CMAKE_CURRENT_LIST_DIR}/fixtures/fuzz_corpus)
else()
  add_test(NAME stk_payload_fuzz_smoke COMMAND stk_payload_fuzz --seconds 5 --corpus ${CMAKE_CURRENT_LIST_DIR}/fixtures/fuzz_corpus)
endif()
set_tests_properties(stk_payload_fuzz_smoke PROPERTIES LABELS "unit;fuzz")
