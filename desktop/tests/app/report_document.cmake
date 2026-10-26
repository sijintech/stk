# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-report-document-tests report_document_host_test.cc)
target_link_libraries(stk-report-document-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-report-document-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
# Keep discovery properties single-valued: semicolon labels break the generated MSVC command.
gtest_discover_tests(stk-report-document-tests DISCOVERY_TIMEOUT 60
  PROPERTIES LABELS "project" TIMEOUT 30
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
