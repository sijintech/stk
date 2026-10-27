/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/editor.hh"
#include <optional>

namespace stk::app {
/** One Reports tab's composer. Restoring this state never reviews sources or sends.
 * The input picker and request controller remain local to this view. */
class ReportsGenerationView {
 public:
  struct Created { std::string project_id, report_id, source_sha256; };
  ReportsGenerationView();
  ~ReportsGenerationView();
  ReportsGenerationView(const ReportsGenerationView &) = delete;
  ReportsGenerationView &operator=(const ReportsGenerationView &) = delete;
  void draw(ui::Layout &, EditorContext &, std::function<bool()> reader_available);
  bool dirty() const;
  std::optional<Created> take_created();
  nlohmann::json save_workspace_state() const;
  static bool valid_workspace_state(const nlohmann::json &);
  bool load_workspace_state(const nlohmann::json &);
 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};
} // namespace stk::app
