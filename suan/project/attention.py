"""What in a project needs a person, is running, or finished recently (UX package U1).

A read-only summary across workflow runs, analysis runs, simulation runs, AI drafts and AI requests,
for one "needs attention" surface (docs/design/ux-package-2026-10.md). Failures come first, then
items to review, then running ones, then finished ones. Each item carries structured fields for the
interface to word, a navigation target, and a key that changes with the item's state, so a viewed
item reappears when it fails again. Nothing here runs, prepares or changes anything.
"""
from .store import ProjectError, _version

MAX_PER_SOURCE = 50
_GROUP_ORDER = {"needs_you": 0, "running": 1, "done": 2}
_SEVERITY_ORDER = {"failure": 0, "review": 1, "progress": 2, "info": 3}


def _item(kind, identity, group, severity, *, name=None, status=None, at=None, target=None, **fields):
    signature = f"{status}"
    if "counts" in fields:
        signature += ":" + ",".join(f"{key}={value}" for key, value in sorted(fields["counts"].items()))
    return {"key": f"{kind}:{identity}:{signature}", "kind": kind, "id": identity, "group": group, "severity": severity,
            "name": name, "status": status, "at": at, "target": target or {}, **fields}


def _newest(page, key):
    """The newest entries of an oldest-first paginated list (bounded)."""
    items, offset = [], 0
    for _ in range(10):
        result = page(offset)
        items.extend(result[key])
        if result.get("next_offset") is None:
            break
        offset = result["next_offset"]
    return items[-MAX_PER_SOURCE:][::-1]


def collect(store):
    """Every attention item of the project, ordered: needs you (failures, reviews), running, done."""
    with store._connect() as db:
        version = _version(db)
        revision = db.execute("SELECT revision FROM project").fetchone()[0]
    items, workflow_analysis_runs = [], set()
    if version >= 10:
        for summary in store.workflow_runs.list(limit=MAX_PER_SOURCE)["runs"]:
            run = store.workflow_runs.get(summary["id"])
            for task in run["tasks"]:
                produced = task.get("produced") or {}
                if produced.get("analysis_run_id"):
                    workflow_analysis_runs.add(produced["analysis_run_id"])
            counts, status = run["counts"], run["status"]
            failed = counts.get("failed", 0) + counts.get("interrupted", 0)
            common = {"name": run["workflow_name"], "at": run["created_at"],
                      "target": {"editor": "workflow", "workflow_id": run["workflow_id"], "run_id": run["id"]},
                      "counts": counts, "rows": len(run["rows"])}
            if status in ("running", "cancel_requested"):
                items.append(_item("workflow_run", run["id"], "running", "progress", status=status, **common))
            elif status == "stopped" and (failed or run["stop_error"]):
                items.append(_item("workflow_run", run["id"], "needs_you", "failure", status="failed",
                                   error=(run["stop_error"] or {}).get("message"), **common))
            elif run["complete"]:
                items.append(_item("workflow_run", run["id"], "done", "info", status="succeeded", **common))
    if version >= 9:
        for run in _newest(lambda offset: store.analysis_runs.list(offset=offset, limit=100), "runs"):
            if run["id"] in workflow_analysis_runs:
                continue  # shown through its workflow run
            common = {"name": run["analysis_name"], "at": run["updated_at"],
                      "target": {"editor": "analysis_graph", "analysis_id": run["analysis_id"], "analysis_run_id": run["id"]}}
            status = run["status"]
            if status in ("running", "cancel_requested"):
                items.append(_item("analysis_run", run["id"], "running", "progress", status=status, **common))
            elif status in ("failed", "unknown"):
                items.append(_item("analysis_run", run["id"], "needs_you", "failure", status=status,
                                   error=(run.get("error") or {}).get("message"), **common))
            elif status in ("succeeded", "cancelled"):
                items.append(_item("analysis_run", run["id"], "done", "info", status=status, **common))
    if version >= 5:
        for run in _newest(lambda offset: store.runs.list(offset=offset, limit=100), "runs"):
            task = run.get("task_state")
            common = {"name": run.get("label"), "at": None, "target": {"page": "simulation_runs", "run_id": run["id"]}}
            submission = run.get("submission")
            if run.get("error") or task in ("failed", "unknown") or (not task and submission == "uncertain"):
                items.append(_item("simulation_run", run["id"], "needs_you", "failure", status=task or submission,
                                   error=run.get("error"), **common))
            elif task in ("succeeded", "cancelled"):
                items.append(_item("simulation_run", run["id"], "done", "info", status=task, **common))
            elif task or submission in ("submitting", "accepted"):
                items.append(_item("simulation_run", run["id"], "running", "progress", status=task or submission, **common))
    if version >= 6:
        for draft in _newest(lambda offset: store.drafts.list(offset=offset, limit=100), "drafts"):
            if draft.get("status") == "pending":
                items.append(_item("draft", draft["id"], "needs_you", "review", name=draft.get("title"), status="pending",
                                   at=draft.get("created_at"), target={"page": "review", "draft_id": draft["id"]}))
    if version >= 8:
        for request in _newest(lambda offset: store.requests.list(offset=offset, limit=100), "requests"):
            status = request.get("status")
            common = {"name": None, "at": request.get("updated_at"), "target": {"page": "conversation", "request_id": request["id"]}}
            if status in ("failed", "uncertain"):
                items.append(_item("request", request["id"], "needs_you", "failure", status=status,
                                   error=request.get("error_code"), **common))
            elif status in ("pending", "running"):
                items.append(_item("request", request["id"], "running", "progress", status=status, **common))
            elif status == "completed":
                items.append(_item("request", request["id"], "done", "info", status=status, **common))
    items.sort(key=lambda item: (_GROUP_ORDER[item["group"]], _SEVERITY_ORDER[item["severity"]], _reverse_time(item["at"])))
    return {"revision": revision, "items": items}


def _reverse_time(value):
    # Newest first within a group; items without a time keep their source order after timed ones.
    return tuple(-ord(c) for c in value) if isinstance(value, str) else (1,)


__all__ = ["collect", "ProjectError"]
