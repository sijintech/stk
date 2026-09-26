# SPDX-License-Identifier: GPL-2.0-or-later
#
# Widget gallery.
#   stk_ui_gallery_screens  core-only screen builders (also used by the layout goldens)
#   widget_gallery          renders every widget offscreen (--headless --export out.png --lang zh|en
#                           --scale S) or in a window (stk_wm); ctest label "gpu" with a tolerant
#                           golden per language/scale

set(_stk_desktop_dir ${CMAKE_CURRENT_LIST_DIR}/../..)
get_filename_component(_stk_desktop_dir ${_stk_desktop_dir} ABSOLUTE)
get_filename_component(_stk_repo_dir ${_stk_desktop_dir}/.. ABSOLUTE)

add_library(stk_ui_gallery_screens STATIC screens.cc)
target_include_directories(stk_ui_gallery_screens PUBLIC ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(stk_ui_gallery_screens PUBLIC stk_ui_core)

if(NOT STK_UI_BUILD_GALLERY OR NOT TARGET stk_ui_gpu)
  return()
endif()

add_executable(widget_gallery widget_gallery.cc gallery_wm.cc)
# stk_wm is added by the root CMakeLists.txt after stk_ui; link items resolve at generate time.
target_link_libraries(widget_gallery PRIVATE stk_ui_gallery_screens stk_ui_gpu stk_gfx stk_wm)
target_compile_definitions(widget_gallery PRIVATE
  STK_DESKTOP_DIR="${_stk_desktop_dir}"
  STK_REPO_ROOT="${_stk_repo_dir}")
if(DEFINED STK_DESKTOP_BIN_DIR)
  set_target_properties(widget_gallery PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
endif()

# GPU tests: headless render and tolerant golden, same software-rendering environment as the WP1
# engine tests (desktop/tests/wm).
set(STK_UI_GALLERY_VK_ICD "/usr/share/vulkan/icd.d/lvp_icd.json" CACHE FILEPATH
    "Vulkan ICD used by the widget gallery tests (default: Mesa lavapipe; empty = system default)")
set(_env "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless" "LIBGL_ALWAYS_SOFTWARE=1"
         "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache")
if(STK_UI_GALLERY_VK_ICD AND EXISTS "${STK_UI_GALLERY_VK_ICD}")
  list(APPEND _env "VK_DRIVER_FILES=${STK_UI_GALLERY_VK_ICD}" "VK_ICD_FILENAMES=${STK_UI_GALLERY_VK_ICD}")
endif()
if(STK_SYSROOT_FOUND)
  list(APPEND _env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}" "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
endif()
set(_backends "")
if(STK_GPU_VULKAN)
  list(APPEND _backends vulkan)
endif()
if(STK_GPU_OPENGL AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  list(APPEND _backends opengl)
endif()
if(STK_GPU_METAL)
  list(APPEND _backends metal)
endif()

foreach(_case "zh;1" "en;1.5")
  list(GET _case 0 _lang)
  list(GET _case 1 _scale)
  string(REPLACE "." "_" _sname "${_scale}")
  set(_golden "${CMAKE_CURRENT_LIST_DIR}/golden/gallery_${_lang}_${_sname}x.png")
  foreach(_be ${_backends})
    set(_name ui_gallery_${_be}_${_lang}_${_sname}x)
    add_test(NAME ${_name}
      COMMAND widget_gallery --headless --backend ${_be} --lang ${_lang} --scale ${_scale}
              --export ${CMAKE_CURRENT_BINARY_DIR}/gallery_${_be}_${_lang}_${_sname}x.png --golden ${_golden})
    set_tests_properties(${_name} PROPERTIES LABELS "gpu;ui" TIMEOUT 300 ENVIRONMENT "${_env}"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
  endforeach()
endforeach()

# Live window (Linux): the interactive gallery on a private Xvfb / headless weston through WP1's
# runner (unix sockets only; skipped with 77 when the servers are missing).
find_package(Python3 COMPONENTS Interpreter)
set(_runner "${_stk_desktop_dir}/tests/wm/run_with_display.py")
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND Python3_Interpreter_FOUND AND EXISTS "${_runner}")
  set(_sysroot_arg "")
  if(STK_SYSROOT_FOUND)
    set(_sysroot_arg --sysroot "${STK_SYSROOT}")
  endif()
  list(REMOVE_ITEM _env "DISPLAY=" "WAYLAND_DISPLAY=" "EGL_PLATFORM=surfaceless")
  foreach(_server xvfb weston)
    set(_name ui_gallery_window_${_server})
    # weston's kiosk shell (1280x800 output) drops clients whose window exceeds the output (WP1
    # open item), so the Wayland run uses the smaller form screen.
    set(_screen gallery)
    if(_server STREQUAL "weston")
      set(_screen form)
    endif()
    add_test(NAME ${_name}
      COMMAND ${Python3_EXECUTABLE} ${_runner} --server ${_server}
              --workdir ${CMAKE_CURRENT_BINARY_DIR}/d_${_server} ${_sysroot_arg}
              -- $<TARGET_FILE:widget_gallery> --lang zh --screen ${_screen} --exit-after-frames 3)
    set_tests_properties(${_name} PROPERTIES
      LABELS "gpu;window;ui" TIMEOUT 180 SKIP_RETURN_CODE 77 ENVIRONMENT "${_env}"
      RESOURCE_LOCK display_${_server}
      PASS_REGULAR_EXPRESSION "presented 3 frames"
      FAIL_REGULAR_EXPRESSION "leaked|Error: Not freed memory")
  endforeach()
endif()
