# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk-desktop: the STK desktop application (GUI + --headless export).

file(READ "${CMAKE_SOURCE_DIR}/engine/third_party/blender/UPSTREAM.json" _upstream)
string(JSON STK_BLENDER_VERSION GET "${_upstream}" version)

set(STK_DESKTOP_GIT "")
find_package(Git QUIET)
if(GIT_FOUND)
  execute_process(COMMAND ${GIT_EXECUTABLE} rev-parse --short=10 HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} OUTPUT_VARIABLE STK_DESKTOP_GIT
    OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
endif()

# The sample screen is shared with the GPU tests (tests/wm).
add_library(stk_app_sample STATIC sample_screen.cc)
target_include_directories(stk_app_sample PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(stk_app_sample PUBLIC stk_wm)

add_executable(stk-desktop main.cc)
target_link_libraries(stk-desktop PRIVATE stk_app_sample stk_wm)
target_compile_definitions(stk-desktop PRIVATE
  STK_DESKTOP_VERSION="${PROJECT_VERSION}"
  STK_BLENDER_VERSION="${STK_BLENDER_VERSION}"
  STK_DESKTOP_GIT="${STK_DESKTOP_GIT}")
set_target_properties(stk-desktop PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
foreach(_t stk_app_sample stk-desktop)
  if(MSVC)
    target_compile_options(${_t} PRIVATE /W3)
  else()
    target_compile_options(${_t} PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
  endif()
endforeach()
# Windows: console subsystem for now so --help / --headless print; packaging (WP12) decides.

install(TARGETS stk-desktop RUNTIME DESTINATION bin)
