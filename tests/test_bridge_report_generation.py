"""The report-generation contract crosses the strict bridge with explicit send/save steps."""
import base64
import hashlib
from uuid import uuid4
import zipfile

import pytest

from suan.project.contexts import _digest, _encode
from suan.project.report_generation import INPUT_EXPORT, RESPONSE_EXPORT
from suan.project.requests import REPORT_PROMPT_VERSION
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401
from test_request_executor import ControlledAdapter, eventually, executors, idle  # noqa: F401


@pytest.mark.parametrize("entry,body", [
    ("report.md", "# 结果\n\nExplicitly reviewed frozen values.\n"),
    ("report.html", "<h1>结果</h1><p>Explicitly reviewed frozen values.</p>"),
])
def test_strict_report_send_edit_save_preview_and_reopen(inproc, model, tmp_path, entry, body):
    h = inproc()
    store, ids = model
    context = capture(model)
    info = h.call("project.open", {"directory": str(store.directory)})["project"]
    project = Project(h.call, info["handle"])
    methods = {"project.reports.generation_request", "project.reports.create_generated"}
    assert methods <= set(h.call("hello", {"protocol": 1})["methods"])
    assert methods <= h.call("script.catalog")["operations"].keys()
    reviewed = project.reports.review_sources([], expected_revision=1)
    message = project.discussion.add("Draft a report from this saved context.",
                                     message_id=str(uuid4()), context_id=context["id"])
    request = project.requests.create(message["id"], request_id=str(uuid4()),
        configuration={"adapter": "controlled", "model": "report-test"},
        prompt_version=REPORT_PROMPT_VERSION, report_selection={
            "expected_revision": 1, "sources": [], "expected_sources_sha256": reviewed["sources_sha256"],
            "snapshot_id": None, "assets": []})
    original = project.reports.generation_request(request["id"])
    assert original["response"] is None and _digest(original["input"]) == request["input_sha256"]
    assert project.reports.list()["total"] == 0 and h.events_of("project.changed") == []
    adapter = ControlledAdapter("Original report draft.")
    executor = h.bridge.projects._executor
    executor._adapters["controlled"] = adapter
    try:
        assert project.requests.start(request["id"])["status"] == "running"
        assert adapter.started.wait(5)
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    saved_request = project.reports.generation_request(request["id"])
    assert saved_request["request"]["status"] == "completed"
    assert saved_request["response"]["text"] == "Original report draft."
    assert len(adapter.inputs) == 1 and project.reports.list()["total"] == 0
    # A subsequent project edit must not silently recapture any report source.
    project.apply([{"op": "rename_table", "id": ids["table"], "name": "Later name"}], expected_revision=1)
    identity = str(uuid4())
    result = project.reports.create_generated("Reviewed report", request["id"], body,
        report_id=identity, expected_revision=2, expected_input_sha256=request["input_sha256"],
        expected_response_sha256=saved_request["request"]["result"]["text_sha256"], entry_path=entry)
    assert result["revision"] == 3 and result["record_id"] == identity
    h.wait_event(lambda event: event["event"] == "project.changed" and event["data"]["revision"] == 3)
    report = project.reports.get(identity)["report"]
    assert report["state"] == "readable" and report["format"] == "stk.report/2"
    assert report["manifest"]["sources"][0]["context"] == context
    assert report["manifest"]["generation"]["edited"] is True
    guards = {"expected_revision": 3, "expected_source_sha256": report["source_sha256"]}
    asset = project.reports.asset(identity, entry, **guards)
    assert base64.b64decode(asset["data"], validate=True) == body.encode()
    preview = project.reports.preview_resources(identity, **guards)
    assert preview["preview"]["source_content_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    destination = tmp_path / (entry + ".zip")
    project.reports.export_file(identity, destination, **guards)
    with zipfile.ZipFile(destination) as package:
        assert package.read(entry) == body.encode()
        assert package.read(INPUT_EXPORT) == _encode(original["input"])
        assert package.read(RESPONSE_EXPORT) == b"Original report draft."
    assert project.close()
    reopened_info = h.call("project.open", {"directory": str(store.directory)})["project"]
    reopened = Project(h.call, reopened_info["handle"])
    assert reopened.reports.get(identity)["report"] == report
    assert reopened.reports.generation_request(request["id"])["input"] == original["input"]
    assert len(adapter.inputs) == 1
    h.assert_clean()


def test_lost_save_reply_is_observed_by_original_report_identity(inproc, model):
    h = inproc()
    store, _ = model
    context = capture(model)
    message = store.discussion.add("Report", message_id=str(uuid4()), context_id=context["id"])
    request = store.requests.create(message["id"], request_id=str(uuid4()),
        configuration={"adapter": "controlled", "model": "report-test"},
        prompt_version=REPORT_PROMPT_VERSION, report_selection={"expected_revision": 1,
            "sources": [], "expected_sources_sha256": None, "snapshot_id": None, "assets": []})
    owner = str(uuid4())
    assert store.requests._claim(request["id"], executor_id=owner)[1]
    done = store.requests._complete(request["id"], executor_id=owner, text="# Frozen report")
    info = h.call("project.open", {"directory": str(store.directory)})["project"]
    writes = []

    def lose_reply(method, params):
        value = h.call(method, params)
        if method == "project.reports.create_generated":
            writes.append(params["report_id"])
            raise ConnectionError("Controlled lost response after commit")
        return value

    project, identity = Project(lose_reply, info["handle"]), str(uuid4())
    with pytest.raises(ConnectionError):
        project.reports.create_generated("Frozen", request["id"], "# Frozen report", report_id=identity,
            expected_revision=1, expected_input_sha256=request["input_sha256"],
            expected_response_sha256=done["result"]["text_sha256"])
    observed = project.reports.get(identity)
    assert observed["revision"] == 2 and observed["report"]["state"] == "readable"
    assert observed["report"]["manifest"]["generation"]["edited"] is False
    assert project.reports.list()["total"] == 1 and writes == [identity]
    h.assert_clean()


def test_real_worker_report_generation_separates_prepare_send_edit_save_and_reopen(scripts, model, executors, tmp_path):
    store, _ = model
    context = capture(model)
    info = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    required = {"project.requests.create", "project.reports.generation_request",
                "project.reports.create_generated", "project.reports.preview", "project.reports.export_file"}
    assert required <= scripts.call("script.catalog")["operations"].keys()
    session = scripts.call("script.open")["session"]
    request_id, report_id = str(uuid4()), str(uuid4())
    destination = tmp_path / "worker reviewed report.zip"
    history, events = store.history(), scripts.events_of("project.changed")
    adapter = ControlledAdapter("# Original saved reply\n\nFrozen temperature: 300 K.\n")
    executor = executors(adapter)

    def run(source):
        result = execute(scripts, session, source, project_handle=info["handle"])
        assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]

    # Preparing in a real persistent worker freezes input, but neither sends nor saves a report.
    run(f'''
import base64
import hashlib
from pathlib import Path
from uuid import uuid4
from suan.scripting import ScriptError
p = stk.project
reports = p.reports
requests = p.requests
revision = p.catalog()['project']['revision']
reviewed = reports.review_sources([], expected_revision=revision)
message = p.discussion.add('Draft a report from the saved values; do not execute anything.',
                          message_id=str(uuid4()), context_id={context['id']!r})
request = requests.create(message['id'], request_id={request_id!r},
    configuration={{'adapter': 'controlled', 'model': 'report-test'}},
    prompt_version={REPORT_PROMPT_VERSION!r}, report_selection={{
        'expected_revision': revision, 'sources': [],
        'expected_sources_sha256': reviewed['sources_sha256'], 'snapshot_id': None, 'assets': []}})
assert request['status'] == 'pending'
assert reports.list()['total'] == 0
''')
    assert store.requests.get(request_id)["status"] == "pending" and adapter.inputs == []
    assert store.history() == history and scripts.events_of("project.changed") == events

    # A later script can inspect pending work without implicitly starting it.
    run('''
pending = reports.generation_request(request['id'])
assert pending['request']['status'] == 'pending' and pending['response'] is None
assert pending['input']['prompt_version'] == 'stk.report-draft/1'
assert reports.list()['total'] == 0
''')
    assert store.requests.get(request_id)["status"] == "pending" and adapter.inputs == []
    frozen_input = store.requests.input(request_id)

    # Only this explicit test-owned executor action sends, to a controlled adapter with no endpoint.
    try:
        assert executor.start(store, request_id)["status"] == "running"
        assert adapter.started.wait(5)
        assert store.reports.list()["total"] == 0
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(request_id)["status"] == "completed"
    assert adapter.inputs == [frozen_input]

    # Loading the saved completion and editing the body still does not create a report.
    run('''
completed = reports.generation_request(request['id'])
assert completed['request']['status'] == 'completed'
assert completed['input'] == pending['input']
assert completed['response']['text'].startswith('# Original saved reply')
body = completed['response']['text'] + '\\n用户审核：仅保存冻结观察，不宣称科学验证。\\n'
assert reports.list()['total'] == 0
''')
    assert store.reports.list()["total"] == 0 and store.history() == history
    assert scripts.events_of("project.changed") == events

    # Saving, rendering and exporting are separate facade calls; reopening cannot retarget old facades.
    run(f'''
created = reports.create_generated('Worker reviewed report', request['id'], body,
    report_id={report_id!r}, expected_revision=revision,
    expected_input_sha256=request['input_sha256'],
    expected_response_sha256=completed['request']['result']['text_sha256'])
assert created['revision'] == revision + 1 and created['record_id'] == {report_id!r}
saved = reports.get({report_id!r})['report']
assert saved['format'] == 'stk.report/2' and saved['manifest']['generation']['edited'] is True
guards = {{'expected_revision': created['revision'], 'expected_source_sha256': saved['source_sha256']}}
asset = reports.asset({report_id!r}, 'report.md', **guards)
assert base64.b64decode(asset['data'], validate=True) == body.encode('utf-8')
preview = reports.preview({report_id!r}, **guards)
assert preview['renderer'] == 'stk.report-renderer/1'
assert preview['source_content_sha256'] == hashlib.sha256(body.encode('utf-8')).hexdigest()
assert preview['content_sha256'] == hashlib.sha256(base64.b64decode(preview['data'], validate=True)).hexdigest()
assert preview['content_sha256'] != preview['source_content_sha256']
exported = reports.export_file({report_id!r}, Path({str(destination)!r}), **guards)
assert exported['sha256'] == hashlib.sha256(Path({str(destination)!r}).read_bytes()).hexdigest()
assert p.close()
reopened = stk.projects.open({str(store.directory)!r})
assert reopened.reports.get({report_id!r})['report'] == saved
assert reopened.reports.generation_request(request['id'])['input'] == pending['input']
assert reopened.reports.preview({report_id!r}, **guards)['session_id'] != preview['session_id']
for old_call in (lambda: reports.generation_request(request['id']),
                 lambda: reports.get({report_id!r}), lambda: requests.get(request['id'])):
    try:
        old_call()
    except ScriptError as error:
        assert error.code == 'not_found'
    else:
        raise AssertionError('closed project facade silently adopted the new handle')
''')
    assert store.info()["revision"] == info["revision"] + 1
    assert len(store.history()) == len(history) + 1 and adapter.inputs == [frozen_input]
    assert scripts.events_of("project.changed") == events + [{"handle": info["handle"], "revision": 2}]
    assert scripts.events_of("ui.request") == []
    report = store.reports.get(report_id)["report"]
    with zipfile.ZipFile(destination) as package:
        assert package.read("report.md") == report["manifest"]["generation"]["body"].encode("utf-8")
        assert package.read(INPUT_EXPORT) == _encode(frozen_input)
        assert package.read(RESPONSE_EXPORT) == adapter.result.encode("utf-8")
    scripts.assert_clean()
