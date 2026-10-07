# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-project-tests project_test.cc script_test.cc project_table_view_test.cc
  project_context_selection_test.cc saved_review_test.cc focus_test.cc workspace_navigation_test.cc analysis_graph_view_test.cc
  analysis_graph_canvas_test.cc viewer_graph_inspection_test.cc
  analysis_graph_state_test.cc analysis_graph_editor_test.cc viewer_graph_configuration_test.cc
  project_analyses_test.cc analysis_documents_editor_test.cc project_analysis_runs_test.cc
  analysis_parameter_draft_test.cc analysis_parameters_editor_test.cc
  analysis_graph_run_state_test.cc analysis_graph_run_editor_test.cc analysis_outputs_editor_test.cc
  analysis_input_reuse_test.cc analysis_input_reuse_editor_test.cc
  analysis_result_inspection_test.cc analysis_result_inspection_editor_test.cc
  analysis_table_grid_test.cc analysis_table_grid_editor_test.cc skills_catalog_test.cc analysis_links_editor_test.cc)
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
    foreach(_review review review_errors drafts discussion requests filter simulation batches ai ai_narrow ai_stream ai_proposal ai_proposal_narrow ai_scope ai_scope_narrow ai_focus workspace workspace_narrow skills skills_narrow)
      add_test(NAME project_${_review}_render_${_be}_${_lang} COMMAND stk-project-render --editor ${_review}
        --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_${_review}_${_be}_${_lang}.png")
      set_tests_properties(project_${_review}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
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
    add_test(NAME expression_render_${_be}_${_lang} COMMAND stk-project-render --editor expression
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/expression_${_be}_${_lang}.png")
    set_tests_properties(expression_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_manage_render_${_be}_${_lang} COMMAND stk-project-render --editor manage
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_manage_${_be}_${_lang}.png")
    set_tests_properties(project_manage_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_files_render_${_be}_${_lang} COMMAND stk-project-render --editor files
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_files_${_be}_${_lang}.png")
    set_tests_properties(project_files_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_snapshots_render_${_be}_${_lang} COMMAND stk-project-render --editor snapshots
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_snapshots_${_be}_${_lang}.png")
    set_tests_properties(project_snapshots_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME offline_workbench_render_${_be}_${_lang} COMMAND stk-project-render --editor offline
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/offline_workbench_${_be}_${_lang}.png")
    set_tests_properties(offline_workbench_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_csv_render_${_be}_${_lang} COMMAND stk-project-render --editor csv
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_csv_${_be}_${_lang}.png")
    set_tests_properties(project_csv_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_sweep_render_${_be}_${_lang} COMMAND stk-project-render --editor sweep
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_sweep_${_be}_${_lang}.png")
    set_tests_properties(project_sweep_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_recent_render_${_be}_${_lang} COMMAND stk-project-render --editor recent
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_recent_${_be}_${_lang}.png")
    set_tests_properties(project_recent_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    add_test(NAME project_runs_render_${_be}_${_lang} COMMAND stk-project-render --editor runs
      --gpu-backend ${_be} --lang ${_lang} --export "${_jobs_out}/project_runs_${_be}_${_lang}.png")
    set_tests_properties(project_runs_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
      ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
  endforeach()
endforeach()

add_executable(stk-analysis-graph-run-render analysis_graph_run_render.cc)
target_link_libraries(stk-analysis-graph-run-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-graph-run-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-graph-run-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_graph_run_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-graph-run-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_graph_run_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_graph_run_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-table-grid-render analysis_table_grid_render.cc)
target_link_libraries(stk-analysis-table-grid-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-table-grid-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-table-grid-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_table_grid_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-table-grid-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_table_grid_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_table_grid_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-result-inspection-render analysis_result_inspection_render.cc)
target_link_libraries(stk-analysis-result-inspection-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-result-inspection-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-result-inspection-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode values_wide values_narrow issues_wide issues_narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_result_inspection_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-result-inspection-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_result_inspection_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_result_inspection_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-input-reuse-render analysis_input_reuse_render.cc)
target_link_libraries(stk-analysis-input-reuse-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-input-reuse-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-input-reuse-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_input_reuse_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-input-reuse-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_input_reuse_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_input_reuse_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-outputs-render analysis_outputs_render.cc)
target_link_libraries(stk-analysis-outputs-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-outputs-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-outputs-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_outputs_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-outputs-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_outputs_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_outputs_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-links-render analysis_links_render.cc)
target_link_libraries(stk-analysis-links-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-links-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-links-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_graph_edit_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-links-render
        --scenario edit --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_graph_edit_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_graph_edit_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
      add_test(NAME analysis_links_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-links-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_links_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_links_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-parameters-render analysis_parameters_render.cc)
target_link_libraries(stk-analysis-parameters-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-parameters-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-parameters-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_parameters_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-parameters-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_parameters_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_parameters_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-runs-render analysis_runs_render.cc)
target_link_libraries(stk-analysis-runs-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-runs-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-runs-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode prepare_wide prepare_narrow result_wide result_narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_runs_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-runs-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_runs_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_runs_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()

add_executable(stk-analysis-graph-render analysis_graph_render.cc)
target_link_libraries(stk-analysis-graph-render PRIVATE stk_jobs_test_support stk_gfx)
set_target_properties(stk-analysis-graph-render PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-analysis-graph-render PRIVATE /W3 /utf-8 /bigobj)
endif()
foreach(_mode wide narrow saved_wide saved_narrow)
  foreach(_lang en zh)
    foreach(_be ${_jobs_backends})
      add_test(NAME analysis_graph_${_mode}_render_${_be}_${_lang} COMMAND stk-analysis-graph-render
        --mode ${_mode} --gpu-backend ${_be} --lang ${_lang}
        --export "${_jobs_out}/analysis_graph_${_mode}_${_be}_${_lang}.png")
      set_tests_properties(analysis_graph_${_mode}_render_${_be}_${_lang} PROPERTIES LABELS "project;gpu" TIMEOUT 120
        ENVIRONMENT "${_jobs_env_headless}" PASS_REGULAR_EXPRESSION "wrote"
        FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory|FAIL")
    endforeach()
  endforeach()
endforeach()
