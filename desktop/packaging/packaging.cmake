# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install layout and packages of the desktop application (WP12); included from desktop/CMakeLists.txt
# once the targets exist. The layout directories and CMAKE_INSTALL_RPATH are set there.
#
#   Linux (relocatable prefix, CPack TGZ)          macOS (STK.app, unsigned, CPack ZIP)
#   bin/stk-desktop, bin/stk-render                 STK.app/Contents/MacOS/stk-desktop, stk-render
#   lib/stk-desktop/          bundled libraries     STK.app/Contents/Frameworks/ (empty: vcpkg is static)
#   share/stk-desktop/datafiles/fonts               STK.app/Contents/Resources/datafiles/fonts
#   share/stk-desktop/i18n/*.json                   STK.app/Contents/Resources/i18n/*.json
#   share/doc/stk-desktop/                          STK.app/Contents/Resources/licenses/
#     LICENSE (GPL-2.0-or-later), THIRD-PARTY-NOTICES.md, third-party/, blender/ (upstream texts)
#                                                   STK.app/Contents/Info.plist, Resources/stk-desktop.icns
#
# The executables find their datafiles and catalogs relative to themselves
# (stk::gfx::locate_datafiles, stk::app::locate_i18n_dir). STK_DESKTOP_RELOCATABLE=ON compiles no
# source-tree fallbacks in. STK_DESKTOP_BUNDLE_LIBS=ON (Linux) copies the executables' non-system
# shared libraries into lib/stk-desktop at install time (bundle_linux_libs.py, from ldd).
# The Python side (suan.desktop_bridge) is not bundled: see docs/desktop.md.

set(_stk_pkg_dir "${CMAKE_CURRENT_LIST_DIR}")
set(_stk_installed stk-desktop)
if(TARGET stk-render)
  list(APPEND _stk_installed stk-render)
endif()
install(TARGETS ${_stk_installed} RUNTIME DESTINATION "${STK_INSTALL_BINDIR}")

# Licences: the engine's GPL, the notices file, and the vendored third-party texts. Blender's
# upstream license directory (fonts: OFL-1.1 / Bitstream-Vera, Blender's bundled code) is installed
# by stk_gfx into <docdir>/blender.
set(_stk_tp "${CMAKE_SOURCE_DIR}/engine/third_party")
install(FILES "${CMAKE_SOURCE_DIR}/LICENSE" "${_stk_pkg_dir}/THIRD-PARTY-NOTICES.md" DESTINATION "${STK_INSTALL_DOCDIR}")
install(FILES "${_stk_tp}/blender/src/COPYING" "${_stk_tp}/blender/UPSTREAM.json" DESTINATION "${STK_INSTALL_DOCDIR}/blender")
install(FILES "${_stk_tp}/nlohmann_json/LICENSE.MIT" DESTINATION "${STK_INSTALL_DOCDIR}/third-party"
        RENAME nlohmann_json-LICENSE.MIT)
install(FILES "${_stk_tp}/libspng/LICENSE" DESTINATION "${STK_INSTALL_DOCDIR}/third-party" RENAME libspng-LICENSE)
install(FILES "${_stk_tp}/libspng/miniz/LICENSE" DESTINATION "${STK_INSTALL_DOCDIR}/third-party" RENAME miniz-LICENSE)

if(APPLE)
  set(STK_BUNDLE_ID "ai.sijin.stk.desktop" CACHE STRING "CFBundleIdentifier of STK.app")
  set(STK_BUNDLE_VERSION "${PROJECT_VERSION}")
  configure_file("${_stk_pkg_dir}/macos/Info.plist.in" "${CMAKE_BINARY_DIR}/packaging/Info.plist" @ONLY)
  install(FILES "${CMAKE_BINARY_DIR}/packaging/Info.plist" DESTINATION "STK.app/Contents")
  install(FILES "${_stk_pkg_dir}/icons/stk-desktop.icns" DESTINATION "${STK_INSTALL_DATADIR}")
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  option(STK_DESKTOP_BUNDLE_LIBS
    "Install: copy the executables' non-system shared libraries into lib/stk-desktop (package builds)" OFF)
  if(STK_DESKTOP_BUNDLE_LIBS)
    # DT_RPATH instead of DT_RUNPATH: it is also searched for the dependencies of bundled libraries.
    foreach(_t ${_stk_installed})
      target_link_options(${_t} PRIVATE "LINKER:--disable-new-dtags")
    endforeach()
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(_stk_bundle_args --libdir "${STK_INSTALL_LIBDIR}" --docdir "${STK_INSTALL_DOCDIR}")
    foreach(_t ${_stk_installed})
      list(APPEND _stk_bundle_args --exe "${STK_INSTALL_BINDIR}/${_t}")
    endforeach()
    list(JOIN _stk_bundle_args "\" \"" _stk_bundle_argstr)
    install(CODE "
      execute_process(COMMAND \"${Python3_EXECUTABLE}\" \"${_stk_pkg_dir}/bundle_linux_libs.py\"
                      --prefix \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}\" \"${_stk_bundle_argstr}\"
                      RESULT_VARIABLE _rc)
      if(_rc)
        message(FATAL_ERROR \"bundle_linux_libs.py failed (\${_rc})\")
      endif()")
  endif()
endif()

# ---------------------------------------------------------------------------------------------
# CPack: `cpack --config <build>/CPackConfig.cmake` (or `cmake --build <build> --target package`).

set(CPACK_PACKAGE_NAME "stk-desktop")
set(CPACK_PACKAGE_VENDOR "Shanghai Sijin Information Technology LLC")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "STK desktop application (GPL-2.0-or-later)")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_SOURCE_DIR}/LICENSE")
if(NOT APPLE)
  # (macOS: CI strips and ad-hoc signs STK.app itself; see .github/workflows/desktop.yml.)
  set(CPACK_STRIP_FILES ON)
endif()
if(APPLE)
  set(CPACK_GENERATOR "ZIP")
  set(_stk_pkg_system "macos-${CMAKE_SYSTEM_PROCESSOR}")
  # The archive holds STK.app at its root.
  set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY OFF)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(CPACK_GENERATOR "TGZ")
  set(_stk_pkg_system "linux-${CMAKE_SYSTEM_PROCESSOR}")
  set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY ON)
else()
  set(CPACK_GENERATOR "ZIP")
  set(_stk_pkg_system "windows-${CMAKE_SYSTEM_PROCESSOR}")
  set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY ON)
endif()
string(TOLOWER "${_stk_pkg_system}" _stk_pkg_system)
set(CPACK_PACKAGE_FILE_NAME "stk-desktop-${PROJECT_VERSION}-${_stk_pkg_system}")
set(CPACK_SOURCE_GENERATOR "")
include(CPack)

# ---------------------------------------------------------------------------------------------
# Test (labels "gpu;package"): install into <build>/install-check, then check_install.py runs the
# installed stk-desktop / stk-render headless from an unrelated directory and checks that fonts and
# catalogs come from the prefix (not the build or source tree).

find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND AND NOT WIN32 AND TARGET stk-render)
  set(_stk_pkg_prefix "${CMAKE_BINARY_DIR}/install-check")
  add_test(NAME package_install
    COMMAND ${CMAKE_COMMAND} --install "${CMAKE_BINARY_DIR}" --prefix "${_stk_pkg_prefix}" --config $<CONFIG>)
  set(_stk_pkg_env "XDG_CACHE_HOME=${CMAKE_BINARY_DIR}/packaging/cache")
  set(_stk_pkg_backend "")
  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(_stk_pkg_backend opengl)
    list(APPEND _stk_pkg_env "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless" "LIBGL_ALWAYS_SOFTWARE=1")
    if(STK_SYSROOT_FOUND)
      list(APPEND _stk_pkg_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
    endif()
  elseif(APPLE)
    set(_stk_pkg_backend metal)
  endif()
  add_test(NAME package_install_check
    COMMAND ${Python3_EXECUTABLE} "${_stk_pkg_dir}/check_install.py" --prefix "${_stk_pkg_prefix}"
            --workdir "${CMAKE_BINARY_DIR}/packaging/check" --backend ${_stk_pkg_backend}
            --payload "${CMAKE_SOURCE_DIR}/../docs/specs/examples/payload-v2")
  set_tests_properties(package_install PROPERTIES LABELS "gpu;package" FIXTURES_SETUP stk_package_install TIMEOUT 300)
  set_tests_properties(package_install_check PROPERTIES LABELS "gpu;package" FIXTURES_REQUIRED stk_package_install
    TIMEOUT 600 ENVIRONMENT "${_stk_pkg_env}" PASS_REGULAR_EXPRESSION "INSTALL PASS"
    FAIL_REGULAR_EXPRESSION "INSTALL FAIL|leaked|Error: Not freed memory")
endif()
