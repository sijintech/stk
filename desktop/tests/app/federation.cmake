# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-federation-tests federation_test.cc)
target_link_libraries(stk-federation-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-federation-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-federation-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
  TEST_LIST stk_federation_tests
  PROPERTIES TIMEOUT 120
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
set(_federation_labels_file "${CMAKE_CURRENT_BINARY_DIR}/stk-federation-test-labels.cmake")
file(GENERATE OUTPUT "${_federation_labels_file}" CONTENT [=[
if(stk_federation_tests)
  set_tests_properties(${stk_federation_tests} PROPERTIES LABELS "federation;project")
endif()
]=])
set_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${_federation_labels_file}")
