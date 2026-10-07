"""Structured model text becomes one recoverable draft only on explicit request."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.store import FORMAT_VERSION
from suan.project.contexts import _digest, _encode
from suan.project.discussion import Discussion
from suan.project.parameter_edits import _identities
from suan.project.requests import PARAMETER_EDITS_PROMPT_VERSION, PROMPT_VERSION, SUPPORTED_PROMPT_VERSIONS


@pytest.fixture
def case(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Parameter proposals")
    ids = {name: str(uuid4()) for name in ("table", "number", "integer", "text", "boolean", "json", "derived",
                                          "unselected", "first", "second", "outside")}
    commands = [{"op": "create_table", "id": ids["table"], "name": "Parameters"}]
    for name, kind in (("number", "number"), ("integer", "integer"), ("text", "text"), ("boolean", "boolean"),
                       ("json", "json"), ("derived", "number"), ("unselected", "number")):
        commands.append({"op": "add_field", "id": ids[name], "table_id": ids["table"], "name": name,
                         "type": kind, "unit": "K" if name == "number" else None})
    commands.extend({"op": "add_record", "id": ids[name], "table_id": ids["table"]}
                    for name in ("first", "second", "outside"))
    commands.extend(cell(ids, name, value) for name, value in (("number", 300), ("integer", 2),
                                                            ("text", None), ("boolean", True), ("json", {"a": 1})))
    commands.append({"op": "set_expression", "table_id": ids["table"], "record_id": ids["first"],
                     "field_id": ids["derived"], "expression": "1 + 2", "bindings": {}})
    store.apply(commands, expected_revision=0)
    context = capture(store, ids)
    message = store.discussion.add("Suggest new selected parameter values; do not run anything.",
                                   message_id=str(uuid4()), context_id=context["id"])
    return store, ids, context, message


def cell(ids, field, value, record="first"):
    return {"op": "set_cell", "table_id": ids["table"], "record_id": ids[record], "field_id": ids[field], "value": value}


def capture(store, ids, **kwargs):
    return store.contexts.capture(**{"table_id": ids["table"], "record_ids": [ids["first"], ids["second"]],
        "field_ids": [ids[name] for name in ("number", "integer", "text", "boolean", "json", "derived")],
        "expected_revision": store.info()["revision"], "title": "Explicit parameters", "context_id": str(uuid4()), **kwargs})


def response(case, **changes):
    _, ids, context, _ = case
    return {"format": PARAMETER_EDITS_PROMPT_VERSION, "context_id": context["id"],
            "base_revision": context["source_revision"], "summary": "Increase the temperature to 310 K.",
            "edits": [{"record_id": ids["first"], "field_id": ids["number"], "value": 310}], **changes}


def request(case, *, prompt_version=PARAMETER_EDITS_PROMPT_VERSION):
    store, _, _, message = case
    return store.requests.create(message["id"], request_id=str(uuid4()),
                                 configuration={"adapter": "controlled/1", "model": "parameter-fixture"},
                                 prompt_version=prompt_version)


def complete(case, *, reply=None, text=None, prompt_version=PARAMETER_EDITS_PROMPT_VERSION):
    store, _, _, _ = case
    item = request(case, prompt_version=prompt_version)
    owner = str(uuid4())
    assert store.requests._claim(item["id"], executor_id=owner)[1]
    if text is None:
        text = json.dumps(response(case) if reply is None else reply, ensure_ascii=False)
    return store.requests._complete(item["id"], executor_id=owner, text=text)


def assert_no_proposal(store):
    assert store.drafts.list() == {"drafts": [], "next_offset": None}
    assert store.discussion.proposals() == {"proposals": [], "next_offset": None}


def test_complete_reply_stays_text_until_explicit_conversion_then_reopens_with_provenance(case):
    store, ids, context, _ = case
    before, history = store.snapshot(), store.history()
    item = complete(case)
    assert_no_proposal(store)
    assert store.requests.edit_proposal(item["id"]) == {"request_id": item["id"], "draft": None, "proposal": None}
    result = store.requests.propose_edits(item["id"], expected_revision=1)
    assert set(result) == {"request_id", "draft", "proposal", "replayed"}
    assert result["replayed"] is False and result["draft"]["status"] == "pending"
    assert result["draft"]["commands"] == [cell(ids, "number", 310)]
    assert result["draft"]["base_revision"] == 1
    assert result["proposal"]["message_id"] == item["assistant_message_id"]
    assert result["proposal"]["context_id"] == context["id"]
    assert result["proposal"]["draft_id"] == result["draft"]["id"]
    reopened = ProjectStore(store.directory)
    assert reopened.requests.edit_proposal(item["id"]) == {k: v for k, v in result.items() if k != "replayed"}
    assert reopened.requests.propose_edits(item["id"], expected_revision=1) == {**result, "replayed": True}
    assert store.snapshot() == before and store.history() == history
    assert store.requests.get(item["id"]) == item and store.info()["format_version"] == FORMAT_VERSION
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM run_plans").fetchone()[0] == 0


@pytest.mark.parametrize("terminal", ["applied", "discarded"])
def test_lost_conversion_response_recovers_terminal_pair_after_edits_and_undo(case, terminal, monkeypatch):
    store, ids, _, _ = case
    item = complete(case)
    saved = store.requests.propose_edits(item["id"], expected_revision=1)
    if terminal == "applied":
        store.drafts.apply(saved["draft"]["id"], expected_revision=1)
        store.undo(expected_revision=2)
    else:
        store.drafts.discard(saved["draft"]["id"])
        store.apply([cell(ids, "number", 350)], expected_revision=1)
    reopened = ProjectStore(store.directory)
    before, history = reopened.snapshot(), reopened.history()
    monkeypatch.setattr(reopened, "preview", lambda *a, **k: pytest.fail("recovery must not preview"))
    pair = reopened.requests.edit_proposal(item["id"])
    result = reopened.requests.propose_edits(item["id"], expected_revision=1)
    assert result == {**pair, "replayed": True}
    assert result["draft"]["status"] == terminal
    assert len(reopened.drafts.list()["drafts"]) == len(reopened.discussion.proposals()["proposals"]) == 1
    assert reopened.snapshot() == before and reopened.history() == history
    if terminal == "applied":
        assert reopened.drafts.apply(saved["draft"]["id"], expected_revision=1)["replayed"] is True
        assert reopened.snapshot() == before


def test_scalar_types_null_and_captured_blank_cells_use_existing_preview_and_apply(case):
    store, ids, _, _ = case
    edits = [{"record_id": ids["second"], "field_id": ids[name], "value": value}
             for name, value in (("number", 298.5), ("integer", -(2**63)), ("boolean", False),
                                 ("text", "__import__('os').system('never executed')"))]
    edits.append({"record_id": ids["first"], "field_id": ids["text"], "value": None})
    item = complete(case, reply=response(case, edits=edits))
    result = store.requests.propose_edits(item["id"], expected_revision=1)
    receipt = store.drafts.apply(result["draft"]["id"], expected_revision=1)
    assert receipt["revision"] == 2
    records = {row["id"]: row for row in store.snapshot()["tables"][0]["records"]}
    assert records[ids["second"]]["values"][ids["text"]] == edits[3]["value"]
    assert records[ids["first"]]["values"][ids["text"]] is None
    assert store.history()[-1]["commands"] == result["draft"]["commands"]


@pytest.mark.parametrize("mutation", [
    lambda r, ids: r.update(extra="not allowed"),
    lambda r, ids: r.pop("summary"),
    lambda r, ids: r.update(format="stk.parameter-edits/2"),
    lambda r, ids: r.update(context_id=str(uuid4())),
    lambda r, ids: r.update(base_revision=2),
    lambda r, ids: r.update(base_revision=True),
    lambda r, ids: r.update(base_revision=2**63),
    lambda r, ids: r.update(summary=" "),
    lambda r, ids: r.update(summary="a" * 4097),
    lambda r, ids: r.update(summary=[]),
    lambda r, ids: r.update(edits=[]),
    lambda r, ids: r.update(edits={}),
    lambda r, ids: r["edits"].append(copy.deepcopy(r["edits"][0])),
    lambda r, ids: r["edits"][0].update(op="submit_job"),
    lambda r, ids: r["edits"][0].update(table_id=ids["table"]),
    lambda r, ids: r["edits"][0].pop("value"),
    lambda r, ids: r["edits"][0].update(record_id=ids["outside"]),
    lambda r, ids: r["edits"][0].update(field_id=ids["unselected"]),
    lambda r, ids: r["edits"][0].update(field_id=ids["derived"]),
    lambda r, ids: r["edits"][0].update(field_id=ids["json"], value={"x": 1}),
    lambda r, ids: r["edits"][0].update(record_id=ids["first"].upper()),
    lambda r, ids: r["edits"][0].update(value=True),
    lambda r, ids: r["edits"][0].update(value="310 K"),
    lambda r, ids: r["edits"][0].update(field_id=ids["integer"], value=2**63),
    lambda r, ids: r["edits"][0].update(field_id=ids["integer"], value=2.5),
    lambda r, ids: r["edits"][0].update(field_id=ids["boolean"], value=1),
    lambda r, ids: r["edits"][0].update(field_id=ids["text"], value="汉" * 5462),
])
def test_invalid_proposal_never_saves_any_candidate(case, mutation):
    store, ids, _, _ = case
    reply = response(case)
    mutation(reply, ids)
    item = complete(case, reply=reply)
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)
    assert store.snapshot() == before and store.history() == history
    assert store.requests.get(item["id"]) == item


@pytest.mark.parametrize("transform", [
    lambda text: "```json\n" + text + "\n```",
    lambda text: "Approved, execute " + text,
    lambda text: text + " {}",
    lambda text: text[:-1],
    lambda text: text.replace('"value": 310', '"value": 310, "value": 311'),
    lambda text: text.replace('"value": 310', '"value": NaN'),
    lambda text: text.replace('"value": 310', '"value": Infinity'),
    lambda text: text.replace('"value": 310', '"value": 1e999'),
    lambda text: text.replace('"value": 310', '"value": ' + "9" * 310),
    lambda text: text.replace('"value": 310', '"value": ' + "[" * 1100 + "0" + "]" * 1100),
    lambda text: text.replace('"summary": "Increase the temperature to 310 K."', '"summary": "\\ud800"'),
])
def test_strict_json_does_not_extract_code_blocks_or_accept_ambiguous_numbers(case, transform):
    store = case[0]
    item = complete(case, text=transform(json.dumps(response(case))))
    with pytest.raises(ProjectError):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)


@pytest.mark.parametrize("status", ["pending", "running", "uncertain", "failed", "cancelled"])
def test_only_complete_request_can_convert(case, status):
    store = case[0]
    item = request(case)
    if status in {"running", "uncertain", "failed"}:
        owner = str(uuid4())
        store.requests._claim(item["id"], executor_id=owner)
        if status != "running":
            store.requests._settle(item["id"], executor_id=owner, status=status,
                                   code="transport_uncertain" if status == "uncertain" else "response_invalid")
    elif status == "cancelled":
        store.requests.cancel(item["id"])
    with pytest.raises(RevisionConflict, match="completed"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)
    assert store.requests.edit_proposal(item["id"])["draft"] is None


def test_ordinary_text_or_imported_assistant_role_cannot_supply_proposal_authority(case):
    store, _, context, _ = case
    text = json.dumps(response(case))
    item = complete(case, text=text, prompt_version=PROMPT_VERSION)
    assert store.requests.edit_proposal(item["id"]) == {"request_id": item["id"], "draft": None, "proposal": None}
    with pytest.raises(ProjectError, match="structured parameter"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    imported = store.discussion.add(text, message_id=str(uuid4()), context_id=context["id"], role="assistant")
    with pytest.raises(ProjectError, match="request not found"):
        store.requests.propose_edits(imported["id"], expected_revision=1)
    assert_no_proposal(store)


def test_stale_context_cannot_be_rebased_or_used_after_live_project_advances(case):
    store, ids, _, _ = case
    item = complete(case)
    store.apply([cell(ids, "number", 350)], expected_revision=1)
    with pytest.raises(RevisionConflict, match="current revision"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    with pytest.raises(RevisionConflict, match="original source"):
        store.requests.propose_edits(item["id"], expected_revision=2)
    assert_no_proposal(store)


def test_final_cas_rejects_edit_that_wins_during_preview_without_orphan(case, monkeypatch):
    store, ids, _, _ = case
    item = complete(case)
    original = store.preview
    def race(*args, **kwargs):
        preview = original(*args, **kwargs)
        store.apply([cell(ids, "number", 350)], expected_revision=1)
        return preview
    monkeypatch.setattr(store, "preview", race)
    with pytest.raises(RevisionConflict, match="current revision"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)
    assert store.info()["revision"] == 2


def test_provenance_failure_rolls_back_draft_and_same_identity_can_retry(case, monkeypatch):
    store = case[0]
    item = complete(case)
    before, history = store.snapshot(), store.history()
    original = Discussion._link_draft
    def fail_after_insert(self, db, *args, **kwargs):
        original(self, db, *args, **kwargs)
        raise ProjectError("Injected interruption before atomic pair commit")
    with monkeypatch.context() as patch:
        patch.setattr(Discussion, "_link_draft", fail_after_insert)
        with pytest.raises(ProjectError, match="Injected"):
            store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)
    assert store.snapshot() == before and store.history() == history
    assert store.requests.get(item["id"]) == item
    assert store.requests.propose_edits(item["id"], expected_revision=1)["replayed"] is False


def test_concurrent_callers_create_exactly_one_atomic_pair(case):
    store = case[0]
    item = complete(case)
    ready = threading.Barrier(4)
    def convert(_):
        independent = ProjectStore(store.directory)
        ready.wait(timeout=10)
        return independent.requests.propose_edits(item["id"], expected_revision=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(convert, range(4)))
    assert sorted(result["replayed"] for result in results) == [False, True, True, True]
    assert all(result["draft"] == results[0]["draft"] and result["proposal"] == results[0]["proposal"] for result in results)
    assert store.info()["revision"] == 1
    assert len(store.drafts.list()["drafts"]) == len(store.discussion.proposals()["proposals"]) == 1


def test_loser_of_preview_race_recovers_pair_even_if_winner_already_applied(case, monkeypatch):
    store = case[0]
    item = complete(case)
    original = store.preview
    winner = {}
    def race(*args, **kwargs):
        other = ProjectStore(store.directory)
        winner.update(other.requests.propose_edits(item["id"], expected_revision=1))
        other.drafts.apply(winner["draft"]["id"], expected_revision=1)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "preview", race)
    result = store.requests.propose_edits(item["id"], expected_revision=1)
    assert result["draft"]["id"] == winner["draft"]["id"]
    assert result["draft"]["status"] == "applied" and result["replayed"] is True
    assert store.info()["revision"] == 2


@pytest.mark.parametrize("ancestor", ["draft", "proposal", "assistant", "context"])
def test_recovery_validates_candidate_and_source_checksums(case, ancestor):
    store, _, context, _ = case
    item = complete(case)
    result = store.requests.propose_edits(item["id"], expected_revision=1)
    relation, key = {"draft": ("project_drafts", result["draft"]["id"]),
                     "proposal": ("project_proposals", result["proposal"]["id"]),
                     "assistant": ("project_messages", item["assistant_message_id"]),
                     "context": ("project_contexts", context["id"])}[ancestor]
    with sqlite3.connect(store.path) as db:
        db.execute(f"UPDATE {relation} SET sha256='corrupt' WHERE id=?", (key,))
    with pytest.raises(ProjectError):
        store.requests.edit_proposal(item["id"])
    with pytest.raises(ProjectError):
        store.requests.propose_edits(item["id"], expected_revision=1)


def test_occupied_deterministic_identity_cannot_be_adopted_or_completed(case):
    store, ids, _, _ = case
    item = complete(case)
    draft_id, _ = _identities(item)
    occupied = store.drafts.save([cell(ids, "number", 999)], expected_revision=1,
                                 title="Unrelated user proposal", draft_id=draft_id)
    with pytest.raises(RevisionConflict, match="incomplete pair"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    with pytest.raises(RevisionConflict, match="incomplete pair"):
        store.requests.edit_proposal(item["id"])
    assert store.drafts.get(draft_id) == occupied and store.discussion.proposals()["proposals"] == []


def test_occupied_provenance_identity_does_not_create_or_attach_missing_draft(case):
    store, ids, _, message = case
    item = complete(case)
    draft_id, proposal_id = _identities(item)
    other = store.drafts.save([cell(ids, "number", 999)], expected_revision=1,
                              title="Unrelated user proposal", draft_id=str(uuid4()))
    link = store.discussion.link_draft(message["id"], other["id"], proposal_id=proposal_id)
    with pytest.raises(RevisionConflict, match="incomplete pair"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    with pytest.raises(RevisionConflict, match="incomplete pair"):
        store.requests.edit_proposal(item["id"])
    assert store.discussion.proposals()["proposals"] == [link]
    assert store.drafts.get(other["id"]) == other
    with pytest.raises(ProjectError, match="draft not found"):
        store.drafts.get(draft_id)


def test_request_modes_preserve_text_hashes_and_are_immutable_under_retries(case):
    store, _, _, message = case
    ordinary = request(case, prompt_version=PROMPT_VERSION)
    structured = request(case)
    assert SUPPORTED_PROMPT_VERSIONS == {PROMPT_VERSION, PARAMETER_EDITS_PROMPT_VERSION}
    with sqlite3.connect(store.path) as db:
        old_hash = db.execute("SELECT request_sha256 FROM project_requests WHERE id=?", (ordinary["id"],)).fetchone()[0]
        new_hash = db.execute("SELECT request_sha256 FROM project_requests WHERE id=?", (structured["id"],)).fetchone()[0]
    original_request = {"message_id": message["id"], "configuration": ordinary["configuration"]}
    assert old_hash == _digest(original_request)
    assert new_hash == _digest({**original_request, "prompt_version": PARAMETER_EDITS_PROMPT_VERSION})
    assert store.requests.create(message["id"], request_id=ordinary["id"], configuration=ordinary["configuration"]) == ordinary
    assert store.requests.create(message["id"], request_id=ordinary["id"], configuration=ordinary["configuration"],
                                  prompt_version=PROMPT_VERSION) == ordinary
    for item, changed in ((ordinary, PARAMETER_EDITS_PROMPT_VERSION), (structured, PROMPT_VERSION)):
        with pytest.raises(RevisionConflict, match="different input"):
            store.requests.create(message["id"], request_id=item["id"], configuration=item["configuration"], prompt_version=changed)
    assert store.requests.input(structured["id"])["prompt_version"] == PARAMETER_EDITS_PROMPT_VERSION
    assert ProjectStore(store.directory).requests.get(structured["id"]) == structured


@pytest.mark.parametrize("version", [None, [], True, "stk.parameter-edits/2", "stk.text/2", ""])
def test_unknown_prompt_modes_never_create_request(case, version):
    with pytest.raises(ProjectError, match="prompt version"):
        request(case, prompt_version=version)
    assert case[0].requests.list()["requests"] == []


def test_project_replacement_during_preview_cannot_receive_candidate(case, tmp_path, monkeypatch):
    store = case[0]
    item = complete(case)
    other = ProjectStore.create(tmp_path / "other", "Other project")
    original = store.preview
    def replace(*args, **kwargs):
        preview = original(*args, **kwargs)
        shutil.copyfile(other.path, store.path)
        return preview
    monkeypatch.setattr(store, "preview", replace)
    with pytest.raises(ProjectError, match="replaced"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(ProjectStore(store.directory))


def with_context(case, context):
    store, ids, _, _ = case
    message = store.discussion.add("Suggest a selected parameter value", message_id=str(uuid4()), context_id=context["id"])
    return store, ids, context, message


@pytest.mark.parametrize("missing", ["record", "field", "table"])
def test_selected_missing_objects_are_not_invented_by_conversion(case, missing):
    store, ids, _, _ = case
    table_id = str(uuid4()) if missing == "table" else ids["table"]
    record_id = str(uuid4()) if missing in {"record", "table"} else ids["first"]
    field_id = str(uuid4()) if missing in {"field", "table"} else ids["number"]
    context = capture(store, ids, table_id=table_id, record_ids=[record_id], field_ids=[field_id])
    case = with_context(case, context)
    item = complete(case, reply=response(case, edits=[{"record_id": record_id, "field_id": field_id, "value": 310}]))
    with pytest.raises(ProjectError, match="missing"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)


def test_omitted_target_is_rejected_but_another_omitted_cell_does_not_expand_scope(case):
    store, ids, _, _ = case
    store.apply([cell(ids, "text", "汉" * 6000)], expected_revision=1)
    case = with_context(case, capture(store, ids))
    assert case[2]["omitted_values"] == 1
    target = complete(case, reply=response(case, edits=[{"record_id": ids["first"], "field_id": ids["text"], "value": "new"}]))
    with pytest.raises(ProjectError, match="omitted"):
        store.requests.propose_edits(target["id"], expected_revision=2)
    assert_no_proposal(store)
    valid = complete(case)
    converted = store.requests.propose_edits(valid["id"], expected_revision=2)
    assert converted["draft"]["commands"] == [cell(ids, "number", 310)]


def test_whole_omitted_context_cannot_supply_proposal_targets(case):
    store, ids, _, _ = case
    records = [str(uuid4()) for _ in range(20)]
    commands = []
    for record_id in records:
        commands.extend([{"op": "add_record", "id": record_id, "table_id": ids["table"]},
                         {"op": "set_cell", "record_id": record_id, "field_id": ids["text"],
                          "table_id": ids["table"], "value": "x" * 15000}])
    store.apply(commands, expected_revision=1)
    context = capture(store, ids, record_ids=records, field_ids=[ids["text"]])
    assert context["content"]["state"] == "omitted"
    case = with_context(case, context)
    item = complete(case, reply=response(case, edits=[{"record_id": records[0], "field_id": ids["text"], "value": "new"}]))
    with pytest.raises(ProjectError, match="included context"):
        store.requests.propose_edits(item["id"], expected_revision=2)
    assert_no_proposal(store)


def test_maximum_value_and_summary_bounds_are_inclusive_and_do_not_truncate(case):
    store, ids, _, _ = case
    value = "x" * (16 * 1024 - 2)  # Quotes count toward the UTF-8 JSON value budget.
    item = complete(case, reply=response(case, summary="汉" * 4096,
        edits=[{"record_id": ids["second"], "field_id": ids["text"], "value": value}]))
    result = store.requests.propose_edits(item["id"], expected_revision=1)
    assert result["draft"]["commands"][0]["value"] == value
    assert len(store.discussion.get(item["assistant_message_id"])["text"].encode("utf-8")) < 64 * 1024


def test_completed_reply_with_recorded_cancel_intent_still_needs_explicit_conversion(case):
    store = case[0]
    item = request(case)
    owner = str(uuid4())
    store.requests._claim(item["id"], executor_id=owner)
    store.requests.cancel(item["id"])
    completed = store.requests._complete(item["id"], executor_id=owner, text=json.dumps(response(case)))
    assert completed["status"] == "completed" and completed["cancel_requested"] is True
    assert_no_proposal(store)
    assert store.requests.propose_edits(item["id"], expected_revision=1)["draft"]["status"] == "pending"
    assert store.requests.get(item["id"]) == completed


def test_preview_result_cannot_smuggle_commands_not_compiled_from_model_values(case, monkeypatch):
    store, ids, _, _ = case
    item = complete(case)
    monkeypatch.setattr(store, "preview", lambda *a, **k: {"commands": [{"op": "delete_table", "id": ids["table"]}]})
    with pytest.raises(ProjectError, match="changed the compiled"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)


def test_independently_valid_provenance_for_another_message_is_not_adopted(case):
    store, _, context, _ = case
    item = complete(case)
    converted = store.requests.propose_edits(item["id"], expected_revision=1)
    imported = store.discussion.add("Unrelated imported assistant", message_id=str(uuid4()), context_id=context["id"], role="assistant")
    altered = {**converted["proposal"], "message_id": imported["id"]}
    request_hash = _digest({"message_id": imported["id"], "draft_id": converted["draft"]["id"]})
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_proposals SET message_id=?,payload=?,request_sha256=?,sha256=? WHERE id=?",
                   (imported["id"], _encode(altered).decode(), request_hash,
                    _digest({"payload": altered, "request_sha256": request_hash}), altered["id"]))
    # The generic manual link remains well-formed, but it is not this conversion.
    assert store.discussion.proposals()["proposals"] == [altered]
    with pytest.raises(RevisionConflict, match="different source"):
        store.requests.edit_proposal(item["id"])
    with pytest.raises(RevisionConflict, match="different source"):
        store.requests.propose_edits(item["id"], expected_revision=1)


def test_live_type_or_unit_damage_is_not_silently_treated_as_original_context(case):
    store, ids, _, _ = case
    item = complete(case)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE fields SET unit='degC' WHERE id=?", (ids["number"],))
    with pytest.raises(RevisionConflict, match="captured field"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)


def test_replacing_saved_complete_result_at_preview_seam_cannot_relabel_old_commands(case, monkeypatch):
    store = case[0]
    item = complete(case)
    original = store.preview
    def replace(*args, **kwargs):
        result = original(*args, **kwargs)
        with sqlite3.connect(store.path) as db:
            raw, message_request_hash = db.execute("SELECT payload,request_sha256 FROM project_messages WHERE id=?",
                                                   (item["assistant_message_id"],)).fetchone()
            message = json.loads(raw)
            altered_reply = json.loads(message["text"])
            altered_reply["edits"][0]["value"] = 777
            message["text"] = json.dumps(altered_reply)
            db.execute("UPDATE project_messages SET payload=?,sha256=? WHERE id=?",
                       (_encode(message).decode(), _digest({"payload": message, "request_sha256": message_request_hash}), message["id"]))
            raw, identity_hash = db.execute("SELECT state,sha256 FROM project_requests WHERE id=?", (item["id"],)).fetchone()
            state = json.loads(raw)
            from suan.project.requests import _text_hash
            state["result"]["text_sha256"] = _text_hash(message["text"])
            db.execute("UPDATE project_requests SET state=?,state_sha256=? WHERE id=?",
                       (_encode(state).decode(), _digest({"id": item["id"], "sha256": identity_hash, "state": state}), item["id"]))
        return result
    monkeypatch.setattr(store, "preview", replace)
    with pytest.raises(RevisionConflict, match="source changed during preview"):
        store.requests.propose_edits(item["id"], expected_revision=1)
    assert_no_proposal(store)
