# Table exchange v1 — CSV, XLSX and typed JSON

Implementation contract, 2026-10-15. Implemented in `suan/project/table_io.py` with the
existing CSV implementation delegated to `suan/project/csv_io.py`. Native interaction
and final cross-platform validation are recorded separately in
[runtime validation](../runtime-validation.md); this contract does not assert unrun tests passed.

This contract exchanges **evaluated table values**. It is not a project backup, a
workspace backup, a formula serialization or an object-copy protocol. The existing
[format-14 table contract](project-tables-14.md) defines field and view semantics.
Portable desktop state uses the separate `.stkworkspace` container.

## APIs and scope

Standalone: `ProjectStore(directory).table_io`. Desktop Python: `stk.project.table_io`.
All methods require `expected_revision`; bridge methods additionally require the current
opened `handle`. A handle is never serialized in a table file.

Bridge methods:

```text
project.table.io.preview {
  handle, source, format:'csv'|'xlsx'|'json', expected_revision,
  delimiter?:',', sheet?:string, limit?:20
}

project.table.io.import {
  handle, source, format, name, expected_revision,
  types?:{columnName:type}, units?:{columnName:unit},
  delimiter?:',', sheet?:string, expected_sha256?:hexSHA256
}

project.table.io.export {
  handle, table_id, destination, format, expected_revision,
  definition?:tableView, view_id?:UUID, delimiter?:','
}
```

`delimiter` is comma or tab and controls CSV only. `sheet` is valid only for XLSX;
omitting it selects the first sheet. The standalone API also accepts `sheet=None`;
the strict bridge request omits that key rather than sending null. `definition` and `view_id` are exclusive.
Explicit `format` determines interpretation; file suffixes do not select CSV delimiters.
Standalone method names are `preview(source, ...)`, `import_file(source, ...)` and
`export_file(table_id, destination, ...)`, with the same keyword parameters excluding
`handle`.

Preview returns:

```text
{
  revision, format, source_sha256,
  columns:[{name,type,unit,options?}], rows:[[value]],
  total_rows, truncated, command_count, can_import,
  sheets:[{name}], sheet:null|string,
  schema_present:boolean, table_name:null|string, warnings:[string]
}
```

`limit` is 1..100. Preview reads and validates a bounded complete file, then returns
up to `limit` rows. It never creates a table, applies commands or executes external
content. CSV/XLSX columns initially have `type:'text',unit:null`; rows contain strings.
JSON carries typed columns/options and typed values. JSON preview may show null for
both an absent cell and explicit null; actual import uses original key presence.
`schema_present` is true only for JSON. `sheets` is empty outside XLSX.

`can_import` describes default-schema batch feasibility, not a promise that later type
mapping or project state is valid. For XLSX/JSON it includes the 1 MiB command budget
and a conservative 1024-byte reserve for the chosen table name. Import repeats all
checks against the actual mapping, SHA and revision.

Import creates new table/field/record UUIDs and returns:

```text
{revision,format,table_id,field_ids:[UUID],record_ids:[UUID],
 rows,columns,source_sha256,sheet?:null|string}
```

`expected_sha256`, when supplied, must match the actual file bytes before edits.
The native UI always sends the preview SHA. Import applies one existing project edit
batch; validation, revision or size failure creates no partial table. One undo removes
that batch; redo restores its generated identities. File selection does not authorize
an automatic import or a model/Runtime request.

Export returns:

```text
{revision,format,table_id,path,rows,columns,size,sha256,warnings?:[string]}
```

With no view, export uses the complete table's stored order. A specified view exports
its matching sorted/grouped records and visible fields in view order, across query
pages. Current-page text search is not a backend view filter. Unresolved views and
formula errors in selected output cells are rejected. Values correspond to one
consistent revision. Export does not modify the project revision.

Publication uses a same-directory temporary file and create-only hard-link publication;
existing files or symlinks are never replaced. Target directories must already exist.
Failure cleans up the temporary file. A published external file is outside project undo.

## CSV and XLSX values

CSV accepts UTF-8 with optional BOM, strict CSV quoting and unique nonempty headers.
CSV export writes BOM and CRLF. No type inference occurs: `001`, `true` and `=1+1`
remain text unless a different column type is explicitly declared. Non-text empty
or whitespace-only cells become null; text retains its original string. Non-text
numeric/boolean/JSON values use finite JSON literal syntax; date and URL use the
format-14 string validators. Only numeric fields may declare units.

The native CSV/XLSX mapper exposes text/integer/number/boolean/json/date/url. It does
not create select choices or object-kind configurations. JSON is the schema-bearing
exchange format for those types. Existing format 13 supports the original five types;
new types require an explicit, backed-up upgrade to 14. Import never upgrades implicitly.

XLSX import reads a selected worksheet's first row as headers. Sparse trailing cells
are blank; rows must fit their named columns. Numeric, boolean and date/time cells
first become explicit strings and then use the declared column converter. Import
rejects formula and Excel-error cells in the selected worksheet instead of using
cached formula results. The parser never calculates formulas.

XLSX export creates one worksheet named `Table` with the header frozen. It writes
successful project formula/reference results as values. It does not retain workbook
styles, charts, named views, project definitions or STK type declarations. JSON,
multi-select and object values become JSON text in Excel. Integers with more than
15 decimal digits are written as strings to preserve int64; explicitly mapping such
a column to integer on reimport recovers its exact value. A floating-point value is
also written as its complete JSON number text when parsing its 15-significant-digit
representation would change it, when it is subnormal, or when it is negative zero.
An explicit `number` mapping on import restores the original float, including the
sign of zero. Ordinary values such as `301.25` remain numeric cells. These rules
protect against Excel's [15-digit precision limit](https://support.microsoft.com/en-us/excel/change-formula-recalculation-iteration-or-precision-in-excel)
and streaming-writer rounding; JSON export retains the original number representation.
Already rounded external numbers cannot be repaired. Strings beginning with
formula-like characters are explicit Excel strings, including `=`, `+`, `-` and `@`.

CSV text is not evaluated by STK. External spreadsheet software may interpret a CSV
string according to its own import settings; this contract does not control it.

## Typed JSON file

The complete top-level shape is:

```json
{
  "format": "stk.table",
  "version": 1,
  "mode": "evaluated_values",
  "source": {
    "project_id": "11111111-1111-4111-8111-111111111111",
    "table_id": "22222222-2222-4222-8222-222222222222",
    "revision": 7
  },
  "name": "Synthetic observations",
  "fields": [{
    "id": "33333333-3333-4333-8333-333333333333",
    "name": "Temperature", "type": "number", "unit": "K",
    "options": {"version": 1}
  }],
  "records": [{
    "id": "44444444-4444-4444-8444-444444444444",
    "values": {"33333333-3333-4333-8333-333333333333": null}
  }]
}
```

Only the shown top-level keys are accepted. `source` has exactly project_id/table_id/
revision. Each field has exactly id/name/type/unit/options; each record has exactly
id/values. UUIDs are validated, field IDs and record IDs must be unique, and values
may name only declared field IDs. Field names are nonempty and unique. Records may
be empty; fields must number 1..64.

All ten format-14 types, units and options retain their normal validators. JSON import
accepts no nonempty `types` or `units` override. A missing field key in `values` is unset;
a present null is explicit null. Choice UUIDs/options and object values are retained.
Original table, field and record UUIDs are provenance only and are replaced on import.
Formula/reference definitions, named views, history and external file bytes are absent.

A non-null object value may be imported only into the original source project. It keeps
its original target identity; the importer does not copy an object or redirect a record
reference to the newly imported row. Missing/stale targets remain governed by the normal
object-resolution contract. Import itself does not open, execute or resolve their content.

JSON requires finite UTF-8, depth <=64 and unique object keys. Integers are checked as
int64 and remain exact; NaN/Infinity and invalid schemas reject the whole import.

## Resource and parser limits

| Constraint | Implemented bound |
| --- | --- |
| Source/export file | 8 MiB |
| Columns | 1..64 |
| Preview/export data rows | <=10000 |
| Preview sample | 1..100; native UI asks for 20 |
| Import edits | <=1000 create-table/field/record/cell commands |
| XLSX/JSON serialized import commands | <=1 MiB; CSV retains its existing batch rule |
| XLSX expanded ZIP members | <=32 MiB total; <=2048 members |
| XLSX sheets | 1..256 |
| XLSX string | <=32767 characters; prohibited XML controls reject |
| JSON nesting | <=64 |

CSV/XLSX with `C` columns consumes `1+C+R*(1+C)` commands, so its import row limit
is `floor((999-C)/(C+1))`, often much lower than the preview/export row limit. JSON
can omit unset cells and consumes commands only for present values. CSV fields also
retain the Python CSV parser's default field-length limit.

XLSX preflight rejects encrypted ZIP members, duplicate names, macros/macro-enabled
content, external workbook links and any external XML relationship. All XML/.rels
members pass defusedxml with DTD, entities and external access forbidden before
openpyxl opens the archive. Worksheet addresses/dimensions are bounded before iteration.
The selected sheet cannot be a chart sheet. Legacy `.xls`/`.xlsb` is unsupported.

The implementation uses `read_only=True`, `data_only=False`, `keep_vba=False` and
`keep_links=False`; their meaning is described by the
[official openpyxl reader](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/reader/excel.html).
The [openpyxl PyPI Security section](https://pypi.org/project/openpyxl/#security)
recommends defusedxml for XML attacks. These upstream references motivate parser
choices; STK's stricter rejection rules and limits above are its own contract.
