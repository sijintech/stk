# SPDX-License-Identifier: GPL-2.0-or-later
# Opt-in P0/P4 candidate: resources remain CPU-only; native embedding needs the desktop engine.

add_library(stk_document_resources STATIC document_resources.cc)
target_include_directories(stk_document_resources PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_features(stk_document_resources PUBLIC cxx_std_20)

if(NOT TARGET GTest::gtest_main)
  find_package(GTest REQUIRED)
endif()
# Evidence recognition is CPU-only too; exercise it even with Blender disabled.
add_library(stk_document_evidence_pixels STATIC evidence_pixels.cc)
target_link_libraries(stk_document_evidence_pixels PUBLIC stk_io)
target_include_directories(stk_document_evidence_pixels PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_features(stk_document_evidence_pixels PUBLIC cxx_std_20)
add_executable(stk-document-evidence-tests evidence_pixels_test.cc)
target_link_libraries(stk-document-evidence-tests PRIVATE stk_document_evidence_pixels GTest::gtest_main)

add_executable(stk-document-resources-tests document_resources_test.cc)
target_link_libraries(stk-document-resources-tests PRIVATE stk_document_resources GTest::gtest_main)
if(COMMAND stk_target_warnings)
  stk_target_warnings(stk_document_resources)
  stk_target_warnings(stk-document-resources-tests)
  stk_target_warnings(stk_document_evidence_pixels)
  stk_target_warnings(stk-document-evidence-tests)
endif()
include(GoogleTest)
gtest_discover_tests(stk-document-evidence-tests DISCOVERY_TIMEOUT 60 DISCOVERY_MODE PRE_TEST
  PROPERTIES LABELS "unit;document_preview"
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
gtest_discover_tests(stk-document-resources-tests DISCOVERY_TIMEOUT 60 DISCOVERY_MODE PRE_TEST
  PROPERTIES LABELS "unit;document_preview"
  ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
  ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")

if(NOT TARGET stk_app OR NOT TARGET stk_wm)
  message(STATUS "Document preview: CPU resource tests only (native candidate requires stk_app/stk_wm)")
  return()
endif()

if(APPLE)
  set(_native_source native_document_view_cocoa.mm)
  set(_evidence_source window_evidence_cocoa.mm)
elseif(WIN32)
  set(_native_source native_document_view_win32.cc)
  set(_evidence_source window_evidence_win32.cc)
else()
  set(_native_source native_document_view_unsupported.cc)
  set(_evidence_source window_evidence_unsupported.cc)
endif()
add_library(stk_document_preview_native STATIC ${_native_source})
target_link_libraries(stk_document_preview_native PUBLIC stk_document_resources stk_wm)
target_compile_features(stk_document_preview_native PUBLIC cxx_std_20)

if(APPLE)
  target_compile_options(stk_document_preview_native PRIVATE
    "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
  find_library(_stk_preview_webkit WebKit REQUIRED)
  find_library(_stk_preview_appkit AppKit REQUIRED)
  target_link_libraries(stk_document_preview_native PRIVATE
    "${_stk_preview_webkit}" "${_stk_preview_appkit}")
elseif(WIN32)
  if(NOT MSVC)
    message(FATAL_ERROR "The WebView2 preview candidate requires MSVC-compatible Windows SDK/WRL headers")
  endif()
  # Official Microsoft NuGet SDK, pinned independently of the installed Evergreen Runtime.
  # FetchContent only runs for this opt-in Windows native target, never for default/CPU builds.
  include(FetchContent)
  set(STK_WEBVIEW2_SDK_URL
    "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.3537.50/microsoft.web.webview2.1.0.3537.50.nupkg"
    CACHE STRING "WebView2 1.0.3537.50 NuGet archive (fixed SHA256; file:// accepted for offline builds)")
  FetchContent_Declare(stk_webview2_sdk
    URL "${STK_WEBVIEW2_SDK_URL}"
    URL_HASH SHA256=5ea526bbd728adda0da4d31219267e96460494a427e4894c4e09d9f320f4b9aa
    DOWNLOAD_NAME webview2-sdk.zip
    DOWNLOAD_EXTRACT_TIMESTAMP ON)
  FetchContent_MakeAvailable(stk_webview2_sdk)

  if(CMAKE_VS_PLATFORM_NAME)
    set(_webview_arch "${CMAKE_VS_PLATFORM_NAME}")
  elseif(CMAKE_CXX_COMPILER_ARCHITECTURE_ID)
    set(_webview_arch "${CMAKE_CXX_COMPILER_ARCHITECTURE_ID}")
  else()
    set(_webview_arch "${CMAKE_SYSTEM_PROCESSOR}")
  endif()
  string(TOLOWER "${_webview_arch}" _webview_arch)
  if(_webview_arch MATCHES "^(arm64|aarch64)$")
    set(_webview_arch arm64)
  elseif(_webview_arch MATCHES "^(win32|x86|i[3-6]86)$" OR CMAKE_SIZEOF_VOID_P EQUAL 4)
    set(_webview_arch x86)
  elseif(_webview_arch MATCHES "^(x64|amd64|x86_64)$")
    set(_webview_arch x64)
  else()
    message(FATAL_ERROR "WebView2 SDK has no loader for target architecture '${_webview_arch}'")
  endif()
  set(_webview_loader "${stk_webview2_sdk_SOURCE_DIR}/build/native/${_webview_arch}/WebView2LoaderStatic.lib")
  if(NOT EXISTS "${_webview_loader}")
    message(FATAL_ERROR "Pinned WebView2 SDK does not contain ${_webview_loader}")
  endif()
  add_library(stk_webview2_loader STATIC IMPORTED)
  set_target_properties(stk_webview2_loader PROPERTIES
    IMPORTED_LOCATION "${_webview_loader}"
    INTERFACE_INCLUDE_DIRECTORIES "${stk_webview2_sdk_SOURCE_DIR}/build/native/include")
  target_link_libraries(stk_document_preview_native PRIVATE
    stk_webview2_loader ole32 oleaut32 shlwapi version advapi32 user32)
  target_compile_options(stk_document_preview_native PRIVATE /utf-8 /bigobj)
endif()

add_executable(stk-document-preview-spike document_preview_spike.cc fixture.cc ${_evidence_source})
target_link_libraries(stk-document-preview-spike PRIVATE
  stk_document_preview_native stk_document_evidence_pixels stk_app)
if(APPLE)
  # Only the evidence helper needs macOS 14.4 at runtime; keep the product minimum at 13.3.
  find_library(_stk_preview_sck ScreenCaptureKit REQUIRED)
  target_link_libraries(stk-document-preview-spike PRIVATE
    "${_stk_preview_appkit}" "${_stk_preview_sck}")
  target_compile_options(stk-document-preview-spike PRIVATE
    "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
  set_target_properties(stk-document-preview-spike PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED ON)
elseif(WIN32)
  target_link_libraries(stk-document-preview-spike PRIVATE d3d11 dxgi dwmapi windowsapp runtimeobject opengl32)
endif()
get_filename_component(_preview_payload "${CMAKE_SOURCE_DIR}/../docs/specs/examples/payload-v2" ABSOLUTE)
target_compile_definitions(stk-document-preview-spike PRIVATE
  STK_DOCUMENT_PREVIEW_PAYLOAD_DIR="${_preview_payload}")
set_target_properties(stk-document-preview-spike PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${STK_DESKTOP_BIN_DIR}")
if(MSVC)
  target_compile_options(stk-document-preview-spike PRIVATE /utf-8 /bigobj)
endif()

# No display/graphics setup is performed by these modes. Verify the exact exit code and
# diagnostics; WILL_FAIL would also accept unrelated crashes and missing-DLL failures.
foreach(_memory_mode late-static leak early-failure)
  string(REPLACE "-" "_" _memory_name "${_memory_mode}")
  add_test(NAME document_preview_memory_${_memory_name}
    COMMAND ${CMAKE_COMMAND}
      "-DPROGRAM=$<TARGET_FILE:stk-document-preview-spike>" "-DMODE=${_memory_mode}"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/check_memory_gate.cmake")
  set_tests_properties(document_preview_memory_${_memory_name} PROPERTIES
    LABELS "unit;document_preview" TIMEOUT 30
    ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
    ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:")
endforeach()

if(APPLE OR WIN32)
  if(APPLE)
    set(_native_backend metal)
    set(_native_command "env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \"$<TARGET_FILE:stk-document-preview-spike>\"")
  else()
    set(_native_backend opengl)
    set(_native_command "$env:STK_TOKEN_PLAN_API_KEY = ''\nRemove-Item Env:STK_TOKEN_PLAN_MODEL -ErrorAction SilentlyContinue\n& \"$<TARGET_FILE:stk-document-preview-spike>\"")
  endif()
  set(_native_evidence "${CMAKE_CURRENT_BINARY_DIR}/native-evidence")
  # No skip code: an absent Runtime, display, capture permission or matching pixels is a failure.
  add_test(NAME document_preview_native_${_native_backend}
    COMMAND $<TARGET_FILE:stk-document-preview-spike> --smoke --require-native --cycles 20
      --evidence-dir "${_native_evidence}" --gpu-backend ${_native_backend})
  set_tests_properties(document_preview_native_${_native_backend} PROPERTIES
    LABELS "gpu;window;document_preview;native_document_preview" TIMEOUT 600
    RESOURCE_LOCK native_window ENVIRONMENT "STK_TOKEN_PLAN_API_KEY="
    ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:"
    PASS_REGULAR_EXPRESSION "PASS: native document evidence"
    FAIL_REGULAR_EXPRESSION "FAIL:|leaked|Error: Not freed memory")
  file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/native-smoke-$<CONFIG>.txt"
    CONTENT "${_native_command} --smoke --require-native --cycles 20 --evidence-dir \"${_native_evidence}\" --gpu-backend ${_native_backend}\n")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  set(_runner "${CMAKE_SOURCE_DIR}/tests/wm/run_with_display.py")
  set(_sysroot_arg "")
  set(_display_env "XDG_CACHE_HOME=${CMAKE_CURRENT_BINARY_DIR}/cache"
    "LIBGL_ALWAYS_SOFTWARE=1" "STK_TOKEN_PLAN_API_KEY=")
  if(STK_TEST_VK_ICD AND EXISTS "${STK_TEST_VK_ICD}")
    list(APPEND _display_env "VK_DRIVER_FILES=${STK_TEST_VK_ICD}" "VK_ICD_FILENAMES=${STK_TEST_VK_ICD}")
  endif()
  if(STK_SYSROOT_FOUND)
    set(_sysroot_arg --sysroot "${STK_SYSROOT}")
    list(APPEND _display_env "LD_LIBRARY_PATH=${STK_SYSROOT_LIBDIR}"
      "__EGL_VENDOR_LIBRARY_DIRS=${STK_SYSROOT_EGL_VENDOR_DIR}")
  endif()
  set(_preview_backends "")
  if(STK_GPU_OPENGL)
    list(APPEND _preview_backends opengl)
  endif()
  if(STK_GPU_VULKAN)
    list(APPEND _preview_backends vulkan)
  endif()
  foreach(_server xvfb weston)
    foreach(_backend IN LISTS _preview_backends)
      set(_test document_preview_${_server}_${_backend})
      add_test(NAME ${_test}
        COMMAND ${Python3_EXECUTABLE} "${_runner}" --server ${_server}
          --workdir "${CMAKE_CURRENT_BINARY_DIR}/d_${_server}_${_backend}" ${_sysroot_arg}
          --size 1440x1000 --timeout 120 -- $<TARGET_FILE:stk-document-preview-spike>
          --smoke --gpu-backend ${_backend})
      set_tests_properties(${_test} PROPERTIES
        LABELS "gpu;window;document_preview" TIMEOUT 180 SKIP_RETURN_CODE 77
        RESOURCE_LOCK display_${_server} ENVIRONMENT "${_display_env}"
        ENVIRONMENT_MODIFICATION "STK_TOKEN_PLAN_MODEL=unset:"
        PASS_REGULAR_EXPRESSION "PASS: document preview"
        FAIL_REGULAR_EXPRESSION "FAIL:|leaked|Error: Not freed memory")
    endforeach()
  endforeach()
endif()
