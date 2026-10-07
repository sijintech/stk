/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_parameter_draft.hh"
#include "stk/app/analysis_document.hh"

#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace stk::app {
namespace {
using io::Json;
using Draft = AnalysisParameterDraft;

void require(bool condition, const char *message)
{
  if (!condition) { throw std::invalid_argument(message); }
}

bool canonical_uuid(std::string_view value)
{
  if (value.size() != 36) { return false; }
  for (size_t i = 0; i < value.size(); ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') { return false; }
    }
    else if (!((value[i] >= '0' && value[i] <= '9') || (value[i] >= 'a' && value[i] <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool space(char32_t c)
{
  // Python str.isspace(), also used by the backend's name.strip() check.
  return (c >= 9 && c <= 13) || (c >= 28 && c <= 32) || c == 0x85 || c == 0xa0 ||
      c == 0x1680 || (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
      c == 0x202f || c == 0x205f || c == 0x3000;
}

bool visible_name(std::string_view name)
{
  for (size_t i = 0; i < name.size();) {
    const auto c = core::utf8::decode(name, i);
    if (!space(c.code_point)) { return true; }
    i += c.length;
  }
  return false;
}


bool same_json(const Json &a, const Json &b)
{
  return io::python_json_dumps(a, true, true) == io::python_json_dumps(b, true, true);
}

/** SAX avoids both duplicate-key replacement and the DOM parser's integer-overflow-to-double
 * fallback. Parsing is bounded before recursive serializers or copies are used. */
class StrictValue final : public nlohmann::json_sax<Json> {
 public:
  Json result;
  std::string error;

  bool null() override { return value(nullptr); }
  bool boolean(bool v) override { return value(v); }
  bool number_integer(number_integer_t v) override { return value(v); }
  bool number_unsigned(number_unsigned_t v) override { return value(v); }
  bool number_float(number_float_t v, const string_t &token) override
  {
    if (!std::isfinite(v) || token.find_first_of(".eE") == std::string::npos) {
      return fail("JSON integer tokens must fit signed or unsigned 64 bits, and numbers must be finite");
    }
    return value(v);
  }
  bool string(string_t &v) override { return value(std::move(v)); }
  bool binary(binary_t &) override { return fail("Binary data is not a JSON parameter value"); }
  bool start_object(size_t) override { return start(true); }
  bool start_array(size_t) override { return start(false); }
  bool end_object() override { return finish(); }
  bool end_array() override { return finish(); }
  bool key(string_t &key) override
  {
    auto &frame = stack_.back();
    if (!frame.keys.insert(key).second) { return fail("JSON objects must not contain duplicate keys"); }
    frame.key = std::move(key);
    return true;
  }
  bool parse_error(size_t, const std::string &, const nlohmann::detail::exception &) override
  {
    return fail("Enter one valid finite JSON value with no trailing data");
  }

 private:
  struct Frame {
    Json data;
    std::set<std::string> keys;
    std::string key;
  };
  std::vector<Frame> stack_;

  bool fail(const char *message) { error = message; return false; }
  bool start(bool object)
  {
    if (stack_.size() > Draft::max_depth) { return fail("Analysis JSON exceeds its depth limit"); }
    stack_.push_back({object ? Json::object() : Json::array(), {}, {}});
    return true;
  }
  bool value(Json v)
  {
    if (stack_.size() > Draft::max_depth) { return fail("Analysis JSON exceeds its depth limit"); }
    if (stack_.empty()) { result = std::move(v); }
    else if (stack_.back().data.is_array()) { stack_.back().data.push_back(std::move(v)); }
    else { stack_.back().data[stack_.back().key] = std::move(v); }
    return true;
  }
  bool finish()
  {
    auto completed = std::move(stack_.back().data); stack_.pop_back();
    return value(std::move(completed));
  }
};

Json strict_value(std::string_view text)
{
  require(text.size() <= Draft::max_text_bytes, "Parameter text exceeds its 384 KiB limit");
  require(core::utf8::is_valid(text), "Parameter text must be valid UTF-8");
  require(!text.starts_with("\xef\xbb\xbf"), "JSON text must not begin with a UTF-8 byte order mark");
  StrictValue parser;
  const bool ok = Json::sax_parse(text.begin(), text.end(), &parser, Json::input_format_t::json, true);
  require(ok, parser.error.empty() ? "Invalid JSON parameter value" : parser.error.c_str());
  return std::move(parser.result);
}

void parameter_key(const std::string &name)
{
  require(name.size() <= Draft::max_parameters_bytes && core::utf8::is_valid(name),
          "Parameter keys must be bounded valid UTF-8 strings");
}

/** Index of the node object whose id occurs exactly once in the raw graph, else -1. */
int unique_node(const Json &graph, const std::string &id)
{
  const auto nodes = graph.find("nodes");
  if (nodes == graph.end() || !nodes->is_array()) { return -1; }
  int found = -1;
  for (size_t index = 0; index < nodes->size(); ++index) {
    const auto &node = (*nodes)[index];
    if (!node.is_object() || io::get_string(node, "id") != id) { continue; }
    if (found >= 0) { return -1; }
    found = int(index);
  }
  return found;
}

/** A raw input value that is absent or exactly {"from": "..."}; anything else stays read-only. */
struct SingleLink {
  bool editable = false;
  std::optional<std::string> source;
};
SingleLink single_link(const Json &node, const std::string &port)
{
  const auto inputs = node.find("inputs");
  if (inputs == node.end()) { return {true, std::nullopt}; }
  if (!inputs->is_object()) { return {}; }
  const auto value = inputs->find(port);
  if (value == inputs->end()) { return {true, std::nullopt}; }
  if (!value->is_object() || value->size() != 1 || !value->contains("from") || !value->at("from").is_string()) { return {}; }
  return {true, value->at("from").get<std::string>()};
}
}  // namespace

void AnalysisParameterDraft::pin(std::string handle, std::string analysis_id, int64_t revision,
                                 std::string name, const Json &document)
{
  require(!handle.empty() && handle.size() <= max_document_bytes && core::utf8::is_valid(handle) &&
      canonical_uuid(analysis_id) && revision >= 0, "Analysis draft requires an opening handle, UUID and revision");
  require(name.size() <= 1024 && core::utf8::is_valid(name) && name.find('\0') == std::string::npos &&
      core::utf8::count_code_points(name) <= 256 && visible_name(name), "Invalid saved analysis name");
  check_analysis_document_bounds(document);
  // These are basic shape checks, not a substitute for the backend's full structural schema.
  try { (void)io::Graph::from_json(document.at("graph")); }
  catch (const std::exception &e) { throw std::invalid_argument(e.what()); }
  Json detached = document;
  handle_ = std::move(handle); analysis_id_ = std::move(analysis_id); revision_ = revision;
  name_ = std::move(name); baseline_ = std::move(detached); edits_.clear(); outputs_override_.reset();
  graph_.reset(); ++generation_; ++version_; ++evaluation_version_;
}

void AnalysisParameterDraft::reset()
{
  handle_.clear(); analysis_id_.clear(); name_.clear(); revision_ = -1;
  baseline_ = nullptr; edits_.clear(); outputs_override_.reset(); graph_.reset(); ++generation_; ++version_; ++evaluation_version_;
}

bool AnalysisParameterDraft::current(const std::string &handle, int64_t revision) const
{
  return pinned() && handle == handle_ && revision == revision_;
}

bool AnalysisParameterDraft::accepts(uint64_t generation) const
{
  return pinned() && generation == generation_;
}

std::optional<Json> AnalysisParameterDraft::override_value(const std::string &name) const
{
  if (!pinned()) { return std::nullopt; }
  if (const auto found = edits_.find(name); found != edits_.end()) { return found->second; }
  const auto &parameters = baseline_.at("parameters");
  const auto found = parameters.find(name);
  return found == parameters.end() ? std::nullopt : std::optional<Json>(*found);
}

bool AnalysisParameterDraft::has_override(const std::string &name) const
{
  if (!pinned()) { return false; }
  if (const auto found = edits_.find(name); found != edits_.end()) { return found->second.has_value(); }
  return baseline_.at("parameters").contains(name);
}

Json AnalysisParameterDraft::parameters() const
{
  Json result = pinned() ? baseline_.at("parameters") : Json::object();
  for (const auto &[name, value] : edits_) {
    if (value) { result[name] = *value; }
    else { result.erase(name); }
  }
  return result;
}

Json AnalysisParameterDraft::document_with(const Json &parameters) const
{
  if (!pinned()) { return nullptr; }
  Json result = baseline_; result["parameters"] = parameters;
  if (outputs_override_) { result["outputs"] = *outputs_override_; }
  if (graph_) { result["graph"] = *graph_; }
  return result;
}

Json AnalysisParameterDraft::candidate_document() const { return document_with(parameters()); }

Json AnalysisParameterDraft::outputs() const
{
  if (!pinned()) { return Json::array(); }
  return outputs_override_ ? *outputs_override_ : baseline_.at("outputs");
}

bool AnalysisParameterDraft::output_selected(const std::string &name) const
{
  if (!pinned()) { return false; }
  const auto &values = outputs_override_ ? *outputs_override_ : baseline_.at("outputs");
  return std::find_if(values.begin(), values.end(), [&name](const Json &value) {
    return value.get_ref<const std::string &>() == name;
  }) != values.end();
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set(const std::string &name, const Json &value,
                                                               uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The parameter draft has changed or is unavailable"}; }
  try {
    parameter_key(name); check_analysis_json_bounds(value);
    Json next = parameters(); next[name] = value;
    check_analysis_document_bounds(document_with(next));
    const auto current = override_value(name);
    if (current && same_json(*current, value)) { return {true, {}}; }
    const auto &base = baseline_.at("parameters");
    if (base.contains(name) && same_json(base.at(name), value)) { edits_.erase(name); }
    else { edits_[name] = value; }
    ++version_; ++evaluation_version_; return {true, {}};
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_text(const std::string &name, std::string_view text,
                                                                    TextMode mode, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The parameter draft has changed or is unavailable"}; }
  try {
    require(text.size() <= max_text_bytes && core::utf8::is_valid(text),
            "Parameter text must be valid UTF-8 of at most 384 KiB");
    require(mode == TextMode::Json || mode == TextMode::LiteralString, "Invalid parameter text mode");
    return set(name, mode == TextMode::Json ? strict_value(text) : Json(std::string(text)), generation);
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::remove(const std::string &name, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The parameter draft has changed or is unavailable"}; }
  try {
    parameter_key(name);
    if (!has_override(name)) { return {true, {}}; }
    if (baseline_.at("parameters").contains(name)) { edits_[name] = std::nullopt; }
    else { edits_.erase(name); }
    ++version_; ++evaluation_version_; return {true, {}};
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_outputs(const Json &values, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  try {
    // Bound every element before making a candidate copy; nested/huge values cannot reach the
    // serializer. A declared graph output is an identifier, not an arbitrary parameter key.
    require(values.is_array() && values.size() <= max_outputs,
            "Select at most 256 distinct declared outputs");
    const auto &declared = graph().at("outputs");
    std::set<std::string_view> selected;
    for (const auto &value : values) {
      require(value.is_string(), "Output names must be declared graph identifiers");
      const auto &name = value.get_ref<const std::string &>();
      require(io::is_graph_id(name) && declared.contains(name) && selected.insert(name).second,
              "Output names must be distinct declared graph identifiers");
    }
    Json candidate = candidate_document(); candidate["outputs"] = values;
    check_analysis_document_bounds(candidate);
    if (values == outputs()) { return {true, {}}; }
    if (values == baseline_.at("outputs")) { outputs_override_.reset(); }
    else { outputs_override_ = values; }
    ++version_; ++evaluation_version_; return {true, {}};
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_output(const std::string &name,
                                                                    const bool selected, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::is_graph_id(name) || !graph().at("outputs").contains(name)) {
    return {false, "Output names must be declared graph identifiers"};
  }
  auto values = outputs();
  const auto found = std::find_if(values.begin(), values.end(), [&name](const Json &value) {
    return value.get_ref<const std::string &>() == name;
  });
  if (selected && found == values.end()) { values.push_back(name); }
  else if (!selected && found != values.end()) { values.erase(found); }
  return set_outputs(values, generation);
}

const Json &AnalysisParameterDraft::graph() const
{
  static const Json none;
  if (!pinned()) { return none; }
  return graph_ ? *graph_ : baseline_.at("graph");
}

bool AnalysisParameterDraft::evaluative_graph_edits() const
{
  if (!graph_) { return false; }
  Json before = baseline_.at("graph"), after = *graph_;
  before.erase("ui"); after.erase("ui");
  return !same_json(before, after);
}

bool AnalysisParameterDraft::link_editable(const std::string &node, const std::string &port) const
{
  if (!pinned() || !io::is_graph_id(node) || !io::is_graph_id(port)) { return false; }
  const auto &candidate = graph();
  const int index = unique_node(candidate, node);
  return index >= 0 && single_link(candidate.at("nodes")[size_t(index)], port).editable;
}

std::optional<std::string> AnalysisParameterDraft::baseline_link(const std::string &node, const std::string &port) const
{
  if (!pinned()) { return std::nullopt; }
  const auto &saved = baseline_.at("graph");
  const int index = unique_node(saved, node);
  return index < 0 ? std::nullopt : single_link(saved.at("nodes")[size_t(index)], port).source;
}

std::optional<std::string> AnalysisParameterDraft::link(const std::string &node, const std::string &port) const
{
  if (!pinned()) { return std::nullopt; }
  const auto &candidate = graph();
  const int index = unique_node(candidate, node);
  return index < 0 ? std::nullopt : single_link(candidate.at("nodes")[size_t(index)], port).source;
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::edit_graph(
    uint64_t generation, const std::function<std::string(Json &graph, Json &outputs)> &change)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  try {
    Json next = graph(), requested = outputs();
    if (auto error = change(next, requested); !error.empty()) { return {false, std::move(error)}; }
    // An emptied ui.positions / ui the saved graph did not have goes, so undoing restores it exactly.
    const auto &saved = baseline_.at("graph");
    if (next.contains("ui") && next.at("ui").is_object()) {
      auto &ui = next["ui"];
      const bool saved_ui = saved.contains("ui") && saved.at("ui").is_object();
      if (ui.contains("positions") && ui.at("positions").is_object() && ui.at("positions").empty() &&
          !(saved_ui && saved.at("ui").contains("positions"))) { ui.erase("positions"); }
      if (ui.empty() && !saved.contains("ui")) { next.erase("ui"); }
    }
    Json candidate = document_with(parameters());
    candidate["graph"] = next; candidate["outputs"] = requested;
    check_analysis_document_bounds(candidate);
    try { (void)io::Graph::from_json(next); }
    catch (const std::exception &error) { return {false, error.what()}; }
    const bool graph_same = same_json(next, graph()), outputs_same = same_json(requested, outputs());
    if (graph_same && outputs_same) { return {true, {}}; }
    Json before = graph(), after = next;
    before.erase("ui"); after.erase("ui");
    const bool evaluative = !outputs_same || !same_json(before, after);
    if (same_json(next, baseline_.at("graph"))) { graph_.reset(); }
    else { graph_ = std::move(next); }
    if (same_json(requested, baseline_.at("outputs"))) { outputs_override_.reset(); }
    else { outputs_override_ = std::move(requested); }
    ++version_;
    if (evaluative) { ++evaluation_version_; }
    return {true, {}};
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

namespace {
/** The node object of a unique id, else null; `saved` tells whether the saved graph has it. */
Json *node_of(Json &graph, const std::string &id)
{
  const int index = unique_node(graph, id);
  return index < 0 ? nullptr : &graph["nodes"][size_t(index)];
}
/** Drop an emptied "inputs"/"params" object the saved node did not have, so undoing an edit
 * restores the exact saved JSON. */
void tidy(Json &node, const Json &saved_graph)
{
  const int index = unique_node(saved_graph, io::get_string(node, "id"));
  const Json *saved = index < 0 ? nullptr : &saved_graph.at("nodes")[size_t(index)];
  for (const auto *key : {"inputs", "params"}) {
    const auto found = node.find(key);
    if (found != node.end() && found->is_object() && found->empty() && !(saved && saved->contains(key))) { node.erase(key); }
  }
}
std::string link_source_error(const Json &graph, const std::string &node, const std::string &source)
{
  const auto reference = io::parse_port_ref(source);
  if (!reference || !io::is_graph_id(reference->first) || !io::is_graph_id(reference->second)) {
    return "A link source is \"node.port\" with graph identifiers";
  }
  if (reference->first == node) { return "A node cannot take its own output as an input"; }
  if (unique_node(graph, reference->first) < 0) { return "The source node must occur exactly once in the graph"; }
  return {};
}
/** Exactly {"from": string} objects, or nullopt for any other shape. */
std::optional<std::vector<std::string>> plain_links(const Json &value)
{
  std::vector<std::string> result;
  auto one = [&result](const Json &entry) {
    if (!entry.is_object() || entry.size() != 1 || !entry.contains("from") || !entry.at("from").is_string()) { return false; }
    result.push_back(entry.at("from").get<std::string>());
    return true;
  };
  if (value.is_array()) {
    for (const auto &entry : value) { if (!one(entry)) { return std::nullopt; } }
    return result;
  }
  if (!one(value)) { return std::nullopt; }
  return result;
}
bool references(const Json &link, const std::string &node)
{
  if (!link.is_object() || !link.contains("from") || !link.at("from").is_string()) { return false; }
  const auto reference = io::parse_port_ref(link.at("from").get<std::string>());
  return reference && reference->first == node;
}
std::string type_name(const std::string &type)
{
  const auto parsed = io::parse_type(type);
  std::string base = parsed ? parsed->name : std::string("node");
  for (auto &c : base) {
    if (c >= 'A' && c <= 'Z') { c = char(c - 'A' + 'a'); }
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) { c = '_'; }
  }
  if (base.empty() || !(base[0] >= 'a' && base[0] <= 'z')) { base = "n_" + base; }
  return base.substr(0, 56);
}
}  // namespace

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_link(const std::string &node, const std::string &port,
                                                                    const std::optional<std::string> &source,
                                                                    uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!link_editable(node, port)) {
    return {false, "Only an input with no link or exactly one {\"from\"} link of a uniquely named node can be edited"};
  }
  if (source) {
    if (auto error = link_source_error(graph(), node, *source); !error.empty()) { return {false, std::move(error)}; }
  }
  return edit_graph(generation, [&](Json &next, Json &) -> std::string {
    auto &target = *node_of(next, node);
    if (source) {
      if (!target.contains("inputs")) { target["inputs"] = Json::object(); }
      target["inputs"][port] = Json{{"from", *source}};
    }
    else if (target.contains("inputs")) { target["inputs"].erase(port); }
    tidy(target, baseline_.at("graph"));
    return {};
  });
}

bool AnalysisParameterDraft::links_editable(const std::string &node, const std::string &port) const
{
  if (!pinned() || !io::is_graph_id(node) || !io::is_graph_id(port)) { return false; }
  const auto &candidate = graph();
  const int index = unique_node(candidate, node);
  if (index < 0) { return false; }
  const auto &value = candidate.at("nodes")[size_t(index)];
  const auto inputs = value.find("inputs");
  if (inputs == value.end()) { return true; }
  if (!inputs->is_object()) { return false; }
  const auto found = inputs->find(port);
  return found == inputs->end() || plain_links(*found).has_value();
}

std::vector<std::string> AnalysisParameterDraft::links(const std::string &node, const std::string &port) const
{
  if (!pinned()) { return {}; }
  const auto &candidate = graph();
  const int index = unique_node(candidate, node);
  if (index < 0) { return {}; }
  const auto &value = candidate.at("nodes")[size_t(index)];
  if (!value.contains("inputs") || !value.at("inputs").is_object() || !value.at("inputs").contains(port)) { return {}; }
  return plain_links(value.at("inputs").at(port)).value_or(std::vector<std::string>{});
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_links(const std::string &node, const std::string &port,
                                                                     const std::vector<std::string> &sources,
                                                                     uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!links_editable(node, port)) {
    return {false, "Only a list input whose entries are exactly {\"from\"} links of a uniquely named node can be edited"};
  }
  if (sources.size() > 256) { return {false, "A list input holds at most 256 links"}; }
  for (const auto &source : sources) {
    if (auto error = link_source_error(graph(), node, source); !error.empty()) { return {false, std::move(error)}; }
  }
  return edit_graph(generation, [&](Json &next, Json &) -> std::string {
    auto &target = *node_of(next, node);
    if (sources.empty()) {
      if (target.contains("inputs")) { target["inputs"].erase(port); }
    }
    else {
      Json list = Json::array();
      for (const auto &source : sources) { list.push_back(Json{{"from", source}}); }
      if (!target.contains("inputs")) { target["inputs"] = Json::object(); }
      target["inputs"][port] = std::move(list);
    }
    tidy(target, baseline_.at("graph"));
    return {};
  });
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::add_node(const std::string &type,
                                                                    std::optional<std::pair<double, double>> position,
                                                                    uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::parse_type(type)) { return {false, "A node type is \"namespace.family.name@major\""}; }
  const auto &current = graph();
  if (current.at("nodes").size() >= max_nodes) { return {false, "A graph holds at most 200 nodes"}; }
  std::set<std::string> taken;
  for (const auto &node : current.at("nodes")) { if (node.is_object()) { taken.insert(io::get_string(node, "id")); } }
  const auto base = type_name(type);
  std::string id = base;
  for (int suffix = 2; taken.count(id); ++suffix) { id = base + "_" + std::to_string(suffix); }
  auto result = edit_graph(generation, [&](Json &next, Json &) -> std::string {
    next["nodes"].push_back(Json{{"id", id}, {"type", type}});
    if (position) {
      const auto [x, y] = *position;
      if (!std::isfinite(x) || !std::isfinite(y) || std::abs(x) > 1e6 || std::abs(y) > 1e6) {
        return "Node positions are finite and at most 1e6 in size";
      }
      if (next.contains("ui") && !next.at("ui").is_object()) { return "The graph's ui entry is not an object"; }
      auto &positions = next["ui"]["positions"];
      if (!positions.is_null() && !positions.is_object()) { return "The graph's ui.positions entry is not an object"; }
      positions[id] = Json::array({int64_t(std::llround(x)), int64_t(std::llround(y))});
    }
    return {};
  });
  if (result.accepted) { result.id = id; }
  return result;
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::remove_node(const std::string &node, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::is_graph_id(node) || unique_node(graph(), node) < 0) { return {false, "Only a uniquely named node can be removed"}; }
  return edit_graph(generation, [&](Json &next, Json &requested) -> std::string {
    auto &nodes = next["nodes"];
    nodes.erase(nodes.begin() + unique_node(next, node));
    for (auto &other : nodes) {
      if (!other.is_object() || !other.contains("inputs") || !other.at("inputs").is_object()) { continue; }
      auto &inputs = other["inputs"];
      for (auto it = inputs.begin(); it != inputs.end();) {
        if (it->is_array()) {
          Json kept = Json::array();
          for (const auto &entry : *it) { if (!references(entry, node)) { kept.push_back(entry); } }
          if (kept.size() == it->size()) { ++it; continue; }
          if (kept.empty()) { it = inputs.erase(it); continue; }
          *it = std::move(kept); ++it; continue;
        }
        if (references(*it, node)) { it = inputs.erase(it); continue; }
        ++it;
      }
      tidy(other, baseline_.at("graph"));
    }
    std::set<std::string> withdrawn;
    if (next.contains("outputs") && next.at("outputs").is_object()) {
      auto &exposed = next["outputs"];
      for (auto it = exposed.begin(); it != exposed.end();) {
        const auto reference = it->is_string() ? io::parse_port_ref(it->get<std::string>()) : std::nullopt;
        if (reference && reference->first == node) { withdrawn.insert(it.key()); it = exposed.erase(it); }
        else { ++it; }
      }
    }
    Json kept = Json::array();
    for (const auto &name : requested) { if (!withdrawn.count(name.get<std::string>())) { kept.push_back(name); } }
    requested = std::move(kept);
    if (next.contains("ui") && next.at("ui").is_object() && next.at("ui").contains("positions") &&
        next.at("ui").at("positions").is_object()) {
      next["ui"]["positions"].erase(node);
    }
    return {};
  });
}

std::optional<Json> AnalysisParameterDraft::node_param(const std::string &node, const std::string &name) const
{
  if (!pinned()) { return std::nullopt; }
  const auto &candidate = graph();
  const int index = unique_node(candidate, node);
  if (index < 0) { return std::nullopt; }
  const auto &value = candidate.at("nodes")[size_t(index)];
  if (!value.contains("params") || !value.at("params").is_object() || !value.at("params").contains(name)) { return std::nullopt; }
  return value.at("params").at(name);
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_node_param(const std::string &node, const std::string &name,
                                                                          const std::optional<Json> &value,
                                                                          uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::is_graph_id(node) || unique_node(graph(), node) < 0) { return {false, "Only params of a uniquely named node can be edited"}; }
  if (name.empty() || name.size() > 256 || !core::utf8::is_valid(name)) { return {false, "Param names are short valid UTF-8 strings"}; }
  try { if (value) { check_analysis_json_bounds(*value); } }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
  return edit_graph(generation, [&](Json &next, Json &) -> std::string {
    auto &target = *node_of(next, node);
    if (target.contains("params") && !target.at("params").is_object()) { return "The node's params entry is not an object"; }
    if (value) { target["params"][name] = *value; }
    else if (target.contains("params")) { target["params"].erase(name); }
    tidy(target, baseline_.at("graph"));
    return {};
  });
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::move_nodes(
    const std::map<std::string, std::pair<double, double>> &positions, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  for (const auto &[node, point] : positions) {
    if (!io::is_graph_id(node) || unique_node(graph(), node) < 0) { return {false, "Only uniquely named nodes can be placed"}; }
    if (!std::isfinite(point.first) || !std::isfinite(point.second) || std::abs(point.first) > 1e6 || std::abs(point.second) > 1e6) {
      return {false, "Node positions are finite and at most 1e6 in size"};
    }
  }
  return edit_graph(generation, [&](Json &next, Json &) -> std::string {
    if (positions.empty()) { return {}; }
    if (next.contains("ui") && !next.at("ui").is_object()) { return "The graph's ui entry is not an object"; }
    auto &placed = next["ui"]["positions"];
    if (!placed.is_null() && !placed.is_object()) { return "The graph's ui.positions entry is not an object"; }
    for (const auto &[node, point] : positions) {
      placed[node] = Json::array({int64_t(std::llround(point.first)), int64_t(std::llround(point.second))});
    }
    return {};
  });
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_graph_output(const std::string &name,
                                                                            const std::optional<std::string> &port,
                                                                            uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::is_graph_id(name)) { return {false, "Output names are graph identifiers"}; }
  if (port) {
    const auto reference = io::parse_port_ref(*port);
    if (!reference || !io::is_graph_id(reference->first) || !io::is_graph_id(reference->second) ||
        unique_node(graph(), reference->first) < 0) {
      return {false, "An output names \"node.port\" of a uniquely named node"};
    }
  }
  return edit_graph(generation, [&](Json &next, Json &requested) -> std::string {
    if (!next.contains("outputs") || !next.at("outputs").is_object()) { return "The graph's outputs entry is not an object"; }
    if (port) { next["outputs"][name] = *port; return {}; }
    if (next.at("outputs").size() <= 1 && next.at("outputs").contains(name)) { return "A graph keeps at least one output"; }
    next["outputs"].erase(name);
    Json kept = Json::array();
    for (const auto &value : requested) { if (value.get<std::string>() != name) { kept.push_back(value); } }
    requested = std::move(kept);
    return {};
  });
}

std::vector<AnalysisParameterDraft::GraphChange> AnalysisParameterDraft::graph_changes() const
{
  std::vector<GraphChange> changes;
  if (!graph_) { return changes; }
  const auto &before = baseline_.at("graph"), &after = *graph_;
  auto unique_ids = [](const Json &value) {
    std::vector<std::string> ids;
    std::map<std::string, int> counts;
    for (const auto &node : value.at("nodes")) { if (node.is_object()) { ++counts[io::get_string(node, "id")]; } }
    for (const auto &node : value.at("nodes")) {
      const auto id = node.is_object() ? io::get_string(node, "id") : std::string();
      if (node.is_object() && counts[id] == 1) { ids.push_back(id); }
    }
    return ids;
  };
  auto member = [](const Json &object, const std::string &key) -> std::optional<Json> {
    if (!object.is_object() || !object.contains(key)) { return std::nullopt; }
    return object.at(key);
  };
  auto positions = [&member](const Json &graph) {
    const auto ui = member(graph, "ui");
    return ui ? member(*ui, "positions").value_or(Json()) : Json();
  };
  const auto saved_ids = unique_ids(before), candidate_ids = unique_ids(after);
  const std::set<std::string> saved(saved_ids.begin(), saved_ids.end()), candidate(candidate_ids.begin(), candidate_ids.end());
  const Json saved_positions = positions(before), candidate_positions = positions(after);
  for (const auto &id : saved_ids) {
    if (!candidate.count(id)) { changes.push_back({"node_removed", id, {}, std::nullopt, std::nullopt}); }
  }
  for (const auto &id : candidate_ids) {
    const auto &next = after.at("nodes")[size_t(unique_node(after, id))];
    if (!saved.count(id)) {
      changes.push_back({"node_added", id, io::get_string(next, "type"), std::nullopt, std::nullopt});
    }
    const Json *previous = saved.count(id) ? &before.at("nodes")[size_t(unique_node(before, id))] : nullptr;
    for (const auto *section : {"inputs", "params"}) {
      const Json old_values = previous ? member(*previous, section).value_or(Json::object()) : Json::object();
      const Json new_values = member(next, section).value_or(Json::object());
      std::set<std::string> keys;
      if (old_values.is_object()) { for (const auto &[key, _] : old_values.items()) { keys.insert(key); } }
      if (new_values.is_object()) { for (const auto &[key, _] : new_values.items()) { keys.insert(key); } }
      for (const auto &key : keys) {
        const auto a = member(old_values, key), b = member(new_values, key);
        if (a.has_value() != b.has_value() || (a && !same_json(*a, *b))) {
          changes.push_back({std::string(section) == "inputs" ? "input" : "param", id, key, a, b});
        }
      }
    }
    const auto a = member(saved_positions, id), b = member(candidate_positions, id);
    if (b && (!a || !same_json(*a, *b))) { changes.push_back({"position", id, {}, a, b}); }
  }
  const Json old_outputs = member(before, "outputs").value_or(Json::object()), new_outputs = member(after, "outputs").value_or(Json::object());
  for (const auto &[name, value] : new_outputs.items()) {
    const auto previous = member(old_outputs, name);
    if (!previous) { changes.push_back({"output_added", {}, name, std::nullopt, value}); }
    else if (!same_json(*previous, value)) { changes.push_back({"output_changed", {}, name, previous, value}); }
  }
  for (const auto &[name, value] : old_outputs.items()) {
    if (!new_outputs.contains(name)) { changes.push_back({"output_removed", {}, name, value, std::nullopt}); }
  }
  return changes;
}

std::map<AnalysisParameterDraft::LinkKey, std::optional<std::string>> AnalysisParameterDraft::link_edits() const
{
  std::map<LinkKey, std::optional<std::string>> edits;
  if (!graph_) { return edits; }
  const auto &before = baseline_.at("graph");
  for (const auto &change : graph_changes()) {
    if (change.kind != "input" || unique_node(before, change.node) < 0) { continue; }
    auto single = [](const std::optional<Json> &value) -> std::optional<std::optional<std::string>> {
      if (!value) { return std::optional<std::string>(); }
      if (value->is_object() && value->size() == 1 && value->contains("from") && value->at("from").is_string()) {
        return std::optional<std::string>(value->at("from").get<std::string>());
      }
      return std::nullopt;
    };
    const auto a = single(change.before), b = single(change.after);
    if (a && b) { edits[{change.node, change.key}] = *b; }
  }
  return edits;
}

bool AnalysisParameterDraft::revert(uint64_t generation)
{
  if (!accepts(generation)) { return false; }
  if (dirty()) { edits_.clear(); outputs_override_.reset(); graph_.reset(); ++version_; ++evaluation_version_; }
  return true;
}

bool AnalysisParameterDraft::matches(const std::string &analysis_id, const std::string &name,
                                    const Json &document) const
{
  if (!pinned() || analysis_id != analysis_id_ || name != name_) { return false; }
  try { check_analysis_document_bounds(document); return same_json(candidate_document(), document); }
  catch (const std::invalid_argument &) { return false; }
}

uint64_t AnalysisCandidateValidation::begin(AnalysisCandidateKey key)
{
  key_ = std::move(key); response_ = nullptr; error_.clear(); pending_ = true;
  return ++ticket_;
}

bool AnalysisCandidateValidation::finish(const uint64_t ticket, const Json &response)
{
  if (!pending_ || ticket != ticket_) { return false; }
  pending_ = false;
  if (!response.is_object() || !response.contains("ok") || !response.at("ok").is_boolean() ||
      !response.contains("issues") || !response.at("issues").is_array()) {
    error_ = "Invalid graph validation response";
    return false;
  }
  response_ = response;
  return true;
}

bool AnalysisCandidateValidation::fail(const uint64_t ticket, std::string error)
{
  if (!pending_ || ticket != ticket_) { return false; }
  pending_ = false; response_ = nullptr; error_ = std::move(error);
  return true;
}

void AnalysisCandidateValidation::reset()
{
  key_ = {}; response_ = nullptr; error_.clear(); pending_ = false; ++ticket_;
}

const Json *AnalysisCandidateValidation::result(const AnalysisCandidateKey &key) const
{
  return !pending_ && !response_.is_null() && key == key_ ? &response_ : nullptr;
}

bool AnalysisCandidateValidation::passed(const AnalysisCandidateKey &key) const
{
  const auto *response = result(key);
  return response && response->at("ok").get<bool>();
}

std::string AnalysisCandidateValidation::error(const AnalysisCandidateKey &key) const
{
  return !pending_ && key == key_ ? error_ : std::string();
}

}  // namespace stk::app
