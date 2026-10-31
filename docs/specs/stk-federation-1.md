# Federation admission, consent and STK training transport v1

This backend adds bounded model/delta bytes, node-owned consent, an explicit
update outbox, fixed Runtime training, STK outbound WSS/blob transport and explicit
persistent rounds with separately installed Flower, plus an additive trusted-owner
management API and independent held-out linear evaluation/version registry.
It is not completed S4 product or cross-site acceptance and adds no
`suan.contracts.load_schema` ID. There is no Flower listener or automatic scheduler.
Desktop owner methods use the published bridge schema; platform acceptance is
recorded separately. Loopback tests do not establish NAT/TURN deployment.
Public-data labels and peer project grants do not authorize federation training.

## Array bundle

`suan.federation.updates` uses only the standard library. The wire begins with
`STKFAR1\n` (eight bytes, including LF), then four-byte unsigned big-endian header length,
strict UTF-8 JSON header, then contiguous raw array buffers.

Header keys are exactly `format`, `kind`, `arrays`, `payload_bytes`,
`payload_sha256`. Format is `stk.federation-arrays/1`, kind is `model` or `delta`.
Each ordered array descriptor has exactly `name`, `dtype`, `shape`, `offset`,
`nbytes`, `sha256`. Offsets begin at zero in the raw payload. All declared lengths
and payload/array SHA-256 values must match actual bytes; gaps, overlaps and
trailing bytes are rejected. There is no compression, pickle or executable format.

Names are unique, nonempty/non-whitespace, contain no controls and fit 128 UTF-8
bytes. Dtypes `f32`/`f64` mean little-endian IEEE float32/float64. Shapes have 1–4
positive integer dimensions; products are checked against the byte budget before
allocation. Booleans are not integers. Every floating value must be finite.
Limits: 128 arrays, 64 KiB header, 64 MiB **whole wire including header/magic**.

A layout is an ordered list of exact `{name,dtype,shape}` descriptors.
`validate_layout` checks metadata without allocating tensor buffers; a complete
bundle's total budget is checked by its encoder/decoder. Layout matching preserves
name, order, dtype and shape without silently casting or reshaping.
Encoders use compact sorted-key JSON. Decoders reject BOM, invalid UTF-8,
duplicate/unknown keys, malformed structures and nonfinite constants.
`decode_arrays` returns detached `format`, `kind`, `arrays`, `layout`, `sha256`,
`bytes`; the latter two identify the entire wire. Mutable byte inputs are copied
after a size check. No partial arrays are returned before full validation.

## Update and round admission

`stk.federation-update/1` has exactly these fields:

| Field | Value |
|---|---|
| `format` | `stk.federation-update/1` |
| `run_id` | canonical UUID |
| `round` | integer 1–10000 |
| `participant_id` | lowercase 64-hex public identity fingerprint |
| `model_sha256` | actual entire **base model bundle** SHA-256 |
| `spec_sha256` | owner-pinned frozen model/training specification SHA-256 |
| `dataset_sha256` | owner-pinned frozen local dataset identity SHA-256 |
| `grant_id` | canonical owner-consent UUID |
| `update_sha256`, `update_bytes` | actual entire delta bundle SHA/length, at most 64 MiB |
| `num_examples` | integer 1–1000000000, not a boolean |
| `metrics` | at most 32 nonempty/control-free keys of at most 64 characters; finite numeric values |
| `masked` | exactly boolean false; no secure-aggregation claim |

`validate_update` requires expected run, round, participant, base model, spec,
dataset and grant independently from trusted local state. Metadata is not sender
authentication. Callers also decode actual delta bytes against the approved layout
and compare actual wire SHA/length with update metadata.
`validate_round` accepts a trusted map of 3–20 approved peers to
`{dataset_sha256,grant_id}`. At least three distinct valid updates are required.
Duplicate/unknown peers or any invalid supplied update reject the whole set;
invalid updates are not silently dropped to proceed with a smaller round.

Dataset/spec hashes are owner pins, not a new cooperative dataset format. This
layer does not read data, validate model architecture or start training. A real
runner must resolve and verify frozen local inputs before approved execution.
Raw datasets are not model/delta bundles. Unmasked updates are visible to the
approved coordinator and do not provide differential privacy.

## Local consent and immutable audit

`ConsentRegistry` uses private node-owned SQLite state outside shared projects.
Constructing/reading it does not create state, send, train or recover anything.
The local owner calls `grant(run_id, *, coordinator_id, participant_id, dataset_id,
dataset_sha256, spec_sha256, model_layout, max_rounds)` explicitly. A new grant
binds the recipient, participant, run, opaque local dataset UUID, frozen hashes,
ordered approved layout and round limit. Layout is persisted with a digest and
revalidated; a self-asserted spec hash alone does not authorize arbitrary arrays.
No path is accepted from the remote party and no public label implies consent.

`authorized(...)` retains a process lock plus SQLite `BEGIN IMMEDIATE` lease over
an accepted short dispatch/publish, including against another registry instance.
Do not hold it throughout training. Actual authenticated identity must come from
trusted transport; this local API does not authenticate asserted identity strings.

`prepare_update(grant_id, metadata, payload, *, model_sha256)` separately binds the
trusted local base model, rechecks current grant and completely decodes a delta
against the owner's layout. Exact bytes/metadata/layout are retained before send.
One `(grant_id,round)` has one original update: identical repeats read it, changed
originals conflict. Preparing and reading do not send. Default audit pages exclude
payloads; `get_update(..., include_payload=True)` reads the actual retained bytes.

`send_update(update_id, *, coordinator_id, deliver)` is one explicit attempt.
The trusted `deliver(metadata,payload)` callback must use the pinned authenticated
recipient and a finite deadline. The registry first commits `sending` intent,
then reacquires a lease, rechecks consent and all retained bytes/bindings, and
holds the lease during the callback. Withdrawal winning before this second check
prevents the callback; it waits for a send already accepted under the lease.
Already departed bytes cannot be recalled.

Callback success records `delivered`, meaning transport callback delivery, not
round aggregation or model admission. Repeating it returns the old delivered
record without invoking the callback. Callback/commit uncertainty retains the same
identity and prevents automatic resend. Death leaves durable `sending`; explicit
`recover` can mark `uncertain` and never sends/retrains. No automatic GC or identity
reset occurs. Registry rollback/loss cannot prove globally exactly-once delivery.

Quotas: 1024 grants, 4096 updates, 64 MiB per bundle, 64 KiB each metadata/layout,
512 MiB total payload plus actual UTF-8 audit bytes. The total cap can be lowered.
Pages have at most 100 records and 1 MiB. Owner audits remain readable after
withdrawal; `as_dict` returns detached JSON, and nested descriptor data is frozen.

## Isolated Flower aggregation

`FlowerAggregator(python, timeout=30)` is passive and installs nothing. Explicit
`aggregate(model, updates, *, participants, run_id, round, spec_sha256)` validates
the whole round and actual delta bytes before launching the selected interpreter.
Inputs are immutable bytes, combined model/deltas at most 256 MiB. Metric key
sets must agree; `num-examples` is the strategy's reserved weight key.

Use base STK plus **flwr 1.42.0 / NumPy 2.5.4** in a separate Linux environment;
do not install STK's `control` extra there or Flower in the public Hub.
The worker is `python -I -m suan.federation.flower_worker`, with fresh private
bounded staging files. It inherits only known noncredential settings: product key
empty/model absent; Flower telemetry/logging/update checks off before imports.
Stdout/stderr are discarded. Python socket audit hooks reject network attempts as
defence in depth, not an OS sandbox or egress guarantee.

The adapter uses `FedAvg.aggregate_train` and version-bound internal
`TaskIdentity`/`make_message` helpers. Review them and rerun independent numerical
regressions before upgrading; this is not a stable-public-API claim. It reconstructs
complete candidate weights from the exact base plus admitted deltas. No training,
SuperLink/SuperNode/gRPC service or potentially unbounded node-sampling loop starts.
The local process has one finite deadline, at most 300 seconds, without retry.

Results are finite same-layout model bundles and strictly typed receipts bound to
run/round/source model/spec/participants/sample total/framework version. The result
is an unregistered candidate. Held-out evaluation, model admission, publication
and rollback remain explicit separate operations. Failure does not install,
train, send, resume or publish anything.

## Frozen trainer and messages

`stk.federation-training-spec/1` has exactly `format, trainer, features, targets,
dtype, normalization, steps, learning_rate, strategy, proximal_mu`. The installed
trainer is `linear-regression/1`; each ordered column has `{name,unit}`, with
1–64 features and 1–16 targets. Dtype is f32/f64; normalization is exactly `none`.
Steps are integer 1–1000, learning rate finite (0,1], strategy fedavg/fedprox.
Proximal mu is finite [0,100], zero for FedAvg and positive for FedProx. Both use
multi-target mean-squared error; FedProx penalizes distance from the exact round
base. No per-node fitted normalization changes the shared parameter space.
Parameters are ordered `weights:[features,targets]`, then `bias:[targets]`.
Canonical compact sorted-key UTF-8 JSON identifies the complete spec by SHA-256.

`stk.federation-message/1` has exactly `format, operation, run_id, round,
coordinator_id, participant_id, grant_id, spec_sha256, dataset_sha256, model`.
Operations train/status/collect/cancel **all** retain the original full binding;
model is exactly `{sha256,bytes}` of the approved base. Limits are 64KiB JSON,
canonical UUIDs, 64 lowercase hex fingerprints/hashes and integer round 1–10000.
No remote task ID, host path, argv, module, interpreter, environment or training
option override is accepted. Structural validation alone is not authorization.

Node receipts `stk.federation-node-result/1` have exactly `format, run_id, round,
participant_id, grant_id, state, task_id, update_id, update`. State is prepared,
queued, running, ready, delivered, failed, cancelled, unknown or uncertain.
Task ID is null or 32 lowercase hex; update ID is null or a canonical UUID.
Update is null except an explicitly collected delivered receipt, where it is
the exact 13-field update metadata above. Ready/delivered require an update ID.
No full Runtime spec, private path or raw array appears in a receipt.

## Owner-bound Hub relay

Only an authenticated Hub owner registers `stk.federation-run/1` with exact fields
`format, run_id, coordinator_device_id, coordinator_id, spec_sha256, participants,
max_rounds`. Participants are 3–20 distinct `{node_id,participant_id,grant_id,
dataset_sha256}` records. Paired device IDs are **32-hex**, public fingerprints
**64-hex**. The owner independently verifies this mapping; bearer authentication
does not prove private-key possession. Only the designated current paired client
executes coordinator actions. Owner administration does not imply coordinator
execution or override a node's own dataset consent.

Routes under `/api/v1/federation/runs` are POST registration, GET `/{run_id}`
and POST `/{run_id}/revoke`. Model routes are PUT/GET/HEAD
`/{run_id}/rounds/{round}/model/{sha256}`; update routes are PUT/GET/HEAD
`/{run_id}/rounds/{round}/updates/{participant_id}/{update_id}/{sha256}`.
PUT requires exact Content-Length and actual bundle SHA/length; its receipt binds
`run_id,round,kind,participant_id,update_id,sha256,bytes`. Models use empty participant
and update IDs. The coordinator writes/reads models, approved nodes read them;
only the corresponding node writes its delta and the coordinator reads it.
Authorization precedes existence checks. Bytes live in a separate federation CAS,
outside ordinary blobs/upload/import/GC, with retained original refs and bounded
space/concurrency. Interrupted uploads retain their identity and space reservation;
cross-process leases serialize each upload identity. No automatic GC resets them.

`POST /api/v1/actions` kind `fl.message` uses existing durable actions and outbound
NodeAgent WSS. The Hub checks all run/device pins, target and already-published
round model before queueing and again before dispatch. Model proposals cannot
submit FL actions. Action reads/events are scoped; oversized FL results fail
instead of entering the ordinary client-readable blob CAS. Revoke stops future
action/blob authorization, not already accepted Runtime work or departed bytes;
the response explicitly reports `tasks_stopped:false`. Run audit remains readable
to its owner/coordinator, and re-registration does not reactivate a revoked run.

## Private Runtime training and coordinator lifecycle

Trusted local owner code registers numeric x/y data and approves the frozen spec
with `NodeFederationService`. The internal dataset identity binds its full manifest,
including column names and actual data SHA; this does not decide the cooperative
`stk.dataset/1` format. Raw datasets, base/delta bundles, jobs and results stay in
private node state disjoint from Runtime workspaces and shared projects. Runtime
`outputs` is not an access-control list. The fixed worker's public work contains
only a sanitized terminal receipt; ordinary NodeAgent snapshots, cached actions,
graph/task/file routes must exclude or reject retained private identities.
Identity snapshots traverse retained state once; unknown task lookups recheck
current reservations after Runtime observation before allowing an ordinary action.

Before dispatch, a persistent `(grant_id,round)` original binds the private job,
fixed installed `python -I` command, workspace and Runtime idempotency key. Changed
base/spec/data conflicts. Lost replies resolve the original task; reopen/status
never submit or retrain. The worker's single-attempt marker prevents replay and
current consent is checked before training and before publishing private results.
The environment is allowlisted, product key empty/model absent and Flower state
private; telemetry/update checks are disabled before imports. Socket audit is
defence in depth, not a same-user OS sandbox. Cancel intent is persisted before
Runtime cancellation; Runtime remains authority for the process-tree terminal state.
Only collect calls the consent outbox publisher under its durable sending intent
and lease. Unknown sends never replay. Raw bundle storage is capped at 512MiB;
metadata has separate 256KiB/file and retained-object limits, not a 512MiB total
private-directory guarantee.

`FederationCoordinator.create/prepare_round` freezes local originals without
network side effects. Explicit train publishes the model and submits each retained
original action once. Recover only queries those actions; observe uses fresh status
actions after prior observations finish. Explicit collect can recheck a definitively
failed action while the node outbox still forbids duplicate sends. Aggregate requires
at least three distinct approved delivered updates and verifies actual bytes with
the independent aggregator. Initial/previous candidate/round base hashes are checked
before reuse. An interrupted aggregation remains `aggregate_uncertain` for evidence
review and is never automatically repeated. The next round requires explicit prepare;
opening a coordinator never trains, sends, advances rounds or admits a model.

## Trusted Runtime owner management (additive extension)

Only a trusted local Runtime configuration may select `federation_node_root` and
optional `federation_coordinator_root`. The node root is the actual NodeAgent
registry root, disjoint from Runtime workspaces/shared projects; coordinator reads
use only canonical run UUID/round beneath its fixed root. No RPC selects a path,
module, executable or credentials. Existing direct/SSH Runtime Bearer authority
accesses `POST /v1/federation/owner/{method}`; Hub paired clients cannot proxy it.
Runtime remains Linux-only and loopback-bound. The optional health feature is
`federation_owner`; absent configuration preserves the previous health contract.

The closed method set is `info`, `operations.get/recover`, `datasets.register/list`,
`grants.approve/revoke/list`, `audit.list`, `candidates.get`,
`evaluations.prepare/evaluate/get`, `models.list/admit/activate`.
`RuntimeClient.federation_owner` rejects duplicate/nonfinite JSON, private extras,
foreign operation/method bindings and malformed bounded results independently.
The request is at most 4MiB, depth 64. No method automatically retries.

Every write has exactly `{operation_id,owner_id,expected_generation,request}`.
UUIDs are canonical; `owner_id=null,expected_generation=0` is accepted only before
the first operation reservation. An initial semantic rejection can create owner
metadata at generation zero without reserving an operation or registering data.
The complete original request digest and intent are retained before effects.
The closed `stk.federation-owner-operation/1` reply has exactly
`format,owner_id,generation,operation_id,method,request_sha256,state,result`.
`request_sha256` hashes canonical UTF-8 of the complete write envelope, preserving
integer/float differences. Its generation is the original reserved generation,
not a fresh observation of the owner's current generation. `state` is
`completed` or `uncertain`; an uncertain result is null. Same-ID/original requests
return the original record; changed method/request conflicts. A fresh global CAS
is obtained through explicit `info`, which is passive before initialization.

`operations.get({operation_id})` returns the retained operation or null, without
effects. Explicit `operations.recover` uses a new envelope with request
`{operation_id: original_id}`. Its result is the nonrecursive
`{format:'stk.federation-owner-recovery/1',operation:{owner_id,generation,operation_id,method,request_sha256,state}}`.
Query the original ID separately for its full result. Recovery never replays
training, sending, approval or admission. Partial registration can verify/fill
only missing publications of the same frozen two-capsule request.

A definitive pre-reservation rejection is HTTP 409 with exactly
`{error: string, rejection: proof}`. The proof has exactly
`{format,operation_id,method,request_sha256,owner_id,generation,reason}`;
`format` is `stk.federation-owner-rejection/1` and `reason` is `stale_owner` or
`invalid_request`. Under the owner lease, the original operation ID must be absent
and no operation INSERT or business effect may have occurred. Its owner UUID and
generation describe that rejection checkpoint; its digest binds the complete
original write envelope, including its original CAS. The Runtime client and bridge
validate this binding independently. The bridge persists the verified proof before
exposing it, so local history can distinguish `rejected` from `uncertain` after a
reopen. The caller must explicitly read fresh owner information before choosing a
new operation UUID; the rejected request is never automatically resent.

An existing-ID conflict, generic HTTP error, invalid or foreign proof, missing
lookup, or failure after reservation is not such a proof. These outcomes cannot
clear an uncertain intent. A rejected operation is absent from the Runtime
operation table; the bridge retains its original intent and proof locally.

Known linear evaluation/version refusals are preflighted before the outer owner
reservation, using the existing linear-registry lease without creating an absent
registry root. This includes reviewed identities and active-version/generation
CAS. Execution checks them again after reservation; a subsequent concurrent change
still produces an uncertain retained operation, never a retroactive rejection.

`stk.federation-registration/1` has exactly `format,source,source_sha256,roles`.
Source binds `project_id,revision,table_id`, ordered feature/target descriptors
`{field_id,name,unit}`, and nonempty disjoint `training_rows,holdout_rows` UUIDs.
At most 1000 total rows, 64 features, 16 targets are admitted. Each role is exactly
`{manifest,x,y}`, using `stk.federation-local-dataset/1` and the actual f64 array
SHA; the manifest is published last without overwrite. Integer inputs must be
exactly representable in f64. This internal numeric capsule does not choose the
pending partner dataset format. Metadata replies exclude numeric arrays/paths.

Approval binds a registered **training** role, source/dataset SHA, exact ordered
training spec, run, coordinator/participant 64hex public identities and max rounds.
Its fixed grant UUID is the operation UUID. The same original grant is retained
after revocation and never reactivated by replay/recovery. Reading audit does not
send a prepared update. Owner and registry operation quotas retain identities;
backup/registry rollback does not establish global exactly-once execution.

## Independent held-out linear evaluation and model versions

The owner reads `stk.federation-candidate/1` metadata only from a fully aggregated
coordinator round and verifies candidate, base, receipt, spec and actual bytes.
It does not use the Materials `stk.curve-model/1`/PyTorch MLP registry.

Evaluation preparation binds a registered heldout role, exact row/field/unit
source, candidate/base SHA, spec SHA, active version/generation and a nonempty
ordered threshold list `{name,unit,max_rmse}`. Thresholds must be explicitly
provided, finite and nonnegative; no scientific value is supplied by default.
`stk.federation-evaluation/1` has exactly
`format,evaluation_id,state,plan_sha256,plan,metrics,gate,receipt_sha256`.
States are `prepared,passed,failed,uncertain`; preparation/reads never infer or
train. An explicit evaluate intent precedes a single bounded local inference.
Interrupted inference is uncertain and is not automatically repeated.

Candidate/base/frozen baseline metrics report per-target RMSE in unchanged raw
units. Without an active version the baseline is the round base. Every target
must satisfy its absolute threshold and not regress against that frozen baseline.
Numeric failure produces a failed receipt, null metrics and an empty gate.
The plan/receipt hashes and actual frozen bytes are rechecked at admission.

`models.admit` explicitly registers an immutable version and receipt, without
changing the active pointer or active generation. `models.activate` alone
switches or rolls back to an admitted version using exact expected active version
and generation; every successful switch increments generation, preventing ABA.
An old admission receipt/recovery cannot reactivate a subsequently changed model.
Publication intent precedes effects; only a proven exact postimage is recovered,
and orphan version directories are not silently adopted or overwritten.
Limits include 128 versions/spec, 1024 evaluations and 256MiB linear registry storage.
These software/row-identity checks do not establish material accuracy or independent
specimen/site sampling.

## Acceptance still required

Loopback acceptance uses three independent Linux Runtimes, three outbound agents,
actual TCP/WSS and run-scoped blobs for FedAvg/FedProx rounds with an independent
numerical reference. Owner/bridge evaluation and desktop tests have separately
recorded scopes; neither loopback nor CPU UI checks prove cross-site deployment,
NAT traversal, target-OS input or a complete production collaboration workflow.
Peer pairing, distributable dependencies, authorized resumable files and network
stages in `stk-peer-1.md` also remain. Numerical/software acceptance does not establish
material-model accuracy. Initial Linux nodes, at least three participants per round,
independent Flower, disabled telemetry/update checks and no initial SecAgg+ remain
the approved direction.
