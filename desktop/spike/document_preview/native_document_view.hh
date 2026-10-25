/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "document_resources.hh"
#include "stk/wm/native_window.hh"

namespace stk::document_preview {

enum class NativeViewStatus { Unsupported, Loading, Ready, Failed, Closed };

struct ViewBounds {
  // Window framebuffer pixels, origin at bottom left. Adapters convert to OS client coordinates.
  int x = 0, y = 0, width = 0, height = 0;
};

struct NativeViewState {
  bool parent_attached = false;
  bool visible = false;
  NativeViewStatus status = NativeViewStatus::Loading;
  std::string message;
  std::string runtime_version;
  uint64_t navigation_generation = 0;
  uint64_t blocked_requests = 0;
};

/** UI-thread-only child view. close() is idempotent and must precede the parent destruction.
 * set_visible(false) must remove the view from focus/hit testing as well as hide its pixels.
 * The owner synchronizes visibility every frame; Region::on_layout alone is insufficient.
 */
class NativeDocumentView {
 public:
  virtual ~NativeDocumentView() = default;
  virtual bool navigate(std::string_view asset_path, std::string &error) = 0;
  virtual void set_bounds(ViewBounds bounds) = 0;
  virtual void set_visible(bool visible) = 0;
  virtual void focus() = 0;
  virtual void close() = 0;
  virtual NativeViewState state() const = 0;
};

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle parent, std::shared_ptr<ResourceSession> resources, std::string &error);

}  // namespace stk::document_preview
