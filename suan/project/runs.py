"""Immutable per-case execution plans and durable observations, separate from editable tables.

Preparing plans never contacts a Runtime. Observations are projections of remote facts and do
not advance the editable project's revision or enter its undo stack.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import uuid4

from suan.runtime.models import TaskSpec, relative_path, TERMINAL
from .snapshots import _canonical
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id, _version

MAX_PLAN_BYTES = 256 * 1024
MAX_BATCH_BYTES = 4 * 1024 * 1024


def _parameters(table, record):
    return {"table_id": table["id"], "record_id": record["id"], "table_name": table["name"],
            "fields": table["fields"], "values": record["values"], "definitions": record.get("definitions", {}),
            "effective_units": {field["id"]: record.get("evaluations", {}).get(field["id"], {}).get("unit", field.get("unit"))
                                for field in table["fields"]}}


def _semantic(parameters):
    return {"fields": {field["id"]: {"type": field["type"], "unit": field.get("unit")} for field in parameters["fields"]},
            **{key: parameters[key] for key in ("values", "definitions", "effective_units")}}


def _find(model, table_id, record_id):
    table = next((table for table in model["tables"] if table["id"] == table_id), None)
    row = next((row for row in table["records"] if row["id"] == record_id), None) if table else None
    return table, row


def _errors(record):
    return any(result.get("state") != "ok" for result in record.get("evaluations", {}).values())


class Runs:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _require(db):
        if _version(db) < 5:
            raise UnsupportedProjectFormat("Upgrade this project to format 5 before preparing or reading runs")

    def _inputs(self, entry, spec):
        snapshot_id = entry.get("input_snapshot_id")
        bindings = entry.get("input_bindings")
        if snapshot_id is None:
            if bindings is not None or spec.get("inputs") or spec.get("input_hashes"):
                raise ProjectError("File inputs need an input_snapshot_id; capture them before preparing a run")
            return None, {}, []
        snapshot = self.store.snapshots.get(snapshot_id)
        files = {file["record_id"]: file for file in snapshot["manifest"]["files"]}
        if bindings is None:
            bindings = {file["name"]: identity for identity, file in files.items()}
            if len(bindings) != len(files):
                raise ProjectError("Snapshot filenames collide; provide explicit input_bindings")
        if not isinstance(bindings, dict) or not 1 <= len(bindings) <= 100:
            raise ProjectError("input_bindings maps 1–100 remote relative paths to snapshot file record IDs")
        normalized, inputs = {}, []
        for name, identity in bindings.items():
            name = relative_path(name)
            if name in normalized or not isinstance(identity, str) or identity not in files:
                raise ProjectError("Input binding is duplicated or does not belong to the chosen snapshot")
            normalized[name] = identity
            file = files[identity]
            inputs.append({"path": name, "record_id": identity, "sha256": file["sha256"], "size": file["size"]})
        expected = {file["path"]: file["sha256"] for file in inputs}
        if spec.get("inputs") is not None and set(spec["inputs"]) != set(normalized):
            raise ProjectError("Task inputs must exactly match the frozen input bindings")
        if spec.get("input_hashes") is not None and spec["input_hashes"] != expected:
            raise ProjectError("Task input_hashes must match the selected snapshot")
        return snapshot_id, normalized, inputs

    def prepare(self, entries, *, connection, connection_identity, expected_revision, node=None):
        _expected_revision(expected_revision)
        if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
            raise ProjectError("Prepare between 1 and 100 explicit case entries")
        if not isinstance(connection, str) or re.fullmatch(r"local|runtime:[A-Za-z0-9][A-Za-z0-9._-]{0,63}|hub:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", connection) is None:
            raise ProjectError("A saved connection ID is required")
        if not isinstance(connection_identity, str) or re.fullmatch(r"[a-f0-9]{16}", connection_identity) is None:
            raise ProjectError("A credential-free Runtime endpoint identity is required")
        if node is not None and (not isinstance(node, str) or re.fullmatch(r"[a-f0-9]{32}", node) is None):
            raise ProjectError("Invalid execution node ID")
        if connection.startswith("hub:") != (node is not None):
            raise ProjectError("Hub runs require a node; direct Runtime runs do not accept one")
        model = self.store.snapshot()
        if model["format_version"] < 5:
            raise UnsupportedProjectFormat("Upgrade this project to format 5 before preparing runs")
        if model["project"]["revision"] != expected_revision:
            raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {model['project']['revision']}")
        plans, total = [], 0
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - {"table_id", "record_id", "spec", "input_snapshot_id", "input_bindings", "label"}:
                raise ProjectError("Invalid run entry; provide table_id, record_id and a TaskSpec")
            table_id, record_id = entry.get("table_id"), entry.get("record_id")
            _id(table_id)
            _id(record_id)
            table, record = _find(model, table_id, record_id)
            if record is None or _errors(record):
                raise ProjectError("Case record is missing or contains a formula error")
            spec = entry.get("spec")
            if not isinstance(spec, dict):
                raise ProjectError("Each run needs a complete TaskSpec including workspace_id")
            try:
                # Validate the caller's structure before inspecting input collections.
                spec = TaskSpec(**spec).to_dict()
                snapshot_id, bindings, inputs = self._inputs(entry, spec)
                spec = TaskSpec(**{**spec, "inputs": [file["path"] for file in inputs],
                                    "input_hashes": {file["path"]: file["sha256"] for file in inputs}}).to_dict()
            except (TypeError, ValueError) as exc:
                raise ProjectError(f"Invalid run inputs/spec: {exc}") from None
            label = entry.get("label", spec["name"] or table["name"] + " / " + record_id[:8])
            if not isinstance(label, str) or not label.strip() or len(label) > 200:
                raise ProjectError("Run label must contain 1–200 characters")
            identity = str(uuid4())
            plan = {"format": 1, "id": identity, "project_id": model["project"]["id"], "label": label,
                    "source_revision": expected_revision, "parameters": _parameters(table, record), "spec": spec,
                    "connection": connection, "node": node, "connection_identity": connection_identity,
                    "input_snapshot_id": snapshot_id, "input_bindings": bindings, "inputs": inputs,
                    "idempotency_key": f"project:{model['project']['id']}:run:{identity}"}
            encoded = _canonical(plan)
            length = len(encoded.encode("utf-8"))
            total += length
            if length > MAX_PLAN_BYTES or total > MAX_BATCH_BYTES:
                raise ProjectError("Run plans exceed the 256 KiB per-plan or 4 MiB batch limit")
            plans.append((plan, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()))
        with self.store._connect(write=True) as db:
            self._require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            revision += 1
            now = datetime.now(timezone.utc).isoformat()
            ids = [plan["id"] for plan, _, _ in plans]
            db.execute("INSERT INTO changes VALUES (?, ?, ?)", (revision, now, _canonical([{"op": "prepare_runs", "run_ids": ids}])))
            for plan, encoded, digest in plans:
                db.execute("INSERT INTO run_plans VALUES (?, ?, ?, ?, ?, ?)",
                           (plan["id"], digest, encoded, now, revision, plan["input_snapshot_id"]))
            db.execute("UPDATE project SET revision=?", (revision,))
        return {"revision": revision, "run_ids": ids}

    def _decode(self, row):
        if row is None:
            raise ProjectError("Run plan not found")
        result = dict(row)
        try:
            plan = json.loads(result.pop("plan"))
            if (hashlib.sha256(_canonical(plan).encode("utf-8")).hexdigest() != result["sha256"]
                    or plan["project_id"] != self.store._project_id or plan["id"] != result["id"]
                    or plan["format"] != 1 or plan["input_snapshot_id"] != result["input_snapshot_id"]):
                raise ValueError("identity/checksum mismatch")
            TaskSpec(**plan["spec"])
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise ProjectError(f"Invalid stored run plan: {exc}") from None
        result["plan"] = plan
        return result

    @staticmethod
    def _observation(db, run_id):
        row = db.execute("SELECT * FROM run_observations WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
        if row is None:
            return {"observation_id": 0, "observed_at": None, "status": {"submission": "prepared"}}
        try:
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                raise ValueError("status is not an object")
        except (ValueError, RecursionError) as exc:
            raise ProjectError(f"Invalid stored run observation: {exc}") from None
        return {"observation_id": row["id"], "observed_at": row["created_at"], "status": payload}

    @staticmethod
    def _freshness(plan, model):
        parameters = plan["parameters"]
        table, record = _find(model, parameters["table_id"], parameters["record_id"])
        if record is None:
            return "missing"
        if _errors(record):
            return "error"
        return "current" if _semantic(_parameters(table, record)) == _semantic(parameters) else "changed"

    def get(self, run_id):
        _id(run_id)
        with self.store._connect() as db:
            self._require(db)
            result = self._decode(db.execute("SELECT * FROM run_plans WHERE id=?", (run_id,)).fetchone())
            result.update(self._observation(db, run_id))
        model = self.store.snapshot()
        result["parameter_state"] = self._freshness(result["plan"], model)
        result["parameter_revision"] = model["project"]["revision"]
        return result

    def list(self, *, offset=0, limit=100):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Run list requires offset >= 0 and limit between 1 and 100")
        model = self.store.snapshot()
        with self.store._connect() as db:
            self._require(db)
            rows = db.execute("SELECT * FROM run_plans ORDER BY rowid LIMIT ? OFFSET ?", (limit + 1, offset)).fetchall()
            results = []
            for row in rows[:limit]:
                result = self._decode(row)
                result.update(self._observation(db, result["id"]))
                plan = result.pop("plan")
                result["parameter_state"] = self._freshness(plan, model)
                result.update({key: plan[key] for key in ("label", "connection", "node", "source_revision")})
                result["table_id"], result["record_id"] = plan["parameters"]["table_id"], plan["parameters"]["record_id"]
                status = result.pop("status")
                result["submission"] = status["submission"]
                result["task_id"] = (status.get("task") or {}).get("id")
                result["task_state"] = (status.get("task") or {}).get("state")
                result["action_state"] = (status.get("action") or {}).get("state")
                result["error"] = (status.get("error") or {}).get("message")
                results.append(result)
            return {"revision": model["project"]["revision"], "runs": results,
                    "next_offset": offset + limit if len(rows) > limit else None}

    def observe(self, run_id, patch):
        """Record a remote observation without advancing editable state. Internal service API."""
        _id(run_id)
        with self.store._connect(write=True) as db:
            self._require(db)
            self._decode(db.execute("SELECT * FROM run_plans WHERE id=?", (run_id,)).fetchone())
            previous = self._observation(db, run_id)["status"]
            current = {**previous, **patch}
            old_task, new_task = previous.get("task"), current.get("task")
            if old_task:
                if new_task and old_task["id"] != new_task["id"]:
                    raise ProjectError("A run attempt cannot change its accepted Runtime task ID")
                if not new_task or (old_task["state"] in TERMINAL and new_task["state"] not in TERMINAL):
                    current["task"] = old_task
                current["submission"] = "accepted"
            if current == previous:
                return self._observation(db, run_id)
            cursor = db.execute("INSERT INTO run_observations(run_id, created_at, payload) VALUES (?, ?, ?)",
                                (run_id, datetime.now(timezone.utc).isoformat(), _canonical(current)))
            return {"observation_id": cursor.lastrowid, "status": current}
