/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * How project objects are named on screen (docs/design/glossary.md): rows by their position in the
 * table rather than their UUID, formula errors by a localized name rather than their code. The
 * stable ids and codes stay in the model, in searches and under "technical details".
 */
#pragma once

#include "stk/app/app_store.hh"
#include "stk/app/project_state.hh"

#include <string>

namespace stk::app {

/** "#division by zero" for the evaluation error code "division_by_zero" (the code when unknown). */
inline std::string formula_error_label(const AppStore &store, const std::string &code)
{
  return "#" + std::string(store.catalog().tr_or("formula.error." + code, code));
}

/** "Row 3" for a record's 1-based position in `table`, or the start of its UUID when it is not there. */
inline std::string row_label(const AppStore &store, const ProjectTable *table, const std::string &record_id)
{
  if (table) {
    for (size_t i = 0; i < table->records.size(); ++i) {
      if (table->records[i].id == record_id) { return store.catalog().format("project.row", {{"n", std::to_string(i + 1)}}); }
    }
  }
  return record_id.substr(0, 8);
}

}  // namespace stk::app
