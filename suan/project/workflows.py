"""Project workflows: experimental `stk.workflow/1` documents in an ordinary, undoable project table.

A workflow lists steps that reference existing project objects by UUID (a parameter table, an
input snapshot, a saved analysis) or a registered simulation template, connected by typed ports.
Saving checks only the document's shape (workflows are drafts); `validate` resolves references
against the current project and reports located issues. Nothing here evaluates graphs, prepares
or submits runs, reads data files or contacts a model. Design: docs/design/project-workflows.md.
"""
import hashlib
import json
import math
import re
from uuid import NAMESPACE_URL, uuid5

from suan.graph.schema import canonical_json

from . import analyses, files
from .managed import ManagedTable, clone, name as _valid_name
from .store import ProjectError, UnsupportedProjectFormat, _expected_revision, _id, _version


DOCUMENT_FORMAT = "stk.workflow/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:workflows:1"))
FIELDS = {"name": ("Name", "text"), "format": ("Format", "text"),
          "steps": ("Steps", "json"), "ui": ("UI", "json")}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:workflows:1:" + key)) for key in FIELDS}
MAX_STEPS = 200
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_PARAMETERS_BYTES = 64 * 1024
MAX_WORKFLOWS = 128
MAX_COLLECTION_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024
MAX_ISSUES = 256
MAX_CHOICE_TABLES = 500
MAX_CHOICE_SNAPSHOTS = 200
KINDS = ("table", "files", "simulation", "analysis")
# Step kind -> the single key its `ref` object holds.
REF_KEYS = {"table": "table", "files": "snapshot", "simulation": "template", "analysis": "analysis"}
STEP_KEYS = {"id", "kind", "ref", "label", "inputs", "parameters", "after"}
# Project field type -> graph parameter types a `{"$field": ...}` binding may feed.
FIELD_PARAMETER_TYPES = {"number": {"number"}, "integer": {"integer", "number", "step"},
                         "text": {"string", "enum"}, "boolean": {"boolean"},
                         "json": {"json", "vector3", "int3", "range"}}
_IDENT = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_PORT_REF = re.compile(r"([a-z][a-z0-9_]{0,63})\.([a-z][a-z0-9_]{0,63})\Z")
_MAX_CELL_BYTES = 2 * MAX_DOCUMENT_BYTES
_TEXT = 256


class WorkflowNotFound(ProjectError):
    """No workflow record with this UUID belongs to the managed table."""


_TABLE = ManagedTable(table_id=TABLE_ID, table_name="Workflows", fields=FIELDS, field_ids=FIELD_IDS,
                      subject="Workflow", not_found=WorkflowNotFound,
                      limits=lambda: (MAX_WORKFLOWS, MAX_COLLECTION_BYTES, MAX_SNAPSHOT_BYTES),
                      limit_text="128 records or 4 MiB", max_cell_bytes=_MAX_CELL_BYTES)


def _text(value, what, limit=_TEXT):
    if type(value) is not str or not value or "\0" in value or len(value) > limit:
        raise ProjectError(f"Workflow {what} must be 1 to {limit} characters without NUL")
    return value


def _ident(value, what):
    if type(value) is not str or _IDENT.fullmatch(value) is None:
        raise ProjectError(f"Workflow {what} must be a lowercase identifier such as field_2")
    return value


def _step(step):
    if type(step) is not dict:
        raise ProjectError("Workflow steps must be objects")
    if any(key not in STEP_KEYS and not (key.startswith("x-") and len(key) <= 64) for key in step):
        raise ProjectError("Workflow steps allow id, kind, ref, label, inputs, parameters, after and x- keys")
    _ident(step.get("id"), "step id")
    _ident(step.get("kind"), "step kind")
    ref = step.get("ref")
    if type(ref) is not dict or not 1 <= len(ref) <= 8:
        raise ProjectError("Workflow step ref must be an object with 1 to 8 entries")
    for key, value in ref.items():
        _ident(key, "ref key")
        _text(value, "ref value", 128)
    if "label" in step:
        _text(step["label"], "step label")
    inputs = step.get("inputs", {})
    if type(inputs) is not dict or len(inputs) > 32:
        raise ProjectError("Workflow step inputs must be an object with at most 32 ports")
    for port, link in inputs.items():
        _ident(port, "input port")
        if type(link) is not dict or set(link) != {"from"} or type(link["from"]) is not str or \
                _PORT_REF.fullmatch(link["from"]) is None:
            raise ProjectError('Workflow inputs must be exactly {"from": "step.port"}')
    parameters = step.get("parameters", {})
    if type(parameters) is not dict or len(parameters) > 64 or len(canonical_json(parameters)) > MAX_PARAMETERS_BYTES:
        raise ProjectError("Workflow step parameters must be an object of at most 64 entries and 64 KiB")
    for name in parameters:
        _ident(name, "parameter name")
    after = step.get("after", [])
    if type(after) is not list or len(after) > 64 or len(set(map(str, after))) != len(after):
        raise ProjectError("Workflow step after must list at most 64 distinct step ids")
    for identity in after:
        _ident(identity, "after step id")


def _document(value):
    value = clone(value, "Workflow")
    if type(value) is not dict or set(value) != {"format", "steps", "ui"}:
        raise ProjectError("Workflow document requires exactly format, steps and ui")
    if value["format"] != DOCUMENT_FORMAT:
        raise UnsupportedProjectFormat("Unsupported workflow document format")
    steps, ui = value["steps"], value["ui"]
    if type(steps) is not list or len(steps) > MAX_STEPS:
        raise ProjectError(f"Workflow steps must be a list of at most {MAX_STEPS} steps")
    for step in steps:
        _step(step)
    if type(ui) is not dict:
        raise ProjectError("Workflow ui must be an object")
    positions = ui.get("positions", {})
    if type(positions) is not dict or any(
            _IDENT.fullmatch(key) is None or type(point) is not list or len(point) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6 for v in point)
            for key, point in positions.items()):
        raise ProjectError("Workflow ui.positions maps step ids to finite [x, y] within 1e6")
    if len(canonical_json(value)) > MAX_DOCUMENT_BYTES:
        raise ProjectError("Workflow document exceeds 256 KiB")
    return value


def _require(db):
    _TABLE.require(db, "workflows")


def _record(db, identity, compatible, schema_error):
    entry = {"id": identity, "name": None, "format": None, "state": "invalid", "error": "", "document": None}
    try:
        entry["name"] = _valid_name(_TABLE.literal(db, identity, "name"), "Workflow")
    except ProjectError:
        pass
    try:
        value = _TABLE.literal(db, identity, "format")
        if type(value) is str and 0 < len(value.encode("utf-8")) <= 128 and "\0" not in value:
            entry["format"] = value
    except ProjectError:
        pass
    if not compatible:
        entry["error"] = schema_error
    elif _TABLE.indirect(db, identity):
        entry["error"] = "Workflow managed cells must be literals; undo or explicitly replace the formula/reference"
    elif entry["format"] is not None and entry["format"] != DOCUMENT_FORMAT:
        entry.update(state="unsupported", error="Unsupported workflow document format")
    else:
        try:
            if entry["name"] is None or entry["format"] != DOCUMENT_FORMAT:
                raise ProjectError("Workflow record has an invalid or missing name/format")
            entry["document"] = _document({"format": entry["format"],
                **{key: _TABLE.literal(db, identity, key) for key in ("steps", "ui")}})
            entry["state"] = "readable"
        except ProjectError as exc:
            entry["error"] = str(exc)
    return entry


class _Issues:
    def __init__(self):
        self.items, self.omitted = [], 0

    def add(self, code, step, path, message):
        if len(self.items) < MAX_ISSUES:
            self.items.append({"code": code, "step": step, "path": path, "message": message})
        else:
            self.omitted += 1


def _analysis_ports(graph):
    """(inputs, parameters, outputs) a saved analysis graph declares, plus bindings given by $param."""
    bindings, dynamic = [], []
    for node in graph.get("nodes", []):
        params = node.get("params") or {}
        if "binding" not in params:
            continue
        value = params["binding"]
        if type(value) is str:
            if value not in bindings:
                bindings.append(value)
        elif node.get("id") not in dynamic:
            dynamic.append(node.get("id"))
    parameters = [{"name": p["name"], "type": p["type"], "label": p.get("label"), "unit": p.get("unit"),
                   "default": p.get("default")} for p in graph.get("parameters", [])]
    outputs = list(graph.get("outputs", {}))
    return bindings, dynamic, parameters, outputs


def _resolve(db, step, model, templates, read_analysis):
    """Describe one step's referenced object and ports; issues are added by the caller."""
    kind, ref = step["kind"], step["ref"]
    summary = {"id": step["id"], "kind": kind, "name": None, "content_sha256": None, "file_count": None,
               "inputs": [], "outputs": [], "parameters": []}
    problem = None
    if kind not in KINDS:
        return summary, ("unknown_kind", f"Unknown step kind {kind!r}; this version knows {', '.join(KINDS)}")
    key = REF_KEYS[kind]
    if set(ref) != {key}:
        return summary, ("invalid_reference", f"A {kind} step references exactly {{{key!r}: ...}}")
    target = ref[key]
    if kind == "simulation":
        template = templates.get(target)
        if template is None:
            return summary, ("unknown_template", f"Simulation template {target!r} is not registered")
        summary.update(name=template.name, inputs=[{"name": "rows", "type": "rows", "required": True}],
                       outputs=[{"name": "files", "type": "files"}])
        return summary, None
    try:
        _id(target)
    except ProjectError:
        return summary, ("invalid_reference", f"The {key} reference must be a UUID")
    if kind == "table":
        table = model["tables"].get(target)
        if table is None or target in (TABLE_ID, analyses.TABLE_ID, files.TABLE_ID):
            return summary, ("missing_reference", "The referenced parameter table does not exist")
        summary.update(name=table["name"], outputs=[{"name": "rows", "type": "rows"}])
    elif kind == "files":
        row = db.execute("SELECT manifest FROM project_snapshots WHERE id=?", (target,)).fetchone() \
            if _version(db) >= 4 else None
        if row is None:
            return summary, ("missing_reference", "The referenced input snapshot does not exist")
        try:
            summary["file_count"] = len(json.loads(row[0])["files"])
        except (ValueError, KeyError, TypeError):
            problem = ("unreadable_reference", "The referenced input snapshot cannot be read")
        summary["outputs"] = [{"name": "files", "type": "files"}]
    else:
        entry = read_analysis(target)
        if entry is None:
            return summary, ("missing_reference", "The referenced saved analysis does not exist")
        summary["name"] = entry["name"]
        if entry["state"] != "readable":
            return summary, ("unreadable_reference", "The referenced saved analysis cannot be read: " + entry["error"])
        document = entry["document"]
        summary["content_sha256"] = entry["content_sha256"]
        bindings, dynamic, parameters, outputs = _analysis_ports(document["graph"])
        summary.update(inputs=[{"name": name, "type": "files", "required": True} for name in bindings],
                       outputs=[{"name": name, "type": "result"} for name in outputs], parameters=parameters)
        if dynamic:
            shown = ", ".join(map(str, dynamic[:5])) + (", ..." if len(dynamic) > 5 else "")
            problem = ("dynamic_binding", f"Nodes {shown} take their binding from a graph parameter; "
                       "workflows need literal binding names")
    return summary, problem


def _cycles(order, edges):
    """Step ids on a cycle (Tarjan SCC), in document order."""
    index, low, stack, on_stack, cyclic, counter = {}, {}, [], set(), set(), [0]
    for root in order:
        if root in index:
            continue
        work = [(root, iter(edges.get(root, ())))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(edges.get(child, ()))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                members = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    members.append(member)
                    if member == node:
                        break
                if len(members) > 1 or node in edges.get(node, ()):
                    cyclic.update(members)
    return [step for step in order if step in cyclic]


class Workflows:
    def __init__(self, store):
        self.store = store

    def list(self, *, offset=0, limit=50):
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Workflow pagination requires offset >= 0 and limit between 1 and 100")
        with self.store._connect() as db:
            _require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            _, compatible, error = _TABLE.schema(db)
            total = db.execute("SELECT count(*) FROM records WHERE table_id=?", (TABLE_ID,)).fetchone()[0]
            records = []
            for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?", (TABLE_ID, limit, offset)):
                entry = _record(db, row[0], compatible, error)
                del entry["document"]
                records.append(entry)
            return {"revision": revision, "table_id": TABLE_ID, "compatible": compatible, "error": error,
                    "offset": offset, "total": total, "workflows": records}

    def get(self, workflow_id):
        _id(workflow_id)
        with self.store._connect() as db:
            _require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (TABLE_ID, workflow_id)).fetchone() is None:
                raise WorkflowNotFound("Workflow document not found")
            _, compatible, error = _TABLE.schema(db)
            return {"revision": revision, "table_id": TABLE_ID, "compatible": compatible, "error": error,
                    "workflow": _record(db, workflow_id, compatible, error)}

    def create(self, name, document, *, workflow_id, expected_revision):
        return self._write(workflow_id, name, document, expected_revision, create=True)

    def update(self, workflow_id, name, document, *, expected_revision):
        return self._write(workflow_id, name, document, expected_revision, create=False)

    def _write(self, identity, name, document, revision, *, create):
        _id(identity)
        _expected_revision(revision)
        name, document = _valid_name(name, "Workflow"), _document(document)
        with self.store._connect(write=True) as db:
            _require(db)
            return _TABLE.write(self.store, db, identity, {"name": name, **document}, revision,
                                create=create, document_format=DOCUMENT_FORMAT)

    def choices(self):
        """What a step can reference now, for an editor: parameter tables (not the managed analysis,
        workflow or file-index tables), input snapshots (newest first), readable saved analyses and
        registered simulation templates. Read-only; nothing is evaluated or created."""
        from suan.workflows.templates import TEMPLATES  # Registered versions only; never loads project code.
        managed = {TABLE_ID, analyses.TABLE_ID, files.TABLE_ID}
        with self.store._connect() as db:
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            tables = [{"id": row["id"], "name": row["name"]}
                      for row in db.execute("SELECT id,name FROM tables ORDER BY rowid") if row["id"] not in managed]
            snapshots = []
            if _version(db) >= 4:
                for row in db.execute("SELECT id,created_at,manifest FROM project_snapshots ORDER BY rowid DESC LIMIT ?",
                                      (MAX_CHOICE_SNAPSHOTS,)):
                    try:
                        count = len(json.loads(row["manifest"])["files"])
                    except (ValueError, KeyError, TypeError):
                        count = None
                    snapshots.append({"id": row["id"], "created_at": row["created_at"], "file_count": count})
            readable = []
            _, compatible, error = analyses._schema(db)
            for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid", (analyses.TABLE_ID,)):
                entry = analyses._record(db, row[0], compatible, error)
                if entry["state"] == "readable":
                    readable.append({"id": entry["id"], "name": entry["name"]})
        return {"revision": revision, "tables": tables[:MAX_CHOICE_TABLES], "omitted_tables": max(0, len(tables) - MAX_CHOICE_TABLES),
                "snapshots": snapshots, "analyses": readable,
                "templates": [{"id": template.id, "name": template.name, "table_id": template.table_id}
                              for template in TEMPLATES.values()]}

    def validate(self, document):
        """Resolve a (possibly unsaved) document against the current project, read-only.

        Returns {revision, ok, issues, omitted_issues, steps}: one summary per step in document order
        (referenced object name, analysis content hash, typed ports and graph parameters)."""
        document = _document(document)
        from suan.workflows.templates import TEMPLATES  # Registered versions only; never loads project code.
        with self.store._connect() as db:
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            model = {"tables": {row["id"]: {"name": row["name"], "fields": {}}
                                for row in db.execute("SELECT id,name FROM tables")}}
            for row in db.execute("SELECT id,table_id,type,unit FROM fields"):
                model["tables"][row["table_id"]]["fields"][row["id"]] = {"type": row["type"], "unit": row["unit"]}
            steps, issues = document["steps"], _Issues()
            _, compatible, error = analyses._schema(db)
            read = {}

            def read_analysis(identity):
                """Each referenced analysis is decoded once per validation."""
                if identity not in read:
                    if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?",
                                  (analyses.TABLE_ID, identity)).fetchone() is None:
                        read[identity] = None
                    else:
                        entry = analyses._record(db, identity, compatible, error)
                        if entry["state"] == "readable":
                            entry["content_sha256"] = hashlib.sha256(canonical_json(entry["document"])).hexdigest()
                        read[identity] = entry
                return read[identity]

            counts = {}
            for step in steps:
                counts[step["id"]] = counts.get(step["id"], 0) + 1
            summaries = []
            for i, step in enumerate(steps):
                summary, problem = _resolve(db, step, model, TEMPLATES, read_analysis)
                summaries.append(summary)
                if counts[step["id"]] > 1:
                    issues.add("duplicate_step", step["id"], f"steps/{i}/id", "Step id is used more than once")
                if problem:
                    issues.add(problem[0], step["id"], f"steps/{i}/ref", problem[1])
        unique = {step["id"]: (i, summaries[i]) for i, step in enumerate(steps) if counts[step["id"]] == 1}
        table_fields = {}
        for step in steps:
            if step["kind"] == "table" and step["id"] in unique and set(step["ref"]) == {"table"}:
                table_fields.update(model["tables"].get(step["ref"]["table"], {}).get("fields", {}))
        edges = {}
        for i, step in enumerate(steps):
            summary, here = summaries[i], step["id"]
            known = summary["inputs"] or summary["outputs"]
            declared = {port["name"]: port for port in summary["inputs"]}
            for port, link in step.get("inputs", {}).items():
                path = f"steps/{i}/inputs/{port}"
                if known and port not in declared:
                    issues.add("unknown_port", here, path, f"This step has no input {port!r}")
                    continue
                source, out = _PORT_REF.fullmatch(link["from"]).groups()
                if counts.get(source, 0) == 0:
                    issues.add("missing_step", here, path, f"No step {source!r}")
                    continue
                if counts[source] > 1:
                    issues.add("ambiguous_step", here, path, f"Step id {source!r} is used more than once")
                    continue
                edges.setdefault(source, set()).add(here)
                origin = unique[source][1]
                outputs = {p["name"]: p for p in origin["outputs"]}
                if not outputs:
                    continue  # The source step's own problem is already reported.
                if out not in outputs:
                    issues.add("missing_port", here, path, f"Step {source!r} has no output {out!r}")
                elif port in declared and outputs[out]["type"] != declared[port]["type"]:
                    issues.add("type_mismatch", here, path,
                               f"{source}.{out} gives {outputs[out]['type']}, input {port!r} takes {declared[port]['type']}")
                elif step["kind"] == "simulation" and port == "rows":
                    template = TEMPLATES.get(step["ref"].get("template"))
                    source_step = steps[unique[source][0]]
                    if template is not None and source_step["ref"].get("table") != template.table_id:
                        issues.add("template_table", here, path,
                                   f"Template {template.id} runs rows of its own case table only")
            for port in declared.values():
                if port["required"] and port["name"] not in step.get("inputs", {}):
                    issues.add("missing_input", here, f"steps/{i}/inputs/{port['name']}",
                               f"Input {port['name']!r} needs a link before this workflow can run")
            graph_parameters = {p["name"]: p for p in summary["parameters"]}
            for name, value in step.get("parameters", {}).items():
                path = f"steps/{i}/parameters/{name}"
                parameter = graph_parameters.get(name)
                if parameter is None:
                    if step["kind"] == "analysis" and not summary["outputs"]:
                        continue  # Unreadable analysis, already reported.
                    issues.add("unknown_parameter", here, path,
                               "Only parameters a saved analysis declares can be set" if step["kind"] == "analysis"
                               else f"A {step['kind']} step takes no parameters")
                    continue
                if type(value) is not dict or set(value) != {"$field"}:
                    continue  # Literal values are checked by graph validation when a run is prepared.
                field_id = value["$field"]
                field = table_fields.get(field_id) if type(field_id) is str else None
                if field is None:
                    issues.add("field_not_in_workflow", here, path,
                               "The $field reference must name a field of a parameter table step in this workflow")
                elif parameter["type"] not in FIELD_PARAMETER_TYPES.get(field["type"], ()):
                    issues.add("parameter_type", here, path,
                               f"A {field['type']} field cannot feed parameter {name!r} of type {parameter['type']}")
                elif parameter.get("unit") and field["unit"] != parameter["unit"]:
                    issues.add("unit_mismatch", here, path,
                               f"Parameter {name!r} is in {parameter['unit']}, the field is in {field['unit'] or 'no unit'}")
            for j, before in enumerate(step.get("after", [])):
                path = f"steps/{i}/after/{j}"
                if counts.get(before, 0) == 0:
                    issues.add("missing_step", here, path, f"No step {before!r}")
                elif counts[before] > 1:
                    issues.add("ambiguous_step", here, path, f"Step id {before!r} is used more than once")
                else:
                    edges.setdefault(before, set()).add(here)
        for step in _cycles([s["id"] for s in steps if s["id"] in unique], edges):
            issues.add("cycle", step, f"steps/{unique[step][0]}", "Step is on a dependency cycle")
        return {"revision": revision, "ok": not issues.items and not issues.omitted, "issues": issues.items,
                "omitted_issues": issues.omitted, "steps": summaries}
