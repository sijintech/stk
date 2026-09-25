/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/bridge/types.hh"

#include <algorithm>
#include <stdexcept>

namespace stk::bridge {

namespace {

using io::get_bool;
using io::get_int;
using io::get_number;
using io::get_string;

const Json &member(const Json &object, const char *key)
{
  static const Json null;
  if (!object.is_object()) {
    return null;
  }
  const auto it = object.find(key);
  return it == object.end() ? null : *it;
}

std::vector<std::string> strings(const Json &array)
{
  std::vector<std::string> out;
  if (array.is_array()) {
    for (const Json &item : array) {
      if (item.is_string()) {
        out.push_back(item.get<std::string>());
      }
    }
  }
  return out;
}

Json bindings_json(const std::map<std::string, std::string> &bindings)
{
  Json out = Json::object();
  for (const auto &[name, path] : bindings) {
    out[name] = path;
  }
  return out;
}

}  // namespace

HelloInfo HelloInfo::from_json(const Json &result)
{
  HelloInfo info;
  info.raw = result;
  info.protocol = int(get_int(result, "protocol", 0));
  const Json &server = member(result, "server");
  info.server.name = get_string(server, "name");
  info.server.version = get_string(server, "version");
  info.server.python = get_string(server, "python");
  info.server.platform = get_string(server, "platform");
  info.server.pid = get_int(server, "pid", 0);
  info.methods = strings(member(result, "methods"));
  info.events = strings(member(result, "events"));
  const Json &limits = member(result, "limits");
  info.limits.max_line_bytes = get_int(limits, "max_line_bytes", info.limits.max_line_bytes);
  info.limits.max_inflight = get_int(limits, "max_inflight", info.limits.max_inflight);
  info.limits.watch_interval_s = get_number(limits, "watch_interval_s", info.limits.watch_interval_s);
  info.limits.log_chunk_bytes = get_int(limits, "log_chunk_bytes", info.limits.log_chunk_bytes);
  info.limits.transfer_chunk_bytes = get_int(limits, "transfer_chunk_bytes", info.limits.transfer_chunk_bytes);
  const Json &paths = member(result, "paths");
  info.paths.state_dir = get_string(paths, "state_dir");
  info.paths.cache_dir = get_string(paths, "cache_dir");
  info.paths.blob_dir = get_string(paths, "blob_dir");
  info.paths.download_dir = get_string(paths, "download_dir");
  info.resumed_transfers = strings(member(result, "resumed_transfers"));
  return info;
}

bool HelloInfo::has_method(const std::string_view method) const
{
  return std::find(methods.begin(), methods.end(), method) != methods.end();
}

ConnectionInfo ConnectionInfo::from_json(const Json &connection)
{
  ConnectionInfo info;
  info.raw = connection;
  info.id = get_string(connection, "id");
  info.kind = get_string(connection, "kind");
  info.name = get_string(connection, "name");
  info.url = get_string(connection, "url");
  info.device_id = get_string(connection, "device_id");
  info.profile = get_string(connection, "profile");
  info.state = get_string(connection, "state");
  return info;
}

ConnectionCheck ConnectionCheck::from_json(const Json &result)
{
  ConnectionCheck check;
  check.raw = result;
  check.id = get_string(result, "id");
  check.ok = get_bool(result, "ok", false);
  check.health = member(result, "health");
  if (member(result, "nodes").is_number_integer()) {
    check.nodes = member(result, "nodes").get<int64_t>();
  }
  if (member(result, "error").is_object()) {
    check.error = Error::from_json(member(result, "error"));
  }
  return check;
}

LocalRuntimeStatus LocalRuntimeStatus::from_json(const Json &result)
{
  LocalRuntimeStatus status;
  status.raw = result;
  status.initialized = get_bool(result, "initialized", false);
  status.api_running = get_bool(result, "api_running", false);
  status.supervisor_running = get_bool(result, "supervisor_running", false);
  status.url = get_string(result, "url");
  status.state_dir = get_string(result, "state_dir");
  status.error = get_string(result, "error");
  return status;
}

HubActionSummary HubActionSummary::from_json(const Json &action)
{
  HubActionSummary summary;
  summary.raw = action;
  summary.id = get_string(action, "id");
  summary.kind = get_string(action, "kind");
  if (summary.kind.empty()) {
    /* Hub records keep the kind in request.kind (bridges before the top-level kind). */
    summary.kind = get_string(member(action, "request"), "kind");
  }
  summary.state = get_string(action, "state");
  summary.node_id = get_string(action, "node_id");
  summary.error = get_string(action, "error");
  summary.review_reason = get_string(action, "review_reason");
  return summary;
}

HubPolicy HubPolicy::from_json(const Json &result)
{
  HubPolicy policy;
  policy.raw = result;
  const Json &p = member(result, "policy");
  policy.device_profile = get_string(p, "device_profile");
  policy.desktop_auto = get_bool(p, "desktop_auto", false);
  policy.desktop_auto_bytes = get_int(p, "desktop_auto_bytes", 0);
  policy.graph_auto_seconds = get_number(p, "graph_auto_seconds", 0.0);
  policy.uploads = get_bool(p, "uploads", false);
  policy.upload_max_bytes = get_int(p, "upload_max_bytes", 0);
  policy.upload_chunk_bytes = get_int(p, "upload_chunk_bytes", 0);
  policy.upload_quota_bytes = get_int(p, "upload_quota_bytes", 0);
  policy.import_max_files = get_int(p, "import_max_files", 0);
  policy.import_request_bytes = get_int(p, "import_request_bytes", 0);
  policy.action_request_bytes = get_int(p, "action_request_bytes", 0);
  policy.read_kinds = strings(member(p, "read_kinds"));
  policy.review_policy = get_string(p, "review_policy");
  return policy;
}

CancelResult CancelResult::from_json(const Json &result)
{
  CancelResult out;
  out.raw = result;
  out.cancelled = get_bool(result, "cancelled", false);
  if (member(result, "action").is_object()) {
    out.action = HubActionSummary::from_json(member(result, "action"));
  }
  if (member(result, "error").is_object()) {
    out.error = Error::from_json(member(result, "error"));
  }
  return out;
}

FileEntry FileEntry::from_json(const Json &file)
{
  FileEntry entry;
  entry.path = get_string(file, "path");
  entry.size = get_int(file, "size", 0);
  entry.sha256 = get_string(file, "sha256");
  entry.media_type = get_string(file, "media_type");
  return entry;
}

Transfer Transfer::from_json(const Json &transfer)
{
  Transfer t;
  t.raw = transfer;
  t.id = get_string(transfer, "id");
  t.kind = get_string(transfer, "kind");
  t.state = get_string(transfer, "state");
  t.connection = get_string(transfer, "connection");
  t.node = get_string(transfer, "node");
  t.workspace_id = get_string(transfer, "workspace_id");
  t.task_id = get_string(transfer, "task_id");
  t.local = get_string(transfer, "local");
  t.remote = get_string(transfer, "remote");
  t.current = get_string(transfer, "current");
  t.sha256 = get_string(transfer, "sha256");
  t.bytes_done = get_int(transfer, "bytes_done", 0);
  t.bytes_total = get_int(transfer, "bytes_total", 0);
  t.files_done = get_int(transfer, "files_done", 0);
  t.files_total = get_int(transfer, "files_total", 0);
  if (member(transfer, "error").is_object()) {
    t.error = Error::from_json(member(transfer, "error"));
  }
  if (member(transfer, "action").is_object()) {
    t.action = HubActionSummary::from_json(member(transfer, "action"));
  }
  t.created_at = get_string(transfer, "created_at");
  t.updated_at = get_string(transfer, "updated_at");
  return t;
}

BlobEnsureResult BlobEnsureResult::from_json(const Json &result)
{
  BlobEnsureResult out;
  out.raw = result;
  const Json &blobs = member(result, "blobs");
  if (blobs.is_object()) {
    for (auto it = blobs.begin(); it != blobs.end(); ++it) {
      out.blobs[it.key()] = {get_string(it.value(), "path"), get_int(it.value(), "size", 0)};
    }
  }
  out.missing = strings(member(result, "missing"));
  out.blob_dir = get_string(result, "blob_dir");
  return out;
}

ColormapList ColormapList::from_json(const Json &result)
{
  ColormapList out;
  out.raw = result;
  const Json &maps = member(result, "colormaps");
  if (maps.is_array()) {
    for (const Json &entry : maps) {
      Colormap map;
      map.name = get_string(entry, "name");
      const std::optional<std::vector<uint8_t>> lut = decode_base64(get_string(entry, "lut_rgba8"));
      if (!lut || lut->size() != map.lut_rgba8.size()) {
        throw std::runtime_error("colormap '" + map.name + "' has no 256 x RGBA8 LUT");
      }
      std::copy(lut->begin(), lut->end(), map.lut_rgba8.begin());
      out.colormaps.push_back(std::move(map));
    }
  }
  out.aliases = member(result, "aliases");
  out.categorical_palettes = member(result, "categorical_palettes");
  out.reserved_colors = member(result, "reserved_colors");
  out.nan_color = member(result, "nan_color");
  return out;
}

EvaluateResult EvaluateResult::from_json(const Json &result)
{
  EvaluateResult out;
  out.raw = result;
  out.result = member(result, "result");
  out.blob_dir = get_string(result, "blob_dir");
  if (member(result, "action").is_object()) {
    out.action = HubActionSummary::from_json(member(result, "action"));
  }
  return out;
}

io::GraphResult EvaluateResult::graph_result() const
{
  if (!result.is_object()) {
    throw std::runtime_error("the evaluation has no result (a hub action awaits review)");
  }
  return io::GraphResult::from_json(result);
}

void Target::apply(Json &params) const
{
  params["connection"] = connection;
  if (!node.empty()) {
    params["node"] = node;
  }
}

Json AddRuntimeParams::to_json() const
{
  Json p = Json::object();
  p["name"] = name;
  p["url"] = url;
  if (!token.empty()) {
    p["token"] = token;
  }
  if (!token_file.empty()) {
    p["token_file"] = token_file;
  }
  if (!check) {
    p["check"] = false;
  }
  return p;
}

Json PairHubParams::to_json() const
{
  Json p = Json::object();
  p["name"] = name;
  p["url"] = url;
  p["code"] = code;
  if (!device_name.empty()) {
    p["device_name"] = device_name;
  }
  return p;
}

Json TaskSubmitParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  p["idempotency_key"] = idempotency_key;
  if (!spec.is_null()) {
    p["spec"] = spec;
  }
  if (!template_name.empty()) {
    p["template"] = template_name;
  }
  if (!workspace_id.empty()) {
    p["workspace_id"] = workspace_id;
  }
  return p;
}

Json UploadParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  p["workspace_id"] = workspace_id;
  p["source"] = source;
  if (!remote.empty()) {
    p["remote"] = remote;
  }
  if (!idempotency_key.empty()) {
    p["idempotency_key"] = idempotency_key;
  }
  return p;
}

Json DownloadParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  if (!task_id.empty()) {
    p["task_id"] = task_id;
  }
  if (!workspace_id.empty()) {
    p["workspace_id"] = workspace_id;
  }
  p["path"] = path;
  if (!dest.empty()) {
    p["dest"] = dest;
  }
  if (!idempotency_key.empty()) {
    p["idempotency_key"] = idempotency_key;
  }
  return p;
}

Json WatchParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  if (!workspace_id.empty()) {
    p["workspace_id"] = workspace_id;
  }
  if (!task_ids.empty()) {
    p["task_ids"] = task_ids;
  }
  if (interval) {
    p["interval"] = *interval;
  }
  return p;
}

Json LogsParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  p["task_id"] = task_id;
  if (!streams.empty()) {
    p["streams"] = streams;
  }
  if (!offsets.empty()) {
    Json o = Json::object();
    for (const auto &[stream, offset] : offsets) {
      o[stream] = offset;
    }
    p["offsets"] = o;
  }
  if (chunk_bytes) {
    p["chunk_bytes"] = *chunk_bytes;
  }
  return p;
}

Json EventsParams::to_json() const
{
  Json p = Json::object();
  target.apply(p);
  p["task_id"] = task_id;
  if (offset > 0) {
    p["offset"] = offset;
  }
  return p;
}

Json HubSubscribeParams::to_json() const
{
  Json p = Json::object();
  p["connection"] = connection;
  if (after > 0) {
    p["after"] = after;
  }
  return p;
}

Json EvaluateParams::to_json() const
{
  Json p = Json::object();
  p["eval_id"] = eval_id;
  p["request"] = request;
  if (!mode.empty() && mode != "local") {
    p["mode"] = mode;
  }
  if (!local_bindings.empty()) {
    p["local_bindings"] = bindings_json(local_bindings);
  }
  if (!target.connection.empty()) {
    target.apply(p);
  }
  if (wait) {
    p["wait"] = *wait;
  }
  return p;
}

Json ProbeParams::to_json() const
{
  Json p = Json::object();
  if (!graph.is_null()) {
    p["graph"] = graph;
  }
  if (!preset.empty()) {
    p["preset"] = preset;
  }
  Json pick = Json::object();
  pick["node"] = node;
  if (!dataset.empty()) {
    pick["dataset"] = dataset;
  }
  p["pick"] = pick;
  if (!context.is_null()) {
    p["context"] = context;
  }
  if (!local_bindings.empty()) {
    p["local_bindings"] = bindings_json(local_bindings);
  }
  if (!target.connection.empty()) {
    target.apply(p);
  }
  if (position) {
    p["position"] = Json::array({(*position)[0], (*position)[1], (*position)[2]});
  }
  return p;
}

std::optional<std::vector<uint8_t>> decode_base64(const std::string_view text)
{
  const auto value = [](const char c) -> int {
    if (c >= 'A' && c <= 'Z') {
      return c - 'A';
    }
    if (c >= 'a' && c <= 'z') {
      return c - 'a' + 26;
    }
    if (c >= '0' && c <= '9') {
      return c - '0' + 52;
    }
    if (c == '+') {
      return 62;
    }
    if (c == '/') {
      return 63;
    }
    return -1;
  };
  std::string_view body = text;
  while (!body.empty() && body.back() == '=') {
    body.remove_suffix(1);
  }
  if (text.size() - body.size() > 2 || body.size() % 4 == 1) {
    return std::nullopt;
  }
  std::vector<uint8_t> out;
  out.reserve(body.size() * 3 / 4);
  uint32_t buffer = 0;
  int bits = 0;
  for (const char c : body) {
    const int v = value(c);
    if (v < 0) {
      return std::nullopt;
    }
    buffer = (buffer << 6) | uint32_t(v);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push_back(uint8_t((buffer >> bits) & 0xFF));
    }
  }
  return out;
}

}  // namespace stk::bridge
