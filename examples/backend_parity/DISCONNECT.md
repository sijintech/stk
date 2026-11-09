# D1 node disconnect: the task keeps running, the same node reconnects

This is the next D1 fault slice after [the two-deployment parity run](README.md). It checks one fault:
- an outbound NodeAgent goes offline while its Runtime task runs;
- the task keeps running;
- after the same node profile reconnects, the Hub observes the same task, with no second submission or
  start.

It is not a failover test: no other node, Runtime or authority is used. It adds no product command,
contract, endpoint or state.

`disconnect.py` loads the helpers of `offline.py` (and, for the socket partition, `socket_partition.py`) by file
path; it does not change them at run time. The only additions to `offline.py` are the optional `extra_templates`
and `node_route` of `start_hub`, used by the offline-completion and socket-partition scenarios below. In installed
mode nothing is put on `sys.path`.

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

## Offline completion (`--scenario offline-completion`, X7)

The default scenario above is unchanged. This second scenario covers the case it leaves out: the worker
completes normally while the NodeAgent is offline. Only the Hub's ability to observe the task is lost; the
task itself is not failed, retried or handed over.

It uses the same deployment and one extra public synthetic program, `parity-release`. That program is
registered as an exact template in this run's Hub only, through the optional `extra_templates` of
`offline.start_hub`. The fixed `offline.py` templates and their default template file do not change, and an
extra template may not replace one of them. The program:
1. appends its `start <pid>` line to the start marker and prints `waiting 等待`;
2. waits up to 120 s for a private release flag, `parity-release.flag`, in its run directory. That is the
   parent of its working directory, so the flag is never published as an artifact;
3. once released, writes the fixed `out.txt` (`parity 结果\n`), prints `released 已释放 ✓` and exits 0.
   If it is never released, it prints `never released 未释放` and exits 3 (failed), so it can never succeed on
   its own.

Steps:
1. **Submit once.** As in the default scenario: one workspace, one submission, the ready line, the frozen
   program and worker identities, one start marker. No release flag, worker result or output exists yet.
   The harness also waits up to 15 s until a heartbeat snapshot lists the task as `running`. This is the
   cached view that exact reads must later refuse to serve.
2. **Stop only the NodeAgent.** The same SIGKILL, reaping and checks as the default step 2. Three exact live
   reads, each with the Hub's node status read right before and right after it:
   - one between the kill and the Hub's offline report. It is recorded on its own as
     `read_before_offline_report`: the Hub still lists the node online, so it is typically refused with the
     Hub's 503 (`hub_node_link_closed`). It must be refused or unknown, never a task state or `not_found`, and
     it never counts as an offline refusal;
   - two after the report. Each must be the strict offline refusal: code `unavailable` with cause
     `node_offline`, with an explicit boolean `online: false` from the Hub on both sides. `node_offline` is
     HubBackend's own refusal when the device listing it just read shows the node offline. It is raised before
     anything is forwarded, so it is never a timeout. A Hub 503 or 504, an HTTP timeout, an unreachable Hub
     (all also code `unavailable`) or an unanswered read never counts.

   Read directly, the owned Runtime still has the same task `running`, with the original program and worker
   alive and no result or output.
3. **Complete offline.** The harness writes the release flag only after the Hub has reported the node offline.
   It writes it once, with exclusive create, and only while the original NodeAgent is the only one ever
   started. With the NodeAgent still down:
   - the owned Runtime reports the original task `succeeded`, never cancel-requested;
   - the original program and worker (frozen identities) have exited. This is checked before any reconnect
     or cleanup;
   - two more exact Hub reads are both the strict offline refusal of step 2 (a timeout or unknown read
     fails). Meanwhile the Hub's heartbeat snapshot still caches the task as `running`. So exact reads served
     neither the completed state nor the stale cache.
4. **Reconnect and read back.** Restart `suan-node run` with the same node state. Then, through the Hub:
   - the first answered exact live read, whatever its state, must be the original task, `succeeded`. This
     read is not the default scenario's `observe_live`, which skips an answered `queued`: here an answered
     `queued`, a stale `running` or any other state fails C8. Only `unavailable` is retried (counted as
     `unavailable_before_answer`). `not_found` or any other refusal fails the run at once. An answer at or
     after the deadline is unknown;
   - the stdout, read by byte cursor, must be exactly `waiting 等待\nreleased 已释放 ✓\n`, the same as
     the owned Runtime;
   - before any content is read, the artifact list must be exactly one item: `out.txt` with the fixed size
     (an integer), SHA-256 and media type. An unknown path, an extra or duplicate item, or a malformed or
     oversized size fails the run with a fixed message. Nothing is downloaded, and the listed values are not
     exported;
   - then the fixture's own `out.txt` description (not the Hub's) is downloaded. The bytes must equal the
     fixed bytes and digest.
5. **Count.** One task, one run directory with one start marker carrying the program's PID, program and
   worker exited, a worker result record. No cancel request.

The action listing is the same at all four points: before the disconnect, while offline, after the offline
completion and after the reconnect and reads. The requests are exactly one workspace creation and one
submission.

| Check | |
|---|---|
| C1 | one submission; ready line; one start marker; unreleased, no result or output; the snapshot lists it running |
| C2 | only the original NodeAgent stopped by the SIGKILL and reaped; Hub, Runtime API and supervisor alive throughout |
| C3 | the Hub reported the node offline; the two reads after that were the strict offline refusal (`unavailable`, cause `node_offline`, explicit Hub offline status before and after); the read before the report was refused or unknown, never a state |
| C4 | not finished before the disconnect: while offline and unreleased, the owned Runtime still ran it, with the original processes, no result and no output |
| C5 | released only after the offline report, with the original NodeAgent still the only one; the owned Runtime reports `succeeded`, not cancelled |
| C6 | the original program and worker exited before any reconnect or cleanup; still one start |
| C7 | after the completion, two exact Hub reads were the strict offline refusal (never a timeout or unknown), while the snapshot still cached `running` |
| C8 | the same node profile reconnected; the first answered exact read, whatever its state, is the original task, `succeeded` |
| C9 | the fixed stdout bytes through the Hub, equal to the owned Runtime's |
| C10 | exactly `out.txt` with the fixed bytes: the listing checked against the fixture before any download, then downloaded and hash-checked |
| C11 | one task, one run directory, one start, program and worker exited; never cancelled |
| C12 | requests: one workspace creation and one submission; no Hub action after the submission, no cancel |

The normal run takes about 25–30 s, mostly the 18–20 s until the Hub reports the node offline. The program's
own 120 s wait has to outlast the worst case before the release:
- snapshot, 15 s;
- offline, 40 s;
- the offline reads, each bounded by the HTTP timeout.

If it does not, the program ends `failed` and C5 fails. That is again a correct, timing-caused failure. The
evidence files are the same five. `phases.json` holds `baseline`, `node_stop`, `offline`, `completed_offline`,
`reconnect`, `outputs`, `final` and `actions`; `run-manifest.json` names the scenario and the
`parity-release` template digest. Each offline read records its outcome, code, cause label and the Hub's
online report before and after; refusal messages are never exported. Neither the flag path nor any workspace
path is exported.

The cause label comes from the message of the product's refusal. HubBackend's offline refusal starts with
`The execution node is offline`; the Hub's HTTP errors carry their status, such as `(503)`. If the product
changes that text, the strict refusal is no longer recognised and C3/C7 fail. That is a safe failure, never
a false pass. The tests drive the real `HubBackend` with a stub Hub to keep the labels in step with the
product.

## Socket partition (`--scenario socket-partition`, X7/F03)

The offline-completion scenario with a different fault: no process is signalled or restarted. The NodeAgent loses
its control link because a loopback relay closes it, then gets it back on the same address. The default `cancel`
scenario and `offline-completion` are unchanged.

`socket_partition.py` (standard library only, loaded by file path like `offline.py`) is the fault injector: a
TCP relay listening on `127.0.0.1` on one port for its whole life, forwarding to the Hub's loopback port.
`offline.start_hub` takes an optional `node_route`. It is called with the Hub's port once the Hub listens and
returns the relay's URL, which is the URL `suan-node pair` is given. So from the initial pairing onward the
NodeAgent's HTTP calls and its WebSocket control link go through the relay. The harness's `HubClient` and
`RuntimeClient` stay direct; the NodeAgent reaches its own Runtime directly, as always. Without `node_route`,
`start_hub` pairs the node with the Hub's own URL, as before.

Steps (the same fixture, `parity-release`, and the same reads as offline completion):
1. **Submit once**, wait for the ready line and for the heartbeat snapshot to list the task `running`. The
   NodeAgent, Hub, Runtime API and supervisor identities (PID plus create time) are frozen once the node is
   online.
2. **Cut.** The relay stops forwarding, closes active tunnels and waits for active and pending connection handlers
   within a fixed grace period. It reports how many tunnels it closed, and whether one opened before submission and still
   carried bytes from the node after it, plus bytes to the node: the task's live control link. While the cut
   holds, every new connection is accepted and closed at once, before anything is forwarded (counted as
   rejected). The NodeAgent keeps running and retries by itself. The first post-cut read is refused or unknown.
   After the offline report the scenario requires two strict
   node-offline refusals with the Hub's explicit `online: false` before and after each.
3. **Release and complete** only after the offline report, with the relay still cut and the original NodeAgent
   still running. The owned Runtime reports the task `succeeded`. The original program and worker exit before
   the relay is reopened, two more exact reads are still the strict refusal, and the snapshot still caches
   `running`.
4. **Reopen** the same relay object: same listening socket, same port. Wait up to 45 s for the node to be online
   with exact reads; the NodeAgent's own retry delay doubles up to 30 s while it is rejected. The node profile
   (`node.json`) must be byte-for-byte unchanged, the same device the only node, and no second `suan-node run`
   started. The first answered exact read is the original task `succeeded`. The stdout and the downloaded
   `out.txt` are the fixed bytes (listing checked first), equal to the owned Runtime's.
5. **Count**: one workspace, one submission, one task, one run directory, one start, no cancel, an unchanged
   action listing. The four frozen identities are alive at the cut, while offline, after the completion, after
   the reopen and at the end.

| Check | |
|---|---|
| P1 | as C1: one submission, ready line, one start marker, unreleased, the snapshot lists it running |
| P2 | the node profile points at the loopback relay, at least two tunnels (pairing and link) before the submission; the harness's Hub and Runtime clients are direct |
| P3 | the relay closed the task's live control link and its tunnels ended; the NodeAgent was not signalled; all four identities alive |
| P4 | as C3: strict node-offline refusals after the offline report. The first post-cut read yields no task state |
| P5 | as C4, and the four identities alive |
| P6 | while cut: no tunnel accepted or active, at least one rejected |
| P7 | released after the offline report with the cut holding and the original NodeAgent running; `succeeded`, not cancelled |
| P8 | as C6: the original program and worker exited before the reopen |
| P9 | as C7: still the strict refusal after the completion, the cache still `running` |
| P10 | the same relay port reopened; the same NodeAgent reconnected through a new tunnel; profile unchanged; no restart; identities alive |
| P11 | as C8: the same device; the first answered exact read is the original task, `succeeded` |
| P12–P13 | as C9–C10: fixed stdout and `out.txt` |
| P14 | as C11, and the same four processes at the end |
| P15 | as C12: one workspace creation, one submission, no further action, no cancel |

P1, P4, P5, P8, P9 and P11–P15 reuse the C predicates of offline completion by ID (`completion_checks`); the C
texts and verdicts themselves are unchanged. A timeout or unknown read while cut, a stale (`running`) or completed
state served while cut, a stale first answer and the wrong task all fail. So do a relay that closed no live link,
a tunnel let through during the cut, a changed port or profile, a restarted or signalled NodeAgent and any extra
submission or cancel. The tests also drive the relay itself with real loopback sockets, and check that a run
failing before or during the cut still closes the relay. The real scenario run in the tests is opt-in
(`STK_SOCKET_PARTITION=1`); the scenario itself is only run on request (`--scenario socket-partition`).

**Client boundary.** The exact reads use the in-process `HubBackend` of `suan.desktop_bridge` over a direct
`HubClient`, as in the other scenarios. The strict stdio bridge subprocess is not exercised here; it is left to
root's separate probe. The manifest records this as `client_boundary`.

The normal run takes about 35–40 s: about 20 s until the Hub reports the node offline, then up to one retry
delay (typically under 16 s) until the NodeAgent's next attempt after the reopen. Cleanup closes the relay first
(recorded as `B socket relay`), then the usual sweep. `phases.json` adds `route`, `partition` and `reopen`, and has
no `node_stop`. The manifest records `socket_partition_sha256` and the relay port; no address beyond the
loopback ports, header or payload is kept.

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
STK_TOKEN_PLAN_API_KEY= timeout 300 /path/to/venv/bin/python examples/backend_parity/disconnect.py \
    --mode installed --evidence-dir NEW_EVIDENCE_DIR

# This source tree, through PYTHONPATH (for development):
STK_TOKEN_PLAN_API_KEY= timeout 300 python examples/backend_parity/disconnect.py --mode source \
    --evidence-dir NEW_EVIDENCE_DIR

# The X7 offline-completion scenario (either mode):
STK_TOKEN_PLAN_API_KEY= timeout 300 python examples/backend_parity/disconnect.py --mode source \
    --scenario offline-completion --evidence-dir NEW_EVIDENCE_DIR

# The X7 socket-partition scenario (either mode):
STK_TOKEN_PLAN_API_KEY= timeout 300 python examples/backend_parity/disconnect.py --mode source \
    --scenario socket-partition --evidence-dir NEW_EVIDENCE_DIR

# The focused tests, including one real source-mode run of the cancel and offline-completion scenarios;
# the real socket-partition run is opt-in (STK_SOCKET_PARTITION=1), its verdict and relay tests always run:
STK_TOKEN_PLAN_API_KEY= python -m pytest -q tests/test_backend_parity_disconnect.py
STK_SOCKET_PARTITION=1 STK_TOKEN_PLAN_API_KEY= python -m pytest -q tests/test_backend_parity_disconnect.py
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
- `0`: D1–D10 (or C1–C12, or P1–P15) passed, the scenario ended within the budget and cleanup was clean;
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
| `run-manifest.json` | Module origins (base kind; relative paths and SHA-256 of key modules), `disconnect_sha256`, `offline_helper_sha256`, the checkout HEAD (reference only), versions, ports, deadline, scenario and total seconds, verified and not-verified scope. A failed socket-partition run has an empty `verified` list. This is informal trial evidence. |
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
- the Hub observes the same task exactly, with no second submission, start or Hub action;
- with `--scenario offline-completion`, the task completes normally on its original Runtime while the node is
  offline. Exact Hub reads are refused because the node is offline, with the Hub answering, and the stale
  snapshot is not served. After the reconnect the first answered exact read is the same task `succeeded`; its
  fixed log and its artifact bytes (listing checked first) follow. There is no cancel and no second start.

- with `--scenario socket-partition`, the same completion while a loopback relay closes the NodeAgent's live
  control link and rejects new tunnels, with no process signalled; the same NodeAgent process reconnects by itself
  once the same relay reopens.

**Not verified:**
- A Hub restart, a Runtime restart, or long outages. A network partition without a process exit only as the
  socket-partition scenario's loopback relay: closed and rejected connections, not silently dropped packets,
  half-open sockets, or asymmetric or intermittent links.
- Cross-host networks, or the native desktop client and the strict stdio bridge subprocess (the scenarios use the
  in-process `HubBackend`).
- Completion at any other moment than one release after the Hub reported the node offline (for example
  exactly at the kill, or while the Hub has not yet noticed).
- That a Hub timeout (504) or an unreachable Hub is told apart in a real run. None was provoked: the real
  runs show the node-offline refusal, and the other causes are exercised only against the real `HubBackend`
  with a stub Hub.
- Failover to another node or Runtime; none is attempted.
- Hub actions outside the client-visible listing (the newest 200, plus actions awaiting review).
- Windows, macOS, other hosts, sites or clusters.
- Real solvers, licensed software or scientific validity.
