# SPDX-License-Identifier: GPL-2.0-or-later
# Independently buildable editor modules. The common Editor/EditorContext contracts live
# in include/stk/app; project data and execution remain in the shared application services.
# Object libraries retain one final executable while avoiding cyclic static-library linkage.
function(stk_editor_module name)
  add_library(stk_editor_${name} OBJECT ${ARGN})
  target_include_directories(stk_editor_${name} PRIVATE ${CMAKE_CURRENT_LIST_DIR}/include)
  target_compile_features(stk_editor_${name} PRIVATE cxx_std_20)
  target_link_libraries(stk_editor_${name} PRIVATE stk_wm stk_ui_core stk_core stk_io stk_bridge stk_platform stk_viewer_gpu stk_viewer_model)
  if(MSVC)
    target_compile_options(stk_editor_${name} PRIVATE /W3 /utf-8 /bigobj)
  else()
    target_compile_options(stk_editor_${name} PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
  endif()
  target_sources(stk_app PRIVATE $<TARGET_OBJECTS:stk_editor_${name}>)
endfunction()

stk_editor_module(viewer
  src/editors/viewer_common.cc
  src/editors/viewer_editor.cc
  src/editors/viewer_panels.cc
)

stk_editor_module(jobs
  src/editors/jobs_editor.cc
  src/editors/jobs_logs.cc
  src/editors/jobs_transfers.cc
)

stk_editor_module(project
  src/editors/project_editor.cc
  src/editors/project_review_view.cc
  src/editors/project_discussion_view.cc
  src/editors/project_simulation_view.cc
  src/editors/simulation_target.cc
  src/editors/project_context_picker.cc
)

stk_editor_module(python
  src/editors/python_editor.cc
)

stk_editor_module(ai
  src/editors/ai_editor.cc
)

stk_editor_module(workspace
  src/editors/workspace_editor.cc
)

stk_editor_module(skills
  src/editors/skills_editor.cc
)

stk_editor_module(workflow
  src/editors/workflow_editor.cc
)

stk_editor_module(analysis
  src/editors/analysis_graph_editor.cc
)

stk_editor_module(table
  src/project_table_editor.cc
  src/table_workbench.cc
  src/editors/table_editor.cc
)

stk_editor_module(files
  src/project_file_tree.cc
  src/editors/files_editor.cc
)

stk_editor_module(reports
  src/project_reports.cc
  src/editors/reports_editor.cc
  src/editors/reports_create_view.cc
)
