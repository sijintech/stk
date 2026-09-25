# SPDX-License-Identifier: GPL-2.0-or-later
# Dependency rule of the desktop engine: stk_core, stk_io and stk_viewer_model never include GHOST,
# GPU, BLF or other Blender headers (nor graphics APIs), so they stay unit-testable anywhere.
#   cmake -DLIB_DIR=<desktop/engine/lib> -P check_includes.cmake
set(_forbidden "GHOST_|GPU_|BLF_|BLI_|BKE_|DNA_|RNA_|WM_|ED_|IMB_|MEM_guardedalloc|blender/|epoxy/|GL/|GLES|vulkan/|Metal/|glad")
set(_violations "")
foreach(_lib stk_core stk_io stk_viewer_model)
  file(GLOB_RECURSE _files "${LIB_DIR}/${_lib}/*.hh" "${LIB_DIR}/${_lib}/*.cc" "${LIB_DIR}/${_lib}/*.inc"
       "${LIB_DIR}/${_lib}/*.h" "${LIB_DIR}/${_lib}/*.cpp")
  foreach(_file ${_files})
    file(STRINGS "${_file}" _includes REGEX "^[ \t]*#[ \t]*include")
    foreach(_line ${_includes})
      if(_line MATCHES "${_forbidden}")
        list(APPEND _violations "${_file}: ${_line}")
      endif()
    endforeach()
  endforeach()
endforeach()
if(_violations)
  string(REPLACE ";" "\n  " _text "${_violations}")
  message(FATAL_ERROR "CPU-only engine libraries include GPU/window-system headers:\n  ${_text}")
endif()
message(STATUS "stk_core, stk_io and stk_viewer_model include no GHOST/GPU/Blender headers")
