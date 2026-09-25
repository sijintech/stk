# SPDX-License-Identifier: GPL-2.0-or-later
#
# Engine and window-manager tests (labels):
#   gpu    : headless exports of the WP1 sample frame at 1x / 1.5x / 2x per GPU backend, golden
#            compare with tolerance and CJK crispness / linear-scaling checks; headless exports
#            of the application's default screen (en 1x, zh 1.5x) against goldens (WP3).
#   wm     : CLI, leak self-test; stk_wm_tests (gtest, no GPU): layout maths, screen tree, event
#            routing, maximize, persistence, default-screen layout goldens (WP3).
#   window : live-window smoke tests under a private Xvfb / headless weston (unix sockets
#            only), skipped (return code 77) when the servers are not installed.

add_executable(stk-wm-image-check image_check.cc)
target_link_libraries(stk-wm-image-check PRIVATE stk_gfx)
target_include_directories(stk-wm-image-check PRIVATE ${CMAKE_SOURCE_DIR}/app)

add_executable(stk-wm-smoke wm_smoke.cc)
target_link_libraries(stk-wm-smoke PRIVATE stk_app_sample stk_wm)

add_executable(stk-app-smoke app_smoke.cc)
target_link_libraries(stk-app-smoke PRIVATE stk_app stk_wm)

add_executable(stk-png-diff png_diff.cc)
target_link_libraries(stk-png-diff PRIVATE stk_gfx)

set_target_properties(stk-wm-image-check stk-wm-smoke stk-app-smoke stk-png-diff PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")

set(_golden_dir "${CMAKE_CURRENT_SOURCE_DIR}/golden")
set(_out "${CMAKE_CURRENT_BINARY_DIR}/out")
file(MAKE_DIRECTORY "${_out}")

set(STK_TEST_VK_ICD "/usr/share/vulkan/icd.d/lvp_icd.json" CACHE FILEPATH
    "Vulkan ICD for the engine tests (default: Mesa lavapipe; empty = system default)")

# Software rendering only; caches inside the build tree.
set(_env_common "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache" "LIBGL_ALWAYS_SOFTWARE=1")
if(STK_TEST_VK_ICD AND EXISTS "${STK_TEST_VK_ICD}")
  list(APPEND _env_common "VK_DRIVER_FILES=${STK_TEST_VK_ICD}" "VK_ICD_FILENAMES=${STK_TEST_VK_ICD}")
endif()
if(STK_SYSROOT_FOUND)
  # EGL / glvnd only exist in the user sysroot on the development host.
  list(APPEND _env_common
    "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}"
    "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()
set(_env_headless ${_env_common} "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless")

set(_backends "")
if(STK_GPU_VULKAN)
  list(APPEND _backends vulkan)
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  list(APPEND _backends opengl)
endif()
if(STK_GPU_METAL)
  list(APPEND _backends metal)
endif()

# -------------------------------------------------------------------------------------------
# CLI

add_test(NAME wm_cli_version COMMAND stk-desktop --version)
set_tests_properties(wm_cli_version PROPERTIES LABELS "wm" PASS_REGULAR_EXPRESSION "stk-desktop [0-9]")
add_test(NAME wm_cli_help COMMAND stk-desktop --help)
set_tests_properties(wm_cli_help PROPERTIES LABELS "wm" PASS_REGULAR_EXPRESSION "--headless")
add_test(NAME wm_cli_bad_option COMMAND stk-desktop --no-such-option)
set_tests_properties(wm_cli_bad_option PROPERTIES LABELS "wm" WILL_FAIL TRUE)
add_test(NAME wm_cli_bad_backend COMMAND stk-desktop --headless --gpu-backend nope)
set_tests_properties(wm_cli_bad_backend PROPERTIES LABELS "wm" WILL_FAIL TRUE)

# The guardedalloc leak check must be able to fail: stk::gfx::Runtime + a deliberate leak
# aborts at exit, so the test passes only when the process does NOT exit cleanly.
if(UNIX)
  add_test(NAME wm_leak_selftest COMMAND sh -c "! \"$<TARGET_FILE:stk-wm-smoke>\" --leak-selftest 2>&1")
  set_tests_properties(wm_leak_selftest PROPERTIES LABELS "wm")
endif()

# -------------------------------------------------------------------------------------------
# Headless exports: 1x / 1.5x / 2x of the same logical frame (480x300 points).

set(_scales 1 1.5 2)
set(_sizes 480x300 720x450 960x600)
foreach(_be ${_backends})
  set(_check_args "")
  foreach(_i RANGE 2)
    list(GET _scales ${_i} _s)
    list(GET _sizes ${_i} _size)
    string(REPLACE "." "_" _tag "${_s}")
    set(_png "${_out}/sample_${_be}_${_tag}x.png")
    add_test(NAME wm_headless_export_${_be}_${_tag}x
      COMMAND stk-desktop --headless --sample --gpu-backend ${_be} --size ${_size} --scale ${_s} --export ${_png})
    set_tests_properties(wm_headless_export_${_be}_${_tag}x PROPERTIES
      LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}"
      FIXTURES_SETUP wm_export_${_be}
      # A leak makes guardedalloc print its report and abort at exit.
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
    list(APPEND _check_args "${_s}=${_png}")
  endforeach()
  add_test(NAME wm_headless_check_${_be}
    COMMAND stk-wm-image-check --golden-dir ${_golden_dir} ${_check_args})
  set_tests_properties(wm_headless_check_${_be} PROPERTIES
    LABELS "gpu" FIXTURES_REQUIRED wm_export_${_be})
endforeach()

# -------------------------------------------------------------------------------------------
# Application screen (WP3): headless exports of the default layout against tolerant goldens
# (en at 1x 1280x800, zh at 1.5x 1440x900), plus layout files through the CLI.

foreach(_case "en;1;1280x800" "zh;1.5;1440x900")
  list(GET _case 0 _lang)
  list(GET _case 1 _s)
  list(GET _case 2 _size)
  string(REPLACE "." "_" _tag "${_s}")
  set(_golden "${_golden_dir}/app_default_${_lang}_${_tag}x.png")
  foreach(_be ${_backends})
    set(_png "${_out}/app_${_be}_${_lang}_${_tag}x.png")
    add_test(NAME wm_app_export_${_be}_${_lang}_${_tag}x
      COMMAND stk-desktop --headless --gpu-backend ${_be} --size ${_size} --scale ${_s} --lang ${_lang}
              --export ${_png})
    set_tests_properties(wm_app_export_${_be}_${_lang}_${_tag}x PROPERTIES
      LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}"
      FIXTURES_SETUP wm_app_${_be}_${_lang}
      PASS_REGULAR_EXPRESSION "4 areas"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|catalogs")
    add_test(NAME wm_app_golden_${_be}_${_lang}_${_tag}x COMMAND stk-png-diff ${_png} ${_golden})
    set_tests_properties(wm_app_golden_${_be}_${_lang}_${_tag}x PROPERTIES
      LABELS "gpu" FIXTURES_REQUIRED wm_app_${_be}_${_lang})
  endforeach()
endforeach()

if(_backends)
  list(GET _backends 0 _be)
  # Layout files through the CLI: save the default layout, load it back, and fall back from a
  # corrupt file (exit 0 with a warning, still 4 areas).
  set(_layout "${_out}/cli_layout.json")
  add_test(NAME wm_app_layout_save
    COMMAND stk-desktop --headless --gpu-backend ${_be} --size 640x400 --lang en --save-layout ${_layout})
  set_tests_properties(wm_app_layout_save PROPERTIES
    LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}" FIXTURES_SETUP wm_app_layout
    PASS_REGULAR_EXPRESSION "4 areas")
  add_test(NAME wm_app_layout_load
    COMMAND stk-desktop --headless --gpu-backend ${_be} --size 640x400 --layout ${_layout})
  set_tests_properties(wm_app_layout_load PROPERTIES
    LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}" FIXTURES_REQUIRED wm_app_layout
    PASS_REGULAR_EXPRESSION "en, [A-Za-z]+, 4 areas" FAIL_REGULAR_EXPRESSION "cannot use layout")
  file(WRITE "${_out}/cli_corrupt.json" "{ not json")
  add_test(NAME wm_app_layout_corrupt
    COMMAND stk-desktop --headless --gpu-backend ${_be} --size 640x400 --layout ${_out}/cli_corrupt.json)
  set_tests_properties(wm_app_layout_corrupt PROPERTIES
    LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}"
    PASS_REGULAR_EXPRESSION "using the default layout")
endif()

# -------------------------------------------------------------------------------------------
# Screen / area / region / app unit tests (gtest, no GPU context).

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

add_executable(stk_wm_tests
  support.cc
  test_app.cc
  test_app_store_open.cc
  test_layout_golden.cc
  test_layout_math.cc
  test_persistence.cc
  test_screen.cc
)
target_link_libraries(stk_wm_tests PRIVATE stk_app stk_wm GTest::gtest_main)
target_compile_definitions(stk_wm_tests PRIVATE
  STK_DESKTOP_DIR="${CMAKE_SOURCE_DIR}"
  STK_WM_GOLDEN_DIR="${_golden_dir}")
if(MSVC)
  target_compile_options(stk_wm_tests PRIVATE /W3 /utf-8 /bigobj)
else()
  target_compile_options(stk_wm_tests PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()
gtest_discover_tests(stk_wm_tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES PROPERTIES LABELS "wm")

# -------------------------------------------------------------------------------------------
# Live windows (Linux): a private Xvfb (X11) and a headless weston (Wayland).

find_package(Python3 COMPONENTS Interpreter)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND Python3_Interpreter_FOUND)
  set(_runner "${CMAKE_CURRENT_SOURCE_DIR}/run_with_display.py")
  set(_sysroot_arg "")
  if(STK_SYSROOT_FOUND)
    set(_sysroot_arg --sysroot "${STK_SYSROOT}")
  endif()
  foreach(_server xvfb weston)
    foreach(_be ${_backends})
      set(_name wm_window_${_server}_${_be})
      add_test(NAME ${_name}
        COMMAND ${Python3_EXECUTABLE} ${_runner} --server ${_server}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server}_${_be} ${_sysroot_arg}
                -- $<TARGET_FILE:stk-wm-smoke> --gpu-backend ${_be})
      set_tests_properties(${_name} PROPERTIES
        LABELS "gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env_common}"
        RESOURCE_LOCK display_${_server})
    endforeach()
    # The application itself: open the window, present frames, quit cleanly without leaks.
    set(_name wm_app_${_server})
    add_test(NAME ${_name}
      COMMAND ${Python3_EXECUTABLE} ${_runner} --server ${_server}
              --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server}_app ${_sysroot_arg}
              -- $<TARGET_FILE:stk-desktop> --exit-after-frames 3 --verbose --no-bridge)
    set_tests_properties(${_name} PROPERTIES
      LABELS "gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77
      ENVIRONMENT "${_env_common};XDG_CONFIG_HOME=${CMAKE_CURRENT_BINARY_DIR}/config_${_server}"
      RESOURCE_LOCK display_${_server}
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
    # The application shell in a live window: pixels, a splitter dragged with synthesized
    # events, resize, UI scale, close with the layout saved (first backend).
    if(_backends)
      list(GET _backends 0 _be)
      set(_name wm_app_window_${_server})
      add_test(NAME ${_name}
        COMMAND ${Python3_EXECUTABLE} ${_runner} --server ${_server}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server}_appsmoke ${_sysroot_arg}
                -- $<TARGET_FILE:stk-app-smoke> --gpu-backend ${_be}
                   --layout-out ${_out}/smoke_layout_${_server}.json)
      set_tests_properties(${_name} PROPERTIES
        LABELS "gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env_common}"
        RESOURCE_LOCK display_${_server} PASS_REGULAR_EXPRESSION "PASS"
        FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
    endif()
  endforeach()
  # GNOME on Wayland: GHOST's client-side decorations (XDG_CURRENT_DESKTOP=GNOME on weston's
  # desktop shell; the kiosk shell makes every window fullscreen, which has no decorations).
  if(_backends)
    list(GET _backends 0 _be)
    add_test(NAME wm_app_window_weston_csd
      COMMAND ${Python3_EXECUTABLE} ${_runner} --server weston --weston-shell desktop
              --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_weston_csd ${_sysroot_arg}
              -- $<TARGET_FILE:stk-app-smoke> --gpu-backend ${_be} --expect-csd
                 --layout-out ${_out}/smoke_layout_csd.json)
    set_tests_properties(wm_app_window_weston_csd PROPERTIES
      LABELS "gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77
      ENVIRONMENT "${_env_common};XDG_CURRENT_DESKTOP=GNOME"
      RESOURCE_LOCK display_weston PASS_REGULAR_EXPRESSION "PASS"
      FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
  endif()
endif()
