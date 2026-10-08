"""Frozen local analysis plans and an append-only single-attempt lifecycle journal.

Storage never executes graphs or touches input/output file bytes. The executor holds
an OS lease before claiming, publishing verified results, or recovering abandoned
work. Ordinary table edits and undo cannot change these historical facts.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata

from suan.graph.schema import canonical_json, graph_hash

from . import analyses
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _id, _version
from . import archive


MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_PLAN_BYTES = 512 * 1024
MAX_EVENT_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
PROFILE = "desktop"
BUDGET = {"max_seconds": 300, "max_output_bytes": MAX_ARCHIVE_BYTES}
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "unknown"})
STATES = TERMINAL | {"prepared", "running", "cancel_requested"}
_PLAN_KEYS = {"id", "project_id", "source_revision", "created_at", "analysis_id", "analysis_name",
              "document", "snapshot_id", "snapshot_sha256", "bindings", "profile", "budget"}
_STATE_KEYS = {"status", "updated_at", "started_at", "finished_at", "cancel_requested_at",
               "executor_id", "error", "result"}
_RESULT_KEYS = {"directory", "manifest_sha256", "graph_hash", "output_count", "has_payload", "has_errors", "size_bytes"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BINDING = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class AnalysisRunNotFound(ProjectError):
    """The selected immutable analysis run does not exist."""


class AnalysisChanged(ProjectError):
    """The saved analysis is no longer the document a frozen workflow run expects (not retryable)."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _require(db):
    if _version(db) < 9:
        raise UnsupportedProjectFormat("Upgrade this project to format 9 before preparing or reading analysis runs")


def _revision(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ProjectError("expected_revision must be a nonnegative signed 64-bit integer")
    return value


def _pack(value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        if len(raw.encode("utf-8")) > limit:
            raise ProjectError("Analysis run JSON exceeds its bounded byte limit")
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ProjectError(f"Invalid bounded analysis run JSON: {exc}") from None


def _hash(value, limit=MAX_PLAN_BYTES):
    return hashlib.sha256(_pack(value, limit).encode("utf-8")).hexdigest()


def _unpack(raw, limit):
    if type(raw) is not str:
        raise ProjectError("Invalid stored analysis run JSON")
    try:
        if len(raw.encode("utf-8")) > limit:
            raise ValueError("byte limit")
        depth, quoted, escaped = 0, False, False
        for char in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > 96:
                    raise ValueError("depth limit")
            elif char in "]}":
                depth -= 1

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate object key")
                result[key] = value
            return result

        def integer(text):
            if len(text.lstrip("-")) > 20:
                raise ValueError("integer size")
            value = int(text)
            if not -(2**63) <= value < 2**64:
                raise ValueError("integer range")
            return value

        def number(text):
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("nonfinite number")
            return value

        def constant(_):
            raise ValueError("nonfinite literal")

        result = json.loads(raw, object_pairs_hook=pairs, parse_int=integer, parse_float=number, parse_constant=constant)
        _pack(result, limit)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProjectError(f"Invalid stored analysis run JSON: {exc}") from None


def _sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ProjectError("Analysis run digest must be lowercase SHA256")
    return value


def _time(value):
    if type(value) is not str or len(value) > 64:
        raise ProjectError("Invalid analysis run timestamp")
    try:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("timezone")
    except ValueError:
        raise ProjectError("Invalid analysis run timestamp") from None


def _path(value):
    if type(value) is not str or not value or len(value) > 1024:
        raise ProjectError("Analysis binding paths must be portable relative filenames")
    try:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ProjectError("Analysis binding paths exceed 1024 UTF-8 bytes") from None
    parts = value.split("/")
    for part in parts:
        if (part in ("", ".", "..") or part[-1:] in (" ", ".")
                or len(part.encode("utf-8")) > 255
                or any(ord(c) < 32 or ord(c) == 127 or c in '\\:<>"|?*' for c in part)
                or part.split(".")[0].casefold() in _RESERVED):
            raise ProjectError("Analysis binding paths must be portable relative filenames")
    return value


def _bindings(value):
    if type(value) is not dict or not 1 <= len(value) <= 32:
        raise ProjectError("Analysis bindings need 1 to 32 explicit named mappings")
    result, count = {}, 0
    for name, files in value.items():
        if type(name) is not str or _BINDING.fullmatch(name) is None:
            raise ProjectError("Invalid analysis binding name")
        if type(files) is not dict or not files:
            raise ProjectError("Each analysis binding needs explicit files")
        count += len(files)
        if count > 100:
            raise ProjectError("Analysis bindings exceed 100 file mappings")
        paths, mapping = set(), {}
        for path, record_id in files.items():
            _path(path)
            _id(record_id)
            key = unicodedata.normalize("NFC", path).casefold()
            if key in paths or any(key.startswith(other + "/") or other.startswith(key + "/") for other in paths):
                raise ProjectError("Analysis binding paths collide on a supported filesystem")
            paths.add(key)
            mapping[path] = record_id
        result[name] = mapping
    # Binding directories themselves also need to coexist on case-insensitive systems.
    if len({name.casefold() for name in result}) != len(result):
        raise ProjectError("Analysis binding names collide on a supported filesystem")
    return result


def _freeze_bindings(bindings, snapshot):
    files = {file["record_id"]: file for file in snapshot["manifest"]["files"]}
    result, total = {}, 0
    for name, selected in bindings.items():
        result[name] = {}
        for path, record_id in selected.items():
            if record_id not in files:
                raise ProjectError("Analysis binding file does not belong to the selected snapshot")
            file = files[record_id]
            total += file["size"]
            if total > MAX_INPUT_BYTES:
                raise ProjectError("Analysis bindings exceed the 256 MiB logical input limit")
            result[name][path] = {key: file[key] for key in ("record_id", "sha256", "size")}
    return result


def _selection(plan):
    try:
        return _bindings({name: {path: file["record_id"] for path, file in files.items()}
                          for name, files in plan["bindings"].items()})
    except (KeyError, TypeError, AttributeError):
        raise ProjectError("Invalid frozen analysis bindings") from None


def _request(plan):
    request = {"analysis_id": plan["analysis_id"], "snapshot_id": plan["snapshot_id"],
               "bindings": _selection(plan), "expected_revision": plan["source_revision"]}
    if "parameter_overrides" in plan:
        request["parameter_overrides"] = plan["parameter_overrides"]
    return request


def _overrides(value, document):
    """Per-run values for declared graph parameters (a workflow row's values), bounded plain JSON.
    Empty means none; the frozen document keeps the saved analysis exactly."""
    if value is None:
        return {}
    value = _clone_overrides(value)
    declared = {item["name"] for item in document["graph"].get("parameters", [])}
    if (type(value) is not dict or len(value) > 64 or len(canonical_json(value)) > 64 * 1024
            or any(type(name) is not str or name not in declared for name in value)):
        raise ProjectError("Parameter overrides name at most 64 declared graph parameters within 64 KiB")
    return value


def _clone_overrides(value):
    from .managed import clone
    return clone(value, "Analysis")


def effective_parameters(plan):
    """The submitted parameters a run evaluates: the frozen document's, then its per-run overrides."""
    return {**plan["document"]["parameters"], **plan.get("parameter_overrides", {})}


def _error(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"code", "message"}
            or type(value["code"]) is not str or not _CODE.fullmatch(value["code"])
            or type(value["message"]) is not str or not value["message"] or "\0" in value["message"]):
        raise ProjectError("Analysis error requires a bounded code and message")
    try:
        if len(value["message"].encode("utf-8")) > 4096:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ProjectError("Analysis error message exceeds 4096 UTF-8 bytes") from None
    return dict(value)


def _result(value, plan):
    if value is None:
        return None
    if type(value) is not dict or set(value) != _RESULT_KEYS:
        raise ProjectError("Invalid archived analysis result summary")
    if value["directory"] != f".stk/analysis-runs/{plan['id']}/result":
        raise ProjectError("Analysis result must use its own fixed archive directory")
    _sha(value["manifest_sha256"])
    if "sha256:" + _sha(value["graph_hash"]) != graph_hash(plan["document"]["graph"]):
        raise ProjectError("Analysis result graph hash differs from the frozen graph")
    if (type(value["output_count"]) is not int or not 0 <= value["output_count"] <= 256
            or type(value["size_bytes"]) is not int or not 0 < value["size_bytes"] <= MAX_ARCHIVE_BYTES
            or type(value["has_payload"]) is not bool or type(value["has_errors"]) is not bool):
        raise ProjectError("Invalid archived analysis result summary counts or flags")
    if value["output_count"] > len(plan["document"]["outputs"]) or (value["has_payload"] and value["output_count"] == 0):
        raise ProjectError("Archived analysis output count differs from the explicit requested outputs")
    return dict(value)


class AnalysisRuns:
    def __init__(self, store):
        self.store = store

    def _snapshot(self, db, snapshot_id, cache=None):
        if cache is not None and snapshot_id in cache:
            return cache[snapshot_id]
        size = db.execute("SELECT length(CAST(manifest AS BLOB)) FROM project_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if size is not None and size[0] > MAX_MANIFEST_BYTES:
            raise ProjectError("Analysis input snapshot manifest exceeds its bounded byte limit")
        snapshot = self.store.snapshots._decode(db.execute(
            "SELECT * FROM project_snapshots WHERE id=?", (snapshot_id,)).fetchone())
        if cache is not None:
            cache[snapshot_id] = snapshot
        return snapshot

    def _plan(self, db, row, cache=None):
        if row is None:
            raise AnalysisRunNotFound("Analysis run not found")
        plan = _unpack(row["payload"], MAX_PLAN_BYTES)
        if type(plan) is not dict or set(plan) not in (_PLAN_KEYS, _PLAN_KEYS | {"parameter_overrides"}):
            raise ProjectError("Invalid frozen analysis plan fields")
        for key in ("id", "project_id", "analysis_id", "snapshot_id"):
            _id(plan[key])
        _revision(plan["source_revision"])
        _time(plan["created_at"])
        analyses._name(plan["analysis_name"])
        analyses._document(plan["document"])
        if "parameter_overrides" in plan and (not plan["parameter_overrides"] or
                _overrides(plan["parameter_overrides"], plan["document"]) != plan["parameter_overrides"]):
            raise ProjectError("Invalid frozen analysis parameter overrides")
        if (plan["id"] != row["id"] or plan["project_id"] != row["project_id"]
                or plan["project_id"] != self.store._project_id or plan["snapshot_id"] != row["snapshot_id"]
                or plan["profile"] != PROFILE or type(plan["budget"]) is not dict
                or _pack(plan["budget"], 256) != _pack(BUDGET, 256)
                or _hash(plan) != row["sha256"] or _hash(_request(plan)) != row["request_sha256"]):
            raise ProjectError("Invalid frozen analysis plan identity or checksum")
        snapshot = self._snapshot(db, plan["snapshot_id"], cache)
        if (plan["snapshot_sha256"] != snapshot["sha256"] or snapshot["revision"] > plan["source_revision"]
                or _pack(plan["bindings"], MAX_PLAN_BYTES) != _pack(_freeze_bindings(_selection(plan), snapshot), MAX_PLAN_BYTES)):
            raise ProjectError("Frozen analysis inputs differ from their snapshot")
        return plan

    @staticmethod
    def _state(plan, state):
        if (type(state) is not dict or set(state) != _STATE_KEYS
                or type(state["status"]) is not str or state["status"] not in STATES):
            raise ProjectError("Invalid analysis lifecycle state")
        _time(state["updated_at"])
        for key in ("started_at", "finished_at", "cancel_requested_at"):
            if state[key] is not None:
                _time(state[key])
        if state["executor_id"] is not None:
            _id(state["executor_id"])
        _error(state["error"])
        _result(state["result"], plan)
        status = state["status"]
        if ((status in TERMINAL) != (state["finished_at"] is not None)
                or (state["executor_id"] is None) != (state["started_at"] is None)
                or (status in {"running", "cancel_requested", "succeeded", "failed", "unknown"} and state["executor_id"] is None)
                or (status == "prepared" and any(state[key] is not None for key in _STATE_KEYS - {"status", "updated_at"}))
                or (status == "cancel_requested" and state["cancel_requested_at"] is None)
                or (status == "succeeded" and (state["result"] is None or state["result"]["has_errors"] or state["error"] is not None))
                or (status in {"failed", "unknown", "cancelled"} and state["error"] is None)
                or (status not in {"failed", "succeeded"} and state["result"] is not None)
                or (status == "failed" and state["result"] is not None and not state["result"]["has_errors"])
                or (status in {"running", "cancel_requested"} and state["error"] is not None)):
            raise ProjectError("Inconsistent analysis lifecycle state")

    @staticmethod
    def _transition(previous, state):
        allowed = {"prepared": {"running", "cancelled"}, "running": {"cancel_requested", *TERMINAL},
                   "cancel_requested": TERMINAL}
        if previous is None:
            if state["status"] != "prepared":
                raise ProjectError("Analysis run is missing its prepared event")
            return
        if state["status"] not in allowed.get(previous["status"], set()):
            raise ProjectError("Invalid analysis lifecycle transition")
        if previous["status"] != "prepared" and any(state[key] != previous[key] for key in ("executor_id", "started_at")):
            raise ProjectError("Analysis execution owner changed")
        if previous["cancel_requested_at"] is not None and state["cancel_requested_at"] != previous["cancel_requested_at"]:
            raise ProjectError("Analysis cancellation intent changed")

    def _read(self, db, run_id, cache=None):
        size = db.execute("SELECT length(CAST(payload AS BLOB)) FROM analysis_run_plans WHERE id=?", (run_id,)).fetchone()
        if size is not None and size[0] > MAX_PLAN_BYTES:
            raise ProjectError("Stored analysis plan exceeds its bounded byte limit")
        plan = self._plan(db, db.execute("SELECT * FROM analysis_run_plans WHERE id=?", (run_id,)).fetchone(), cache)
        previous, previous_hash = None, ""
        sizes = db.execute("SELECT length(CAST(payload AS BLOB)) FROM analysis_run_events WHERE run_id=? ORDER BY id LIMIT 5", (run_id,)).fetchall()
        if not 1 <= len(sizes) <= 4 or any(row[0] > MAX_EVENT_BYTES for row in sizes):
            raise ProjectError("Invalid analysis event count or byte limit")
        events = db.execute("SELECT * FROM analysis_run_events WHERE run_id=? ORDER BY id LIMIT 5", (run_id,)).fetchall()
        for event in events:
            state = _unpack(event["payload"], MAX_EVENT_BYTES)
            self._state(plan, state)
            self._transition(previous, state)
            digest = _hash({"run_id": run_id, "previous_sha256": previous_hash, "state": state}, MAX_EVENT_BYTES)
            if event["status"] != state["status"] or event["previous_sha256"] != previous_hash or event["sha256"] != digest:
                raise ProjectError("Invalid analysis event identity or checksum")
            previous, previous_hash = state, digest
        return plan, previous, previous_hash

    @staticmethod
    def _public(plan, state):
        return {**plan, "plan_sha256": _hash(plan), **state}

    def _append(self, db, plan, previous, previous_hash, state):
        self._state(plan, state)
        self._transition(previous, state)
        digest = _hash({"run_id": plan["id"], "previous_sha256": previous_hash, "state": state}, MAX_EVENT_BYTES)
        db.execute("INSERT INTO analysis_run_events(run_id,status,payload,previous_sha256,sha256) VALUES (?,?,?,?,?)",
                   (plan["id"], state["status"], _pack(state, MAX_EVENT_BYTES), previous_hash, digest))
        return self._public(plan, state)

    def prepare(self, analysis_id, snapshot_id, bindings, *, run_id, expected_revision, parameter_overrides=None,
                expected_document_sha256=None):
        """``expected_document_sha256`` (for a frozen workflow run) refuses the preparation when the saved
        analysis is no longer the document that run froze."""
        for identity in (analysis_id, snapshot_id, run_id):
            _id(identity)
        _revision(expected_revision)
        bindings = _bindings(bindings)
        if parameter_overrides is not None and type(parameter_overrides) is not dict:
            raise ProjectError("Parameter overrides must be an object")
        request = {"analysis_id": analysis_id, "snapshot_id": snapshot_id,
                   "bindings": bindings, "expected_revision": expected_revision}
        if parameter_overrides:
            request["parameter_overrides"] = parameter_overrides
        request_hash = _hash(request)
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT request_sha256 FROM analysis_run_plans WHERE id=?", (run_id,)).fetchone()
            if existing is not None:
                plan, state, _ = self._read(db, run_id)
                if existing[0] != request_hash:
                    raise RevisionConflict("Analysis run UUID is already used by a different preparation request")
                return self._public(plan, state)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (analyses.TABLE_ID, analysis_id)).fetchone() is None:
                raise analyses.AnalysisNotFound("Analysis document not found")
            _, compatible, error = analyses._schema(db)
            analysis = analyses._record(db, analysis_id, compatible, error)
            if analysis["state"] != "readable":
                raise ProjectError("Analysis definition is not readable: " + analysis["error"])
            if (expected_document_sha256 is not None and
                    hashlib.sha256(canonical_json(analysis["document"])).hexdigest() != expected_document_sha256):
                raise AnalysisChanged("The saved analysis changed after the workflow run was prepared; prepare a new run")
            snapshot = self._snapshot(db, snapshot_id)
            if snapshot["revision"] > revision:
                raise ProjectError("Analysis input snapshot comes from a later project revision")
            now = _now()
            plan = {"id": run_id, "project_id": self.store._project_id, "source_revision": revision,
                    "created_at": now, "analysis_id": analysis_id, "analysis_name": analysis["name"],
                    "document": analysis["document"], "snapshot_id": snapshot_id, "snapshot_sha256": snapshot["sha256"],
                    "bindings": _freeze_bindings(bindings, snapshot), "profile": PROFILE, "budget": dict(BUDGET)}
            overrides = _overrides(parameter_overrides, analysis["document"])
            if overrides:
                plan["parameter_overrides"] = overrides
            db.execute("INSERT INTO analysis_run_plans VALUES (?,?,?,?,?,?)",
                       (run_id, self.store._project_id, snapshot_id, _pack(plan, MAX_PLAN_BYTES), request_hash, _hash(plan)))
            state = {"status": "prepared", "updated_at": now, "started_at": None, "finished_at": None,
                     "cancel_requested_at": None, "executor_id": None, "error": None, "result": None}
            return self._append(db, plan, None, "", state)

    def get(self, run_id):
        _id(run_id)
        with self.store._connect() as db:
            _require(db)
            plan, state, _ = self._read(db, run_id)
            return self._public(plan, state)

    def list(self, *, offset=0, limit=50, archived=None):
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Analysis run pagination requires offset >= 0 and limit between 1 and 100")
        with self.store._connect() as db:
            _require(db)
            where, extra = archive.where(db, "analysis_run", archived)
            rows = db.execute("SELECT id FROM analysis_run_plans" + where + " ORDER BY rowid LIMIT ? OFFSET ?",
                              (*extra, limit + 1, offset)).fetchall()
            result, cache = [], {}
            for row in rows[:limit]:
                plan, state, _ = self._read(db, row[0], cache)
                result.append({key: value for key, value in self._public(plan, state).items() if key not in {"document", "bindings"}})
            return {"runs": result, "next_offset": offset + limit if len(rows) > limit else None}

    def _claim(self, run_id, *, executor_id):
        _id(run_id)
        _id(executor_id)
        with self.store._connect(write=True) as db:
            _require(db)
            plan, state, previous_hash = self._read(db, run_id)
            if state["status"] != "prepared":
                return self._public(plan, state), False
            now = _now()
            next_state = {**state, "status": "running", "updated_at": now, "started_at": now, "executor_id": executor_id}
            return self._append(db, plan, state, previous_hash, next_state), True

    def cancel(self, run_id):
        _id(run_id)
        with self.store._connect(write=True) as db:
            _require(db)
            plan, state, previous_hash = self._read(db, run_id)
            if state["status"] not in {"prepared", "running"}:
                return self._public(plan, state)
            now = _now()
            changes = {"status": "cancel_requested", "updated_at": now, "cancel_requested_at": now}
            if state["status"] == "prepared":
                changes.update(status="cancelled", finished_at=now,
                               error={"code": "cancelled_before_start", "message": "Cancelled before analysis execution"})
            return self._append(db, plan, state, previous_hash, {**state, **changes})

    def _finish(self, run_id, *, executor_id, status, error=None, result=None, guard=None):
        """Settle an owned attempt after the optional executor publication fence.

        ``guard`` runs inside the acquired write transaction immediately before
        appending. It must be a nonblocking, lock-free event check; exceptions
        roll back the transaction. Existing terminal receipts bypass the fence.
        """
        _id(run_id)
        _id(executor_id)
        if type(status) is not str or status not in TERMINAL:
            raise ProjectError("Invalid terminal analysis status")
        if guard is not None and not callable(guard):
            raise ProjectError("Analysis publication guard must be callable")
        error = _error(error)
        with self.store._connect(write=True) as db:
            _require(db)
            plan, state, previous_hash = self._read(db, run_id)
            if state["executor_id"] != executor_id:
                raise RevisionConflict("Analysis run belongs to another execution owner")
            result = _result(result, plan)
            if state["status"] in TERMINAL:
                if (state["status"] != status or _pack(state["error"], MAX_EVENT_BYTES) != _pack(error, MAX_EVENT_BYTES)
                        or _pack(state["result"], MAX_EVENT_BYTES) != _pack(result, MAX_EVENT_BYTES)):
                    raise RevisionConflict("Analysis run already has a different terminal outcome")
                return self._public(plan, state)
            if state["status"] not in {"running", "cancel_requested"}:
                raise RevisionConflict("Analysis run has not entered execution")
            if guard is not None:
                guard()
            now = _now()
            return self._append(db, plan, state, previous_hash,
                                {**state, "status": status, "updated_at": now, "finished_at": now, "error": error, "result": result})

    def _recover(self, run_id):
        """Only call while the executor holds this run's otherwise vacant OS lease."""
        _id(run_id)
        with self.store._connect(write=True) as db:
            _require(db)
            plan, state, previous_hash = self._read(db, run_id)
            if state["status"] not in {"running", "cancel_requested"}:
                return self._public(plan, state)
            now = _now()
            return self._append(db, plan, state, previous_hash,
                {**state, "status": "unknown", "updated_at": now, "finished_at": now,
                 "error": {"code": "execution_interrupted", "message": "The execution owner is gone; this run will not be replayed"}})
