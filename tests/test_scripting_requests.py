"""Request intent is durable through the real bridge; no send operation is exposed."""

from uuid import uuid4

from suan.desktop_bridge.schema import validate_params

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
    assert harness.call("project.requests.get", {"handle": info["handle"], "request_id": saved["id"]})["request"] == saved
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
    assert harness.error("project.requests.start", {"handle": info["handle"], "request_id": saved["id"]})["code"] == "invalid_params"
    assert store.snapshot() == before and store.history() == history and harness.events_of("project.changed") == []
    assert harness.call("project.close", {"handle": info["handle"]})["closed"]
    assert harness.error("project.requests.get", {"handle": info["handle"], "request_id": saved["id"]})["code"] == "not_found"
    assert not harness.violations


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
assert len(p.discussion.list()['messages']) == 1
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.snapshot() == before and store.history() == history
    assert scripts.events_of("project.changed") == [] and not scripts.violations
