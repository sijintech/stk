/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "window_evidence.hh"
namespace stk::document_preview {
namespace {
class Unsupported final : public WindowEvidenceCapture {
  std::optional<WindowEvidence> poll() override
  {
    return WindowEvidence{{}, "unsupported", "OS native-window evidence is unsupported on this platform"};
  }
};
}
std::string native_evidence_environment_error()
{
  return "Native window evidence is unsupported on this platform";
}
std::unique_ptr<WindowEvidenceCapture> capture_window_evidence(wm::NativeWindowHandle)
{
  return std::make_unique<Unsupported>();
}
}  // namespace stk::document_preview
