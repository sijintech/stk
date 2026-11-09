# SPDX-License-Identifier: GPL-2.0-or-later
# Real production report path. Only the public fixture is captured; no desktop capture fallback.
find_package(Threads REQUIRED)
add_library(stk_reports_native_ax_cpu STATIC reports_native_ax_protocol.cc reports_native_ax_process.cc)
target_compile_features(stk_reports_native_ax_cpu PUBLIC cxx_std_20)
target_link_libraries(stk_reports_native_ax_cpu PUBLIC Threads::Threads)
add_executable(stk-reports-native-ax-tests reports_native_ax_test.cc)
target_link_libraries(stk-reports-native-ax-tests PRIVATE stk_reports_native_ax_cpu)
add_test(NAME reports_native_ax_cpu COMMAND stk-reports-native-ax-tests)
set_tests_properties(reports_native_ax_cpu PROPERTIES LABELS "unit;app;document_preview" TIMEOUT 20
  FAIL_REGULAR_EXPRESSION "FAIL:" ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")

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
if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES)
  if(APPLE)
    target_sources(stk-reports-native-window PRIVATE reports_native_input_cocoa.mm)
    find_library(_reports_ax_services ApplicationServices REQUIRED)
    add_executable(stk-reports-native-ax-client reports_native_ax_helper.mm reports_native_ax_protocol.cc)
    target_link_libraries(stk-reports-native-ax-client PRIVATE "${_reports_ax_services}")
    target_compile_features(stk-reports-native-ax-client PRIVATE cxx_std_20)
    target_compile_options(stk-reports-native-ax-client PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
    # Test-only helper, outside the application/package bin directory; never installed.
    set_target_properties(stk-reports-native-ax-client PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED ON
      RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/native-ax-tools")
    target_link_libraries(stk-reports-native-window PRIVATE stk_reports_native_ax_cpu)
    target_compile_definitions(stk-reports-native-window PRIVATE
      STK_REPORTS_NATIVE_AX_HELPER="$<TARGET_FILE:stk-reports-native-ax-client>")
    add_dependencies(stk-reports-native-window stk-reports-native-ax-client)
  elseif(WIN32)
    target_sources(stk-reports-native-window PRIVATE reports_native_input_win32.cc)
  else()
    target_sources(stk-reports-native-window PRIVATE reports_native_input_unsupported.cc)
  endif()
endif()
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
  set(_reports_sources markdown html pdf)
  if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES)
    list(APPEND _reports_sources video html-video)
  endif()
  foreach(_source IN LISTS _reports_sources)
    add_test(NAME reports_native_${_source}_${_reports_native_backend} COMMAND "${STK_BRIDGE_TEST_PYTHON}"
      "${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py"
      --success-marker "PASS: production ReportsEditor native evidence" --timeout 570 --
      $<TARGET_FILE:stk-reports-native-window>
      --python "${STK_BRIDGE_TEST_PYTHON}" --gpu-backend ${_reports_native_backend} --source ${_source}
      --media-fixture "${_reports_spike}/fixtures/frozen-preview.mp4"
      --evidence-dir "${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}")
    set_tests_properties(reports_native_${_source}_${_reports_native_backend} PROPERTIES
      LABELS "project;gpu;window;document_preview" TIMEOUT 600
      RESOURCE_LOCK native_window
      FAIL_REGULAR_EXPRESSION "FAIL:|Error: Not freed memory|leaked")
    file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}-$<CONFIG>.txt"
      CONTENT "\"${STK_BRIDGE_TEST_PYTHON}\" \"${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py\" --success-marker \"PASS: production ReportsEditor native evidence\" --timeout 570 -- \"$<TARGET_FILE:stk-reports-native-window>\" --python \"${STK_BRIDGE_TEST_PYTHON}\" --gpu-backend ${_reports_native_backend} --source ${_source} --media-fixture \"${_reports_spike}/fixtures/frozen-preview.mp4\" --evidence-dir \"${CMAKE_CURRENT_BINARY_DIR}/reports-native-${_source}\"\n")
  endforeach()
  if(APPLE AND STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES)
    foreach(_source IN ITEMS video html-video)
      foreach(_arm IN ITEMS pre_seek_hide quiet_pre_seek_hide isolated_quiet_pre_seek_hide)
        set(_control reports_${_arm}_${_source}_metal)
        string(REPLACE "_" "-" _scenario "${_arm}")
        string(REPLACE "_" " " _description "${_arm}")
        # Keep "pre-seek" as a single term in the executable's success marker.
        string(REPLACE "pre seek" "pre-seek" _description "${_description}")
        add_test(NAME ${_control} COMMAND "${STK_BRIDGE_TEST_PYTHON}"
          "${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py"
          --success-marker "PASS: production ReportsEditor ${_description} control" --timeout 150 --
          $<TARGET_FILE:stk-reports-native-window>
          --python "${STK_BRIDGE_TEST_PYTHON}" --gpu-backend metal --source ${_source}
          --media-fixture "${_reports_spike}/fixtures/frozen-preview.mp4"
          --${_scenario}-control
          --evidence-dir "${CMAKE_CURRENT_BINARY_DIR}/reports-${_scenario}-${_source}")
        set_tests_properties(${_control} PROPERTIES LABELS "project;gpu;window;document_preview"
          TIMEOUT 180 RESOURCE_LOCK native_window
          FAIL_REGULAR_EXPRESSION "FAIL:|Error: Not freed memory|leaked")
      endforeach()
      foreach(_arm IN ITEMS visible_native_pause second_visible_native_pause hide_after_verified_native_pause
                            hide_without_repeat_native_pause hide_without_repeat_native_pause_dom
                            fresh_native_hide_dom fresh_native_visible_dom)
        set(_control reports_${_arm}_${_source}_metal)
        string(REPLACE "_" "-" _scenario "${_arm}")
        string(REPLACE "_" " " _description "${_arm}")
        add_test(NAME ${_control} COMMAND "${STK_BRIDGE_TEST_PYTHON}"
          "${CMAKE_SOURCE_DIR}/tests/check_native_evidence.py"
          --success-marker "PASS: Cocoa ${_description} diagnostic" --timeout 150 --
          $<TARGET_FILE:stk-reports-native-window>
          --python "${STK_BRIDGE_TEST_PYTHON}" --gpu-backend metal --source ${_source}
          --media-fixture "${_reports_spike}/fixtures/frozen-preview.mp4" --${_scenario}-control
          --evidence-dir "${CMAKE_CURRENT_BINARY_DIR}/reports-${_scenario}-${_source}")
        set_tests_properties(${_control} PROPERTIES LABELS "project;gpu;window;document_preview"
          TIMEOUT 180 RESOURCE_LOCK native_window
          FAIL_REGULAR_EXPRESSION "FAIL:|Error: Not freed memory|leaked")
      endforeach()
    endforeach()
  endif()
endif()
