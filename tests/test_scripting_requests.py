"""Saving and observing request intent through the real bridge never sends it."""

import json
from uuid import uuid4

import pytest

from suan.desktop_bridge.schema import validate_params
from suan.scripting import ProjectRequests

from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401


def test_request_catalog_schema_and_closed_handles(inproc, model):
    store, _ = model
    context = capture(model)
    message = store.discussion.add("Compare selected values", message_id=str(uuid4()), context_id=context["id"])
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    before, history = store.snapshot(), store.history()
    params = {"handle": info["handle"], "message_id": message["id"], "request_id": str(uuid4()),
              "configuration": {"adapter": "test-controlled", "model": "fixture-v1"}}
    saved = harness.call("project.requests.create", params)["request"]
    assert saved["status"] == "pending" and saved["executor_id"] is None and saved["result"] is None
    assert harness.call("project.requests.create", params)["request"] == saved
    assert harness.call("project.requests.create", {**params, "prompt_version": "stk.text/1"})["request"] == saved
    assert harness.error("project.requests.create", {**params, "prompt_version": "stk.parameter-edits/1"})["code"] == "conflict"
    for invalid in (None, True, [], {}, "", "stk.text/2", "stk.parameter-edits/2"):
        malformed = {**params, "prompt_version": invalid}
        assert validate_params("project.requests.create", malformed)
        assert harness.error("project.requests.create", malformed)["code"] == "invalid_params"
    assert harness.call("project.requests.get", {"handle": info["handle"], "request_id": saved["id"]})["request"] == saved
    assert harness.call("project.requests.progress", {"handle": info["handle"], "request_id": saved["id"]}) == {
        "request": saved, "progress": None}
    assert harness.call("project.requests.list", {"handle": info["handle"], "limit": 1}) == {"requests": [saved], "next_offset": None}
    assert harness.error("project.requests.create", {**params, "configuration": {**params["configuration"], "api_key": "must-not-store"}})["code"] == "invalid_params"
    for key in ("adapter", "model"):
        malformed = {**params, "configuration": {**params["configuration"], key: "https://example.test"}}
        assert validate_params("project.requests.create", malformed)
        assert harness.error("project.requests.create", malformed)["code"] == "invalid_params"
    assert harness.error("project.requests.create", {**params, "configuration": {"adapter": "test-controlled", "model": "changed"}})["code"] == "conflict"
    catalog = harness.call("script.catalog")
    assert {"project.requests.create", "project.requests.get", "project.requests.list", "project.requests.cancel"} <= catalog["operations"].keys()
    assert "project.requests.start" in catalog["operations"]
    assert "project.requests.progress" in catalog["operations"]
    proposal_methods = {"project.requests.propose_edits", "project.requests.edit_proposal"}
    assert proposal_methods <= catalog["operations"].keys()
    assert proposal_methods <= set(harness.call("hello", {"protocol": 1})["methods"])
    assert harness.call("project.requests.edit_proposal", {"handle": info["handle"], "request_id": saved["id"]}) == {
        "request_id": saved["id"], "draft": None, "proposal": None}
    assert harness.error("project.requests.start", {"handle": info["handle"], "request_id": saved["id"]})["code"] == "invalid_params"
    assert store.snapshot() == before and store.history() == history and harness.events_of("project.changed") == []
    assert harness.call("project.close", {"handle": info["handle"]})["closed"]
    assert harness.error("project.requests.get", {"handle": info["handle"], "request_id": saved["id"]})["code"] == "not_found"
    assert harness.error("project.requests.progress", {"handle": info["handle"], "request_id": saved["id"]})["code"] == "not_found"
    for method, extra in (("edit_proposal", {}), ("propose_edits", {"expected_revision": 1})):
        assert harness.error("project.requests." + method, {
            "handle": info["handle"], "request_id": saved["id"], **extra})["code"] == "not_found"
    assert not harness.violations


@pytest.mark.parametrize("explicit_default", [False, True])
def test_text_facade_preserves_create_wire_shape_for_older_bridges(explicit_default):
    def older_bridge(method, params):
        assert method == "project.requests.create"
        assert set(params) == {"handle", "request_id", "message_id", "configuration"}
        return {"request": {"status": "pending"}}
    requests = ProjectRequests(older_bridge, "a" * 32)
    kwargs = {"prompt_version": "stk.text/1"} if explicit_default else {}
    assert requests.create(str(uuid4()), request_id=str(uuid4()),
                           configuration={"adapter": "fixture", "model": "test"}, **kwargs) == {"status": "pending"}


def test_real_script_parameter_facade_saves_and_reopens_same_unapplied_draft(scripts, model):
    store, ids = model
    context = capture(model)
    message = store.discussion.add("Suggest a selected temperature", message_id=str(uuid4()), context_id=context["id"])
    info = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    session = scripts.call("script.open")["session"]
    before, history = store.snapshot(), store.history()
    request_id = str(uuid4())
    result = execute(scripts, session, f'''
p = stk.project
request_id = {request_id!r}
r = p.requests.create({message['id']!r}, request_id=request_id,
    configuration={{'adapter':'test-unregistered','model':'fixture'}}, prompt_version='stk.parameter-edits/1')
assert r['prompt_version'] == 'stk.parameter-edits/1' and r['status'] == 'pending'
assert p.requests.edit_proposal(request_id) == {{'request_id': request_id, 'draft': None, 'proposal': None}}
''', project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    # Complete a controlled local fixture; the script has no adapter registration or live provider.
    owner = str(uuid4())
    assert store.requests._claim(request_id, executor_id=owner)[1]
    store.requests._complete(request_id, executor_id=owner, text=json.dumps({
        "format": "stk.parameter-edits/1", "context_id": context["id"], "base_revision": 1,
        "summary": "Review a higher temperature", "edits": [
            {"record_id": ids["first"], "field_id": ids["temperature"], "value": 325}]}))
    result = execute(scripts, session, '''
assert p.requests.get(request_id)['status'] == 'completed'
assert p.requests.edit_proposal(request_id)['draft'] is None
pair = p.requests.propose_edits(request_id, expected_revision=1)
assert not pair['replayed'] and pair['draft']['status'] == 'pending'
assert pair['draft']['base_revision'] == 1
assert pair['proposal']['message_id'] == r['assistant_message_id']
assert p.requests.propose_edits(request_id, expected_revision=1) == {**pair, 'replayed': True}
assert p.requests.edit_proposal(request_id) == {k: v for k, v in pair.items() if k != 'replayed'}
assert p.snapshot()['project']['revision'] == 1
p.close()
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    result = execute(scripts, session, f'''
p = stk.projects.open({str(store.directory)!r})
assert p.requests.edit_proposal(request_id)['draft']['id'] == pair['draft']['id']
assert p.requests.edit_proposal(request_id)['draft']['status'] == 'pending'
assert p.requests.propose_edits(request_id, expected_revision=1) == {{**pair, 'replayed': True}}
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.snapshot() == before and store.history() == history
    assert scripts.events_of("project.changed") == [] and not scripts.violations


def test_real_script_facade_create_cancel_and_reopen_never_sends(scripts, model):
    store, ids = model
    info = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    session = scripts.call("script.open")["session"]
    before, history = store.snapshot(), store.history()
    result = execute(scripts, session, f'''
from uuid import uuid4
p = stk.project
ids = {ids!r}
context = p.contexts.capture(ids['table'], [ids['first']], [ids['temperature']],
    expected_revision=1, title='Explicit scope', context_id=str(uuid4()))
message = p.discussion.add('Explain these saved values', context_id=context['id'], message_id=str(uuid4()))
request_id = str(uuid4())
request = p.requests.create(message['id'], request_id=request_id,
    configuration={{'adapter':'test-controlled','model':'fixture-v1','max_output_tokens':32}})
assert request['context_id'] == context['id'] and request['status'] == 'pending'
assert p.requests.get(request_id) == request
assert p.requests.progress(request_id) == {{'request': request, 'progress': None}}
assert p.requests.list()['requests'] == [request]
cancelled = p.requests.cancel(request_id)
assert cancelled['status'] == 'cancelled' and cancelled['cancel_requested']
assert p.requests.cancel(request_id) == cancelled
assert len(p.discussion.list()['messages']) == 1
p.close()
''', project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert scripts.call("script.close", {"session": session})["closed"]
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f'''
p = stk.projects.open({str(store.directory)!r})
request = p.requests.list()['requests'][0]
assert request['status'] == 'cancelled' and request['executor_id'] is None
assert request['result'] is None and p.requests.get(request['id']) == request
assert p.requests.progress(request['id']) == {{'request': request, 'progress': None}}
assert len(p.discussion.list()['messages']) == 1
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.snapshot() == before and store.history() == history
    assert scripts.events_of("project.changed") == [] and not scripts.violations
