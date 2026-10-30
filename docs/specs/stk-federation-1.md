# Federation admission, consent and local aggregation v1

This is an implemented backend foundation, not completed S4 network/training
acceptance. It adds no `suan.contracts.load_schema` ID. It supplies bounded
model/delta bytes, node-owned consent, an auditable explicit update outbox and
separately installed Flower aggregation. No listener, STK outbound adapter,
training scheduler, desktop consent UI or model admission/publication is supplied.
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

## Acceptance still required

Authenticated STK outbound transport, persistent coordinator lifecycle, Linux
Runtime training integration, desktop dataset consent and per-round audit viewing,
and actual three-node network operation remain to be integrated. Peer pairing,
file transfer and network stages in `stk-peer-1.md` also remain. Local processes,
pipes and mathematical convergence do not replace those requirements or establish
material-model accuracy. Initial Linux nodes, three participants each round,
independent Flower, disabled telemetry/update checks and no initial SecAgg+
remain the approved direction.
