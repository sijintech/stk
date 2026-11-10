"""Local, durable intent records for explicit MuPRO preflight tasks.

This journal is outside projects. Reopening, listing and closing never contact a
Runtime. Reserve confirms a durable ID before a separate execution RPC may be
sent. Only explicit retry (or the compatibility submit helper) may POST; refresh
reads the original task. An operation lease survives no process crash, while its
immutable request does.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import stat
import threading
from uuid import UUID

from suan.mupro.client import read_preflight
from suan.mupro.preflight import MAX_OBSERVATION_BYTES, OBSERVATION_NAME, parse_observation
from suan.mupro.spec import preflight_spec
from suan.runtime.common import atomic_json, now
from suan.runtime.models import TaskSpec
from . import mupro_preflight as adapter
from .protocol import BridgeError, ERROR_CODES


MAX_RECORD_BYTES = 128 * 1024
MAX_RECORDS = 4096  # Refuse new work, never silently prune unresolved requests.
_OPTIONS = frozenset({"backend", "walltime_seconds", "memory_mb", "queue", "account", "name"})
_REQUEST = frozenset({"connection", "expected_connection_identity", "workspace_id", "options", "idempotency_key"})
_FIELDS = frozenset({"id", "project_id", "request", "workspace_id", "task_id", "phase", "task_state",
                     "task_exit_code", "result", "error", "created_at", "updated_at"})
_PHASES = frozenset({"prepared", "creating_workspace", "submitting", "unknown", "accepted", "running", "finished", "error"})
_STATES = frozenset({"preparing", "submitting", "queued", "running", "succeeded", "failed", "cancelled", "unknown"})


def _link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) &
                                            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{%d}" % length, value) is not None


def _project(value):
    try:
        valid = isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise BridgeError("invalid_params", "Expected a canonical project UUID")
    return value


def _closed(params, fields):
    if not isinstance(params, dict) or set(params) != set(fields):
        raise BridgeError("invalid_params", "Unexpected MuPRO preflight parameters")


def _request(params):
    _closed(params, _REQUEST)
    connection, identity = params["connection"], params["expected_connection_identity"]
    if (not isinstance(connection, str) or not connection or len(connection) > 256
            or any(ord(ch) < 32 for ch in connection) or not _hex(identity, 16)
            or not _hex(params["idempotency_key"], 32)
            or (params["workspace_id"] is not None and not _hex(params["workspace_id"], 32))):
        raise BridgeError("invalid_params", "Invalid MuPRO preflight request identity")
    options = params["options"]
    if not isinstance(options, dict) or set(options) - _OPTIONS:
        raise BridgeError("invalid_params", "Unsupported MuPRO preflight options")
    try:
        spec = TaskSpec(**preflight_spec(params["workspace_id"] or "0" * 32, **options)).to_dict()
    except (ValueError, TypeError, KeyError):
        raise BridgeError("invalid_params", "Invalid MuPRO preflight execution options") from None
    canonical = {"backend": spec["backend"], "name": spec["name"]}
    canonical.update({k: v for k, v in spec["resources"].items() if k != "cpus"})
    return {**params, "options": canonical}


def _storage_error():
    return BridgeError("unavailable", "MuPRO preflight journal is unavailable or invalid; preserve the original key",
                       retryable=False)


def _safe_error(error):
    # Remote diagnostics can contain paths, hosts and arbitrary data. Persist only a
    # stable code and our own text; never a backend message or its data object.
    code = error.code if isinstance(error, BridgeError) else "remote_error"
    return BridgeError(code, "MuPRO preflight operation could not be verified; retain the original request and key",
                       retryable=False).to_json()


def _lock(path, blocking):
    stream = None
    try:
        if _link(path):
            raise OSError("Invalid lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        stream = os.fdopen(fd, "r+b")
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise OSError("Invalid lock")
        if os.name == "nt":
            import msvcrt
            if not os.fstat(fd).st_size:
                stream.write(b"0"); stream.flush()
            stream.seek(0)
            msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return stream
    except OSError as error:
        if stream is not None:
            stream.close()
        if not blocking and error.errno in {errno.EACCES, errno.EAGAIN}:
            return None
        raise _storage_error() from None


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid timestamp")
    if datetime.fromisoformat(value).utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("Invalid timestamp")


def _cached_result(value, record):
    if (not isinstance(value, dict) or set(value) != {"schema", "scope", "target", "task", "artifact", "observation"}
            or value["schema"] != "stk.mupro-preflight-result/1" or value["scope"] != "runtime_task"):
        raise ValueError("Invalid cached result")
    target, task, artifact = value["target"], value["task"], value["artifact"]
    if (not isinstance(target, dict) or set(target) != {"profile", "connection_sha256"}
            or target["profile"] is not None or not _hex(target["connection_sha256"], 64)
            or target["connection_sha256"][:16] != record["request"]["expected_connection_identity"]
            or not isinstance(task, dict) or set(task) != {"id", "workspace_id", "backend", "state", "exit_code"}
            or task["id"] != record["task_id"] or task["workspace_id"] != record["workspace_id"]
            or task["backend"] != record["request"]["options"]["backend"]
            or type(task["exit_code"]) is not int
            or not isinstance(artifact, dict) or set(artifact) != {"path", "size", "sha256"}
            or artifact["path"] != OBSERVATION_NAME or not _hex(artifact["sha256"], 64)
            or type(artifact["size"]) is not int or not 1 <= artifact["size"] <= MAX_OBSERVATION_BYTES):
        raise ValueError("Invalid cached result binding")
    observation = parse_observation(json.dumps(value["observation"], ensure_ascii=False, allow_nan=False,
                                               separators=(",", ":")).encode())
    failed = observation["summary"] == "checks_failed"
    if task["state"] != ("failed" if failed else "succeeded") or task["exit_code"] != int(failed):
        raise ValueError("Invalid cached completion")
    if task["state"] != record["task_state"] or task["exit_code"] != record["task_exit_code"]:
        raise ValueError("Invalid cached task state")


def _validate(record, key):
    if not isinstance(record, dict) or set(record) != _FIELDS or record["id"] != key or not _hex(key, 32):
        raise ValueError("Invalid journal record")
    _project(record["project_id"])
    request = _request(record["request"])
    if request != record["request"] or request["idempotency_key"] != key:
        raise ValueError("Invalid journal request")
    workspace, task = record["workspace_id"], record["task_id"]
    if ((workspace is not None and not _hex(workspace, 32)) or (task is not None and not _hex(task, 32))
            or (request["workspace_id"] is not None and workspace != request["workspace_id"])
            or (task is not None and workspace is None)
            or not isinstance(record["phase"], str) or record["phase"] not in _PHASES
            or (record["task_state"] is not None and (not isinstance(record["task_state"], str) or record["task_state"] not in _STATES))
            or (record["task_exit_code"] is not None and type(record["task_exit_code"]) is not int)):
        raise ValueError("Invalid journal state")
    if record["phase"] in {"accepted", "running", "finished"} and task is None:
        raise ValueError("Missing accepted task")
    if record["phase"] == "prepared" and (workspace != request["workspace_id"] or task is not None
            or any(record[field] is not None for field in ("task_state", "task_exit_code", "result", "error"))):
        raise ValueError("Invalid prepared intent")
    for field in ("created_at", "updated_at"):
        _timestamp(record[field])
    error = record["error"]
    if error is not None and (not isinstance(error, dict) or set(error) != {"code", "message", "retryable"}
                              or not isinstance(error["code"], str) or error["code"] not in ERROR_CODES
                              or error != _safe_error(BridgeError(error["code"], ""))):
        raise ValueError("Invalid journal error")
    if record["result"] is not None:
        if record["phase"] != "finished":
            raise ValueError("Unexpected cached result")
        _cached_result(record["result"], record)
    if record["phase"] == "finished" and record["result"] is None:
        raise ValueError("Missing verified result")


def _decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate key")
            value[key] = item
        return value

    def constant(_):
        raise ValueError("Nonfinite value")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class MuproPreflightService:
    def __init__(self, backend_resolver, state_dir):
        self.resolve = backend_resolver
        # state_dir is host configuration under the Bridge's lifetime lock, never
        # request data. Bind its configured destination once; managed children may
        # not redirect this journal through links/reparse points.
        self.root = Path(state_dir).resolve() / "mupro-preflight"
        self.mutex = threading.RLock()
        self.closed = False
        # A corrupt record blocks recovery; it must never become a guessed fresh request.
        with self._transaction():
            for path in self._paths():
                record = self._read(path.stem)
                lease = _lock(self.root / (path.stem + ".operation.lock"), False)
                if lease is not None:
                    try:
                        if record["phase"] in {"creating_workspace", "submitting"}:
                            record.update(phase="unknown", error=_safe_error(BridgeError("unavailable", "")))
                            self._write(record)
                    finally:
                        lease.close()

    def close(self):
        with self.mutex:
            self.closed = True

    def _open(self):
        if self.closed:
            raise BridgeError("shutting_down", "MuPRO preflight service is closed")

    @contextmanager
    def _transaction(self):
        with self.mutex:
            try:
                if _link(self.root):
                    raise OSError("Invalid directory")
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                if _link(self.root) or not self.root.is_dir():
                    raise OSError("Invalid directory")
                os.chmod(self.root, 0o700)
                lock = _lock(self.root / ".journal.lock", True)
                try:
                    yield
                finally:
                    lock.close()
            except (OSError, ValueError, TypeError, RecursionError):
                raise _storage_error() from None

    def _paths(self):
        paths = []
        operation_keys = []
        for path in self.root.iterdir():
            if path.suffix == ".json":
                if not _hex(path.stem, 32) or len(paths) >= MAX_RECORDS:
                    raise _storage_error()
                paths.append(path)
            elif path.name.endswith(".operation.lock"):
                if len(operation_keys) >= MAX_RECORDS:
                    raise _storage_error()
                operation_keys.append(path.name.removesuffix(".operation.lock"))
        keys = {path.stem for path in paths}
        if any(not _hex(key, 32) or key not in keys for key in operation_keys):
            raise _storage_error()  # A lost intent is not permission to reuse/redefine its key.
        return paths

    def _read(self, key):
        path = self.root / (key + ".json")
        try:
            if _link(path):
                raise _storage_error()
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError:
            return None
        try:
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_RECORD_BYTES:
                    raise ValueError("Invalid journal file")
                raw = stream.read(MAX_RECORD_BYTES + 1)
            if len(raw) > MAX_RECORD_BYTES:
                raise ValueError("Oversized journal")
            record = _decode(raw)
            _validate(record, key)
            return record
        except (OSError, ValueError, TypeError, RecursionError, BridgeError):
            raise _storage_error() from None

    def _write(self, record):
        record = deepcopy(record)
        record["updated_at"] = now()
        _validate(record, record["id"])
        if len(json.dumps(record, ensure_ascii=False, allow_nan=False).encode()) > MAX_RECORD_BYTES:
            raise _storage_error()
        atomic_json(self.root / (record["id"] + ".json"), record)
        if os.name != "nt":
            fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return record

    def _update(self, key, **changes):
        with self._transaction():
            record = self._read(key)
            if record is None:
                raise _storage_error()
            record.update(changes)
            return self._write(record)

    def _admit(self, key, backend, request, phase):
        self._binding(backend, request)
        # Admission is the execution linearization point. close() prevents later
        # admissions; already admitted I/O may finish and persist its identity.
        with self._transaction():
            self._open()
            record = self._read(key)
            if record is None:
                raise _storage_error()
            record.update(phase=phase, error=None)
            return self._write(record)

    def _backend(self, request):
        self._open()
        backend = self.resolve({key: request[key] for key in ("connection", "expected_connection_identity")})
        self._binding(backend, request)
        return backend

    @staticmethod
    def _binding(backend, request):
        value = adapter.describe(backend)
        if value != {key: request[source] for key, source in (
                ("connection", "connection"), ("connection_identity", "expected_connection_identity"))}:
            raise BridgeError("conflict", "The original MuPRO preflight target changed")

    def describe(self, params):
        self._open()
        _closed(params, {"connection"})
        if not isinstance(params["connection"], str) or not params["connection"] or len(params["connection"]) > 256:
            raise BridgeError("invalid_params", "A saved Runtime connection is required")
        return adapter.describe(self.resolve(dict(params)))

    def list(self, params):
        _closed(params, {"project_id"})
        project = _project(params["project_id"])
        with self._transaction():
            records = []
            for path in self._paths():
                record = self._read(path.stem)  # Validate even older/other-project files; never guess past damage.
                if record["project_id"] == project:
                    records.append(record)
                    records.sort(key=lambda item: (item["updated_at"], item["id"]), reverse=True)
                    del records[20:]
            return {"records": records}

    def reserve(self, params):
        """Persist an immutable intent, without even resolving an execution backend.

        The native caller must receive this acknowledgement before sending retry.
        Losing this reply therefore cannot leave a queued execution RPC behind.
        """
        self._open()
        _closed(params, _REQUEST | {"project_id"})
        project = _project(params["project_id"])
        request = _request({key: value for key, value in params.items() if key != "project_id"})
        key = request["idempotency_key"]
        with self._transaction():
            self._open()
            record = self._read(key)
            if record is not None:
                if record["project_id"] != project or record["request"] != request:
                    raise BridgeError("conflict", "This preflight key belongs to another request")
                return {"record": record}
            if len(self._paths()) >= MAX_RECORDS:
                raise _storage_error()
            lease = _lock(self.root / (key + ".operation.lock"), False)
            if lease is None:
                raise BridgeError("busy", "This MuPRO preflight request is already active")
            try:
                record = self._write({"id": key, "project_id": project, "request": request,
                    "workspace_id": request["workspace_id"], "task_id": None, "phase": "prepared",
                    "task_state": None, "task_exit_code": None, "result": None, "error": None,
                    "created_at": now(), "updated_at": now()})
                return {"record": record}
            finally:
                lease.close()

    def submit(self, params):
        """Compatibility helper for synchronous callers; never expose this as the native RPC."""
        record = self.reserve(params)["record"]
        return self.retry({"project_id": record["project_id"], "id": record["id"]})

    def _claim(self, params):
        self._open()
        _closed(params, {"project_id", "id"})
        project = _project(params["project_id"])
        if not _hex(params["id"], 32):
            raise BridgeError("invalid_params", "Expected a preflight record ID")
        with self._transaction():
            self._open()
            record = self._read(params["id"])
            if record is None:
                raise BridgeError("not_found", "MuPRO preflight request not found")
            if record["project_id"] != project:
                raise BridgeError("conflict", "MuPRO preflight request belongs to another project")
            return record, _lock(self.root / (record["id"] + ".operation.lock"), False)

    def retry(self, params):
        record, lease = self._claim(params)
        if lease is None:
            return {"record": record}
        try:
            if record["task_id"] is not None:
                return {"record": record}
            backend = self._backend(record["request"])
            return {"record": self._submit(record, backend)}
        finally:
            lease.close()

    def _submit(self, record, backend):
        key, request = record["id"], record["request"]
        try:
            if record["workspace_id"] is None:
                self._admit(key, backend, request, "creating_workspace")
                answer = backend.create_workspace("STK MuPRO preflight", "mupro-preflight:" + key + ":workspace")
                self._binding(backend, request)
                workspace = answer.get("workspace") if isinstance(answer, dict) else None
                workspace = workspace.get("id") if isinstance(workspace, dict) else None
                if not _hex(workspace, 32):
                    raise BridgeError("remote_error", "Invalid preflight workspace acknowledgement")
                record = self._update(key, workspace_id=workspace)
            self._admit(key, backend, request, "submitting")
            answer = adapter.submit(backend, {**request, "workspace_id": record["workspace_id"]})
            self._binding(backend, request)
            task = answer.get("task") if isinstance(answer, dict) else None
            if (not isinstance(task, dict) or not _hex(task.get("id"), 32)
                    or not isinstance(task.get("state"), str) or task["state"] not in _STATES
                    or (task.get("exit_code") is not None and type(task["exit_code"]) is not int)):
                raise BridgeError("remote_error", "Invalid preflight task acknowledgement")
            return self._update(key, task_id=task["id"], phase="accepted", task_state=task["state"],
                                task_exit_code=task.get("exit_code"), error=None)
        except (BridgeError, OSError, ValueError, TypeError, KeyError) as error:
            return self._update(key, phase="unknown", error=_safe_error(error))

    def refresh(self, params):
        record, lease = self._claim(params)
        if lease is None:
            return {"record": record}
        try:
            if record["task_id"] is None:
                return {"record": record}
            backend = self._backend(record["request"])
            request, key, task_id = record["request"], record["id"], record["task_id"]
            spec = TaskSpec(**preflight_spec(record["workspace_id"], **request["options"])).to_dict()
            try:
                task = backend.call(backend.client.task, task_id)
                self._binding(backend, request)
                if (not isinstance(task, dict) or task.get("id") != task_id
                        or TaskSpec(**task["spec"]).to_dict() != spec
                        or not isinstance(task.get("state"), str) or task["state"] not in _STATES
                        or (task.get("exit_code") is not None and type(task["exit_code"]) is not int)):
                    raise BridgeError("remote_error", "Invalid original preflight task")
                state = task["state"]
                record = self._update(key, task_state=state, task_exit_code=task.get("exit_code"), result=None, error=None,
                    phase="running" if state == "running" else "unknown" if state == "unknown" else "accepted")
                if state == "cancelled":
                    raise BridgeError("cancelled", "The original preflight task was cancelled")
                if state in {"succeeded", "failed"}:
                    self._open()
                    result = backend.call(read_preflight, backend.client, task_id, expected_spec=spec)
                    self._binding(backend, request)
                    record = self._update(key, phase="finished", result=result, error=None)
            except (BridgeError, OSError, ValueError, TypeError, KeyError) as error:
                record = self._update(key, phase="error", result=None, error=_safe_error(error))
            return {"record": record}
        finally:
            lease.close()
