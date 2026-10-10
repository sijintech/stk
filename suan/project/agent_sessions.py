"""Agent sessions (project format 13, docs/design/agent-harness.md): a frozen header and an append-only, hash-chained
event log per session, plus a registry of the project objects each step made.

The header freezes everything a planner turn was built from (system prompt, skills, tool definitions, model
configuration, route, policy and limits) so a session can be checked without the code that made it. Every event's
digest covers the session, its turn, kind and payload and the previous digest; the chain starts at the header's
digest, so changing the header or any event, or their order, breaks every read. Nothing here calls a model or a
tool: suan/agent/executor.py does, and records each step here before and after it acts. Sessions never change the
editable revision or enter undo.
"""
from datetime import datetime, timezone
import hashlib
import json

from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _id, _version

HARNESS = "stk.agent/1"
MAX_HEADER_BYTES = 256 * 1024
MAX_EVENT_BYTES = 64 * 1024
MAX_USER_TEXT_CHARS = 8 * 1024
MAX_VIEW_EVENTS = 1000
MAX_AWAITING = 100  # the newest open items a view lists
KINDS = ("user_turn", "model_claimed", "model_completed", "model_settled", "tool_called", "tool_result", "awaiting_user",
         "approval_decided", "approval_receipt", "observed", "policy", "cancel_requested", "stopped")
OBJECT_KINDS = ("context", "message", "request", "draft")
# A session ends after these: an uncertain planner turn is never re-sent (owner decision 5), and an interrupted one is
# uncertain too. Others (final, limit, cancelled, error, private_data, network) leave room for the next message.
ENDING_REASONS = ("uncertain", "interrupted")


class AgentSessionNotFound(ProjectError):
    """The selected agent session does not exist."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _require(db):
    if _version(db) < 13:
        raise UnsupportedProjectFormat("Upgrade this project to format 13 before using the agent")


def available(db):
    return _version(db) >= 13


def _pack(value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProjectError(f"Invalid bounded agent session JSON: {exc}") from None
    if len(raw.encode("utf-8")) > limit:
        raise ProjectError("Agent session JSON exceeds its bounded byte limit")
    return raw


def _hash(value, limit):
    return hashlib.sha256(_pack(value, limit).encode("utf-8")).hexdigest()


def digest(value, limit=MAX_EVENT_BYTES):
    """The canonical SHA-256 of a JSON value (sorted keys, no spaces), as used for every hash in a session."""
    return _hash(value, limit)


def user_text(value):
    if type(value) is not str or not value.strip() or len(value) > MAX_USER_TEXT_CHARS or "\0" in value:
        raise ProjectError(f"An agent message is text of 1 to {MAX_USER_TEXT_CHARS} characters")
    return value


class AgentSessions:
    def __init__(self, store):
        self.store = store

    # ---- writing ----

    def create(self, session_id, header, text, *, turn_id, request_sha256):
        """Freeze ``header`` and the first message. The same ID with the same creation request returns the existing
        session; with another request it conflicts (as requests and runs do)."""
        _id(session_id)
        _id(turn_id)
        text = user_text(text)
        if type(request_sha256) is not str or len(request_sha256) != 64:
            raise ProjectError("An agent session needs the digest of its creation request")
        if not isinstance(header, dict) or header.get("harness") != HARNESS or header.get("id") != session_id:
            raise ProjectError("An agent session header names its harness and its session")
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT request_sha256 FROM project_agent_sessions WHERE id=?", (session_id,)).fetchone()
            if existing is not None:
                if existing[0] != request_sha256:
                    raise RevisionConflict("Agent session ID already used for another request")
                return self._get(db, session_id)
            header = {**header, "project_id": self.store._project_id, "created_at": header.get("created_at") or _now()}
            packed = _pack(header, MAX_HEADER_BYTES)
            db.execute("INSERT INTO project_agent_sessions VALUES (?,?,?,?,?)",
                       (session_id, self.store._project_id, packed, request_sha256, _hash(header, MAX_HEADER_BYTES)))
            self._append(db, session_id, 0, "user_turn", {"turn_id": turn_id, "text": text, "at": _now()})
            return self._get(db, session_id)

    def replay(self, session_id, request_sha256):
        """The session an identical creation request already made (``None`` when the ID is unused); another request
        with the same ID conflicts. Lets a caller answer a repeated create before resolving anything new."""
        _id(session_id)
        with self.store._connect() as db:
            _require(db)
            existing = db.execute("SELECT request_sha256 FROM project_agent_sessions WHERE id=?", (session_id,)).fetchone()
            if existing is None:
                return None
            if existing[0] != request_sha256:
                raise RevisionConflict("Agent session ID already used for another request")
            return self._get(db, session_id)

    def say(self, session_id, text, *, turn_id):
        """Append the next message; the same ``turn_id`` again is a no-op. Refused once the session has ended."""
        _id(turn_id)
        text = user_text(text)
        with self.store._connect(write=True) as db:
            header, events = self._read(db, session_id)
            for event in events:
                if event["kind"] == "user_turn" and event["turn_id"] == turn_id:
                    if event["text"] != text:
                        raise RevisionConflict("Agent message ID already used for another text")
                    return self._view(header, events)
            state = self.state(events)
            if state["state"] == "ended":
                raise ProjectError("This agent session has ended; start a new one")
            if state["state"] == "ready":
                raise ProjectError("The agent has not answered the previous message yet")
            turn = state["turn"] + 1
            self._append(db, session_id, turn, "user_turn", {"turn_id": turn_id, "text": text, "at": _now()})
            return self._get(db, session_id)

    def append(self, session_id, kind, payload, *, turn, objects=()):
        """Append one event (committed before this returns) and register the objects it made, in one transaction.
        ``objects`` is ``[(kind, id), ...]``; an object belongs to at most one step of one session."""
        if kind not in KINDS:
            raise ProjectError(f"Unknown agent event kind {kind}")
        if not isinstance(payload, dict) or payload.keys() & {"id", "turn", "kind", "sha256"}:
            raise ProjectError("An agent event payload is an object without id, turn, kind or sha256")
        if type(turn) is not int or turn < 0:
            raise ProjectError("An agent event's turn is a non-negative integer")
        with self.store._connect(write=True) as db:
            self._read(db, session_id)
            event_id = self._append(db, session_id, turn, kind, payload)
            for object_kind, object_id in objects:
                if object_kind not in OBJECT_KINDS:
                    raise ProjectError(f"Unknown agent object kind {object_kind}")
                _id(object_id)
                owner = db.execute("SELECT session_id FROM project_agent_objects WHERE kind=? AND object_id=?",
                                   (object_kind, object_id)).fetchone()
                if owner is not None:
                    if owner[0] != session_id:
                        raise ProjectError(f"The {object_kind} {object_id} belongs to another agent session")
                    continue  # replayed step: already registered
                db.execute("INSERT INTO project_agent_objects VALUES (?,?,?,?)", (object_kind, object_id, session_id, event_id))
            return event_id

    def _append(self, db, session_id, turn, kind, payload):
        previous = db.execute("SELECT sha256 FROM project_agent_events WHERE session_id=? ORDER BY id DESC LIMIT 1",
                              (session_id,)).fetchone()
        if previous is None:
            previous = db.execute("SELECT sha256 FROM project_agent_sessions WHERE id=?", (session_id,)).fetchone()
        previous_hash = previous[0]
        packed = _pack(payload, MAX_EVENT_BYTES)
        event_digest = _hash({"session_id": session_id, "turn": turn, "kind": kind, "payload": payload,
                              "previous_sha256": previous_hash}, MAX_EVENT_BYTES + 1024)
        cursor = db.execute("INSERT INTO project_agent_events(session_id,turn,kind,payload,previous_sha256,sha256) "
                            "VALUES (?,?,?,?,?,?)", (session_id, turn, kind, packed, previous_hash, event_digest))
        return cursor.lastrowid

    # ---- reading ----

    def get(self, session_id, *, offset=None, limit=None):
        with self.store._connect() as db:
            return self._get(db, session_id, offset=offset, limit=limit)

    def events(self, session_id):
        """The header and every event (checked), for the agent layer; not bounded like ``get``."""
        with self.store._connect() as db:
            return self._read(db, session_id)

    def _get(self, db, session_id, *, offset=None, limit=None):
        header, events = self._read(db, session_id)
        return self._view(header, events, offset=offset, limit=limit)

    def _view(self, header, events, *, offset=None, limit=None):
        """A page of events: ``limit`` of them from ``offset``; without either, the newest ``MAX_VIEW_EVENTS``."""
        if (offset is not None and (type(offset) is not int or offset < 0)) or (
                limit is not None and (type(limit) is not int or not 1 <= limit <= MAX_VIEW_EVENTS)):
            raise ProjectError(f"offset is a non-negative integer and limit 1 to {MAX_VIEW_EVENTS}")
        if offset is None and limit is None:
            shown = events[-MAX_VIEW_EVENTS:]
        else:
            start = offset or 0
            shown = events[start:start + (limit or MAX_VIEW_EVENTS)]
        return {"session": header, "events": shown, "total": len(events), "chain_sha256": events[-1]["sha256"] if events
                else header["sha256"], **self.state(events)}

    def _read(self, db, session_id):
        """The header and every event, after checking the header digest and the whole chain."""
        _id(session_id)
        _require(db)
        row = db.execute("SELECT * FROM project_agent_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise AgentSessionNotFound("Agent session not found")
        header = json.loads(row["payload"])
        if (_hash(header, MAX_HEADER_BYTES) != row["sha256"] or header.get("id") != session_id
                or header.get("project_id") != self.store._project_id or header.get("harness") != HARNESS):
            raise ProjectError("Invalid frozen agent session header or checksum")
        events, previous = [], row["sha256"]
        for event in db.execute("SELECT * FROM project_agent_events WHERE session_id=? ORDER BY id", (session_id,)):
            payload = json.loads(event["payload"])
            event_digest = _hash({"session_id": session_id, "turn": event["turn"], "kind": event["kind"], "payload": payload,
                                  "previous_sha256": previous}, MAX_EVENT_BYTES + 1024)
            if event["previous_sha256"] != previous or event["sha256"] != event_digest:
                raise ProjectError("The agent session log is not an unbroken chain")
            previous = event_digest
            events.append({"id": event["id"], "turn": event["turn"], "kind": event["kind"], "sha256": event_digest, **payload})
        return {**header, "sha256": row["sha256"]}, events

    def list(self, *, offset=0, limit=50):
        """Sessions, newest first: ID, first message, state, turn count and when it was created."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ProjectError("offset is a non-negative integer and limit 1 to 200")
        with self.store._connect() as db:
            if not available(db):
                return {"items": [], "total": 0}
            total = db.execute("SELECT count(*) FROM project_agent_sessions").fetchone()[0]
            ids = [row[0] for row in db.execute("SELECT s.id FROM project_agent_sessions s ORDER BY "
                                                "(SELECT min(e.id) FROM project_agent_events e WHERE e.session_id=s.id) DESC "
                                                "LIMIT ? OFFSET ?", (limit, offset))]
            items = []
            for session_id in ids:
                header, events = self._read(db, session_id)
                first = next((event["text"] for event in events if event["kind"] == "user_turn"), "")
                items.append({"id": session_id, "created_at": header["created_at"], "first_message": first[:200],
                              **self.state(events)})
        return {"items": items, "total": total}

    def object_owner(self, kind, object_id):
        """Which session and step made an object: ``{session_id, event_id, turn}`` or ``None``."""
        if kind not in OBJECT_KINDS:
            raise ProjectError(f"Unknown agent object kind {kind}")
        _id(object_id)
        with self.store._connect() as db:
            if not available(db):
                return None
            row = db.execute("SELECT o.session_id, o.event_id, e.turn FROM project_agent_objects o "
                             "JOIN project_agent_events e ON e.id=o.event_id WHERE o.kind=? AND o.object_id=?",
                             (kind, object_id)).fetchone()
        return None if row is None else {"session_id": row[0], "event_id": row[1], "turn": row[2]}

    def objects(self, session_id):
        """Every object registered for a session, in the order it was made."""
        with self.store._connect() as db:
            self._read(db, session_id)
            return [{"kind": row[0], "id": row[1], "event_id": row[2]} for row in db.execute(
                "SELECT kind, object_id, event_id FROM project_agent_objects WHERE session_id=? ORDER BY event_id",
                (session_id,))]

    @staticmethod
    def open_steps(events):
        """What a lost executor left open: planner claims with no outcome and tool calls with no result (a claim is
        ``(turn, call)``, unique in a session; a tool call's ID is the executor's). Returns ``(claims, tool_calls)``."""
        settled = {(event["turn"], event.get("call")) for event in events
                   if event["kind"] in ("model_completed", "model_settled")}
        results = {event.get("call_id") for event in events if event["kind"] == "tool_result"}
        claims = [event for event in events if event["kind"] == "model_claimed" and (event["turn"], event["call"]) not in settled]
        calls = [event for event in events if event["kind"] == "tool_called" and event["call_id"] not in results]
        return claims, calls

    @staticmethod
    def state(events):
        """``ready`` (a message waits for the agent), ``awaiting`` (the agent waits for a person), ``idle`` or ``ended``,
        with the current turn, the open awaited items and why it last stopped."""
        turn, stop, ended = 0, None, False
        awaited, resolved = {}, set()
        answered = True
        for event in events:
            kind = event["kind"]
            if kind == "user_turn":
                turn, answered = event["turn"], False
            elif kind == "stopped":
                stop, answered = event.get("reason"), True
                ended = ended or stop in ENDING_REASONS
            elif kind == "awaiting_user":
                for item in event.get("items", []):
                    awaited[item["item_id"]] = item
            elif kind == "approval_receipt" and event.get("ok") and event.get("item_id"):
                resolved.add(event["item_id"])  # a decision whose action failed leaves its item open
            elif kind == "observed" and event.get("resolved", False) and event.get("item_id"):
                resolved.add(event["item_id"])
        open_items = [item for key, item in awaited.items() if key not in resolved][-MAX_AWAITING:]
        if ended:
            state = "ended"
        elif not answered:
            state = "ready"
        elif open_items:
            state = "awaiting"
        else:
            state = "idle"
        return {"state": state, "turn": turn, "stop_reason": stop, "awaiting": open_items}

    def verify(self, session_id, *, snapshot=False):
        """Check the chain, the header and that every registered object still exists. The agent layer adds the
        checks that need its code (rebuilt planner inputs, recomputed tools); ``snapshot`` also returns the header and
        events this check read, so those checks and an export describe the same log."""
        problems = []
        with self.store._connect() as db:
            header, events = self._read(db, session_id)
            for kind, object_id, event_id in db.execute(
                    "SELECT kind, object_id, event_id FROM project_agent_objects WHERE session_id=?", (session_id,)):
                table = {"context": "project_contexts", "message": "project_messages", "request": "project_requests",
                         "draft": "project_drafts"}[kind]
                if db.execute(f"SELECT 1 FROM {table} WHERE id=?", (object_id,)).fetchone() is None:
                    problems.append(f"The {kind} {object_id} of step {event_id} no longer exists")
        report = {"session_id": session_id, "events": len(events), "chain_sha256": events[-1]["sha256"] if events
                  else header["sha256"], "problems": problems}
        return (report, header, events) if snapshot else report


__all__ = ["AgentSessions", "AgentSessionNotFound", "HARNESS", "KINDS", "MAX_VIEW_EVENTS", "OBJECT_KINDS", "available",
           "digest", "user_text"]
