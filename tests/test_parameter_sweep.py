"""AI sweep proposals (P2 L1): a sweep shape compiled by the manual sweep generator into a review draft."""
import json
from uuid import UUID, uuid4, uuid5

import pytest

from suan.project import ProjectError, RevisionConflict
from test_project_contexts import capture, model  # noqa: F401
from test_project_requests import claim


def ask(store, context, reply, *, prompt_version="stk.parameter-sweep/1"):
    message = store.discussion.add("Scan the first case from 300 K to 400 K", message_id=str(uuid4()), context_id=context["id"])
    request = store.requests.create(message["id"], request_id=str(uuid4()),
                                    configuration={"adapter": "controlled/1", "model": "text-fixture"},
                                    prompt_version=prompt_version)
    owner = claim(store, request)
    store.requests._complete(request["id"], executor_id=owner, text=reply if isinstance(reply, str) else json.dumps(reply))
    return store.requests.get(request["id"])


def sweep(context, ids, **changes):
    return {"format": "stk.parameter-sweep/1", "context_id": context["id"], "base_revision": context["source_revision"],
            "summary": "Five temperatures between 300 K and 400 K.", "base_record_id": ids["first"],
            "axes": [{"field_id": ids["temperature"], "start": 300, "stop": 400, "count": 5}], "mode": "product", **changes}


def test_a_sweep_reply_becomes_a_draft_of_new_rows_identical_to_a_manual_sweep(model):
    store, ids = model
    context = capture(model)
    request = ask(store, context, sweep(context, ids))
    before, history = store.snapshot(), store.history()
    saved = store.requests.propose_edits(request["id"], expected_revision=context["source_revision"])
    assert store.snapshot() == before and store.history() == history  # a draft, nothing applied
    draft = saved["draft"]
    assert draft["status"] == "pending" and draft["title"] == "Parameter sweep: " + request["id"]
    added = [command["id"] for command in draft["commands"] if command["op"] == "add_record"]
    namespace = UUID(request["id"])
    assert added == [str(uuid5(namespace, f"{request['project_id']}:sweep:{i}")) for i in range(5)]
    # The same generator, with the same row IDs, gives exactly these commands.
    from suan.project.sweep import plan_sweep
    manual = plan_sweep(before, ids["table"], [{"field_id": ids["temperature"], "start": 300, "stop": 400, "count": 5}],
                        ids["first"], "product", new_id=lambda i: added[i])
    assert [{k: v for k, v in c.items()} for c in draft["commands"]] == manual["commands"]
    assert saved["proposal"]["draft_id"] == draft["id"] and not saved["replayed"]
    assert store.requests.propose_edits(request["id"], expected_revision=context["source_revision"])["replayed"]
    applied = store.drafts.apply(draft["id"], expected_revision=draft["base_revision"])
    table = next(t for t in store.snapshot()["tables"] if t["id"] == ids["table"])
    rows = {record["id"]: record for record in table["records"]}
    assert [rows[row]["values"][ids["temperature"]] for row in added] == [300, 325, 350, 375, 400]
    # The base row's formula moved onto each new row (its own temperature + 10 K).
    assert rows[added[0]]["definitions"][ids["derived"]]["bindings"]["base"]["record_id"] == added[0]
    assert applied["revision"] == context["source_revision"] + 1
    # Reading the saved proposal later does not recompile it against the newer project.
    assert store.requests.edit_proposal(request["id"])["draft"]["id"] == draft["id"]


@pytest.mark.parametrize("change, message", [
    (lambda c, ids: {"axes": [{"field_id": ids["json"], "values": [1]}]}, "outside the captured selection"),
    (lambda c, ids: {"axes": [{"field_id": ids["note"], "values": ["a"], "count": 2}]}, "Each sweep axis"),
    (lambda c, ids: {"base_record_id": str(uuid4())}, "base row is outside"),
    (lambda c, ids: {"axes": [{"field_id": ids["temperature"], "start": 1, "stop": 200, "count": 200}]}, "at most 100"),
    (lambda c, ids: {"mode": "random"}, "product or zip"),
    (lambda c, ids: {"format": "stk.parameter-edits/1"}, "Unsupported sweep proposal format"),
])
def test_out_of_scope_or_malformed_sweeps_are_refused(model, change, message):
    store, ids = model
    context = capture(model)
    request = ask(store, context, sweep(context, ids, **change(context, ids)))
    with pytest.raises((ProjectError, RevisionConflict), match=message):
        store.requests.propose_edits(request["id"], expected_revision=context["source_revision"])
    assert store.drafts.list()["drafts"] == []


def test_a_project_changed_after_capture_asks_for_a_new_question(model):
    store, ids = model
    context = capture(model)
    request = ask(store, context, sweep(context, ids))
    store.apply([{"op": "set_cell", "table_id": ids["table"], "record_id": ids["second"], "field_id": ids["temperature"],
                  "value": 320}], expected_revision=store.info()["revision"])
    with pytest.raises(RevisionConflict, match="ask again"):
        store.requests.propose_edits(request["id"], expected_revision=context["source_revision"])
    with pytest.raises(ProjectError, match="not JSON|strict JSON"):
        store.requests.propose_edits(ask(store, capture(model), "not JSON")["id"], expected_revision=store.info()["revision"])
