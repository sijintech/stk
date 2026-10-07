/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <cstddef>
#include <string_view>

namespace stk::app {

struct AnalysisDocumentLimits {
  static constexpr size_t max_overrides = 64;
  static constexpr size_t max_parameters_bytes = 64 * 1024;
  static constexpr size_t max_graph_bytes = 256 * 1024;
  static constexpr size_t max_document_bytes = 384 * 1024;
  static constexpr size_t max_depth = 64;
};

/** Check finite plain JSON, UTF-8, depth and raw storage budgets without copying or recursive
 * serialization. Throws invalid_argument. This is a resource guard, not a structural schema. */
void check_analysis_json_bounds(const io::Json &value);

/** Check the saved document shape and storage bounds before copying it. The backend remains
 * authoritative for the complete graph schema, and catalog validation is a separate operation. */
void check_analysis_document_bounds(const io::Json &document);

/** A lowercase canonical UUID (8-4-4-4-12 hexadecimal digits), as project records are named. */
bool canonical_uuid(std::string_view value);
/** Whether valid UTF-8 text has a character other than Python's str.isspace() whitespace
 * (the backend's name.strip() check for saved names). */
bool visible_text(std::string_view text);

}  // namespace stk::app
