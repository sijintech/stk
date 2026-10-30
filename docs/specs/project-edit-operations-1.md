# Explicit project edit operations, version 1

This additive storage and local-bridge contract provides a durable success receipt
for a caller-supplied project edit identity. It is a foundation for a future peer
endpoint; it does not implement a network server, pairing, remote authorization or
cross-platform connectivity. Existing `project.apply` is unchanged.

## Storage API and identity

```python
result = store.edit_operations.apply_once(
    commands,
    operation_id=operation_id,
    expected_revision=base_revision,
    scope="local",
)
receipt = store.edit_operations.get(operation_id, scope="local")
```

`operation_id` is an explicitly supplied canonical, lowercase, hyphenated UUID.
The API never generates or silently replaces it. A caller retains the same ID and
original request when observing a lost response. `scope` defaults to `local` and
is 1–256 printable ASCII bytes without whitespace (`U+0021`–`U+007E`).

The identity is the selected project, scope and operation ID. A trusted adapter
supplies the scope; a future authenticated peer adapter must bind stable owner and
caller identities, not accept an asserted scope from its network request body.
The scope must survive reconnects and process restarts, so it cannot be a transient
session ID. Reading an old success is not authorization to access or edit a
project: the adapter must still check the current project grant and caller.

The additive local bridge methods are:

| Method | Parameters | Result |
|---|---|---|
| `project.edit_operations.apply_once` | `{handle, operation_id, expected_revision, commands}` | `{receipt, replayed}` |
| `project.edit_operations.get` | `{handle, operation_id}` | `{receipt}` |

The local bridge fixes the scope to `local`; it does not accept a `scope` parameter.
The script facade is `p.edit_operations.apply_once(...)` and
`p.edit_operations.get(operation_id)`, with the latter returning the receipt
directly. Initial successful edits emit `project.changed` once; receipt replays
and lookups do not emit it. Capability discovery is required before using these
methods. A missing record maps to `not_found`, a different request to `conflict`,
and an old project without explicit upgrade to `unsupported`.

The exact original request is:

```json
{
  "project_id": "canonical-project-uuid",
  "scope": "local",
  "operation_id": "canonical-operation-uuid",
  "expected_revision": 0,
  "commands": [{"op": "create_table", "name": "Parameters"}]
}
```

The request is detached from caller-owned objects, bounded and hashed **before**
the store generates object UUIDs or normalizes command options. The server computes
the request digest; a caller-provided digest is not a substitute for checking the
complete request. Object-key order is immaterial, while command order, original
revision, integer/float/boolean types, negative zero, null and omitted fields retain
their JSON meanings. No Unicode or unit normalization is performed.

## Success receipt

`apply_once` returns exactly `{receipt, replayed}`. `get` returns the receipt,
without executing an edit, changing a revision, emitting a project change or
upgrading a project. A missing identity raises `OperationNotFound`.

The receipt has exactly these fields:

| Field | Meaning |
|---|---|
| `format` | `stk.project-edit-receipt/1` |
| `project_id` | The selected project's stable UUID |
| `scope`, `operation_id` | Original stable operation identity |
| `request_sha256` | SHA-256 of the complete original request |
| `base_revision` | The original `expected_revision` |
| `applied_revision` | The committed revision, exactly `base_revision + 1` |
| `commands` | Actual applied commands, including generated object UUIDs and normalized options |
| `created_at` | Original timezone-aware UTC creation time |
| `sha256` | SHA-256 of the canonical receipt with only this field omitted |

Canonical JSON uses sorted keys, compact separators, UTF-8, `ensure_ascii=False`
and `allow_nan=False`. Arrays preserve order. Stored requests and receipts use
this exact encoding; duplicate keys, invalid UTF-8 and nonfinite numbers are
rejected. The receipt is not signed and is not an authenticated remote identity.

Both complete original request and complete success receipt are saved and checked
on read. The receipt's actual commands must also match the corresponding immutable
`changes` record. JSON byte lengths are checked before loading stored request,
receipt or history bodies; pre-existing history may retain its original JSON
whitespace. A damaged binding fails closed and is never overwritten by a retry.

## Atomicity, concurrency and response loss

Each initial call uses the project's existing `BEGIN IMMEDIATE` write transaction:

1. Read any existing receipt for the exact scope and operation ID.
2. If its original request digest matches, return that original success with
   `replayed=true`; a different request is `RevisionConflict`.
3. Otherwise enforce the original revision CAS and apply the ordinary command
   batch through the shared store implementation.
4. Insert the complete success receipt in the **same transaction** as business
   rows, derived caches, revision, command history and undo delta.
5. Commit before returning the success with `replayed=false`.

Only successful edits have receipts. There is no separate pending ledger or
partially claimed operation. Validation, insertion, capacity or commit failure
rolls back the whole edit. Two connections/processes with one identity observe
one committed edit; different identities at the same base revision still compete
under the ordinary CAS, so only one can succeed.

A process can exit after SQLite has spilled uncommitted pages to the database.
Reopening then lets SQLite recover its hot rollback journal before reading the
project. Normal reads still use `mode=ro`. Only an initial
[`SQLITE_READONLY_ROLLBACK` (776)](https://www.sqlite.org/rescode.html#readonly_rollback),
before the read connection reaches its caller, permits one physical recovery
attempt. The store first checks the ordinary database file's bounded 100-byte
[SQLite header and STKP application ID](https://www.sqlite.org/fileformat2.html#application_id),
and checks file identity before and after recovery. It opens an existing file
with `mode=rw` and `query_only=ON` for the original identity and format reads,
closes that connection, then repeats the requested read on a fresh `mode=ro`
connection. SQLite alone rolls back the journal; the store never parses, copies
or deletes it. This recovery performs no business edit, revision increase,
receipt insertion, command replay or format upgrade. If writable database and
directory access or a recovery lock are unavailable, reopening fails with an
explicit recovery error. A fully committed receipt remains available after a
process exits before returning its reply.

Receipt lookup precedes the current revision CAS. After a lost reply, reopening,
later edits or undo, an identical explicit call returns the original receipt and
its original revision without editing again. It never rebases the request.
`replayed` is an observation flag, not a persisted field or proof that the original
reply reached the caller. A client should first query its retained identity after
an uncertain response and must not automatically invent a new ID or revision.

An undo/redo operation changes editable rows through the existing journal. It does
not remove, reset or replay receipts. A new edit can discard the redo branch
without freeing any earlier operation ID. An already applied receipt proves a
historical success, not that its effects remain in the current model.

## Budgets and retention

- At most 1000 commands, as for the existing shared edit API.
- At most **256 KiB** for the complete canonical original request, including its
  project, scope, operation ID and original revision.
- At most **512 KiB** for the complete canonical receipt, including `sha256` and
  the actual commands after generated IDs and normalization.
- At most **10000** successful operation receipts per project and **64 MiB** for
  the sum of canonical UTF-8 original requests plus complete receipts.

All scopes share the project budget. New receipts are rejected before commit when
a budget would be exceeded; existing successes remain queryable and replayable.
There is no automatic garbage collection or identity reuse. Reclaiming an old
receipt without retaining its consumed identity would reopen a duplicate-execution
window and requires a separate versioned retention design.

## Format 15 and compatibility

New projects use format 15. It adds `project_edit_operations` in the same SQLite
database, with `(scope, operation_id)` as primary key, a project foreign key and
an applied-revision foreign key to `changes`. The applied revision is unique and
constrained to the base revision plus one. This metadata is outside the editable
journal relations and is never undone.

Formats 1–14 remain readable and retain their existing ordinary edit capabilities.
The two new receipt APIs require explicit upgrade to 15 and never create a table
while reading an old project. The existing upgrade path first creates and verifies
a backup of the original database, then atomically adds the schema and increases
the revision once. Upgrade is not an undoable format downgrade. Older software
that only supports format 14 rejects a format-15 database rather than dropping
the receipt table.

Database backups and portable workspaces preserve the complete receipt table
without replaying edits. They also preserve historical project identity: importing
a copy does not grant access to a new machine. Restoring an older database can
restore an older receipt set. A future peer authority must invalidate prior
authorization when restoring/replacing its bound database generation and must not
claim global exactly-once execution after losing the authoritative receipt state.

This contract covers ordinary project command batches only. It does not make
undo/redo, file publication, model requests, task submission or external side
effects idempotent, and it does not expand the agent's permitted tools.
