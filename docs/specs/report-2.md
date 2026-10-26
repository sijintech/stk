# Generated project reports (`stk.report/2`)

This version adds an explicitly edited generated Markdown/HTML entry to the existing
[report storage and reading operations](report-1.md). `stk.report/1` remains unchanged.
It uses the same ordinary Reports table and one CAS/undo transaction; no database migration
or synthetic Files record/snapshot is introduced. Machine shapes live in
[`desktop-bridge-1.schema.json`](../../suan/contracts/schemas/desktop-bridge-1.schema.json).

## Frozen request input

`project.requests.create` with `prompt_version="stk.report-draft/1"` requires
`report_selection={expected_revision, sources, expected_sources_sha256, snapshot_id, assets}`.
The message must reference a real saved user message and its real primary context.
Preparing creates immutable intent only; sending still requires explicit `project.requests.start`.
Normal request purposes retain their existing wire shape and reject `report_selection`.

`sources` is an ordered list of `{kind,id}` selections using the four kinds in report/1.
Nonempty selections require the exact `review_sources` digest. Run observations can advance
without a project revision change, so preparation compares the reviewed digest before freezing.
The real primary context occupies one of the sixteen total source slots; a duplicate primary
selection must contain the identical context. Reads retain frozen observations and never
recapture later run state.

`snapshot_id` may be null only when `assets` is empty. Otherwise it identifies one existing
snapshot. Each asset selection has `{record_id,path}`; at most 63 may accompany the generated
entry, with original size, hash and MIME verified. The virtual suffix must agree with the
original MIME. No file bytes are sent to a model by this protocol. Both generation evidence
filenames below are reserved, including portable case-folded and file/directory collisions.

The frozen request adds `report_input` to the normal context/message/configuration/purpose input.
It has exactly `{format, project_id, source_revision, sources, snapshot_id, snapshot_sha256, assets}`,
with `format="stk.report-input/1"`. It is at most 256 KiB. Combined full sources (including
the primary context) and asset metadata are at most 192 KiB, leaving room for a 64 KiB body
even when JSON quoting doubles its size, plus bounded provenance and title in a 384 KiB record.
Asset bytes leave 64 KiB free within the 32 MiB report asset budget. Oversize input fails before sending.

Stored input must still match the committed selection's revision, ordered source identities,
reviewed source digest, snapshot and ordered asset mappings, even if outer hashes are recomputed.
These are consistency checks, not a cryptographic authorship boundary against arbitrary database edits.
The prompt identifies captured lifecycle state as such: run status and plan hashes are not
scientific result values, and selected asset metadata does not imply that their bytes were read.

Sending to an external endpoint rechecks every context table and asset file's **current** public
label in one database read transaction. Structure-only labels do not expose table values.
There is no public run label, so any selected run requires a local or internal endpoint.
Existing network, credential and single-send restrictions remain authoritative. Reopen, read,
preview, export and cancellation never generate another response.

## Explicit editing and creation

`project.reports.generation_request({handle,request_id})` returns exactly
`{revision,request,input,response}`. The response is null until the request completes; it then
contains the original saved assistant message. This read neither sends nor recovers a request.
Failed, cancelled, pending, running and uncertain requests cannot become generated reports.

`project.reports.create_generated` takes
`{handle,name,request_id,body,report_id,expected_revision,expected_input_sha256,expected_response_sha256,entry_path?}`.
The caller supplies one stable report UUID and both original hashes. The default entry is `report.md`;
only Markdown/HTML entry suffixes are admitted. `body` must be nonempty UTF-8 at most 64 KiB,
without controls other than tab, CR and LF. Save is explicit and does not call a model.
The completed request, response and exact frozen input are revalidated before one ordinary edit.
The result is `{revision,commands,table_id,record_id}` and emits `project.changed` on success.
Duplicate report UUIDs conflict. A lost reply requires lookup of the original report UUID;
neither an uncertain request nor uncertain report creation is replayed automatically.

The manifest retains the eight report/1 keys and adds `generation`, with `format="stk.report/2"`.
Snapshot identity/hash may both be null only for an entry without extra snapshot assets.
The entry is first in `assets`; its UUID is UUIDv5(request UUID, `stk.report-generated-entry/1`),
explicitly a generated-entry identity rather than a Files-table record. Its size/hash cover the
exact edited UTF-8 body. Extra assets and sources must equal the frozen request selection;
the primary context is first. All asset identities and virtual paths are distinct.

`generation` has exactly twelve keys:

| Keys | Meaning |
|---|---|
| `format` | `stk.report-generation/1` |
| `request_id`, `message_id`, `assistant_message_id` | Original request and saved exchange identities |
| `input_sha256`, `report_input_sha256`, `response_sha256` | Canonical full input, frozen report input and original reply byte digests |
| `input_revision` | Revision of report-input preparation |
| `configuration`, `response_metadata` | Original bounded request configuration and provider receipt metadata; never credentials |
| `edited`, `body` | Server-derived comparison with the original reply and the exact edited entry |

Primary-context revision, input-preparation revision and report-creation revision can differ,
but must be monotonically ordered. Generation provenance must exactly match the original completed
request and response. A changed body requires its corresponding descriptor hash and derived edited
flag. Metadata including title, format and manifest remains at most 384 KiB; collection and project
budgets from report/1 still apply. Reports remain frozen; later project edits or run observations
do not rewrite them. The project must retain its original request journal for provenance validation.

## Reading, previews and export

Existing `get/list/asset/preview/preview_resources/export_file` methods also accept readable report/2.
Reading the generated entry returns the inline body through the same source-bound asset receipt;
extra assets are read from their real frozen objects. Markdown/HTML use the same sanitizer and
explicit native resource-session preparation. Schema acceptance and navigation Ready do not prove
OS rendering, scientific validity or human approval of generated claims.

A source ZIP contains `stk-report.json`, the edited entry, selected assets and two evidence files:

- `stk-generation-input.json`: the exact canonical full frozen request input; SHA equals `input_sha256`.
- `stk-generation-response.txt`: the exact original saved assistant reply bytes; SHA equals `response_sha256`.

The evidence files make original input, reply and subsequent edits independently inspectable.
Export verifies hashes and the current selected report before non-overwriting publication. It neither
calls a model nor updates project revision. This source bundle is not a rendered-page or project importer.
