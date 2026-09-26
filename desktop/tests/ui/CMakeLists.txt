# SPDX-License-Identifier: GPL-2.0-or-later
# stk_ui tests (ui_core only, no GPU): text/IME/number/event tests, layout goldens (en/zh at
# 1x/1.5x/2x), form-builder tests against the catalog and the muferro-domains preset, i18n.
# Added from engine/lib/stk_ui/CMakeLists.txt. Regenerate goldens with STK_UPDATE_GOLDENS=1.

set(_stk_desktop_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
get_filename_component(_stk_desktop_dir ${_stk_desktop_dir} ABSOLUTE)
get_filename_component(_stk_repo_dir ${_stk_desktop_dir}/.. ABSOLUTE)

# googletest: same pinned tarball and FetchContent name as desktop/tests/unit (first declaration
# wins; both directories can be configured in either order).
if(NOT TARGET GTest::gtest_main)
  if(STK_USE_SYSTEM_GTEST)
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
endif()
include(GoogleTest)

add_executable(stk_ui_tests
  test_text.cc
  test_number.cc
  test_text_edit.cc
  test_events.cc
  test_layout_golden.cc
  test_form.cc
  test_transfer_function.cc
  test_i18n.cc
  support.cc
)
target_link_libraries(stk_ui_tests PRIVATE stk_ui_core stk_ui_gallery_screens GTest::gtest_main)
target_compile_definitions(stk_ui_tests PRIVATE
  STK_DESKTOP_DIR="${_stk_desktop_dir}"
  STK_REPO_ROOT="${_stk_repo_dir}"
  STK_UI_GOLDEN_DIR="${CMAKE_CURRENT_LIST_DIR}/golden")
if(MSVC)
  target_compile_options(stk_ui_tests PRIVATE /W4 /utf-8 /bigobj)
else()
  target_compile_options(stk_ui_tests PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
gtest_discover_tests(stk_ui_tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES PROPERTIES LABELS "ui")

add_test(NAME ui_core_include_rule
         COMMAND ${CMAKE_COMMAND} -DUI_DIR=${_stk_desktop_dir}/engine/lib/stk_ui
                 -P ${CMAKE_CURRENT_LIST_DIR}/check_ui_core_includes.cmake)
set_tests_properties(ui_core_include_rule PROPERTIES LABELS "ui")

# i18n: the catalogs must be complete (fails CI on a missing key), and the checker must fail on
# broken catalogs (unittest).
find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
  add_test(NAME ui_i18n_catalogs
    COMMAND ${Python3_EXECUTABLE} ${_stk_desktop_dir}/app/i18n/check_i18n.py --scan ${_stk_desktop_dir})
  add_test(NAME ui_i18n_checker_selftest
    COMMAND ${Python3_EXECUTABLE} -m unittest -v test_i18n_checker
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR})
  set_tests_properties(ui_i18n_catalogs ui_i18n_checker_selftest PROPERTIES LABELS "ui"
    ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1;STK_I18N_CHECKER=${_stk_desktop_dir}/app/i18n/check_i18n.py")
endif()
