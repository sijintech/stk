"""Explicit full-pin verification and two-party host-approved sharing sessions.

Pairing metadata and original-operation receipts use additive pairing_ tables in
the Authority database, so pin/revoke and authenticated peer epochs commit in one
FULL transaction. Reads are read-only and never create tables. A session is not a
project/file/training grant; accepted file chunks require a separate adapter lease.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .authority import MAX_PEERS, PeerDenied, _file_identity, _registry_header
from .identity import IdentityError, _json, _uuid, validate_card


SESSION_FORMAT = "stk.peer-sharing-session/1"
MAX_LIFETIME = 3600
MAX_PINS = 1024
MAX_SESSIONS = 4096
MAX_OPERATIONS = 8192


class PairingError(PeerDenied):
    """Fixed local diagnostic; no credential, path or rejected body is included."""


@dataclass(frozen=True)
class PairedPeerLease:
    owner_id: str
    local_peer_id: str
    remote_owner_id: str
    remote_peer_id: str
    registry_id: str
    peer_epoch: int
    identity_generation: int
    pin_epoch: int


@dataclass(frozen=True)
class SessionLease:
    session_id: str
    session_epoch: int
    owner_id: str
    local_peer_id: str
    remote_owner_id: str
    remote_peer_id: str
    host_owner_id: str
    host_peer_id: str
    recipient_owner_id: str
    recipient_peer_id: str
    registry_id: str
    peer_epoch: int
    identity_generation: int
    expires_at: float
    role: str


def validate_offer(value):
    if (type(value) is not dict or set(value) != {"format", "session_id", "session_epoch", "host", "recipient", "expires_at"}
            or value["format"] != SESSION_FORMAT or type(value["session_epoch"]) is not int
            or not 1 <= value["session_epoch"] <= 2**53 - 1
            or type(value["expires_at"]) not in (int, float) or not math.isfinite(value["expires_at"])):
        raise PairingError("Sharing session offer is invalid")
    try:
        _uuid(value["session_id"])
        host, recipient = validate_card(value["host"]), validate_card(value["recipient"])
        if host["peer_id"] == recipient["peer_id"]:
            raise IdentityError("A sharing session requires two different devices")
        return json.loads(_json({**value, "host": host, "recipient": recipient}))
    except IdentityError:
        raise PairingError("Sharing session offer is invalid") from None


class PairingStore:
    """Local owner API, never a remotely callable approval registry.

    Lock order is Authority -> pairing metadata -> file adapter. Session bindings
    retain the exact process-local context object; a stored approved row by itself
    grants nothing after reconnect/reopen. Host reapproval produces a newer offer.
    """

    def __init__(self, directory, identity, authority, *, clock=time.time, monotonic=time.monotonic):
        self.directory = Path(directory).absolute()
        if self.directory != authority.directory:
            raise PairingError("Pairing state must use its local Authority directory")
        self.identity, self.authority = identity, authority
        self._clock, self._monotonic = clock, monotonic
        self._bindings = {}

    def __repr__(self):
        return "<PairingStore>"

    @staticmethod
    def _tables(db, *, create=False):
        if create:
            db.execute("CREATE TABLE IF NOT EXISTS pairing_pins (peer_id TEXT PRIMARY KEY, card TEXT NOT NULL, "
                       "epoch INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)))")
            db.execute("CREATE TABLE IF NOT EXISTS pairing_sessions (id TEXT PRIMARY KEY, offer TEXT NOT NULL, "
                       "role TEXT NOT NULL, identity_generation INTEGER NOT NULL, pin_epoch INTEGER NOT NULL, "
                       "active INTEGER NOT NULL CHECK(active IN (0,1)))")
            db.execute("CREATE TABLE IF NOT EXISTS pairing_operations (id TEXT PRIMARY KEY, request TEXT NOT NULL, receipt TEXT NOT NULL)")
            return True
        return db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN "
                          "('pairing_pins','pairing_sessions','pairing_operations')").fetchone()[0] == 3

    @contextmanager
    def _read(self):
        db = None
        handling_body = False
        with self.authority._lock:
            try:
                identity = _file_identity(self.authority.path)
                if identity != self.authority._identity:
                    raise PairingError("Pairing authority was replaced")
                _registry_header(self.authority.path, identity)
                db = sqlite3.connect(self.authority.path.as_uri() + "?mode=ro", uri=True,
                                     isolation_level=None, timeout=10)
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")
                self.authority._validate(db)
                handling_body = True
                yield db if self._tables(db) else None
                handling_body = False
                if _file_identity(self.authority.path) != identity:
                    raise PairingError("Pairing authority changed")
            except (sqlite3.Error, OSError):
                if handling_body:
                    raise
                raise PairingError("Pairing storage is unavailable") from None
            finally:
                if db is not None:
                    db.close()

    def _local(self):
        current = self.identity.info()
        if (current is None or not current["active"]
                or current["card"]["owner_id"] != self.authority.owner_id):
            raise PairingError("Current local device identity is unavailable")
        return current

    @staticmethod
    def _decode(raw):
        if type(raw) is not str or len(raw.encode("utf-8")) > 16384:
            raise PairingError("Pairing metadata is invalid")
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            raise PairingError("Pairing metadata is invalid") from None

    @classmethod
    def _pin(cls, db, peer_id, *, active=True):
        if db is None:
            raise PairingError("Peer public pin is unavailable")
        row = db.execute("SELECT card,epoch,active FROM pairing_pins WHERE peer_id=?", (peer_id,)).fetchone()
        if row is None or (active and not row["active"]):
            raise PairingError("Peer public pin is unavailable")
        try:
            card = validate_card(cls._decode(row["card"]))
            if card["peer_id"] != peer_id or type(row["epoch"]) is not int or row["epoch"] < 1:
                raise IdentityError("Invalid pin")
        except IdentityError:
            raise PairingError("Peer public pin is invalid") from None
        return {"card": card, "epoch": row["epoch"], "active": bool(row["active"])}

    def pin(self, peer_id):
        with self._read() as db:
            return self._pin(db, peer_id, active=False)

    @staticmethod
    def _page(offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise PairingError("Pairing page is invalid")

    def pins(self, *, offset=0, limit=100):
        self._page(offset, limit)
        with self._read() as db:
            if db is None:
                return []
            return [self._pin(db, row[0], active=False) for row in db.execute(
                "SELECT peer_id FROM pairing_pins ORDER BY peer_id LIMIT ? OFFSET ?", (limit, offset))]

    @classmethod
    def _old(cls, db, operation_id, request=None):
        row = db.execute("SELECT request,receipt FROM pairing_operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        if request is not None and row["request"] != request:
            raise PairingError("Pairing operation UUID belongs to another request")
        receipt = cls._decode(row["receipt"])
        try:
            if (receipt["operation_id"] != operation_id or receipt["request_sha256"] !=
                    hashlib.sha256(row["request"].encode("utf-8")).hexdigest()):
                raise ValueError
            return receipt
        except (ValueError, TypeError, KeyError):
            raise PairingError("Pairing operation receipt is invalid") from None

    def operation(self, operation_id):
        _uuid(operation_id)
        with self._read() as db:
            return None if db is None else self._old(db, operation_id)

    def _change(self, operation_id, request, action):
        _uuid(operation_id)
        encoded = _json(request)
        with self.authority._transaction() as db:
            self._tables(db, create=True)
            old = self._old(db, operation_id, encoded)
            if old is not None:
                return old
            if db.execute("SELECT count(*) FROM pairing_operations").fetchone()[0] >= MAX_OPERATIONS:
                raise PairingError("Pairing operation capacity is exhausted")
            current = self._local()
            result = action(db, current)
            receipt = {"format": "stk.peer-pairing-operation/1", "operation_id": operation_id,
                       "kind": request["kind"], "request_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                       "result": result}
            db.execute("INSERT INTO pairing_operations VALUES (?,?,?)", (operation_id, encoded, _json(receipt)))
            return receipt

    def verify_pin(self, operation_id, card, expected_peer_id):
        """Owner explicitly attests separate full-fingerprint verification; never TOFU."""
        card = validate_card(card)
        if expected_peer_id != card["peer_id"]:
            raise PairingError("Verified fingerprint does not match the public card")
        request = {"kind": "verify_pin", "card": card, "expected_peer_id": expected_peer_id}

        def apply(db, current):
            if card["peer_id"] == current["card"]["peer_id"]:
                raise PairingError("A device cannot pair with itself")
            row = db.execute("SELECT card,epoch,active FROM pairing_pins WHERE peer_id=?", (card["peer_id"],)).fetchone()
            if row is not None:
                previous = self._pin(db, card["peer_id"], active=False)
                # Display text may change only with the same full cryptographic owner binding.
                if any(previous["card"][key] != card[key] for key in ("owner_id", "peer_id", "public_key")):
                    raise PairingError("Peer owner or public identity changed")
                epoch = previous["epoch"] + (not previous["active"])
            else:
                if db.execute("SELECT count(*) FROM pairing_pins").fetchone()[0] >= MAX_PINS:
                    raise PairingError("Peer pin capacity is exhausted")
                epoch = 1
            public = bytes.fromhex(card["public_key"])
            peer = db.execute("SELECT public_key,active FROM peers WHERE peer_id=?", (card["peer_id"],)).fetchone()
            if peer is None:
                if db.execute("SELECT count(*) FROM peers").fetchone()[0] >= MAX_PEERS:
                    raise PairingError("Peer authority capacity is exhausted")
                db.execute("INSERT INTO peers VALUES (?,?,1,1)", (card["peer_id"], public))
            elif peer["public_key"] != public:
                raise PairingError("Peer public identity changed")
            elif not peer["active"]:
                db.execute("UPDATE peers SET active=1,epoch=epoch+1 WHERE peer_id=?", (card["peer_id"],))
            db.execute("INSERT OR REPLACE INTO pairing_pins VALUES (?,?,?,1)", (card["peer_id"], _json(card), epoch))
            return {"card": card, "epoch": int(epoch), "active": True}
        return self._change(operation_id, request, apply)

    def revoke_pin(self, operation_id, peer_id):
        def apply(db, current):
            pin = self._pin(db, peer_id, active=False)
            db.execute("UPDATE pairing_pins SET active=0,epoch=epoch+1 WHERE peer_id=?", (peer_id,))
            db.execute("UPDATE peers SET active=0,epoch=epoch+1 WHERE peer_id=?", (peer_id,))
            db.execute("UPDATE grants SET active=0 WHERE peer_id=?", (peer_id,))
            return {"peer_id": peer_id, "epoch": pin["epoch"] + 1, "active": False}
        return self._change(operation_id, {"kind": "revoke_pin", "peer_id": peer_id}, apply)

    def _time(self):
        wall, mono = self._clock(), self._monotonic()
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (wall, mono)):
            raise PairingError("Sharing session clock is unavailable")
        return wall, mono

    @staticmethod
    def _lifetime(value):
        if type(value) is not int or not 1 <= value <= MAX_LIFETIME:
            raise PairingError("Sharing session lifetime must be 1 to 3600 seconds")

    @classmethod
    def _session(cls, db, session_id):
        if db is None:
            raise PairingError("Sharing session is unavailable")
        row = db.execute("SELECT * FROM pairing_sessions WHERE id=?", (_uuid(session_id),)).fetchone()
        if row is None:
            raise PairingError("Sharing session is unavailable")
        offer = validate_offer(cls._decode(row["offer"]))
        if offer["session_id"] != session_id or row["role"] not in ("host", "recipient"):
            raise PairingError("Sharing session metadata is invalid")
        return {"offer": offer, "role": row["role"], "identity_generation": row["identity_generation"],
                "pin_epoch": row["pin_epoch"], "active": bool(row["active"])}

    def session(self, session_id):
        with self._read() as db:
            result = self._session(db, session_id)
            # Approval history is never reported as a usable live context credential.
            return {**result, "context_bound": False}

    def sessions(self, *, offset=0, limit=100):
        self._page(offset, limit)
        with self._read() as db:
            if db is None:
                return []
            return [{**self._session(db, row[0]), "context_bound": False} for row in db.execute(
                "SELECT id FROM pairing_sessions ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]

    def _bound_change(self, operation_id, request, context, action):
        """Runtime bindings are installed only after a newly committed explicit approval."""
        binding = []
        def apply(db, current):
            peer_id = self.authority._peer(db, context)
            peer_epoch = db.execute("SELECT epoch FROM peers WHERE peer_id=?", (peer_id,)).fetchone()[0]
            result, pin_epoch = action(db, current, peer_id)
            offer = result["offer"]
            wall, mono = self._time()
            binding.append((offer["session_id"], (context, offer["session_epoch"], current["generation"],
                                                 pin_epoch, peer_epoch, mono + offer["expires_at"] - wall)))
            return result
        with self.authority._lock:
            receipt = self._change(operation_id, request, apply)
            if binding:
                self._bindings[binding[0][0]] = binding[0][1]
            return receipt

    def host_session(self, operation_id, recipient_peer_id, lifetime, *, context, session_id=None):
        """Explicit Host approval on this context; reapproval keeps ID and increases epoch."""
        self._lifetime(lifetime)
        if session_id is not None:
            _uuid(session_id)
        request = {"kind": "host_session", "recipient_peer_id": recipient_peer_id,
                   "lifetime": lifetime, "session_id": session_id}
        def apply(db, current, peer_id):
            if peer_id != recipient_peer_id:
                raise PairingError("Host approval recipient is not the authenticated peer")
            pin = self._pin(db, peer_id)
            epoch, sid = 1, session_id or str(uuid4())
            if session_id is not None:
                previous = self._session(db, sid)
                if (not previous["active"] or previous["role"] != "host"
                        or previous["offer"]["host"] != current["card"]
                        or previous["offer"]["recipient"] != pin["card"]):
                    raise PairingError("Sharing session cannot be rebound to different pins")
                epoch = previous["offer"]["session_epoch"] + 1
            elif db.execute("SELECT count(*) FROM pairing_sessions").fetchone()[0] >= MAX_SESSIONS:
                raise PairingError("Sharing session capacity is exhausted")
            wall, _ = self._time()
            offer = validate_offer({"format": SESSION_FORMAT, "session_id": sid, "session_epoch": epoch,
                                    "host": current["card"], "recipient": pin["card"], "expires_at": wall + lifetime})
            db.execute("INSERT OR REPLACE INTO pairing_sessions VALUES (?,?,?,?,?,1)",
                       (sid, _json(offer), "host", current["generation"], pin["epoch"]))
            return {"offer": offer, "role": "host"}, pin["epoch"]
        return self._bound_change(operation_id, request, context, apply)

    def accept_session(self, operation_id, context, offer):
        """Recipient's explicit acceptance, from the authenticated full pinned Host."""
        offer = validate_offer(offer)
        request = {"kind": "accept_session", "offer": offer}
        def apply(db, current, peer_id):
            pin = self._pin(db, peer_id)
            wall, _ = self._time()
            if (offer["host"] != pin["card"] or offer["recipient"] != current["card"]
                    or not wall < offer["expires_at"] <= wall + MAX_LIFETIME):
                raise PairingError("Sharing offer does not match the current Host, recipient or expiry")
            row = db.execute("SELECT id FROM pairing_sessions WHERE id=?", (offer["session_id"],)).fetchone()
            if row is not None:
                previous = self._session(db, offer["session_id"])
                if (not previous["active"] or previous["role"] != "recipient"
                        or previous["offer"]["host"] != offer["host"]
                        or previous["offer"]["recipient"] != offer["recipient"]
                        or offer["session_epoch"] <= previous["offer"]["session_epoch"]):
                    raise PairingError("Sharing offer must be a new Host approval epoch")
            elif db.execute("SELECT count(*) FROM pairing_sessions").fetchone()[0] >= MAX_SESSIONS:
                raise PairingError("Sharing session capacity is exhausted")
            db.execute("INSERT OR REPLACE INTO pairing_sessions VALUES (?,?,?,?,?,1)",
                       (offer["session_id"], _json(offer), "recipient", current["generation"], pin["epoch"]))
            return {"offer": offer, "role": "recipient"}, pin["epoch"]
        return self._bound_change(operation_id, request, context, apply)

    def revoke_session(self, operation_id, session_id):
        _uuid(session_id)
        def apply(db, current):
            previous = self._session(db, session_id)
            db.execute("UPDATE pairing_sessions SET active=0 WHERE id=?", (session_id,))
            return {"session_id": session_id, "session_epoch": previous["offer"]["session_epoch"], "active": False}
        return self._change(operation_id, {"kind": "revoke_session", "session_id": session_id}, apply)

    @contextmanager
    def peer_access(self, context):
        """Verified full-pin metadata only; no session and no business authorization."""
        with self.authority.peer_access(context) as peer:
            with self.identity.current_identity() as current:
                if current["card"]["owner_id"] != peer.owner_id:
                    raise PairingError("Local device owner does not match the Authority")
                with self._read() as db:
                    pin = self._pin(db, peer.peer_id)
                    yield PairedPeerLease(peer.owner_id, current["card"]["peer_id"], pin["card"]["owner_id"],
                                          peer.peer_id, peer.registry_id, peer.peer_epoch, current["generation"], pin["epoch"])

    @contextmanager
    def session_access(self, context, session_id):
        """Current exact-context approval lease. Never connects, approves or renews."""
        with self.peer_access(context) as peer:
            with self._read() as db:
                saved = self._session(db, session_id)
                offer, binding = saved["offer"], self._bindings.get(session_id)
                wall, mono = self._time()
                local = offer["host"] if saved["role"] == "host" else offer["recipient"]
                remote = offer["recipient"] if saved["role"] == "host" else offer["host"]
                if (not saved["active"] or binding is None or binding[0] is not context
                        or binding[1:5] != (offer["session_epoch"], peer.identity_generation, peer.pin_epoch, peer.peer_epoch)
                        or saved["identity_generation"] != peer.identity_generation or saved["pin_epoch"] != peer.pin_epoch
                        or not wall < offer["expires_at"] or not mono < binding[5]
                        or (local["owner_id"], local["peer_id"]) != (peer.owner_id, peer.local_peer_id)
                        or (remote["owner_id"], remote["peer_id"]) != (peer.remote_owner_id, peer.remote_peer_id)):
                    raise PairingError("Sharing session needs current explicit approval")
                yield SessionLease(session_id, offer["session_epoch"], peer.owner_id, peer.local_peer_id,
                                   peer.remote_owner_id, peer.remote_peer_id, offer["host"]["owner_id"], offer["host"]["peer_id"],
                                   offer["recipient"]["owner_id"], offer["recipient"]["peer_id"], peer.registry_id,
                                   peer.peer_epoch, peer.identity_generation, offer["expires_at"], saved["role"])


__all__ = ["PairingStore", "PairingError", "PairedPeerLease", "SessionLease", "SESSION_FORMAT", "MAX_LIFETIME", "validate_offer"]
