"""Resumable, journaled uploads and downloads (spec §7).

Every transfer has a journal ``<state_dir>/transfers/<id>.json`` written atomically before and
during the work, so a bridge that crashed or was closed resumes where it stopped:

* **Uploads** use the Runtime's resumable upload sessions (``POST .../uploads`` returns the byte
  offset the Runtime already holds; ``PUT`` appends 1 MiB chunks; ``finish`` verifies size and
  sha256). The journal keeps each file's size, mtime and sha256, so a resumed upload re-hashes
  only files that changed; a changed file starts a new upload revision.
* **Uploads through a hub** send each file into the hub's blob store with the same kind of
  resumable session (``suan.control.uploads``), then create one ``workspace.import`` action (id
  derived from the transfer id and ``import_attempt``, so a resumed transfer re-reads the same
  action). Imports are always reviewed: the transfer stays ``running`` with ``action.state:
  "review"`` until the owner decides, without holding a transfer slot. A rejected or failed import
  fails the transfer; ``transfer.resume`` then asks again with a new action. ``transfer.cancel``
  rejects an import still in review. Resuming a cancelled transfer asks again once the original
  import's rejection is confirmed.
* **Downloads** append to ``<dest>.part`` next to the destination (its expected ``{path, size,
  sha256}`` in ``<dest>.part.json``), resume from the part's size, and move the file into place
  only after its sha256 matched the Runtime's listing (``checksum_mismatch`` otherwise; the part
  is discarded so a retry starts clean).

A transfer found in state ``queued``/``running`` when the bridge starts was interrupted; it is
marked ``interrupted`` and continues on ``transfer.resume`` (or ``hello`` with
``resume_transfers``). Progress is reported by ``transfer.updated`` events (state changes always,
progress at most every 250 ms).
"""
import hashlib
import os
from pathlib import Path
import threading
from contextvars import copy_context
from functools import wraps
import time
import uuid

from suan.control.limits import IMPORT_MAX_FILES, IMPORT_REQUEST_BYTES, encoded_size
from suan.runtime.common import atomic_json, inside, instance_lock, now, read_json
from suan.runtime.models import relative_path

from .backends import action_failure, action_id, summary
from .protocol import BridgeError

__all__ = ["TransferManager"]

CHUNK = 1024 * 1024
ACTIVE = {"queued", "running"}
FINAL = {"completed", "failed", "cancelled"}
MAX_FILES = 100_000
MAX_CONCURRENT = 4
PROGRESS_INTERVAL = 0.25
KEEP_FINISHED_SECONDS = 7 * 24 * 3600
REVIEW_POLL = 2.0


def _sha256(path, check=None):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            if check is not None:
                check()
            result.update(block)
    return result.hexdigest()


class _Stopped(Exception):
    """Internal: the transfer was paused (bridge shutdown) or cancelled."""


def _writer(method):
    """Keep admitted journal mutations inside the namespace owner's lifetime."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._activity:
            if self.stopping.is_set():
                raise BridgeError("shutting_down", "Transfers are shutting down")
            self._writers += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._writer_finished()
    return call


class TransferManager:
    def __init__(self, state_dir, emit, backend_for):
        self.root = Path(state_dir) / "transfers"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.emit = emit                  # emit(event, data)
        self.backend_for = backend_for    # backend_for(connection, node) -> backend
        self.lock = threading.RLock()
        self.threads = {}
        self.cancelled = set()
        self.notified = {}
        self.stopping = threading.Event()
        # Separate from self.lock: source preparation may hold that lock for a long time.
        self._activity = threading.Condition()
        self._writers = 0
        self._release_callback = None
        self._release_pending = False
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT)
        self.releasers = {}
        self._recover()

    # -- journal --------------------------------------------------------------------------------

    def _path(self, transfer_id):
        if (not isinstance(transfer_id, str) or len(transfer_id) != 32
                or any(c not in "0123456789abcdef" for c in transfer_id)):
            raise BridgeError("invalid_params", "A transfer id is 32 lowercase hexadecimal characters")
        return self.root / (transfer_id + ".json")

    def load(self, transfer_id):
        record = read_json(self._path(transfer_id))
        if record is None:
            raise BridgeError("not_found", "Unknown transfer")
        return record

    def save(self, record):
        record["updated_at"] = now()
        atomic_json(self._path(record["id"]), record)

    def _record_backend(self, record):
        backend = self.backend_for(record["connection"], record.get("node"))
        if record.get("connection_identity") is not None and backend.server_key != record["connection_identity"]:
            raise BridgeError("conflict", "The transfer Runtime endpoint changed; restore the original connection")
        return backend

    def _recover(self):
        cutoff = time.time() - KEEP_FINISHED_SECONDS
        for path in self.root.glob("*.json"):
            try:
                record = read_json(path)
            except (OSError, ValueError):
                continue
            if not isinstance(record, dict) or not isinstance(record.get("state"), str):
                continue
            if record["state"] in ACTIVE:
                record["state"] = "interrupted"
                self.save(record)
            elif record["state"] in FINAL and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                path.with_suffix(".lock").unlink(missing_ok=True)

    def public(self, record):
        """The transfer as the app sees it (spec ``Transfer``)."""
        keys = ("id", "kind", "state", "connection", "node", "workspace_id", "task_id", "local", "remote",
                "bytes_done", "bytes_total", "files_done", "files_total", "current", "sha256", "error", "action",
                "created_at", "updated_at")
        return {key: record[key] for key in keys if record.get(key) is not None}

    def list(self):
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                record = read_json(path)
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and "id" in record:
                records.append(self.public(record))
        records.sort(key=lambda r: r.get("created_at", ""))
        return records

    # -- starting -------------------------------------------------------------------------------

    @staticmethod
    def keyed_id(kind, key):
        """The transfer id of an idempotency key: ``sha256("<kind>.start\\0<key>")[:32]``."""
        return hashlib.sha256(f"{kind}.start\0{key}".encode("utf-8")).hexdigest()[:32]

    def _existing(self, kind, key, request, *, expected_connection_identity=None):
        """The journaled transfer of ``key`` (same request), ``None`` when there is none; else conflict."""
        if key is None:
            return None
        record = read_json(self._path(self.keyed_id(kind, key)))
        if record is None:
            return None
        if record.get("request") != request:
            raise BridgeError("conflict", f"The idempotency key names an earlier {kind} with a different request",
                              data={"transfer_id": record.get("id")})
        if expected_connection_identity is not None and record.get("connection_identity") != expected_connection_identity:
            raise BridgeError("conflict", "The earlier transfer does not match the expected Runtime endpoint",
                              data={"transfer_id": record.get("id")})
        return self.public(record)

    def _new(self, kind, key=None, request=None, *, connection_identity=None, **fields):
        if connection_identity is None:
            connection_identity = self.backend_for(fields["connection"], fields.get("node")).server_key
        record = {"id": self.keyed_id(kind, key) if key is not None else uuid.uuid4().hex, "kind": kind,
                  "state": "queued", "bytes_done": 0, "files_done": 0, "created_at": now(),
                  **fields, "connection_identity": connection_identity}
        if key is not None:
            record["idempotency_key"] = key
            record["request"] = request
        record["files_total"] = len(record["items"])
        record["bytes_total"] = sum(item["size"] for item in record["items"] if item["size"] is not None)
        self.save(record)
        return record

    @_writer
    def start_upload(self, connection, workspace_id, source, remote=None, node=None, idempotency_key=None):
        """A new upload, or with ``idempotency_key`` the transfer an earlier request with that key
        started (whatever its state now; a different request under the key is ``conflict``)."""
        request = {"connection": connection, "node": node, "workspace_id": workspace_id, "source": str(source),
                   "remote": remote}
        with self.lock:  # one transfer per key, also for concurrent repeats
            existing = self._existing("upload", idempotency_key, request)
            if existing is not None:
                return existing
            return self._start_upload(connection, workspace_id, source, remote, node, idempotency_key, request)

    def _start_upload(self, connection, workspace_id, source, remote, node, key, request):
        source = Path(source)
        if not source.is_absolute():
            raise BridgeError("invalid_params", "'source' must be an absolute local path")
        if source.is_symlink() or not source.exists():
            raise BridgeError("not_found", "The upload source does not exist or is a symbolic link")
        # remote "." puts a folder's contents at the workspace root (a file keeps its name there);
        # anything else must be a safe relative path (no "..", absolute paths, drive letters, ...).
        into_root = remote in (".", "./")
        if remote is not None and not into_root:
            try:
                remote = relative_path(remote)
            except ValueError as exc:
                raise BridgeError("invalid_params", f"Invalid remote path {remote!r}: {exc}") from None
        items = []
        if source.is_file():
            name = source.name if into_root else (remote or source.name)
            items.append(self._upload_item(source, name))
        elif source.is_dir():
            prefix = "" if into_root else (remote or source.name).strip("/")
            for directory, dirs, files in os.walk(source, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
                for file in sorted(files):
                    path = Path(directory) / file
                    if path.is_symlink() or not path.is_file():
                        continue
                    relative = path.relative_to(source).as_posix()
                    items.append(self._upload_item(path, f"{prefix}/{relative}" if prefix else relative))
                    if len(items) > MAX_FILES:
                        raise BridgeError("invalid_params", f"A folder upload is limited to {MAX_FILES} files")
            if not items:
                raise BridgeError("invalid_params", "The folder holds no regular files")
        else:
            raise BridgeError("invalid_params", "Upload a regular file or a folder")
        # Fail before starting when the connection is unknown (or a hub connection has no node).
        if self.backend_for(connection, node).kind == "hub":
            # The workspace.import request must fit the hub's caps (checked here, before any byte moves).
            if len(items) > IMPORT_MAX_FILES:
                raise BridgeError("invalid_params", f"An upload through a hub is limited to {IMPORT_MAX_FILES} "
                                  "files; upload the folder in parts")
            import_request = {"id": "0" * 32, "node_id": "0" * 32, "kind": "workspace.import", "payload": {
                "workspace_id": workspace_id, "files": [{"path": i["remote"], "sha256": "0" * 64, "size": i["size"]}
                                                        for i in items]}}
            if encoded_size(import_request) > IMPORT_REQUEST_BYTES:
                raise BridgeError("invalid_params", f"The file list of this upload exceeds the hub's "
                                  f"{IMPORT_REQUEST_BYTES}-byte import request limit; upload the folder in parts")
        record = self._new("upload", key, request, connection=connection, node=node, workspace_id=workspace_id,
                           local=str(source), remote=(source.name if into_root and source.is_file() else
                                                      remote or source.name), items=items)
        self._launch(record["id"])
        return self.public(record)

    @staticmethod
    def _upload_item(path, remote):
        try:
            remote = relative_path(remote)
        except ValueError as exc:
            raise BridgeError("invalid_params", f"Invalid remote path {remote!r}: {exc}") from None
        info = path.stat()
        return {"local": str(path), "remote": remote, "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                "sha256": None, "done": False}

    @_writer
    def start_download(self, connection, owner, owner_id, path, dest, node=None, idempotency_key=None,
                       *, expected_connection_identity=None, cache_directory=None):
        """A new download, or with ``idempotency_key`` the transfer an earlier request with that key
        started (a different request under the key is ``conflict``)."""
        request = {"connection": connection, "node": node, "owner": owner, "owner_id": owner_id, "path": path,
                   "dest": str(dest)}
        with self.lock:
            existing = self._existing("download", idempotency_key, request,
                                      expected_connection_identity=expected_connection_identity)
            if existing is not None:
                return existing
            return self._start_download(connection, owner, owner_id, path, dest, node, idempotency_key, request,
                                        expected_connection_identity, cache_directory)

    def _start_download(self, connection, owner, owner_id, path, dest, node, key, request,
                        expected_connection_identity, cache_directory):
        try:
            path = relative_path(path)
        except ValueError as exc:
            raise BridgeError("invalid_params", f"Invalid remote path: {exc}") from None
        dest = Path(dest)
        if not dest.is_absolute():
            raise BridgeError("invalid_params", "'dest' must be an absolute local path")
        identity = self.backend_for(connection, node).server_key
        if expected_connection_identity is not None and identity != expected_connection_identity:
            raise BridgeError("conflict", "The Runtime endpoint differs from the expected connection")
        if cache_directory is not None:
            cache_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                if inside(cache_directory, path) != dest:
                    raise ValueError("Default download destination changed")
            except ValueError as exc:
                raise BridgeError("invalid_params", str(exc)) from None
        record = self._new("download", key, request, connection_identity=identity,
                           connection=connection, node=node, owner=owner,
                           task_id=owner_id if owner == "task" else None,
                           workspace_id=owner_id if owner == "workspace" else None,
                           local=str(dest), remote=path,
                           items=[{"local": str(dest), "remote": path, "size": None, "sha256": None, "done": False}])
        self._launch(record["id"])
        return self.public(record)

    @_writer
    def resume(self, transfer_id):
        deadline = time.monotonic() + 5.0
        waited_for = None
        while True:
            with self.lock:
                if self.stopping.is_set():
                    raise BridgeError("shutting_down", "Transfers are shutting down")
                # Read under the same lock as launching: another resume may have queued it.
                record = self.load(transfer_id)
                running = self.threads.get(transfer_id)
                if record["state"] == "completed":
                    return self.public(record)
                if waited_for is not None and running is not None and running is not waited_for:
                    # Another caller retried the attempt we joined. Its successor may already be terminal.
                    return self.public(record)
                if running is None or not running.is_alive():
                    self.cancelled.discard(transfer_id)
                    action = record.get("action") or {}
                    if (record["state"] == "cancelled" and record["kind"] == "upload"
                            and action.get("kind") == "workspace.import"
                            and action.get("state") in ("review", "rejected")):
                        record["cancelled_import_id"] = action["id"]
                    record.update(state="queued", error=None)
                    self.save(record)
                    self._launch(transfer_id)
                    return self.public(record)
                if record["state"] in ACTIVE:
                    return self.public(record)
            # A terminal event is observable before its worker releases the file lock and slot.
            # Do not acknowledge resume as a no-op in that interval, or launch a competing worker.
            # Waiting outside self.lock lets the old worker finish its cleanup.
            remaining = deadline - time.monotonic()
            if remaining <= 0 or running is threading.current_thread():
                raise BridgeError("busy", "The previous transfer attempt is still finishing", retryable=True)
            waited_for = running
            running.join(timeout=remaining)

    def resume_interrupted(self):
        resumed = []
        for record in self.list():
            if record["state"] == "interrupted":
                self.resume(record["id"])
                resumed.append(record["id"])
        return resumed

    @_writer
    def cancel(self, transfer_id):
        with self.lock:
            record = self.load(transfer_id)
            thread = self.threads.get(transfer_id)
            if record["state"] in FINAL:
                return self.public(record)
            self.cancelled.add(transfer_id)
            if thread is None or not thread.is_alive():
                self._finish_cancel(record)
                return self.public(self.load(transfer_id))
        thread.join(timeout=30)
        return self.public(self.load(transfer_id))

    def _finish_cancel(self, record):
        action = record.get("action") or {}
        if record["kind"] == "upload" and action.get("state") == "review":
            try:  # a cancelled upload must not be imported later by an approval
                backend = self._record_backend(record)
                record["action"] = summary(backend.reject(action["id"]))
            except BridgeError:
                pass
        if record["kind"] == "upload":
            # A pending upload session blocks task submission in that workspace: abort it.
            for item in record["items"]:
                if not item["done"] and item.get("upload_id"):
                    try:
                        self._record_backend(record).upload_abort(
                            record["workspace_id"], item["upload_id"])
                    except BridgeError:
                        pass
                    item["upload_id"] = None
        else:
            dest = Path(record["local"])
            dest.with_name(dest.name + ".part").unlink(missing_ok=True)
            dest.with_name(dest.name + ".part.json").unlink(missing_ok=True)
        record.update(state="cancelled", current=None)
        self.save(record)
        self._notify(record, force=True)

    def stop(self, timeout=5.0):
        """Pause every running transfer at its next chunk (bridge shutdown); journals stay resumable."""
        with self._activity:
            self.stopping.set()
            threads = tuple(self.threads.values())
        deadline = time.monotonic() + timeout
        for thread in threads:
            if thread is not threading.current_thread() and thread.ident is not None:
                thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _writer_finished(self):
        with self._activity:
            self._writers -= 1
            self._activity.notify_all()

    def release_after_stop(self, release):
        """Release namespace ownership only after admitted calls and worker threads exit.

        stop() keeps its bounded foreground wait. A slow transfer retains ownership in a
        reaper, including the tiny interval between its last mutation and actual thread exit.
        """
        with self._activity:
            if not self.stopping.is_set():
                raise RuntimeError("Stop transfers before releasing their namespace")
            if self._release_pending:
                return
            self._release_pending = True
            self._release_callback = release
            idle = self._writers == 0 and all(not t.is_alive() for t in self.threads.values())
        if idle:
            release()
            self._release_callback = None
            return

        def finish():
            with self._activity:
                self._activity.wait_for(lambda: self._writers == 0)
                threads = tuple(self.threads.values())
            for thread in threads:
                thread.join()
            release()
            self._release_callback = None

        # Retain the callback above even if starting the reaper fails: active writers must
        # never lose their lease merely because a cleanup thread could not be created.
        threading.Thread(target=finish, daemon=True, name="stk-transfers-close").start()

    # -- running --------------------------------------------------------------------------------

    def _launch(self, transfer_id):
        context = copy_context()  # retain this workflow's frozen-target guard in the transfer worker

        def run():
            try:
                context.run(self._run, transfer_id)
            finally:
                self._writer_finished()

        thread = threading.Thread(target=run, daemon=True,
                                  name=f"stk-transfer-{transfer_id[:8]}")
        with self.lock:
            with self._activity:
                if self.stopping.is_set():
                    raise BridgeError("shutting_down", "Transfers are shutting down")
                self._writers += 1
                self.threads[transfer_id] = thread
                try:
                    thread.start()
                except BaseException as exc:
                    # A signal may interrupt start() after native thread creation. Only a
                    # normal, unstarted failure proves no worker needs its ownership kept.
                    if isinstance(exc, Exception) and thread.ident is None:
                        self.threads.pop(transfer_id, None)
                        self._writers -= 1
                        self._activity.notify_all()
                    raise

    def _notify(self, record, force=False):
        stamp = time.monotonic()
        if not force and stamp - self.notified.get(record["id"], 0.0) < PROGRESS_INTERVAL:
            return
        self.notified[record["id"]] = stamp
        self.emit("transfer.updated", {"transfer": self.public(record)})

    def _check(self, transfer_id):
        if transfer_id in self.cancelled or self.stopping.is_set():
            raise _Stopped()

    def _run(self, transfer_id):
        acquired = False
        while not acquired:
            if self.stopping.is_set():
                return  # still queued in the journal: interrupted at the next start
            if transfer_id in self.cancelled:
                self._finish_cancel(self.load(transfer_id))
                return
            acquired = self.slots.acquire(timeout=0.2)
        released = threading.Event()

        def release():
            # Once per run: a hub import waiting for review gives its slot back early.
            if not released.is_set():
                released.set()
                self.slots.release()
        with self.lock:
            self.releasers[transfer_id] = release
        try:
            guard = instance_lock(self.root / (transfer_id + ".lock"))
            try:
                guard.__enter__()
            except OSError:
                record = self.load(transfer_id)
                error = BridgeError("conflict", "This transfer is running in another bridge process")
                self.emit("transfer.updated", {"transfer": {**self.public(record), "error": error.to_json()}})
                return
            try:
                self._run_locked(transfer_id)
            finally:
                guard.__exit__(None, None, None)
        finally:
            with self.lock:
                self.releasers.pop(transfer_id, None)
            release()

    def _run_locked(self, transfer_id):
        record = self.load(transfer_id)
        if record["state"] in FINAL:
            return
        record["state"] = "running"
        record.pop("error", None)
        self.save(record)
        self._notify(record, force=True)
        try:
            backend = self._record_backend(record)
            if record["kind"] == "upload":
                self._upload(record, backend)
            else:
                self._download(record, backend)
        except _Stopped:
            if transfer_id in self.cancelled:
                self._finish_cancel(record)
            else:
                record["state"] = "interrupted"
                self.save(record)
                self._notify(record, force=True)
            return
        except BridgeError as exc:
            record.update(state="failed", error=exc.to_json())
        except OSError as exc:
            record.update(state="failed", error=BridgeError(
                "remote_error", f"Local file error: {exc.strerror or type(exc).__name__}").to_json())
        except Exception as exc:  # never lose the journal state on an unexpected error
            record.update(state="failed", error=BridgeError("internal_error", f"{type(exc).__name__}: {exc}").to_json())
        else:
            record.update(state="completed", current=None)
        self.save(record)
        self._notify(record, force=True)

    def _upload(self, record, backend):
        transfer_id = record["id"]
        workspace = record["workspace_id"]
        done_bytes = sum(item["size"] for item in record["items"] if item["done"])
        for item in record["items"]:
            if item["done"]:
                continue
            self._check(transfer_id)
            record["current"] = item["remote"]
            path = Path(item["local"])
            if path.is_symlink() or not path.is_file():
                raise BridgeError("not_found", f"Upload source file is gone: {item['local']}")
            info = path.stat()
            if item["sha256"] is None or info.st_size != item["size"] or info.st_mtime_ns != item["mtime_ns"]:
                record["bytes_total"] += info.st_size - item["size"]
                item.update(size=info.st_size, mtime_ns=info.st_mtime_ns,
                            sha256=_sha256(path, lambda: self._check(transfer_id)))
                self.save(record)
            meta = backend.upload_begin(workspace, item["remote"], item["size"], item["sha256"])
            item["upload_id"] = meta["id"]
            self.save(record)
            offset = meta["offset"]
            record["bytes_done"] = done_bytes + offset
            self._notify(record)
            if not meta["completed"]:
                with open(path, "rb") as stream:
                    stream.seek(offset)
                    while offset < item["size"]:
                        self._check(transfer_id)
                        chunk = stream.read(CHUNK)
                        if not chunk:
                            raise BridgeError("conflict", f"{item['local']} became shorter while uploading")
                        meta = backend.upload_chunk(workspace, meta["id"], offset, chunk)
                        offset = meta["offset"]
                        record["bytes_done"] = done_bytes + offset
                        self._notify(record)
                self._check(transfer_id)
                try:
                    backend.upload_finish(workspace, meta["id"])
                except BridgeError as exc:
                    if "checksum" not in exc.message and "sha256" not in exc.message:  # Runtime / hub wording
                        raise
                    # Discard the Runtime's copy and re-hash the source, so a retry starts clean.
                    try:
                        backend.upload_abort(workspace, meta["id"])
                    except BridgeError:
                        pass
                    item.update(sha256=None, upload_id=None)
                    self.save(record)
                    raise BridgeError("checksum_mismatch", f"The {backend.kind} copy of {item['remote']} does not "
                                      "match its sha256; the file changed while uploading. Retry the upload"
                                      ) from None
            item["done"] = True
            item["upload_id"] = None
            done_bytes += item["size"]
            record["files_done"] += 1
            record["bytes_done"] = done_bytes
            self.save(record)
            self._notify(record)
        if backend.kind == "hub":
            self._import(record, backend)

    def _import(self, record, backend):
        """Every file is in the hub's blob store: import them into the workspace (reviewed) and wait."""
        transfer_id = record["id"]
        with self.lock:
            release = self.releasers.get(transfer_id)
        if release is not None:
            release()  # no local bytes move from here on; waiting for review must not block other transfers
        attempt = int(record.get("import_attempt", 0))
        identity = action_id("workspace.import", backend.node_id, transfer_id, attempt)
        files = [{"path": item["remote"], "sha256": item["sha256"], "size": item["size"]} for item in record["items"]]

        def post(identity):
            self._check(transfer_id)
            try:
                return backend.post_import(record["workspace_id"], files, identity)
            except BridgeError as exc:
                if "before importing" not in exc.message:
                    raise
                # The hub collected the uploaded files: upload them again on resume.
                for item in record["items"]:
                    item.update(done=False, upload_id=None)
                record.update(bytes_done=0, files_done=0)
                raise BridgeError("remote_error", "The hub no longer holds the uploaded files (they expired before "
                                  "the import); resume the transfer to upload them again") from None

        record["current"] = None
        self._check(transfer_id)
        action = None
        cancelled_import = record.get("cancelled_import_id")
        if cancelled_import is not None:
            if cancelled_import == identity:
                previous = record.get("action") or {}
                if previous.get("state") != "rejected":
                    # The hub may have recorded the rejection before its reply was lost.
                    previous = summary(backend.action_record(identity))
                if previous.get("state") != "rejected":
                    # Rejection can still arrive between the read and this same-ID replay.
                    action = post(identity)
                    previous = summary(action)
                if (previous.get("id"), previous.get("node_id"), previous.get("kind"), previous.get("state")) == (
                        identity, backend.node_id, "workspace.import", "rejected"):
                    attempt += 1
                    record["import_attempt"] = attempt
                    identity = action_id("workspace.import", backend.node_id, transfer_id, attempt)
                    record.pop("action", None)
                    action = None
            # Persist the choice before POST so interruption reuses the same successor.
            record.pop("cancelled_import_id")
            self.save(record)
        if action is None:
            action = post(identity)
        delay = 0.25
        while True:
            view = summary(action)
            if view != record.get("action"):
                record["action"] = view
                self.save(record)
                self._notify(record, force=True)
            if action["state"] == "succeeded":
                return
            if action["state"] in ("failed", "rejected"):
                record["import_attempt"] = attempt + 1  # a resume asks again with a new action
                raise action_failure(action, "The import was rejected in review")
            wait = REVIEW_POLL if action["state"] == "review" else delay
            delay = min(1.0, delay * 1.5)
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                self._check(transfer_id)
                time.sleep(0.05)
            action = backend.action_record(identity)

    def _download(self, record, backend):
        transfer_id = record["id"]
        item = record["items"][0]
        owner = record.get("owner", "task")
        owner_id = record["task_id"] if owner == "task" else record["workspace_id"]
        described = backend.describe(owner, owner_id, item["remote"])
        expected = {"path": described["path"], "size": described["size"], "sha256": described["sha256"]}
        item.update(size=expected["size"], sha256=expected["sha256"])
        record.update(bytes_total=expected["size"], sha256=expected["sha256"], current=item["remote"])
        self.save(record)
        dest = Path(item["local"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.stat().st_size == expected["size"] and _sha256(dest) == expected["sha256"]:
            record.update(bytes_done=expected["size"], files_done=1)
            item["done"] = True
            return
        part = dest.with_name(dest.name + ".part")
        meta = dest.with_name(dest.name + ".part.json")
        if read_json(meta) != expected or (part.exists() and part.stat().st_size > expected["size"]):
            part.unlink(missing_ok=True)
        atomic_json(meta, expected)
        offset = part.stat().st_size if part.exists() else 0
        with open(part, "ab") as stream:
            while offset < expected["size"]:
                self._check(transfer_id)
                chunk = backend.read_chunk(owner, owner_id, item["remote"], offset)
                if not chunk:
                    raise BridgeError("remote_error", "The download ended before the declared file size",
                                      retryable=True)
                stream.write(chunk)
                stream.flush()
                offset += len(chunk)
                record["bytes_done"] = offset
                self._notify(record)
            os.fsync(stream.fileno())
        if part.stat().st_size != expected["size"] or _sha256(part) != expected["sha256"]:
            part.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            record["bytes_done"] = 0
            raise BridgeError("checksum_mismatch", f"The downloaded {item['remote']} does not match its sha256; "
                              "the partial file was discarded. Retry the download")
        os.replace(part, dest)
        meta.unlink(missing_ok=True)
        item["done"] = True
        record.update(bytes_done=expected["size"], files_done=1)
