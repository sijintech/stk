# D1 node disconnect: the task keeps running, the same node reconnects

This is the next D1 fault slice after [the two-deployment parity run](README.md). It checks one fault:
- an outbound NodeAgent goes offline while its Runtime task runs;
- the task keeps running;
- after the same node profile reconnects, the Hub observes the same task, with no second submission or
  start.

It is not a failover test: no other node, Runtime or authority is used. It adds no product command,
contract, endpoint or state.

`disconnect.py` loads the helpers of `offline.py` by file path; it does not change them. In installed mode
nothing is put on `sys.path`.

## Deployment

One private loopback deployment, started with existing entry points:

| Process | Started with |
|---|---|
| Runtime API and supervisor | `suan server init` / `start` |
| Hub (HTTP and WebSocket), with the exact `parity-wait` template | `suan-control init` / `serve` |
| Outbound NodeAgent | `suan-node pair` / `run` |

The client is `HubClient` + `HubBackend` with a paired client device.

The program is the fixed public synthetic `parity-wait` from `offline.py`. It does the following:
1. it appends one `start <pid>` line to a start marker in its run directory;
2. it prints `waiting 等待`;
3. it waits for up to 120 s.

## Scenario

1. **Submit once.** Create one workspace, submit once and wait until the program itself prints its ready
   line. Record the program and worker identities (PID plus create time) that the Runtime recorded. The
   marker must have exactly one line, carrying the program's PID.
   These original program and worker identities are frozen here and compared in every later phase. Replaced
   metadata in `program.json` or `worker.json` fails.
2. **Stop only the NodeAgent.** The original NodeAgent's identity is frozen when it comes online. Immediately
   before the kill, that same process must still be running. The harness then sends SIGKILL to its process
   group and reaps it.
   - It must exit by that SIGKILL, and its frozen identity must be gone.
   - A node that had already exited cleanly or crashed fails, as does one with a missing or foreign identity.
     Such a node is not this scenario's fault injection.
   - The Hub, the Runtime API, the supervisor and the program keep running.
   - Three exact live reads (`task.get` with `require_live`) are made: one right after the kill, and two
     after the Hub reports the node offline.
   - The Hub reports a node offline 20 s after its last heartbeat. The harness waits up to 40 s for that.
   - Every read must be refused as `unavailable` (or `timeout`, or end `unknown`). A task state or
     `not_found` fails.
   - The heartbeat snapshot is never used to decide whether the task exists or failed. No write is made.
3. **Observe directly.** Read the task from this run's own Runtime. It must be the same task, still
   running, with the original program and worker alive and still one start marker. This is observation only; the
   task is not handed to another authority.
4. **Reconnect.** Restart `suan-node run` with the same node state. There is no new pairing, workspace or
   submission. Wait until the node is online with exact reads, then read the original task live.
   - The same node device must be the only node.
   - The read must return the original task, `running`, with the original program and worker.
   - An unanswered read ends `unknown`; nothing is resubmitted, cancelled or retried under another key.
5. **Cancel.** Explicitly cancel the original task. It must end `cancelled` (also read directly), with:
   - the same program and worker recorded;
   - the original program and worker exited, checked by their frozen identities right after the cancel and
     before any cleanup. A later cleanup sweep stopping them would prove nothing.
   - exactly one well-formed start marker with the program's PID;
   - exactly one task and one run directory in the workspace.

The Hub's read-only action listing (`GET /api/v1/actions`) is compared at four points. The action set is
identical before the disconnect, while offline and after the reconnect. After the cancel it has exactly
one more action, a `task.cancel`.

| Check | |
|---|---|
| D1 | one submission; ready line; valid program and worker identities; one start marker with the program PID |
| D2 | only the original NodeAgent stopped: alive right before the SIGKILL, killed by it, reaped and gone; Hub, Runtime API and supervisor alive |
| D3 | the Hub reported the node offline, and a live read was made while it did |
| D4 | live exact reads while offline were refused as unavailable |
| D5 | the owned Runtime still ran the same task with the original program and worker and one marker |
| D6 | no Hub action while offline or by the reconnect |
| D7 | the same node profile reconnected; the live read returned the original running task |
| D8 | the cancel ended the original task; the original program and worker exited before cleanup; one task, one run, one start |
| D9 | only the cancel added a Hub action |
| D10 | requests: one workspace creation, one submission, one cancel |

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
STK_TOKEN_PLAN_API_KEY= timeout 300 /path/to/venv/bin/python examples/backend_parity/disconnect.py \
    --mode installed --evidence-dir NEW_EVIDENCE_DIR

# This source tree, through PYTHONPATH (for development):
STK_TOKEN_PLAN_API_KEY= timeout 300 python examples/backend_parity/disconnect.py --mode source \
    --evidence-dir NEW_EVIDENCE_DIR

# The focused tests, including one real source-mode run:
STK_TOKEN_PLAN_API_KEY= python -m pytest -q tests/test_backend_parity_disconnect.py
```

Leave `STK_TOKEN_PLAN_MODEL`, `DISPLAY` and `WAYLAND_DISPLAY` unset. `--evidence-dir` must be new or empty;
an earlier trial's evidence is never overwritten (exit 2).

The rest of the run's environment and handling comes from the `offline.py` helpers, as described in
[README.md](README.md):
- the narrow environment, with the original `HOME` kept;
- the import-origin check for `--mode` (same base and identical module hashes for the harness and the
  services);
- the controlled error export;
- the cleanup.

Exit codes:
- `0`: D1–D10 passed, the scenario ended within the budget and cleanup was clean;
- `1`: a check failed, a wait ended `unknown`, an error occurred, the budget ran out or cleanup was unclean;
- `2`: not Linux, an invalid `--deadline`, or an evidence directory that is not new.

## Time budget

`--deadline` (default 170 s) bounds setup and the scenario. Every wait and call is bounded by the time left.
A spent budget ends `unknown`, and a scenario that ends after it fails. The normal scenario takes about
25 s, of which about 18–20 s is waiting for the Hub to report the node offline. The cancel comes about 20 s
after the submission, well before the program's own 120 s end.

In the worst case the bounded waits can add up past 120 s:
- ready line, 60 s;
- offline, 40 s;
- node online, 30 s;
- live read, 30 s.

The program then ends `succeeded` before the cancel and D8 fails. That is a correct failure, caused by
timing rather than task semantics.

Cleanup runs after the budget, with its own bounded grace per step:
- 15 s plus 5 s per spawned process group;
- up to 60 s for `suan server stop`;
- 10 s for leftovers.

So the deadline is not a hard limit for the whole run. Use an external watchdog such as `timeout 300` for
an absolute bound. Cleanup stops both NodeAgent processes (the killed one is already reaped), the Hub and
the Runtime, then any leftover process in the private directory, and removes that directory. If a run
fails before its explicit cancel, cleanup also cancels the open task on the owned Runtime. That is cleanup
of this run's own processes, not recovery, and such a run never passes.

## Evidence

| File | Contents |
|---|---|
| `run-manifest.json` | Module origins (base kind; relative paths and SHA-256 of key modules), `disconnect_sha256`, `offline_helper_sha256`, the checkout HEAD (reference only), versions, ports, deadline, scenario and total seconds, verified and not-verified scope. It is informal trial evidence, not a published format. |
| `requests.jsonl` | The operations the scenario recorded: workspace creation, the one submission (key, template, task ID) and the cancel. Reads are not listed. |
| `phases.json` | Per phase: states, program and worker identities, liveness, marker counts. The node stop records the identity check, liveness right before the kill, the signal and the exit status. Also listed: each offline read's outcome and whether the Hub reported the node online then, and the action kinds at each point |
| `assertions.json` | D1–D10, the exported error, `cleanup_ok`, `within_deadline`, `ok` |
| `resources.json` | Processes started (including the restarted node), each cleanup step, leftovers, directory removal |

No tokens, pairing codes, credential files, database contents, environment values, absolute paths or raw
exception text are written. Action IDs are compared in memory; only their kinds and counts are exported.

## Scope and limits

**Verified:** on one Linux host, with a synthetic program:
- a Runtime task keeps running while its outbound NodeAgent is killed and offline;
- the same node profile reconnects;
- the Hub observes the same task exactly, with no second submission, start or Hub action.

**Not verified:**
- A Hub restart, a Runtime restart, a network partition without a process exit, or long outages.
- Failover to another node or Runtime; none is attempted.
- Hub actions outside the client-visible listing (the newest 200, plus actions awaiting review).
- Windows, macOS, other hosts, sites or clusters.
- Real solvers, licensed software or scientific validity.
