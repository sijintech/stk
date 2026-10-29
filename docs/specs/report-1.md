# Frozen project reports (`stk.report/1`)

This additive contract describes saved report selections, not a workflow or an executable page.
The machine shapes are `$defs.projectReportManifest`, `projectReportSource`, `projectReportAsset`
and the `project.reports.*` methods in
[`desktop-bridge-1.schema.json`](../../suan/contracts/schemas/desktop-bridge-1.schema.json).
The storage validator also enforces source membership, byte hashes, portable paths and aggregate budgets.
The [Chinese guide](../project-reports.md) describes the desktop and scripting entry points.

## Storage and identity

Reports are ordinary project records with `name` (text), `format` (text) and `manifest` (JSON).
The table UUID is UUIDv5(NAMESPACE_URL, `urn:stk:project:reports:1`); field UUIDs append
`:name`, `:format` and `:manifest` respectively. Creating a report uses the ordinary CAS and undo history.
No database format migration is introduced; selecting snapshot assets requires the existing snapshot capability.
There is no update or overwrite operation in this API. A new report UUID creates a new frozen selection.

The manifest has exactly these fields:

| Field | Meaning |
|---|---|
| `format` | `stk.report/1` |
| `project_id` | Owning project UUID |
| `snapshot_id`, `snapshot_sha256` | One existing file snapshot and its verified manifest digest |
| `source_revision` | Project revision at report capture; at least the snapshot revision |
| `entry_path` | Exactly one selected asset's virtual path |
| `assets` | Ordered `{record_id, path, mime, sha256, size}` entries |
| `sources` | Frozen context or run observations, described below |

`source_sha256` in report responses is the SHA-256 of the manifest serialized with
Python `json.dumps(ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))`, UTF-8 encoded.
It identifies the selection and provenance; it is independent of a report's display name and record UUID.
Each asset's `sha256` identifies its original bytes. Rendered preview bytes have a third, separate digest.
Hashes provide consistency checks; ordinary table access is not a cryptographic authorship boundary.

Asset records must be distinct members of that snapshot, with matching size and hash.
Source and virtual suffixes must map to the same admitted MIME. Supported suffixes are `.md`, `.markdown`,
`.html`, `.htm`, `.css`, `.txt`, `.tex`, `.log`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.pdf` and `.mp4`.
Text MIME includes `charset=utf-8`. MIME admission does not validate every image or PDF encoding.
The 2026-10-27 additive extension admits `.tex` and `.log` as `text/plain; charset=utf-8`
for exact source and compilation-log evidence. They remain inert UTF-8 assets: creating,
reading, reopening or exporting a report never starts a compiler or interprets log contents.
The 2026-10-29 additive extension admits `.mp4` as `video/mp4`. The original bytes and provenance
remain frozen report assets. Container admission does not certify a codec or system decoder;
unsupported playback must retain the source and export path. Preparing or reopening never plays media.
Paths are portable relative POSIX names, at most 1024 UTF-8 bytes: no absolute paths, `.`/`..`, backslashes,
controls, Windows reserved names, trailing dot/space or NFC/case-folded file/directory collisions.
`stk-report.json` is reserved at the root. Source paths are never used as arbitrary host filesystem paths.

## Frozen sources

Creation takes optional selections `{kind, id}`. Every resulting source has
`kind`, `id`, `project_id` and `source_revision`. Supported kinds are:

- `context`: additionally `context` and `context_sha256`. The complete context descriptor is frozen,
  including selection, content, omission information and diagnostics. The outer hash covers that descriptor;
  `context.content.sha256` covers its content value and has a different scope.
- `simulation_run`, `analysis_run`, `workflow_run`: additionally `plan_sha256` and `captured_status`.
  The selected run's original status shape is preserved, including failure and incomplete observations.
  A simulation observation includes its observation ID and time. An analysis observation retains its lifecycle;
  a workflow observation retains `status`, `complete`, `counts` and `stop_error`.

Sources are read in one SQLite read transaction. Run observations may advance without changing the ordinary
project revision; the saved value describes capture time, not the latest state. A plan digest is not an output
byte digest. Capturing a source never starts or refreshes a remote run. No scientific validity is inferred.

## Operations and failures

Discover all optional methods through `hello.methods`. `project.reports.create` accepts
`{handle, report_id, name, snapshot_id, entry_record_id, assets, expected_revision, sources?}`;
asset selections contain only `record_id` and `path`. It verifies every selected asset before one CAS write.
The result is `{revision, commands, table_id, record_id}`, followed by `project.changed` only on success.
Duplicate report UUIDs conflict. An uncertain write is not automatically replayed.

`get` returns `{revision, table_id, report}`; `list` returns
`{revision, table_id, offset, total, reports}` with summary records and no manifest.
Each summary has `{id, name, format, state, error, source_sha256}`; `get` adds `manifest`.
`state` is `readable` or `invalid`. Invalid records are isolated rather than aborting an entire list.
These are metadata reads: readability does not prove that frozen byte objects still exist.

`asset`, `preview`, `preview_resources` and `export_file` require `report_id`, `expected_revision` and
`expected_source_sha256` in addition to the current open handle. `asset` additionally takes `path`;
`export_file` takes an absolute `destination`. They recheck the selected revision and manifest after I/O.
Closed handles, different projects, stale revisions and different manifest digests are rejected.
Missing assets do not fall back to working files. None of these operations starts execution or calls a model.

`asset` returns the complete base64 `data`, `size`, `content_sha256`, `path`, `mime`,
`project_id`, `report_id` and `source_sha256`. `preview` additionally includes `revision`, fresh `session_id`,
`renderer`, `source_mime`, `source_content_sha256` and `source_size`.
Markdown/HTML preview uses `stk.report-renderer/1`; other admitted MIME uses `identity`.
The preview is derived data, creates no browser, and must not be confused with original source bytes.
The host binds and invalidates its own resource session; a UUID is not an authorization token.

`preview_resources` is an additive, optional two-stage native resource preparation method. It accepts the
same selection arguments as `preview` and returns exactly `{preview, resources, total_size}`. `preview`
has the existing preview result shape, with a fresh session UUID, a Markdown/HTML source entry and
sanitized HTML display bytes. The media extension below preserves existing no-media and legacy `preview`
behavior. `resources` contains only non-entry PNG/JPEG/GIF/WebP descriptors copied
from the frozen manifest, in manifest order, each exactly `{record_id, path, mime, sha256, size}`.
Secondary HTML/Markdown, CSS, plain text and PDF are excluded from both the resource list and generated
URL mappings. Image CSP sources identify the exact admitted raster paths under the session/project/report/
manifest-digest URL prefix; relative references retain the entry's virtual directory. Existing `preview`
behavior, including identity previews for other admitted MIME, is unchanged.

This preparation reads and verifies the entry only. Resource descriptors do not prove that image bytes
are available, match their digests, or decode as images. The host must call `asset` explicitly for each
listed resource using the same open handle, expected revision and manifest digest; it must verify returned
identity, path, MIME, size and checksum against the frozen descriptor before creating one complete native
resource session. It must not add raw secondary documents through `asset`. A project/handle/bridge-session
change, stale selection, failed resource read or close invalidates the pending preparation and old session.
The native session must close on the host's lifecycle boundary; no server-side persistent session is created.

`total_size` is the actual rendered entry byte count plus the declared original raster byte counts, capped
at 32 MiB. Source and display bytes are budgeted separately: each rendered output is at most 4 MiB and
Markdown/HTML input is at most 1 MiB; at most 63 resource descriptors accompany the one entry. No image
body is embedded in this response. Separate, bounded `asset` responses avoid placing the 32 MiB display
collection into one bridge line. Metadata and actual bytes still need final host verification before display.

### Frozen MP4 resource preparation

For `preview_resources`, a Markdown/HTML entry may additionally reference explicitly selected MP4 assets.
Those resource descriptors follow the same manifest order, complete-byte verification, 4 MiB per-asset,
32 MiB collection and 63-descriptor limits as images. A media-capable rendered entry uses
`stk.report-renderer/2`; without MP4 resources it continues to use `/1`. The new response includes
`preview.source_path`, exactly the original manifest entry. Legacy `/1` responses without that additive
field remain readable. No secondary documents, remote media URLs, arbitrary filesystem paths or guessed
assets are admitted.

An MP4 can itself be the report entry. Its `source_path`, `source_mime`, `source_size` and
`source_content_sha256` describe that original frozen MP4. Its display `path` is the distinct virtual name
`_stk-preview/{session_id}/player.html`; `mime` is HTML, `renderer` is `/2`, and display hash/size cover
the generated player. `resources` contains exactly the original MP4 descriptor, even if the report stores
other unreferenced assets. Its relative URL is resolved from the player's virtual directory. The player
uses only standard-library generation; it does not require Markdown/nh3 or start another program.

The renderer accepts media references only through a separate typed MP4 map. Video controls are always
present, preload is `none`, and inline playback is allowed. Autoplay, looping, event handlers and arbitrary
page script remain disabled. Both document CSP and native resource policy restrict `media-src` to the
exact listed MP4 URLs under this session/project/report/manifest identity. A video URL cannot become a
top-level navigation. Native system controls provide explicit play and seeking; returning to a hidden
preview never resumes playback. The host pauses media before hiding or closes and revokes the view if
pause fails. Changing project, report, source version, bridge session or owning area revokes the session.
These lifecycle rules do not prove that a particular system codec has decoded a frame.

Native resource reads accept only GET/HEAD. GET supports one bounded byte range (`start-end`, `start-`
or `-suffix`), returns 206 with generated `Content-Range` and correct length, and clamps an end beyond the
entity. Malformed, multipart, overflowing and unsatisfiable ranges return 416 with `bytes */N`; HEAD
ignores Range and returns the full entity length without a body. Closed sessions return 410 before
method/range handling. Range responses slice already verified immutable bytes, not live files or network
sources. Codec, actual play/seek, native focus and OS capture acceptance remain separate platform evidence.

The renderer removes active content, arbitrary styles and external URLs, and admits only selected relative
asset references. It produces a full UTF-8 HTML document with a restrictive CSP and fixed stylesheet hash.
Page policy does not prove that an embedded browser makes no background network requests.
The desktop source/PNG reader and the optional native-browser prototype have separate acceptance evidence.

## Export and budgets

Export creates a new ZIP containing original assets at their virtual paths and a root `stk-report.json`:
`{format, project_id, report_id, name, source_sha256, manifest}`. It verifies all bytes before publication,
uses a same-directory private temporary file, and publishes without replacing an existing target.
The receipt is `{project_id, report_id, source_sha256, path, sha256, size}` for the entire ZIP.
This is a source bundle, not an automatically self-contained rendered HTML page or project importer.
Export does not change project revision and is not undone by project undo.

One report admits 1–64 assets, at most 4 MiB each and 32 MiB total, and at most 16 distinct sources.
Metadata including name, format and manifest is at most 384 KiB; the managed collection admits 64 records
and 4 MiB. Provenance reads have a combined 32 MiB budget and a 100,000-entry limit per selected run log.
Rendering admits at most 1 MiB input and 4 MiB output. Lists have a maximum page size of 100.
Limits fail explicitly; source evidence is not silently truncated. Existing snapshot limits still apply.

Keeping only SQLite is not a full report backup: the selected `.stk/objects` byte objects are also needed.
The existing [workspace contract](workspace-1.md) transports that project resource closure without executing it.

## Explicit source review and optional source CAS

`review_sources(sources, expected_revision=...)` is read-only and returns exactly
`{project_id, revision, sources, sources_sha256}`. It accepts the same ordered, distinct
`{kind, id}` selections as create (at most 16) and captures complete typed provenance in one
SQLite read transaction at the requested project revision. No source asset, live file, run
execution, recovery, remote refresh, plugin or model is invoked. The entire canonical result
is limited to 384 KiB; larger provenance is rejected, never truncated. Full workflow plans
remain internal to the bounded storage read and are not serialized into the bridge response.

`sources_sha256` is SHA-256 of the ordered `sources` array serialized as UTF-8 JSON with
`ensure_ascii=False`, sorted object keys, compact separators and no nonfinite numbers. It is
separate from the complete report manifest digest and from all plan and asset byte digests.

Create accepts optional `expected_sources_sha256`. When present, it compares this digest to
the **same** captured provenance array that enters the new manifest, before asset reads or
any write. Mismatch returns revision conflict and changes no record/history/revision. Run
observations can advance without changing project revision, so revision alone does not bind
a review. The caller must explicitly review again and submit a new attempt; it must never
weaken original-report-UUID and complete-manifest checks after an uncertain write. Omission
preserves the existing capture-at-create behavior. A later observation does not change the
frozen array already accepted by this comparison.

The desktop creation draft v2 stores only selected source kind/UUID pairs before submission;
reviewed payloads and session/handle/revision gates are transient. Pending writes retain the
complete manifest and digest for exact receipt lookup. Its local workspace budget is 512 KiB
to accommodate the existing 384 KiB report metadata limit; v1 source-free drafts still load.
Restoration and scope/revision changes never automatically read or re-review sources.
