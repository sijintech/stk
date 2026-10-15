"""Versioned project field semantics. Validation never opens resources or executes code."""
from datetime import date
import json
import re
from urllib.parse import urlsplit

CORE_TYPES = {"text", "integer", "number", "boolean", "json"}
FIELD_TYPES = CORE_TYPES | {"date", "url", "single_select", "multi_select", "object"}
OBJECT_KINDS = {"record", "file", "snapshot_file", "analysis", "simulation", "workflow"}


def options(kind, value=None):
    from .store import ProjectError, _id
    from .managed import clone
    if type(kind) is not str or kind not in FIELD_TYPES:
        raise ProjectError("Unsupported field type")
    value = {"version": 1} if value is None else clone(value, "Field options")
    allowed = {"version", "choices"} if kind.endswith("select") else {"version", "kinds"} if kind == "object" else {"version"}
    if type(value) is not dict or set(value) != allowed or type(value.get("version")) is not int or value["version"] != 1:
        raise ProjectError("Field options require exactly the version 1 keys for their type")
    if kind.endswith("select"):
        choices = value["choices"]
        if type(choices) is not list or not 1 <= len(choices) <= 256:
            raise ProjectError("Select fields require 1 to 256 choices")
        seen = set()
        for choice in choices:
            if type(choice) is not dict or set(choice) != {"id", "label", "color"}:
                raise ProjectError("A choice requires id, label and color")
            _id(choice["id"])
            if choice["id"] in seen:
                raise ProjectError("Choice IDs must be unique")
            seen.add(choice["id"])
            if (type(choice["label"]) is not str or not choice["label"].strip() or
                    len(choice["label"]) > 256 or "\0" in choice["label"] or
                    type(choice["color"]) is not str or not re.fullmatch(r"#[0-9a-fA-F]{6}", choice["color"])):
                raise ProjectError("A choice needs a bounded label and #RRGGBB color")
    elif kind == "object":
        kinds = value["kinds"]
        if (type(kinds) is not list or not kinds or any(type(k) is not str or k not in OBJECT_KINDS for k in kinds)
                or len(set(kinds)) != len(kinds)):
            raise ProjectError("Object kinds must be a unique nonempty supported list")
    return value


def reference(value, project_id=None):
    from .store import ProjectError, _id
    if type(value) is not dict or not {"version", "project_id", "kind", "id"} <= value.keys():
        raise ProjectError("An object reference needs version, project_id, kind and id")
    if (type(value["version"]) is not int or value["version"] != 1 or
            type(value["kind"]) is not str or value["kind"] not in OBJECT_KINDS):
        raise ProjectError("Unsupported object reference kind or version")
    allowed = {"version", "project_id", "kind", "id", "source_sha256"}
    if value["kind"] == "record":
        allowed.add("table_id")
        if "table_id" not in value:
            raise ProjectError("A record reference requires table_id")
        _id(value["table_id"])
    elif value["kind"] == "snapshot_file":
        allowed.update({"path", "record_id"})
        if "record_id" in value:
            _id(value["record_id"])
        if not {"path", "source_sha256"} <= value.keys():
            raise ProjectError("A snapshot file reference requires path and source_sha256")
        path = value["path"]
        if (type(path) is not str or not path or len(path) > 4096 or "\\" in path or "\0" in path or
                any(part in {"", ".", ".."} for part in path.split("/")) or path.startswith("/") or ":" in path):
            raise ProjectError("Snapshot paths must be safe relative POSIX paths")
    if value.keys() - allowed:
        raise ProjectError("Unexpected object reference keys")
    _id(value["project_id"])
    _id(value["id"])
    if project_id is not None and value["project_id"] != project_id:
        raise ProjectError("Object references must belong to this project")
    if "source_sha256" in value and (type(value["source_sha256"]) is not str or
                                      not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"])):
        raise ProjectError("Object reference source_sha256 must be a lowercase SHA-256")
    return value


def check(value, kind, config=None, project_id=None):
    from .store import ProjectError, _check_value
    config = options(kind, config)
    if value is None:
        return
    if kind in CORE_TYPES:
        _check_value(value, kind)
    elif kind == "date":
        try:
            if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise ProjectError("Dates must be valid ISO YYYY-MM-DD strings") from None
    elif kind == "url":
        try:
            parsed = urlsplit(value) if (type(value) is str and len(value) <= 4096 and
                not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)) else None
            if not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError
            parsed.port
        except ValueError:
            raise ProjectError("URLs must be absolute http/https addresses without credentials") from None
    elif kind.endswith("select"):
        ids = {choice["id"] for choice in config["choices"]}
        selected = [value] if kind == "single_select" else value
        if (type(selected) is not list or len(selected) > 256 or
                any(type(choice) is not str or choice not in ids for choice in selected) or len(set(selected)) != len(selected)):
            raise ProjectError("Selected choice IDs must exist and be unique")
    else:
        reference(value, project_id)
        if value["kind"] not in config["kinds"]:
            raise ProjectError("Object kind is not permitted by this field")
    # Bound all new type payloads while preserving the original JSON type.
    if kind not in CORE_TYPES and len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 65536:
        raise ProjectError("Typed field value exceeds 64 KiB")


def read_options(db, field_id, kind):
    from .store import ProjectError, _version
    if _version(db) < 14:
        return {"version": 1}
    row = db.execute("SELECT definition FROM field_options WHERE field_id=?", (field_id,)).fetchone()
    try:
        return options(kind, json.loads(row[0]) if row else None)
    except (ValueError, TypeError, RecursionError):
        raise ProjectError("Stored field options are invalid; undo or restore a verified backup") from None
