"""Pinned Python selection requests use the desktop executor, never project edits."""

from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.schema import validate_params
from suan.desktop_bridge.ui_requests import UI_OPERATIONS, UIRequests
from suan.project import ProjectStore
from suan.scripting import API, ScriptError
from test_desktop_scripts import scripts, execute, settled  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401


def test_selection_helpers_keep_the_held_handle_and_forward_explicit_identity_only():
    calls = []
    result = {"project_id": str(uuid4()), "revision": 7, "table_id": str(uuid4()), "record_id": str(uuid4())}
    def call(operation, params):
        calls.append((operation, params))
        return result
    api = API(call)
    with pytest.raises(ScriptError, match="No project"):
        api.project.selection()
    api._project_handle = "a" * 32
    original = api.project
    api._project_handle = "b" * 32
    assert original.selection() == result
    assert original.select(result["table_id"], result["record_id"], expected_revision=7) == result
    assert calls == [("ui.project.selection", {"handle": "a" * 32}),
                     ("ui.project.select", {"handle": "a" * 32, "expected_revision": 7,
                                            "table_id": result["table_id"], "record_id": result["record_id"]})]
    # Omitted identities/revisions cannot become an implicit current-row operation.
    with pytest.raises(TypeError):
        original.select(result["table_id"], expected_revision=7)
    with pytest.raises(TypeError):
        original.select(result["table_id"], result["record_id"])
    assert len(calls) == 2


def test_original_six_and_all_twenty_one_desktop_capabilities_fit_attach_schema():
    original = ["layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close"]
    assert len(UI_OPERATIONS) == 21 and {"project.selection", "project.select"} <= set(UI_OPERATIONS)
    assert validate_params("ui.attach", {"operations": original}) == []
    assert validate_params("ui.attach", {"operations": list(UI_OPERATIONS)}) == []
    assert validate_params("ui.attach", {"operations": ["project.selection", "project.selection"]})
    assert validate_params("ui.attach", {"operations": ["project.unknown"]})


def test_worker_selection_requires_desktop_and_individually_negotiated_capabilities(scripts, tmp_path):
    info = scripts.call("project.create", {"directory": str(tmp_path / "project"), "name": "Selection"})["project"]
    session = scripts.call("script.open")["session"]
    catalog = scripts.call("script.catalog")
    assert {"project.selection", "project.select"} <= set(catalog["ui_operations"])
    assert not {"project.selection", "project.select", "ui.project.selection", "ui.project.select"} & set(catalog["operations"])
    setup = ("p = stk.project\nfrom suan.scripting import ScriptError\n"
             "def rejected(code):\n"
             "    for action in [p.selection, lambda: p.select('11111111-1111-4111-8111-111111111111', "
             "'22222222-2222-4222-8222-222222222222', expected_revision=0)]:\n"
             "        try:\n"
             "            action()\n"
             "        except ScriptError as error:\n"
             "            assert error.code == code, str(error)\n"
             "        else:\n"
             "            raise AssertionError('unexpected acceptance')\n"
             "rejected('unavailable')")
    assert execute(scripts, session, setup, project_handle=info["handle"])["run"]["state"] == "succeeded"
    original = ["layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close"]
    old = scripts.call("ui.attach", {"operations": original})["session"]
    assert execute(scripts, session, "rejected('unsupported')")["run"]["state"] == "succeeded"
    assert scripts.events_of("ui.request") == []
    assert scripts.call("ui.detach", {"session": old})["detached"]
    attached = scripts.call("ui.attach", {"operations": list(UI_OPERATIONS)})
    assert set(attached["operations"]) == set(UI_OPERATIONS)
    assert scripts.events_of("project.changed") == []
    assert scripts.call("project.snapshot", {"handle": info["handle"]})["snapshot"]["tables"] == []


def test_real_worker_selection_transports_results_without_retarget_or_persistence(scripts, tmp_path):
    first = scripts.call("project.create", {"directory": str(tmp_path / "first"), "name": "First"})["project"]
    second = scripts.call("project.create", {"directory": str(tmp_path / "second"), "name": "Second"})["project"]
    session = scripts.call("script.open")["session"]
    assert execute(scripts, session, "p = stk.project", project_handle=first["handle"])["run"]["state"] == "succeeded"
    ui = scripts.call("ui.attach", {"operations": ["project.selection", "project.select"]})["session"]
    store = ProjectStore(tmp_path / "first")
    before, history = store.snapshot(), store.history()
    mark = scripts.mark()
    scripts.call("script.execute", {"session": session, "project_handle": second["handle"],
                                     "source": "selection = p.selection()\nexecution_project = stk.project.handle"})
    request = scripts.wait_event(lambda event: event["event"] == "ui.request", start=mark)["data"]
    assert request["session"] == ui and request["operation"] == "project.selection"
    assert request["params"] == {"handle": first["handle"]}
    selected = {"project_id": first["id"], "revision": 0, "table_id": None, "record_id": None}
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"], "result": selected})["accepted"]
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert execute(scripts, session, f"assert selection == {selected!r}\nassert execution_project == {second['handle']!r}")['run']['state'] == 'succeeded'

    # Fake UI transport here; real object membership/atomic native validation is
    # covered by ScriptPython desktop tests, not performed by the worker facade.
    table_id, record_id = str(uuid4()), str(uuid4())
    mark = scripts.mark()
    scripts.call("script.execute", {"session": session,
        "source": f"chosen = p.select({table_id!r}, {record_id!r}, expected_revision=selection['revision'])"})
    request = scripts.wait_event(lambda event: event["event"] == "ui.request", start=mark)["data"]
    assert request["operation"] == "project.select" and request["params"] == {
        "handle": first["handle"], "expected_revision": 0, "table_id": table_id, "record_id": record_id}
    chosen = {**selected, "table_id": table_id, "record_id": record_id}
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"], "result": chosen})["accepted"]
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert execute(scripts, session, f"assert chosen == {chosen!r}")['run']['state'] == 'succeeded'
    assert store.snapshot() == before and store.history() == history
    assert scripts.events_of("project.changed") == [] and scripts.events_of("project.closed") == []
    assert [event["operation"] for event in scripts.events_of("ui.request")] == ["project.selection", "project.select"]


def test_worker_select_propagates_native_conflict_without_retry(scripts, tmp_path):
    info = scripts.call("project.create", {"directory": str(tmp_path / "project"), "name": "Selection"})["project"]
    session = scripts.call("script.open")["session"]
    assert execute(scripts, session, "p = stk.project", project_handle=info["handle"])["run"]["state"] == "succeeded"
    ui = scripts.call("ui.attach", {"operations": ["project.select"]})["session"]
    source = ("from suan.scripting import ScriptError\n"
              "try:\n"
              "    p.select('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222', expected_revision=0)\n"
              "except ScriptError as error:\n"
              "    assert error.code == 'conflict'\n"
              "else:\n"
              "    raise AssertionError('expected stale selection')")
    scripts.call("script.execute", {"session": session, "source": source})
    request = scripts.wait_event(lambda event: event["event"] == "ui.request")["data"]
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"],
        "error": {"code": "conflict", "message": "The visible project changed", "retryable": False}})["accepted"]
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert len(scripts.events_of("ui.request")) == 1 and scripts.events_of("project.changed") == []


def test_selection_cancellation_and_timeout_drop_late_replies_without_reissuing():
    emitted, ready, cancelled = [], threading.Event(), threading.Event()
    def emit(event, data):
        emitted.append((event, data))
        ready.set()
    requests = UIRequests(emit)
    session = requests.attach({"operations": ["project.selection", "project.select"]})["session"]
    params = {"handle": "a" * 32, "expected_revision": 0, "table_id": str(uuid4()), "record_id": str(uuid4())}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(requests.call, "project.select", params, cancelled)
        assert ready.wait(5)
        cancelled.set()
        with pytest.raises(BridgeError) as failure:
            pending.result(timeout=5)
        assert failure.value.code == "cancelled"
    assert len(emitted) == 1 and emitted[0][1]["params"] == params and not requests.pending
    assert requests.reply({"session": session, "request": emitted[0][1]["request"], "result": {}}) == {"accepted": False}
    with pytest.raises(BridgeError) as failure:
        requests.call("project.selection", {"handle": "a" * 32}, threading.Event(), timeout=0)
    assert failure.value.code == "timeout" and len(emitted) == 2 and not requests.pending
    assert requests.reply({"session": session, "request": emitted[1][1]["request"], "result": {}}) == {"accepted": False}
    requests.close()
