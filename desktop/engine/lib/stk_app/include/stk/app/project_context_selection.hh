/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/project_state.hh"

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace stk::app {

/** Editor-local context selection against one frozen table and opening handle/revision.
 * This is a view draft, not a saved context or shared project selection. It never reads a bridge,
 * edits data, follows references, or updates itself when the live project changes. Callers must
 * check current() before edits and capture; a stale draft remains inspectable until an explicit pin.
 */
class ProjectContextSelection {
 public:
  static constexpr size_t max_rows = 100, max_fields = 64, max_cells = 1000;

  /** Explicitly replace the scope. A valid seed record selects that row and every field only when
   * there are 1..64 fields; otherwise both selections start empty. No prefix is silently selected.
   * Invalid identity or duplicate/empty table object IDs throw invalid_argument without changing
   * the existing draft. Re-pinning even the same scope invalidates old widget generations. */
  void pin(std::string handle, int64_t revision, const ProjectTable &table,
           const std::string &seed_record = {});
  void reset();

  uint64_t generation() const { return generation_; }
  bool current(const std::string &handle, int64_t revision) const;
  const std::string &handle() const { return handle_; }
  int64_t revision() const { return revision_; }
  const ProjectTable &table() const { return table_; }
  /** Checked IDs in the frozen table's original order, independent of click/display order. */
  const std::vector<std::string> &rows() const { return rows_; }
  const std::vector<std::string> &fields() const { return fields_; }
  bool row_checked(const std::string &id) const;
  bool field_checked(const std::string &id) const;

  /** False means stale generation, unknown ID or a per-axis limit; no state then changes.
   * True includes an already-satisfied request. Every actual change increments generation. */
  bool set_row(const std::string &id, bool checked, uint64_t generation);
  bool set_field(const std::string &id, bool checked, uint64_t generation);
  bool all_rows(uint64_t generation);
  bool all_fields(uint64_t generation);
  bool clear_rows(uint64_t generation);
  bool clear_fields(uint64_t generation);

  size_t cell_count() const { return rows_.size() * fields_.size(); }
  /** Selection bounds only; callers must additionally check current() and project readiness.
   * Selecting more than 1000 cells is allowed while editing but cannot be captured. */
  bool valid() const;

 private:
  bool accepts(uint64_t generation) const;
  bool replace(std::vector<std::string> &selection, std::vector<std::string> next);
  bool set(std::vector<std::string> &selection,
           const std::unordered_map<std::string, size_t> &order, size_t limit,
           const std::string &id, bool checked, uint64_t generation);

  std::string handle_;
  int64_t revision_ = -1;
  ProjectTable table_;
  std::unordered_map<std::string, size_t> row_order_, field_order_;
  std::vector<std::string> rows_, fields_;
  uint64_t generation_ = 0;
};

}  // namespace stk::app
