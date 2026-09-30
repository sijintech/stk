/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/graph.hh"

#include <cstddef>
#include <string>
#include <vector>

namespace stk::io { struct Catalog; }

namespace stk::app {

struct AnalysisGraphPoint {
  double x = 0, y = 0;
  bool operator==(const AnalysisGraphPoint &) const = default;
};
struct AnalysisGraphRect {
  double x = 0, y = 0, width = 0, height = 0;
  bool operator==(const AnalysisGraphRect &) const = default;
};

struct AnalysisGraphPort {
  std::string name, type_text;
  bool required = false, multi = false, declared = false;
  AnalysisGraphPoint point;
};

struct AnalysisGraphReference {
  std::string parameter, path;
  /** The graph declaration's default, never a caller override or evaluated value. */
  bool has_default = false;
  std::string default_text;
};

struct AnalysisGraphParameter {
  std::string name, value_text, stage, unit;
  /** explicit, default (node catalog default), or missing; explicit null is not missing. */
  std::string origin;
  bool declared = false, required = false;
  std::vector<AnalysisGraphReference> references;
  /** False when bounded reference discovery did not inspect the whole value. */
  bool references_complete = true;
};

struct AnalysisGraphNode {
  std::string id, type, label, title_en, title_zh, stage;
  bool known_type = false, cyclic = false, ambiguous_id = false, supplied_position = false;
  AnalysisGraphRect rect;
  std::vector<AnalysisGraphPort> inputs, outputs;
  std::vector<AnalysisGraphParameter> parameters;
  size_t omitted_inputs = 0, omitted_outputs = 0, omitted_parameters = 0;
};

struct AnalysisGraphEdge {
  std::string source_node, source_port, target_node, target_port, alias;
  /** Indices into nodes and each node's corresponding ports; -1 means unresolved/omitted. */
  int source = -1, target = -1, output = -1, input = -1;
  size_t link_index = 0;
  AnalysisGraphPoint from, to;
  /** Empty, unknown_type, missing_node, ambiguous_node, missing_port, or display_limit.
   * Empty means both endpoints were found; it does not assert port-type compatibility. */
  std::string diagnostic;
};

struct AnalysisGraphOutput {
  std::string name, node, port, diagnostic;
  int node_index = -1, port_index = -1;
};

struct AnalysisGraphIssue {
  std::string code, node, path, message;
};

struct AnalysisGraphView {
  static constexpr size_t max_nodes = 200, max_ports = 128, max_parameters = 128;
  static constexpr size_t max_edges = 4096, max_outputs = 256, max_issues = 256;
  static constexpr size_t summary_bytes = 160;
  /** Logical canvas coordinates; the renderer applies its own pan, zoom and DPI. */
  static constexpr double node_width = 180, header_height = 44, port_spacing = 18;

  std::string id, name;
  /** Document order is retained, including unknown types and duplicate node IDs. */
  std::vector<AnalysisGraphNode> nodes;
  std::vector<AnalysisGraphEdge> edges;
  std::vector<AnalysisGraphOutput> outputs;
  std::vector<AnalysisGraphIssue> issues;
  AnalysisGraphRect bounds;
  size_t omitted_edges = 0, omitted_outputs = 0, omitted_issues = 0;
};

/** Pure presentation of an already parsed stk.graph/1 document. Never validates semantic port
 * compatibility, evaluates, saves, reads files, imports plugins, or copies raw JSON values.
 * The catalog may be absent. Unknown types retain referenced ports and their parameter summaries.
 * Duplicate node IDs never resolve a link to an arbitrary node.
 *
 * Honors graph.ui.positions[node_id] = [x,y] when both coordinates are finite and |value| <= 1e6.
 * Other nodes use deterministic layers of the SCC-condensed dependency graph; cycle members are
 * marked and descendants remain on later layers. Port/link order follows the catalog/document.
 * Display caps report omitted counts/issues. References inspect at most 256 values, 64 levels and
 * 32 references per parameter. Labels/summaries are at most 160 UTF-8 bytes. Exact graph identities
 * are retained; identities over 1024 bytes or more than 200 nodes throw invalid_argument.
 * The authoritative original graph, source identity, effective overrides, results and freshness
 * remain the caller's responsibility. Graph validation issues should be shown separately.
 */
AnalysisGraphView analysis_graph_view(const io::Graph &graph, const io::Catalog *catalog = nullptr);

}  // namespace stk::app
