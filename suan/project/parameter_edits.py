"""Explicit conversion of complete structured replies into ordinary saved drafts.

This module is a bounded data compiler, not a tool runner. A completed request
and its frozen selection supply identity; model text supplies only proposed
scalar values. Neither conversion nor recovery applies edits or invokes a model.
"""

import json
import math
from uuid import UUID, uuid5

from .contexts import MAX_VALUE_BYTES, _digest, _encode
from .discussion import _message_text
from .drafts import _canonical, _commands
from .requests import PARAMETER_EDITS_PROMPT_VERSION, _require
from .store import ProjectError, RevisionConflict, _check_value, _expected_revision, _id


MAX_SUMMARY_CHARS = 4096
SCALAR_FIELD_TYPES = frozenset({"text", "integer", "number", "boolean"})


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object key")
        value[key] = item
    return value


def _integer(value):
    # Bound Python 3.10 integer parsing too; a finite numeric field cannot use
    # an integer with more than 309 decimal digits, regardless of the field type.
    if len(value.lstrip("-")) > 309:
        raise ValueError("oversized integer")
    return int(value)


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite number")
    return result


def _constant(value):
    raise ValueError("nonfinite constant")


def compile_response(text, context):
    """Return only scalar set_cell commands scoped to the immutable context.

    Complete JSON is mandatory. Missing and omitted source values differ from
    captured blank cells, and a literal cannot silently replace a definition.
    """
    _message_text(text)
    try:
        reply = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_constant,
                           parse_int=_integer, parse_float=_number)
    except (TypeError, ValueError, RecursionError):
        raise ProjectError("Parameter proposal must be one complete strict JSON document") from None
    if not isinstance(reply, dict) or set(reply) != {"format", "context_id", "base_revision", "summary", "edits"}:
        raise ProjectError("Parameter proposal requires exactly format, context_id, base_revision, summary and edits")
    if reply["format"] != PARAMETER_EDITS_PROMPT_VERSION:
        raise ProjectError("Unsupported parameter proposal format")
    _id(reply["context_id"])
    _expected_revision(reply["base_revision"])
    if reply["context_id"] != context["id"] or reply["base_revision"] != context["source_revision"]:
        raise RevisionConflict("Parameter proposal does not match its saved context and source revision")
    summary = reply["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > MAX_SUMMARY_CHARS:
        raise ProjectError("Parameter proposal summary must contain 1 to 4096 characters")
    _encode(summary)  # Reject escaped unpaired surrogates, even in explanatory text.
    edits = reply["edits"]
    if not isinstance(edits, list) or not 1 <= len(edits) <= 1000:
        raise ProjectError("Parameter proposal requires between 1 and 1000 edits")
    if context["content"]["state"] != "included":
        raise ProjectError("Parameter proposal requires included context content")
    selection, content = context["selection"], context["content"]["value"]
    if content["table"] is None or content["table"]["id"] != selection["table_id"]:
        raise ProjectError("Parameter proposal context table is missing")
    fields = {field["id"]: field for field in content["fields"]}
    records = {record["id"]: record for record in content["records"]}
    selected_records, selected_fields = set(selection["record_ids"]), set(selection["field_ids"])
    seen, commands = set(), []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"record_id", "field_id", "value"}:
            raise ProjectError("Each parameter edit requires exactly record_id, field_id and value")
        record_id, field_id = _id(edit["record_id"]), _id(edit["field_id"])
        key = (record_id, field_id)
        if key in seen:
            raise ProjectError("Parameter proposal contains a duplicate cell target")
        seen.add(key)
        if record_id not in selected_records or field_id not in selected_fields:
            raise ProjectError("Parameter proposal target is outside the captured selection")
        if record_id not in records or field_id not in fields:
            raise ProjectError("Parameter proposal target is missing from the captured content")
        record, field = records[record_id], fields[field_id]
        if field["type"] not in SCALAR_FIELD_TYPES:
            raise ProjectError("Parameter proposals support only scalar fields")
        if field_id in record["definitions"]:
            raise ProjectError("Parameter proposals cannot replace a formula or reference")
        literal = record["literals"].get(field_id)
        if literal is not None and literal["state"] != "included":
            raise ProjectError("Parameter proposal target value was omitted from the context")
        _check_value(edit["value"], field["type"])
        if len(_encode(edit["value"])) > MAX_VALUE_BYTES:
            raise ProjectError("Parameter proposal value exceeds the 16 KiB limit")
        commands.append({"op": "set_cell", "table_id": selection["table_id"],
                         "record_id": record_id, "field_id": field_id, "value": edit["value"]})
    return commands


def _identities(request):
    namespace = UUID(request["id"])
    prefix = request["project_id"] + ":" + PARAMETER_EDITS_PROMPT_VERSION
    return (str(uuid5(namespace, prefix + ":draft")), str(uuid5(namespace, prefix + ":provenance")))


def _title(request):
    return "Parameter edits: " + request["id"]


def _draft_hash(request, commands):
    return _digest({"commands": commands, "title": _title(request), "base_revision": request["source_revision"]})


def _source(requests, db, identity, state):
    if identity["prompt_version"] != PARAMETER_EDITS_PROMPT_VERSION:
        raise ProjectError("Request did not ask for a structured parameter proposal")
    if state["status"] != "completed":
        raise RevisionConflict("Only a completed saved request can produce a parameter proposal")
    # Requests._read has verified the reserved assistant ID, complete text hash,
    # source hashes and context/project identity in this same database snapshot.
    context = requests.store.contexts._get(db, identity["context_id"])
    assistant = requests.store.discussion._get_message(db, identity["assistant_message_id"])
    commands = compile_response(assistant["text"], context)
    return context, commands


def _existing(requests, db, identity, state, commands=None):
    draft_id, proposal_id = _identities(identity)
    draft_row = db.execute("SELECT * FROM project_drafts WHERE id=?", (draft_id,)).fetchone()
    proposal_row = db.execute("SELECT * FROM project_proposals WHERE id=?", (proposal_id,)).fetchone()
    if draft_row is None and proposal_row is None:
        return None
    if draft_row is None or proposal_row is None:
        raise RevisionConflict("Parameter proposal identity is occupied by an incomplete pair")
    if commands is None:
        _, commands = _source(requests, db, identity, state)
    draft = requests.store.drafts._existing(db, draft_id, _draft_hash(identity, commands))
    proposal = requests.store.discussion._decode_proposal(db, proposal_row)
    if (_canonical(draft["commands"]) != _canonical(commands)
            or draft["base_revision"] != identity["source_revision"] or draft["title"] != _title(identity)
            or proposal["message_id"] != identity["assistant_message_id"]
            or proposal["draft_id"] != draft_id or proposal["context_id"] != identity["context_id"]
            or proposal["base_revision"] != identity["source_revision"]
            or proposal_row["request_sha256"] != _digest({"message_id": identity["assistant_message_id"], "draft_id": draft_id})):
        raise RevisionConflict("Parameter proposal identity belongs to a different source or edit")
    return {"request_id": identity["id"], "draft": draft, "proposal": proposal}


def _current(db, context, commands, expected_revision):
    revision = db.execute("SELECT revision FROM project").fetchone()[0]
    if revision != expected_revision:
        raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
    fields = {field["id"]: field for field in context["content"]["value"]["fields"]}
    for command in commands:
        field = db.execute("SELECT * FROM fields WHERE id=?", (command["field_id"],)).fetchone()
        record = db.execute("SELECT table_id FROM records WHERE id=?", (command["record_id"],)).fetchone()
        frozen = fields[command["field_id"]]
        if (field is None or record is None or field["table_id"] != command["table_id"]
                or record["table_id"] != command["table_id"]
                or field["type"] != frozen["type"] or field["unit"] != frozen["unit"]):
            raise RevisionConflict("Parameter target no longer matches the captured field and table")
        if db.execute("SELECT 1 FROM definitions WHERE record_id=? AND field_id=?",
                      (command["record_id"], command["field_id"])).fetchone() is not None:
            raise RevisionConflict("Parameter target is now a formula or reference")


def edit_proposal(requests, request_id):
    _id(request_id)
    with requests.store._connect() as db:
        _require(db)
        identity, state = requests._read(db, request_id)
        return _existing(requests, db, identity, state) or {"request_id": request_id, "draft": None, "proposal": None}


def propose_edits(requests, request_id, *, expected_revision):
    _id(request_id)
    _expected_revision(expected_revision)
    store = requests.store
    with store._connect() as db:
        _require(db)
        identity, state = requests._read(db, request_id)
        if expected_revision != identity["source_revision"]:
            raise RevisionConflict("Expected revision must match the request's original source revision")
        context, commands = _source(requests, db, identity, state)
        source_result = state["result"]
        existing = _existing(requests, db, identity, state, commands)
        if existing is not None:
            return {**existing, "replayed": True}
        _current(db, context, commands, expected_revision)
    try:
        preview = store.preview(commands, expected_revision=expected_revision)
    except RevisionConflict:
        # A concurrent identical conversion can already have been applied while
        # this caller awaited preview. Recover its terminal pair, never rebase.
        with store._connect() as db:
            _require(db)
            recovered_identity, recovered_state = requests._read(db, request_id)
            if recovered_identity != identity or recovered_state["result"] != source_result:
                raise RevisionConflict("Parameter request source changed during preview") from None
            existing = _existing(requests, db, recovered_identity, recovered_state, commands)
            if existing is not None:
                return {**existing, "replayed": True}
        raise
    normalized = _commands(store, preview["commands"], expected_revision)
    if _canonical(normalized) != _canonical(commands):
        raise ProjectError("Parameter preview changed the compiled command identities or values")
    with store._connect(write=True) as db:
        _require(db)
        current_identity, state = requests._read(db, request_id)
        if current_identity != identity or state["result"] != source_result or state["status"] != "completed":
            raise RevisionConflict("Parameter request source changed during preview")
        existing = _existing(requests, db, identity, state, commands)
        if existing is not None:
            return {**existing, "replayed": True}
        _current(db, context, commands, expected_revision)
        draft_id, proposal_id = _identities(identity)
        draft = store.drafts._save_validated(db, normalized, expected_revision=expected_revision,
                                            title=_title(identity), draft_id=draft_id,
                                            request_sha256=_draft_hash(identity, commands))
        proposal = store.discussion._link_draft(db, identity["assistant_message_id"], draft_id,
                                                proposal_id=proposal_id)
        return {"request_id": request_id, "draft": draft, "proposal": proposal, "replayed": False}
