"""Read-only compilation evidence and source binding through the actual bridge."""
import base64
from copy import deepcopy
import hashlib
import json
import subprocess

import pytest

from suan.desktop_bridge.schema import validate_params
from suan.documents import latex
from suan.scripting import API
from suan.workflows import templates
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_latex_compile import compiler_fixture  # noqa: F401
from test_workflow_latex import selection, prepare, open_bridge  # noqa: F401
from test_bridge_workflow_runs import settled


@pytest.fixture
def evidence(selection, compiler_fixture, inproc):
    store, row, _, _ = selection
    compiler_fixture[0].write_text("failed")
    run = prepare(selection)
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    settled(h, handle, run["id"])
    identity = {"handle": handle, "run_id": run["id"], "step": "compile", "row": row, "attempt": 1}
    return store, h, identity, compiler_fixture


def test_read_failed_receipt_paginated_logs_and_source_never_executes(evidence, monkeypatch):
    store, h, identity, compiler = evidence
    before, history = store.snapshot(), store.history()
    trace = compiler[1].read_bytes()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("inspection executed a process"))
    result = h.call("project.workflow_runs.compilation", identity)
    receipt = result["receipt"]
    assert receipt["state"] == "failed" and receipt["exit_code"] == 9
    assert len(receipt["diagnostics"]) == 2
    assert {item["path"] for item in receipt["diagnostics"]} == {"sub/章节.tex", "main.tex"}
    assert "runner" not in receipt and "owner" not in receipt
    page, raw = 0, b""
    while True:
        value = h.call("project.workflow_runs.compilation_log", {**identity, "offset": page, "limit": 7})
        selected = base64.b64decode(value["data"], validate=True)
        assert value["offset"] == page and value["next_offset"] == page + len(selected) and value["terminal"]
        raw += selected
        page = value["next_offset"]
        if len(selected) < 7:
            break
    entry = next(item for item in receipt["files"] if item["path"] == "stdout.txt")
    assert len(raw) == entry["size"] and hashlib.sha256(raw).hexdigest() == entry["sha256"]
    source = h.call("project.workflow_runs.compilation_source", {**identity, "diagnostic": 0, "expected_revision": store.info()["revision"]})
    assert source["path"] == str(store.directory / "章节.tex")
    assert (source["line"], source["column"]) == (7, 3)
    assert compiler[1].read_bytes() == trace and store.snapshot() == before and store.history() == history
    assert not h.violations


def test_changed_missing_or_wrong_revision_source_is_refused(evidence):
    store, h, identity, _ = evidence
    params = {**identity, "diagnostic": 0, "expected_revision": store.info()["revision"]}
    assert h.error("project.workflow_runs.compilation_source", {**params, "expected_revision": 0})["code"] == "conflict"
    source = store.directory / "章节.tex"
    source.write_text("changed after the compilation", encoding="utf-8")
    assert "changed since compilation" in h.error("project.workflow_runs.compilation_source", params)["message"]
    source.unlink()
    assert h.error("project.workflow_runs.compilation_source", params)["code"] == "invalid_params"
    # The failure log remains readable even after all working inputs disappear.
    assert h.call("project.workflow_runs.compilation", identity)["receipt"]["state"] == "failed"
    assert base64.b64decode(h.call("project.workflow_runs.compilation_log", identity)["data"])


def test_attempt_selection_and_corrupt_terminal_log_are_refused(evidence):
    store, h, identity, _ = evidence
    assert h.error("project.workflow_runs.compilation", {**identity, "attempt": 2})["code"] == "invalid_params"
    assert h.error("project.workflow_runs.compilation", {**identity, "step": "input"})["code"] == "invalid_params"
    location = store.workflow_runs.local_attempt(identity["run_id"], identity["step"], identity["row"], 1)
    (store.directory / location["directory"] / "stdout.txt").write_text("tampered", encoding="utf-8")
    assert h.error("project.workflow_runs.compilation_log", identity)["code"] == "invalid_params"


def receipt_file(store, identity):
    location = store.workflow_runs.local_attempt(**{key: identity[key] for key in ("run_id", "step", "row", "attempt")})
    return store.directory / location["directory"] / "compile.json", location


def refuse_every_read(store, h, identity, message):
    for action in ("compilation", "compilation_log", "compilation_source"):
        params = dict(identity)
        if action == "compilation_source":
            params.update(diagnostic=0, expected_revision=store.info()["revision"])
        error = h.error("project.workflow_runs." + action, params)
        assert error["code"] == "invalid_params", error
        assert message in error["message"], error
    assert not h.violations


def replacement_inputs(store, original):
    paths = []
    for number, asset in enumerate(original["assets"]):
        path = store.directory / f"replacement-{number}.tex"
        path.write_text(f"different frozen source {number}\n", encoding="utf-8")
        paths.append(str(path))
    records = store.files.index(paths, expected_revision=store.info()["revision"])["record_ids"]
    snapshot = store.snapshots.capture(records, expected_revision=store.info()["revision"])["snapshot"]
    return latex.freeze_inputs(store, snapshot["id"],
        [{"record_id": record, "path": asset["path"]} for record, asset in zip(records, original["assets"])],
        entry_path=original["entry_path"], expected_revision=store.info()["revision"])


def substitute_inputs(receipt, inputs):
    receipt["inputs"], receipt["inputs_sha256"] = inputs, latex._sha(inputs)
    by_path = {asset["path"]: asset for asset in inputs["assets"]}
    for diagnostic in receipt["diagnostics"]:
        source = by_path[diagnostic["path"]]
        diagnostic.update(record_id=source["record_id"], source_sha256=source["sha256"])


@pytest.mark.parametrize("field,value", [("engine", "xelatex"), ("sha256", "b" * 64)])
def test_valid_but_different_compiler_is_not_this_workflow_evidence(evidence, monkeypatch, field, value):
    store, h, identity, compiler = evidence
    path, location = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["compiler"][field] = value
    path.write_text(json.dumps(receipt), encoding="utf-8")
    # It remains a valid independent compiler receipt; the workflow binding must reject it.
    assert latex.read_receipt(store, **location)["compiler"][field] == value
    before, history, trace = store.snapshot(), store.history(), compiler[1].read_bytes()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("inspection executed a process"))
    refuse_every_read(store, h, identity, "compiler differs")
    assert store.snapshot() == before and store.history() == history and compiler[1].read_bytes() == trace


def test_valid_same_project_snapshot_cannot_replace_static_frozen_input(evidence, monkeypatch):
    store, h, identity, _ = evidence
    path, location = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    substitute_inputs(receipt, replacement_inputs(store, receipt["inputs"]))
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert latex.read_receipt(store, **location)["inputs"] == receipt["inputs"]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("inspection executed a process"))
    refuse_every_read(store, h, identity, "inputs differ from the frozen workflow")


def test_another_attempt_receipt_cannot_be_read_under_the_old_attempt(evidence):
    store, h, identity, _ = evidence
    path, _ = receipt_file(store, identity)
    old = path.read_bytes()
    h.call("project.workflow_runs.start", {"handle": identity["handle"], "run_id": identity["run_id"]})
    settled(h, identity["handle"], identity["run_id"])
    second = {**identity, "attempt": 2}
    second_path, _ = receipt_file(store, second)
    path.write_bytes(second_path.read_bytes())
    refuse_every_read(store, h, identity, "identity does not match")
    assert h.call("project.workflow_runs.compilation", second)["receipt"]["state"] == "failed"
    path.write_bytes(old)


@pytest.fixture
def dynamic_evidence(selection, compiler_fixture, inproc, monkeypatch):
    class Source:
        id, name, local, table_id = "fixture-tex-evidence/1", "Controlled TeX source", True, None
        parameters, outputs = [], ["main.tex", "章节.tex"]

        def run(self, parameters, directory):
            directory.mkdir()
            (directory / "main.tex").write_text("good", encoding="utf-8")
            (directory / "章节.tex").write_text("selected source\n", encoding="utf-8")

    store, row, workflow, document = selection
    monkeypatch.setitem(templates.LOCAL_TEMPLATES, Source.id, Source())
    document["steps"][1] = {"id": "input", "kind": "simulation", "ref": {"template": Source.id},
                            "inputs": {"rows": {"from": "rows.rows"}}}
    store.workflows.update(workflow, "Generated files", document, expected_revision=store.info()["revision"])
    compiler_fixture[0].write_text("failed")
    run = prepare(selection)
    assert run["steps"]["compile"]["prepared"][row]["inputs"] is None
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert next(task for task in done["tasks"] if task["step"] == "input")["status"] == "succeeded"
    identity = {"handle": handle, "run_id": run["id"], "step": "compile", "row": row, "attempt": 1}
    return store, h, identity, compiler_fixture


def test_dynamic_inputs_are_bound_to_the_original_upstream_snapshot(dynamic_evidence, monkeypatch):
    store, h, identity, _ = dynamic_evidence
    path, location = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert h.call("project.workflow_runs.compilation", identity)["receipt"]["state"] == "failed"
    substitute_inputs(receipt, replacement_inputs(store, receipt["inputs"]))
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert latex.read_receipt(store, **location)["inputs"] == receipt["inputs"]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("inspection executed a process"))
    refuse_every_read(store, h, identity, "historical upstream files")


@pytest.mark.parametrize("change", ["records", "paths", "entry"])
def test_same_snapshot_cannot_rebind_dynamic_selection(dynamic_evidence, change):
    store, h, identity, _ = dynamic_evidence
    path, location = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    inputs = deepcopy(receipt["inputs"])
    if change == "records":
        original = deepcopy(inputs["assets"])
        for selected, other in zip(inputs["assets"], reversed(original)):
            selected.update({key: other[key] for key in ("record_id", "sha256", "size")})
    elif change == "paths":
        inputs["assets"][1]["path"] = "moved/chapter.tex"
        for diagnostic in receipt["diagnostics"]:
            if diagnostic["path"] == "sub/章节.tex":
                diagnostic["path"] = "moved/chapter.tex"
    else:
        inputs["entry_path"] = "sub/章节.tex"
    substitute_inputs(receipt, inputs)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert latex.read_receipt(store, **location)["inputs"] == inputs
    refuse_every_read(store, h, identity, "historical upstream files")


def test_later_upstream_journal_events_do_not_retarget_an_earlier_compile(dynamic_evidence, monkeypatch):
    store, h, identity, _ = dynamic_evidence
    path, _ = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    original = deepcopy(receipt["inputs"])
    replacement = replacement_inputs(store, original)
    # Deliberately append a later, hash-chained source observation. Historical
    # inspection must use the prefix at compile start, never the latest task state.
    files = {"main.tex": replacement["assets"][0]["record_id"], "章节.tex": replacement["assets"][1]["record_id"]}
    with store._connect(write=True) as db:
        store.workflow_runs._append(db, identity["run_id"], "input", identity["row"], 2, "running", {})
        store.workflow_runs._append(db, identity["run_id"], "input", identity["row"], 2, "succeeded",
            {"produced": {"snapshot_id": replacement["snapshot_id"], "files": files}})
    evidence = store.workflow_runs.compilation_evidence(**{key: identity[key] for key in ("run_id", "step", "row", "attempt")})
    assert evidence["source_attempt"] == 1 and evidence["source"]["snapshot_id"] == original["snapshot_id"]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("inspection executed a process"))
    assert h.call("project.workflow_runs.compilation", identity)["receipt"]["snapshot_id"] == original["snapshot_id"]
    substitute_inputs(receipt, replacement)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    refuse_every_read(store, h, identity, "historical upstream files")


def test_log_rechecks_the_binding_on_the_receipt_it_actually_reads(evidence, monkeypatch):
    store, h, identity, _ = evidence
    path, _ = receipt_file(store, identity)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    changed = deepcopy(receipt)
    changed["compiler"]["engine"] = "xelatex"
    read_log = latex.read_log

    def replace_then_read(*args, **kwargs):
        path.write_text(json.dumps(changed), encoding="utf-8")
        return read_log(*args, **kwargs)

    monkeypatch.setattr(latex, "read_log", replace_then_read)
    error = h.error("project.workflow_runs.compilation_log", identity)
    assert error["code"] == "invalid_params" and "bound compiler or inputs" in error["message"]


def test_log_allows_a_normal_running_to_terminal_receipt_publication(evidence, monkeypatch):
    store, h, identity, _ = evidence
    path, _ = receipt_file(store, identity)
    terminal = json.loads(path.read_text(encoding="utf-8"))
    running = {**terminal, "state": "running", "reason": None, "exit_code": None, "files": [], "diagnostics": []}
    path.write_text(json.dumps(running), encoding="utf-8")
    read_log = latex.read_log

    def finish_then_read(*args, **kwargs):
        path.write_text(json.dumps(terminal), encoding="utf-8")
        return read_log(*args, **kwargs)

    monkeypatch.setattr(latex, "read_log", finish_then_read)
    result = h.call("project.workflow_runs.compilation_log", identity)
    assert result["terminal"] and b"selected source diagnostic" in base64.b64decode(result["data"])
    assert not h.violations


@pytest.mark.parametrize("changes", [{"attempt": 0}, {"attempt": True}, {"step": "../outside"}, {"directory": "/tmp"},
    {"stream": "../compile.json"}, {"limit": 65537}, {"offset": -1}])
def test_log_schema_refuses_arbitrary_paths_and_unbounded_pages(changes):
    params = {"handle": "a" * 32, "run_id": "00000000-0000-0000-0000-000000000001", "step": "compile",
              "row": "00000000-0000-0000-0000-000000000002", "attempt": 1}
    assert validate_params("project.workflow_runs.compilation_log", {**params, **changes})


def test_scripting_facade_retains_original_handle_and_explicit_attempts():
    calls = []
    api = API(lambda method, params: calls.append((method, params)) or params)
    api._project_handle = "a" * 32
    runs = api.project.workflow_runs
    runs.compilation("run", "compile", "row", 2)
    runs.compilation_log("run", "compile", "row", 1, stream="compiler.txt", offset=7, limit=11)
    api._project_handle = "b" * 32
    runs.compilation_source("run", "compile", "row", 1, 0, expected_revision=5)
    assert [method for method, _ in calls] == ["project.workflow_runs.compilation", "project.workflow_runs.compilation_log", "project.workflow_runs.compilation_source"]
    assert all(params["handle"] == "a" * 32 for _, params in calls)
    assert calls[1][1]["offset"] == 7 and calls[1][1]["limit"] == 11 and calls[2][1]["expected_revision"] == 5
