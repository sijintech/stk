# MuPRO preflight task result v1

An explicit preflight task observes the environment of its Runtime worker or scheduler
allocation. It runs the existing prerequisite checker and may source the worker's
configured trusted scripts. It creates a task and uses execution resources. It does
not run MuPRO, start MPI, check out a licence, or authorize a later simulation.

The inner observation remains [`stk.mupro-preflight/1`](mupro-preflight-1.md), with
`scope: local_process`. The task result associates those bytes with the task and the
client's selected connection. It does not establish an authenticated physical machine
identity, a MuPRO software version, licence validity, or scientific correctness.

## Commands

```text
suan mupro preflight --profile NAME --workspace WORKSPACE_ID
                    [--backend local|pbs|slurm] [--walltime SECONDS]
                    [--memory-mb MB] [--queue NAME] [--account NAME]
                    [--name NAME] [--key KEY] [--wait] [--timeout SECONDS]
suan mupro preflight-result --profile NAME TASK_ID [--output NEW_FILE]
```

The normal Runtime connection options also allow `--state-dir` or the existing local
connection selection. No SDK, licence, script or program paths are transferred from
the client. The worker uses its own configured environment. `local` describes the
selected Runtime's backend; it need not be the desktop's machine. Cluster backends
require an explicit walltime. Every preflight requests one CPU, no MPI ranks, no case
inputs, and no client environment overrides.

Without `--wait`, submission prints the existing Runtime task record. The idempotency
key is printed before submission. After a lost response, explicitly repeat the same
request with that key; changed options conflict under the existing Runtime rules.
Neither command automatically submits a replacement after an uncertain outcome.

`--wait` verifies the completed task's observation. `preflight-result` only reads the
given task and can be used by a new client process. Queued, running, unknown or cancelled
tasks do not yield a verified preflight result. Existing generic task/log commands
remain available to observe or cancel the original task.

Both result paths print the envelope below. They exit 1 for `checks_failed` and 0 for
`checks_incomplete` or `checks_passed`; operational errors are nonzero. Exit 0 is not
solver readiness. `--output` creates a new file containing the verified envelope and
refuses an occupied destination. No result file is written before verification.

## Worker and artifact

The task's fixed command is `[{python}, -m, suan.mupro.preflight]`, with no case inputs,
an empty task environment, one CPU, and the single declared output
`stk-mupro-preflight.json`. The worker creates that output exclusively before collecting;
an existing file or symlink prevents collection. Configuration check failures still
write a valid observation and exit 1. An infrastructure failure may leave no valid
observation. An older compute package missing this entry point fails explicitly;
the client never substitutes a check of its own environment.

Results are accepted only for this unmodified task specification. The declared artifact
must be unique, have a positive size no greater than 65,536 bytes, and carry a lowercase
SHA-256 digest. A single bounded range request reads exactly that size. The client
checks size, digest, strict UTF-8/JSON and the complete inner schema, then checks the
same connection and core task again. Dynamic monitoring metadata is not task identity.

Task completion must agree with the observation: `succeeded`/0 for incomplete or
passed checks; `failed`/1 for failed checks. Other combinations are execution failures,
not verified preflight results. No extra Runtime HTTP route or automatic execution
permission is introduced.

## Result envelope

The object has exactly these fields:

| Field | Meaning |
|---|---|
| `schema` | Exactly `stk.mupro-preflight-result/1`. |
| `scope` | Exactly `runtime_task`. |
| `target` | `{profile: string|null, connection_sha256: string}`. Profile argument, or null for existing default selection; SHA-256 of the client's stable connection identity. The raw connection address, SSH host and credentials are not emitted. |
| `task` | `{id, workspace_id, backend, state, exit_code}` from the verified Runtime task. |
| `artifact` | `{path: "stk-mupro-preflight.json", size: integer, sha256: string}` from the unique verified artifact. |
| `observation` | The complete existing `stk.mupro-preflight/1` observation from that artifact. |

The connection digest is a correlation value, not authentication or a portable node ID.
A changed saved profile may select a different Runtime; callers must keep the intended
connection and original task ID. Observations record their own collection timestamps
and may become stale. Refreshing a result reads those same bytes and does not refresh
the checks. Running another check requires another explicit task submission.

This contract does not add node-list projections, automatic placement, desktop checks,
Agent tools or permission extensions. These integrations require their own review.
