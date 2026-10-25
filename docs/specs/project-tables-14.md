# STK table backend API v1 (implementation contract, 2026-10-15)

All bridge methods below use the current bridge `handle`, never a persisted handle.
Read methods return the observed project `revision`. `expected_revision` is required
for query, paste planning, candidates and resolution; views.list/get also require it.
Wrong revisions produce `conflict`. Reads/plan never edit, execute or import resources.
All mutations are commands through existing `project.apply`; one batch/one undo.

## Field schemas (format 14)

The original types remain text/integer/number/boolean/json. Add date/url/single_select/
multi_select/object. Every snapshot field additionally has `options` (plain JSON).
Default options are `{version:1}`. Select types require
`{version:1,choices:[{id:canonicalUUID,label:string,color:'#RRGGBB'}]}`.
Object options are `{version:1,kinds:['record','file','snapshot_file','analysis','simulation','workflow']}`;
the kinds array is nonempty, unique and may restrict that set.
Select values are choice UUID or an ordered unique array of choice UUIDs. Dates are
strict YYYY-MM-DD strings, URLs are absolute http/https strings. All types allow null;
unset remains absent. Existing set_reference/set_expression definitions remain valid,
with target validation and error diagnostics. Object values use the reference below.

New commands:
* `set_field_schema {op,id,type,unit:null|string,options:object}`
* `put_table_view {op,id,table_id,name,definition:object}` (id explicit UUID; create or replace)
* `delete_table_view {op,id}`
`add_field` gains optional `options`; old calls are unchanged. New types/options need
format14. Schema changes cannot silently discard used choices or coerce stored values.

## View definition

`{version:1,kind:'grid'|'board'|'gallery',columns:[{field_id,width:160,hidden:false}],
 filters:{op:'and',conditions:[]},sorts:[{field_id,direction:'asc'|'desc',nulls:'last'|'first'}],
 group_field_id:null|UUID,row_height:32,frozen_columns:0}`.
All keys except version/kind are optional and normalized. Width is logical pixels.
Omitted columns default to current field order. When group_field_id is set, query
orders groups ascending with null/unset/error last before pagination; explicit sorts
apply within each group. Typed group values use the same comparator as sorts. The
returned definition.sorts remains the user configuration. No records are copied or
modified by grouping.
Filter groups use and/or + conditions. Leaves use field_id/op/value; supported ops:
eq,ne,contains,gt,gte,lt,lte,is_empty,is_not_empty,is_null,is_unset,is_error.
The last five have no value. No regex, arbitrary SQL or code.

## Read operations

`project.table.views.list {handle,table_id,expected_revision}`
 -> `{revision,views:[{id,table_id,name,definition}]}`.
`project.table.views.get {handle,id,expected_revision}`
 -> `{revision,view:{id,table_id,name,definition}}`.

`project.table.query {handle,table_id,expected_revision,view_id?:UUID,
 definition?:object,offset?:0,limit?:200}` (view_id and definition are exclusive)
 -> `{revision,table_id,view_id:null|UUID,definition,fields:[field descriptors],
 total,record_ids:[UUID],records:[{id,values,definitions?,evaluations?}],
 next_offset:null|integer,issues:[string]}`.
limit 1..500; offset nonnegative; no cursor. records/record_ids are the requested
typed-filtered/sorted page. Unset cells remain absent, explicit null remains null,
formula errors remain in evaluations. Fields use view column order (including hidden
fields; UI checks definition.columns.hidden). No rendered strings replace values.

`project.table.paste.plan {handle,table_id,expected_revision,record_ids:[UUID],
 field_ids:[UUID],text:string,delimiter?:'\t',append_rows?:false,fit_targets?:false}`
 -> `{base_revision,table_id,rows,columns,command_count,record_ids:[UUID],
 field_ids:[UUID],commands:[project commands]}`.
TSV/CSV uses strict CSV quoting, exact rectangular shape, complete untruncated values.
record_ids are explicitly ordered existing target rows; append_rows=true permits extra
input rows and generates add_record UUIDs. No new fields or inferred formulas.
Text is raw; blank non-text is null; typed values otherwise use JSON literals, except
date/url/single_select may be plain strings (single_select accepts exact IDs or unique labels).
Multi_select requires a JSON array of exact IDs or unique labels.
Object clipboard cells must be explicit reference JSON. All validation completes before
returning; >1000 total commands is rejected, never split into partial commits.
With explicit fit_targets=true, supplied ordered IDs are the remaining rows/columns from
the anchor. The strict server TSV parser trims those lists to the actual input rectangle;
more columns than supplied rejects, excess rows still require append_rows=true. Defaults
retain the exact-rectangle contract. Quoted embedded newlines count as one CSV field.

## Object references (format14 object fields)

`{version:1,project_id:UUID,kind:'record'|'file'|'snapshot_file'|'analysis'|'simulation'|'workflow',
 id:UUID,table_id?:UUID,record_id?:UUID,path?:relativePOSIX,source_sha256?:64hex}`.
record requires table_id; snapshot_file requires path and source_sha256. Other kinds
reject table_id/path. source_sha256 may pin an observed descriptor on other kinds;
changed observations then return stale. Same-project only; cross-project refs reject.
File means an existing FileIndex record (live observation, not frozen content).
Snapshot_file names a frozen snapshot + manifest path/hash. Other IDs resolve through
existing stores, not a parallel object DB. Metadata discovery and resolution do not
read contents or execute processes, models or graphs.

`project.table.objects.list_candidates {handle,kind,expected_revision,table_id?:UUID,
 offset?:0,limit?:100}` (limit1..200)
 -> `{revision,items:[{reference,label,state,summary}],total,next_offset:null|integer}`.
`project.table.objects.resolve {handle,reference,expected_revision}`
 -> `{revision,reference,state:'available'|'missing'|'stale',label,summary,reason:null|string}`.
Unknown/mismatched sources cannot resolve as available. Missing/stale references remain
diagnosable after target removal. Candidates include complete references ready for set_cell.

### Explicit local attachment preview (additive, 2026-10-25)

`project.table.objects.preview {handle,reference,expected_revision}`
 -> `{version:1,revision,reference,label,kind:'text'|'png',content_sha256:64hex,
 size:integer,data:string,truncated:boolean,render?:object}`.
This separate read accepts only an available same-project `file` or `snapshot_file`.
The Python facade is `project.table.objects_preview(reference, expected_revision=...)`.
It does not refresh the file index, change project revision/history, invoke a model,
execute code, download resources or open/replace Viewer. Agent tools do not expose it.

The file must be regular and no larger than 1 MiB. Reading pins one descriptor and
checks its identity, size and timestamps before/after; directory and file replacement
during the read rejects. Indexed paths use the existing FileIndex/workspace relocation
rules and return current local bytes, which may differ from the last indexed observation.
Frozen files are read from the content store and must match the manifest size and SHA-256.
Missing/stale references, unsupported types, read races and corrupt frozen bytes fail.

For a normal PNG preview, `data` contains base64 of the complete original file. Header dimensions must be
positive, at most 4096 per axis and at most 4194304 pixels. The bridge checks the header;
the native client also validates the byte checksum and decodes PNG with these limits,
rejecting corrupt/unsupported encoding before display. `truncated` is always false.

JPEG (`.jpg`/`.jpeg`), WebP, GIF, BMP and TIFF (`.tif`/`.tiff`) are also accepted.
These formats require Pillow from the `visualization` extra; missing support is an explicit
error, without affecting the original PNG/text path. Decoding accepts only the format matching
the extension, with the same source byte and dimension limits. The first frame is oriented
using EXIF and converted to RGBA PNG, fitted within 2048 pixels per axis and reduced further
if needed to keep encoded pixels within 1 MiB. Derived pixels carry no source EXIF/ICC/text metadata.
`size` and `content_sha256` still identify the complete original file, not the derived PNG.
The additional `render` contains `sha256`, `size`, `format`, source `width`/`height`,
`display_width`/`display_height`, `frames`, `frame:0` and `thumbnail:false`.
Clients verify the derived byte count/checksum and decoded dimensions separately; multi-frame
images are labelled as first-frame previews, not animation playback or complete TIFF page viewing.

`project.table.objects.thumbnail {handle,reference,expected_revision}` returns the same envelope,
with required `kind:'png'` and `render.thumbnail:true`, fitted within 256 pixels per axis.
It accepts only the image formats above, including PNG, and always requires the decoder.
Capability discovery is required for this additive method. Python exposes
`project.table.objects_thumbnail(reference, expected_revision=...)`.
Cards and boards offer an explicit load action for each visible file-object field; merely
opening a view does not read attachments. Each editor keeps at most 32 thumbnails and releases
their textures when its source/revision/view changes or the editor closes. Refreshing an image
discards its old preview first; a failed read cannot retain old pixels as a new result.
This temporary cache is neither a project resource nor part of workspace persistence.

Text suffixes: `.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`,
`.toml`, `.xml`, `.html`, `.htm`, `.tex`, `.rst`, `.py`, `.log` (case-insensitive).
The entire bounded file must be strict UTF-8 without C0 controls other than tab/CR/LF.
`data` shows at most the first 64 KiB, cut at a UTF-8 boundary; `truncated` reports omitted
bytes. `size` and `content_sha256` describe the complete file, including when truncated.
Markup and code are literal text. This operation does not implement embedded HTML,
Markdown rendering, PDF or video preview. The desktop keeps one temporary preview per
table editor; changing its source or closing details discards it. Workspace restore
does not persist or automatically reload attachment content.

## Persistence and compatibility

`project.table.csv.preview {handle,source,expected_revision,delimiter?:',',limit?:20}`
 -> `{revision,source_sha256,columns:[{name,type:'text',unit:null}],rows:[[string]],
 total_rows,truncated,command_count,can_import}`. limit1..100; explicit bounded UTF8
file read (8MiB); no inference/execution. Existing project.csv.import gains optional
`expected_sha256`: mismatch rejects before any edit; import uses precisely captured bytes.
Existing project.csv.export gains mutually exclusive optional `definition` or `view_id`:
export the matching sorted records and visible columns in view order, up to10000 rows.
With neither option, export keeps the original whole-table behavior. Publication remains atomic/create-only.

Format14 adds field_options(field_id PRIMARY KEY FK fields,definition JSON TEXT) and
table_views(id PRIMARY KEY,table_id FK tables,name,definition JSON TEXT) in the same DB.
No fields-column change: preserve old journal row shapes. Missing options on old five
types mean version1 defaults. Upgrade is explicit, revision-CAS checked, prebackup first.
New relation snapshots are captured/restored by existing edit_journal, including delete
cascades. View save/delete, field schema and pasted cells commit or roll back together.
Upgrade itself is not an undoable edit: undo after upgrade restores prior edits without
downgrading the format. Deleting a field preserves saved views that mention its UUID;
query reports issues and zero records until the view is explicitly repaired. Deleting
the table removes its saved views in the same undoable batch.

Snapshot-file identity clarification: candidates now include optional `record_id` in
the reference, binding the exact manifest source entry even when two files share
the same SHA/blob path. New candidates always include it. Legacy references without
record_id remain valid when exactly one manifest entry matches; ambiguous ones
resolve as stale and require an explicit selection. The schema accepts record_id
only semantically for snapshot_file; wrong source/path/SHA never selects another file.

Record candidate labels use the table name plus the first nonempty literal scalar
from ordered fields, preferring text fields; absent literals fall back to the UUID
prefix. Table prefix is at most 64 characters and value preview at most 128,
controls/newlines normalized for display. Formulas/references are not evaluated or
read from evaluation caches. Reference IDs and source SHA semantics are unchanged.
