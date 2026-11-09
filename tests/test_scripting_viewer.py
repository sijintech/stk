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


def test_collected_open_preserves_the_lexical_path_and_source_proof(tmp_path):
    calls = []
    viewer = API(lambda name, params: calls.append((name, params))).viewer
    root = tmp_path / "case"
    root.mkdir()
    proof = {"project_root": str(tmp_path), "case_path": "case",
             "files": [{"path": "case/a.dat", "sha256": "a" * 64}]}
    viewer.open(root, source_proof=proof)
    assert calls[-1] == ("ui.viewer.open", {"path": str(root), "focus": True, "source_proof": proof})


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


def opening(*, request="opening-2", state="pending", target="payload|two"):
    return {"id": request, "state": state,
            "source": {"key": target, "kind": "payload", "path": "/two"}}


def scripted_viewer(*states):
    remaining = iter(states)
    calls = []

    def call(name, params):
        calls.append((name, params))
        return deepcopy(next(remaining))

    return API(call).viewer, calls


@pytest.mark.parametrize("target", ["payload|one", "payload|two"])
def test_wait_follows_only_its_verified_opening_including_same_source_reopen(target):
    ready = status(source={"key": target, "kind": "payload"},
                   opening=opening(state="succeeded", target=target))
    viewer, calls = scripted_viewer(
        status(evaluating=True, pending_edit="data", opening=opening(target=target)),
        # An old displayed payload is not evidence that the opening finished.
        status(opening=opening(target=target)),
        ready,
    )
    assert viewer.wait(timeout=1, interval=.001) == ready
    assert calls == [("ui.viewer.status", {})] * 3


@pytest.mark.parametrize("already_failed", [False, True])
def test_wait_returns_failed_opening_with_previous_payload_and_unsent_draft(already_failed):
    failed = status(pending_edit="data", error="Opening /two failed: content digest mismatch",
                    opening=opening(state="failed"))
    states = [failed] if already_failed else [status(evaluating=True, opening=opening()), failed]
    viewer, calls = scripted_viewer(*states)
    assert viewer.wait(timeout=1, interval=.001) == failed
    assert calls == [("ui.viewer.status", {})] * len(states)


@pytest.mark.parametrize("replacement", [
    opening(state="cancelled"),
    None,
    opening(request="opening-3"),
    opening(request="opening-3", state="succeeded"),
])
def test_wait_does_not_follow_cancelled_or_replaced_opening_even_for_the_same_target(replacement):
    viewer, calls = scripted_viewer(
        status(evaluating=True, opening=opening()),
        status(opening=replacement),
    )
    with pytest.raises(RuntimeError, match="opening.*cancelled or replaced"):
        viewer.wait(timeout=1, interval=.001)
    assert calls == [("ui.viewer.status", {})] * 2


@pytest.mark.parametrize("changed", [
    status(source={"key": "payload|three", "kind": "payload"}, opening=opening()),
    status(source={"key": "payload|three", "kind": "payload"}, opening=opening(state="succeeded")),
    status(source={"key": "payload|two", "kind": "payload"}, opening=opening(state="failed")),
])
def test_wait_rejects_unrelated_source_changes_during_its_opening(changed):
    viewer, calls = scripted_viewer(status(evaluating=True, opening=opening()), changed)
    with pytest.raises(RuntimeError, match="source changed"):
        viewer.wait(timeout=1, interval=.001)
    assert calls == [("ui.viewer.status", {})] * 2


def test_wait_rejects_a_target_change_even_with_the_same_opening_id():
    viewer, calls = scripted_viewer(
        status(evaluating=True, opening=opening()),
        status(opening=opening(target="payload|three")),
    )
    with pytest.raises(RuntimeError, match="opening.*cancelled or replaced"):
        viewer.wait(timeout=1, interval=.001)
    assert calls == [("ui.viewer.status", {})] * 2


def test_wait_does_not_adopt_an_opening_started_after_waiting_began():
    viewer, calls = scripted_viewer(status(evaluating=True), status(opening=opening()))
    with pytest.raises(RuntimeError, match="opening.*cancelled or replaced"):
        viewer.wait(timeout=1, interval=.001)
    assert calls == [("ui.viewer.status", {})] * 2


def test_wait_accepts_an_already_successful_opening_and_rejects_an_inconsistent_source():
    ready = status(opening=opening(state="succeeded", target="payload|one"))
    viewer, calls = scripted_viewer(ready)
    assert viewer.wait(timeout=0) == ready
    assert calls == [("ui.viewer.status", {})]
    viewer, calls = scripted_viewer(status(opening=opening(state="succeeded")))
    with pytest.raises(RuntimeError, match="source changed"):
        viewer.wait(timeout=0)
    assert calls == [("ui.viewer.status", {})]


def test_wait_timeout_and_already_cancelled_opening_never_mutate_viewer_work():
    viewer, calls = scripted_viewer(status(opening=opening()))
    with pytest.raises(TimeoutError, match="without cancelling"):
        viewer.wait(timeout=0)
    assert calls == [("ui.viewer.status", {})]
    viewer, calls = scripted_viewer(status(opening=opening(state="cancelled")))
    with pytest.raises(RuntimeError, match="opening.*cancelled or replaced"):
        viewer.wait(timeout=0)
    assert calls == [("ui.viewer.status", {})]


def test_all_advertised_desktop_operations_fit_the_shared_attach_contract():
    from suan.desktop_bridge.schema import validate_params
    from suan.desktop_bridge.ui_requests import UI_OPERATIONS
    assert validate_params("ui.attach", {"operations": list(UI_OPERATIONS)}) == []
    assert validate_params("ui.attach", {"operations": ["viewer.status", "viewer.status"]})
    assert validate_params("ui.attach", {"operations": ["viewer.unknown"]})
