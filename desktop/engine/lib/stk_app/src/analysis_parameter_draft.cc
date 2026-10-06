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
  link_edits_.clear(); ++generation_; ++version_;
}

void AnalysisParameterDraft::reset()
{
  handle_.clear(); analysis_id_.clear(); name_.clear(); revision_ = -1;
  baseline_ = nullptr; edits_.clear(); outputs_override_.reset(); link_edits_.clear(); ++generation_; ++version_;
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
  if (!link_edits_.empty()) {
    auto &graph = result["graph"];
    for (const auto &[key, source] : link_edits_) {
      // set_link admitted only unique nodes, and nodes are never added, removed or reordered.
      auto &node = graph["nodes"][size_t(unique_node(graph, key.first))];
      if (source) {
        if (!node.contains("inputs")) { node["inputs"] = Json::object(); }
        node["inputs"][key.second] = Json{{"from", *source}};
      }
      else if (node.contains("inputs")) { node["inputs"].erase(key.second); }
    }
  }
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
    ++version_; return {true, {}};
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
    ++version_; return {true, {}};
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
    const auto &declared = baseline_.at("graph").at("outputs");
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
    ++version_; return {true, {}};
  }
  catch (const std::invalid_argument &error) { return {false, error.what()}; }
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_output(const std::string &name,
                                                                    const bool selected, uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!io::is_graph_id(name) || !baseline_.at("graph").at("outputs").contains(name)) {
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

bool AnalysisParameterDraft::link_editable(const std::string &node, const std::string &port) const
{
  if (!pinned() || !io::is_graph_id(node) || !io::is_graph_id(port)) { return false; }
  const auto &graph = baseline_.at("graph");
  const int index = unique_node(graph, node);
  return index >= 0 && single_link(graph.at("nodes")[size_t(index)], port).editable;
}

std::optional<std::string> AnalysisParameterDraft::baseline_link(const std::string &node, const std::string &port) const
{
  if (!pinned()) { return std::nullopt; }
  const auto &graph = baseline_.at("graph");
  const int index = unique_node(graph, node);
  return index < 0 ? std::nullopt : single_link(graph.at("nodes")[size_t(index)], port).source;
}

std::optional<std::string> AnalysisParameterDraft::link(const std::string &node, const std::string &port) const
{
  if (const auto found = link_edits_.find({node, port}); found != link_edits_.end()) { return found->second; }
  return baseline_link(node, port);
}

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set_link(const std::string &node, const std::string &port,
                                                                    const std::optional<std::string> &source,
                                                                    uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The analysis draft has changed or is unavailable"}; }
  if (!link_editable(node, port)) {
    return {false, "Only an input with no link or exactly one {\"from\"} link of a uniquely named node can be edited"};
  }
  if (source) {
    const auto reference = io::parse_port_ref(*source);
    if (!reference || !io::is_graph_id(reference->first) || !io::is_graph_id(reference->second)) {
      return {false, "A link source is \"node.port\" with graph identifiers"};
    }
    if (reference->first == node) { return {false, "A node cannot take its own output as an input"}; }
    if (unique_node(baseline_.at("graph"), reference->first) < 0) {
      return {false, "The source node must occur exactly once in the graph"};
    }
  }
  if (link(node, port) == source) { return {true, {}}; }
  const LinkKey key{node, port};
  const auto previous = link_edits_;
  if (baseline_link(node, port) == source) { link_edits_.erase(key); }
  else { link_edits_[key] = source; }
  try { check_analysis_document_bounds(candidate_document()); }
  catch (const std::invalid_argument &error) { link_edits_ = previous; return {false, error.what()}; }
  ++version_; return {true, {}};
}

bool AnalysisParameterDraft::revert(uint64_t generation)
{
  if (!accepts(generation)) { return false; }
  if (dirty()) { edits_.clear(); outputs_override_.reset(); link_edits_.clear(); ++version_; }
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
