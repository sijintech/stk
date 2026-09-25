"""Resumable client uploads into the hub's content-addressed blob store (standard library only).

A client device (the desktop bridge) uploads one file's bytes as one blob::

    POST   /api/v1/uploads {sha256, size}          -> {id, sha256, size, offset, completed}
    PUT    /api/v1/uploads/<id>?offset=N  <bytes>  -> the same record (appends at exactly the held offset)
    GET    /api/v1/uploads/<id>                    -> the same record (resume from ``offset``)
    POST   /api/v1/uploads/<id>/finish             -> the record, completed (hashed, blob moved into place)
    DELETE /api/v1/uploads/<id>                    -> {aborted: true}

The shape mirrors the Runtime's resumable upload sessions, so the desktop bridge drives both with the
same journaled transfer code. A session belongs to the device that began it (other devices get 404)
and is named by ``sha256(device, digest, size)``: a client that lost its own state begins the same
session again and continues from the bytes the hub already holds. A blob the store already has is
``completed`` at once and no bytes move. Bytes live in ``<blobs>/.uploads/<id>.part`` and become a
blob only after ``finish`` hashed them to the declared sha256; a mismatch discards them. Limits: the
store's ``max_bytes`` per blob, :data:`CHUNK_MAX` per chunk, :data:`MAX_OPEN` open sessions per
device; sessions untouched for :data:`KEEP_SECONDS` are removed.
"""
import hashlib
import json
import os
import re
import threading
import time

from .blobs import BlobError, BlobMismatch, BlobTooLarge

__all__ = ["CHUNK_MAX", "KEEP_SECONDS", "MAX_OPEN", "UploadConflict", "UploadLimit", "UploadSessions"]

CHUNK_MAX = 8 * 1024 * 1024
MAX_OPEN = 16
KEEP_SECONDS = 7 * 24 * 3600
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadConflict(BlobError):
    """The chunk does not start at the offset the hub holds (HTTP 409)."""


class UploadLimit(BlobError):
    """Too many open upload sessions for this device (HTTP 429)."""


class UploadSessions:
    def __init__(self, blobs):
        self.blobs = blobs
        self.root = blobs.root / ".uploads"
        self.root.mkdir(exist_ok=True, mode=0o700)
        self._guard = threading.Lock()
        self._locks = {}

    # -- files ----------------------------------------------------------------------------------

    def _lock(self, upload_id):
        with self._guard:
            return self._locks.setdefault(upload_id, threading.Lock())

    def _paths(self, upload_id):
        if not isinstance(upload_id, str) or not UPLOAD_ID.fullmatch(upload_id):
            raise KeyError("Upload not found")
        return self.root / (upload_id + ".json"), self.root / (upload_id + ".part")

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

    def _expire(self):
        cutoff = time.time() - KEEP_SECONDS
        for path in self.root.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.with_suffix(".part").unlink(missing_ok=True)
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    # -- operations -----------------------------------------------------------------------------

    def begin(self, device, digest, size):
        self.blobs.check(digest)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BlobError("Upload size must be a nonnegative integer")
        if size > self.blobs.max_bytes:
            raise BlobTooLarge(f"Blob of {size} bytes exceeds the {self.blobs.max_bytes}-byte limit")
        upload_id = hashlib.sha256(f"{device}\x00{digest}\x00{size}".encode("utf-8")).hexdigest()[:32]
        meta = {"id": upload_id, "device": device, "sha256": digest, "size": size}
        stored = self.blobs.size(digest)
        if stored is not None:
            if stored != size:
                raise BlobError("The declared size does not match the stored blob of this sha256")
            return self._record(meta, size, completed=True)
        meta_path, part = self._paths(upload_id)
        with self._lock(upload_id):
            if self._read(meta_path) is None:
                self._expire()
                open_sessions = sum(1 for path in self.root.glob("*.json")
                                    if (self._read(path) or {}).get("device") == device)
                if open_sessions >= MAX_OPEN:
                    raise UploadLimit(f"At most {MAX_OPEN} unfinished uploads per device; finish or abort one")
                part.unlink(missing_ok=True)
                self._write(meta_path, {**meta, "created": time.time()})
            else:
                os.utime(meta_path)
            return self._record(meta, part.stat().st_size if part.exists() else 0)

    def status(self, device, upload_id):
        meta, _, part = self._load(device, upload_id)
        return self._record(meta, part.stat().st_size if part.exists() else 0)

    def chunk(self, device, upload_id, offset, data):
        if len(data) > CHUNK_MAX:
            raise BlobTooLarge(f"Upload chunks are limited to {CHUNK_MAX} bytes")
        with self._lock(upload_id):
            meta, meta_path, part = self._load(device, upload_id)
            held = part.stat().st_size if part.exists() else 0
            if offset != held:
                raise UploadConflict(f"The hub holds {held} bytes of this upload; continue from there")
            if held + len(data) > meta["size"]:
                raise BlobTooLarge("The chunk runs past the declared upload size")
            # O_BINARY: no newline translation on Windows (0 elsewhere).
            descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
            with os.fdopen(descriptor, "ab") as stream:
                stream.write(data)
            os.utime(meta_path)
            return self._record(meta, held + len(data))

    def finish(self, device, upload_id):
        with self._lock(upload_id):
            meta, meta_path, part = self._load(device, upload_id)
            if meta["size"] == 0 and not part.exists():
                part.touch(mode=0o600)
            held = part.stat().st_size if part.exists() else 0
            if held != meta["size"]:
                raise UploadConflict(f"The upload is incomplete: the hub holds {held} of {meta['size']} bytes")
            with open(part, "rb+") as stream:
                os.fsync(stream.fileno())
            try:
                self.blobs.adopt(part, meta["sha256"])
            except BlobMismatch:
                part.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                raise
            meta_path.unlink(missing_ok=True)
            return self._record(meta, meta["size"], completed=True)

    def abort(self, device, upload_id):
        with self._lock(upload_id):
            _, meta_path, part = self._load(device, upload_id)
            part.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        return {"aborted": True}
