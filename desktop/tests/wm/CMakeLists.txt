# SPDX-License-Identifier: GPL-2.0-or-later
#
# WP1 engine tests (labels):
#   gpu    : headless exports of the sample frame at 1x / 1.5x / 2x per GPU backend, golden
#            compare with tolerance and CJK crispness / linear-scaling checks.
#   wm     : CLI, leak self-test.
#   window : live-window smoke tests under a private Xvfb / headless weston (unix sockets
#            only), skipped (return code 77) when the servers are not installed.

add_executable(stk-wm-image-check image_check.cc)
target_link_libraries(stk-wm-image-check PRIVATE stk_gfx)
target_include_directories(stk-wm-image-check PRIVATE ${CMAKE_SOURCE_DIR}/app)

add_executable(stk-wm-smoke wm_smoke.cc)
target_link_libraries(stk-wm-smoke PRIVATE stk_app_sample stk_wm)

set_target_properties(stk-wm-image-check stk-wm-smoke PROPERTIES
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
      COMMAND stk-desktop --headless --gpu-backend ${_be} --size ${_size} --scale ${_s} --export ${_png})
    set_tests_properties(wm_headless_export_${_be}_${_tag}x PROPERTIES
      LABELS "gpu" TIMEOUT 300 ENVIRONMENT "${_env_headless}"
      FIXTURES_SETUP wm_export_${_be}
      # A leak makes stk-desktop fail (exit 1, then guardedalloc's report).
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
    list(APPEND _check_args "${_s}=${_png}")
  endforeach()
  add_test(NAME wm_headless_check_${_be}
    COMMAND stk-wm-image-check --golden-dir ${_golden_dir} ${_check_args})
  set_tests_properties(wm_headless_check_${_be} PROPERTIES
    LABELS "gpu" FIXTURES_REQUIRED wm_export_${_be})
endforeach()

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
              -- $<TARGET_FILE:stk-desktop> --exit-after-frames 3 --verbose)
    set_tests_properties(${_name} PROPERTIES
      LABELS "gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env_common}"
      RESOURCE_LOCK display_${_server}
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
  endforeach()
endif()
