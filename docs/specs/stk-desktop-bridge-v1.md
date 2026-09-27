# STK desktop bridge protocol v1

> 中文摘要：桌面程序（GPL，C++）通过子进程 `python -m suan.desktop_bridge --stdio`（MIT）访问 STK：标准输入输出上逐行传输
> JSON（NDJSON），请求带 `id`、响应按 `id` 对应、事件由桥主动推送，错误码稳定。桥持有全部凭据（运行时令牌、控制服务设备令牌），
> 程序只见不透明的连接 ID；大数据经内容寻址缓存 `<cache>/blobs/<aa>/<sha256>` 由程序内存映射。上传下载可续传、有日志、下载经
> sha256 校验；提交任务带幂等键；日志按字节偏移增量推送且跨块多字节字符安全；关闭程序不会停止任务。

Status: **frozen for Milestone D1** (WP7), with the additive hub-mode changes of WP11 (§7.1, §9,
§10, §1 state-directory lock) and the WP8 follow-ups (`bytes` in offset-based events, transfer
idempotency keys, ids of undecodable lines, clarifications in §2, §3, §7, §8, §12); still
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
  hub actions are never cancelled**: closing the app keeps jobs running.
- **Crash and restart.** If the bridge dies, the app starts a new one, sends `hello` (which by
  default resumes interrupted transfers) and replays its subscriptions from the offsets it last
  received (§8). Every operation that creates something takes an idempotency key, so replaying a
  request whose response was lost never creates a second workspace, task or hub action.

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
| `busy` | yes / no | Two meanings: too many requests in flight (`retryable: true`: repeat later), or another bridge holds the state directory (§1; `data.state_dir`, `retryable: false`: the bridge will not serve anything and exits with status 3) |
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

- `spec` is a Runtime `TaskSpec` (`workspace_id, argv, backend?, name?, inputs?, outputs?, env?,
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
| `transfer.resume` | `id` | `{transfer}` (continues an `interrupted`, `failed` or `cancelled` transfer) |
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
- **Retry ordering.** A retry immediately after a terminal event is accepted even if the previous
  worker is still cleaning up. It returns `queued` and runs after that worker releases the transfer
  lock and concurrency slot. Repeated resumes while queued/running do not start duplicate attempts;
  completed transfers remain completed. A queued retry can be cancelled, and closing the bridge
  leaves it resumable from its journal on the next start.
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
