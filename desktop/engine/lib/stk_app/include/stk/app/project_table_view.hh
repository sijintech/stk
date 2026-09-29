/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <cstddef>
#include <string>
#include <vector>

namespace stk::app {

struct ProjectTable;

/** View-only query. ASCII letters ignore case; other UTF-8 text matches literally, without regex
 * or locale-dependent folding. Invalid UTF-8 and queries over 256 bytes throw invalid_argument. */
struct ProjectTableQuery {
  std::string text;
  bool errors_only = false;
};

/** Original row indices in original order, matching record UUID, displayed values or error text.
 * Never changes the model or selection. The caller maps all TableSpec callbacks through these
 * indices and invalidates its mapping when either model data or the query changes. */
std::vector<int> project_table_rows(const ProjectTable &table, const ProjectTableQuery &query);

/** Single-line cell summary, at most max_bytes UTF-8 bytes. Details must retain the original value.
 * Strings display without quotes; line/control characters are escaped. Integers stay exact.
 * Stops after the visible prefix; objects/arrays are not serialized in full. Nesting is capped at
 * 64 levels for display, with the same ellipsis used for byte truncation. */
std::string project_value_summary(const io::Json &value, size_t max_bytes = 160);

struct CapturedProjectCell {
  std::string record_id, field_id, field_name, type, unit;
  /** literal, null, unset, evaluated, formula_error, omitted, evaluation_unavailable,
   * missing_record, missing_field or missing_table. These are catalog suffixes, not labels. */
  std::string status, value_text;
  bool incomplete = false;
  /** Source identity, field metadata and original literal/definition/evaluation parts. An absent
   * part stays absent; an included null stays an included null. Nothing is resolved against live data. */
  io::Json details = io::Json::object();
};

struct CapturedProjectTable {
  /** Captured selection order: record_ids first, then field_ids; missing objects keep their IDs. */
  std::vector<CapturedProjectCell> cells;
  /** Nonempty only when the entire captured content was omitted. No fabricated cells are added. */
  std::string omission_reason;
};

/** Read a full format-7 context returned by contexts.get/capture (not a list summary).
 * Uses only captured parts, including saved evaluation observations. Never evaluates a formula,
 * follows a reference, reads the project, or changes any input. Malformed input throws. */
CapturedProjectTable project_context_table(const io::Json &context);

}  // namespace stk::app
