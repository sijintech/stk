# D1 backend parity: one task, two deployments

This harness implements the first slice of D1 as chosen in
[d1-compatibility-gates.md §1.1(a)](../../docs/planning/d1-compatibility-gates.md). It uses only existing entry
points; it adds no product command and no published contract.

On one Linux host it starts two private deployments from the same STK installation:

| Deployment | Processes started by this run | Client used here |
|---|---|---|
| A, direct | `suan server init` / `start` (Runtime API and supervisor) | `RuntimeBackend` over the Runtime HTTP API |
| B, Hub | `suan-control init` / `serve` (HTTP and WebSocket Hub), `suan-node pair` / `run` (outbound NodeAgent), and a second `suan server` Runtime | `HubClient` + `HubBackend`, with a paired client device |

Both sides run the same two public synthetic programs with an identical `{python}` argv. B registers them as
exact operator templates (`--template-file`), so the Hub's existing review rules let them run without review.

## What is compared

For each side, using only that side's own authority and IDs:

1. A completed submission, observed with an exact task read. On B this is a live `task.get` with
   `require_live`; the heartbeat task list is never used to decide whether a task exists.
2. Resubmitting the same key on the same path returns the original task.
3. The same key with a different request is refused as `conflict`.
4. The artifact list and the downloaded bytes. Each side must list exactly `out.txt`, with the fixed
   expected UTF-8 bytes (size and SHA-256), and the downloaded bytes must have that SHA-256. An empty or
   different list fails.
5. UTF-8 stdout read by byte cursor, including a cursor that starts inside a multi-byte character.
   The stdout must be non-empty and identical on both sides.
6. An explicit cancel of a running program, and a repeated cancel. The cancel is sent only after the
   program has printed its first line, so it stops a real process.
7. Real executions. Each program first appends one `start <pid>` line to `parity-start.marker` with a
   single `O_APPEND` write. The marker lives in its run directory, outside the working directory, so it is
   not published as an artifact. After replay and conflict, each workspace must have:
   - exactly two task records;
   - exactly two run directories, each with a finished record and a marker of exactly one line
     `start <positive PID>`;
   - that PID equals the program PID the Runtime recorded in `program.json`. On Linux the worker execs
     the program in place, so it is the same process.
   - valid recorded worker and program identities (positive integer PID, finite positive create time)
     that have exited, checked by PID plus create time.

   A malformed line, an extra line, another PID, a missing or malformed identity, or a third run directory
   fails.

IDs are never expected to match across paths, and recovery never switches paths. A wait that expires is
reported as `unknown`, and nothing is resubmitted. An unreachable service or node is retried as
unreachable, never recorded as a task failure.

## Time budget

`--deadline` (default 170 s) must be a finite positive number. It is the budget for setup and the scenario:
- every wait, CLI call and Hub action is bounded by the time left;
- once the budget is spent, the next call is not made and the run ends `unknown`;
- a scenario that ends after the budget fails (`within_deadline: false`).

Cleanup runs after the budget, with its own bounded grace per step:
- 15 s plus 5 s for each spawned process group;
- up to 60 s for each `suan server stop`;
- 10 s for terminating leftovers.

So the deadline is not a hard limit for the whole run. Wrap the command in an external watchdog (for
example `timeout 300`) if you need one. The manifest records `scenario_seconds` and
`elapsed_seconds_including_cleanup` separately.

## Running it

```sh
# The interpreter's installed STK (e.g. a venv with only .[server,control,test]); nothing is injected:
STK_TOKEN_PLAN_API_KEY= /path/to/venv/bin/python examples/backend_parity/offline.py \
    --mode installed --evidence-dir EVIDENCE_DIR

# This source tree, through PYTHONPATH (for development), with an external watchdog:
STK_TOKEN_PLAN_API_KEY= timeout 300 python examples/backend_parity/offline.py --mode source \
    --evidence-dir EVIDENCE_DIR

# The focused tests, including one real source-mode run:
STK_TOKEN_PLAN_API_KEY= python -m pytest -q tests/test_backend_parity.py
```

Leave `STK_TOKEN_PLAN_MODEL` unset.

Before starting anything, the harness checks where STK is imported from. It probes itself, and a child with
the services' environment, for 12 key Runtime, Hub and client modules. Both must resolve to the same base
directory, with identical relative paths and SHA-256 for every module. That base must also be what
`--mode` claims:
- `installed`: a `site-packages` directory. Another checkout, or an editable install pointing elsewhere,
  is refused.
- `source`: this source tree.

Otherwise the run fails and starts no process. The manifest records the module paths relative to that
base, their SHA-256 and the harness's own SHA-256, never absolute paths.

Exit codes:
- `0`: every assertion passed, the scenario ended within the budget and cleanup was clean;
- `1`: an assertion failed, a wait ended `unknown`, an error occurred, the budget ran out, or cleanup left
  something behind. There is no pass without assertions.
- `2`: not Linux, or an invalid `--deadline`.

Child processes inherit only `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_*` and `TZ`. `HOME` is kept as it
is. STK state, client profiles, XDG and `TMPDIR` point into the run's private directory. The product model
key is empty, and no model, proxy, display or credential variable is passed on. Every service listens on
`127.0.0.1` only.

The run stops only processes it started:
- the Hub and the node, by their process groups;
- each Runtime, with `suan server stop --supervisor`;
- then any process still running inside the private directory.

The private directory is then removed; `--keep` keeps it for inspection.

Every cleanup step runs even if an earlier one failed. A process that exits between the check and the
signal counts as stopped. Cleanup is clean only if:
- every step succeeded;
- the leftover scan ran and found no process inside the private directory;
- every Runtime stopped and every spawned process exited;
- unless `--keep` was given, the directory is really gone.

A failed cleanup fails the run.

Setup failures are reported like any other error, with evidence still written. These include an
unusable `--work-root` and an import probe that fails. If the evidence directory itself cannot be written,
stdout still carries only the controlled error record.

## Evidence

Written to `--evidence-dir`. These files contain no tokens, pairing codes, environment values or absolute
paths. Errors are exported only as a fixed kind and code with a message written by the harness:
- a failed backend call: `{kind: error, code, message: "a backend call failed"}`;
- any other exception: its type name and a fixed message;
- a cleanup failure: the exception type only.

Raw exception text, command arguments and paths are never written.

| File | Contents |
|---|---|
| `run-manifest.json` | Module origins (base kind; relative paths and SHA-256 of the key modules; harness SHA-256), the checkout HEAD and whether it has uncommitted changes (for reference only; the hashes identify the code run), interpreter and package versions, ports, deadline, scenario and total seconds, verified and not-verified scope |
| `requests.jsonl` | The operations the scenario recorded per side: workspace creation, each submission (operation, key, template, outcome or error code, task ID, elapsed time) and each first cancel. Reads, log pages, downloads, the repeated cancel and setup and cleanup calls are not listed. A run that fails early lists only what it reached. |
| `backend-parity.json` | Per command: both sides' observations, the comparison rule, and whether it is a business rule or a permitted projection difference |
| `assertions.json` | A1–A9, the exported error, `cleanup_ok`, `within_deadline` and `ok` |
| `resources.json` | Processes started, each cleanup step's outcome (failures by type only), leftover PIDs, whether the private directory was created and removed |

## Scope and limits

**Verified:** task-lifecycle semantics on one Linux host, through a direct Runtime and through a real Hub plus
outbound node.

**Not verified here:**
- Project or conversation semantics: there is no cloud project service.
- That the interpreter holds only the minimal extras. Run it with such a venv to check that.
- GUI-free imports inside the service processes.
- Windows, macOS, other hosts or clusters.
- Real solvers, licensed software, or scientific validity of any result.
- Authority identity beyond configuration fingerprints.

The programs are synthetic and prove software behaviour only.
