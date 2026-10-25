/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/io/png.hh"
#include "stk/wm/native_window.hh"
#include <memory>
#include <optional>
#include <string>

namespace stk::document_preview {
struct WindowEvidence {
  io::Image image;
  std::string backend, error;
};
// Prototype-only, UI-thread API. Only the given STK window is captured; the exported image
// is its client area. Does not read the desktop, GPU framebuffer or browser-only snapshot.
// Destruction cancels/forgets in-flight delivery; late OS callbacks never access the parent.
class WindowEvidenceCapture {
 public:
  virtual ~WindowEvidenceCapture() = default;
  virtual std::optional<WindowEvidence> poll() = 0;
};
// Probe before GHOST creates a window: its Windows GL failure path otherwise opens a modal
// error dialog. Returns a diagnostic only; success is never native presentation evidence.
std::string native_evidence_environment_error();
std::unique_ptr<WindowEvidenceCapture> capture_window_evidence(wm::NativeWindowHandle parent);
}  // namespace stk::document_preview
