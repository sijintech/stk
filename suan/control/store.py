"""Durable actions and replayable event cursors. Tokens are stored as hashes."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ControlStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "control.sqlite3"
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

    def pairing(self, role):
        code = secrets.token_urlsafe(24)
        expires = time.time() + 300
        with self.db() as db:
            db.execute("DELETE FROM pairings WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO pairings VALUES(?,?,?)", (digest(code), role, expires))
        return {"code": code, "expires_at": expires, "role": role}

    def claim(self, code, name):
        token, identity = secrets.token_urlsafe(32), uuid.uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            pair = db.execute("SELECT * FROM pairings WHERE code_hash=?", (digest(code),)).fetchone()
            if pair is None or pair["expires"] < time.time():
                raise ValueError("Pairing code expired or already used")
            db.execute("DELETE FROM pairings WHERE code_hash=?", (digest(code),))
            db.execute("INSERT INTO devices VALUES(?,?,?,?,0,NULL,'{}')", (identity, name, pair["role"], digest(token)))
            self.event(db, "devices.changed", {"device_id": identity})
        return {"device_id": identity, "token": token, "role": pair["role"]}

    def authenticate(self, token):
        with self.db() as db:
            row = db.execute("SELECT id,role FROM devices WHERE token_hash=? AND revoked=0", (digest(token),)).fetchone()
        return dict(row) if row else None

    def devices(self):
        with self.db() as db:
            rows = db.execute("SELECT id,name,role,revoked,last_seen,snapshot FROM devices").fetchall()
        return [{**dict(r), "snapshot": json.loads(r["snapshot"]),
                 "online": not r["revoked"] and r["last_seen"] is not None and time.time()-r["last_seen"] < 20} for r in rows]

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

    def create_action(self, request, review_reason=""):
        identity = request["id"]
        body = encode(request)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT request FROM actions WHERE id=?", (identity,)).fetchone()
            if old and old[0] != body:
                raise ValueError("Action ID already used for a different request")
            if not old:
                db.execute("INSERT INTO actions VALUES(?,?,?,?,NULL,'',?,?,?)", (
                    identity, body, request["node_id"], "review" if review_reason else "queued",
                    time.time(), time.time(), review_reason))
                self.event(db, "actions.changed", {"action_id": identity})
        return self.action(identity)

    def action(self, identity):
        with self.db() as db:
            row = db.execute("SELECT * FROM actions WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError("Action not found")
        return {**dict(row), "request": json.loads(row["request"]),
                "result": json.loads(row["result"]) if row["result"] is not None else None}

    def actions(self, node_id=None, pending=False):
        with self.db() as db:
            rows = db.execute("SELECT id FROM actions WHERE (? IS NULL OR node_id=?) "
                              "AND (?=0 OR state='queued') ORDER BY created DESC LIMIT 200",
                              (node_id, node_id, pending)).fetchall()
        return [self.action(r[0]) for r in rows]

    def approve(self, identity, approved):
        with self.db() as db:
            db.execute("UPDATE actions SET state=?,updated=? WHERE id=? AND state='review'",
                       ("queued" if approved else "rejected", time.time(), identity))
            self.event(db, "actions.changed", {"action_id": identity})
        return self.action(identity)

    def complete(self, identity, node_id, result=None, error=""):
        with self.db() as db:
            row = db.execute("SELECT state,node_id FROM actions WHERE id=?", (identity,)).fetchone()
            if not row or row["node_id"] != node_id or row["state"] != "queued":
                return
            db.execute("UPDATE actions SET state=?,result=?,error=?,updated=? WHERE id=?",
                       ("failed" if error else "succeeded", encode(result), error[:2000], time.time(), identity))
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

    def publish_reply(self, identity, session_id, content, proposals):
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
                    db.execute("INSERT INTO actions VALUES(?,?,?,?,NULL,'',?,?,?)", (
                        request["id"], body, request["node_id"], state, time.time(), time.time(), reason))
                    self.event(db, "actions.changed", {"action_id": request["id"]})
                states.append(f"操作 {request['id']}：{state}")
            if states:
                content += "\n" + "\n".join(states)
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?)", (identity, session_id, "assistant", content, time.time()))
            self.event(db, "sessions.changed", {"session_id": session_id})
