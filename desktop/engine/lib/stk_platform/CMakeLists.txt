# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_platform: file dialogs (native through zenity / kdialog on Linux, with the editors' in-app
# path field as the fallback) and "open with the system". CPU only: no GHOST, GPU or toolkit
# headers. Child processes come from stk_bridge's ChildProcess. See include/stk/platform/*.hh.

add_library(stk_platform STATIC
  src/file_dialog.cc
)
target_include_directories(stk_platform PUBLIC ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_platform PUBLIC cxx_std_20)
# stk_bridge is added after this directory; CMake resolves the target at generate time.
target_link_libraries(stk_platform PUBLIC stk_core PRIVATE stk_bridge)
if(MSVC)
  target_compile_options(stk_platform PRIVATE /W3 /utf-8)
else()
  target_compile_options(stk_platform PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
