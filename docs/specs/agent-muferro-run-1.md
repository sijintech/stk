# MuPRO agent preparation and first-start approval, version 1

This additive extension permits a research agent to freeze a MuPRO/MuFerro workflow plan.
The desktop separately records a person's single-use decision to start that exact plan.
The project format, Runtime protocol, existing manual workflow methods and old frozen
agent sessions keep their existing contracts.

## Preparation tool

New sessions may offer `prepare_muferro_run`, version 1, at level `prepare_run`.
Its arguments are exactly `{workflow_id, rows, expected_revision}`: a canonical workflow
UUID, 1–100 distinct canonical case-row UUIDs and a nonnegative integer revision.
Booleans are not revision integers. Existing saved case rows are supported; an AI-created
scan draft is not required. Scientific scan values must come from the user.

The saved workflow, including expanded subworkflows, must use one MuFerro case table,
at least one simulation step, and only `muferro/1` simulations and saved analysis steps.
This tool does not prepare LAMMPS, PET or LaTeX work. It uses the Runtime and execution
options explicitly selected on the desktop; arguments cannot select a host or resources.

Preparation freezes only a local workflow plan. It does not call `MuFerro.prepare`,
upload files, submit tasks, run a solver, or start analysis. The deterministic run UUID
is UUIDv5 of the session UUID and `"<turn>:<call_id>:workflow_run"`. Replaying a call reads
the original plan and approval binding, even if the selected target later changes.
The result contains a bounded summary and an approval item; the complete plan is read
separately. The run is not registered as an agent object kind.

## Desktop methods

These four bridge-v1 methods are desktop-only. They are omitted from the script catalog,
headless API and agent tools. Clients discover all four capabilities before showing
execution controls. Every call uses retry policy Never.

| Method | Parameters beyond `handle, session_id` | Result |
|---|---|---|
| `project.agent.run_target` | `simulation?`: omitted reads; null clears; `{connection, options}` explicitly selects | `agentSessionView` |
| `project.agent.run_plan` | `item_id` | `{item, run}` with the complete frozen workflow plan |
| `project.agent.run_decide` | `item_id, decision, plan_sha256, expected_revision` | `{receipt, revision}` |
| `project.agent.run_observe` | `item_id` | `{receipt, revision}` |

The bridge resolves the selected direct or SSH Runtime's endpoint fingerprint; the caller
cannot supply `connection_identity`. Hub targets are excluded. The fingerprint is a
configuration binding, not cryptographic machine authentication. Resource options are
validated as a MuFerro TaskSpec without submitting it. Selection appends session intent
and changes no editable project revision. Refresh, reopen and workspace restoration do
not select a target or execute work.

Execution checks the frozen endpoint identity on the actual backend instance used by
each Runtime operation, including child-run preparation and submission. Transfer workers
retain the same guard; new transfer journals also bind the endpoint for restart recovery.
A profile change cannot redirect an approved workflow or its resumed transfers.

`agentSessionView` adds optional `run_target` and `run_approvals`. The former is null or
`{connection, connection_identity, options}`. The latter contains at most 20 cards, pending
first then recent consumed cards, independent of event pagination. Each card is
`{item, decision, receipt}`; decision and receipt may be null. The full event chain remains
the authority for older cards. Card receipts are the last saved observation; they do not
implicitly refresh workflow state. The person can explicitly observe the original item.

An item contains `item_id, kind: "start_run", run_id, plan_sha256, request_sha256,
expected_revision, source_event_id, source_turn, source_call_id`. Its identity and original
tool call, frozen tool version/level, arguments, plan and preparation request are checked
against stored evidence. Existing event kinds carry the extension; no new database DDL
or project-format migration is introduced.

## Review, consumption and dispatch

The person first reads the complete plan, including all rows, inputs, analysis definitions,
target and resource options. Truncated summaries cannot unlock approval. `run_plan`
checks the original plan and request hashes and records inspection in this bridge process
only after the complete response fits its line limit. A bridge restart requires inspection
again. The UI binds inspection to the current project opening, bridge, session, item,
plan digest and revision. It must keep uncertain target configuration blocked across
session selection changes until explicitly resolved.

`decision` is `start` or `decline`. A start requires the session to be stopped, the same
current target/resources, the original project revision, an unarchived run, no previous
started event and local executor capacity. Admission failures before consumption leave
the card pending. Decline does not execute and may dismiss a stale plan.

Consumption commits the local human decision before dispatch. Only its first successful
consumption permits dispatch. The subsequent workflow first-start transaction atomically
checks the plan/request digests, revision, archive status and absence of **any** previous
started event, and records the four-key approval envelope with `started`. Separate store
transactions do not guarantee dispatch after a crash: a consumed card may remain uncertain.
This is deliberate; neither a missing receipt nor an error permits another dispatch.

The UI records its pending decision before sending. A lost reply, refresh or reopen offers
only `run_observe` for that original item. Observation never starts, recovers, cancels or
reassigns work. It may append an audit receipt but has no execution effect. An exact
original `started` approval yields historical `outcome: started`; another start yields
`other_start`; no start after consumption yields `uncertain`. Pending and declined cards
yield `pending` and `declined`. In a fresh observation, `run_status` is the current workflow state and is separate
from the historical start receipt. Historical success grants no restart or retry right.

Local user/host labels are recorded with `authenticated: false`. Neither model output nor
a human-label string is an authentication credential. Existing explicit manual workflow
controls retain their separate behavior; this extension grants no automatic cancel,
restart, retry, draft application, data relabeling or settings changes.

## Data and validation boundaries

Workflow-run source metadata is private to the local/institutional model boundary even
when its parameter table is public. Planner calls remain local or internal; the agent
does not change model endpoints, credentials or network policy.

The HDF5 contract remains [MuPRO HDF5/1](mupro-hdf5-1.md). HDF5 discovery and attached
result collection do not establish solver completion by themselves; existing DAT completion
verification remains required. Manufactured Runtime tests verify software behavior, not a
real MuPRO license, scientific scan protocol, material validity or target-OS UI acceptance.
