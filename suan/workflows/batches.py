"""Explicit bounded batches over existing project runs, with durable per-row outcomes.

The content-addressed intent fixes membership, parameter values and template version. Preparing
is separate from submission. No scheduler, background replay or automatic task retry lives here.
"""
from copy import deepcopy
import hashlib
import re
from uuid import NAMESPACE_URL, uuid5

from .muferro import _canonical, _cells, _create_table, _revision, _table
from .templates import TEMPLATES, template


def identity(name):
    return str(uuid5(NAMESPACE_URL, "urn:stk:workflow:batches:1:" + name))


TABLE_ID = identity("table")
FIELDS = {"name": ("Batch / 批次", "text", None),
          "intent": ("Frozen selection / 冻结范围", "json", None),
          "outcomes": ("Last operations / 最近操作", "json", None)}
FIELD_IDS = {name: identity(name) for name in FIELDS}


def _identity(intent):
    encoded = _canonical(intent).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise ValueError("Batch intent exceeds 1 MiB")
    return identity(hashlib.sha256(encoded).hexdigest())


def _ids(values):
    if (not isinstance(values, list) or not 1 <= len(values) <= 100
            or any(not isinstance(v, str) for v in values) or len(set(values)) != len(values)):
        raise ValueError("Choose 1–100 distinct record IDs")
    return values


def _batch(model, batch_id):
    table = _table(model, TABLE_ID, FIELDS, FIELD_IDS)
    row = next((r for r in table["records"] if r["id"] == batch_id), None) if table else None
    if row is None:
        raise ValueError("Saved batch not found")
    intent = row["values"].get(FIELD_IDS["intent"])
    if (not isinstance(intent, dict) or _identity(intent) != batch_id or intent.get("format") != 1
            or intent.get("project_id") != model["project"]["id"]):
        raise ValueError("Batch intent changed; create a new batch from the desired rows")
    template(intent["template"])
    _ids([e["record_id"] for e in intent["entries"]])
    outcomes = row["values"].get(FIELD_IDS["outcomes"], {})
    if not isinstance(outcomes, dict):
        raise ValueError("Batch operation outcomes must be an object")
    return intent, outcomes, row["values"].get(FIELD_IDS["name"], "")


def _plans(project, intent):
    labels = {entry["label"] for entry in intent["entries"]}
    result, offset = {}, 0
    while True:
        page = project.runs.list(offset=offset)
        for run in page["runs"]:
            if run["label"] in labels:
                if run["label"] in result:
                    raise ValueError("Multiple runs match one batch member; inspect Runs before continuing")
                # A user-created label alone is insufficient to authorize acting on a run.
                saved = project.runs.get(run["id"])["plan"]
                entry = next(e for e in intent["entries"] if e["label"] == run["label"])
                adapter = template(intent["template"])
                if (saved["connection"] != intent["connection"] or saved["parameters"]["table_id"] != adapter.table_id
                        or saved["parameters"]["record_id"] != entry["record_id"]):
                    raise ValueError("Run identity does not match the batch member")
                adapter.validate_run(saved, entry, intent)
                result[run["label"]] = run
        if page["next_offset"] is None:
            return result
        offset = page["next_offset"]


def _archived(p, batch_id):
    """Whether the batch is archived (project format 11); services without archiving have none."""
    try:
        listed = p.archived("batch")
    except Exception:  # noqa: BLE001 - an older service or project simply archives nothing
        return False
    return any(item["id"] == batch_id for item in listed["items"])


class Batches:
    def __init__(self, stk):
        self.stk = stk

    def templates(self):
        return [{"id": t.id, "name": t.name, "table_id": t.table_id} for t in TEMPLATES.values()]

    def create(self, template_id, record_ids, connection, *, expected_revision, options=None, project=None):
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        adapter = template(template_id)
        options = deepcopy({} if options is None else options)
        if not isinstance(options, dict):
            raise ValueError("Execution options must be an object")
        if not isinstance(connection, str) or re.fullmatch(r"runtime:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", connection) is None:
            raise ValueError("Select a saved direct or SSH Runtime profile")
        intent = {"format": 1, "project_id": model["project"]["id"], "template": template_id,
                  "connection": connection, "options": options,
                  "entries": [adapter.describe(model, r, connection, options) for r in sorted(_ids(record_ids))]}
        batch_id = _identity(intent)
        table = _table(model, TABLE_ID, FIELDS, FIELD_IDS)
        if table and any(r["id"] == batch_id for r in table["records"]):
            _batch(model, batch_id)
            return {"id": batch_id, "revision": expected_revision}
        commands = [] if table else _create_table(TABLE_ID, "Simulation batches / 仿真批次", FIELDS, FIELD_IDS)
        commands += [{"op": "add_record", "table_id": TABLE_ID, "id": batch_id}]
        commands += _cells(TABLE_ID, batch_id, {"name": f"{adapter.name} · {len(record_ids)} · {batch_id[:8]}",
                                              "intent": intent, "outcomes": {}}, FIELD_IDS)
        result = p.apply(commands, expected_revision=expected_revision)
        print("Saved batch:", batch_id, "— no input uploaded and no task submitted", flush=True)
        return {"id": batch_id, "revision": result["revision"]}

    def inspect(self, batch_id, *, project=None):
        """Read saved observations offline; refresh is an explicit separate operation."""
        p = project or self.stk.project
        model = p.snapshot()
        intent, outcomes, name = _batch(model, batch_id)
        plans, items = _plans(p, intent), []
        adapter = template(intent["template"])
        for entry in intent["entries"]:
            run = plans.get(entry["label"], {})
            error, parameter_state = "", "current"
            try:
                current = adapter.describe(model, entry["record_id"], intent["connection"], intent["options"])
                if current["label"] != entry["label"]:
                    parameter_state = "changed"
            except Exception as exc:
                parameter_state, error = "error", str(exc)
            items.append({**entry, "run_id": run.get("id"), "task_id": run.get("task_id"),
                          "state": run.get("task_state") or run.get("submission", "unprepared"),
                          "parameter_state": parameter_state, "parameter_error": error,
                          "last_operation": outcomes.get(entry["record_id"], {})})
        return {"id": batch_id, "name": name, "template": intent["template"],
                "connection": intent["connection"], "items": items}

    def execute(self, batch_id, operation, *, expected_revision, record_ids=None, project=None):
        """Perform one explicit operation per selected member; save partial outcomes and continue.

        KeyboardInterrupt stops future members. Accepted remote tasks continue; resume with the
        same batch/operation to recover the original plans and task IDs. Task failure never reruns.
        """
        if operation not in {"prepare", "submit", "refresh", "cancel", "collect"}:
            raise ValueError("Unknown batch operation")
        if operation in {"prepare", "submit"} and _archived(project or self.stk.project, batch_id):
            raise ValueError("This batch is archived; restore it to prepare or submit it")
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        intent, _, _ = _batch(model, batch_id)
        adapter = template(intent["template"])
        members = {e["record_id"]: e for e in intent["entries"]}
        selected = _ids(record_ids) if record_ids is not None else list(members)
        if any(r not in members for r in selected):
            raise ValueError("Selected row is not part of this batch")
        results = []
        for record_id in selected:
            model = p.snapshot()
            _batch(model, batch_id)  # Deletion/undo of the batch stops subsequent external actions.
            outcome = {"operation": operation, "ok": False, "run_id": None}
            run = None
            try:
                run = _plans(p, intent).get(members[record_id]["label"])
                if run:
                    outcome["run_id"] = run["id"]
                if operation == "prepare":
                    if run is None:
                        current = adapter.describe(model, record_id, intent["connection"], intent["options"])
                        if current["label"] != members[record_id]["label"]:
                            raise ValueError("Parameters changed; create a new batch before preparing this row")
                        run = adapter.prepare(self.stk, p, record_id, intent["connection"], intent["options"],
                                              model["project"]["revision"])
                elif run is None:
                    raise ValueError("Prepare this batch member first")
                elif operation == "collect":
                    adapter.collect(self.stk, p, run["id"])
                else:
                    getattr(p.runs, operation)(run["id"])
                outcome.update(ok=True, run_id=run["id"])
                observed = p.runs.get(run["id"])
                status = observed["status"]
                outcome["state"] = (status.get("task") or {}).get("state", status["submission"])
                outcome["parameter_state"] = observed["parameter_state"]
            except Exception as exc:
                outcome["error"] = str(exc)[:2000]
                if outcome["run_id"]:
                    observed = p.runs.get(outcome["run_id"])
                    status = observed["status"]
                    outcome["state"] = (status.get("task") or {}).get("state", status["submission"])
                    outcome["parameter_state"] = observed["parameter_state"]
            # Save each outcome, including failures; accepted run/task identity remains in Runs
            # even if this write loses its response or a concurrent edit rejects the revision.
            model = p.snapshot()
            _, outcomes, _ = _batch(model, batch_id)
            outcomes = {**outcomes, record_id: outcome}
            p.apply(_cells(TABLE_ID, batch_id, {"outcomes": outcomes}, FIELD_IDS),
                    expected_revision=model["project"]["revision"])
            results.append({"record_id": record_id, **outcome})
            print("Batch", operation, record_id, "OK" if outcome["ok"] else outcome["error"], flush=True)
        return {"id": batch_id, "operation": operation, "items": results,
                "ok": all(item["ok"] for item in results)}


    def run(self, template_id, record_ids, connection, *, expected_revision, options=None, project=None):
        """One explicit "run these rows": save (or reuse) the batch, prepare every member, submit the prepared ones.

        The batch is created at ``expected_revision`` and prepared at the revision that creation
        returned. Submission then follows at the revision preparation left: every member is checked
        against the frozen batch intent, so later edits of its parameters are refused, never adopted.
        Members that failed to prepare are not submitted; their errors stay in the batch outcomes.
        Accepted tasks are not waited for, refreshed or collected here.
        """
        p = project or self.stk.project
        created = self.create(template_id, record_ids, connection, expected_revision=expected_revision,
                              options=options, project=p)
        prepared = self.execute(created["id"], "prepare", expected_revision=created["revision"], project=p)
        ready = [item["record_id"] for item in prepared["items"] if item["ok"]]
        submitted = None
        if ready:
            submitted = self.execute(created["id"], "submit", expected_revision=p.snapshot()["project"]["revision"],
                                     record_ids=ready, project=p)
        accepted = sum(item["ok"] for item in submitted["items"]) if submitted else 0
        print(f"Batch run: {accepted} of {len(prepared['items'])} rows submitted to {connection}", flush=True)
        return {"id": created["id"], "prepare": prepared, "submit": submitted,
                "ok": prepared["ok"] and bool(submitted) and submitted["ok"]}


def native_action(stk, action, params, *, project):
    if action == "create":
        return stk.batches.create(project=project, **params)
    if action == "run":
        return stk.batches.run(project=project, **params)
    return stk.batches.execute(operation=action, project=project, **params)
