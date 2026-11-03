"""Explicit snapshot-file sending and the production receiver/endpoint adapter.

Original controls and each bounded DATA intent commit before network I/O. Reads,
reopening, and receipt queries never send or resume. Only a new explicit resume
may reconcile the one unacknowledged block against a verified receiver prefix.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from suan.materials.jobs import Lease, Locked
from .identity import _directory, _ordinary
from .file_io import Directory
from .file_protocol import (CHUNK_BYTES, FILE_MUTATIONS, FileProtocolError,
                            decode_frame, encode_data, request_sha256,
                            validate_file_params, validate_file_result, validate_receipt)
from .manifests import prepare_manifest, validate_manifest, manifest_sha256


MAX_PLANS = 128
MAX_TRANSFERS = 128
MAX_OPERATIONS = 4096
MAX_ATTEMPTS = 250000
MAX_DECLARED_BYTES = 8 * 1024**3
MAX_JOURNAL_BYTES = 128 * 1024**2
_APP_ID = 0x53545053


class FileSendError(FileProtocolError):
    pass


class FileSendUncertain(FileSendError):
    def __init__(self, operation_id, transfer_id):
        self.operation_id, self.transfer_id = operation_id, transfer_id
        super().__init__("unavailable", "Original file send is uncertain; inspect it before explicit resume")


def _fail(code="unavailable", message="Peer file sending is unavailable"):
    raise FileSendError(code, message) from None


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        _fail("invalid_params")
    return value


def _json(value):
    try:
        result = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(result.encode()) > 3 * 1024**2:
            _fail("limit_exceeded")
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail("invalid_params")


def _copy(value):
    return json.loads(_json(value))


def _stamp(stream):
    s = os.fstat(stream.fileno())
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


class ReceiverAdapter:
    """Only authenticated incoming file operations; never local approval RPCs."""
    def __init__(self, store):
        self.store = store

    def capabilities(self, context):
        return self.store.capabilities(context)

    def call(self, context, method, params):
        result = self.store.call(context, method, params)
        return result, self.store.manifest(params["transfer_id"])

    def receive_frame(self, context, frame):
        return self.store.accept_data(context, frame)


class FileSender:
    """Local-owner API with a passive constructor and a private bounded journal."""
    def __init__(self, directory, pairing, *, monotonic=time.monotonic):
        self.directory = Path(directory).absolute()
        self.path = self.directory / "peer-sends.sqlite3"
        self.pairing, self._monotonic, self._identity = pairing, monotonic, None

    def __repr__(self):
        return "<PeerFileSender>"

    @contextmanager
    def _db(self, *, write=False):
        db = None
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
            if self._identity is not None and identity != self._identity:
                _fail()
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                 uri=True, isolation_level=None, timeout=10)
            db.row_factory = sqlite3.Row
            if write:
                db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if created:
                for table in ("plans", "transfers", "operations", "sends", "attempts"):
                    db.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                db.execute(f"PRAGMA application_id={_APP_ID}")
                db.execute("PRAGMA user_version=1")
                db.commit()
                db.execute("BEGIN IMMEDIATE")
            if (db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID
                    or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or _ordinary(self.path, private=True) != identity):
                _fail()
            self._identity = identity
            yield db
            if _ordinary(self.path, private=True) != identity:
                _fail()
            if write and db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0] > MAX_JOURNAL_BYTES:
                _fail("limit_exceeded")
            db.commit()
        except sqlite3.Error:
            _fail()
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _get(db, table, identity, *, optional=False):
        row = None if db is None else db.execute(f"SELECT record FROM {table} WHERE id=?", (_uuid(identity),)).fetchone()
        if row is None:
            if optional:
                return None
            _fail("not_found")
        try:
            if len(row[0].encode()) > 3 * 1024**2:
                _fail()
            return json.loads(row[0])
        except (ValueError, TypeError):
            _fail()

    @staticmethod
    def _put(db, table, identity, value):
        db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?)", (identity, _json(value)))

    @staticmethod
    def _room(db, table, limit):
        if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= limit:
            _fail("limit_exceeded")

    @staticmethod
    def _peer(row, peer):
        if (row["host_owner_id"], row["host_peer_id"], row["recipient_owner_id"], row["recipient_peer_id"]) != (
                peer.owner_id, peer.local_peer_id, peer.remote_owner_id, peer.remote_peer_id):
            _fail("forbidden")

    @staticmethod
    def _channel(endpoint, context):
        if endpoint.authenticated_context is not context:
            _fail("forbidden", "File sending requires its explicitly approved connection")

    def _authorize(self, row, lease):
        self._peer(row, lease)
        if (lease.role != "host" or not row["active"] or row["session_id"] != lease.session_id
                or row["session_epoch"] != lease.session_epoch
                or row["registry_id"] != lease.registry_id or row["peer_epoch"] != lease.peer_epoch
                or row["identity_generation"] != lease.identity_generation):
            _fail("forbidden", "A current explicit file sending approval is required")
        store = self.pairing.authority.bound_project(row["manifest"]["project_id"], row["database_generation"])
        if str(store.directory) != row["source_directory"]:
            _fail("forbidden")
        return store

    @staticmethod
    def _target(row):
        return {k: row[k] for k in ("session_id", "transfer_id", "manifest_sha256")}

    @staticmethod
    def _local_status(row):
        # Local paths, database identities and raw requests stay in the journal.
        return {k: _copy(row[k]) for k in ("transfer_id", "session_id", "manifest_sha256", "state", "active", "progress", "completion")}

    def prepare(self, operation_id, store, snapshot_id, record_ids, *, names=None, media_types=None):
        """Explicit local preparation; it grants no recipient and sends no bytes."""
        _uuid(operation_id), _uuid(snapshot_id)
        info = store.info()
        request = {"project_id": info["id"], "source_directory": str(store.directory), "snapshot_id": snapshot_id,
                   "record_ids": record_ids, "names": names, "media_types": media_types}
        _json(request)
        with self._db() as db:
            old = self._get(db, "plans", operation_id, optional=True)
            if old is not None:
                if old["request"] != request:
                    _fail("conflict")
                return _copy(old["receipt"])
        manifest = prepare_manifest(store, snapshot_id, record_ids, names=names, media_types=media_types)
        receipt = {"plan_id": operation_id, "manifest": manifest, "manifest_sha256": manifest_sha256(manifest)}
        with self._db(write=True) as db:
            old = self._get(db, "plans", operation_id, optional=True)
            if old is not None:
                if old["request"] != request:
                    _fail("conflict")
                return _copy(old["receipt"])
            self._room(db, "plans", MAX_PLANS)
            self._put(db, "plans", operation_id, {"request": request, "receipt": receipt})
        return _copy(receipt)

    def manifest(self, plan_id):
        with self._db() as db:
            return validate_manifest(self._get(db, "plans", plan_id)["receipt"]["manifest"])

    def transfer_manifest(self, transfer_id):
        """Detached immutable content for local review, not source-byte authority."""
        with self._db() as db:
            return validate_manifest(self._get(db, "transfers", transfer_id)["manifest"])

    def status(self, transfer_id):
        """Pure local observation, never a network or restoration trigger."""
        with self._db() as db:
            return self._local_status(self._get(db, "transfers", transfer_id))

    def list(self, *, offset=0, limit=50):
        """Bounded local history, never proof of a current connection or grant."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            _fail("invalid_params")
        with self._db() as db:
            if db is None:
                return []
            return [self._local_status(self._get(db, "transfers", row[0])) for row in
                    db.execute("SELECT id FROM transfers ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]

    def operation(self, operation_id):
        """Retained original-control observation; no request replay."""
        with self._db() as db:
            op = self._get(db, "operations", operation_id, optional=True)
            if op is None:
                return None
            return {"operation_id": operation_id, "method": op["method"], "params": _copy(op["params"]),
                    "receipt": _copy(op["receipt"]), "observation": _copy(op.get("observation"))}

    def _control(self, context, endpoint, method, params, *, reserved=False, expected_epoch=None):
        params = validate_file_params(method, params)
        self._channel(endpoint, context)
        with self.pairing.peer_access(context) as peer, self._db() as db:
            row = self._get(db, "transfers", params["transfer_id"])
            self._peer(row, peer)
            old = self._get(db, "operations", params["operation_id"], optional=True)
            if old is not None and not reserved:
                if old["method"] != method or old["params"] != params:
                    _fail("conflict")
                if old["receipt"] is None:
                    raise FileSendUncertain(params["operation_id"], params["transfer_id"])
                return _copy(old["receipt"])
        access = (self.pairing.peer_access(context) if method == "files.cancel" and params["grant_id"] is None
                  else self.pairing.session_access(context, row["session_id"]))
        with access as lease, self._db(write=True) as db:
            row = self._get(db, "transfers", params["transfer_id"])
            if method == "files.cancel":
                # Withdrawal grants no source-byte access, even after a rebind.
                self._peer(row, lease)
                if params["grant_id"] is not None and (lease.role != "host" or lease.session_id != row["session_id"]
                        or lease.session_epoch != row["session_epoch"] or lease.registry_id != row["registry_id"]
                        or lease.peer_epoch != row["peer_epoch"] or lease.identity_generation != row["identity_generation"]):
                    _fail("forbidden")
            else:
                self._authorize(row, lease)
            if expected_epoch is not None and row["session_epoch"] != expected_epoch:
                _fail("forbidden", "An earlier send cannot consume a newer approval")
            old = self._get(db, "operations", params["operation_id"], optional=True)
            if reserved:
                if old is None or old["method"] != method or old["params"] != params or old["receipt"] is not None:
                    _fail("conflict")
            else:
                if old is not None:
                    if old["method"] != method or old["params"] != params:
                        _fail("conflict")
                    if old["receipt"] is not None:
                        return _copy(old["receipt"])
                    raise FileSendUncertain(params["operation_id"], params["transfer_id"])
                self._room(db, "operations", MAX_OPERATIONS)
                self._put(db, "operations", params["operation_id"], {"method": method, "params": params, "receipt": None})
            frozen = row["manifest"]
        # Neither Authority, identity, pairing nor journal transactions span I/O.
        try:
            result = endpoint.request(method, params, file_manifest=frozen)
            result = validate_file_result(method, result, params=params, manifest=frozen)
        except Exception:
            raise FileSendUncertain(params["operation_id"], params["transfer_id"]) from None
        with self._db(write=True) as db:
            old = self._get(db, "operations", params["operation_id"])
            if old["method"] != method or old["params"] != params:
                _fail("conflict")
            old["receipt"] = result
            self._put(db, "operations", params["operation_id"], old)
        return result

    def offer(self, operation_id, context, endpoint, plan_id, database_generation, session_id, *, transfer_id=None):
        """Explicit Host selection for exactly this recipient; no DATA starts."""
        _uuid(operation_id), _uuid(database_generation), _uuid(session_id), _uuid(plan_id)
        self._channel(endpoint, context)
        reserved = False
        with self.pairing.session_access(context, session_id) as lease, self._db(write=True) as db:
            if lease.role != "host":
                _fail("forbidden")
            previous = self._get(db, "operations", operation_id, optional=True)
            if previous is not None:
                params = previous["params"]
                row = self._get(db, "transfers", params["transfer_id"])
                self._peer(row, lease)
                if (previous["method"] != "files.offer" or row["plan_id"] != plan_id
                        or row["database_generation"] != database_generation or row["session_id"] != session_id
                        or transfer_id is not None and transfer_id != row["transfer_id"]):
                    _fail("conflict")
            else:
                plan = self._get(db, "plans", plan_id)
                frozen = plan["receipt"]
                transfer_id = str(uuid4()) if transfer_id is None else _uuid(transfer_id)
                row = self._get(db, "transfers", transfer_id, optional=True)
                if row is None:
                    self._room(db, "transfers", MAX_TRANSFERS)
                    total = sum(sum(f["bytes"] for f in json.loads(r[0])["manifest"]["files"])
                                for r in db.execute("SELECT record FROM transfers"))
                    if total + sum(f["bytes"] for f in frozen["manifest"]["files"]) > MAX_DECLARED_BYTES:
                        _fail("limit_exceeded")
                    row = {"transfer_id": transfer_id, "plan_id": plan_id,
                           "source_directory": plan["request"]["source_directory"], "database_generation": database_generation,
                           "manifest": frozen["manifest"], "manifest_sha256": frozen["manifest_sha256"],
                           "session_id": session_id, "host_owner_id": lease.owner_id, "host_peer_id": lease.local_peer_id,
                           "recipient_owner_id": lease.remote_owner_id, "recipient_peer_id": lease.remote_peer_id,
                           "state": "offered", "active": True, "pending": None, "completion": None,
                           "progress": [{"file_id": f["file_id"], "bytes": f["bytes"], "committed_bytes": 0,
                                         "next_sequence": 0, "verified_sha256": None} for f in frozen["manifest"]["files"]]}
                else:
                    self._peer(row, lease)
                    if (not row["active"] or row["state"] in {"complete", "cancelled"}
                            or row["plan_id"] != plan_id or row["database_generation"] != database_generation
                            or row["session_id"] != session_id or lease.session_epoch <= row["session_epoch"]):
                        _fail("conflict")
                    row["state"] = "interrupted"
                row.update(session_epoch=lease.session_epoch, registry_id=lease.registry_id,
                           peer_epoch=lease.peer_epoch, identity_generation=lease.identity_generation)
                self._authorize(row, lease)
                session_offer = self.pairing.session(session_id)["offer"]
                params = {**self._target(row), "operation_id": operation_id,
                          "manifest": row["manifest"], "session_offer": session_offer}
                self._room(db, "operations", MAX_OPERATIONS)
                self._put(db, "operations", operation_id, {"method": "files.offer", "params": params, "receipt": None})
                reserved = True
                self._put(db, "transfers", transfer_id, row)
        return self._control(context, endpoint, "files.offer", params, reserved=reserved)

    def query(self, context, endpoint, transfer_id, *, operation_id=None):
        """Explicit network observation, not a send, grant or resume."""
        self._channel(endpoint, context)
        with self.pairing.peer_access(context) as peer, self._db() as db:
            row = self._get(db, "transfers", transfer_id)
            self._peer(row, peer)
            original = None if operation_id is None else self._get(db, "operations", operation_id)
            if original is not None and original["params"]["transfer_id"] != transfer_id:
                _fail("conflict")
            params = {**self._target(row), "operation_id": operation_id}
        binding = None if original is None else (original["method"], original["params"])
        result = endpoint.request("files.status", params, file_manifest=row["manifest"], file_operation=binding)
        result = validate_file_result("files.status", result, params=params, manifest=row["manifest"])
        if original is not None:
            op = result["operation"]
            if op is not None and (op["operation_id"] != operation_id or op["method"] != original["method"]
                    or op["request_sha256"] != request_sha256(original["method"], original["params"])):
                _fail("invalid_response")
            with self._db(write=True) as db:
                original = self._get(db, "operations", operation_id)
                original["observation"] = result
                self._put(db, "operations", operation_id, original)
        return result

    def revoke(self, operation_id, transfer_id):
        """Local owner withdrawal; accepted bytes/receipts cannot be recalled."""
        _uuid(operation_id)
        with self._db(write=True) as db:
            old = self._get(db, "operations", operation_id, optional=True)
            request = {"transfer_id": transfer_id}
            if old is not None:
                if old["method"] != "local.revoke" or old["params"] != request:
                    _fail("conflict")
                return _copy(old["receipt"])
            row = self._get(db, "transfers", transfer_id)
            self._room(db, "operations", MAX_OPERATIONS)
            row["active"] = False
            if row["state"] != "complete":
                row["state"] = "cancelled"
            receipt = {"operation_id": operation_id, "transfer_id": transfer_id, "active": False}
            self._put(db, "transfers", transfer_id, row)
            self._put(db, "operations", operation_id, {"method": "local.revoke", "params": request, "receipt": receipt})
            return receipt

    def cancel(self, operation_id, context, endpoint, transfer_id, *, grant_id=None):
        """Withdraw locally before the one explicit remote cancellation attempt."""
        _uuid(operation_id)
        self._channel(endpoint, context)
        reserved = False
        with self.pairing.peer_access(context) as peer, self._db(write=True) as db:
            row = self._get(db, "transfers", transfer_id)
            self._peer(row, peer)
            params = validate_file_params("files.cancel", {**self._target(row), "operation_id": operation_id, "grant_id": grant_id})
            old = self._get(db, "operations", operation_id, optional=True)
            if old is not None:
                if old["method"] != "files.cancel" or old["params"] != params:
                    _fail("conflict")
            else:
                self._room(db, "operations", MAX_OPERATIONS)
                self._put(db, "operations", operation_id, {"method": "files.cancel", "params": params, "receipt": None})
                row["active"] = False
                if row["state"] != "complete":
                    row["state"] = "cancelled"
                self._put(db, "transfers", transfer_id, row)
                reserved = True
        return self._control(context, endpoint, "files.cancel", params, reserved=reserved)

    def recover(self, operation_id, context, endpoint, send_operation_id):
        """Explicitly adopt an exact original completion; never send DATA/control writes.

        A current paired channel can observe historical completion even when its
        former sending grant is revoked. Adoption never reactivates that grant.
        """
        _uuid(operation_id), _uuid(send_operation_id)
        self._channel(endpoint, context)
        request = {"send_operation_id": send_operation_id}
        complete_id = str(uuid5(NAMESPACE_URL, "stk.peer.file.send.complete/1/" + send_operation_id))
        with self.pairing.peer_access(context) as peer, self._db(write=True) as db:
            send = self._get(db, "sends", send_operation_id)
            row = self._get(db, "transfers", send["request"]["transfer_id"])
            self._peer(row, peer)
            old = self._get(db, "operations", operation_id, optional=True)
            if old is not None:
                if old["method"] != "local.recover" or old["params"] != request:
                    _fail("conflict")
                if old["receipt"] is not None:
                    return _copy(old["receipt"])
            complete = self._get(db, "operations", complete_id)
            if (complete["method"] != "files.complete"
                    or complete["params"]["grant_id"] != send["request"]["grant_id"]
                    or any(complete["params"][k] != row[k] for k in self._target(row))):
                _fail("conflict")
            if old is None:
                self._room(db, "operations", MAX_OPERATIONS)
                self._put(db, "operations", operation_id, {"method": "local.recover", "params": request, "receipt": None})
        observed = complete["receipt"]
        if observed is None:
            observed = self.query(context, endpoint, row["transfer_id"], operation_id=complete_id)
        proven = (observed["state"] == "complete" and observed["operation"] is not None
                  and observed["operation"]["state"] == "completed")
        completed = (validate_file_result("files.complete", observed, params=complete["params"], manifest=row["manifest"])
                     if proven else None)
        result = {"operation_id": operation_id, "send_operation_id": send_operation_id,
                  "transfer_id": row["transfer_id"], "recovered": proven, "completion": completed}
        with self.pairing.peer_access(context) as peer, self._db(write=True) as db:
            current = self._get(db, "transfers", row["transfer_id"])
            self._peer(current, peer)
            if current["manifest"] != row["manifest"]:
                _fail("conflict")
            old = self._get(db, "operations", operation_id)
            if old["method"] != "local.recover" or old["params"] != request:
                _fail("conflict")
            if old["receipt"] is not None:
                return _copy(old["receipt"])
            if completed is not None:
                # Preserve current active=false and every prior intent/attempt.
                current.update(state="complete", progress=completed["files"], completion=completed["completion"])
                self._put(db, "transfers", current["transfer_id"], current)
                send["result"] = completed
                self._put(db, "sends", send_operation_id, send)
                complete["receipt"] = completed
                self._put(db, "operations", complete_id, complete)
            old["receipt"] = result
            self._put(db, "operations", operation_id, old)
        return result

    @contextmanager
    def _source(self, store, row, item, deadline):
        # Resolve and hash without holding any authorization or journal lease.
        source = store.snapshots.resolve(row["manifest"]["snapshot_id"], item["file_id"])
        if source["sha256"] != item["sha256"] or source["size"] != item["bytes"]:
            _fail("conflict")
        path = Path(source["path"])
        with Directory.open(path.parent) as parent, parent.file(path.name) as stream:
            signature, digest, size = _stamp(stream), hashlib.sha256(), 0
            while True:
                if self._monotonic() >= deadline:
                    _fail("unavailable", "File send reached its explicit deadline")
                chunk = stream.read(1024**2)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                if size > item["bytes"]:
                    _fail("conflict")
            if _stamp(stream) != signature or size != item["bytes"] or digest.hexdigest() != item["sha256"]:
                _fail("conflict", "Frozen source bytes changed")
            stream.seek(0)
            yield stream, signature, parent

    def _reconcile(self, db, row, result):
        pending = row["pending"]
        for old, current in zip(row["progress"], result["files"]):
            before, after = old["committed_bytes"], current["committed_bytes"]
            extra = (pending["length"] if pending is not None and pending["file_id"] == old["file_id"] else 0)
            if after < before or after > before + extra or after not in {before, before + extra}:
                _fail("conflict", "Receiver prefix differs from retained sending evidence")
            expected = old["next_sequence"] + int(after > before)
            if current["next_sequence"] != expected:
                _fail("conflict")
        if pending is not None:
            attempt = self._get(db, "attempts", pending["attempt_id"])
            attempt["outcome"] = "explicit_resume_observed"
            self._put(db, "attempts", pending["attempt_id"], attempt)
        row["pending"], row["progress"] = None, result["files"]

    def send(self, operation_id, context, endpoint, transfer_id, grant_id, *, resume=False, timeout=3600):
        """One explicit start/resume, DATA stream and completion; never auto-replay."""
        _uuid(operation_id), _uuid(transfer_id), _uuid(grant_id)
        if type(resume) is not bool or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
            _fail("invalid_params")
        request = {"transfer_id": transfer_id, "grant_id": grant_id, "resume": resume, "timeout": timeout}
        self._channel(endpoint, context)
        accepted = False
        try:
            _directory(self.directory, create=False)
            with Lease(self.directory / (transfer_id + ".send.lock")):
                with self.pairing.session_access(context, self.status(transfer_id)["session_id"]) as lease, self._db(write=True) as db:
                    row = self._get(db, "transfers", transfer_id)
                    store = self._authorize(row, lease)
                    send_epoch = row["session_epoch"]
                    old = self._get(db, "sends", operation_id, optional=True)
                    if old is not None:
                        if old["request"] != request:
                            _fail("conflict")
                        if old["result"] is None:
                            raise FileSendUncertain(operation_id, transfer_id)
                        return _copy(old["result"])
                    if row["state"] == "complete":
                        _fail("conflict")
                    self._room(db, "sends", MAX_OPERATIONS)
                    self._put(db, "sends", operation_id, {"request": request, "result": None})
                    params = {**self._target(row), "operation_id": operation_id, "grant_id": grant_id}
                accepted = True
                result = self._control(context, endpoint, "files.resume" if resume else "files.start", params,
                                       expected_epoch=send_epoch)
                with self.pairing.session_access(context, row["session_id"]) as lease, self._db(write=True) as db:
                    row = self._get(db, "transfers", transfer_id)
                    self._authorize(row, lease)
                    if row["session_epoch"] != send_epoch:
                        _fail("forbidden")
                    self._reconcile(db, row, result)
                    row["state"] = "sending"
                    self._put(db, "transfers", transfer_id, row)
                deadline = self._monotonic() + timeout
                for index, item in enumerate(row["manifest"]["files"]):
                    with self._source(store, row, item, deadline) as (stream, signature, parent):
                        with self._db() as db:
                            offset = self._get(db, "transfers", transfer_id)["progress"][index]["committed_bytes"]
                        stream.seek(offset)
                        while offset < item["bytes"]:
                            remaining = deadline - self._monotonic()
                            if remaining <= 0:
                                _fail("unavailable", "File send reached its explicit deadline")
                            self._channel(endpoint, context)
                            with self.pairing.session_access(context, row["session_id"]) as lease, self._db(write=True) as db:
                                row = self._get(db, "transfers", transfer_id)
                                self._authorize(row, lease)
                                if row["session_epoch"] != send_epoch:
                                    _fail("forbidden", "An earlier send cannot consume a newer approval")
                                progress = row["progress"][index]
                                if row["pending"] is not None or progress["committed_bytes"] != offset:
                                    _fail("conflict")
                                parent.check()
                                if _stamp(stream) != signature:
                                    _fail("conflict", "Frozen source bytes changed")
                                body = stream.read(min(CHUNK_BYTES, item["bytes"] - offset))
                                if len(body) != min(CHUNK_BYTES, item["bytes"] - offset) or _stamp(stream) != signature:
                                    _fail("conflict", "Frozen source bytes changed")
                                frame = decode_frame(encode_data(transfer_id, item["file_id"], progress["next_sequence"], offset, body))
                                self._room(db, "attempts", MAX_ATTEMPTS)
                                pending = {"attempt_id": str(uuid4()), "file_id": item["file_id"], "sequence": frame.sequence,
                                           "offset": offset, "length": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                                row["pending"] = pending
                                self._put(db, "attempts", pending["attempt_id"], {**pending, "transfer_id": transfer_id, "outcome": "uncertain"})
                                self._put(db, "transfers", transfer_id, row)
                            receipt = endpoint.send_file_data(frame, timeout=min(30, remaining))
                            if isinstance(receipt, bytes):
                                receipt = decode_frame(receipt)
                            validate_receipt(receipt, frame)
                            with self._db(write=True) as db:
                                row = self._get(db, "transfers", transfer_id)
                                if row["pending"] != pending:
                                    _fail("conflict")
                                row["progress"][index].update(committed_bytes=offset + len(body), next_sequence=frame.sequence + 1)
                                row["pending"] = None
                                self._put(db, "transfers", transfer_id, row)
                                attempt = self._get(db, "attempts", pending["attempt_id"])
                                attempt["outcome"] = "durable_receipt"
                                self._put(db, "attempts", pending["attempt_id"], attempt)
                            offset += len(body)
                complete_id = str(uuid5(NAMESPACE_URL, "stk.peer.file.send.complete/1/" + operation_id))
                completed = self._control(context, endpoint, "files.complete", {**self._target(row), "operation_id": complete_id, "grant_id": grant_id},
                                          expected_epoch=send_epoch)
                with self._db(write=True) as db:
                    row = self._get(db, "transfers", transfer_id)
                    row.update(state="complete", progress=completed["files"], completion=completed["completion"])
                    self._put(db, "transfers", transfer_id, row)
                    self._put(db, "sends", operation_id, {"request": request, "result": completed})
                return completed
        except Locked:
            _fail("busy", "Another explicit send is already active for this transfer")
        except Exception:
            # Do not hide exact permission/validation errors or touch an old receipt.
            if accepted:
                with self._db(write=True) as db:
                    row = self._get(db, "transfers", transfer_id, optional=True)
                    if row is not None and row["active"] and row["state"] != "complete":
                        row["state"] = "interrupted"
                        self._put(db, "transfers", transfer_id, row)
            raise


__all__ = ["FileSender", "ReceiverAdapter", "FileSendError", "FileSendUncertain"]
