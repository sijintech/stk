/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/document/native_view.hh"
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
#  include "stk/document/test_media_probe.hh"
#endif

namespace stk::document_preview {
namespace {
class UnsupportedView final : public NativeDocumentView {
 public:
  explicit UnsupportedView(std::shared_ptr<ResourceSession> resources)
      : resources_(std::move(resources))
  {
    state_.status = NativeViewStatus::Unsupported;
    state_.message = "Embedded document preview is not supported on this platform yet.";
  }
  ~UnsupportedView() override { close(); }
  bool navigate(std::string_view, std::string &error) override
  {
    error = state_.message;
    return false;
  }
  void set_bounds(ViewBounds) override {}
  void set_visible(bool) override {}
  bool pause_media(std::string &error) override
  {
    error = "Media playback control is not supported on this platform.";
    return false;
  }
  void focus() override {}
  void set_focus_exit_handler(FocusExitHandler) override {}
  bool return_focus() override { return true; }
  void close() override
  {
    if (resources_) { resources_->close(); }
    state_.status = NativeViewStatus::Closed;
    state_.message = "Document preview closed.";
  }
  NativeViewState state() const override { return state_; }
 private:
  std::shared_ptr<ResourceSession> resources_;
  NativeViewState state_;
};
}  // namespace

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle, std::shared_ptr<ResourceSession> resources, std::string &error)
{
  error.clear();
  return std::make_unique<UnsupportedView>(std::move(resources));
}
#ifdef STK_DESKTOP_NATIVE_DOCUMENT_TEST_PROBES
namespace test {
std::shared_ptr<ResourceSession> resource_session(wm::NativeWindowHandle, std::string_view,
                                                std::string &error)
{
  error = "Native media test probes are unsupported on this platform"; return {};
}
bool probe_media(wm::NativeWindowHandle, std::string_view, MediaProbeCallback, std::string &error)
{
  error = "Native media test probes are unsupported on this platform"; return false;
}
}
#endif
}  // namespace stk::document_preview
