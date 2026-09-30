/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_parameter_draft.hh"

#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"

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

/** Match the storage clone's raw budget/depth before copying or recursively serializing JSON.
 * Object keys count as values at depth+1. The raw budget deliberately precedes canonical bytes. */
void plain_json(const Json &value, size_t byte_limit = Draft::max_document_bytes)
{
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
    require(depth <= Draft::max_depth, "Analysis JSON exceeds its depth limit");
    if (current->is_object() || current->is_array()) {
      add_bytes(2);
      const size_t multiplier = current->is_object() ? 2 : 1;
      require(current->size() <= (Draft::max_document_bytes - scheduled) / multiplier,
              "Analysis JSON exceeds its item limit");
      scheduled += current->size() * multiplier;
      for (auto it = current->begin(); it != current->end(); ++it) {
        if (current->is_object()) {
          require(depth + 1 <= Draft::max_depth, "Analysis JSON exceeds its depth limit");
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

void document_bounds(const Json &document)
{
  plain_json(document);
  require(document.is_object() && document.size() == 4 && document.contains("format") &&
      document.at("format") == "stk.analysis-document/1" && document.contains("graph") &&
      document.contains("parameters") && document.contains("outputs"), "Invalid saved analysis document shape");
  const auto &graph = document.at("graph");
  const auto &parameters = document.at("parameters");
  const auto &outputs = document.at("outputs");
  require(graph.is_object() && io::canonical_json(graph).size() <= Draft::max_graph_bytes,
          "Analysis graph exceeds its 256 KiB limit or is not an object");
  require(parameters.is_object() && parameters.size() <= Draft::max_overrides &&
      io::canonical_json(parameters).size() <= Draft::max_parameters_bytes,
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
      require(node.at("params").is_object() && io::canonical_json(node.at("params")).size() <= Draft::max_parameters_bytes,
              "Analysis node parameters require an object of at most 64 KiB");
    }
  }
  require(io::canonical_json(document).size() <= Draft::max_document_bytes,
          "Analysis document exceeds its 384 KiB limit");
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
}  // namespace

void AnalysisParameterDraft::pin(std::string handle, std::string analysis_id, int64_t revision,
                                 std::string name, const Json &document)
{
  require(!handle.empty() && handle.size() <= max_document_bytes && core::utf8::is_valid(handle) &&
      canonical_uuid(analysis_id) && revision >= 0, "Analysis draft requires an opening handle, UUID and revision");
  require(name.size() <= 1024 && core::utf8::is_valid(name) && name.find('\0') == std::string::npos &&
      core::utf8::count_code_points(name) <= 256 && visible_name(name), "Invalid saved analysis name");
  document_bounds(document);
  // These are basic shape checks, not a substitute for the backend's full structural schema.
  try { (void)io::Graph::from_json(document.at("graph")); }
  catch (const std::exception &e) { throw std::invalid_argument(e.what()); }
  Json detached = document;
  handle_ = std::move(handle); analysis_id_ = std::move(analysis_id); revision_ = revision;
  name_ = std::move(name); baseline_ = std::move(detached); edits_.clear();
  ++generation_; ++version_;
}

void AnalysisParameterDraft::reset()
{
  handle_.clear(); analysis_id_.clear(); name_.clear(); revision_ = -1;
  baseline_ = nullptr; edits_.clear(); ++generation_; ++version_;
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
  Json result = baseline_; result["parameters"] = parameters; return result;
}

Json AnalysisParameterDraft::candidate_document() const { return document_with(parameters()); }

AnalysisParameterDraft::EditResult AnalysisParameterDraft::set(const std::string &name, const Json &value,
                                                               uint64_t generation)
{
  if (!accepts(generation)) { return {false, "The parameter draft has changed or is unavailable"}; }
  try {
    parameter_key(name); plain_json(value);
    Json next = parameters(); next[name] = value;
    document_bounds(document_with(next));
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

bool AnalysisParameterDraft::revert(uint64_t generation)
{
  if (!accepts(generation)) { return false; }
  if (dirty()) { edits_.clear(); ++version_; }
  return true;
}

bool AnalysisParameterDraft::matches(const std::string &analysis_id, const std::string &name,
                                    const Json &document) const
{
  if (!pinned() || analysis_id != analysis_id_ || name != name_) { return false; }
  try { document_bounds(document); return same_json(candidate_document(), document); }
  catch (const std::invalid_argument &) { return false; }
}

}  // namespace stk::app
