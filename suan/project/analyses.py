"""Bounded analysis definitions stored in ordinary, undoable project tables.

Readable documents are editable drafts, not validated or executed graphs. Reads
inspect literal cells directly and never evaluate formulas or load node plugins.
The API's write limits do not constrain edits made through the generic table API.
"""
from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from suan.contracts import load_schema
from suan.graph.schema import canonical_json, check_value

from .managed import MAX_DEPTH, ManagedTable, clone, name  # noqa: F401 - MAX_DEPTH stays importable here
from .store import ProjectError, UnsupportedProjectFormat, _expected_revision, _id


DOCUMENT_FORMAT = "stk.analysis-document/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:analyses:1"))
FIELDS = {"name": ("Name", "text"), "format": ("Format", "text"),
          "graph": ("Graph", "json"), "parameters": ("Parameters", "json"),
          "outputs": ("Outputs", "json")}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:analyses:1:" + key)) for key in FIELDS}
MAX_GRAPH_BYTES = 256 * 1024
MAX_PARAMETERS_BYTES = 64 * 1024
MAX_DOCUMENT_BYTES = 384 * 1024
MAX_OUTPUTS = 256
MAX_ANALYSES = 128
MAX_COLLECTION_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024
_MAX_CELL_BYTES = 2 * MAX_DOCUMENT_BYTES


class AnalysisNotFound(ProjectError):
    """No analysis record with this UUID belongs to the managed table."""


_TABLE = ManagedTable(table_id=TABLE_ID, table_name="Analyses", fields=FIELDS, field_ids=FIELD_IDS,
                      subject="Analysis", not_found=AnalysisNotFound,
                      # Read at write time so the module limits stay authoritative.
                      limits=lambda: (MAX_ANALYSES, MAX_COLLECTION_BYTES, MAX_SNAPSHOT_BYTES),
                      limit_text="128 records or 4 MiB", max_cell_bytes=_MAX_CELL_BYTES)


def _name(value):
    return name(value, "Analysis")


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
    value = clone(value, "Analysis")
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
    _TABLE.require(db, "analysis documents")


def _schema(db):
    return _TABLE.schema(db)


def _literal(db, record_id, key):
    return _TABLE.literal(db, record_id, key)


def _indirect(db, record_id):
    return _TABLE.indirect(db, record_id)


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
        with self.store._connect(write=True) as db:
            _require(db)
            return _TABLE.write(self.store, db, identity, {"name": name, **document}, revision,
                                create=create, document_format=DOCUMENT_FORMAT)
