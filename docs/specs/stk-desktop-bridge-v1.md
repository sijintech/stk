# STK desktop bridge protocol v1

> 中文摘要：桌面程序（GPL，C++）通过子进程 `python -m suan.desktop_bridge --stdio`（MIT）访问 STK：标准输入输出上逐行传输
> JSON（NDJSON），请求带 `id`、响应按 `id` 对应、事件由桥主动推送，错误码稳定。桥持有全部凭据（运行时令牌、控制服务设备令牌），
> 程序只见不透明的连接 ID；大数据经内容寻址缓存 `<cache>/blobs/<aa>/<sha256>` 由程序内存映射。上传下载可续传、有日志、下载经
> sha256 校验；提交任务带幂等键；日志按字节偏移增量推送且跨块多字节字符安全；关闭程序不会停止任务。

Status: **frozen for Milestone D1** (WP7), with the additive hub-mode changes of WP11 (§7.1, §9,
§10, §1 state-directory lock) and the WP8 follow-ups (`bytes` in offset-based events, transfer
idempotency keys, ids of undecodable lines, clarifications in §2, §3, §7, §8, §12), and the local
project extension (§13, 2026-09-28); still
`protocol: 1`. Schema: `suan/contracts/schemas/desktop-bridge-1.schema.json`
(`suan.contracts.load_schema("desktop-bridge-1")`). Implementation: `suan/desktop_bridge/` (standard
library plus the STK core it drives). Conformance tests: `tests/test_desktop_bridge*.py`. The C++
client is `desktop/engine/lib/stk_bridge` (WP8), written against this document and the schema.

The bridge replaces the file-queue bridge of the Blender workbench (`suan/blender_client/bridge.py`,
archived at D1 exit under the tag `archive/blender-workbench-2026-09`).

## 1. Process model

- The desktop app (GPL-2.0-or-later) spawns **one bridge child process** and talks to it over the
  child's stdin (app → bridge) and stdout (bridge → app). stderr is free-form diagnostics for logs;
  the app must drain it but never parses it.
- Command line: `python -m suan.desktop_bridge --stdio [--state-dir DIR] [--cache-dir DIR] [--strict]`.
  - `--state-dir` (default `$STK_DESKTOP_BRIDGE_DIR`, else `~/.stk/desktop-bridge`): paired hubs
    (`hubs.json`), transfer journals (`transfers/`). Created with mode 0700.
  - `--cache-dir` (default `<state-dir>/cache`): the blob cache (`blobs/`), downloads
    (`downloads/`), graph caches (`graph/`) and probe field copies (`fields/`).
  - `--strict` (or `STK_BRIDGE_STRICT=1`): the bridge validates every message it sends against the
    schema and turns a violating response into `internal_error` (tests and CI run this way).
  - Also read: `STK_PROFILES_FILE` (Runtime profiles, shared with `suan connect`; default
    `~/.stk/connections.json`) and `STK_STATE_DIR` (the local Runtime; default `~/.stk/runtime`).
- **One bridge per state directory.** At start the bridge takes an exclusive, non-blocking OS lock on
  `<state-dir>/bridge.lock` (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows), before it reads
  or rewrites any journal. The OS releases it when the process exits or crashes. A second bridge on
  the same state directory does not start: it answers **every** request with error `busy`
  (`data.state_dir`; the message names the directory; `retryable: false`, because repeating cannot
  help while the other bridge runs), writes the reason to stderr, and exits with status **3** at
  stdin EOF. The app must not restart such a bridge in a loop. The app shows the message and either closes the other bridge or uses
  another `--state-dir`. (In-process, `Bridge(...)` raises `BridgeError("busy")`.)
- **Lifetime.** The bridge exits when stdin reaches EOF or after answering `shutdown`: it stops
  subscriptions, cancels local graph evaluations, pauses transfers at the next chunk boundary
  (their journals stay resumable) and waits up to 5 s for in-flight requests. **Runtime tasks and
  hub actions are never cancelled**: closing the app keeps jobs running. Owned model requests have
  a separate lifetime: project-session shutdown fences late results and schedules best-effort
  persistence of uncertain outcomes without waiting on a locked project database (§13).
- **Crash and restart.** If the bridge dies, the app starts a new one, sends `hello` (which by
  default resumes interrupted transfers) and replays its subscriptions from the offsets it last
  received (§8). Workspace/task/hub-action creation takes an idempotency key, so replaying a
  request whose response was lost never creates a second workspace, task or hub action. Local
  project creation and edits use a different recovery rule and must not be replayed automatically (§13).

## 2. Framing

- One message per line: a UTF-8 JSON object followed by `\n` (a final `\r` is tolerated on input).
  JSON is **strict**: no `NaN`/`Infinity`, no duplicate keys. Non-finite numbers inside data
  (monitoring events, graph results) are the strings `"NaN"`, `"Inf"`, `"-Inf"`, as in events v1.
- A line holds at most **16 MiB** (`limits.max_line_bytes`, excluding the newline). The limit is
  16 MiB in protocol 1 **before `hello` too**: an app may rely on it for the `hello` request itself
  and then use the value `hello` reports. A longer input line is discarded and answered with
  `line_too_long` (with the line's id when it starts with it, see §3, else `id: null`); a result that
  would be longer is replaced by a `result_too_large` error. Large data never travels inline: it goes
  through the blob cache (§9) or files.
- Blank input lines are ignored.
- **stdout carries nothing but protocol lines.** Before anything else runs, the bridge moves its
  protocol stream to a private duplicate of file descriptor 1 and points descriptor 1, `sys.stdout`
  and `logging` at stderr, so stray `print`s, library output and child processes cannot corrupt it.

## 3. Envelopes

```json
{"id": 7, "method": "task.get", "params": {"connection": "runtime:cluster", "task_id": "…"}}
{"id": 7, "result": {"task": {"id": "…", "state": "running", "…": "…"}}}
{"id": 7, "error": {"code": "not_found", "message": "Task not found", "retryable": false}}
{"event": "logs.chunk", "data": {"sub": "…", "stream": "stdout", "text": "…", "offset": 0, "next_offset": 42, "bytes": 42}}
```

| Message | Keys | Notes |
|---|---|---|
| request (app → bridge) | `id`, `method`, `params`? | `id`: integer 0..2^53−1 or string of 1..128 characters, unique among the app's outstanding requests. `params` defaults to `{}`. No other keys. |
| response (bridge → app) | `id`, and exactly one of `result` (object) / `error` | `id` is `null` only when the request's id could not be read (`parse_error`, `line_too_long`, `invalid_request`; see below). |
| event (bridge → app) | `event`, `data` (object) | Pushed at any time. Subscription events carry `data.sub`. |

- **Concurrency.** Requests run concurrently (at most 64 in flight, else `busy`); responses arrive in
  any order and are matched by `id`. A subscription's first event is sent only after its subscribe
  response.
- **Params are closed**: unknown keys are `invalid_params`, so typos fail loudly. Results and event
  data are **open**: clients ignore keys they do not know (additions are not breaking).
- **Errors of undecodable lines.** A line that is not UTF-8, not strict JSON or too long cannot be
  parsed, but when it **starts with its `id` member** (`{"id": 7, ...` or `{"id": "a-1", ...`:
  optional blanks, `"id"`, `:`, an integer 0..2^53−1 without leading zeros or a string of 1..128
  characters without escapes, then `,` or `}`) the error response carries that id, so the app
  completes exactly that call. Apps should therefore write `id` first. Otherwise the error has
  `id: null` and cannot be attributed: responses to other lines arrive in any order, so "the oldest
  pending call" would be a guess. The app logs it, and the call it belongs to ends by the app's own
  timeout.
- There is no request cancellation message; long operations have their own (`graph.cancel`,
  `transfer.cancel`, `unsubscribe`). A call the app abandons (timeout, user cancel) still runs to
  completion in the bridge and keeps one of the 64 in-flight slots until then; its late response is
  dropped by the app. A `cancel {id}` request is a protocol 2 item (§12).

## 4. Errors

`error = {"code", "message", "retryable", "data"?}`. `message` is human-readable English (or the
Runtime's/hub's own text) and never contains credentials. `retryable: true` means repeating the same
request (same idempotency key) may succeed.

| Code | Retryable | Meaning |
|---|---|---|
| `parse_error` | no | The line is not UTF-8 or not strict JSON |
| `line_too_long` | no | The line exceeds `max_line_bytes` |
| `invalid_request` | no | The envelope is malformed |
| `unknown_method` | no | `data.methods` lists the known methods |
| `invalid_params` | no | Params fail the schema or a semantic check; `data.errors: [{path, message}]` (JSON pointers) |
| `unsupported` | no | The protocol version or the connection cannot do this (e.g. a hub read path the node lacks) |
| `not_found` | no | Unknown connection, workspace, task, artifact, transfer, subscription or preset |
| `unauthorized` | no | The Runtime or hub refused the stored credential (re-add or re-pair) |
| `unavailable` | yes | The Runtime or hub cannot be reached (tunnel down, service stopped) |
| `conflict` | no | An idempotency key or action id reused with different content; a transfer running in another bridge |
| `review_not_inspected` | no | `hub.review` approval without a prior `hub.action` read of that action |
| `remote_error` | no* | The Runtime, hub or node refused or failed the operation (`data.action` for hub actions) |
| `checksum_mismatch` | yes | Transferred bytes do not match the declared sha256 |
| `graph_error` | no | Graph validation or evaluation failed: `data.graph_code` (stk-graph-v1 codes), `issues`, `node`, `errors` |
| `cancelled` | no | The operation was cancelled |
| `timeout` | yes | A hub action has not finished within the wait; repeat the request to keep waiting |
| `busy` | yes / no | Too many requests in flight (`retryable: true`); another bridge holds the state directory (§1; `data.state_dir`, `retryable: false`, exits with status 3); or a live model executor owns the requested execution lock (§13; `retryable: false`) |
| `result_too_large` | no | The response would exceed `max_line_bytes` |
| `shutting_down` | no | The bridge is exiting |
| `internal_error` | no | A bridge bug (details on stderr) |

\* `remote_error` is retryable when the Runtime answered HTTP 5xx.

## 5. Session

`hello {protocol: 1, client?: {name, version}, resume_transfers?: true}` → `{protocol, server: {name,
version, python, platform, pid}, methods, events, limits: {max_line_bytes, max_inflight,
watch_interval_s, log_chunk_bytes, transfer_chunk_bytes}, paths: {state_dir, cache_dir, blob_dir,
download_dir}, resumed_transfers}`. Another major `protocol` is `unsupported` with
`data.supported: [1]`. The app sends `hello` first and after every restart; `methods` lets a newer
app detect an older bridge. `shutdown {}` → `{ok: true}`, then the bridge exits as on EOF.

## 6. Connections and credentials

Connection ids are opaque to the app; the bridge resolves them:

| Id | Meaning | Credential store |
|---|---|---|
| `local` | The Runtime initialized on this computer (`$STK_STATE_DIR`) | its `config.json` |
| `runtime:<name>` | A loopback endpoint, directly or through an SSH tunnel | `$STK_PROFILES_FILE` (shared with `suan connect`) |
| `hub:<name>` | A control hub this bridge paired with as a client device | `<state-dir>/hubs.json` |

- Tokens go **into** the bridge only (`connections.add_runtime` `token`/`token_file`,
  `connections.pair_hub` one-time `code`). No result, event or error carries a token; files holding
  them are written atomically with mode 0600. Runtime URLs must be loopback HTTP (tunnels); hub URLs
  must be HTTPS (or HTTP on loopback); requests use no proxies and follow no redirects.
- Model requests use the separate environment-only `STK_TOKEN_PLAN_API_KEY` credential (§13),
  not a Runtime/hub connection ID. There is no bridge method to set or return that credential.
- Names: `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`.
- Operations on a hub connection need `node`: the device id of an execution node (from
  `hub.devices`).

| Method | Params | Result |
|---|---|---|
| `connections.list` | – | `{connections: [{id, kind: local\|runtime\|hub, name, url, device_id?, profile?, state?}]}` (`profile: "desktop"` for a hub device paired with a desktop code). `local` is always listed, with `state: "initialized"` or `"not_initialized"` (then `url` is null and `connections.check {id: "local"}` answers `ok: false` with `not_found`) |
| `connections.add_runtime` | `name, url, token \| token_file, check?=true` | `{connection}` (health-checked unless `check: false`) |
| `connections.remove` | `id` | `{removed}` (forgets the profile; never revokes on the hub) |
| `connections.check` | `id` | `{id, ok, health?, nodes?, error?}`: `ok: false` with `error` when unreachable or refused |
| `connections.pair_hub` | `name, url, code, device_name?` | `{connection}`; only client pairing codes are accepted. A code the owner issued with `suan-control pair --role client --profile desktop` pairs a **desktop device** (§7.1) |
| `connections.local` | – | `{initialized, api_running, supervisor_running, url, state_dir, error?}` |
| `connections.local_start` | `initialize?=false` | as `connections.local`, after starting the API and supervisor (Linux); with `initialize: true` an uninitialized local Runtime is initialized first (`suan server init` defaults), as the legacy Tasks tab did |

## 7. Workspaces, tasks and the hub

| Method | Params | Result |
|---|---|---|
| `workspace.list` | `connection, node?` | `{workspaces: [{id, name, created_at}]}` |
| `workspace.create` | `connection, node?, name, idempotency_key?` | `{workspace?, action?}` |
| `workspace.files` | `connection, node?, workspace_id` | `{files: [{path, size, sha256, media_type?}]}` |
| `task.submit` | `connection, node?, idempotency_key, spec \| (template, workspace_id)` | `{task?, action?}` |
| `task.list` | `connection, node?, workspace_id?` | `{tasks}` newest first |
| `task.get` | `connection, node?, task_id` | `{task}` (with `monitor` once events exist) |
| `task.cancel` | `connection, node?, task_id, idempotency_key?` | `{task?, action?}` |
| `task.artifacts` | `connection, node?, task_id` | `{artifacts: [{path, size, sha256, media_type}]}` (empty while running) |
| `hub.devices` | `connection` | `{devices: [{id, name, role, online, snapshot}]}` |
| `hub.templates` | `connection` | `{templates: {<name>: {argv, inputs?, outputs?, resources?, ...}}}`: an object keyed by template name (the hub's `GET /api/v1/templates`); the names are what `task.submit {template}` takes |
| `hub.actions` | `connection` | `{actions}`: recent actions plus every action in review (without results); each record carries `kind` at the top level (the hub keeps it in `request.kind`, which stays) |
| `hub.action` | `connection, action_id` | `{action}` with full `request`, `result` and top-level `kind`; marks it *inspected* |
| `hub.review` | `connection, action_id, approved` | `{action}` |
| `hub.policy` | `connection` | `{policy: {device_profile, desktop_auto, desktop_auto_bytes, graph_auto_seconds, uploads, upload_max_bytes, upload_chunk_bytes, upload_quota_bytes, import_max_files, import_request_bytes, action_request_bytes, read_kinds, review_policy}}` (WP11) |

- `spec` is a Runtime `TaskSpec` (`workspace_id, argv, backend?, name?, inputs?, input_hashes?, outputs?, env?,
  resources?` including MPI `ranks`/`threads_per_rank`; see docs/runtime.md). It is validated before
  sending (`invalid_params`). `argv` tokens `{python}`, `{ranks}`, `{threads_per_rank}`, `{nodes}`
  are expanded by the Runtime; through a hub, `argv[0] == "@python"` names the node's Python.
- **Idempotency.** Direct Runtime: the key is the Runtime's own idempotency key: the same key and
  spec return the same task (also after a bridge restart); the same key with a different spec is
  `conflict`. Hub: the action id is `sha256("task.submit\0<node>\0<key>")[:32]` (likewise
  `workspace.create`, `task.cancel`), so a repeated request re-reads the same action, and the hub
  rejects a different request under that id (`conflict`).
- **Retries are the client's.** The Runtime `TaskSpec` has no retry field and nothing in the bridge
  re-runs a failed task. A retry policy (automatic re-sends after `unavailable`, `timeout`,
  retryable `busy` or HTTP 5xx, or a "retry last submission" button) re-sends the **same request
  with the same idempotency key**, which can never create a second task or hub action.
- **Hub actions** (`action = {id, kind, state, node_id, error, review_reason, created, updated}`):
  a method that becomes a hub action waits up to 30 s for it (`timeout` otherwise; repeat to keep
  waiting). An action that needs review returns at once with `state: "review"` and no result; after
  approval, the same request (same key) waits for and returns the result. `failed` and `rejected`
  actions are `remote_error` with `data.action`.
- **Review.** `hub.review {approved: true}` is refused with `review_not_inspected` unless this
  bridge read that action with `hub.action` first (the app shows the full request before the user
  approves). Rejections need no inspection. The inspection is remembered by the bridge process only:
  **after a bridge restart the app must run `hub.action` again before `hub.review`** (and should
  show the request again, since it may have changed).
- Through a hub, `workspace.list`, `task.list` and `task.get` read the node's latest heartbeat
  snapshot (tasks without their spec); `task.artifacts`, `workspace.files`, logs, events and
  download chunks use the hub's read path (§7.2), never reviewed; uploads go through the hub's blob
  store and a reviewed `workspace.import` (§9).

### 7.1 Desktop devices and automatic execution (WP11)

A hub client device paired with a **desktop** code (the owner grants it; a device cannot claim it)
runs graph evaluations and read-only data actions on a node without per-action review, as long as
the **expected transfer** stays under the hub's cap: `budget.max_output_bytes` of the request, or
when unset the result profile's default delivery limit (phone 32 MiB, web 128 MiB, desktop 2 GiB;
the node enforces it). The cap defaults to **256 MiB**; it is a default the hub owner changes
(`suan-control serve --desktop-auto-mib N`, or `"desktop_auto_mib"` in the hub's `control.json`;
0 turns desktop auto-run off). `hub.policy` reports it, so the app sets `budget.max_output_bytes`
accordingly for `profile: "desktop"` requests.

| Request | Other clients, owner token | Desktop device |
|---|---|---|
| `graph.evaluate` phone/web within the ordinary budget | runs | runs (expected transfer ≤ cap) |
| `graph.evaluate` with result profile `desktop` or desktop payloads (desktop payload counts, `bytes` ≤ cap) | review | runs when expected transfer ≤ cap |
| expected transfer > cap (including `desktop` without `max_output_bytes`) | review | review |
| `max_seconds` > 300, image pixels over budget, node types the hub lacks | review | review |
| logs, events, artifacts, file chunks, `workspace.files`, `view.build`, `view.probe`, `graph.meta`, `graph.cancel` | runs | runs |
| `workspace.create`, `task.cancel`, exact template `task.submit` | runs | runs (unchanged) |
| any other `task.submit`, and `workspace.import` (writes) | review | review |

A revoked device is refused everywhere (the hub answers 401, the bridge `unauthorized`).

**Review is a confirmation step by default.** Under the hub's default `review_policy: any`, any
client device, including the one that submitted an action, may approve it; the security boundary
is owner-granted pairing plus revocation. A hub owner can make review an authorization boundary
with `review_policy: not-self` (a device cannot approve its own action; the owner token always can;
recommended for hubs reachable from the internet) or `owner` (only the owner token approves).
`hub.policy.review_policy` reports it. An approval the policy refuses is `unauthorized` with
`data: {action_id, reason: "review_policy"}` and the hub's message; rejections are always allowed
(so `transfer.cancel` can still withdraw its own import).

**Request limits.** The hub checks every action and read exactly: unknown payload keys are refused
(HTTP 422, bridge `remote_error`), and an action's encoded request is at most 1 MiB (a
`workspace.import` at most 4 MiB and 4096 files; HTTP 413). Nothing the hub stores can therefore
exceed the 16 MiB node connection frame; the hub also fails, instead of sending, any stored action
that would not fit, and the owner can stop a stuck action (`POST /api/v1/actions/<id>/fail`).

### 7.2 The hub read path (WP11)

Polled reads (logs, events, artifact lists, workspace input lists, download chunks) through a hub
use `POST /api/v1/nodes/<node>/read {kind, payload}`: the hub forwards the read over the node's open
WebSocket (`{"type": "read"}`), the node agent answers on a separate read lane (`read_result`), and
the hub returns the result. **No action row and no `actions.changed` event is created.**

Why this and not one long-lived action with a cursor or a stream: reads are idempotent and small (at
most 1 MiB of data per request), so they need neither durability nor review, while every action row
is kept forever (M1 has no retention), wakes every hub subscriber through `actions.changed`, and
competes with reviews in the 200-row listing. A per-subscription cursor action would still need a
hub-side stream protocol, state that survives reconnects, and cleanup of abandoned cursors; a
request/response over the connection the node already keeps open needs none of that. Reads fail
fast when the node is offline (`unavailable`, retryable) instead of queuing, so an outage does not
leave a backlog of stale polls to run later.

Compatibility: a node agent without the read path (no `read` in its snapshot features) makes the hub
answer 501, and a hub without the route answers 404/405; the bridge then uses a read action as
before (one row per call) and tries the read path again a minute later. A node's own error (unknown
task, missing file) is `remote_error` with the node's message.

## 8. Subscriptions

Each subscribe method returns `{sub}` (32 hex); `unsubscribe {sub}` stops it. Subscriptions poll in
the bridge and push events; a failing poll sends one `subscription.error {sub, error}` and keeps
retrying (`final: true` when the subscription ended because of it, e.g. `not_found`).

| Method | Params | Events |
|---|---|---|
| `watch` | `connection, node?, workspace_id?, task_ids?, interval?=2` (s, ≥ 0.5) | `watch.snapshot {sub, tasks, time}`: the first poll, then whenever the task list changed |
| `logs.subscribe` | `connection, node?, task_id, streams?=[stdout, stderr], offsets?, chunk_bytes?` | `logs.chunk {sub, stream, text, offset, next_offset, bytes}`; `logs.end {sub, offsets}` |
| `events.subscribe` | `connection, node?, task_id, offset?=0` | `events.batch {sub, events, invalid, offset, next_offset, bytes}`; `events.end {sub, next_offset}` |
| `hub.subscribe` | `connection, after?=0` | `hub.event {sub, cursor, kind, payload}` (hub SSE: `actions.changed`, `devices.changed`, …) |

- **Logs are UTF-8 safe.** The bridge reads byte ranges (`chunk_bytes`, default 256 KiB, max 1 MiB)
  and decodes them incrementally: a character split across reads is held back until complete;
  invalid bytes become U+FFFD. `offset`/`next_offset` are byte offsets of the **source stream** and
  lie on character boundaries; `text` is the decoding of the source bytes `[offset, next_offset)`,
  and `bytes = next_offset − offset` is their count. Where the stream held invalid UTF-8, each
  invalid sequence became U+FFFD, so the UTF-8 length of `text` can differ from `bytes`: clients
  count positions with `offset`/`next_offset`/`bytes`, never with the length of `text` (in
  particular a client that trims an overlapping chunk may cut `text` by bytes only when its UTF-8
  length equals `bytes`; otherwise it drops or keeps the chunk whole). Streams: `stdout`, `stderr`,
  `scheduler.out`, `scheduler.err`, `wrapper`. `logs.end.offsets` maps each stream to its final
  offset (integers).
- `events.batch` carries `bytes = next_offset − offset` as well (bytes of the events file).
  `bytes` was added after the D1 freeze: clients use `next_offset − offset` when it is missing.
- **Replay.** After a restart the app resubscribes with `offsets: {stream: last next_offset}` (logs)
  or `offset: last next_offset` (events) and continues exactly, without duplicates. `hub.subscribe`
  resumes with `after: last cursor`.
- **Snapshots are state, not deltas.** Each `watch.snapshot` is the complete current task list
  (filtered by `workspace_id`/`task_ids`); a client replaces its view with it. A resubscribed
  `watch` therefore starts with a snapshot equal to the last one seen before the restart, which is
  not a duplicate event to reconcile, and a missed snapshot loses nothing.
- A log stream ends after two empty reads of a finished task (so bytes written just before the task
  finished are not lost); `logs.end` then carries the final offsets. Events follow events v1 §5
  (whole lines, invalid lines reported by offset in `invalid`); `events.end` follows the last batch
  of a finished task.

## 9. Transfers and the blob cache

| Method | Params | Result |
|---|---|---|
| `upload.start` | `connection, node?, workspace_id, source` (absolute file or folder), `remote?` (relative path; default the source name; `"."` puts a folder's contents at the workspace root and keeps a file's name), `idempotency_key?` | `{transfer}` |
| `download.start` | `connection, node?, task_id \| workspace_id, path, dest?` (absolute; default `<download_dir>/<server key>/<task or workspace id>/<path>`), `idempotency_key?` | `{transfer}` |
| `transfer.list` / `transfer.get {id}` | – / `id` | `{transfers}` / `{transfer}` |
| `transfer.resume` | `id` | `{transfer}` (continues an `interrupted` or `failed` transfer) |
| `transfer.cancel` | `id` | `{transfer}` in state `cancelled` |

`transfer = {id, kind: upload|download, state: queued|running|interrupted|completed|failed|cancelled,
connection, node?, workspace_id?, task_id?, local, remote, bytes_done, bytes_total, files_done,
files_total, current?, sha256?, error?, action?, created_at, updated_at}` (`action`: the hub
`workspace.import` of an upload through a hub). `transfer.updated {transfer}` is sent
on every state change and at most every 250 ms while bytes move.

- **Idempotency.** With `idempotency_key` the transfer id is `sha256("<kind>.start\0<key>")[:32]`
  (`kind` = `upload` / `download`, so the two key spaces are separate) and the key and request are
  kept in the journal: repeating the request with the same key (also from a new bridge after a
  crash) returns that transfer in whatever state it is now, without starting another; the same key
  with a different request (`connection, node, workspace_id, source, remote` or `connection, node,
  task/workspace, path, dest`) is `conflict` with `data.transfer_id`. A failed or cancelled keyed
  transfer is continued with `transfer.resume`, not by repeating `*.start`. Keys are remembered as
  long as the journal (finished journals are kept 7 days).
- **Journal.** `<state-dir>/transfers/<id>.json` is written atomically before and during the work. A
  transfer found `queued`/`running` at start-up was interrupted: it becomes `interrupted` and
  continues on `transfer.resume` or `hello` (`resume_transfers`, default true). One bridge runs a
  transfer at a time (a lock file per transfer; `conflict` otherwise). Finished journals are kept 7
  days.
- **Uploads** use the Runtime's resumable sessions: `begin` returns the byte offset the Runtime
  holds, 1 MiB chunks are appended from there, and `finish` checks size and sha256. A folder upload
  sends every regular file below it (symbolic links are never followed) under `remote/…`, or at the
  workspace root with `remote: "."`; any other `remote` must be a normalized relative path (no `..`,
  absolute paths, drive letters or backslashes: `invalid_params`). A file
  that changed since it was hashed is re-hashed and starts a new revision. `transfer.cancel` aborts
  the Runtime's session (pending sessions block submissions in that workspace).
- **Uploads through a hub** (`connection` a hub, `node` the execution node; WP11) keep the same
  journal semantics in two stages:
  1. Each file goes into the hub's content-addressed blob store through a resumable session
     (`POST /api/v1/uploads` returns the bytes the hub holds, 1 MiB chunks are appended from there,
     `finish` checks size and sha256; the session belongs to this device). A file the hub already
     holds moves no bytes. Only **desktop devices** may upload (others get `unauthorized`). Limits:
     the hub's blob cap per file (`hub.policy.upload_max_bytes`); a per-device quota
     (`upload_quota_bytes`, default 4 GiB) over unfinished uploads plus uploaded files no queued or
     succeeded import references (`invalid_params` when exceeded); a free-disk floor on the hub
     (default 5 GiB; `unavailable` while below it); at most 4 chunks per device in flight. A folder
     through a hub holds at most 4096 files and its file list must fit the 4 MiB import request
     (`invalid_params` at `upload.start`, before any byte moves; upload large folders in parts).
     Uploaded files that no pending or finished import references are deleted by the hub after a
     day by default (`--upload-gc-hours`), so an interrupted upload should be resumed within that
     time or it starts over.
  2. One `workspace.import` action (id `sha256("workspace.import\0<node>\0<transfer id>\0<attempt>")[:32]`)
     asks the node to copy the blobs into the workspace. The node re-verifies every sha256 and the
     paths (§7.1 confinement rules: normalized relative paths, no `..`, absolute paths, drive letters,
     backslashes or control characters), and the Runtime checks again. **Imports always need
     review** (they write, and may replace inputs of the same name): the transfer stays `running`
     with `bytes_done == bytes_total` and `action.state: "review"` until the owner decides, and does
     not hold one of the 4 transfer slots meanwhile. After approval it completes when the node
     reports success.
  A bridge restart during either stage resumes it (`interrupted`, then `transfer.resume` or
  `hello`): stage 1 continues from the hub's offsets, stage 2 re-reads the same action. A rejected or
  failed import fails the transfer (`remote_error`, `data.action`); `transfer.resume` then asks again
  with a new action. `transfer.cancel` aborts unfinished hub sessions and rejects an import still in
  review.
- **Downloads** append to `<dest>.part` (expected `{path, size, sha256}` in `<dest>.part.json`) from
  its current size and move the file into place only after its sha256 matched the listing; a
  mismatch discards the part and fails with `checksum_mismatch` (retryable). A destination that
  already holds the right bytes completes without transferring.
- **Blob cache** `<cache>/blobs/<sha[:2]>/<sha256>`: the layout of the hub store and
  `suan.graph.service.DirectoryBlobSink`. Files are immutable and named by their content; the app
  memory-maps them. `blob.ensure {sha256: [...], connection?}` → `{blobs: {sha: {path, size}},
  missing, blob_dir}` fetches absent blobs from a hub connection (verified before they appear).

## 10. Graphs, probes and colormaps

| Method | Params | Result |
|---|---|---|
| `graph.catalog` | – | `{catalog}` (`stk.catalog/1`) |
| `graph.presets` | – | `{presets: [{id, name, description, graph, bindings, parameters}]}` |
| `graph.validate` | `graph, parameters?` | `{ok, issues: [{code, message, path, node, hint, severity}]}` |
| `graph.evaluate` | `eval_id, request, mode?=local \| hub, local_bindings?, connection?, node?, wait?` | `{result, blob_dir, action?}` |
| `graph.cancel` | `eval_id, connection?, node?` | `{cancelled, action?, error?}` |
| `probe` | `graph \| preset, pick: {node, dataset?}, context?: {bindings, values, result, artifacts}, local_bindings?, connection?, node?, position?` | `{target: {binding, task_id?, path, node, metadata?}, sample?}` |
| `colormaps.list` | – | `{colormaps: [{name, lut_rgba8}], aliases, categorical_palettes, reserved_colors, nan_color}` |

- `request` is the `graph.evaluate` payload of stk-graph-v1 §9 (`graph | preset, bindings,
  parameters, outputs, profile, budget, plot_format`); request bindings only name Runtime tasks.
- **Local mode** evaluates in a reusable worker child process: `local_bindings: {name: absolute directory}`
  (`LocalDirResolver`, confined to each directory) and, with a Runtime `connection`, task bindings
  (`RuntimeResolver`: sha256-verified downloads into the graph cache). Progress arrives as
  `graph.progress {eval_id, event}` (the evaluator's `node.started`, `node.cached`,
  `node.finished`, `node.failed`, `progress`, `warning` events). Blobs go straight into the blob
  cache. Local requests share a serial evaluation lane and a warm in-memory node cache; the bridge
  continues serving Jobs, subscriptions and cancellation while the worker computes. Runtime
  credentials cross only the private pipe, never command-line arguments or temporary request files.
  Worker stdout/native output and its subprocesses are isolated from the bridge protocol streams.
  `graph.cancel` stops the evaluation (`cancelled` error): queued requests leave active work alone;
  active requests get cooperative cancellation, followed after 0.5 seconds by terminating the worker
  and its subprocesses if needed. Cooperative cancellation preserves the warm cache. A forced stop
  discards in-memory cache entries; disk cache and blobs remain available to the next worker.
  Worker crashes answer `unavailable`; requests are not automatically replayed, and the next request
  starts a fresh worker. Bridge shutdown stops the worker; loss of the parent's pipe also ends it.
- **Hub mode** sends a `graph.evaluate` action to `node` with id
  `sha256("graph.evaluate\0<node>\0<eval_id>")[:32]` and waits up to `wait` seconds (default 600).
  Requests over the automatic budget return with `action.state: "review"` and `result: null`;
  repeating the request with the same `eval_id` after approval waits for it. Every blob the result
  references is fetched into the cache before the response.
- **Hub-side cancellation** (WP11). `graph.cancel {eval_id}` of a hub evaluation this bridge is
  waiting for stops the wait at once (the evaluate request answers `cancelled`) and creates a
  `graph.cancel` hub action (id `sha256("graph.cancel\0<node>\0<evaluate action id>")[:32]`): an
  evaluation still in review is failed by the hub without reaching the node; a queued or running one
  is cancelled on the node through the evaluator's `CancelToken` (checked between nodes and between
  Runtime download chunks), also when it is still waiting for the graph lane or the node agent
  restarts. The cancelled evaluate action ends `failed` with an error starting `cancelled:`;
  repeating `graph.evaluate` with that `eval_id` answers `cancelled` (use a new `eval_id` to run it
  again). With `connection` and `node`, `graph.cancel` also cancels a hub evaluation this bridge is
  not waiting for (e.g. one in review, or started before a bridge restart). The result: `cancelled`
  is whether the hub or node stopped (or will stop) the evaluation, `action` the `graph.cancel` hub
  action, `error` why the hub could not be asked (e.g. `remote_error` for an unknown evaluation);
  a local evaluation answers `{cancelled: true}` as before.
- `eval_id` is the app's name for one evaluation (`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`); two
  evaluations with the same id cannot run at once (`conflict`).
- `graph_error` carries `data.graph_code` (e.g. `unknown_preset`, `unknown_binding`,
  `budget_exceeded`), `issues` for validation errors, and `errors` (per node) for failed nodes.
- **Probe.** `target` comes from `suan.graph.probe.resolve_probe_target` (the port of
  `web/src/graph.ts::resolveProbeTarget`): walking upstream from `pick.node` to the first
  `stk.source.file@1` or `stk.source.muferro_frame@1`. Unresolvable targets are `not_found` with the
  resolver's message. With `position` (physical xyz), `sample = {position, values, units,
  interpolation: "trilinear", source: "original_point_data"}` reads the original field: from a local
  binding, from the Runtime (cached by sha256), or through the hub's `view.probe` action.
  muFerro frames use grid-index coordinates unless the source declares `origin`/`spacing`.
- `lut_rgba8` is base64 of the 256 × RGBA8 table of stk-render-payload-v2 §5.

## 11. Events

| Event | Data |
|---|---|
| `transfer.updated` | `{transfer}` |
| `watch.snapshot` | `{sub, tasks, time}` |
| `logs.chunk` / `logs.end` | `{sub, stream, text, offset, next_offset, bytes}` / `{sub, offsets: {stream: integer}}` |
| `events.batch` / `events.end` | `{sub, events, invalid, offset, next_offset, bytes}` / `{sub, next_offset}` |
| `hub.event` | `{sub, cursor, kind, payload}` |
| `subscription.error` | `{sub, error, final?}` |
| `graph.progress` | `{eval_id, event: {type, …}}` |
| `project.changed` | `{handle, revision}` (§13) |
| `project.closed` | `{handle}` (§13) |

## 12. Schema, conformance and versioning

- `desktop-bridge-1.schema.json` validates every message: the root is `oneOf` request / response /
  event; `$defs/methods/<method>/{params, result}` and `$defs/events/<event>` give each method and
  event. It uses only the JSON Schema subset of `suan.graph.schema.check_value` (type, enum, const,
  bounds, lengths, pattern, items, properties/required/additionalProperties/patternProperties,
  anyOf/oneOf/allOf) plus local `$ref`, so the C++ subset validator (stk_io) reads it too.
  `suan.desktop_bridge.schema` inlines the references and validates with `check_value`; the tests
  also check it with `jsonschema` (Draft 2020-12) when installed.
- The conformance tests validate every message they send and receive, check that stdout carries
  nothing else (including stray prints, raw writes to descriptor 1 and child processes), and cover
  resumed uploads after a bridge restart, idempotent submission, logs split inside multibyte
  characters, verified downloads, the hub review flow and local evaluation of a fake muFerro run.
  `tests/test_hub_desktop*.py` (WP11) cover the desktop auto-run policy, the hub upload and import
  path (resume, review, sha256 and path checks at the node), hub-side `graph.cancel`, the read path
  with a node agent connected over its WebSocket, auth on every new hub route, and the state-directory
  lock.
- **Versioning.** Additive changes (new methods, events, optional params, result keys)
  keep `protocol: 1`; clients detect new methods through `hello.methods` and must ignore unknown
  events and result keys. The error codes of §4 are closed in protocol 1. Removing or changing the
  meaning of anything needs protocol 2.
- **Protocol 2 candidates** (not in protocol 1): request cancellation (`cancel {id}`, freeing the
  in-flight slot of an abandoned call, §3); a distinct error code for the state-directory lock
  instead of the second meaning of `busy` (§4); `bytes` required in offset-based events.

## 13. Local project sessions (additive P1 extension)

These methods access local SQLite project directories through `suan.project.ProjectStore`.
They are independent of Runtime connections and never start simulations. Check `hello.methods`
before exposing project operations with an older bridge. This extension adds no network endpoint
or reverse UI RPC. The experimental storage format is described in [the project guide](../project.md).

| Method | Params | Result |
|---|---|---|
| `project.create` | `{directory, name}` | `{project}` |
| `project.open` | `{directory, expected_id?: project UUID}` | `{project}` |
| `project.list` | `{}` | `{projects: [project]}` |
| `project.recent` | `{}` | `{projects: [{id, directory, name, last_opened}], warning}` |
| `project.forget` | `{directory}` | `{removed: boolean}` |
| `project.close` | `{handle}` | `{closed: boolean}` |
| `project.csv.import` | `{handle, source, name, expected_revision, types?, units?, delimiter?}` | `{revision, table_id, field_ids, record_ids, rows, columns, source_sha256}` |
| `project.csv.export` | `{handle, table_id, destination, expected_revision, delimiter?}` | `{revision, table_id, path, rows, columns, size, sha256}` |
| `project.snapshot` | `{handle}` | `{snapshot}` |
| `project.apply` | `{handle, expected_revision, commands}` | `{revision, commands}` |
| `project.preview` | `{handle, expected_revision, commands}` | `{persisted: false, base_revision, proposed_revision, commands, snapshot}` |
| `project.drafts.save` | `{handle, draft_id, expected_revision, title, commands}` | `{draft}` |
| `project.drafts.get` | `{handle, draft_id}` | `{draft}` |
| `project.drafts.list` | `{handle, offset?, limit?}` | `{drafts: [draft summary], next_offset: integer|null}` |
| `project.drafts.apply` | `{handle, draft_id, expected_revision}` | `{draft, revision, replayed: boolean}` |
| `project.drafts.discard` | `{handle, draft_id}` | `{draft}` |
| `project.contexts.capture` | `{handle, context_id, expected_revision, title, table_id, record_ids, field_ids}` | `{context}` |
| `project.contexts.get` | `{handle, context_id}` | `{context}` |
| `project.contexts.list` | `{handle, offset?, limit?}` | `{contexts: [context summary], next_offset: integer|null}` |
| `project.discussion.add` | `{handle, message_id, context_id, text, role?}` | `{message}` |
| `project.discussion.get` | `{handle, message_id}` | `{message}` |
| `project.discussion.list` | `{handle, offset?, limit?}` | `{messages: [message summary], next_offset: integer|null}` |
| `project.discussion.link_draft` | `{handle, proposal_id, message_id, draft_id}` | `{proposal}` |
| `project.discussion.proposals` | `{handle, offset?, limit?, draft_id?}` | `{proposals: [proposal], next_offset: integer|null}` |
| `project.requests.create` | `{handle, request_id, message_id, configuration}` | `{request}` |
| `project.requests.get` | `{handle, request_id}` | `{request}` |
| `project.requests.list` | `{handle, offset?, limit?}` | `{requests: [request], next_offset: integer|null}` |
| `project.requests.cancel` | `{handle, request_id}` | `{request}` |
| `project.requests.provider` | `{handle}` | `{provider}` (local configuration presence only) |
| `project.requests.start` | `{handle, request_id}` | `{request}` (durable claim or existing state) |
| `project.requests.recover` | `{handle, request_id}` | `{request}` (local abandoned-owner reconciliation only) |
| `project.history` | `{handle}` | `{history: [{revision, created_at, commands}]}` |
| `project.backup` | `{handle}` | `{path, project_id, revision, format_version}` |
| `project.upgrade` | `{handle, expected_revision}` | `{upgraded, revision, format_version, backup: object|null}` |
| `project.undo` / `project.redo` | `{handle, expected_revision}` | `{revision, target_revision}` |
| `project.files.list` | `{handle}` | `{revision, table_id, records}` |
| `project.files.index` | `{handle, expected_revision, paths: [string]}` | `{revision, commands, table_id, record_ids}` |
| `project.files.refresh` | `{handle, expected_revision, record_ids: [uuid]}` | `{revision, commands, table_id, record_ids}` |
| `project.files.resolve` | `{handle, expected_revision, record_id}` | `{revision, record_id, path, kind}` |
| `project.snapshots.capture` | `{handle, expected_revision, record_ids, max_bytes?}` | `{revision, snapshot: inputManifest}` |
| `project.snapshots.list` | `{handle}` | `{revision, snapshots: [inputManifest]}` |
| `project.snapshots.get` | `{handle, snapshot_id}` | `{snapshot: inputManifest}` |
| `project.snapshots.verify` | `{handle, snapshot_id}` | `{snapshot_id, ok, files: [{record_id, sha256, state, error}]}` |
| `project.snapshots.resolve` | `{handle, snapshot_id, record_id}` | `{snapshot_id, record_id, name, path, location, sha256, size}` |

- `project.preview` evaluates ordinary edit commands on an in-memory SQLite copy (source logical size
  at most 128 MiB). It performs no persisted edit, file operation or task submission, and emits no
  `project.changed`. Its snapshot, revision and edit-history pointers are hypothetical. Formula
  errors remain visible in candidate evaluations. Apply its normalized commands (including generated
  UUIDs) explicitly at `base_revision`; a later project edit makes that submission conflict.
  It does not persist or approve a proposal, bypass task review, or automatically upgrade old formats.
- `directory` is an absolute local directory path; the database is `project.sqlite3` within it.
  Creation is explicit and never overwrites an existing database (`conflict`). Open does not create
  missing files (`not_found`). An unsupported format returns `unsupported`; malformed data or edits
  return `invalid_params`. Creating parent directories is permitted.
- `project = {handle, id, name, directory, revision, format_version}`. `id` is the persistent UUID;
  `handle` is a 32-character lowercase hexadecimal session token. Concurrent opens of the same
  canonical path share a handle. Handles expire on close or bridge restart; reopen by directory and
  reload the snapshot. An expired handle returns `not_found`. Close is idempotent and does not delete
  files or revert saved edits. Replacing a database with a different project invalidates use of its
  existing store; close and reopen explicitly.
- `snapshot = {format_version, project: {id, name, revision}, tables}` is one consistent read.
  Each table has `id`, `name`, `fields: [{id, name, type, unit}]`, and
  `records: [{id, values: {field_uuid: value}}]`. Unset cells are absent; explicit nulls remain null.
  Types are `text`, signed-64-bit `integer`, finite `number`, `boolean`, and `json`. Numeric units
  use exact matching for derived values, without implicit conversion. IDs are canonical lowercase UUIDs.
  Format 2 records may additionally have `definitions` and `evaluations`, both keyed by field UUID.
  Definitions are `{kind: "reference", source: {record_id, field_id}}` or
  `{kind: "expression", expression, bindings: {variable: {record_id, field_id}}}`.
  Evaluations contain `state`, `evaluated_revision`, `engine_version`, and either `value, unit` (`ok`)
  or `error: {code, message, source?}` (`error`). Failed values are absent from `values`; explicit null
  results remain present. Definitions survive missing sources and evaluation errors.
  Format 3 adds `edit_history: {undo_revision: integer|null, redo_revision: integer|null}` to the snapshot;
  these identify original edit batches, not the current monotonic project revision.
  An indexed file table adds `file_index: {table_id, fields: {field_name: field_uuid}, compatible: boolean}`.
  The built-in view is recognized by fixed UUIDs/types, not editable display names. File rows remain ordinary
  records and may participate in references/expressions/undo. Incompatible fixed fields require explicit repair.
- `commands` contains 1–1000 closed command objects. Supported operations are `create_table`,
  `add_field`, `add_record`, `set_cell`, `rename_table`, `rename_field`, `set_reference`, `set_expression`,
  `unset_cell`, `delete_record`, `delete_field`, and `delete_table`; the exact required and
  optional properties are in `$defs/projectCommand` and the project guide. The whole batch commits
  atomically at `expected_revision`, or returns `conflict` for a stale revision. The response contains
  the new revision and applied commands, including generated IDs. Edits persist immediately; no
  separate save request is needed. Close waits for any edit already accepted by that session manager.
  Format 1 supports the original literal operations; new definition/deletion operations require an explicit upgrade.
  Scalar evaluation runs inside the edit transaction and updates only affected caches; it never launches work.
  Cycles, missing/unset sources, unit/type/parse errors become saved cell diagnostics. Invalid command shapes
  and literal types still reject the batch. See the project guide for the bounded expression grammar/unit policy.
- `project.backup` writes a consistent, checked SQLite copy under the project's `backups/` directory;
  it does not include external assets or change project revision. `project.upgrade` first creates such a
  backup, then migrates supported older formats (v1–v7) to v8 atomically, adding one revision and an internal
  `{op: "upgrade_format", from_version, to_version}` history record. A stale precondition is `conflict`.
  Already-current format returns `upgraded=false, backup=null` without changing revision. Opening alone
  never migrates. A failed migration rolls back the source; a completed pre-migration backup is kept.
- Format 3 `undo`/`redo` operate on the shared persistent edit stack. They restore one whole batch's row
  values, definitions, identities and display order, recompute affected caches and append a new revision
  with `{op: "undo"|"redo", target_revision}` in history. New successful edits discard the redo branch;
  conflicts/failures preserve it. Empty stacks return `invalid_params` without mutation. Upgrades and
  edits made before format 3 cannot be undone. External files, Runtime jobs, scripts and UI drafts are
  outside this stack. No implicit side effects or script execution occur during restoration.
- `project.files.*` requires format 3. Index/refresh accepts 1–100 explicit paths/record IDs and commits ordinary
  edit commands atomically, emitting `project.changed`. Indexing observes metadata only and never copies/removes
  files. List reads saved observations; resolve rechecks a regular file at the requested revision without opening
  it. Project-relative locations cannot escape the project; external locations retain their OS path syntax.
  Missing future output files may be registered. Size/mtime are observations, not content hashes or immutable
  snapshots. See [file index guide](../project-files.md) for field names, state values and restore semantics.
- `project.snapshots.*` requires format 4 and explicitly manages frozen input bytes, distinct from
  `project.snapshot` (the current editable model). Capture selects 1–100 indexed files, default total budget
  256 MiB (`max_bytes` may be 1 byte–1 TiB), and appends a manifest after a final revision check. It emits
  `project.changed` and is never replayed automatically. Each manifest has a stable UUID, checksum, creation
  time, saved revision and source revision; files retain index IDs, source metadata, size and content SHA-256.
  Table undo cannot change historical manifests. Object publication is atomic/no-replace; a conflict may
  leave reusable unreferenced objects, but no partial manifest. Reads validate manifest identity; verify/resolve
  additionally hash content. Resolve's `path` is the absolute frozen object path; the original source path
  remains in the manifest. Source deletion or project relocation does not invalidate existing objects.
  Database backup excludes object contents. See [input snapshot guide](../project-snapshots.md) for storage
  layout, source-change checks, filesystem requirements and current non-atomic multi-file capture boundary.
- `project.runs.*` requires format 5: prepare freezes 1–100 explicit row/TaskSpec/input snapshot entries at one
  revision without remote execution; list returns paginated summaries (offset/limit, at most 100), get returns
  the immutable plan and latest observation. Submit/cancel are explicit and never automatically replayed;
  submit persists intent before transport and uses the frozen idempotency key for caller-initiated recovery.
  Refresh only reads task/action status. Profile endpoint identity changes are conflicts; new stale plans need
  explicit `allow_stale`. Prepared plans emit `project.changed`; remote observations do not edit the project
  revision and emit independent `project.runs.changed {handle, run_id, observation_id}` hints, possibly before
  a response or on failure. Hub review policy remains in force. See [run guide](../project-runs.md).
- `project.drafts.*` is an optional format 6 extension. Check `hello.methods`; older project formats
  return `unsupported` without implicit migration. A full draft has exactly
  `{id, project_id, title, base_revision, commands, created_at, status, applied_revision, closed_at}`.
  IDs are canonical lowercase UUIDs. `status` is `pending`, `applied` or `discarded`; pending drafts
  have null `applied_revision` and `closed_at`, applied drafts retain their original committed revision
  and closure time, discarded drafts have a closure time and null `applied_revision`. Staleness is
  derived from the current project revision, not another stored status. These are command records
  and resolution receipts, not saved preview snapshots, conversation context or approval records.
  Save validates through the ordinary preview engine at `expected_revision`, then stores normalized
  commands with generated object UUIDs. It takes 1–1000 ordinary edit commands (at most 256 KiB of
  canonical UTF-8 JSON, checked before and after normalization), a nonblank title of at most 1024
  characters and an explicit caller-provided `draft_id`. It retains the preview's 128 MiB source
  database limit. Formula errors follow ordinary edit semantics; successful save is not proof of
  error-free evaluation. The draft command schema accepts objects; backend command validation is
  authoritative and rejects non-edit operations. Repeating the same ID and original request
  (commands, title, base revision) returns the same draft, even after the project advances or the
  draft resolves. A changed request with the same ID returns `conflict`.
  List defaults to `offset=0, limit=100`, accepts a nonnegative offset and limit 1–100, and returns
  creation-order summaries containing every draft field except commands. It includes terminal records;
  `next_offset=null` ends pagination. Get returns the complete saved record. Save/list/get/discard
  never change table revision/history or emit `project.changed`; refresh explicitly across clients.
  Apply requires `expected_revision` equal to the saved base; a pending draft also checks the current
  project revision. Its ordinary edit and applied marker commit in one SQLite transaction, increase
  revision once, enter the usual edit/undo history and emit `project.changed`. Repeating an applied
  request with its original base returns `replayed=true` and the original application revision with
  no further edit or event, including after that edit has been undone. It never retargets to a later
  revision. Discard is idempotent for a discarded record; applied records cannot be discarded and
  discarded records cannot be applied. No API reopens a resolved record, overwrites its commands or
  removes it. These methods never automatically retry, open the native review view, or submit tasks.
  For uncertain responses retain the UUID and inspect the saved record before explicitly retrying
  the same save/application request. See [saved draft guide](../project-drafts.md).
- `project.contexts.*` and `project.discussion.*` are optional format 7 extensions. Check
  `hello.methods`; older projects require explicit backup/upgrade. These methods never call a model,
  execute message text, open files, apply drafts or submit work. They do not advance the editable
  revision, alter its history/undo stack or emit `project.changed`. Refresh lists explicitly across clients.
  Their records persist across project close/reopen; restoring a record triggers no action.
  Capture, add and link require separate caller-provided canonical UUIDs. Repeating the same ID and
  original request returns the same record; changing the request under that ID returns `conflict`.
  For uncertain responses retain IDs and inspect records before explicitly retrying; do not generate
  replacement IDs automatically. Records are immutable and have no overwrite/delete endpoint.
  All lists default to offset 0 and limit 100, accept limit 1–100, and return `next_offset=null` at the end.
- Context capture binds one project UUID and `source_revision` to exactly one selected table UUID,
  1–100 distinct record UUIDs and 1–64 distinct field UUIDs; their product is at most 1000.
  A stale `expected_revision` conflicts. Missing selected objects remain in selection and
  `diagnostics: {table_missing, record_ids, field_ids}`; selected objects belonging to another table
  are invalid. Names, types, units and selected literals/definitions/cached evaluations are frozen.
  Unset literals remain absent and explicit nulls remain present. Capture uses the selected rows and
  columns directly, without loading a full project snapshot, traversing unselected dependencies,
  reading referenced files or fetching task logs/credentials.
  A context has `id, project_id, title, source_revision, created_at, selection, content, diagnostics,
  limits, omitted_values`; the schema defines the exact closed object shapes. Selection contains
  `table_id, record_ids, field_ids`. Included content contains one table descriptor or null, selected
  field descriptors and records with `literals`, `definitions` and `evaluations` keyed by field UUID.
  Each part is explicitly `included` with its value, or `omitted` with a reason, byte size and SHA-256.
  Parts over 16 KiB use `value_limit`; unavailable evaluation caches use `evaluation_unavailable` and
  are not recomputed. A context exceeding the 256 KiB total budget instead retains an omitted content
  descriptor with `context_limit`, size and checksum. Omission is explicit, not silent truncation.
  List summaries exclude `content.value`; get returns the saved representation, including omission
  markers. Later edits or source deletion cannot change it; compare source/current revisions to assess
  staleness, and explicitly capture a new ID when new data is required.
- A discussion message is `{id, project_id, context_id, role, text, created_at}`. `context_id` must
  identify a saved context. `role` is `user` (default) or `assistant`, an informational label with no
  authentication or authorization meaning. Text must be nonblank and at most 64 KiB UTF-8; Markdown,
  code blocks and claims of approval remain inert text. List summaries omit text and include
  `text_bytes`; get returns the complete message. No generation request or active model session is implied.
  A proposal link is `{id, project_id, message_id, context_id, draft_id, base_revision, created_at}`.
  Its message/context and saved draft must belong to the same project, and context source revision
  must equal the draft base revision. Each draft has at most one provenance link; `proposals` accepts
  an optional exact `draft_id` filter. The link records provenance only and neither applies the draft
  nor changes its status; context selection is not an authorization scope for draft commands.
  Draft application retains all format 6 checks and atomic receipt semantics. See
  [context and discussion guide](../project-contexts.md) for usage and recovery boundaries.
- `project.requests.*` is an optional format 8 extension for durable text-request records. Check
  `hello.methods`; earlier formats return `unsupported` and require explicit backup/upgrade.
  The bridge exposes create/get/list/cancel/provider/start/recover. Creating a record saves intent;
  only explicit start can send the saved input. Get/list, opening a project and restoring a view
  never send or poll a provider. These methods do not change project revision/history/undo, apply
  a draft or submit a Runtime task, and emit no event, including no `project.changed`. Refresh
  explicitly to read changes from SQLite. The Python facade exposes the same seven operations as
  `p.requests.*` on its pinned handle; older bridges may expose only the first four methods.
- Provider returns exactly `{adapter, base_url, key_env, model_env, configured, model}` inside
  `{provider}`. The built-in adapter is `aliyun-token-plan/1`, with fixed base URL
  `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`, key environment variable
  `STK_TOKEN_PLAN_API_KEY` and optional model environment variable `STK_TOKEN_PLAN_MODEL`.
  `configured` reports plausible local credential presence, not authentication, account entitlement
  or network health. Model is an explicit bounded identifier, or the empty string if absent/invalid;
  there is no guessed default. A request always uses its saved configuration, not a later model
  environment change. Provider reads local configuration only and returns no credential value.
  Credentials, endpoint overrides and arbitrary adapter configuration are not accepted by any
  request method. Real account operation has not been validated; API compatibility does not establish
  STK's eligibility under the provider's current Token Plan tool/use terms.
- A request is the closed, flat object
  `{id, project_id, context_id, message_id, assistant_message_id, source_revision, configuration,
  prompt_version, input_sha256, created_at, status, cancel_requested, executor_id, updated_at,
  error_code, result}`. IDs are canonical lowercase UUIDs; `executor_id` is nullable.
  Create requires a caller-retained `request_id` and an existing `user` message in this project.
  It binds that message's saved context and source revision; it does not select the current table,
  add other conversation history or reread live data. `assistant_message_id` is derived from the
  project/request UUIDs and reserved against manual message insertion. `prompt_version` is `stk.text/1`;
  `input_sha256` covers canonical UTF-8 JSON containing exactly the saved context, user message,
  normalized configuration and prompt version. Complete input is limited to 1 MiB. Get/list return
  the same metadata shape without input values or message text. Each read verifies record checksums,
  the complete saved input lineage and, when completed, the linked assistant message and text digest.
- `configuration` requires `adapter` and `model`; its only optional fields are `temperature` and
  `max_output_tokens`. Identifiers are 1–128 ASCII characters matching
  `[A-Za-z0-9][A-Za-z0-9._:/-]*`; both schema and backend validation reject `//`. Temperature is a
  finite number in [0, 2]; output tokens are an integer in [1, 32768], default 4096. Returned
  configurations always contain this output limit; a supplied temperature is normalized to a number.
  URLs, credential fields and arbitrary provider parameters are not accepted. These names do not
  resolve to dynamic imports or network endpoints. Repeating a request UUID with the same message
  and normalized configuration returns its saved record, including its current terminal state;
  different input under that UUID is `conflict`. A changed input requires a new UUID. List defaults
  to offset 0 and limit 100, accepts a nonnegative signed-64-bit offset and limit 1–100, preserves
  creation order, includes terminal records and ends with `next_offset=null`.
- Saved request states are `pending` (intent saved, not claimed), `running` (claim persisted before
  a possible send), `completed` (full response and assistant message atomically saved), `failed`
  (known failure), `cancelled` (before dispatch or with confirmed cancellation evidence), and
  `uncertain` (a send may have occurred without a definitive result). Reading or reopening a project
  preserves the recorded state; `running` alone does not prove a live executor still exists.
  Cancel changes pending to cancelled with `cancel_requested=true` and
  `error_code="cancelled_before_start"`; running or previously uncancelled uncertain requests become
  uncertain with cancellation intent and `error_code="cancel_unconfirmed"`. Already-requested
  cancellation and completed/failed/cancelled records are returned unchanged. After persisting
  intent, this bridge signals its own worker's cancellation event if present. It cannot signal a
  worker owned by a different executor/process or confirm remote cancellation. The Token Plan
  adapter can prove cancellation only before submission; once submitted, it waits for the bounded
  complete response and a valid result may still be saved with the cancellation intent retained.
- `result` is null until completed, then exactly `{message_id, text_sha256, metadata}`; `message_id`
  equals the reserved assistant ID. Its full nonblank response is an ordinary immutable assistant
  message, at most 64 KiB UTF-8, read through `project.discussion.get`. Metadata accepts only optional
  `model`, `remote_request_id` (the same bounded identifier rules), and `input_tokens`, `output_tokens`
  (nonnegative signed-64-bit integers). It never contains raw response headers or exception text.
  The trusted local execution service inserts this message and marks completion in one SQLite
  transaction. A same-owner identical completion is idempotent; conflicting complete results are
  rejected. Confirmed cancellation/known failure cannot publish a late message; a complete result
  after unconfirmed cancellation may be saved while retaining `cancel_requested=true`. Completion
  does not create/apply a draft, interpret code blocks or submit work.
- The local `suan.project.request_executor.RequestExecutor` defaults to an empty trusted adapter
  registry; the bridge explicitly registers `AliyunTokenPlanAdapter`. Start first reads the saved
  request. A non-pending record is returned unchanged and never resubmitted. For pending work,
  start obtains its nonblocking OS lock, validates immutable input and runs optional adapter
  preparation before committing a single claim. Token Plan preparation validates the payload and
  credential locally and captures both in memory; failure returns `invalid_params` with the request
  still pending. Missing adapters likewise leave it pending. The prepared sender is invoked only
  after `running` and `executor_id` are committed. Start acknowledges that claim without waiting
  for the network response. It holds no SQLite transaction during network I/O and never retries.
  A live execution lock prevents another sender or local recovery (`busy`).
- Explicit recover only acts on `running`: it must acquire the request's free OS lock before marking
  it `uncertain/executor_lost`; other states are returned unchanged. It does not send, query a provider
  or revert to pending. Closing a project handle or switching projects leaves accepted work bound
  to the original project UUID and database. Bridge shutdown fences late responses and asynchronously
  attempts to mark active work uncertain; a live worker retains its lock until it exits. If persistence
  is unavailable or process exit interrupts cleanup, later explicit recover can reconcile a saved
  running claim. Neither shutdown nor recovery proves remote cancellation.
  The fixed journal error codes are `adapter_unavailable`, `adapter_failed`, `response_invalid`, `dispatch_failed`
  (failed), `executor_lost`, `cancel_unconfirmed`, `transport_uncertain`, `local_save_failed`
  (uncertain), and `cancelled_before_start`, `cancel_confirmed` (cancelled). Pending/running/completed
  have null `error_code`. The fixed Token Plan adapter uses one verified HTTPS Chat Completions
  POST with `stream=false` and `enable_thinking=false`; it sends no tools. It accepts only one complete
  assistant text with `finish_reason=stop`, rejects tool/function output and truncation, bounds the
  HTTP body to 1 MiB and the saved text to 64 KiB, and uses a 60-second socket timeout with elapsed
  deadline checks between operations. It follows no redirects, uses no proxy and makes no retry.
  This adapter requires temperature below 2, within the generic configuration range above. Known
  rejection responses are failed; transport errors, ambiguous statuses and timeouts remain uncertain.
  No remote cancellation/query, streaming, token counting or tool execution is implemented. See
  [request guide](../project-requests.md) for configuration, exact transport scope, lock guarantees
  and save-failure limits.
- **Uncertain responses:** create/apply/backup/upgrade/undo/redo and file index/refresh are never automatically retried. If a response is lost,
  reopen the directory and inspect snapshot/history before deciding what to do next. Do not merely
  raise `expected_revision` and repeat an edit: the previous batch may already have committed.
  Explicit reapplication at the original revision cannot commit twice. Opening an already created
  project is safe; repeating create reports `conflict`. These methods use no idempotency key.
- A successful apply, undo/redo or effective upgrade emits `project.changed {handle, revision}` after its response. An effective
  close emits `project.closed {handle}` after its response. Concurrent request responses/events may
  interleave: ignore closed handles and revisions at or below the displayed snapshot. Events are
  refresh hints, not an ordered history stream. External CLI edits have no bridge event; refresh
  snapshot/list to see them, and rely on revision conflicts before writing.
- Snapshot/history are currently unpaginated and subject to the 16 MiB line limit (§2), returning
  `result_too_large` when necessary. Large scientific arrays and files do not belong in JSON cells.
  No project directory is automatically reopened by a new bridge; the desktop owns recovery intent.

CSV imports create a new table using the ordinary atomic edit batch and publish `project.changed` after
success. Source/destination paths are absolute on the bridge; delimiter is comma (default) or tab.
Types map header names to the five existing field types (default text); units apply only to numeric
columns. Export materializes a consistent revision and rejects evaluation errors; it never overwrites
an existing destination and does not change project revision. Both files are bounded to 8 MiB and 64
columns; import also observes the 1000-command transaction limit, export a 10000-row limit. See
[CSV exchange](../project-csv.md) for null/empty handling and the exclusive file-publication requirement.

Recent locations are bridge preferences (`recent-projects.json`, version 1), at most 20 entries in
most-recently-opened order. Creating/opening successfully remembers canonical directory, project UUID,
last known name and UTC ISO timestamp. Listing reads saved metadata only, without opening or stat'ing
the projects; missing locations remain listed. Forgetting never deletes project files or closes handles.
An optional `expected_id` on open rejects a replaced project before registering a handle or updating history.
History persistence failure is a `warning` in `project.recent`, not a failed project create/open; an
explicit forget that cannot persist fails with `unavailable`. Corrupt/unknown history is preserved and
reported, never silently replaced. Preferences do not advance project revisions or emit project change events.

## 14. Local Python sessions and desktop control (additive extension)

Discover the methods/events in `hello`; older v1 bridges may not implement this extension.
It adds an explicit reverse request direction on the **existing private local stdio connection**,
not a network service, remote Python permission, or an implicit interpretation of old events.
The shared schema remains authoritative. The user-facing API and coverage are in [scripting](../scripting.md).

### Python session methods

| Method | Parameters | Result |
|---|---|---|
| `script.open` | optional initial absolute `directory` | session status |
| `script.status` | `session` | session status |
| `script.execute` | `session`, exactly one of `source` / absolute `path`, optional `project_handle` | `{run}` |
| `script.read` | `session`, optional `cursor` (0), `limit` (65536, max 65536) | status plus `{text, cursor, truncated}` |
| `script.interrupt` | `session` | `{interrupted}` (whether execution was running) |
| `script.close` | `session` | `{closed: true}` |
| `script.catalog` | none | `{operations: {name: {params, result}}, ui_operations}` |

One bridge owns one shared Python session. Open is idempotent; a different initial directory while
it is open is a conflict. Tokens and run/kernel IDs are opaque 32-digit lowercase hex strings.
Status is `{session, state, kernel, directory, run, output_start, output_end}`:
`state` is `ready`, `running` or `stopping`; `kernel` is null when no worker exists.
`run` is null or `{id, state, filename, error}` with run states `running`, `succeeded`, `failed`,
`cancelled`. Python exceptions are printed and produce `failed` with a null structured error;
worker transport/crash failures include an error object. `directory` is the initial directory,
not a continuously tracked `os.getcwd()`.

Execute acknowledges a run before starting it, rejects overlapping runs with `busy`, and never
automatically replays. Source and UTF-8 file limits are in the schema/guide. A disposable worker
preserves globals between runs. The bridge, project transactions and submitted Runtime tasks keep
their independent lifetimes. Interrupt kills the worker tree (also resetting an idle namespace);
an already accepted operation may finish and must not be blindly repeated. A slow in-flight project
operation can keep the session `stopping` until its outcome is known to the bridge.
The script operation catalog also exposes graph catalog/presets/validation/evaluation/cancellation,
blob lookup, probes and colormaps. A console `graph.evaluate` is tied to that execution's cancellation:
interrupting cancels its local graph work (queued work leaves another active evaluation untouched).
In Hub mode it only stops waiting, without sending a remote cancel action; accepted node work remains
recoverable by the caller-owned eval ID. Viewer polling has independent ownership and is not cancelled
by stopping a console wait. See [graph scripting](../scripting-graphs.md).

`script.changed {session}` is a refresh hint, coalesced until `script.read` acknowledges it; start/end
transitions also emit a hint. Output is bounded to 1 Mi Unicode characters, read offsets count Unicode
codepoints, and the returned cursor is the next position. A stale cursor is clamped to `output_start`
with `truncated=true`; a cursor beyond `output_end` is invalid. Read until cursor reaches the returned
end, retaining hints that arrive while a read is in flight. Native descriptor/subprocess output goes
to bridge stderr. EOF/close/shutdown stops the worker; restarting never restores or auto-runs code.

### Explicit reverse desktop requests

- `ui.attach {operations}` returns `{session, operations}`. The local client advertises supported
  operation names: `layout.get`, `layout.apply`, `editors.list`, `project.current`, `project.open`,
  `project.close`, optional `project.review`, `project.selection`, `project.select`, plus the Viewer
  operations below. The current supported set contains 21 operation names; discover and negotiate
  names rather than assuming support from that count. Reattaching the same set is idempotent; changing it requires detach.
- `ui.request {session, request, operation, params, expires_at_ms}` asks that executor to perform one
  operation. Requests are correlated by both IDs, expire after 30 seconds, and are never replayed.
  `expires_at_ms` is a UTC Unix timestamp in milliseconds on the same machine. The desktop rejects
  expired requests before starting them, and always runs window/layout changes on its main thread.
- `ui.reply {session, request, result}` or `{session, request, error}` returns `{accepted}`.
  Results are objects, errors use the normal bridge error schema. Both/neither are invalid.
  Late, duplicate and detached-session replies return false. A reply is not a second execution.
- `ui.detach {session}` returns `{detached}` and fails outstanding calls with `unavailable`.
  Shutdown does the same. Cancellation drops a pending request; timeouts/cancellation do not roll
  back a UI mutation that the desktop already accepted. Inspect state before retrying it.

Operation shapes: `layout.get {}` → `{layout}` (`stk.desktop.layout/1`),
`layout.apply {layout}` → `{applied: true}`, `editors.list {}` → `{editors: [{id, label}]}`,
`project.current {}` → `{project: projectInfo|null}`, `project.open {directory}` → `{project: projectInfo}`,
`project.close {}` → `{closed: boolean}`. Viewer adds `viewer.status`, `viewer.presets`,
`viewer.open {path, preset?, parameters?, focus?}`, `viewer.close`, `viewer.configure`, `viewer.preset {id}`,
`viewer.evaluate`, `viewer.cancel`, `viewer.layer {id, visible?, opacity?}`, `viewer.step {index}`,
`viewer.play {playing}`, and `viewer.reset_camera`. Mutations except open accept optional `expected_source`,
checked against the current source key before applying. Configure validates all supplied parameters/display
settings before changing any; graph semantic/data errors can still occur asynchronously. Open returns acceptance,
not completion. Status reports current source, parameters, layers, pending/evaluating flags, errors and timeline.
Presets returns `{ready, presets, error}`; other operations return status. The shared Viewer data model is global
across windows; open focuses an existing Viewer tab or adds one unless `focus=false`. These are local UI operations,
not network endpoints. See [Viewer scripting](../scripting-viewer.md) for exact options and wait semantics.
 Invalid parameters return `invalid_params`; absent capabilities
return `unsupported`, and an absent desktop returns `unavailable`. Applying a layout validates the whole
description before changing the current screen; geometry is captured for round trips but not forced on apply.

The additive `project.review {handle, expected_revision, commands}` operation returns
`{accepted: true, project_id, base_revision}`. The handle must be the visible project's current bridge
handle, with a matching nonnegative int64 revision, checked when the queued request executes.
`commands` is a nonempty array of up to 1000 ordinary project edit commands; its compact JSON encoding
must fit 256 KiB. No extra parameters or caller-supplied preview snapshots are accepted. The native
client starts `project.preview` and focuses the first window's Project review view, adding a tab if
needed. Acceptance precedes evaluation; semantic command errors appear in that view. No database
write or external execution occurs. Only explicit native Apply submits the normalized preview commands
at their original revision; ordinary edit history and undo apply.

A mismatched/closed project or changed revision returns `conflict`. Existing draft text, a candidate
or a preview error also returns `conflict`; scripts cannot replace/clear reviews. The user must inspect
and clear the draft first. A busy/unloaded project or active text edit in any attached window returns
`busy`, preserving uncommitted text. Discard/input changes invalidate pending candidates; project
switch/close and bridge restart clear reviews. Timeout/cancellation does not undo accepted previews.
These lifecycle rules concern the current review editor and candidate. A separate explicit native
save through `project.drafts.save` can persist the checked commands; restarting does not load or apply
that record automatically. Loading a pending record requires an empty review and another explicit
preview. A stale saved record must be copied into a new draft for review at the current revision;
its original record is retained. Clearing the review editor never discards a saved database record.
Capability discovery/attachment includes `project.review` only when both bridge and client support it;
the original six-operation fallback is unchanged. The Python facade exposes this as
`stk.project.review(commands, expected_revision=...)`. See [project preview](../project-preview.md).

The optional reverse UI operation `project.selection {handle}` returns the flat object
`{project_id, revision, table_id: uuid|null, record_id: uuid|null}` for the currently loaded shared
project selection. It performs no database read or implicit refresh. The facade's handle must match
the current native project. The project controller must be ready, loaded and idle, without a known
newer revision awaiting refresh. Active text input alone does not prevent this read. Null table or
record IDs indicate no corresponding shared selection; the result contains no editor-local field
selection, search query or filtered row set.

`project.select {handle, expected_revision, table_id, record_id}` validates the same native project
handle, a matching nonnegative int64 revision, canonical non-null UUIDs, and an existing record
belonging to the requested table. It validates both targets before atomically changing the shared
table/record selection, and returns the same flat selection object. Invalid UUIDs/parameter shapes
are `invalid_params`; a current project/handle/revision mismatch is `conflict`, and a missing table or
record outside the requested table is `not_found`. Rejection leaves the selection unchanged.
Any active text edit in any attached window makes this write `busy`, preserving uncommitted input.
Neither operation opens a project/editor, moves focus, changes tabs, clears view-local filters or
replaces an existing review. A selected row may be hidden by an editor's local filter. Selection
does not modify the database, advance revision, emit `project.changed`, capture context or submit work.

These are explicitly negotiated local UI operations, not new ordinary project bridge methods or
remote endpoints. `script.catalog.ui_operations` and `ui.attach` advertise them when supported;
the original six-operation fallback remains unchanged. Python exposes `p.selection()` and
`p.select(table_id, record_id, expected_revision=...)`, passing the facade's pinned project handle.
The executor checks preconditions when the queued request runs and follows the session/expiry rules
above; neither request is automatically replayed. An external writer may have advanced SQLite
without a desktop event: returned revisions describe the loaded snapshot, and subsequent
`project.contexts.capture` or edits must still pass their database revision check. See
[selection scripting](../scripting.md#查询和改变原生共享选择) and
[explicit capture from selection](../project-contexts.md#从原生共享选择明确捕获).

The Python facade exposes project methods, saved connection inspection/managed SSH, workspace/task
operations, transfers and read-only Hub discovery/action queries through the shared command handlers.
`script.catalog` is authoritative for current coverage; it excludes recursive script lifecycle, unowned
subscriptions, executor attachment and Hub review approval. Runtime helpers require explicit idempotency
keys for creation/submission/cancellation/transfers and preserve pending Hub action envelopes. Waiting
only polls; interruption or timeout does not cancel accepted work. See [Python guide](../scripting.md).
The native
desktop binds these UI operations on its main loop, targeting the first installed screen.
Stale callbacks from an earlier bridge session cannot apply queued layout changes. A bridge without
that executor (for example a protocol test harness) must attach its own implementation or return unavailable.

`task.logs {connection, node?, task_id, stream?, offset?, limit?}` is an additive one-shot read for
automation. Defaults: `stream: "stdout"`, `offset: 0`, `limit: 65536`; limit is 1–1048576 bytes.
Result is `{data: base64, offset, next_offset, terminal}`. Both offsets count bytes, including partial
UTF-8 characters. `terminal` describes task state, not whether this chunk exhausted the log; a caller
continues from `next_offset` until an empty chunk. The bridge clamps older Hub responses to the limit
and adjusts `next_offset` to bytes actually returned. No subscription or background reader is created.

## 15. Managed OpenSSH Runtime connections (additive extension)

`connections.add_runtime` accepts optional `ssh: {host: string}`. In that case `url` names the
**remote** loopback Runtime endpoint and must contain an explicit nonzero port. `host` is an OpenSSH
Host alias or `user@hostname`, not a command/options string. Token/token_file and `check` retain
their existing meanings. A failed candidate health check does not replace the previous profile.
Omitting `ssh` preserves direct/external-tunnel behavior.

Saved SSH connections in `connections.list` and `connections.add_runtime` include
`ssh: {host?, state, url, error}`. States are `stopped`, `ready`, `failed`; `url` is a temporary
local loopback endpoint only when ready, otherwise null. It is not the connection's saved remote URL.
This status describes the tunnel; use `connections.check` to check Runtime authentication/health.
Listing/status never initiates an SSH connection. Diagnostics are bounded and tokens are not returned.

`connections.ssh {id, action}` returns `{connection: id, ssh}`. Actions:

- `status`: inspect the managed profile without starting it;
- `connect`: clear an explicit disconnect and establish/reuse its tunnel;
- `disconnect`: close the owned tunnel and inhibit implicit reconnection for this bridge session.

The method returns `invalid_params` for direct/local/hub profiles and `not_found` for missing profiles.
Connection failures return `unavailable`. A bridge without this extension omits it from `hello.methods`.
These explicit control requests are not automatically replayed by the native client.

Runtime operations start tunnels on demand and re-establish an exited SSH process on a later operation,
unless explicitly disconnected. No HTTP request is replayed by this transport. Transfer/submission
idempotency remains the responsibility of the existing operation contracts. Profiles share a tunnel;
removing/replacing a profile closes its old tunnel and invalidates clients holding it. Source/cache identity
uses the Host and remote endpoint, not the ephemeral local port.

OpenSSH uses user config and existing key/agent authentication, strict known-host verification, loopback
forwarding and keepalives. No interactive prompt, password persistence, automatic host trust, remote
service installation or remote Python/UI access is introduced. A private guardian watches parent-pipe EOF
and cleans up SSH descendants on bridge death; shutdown/removal never cancels Runtime tasks.
See the [SSH guide](../ssh.md) for setup, restart behavior and current validation limits.
