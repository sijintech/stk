/* SPDX-License-Identifier: GPL-2.0-or-later */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <dwmapi.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <GL/gl.h>
#include <cstdio>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include "window_evidence.hh"
#include "stk/io/json.hh"
#include <atomic>
#include <cstdint>
#include <cwchar>
#include <iterator>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace stk::document_preview {
namespace {
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;

// This file belongs only to the opt-in acceptance executables. Keep the diagnostic handle
// for their whole process lifetime, including engine static destruction; Windows closes it
// on exit. Never serialize stack memory, registers containing data, or an environment dump.
HANDLE crash_file = INVALID_HANDLE_VALUE;
std::atomic<const char *> last_stage{"diagnostics.not-installed"};
static_assert(std::atomic<const char *>::is_always_lock_free);
std::atomic<unsigned> stage_count{0};
volatile LONG handling_crash = 0;

void write_crash_line(const char *line, DWORD length) noexcept
{
  if (crash_file != INVALID_HANDLE_VALUE) {
    DWORD written = 0;
    WriteFile(crash_file, line, length, &written, nullptr);
    FlushFileBuffers(crash_file);
  }
  // Avoid stdio stream locks in this write path. Ordinary lifecycle logging explicitly
  // flushes stdout; fault logging writes directly to the already inherited stderr handle.
  const auto error = GetStdHandle(STD_ERROR_HANDLE);
  if (error && error != INVALID_HANDLE_VALUE) {
    DWORD written = 0;
    WriteFile(error, line, length, &written, nullptr);
  }
}

void record_fault_frame(unsigned index, uintptr_t address) noexcept
{
  MEMORY_BASIC_INFORMATION memory{};
  const auto base = VirtualQuery(reinterpret_cast<const void *>(address), &memory, sizeof(memory)) ?
      reinterpret_cast<uintptr_t>(memory.AllocationBase) : uintptr_t(0);
  wchar_t module_path[1024]{};
  char module_name[128] = "unknown";
  const auto count = base ? GetModuleFileNameW(reinterpret_cast<HMODULE>(base), module_path,
                                               DWORD(std::size(module_path))) : 0;
  if (count && count < std::size(module_path)) {
    DWORD start = 0;
    for (DWORD i = 0; i < count; ++i) {
      if (module_path[i] == L'\\' || module_path[i] == L'/') { start = i + 1; }
    }
    size_t out = 0;
    for (DWORD i = start; i < count && out + 1 < sizeof(module_name); ++i) {
      const auto c = module_path[i];
      module_name[out++] = c >= 33 && c <= 126 && c != '=' ? char(c) : '?';
    }
    module_name[out] = '\0';
  }
  char line[384]{};
  const int length = std::snprintf(line, sizeof(line),
      "STK_NATIVE_CRASH_FRAME index=%u address=0x%llx module=%s allocation_base=0x%llx offset=0x%llx\n",
      index, static_cast<unsigned long long>(address), module_name, static_cast<unsigned long long>(base),
      static_cast<unsigned long long>(base ? address - base : 0));
  if (length > 0 && size_t(length) < sizeof(line)) { write_crash_line(line, DWORD(length)); }
}

void record_fault_stack(const CONTEXT *source) noexcept
{
#if defined(_M_X64)
  // Unwind a COPY of the fault context, not the exception-handler call stack. No symbols,
  // DLL loading, callbacks of our own or heap allocations are needed. A damaged stack or
  // driver unwind table must not prevent the already flushed exception record surviving.
  __try {
    CONTEXT context = *source;
    for (unsigned index = 0; index < 32 && context.Rip; ++index) {
      record_fault_frame(index, uintptr_t(context.Rip));
      const auto previous_ip = context.Rip;
      const auto previous_sp = context.Rsp;
      DWORD64 image_base = 0;
      const auto entry = RtlLookupFunctionEntry(context.Rip, &image_base, nullptr);
      if (entry) {
        PVOID handler_data = nullptr;
        DWORD64 frame = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, image_base, context.Rip, entry, &context,
                        &handler_data, &frame, nullptr);
      }
      else {
        DWORD64 return_address = 0;
        SIZE_T bytes = 0;
        if (!ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<const void *>(context.Rsp),
                               &return_address, sizeof(return_address), &bytes) ||
            bytes != sizeof(return_address)) { break; }
        context.Rip = return_address;
        context.Rsp += sizeof(return_address);
      }
      if (context.Rsp <= previous_sp || context.Rsp - previous_sp > 1024 * 1024 ||
          context.Rip == previous_ip) { break; }
    }
  }
  __except (EXCEPTION_EXECUTE_HANDLER) {
    constexpr char line[] = "STK_NATIVE_CRASH_STACK stopped=invalid-unwind\n";
    write_crash_line(line, DWORD(sizeof(line) - 1));
  }
#else
  (void)source;
  constexpr char line[] = "STK_NATIVE_CRASH_STACK unavailable=non-x64\n";
  write_crash_line(line, DWORD(sizeof(line) - 1));
#endif
}

LONG WINAPI record_unhandled_exception(EXCEPTION_POINTERS *exception) noexcept
{
  if (InterlockedCompareExchange(&handling_crash, 1, 0) != 0) { return EXCEPTION_CONTINUE_SEARCH; }
  const auto *record = exception ? exception->ExceptionRecord : nullptr;
  char line[384]{};
  const int length = std::snprintf(line, sizeof(line),
      "STK_NATIVE_CRASH code=0x%08lx address=0x%llx thread=%lu last_stage=%s\n",
      record ? record->ExceptionCode : 0ul,
      static_cast<unsigned long long>(record ? reinterpret_cast<uintptr_t>(record->ExceptionAddress) : 0),
      GetCurrentThreadId(), last_stage.load(std::memory_order_relaxed));
  if (length > 0 && size_t(length) < sizeof(line)) { write_crash_line(line, DWORD(length)); }
  if (exception && exception->ContextRecord) { record_fault_stack(exception->ContextRecord); }
  // Preserve the original failure and normal Windows termination. Never resume execution,
  // convert a crash to a passing exit, or emit any successful native-evidence marker.
  return EXCEPTION_CONTINUE_SEARCH;
}

void stage(const char *name, long result = 0, DWORD error = 0) noexcept
{
  last_stage.store(name, std::memory_order_relaxed); // All callers use fixed string literals.
  if (stage_count.fetch_add(1, std::memory_order_relaxed) >= 128) { return; }
  std::printf("STK_NATIVE_STAGE name=%s thread=%lu result=%ld win32_error=%lu\n",
              name, GetCurrentThreadId(), result, error);
  std::fflush(stdout);
}

std::string install_crash_diagnostics()
{
  static bool installed = false; // Only the acceptance UI thread calls this entry point.
  if (installed) { return {}; }
  wchar_t root[32768]{};
  const auto count = GetEnvironmentVariableW(L"STK_NATIVE_TEST_DIR", root, DWORD(std::size(root)));
  if (count >= std::size(root)) { return "Native diagnostic evidence directory exceeds path budget"; }
  if (count) {
    // The explicit CI evidence directory is a local absolute path. Do not open a network
    // share or follow a redirected evidence child. The fixed basename cannot escape it.
    if (count < 3 || root[1] != L':' || (root[2] != L'\\' && root[2] != L'/')) {
      return "Native diagnostic evidence directory must be an absolute local drive path";
    }
    const auto folder = std::wstring(root, count) + L"\\evidence";
    const auto attributes = GetFileAttributesW(folder.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY) ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
      return "Native diagnostic evidence child directory is missing or redirected";
    }
    wchar_t basename[96]{};
    std::swprintf(basename, std::size(basename), L"\\native-crash-%lu-%llu.txt", GetCurrentProcessId(),
                  static_cast<unsigned long long>(GetTickCount64()));
    const auto path = folder + basename;
    if (path.size() >= 32768) { return "Native diagnostic evidence file exceeds path budget"; }
    crash_file = CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW,
                             FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, nullptr);
    if (crash_file == INVALID_HANDLE_VALUE) { return "Cannot create exclusive native crash evidence file"; }
    constexpr char header[] = "STK_NATIVE_CRASH_FORMAT version=1 stack=addresses-only limit=32\n";
    DWORD written = 0;
    if (!WriteFile(crash_file, header, DWORD(sizeof(header) - 1), &written, nullptr) ||
        written != sizeof(header) - 1 || !FlushFileBuffers(crash_file)) {
      CloseHandle(crash_file); crash_file = INVALID_HANDLE_VALUE;
      return "Cannot flush native crash evidence header";
    }
  }
  SetUnhandledExceptionFilter(record_unhandled_exception);
  installed = true;
  stage(count ? "diagnostics.installed.file-and-stderr" : "diagnostics.installed.stderr-only");
  return {};
}

class Capture final : public WindowEvidenceCapture {
 public:
  explicit Capture(wm::NativeWindowHandle parent)
  {
    try {
      // Test-only, explicit selection: never silently reinterpret a hardware failure as WARP.
      wchar_t requested[16]{};
      const auto count = GetEnvironmentVariableW(L"STK_NATIVE_EVIDENCE_D3D_DRIVER", requested, 16);
      if (count >= 16) { throw std::runtime_error("Invalid native evidence D3D driver option"); }
      const std::wstring_view option(requested, count);
      const bool warp = option == L"warp";
      if (!option.empty() && option != L"hardware" && !warp) {
        throw std::runtime_error("STK_NATIVE_EVIDENCE_D3D_DRIVER must be hardware or warp");
      }
      backend_ += warp ? ";d3d11_request=warp" : ";d3d11_request=hardware";
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
      // Microsoft supports WARP through this same API. WGC support and actual pixels still
      // have to pass below; choosing WARP does not bypass any capability or image check.
      D3D_FEATURE_LEVEL feature_level{};
      winrt::check_hresult(D3D11CreateDevice(nullptr,
          warp ? D3D_DRIVER_TYPE_WARP : D3D_DRIVER_TYPE_HARDWARE, nullptr,
          D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
          device_.put(), &feature_level, context_.put()));
      const auto dxgi = device_.as<IDXGIDevice>();
      winrt::com_ptr<IDXGIAdapter> adapter;
      winrt::check_hresult(dxgi->GetAdapter(adapter.put()));
      DXGI_ADAPTER_DESC1 description{};
      winrt::check_hresult(adapter.as<IDXGIAdapter1>()->GetDesc1(&description));
      const bool software = (description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) != 0;
      backend_ += ";adapter=" + winrt::to_string(description.Description) +
          ";adapter_software=" + (software ? std::string("true") : std::string("false")) +
          ";feature_level=" + std::to_string(unsigned(feature_level));
      if (warp && !software) { throw std::runtime_error("WARP capture did not report a software DXGI adapter"); }
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
    out.backend = backend_;
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
  std::string backend_ = "windows-graphics-capture-window-client";
  winrt::com_ptr<ID3D11Device> device_;
  winrt::com_ptr<ID3D11DeviceContext> context_;
  GraphicsCaptureItem item_{nullptr};
  Direct3D11CaptureFramePool pool_{nullptr};
  GraphicsCaptureSession session_{nullptr};
};
}
std::string native_evidence_environment_error()
{
  if (const auto error = install_crash_diagnostics(); !error.empty()) { return error; }
  stage("probe.begin");
  wchar_t software_option[4]{};
  const auto software_count = GetEnvironmentVariableW(
      L"STK_NATIVE_EVIDENCE_REQUIRE_LLVMPIPE", software_option, 4);
  if (software_count >= 4) { return "Invalid native evidence software-renderer option"; }
  const std::wstring_view software(software_option, software_count);
  if (!software.empty() && software != L"0" && software != L"1") {
    return "STK_NATIVE_EVIDENCE_REQUIRE_LLVMPIPE must be 0 or 1";
  }
  const bool require_llvmpipe = software == L"1";
  // Version overrides can advertise unsupported contexts. Never accept them as capability
  // evidence, even outside the explicit software mode. Read only presence, not their values.
  for (const auto *name : {L"MESA_GL_VERSION_OVERRIDE", L"MESA_GLSL_VERSION_OVERRIDE",
                           L"MESA_GLES_VERSION_OVERRIDE"}) {
    if (GetEnvironmentVariableW(name, nullptr, 0) != 0) {
      return "Native evidence refuses Mesa GL/GLSL/GLES version overrides";
    }
  }
  const auto gl_module = GetModuleHandleW(L"opengl32.dll"); // Borrowed module already imported.
  if (!gl_module) { return "Cannot identify the loaded OpenGL module"; }
  std::wstring module_path(32768, L'\0');
  const auto path_size = GetModuleFileNameW(gl_module, module_path.data(), DWORD(module_path.size()));
  if (!path_size || path_size >= module_path.size()) {
    return "Cannot read the complete loaded opengl32.dll path";
  }
  module_path.resize(path_size);
  const auto loaded_path = winrt::to_string(module_path);
  const auto gl_text = [](GLenum name) {
    const auto *value = reinterpret_cast<const char *>(glGetString(name));
    if (!value) { throw std::runtime_error("OpenGL probe did not provide its driver strings"); }
    size_t count = 0;
    while (count < 4096 && value[count]) { ++count; }
    if (!count || count == 4096) { throw std::runtime_error("OpenGL probe driver string is empty or exceeds metadata budget"); }
    return std::string(value, count);
  };
  const auto record_gl = [&](const char *stage) {
    const auto renderer = gl_text(GL_RENDERER);
    const io::Json metadata = {{"format", "stk.native-gl-provenance/1"}, {"stage", stage},
        {"require_llvmpipe", require_llvmpipe}, {"opengl32_path", loaded_path},
        {"gl_vendor", gl_text(GL_VENDOR)}, {"gl_renderer", renderer}, {"gl_version", gl_text(GL_VERSION)}};
    // The acceptance log is uploaded with evidence. JSON escapes driver text and paths so
    // one probe remains one controlled line; no other process/module/environment is inspected.
    const auto encoded = metadata.dump(-1, ' ', true, io::Json::error_handler_t::replace);
    if (std::printf("STK_NATIVE_GL_PROVENANCE %s\n", encoded.c_str()) < 0 || std::fflush(stdout) != 0) {
      throw std::runtime_error("Cannot write native OpenGL provenance evidence");
    }
    auto normalized = renderer;
    for (auto &c : normalized) { if (c >= 'A' && c <= 'Z') { c = char(c - 'A' + 'a'); } }
    return !require_llvmpipe || normalized.find("llvmpipe") != std::string::npos;
  };
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
  stage("probe.dpi.before");
  if (!set_process_context(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE) &&
      get_context_awareness(get_thread_context()) != DPI_AWARENESS_PER_MONITOR_AWARE) {
    return "Cannot establish GHOST-compatible per-monitor DPI awareness before the GL probe";
  }
  if (get_context_awareness(get_thread_context()) != DPI_AWARENESS_PER_MONITOR_AWARE) {
    return "The native evidence UI thread has an incompatible DPI context";
  }
  stage("probe.dpi.after");
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
      stage("probe.teardown.begin");
      if (legacy || modern) {
        stage("probe.unbind.before");
        const auto ok = wglMakeCurrent(nullptr, nullptr);
        stage("probe.unbind.after", ok, ok ? 0 : GetLastError());
      }
      if (modern) {
        stage("probe.delete-core.before");
        const auto ok = wglDeleteContext(modern);
        stage("probe.delete-core.after", ok, ok ? 0 : GetLastError());
      }
      if (legacy) {
        stage("probe.delete-legacy.before");
        const auto ok = wglDeleteContext(legacy);
        stage("probe.delete-legacy.after", ok, ok ? 0 : GetLastError());
      }
      if (dc) {
        stage("probe.release-dc.before");
        const auto ok = ReleaseDC(window, dc);
        stage("probe.release-dc.after", ok); // ReleaseDC does not define GetLastError.
      }
      if (window) {
        stage("probe.destroy-window.before");
        const auto ok = DestroyWindow(window);
        stage("probe.destroy-window.after", ok, ok ? 0 : GetLastError());
      }
      if (atom) {
        stage("probe.unregister-class.before");
        const auto ok = UnregisterClassW(name, instance);
        stage("probe.unregister-class.after", ok, ok ? 0 : GetLastError());
      }
      stage("probe.teardown.end");
    }
  } p;
  WNDCLASSW cls{};
  cls.style = CS_OWNDC;
  cls.lpfnWndProc = DefWindowProcW;
  cls.hInstance = p.instance;
  cls.lpszClassName = p.name;
  stage("probe.register-class.before");
  p.atom = RegisterClassW(&cls);
  stage("probe.register-class.after", p.atom, p.atom ? 0 : GetLastError());
  if (!p.atom) { return "Cannot register the isolated STK OpenGL capability probe"; }
  stage("probe.create-window.before");
  p.window = CreateWindowW(p.name, L"STK native evidence capability probe", WS_OVERLAPPEDWINDOW,
                            0, 0, 64, 64, nullptr, nullptr, p.instance, nullptr);
  stage("probe.create-window.after", p.window != nullptr, p.window ? 0 : GetLastError());
  stage("probe.get-dc.before");
  if (!p.window || !(p.dc = GetDC(p.window))) { return "No interactive Win32 window/DC for the STK probe"; }
  stage("probe.get-dc.after", 1);
  PIXELFORMATDESCRIPTOR format{};
  format.nSize = sizeof(format); format.nVersion = 1;
  format.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
  format.iPixelType = PFD_TYPE_RGBA; format.cColorBits = 32;
  format.cDepthBits = 24; format.cStencilBits = 8;
  stage("probe.pixel-format.before");
  const int index = ChoosePixelFormat(p.dc, &format);
  if (!index || !SetPixelFormat(p.dc, index, &format)) {
    return "Windows runner cannot create an OpenGL context; native preview is unverified";
  }
  stage("probe.pixel-format.after", index);
  stage("probe.create-legacy.before");
  p.legacy = wglCreateContext(p.dc);
  stage("probe.create-legacy.after", p.legacy != nullptr, p.legacy ? 0 : GetLastError());
  if (!p.legacy) { return "Windows runner cannot create an OpenGL context; native preview is unverified"; }
  stage("probe.bind-legacy.before");
  if (!wglMakeCurrent(p.dc, p.legacy)) {
    return "Windows runner cannot create an OpenGL context; native preview is unverified";
  }
  stage("probe.bind-legacy.after", 1);
  if (!record_gl("legacy")) { return "The actual OpenGL renderer is not the explicitly required llvmpipe"; }
  const auto legacy_version = gl_text(GL_VERSION);
  stage("probe.lookup-core.before");
  const auto address = wglGetProcAddress("wglCreateContextAttribsARB");
  stage("probe.lookup-core.after");
  const auto value = reinterpret_cast<uintptr_t>(address);
  if (!address || value <= 3 || value == UINTPTR_MAX) {
    return "Native STK window needs OpenGL 4.3 core; runner exposes " + legacy_version +
           " without WGL_ARB_create_context. No driver or Runtime was installed.";
  }
  using CreateContext = HGLRC(WINAPI *)(HDC, HGLRC, const int *);
  // WGL_CONTEXT_MAJOR_VERSION_ARB, MINOR_VERSION_ARB, PROFILE_MASK_ARB, CORE_PROFILE_BIT_ARB.
  const int attributes[] = {0x2091, 4, 0x2092, 3, 0x9126, 1, 0};
  const auto create = reinterpret_cast<CreateContext>(address);
  stage("probe.create-core.before");
  p.modern = create(p.dc, nullptr, attributes);
  stage("probe.create-core.after", p.modern != nullptr, p.modern ? 0 : GetLastError());
  if (!p.modern) {
    return "Native STK window needs OpenGL 4.3 core; creation failed on runner GL " + legacy_version;
  }
  stage("probe.bind-core.before");
  if (!wglMakeCurrent(p.dc, p.modern)) {
    return "Native STK window needs OpenGL 4.3 core; creation failed on runner GL " + legacy_version;
  }
  stage("probe.bind-core.after", 1);
  if (!record_gl("core")) { return "The actual OpenGL core renderer is not the explicitly required llvmpipe"; }
  stage("probe.verify-core.before");
  int major = 0, minor = 0;
  const auto modern_text = gl_text(GL_VERSION);
  if (std::sscanf(modern_text.c_str(), "%d.%d", &major, &minor) != 2 ||
      major < 4 || (major == 4 && minor < 3)) {
    return "The runner did not supply the requested OpenGL 4.3 context";
  }
  stage("probe.verify-core.after", 1);
  // Driver strings were already emitted as escaped JSON; keep this stage line fixed.
  stage("probe.return-success.pending-teardown");
  return {};
}
std::unique_ptr<WindowEvidenceCapture> capture_window_evidence(wm::NativeWindowHandle parent)
{
  return std::make_unique<Capture>(parent);
}
}  // namespace stk::document_preview
