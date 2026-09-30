"""Bounded analysis definitions stored in ordinary, undoable project tables.

Readable documents are editable drafts, not validated or executed graphs. Reads
inspect literal cells directly and never evaluate formulas or load node plugins.
The API's write limits do not constrain edits made through the generic table API.
"""
from functools import lru_cache
import json
import math
from uuid import NAMESPACE_URL, uuid5

from suan.contracts import load_schema
from suan.graph.schema import canonical_json, check_value

from .store import (ProjectError, RevisionConflict, UnsupportedProjectFormat,
                    _expected_revision, _id, _json, _version)


DOCUMENT_FORMAT = "stk.analysis-document/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:analyses:1"))
FIELDS = {"name": ("Name", "text"), "format": ("Format", "text"),
          "graph": ("Graph", "json"), "parameters": ("Parameters", "json"),
          "outputs": ("Outputs", "json")}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:analyses:1:" + key)) for key in FIELDS}
MAX_DEPTH = 64
MAX_GRAPH_BYTES = 256 * 1024
MAX_PARAMETERS_BYTES = 64 * 1024
MAX_DOCUMENT_BYTES = 384 * 1024
MAX_OUTPUTS = 256
MAX_ANALYSES = 128
MAX_COLLECTION_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024
_MAX_CELL_BYTES = 2 * MAX_DOCUMENT_BYTES
_MIN_INTEGER, _MAX_INTEGER = -(2**63), 2**64 - 1


class AnalysisNotFound(ProjectError):
    """No analysis record with this UUID belongs to the managed table."""


def _name(value):
    if type(value) is not str or not value.strip() or "\0" in value or len(value) > 256:
        raise ProjectError("Analysis name must contain 1 to 256 characters without NUL")
    try:
        if len(value.encode("utf-8")) > 1024:
            raise ProjectError("Analysis name exceeds 1024 UTF-8 bytes")
    except UnicodeError:
        raise ProjectError("Analysis name must be valid UTF-8") from None
    return value


def _clone(value):
    """Detach plain JSON iteratively, bounding work before recursive JSON/schema helpers."""
    budget, count, ancestors = 0, 0, set()

    def item(source, depth):
        nonlocal budget, count
        count += 1
        if count > MAX_DOCUMENT_BYTES or depth > MAX_DEPTH:
            raise ProjectError("Analysis JSON exceeds the depth or item limit")
        kind = type(source)
        if kind in (dict, list):
            if id(source) in ancestors:
                raise ProjectError("Analysis JSON cannot contain cycles")
            budget += 2
            target = {} if kind is dict else []
            return target, (source, target, iter(source.items() if kind is dict else source), depth)
        if kind is str:
            if len(source) > MAX_DOCUMENT_BYTES:
                raise ProjectError("Analysis JSON exceeds the document byte limit")
            budget += len(source.encode("utf-8")) + 2
        elif kind is int:
            if not _MIN_INTEGER <= source <= _MAX_INTEGER:
                raise ProjectError("Analysis JSON integers must fit signed or unsigned 64-bit values")
            budget += len(str(source))
        elif kind is float:
            if not math.isfinite(source):
                raise ProjectError("Analysis JSON numbers must be finite")
            budget += len(str(source))
        elif source is None or kind is bool:
            budget += 4
        else:
            raise ProjectError("Analysis values must be plain JSON data")
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
                    raise ProjectError("Analysis JSON object keys must be strings")
                item(key, depth + 1)
            else:
                child = next_item
            copied, frame = item(child, depth + 1)
            if type(source) is dict:
                target[key] = copied
            else:
                target.append(copied)
            if budget > MAX_DOCUMENT_BYTES:
                raise ProjectError("Analysis JSON exceeds the document byte limit")
            if frame:
                ancestors.add(id(frame[0]))
                stack.append(frame)
        if budget > MAX_DOCUMENT_BYTES:
            raise ProjectError("Analysis JSON exceeds the document byte limit")
        return result
    except (UnicodeError, RuntimeError):
        raise ProjectError("Analysis JSON must be valid UTF-8 and stable while being captured") from None


def _strict_decode(raw):
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

        return _clone(json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                                 parse_float=number, parse_constant=constant))
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ProjectError("Analysis cell contains invalid, ambiguous or excessively nested JSON") from None


@lru_cache(maxsize=1)
def _graph_schema():
    """Resolve only the trusted shipped structural schema; no registry or plugin imports."""
    document = load_schema("graph-1")

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = document
                for part in node["$ref"].removeprefix("#/").split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                rest = {key: inline(value) for key, value in node.items() if key != "$ref"}
                return {"allOf": [inline(target), rest]} if rest else inline(target)
            return {key: inline(value) for key, value in node.items() if key not in {"$defs", "$id", "$schema"}}
        if isinstance(node, list):
            return [inline(value) for value in node]
        return node

    return inline(document)


def _document(value):
    value = _clone(value)
    if type(value) is not dict or set(value) != {"format", "graph", "parameters", "outputs"}:
        raise ProjectError("Analysis document requires exactly format, graph, parameters and outputs")
    if value["format"] != DOCUMENT_FORMAT:
        raise UnsupportedProjectFormat("Unsupported analysis document format")
    graph, parameters, outputs = value["graph"], value["parameters"], value["outputs"]
    if type(graph) is not dict or len(canonical_json(graph)) > MAX_GRAPH_BYTES:
        raise ProjectError("Analysis graph must be an object of at most 256 KiB")
    problems = check_value(graph, _graph_schema())
    if problems:
        # Do not repeat untrusted values/keys in errors or depend on runtime node availability.
        raise ProjectError("Analysis graph does not match the structural stk.graph/1 contract")
    if any(len(canonical_json(node.get("params", {}))) > MAX_PARAMETERS_BYTES for node in graph["nodes"]):
        raise ProjectError("Analysis node parameters exceed 64 KiB")
    if type(parameters) is not dict or len(parameters) > 64 or len(canonical_json(parameters)) > MAX_PARAMETERS_BYTES:
        raise ProjectError("Analysis parameters require at most 64 overrides and 64 KiB")
    if (type(outputs) is not list or len(outputs) > MAX_OUTPUTS or
            any(type(name) is not str or name not in graph["outputs"] for name in outputs) or
            len(set(outputs)) != len(outputs)):
        raise ProjectError("Analysis outputs must be at most 256 distinct declared output names")
    if len(canonical_json(value)) > MAX_DOCUMENT_BYTES:
        raise ProjectError("Analysis document exceeds 384 KiB")
    return value


def _require(db):
    if _version(db) < 3:
        raise UnsupportedProjectFormat("Upgrade this project to format 3 before saving analysis documents")


def _schema(db):
    if db.execute("SELECT 1 FROM tables WHERE id=?", (TABLE_ID,)).fetchone() is None:
        return False, True, ""
    fields = {row["id"]: row for row in db.execute("SELECT id,type,unit FROM fields WHERE table_id=?", (TABLE_ID,))}
    for key, (_, kind) in FIELDS.items():
        field = fields.get(FIELD_IDS[key])
        if field is None or field["type"] != kind or field["unit"] is not None:
            return True, False, "Analysis table has missing or incompatible fields; undo or explicitly repair the structural edit"
    return True, True, ""


def _literal(db, record_id, key):
    identity = (TABLE_ID, record_id, FIELD_IDS[key])
    size = db.execute("SELECT length(CAST(value AS BLOB)) FROM cells WHERE table_id=? AND record_id=? AND field_id=?",
                      identity).fetchone()
    if size is None:
        raise ProjectError("Analysis record has missing literal values")
    if size[0] > _MAX_CELL_BYTES:
        raise ProjectError("Analysis cell exceeds the bounded stored JSON limit")
    raw = db.execute("SELECT CAST(value AS BLOB) FROM cells WHERE table_id=? AND record_id=? AND field_id=?",
                     identity).fetchone()[0]
    return _strict_decode(raw)


def _indirect(db, record_id):
    return any(row[0] in FIELD_IDS.values() for row in db.execute(
        "SELECT field_id FROM definitions WHERE table_id=? AND record_id=?", (TABLE_ID, record_id)))


def _record(db, identity, compatible, schema_error):
    entry = {"id": identity, "name": None, "format": None, "state": "invalid", "error": "", "document": None}
    try:
        entry["name"] = _name(_literal(db, identity, "name"))
    except ProjectError:
        pass
    try:
        value = _literal(db, identity, "format")
        if type(value) is str and 0 < len(value.encode("utf-8")) <= 128 and "\0" not in value:
            entry["format"] = value
    except ProjectError:
        pass
    if not compatible:
        entry["error"] = schema_error
    elif _indirect(db, identity):
        entry["error"] = "Analysis managed cells must be literals; undo or explicitly replace the formula/reference"
    elif entry["format"] is not None and entry["format"] != DOCUMENT_FORMAT:
        entry.update(state="unsupported", error="Unsupported analysis document format")
    else:
        try:
            if entry["name"] is None or entry["format"] != DOCUMENT_FORMAT:
                raise ProjectError("Analysis record has an invalid or missing name/format")
            entry["document"] = _document({"format": entry["format"],
                **{key: _literal(db, identity, key) for key in ("graph", "parameters", "outputs")}})
            entry["state"] = "readable"
        except ProjectError as exc:
            entry["error"] = str(exc)
    return entry


def _snapshot_limit(store, db):
    # Like bridge encode_message: UTF-8, compact separators, no ASCII escaping or NaN.
    # Scalar project formulas can be evaluated here; node code and files are never touched.
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    size = 0
    for chunk in encoder.iterencode(store._snapshot(db)):
        size += len(chunk.encode("utf-8"))
        if size > MAX_SNAPSHOT_BYTES:
            raise ProjectError("Analysis edit would exceed the 12 MiB project snapshot limit")


class Analyses:
    def __init__(self, store):
        self.store = store

    def list(self, *, offset=0, limit=50):
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Analysis pagination requires offset >= 0 and limit between 1 and 100")
        with self.store._connect() as db:
            _require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            _, compatible, error = _schema(db)
            total = db.execute("SELECT count(*) FROM records WHERE table_id=?", (TABLE_ID,)).fetchone()[0]
            records = []
            for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?", (TABLE_ID, limit, offset)):
                entry = _record(db, row[0], compatible, error)
                del entry["document"]
                records.append(entry)
            return {"revision": revision, "table_id": TABLE_ID, "compatible": compatible, "error": error,
                    "offset": offset, "total": total, "analyses": records}

    def get(self, analysis_id):
        _id(analysis_id)
        with self.store._connect() as db:
            _require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (TABLE_ID, analysis_id)).fetchone() is None:
                raise AnalysisNotFound("Analysis document not found")
            _, compatible, error = _schema(db)
            return {"revision": revision, "table_id": TABLE_ID, "compatible": compatible, "error": error,
                    "analysis": _record(db, analysis_id, compatible, error)}

    def create(self, name, document, *, analysis_id, expected_revision):
        return self._write(analysis_id, name, document, expected_revision, create=True)

    def update(self, analysis_id, name, document, *, expected_revision):
        return self._write(analysis_id, name, document, expected_revision, create=False)

    def _write(self, identity, name, document, revision, *, create):
        _id(identity)
        _expected_revision(revision)
        name, document = _name(name), _document(document)
        values = {"name": name, **document}
        serialized = {key: _json(value) for key, value in values.items()}
        with self.store._connect(write=True) as db:
            _require(db)
            current = db.execute("SELECT revision FROM project").fetchone()[0]
            if current != revision:
                raise RevisionConflict(f"Expected revision {revision}, current revision is {current}")
            exists, compatible, error = _schema(db)
            if not compatible:
                raise ProjectError(error)
            row = db.execute("SELECT table_id FROM records WHERE id=?", (identity,)).fetchone()
            if create and row is not None:
                raise RevisionConflict("Analysis record UUID already exists")
            if not create and (row is None or row[0] != TABLE_ID):
                raise AnalysisNotFound("Analysis document not found")
            if not create:
                if _indirect(db, identity):
                    raise ProjectError("Analysis managed cells must be literals; explicitly replace the formula/reference first")
                try:
                    old_format = _literal(db, identity, "format")
                except ProjectError:
                    old_format = None
                if type(old_format) is str and old_format != DOCUMENT_FORMAT:
                    raise UnsupportedProjectFormat("Cannot replace an unsupported analysis document format")
            count = db.execute("SELECT count(*) FROM records WHERE table_id=?", (TABLE_ID,)).fetchone()[0] + int(create)
            placeholders = ",".join("?" for _ in FIELD_IDS)
            managed = (TABLE_ID, *FIELD_IDS.values())
            total = db.execute(f"SELECT coalesce(sum(length(CAST(value AS BLOB))),0) FROM cells "
                               f"WHERE table_id=? AND field_id IN ({placeholders})", managed).fetchone()[0]
            replaced = db.execute(f"SELECT coalesce(sum(length(CAST(value AS BLOB))),0) FROM cells "
                                  f"WHERE table_id=? AND field_id IN ({placeholders}) AND record_id=?",
                                  (*managed, identity)).fetchone()[0]
            total = total - replaced + sum(len(value.encode("utf-8")) for value in serialized.values())
            if count > MAX_ANALYSES or total > MAX_COLLECTION_BYTES:
                raise ProjectError("Analysis collection exceeds 128 records or 4 MiB of stored managed JSON")
            commands = []
            if not exists:
                if db.execute(f"SELECT 1 FROM fields WHERE id IN ({placeholders}) LIMIT 1", tuple(FIELD_IDS.values())).fetchone():
                    raise ProjectError("Reserved analysis field IDs belong to another table; explicitly repair the structure")
                commands.append({"op": "create_table", "id": TABLE_ID, "name": "Analyses"})
                commands.extend({"op": "add_field", "table_id": TABLE_ID, "id": FIELD_IDS[key], "name": title, "type": kind}
                                for key, (title, kind) in FIELDS.items())
            if create:
                commands.append({"op": "add_record", "table_id": TABLE_ID, "id": identity})
            commands.extend({"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
                             "field_id": FIELD_IDS[key], "value": value} for key, value in values.items())
            try:
                result = self.store._apply(db, self.store._prepare_commands(commands, revision), revision)
                _snapshot_limit(self.store, db)
            except ProjectError:
                raise
            except (ValueError, TypeError, RecursionError, UnicodeError):
                raise ProjectError("Project data cannot be serialized safely; undo or repair invalid table values") from None
            return {**result, "table_id": TABLE_ID, "record_id": identity}
