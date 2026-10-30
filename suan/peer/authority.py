"""Owner-approved peer identities and project grants.

Only public keys and local authorization metadata are persisted here. Private
signing keys remain with their owner. Network adapters must obtain channel_binding
from their actual authenticated transport, never from a peer's asserted JSON.
Owner control methods are deliberately absent from the public peer protocol.

Explicit database restore/replacement MUST use rebind_project. File replacement
and observed revision rollback are rejected automatically, but an unobserved
out-of-band in-place restore cannot be proven safe from a SQLite snapshot alone.
This module does not promise exactly-once execution after authoritative state loss.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
from uuid import UUID, uuid4

from suan.project import ProjectStore


_APP_ID = 0x53545041
_FORMAT = 1
_HEX = re.compile(r"[0-9a-f]{64}")
_CAPABILITIES = frozenset({"project.read", "project.edit"})
_AUTH_FIELDS = frozenset({"format", "owner_id", "peer_id", "challenge_id", "nonce",
                          "channel_binding", "expires_in"})
CHALLENGE_SECONDS = 60
SESSION_SECONDS = 600
MAX_PEERS = 1024
MAX_PROJECTS = 1024
MAX_GRANTS = 8192
MAX_CHALLENGES = 1024
MAX_SESSIONS = 1024


class PeerDenied(PermissionError):
    """Missing, revoked, expired or inconsistent authority; safe to report generically."""


class PeerOutcomeUncertain(RuntimeError):
    """An accepted project edit may have committed before authority cleanup failed."""


class PeerContext:
    """Opaque process-local handle, issued only after signature verification."""
    __slots__ = ()

    def __repr__(self):
        return "<PeerContext>"


@dataclass(frozen=True)
class ProjectLease:
    store: ProjectStore
    project_id: str
    operation_scope: str


def _uuid(value):
    if type(value) is not str:
        raise PeerDenied("Invalid peer authority identity")
    try:
        valid = str(UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise PeerDenied("Invalid peer authority identity")
    return value


def _hex(value):
    if type(value) is not str or not _HEX.fullmatch(value):
        raise PeerDenied("Invalid peer authority identity")
    return value


def peer_id_for(public_key):
    """Domain-separated fingerprint of a raw Ed25519 PUBLIC key (never a secret)."""
    if type(public_key) is not bytes or len(public_key) != 32:
        raise PeerDenied("An Ed25519 public key must contain exactly 32 bytes")
    return hashlib.sha256(b"stk.peer.identity/1\0" + public_key).hexdigest()


def auth_message(challenge):
    """Exact bytes the paired device signs; no caller-selected identity or binding."""
    if type(challenge) is not dict or set(challenge) != _AUTH_FIELDS:
        raise PeerDenied("Invalid peer authentication challenge")
    if (challenge["format"] != "stk.peer-auth/1" or type(challenge["expires_in"]) is not int
            or challenge["expires_in"] != CHALLENGE_SECONDS):
        raise PeerDenied("Invalid peer authentication challenge")
    _uuid(challenge["owner_id"])
    _uuid(challenge["challenge_id"])
    for key in ("peer_id", "nonce", "channel_binding"):
        _hex(challenge[key])
    return b"STK-PEER-AUTH/1\0" + json.dumps(challenge, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _file_identity(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise PeerDenied("Peer authority requires an ordinary database file")
    return str(info.st_dev), str(info.st_ino)


def _registry_header(path, identity):
    """Reject foreign/unfinished files before SQLite can recover anything writable."""
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or (str(before.st_dev), str(before.st_ino)) != identity):
            raise PeerDenied("Peer authority database was replaced")
        header = os.read(fd, 100)
        after = os.fstat(fd)
        stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if (stamp(before) != stamp(after) or _file_identity(path) != identity
                or len(header) != 100 or header[:16] != b"SQLite format 3\0"
                or int.from_bytes(header[68:72], "big") != _APP_ID):
            raise PeerDenied("Unsupported peer authority database")
    finally:
        os.close(fd)


class PeerAuthority:
    """Persistent owner control and per-operation authorization leases.

    A registry transaction is held for the ENTIRE project operation. Owner revoke
    and rebind operations serialize with accepted calls, including across registry
    instances/processes. Already accepted edits finish before a waiting revocation;
    every subsequent access revalidates the grant and database generation.
    """
    def __init__(self, directory, *, owner_id, clock=time.monotonic):
        self.owner_id = _uuid(owner_id)
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "peer-authority.sqlite3"
        self._lock = threading.RLock()
        self._clock = clock
        self._challenges = {}
        self._contexts = {}
        created = False
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            created = True
        except FileExistsError:
            pass
        self._identity = _file_identity(self.path)
        if not created:
            _registry_header(self.path, self._identity)
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                             isolation_level=None, timeout=10)
        try:
            if created:
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TABLE authority (owner_id TEXT NOT NULL, registry_id TEXT NOT NULL)")
                db.execute("CREATE TABLE peers (peer_id TEXT PRIMARY KEY, public_key BLOB NOT NULL, "
                           "epoch INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)))")
                db.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, directory TEXT NOT NULL, "
                           "generation TEXT NOT NULL, device TEXT NOT NULL, inode TEXT NOT NULL, "
                           "revision INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)))")
                db.execute("CREATE TABLE grants (grant_id TEXT PRIMARY KEY, peer_id TEXT NOT NULL "
                           "REFERENCES peers(peer_id), project_id TEXT NOT NULL REFERENCES projects(project_id), "
                           "generation TEXT NOT NULL, capabilities TEXT NOT NULL, "
                           "active INTEGER NOT NULL CHECK(active IN (0,1)))")
                db.execute("INSERT INTO authority VALUES (?, ?)", (self.owner_id, str(uuid4())))
                db.execute(f"PRAGMA application_id={_APP_ID}")
                db.execute(f"PRAGMA user_version={_FORMAT}")
                db.commit()
            self._validate(db)
            self._registry_id = db.execute("SELECT registry_id FROM authority").fetchone()[0]
            _uuid(self._registry_id)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        if _file_identity(self.path) != self._identity:
            raise PeerDenied("Peer authority database changed while opening")

    def _validate(self, db):
        if (db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID
                or db.execute("PRAGMA user_version").fetchone()[0] != _FORMAT):
            raise PeerDenied("Unsupported peer authority database")
        rows = db.execute("SELECT owner_id,registry_id FROM authority").fetchall()
        if len(rows) != 1 or rows[0][0] != self.owner_id:
            raise PeerDenied("Peer authority owner does not match")
        if hasattr(self, "_registry_id") and rows[0][1] != self._registry_id:
            raise PeerDenied("Peer authority database was replaced")

    @contextmanager
    def _transaction(self):
        with self._lock:
            db = None
            handling_body = False
            try:
                if _file_identity(self.path) != self._identity:
                    raise PeerDenied("Peer authority database was replaced")
                db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                     isolation_level=None, timeout=10)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._validate(db)
                if _file_identity(self.path) != self._identity:
                    raise PeerDenied("Peer authority database was replaced")
                handling_body = True
                yield db
                handling_body = False
                db.commit()
            except (sqlite3.Error, OSError) as exc:
                if db is not None:
                    db.rollback()
                # Shared project operations own their public OSError subtypes
                # (notably FileNotFoundError for a missing table). Do not turn
                # their ordinary business failures into authorization denials.
                if isinstance(exc, PeerDenied) or (handling_body and isinstance(exc, OSError)):
                    raise
                raise PeerDenied("Peer authority is unavailable") from None
            finally:
                if db is not None:
                    db.close()

    def _now(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise PeerDenied("Peer authority clock is unavailable")
        return now

    def approve_peer(self, peer_id, public_key):
        """Owner-only approval after separately verifying the public fingerprint."""
        if _hex(peer_id) != peer_id_for(public_key):
            raise PeerDenied("Peer fingerprint does not match its public key")
        with self._transaction() as db:
            previous = db.execute("SELECT * FROM peers WHERE peer_id=?", (peer_id,)).fetchone()
            if previous is None:
                if db.execute("SELECT count(*) FROM peers").fetchone()[0] >= MAX_PEERS:
                    raise PeerDenied("Peer authority capacity is exhausted")
                db.execute("INSERT INTO peers VALUES (?, ?, 1, 1)", (peer_id, public_key))
            elif previous["public_key"] != public_key:
                raise PeerDenied("Peer identity changed")
            elif not previous["active"]:
                db.execute("UPDATE peers SET active=1,epoch=epoch+1 WHERE peer_id=?", (peer_id,))
        return {"peer_id": peer_id}

    def revoke_peer(self, peer_id):
        with self._transaction() as db:
            db.execute("UPDATE peers SET active=0,epoch=epoch+1 WHERE peer_id=?", (_hex(peer_id),))
            db.execute("UPDATE grants SET active=0 WHERE peer_id=?", (peer_id,))

    def challenge(self, peer_id, *, channel_binding):
        peer_id, binding = _hex(peer_id), _hex(channel_binding)
        with self._transaction() as db:
            now = self._now()
            self._challenges = {key: value for key, value in self._challenges.items() if value[2] > now}
            peer = db.execute("SELECT epoch FROM peers WHERE peer_id=? AND active=1", (peer_id,)).fetchone()
            if peer is None:
                raise PeerDenied("Peer is not approved")
            if (len(self._challenges) >= MAX_CHALLENGES
                    or sum(x[0]["peer_id"] == peer_id for x in self._challenges.values()) >= 8):
                raise PeerDenied("Peer authentication capacity is exhausted")
            body = {"format": "stk.peer-auth/1", "owner_id": self.owner_id, "peer_id": peer_id,
                    "challenge_id": str(uuid4()), "nonce": secrets.token_hex(32),
                    "channel_binding": binding, "expires_in": CHALLENGE_SECONDS}
            self._challenges[body["challenge_id"]] = (body, peer["epoch"], now + CHALLENGE_SECONDS)
            return dict(body)

    def authenticate(self, challenge_id, signature):
        with self._transaction() as db:
            pending = self._challenges.pop(_uuid(challenge_id), None)
            now = self._now()
            if pending is None or pending[2] <= now or type(signature) is not bytes or len(signature) != 64:
                raise PeerDenied("Peer authentication failed")
            body, epoch, _ = pending
            peer = db.execute("SELECT * FROM peers WHERE peer_id=? AND active=1", (body["peer_id"],)).fetchone()
            if (peer is None or peer["epoch"] != epoch
                    or peer_id_for(peer["public_key"]) != body["peer_id"]):
                raise PeerDenied("Peer authentication failed")
            try:
                from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            except ImportError:
                raise PeerDenied("Peer authentication requires the optional peer dependency") from None
            try:
                Ed25519PublicKey.from_public_bytes(peer["public_key"]).verify(signature, auth_message(body))
            except (InvalidSignature, UnsupportedAlgorithm, ValueError):
                raise PeerDenied("Peer authentication failed") from None
            self._contexts = {key: value for key, value in self._contexts.items() if value[2] > now}
            if len(self._contexts) >= MAX_SESSIONS:
                raise PeerDenied("Peer session capacity is exhausted")
            context = PeerContext()
            self._contexts[context] = (body["peer_id"], epoch, now + SESSION_SECONDS)
            return context

    def disconnect(self, context):
        with self._lock:
            if type(context) is not PeerContext:
                raise PeerDenied("Peer session is unavailable")
            self._contexts.pop(context, None)

    def _peer(self, db, context):
        session = self._contexts.get(context) if type(context) is PeerContext else None
        if session is None or session[2] <= self._now():
            raise PeerDenied("Peer session is unavailable")
        peer = db.execute("SELECT * FROM peers WHERE peer_id=? AND active=1", (session[0],)).fetchone()
        if (peer is None or peer["epoch"] != session[1]
                or peer_id_for(peer["public_key"]) != session[0]):
            raise PeerDenied("Peer session is unavailable")
        return session[0]

    def capabilities(self, context):
        """Current permission kinds for hello filtering, never a substitute for a lease."""
        with self._transaction() as db:
            peer_id = self._peer(db, context)
            rows = db.execute("SELECT g.capabilities FROM grants g JOIN projects p ON p.project_id=g.project_id "
                              "WHERE g.peer_id=? AND g.active=1 AND p.active=1 AND g.generation=p.generation",
                              (peer_id,)).fetchall()
            result = set()
            for row in rows:
                try:
                    values = json.loads(row[0])
                    if (type(values) is not list or not values
                            or any(type(x) is not str or x not in _CAPABILITIES for x in values)
                            or values != sorted(set(values))):
                        raise PeerDenied("Project capabilities are unavailable")
                except (ValueError, TypeError):
                    raise PeerDenied("Project capabilities are unavailable") from None
                result.update(values)
            return frozenset(result)

    def _local_project(self, directory):
        directory = Path(directory).expanduser().resolve()
        if self.directory == directory or self.directory.is_relative_to(directory):
            raise PeerDenied("Peer authority must be stored outside shared projects")
        identity = _file_identity(directory / "project.sqlite3")
        store = ProjectStore(directory)
        info = store.info()
        if _file_identity(store.path) != identity:
            raise PeerDenied("Project database changed while opening")
        return store, info, identity

    def bind_project(self, directory):
        """Owner-only bind; an existing project ID can only move by explicit rebind."""
        with self._transaction() as db:
            store, info, identity = self._local_project(directory)
            row = db.execute("SELECT * FROM projects WHERE project_id=?", (info["id"],)).fetchone()
            if row is not None:
                if (not row["active"] or row["directory"] != str(store.directory)
                        or (row["device"], row["inode"]) != identity or info["revision"] < row["revision"]):
                    raise PeerDenied("Project requires an explicit owner rebind")
                return {"project_id": info["id"], "database_generation": row["generation"]}
            if db.execute("SELECT count(*) FROM projects").fetchone()[0] >= MAX_PROJECTS:
                raise PeerDenied("Project authority capacity is exhausted")
            generation = str(uuid4())
            db.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, 1)",
                       (info["id"], str(store.directory), generation, *identity, info["revision"]))
            return {"project_id": info["id"], "database_generation": generation}

    def grant(self, peer_id, project_id, capabilities):
        peer_id, project_id = _hex(peer_id), _uuid(project_id)
        if (not isinstance(capabilities, (list, tuple, set, frozenset)) or not capabilities
                or any(type(x) is not str or x not in _CAPABILITIES for x in capabilities)):
            raise PeerDenied("Invalid project capabilities")
        with self._transaction() as db:
            peer = db.execute("SELECT 1 FROM peers WHERE peer_id=? AND active=1", (peer_id,)).fetchone()
            project = db.execute("SELECT generation FROM projects WHERE project_id=? AND active=1", (project_id,)).fetchone()
            if peer is None or project is None:
                raise PeerDenied("Project grant is unavailable")
            if db.execute("SELECT count(*) FROM grants").fetchone()[0] >= MAX_GRANTS:
                raise PeerDenied("Project grant capacity is exhausted")
            grant_id = str(uuid4())
            db.execute("UPDATE grants SET active=0 WHERE peer_id=? AND project_id=?", (peer_id, project_id))
            db.execute("INSERT INTO grants VALUES (?, ?, ?, ?, ?, 1)",
                       (grant_id, peer_id, project_id, project["generation"], json.dumps(sorted(set(capabilities)))))
            return {"grant_id": grant_id, "database_generation": project["generation"]}

    def revoke_grant(self, grant_id):
        with self._transaction() as db:
            db.execute("UPDATE grants SET active=0 WHERE grant_id=?", (_uuid(grant_id),))

    @staticmethod
    def _invalidate(db, project_id):
        db.execute("UPDATE projects SET active=0 WHERE project_id=?", (project_id,))
        db.execute("UPDATE peers SET epoch=epoch+1 WHERE peer_id IN "
                   "(SELECT peer_id FROM grants WHERE project_id=?)", (project_id,))
        db.execute("UPDATE grants SET active=0 WHERE project_id=?", (project_id,))

    def rebind_project(self, project_id, directory):
        """Owner-only restore/replacement: rotate generation and revoke old access."""
        project_id = _uuid(project_id)
        with self._transaction() as db:
            previous = db.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if previous is None:
                raise PeerDenied("Project binding is unavailable")
            store, info, identity = self._local_project(directory)
            if info["id"] != project_id:
                raise PeerDenied("Replacement project identity does not match")
            self._invalidate(db, project_id)
            generation = str(uuid4())
            db.execute("UPDATE projects SET directory=?,generation=?,device=?,inode=?,revision=?,active=1 "
                       "WHERE project_id=?", (str(store.directory), generation, *identity, info["revision"], project_id))
            return {"project_id": project_id, "database_generation": generation}

    @contextmanager
    def project_access(self, context, project_id, *, grant_id, database_generation, capability):
        project_id, grant_id, generation = _uuid(project_id), _uuid(grant_id), _uuid(database_generation)
        if type(capability) is not str or capability not in _CAPABILITIES:
            raise PeerDenied("Invalid project capability")
        with self._transaction() as db:
            peer_id = self._peer(db, context)
            grant = db.execute("SELECT * FROM grants WHERE grant_id=? AND peer_id=? AND project_id=? "
                               "AND generation=? AND active=1", (grant_id, peer_id, project_id, generation)).fetchone()
            project = db.execute("SELECT * FROM projects WHERE project_id=? AND generation=? AND active=1",
                                 (project_id, generation)).fetchone()
            if grant is None or project is None:
                raise PeerDenied("Project access is unavailable")
            try:
                capabilities = json.loads(grant["capabilities"])
                valid_capabilities = (type(capabilities) is list and capabilities
                    and all(type(x) is str and x in _CAPABILITIES for x in capabilities)
                    and capabilities == sorted(set(capabilities)))
            except (ValueError, TypeError):
                valid_capabilities = False
            if not valid_capabilities or capability not in capabilities:
                raise PeerDenied("Project access is unavailable")
            try:
                if _file_identity(Path(project["directory"]) / "project.sqlite3") != (project["device"], project["inode"]):
                    raise PeerDenied("Project database was replaced")
                store, info, identity = self._local_project(project["directory"])
                valid = (info["id"] == project_id and info["revision"] >= project["revision"]
                         and identity == (project["device"], project["inode"]))
            except (OSError, ValueError, PeerDenied):
                valid = False
            if not valid:
                self._invalidate(db, project_id)
                db.commit()  # Persist revocation even though this request is rejected.
                raise PeerDenied("Project binding changed; owner rebind is required")
            scope_body = json.dumps([self.owner_id, peer_id, generation], separators=(",", ":")).encode("ascii")
            scope = "peer/1/" + hashlib.sha256(scope_body).hexdigest()
            try:
                yield ProjectLease(store, project_id, scope)
            finally:
                # An unsuccessful business lookup still observed this revision.
                # Preserve the watermark on that path without releasing the lease
                # before the shared-store call has completely finished.
                try:
                    try:
                        if _file_identity(store.path) != identity:
                            raise PeerDenied("Project database was replaced")
                        after = store.info()
                        valid = after["id"] == project_id and after["revision"] >= info["revision"]
                    except (OSError, ValueError, PeerDenied):
                        valid = False
                    if not valid:
                        self._invalidate(db, project_id)
                        db.commit()
                        if capability == "project.edit":
                            raise PeerOutcomeUncertain("Project edit outcome requires explicit receipt lookup")
                        raise PeerDenied("Project binding changed; owner rebind is required")
                    db.execute("UPDATE projects SET revision=? WHERE project_id=?", (after["revision"], project_id))
                    db.commit()
                except (sqlite3.Error, OSError):
                    if capability == "project.edit":
                        raise PeerOutcomeUncertain("Project edit outcome requires explicit receipt lookup") from None
                    raise


__all__ = ["PeerAuthority", "PeerContext", "PeerDenied", "PeerOutcomeUncertain", "ProjectLease", "auth_message", "peer_id_for"]
