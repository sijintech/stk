# SPDX-License-Identifier: GPL-2.0-or-later
# Real production report path. Only the public fixture is captured; no desktop capture fallback.
if(NOT STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW OR NOT TARGET stk_document_native OR NOT TARGET stk_app)
  return()
endif()
get_filename_component(_reports_spike "${CMAKE_CURRENT_LIST_DIR}/../../spike/document_preview" ABSOLUTE)
if(APPLE)
  set(_reports_capture "${_reports_spike}/window_evidence_cocoa.mm")
  set(_reports_scroll reports_native_scroll_cocoa.mm)
elseif(WIN32)
  set(_reports_capture "${_reports_spike}/window_evidence_win32.cc")
  set(_reports_scroll reports_native_scroll_win32.cc)
else()
  set(_reports_capture "${_reports_spike}/window_evidence_unsupported.cc")
  set(_reports_scroll reports_native_scroll_unsupported.cc)
endif()
add_executable(stk-reports-native-window reports_native_window.cc ${_reports_capture} ${_reports_scroll}
  "${_reports_spike}/evidence_pixels.cc" "${_reports_spike}/fixture.cc")
target_link_libraries(stk-reports-native-window PRIVATE stk_app stk_document_native)
get_filename_component(_reports_repo "${CMAKE_SOURCE_DIR}/.." ABSOLUTE)
target_compile_definitions(stk-reports-native-window PRIVATE STK_REPO_ROOT="${_reports_repo}")
set_target_properties(stk-reports-native-window PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(APPLE)
  find_library(_reports_appkit AppKit REQUIRED)
  find_library(_reports_sck ScreenCaptureKit REQUIRED)
  find_library(_reports_webkit WebKit REQUIRED)
  find_library(_reports_cg CoreGraphics REQUIRED)
  target_link_libraries(stk-reports-native-window PRIVATE "${_reports_appkit}" "${_reports_sck}"
    "${_reports_webkit}" "${_reports_cg}")
  target_compile_options(stk-reports-native-window PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
  set_target_properties(stk-reports-native-window PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED ON)
  set(_reports_native_backend metal)
elseif(WIN32)
  target_link_libraries(stk-reports-native-window PRIVATE d3d11 dxgi dwmapi windowsapp runtimeobject opengl32 comctl32)
  target_compile_options(stk-reports-native-window PRIVATE /utf-8 /bigobj)
  set(_reports_native_backend opengl)
endif()
if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW AND (APPLE OR WIN32))
  foreach(_source markdown html pdf)
    add_test(NAME reports_native_${_source}_${_reports_native_backend} COMMAND "${STK_BRIDGE_TEST_PYTHON}"
      "${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py"
      --success-marker "PASS: production ReportsEditor native evidence" --timeout 570 --
      $<TARGET_FILE:stk-reports-native-window>
      --python "${STK_BRIDGE_TEST_PYTHON}" --gpu-backend ${_reports_native_backend} --source ${_source}
      --evidence-dir "${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}")
    set_tests_properties(reports_native_${_source}_${_reports_native_backend} PROPERTIES
      LABELS "project;gpu;window;document_preview" TIMEOUT 600
      RESOURCE_LOCK native_window
      FAIL_REGULAR_EXPRESSION "FAIL:|Error: Not freed memory|leaked")
    file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}-$<CONFIG>.txt"
      CONTENT "\"${STK_BRIDGE_TEST_PYTHON}\" \"${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py\" --success-marker \"PASS: production ReportsEditor native evidence\" --timeout 570 -- \"$<TARGET_FILE:stk-reports-native-window>\" --python \"${STK_BRIDGE_TEST_PYTHON}\" --gpu-backend ${_reports_native_backend} --source ${_source} --evidence-dir \"${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}\"\n")
  endforeach()
endif()
