"""Append-only project manifests and verified, content-addressed local input copies.

Snapshot creation is explicit. Source files stay untouched, ordinary edits/undo cannot rewrite
historical manifests, and every resolve verifies the bytes before returning a local path.
Unreferenced objects left by a conflict/crash are safe to reuse; this module never garbage-collects.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
from uuid import UUID, uuid4, uuid5

from .files import _resolve
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id, _version

DEFAULT_MAX_BYTES = 256 * 1024 * 1024
MAX_BYTES = 1024 ** 4
CHUNK = 1024 * 1024


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _reader(path):
    # Check file type on the open descriptor without blocking forever if a path was replaced
    # with a FIFO between metadata inspection and open. O_NOFOLLOW is available on POSIX.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    return os.fdopen(fd, "rb")


def _sync_directory(directory):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Snapshots:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _require(db):
        if _version(db) < 4:
            raise UnsupportedProjectFormat("Upgrade this project to format 4 before creating or reading input snapshots")

    def _directory(self, parts, *, create=False):
        path = self.store.directory
        for part in parts:
            path = path / part
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise ProjectError("Snapshot storage directories must not be files or symbolic links")
            if create:
                existed = path.exists()
                path.mkdir(mode=0o700, exist_ok=True)
                if not existed:
                    _sync_directory(path.parent)
        return path

    def _object(self, digest, *, create=False):
        if not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None:
            raise ProjectError("Invalid snapshot object digest")
        return self._directory((".stk", "objects", "sha256", digest[:2]), create=create) / digest[2:]

    @staticmethod
    def _verify_object(path, digest, size):
        if path.is_symlink():
            raise ProjectError("Snapshot object must not be a symbolic link")
        with _reader(path) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != size:
                raise ProjectError("Snapshot object size or file type does not match its manifest")
            checksum, count = hashlib.sha256(), 0
            for chunk in iter(lambda: stream.read(CHUNK), b""):
                count += len(chunk)
                if count > size:
                    raise ProjectError("Snapshot object grew while being verified")
                checksum.update(chunk)
            after = os.fstat(stream.fileno())
        # A concurrent no-replace publication may still remove its temporary hard link,
        # changing ctime/link count without changing bytes. Content, identity, size and mtime
        # must match; source capture below additionally compares ctime.
        if checksum.hexdigest() != digest or _signature(before)[:4] != _signature(after)[:4]:
            raise ProjectError("Snapshot object checksum does not match its manifest")
        if _signature(path.stat())[:4] != _signature(after)[:4]:
            raise ProjectError("Snapshot object changed while being verified")

    def _copy(self, source, remaining):
        temporary = self._directory((".stk", "tmp"), create=True) / (uuid4().hex + ".part")
        try:
            with _reader(source) as reader, temporary.open("xb") as writer:
                before = os.fstat(reader.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ProjectError("Snapshot sources must be regular files")
                if before.st_size > remaining:
                    raise ProjectError("Snapshot exceeds max_bytes; increase the explicit budget or select fewer files")
                checksum, size = hashlib.sha256(), 0
                for chunk in iter(lambda: reader.read(CHUNK), b""):
                    size += len(chunk)
                    if size > remaining:
                        raise ProjectError("Snapshot exceeds max_bytes while reading a source")
                    writer.write(chunk)
                    checksum.update(chunk)
                after = os.fstat(reader.fileno())
                if _signature(before) != _signature(after) or size != after.st_size or _signature(source.stat()) != _signature(after):
                    raise ProjectError("Snapshot source changed while being copied; refresh and capture again")
                writer.flush()
                os.fsync(writer.fileno())
            digest = checksum.hexdigest()
            target = self._object(digest, create=True)
            try:
                # Atomic no-replace publication. Concurrent identical captures share the object;
                # a damaged existing object is diagnosed, never silently overwritten.
                os.link(temporary, target)
                _sync_directory(target.parent)
            except FileExistsError:
                self._verify_object(target, digest, size)
            return digest, size, _signature(after)
        finally:
            temporary.unlink(missing_ok=True)

    def _decode(self, row):
        if row is None:
            raise ProjectError("Input snapshot not found")
        result = dict(row)
        try:
            manifest = json.loads(result["manifest"])
            digest = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
            identity = str(uuid5(UUID(self.store._project_id), digest))
            if digest != result["sha256"] or identity != result["id"] or manifest["project_id"] != self.store._project_id:
                raise ValueError("identity/checksum mismatch")
            if result["kind"] != "files" or manifest["kind"] != "files" or manifest["format"] != 1:
                raise ValueError("unsupported manifest kind/version")
            if type(manifest["source_revision"]) is not int or manifest["source_revision"] < 0:
                raise ValueError("invalid source revision")
            if not isinstance(manifest["files"], list) or not 1 <= len(manifest["files"]) <= 100:
                raise ValueError("invalid file list")
            ids = set()
            for file in manifest["files"]:
                _id(file["record_id"])
                if file["record_id"] in ids or type(file["size"]) is not int or not 0 <= file["size"] <= MAX_BYTES:
                    raise ValueError("invalid file identity or size")
                ids.add(file["record_id"])
                if re.fullmatch("[0-9a-f]{64}", file["sha256"]) is None:
                    raise ValueError("invalid file digest")
                if not all(isinstance(file[key], str) for key in ("name", "path", "location")):
                    raise ValueError("invalid file metadata")
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise ProjectError(f"Invalid stored snapshot manifest: {exc}") from None
        result["manifest"] = manifest
        return result

    def list(self):
        with self.store._connect() as db:
            self._require(db)
            return {"revision": db.execute("SELECT revision FROM project").fetchone()[0],
                    "snapshots": [self._decode(row) for row in db.execute("SELECT * FROM project_snapshots ORDER BY rowid")]}

    def get(self, snapshot_id):
        _id(snapshot_id)
        with self.store._connect() as db:
            self._require(db)
            return self._decode(db.execute("SELECT * FROM project_snapshots WHERE id=?", (snapshot_id,)).fetchone())

    def capture(self, record_ids, *, expected_revision, max_bytes=DEFAULT_MAX_BYTES):
        _expected_revision(expected_revision)
        if not isinstance(record_ids, list) or not 1 <= len(record_ids) <= 100:
            raise ProjectError("Capture between 1 and 100 explicit file record IDs")
        for identity in record_ids:
            _id(identity)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ProjectError("max_bytes must be an integer between 1 and 1 TiB")
        model = self.store.files._read(expected_revision)
        if model["format_version"] < 4:
            raise UnsupportedProjectFormat("Upgrade this project to format 4 before creating input snapshots")
        table = self.store.files._table(model)
        self.store.files._fields(table)
        rows = {row["id"]: row for row in table["records"]} if table else {}
        selected = []
        for identity in dict.fromkeys(record_ids):
            row = rows.get(identity)
            if row is None:
                raise ProjectError("File record not found in the project index")
            if any(value.get("state") != "ok" for value in row.get("evaluations", {}).values()):
                raise ProjectError("Resolve file record expression errors before capturing inputs")
            values = self.store.files._values(row)
            source = _resolve(self.store.directory, values["location"], values["path"])
            if not source.is_file():
                raise ProjectError("Snapshot source is missing or is not a regular file")
            selected.append((identity, values, source))
        files, signatures, total = [], [], 0
        for identity, values, source in selected:
            digest, size, signature = self._copy(source, max_bytes - total)
            total += size
            files.append({"record_id": identity, "name": source.name, "path": values["path"],
                          "location": values["location"], "sha256": digest, "size": size})
            signatures.append((source, signature))
        for source, signature in signatures:
            if _signature(source.stat()) != signature:
                raise ProjectError("Snapshot source changed during capture; refresh and capture again")
        manifest = {"format": 1, "kind": "files", "project_id": model["project"]["id"],
                    "source_revision": expected_revision, "files": files}
        encoded = _canonical(manifest)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        identity = str(uuid5(UUID(model["project"]["id"]), digest))
        with self.store._connect(write=True) as db:
            self._require(db)
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            revision += 1
            now = datetime.now(timezone.utc).isoformat()
            db.execute("INSERT INTO changes VALUES (?, ?, ?)",
                       (revision, now, _canonical([{"op": "capture_files", "snapshot_id": identity, "sha256": digest}])))
            db.execute("INSERT INTO project_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                       (identity, "files", digest, encoded, now, revision))
            db.execute("UPDATE project SET revision=?", (revision,))
        return {"revision": revision, "snapshot": self.get(identity)}

    def verify(self, snapshot_id):
        snapshot = self.get(snapshot_id)
        results = []
        for file in snapshot["manifest"]["files"]:
            state, error = "ok", None
            try:
                self._verify_object(self._object(file["sha256"]), file["sha256"], file["size"])
            except FileNotFoundError:
                state, error = "missing", "Snapshot object is missing"
            except (OSError, ProjectError) as exc:
                state, error = "invalid", str(exc)
            results.append({"record_id": file["record_id"], "sha256": file["sha256"], "state": state, "error": error})
        return {"snapshot_id": snapshot_id, "ok": all(file["state"] == "ok" for file in results), "files": results}

    def resolve(self, snapshot_id, record_id):
        _id(record_id)
        snapshot = self.get(snapshot_id)
        file = next((file for file in snapshot["manifest"]["files"] if file["record_id"] == record_id), None)
        if file is None:
            raise ProjectError("File record is not part of this input snapshot")
        path = self._object(file["sha256"])
        self._verify_object(path, file["sha256"], file["size"])
        return {"snapshot_id": snapshot_id, **file, "path": str(path)}
