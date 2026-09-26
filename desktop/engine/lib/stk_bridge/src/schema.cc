/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/bridge/schema.hh"

#include <stdexcept>

namespace stk::bridge {

namespace {

#include "desktop_bridge_schema.inc"

std::string unescape_token(std::string token)
{
  std::string out;
  for (size_t i = 0; i < token.size(); i++) {
    if (token[i] == '~' && i + 1 < token.size()) {
      out += token[i + 1] == '1' ? '/' : '~';
      i++;
    }
    else {
      out += token[i];
    }
  }
  return out;
}

const Json &pointer(const Json &document, const std::string &ref)
{
  if (ref.rfind("#/", 0) != 0) {
    throw std::runtime_error("only local $ref is supported, got '" + ref + "'");
  }
  const Json *node = &document;
  size_t start = 2;
  while (start <= ref.size()) {
    size_t end = ref.find('/', start);
    if (end == std::string::npos) {
      end = ref.size();
    }
    const std::string key = unescape_token(ref.substr(start, end - start));
    if (!node->is_object() || !node->contains(key)) {
      throw std::runtime_error("unresolvable $ref '" + ref + "'");
    }
    node = &(*node)[key];
    start = end + 1;
  }
  return *node;
}

Json inline_node(const Json &node, const Json &document, const int depth)
{
  if (depth > 64) {
    throw std::runtime_error("the schema's $ref chain is too deep (recursive?)");
  }
  if (node.is_object()) {
    if (node.contains("$ref") && node["$ref"].is_string()) {
      Json target = inline_node(pointer(document, node["$ref"].get<std::string>()), document, depth + 1);
      Json rest = Json::object();
      for (auto it = node.begin(); it != node.end(); ++it) {
        if (it.key() != "$ref") {
          rest[it.key()] = inline_node(it.value(), document, depth + 1);
        }
      }
      if (rest.empty()) {
        return target;
      }
      Json all = Json::object();
      all["allOf"] = Json::array({std::move(target), std::move(rest)});
      return all;
    }
    Json out = Json::object();
    for (auto it = node.begin(); it != node.end(); ++it) {
      if (it.key() == "$defs" || it.key() == "$schema" || it.key() == "$id") {
        continue;
      }
      out[it.key()] = inline_node(it.value(), document, depth + 1);
    }
    return out;
  }
  if (node.is_array()) {
    Json out = Json::array();
    for (const Json &item : node) {
      out.push_back(inline_node(item, document, depth + 1));
    }
    return out;
  }
  return node;
}

std::string method_ref(std::string_view method, const char *part)
{
  std::string escaped;
  for (const char c : method) {
    if (c == '~') {
      escaped += "~0";
    }
    else if (c == '/') {
      escaped += "~1";
    }
    else {
      escaped += c;
    }
  }
  return "#/$defs/methods/" + escaped + "/" + part;
}

}  // namespace

Json inline_schema_refs(const Json &node, const Json &document)
{
  return inline_node(node, document, 0);
}

const ProtocolSchema &ProtocolSchema::embedded()
{
  static const ProtocolSchema schema(io::parse_json(
      std::string_view(reinterpret_cast<const char *>(desktop_bridge_schema), desktop_bridge_schema_size)));
  return schema;
}

ProtocolSchema::ProtocolSchema(Json document) : document_(std::move(document)) {}

std::vector<std::string> ProtocolSchema::method_names() const
{
  std::vector<std::string> names;
  for (auto it = document_["$defs"]["methods"].begin(); it != document_["$defs"]["methods"].end(); ++it) {
    names.push_back(it.key());
  }
  return names;
}

std::vector<std::string> ProtocolSchema::event_names() const
{
  std::vector<std::string> names;
  for (auto it = document_["$defs"]["events"].begin(); it != document_["$defs"]["events"].end(); ++it) {
    names.push_back(it.key());
  }
  return names;
}

bool ProtocolSchema::has_method(const std::string_view method) const
{
  return document_["$defs"]["methods"].contains(std::string(method));
}

bool ProtocolSchema::has_event(const std::string_view event) const
{
  return document_["$defs"]["events"].contains(std::string(event));
}

const Json &ProtocolSchema::resolved(const std::string &ref) const
{
  std::lock_guard lock(mutex_);
  auto it = cache_.find(ref);
  if (it == cache_.end()) {
    Json reference = Json::object();
    reference["$ref"] = ref;
    it = cache_.emplace(ref, std::make_unique<Json>(inline_schema_refs(reference, document_))).first;
  }
  return *it->second;
}

std::vector<io::SchemaIssue> ProtocolSchema::check_request(const Json &message) const
{
  std::vector<io::SchemaIssue> issues = io::check_value(message, resolved("#/$defs/request"));
  if (!issues.empty()) {
    return issues;
  }
  const std::string method = message["method"].get<std::string>();
  if (!has_method(method)) {
    return {{"/method", "unknown method '" + method + "'"}};
  }
  const Json params = message.contains("params") ? message["params"] : Json::object();
  return io::check_value(params, resolved(method_ref(method, "params")), "/params");
}

std::vector<io::SchemaIssue> ProtocolSchema::check_response(const Json &message, const std::string_view method) const
{
  std::vector<io::SchemaIssue> issues = io::check_value(message, resolved("#/$defs/response"));
  if (!issues.empty() || !message.contains("result") || method.empty() || !has_method(method)) {
    return issues;
  }
  return io::check_value(message["result"], resolved(method_ref(method, "result")), "/result");
}

std::vector<io::SchemaIssue> ProtocolSchema::check_event(const Json &message) const
{
  std::vector<io::SchemaIssue> issues = io::check_value(message, resolved("#/$defs/event"));
  if (!issues.empty()) {
    return issues;
  }
  const std::string event = message["event"].get<std::string>();
  if (!has_event(event)) {
    return {{"/event", "unknown event '" + event + "'"}};
  }
  return io::check_value(message["data"], resolved("#/$defs/events/" + event), "/data");
}

}  // namespace stk::bridge
