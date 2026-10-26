/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/document/resources.hh"
#include "stk/wm/native_window.hh"

#include <functional>

namespace stk::document_preview {

enum class NativeViewStatus { Unsupported, Loading, Ready, Failed, Closed };
enum class NativeFocusExit { Next, Previous };
using FocusExitHandler = std::function<void(NativeFocusExit)>;

struct ViewBounds {
  // Window framebuffer pixels, origin at bottom left. Adapters convert to OS client coordinates.
  int x = 0, y = 0, width = 0, height = 0;
};

struct NativeViewState {
  bool parent_attached = false;
  bool visible = false;
  bool focused = false;
  NativeViewStatus status = NativeViewStatus::Loading;
  std::string message;
  std::string runtime_version;
  uint64_t navigation_generation = 0;
  uint64_t blocked_requests = 0;
};

/** UI-thread-only child view. close() is idempotent and must precede the parent destruction.
 * set_visible(false) must remove the view from focus/hit testing as well as hide its pixels.
 * The owner synchronizes visibility every frame; Region::on_layout alone is insufficient.
 * Escape and text/IME events remain native. No keyboard event is replayed to the host.
 */
class NativeDocumentView {
 public:
  virtual ~NativeDocumentView() = default;
  /** Explicitly select the top-level document. Links may only change its fragment; other
   * admitted assets remain subresources until the host explicitly navigates to them.
   */
  virtual bool navigate(std::string_view asset_path, std::string &error) = 0;
  virtual void set_bounds(ViewBounds bounds) = 0;
  virtual void set_visible(bool visible) = 0;
  /** Explicit focus only while the parent is active; never activate a background window. */
  virtual void focus() = 0;
  /** Called after native Tab traversal leaves the page and OS focus has been returned.
   * The owner must recheck its lifetime/scope before choosing a host UI focus target.
   * Hiding, closing and explicit return_focus() never invoke this handler.
   */
  virtual void set_focus_exit_handler(FocusExitHandler handler) = 0;
  /** Relinquish only this view's focus, without stealing focus from another view/modal.
   * True means this view no longer owns focus. Failure closes its resources and view.
   */
  virtual bool return_focus() = 0;
  virtual void close() = 0;
  virtual NativeViewState state() const = 0;
};

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle parent, std::shared_ptr<ResourceSession> resources, std::string &error);

}  // namespace stk::document_preview
