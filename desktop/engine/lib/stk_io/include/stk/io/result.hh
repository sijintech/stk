/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* stk.graph-result/1 (docs/specs/stk-graph-v1.md §9) and stk.series/1 (§6). */

#include "stk/io/json.hh"

#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace stk::io {

inline constexpr std::string_view kResultSchema = "stk.graph-result/1";
inline constexpr std::string_view kSeriesSchema = "stk.series/1";

struct GraphIssueRecord {
  std::string code, message, path, node, hint;
  std::string severity; /* "error" | "warning" */
  Json details;
  std::vector<std::string> skipped;
};

struct ResultOutput {
  std::string name;
  std::string type; /* payload, image, table, value, plot, file, dataset */
  Json raw;

  /** payload: the stk.payload/2 manifest (nullptr otherwise). */
  const Json *manifest() const;
  /** image/plot/file/large table or value: the blob sha256 ("" when inline). */
  std::string blob() const;
  std::string media_type() const;
  /** Every blob this output references (blob, data_blob, payload buffers). */
  std::vector<std::string> blobs() const;
};

struct ParameterChoices {
  Json value;
  Json choices; /* null when the evaluator reported none */
};

struct GraphResult {
  std::string schema, graph_sha256, graph_hash, profile;
  std::vector<ResultOutput> outputs;
  std::map<std::string, ParameterChoices> parameters;
  Json keys;
  std::vector<std::string> evaluated; /* nodes evaluated (not served from a cache) in this request */
  std::map<std::string, double> timings;
  int64_t cache_hits = 0, cache_misses = 0;
  std::vector<GraphIssueRecord> warnings, errors;
  Json raw;

  static GraphResult from_json(const Json &document);
  const ResultOutput *output(std::string_view name) const;
  bool was_evaluated(std::string_view node) const;
  /** True when any of `nodes` was evaluated (e.g. data-stage nodes after a client-stage change). */
  bool evaluated_any(const std::vector<std::string> &nodes) const;
  /** Union of every output's blobs (for prefetching into the blob cache). */
  std::vector<std::string> blobs() const;
};

struct SeriesFrame {
  Json step;
  std::map<std::string, std::string> outputs;
};

struct Series {
  std::string parameter;
  std::vector<SeriesFrame> frames;

  static Series from_json(const Json &document);
  Json to_json() const;
};

}  // namespace stk::io
