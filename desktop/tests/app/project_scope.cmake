# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-project-scope-tests project_scope_test.cc)
target_link_libraries(stk-project-scope-tests PRIVATE stk_app GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-project-scope-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-project-scope-tests DISCOVERY_TIMEOUT 60
  PROPERTIES LABELS "project;unit" TIMEOUT 30
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
