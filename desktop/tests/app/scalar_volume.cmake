# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-scalar-volume-tests scalar_volume_test.cc)
target_link_libraries(stk-scalar-volume-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-scalar-volume-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-scalar-volume-tests PROPERTIES LABELS "project;scalar" TIMEOUT 120 DISCOVERY_TIMEOUT 60)

add_executable(stk-scalar-volume-render scalar_volume_render.cc)
target_link_libraries(stk-scalar-volume-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-scalar-volume-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-scalar-volume-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME scalar_volume_${_mode}_render_${_be}_${_lang} COMMAND stk-scalar-volume-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/scalar_volume_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(scalar_volume_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;scalar;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()
