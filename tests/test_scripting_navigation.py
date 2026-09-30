"""Editor navigation uses negotiated reverse UI calls, without replacing project state."""

import pytest

from suan.contracts import load_schema
from suan.desktop_bridge.schema import validate_params
from suan.desktop_bridge.ui_requests import UI_OPERATIONS
from suan.graph.schema import check_value
from suan.project import ProjectStore
from suan.scripting import API
from test_desktop_scripts import scripts, execute, settled  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401


def test_navigation_facade_preserves_explicit_booleans_and_returns_flat_results():
    calls = []
    activated = {"area_id": "a2", "editor_id": "ai", "tab_index": 1, "maximized": False}

    def call(operation, params):
        calls.append((operation, params))
        if operation == "ui.editors.activate":
            return {**activated, "maximized": params["maximize"]}
        return {"restored": False}

    api = API(call)
    assert api.ui.activate_editor("ai") == activated
    assert api.ui.activate_editor("ai", maximize=True) == {**activated, "maximized": True}
    assert api.ui.restore_split_layout() is False
    assert calls == [("ui.editors.activate", {"editor_id": "ai", "maximize": False}),
                     ("ui.editors.activate", {"editor_id": "ai", "maximize": True}),
                     ("ui.layout.unmaximize", {})]
    with pytest.raises(TypeError):
        api.ui.activate_editor("ai", True)
    for invalid in (0, 1, None, "false", []):
        with pytest.raises(TypeError, match="maximize must be a boolean"):
            api.ui.activate_editor("ai", maximize=invalid)
    assert len(calls) == 3


def test_navigation_contracts_are_additive_and_describe_exact_payloads():
    schema = load_schema("desktop-bridge-1")["$defs"]
    assert {"editors.activate", "layout.unmaximize"} <= set(UI_OPERATIONS)
    original = ["layout.get", "layout.apply", "editors.list", "project.current", "project.open", "project.close"]
    assert validate_params("ui.attach", {"operations": original}) == []
    assert validate_params("ui.attach", {"operations": list(UI_OPERATIONS)}) == []
    assert validate_params("ui.attach", {"operations": ["editors.activate", "editors.activate"]})
    params = schema["uiEditorActivationParams"]
    assert check_value({"editor_id": "ai", "maximize": False}, params) == []
    for invalid in ({"editor_id": "ai"}, {"editor_id": "ai", "maximize": 1},
                    {"editor_id": "", "maximize": True}, {"editor_id": "x" * 129, "maximize": True},
                    {"editor_id": "ai", "maximize": True, "window": 2}):
        assert check_value(invalid, params)
    result = {"area_id": "a1", "editor_id": "ai", "tab_index": 15, "maximized": True}
    assert check_value(result, schema["uiEditorActivationResult"]) == []
    for change in ({"area_id": 1}, {"tab_index": 16}, {"tab_index": True}, {"maximized": 1}):
        assert check_value({**result, **change}, schema["uiEditorActivationResult"])
    assert check_value({}, schema["uiLayoutUnmaximizeParams"]) == []
    assert check_value({"window": "second"}, schema["uiLayoutUnmaximizeParams"])
    assert check_value({"restored": True}, schema["uiLayoutUnmaximizeResult"]) == []
    assert check_value({"restored": 1}, schema["uiLayoutUnmaximizeResult"])
    assert check_value({"restored": False, "layout": {}}, schema["uiLayoutUnmaximizeResult"])


def test_navigation_requires_individually_negotiated_capabilities(scripts):
    session = scripts.call("script.open")["session"]
    catalog = scripts.call("script.catalog")
    assert {"editors.activate", "layout.unmaximize"} <= set(catalog["ui_operations"])
    assert not {"editors.activate", "layout.unmaximize", "ui.editors.activate", "ui.layout.unmaximize"} & set(catalog["operations"])
    setup = ("from suan.scripting import ScriptError\n"
             "def rejected(action, code):\n"
             "    try:\n"
             "        action()\n"
             "    except ScriptError as error:\n"
             "        assert error.code == code, str(error)\n"
             "    else:\n"
             "        raise AssertionError('unexpected navigation acceptance')\n"
             "rejected(lambda: stk.ui.activate_editor('ai'), 'unavailable')\n"
             "rejected(stk.ui.restore_split_layout, 'unavailable')")
    assert execute(scripts, session, setup)["run"]["state"] == "succeeded"
    old = scripts.call("ui.attach", {"operations": ["layout.get", "layout.apply", "editors.list"]})["session"]
    assert execute(scripts, session, "rejected(lambda: stk.ui.activate_editor('ai'), 'unsupported')\n"
                   "rejected(stk.ui.restore_split_layout, 'unsupported')")["run"]["state"] == "succeeded"
    assert scripts.call("ui.detach", {"session": old})["detached"]
    scripts.call("ui.attach", {"operations": ["editors.activate"]})
    assert execute(scripts, session, "rejected(stk.ui.restore_split_layout, 'unsupported')")["run"]["state"] == "succeeded"
    assert scripts.events_of("ui.request") == []


def test_real_worker_navigation_roundtrip_does_not_write_or_send_model_requests(scripts, tmp_path):
    directory = tmp_path / "navigation"
    info = scripts.call("project.create", {"directory": str(directory), "name": "Navigation"})["project"]
    store = ProjectStore(directory)
    before, history, requests = store.snapshot(), store.history(), store.requests.list()
    session = scripts.call("script.open")["session"]
    ui = scripts.call("ui.attach", {"operations": ["editors.activate", "layout.unmaximize"]})["session"]
    operations = [
        ("selected = stk.ui.activate_editor('ai', maximize=True)", "editors.activate",
         {"editor_id": "ai", "maximize": True}, {"area_id": "a3", "editor_id": "ai", "tab_index": 2, "maximized": True},
         "assert selected == {'area_id':'a3', 'editor_id':'ai', 'tab_index':2, 'maximized':True}"),
        ("restored = stk.ui.restore_split_layout()", "layout.unmaximize", {}, {"restored": True}, "assert restored is True"),
        ("restored = stk.ui.restore_split_layout()", "layout.unmaximize", {}, {"restored": False}, "assert restored is False"),
        ("selected = stk.ui.activate_editor('project')", "editors.activate", {"editor_id": "project", "maximize": False},
         {"area_id": "a1", "editor_id": "project", "tab_index": 0, "maximized": False}, "assert selected['maximized'] is False"),
    ]
    for source, operation, params, result, assertion in operations:
        mark = scripts.mark()
        scripts.call("script.execute", {"session": session, "source": source, "project_handle": info["handle"]})
        request = scripts.wait_event(lambda event: event["event"] == "ui.request", start=mark)["data"]
        assert request["session"] == ui and request["operation"] == operation and request["params"] == params
        assert scripts.call("ui.reply", {"session": ui, "request": request["request"], "result": result})["accepted"]
        assert settled(scripts, session)["run"]["state"] == "succeeded"
        assert execute(scripts, session, assertion)["run"]["state"] == "succeeded"
    assert store.snapshot() == before and store.history() == history and store.requests.list() == requests
    assert scripts.events_of("project.changed") == [] and scripts.events_of("project.closed") == []
    assert [event["operation"] for event in scripts.events_of("ui.request")] == [row[1] for row in operations]


@pytest.mark.parametrize("code", ["invalid_params", "busy", "unavailable"])
def test_navigation_native_rejection_is_returned_without_retry(scripts, code):
    session = scripts.call("script.open")["session"]
    ui = scripts.call("ui.attach", {"operations": ["editors.activate"]})["session"]
    source = ("from suan.scripting import ScriptError\n"
              "try:\n"
              "    stk.ui.activate_editor('ai')\n"
              "except ScriptError as error:\n"
              f"    assert error.code == {code!r}\n"
              "else:\n"
              "    raise AssertionError('expected rejected navigation')")
    scripts.call("script.execute", {"session": session, "source": source})
    request = scripts.wait_event(lambda event: event["event"] == "ui.request")["data"]
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"],
        "error": {"code": code, "message": "Navigation rejected", "retryable": False}})["accepted"]
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert len(scripts.events_of("ui.request")) == 1


def test_navigation_detach_rejects_pending_call_and_late_reply(scripts):
    session = scripts.call("script.open")["session"]
    ui = scripts.call("ui.attach", {"operations": ["layout.unmaximize"]})["session"]
    scripts.call("script.execute", {"session": session, "source": "stk.ui.restore_split_layout()"})
    request = scripts.wait_event(lambda event: event["event"] == "ui.request")["data"]
    assert scripts.call("ui.detach", {"session": ui})["detached"]
    assert settled(scripts, session)["run"]["state"] == "failed"
    assert "unavailable" in scripts.call("script.read", {"session": session})["text"]
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"], "result": {"restored": True}}) == {"accepted": False}
    assert len(scripts.events_of("ui.request")) == 1
