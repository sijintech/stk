# SPDX-License-Identifier: GPL-2.0-or-later
#
# WP9 Jobs editor tests (included from tests/app/CMakeLists.txt; label `jobs`):
#   stk-jobs-tests   gtest, no GPU: the submit form (TaskSpec rules, shlex), JobsState against the
#                    scripted fake bridge (stk-bridge-fake --jobs: connections, workspaces, uploads,
#                    idempotent submit and retry, watch, logs, events, verified downloads and PNG
#                    preview, hub review and the review_policy refusal, re-inspection after a
#                    restart, closing never cancels), layout goldens of the Jobs editor (en / zh,
#                    golden/jobs_*.json, STK_UPDATE_GOLDENS=1 rewrites them), and the integration
#                    run against the real Python bridge and a loopback Runtime (jobs_fixture.py;
#                    skipped with the reason when Python / the Runtime cannot run here).
#   stk-jobs-render  (label `gpu`) the Jobs editor with a populated fake task list rendered
#                    headless, compared with golden/jobs_editor_*.png by stk-png-diff.
#   stk-jobs-live    (label `window`) a live window on Xvfb / weston: Chinese typed into the task
#                    name through synthesized IME events, submitted to the fake bridge.

get_filename_component(_jobs_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(_jobs_scratch "${CMAKE_CURRENT_BINARY_DIR}/scratch")
set(_jobs_golden "${CMAKE_CURRENT_SOURCE_DIR}/golden")
set(_jobs_out "${CMAKE_CURRENT_BINARY_DIR}/out")
file(MAKE_DIRECTORY "${_jobs_out}")

add_library(stk_jobs_test_support STATIC
  jobs_support.cc
  ../bridge/support.cc
  ../wm/support.cc
)
target_include_directories(stk_jobs_test_support PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(stk_jobs_test_support PUBLIC stk_app stk_wm stk_bridge GTest::gtest)
set(_jobs_fake "")
if(TARGET stk-bridge-fake)
  set(_jobs_fake "$<TARGET_FILE:stk-bridge-fake>")
endif()
target_compile_definitions(stk_jobs_test_support PUBLIC
  STK_DESKTOP_DIR="${CMAKE_SOURCE_DIR}"
  STK_REPO_ROOT="${_jobs_repo}"
  STK_BRIDGE_TEST_SCRATCH="${_jobs_scratch}"
  STK_BRIDGE_FAKE="${_jobs_fake}"
  STK_JOBS_GOLDEN_DIR="${_jobs_golden}"
  STK_BRIDGE_TEST_PYTHON_DEFAULT="${STK_BRIDGE_TEST_PYTHON}")

add_executable(stk-jobs-tests
  jobs_spec_test.cc
  jobs_state_test.cc
  jobs_layout_test.cc
  jobs_python_test.cc
)
target_link_libraries(stk-jobs-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(TARGET stk-bridge-fake)
  add_dependencies(stk-jobs-tests stk-bridge-fake)
endif()
foreach(_t stk_jobs_test_support stk-jobs-tests)
  if(MSVC)
    target_compile_options(${_t} PRIVATE /W3 /utf-8 /bigobj)
  else()
    target_compile_options(${_t} PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
  endif()
endforeach()
if(WIN32)
  gtest_discover_tests(stk-jobs-tests TEST_FILTER "JobsSpec.*:JobsLayout.*"
    PROPERTIES LABELS "jobs" DISCOVERY_TIMEOUT 60)
else()
  gtest_discover_tests(stk-jobs-tests PROPERTIES LABELS "jobs" TIMEOUT 600 DISCOVERY_TIMEOUT 60)
endif()

# -------------------------------------------------------------------------------------------
# GPU golden and live window (need the engine).

add_executable(stk-jobs-render jobs_render.cc)
target_link_libraries(stk-jobs-render PRIVATE stk_jobs_test_support stk_gfx)
add_executable(stk-jobs-live jobs_live.cc)
target_link_libraries(stk-jobs-live PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-jobs-render stk-jobs-live PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(TARGET stk-bridge-fake)
  add_dependencies(stk-jobs-live stk-bridge-fake)
endif()

set(_jobs_env "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache" "LIBGL_ALWAYS_SOFTWARE=1")
if(STK_TEST_VK_ICD AND EXISTS "${STK_TEST_VK_ICD}")
  list(APPEND _jobs_env "VK_DRIVER_FILES=${STK_TEST_VK_ICD}" "VK_ICD_FILENAMES=${STK_TEST_VK_ICD}")
endif()
if(STK_SYSROOT_FOUND)
  list(APPEND _jobs_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()
set(_jobs_env_headless ${_jobs_env} "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless")
set(_jobs_backends "")
if(STK_GPU_VULKAN)
  list(APPEND _jobs_backends vulkan)
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  list(APPEND _jobs_backends opengl)
endif()
if(STK_GPU_METAL)
  list(APPEND _jobs_backends metal)
endif()

foreach(_lang en zh)
  foreach(_be ${_jobs_backends})
    set(_png "${_jobs_out}/jobs_${_be}_${_lang}.png")
    add_test(NAME jobs_render_${_be}_${_lang}
      COMMAND stk-jobs-render --gpu-backend ${_be} --lang ${_lang} --export ${_png} --work ${_jobs_out}/render_${_be}_${_lang})
    set_tests_properties(jobs_render_${_be}_${_lang} PROPERTIES
      LABELS "gpu;jobs" TIMEOUT 300 ENVIRONMENT "${_jobs_env_headless}" FIXTURES_SETUP jobs_render_${_be}_${_lang}
      PASS_REGULAR_EXPRESSION "wrote" FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME jobs_golden_${_be}_${_lang}
      COMMAND stk-png-diff ${_png} ${_jobs_golden}/jobs_editor_${_lang}.png)
    set_tests_properties(jobs_golden_${_be}_${_lang} PROPERTIES
      LABELS "gpu;jobs" FIXTURES_REQUIRED jobs_render_${_be}_${_lang})
  endforeach()
endforeach()

find_package(Python3 COMPONENTS Interpreter)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND Python3_Interpreter_FOUND AND _jobs_backends AND TARGET stk-bridge-fake)
  set(_jobs_runner "${CMAKE_CURRENT_SOURCE_DIR}/../wm/run_with_display.py")
  set(_jobs_sysroot_arg "")
  if(STK_SYSROOT_FOUND)
    set(_jobs_sysroot_arg --sysroot "${STK_SYSROOT}")
  endif()
  list(GET _jobs_backends 0 _be)
  foreach(_server xvfb weston)
    set(_name jobs_live_${_server})
    add_test(NAME ${_name}
      COMMAND ${Python3_EXECUTABLE} ${_jobs_runner} --server ${_server}
              --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server} ${_jobs_sysroot_arg}
              -- $<TARGET_FILE:stk-jobs-live> --gpu-backend ${_be} --fake-bridge $<TARGET_FILE:stk-bridge-fake>
                 --work ${_jobs_out}/live_${_server} --screenshot ${_jobs_out}/jobs_live_${_server}.png)
    set_tests_properties(${_name} PROPERTIES
      LABELS "window;jobs" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_jobs_env}"
      RESOURCE_LOCK display_${_server} PASS_REGULAR_EXPRESSION "PASS"
      FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
  endforeach()
endif()
