/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_result_inspection.hh"

namespace stk::app {

struct AnalysisTableColumn {
  size_t index = 0;
  std::string name;                // Exact identity, including empty/numeric/Unicode keys.
  bool has_unit = false;           // Missing is distinct from the string "unspecified".
  std::string unit;                // Exact nonempty string when present; never converted.
  std::string label;               // Bounded quoted/escaped display; not an identity.
  bool label_truncated = false;
};
struct AnalysisTablePage {
  size_t row_offset = 0, column_offset = 0, total_rows = 0, total_columns = 0;
  std::vector<size_t> columns;      // Absolute column indices, source order, at most eight.
  std::vector<std::vector<AnalysisJsonDescription>> rows;
  std::optional<size_t> next_row_offset, next_column_offset;
};

/** Read-only grid over a previously verified immutable result. Never reads blobs/files,
 * normalizes scientific values, infers units/dtypes or copies entire column arrays.
 * Original column_names order and equal row lengths are mandatory. Malformed/blob-backed
 * deliveries throw invalid_argument; the original typed property browser stays available. */
class AnalysisTableGrid {
 public:
  static constexpr size_t row_page_size = 64, column_page_size = 8;
  static std::shared_ptr<const AnalysisTableGrid> from_output(
      std::shared_ptr<const AnalysisResultInspection> model, const std::string &output);
  const std::string &output() const { return output_; }
  const std::vector<AnalysisTableColumn> &columns() const { return columns_; }
  size_t row_count() const { return row_count_; }
  const std::shared_ptr<const AnalysisResultInspection> &inspection() const { return inspection_; }
  /** Row/column offsets may equal their totals, producing an empty axis. Limits must be
   * 1..64/1..8. Each page contains bounded descriptions; no repeated cell paths or JSON. */
  AnalysisTablePage page(size_t row_offset = 0, size_t column_offset = 0,
                        size_t row_limit = row_page_size, size_t column_limit = column_page_size) const;
  /** Exact paths are derived only for an explicitly selected cell/name/unit. Missing units
   * and out-of-range coordinates throw. A cell may be scalar, array or object. */
  AnalysisJsonPath cell_path(size_t row, size_t column) const;
  AnalysisJsonPath column_name_path(size_t column) const;
  AnalysisJsonPath unit_path(size_t column) const;
  /** Format only a visible/selected unit, never all unit paths during construction. */
  AnalysisJsonDescription unit_description(size_t column) const;

 private:
  AnalysisTableGrid() = default;
  AnalysisJsonPath column_path(size_t column) const;
  std::shared_ptr<const AnalysisResultInspection> inspection_;
  std::string output_;
  std::vector<AnalysisTableColumn> columns_;
  size_t row_count_ = 0;
};
} // namespace stk::app
