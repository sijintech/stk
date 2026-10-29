# SPDX-License-Identifier: GPL-2.0-or-later
# Confined report bytes are CPU-only; platform browser adapters are an explicit candidate.
option(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES
  "Build fixed, read-only own-window media probes for native document acceptance tests" OFF)
if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES AND NOT STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW)
  message(FATAL_ERROR "Native document test probes require the explicit native preview candidate")
endif()
add_library(stk_document_resources STATIC src/resources.cc)
target_include_directories(stk_document_resources PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(stk_document_resources PUBLIC cxx_std_20)
if(NOT TARGET stk_wm)
  return()
endif()

if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW AND APPLE)
  set(_native_source src/native_view_cocoa.mm)
elseif(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW AND WIN32)
  set(_native_source src/native_view_win32.cc)
else()
  set(_native_source src/native_view_unsupported.cc)
endif()
add_library(stk_document_native STATIC ${_native_source})
target_link_libraries(stk_document_native PUBLIC stk_document_resources stk_wm)
target_compile_features(stk_document_native PUBLIC cxx_std_20)
target_include_directories(stk_document_native PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES)
  target_sources(stk_document_native PRIVATE src/test_media_probe.cc)
  target_compile_definitions(stk_document_native PUBLIC STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES=1)
  target_link_libraries(stk_document_native PRIVATE stk_io)
endif()

if(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW AND APPLE)
  set_target_properties(stk_document_native PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED ON)
  target_compile_options(stk_document_native PRIVATE
    "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
  find_library(_stk_preview_webkit WebKit REQUIRED)
  find_library(_stk_preview_appkit AppKit REQUIRED)
  target_link_libraries(stk_document_native PRIVATE
    "${_stk_preview_webkit}" "${_stk_preview_appkit}")
elseif(STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW AND WIN32)
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
  target_link_libraries(stk_document_native PRIVATE
    stk_webview2_loader ole32 oleaut32 shlwapi version advapi32 user32)
  target_compile_options(stk_document_native PRIVATE /utf-8 /bigobj)
endif()
