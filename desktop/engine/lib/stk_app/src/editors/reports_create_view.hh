/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/editor.hh"
#include <optional>

namespace stk::app {
/** Editor-local report creation. Metadata is fetched only by explicit actions; a restored
 * draft is never a reviewed snapshot. No document bytes, handles or callbacks are persisted. */
class ReportsCreateView {
 public:
  struct Created { std::string project_id, report_id, source_sha256; };
  ReportsCreateView();
  ~ReportsCreateView();
  ReportsCreateView(const ReportsCreateView &) = delete;
  ReportsCreateView &operator=(const ReportsCreateView &) = delete;
  bool dirty() const;
  void draw(ui::Layout &layout, EditorContext &ctx, std::function<bool()> reader_available);
  std::optional<Created> take_created();
  nlohmann::json save_workspace_state() const;
  static bool valid_workspace_state(const nlohmann::json &state);
  bool load_workspace_state(const nlohmann::json &state);
 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace stk::app
