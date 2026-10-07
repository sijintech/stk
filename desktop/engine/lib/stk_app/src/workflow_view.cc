/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/workflow_view.hh"

#include "stk/io/catalog.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>

namespace stk::app {
using io::Json;
namespace {

const Json &member(const Json &object, const char *key)
{
  static const Json null;
  if (!object.is_object()) { return null; }
  const auto found = object.find(key);
  return found == object.end() ? null : *found;
}

std::string kind_stage(const std::string &kind)
{
  if (kind == "table") { return "source"; }
  if (kind == "files") { return "data"; }
  if (kind == "simulation") { return "representation"; }
  if (kind == "analysis") { return "analysis"; }
  return {};
}

std::string replaced(std::string text, const std::string &key, const std::string &value)
{
  if (const auto at = text.find(key); at != std::string::npos) { text.replace(at, key.size(), value); }
  return text;
}

std::vector<io::PortSpec> ports(const Json &list)
{
  std::vector<io::PortSpec> result;
  if (!list.is_array()) { return result; }
  for (const auto &port : list) {
    io::PortSpec spec;
    spec.name = io::get_string(port, "name");
    spec.types = {io::get_string(port, "type")};
    spec.required = io::get_bool(port, "required", false);
    if (!spec.name.empty()) { result.push_back(std::move(spec)); }
  }
  return result;
}

}  // namespace

AnalysisGraphView workflow_graph_view(const Json &document, const Json &validation, const WorkflowViewText &text)
{
  const auto &steps = member(document, "steps");
  const auto &summaries = member(validation, "steps");
  if (!steps.is_array() || !summaries.is_array() || steps.size() != summaries.size()) {
    throw std::invalid_argument("The validation reply does not describe this workflow");
  }
  std::map<std::string, int> counts;
  std::set<std::string> awaited, flagged;
  for (size_t i = 0; i < steps.size(); ++i) {
    if (io::get_string(summaries[i], "id") != io::get_string(steps[i], "id")) {
      throw std::invalid_argument("The validation reply does not describe this workflow");
    }
    ++counts[io::get_string(steps[i], "id")];
    for (const auto &before : member(steps[i], "after")) {
      if (before.is_string()) { awaited.insert(before.get<std::string>()); }
    }
  }
  for (const auto &issue : member(validation, "issues")) { flagged.insert(io::get_string(issue, "step")); }

  io::Catalog catalog;
  io::Graph graph;
  graph.schema = "stk.graph/1";
  graph.raw = Json::object();
  if (member(document, "ui").is_object()) { graph.raw["ui"] = member(document, "ui"); }
  for (size_t i = 0; i < steps.size(); ++i) {
    const auto &step = steps[i];
    const auto &summary = summaries[i];
    const auto id = io::get_string(step, "id"), kind = io::get_string(step, "kind");
    const auto type = "wf.step." + id + "@1";
    const auto found = text.kinds.find(kind);
    const auto kind_name = found == text.kinds.end() ? kind : found->second;
    std::string name = io::get_string(step, "label");
    if (name.empty()) { name = io::get_string(summary, "name"); }
    if (name.empty() && member(summary, "file_count").is_number_integer()) {
      name = replaced(text.files, "{count}", std::to_string(member(summary, "file_count").get<int64_t>()));
    }
    if (name.empty()) { name = id; }

    const bool resolved = !member(summary, "inputs").empty() || !member(summary, "outputs").empty();
    if (resolved && counts[id] == 1) {
      io::NodeType node_type;
      node_type.id = type;
      node_type.type = "wf.step." + id;
      node_type.version = 1;
      node_type.stage = kind_stage(kind);
      node_type.title_en = node_type.title_zh = kind_name;
      node_type.inputs = ports(member(summary, "inputs"));
      node_type.outputs = ports(member(summary, "outputs"));
      if (member(step, "after").is_array() && !member(step, "after").empty()) {
        io::PortSpec after;
        after.name = text.after; after.types = {"order"}; after.multi = true;
        node_type.inputs.push_back(std::move(after));
      }
      if (awaited.count(id)) {
        io::PortSpec done;
        done.name = text.done; done.types = {"order"};
        node_type.outputs.push_back(std::move(done));
      }
      catalog.nodes.push_back(std::move(node_type));
    }

    io::GraphNode node;
    node.id = id;
    node.type = type;
    node.label = kind_name + " · " + name;
    node.raw = step;
    for (const auto &[port, link] : member(step, "inputs").items()) {
      const auto parsed = io::parse_port_ref(io::get_string(link, "from"));
      if (!parsed) { continue; }
      node.inputs.push_back({port, {{parsed->first, parsed->second, {}}}, false});
    }
    io::GraphInput order{text.after, {}, true};
    for (const auto &before : member(step, "after")) {
      if (before.is_string()) { order.links.push_back({before.get<std::string>(), text.done, {}}); }
    }
    if (!order.links.empty()) { node.inputs.push_back(std::move(order)); }
    graph.nodes.push_back(std::move(node));
  }

  auto view = analysis_graph_view(graph, &catalog);
  // Synthetic types are an implementation detail; the validation reply carries the real issues.
  std::vector<AnalysisGraphIssue> kept;
  for (auto &issue : view.issues) {
    if (issue.code == "display_limit" || issue.code == "invalid_position") { kept.push_back(std::move(issue)); }
  }
  view.issues = std::move(kept);
  for (auto &node : view.nodes) { node.flagged = flagged.count(node.id) > 0; }
  return view;
}

Json workflow_provisional_validation(const Json &document, const std::vector<WorkflowKnownSummaries> &known)
{
  const auto lookup = [&](const Json &step) -> const Json * {
    const auto id = io::get_string(step, "id");
    for (const auto &[source, validation] : known) {
      if (!source || !validation) { continue; }
      const auto &steps = member(*source, "steps");
      const auto &summaries = member(*validation, "steps");
      if (!steps.is_array() || !summaries.is_array() || steps.size() != summaries.size()) { continue; }
      const Json *match = nullptr;
      int count = 0;
      for (size_t i = 0; i < steps.size(); ++i) {
        if (io::get_string(steps[i], "id") != id) { continue; }
        ++count;
        if (member(steps[i], "kind") == member(step, "kind") && member(steps[i], "ref") == member(step, "ref")) { match = &summaries[i]; }
      }
      if (count == 1 && match) { return match; }
    }
    return nullptr;
  };
  Json steps = Json::array();
  for (const auto &step : member(document, "steps")) {
    if (const auto *summary = lookup(step)) { steps.push_back(*summary); continue; }
    steps.push_back({{"id", io::get_string(step, "id")}, {"kind", io::get_string(step, "kind")}, {"name", nullptr},
                     {"content_sha256", nullptr}, {"file_count", nullptr}, {"inputs", Json::array()},
                     {"outputs", Json::array()}, {"parameters", Json::array()}});
  }
  int64_t revision = 0;
  for (const auto &[source, validation] : known) { if (validation) { revision = std::max(revision, io::get_int(*validation, "revision", 0)); } }
  return {{"revision", revision}, {"ok", false}, {"issues", Json::array()}, {"omitted_issues", 0}, {"steps", std::move(steps)}};
}

}  // namespace stk::app
