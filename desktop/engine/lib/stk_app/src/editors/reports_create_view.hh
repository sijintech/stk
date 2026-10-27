/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "stk/app/editor.hh"
#include "stk/io/json.hh"
#include <optional>

namespace stk::app {
/** Editor-local report creation. Metadata is fetched only by explicit actions; a restored
 * draft is never a reviewed snapshot. No document bytes, handles or callbacks are persisted. */
class ReportsCreateView {
 public:
  struct Created { std::string project_id, report_id, source_sha256; };
  enum class Mode { FileReport, GenerationInputs };
  struct ReviewedInput {
    std::string project_id;
    int64_t revision = -1;
    io::Json sources, assets, snapshot_id, snapshot_sha256;
  };
  explicit ReportsCreateView(Mode mode = Mode::FileReport);
  // No RPC. Returns metadata only after explicit review at this current scope/revision.
  std::optional<ReviewedInput> reviewed_input() const;
  static bool valid_input_workspace_state(const nlohmann::json &state);
  ~ReportsCreateView();
  ReportsCreateView(const ReportsCreateView &) = delete;
  ReportsCreateView &operator=(const ReportsCreateView &) = delete;
  bool dirty() const;
  uint64_t version() const;
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
