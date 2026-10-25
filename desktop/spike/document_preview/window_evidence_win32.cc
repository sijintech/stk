/* SPDX-License-Identifier: GPL-2.0-or-later */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <dwmapi.h>
#include <d3d11.h>
#include <GL/gl.h>
#include <cstdio>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include "window_evidence.hh"
#include <stdexcept>
#include <utility>

namespace stk::document_preview {
namespace {
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;

class Capture final : public WindowEvidenceCapture {
 public:
  explicit Capture(wm::NativeWindowHandle parent)
  {
    try {
      winrt::init_apartment(winrt::apartment_type::single_threaded);
      apartment_ = true;
      window_ = static_cast<HWND>(parent.value);
      if (parent.kind != wm::NativeWindowKind::Win32 || !IsWindow(window_) ||
          !IsWindowVisible(window_) || IsIconic(window_) || !GraphicsCaptureSession::IsSupported()) {
        throw std::runtime_error("Windows Graphics Capture needs a visible STK window and supported interactive session");
      }
      DWORD owner = 0;
      if (!GetWindowThreadProcessId(window_, &owner) || owner != GetCurrentProcessId()) {
        throw std::runtime_error("Evidence capture refuses a window outside this STK process");
      }
      client_ = client_bounds();
      winrt::check_hresult(DwmGetWindowAttribute(window_, DWMWA_EXTENDED_FRAME_BOUNDS,
                                                 &outer_, sizeof(outer_)));
      auto interop = winrt::get_activation_factory<GraphicsCaptureItem, IGraphicsCaptureItemInterop>();
      winrt::check_hresult(interop->CreateForWindow(window_, winrt::guid_of<GraphicsCaptureItem>(),
                                                   winrt::put_abi(item_)));
      const auto size = item_.Size();
      if (size.Width != outer_.right - outer_.left || size.Height != outer_.bottom - outer_.top ||
          size.Width <= 0 || size.Height <= 0 || size.Width > 8192 || size.Height > 8192 ||
          int64_t(size.Width) * size.Height > 16 * 1024 * 1024 ||
          client_.left < outer_.left || client_.top < outer_.top ||
          client_.right > outer_.right || client_.bottom > outer_.bottom) {
        throw std::runtime_error("Captured window geometry does not match the bounded STK client area");
      }
      // Capture has its own D3D device; the STK rendering backend remains OpenGL.
      winrt::check_hresult(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
          D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
          device_.put(), nullptr, context_.put()));
      const auto dxgi = device_.as<IDXGIDevice>();
      winrt::com_ptr<IInspectable> inspectable;
      winrt::check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.get(), inspectable.put()));
      pool_ = Direct3D11CaptureFramePool::CreateFreeThreaded(inspectable.as<IDirect3DDevice>(),
          DirectXPixelFormat::B8G8R8A8UIntNormalized, 1, size);
      session_ = pool_.CreateCaptureSession(item_);
      session_.IsCursorCaptureEnabled(false);
      // Keep the OS capture indicator; do not ask for borderless-capture privileges.
      session_.StartCapture();
    }
    catch (const winrt::hresult_error &e) { error_ = winrt::to_string(e.message()); }
    catch (const std::exception &e) { error_ = e.what(); }
  }
  ~Capture() override
  {
    // No callback or worker owns a borrowed HWND. Free-threaded frames are polled on the UI thread.
    try { if (session_) { session_.Close(); } } catch (...) {}
    try { if (pool_) { pool_.Close(); } } catch (...) {}
    session_ = nullptr; pool_ = nullptr; item_ = nullptr;
    context_ = nullptr; device_ = nullptr;
    if (apartment_) { winrt::uninit_apartment(); }
  }
  std::optional<WindowEvidence> poll() override
  {
    WindowEvidence out;
    out.backend = "windows-graphics-capture-window-client";
    if (!error_.empty()) { out.error = error_; return out; }
    Direct3D11CaptureFrame frame{nullptr};
    bool mapped = false;
    winrt::com_ptr<ID3D11Texture2D> staging;
    try {
      RECT current_outer{};
      winrt::check_hresult(DwmGetWindowAttribute(window_, DWMWA_EXTENDED_FRAME_BOUNDS,
                                                 &current_outer, sizeof(current_outer)));
      const auto current_client = client_bounds();
      if (!IsWindow(window_) || !IsWindowVisible(window_) || IsIconic(window_) ||
          !EqualRect(&client_, &current_client) || !EqualRect(&outer_, &current_outer)) {
        throw std::runtime_error("STK window moved or closed during evidence capture");
      }
      frame = pool_.TryGetNextFrame();
      if (!frame) { return std::nullopt; }
      const auto size = frame.ContentSize();
      if (size.Width != item_.Size().Width || size.Height != item_.Size().Height) {
        throw std::runtime_error("STK capture geometry changed");
      }
      const auto access = frame.Surface().as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
      winrt::com_ptr<ID3D11Texture2D> texture;
      winrt::check_hresult(access->GetInterface(__uuidof(ID3D11Texture2D), texture.put_void()));
      D3D11_TEXTURE2D_DESC desc{};
      texture->GetDesc(&desc);
      if (desc.Format != DXGI_FORMAT_B8G8R8A8_UNORM || desc.Width < UINT(size.Width) ||
          desc.Height < UINT(size.Height)) {
        throw std::runtime_error("Windows capture texture format or extent changed");
      }
      desc.Width = UINT(client_.right - client_.left);
      desc.Height = UINT(client_.bottom - client_.top);
      desc.MipLevels = 1; desc.ArraySize = 1;
      desc.SampleDesc.Count = 1; desc.SampleDesc.Quality = 0;
      desc.Usage = D3D11_USAGE_STAGING;
      desc.BindFlags = 0; desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ; desc.MiscFlags = 0;
      winrt::check_hresult(device_->CreateTexture2D(&desc, nullptr, staging.put()));
      D3D11_BOX box{UINT(client_.left - outer_.left), UINT(client_.top - outer_.top), 0,
                    UINT(client_.right - outer_.left), UINT(client_.bottom - outer_.top), 1};
      context_->CopySubresourceRegion(staging.get(), 0, 0, 0, 0, texture.get(), 0, &box);
      D3D11_MAPPED_SUBRESOURCE data{};
      winrt::check_hresult(context_->Map(staging.get(), 0, D3D11_MAP_READ, 0, &data));
      mapped = true;
      out.image = io::Image(desc.Width, desc.Height);
      for (uint32_t y = 0; y < desc.Height; ++y) {
        const auto *src = static_cast<const uint8_t *>(data.pData) + size_t(y) * data.RowPitch;
        auto *dst = out.image.row(y);
        for (uint32_t x = 0; x < desc.Width; ++x) {
          dst[4*x] = src[4*x+2]; dst[4*x+1] = src[4*x+1];
          dst[4*x+2] = src[4*x]; dst[4*x+3] = 255;
        }
      }
    }
    catch (const winrt::hresult_error &e) { out.error = winrt::to_string(e.message()); }
    catch (const std::exception &e) { out.error = e.what(); }
    if (mapped) { context_->Unmap(staging.get(), 0); }
    try { if (frame) { frame.Close(); } }
    catch (const winrt::hresult_error &e) { out.error = winrt::to_string(e.message()); }
    return out;
  }
 private:
  RECT client_bounds()
  {
    RECT rect{};
    POINT top{}, bottom{};
    if (!GetClientRect(window_, &rect)) { throw std::runtime_error("Cannot get STK client geometry"); }
    bottom = {rect.right, rect.bottom};
    if (!ClientToScreen(window_, &top) || !ClientToScreen(window_, &bottom) ||
        bottom.x <= top.x || bottom.y <= top.y) { throw std::runtime_error("Cannot locate STK client area"); }
    return {top.x, top.y, bottom.x, bottom.y};
  }
  bool apartment_ = false;
  HWND window_ = nullptr;
  RECT client_{}, outer_{};
  std::string error_;
  winrt::com_ptr<ID3D11Device> device_;
  winrt::com_ptr<ID3D11DeviceContext> context_;
  GraphicsCaptureItem item_{nullptr};
  Direct3D11CaptureFramePool pool_{nullptr};
  GraphicsCaptureSession session_{nullptr};
};
}
std::string native_evidence_environment_error()
{
  // GHOST requests PROCESS_PER_MONITOR_DPI_AWARE during its later startup. Set that same
  // process default before the probe's first HWND: changing it after any HWND is unsupported
  // and could mix virtualized client coordinates with DWM's physical capture pixels.
  // The shared Blender target retains _WIN32_WINNT=0x0603. Resolve these newer
  // User32 APIs only for this opt-in evidence path; neither headers nor imports should
  // raise the main product's minimum OS. Missing APIs are a failed capability check.
  using SetProcessContext = BOOL(WINAPI *)(DPI_AWARENESS_CONTEXT);
  using GetThreadContext = DPI_AWARENESS_CONTEXT(WINAPI *)();
  using GetContextAwareness = DPI_AWARENESS(WINAPI *)(DPI_AWARENESS_CONTEXT);
  const HMODULE user32 = GetModuleHandleW(L"user32.dll"); // Borrowed; do not FreeLibrary.
  const auto set_process_context = user32 ? reinterpret_cast<SetProcessContext>(
      GetProcAddress(user32, "SetProcessDpiAwarenessContext")) : nullptr;
  const auto get_thread_context = user32 ? reinterpret_cast<GetThreadContext>(
      GetProcAddress(user32, "GetThreadDpiAwarenessContext")) : nullptr;
  const auto get_context_awareness = user32 ? reinterpret_cast<GetContextAwareness>(
      GetProcAddress(user32, "GetAwarenessFromDpiAwarenessContext")) : nullptr;
  if (!set_process_context || !get_thread_context || !get_context_awareness) {
    return "Native evidence requires User32 DPI awareness context APIs; one or more are unavailable";
  }
  if (!set_process_context(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE) &&
      get_context_awareness(get_thread_context()) != DPI_AWARENESS_PER_MONITOR_AWARE) {
    return "Cannot establish GHOST-compatible per-monitor DPI awareness before the GL probe";
  }
  if (get_context_awareness(get_thread_context()) != DPI_AWARENESS_PER_MONITOR_AWARE) {
    return "The native evidence UI thread has an incompatible DPI context";
  }
  // GHOST displays a modal dialog on GL startup failure. Probe our own hidden window first
  // so a runner with only Microsoft's GL 1.1 fails with a durable, non-interactive diagnosis.
  // This DC belongs solely to this temporary STK window: no screen DC or pixels are read.
  struct Probe {
    HINSTANCE instance = GetModuleHandleW(nullptr);
    const wchar_t *name = L"STKNativeEvidenceGLProbe";
    ATOM atom = 0;
    HWND window = nullptr;
    HDC dc = nullptr;
    HGLRC legacy = nullptr, modern = nullptr;
    ~Probe()
    {
      if (legacy || modern) { wglMakeCurrent(nullptr, nullptr); }
      if (modern) { wglDeleteContext(modern); }
      if (legacy) { wglDeleteContext(legacy); }
      if (dc) { ReleaseDC(window, dc); }
      if (window) { DestroyWindow(window); }
      if (atom) { UnregisterClassW(name, instance); }
    }
  } p;
  WNDCLASSW cls{};
  cls.style = CS_OWNDC;
  cls.lpfnWndProc = DefWindowProcW;
  cls.hInstance = p.instance;
  cls.lpszClassName = p.name;
  p.atom = RegisterClassW(&cls);
  if (!p.atom) { return "Cannot register the isolated STK OpenGL capability probe"; }
  p.window = CreateWindowW(p.name, L"STK native evidence capability probe", WS_OVERLAPPEDWINDOW,
                            0, 0, 64, 64, nullptr, nullptr, p.instance, nullptr);
  if (!p.window || !(p.dc = GetDC(p.window))) { return "No interactive Win32 window/DC for the STK probe"; }
  PIXELFORMATDESCRIPTOR format{};
  format.nSize = sizeof(format); format.nVersion = 1;
  format.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
  format.iPixelType = PFD_TYPE_RGBA; format.cColorBits = 32;
  format.cDepthBits = 24; format.cStencilBits = 8;
  const int index = ChoosePixelFormat(p.dc, &format);
  if (!index || !SetPixelFormat(p.dc, index, &format) ||
      !(p.legacy = wglCreateContext(p.dc)) || !wglMakeCurrent(p.dc, p.legacy)) {
    return "Windows runner cannot create an OpenGL context; native preview is unverified";
  }
  const auto version_text = glGetString(GL_VERSION);
  const std::string legacy_version = version_text ? reinterpret_cast<const char *>(version_text) : "unknown";
  const auto address = wglGetProcAddress("wglCreateContextAttribsARB");
  const auto value = reinterpret_cast<uintptr_t>(address);
  if (!address || value <= 3 || value == UINTPTR_MAX) {
    return "Native STK window needs OpenGL 4.3 core; runner exposes " + legacy_version +
           " without WGL_ARB_create_context. No driver or Runtime was installed.";
  }
  using CreateContext = HGLRC(WINAPI *)(HDC, HGLRC, const int *);
  // WGL_CONTEXT_MAJOR_VERSION_ARB, MINOR_VERSION_ARB, PROFILE_MASK_ARB, CORE_PROFILE_BIT_ARB.
  const int attributes[] = {0x2091, 4, 0x2092, 3, 0x9126, 1, 0};
  const auto create = reinterpret_cast<CreateContext>(address);
  p.modern = create(p.dc, nullptr, attributes);
  if (!p.modern || !wglMakeCurrent(p.dc, p.modern)) {
    return "Native STK window needs OpenGL 4.3 core; creation failed on runner GL " + legacy_version;
  }
  int major = 0, minor = 0;
  const auto modern_text = glGetString(GL_VERSION);
  if (!modern_text || std::sscanf(reinterpret_cast<const char *>(modern_text), "%d.%d", &major, &minor) != 2 ||
      major < 4 || (major == 4 && minor < 3)) {
    return "The runner did not supply the requested OpenGL 4.3 context";
  }
  std::printf("Native evidence capability probe: OpenGL %s; actual window/capture still pending\n", reinterpret_cast<const char *>(modern_text));
  return {};
}
std::unique_ptr<WindowEvidenceCapture> capture_window_evidence(wm::NativeWindowHandle parent)
{
  return std::make_unique<Capture>(parent);
}
}  // namespace stk::document_preview
