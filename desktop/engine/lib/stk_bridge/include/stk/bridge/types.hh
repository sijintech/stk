/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * Typed params and results of the protocol-1 methods and events the desktop app (D1) uses.
 * Results keep the full message in `raw`: results and event data are open (§3), so fields a
 * newer bridge adds are never lost, and rich Runtime objects (tasks, workspaces, templates)
 * stay JSON for the UI models that own them.
 */
#pragma once

#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "stk/bridge/protocol.hh"
#include "stk/io/result.hh"

namespace stk::bridge {

/* -------------------------------------------------------------------------------------------- */
/* Results */

struct HelloInfo {
  int protocol = 0;
  struct Server {
    std::string name, version, python, platform;
    int64_t pid = 0;
  } server;
  std::vector<std::string> methods, events;
  struct Limits {
    int64_t max_line_bytes = int64_t(kDefaultMaxLineBytes);
    int64_t max_inflight = 64;
    double watch_interval_s = 2.0;
    int64_t log_chunk_bytes = 256 * 1024;
    int64_t transfer_chunk_bytes = 1024 * 1024;
  } limits;
  struct Paths {
    std::string state_dir, cache_dir, blob_dir, download_dir;
  } paths;
  std::vector<std::string> resumed_transfers;
  Json raw;

  static HelloInfo from_json(const Json &result);
  /** The bridge implements `method` (a newer app talking to an older bridge checks this). */
  bool has_method(std::string_view method) const;
};

struct ConnectionInfo {
  std::string id;   /* "local", "runtime:<name>", "hub:<name>" */
  std::string kind; /* local | runtime | hub */
  std::string name;
  std::string url; /* empty when null */
  std::string device_id;
  /** "desktop" for a hub device paired with a desktop code (WP11), else empty. */
  std::string profile;
  Json raw;
  static ConnectionInfo from_json(const Json &connection);
};

struct ConnectionCheck {
  std::string id;
  bool ok = false;
  Json health;                    /* null when absent */
  std::optional<int64_t> nodes;   /* hub connections */
  std::optional<Error> error;     /* ok == false */
  Json raw;
  static ConnectionCheck from_json(const Json &result);
};

struct LocalRuntimeStatus {
  bool initialized = false, api_running = false, supervisor_running = false;
  std::string url, state_dir, error;
  Json raw;
  static LocalRuntimeStatus from_json(const Json &result);
};

struct HubActionSummary {
  std::string id, kind, state, node_id, error, review_reason;
  Json raw;
  static HubActionSummary from_json(const Json &action);
  bool in_review() const
  {
    return state == "review";
  }
};

/** hub.policy (WP11): the hub's limits for this device. */
struct HubPolicy {
  std::string device_profile; /* "desktop" for a desktop device */
  bool desktop_auto = false;
  int64_t desktop_auto_bytes = 0; /* expected-transfer cap for automatic desktop runs */
  double graph_auto_seconds = 0.0;
  bool uploads = false;
  int64_t upload_max_bytes = 0, upload_chunk_bytes = 0, upload_quota_bytes = 0;
  int64_t import_max_files = 0, import_request_bytes = 0, action_request_bytes = 0;
  std::vector<std::string> read_kinds;
  std::string review_policy; /* any | not-self | owner */
  Json raw;
  static HubPolicy from_json(const Json &result);
};

/** graph.cancel: whether the evaluation stopped (or will), and the hub side (WP11). */
struct CancelResult {
  bool cancelled = false;
  std::optional<HubActionSummary> action;
  std::optional<Error> error;
  Json raw;
  static CancelResult from_json(const Json &result);
};

/** task.submit / task.cancel / workspace.create: the Runtime object and/or the hub action. */
struct Submitted {
  Json object; /* result.task or result.workspace (null through a hub action still in review) */
  std::optional<HubActionSummary> action;
  Json raw;
};

struct FileEntry {
  std::string path, sha256, media_type;
  int64_t size = 0;
  static FileEntry from_json(const Json &file);
};

struct Transfer {
  std::string id, kind, state, connection, node, workspace_id, task_id, local, remote, current, sha256;
  int64_t bytes_done = 0, bytes_total = 0, files_done = 0, files_total = 0;
  std::optional<Error> error;
  /** The hub `workspace.import` of an upload through a hub (WP11); in review until approved. */
  std::optional<HubActionSummary> action;
  std::string created_at, updated_at;
  Json raw;
  static Transfer from_json(const Json &transfer);
  bool finished() const
  {
    return state == "completed" || state == "failed" || state == "cancelled";
  }
};

struct BlobEnsureResult {
  struct Blob {
    std::string path;
    int64_t size = 0;
  };
  std::map<std::string, Blob> blobs;
  std::vector<std::string> missing;
  std::string blob_dir;
  Json raw;
  static BlobEnsureResult from_json(const Json &result);
};

struct Colormap {
  std::string name;
  /** 256 x RGBA8 (stk-render-payload-v2 §5), decoded from base64. */
  std::array<uint8_t, 1024> lut_rgba8{};
};

struct ColormapList {
  std::vector<Colormap> colormaps;
  Json aliases, categorical_palettes, reserved_colors, nan_color;
  Json raw;
  /** Throws std::runtime_error when a LUT is not 1024 bytes of valid base64. */
  static ColormapList from_json(const Json &result);
};

struct EvaluateResult {
  /** stk.graph-result/1; null when a hub action waits for review. */
  Json result;
  std::string blob_dir;
  std::optional<HubActionSummary> action;
  Json raw;
  static EvaluateResult from_json(const Json &result);
  /** The parsed result (throws when `result` is null). */
  io::GraphResult graph_result() const;
};

/* -------------------------------------------------------------------------------------------- */
/* Events */

struct LogChunk {
  std::string stream, text;
  int64_t offset = 0, next_offset = 0;
};
struct LogsEnd {
  std::map<std::string, int64_t> offsets;
};
struct EventsBatch {
  Json events, invalid;
  int64_t offset = 0, next_offset = 0;
};
struct EventsEnd {
  int64_t next_offset = 0;
};
struct WatchSnapshot {
  Json tasks;
  double time = 0.0;
};
struct HubEvent {
  int64_t cursor = 0;
  std::string kind;
  Json payload;
};
struct GraphProgress {
  std::string eval_id;
  Json event; /* {type: node.started | node.cached | node.finished | node.failed | progress | warning, ...} */
};

/* -------------------------------------------------------------------------------------------- */
/* Params */

/** A connection id plus, for hub connections, the execution node's device id. */
struct Target {
  std::string connection;
  std::string node;
  void apply(Json &params) const;
};

struct AddRuntimeParams {
  std::string name, url;
  /** Exactly one of token / token_file. The token goes into the bridge only. */
  std::string token, token_file;
  bool check = true;
  Json to_json() const;
};

struct PairHubParams {
  std::string name, url, code, device_name;
  Json to_json() const;
};

struct TaskSubmitParams {
  Target target;
  std::string idempotency_key;
  /** A Runtime TaskSpec, or a hub template with its workspace. */
  Json spec;
  std::string template_name, workspace_id;
  Json to_json() const;
};

struct UploadParams {
  Target target;
  std::string workspace_id;
  std::string source; /* absolute file or folder */
  std::string remote; /* relative; empty: the source name */
  Json to_json() const;
};

struct DownloadParams {
  Target target;
  /** Exactly one of task_id / workspace_id. */
  std::string task_id, workspace_id;
  std::string path;
  std::string dest; /* absolute; empty: <download_dir>/<server>/<owner>/<path> */
  Json to_json() const;
};

struct WatchParams {
  Target target;
  std::string workspace_id;
  std::vector<std::string> task_ids;
  std::optional<double> interval;
  Json to_json() const;
};

struct LogsParams {
  Target target;
  std::string task_id;
  std::vector<std::string> streams; /* empty: stdout + stderr */
  /** Starting byte offsets per stream (a view restored from an earlier session). */
  std::map<std::string, int64_t> offsets;
  std::optional<int64_t> chunk_bytes;
  Json to_json() const;
};

struct EventsParams {
  Target target;
  std::string task_id;
  int64_t offset = 0;
  Json to_json() const;
};

struct HubSubscribeParams {
  std::string connection;
  int64_t after = 0;
  Json to_json() const;
};

struct EvaluateParams {
  std::string eval_id;
  /** stk-graph-v1 §9 request: graph | preset, bindings, parameters, outputs, ... */
  Json request;
  std::string mode = "local"; /* local | hub */
  std::map<std::string, std::string> local_bindings;
  Target target; /* Runtime task bindings (local mode) or the hub node */
  std::optional<double> wait;
  Json to_json() const;
};

struct ProbeParams {
  Json graph; /* or preset */
  std::string preset;
  std::string node, dataset;
  Json context; /* {bindings, values, result, artifacts}; null: absent */
  std::map<std::string, std::string> local_bindings;
  Target target;
  std::optional<std::array<double, 3>> position;
  Json to_json() const;
};

/** Standard base64 (RFC 4648, padding optional); nullopt on invalid input. */
std::optional<std::vector<uint8_t>> decode_base64(std::string_view text);

}  // namespace stk::bridge
