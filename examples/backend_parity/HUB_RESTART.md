# D1 Hub restart at the lost-result boundary

This D1 fault slice follows [the parity run](README.md) and [the node disconnect](DISCONNECT.md). The Hub
dies at a precise point:
- the Runtime has accepted the one submission, and its real program and worker run;
- the Hub's original `task.submit` action is still `queued`, with no result.

The same Hub then restarts and the original queued action is delivered again. The Runtime and the NodeAgent
process survive throughout.

There is one program start, one task and one run directory. The second delivery is answered with the
original task.

This is not a failover, network partition or cross-host test. It adds no product command, contract,
endpoint or state. `hub_restart.py` loads `disconnect.py`, and through it `offline.py`, by file path; it does
not change them. In installed mode nothing is put on `sys.path`.

## Deployment and the test driver

One private loopback deployment:

| Process | Started with |
|---|---|
| Runtime API and supervisor | `suan server init` / `start` |
| Hub, with the exact `parity-wait` template | `suan-control init` / `serve`; later the same `serve` command again |
| NodeAgent | the real `suan-node run`, through the test driver below |

The **driver** is the `DRIVER` text in `hub_restart.py`. Each run writes it into its own private directory
and hashes the file twice:
- once after writing it, before any service starts;
- once more immediately before the NodeAgent launch.

Both must equal the harness's own `DRIVER` digest. Otherwise the run fails with a fixed error, and the driver
is never launched. This binding is check H0, and the run also requires it explicitly. Missing or mismatched
proof fails, even when every other check and cleanup passed.

The driver wraps real methods and then calls the real `suan.control.cli:node run`:
- **`NodeAgent.execute`** always runs the real `execute` first: a real `Runtime.submit` and the real
  action-cache write. For the first `task.submit` only, it then holds the return until two things are true:
  the harness has written a release file (after killing the Hub), and the agent's own `_send` is `None` (the
  agent noticed the disconnect). The hold is bounded by the run budget.
- **`NodeAgent._perform`** is only staged: when the first delivery finishes, the driver records whether
  `_send` was `None`. The real `_perform` reads `_send` after `execute` returns. Here it found no connection
  and dropped the first reply, so the Hub kept the action queued.
- **`RuntimeClient.submit`** is only counted. Each call stages its idempotency key and the task ID returned.

The driver changes no result or business state. Its stages are observations bound to its source: call
numbers, cache hits, returned task IDs and `_send`.

## Scenario

1. **Accepted before the loss.**
   - Create one workspace, then make one client submission. Its reply wait (3 s) times out while the result
     is held.
   - The Runtime holds exactly one task, and the driver staged that same task ID from the real
     `Runtime.submit`.
   - The program prints its ready line. Its program and worker identities (PID plus create time) and its
     single start marker are frozen.
   - The Hub's public action record (`GET /api/v1/actions/{id}`) is `queued`, with no result.
   - The Hub, NodeAgent, Runtime API and supervisor are alive.
2. **The fault.**
   - The Hub's identity was frozen when it started. It must be alive right before the kill. Its process
     group is then sent SIGKILL and reaped, and it must have exited by that SIGKILL, with the frozen identity
     gone.
   - A Hub that had already exited, exited cleanly, crashed or was stopped by another signal fails.
3. **The outage.**
   - The original task is still running on the owned Runtime, with the same program and worker. The NodeAgent
     process and the Runtime stay alive.
   - Hub reads are refused as unavailable, never answered with a task state.
   - The held result is released only after the disconnect (`_send` is `None`). The first delivery then
     finishes with no connection, before the Hub restarts: the first reply was dropped.
   - Before the restart, the node had seen exactly one delivery.
   - The harness restarts the Hub only after it has read the driver's first-delivery stage. The stage's time
     is also compared with the restart time. Both clocks are `time.monotonic()`, the system-wide
     `CLOCK_MONOTONIC` on Linux, so they compare across the two processes.
4. **The restart.**
   - The harness runs the identical `serve` command again: the same state directory and database, the same
     templates and the same port.
   - No `init`, pairing, profile or workspace call follows the restart.
   - The same NodeAgent process reconnects as the same, only node device.
   - Reusing the command only describes what the harness did. The proof that the pre-fault state came back is
     what the new Hub process answers: it lists the pre-fault node device, and it holds the pre-fault action
     with the same request digest.
5. **The recovery.**
   - The Hub delivers the original queued action again, with the same ID and the same request digest.
   - The agent's persisted action cache answers it with the original task:
     - the second `execute` call finds the cached result;
     - `Runtime.submit` is not called again.
   - The action succeeds with the original task. The evidence classifies the path as `node action cache`. A
     second `Runtime.submit` with the same identity would be classified as `Runtime idempotent replay`.
   - No caller resubmits, uses another key, path or authority, or creates a workspace.
6. **After the recovery.**
   - A live read returns the original running task, with the same program and worker and one start marker.
   - The action listing has the same action IDs; only the submission's state changed (`queued` to
     `succeeded`).
7. **The cancel.**
   - An explicit cancel through the recovered Hub path ends the original task.
   - Before any cleanup, the original program and worker have exited, checked by their frozen identities.
   - There is exactly one run directory and one task, with exactly one well-formed start marker.
   - Only the cancel added an action.

| Check | |
|---|---|
| H0 | the launched NodeAgent driver had the expected bytes: hashed when written and right before launch, and launched |
| H1 | accepted before the loss: the client reply timed out; one Runtime task, the same ID the driver staged from the real `Runtime.submit`; the Hub action queued with no result |
| H2 | the program was ready with its worker and one marker; Hub, NodeAgent and Runtime alive |
| H3 | only the original Hub was killed: alive right before the SIGKILL, killed by it, reaped, gone |
| H4 | during the outage: same task, program, worker, NodeAgent and Runtime alive; Hub reads refused |
| H5 | the first reply was dropped: released after the disconnect; the first delivery finished with no connection, before the restart; one delivery before the restart |
| H6 | a new Hub process with the pre-fault state (same, only node device); no init or pairing after the restart; same NodeAgent process |
| H7 | the original action delivered again and recovered with the original task, ID and request digest unchanged; the recovery path is classified |
| H8 | after the recovery: one task, same program and worker, one marker; reads created no action |
| H9 | the cancel ended the original task; original program and worker exited before cleanup; one run, one start; only the cancel added an action |
| H10 | requests: one workspace creation, one client submission, one cancel |

The run makes two deliveries of the original action over two WebSocket connections. It does not claim
exactly one delivery; it claims one start, one task and one run.

## Scenario `hub-offline-completion` (X7: the task completes while the Hub is dead)

`--scenario hub-offline-completion` is optional; the default stays `lost-result`, above, with its checks and
interface unchanged. The task completes naturally on its original Runtime while the Hub **process** is dead
and has never been restarted. [`DISCONNECT.md`](DISCONNECT.md)'s `offline-completion` covers the same task
completion while the **NodeAgent** is down and the Hub stays up.

It reuses, read-only:
- the same deployment, ports, budget and cleanup;
- the same driver bytes (H0/K0 binding), launched with a hold of `0`, so it holds nothing and only counts and
  stages `execute`, `_perform` and `RuntimeClient.submit`. Only with this zero hold, the driver also stages
  each `RuntimeClient.submit` at its entry (`runtime_submit_called`: call number and key), before the real
  call, so a call that raises is still counted. The success stage `runtime_submit` (call number, key, task)
  is kept as before and shares the entry's call number. `lost-result` stages no entry; its stages, interface
  and H0–H10 are unchanged;
- `disconnect.py`'s release-gated program `parity-release`, registered in this run's Hub only;
- `disconnect.py`'s process identities, run-directory records, exact-read classification, fixed-artifact
  listing check and stdout bytes.

1. **A normal receipt.**
   - One workspace, then one client submission. Its reply arrives within the action wait and names the
     Runtime's one task.
   - The Hub's public action record is `succeeded` with that task. Its request object must be present and
     carry the original action ID, the Node ID, kind `task.submit` and the workspace
     (`payload.spec.workspace_id`). Only then is its digest taken; only the digest and these booleans are
     exported, never the request. A missing request has no digest and fails K1 and K9, even if it is missing
     both before and after.
   - From one read of the driver's stages: one delivery of the original action (no cached result before it),
     exactly one `RuntimeClient.submit` entry keyed by the original action ID, and exactly one successful
     return with the same call number and key, returning the original task. Invalid JSON or a stage with
     missing or mistyped fields counts as malformed and fails the check. The first delivery finished on a
     live connection without a gate delay.
   - The program prints its ready line and waits for its private flag. No flag, result record or `out.txt`
     exists yet. Its program and worker identities and its single start marker are frozen.
   - The heartbeat snapshot lists the task `running`: the cached view that live reads must never serve.
   - The Hub, NodeAgent, Runtime API and supervisor are alive.
2. **Only the Hub dies.** The same SIGKILL/reap record as H3: alive right before, killed by the SIGKILL,
   reaped, the frozen identity gone.
3. **The release gate.** The private flag is written (exclusive create, in the run directory, never a
   published artifact) only when all of the following hold. Otherwise the run fails, and nothing is released:
   - the original Hub exited by the SIGKILL, its identity is gone, no other Hub was started, and its port
     refuses TCP connections;
   - the original NodeAgent, Runtime API and supervisor (frozen identities) are alive, and the NodeAgent was
     never replaced;
   - at least two exact live reads (`require_live`) were refused `unavailable` because the Hub *cannot be
     reached*. For each read, neither health check right before or after answered, and the port refused
     right before and after. A running Hub that lists the node offline, a timeout or an unknown read never
     counts;
   - the owned Runtime still runs the original task, with the original program and worker, and no result or
     output.
4. **Completion with the Hub still dead.**
   - With the Hub dead and never restarted (the same four facts), the owned Runtime reports the original task
     `succeeded`, not cancelled, with its result record and `out.txt`.
   - The original program and worker exit before the restart.
   - Two more exact reads are refused in the same strict way: never `succeeded`, a cached state, a timeout or
     unknown.
5. **The restart.**
   - The harness reruns the recorded `serve` command: the same state directory, database, templates and port.
     No init, pairing, profile, workspace or submission call follows.
   - The original NodeAgent process reconnects by itself: the same identity, still the only node run, and its
     log has at least one lost-connection line (only the count is exported). It is the same, only node device.
6. **The read-back.**
   - The first answered exact live read, whatever its state, is the original task `succeeded`. Only
     `unavailable` is retried, as in `DISCONNECT.md`. A second read confirms it with the Hub reporting the node
     online.
   - The Hub's action record equals the pre-fault record: same ID, `succeeded` with the original task, a
     present request bound as in step 1, same request digest.
   - The fixed stdout is read through the Hub by byte cursor. The artifact listing must be exactly the fixed
     `out.txt` (path, size, SHA-256, media type) before any content is read. Then it is downloaded and
     hash-checked. All of it equals the fixture and the owned Runtime.
7. **Nothing was repeated.**
   - The node had no delivery after the restart. A final single read of the driver's stages equals the
     pre-fault snapshot: still one delivery, one `RuntimeClient.submit` entry and one matching return, no
     malformed line. A second same-key call that raised would leave the one success stage unchanged but add a
     second entry, and fail K1/K11.
   - One task, one run directory, one start; never cancelled.
   - The action listing equals the pre-fault listing after the restart and at the end.
   - The requests are the workspace creation and the one accepted submission.

| Check | |
|---|---|
| K0 | the launched NodeAgent driver had the expected bytes (as H0) |
| K1 | a normal receipt naming the Runtime's one task; the action, with a present request bound to the original action, node, `task.submit` and workspace, `succeeded` with it before the fault; nothing held; one delivery, one `RuntimeClient.submit` entry and one matching return, no malformed stage |
| K2 | before the fault: ready, running unreleased with the original program/worker and one marker; snapshot `running`; Hub, NodeAgent, Runtime API, supervisor alive |
| K3 | only the original Hub was killed: alive right before the SIGKILL, killed by it, reaped, gone |
| K4 | released only after the outage was confirmed (the release gate above) |
| K5 | with the Hub still dead and never restarted, the owned Runtime reports the original task `succeeded` with its result and output; NodeAgent and Runtime alive and not replaced |
| K6 | the original program and worker exited before the restart; one run, one start |
| K7 | after the completion, exact reads through the dead Hub were still refused because it cannot be reached |
| K8 | a new Hub process from the recorded `serve` command; no CLI call after it; the original NodeAgent process reconnected as the same, only node device |
| K9 | the first answered live read is the original task `succeeded`, confirmed online; the action record, its present and bound request and its digest are unchanged |
| K10 | fixed stdout and exactly the fixed `out.txt`, through the Hub, equal to the fixture and the owned Runtime |
| K11 | one task/run/start, never cancelled; no delivery after the restart; the final stage snapshot equals the pre-fault one, with one `RuntimeClient.submit` entry and one matching return; the action listing never changed |
| K12 | requests: one workspace creation and one accepted submission; no cancel |

**What is counted where.** The task, run directory, start marker and program/worker identities come from the
owned Runtime and its run directory. The one `RuntimeClient.submit` is counted by the test driver inside
the NodeAgent (its wrapper stages each call's entry and its successful return), not by the Runtime itself.
The Runtime's own evidence is one task and one start. The one Hub action comes from the Hub's client-visible
listing. A `RuntimeClient.submit` made outside the wrapped class in the NodeAgent process is not counted.

**The cache is never served as live.** Exact reads use `require_live`, which never falls back to the heartbeat
snapshot. The snapshot state of the restarted Hub, before the node's next heartbeat, is recorded as
`snapshot_after_restart` but not asserted, because it depends on heartbeat timing. In the first trial it still
said `running` while the first live read said `succeeded`.

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
STK_TOKEN_PLAN_API_KEY= timeout 300 /path/to/venv/bin/python -I examples/backend_parity/hub_restart.py \
    --mode installed --evidence-dir NEW_EVIDENCE_DIR

# This source tree (for development):
STK_TOKEN_PLAN_API_KEY= timeout 300 python -I examples/backend_parity/hub_restart.py --mode source \
    --evidence-dir NEW_EVIDENCE_DIR

# The X7 Hub offline-completion scenario (either mode):
STK_TOKEN_PLAN_API_KEY= timeout 300 python -I examples/backend_parity/hub_restart.py --mode source \
    --scenario hub-offline-completion --evidence-dir NEW_EVIDENCE_DIR

# The focused tests, including one real source-mode run:
STK_TOKEN_PLAN_API_KEY= python -m pytest -q tests/test_backend_parity_hub_restart.py
```

Leave `STK_TOKEN_PLAN_MODEL`, `DISPLAY` and `WAYLAND_DISPLAY` unset. `--evidence-dir` must be new or empty.

The rest comes from the `offline.py` helpers, as described in [README.md](README.md):
- the narrow environment, with the original `HOME` kept;
- the import-origin check (same base and module hashes for the harness and the services);
- the controlled error export;
- the cleanup.

Pairing data stays in the run's private files and is never written to evidence.

Exit codes:
- `0`: H0–H10 (or K0–K12 for `hub-offline-completion`) passed, including the driver binding; the scenario
  ended within the budget and cleanup was clean;
- `1`: a check failed, the driver bytes did not match, a wait ended `unknown`, an error occurred (including
  an unconfirmed outage that stopped the release, or an artifact listing that is not exactly the fixture), the
  budget ran out or cleanup was unclean;
- `2`: not Linux, an invalid `--deadline` or `--scenario`, or an evidence directory that is not new.

## Time budget

`--deadline` (default 170 s) bounds setup and the scenario. The raw, unrounded scenario time must not exceed
it. Every wait, CLI call, Hub action and the driver's hold starts with at most the time left, and a spent
budget ends `unknown`. A real synchronous HTTP call already in flight is bounded by its client timeout
(10 s), not cut off at the deadline, so it can end past a local wait's limit. The final budget gate
(`within_deadline`) then rejects the late run. No hard limit on a single synchronous call is claimed. The
normal scenario takes about 9 s; `hub-offline-completion` about 8 s.

The budget is one absolute deadline for the whole case, set once when the run starts. A Hub restart or a
NodeAgent reconnect never renews it. The wait for the first live answer after the restart (up to 60 s, since
the NodeAgent's reconnect backoff grows to 30 s) is bounded by the time left.

Cleanup runs afterwards, with its own bounded grace per step:
- 15 s plus 5 s per spawned process group;
- up to 60 s for `suan server stop`;
- 10 s for leftovers.

Use an external watchdog such as `timeout 300` for an absolute bound. Cleanup stops the restarted Hub, the
NodeAgent and the Runtime (the killed Hub is already reaped), then any leftover process in the private
directory, and removes that directory. A failed cleanup step fails the run.

## Evidence

| File | Contents |
|---|---|
| `run-manifest.json` | For `hub-offline-completion` also `scenario`, the `parity-release` argv digest and the driver's `gate_seconds` (0). Module origins (base kind; relative paths and SHA-256 of key modules); `hub_restart_sha256`, `disconnect_helper_sha256`, `offline_helper_sha256`, `driver_sha256`, `driver_file_matches` (the H0 result); the checkout HEAD (reference only), versions, ports, deadline, scenario and total seconds, verified and not-verified scope. It is informal trial evidence, not a published format. |
| `requests.jsonl` | The operations the scenario recorded: the workspace creation, the one client submission (key, template, its timeout outcome, the original action ID) and the cancel |
| `phases.json` | The driver digests (expected, written, at launch) and whether it was launched. Per phase: the submission and the queued action; frozen and current program and worker identities; the Hub stop record; outage reads and the driver's release and first-delivery stages; the restart; every delivery, node result and `Runtime.submit`; the recovery path; the action record, its digest and the action kinds at each point. For `hub-offline-completion`, the stage snapshots (`executes`, `runtime_submit_calls`, `runtime_submits`, `malformed`) and, per action record, `request_present`, the `request_bound` booleans and the digest (never the request) |
| `assertions.json` | H0–H10 (or K0–K12), the exported error, `cleanup_ok`, `within_deadline`, `driver_bound`, `ok` |
| `resources.json` | Processes started (including the restarted Hub), each cleanup step, leftovers, directory removal |

No tokens, pairing codes, credential files, database contents, environment values, absolute paths or raw
exception text are written. Action IDs and digests are not secrets.

## Scope and limits

**Verified:** on one Linux host, with a synthetic program:
- the Hub is killed after the Runtime accepted a submission and its program runs, and before the Hub
  recorded the result;
- the same Hub state restarts;
- the original queued action is delivered again, and the NodeAgent's action cache answers it with the
  original task;
- there is one program start, one task and one run, and the original processes stop on the explicit cancel;
- with `hub-offline-completion`: after one submission with a normal receipt, only the Hub is killed. The
  original task completes on its original Runtime while the Hub is dead and never restarted. After the same Hub
  state restarts, the original NodeAgent process reconnects, and the first exact live read is the original
  task `succeeded`, with its fixed log and artifact bytes. There is one delivery, one `RuntimeClient.submit`
  entry with one matching return (counted in the NodeAgent), one task, one run, one start and no cancel.

**Not verified:**
- For `hub-offline-completion`: a Runtime-side count of submit calls (see "What is counted where"); the Hub
  dying before the dispatch or while recording the result; completion before the Hub's death; whether the
  restarted Hub's snapshot is stale (recorded, not asserted); long outages (this one lasts seconds). The
  scenario's own refusal to release on an unconfirmed outage is exercised only by the real run. The
  counterexamples test the gate function and K4, not that code path in isolation.
- A second `Runtime.submit` with the same identity. The NodeAgent's persisted action cache answers the second
  delivery, so Runtime idempotency is not exercised here. The cache is kept as the product has it, neither
  removed nor bypassed.
- The Hub dying at other points: before the dispatch, or after it recorded the result.
- NodeAgent or Runtime restarts, network partitions without a process exit, or long outages.
- Hub actions outside the client-visible listing (the newest 200, plus actions awaiting review).
- Failover, other hosts, sites or clusters, Windows or macOS.
- Cloud project semantics, real solvers, licensed software (MuPRO) or scientific validity.
