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

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
STK_TOKEN_PLAN_API_KEY= timeout 300 /path/to/venv/bin/python -I examples/backend_parity/hub_restart.py \
    --mode installed --evidence-dir NEW_EVIDENCE_DIR

# This source tree (for development):
STK_TOKEN_PLAN_API_KEY= timeout 300 python -I examples/backend_parity/hub_restart.py --mode source \
    --evidence-dir NEW_EVIDENCE_DIR

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
- `0`: H0–H10 passed (including the driver binding), the scenario ended within the budget and cleanup was
  clean;
- `1`: a check failed, the driver bytes did not match, a wait ended `unknown`, an error occurred, the budget
  ran out or cleanup was unclean;
- `2`: not Linux, an invalid `--deadline`, or an evidence directory that is not new.

## Time budget

`--deadline` (default 170 s) bounds setup and the scenario. The raw, unrounded scenario time must not exceed
it. Every wait, CLI call, Hub action and the driver's hold is bounded by the time left. A spent budget ends
`unknown`. The normal scenario takes about 9 s.

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
| `run-manifest.json` | Module origins (base kind; relative paths and SHA-256 of key modules); `hub_restart_sha256`, `disconnect_helper_sha256`, `offline_helper_sha256`, `driver_sha256`, `driver_file_matches` (the H0 result); the checkout HEAD (reference only), versions, ports, deadline, scenario and total seconds, verified and not-verified scope. It is informal trial evidence, not a published format. |
| `requests.jsonl` | The operations the scenario recorded: the workspace creation, the one client submission (key, template, its timeout outcome, the original action ID) and the cancel |
| `phases.json` | The driver digests (expected, written, at launch) and whether it was launched. Per phase: the submission and the queued action; frozen and current program and worker identities; the Hub stop record; outage reads and the driver's release and first-delivery stages; the restart; every delivery, node result and `Runtime.submit`; the recovery path; the action record, its digest and the action kinds at each point |
| `assertions.json` | H0–H10, the exported error, `cleanup_ok`, `within_deadline`, `driver_bound`, `ok` |
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
- there is one program start, one task and one run, and the original processes stop on the explicit cancel.

**Not verified:**
- A second `Runtime.submit` with the same identity. The NodeAgent's persisted action cache answers the second
  delivery, so Runtime idempotency is not exercised here. The cache is kept as the product has it, neither
  removed nor bypassed.
- The Hub dying at other points: before the dispatch, or after it recorded the result.
- NodeAgent or Runtime restarts, network partitions without a process exit, or long outages.
- Hub actions outside the client-visible listing (the newest 200, plus actions awaiting review).
- Failover, other hosts, sites or clusters, Windows or macOS.
- Cloud project semantics, real solvers, licensed software (MuPRO) or scientific validity.
