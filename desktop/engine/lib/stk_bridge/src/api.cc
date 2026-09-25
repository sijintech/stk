/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Typed wrappers of the protocol-1 methods (client.hh). */

#include "stk/bridge/client.hh"

namespace stk::bridge {

namespace {

Json object(std::initializer_list<std::pair<const char *, Json>> members)
{
  Json out = Json::object();
  for (const auto &[key, value] : members) {
    out[key] = value;
  }
  return out;
}

Json with_target(const Target &target, Json params = Json::object())
{
  target.apply(params);
  return params;
}

const Json &field(const Json &result, const char *key)
{
  static const Json null;
  const auto it = result.find(key);
  return it == result.end() ? null : *it;
}

template<typename T> std::vector<T> list_of(const Json &array, T (*convert)(const Json &))
{
  std::vector<T> out;
  if (array.is_array()) {
    for (const Json &item : array) {
      out.push_back(convert(item));
    }
  }
  return out;
}

Submitted submitted(const Json &result, const char *object_key)
{
  Submitted out;
  out.raw = result;
  out.object = field(result, object_key);
  if (field(result, "action").is_object()) {
    out.action = HubActionSummary::from_json(field(result, "action"));
  }
  return out;
}

}  // namespace

Future<Json> Client::shutdown_bridge()
{
  CallOptions options;
  options.retry = CallOptions::Retry::Never;
  return call("shutdown", Json::object(), options);
}

/* -- Connections -------------------------------------------------------------------------- */

Future<std::vector<ConnectionInfo>> Client::connections_list()
{
  return call("connections.list").map([](const Json &r) {
    return list_of<ConnectionInfo>(field(r, "connections"), &ConnectionInfo::from_json);
  });
}

Future<ConnectionInfo> Client::connections_add_runtime(const AddRuntimeParams &params)
{
  return call("connections.add_runtime", params.to_json()).map([](const Json &r) {
    return ConnectionInfo::from_json(field(r, "connection"));
  });
}

Future<Json> Client::connections_remove(const std::string &id)
{
  return call("connections.remove", object({{"id", id}}));
}

Future<ConnectionCheck> Client::connections_check(const std::string &id)
{
  return call("connections.check", object({{"id", id}})).map([](const Json &r) {
    return ConnectionCheck::from_json(r);
  });
}

Future<ConnectionInfo> Client::connections_pair_hub(const PairHubParams &params)
{
  /* One-time code: never repeated by the client. */
  CallOptions options;
  options.retry = CallOptions::Retry::Never;
  return call("connections.pair_hub", params.to_json(), options).map([](const Json &r) {
    return ConnectionInfo::from_json(field(r, "connection"));
  });
}

Future<LocalRuntimeStatus> Client::connections_local()
{
  return call("connections.local").map([](const Json &r) { return LocalRuntimeStatus::from_json(r); });
}

Future<LocalRuntimeStatus> Client::connections_local_start()
{
  return call("connections.local_start").map([](const Json &r) { return LocalRuntimeStatus::from_json(r); });
}

/* -- Hub ---------------------------------------------------------------------------------- */

Future<Json> Client::hub_devices(const std::string &connection)
{
  return call("hub.devices", object({{"connection", connection}}));
}

Future<Json> Client::hub_templates(const std::string &connection)
{
  return call("hub.templates", object({{"connection", connection}}));
}

Future<Json> Client::hub_actions(const std::string &connection)
{
  return call("hub.actions", object({{"connection", connection}}));
}

Future<Json> Client::hub_action(const std::string &connection, const std::string &action_id)
{
  return call("hub.action", object({{"connection", connection}, {"action_id", action_id}}));
}

Future<Json> Client::hub_review(const std::string &connection, const std::string &action_id, const bool approved)
{
  return call("hub.review", object({{"connection", connection}, {"action_id", action_id}, {"approved", approved}}));
}

Future<HubPolicy> Client::hub_policy(const std::string &connection)
{
  return call("hub.policy", object({{"connection", connection}})).map([](const Json &r) {
    return HubPolicy::from_json(r);
  });
}


/* -- Workspaces and tasks -------------------------------------------------------------------- */

Future<Json> Client::workspace_list(const Target &target)
{
  return call("workspace.list", with_target(target));
}

Future<Submitted> Client::workspace_create(const Target &target, const std::string &name,
                                           const std::string &idempotency_key)
{
  Json params = with_target(target);
  params["name"] = name;
  if (!idempotency_key.empty()) {
    params["idempotency_key"] = idempotency_key;
  }
  return call("workspace.create", params).map([](const Json &r) { return submitted(r, "workspace"); });
}

Future<std::vector<FileEntry>> Client::workspace_files(const Target &target, const std::string &workspace_id)
{
  Json params = with_target(target);
  params["workspace_id"] = workspace_id;
  return call("workspace.files", params).map([](const Json &r) {
    return list_of<FileEntry>(field(r, "files"), &FileEntry::from_json);
  });
}

Future<Submitted> Client::task_submit(const TaskSubmitParams &params)
{
  return call("task.submit", params.to_json()).map([](const Json &r) { return submitted(r, "task"); });
}

Future<Json> Client::task_list(const Target &target, const std::string &workspace_id)
{
  Json params = with_target(target);
  if (!workspace_id.empty()) {
    params["workspace_id"] = workspace_id;
  }
  return call("task.list", params);
}

Future<Json> Client::task_get(const Target &target, const std::string &task_id)
{
  Json params = with_target(target);
  params["task_id"] = task_id;
  return call("task.get", params);
}

Future<Submitted> Client::task_cancel(const Target &target, const std::string &task_id,
                                      const std::string &idempotency_key)
{
  Json params = with_target(target);
  params["task_id"] = task_id;
  if (!idempotency_key.empty()) {
    params["idempotency_key"] = idempotency_key;
  }
  return call("task.cancel", params).map([](const Json &r) { return submitted(r, "task"); });
}

Future<std::vector<FileEntry>> Client::task_artifacts(const Target &target, const std::string &task_id)
{
  Json params = with_target(target);
  params["task_id"] = task_id;
  return call("task.artifacts", params).map([](const Json &r) {
    return list_of<FileEntry>(field(r, "artifacts"), &FileEntry::from_json);
  });
}




/* -- Transfers ------------------------------------------------------------------------------ */

namespace {
Transfer transfer_of(const Json &r)
{
  return Transfer::from_json(field(r, "transfer"));
}
}  // namespace

Future<Transfer> Client::upload_start(const UploadParams &params)
{
  return call("upload.start", params.to_json()).map(&transfer_of);
}

Future<Transfer> Client::download_start(const DownloadParams &params)
{
  return call("download.start", params.to_json()).map(&transfer_of);
}

Future<std::vector<Transfer>> Client::transfer_list()
{
  return call("transfer.list").map([](const Json &r) {
    return list_of<Transfer>(field(r, "transfers"), &Transfer::from_json);
  });
}

Future<Transfer> Client::transfer_get(const std::string &id)
{
  return call("transfer.get", object({{"id", id}})).map(&transfer_of);
}

Future<Transfer> Client::transfer_resume(const std::string &id)
{
  return call("transfer.resume", object({{"id", id}})).map(&transfer_of);
}

Future<Transfer> Client::transfer_cancel(const std::string &id)
{
  return call("transfer.cancel", object({{"id", id}})).map(&transfer_of);
}

Future<BlobEnsureResult> Client::blob_ensure(const std::vector<std::string> &sha256, const std::string &connection)
{
  Json params = object({{"sha256", sha256}});
  if (!connection.empty()) {
    params["connection"] = connection;
  }
  return call("blob.ensure", params).map([](const Json &r) { return BlobEnsureResult::from_json(r); });
}

/* -- Graphs, probes, colormaps ----------------------------------------------------------------- */

Future<Json> Client::graph_catalog()
{
  return call("graph.catalog");
}

Future<Json> Client::graph_presets()
{
  return call("graph.presets");
}

Future<Json> Client::graph_validate(const Json &graph, const Json &parameters)
{
  Json params = object({{"graph", graph}});
  if (!parameters.is_null()) {
    params["parameters"] = parameters;
  }
  return call("graph.validate", params);
}

Future<CancelResult> Client::graph_cancel(const std::string &eval_id, const Target &target)
{
  Json params = object({{"eval_id", eval_id}});
  if (!target.connection.empty()) {
    target.apply(params);
  }
  return call("graph.cancel", params).map([](const Json &r) { return CancelResult::from_json(r); });
}

Future<Json> Client::probe(const ProbeParams &params)
{
  return call("probe", params.to_json());
}

Future<ColormapList> Client::colormaps_list()
{
  return call("colormaps.list").map([](const Json &r) { return ColormapList::from_json(r); });
}

}  // namespace stk::bridge
