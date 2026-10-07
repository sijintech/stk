"""One fixed-UUID ordinary project table whose records hold bounded literal JSON documents.

Saved analyses and workflows use it: writes are ordinary undoable project edits checked against an
expected revision; reads inspect literal cells directly and never evaluate formulas or load node plugins.
"""
import json
import math

from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _json, _version


MAX_DEPTH = 64
# Item/byte budget while detaching a document; each document type checks its own smaller limits.
MAX_JSON_BYTES = 384 * 1024
MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024
_MIN_INTEGER, _MAX_INTEGER = -(2**63), 2**64 - 1


def name(value, subject):
    if type(value) is not str or not value.strip() or "\0" in value or len(value) > 256:
        raise ProjectError(f"{subject} name must contain 1 to 256 characters without NUL")
    try:
        if len(value.encode("utf-8")) > 1024:
            raise ProjectError(f"{subject} name exceeds 1024 UTF-8 bytes")
    except UnicodeError:
        raise ProjectError(f"{subject} name must be valid UTF-8") from None
    return value


def clone(value, subject):
    """Detach plain JSON iteratively, bounding work before recursive JSON/schema helpers."""
    budget, count, ancestors = 0, 0, set()

    def item(source, depth):
        nonlocal budget, count
        count += 1
        if count > MAX_JSON_BYTES or depth > MAX_DEPTH:
            raise ProjectError(f"{subject} JSON exceeds the depth or item limit")
        kind = type(source)
        if kind in (dict, list):
            if id(source) in ancestors:
                raise ProjectError(f"{subject} JSON cannot contain cycles")
            budget += 2
            target = {} if kind is dict else []
            return target, (source, target, iter(source.items() if kind is dict else source), depth)
        if kind is str:
            if len(source) > MAX_JSON_BYTES:
                raise ProjectError(f"{subject} JSON exceeds the document byte limit")
            budget += len(source.encode("utf-8")) + 2
        elif kind is int:
            if not _MIN_INTEGER <= source <= _MAX_INTEGER:
                raise ProjectError(f"{subject} JSON integers must fit signed or unsigned 64-bit values")
            budget += len(str(source))
        elif kind is float:
            if not math.isfinite(source):
                raise ProjectError(f"{subject} JSON numbers must be finite")
            budget += len(str(source))
        elif source is None or kind is bool:
            budget += 4
        else:
            raise ProjectError(f"{subject} values must be plain JSON data")
        return source, None

    try:
        result, frame = item(value, 0)
        stack = [frame] if frame else []
        if frame:
            ancestors.add(id(frame[0]))
        while stack:
            source, target, iterator, depth = stack[-1]
            try:
                next_item = next(iterator)
            except StopIteration:
                ancestors.remove(id(source))
                stack.pop()
                continue
            if type(source) is dict:
                key, child = next_item
                if type(key) is not str:
                    raise ProjectError(f"{subject} JSON object keys must be strings")
                item(key, depth + 1)
            else:
                child = next_item
            copied, frame = item(child, depth + 1)
            if type(source) is dict:
                target[key] = copied
            else:
                target.append(copied)
            if budget > MAX_JSON_BYTES:
                raise ProjectError(f"{subject} JSON exceeds the document byte limit")
            if frame:
                ancestors.add(id(frame[0]))
                stack.append(frame)
        if budget > MAX_JSON_BYTES:
            raise ProjectError(f"{subject} JSON exceeds the document byte limit")
        return result
    except (UnicodeError, RuntimeError):
        raise ProjectError(f"{subject} JSON must be valid UTF-8 and stable while being captured") from None


def strict_decode(raw, subject):
    """Bound raw nesting before json.loads; reject ambiguous or lossy JSON literals."""
    try:
        text = raw.decode("utf-8")
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_DEPTH + 1:
                    raise ValueError("depth")
            elif char in "]}":
                depth -= 1

        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        def integer(text):
            if len(text.lstrip("-")) > 20:
                raise ValueError("integer size")
            value = int(text)
            if not _MIN_INTEGER <= value <= _MAX_INTEGER:
                raise ValueError("integer range")
            return value

        def number(text):
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("nonfinite")
            return value

        def constant(_):
            raise ValueError("nonfinite")

        return clone(json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                                 parse_float=number, parse_constant=constant), subject)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ProjectError(f"{subject} cell contains invalid, ambiguous or excessively nested JSON") from None



def snapshot_limit(store, db, subject, max_bytes=MAX_SNAPSHOT_BYTES):
    # Like bridge encode_message: UTF-8, compact separators, no ASCII escaping or NaN.
    # Scalar project formulas can be evaluated here; node code and files are never touched.
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    size = 0
    for chunk in encoder.iterencode(store._snapshot(db)):
        size += len(chunk.encode("utf-8"))
        if size > max_bytes:
            raise ProjectError(f"{subject} edit would exceed the 12 MiB project snapshot limit")


class ManagedTable:
    def __init__(self, *, table_id, table_name, fields, field_ids, subject, not_found, limits, limit_text, max_cell_bytes):
        """`limits()` returns (max records, max managed JSON bytes, max project snapshot bytes) at write time;
        `limit_text` names the first two in errors, for example "128 records or 4 MiB"."""
        self.table_id, self.table_name, self.fields, self.field_ids = table_id, table_name, fields, field_ids
        self.subject, self.not_found, self.limits, self.limit_text = subject, not_found, limits, limit_text
        self.max_cell_bytes = max_cell_bytes

    def require(self, db, documents):
        if _version(db) < 3:
            raise UnsupportedProjectFormat(f"Upgrade this project to format 3 before saving {documents}")

    def schema(self, db):
        """(exists, compatible, error) of the managed table's structure."""
        if db.execute("SELECT 1 FROM tables WHERE id=?", (self.table_id,)).fetchone() is None:
            return False, True, ""
        fields = {row["id"]: row for row in db.execute("SELECT id,type,unit FROM fields WHERE table_id=?", (self.table_id,))}
        for key, (_, kind) in self.fields.items():
            field = fields.get(self.field_ids[key])
            if field is None or field["type"] != kind or field["unit"] is not None:
                return True, False, (f"{self.subject} table has missing or incompatible fields; "
                                     "undo or explicitly repair the structural edit")
        return True, True, ""

    def literal(self, db, record_id, key):
        identity = (self.table_id, record_id, self.field_ids[key])
        size = db.execute("SELECT length(CAST(value AS BLOB)) FROM cells WHERE table_id=? AND record_id=? AND field_id=?",
                          identity).fetchone()
        if size is None:
            raise ProjectError(f"{self.subject} record has missing literal values")
        if size[0] > self.max_cell_bytes:
            raise ProjectError(f"{self.subject} cell exceeds the bounded stored JSON limit")
        raw = db.execute("SELECT CAST(value AS BLOB) FROM cells WHERE table_id=? AND record_id=? AND field_id=?",
                         identity).fetchone()[0]
        return strict_decode(raw, self.subject)

    def indirect(self, db, record_id):
        return any(row[0] in self.field_ids.values() for row in db.execute(
            "SELECT field_id FROM definitions WHERE table_id=? AND record_id=?", (self.table_id, record_id)))

    def write(self, store, db, identity, values, revision, *, create, document_format):
        """Create or replace one record's managed cells inside an open write transaction."""
        current = db.execute("SELECT revision FROM project").fetchone()[0]
        if current != revision:
            raise RevisionConflict(f"Expected revision {revision}, current revision is {current}")
        exists, compatible, error = self.schema(db)
        if not compatible:
            raise ProjectError(error)
        row = db.execute("SELECT table_id FROM records WHERE id=?", (identity,)).fetchone()
        if create and row is not None:
            raise RevisionConflict(f"{self.subject} record UUID already exists")
        if not create and (row is None or row[0] != self.table_id):
            raise self.not_found(f"{self.subject} document not found")
        lower = self.subject.lower()
        if not create:
            if self.indirect(db, identity):
                raise ProjectError(f"{self.subject} managed cells must be literals; explicitly replace the formula/reference first")
            try:
                old_format = self.literal(db, identity, "format")
            except ProjectError:
                old_format = None
            if type(old_format) is str and old_format != document_format:
                raise UnsupportedProjectFormat(f"Cannot replace an unsupported {lower} document format")
        serialized = {key: _json(value) for key, value in values.items()}
        count = db.execute("SELECT count(*) FROM records WHERE table_id=?", (self.table_id,)).fetchone()[0] + int(create)
        placeholders = ",".join("?" for _ in self.field_ids)
        managed = (self.table_id, *self.field_ids.values())
        total = db.execute(f"SELECT coalesce(sum(length(CAST(value AS BLOB))),0) FROM cells "
                           f"WHERE table_id=? AND field_id IN ({placeholders})", managed).fetchone()[0]
        replaced = db.execute(f"SELECT coalesce(sum(length(CAST(value AS BLOB))),0) FROM cells "
                              f"WHERE table_id=? AND field_id IN ({placeholders}) AND record_id=?",
                              (*managed, identity)).fetchone()[0]
        total = total - replaced + sum(len(value.encode("utf-8")) for value in serialized.values())
        max_records, max_bytes, max_snapshot = self.limits()
        if count > max_records or total > max_bytes:
            raise ProjectError(f"{self.subject} collection exceeds {self.limit_text} of stored managed JSON")
        commands = []
        if not exists:
            if db.execute(f"SELECT 1 FROM fields WHERE id IN ({placeholders}) LIMIT 1", tuple(self.field_ids.values())).fetchone():
                raise ProjectError(f"Reserved {lower} field IDs belong to another table; explicitly repair the structure")
            commands.append({"op": "create_table", "id": self.table_id, "name": self.table_name})
            commands.extend({"op": "add_field", "table_id": self.table_id, "id": self.field_ids[key], "name": title, "type": kind}
                            for key, (title, kind) in self.fields.items())
        if create:
            commands.append({"op": "add_record", "table_id": self.table_id, "id": identity})
        commands.extend({"op": "set_cell", "table_id": self.table_id, "record_id": identity,
                         "field_id": self.field_ids[key], "value": value} for key, value in values.items())
        try:
            result = store._apply(db, store._prepare_commands(commands, revision), revision)
            snapshot_limit(store, db, self.subject, max_snapshot)
        except ProjectError:
            raise
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ProjectError("Project data cannot be serialized safely; undo or repair invalid table values") from None
        return {**result, "table_id": self.table_id, "record_id": identity}
