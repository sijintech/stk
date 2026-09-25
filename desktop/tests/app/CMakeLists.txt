# SPDX-License-Identifier: GPL-2.0-or-later
# Application editor tests (desktop/tests/app). Each work package keeps its targets in its own
# <name>.cmake file here (WP9: jobs.cmake, WP10: viewer.cmake), so parallel additions do not touch
# a shared list.
# Added from desktop/CMakeLists.txt after tests/unit, tests/wm and tests/bridge (googletest, the
# fake bridge and tests/wm/support.cc come from there).

if(NOT TARGET stk_app OR NOT TARGET GTest::gtest_main)
  return()
endif()
include(GoogleTest)

file(GLOB _stk_app_test_parts "${CMAKE_CURRENT_SOURCE_DIR}/*.cmake")
list(SORT _stk_app_test_parts)
foreach(_part ${_stk_app_test_parts})
  include(${_part})
endforeach()
