"""Receiver-only durable file offers, explicit grants and no-replace publication.

No constructor/read starts work. Network waits belong outside every lease here.
Byte commits are one fixed chunk; whole-file verification runs without Authority
locks, then a short current lease rechecks its original intent before publication.
"""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from suan.materials.jobs import Lease, Locked
from .identity import _directory, _ordinary
from .pairing import validate_offer
from .file_io import Directory, FileStorageError
from .manifests import validate_manifest, manifest_sha256, portable_name
from .file_protocol import (FILE_METHODS, FILE_MUTATIONS, CHUNK_BYTES, DATA, FileFrame,
                            FileProtocolError, validate_file_params, request_sha256,
                            validate_file_result, decode_frame, encode_frame, encode_receipt)


MAX_TRANSFERS = 128
MAX_OPERATIONS = 4096
MAX_DECLARED_BYTES = 8 * 1024**3
_APP_ID = 0x53545046
_METADATA_BYTES = 3 * 1024**2


class FileStoreError(FileProtocolError):
    pass


def _fail(code="unavailable", message="Peer file operation is unavailable"):
    raise FileStoreError(code, message)


def _json(value):
    try:
        result = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(result.encode("utf-8")) > _METADATA_BYTES:
            _fail("limit_exceeded")
        return result
    except (ValueError, TypeError, UnicodeError):
        _fail("invalid_params")


def _decode(value):
    if type(value) is not str or len(value.encode("utf-8")) > _METADATA_BYTES:
        _fail()
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        _fail()


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        _fail("invalid_params")
    return value


class FileStore:
    def __init__(self, directory, pairing, *, clock=time.time):
        self.directory = Path(directory).absolute()
        self.path = self.directory / "peer-files.sqlite3"
        self.pairing, self._clock, self._identity = pairing, clock, None

    def __repr__(self):
        return "<PeerFileStore>"

    def capabilities(self, context):
        with self.pairing.peer_access(context):
            return {method: 1 for method in FILE_METHODS}

    @contextmanager
    def _connect(self, *, write=False):
        db, handling = None, False
        try:
            try:
                _directory(self.directory, create=write)
            except FileNotFoundError:
                if self._identity is not None:
                    _fail()
                yield None
                return
            created = False
            if write:
                if self._identity is not None and not self.path.exists():
                    _fail()
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(fd)
                    created = True
                except FileExistsError:
                    pass
            try:
                identity = _ordinary(self.path, private=True)
            except FileNotFoundError:
                if self._identity is not None or write:
                    _fail()
                yield None
                return
            if self._identity is not None and self._identity != identity:
                _fail()
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                 uri=True, isolation_level=None, timeout=10)
            db.row_factory = sqlite3.Row
            if write:
                db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if created:
                db.execute("CREATE TABLE transfers (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                db.execute("CREATE TABLE operations (id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL, peer TEXT NOT NULL, "
                           "method TEXT NOT NULL, request TEXT NOT NULL, receipt TEXT)")
                db.execute("CREATE TABLE offers (id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL, params TEXT NOT NULL)")
                db.execute("CREATE TABLE chunks (transfer_id TEXT NOT NULL, file_id TEXT NOT NULL, sequence INTEGER NOT NULL, "
                           "offset INTEGER NOT NULL, length INTEGER NOT NULL, sha256 TEXT NOT NULL, "
                           "PRIMARY KEY(transfer_id,file_id,sequence))")
                db.execute(f"PRAGMA application_id={_APP_ID}")
                db.execute("PRAGMA user_version=1")
                db.commit()
                db.execute("BEGIN IMMEDIATE")
            if (db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID
                    or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or _ordinary(self.path, private=True) != identity):
                _fail()
            self._identity = identity
            handling = True
            yield db
            handling = False
            if _ordinary(self.path, private=True) != identity:
                _fail()
            db.commit()
        except (sqlite3.Error, OSError):
            if handling:
                raise
            _fail()
        finally:
            if db is not None:
                db.close()

    @contextmanager
    def _write(self):
        try:
            _directory(self.directory, create=True)
            with Lease(self.directory / "files.lock"):
                yield
        except Locked:
            _fail("busy", "Another peer file acceptance is in progress")

    @staticmethod
    def _row(db, transfer_id):
        row = None if db is None else db.execute("SELECT record FROM transfers WHERE id=?", (_uuid(transfer_id),)).fetchone()
        if row is None:
            _fail("not_found", "Peer file transfer was not found")
        result = _decode(row[0])
        if result.get("transfer_id") != transfer_id or result.get("role") != "receiver":
            _fail()
        return result

    @staticmethod
    def _save(db, row):
        db.execute("INSERT OR REPLACE INTO transfers VALUES (?,?)", (row["transfer_id"], _json(row)))

    @staticmethod
    def _peer(row, peer):
        if (row["host_owner_id"], row["host_peer_id"], row["recipient_owner_id"], row["recipient_peer_id"]) != (
                peer.remote_owner_id, peer.remote_peer_id, peer.owner_id, peer.local_peer_id):
            _fail("forbidden")

    @staticmethod
    def _target(row, params):
        if any(row[key] != params[key] for key in ("session_id", "transfer_id", "manifest_sha256")):
            _fail("conflict")

    @staticmethod
    def _grant(row, lease, grant_id):
        if (lease.role != "recipient" or row.get("grant") is None or not row["grant"].get("active")
                or row["grant"]["id"] != grant_id
                or row["session_id"] != lease.session_id or row["grant"]["epoch"] != lease.session_epoch
                or row["offer"]["session_epoch"] != lease.session_epoch
                or row["grant"]["identity_generation"] != lease.identity_generation
                or row["grant"]["peer_epoch"] != lease.peer_epoch
                or row["grant"]["registry_id"] != lease.registry_id):
            _fail("forbidden", "A current exact-file grant is required")
        FileStore._peer(row, lease)

    @staticmethod
    def _operation(db, operation_id, peer, method=None, params=None):
        item = None if db is None else db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if item is None:
            return None
        if item["peer"] != peer:
            _fail("forbidden")
        if method is not None and (item["method"] != method or item["request"] != _json(params)):
            _fail("conflict", "File operation UUID belongs to another request")
        return item

    @staticmethod
    def _reserve(db, peer, method, params):
        if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
            _fail("limit_exceeded")
        db.execute("INSERT INTO operations VALUES (?,?,?,?,?,NULL)",
                   (params["operation_id"], params["transfer_id"], peer, method, _json(params)))

    @staticmethod
    def _operation_dto(item):
        if item is None or not item["method"].startswith("files."):
            return None
        return {"operation_id": item["id"], "method": item["method"],
                "request_sha256": request_sha256(item["method"], _decode(item["request"])),
                "state": "completed" if item["receipt"] is not None else "uncertain"}

    def _result(self, row, operation=None):
        return {key: row[key] for key in ("session_id", "transfer_id", "manifest_sha256", "state")} | {
            "grant_id": None if row.get("grant") is None else row["grant"]["id"],
            "files": row["progress"], "operation": self._operation_dto(operation),
            "completion": row.get("completion")}

    def _finish(self, db, row, method, params):
        item = self._operation(db, params["operation_id"], row["host_peer_id"], method, params)
        op = dict(item)
        op["receipt"] = "completed"
        result = self._result(row, op)
        # Pending-offer cancellation has a null grant even when an old grant exists.
        if method == "files.cancel":
            result["grant_id"] = params["grant_id"]
        result = validate_file_result(method, result, params=params, manifest=row["manifest"])
        self._save(db, row)
        db.execute("UPDATE operations SET receipt=? WHERE id=?", (_json(result), params["operation_id"]))
        return result

    def manifest(self, transfer_id):
        with self._connect() as db:
            return validate_manifest(self._row(db, transfer_id)["manifest"])

    def get(self, transfer_id):
        """Local historical metadata only; it grants no current peer authority."""
        with self._connect() as db:
            return _decode(_json(self._result(self._row(db, transfer_id))))

    def reviewed_offer(self, transfer_id):
        """Exact local pending-offer review; never an implicit acceptance/grant."""
        with self._connect() as db:
            row = self._row(db, transfer_id)
            identity = _uuid(row["pending_offer"])
            saved = self._operation(db, identity, row["host_peer_id"])
            if saved is None or saved["method"] != "files.offer":
                _fail()
            params = validate_file_params("files.offer", _decode(saved["request"]))
            self._target(row, params)
            if params["manifest"] != row["manifest"] or params["session_offer"] != row["offer"]:
                _fail("conflict")
            return {"transfer_id": transfer_id, "offer_operation_id": identity,
                    "session_offer": params["session_offer"], "manifest": params["manifest"],
                    "manifest_sha256": params["manifest_sha256"]}

    def list(self, *, offset=0, limit=50):
        """Passive local inbox/audit page; no paths, nonces or asset I/O/grants."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            _fail("invalid_params")
        with self._connect() as db:
            if db is None:
                return []
            return [_decode(_json(self._result(self._row(db, row[0])))) for row in
                    db.execute("SELECT id FROM transfers ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]

    def _replay(self, db, peer, method, params):
        old = self._operation(db, params["operation_id"], peer.remote_peer_id, method, params)
        if old is None:
            return None
        if old["receipt"] is None:
            _fail("unavailable", "Original file operation outcome is uncertain; query its identity")
        return _decode(old["receipt"])

    def call(self, context, method, params):
        params = validate_file_params(method, params)
        with self.pairing.peer_access(context) as peer:
            with self._connect() as db:
                if method in FILE_MUTATIONS:
                    replay = self._replay(db, peer, method, params)
                    if replay is not None:
                        return replay
                if method == "files.status":
                    row = self._row(db, params["transfer_id"])
                    self._peer(row, peer)
                    self._target(row, params)
                    item = None if params["operation_id"] is None else self._operation(db, params["operation_id"], peer.remote_peer_id)
                    if item is not None and item["transfer_id"] != row["transfer_id"]:
                        _fail("conflict")
                    return validate_file_result(method, self._result(row, item), params=params, manifest=row["manifest"])
            if method == "files.offer":
                return self._offer(peer, params)
            if method == "files.cancel" and params["grant_id"] is None:
                with self._write(), self._connect(write=True) as db:
                    row = self._row(db, params["transfer_id"])
                    self._peer(row, peer)
                    self._target(row, params)
                    if (row["state"] not in {"offered", "interrupted"} or row.get("phase") == "publishing"
                            or row.get("grant") is not None and row["grant"]["epoch"] == row["offer"]["session_epoch"]):
                        _fail("forbidden")
                    self._reserve(db, peer.remote_peer_id, method, params)
                    row["state"] = "cancelled"
                    return self._finish(db, row, method, params)
        # A current session lease is acquired afresh for each actual business step.
        if method in {"files.start", "files.resume"}:
            return self._start(context, method, params)
        if method == "files.complete":
            return self._complete(context, params)
        if method == "files.cancel":
            with self.pairing.session_access(context, params["session_id"]) as lease, self._write(), self._connect(write=True) as db:
                replay = self._replay(db, lease, method, params)
                if replay is not None:
                    return replay
                row = self._row(db, params["transfer_id"])
                self._target(row, params)
                self._grant(row, lease, params["grant_id"])
                if row["state"] == "complete":
                    _fail("conflict")
                self._reserve(db, lease.remote_peer_id, method, params)
                row["state"], row["active_operation"] = "cancelled", None
                return self._finish(db, row, method, params)
        _fail("unsupported")

    def _offer(self, peer, params):
        offer = validate_offer(params["session_offer"])
        current = self.pairing.identity.info()["card"]
        pin = self.pairing.pin(peer.remote_peer_id)["card"]
        now = self._clock()
        if (type(now) not in (int, float) or not math.isfinite(now) or offer["host"] != pin
                or offer["recipient"] != current or not now < offer["expires_at"] <= now + 3600):
            _fail("forbidden")
        with self._write(), self._connect(write=True) as db:
            existing = db.execute("SELECT record FROM transfers WHERE id=?", (params["transfer_id"],)).fetchone()
            if existing is None:
                records = [_decode(item[0]) for item in db.execute("SELECT record FROM transfers")]
                declared = sum(sum(f["bytes"] for f in r["manifest"]["files"]) for r in records)
                if (len(records) >= MAX_TRANSFERS or declared + sum(f["bytes"] for f in params["manifest"]["files"]) > MAX_DECLARED_BYTES):
                    _fail("limit_exceeded")
                row = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256", "manifest")}
                row.update(role="receiver", host_owner_id=peer.remote_owner_id, host_peer_id=peer.remote_peer_id,
                           recipient_owner_id=peer.owner_id, recipient_peer_id=peer.local_peer_id,
                           state="offered", target=None, grant=None, completion=None, stage_identity=None,
                           active_operation=None, phase=None, nonce=secrets.token_hex(16),
                           progress=[{"file_id": f["file_id"], "bytes": f["bytes"], "committed_bytes": 0,
                                      "next_sequence": 0, "verified_sha256": None} for f in params["manifest"]["files"]])
            else:
                row = self._row(db, params["transfer_id"])
                self._peer(row, peer)
                self._target(row, params)
                if (row["manifest"] != params["manifest"] or row["state"] in {"cancelled", "complete", "failed"}
                        or row.get("phase") == "publishing" or offer["session_epoch"] <= row["offer"]["session_epoch"]):
                    _fail("conflict")
                if any(offer[side] != row["offer"][side] for side in ("host", "recipient")):
                    _fail("forbidden")
                row["state"], row["active_operation"] = "interrupted", None
            self._reserve(db, peer.remote_peer_id, "files.offer", params)
            db.execute("INSERT INTO offers VALUES (?,?,?)", (params["operation_id"], row["transfer_id"], _json(params)))
            row["offer"], row["pending_offer"] = offer, params["operation_id"]
            return self._finish(db, row, "files.offer", params)

    def accept(self, operation_id, context, transfer_id, offer_operation_id, target):
        _uuid(operation_id), _uuid(transfer_id), _uuid(offer_operation_id)
        target = Path(target)
        if not target.is_absolute() or ".." in target.parts:
            _fail("invalid_params")
        portable_name(target.name)
        request = {"operation_id": operation_id, "transfer_id": transfer_id,
                   "offer_operation_id": offer_operation_id, "target": str(target)}
        with self.pairing.peer_access(context) as peer, self._write(), self._connect(write=True) as db:
            old = self._operation(db, operation_id, peer.remote_peer_id, "local.accept", request)
            if old is not None:
                if old["receipt"] is None:
                    _fail("unavailable", "Original local file acceptance is uncertain")
                return _decode(old["receipt"])
            row = self._row(db, transfer_id)
            self._peer(row, peer)
            if row["pending_offer"] != offer_operation_id or row["state"] not in {"offered", "interrupted"}:
                _fail("conflict")
            if row["target"] is not None and row["target"] != str(target):
                _fail("conflict", "An existing transfer cannot change its local destination")
            with Directory.open(target.parent) as parent:
                try:
                    with parent.child(target.name):
                        _fail("conflict", "File destination already exists")
                except FileNotFoundError:
                    pass
                parent_identity = list(parent.identity)
            self._reserve(db, peer.remote_peer_id, "local.accept", request)
            reviewed, offer = row, row["offer"]
        # Explicit user action, outside any Files/Authority nested transaction.
        pairing_id = str(uuid5(NAMESPACE_URL, "stk.peer.file.accept/1/" + operation_id))
        self.pairing.accept_session(pairing_id, context, offer)
        with self.pairing.session_access(context, offer["session_id"]) as lease, self._write(), self._connect(write=True) as db:
            row = self._row(db, transfer_id)
            intent = self._operation(db, operation_id, lease.remote_peer_id, "local.accept", request)
            # Session acceptance spans no Files lease. A local revoke/cancel or
            # another accepted intent must not be overwritten by this older
            # acceptance, even when the reviewed offer itself did not change.
            if intent is None or intent["receipt"] is not None or row != reviewed:
                _fail("conflict", "Original file acceptance is no longer current")
            row.update(target=str(target), parent_identity=parent_identity,
                       stage_name=".stk-peer-" + UUID(transfer_id).hex + "-" + row["nonce"],
                       grant={"id": str(uuid4()), "active": True, "epoch": lease.session_epoch, "identity_generation": lease.identity_generation,
                              "peer_epoch": lease.peer_epoch, "registry_id": lease.registry_id})
            row["state"] = "interrupted" if any(p["committed_bytes"] for p in row["progress"]) or row["stage_identity"] else "accepted"
            self._save(db, row)
            result = {"operation_id": operation_id, "request_sha256": hashlib.sha256(_json(request).encode()).hexdigest(),
                      "result": self._result(row)}
            db.execute("UPDATE operations SET receipt=? WHERE id=?", (_json(result), operation_id))
            return result

    def revoke(self, operation_id, transfer_id):
        """Explicit local owner withdrawal; does not delete or recall received bytes."""
        _uuid(operation_id), _uuid(transfer_id)
        request = {"operation_id": operation_id, "transfer_id": transfer_id}
        with self.pairing.authority._transaction(), self._write(), self._connect(write=True) as db:
            row = self._row(db, transfer_id)
            if row["recipient_owner_id"] != self.pairing.authority.owner_id:
                _fail("forbidden")
            old = self._operation(db, operation_id, row["host_peer_id"], "local.revoke", request)
            if old is not None:
                if old["receipt"] is None:
                    _fail()
                return _decode(old["receipt"])
            self._reserve(db, row["host_peer_id"], "local.revoke", request)
            if row.get("grant"):
                row["grant"]["active"] = False
            if row["state"] != "complete":
                row["state"], row["active_operation"] = "cancelled", None
            self._save(db, row)
            result = {"operation_id": operation_id, "request_sha256": hashlib.sha256(_json(request).encode()).hexdigest(),
                      "result": self._result(row)}
            db.execute("UPDATE operations SET receipt=? WHERE id=?", (_json(result), operation_id))
            return result

    @contextmanager
    def _stage(self, row, *, create=False):
        with Directory.open(Path(row["target"]).parent) as parent:
            if list(parent.identity) != row["parent_identity"]:
                _fail("conflict", "File destination parent changed")
            with parent.child(row["stage_name"], create=create, exclusive=create) as stage:
                if not create and list(stage.identity) != row["stage_identity"]:
                    _fail("conflict", "File staging identity changed")
                yield parent, stage

    @staticmethod
    @contextmanager
    def _file(stage, name, *, create=False, write=True):
        parts = name.split("/")
        with ExitStack() as stack:
            directory = stage
            for part in parts[:-1]:
                directory = stack.enter_context(directory.child(part, create=create))
            yield stack.enter_context(directory.file(parts[-1], create=create, write=write))

    @staticmethod
    def _marker(row):
        return _json({"transfer_id": row["transfer_id"], "manifest_sha256": row["manifest_sha256"],
                      "nonce": row["nonce"], "host_peer_id": row["host_peer_id"],
                      "recipient_peer_id": row["recipient_peer_id"]}).encode()

    def _check_marker(self, stage, row):
        with stage.file(".stk-peer-receipt.json") as stream:
            if stream.read(16385) != self._marker(row):
                _fail("conflict", "Private staging receipt does not match")

    def _start(self, context, method, params):
        with self.pairing.session_access(context, params["session_id"]) as lease, self._write():
            with self._connect(write=True) as db:
                replay = self._replay(db, lease, method, params)
                if replay is not None:
                    return replay
                row = self._row(db, params["transfer_id"])
                self._target(row, params)
                self._grant(row, lease, params["grant_id"])
                if row["state"] not in ({"accepted"} if method == "files.start" else {"accepted", "receiving", "interrupted"}):
                    _fail("conflict")
                if row.get("phase") == "publishing":
                    _fail("unavailable", "Publication outcome remains uncertain")
                self._reserve(db, lease.remote_peer_id, method, params)
                row["state"], row["active_operation"] = "interrupted", params["operation_id"]
                row["phase"] = "starting" if row["stage_identity"] is None else "resuming"
                self._save(db, row)
            if row["stage_identity"] is None:
                with self._stage(row, create=True) as (_, stage):
                    row["stage_identity"] = list(stage.identity)
                    with stage.file(".stk-peer-receipt.json", create=True, write=True) as marker:
                        marker.write(self._marker(row)); os.fsync(marker.fileno())
                    stage.sync()
                    with self._connect(write=True) as db:
                        self._save(db, row)
                    for item in row["manifest"]["files"]:
                        with self._file(stage, item["name"], create=True) as stream:
                            os.fsync(stream.fileno())
                with self._connect(write=True) as db:
                    row["state"], row["phase"] = "receiving", None
                    return self._finish(db, row, method, params)
        # No Authority/identity/pairing lease or Files transaction spans the scan.
        # Cancellation/reoffer/new resume may supersede this original intent.
        checkpoint = self._verify_prefix(row, allow_tail=True, allow_missing=True)
        with self.pairing.session_access(context, params["session_id"]) as lease, self._write(), self._connect(write=True) as db:
            current = self._row(db, params["transfer_id"])
            self._grant(current, lease, params["grant_id"])
            if (current["state"] != "interrupted" or current["phase"] != "resuming"
                    or current["active_operation"] != params["operation_id"]
                    or any(current[key] != row[key] for key in
                           ("progress", "stage_identity", "parent_identity", "target", "nonce", "manifest_sha256"))):
                _fail("conflict", "Original resume checkpoint is no longer current")
            self._apply_prefix_checkpoint(db, current, checkpoint)
            current["state"], current["phase"] = "receiving", None
            return self._finish(db, current, method, params)

    @staticmethod
    def _stamp(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    @staticmethod
    def _chunks(db, row, item):
        # At most ceil(1GiB/60KiB) metadata rows per file; never read a file-sized
        # payload or hold a SQLite read transaction while hashing its bytes.
        maximum = (item["bytes"] + CHUNK_BYTES - 1) // CHUNK_BYTES
        chunks = db.execute("SELECT sequence,offset,length,sha256 FROM chunks WHERE transfer_id=? AND file_id=? "
                            "ORDER BY sequence LIMIT ?", (row["transfer_id"], item["file_id"], maximum + 1)).fetchall()
        if len(chunks) > maximum:
            _fail("conflict", "File chunk journal exceeds its frozen bounds")
        return [tuple(chunk) for chunk in chunks]

    @staticmethod
    def _checkpoint(chunks):
        return hashlib.sha256(_json(chunks).encode("utf-8")).hexdigest()

    def _verify_prefix(self, row, *, allow_tail=False, allow_missing=False):
        result = []
        with self._stage(row) as (_, stage):
            self._check_marker(stage, row)
            for item, progress in zip(row["manifest"]["files"], row["progress"]):
                with self._connect() as db:
                    chunks = self._chunks(db, row, item)
                try:
                    with self._file(stage, item["name"], write=False) as stream:
                        before = self._stamp(os.fstat(stream.fileno()))
                        offset, sequence = 0, 0
                        for seq, start, length, digest in chunks:
                            if (seq != sequence or start != offset or type(length) is not int
                                    or not 1 <= length <= CHUNK_BYTES or length != min(CHUNK_BYTES, item["bytes"] - offset)):
                                _fail()
                            body = stream.read(length)
                            if len(body) != length or hashlib.sha256(body).hexdigest() != digest:
                                _fail("conflict", "Durable file prefix changed")
                            offset += len(body); sequence += 1
                        if (offset, sequence) != (progress["committed_bytes"], progress["next_sequence"]):
                            _fail()
                        after = self._stamp(os.fstat(stream.fileno()))
                        if before != after:
                            _fail("conflict", "File changed during prefix verification")
                        actual = after[2]
                        if actual < offset:
                            _fail("conflict", "Durable file prefix was truncated")
                        if actual != offset and not allow_tail:
                            _fail("conflict", "File has an uncommitted tail")
                        result.append({"stamp": after, "journal": self._checkpoint(chunks)})
                except FileNotFoundError:
                    if not allow_missing or progress["committed_bytes"] or chunks:
                        raise
                    result.append({"stamp": None, "journal": self._checkpoint(chunks)})
            stage.check()
        return result

    def _apply_prefix_checkpoint(self, db, row, checkpoint):
        # Validate the entire bounded checkpoint before truncating/creating any
        # leaf. Open files stay pinned through the accepted repair and journal.
        if len(checkpoint) != len(row["manifest"]["files"]):
            _fail("conflict", "File prefix checkpoint is incomplete")
        with self._stage(row) as (_, stage), ExitStack() as handles:
            self._check_marker(stage, row)
            pending = []
            for item, progress, saved in zip(row["manifest"]["files"], row["progress"], checkpoint):
                if self._checkpoint(self._chunks(db, row, item)) != saved["journal"]:
                    _fail("conflict", "File journal checkpoint changed")
                if saved["stamp"] is None:
                    try:
                        with self._file(stage, item["name"], write=False):
                            _fail("conflict", "Missing transfer file appeared after verification")
                    except FileNotFoundError:
                        pass
                    stream = None
                else:
                    stream = handles.enter_context(self._file(stage, item["name"]))
                    if self._stamp(os.fstat(stream.fileno())) != saved["stamp"]:
                        _fail("conflict", "File identity checkpoint changed")
                pending.append((item, progress, stream))
            for item, progress, stream in pending:
                if stream is None:
                    with self._file(stage, item["name"], create=True) as created:
                        os.fsync(created.fileno())
                elif os.fstat(stream.fileno()).st_size != progress["committed_bytes"]:
                    stream.truncate(progress["committed_bytes"])
                    os.fsync(stream.fileno())
            stage.sync()

    def accept_data(self, context, frame):
        data = decode_frame(frame if type(frame) is bytes else encode_frame(frame))
        if data.kind != DATA:
            _fail("invalid_params")
        with self.pairing.peer_access(context) as peer, self._connect() as db:
            target = self._row(db, data.transfer_id)
            self._peer(target, peer)
            session_id = target["session_id"]
        with self.pairing.session_access(context, session_id) as lease, self._write(), self._connect(write=True) as db:
            row = self._row(db, data.transfer_id)
            self._grant(row, lease, row["grant"]["id"] if row.get("grant") else None)
            if row["state"] != "receiving":
                _fail("conflict")
            selected = [(i, f) for i, f in enumerate(row["manifest"]["files"]) if f["file_id"] == data.file_id]
            if len(selected) != 1:
                _fail("forbidden")
            index, item = selected[0]
            progress = row["progress"][index]
            old = db.execute("SELECT * FROM chunks WHERE transfer_id=? AND file_id=? AND sequence=?",
                             (data.transfer_id, data.file_id, data.sequence)).fetchone()
            with self._stage(row) as (_, stage):
                self._check_marker(stage, row)
                with self._file(stage, item["name"]) as stream:
                    if old is not None:
                        if (old["offset"], old["length"], old["sha256"]) != (data.offset, data.length, data.sha256):
                            _fail("conflict")
                        stream.seek(data.offset)
                        if stream.read(data.length) != data.body:
                            _fail("conflict", "Durable file prefix changed")
                        return encode_receipt(data)
                    if (data.offset != progress["committed_bytes"] or data.sequence != progress["next_sequence"]
                            or data.length != min(CHUNK_BYTES, item["bytes"] - data.offset)
                            or os.fstat(stream.fileno()).st_size != data.offset):
                        _fail("conflict", "File block does not match its next durable offset")
                    stream.seek(data.offset)
                    if stream.write(data.body) != data.length:
                        _fail()
                    os.fsync(stream.fileno())
                    db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?)", (data.transfer_id, data.file_id, data.sequence,
                                                                         data.offset, data.length, data.sha256))
                    progress["committed_bytes"] += data.length
                    progress["next_sequence"] += 1
                    self._save(db, row)
            receipt = encode_receipt(data)
        # The contextmanager committed FULL before the receipt can escape.
        return receipt

    def _whole(self, row):
        stamps = []
        self._verify_prefix(row)
        with self._stage(row) as (_, stage):
            for item in row["manifest"]["files"]:
                with self._file(stage, item["name"]) as stream:
                    before = os.fstat(stream.fileno())
                    digest = hashlib.sha256()
                    while True:
                        block = stream.read(CHUNK_BYTES)
                        if not block:
                            break
                        digest.update(block)
                    after = os.fstat(stream.fileno())
                    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
                    if stamp(before) != stamp(after) or after.st_size != item["bytes"] or digest.hexdigest() != item["sha256"]:
                        _fail("conflict", "Complete file bytes do not match the frozen manifest")
                    stamps.append(stamp(after))
        return stamps

    def _complete(self, context, params):
        with self.pairing.session_access(context, params["session_id"]) as lease, self._write(), self._connect(write=True) as db:
            replay = self._replay(db, lease, "files.complete", params)
            if replay is not None:
                return replay
            row = self._row(db, params["transfer_id"])
            self._target(row, params)
            self._grant(row, lease, params["grant_id"])
            if row["state"] != "receiving" or any(p["bytes"] != p["committed_bytes"] for p in row["progress"]):
                _fail("conflict")
            self._reserve(db, lease.remote_peer_id, "files.complete", params)
            row["state"], row["phase"], row["active_operation"] = "interrupted", "verifying", params["operation_id"]
            self._save(db, row)
        # Revocation and control replies remain available during full-file hashing.
        stamps = self._whole(row)
        with self.pairing.session_access(context, params["session_id"]) as lease, self._write():
            with self._connect(write=True) as db:
                current = self._row(db, params["transfer_id"])
                self._grant(current, lease, params["grant_id"])
                if (current["phase"] != "verifying" or current["active_operation"] != params["operation_id"]
                        or current["state"] != "interrupted"):
                    _fail("conflict")
                with self._stage(current) as (_, stage):
                    for item, stamp in zip(current["manifest"]["files"], stamps):
                        with self._file(stage, item["name"]) as stream:
                            info = os.fstat(stream.fileno())
                            if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != stamp:
                                _fail("conflict")
                current["phase"] = "publishing"
                self._save(db, current)
            # Publishing intent is durable before the atomic no-replace operation.
            with self._stage(current) as (parent, _):
                parent.publish(current["stage_name"], Path(current["target"]).name,
                               expected_identity=current["stage_identity"])
            with self._connect(write=True) as db:
                current["state"], current["phase"] = "complete", None
                for progress, item in zip(current["progress"], current["manifest"]["files"]):
                    progress["verified_sha256"] = item["sha256"]
                current["completion"] = {"format": "stk.peer-files-receipt/1", "transfer_id": current["transfer_id"],
                    "manifest_sha256": current["manifest_sha256"], "files": [
                        {key: item[key] for key in ("file_id", "bytes", "sha256")} for item in current["manifest"]["files"]]}
                return self._finish(db, current, "files.complete", params)


__all__ = ["FileStore", "FileStoreError", "MAX_TRANSFERS", "MAX_OPERATIONS", "MAX_DECLARED_BYTES"]
