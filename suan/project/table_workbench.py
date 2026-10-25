"""Typed table queries, durable views and atomic paste plans over ProjectStore."""
import csv
from functools import cmp_to_key
import io
import json
from uuid import uuid4

from .field_types import check, options
from .store import ProjectError, RevisionConflict, _expected_revision, _id, _json, _text, _version
from .table_reader import READ_BATCH, TableReader

MAX_TEXT_BYTES = 1024 * 1024
MAX_QUERY_BYTES = 8 * 1024 * 1024
OPS = {"eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty", "is_null", "is_unset", "is_error"}
NO_VALUE = {"is_empty", "is_not_empty", "is_null", "is_unset", "is_error"}


def view_definition(value, fields, *, allow_missing=False):
    from .managed import clone
    value = clone(value, "Table view")
    allowed = {"version", "kind", "columns", "filters", "sorts", "group_field_id", "row_height", "frozen_columns"}
    if (type(value) is not dict or value.keys() - allowed or type(value.get("version")) is not int or
            value["version"] != 1 or type(value.get("kind")) is not str or value["kind"] not in {"grid", "board", "gallery"}):
        raise ProjectError("Table view requires a supported version 1 kind and keys")
    field_map = {f["id"]: f for f in fields}
    issues = []

    def field_id(identity):
        _id(identity)
        if identity not in field_map:
            if not allow_missing:
                raise ProjectError("View field does not belong to this table")
            issues.append("Missing view field " + identity)
        return identity

    columns = value.get("columns", [{"field_id": f["id"], "width": 160, "hidden": False} for f in fields])
    if type(columns) is not list or len(columns) > 1000:
        raise ProjectError("View columns must be a bounded array")
    seen = set()
    normalized = []
    for column in columns:
        if type(column) is not dict or column.keys() - {"field_id", "width", "hidden"} or "field_id" not in column:
            raise ProjectError("Invalid view column")
        identity = field_id(column["field_id"])
        width, hidden = column.get("width", 160), column.get("hidden", False)
        if (identity in seen or type(width) not in (int, float) or not 48 <= width <= 2048 or type(hidden) is not bool):
            raise ProjectError("View columns need unique fields, width 48..2048 and a boolean hidden flag")
        seen.add(identity)
        normalized.append({"field_id": identity, "width": width, "hidden": hidden})
    sorts = value.get("sorts", [])
    if type(sorts) is not list or len(sorts) > 16:
        raise ProjectError("At most 16 view sorts are supported")
    sort_ids = set()
    for sort in sorts:
        if type(sort) is not dict or not {"field_id", "direction"} <= sort.keys() or sort.keys() - {"field_id", "direction", "nulls"}:
            raise ProjectError("Invalid view sort")
        identity = field_id(sort["field_id"])
        if (identity in sort_ids or type(sort["direction"]) is not str or sort["direction"] not in {"asc", "desc"} or
                type(sort.get("nulls", "last")) is not str or sort.get("nulls", "last") not in {"first", "last"}):
            raise ProjectError("Sort fields must be unique and use asc/desc and first/last")
        sort_ids.add(identity)
        sort.setdefault("nulls", "last")
    terms = [0]

    def filtering(node, depth=0):
        terms[0] += 1
        if depth > 6 or terms[0] > 64 or type(node) is not dict:
            raise ProjectError("View filters exceed their depth/term limit")
        if type(node.get("op")) is not str:
            raise ProjectError("Filter op must be a supported string")
        if node["op"] in {"and", "or"}:
            if set(node) != {"op", "conditions"} or type(node["conditions"]) is not list:
                raise ProjectError("Filter groups require op and conditions")
            for child in node["conditions"]:
                filtering(child, depth + 1)
        else:
            op = node.get("op")
            if type(op) is not str or op not in OPS or set(node) != ({"field_id", "op"} if op in NO_VALUE else {"field_id", "op", "value"}):
                raise ProjectError("Invalid typed filter condition")
            identity = field_id(node["field_id"])
            if op not in NO_VALUE and identity in field_map:
                field = field_map[identity]
                if op == "contains" and field["type"] == "multi_select":
                    check(node["value"], "single_select", field["options"])
                elif op != "contains":
                    check(node["value"], field["type"], field.get("options"))
                elif type(node["value"]) is not str:
                    raise ProjectError("Contains filter requires text or a choice ID")

    filters = value.get("filters", {"op": "and", "conditions": []})
    filtering(filters)
    group = value.get("group_field_id")
    if group is not None:
        field_id(group)
    height, frozen = value.get("row_height", 32), value.get("frozen_columns", 0)
    if (type(height) is not int or not 24 <= height <= 240 or type(frozen) is not int or not 0 <= frozen <= len(columns)):
        raise ProjectError("Invalid row height or frozen column count")
    return {"version": 1, "kind": value["kind"], "columns": normalized, "filters": filters,
            "sorts": sorts, "group_field_id": group, "row_height": height, "frozen_columns": frozen}, list(dict.fromkeys(issues))


def apply_view(db, command):
    if command["op"] == "delete_table_view":
        if db.execute("DELETE FROM table_views WHERE id=?", (command["id"],)).rowcount != 1:
            raise ProjectError("Cannot delete a missing table view")
        return
    if db.execute("SELECT 1 FROM tables WHERE id=?", (command["table_id"],)).fetchone() is None:
        raise ProjectError("View table is missing")
    old = db.execute("SELECT table_id FROM table_views WHERE id=?", (command["id"],)).fetchone()
    if old is not None and old[0] != command["table_id"]:
        raise ProjectError("A view cannot move between tables")
    from .field_types import read_options
    fields = [dict(row) for row in db.execute("SELECT * FROM fields WHERE table_id=? ORDER BY rowid", (command["table_id"],))]
    for f in fields:
        f["options"] = read_options(db, f["id"], f["type"])
    command["definition"], _ = view_definition(command["definition"], fields)
    db.execute("INSERT INTO table_views VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,definition=excluded.definition",
               (command["id"], command["table_id"], command["name"], _json(command["definition"])))


def cell_state(record, field_id):
    entry = record.get("evaluations", {}).get(field_id)
    if entry and entry.get("state") == "error":
        return "error", None
    if field_id not in record["values"]:
        return "unset", None
    value = record["values"][field_id]
    return ("null" if value is None else "value"), value


def matches(record, condition):
    op = condition["op"]
    if op in {"and", "or"}:
        values = (matches(record, child) for child in condition["conditions"])
        return all(values) if op == "and" else any(values)
    state, value = cell_state(record, condition["field_id"])
    empty = state in {"unset", "null"} or (state == "value" and value in ("", []))
    if op in NO_VALUE:
        return {"is_empty": empty, "is_not_empty": not empty, "is_null": state == "null",
                "is_unset": state == "unset", "is_error": state == "error"}[op]
    other = condition["value"]
    if state in {"unset", "error"}:
        return False
    if op in {"eq", "ne"}:
        equal = (type(value) is type(other) and value == other) or (type(value) in (int, float) and type(other) in (int, float) and value == other)
        return equal if op == "eq" else not equal
    if op == "contains":
        return type(value) in (str, list) and other in value
    if value is None or other is None or type(value) not in (str, int, float) or type(value) is bool:
        return False
    try:
        return {"gt": lambda: value > other, "gte": lambda: value >= other,
                "lt": lambda: value < other, "lte": lambda: value <= other}[op]()
    except TypeError:
        return False


def compare_records(a, b, sorts):
    for sort in sorts:
        left_state, left = cell_state(a, sort["field_id"])
        right_state, right = cell_state(b, sort["field_id"])
        if left_state != "value" or right_state != "value":
            ranks = {"value": 0, "null": 1, "unset": 2, "error": 3}
            if sort["nulls"] == "first":
                ranks = {"null": 0, "unset": 1, "error": 2, "value": 3}
            order = (ranks[left_state] > ranks[right_state]) - (ranks[left_state] < ranks[right_state])
        else:
            if type(left) in (dict, list) or type(right) in (dict, list):
                left, right = _json(left), _json(right)
            try:
                order = (left > right) - (left < right)
            except TypeError:
                left, right = _json(left), _json(right)
                order = (left > right) - (left < right)
            if sort["direction"] == "desc":
                order = -order
        if order:
            return order
    return 0  # Stable sort retains the original record order for equal keys.


def query_page(db, reader, definition, offset, limit):
    """Page first for an unfiltered view; otherwise scan only filter/sort cells."""
    sorts = definition["sorts"]
    if definition["group_field_id"] is not None:
        sorts = [{"field_id": definition["group_field_id"], "direction": "asc", "nulls": "last"}, *sorts]
    filters = definition["filters"]
    if not sorts and filters == {"op": "and", "conditions": []}:
        total = db.execute("SELECT count(*) FROM records WHERE table_id=?", (reader.table_id,)).fetchone()[0]
        identities = [row[0] for row in db.execute(
            "SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?",
            (reader.table_id, limit, offset))]
        return total, reader.records(identities)

    sort_fields = {sort["field_id"] for sort in sorts}
    field_ids = set(sort_fields)

    def filter_fields(node):
        if node["op"] in {"and", "or"}:
            for child in node["conditions"]:
                filter_fields(child)
        else:
            field_ids.add(node["field_id"])

    filter_fields(filters)
    cursor = db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid", (reader.table_id,))
    total, selected, sortable = 0, [], []
    while identities := [row[0] for row in cursor.fetchmany(READ_BATCH)]:
        for record in reader.records(identities, field_ids):
            if matches(record, filters):
                if sorts:
                    # Drop formula definitions/results after inspecting their
                    # state. Sorting needs only typed values and error markers.
                    sortable.append({"id": record["id"], "values": {key: value for key, value in
                                                                     record["values"].items() if key in sort_fields},
                                     "evaluations": {key: {"state": "error"} for key, value in
                                                     record.get("evaluations", {}).items()
                                                     if key in sort_fields and value["state"] == "error"}})
                elif offset <= total < offset + limit:
                    selected.append(record["id"])
                total += 1
    if sorts:
        sortable.sort(key=cmp_to_key(lambda a, b: compare_records(a, b, sorts)))
        selected = [record["id"] for record in sortable[offset:offset + limit]]
    return total, reader.records(selected)


def paste_value(text, field):
    kind = field["type"]
    if kind == "text":
        return text
    if not text.strip():
        return None
    if kind in {"date", "url"}:
        return text
    if kind.endswith("select"):
        choices = field["options"]["choices"]

        def choice(raw):
            found = [c["id"] for c in choices if raw == c["id"]]
            if not found:
                found = [c["id"] for c in choices if raw == c["label"]]
            if len(found) != 1:
                raise ProjectError("Pasted select value needs an exact choice ID or unique label")
            return found[0]

        if kind == "single_select":
            return choice(text)
        try:
            values = json.loads(text)
        except (ValueError, RecursionError):
            raise ProjectError("Pasted multiple choices must be a JSON array") from None
        if type(values) is not list:
            raise ProjectError("Pasted multiple choices must be a JSON array")
        return [choice(v) for v in values]
    from .csv_io import _literal
    if kind == "object":
        try:
            return json.loads(text)
        except (ValueError, RecursionError):
            raise ProjectError("Pasted object references must be explicit JSON") from None
    return _literal(text, kind, 0, field["name"])


class TableWorkbench:
    def __init__(self, store):
        self.store = store

    def _revision(self, db, expected_revision):
        _expected_revision(expected_revision)
        revision = db.execute("SELECT revision FROM project").fetchone()[0]
        if revision != expected_revision:
            raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
        return revision

    @staticmethod
    def _view(row):
        return {"id": row["id"], "table_id": row["table_id"], "name": row["name"], "definition": json.loads(row["definition"])}

    def views_list(self, table_id, *, expected_revision):
        _id(table_id)
        with self.store._connect() as db:
            revision = self._revision(db, expected_revision)
            if db.execute("SELECT 1 FROM tables WHERE id=?", (table_id,)).fetchone() is None:
                raise ProjectError("Table is missing")
            views = [] if _version(db) < 14 else [self._view(row) for row in db.execute("SELECT * FROM table_views WHERE table_id=? ORDER BY rowid", (table_id,))]
            return {"revision": revision, "views": views}

    def views_get(self, identity, *, expected_revision):
        _id(identity)
        with self.store._connect() as db:
            revision = self._revision(db, expected_revision)
            row = db.execute("SELECT * FROM table_views WHERE id=?", (identity,)).fetchone() if _version(db) >= 14 else None
            if row is None:
                raise FileNotFoundError("Table view is missing")
            return {"revision": revision, "view": self._view(row)}

    def query(self, table_id, *, expected_revision, view_id=None, definition=None, offset=0, limit=200):
        _id(table_id)
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 500:
            raise ProjectError("Table query requires offset >= 0 and limit 1 to 500")
        if view_id is not None and definition is not None:
            raise ProjectError("Use either view_id or an explicit view definition")
        with self.store._connect() as db:
            revision = self._revision(db, expected_revision)
            if db.execute("SELECT 1 FROM tables WHERE id=?", (table_id,)).fetchone() is None:
                raise ProjectError("Table is missing")
            reader = TableReader(db, table_id, revision, _version(db))
            if view_id is not None:
                _id(view_id)
                row = db.execute("SELECT * FROM table_views WHERE id=? AND table_id=?", (view_id, table_id)).fetchone() if _version(db) >= 14 else None
                if row is None:
                    raise FileNotFoundError("Table view is missing or belongs to a different table")
                definition = json.loads(row["definition"])
            if definition is None:
                definition = {"version": 1, "kind": "grid"}
            definition, issues = view_definition(definition, reader.fields, allow_missing=view_id is not None)
            total, page = (0, []) if issues else query_page(db, reader, definition, offset, limit)
            by_id = {f["id"]: f for f in reader.fields}
            fields = [by_id[c["field_id"]] for c in definition["columns"] if c["field_id"] in by_id]
            result = {"revision": revision, "table_id": table_id, "view_id": view_id, "definition": definition,
                      "fields": fields, "total": total, "record_ids": [r["id"] for r in page], "records": page,
                      "next_offset": offset + limit if offset + limit < total else None, "issues": issues}
            if len(_json(result).encode("utf-8")) > MAX_QUERY_BYTES:
                raise ProjectError("Table query exceeds 8 MiB; reduce the page size")
            return result

    def paste_plan(self, table_id, record_ids, field_ids, text, *, expected_revision, delimiter="\t", append_rows=False, fit_targets=False):
        _id(table_id)
        if (type(text) is not str or len(text.encode("utf-8")) > MAX_TEXT_BYTES or "\0" in text or
                delimiter not in ("\t", ",") or type(append_rows) is not bool or type(fit_targets) is not bool):
            raise ProjectError("Paste requires bounded UTF-8 CSV/TSV text without NUL")
        for values in (record_ids, field_ids):
            if type(values) is not list or len(values) > 1000:
                raise ProjectError("Paste target IDs must be unique bounded arrays")
            for identity in values:
                _id(identity)
            if len(set(values)) != len(values):
                raise ProjectError("Paste target IDs must be unique bounded arrays")
        if not field_ids:
            raise ProjectError("Paste needs at least one field")
        with self.store._connect() as db:
            self._revision(db, expected_revision)
            table = next((t for t in self.store._snapshot(db)["tables"] if t["id"] == table_id), None)
        if table is None:
            raise ProjectError("Paste table is missing")
        rows, fields = {r["id"] for r in table["records"]}, {f["id"]: f for f in table["fields"]}
        if any(r not in rows for r in record_ids) or any(f not in fields for f in field_ids):
            raise ProjectError("Paste target does not belong to this table")
        try:
            matrix = []
            for index, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)):
                if index >= 1000:
                    raise ProjectError("Paste exceeds the bounded 1000-row atomic plan")
                matrix.append(row)
            if not text:
                matrix = [[""]]
        except csv.Error as exc:
            raise ProjectError(f"Invalid pasted CSV/TSV: {exc}") from None
        matrix = [row or [""] for row in matrix]
        if fit_targets and matrix:
            columns = len(matrix[0])
            if columns > len(field_ids) or any(len(row) != columns for row in matrix):
                raise ProjectError("Pasted rectangle exceeds the provided fields or is nonrectangular")
            field_ids = field_ids[:columns]
            record_ids = record_ids[:len(matrix)]
        if (not matrix or any(len(row) != len(field_ids) for row in matrix) or len(matrix) < len(record_ids) or
                (len(matrix) != len(record_ids) and not append_rows)):
            raise ProjectError("Paste must match the exact target rectangle; appending rows must be explicit")
        command_count = len(matrix) * len(field_ids) + len(matrix) - len(record_ids)
        if command_count > 1000:
            raise ProjectError("Paste exceeds one atomic batch of 1000 commands")
        targets, commands = list(record_ids), []
        for _ in range(len(matrix) - len(targets)):
            identity = str(uuid4())
            targets.append(identity)
            commands.append({"op": "add_record", "table_id": table_id, "id": identity})
        for identity, values in zip(targets, matrix):
            for field_id, raw in zip(field_ids, values):
                field = fields[field_id]
                value = paste_value(raw, field)
                check(value, field["type"], field.get("options"), self.store._project_id)
                commands.append({"op": "set_cell", "table_id": table_id, "record_id": identity, "field_id": field_id, "value": value})
        preview = self.store.preview(commands, expected_revision=expected_revision)
        return {"base_revision": expected_revision, "table_id": table_id, "rows": len(matrix), "columns": len(field_ids),
                "command_count": len(commands), "record_ids": targets, "field_ids": field_ids, "commands": preview["commands"]}

    def objects_resolve(self, value, *, expected_revision):
        from .object_refs import resolve
        with self.store._connect() as db:
            revision = self._revision(db, expected_revision)
            return {"revision": revision, **resolve(self.store, db, value)}

    def objects_list_candidates(self, kind, *, expected_revision, table_id=None, offset=0, limit=100):
        from .object_refs import candidates
        with self.store._connect() as db:
            revision = self._revision(db, expected_revision)
            return {"revision": revision, **candidates(self.store, db, kind, table_id, offset, limit)}
