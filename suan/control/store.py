"""Durable actions and replayable event cursors. Tokens are stored as hashes.

Action results larger than :data:`RESULT_INLINE_LIMIT` bytes of JSON live in the
content-addressed blob store (``result_ref``); :meth:`ControlStore.action`
returns them exactly as if they were inline, and :meth:`ControlStore.actions`
never reads or decodes results.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from .blobs import BlobStore

RESULT_INLINE_LIMIT = 64 * 1024
PROFILES = ("", "desktop")
ACTION_COLUMNS = ("id", "request", "node_id", "state", "result", "error", "created", "updated", "review_reason",
                  "result_ref")
# Everything a listing needs; results are loaded one action at a time.
LISTING_COLUMNS = ("id", "request", "node_id", "state", "error", "created", "updated", "review_reason")


def encode(value):
    """Canonical JSON (sorted keys): requests and snapshots are compared as text."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def encode_result(value):
    """JSON of an action result in its own key order (table columns keep the order the node gave them)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def decode_result(text):
    """Decode a stored action result (the only place results are parsed)."""
    return json.loads(text)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ControlStore:
    def __init__(self, directory, blob_max_bytes=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "control.sqlite3"
        self.blobs = BlobStore(self.directory / "blobs", **({} if blob_max_bytes is None else
                                                            {"max_bytes": blob_max_bytes}))
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, name TEXT, role TEXT,
                    token_hash TEXT UNIQUE, revoked INTEGER DEFAULT 0, last_seen REAL, snapshot TEXT);
                CREATE TABLE IF NOT EXISTS pairings(code_hash TEXT PRIMARY KEY, role TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, request TEXT, node_id TEXT,
                    state TEXT, result TEXT, error TEXT, created REAL, updated REAL, review_reason TEXT);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT, payload TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, name TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, session_id TEXT,
                    role TEXT, content TEXT, created REAL);
            """)
            # Additive migration of databases created before result offloading.
            if "result_ref" not in {row["name"] for row in db.execute("PRAGMA table_info(actions)")}:
                db.execute("ALTER TABLE actions ADD COLUMN result_ref TEXT")
            # Additive migration: the owner-granted client profile ("desktop": see policy.py).
            for table in ("devices", "pairings"):
                if "profile" not in {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN profile TEXT NOT NULL DEFAULT ''")
            # Additive migration: the device that submitted an action (review_policy "not-self").
            if "submitted_by" not in {row["name"] for row in db.execute("PRAGMA table_info(actions)")}:
                db.execute("ALTER TABLE actions ADD COLUMN submitted_by TEXT NOT NULL DEFAULT ''")
            # Client uploads (suan.control.uploads): which device stored which blob, and which
            # workspace.import actions reference them (quota and garbage collection).
            db.execute("CREATE TABLE IF NOT EXISTS client_blobs(device_id TEXT, sha256 TEXT, size INTEGER, "
                       "created REAL, PRIMARY KEY(device_id, sha256))")
            db.execute("CREATE TABLE IF NOT EXISTS import_refs(action_id TEXT, sha256 TEXT, "
                       "PRIMARY KEY(action_id, sha256))")
            db.execute("CREATE INDEX IF NOT EXISTS import_refs_sha ON import_refs(sha256)")
            db.execute("CREATE INDEX IF NOT EXISTS actions_node_state ON actions(node_id, state, created)")
            db.execute("CREATE INDEX IF NOT EXISTS actions_state ON actions(state, created)")
            db.execute("CREATE INDEX IF NOT EXISTS actions_created ON actions(created)")
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, kind, payload):
        db.execute("INSERT INTO events(kind,payload,created) VALUES(?,?,?)", (kind, encode(payload), time.time()))

    def pairing(self, role, profile=""):
        """A one-time pairing code; ``profile`` ("desktop", clients only) is granted by the owner here."""
        if profile not in PROFILES or (profile and role != "client"):
            raise ValueError("Profile must be empty or 'desktop' (client pairings only)")
        code = secrets.token_urlsafe(24)
        expires = time.time() + 300
        with self.db() as db:
            db.execute("DELETE FROM pairings WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO pairings(code_hash,role,expires,profile) VALUES(?,?,?,?)",
                       (digest(code), role, expires, profile))
        return {"code": code, "expires_at": expires, "role": role, **({"profile": profile} if profile else {})}

    def claim(self, code, name):
        token, identity = secrets.token_urlsafe(32), uuid.uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            pair = db.execute("SELECT * FROM pairings WHERE code_hash=?", (digest(code),)).fetchone()
            if pair is None or pair["expires"] < time.time():
                raise ValueError("Pairing code expired or already used")
            db.execute("DELETE FROM pairings WHERE code_hash=?", (digest(code),))
            db.execute("INSERT INTO devices(id,name,role,token_hash,revoked,last_seen,snapshot,profile) "
                       "VALUES(?,?,?,?,0,NULL,'{}',?)", (identity, name, pair["role"], digest(token), pair["profile"]))
            self.event(db, "devices.changed", {"device_id": identity})
        return {"device_id": identity, "token": token, "role": pair["role"], "profile": pair["profile"]}

    def authenticate(self, token):
        with self.db() as db:
            row = db.execute("SELECT id,role,profile FROM devices WHERE token_hash=? AND revoked=0",
                             (digest(token),)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _device(r):
        return {**dict(r), "snapshot": json.loads(r["snapshot"]),
                "online": not r["revoked"] and r["last_seen"] is not None and time.time()-r["last_seen"] < 20}

    def devices(self):
        with self.db() as db:
            rows = db.execute("SELECT id,name,role,profile,revoked,last_seen,snapshot FROM devices").fetchall()
        return [self._device(r) for r in rows]

    def device(self, identity):
        """One device (``None`` when unknown)."""
        with self.db() as db:
            row = db.execute("SELECT id,name,role,profile,revoked,last_seen,snapshot FROM devices WHERE id=?",
                             (identity,)).fetchone()
        return self._device(row) if row else None

    def revoke(self, identity):
        with self.db() as db:
            db.execute("UPDATE devices SET revoked=1 WHERE id=?", (identity,))
            self.event(db, "devices.changed", {"device_id": identity})

    def heartbeat(self, identity, snapshot):
        with self.db() as db:
            old = db.execute("SELECT snapshot FROM devices WHERE id=?", (identity,)).fetchone()
            body = encode(snapshot)
            db.execute("UPDATE devices SET last_seen=?,snapshot=? WHERE id=?", (time.time(), body, identity))
            if old and old[0] != body:
                self.event(db, "devices.changed", {"device_id": identity})

    @staticmethod
    def _import_refs(db, request):
        if request.get("kind") == "workspace.import":
            db.executemany("INSERT OR IGNORE INTO import_refs(action_id,sha256) VALUES(?,?)",
                           [(request["id"], item["sha256"]) for item in request["payload"]["files"]])

    def create_action(self, request, review_reason="", submitted_by=""):
        identity = request["id"]
        body = encode(request)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT request FROM actions WHERE id=?", (identity,)).fetchone()
            if old and old[0] != body:
                raise ValueError("Action ID already used for a different request")
            if not old:
                db.execute("INSERT INTO actions(id,request,node_id,state,result,error,created,updated,review_reason,"
                           "submitted_by) VALUES(?,?,?,?,NULL,'',?,?,?,?)", (
                               identity, body, request["node_id"], "review" if review_reason else "queued",
                               time.time(), time.time(), review_reason, submitted_by))
                self._import_refs(db, request)
                self.event(db, "actions.changed", {"action_id": identity})
        return self.action(identity)

    def submitter(self, identity):
        """The device id that submitted an action (``""`` for actions from before the column existed)."""
        with self.db() as db:
            row = db.execute("SELECT submitted_by FROM actions WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError("Action not found")
        return row[0]

    def fail(self, identity, error, states=("queued", "review")):
        """Move an unfinished action to ``failed`` (oversized for the node link, or stopped by the owner).

        Returns ``True`` when it changed; a node result that arrives later is ignored.
        """
        with self.db() as db:
            changed = db.execute(f"UPDATE actions SET state='failed',error=?,updated=? WHERE id=? AND state IN "
                                 f"({','.join('?' * len(states))})", (error[:2000], time.time(), identity, *states))
            if changed.rowcount:
                self.event(db, "actions.changed", {"action_id": identity})
            return bool(changed.rowcount)

    # -- client blobs (uploads, quota, garbage collection) --------------------------------------

    def record_client_blob(self, device, digest, size):
        with self.db() as db:
            db.execute("INSERT INTO client_blobs(device_id,sha256,size,created) VALUES(?,?,?,?) "
                       "ON CONFLICT(device_id,sha256) DO UPDATE SET created=excluded.created",
                       (device, digest, size, time.time()))

    def is_client_blob(self, digest):
        with self.db() as db:
            return db.execute("SELECT 1 FROM client_blobs WHERE sha256=?", (digest,)).fetchone() is not None

    def forget_client_blob(self, digest, db=None):
        """The hub or a node stored the same bytes for itself: never collect them as a client upload."""
        if db is not None:
            db.execute("DELETE FROM client_blobs WHERE sha256=?", (digest,))
            return
        with self.db() as connection:
            connection.execute("DELETE FROM client_blobs WHERE sha256=?", (digest,))

    def client_usage(self, device):
        """Bytes of this device's client blobs no queued or succeeded import references yet (its quota)."""
        with self.db() as db:
            row = db.execute("SELECT COALESCE(SUM(c.size),0) FROM client_blobs c WHERE c.device_id=? AND NOT EXISTS("
                             "SELECT 1 FROM import_refs r JOIN actions a ON a.id=r.action_id WHERE r.sha256=c.sha256 "
                             "AND a.state IN ('queued','succeeded'))", (device,)).fetchone()
        return int(row[0])

    def collect_client_blobs(self, cutoff):
        """Forget client blobs stored before ``cutoff`` that no pending or done import references.

        Returns their sha256s (the caller deletes the files). A blob several devices uploaded is
        collected only when every device's copy qualifies.
        """
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT c.sha256 FROM client_blobs c GROUP BY c.sha256 HAVING MAX(c.created) < ? "
                              "AND NOT EXISTS(SELECT 1 FROM import_refs r JOIN actions a ON a.id=r.action_id "
                              "WHERE r.sha256=c.sha256 AND a.state IN ('review','queued','succeeded'))",
                              (cutoff,)).fetchall()
            digests = [row[0] for row in rows]
            db.executemany("DELETE FROM client_blobs WHERE sha256=?", [(d,) for d in digests])
        return digests

    def create_cancel(self, request, submitted_by=""):
        """Create a ``graph.cancel`` action for ``request["payload"]["action_id"]`` in one transaction.

        A target still in review is failed here (it never reaches the node) and the cancel action is
        created ``succeeded``; a finished target leaves the cancel ``succeeded`` with
        ``cancelled: false``; a queued target (possibly running) gets a queued cancel the node runs.
        Raises ``ValueError`` for an unknown target, another node's action or a non-graph action.
        """
        identity, target_id = request["id"], request["payload"]["action_id"]
        body = encode(request)
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT request FROM actions WHERE id=?", (identity,)).fetchone()
            if old and old[0] != body:
                raise ValueError("Action ID already used for a different request")
            if not old:
                target = db.execute("SELECT request,node_id,state FROM actions WHERE id=?", (target_id,)).fetchone()
                if (target is None or target["node_id"] != request["node_id"]
                        or json.loads(target["request"]).get("kind") != "graph.evaluate"):
                    raise ValueError("graph.cancel needs a graph.evaluate action of the same node")
                state, result = "succeeded", {"cancelled": False, "state": target["state"]}
                if target["state"] == "review":
                    db.execute("UPDATE actions SET state='failed',error=?,updated=? WHERE id=? AND state='review'",
                               ("cancelled: Cancelled by a client before review", now, target_id))
                    self.event(db, "actions.changed", {"action_id": target_id})
                    result = {"cancelled": True, "state": "failed"}
                elif target["state"] == "queued":
                    state, result = "queued", None
                db.execute("INSERT INTO actions(id,request,node_id,state,result,error,created,updated,review_reason,"
                           "submitted_by) VALUES(?,?,?,?,?,'',?,?,'',?)",
                           (identity, body, request["node_id"], state,
                            None if result is None else encode_result(result), now, now, submitted_by))
                self.event(db, "actions.changed", {"action_id": identity})
        return self.action(identity)

    def action(self, identity):
        """One action with its full result (inline or from the blob store)."""
        with self.db() as db:
            row = db.execute(f"SELECT {','.join(ACTION_COLUMNS)} FROM actions WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError("Action not found")
        record = {key: row[key] for key in ACTION_COLUMNS if key != "result_ref"}
        record["request"] = json.loads(row["request"])
        if row["result_ref"]:
            try:
                text = self.blobs.read(row["result_ref"]).decode("utf-8")
            except (OSError, ValueError):
                text = None  # the stored result is gone; the action record is still valid
            record["result"] = decode_result(text) if text is not None else None
        else:
            record["result"] = decode_result(row["result"]) if row["result"] is not None else None
        return record

    def actions(self, node_id=None, pending=False):
        """Newest 200 actions without results (listing and node dispatch never decode results).

        A listing also keeps every action still awaiting review, so frequent
        reads (``task.events`` polls) cannot push a review out of view.
        """
        columns = ",".join(LISTING_COLUMNS)
        with self.db() as db:
            rows = db.execute(f"SELECT {columns} FROM actions WHERE (? IS NULL OR node_id=?) "
                              "AND (?=0 OR state='queued') ORDER BY created DESC LIMIT 200",
                              (node_id, node_id, pending)).fetchall()
            if not pending:
                seen = {r["id"] for r in rows}
                reviews = db.execute(f"SELECT {columns} FROM actions WHERE state='review' AND (? IS NULL OR node_id=?) "
                                     "ORDER BY created DESC LIMIT 200", (node_id, node_id)).fetchall()
                rows = sorted([*rows, *(r for r in reviews if r["id"] not in seen)], key=lambda r: r["created"],
                              reverse=True)
        return [{**{key: r[key] for key in LISTING_COLUMNS}, "request": json.loads(r["request"])} for r in rows]

    def approve(self, identity, approved):
        with self.db() as db:
            db.execute("UPDATE actions SET state=?,updated=? WHERE id=? AND state='review'",
                       ("queued" if approved else "rejected", time.time(), identity))
            self.event(db, "actions.changed", {"action_id": identity})
        return self.action(identity)

    def complete(self, identity, node_id, result=None, error=""):
        body = encode_result(result)
        with self.db() as db:
            row = db.execute("SELECT state,node_id FROM actions WHERE id=?", (identity,)).fetchone()
            if not row or row["node_id"] != node_id or row["state"] != "queued":
                return
            data = body.encode("utf-8")
            reference = None
            if len(data) > RESULT_INLINE_LIMIT:
                # Large results (views, catalogs) move out of the row; listings stay cheap.
                reference, body = self.blobs.put(data), None
                self.forget_client_blob(reference, db)
            db.execute("UPDATE actions SET state=?,result=?,result_ref=?,error=?,updated=? WHERE id=?",
                       ("failed" if error else "succeeded", body, reference, error[:2000], time.time(), identity))
            self.event(db, "actions.changed", {"action_id": identity})

    def events(self, after=0):
        with self.db() as db:
            rows = db.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (after,)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def session(self, identity, name="新会话"):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?)", (identity, name, time.time()))
            rows = db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY created", (identity,)).fetchall()
        return {"id": identity, "messages": [dict(r) for r in rows]}

    def message(self, identity, session_id, role, content):
        with self.db() as db:
            old = db.execute("SELECT session_id,role,content FROM messages WHERE id=?", (identity,)).fetchone()
            if old and tuple(old) != (session_id, role, content):
                raise ValueError("Message ID reused for different content or session")
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?)", (identity, session_id, role, content, time.time()))
            self.event(db, "sessions.changed", {"session_id": session_id})

    def publish_reply(self, identity, session_id, content, proposals, submitted_by=""):
        """Publish all validated tools and the assistant reply in one transaction.

        A malformed later tool, crash, or concurrent retry cannot expose a
        partially accepted plan to an execution node.
        """
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM messages WHERE id=?", (identity,)).fetchone():
                return
            states = []
            for request, reason in proposals:
                body = encode(request)
                old = db.execute("SELECT request FROM actions WHERE id=?", (request["id"],)).fetchone()
                if old and old[0] != body:
                    raise ValueError("Action ID already used for a different request")
                state = "review" if reason else "queued"
                if not old:
                    db.execute("INSERT INTO actions(id,request,node_id,state,result,error,created,updated,"
                               "review_reason,submitted_by) VALUES(?,?,?,?,NULL,'',?,?,?,?)", (
                                   request["id"], body, request["node_id"], state, time.time(), time.time(), reason,
                                   submitted_by))
                    self._import_refs(db, request)
                    self.event(db, "actions.changed", {"action_id": request["id"]})
                states.append(f"操作 {request['id']}：{state}")
            if states:
                content += "\n" + "\n".join(states)
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?)", (identity, session_id, "assistant", content, time.time()))
            self.event(db, "sessions.changed", {"session_id": session_id})
