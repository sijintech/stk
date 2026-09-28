/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"
#include <optional>
#include <vector>

namespace stk::app {
struct ProjectTable;

/** One stable-identity object or sparse cell. Missing is distinct from an explicit JSON null. */
struct ProjectDifference {
  std::string kind, table_id, record_id, field_id, label;
  std::optional<io::Json> before, after;
};

/** Transient, immutable review. No execution, file or database effects belong to this model. */
struct ProjectReview {
  std::string project_id;
  int64_t base_revision = -1, proposed_revision = -1;
  io::Json commands;
  std::vector<ProjectDifference> differences, errors;

  static ProjectReview from_preview(const std::string &project_id, int64_t base_revision,
                                    const std::vector<ProjectTable> &before, const io::Json &result);
};
}  // namespace stk::app
