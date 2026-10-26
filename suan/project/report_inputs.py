"""Frozen, explicitly selected inputs for a report request; no file bodies or execution.

The request owns these observations, rather than reading later run state at send time.
Data labels are deliberately checked at send time, independently of this frozen data.
"""
from .contexts import _encode
from .managed import clone
from .store import ProjectError, RevisionConflict, _expected_revision, _id

FORMAT = "stk.report-input/1"
PROMPT_VERSION = "stk.report-draft/1"
MAX_INPUT_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 192 * 1024


def selection(value):
    from .report_generation import INPUT_EXPORT, RESPONSE_EXPORT
    from .reports import _digest as checksum, _path, _paths, _source_selection
    value = clone(value, "Report request selection", max_bytes=32 * 1024)
    keys = {"expected_revision", "sources", "expected_sources_sha256", "snapshot_id", "assets"}
    if type(value) is not dict or set(value) != keys:
        raise ProjectError("Report request selection requires revision, reviewed sources, snapshot and assets")
    _expected_revision(value["expected_revision"])
    _source_selection(value["sources"])
    if value["expected_sources_sha256"] is not None:
        checksum(value["expected_sources_sha256"])
    elif value["sources"]:
        raise ProjectError("Review report sources before preparing a report request")
    if value["snapshot_id"] is not None:
        _id(value["snapshot_id"])
    assets = value["assets"]
    if type(assets) is not list or len(assets) > 63 or (assets and value["snapshot_id"] is None):
        raise ProjectError("Select at most 63 assets from one explicit report snapshot")
    seen = set()
    for asset in assets:
        if type(asset) is not dict or set(asset) != {"record_id", "path"}:
            raise ProjectError("Report request assets require only record_id and virtual path")
        identity = _id(asset["record_id"])
        if identity in seen:
            raise ProjectError("Report request asset identities must be distinct")
        seen.add(identity)
        _path(asset["path"])
    _paths([asset["path"] for asset in assets] + [INPUT_EXPORT, RESPONSE_EXPORT])
    return value


def freeze(store, db, context, selected):
    from .reports import _capture_sources, _hash, _mime, _revision, _snapshot
    _revision(db, selected["expected_revision"])
    sources = _capture_sources(store, db, selected["sources"])
    if (selected["expected_sources_sha256"] is not None and
            _hash(sources) != selected["expected_sources_sha256"]):
        raise RevisionConflict("Report sources changed; review them again before preparing a request")
    snapshot = _snapshot(store, db, selected["snapshot_id"]) if selected["snapshot_id"] else None
    originals = {item["record_id"]: item for item in snapshot["manifest"]["files"]} if snapshot else {}
    assets = []
    for asset in selected["assets"]:
        source = originals.get(asset["record_id"])
        if source is None:
            raise ProjectError("Report request asset is not in its selected snapshot")
        assets.append({**asset, "mime": _mime(source["name"]), "sha256": source["sha256"], "size": source["size"]})
    result = {"format": FORMAT, "project_id": store._project_id, "source_revision": selected["expected_revision"],
              "sources": sources, "snapshot_id": selected["snapshot_id"],
              "snapshot_sha256": snapshot["sha256"] if snapshot else None, "assets": assets}
    validate(store, db, context, result)
    return result


def sources_with_context(context, value):
    from .reports import _hash
    primary = {"kind": "context", "id": context["id"], "project_id": context["project_id"],
               "source_revision": context["source_revision"], "context_sha256": _hash(context), "context": context}
    return [primary] + [source for source in value["sources"]
                        if (source["kind"], source["id"]) != ("context", context["id"])]


def validate_binding(selected, value):
    """Bind frozen observations to the reviewed request intent without rereading runs."""
    from .reports import _hash
    if (_encode({"expected_revision": value["source_revision"], "snapshot_id": value["snapshot_id"],
                 "sources": [{"kind": source["kind"], "id": source["id"]} for source in value["sources"]],
                 "assets": [{"record_id": asset["record_id"], "path": asset["path"]} for asset in value["assets"]]}) !=
            _encode({key: selected[key] for key in ("expected_revision", "snapshot_id", "sources", "assets")}) or
            (selected["expected_sources_sha256"] is not None and
             _hash(value["sources"]) != selected["expected_sources_sha256"])):
        raise ProjectError("Frozen report input differs from the reviewed request selection")


def validate(store, db, context, value):
    from .report_generation import INPUT_EXPORT, RESPONSE_EXPORT
    from .reports import (MAX_ASSET_BYTES, MAX_TOTAL_BYTES, _digest as checksum, _mime,
                          _path, _paths, _provenance, _snapshot)
    keys = {"format", "project_id", "source_revision", "sources", "snapshot_id", "snapshot_sha256", "assets"}
    if (type(value) is not dict or set(value) != keys or value["format"] != FORMAT or
            value["project_id"] != store._project_id or len(_encode(value)) > MAX_INPUT_BYTES):
        raise ProjectError("Invalid or oversized frozen report input")
    _expected_revision(value["source_revision"])
    if context["source_revision"] > value["source_revision"]:
        raise ProjectError("Report context is newer than its frozen request sources")
    # Check the raw list too: deduplication must never conceal a malformed or forged
    # duplicate of the primary context. The primary occupies one of the 16 slots.
    _provenance(value["sources"], store._project_id, value["source_revision"])
    combined = sources_with_context(context, value)
    for source in value["sources"]:
        if (source["kind"], source["id"]) == ("context", context["id"]):
            if _encode(source) != _encode(combined[0]):
                raise ProjectError("Report input's primary context differs from the saved request context")
    _provenance(combined, store._project_id, value["source_revision"])
    # A 64 KiB body may take 128 KiB as JSON (quotes, backslashes and newlines).
    # Leave a further 64 KiB for bounded provenance, entry descriptor and title in
    # the 384 KiB record; reject before a model request can ever be sent.
    if len(_encode({"sources": combined, "assets": value["assets"]})) > MAX_SOURCE_BYTES:
        raise ProjectError("Combined report sources and asset metadata exceed 192 KiB; select fewer sources")
    if value["snapshot_id"] is None:
        if value["snapshot_sha256"] is not None or value["assets"] != []:
            raise ProjectError("Report input assets require their original snapshot")
        return
    _id(value["snapshot_id"])
    snapshot = _snapshot(store, db, value["snapshot_id"])
    if (checksum(value["snapshot_sha256"]) != snapshot["sha256"] or
            snapshot["revision"] > value["source_revision"]):
        raise ProjectError("Report input snapshot identity or revision differs")
    assets = value["assets"]
    if type(assets) is not list or len(assets) > 63:
        raise ProjectError("Report input contains too many assets")
    originals = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
    seen, total = set(), 0
    for asset in assets:
        if type(asset) is not dict or set(asset) != {"record_id", "path", "mime", "sha256", "size"}:
            raise ProjectError("Invalid frozen report input asset")
        identity = _id(asset["record_id"])
        original = originals.get(identity)
        if identity in seen or original is None:
            raise ProjectError("Report input asset is missing or duplicated")
        seen.add(identity)
        if (type(asset["size"]) is not int or not 0 <= asset["size"] <= MAX_ASSET_BYTES or
                asset["size"] != original["size"] or checksum(asset["sha256"]) != original["sha256"] or
                asset["mime"] != _mime(original["name"]) or asset["mime"] != _mime(_path(asset["path"]))):
            raise ProjectError("Report input asset differs from its frozen original")
        total += asset["size"]
        _path(asset["path"])
    if total > MAX_TOTAL_BYTES - 64 * 1024:
        raise ProjectError("Report input assets must leave 64 KiB for the generated entry within 32 MiB")
    _paths([asset["path"] for asset in assets] + [INPUT_EXPORT, RESPONSE_EXPORT])


def external_allowed(store, db, context, value):
    """No run-public label exists; run observations stay on local/internal endpoints.

    Public context and file labels are re-read in this one transaction. A structure-only
    table label never releases its values, and an old public label is not a permission.
    """
    for source in sources_with_context(context, value):
        if source["kind"] != "context":
            return False
        if not store.labels._public(db, "table", source["context"]["selection"]["table_id"]):
            return False
    return all(store.labels._public(db, "file", asset["record_id"]) for asset in value["assets"])
