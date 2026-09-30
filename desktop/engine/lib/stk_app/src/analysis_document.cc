/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_document.hh"

#include "stk/core/utf8.hh"

#include <cmath>
#include <set>
#include <stdexcept>
#include <vector>

namespace stk::app {
namespace {
using io::Json;
void require(bool condition, const char *message)
{
  if (!condition) { throw std::invalid_argument(message); }
}
}  // namespace

/** Match the storage clone's raw budget/depth before copying or recursively serializing JSON.
 * Object keys count as values at depth+1. The raw budget deliberately precedes canonical bytes. */
void check_analysis_json_bounds(const Json &value)
{
  constexpr size_t byte_limit = AnalysisDocumentLimits::max_document_bytes;
  struct Item { const Json *value; size_t depth; };
  std::vector<Item> pending{{&value, 0}};
  size_t scheduled = 1, budget = 0;
  auto add_bytes = [&](size_t count) {
    require(count <= byte_limit - budget, "Analysis JSON exceeds its byte limit");
    budget += count;
  };
  auto string = [&](const std::string &text) {
    require(text.size() <= byte_limit && core::utf8::is_valid(text), "Analysis JSON strings must be bounded valid UTF-8");
    add_bytes(text.size()); add_bytes(2);
  };
  while (!pending.empty()) {
    const auto [current, depth] = pending.back(); pending.pop_back();
    require(depth <= AnalysisDocumentLimits::max_depth, "Analysis JSON exceeds its depth limit");
    if (current->is_object() || current->is_array()) {
      add_bytes(2);
      const size_t multiplier = current->is_object() ? 2 : 1;
      require(current->size() <= (AnalysisDocumentLimits::max_document_bytes - scheduled) / multiplier,
              "Analysis JSON exceeds its item limit");
      scheduled += current->size() * multiplier;
      for (auto it = current->begin(); it != current->end(); ++it) {
        if (current->is_object()) {
          require(depth + 1 <= AnalysisDocumentLimits::max_depth, "Analysis JSON exceeds its depth limit");
          string(it.key());
        }
        pending.push_back({&it.value(), depth + 1});
      }
    }
    else if (current->is_string()) { string(current->get_ref<const std::string &>()); }
    else if (current->is_number_float()) {
      require(std::isfinite(current->get<double>()), "Analysis JSON numbers must be finite");
      add_bytes(io::python_float_repr(current->get<double>()).size());
    }
    else if (current->is_number_integer()) { add_bytes(io::python_str(*current).size()); }
    else if (current->is_null() || current->is_boolean()) { add_bytes(4); }
    else { throw std::invalid_argument("Analysis values must be plain JSON data"); }
  }
}

void check_analysis_document_bounds(const Json &document)
{
  check_analysis_json_bounds(document);
  require(document.is_object() && document.size() == 4 && document.contains("format") &&
      document.at("format") == "stk.analysis-document/1" && document.contains("graph") &&
      document.contains("parameters") && document.contains("outputs"), "Invalid saved analysis document shape");
  const auto &graph = document.at("graph");
  const auto &parameters = document.at("parameters");
  const auto &outputs = document.at("outputs");
  require(graph.is_object() && io::canonical_json(graph).size() <= AnalysisDocumentLimits::max_graph_bytes,
          "Analysis graph exceeds its 256 KiB limit or is not an object");
  require(parameters.is_object() && parameters.size() <= AnalysisDocumentLimits::max_overrides &&
      io::canonical_json(parameters).size() <= AnalysisDocumentLimits::max_parameters_bytes,
      "Analysis parameters require at most 64 overrides and 64 KiB");
  require(outputs.is_array() && outputs.size() <= 256 && graph.contains("outputs") &&
      graph.at("outputs").is_object(), "Analysis outputs must name declared graph outputs");
  std::set<std::string> selected;
  for (const auto &output : outputs) {
    require(output.is_string(), "Analysis outputs must be strings");
    const auto &name = output.get_ref<const std::string &>();
    require(graph.at("outputs").contains(name) && selected.insert(name).second,
            "Analysis outputs must be distinct declared graph outputs");
  }
  require(graph.contains("nodes") && graph.at("nodes").is_array() &&
      !graph.at("nodes").empty() && graph.at("nodes").size() <= 200,
      "Analysis graph requires between 1 and 200 nodes");
  if (graph.contains("parameters")) {
    require(graph.at("parameters").is_array() && graph.at("parameters").size() <= 64,
            "Analysis graph allows at most 64 declared parameters");
  }
  for (const auto &node : graph.at("nodes")) {
    require(node.is_object(), "Analysis graph nodes must be objects");
    if (node.contains("params")) {
      require(node.at("params").is_object() && io::canonical_json(node.at("params")).size() <= AnalysisDocumentLimits::max_parameters_bytes,
              "Analysis node parameters require an object of at most 64 KiB");
    }
  }
  require(io::canonical_json(document).size() <= AnalysisDocumentLimits::max_document_bytes,
          "Analysis document exceeds its 384 KiB limit");
}


}  // namespace stk::app
