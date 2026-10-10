"""The agent's tools (docs/design/agent-harness.md): a fixed registry at the read, record, model and draft levels.

Nothing here can change the project's revision, labels or settings, prepare or start a run, or connect anywhere: those
operations are not tools (suan/agent/levels.py lists every scripting operation and why the agent does not use it).
A tool works on the store directly, never through the script catalog, and returns bounded JSON for the model, the
objects it made and the data sources it read (computed here, never declared by the model).
"""
from dataclasses import dataclass, field
import json
from uuid import UUID, uuid5

from suan.project import analyses, files, workflows
from suan.project.store import ProjectError, RevisionConflict
from suan.workflows import muferro

from . import levels, stats

MAX_RESULT_BYTES = 16 * 1024
_MANAGED = {files.TABLE_ID: "files", workflows.TABLE_ID: "workflows", analyses.TABLE_ID: "analyses"}
_NUMERIC = ("number", "integer")


@dataclass
class ToolContext:
    """What a tool may use: the project, which session and step it runs for, and the services it may ask."""
    store: object
    session_id: str
    turn: int
    call_id: str
    services: dict = field(default_factory=dict)

    def object_id(self, kind):
        """The ID of an object this step makes: the same call replayed makes the same objects."""
        return str(uuid5(UUID(self.session_id), f"{self.turn}:{self.call_id}:{kind}"))


@dataclass
class ToolResult:
    status: str  # "ok" or "error"
    data: object
    objects: list = field(default_factory=list)  # [(kind, id)]
    sources: list = field(default_factory=list)  # [{"kind": "table" | "table_structure", "id": ...}]


@dataclass(frozen=True)
class Tool:
    name: str
    version: int
    description: str
    parameters: dict
    handler: object = field(repr=False)
    annotations: dict = field(default_factory=dict)

    @property
    def level(self):
        return levels.tool_level(self.name)

    def definition(self):
        """What a session header freezes about the tool."""
        return {"name": self.name, "version": self.version, "level": self.level, "annotations": self.annotations,
                "description": self.description, "parameters": self.parameters}


def _uuid_schema():
    return {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}


# ---- read: the project's structure, without any value ----

def project_outline(context, arguments):
    store = context.store
    with store._connect() as db:
        tables = [dict(row) for row in db.execute("SELECT id, name FROM tables ORDER BY rowid")]
        fields = {}
        for row in db.execute("SELECT id, table_id, name, type, unit FROM fields ORDER BY rowid"):
            fields.setdefault(row["table_id"], []).append({"id": row["id"], "name": row["name"], "type": row["type"],
                                                           "unit": row["unit"]})
        counts = {row[0]: row[1] for row in db.execute("SELECT table_id, count(*) FROM records GROUP BY table_id")}
    listed, sources = [], []
    for table in tables:
        if table["id"] in _MANAGED:
            continue
        label = store.labels.label("table", table["id"])
        role = "muferro_cases" if table["id"] == muferro.TABLE_ID else "muferro_results" if table["id"] == muferro.RESULT_TABLE_ID \
            else None
        entry = {"id": table["id"], "name": table["name"], "rows": counts.get(table["id"], 0), "label": label,
                 "fields": fields.get(table["id"], [])}
        if role:
            entry["role"] = role
        listed.append(entry)
        sources.append({"kind": "table_structure", "id": table["id"]})
    flows = []
    try:
        for entry in store.workflows.list(limit=100)["workflows"]:
            item = {"id": entry["id"], "name": entry["name"], "state": entry["state"], "parameter_table_id": entry["table_id"]}
            if entry["state"] == "readable":
                document = store.workflows.get(entry["id"])["document"]
                item["steps"] = [step["kind"] + (f":{(step.get('ref') or {}).get('node')}" if step["kind"] == "remote" else "")
                                 for step in document["steps"]]
            flows.append(item)
    except ProjectError:
        pass
    return ToolResult("ok", {"revision": store.info()["revision"], "tables": listed, "workflows": flows}, sources=sources)


# ---- record: capture rows as an immutable context ----

def capture_rows(context, arguments):
    store = context.store
    table_id = arguments["table_id"]
    with store._connect() as db:
        if db.execute("SELECT 1 FROM tables WHERE id=?", (table_id,)).fetchone() is None or table_id in _MANAGED:
            return ToolResult("error", {"error": "No such parameter table"})
        field_ids = arguments.get("field_ids") or [row[0] for row in db.execute(
            "SELECT id FROM fields WHERE table_id=? ORDER BY rowid LIMIT 64", (table_id,))]
        record_ids = arguments.get("record_ids") or [row[0] for row in db.execute(
            "SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT 100", (table_id,))]
    if not field_ids or not record_ids:
        return ToolResult("error", {"error": "The table has no rows or fields to capture"})
    record_ids, field_ids = record_ids[:100], field_ids[:64]
    while len(record_ids) * len(field_ids) > 1000 and len(record_ids) > 1:
        record_ids = record_ids[:len(record_ids) - 1]
    context_id = context.object_id("context")
    try:
        captured = store.contexts.capture(table_id, record_ids, field_ids, expected_revision=store.info()["revision"],
                                          title=f"Agent step {context.turn}:{context.call_id}"[:200], context_id=context_id)
    except RevisionConflict:
        return ToolResult("error", {"error": "The project changed while capturing; call capture_rows again"})
    content = captured["content"]
    data = {"context_id": context_id, "source_revision": captured["source_revision"], "table": content.get("value", {}).get("table"),
            "fields": content.get("value", {}).get("fields", []), "rows": _rows(content.get("value")),
            "missing": captured["diagnostics"]}
    if content["state"] != "included":
        data["omitted"] = content.get("reason")
    return ToolResult("ok", data, objects=[("context", context_id)], sources=[{"kind": "table", "id": table_id}])


def _cell(record, field_id):
    """A cell's value as captured: its literal, else its evaluated value (state ok), else None."""
    literal = record.get("literals", {}).get(field_id)
    if literal and literal.get("state") == "included":
        return literal["value"]
    evaluation = record.get("evaluations", {}).get(field_id)
    if evaluation and evaluation.get("state") == "included" and isinstance(evaluation.get("value"), dict) \
            and evaluation["value"].get("state") == "ok":
        return evaluation["value"]["value"]
    return None


def _rows(value):
    if not value:
        return []
    return [{"id": record["id"], **{field["id"]: _cell(record, field["id"]) for field in value["fields"]}}
            for record in value["records"]]


# ---- read: statistics of a captured context ----

def table_statistics(context, arguments):
    captured = context.store.contexts.get(arguments["context_id"])
    value = captured["content"].get("value")
    if value is None:
        return ToolResult("error", {"error": "The context's values were omitted (too large); capture fewer rows or fields"})
    fields = {field["id"]: field for field in value["fields"]}
    wanted = arguments.get("fields") or [identity for identity, field in fields.items() if field["type"] in _NUMERIC]
    result = {"context_id": captured["id"], "rows": len(value["records"]), "fields": {}}
    for identity in wanted:
        if identity not in fields:
            return ToolResult("error", {"error": f"Field {identity} is not in the context"})
        numbers = [_number(_cell(record, identity)) for record in value["records"]]
        present = [number for number in numbers if number is not None]
        result["fields"][identity] = {"name": fields[identity]["name"], "unit": fields[identity]["unit"],
                                      "missing": len(numbers) - len(present), **stats.summary(present)}
    fit = arguments.get("fit", "none")
    if fit != "none":
        x_field = arguments.get("x_field")
        if x_field not in fields or len(wanted) != 1 or wanted[0] == x_field:
            return ToolResult("error", {"error": "A fit needs x_field and exactly one other field in fields"})
        pairs = [(_number(_cell(record, x_field)), _number(_cell(record, wanted[0]))) for record in value["records"]]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        result["fit"] = {"x": x_field, "y": wanted[0], **stats.fit([x for x, _ in pairs], [y for _, y in pairs],
                                                                   1 if fit == "linear" else 2)}
    return ToolResult("ok", result, sources=[{"kind": "table", "id": captured["selection"]["table_id"]}])


def _number(value):
    if type(value) in (int, float) and value == value and value not in (float("inf"), float("-inf")):
        return value
    return None


REGISTRY = {tool.name: tool for tool in (
    Tool("project_outline", 1, "The project's parameter tables (fields with types and units, row counts, data label: "
         "public, structure or private) and workflows (steps, parameter table). Reads no values.",
         {"type": "object", "properties": {}, "additionalProperties": False}, project_outline,
         {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    Tool("capture_rows", 1, "Save rows of a parameter table as an immutable context and return their values "
         "(default: every field, the first 100 rows; at most 100 rows, 64 fields and 1000 cells).",
         {"type": "object", "properties": {"table_id": _uuid_schema(),
                                           "record_ids": {"type": "array", "items": _uuid_schema(), "maxItems": 100},
                                           "field_ids": {"type": "array", "items": _uuid_schema(), "maxItems": 64}},
          "required": ["table_id"], "additionalProperties": False}, capture_rows,
         {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    Tool("table_statistics", 1, "Count, mean, standard deviation, minimum and maximum of numeric fields of a captured "
         "context; optionally a least-squares fit (linear or quadratic) of one field against x_field, with R².",
         {"type": "object", "properties": {"context_id": _uuid_schema(),
                                           "fields": {"type": "array", "items": _uuid_schema(), "maxItems": 64},
                                           "x_field": _uuid_schema(),
                                           "fit": {"enum": ["none", "linear", "quadratic"]}},
          "required": ["context_id"], "additionalProperties": False}, table_statistics,
         {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
)}


def registry(names=None):
    """The tools a session offers (all registered ones by default), in a fixed order."""
    names = list(REGISTRY) if names is None else names
    return [REGISTRY[name] for name in names]


def content(tool_name, result):
    """What the model sees: bounded JSON text (truncated with a marker when too long)."""
    text = json.dumps({"tool": tool_name, "status": result.status, "data": result.data}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    if len(text.encode("utf-8")) <= MAX_RESULT_BYTES:
        return text, False
    cut = text.encode("utf-8")[:MAX_RESULT_BYTES - 64].decode("utf-8", errors="ignore")
    return cut + '…{"truncated":true}', True


__all__ = ["MAX_RESULT_BYTES", "REGISTRY", "Tool", "ToolContext", "ToolResult", "content", "registry"]
