"""Manual discussion records and metadata-only links to immutable saved drafts.

Roles label imported text, not authenticated actors or approval. These operations
never execute code, edit parameters, prepare runs, or submit tasks.
"""

from datetime import datetime, timezone

from .contexts import _decode_record, _digest, _encode, _pagination, _require
from .store import ProjectError, RevisionConflict, _id, _expected_revision


MAX_TEXT_BYTES = 64 * 1024


def _message_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ProjectError("Message text must be nonempty")
    try:
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProjectError("Message text exceeds the 64 KiB limit")
    except UnicodeEncodeError:
        raise ProjectError("Message text must contain valid UTF-8") from None
    return text


class Discussion:
    def __init__(self, store):
        self.store = store

    def _decode_message(self, row):
        message = _decode_record(row, self.store._project_id, "message", ("context_id",), MAX_TEXT_BYTES * 6 + 2048)
        try:
            _id(message["context_id"])
            _message_text(message["text"])
            if message["role"] not in ("user", "assistant"):
                raise ValueError("invalid informational role")
            if set(message) != {"id", "project_id", "context_id", "role", "text", "created_at"}:
                raise ValueError("invalid message fields")
            return message
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectError(f"Invalid stored project message: {exc}") from None

    def _get_message(self, db, message_id):
        return self._decode_message(db.execute("SELECT * FROM project_messages WHERE id=?", (message_id,)).fetchone())

    def add(self, text, *, message_id, context_id, role="user"):
        _id(message_id)
        _id(context_id)
        text = _message_text(text)
        if role not in ("user", "assistant"):
            raise ProjectError("Message role must be user or assistant")
        request = _digest({"text": text, "context_id": context_id, "role": role})
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT * FROM project_messages WHERE id=?", (message_id,)).fetchone()
            if existing is not None:
                message = self._decode_message(existing)
                if existing["request_sha256"] != request:
                    raise RevisionConflict("Message ID already belongs to a different request")
                return message
            self.store.contexts._get(db, context_id)
            message = {"id": message_id, "project_id": self.store._project_id, "context_id": context_id, "role": role,
                       "text": text, "created_at": datetime.now(timezone.utc).isoformat()}
            db.execute("INSERT INTO project_messages VALUES (?, ?, ?, ?, ?, ?)",
                       (message_id, self.store._project_id, context_id, _encode(message).decode("utf-8"), request,
                        _digest({"payload": message, "request_sha256": request})))
            return message

    def get(self, message_id):
        _id(message_id)
        with self.store._connect() as db:
            _require(db)
            return self._get_message(db, message_id)

    def list(self, *, offset=0, limit=100):
        _pagination(offset, limit)
        with self.store._connect() as db:
            _require(db)
            rows = db.execute("SELECT * FROM project_messages ORDER BY rowid LIMIT ? OFFSET ?", (limit + 1, offset)).fetchall()
            messages = []
            for row in rows[:limit]:
                message = self._decode_message(row)
                message["text_bytes"] = len(message.pop("text").encode("utf-8"))
                messages.append(message)
            return {"messages": messages, "next_offset": offset + limit if len(rows) > limit else None}

    def _decode_proposal(self, db, row, ancestors=None):
        proposal = _decode_record(row, self.store._project_id, "proposal",
                                  ("message_id", "context_id", "draft_id", "base_revision"), 2048)
        try:
            for key in ("message_id", "context_id", "draft_id"):
                _id(proposal[key])
            _expected_revision(proposal["base_revision"])
            if set(proposal) != {"id", "project_id", "message_id", "context_id", "draft_id", "base_revision", "created_at"}:
                raise ValueError("invalid proposal fields")
            # The independently immutable ancestors must still describe the same
            # provenance. Their checksums are verified in this one read snapshot;
            # draft terminal status is deliberately not part of this identity.
            if ancestors is None:
                ancestors = {}
            def ancestor(kind, identity, read):
                key = (kind, identity)
                if key not in ancestors:
                    ancestors[key] = read()
                return ancestors[key]
            message = ancestor("message", proposal["message_id"], lambda: self._get_message(db, proposal["message_id"]))
            context = ancestor("context", proposal["context_id"], lambda: self.store.contexts._get(db, proposal["context_id"]))
            draft = ancestor("draft", proposal["draft_id"], lambda: self.store.drafts._decode(
                db.execute("SELECT * FROM project_drafts WHERE id=?", (proposal["draft_id"],)).fetchone()))
            if (message["context_id"] != context["id"]
                    or proposal["base_revision"] != context["source_revision"]
                    or proposal["base_revision"] != draft["base_revision"]):
                raise ValueError("linked provenance identity mismatch")
            return proposal
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectError(f"Invalid stored project proposal: {exc}") from None

    def link_draft(self, message_id, draft_id, *, proposal_id):
        _id(message_id)
        _id(draft_id)
        _id(proposal_id)
        request = _digest({"message_id": message_id, "draft_id": draft_id})
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT * FROM project_proposals WHERE id=?", (proposal_id,)).fetchone()
            if existing is not None:
                proposal = self._decode_proposal(db, existing)
                if existing["request_sha256"] != request:
                    raise RevisionConflict("Proposal ID already belongs to a different request")
                return proposal
            if db.execute("SELECT id FROM project_proposals WHERE draft_id=?", (draft_id,)).fetchone() is not None:
                raise RevisionConflict("Draft already has a provenance link")
            message = self._get_message(db, message_id)
            context = self.store.contexts._get(db, message["context_id"])
            draft = self.store.drafts._decode(db.execute("SELECT * FROM project_drafts WHERE id=?", (draft_id,)).fetchone())
            if draft["base_revision"] != context["source_revision"]:
                raise RevisionConflict("Draft base revision does not match the message context")
            proposal = {"id": proposal_id, "project_id": self.store._project_id, "message_id": message_id,
                        "context_id": context["id"], "draft_id": draft_id, "base_revision": draft["base_revision"],
                        "created_at": datetime.now(timezone.utc).isoformat()}
            db.execute("INSERT INTO project_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (proposal_id, self.store._project_id, message_id, context["id"], draft_id, draft["base_revision"],
                        _encode(proposal).decode("utf-8"), request, _digest({"payload": proposal, "request_sha256": request})))
            return proposal

    def proposals(self, *, offset=0, limit=100, draft_id=None):
        _pagination(offset, limit)
        if draft_id is not None:
            _id(draft_id)
        with self.store._connect() as db:
            _require(db)
            where, parameters = (" WHERE draft_id=?", (draft_id,)) if draft_id is not None else ("", ())
            rows = db.execute("SELECT * FROM project_proposals" + where + " ORDER BY rowid LIMIT ? OFFSET ?",
                              (*parameters, limit + 1, offset)).fetchall()
            ancestors = {}  # Shared immutable context/message decoded once per read transaction.
            return {"proposals": [self._decode_proposal(db, row, ancestors) for row in rows[:limit]],
                    "next_offset": offset + limit if len(rows) > limit else None}
