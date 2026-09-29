"""Durable text-request identities and an atomic, metadata-only execution journal.

There is no provider, network client, credential lookup or implicit executor here.
A trusted local executor must explicitly claim a pending request before sending;
opening or reading this journal cannot start or recover work.
"""

from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import UUID, uuid5

from .contexts import _digest, _encode, _pagination
from .discussion import _message_text
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _id, _version


PROMPT_VERSION = "stk.text/1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 8192
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
SETTLEMENT_CODES = frozenset({"executor_lost", "adapter_unavailable", "adapter_failed", "response_invalid",
                            "cancel_confirmed", "cancel_unconfirmed", "transport_uncertain", "dispatch_failed",
                            "local_save_failed"})
_SETTLEMENTS = {"failed": frozenset({"adapter_unavailable", "adapter_failed", "response_invalid", "dispatch_failed"}),
                "uncertain": frozenset({"executor_lost", "cancel_unconfirmed", "transport_uncertain", "local_save_failed"}),
                "cancelled": frozenset({"cancel_confirmed", "cancelled_before_start"})}
_STATUSES = frozenset({"pending", "running", "completed", "failed", "cancelled", "uncertain"})
_IDENTITY = ("id", "project_id", "context_id", "message_id", "assistant_message_id", "source_revision",
             "configuration", "prompt_version", "input_sha256", "created_at")
_PRIVATE = ("context_sha256", "message_sha256")
_STATE = ("status", "cancel_requested", "executor_id", "updated_at", "error_code", "result")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _identifier(value, label):
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value) or "//" in value:
        raise ProjectError(f"{label} must be a safe identifier of 1 to 128 ASCII characters")
    return value


def _configuration(value):
    if not isinstance(value, dict) or not {"adapter", "model"} <= value.keys() or value.keys() - {
            "adapter", "model", "temperature", "max_output_tokens"}:
        raise ProjectError("Request configuration requires adapter and model, with optional temperature and max_output_tokens")
    result = {key: _identifier(value[key], key) for key in ("adapter", "model")}
    maximum = value.get("max_output_tokens", 4096)
    if type(maximum) is not int or not 1 <= maximum <= 32768:
        raise ProjectError("max_output_tokens must be an integer between 1 and 32768")
    result["max_output_tokens"] = maximum
    if "temperature" in value:
        temperature = value["temperature"]
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2:
            raise ProjectError("temperature must be a finite number between 0 and 2")
        result["temperature"] = float(temperature)
    return result


def _validate_metadata(value):
    """Only bounded, noncredential observations can accompany a complete response."""
    if value is None:
        return {}
    if not isinstance(value, dict) or value.keys() - {"model", "remote_request_id", "input_tokens", "output_tokens"}:
        raise ProjectError("Invalid response metadata fields")
    result = {}
    for key, item in value.items():
        if key in ("model", "remote_request_id"):
            result[key] = _identifier(item, key)
        else:
            if type(item) is not int or not 0 <= item < 2**63:
                raise ProjectError("Response token counts must be nonnegative 64-bit integers")
            result[key] = item
    return result


def _text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require(db):
    if _version(db) < 8:
        raise UnsupportedProjectFormat("Upgrade this project to format 8 before using model request records")


def _assistant_id(request_id, project_id):
    return str(uuid5(UUID(request_id), project_id + ":assistant"))


class Requests:
    def __init__(self, store):
        self.store = store

    def _input(self, db, identity, ancestors=None):
        if ancestors is None:
            ancestors = {}
        def ancestor(kind, key, read):
            marker = (kind, key)
            if marker not in ancestors:
                ancestors[marker] = read()
            return ancestors[marker]
        context = ancestor("context", identity["context_id"],
                           lambda: self.store.contexts._get(db, identity["context_id"]))
        message = ancestor("message", identity["message_id"],
                           lambda: self.store.discussion._get_message(db, identity["message_id"]))
        result = {"context": context, "message": message, "configuration": identity["configuration"],
                  "prompt_version": identity["prompt_version"]}
        if (message["role"] != "user" or message["context_id"] != context["id"]
                or context["source_revision"] != identity["source_revision"]
                or _digest(context) != identity["context_sha256"]
                or _digest(message) != identity["message_sha256"]
                or _digest(result) != identity["input_sha256"] or len(_encode(result)) > MAX_INPUT_BYTES):
            raise ProjectError("Invalid stored project request: input provenance mismatch")
        return result

    def _decode(self, db, row, ancestors=None):
        if row is None:
            raise ProjectError("Project request not found")
        try:
            if (not isinstance(row["payload"], str) or not isinstance(row["state"], str)
                    or len(row["payload"].encode("utf-8")) > MAX_REQUEST_BYTES
                    or len(row["state"].encode("utf-8")) > MAX_REQUEST_BYTES):
                raise ValueError("invalid payload size")
            identity, state = json.loads(row["payload"]), json.loads(row["state"])
            if not isinstance(identity, dict) or set(identity) != set(_IDENTITY + _PRIVATE):
                raise ValueError("invalid identity fields")
            if not isinstance(state, dict) or set(state) != set(_STATE):
                raise ValueError("invalid state fields")
            for key in ("id", "project_id", "context_id", "message_id", "assistant_message_id"):
                _id(identity[key])
                if identity[key] != row[key]:
                    raise ValueError("identity column mismatch")
            if identity["project_id"] != self.store._project_id:
                raise ValueError("project identity mismatch")
            if identity["assistant_message_id"] != _assistant_id(identity["id"], identity["project_id"]):
                raise ValueError("assistant identity mismatch")
            if type(identity["source_revision"]) is not int or not 0 <= identity["source_revision"] < 2**63:
                raise ValueError("invalid source revision")
            if identity["configuration"] != _configuration(identity["configuration"]) or identity["prompt_version"] != PROMPT_VERSION:
                raise ValueError("invalid input configuration")
            for key in ("input_sha256", "context_sha256", "message_sha256"):
                if not isinstance(identity[key], str) or not _HASH.fullmatch(identity[key]):
                    raise ValueError("invalid input checksum")
            request_hash = _digest({"message_id": identity["message_id"], "configuration": identity["configuration"]})
            if request_hash != row["request_sha256"] or _digest({"payload": identity, "request_sha256": request_hash}) != row["sha256"]:
                raise ValueError("identity checksum mismatch")
            if _digest({"id": identity["id"], "sha256": row["sha256"], "state": state}) != row["state_sha256"]:
                raise ValueError("state checksum mismatch")
            datetime.fromisoformat(identity["created_at"])
            datetime.fromisoformat(state["updated_at"])
            status = state["status"]
            if not isinstance(status, str) or status not in _STATUSES or status != row["status"] or type(state["cancel_requested"]) is not bool:
                raise ValueError("invalid state")
            owner, code, result = state["executor_id"], state["error_code"], state["result"]
            if owner is not None:
                _id(owner)
            if code is not None and (not isinstance(code, str) or code not in SETTLEMENT_CODES | {"cancelled_before_start"}):
                raise ValueError("invalid error code")
            if status == "pending":
                valid = owner is None and not state["cancel_requested"] and code is None and result is None
            elif status == "running":
                valid = owner is not None and not state["cancel_requested"] and code is None and result is None
            elif status == "completed":
                valid = owner is not None and code is None and isinstance(result, dict) and set(result) == {"message_id", "text_sha256", "metadata"}
                if valid:
                    assistant = self.store.discussion._get_message(db, identity["assistant_message_id"])
                    valid = (result["message_id"] == assistant["id"] and assistant["context_id"] == identity["context_id"]
                             and assistant["role"] == "assistant" and result["text_sha256"] == _text_hash(assistant["text"])
                             and result["metadata"] == _validate_metadata(result["metadata"]))
            else:
                valid = result is None and code in _SETTLEMENTS[status]
                if code == "cancelled_before_start":
                    valid = valid and owner is None
                else:
                    valid = valid and owner is not None
                if status == "cancelled":
                    valid = valid and state["cancel_requested"]
                if code == "cancel_unconfirmed":
                    valid = valid and state["cancel_requested"]
            if not valid:
                raise ValueError("invalid terminal or execution state")
            self._input(db, identity, ancestors)
            return identity, state
        except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
            raise ProjectError(f"Invalid stored project request: {exc}") from None

    @staticmethod
    def _public(identity, state):
        return {**{key: identity[key] for key in _IDENTITY}, **state}

    def _read(self, db, request_id, ancestors=None):
        return self._decode(db, db.execute("SELECT * FROM project_requests WHERE id=?", (request_id,)).fetchone(), ancestors)

    def _update(self, db, identity, state, **changes):
        state = {**state, **changes, "updated_at": _now()}
        identity_hash = db.execute("SELECT sha256 FROM project_requests WHERE id=?", (identity["id"],)).fetchone()[0]
        digest = _digest({"id": identity["id"], "sha256": identity_hash, "state": state})
        db.execute("UPDATE project_requests SET status=?, state=?, state_sha256=? WHERE id=?",
                   (state["status"], _encode(state).decode("utf-8"), digest, identity["id"]))
        return self._public(identity, state)

    def create(self, message_id, *, request_id, configuration):
        _id(message_id)
        _id(request_id)
        configuration = _configuration(configuration)
        request_hash = _digest({"message_id": message_id, "configuration": configuration})
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT * FROM project_requests WHERE id=?", (request_id,)).fetchone()
            if existing is not None:
                identity, state = self._decode(db, existing)
                if request_hash != existing["request_sha256"]:
                    raise RevisionConflict("Request ID already belongs to a different input")
                return self._public(identity, state)
            message = self.store.discussion._get_message(db, message_id)
            if message["role"] != "user":
                raise ProjectError("A text request must reference a user message")
            context = self.store.contexts._get(db, message["context_id"])
            selected = {"context": context, "message": message, "configuration": configuration, "prompt_version": PROMPT_VERSION}
            if len(_encode(selected)) > MAX_INPUT_BYTES:
                raise ProjectError("Request input exceeds the 1 MiB limit")
            assistant_id = _assistant_id(request_id, self.store._project_id)
            if db.execute("SELECT id FROM project_messages WHERE id=?", (assistant_id,)).fetchone() is not None:
                raise RevisionConflict("Request assistant message ID is already occupied")
            now = _now()
            identity = {"id": request_id, "project_id": self.store._project_id, "context_id": context["id"],
                        "message_id": message_id, "assistant_message_id": assistant_id,
                        "source_revision": context["source_revision"], "configuration": configuration,
                        "prompt_version": PROMPT_VERSION, "input_sha256": _digest(selected), "created_at": now,
                        "context_sha256": _digest(context), "message_sha256": _digest(message)}
            state = {"status": "pending", "cancel_requested": False, "executor_id": None, "updated_at": now,
                     "error_code": None, "result": None}
            digest = _digest({"payload": identity, "request_sha256": request_hash})
            state_digest = _digest({"id": request_id, "sha256": digest, "state": state})
            db.execute("INSERT INTO project_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (request_id, self.store._project_id, context["id"], message_id, assistant_id,
                        _encode(identity).decode("utf-8"), request_hash, digest, "pending",
                        _encode(state).decode("utf-8"), state_digest))
            return self._public(identity, state)

    def get(self, request_id):
        _id(request_id)
        with self.store._connect() as db:
            _require(db)
            return self._public(*self._read(db, request_id))

    def list(self, *, offset=0, limit=100):
        _pagination(offset, limit)
        with self.store._connect() as db:
            _require(db)
            rows = db.execute("SELECT * FROM project_requests ORDER BY rowid LIMIT ? OFFSET ?", (limit + 1, offset)).fetchall()
            ancestors = {}
            return {"requests": [self._public(*self._decode(db, row, ancestors)) for row in rows[:limit]],
                    "next_offset": offset + limit if len(rows) > limit else None}

    def input(self, request_id):
        _id(request_id)
        with self.store._connect() as db:
            _require(db)
            ancestors = {}
            identity, _ = self._read(db, request_id, ancestors)
            return self._input(db, identity, ancestors)

    def _claim(self, request_id, *, executor_id):
        _id(request_id)
        _id(executor_id)
        with self.store._connect(write=True) as db:
            _require(db)
            identity, state = self._read(db, request_id)
            if state["status"] != "pending":
                return self._public(identity, state), False
            return self._update(db, identity, state, status="running", executor_id=executor_id), True

    def cancel(self, request_id):
        _id(request_id)
        with self.store._connect(write=True) as db:
            _require(db)
            identity, state = self._read(db, request_id)
            if state["status"] in ("completed", "failed", "cancelled") or state["cancel_requested"]:
                return self._public(identity, state)
            if state["status"] == "pending":
                return self._update(db, identity, state, status="cancelled", cancel_requested=True,
                                    error_code="cancelled_before_start")
            return self._update(db, identity, state, status="uncertain", cancel_requested=True,
                                error_code="cancel_unconfirmed")

    @staticmethod
    def _owner(state, executor_id):
        if state["executor_id"] != executor_id:
            raise RevisionConflict("Request belongs to another execution attempt")

    def _complete(self, request_id, *, executor_id, text, metadata=None):
        _id(request_id)
        _id(executor_id)
        text = _message_text(text)
        metadata = _validate_metadata(metadata)
        with self.store._connect(write=True) as db:
            _require(db)
            identity, state = self._read(db, request_id)
            self._owner(state, executor_id)
            result = {"message_id": identity["assistant_message_id"], "text_sha256": _text_hash(text), "metadata": metadata}
            if state["status"] == "completed":
                if state["result"] != result:
                    raise RevisionConflict("Request already has a different complete result")
                return self._public(identity, state)
            if state["status"] in ("cancelled", "failed"):
                return self._public(identity, state)
            if state["status"] not in ("running", "uncertain"):
                raise RevisionConflict("Request has not entered execution")
            self.store.discussion._add(db, text, message_id=identity["assistant_message_id"],
                                       context_id=identity["context_id"], role="assistant", request_id=request_id)
            return self._update(db, identity, state, status="completed", error_code=None, result=result)

    def _settle(self, request_id, *, executor_id, status, code):
        _id(request_id)
        _id(executor_id)
        if (status not in ("failed", "uncertain", "cancelled") or not isinstance(code, str)
                or code not in SETTLEMENT_CODES or code not in _SETTLEMENTS[status]):
            raise ProjectError("Invalid request settlement status or safe error code")
        with self.store._connect(write=True) as db:
            _require(db)
            identity, state = self._read(db, request_id)
            self._owner(state, executor_id)
            if state["status"] in ("completed", "failed", "cancelled"):
                return self._public(identity, state)
            if state["status"] not in ("running", "uncertain"):
                raise RevisionConflict("Request has not entered execution")
            if code == "cancel_unconfirmed" and not state["cancel_requested"]:
                raise ProjectError("Unconfirmed cancellation requires a recorded cancellation intent")
            if state["status"] == status and state["error_code"] == code:
                return self._public(identity, state)
            return self._update(db, identity, state, status=status, error_code=code,
                                cancel_requested=state["cancel_requested"] or status == "cancelled")
