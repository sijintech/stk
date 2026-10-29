/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/project_reports.hh"
#include "stk/document/native_view.hh"
#include "stk/ui/ui.hh"
#include <functional>

namespace stk::app {
class AppStore;
class Editor;
struct EditorContext;

/** Tab-local native document host. Only verified, complete prepared collections are admitted.
 * Scope/reader invalidation closes URLs synchronously; layout only controls visibility.
 * It never reads files, calls the bridge, persists browser state, or changes Viewer state. */
class ReportDocumentHost {
 public:
  using Factory = std::function<std::unique_ptr<document_preview::NativeDocumentView>(
      wm::NativeWindowHandle, std::shared_ptr<document_preview::ResourceSession>, std::string &)>;
  explicit ReportDocumentHost(AppStore &store, Factory factory = {});
  ~ReportDocumentHost();
  ReportDocumentHost(const ReportDocumentHost &) = delete;
  ReportDocumentHost &operator=(const ReportDocumentHost &) = delete;
  /** Must be connected to the owning ProjectReports::on_preview_invalidated. */
  std::function<void()> invalidator() const;
  bool adopt(PreparedReportPreview preview);
  void clear();
  void bind(Editor &owner, EditorContext &ctx);
  void set_viewport(ui::WidgetId viewport, ui::WidgetId previous_anchor, ui::WidgetId next_anchor);
  void set_visible(bool visible);
  void focus();
  void return_focus();
  /** Explicitly pause admitted video. Becoming visible never resumes playback. */
  bool pause_media();
  bool has_media() const;
  document_preview::NativeViewState state() const;
  bool has_content() const;
  /** Borrowed immutable collection identity, also used by lifecycle contract tests. */
  std::shared_ptr<const document_preview::ResourceSession> session() const;
 private:
  struct State;
  std::shared_ptr<State> state_;
};
}  // namespace stk::app
