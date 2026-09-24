"""Windows is client-only: the server Runtime refuses clearly and client paths keep working."""

import io
import json
import sys

from click.testing import CliRunner
import pytest

from suan.cli.main import utf8_stdio
from suan.runtime.cli import connect, jobs, server, workspaces
from suan.runtime.client import RuntimeClient
from suan.runtime.common import (
    UnsupportedServerPlatform,
    atomic_json,
    init_config,
    load_config,
    require_linux_server,
)


def test_server_configuration_refuses_off_linux(tmp_path, monkeypatch):
    configured = tmp_path / "configured"
    atomic_json(configured / "config.json", {"token": "private-test-token"})
    monkeypatch.setattr(sys, "platform", "win32")
    state = tmp_path / "state"
    with pytest.raises(UnsupportedServerPlatform, match="Linux only"):
        init_config(state)
    assert not state.exists()
    # The guard runs before reading, even when a configuration exists.
    with pytest.raises(UnsupportedServerPlatform, match="--profile"):
        load_config(configured)


def test_server_cli_explains_client_use_off_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    state = tmp_path / "state"
    runner = CliRunner()
    result = runner.invoke(server, ["--state-dir", str(state), "init"])
    assert result.exit_code == 1
    assert "Linux only" in result.output
    result = runner.invoke(server, ["--state-dir", str(state), "init", "--help"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(server, ["--state-dir", str(state), "doctor", "--json"])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["ok"] is False
    assert any(
        item["status"] == "fail" and "Linux only" in item["message"]
        for item in report["checks"]
    )
    assert not state.exists()


def test_client_commands_work_off_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("STK_RUNTIME_URL", raising=False)
    monkeypatch.delenv("STK_RUNTIME_TOKEN", raising=False)
    monkeypatch.setenv("STK_STATE_DIR", str(tmp_path / "state"))
    runner = CliRunner()
    result = runner.invoke(jobs, ["list"])
    assert result.exit_code == 1
    assert "--profile" in result.output

    profiles = tmp_path / "connections.json"
    monkeypatch.setenv("STK_PROFILES_FILE", str(profiles))
    atomic_json(
        profiles, {"p": {"url": "http://127.0.0.1:9876", "token": "private-test-token"}}
    )
    requests = []

    def request(self, method, path, data=None, binary=False):
        requests.append((self.url, method, path))
        return []

    monkeypatch.setattr(RuntimeClient, "request", request)
    result = runner.invoke(jobs, ["--profile", "p", "list"])
    assert result.exit_code == 0, result.output
    assert requests == [("http://127.0.0.1:9876", "GET", "tasks")]
    result = runner.invoke(connect, ["list"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"p": {"url": "http://127.0.0.1:9876"}}
    assert not (tmp_path / "state").exists()


def test_client_subcommand_help_needs_no_runtime_off_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("STK_RUNTIME_URL", raising=False)
    monkeypatch.delenv("STK_RUNTIME_TOKEN", raising=False)
    monkeypatch.setenv("STK_STATE_DIR", str(tmp_path / "state"))
    runner = CliRunner()
    for group, args in ((jobs, ["submit", "--help"]), (workspaces, ["upload", "--help"])):
        result = runner.invoke(group, args)
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.output and "Linux only" not in result.output
    # The connection error still surfaces once a command needs the Runtime.
    result = runner.invoke(workspaces, ["list"])
    assert result.exit_code == 1 and "Linux only" in result.output
    assert not (tmp_path / "state").exists()


def test_utf8_stdio_fixes_cp1252_and_keeps_gbk(monkeypatch):
    cp1252 = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    gbk = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    monkeypatch.setattr(sys, "stdout", cp1252)
    monkeypatch.setattr(sys, "stderr", gbk)
    utf8_stdio()
    assert cp1252.encoding == "utf-8"
    assert gbk.encoding == "gbk"
    # pythonw starts without console streams.
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    utf8_stdio()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs a Linux host")
def test_linux_host_may_run_the_server():
    assert require_linux_server() is None
