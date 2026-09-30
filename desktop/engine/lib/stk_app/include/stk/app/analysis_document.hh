/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"

#include <cstddef>

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

}  // namespace stk::app
