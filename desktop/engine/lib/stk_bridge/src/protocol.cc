/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/bridge/protocol.hh"

#include <array>
#include <cmath>
#include <set>
#include <vector>

#include "stk/core/utf8.hh"

namespace stk::bridge {

namespace {

struct CodeInfo {
  ErrorCode code;
  std::string_view name;
  bool retryable;
};

constexpr std::array<CodeInfo, 20> kCodes = {{
    {ErrorCode::ParseError, "parse_error", false},
    {ErrorCode::LineTooLong, "line_too_long", false},
    {ErrorCode::InvalidRequest, "invalid_request", false},
    {ErrorCode::UnknownMethod, "unknown_method", false},
    {ErrorCode::InvalidParams, "invalid_params", false},
    {ErrorCode::Unsupported, "unsupported", false},
    {ErrorCode::NotFound, "not_found", false},
    {ErrorCode::Unauthorized, "unauthorized", false},
    {ErrorCode::Unavailable, "unavailable", true},
    {ErrorCode::Conflict, "conflict", false},
    {ErrorCode::ReviewNotInspected, "review_not_inspected", false},
    {ErrorCode::RemoteError, "remote_error", false},
    {ErrorCode::ChecksumMismatch, "checksum_mismatch", true},
    {ErrorCode::GraphError, "graph_error", false},
    {ErrorCode::Cancelled, "cancelled", false},
    {ErrorCode::Timeout, "timeout", true},
    {ErrorCode::Busy, "busy", true},
    {ErrorCode::ResultTooLarge, "result_too_large", false},
    {ErrorCode::ShuttingDown, "shutting_down", false},
    {ErrorCode::InternalError, "internal_error", false},
}};

bool has_non_finite(const Json &value)
{
  switch (value.type()) {
    case Json::value_t::number_float:
      return !std::isfinite(value.get<double>());
    case Json::value_t::array:
    case Json::value_t::object:
      for (const auto &item : value) {
        if (has_non_finite(item)) {
          return true;
        }
      }
      return false;
    default:
      return false;
  }
}

bool valid_id(const Json &id)
{
  if (id.is_number_unsigned()) {
    return id.get<uint64_t>() <= (uint64_t(1) << 53) - 1;
  }
  if (id.is_number_integer()) {
    const int64_t v = id.get<int64_t>();
    return v >= 0 && v <= (int64_t(1) << 53) - 1;
  }
  if (id.is_string()) {
    const size_t n = core::utf8::count_code_points(id.get_ref<const std::string &>());
    return n >= 1 && n <= 128;
  }
  return false;
}

}  // namespace

std::string_view error_code_name(const ErrorCode code)
{
  for (const CodeInfo &info : kCodes) {
    if (info.code == code) {
      return info.name;
    }
  }
  return "unknown";
}

ErrorCode error_code_from_name(const std::string_view name)
{
  for (const CodeInfo &info : kCodes) {
    if (info.name == name) {
      return info.code;
    }
  }
  return ErrorCode::Unknown;
}

bool error_code_retryable(const ErrorCode code)
{
  for (const CodeInfo &info : kCodes) {
    if (info.code == code) {
      return info.retryable;
    }
  }
  return false;
}

Error Error::make(const ErrorCode code, std::string message, const bool local, Json data)
{
  Error error;
  error.code = code;
  error.name = std::string(error_code_name(code));
  error.message = std::move(message);
  error.retryable = error_code_retryable(code);
  error.data = std::move(data);
  error.local = local;
  return error;
}

Error Error::from_json(const Json &error)
{
  Error result;
  result.name = io::get_string(error, "code", "internal_error");
  result.code = error_code_from_name(result.name);
  result.message = io::get_string(error, "message");
  result.retryable = io::get_bool(error, "retryable", error_code_retryable(result.code));
  if (error.is_object()) {
    const auto it = error.find("data");
    if (it != error.end()) {
      result.data = *it;
    }
  }
  return result;
}

Json Error::to_json() const
{
  Json out = Json::object();
  out["code"] = name.empty() ? std::string(error_code_name(code)) : name;
  out["message"] = message;
  out["retryable"] = retryable;
  if (!data.is_null()) {
    out["data"] = data;
  }
  return out;
}

std::string Error::describe() const
{
  return (name.empty() ? std::string(error_code_name(code)) : name) + ": " + message;
}

BridgeException::BridgeException(Error error) : std::runtime_error(error.describe()), error_(std::move(error)) {}

Json decode_line(std::string_view line)
{
  if (!line.empty() && line.back() == '\r') {
    line.remove_suffix(1);
  }
  const size_t bad = core::utf8::first_invalid(line);
  if (bad != line.size()) {
    throw ProtocolError("the line is not valid UTF-8 (byte " + std::to_string(bad) + ")");
  }
  /* Duplicate keys: one key set per open object. */
  std::vector<std::set<std::string>> keys;
  std::string duplicate;
  const auto callback = [&](int /*depth*/, nlohmann::json::parse_event_t event, Json &parsed) {
    switch (event) {
      case nlohmann::json::parse_event_t::object_start:
        keys.emplace_back();
        break;
      case nlohmann::json::parse_event_t::object_end:
        if (!keys.empty()) {
          keys.pop_back();
        }
        break;
      case nlohmann::json::parse_event_t::key:
        if (!keys.empty() && parsed.is_string() && !keys.back().insert(parsed.get<std::string>()).second &&
            duplicate.empty())
        {
          duplicate = parsed.get<std::string>();
        }
        break;
      default:
        break;
    }
    return true;
  };
  Json message;
  try {
    message = Json::parse(line.begin(), line.end(), callback);
  }
  catch (const nlohmann::json::exception &error) {
    throw ProtocolError(std::string("the line is not strict JSON: ") + error.what());
  }
  if (!duplicate.empty()) {
    throw ProtocolError("the line is not strict JSON: duplicate key \"" + duplicate + "\"");
  }
  if (!message.is_object()) {
    throw ProtocolError("a protocol message must be a JSON object");
  }
  return message;
}

std::string encode_line(const Json &message)
{
  if (has_non_finite(message)) {
    throw ProtocolError("the message holds a non-finite number (protocol JSON is strict)");
  }
  std::string line;
  try {
    line = message.dump(-1, ' ', false, nlohmann::json::error_handler_t::strict);
  }
  catch (const nlohmann::json::exception &error) {
    throw ProtocolError(std::string("the message is not valid UTF-8 JSON: ") + error.what());
  }
  line.push_back('\n');
  return line;
}

MessageKind classify_message(const Json &message, std::string *why)
{
  const auto fail = [&](const char *reason) {
    if (why) {
      *why = reason;
    }
    return MessageKind::Invalid;
  };
  if (!message.is_object()) {
    return fail("not an object");
  }
  if (message.contains("event")) {
    const auto event = message.find("event");
    const auto data = message.find("data");
    if (!event->is_string() || data == message.end() || !data->is_object() || message.size() != 2) {
      return fail("an event needs exactly a string 'event' and an object 'data'");
    }
    return MessageKind::Event;
  }
  const auto id = message.find("id");
  if (id == message.end()) {
    return fail("neither 'event' nor 'id'");
  }
  const bool has_result = message.contains("result");
  const bool has_error = message.contains("error");
  if (has_result == has_error || message.size() != 2) {
    return fail("a response needs 'id' and exactly one of 'result' / 'error'");
  }
  if (has_result && !message["result"].is_object()) {
    return fail("'result' must be an object");
  }
  if (has_error && !message["error"].is_object()) {
    return fail("'error' must be an object");
  }
  if (!(id->is_null() && has_error) && !valid_id(*id)) {
    return fail("invalid response id");
  }
  return MessageKind::Response;
}

void LineSplitter::feed(std::string_view data,
                        const std::function<void(std::string_view)> &on_line,
                        const std::function<void(size_t)> &on_oversize)
{
  while (!data.empty()) {
    const size_t newline = data.find('\n');
    const std::string_view part = data.substr(0, newline);
    if (discarding_) {
      discarded_ += part.size();
    }
    else if (buffer_.size() + part.size() > max_) {
      discarding_ = true;
      discarded_ = buffer_.size() + part.size();
      buffer_.clear();
      buffer_.shrink_to_fit();
    }
    else {
      buffer_.append(part);
    }
    if (newline == std::string_view::npos) {
      return;
    }
    data.remove_prefix(newline + 1);
    if (discarding_) {
      if (on_oversize) {
        on_oversize(discarded_);
      }
      discarding_ = false;
      discarded_ = 0;
      continue;
    }
    if (on_line) {
      on_line(buffer_);
    }
    buffer_.clear();
  }
}

void LineSplitter::reset()
{
  buffer_.clear();
  discarding_ = false;
  discarded_ = 0;
}

bool method_is_subscribe(const std::string_view method)
{
  return method == "watch" || method == "logs.subscribe" || method == "events.subscribe" ||
         method == "hub.subscribe";
}

bool method_is_retry_safe(const std::string_view method, const Json &params)
{
  /* Reads: repeating them has no effect beyond the answer. hub.action also marks the action
   * "inspected" in the bridge, which a repeat does again. */
  static const std::set<std::string_view> reads = {
      "hello",           "connections.list", "connections.check", "connections.local",
      "workspace.list",  "workspace.files",  "task.list",         "task.get",
      "task.artifacts",  "hub.devices",      "hub.templates",     "hub.actions",
      "hub.action",      "hub.policy",       "transfer.list",     "transfer.get",      "graph.catalog",
      "graph.presets",   "graph.validate",   "blob.ensure",       "probe",
      "colormaps.list",
  };
  if (reads.count(method)) {
    return true;
  }
  /* Creating operations: the key names the same task / workspace / hub action again. */
  if (method == "task.submit") {
    return true; /* idempotency_key is required */
  }
  if (method == "workspace.create" || method == "task.cancel") {
    return params.is_object() && params.contains("idempotency_key");
  }
  /* Hub evaluations are hub actions named by eval_id: a repeat waits for the same action. A local
   * evaluation died with the bridge (and may be what killed it): it is not repeated. */
  if (method == "graph.evaluate") {
    return params.is_object() && io::get_string(params, "mode", "local") == "hub";
  }
  return false;
}

}  // namespace stk::bridge
