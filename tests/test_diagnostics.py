"""Deployment diagnostics must fail usefully without changing service state."""

import json
import subprocess
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from suan.runtime import diagnostics
from suan.runtime.cli import connect, server
from suan.runtime.common import atomic_json, init_config


def test_uninitialized_doctor_is_machine_readable_and_does_not_initialize(tmp_path):
    state = tmp_path / "missing"
    result = CliRunner().invoke(server, ["--state-dir", str(state), "doctor", "--json"])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["ok"] is False
    assert report["checks"][0]["id"] == "config"
    assert "suan server init" in report["checks"][0]["message"]
    assert not state.exists()


@pytest.mark.parametrize(
    "patch",
    [
        {"python": ""},
        {"workspace_root": "relative"},
        {"state_dir": "/different-state"},
        {"port": True},
        {"concurrency": 0},
        {"poll_interval": 0},
        {"scheduler_interval": float("nan")},
        {"token": ""},
    ],
)
def test_invalid_configuration_is_reported_without_starting_services(tmp_path, patch):
    config = init_config(tmp_path)
    config.update(patch)
    # Deliberately write invalid JSON numeric values for the diagnostic to reject.
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    report = diagnostics.diagnose_server(tmp_path)
    assert not report["ok"]
    assert report["checks"][0]["id"] == "config"
    assert not (tmp_path / "api.pid").exists()
    assert not (tmp_path / "runtime.sqlite3").exists()


@pytest.mark.parametrize("contents", ["{broken", "[]"])
def test_broken_config_is_a_json_failure(tmp_path, contents):
    (tmp_path / "config.json").write_text(contents)
    result = CliRunner().invoke(
        server, ["--state-dir", str(tmp_path), "doctor", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["checks"][0]["status"] == "fail"


def test_network_state_detection_uses_most_specific_mount(tmp_path, monkeypatch):
    mounts = [SimpleNamespace(mountpoint=str(tmp_path), fstype="nfs4")]
    monkeypatch.setattr(diagnostics.psutil, "disk_partitions", lambda **_: mounts)
    state = tmp_path / "local" / "runtime"
    assert diagnostics.state_filesystem_check(state)["status"] == "fail"
    mounts.append(SimpleNamespace(mountpoint=str(tmp_path / "local"), fstype="ext4"))
    assert diagnostics.state_filesystem_check(state)["status"] == "pass"


def test_directory_probes_are_removed_and_missing_paths_are_not_created(tmp_path):
    assert diagnostics.directory_check("workspace", tmp_path)["status"] == "pass"
    assert list(tmp_path.iterdir()) == []
    missing = tmp_path / "missing"
    assert diagnostics.directory_check("workspace", missing)["status"] == "fail"
    assert not missing.exists()


def test_database_checks_do_not_create_or_replace_database(tmp_path):
    assert diagnostics.database_check(tmp_path, 1)["status"] == "warn"
    path = tmp_path / "runtime.sqlite3"
    assert not path.exists()
    path.write_bytes(b"not a database")
    assert diagnostics.database_check(tmp_path, 1)["status"] == "fail"
    assert path.read_bytes() == b"not a database"


def test_configured_worker_interpreter_failure_and_timeout(tmp_path, monkeypatch):
    config = init_config(tmp_path)
    config["python"] = str(tmp_path / "missing-python")
    assert diagnostics.python_check(config, False, 1)["status"] == "fail"

    def timeout(argv, **kwargs):
        assert argv[0] == config["python"]
        assert kwargs["timeout"] == 0.1
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(diagnostics.subprocess, "run", timeout)
    result = diagnostics.python_check(config, True, 0.1)
    assert result["status"] == "fail"
    assert "timed out" in result["message"]


@pytest.mark.parametrize(
    "backend,commands",
    [
        ("pbs", ["qsub", "qstat", "qdel"]),
        ("slurm", ["sbatch", "squeue", "sacct", "scancel"]),
    ],
)
def test_missing_scheduler_commands_do_not_claim_cluster_acceptance(
    tmp_path, monkeypatch, backend, commands
):
    init_config(tmp_path)
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        diagnostics.RuntimeClient,
        "health",
        lambda _: {"api_version": 1, "status": "ok", "supervisor_running": True},
    )
    report = diagnostics.diagnose_server(tmp_path, backend)
    checks = {item["id"]: item for item in report["checks"]}
    assert checks["scheduler_commands"]["status"] == "fail"
    if diagnostics.os.name != "nt":
        assert all(name in checks["scheduler_commands"]["message"] for name in commands)
    assert checks["compute_nodes"]["status"] == "warn"
    assert not report["ok"]


def test_saved_connection_reports_incompatible_api_and_missing_profile(
    tmp_path, monkeypatch
):
    path = tmp_path / "connections.json"
    monkeypatch.setenv("STK_PROFILES_FILE", str(path))
    atomic_json(
        path,
        {"cluster": {"url": "http://127.0.0.1:9876", "token": "private-test-token"}},
    )
    monkeypatch.setattr(
        diagnostics.RuntimeClient,
        "health",
        lambda _: {"api_version": 2, "status": "ok"},
    )
    result = CliRunner().invoke(connect, ["check", "cluster", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["checks"][0]["status"] == "fail"
    assert "private-test-token" not in result.output
    result = CliRunner().invoke(connect, ["check", "absent", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["checks"][0]["id"] == "profile"
