# D1 upload restart: a Bridge crash after the Hub accepted a chunk

This D1 software gate follows [the parity run](README.md), [the node disconnect](DISCONNECT.md),
[the Hub restart](HUB_RESTART.md) and [the input transfer](INPUT_TRANSFER.md).

A real desktop Bridge uploads one fixed public input through a Hub. It is killed with SIGKILL at a precise
point: the Hub has accepted a chunk, but the Bridge has not yet recorded that acknowledgement in its
transfer journal.

The same Bridge state then reopens. The original transfer resumes in the same Hub upload session, at the
offset the Hub holds. The reviewed `workspace.import` still lands only after an explicit decision.

It is one Linux host and one process crash. It is not a network partition, cross-host recovery or R3, and
it involves no licensed solver or scientific validation. It adds no product command, contract, endpoint or
state.

`upload_restart.py` loads `disconnect.py`, and through it `offline.py`, by file path. It does not change
them; it reuses their lifecycle, origin check, deadline, process identities and owned cleanup. In installed
mode nothing is put on `sys.path`.

## Deployment

| Process | Started with |
|---|---|
| Runtime API and supervisor | `suan server init` / `start` |
| Hub | `suan-control init` / `serve` |
| NodeAgent | `suan-node pair` / `run` |
| Bridge, original | the real `suan.desktop_bridge --stdio` entry point, through the crash driver |
| Bridge, restarted | the same entry point and the same `--state-dir`, through the observe driver |

The Bridge pairs once with the Hub as a `desktop` client (`connections.pair_hub`). The one-time code comes
from `suan-control pair --role client --profile desktop`.

The input is fixed and public: 2.5 MiB plus a UTF-8 tail (2 621 464 bytes), so three 1 MiB chunks. It is
uploaded with `upload.start` under a frozen caller key. The transfer ID is derived from that key.

## Test drivers

Both drivers are text in `upload_restart.py`. Each run writes them into its own private directory and
hashes each file twice:
- once after writing it, before any service starts;
- once more immediately before the Bridge launch.

Both hashes must equal the harness's own digest. Otherwise the run fails with a fixed error:
- **At write time** (both drivers are written first): a mismatch stops the run before any service starts.
- **At launch time:** a mismatch prevents only that Bridge's launch. The Runtime, Hub, node and any earlier
  Bridge already running are then stopped by the owned cleanup in `finally`.

This binding is check U0, and the run also requires it explicitly, so it holds even if the assertions are
bypassed.

The drivers:
- **Crash driver:** wraps the real `HubClient.upload_chunk`. It calls the real method first, then holds its
  first successful return, the one by which the Hub had just accepted bytes. While the return is held, the
  Bridge's `TransferManager` cannot update or save anything for that chunk. If the hold outlives the run
  budget, the driver exits with status 75, which can never count as the injected fault.
- **Observe driver:** records the real `HubClient.upload_begin/status/chunk/finish` calls of the restarted
  Bridge (the session ID, the offsets and the returned offsets). It changes nothing.

## Scenario

1. **Accepted before the lost ACK.** The original Bridge creates the workspace and starts the keyed upload.
   When the crash driver holds the first returned chunk, the harness checks three things:
   - **Hub API:** with the Bridge's own device credential, the session reports offset 1 MiB, not completed,
     out of 2 621 464 bytes.
   - **Hub state on disk:** the session's `.part` file in the owned Hub state is exactly the input's first
     1 MiB.
   - **Bridge journal:** the transfer is `running` and holds that same session, but its `bytes_done` is 0.
     `TransferManager` saves the journal at `upload_begin` and at the end of each file, never per chunk
     ACK.

   The Bridge must also be alive at this point.
2. **The fault.** The Bridge's identity (PID plus create time) was frozen at launch. It must be alive right
   before the kill. Its process group is then sent SIGKILL and reaped, and it must have exited by that
   SIGKILL, with the frozen identity gone. The Hub, node and Runtime stay alive, and the journal stays
   `running` with the same session. A premature, natural or non-SIGKILL exit fails, as does an expired hold.
3. **Reopen.**
   - The restarted Bridge opens the same state directory and starts with `hello` and
     `resume_transfers: false`.
   - It reports the same transfer as `interrupted`, under the same Hub connection and device. There is no
     re-pairing.
   - The same key returns the same transfer, and an explicit `transfer.resume` runs it.
4. **Resume at the held offset.**
   - The real `upload_begin` returns the same session at the held offset (1 MiB), for the frozen sha256 and
     size.
   - The chunks then start exactly there, are contiguous to the end and stay in that session, followed by
     one finish.
   - A chunk at offset 0, a new session or a gap fails.
5. **Reviewed import.**
   - The transfer waits in `running` with its `workspace.import` action in `review`.
   - The action ID is derived from the transfer, and its request is exactly the original
     `{workspace_id, files: [{path, size, sha256}]}`.
   - Until the decision, the workspace holds no file and no task.
   - The test operator (this deployment's owner) then approves that exact action once.
6. **Completion.**
   - The original transfer completes.
   - The workspace lists exactly `input.bin` with the input's size and sha256.
   - The bytes downloaded from the Runtime equal the input.
   - The Hub session is released (404).
   - There is one transfer and no task, and the only actions are the workspace creation and the one import.

| Check | |
|---|---|
| U0 | both drivers had the expected bytes (written and at launch), and were launched |
| U1 | accepted before the lost ACK: Hub offset ≥ 1 MiB and < total; `.part` equals the input prefix; the journal holds the session but not the ACK; Bridge alive |
| U2 | only the original Bridge was killed: alive before the SIGKILL, killed by it, reaped, gone; Hub, node and Runtime alive; the hold never expired |
| U3 | the crash left the journal `running` with the same session, and the Hub still held the offset |
| U4 | the same state reopened the same transfer (`interrupted`) and the same Hub device; the same key gave the same transfer; the explicit resume ran it |
| U5 | resumed in the same session at the held offset; never from zero; contiguous; one finish |
| U6 | the import waited for review of its exact original request; nothing landed before it |
| U7 | after the approval: the original transfer completed; exact path, size, sha256 and bytes; the session released |
| U8 | one transfer, no task, only the workspace creation and the one import |
| U9 | requests: one pairing, one workspace creation, the keyed upload and its same-key replay, one explicit resume; all answered |

No program is submitted to read the uploaded input; that is listed as not verified.

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
env -u STK_TOKEN_PLAN_MODEL -u DISPLAY -u WAYLAND_DISPLAY STK_TOKEN_PLAN_API_KEY= timeout 300 \
    /path/to/venv/bin/python -I examples/backend_parity/upload_restart.py --mode installed \
    --evidence-dir NEW_EVIDENCE_DIR

# This source tree (for development):
env -u STK_TOKEN_PLAN_MODEL -u DISPLAY -u WAYLAND_DISPLAY STK_TOKEN_PLAN_API_KEY= timeout 300 \
    python -I examples/backend_parity/upload_restart.py --mode source --evidence-dir NEW_EVIDENCE_DIR

# The focused tests, including one real source-mode run:
env -u STK_TOKEN_PLAN_MODEL -u DISPLAY -u WAYLAND_DISPLAY STK_TOKEN_PLAN_API_KEY= \
    python -m pytest -q tests/test_backend_parity_upload_restart.py
```

The commands unset `STK_TOKEN_PLAN_MODEL`, `DISPLAY` and `WAYLAND_DISPLAY` and leave the model key empty.
`--evidence-dir` must be new or empty.

The narrow child environment, with the original `HOME`, and the import-origin check come from `offline.py`.
The module hashes also bind the Bridge server, its transfer journal, its connections, its entry point and the
Hub's upload sessions.

Credentials stay in memory and in the run's private files, and are never exported. They are only those this
deployment generated:
- the pairing code;
- the Bridge's device token, read to query its own upload session;
- the Hub owner token, for the review.

Exit codes:
- `0`: U0–U9 passed (including the driver binding), the scenario ended within the budget and cleanup was
  clean;
- `1`: a check failed, a driver did not match, a wait ended `unknown`, a Bridge call failed, an error
  occurred, the budget ran out or cleanup was unclean;
- `2`: not Linux, an invalid `--deadline`, or an evidence directory that is not new.

## Time budget

`--deadline` (default 170 s) bounds setup and the scenario. The raw scenario time must not exceed it. Every
Bridge request, Hub wait and the crash driver's hold is bounded by the time left. A reply or a terminal state
that arrives after its frozen deadline cannot pass. The normal scenario takes about 6 s.

Cleanup runs afterwards, with its own bounded grace per step. The restarted Bridge exits on the end of its
input. The killed one is already reaped. The Hub, node and Runtime are stopped, then any leftover process in
the private directory, and the directory is removed. A failed cleanup step fails the run. Use an external
watchdog such as `timeout 300` for an absolute bound.

## Evidence

| File | Contents |
|---|---|
| `run-manifest.json` | Module origins (base kind; relative paths and SHA-256 of the key modules); `upload_restart_sha256`, `disconnect_helper_sha256`, `offline_helper_sha256`, both `driver_sha256` values, `driver_files_match`; the input's size and sha256; versions, ports, deadline, scenario and total seconds, verified and not-verified scope. It is informal trial evidence, not a published format. |
| `requests.jsonl` | Every Bridge request, by Bridge, method and outcome only, never its parameters |
| `phases.json` | The driver digests; the accepted chunk, the Hub status and `.part` checks and the journal at the crash; the SIGKILL record; the outage; the restart, every observed `upload_begin`, chunk and finish; the review; the completion |
| `assertions.json` | U0–U9, the exported error, `cleanup_ok`, `within_deadline`, `drivers_bound`, `ok` |
| `resources.json` | Processes started (both Bridges), each cleanup step, leftovers, directory removal |

No tokens, pairing codes, upload or transfer IDs, local paths, file content, environment values or raw
exception text are written. A Bridge error is exported as its code only.

## Scope and limits

**Verified:** on one Linux host:
- a real Bridge is SIGKILLed after the Hub accepted an upload chunk whose ACK it had not journaled;
- the same Bridge state resumes the original transfer in the same Hub session at the held offset;
- the reviewed import lands only after an explicit decision on its exact request;
- the workspace then holds exactly the input.

**Not verified:**
- A crash at other points: before a chunk is sent, during finish, or during the import.
- Several chunks in flight, or several files.
- Network partitions, cross-host recovery, Hub or Runtime restarts, R3.
- A program reading the uploaded input (no task is submitted).
- Windows or macOS, sites, licensed software or scientific validity.
