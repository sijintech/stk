"""Per-row workflow runs (project format 10): frozen plans and an append-only, hash-chained log.

Preparing a run freezes the workflow, the selected rows with every parameter value the run uses,
the referenced saved analyses (documents and content hashes), input snapshots and templates, and
the execution order. Each step x row is a task; every execution of a task is a numbered attempt
over that same frozen plan, and only the latest attempt can finish (a late, stale attempt is
refused). Nothing here executes a step: suan/desktop_bridge/workflow_runs.py does, explicitly.
Plans and events never change the editable revision or enter undo. Design: docs/design/workflow-runs.md.
"""
from datetime import datetime, timezone
import hashlib
import json
import math

from suan.graph.schema import canonical_json

from . import analyses, workflows
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id, _version
from . import archive


MAX_ROWS = 100
MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_EVENT_BYTES = 64 * 1024
RUN_EVENTS = ("prepared", "started", "cancel_requested", "stopped")
TASK_TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")
TASK_EVENTS = ("running", *TASK_TERMINAL)
PROGRESS_STAGES = ("preparing", "prepared", "submitted", "queued", "running", "collecting", "adopted")
RESULTS_DIRECTORY = "results/workflow-runs"


class WorkflowRunNotFound(ProjectError):
    """The selected workflow run does not exist."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _require(db):
    if _version(db) < 10:
        raise UnsupportedProjectFormat("Upgrade this project to format 10 before preparing or reading workflow runs")


def _pack(value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProjectError(f"Invalid bounded workflow run JSON: {exc}") from None
    if len(raw.encode("utf-8")) > limit:
        raise ProjectError("Workflow run JSON exceeds its bounded byte limit")
    return raw


def _hash(value, limit=MAX_PLAN_BYTES):
    return hashlib.sha256(_pack(value, limit).encode("utf-8")).hexdigest()


def _error(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"code", "message"} or type(value["code"]) is not str
            or not workflows._IDENT.fullmatch(value["code"]) or type(value["message"]) is not str or not value["message"]):
        raise ProjectError("A workflow run error is {code, message}")
    return {"code": value["code"], "message": value["message"][:2048]}


def _order(steps):
    """Steps other than parameter tables in dependency order (links and `after`), ties in document order."""
    ids = [step["id"] for step in steps]
    needs = {step["id"]: set() for step in steps}
    for step in steps:
        for link in step.get("inputs", {}).values():
            needs[step["id"]].add(link["from"].split(".", 1)[0])
        needs[step["id"]].update(step.get("after", []))
    done, order = set(), []
    while len(done) < len(ids):
        ready = [identity for identity in ids if identity not in done and needs[identity] <= done]
        if not ready:
            raise ProjectError("Workflow steps form a cycle")
        done.add(ready[0])
        order.append(ready[0])
    kinds = {step["id"]: step["kind"] for step in steps}
    return [identity for identity in order if kinds[identity] != "table"]


def _value(value, row_values, what):
    """A step parameter for one row: a literal, or the row's frozen value of a $field."""
    if type(value) is dict and set(value) == {"$field"}:
        if value["$field"] not in row_values:
            raise ProjectError(f"{what} takes a field the run did not freeze")
        return row_values[value["$field"]]
    return value


class WorkflowRuns:
    def __init__(self, store):
        self.store = store

    # ---- preparation ----

    def prepare(self, workflow_id, rows, *, run_id, expected_revision, simulation=None):
        """Freeze one run of a saved workflow over explicit rows of its parameter table (1-100).

        ``simulation`` ({connection, connection_identity, options}) is where remote simulation steps
        (``muferro/1``) run: a saved Runtime profile, its endpoint fingerprint and resource options."""
        for identity in (workflow_id, run_id):
            _id(identity)
        _expected_revision(expected_revision)
        if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS or len(set(map(str, rows))) != len(rows):
            raise ProjectError(f"A workflow run takes 1 to {MAX_ROWS} distinct row IDs")
        for row in rows:
            _id(row)
        if simulation is not None and (type(simulation) is not dict or set(simulation) != {"connection", "connection_identity", "options"}
                                       or type(simulation["connection"]) is not str or not 1 <= len(simulation["connection"]) <= 256
                                       or type(simulation["connection_identity"]) is not str or len(simulation["connection_identity"]) > 256
                                       or type(simulation["options"]) is not dict):
            raise ProjectError("A run's simulation settings are {connection, connection_identity, options}")
        request = {"workflow_id": workflow_id, "rows": rows, "expected_revision": expected_revision}
        if simulation is not None:
            request["simulation"] = simulation
        request_hash = _hash(request)
        with self.store._connect() as db:
            _require(db)
            existing = db.execute("SELECT request_sha256 FROM workflow_run_plans WHERE id=?", (run_id,)).fetchone()
        if existing is not None:
            if existing[0] != request_hash:
                raise RevisionConflict("Workflow run UUID is already used by a different preparation request")
            return self.get(run_id)
        plan = self._plan(workflow_id, rows, run_id, expected_revision, simulation)
        with self.store._connect(write=True) as db:
            _require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            if db.execute("SELECT 1 FROM workflow_run_plans WHERE id=?", (run_id,)).fetchone() is not None:
                raise RevisionConflict("Workflow run UUID is already used")
            db.execute("INSERT INTO workflow_run_plans VALUES (?,?,?,?,?,?)",
                       (run_id, self.store._project_id, workflow_id, _pack(plan, MAX_PLAN_BYTES), request_hash, _hash(plan)))
            self._append(db, run_id, "", "", 0, "prepared", {"at": plan["created_at"]})
        return self.get(run_id)

    def _plan(self, workflow_id, rows, run_id, revision, simulation=None):
        from suan.workflows import muferro
        from suan.workflows.templates import workflow_templates  # Registered versions only.
        saved = self.store.workflows.get(workflow_id)
        record = saved["workflow"]
        if saved["revision"] != revision:
            raise RevisionConflict(f"Expected revision {revision}, current revision is {saved['revision']}")
        if record["state"] != "readable":
            raise ProjectError("The workflow cannot be read: " + record["error"])
        document = record["document"]
        checked = self.store.workflows.validate(document)
        if checked["revision"] != revision:
            raise RevisionConflict(f"Expected revision {revision}, current revision is {checked['revision']}")
        if not checked["ok"]:
            codes = ", ".join(sorted({issue["code"] for issue in checked["issues"]}))
            raise ProjectError(f"The workflow has problems ({codes}); fix them before running it")
        model = self.store.snapshot()
        if model["project"]["revision"] != revision:
            raise RevisionConflict(f"Expected revision {revision}, current revision is {model['project']['revision']}")
        steps = document["steps"]
        tables = [step for step in steps if step["kind"] == "table"]
        if len(tables) != 1:
            raise ProjectError("A workflow run needs exactly one parameter table step to take its rows from")
        templates = workflow_templates()
        remote = [step for step in steps if step["kind"] == "simulation" and getattr(templates[step["ref"]["template"]], "remote", False)]
        for step in steps:
            # Whatever rows are chosen, a step that cannot run here refuses the whole run.
            template = templates[step["ref"]["template"]] if step["kind"] == "simulation" else None
            if template is not None and not getattr(template, "local", False) and not getattr(template, "remote", False):
                raise ProjectError(f"Per-row runs of {step['ref']['template']} are not supported yet; use simulation batches")
        if remote and simulation is None:
            raise ProjectError("Choose where to run: this workflow's simulation steps need a Runtime connection")
        if remote and simulation["connection"].startswith("hub:"):
            raise ProjectError("Workflow runs submit MuFerro through direct or SSH Runtime connections; Hub nodes are not supported")
        table_id = tables[0]["ref"]["table"]
        table = next(table for table in model["tables"] if table["id"] == table_id)
        records = {entry["id"]: (number, entry) for number, entry in enumerate(table["records"], start=1)}
        fields = {value["$field"] for step in steps for value in step.get("parameters", {}).values()
                  if type(value) is dict and set(value) == {"$field"}}
        if remote:
            fields |= set(muferro.FIELD_IDS.values())  # a MuFerro step takes every case field of its row
        frozen_rows = []
        for row in rows:
            if row not in records:
                raise ProjectError("Every row of a workflow run must belong to its parameter table")
            number, entry = records[row]
            for field in fields:
                if entry.get("evaluations", {}).get(field, {"state": "ok"})["state"] != "ok":
                    raise ProjectError(f"Row {number} has a formula error in a field this workflow uses")
            frozen_rows.append({"id": row, "number": number, "values": {field: entry["values"].get(field) for field in sorted(fields)}})
        frozen_steps, parameters = {}, {}
        for step in steps:
            kind, identity = step["kind"], step["id"]
            if kind == "simulation" and getattr(templates[step["ref"]["template"]], "remote", False):
                template = templates[step["ref"]["template"]]
                frozen_steps[identity] = {"kind": kind, "template": template.id, "outputs": [], "remote": True}
                parameters[identity] = {}
                for row in frozen_rows:
                    try:
                        values, _, _ = muferro.describe_case(model, row["id"], simulation["connection"], simulation["options"])
                    except (ValueError, TypeError) as exc:
                        raise ProjectError(f"Row {row['number']}: {exc}") from None
                    parameters[identity][row["id"]] = values
            elif kind == "simulation":
                template = templates[step["ref"]["template"]]
                frozen_steps[identity] = {"kind": kind, "template": template.id, "outputs": list(template.outputs)}
                declared = {item["name"]: item for item in template.parameters}
                parameters[identity] = {}
                for row in frozen_rows:
                    values = {}
                    for name, item in declared.items():
                        if name in step.get("parameters", {}):
                            values[name] = _value(step["parameters"][name], row["values"], f"Step {identity}")
                        elif "default" in item:
                            values[name] = item["default"]
                        else:
                            raise ProjectError(f"Step {identity} needs a value for template parameter {name}")
                        if item["type"] in ("number", "integer") and (type(values[name]) not in (int, float) or
                                                                     not math.isfinite(values[name])):
                            raise ProjectError(f"Row {row['number']}: step {identity} parameter {name} is not a number")
                    parameters[identity][row["id"]] = values
            elif kind == "files":
                snapshot = self.store.snapshots.get(step["ref"]["snapshot"])
                names = {}
                for file in snapshot["manifest"]["files"]:
                    names.setdefault(file["name"], []).append(file["record_id"])
                frozen_steps[identity] = {"kind": kind, "snapshot_id": snapshot["id"], "sha256": snapshot["sha256"],
                                          "files": {name: ids[0] for name, ids in names.items() if len(ids) == 1},
                                          "duplicates": sorted(name for name, ids in names.items() if len(ids) > 1)}
            elif kind == "analysis":
                analysis = self.store.analyses.get(step["ref"]["analysis"])["analysis"]
                sources = {link["from"].split(".", 1)[0] for link in step.get("inputs", {}).values()}
                if len(sources) > 1:
                    raise ProjectError(f"Step {identity}: all inputs of an analysis must come from one simulation or files step")
                frozen_steps[identity] = {
                    "kind": kind, "analysis_id": analysis["id"], "name": analysis["name"], "document": analysis["document"],
                    "sha256": hashlib.sha256(canonical_json(analysis["document"])).hexdigest(),
                    "source": next(iter(sources), None), "bindings": sorted(step.get("inputs", {}))}
                parameters[identity] = {row["id"]: {name: _value(value, row["values"], f"Step {identity}")
                                                    for name, value in step.get("parameters", {}).items()}
                                        for row in frozen_rows}
        for identity, frozen in frozen_steps.items():
            if frozen["kind"] == "analysis" and frozen["source"] and frozen_steps.get(frozen["source"], {}).get("duplicates"):
                raise ProjectError(f"Step {identity}: the input files of step {frozen['source']} repeat the names "
                                   + ", ".join(frozen_steps[frozen["source"]]["duplicates"][:5]))
        plan = {"id": run_id, "project_id": self.store._project_id, "workflow_id": workflow_id,
                "workflow_name": record["name"], "document": document,
                "document_sha256": hashlib.sha256(canonical_json(document)).hexdigest(),
                "source_revision": revision, "created_at": _now(), "table_id": table_id, "rows": frozen_rows,
                "order": _order(steps), "steps": frozen_steps, "parameters": parameters,
                "directory": f"{RESULTS_DIRECTORY}/{run_id}"}
        if remote:
            plan["simulation"] = simulation
        return plan

    # ---- the log ----

    def _append(self, db, run_id, step, row, attempt, status, payload):
        previous = db.execute("SELECT sha256 FROM workflow_run_events WHERE run_id=? ORDER BY id DESC LIMIT 1",
                              (run_id,)).fetchone()
        previous_hash = previous[0] if previous else ""
        packed = _pack(payload, MAX_EVENT_BYTES)
        digest = _hash({"run_id": run_id, "step": step, "row": row, "attempt": attempt, "status": status,
                        "payload": payload, "previous_sha256": previous_hash}, MAX_EVENT_BYTES + 1024)
        db.execute("INSERT INTO workflow_run_events(run_id,step,row,attempt,status,payload,previous_sha256,sha256) "
                   "VALUES (?,?,?,?,?,?,?,?)", (run_id, step, row, attempt, status, packed, previous_hash, digest))

    def _read(self, db, run_id):
        _id(run_id)
        _require(db)
        row = db.execute("SELECT * FROM workflow_run_plans WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise WorkflowRunNotFound("Workflow run not found")
        plan = json.loads(row["payload"])
        if _hash(plan) != row["sha256"] or plan.get("id") != run_id or plan.get("project_id") != self.store._project_id:
            raise ProjectError("Invalid frozen workflow run plan identity or checksum")
        events, previous = [], ""
        for event in db.execute("SELECT * FROM workflow_run_events WHERE run_id=? ORDER BY id", (run_id,)):
            payload = json.loads(event["payload"])
            digest = _hash({"run_id": run_id, "step": event["step"], "row": event["row"], "attempt": event["attempt"],
                            "status": event["status"], "payload": payload, "previous_sha256": previous}, MAX_EVENT_BYTES + 1024)
            if event["previous_sha256"] != previous or event["sha256"] != digest:
                raise ProjectError("The workflow run log is not an unbroken chain")
            previous = digest
            events.append({"step": event["step"], "row": event["row"], "attempt": event["attempt"],
                           "status": event["status"], **payload})
        return plan, events

    @staticmethod
    def _state(plan, events):
        run_events = [event for event in events if event["step"] == ""]
        last = run_events[-1] if run_events else {"status": "prepared"}
        status = {"prepared": "prepared", "started": "running", "cancel_requested": "cancel_requested",
                  "stopped": "stopped"}[last["status"]]
        started = next((event for event in reversed(run_events) if event["status"] == "started"), {})
        executor = started.get("executor_id")
        stop_error = last.get("error") if last["status"] == "stopped" else None
        tasks = {}
        for event in events:
            if event["step"] == "":
                continue
            key = (event["step"], event["row"])
            task = tasks.setdefault(key, {"step": event["step"], "row": event["row"], "attempt": 0, "status": "pending",
                                          "produced": None, "error": None, "updated_at": None, "progress": None})
            if event["status"] == "running" and "progress" in event:
                # Remote work of a running attempt (W5), stored as a further "running" event of that attempt
                # (the format-10 table allows no other status); kept across attempts so a later one can adopt it.
                task.update(progress={"attempt": event["attempt"], **event["progress"]}, updated_at=event.get("at"))
                continue
            task.update(attempt=event["attempt"], status=event["status"], updated_at=event.get("at"),
                        produced=event.get("produced"), error=event.get("error"))
        listed = []
        for row in plan["rows"]:
            for step in plan["order"]:
                listed.append(tasks.get((step, row["id"]), {"step": step, "row": row["id"], "attempt": 0, "status": "pending",
                                                             "produced": None, "error": None, "updated_at": None,
                                                             "progress": None}))
        counts = {}
        for task in listed:
            counts[task["status"]] = counts.get(task["status"], 0) + 1
        return {"status": status, "executor_id": executor if status in ("running", "cancel_requested") else None,
                "owner": started.get("owner") if status in ("running", "cancel_requested") else None,
                "stop_error": stop_error, "tasks": listed, "counts": counts,
                "complete": counts.get("succeeded", 0) == len(listed)}

    def get(self, run_id):
        with self.store._connect() as db:
            plan, events = self._read(db, run_id)
        return {**plan, "plan_sha256": _hash(plan), **self._state(plan, events)}

    def list(self, *, offset=0, limit=50, workflow_id=None, archived=None):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Workflow run pagination requires offset >= 0 and limit between 1 and 100")
        if workflow_id is not None:
            _id(workflow_id)
        with self.store._connect() as db:
            _require(db)
            where, extra = archive.where(db, "workflow_run", archived, existing="workflow_id=?" if workflow_id else "")
            query = "SELECT id FROM workflow_run_plans" + where + " ORDER BY rowid DESC LIMIT ? OFFSET ?"
            ids = [row[0] for row in db.execute(query, ((workflow_id,) if workflow_id else ()) + tuple(extra) + (limit + 1, offset))]
            runs = []
            for identity in ids[:limit]:
                plan, events = self._read(db, identity)
                state = self._state(plan, events)
                runs.append({"id": identity, "workflow_id": plan["workflow_id"], "workflow_name": plan["workflow_name"],
                             "created_at": plan["created_at"], "source_revision": plan["source_revision"],
                             "rows": len(plan["rows"]), "status": state["status"], "counts": state["counts"],
                             "complete": state["complete"]})
        return {"runs": runs, "next_offset": offset + limit if len(ids) > limit else None}

    # ---- staleness (W4c) ----

    def stale(self, run_id):
        """Which rows' results no longer match the current definitions, and why. Read-only.

        Per executed step and row: ``step_changed`` (the step's definition, labels aside),
        ``analysis_changed`` / ``analysis_missing``, ``template_unavailable``, ``value_changed`` (a field the
        step takes from the row, with before/after), ``value_error``, ``row_removed``, ``workflow_missing``,
        and ``upstream_changed`` when an earlier step of the row is stale. Old results stay as they are."""
        from suan.workflows.templates import workflow_templates
        plan = self.get(run_id)
        model = self.store.snapshot()
        try:
            current = self.store.workflows.get(plan["workflow_id"])["workflow"]
            current_steps = ({step["id"]: step for step in current["document"]["steps"]}
                             if current["state"] == "readable" else None)
        except workflows.WorkflowNotFound:
            current_steps = None
        frozen_steps = {step["id"]: step for step in plan["document"]["steps"]}
        table = next((t for t in model["tables"] if t["id"] == plan["table_id"]), None)
        records = {record["id"]: record for record in table["records"]} if table else {}
        names = {field["id"]: field["name"] for field in table["fields"]} if table else {}
        templates = workflow_templates()
        hashes = {}

        def analysis_hash(identity):
            if identity not in hashes:
                try:
                    entry = self.store.analyses.get(identity)["analysis"]
                    hashes[identity] = (hashlib.sha256(canonical_json(entry["document"])).hexdigest()
                                        if entry["state"] == "readable" else None)
                except analyses.AnalysisNotFound:
                    hashes[identity] = None
            return hashes[identity]

        def comparable(step):
            return {key: value for key, value in step.items() if key != "label"}

        def fields_of(step):
            if plan["steps"].get(step["id"], {}).get("remote"):
                from suan.workflows import muferro
                return list(muferro.FIELD_IDS.values())  # every case field of the row
            return [value["$field"] for value in step.get("parameters", {}).values()
                    if type(value) is dict and set(value) == {"$field"}]

        step_reasons = {}
        for identity in plan["order"]:
            frozen = frozen_steps[identity]
            reasons = []
            if current_steps is None:
                reasons.append({"code": "workflow_missing"})
            elif identity not in current_steps or comparable(current_steps[identity]) != comparable(frozen):
                reasons.append({"code": "step_changed"})
            kind = plan["steps"][identity]["kind"]
            if kind == "analysis":
                now = analysis_hash(plan["steps"][identity]["analysis_id"])
                if now is None:
                    reasons.append({"code": "analysis_missing"})
                elif now != plan["steps"][identity]["sha256"]:
                    reasons.append({"code": "analysis_changed"})
            if kind == "simulation" and plan["steps"][identity]["template"] not in templates:
                reasons.append({"code": "template_unavailable"})
            step_reasons[identity] = reasons
        rows = []
        needs = {}
        for step in plan["document"]["steps"]:
            needs[step["id"]] = ({link["from"].split(".", 1)[0] for link in step.get("inputs", {}).values()}
                                 | set(step.get("after", []))) & set(plan["order"])
        for row in plan["rows"]:
            record = records.get(row["id"])
            steps = {}
            for identity in plan["order"]:
                reasons = list(step_reasons[identity])
                if record is None:
                    reasons.append({"code": "row_removed"})
                else:
                    for field in fields_of(frozen_steps[identity]):
                        state = record.get("evaluations", {}).get(field, {"state": "ok"})["state"]
                        if state != "ok":
                            reasons.append({"code": "value_error", "field": field, "name": names.get(field, field)})
                            continue
                        before, after = row["values"].get(field), record["values"].get(field)
                        if canonical_json(before) != canonical_json(after):
                            reasons.append({"code": "value_changed", "field": field, "name": names.get(field, field),
                                            "before": before, "after": after})
                for upstream in sorted(needs.get(identity, ())):
                    if steps.get(upstream):
                        reasons.append({"code": "upstream_changed", "step": upstream})
                steps[identity] = reasons
            rows.append({"id": row["id"], "number": row["number"], "stale": any(steps.values()), "steps": steps})
        return {"run_id": run_id, "revision": model["project"]["revision"], "rows": rows,
                "stale_rows": [row["id"] for row in rows if row["stale"]]}

    # ---- execution bookkeeping (used by the explicit executor) ----

    def start(self, run_id, *, executor_id, owner=None):
        """Claim a prepared or stopped run for one executor; a running run is refused (see interrupt).
        ``owner`` ({host, pid}) identifies the service process, so another one can tell whether it still runs."""
        _id(executor_id)
        self.store.archive.require_active("workflow_run", run_id, "start or retry it")
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            if state["status"] in ("running", "cancel_requested"):
                raise RevisionConflict("This workflow run already has an executor")
            if state["complete"]:
                raise ProjectError("Every task of this workflow run has succeeded")
            payload = {"at": _now(), "executor_id": executor_id}
            if owner is not None:
                payload["owner"] = {"host": str(owner["host"])[:255], "pid": int(owner["pid"])}
            self._append(db, run_id, "", "", 0, "started", payload)
        return self.get(run_id)

    def request_cancel(self, run_id):
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            if self._state(plan, events)["status"] == "running":
                self._append(db, run_id, "", "", 0, "cancel_requested", {"at": _now()})
        return self.get(run_id)

    def stop(self, run_id, *, executor_id, error=None):
        """Release the run; ``error`` says why it stopped unexpectedly (shown with the run)."""
        error = _error(error)
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            if state["status"] not in ("running", "cancel_requested") or state["executor_id"] != executor_id:
                raise RevisionConflict("This executor does not own the workflow run")
            self._append(db, run_id, "", "", 0, "stopped", {"at": _now(), "executor_id": executor_id, "error": error})
        return self.get(run_id)

    def begin_attempt(self, run_id, step, row, *, executor_id):
        """Start the next numbered attempt of one task; returns its number."""
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            if state["status"] != "running" or state["executor_id"] != executor_id:
                raise RevisionConflict("This executor does not own a running workflow run")
            task = next((t for t in state["tasks"] if t["step"] == step and t["row"] == row), None)
            if task is None:
                raise ProjectError("No such task in this workflow run")
            if task["status"] in ("running", "succeeded"):
                raise RevisionConflict(f"Task {step} of this row is already {task['status']}")
            attempt = task["attempt"] + 1
            self._append(db, run_id, step, row, attempt, "running", {"at": _now(), "executor_id": executor_id})
        return attempt

    def finish_attempt(self, run_id, step, row, attempt, status, *, executor_id, produced=None, error=None):
        """Finish an attempt; only the latest, still running attempt of the task can finish."""
        if status not in TASK_TERMINAL:
            raise ProjectError("An attempt finishes as succeeded, failed, cancelled or interrupted")
        error = _error(error)
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            task = next((t for t in state["tasks"] if t["step"] == step and t["row"] == row), None)
            if task is None or task["attempt"] != attempt or task["status"] != "running":
                raise RevisionConflict("A stale or finished attempt cannot finish this task")
            if state["executor_id"] != executor_id:
                raise RevisionConflict("This executor does not own the workflow run")
            self._append(db, run_id, step, row, attempt, status,
                         {"at": _now(), "executor_id": executor_id, "produced": produced, "error": error})
        return self.get(run_id)

    def progress_attempt(self, run_id, step, row, attempt, *, executor_id, progress):
        """Record remote work of the latest running attempt (W5): its simulation run, Runtime task and stage.
        Not a result: the task stays running, and a later attempt may adopt the same remote work."""
        if (type(progress) is not dict or progress.get("stage") not in PROGRESS_STAGES
                or set(progress) - {"stage", "simulation_run_id", "task_id", "state", "adopted_from"}):
            raise ProjectError("Workflow run progress is {stage, simulation_run_id?, task_id?, state?, adopted_from?}")
        for key in ("simulation_run_id", "task_id", "state"):
            if key in progress and (type(progress[key]) is not str or len(progress[key]) > 128):
                raise ProjectError(f"Workflow run progress {key} must be a short string")
        if "adopted_from" in progress and type(progress["adopted_from"]) is not int:
            raise ProjectError("Workflow run progress adopted_from is an attempt number")
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            task = next((t for t in state["tasks"] if t["step"] == step and t["row"] == row), None)
            if task is None or task["attempt"] != attempt or task["status"] != "running":
                raise RevisionConflict("Only the running attempt of a task can record progress")
            if state["executor_id"] != executor_id:
                raise RevisionConflict("This executor does not own the workflow run")
            self._append(db, run_id, step, row, attempt, "running", {"at": _now(), "executor_id": executor_id, "progress": progress})
        return self.get(run_id)

    def interrupt(self, run_id):
        """After an executor vanished (service restart): running attempts become interrupted and the run
        stops, so it can be started again (only unfinished tasks run)."""
        with self.store._connect(write=True) as db:
            plan, events = self._read(db, run_id)
            state = self._state(plan, events)
            if state["status"] not in ("running", "cancel_requested"):
                return self.get(run_id)
            for task in state["tasks"]:
                if task["status"] == "running":
                    self._append(db, run_id, task["step"], task["row"], task["attempt"], "interrupted",
                                 {"at": _now(), "error": {"code": "interrupted", "message": "The executor stopped before this attempt finished"}})
            self._append(db, run_id, "", "", 0, "stopped", {"at": _now(), "executor_id": state["executor_id"]})
        return self.get(run_id)
