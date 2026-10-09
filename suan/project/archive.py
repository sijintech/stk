"""Archived project objects (project format 11, docs/design/project-archive.md).

Archiving hides an object from the default lists and freezes it: it cannot be changed (saved, retried,
sent, applied or discarded in place) but can still be used as it is, which creates new objects (owner
decision 2026-10-08); its data, identity and results stay as they are. Each change is one appended row of ``project_archive``
(``kind, object_id, archived, at, note``) and an object's current state is its last row. Unlike the
run and request journals the rows are not hash-chained: they record a view choice, not results. They
never advance the editable revision or enter undo. Below format 11 nothing is archived: every read
here is a no-op and only ``set`` asks for the upgrade.
"""
from datetime import datetime, timezone

from .store import ProjectError, UnsupportedProjectFormat, _id, _version

KINDS = ("workflow", "analysis", "batch", "workflow_run", "analysis_run", "simulation_run", "request", "draft", "context")
MAX_ITEMS = 100
MAX_NOTE_CHARS = 1000
_TERMINAL_TASKS = frozenset({"succeeded", "failed", "cancelled", "unknown"})
_CURRENT = ("SELECT a.object_id FROM project_archive a WHERE a.kind=? AND a.archived=1 AND a.id="
            "(SELECT max(b.id) FROM project_archive b WHERE b.kind=a.kind AND b.object_id=a.object_id)")


def available(db):
    return _version(db) >= 11


def clause(db, kind, archived, column="id"):
    """(SQL condition, parameters) keeping only archived (True) or unarchived (False) objects of a kind
    in a list query; ("", []) when not filtering. Below format 11 nothing is archived."""
    if archived is None:
        return "", []
    if type(archived) is not bool:
        raise ProjectError("archived filters with true or false")
    if not available(db):
        return ("0", []) if archived else ("", [])
    return f"{column} {'IN' if archived else 'NOT IN'} ({_CURRENT})", [kind]


def where(db, kind, archived, column="id", existing=""):
    """``existing`` (a WHERE condition or "") combined with the archive filter, as " WHERE ..." or ""."""
    condition, params = clause(db, kind, archived, column)
    parts = [part for part in (existing, condition) if part]
    return (" WHERE " + " AND ".join(parts)) if parts else "", params


class Archived(ProjectError):
    """The object is archived; restore it first."""


class Archive:
    def __init__(self, store):
        self.store = store

    def ids(self, kind):
        """The currently archived object IDs of a kind."""
        with self.store._connect() as db:
            if not available(db):
                return set()
            return {row[0] for row in db.execute(_CURRENT, (kind,))}

    def is_archived(self, kind, object_id):
        with self.store._connect() as db:
            return self._archived(db, kind, object_id)

    @staticmethod
    def _archived(db, kind, object_id):
        if not available(db):
            return False
        row = db.execute("SELECT archived FROM project_archive WHERE kind=? AND object_id=? ORDER BY id DESC LIMIT 1",
                         (kind, object_id)).fetchone()
        return bool(row and row[0])

    def require_active(self, kind, object_id, action):
        """Refuse ``action`` (for example "edit this workflow") on an archived object."""
        if self.is_archived(kind, object_id):
            raise Archived(f"This {kind.replace('_', ' ')} is archived; restore it to {action}")

    def list(self, kind=None):
        """Every currently archived object (optionally of one kind) with when and why, and counts per kind."""
        if kind is not None and kind not in KINDS:
            raise ProjectError("Unknown archive kind")
        with self.store._connect() as db:
            if not available(db):
                return {"items": [], "counts": dict.fromkeys(KINDS, 0)}
            rows = db.execute("SELECT a.kind, a.object_id, a.at, a.note FROM project_archive a WHERE a.archived=1 AND a.id="
                              "(SELECT max(b.id) FROM project_archive b WHERE b.kind=a.kind AND b.object_id=a.object_id)"
                              + (" AND a.kind=?" if kind else "") + " ORDER BY a.id", (kind,) if kind else ()).fetchall()
        counts = dict.fromkeys(KINDS, 0)
        for row in rows:
            counts[row[0]] += 1
        return {"items": [{"kind": row[0], "id": row[1], "archived_at": row[2], "note": row[3]} for row in rows],
                "counts": counts}

    def set(self, items, *, archived, note=None, include_runs=False):
        """Archive (or restore) 1-100 objects. Unknown objects and objects still in progress are refused;
        objects already in that state are left alone. ``include_runs`` also archives (or restores) the runs
        of each listed workflow that are not running. Returns the ones that changed."""
        if type(archived) is not bool:
            raise ProjectError("archived is true or false")
        if note is not None and (type(note) is not str or len(note) > MAX_NOTE_CHARS or "\0" in note):
            raise ProjectError(f"An archive note is text of at most {MAX_NOTE_CHARS} characters")
        if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
            raise ProjectError(f"Archive 1 to {MAX_ITEMS} objects at a time")
        wanted = []
        for item in items:
            if type(item) is not dict or set(item) != {"kind", "id"} or item["kind"] not in KINDS:
                raise ProjectError("Each archived object is {kind, id} of a known kind")
            key = (item["kind"], _id(item["id"]))
            if key not in wanted:
                wanted.append(key)
        with self.store._connect() as db:
            if not available(db):
                raise UnsupportedProjectFormat("Upgrade this project to format 11 before archiving")
        if include_runs:
            for kind, object_id in list(wanted):
                if kind != "workflow":
                    continue
                offset = 0
                while offset is not None:
                    page = self.store.workflow_runs.list(offset=offset, limit=100, workflow_id=object_id)
                    for run in page["runs"]:
                        if run["status"] not in ("running", "cancel_requested") and ("workflow_run", run["id"]) not in wanted:
                            wanted.append(("workflow_run", run["id"]))
                    offset = page["next_offset"]
        with self.store._connect() as db:
            pending = [key for key in wanted if self._archived(db, *key) != archived]
        for kind, object_id in pending:
            self._check(kind, object_id, archived)  # reads only; refuses before anything is written
        now = datetime.now(timezone.utc).isoformat()
        with self.store._connect(write=True) as db:
            changed = []
            for kind, object_id in pending:
                if self._archived(db, kind, object_id) == archived:
                    continue
                db.execute("INSERT INTO project_archive(kind, object_id, archived, at, note) VALUES (?,?,?,?,?)",
                           (kind, object_id, int(archived), now, note))
                changed.append({"kind": kind, "id": object_id})
        return {"changed": len(changed), "items": changed}

    def _check(self, kind, object_id, archiving):
        """The object exists; when archiving, it is not in progress."""
        from suan.workflows import batches
        from . import analyses, workflows
        store = self.store
        if kind in ("workflow", "analysis", "batch"):
            table = {"workflow": workflows.TABLE_ID, "analysis": analyses.TABLE_ID, "batch": batches.TABLE_ID}[kind]
            with store._connect() as db:
                if db.execute("SELECT 1 FROM records WHERE id=? AND table_id=?", (object_id, table)).fetchone() is None:
                    raise ProjectError(f"No {kind} {object_id} in this project")
            return
        table = {"workflow_run": "workflow_run_plans", "analysis_run": "analysis_run_plans", "simulation_run": "run_plans",
                 "request": "project_requests", "draft": "project_drafts", "context": "project_contexts"}[kind]
        with store._connect() as db:
            if db.execute(f"SELECT 1 FROM {table} WHERE id=?", (object_id,)).fetchone() is None:
                raise ProjectError(f"No {kind.replace('_', ' ')} {object_id} in this project")
        if not archiving:
            return
        if kind == "workflow_run" and store.workflow_runs.get(object_id)["status"] in ("running", "cancel_requested"):
            raise ProjectError("This workflow run is still running; cancel it or wait for it to stop before archiving")
        if kind == "analysis_run" and store.analysis_runs.get(object_id)["status"] in ("running", "cancel_requested"):
            raise ProjectError("This analysis run is still running; cancel it or wait for it to finish before archiving")
        if kind == "simulation_run":
            task = (store.runs.get(object_id)["status"].get("task") or {}).get("state")
            if task is not None and task not in _TERMINAL_TASKS:
                raise ProjectError("This simulation is still on the Runtime; cancel it or wait for it to finish before archiving")
        if kind == "request" and store.requests.get(object_id)["status"] == "running":
            raise ProjectError("This AI request is being answered; cancel it or wait for its reply before archiving")


__all__ = ["Archive", "Archived", "KINDS", "clause", "where"]
