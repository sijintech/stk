# Local desktop literature service — `literature.*`

The Bridge registers the exact 20 methods below with the `literature.` prefix in
`desktop-bridge-1.schema.json`. All are desktop-only, including passive metadata;
they are absent from the Python script catalog and agent operations/tools.
The native Literature editor uses these methods through explicit controls for
libraries, model review, search, citations, pages and original-action history.
Privacy RAG, paid literature and shared sessions remain separate pending work.
These methods do not extend project/report identity.

`LiteratureService(state_dir, python=…, parser_python=…, encoder_python=…)` uses
explicit absolute trusted interpreter configuration. Requests select local asset
folders, never arbitrary executables. The optional compatibility `python` field
must exactly match `encoder_python` before admission. There are no downloads,
external models, endpoint changes, credential configuration or model requests on
refresh/reopen. Local embedding inference happens only on explicit build/search.

The host may construct `Bridge(..., literature_parser_python=…,
literature_encoder_python=…)` with trusted absolute interpreters. Both default to
`sys.executable`; the service worker always uses the Bridge interpreter. This is
a host construction interface, with no new stdio argument, RPC configuration or
user model setting. Missing optional dependencies leave the admitted action
uncertain with a bounded unavailable error (`unavailable`, `encoder_unavailable`
or `parser_unavailable`); nothing installs them automatically. Bridge construction,
`hello`, passive reopen and shutdown never construct a literature worker or
create a corpus. The service itself is constructed on the first literature call.

## Methods

All objects are closed: unknown/missing fields, booleans in integer fields,
nonfinite numbers, invalid UTF-8, deep containers and over-budget requests fail.
Every explicit action requires the caller's canonical lowercase UUID
`operation_id`. A repeated UUID with the exact original action/request returns
the existing admission metadata; another request conflicts. It never dispatches
again. A lost response must be queried under its original UUID.
An exact original admission can still be observed after trusted interpreter
configuration changes; a new UUID must satisfy the current configuration.

| Method | Required fields besides operation_id | Optional fields |
|---|---|---|
| corpora.create | name | — |
| encoder.review | assets | python (must match configured interpreter) |
| encoder.select | review_id, review_sha256, expected_generation | — |
| import.review | corpus_id, source, document_id, title, authorization | — |
| import.commit | review_id, review_sha256 | — |
| import.recover | corpus_id, original_operation_id | — |
| versions.revoke | corpus_id, version_id | — |
| index.start | corpus_id, version_id | — |
| dense.build | corpus_id, expected_generation, encoder_generation | timeout (integer 1–3600 seconds) |
| search | scopes, query, encoder_generation | limit |
| citations.resolve | scopes, citation | — |
| pages.render | scopes, citation | long_edge |

Passive methods have no action UUID except the queried original identity:

| Method | Fields |
|---|---|
| info, corpora.list, encoder.info | empty object |
| corpora.info | corpus_id |
| versions.list | corpus_id; optional offset, limit |
| operations.get | operation_id |
| operations.list | optional offset, limit |
| operations.result | operation_id, expected_request_sha256 |

`info`/`corpora.list` return managed corpus IDs, display names, original database
UUIDs and create-operation UUIDs, encoder generation/configured status and active
job count. These observations do not prove availability or authorize content.
`encoder.info` returns generation and bounded selected manifest/fingerprint/review
identity; it does not load a model or reverify every asset.

`corpora.info` returns the exact closed object `{corpus_id,database_id,generation,
dense_generation,dense_source_generation,dense_encoder_fingerprint}`. The last
three fields are null before the first dense build. Original database UUID,
current corpus generation and retained dense metadata are read in one Library
read transaction, with bounded manifest bytes and verified hash. A stale dense
index still reports its source generation, so an explicit Build can use the
current `generation` as its CAS input after reopen. Damage or replacement fails
closed. This read never parses/hashes PDFs, encodes, downloads, adopts or rebuilds.

Actions return `{operation}`. Its closed fields are `operation_id`, `action`,
`request_sha256`, `state`, `result_sha256`, `error`; state is running, completed or
uncertain. Errors contain only a bounded code/message. `operations.get` returns
null for an unknown identity. List methods are metadata-only. `operations.result`
returns `{operation,result}` only for a completed action and exact request SHA.
Historical completion is distinct from current approval.
The result Schema is a closed union tagged by `operation.action`: each completed
action permits only its exact receipt/review/search/resolve/page result shape.
It cannot accept another action's result or an unrestricted JSON object. The
service additionally checks UTF-8 byte budgets, hashes, cross-field identities,
numeric types, source approval and generation fences; Schema structure alone
does not establish those evidence properties.

The request SHA is ordinary UTF-8 JSON of `{action,params}`, sorted keys, compact
separators, finite numbers, without ASCII escaping. This is not a credential or
an authorization token. The caller must retain original request identity.

## Results and evidence

Corpus creation returns `{corpus_id,database_id}`. The managed ID is `local_` plus
the create UUID's 32 hex digits; database UUID is Library's actual persistent
identity. No name-based rebinding or unknown-library adoption occurs.

Import review freezes the exact source path/SHA/size, document UUID, title,
explicit Library authorization and original corpus UUID/generation. It does not
import or parse. Commit requires that review's exact result SHA and unchanged
corpus identity/generation. Import/index/build/revoke/recover retain Library's
original operation IDs, kind, request SHA and immutable receipt. The service
journal is separate; it never pre-reserves a Library operation.

Encoder review hashes and verifies an exact known asset profile and runtime metadata,
without loading weights. Selection re-verifies that exact review and uses encoder
generation CAS. The known CPU float32 profiles are `e5-small-cpu-f32`
(384 dimensions, masked mean pooling) and `qwen3-0.6b-cpu-f32` (1024 dimensions,
last non-padding token, pinned instruction prefix); both use the explicit
512-token complete-window budget and the constructor-trusted interpreter with
reviewed shared CORE dependencies. Asset manifests select exact known profiles,
never arbitrary model names. Inference identity binds both `dense_worker.py` and
`encoder_profiles.py`. There is no automatic migration to another recipe, runtime
or model. Historical metadata remains readable without current-dispatch
authority. Selection
alone does not build any corpus.

Search uses actual Collection API results with the chosen local scopes, complete
current generations and selected encoder fingerprint. It preserves globally
fused hits, exact citations, rank evidence and source text; evaluation branch
ledgers are omitted from the product cache. This API returns evidence, not a RAG
answer or a claim that retrieval quality passed the frozen evaluation.

Resolve returns exact verified paragraph/window text, parser and character
geometry with the original collection citation. Page render returns only a PNG
(at most 4 MiB), exact image SHA/size/dimensions, source SHA, page metadata,
renderer binary/worker proof, a six-number PDF-to-pixel affine transform and
per-character pixel quads with their geometry SHA. Pixel coordinates start at
the image's top left. Matrix order is `[a,b,c,d,e,f]`:
`x_pixel=a*x_pdf+b*y_pdf+c`, `y_pixel=d*x_pdf+e*y_pdf+f`.
The parent independently checks all page corners against page box/rotation with
a 0.02-pixel tolerance for PDFium's native float transforms, and validates the
complete bounded RGBA PNG stream, source proof and every highlight quad.
No whole PDF, fabricated project/report identity or arbitrary file URL is returned.

Before publishing cached search text, resolved text or PNG, the service verifies
the original frozen corpus UUIDs, retained generation membership, exact source
bytes and every cited version's current approval. Batch verification is local to
one read. Final sequential per-corpus leases check all cited approvals, followed
by a matching monotonic-generation pass to establish an overlapping publication
snapshot. Library's process-wide connection gate prohibits nested DB leases.
Same-service revocation is serialized with result delivery; a later external
revocation invalidates subsequent reads.
Revoke/replacement invalidates subsequent result delivery; it does not erase the
historical completion record. Result reads may verify local evidence but never
parse, encode, import, build, restore or dispatch a worker.

## Persistence, resources and lifecycle

Private state lives below `state_dir/literature`; OS lease lives beside it.
JSON files have a closed `{body,sha256}` envelope, owner-only permissions,
bounded stable reads and atomic writes. Unknown/corrupt existing state fails
closed without reset. No automatic repair, migration, pending-job replay or
silent corpus adoption occurs. Interrupted corpus creation or selection can
leave an uncertain admission; original artifacts must be inspected explicitly.

Limits: eight managed corpora, two admitted owned worker trees, one embedding
build/search task, no unbounded work queue; 4,096 journal entries and 64 MiB
service metadata/results with worst-case result reservation before admission.
Each request is at most 32 KiB, journal/config 128 KiB, result 8 MiB; Library's
separate corpus/source/index quotas still apply. Queries/names/titles are bounded
to 256 UTF-8 bytes; search limit 1–20, list limit 1–50 (versions at most 20), page
long edge 256–2048. Worker build bounds are request timeout plus 10 seconds
(default 610, at most 3610); other action time bounds are
search 130 seconds, other actions 75 seconds. Parse/build/encode have their own
nested bounds. Metadata/cache quota exhaustion requires explicit management;
there is no automatic GC that releases operation identities.

The parent constructs a child environment from an allowlist; product KEY is
empty, MODEL absent, HF offline/telemetry flags explicit. Credentials are neither
read nor passed to children. Fixed private worker protocol is closed and bounded;
third-party stdout/stderr cannot enter the Bridge protocol/log. Socket auditing
is a local offline guard, not an operating-system sandbox.

Shutdown closes admission, kills only owned worker trees, and leaves incomplete
actions uncertain. It does not cancel unrelated Runtime work. Passive reopen
reports old running admissions as uncertain without spawning or rewriting them.
Workspace restoration may later restore bounded query/scope drafts only, never
capabilities, authorization, pending jobs, model authority or automatic actions.

## Native UI and validation

The `literature` editor has its own tab-local View and local text drafts. Its
top-bar and Workspace entries do not require an opened project. Opening, drawing
or restoring it sends no literature RPC; Refresh reads metadata explicitly.
Review approval buttons freeze the displayed operation UUID, result SHA and
generation. Execution callbacks also check the actual Bridge process and active
area; local text commits survive metadata invalidation and Bridge reattachment.
Hiding or moving the tab stops observation and releases page resources without
cancelling background work. Authorization and reviews do not survive detachment.

Workspace restoration saves only bounded query/scope and navigation state.
Import paths, permission evidence, model folders and operation authority remain
local to the live tab and are not exported. The dirty-draft gate protects them
from replacement; explicit Discard clears the form. History reads are separate
from current approval. Its paged result summary omits PNG bytes and character
geometry; the reader separately adopts only a verified resolve/render pair.
Highlights use the same image fit, pan and zoom transform without modifying PNG
bytes. A new render releases its previous texture before dispatch.

Service tests and Bridge contract tests cover different boundaries; a service-only
pass does not establish published dispatch/Schema or desktop UI behavior.
`tests/test_desktop_bridge_literature_contract.py` checks registration, lazy
lifecycle, trusted host configuration, script/headless isolation, closed Schema
counterexamples and a provisioned real-parser/E5 Bridge chain. Real asset cases
must execute with zero skips before claiming that chain passed.
`desktop/tests/app/literature_test.cc` exercises real Bridge import review/commit
with a self-authored byte fixture, passive one-click entry in two fixed layouts,
stale approval/process callbacks, draft preservation and workspace limits.
Image overlay tests check CPU draw commands. These tests do not establish a full
real-encoder search/citation/page UI chain or target-OS rendering; both remain
separate acceptance work recorded in `docs/runtime-validation.md`.
The native editor must preserve
Viewer and hidden drafts, reject stale Bridge/tab/scope responses, release page
textures on revoke/rebind/detach, and record fixed-start click count and resulting
state. Do not reuse ReportDocumentHost by inventing project/report UUIDs.
Corpus import/retrieval authorization is distinct from publication, external
model use or a per-session sharing grant.
