"""Atomic receipts for explicitly identified project edits.

Only successful edits are recorded, in the same SQLite transaction as their data,
revision and undo history. Receipts are not editable state and are never undone
or collected. Reading one observes its original success, not the current model.
"""
from datetime import datetime, timezone
import hashlib
import json
import re

from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id, _version


FORMAT = "stk.project-edit-receipt/1"
MAX_REQUEST_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_OPERATIONS = 10000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_REQUEST_FIELDS = {"project_id", "scope", "operation_id", "expected_revision", "commands"}
_RECEIPT_FIELDS = {"format", "project_id", "scope", "operation_id", "request_sha256", "base_revision",
                   "applied_revision", "commands", "created_at", "sha256"}
_SHA = re.compile(r"[a-f0-9]{64}")


class OperationNotFound(ProjectError):
    """No successful edit receipt exists for this scope and operation ID."""


def _scope(value):
    if (type(value) is not str or not 1 <= len(value) <= 256
            or any(not 0x21 <= ord(character) <= 0x7e for character in value)):
        raise ProjectError("Edit operation scope must be 1–256 printable ASCII bytes without whitespace")
    return value


def _pack(value, maximum, label):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProjectError(f"{label} must be finite valid UTF-8 JSON") from None
    if len(raw) > maximum:
        raise ProjectError(f"{label} exceeds its {maximum}-byte limit")
    return raw


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _strict_json(text, maximum, *, canonical=True):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    def constant(_):
        raise ValueError("nonfinite number")

    if type(text) is not str or len(text.encode("utf-8")) > maximum:
        raise ValueError("invalid JSON size")
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if canonical and _pack(value, maximum, "Stored edit JSON").decode("utf-8") != text:
        raise ValueError("noncanonical JSON")
    return value


class EditOperations:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _require(db):
        if _version(db) < 15:
            raise UnsupportedProjectFormat("Upgrade this project to format 15 before using edit operation receipts")

    def _lookup(self, db, operation_id, scope):
        # Check byte lengths before bringing potentially damaged JSON into Python.
        row = db.execute("""SELECT project_id, base_revision, applied_revision, request_sha256, sha256, created_at,
            length(CAST(request AS BLOB)) AS request_bytes, length(CAST(receipt AS BLOB)) AS receipt_bytes
            FROM project_edit_operations WHERE scope=? AND operation_id=?""", (scope, operation_id)).fetchone()
        if row is None:
            return None
        try:
            if (type(row["request_bytes"]) is not int or not 0 < row["request_bytes"] <= MAX_REQUEST_BYTES
                    or type(row["receipt_bytes"]) is not int or not 0 < row["receipt_bytes"] <= MAX_RECEIPT_BYTES):
                raise ValueError("invalid stored sizes")
            saved = db.execute("SELECT request, receipt FROM project_edit_operations WHERE scope=? AND operation_id=?",
                               (scope, operation_id)).fetchone()
            request = _strict_json(saved["request"], MAX_REQUEST_BYTES)
            receipt = _strict_json(saved["receipt"], MAX_RECEIPT_BYTES)
            if type(request) is not dict or set(request) != _REQUEST_FIELDS:
                raise ValueError("invalid request")
            if type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS:
                raise ValueError("invalid receipt")
            project_id = self.store._project_id
            for value in (request, receipt):
                if (value["project_id"], value["scope"], value["operation_id"]) != (project_id, scope, operation_id):
                    raise ValueError("identity mismatch")
            if row["project_id"] != project_id or receipt["format"] != FORMAT:
                raise ValueError("project or format mismatch")
            base, applied = receipt["base_revision"], receipt["applied_revision"]
            _expected_revision(base)
            _expected_revision(applied)
            if (type(request["expected_revision"]) is not int or request["expected_revision"] != base
                    or applied != base + 1 or (row["base_revision"], row["applied_revision"]) != (base, applied)):
                raise ValueError("revision mismatch")
            if (type(receipt["request_sha256"]) is not str or not _SHA.fullmatch(receipt["request_sha256"])
                    or receipt["request_sha256"] != row["request_sha256"]
                    or receipt["request_sha256"] != _digest(saved["request"].encode("utf-8"))):
                raise ValueError("request digest mismatch")
            if (type(receipt["sha256"]) is not str or not _SHA.fullmatch(receipt["sha256"])
                    or receipt["sha256"] != row["sha256"] or receipt["sha256"] != _digest(_pack(
                        {key: value for key, value in receipt.items() if key != "sha256"},
                        MAX_RECEIPT_BYTES, "Stored edit receipt"))):
                raise ValueError("receipt digest mismatch")
            created = receipt["created_at"]
            if (type(created) is not str or not 1 <= len(created) <= 64 or created != row["created_at"]
                    or datetime.fromisoformat(created).utcoffset() is None):
                raise ValueError("invalid creation time")
            self.store._prepare_commands(request["commands"], base)
            normalized = self.store._prepare_commands(receipt["commands"], base)
            for command in normalized:
                if not isinstance(command, dict):
                    raise ValueError("invalid command")
                if command.get("op") in {"create_table", "add_field", "add_record"}:
                    _id(command.get("id"))
            history_size = db.execute("SELECT length(CAST(commands AS BLOB)) FROM changes WHERE revision=?",
                                      (applied,)).fetchone()
            if (history_size is None or type(history_size[0]) is not int
                    or not 0 < history_size[0] <= MAX_RECEIPT_BYTES):
                raise ValueError("invalid edit history size")
            history = db.execute("SELECT commands FROM changes WHERE revision=?", (applied,)).fetchone()
            # Existing history uses store._json's whitespace, not this receipt's
            # compact encoding. It must still reject duplicate and nonfinite JSON.
            commands = _strict_json(history["commands"], MAX_RECEIPT_BYTES, canonical=False)
            if (_pack(commands, MAX_RECEIPT_BYTES, "Edit history")
                    != _pack(normalized, MAX_RECEIPT_BYTES, "Stored commands")):
                raise ValueError("edit history mismatch")
            return receipt
        except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
            raise ProjectError("Stored edit operation receipt is invalid") from None

    def get(self, operation_id, *, scope="local"):
        """Read the original successful receipt; never edit, retry, upgrade or rebase."""
        operation_id, scope = _id(operation_id), _scope(scope)
        with self.store._connect() as db:
            self._require(db)
            receipt = self._lookup(db, operation_id, scope)
            if receipt is None:
                raise OperationNotFound("Project edit operation not found")
            return receipt

    def apply_once(self, commands, *, operation_id, expected_revision, scope="local"):
        """Explicitly apply once at the original CAS revision, or return that same success.

        ``scope`` is supplied by the trusted adapter, not a remote request body.
        It must remain stable across sessions. The original request is hashed before
        the store assigns object UUIDs or normalizes command options.
        """
        operation_id, scope = _id(operation_id), _scope(scope)
        commands = self.store._prepare_commands(commands, expected_revision)
        request = {"project_id": self.store._project_id, "scope": scope, "operation_id": operation_id,
                   "expected_revision": expected_revision, "commands": commands}
        original = _pack(request, MAX_REQUEST_BYTES, "Edit operation request")
        request_sha256 = _digest(original)
        with self.store._connect(write=True) as db:
            self._require(db)
            existing = self._lookup(db, operation_id, scope)
            if existing is not None:
                if existing["request_sha256"] != request_sha256:
                    raise RevisionConflict("Operation ID already belongs to a different request")
                return {"receipt": existing, "replayed": True}
            count, total = db.execute("""SELECT count(*), coalesce(sum(
                length(CAST(request AS BLOB)) + length(CAST(receipt AS BLOB))), 0)
                FROM project_edit_operations""").fetchone()
            if count >= MAX_OPERATIONS or total >= MAX_TOTAL_BYTES:
                raise ProjectError("Project edit operation receipt capacity is exhausted")
            result = self.store._apply(db, commands, expected_revision)
            receipt = {"format": FORMAT, "project_id": self.store._project_id, "scope": scope,
                       "operation_id": operation_id, "request_sha256": request_sha256,
                       "base_revision": expected_revision, "applied_revision": result["revision"],
                       "commands": result["commands"], "created_at": datetime.now(timezone.utc).isoformat()}
            receipt["sha256"] = _digest(_pack(receipt, MAX_RECEIPT_BYTES, "Edit operation receipt"))
            packed = _pack(receipt, MAX_RECEIPT_BYTES, "Edit operation receipt")
            if total + len(original) + len(packed) > MAX_TOTAL_BYTES:
                raise ProjectError("Project edit operation receipts exceed their total byte budget")
            db.execute("""INSERT INTO project_edit_operations
                (scope, operation_id, project_id, base_revision, applied_revision,
                 request_sha256, request, receipt, sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (scope, operation_id, self.store._project_id, expected_revision, result["revision"],
                        request_sha256, original.decode("utf-8"), packed.decode("utf-8"),
                        receipt["sha256"], receipt["created_at"]))
            return {"receipt": receipt, "replayed": False}


__all__ = ["EditOperations", "FORMAT", "MAX_OPERATIONS", "MAX_RECEIPT_BYTES", "MAX_REQUEST_BYTES",
           "MAX_TOTAL_BYTES", "OperationNotFound"]
