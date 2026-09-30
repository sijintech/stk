"""Explicit local execution of frozen project analyses, with durable single-attempt claims.

The shared graph worker owns its serial lane and process cancellation. This coordinator never
replays an interrupted claim, executes during a read, or resolves a live project input file.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
from uuid import uuid4

from suan.project.snapshots import _reader, _signature, _sync_directory
from suan.project.store import ProjectError, _id
from .protocol import BridgeError

MAX_ACTIVE_RUNS = 4
MAX_BYTES = 256 * 1024 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 300
CHUNK = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HELD = set()
_HELD_GUARD = threading.Lock()


def _directory(root, parts, *, create=False):
    path = Path(root)
    for part in parts:
        path = path / part
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ProjectError("Analysis run directories must not be files or symbolic links")
        if create:
            existed = path.exists()
            path.mkdir(mode=0o700, exist_ok=True)
            if not existed:
                _sync_directory(path.parent)
    return path


class _Lease:
    """Never unlink lease files: replacement would let two processes own one run."""
    def __init__(self, store, run_id):
        _id(run_id)
        directory = _directory(store.directory, (".stk", "analysis-run-locks"), create=True)
        path = directory / (run_id + ".lock")
        if path.is_symlink():
            raise ProjectError("Analysis run locks must not be symbolic links")
        self.key, self.stream = os.path.normcase(str(path)), None
        with _HELD_GUARD:
            if self.key in _HELD:
                raise BridgeError("busy", "A live executor owns this analysis run")
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            stream = os.fdopen(fd, "r+b", buffering=0)
            try:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ProjectError("Analysis run locks must be regular files")
                if os.name == "nt":
                    import msvcrt
                    if info.st_size == 0:
                        stream.write(b"0")
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                stream.close()
                raise BridgeError("busy", "A live executor owns this analysis run") from None
            except BaseException:
                stream.close()
                raise
            self.stream = stream
            _HELD.add(self.key)

    def release(self):
        with _HELD_GUARD:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
                _HELD.discard(self.key)


@dataclass
class _Job:
    store: object
    run: dict
    lease: _Lease
    owner: str
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    timed_out: bool = False
    thread: object = None


class _Cancellation(threading.Event):
    def __init__(self, closing):
        super().__init__()
        self.closing = closing

    def is_set(self):
        return super().is_set() or self.closing.is_set()


class _PublicationCancelled(Exception):
    pass


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise BridgeError("cancelled", "Analysis execution cancelled")


def _copy_verified(source, target, digest, size, remaining, cancel=None):
    """Copy and hash the same open bytes; never hardlink an input or trust cache existence."""
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
        raise ProjectError("Invalid analysis artifact digest")
    if source.is_symlink():
        raise ProjectError("Analysis artifacts must not be symbolic links")
    _check(cancel)
    checksum, count = hashlib.sha256(), 0
    with _reader(source) as reader:
        before = os.fstat(reader.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > remaining:
            raise ProjectError("Analysis artifact is not a regular file within the byte budget")
        if size is not None and before.st_size != size:
            raise ProjectError("Analysis artifact size does not match its frozen manifest")
        writer = target.open("xb") if target is not None else None
        try:
            while True:
                _check(cancel)
                block = reader.read(CHUNK)
                if not block:
                    break
                count += len(block)
                if count > remaining or (size is not None and count > size):
                    raise ProjectError("Analysis artifact exceeds its byte budget")
                checksum.update(block)
                if writer is not None:
                    writer.write(block)
            after = os.fstat(reader.fileno())
            final = source.stat(follow_symlinks=False)
            if (not stat.S_ISREG(final.st_mode) or _signature(before)[:4] != _signature(after)[:4]
                    or _signature(after)[:4] != _signature(final)[:4] or count != after.st_size
                    or checksum.hexdigest() != digest):
                raise ProjectError("Analysis artifact changed or its checksum does not match")
            if writer is not None:
                writer.flush()
                os.fsync(writer.fileno())
        finally:
            if writer is not None:
                writer.close()
    if target is not None:
        _sync_directory(target.parent)
    return count


def _json_bytes(value):
    # Bound traversal before recursive encoding/validators, including hand-edited archives.
    stack, count, ancestors = [(value, 0, False)], 0, set()
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            ancestors.remove(id(current))
            continue
        count += 1
        if depth > 64 or count > MAX_RESULT_BYTES:
            raise ProjectError("Analysis result exceeds its JSON depth or item limit")
        if type(current) in (dict, list):
            if id(current) in ancestors:
                raise ProjectError("Analysis result JSON contains a cycle")
            ancestors.add(id(current))
            stack.append((current, depth, True))
            if type(current) is dict:
                if any(type(key) is not str for key in current):
                    raise ProjectError("Analysis result JSON keys must be strings")
                stack.extend((key, depth + 1, False) for key in current)
                stack.extend((child, depth + 1, False) for child in current.values())
            else:
                stack.extend((child, depth + 1, False) for child in current)
        elif type(current) is str:
            if len(current) > MAX_RESULT_BYTES:
                raise ProjectError("Analysis result string exceeds its byte limit")
        elif current is not None and type(current) not in (bool, int, float):
            raise ProjectError("Analysis result must contain plain JSON values")
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise ProjectError("Analysis result is not finite UTF-8 JSON") from None
    if len(raw) > MAX_RESULT_BYTES:
        raise ProjectError("Analysis result exceeds its 4 MiB JSON limit")
    return raw


@lru_cache(maxsize=1)
def _payload_schema():
    from suan.contracts import load_schema
    from .schema import _inline
    schema = load_schema("payload-2")
    # payload/2 embeds the separately published view contract; the bridge helper only
    # inlines local references, so resolve this one external document in its own scope.
    view = load_schema("view-1")
    schema["properties"]["view"] = _inline(view, view)
    return _inline(schema, schema)


def _result_info(document, frozen):
    from suan.graph.schema import check_value, graph_hash
    raw = _json_bytes(document)
    if (type(document) is not dict or document.get("schema") != "stk.graph-result/1"
            or type(document.get("outputs")) is not dict or len(document["outputs"]) > 256):
        raise ProjectError("Invalid analysis graph result")
    expected_hash = graph_hash(frozen["graph"])
    if document.get("graph_hash") != expected_hash or document.get("graph_sha256") != expected_hash[7:]:
        raise ProjectError("Analysis result graph identity does not match the frozen graph")
    if "errors" in document and type(document["errors"]) is not list:
        raise ProjectError("Invalid analysis output errors")
    selected = set(frozen["outputs"])
    if (set(document["outputs"]) - selected or
            (not document.get("errors") and set(document["outputs"]) != selected)):
        raise ProjectError("Analysis result outputs do not match the explicit selection")
    parameters = document.get("parameters")
    declared = {item["name"] for item in frozen["graph"].get("parameters", [])}
    if (type(parameters) is not dict or not declared.issubset(parameters)
            or any(type(item) is not dict or "value" not in item or
                   ("choices" in item and type(item["choices"]) is not list)
                   for item in parameters.values())):
        raise ProjectError("Invalid resolved analysis parameter metadata")
    blobs, has_payload = {}, False

    def add(digest, size=None):
        if type(digest) is not str or _SHA.fullmatch(digest) is None:
            raise ProjectError("Analysis result contains an invalid blob reference")
        if size is not None and (type(size) is not int or not 0 <= size <= MAX_BYTES):
            raise ProjectError("Analysis result contains an invalid blob size")
        previous = blobs.get(digest)
        if previous is not None and size is not None and previous != size:
            raise ProjectError("Analysis blob references disagree about their size")
        blobs[digest] = size if size is not None else previous
        if len(blobs) > 4096:
            raise ProjectError("Analysis result references too many blobs")

    for output in document["outputs"].values():
        if type(output) is not dict or output.get("type") not in {"payload", "image", "table", "plot", "value", "dataset", "file"}:
            raise ProjectError("Analysis result contains an invalid output")
        for key in ("blob", "data_blob"):
            if key in output:
                add(output[key], output.get("size") if key == "blob" else None)
        if output["type"] == "payload":
            manifest = output.get("manifest")
            if check_value(manifest, _payload_schema()):
                raise ProjectError("Analysis result contains an invalid payload manifest")
            has_payload = True
            for buffer in manifest["buffers"]:
                digest = buffer.get("sha256")
                if buffer.get("uri") != "sha256:" + str(digest):
                    raise ProjectError("Archived payload buffers must use SHA256 references")
                add(digest, buffer["byteLength"])
    return raw, blobs, {"graph_hash": expected_hash[7:], "output_count": len(document["outputs"]),
                        "has_payload": has_payload, "has_errors": bool(document.get("errors"))}


class AnalysisRunExecutor:
    def __init__(self, worker, blob_dir):
        self.worker, self.blob_dir = worker, Path(blob_dir)
        self.executor_id = str(uuid4())
        self._lock, self._closing = threading.RLock(), threading.Event()
        self._jobs = {}

    @staticmethod
    def _key(store, run_id):
        return os.path.normcase(str(store.path)), store._project_id, run_id

    def start(self, store, run_id):
        with self._lock:
            if self._closing.is_set():
                raise BridgeError("shutting_down", "Analysis executor is closed")
            record = store.analysis_runs.get(run_id)
            if record["status"] != "prepared":
                return record
            if len(self._jobs) >= MAX_ACTIVE_RUNS:
                raise BridgeError("busy", "The local executor has reached its 4-analysis limit")
            lease = _Lease(store, run_id)
            try:
                record, claimed = store.analysis_runs._claim(run_id, executor_id=self.executor_id)
                if not claimed:
                    lease.release()
                    return record
                if self._closing.is_set():
                    record = store.analysis_runs._finish(run_id, executor_id=self.executor_id, status="cancelled",
                        error={"code": "cancelled", "message": "Analysis executor closed before dispatch"})
                    lease.release()
                    return record
                job = _Job(store, deepcopy(record), lease, self.executor_id, cancel=_Cancellation(self._closing))
                job.thread = threading.Thread(target=self._run, args=(job,), daemon=True,
                                              name="stk-analysis-" + run_id)
                self._jobs[self._key(store, run_id)] = job
                try:
                    job.thread.start()
                except BaseException:
                    self._jobs.pop(self._key(store, run_id), None)
                    store.analysis_runs._finish(run_id, executor_id=self.executor_id, status="failed",
                                               error={"code": "executor_unavailable", "message": "The local execution thread could not start"})
                    raise
                return record
            except BaseException:
                lease.release()
                raise

    def _stage(self, job):
        root = _directory(job.store.directory, (".stk", "analysis-runs", job.run["id"]), create=True)
        stage = root / ("stage-" + uuid4().hex)
        stage.mkdir(mode=0o700)
        local, total = {}, 0
        try:
            for binding, files in job.run["bindings"].items():
                directory = _directory(stage, (binding,), create=True)
                local[binding] = str(directory)
                for relative, metadata in files.items():
                    parts = relative.split("/")
                    parent = _directory(directory, parts[:-1], create=True)
                    source = job.store.snapshots._object(metadata["sha256"])
                    total += _copy_verified(source, parent / parts[-1], metadata["sha256"],
                                            metadata["size"], MAX_BYTES - total, job.cancel)
            return stage, local
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _archive(self, job, document):
        raw, blobs, summary = _result_info(document, job.run["document"])
        parent = _directory(job.store.directory, (".stk", "analysis-runs", job.run["id"]), create=True)
        target = parent / "result"
        if target.exists() or target.is_symlink():
            raise ProjectError("Analysis result archive already exists; it will not be replaced or adopted")
        temporary = parent / ("result-" + uuid4().hex + ".part")
        temporary.mkdir(mode=0o700)
        try:
            total = len(raw)
            if total > MAX_BYTES:
                raise ProjectError("Analysis manifest exceeds the archive byte budget")
            for digest, size in blobs.items():
                source = _directory(self.blob_dir, (digest[:2],)) / digest
                destination = _directory(temporary, ("blobs", digest[:2]), create=True) / digest
                total += _copy_verified(source, destination, digest, size, MAX_BYTES - total, job.cancel)
            _directory(temporary, ("blobs",), create=True)
            with (temporary / "graph-result.json").open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(temporary)
            _check(job.cancel)
            if target.exists() or target.is_symlink():
                raise ProjectError("Analysis result archive appeared before publication")
            os.rename(temporary, target)
            _sync_directory(parent)
            return {"directory": target.relative_to(job.store.directory).as_posix(),
                    "manifest_sha256": hashlib.sha256(raw).hexdigest(), **summary, "size_bytes": total}
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def _observe_cancel(self, job):
        deadline = time.monotonic() + MAX_SECONDS
        while not job.done.wait(0.1):
            if self._closing.is_set() or job.cancel.is_set():
                job.cancel.set()
                return
            if time.monotonic() >= deadline:
                job.timed_out = True
                job.cancel.set()
                return
            try:
                if job.store.analysis_runs.get(job.run["id"])["status"] == "cancel_requested":
                    job.cancel.set()
                    return
            except (ProjectError, OSError):
                # Losing the journal prevents honest publication; stop this run only.
                job.cancel.set()
                return

    def _run(self, job):
        stage, result = None, None
        status, error = "unknown", {"code": "execution_interrupted", "message": "Analysis execution was interrupted"}
        observer = threading.Thread(target=self._observe_cancel, args=(job,), daemon=True,
                                    name="stk-analysis-cancel")
        try:
            observer.start()
            stage, local = self._stage(job)
            frozen = job.run["document"]
            work = {"request": {"graph": frozen["graph"], "parameters": frozen["parameters"],
                                 "outputs": frozen["outputs"], "profile": job.run["profile"],
                                 "budget": job.run["budget"]}, "local_bindings": local}
            _check(job.cancel)
            document = self.worker.evaluate("analysis-" + job.run["id"], work, job.cancel, lambda event: None)
            _check(job.cancel)
            result = self._archive(job, document)
            status = "failed" if result["has_errors"] else "succeeded"
            error = ({"code": "partial_outputs", "message": "Some requested analysis outputs failed; inspect the archived result"}
                     if result["has_errors"] else None)
        except BridgeError as exc:
            if exc.code == "cancelled":
                status = "failed" if job.timed_out else "cancelled"
                error = {"code": "time_budget_exceeded" if job.timed_out else "cancelled",
                         "message": "Analysis exceeded its 300 second time budget" if job.timed_out else "Analysis execution cancelled"}
            elif exc.code == "graph_error":
                status, error = "failed", {"code": "graph_error", "message": exc.message[:1000]}
            else:
                status, error = "unknown", {"code": "execution_interrupted", "message": "The local graph worker stopped without a confirmed result"}
        except (ProjectError, OSError, ValueError, TypeError):
            status, error = "failed", {"code": "artifact_invalid", "message": "Analysis input or result verification failed"}
        finally:
            job.done.set()
            try:
                def publish_guard():
                    if result is not None and job.cancel.is_set():
                        raise _PublicationCancelled()
                try:
                    # Check after BEGIN IMMEDIATE, not while waiting for its lock. Once admitted
                    # to this atomic transaction, a complete verified result may win a close.
                    job.store.analysis_runs._finish(job.run["id"], executor_id=job.owner,
                        status=status, error=error, result=result, guard=publish_guard)
                except _PublicationCancelled:
                    job.store.analysis_runs._finish(job.run["id"], executor_id=job.owner,
                        status="failed" if job.timed_out else "cancelled",
                        error={"code": "time_budget_exceeded" if job.timed_out else "cancelled",
                               "message": "Analysis execution stopped before result publication"})
            except (ProjectError, OSError):
                pass  # The committed claim stays recoverable as unknown, never automatically replayed.
            finally:
                if stage is not None:
                    shutil.rmtree(stage, ignore_errors=True)
                with self._lock:
                    self._jobs.pop(self._key(job.store, job.run["id"]), None)
                    job.lease.release()

    def cancel(self, store, run_id):
        with self._lock:
            record = store.analysis_runs.cancel(run_id)
            job = self._jobs.get(self._key(store, run_id))
            if job is not None:
                job.cancel.set()
            return record

    def recover(self, store, run_id):
        lease = _Lease(store, run_id)
        try:
            return store.analysis_runs._recover(run_id)
        finally:
            lease.release()

    def close_project(self, store):
        # Called inside the session close fence. No SQLite or worker wait under its global lock.
        with self._lock:
            for key, job in self._jobs.items():
                if key[:2] == self._key(store, "")[:2]:
                    job.cancel.set()

    def shutdown(self, *, wait=False):
        self._closing.set()
        # A blocked SQLite claim must not delay the bridge's immediate closing fence.
        if not self._lock.acquire(blocking=wait):
            return  # Observers also see _closing and signal their own cancellation.
        try:
            jobs = list(self._jobs.values())
            for job in jobs:
                job.cancel.set()
        finally:
            self._lock.release()
        if wait:
            deadline = time.monotonic() + 2
            for job in jobs:
                job.thread.join(max(0, deadline - time.monotonic()))

    def result(self, store, run_id):
        run = store.analysis_runs.get(run_id)
        summary = run["result"]
        if summary is None:
            raise BridgeError("conflict", "This analysis run has no archived result")
        try:
            return self._read_result(store, run)
        except (FileNotFoundError, PermissionError):
            raise BridgeError("unavailable", "The archived analysis result is missing or inaccessible", retryable=False) from None

    def _read_result(self, store, run):
        run_id, summary = run["id"], run["result"]
        directory = _directory(store.directory, (".stk", "analysis-runs", run_id, "result"))
        manifest = directory / "graph-result.json"
        _copy_verified(manifest, None, summary["manifest_sha256"], None, MAX_RESULT_BYTES)
        with _reader(manifest) as stream:
            raw = stream.read(MAX_RESULT_BYTES + 1)
        if len(raw) > MAX_RESULT_BYTES or hashlib.sha256(raw).hexdigest() != summary["manifest_sha256"]:
            raise ProjectError("Archived analysis manifest changed while being read")
        from .protocol import decode_line
        # Do not reuse the much smaller editable-document decoder (384 KiB): archived
        # graph results deliberately permit 4 MiB, while _result_info bounds nesting.
        try:
            document = decode_line(raw)
        except BridgeError:
            raise ProjectError("Archived analysis manifest is not strict JSON") from None
        canonical, blobs, metadata = _result_info(document, run["document"])
        if canonical != raw or any(summary[key] != value for key, value in metadata.items()):
            raise ProjectError("Archived analysis metadata does not match the journal")
        total = len(raw)
        for digest, size in blobs.items():
            source = _directory(directory, ("blobs", digest[:2])) / digest
            total += _copy_verified(source, None, digest, size, MAX_BYTES - total)
        if total != summary["size_bytes"]:
            raise ProjectError("Archived analysis size does not match the journal")
        return {"run": run, "result": document, "blob_dir": str(directory / "blobs")}
