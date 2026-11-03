# SPDX-License-Identifier: GPL-2.0-or-later
add_executable(stk-peer-app-tests peer_test.cc)
target_link_libraries(stk-peer-app-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
if(MSVC)
  target_compile_options(stk-peer-app-tests PRIVATE /W3 /utf-8 /bigobj)
endif()
gtest_discover_tests(stk-peer-app-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
  TEST_LIST stk_peer_app_tests
  PROPERTIES TIMEOUT 120
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
# Keep list-valued labels out of the generated Windows POST_BUILD command.
# Apply them after CTest includes the discovered test names, as for Materials.
set(_peer_labels_file "${CMAKE_CURRENT_BINARY_DIR}/stk-peer-test-labels.cmake")
file(GENERATE OUTPUT "${_peer_labels_file}" CONTENT [=[
if(stk_peer_app_tests)
  set_tests_properties(${stk_peer_app_tests} PROPERTIES LABELS "peer;project")
endif()
]=])
set_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${_peer_labels_file}")

# Requires an explicitly prepared, verified installation at test runtime. This
# acceptance target is separate from the portable CPU suite and never skips.
option(STK_PEER_NATIVE_APP_ACCEPTANCE "Build installed-helper Peer UI acceptance" OFF)
if(STK_PEER_NATIVE_APP_ACCEPTANCE)
  add_executable(stk-peer-native-app-tests peer_test.cc)
  target_link_libraries(stk-peer-native-app-tests PRIVATE stk_jobs_test_support GTest::gtest_main)
  target_compile_definitions(stk-peer-native-app-tests PRIVATE STK_PEER_NATIVE_ACCEPTANCE=1)
  if(MSVC)
    target_compile_options(stk-peer-native-app-tests PRIVATE /W3 /utf-8 /bigobj)
  endif()
  gtest_discover_tests(stk-peer-native-app-tests DISCOVERY_TIMEOUT 60 NO_PRETTY_VALUES
    TEST_FILTER "PeerNativeMouse.*:PeerNativeReceiverMouse.*"
    TEST_LIST stk_peer_native_app_tests
    PROPERTIES TIMEOUT 180
    ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
    ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
  set(_peer_native_labels_file "${CMAKE_CURRENT_BINARY_DIR}/stk-peer-native-test-labels.cmake")
  file(GENERATE OUTPUT "${_peer_native_labels_file}" CONTENT [=[
if(stk_peer_native_app_tests)
  set_tests_properties(${stk_peer_native_app_tests} PROPERTIES LABELS "peer;project;installed-helper")
endif()
]=])
  set_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${_peer_native_labels_file}")
endif()
