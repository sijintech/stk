# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-project-tests project_test.cc script_test.cc)
target_link_libraries(stk-project-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-project-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-project-tests PROPERTIES LABELS "project" TIMEOUT 120 DISCOVERY_TIMEOUT 60)

add_executable(stk-project-render project_render.cc)
target_link_libraries(stk-project-render PRIVATE stk_jobs_test_support stk_gfx)
if(MSVC)
  target_compile_options(stk-project-render PRIVATE /W3 /utf-8 /bigobj)
endif()
set_target_properties(stk-project-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
# Reuse the software-GPU environment and supported backends established in jobs.cmake.
foreach(_lang en zh)
  foreach(_be ${_jobs_backends})
    add_test(NAME project_render_${_be}_${_lang} COMMAND stk-project-render
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_${_be}_${_lang}.png")
    set_tests_properties(project_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME python_render_${_be}_${_lang} COMMAND stk-project-render --editor python
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/python_${_be}_${_lang}.png")
    set_tests_properties(python_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
  endforeach()
endforeach()
