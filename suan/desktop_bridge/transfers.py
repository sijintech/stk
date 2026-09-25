"""Resumable, journaled uploads and downloads (spec §7).

Every transfer has a journal ``<state_dir>/transfers/<id>.json`` written atomically before and
during the work, so a bridge that crashed or was closed resumes where it stopped:

* **Uploads** use the Runtime's resumable upload sessions (``POST .../uploads`` returns the byte
  offset the Runtime already holds; ``PUT`` appends 1 MiB chunks; ``finish`` verifies size and
  sha256). The journal keeps each file's size, mtime and sha256, so a resumed upload re-hashes
  only files that changed; a changed file starts a new upload revision.
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
import time
import uuid

from suan.runtime.common import atomic_json, instance_lock, now, read_json
from suan.runtime.models import relative_path

from .protocol import BridgeError

__all__ = ["TransferManager"]

CHUNK = 1024 * 1024
ACTIVE = {"queued", "running"}
FINAL = {"completed", "failed", "cancelled"}
MAX_FILES = 100_000
MAX_CONCURRENT = 4
PROGRESS_INTERVAL = 0.25
KEEP_FINISHED_SECONDS = 7 * 24 * 3600


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
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT)
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

    def _recover(self):
        cutoff = time.time() - KEEP_FINISHED_SECONDS
        for path in self.root.glob("*.json"):
            try:
                record = read_json(path)
            except (OSError, ValueError):
                continue
            if not isinstance(record, dict) or "state" not in record:
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
                "bytes_done", "bytes_total", "files_done", "files_total", "current", "sha256", "error",
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

    def _new(self, kind, **fields):
        record = {"id": uuid.uuid4().hex, "kind": kind, "state": "queued", "bytes_done": 0, "files_done": 0,
                  "created_at": now(), **fields}
        record["files_total"] = len(record["items"])
        record["bytes_total"] = sum(item["size"] for item in record["items"] if item["size"] is not None)
        self.save(record)
        return record

    def start_upload(self, connection, workspace_id, source, remote=None, node=None):
        source = Path(source)
        if not source.is_absolute():
            raise BridgeError("invalid_params", "'source' must be an absolute local path")
        if source.is_symlink() or not source.exists():
            raise BridgeError("not_found", "The upload source does not exist or is a symbolic link")
        items = []
        if source.is_file():
            name = remote or source.name
            items.append(self._upload_item(source, name))
        elif source.is_dir():
            prefix = (remote or source.name).strip("/")
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
        # Fail before starting when the connection is unknown or cannot upload (hub connections).
        if self.backend_for(connection, node).kind != "runtime":
            raise BridgeError("unsupported", "Uploads through the control hub are not available yet; connect to "
                              "the Runtime directly (SSH tunnel)")
        record = self._new("upload", connection=connection, node=node, workspace_id=workspace_id,
                           local=str(source), remote=remote or source.name, items=items)
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

    def start_download(self, connection, owner, owner_id, path, dest, node=None):
        try:
            path = relative_path(path)
        except ValueError as exc:
            raise BridgeError("invalid_params", f"Invalid remote path: {exc}") from None
        dest = Path(dest)
        if not dest.is_absolute():
            raise BridgeError("invalid_params", "'dest' must be an absolute local path")
        record = self._new("download", connection=connection, node=node, owner=owner,
                           task_id=owner_id if owner == "task" else None,
                           workspace_id=owner_id if owner == "workspace" else None,
                           local=str(dest), remote=path,
                           items=[{"local": str(dest), "remote": path, "size": None, "sha256": None, "done": False}])
        self._launch(record["id"])
        return self.public(record)

    def resume(self, transfer_id):
        record = self.load(transfer_id)
        with self.lock:
            running = self.threads.get(transfer_id)
            if running is not None and running.is_alive():
                return self.public(record)
            if record["state"] == "completed":
                return self.public(record)
            self.cancelled.discard(transfer_id)
            record.update(state="queued", error=None)
            self.save(record)
            self._launch(transfer_id)
        return self.public(record)

    def resume_interrupted(self):
        resumed = []
        for record in self.list():
            if record["state"] == "interrupted":
                self.resume(record["id"])
                resumed.append(record["id"])
        return resumed

    def cancel(self, transfer_id):
        record = self.load(transfer_id)
        with self.lock:
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
        if record["kind"] == "upload":
            # A pending upload session blocks task submission in that workspace: abort it.
            for item in record["items"]:
                if not item["done"] and item.get("upload_id"):
                    try:
                        self.backend_for(record["connection"], record.get("node")).upload_abort(
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
        self.stopping.set()
        deadline = time.monotonic() + timeout
        for thread in list(self.threads.values()):
            thread.join(timeout=max(0.0, deadline - time.monotonic()))

    # -- running --------------------------------------------------------------------------------

    def _launch(self, transfer_id):
        thread = threading.Thread(target=self._run, args=(transfer_id,), daemon=True,
                                  name=f"stk-transfer-{transfer_id[:8]}")
        with self.lock:
            self.threads[transfer_id] = thread
        thread.start()

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
            self.slots.release()

    def _run_locked(self, transfer_id):
        record = self.load(transfer_id)
        if record["state"] in FINAL:
            return
        record["state"] = "running"
        record.pop("error", None)
        self.save(record)
        self._notify(record, force=True)
        try:
            backend = self.backend_for(record["connection"], record.get("node"))
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
                    if "checksum" not in exc.message:
                        raise
                    # Discard the Runtime's copy and re-hash the source, so a retry starts clean.
                    try:
                        backend.upload_abort(workspace, meta["id"])
                    except BridgeError:
                        pass
                    item.update(sha256=None, upload_id=None)
                    self.save(record)
                    raise BridgeError("checksum_mismatch", f"The Runtime's copy of {item['remote']} does not "
                                      "match its sha256; the file changed while uploading. Retry the upload"
                                      ) from None
            item["done"] = True
            item["upload_id"] = None
            done_bytes += item["size"]
            record["files_done"] += 1
            record["bytes_done"] = done_bytes
            self.save(record)
            self._notify(record)

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
