/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_graph_view.hh"

#include <map>
#include <string>
#include <utility>
#include <vector>

namespace stk::app {

/** Localized words a workflow canvas shows; the caller takes them from the UI catalog. */
struct WorkflowViewText {
  /** Step kind ("table", "files", "simulation", "analysis") -> its display name. */
  std::map<std::string, std::string> kinds;
  /** Names of the execution-order sockets; they contain characters no data port name can. */
  std::string after = "(after)", done = "(done)";
  /** A snapshot step's name; "{count}" is replaced by its file count. */
  std::string files = "{count} files";
};

/** Present an stk.workflow/1 document on the analysis graph canvas, using the step summaries of a
 * project.workflows.validate reply for that same document (one per step, in document order).
 *
 * Each step becomes a node titled "<kind> · <label or referenced name>" with the typed ports the
 * reply resolved; a step whose reference did not resolve keeps only the ports its links name and
 * shows as unknown. `after` dependencies become an order link from the earlier step's done socket
 * to the later step's after socket, so layout and cycle marks include them. ui.positions place
 * steps like graph nodes. Steps named by `flagged` (validation issues) are marked as problems.
 * Pure presentation: throws invalid_argument when the reply does not describe the document. */
AnalysisGraphView workflow_graph_view(const io::Json &document, const io::Json &validation,
                                      const WorkflowViewText &text);

/** A (document, its validation reply) pair whose step summaries can stand in for another document's. */
using WorkflowKnownSummaries = std::pair<const io::Json *, const io::Json *>;

/** A stand-in validation reply for an unsaved candidate until its own check arrives: each step keeps
 * the summary of the first known document (in order, e.g. the last checked candidate, then the saved
 * workflow) that has a step with the same id, kind and ref; other steps get empty summaries (shown
 * as unresolved). No issues. */
io::Json workflow_provisional_validation(const io::Json &document, const std::vector<WorkflowKnownSummaries> &known);

}  // namespace stk::app
