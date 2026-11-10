# Desktop MuPRO diagnostic requests v1

The desktop Bridge adds five `mupro.preflight.*` methods. They use an existing saved
direct/SSH Runtime connection and the [preflight task/result contract](mupro-preflight-task-1.md).
They do not add Agent tools, automatic placement or permission to run a simulation.

## Methods

| Method | Params | Result and effects |
|---|---|---|
| `describe` | `connection` | `{connection, connection_identity}`. Credential-free identity metadata; no health request or prerequisite check. |
| `list` | `project_id` | `{records}`. At most twenty recent local diagnostic records for this project; no Runtime I/O. |
| `reserve` | `project_id`, `connection`, `expected_connection_identity`, `workspace_id`, `options`, `idempotency_key` | `{record}`. Save a frozen request locally in `prepared` phase. No backend resolution or execution. |
| `retry` | `project_id`, `id` | `{record}`. An explicit execution/recovery request for the acknowledged original record. Known tasks are returned without another submission. |
| `refresh` | `project_id`, `id` | `{record}`. Read the original task and verify its artifact. No submission, recollection, cancellation or approval. |

Project IDs are canonical UUIDs; record IDs and idempotency keys are lowercase 32-digit
hex strings. `expected_connection_identity` is the existing 16-digit Runtime backend
`server_key`. Options accept only `backend`, `walltime_seconds`, `memory_mb`, `queue`,
`account` and `name`. The fixed task uses one CPU. Client SDK, licence, script, program,
case and environment overrides are rejected.

`workspace_id` is an existing Runtime workspace ID or null. Null explicitly requests
creation of an empty diagnostic workspace when `retry` executes. Creation uses its own
stable key derived from the original diagnostic ID. A recovered creation and subsequent
submission reuse that workspace and the original task key. No inputs are uploaded or
read from the project.

## Reservation and recovery

The native caller must receive the durable `reserve` acknowledgement before sending an
execution RPC. Its single explicit check action may then continue with `retry` while
the original view/target is current. Losing the reservation reply cannot leave a queued
execution request behind. Closing, hiding or changing context before acknowledgement
does not start a task.

The private Bridge journal lives outside project files. It freezes the project label,
connection, identity, original workspace choice, canonical options and key before I/O.
Resolved workspace/task IDs, task state and verified results are separate fields. Same
key and equivalent defaults return the same record; changed requests conflict.

Interrupted `creating_workspace` or `submitting` records reopen as `unknown`.
`prepared` records remain unsubmitted. Reopening and listing perform no remote action.
Only an explicit recovery uses the old target and key; editing current controls does
not redefine that request. Active duplicate calls are deduplicated without holding the
journal lock during HTTP. Closing the Bridge does not cancel jobs or erase records.

A damaged journal is unavailable, with no implicit deletion or rebuilding. It disables
diagnostics while other Bridge methods remain available. The implementation bounds each
record to 128 KiB and the journal to 4,096 records; listing returns the twenty most
recently updated matches. Older identities remain addressable by their known ID.

## Records and observations

The authoritative closed shapes are in
[`desktop-bridge-1.schema.json`](../../suan/contracts/schemas/desktop-bridge-1.schema.json).
Records contain `id`, `project_id`, frozen `request`, resolved `workspace_id` and
`task_id`, `phase`, `task_state`, `task_exit_code`, `result`, `error`, `created_at` and
`updated_at`.

Phases are `prepared`, `creating_workspace`, `submitting`, `unknown`, `accepted`,
`running`, `finished` and `error`. `finished` means an observation was verified; failed
configuration checks can be a valid `failed`/1 task with a `checks_failed` observation.
It does not mean MuPRO, licensing or a scientific case is ready. Task cancellation,
infrastructure failures and malformed artifacts retain the original identity and error.

Cached observations retain their original timestamps. An explicit refresh checks the
frozen connection, exact task specification, state/exit consistency, artifact size and
SHA-256, strict observation schema and final task identity. It never substitutes a local
check. Raw endpoints, credentials, worker paths, environment and diagnostic output are
not copied into the public records.

Bridge support and native panel delivery are separate acceptance steps. Target platform
UI clicks, view lifecycle and draft preservation require native validation; the task
checks themselves are not evidence of an installed/licensed solver.
