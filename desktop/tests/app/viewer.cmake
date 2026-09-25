# SPDX-License-Identifier: GPL-2.0-or-later
# WP10 viewer tests (included from tests/app/CMakeLists.txt):
#   stk_app_viewer_tests      gtest, no GPU (label "app"): ViewerState against the scripted fake
#                             bridge (evaluated nodes after client / data edits, debounce,
#                             cancellation, progress, prefetch and cached step switches, camera
#                             preservation, playback, probe, layer overrides, sequence export),
#                             result / series folders, and layout goldens of the Properties forms
#                             of all 7 presets (zh / en; STK_UPDATE_GOLDENS=1 rewrites golden/).
#   stk_app_viewer_gpu_tests  gtest with a GPU and the real Python bridge (labels "app;gpu;bridge"):
#                             muferro-domains on a fake muFerro run; a client-stage change re-runs
#                             no data node and re-renders; a data-stage change re-runs data nodes;
#                             a cached step switch completes in under 300 ms (measured, printed).
#   app_viewer_e2e_<backend>  stk-desktop --headless --preset muferro-domains --run <fake run>
#                             --export: golden (SSIM >= 0.98) and VTK cross-check (mask IoU >= 0.9).
#   app_viewer_window_<srv>   stk-viewer-live under Xvfb / weston: open a run, orbit with a
#                             synthesized drag, pick, and the Probe editor shows the value.

set(_app_repo "${CMAKE_SOURCE_DIR}/..")
get_filename_component(_app_repo "${_app_repo}" ABSOLUTE)
set(_app_scratch "${CMAKE_CURRENT_BINARY_DIR}/scratch")
set(_app_golden "${CMAKE_CURRENT_SOURCE_DIR}/golden")
set(_app_python "${STK_BRIDGE_TEST_PYTHON}")
if(NOT _app_python)
  set(_app_python "python3")
endif()

if(TARGET stk-bridge-fake)
  add_executable(stk_app_viewer_tests
    viewer_support.cc
    test_viewer_state.cc
    test_viewer_forms.cc
    ${CMAKE_SOURCE_DIR}/tests/wm/support.cc
  )
  target_include_directories(stk_app_viewer_tests PRIVATE ${CMAKE_SOURCE_DIR}/tests/wm)
  target_link_libraries(stk_app_viewer_tests PRIVATE stk_app stk_wm GTest::gtest_main)
  target_compile_definitions(stk_app_viewer_tests PRIVATE
    STK_REPO_ROOT="${_app_repo}"
    STK_DESKTOP_DIR="${CMAKE_SOURCE_DIR}"
    STK_BRIDGE_FAKE="$<TARGET_FILE:stk-bridge-fake>"
    STK_APP_TEST_SCRATCH="${_app_scratch}"
    STK_APP_GOLDEN_DIR="${_app_golden}")
  add_dependencies(stk_app_viewer_tests stk-bridge-fake)
  if(NOT MSVC)
    target_compile_options(stk_app_viewer_tests PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
  endif()
  gtest_discover_tests(stk_app_viewer_tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
    PROPERTIES LABELS "app" TIMEOUT 300)
endif()

# ---------------------------------------------------------------------------------------------
# GPU: image comparison tool, the Python-bridge integration test, the e2e golden, live windows.

if(NOT TARGET stk_viewer_gpu)
  return()
endif()

add_executable(stk-viewer-image-compare image_compare.cc)
target_link_libraries(stk-viewer-image-compare PRIVATE stk_gfx)
set_target_properties(stk-viewer-image-compare PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")

set(_app_env "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless" "LIBGL_ALWAYS_SOFTWARE=1"
             "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache")
set(_app_icd "/usr/share/vulkan/icd.d/lvp_icd.json")
if(EXISTS "${_app_icd}")
  list(APPEND _app_env "VK_DRIVER_FILES=${_app_icd}" "VK_ICD_FILENAMES=${_app_icd}")
endif()
if(STK_SYSROOT_FOUND)
  list(APPEND _app_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()
set(_app_backends "")
if(STK_GPU_VULKAN)
  list(APPEND _app_backends vulkan)
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  list(APPEND _app_backends opengl)
endif()

if(NOT WIN32)
  add_executable(stk_app_viewer_gpu_tests viewer_gpu_main.cc test_viewer_python.cc viewer_support.cc)
  target_link_libraries(stk_app_viewer_gpu_tests PRIVATE stk_app stk_viewer_gpu stk_gfx GTest::gtest)
  target_compile_definitions(stk_app_viewer_gpu_tests PRIVATE
    STK_REPO_ROOT="${_app_repo}"
    STK_BRIDGE_FAKE="$<TARGET_FILE:stk-bridge-fake>"
    STK_APP_TEST_SCRATCH="${_app_scratch}"
    STK_APP_TEST_PYTHON="${_app_python}")
  set_target_properties(stk_app_viewer_gpu_tests PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
  foreach(_be ${_app_backends})
    add_test(NAME app_viewer_python_${_be} COMMAND stk_app_viewer_gpu_tests --gpu-backend ${_be})
    set_tests_properties(app_viewer_python_${_be} PROPERTIES
      LABELS "app;gpu;bridge" TIMEOUT 900 SKIP_RETURN_CODE 77 ENVIRONMENT "${_app_env}"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
  endforeach()

  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_Interpreter_FOUND AND TARGET stk-desktop)
    foreach(_be ${_app_backends})
      add_test(NAME app_viewer_e2e_${_be}
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/run_e2e.py
                --desktop $<TARGET_FILE:stk-desktop>
                --compare $<TARGET_FILE:stk-viewer-image-compare>
                --python ${_app_python} --repo ${_app_repo} --backend ${_be}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/e2e_${_be}
                --golden ${_app_golden}/e2e_muferro_domains.png
                --vtk ${CMAKE_SOURCE_DIR}/tests/viewer/fixtures/vtk/muferro_domains.png)
      set_tests_properties(app_viewer_e2e_${_be} PROPERTIES
        LABELS "app;gpu;e2e" TIMEOUT 900 SKIP_RETURN_CODE 77 ENVIRONMENT "${_app_env}"
        PASS_REGULAR_EXPRESSION "E2E PASS" FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|E2E FAIL")
    endforeach()
  endif()

  # Live windows: the application with the Viewer, a synthesized orbit drag, a pick and the Probe.
  add_executable(stk-viewer-live viewer_live.cc)
  target_link_libraries(stk-viewer-live PRIVATE stk_app stk_wm stk_bridge)
  set_target_properties(stk-viewer-live PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
  if(Python3_Interpreter_FOUND AND CMAKE_SYSTEM_NAME STREQUAL "Linux" AND _app_backends)
    list(GET _app_backends 0 _be)
    set(_sysroot_arg "")
    if(STK_SYSROOT_FOUND)
      set(_sysroot_arg --sysroot "${STK_SYSROOT}")
    endif()
    set(_live_env "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache" "LIBGL_ALWAYS_SOFTWARE=1")
    if(EXISTS "${_app_icd}")
      list(APPEND _live_env "VK_DRIVER_FILES=${_app_icd}" "VK_ICD_FILENAMES=${_app_icd}")
    endif()
    if(STK_SYSROOT_FOUND)
      list(APPEND _live_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
    endif()
    foreach(_server xvfb weston)
      # The GUI opens a payload at start (--open), draws it and quits without leaks (the Viewer's
      # GPU resources are released with the window's context current).
      add_test(NAME app_viewer_gui_open_${_server}
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/wm/run_with_display.py --server ${_server}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/g_${_server} ${_sysroot_arg}
                -- $<TARGET_FILE:stk-desktop> --gpu-backend ${_be} --no-bridge --no-save-layout --lang en
                   --open ${CMAKE_SOURCE_DIR}/tests/viewer/fixtures/muferro_domains.stkp --exit-after-frames 5)
      set_tests_properties(app_viewer_gui_open_${_server} PROPERTIES
        LABELS "app;gpu;window" TIMEOUT 180 SKIP_RETURN_CODE 77
        ENVIRONMENT "${_live_env};XDG_CONFIG_HOME=${CMAKE_CURRENT_BINARY_DIR}/config_${_server}"
        RESOURCE_LOCK display_${_server} PASS_REGULAR_EXPRESSION "frame\\(s\\) presented"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|cannot open")
      add_test(NAME app_viewer_window_${_server}
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/wm/run_with_display.py --server ${_server}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server} ${_sysroot_arg} --timeout 480
                -- $<TARGET_FILE:stk-viewer-live> --gpu-backend ${_be} --python ${_app_python}
                   --repo ${_app_repo} --workdir ${CMAKE_CURRENT_BINARY_DIR}/live_${_server}
                   --screenshot ${CMAKE_CURRENT_BINARY_DIR}/out/viewer_live_${_server}.png)
      set_tests_properties(app_viewer_window_${_server} PROPERTIES
        LABELS "app;gpu;window" TIMEOUT 600 SKIP_RETURN_CODE 77 ENVIRONMENT "${_live_env}"
        RESOURCE_LOCK display_${_server} PASS_REGULAR_EXPRESSION "PASS"
        FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
    endforeach()
  endif()
endif()
