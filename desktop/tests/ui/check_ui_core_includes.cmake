# SPDX-License-Identifier: GPL-2.0-or-later
# Dependency rule: ui_core (stk_ui src/core and every public header except gpu_painter.hh) never
# includes GHOST, GPU, BLF or other Blender headers, so it builds and tests anywhere (MSVC, macOS,
# no GPU). Same forbidden list as desktop/tests/unit/check_includes.cmake.
#   cmake -DUI_DIR=<desktop/engine/lib/stk_ui> -P check_ui_core_includes.cmake
set(_forbidden "GHOST_|GPU_|BLF_|BLI_|BKE_|DNA_|RNA_|WM_|ED_|IMB_|MEM_guardedalloc|blender/|epoxy/|GL/|GLES|vulkan/|Metal/|glad")
file(GLOB_RECURSE _files "${UI_DIR}/src/core/*" "${UI_DIR}/include/stk/ui/*.hh")
list(FILTER _files EXCLUDE REGEX "/gpu_painter\\.hh$")
set(_violations "")
foreach(_file ${_files})
  file(STRINGS "${_file}" _includes REGEX "^[ \t]*#[ \t]*include")
  foreach(_line ${_includes})
    if(_line MATCHES "${_forbidden}")
      list(APPEND _violations "${_file}: ${_line}")
    endif()
  endforeach()
endforeach()
if(_violations)
  string(REPLACE ";" "\n  " _text "${_violations}")
  message(FATAL_ERROR "ui_core includes GPU/window-system headers:\n  ${_text}")
endif()
list(LENGTH _files _n)
message(STATUS "ui_core: ${_n} files include no GHOST/GPU/BLF/Blender headers")
