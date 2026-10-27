# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-report-generation-tests project_report_generation_test.cc)
target_link_libraries(stk-report-generation-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-report-generation-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-report-generation-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
  PROPERTIES LABELS "project" TIMEOUT 120
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
