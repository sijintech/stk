# Local materials training and frozen inputs, version 1

This additive contract covers the local materials service and its desktop bridge
methods. It does not change the existing curve-training `stk.dataset/1` directory
or choose the cooperation dataset formats that remain under discussion.

## Frozen inputs

`stk.materials-training-input/1` is a private capsule containing `manifest.json`,
`dataset.json` and `samples.jsonl`. Optional `base/` and `baseline/` directories
each contain exactly `model.json` and `model.pt`. Unlisted payload files are
rejected. No source path is needed to train from the capsule.

The manifest has exactly these fields:

| Field | Meaning |
|---|---|
| `format` | `stk.materials-training-input/1` |
| `sha256` | SHA-256 of the canonical manifest with this field omitted |
| `kind` | `pe_loop` or `capacity_fade` |
| `dataset` | Existing semantic dataset `sha256` and the local validated `card` |
| `options` | Complete normalized training settings |
| `split` | Ordered sample ID arrays named `train`, `validation`, `test` |
| `base_model` | Initialization role, or null |
| `baseline_model` | Prepare-time active comparison role, or null |
| `files` | Exact relative payload path → `{size, sha256}` |

Each model role is `{model_sha256, weights_sha256, model_size, weights_size}`.
Canonical JSON uses sorted keys, compact separators, UTF-8, `ensure_ascii=False`
and `allow_nan=False`. Arrays retain order. The top-level manifest is limited to
16 MiB; each dataset/model JSON to 1 MiB, samples to 256 MiB and each role's weights
to 256 MiB. Files must be ordinary files; links, junctions, reparse points,
changing files and special files are rejected. Publication never replaces an
existing capsule, and the manifest is published last as its readiness marker.

Options retain the existing defaults: hidden `[128,128]`, 400 epochs, batch size
64, learning rate 0.001, patience 40, seed 0 and split `[0.7,0.15,0.15]`.
Hidden layers number 1–4 with widths 4–1024; epochs/patience 1–5000; batch size
1–4096; finite learning rate in `(0,1]`; integer seed 0–2147483647. The three split
fractions must be finite, positive and sum to one within 1e-9. Normalization is
idempotent and does not repeatedly round fractions already within tolerance.

IDs are sorted, shuffled using the seed, then assigned using rounded train and
validation counts with test taking the remainder. Every partition must be
nonempty, disjoint and together cover the exact sample IDs. There is no fallback
from test to validation or training. The trainer additionally requires at least
20 samples and at least one training observation at every output position.

## Tasks and explicit actions

The bridge advertises methods in `desktop-bridge-1`; discover support before use.

| Method | Effect |
|---|---|
| `materials.prepare` | Freeze dataset/options and selected initialization/active comparison models; create a prepared task without Torch |
| `materials.start` | Explicitly start that prepared task using only its frozen capsule |
| `materials.train` | Compatibility convenience for explicit prepare plus start |
| `materials.jobs.get` | Read one durable receipt |
| `materials.jobs.list` | Read a page, offset 0–1000000, limit 1–100 |
| `materials.jobs.curves` | Read recorded epochs after 0–5000, limit 1–1000 |
| `materials.jobs.cancel` | Persist cancellation intent; cancel a prepared task or signal its trainer |
| `materials.jobs.recover` | Reconcile an abandoned claim/publication receipt, without training or publishing |
| `materials.models.list`, `materials.models.activate`, `materials.predict` | Existing listing, explicit version switch and local prediction |

`prepare` takes an absolute dataset directory, job ID, optional settings and
optional `base_version`. IDs contain 1–64 ASCII letters, digits, underscores or
hyphens. An identical prepare retry returns the original frozen task; changed
settings/path/base require a new ID. To capture changed bytes at the same source
path, also use a new ID. The compatibility `train` retains its former behavior of
returning an existing ID without replaying it. Retrying `start` on an existing
non-prepared task returns its state without retraining.

Task receipts and per-epoch losses live in local service `training.sqlite3`,
not the project database. Input capsules live under `jobs/<id>/inputs`. States
are `prepared`, `running`, `done`, `rejected`, `cancelled`, `failed`, `interrupted`
and `uncertain`. `started_at` is null before start. Public receipts include the
data card, exact capsule SHA, options, split counts, selected model versions,
latest losses, metrics, comparison, bounded evaluation preview and reason.
Internal owner, request and publication-intent fields are not exposed.

Reopening, listing, polling, restoring a desktop draft or reading curves does
not start or recover a trainer. A running receipt survives service loss until
explicit recovery. A process lease plus an in-process guard permits one trainer
per state root. Cancellation is durable and checked between training batches
and again inside the publication operation. Shutdown signals its own trainer.
A cancelled/interrupted/failed task requires a new task ID to train again.

## Comparison and admission

A selected base initializes the candidate's actual weights and normalization.
Its target, grid, ordered inputs and units, activation and requested hidden layers
must be compatible. The baseline is independently frozen from the active model
at preparation, even if initialization uses an older version. A baseline does
not change scratch initialization.

Candidate, base and baseline metrics use the exact same frozen test IDs, observed
points and truth spread. `comparison` has format
`stk.materials-training-comparison/1`, `test_sha256`, `test_samples`, `candidate`,
`base` and `baseline`. Each populated role has the existing test metrics shape.
The evaluation preview contains the first at most three test samples, their
observed curves (including null missing points), actual candidate/base/baseline
predictions and the existing grid descriptor. It is display evidence, not a
replacement for the full frozen split or quantitative evaluation.

Admission requires finite nonnegative candidate normalized RMSE at most 0.25
for P–E or 0.1 for capacity fade, and no worse than the prepare-time baseline
when present. It also requires the current active version and its activation
generation still match preparation. A manual activation, including a switch
away and back, prevents automatic replacement. Rejection preserves metrics and
curves; it does not replace the active model. Explicit rollback remains possible.

Model versions retain their immutable folder identity. New models bind weights
SHA-256, capsule/split provenance and both frozen model roles. Weights are checked
before `torch.load(..., weights_only=True)`. Legacy model/1 folders without a
weights digest remain readable and are reported as `legacy_unverified`; no digest
is invented for them. Model numbers include orphan folders and are not reused.

Publication records an intent before moving a model and replacing the registry.
Recovery recognizes only an exact already-published version receipt and verifies
its metadata, weights and input evidence. It never publishes a pending model or
reactivates a version that a person has since rolled back. Missing/conflicting
published evidence remains `uncertain`; an unpublished stopped attempt becomes
`interrupted` or `cancelled`. Registry readers and writers share a process lease
so an ordinary Windows reader cannot overlap supported registry replacement.

## Interpretation limits

This proves a local software training and comparison chain. A row split does not
establish independence between related specimens, batches or materials. A reused
base or baseline may have seen overlapping samples during earlier training.
Synthetic data and their models remain explicitly labelled; passing this gate
does not validate real material properties. Cooperation formats, MuPRO electric
field scans, external-agent permissions and PET-specific evaluation remain
separate decisions/work.
