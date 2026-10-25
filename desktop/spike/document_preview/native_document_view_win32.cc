/* SPDX-License-Identifier: GPL-2.0-or-later */
/** WebView2 windowed-host candidate. All COM work stays on GHOST's existing UI STA.
 * This controls document requests, not the Runtime's own update/telemetry transport. It does not
 * install a Runtime, grant a directory to a page, or expose the desktop bridge to JavaScript.
 */
#include "native_document_view.hh"

#ifndef NOMINMAX
#  define NOMINMAX
#endif
#include <windows.h>
#include <objbase.h>
#include <shlwapi.h>
#include <wrl.h>

#include <WebView2.h>
#include <WebView2EnvironmentOptions.h>

#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cwchar>
#include <filesystem>
#include <iterator>
#include <limits>
#include <utility>

namespace stk::document_preview {
namespace {

using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;
using Microsoft::WRL::Make;

struct ComText {
  LPWSTR value = nullptr;
  ~ComText() { CoTaskMemFree(value); }
};

std::string utf8(LPCWSTR text)
{
  if (!text) {
    return {};
  }
  const size_t length = std::wcslen(text);
  if (length > 65536) {
    return {};
  }
  const int count = WideCharToMultiByte(
      CP_UTF8, WC_ERR_INVALID_CHARS, text, int(length), nullptr, 0, nullptr, nullptr);
  if (count <= 0) {
    return {};
  }
  std::string result(size_t(count), '\0');
  WideCharToMultiByte(
      CP_UTF8, WC_ERR_INVALID_CHARS, text, int(length), result.data(), count, nullptr, nullptr);
  return result;
}

std::wstring wide(std::string_view text)
{
  if (text.empty() || text.size() > 65536) {
    return {};
  }
  const int count = MultiByteToWideChar(
      CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), int(text.size()), nullptr, 0);
  if (count <= 0) {
    return {};
  }
  std::wstring result(size_t(count), L'\0');
  MultiByteToWideChar(
      CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), int(text.size()), result.data(), count);
  return result;
}

std::string failure_message(std::string_view operation, HRESULT result)
{
  char code[24];
  std::snprintf(code, sizeof(code), " (HRESULT 0x%08lx)", static_cast<unsigned long>(result));
  if (result == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)) {
    return "WebView2 Runtime is missing. Install the Microsoft Runtime separately, then retry.";
  }
  return std::string(operation) + code;
}

struct TemporaryProfile {
  std::filesystem::path path;
  bool cleanup_scheduled = false;  // Only accessed on the UI thread.
  bool browser_exited = false;

  ~TemporaryProfile()
  {
    // Fallback for failed environment creation. A locked directory may remain after abrupt exit;
    // the normal controller path waits for BrowserProcessExited before releasing this owner.
    std::error_code error;
    if (!path.empty()) {
      std::filesystem::remove_all(path, error);
    }
  }

  bool create(std::string &error)
  {
    GUID identity;
    const HRESULT result = CoCreateGuid(&identity);
    if (FAILED(result)) {
      error = failure_message("Could not allocate a preview profile identity", result);
      return false;
    }
    wchar_t name[40] = {};
    if (!StringFromGUID2(identity, name, int(std::size(name)))) {
      error = "Could not format the preview profile identity";
      return false;
    }
    std::error_code filesystem_error;
    auto candidate = std::filesystem::temp_directory_path(filesystem_error);
    if (filesystem_error) {
      error = "Could not locate the temporary directory for WebView2";
      return false;
    }
    candidate /= std::wstring(L"stk-document-preview-") + name;
    if (!std::filesystem::create_directory(candidate, filesystem_error) || filesystem_error) {
      error = "Could not create an exclusive temporary WebView2 profile";
      return false;
    }
    path = std::move(candidate);  // Never adopt or remove a pre-existing directory.
    return true;
  }
};

void cleanup_after_browser_exit(ICoreWebView2Environment *environment,
                                const std::shared_ptr<TemporaryProfile> &profile)
{
  if (!environment || !profile || profile->cleanup_scheduled) {
    return;
  }
  ComPtr<ICoreWebView2Environment5> lifecycle;
  if (FAILED(environment->QueryInterface(IID_PPV_ARGS(&lifecycle)))) {
    return;
  }
  // This deliberately retains only the environment/profile, never a view or parent HWND. The
  // event removes its own reference cycle. No wait or nested message pump runs during close().
  auto token = std::make_shared<EventRegistrationToken>();
  const HRESULT result = lifecycle->add_BrowserProcessExited(
      Callback<ICoreWebView2BrowserProcessExitedEventHandler>(
          [lifecycle, profile, token](ICoreWebView2Environment *,
                                      ICoreWebView2BrowserProcessExitedEventArgs *) -> HRESULT {
            profile->browser_exited = true;
            lifecycle->remove_BrowserProcessExited(*token);
            return S_OK;
          })
          .Get(),
      token.get());
  profile->cleanup_scheduled = SUCCEEDED(result);
}

struct View : std::enable_shared_from_this<View> {
  HWND parent = nullptr;
  DWORD thread = GetCurrentThreadId();
  std::shared_ptr<ResourceSession> resources;
  std::shared_ptr<TemporaryProfile> profile;
  ComPtr<ICoreWebView2Environment> environment;
  ComPtr<ICoreWebView2Controller> controller;
  ComPtr<ICoreWebView2> web;
  NativeViewState report;
  ViewBounds bounds;
  bool visible = false;
  bool has_bounds = false;
  bool focused = false;
  bool closed = false;
  bool fatal = false;
  bool navigation_requested = false;
  bool awaiting_navigation_start = false;
  UINT64 navigation_id = 0;
  std::string pending_url;
  std::string submitted_url;

  bool on_thread() const
  {
    assert(thread == GetCurrentThreadId());
    return thread == GetCurrentThreadId();
  }

  void release_focus()
  {
    if (focused && IsWindow(parent)) {
      SetFocus(parent);
    }
    focused = false;
  }

  void shutdown()
  {
    if (resources) {
      resources->close();
    }
    release_focus();
    cleanup_after_browser_exit(environment.Get(), profile);
    if (controller) {
      controller->put_IsVisible(FALSE);
      controller->Close();
    }
    web.Reset();
    controller.Reset();
    environment.Reset();
    profile.reset();
    resources.reset();
  }

  void fail(std::string_view operation, HRESULT result)
  {
    if (closed || fatal) {
      return;
    }
    fatal = true;
    report.status = NativeViewStatus::Failed;
    report.message = failure_message(operation, result);
    shutdown();
  }

  void layout()
  {
    if (!controller || closed || fatal) {
      return;
    }
    RECT client{};
    if (!GetClientRect(parent, &client)) {
      fail("The document's parent window is no longer available", HRESULT_FROM_WIN32(GetLastError()));
      return;
    }
    // GHOST Win32 is per-monitor DPI aware and uses native client pixels. RAW_PIXELS avoids a
    // second WebView2 scale conversion; monitor changes still update the browser rasterization.
    const int64_t width = client.right, height = client.bottom;
    const int64_t left = std::clamp<int64_t>(bounds.x, 0, width);
    const int64_t right = std::clamp<int64_t>(int64_t(bounds.x) + std::max(0, bounds.width), 0, width);
    const int64_t top = std::clamp<int64_t>(height - int64_t(bounds.y) - std::max(0, bounds.height), 0, height);
    const int64_t bottom = std::clamp<int64_t>(height - int64_t(bounds.y), 0, height);
    const RECT rectangle{LONG(left), LONG(top), LONG(right), LONG(bottom)};
    has_bounds = right > left && bottom > top;
    HRESULT result = controller->put_Bounds(rectangle);
    if (SUCCEEDED(result)) {
      result = controller->NotifyParentWindowPositionChanged();
    }
    if (SUCCEEDED(result)) {
      result = controller->put_IsVisible(visible && has_bounds);
    }
    if (FAILED(result)) {
      fail("Could not update WebView2 region bounds", result);
    }
    else if (!visible || !has_bounds) {
      release_focus();
    }
  }

  HRESULT respond(ICoreWebView2WebResourceRequestedEventArgs *args)
  {
    ComPtr<ICoreWebView2WebResourceRequest> request;
    HRESULT result = args->get_Request(&request);
    if (FAILED(result)) {
      return result;
    }
    ComText uri, method;
    if (FAILED(result = request->get_Uri(&uri.value)) ||
        FAILED(result = request->get_Method(&method.value))) {
      return result;
    }
    const std::string request_method = utf8(method.value);
    ResourceResponse response = resources->read(utf8(uri.value), request_method);
    if (response.status != 200) {
      ++report.blocked_requests;
    }
    if (response.bytes.size() > std::numeric_limits<UINT>::max() ||
        response.mime.find_first_of("\r\n") != std::string::npos ||
        response.content_security_policy.find_first_of("\r\n") != std::string::npos) {
      return E_INVALIDARG;
    }
    ComPtr<IStream> content;
    content.Attach(SHCreateMemStream(response.bytes.data(), UINT(response.bytes.size())));
    if (!content) {
      return E_OUTOFMEMORY;
    }
    std::string response_headers = "Content-Type: " + response.mime +
                                   "\r\nContent-Security-Policy: " + response.content_security_policy +
                                   "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff"
                                   "\r\nReferrer-Policy: no-referrer\r\n";
    if (request_method != "HEAD") {
      response_headers += "Content-Length: " + std::to_string(response.bytes.size()) + "\r\n";
    }
    const auto headers = wide(response_headers);
    if (headers.empty()) {
      return E_INVALIDARG;
    }
    ComPtr<ICoreWebView2WebResourceResponse> native_response;
    result = environment->CreateWebResourceResponse(content.Get(),
                                                    response.status,
                                                    response.status == 200 ? L"OK" : L"Blocked",
                                                    headers.c_str(),
                                                    &native_response);
    return FAILED(result) ? result : args->put_Response(native_response.Get());
  }

  HRESULT configure()
  {
    HRESULT result = controller->get_CoreWebView2(&web);
    if (FAILED(result)) {
      return result;
    }
    ComPtr<ICoreWebView2_22> restricted_web;
    ComPtr<ICoreWebView2Controller4> native_controller;
    ComPtr<ICoreWebView2Settings> base_settings;
    ComPtr<ICoreWebView2Settings7> settings;
    if (FAILED(result = web.As(&restricted_web)) ||
        FAILED(result = controller.As(&native_controller)) ||
        FAILED(result = web->get_Settings(&base_settings)) ||
        FAILED(result = base_settings.As(&settings))) {
      return result;  // No fallback to a resource filter that misses workers or other frames.
    }
    if (FAILED(result = controller->put_IsVisible(FALSE)) ||
        FAILED(result = native_controller->put_BoundsMode(COREWEBVIEW2_BOUNDS_MODE_USE_RAW_PIXELS)) ||
        FAILED(result = native_controller->put_ShouldDetectMonitorScaleChanges(TRUE)) ||
        FAILED(result = native_controller->put_AllowExternalDrop(FALSE)) ||
        FAILED(result = settings->put_IsScriptEnabled(FALSE)) ||
        FAILED(result = settings->put_IsWebMessageEnabled(FALSE)) ||
        FAILED(result = settings->put_AreHostObjectsAllowed(FALSE)) ||
        FAILED(result = settings->put_AreDefaultScriptDialogsEnabled(FALSE)) ||
        FAILED(result = settings->put_AreDevToolsEnabled(FALSE)) ||
        FAILED(result = settings->put_AreDefaultContextMenusEnabled(FALSE)) ||
        FAILED(result = settings->put_IsStatusBarEnabled(FALSE)) ||
        FAILED(result = settings->put_IsBuiltInErrorPageEnabled(FALSE)) ||
        FAILED(result = settings->put_AreBrowserAcceleratorKeysEnabled(FALSE)) ||
        FAILED(result = settings->put_IsPasswordAutosaveEnabled(FALSE)) ||
        FAILED(result = settings->put_IsGeneralAutofillEnabled(FALSE)) ||
        FAILED(result = settings->put_IsSwipeNavigationEnabled(FALSE)) ||
        FAILED(result = settings->put_HiddenPdfToolbarItems(COREWEBVIEW2_PDF_TOOLBAR_ITEMS(
                   COREWEBVIEW2_PDF_TOOLBAR_ITEMS_SAVE | COREWEBVIEW2_PDF_TOOLBAR_ITEMS_SAVE_AS |
                   COREWEBVIEW2_PDF_TOOLBAR_ITEMS_PRINT))) ||
        FAILED(result = restricted_web->AddWebResourceRequestedFilterWithRequestSourceKinds(
                   L"*", COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL,
                   COREWEBVIEW2_WEB_RESOURCE_REQUEST_SOURCE_KINDS_ALL))) {
      return result;
    }

    // Install a preallocated denial before consulting the view. A late request after close()
    // must not fall through to the network even when the weak view no longer exists.
    ComPtr<ICoreWebView2WebResourceResponse> denied_response;
    result = environment->CreateWebResourceResponse(
        nullptr, 403, L"Blocked",
        L"Content-Type: text/plain; charset=utf-8\r\nContent-Security-Policy: default-src 'none'"
        L"\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n", &denied_response);
    if (FAILED(result)) {
      return result;
    }
    const std::weak_ptr<View> weak = shared_from_this();
    EventRegistrationToken token{};
    result = web->add_WebResourceRequested(
        Callback<ICoreWebView2WebResourceRequestedEventHandler>(
            [weak, denied_response](ICoreWebView2 *sender,
                                    ICoreWebView2WebResourceRequestedEventArgs *args) -> HRESULT {
              const HRESULT denied = args->put_Response(denied_response.Get());
              if (FAILED(denied)) {
                sender->Stop();
                if (auto self = weak.lock()) {
                  self->fail("Could not deny an unhandled document resource", denied);
                }
                return denied;
              }
              if (auto self = weak.lock(); self && !self->closed && !self->fatal) {
                try {
                  const HRESULT response = self->respond(args);
                  if (FAILED(response)) {
                    // Never return to default URL loading after a response allocation/API error.
                    self->fail("Could not provide the confined document resource", response);
                  }
                }
                catch (...) {
                  self->fail("Could not provide the confined document resource", E_OUTOFMEMORY);
                }
              }
              return S_OK;
            })
            .Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_NavigationStarting(
        Callback<ICoreWebView2NavigationStartingEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2NavigationStartingEventArgs *args) -> HRESULT {
              auto self = weak.lock();
              ComText uri;
              if (!self || self->closed || self->fatal || FAILED(args->get_Uri(&uri.value)) ||
                  !self->resources->allows_navigation(utf8(uri.value))) {
                if (self) {
                  ++self->report.blocked_requests;
                }
                return args->put_Cancel(TRUE);
              }
              const std::string target = utf8(uri.value);
              UINT64 id = 0;
              if (FAILED(args->get_NavigationId(&id))) {
                return args->put_Cancel(TRUE);
              }
              // Serialize host submissions until their Starting event binds a NavigationId.
              // IsUserInitiated cannot distinguish a page click from a host Navigate() call.
              if (self->awaiting_navigation_start) {
                if (target != self->submitted_url) {
                  ++self->report.blocked_requests;
                  return args->put_Cancel(TRUE);
                }
                self->awaiting_navigation_start = false;
                if (target != self->pending_url) {
                  const HRESULT cancelled = args->put_Cancel(TRUE);
                  if (FAILED(cancelled)) {
                    self->fail("Could not cancel a superseded document navigation", cancelled);
                  }
                  else {
                    self->navigate_pending();
                  }
                  return S_OK;
                }
              }
              else {
                ++self->report.navigation_generation;
              }
              self->pending_url = target;
              self->navigation_requested = false;
              self->navigation_id = id;
              self->report.status = NativeViewStatus::Loading;
              self->report.message = "Loading the admitted document";
              return S_OK;
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_FrameNavigationStarting(
        Callback<ICoreWebView2NavigationStartingEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2NavigationStartingEventArgs *args) -> HRESULT {
              if (auto self = weak.lock()) {
                ++self->report.blocked_requests;
              }
              return args->put_Cancel(TRUE);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_NavigationCompleted(
        Callback<ICoreWebView2NavigationCompletedEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2NavigationCompletedEventArgs *args) -> HRESULT {
              auto self = weak.lock();
              UINT64 id = 0;
              if (!self || self->closed || self->fatal ||
                  FAILED(args->get_NavigationId(&id)) || id != self->navigation_id) {
                return S_OK;
              }
              BOOL success = FALSE;
              if (SUCCEEDED(args->get_IsSuccess(&success)) && success) {
                self->report.status = NativeViewStatus::Ready;
                self->report.message = "WebView2 navigation completed; native embedding still requires visual validation";
              }
              else {
                self->report.status = NativeViewStatus::Failed;
                self->report.message = "WebView2 could not load the admitted document";
              }
              return S_OK;
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_NewWindowRequested(
        Callback<ICoreWebView2NewWindowRequestedEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2NewWindowRequestedEventArgs *args) -> HRESULT {
              if (auto self = weak.lock()) {
                ++self->report.blocked_requests;
              }
              return args->put_Handled(TRUE);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_PermissionRequested(
        Callback<ICoreWebView2PermissionRequestedEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2PermissionRequestedEventArgs *args) -> HRESULT {
              if (auto self = weak.lock()) {
                ++self->report.blocked_requests;
              }
              return args->put_State(COREWEBVIEW2_PERMISSION_STATE_DENY);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = restricted_web->add_DownloadStarting(
        Callback<ICoreWebView2DownloadStartingEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2DownloadStartingEventArgs *args) -> HRESULT {
              if (auto self = weak.lock()) {
                ++self->report.blocked_requests;
              }
              args->put_Handled(TRUE);
              return args->put_Cancel(TRUE);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = restricted_web->add_LaunchingExternalUriScheme(
        Callback<ICoreWebView2LaunchingExternalUriSchemeEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2LaunchingExternalUriSchemeEventArgs *args) -> HRESULT {
              if (auto self = weak.lock()) {
                ++self->report.blocked_requests;
              }
              return args->put_Cancel(TRUE);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = web->add_ProcessFailed(
        Callback<ICoreWebView2ProcessFailedEventHandler>(
            [weak](ICoreWebView2 *, ICoreWebView2ProcessFailedEventArgs *) -> HRESULT {
              if (auto self = weak.lock()) {
                self->fail("WebView2 stopped responding or a browser process exited", E_FAIL);
              }
              return S_OK;
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = controller->add_GotFocus(
        Callback<ICoreWebView2FocusChangedEventHandler>(
            [weak](ICoreWebView2Controller *, IUnknown *) -> HRESULT {
              if (auto self = weak.lock()) {
                self->focused = true;
                if (!self->visible || !self->has_bounds || self->closed) {
                  self->release_focus();
                }
              }
              return S_OK;
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = controller->add_LostFocus(
        Callback<ICoreWebView2FocusChangedEventHandler>(
            [weak](ICoreWebView2Controller *, IUnknown *) -> HRESULT {
              if (auto self = weak.lock()) {
                self->focused = false;
              }
              return S_OK;
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    result = controller->add_MoveFocusRequested(
        Callback<ICoreWebView2MoveFocusRequestedEventHandler>(
            [weak](ICoreWebView2Controller *, ICoreWebView2MoveFocusRequestedEventArgs *args) -> HRESULT {
              if (auto self = weak.lock(); self && !self->closed) {
                self->release_focus();
              }
              return args->put_Handled(TRUE);
            }).Get(), &token);
    if (FAILED(result)) {
      return result;
    }
    return controller->add_AcceleratorKeyPressed(
        Callback<ICoreWebView2AcceleratorKeyPressedEventHandler>(
            [weak](ICoreWebView2Controller *, ICoreWebView2AcceleratorKeyPressedEventArgs *args) -> HRESULT {
              UINT key = 0;
              if (SUCCEEDED(args->get_VirtualKey(&key)) && key == VK_ESCAPE) {
                args->put_Handled(TRUE);
                if (auto self = weak.lock(); self && !self->closed) {
                  self->release_focus();
                }
              }
              return S_OK;
            }).Get(), &token);
  }

  void navigate_pending()
  {
    if (!web || pending_url.empty() || closed || fatal || !navigation_requested ||
        awaiting_navigation_start) {
      return;
    }
    navigation_id = 0;  // A superseded navigation completion must not mark the new request ready.
    const auto uri = wide(pending_url);
    submitted_url = pending_url;
    awaiting_navigation_start = true;
    const HRESULT result = uri.empty() ? E_INVALIDARG : web->Navigate(uri.c_str());
    if (FAILED(result)) {
      fail("Could not start WebView2 document navigation", result);
    }
  }

  HRESULT begin()
  {
    profile = std::make_shared<TemporaryProfile>();
    std::string error;
    if (!profile->create(error)) {
      fail(error, E_FAIL);
      return E_FAIL;
    }
    auto options = Make<CoreWebView2EnvironmentOptions>();
    if (!options) {
      return E_OUTOFMEMORY;
    }
    HRESULT result;
    if (FAILED(result = options->put_AllowSingleSignOnUsingOSPrimaryAccount(FALSE)) ||
        FAILED(result = options->put_ExclusiveUserDataFolderAccess(TRUE)) ||
        FAILED(result = options->put_IsCustomCrashReportingEnabled(TRUE)) ||
        FAILED(result = options->put_AreBrowserExtensionsEnabled(FALSE)) ||
        FAILED(result = options->put_ReleaseChannels(COREWEBVIEW2_RELEASE_CHANNELS_STABLE))) {
      return result;
    }
    const std::weak_ptr<View> weak = shared_from_this();
    return CreateCoreWebView2EnvironmentWithOptions(
        nullptr, profile->path.c_str(), options.Get(),
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [weak, temporary = profile](HRESULT created, ICoreWebView2Environment *native) -> HRESULT {
              auto self = weak.lock();
              if (!self || self->closed || self->fatal) {
                return S_OK;
              }
              if (FAILED(created) || !native) {
                self->fail("Could not create the WebView2 environment", FAILED(created) ? created : E_FAIL);
                return S_OK;
              }
              self->environment = native;
              ComText version;
              if (SUCCEEDED(native->get_BrowserVersionString(&version.value))) {
                self->report.runtime_version = utf8(version.value);
              }
              ComPtr<ICoreWebView2Environment10> modern;
              ComPtr<ICoreWebView2ControllerOptions> controller_options;
              HRESULT result;
              if (FAILED(result = self->environment.As(&modern)) ||
                  FAILED(result = modern->CreateCoreWebView2ControllerOptions(&controller_options)) ||
                  FAILED(result = controller_options->put_IsInPrivateModeEnabled(TRUE))) {
                self->fail("WebView2 Runtime cannot create an isolated preview profile", result);
                return S_OK;
              }
              const ComPtr<ICoreWebView2Environment> environment = self->environment;
              // Subscribe before controller creation. ProcessFailed and BrowserProcessExited
              // have no guaranteed ordering, so subscribing only inside close() can miss exit.
              cleanup_after_browser_exit(environment.Get(), temporary);
              result = modern->CreateCoreWebView2ControllerWithOptions(
                  self->parent, controller_options.Get(),
                  Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                      [weak, temporary, environment](HRESULT created, ICoreWebView2Controller *controller) -> HRESULT {
                        auto self = weak.lock();
                        if (!self || self->closed || self->fatal) {
                          cleanup_after_browser_exit(environment.Get(), temporary);
                          if (controller) {
                            controller->Close();  // Late creation never adopts a destroyed HWND.
                          }
                          return S_OK;
                        }
                        if (FAILED(created) || !controller) {
                          if (controller) {
                            controller->Close();
                          }
                          self->fail("Could not attach WebView2 to the existing window", FAILED(created) ? created : E_FAIL);
                          return S_OK;
                        }
                        if (temporary->browser_exited) {
                          controller->Close();
                          self->fail("WebView2 exited during controller creation", E_FAIL);
                          return S_OK;
                        }
                        self->controller = controller;
                        const HRESULT configured = self->configure();
                        if (FAILED(configured)) {
                          self->fail("WebView2 Runtime does not support the required confined preview policy", configured);
                          return S_OK;
                        }
                        self->layout();
                        self->navigate_pending();
                        return S_OK;
                      }).Get());
              if (FAILED(result)) {
                self->fail("Could not start WebView2 controller creation", result);
              }
              return S_OK;
            }).Get());
  }
};

class Win32DocumentView final : public NativeDocumentView {
 public:
  explicit Win32DocumentView(std::shared_ptr<View> view) : view_(std::move(view)) {}
  ~Win32DocumentView() override { close(); }

  bool navigate(std::string_view path, std::string &error) override
  {
    if (!view_->on_thread() || view_->closed || view_->fatal) {
      error = "The native document view is closed or unavailable";
      return false;
    }
    auto url = view_->resources->url(path, true);
    if (url.empty() || !view_->resources->allows_navigation(url)) {
      error = "The requested document is not admitted to this preview session";
      return false;
    }
    // A session's URL identifies immutable bytes. Re-requesting the same pending/ready version
    // is idempotent; it must not introduce two indistinguishable asynchronous navigation starts.
    if (url == view_->pending_url && (view_->report.status == NativeViewStatus::Loading ||
                                     view_->report.status == NativeViewStatus::Ready)) {
      error.clear();
      return true;
    }
    view_->pending_url = std::move(url);
    view_->navigation_requested = true;
    view_->navigation_id = 0;
    ++view_->report.navigation_generation;
    view_->report.status = NativeViewStatus::Loading;
    view_->report.message = "Loading the admitted document";
    view_->navigate_pending();
    if (view_->fatal) {
      error = view_->report.message;
      return false;
    }
    error.clear();
    return true;
  }

  void set_bounds(ViewBounds bounds) override
  {
    if (view_->on_thread()) {
      view_->bounds = bounds;
      view_->layout();
    }
  }

  void set_visible(bool visible) override
  {
    if (view_->on_thread()) {
      view_->visible = visible;
      view_->layout();
    }
  }

  void focus() override
  {
    if (view_->on_thread() && view_->controller && view_->visible && view_->has_bounds &&
        !view_->closed && !view_->fatal) {
      view_->controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
    }
  }

  void close() override
  {
    if (view_->on_thread() && !view_->closed) {
      view_->closed = true;
      view_->report.status = NativeViewStatus::Closed;
      view_->report.message = "Document preview closed";
      view_->shutdown();
    }
  }

  NativeViewState state() const override
  {
    NativeViewState result = view_->report;
    result.parent_attached = false;
    result.visible = false;
    if (!view_->on_thread() || view_->closed || view_->fatal || !view_->controller) {
      return result;
    }
    HWND actual_parent = nullptr;
    if (FAILED(view_->controller->get_ParentWindow(&actual_parent)) ||
        actual_parent != view_->parent || !IsWindow(actual_parent)) {
      return result;
    }
    result.parent_attached = true;
    BOOL controller_visible = FALSE;
    RECT actual_bounds{}, client{}, intersection{};
    result.visible = SUCCEEDED(view_->controller->get_IsVisible(&controller_visible)) &&
                     controller_visible && IsWindowVisible(actual_parent) &&
                     !IsIconic(actual_parent) &&
                     SUCCEEDED(view_->controller->get_Bounds(&actual_bounds)) &&
                     GetClientRect(actual_parent, &client) &&
                     IntersectRect(&intersection, &actual_bounds, &client);
    // These are queried attachment/visibility flags, not proof of painting or lack of occlusion.
    return result;
  }

 private:
  std::shared_ptr<View> view_;
};

}  // namespace

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle parent, std::shared_ptr<ResourceSession> resources, std::string &error)
{
  error.clear();
  if (parent.kind != wm::NativeWindowKind::Win32 || !IsWindow(static_cast<HWND>(parent.value)) ||
      GetWindowThreadProcessId(static_cast<HWND>(parent.value), nullptr) != GetCurrentThreadId() ||
      !resources || !resources->active()) {
    error = "WebView2 requires an existing window and active resource session on its UI thread";
    return nullptr;
  }
  APTTYPE apartment;
  APTTYPEQUALIFIER qualifier;
  const HRESULT initialized = CoGetApartmentType(&apartment, &qualifier);
  if (FAILED(initialized) || (apartment != APTTYPE_STA && apartment != APTTYPE_MAINSTA)) {
    error = "WebView2 requires the existing GHOST UI thread to use a COM STA";
    return nullptr;
  }
  auto view = std::make_shared<View>();
  view->parent = static_cast<HWND>(parent.value);
  view->resources = std::move(resources);
  view->report.message = "Creating the WebView2 native child view";
  const HRESULT started = view->begin();
  if (FAILED(started)) {
    view->fail("Could not initialize WebView2", started);
    error = view->report.message;
  }
  // Keep a readable Failed state for missing Runtime; never silently open another window.
  return std::make_unique<Win32DocumentView>(std::move(view));
}

}  // namespace stk::document_preview
