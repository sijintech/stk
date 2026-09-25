# SPDX-License-Identifier: GPL-2.0-or-later
#
# stk_gfx: GPU/BLF bootstrap on the vendored Blender engine (runtime, backend selection, main
# context, font stack, UI scale, offscreen render to PNG). See include/stk/gfx/*.hh.

if(NOT TARGET stk_blender)
  message(STATUS "stk_gfx: skipped (STK_DESKTOP_WITH_BLENDER=OFF)")
  return()
endif()
if(NOT TARGET stk_io)
  add_subdirectory(${CMAKE_CURRENT_LIST_DIR}/../stk_io ${CMAKE_BINARY_DIR}/engine/lib/stk_io)
endif()

option(STK_GFX_SOURCE_DATAFILES_FALLBACK
  "Let binaries fall back to the vendored source tree for fonts (development builds)" ON)

add_library(stk_gfx STATIC
  src/fonts.cc
  src/gpu.cc
  src/offscreen.cc
  src/png.cc
)
target_include_directories(stk_gfx PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(stk_gfx PUBLIC cxx_std_20)
# stk_core (UTF-8 paths, environment) and stk_io (PNG via libspng) are CPU-only libraries.
target_link_libraries(stk_gfx PUBLIC stk_blender PRIVATE stk_core stk_io)
if(STK_GFX_SOURCE_DATAFILES_FALLBACK)
  target_compile_definitions(stk_gfx PRIVATE STK_GFX_SOURCE_DATAFILES="${STK_BLENDER_DATAFILES}")
endif()
if(MSVC)
  target_compile_options(stk_gfx PRIVATE /W3)
else()
  target_compile_options(stk_gfx PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()

# Engine executables go to <build>/bin, with the fonts staged at <build>/bin/datafiles/fonts so the
# exe-relative lookup is exercised in build trees just like in installs
# (<prefix>/bin + <prefix>/share/stk-desktop/datafiles).
set(STK_DESKTOP_BIN_DIR "${CMAKE_BINARY_DIR}/bin" CACHE INTERNAL "Output directory of engine executables")
set(STK_GFX_DATAFILES_STAGE "${STK_DESKTOP_BIN_DIR}/datafiles" CACHE INTERNAL "")
file(GLOB _stk_fonts "${STK_BLENDER_DATAFILES}/fonts/*")
set(_staged "")
foreach(_f ${_stk_fonts})
  get_filename_component(_n "${_f}" NAME)
  add_custom_command(OUTPUT "${STK_GFX_DATAFILES_STAGE}/fonts/${_n}"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${_f}" "${STK_GFX_DATAFILES_STAGE}/fonts/${_n}"
    DEPENDS "${_f}" COMMENT "Staging font ${_n}")
  list(APPEND _staged "${STK_GFX_DATAFILES_STAGE}/fonts/${_n}")
endforeach()
add_custom_target(stk_gfx_datafiles DEPENDS ${_staged})
add_dependencies(stk_gfx stk_gfx_datafiles)

install(DIRECTORY "${STK_BLENDER_DATAFILES}/fonts" DESTINATION share/stk-desktop/datafiles)
# Upstream license texts (fonts: OFL-1.1 / Bitstream-Vera; engine: GPL-2.0-or-later).
install(DIRECTORY "${STK_BLENDER_DATAFILES}/../license" DESTINATION share/stk-desktop)
