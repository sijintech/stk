# SPDX-FileCopyrightText: 2026 STK Authors
# SPDX-License-Identifier: GPL-2.0-or-later
set(INC
  ../include
  ../../makesrna
  ${CMAKE_BINARY_DIR}/source/blender/makesrna
)
set(INC_SYS)
set(SRC space_stk.cc stk_scene.hh)
set(LIB
  PRIVATE bf::blenfont
  PRIVATE bf::blenkernel
  PRIVATE bf::blenlib
  PRIVATE bf::blenloader
  PRIVATE bf::dna
  PRIVATE bf::gpu
  PRIVATE bf::intern::guardedalloc
  PRIVATE bf::windowmanager
)
blender_add_lib(bf_editor_space_stk "${SRC}" "${INC}" "${INC_SYS}" "${LIB}")
add_dependencies(bf_editor_space_stk bf_rna)
