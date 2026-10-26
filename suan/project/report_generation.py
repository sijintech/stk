"""Explicitly freeze an edited, completed report reply without inventing a file source."""
import hashlib
from uuid import UUID, uuid5

from .contexts import _digest, _encode
from .discussion import _message_text
from .requests import REPORT_PROMPT_VERSION
from .store import ProjectError, RevisionConflict, _expected_revision, _id

DOCUMENT_FORMAT = "stk.report/2"
GENERATION_FORMAT = "stk.report-generation/1"
INPUT_EXPORT = "stk-generation-input.json"
RESPONSE_EXPORT = "stk-generation-response.txt"


def _request(store, db, request_id, *, completed=False):
    ancestors = {}
    identity, state = store.requests._read(db, _id(request_id), ancestors)
    record = store.requests._public(identity, state)
    if record["prompt_version"] != REPORT_PROMPT_VERSION:
        raise ProjectError("Select a dedicated report request")
    if completed and record["status"] != "completed":
        raise ProjectError("Only a complete saved report response can become a report")
    inputs = store.requests._input(db, identity, ancestors)
    response = (store.discussion._get_message(db, record["assistant_message_id"])
                if record["status"] == "completed" else None)
    return record, inputs, response


def request_details(store, request_id):
    from .reports import _revision
    with store._connect() as db:
        record, inputs, response = _request(store, db, request_id)
        return {"revision": _revision(db), "request": record, "input": inputs, "response": response}


def _body(value):
    value = _message_text(value)
    if any(ord(c) < 32 and c not in "\t\r\n" or 127 <= ord(c) <= 159 for c in value):
        raise ProjectError("Report body cannot contain control characters")
    return value


def _generation(record, inputs, response, body):
    return {"format": GENERATION_FORMAT, "request_id": record["id"],
            "message_id": record["message_id"], "assistant_message_id": record["assistant_message_id"],
            "input_sha256": record["input_sha256"], "report_input_sha256": _digest(inputs["report_input"]),
            "response_sha256": record["result"]["text_sha256"],
            "input_revision": inputs["report_input"]["source_revision"],
            "configuration": record["configuration"], "response_metadata": record["result"]["metadata"],
            "edited": body != response["text"], "body": body}


def _entry(request_id, path, body):
    from .reports import _mime, _path
    mime = _mime(_path(path))
    if mime not in ("text/markdown; charset=utf-8", "text/html; charset=utf-8"):
        raise ProjectError("Generated report entries must be Markdown or HTML")
    data = _body(body).encode("utf-8")
    # This identity explicitly denotes a generated entry, never a Files-table record.
    return {"record_id": str(uuid5(UUID(request_id), "stk.report-generated-entry/1")),
            "path": path, "mime": mime, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def validate_manifest(store, db, value):
    from .report_inputs import sources_with_context
    from .reports import MAX_MANIFEST_BYTES, MAX_TOTAL_BYTES, _paths, _provenance, _revision
    keys = {"format", "project_id", "snapshot_id", "snapshot_sha256", "source_revision", "entry_path",
            "assets", "sources", "generation"}
    if (set(value) != keys or value["format"] != DOCUMENT_FORMAT or value["project_id"] != store._project_id or
            len(_encode(value)) > MAX_MANIFEST_BYTES):
        raise ProjectError("Invalid generated report manifest")
    _expected_revision(value["source_revision"])
    if value["source_revision"] > _revision(db):
        raise ProjectError("Generated report revision is newer than this project")
    generation = value["generation"]
    if type(generation) is not dict:
        raise ProjectError("Invalid report generation provenance")
    record, inputs, response = _request(store, db, generation.get("request_id"), completed=True)
    body = _body(generation.get("body"))
    frozen = inputs["report_input"]
    entry = _entry(record["id"], value["entry_path"], body)
    sources = sources_with_context(inputs["context"], frozen)
    if (_encode(generation) != _encode(_generation(record, inputs, response, body)) or
            value["snapshot_id"] != frozen["snapshot_id"] or value["snapshot_sha256"] != frozen["snapshot_sha256"] or
            _encode(value["assets"]) != _encode([entry] + frozen["assets"]) or
            _encode(value["sources"]) != _encode(sources) or
            frozen["source_revision"] > value["source_revision"]):
        raise ProjectError("Generated report differs from its original completed request or edited entry")
    _provenance(sources, store._project_id, value["source_revision"])
    if len({asset["record_id"] for asset in value["assets"]}) != len(value["assets"]):
        raise ProjectError("Generated report asset identities must be distinct")
    _paths([asset["path"] for asset in value["assets"]] + [INPUT_EXPORT, RESPONSE_EXPORT])
    if sum(asset["size"] for asset in value["assets"]) > MAX_TOTAL_BYTES:
        raise ProjectError("Generated report assets exceed 32 MiB")
    return value


def create(store, name, request_id, body, *, report_id, expected_revision, expected_input_sha256,
           expected_response_sha256, entry_path="report.md"):
    from .managed import name as report_name
    from .report_inputs import sources_with_context
    from .reports import MAX_MANIFEST_BYTES, _TABLE, _digest as checksum, _manifest, _read_asset, _revision
    _id(report_id); _id(request_id); _expected_revision(expected_revision)
    checksum(expected_input_sha256); checksum(expected_response_sha256)
    title, body = report_name(name, "Report"), _body(body)
    with store._connect() as db:
        _TABLE.require(db, "reports")
        _revision(db, expected_revision)
        record, inputs, response = _request(store, db, request_id, completed=True)
        if record["input_sha256"] != expected_input_sha256 or record["result"]["text_sha256"] != expected_response_sha256:
            raise RevisionConflict("The selected report request or response differs; reopen the saved response")
        frozen = inputs["report_input"]
        manifest = _manifest(store, db, {"format": DOCUMENT_FORMAT, "project_id": store._project_id,
            "source_revision": expected_revision, "snapshot_id": frozen["snapshot_id"],
            "snapshot_sha256": frozen["snapshot_sha256"], "entry_path": entry_path,
            "assets": [_entry(request_id, entry_path, body)] + frozen["assets"],
            "sources": sources_with_context(inputs["context"], frozen),
            "generation": _generation(record, inputs, response, body)})
        if len(_encode({"name": title, "format": DOCUMENT_FORMAT, "manifest": manifest})) > MAX_MANIFEST_BYTES:
            raise ProjectError("Report metadata exceeds 384 KiB")
    for asset in manifest["assets"][1:]:
        _read_asset(store, asset)
    with store._connect(write=True) as db:
        # Recheck the saved request in the same CAS transaction, never current run observations.
        _manifest(store, db, manifest)
        return _TABLE.write(store, db, report_id, {"name": title, "format": DOCUMENT_FORMAT, "manifest": manifest},
                            expected_revision, create=True, document_format=DOCUMENT_FORMAT)


def exported_evidence(store, manifest):
    with store._connect() as db:
        validate_manifest(store, db, manifest)
        record, inputs, response = _request(store, db, manifest["generation"]["request_id"], completed=True)
        encoded, text = _encode(inputs), response["text"].encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != record["input_sha256"] or hashlib.sha256(text).hexdigest() != record["result"]["text_sha256"]:
            raise ProjectError("Report export generation evidence checksum differs")
        return [(INPUT_EXPORT, encoded), (RESPONSE_EXPORT, text)]
