/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/analysis_result_inspection.hh"

#include "stk/core/sha256.hh"
#include "stk/core/utf8.hh"
#include "stk/io/graph.hh"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace stk::app {
namespace {
using io::Json;
using Limits = AnalysisResultInspection;
void require(const bool valid, const char *message)
{
  if (!valid) { throw std::invalid_argument(message); }
}

// Exact byte count of Python's compact ensure_ascii=False JSON, retaining numeric types.
// Traverse only borrowed values. Bound scheduling/depth before any recursive encoder/copy.
size_t preflight(const Json &root)
{
  struct Item { const Json *value; size_t depth; };
  std::vector<Item> pending{{&root, 0}};
  size_t scheduled = 1, bytes = 0;
  const auto add = [&bytes](const size_t n) {
    require(n <= Limits::max_result_bytes - bytes, "Analysis result exceeds its 4 MiB JSON limit");
    bytes += n;
  };
  const auto string_bytes = [&add](const std::string &text) {
    require(text.size() <= Limits::max_result_bytes && core::utf8::is_valid(text),
            "Analysis result strings require bounded valid UTF-8");
    add(2);
    for (const unsigned char c : text) {
      if (c == '"' || c == '\\' || c == '\b' || c == '\f' || c == '\n' || c == '\r' || c == '\t') { add(2); }
      else { add(c < 32 ? 6 : 1); }
    }
  };
  while (!pending.empty()) {
    const auto [value, depth] = pending.back(); pending.pop_back();
    require(depth <= Limits::max_depth, "Analysis result exceeds its JSON depth limit");
    if (value->is_object() || value->is_array()) {
      add(2);
      if (!value->empty()) { add(value->size() - 1); }
      const size_t multiplier = value->is_object() ? 2 : 1;
      require(value->size() <= (Limits::max_result_bytes - scheduled) / multiplier,
              "Analysis result exceeds its JSON item limit");
      scheduled += value->size() * multiplier;
      if (value->is_object()) { add(value->size()); }
      require(value->empty() || depth < Limits::max_depth, "Analysis result exceeds its JSON depth limit");
      for (auto it = value->begin(); it != value->end(); ++it) {
        if (value->is_object()) { string_bytes(it.key()); }
        pending.push_back({&it.value(), depth + 1});
      }
    }
    else if (value->is_string()) { string_bytes(value->get_ref<const std::string &>()); }
    else if (value->is_number_float()) {
      require(std::isfinite(value->get<double>()), "Analysis result numbers must be finite");
      add(io::python_float_repr(value->get<double>()).size());
    }
    else if (value->is_number_integer()) { add(io::python_str(*value).size()); }
    else if (value->is_null()) { add(4); }
    else if (value->is_boolean()) { add(value->get<bool>() ? 4 : 5); }
    else { throw std::invalid_argument("Analysis results require plain JSON data"); }
  }
  return bytes;
}

std::string escaped_token(const std::string &text, size_t &position)
{
  const auto c = static_cast<unsigned char>(text[position]);
  ++position;
  switch (c) {
    case '"': return "\\\"";
    case '\\': return "\\\\";
    case '\b': return "\\b";
    case '\f': return "\\f";
    case '\n': return "\\n";
    case '\r': return "\\r";
    case '\t': return "\\t";
    default: break;
  }
  if (c < 32) {
    constexpr char hex[] = "0123456789abcdef";
    std::string token = "\\u00"; token.push_back(hex[c >> 4]); token.push_back(hex[c & 15]); return token;
  }
  const auto start = position - 1;
  const auto length = core::utf8::decode(text, start).length;
  position = start + length;
  return text.substr(start, length);
}

std::pair<std::string, bool> string_preview(const std::string &text)
{
  std::string result = "\"";
  std::vector<size_t> starts;
  size_t position = 0;
  while (position < text.size()) {
    auto token = escaped_token(text, position);
    if (result.size() + token.size() + 1 > Limits::preview_bytes) {
      while (result.size() + 4 > Limits::preview_bytes) {
        result.resize(starts.back()); starts.pop_back();
      }
      result += "…\"";
      return {std::move(result), true};
    }
    starts.push_back(result.size());
    result += token;
  }
  result += '"';
  return {std::move(result), false};
}

AnalysisJsonDescription description(const Json &value)
{
  AnalysisJsonDescription result;
  if (value.is_object() || value.is_array()) {
    result.type = value.is_object() ? AnalysisJsonType::Object : AnalysisJsonType::Array;
    result.child_count = value.size();
    result.preview = (value.is_object() ? "{…} (" : "[…] (") + std::to_string(value.size()) + ")";
  }
  else if (value.is_string()) {
    result.type = AnalysisJsonType::String;
    auto [preview, truncated] = string_preview(value.get_ref<const std::string &>());
    result.preview = std::move(preview); result.preview_truncated = truncated;
  }
  else {
    if (value.is_number_unsigned()) { result.type = AnalysisJsonType::UnsignedInteger; }
    else if (value.is_number_integer()) { result.type = AnalysisJsonType::Integer; }
    else if (value.is_number_float()) { result.type = AnalysisJsonType::Float; }
    else if (value.is_boolean()) { result.type = AnalysisJsonType::Boolean; }
    else { result.type = AnalysisJsonType::Null; }
    result.preview = io::python_json_dumps(value, true, true);
  }
  return result;
}

AnalysisJsonText split_text(const std::string &text, const bool json_escapes)
{
  AnalysisJsonText result; result.total_bytes = text.size();
  std::string page;
  for (size_t position = 0; position < text.size();) {
    size_t length;
    if (json_escapes && text[position] == '\\') { length = text[position + 1] == 'u' ? 6 : 2; }
    else { length = core::utf8::decode(text, position).length; }
    if (page.size() + length > Limits::scalar_page_bytes) { result.pages.push_back(std::move(page)); page.clear(); }
    page.append(text, position, length); position += length;
  }
  if (!page.empty() || result.pages.empty()) { result.pages.push_back(std::move(page)); }
  return result;
}

bool known_delivery(const std::string_view type)
{
  return type == "payload" || type == "image" || type == "plot" || type == "table" ||
      type == "value" || type == "dataset" || type == "file";
}
} // namespace

std::shared_ptr<const AnalysisResultInspection> AnalysisResultInspection::from_result(
    const Json &requested_outputs, const Json &archived_result)
{
  require(requested_outputs.is_array() && requested_outputs.size() <= 256,
          "Requested analysis outputs require at most 256 names");
  std::set<std::string> requested;
  for (const auto &name : requested_outputs) {
    require(name.is_string() && io::is_graph_id(name.get_ref<const std::string &>()),
            "Requested analysis output names must be graph identifiers");
    require(requested.insert(name.get_ref<const std::string &>()).second, "Requested analysis outputs must be distinct");
  }
  const auto bytes = preflight(archived_result);
  require(archived_result.is_object() && archived_result.contains("schema") &&
      archived_result.at("schema") == "stk.graph-result/1" && archived_result.contains("outputs") &&
      archived_result.at("outputs").is_object() && archived_result.at("outputs").size() <= 256,
      "Invalid archived analysis result shape");
  const auto &delivered = archived_result.at("outputs");
  for (const auto &[name, unused] : delivered.items()) {
    (void)unused;
    require(requested.contains(name), "The result contains an output outside the frozen selection");
  }
  // Match the backend archive's exact hash, including 1.0 and signed zero. A caller must
  // compare this to the trusted run receipt before publishing parsed numeric values.
  const auto encoded = io::python_json_dumps(archived_result, true, true);
  require(encoded.size() == bytes && encoded.size() <= max_result_bytes, "Analysis result encoding differs from its bounded preflight");
  const auto digest = core::Sha256::hex(encoded);
  auto model = std::shared_ptr<AnalysisResultInspection>(new AnalysisResultInspection);
  model->encoded_bytes_ = bytes; model->encoded_sha256_ = digest;
  model->result_ = archived_result;
  for (const auto &item : requested_outputs) {
    AnalysisResultOutput output;
    output.name = item.get_ref<const std::string &>();
    output.path = {std::string("outputs"), output.name};
    const auto found = delivered.find(output.name);
    output.delivered = found != delivered.end();
    if (output.delivered && found->is_object()) {
      const auto type = found->find("type");
      if (type != found->end() && type->is_string()) {
        const auto &name = type->get_ref<const std::string &>();
        if (known_delivery(name)) { output.delivery_type = name; }
      }
      output.metadata_only = output.delivery_type == "dataset";
      output.content_not_loaded = output.delivery_type == "image" || output.delivery_type == "plot" ||
          output.delivery_type == "file" || ((output.delivery_type == "table" || output.delivery_type == "value") && found->contains("blob"));
    }
    model->outputs_.push_back(std::move(output));
  }
  const auto issues = [&archived_result](const char *key) {
    AnalysisResultIssues result; result.path = {std::string(key)};
    const auto found = archived_result.find(key);
    if (found != archived_result.end()) { result.present = true; result.value = description(*found); }
    return result;
  };
  model->errors_ = issues("errors"); model->warnings_ = issues("warnings");
  return model;
}

const Json &AnalysisResultInspection::resolve(const AnalysisJsonPath &path) const
{
  require(path.size() <= max_depth, "Analysis result path exceeds its depth limit");
  size_t bytes = 0;
  for (const auto &component : path) {
    if (const auto *key = std::get_if<std::string>(&component)) {
      require(key->size() <= max_result_bytes - bytes && core::utf8::is_valid(*key),
              "Analysis result path requires bounded valid UTF-8 keys");
      bytes += key->size();
    }
  }
  const Json *value = &result_;
  for (const auto &component : path) {
    if (const auto *key = std::get_if<std::string>(&component)) {
      require(value->is_object(), "An object key cannot select an analysis array or scalar");
      const auto found = value->find(*key);
      require(found != value->end(), "The analysis result property does not exist");
      value = &*found;
    }
    else {
      const auto index = std::get<size_t>(component);
      require(value->is_array() && index < value->size(), "The analysis result array index does not exist");
      value = &(*value)[index];
    }
  }
  return *value;
}

AnalysisJsonDescription AnalysisResultInspection::describe(const AnalysisJsonPath &path) const
{
  return description(resolve(path));
}

AnalysisJsonPropertyPage AnalysisResultInspection::children(const AnalysisJsonPath &path,
                                                            const size_t offset, const size_t limit) const
{
  const auto &value = resolve(path);
  require(value.is_object() || value.is_array(), "Only analysis result containers have child properties");
  require(limit >= 1 && limit <= page_size && offset <= value.size(), "Invalid analysis result property page");
  AnalysisJsonPropertyPage result;
  result.value = description(value); result.offset = offset; result.total = value.size();
  const size_t end = offset + std::min(limit, value.size() - offset);
  auto it = value.begin(); std::advance(it, offset);
  for (size_t index = offset; index < end; ++index, ++it) {
    AnalysisJsonProperty row;
    if (value.is_object()) {
      row.component = it.key();
      auto [label, truncated] = string_preview(it.key());
      row.label = std::move(label); row.label_truncated = truncated;
    }
    else { row.component = index; row.label = std::to_string(index); }
    row.value = description(it.value()); result.rows.push_back(std::move(row));
  }
  if (end < value.size()) { result.next_offset = end; }
  return result;
}

AnalysisJsonText AnalysisResultInspection::scalar_text(const AnalysisJsonPath &path) const
{
  const auto &value = resolve(path);
  require(!value.is_object() && !value.is_array(), "Analysis result scalar text requires a primitive value");
  return split_text(io::python_json_dumps(value, true, true), true);
}

AnalysisJsonText AnalysisResultInspection::path_text(const AnalysisJsonPath &path) const
{
  (void)resolve(path);
  std::string pointer;
  for (const auto &component : path) {
    pointer += '/';
    if (const auto *key = std::get_if<std::string>(&component)) {
      for (const char c : *key) {
        if (c == '~') { pointer += "~0"; }
        else if (c == '/') { pointer += "~1"; }
        else { pointer += c; }
      }
    }
    else { pointer += std::to_string(std::get<size_t>(component)); }
  }
  return split_text(pointer, false);
}
} // namespace stk::app
