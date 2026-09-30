"""Analysis persistence and pure Viewer capture remain two explicit, negotiated operations."""
from copy import deepcopy
from uuid import uuid4

import pytest

from suan.contracts import load_schema
from suan.desktop_bridge.schema import _resolved, validate_params
from suan.desktop_bridge.ui_requests import UI_OPERATIONS
from suan.graph.schema import check_value
from suan.project import ProjectStore
from suan.scripting import API
from test_bridge_analyses import document
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, execute, settled  # noqa: F401


def configuration(displayed=False):
    return {"viewer_version": 7, "displayed": displayed, "displayed_graph_verified": None,
        "configuration": {"source": {"key": "run|fixture", "kind": "run", "path": "/fixture/run",
            "field_file": "", "connection": "", "node": "", "workspace_id": "", "task_id": "", "series": False},
            "preset_id": "fixture", "graph": document()["graph"], "parameters": {"step": "latest"},
            "requested_outputs": ["frames"]}}


def test_facades_keep_explicit_revision_identity_and_strict_capture_boolean():
    calls = []
    def call(method, params):
        calls.append((method, params))
        return {"operation": method}
    api = API(call); api._project_handle = "a" * 32
    saved = api.project.analyses
    identity = str(uuid4()); doc = document()
    assert saved.create("Name", doc, analysis_id=identity, expected_revision=3) == {"operation": "project.analyses.create"}
    saved.update(identity, "Updated", doc, expected_revision=4)
    saved.get(identity); saved.list()
    assert calls[:2] == [("project.analyses.create", {"handle": "a" * 32, "analysis_id": identity,
        "name": "Name", "document": doc, "expected_revision": 3}),
        ("project.analyses.update", {"handle": "a" * 32, "analysis_id": identity,
        "name": "Updated", "document": doc, "expected_revision": 4})]
    assert calls[2:] == [("project.analyses.get", {"handle": "a" * 32, "analysis_id": identity}),
                         ("project.analyses.list", {"handle": "a" * 32, "offset": 0, "limit": 50})]
    api._project_handle = "b" * 32; saved.get(identity)
    assert calls[-1][1]["handle"] == "a" * 32
    api.viewer.graph_configuration(); api.viewer.graph_configuration(displayed=True)
    assert calls[-2:] == [("ui.viewer.graph_configuration", {"displayed": False}),
                         ("ui.viewer.graph_configuration", {"displayed": True})]
    size = len(calls)
    for bad in (None, 0, 1, "false", [], {}):
        with pytest.raises(TypeError, match="displayed must be a boolean"):
            api.viewer.graph_configuration(displayed=bad)
    with pytest.raises(TypeError): api.viewer.graph_configuration(True)
    assert len(calls) == size


def test_capture_contracts_are_exact_and_additive():
    assert "viewer.graph_configuration" in UI_OPERATIONS
    original = ["layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close"]
    assert validate_params("ui.attach", {"operations": original}) == []
    assert validate_params("ui.attach", {"operations": list(UI_OPERATIONS)}) == []
    params = load_schema("desktop-bridge-1")["$defs"]["uiViewerGraphConfigurationParams"]
    assert check_value({"displayed": False}, params) == []
    for bad in ({}, {"displayed": 1}, {"displayed": False, "expected_source": "run|fixture"}):
        assert check_value(bad, params)
    result = _resolved("#/$defs/uiViewerGraphConfigurationResult")
    assert check_value(configuration(), result) == []
    unavailable = {"viewer_version": 0, "displayed": True, "displayed_graph_verified": None, "configuration": None}
    assert check_value(unavailable, result) == []
    for replacement in ({"viewer_version": True}, {"displayed": 0}, {"displayed_graph_verified": "unknown"},
                        {"result": {"payload": {}}}):
        assert check_value({**configuration(), **replacement}, result)
    missing = configuration(); del missing["configuration"]["source"]["workspace_id"]
    assert check_value(missing, result)


def test_real_worker_analysis_facade_preserves_documents_through_reopen_and_cas(scripts, tmp_path):
    directory = tmp_path / "project"
    info = scripts.call("project.create", {"directory": str(directory), "name": "Analyses"})["project"]
    session = scripts.call("script.open")["session"]
    identity = str(uuid4())
    source = f'''
from suan.scripting import ScriptError
p = stk.project
doc = {document()!r}
analysis_id = {identity!r}
assert p.analyses.list()['analyses'] == []
assert p.analyses.create('Saved graph', doc, analysis_id=analysis_id, expected_revision=0)['revision'] == 1
assert p.analyses.get(analysis_id)['analysis']['document'] == doc
doc['parameters']['step'] = 2
assert p.analyses.update(analysis_id, 'Updated graph', doc, expected_revision=1)['revision'] == 2
assert p.analyses.list(limit=1)['analyses'][0]['id'] == analysis_id
try:
    p.analyses.update(analysis_id, 'Stale', doc, expected_revision=1)
except ScriptError as error:
    assert error.code == 'conflict'
else:
    raise AssertionError('stale analysis write accepted')
assert p.close()
reopened = stk.projects.open({str(directory)!r})
assert reopened.analyses.get(analysis_id)['analysis']['document'] == doc
try:
    p.analyses.get(analysis_id)
except ScriptError as error:
    assert error.code == 'not_found'
else:
    raise AssertionError('old handle silently retargeted')
'''
    result = execute(scripts, session, source, project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    store = ProjectStore(directory)
    assert store.info()["revision"] == 2 and len(store.history()) == 2
    assert store.requests.list()["requests"] == []
    assert scripts.events_of("ui.request") == []
    assert [event["revision"] for event in scripts.events_of("project.changed")] == [1, 2]
    assert not scripts.violations


def test_capture_requires_its_own_desktop_capability_without_fallback_to_status(scripts):
    session = scripts.call("script.open")["session"]
    catalog = scripts.call("script.catalog")
    assert "viewer.graph_configuration" in catalog["ui_operations"]
    assert "ui.viewer.graph_configuration" not in catalog["operations"]
    source = '''
from suan.scripting import ScriptError
def rejected(code):
    try:
        stk.viewer.graph_configuration()
    except ScriptError as error:
        assert error.code == code
    else:
        raise AssertionError('capture unexpectedly accepted')
rejected('unavailable')
'''
    assert execute(scripts, session, source)["run"]["state"] == "succeeded"
    scripts.call("ui.attach", {"operations": ["viewer.status", "viewer.presets"]})
    assert execute(scripts, session, "rejected('unsupported')")["run"]["state"] == "succeeded"
    assert scripts.events_of("ui.request") == []


def test_capture_copies_values_and_only_an_explicit_save_creates_project_history(scripts, tmp_path):
    directory = tmp_path / "project"
    info = scripts.call("project.create", {"directory": str(directory), "name": "Capture"})["project"]
    store = ProjectStore(directory); initial = store.snapshot()
    session = scripts.call("script.open")["session"]
    attached = scripts.call("ui.attach", {"operations": ["viewer.graph_configuration"]})["session"]
    response = configuration()
    for index, displayed in enumerate((False, True)):
        mark = scripts.mark()
        source = f"capture = stk.viewer.graph_configuration(displayed={displayed!r})"
        scripts.call("script.execute", {"session": session, "source": source, "project_handle": info["handle"]})
        event = scripts.wait_event(lambda e: e["event"] == "ui.request", start=mark)["data"]
        assert event["operation"] == "viewer.graph_configuration" and event["params"] == {"displayed": displayed}
        reply = {**deepcopy(response), "displayed": displayed}
        assert scripts.call("ui.reply", {"session": attached, "request": event["request"], "result": reply})["accepted"]
        assert settled(scripts, session)["run"]["state"] == "succeeded"
        assert execute(scripts, session, f"assert capture == {reply!r}\n"
                       "capture['configuration']['parameters']['step'] = 99")["run"]["state"] == "succeeded"
        assert store.snapshot() == initial and store.history() == []
    assert response["configuration"]["parameters"] == {"step": "latest"}
    identity = str(uuid4())
    source = f'''
c = capture['configuration']
saved_document = {{'format':'stk.analysis-document/1', 'graph':c['graph'],
                  'parameters':c['parameters'], 'outputs':c['requested_outputs']}}
stk.project.analyses.create('Explicit capture', saved_document, analysis_id={identity!r}, expected_revision=0)
'''
    result = execute(scripts, session, source, project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    saved = store.analyses.get(identity)["analysis"]["document"]
    assert saved["parameters"] == {"step": 99}
    assert set(saved) == {"format", "graph", "parameters", "outputs"}
    assert store.info()["revision"] == 1 and store.requests.list()["requests"] == []
    assert len(scripts.events_of("ui.request")) == 2
    assert [e["revision"] for e in scripts.events_of("project.changed")] == [1]
    assert not scripts.violations


def test_capture_unavailable_definition_and_detached_session_remain_explicit(scripts):
    session = scripts.call("script.open")["session"]
    attached = scripts.call("ui.attach", {"operations": ["viewer.graph_configuration"]})["session"]
    scripts.call("script.execute", {"session": session, "source": "capture = stk.viewer.graph_configuration(displayed=True)"})
    event = scripts.wait_event(lambda e: e["event"] == "ui.request")["data"]
    absent = {"viewer_version": 2, "displayed": True, "displayed_graph_verified": None, "configuration": None}
    assert scripts.call("ui.reply", {"session": attached, "request": event["request"], "result": absent})["accepted"]
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert execute(scripts, session, "assert capture['configuration'] is None")["run"]["state"] == "succeeded"
    mark = scripts.mark()
    scripts.call("script.execute", {"session": session, "source": "stk.viewer.graph_configuration()"})
    event = scripts.wait_event(lambda e: e["event"] == "ui.request", start=mark)["data"]
    assert scripts.call("ui.detach", {"session": attached})["detached"]
    assert settled(scripts, session)["run"]["state"] == "failed"
    assert "unavailable" in scripts.call("script.read", {"session": session})["text"]
    assert scripts.call("ui.reply", {"session": attached, "request": event["request"], "result": configuration()}) == {"accepted": False}
    assert len(scripts.events_of("ui.request")) == 2
