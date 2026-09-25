/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/result.hh"

#include "stk/core/sha256.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <set>

namespace stk::io {

namespace {

const Json *get(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

std::string string_or(const Json &object, std::string_view key)
{
  const Json *value = get(object, key);
  return value && value->is_string() ? value->get<std::string>() : std::string();
}

GraphIssueRecord issue_from_json(const Json &item)
{
  GraphIssueRecord issue;
  issue.code = string_or(item, "code");
  issue.message = string_or(item, "message");
  issue.path = string_or(item, "path");
  issue.node = string_or(item, "node");
  issue.hint = string_or(item, "hint");
  issue.severity = string_or(item, "severity");
  issue.details = item.value("details", Json());
  if (const Json *skipped = get(item, "skipped"); skipped && skipped->is_array()) {
    for (const Json &s : *skipped) {
      if (s.is_string()) {
        issue.skipped.push_back(s.get<std::string>());
      }
    }
  }
  return issue;
}

std::vector<GraphIssueRecord> issues(const Json *list)
{
  std::vector<GraphIssueRecord> out;
  if (list && list->is_array()) {
    for (const Json &item : *list) {
      if (item.is_object()) {
        out.push_back(issue_from_json(item));
      }
    }
  }
  return out;
}

}  // namespace

const Json *ResultOutput::manifest() const
{
  if (type != "payload") {
    return nullptr;
  }
  const Json *m = get(raw, "manifest");
  return m && m->is_object() ? m : nullptr;
}

std::string ResultOutput::blob() const
{
  return string_or(raw, "blob");
}

std::string ResultOutput::media_type() const
{
  return string_or(raw, "media_type");
}

std::vector<std::string> ResultOutput::blobs() const
{
  std::vector<std::string> out;
  for (const char *key : {"blob", "data_blob"}) {
    const std::string sha = string_or(raw, key);
    if (core::is_sha256_hex(sha)) {
      out.push_back(sha);
    }
  }
  if (const Json *m = manifest()) {
    if (const Json *buffers = get(*m, "buffers"); buffers && buffers->is_array()) {
      for (const Json &buffer : *buffers) {
        const std::string sha = string_or(buffer, "sha256");
        if (core::is_sha256_hex(sha)) {
          out.push_back(sha);
        }
      }
    }
  }
  return out;
}

GraphResult GraphResult::from_json(const Json &document)
{
  if (!document.is_object()) {
    throw GraphModelError("a graph result must be a JSON object");
  }
  GraphResult result;
  result.raw = document;
  result.schema = string_or(document, "schema");
  if (result.schema != kResultSchema) {
    throw GraphModelError("schema must be 'stk.graph-result/1'", "/schema");
  }
  result.graph_sha256 = string_or(document, "graph_sha256");
  result.graph_hash = string_or(document, "graph_hash");
  result.profile = string_or(document, "profile");
  if (const Json *outputs = get(document, "outputs"); outputs && outputs->is_object()) {
    for (auto it = outputs->begin(); it != outputs->end(); ++it) {
      result.outputs.push_back({it.key(), string_or(it.value(), "type"), it.value()});
    }
  }
  if (const Json *parameters = get(document, "parameters"); parameters && parameters->is_object()) {
    for (auto it = parameters->begin(); it != parameters->end(); ++it) {
      result.parameters[it.key()] = {it.value().value("value", Json()), it.value().value("choices", Json())};
    }
  }
  result.keys = document.value("keys", Json::object());
  if (const Json *evaluated = get(document, "evaluated"); evaluated && evaluated->is_array()) {
    for (const Json &node : *evaluated) {
      if (node.is_string()) {
        result.evaluated.push_back(node.get<std::string>());
      }
    }
  }
  if (const Json *timings = get(document, "timings"); timings && timings->is_object()) {
    for (auto it = timings->begin(); it != timings->end(); ++it) {
      if (it.value().is_number()) {
        result.timings[it.key()] = it.value().get<double>();
      }
    }
  }
  if (const Json *cache = get(document, "cache"); cache && cache->is_object()) {
    result.cache_hits = get_int(*cache, "hits", 0);
    result.cache_misses = get_int(*cache, "misses", 0);
  }
  result.warnings = issues(get(document, "warnings"));
  result.errors = issues(get(document, "errors"));
  return result;
}

const ResultOutput *GraphResult::output(std::string_view name) const
{
  for (const ResultOutput &output : outputs) {
    if (output.name == name) {
      return &output;
    }
  }
  return nullptr;
}

bool GraphResult::was_evaluated(std::string_view node) const
{
  return std::find(evaluated.begin(), evaluated.end(), node) != evaluated.end();
}

bool GraphResult::evaluated_any(const std::vector<std::string> &nodes) const
{
  return std::any_of(nodes.begin(), nodes.end(), [&](const std::string &n) { return was_evaluated(n); });
}

std::vector<std::string> GraphResult::blobs() const
{
  std::vector<std::string> out;
  std::set<std::string> seen;
  for (const ResultOutput &output : outputs) {
    for (std::string &sha : output.blobs()) {
      if (seen.insert(sha).second) {
        out.push_back(std::move(sha));
      }
    }
  }
  return out;
}

Series Series::from_json(const Json &document)
{
  if (!document.is_object() || string_or(document, "schema") != kSeriesSchema) {
    throw GraphModelError("schema must be 'stk.series/1'", "/schema");
  }
  Series series;
  series.parameter = string_or(document, "parameter");
  if (const Json *frames = get(document, "frames"); frames && frames->is_array()) {
    for (const Json &frame : *frames) {
      SeriesFrame f;
      f.step = frame.value("step", Json());
      if (const Json *outputs = get(frame, "outputs"); outputs && outputs->is_object()) {
        for (auto it = outputs->begin(); it != outputs->end(); ++it) {
          if (it.value().is_string()) {
            f.outputs[it.key()] = it.value().get<std::string>();
          }
        }
      }
      series.frames.push_back(std::move(f));
    }
  }
  return series;
}

Json Series::to_json() const
{
  Json frames_json = Json::array();
  for (const SeriesFrame &frame : frames) {
    Json outputs_json = Json::object();
    for (const auto &[name, file] : frame.outputs) {
      outputs_json[name] = file;
    }
    frames_json.push_back({{"step", frame.step}, {"outputs", outputs_json}});
  }
  return {{"schema", std::string(kSeriesSchema)}, {"parameter", parameter}, {"frames", frames_json}};
}

}  // namespace stk::io
