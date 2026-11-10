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
// Optional run-scoped source. On Windows it leases only the capture target item for the
// exact original window lifetime. Every capture still creates its own pool/session/frames.
// Use and destroy the source and all its captures on the owning UI thread, before the
// window is destroyed. Existing one-shot callers retain their independent startup path.
class WindowEvidenceCaptureSource {
 public:
  virtual ~WindowEvidenceCaptureSource() = default;
  virtual std::unique_ptr<WindowEvidenceCapture> capture(wm::NativeWindowHandle parent) = 0;
};
#ifdef _WIN32
std::unique_ptr<WindowEvidenceCaptureSource> window_evidence_capture_source(wm::NativeWindowHandle parent);
#endif
}  // namespace stk::document_preview
