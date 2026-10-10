"""The agent's tools (docs/design/agent-harness.md): a fixed registry at the read, record, model and draft levels.

Nothing here can change the project's revision, labels or settings, prepare or start a run, or connect anywhere: those
operations are not tools (suan/agent/levels.py lists every scripting operation and why the agent does not use it).
A tool works on the store directly, never through the script catalog, and returns bounded JSON for the model, the
objects it made and the data sources it read (computed here, never declared by the model).
"""
from dataclasses import dataclass, field
import json
import threading
import time
from uuid import UUID, uuid5

from suan.models.routing import candidates, task_kind
from suan.project import analyses, files, workflows
from suan.project.drafts import _IMMUTABLE as _DRAFT_IDENTITY, _digest as _draft_digest
from suan.project.requests import PARAMETER_SWEEP_PROMPT_VERSION, PROMPT_VERSION
from suan.project.store import ProjectError, RevisionConflict
from suan.workflows import muferro

from . import levels, stats

MAX_RESULT_BYTES = 16 * 1024
MAX_ANSWER_BYTES = 6 * 1024  # leaves room in the 16 KiB result for JSON escaping
MAX_PENDING_DRAFTS = 20
REQUEST_POLL_SECONDS = 0.2
CANCEL_WAIT_SECONDS = 60
_TERMINAL = ("completed", "failed", "cancelled", "uncertain")
_MANAGED = {files.TABLE_ID: "files", workflows.TABLE_ID: "workflows", analyses.TABLE_ID: "analyses"}
_NUMERIC = ("number", "integer")


@dataclass
class ToolContext:
    """What a tool may use: the project, which session and step it runs for, and the services it may ask."""
    store: object
    session_id: str
    turn: int
    call_id: str
    services: dict = field(default_factory=dict)  # requests (RequestExecutor), gateway, local (LocalModels)
    sources: list = field(default_factory=list)  # every data source the session has read before this step
    cancel: threading.Event = field(default_factory=threading.Event)
    deadline: float | None = None  # time.monotonic() by which the message's turn must end

    def object_id(self, kind):
        """The ID of an object this step makes: the same call replayed makes the same objects."""
        return str(uuid5(UUID(self.session_id), f"{self.turn}:{self.call_id}:{kind}"))


def all_public(store, sources):
    """With the labels as they are now: a table's values are public only when labelled public; its structure when
    labelled public or structure; anything else counts as private."""
    for source in sources:
        if source["kind"] == "table":
            if not store.labels.is_public("table", source["id"]):
                return False
        elif source["kind"] == "table_structure":
            if not store.labels.structure_public("table", source["id"]):
                return False
        else:
            return False
    return True


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
                document = store.workflows.get(entry["id"])["workflow"]["document"]
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


# ---- model: requests the session makes for itself (a parameter sweep, a question on a context) ----

def _request_exists(store, request_id):
    with store._connect() as db:
        return db.execute("SELECT 1 FROM project_requests WHERE id=?", (request_id,)).fetchone() is not None


def _choose(context, prompt_version, public):
    """The model for a request of the session: a running one, the nearest suitable by the S1d ranking; external only
    when every source of the session (and the request's own table) is public."""
    gateway, local = context.services["gateway"], context.services.get("local")
    try:
        models = local.routing_view() if local is not None else []
    except (ProjectError, OSError):
        models = []
    route = candidates(gateway.describe()["endpoints"], models, task=task_kind(prompt_version), public=public)
    ready = [item for item in route["candidates"] if not item.get("start")]
    if not ready:
        reasons = sorted({item["reason"] for item in route["excluded"]})
        raise ProjectError("No running model can answer this request" + (f" ({', '.join(reasons)})" if reasons else "")
                           + "; start a local model in Models and network")
    return {"adapter": ready[0]["adapter"], "model": ready[0]["model"]}


class StepFailed(ProjectError):
    """A tool step that failed after it had already made project objects: they still belong to the session."""

    def __init__(self, message, objects, sources):
        super().__init__(message)
        self.objects, self.sources = objects, sources


def _message_exists(store, message_id):
    with store._connect() as db:
        return db.execute("SELECT 1 FROM project_messages WHERE id=?", (message_id,)).fetchone() is not None


def _stopping(context):
    return context.cancel.is_set() or (context.deadline is not None and time.monotonic() > context.deadline)


def _ask(context, context_id, text, prompt_version, *, stale_check=False):
    """Save the question as a message on the context, make one request (or reuse the one this step made), start it
    once and wait for its final record. Returns ``(request, answer text, sources, objects)``; never resends. Once the
    step has made a message or request, a failure raises ``StepFailed`` carrying them, so they stay the session's."""
    store = context.store
    captured = store.contexts.get(context_id)
    sources = [{"kind": "table", "id": captured["selection"]["table_id"]}]
    public = all_public(store, context.sources + sources)
    message_id, request_id = context.object_id("message"), context.object_id("request")
    gateway, requests = context.services["gateway"], context.services["requests"]
    made = [("message", message_id)] if _message_exists(store, message_id) else []
    try:
        if _request_exists(store, request_id):  # a replayed step: the request keeps the model it was made with
            made = [("message", message_id), ("request", request_id)]
            record = store.requests.get(request_id)
        else:
            if _stopping(context):
                raise ProjectError("The session was cancelled or reached its time limit; nothing was sent")
            if stale_check and store.info()["revision"] != captured["source_revision"]:
                raise RevisionConflict("The project changed since the rows were captured; capture them again")
            if any(run["status"] in ("running", "cancel_requested") for run in store.workflow_runs.list(limit=100)["runs"]):
                raise ProjectError("A workflow run is writing to the project; wait for it to finish, then ask again")
            configuration = _choose(context, prompt_version, public)
            gateway.admit_sources(configuration, all_public=public)
            store.discussion.add(text, message_id=message_id, context_id=context_id)
            made = [("message", message_id)]
            record = store.requests.create(message_id, request_id=request_id, configuration=configuration,
                                           prompt_version=prompt_version)
            made.append(("request", request_id))
        if record["status"] == "pending":
            if _stopping(context):
                raise ProjectError("The session was cancelled or reached its time limit; the request was not sent")
            gateway.admit_sources(record["configuration"], all_public=public)  # labels are read again before sending
            record = requests.start(store, request_id)
        elif record["status"] == "running":
            try:  # left running by a lost executor: settled as uncertain once nobody holds it (never resent)
                record = requests.recover(store, request_id)
            except ProjectError:
                pass  # a live executor still owns it: wait for it
        cancelled = False
        while record["status"] not in _TERMINAL:
            # Cancelling the session or reaching the message's time limit cancels the request (once), then waits for
            # it to settle: a request the model may have received is never left running unrecorded.
            if not cancelled and _stopping(context):
                requests.cancel(store, request_id)
                cancelled = time.monotonic()
            elif cancelled and time.monotonic() - cancelled > CANCEL_WAIT_SECONDS:
                raise ProjectError("The request did not stop after it was cancelled; recover it from the conversation")
            time.sleep(REQUEST_POLL_SECONDS)
            record = store.requests.get(request_id)
        if record["status"] != "completed":
            raise ProjectError(f"The request ended {record['status']} ({record.get('error_code')}); it is not sent again")
        answer = store.discussion.get(record["result"]["message_id"])["text"]
    except StepFailed:
        raise
    except ProjectError as exc:
        if not made:
            raise
        raise StepFailed(str(exc), made, sources) from None
    return record, answer, sources, made


def _failed(exc):
    return ToolResult("error", {"error": str(exc)[:1000]}, objects=exc.objects, sources=exc.sources)


def propose_sweep(context, arguments):
    try:
        owned = context.store.agent_sessions.objects(context.session_id)
    except ProjectError:
        owned = []  # not a recorded session (a tool used on its own)
    pending = sum(1 for entry in owned if entry["kind"] == "draft" and context.store.drafts.get(entry["id"])["status"] == "pending")
    if pending >= MAX_PENDING_DRAFTS:
        return ToolResult("error", {"error": f"{pending} drafts of this session wait for review; ask the person to "
                                             "review them first"})
    try:
        record, _, sources, objects = _ask(context, arguments["context_id"], arguments["instruction"],
                                           PARAMETER_SWEEP_PROMPT_VERSION, stale_check=True)
    except StepFailed as exc:
        return _failed(exc)
    try:
        saved = context.store.requests.propose_edits(record["id"], expected_revision=record["source_revision"])
    except RevisionConflict:
        return ToolResult("error", {"error": "The project changed since the rows were captured; capture them again"},
                          objects=objects, sources=sources)
    except ProjectError as exc:
        return ToolResult("error", {"error": f"The model's sweep was not usable: {str(exc)[:500]}"}, objects=objects,
                          sources=sources)
    draft = saved["draft"]
    added = [command["id"] for command in draft["commands"] if command["op"] == "add_record"]
    return ToolResult("ok", {"draft_id": draft["id"], "title": draft["title"], "status": draft["status"],
                             "base_revision": draft["base_revision"], "new_rows": len(added),
                             "commands": len(draft["commands"]), "request_id": record["id"]},
                      objects=objects + [("draft", draft["id"])], sources=sources)


def ask_about_context(context, arguments):
    try:
        record, answer, sources, objects = _ask(context, arguments["context_id"], arguments["question"], PROMPT_VERSION)
    except StepFailed as exc:
        return _failed(exc)
    encoded = answer.encode("utf-8")
    data = {"request_id": record["id"], "model": record["configuration"]["model"],
            "answer": encoded[:MAX_ANSWER_BYTES].decode("utf-8", errors="ignore")}
    if len(encoded) > MAX_ANSWER_BYTES:
        data["truncated"] = True  # the whole answer stays in the project's conversation
    return ToolResult("ok", data, objects=objects, sources=sources)


# ---- read: drafts and runs ----

def draft_sha256(draft):
    """The digest of a draft's frozen content (what a person reviews and approves)."""
    return _draft_digest({key: draft[key] for key in _DRAFT_IDENTITY})


def _draft_tables(draft):
    tables = []
    for command in draft["commands"]:
        table = command.get("table_id")
        if table and table not in tables:
            tables.append(table)
    return tables


def _added_rows(draft):
    return [command["id"] for command in draft["commands"] if command["op"] == "add_record"]


def draft_status(context, arguments):
    draft = context.store.drafts.get(arguments["draft_id"])
    data = {"draft_id": draft["id"], "title": draft["title"], "status": draft["status"], "draft_sha256": draft_sha256(draft),
            "base_revision": draft["base_revision"], "applied_revision": draft.get("applied_revision"),
            "new_rows": _added_rows(draft)[:100], "tables": _draft_tables(draft),
            "project_revision": context.store.info()["revision"]}
    return ToolResult("ok", data, sources=[{"kind": "table", "id": table} for table in data["tables"]])


def _runs_covering(store, rows):
    wanted, found = set(rows), []
    for summary in store.workflow_runs.list(limit=100)["runs"]:
        run = store.workflow_runs.get(summary["id"])
        covered = [row["id"] for row in run["rows"] if row["id"] in wanted]
        if covered:
            simulation = run.get("simulation") or {}
            found.append({"run_id": run["id"], "workflow_name": run["workflow_name"], "status": run["status"],
                          "complete": run["complete"], "counts": run["counts"], "rows": covered[:100],
                          "table_id": run["table_id"], "connection": simulation.get("connection"),
                          "options": simulation.get("options")})
    return found


def find_runs(context, arguments):
    store = context.store
    if arguments.get("draft_id"):
        draft = store.drafts.get(arguments["draft_id"])
        rows, tables = _added_rows(draft), _draft_tables(draft)
    elif arguments.get("record_ids"):
        rows, tables = arguments["record_ids"], [arguments["table_id"]] if arguments.get("table_id") else []
    else:
        return ToolResult("error", {"error": "Give draft_id, or table_id and record_ids"})
    runs = _runs_covering(store, rows)
    tables += [run["table_id"] for run in runs if run["table_id"] not in tables]
    return ToolResult("ok", {"rows": len(rows), "runs": runs[:20]},
                      sources=[{"kind": "table_structure", "id": table} for table in tables])


# ---- record: a run's results as a captured context (Python version of the desktop's L3) ----

def capture_run_results(context, arguments):
    store = context.store
    run = store.workflow_runs.get(arguments["run_id"])
    results = []
    for task in run["tasks"]:
        record = (task.get("produced") or {}).get("result_record_id")
        if task["status"] == "succeeded" and record and record not in results:
            results.append(record)
    if not results:
        return ToolResult("error", {"error": "This run has no succeeded results yet"})
    if len(results) > 100:
        return ToolResult("error", {"error": "This run has more than 100 results; a context holds at most 100 rows"})
    with store._connect() as db:
        row = db.execute("SELECT table_id FROM records WHERE id=?", (results[0],)).fetchone()
        if row is None:
            return ToolResult("error", {"error": "The run's result rows are no longer in the project"})
        table_id = row[0]
        field_ids = [item[0] for item in db.execute(
            "SELECT id FROM fields WHERE table_id=? AND type IN ('number','integer') ORDER BY rowid LIMIT 64", (table_id,))]
    if not field_ids:
        return ToolResult("error", {"error": "The result table has no numeric fields"})
    return capture_rows(context, {"table_id": table_id, "record_ids": results, "field_ids": field_ids})


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
    Tool("propose_sweep", 1, "Ask a model for a parameter sweep over a captured context (vary fields of a base row) "
         "and save it as a draft of new rows for a person to review and apply. Never applies anything.",
         {"type": "object", "properties": {"context_id": _uuid_schema(),
                                           "instruction": {"type": "string", "minLength": 1, "maxLength": 4000}},
          "required": ["context_id", "instruction"], "additionalProperties": False}, propose_sweep,
         {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}),
    Tool("ask_about_context", 1, "Ask a model a question about a captured context; the answer is saved in the "
         "project's conversation and returned (at most 6 KiB; the whole answer stays in the conversation).",
         {"type": "object", "properties": {"context_id": _uuid_schema(),
                                           "question": {"type": "string", "minLength": 1, "maxLength": 4000}},
          "required": ["context_id", "question"], "additionalProperties": False}, ask_about_context,
         {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}),
    Tool("draft_status", 1, "A draft's status (pending, applied or discarded), its base and applied revisions and "
         "the IDs of the rows it adds.",
         {"type": "object", "properties": {"draft_id": _uuid_schema()}, "required": ["draft_id"],
          "additionalProperties": False}, draft_status,
         {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    Tool("find_runs", 1, "Workflow runs that cover the rows a draft added (or the given rows): status, task counts, "
         "where they ran and with which options.",
         {"type": "object", "properties": {"draft_id": _uuid_schema(), "table_id": _uuid_schema(),
                                           "record_ids": {"type": "array", "items": _uuid_schema(), "maxItems": 100}},
          "additionalProperties": False}, find_runs,
         {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    Tool("capture_run_results", 1, "Save the result rows of a workflow run's succeeded tasks (at most 100, numeric "
         "fields) as an immutable context and return their values.",
         {"type": "object", "properties": {"run_id": _uuid_schema()}, "required": ["run_id"],
          "additionalProperties": False}, capture_run_results,
         {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
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


__all__ = ["MAX_RESULT_BYTES", "REGISTRY", "Tool", "ToolContext", "ToolResult", "all_public", "content", "registry"]
