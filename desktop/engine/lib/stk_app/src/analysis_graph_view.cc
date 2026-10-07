/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_graph_view.hh"

#include "stk/app/project_table_view.hh"
#include "stk/core/utf8.hh"
#include "stk/io/catalog.hh"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
using View = AnalysisGraphView;

std::string identity(const std::string &value)
{
  if (value.size() > 1024) { throw std::invalid_argument("Graph presentation identity exceeds 1024 bytes"); }
  return value;
}

std::string text(const std::string_view value)
{
  // Avoid copying or escaping a whole long label just to display its first line.
  const auto prefix = core::utf8::truncate_bytes(value, View::summary_bytes + 4);
  std::string result = project_value_summary(Json(std::string(prefix)), View::summary_bytes);
  if (prefix.size() != value.size()) {
    result = std::string(core::utf8::truncate_bytes(result, View::summary_bytes - 3)) + "…";
  }
  return result;
}

std::string port_type(const io::PortSpec &port)
{
  std::string result;
  auto append = [&](const std::vector<std::string> &parts) {
    for (size_t i = 0; i < parts.size() && result.size() <= View::summary_bytes; ++i) {
      if (i) { result += " | "; }
      result += text(parts[i]);
    }
  };
  append(port.types);
  if (!port.value_type.empty()) { result += "<" + text(port.value_type) + ">"; }
  const auto &kinds = port.accepts.empty() ? port.kinds : port.accepts;
  if (!kinds.empty() && result.size() <= View::summary_bytes) {
    result += " (";
    append(kinds);
    result += ")";
  }
  if (result.empty()) { result = "?"; }
  return text(result);
}

struct NodeIndex {
  const io::NodeType *type = nullptr;
  std::map<std::string, int> inputs, outputs;
};

class Builder {
 public:
  Builder(const io::Graph &graph, const io::Catalog *catalog) : graph_(graph), catalog_(catalog) {}

  View build()
  {
    if (graph_.nodes.size() > View::max_nodes) {
      throw std::invalid_argument("Graph presentation supports at most 200 nodes");
    }
    view_.id = identity(graph_.id);
    view_.name = text(graph_.name);
    index_.resize(graph_.nodes.size());
    for (size_t i = 0; i < graph_.nodes.size(); ++i) {
      const auto id = identity(graph_.nodes[i].id);
      const auto [found, inserted] = nodes_.emplace(id, int(i));
      if (!inserted) { found->second = -1; }
    }
    for (size_t i = 0; i < graph_.parameters.size(); ++i) {
      const auto &parameter = graph_.parameters[i];
      const auto [found, inserted] = parameters_.emplace(identity(parameter.name), &parameter);
      if (!inserted) { found->second = nullptr; }
    }
    for (size_t i = 0; i < graph_.nodes.size(); ++i) { node(i); }
    links();
    outputs();
    layout();
    endpoints();
    bounds();
    if (graph_.nodes.empty()) { issue("no_nodes", {}, "/nodes", "The graph has no nodes"); }
    return std::move(view_);
  }

 private:
  void issue(std::string code, std::string node, std::string path, std::string message)
  {
    if (view_.issues.size() == View::max_issues) { ++view_.omitted_issues; return; }
    view_.issues.push_back({std::move(code), std::move(node), std::move(path), text(message)});
  }

  int port(size_t node_index, bool input, const std::string &name, const io::PortSpec *declaration = nullptr)
  {
    auto &index = input ? index_[node_index].inputs : index_[node_index].outputs;
    const auto found = index.find(name);
    if (found != index.end()) { return found->second; }
    auto &node = view_.nodes[node_index];
    auto &ports = input ? node.inputs : node.outputs;
    identity(name);
    if (ports.size() == View::max_ports) {
      auto &omitted = input ? node.omitted_inputs : node.omitted_outputs;
      if (!omitted) {
        issue("display_limit", node.id, "/nodes/" + std::to_string(node_index),
              "Some ports are omitted from the graph presentation");
      }
      ++omitted;
      index.emplace(name, -1);
      return -1;
    }
    const int result = int(ports.size());
    index.emplace(name, result);
    AnalysisGraphPort item;
    item.name = name;
    item.declared = declaration != nullptr;
    item.type_text = declaration ? port_type(*declaration) : "?";
    item.required = declaration && declaration->required;
    item.multi = declaration && declaration->multi;
    ports.push_back(std::move(item));
    return result;
  }

  bool references(const Json &value, const std::string &path, size_t depth,
                  size_t &visited, AnalysisGraphParameter &parameter)
  {
    if (visited++ >= 256 || depth >= 64 || path.size() > 2048) { return false; }
    if (value.is_object() && value.size() == 1 && value.contains("$param") && value["$param"].is_string()) {
      if (parameter.references.size() == 32) { return false; }
      AnalysisGraphReference reference;
      reference.parameter = identity(value["$param"].get_ref<const std::string &>());
      reference.path = path;
      const auto found = parameters_.find(reference.parameter);
      if (found != parameters_.end() && found->second && found->second->has_default) {
        reference.has_default = true;
        reference.default_text = project_value_summary(found->second->default_value, View::summary_bytes);
      }
      parameter.references.push_back(std::move(reference));
    }
    else if (value.is_object()) {
      for (auto child = value.begin(); child != value.end(); ++child) {
        if (child.key().size() > 1024 ||
            !references(child.value(), path + "/" + io::pointer_token(child.key()), depth + 1, visited, parameter)) {
          return false;
        }
      }
    }
    else if (value.is_array()) {
      for (size_t i = 0; i < value.size(); ++i) {
        if (!references(value[i], path + "/" + std::to_string(i), depth + 1, visited, parameter)) { return false; }
      }
    }
    return true;
  }

  void parameter(size_t node_index, const std::string &name, const io::ParamSpec *declaration)
  {
    auto &node = view_.nodes[node_index];
    identity(name);
    if (node.parameters.size() == View::max_parameters) {
      if (!node.omitted_parameters) {
        issue("display_limit", node.id, "/nodes/" + std::to_string(node_index) + "/params",
              "Some parameters are omitted from the graph presentation");
      }
      ++node.omitted_parameters;
      return;
    }
    AnalysisGraphParameter result;
    result.name = name;
    result.declared = declaration != nullptr;
    result.required = declaration && declaration->required;
    if (declaration) { result.stage = text(declaration->stage); result.unit = text(declaration->unit); }
    const auto &params = graph_.nodes[node_index].params;
    const Json *value = nullptr;
    const auto found = params.is_object() ? params.find(name) : params.end();
    if (found != params.end()) { result.origin = "explicit"; value = &*found; }
    else if (declaration && declaration->has_default) { result.origin = "default"; value = &declaration->default_value; }
    else { result.origin = "missing"; }
    if (value) {
      result.value_text = project_value_summary(*value, View::summary_bytes);
      size_t visited = 0;
      result.references_complete = references(*value, "", 0, visited, result);
    }
    node.parameters.push_back(std::move(result));
  }

  void node(size_t i)
  {
    const auto &source = graph_.nodes[i];
    const auto *type = catalog_ ? catalog_->find(source.type) : nullptr;
    index_[i].type = type;
    AnalysisGraphNode result;
    result.id = identity(source.id);
    result.type = identity(source.type);
    result.label = text(source.label.empty() ? source.id : source.label);
    result.known_type = type != nullptr;
    result.ambiguous_id = nodes_.at(source.id) < 0;
    if (type) {
      result.title_en = text(type->title_en);
      result.title_zh = text(type->title_zh);
      result.stage = text(type->stage);
    }
    view_.nodes.push_back(std::move(result));
    if (!type) { issue("unknown_type", source.id, "/nodes/" + std::to_string(i) + "/type", "Node type is absent from the catalog"); }
    if (view_.nodes[i].ambiguous_id) {
      issue("duplicate_id", source.id, "/nodes/" + std::to_string(i) + "/id", "Duplicate node ID cannot identify a link endpoint");
    }
    std::set<std::string> names;
    if (type) {
      for (const auto &input : type->inputs) { port(i, true, input.name, &input); }
      for (const auto &output : type->outputs) { port(i, false, output.name, &output); }
      for (const auto &item : type->params) {
        if (names.insert(item.name).second) { parameter(i, item.name, &item); }
      }
    }
    if (source.params.is_object()) {
      for (auto item = source.params.begin(); item != source.params.end(); ++item) {
        if (names.insert(item.key()).second) { parameter(i, item.key(), nullptr); }
      }
    }
    for (const auto &input : source.inputs) { port(i, true, input.port); }
  }

  int endpoint(const std::string &id) const
  {
    const auto found = nodes_.find(id);
    return found == nodes_.end() ? -1 : found->second;
  }

  std::string diagnostic(const std::string &id, int node_index, int port_index, bool input) const
  {
    const auto found = nodes_.find(id);
    if (found == nodes_.end()) { return "missing_node"; }
    if (found->second < 0) { return "ambiguous_node"; }
    if (port_index < 0) { return "display_limit"; }
    const auto &node = view_.nodes[size_t(node_index)];
    if (!node.known_type) { return "unknown_type"; }
    if (!(input ? node.inputs : node.outputs)[size_t(port_index)].declared) { return "missing_port"; }
    return {};
  }

  void links()
  {
    for (size_t target = 0; target < graph_.nodes.size(); ++target) {
      const auto &node = graph_.nodes[target];
      for (const auto &input : node.inputs) {
        for (size_t i = 0; i < input.links.size(); ++i) {
          if (view_.edges.size() == View::max_edges) { ++view_.omitted_edges; continue; }
          const auto &link = input.links[i];
          AnalysisGraphEdge edge;
          edge.source_node = identity(link.node);
          edge.source_port = identity(link.port);
          edge.target_node = identity(node.id);
          edge.target_port = identity(input.port);
          edge.alias = identity(link.alias);
          edge.link_index = i;
          edge.source = endpoint(link.node);
          // The input belongs to this concrete document node, but duplicate IDs are still invalid.
          edge.target = view_.nodes[target].ambiguous_id ? -1 : int(target);
          if (edge.source >= 0) { edge.output = port(size_t(edge.source), false, link.port); }
          if (edge.target >= 0) { edge.input = port(target, true, input.port); }
          edge.diagnostic = diagnostic(edge.source_node, edge.source, edge.output, false);
          const auto target_diagnostic = diagnostic(edge.target_node, edge.target, edge.input, true);
          if (edge.diagnostic.empty() || (edge.diagnostic == "unknown_type" && !target_diagnostic.empty())) {
            edge.diagnostic = target_diagnostic;
          }
          if (!edge.diagnostic.empty() && edge.diagnostic != "unknown_type") {
            issue(edge.diagnostic, node.id, "/nodes/" + std::to_string(target) + "/inputs/" + io::pointer_token(input.port),
                  "A link endpoint cannot be resolved to a declared visible port");
          }
          view_.edges.push_back(std::move(edge));
        }
      }
    }
    if (view_.omitted_edges) { issue("display_limit", {}, "/nodes", "Some links are omitted from the graph presentation"); }
  }

  void outputs()
  {
    for (const auto &source : graph_.outputs) {
      if (view_.outputs.size() == View::max_outputs) { ++view_.omitted_outputs; continue; }
      AnalysisGraphOutput result;
      result.name = identity(source.name);
      result.node = identity(source.node);
      result.port = identity(source.port);
      result.node_index = endpoint(source.node);
      if (result.node_index >= 0) { result.port_index = port(size_t(result.node_index), false, source.port); }
      result.diagnostic = diagnostic(result.node, result.node_index, result.port_index, false);
      if (!result.diagnostic.empty() && result.diagnostic != "unknown_type") {
        issue(result.diagnostic, result.node, "/outputs/" + io::pointer_token(result.name),
              "A graph output cannot be resolved to a declared visible port");
      }
      view_.outputs.push_back(std::move(result));
    }
    if (view_.omitted_outputs) { issue("display_limit", {}, "/outputs", "Some graph outputs are omitted from the presentation"); }
  }

  bool position(AnalysisGraphNode &node)
  {
    if (!graph_.raw.is_object()) { return false; }
    const auto ui = graph_.raw.find("ui");
    if (ui == graph_.raw.end() || !ui->is_object()) { return false; }
    const auto positions = ui->find("positions");
    if (positions == ui->end() || !positions->is_object()) { return false; }
    const auto value = positions->find(node.id);
    if (value == positions->end()) { return false; }
    if (!node.ambiguous_id && value->is_array() && value->size() == 2 && (*value)[0].is_number() && (*value)[1].is_number()) {
      const double x = (*value)[0].get<double>(), y = (*value)[1].get<double>();
      if (std::isfinite(x) && std::isfinite(y) && std::abs(x) <= 1e6 && std::abs(y) <= 1e6) {
        node.rect.x = x;
        node.rect.y = y;
        return true;
      }
    }
    issue("invalid_position", node.id, "/ui/positions/" + io::pointer_token(node.id),
          "Invalid, ambiguous or unbounded node position; using deterministic layout");
    return false;
  }

  void layout()
  {
    const size_t count = view_.nodes.size();
    std::vector<std::set<int>> next(count);
    for (const auto &edge : view_.edges) {
      if (edge.source >= 0 && edge.target >= 0) { next[size_t(edge.source)].insert(edge.target); }
    }
    // At most 200 vertices: bounded Tarjan recursion, with document-order traversal.
    std::vector<int> visit(count, -1), low(count), component(count, -1), stack;
    std::vector<bool> active(count);
    std::vector<int> sizes;
    int serial = 0;
    std::function<void(int)> walk = [&](int vertex) {
      visit[size_t(vertex)] = low[size_t(vertex)] = serial++;
      stack.push_back(vertex);
      active[size_t(vertex)] = true;
      for (const int target : next[size_t(vertex)]) {
        if (visit[size_t(target)] < 0) { walk(target); low[size_t(vertex)] = std::min(low[size_t(vertex)], low[size_t(target)]); }
        else if (active[size_t(target)]) { low[size_t(vertex)] = std::min(low[size_t(vertex)], visit[size_t(target)]); }
      }
      if (low[size_t(vertex)] != visit[size_t(vertex)]) { return; }
      int size = 0;
      for (;;) {
        const int member = stack.back(); stack.pop_back();
        active[size_t(member)] = false;
        component[size_t(member)] = int(sizes.size());
        ++size;
        if (member == vertex) { break; }
      }
      sizes.push_back(size);
    };
    for (size_t i = 0; i < count; ++i) { if (visit[i] < 0) { walk(int(i)); } }
    std::vector<std::set<int>> parents(sizes.size());
    for (size_t i = 0; i < count; ++i) {
      for (const int target : next[i]) {
        if (component[i] != component[size_t(target)]) { parents[size_t(component[size_t(target)])].insert(component[i]); }
      }
    }
    std::vector<int> ranks(sizes.size(), -1);
    std::function<int(int)> rank = [&](int group) {
      auto &result = ranks[size_t(group)];
      if (result >= 0) { return result; }
      result = 0;
      for (int parent : parents[size_t(group)]) { result = std::max(result, rank(parent) + 1); }
      return result;
    };
    std::map<int, double> bottoms;
    for (size_t i = 0; i < count; ++i) {
      auto &node = view_.nodes[i];
      node.cyclic = sizes[size_t(component[i])] > 1 || next[i].contains(int(i));
      if (node.cyclic) { issue("cycle", node.id, "/nodes/" + std::to_string(i), "Node belongs to a dependency cycle"); }
      const int layer = rank(component[i]);
      node.rect = {double(layer) * (View::node_width + 70), bottoms[layer], View::node_width,
                   std::max(80.0, View::header_height + 12 + View::port_spacing * double(std::max(node.inputs.size(), node.outputs.size())))};
      bottoms[layer] += node.rect.height + 36;
      node.supplied_position = position(node);
      for (size_t j = 0; j < node.inputs.size(); ++j) {
        node.inputs[j].point = {node.rect.x, node.rect.y + View::header_height + double(j) * View::port_spacing};
      }
      for (size_t j = 0; j < node.outputs.size(); ++j) {
        node.outputs[j].point = {node.rect.x + node.rect.width, node.rect.y + View::header_height + double(j) * View::port_spacing};
      }
    }
  }

  void endpoints()
  {
    for (auto &edge : view_.edges) {
      const auto source = edge.source >= 0 ? &view_.nodes[size_t(edge.source)] : nullptr;
      const auto target = edge.target >= 0 ? &view_.nodes[size_t(edge.target)] : nullptr;
      if (source) {
        edge.from = edge.output >= 0 ? source->outputs[size_t(edge.output)].point :
                                      AnalysisGraphPoint{source->rect.x + source->rect.width, source->rect.y + View::header_height};
      }
      if (target) {
        edge.to = edge.input >= 0 ? target->inputs[size_t(edge.input)].point :
                                  AnalysisGraphPoint{target->rect.x, target->rect.y + View::header_height};
      }
      if (!source && target) { edge.from = {edge.to.x - 60, edge.to.y}; }
      else if (source && !target) { edge.to = {edge.from.x + 60, edge.from.y}; }
    }
  }

  void bounds()
  {
    if (view_.nodes.empty()) { return; }
    double left = std::numeric_limits<double>::infinity(), top = left, right = -left, bottom = -left;
    auto point = [&](double x, double y) {
      left = std::min(left, x); top = std::min(top, y);
      right = std::max(right, x); bottom = std::max(bottom, y);
    };
    for (const auto &node : view_.nodes) {
      point(node.rect.x, node.rect.y); point(node.rect.x + node.rect.width, node.rect.y + node.rect.height);
    }
    for (const auto &edge : view_.edges) {
      if (edge.source >= 0 || edge.target >= 0) { point(edge.from.x, edge.from.y); point(edge.to.x, edge.to.y); }
    }
    view_.bounds = {left, top, right - left, bottom - top};
  }

  const io::Graph &graph_;
  const io::Catalog *catalog_;
  View view_;
  std::vector<NodeIndex> index_;
  std::map<std::string, int> nodes_;
  std::map<std::string, const io::GraphParameter *> parameters_;
};
}  // namespace

AnalysisGraphView analysis_graph_view(const io::Graph &graph, const io::Catalog *catalog)
{
  return Builder(graph, catalog).build();
}

AnalysisGraphView analysis_graph_view_moved(const AnalysisGraphView &view, const size_t node, const double dx, const double dy)
{
  AnalysisGraphView result = view;
  if (node >= result.nodes.size() || !std::isfinite(dx) || !std::isfinite(dy)) { return result; }
  auto &moved = result.nodes[node];
  moved.rect.x += dx; moved.rect.y += dy;
  for (auto *ports : {&moved.inputs, &moved.outputs}) {
    for (auto &port : *ports) { port.point.x += dx; port.point.y += dy; }
  }
  for (auto &edge : result.edges) {
    if (edge.source == int(node)) { edge.from.x += dx; edge.from.y += dy; }
    if (edge.target == int(node)) { edge.to.x += dx; edge.to.y += dy; }
  }
  return result;
}

}  // namespace stk::app
