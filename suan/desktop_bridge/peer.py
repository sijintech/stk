"""Desktop-only explicit peer lifecycle and durable file-job admission.

Signals exist only in transport memory and the explicit desktop response. A
reopened journal is an observation, never a queue. No private signer bytes or
connection settings enter projects, scripting or the wire protocol.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from uuid import UUID

from suan.peer.authority import PeerAuthority, PeerDenied
from suan.peer.identity import LocalDeviceIdentity, IdentityError, _directory, _ordinary
from suan.peer.pairing import PairingStore, PairingError
from suan.peer.files import FileSender, ReceiverAdapter
from suan.peer.file_store import FileStore
from suan.peer.protocol import PeerProtocolError
from suan.peer.transport import NativeTransport, TransportSignal, TransportError
from suan.peer.endpoint import PeerEndpoint
from .protocol import BridgeError


METHODS = frozenset({"info", "operations.get", "operations.list", "identity.initialize", "identity.rotate",
    "identity.revoke", "identity.recover", "pins.list", "pins.verify", "pins.revoke", "connections.open", "connections.list",
    "connections.signals", "connections.push_signal", "connections.authenticate", "connections.close",
    "sessions.list", "sessions.host", "sessions.revoke", "files.prepare", "files.list", "files.get",
    "files.offer", "files.accept", "files.send", "files.query", "files.recover", "files.cancel", "files.revoke"})
READS = frozenset({"info", "operations.get", "operations.list", "pins.list", "connections.list",
                  "connections.signals", "sessions.list", "files.list", "files.get"})
MAX_CONNECTIONS, MAX_OPERATIONS, MAX_BYTES = 8, 4096, 64 * 1024**2
_APP_ID = 0x53545042


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError
    return value


def _json(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 4 * 1024**2:
        raise ValueError
    return raw


def _page(params):
    offset, limit = params.get("offset", 0), params.get("limit", 50)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError
    return offset, limit


def _safe_error(code="unavailable"):
    return {"code": code, "message": "Peer action did not produce a confirmed result"}


def request_sha256(action, params):
    """Original typed desktop request identity; normal JSON preserves -0.0."""
    request = dict(params)
    if action == "connections.push_signal":
        request["signal_text"] = hashlib.sha256(request["signal_text"].encode()).hexdigest()
    return hashlib.sha256(_json({"action": action, "params": request}).encode()).hexdigest()


class PeerService:
    def __init__(self, state_dir, projects):
        self.root = Path(state_dir).absolute() / "peer"
        self.path = self.root / "peer-service.sqlite3"
        self.identity = LocalDeviceIdentity(self.root / "device")
        self.projects = projects
        self._authority = self._pairing = self._sender = self._receiver = None
        self._lock, self._db_lock = threading.RLock(), threading.RLock()
        self._connections, self._running = {}, set()
        self._pool, self._closed, self._identity = None, False, None

    @contextmanager
    def _db(self, *, write=False):
        # Independent private FULL journal; construction and all absent reads are passive.
        with self._db_lock:
            db = None
            try:
                try:
                    _directory(self.root, create=write)
                except FileNotFoundError:
                    if self._identity is not None:
                        raise ValueError
                    yield None
                    return
                if self._identity is not None and not self.path.exists():
                    raise ValueError
                created = False
                if write:
                    import os
                    try:
                        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        os.close(fd)
                        created = True
                    except FileExistsError:
                        pass
                try:
                    identity = _ordinary(self.path, private=True)
                except FileNotFoundError:
                    yield None
                    return
                if self._identity is not None and self._identity != identity:
                    raise ValueError
                db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                     uri=True, isolation_level=None, timeout=10)
                if write:
                    db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if created:
                    db.execute("CREATE TABLE operations (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                    db.execute(f"PRAGMA application_id={_APP_ID}")
                    db.execute("PRAGMA user_version=1")
                    db.commit()
                    db.execute("BEGIN IMMEDIATE")
                if (db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID
                        or db.execute("PRAGMA user_version").fetchone()[0] != 1
                        or _ordinary(self.path, private=True) != identity):
                    raise ValueError
                self._identity = identity
                yield db
                if (_ordinary(self.path, private=True) != identity or write and
                        db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0] > MAX_BYTES):
                    raise ValueError
                db.commit()
            finally:
                if db is not None:
                    db.close()

    @staticmethod
    def _get(db, operation_id):
        _uuid(operation_id)
        raw = None if db is None else db.execute("SELECT record FROM operations WHERE id=?", (operation_id,)).fetchone()
        if raw is None:
            return None
        if len(raw[0].encode()) > 4 * 1024**2:
            raise ValueError
        row = json.loads(raw[0])
        digest = hashlib.sha256(_json({"action": row["action"], "params": row["request"]}).encode()).hexdigest()
        if (row["operation_id"] != operation_id or row["action"] not in METHODS
                or row["request_sha256"] != digest or row["state"] not in {"running", "completed", "uncertain"}):
            raise ValueError
        return row

    @staticmethod
    def _put(db, row):
        db.execute("INSERT OR REPLACE INTO operations VALUES (?,?)", (row["operation_id"], _json(row)))

    def _public(self, row):
        if row is None:
            return None
        result = {k: row[k] for k in ("operation_id", "action", "request_sha256", "state", "connection_id",
                                     "transfer_id", "result", "error")}
        if result["state"] == "running" and row["operation_id"] not in self._running:
            result = {**result, "state": "uncertain", "error": _safe_error()}
        return json.loads(_json(result))

    def _services(self, *, create=False):
        with self._lock:
            if self._authority is None:
                current = self.identity.info()
                if current is None:
                    raise BridgeError("unavailable", "Initialize this device explicitly first")
                authority = PeerAuthority(self.identity.directory, owner_id=current["card"]["owner_id"], create=create)
                self._authority = authority
                self._pairing = PairingStore(authority.directory, self.identity, authority)
                self._sender = FileSender(self.root / "sending", self._pairing)
                self._receiver = FileStore(self.root / "receiving", self._pairing)
            return self._authority, self._pairing, self._sender, self._receiver

    @staticmethod
    def _connection_public(row):
        return {k: row[k] for k in ("connection_id", "peer_id", "state", "error")}

    def _connection(self, identity, *, ready=False):
        _uuid(identity)
        with self._lock:
            row = self._connections.get(identity)
            if row is None or ready and row["state"] != "ready":
                raise BridgeError("unavailable", "The explicitly authenticated peer connection is unavailable")
            return row

    def _current(self, identity):
        row = self._connection(identity, ready=True)
        context = row["endpoint"].authenticated_context
        if context is not row.get("context"):
            raise BridgeError("unavailable", "The approved peer connection changed")
        return context, row["endpoint"]

    def _reserve(self, action, params):
        operation_id = _uuid(params["operation_id"])
        request = dict(params)
        if action == "connections.push_signal":
            # ICE/SDP never enters the durable original-intent journal.
            request["signal_text"] = hashlib.sha256(request["signal_text"].encode()).hexdigest()
        digest = request_sha256(action, params)
        with self._db() as db:
            old = self._get(db, operation_id)
            if old is not None:
                if old["action"] != action or old["request_sha256"] != digest:
                    raise BridgeError("conflict", "Peer operation UUID belongs to another original request")
                return old, False
        binding = None
        if action in {"files.send", "connections.authenticate", "connections.open"}:
            current = self.identity.info()
            if action == "connections.open":
                pin = self._services()[1].pin(params["peer_id"])
                if not pin["active"]:
                    raise PeerDenied("Peer pin is revoked")
                connection = {"pin": pin["card"], "connection_id": operation_id}
            else:
                connection = self._connection(params["connection_id"], ready=action == "files.send")
            binding = {"local_card": current["card"], "identity_generation": current["generation"],
                       "remote_card": connection["pin"], "connection_id": connection["connection_id"]}
            if action == "files.send":
                context, _ = self._current(params["connection_id"])
                with self._services()[1].peer_access(context) as lease:
                    binding.update(registry_id=lease.registry_id, peer_epoch=lease.peer_epoch)
        with self._db(write=True) as db:
            old = self._get(db, operation_id)
            if old is not None:
                if old["action"] != action or old["request_sha256"] != digest:
                    raise BridgeError("conflict", "Peer operation UUID belongs to another original request")
                return old, False
            if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
                raise BridgeError("busy", "Peer operation journal capacity is exhausted")
            row = {"operation_id": operation_id, "action": action, "request_sha256": digest,
                   "state": "running", "connection_id": operation_id if action == "connections.open" else params.get("connection_id"),
                   "transfer_id": params.get("transfer_id"), "result": None, "error": None, "request": request,
                   "binding": binding}
            self._put(db, row)
            return row, True

    def _finish(self, row, result=None, error=None):
        with self._db(write=True) as db:
            current = self._get(db, row["operation_id"])
            if current["state"] == "completed":
                return
            current.update(state="completed" if error is None else "uncertain", result=result, error=error)
            if result is not None and "transfer_id" in result:
                current["transfer_id"] = result["transfer_id"]
            self._put(db, current)

    def call(self, action, params):
        try:
            if action not in METHODS:
                raise ValueError
            with self._lock:
                if self._closed:
                    raise BridgeError("shutting_down", "Peer service is closed")
            if action in READS:
                return self._read(action, params)
            asynchronous = action in {"connections.authenticate", "files.send"}
            with self._lock:
                # Deduplicate before the bounded executor's admission decision.
                with self._db() as db:
                    previous = self._get(db, params["operation_id"])
                if asynchronous and previous is None and len(self._running) >= 2:
                    raise BridgeError("busy", "Two explicit peer actions are already active")
                row, fresh = self._reserve(action, params)
                if not fresh:
                    return {"operation": self._public(row)}
                self._running.add(row["operation_id"])
                if asynchronous:
                    admission = {"accepted": False}
                    try:
                        if self._pool is None:
                            self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stk-peer-owner")
                        self._pool.submit(self._dispatch, admission, row, action, dict(params))
                    except Exception:
                        # submit can queue the callable before worker startup
                        # fails. The dispatcher cannot pass this lock until its
                        # admission is confirmed, so a rejected item stays inert.
                        admission["accepted"] = False
                        try:
                            self._finish(row, error=_safe_error())
                        except Exception:
                            pass
                        finally:
                            self._running.discard(row["operation_id"])
                        row.update(state="uncertain", result=None, error=_safe_error())
                        return {"operation": self._public(row)}
                    admission["accepted"] = True
                    return {"operation": self._public(row)}
            self._execute(row, action, params)
            with self._db() as db:
                return {"operation": self._public(self._get(db, row["operation_id"]))}
        except BridgeError:
            raise
        except (IdentityError, PairingError, PeerDenied):
            raise BridgeError("unavailable", "Current peer identity or approval is unavailable", retryable=False) from None
        except PeerProtocolError as exc:
            code = exc.code if exc.code in {"conflict", "invalid_params", "not_found", "busy", "unavailable", "unsupported"} else "unavailable"
            raise BridgeError(code, "Peer operation could not be completed", retryable=False) from None
        except (OSError, sqlite3.Error, TransportError):
            raise BridgeError("unavailable", "Private peer state or transport is unavailable", retryable=False) from None
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise BridgeError("invalid_params", "Invalid peer request", retryable=False) from None

    def _dispatch(self, admission, row, action, params):
        with self._lock:
            if not admission["accepted"]:
                return
        # This lock never spans identity/session acceptance, files or network.
        self._execute(row, action, params)

    def _execute(self, row, action, params):
        try:
            if row["binding"] is not None:
                current = self.identity.info()
                binding = row["binding"]
                if (not current["active"] or current["generation"] != binding["identity_generation"]
                        or current["card"] != binding["local_card"]):
                    raise ValueError
            result = self._mutate(action, params, binding=row["binding"])
            self._finish(row, result=result)
        except Exception:
            # No raw domain exception, signaling, filesystem path or key in logs.
            try:
                self._finish(row, error=_safe_error())
            except Exception:
                pass  # The pre-effect intent remains uncertain on journal failure.
        finally:
            with self._lock:
                self._running.discard(row["operation_id"])

    def _read(self, action, params):
        if action in {"info", "connections.list"}:
            with self._lock:
                connections = [self._connection_public(r) for r in self._connections.values()]
            return {"connections": connections, **({"identity": self.identity.info()} if action == "info" else {})}
        if action.startswith("operations."):
            with self._db() as db:
                if action == "operations.get":
                    return {"operation": self._public(self._get(db, params["operation_id"]))}
                offset, limit = _page(params)
                rows = [] if db is None else db.execute("SELECT id FROM operations ORDER BY id LIMIT ? OFFSET ?", (limit, offset))
                results, size = [], 0
                for r in rows:
                    public = self._public(self._get(db, r[0]))
                    size += len(_json(public).encode())
                    if size > 4 * 1024**2:
                        raise BridgeError("invalid_params", "Reduce the peer operation page limit")
                    results.append(public)
                return {"operations": results}
        if action == "connections.signals":
            row = self._connection(params["connection_id"])
            try:
                signal = row["transport"].next_signal(timeout=.05)
            except TimeoutError:
                return {"signal_text": None}
            return {"signal_text": _json({"kind": signal.kind, "payload": signal.payload})}
        if self.identity.info() is None:
            if action in {"pins.list", "sessions.list", "files.list"}:
                return {"pins": []} if action == "pins.list" else {"sessions": []} if action == "sessions.list" else {"transfers": []}
        _, pairing, sender, receiver = self._services()
        offset, limit = _page(params)
        if action == "pins.list":
            return {"pins": pairing.pins(offset=offset, limit=limit)}
        if action == "sessions.list":
            return {"sessions": pairing.sessions(offset=offset, limit=limit)}
        role = params["role"]
        service = sender if role == "sender" else receiver
        if action == "files.list":
            return {"transfers": service.list(offset=offset, limit=limit)}
        transfer_id = params["transfer_id"]
        return {"transfer": service.status(transfer_id) if role == "sender" else service.get(transfer_id),
                "manifest": service.transfer_manifest(transfer_id) if role == "sender" else service.manifest(transfer_id),
                "offer": None if role == "sender" else service.reviewed_offer(transfer_id)}

    def _mutate(self, action, p, *, binding=None):
        op = p["operation_id"]
        if action == "identity.recover":
            return self._recover_identity(p)
        if action.startswith("identity."):
            method = action.split(".")[1]
            result = getattr(self.identity, method)(op, p["display_name"] if method == "initialize" else p["expected_generation"])
            if method == "initialize":
                self._services(create=True)
            else:
                self._close_connections(older_generation=result["result"]["generation"])
            return result
        authority, pairing, sender, receiver = self._services()
        if action == "pins.verify":
            return pairing.verify_pin(op, p["card"], p["expected_peer_id"])
        if action == "pins.revoke":
            result = pairing.revoke_pin(op, p["peer_id"])
            self._close_connections(peer_id=p["peer_id"])
            return result
        if action == "connections.open":
            from suan.peer.helper_installation import load_helper_installation
            installation = load_helper_installation(Path(p["helper_prefix"]))
            with self._lock:
                current, pin = self.identity.info(), pairing.pin(p["peer_id"])
                if (self._closed or len(self._connections) >= MAX_CONNECTIONS or not pin["active"]
                        or not current["active"] or current["generation"] != binding["identity_generation"]
                        or current["card"] != binding["local_card"] or pin["card"] != binding["remote_card"]):
                    raise ValueError
                transport = NativeTransport(installation.executable, offerer=p["offerer"], route=p["route"])
                connection = {"connection_id": op, "peer_id": p["peer_id"], "state": "signaling", "error": None,
                              "transport": transport, "pin": pin["card"], "endpoint": None,
                              "identity_generation": current["generation"]}
                self._connections[op] = connection
                # Serialize only the short local process/IPC startup with close.
                # Authentication/network waits are exclusively outside this lock.
                try:
                    transport.start()
                except Exception:
                    connection.update(state="failed", error=_safe_error())
                    transport.close()
                    raise
            return self._connection_public(connection)
        if action == "connections.push_signal":
            signal = json.loads(p["signal_text"])
            if type(signal) is not dict or set(signal) != {"kind", "payload"}:
                raise ValueError
            self._connection(p["connection_id"])["transport"].accept_signal(TransportSignal(signal["kind"], signal["payload"]))
            return {"applied": True}
        if action == "connections.authenticate":
            row = self._connection(p["connection_id"])
            with self._lock:
                if row["state"] != "signaling":
                    raise ValueError
                row["state"] = "authenticating"
                own = self.identity.info()["card"]
                endpoint = PeerEndpoint(row["transport"], authority, public_key=bytes.fromhex(own["public_key"]),
                    sign=self.identity.signer(row["pin"]["owner_id"]), remote_peer_id=row["peer_id"],
                    remote_owner_id=row["pin"]["owner_id"], file_adapter=ReceiverAdapter(receiver))
                row["endpoint"] = endpoint
            try:
                endpoint.start(timeout=30)
                context = endpoint.authenticated_context
                with pairing.peer_access(context):
                    pass
                with self._lock:
                    if self._closed or row["state"] != "authenticating":
                        raise ValueError
                    row.update(state="ready", context=context)
            except Exception:
                endpoint.close()
                with self._lock:
                    row.update(state="failed", error=_safe_error())
                raise
            return self._connection_public(row)
        if action == "connections.close":
            row = self._connection(p["connection_id"])
            self._close_connections(connection_id=p["connection_id"])
            return self._connection_public(row)
        if action == "sessions.revoke":
            return pairing.revoke_session(op, p["session_id"])
        if action == "files.prepare":
            with self.projects._operation():
                store = self.projects._get(p["handle"])
                if store.info()["revision"] != p["expected_revision"]:
                    raise ValueError
                plan = sender.prepare(op, store, p["snapshot_id"], p["record_ids"],
                                      names=p.get("names"), media_types=p.get("media_types"))
                if store.info()["revision"] != p["expected_revision"]:
                    raise ValueError
                binding = authority.bind_project(store.directory)
                return {**plan, "database_generation": binding["database_generation"]}
        if action == "files.revoke":
            return (sender if p["role"] == "sender" else receiver).revoke(op, p["transfer_id"])
        context, endpoint = self._current(p["connection_id"])
        if action == "sessions.host":
            peer_id = self._connection(p["connection_id"], ready=True)["peer_id"]
            return pairing.host_session(op, peer_id, p["lifetime"], context=context, session_id=p["session_id"])
        if action == "files.offer":
            return sender.offer(op, context, endpoint, p["plan_id"], p["database_generation"], p["session_id"], transfer_id=p["transfer_id"])
        if action == "files.accept":
            target = Path(p["target"])
            if not target.is_absolute():
                raise ValueError
            return receiver.accept(op, context, p["transfer_id"], p["offer_operation_id"], target)
        if action == "files.send":
            return sender.send(op, context, endpoint, p["transfer_id"], p["grant_id"], resume=p["resume"], timeout=p["timeout"])
        if action == "files.query":
            return sender.query(context, endpoint, p["transfer_id"], operation_id=p["original_operation_id"])
        if action == "files.recover":
            return sender.recover(op, context, endpoint, p["send_operation_id"])
        if action == "files.cancel":
            return sender.cancel(op, context, endpoint, p["transfer_id"], grant_id=p["grant_id"])
        raise ValueError

    def _recover_identity(self, p):
        original_id = _uuid(p["original_operation_id"])
        with self._db() as db:
            original = self._get(db, original_id)
            if original is None or original["action"] not in {"identity.initialize", "identity.rotate", "identity.revoke"}:
                raise ValueError
            kind = original["action"].split(".")[1]
            expected = {"kind": kind}
            field = "display_name" if kind == "initialize" else "expected_generation"
            expected[field] = original["request"][field]
            expected_hash = hashlib.sha256(_json(expected).encode()).hexdigest()
            receipt = self.identity.operation(original_id)
            current = self.identity.info()
            if (receipt is None or receipt["kind"] != kind or receipt["request_sha256"] != expected_hash
                    or receipt["result"] != current):
                raise ValueError
            if kind == "initialize" and not (self.identity.directory / "peer-authority.sqlite3").exists():
                # Only the original bootstrap may create missing metadata. Once
                # any peer action might have used an Authority, loss is not reset.
                for (raw,) in db.execute("SELECT record FROM operations"):
                    if json.loads(raw)["action"] not in {"identity.initialize", "identity.recover"}:
                        raise ValueError
                if self._authority is not None:
                    raise ValueError  # A registry known to this process was lost.
        if kind == "initialize":
            if (self.identity.directory / "peer-authority.sqlite3").exists():
                # Validate actual current registry even if an old object is cached.
                PeerAuthority(self.identity.directory, owner_id=current["card"]["owner_id"], create=False)
            else:
                self._services(create=True)
        if self.identity.info() != current:
            raise ValueError
        if kind != "initialize":
            self._close_connections(older_generation=current["generation"])
        with self._db(write=True) as db:
            latest = self._get(db, original_id)
            if (latest["request_sha256"] != original["request_sha256"] or self.identity.info() != current):
                raise ValueError
            if latest["state"] != "completed":
                latest.update(state="completed", result=receipt, error=None)
                self._put(db, latest)
        return {"original_operation_id": original_id, "identity": current, "recovered": True}

    def _close_connections(self, *, connection_id=None, peer_id=None, older_generation=None):
        with self._lock:
            rows = [r for r in self._connections.values() if (connection_id is None or r["connection_id"] == connection_id)
                    and (peer_id is None or r["peer_id"] == peer_id)
                    and (older_generation is None or r["identity_generation"] < older_generation)]
            for row in rows:
                row["state"] = "closed"
        for row in rows:
            if row["endpoint"] is not None:
                row["endpoint"].close()
            else:
                row["transport"].close()

    def shutdown(self):
        with self._lock:
            self._closed = True
        self._close_connections()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
