"""Viewer automation is explicit; waiting observes one source and never cancels its work."""
from copy import deepcopy

import pytest

from suan.scripting import API


def status(**changes):
    return {"source": {"key": "payload|one", "kind": "payload"}, "evaluating": False, "pending_edit": "",
            "has_payload": True, "error": "", "metadata_error": "", **changes}


def test_helpers_keep_explicit_source_guard_and_resolve_local_paths(tmp_path, monkeypatch):
    calls = []
    def call(name, params):
        calls.append((name, params))
        return status()
    stk = API(call)
    monkeypatch.chdir(tmp_path)
    stk.viewer.open("result", preset="volume", parameters={"path": "field.vtk"}, focus=False)
    assert calls[-1] == ("ui.viewer.open", {"path": str(tmp_path / "result"), "preset": "volume", "parameters": {"path": "field.vtk"}, "focus": False})
    stk.viewer.configure(parameters={"colormap": "cividis"}, auto_evaluate=False, expected_source="payload|one")
    assert calls[-1][1] == {"parameters": {"colormap": "cividis"}, "auto_evaluate": False, "expected_source": "payload|one"}
    stk.viewer.layer("mesh", visible=False, opacity=0, expected_source="payload|one")
    assert calls[-1][1] == {"id": "mesh", "visible": False, "opacity": 0, "expected_source": "payload|one"}
    stk.viewer.play(False)
    assert calls[-1] == ("ui.viewer.play", {"playing": False})
    for action in (stk.viewer.cancel, stk.viewer.close, stk.viewer.evaluate, stk.viewer.reset_camera):
        action(expected_source="payload|one")
        assert calls[-1][1] == {"expected_source": "payload|one"}


def test_wait_uses_only_status_and_does_not_return_old_payload_while_pending():
    states = [status(evaluating=True), status(pending_edit="data"), status()]
    calls = []
    def call(name, params):
        calls.append(name)
        return states.pop(0)
    answer = API(call).viewer.wait(timeout=1, interval=.001)
    assert answer == status() and calls == ["ui.viewer.status"] * 3


def test_wait_timeout_change_and_error_preserve_viewer_work():
    calls = []
    def call(name, params):
        calls.append(name)
        return status(evaluating=True)
    with pytest.raises(TimeoutError, match="without cancelling"):
        API(call).viewer.wait(timeout=0)
    assert calls == ["ui.viewer.status"]
    values = [status(evaluating=True), status(source={"key": "payload|two", "kind": "payload"})]
    with pytest.raises(RuntimeError, match="source changed"):
        API(lambda name, params: values.pop(0)).viewer.wait(timeout=1, interval=.001)
    failed = status(has_payload=False, error="The file is missing")
    assert API(lambda name, params: deepcopy(failed)).viewer.wait(timeout=0) == failed
    for kwargs in ({"timeout": -1}, {"timeout": True}, {"timeout": float("inf")}, {"interval": 0}, {"interval": False}):
        with pytest.raises(ValueError):
            API(call).viewer.wait(**kwargs)


def test_all_advertised_desktop_operations_fit_the_shared_attach_contract():
    from suan.desktop_bridge.schema import validate_params
    from suan.desktop_bridge.ui_requests import UI_OPERATIONS
    assert validate_params("ui.attach", {"operations": list(UI_OPERATIONS)}) == []
    assert validate_params("ui.attach", {"operations": ["viewer.status", "viewer.status"]})
    assert validate_params("ui.attach", {"operations": ["viewer.unknown"]})
