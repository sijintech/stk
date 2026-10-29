"""LaTeX through the persisted workflow and bridge, with a controlled real process.

The compiler fixture substitutes the program body only; the independent executor's
process gate, frozen copies, cancellation, receipts and log limits are real.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from suan.documents import latex
from suan.project import ProjectStore, ProjectError
from suan.workflows import templates
from suan.workflows.latex import LatexCompileTemplate
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_bridge_workflow_runs import settled
from test_latex_compile import compiler_fixture, until  # noqa: F401


@pytest.fixture
def selection(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Frozen LaTeX workflow")
    table, row, workflow = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": table, "name": "Documents"},
                 {"op": "add_record", "id": row, "table_id": table}], expected_revision=0)
    paths = []
    for name, text in (("main.tex", "good"), ("章节.tex", "selected source\n")):
        path = store.directory / name
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    records = store.files.index(paths, expected_revision=1)["record_ids"]
    snapshot = store.snapshots.capture(records, expected_revision=2)["snapshot"]
    document = {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "rows", "kind": "table", "ref": {"table": table}},
        {"id": "input", "kind": "files", "ref": {"snapshot": snapshot["id"]}},
        {"id": "compile", "kind": "simulation", "ref": {"template": "latex-compile/1"},
         "inputs": {"rows": {"from": "rows.rows"}, "files": {"from": "input.files"}},
         "parameters": {"compiler_path": sys.executable, "assets": [
             {"source": "main.tex", "path": "main.tex"}, {"source": "章节.tex", "path": "sub/章节.tex"}]}}]}
    store.workflows.create("Compile", document, workflow_id=workflow, expected_revision=3)
    return store, row, workflow, document


def prepare(selection):
    store, row, workflow, _ = selection
    return store.workflow_runs.prepare(workflow, [row], run_id=str(uuid4()), expected_revision=store.info()["revision"])


def open_bridge(inproc, store):
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    return h, handle


def compile_task(run):
    return next(task for task in run["tasks"] if task["step"] == "compile")


def test_ports_and_prepare_are_metadata_only(selection, monkeypatch):
    store, row, _, document = selection
    before, history = store.snapshot(), store.history()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("prepare spawned"))
    checked = store.workflows.validate(document)
    assert checked["ok"]
    assert checked["steps"][2]["inputs"] == [
        {"name": "rows", "type": "rows", "required": True}, {"name": "files", "type": "files", "required": True}]
    missing = deepcopy(document)
    del missing["steps"][2]["inputs"]["files"]
    assert "missing_input" in {issue["code"] for issue in store.workflows.validate(missing)["issues"]}
    wrong = deepcopy(document)
    wrong["steps"][2]["inputs"]["files"] = {"from": "rows.rows"}
    assert "type_mismatch" in {issue["code"] for issue in store.workflows.validate(wrong)["issues"]}
    run = prepare(selection)
    frozen = run["steps"]["compile"]["prepared"][row]
    assert frozen["compiler"]["sha256"] == hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()
    assert frozen["inputs"]["snapshot_id"] == document["steps"][1]["ref"]["snapshot"]
    assert store.snapshot() == before and store.history() == history
    assert store.workflow_runs.get(run["id"])["status"] == "prepared"
    assert not (store.directory / run["directory"]).exists()


@pytest.mark.parametrize("change", [
    {"assets": []}, {"assets": [{"source": "missing.tex", "path": "main.tex"}]},
    {"assets": [{"source": "main.tex", "path": "../main.tex"}]},
    {"assets": [{"source": "main.tex", "path": "main.png"}]},
    {"entry_path": "sub/missing.tex"}, {"timeout_seconds": True}, {"timeout_seconds": 301},
    {"engine": "shell"}, {"compiler_path": "pdflatex"},
])
def test_invalid_selection_refuses_preparation(selection, change, monkeypatch):
    store, _, workflow, document = selection
    document["steps"][2]["parameters"].update(change)
    store.workflows.update(workflow, "Compile", document, expected_revision=store.info()["revision"])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("invalid prepare spawned"))
    with pytest.raises((ProjectError, ValueError)):
        prepare(selection)
    assert store.workflow_runs.list()["runs"] == []


def test_bridge_compiles_frozen_files_then_registers_and_snapshots_outputs(selection, compiler_fixture, inproc, monkeypatch):
    store, row, workflow, document = selection
    h, handle = open_bridge(inproc, store)
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow, "rows": [row],
        "run_id": str(uuid4()), "expected_revision": store.info()["revision"]})["run"]
    assert not compiler_fixture[1].exists()
    for name in ("main.tex", "章节.tex"):
        (store.directory / name).unlink()
    # Editing the live workflow after prepare cannot replace the frozen entry.
    document["steps"][2]["parameters"]["entry_path"] = "not-selected.tex"
    store.workflows.update(workflow, "Changed live definition", document, expected_revision=store.info()["revision"])
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert done["complete"], done["tasks"]
    produced = compile_task(done)["produced"]
    assert set(produced["files"]) == set(LatexCompileTemplate.outputs)
    snapshot = store.snapshots.get(produced["snapshot_id"])
    assert {item["record_id"] for item in snapshot["manifest"]["files"]} == set(produced["files"].values())
    identity = store.workflow_runs.local_attempt(run["id"], "compile", row, 1)
    receipt = latex.read_receipt(store, **identity)
    assert receipt["state"] == "succeeded" and receipt["inputs"]["entry_path"] == "main.tex"
    assert (store.directory / identity["directory"] / "input/main.tex").read_text() == "good"
    assert len(compiler_fixture[1].read_text().splitlines()) == 2
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("reopen/read spawned"))
    reopened = ProjectStore(store.directory)
    assert reopened.workflow_runs.get(run["id"])["complete"]
    assert latex.recover(reopened, **identity)["state"] == "succeeded"
    assert base64.b64decode(latex.read_log(reopened, **identity)["data"])
    assert not h.violations


def test_failure_logs_persist_and_only_explicit_restart_creates_new_attempt(selection, compiler_fixture, inproc):
    store, row, _, _ = selection
    compiler_fixture[0].write_text("failed")
    run = prepare(selection)
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    failed = settled(h, handle, run["id"])
    assert compile_task(failed)["status"] == "failed" and compile_task(failed)["produced"] is None
    identity = store.workflow_runs.local_attempt(run["id"], "compile", row, 1)
    assert latex.read_receipt(store, **identity)["state"] == "failed"
    assert b"selected source diagnostic" in base64.b64decode(latex.read_log(store, **identity)["data"])
    compiler_fixture[0].write_text("good")
    h.call("project.workflow_runs.get", {"handle": handle, "run_id": run["id"]})
    h.call("project.workflow_runs.recover", {"handle": handle, "run_id": run["id"]})
    assert len(compiler_fixture[1].read_text().splitlines()) == 2
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert done["complete"] and compile_task(done)["attempt"] == 2
    second = store.workflow_runs.local_attempt(run["id"], "compile", row, 2)
    assert second != identity and latex.read_receipt(store, **identity)["state"] == "failed"
    assert len(compiler_fixture[1].read_text().splitlines()) == 4


def test_cancel_terminates_the_current_compile_and_keeps_its_log(selection, compiler_fixture, inproc):
    store, row, _, _ = selection
    compiler_fixture[0].write_text("sleep")
    run = prepare(selection)
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    until(lambda: compiler_fixture[1].exists() and len(compiler_fixture[1].read_text().splitlines()) == 2)
    h.call("project.workflow_runs.cancel", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert compile_task(done)["status"] == "cancelled" and compile_task(done)["produced"] is None
    identity = store.workflow_runs.local_attempt(run["id"], "compile", row, 1)
    assert latex.read_receipt(store, **identity)["state"] == "cancelled"


def test_changed_compiler_is_rejected_before_execution(selection, compiler_fixture, inproc, tmp_path):
    store, _, workflow, document = selection
    compiler = tmp_path / "compiler"
    compiler.write_bytes(b"frozen compiler identity")
    compiler.chmod(0o700)
    document["steps"][2]["parameters"]["compiler_path"] = str(compiler)
    store.workflows.update(workflow, "Compile", document, expected_revision=store.info()["revision"])
    run = prepare(selection)
    compiler.write_bytes(b"replaced compiler identity")
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert compile_task(done)["status"] == "failed"
    assert "compiler changed" in compile_task(done)["error"]["message"]
    assert not compiler_fixture[1].exists()


def test_missing_compiler_reports_tool_selection_not_missing_project(selection, inproc, tmp_path):
    store, row, workflow, document = selection
    document["steps"][2]["parameters"]["compiler_path"] = str(tmp_path / "not-installed" / "pdflatex")
    store.workflows.update(workflow, "Compile", document, expected_revision=store.info()["revision"])
    h, handle = open_bridge(inproc, store)
    error = h.error("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow,
        "rows": [row], "run_id": str(uuid4()), "expected_revision": store.info()["revision"]})
    assert error["code"] == "invalid_params"
    assert "absolute compiler path" in error["message"] and "TeX Live or MiKTeX" in error["message"]
    assert store.workflow_runs.list()["runs"] == []


def test_explicit_retry_refuses_unsettled_previous_execution(selection, compiler_fixture, inproc):
    store, row, _, _ = selection
    compiler_fixture[0].write_text("failed")
    run = prepare(selection)
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    settled(h, handle, run["id"])
    identity = store.workflow_runs.local_attempt(run["id"], "compile", row, 1)
    receipt_path = store.directory / identity["directory"] / "compile.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["state"] = "running"  # A saved attempt still names this live owner.
    receipt_path.write_text(json.dumps(receipt))
    compiler_fixture[0].write_text("good")
    for attempt in (2, 3):
        h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
        done = settled(h, handle, run["id"])
        assert compile_task(done)["status"] == "failed" and compile_task(done)["attempt"] == attempt
        assert "live execution" in compile_task(done)["error"]["message"]
        assert len(compiler_fixture[1].read_text().splitlines()) == 2


def test_consumes_upstream_generated_snapshot_after_working_files_are_removed(selection, compiler_fixture, inproc, monkeypatch):
    class Source:
        id, name, local, table_id = "fixture-tex/1", "Controlled TeX source", True, None
        parameters, outputs = [], ["main.tex", "章节.tex"]

        def run(self, parameters, directory):
            directory.mkdir()
            (directory / "main.tex").write_text("good")
            (directory / "章节.tex").write_text("selected source\n", encoding="utf-8")

    store, row, workflow, document = selection
    monkeypatch.setitem(templates.LOCAL_TEMPLATES, Source.id, Source())
    document["steps"][1] = {"id": "input", "kind": "simulation", "ref": {"template": Source.id},
                             "inputs": {"rows": {"from": "rows.rows"}}}
    store.workflows.update(workflow, "Generated files", document, expected_revision=store.info()["revision"])
    run = prepare(selection)
    assert run["steps"]["compile"]["prepared"][row]["inputs"] is None
    execute = LatexCompileTemplate.execute_frozen

    def remove_working_then_execute(self, store, prepared, source, **kwargs):
        for name in Source.outputs:
            (store.directory / source["directory"] / name).unlink()
        return execute(self, store, prepared, source, **kwargs)

    monkeypatch.setattr(LatexCompileTemplate, "execute_frozen", remove_working_then_execute)
    h, handle = open_bridge(inproc, store)
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(h, handle, run["id"])
    assert done["complete"], done["tasks"]
    upstream = next(task for task in done["tasks"] if task["step"] == "input")["produced"]
    receipt = latex.read_receipt(store, **store.workflow_runs.local_attempt(run["id"], "compile", row, 1))
    assert receipt["inputs"]["snapshot_id"] == upstream["snapshot_id"]
    assert {item["record_id"] for item in receipt["inputs"]["assets"]} == set(upstream["files"].values())
