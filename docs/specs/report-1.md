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
`.html`, `.htm`, `.css`, `.txt`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` and `.pdf`.
Text MIME includes `charset=utf-8`. MIME admission does not validate every image or PDF encoding.
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

`asset`, `preview` and `export_file` require `report_id`, `expected_revision` and
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
