# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_app: the application shell (top bar, status bar, default layout, layout persistence), the
# AppStore, the editor registry and the WP3 placeholder editors (Jobs, Viewer, Properties, Logs,
# Probe, Transfers, Bridge log). See include/stk/app/*.hh.

if(NOT TARGET stk_wm OR NOT TARGET stk_bridge OR NOT TARGET stk_viewer_gpu)
  message(STATUS "stk_app: skipped (needs stk_wm, stk_bridge and stk_viewer_gpu)")
  return()
endif()

set(_stk_desktop_dir ${CMAKE_CURRENT_LIST_DIR}/../../..)
get_filename_component(_stk_desktop_dir ${_stk_desktop_dir} ABSOLUTE)

add_library(stk_app STATIC
  src/app_store.cc
  src/bridge_status.cc
  src/editor.cc
  src/editor_area.cc
  src/editors.cc
  src/editors/viewer_common.cc
  src/editors/viewer_editor.cc
  src/editors/viewer_panels.cc
  src/shell.cc
  src/viewer_export.cc
  src/viewer_state.cc
)
target_include_directories(stk_app PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_app PUBLIC cxx_std_20)
# stk_bridge (CPU only): BridgeStatus mirrors the bridge client into the status bar.
target_link_libraries(stk_app PUBLIC stk_wm stk_ui_core stk_core stk_bridge)
# WP10: the Viewer editor draws with stk_viewer_gpu; ViewerState decodes payloads (stk_io) and
# formats labels (stk_viewer_model).
target_link_libraries(stk_app PUBLIC stk_viewer_gpu stk_viewer_model stk_io)
target_compile_definitions(stk_app PRIVATE STK_APP_VERSION="${PROJECT_VERSION}")
option(STK_APP_SOURCE_I18N_FALLBACK "Let binaries fall back to the source tree for message catalogs" ON)
if(STK_APP_SOURCE_I18N_FALLBACK)
  target_compile_definitions(stk_app PRIVATE STK_APP_SOURCE_I18N_DIR="${_stk_desktop_dir}/app/i18n")
endif()
if(MSVC)
  target_compile_options(stk_app PRIVATE /W3 /utf-8)
else()
  target_compile_options(stk_app PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()

# Message catalogs next to the executables (<build>/bin/i18n), like an install
# (<prefix>/share/stk-desktop/i18n).
if(DEFINED STK_DESKTOP_BIN_DIR)
  file(GLOB _stk_catalogs "${_stk_desktop_dir}/app/i18n/*.json")
  set(_staged "")
  foreach(_f ${_stk_catalogs})
    get_filename_component(_n "${_f}" NAME)
    add_custom_command(OUTPUT "${STK_DESKTOP_BIN_DIR}/i18n/${_n}"
      COMMAND ${CMAKE_COMMAND} -E copy_if_different "${_f}" "${STK_DESKTOP_BIN_DIR}/i18n/${_n}"
      DEPENDS "${_f}" COMMENT "Staging catalog ${_n}")
    list(APPEND _staged "${STK_DESKTOP_BIN_DIR}/i18n/${_n}")
  endforeach()
  add_custom_target(stk_app_catalogs DEPENDS ${_staged})
  add_dependencies(stk_app stk_app_catalogs)
endif()
install(DIRECTORY "${_stk_desktop_dir}/app/i18n/" DESTINATION share/stk-desktop/i18n FILES_MATCHING PATTERN "*.json")
