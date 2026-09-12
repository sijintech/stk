"""Real independent services and the shipped scientific acceptance workflow."""

from pathlib import Path
import json
import subprocess
import sys
import time

import pytest
from click.testing import CliRunner

from suan.runtime import daemon
from suan.runtime.client import RuntimeClient
from suan.runtime.common import atomic_json, init_config, read_json, alive
from suan.runtime.models import TaskSpec
from suan.runtime.cli import connect, server


@pytest.fixture
def deployed(tmp_path):
    state = tmp_path / "runtime"
    config = init_config(state, tmp_path / "shared", port=0)
    config["poll_interval"] = 0.05
    atomic_json(state / "config.json", config)
    running = daemon.start(state)
    try:
        yield state, config, RuntimeClient(running["url"], config["token"])
    finally:
        running = daemon.start(state)
        client = RuntimeClient(running["url"], config["token"])
        for task in client.tasks():
            if task["state"] not in {"succeeded", "failed", "cancelled"}:
                client.cancel(task["id"])
                client.wait(task["id"], timeout=10)
        daemon.stop(state, supervisor=True)


def test_real_api_and_supervisor_restart_preserve_worker(deployed):
    state, config, client = deployed
    workspace = client.create_workspace("restart")["id"]
    spec = TaskSpec(
        workspace,
        [
            "{python}",
            "-c",
            "import time; print('started', flush=True); time.sleep(4); print('finished', flush=True)",
        ],
    )
    task = client.submit(spec, "restart-key")
    deadline = time.monotonic() + 10
    while not client.logs(task["id"])["bytes"]:
        assert time.monotonic() < deadline
        time.sleep(0.05)
    old = client.task(task["id"])
    worker = read_json(
        Path(config["workspace_root"]) / workspace / "runs" / task["id"] / "worker.json"
    )
    supervisor = read_json(state / "supervisor.pid")
    api = read_json(state / "api.pid")
    offset = client.logs(task["id"])["next_offset"]
    daemon.stop(state)
    assert alive(worker) and alive(supervisor) and not alive(api)
    running = daemon.start(state)
    reconnected = RuntimeClient(running["url"], config["token"])
    assert reconnected.submit(spec, "restart-key")["id"] == task["id"]
    assert reconnected.task(task["id"])["backend_id"] == old["backend_id"]
    daemon.stop(state, supervisor=True)
    assert alive(worker) and not alive(supervisor)
    running = daemon.start(state)
    restored = RuntimeClient(running["url"], config["token"])
    assert restored.wait(task["id"], timeout=15)["state"] == "succeeded"
    assert restored.logs(task["id"], offset=offset)["bytes"] == b"finished\n"
    assert restored.logs(task["id"])["bytes"].count(b"started") == 1


def test_shipped_parameter_sweep(deployed, tmp_path):
    state, config, client = deployed
    demo = Path(__file__).resolve().parents[1] / "examples/runtime/run_demo.py"
    output = tmp_path / "results"
    result = subprocess.run(
        [sys.executable, str(demo), "--state-dir", str(state), "--output", str(output)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    summaries = [json.loads(p.read_text()) for p in output.glob("*/summary.json")]
    assert sorted(s["mean"] for s in summaries) == [13, 26]
    assert len(list(output.glob("*/preview.png"))) == 2
    assert len(list(output.glob("*/field.vtk"))) == 2
    assert all(t["state"] == "succeeded" for t in client.tasks())
    report = json.loads(next(output.glob("acceptance-*.json")).read_text())
    assert report["status"] == "succeeded" and report["verified"]
    assert len(report["tasks"]) == 2
    assert "inputs/simulate.py" in report["source_sha256"]
    for task in report["tasks"]:
        assert task["verified"] and task["input_manifest"]
        assert task["idempotency_key"]
        assert task["verification"]["field_max_absolute_error"] == {
            "field.dat": 0,
            "field.vtk": 0,
        }
        assert task["compute_environment"]["python"]
        assert len(task["artifacts"]) == 5
    assert config["token"] not in json.dumps(report)


def test_doctor_and_saved_connection_check_running_stopped_and_bad_token(
    deployed, tmp_path, monkeypatch
):
    state, config, client = deployed
    runner = CliRunner()
    result = runner.invoke(
        server, ["--state-dir", str(state), "doctor", "--science", "--json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"]
    assert {c["id"]: c["status"] for c in report["checks"]}["database"] == "pass"
    assert config["token"] not in result.output
    profiles = tmp_path / "connections.json"
    monkeypatch.setenv("STK_PROFILES_FILE", str(profiles))
    atomic_json(profiles, {"cluster": {"url": client.url, "token": config["token"]}})
    assert runner.invoke(connect, ["check", "cluster"]).exit_code == 0
    atomic_json(
        profiles, {"cluster": {"url": client.url, "token": "incorrect-test-token"}}
    )
    result = runner.invoke(connect, ["check", "cluster", "--json"])
    assert result.exit_code == 1
    assert "authentication failed" in json.loads(result.output)["checks"][0]["message"]
    assert "incorrect-test-token" not in result.output
    daemon.stop(state, supervisor=True)
    result = runner.invoke(server, ["--state-dir", str(state), "doctor", "--json"])
    assert result.exit_code == 1
    assert not json.loads(result.output)["ok"]
    assert not daemon.status(state)["api_running"]
    assert not daemon.status(state)["supervisor_running"]


def test_acceptance_timeout_persists_keys_and_does_not_cancel_tasks(deployed, tmp_path):
    state, config, client = deployed
    demo = Path(__file__).resolve().parents[1] / "examples/runtime/run_demo.py"
    output = tmp_path / "timeout-results"
    # A stopped supervisor leaves submissions queued deterministically. Waiting
    # must time out without erasing evidence or cancelling those submissions.
    daemon.stop(state, supervisor=True)
    process = subprocess.Popen(
        [sys.executable, "-m", "suan.runtime.server", "--state-dir", str(state)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not daemon.status(state)["api_running"]:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        result = subprocess.run(
            [
                sys.executable,
                str(demo),
                "--state-dir",
                str(state),
                "--timeout",
                ".01",
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        report = json.loads(next(output.glob("acceptance-*.json")).read_text())
        assert report["status"] == "timed_out" and not report["verified"]
        assert len(report["active_task_ids"]) == 2
        restored = RuntimeClient(daemon.status(state)["url"], config["token"])
        for task in report["tasks"]:
            assert task["id"] in report["active_task_ids"]
            assert not restored.task(task["id"])["cancel_requested"]
            assert (
                restored.submit(task["spec"], task["idempotency_key"])["id"]
                == task["id"]
            )
    finally:
        process.terminate()
        process.wait(timeout=5)
