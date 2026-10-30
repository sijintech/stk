# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-materials-tests materials_editor_test.cc materials_state_test.cc)
target_link_libraries(stk-materials-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-materials-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-materials-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
  TEST_LIST stk_materials_tests
  PROPERTIES TIMEOUT 120
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
# GoogleTest discovery flattens list-valued properties and breaks Windows quoting.
# Apply the complete label list after CTest has included the discovered test names.
set(_materials_labels_file "${CMAKE_CURRENT_BINARY_DIR}/stk-materials-test-labels.cmake")
file(GENERATE OUTPUT "${_materials_labels_file}" CONTENT [=[
if(stk_materials_tests)
  set_tests_properties(${stk_materials_tests} PROPERTIES LABELS "materials;project")
endif()
]=])
set_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${_materials_labels_file}")

# Production MaterialsEditor draw_gpu, actual fonts/offscreen GPU pixels, strict local bridge.
# Both images are checked inside the plot rather than accepting its small legend swatches.
add_executable(stk-materials-render materials_render.cc)
target_link_libraries(stk-materials-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-materials-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-materials-render PRIVATE /W3 /utf-8 /bigobj)
endif()
set(_materials_sysroot_arg "")
if(STK_SYSROOT_FOUND)
  set(_materials_sysroot_arg --sysroot "${STK_SYSROOT}")
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      set(_materials_name materials_${_mode}_render_${_be}_${_lang})
      if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        if(NOT Python3_Interpreter_FOUND)
          # The required-test checker must see absent cases as missing, not a fabricated pass.
          continue()
        endif()
        add_test(NAME ${_materials_name}
          COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/../wm/run_with_display.py"
            --server xvfb --workdir "${CMAKE_CURRENT_BINARY_DIR}/d_${_materials_name}"
            --size 1440x1100 ${_materials_sysroot_arg}
            -- $<TARGET_FILE:stk-materials-render> --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
              --export "${_jobs_out}/${_materials_name}")
        set_tests_properties(${_materials_name} PROPERTIES RESOURCE_LOCK display_xvfb)
      else()
        # Only backends already supported by the existing render targets are registered.
        add_test(NAME ${_materials_name} COMMAND stk-materials-render
          --mode ${_mode} --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/${_materials_name}")
      endif()
      set_tests_properties(${_materials_name} PROPERTIES LABELS "materials;project;gpu" TIMEOUT 180
        ENVIRONMENT "${_jobs_env};STK_TOKEN_PLAN_API_KEY="
        ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:"
        PASS_REGULAR_EXPRESSION "actual MaterialsEditor GPU pixels"
        FAIL_REGULAR_EXPRESSION "FAIL|leaked|Error: Not freed memory")
    endforeach()
  endforeach()
endforeach()
