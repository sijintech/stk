# Jobs editor: parity with the legacy Tasks tab (WP9)

> 中文摘要：本表逐项对照旧版 PyQt “任务”页（`suan/gui/Tab/runtime_tab.py`）与桌面程序的任务编辑器（WP9），列出实现位置与验证测试。
> 旧版的全部功能均已实现；另按计划增加了控制服务配对与审核、传输编辑器、监控事件、重试策略、MPI 资源等。差异见文末。

The legacy tab is `suan/gui/Tab/runtime_tab.py` (PyQt, one Runtime client, HTTP in worker
threads, a 2 s timer). The desktop replacement is the Jobs editor and its companions (Transfers,
Logs, Bridge log) in `desktop/engine/lib/stk_app` (`jobs_state.hh`, `jobs_spec.hh`,
`src/editors/jobs_*.cc`), talking to the Python bridge (`docs/specs/stk-desktop-bridge-v1.md`)
instead of the Runtime directly.

Status: **done** = implemented and covered by the test named; **changed** = same purpose, different
behaviour (explained); **deferred** = not in D1.

Tests: `desktop/tests/app` (`stk-jobs-tests`: `JobsSpec.*` form rules, `JobsFake.*` state machines
on `stk-bridge-fake --jobs`, `JobsLayout.*` UI with synthesized events, `JobsPython.*` the real
bridge and a loopback Runtime; `jobs_render_*` / `jobs_golden_*` GPU goldens; `jobs_live_*` live
windows on Xvfb and weston).

## Legacy Tasks tab items

| # | Legacy behaviour (runtime_tab.py) | Desktop | Status | Test |
|---|---|---|---|---|
| 1 | "运行位置" dropdown: 本机 plus the `suan connect` profiles | Connection dropdown from `connections.list`: this computer (local Runtime), Runtime profiles (shared with `suan connect`), paired hubs | done | `JobsFake.ConnectsChecksHealthAndWatchesTheWorkspace` |
| 2 | "连接": starts the local Runtime daemon when needed, checks `health` (API version 1), "已连接" / "已连接，但任务调度服务未运行" | Selecting a connection checks it (`connections.check`); health shown as connected / connected with problems (supervisor stopped, API version, node offline) / unreachable with the reason, also in the status bar; local Runtime status line with a Start button (`connections.local_start`) | done | `JobsFake.ConnectsChecksHealthAndWatchesTheWorkspace`, `JobsFake.AddPairRemoveConnectionsAndTheLocalRuntime` |
| 3 | "添加连接" dialog: name, forwarded URL (default `http://127.0.0.1:9876`), token (password echo), SSH-tunnel hint; health check before saving; then connect | Add Runtime dialog: name, address (same default), token (masked field) or token file (Browse…), "check before saving", the same hint; `connections.add_runtime`; errors shown in the dialog; connects to the new profile | done | `JobsLayout.AddRuntimeDialogAndThePathFieldFallback`, `JobsFake.AddPairRemoveConnectionsAndTheLocalRuntime` |
| 4 | Status label: progress and errors ("操作未完成：…"); "关闭桌面不会取消服务器任务" | Status line at the top of the Jobs editor (every outcome also goes to the Logs editor); the hint "Closing the desktop never cancels tasks" | done | all `JobsFake.*` (status checks) |
| 5 | Workspace dropdown; switching clears logs, outputs and inputs and refreshes | Workspace dropdown (`workspace.list`); switching drops the watch, detail, logs, artifacts and preview and re-subscribes; late results of the old selection are dropped (epochs) | done | `JobsFake.SwitchingConnectionDropsStaleResults` |
| 6 | "新建" workspace (name prompt) | New… dialog → `workspace.create` with an idempotency key; the new workspace is selected | done | `JobsPython.*` |
| 7 | "上传文件" (multi-select dialog) | Upload files… : native dialog (zenity / kdialog), else a path field (one per line or `;`, `file://` URIs, `~`) | done | `JobsLayout.NativeDialogPathsAndItsFallback`, `JobsLayout.AddRuntimeDialogAndThePathFieldFallback` |
| 8 | "上传文件夹" (recursive) | Upload folder… → `upload.start` of the folder (every regular file, symbolic links not followed) | changed: files land under `<folder name>/…` (the bridge's rule), the legacy tab put the folder's contents at the workspace root | `JobsPython.*`, `JobsFake.UploadsWaitForAWorkspaceThenCompleteAndBlockSubmitting` |
| 9 | Uploads verified; "已上传并校验 N 个文件"; Submit disabled while uploading | Resumable, sha256-verified uploads with progress bars; "Uploaded and verified N file(s)"; Submit disabled (and refused) while uploads into the workspace are unfinished | done | `JobsFake.UploadsWaitForAWorkspaceThenCompleteAndBlockSubmitting` |
| 10 | Input-file list; double-click → save-as download → open | Input files list (`workspace.files`); Enter / double-click → destination chooser → verified `download.start` → opened (preview, Viewer or the system) | done | `JobsFake.InputFilesDownloadToAChosenDestination` |
| 11 | Form: task name, program (`{python}`), arguments (shlex, quoting hint), backend local / pbs / slurm | Same fields; arguments split exactly like Python's `shlex.split`; the name accepts IME input (Chinese) | done | `JobsSpec.ShlexSplitsLikePython`, `JobsLayout.SubmitFromTheFormWithAChineseName`, `jobs_live_*` |
| 12 | "资源配置": CPUs per node, nodes, memory MB (0 = default), walltime s (0 = default), queue, account | Resources panel: the same plus GPUs and MPI (`ranks`, `threads_per_rank`, from `suan/runtime/models.py`); 0 / empty = the environment's default, never written into the spec | done | `JobsSpec.ResourcesOutputsAndEnvironment` |
| 13 | Submit: `TaskSpec` errors shown; one `uuid4` idempotency key per submission; "请先选择工作区" | Live validation with the `TaskSpec` rules (workspace, argv, name ≤ 200 characters, outputs, env names and reserved variables, resource ranges, cpus vs MPI, ranks multiple of nodes, local backend limits) in zh / en; a fresh 32-hex key per submit | done | `JobsSpec.ValidationFollowsTheRuntimeTaskSpec`, `JobsSpec.IdempotencyKeysAreFresh32Hex`, `JobsFake.SubmitRunsStreamsLogsEventsAndListsArtifacts` |
| 14 | "重试上次提交" (same key) after a failure: "系统会识别重复请求" | Retry last submission (same key); plus an automatic retry policy (N re-sends with backoff on retryable errors, same key) | done | `JobsFake.ManualRetryAfterAFailedSubmission`, `JobsFake.AutomaticRetryReusesTheIdempotencyKey` |
| 15 | "任务已登记：<id>" | "Task registered: <id>"; the new task is selected | done | `JobsFake.SubmitRunsStreamsLogsEventsAndListsArtifacts` |
| 16 | "刷新" and a 2 s timer polling tasks, files, logs, artifacts | `watch` subscription (snapshots every 2 s, each replaces the list: state, not deltas), `logs.subscribe` / `events.subscribe` push; Refresh in the header re-reads connections, workspaces, tasks and transfers | changed: push instead of polling (restart-safe replay by the client) | `JobsFake.BridgeRestartClearsInspectionsAndKeepsWatching` |
| 17 | "取消选中任务" | Cancel task (confirmation dialog) → `task.cancel` with a key; "cancelling" until the Runtime reports cancelled | done | `JobsFake.CancelShowsCancellingThenCancelled` |
| 18 | Task table: name (or id[:12]), state (准备中 … 待核实), backend, reason; "正在取消"; selection kept across refreshes | Sortable table: name (or id[:12]), state (same localized names, "cancelling"), backend, submitted, note; state colours; selection kept by task id | done | `JobsLayout/JobsLayoutGolden.*`, `jobs_golden_*` |
| 19 | Log view: stdout / stderr incremental (UTF-8 safe), stderr prefixed, 10 000 lines, placeholder | Log view with follow-tail: stdout + stderr (stderr lines marked `[stderr]`, whole lines only), or each stream alone; 10 000 lines; "live" / "complete" | done | `JobsFake.SubmitRunsStreamsLogsEventsAndListsArtifacts`, `JobsPython.*` |
| 20 | Outputs list; double-click → download into the cache, verify, open | Results tab: artifacts with size and a verification column; Download (cache, sha256 verified by the bridge and re-checked on disk, then opened) and Save as… (destination chooser); progress bar | done | `JobsFake.DownloadIsVerifiedAndPngIsPreviewedAsATexture`, `JobsPython.*` |
| 21 | Open a result: PNG / JPG preview, `.vtk` into the VTK view, else the system's application | PNG decoded with `stk_io` and shown in the image widget as a GPU texture; `.stkp`, `.vtk` and folders go to the Viewer (`AppStore::request_open_result`); Open in Viewer for the task; other files with the system (`xdg-open` / `open`) | changed: JPEG is opened with the system (stk_io decodes PNG only) | `JobsFake.DownloadIsVerifiedAndPngIsPreviewedAsATexture`, `jobs_render_*` |
| 22 | Connection epoch: results of an old connection are ignored | Epochs per connection, per connection+node+workspace and per selected task | done | `JobsFake.SwitchingConnectionDropsStaleResults` |

## Additions from the D1 plan

| Item | Desktop | Status | Test |
|---|---|---|---|
| Pair a hub with a one-time code | Pair hub… dialog (`connections.pair_hub`: name, HTTPS address, code (masked), device name) | done | `JobsFake.AddPairRemoveConnectionsAndTheLocalRuntime` |
| Remove a connection | Remove… with the warning that a Runtime profile also disappears from `suan connect` (hubs: the pairing is forgotten locally, not revoked) | done | `JobsFake.AddPairRemoveConnectionsAndTheLocalRuntime` |
| Hub nodes, templates, policy | Node dropdown (`hub.devices`, first online node), templates (`hub.templates`), device profile and review policy (`hub.policy`) | done | `JobsFake.HubCustomSubmitGoesToReviewThenRunsAfterApproval` |
| Hub submit: template vs custom | Template submits run at once; a custom command becomes an action in review, shown as such; after approval the same key is sent again and returns the task | done | `JobsFake.HubCustomSubmitGoesToReviewThenRunsAfterApproval` |
| Hub review panel | Actions in review (`hub.actions`, followed through `hub.subscribe`): Inspect (`hub.action`, full request shown), Approve (only after inspecting), Reject | done | same |
| `review_policy` refusal | `unauthorized` with `data.reason == "review_policy"` explained with the hub's policy and the advice to ask the hub owner | done | `JobsFake.ReviewPolicyRefusalIsExplained` |
| Re-inspect after a bridge restart | Inspections are per bridge process: cleared on restart; a `review_not_inspected` answer re-reads the action and asks to approve again | done | `JobsFake.ApprovalAfterABridgeRestartReadsTheActionAgain`, `JobsFake.BridgeRestartClearsInspectionsAndKeepsWatching` |
| Hub uploads in review | Transfer shown "in review" (`action.state: "review"`, bytes all sent) until the `workspace.import` is approved; cancel withdraws it | done | `JobsFake.HubUploadWaitsForTheImportReview` |
| Drag and drop | Files / folders dropped on Jobs or Transfers are uploaded into the current workspace (queued until one is chosen) | done | `JobsLayout.DropsOnJobsAndTransfersQueueUploads` |
| Transfers editor | All transfers (journaled by the bridge): file, direction, %, size, state (colours), updated; Resume (interrupted / failed), Cancel; details of the selection | done | `JobsLayout.TransfersEditorResumesAndCancels` |
| Monitoring events | Monitor tab: program, progress (bar), step / total, phase, latest metrics, counts of frames / checkpoints / warnings / errors, latest message, program's completion claim, verification, unreadable lines | done | `JobsFake.SubmitRunsStreamsLogsEventsAndListsArtifacts` |
| Status-bar connection | `AppStore::set_connection("<name> · <health>")` | done | `JobsFake.ConnectsChecksHealthAndWatchesTheWorkspace`, `jobs_live_*` |
| Logs / Bridge log editors | App log (every operation's outcome, Clear); the bridge's stderr ring with state, pid, restarts, calls and Restart after Failed | done | `wm` goldens |
| Closing the app never stops jobs | Detaching drops subscriptions only; the bridge gets EOF, no `task.cancel` / `transfer.cancel` | done | `JobsFake.ClosingTheAppNeverCancelsTasks`, `JobsPython.*` (the task finishes after the app closed), `jobs_live_*` |

## Differences and deferred items

- Folder uploads keep the folder name as a prefix (`upload.start` has no way to put a folder's
  contents at the workspace root: `remote` must be a non-empty relative path).
- JPEG results open with the system application; only PNG is previewed.
- Native file dialogs: Linux through `zenity` / `kdialog`; macOS and Windows use the path field
  until nativefiledialog-extended is wired (stk_platform keeps the same interface).
- The Runtime `TaskSpec` has no retry field: the retry policy is the client re-sending the same
  idempotency key (never a duplicate task).
- Hub node snapshots carry no task spec, so the backend column is empty for hub tasks.
