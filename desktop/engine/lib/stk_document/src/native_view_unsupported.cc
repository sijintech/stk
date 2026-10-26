/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/document/native_view.hh"

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
}  // namespace stk::document_preview
