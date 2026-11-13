"""Desktop title search over the initial text of saved project conversations."""

from datetime import datetime
from heapq import nlargest
import json
import re
import unicodedata

from . import archive
from .agent_sessions import HARNESS, MAX_EVENT_BYTES, MAX_HEADER_BYTES, _hash, user_text
from .contexts import _digest
from .requests import MAX_REPORT_REQUEST_BYTES
from .store import ProjectError, UnsupportedProjectFormat, _id, _version


_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _label(text):
    clean = " ".join(_CONTROLS.sub(" ", text).split())
    return (clean[:79].rstrip() + "…" if len(clean) > 80 else clean) or "…"


def _fold(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _dated(value):
    if not isinstance(value, str) or len(value) > 40 or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("Invalid conversation creation time")
    return value


def _questions(db, store):
    where, params = archive.where(db, "request", False, column="r.id")
    for row in db.execute("SELECT r.* FROM project_requests AS r" + where, params):
        try:
            if len(row["payload"].encode("utf-8")) > MAX_REPORT_REQUEST_BYTES:
                continue
            request = json.loads(row["payload"])
            if (request["project_id"] != store._project_id or row["project_id"] != store._project_id
                    or any(request[key] != row[key] for key in ("id", "context_id", "message_id"))
                    or _digest({"payload": request, "request_sha256": row["request_sha256"]}) != row["sha256"]):
                continue
            message = store.discussion._get_message(db, row["message_id"])
            if (message["role"] != "user" or message["context_id"] != row["context_id"]
                    or _digest(message) != request["message_sha256"]):
                continue
            _id(row["id"])
            yield {"kind": "question", "id": row["id"], "label": _label(message["text"]),
                   "created_at": _dated(request["created_at"])}
        except (ProjectError, KeyError, TypeError, ValueError, RecursionError):
            continue


def _sessions(db, store):
    rows = db.execute("""SELECT s.id, s.project_id, s.payload, s.sha256, e.turn, e.kind,
                                e.payload AS first_payload, e.previous_sha256, e.sha256 AS first_sha256
                         FROM project_agent_sessions s JOIN project_agent_events e ON e.id = (
                            SELECT id FROM project_agent_events WHERE session_id=s.id ORDER BY id LIMIT 1)""")
    for row in rows:
        try:
            _id(row["id"])
            if (row["project_id"] != store._project_id or row["kind"] != "user_turn" or row["turn"] != 0
                    or row["previous_sha256"] != row["sha256"]
                    or len(row["payload"].encode("utf-8")) > MAX_HEADER_BYTES
                    or len(row["first_payload"].encode("utf-8")) > MAX_EVENT_BYTES):
                continue
            header = json.loads(row["payload"])
            first = json.loads(row["first_payload"])
            if (header["id"] != row["id"] or header["project_id"] != store._project_id or header["harness"] != HARNESS
                    or _hash(header, MAX_HEADER_BYTES) != row["sha256"]
                    or _hash({"session_id": row["id"], "turn": 0, "kind": "user_turn", "payload": first,
                              "previous_sha256": row["sha256"]}, MAX_EVENT_BYTES + 1024) != row["first_sha256"]):
                continue
            yield {"kind": "agent", "id": row["id"], "label": _label(user_text(first["text"])),
                   "created_at": _dated(header["created_at"])}
        except (ProjectError, KeyError, TypeError, ValueError, RecursionError):
            continue


def _order(row):
    return datetime.fromisoformat(row["created_at"]), row["kind"], row["id"]


def search_conversations(store, query, *, after=None, limit=20):
    if not isinstance(query, str) or not 1 <= len(query) <= 200 or type(limit) is not int or not 1 <= limit <= 50:
        raise ProjectError("Conversation search requires a title query of 1 to 200 characters and a limit of 1 to 50")
    terms = _fold(_CONTROLS.sub(" ", query)).split()
    if not terms:
        raise ProjectError("Conversation title query is empty")
    boundary = None
    if after is not None:
        try:
            if after["kind"] not in ("question", "agent"):
                raise ValueError("Invalid conversation kind")
            _id(after["id"])
            _dated(after["created_at"])
            boundary = _order(after)
        except (ProjectError, KeyError, TypeError, ValueError):
            raise ProjectError("Invalid conversation search cursor") from None
    with store._connect() as db:
        version = _version(db)
        if version < 8:
            raise UnsupportedProjectFormat("Upgrade this project before searching saved conversations")
        sources = (_questions(db, store), _sessions(db, store)) if version >= 13 else (_questions(db, store),)

        def matching():
            for source in sources:
                for row in source:
                    title = _fold(row["label"])
                    if all(term in title for term in terms) and (boundary is None or _order(row) < boundary):
                        yield row

        hits = nlargest(limit + 1, matching(), key=_order)
    cursor = {key: hits[limit - 1][key] for key in ("kind", "id", "created_at")} if len(hits) > limit else None
    return {"items": hits[:limit], "next": cursor}
