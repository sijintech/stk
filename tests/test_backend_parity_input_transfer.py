"""Real two-deployment input/revocation exercise and counterexamples to its success oracle."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples/backend_parity/input_transfer.py"
pytestmark = pytest.mark.server


def harness():
    spec = importlib.util.spec_from_file_location("backend_input_transfer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_late_terminal_action_reply_does_not_extend_its_original_deadline(monkeypatch):
    module = harness()
    ticks = iter((0, 0, 31))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    helper = SimpleNamespace(budget=lambda seconds: seconds, Unknown=RuntimeError)
    hub = SimpleNamespace(action=lambda identity: {"state": "succeeded"})
    with pytest.raises(RuntimeError, match="frozen deadline"):
        module.wait_action(helper, hub, "a" * 32)


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    if platform.system() != "Linux":
        pytest.skip("Runtime and Hub servers are Linux-only")
    for dependency in ("fastapi", "uvicorn", "websockets", "psutil"):
        pytest.importorskip(dependency)
    work = tmp_path_factory.mktemp("input-transfer")
    evidence = work / "evidence"
    env = {key: value for key, value in os.environ.items()
           if key not in ("STK_TOKEN_PLAN_MODEL", "DISPLAY", "WAYLAND_DISPLAY")}
    env["STK_TOKEN_PLAN_API_KEY"] = ""
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--mode", "source", "--deadline", "170",
                             "--evidence-dir", str(evidence), "--work-root", str(work)],
                            cwd=work, env=env, capture_output=True, text=True, timeout=210)
    documents = {name: json.loads((evidence / (name + ".json")).read_text(encoding="utf-8"))
                 for name in ("run-manifest", "assertions", "backend-parity", "resources")}
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert result.returncode == 0, (summary, documents["assertions"])
    assert summary["ok"]
    return documents


def test_real_upload_review_execution_and_hot_cold_device_revocation(actual):
    module = harness()
    result = actual["assertions"]
    assert result["ok"] and result["cleanup_ok"] and result["within_deadline"]
    assert len(result["assertions"]) == 11
    assert {item["status"] for item in result["assertions"]} == {"pass"}
    phases = actual["backend-parity"][0]
    for name in ("A", "B"):
        side = phases[name]
        assert side["partial"]["offset"] == 1024 * 1024
        assert side["finish"]["size"] == len(module.INPUT)
        assert side["files"][0]["sha256"] == hashlib.sha256(module.INPUT).hexdigest()
        assert side["output"] == hashlib.sha256(module.INPUT).hexdigest() + "\n"
        assert side["executions"][0]["start_markers"] == 1
    assert phases["B"]["import"]["before"] == "review" and phases["B"]["import"]["workspace_empty"]
    assert set(phases["B"]["revoked"]["denials"].values()) == {401}
    assert phases["B"]["revoked"]["denials"]["cold.status"] == 401
    manifest = actual["run-manifest"]
    assert manifest["module_origins"]["consistent"]
    assert manifest["module_origins"]["input_transfer_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert manifest["module_origins"]["harness_sha256"] == hashlib.sha256(SCRIPT.with_name("offline.py").read_bytes()).hexdigest()
    assert actual["resources"]["leftover_pids_after_cleanup"] == []
    assert actual["resources"]["removed_work_dir"] is True


@pytest.mark.parametrize("fault,expected", [
    ("new-session", "I1"), ("short-upload", "I2"), ("wrong-file-hash", "I3"),
    ("import-without-review", "I4"), ("task-input-changed", "I5"), ("wrong-output", "I6"),
    ("second-execution", "I7"), ("extra-queued-task", "I7"),
    ("submit-before-review", "I8"), ("revoked-still-allowed", "I9"),
    ("cold-client-allowed", "I9"), ("not-authorized-before", "I10"), ("new-action-created", "I10"),
    ("runtime-task-changed", "I11"), ("second-task", "I11"),
])
def test_counterexample_cannot_pass(actual, fault, expected):
    phases = copy.deepcopy(actual["backend-parity"][0])
    a, b = phases["A"], phases["B"]
    if fault == "new-session":
        a["resumed"]["same_id"] = False
    elif fault == "short-upload":
        b["finish"]["offset"] -= 1
    elif fault == "wrong-file-hash":
        a["files"][0]["sha256"] = "0" * 64
    elif fault == "import-without-review":
        b["import"]["before"] = "queued"
    elif fault == "task-input-changed":
        b["task"]["input_manifest"][0]["sha256"] = "0" * 64
    elif fault == "wrong-output":
        a["output"] = "0" * 64 + "\n"
    elif fault == "second-execution":
        a["executions"].append(copy.deepcopy(a["executions"][0]))
    elif fault == "extra-queued-task":
        a["task_count"] += 1
    elif fault == "submit-before-review":
        b["submit_review"] = False
    elif fault == "revoked-still-allowed":
        b["revoked"]["denials"]["upload.chunk"] = "allowed"
    elif fault == "cold-client-allowed":
        b["revoked"]["denials"]["cold.status"] = "allowed"
    elif fault == "not-authorized-before":
        b["revoked"]["before_authorized"] = False
    elif fault == "new-action-created":
        b["revoked"]["new_action_absent"] = False
    elif fault == "runtime-task-changed":
        b["revoked"]["runtime_task_unchanged"] = False
    elif fault == "second-task":
        b["revoked"]["runtime_task_count"] = 2
    statuses = {item["id"]: item["status"] for item in harness().checks(a, b)}
    assert statuses[expected] == "fail"

