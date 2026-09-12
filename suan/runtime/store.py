"""Durable metadata. Each operation uses a short independent transaction."""

from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3

from .common import identity, now
from .models import TaskRecord, TERMINAL


class Store:
    def __init__(self, state_dir):
        self.path = str(Path(state_dir) / "runtime.sqlite3")
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    spec_hash TEXT NOT NULL, data TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def workspace(self, workspace_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            raise KeyError("Workspace not found")
        return json.loads(row[0])

    def workspaces(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM workspaces ORDER BY rowid")]

    def add_workspace(self, workspace):
        with self.connect() as db:
            db.execute("INSERT INTO workspaces VALUES (?,?)", (workspace["id"], json.dumps(workspace)))

    def reserve(self, task_id, key, spec_hash, spec):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT spec_hash,data FROM tasks WHERE request_key=?", (key,)).fetchone()
            if row:
                if row[0] != spec_hash:
                    raise ValueError("Idempotency key was already used for a different task")
                return json.loads(row[1]), False
            record = asdict(TaskRecord(task_id, spec, "preparing", now(), now()))
            record['preparer'] = identity()
            db.execute("INSERT INTO tasks VALUES (?,?,?,?)", (task_id, key, spec_hash, json.dumps(record)))
        return record, True

    def task(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("Task not found")
        return json.loads(row[0])

    def tasks(self, workspace_id=None):
        with self.connect() as db:
            records = [json.loads(r[0]) for r in db.execute("SELECT data FROM tasks ORDER BY rowid DESC")]
        return [r for r in records if workspace_id is None or r["spec"]["workspace_id"] == workspace_id]

    def update(self, task_id, expected=None, **changes):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError("Task not found")
            record = json.loads(row[0])
            if expected is not None and record["state"] not in expected:
                return record
            record.update(changes, updated_at=now())
            if record['state'] in TERMINAL:
                record.setdefault('finished_at', now())
            elif record['state'] == 'running':
                record.setdefault('started_at', now())
            db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(record), task_id))
        return record

    def claim(self, task_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = json.loads(db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()[0])
            if record["state"] != "queued" or record.get("attempted_at") or record["cancel_requested"]:
                return None
            record.update(state="submitting", attempted_at=now(), updated_at=now())
            db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(record), task_id))
            return record
