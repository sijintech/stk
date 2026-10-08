"""Explicit conversion of a complete AI sweep reply into an ordinary saved draft (P2 L1).

The model proposes the *shape* of new rows -- a base row selected in the immutable context and one
to eight axes over selected fields -- and STK compiles it with the same ``plan_sweep`` the manual
sweep generator uses, so an AI sweep and a manual one produce identical edits. New row IDs derive
from the request and project, so repeating the conversion yields the same draft. The first
conversion requires the project to still be at the context's revision (the sweep copies the base
row's current other cells); afterwards the saved draft is verified against the frozen reply digest,
never recompiled against a newer project. Nothing here applies edits, runs or invokes a model.
Design: docs/design/ai-batch-loop.md.
"""
import json
from uuid import UUID, uuid5

from .contexts import _digest, _encode
from .discussion import _message_text
from .drafts import _canonical, _commands
from .parameter_edits import MAX_SUMMARY_CHARS, SCALAR_FIELD_TYPES, _constant, _integer, _number, _unique_object
from .requests import PARAMETER_SWEEP_PROMPT_VERSION, _require
from .store import ProjectError, RevisionConflict, _expected_revision, _id
from .sweep import MAX_AXES, plan_sweep

MAX_SWEEP_ROWS = 100  # one workflow run takes at most 100 rows
_AXIS_SHAPES = ({"field_id", "values"}, {"field_id", "start", "stop", "count"}, {"field_id", "start", "stop", "step"})


def parse_sweep(text, context):
    """The validated sweep specification of a complete reply, scoped to the immutable context."""
    _message_text(text)
    try:
        reply = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_constant,
                           parse_int=_integer, parse_float=_number)
    except (TypeError, ValueError, RecursionError):
        raise ProjectError("Sweep proposal must be one complete strict JSON document") from None
    keys = {"format", "context_id", "base_revision", "summary", "base_record_id", "axes", "mode"}
    if not isinstance(reply, dict) or set(reply) != keys:
        raise ProjectError("Sweep proposal requires exactly format, context_id, base_revision, summary, "
                           "base_record_id, axes and mode")
    if reply["format"] != PARAMETER_SWEEP_PROMPT_VERSION:
        raise ProjectError("Unsupported sweep proposal format")
    _id(reply["context_id"])
    _expected_revision(reply["base_revision"])
    if reply["context_id"] != context["id"] or reply["base_revision"] != context["source_revision"]:
        raise RevisionConflict("Sweep proposal does not match its saved context and source revision")
    summary = reply["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > MAX_SUMMARY_CHARS:
        raise ProjectError("Sweep proposal summary must contain 1 to 4096 characters")
    _encode(summary)
    if reply["mode"] not in ("product", "zip"):
        raise ProjectError("Sweep proposal mode is product or zip")
    if context["content"]["state"] != "included":
        raise ProjectError("Sweep proposal requires included context content")
    selection, content = context["selection"], context["content"]["value"]
    if content["table"] is None or content["table"]["id"] != selection["table_id"]:
        raise ProjectError("Sweep proposal context table is missing")
    base = _id(reply["base_record_id"])
    if base not in selection["record_ids"] or base not in {record["id"] for record in content["records"]}:
        raise ProjectError("Sweep proposal base row is outside the captured selection")
    fields = {field["id"]: field for field in content["fields"]}
    axes = reply["axes"]
    if not isinstance(axes, list) or not 1 <= len(axes) <= MAX_AXES:
        raise ProjectError(f"Sweep proposal requires 1 to {MAX_AXES} axes")
    for axis in axes:
        if not isinstance(axis, dict) or set(axis) not in _AXIS_SHAPES:
            raise ProjectError("Each sweep axis is {field_id, values}, {field_id, start, stop, count} or {field_id, start, stop, step}")
        field_id = _id(axis["field_id"])
        if field_id not in selection["field_ids"] or field_id not in fields:
            raise ProjectError("Sweep proposal axis field is outside the captured selection")
        if fields[field_id]["type"] not in SCALAR_FIELD_TYPES:
            raise ProjectError("Sweep proposals support only scalar fields")
    return {"summary": summary, "base_record_id": base, "axes": axes, "mode": reply["mode"],
            "table_id": selection["table_id"], "fields": {f: fields[f] for f in {a["field_id"] for a in axes}}}


def _identities(request):
    namespace = UUID(request["id"])
    prefix = request["project_id"] + ":" + PARAMETER_SWEEP_PROMPT_VERSION
    return str(uuid5(namespace, prefix + ":draft")), str(uuid5(namespace, prefix + ":provenance"))


def _title(request):
    return "Parameter sweep: " + request["id"]


def _draft_hash(request, state):
    # The frozen reply, not commands compiled from a later project, identifies the draft.
    return _digest({"reply_sha256": state["result"]["text_sha256"], "title": _title(request),
                    "base_revision": request["source_revision"], "format": PARAMETER_SWEEP_PROMPT_VERSION})


def _source(requests, db, identity, state):
    if identity["prompt_version"] != PARAMETER_SWEEP_PROMPT_VERSION:
        raise ProjectError("Request did not ask for a sweep proposal")
    if state["status"] != "completed":
        raise RevisionConflict("Only a completed saved request can produce a sweep proposal")
    context = requests.store.contexts._get(db, identity["context_id"])
    assistant = requests.store.discussion._get_message(db, identity["assistant_message_id"])
    return context, parse_sweep(assistant["text"], context)


def _existing(requests, db, identity, state):
    draft_id, proposal_id = _identities(identity)
    draft_row = db.execute("SELECT * FROM project_drafts WHERE id=?", (draft_id,)).fetchone()
    proposal_row = db.execute("SELECT * FROM project_proposals WHERE id=?", (proposal_id,)).fetchone()
    if draft_row is None and proposal_row is None:
        return None
    if draft_row is None or proposal_row is None:
        raise RevisionConflict("Sweep proposal identity is occupied by an incomplete pair")
    draft = requests.store.drafts._existing(db, draft_id, _draft_hash(identity, state))
    proposal = requests.store.discussion._decode_proposal(db, proposal_row)
    if (draft["base_revision"] != identity["source_revision"] or draft["title"] != _title(identity)
            or proposal["message_id"] != identity["assistant_message_id"]
            or proposal["draft_id"] != draft_id or proposal["context_id"] != identity["context_id"]
            or proposal["base_revision"] != identity["source_revision"]
            or proposal_row["request_sha256"] != _digest({"message_id": identity["assistant_message_id"], "draft_id": draft_id})):
        raise RevisionConflict("Sweep proposal identity belongs to a different source or edit")
    return {"request_id": identity["id"], "draft": draft, "proposal": proposal}


def edit_proposal(requests, request_id):
    _id(request_id)
    with requests.store._connect() as db:
        _require(db)
        identity, state = requests._read(db, request_id)
        return _existing(requests, db, identity, state) or {"request_id": request_id, "draft": None, "proposal": None}


def propose_sweep(requests, request_id, *, expected_revision):
    """Validate a completed sweep reply and save its deterministic draft and provenance; never apply."""
    _id(request_id)
    _expected_revision(expected_revision)
    store = requests.store
    with store._connect() as db:
        _require(db)
        identity, state = requests._read(db, request_id)
        if expected_revision != identity["source_revision"]:
            raise RevisionConflict("Expected revision must match the request's original source revision")
        context, spec = _source(requests, db, identity, state)
        existing = _existing(requests, db, identity, state)
        if existing is not None:
            return {**existing, "replayed": True}
    snapshot = store.snapshot()
    if snapshot["project"]["revision"] != expected_revision:
        raise RevisionConflict("The project changed since the question was captured; ask again to propose a sweep "
                               "over the current rows")
    table = next((t for t in snapshot["tables"] if t["id"] == spec["table_id"]), None)
    current = {field["id"]: field for field in (table or {}).get("fields", ())}
    for field_id, frozen in spec["fields"].items():
        field = current.get(field_id)
        if field is None or field["type"] != frozen["type"] or field.get("unit") != frozen.get("unit"):
            raise RevisionConflict("A swept field no longer matches the captured field")
    namespace, prefix = UUID(identity["id"]), identity["project_id"] + ":sweep:"
    plan = plan_sweep(snapshot, spec["table_id"], spec["axes"], spec["base_record_id"], spec["mode"],
                      new_id=lambda index: str(uuid5(namespace, prefix + str(index))))
    if plan["rows"] > MAX_SWEEP_ROWS:
        raise ProjectError(f"The proposed sweep makes {plan['rows']} rows; a proposal adds at most {MAX_SWEEP_ROWS} "
                           "(one workflow run)")
    commands = plan["commands"]
    preview = store.preview(commands, expected_revision=expected_revision)
    normalized = _commands(store, preview["commands"], expected_revision)
    if _canonical(normalized) != _canonical(_commands(store, commands, expected_revision)):
        raise ProjectError("Sweep preview changed the compiled command identities or values")
    with store._connect(write=True) as db:
        _require(db)
        current_identity, current_state = requests._read(db, request_id)
        if current_identity != identity or current_state["result"] != state["result"] or current_state["status"] != "completed":
            raise RevisionConflict("Sweep request source changed during preview")
        existing = _existing(requests, db, identity, current_state)
        if existing is not None:
            return {**existing, "replayed": True}
        draft_id, proposal_id = _identities(identity)
        draft = store.drafts._save_validated(db, normalized, expected_revision=expected_revision,
                                            title=_title(identity), draft_id=draft_id,
                                            request_sha256=_draft_hash(identity, current_state))
        proposal = store.discussion._link_draft(db, identity["assistant_message_id"], draft_id, proposal_id=proposal_id)
        return {"request_id": request_id, "draft": draft, "proposal": proposal, "replayed": False}
