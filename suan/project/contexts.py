"""Explicit, immutable, bounded project context; capture never evaluates or executes.

Only selected cells and their saved evaluation observations are read. Dependency
values, file contents and whole project snapshots are deliberately not fetched.
"""

from datetime import datetime, timezone
import hashlib
import json
import re

from .expressions import ENGINE_VERSION, EvaluationError, Value, check_target
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id, _text, _version
from . import archive


MAX_VALUE_BYTES = 16 * 1024
MAX_CONTEXT_BYTES = 256 * 1024


def _encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProjectError(f"Expected finite UTF-8 JSON data: {exc}") from None


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _require(db):
    if _version(db) < 7:
        raise UnsupportedProjectFormat("Upgrade this project to format 7 before using contexts or discussion")


def _pagination(offset, limit):
    if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
        raise ProjectError("Pagination requires offset >= 0 and limit between 1 and 100")


def _decode_record(row, project_id, label, columns, maximum):
    if row is None:
        raise ProjectError(f"Project {label} not found")
    try:
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict) or len(_encode(payload)) > maximum:
            raise ValueError("invalid payload or size")
        _id(payload["id"])
        if payload["project_id"] != project_id or any(payload[key] != row[key] for key in ("id", "project_id", *columns)):
            raise ValueError("identity mismatch")
        datetime.fromisoformat(payload["created_at"])
        if not isinstance(row["request_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", row["request_sha256"]):
            raise ValueError("invalid request checksum")
        if _digest({"payload": payload, "request_sha256": row["request_sha256"]}) != row["sha256"]:
            raise ValueError("checksum mismatch")
        return payload
    except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise ProjectError(f"Invalid stored project {label}: {exc}") from None


def _ids(values, label, maximum):
    if not isinstance(values, list) or not 1 <= len(values) <= maximum:
        raise ProjectError(f"{label} must contain 1 to {maximum} explicit IDs")
    for value in values:
        _id(value)
    if len(set(values)) != len(values):
        raise ProjectError(f"{label} must contain distinct IDs")
    return list(values)


def _valid_evaluation(value, field, revision):
    if not isinstance(value, dict) or type(value.get("engine_version")) is not int or value["engine_version"] != ENGINE_VERSION:
        return False
    if type(value.get("evaluated_revision")) is not int or not 0 <= value["evaluated_revision"] <= revision:
        return False
    if value.get("state") == "ok":
        if "value" not in value or "unit" not in value or (value["unit"] is not None and not isinstance(value["unit"], str)):
            return False
        try:
            check_target(Value(value["value"], value["unit"]), field["type"], field["unit"])
            return True
        except EvaluationError:
            return False
    error = value.get("error")
    if value.get("state") != "error" or not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
        return False
    source = error.get("source")
    return "source" not in error or (isinstance(source, dict) and set(source) == {"record_id", "field_id"}
                                     and all(isinstance(item, str) for item in source.values()))


def _part(db, relation, column, record_id, field, revision):
    # SQL identifiers are internal constants; stream oversized values through a
    # digest instead of materializing their potentially large JSON arrays/text.
    key = (record_id, field["id"])
    row = db.execute(f"SELECT length(CAST({column} AS BLOB)) FROM {relation} WHERE record_id=? AND field_id=?", key).fetchone()
    if row is None:
        if relation != "evaluations":
            return None
        return {"state": "omitted", "reason": "evaluation_unavailable", "size_bytes": 0,
                "sha256": hashlib.sha256(b"").hexdigest()}
    size = row[0]
    digest = hashlib.sha256()
    raw = bytearray()
    for start in range(1, size + 1, 65536):
        chunk = db.execute(f"SELECT substr(CAST({column} AS BLOB), ?, 65536) FROM {relation} WHERE record_id=? AND field_id=?",
                           (start, *key)).fetchone()[0]
        digest.update(chunk)
        if size <= MAX_VALUE_BYTES:
            raw.extend(chunk)
    omitted = {"state": "omitted", "reason": "value_limit", "size_bytes": size, "sha256": digest.hexdigest()}
    if size > MAX_VALUE_BYTES:
        return omitted
    try:
        value = json.loads(raw)
        _encode(value)
    except (TypeError, ValueError, RecursionError) as exc:
        if relation != "evaluations":
            raise ProjectError(f"Invalid selected project value: {exc}") from None
        value = None
    if relation == "evaluations" and not _valid_evaluation(value, field, revision):
        return {**omitted, "reason": "evaluation_unavailable"}
    return {"state": "included", "value": value}


class Contexts:
    def __init__(self, store):
        self.store = store

    def _decode(self, row):
        context = _decode_record(row, self.store._project_id, "context", ("source_revision",), MAX_CONTEXT_BYTES)
        try:
            _text(context["title"], "Context title")
            _expected_revision(context["source_revision"])
            selection = context["selection"]
            _id(selection["table_id"])
            records, fields = _ids(selection["record_ids"], "record_ids", 100), _ids(selection["field_ids"], "field_ids", 64)
            if len(records) * len(fields) > 1000:
                raise ValueError("too many cells")
            content = context["content"]
            if type(content["size_bytes"]) is not int or content["size_bytes"] < 0 or not re.fullmatch(r"[a-f0-9]{64}", content["sha256"]):
                raise ValueError("invalid content identity")
            if content["state"] == "included":
                encoded = _encode(content["value"])
                if len(encoded) != content["size_bytes"] or hashlib.sha256(encoded).hexdigest() != content["sha256"]:
                    raise ValueError("content checksum mismatch")
            elif content["state"] != "omitted" or content.get("reason") != "context_limit" or "value" in content:
                raise ValueError("invalid content state")
            return context
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise ProjectError(f"Invalid stored project context: {exc}") from None

    def _get(self, db, context_id):
        return self._decode(db.execute("SELECT * FROM project_contexts WHERE id=?", (context_id,)).fetchone())

    def capture(self, table_id, record_ids, field_ids, *, expected_revision, title, context_id):
        _id(context_id)
        _id(table_id)
        _expected_revision(expected_revision)
        title = _text(title, "Context title")
        records, fields = _ids(record_ids, "record_ids", 100), _ids(field_ids, "field_ids", 64)
        if len(records) * len(fields) > 1000:
            raise ProjectError("Select at most 1000 cells per context")
        selection = {"table_id": table_id, "record_ids": records, "field_ids": fields}
        request = _digest({"selection": selection, "title": title, "source_revision": expected_revision})
        with self.store._connect(write=True) as db:
            _require(db)
            existing = db.execute("SELECT * FROM project_contexts WHERE id=?", (context_id,)).fetchone()
            if existing is not None:
                value = self._decode(existing)
                if existing["request_sha256"] != request:
                    raise RevisionConflict("Context ID already belongs to a different request")
                return value
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            table = db.execute("SELECT id, name FROM tables WHERE id=?", (table_id,)).fetchone()
            content = {"table": dict(table) if table else None, "fields": [], "records": []}
            missing = {"table_missing": table is None, "record_ids": [], "field_ids": []}
            for identity in fields:
                field = db.execute("SELECT * FROM fields WHERE id=?", (identity,)).fetchone()
                if field is None:
                    missing["field_ids"].append(identity)
                elif field["table_id"] != table_id:
                    raise ProjectError("Selected field belongs to a different table")
                else:
                    content["fields"].append({key: field[key] for key in ("id", "name", "type", "unit")})
            omitted = 0
            for identity in records:
                record = db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
                if record is None:
                    missing["record_ids"].append(identity)
                    continue
                if record["table_id"] != table_id:
                    raise ProjectError("Selected record belongs to a different table")
                value = {"id": identity, "literals": {}, "definitions": {}, "evaluations": {}}
                for field in content["fields"]:
                    for relation, column, target in (("cells", "value", "literals"), ("definitions", "definition", "definitions"),
                                                     ("evaluations", "result", "evaluations")):
                        if relation == "evaluations" and field["id"] not in value["definitions"]:
                            continue
                        part = _part(db, relation, column, identity, field, revision)
                        if part is not None:
                            value[target][field["id"]] = part
                            omitted += part["state"] == "omitted"
                content["records"].append(value)
            encoded = _encode(content)
            descriptor = {"state": "included", "value": content, "size_bytes": len(encoded),
                          "sha256": hashlib.sha256(encoded).hexdigest()}
            result = {"id": context_id, "project_id": self.store._project_id, "title": title, "source_revision": revision,
                      "created_at": datetime.now(timezone.utc).isoformat(), "selection": selection, "content": descriptor,
                      "diagnostics": missing, "omitted_values": omitted,
                      "limits": {"max_value_bytes": MAX_VALUE_BYTES, "max_context_bytes": MAX_CONTEXT_BYTES}}
            if len(_encode(result)) > MAX_CONTEXT_BYTES:
                descriptor.pop("value")
                descriptor.update(state="omitted", reason="context_limit")
            serialized = _encode(result)
            if len(serialized) > MAX_CONTEXT_BYTES:
                raise ProjectError("Context selection metadata exceeds the 256 KiB limit")
            db.execute("INSERT INTO project_contexts VALUES (?, ?, ?, ?, ?, ?)",
                       (context_id, self.store._project_id, revision, serialized.decode("utf-8"), request,
                        _digest({"payload": result, "request_sha256": request})))
            return result

    def get(self, context_id):
        _id(context_id)
        with self.store._connect() as db:
            _require(db)
            return self._get(db, context_id)

    def list(self, *, offset=0, limit=100, archived=None):
        _pagination(offset, limit)
        with self.store._connect() as db:
            _require(db)
            where, extra = archive.where(db, "context", archived)
            rows = db.execute("SELECT * FROM project_contexts" + where + " ORDER BY rowid LIMIT ? OFFSET ?", (*extra, limit + 1, offset)).fetchall()
            contexts = []
            for row in rows[:limit]:
                context = self._decode(row)
                context["content"].pop("value", None)
                contexts.append(context)
            return {"contexts": contexts, "next_offset": offset + limit if len(rows) > limit else None}
