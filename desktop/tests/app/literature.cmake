# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-literature-app-tests literature_test.cc literature_page_test.cc)
target_link_libraries(stk-literature-app-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
target_compile_definitions(stk-literature-app-tests PRIVATE STK_LITERATURE_PAGE_FIXTURE="${CMAKE_CURRENT_SOURCE_DIR}/fixtures/literature-page-1.json")
if(MSVC)
  target_compile_options(stk-literature-app-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-literature-app-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
  TEST_LIST stk_literature_tests
  PROPERTIES TIMEOUT 180
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
# Apply the list-valued labels after discovery so MSVC command quoting cannot
# split the list next to a CMake executable installed under Program Files.
set(_literature_labels_file "${CMAKE_CURRENT_BINARY_DIR}/stk-literature-test-labels.cmake")
file(GENERATE OUTPUT "${_literature_labels_file}" CONTENT [=[
if(stk_literature_tests)
  set_tests_properties(${stk_literature_tests} PROPERTIES LABELS "literature;cpu")
endif()
]=])
set_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${_literature_labels_file}")
