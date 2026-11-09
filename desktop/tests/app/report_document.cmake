# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-report-document-tests report_document_host_test.cc)
target_link_libraries(stk-report-document-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-report-document-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
# Keep discovery properties single-valued: semicolon labels break the generated MSVC command.
# The live-window suite runs only through the dedicated display test below.
gtest_discover_tests(stk-report-document-tests DISCOVERY_TIMEOUT 60
  TEST_FILTER "-ReportDocumentHostDisplay.*"
  PROPERTIES LABELS "project" TIMEOUT 30
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")

# Linux only: a real WindowManager/AppShell window on a private Xvfb with a mock native view.
find_package(Python3 COMPONENTS Interpreter)
set(_report_document_backend "")
if(STK_GPU_VULKAN)
  set(_report_document_backend vulkan)
elseif(STK_GPU_OPENGL)
  set(_report_document_backend opengl)
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND Python3_Interpreter_FOUND AND _report_document_backend)
  set(_report_document_env "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache" "LIBGL_ALWAYS_SOFTWARE=1"
      "STK_TEST_GPU_BACKEND=${_report_document_backend}" "STK_TOKEN_PLAN_API_KEY=")
  if(STK_TEST_VK_ICD AND EXISTS "${STK_TEST_VK_ICD}")
    list(APPEND _report_document_env "VK_DRIVER_FILES=${STK_TEST_VK_ICD}" "VK_ICD_FILENAMES=${STK_TEST_VK_ICD}")
  endif()
  set(_report_document_sysroot "")
  if(STK_SYSROOT_FOUND)
    list(APPEND _report_document_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}"
         "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
    set(_report_document_sysroot --sysroot "${STK_SYSROOT}")
  endif()
  add_test(NAME report_document_display_xvfb
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../wm/run_with_display.py --server xvfb
            --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_report_document_xvfb ${_report_document_sysroot}
            -- $<TARGET_FILE:stk-report-document-tests> --gtest_filter=ReportDocumentHostDisplay.*)
  set_tests_properties(report_document_display_xvfb PROPERTIES
    LABELS "window;project" TIMEOUT 180 SKIP_RETURN_CODE 77 RESOURCE_LOCK display_xvfb
    ENVIRONMENT "${_report_document_env}" ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:"
    PASS_REGULAR_EXPRESSION "\\[  PASSED  \\] 1 test"
    FAIL_REGULAR_EXPRESSION "FAIL|SKIPPED|leaked|Error: Not freed memory")
endif()
