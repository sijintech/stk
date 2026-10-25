/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_document.hh"

#include "stk/core/utf8.hh"

#include <cmath>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace stk::app {
namespace {
using io::Json;
void require(bool condition, const char *message)
{
  if (!condition) { throw std::invalid_argument(message); }
}

/** SAX preserves duplicate-key and integer-token failures that a DOM parser would erase. */
class StrictParameterValue final : public nlohmann::json_sax<Json> {
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
    if (stack_.size() > AnalysisDocumentLimits::max_depth) { return fail("Analysis JSON exceeds its depth limit"); }
    stack_.push_back({object ? Json::object() : Json::array(), {}, {}});
    return true;
  }
  bool value(Json v)
  {
    if (stack_.size() > AnalysisDocumentLimits::max_depth) { return fail("Analysis JSON exceeds its depth limit"); }
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

bool space(char32_t c)
{
  // Python str.isspace(), also used by the backend's name.strip() check.
  return (c >= 9 && c <= 13) || (c >= 28 && c <= 32) || c == 0x85 || c == 0xa0 ||
      c == 0x1680 || (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
      c == 0x202f || c == 0x205f || c == 0x3000;
}
}  // namespace

Json parse_parameter_json(const std::string_view text)
{
  require(text.size() <= AnalysisDocumentLimits::max_document_bytes, "Parameter text exceeds its 384 KiB limit");
  require(core::utf8::is_valid(text), "Parameter text must be valid UTF-8");
  require(!text.starts_with("\xef\xbb\xbf"), "JSON text must not begin with a UTF-8 byte order mark");
  StrictParameterValue parser;
  const bool ok = Json::sax_parse(text.begin(), text.end(), &parser, Json::input_format_t::json, true);
  require(ok, parser.error.empty() ? "Invalid JSON parameter value" : parser.error.c_str());
  check_analysis_json_bounds(parser.result);
  return std::move(parser.result);
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

bool visible_text(std::string_view text)
{
  for (size_t i = 0; i < text.size();) {
    const auto c = core::utf8::decode(text, i);
    if (!space(c.code_point)) { return true; }
    i += c.length;
  }
  return false;
}

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
