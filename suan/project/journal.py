"""Persistent edit deltas. Derived caches and external effects are never journaled.

Only rows touched by a command are captured, once per batch. SQLite rowids retain
the original display order when deleted objects are restored. All SQL identifiers
come from this module, never from the journal or a command.
"""

# Parent-first insertion order; deletion uses the reverse order.
RELATIONS = {
    "tables": ("id", "name"),
    "fields": ("id", "table_id", "name", "type", "unit"),
    "records": ("id", "table_id"),
    "cells": ("table_id", "record_id", "field_id", "value"),
    "definitions": ("table_id", "record_id", "field_id", "definition"),
}


def _key(relation, row):
    columns = RELATIONS[relation]
    keys = ("record_id", "field_id") if relation in {"cells", "definitions"} else ("id",)
    return tuple(row[1 + columns.index(column)] for column in keys)


def _where(relation):
    return "record_id=? AND field_id=?" if relation in {"cells", "definitions"} else "id=?"


def _row(db, relation, key):
    row = db.execute(f"SELECT rowid, * FROM {relation} WHERE {_where(relation)}", key).fetchone()
    return list(row) if row is not None else None


class Capture:
    def __init__(self, db):
        self.db = db
        self.before = {}

    def watch(self, relation, key):
        identity = (relation, tuple(key))
        if identity not in self.before:
            self.before[identity] = _row(self.db, relation, key)

    def children(self, relation, column, identity):
        for row in self.db.execute(f"SELECT rowid, * FROM {relation} WHERE {column}=?", (identity,)):
            self.before.setdefault((relation, _key(relation, row)), list(row))

    def command(self, command):
        # Invalid commands remain the store's responsibility and roll the transaction back.
        if not isinstance(command, dict):
            return
        op = command.get("op")
        if not isinstance(op, str):
            return
        if op in {"create_table", "add_field", "add_record", "rename_table", "rename_field"}:
            relation = {"create_table": "tables", "add_field": "fields", "add_record": "records",
                        "rename_table": "tables", "rename_field": "fields"}[op]
            if isinstance(command.get("id"), str):
                self.watch(relation, (command["id"],))
        elif op in {"set_cell", "set_reference", "set_expression", "unset_cell"}:
            if all(isinstance(command.get(key), str) for key in ("record_id", "field_id")):
                for relation in ("cells", "definitions"):
                    self.watch(relation, (command["record_id"], command["field_id"]))
        elif op in {"delete_table", "delete_field", "delete_record"} and isinstance(command.get("id"), str):
            kind = op.removeprefix("delete_")
            self.watch({"table": "tables", "field": "fields", "record": "records"}[kind], (command["id"],))
            for relation in ("cells", "definitions"):
                self.children(relation, kind + "_id", command["id"])
            if kind == "table":
                for relation in ("fields", "records"):
                    self.children(relation, "table_id", command["id"])

    def created(self, command):
        relation = {"create_table": "tables", "add_field": "fields", "add_record": "records"}.get(command["op"])
        if relation:
            # Covers IDs assigned by the store; an earlier delete/create in this same batch
            # retains the first before-image instead of treating the row as newly created.
            self.before.setdefault((relation, (command["id"],)), None)

    def delta(self):
        result = []
        for (relation, key), before in self.before.items():
            after = _row(self.db, relation, key)
            if before != after:
                result.append({"relation": relation, "key": list(key), "before": before, "after": after})
        return result


def restore(db, delta, side):
    """Restore one side atomically inside the caller's CAS-checked write transaction."""
    if side not in {"before", "after"} or not isinstance(delta, list):
        raise ValueError("Invalid edit journal")
    seen = set()
    for entry in delta:
        if not isinstance(entry, dict) or set(entry) != {"relation", "key", "before", "after"}:
            raise ValueError("Invalid edit journal entry")
        relation, key = entry["relation"], entry["key"]
        if not isinstance(relation, str) or relation not in RELATIONS or not isinstance(key, list):
            raise ValueError("Invalid edit journal identity")
        if len(key) != (2 if relation in {"cells", "definitions"} else 1) or not all(isinstance(k, str) for k in key):
            raise ValueError("Invalid edit journal key")
        identity = (relation, tuple(key))
        if identity in seen:
            raise ValueError("Duplicate edit journal key")
        seen.add(identity)
        for state in ("before", "after"):
            row = entry[state]
            if row is not None and (not isinstance(row, list) or len(row) != len(RELATIONS[relation]) + 1
                                    or type(row[0]) is not int or tuple(key) != _key(relation, row)):
                raise ValueError("Invalid edit journal row")
        # Refuse to overwrite a state that no longer matches this stack entry.
        other = "after" if side == "before" else "before"
        if _row(db, relation, key) != entry[other]:
            raise ValueError("Project rows do not match the edit journal; reopen a verified backup")

    # Temporary missing parents are allowed only inside this transaction. This also
    # handles delete/recreate batches that exchanged rowids; all target rows are freed first.
    db.execute("PRAGMA defer_foreign_keys=ON")
    for relation in reversed(RELATIONS):
        for entry in delta:
            if entry["relation"] == relation:
                db.execute(f"DELETE FROM {relation} WHERE {_where(relation)}", entry["key"])
    changed = set()
    for relation, columns in RELATIONS.items():
        for entry in delta:
            if entry["relation"] != relation:
                continue
            row = entry[side]
            if row is not None:
                placeholders = ",".join("?" for _ in row)
                db.execute(f"INSERT INTO {relation} (rowid,{','.join(columns)}) VALUES ({placeholders})", row)
            if relation in {"cells", "definitions"}:
                changed.add(("cell", *entry["key"]))
            elif relation in {"records", "fields"}:
                changed.add(("record" if relation == "records" else "field", entry["key"][0]))
    return changed
