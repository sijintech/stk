/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/app/analysis_document.hh"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace stk::app {

/** Detached editor-local edits to one saved analysis: submitted parameters, requested outputs and
 * the graph itself (links, list inputs, nodes, node params, positions and exposed outputs). No I/O,
 * evaluation, implicit defaults, rebasing or live-project observation occurs here. Call current()
 * against the live opening handle/revision before editing or saving. pin() accepts an already-read
 * document and checks its shape and storage bounds.
 *
 * Graph edits work on one candidate copy of the saved graph, made at the first edit; every key an
 * edit does not touch keeps its exact JSON, and an edit that returns the graph to the saved one
 * drops the copy. Edits address nodes by id and refuse ids that occur more than once. Removing a
 * node also removes links from it (single links and list entries), the graph outputs that name it,
 * those outputs from the requested list, and its position; graph parameters and other nodes'
 * `$param` references are kept (they are declared independently; validation reports problems).
 * Saving does not validate graphs (saved analyses are drafts): the editor asks graph.validate for
 * every candidate with evaluative graph edits, and preparing a run checks the graph again. */
class AnalysisParameterDraft {
 public:
  static constexpr size_t max_overrides = AnalysisDocumentLimits::max_overrides;
  static constexpr size_t max_outputs = 256;
  static constexpr size_t max_parameters_bytes = AnalysisDocumentLimits::max_parameters_bytes;
  static constexpr size_t max_graph_bytes = AnalysisDocumentLimits::max_graph_bytes;
  static constexpr size_t max_document_bytes = AnalysisDocumentLimits::max_document_bytes;
  // Typed editing text may exceed canonical parameter bytes (for example many -0.0 values).
  static constexpr size_t max_text_bytes = max_document_bytes;
  static constexpr size_t max_depth = AnalysisDocumentLimits::max_depth;

  enum class TextMode { Json, LiteralString };
  struct EditResult {
    bool accepted = false;
    std::string error;
    /** add_node: the id given to the new node. */
    std::string id;
  };
  /** One difference between the saved and the candidate graph, for listing pending edits.
   * kind: node_added, node_removed, input (one input port's raw value), param, position,
   * output_added, output_removed or output_changed. Absent values are nullopt. */
  struct GraphChange {
    std::string kind, node, key;
    std::optional<io::Json> before, after;
  };
  static constexpr size_t max_nodes = 200;

  /** Explicit baseline replacement. Invalid identity, shape or bounds throws invalid_argument
   * before changing the existing draft. Re-pinning the same baseline also fences old callbacks. */
  void pin(std::string handle, std::string analysis_id, int64_t revision,
           std::string name, const io::Json &document);
  void reset();
  bool pinned() const { return !handle_.empty(); }
  bool current(const std::string &handle, int64_t revision) const;
  const std::string &handle() const { return handle_; }
  const std::string &analysis_id() const { return analysis_id_; }
  int64_t revision() const { return revision_; }
  const std::string &name() const { return name_; }
  const io::Json &baseline_document() const { return baseline_; }

  /** Generation changes only on pin/reset; version additionally changes on an actual edit.
   * A text editor may submit multiple edits against the same generation before being rebuilt. */
  uint64_t generation() const { return generation_; }
  uint64_t version() const { return version_; }
  bool dirty() const { return !edits_.empty() || outputs_override_.has_value() || graph_.has_value(); }

  bool has_override(const std::string &name) const;
  /** Disengaged means no override; an engaged JSON null is an explicit submitted null. */
  std::optional<io::Json> override_value(const std::string &name) const;
  /** Detached copies. An unpinned draft returns an empty parameters object/null document. */
  io::Json parameters() const;
  /** Detached ordered array. An unpinned draft returns []; empty never means all outputs. */
  io::Json outputs() const;
  bool output_selected(const std::string &name) const;
  io::Json candidate_document() const;

  /** Valid no-ops are accepted without changing version. Rejected edits preserve all state.
   * Keys are exact UTF-8 strings, including empty/unknown keys admitted by existing storage. */
  EditResult set(const std::string &name, const io::Json &value, uint64_t expected_generation);
  /** JSON mode rejects duplicate keys, trailing data, nonfinite/overflowed numbers and invalid
   * UTF-8. LiteralString stores exact text, so empty text and text "null" remain strings. */
  EditResult set_text(const std::string &name, std::string_view text, TextMode mode,
                      uint64_t expected_generation);
  EditResult remove(const std::string &name, uint64_t expected_generation);
  /** Exact ordered replacement of 0..256 distinct declared output names. No parameter changes.
   * Toggle-on appends; toggle-off removes only that name. Unknown names always fail, even off. */
  EditResult set_outputs(const io::Json &outputs, uint64_t expected_generation);
  EditResult set_output(const std::string &name, bool selected, uint64_t expected_generation);
  /** The candidate graph (the saved graph while it has no edits); a detached reference. */
  const io::Json &graph() const;
  /** Whether the graph differs from the saved one at all, and ignoring `ui` (positions), which
   * never affects evaluation: only evaluative edits need graph validation before saving. */
  bool graph_edited() const { return graph_.has_value(); }
  bool evaluative_graph_edits() const;
  /** Differences in document order (nodes by id; duplicated ids are skipped). */
  std::vector<GraphChange> graph_changes() const;
  /** Single-input link differences of nodes present in both graphs, keyed by (node id, input port):
   * the candidate source "node.port", or nullopt when the input is absent (disconnected). */
  using LinkKey = std::pair<std::string, std::string>;
  std::map<LinkKey, std::optional<std::string>> link_edits() const;
  bool has_link_edits() const { return !link_edits().empty(); }
  /** Structural editability without a catalog: the node id occurs exactly once and its input is
   * absent or exactly {"from": "node.port"}. Lists (multi inputs), aliases and unknown keys stay
   * read-only so untouched fields keep their exact JSON. Catalog rules belong to the caller. */
  bool link_editable(const std::string &node, const std::string &port) const;
  /** The candidate source of an input ("node.port"), or nullopt when it has no single link. */
  std::optional<std::string> link(const std::string &node, const std::string &port) const;
  std::optional<std::string> baseline_link(const std::string &node, const std::string &port) const;
  /** Replace (source engaged) or remove (nullopt) one editable input link. The source node must
   * exist once and differ from the target; port compatibility and cycles are left to graph
   * validation. Setting the baseline value again drops the edit. No parameters/outputs change. */
  EditResult set_link(const std::string &node, const std::string &port,
                      const std::optional<std::string> &source, uint64_t expected_generation);
  /** List inputs (multi ports): absent, one {"from"} object or a list of exactly {"from"} objects.
   * Aliased or extended entries stay read-only. The caller decides which ports are multi. */
  bool links_editable(const std::string &node, const std::string &port) const;
  std::vector<std::string> links(const std::string &node, const std::string &port) const;
  /** Replace the ordered sources of a list input; an empty list removes the input key. */
  EditResult set_links(const std::string &node, const std::string &port, const std::vector<std::string> &sources,
                       uint64_t expected_generation);
  /** Append a node of `type` (a catalog id such as "stk.filter.contour@1") with no params (catalog
   * defaults apply) at an optional logical position. Its id derives from the type name and never
   * collides: contour, contour_2, ... The result's `id` names it. */
  EditResult add_node(const std::string &type, std::optional<std::pair<double, double>> position,
                      uint64_t expected_generation);
  EditResult remove_node(const std::string &node, uint64_t expected_generation);
  /** A node param's raw candidate value (nullopt when absent, so the catalog default applies). */
  std::optional<io::Json> node_param(const std::string &node, const std::string &name) const;
  /** Set (engaged) or remove (nullopt) one node param; `$param` references are ordinary values. */
  EditResult set_node_param(const std::string &node, const std::string &name, const std::optional<io::Json> &value,
                            uint64_t expected_generation);
  /** Write ui.positions for unique nodes (finite, |value| <= 1e6, rounded to whole units). */
  EditResult move_nodes(const std::map<std::string, std::pair<double, double>> &positions, uint64_t expected_generation);
  /** Expose (engaged "node.port") or withdraw (nullopt) a graph output; withdrawing also removes
   * the name from the requested outputs. */
  EditResult set_graph_output(const std::string &name, const std::optional<std::string> &port,
                              uint64_t expected_generation);

  /** Discard accepted parameter, output and link edits; unaccepted text belongs to the caller. */
  bool revert(uint64_t expected_generation);

  /** Current-state observation only, never a transaction receipt or automatic adoption.
   * Typed equality distinguishes integer/float and signed zero, ignoring object key order. */
  bool matches(const std::string &analysis_id, const std::string &name,
               const io::Json &document) const;

 private:
  bool accepts(uint64_t generation) const;
  io::Json document_with(const io::Json &parameters) const;
  /** Applies `change` to copies of the candidate graph and requested outputs, checks bounds and
   * shape, and commits only an actual difference (dropping copies equal to the saved ones). */
  EditResult edit_graph(uint64_t generation, const std::function<std::string(io::Json &graph, io::Json &outputs)> &change);
  std::string handle_, analysis_id_, name_;
  int64_t revision_ = -1;
  uint64_t generation_ = 0, version_ = 0;
  io::Json baseline_;
  // Disengaged optional removes a key; engaged JSON null is an explicit override.
  std::map<std::string, std::optional<io::Json>> edits_;
  std::optional<io::Json> outputs_override_;
  std::optional<io::Json> graph_;
};

/** Everything a graph validation reply about a candidate is bound to. A reply applies only while
 * every field still matches: the project opening, the analysis and the revision it was read at,
 * the exact draft content (generation and version) and the bridge process that checked it. */
struct AnalysisCandidateKey {
  std::string handle, analysis_id, session;
  int64_t revision = -1;
  uint64_t generation = 0, version = 0;
  bool operator==(const AnalysisCandidateKey &) const = default;
};

/** The latest explicit graph.validate of a saved-analysis candidate. Pure state: the caller sends
 * the request; replies for an older ticket are ignored, and a result only counts for its key. */
class AnalysisCandidateValidation {
 public:
  /** Starts a check, dropping any earlier result or pending ticket. */
  uint64_t begin(AnalysisCandidateKey key);
  /** Applies {ok: bool, issues: [...]} for the latest ticket; false when stale or malformed. */
  bool finish(uint64_t ticket, const io::Json &response);
  bool fail(uint64_t ticket, std::string error);
  void reset();
  bool pending() const { return pending_; }
  /** The response for exactly this key, else null (no check, another key, or failure). */
  const io::Json *result(const AnalysisCandidateKey &key) const;
  /** Whether this exact candidate was checked and reported ok. */
  bool passed(const AnalysisCandidateKey &key) const;
  /** The failure of the latest check for this key, else empty. */
  std::string error(const AnalysisCandidateKey &key) const;

 private:
  AnalysisCandidateKey key_;
  uint64_t ticket_ = 0;
  bool pending_ = false;
  io::Json response_;
  std::string error_;
};

}  // namespace stk::app
