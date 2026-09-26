# SPDX-License-Identifier: GPL-2.0-or-later
# stk_bridge tests (label `bridge`):
#   stk-bridge-tests   gtest: protocol units, ChildProcess, the client against stk-bridge-fake (a
#                      scripted fake bridge), and against the real Python bridge (skipped with the
#                      reason when STK_BRIDGE_TEST_PYTHON / python3 cannot import suan.desktop_bridge).
#   stk-wm-post-check  WindowManager::post / executor under Xvfb and weston (labels `bridge;window`),
#                      when the engine (stk_wm) is built.
# Added from desktop/CMakeLists.txt after tests/unit (which provides googletest).

if(NOT TARGET stk_bridge)
  return()
endif()
if(NOT TARGET GTest::gtest_main)
  message(STATUS "tests/bridge: skipped (googletest comes with tests/unit)")
  return()
endif()

set(STK_BRIDGE_TEST_PYTHON "" CACHE FILEPATH
  "Python for the stk_bridge integration tests (empty: $STK_BRIDGE_TEST_PYTHON, else python3 on PATH)")

get_filename_component(_repo_root "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(_scratch "${CMAKE_CURRENT_BINARY_DIR}/scratch")

if(NOT WIN32)
  add_executable(stk-bridge-fake fake_bridge.cc fake_jobs.cc)
  target_link_libraries(stk-bridge-fake PRIVATE stk_io stk_core)
endif()

add_executable(stk-bridge-tests
  support.cc
  test_client_fake.cc
  test_client_python.cc
  test_process.cc
  test_protocol.cc
)
target_link_libraries(stk-bridge-tests PRIVATE stk_bridge GTest::gtest_main)
target_compile_definitions(stk-bridge-tests PRIVATE
  STK_REPO_ROOT="${_repo_root}"
  STK_BRIDGE_TEST_SCRATCH="${_scratch}"
  STK_BRIDGE_TEST_PYTHON_DEFAULT="${STK_BRIDGE_TEST_PYTHON}")
if(TARGET stk-bridge-fake)
  target_compile_definitions(stk-bridge-tests PRIVATE STK_BRIDGE_FAKE="$<TARGET_FILE:stk-bridge-fake>")
else()
  target_compile_definitions(stk-bridge-tests PRIVATE STK_BRIDGE_FAKE="")
endif()
if(MSVC)
  target_compile_options(stk-bridge-tests PRIVATE /utf-8 /bigobj)
endif()
if(TARGET stk-bridge-fake)
  add_dependencies(stk-bridge-tests stk-bridge-fake)
endif()

include(GoogleTest)
if(WIN32)
  # The fake bridge and the process-group tests are POSIX; Windows builds everything and runs the
  # protocol units only (CI builds Windows without running tests).
  gtest_discover_tests(stk-bridge-tests TEST_FILTER "Framing.*:Decode.*:Encode.*:Classify.*:Errors.*:Retry.*:Schema.*:Types.*:Future.*:LogRing.*"
    PROPERTIES LABELS "bridge" DISCOVERY_TIMEOUT 60)
else()
  gtest_discover_tests(stk-bridge-tests
    PROPERTIES LABELS "bridge" TIMEOUT 600 DISCOVERY_TIMEOUT 60)
endif()

# WindowManager::post under a live display (needs the engine).
if(TARGET stk_wm AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  add_executable(stk-wm-post-check wm_post_check.cc)
  target_link_libraries(stk-wm-post-check PRIVATE stk_wm stk_bridge)
  set_target_properties(stk-wm-post-check PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_Interpreter_FOUND)
    set(_runner "${CMAKE_CURRENT_SOURCE_DIR}/../wm/run_with_display.py")
    set(_sysroot_arg "")
    if(STK_SYSROOT_FOUND)
      set(_sysroot_arg --sysroot "${STK_SYSROOT}")
    endif()
    set(_env "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache" "LIBGL_ALWAYS_SOFTWARE=1")
    if(STK_SYSROOT_FOUND)
      list(APPEND _env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}"
                       "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
    endif()
    set(_be opengl)
    if(NOT STK_GPU_OPENGL AND STK_GPU_VULKAN)
      set(_be vulkan)
    endif()
    foreach(_server xvfb weston)
      set(_name bridge_wm_post_${_server})
      add_test(NAME ${_name}
        COMMAND ${Python3_EXECUTABLE} ${_runner} --server ${_server}
                --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server} ${_sysroot_arg}
                -- $<TARGET_FILE:stk-wm-post-check> --gpu-backend ${_be}
                   --fake-bridge $<TARGET_FILE:stk-bridge-fake>)
      set_tests_properties(${_name} PROPERTIES
        LABELS "bridge;window" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env}"
        RESOURCE_LOCK display_${_server}
        FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
    endforeach()
    # The X11 fallback path (condition-variable poll) as well.
    add_test(NAME bridge_wm_post_xvfb_pollmode
      COMMAND ${Python3_EXECUTABLE} ${_runner} --server xvfb
              --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_xvfb_poll ${_sysroot_arg}
              -- $<TARGET_FILE:stk-wm-post-check> --gpu-backend ${_be})
    set_tests_properties(bridge_wm_post_xvfb_pollmode PROPERTIES
      LABELS "bridge;window" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env};STK_WM_WAIT=poll"
      RESOURCE_LOCK display_xvfb
      FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
  endif()
endif()
