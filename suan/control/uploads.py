"""Resumable client uploads into the hub's content-addressed blob store (standard library only).

A desktop-profile client device (the desktop bridge) uploads one file's bytes as one blob::

    POST   /api/v1/uploads {sha256, size}          -> {id, sha256, size, offset, completed}
    PUT    /api/v1/uploads/<id>?offset=N  <bytes>  -> the same record (appends at exactly the held offset)
    GET    /api/v1/uploads/<id>                    -> the same record (resume from ``offset``)
    POST   /api/v1/uploads/<id>/finish             -> the record, completed (hashed, blob moved into place)
    DELETE /api/v1/uploads/<id>                    -> {aborted: true}

The shape mirrors the Runtime's resumable upload sessions, so the desktop bridge drives both with the
same journaled transfer code. A session belongs to the device that began it (other devices get 404)
and is named by ``sha256(device, digest, size)``: a client that lost its own state begins the same
session again and continues from the bytes the hub already holds. A blob the store already has is
``completed`` at once and no bytes move. Bytes stream into ``<blobs>/.uploads/<id>.part`` and become
a blob only after ``finish`` hashed them to the declared sha256; a mismatch discards them.

Limits (all per device unless noted):

* the store's ``max_bytes`` per blob, :data:`CHUNK_MAX` per chunk, :data:`MAX_OPEN` open sessions,
  :data:`MAX_PUTS` chunks being written at once (429 beyond);
* a byte **quota** (default :data:`DEFAULT_QUOTA_BYTES`) over the declared sizes of open sessions
  plus the device's uploaded blobs that no queued or succeeded ``workspace.import`` references yet;
* a **free-disk floor** for the blob store (default :data:`DEFAULT_MIN_FREE_BYTES`, whole hub): no
  new upload or chunk while less space is free (HTTP 507);
* **garbage collection**: uploaded blobs that no pending or finished import references are deleted
  :data:`DEFAULT_TTL_SECONDS` after their last upload (checked when uploads begin, at most once a
  minute), and sessions untouched for :data:`KEEP_SECONDS` are removed.
"""
import hashlib
import json
import os
import re
import shutil
import threading
import time

from .blobs import BlobError, BlobMismatch, BlobTooLarge

__all__ = ["CHUNK_MAX", "DEFAULT_MIN_FREE_BYTES", "DEFAULT_QUOTA_BYTES", "DEFAULT_TTL_SECONDS", "KEEP_SECONDS",
           "MAX_OPEN", "MAX_PUTS", "DiskFull", "UploadBusy", "UploadConflict", "UploadLimit", "UploadQuota",
           "UploadSessions"]

MIB = 1024 * 1024
CHUNK_MAX = 8 * MIB
MAX_OPEN = 16
MAX_PUTS = 4
KEEP_SECONDS = 7 * 24 * 3600
DEFAULT_QUOTA_BYTES = 4096 * MIB
DEFAULT_TTL_SECONDS = 24 * 3600
DEFAULT_MIN_FREE_BYTES = 5120 * MIB
GC_INTERVAL = 60.0
STRIPES = 64
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadConflict(BlobError):
    """The chunk does not start at the offset the hub holds, or the session is busy (HTTP 409)."""


class UploadLimit(BlobError):
    """Too many open upload sessions for this device (HTTP 429)."""


class UploadBusy(BlobError):
    """Too many chunks of this device are being written at once (HTTP 429)."""


class UploadQuota(BlobError):
    """The device's upload quota would be exceeded (HTTP 413)."""


class DiskFull(BlobError):
    """The blob store's free space is below the floor (HTTP 507)."""


class _Append:
    """One chunk streaming into a session's part file; ``commit`` or ``abort`` exactly once."""

    def __init__(self, sessions, device, meta, meta_path, part, held):
        self.sessions, self.device, self.meta, self.meta_path, self.part = sessions, device, meta, meta_path, part
        self.start = held
        self.written = 0
        descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
        self.stream = os.fdopen(descriptor, "ab")

    def write(self, data):
        self.written += len(data)
        if self.written > CHUNK_MAX:
            raise BlobTooLarge(f"Upload chunks are limited to {CHUNK_MAX} bytes")
        if self.start + self.written > self.meta["size"]:
            raise BlobTooLarge("The chunk runs past the declared upload size")
        self.stream.write(data)

    def commit(self):
        try:
            self.stream.close()
            os.utime(self.meta_path)
            return self.sessions._record(self.meta, self.start + self.written)
        finally:
            self.sessions._release(self.device, self.meta["id"])

    def abort(self):
        """Discard this chunk's bytes (the session keeps what it held before)."""
        try:
            if not self.stream.closed:
                self.stream.close()
            with open(self.part, "rb+") as stream:
                stream.truncate(self.start)
        except OSError:
            pass
        finally:
            self.sessions._release(self.device, self.meta["id"])


class UploadSessions:
    def __init__(self, blobs, ledger, *, quota_bytes=DEFAULT_QUOTA_BYTES, ttl_seconds=DEFAULT_TTL_SECONDS,
                 min_free_bytes=DEFAULT_MIN_FREE_BYTES):
        self.blobs = blobs
        self.ledger = ledger  # ControlStore: client_blobs / import_refs
        self.quota_bytes = int(quota_bytes)
        self.ttl_seconds = float(ttl_seconds)
        self.min_free_bytes = int(min_free_bytes)
        self.root = blobs.root / ".uploads"
        self.root.mkdir(exist_ok=True, mode=0o700)
        self._stripes = [threading.Lock() for _ in range(STRIPES)]  # fixed: never grows with request ids
        self._begin = threading.Lock()   # counting and creating sessions, garbage collection
        self._guard = threading.Lock()   # _writing and _puts
        self._writing = set()            # sessions with a chunk streaming in
        self._puts = {}                  # device -> chunks being written
        self._last_gc = 0.0

    # -- files ----------------------------------------------------------------------------------

    def _paths(self, upload_id):
        if not isinstance(upload_id, str) or not UPLOAD_ID.fullmatch(upload_id):
            raise KeyError("Upload not found")
        return self.root / (upload_id + ".json"), self.root / (upload_id + ".part")

    def _lock(self, upload_id):
        self._paths(upload_id)  # validate before any lock is chosen
        return self._stripes[int(upload_id[:8], 16) % STRIPES]

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write(path, value):
        tmp = path.with_name(path.name + ".tmp")
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        os.replace(tmp, path)

    def _load(self, device, upload_id):
        meta_path, part = self._paths(upload_id)
        meta = self._read(meta_path)
        if not isinstance(meta, dict) or meta.get("device") != device:
            raise KeyError("Upload not found")  # another device's session is indistinguishable from none
        return meta, meta_path, part

    @staticmethod
    def _record(meta, offset, completed=False):
        return {"id": meta["id"], "sha256": meta["sha256"], "size": meta["size"], "offset": offset,
                "completed": completed}

    def _sessions(self):
        for path in self.root.glob("*.json"):
            meta = self._read(path)
            if isinstance(meta, dict):
                yield path, meta

    def _check_disk(self, incoming=0):
        if self.min_free_bytes <= 0:
            return
        free = shutil.disk_usage(self.blobs.root).free
        if free - incoming < self.min_free_bytes:
            raise DiskFull(f"The hub's blob store is low on disk space (under {self.min_free_bytes // MIB} MiB "
                           "would be left); uploads resume when space is freed")

    def _busy(self, upload_id):
        with self._guard:
            return upload_id in self._writing

    def _release(self, device, upload_id):
        with self._guard:
            self._writing.discard(upload_id)
            count = self._puts.get(device, 0) - 1
            if count > 0:
                self._puts[device] = count
            else:
                self._puts.pop(device, None)

    # -- housekeeping ---------------------------------------------------------------------------

    def gc(self, now=None):
        """Remove expired sessions and unreferenced client blobs; returns the sha256s deleted."""
        now = time.time() if now is None else now
        with self._begin:
            self._last_gc = time.monotonic()
            for path, meta in list(self._sessions()):
                upload_id = meta.get("id", "")
                try:
                    if path.stat().st_mtime < now - KEEP_SECONDS and not self._busy(upload_id):
                        path.with_suffix(".part").unlink(missing_ok=True)
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
            collected = self.ledger.collect_client_blobs(now - self.ttl_seconds)
            for digest in collected:
                try:
                    self.blobs.path(digest).unlink(missing_ok=True)
                except (OSError, BlobError):
                    pass
        return collected

    def usage(self, device):
        """Quota bytes in use: open sessions (declared sizes) plus unimported client blobs."""
        pending = sum(int(meta.get("size", 0)) for _, meta in self._sessions() if meta.get("device") == device)
        return pending + self.ledger.client_usage(device)

    # -- operations -----------------------------------------------------------------------------

    def begin(self, device, digest, size):
        self.blobs.check(digest)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BlobError("Upload size must be a nonnegative integer")
        if size > self.blobs.max_bytes:
            raise BlobTooLarge(f"Blob of {size} bytes exceeds the {self.blobs.max_bytes}-byte limit")
        if time.monotonic() - self._last_gc > GC_INTERVAL:
            self.gc()
        upload_id = hashlib.sha256(f"{device}\x00{digest}\x00{size}".encode("utf-8")).hexdigest()[:32]
        meta = {"id": upload_id, "device": device, "sha256": digest, "size": size}
        meta_path, part = self._paths(upload_id)
        with self._begin:
            stored = self.blobs.size(digest)
            if stored is not None:
                if stored != size:
                    raise BlobError("The declared size does not match the stored blob of this sha256")
                if self.ledger.is_client_blob(digest):
                    self.ledger.record_client_blob(device, digest, size)  # this device relies on it too
                return self._record(meta, size, completed=True)
            if self._read(meta_path) is None:
                open_sessions = sum(1 for _, other in self._sessions() if other.get("device") == device)
                if open_sessions >= MAX_OPEN:
                    raise UploadLimit(f"At most {MAX_OPEN} unfinished uploads per device; finish or abort one")
                used = self.usage(device)
                if used + size > self.quota_bytes:
                    raise UploadQuota(f"This device's upload quota is {self.quota_bytes // MIB} MiB and "
                                      f"{used} bytes are in use by unfinished uploads and files not imported yet")
                self._check_disk(size)
                with self._lock(upload_id):
                    part.unlink(missing_ok=True)
                    self._write(meta_path, {**meta, "created": time.time()})
            else:
                os.utime(meta_path)
        return self._record(meta, part.stat().st_size if part.exists() else 0)

    def status(self, device, upload_id):
        with self._lock(upload_id):
            meta, _, part = self._load(device, upload_id)
            return self._record(meta, part.stat().st_size if part.exists() else 0)

    def open_chunk(self, device, upload_id, offset, length=None):
        """Check session, owner, offset and length before any byte is read; returns an :class:`_Append`.

        ``length`` is the declared Content-Length (``None`` when unknown; the stream is then capped
        as it arrives).
        """
        lock = self._lock(upload_id)
        with self._guard:
            if upload_id in self._writing:
                raise UploadConflict("Another chunk of this upload is being written")
            if self._puts.get(device, 0) >= MAX_PUTS:
                raise UploadBusy(f"At most {MAX_PUTS} chunks per device are written at once; retry")
            self._puts[device] = self._puts.get(device, 0) + 1
            self._writing.add(upload_id)
        try:
            with lock:
                meta, meta_path, part = self._load(device, upload_id)
                held = part.stat().st_size if part.exists() else 0
                if offset != held:
                    raise UploadConflict(f"The hub holds {held} bytes of this upload; continue from there")
                if length is not None and length > CHUNK_MAX:
                    raise BlobTooLarge(f"Upload chunks are limited to {CHUNK_MAX} bytes")
                if length is not None and held + length > meta["size"]:
                    raise BlobTooLarge("The chunk runs past the declared upload size")
                self._check_disk(length or 0)
                return _Append(self, device, meta, meta_path, part, held)
        except BaseException:
            self._release(device, upload_id)
            raise

    def chunk(self, device, upload_id, offset, data):
        """Append ``data`` in one call (the HTTP route streams through :meth:`open_chunk` instead)."""
        append = self.open_chunk(device, upload_id, offset, len(data))
        try:
            append.write(data)
        except BaseException:
            append.abort()
            raise
        return append.commit()

    def finish(self, device, upload_id):
        with self._lock(upload_id):
            if self._busy(upload_id):
                raise UploadConflict("A chunk of this upload is still being written")
            meta, meta_path, part = self._load(device, upload_id)
            if meta["size"] == 0 and not part.exists():
                part.touch(mode=0o600)
            held = part.stat().st_size if part.exists() else 0
            if held != meta["size"]:
                raise UploadConflict(f"The upload is incomplete: the hub holds {held} of {meta['size']} bytes")
            with open(part, "rb+") as stream:
                os.fsync(stream.fileno())
            try:
                created = self.blobs.adopt(part, meta["sha256"])
            except BlobMismatch:
                part.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                raise
            if created or self.ledger.is_client_blob(meta["sha256"]):
                self.ledger.record_client_blob(device, meta["sha256"], meta["size"])
            meta_path.unlink(missing_ok=True)
            return self._record(meta, meta["size"], completed=True)

    def abort(self, device, upload_id):
        with self._lock(upload_id):
            if self._busy(upload_id):
                raise UploadConflict("A chunk of this upload is still being written")
            _, meta_path, part = self._load(device, upload_id)
            part.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        return {"aborted": True}
